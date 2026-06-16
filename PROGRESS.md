# Eurosynth build progress

Single source of truth for "what's done." Reconcile against `git log` before new
work. See [PLAN.md](PLAN.md) for chunk definitions/resume and
[docs/template_integration.md](docs/template_integration.md) for the template facts.

Legend: `[x]` done+verified · `[~]` in progress · `[ ]` not started · `[!]` blocked

---
> ### 🎯 TARGET SLOT CHANGED: `1x1` → `1x0p5` (half slot)
> Pad budget is now **4 input / 46 bidir / 4 analog** (was 12/40/2). Only 4 input
> pads → `voice_sel[2:0]` + `bypass_en` fill them; KS `pluck`/`period` (and future
> CV/gates/SPI) must move to **bidir pads configured as inputs**. Engine DSP is
> slot-independent. All build commands use `SLOT=1x0p5`. Details + new pin map in
> [docs/template_integration.md](docs/template_integration.md) and NOTES.md.

> ### ⚙️ Verification rail (PDK reality)
> Template `make sim` (cocotb on `chip_top`) AND `make librelane` need the **PDK**
> (multi-GB `ciel` fetch) + nix → **human PDK session**, not the light Docker image.
> Autonomous tonight verifies via **standalone Icarus TBs** (spine, ks_engine,
> chip_core elaboration). Execution reorder: KS engine (P2) + wire-in (P3) FIRST,
> heavier template import (P1) after.
---

## Phase 0 — De-risk & baseline  ✅ DONE (human awake)
- [x] 0a  `eurosynth-sim` Docker image — Icarus 11.0 confirmed in-container
- [x] 0b  Spine TB green in container — 21 frames, 0 mismatches ("SPINE OK")
- [x] 0c  Baseline on `main` (f861ae0) + scaffold (8ce8bfe); pushed. Push proven.

## Phase 2 — Karplus-Strong engine (slot-independent; in progress)
- [x] 2a  Spec `docs/karplus_strong.md` + bit-exact model `models/ks_ref.py`
          (ports match contract). Verified in-container: deterministic, 256-line
          `models/ks_golden.hex`; first sample -7568 == 0xe270. ✅
- [ ] 2c  RTL `src/ks_engine.sv` implementing the spec's exact integer math;
          elaborates clean under iverilog `-g2012` (no latches/width errors).
- [ ] 2d  TB `tb/tb_ks_engine.sv` self-checks vs `models/ks_golden.hex` via
          `$readmemh`, period=48, 256 samples, **0 mismatches**.

## Phase 3 — Spine integration + regression
- [ ] 3a  Instantiate `ks_engine` in `src/synth_spine.sv`, add mux case `3'd4`,
          feed it `sample_tick`. Verify: spine TB still "SPINE OK" + KS voice
          reaches serializer.
- [ ] 3b  `chip_core` 1x0p5 pin-map redesign: input_in[3:0] = voice_sel+bypass_en;
          per-bit `bidir_oe`/`bidir_ie` so chosen bidir pads are INPUTS for
          `pluck`/`period`; i2s+heartbeat+tick+sample_dbg on output bidir pads.
          Verify: chip_core elaborates with 1x0p5 params (4/46/4), no latches.

## Phase 1 — Template integration  (after 2 & 3; only elaboration-checkable, no PDK)
- [x] 1a  Recon — captured in docs/template_integration.md
- [~] 1b  Layout: synth_spine/chip_core → src/, tb_synth_spine → tb/ (spine green)
- [ ] 1b' Import template tree into repo; set DEFAULT_SLOT/usage to 1x0p5; add
          synth_spine + ks_engine to VERILOG_FILES & cocotb sources; strip SRAM
          macro/PDN refs. Verify: chip_core elaborates.

## Phase 4 — GDSII prep & docs (NO hardening run)
- [ ] 4a  librelane/config.yaml VERILOG_FILES + top + 1x0p5 correct
- [ ] 4b  NOTES.md status/roadmap/pin-map updated for 1x0p5 + KS
- [ ] 4c  Final verify, push, morning report

## Commit log (chunk → hash)
- baseline → f861ae0 (main)
- phase0/scaffold → 8ce8bfe
- phase0 mark done → c99514b
- phase1a/layout → ea1880a

## Morning report
_(written by the final chunk)_
