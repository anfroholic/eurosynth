# Kitchen-sink engine roster — build plan (`engines/kitchen-sink`)

Adds the remaining four sound engines from the roadmap plus an **SPI config port**,
following the same trust-anchored flow that made Karplus-Strong bit-exact:
**spec → Python golden model → golden vector → RTL → self-checking iverilog TB →
wire into spine → regression**, one commit per green engine. No PDK needed for the
verification rail.

## Decisions (locked)
- **Neural oscillator = morphing oscillator**: a `morph` control sweeps the timbre
  across a waveshape continuum (sine → saw → square → pulse). Trained offline (numpy).
- **Control = pins + an SPI config port** (new this branch): real-time play stays on
  pins; deep per-engine parameters and the neural weights load over SPI.

## Voice-select map (3-bit `voice_sel`, all 8 slots)
| sel | engine | status |
|----:|--------|--------|
| 0 | bypass ramp (bring-up) | existing |
| 1 | saw oscillator | existing |
| 2 | square oscillator | existing |
| 3 | **SID homage** (3 voices) | done |
| 4 | Karplus-Strong | done |
| 5 | **Chaos** (logistic/Lorenz + CA) | done |
| 6 | **Bytebeat** | done |
| 7 | **Neural morphing oscillator** | done |

Only one voice reaches the output at a time (the spine mux) → engines stay isolated.

## Control architecture
Real-time, on existing pads (unchanged):
- `input_PAD[2:0]` = `voice_sel`, `input_PAD[3]` = `bypass_en`
- `bidir_PAD[5]` = `gate`/trigger (pluck for KS; gate/retrigger for others)
- `bidir_PAD[15:6]` = 10-bit `pitch`/param bus (period for KS; pitch for others)

Deep config, over the new SPI slave (pin-map additions, direction mask extended;
all existing pads keep their meaning):
- `bidir_PAD[32]` = `spi_sclk` (in)
- `bidir_PAD[33]` = `spi_mosi` (in)
- `bidir_PAD[34]` = `spi_csn`  (in, active low)
- `bidir_PAD[36]` = `spi_miso` (out)

### SPI protocol (slave, Mode 0, MSB-first)
- 24-bit frame while `csn` low: `{ addr[7:0], data[15:0] }`. MOSI sampled on `sclk`
  rising. On `csn` rising (frame end) the 16-bit `data` is written to `config[addr]`.
- `miso` shifts out a fixed 16-bit liveness signature (`0x5713`) during the frame.
  (Full register readback = future enhancement.)
- SCLK/MOSI/CSN are 2-FF synchronized into the `clk` domain; edges detected there.
  SCLK must be ≪ `clk` (true in practice: clk ≥ ~10 MHz, SPI ≤ ~1 MHz).

### Config register map (128 × 16-bit, write via SPI)
| addr | use |
|------|-----|
| 0x00 | GLOBAL ctrl (config_valid, source-select bits) |
| 0x10 | bytebeat: `[3:0]` formula sel, `[11:4]` t-increment |
| 0x11 | chaos: `[1:0]` map sel, `[7:2]` rate, `[15:8]` r/seed |
| 0x12–0x14 | SID voice 0/1/2: freq-hi reuse, `[2:0]` waveform, `[3]` ring, `[4]` sync, `[15:8]` pulse-width |
| 0x15 | neural: `[7:0]` morph amount, `[15:8]` reserved |
| 0x40–0x4F | neural weights (loaded over SPI; reset defaults = trained values) |

Each engine reads its slice of the config bus combinationally. Engines also accept the
pin `pitch`/`gate` for real-time play; SPI params refine/override.

## Per-engine specs (summary)
All obey the **engine contract**: advance only on `sample_tick`, present a registered
signed-16 `sample` stable between ticks, one mux case. Each ships a bit-exact
`models/<eng>_ref.py` → `models/<eng>_golden.hex` and a `tb/tb_<eng>.sv`.

1. **Bytebeat** (`src/bytebeat.sv`) — free-running `t` counter; output = low 8 bits of
   one of N classic bytebeat formulas `f(t)` (e.g. `t*(t>>5|t>>8)`), mapped to signed
   16-bit. `formula`/`t_inc` from config. Pure integer → trivially bit-exact.
2. **Chaos** (`src/chaos_engine.sv`) — fixed-point **logistic map** `x←r·x·(1−x)` (Q16)
   and a **cellular-automaton** (rule-30/90/110) sequencer that perturbs `r`/pitch;
   optional fixed-point **Lorenz**. Output = state mapped to signed-16. Bit-exact
   fixed-point (same care as KS: form products wide, shift, truncate toward −∞).
3. **SID homage** (`src/sid_engine.sv`, `src/sid_voice.sv`) — 3 phase-accumulator
   voices; waveforms saw / triangle / pulse(+PW) / LFSR-noise; **ring-mod** (XOR MSB
   with neighbor) and **hard sync** (reset phase on neighbor overflow); summed & scaled.
   Per-voice params via config (0x12–0x14). Bit-exact.
4. **Neural morphing oscillator** (`src/neural_osc.sv`) — input features = harmonics of
   the phase from a sine LUT `[sin φ, sin 2φ, sin 3φ, sin 4φ]` + `morph`; a small MLP
   (e.g. 5→8→8→1, fixed-point, LUT/PWL activation) outputs the sample. One time-shared
   MAC sequences across the (~1024-cycle) audio frame. Weights quantized offline
   (`models/neural_train.py`, numpy), exported as reset-default params **and**
   SPI-loadable (0x40–0x4F). Golden = the quantized fixed-point forward pass.

## Build order (de-risk simplest first)
Bytebeat → SPI config port → Chaos → SID → Neural → full integration → docs.

## Verification
- Per engine: `bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/x.vvp src/<eng>.sv tb/tb_<eng>.sv && vvp /tmp/x.vvp'` → expect `0 mismatches`.
- SPI: TB drives frames, checks `config[]` contents + miso signature.
- Regression after each wire-in: spine TB + `chip_core` elaboration stay green.
- Hardening (full multi-engine GDSII) is a **follow-up** — 5 engines is tight on the
  half-slot; may want a larger slot. This branch leaves the tree hardening-ready.

---

## Status / resume (as of 2026-06-17)
- **Branch:** `engines/kitchen-sink` (off `overnight/karplus-strong`; has spine + KS +
  showcase docs). 1024 hardening baseline was **stopped** per human; the 256 GDSII
  deliverable is done on the previous branch.
- **DONE — roster complete + verified.** All 4 new engines **and** the SPI config port
  are built, **bit-exact** standalone (every golden regenerated from its model during
  the sweep → model↔RTL match is genuine), **integrated** into the spine, with the full
  regression **green**. The build-order/verification sections above stand as the
  method-of-record; this is the result.

### Done / verified
Every standalone TB = **0 mismatches** (re-run via `bash scripts/sim.sh ...`):

| voice / port | module(s) | TB / result | commit |
|---|---|---|---|
| 6 Bytebeat | `src/bytebeat.sv` | `tb/tb_bytebeat.sv` — 256 samples, **BYTEBEAT OK** | 9912ff8 (with SPI) |
| — SPI config | `src/spi_config.sv` | `tb/tb_spi_config.sv` — 36 checks, **SPI OK** | 9912ff8 |
| 5 Chaos | `src/chaos_engine.sv` | `tb/tb_chaos_engine.sv` — 255 samples, **CHAOS OK** | d4e8344 |
| 3 SID | `src/sid_engine.sv`, `src/sid_voice.sv` | `tb/tb_sid_engine.sv` — 256 samples, **SID OK** | 71268ab |
| 7 Neural | `src/neural_osc.sv` | `tb/tb_neural_osc.sv` — 255 samples, **NEURAL OK** | 6182c2c |
| (config in librelane+cocotb) | — | RTL registered in `VERILOG_FILES` / cocotb sources | f393d2e |

- **Integration** (`src/synth_spine.sv`): spine instantiates `spi_config` + all 4 new
  engines; each reads its config slice combinationally; mux cases 3/5/6/7 added; neural
  weight writes (0x40–0x4F) routed from the SPI write-event taps
  (`cfg_we`/`cfg_addr`/`cfg_wdata`).
- **Regression — green.** Spine `tb/tb_synth_spine.sv`: **SPINE OK**, 64 frames, 0
  mismatches (drives SPI config frames, then selects voices 3/5/6 — each reaches the
  serializer non-silent and round-trips through the I2S decoder; voice 4 KS unchanged).
  Chip elaboration `tb/tb_chip_core_elab.sv`: **ELAB OK** — 1x0p5 (4/46/4) direction
  mask correct including the new SPI bits (`oe[34:32]=0`, `oe[36]=1`), and neural voice 7
  is proven at the real frame rate (`BCLK_DIV=16` ≈ 1024 clk/frame ≫ the ~139-clk MAC).
- **Pin-map additions** are in chip_core (1x0p5, 4/46/4): `bidir[34:32]` = SPI
  sclk/mosi/csn (inputs, `oe=0`), `bidir[36]` = SPI miso (output). `ks_period`
  (`bidir[15:6]`) now **also** doubles as the shared 10-bit pitch bus for SID + neural.

### Follow-ups (caveats, recorded honestly)
- **Full multi-engine GDSII hardening is NOT done on this branch** — 5 engines is tight
  on the half slot (may want a larger slot). The tree is left **hardening-ready** (all
  RTL in `config.yaml`). The prior 256 KS-only clean signoff stands on the previous
  branch; this branch is RTL + verification only.
- **Before any hardening run**, `neural_osc`'s `$readmemh` weight path
  (`models/neural_weights.hex`) must be made **absolute** (synth cwd is the run dir, not
  the repo root) — set the `WFILE` param or convert the weights to `localparam` initial
  values.
