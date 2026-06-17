#!/usr/bin/env python3
"""
Neural morphing oscillator -- offline numpy trainer + quantizer.

Trains a tiny MLP (5 -> 8 -> 8 -> 1) whose `morph` control sweeps the output
timbre across a waveshape continuum (sine -> saw -> square -> pulse). The input
feature vector for a given phase phi and morph m is

    [ sin(phi), sin(2 phi), sin(3 phi), sin(4 phi), morph_scaled ]

i.e. the first four sine harmonics of the phase plus the morph amount. Training
is done in float with plain gradient descent (quality is SECONDARY -- the
milestone is bit-exactness of the integer forward pass, not audio fidelity).

After training, weights and biases are QUANTIZED to signed Q1.14 16-bit integers
and written to models/neural_weights.hex in the EXACT order the RTL / golden
model consume them (see "Weight memory layout" below). models/neural_ref.py and
src/neural_osc.sv both read that same file, so this script is the single source
of the trained constants.

Determinism: numpy's RNG is SEEDED, so re-running reproduces identical weights.

    python3 models/neural_train.py        # (re)writes models/neural_weights.hex
"""

import os
import numpy as np

# ---------------------------------------------------------------------------
# Fixed-point + topology constants -- MUST match models/neural_ref.py and
# src/neural_osc.sv exactly.
# ---------------------------------------------------------------------------
SEED      = 20260617                         # deterministic RNG seed
QBITS     = 14                              # fractional bits: Q1.14 features/weights
QSCALE    = 1 << QBITS                       # 16384
QMAX      =  (1 << 15) - 1                   # +32767  (signed 16-bit weight ceiling)
QMIN      = -(1 << 15)                       # -32768  (signed 16-bit weight floor)

LUT_DEPTH = 256                              # sine LUT entries (indexed by phase[15:8])
LUT_W     = 16                               # sine LUT word width (signed Q1.14)

N_IN      = 5                                # inputs: 4 harmonics + morph
H1        = 8                                # hidden layer 1 width
H2        = 8                                # hidden layer 2 width
N_OUT     = 1                                # single sample output

WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "neural_weights.hex")

# The neural_weights.hex file is laid out as ONE contiguous memory that both the
# RTL and the golden model $readmemh / read:
#
#     addr 0 .. LUT_DEPTH-1            : sine LUT (256 words, signed Q1.14)
#     addr LUT_DEPTH .. LUT_DEPTH+128  : 129 MLP weight/bias words
#
# Folding the LUT into the same file keeps the sine table bit-identical across
# Python and Verilog WITHOUT computing sin() in the RTL (Verilog has no portable
# integer sine), so there is no float-vs-LUT mismatch risk.
WEIGHT_BASE = LUT_DEPTH                       # MLP words start after the LUT

# Output scaling: the linear output neuron produces a Q1.14 value in roughly
# [-1, 1]; the engine emits a signed-16 audio sample. We scale the Q1.14 output
# up by OUT_SHIFT bits then clamp to signed-16. With OUT_SHIFT = 1, a full-scale
# +/-1.0 (Q1.14 = +/-16384) maps to about +/-32767 -- i.e. near full audio range.
OUT_SHIFT = 1


# ---------------------------------------------------------------------------
# Sine LUT (signed Q1.14). Generated here so the EXACT same quantized table is
# embedded in neural_weights.hex and used by both the golden model and the RTL.
# Index 0..LUT_DEPTH-1 covers one full period; value = round(sin(2*pi*k/N)*QSCALE),
# clamped to signed-16 (the +1.0 peak rounds to QSCALE = 16384 which is in range).
# ---------------------------------------------------------------------------
def build_sine_lut():
    lut = []
    for k in range(LUT_DEPTH):
        v = int(np.round(np.sin(2.0 * np.pi * k / LUT_DEPTH) * QSCALE))
        if v > QMAX:
            v = QMAX
        if v < QMIN:
            v = QMIN
        lut.append(v)
    return lut


# ---------------------------------------------------------------------------
# Target waveshapes as functions of normalized phase t in [0, 1).
# ---------------------------------------------------------------------------
def w_sine(t):
    return np.sin(2.0 * np.pi * t)


def w_saw(t):
    # rising sawtooth in [-1, 1)
    return 2.0 * (t - np.floor(t + 0.5))


def w_square(t):
    return np.where((t % 1.0) < 0.5, 1.0, -1.0)


def w_pulse(t):
    # 25% duty pulse
    return np.where((t % 1.0) < 0.25, 1.0, -1.0)


# Morph continuum: m in [0,1] interpolates sine -> saw -> square -> pulse across
# three equal segments.
def target_wave(t, m):
    segs = [w_sine, w_saw, w_square, w_pulse]
    x = m * (len(segs) - 1)          # 0..3
    i = int(np.floor(x))
    if i >= len(segs) - 1:
        return segs[-1](t)
    frac = x - i
    return (1.0 - frac) * segs[i](t) + frac * segs[i + 1](t)


# ---------------------------------------------------------------------------
# Feature builder (FLOAT version, mirrors the integer LUT path in neural_ref).
# phi normalized in [0,1); harmonics wrap.
# ---------------------------------------------------------------------------
def features_float(t, m):
    return np.array([
        np.sin(2.0 * np.pi * (1.0 * t % 1.0)),
        np.sin(2.0 * np.pi * (2.0 * t % 1.0)),
        np.sin(2.0 * np.pi * (3.0 * t % 1.0)),
        np.sin(2.0 * np.pi * (4.0 * t % 1.0)),
        2.0 * m - 1.0,                          # morph mapped to [-1, 1]
    ], dtype=np.float64)


# ---------------------------------------------------------------------------
# Build the training set.
# ---------------------------------------------------------------------------
def build_dataset():
    rng = np.random.default_rng(SEED)
    phases = np.linspace(0.0, 1.0, 64, endpoint=False)
    morphs = np.linspace(0.0, 1.0, 17)
    X, Y = [], []
    for m in morphs:
        for t in phases:
            X.append(features_float(t, m))
            Y.append([target_wave(t, m)])
    X = np.array(X, dtype=np.float64)
    Y = np.array(Y, dtype=np.float64)
    return X, Y, rng


# ---------------------------------------------------------------------------
# Tiny MLP in float (ReLU hidden, linear output). Trained with plain SGD.
# ---------------------------------------------------------------------------
def relu(z):
    return np.maximum(0.0, z)


def relu_grad(z):
    return (z > 0.0).astype(np.float64)


def train():
    X, Y, rng = build_dataset()
    n = X.shape[0]

    # He-ish init, scaled small so quantized weights stay in Q1.14 range.
    W1 = rng.standard_normal((N_IN, H1)) * 0.5
    b1 = np.zeros(H1)
    W2 = rng.standard_normal((H1, H2)) * 0.5
    b2 = np.zeros(H2)
    W3 = rng.standard_normal((H2, N_OUT)) * 0.5
    b3 = np.zeros(N_OUT)

    lr = 0.02
    epochs = 4000
    batch = 128
    for ep in range(epochs):
        idx = rng.permutation(n)
        for s in range(0, n, batch):
            bi = idx[s:s + batch]
            xb, yb = X[bi], Y[bi]
            # forward
            z1 = xb @ W1 + b1
            a1 = relu(z1)
            z2 = a1 @ W2 + b2
            a2 = relu(z2)
            out = a2 @ W3 + b3
            # backward (MSE)
            d = (out - yb) / xb.shape[0]
            dW3 = a2.T @ d
            db3 = d.sum(axis=0)
            da2 = d @ W3.T
            dz2 = da2 * relu_grad(z2)
            dW2 = a1.T @ dz2
            db2 = dz2.sum(axis=0)
            da1 = dz2 @ W2.T
            dz1 = da1 * relu_grad(z1)
            dW1 = xb.T @ dz1
            db1 = dz1.sum(axis=0)
            # update
            W3 -= lr * dW3; b3 -= lr * db3
            W2 -= lr * dW2; b2 -= lr * db2
            W1 -= lr * dW1; b1 -= lr * db1
        if (ep + 1) % 1000 == 0:
            z1 = X @ W1 + b1; a1 = relu(z1)
            z2 = a1 @ W2 + b2; a2 = relu(z2)
            out = a2 @ W3 + b3
            mse = float(np.mean((out - Y) ** 2))
            print("  epoch %4d  mse %.5f" % (ep + 1, mse))

    return (W1, b1, W2, b2, W3, b3)


# ---------------------------------------------------------------------------
# Quantization to signed Q1.14 16-bit, clamped to [QMIN, QMAX].
# ---------------------------------------------------------------------------
def quantize(x):
    """Round-to-nearest then clamp to signed 16-bit. (Used at BUILD time only;
    the runtime forward pass uses pure-integer truncating shifts.)"""
    q = int(np.round(x * QSCALE))
    if q > QMAX:
        q = QMAX
    if q < QMIN:
        q = QMIN
    return q


# ---------------------------------------------------------------------------
# Weight memory layout (THE consumption order -- ref model + RTL must agree).
#
#   Layer 1 (5->8): for j in 0..7:  W1[0..4][j] (5 words), then b1[j] (1 word)
#   Layer 2 (8->8): for j in 0..7:  W2[0..7][j] (8 words), then b2[j] (1 word)
#   Layer 3 (8->1): for j in 0..0:  W3[0..7][j] (8 words), then b3[j] (1 word)
#
# i.e. each output neuron contributes a contiguous block of (fan_in weights +
# 1 bias). Total = 8*(5+1) + 8*(8+1) + 1*(8+1) = 48 + 72 + 9 = 129 words.
# ---------------------------------------------------------------------------
def flatten_weights(params):
    W1, b1, W2, b2, W3, b3 = params
    words = []
    # Layer 1
    for j in range(H1):
        for i in range(N_IN):
            words.append(quantize(W1[i, j]))
        words.append(quantize(b1[j]))
    # Layer 2
    for j in range(H2):
        for i in range(H1):
            words.append(quantize(W2[i, j]))
        words.append(quantize(b2[j]))
    # Layer 3
    for j in range(N_OUT):
        for i in range(H2):
            words.append(quantize(W3[i, j]))
        words.append(quantize(b3[j]))
    return words


def write_weights(lut, words, path=WEIGHTS_PATH):
    """Write the combined memory image: sine LUT first, then MLP weights."""
    with open(path, "w", newline="\n") as f:
        for v in lut:
            f.write("%04x\n" % (v & 0xFFFF))
        for w in words:
            f.write("%04x\n" % (w & 0xFFFF))


def main():
    print("Neural morphing oscillator -- training (numpy, seeded)")
    print("  seed        = %d" % SEED)
    print("  topology    = %d -> %d -> %d -> %d  (ReLU hidden, linear out)"
          % (N_IN, H1, H2, N_OUT))
    params = train()
    lut = build_sine_lut()
    words = flatten_weights(params)
    write_weights(lut, words)

    mn, mx = min(words), max(words)
    print()
    print("quantization:")
    print("  format       = signed Q1.%d  (scale = %d)" % (QBITS, QSCALE))
    print("  weight count = %d  (L1=%d, L2=%d, L3=%d)"
          % (len(words), H1 * (N_IN + 1), H2 * (H1 + 1), N_OUT * (H2 + 1)))
    print("  quant range  = [%d, %d]  (clamp [%d, %d])" % (mn, mx, QMIN, QMAX))
    print("  out scaling  = << %d then clamp to signed-16" % OUT_SHIFT)
    print("  sine LUT     = %d entries x %d-bit (signed Q1.%d)"
          % (LUT_DEPTH, LUT_W, QBITS))
    print("  hex layout   = [0..%d] LUT, [%d..%d] weights  (%d words total)"
          % (LUT_DEPTH - 1, WEIGHT_BASE, WEIGHT_BASE + len(words) - 1,
             LUT_DEPTH + len(words)))
    print("  output file  = %s" % WEIGHTS_PATH)


if __name__ == "__main__":
    main()
