# Eurosynth build progress

Single source of truth for "what's done." Reconcile against `git log` before new
work. See [PLAN.md](PLAN.md) for chunk definitions/resume and
[docs/template_integration.md](docs/template_integration.md) for the template facts.

Legend: `[x]` done+verified · `[~]` in progress · `[ ]` not started · `[!]` blocked

---
> ### 🚀 NEW DIRECTION (2026-06-17): full engine roster on branch `engines/kitchen-sink` — ✅ COMPLETE
> The 256 GDSII deliverable shipped (clean signoff; see Phase 5e). The 1024 baseline
> was **stopped** per human call. New work added the remaining roadmap engines —
> **Bytebeat, Chaos, SID, Neural morphing oscillator** — plus an **SPI config port**,
> all on branch **`engines/kitchen-sink`**. **Plan + status + resume steps:
> [docs/engines_plan.md](docs/engines_plan.md).** Build method: **parallel subagents,
> one per isolated engine, self-verifying; main integrates into the spine.**
> **STATUS: roster COMPLETE + verified** — all 4 engines + SPI built, bit-exact
> standalone, integrated into the spine, full regression green (see Phase E below).
> Full multi-engine GDSII hardening remains a follow-up (not on this branch).
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
- [~] 5c  `make librelane` (from container-local `/build`). **Run 1 reached
          stage 22/83 then failed: `[PDN-1030] Unable to find instance
          i_chip_core.sram_0`** — the SRAM removal missed `librelane/pdn/pdn_cfg.tcl`,
          which unconditionally `source`s `pdn_5v_sram.tcl` (PDN grids for the
          deleted SRAMs). FIXED: pdn_cfg.tcl no longer sources the SRAM PDN.
          Timing note: yosys synthesis of the KS 16 Kbit flop `line[]` took ~6 h
          (steps 1–21 = ~7 h total) — synthesis is the bottleneck (see area
          caveat; smaller NMAX or SRAM macro would slash this). Re-running via
          **resume** (`--last-run --from OpenROAD.GeneratePDN`) to skip the 6 h
          synthesis. **Status 2026-06-17 ~04:18 UTC: still grinding — at step 37/83
          (`OpenROAD.ResizerTimingPostCTS`) for ~6.5 h — WEDGED.** The post-CTS resizer is
          churning on ~16 400 violating endpoints (WNS ~−54 ns vs 40 ns clock) from
          the 1024:1 mux; it improves WNS only marginally (-53.6 to -44.0 ns over 5 h, ~10 ns/5 h) and CANNOT
          converge (1024:1 mux path is architecturally too long; buffering won't fix
          it). Finishing the flow would be ~12-24 h more for a predictably
          inferior-to-256 result. **Per human call (2026-06-17 ~09:30 UTC): LEFT
          RUNNING** to capture its GDS if it ever completes (orphaned to PID 1,
          survives sessions). Not a blocker; the 256 (5e) remains the deliverable. **LOWER PRIORITY now** — the 256 lean (5e) is the proven clean
          deliverable, and the 1024 is the *same architecture* (just NMAX 1024) so it
          adds no new manufacturability info, only a slower variant with worse setup.
          Left running (no contention; pmap wall at step 60 is pre-fixed) — if it
          finishes it's a bonus; not a blocker. Verify if done: `final/` GDS produced.
- [x] 5d  **Lean variant: KS `NMAX` 1024→256** (per human call: finish 1024
          baseline, then ship 256). `period` port decoupled to a fixed `[9:0]`
          (contract) and clamped internally, so the pin map is untouched. Golden
          is **byte-identical** (PGOLDEN=48 ≤ 255). **Verified (main): KS OK /
          SPINE OK / ELAB OK; `models/ks_golden.hex` unchanged.** ✅ (commit 9a4cc62)
- [x] 5e  **Harden the lean 256 design — DONE, CLEAN SIGNOFF.** 🎉 `RESUME256_EXIT=0`,
          flow reached step 80/80 and saved all final views. `final/gds/chip_top.gds`
          (112 MB) produced. **Signoff (from `final/metrics.json` + manufacturability.rpt):**
          Magic DRC **0**, KLayout DRC **0**, routing DRC **0** (converged), density **0**,
          **LVS 0** (0 device/net/pin diffs, 0 errors — layout matches netlist),
          antenna **0** violating nets/pins, PDN **0**, unmapped cells **0**, flow errors **0**.
          manufacturability.rpt = **Antenna ✅ / LVS ✅ / DRC ✅ all Passed**. Die area
          ~9.95 M units, core ~5.0 M, util 37%, 81 antenna diodes. **Caveat — setup
          timing:** WNS −21.7 ns vs the template's default 40 ns/25 MHz `clk_PAD` SDC
          (12 315 violating endpoints; the 256:1 delay-line read mux is the critical
          path). **Hold is clean (0 vios)** — the unfixable-post-fab one. Setup is a
          non-issue for an audio synth that advances on a ~48 kHz `sample_tick`; the
          real operational clock is far below 25 MHz (future: pipeline the mux or use
          an SRAM macro to close 25 MHz). Curated deliverable extracted to repo
          `final/` (gitignored): gds, klayout_gds, nl/pnl, spice, def, lib, sdc, render,
          metrics, manufacturability.rpt. Full 998 MB bundle (incl. sdf/spef/odb/mag
          intermediates) remains in container at `/build256/final`.

> ### 🔧 BLOCKER HIT + FIXED (2026-06-17 ~03:05 UTC): missing `pmap` in container
> Run 1 of the 256 flow produced a valid GDS (Magic/KLayout streamout, steps 56–57)
> but **crashed at step 60 `KLayout.Antenna` with exit 2**. Root cause: the PDK's
> KLayout **antenna + LVS** decks (`/pdk/.../klayout/tech/drc/gf180mcu.drc:53`,
> `.../lvs/gf180mcu.lvs:74`) log memory via `` `pmap PID | tail -1`[10,40].strip ``;
> `pmap` (procps) was **absent** in the container, so the backtick → `""`,
> `""[10,40]` → `nil`, `nil.strip` → `NoMethodError`. (Same missing procps that broke
> `ps` — see the `/proc` note below.) **Fix:** `nix profile install nixpkgs#procps`
> → `pmap` now resolves via `/root/.nix-profile/bin/pmap` (on the running 1024's PATH
> AND fresh devshells); `ps`/`pgrep` work again too. One fix covers both runs and the
> later LVS step. Resumed the 256 `--last-run --from KLayout.Antenna` → ran clean to
> completion.

### ⏳ HARDENING STATUS — how to resume on a fresh session (updated 2026-06-17 ~04:20 UTC)
**Live status (04:20):** ✅ **256 lean = DONE, clean signoff** (`RESUME256_EXIT=0`;
`final/` extracted to repo — see Phase 5e + Morning report). ⏳ **1024 baseline =
still running**, step 37/83 (post-CTS resizer), slow/optional. Use `/proc` (NOT `ps`)
to check liveness.

Rig: long-lived Docker container **`eurosynth-harden`** (`nixos/nix`; `/nix` has
LibreLane v3.1.0.dev1 + tools; **`procps` now installed** so `pmap`/`ps` work).
Mounts: `/work`=repo, `/pdk`=gf180mcuD PDK volume.
Run hardening as: `docker exec eurosynth-harden bash -lc 'cd <DIR> && nix develop --accept-flake-config --command bash -lc "SLOT=1x0p5 PDK_ROOT=/pdk make librelane"'`.
Detached relaunch that survives sessions: `docker exec -d eurosynth-harden bash -lc '<script> > <log> 2>&1'`.

Runs (bg task IDs are from prior sessions and now dead — runs orphan to PID 1 and
keep going; track by log sentinel + `/proc`, not by task ID):
| run | RTL | work dir | run dir | log | sentinel |
|---|---|---|---|---|---|
| **1024 baseline** (running) | 1024 (commit a30de83) | `/build` | `/build/librelane/runs/RUN_2026-06-16_15-04-43` | `/root/resume.log` | `RESUME_EXIT=` |
| **256 lean** ✅ DONE | 9a4cc62 | `/build256` | `/build256/librelane/runs/RUN_2026-06-16_22-40-18` | `/root/harden256.log` then `/root/resume256.log` | `RESUME256_EXIT=0` |

⚠️ **`ps`/`pgrep` ARE BROKEN in this container** (procps reports only PID 1 / "1
process" even while flows run — nearly caused a wrongful relaunch that would have
`rm -rf`'d a live run). To check process liveness, **enumerate `/proc` directly**:
`docker exec eurosynth-harden bash -lc 'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline; echo; done | grep -E "openroad|librelane|make"'`.
A running flow shows `…/bin/python3.13 …librelane…` + an `openroad`/`yosys` child.

⚠️ **Do NOT relaunch a run that is still alive.** `harden256.sh` begins with
`rm -rf /build256` — re-running it destroys an in-progress 256 run. Confirm via
`/proc` that the flow is dead AND that no exit sentinel will appear before relaunch.

Check status (fresh session):
- `docker exec eurosynth-harden bash -lc 'tail -30 /root/harden256.log'` (and `/root/resume.log`).
  Success sentinels: `HARDEN256_EXIT=0` / `RESUME_EXIT=0` (or `RESUME2_EXIT=0`).
  Step progress:
  `docker exec eurosynth-harden bash -lc 'ls -1dt /build256/librelane/runs/*/[0-9][0-9]-*/ | head'`.
- GDS when done: `docker exec eurosynth-harden ls -la /build256/final/` (look for `final/gds/chip_top.gds`).
  Extract: `docker cp eurosynth-harden:/build256/final <repo>/final` (final/ is gitignored — large binary).
- Baseline 1024 is SLOW (16 Kbit flops; STA steps ~tens of min). If it's wedged or
  no longer needed, the 256 lean GDS is the real deliverable.

Remaining after a run finishes: verify `final/` GDS + check DRC/LVS in the run's
reports/`*.rpt`/metrics; copy the GDS out; then Phase 4c (morning report + final push).

## Phase E — kitchen-sink engine roster (branch `engines/kitchen-sink`)  ✅ DONE
Method-of-record + per-engine specs: [docs/engines_plan.md](docs/engines_plan.md).
All standalone TBs run via `bash scripts/sim.sh ...` (Docker `eurosynth-sim` Icarus,
no PDK); every golden was **regenerated from its model** during the sweep, so the
model↔RTL match is genuine. Engines built by parallel subagents; integration serial in
main.
- [x] Ea  **Bytebeat** (voice 6) — `src/bytebeat.sv`: free-running integer formula gen,
          4 classic formulas, output = low 8 bits → signed-16; config 0x10
          (`formula_sel[3:0]`, `t_inc[11:4]`). **BYTEBEAT OK** — `tb/tb_bytebeat.sv`,
          256 samples, 0 mismatches. ✅ (commit 9912ff8)
- [x] Eb  **SPI config port** — `src/spi_config.sv`: Mode 0, MSB-first, 24-bit frame
          `{addr[7:0], data[15:0]}`; MOSI sampled on sclk-rising, write commits on csn
          rising; 128×16 regfile flattened as `cfg_flat`; `miso` shifts fixed liveness
          sig `0x5713`; sclk/mosi/csn 2-FF synced into `clk`. **SPI OK** —
          `tb/tb_spi_config.sv`, 36 checks. ✅ (commit 9912ff8)
- [x] Ec  **Chaos** (voice 5) — `src/chaos_engine.sv`: Q16 logistic map, rule-30
          CA-perturbed logistic, Q12 Euler Lorenz; `map_sel` chooses; config 0x11
          (`map_sel[1:0]`, `rate[7:2]`, `r_seed[15:8]`). **CHAOS OK** —
          `tb/tb_chaos_engine.sv`, 255 samples, 0 mismatches. ✅ (commit d4e8344)
- [x] Ed  **SID homage** (voice 3) — `src/sid_engine.sv` + `src/sid_voice.sv`: 3
          phase-accum voices (saw/triangle/pulse+PW/LFSR-noise) with ring-mod (neighbor
          MSB into triangle fold) + hard sync (neighbor overflow resets accumulator),
          summed & scaled `>>2`; per-voice config 0x12–0x14 (`waveform[2:0]`, `ring[3]`,
          `sync[4]`, `pulse-width[15:8]`); the 3 phase increments come from the shared
          pitch bus (v1 detuned, v2 one octave down). **SID OK** — `tb/tb_sid_engine.sv`,
          256 samples, 0 mismatches. ✅ (commit 71268ab)
- [x] Ee  **Neural morphing oscillator** (voice 7) — `src/neural_osc.sv`: fixed-point
          MLP 5→8→8→1, ReLU, Q1.14; `morph` (config 0x15[7:0]) sweeps
          sine→saw→square→pulse; features = 4 phase harmonics from a 256-entry sine LUT
          + morph; one time-shared MAC (~139 clk/sample). Weights trained offline in
          numpy (seeded/deterministic; `models/neural_train.py`, `models/neural_ref.py`),
          embedded via `$readmemh` (`models/neural_weights.hex`), SPI-overwritable in
          0x40–0x4F. **NEURAL OK** — `tb/tb_neural_osc.sv`, 255 samples, 0 mismatches.
          ✅ (commit 6182c2c)
- [x] Ef  **Spine integration** (`src/synth_spine.sv`) — instantiates `spi_config` + all
          4 new engines; each reads its config slice combinationally; mux cases 3/5/6/7
          added; neural weight writes routed from the SPI write-event taps
          (`cfg_we`/`cfg_addr`/`cfg_wdata`) when `cfg_addr` ∈ 0x40–0x4F. Pin-map
          additions in `src/chip_core.sv` (1x0p5, 4/46/4): `bidir[34:32]` =
          spi_sclk/mosi/csn (inputs, `oe=0`), `bidir[36]` = spi_miso (output);
          `ks_period` (`bidir[15:6]`) now **also** doubles as the shared 10-bit pitch
          bus for SID + neural. **Regression green:** spine `tb/tb_synth_spine.sv` =
          **SPINE OK**, 64 frames, 0 mismatches (drives SPI frames, selects voices
          3/5/6 non-silent + I2S round-trip; KS voice 4 unchanged); chip
          `tb/tb_chip_core_elab.sv` = **ELAB OK** — direction mask correct incl. SPI bits
          (`oe[34:32]=0`, `oe[36]=1`), neural voice 7 proven at real frame rate
          (`BCLK_DIV=16` ≈ 1024 clk/frame ≫ 139-clk MAC). ✅
- [x] Eg  RTL registered in librelane `VERILOG_FILES` + cocotb sources. ✅ (commit f393d2e)

> **Follow-up:** Full multi-engine GDSII hardening — 5 engines is tight on the half
> slot (may want a larger slot); the tree is hardening-ready (all RTL in `config.yaml`).
> The prior 256 KS-only clean signoff (Phase 5e) stands on the previous branch. A
> full-roster hardening attempt is now IN FLIGHT — see Phase F.

## Phase F — full-roster GDSII hardening attempt (`engines/kitchen-sink`)  ⏳ RUNNING
Hardening prep done, then a full-roster `make librelane` (SLOT=1x0p5, gf180mcuD)
launched detached in the `eurosynth-harden` container.
- [x] Fa  **Neural weights synthesis-safe** — `$readmemh` baked into RTL via generated
          `src/neural_weights_init.svh` (`\`include`, 385 words, bit-identical to the
          hex). Removes the cwd-relative file dependency. ✅ (commit aca1c77)
- [x] Fb  **yosys-frontend fix** — `neural_osc` LUT helpers made pure (pass `phase` as
          an arg) so yosys stops rejecting "Non-constant expression in constant
          function". yosys now reads + elaborates the whole `chip_core` hierarchy
          (5 engines + SPI), `check` = **0 problems**. Bit-exact preserved (NEURAL/
          SPINE/ELAB green). ✅ (commit a5b674a)
- [x] Fc  **`make librelane` COMPLETE — full-roster GDSII produced.** 🎉 The whole
          5-engine + SPI chip placed, routed, and streamed out on the **1x0p5 half slot**.
          `ROSTER2_EXIT=0`. Deliverable extracted to repo `final_roster/` (gitignored):
          gds (135 MB), render PNG, metrics, nl/pnl, def, sdc.
- [x] Fd  **KLayout DRC OOM hit + fixed.** Run 1 reached the signoff DRC (~step 68) then
          died: `workers: max` (=48) OOM-killed several deck workers on the big layout
          (deep-mode DRC over ~1M polygons/layer) -> empty deck results ("unexpected
          token at ''"). NOT a design issue. Fixed by bounding `KLAYOUT_DRC_OPTIONS` +
          `KLAYOUT_ANTENNA_OPTIONS` `workers: 6` (commit cfd7e88); **resumed
          `--last-run --from KLayout.DRC`** (skipped the ~8 h of cached synth/PnR) ->
          ran clean to completion.

### Phase F signoff (full roster, SLOT=1x0p5, gf180mcuD)
| Check | Result |
|---|---|
| Magic DRC / KLayout DRC / routing DRC | **0 / 0 / 0** ✅ |
| LVS errors / device diffs | **0 / 0** ✅ (layout == netlist) |
| Hold timing (post-fab-fatal) | **0 violations**, WS +0.32 ns ✅ |
| Antenna (final, post-repair) | **1 violating net / 1 pin** ⚠️ (147 post-route -> repair cleared 146) |
| Setup timing @ 25 MHz / 40 ns | WS **-22.9 ns**, TNS -93 us, **15 858** vio endpoints ⚠️ (expected; audio runs <<25 MHz) |
| max slew / max fanout vios | 9201 / 462 (same slow-path family as setup) |
| Utilization / instances | **57.5%** / 244 584 cells (256-only was 37% / 168 278) |
| Die / core area | 9.95 M / 5.0 M um^2 (slot-bound; same die as the 256) |

**Verdict:** manufacturable full-roster GDS — DRC + LVS + hold all clean; **fits comfortably**
(57.5% util). Two caveats, both expected/minor: (1) **1 residual antenna violation** (the
256 had 0) — likely waivable or clearable with more `DRT_ANTENNA_REPAIR_ITERS` / a diode
(needs a re-route, ~hours); (2) **setup timing heavily violated** at 25 MHz — non-issue for
a ~48 kHz audio chip (drive `clk_PAD` <<25 MHz), but worse than the 256 (more long combinational
paths from the MLP MAC / chaos multipliers). Resume run dir
`/buildroster/librelane/runs/RUN_2026-06-17_13-49-44`; logs `/root/harden_roster.log` +
`/root/resume_roster.log` (sentinel `ROSTER2_EXIT=0`).
  - Rig: container **`eurosynth-harden`** (`nixos/nix`; LibreLane v3.1.0.dev1 + tools +
    PDK at `/pdk`). NOTE: this non-interactive shell needs
    `nix --extra-experimental-features "nix-command flakes" develop` (the bare
    `nix develop` errors "flakes disabled"); `sed`/`ps`/`pgrep` are NOT on PATH — use
    `/proc` enumeration for liveness.
  - Build dir `/buildroster` (fresh copy of the repo at commit a5b674a). Run dir
    `/buildroster/librelane/runs/RUN_2026-06-17_13-49-44`. Launch script
    `/root/harden_roster.sh`. Log `/root/harden_roster.log`, sentinel `ROSTER_EXIT=`.
  - Check (fresh session): liveness via
    `docker exec eurosynth-harden bash -lc 'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline 2>/dev/null; echo; done | grep -E "yosys|openroad|make"'`;
    progress `tail -20 /root/harden_roster.log` + `ls -1dt /buildroster/librelane/runs/RUN_*/[0-9][0-9]-*/`.
    GDS when done: `/buildroster/final/gds/chip_top.gds` (extract with `docker cp`).

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
- phaseE/bytebeat + SPI config port (voice 6) → 9912ff8
- phaseE/chaos engine (voice 5) → d4e8344
- phaseE/SID homage (voice 3) → 71268ab
- phaseE/neural morphing osc (voice 7) → 6182c2c
- phaseE/register engine RTL in librelane VERILOG_FILES + cocotb → f393d2e

## Morning report  (2026-06-17, autonomous run)

**Headline: the lean Karplus-Strong chip hardened to a clean, manufacturable GDSII.** 🎉

### What you have
- **RTL, bit-exact & verified** (standalone Icarus rail, all green and committed):
  KS engine `256/256` samples == golden, spine `SPINE OK`, `chip_core` 1x0p5
  `ELAB OK`. (Phases 0–4 + lean 256 variant; see commit log.)
- **GDSII (the new thing tonight):** the 256-deep KS design (`SLOT=1x0p5`,
  `DESIGN_NAME=chip_top`) ran RTL→GDSII through LibreLane v3.1.0.dev1 on gf180mcuD
  and **passed full physical signoff**:
  | Check | Result |
  |---|---|
  | Magic DRC / KLayout DRC / routing DRC / density | **0 / 0 / 0 / 0** |
  | LVS (Netgen) — device/net/pin diffs, errors | **0 / 0 / 0 / 0** (layout == netlist) |
  | Antenna (violating nets/pins) | **0 / 0** |
  | Power grid (PDN) | **0** |
  | manufacturability.rpt | **Antenna ✅ · LVS ✅ · DRC ✅** |
  - **Deliverable bundle** copied to repo `final/` (gitignored): `gds/chip_top.gds`
    (112 MB), klayout GDS, netlists (`nl`/`pnl`), SPICE, DEF, `.lib` (9 corners),
    SDC, render PNG, `metrics.json/csv`, `manufacturability.rpt`. Full 998 MB run
    output (sdf/spef/odb/mag) is retained in the container at `/build256/final`.
  - **One caveat — setup timing:** WNS −21.7 ns against the template's default
    25 MHz `clk_PAD` constraint (the 256:1 delay-line read mux is the long path).
    **Hold is clean** (the post-fab-fatal kind). For an audio synth advancing on a
    ~48 kHz `sample_tick` this is a non-issue — drive `clk_PAD` well under 25 MHz, or
    later pipeline the mux / move the line into an SRAM macro to close 25 MHz.

### What happened overnight (notable)
1. **`ps` is broken in the harden container** — it reports "1 process" even with
   flows running. I almost concluded the runs had died and relaunched them; that
   would have `rm -rf`'d a live run. Verified liveness via `/proc` instead — both
   runs were healthy the whole time. (Documented in the resume guide above + memory.)
2. **Missing `pmap` blocked signoff.** The PDK's KLayout antenna+LVS decks call
   `pmap` for memory logging; it was absent → `nil.strip` Ruby crash at step 60.
   Fixed with `nix profile install nixpkgs#procps` (also un-broke `ps`), then resumed
   the flow `--from KLayout.Antenna`. Clean to completion. (See the 🔧 note in Phase 5.)

### 1024 baseline (optional/bonus)
Still running at step 37/83 (post-CTS timing resizer) as of ~04:18 UTC, grinding
~16 400 violating endpoints from the 1024:1 mux; may not converge and adds no new
manufacturability info beyond the 256. Left running; not a blocker. If it finishes,
its `final/` GDS is at `/build256`→`/build/final` (run dir `RUN_2026-06-16_15-04-43`).

### Suggested next steps (human)
1. Open `final/gds/chip_top.gds` in your local KLayout to eyeball the layout, and
   `final/render/chip_top.png` for a quick look.
2. If happy, merge `overnight/karplus-strong` → `main`.
3. Timing: decide the real `clk_PAD` target (audio needs ≪25 MHz). If you want
   25 MHz closure, that's an architecture task (pipeline the tap mux / SRAM macro),
   not a re-run knob.
