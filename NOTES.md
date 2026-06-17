# Synth chip — project notes / handoff brief

A "kitchen-sink" eurorack synthesizer voice on the **GF180MCU** PDK, built on the
[wafer.space gf180mcu project template](https://github.com/wafer-space/gf180mcu-project-template)
and the LibreLane digital RTL-to-GDSII flow.

This file is the source of truth for *why the design looks the way it does*. If you
are a fresh session picking this up, read this first, then the comments in the RTL.

> 📣 **Showing the chip off?** See [docs/SHOWCASE.md](docs/SHOWCASE.md) (architecture,
> silicon signoff, specs, pinout) and [docs/HARDWARE_GUIDE.md](docs/HARDWARE_GUIDE.md)
> (power/clock/reset + a sample circuit for every pad + an Arduino controller).

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

> Note: the `voice_sel` mux is now **fully populated** — `3'd3` SID, `3'd4`
> Karplus-Strong, `3'd5` chaos, `3'd6` bytebeat, `3'd7` neural (plus `3'd0`–`3'd2`
> = bypass ramp / saw / square). All eight slots are taken; a further engine would
> have to share or replace a slot.

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
`voice_sel` / `bypass_en` (the KS pluck/period, the SID/neural pitch, and the SPI
config port) has to live on **bidir pads configured as inputs**. This map matches
`src/chip_core.sv`.

Dedicated input pads (`input_in[]`, all 4 used):
| bit | function                                                                       |
|-----|--------------------------------------------------------------------------------|
| 2:0 | `voice_sel` (0=ramp, 1=saw, 2=square, **3=SID, 4=Karplus-Strong, 5=chaos, 6=bytebeat, 7=neural**) |
| 3   | `bypass_en` (force the bring-up test ramp)                                      |

Bidir pads are **per-bit direction-configurable**: a generate-loop builds a static
`bidir_oe` mask (output where `oe=1`, input where `oe=0`), and `bidir_ie = ~bidir_oe`.

Bidir bits driven as INPUTS (`oe=0`):
| bit   | function                                                                        |
|-------|---------------------------------------------------------------------------------|
| 5     | `ks_pluck` — 1-clk strobe to (re)excite the string                              |
| 15:6  | `ks_period[9:0]` — delay-line length / pitch; **also** the shared 10-bit pitch bus for the SID + neural voices |
| 32    | `spi_sclk` — SPI config clock (in)                                              |
| 33    | `spi_mosi` — SPI config data in                                                |
| 34    | `spi_csn` — SPI config chip-select (in, active low)                            |

Bidir bits driven as OUTPUTS (`oe=1`):
| bit   | function                                            |
|-------|-----------------------------------------------------|
| 0     | `i2s_sd`  — serial audio data to DAC                |
| 1     | `i2s_bclk` — bit clock                              |
| 2     | `i2s_ws` — word select / LRCK                       |
| 3     | `heartbeat` — slow toggle, "chip is alive" LED      |
| 4     | `sample_tick` — audio-rate frame strobe (scope tap) |
| 36    | `spi_miso` — SPI liveness/readback (out)            |
| 31:16 | `sample_dbg` — parallel sample mirror (bring-up)    |

Analog pads (4): currently **unused / reserved**. Held for a future on-die
entropy/TRNG output or an analog interface experiment.

---

## Files

| file                          | role                                                       |
|-------------------------------|------------------------------------------------------------|
| `src/synth_spine.sv`          | The reusable spine: tick gen, mux, bypass ramp, serializer, 2 placeholder oscillators, plus the `spi_config` port + all 5 engine instances (KS, SID, chaos, bytebeat, neural). |
| `src/chip_core.sv`            | Drop-in replacement for the template's example core. Wires the spine to the 1x0p5 pad interface (incl. the SPI pins on bidir 32–34 in / 36 out). |
| `src/ks_engine.sv`            | Karplus-Strong plucked-string voice (engine #1, `voice_sel = 4`). |
| `src/sid_engine.sv`, `src/sid_voice.sv` | SID homage — 3 phase-accum voices, ring-mod + hard sync (`voice_sel = 3`). |
| `src/chaos_engine.sv`         | Chaos — logistic / CA-perturbed / Lorenz (`voice_sel = 5`). |
| `src/bytebeat.sv`             | Bytebeat formula generator (`voice_sel = 6`). |
| `src/neural_osc.sv`           | Neural morphing oscillator — fixed-point MLP (`voice_sel = 7`); weights from `models/neural_weights.hex`, SPI-loadable. |
| `src/spi_config.sv`           | SPI slave config port — 128×16 regfile, deep params + neural weight load. |
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
  recirculates one step per `sample_tick`. `NMAX=256` (period 2..255); the
  delay line is an inferred reg-array RAM. `period` is a fixed 10-bit control
  clamped internally to `[2, NMAX-1]`, so NMAX is decoupled from the pin map.
- **Spine integration proven.** KS is wired as `voice_sel = 4`. `tb/tb_synth_spine.sv`
  phase [5] plucks then selects voice 4 → **SPINE OK, 27 frames, 0 mismatches**,
  and the decoded I2S word is **-7568 = the KS golden first sample** — i.e. the
  engine → mux → serializer → I2S path is proven bit-exact end to end.
- **Full engine roster + SPI config port — built & bit-exact** (branch
  `engines/kitchen-sink`). Every standalone TB = 0 mismatches: **BYTEBEAT OK** (256),
  **SPI OK** (36 checks), **CHAOS OK** (255), **SID OK** (256), **NEURAL OK** (255).
  Goldens were regenerated from their models during the sweep, so model↔RTL is genuine.
  Voices 3/5/6/7 are now populated (SID / chaos / bytebeat / neural); the SPI port
  drives deep per-engine params + the neural weight-load window (0x40–0x4F).
- **Spine regression — green with the new engines.** `tb/tb_synth_spine.sv` drives SPI
  config frames then selects voices 3/5/6 → **SPINE OK, 64 frames, 0 mismatches**, each
  reaching the serializer non-silent + round-tripping through the I2S decoder (KS voice
  4 unchanged).
- **`chip_core` 1x0p5 pin map proven** (now incl. the SPI bits). `tb/tb_chip_core_elab.sv`
  → **ELAB OK**: the direction mask is correct including `oe[34:32]=0` (SPI inputs) and
  `oe[36]=1` (spi_miso), `i2s_bclk` is live, clean under `-Wall`. Neural voice 7 is also
  proven at the **real frame rate** here (`BCLK_DIV=16` ≈ 1024 clk/frame ≫ the ~139-clk
  MAC) — its sample mirror goes non-zero.
- **Template imported** → the tree is `make librelane`-ready; all engine RTL is in
  `librelane/config.yaml` (`VERILOG_FILES`) + the cocotb sources.
- **GDSII hardening:** the 256 KS-only design has a clean signoff on the **previous**
  branch (PROGRESS.md Phase 5e). **Full multi-engine hardening is a follow-up** — 5
  engines is tight on the half slot; before any run, make `neural_osc`'s `$readmemh`
  weight path absolute (synth cwd is the run dir, not the repo root). This branch is
  RTL + verification only.

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
- **SPI config port**: ✅ **built + verified** (`src/spi_config.sv`, **SPI OK**, 36
  checks). Mode 0, MSB-first, 24-bit `{addr[7:0], data[15:0]}` frames into a 128×16
  regfile; loads neural weights (0x40–0x4F) + per-engine deep params; `miso` shifts a
  fixed liveness signature `0x5713` (full register readback is a future enhancement).
  Since the 1x0p5 slot's 4 dedicated input pads are all used by
  `voice_sel`/`bypass_en`, the SPI pins ride on **bidir pads configured as inputs**
  (`sclk`/`mosi`/`csn` = bidir `[34:32]`, `miso` out = bidir `[36]`) — exactly how the
  KS `pluck`/`period` controls already ride on bidir `[15:5]`.
- **Voice-switch latency**: switching `voice_sel` takes effect on the next frame
  (one-frame serializer pipeline latency). Expected, not a bug.
- **Placeholder oscillators** (saw/square) are stand-ins to exercise the mux; they
  get replaced/augmented by real engines.
- **KS delay-line area**: the Karplus-Strong delay line is an inferred reg-array
  RAM (`NMAX=256` × 16b = 4 Kbit of flops) — fine for sim and for proving the
  contract, but still area-hungry / timing-unfriendly in silicon. Production should
  back it with an SRAM macro or pick an even smaller `NMAX` (see
  `docs/karplus_strong.md` "AREA caveat"). `period` is a fixed 10-bit control
  clamped internally to `[2, NMAX-1]`, so NMAX can change without touching the
  contract or pin map. The contract is independent of how `line` is stored.
- **Area budget**: don't pack the 1x0p5 slot near full — leave headroom for timing
  closure and routing. Consider a larger slot if the engine list grows.
- **Analog/TRNG**: any on-die analog (entropy source, etc.) is a categorically
  higher-risk, non-LibreLane effort. Keep it optional and non-fatal.

---

## Engine roadmap

The contract makes each engine independent. The full roster is now **built and
bit-exact verified** (branch `engines/kitchen-sink`; per-engine specs + verify lines
in [docs/engines_plan.md](docs/engines_plan.md)):

1. **Karplus-Strong** plucked string — delay line + filter. ✅ **DONE — engine #1,
   bit-exact** (`src/ks_engine.sv`, `voice_sel = 4`). Shook out the contract + verify
   flow end to end (see Status).
2. **Chaos engine** — Q16 logistic map, rule-30 CA-perturbed logistic, Q12 Lorenz.
   ✅ **DONE — bit-exact** (`src/chaos_engine.sv`, `voice_sel = 5`, **CHAOS OK**).
3. **SID homage** — 3 phase-accum voices, classic waveforms, ring mod / hard sync.
   ✅ **DONE — bit-exact** (`src/sid_engine.sv` + `src/sid_voice.sv`, `voice_sel = 3`,
   **SID OK**).
4. **Bytebeat box** — free-running integer formula generator (4 classic formulas).
   ✅ **DONE — bit-exact** (`src/bytebeat.sv`, `voice_sel = 6`, **BYTEBEAT OK**).
5. **Neural oscillator** (the headliner) — a small fixed-point MLP (5→8→8→1, Q1.14,
   ReLU) that *is* the waveform generator; `morph` sweeps sine→saw→square→pulse;
   one time-shared MAC (~139 clk/sample); weights trained offline in numpy and
   **SPI-loadable** (0x40–0x4F). ✅ **DONE — bit-exact** (`src/neural_osc.sv`,
   `voice_sel = 7`, **NEURAL OK**).

Plus the **SPI config port** (`src/spi_config.sv`, **SPI OK**) — the deep-param /
weight-load channel for all of the above.

**Where we are:** the roster is **complete and verified** — all 5 engines + the SPI
config port are bit-exact standalone, integrated into the spine, and the regression
is green (**SPINE OK** 64 frames / **ELAB OK**). Remaining work is the **follow-up
multi-engine GDSII hardening** (not on this branch — 5 engines is tight on the half
slot; see caveats above). The 256 KS-only clean signoff stands on the previous branch.
