# Eurosynth build progress

Single source of truth for "what's done." Reconcile against `git log` before new
work. See [PLAN.md](PLAN.md) §5 for the chunk definitions and §11 for resume.

Legend: `[x]` done+verified · `[~]` in progress · `[ ]` not started · `[!]` blocked

## Phase 0 — De-risk & baseline  ✅ DONE (human awake)
- [x] 0a  Build `eurosynth-sim` Docker image — Icarus 11.0 confirmed in-container
- [x] 0b  Spine TB green in container — 21 frames, 0 mismatches ("SPINE OK")
- [x] 0c  Baseline on `main` (f861ae0) + scaffold on `overnight/karplus-strong`
          (8ce8bfe); both pushed to origin. `git push` credentials proven.

> **Recon finding (changes the verification rail):** the template's `make sim`
> (cocotb on `chip_top`) AND `make librelane` both need the **PDK** (multi-GB
> `ciel` download) + nix toolchain for pad-cell behavioral models. Our light sim
> image has neither. So **tonight's autonomous verification = standalone Icarus
> TBs** on pure RTL (spine, ks_engine, chip_core elaboration). Full `chip_top`
> cocotb + GDSII = the human PDK session. Our `chip_core` already matches the
> template's exact port contract and is SRAM-free.
>
> **Execution reorder:** doing the fully-verifiable KS engine (Phase 2) + spine
> wire-in (Phase 3) FIRST to bank verified value, THEN the heavier template
> import (Phase 1) which is only elaboration-checkable without the PDK.

## Phase 1 — Template integration  (done AFTER 2 & 3)
- [x] 1a  Recon — template cloned to sibling dir; integration points mapped
- [~] 1b  Layout: synth_spine/chip_core → src/, tb_synth_spine → tb/ (spine green)
- [ ] 1b' Import template tree into repo; add synth_spine+ks_engine to VERILOG_FILES
          & cocotb sources; strip SRAM macro/PDN refs. Verify: chip_core elaborates.
- [ ] 1c  Regression: standalone spine TB green from src//tb/ paths

## Phase 2 — Karplus-Strong engine
- [ ] 2a  Spec: docs/karplus_strong.md (ports match contract)
- [ ] 2b  Model: models/ks_ref.py emits golden vector
- [ ] 2c  RTL: src/ks_engine.sv elaborates clean
- [ ] 2d  TB: tb/tb_ks_engine.sv self-checks vs golden, 0 mismatches

## Phase 3 — Spine integration + regression
- [ ] 3a  Wire ks_engine into spine (mux case 4) + chip_core pins; spine TB green
- [ ] 3b  cocotb test selects KS voice; `make sim` green

## Phase 4 — GDSII prep & docs
- [ ] 4a  librelane/config.yaml VERILOG_FILES + top correct
- [ ] 4b  NOTES.md status/roadmap updated
- [ ] 4c  Final verify, push, morning report

## Commit log (chunk → hash)
- baseline → f861ae0 (main)
- phase0/scaffold → 8ce8bfe

## Morning report
_(written by the final chunk)_
