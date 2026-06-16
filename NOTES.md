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

> Note: `3'd4` is now **taken** by the real Karplus-Strong engine
> (`src/ks_engine.sv`, wired in as `voice_sel = 4`). A new engine would use
> `3'd5` and up.

---

## Timing / sample rate

- Serializer divides `clk` to a bit-clock, 32 bits per frame (16 L + 16 R, mono
  duplicated to both channels), MSB first.
- **fs = clk / (64 * BCLK_DIV)**. At clk = 50 MHz, `BCLK_DIV = 16` → ~48.8 kHz.
  Tune `BCLK_DIV` (and/or the input clock) to hit an exact rate later.
- Output is **I2S-style** 3-wire: `i2s_bclk`, `i2s_ws` (LRCK), `i2s_sd`.

---

## Pin map (1x0p5 slot: 4 input pads, 46 bidir pads, 4 analog pads)

The half-slot gives us only **4 dedicated input pads**, so any control beyond
`voice_sel` / `bypass_en` (the KS pluck/period, and future CV / gates / SPI) has
to live on **bidir pads configured as inputs**. This map matches `src/chip_core.sv`.

Dedicated input pads (`input_in[]`, all 4 used):
| bit | function                                                                       |
|-----|--------------------------------------------------------------------------------|
| 2:0 | `voice_sel` (0=bypass ramp, 1=saw, 2=square, 3=silence, **4=Karplus-Strong**)  |
| 3   | `bypass_en` (force the bring-up test ramp)                                      |

Bidir pads are **per-bit direction-configurable**: a generate-loop builds a static
`bidir_oe` mask (output where `oe=1`, input where `oe=0`), and `bidir_ie = ~bidir_oe`.

Bidir bits driven as INPUTS (`oe=0`), a contiguous block `[15:5]`:
| bit  | function                                                  |
|------|-----------------------------------------------------------|
| 5    | `ks_pluck` — 1-clk strobe to (re)excite the string        |
| 15:6 | `ks_period[9:0]` — delay-line length / pitch              |

Bidir bits driven as OUTPUTS (`oe=1`):
| bit   | function                                            |
|-------|-----------------------------------------------------|
| 0     | `i2s_sd`  — serial audio data to DAC                |
| 1     | `i2s_bclk` — bit clock                              |
| 2     | `i2s_ws` — word select / LRCK                       |
| 3     | `heartbeat` — slow toggle, "chip is alive" LED      |
| 4     | `sample_tick` — audio-rate frame strobe (scope tap) |
| 31:16 | `sample_dbg` — parallel sample mirror (bring-up)    |

Analog pads (4): currently **unused / reserved**. Held for a future on-die
entropy/TRNG output or an analog interface experiment.

---

## Files

| file                          | role                                                       |
|-------------------------------|------------------------------------------------------------|
| `src/synth_spine.sv`          | The reusable spine: tick gen, mux, bypass ramp, serializer, 2 placeholder oscillators, KS instance. |
| `src/chip_core.sv`            | Drop-in replacement for the template's example core. Wires the spine to the 1x0p5 pad interface. |
| `src/ks_engine.sv`            | **NEW:** Karplus-Strong plucked-string voice (engine #1). |
| `src/chip_top.sv`             | Template top / pad ring (from the wafer.space template). |
| `src/slot_defines.svh`        | Slot pad budgets (selects 1x0p5 = 4/46/4). |
| `tb/tb_synth_spine.sv`        | Standalone iverilog self-checking spine TB (decodes I2S back, compares). |
| `tb/tb_ks_engine.sv`          | **NEW:** standalone KS golden-vector TB (compares against `ks_golden.hex`). |
| `tb/tb_chip_core_elab.sv`     | **NEW:** 1x0p5 elaboration check (direction mask, bclk live). |
| `models/ks_ref.py`            | Bit-exact integer reference model for KS. |
| `models/ks_golden.hex`        | Golden samples emitted by `ks_ref.py` (the trust anchor). |
| `docs/karplus_strong.md`      | KS engine spec (algorithm, fixed-point, test plan). |
| `docs/template_integration.md`| Template recon notes. |
| `cocotb/..._tb.py`            | Template's cocotb harness — drive `input_PAD` bits to exercise the design (needs PDK). |

The standalone iverilog testbenches now live in `tb/` (not the repo root).

### Integrating into the template — DONE
The wafer.space template tree was imported (Makefile, `librelane/`, `cocotb/`,
`ip/`, `src/chip_top.sv`, `src/slot_defines.svh`). What we kept / changed:
1. **Our `chip_core.sv` was kept** (it replaces the template's example core).
2. `synth_spine.sv` **and** `ks_engine.sv` were added to `VERILOG_FILES` in
   `librelane/config.yaml` (and to the cocotb sources).
3. The example's **SRAM macros were removed** from `macros_5v.yaml` /
   `macros_3v3.yaml` (the core is SRAM-free). They come back if an engine needs
   weight storage or a wavetable — re-add the
   `gf180mcu_xxx_ip_sram__sram512x8m8wm1` instances then. (See the KS area caveat
   below: the delay line *should* eventually be backed by such a macro.)
4. `DEFAULT_SLOT = 1x0p5`.

---

## Status — what's proven

Everything below is verified **in-container via Icarus** (`scripts/sim.sh`). The
standalone TBs are the trust anchor — they need **no PDK**.

- **Karplus-Strong engine is bit-exact verified.** The spec
  (`docs/karplus_strong.md`) → integer reference model
  (`models/ks_ref.py` → `models/ks_golden.hex`) → RTL (`src/ks_engine.sv`) →
  golden TB (`tb/tb_ks_engine.sv`) chain closes: **KS OK, 256/256 samples, 0
  mismatches.** Algorithm: a Galois-LFSR noise burst seeds the delay line on
  `pluck`, then a two-tap average × decay (gain `DECAY_NUM=2047 >> 12 ≈ 0.49976`)
  recirculates one step per `sample_tick`. `NMAX=1024` (period 2..1023); the
  delay line is an inferred reg-array RAM.
- **Spine integration proven.** KS is wired as `voice_sel = 4`. `tb/tb_synth_spine.sv`
  phase [5] plucks then selects voice 4 → **SPINE OK, 27 frames, 0 mismatches**,
  and the decoded I2S word is **-7568 = the KS golden first sample** — i.e. the
  engine → mux → serializer → I2S path is proven bit-exact end to end.
- **`chip_core` 1x0p5 pin map proven.** `tb/tb_chip_core_elab.sv` → **ELAB OK**:
  the direction mask is correct, `i2s_bclk` is live, clean under `-Wall`.
- **Template imported** → the tree is `make librelane`-ready.
- **GDSII hardening (`make librelane`) is greenlit and being attempted
  autonomously** — Docker `nixos/nix` rig; status is logged in PROGRESS.md Phase 5.

Run it (container-based standalone TBs — no PDK):
```bash
bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/spine.vvp src/synth_spine.sv src/ks_engine.sv tb/tb_synth_spine.sv && vvp /tmp/spine.vvp'
bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/ks.vvp src/ks_engine.sv tb/tb_ks_engine.sv && vvp /tmp/ks.vvp'
bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/core.vvp src/chip_core.sv src/synth_spine.sv src/ks_engine.sv tb/tb_chip_core_elab.sv && vvp /tmp/core.vvp'
```

`make sim` (cocotb on `chip_top`) and `make librelane` (RTL → GDSII) both need the
**PDK** — see PLAN §9 / PROGRESS Phase 5.

---

## Known caveats / TODO before tapeout

- **I2S timing**: the serializer is "I2S-style" and round-trips against our own
  receiver, but validate against the exact **Philips I2S** convention (data is
  delayed one BCLK after the WS edge) and against the specific DAC chip chosen.
- **SPI config port**: not built yet. v0 control is raw pins. Needed for loading
  neural weights and richer mode/param control. On the 1x0p5 slot there are only
  4 dedicated input pads (all used by `voice_sel`/`bypass_en`), so a future
  SPI/CV/gate port must live on **bidir pads configured as inputs** — exactly how
  the KS `pluck`/`period` controls already ride on bidir `[15:5]`.
- **Voice-switch latency**: switching `voice_sel` takes effect on the next frame
  (one-frame serializer pipeline latency). Expected, not a bug.
- **Placeholder oscillators** (saw/square) are stand-ins to exercise the mux; they
  get replaced/augmented by real engines.
- **KS delay-line area**: the Karplus-Strong delay line is an inferred reg-array
  RAM (`NMAX=1024` × 16b = 16 Kbit of flops) — fine for sim and for proving the
  contract, but area-hungry / timing-unfriendly in silicon. Production should back
  it with an SRAM macro or pick a smaller `NMAX` (see `docs/karplus_strong.md`
  "AREA caveat"). The contract is independent of how `line` is stored.
- **Area budget**: don't pack the 1x0p5 slot near full — leave headroom for timing
  closure and routing. Consider a larger slot if the engine list grows.
- **Analog/TRNG**: any on-die analog (entropy source, etc.) is a categorically
  higher-risk, non-LibreLane effort. Keep it optional and non-fatal.

---

## Engine roadmap

Build order is **your call** — the contract makes each one independent. Candidates,
roughly easiest-to-sing first:

1. **Karplus-Strong** plucked string — delay line + filter. ✅ **DONE — engine #1,
   BUILT and bit-exact verified** (`src/ks_engine.sv`, `voice_sel = 4`). It
   validated the contract end to end (see Status). The rest below are future work.
2. **Chaos engine** — Lorenz / logistic-map oscillators + a cellular-automaton
   sequencer. No training, alien textures, devoted modular following.
3. **SID homage** — 3 voices, classic waveforms, ring mod / sync. Nostalgia bait,
   well-understood target, low risk.
4. **Bytebeat box** — tiny configurable arithmetic expressions → music. Cult
   classic, tiny area (could even fit a half slot).
5. **Neural oscillator** (the headliner) — a small fixed-point MLP that *is* the
   waveform generator; morph timbre via control inputs; SPI-loadable weights.
   Most involved: needs MAC time-sharing to hit audio rate + **offline weight
   training & quantization** (a non-goal for the current run). Highest "talk about
   it" payoff.

**Where we are:** the simple first engine is done — Karplus-Strong shook out the
contract and the verification flow, so the harder engines can now be tackled with
confidence. Pick the next one off the list above.
