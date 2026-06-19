# Sound recipes — a patch cookbook for the EuroSynth chip

> **For the non-musician.** This file is a tour of *what this chip can actually
> make noise like*, written for someone who has never touched a synth. Every
> recipe is a concrete set of control values you (or a microcontroller) feed the
> chip's pins/SPI port. The numbers are real — they're computed from the RTL in
> [`src/synth_spine.sv`](../src/synth_spine.sv) and the engines, not made up.
>
> Companion docs: [SHOWCASE.md](SHOWCASE.md) (what the chip is) and
> [HARDWARE_GUIDE.md](HARDWARE_GUIDE.md) (how to wire it + the Arduino controller
> that plays these recipes).

---

## First, the three things that shape *every* sound

**1. It's lo-fi on purpose.** The sample rate is **12 kHz** (at the recommended
12.288 MHz clock). That means the highest pitch it can represent is ~6 kHz —
roughly the brightness of an old telephone, a vintage sampler, or a 1980s game
console. Everything will sound a little "crunchy / retro," and that's the
aesthetic, not a defect. 16-bit depth keeps it clean, not hissy.

**2. It plays ONE voice at a time.** There's no mixer. A 3-bit `voice_sel`
chooses exactly one of eight sound sources to send to the speaker. So chords and
layering come from *within* an engine (the SID engine has 3 internal voices; the
neural one stacks harmonics), or from switching engines very fast. Think of it
as a single, very versatile mouth — not a choir.

**3. The chip is the instrument; a microcontroller is the *player*.** The chip
makes the timbre. *Rhythm and melody* come from something outside (an Arduino,
say) changing the control pins over time — strobing a "pluck," nudging the pitch,
flipping `voice_sel`. **Two exceptions:** the **bytebeat** and **chaos** engines
generate their own evolving patterns with no help — you switch them on and they
*play themselves*.

### The eight sources (`voice_sel`)

| `voice_sel` | Source | What it's for |
|---:|---|---|
| 0 | Bypass test ramp | A clean ~187 Hz buzz. "Is the chip alive?" beep. |
| 1 | Saw oscillator | Fixed ~399 Hz bright tone (test/drone). |
| 2 | Square oscillator | Fixed ~239 Hz hollow tone (test/drone). |
| 3 | **SID** (3 voices) | Chiptune leads, chords, basses, sirens, robots. |
| 4 | **Karplus–Strong** | Plucked strings: guitar, harp, koto, plus drums. |
| 5 | **Chaos** | Noise, static, growls, alien sweeps, drones. |
| 6 | **Bytebeat** | Self-playing algorithmic music loops. |
| 7 | **Neural** | A morphing oscillator: bass that melts between shapes. |

### The two control "knobs" you'll use most

- **Pitch bus** (`ks_period`, 10 bits, pins `bidir[15:6]`). One number, but each
  engine reads it differently — see the pitch tables below. **The same number is
  a different note on KS vs. SID vs. neural.**
- **Gate / pluck** (`ks_pluck`, 1 pin, `bidir[5]`). A momentary "strike." For the
  string engine it's the pluck. Strobe it rhythmically and you have a beat.
- **Deep params** go over the **SPI port** (3 pins) into a register file — that's
  how you pick a bytebeat formula, a chaos map, SID waveforms, neural morph, etc.

---

## Part 1 — Sustained tones (drones, pads, leads)

### 1.1 The "hello world" beep
The simplest sound the chip makes. Used on first power-up to prove it's talking
to the speaker before you trust any DSP.

- **Set:** `bypass_en = 1` (or `voice_sel = 0`). Nothing else.
- **Result:** a steady **~187 Hz buzzy sawtooth** — a low, slightly rude beep.
  If you hear it, the whole audio path works.

### 1.2 Two free "test tones"
`voice_sel = 1` → a **~399 Hz sawtooth** (bright, buzzy, like a kazoo).
`voice_sel = 2` → a **~239 Hz square** (hollow, woody, like a recorder/8-bit
flute). Both are fixed pitch — good as a tuning reference or a held drone.

### 1.3 A fat chiptune lead (SID)
The SID engine is three oscillators in one. It's pre-wired into a "thick" patch:
voice 1 is detuned slightly sharp (a built-in chorus shimmer) and voice 2 plays
**one octave below** — so a single note already sounds full.

- **Set:** `voice_sel = 3`, pitch bus = the note (see SID table below).
- **Pick the waveform** over SPI — write config word `0x12` (voice 0), `0x13`
  (voice 1), `0x14` (voice 2). Low 3 bits = waveform: **0 = sawtooth** (buzzy,
  classic lead), **1 = triangle** (soft, flute-like), **2 = pulse** (hollow,
  reedy — set the pulse width in bits `[15:8]`), **3 = noise** (hiss/percussion).
- **Try this — a bright lead on A4 (440 Hz):** pitch bus = **38**; set all three
  voices to sawtooth (`0x12 = 0x13 = 0x14 = 0x0000`). You get a buzzy, detuned,
  octave-stacked "supersaw"-ish lead.
- **Try this — a soft flute:** same note, set waveform = triangle
  (`0x12 = 0x14 = 0x0001`). Mellow and round.

### 1.4 A morphing bass that "opens up" (neural)
Voice 7 is the headliner: a tiny neural network *is* the oscillator. One control,
`morph` (SPI `0x15`, low byte `0x00`→`0xFF`), sweeps the timbre across a
continuum: **sine → sawtooth → square → pulse.** Sweep it slowly and the tone
sounds like a filter opening — a synth "wah" / "vowel" morph.

- **Set:** `voice_sel = 7`, pitch bus = note (neural table below — it's a **bass**
  engine, tops out near 187 Hz).
- **Try this — a wobbling bass:** pitch bus = **357** (≈ 65 Hz, a low C). Then
  have the controller ramp `0x15` from `0x00` to `0xFF` and back over ~2 seconds.
  The bass starts pure and round, grows buzzy and aggressive, then softens again
  — a slow timbral "breathing."
- **Drone use:** hold `morph` fixed at, say, `0x60` for a static, slightly-buzzy
  sub-bass pad. With harmonics baked in it's richer than a plain sine.

### 1.5 Plucked-string "pad" (Karplus–Strong, re-struck)
The string engine decays (it's a pluck, not a held note), but if you **re-pluck
it gently every ~1 second** at the same pitch it reads as a slow, breathing,
harp-like pad. See Part 2 for the engine itself.

---

## Part 2 — Plucked & percussive (Karplus–Strong, voice 4)

This is the chip's most "real-instrument" sound. A pluck fills a short digital
"string" with a burst of noise; it then rings and mellows exactly like a real
plucked string — bright attack, warm tail. **Pitch = `12000 / N`**, where `N` is
the pitch-bus value (valid 2–255). It rings for roughly a **second or two** at
mid pitches and **longer for lower notes** (see [karplus_strong.md](karplus_strong.md)).

To play a note: set the pitch bus to `N`, then pulse `ks_pluck` (`bidir[5]`) high
for one clock. Re-pluck to repeat.

### 2.1 A plucked melody / harp
- **Set:** `voice_sel = 4`. For each note: set pitch bus = `N` from the KS table,
  then strobe the pluck.
- **Try this — a little ascending run:** pluck `N=46` (C4), wait ~250 ms, pluck
  `N=36` (E4), wait, pluck `N=31` (G4), wait, pluck `N=23` (C5). That's a C-major
  arpeggio — sounds like a music box / harp.

### 2.2 A guitar (open strings)
Feed the six open-string pitches and strum them (pluck in quick succession,
~30–50 ms apart):

| String | Pitch | `N` |
|---|---|---:|
| Low E (82 Hz) | E2 | 146 |
| A (110 Hz) | A2 | 109 |
| D (147 Hz) | D3 | 82 |
| G (196 Hz) | G3 | 61 |
| B (247 Hz) | B3 | 49 |
| High E (330 Hz) | E4 | 36 |

Plucking all six fast = a strummed chord. Plucking one at a time = fingerpicking.

### 2.3 Drums from a "string" (the fun trick)
Make the string *very short* and it stops sounding pitched and starts sounding
percussive — the noise burst dominates:

- **Snare / clap:** `N` ≈ **6–12**, single pluck. Short, noisy, snappy.
- **Hi-hat / click:** `N` ≈ **2–4**, single pluck. A tiny bright "tick."
- **Tom / "thunk":** `N` ≈ **30–60**, single pluck. A short pitched drum.
- **Kick-ish "boom":** `N` ≈ **180–255** (lowest notes), single pluck. A deep,
  fast-thumping low pluck. (It's not a true sine kick, but it reads as a low drum.)

Now you can sequence a **drum kit out of one engine** just by changing `N`
between plucks. See Part 4.

---

## Part 3 — Music that plays itself (bytebeat & chaos)

These two engines don't need a sequencer. Turn them on and they evolve.

### 3.1 Bytebeat (voice 6) — algorithmic loops
"Bytebeat" is music made by running a counter `t` through a one-line formula and
listening to the low 8 bits. The chip has four classic formulas, picked by SPI
config `0x10` (low 4 bits = formula, bits `[11:4]` = speed `t_inc`). Speed `t_inc`
acts like a tempo/pitch knob (1 = normal, higher = faster & higher).

| Formula | Expression | What it sounds like |
|---:|---|---|
| 0 | `t*(t>>5 \| t>>8)` | The famous one. An evolving, arpeggiated melodic riff with a driving pulse — sounds like a tiny chiptune song that never quite repeats. **Start here.** |
| 1 | formula 0, octave-shifted by time | Formula 0 but with a slow descending "staircase" every ~5 seconds — like a melody that periodically drops in register. |
| 2 | `t*(((t>>12)\|(t>>8))&(63&(t>>4)))` | Sparser, glitchier, more melodic-and-broken — clicky arpeggios with gaps. |
| 3 | `t&(t>>8)` | The "Sierpinski" buzz: a low, gnarly, rhythmic drone with a triangular pulsing pattern. Very robotic. |

- **Try this — instant chiptune:** `voice_sel = 6`, write `0x10 = 0x0010`
  (formula 0, `t_inc = 1`). Walk away — it plays a melody.
- **Try this — double-time, brighter:** `0x10 = 0x0020` (formula 0, `t_inc = 2`).
- **Try this — robot drone:** `0x10 = 0x0013` (formula 3).

### 3.2 Chaos (voice 5) — noise, growls, alien sweeps
Three "chaotic math" generators, picked by SPI config `0x11` (bits `[1:0]` =
map, `[7:2]` = rate, `[15:8]` = `r_seed`).

**Map 0 — logistic map.** A number bounces around by `x ← r·x·(1−x)`. The single
parameter `r_seed` (`r` = 3.0 + `r_seed`/256) decides the character:

| `r_seed` | `r` ≈ | Sound |
|---:|---|---|
| 0–110 | 3.0–3.43 | A **steady buzzy tone** (the bounce settles into a repeating pattern). |
| 110–150 | 3.43–3.59 | A **warbling, gargling** tone (it splits between values — "period doubling"). |
| 150–255 | 3.59–4.0 | **Full noise / static / harsh hiss** (true chaos). Great for cymbals, wind, explosions. |

- **Try this — white-noise hiss:** `voice_sel = 5`, `0x11 = 0xC800` (map 0,
  `r_seed = 0xC8 = 200`). A harsh static — useful as a noise source for sweeps.
- **Try this — a growl:** `0x11 = 0x7800` (`r_seed ≈ 120`) — sits in the
  warbling zone, sounds like a low, unstable growl.

**Map 1 — CA-perturbed logistic.** Same chaos, but a cellular automaton slowly
mutates `r` over time, so the texture *drifts and evolves*. `rate` (`[7:2]`) sets
how slowly: `rate = 0` mutates fast (restless), high `rate` evolves slowly (a
texture that morphs over many seconds — good for "alien radio" ambience).

- **Try this — evolving static:** `0x11 = 0x9C2D` → map 1, `rate ≈ 11`,
  `r_seed ≈ 0x9C`. A hissing texture that keeps shifting.

**Map 2 — Lorenz attractor.** A smooth, swooping 3-D system; you hear its
X-coordinate. Unlike the harsh logistic noise, this is **low, smooth, and
organic** — a deep wandering rumble that loops in a lopsided figure-eight. Ideal
for sci-fi / underwater / "thinking machine" drones.

- **Try this — alien drone:** `0x11 = 0x0002` (map 2). Let it wander. Swooping,
  unpredictable, but never harsh.

---

## Part 4 — Rhythms (how to get a beat out of a one-voice chip)

Rhythm comes from **a controller changing pins on a clock.** Here are concrete
grooves. Times assume **120 BPM** (1 beat = 500 ms, ♪ eighth = 250 ms,
♬ sixteenth = 125 ms) — the controller just sets the pin values at those moments.

### 4.1 A plucked bassline (KS)
`voice_sel = 4`. On each eighth note, set the pitch and pluck:

```
beat:   1   &   2   &   3   &   4   &
note:  A2  A2  C3  E3  A2  A2  G2  E3
N:    109 109  92  73 109 109 122  73
pluck:  x   x   x   x   x   x   x   x
```
A walking, rubbery plucked bass. Skip a pluck to leave a rest; the string keeps
ringing through it.

### 4.2 A drum pattern from KS (one engine, whole kit)
Use the "drums from a string" trick (Part 2.3). Each hit is `set N → pluck`:

```
step:  1  2  3  4  5  6  7  8   (sixteenths)
kick:  x  .  .  .  x  .  .  .    N=200
snare: .  .  x  .  .  .  x  .    N=8
hat:   x  x  x  x  x  x  x  x    N=3
```
The controller just picks which `N` to load before each pluck. A four-on-the-
floor-ish beat from a *single* plucked-string engine.

### 4.3 Self-playing groove (bytebeat) + live drums (KS)
Let bytebeat run the music bed, and *punch in* KS drums by briefly switching the
mux:
- Default `voice_sel = 6` (bytebeat formula 0 plays the loop).
- On each kick beat, the controller flips `voice_sel = 4`, plucks a low `N=200`,
  then flips back to `6`. The switch takes effect on the next audio frame (~0.1 ms
  — inaudible), so the drum "interrupts" the loop for its duration. A crude but
  effective drum-machine-over-a-track.

### 4.4 Built-in rhythm, zero effort (bytebeat formula 3)
`voice_sel = 6`, `0x10 = 0x0013`. The `t&(t>>8)` formula has a *built-in*
pulsing rhythm — the binary pattern of the counter literally is the beat. No
controller activity needed at all.

### 4.5 Tremolo / strum / "buzz roll" (rapid re-pluck)
Re-plucking KS *fast* (every 30–60 ms) at one pitch gives a mandolin-tremolo or
a buzzy sustained texture. Speed it up further and the plucks blur into a rough
sustained tone — a "machine-gun" string.

---

## Part 5 — Sound effects & textures

| Effect | How |
|---|---|
| **Laser / "pew"** | `voice_sel = 3` (SID, pulse wave). Controller sweeps the pitch bus from high to low over ~120 ms. A fast downward chirp. |
| **Riser / build-up** | Any pitched voice; controller ramps the pitch bus *upward* over 1–4 s. With chaos map 0 and a rising `r_seed`, it rises *and* dissolves into noise. |
| **Siren** | SID; controller oscillates the pitch bus up/down slowly (e.g. a triangle sweep over 1 s, repeated). |
| **Robot voice / ring-mod bell** | SID with **ring-mod** on (set bit 3 of a voice's config word, e.g. `0x12 = 0x0009` = triangle + ring). Two voices multiply into clangy, inharmonic, metallic/vocal tones. |
| **Hard-sync "tearing" lead** | SID with **hard-sync** on (bit 4, e.g. `0x12 = 0x0011`). One voice resets another → that aggressive, buzzy, ripping sync-lead sound. |
| **Explosion / crash** | Chaos map 0, `r_seed` high (`0x11 = 0xF000`) for a burst of noise; controller fades it by switching to silence. Or a single KS pluck at `N=4`. |
| **Wind / ocean** | Chaos map 1 (CA), slow `rate` — evolving hiss that swells and recedes. |
| **UFO / underwater** | Chaos map 2 (Lorenz) — smooth swooping drone. |
| **Dial-up modem / glitch** | Bytebeat formula 2 at high `t_inc` (`0x10 = 0x0042`) — clicky, broken, data-like chatter. |
| **Cymbal / hi-hat** | KS at `N=2–3`, single pluck — bright metallic tick. |

---

## Part 6 — Three "demo track" sketches

These are controller scripts — sequences of pin/SPI changes over time — that
string the recipes into something song-like.

### 6.1 "Chiptune jam" (~10 s)
1. `voice_sel = 6`, `0x10 = 0x0010` → bytebeat melody starts (the bed).
2. After 4 s, punch in a KS bassline (Part 4.1) by quickly alternating
   `voice_sel` 6↔4 on the beat.
3. At 8 s, switch `0x10 = 0x0020` (double-time) for an "outro."

### 6.2 "Ambient sci-fi" (~30 s)
1. `voice_sel = 5`, `0x11 = 0x0002` (Lorenz) → a slow alien drone.
2. Layer feeling by occasionally switching to `voice_sel = 7` (neural) on a low
   note and slowly sweeping `morph` `0x00→0xFF` → a breathing pad rises over the
   drone.
3. Sprinkle KS harp plucks (`voice_sel = 4`, high `N` like 23/31/46) at random,
   long intervals → distant bells.

### 6.3 "Plucked ballad" (the most musical)
1. `voice_sel = 4` throughout.
2. Left-hand bass: pluck low notes (`N` 92–146) on beats 1 & 3.
3. Right-hand melody: pluck higher notes (`N` 23–46) on the off-beats.
4. Let lower notes ring under the melody (their longer decay sustains the
   harmony). This is the closest thing to a "real instrument performance" the
   chip does.

---

## Appendix — pitch → control-value tables

**Remember:** the *same* pitch-bus number means a different pitch on each engine,
because each interprets it differently:
- **KS (voice 4):** the number is a delay length `N`; pitch = `12000 / N`. **Bigger
  number = lower note.** Valid 2–255.
- **SID (voice 3):** the number is scaled ×64 into a phase rate; pitch ≈
  `number × 11.72 Hz`. **Bigger number = higher note.** Coarse below ~C3.
- **Neural (voice 7):** the number is the phase rate directly; pitch ≈
  `number × 0.183 Hz`. **Bigger = higher,** but caps at ~187 Hz (it's a bass).

| Note (freq) | KS `N` | SID bus | Neural bus |
|---|---:|---:|---:|
| C2 (65 Hz) | 183 | 6 | 357 |
| G2 (98 Hz) | 122 | 8 | 535 |
| A2 (110 Hz) | 109 | 9 | 601 |
| C3 (131 Hz) | 92 | 11 | 714 |
| E3 (165 Hz) | 73 | 14 | 900 |
| F3 (175 Hz) | 69 | 15 | 954 |
| G3 (196 Hz) | 61 | 17 | *(>187 Hz: out of range)* |
| A3 (220 Hz) | 55 | 19 | — |
| C4 (262 Hz) | 46 | 22 | — |
| E4 (330 Hz) | 36 | 28 | — |
| G4 (392 Hz) | 31 | 33 | — |
| A4 (440 Hz) | 27 | 38 | — |
| C5 (523 Hz) | 23 | 45 | — |
| A5 (880 Hz) | 14 | 75 | — |
| (drum/click) | 2–6 | — | — |

### SPI config quick-reference (write `{addr[7:0], data[15:0]}`)

| addr | engine | fields |
|---|---|---|
| `0x10` | bytebeat | `[3:0]` formula (0–3), `[11:4]` `t_inc` (speed) |
| `0x11` | chaos | `[1:0]` map (0=logistic,1=CA,2=Lorenz), `[7:2]` rate, `[15:8]` `r_seed` |
| `0x12`–`0x14` | SID v0/v1/v2 | `[2:0]` wave (0=saw,1=tri,2=pulse,3=noise), `[3]` ring-mod, `[4]` hard-sync, `[15:8]` pulse-width |
| `0x15` | neural | `[7:0]` morph (`0x00` sine → `0xFF` pulse) |
| `0x40`–`0x4F` | neural | weight load (advanced; defaults are pre-trained) |

> All frequencies assume the recommended **12.288 MHz clock → fs = 12 kHz**. Run
> the chip at a different clock and every pitch scales by the same ratio.
