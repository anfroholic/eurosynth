# The Neural Engine — playing it, training it, and breaking it on purpose

> **This is the headliner.** Voice 7 of the EuroSynth chip is a tiny neural
> network that *is* the oscillator — there is no wavetable being played back and
> no classic synthesis formula. Every sample is the output of a 5→8→8→1 MLP run
> in fixed-point integer math on silicon. A single control, `morph`, walks the
> sound across a timbre continuum the network learned offline.
>
> This document is the creative guide: how to **play** it, how to **make your own
> weights**, and a pile of **playful ways to make sounds nothing else can**.
>
> Companions: [SOUND_RECIPES.md](SOUND_RECIPES.md) (the whole-chip patch
> cookbook), [SHOWCASE.md](SHOWCASE.md) (what the chip is), and
> [HARDWARE_GUIDE.md](HARDWARE_GUIDE.md) (wiring + the Arduino that drives it).
> The math lives in [`src/neural_osc.sv`](../src/neural_osc.sv),
> [`models/neural_train.py`](../models/neural_train.py), and
> [`models/neural_ref.py`](../models/neural_ref.py).

---

## TL;DR — make it sing in four moves

1. Select it: drive `voice_sel = 7` (the 3 dedicated input pins).
2. Give it a pitch: write the **pitch bus** (`ks_period`, 10 bits on `bidir[15:6]`).
   It's a **bass** voice — pitch ≈ `bus × 0.183 Hz`, topping out near **187 Hz**.
3. Pick a timbre: send SPI config word **`0x15`**, low byte = `morph`
   (`0x00` = sine … `0xFF` = pulse).
4. **Sweep `morph` over time** and listen to the tone *melt* between shapes.
   That sweep is the whole party trick — see [§3](#3-playing-it-the-morph-is-the-instrument).

Want to hear it on your laptop right now (no chip, no PDK)?

```bash
python3 models/render_audio.py        # writes previews/neural.wav (a morph glide)
```

---

## 1. What it actually is

Most "oscillators" read a stored shape or evaluate a formula. This one runs a
**neural network forward pass per audio sample**:

```
 phase accumulator ──► 4 sine harmonics (from a 256-entry LUT)  ┐
                                                                 ├─► [5→8→8→1 MLP] ─► sample
 morph control ─────────────────────────────────────────────────┘     ReLU hidden,
                                                                       linear output
```

- **Inputs (5 features):** the 1st, 2nd, 3rd and 4th sine harmonics of the
  current phase (looked up from a quantized sine table), plus the `morph` value
  scaled into `[-1, +1]`. So the network is *handed* a little harmonic palette
  and the morph knob, and it learns how to **mix and shape them** into a waveform.
- **Network:** 5 inputs → 8 → 8 → 1 output. ReLU on the hidden layers, linear on
  the output. All arithmetic is **Q1.14 fixed-point** (16-bit signed, 14
  fractional bits) running through one time-shared multiply-accumulate — about
  **139 clock cycles per sample**, which is plenty fast at the chip's 12 kHz
  sample rate.
- **The output is the audio.** No filter, no DAC trickery on-die: the network's
  single output neuron, scaled and clamped to signed-16, *is* the sample.
- **Why "morphing":** it was trained so that `morph` 0→1 interpolates the target
  waveform through **sine → sawtooth → square → 25%-pulse**. Because the network
  learned the *in-between* states too, sweeping `morph` sounds like one shape
  continuously dissolving into the next — much more like a filter sweep or a vowel
  morph than a hard waveform switch.

> **It is deliberately a bass engine.** With the 16-bit phase accumulator and the
> 12 kHz sample rate, the highest note is ~187 Hz. That's the design — it's meant
> to sit *under* the SID/Karplus voices, not over them. Lean into it: fat,
> breathing, morphing sub-bass is exactly what it's good at.

### The trust chain (why the chip sounds like your Python)

Everything is **bit-exact** end to end, which is what makes "train your own
weights" actually work:

```
 neural_train.py ──writes──► neural_weights.hex ──+── neural_ref.py ──► neural_golden.hex
        │                    (LUT + 129 weights)   │   (integer oracle)        │
        └──also writes──► src/neural_weights_init.svh                          │
                          (baked into the RTL)                                  │
                                   │                                            │
                          src/neural_osc.sv ◄──tb/tb_neural_osc.sv compares──► golden
```

The trainer emits the weights **twice**: once as `neural_weights.hex` (read by
the Python oracle) and once as `src/neural_weights_init.svh` (baked straight into
the RTL, so the build needs no runtime file). They are bit-for-bit identical. The
testbench proves the silicon matches the integer oracle exactly — when it prints
`NEURAL OK`, the chip will produce *precisely* the samples your Python did.

---

## 2. The controls (the full surface you can poke)

| What | Where | Notes |
|---|---|---|
| **Select the engine** | `voice_sel = 7` (input pins `2:0`) | One voice at a time; takes effect next audio frame. |
| **Pitch** | pitch bus `ks_period[9:0]` (`bidir[15:6]`) | `freq ≈ bus × 0.183 Hz`; max ≈ 187 Hz. Bigger = higher. |
| **Morph (timbre)** | SPI `0x15`, low byte `[7:0]` | `0x00` sine → `0xFF` pulse. The headline knob. |
| **Live weight patch** | SPI `0x40`–`0x4F` (16 words) | Overwrites the *first 16 of 129* weight words at runtime — see [§4 Method B](#method-b--live-spi-patching-runtime-glitch-knob). |

**Morph landmarks** (the byte you write to `0x15`):

| `morph` byte | Trained shape |
|---:|---|
| `0x00` | sine (pure, round) |
| `~0x55` | sawtooth (buzzy) |
| `~0xAA` | square (hollow) |
| `0xFF` | 25% pulse (reedy, nasal) |

Everything between those is a learned blend — that's the point.

**SPI frame format** (same as every other engine): each frame is
`{ addr[7:0], data[15:0] }`, MSB-first, Mode 0. So "set morph to square" is one
24-bit frame: `0x15` then `0x00AA`.

**Pitch quick-picks** (bass register; full table in
[SOUND_RECIPES.md](SOUND_RECIPES.md#appendix--pitch--control-value-tables)):

| Note | pitch bus |
|---|---:|
| C2 (~65 Hz) | 357 |
| G2 (~98 Hz) | 535 |
| C3 (~131 Hz) | 714 |
| E3 (~165 Hz) | 900 |
| F3 (~175 Hz) | 954 |

---

## 3. Playing it — the morph *is* the instrument

The engine makes a static tone if you leave `morph` parked. It comes alive when
something **moves the morph over time**. The chip makes the timbre; a
microcontroller (or an LFO, or an envelope) is the performer.

### 3.1 The "breathing bass" (start here)
- `voice_sel = 7`, pitch bus = **357** (low C, ~65 Hz).
- Have the controller ramp `0x15` from `0x00` → `0xFF` → `0x00` over ~2 seconds.
- You hear the bass start pure and round, grow buzzy and aggressive, then soften
  — a slow timbral "wah" with no filter anywhere in the chip. This is the demo
  that sells the engine.

### 3.2 Morph as an envelope (pluck-like motion)
Map `morph` to a fast **decay** instead of an LFO: jump it to `0xC0` on note-on,
then fall to `0x10` over ~150 ms. The note "snaps" bright and settles dark — a
synthetic pluck/zap built entirely out of timbre motion.

### 3.3 Morph LFO at audio rate (growl / FM-ish grit)
Update `0x15` *fast* — every few audio frames. As the morph modulation approaches
audio rate it stops sounding like a sweep and starts adding sidebands: gnarly,
metallic, talking-bass growl. The controller's update rate becomes a second pitch.

### 3.4 Static "rich sine" drone
Park `morph` around `0x30`–`0x50` and just hold a low note. Because four
harmonics are baked into the features, even the "almost sine" settings are
fuller and more alive than a plain sine — a warm sub pad.

### 3.5 Stack it (one voice at a time, fast switching)
The chip plays one voice at a time, but the mux switches in a single audio frame
(~0.1 ms, inaudible). Alternate `voice_sel` between **7 (neural bass)** on
down-beats and **4 (Karplus pluck)** or **3 (SID lead)** on off-beats and you get
a layered, full arrangement out of a mono engine. See
[SOUND_RECIPES Part 4](SOUND_RECIPES.md#part-4--rhythms-how-to-get-a-beat-out-of-a-one-voice-chip).

---

## 4. Making your own weights

This is where the engine stops being a fixed instrument and becomes a **sound-
design platform**. There are three routes, from "proper ML" to "type hex and
see what screams." All three are safe: nothing you do to the weights can break
the rest of the chip — a bad network just sounds bad.

### Method A — Retrain the network (full control, build-time)

The intended path. You change *what waveforms the morph knob sweeps through* and
let gradient descent find the weights.

1. **Edit the targets** in [`models/neural_train.py`](../models/neural_train.py).
   The waveshape functions `w_sine`, `w_saw`, `w_square`, `w_pulse` and the
   `target_wave(t, m)` blender define the continuum. Swap in anything you can
   express as `f(phase) → [-1, 1]`:
   - **Vowel/formant shapes** for a talking bass.
   - **Organ drawbar mixes** (sums of harmonics) for a Hammond-ish morph.
   - **Single-cycle samples** you captured — drop the array in as a target.
   - A morph that sweeps through *five* shapes instead of four — just add to the
     `segs` list in `target_wave`.
2. **Train + emit:**
   ```bash
   python3 models/neural_train.py
   ```
   This (re)writes **both** `models/neural_weights.hex` *and*
   `src/neural_weights_init.svh` (the baked RTL defaults) — identical values.
   The RNG is seeded, so runs are reproducible.
3. **Regenerate the golden oracle:**
   ```bash
   python3 models/neural_ref.py        # writes models/neural_golden.hex
   ```
4. **Prove the silicon still matches** (no PDK needed — pure Icarus):
   ```bash
   bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/nn.vvp \
       src/neural_osc.sv tb/tb_neural_osc.sv && vvp /tmp/nn.vvp'
   # expect: ==== NEURAL OK: every sample matched golden ====
   ```
5. **Listen** before you commit to silicon:
   ```bash
   python3 models/render_audio.py      # previews/neural.wav uses your new weights
   ```
6. **Bake into the chip:** re-harden (RTL→GDSII). The new weights become the
   power-on defaults of the on-die memory.

> **Keep the shape, change the lesson.** You can freely change the *targets*,
> training data, epochs, learning rate, and seed. If you change the **topology**
> (the `5→8→8→1` sizes) or the **input features**, you must change all three of
> `neural_train.py`, `neural_ref.py`, and the parameters in `neural_osc.sv`
> together, then re-verify — the bit-exact chain only holds if they agree. For
> "new sounds," you almost never need to touch the topology; just retrain.

### Method B — Live SPI patching (runtime "glitch knob")

You can overwrite weights **on a running chip**, no rebuild, by writing SPI
config words **`0x40`–`0x4F`** (`0x40` → weight 0, `0x41` → weight 1, …).

**Be clear about the scope** (this is a feature, not a full retrain): the live
window is **16 words**, and they map to weight indices **0–15** — the *first 16
of the 129 weight words*, which is part of **Layer 1**. The 256-word sine table
and weights 16–128 stay at their baked defaults and are **not** live-writable.

So Method B does **not** reprogram the network — it **perturbs the front of it**.
That turns out to be wonderful for performance:

- **Weight wobble:** stream slowly-changing values into `0x40`–`0x4F` and the
  timbre warps, detunes, and destabilizes in ways the `morph` knob can't reach —
  a "neural feedback" knob.
- **Random patches:** fire a few random 16-bit values into the window for an
  instant, unrepeatable timbre. Re-randomize per note for an ever-mutating bass.
- **Reset-to-clean:** there's no "reset weights" command — just re-write the
  original 16 values (or pulse the chip's reset, which reloads all baked
  defaults) to get back to your trained sound.

If you need the *whole* network reprogrammable at runtime, that's a future
hardware change (widen the SPI weight window in the spine); today, full custom
networks go in via **Method A**.

### Method C — Hand-craft weights (no training at all)

The weights are just signed integers in a text file. You can bypass ML entirely
and **author them by hand or by script**, then run the same verify + listen flow
as Method A (steps 3–5). Because it's bit-exact, you hear *exactly* what you typed.

Things that produce striking results:
- **Kill harmonics:** zero the Layer-1 weights that read harmonics 2–4 and the
  network collapses toward a near-sine — a clean, minimal sub.
- **Overdrive a path:** crank one weight far up so the output slams the signed-16
  clamp and you get hard digital clipping — instant fuzz bass.
- **Sparsify:** zero most weights and leave a few — strange, hollow, partial
  spectra you'd never train toward.

And the most fun hack of all:

- **Swap the sine LUT (a wavetable hack).** The first **256 words** of
  `neural_weights.hex` aren't weights at all — they're the **sine table** the
  network draws its harmonics from. Replace them with a *different* single-cycle
  waveform (triangle, a sampled waveform, even noise) and you change the **raw
  material** the MLP shapes. The network keeps doing its morph, but now over your
  table. It effectively becomes a neural wavetable oscillator. (Regenerate the
  golden + re-run the TB afterward; the LUT is part of the same bit-exact image.)

> ⚠️ The LUT is in the **baked** image (`0x40`–`0x4F` live-load only reaches
> weights, not the LUT), so a LUT swap is a **build-time** change — rebuild and
> re-harden to put it on silicon.

---

## 5. Playful project ideas

- **CV-controlled morph.** Wire an external CV → ADC → `0x15` on the
  microcontroller and you have a classic 1-knob "timbre" / "filter" voltage on a
  Eurorack panel, except it's a neural network behind it.
- **Two LFOs, two axes.** LFO the pitch bus (vibrato) *and* the morph (timbre
  motion) at different rates for a constantly-evolving, never-static drone.
- **Patch bank.** Train several weight sets (Method A) for different "characters"
  (warm/aggressive/vocal), keep their `.hex` files, and pick one per build — or
  per chip. A morph engine *and* a preset system.
- **Generative bass.** Let the controller random-walk both `morph` and the pitch
  bus on a slow clock for a self-playing, ambient, neural sub-bass piece.
- **Glitch performance.** Map a knob to stream values into the live weight window
  (`0x40`–`0x4F`) for on-stage timbre destruction that always recovers on reset.
- **"Wrong on purpose" training.** Train Method A on deliberately weird or
  inconsistent targets (mismatched morph segments, clipped shapes, noise). The
  network's attempt to fit the impossible produces sounds you can't design
  directly — happy accidents are a legitimate technique here.

---

## 6. Reference card

**Control map**

| Function | Pin / SPI | Value |
|---|---|---|
| Engine select | `voice_sel` | `7` |
| Pitch | `ks_period[9:0]` | `freq ≈ bus × 0.183 Hz`, ≤ ~187 Hz |
| Morph | SPI `0x15[7:0]` | `0x00` sine … `0xFF` pulse |
| Live weight patch | SPI `0x40`–`0x4F` | first 16 of 129 weight words |

**Network at a glance:** 5→8→8→1 MLP · ReLU hidden · linear out · Q1.14 ·
1 time-shared MAC (~139 clk/sample) · 256-word sine LUT + 129 weight/bias words.

**Toolchain files**

| File | Role |
|---|---|
| [`models/neural_train.py`](../models/neural_train.py) | Offline trainer + quantizer. Edit targets here. Writes the `.hex` **and** the baked `.svh`. |
| [`models/neural_ref.py`](../models/neural_ref.py) | Bit-exact integer oracle. Writes `neural_golden.hex`. |
| [`models/neural_weights.hex`](../models/neural_weights.hex) | The memory image: 256 LUT words + 129 weights. |
| `src/neural_weights_init.svh` | Generated baked RTL defaults (identical to the `.hex`). |
| [`src/neural_osc.sv`](../src/neural_osc.sv) | The silicon datapath. |
| [`tb/tb_neural_osc.sv`](../tb/tb_neural_osc.sv) | Self-checking TB (`NEURAL OK`). |
| [`models/render_audio.py`](../models/render_audio.py) | Renders `previews/neural.wav` so you can hear it. |

**The build → hear → prove loop, in one block**

```bash
python3 models/neural_train.py        # 1. write new weights (.hex + baked .svh)
python3 models/neural_ref.py          # 2. regenerate the golden oracle
python3 models/render_audio.py        # 3. listen: previews/neural.wav
bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/nn.vvp \
    src/neural_osc.sv tb/tb_neural_osc.sv && vvp /tmp/nn.vvp'   # 4. prove bit-exact
# Then re-harden to bake the new weights into silicon.
```

> All frequencies assume the recommended **12.288 MHz clock → 12 kHz sample
> rate**. Run a different clock and every pitch scales by the same ratio.
