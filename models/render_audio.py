#!/usr/bin/env python3
"""
Render LISTENABLE audio previews for the eurosynth sound engines.

This DRIVES each bit-exact Python reference model under models/ with a longer,
musical scenario and renders a few seconds of audio to a WAV file under previews/.
The reference models themselves are NOT modified -- we only call their public API.

Output: 48 kHz, mono, 16-bit signed PCM. The ref models already emit signed-16
samples; we write them straight through (with only a gentle global gain when a
clip would otherwise be near-silent or clipping).

Run:
    python3 models/render_audio.py
or inside the sim container:
    bash scripts/sim.sh bash -lc 'python3 models/render_audio.py'
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

SR = 48000  # output sample rate (Hz)

PREVIEWS_DIR = os.path.normpath(os.path.join(HERE, "..", "previews"))


# ----------------------------------------------------------------------------
# WAV writing + helpers
# ----------------------------------------------------------------------------
def clamp16(x):
    if x > 32767:
        return 32767
    if x < -32768:
        return -32768
    return int(x)


def apply_gain(samples, gain):
    """Apply a (float) gain and clamp back to signed-16."""
    if gain == 1.0:
        return samples
    return [clamp16(round(s * gain)) for s in samples]


def auto_gain(samples, target_peak=29000):
    """Gentle global gain: only boost quiet clips or tame clipping ones.

    If the loudest sample is already comfortably in range we leave it alone.
    Returns (gained_samples, gain_applied)."""
    peak = max((abs(s) for s in samples), default=0)
    if peak == 0:
        return samples, 1.0
    # Boost if quiet (< ~40% FS) or attenuate if slamming the rails.
    if peak < 13000 or peak > 32000:
        gain = target_peak / float(peak)
        return apply_gain(samples, gain), gain
    return samples, 1.0


def write_wav(name, samples):
    """Write a mono 16-bit PCM WAV; return (path, seconds, peak)."""
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


def fade(samples, n=480):
    """Short linear fade-in/out (default 10 ms @48k) to avoid clicks at joins."""
    out = list(samples)
    n = min(n, len(out) // 2)
    for i in range(n):
        g = i / float(n)
        out[i] = clamp16(round(out[i] * g))
        out[-1 - i] = clamp16(round(out[-1 - i] * g))
    return out


# ----------------------------------------------------------------------------
# 1) Karplus-Strong -- pluck a short melody.
#    Lower period = higher pitch. At 48 kHz a period P gives ~ 48000/P Hz.
#    We pluck a little riff and let each note ring before re-plucking.
# ----------------------------------------------------------------------------
def render_ks():
    ks = ks_ref.KS()
    ks.reset()
    # A small ascending/descending phrase. Periods chosen for a pleasant range
    # (~150 Hz .. ~330 Hz). Smaller period => higher note.
    # 48000/period: 145->331Hz 163->294 183->262 218->220 145->331 122->393
    melody = [218, 183, 163, 145, 122, 145, 163, 183, 218, 183, 145, 145]
    note_len = int(0.30 * SR)   # 300 ms ring per note
    out = []
    for period in melody:
        ks.pluck(period)
        for _ in range(note_len):
            out.append(ks.tick())
    # Let the final note ring out a touch longer.
    for _ in range(int(0.4 * SR)):
        out.append(ks.tick())
    out, _ = auto_gain(out)
    return fade(out)


# ----------------------------------------------------------------------------
# 2) Bytebeat -- cycle the 4 formulas, ~0.9 s each, t free-running across.
#    t_inc sets how fast t advances => rhythm/pitch. ~6 keeps it rhythmic
#    and audible at 48 kHz without aliasing into garbage.
# ----------------------------------------------------------------------------
def render_bytebeat():
    bb = bytebeat_ref.Bytebeat()
    bb.reset()
    t_inc = 6
    block = int(0.9 * SR)   # ~0.9 s per formula
    out = []
    for sel in range(4):    # formulas 0,1,2,3
        seg = [bb.tick(sel, t_inc) for _ in range(block)]
        out.extend(fade(seg, n=240))   # tiny fade at each formula boundary
    out, _ = auto_gain(out)
    return out


# ----------------------------------------------------------------------------
# 3) Chaos -- sweep r_seed across the logistic chaotic range (tone -> noise),
#    then a CA-perturbed logistic segment, then a Lorenz segment.
#    r_q16 = 3 + r_seed/256 ; low r_seed = periodic/tone-ish, high = chaotic/noisy.
# ----------------------------------------------------------------------------
def render_chaos():
    ch = chaos_ref.Chaos()
    out = []

    # (a) Logistic sweep: r_seed climbs from ~periodic into full chaos.
    #     We re-config + tick in short steps so you hear the tone dissolve.
    step_len = int(0.05 * SR)        # 50 ms per r_seed value
    # logistic gets interesting/period-doubling around r~3.45+ (r_seed ~115)
    # and fully chaotic near r~3.9 (r_seed ~230). Sweep across that band.
    ch.config(0, 0, 96)
    ch.reset()
    for rseed in range(96, 252, 2):  # ~78 steps -> ~3.9 s of sweep... trim below
        ch.config(0, 0, rseed)       # change r WITHOUT reset (keep trajectory)
        for _ in range(step_len):
            out.append(ch.tick())
    # Keep the logistic sweep to ~1.6 s.
    out = out[:int(1.6 * SR)]

    # (b) CA-perturbed logistic ~0.9 s -- drifting, gritty chaos.
    ch.config(1, 3, 0xC4)
    ch.reset()
    seg = [ch.tick() for _ in range(int(0.9 * SR))]
    out.extend(fade(seg, n=240))

    # (c) Lorenz ~1.0 s -- low, growly wrapped attractor tone.
    ch.config(2, 0, 0x00)
    ch.reset()
    seg = [ch.tick() for _ in range(int(1.0 * SR))]
    out.extend(fade(seg, n=240))

    out, _ = auto_gain(out)
    return fade(out)


# ----------------------------------------------------------------------------
# 4) SID -- a short 3-voice patch: saw/triangle/pulse + ring + sync, then a
#    little arpeggio that also brings in noise. 16-bit phase: freq F gives
#    F * 48000 / 65536 Hz. e.g. F=0x0200 (512) -> ~375 Hz.
# ----------------------------------------------------------------------------
def render_sid():
    SAW, TRI, PULSE, NOISE = 0, 1, 2, 3
    sid = sid_ref.SID()
    sid.reset()
    out = []

    # freq for a MIDI-ish note: 65536 * f_hz / 48000.
    def fword(hz):
        return int(round(65536.0 * hz / SR)) & 0xFFFF

    # A small C-major-ish arpeggio (Hz) for the lead voice v0 (saw).
    chord = [
        # (v0_hz, v1_hz, v2_hz, wave_v2, ring_mask, sync_mask, pw_v2)
        (130.8, 196.0, 261.6, PULSE, 0b010, 0b000, 0x80),  # C3 root + ring on tri
        (164.8, 246.9, 329.6, PULSE, 0b010, 0b000, 0x40),  # E3
        (196.0, 293.7, 392.0, PULSE, 0b010, 0b010, 0x80),  # G3 + hard-sync v1
        (261.6, 392.0, 523.3, NOISE, 0b010, 0b010, 0x80),  # C4 + noise on v2
        (196.0, 293.7, 392.0, PULSE, 0b010, 0b000, 0xC0),  # back down to G3
        (164.8, 246.9, 329.6, PULSE, 0b010, 0b000, 0x80),  # E3
    ]
    note_len = int(0.5 * SR)   # 500 ms per step
    for (h0, h1, h2, w2, ring, sync, pw2) in chord:
        freq = [fword(h0), fword(h1), fword(h2)]
        wave_sel = [SAW, TRI, w2]
        pw = [0x00, 0x00, pw2]
        seg = [sid.tick(freq, wave_sel, pw, ring, sync) for _ in range(note_len)]
        out.extend(fade(seg, n=240))
    out, _ = auto_gain(out)
    return fade(out)


# ----------------------------------------------------------------------------
# 5) Neural morphing oscillator -- THE headline demo. Hold a steady pitch and
#    sweep morph 0 -> 255 slowly, many ticks per morph step, so you hear the
#    sine -> saw -> square -> pulse timbre morph as one continuous glide.
# ----------------------------------------------------------------------------
def render_neural():
    lut, w = neural_ref.load_lut_and_weights()
    nn = neural_ref.Neural(lut, w)
    nn.reset()
    # Steady pitch. PITCH=0x140 (320) -> ~ period of 65536/320 = 205 ticks
    # -> ~234 Hz at 48 kHz. A nice audible mid note.
    pitch = 0x140
    total = int(3.6 * SR)            # ~3.6 s glide
    out = []
    # Sweep morph 0..255 linearly across the whole clip; many ticks per value.
    for i in range(total):
        morph = (i * 256) // total   # 0 .. 255
        if morph > 255:
            morph = 255
        out.append(nn.tick(pitch, morph))
    out, _ = auto_gain(out)
    return fade(out)


# ----------------------------------------------------------------------------
# 6) Tour -- ~2 s of each engine, back to back, with fades between.
# ----------------------------------------------------------------------------
def render_tour(clips):
    seg_len = int(2.0 * SR)
    out = []
    for name in ("ks", "bytebeat", "chaos", "sid", "neural"):
        src = clips[name]
        # take a 2 s window from the middle so we land on the meatiest part
        if len(src) > seg_len:
            start = (len(src) - seg_len) // 2
            seg = src[start:start + seg_len]
        else:
            seg = list(src)
        out.extend(fade(seg, n=960))   # 20 ms crossfade-ish joins
    return out


# ----------------------------------------------------------------------------
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
    print("Rendered previews (48 kHz, mono, 16-bit PCM) -> %s" % PREVIEWS_DIR)
    for name in order:
        path, seconds, peak = write_wav(name + ".wav", clips[name])
        print("  %-12s  %5.2f s  peak=%6d  %s"
              % (name + ".wav", seconds, peak, os.path.basename(path)))


if __name__ == "__main__":
    main()
