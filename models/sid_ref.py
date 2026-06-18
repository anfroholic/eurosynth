#!/usr/bin/env python3
"""
SID-homage 3-voice oscillator engine -- bit-exact integer reference model.

This is the GOLDEN reference for the `sid_engine` / `sid_voice` RTL (voice 3 in
the spine mux; per-engine spec item 3 in docs/engines_plan.md). The
SystemVerilog implementation and its testbench must reproduce the output of this
model EXACTLY, sample for sample, bit for bit.

Everything here is plain Python `int` arithmetic so it matches Verilog's signed
`>>>` (arithmetic right shift, floors toward -inf) and 16-bit two's-complement
wrap-on-store. No numpy, no floats anywhere in the data path.

Algorithm (classic SID, all integer)
-------------------------------------
Three voices, each with a 16-bit phase accumulator advanced by `freq` on every
`sample_tick` (wraps naturally mod 2^16). Per voice we expose:
  * phase_msb  = phase >> 15          (the accumulator MSB)
  * overflow   = carry out of bit 15  ((phase_prev + freq) >> 16) & 1
Waveforms (selected by wave[2:0]) map to a signed-16 value centered on 0:
  0 saw      : (phase - 0x8000)                      -> -0x8000..0x7FFF ramp
  1 triangle : fold the phase about its MSB into an up/down ramp; if ring is
               enabled the *neighbor's* MSB is XORed into the fold sign first
               (classic SID ring-mod, which only affects the triangle).
  2 pulse    : compare the top 8 phase bits to pw: (phase>>8) >= pw -> +0x7FFF
               else -0x8000.
  3 noise    : a 16-bit Galois LFSR clocked once per accumulator overflow,
               sampled as a signed-16 word.
HARD SYNC (sync_en[i]): when this voice's modulation neighbor overflows on this
tick, voice i's accumulator is reset to 0 AFTER its own advance (so the neighbor
hard-resets this oscillator's phase).
RING / SYNC neighbor mapping: voice i is modulated by voice (i+2)%3 -- the
"previous" voice around the ring:  v0<-v2,  v1<-v0,  v2<-v1.
MIX: sum the three signed voice outputs (wide), arithmetic-shift right by 2
(>>2, floors toward -inf, == Verilog >>>2). Sum of three signed-16 fits in 18
bits; >>2 keeps |sample| < 2^16 so the registered signed-16 never saturates.

Run with no args to (re)generate models/sid_golden.hex deterministically:

    python3 models/sid_ref.py
"""

import os

# ----------------------------------------------------------------------------
# Parameters -- these mirror the `sid_engine` / `sid_voice` module params.
# The RTL testbench MUST use the same values.
# ----------------------------------------------------------------------------
SAMPLE_W   = 16          # sample bit width
PHASE_W    = 16          # phase-accumulator width (wraps mod 2^16)
NOISE_SEED = 0x7FFFF8    # ignored low bits aside, we use the low 16 here as seed
LFSR_SEED  = 0xACE1      # 16-bit noise LFSR seed (reproducible burst)
LFSR_POLY  = 0xB400      # Galois taps: x^16 + x^14 + x^13 + x^11 + 1

PHASE_MASK = (1 << PHASE_W) - 1          # 0xFFFF
PHASE_MSB  = 1 << (PHASE_W - 1)          # 0x8000

# ----------------------------------------------------------------------------
# Fixed golden scenario constants -- the TB mirrors these EXACTLY.
# ----------------------------------------------------------------------------
NSAMP    = 256           # number of samples to capture

# Phase 1 (samples 0 .. SWITCH-1):
#   v0 = saw
#   v1 = triangle, ring-modulated from its neighbor v0
#   v2 = pulse, pw = 0x80
# Phase 2 (samples SWITCH .. NSAMP-1):
#   v2 switches to noise, and hard-sync is enabled on v1 (neighbor v0 resets v1)
SWITCH   = 128

V0_FREQ  = 0x0123        # saw / ring+sync source
V1_FREQ  = 0x0456        # triangle (ring victim, later sync victim)
V2_FREQ  = 0x0789        # pulse / noise
V2_PW    = 0x80          # pulse width (top-8-bit threshold)

WAVE_SAW, WAVE_TRI, WAVE_PULSE, WAVE_NOISE = 0, 1, 2, 3

GOLDEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sid_golden.hex")


# ----------------------------------------------------------------------------
# Primitive helpers
# ----------------------------------------------------------------------------
def to_signed16(x):
    """Reinterpret the low 16 bits of x as a two's-complement signed 16-bit int."""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def lfsr_step(lfsr):
    """One Galois LFSR step. Returns the new 16-bit lfsr state.

        lsb  = lfsr & 1
        lfsr = lfsr >> 1
        if lsb: lfsr ^= LFSR_POLY      // 16-bit
    """
    lsb = lfsr & 1
    lfsr >>= 1
    if lsb:
        lfsr ^= LFSR_POLY
    return lfsr & 0xFFFF


# ----------------------------------------------------------------------------
# One SID voice -- 16-bit phase accumulator + waveform generator + noise LFSR.
# ----------------------------------------------------------------------------
class Voice:
    def __init__(self):
        self.reset()

    def reset(self):
        self.phase    = 0          # 16-bit phase accumulator
        self.overflow = 0          # carry out of the LAST advance (bit 16)
        self.lfsr     = LFSR_SEED  # noise LFSR state

    def advance(self, freq):
        """Advance the accumulator by freq; latch the overflow (carry out)."""
        nxt = self.phase + (freq & PHASE_MASK)
        self.overflow = (nxt >> PHASE_W) & 1
        self.phase = nxt & PHASE_MASK
        # Clock the noise LFSR once per accumulator overflow (classic SID-ish).
        if self.overflow:
            self.lfsr = lfsr_step(self.lfsr)

    def sync_reset(self):
        """Hard-sync: force the accumulator back to 0 (neighbor overflowed)."""
        self.phase = 0

    @property
    def phase_msb(self):
        return (self.phase >> (PHASE_W - 1)) & 1

    def waveform(self, wave, pw, ring, neighbor_msb):
        """Return this voice's signed-16 sample for the given controls.

        ring        : 1 => ring-mod the triangle with neighbor_msb
        neighbor_msb: the modulation neighbor's phase MSB (for ring-mod)
        """
        if wave == WAVE_SAW:
            # signed-centered ramp: phase 0..0xFFFF -> -0x8000..0x7FFF
            return to_signed16(self.phase - PHASE_MSB)

        if wave == WAVE_TRI:
            # Fold the phase about its MSB. The fold sign is the phase MSB,
            # XORed with the neighbor MSB when ring-mod is enabled (SID ring
            # affects only the triangle).
            sign = self.phase_msb
            if ring:
                sign ^= (neighbor_msb & 1)
            low15 = self.phase & 0x7FFF              # low 15 bits
            # When sign==0 ramp up (0..0x7FFE*2), when sign==1 ramp down.
            tri = (low15 ^ (0x7FFF if sign else 0)) << 1   # 16-bit unsigned triangle
            return to_signed16(tri - PHASE_MSB)            # center about 0

        if wave == WAVE_PULSE:
            # Compare the top 8 phase bits to the 8-bit pulse width.
            return 0x7FFF if (self.phase >> 8) >= (pw & 0xFF) else -0x8000

        # WAVE_NOISE: current LFSR state as a signed-16 word.
        return to_signed16(self.lfsr)


# ----------------------------------------------------------------------------
# SID engine -- 3 voices in a modulation ring + mix.
#   Neighbor (ring/sync source) of voice i is voice (i+2)%3.
# ----------------------------------------------------------------------------
class SID:
    NEIGHBOR = [2, 0, 1]   # voice i is modulated by voice NEIGHBOR[i]

    def __init__(self):
        self.reset()

    def reset(self):
        self.v = [Voice(), Voice(), Voice()]
        self.sample = 0

    def tick(self, freq, wave, pw, ring_en, sync_en):
        """One sample_tick. All args are 3-element lists / bitmasks.

        freq[i], wave[i], pw[i] : per-voice controls
        ring_en, sync_en        : 3-bit masks (bit i => voice i)
        Returns the registered signed-16 sample for THIS tick.
        """
        # 1) Advance every accumulator (latching each overflow). We read the
        #    PRE-advance MSBs for ring-mod so all voices see a consistent
        #    snapshot, exactly like the parallel RTL (neighbor_msb sampled from
        #    the registered phase before this tick's update is committed).
        pre_msb = [self.v[i].phase_msb for i in range(3)]
        for i in range(3):
            self.v[i].advance(freq[i])

        # 2) Hard sync: if voice i's neighbor overflowed THIS tick, reset i.
        #    Done after all advances so the overflow flags are settled.
        ov = [self.v[i].overflow for i in range(3)]
        for i in range(3):
            if (sync_en >> i) & 1:
                if ov[self.NEIGHBOR[i]]:
                    self.v[i].sync_reset()

        # 3) Produce each voice's waveform and sum (wide), then >>2 and register.
        outs = []
        for i in range(3):
            ring = (ring_en >> i) & 1
            nb   = self.NEIGHBOR[i]
            outs.append(self.v[i].waveform(wave[i], pw[i], ring, pre_msb[nb]))

        mix = outs[0] + outs[1] + outs[2]    # signed sum, fits in 18 bits
        self.sample = to_signed16(mix >> 2)  # arithmetic >>2 (floor toward -inf)
        return self.sample


# ----------------------------------------------------------------------------
# Golden scenario runner
# ----------------------------------------------------------------------------
def run_golden():
    """Reset, then NSAMP ticks under the scheduled config. Returns sample list."""
    sid = SID()
    sid.reset()
    out = []
    for k in range(NSAMP):
        if k < SWITCH:
            wave    = [WAVE_SAW, WAVE_TRI, WAVE_PULSE]
            ring_en = 0b010      # v1 ring-modulated by its neighbor v0
            sync_en = 0b000
        else:
            wave    = [WAVE_SAW, WAVE_TRI, WAVE_NOISE]
            ring_en = 0b010      # keep ring on v1
            sync_en = 0b010      # also hard-sync v1 from neighbor v0
        freq = [V0_FREQ, V1_FREQ, V2_FREQ]
        pw   = [0x00,    0x00,    V2_PW]
        out.append(sid.tick(freq, wave, pw, ring_en, sync_en))
    return out


def write_golden(samples, path=GOLDEN_PATH):
    """Write one 4-digit lowercase hex word per line (16-bit two's complement)."""
    with open(path, "w", newline="\n") as f:
        for s in samples:
            f.write("%04x\n" % (s & 0xFFFF))


def main():
    samples = run_golden()
    write_golden(samples)

    print("SID-homage golden reference (bit-exact integer model)")
    print("scenario:")
    print("  NSAMP      = %d  (samples captured)" % NSAMP)
    print("  SWITCH     = %d  (phase-1/phase-2 boundary)" % SWITCH)
    print("  PHASE_W    = %d  (accumulator width, wraps mod 2^%d)" % (PHASE_W, PHASE_W))
    print("  SAMPLE_W   = %d" % SAMPLE_W)
    print("  LFSR_SEED  = 0x%04X   LFSR_POLY = 0x%04X" % (LFSR_SEED, LFSR_POLY))
    print("  v*_freq    = 0x%04X 0x%04X 0x%04X" % (V0_FREQ, V1_FREQ, V2_FREQ))
    print("  v2_pw      = 0x%02X" % V2_PW)
    print("  phase 1 (0..%d):  v0 saw, v1 tri+ring(v0), v2 pulse(pw=0x%02X)" % (SWITCH - 1, V2_PW))
    print("  phase 2 (%d..%d): v2 -> noise, v1 +hard-sync(v0)" % (SWITCH, NSAMP - 1))
    print("  output file= %s" % GOLDEN_PATH)
    print()
    print("first 8 samples (decimal):", samples[:8])
    print("samples around switch    :", samples[SWITCH - 2:SWITCH + 2])
    print("last 4 samples  (decimal):", samples[-4:])
    print("min = %d   max = %d" % (min(samples), max(samples)))


if __name__ == "__main__":
    main()
