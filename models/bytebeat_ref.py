#!/usr/bin/env python3
"""
Bytebeat voice engine -- bit-exact integer reference model.

This is the GOLDEN reference for the `bytebeat` RTL (src/bytebeat.sv) and the
engine contract in NOTES.md / docs/engines_plan.md (per-engine spec item 1,
config addr 0x10). The SystemVerilog implementation and its testbench must
reproduce the output of this model EXACTLY, sample for sample, bit for bit.

"Bytebeat" music is a one-liner integer formula f(t) of a free-running time
counter; the low 8 bits are streamed as an unsigned 8-bit waveform. Here we
center that byte into signed 16-bit audio.

CRITICAL bit-exactness rule (mirrored verbatim in the RTL): every intermediate
operation is performed on an UNSIGNED 32-bit value with explicit 32-bit
wraparound. In Python we mask with & 0xFFFFFFFF after every arithmetic op
(especially the multiply, which can exceed 32 bits). All shifts are LOGICAL
(unsigned). In Verilog `t` and the intermediates are declared `[31:0]` so they
wrap at 32 bits identically. Take the low 8 bits as the output byte.

No numpy, no floats anywhere in the data path -- plain Python `int`.

Run with no args to (re)generate models/bytebeat_golden.hex deterministically:

    python3 models/bytebeat_ref.py
"""

import os

# ----------------------------------------------------------------------------
# Parameters -- these mirror the `bytebeat` module parameters EXACTLY.
# The RTL testbench MUST use the same values.
# ----------------------------------------------------------------------------
SAMPLE_W = 16          # sample bit width

MASK32 = 0xFFFFFFFF    # 32-bit wrap mask (applied after every arithmetic op)

# ----------------------------------------------------------------------------
# Fixed golden scenario constants -- the TB will mirror these EXACTLY.
#
# Four consecutive blocks of BLOCK samples, block i uses formula_sel = i, with
# t FREE-RUNNING across block boundaries (t is NOT reset between blocks). This
# exercises every selectable formula in one deterministic vector.
# ----------------------------------------------------------------------------
NFORMULA = 4           # number of formulas exercised
BLOCK    = 64          # samples per formula block
NSAMP    = NFORMULA * BLOCK   # total samples captured (256)
T_INC    = 1           # t increment per sample_tick for the golden run

GOLDEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "bytebeat_golden.hex")


# ----------------------------------------------------------------------------
# Primitive helpers
# ----------------------------------------------------------------------------
def to_signed16(x):
    """Reinterpret the low 16 bits of x as a two's-complement signed 16-bit int."""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


# ----------------------------------------------------------------------------
# Bytebeat formulas. Each returns the low 8 bits of a classic one-liner.
#
# ALL math is on a 32-bit UNSIGNED `t` with 32-bit wraparound: every arithmetic
# result is masked with & MASK32 so it wraps exactly like a Verilog [31:0] net.
# Shifts are logical (Python ints are non-negative here, so >> is logical). The
# documented expression next to each is textually parallel to the RTL.
# ----------------------------------------------------------------------------
def formula0(t):
    # 0:  t*(t>>5 | t>>8)
    v = (t * (((t >> 5) | (t >> 8)) & MASK32)) & MASK32
    return v & 0xFF


def formula1(t):
    # 1:  ( t*(t>>5 | t>>8) ) >> (t>>16 & 7)
    #     multiply wraps at 32 bits FIRST, then a variable logical right shift
    #     by (t>>16 & 7) in 0..7.
    v = (t * (((t >> 5) | (t >> 8)) & MASK32)) & MASK32
    sh = (t >> 16) & 7
    v = (v >> sh) & MASK32
    return v & 0xFF


def formula2(t):
    # 2:  t * ( ((t>>12)|(t>>8)) & (63 & (t>>4)) )
    inner = (((t >> 12) | (t >> 8)) & (63 & (t >> 4))) & MASK32
    v = (t * inner) & MASK32
    return v & 0xFF


def formula3(t):
    # 3:  t & (t>>8)
    v = (t & (t >> 8)) & MASK32
    return v & 0xFF


FORMULAS = [formula0, formula1, formula2, formula3]


def formula(sel, t):
    """Select a formula by 4-bit sel; out-of-range maps to formula 0 (mirrors RTL)."""
    if 0 <= sel < NFORMULA:
        return FORMULAS[sel](t)
    return FORMULAS[0](t)


# ----------------------------------------------------------------------------
# Bytebeat engine -- mirrors the integer algorithm in the contract.
# ----------------------------------------------------------------------------
class Bytebeat:
    def __init__(self):
        self.reset()

    def reset(self):
        """Reset: t = 0, sample = 0."""
        self.t = 0
        self.sample = 0

    def tick(self, formula_sel, t_inc):
        """One sample step (one sample_tick). Returns the value output THIS tick.

            byte8  = formula(formula_sel, t)[7:0]
            sample = signed16( (byte8 << 8) - 32768 )     // center 0..255 -> signed16
            t      = (t + (t_inc==0 ? 1 : t_inc)) & 0xFFFFFFFF
        """
        byte8 = formula(formula_sel, self.t) & 0xFF
        centered = ((byte8 << 8) - 32768)            # range -32768 .. 32512
        self.sample = to_signed16(centered)
        step = t_inc if t_inc != 0 else 1
        self.t = (self.t + step) & MASK32            # 32-bit free-running, wraps
        return self.sample


# ----------------------------------------------------------------------------
# Golden scenario runner
# ----------------------------------------------------------------------------
def run_golden():
    """Reset, then NFORMULA blocks of BLOCK samples; block i uses formula_sel=i,
    t_inc=T_INC, with t FREE-RUNNING across block boundaries (not reset).
    Returns a list of NSAMP samples."""
    bb = Bytebeat()
    bb.reset()
    out = []
    for sel in range(NFORMULA):
        for _ in range(BLOCK):
            out.append(bb.tick(sel, T_INC))
    return out


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

    print("Bytebeat golden reference (bit-exact integer model)")
    print("scenario:")
    print("  NFORMULA    = %d  (formulas exercised, sel = block index)" % NFORMULA)
    print("  BLOCK       = %d  (samples per formula block)" % BLOCK)
    print("  NSAMP       = %d  (total samples captured)" % NSAMP)
    print("  T_INC       = %d  (t increment per tick)" % T_INC)
    print("  SAMPLE_W    = %d" % SAMPLE_W)
    print("  output file = %s" % GOLDEN_PATH)
    print()
    print("formulas:")
    print("  0: t*(t>>5 | t>>8)")
    print("  1: ( t*(t>>5 | t>>8) ) >> (t>>16 & 7)")
    print("  2: t * ( ((t>>12)|(t>>8)) & (63 & (t>>4)) )")
    print("  3: t & (t>>8)")
    print()
    print("first 8 samples (decimal):", samples[:8])
    print("block boundary samples [63,64,127,128,191,192]:",
          [samples[i] for i in (63, 64, 127, 128, 191, 192)])
    print("last 4 samples  (decimal):", samples[-4:])
    print("min = %d   max = %d" % (min(samples), max(samples)))


if __name__ == "__main__":
    main()
