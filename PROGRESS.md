# Eurosynth build progress

Single source of truth for "what's done." Reconcile against `git log` before new
work. See [PLAN.md](PLAN.md) §5 for the chunk definitions and §11 for resume.

Legend: `[x]` done+verified · `[~]` in progress · `[ ]` not started · `[!]` blocked

## Phase 0 — De-risk & baseline
- [~] 0a  Build `eurosynth-sim` Docker image
- [ ] 0b  Spine TB runs green in container ("SPINE OK")
- [ ] 0c  Commit baseline + scaffold, branch, push to origin

## Phase 1 — Template integration
- [ ] 1a  Recon: clone template, report core/ports/VERILOG_FILES/chip_top wiring
- [ ] 1b  Integrate: files into src/ & tb/, reconcile ports, update VERILOG_FILES
- [ ] 1c  Regression: standalone spine TB green from new paths

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
_(appended as chunks land)_

## Morning report
_(written by the final chunk)_
