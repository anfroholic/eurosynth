#!/usr/bin/env python3
"""
Neural morphing oscillator -- BIT-EXACT integer reference (the golden oracle).

This is a pure-integer forward pass of the trained MLP. It mirrors
src/neural_osc.sv operation-for-operation: same sine LUT, same feature build,
same fixed-point MACs, same truncating arithmetic shifts (Python `>>` on ints
floors toward -inf, identical to Verilog `>>>`), same ReLU, same output scale
and signed-16 clamp. The RTL forward pass MUST equal this model bit-for-bit.

Reads models/neural_weights.hex (written by models/neural_train.py), which holds
the sine LUT (first LUT_DEPTH words) followed by the 129 MLP weight/bias words.

    python3 models/neural_ref.py        # (re)writes models/neural_golden.hex
"""

import os

# ---------------------------------------------------------------------------
# Fixed-point + topology constants -- MUST match neural_train.py and the RTL.
# ---------------------------------------------------------------------------
SAMPLE_W  = 16
QBITS     = 14                 # Q1.14 fractional bits (features + weights)
QSCALE    = 1 << QBITS         # 16384

LUT_DEPTH = 256                # sine LUT entries
PHASE_W   = 16                 # phase accumulator width (wraps mod 2^16)
LUT_SHIFT = PHASE_W - 8        # top 8 phase bits index the 256-entry LUT (= 8)

N_IN      = 5
H1        = 8
H2        = 8
N_OUT     = 1

OUT_SHIFT = 1                  # output Q1.14 << OUT_SHIFT -> signed-16, then clamp

WEIGHT_BASE = LUT_DEPTH        # MLP words begin right after the LUT
N_WEIGHTS   = H1 * (N_IN + 1) + H2 * (H1 + 1) + N_OUT * (H2 + 1)   # 129

HERE        = os.path.dirname(os.path.abspath(__file__))
WEIGHTS_PATH = os.path.join(HERE, "neural_weights.hex")
GOLDEN_PATH  = os.path.join(HERE, "neural_golden.hex")

# ---------------------------------------------------------------------------
# Golden scenario -- the TB mirrors these EXACTLY.
#   Sweep morph across MORPHS, step the phase by PITCH each tick, capture
#   NSTEP samples per morph value. Total = len(MORPHS) * NSTEP samples.
# ---------------------------------------------------------------------------
PITCH   = 0x140               # phase increment per tick (320 -> ~ period of 205 steps)
MORPHS  = [0, 64, 128, 192, 255]
NSTEP   = 51                  # samples captured per morph value (5*51 = 255 ~ 256)


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------
def to_signed16(x):
    """Reinterpret the low 16 bits of x as two's-complement signed 16-bit."""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def clamp16(x):
    """Saturating clamp to signed-16 range (used only at output scaling)."""
    if x > 32767:
        return 32767
    if x < -32768:
        return -32768
    return x


# ---------------------------------------------------------------------------
# Load the combined memory image (LUT + weights).
# ---------------------------------------------------------------------------
def load_mem(path=WEIGHTS_PATH):
    vals = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            vals.append(int(line, 16) & 0xFFFF)
    return vals


def load_lut_and_weights(path=WEIGHTS_PATH):
    mem = load_mem(path)
    lut = [to_signed16(mem[i]) for i in range(LUT_DEPTH)]
    w   = [to_signed16(mem[WEIGHT_BASE + i]) for i in range(N_WEIGHTS)]
    return lut, w


# ---------------------------------------------------------------------------
# Forward pass -- pure integer, mirrors the RTL datapath exactly.
# ---------------------------------------------------------------------------
class Neural:
    def __init__(self, lut, weights):
        self.lut = lut
        self.w = weights
        self.phase = 0          # 16-bit phase accumulator

    def reset(self):
        self.phase = 0

    def _sine(self, harm_phase):
        """LUT lookup: index = top 8 bits of (harm_phase mod 2^16)."""
        idx = (harm_phase >> LUT_SHIFT) & (LUT_DEPTH - 1)
        return self.lut[idx]

    def features(self, morph):
        """Build the 5-element Q1.14 feature vector from phase + morph."""
        ph = self.phase & 0xFFFF
        f = [
            self._sine((1 * ph) & 0xFFFF),
            self._sine((2 * ph) & 0xFFFF),
            self._sine((3 * ph) & 0xFFFF),
            self._sine((4 * ph) & 0xFFFF),
            ((morph << 7) - QSCALE),        # morph 0..255 -> Q1.14 [-16384, 16256]
        ]
        return f

    def _layer(self, inp, base, n_in, n_out, relu):
        """One dense layer. Weight block for neuron j is n_in weights then 1 bias,
        all contiguous starting at `base`. Accumulate products at full int width,
        add the bias shifted to the product scale, arithmetic-shift back to Q1.14,
        optionally ReLU."""
        out = []
        idx = base
        for _j in range(n_out):
            acc = 0
            for i in range(n_in):
                acc += inp[i] * self.w[idx]
                idx += 1
            bias = self.w[idx]
            idx += 1
            acc += bias << QBITS            # lift bias (Q1.14) to product scale (Q2.28)
            val = acc >> QBITS              # back to Q1.14 (floor toward -inf)
            if relu and val < 0:
                val = 0
            out.append(val)
        return out, idx

    def forward(self, morph):
        """Full 5->8->8->1 forward pass; returns the signed-16 sample.
        The weights array is consumed in order: L1 block, then L2, then L3."""
        f = self.features(morph)
        a1, b = self._layer(f,  0, N_IN, H1,    relu=True)
        a2, b = self._layer(a1, b, H1,   H2,    relu=True)
        o,  b = self._layer(a2, b, H2,   N_OUT, relu=False)
        # Output neuron is Q1.14; scale up and clamp to signed-16.
        sample = clamp16(o[0] << OUT_SHIFT)
        return sample

    def tick(self, pitch, morph):
        """Advance phase by pitch (wrap 16-bit), then compute the sample for the
        NEW phase. The registered RTL sample equals this for the same schedule."""
        self.phase = (self.phase + pitch) & 0xFFFF
        return self.forward(morph)


# ---------------------------------------------------------------------------
# Golden runner
# ---------------------------------------------------------------------------
def run_golden():
    lut, w = load_lut_and_weights()
    nn = Neural(lut, w)
    samples = []
    for m in MORPHS:
        nn.reset()                  # restart phase for each morph segment
        for _ in range(NSTEP):
            samples.append(nn.tick(PITCH, m))
    return samples


def write_golden(samples, path=GOLDEN_PATH):
    with open(path, "w", newline="\n") as f:
        for s in samples:
            f.write("%04x\n" % (s & 0xFFFF))


def main():
    samples = run_golden()
    write_golden(samples)

    print("Neural morphing oscillator -- golden reference (bit-exact integer)")
    print("scenario:")
    print("  PITCH    = 0x%03X (%d)  phase increment per tick" % (PITCH, PITCH))
    print("  MORPHS   = %s" % MORPHS)
    print("  NSTEP    = %d per morph  ->  %d samples total"
          % (NSTEP, len(MORPHS) * NSTEP))
    print("  topology = %d->%d->%d->%d  ReLU hidden, linear out"
          % (N_IN, H1, H2, N_OUT))
    print("  fmt      = Q1.%d features/weights; acc full int; >>%d requant; out <<%d"
          % (QBITS, QBITS, OUT_SHIFT))
    print("  LUT      = %d x %d-bit signed; phase %d-bit, top 8 bits index"
          % (LUT_DEPTH, SAMPLE_W, PHASE_W))
    print("  weights  = %d words (after %d-word LUT)" % (N_WEIGHTS, LUT_DEPTH))
    print("  output   = %s" % GOLDEN_PATH)
    print()
    print("first 8 samples (decimal):", samples[:8])
    print("last 4 samples  (decimal):", samples[-4:])
    print("min = %d   max = %d" % (min(samples), max(samples)))


if __name__ == "__main__":
    main()
