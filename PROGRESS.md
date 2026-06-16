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

> ### 🟢 SCOPE CHANGE (2026-06-16, mid-run): GDSII hardening GREENLIT
> The human greenlit **PLAN §9 (`make librelane`)** — formerly a non-goal — to run
> autonomously. New trailing phase **P5** below attempts the RTL→GDSII flow for
> `SLOT=1x0p5` in **WSL2 Ubuntu-22.04** (present on this machine; 108 GB free).
> Standalone-TB rail is unaffected and still the trust anchor. Hardening is
> long/heavy and may not finish by morning — P5 logs blockers in §12 rather than
> thrash, and runs the heavy steps in the background.
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
- [x] 3b  `chip_core` 1x0p5 pin-map redesign: `input_in[3:0]`=voice_sel+bypass_en;
          per-bit `bidir_oe` mask (generate loop) → bidir `[15:5]` are INPUTS
          (`ks_pluck`=bit5, `ks_period`=bits15:6), `bidir_ie=~bidir_oe`;
          i2s+heartbeat+tick+sample_dbg on output bidir pads. New harness
          `tb/tb_chip_core_elab.sv`. **Verified (main, in-container): ELAB OK with
          4/46/4 — direction mask correct, i2s_bclk live, clean `-Wall`, exit 0;
          spine TB still SPINE OK (no regression).** ✅
          NOTE: had to add inert default param values (`=1/32/1`) — iverilog
          `-g2012` rejects a no-default ANSI parameter (confirmed empirically).
          Param names/order unchanged; `chip_top` overrides all three, so the
          template contract is preserved.

## Phase 1 — Template integration  (after 2 & 3; only elaboration-checkable, no PDK)
- [x] 1a  Recon — captured in docs/template_integration.md
- [x] 1b  Layout: synth_spine/chip_core → src/, tb_synth_spine → tb/ (spine green)
- [x] 1b' Imported template tree (46 files: Makefile, flake, librelane/, cocotb/,
          ip/, src/chip_top.sv, src/slot_defines.svh) keeping OUR chip_core.
          `DEFAULT_SLOT=1x0p5`; `synth_spine`+`ks_engine` added to
          `librelane/config.yaml` VERILOG_FILES & cocotb sources; SRAM macro +
          PDN_MACRO_CONNECTIONS stripped from `macros_5v/3v3.yaml` & cocotb;
          `.gitignore` extended (`gf180mcu/`, generated_defines). Excluded
          `.github/` CI (nix; would fail every push) + template README. **Verified
          (main): chip_core.sv untouched; SPINE OK / KS OK / ELAB OK all still
          green; no PDK/runs/vcd junk in tree.** ✅

## Phase 4 — GDSII prep & docs
- [x] 4a  `librelane/config.yaml` verified: VERILOG_FILES lists all 4 RTL files,
          `DESIGN_NAME: chip_top`, clock `clk_PAD`/40ns, SRAM macros removed,
          slot 1x0p5 via `DEFAULT_SLOT` + `slot_defines.svh` (4/46/4). (Inspection,
          not a hardening run.) ✅
- [x] 4b  NOTES.md updated: 1x0p5 pin map (KS pluck/period on bidir inputs),
          status (KS bit-exact + spine + chip_core all verified), Files table,
          template-integration marked done, KS = engine #1 done in roadmap. ✅
- [ ] 4c  Final verify, push, morning report

## Phase 5 — GDSII hardening (§9, greenlit mid-run) — attempt autonomously
Env recon ruled out the WSL path (see §12). **Chosen rig: a long-lived Docker
container `eurosynth-harden` from `nixos/nix`** (root → can populate `/nix`
without host sudo), repo bind-mounted at `/work`, PDK on named volume `/pdk`.
The template `flake.nix` pulls librelane + EDA tools from the fossi-foundation
nix binary cache (prebuilt, not source-compiled). Commands run via
`docker exec eurosynth-harden bash -lc 'cd /work && nix develop --accept-flake-config --command bash -lc "SLOT=1x0p5 PDK_ROOT=/pdk make <tgt>"'`.
- [x] 5a  Materialized librelane devshell (`nix develop`, ~7.4 GB nix closure
          from fossi cache, no source builds). **LibreLane v3.1.0.dev1**;
          `librelane`/`make`/`ciel`/`iverilog` all on PATH. ✅
- [x] 5b  PDK fetched (gf180mcuD @ f6bfbd4, 4.0 GB at `/pdk/ciel/...`). First
          ciel attempt timed out mid-download (transient); a retry loop got a
          clean download on the next attempt. ✅
- [~] 5c  `SLOT=1x0p5 PDK_ROOT=/pdk make librelane` — IN PROGRESS, background
          (runs from container-local `/build` copy to dodge slow Windows
          bind-mount PnR I/O). Synthesis confirmed underway (yosys on the KS
          `line[]` 16 Kbit inferred memory). Verify: run completes, `final/`
          GDS views produced. Results/blockers → here + §12.

## Commit log (chunk → hash)
- baseline → f861ae0 (main)
- phase0/scaffold → 8ce8bfe
- phase0 mark done → c99514b
- phase1a/layout → ea1880a
- phase2a/spec+model+golden → 02fac94
- phase2c/ks_engine RTL → 890962f
- phase2d/ks golden TB → a2c7021
- docs/retarget PLAN to 1x0p5 → 7ae45ac
- phase3a/wire-in (KS into spine) → 7d16faa
- phase3b/chip_core 1x0p5 pin map → a0fe78b
- phase1b'/template import (1x0p5, KS in config) → (this commit)

## Morning report
_(written by the final chunk)_
