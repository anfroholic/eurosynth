# Synth chip — project notes / handoff brief

A "kitchen-sink" eurorack synthesizer voice on the **GF180MCU** PDK, built on the
[wafer.space gf180mcu project template](https://github.com/wafer-space/gf180mcu-project-template)
and the LibreLane digital RTL-to-GDSII flow.

This file is the source of truth for *why the design looks the way it does*. If you
are a fresh session picking this up, read this first, then the comments in the RTL.

---

## What we're building

A fully **digital** synth voice that outputs a serial audio stream to a cheap
external DAC on the module PCB. The "analog" side of eurorack life (±12V rails,
1V/oct conditioning, audio buffering, the DAC itself) lives on the PCB *around*
the chip — the chip is the brain, not the signal chain.

The design is deliberately a kitchen sink: many sound engines on one die. The bet
is that this is safe **if and only if** the engines are isolated. See architecture.

---

## Architecture: spine + isolated engines

```
  [engine 0..N]  ->  [voice mux]  ->  [serializer]  ->  I2S out -> external DAC
   (isolated)        (one wins)       (timing master)
        ^                                  |
        +-------- sample_tick -------------+      [bypass test ramp] --+
                                                                       |
                                                  (independent path) --+--> serializer
```

The **spine** (`synth_spine.sv`) is the bulletproof shared backbone:

- It owns timing. The serializer is the **clock master**: it emits exactly one
  `sample_tick` pulse per audio frame. Every engine advances on that tick.
- A **voice-select mux** lets exactly ONE source reach the output at a time.
  Engines never interfere → a bug in one engine stays in that one engine. This is
  the whole reason a kitchen sink is allowed to be greedy: blast radius is bounded.
- A **bypass test ramp** is an independent known-good sawtooth that reaches the
  serializer without touching any engine. It is **bring-up insurance**: on first
  power-up you assert `bypass_en` and confirm the chip is alive and talking to the
  DAC *before* trusting any real DSP.

Design principle: keep the spine dead-simple and verify it to death; hang every
fancy thing off it as an isolated leaf. If an engine won't fit area or won't pass
verification in time, just don't give it a `voice_sel` slot — the rest still ships.

---

## The engine contract (how to add a voice)

Every engine is a module that:

1. Advances its state **only** on `sample_tick` (a 1-clk pulse, audio rate).
2. Presents a 16-bit signed `sample` that is **stable between ticks**.
3. Gets wired into the spine as one more `voice_sel` case.

```systemverilog
module my_engine (
    input  wire               clk,
    input  wire               rst_n,        // active low
    input  wire               sample_tick,  // advance state here
    // ... your control inputs (CV, pitch, params) ...
    output wire signed [15:0] sample        // current output, held between ticks
);
```

To enable it: instantiate it in `synth_spine.sv` and add a line to the mux `case`
(e.g. `3'd4: sel_sample = my_engine_out;`). Nothing else can break.

---

## Timing / sample rate

- Serializer divides `clk` to a bit-clock, 32 bits per frame (16 L + 16 R, mono
  duplicated to both channels), MSB first.
- **fs = clk / (64 * BCLK_DIV)**. At clk = 50 MHz, `BCLK_DIV = 16` → ~48.8 kHz.
  Tune `BCLK_DIV` (and/or the input clock) to hit an exact rate later.
- Output is **I2S-style** 3-wire: `i2s_bclk`, `i2s_ws` (LRCK), `i2s_sd`.

---

## Pin map (1x1 slot: 12 input pads, 40 bidir pads, 2 analog pads)

Inputs (`input_in[]`):
| bit  | function                                            |
|------|-----------------------------------------------------|
| 2:0  | `voice_sel` (0=bypass ramp, 1=saw, 2=square, 3=silence) |
| 3    | `bypass_en` (force the bring-up test ramp)          |
| 11:4 | reserved (gates / CV / SPI config — not yet wired)  |

Outputs (`bidir_out[]`, all pads configured as outputs):
| bit   | function                                            |
|-------|-----------------------------------------------------|
| 0     | `i2s_sd`  — serial audio data to DAC                |
| 1     | `i2s_bclk` — bit clock                              |
| 2     | `i2s_ws` — word select / LRCK                       |
| 3     | `heartbeat` — slow toggle, "chip is alive" LED      |
| 4     | `sample_tick` — audio-rate frame strobe (scope tap) |
| 31:16 | `sample_dbg` — parallel sample mirror (bring-up)    |

Analog pads (2): currently **unused**. Reserved for a future on-die entropy/TRNG
output or an analog interface experiment.

---

## Files

| file                | role                                                       |
|---------------------|------------------------------------------------------------|
| `src/synth_spine.sv`| The reusable spine: tick gen, mux, bypass ramp, serializer, 2 placeholder oscillators. |
| `src/chip_core.sv`  | Drop-in replacement for the template's example core. Wires the spine to the pad interface. |
| `cocotb/..._tb.py`  | Template's cocotb harness — drive `input_PAD` bits to exercise the design. |
| `tb_synth_spine.sv` | Standalone iverilog self-checking testbench (decodes I2S back, compares). |

### Integrating into the template
1. Put `synth_spine.sv` in `src/`.
2. Replace `src/chip_core.sv` with this one.
3. Add `synth_spine.sv` to `VERILOG_FILES` in `librelane/config.yaml`.
4. The example's SRAM macros were **removed** (nothing needs memory yet). They
   come back when an engine needs weight storage or a wavetable — re-add the
   `gf180mcu_xxx_ip_sram__sram512x8m8wm1` instances then.

---

## Status — what's proven

- `synth_spine` simulates under Icarus Verilog. The testbench decodes the serial
  output exactly as a DAC would and **every frame's decoded sample matches the
  intended sample** across all four mux settings (0 mismatches).
- `chip_core` elaborates against the real 1x1 pad counts, drives all bidir pads as
  outputs, and the audio bit-clock toggles correctly.

Run it:
```bash
# standalone logic proof (fast, no PDK needed)
iverilog -g2012 -o spine.vvp src/synth_spine.sv tb_synth_spine.sv && vvp spine.vvp

# in the real template harness
nix-shell
make sim          # RTL simulation via cocotb
make librelane    # RTL -> GDSII (first run compiles OpenROAD locally; slow)
```

---

## Known caveats / TODO before tapeout

- **I2S timing**: the serializer is "I2S-style" and round-trips against our own
  receiver, but validate against the exact **Philips I2S** convention (data is
  delayed one BCLK after the WS edge) and against the specific DAC chip chosen.
- **SPI config port**: not built yet. v0 control is raw pins. Needed for loading
  neural weights and richer mode/param control. Reserve `input_in[11:4]`.
- **Voice-switch latency**: switching `voice_sel` takes effect on the next frame
  (one-frame serializer pipeline latency). Expected, not a bug.
- **Placeholder oscillators** (saw/square) are stand-ins to exercise the mux; they
  get replaced/augmented by real engines.
- **Area budget**: don't pack the 1x1 slot near full — leave headroom for timing
  closure and routing. Consider a larger slot if the engine list grows.
- **Analog/TRNG**: any on-die analog (entropy source, etc.) is a categorically
  higher-risk, non-LibreLane effort. Keep it optional and non-fatal.

---

## Engine roadmap

Build order is **your call** — the contract makes each one independent. Candidates,
roughly easiest-to-sing first:

1. **Karplus-Strong** plucked string — delay line + filter. Trivial digitally,
   gorgeous output. Great first engine to validate the contract end to end.
2. **Chaos engine** — Lorenz / logistic-map oscillators + a cellular-automaton
   sequencer. No training, alien textures, devoted modular following.
3. **SID homage** — 3 voices, classic waveforms, ring mod / sync. Nostalgia bait,
   well-understood target, low risk.
4. **Bytebeat box** — tiny configurable arithmetic expressions → music. Cult
   classic, tiny area (could even fit a half slot).
5. **Neural oscillator** (the headliner) — a small fixed-point MLP that *is* the
   waveform generator; morph timbre via control inputs; SPI-loadable weights.
   Most involved: needs MAC time-sharing to hit audio rate + offline weight
   training & quantization. Highest "talk about it" payoff.

**Recommendation:** do one *simple* engine (Karplus-Strong or chaos) first to
shake out the contract and the cocotb flow, then tackle the neural core with
confidence. **Not yet decided which is engine #1 — pick this up here.**
