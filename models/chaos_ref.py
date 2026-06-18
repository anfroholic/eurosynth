#!/usr/bin/env python3
"""
Chaos voice engine -- bit-exact integer reference model.

This is the GOLDEN reference for the `chaos_engine` RTL (src/chaos_engine.sv).
The SystemVerilog implementation and its testbench must reproduce the output of
this model EXACTLY, sample for sample, bit for bit.

Everything here is plain Python `int` arithmetic so it matches Verilog's shifts
and 16-bit two's-complement wrap-on-store. No numpy, no floats in the data path.

The engine implements three deterministic chaotic maps selected by `map_sel`:

    map_sel = 0  LOGISTIC MAP                  x <- r*x*(1-x)          (Q16)
    map_sel = 1  CA-PERTURBED LOGISTIC         logistic, with a rule-30
                                               cellular automaton XORed
                                               into the low bits of r each
                                               update so the trajectory drifts
    map_sel = 2  LORENZ (fixed-point Euler)    x,y,z Lorenz system, output x

All three keep the SAME engine contract as ks_engine: synchronous active-low
reset, state advances only on `sample_tick`, the registered signed-16 `sample`
is stable between ticks.

Run with no args to (re)generate models/chaos_golden.hex deterministically:

    python3 models/chaos_ref.py
"""

import os

# ----------------------------------------------------------------------------
# Parameters -- mirror the `chaos_engine` module parameters EXACTLY.
# ----------------------------------------------------------------------------
SAMPLE_W = 16            # sample bit width

# ---- Logistic / CA fixed-point constants (Q16: 1.0 == 65536) ----
ONE_Q16  = 1 << 16       # 65536 == 1.0 in Q16
MASK16   = 0xFFFF
X_MAX    = 0xFFFF        # clamp ceiling for x (just under 1.0)

# ---- CA (rule-30) constants for map_sel=1 ----
CA_W     = 8             # 8-cell cellular automaton register
CA_RULE  = 30           # elementary CA rule used to perturb r

# ---- Lorenz fixed-point constants for map_sel=2 ----
# Lorenz: dx = sigma*(y-x); dy = x*(rho-z)-y; dz = x*y - beta*z.
# State held in Q12 fixed point. sigma=10, rho=28, beta=8/3 (~2.6640625 in Q8).
# dt chosen as a power-of-two shift (dt = 1/64) so the Euler step is exact-integer.
LZ_Q       = 12           # Q-format fractional bits for Lorenz state
LZ_SIGMA   = 10           # sigma (integer)
LZ_RHO     = 28           # rho   (integer)
LZ_BETA_Q8 = 683          # beta = 8/3 in Q8 == round(2.6666667*256) == 683
LZ_DT_SH   = 6            # dt = 2^-6 = 1/64  (Euler step = (deriv >> LZ_DT_SH))
# Reset state for Lorenz (Q12): x=y=z held near the attractor, deterministic.
LZ_X0 = 2 << LZ_Q         # x = 2.0
LZ_Y0 = 3 << LZ_Q         # y = 3.0
LZ_Z0 = 15 << LZ_Q        # z = 15.0
# Output scaling: Lorenz x roughly in [-25,+25]. x is Q12; to map ~+/-25 to
# signed16 we take (x_q12 >> 1) and wrap to 16 bits -> +/-25*4096/2 ~ +/-51200,
# which exceeds 16 bits, so 2's-comp wrap gives a bounded chaotic waveform
# (documented: we deliberately let the high-amplitude excursions wrap).
LZ_OUT_SH = 1             # sample = signed16(x_q12 >> LZ_OUT_SH)

GOLDEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chaos_golden.hex")


# ----------------------------------------------------------------------------
# Primitive helpers
# ----------------------------------------------------------------------------
def to_signed16(x):
    """Reinterpret the low 16 bits of x as a two's-complement signed 16-bit int."""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def ca_step(state, rule, width):
    """One elementary cellular-automaton step over a `width`-bit register.

    Periodic (wrap-around) boundary: cell i sees neighbours (i-1, i, i+1) mod width.
    `rule` is the 8-entry Wolfram rule (e.g. 30). Returns the new width-bit state.
    Pure integer, deterministic.
    """
    mask = (1 << width) - 1
    new = 0
    for i in range(width):
        left  = (state >> ((i + 1) % width)) & 1   # neighbour to the "left"  (higher bit)
        cen   = (state >> i) & 1
        right = (state >> ((i - 1) % width)) & 1    # neighbour to the "right" (lower bit)
        idx   = (left << 2) | (cen << 1) | right
        new  |= ((rule >> idx) & 1) << i
    return new & mask


# ----------------------------------------------------------------------------
# Chaos engine -- mirrors the integer algorithm in the contract.
# ----------------------------------------------------------------------------
class Chaos:
    def __init__(self):
        self.map_sel = 0
        self.rate    = 0
        self.r_seed  = 0
        self.reset()

    @staticmethod
    def r_q16(r_seed):
        """Map the 8-bit r_seed into the chaotic logistic range [3.000, 3.996] in Q16.

            r_q16 = (3 << 16) + (r_seed << 8)
        """
        return (3 << 16) + ((r_seed & 0xFF) << 8)

    @staticmethod
    def x_seed(r_seed):
        """Deterministic nonzero reset value for x (Q16), derived from r_seed.

        Build a value strictly inside (0, 1): take r_seed into the high byte and a
        fixed nonzero low byte so x can never be 0 (which would stick the logistic
        map at the 0 fixed point).
            x0 = ((r_seed << 8) | 0x80) & 0xFFFF  guaranteed in [0x0080, 0xFF80].
        """
        return (((r_seed & 0xFF) << 8) | 0x80) & MASK16

    def reset(self):
        """Synchronous reset. Initialise all map state deterministically."""
        # Logistic / CA-logistic state.
        self.x  = self.x_seed(self.r_seed)
        # CA register: seed with a fixed nonzero pattern (rule-30 from all-zero
        # would stay zero; we want a live automaton).
        self.ca = 0x01
        self.ca_cnt = 0
        # Lorenz state (Q12).
        self.lx = LZ_X0
        self.ly = LZ_Y0
        self.lz = LZ_Z0
        # Registered output.
        self.sample = 0

    # ---- individual map updates (each returns the signed-16 sample) ----
    def _logistic_next(self, r_q16):
        """One logistic update with the supplied r (Q16). Updates self.x, returns x_next."""
        x = self.x
        one_minus_x = ONE_Q16 - x                 # up to 65536 (17 bits)
        xmul   = (x * one_minus_x) >> 16          # Q16 of x*(1-x), in [0, 0.25]
        x_next = (r_q16 * xmul) >> 16             # Q16
        if x_next > X_MAX:                         # clamp to [0, 65535]
            x_next = X_MAX
        if x_next < 0:
            x_next = 0
        self.x = x_next
        return x_next

    def _tick_logistic(self):
        r_q16 = self.r_q16(self.r_seed)
        x_next = self._logistic_next(r_q16)
        # Center [0,1) Q16 -> signed16 [-1,1): sample = signed16(x - 32768).
        return to_signed16(x_next - 32768)

    def _tick_ca_logistic(self):
        # Advance the CA every `rate` ticks (every tick if rate == 0).
        # The CA bits perturb the low byte of r each update.
        if self.rate == 0 or self.ca_cnt >= self.rate:
            self.ca = ca_step(self.ca, CA_RULE, CA_W)
            self.ca_cnt = 0
        else:
            self.ca_cnt += 1
        # XOR the 8 CA bits into the low 8 bits of r_q16.
        r_q16 = self.r_q16(self.r_seed) ^ (self.ca & 0xFF)
        x_next = self._logistic_next(r_q16)
        return to_signed16(x_next - 32768)

    def _tick_lorenz(self):
        # Fixed-point forward-Euler Lorenz step, all integer.
        x, y, z = self.lx, self.ly, self.lz
        # Derivatives in Q12 (products formed wide, then shifted back to Q12).
        # dx = sigma*(y - x)
        dx = LZ_SIGMA * (y - x)
        # dy = x*(rho - z) - y ; x*(rho - z): x is Q12, (rho-z) is Q12 -> >>LZ_Q.
        dy = ((x * ((LZ_RHO << LZ_Q) - z)) >> LZ_Q) - y
        # dz = x*y - beta*z ; x*y both Q12 -> >>LZ_Q ; beta*z: beta Q8, z Q12 -> >>8.
        dz = ((x * y) >> LZ_Q) - ((LZ_BETA_Q8 * z) >> 8)
        # Euler integrate: state += deriv * dt, dt = 2^-LZ_DT_SH.
        # deriv is Q12; (deriv >> LZ_DT_SH) is the Q12 increment for this step.
        self.lx = x + (dx >> LZ_DT_SH)
        self.ly = y + (dy >> LZ_DT_SH)
        self.lz = z + (dz >> LZ_DT_SH)
        # Output coordinate x, scaled and wrapped to signed-16.
        return to_signed16(self.lx >> LZ_OUT_SH)

    def tick(self):
        """One sample_tick: advance the selected map, register and return the sample."""
        if self.map_sel == 0:
            s = self._tick_logistic()
        elif self.map_sel == 1:
            s = self._tick_ca_logistic()
        else:  # map_sel == 2
            s = self._tick_lorenz()
        self.sample = s
        return s

    def config(self, map_sel, rate, r_seed):
        """Apply the config slice (addr 0x11) WITHOUT advancing state."""
        self.map_sel = map_sel & 0x3
        self.rate    = rate & 0x3F
        self.r_seed  = r_seed & 0xFF


# ----------------------------------------------------------------------------
# Golden scenario runner
# ----------------------------------------------------------------------------
# Three blocks (one per implemented map_sel). The TB drives the IDENTICAL
# schedule: configure, assert reset for the block, then tick BLK times.
BLK   = 85                       # samples per map block
NSAMP = 3 * BLK                  # 255 total

# (map_sel, rate, r_seed) per block. Chosen to land each map in a lively regime.
BLOCKS = [
    (0,  0, 0xE6),   # logistic,    r = 3 + 0xE6/256*~1  -> ~3.90 (chaotic)
    (1,  3, 0xC4),   # CA-perturbed logistic, CA steps every 3 ticks
    (2,  0, 0x00),   # Lorenz (r_seed unused by the Lorenz path)
]


def run_golden():
    """Run each block from a fresh reset; concatenate the captured samples."""
    samples = []
    ch = Chaos()
    for (map_sel, rate, r_seed) in BLOCKS:
        ch.config(map_sel, rate, r_seed)
        ch.reset()                       # reset uses the just-applied config
        for _ in range(BLK):
            samples.append(ch.tick())
    return samples


def write_golden(samples, path=GOLDEN_PATH):
    """Write one 4-digit lowercase hex word per line (16-bit two's complement)."""
    with open(path, "w", newline="\n") as f:
        for s in samples:
            f.write("%04x\n" % (s & 0xFFFF))


def main():
    samples = run_golden()
    write_golden(samples)

    print("Chaos voice golden reference (bit-exact integer model)")
    print("scenario: 3 blocks x %d samples = %d total" % (BLK, NSAMP))
    for i, (m, rt, rs) in enumerate(BLOCKS):
        seg = samples[i * BLK:(i + 1) * BLK]
        name = {0: "logistic", 1: "CA-logistic", 2: "lorenz"}[m]
        print("  block %d  map_sel=%d (%-11s) rate=%-2d r_seed=0x%02X  "
              "first4=%s  min=%d max=%d"
              % (i, m, name, rt, rs, seg[:4], min(seg), max(seg)))
    print("  SAMPLE_W = %d" % SAMPLE_W)
    print("  output file = %s" % GOLDEN_PATH)
    print()
    print("first 8 samples (decimal):", samples[:8])
    print("last 4 samples  (decimal):", samples[-4:])
    print("min = %d   max = %d" % (min(samples), max(samples)))


if __name__ == "__main__":
    main()
