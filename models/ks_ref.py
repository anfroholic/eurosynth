#!/usr/bin/env python3
"""
Karplus-Strong plucked-string voice engine -- bit-exact integer reference model.

This is the GOLDEN reference for the `ks_engine` RTL (see docs/karplus_strong.md and
the engine contract in NOTES.md). The SystemVerilog implementation and its testbench
must reproduce the output of this model EXACTLY, sample for sample, bit for bit.

Everything here is plain Python `int` arithmetic so that it matches Verilog's
signed `>>>` (arithmetic right shift, floors toward -inf) and 16-bit two's-complement
wrap-on-store. No numpy, no floats anywhere in the data path.

Run with no args to (re)generate models/ks_golden.hex deterministically:

    python3 models/ks_ref.py
"""

import os

# ----------------------------------------------------------------------------
# Parameters -- these mirror the `ks_engine` module parameters EXACTLY.
# The RTL testbench MUST use the same values.
# ----------------------------------------------------------------------------
SAMPLE_W    = 16        # sample bit width
NMAX        = 1024      # delay-line depth (max period)
DECAY_NUM   = 2047      # feedback gain numerator
DECAY_SHIFT = 12        # feedback gain = DECAY_NUM / 2^DECAY_SHIFT  (~0.49976)
LFSR_SEED   = 0xACE1    # 16-bit LFSR seed
LFSR_POLY   = 0xB400    # Galois taps: x^16 + x^14 + x^13 + x^11 + 1

# ----------------------------------------------------------------------------
# Fixed golden scenario constants -- the TB will mirror these EXACTLY.
# ----------------------------------------------------------------------------
PGOLDEN = 48            # pluck period (sets pitch) for the golden run
NSAMP   = 256           # number of sustain steps to capture

GOLDEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ks_golden.hex")


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
# Karplus-Strong engine -- mirrors the integer algorithm in the contract.
# ----------------------------------------------------------------------------
class KS:
    def __init__(self):
        self.reset()

    def reset(self):
        """Reset: line all 0, ptr=0, lfsr=LFSR_SEED, sample=0."""
        self.line   = [0] * NMAX
        self.ptr    = 0
        self.lfsr   = LFSR_SEED
        self.N      = 2
        self.sample = 0

    @staticmethod
    def _clamp_period(period):
        """Effective length N = clamp(period, 2, NMAX-1)."""
        if period < 2:
            return 2
        if period > NMAX - 1:
            return NMAX - 1
        return period

    def pluck(self, period):
        """(Re)excite the string.

        Reset lfsr = LFSR_SEED, then for i in 0..N-1: step the lfsr and write
        line[i] = signed16(lfsr). Set ptr = 0.

        The RTL does this incrementally (one write per clk after the pluck strobe),
        completing within N clks before the next sample_tick. This model performs the
        same writes at sample granularity -- identical final buffer contents.
        """
        self.N   = self._clamp_period(period)
        self.lfsr = LFSR_SEED
        for i in range(self.N):
            self.lfsr = lfsr_step(self.lfsr)
            self.line[i] = to_signed16(self.lfsr)
        self.ptr = 0

    def tick(self):
        """One sustain step (one sample_tick). Returns the value output THIS tick.

            out  = line[ptr]
            prev = line[(ptr + N - 1) mod N]
            acc  = (out + prev) * DECAY_NUM        // signed, >= 32-bit
            new  = acc >>> DECAY_SHIFT             // arithmetic right shift
            line[ptr] = new[15:0]                  // 16-bit wrap on store
            ptr  = (ptr + 1) mod N
            sample <= out
        """
        N    = self.N
        ptr  = self.ptr
        out  = self.line[ptr]
        prev = self.line[(ptr + N - 1) % N]
        acc  = (out + prev) * DECAY_NUM      # plain Python int -> exact signed math
        new  = acc >> DECAY_SHIFT            # Python >> on ints floors toward -inf == Verilog >>>
        self.line[ptr] = to_signed16(new)    # store low 16 bits, two's-complement wrap
        self.ptr = (ptr + 1) % N
        self.sample = out                    # registered output = value read THIS tick
        return out


# ----------------------------------------------------------------------------
# Golden scenario runner
# ----------------------------------------------------------------------------
def run_golden():
    """Reset, one pluck at PGOLDEN, then NSAMP sustain steps. Returns list of samples."""
    ks = KS()
    ks.reset()
    ks.pluck(PGOLDEN)
    return [ks.tick() for _ in range(NSAMP)]


def write_golden(samples, path=GOLDEN_PATH):
    """Write one 4-digit lowercase hex word per line (16-bit two's complement).

    Plain hex words only, no header -- parses cleanly with Verilog `$readmemh`.
    """
    with open(path, "w", newline="\n") as f:
        for s in samples:
            f.write("%04x\n" % (s & 0xFFFF))


def main():
    samples = run_golden()
    write_golden(samples)

    print("Karplus-Strong golden reference (bit-exact integer model)")
    print("scenario:")
    print("  PGOLDEN     = %d  (delay length N, sets pitch)" % PGOLDEN)
    print("  NSAMP       = %d  (sustain steps captured)" % NSAMP)
    print("  SAMPLE_W    = %d" % SAMPLE_W)
    print("  NMAX        = %d" % NMAX)
    print("  DECAY_NUM   = %d" % DECAY_NUM)
    print("  DECAY_SHIFT = %d  (gain = %d/%d = %.5f)" %
          (DECAY_SHIFT, DECAY_NUM, 1 << DECAY_SHIFT, DECAY_NUM / float(1 << DECAY_SHIFT)))
    print("  LFSR_SEED   = 0x%04X" % LFSR_SEED)
    print("  LFSR_POLY   = 0x%04X" % LFSR_POLY)
    print("  output file = %s" % GOLDEN_PATH)
    print()
    print("first 8 samples (decimal):", samples[:8])
    print("last 4 samples  (decimal):", samples[-4:])
    print("min = %d   max = %d" % (min(samples), max(samples)))


if __name__ == "__main__":
    main()
