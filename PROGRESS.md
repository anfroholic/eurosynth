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
- [x] 2c  RTL `src/ks_engine.sv` — elaborates clean (-g2012 -Wall, exit 0).
- [x] 2d  TB `tb/tb_ks_engine.sv` — **KS OK: 256/256 samples matched golden,
          0 mismatches.** (Main caught + fixed a clock-edge race in the TB strobe;
          design was correct.) ✅ **Karplus-Strong engine is bit-exact verified.**

## Phase 3 — Spine integration + regression
- [x] 3a  Instantiate `ks_engine` in `src/synth_spine.sv` (new spine ports
          `ks_pluck`/`ks_period[9:0]`), add mux case `3'd4`, feed it
          `sample_tick`. TB phase [5] plucks then selects voice 4. **Verified
          (main, in-container): SPINE OK, 27 frames, 0 mismatches; phases
          [1]–[4] unchanged; voice-4 round-trip decoded -7568 (== KS golden
          first sample), `ks_nonzero` guard proves the voice is non-silent.** ✅
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
- phase2a/spec+model+golden → 02fac94
- phase2c/ks_engine RTL → 890962f
- phase2d/ks golden TB → a2c7021
- docs/retarget PLAN to 1x0p5 → 7ae45ac
- phase3a/wire-in (KS into spine) → (this commit)

## Morning report
_(written by the final chunk)_
