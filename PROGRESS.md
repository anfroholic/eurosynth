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
