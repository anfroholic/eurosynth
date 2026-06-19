#!/usr/bin/env python3
"""
Render the TRUE 12 kHz audio previews -- what the chip actually sounds like at
the recommended 12.288 MHz clock (fs = clk / 1024 = 12 kHz).

This is the companion to render_audio.py (which renders at 48 kHz, a comfier
listening rate that's equivalent to clocking the chip ~4x faster). Here we drive
the SAME bit-exact reference models with the SAME musical performances, but at
fs = 12 kHz and with the control values RE-TUNED so the pitch/tempo land in the
same place. That way an A/B of ks.wav vs ks_12k.wav isolates exactly one thing:
the sonic character of the real 12 kHz rate (less high-end, more aliasing grit).

Two engines can't be pitch-matched, and we keep them honest:
  * chaos  -- advances one map step per sample, so its pitch is tied to fs; at
             12 kHz the same config sounds ~2 octaves lower than the 48 kHz clip.
  * neural -- on the real chip the pitch bus is 10-bit (max ~187 Hz), so the
             neural voice IS a bass. We render it at a real in-range note.

Output: previews/<name>_12k.wav (12 kHz, mono, 16-bit PCM). The 48 kHz set is
left untouched. The reference models are not modified -- we only call their API.

Run:
    python3 models/render_audio_12k.py
or inside the sim container:
    bash scripts/sim.sh bash -lc 'python3 models/render_audio_12k.py'
"""

import os
import sys
import struct
import wave

# Make the models package importable regardless of CWD.
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ks_ref
import bytebeat_ref
import chaos_ref
import sid_ref
import neural_ref

SR = 12000  # TRUE chip sample rate at the recommended 12.288 MHz clock

PREVIEWS_DIR = os.path.normpath(os.path.join(HERE, "..", "previews"))


# ----------------------------------------------------------------------------
# WAV writing + helpers (same shape as render_audio.py, retuned for 12 kHz)
# ----------------------------------------------------------------------------
def clamp16(x):
    if x > 32767:
        return 32767
    if x < -32768:
        return -32768
    return int(x)


def apply_gain(samples, gain):
    if gain == 1.0:
        return samples
    return [clamp16(round(s * gain)) for s in samples]


def auto_gain(samples, target_peak=29000):
    """Gentle global gain: only boost quiet clips or tame clipping ones."""
    peak = max((abs(s) for s in samples), default=0)
    if peak == 0:
        return samples, 1.0
    if peak < 13000 or peak > 32000:
        gain = target_peak / float(peak)
        return apply_gain(samples, gain), gain
    return samples, 1.0


def write_wav(name, samples):
    path = os.path.join(PREVIEWS_DIR, name)
    frames = b"".join(struct.pack("<h", clamp16(s)) for s in samples)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)
    seconds = len(samples) / float(SR)
    peak = max((abs(s) for s in samples), default=0)
    return path, seconds, peak


def fade(samples, n=120):
    """Short linear fade-in/out (default 10 ms @ 12 kHz) to avoid click joins."""
    out = list(samples)
    n = min(n, len(out) // 2)
    for i in range(n):
        g = i / float(n)
        out[i] = clamp16(round(out[i] * g))
        out[-1 - i] = clamp16(round(out[-1 - i] * g))
    return out


# Pitch helper for KS: delay length N for a target Hz at THIS sample rate.
def ks_period_for(hz):
    n = int(round(SR / float(hz)))
    return max(2, min(255, n))


# ----------------------------------------------------------------------------
# 1) Karplus-Strong -- the SAME phrase as the 48 kHz clip (~220..393 Hz),
#    re-tuned: at 12 kHz, period N = 12000 / f, so the notes match in pitch.
# ----------------------------------------------------------------------------
def render_ks():
    ks = ks_ref.KS()
    ks.reset()
    # 48 kHz used periods [218,183,163,145,122,...] -> ~220,262,294,331,393 Hz.
    # Reproduce those pitches at 12 kHz via N = 12000/f.
    melody_hz = [220, 262, 294, 331, 393, 331, 294, 262, 220, 262, 331, 331]
    note_len = int(0.30 * SR)   # 300 ms ring per note (same as 48 kHz clip)
    out = []
    for hz in melody_hz:
        ks.pluck(ks_period_for(hz))
        for _ in range(note_len):
            out.append(ks.tick())
    for _ in range(int(0.4 * SR)):     # let the last note ring out
        out.append(ks.tick())
    out, _ = auto_gain(out)
    return fade(out)


# ----------------------------------------------------------------------------
# 2) Bytebeat -- same four formulas, ~0.9 s each. t_inc scaled so t advances at
#    the same real-time rate as the 48 kHz clip: 48k used t_inc=6, so at 12 kHz
#    t_inc = 6 * 48000/12000 = 24 (fits the chip's 8-bit t_inc field).
# ----------------------------------------------------------------------------
def render_bytebeat():
    bb = bytebeat_ref.Bytebeat()
    bb.reset()
    t_inc = 24
    block = int(0.9 * SR)
    out = []
    for sel in range(4):
        seg = [bb.tick(sel, t_inc) for _ in range(block)]
        out.extend(fade(seg, n=60))
    out, _ = auto_gain(out)
    return out


# ----------------------------------------------------------------------------
# 3) Chaos -- SAME config program as the 48 kHz clip. Chaos steps once per
#    sample, so at 12 kHz it sits ~2 octaves lower (this is rate-bound and
#    honest: the chip's chaos pitch follows fs). Logistic tone->noise sweep,
#    then CA-perturbed grit, then a low Lorenz growl.
# ----------------------------------------------------------------------------
def render_chaos():
    ch = chaos_ref.Chaos()
    out = []

    step_len = int(0.05 * SR)          # 50 ms per r_seed value
    ch.config(0, 0, 96)
    ch.reset()
    for rseed in range(96, 252, 2):
        ch.config(0, 0, rseed)         # change r WITHOUT reset (keep trajectory)
        for _ in range(step_len):
            out.append(ch.tick())
    out = out[:int(1.6 * SR)]          # keep the sweep to ~1.6 s

    ch.config(1, 3, 0xC4)              # CA-perturbed logistic ~0.9 s
    ch.reset()
    seg = [ch.tick() for _ in range(int(0.9 * SR))]
    out.extend(fade(seg, n=60))

    ch.config(2, 0, 0x00)              # Lorenz ~1.0 s
    ch.reset()
    seg = [ch.tick() for _ in range(int(1.0 * SR))]
    out.extend(fade(seg, n=60))

    out, _ = auto_gain(out)
    return fade(out)


# ----------------------------------------------------------------------------
# 4) SID -- same 3-voice arpeggio + ring/sync/noise as the 48 kHz clip, with the
#    phase words recomputed for 12 kHz so the pitches match (F = 65536*hz/12000).
# ----------------------------------------------------------------------------
def render_sid():
    SAW, TRI, PULSE, NOISE = 0, 1, 2, 3
    sid = sid_ref.SID()
    sid.reset()
    out = []

    def fword(hz):
        return int(round(65536.0 * hz / SR)) & 0xFFFF

    chord = [
        (130.8, 196.0, 261.6, PULSE, 0b010, 0b000, 0x80),
        (164.8, 246.9, 329.6, PULSE, 0b010, 0b000, 0x40),
        (196.0, 293.7, 392.0, PULSE, 0b010, 0b010, 0x80),
        (261.6, 392.0, 523.3, NOISE, 0b010, 0b010, 0x80),
        (196.0, 293.7, 392.0, PULSE, 0b010, 0b000, 0xC0),
        (164.8, 246.9, 329.6, PULSE, 0b010, 0b000, 0x80),
    ]
    note_len = int(0.5 * SR)
    for (h0, h1, h2, w2, ring, sync, pw2) in chord:
        freq = [fword(h0), fword(h1), fword(h2)]
        wave_sel = [SAW, TRI, w2]
        pw = [0x00, 0x00, pw2]
        seg = [sid.tick(freq, wave_sel, pw, ring, sync) for _ in range(note_len)]
        out.extend(fade(seg, n=60))
    out, _ = auto_gain(out)
    return fade(out)


# ----------------------------------------------------------------------------
# 5) Neural morphing oscillator -- on the real chip the pitch bus is 10-bit
#    (phase inc = pitch, f = pitch*12000/65536), so the neural voice tops out
#    near 187 Hz: it's a BASS. We hold A2 (~110 Hz, pitch=601, in range) and
#    sweep morph 0..255 -> the sine->saw->square->pulse glide as a low bass.
# ----------------------------------------------------------------------------
def render_neural():
    lut, w = neural_ref.load_lut_and_weights()
    nn = neural_ref.Neural(lut, w)
    nn.reset()
    pitch = 601                        # ~110 Hz at 12 kHz; within the 10-bit bus
    total = int(3.0 * SR)
    out = []
    for i in range(total):
        morph = (i * 256) // total
        if morph > 255:
            morph = 255
        out.append(nn.tick(pitch, morph))
    out, _ = auto_gain(out)
    return fade(out)


# ----------------------------------------------------------------------------
# 6) Tour -- ~2 s of each engine, back to back.
# ----------------------------------------------------------------------------
def render_tour(clips):
    seg_len = int(2.0 * SR)
    out = []
    for name in ("ks", "bytebeat", "chaos", "sid", "neural"):
        src = clips[name]
        if len(src) > seg_len:
            start = (len(src) - seg_len) // 2
            seg = src[start:start + seg_len]
        else:
            seg = list(src)
        out.extend(fade(seg, n=240))
    return out


def main():
    os.makedirs(PREVIEWS_DIR, exist_ok=True)

    clips = {}
    clips["ks"] = render_ks()
    clips["bytebeat"] = render_bytebeat()
    clips["chaos"] = render_chaos()
    clips["sid"] = render_sid()
    clips["neural"] = render_neural()
    clips["tour"] = render_tour(clips)

    order = ["ks", "bytebeat", "chaos", "sid", "neural", "tour"]
    print("Rendered TRUE-rate previews (12 kHz, mono, 16-bit PCM) -> %s"
          % PREVIEWS_DIR)
    for name in order:
        path, seconds, peak = write_wav(name + "_12k.wav", clips[name])
        print("  %-15s  %5.2f s  peak=%6d  %s"
              % (name + "_12k.wav", seconds, peak, os.path.basename(path)))


if __name__ == "__main__":
    main()
