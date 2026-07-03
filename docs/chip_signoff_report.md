# eurosynth chip_top — signoff report

**Final run:** `librelane/runs/RUN_2026-07-03_01-07-23` (full 9-corner, no DEV overlay)
**Verdict:** ✅ **FULLY GREEN.** Setup, hold, **max-slew**, DRC, LVS, and antenna all pass across all 9 corners. The only remaining item is the known-benign I/O-pad max-cap (88–89/corner, all pad external-load artifacts — see below). Flow exits 0 and saves views.

Final worst slacks: setup **+5.51 ns**, hold **+0.235 ns**, max-slew **0**, all at the ss/ff worst corners.

(Earlier run `RUN_2026-07-02_22-24-00` was clean on everything except 24 ss clock-tree max-slew nets; the iteration log below tracks how those were closed.)

## Scorecard (9 corners)

| Check | Result |
|---|---|
| **Setup** | ✅ 0 violations all corners, worst **+8.53 ns** (max_ss) |
| **Hold** | ✅ 0 violations all corners, worst **+0.155 ns** (max_ff) |
| **DRC** (Magic + KLayout) | ✅ Passed |
| **LVS** (Netgen) | ✅ Passed |
| **Antenna** (OpenROAD + KLayout deck) | ✅ Passed |
| **Max Cap** | ⚠️ 93/corner — **all I/O-pad external-load artifacts** (pad drives the intended ~3.53 pF `OUTPUT_CAP_LOAD` vs a 0.2 pF internal-net limit); 0 internal-net violators. Non-fatal warning. |
| **Max Slew** | ⚠️ ss-only: 24 @ max_ss, 21 @ nom_ss, 12 @ min_ss; **0 at all tt/ff corners** |

## How we got here (this session)

Assembled all 5 pre-hardened engine macros (neural_osc, chaos, ks, sid, bytebeat) into `chip_top` via the hierarchical MACRO flow. Each kink resolved to a real, understood cause — **zero RTL changes**:

1. **Markers unresolved at lint** — LibreLane does not deep-merge the `MACROS` dict across files; a separate `engines.yaml` silently overrode the wafer.space markers. Fix: engines + markers in one dict (`macros_5v.yaml`).
2. **Setup −39.25 ns / 262 vios** — ~256 were the global **reset** path (`rst_n_PAD`, chip-wide fanout timed single-cycle). Fix: `set_false_path` on reset + engine-contract reg→reg multicycle → setup **+5→+13→+8.5 ns / 0**.
3. **274 max-slew + 3 KLayout antenna** — the chip never inherited the engine DRV recipe. Ported slew/cap over-repair margins (33/28), long-wire buffering (WL 300), CTS leaf clustering → **slew 274→~24**, and the reroute **absorbed all 3 antenna errors**.
4. **Fast-corner hold −0.44→−0.54 ns** — NOT reg-to-reg. All on `bidir_PAD[*] → u_neural/u_ks` paths. Root cause: **the chip's control inputs are asynchronous by design** — pitch (`bidir[15:6]`), pluck (`bidir[5]`), voice_sel (`input[2:0]`) are directly pad-strapped into the macros with no synchronizer; SPI pins are async→internally-2FF-synchronized. Hold-timing an async input against the core clock is not physical, and a hold margin bump made it worse (pinned input arrival can't be buffer-fixed). Fix: `set_false_path` (setup+hold) on the async control inputs — same class as reset. A one-sample (~20.8 µs) stale value on an async change is inaudible; the engines are all sample_tick-gated (~48 kHz). → **hold 0 violations all corners**.

## Remaining item → next run

**Clock-tree max-slew at ss corners (24 nets).** Every violator is a clock cell — `clkbuf_1_0_2_clk_PAD2CORE/Z` (6.31 ns) and `clkbuf_1_1_2` (5.47) are the root distribution buffers driving the clock across the ~3 mm die; the rest are `clkbuf_leaf_*` and macro `/clk` pins ~0.5 ns over the 3.0 ns limit at the slowest corner. Datapath `DESIGN_REPAIR_*` cannot fix these (clock nets are don't-touch for design repair) — this is a **CTS lever**. Note the clock is functionally fine: setup/hold both passed *using* these actual clock slews; the violation is a library max-transition guideline exceeded on 24 buffers at the worst corner.

**Change for the next run** (`librelane/config.yaml`): tighten the CTS DRV ceilings so the built tree keeps margin through the ss degradation —
- `CTS_MAX_SLEW: 0.1 → 0.08`
- `CTS_MAX_CAP: 0.14 → 0.10`
- (`CTS_SINK_CLUSTERING_SIZE` held at 8; watch skew/hold — hold margin is +0.155 ns, so verify it doesn't regress.)

If the two root buffers persist, follow up by splitting the pad→core clock route (more root-level buffering) rather than tightening clustering further.

## Iteration log

- **Run `RUN_2026-07-02_22-24-00`** (async-input false_path): setup/hold/DRC/LVS/antenna clean; 24 ss max-slew (all clock tree).
- **Run `RUN_2026-07-02_23-44-09`** (CTS_MAX_SLEW 0.1→0.08, CTS_MAX_CAP 0.14→0.10): hold/setup/DRC/LVS/antenna still clean (hold improved to +0.34 ns). Slew: leaves improved (nom_ss 21→14, min_ss 12→2) but **max_ss stuck at 24** — the 2 root buffers `clkbuf_1_x_clk_PAD2CORE` are UNCHANGED at 6.5/5.3 ns. Diagnosis: `CTS_ROOT_BUFFER` is already `clkbuf_16` (strongest), so it's not drive — the root clock net is UNBOUNDED length (`CTS_CLK_MAX_WIRE_LENGTH` was 0).
- **Run `RUN_2026-07-03_01-07-23`** (`CTS_CLK_MAX_WIRE_LENGTH: 0 → 300`): ✅ **max-slew 0 across all 9 corners** — the root clock nets got split with intermediate buffers as intended. Hold/setup/DRC/LVS/antenna all still clean. Setup eased +8.5→+5.5 ns from the added clock buffering (ample margin). **This is the final, fully-green signoff.**

## Note on submittability

The chip **passes signoff now** (all mandatory checks green; flow exits 0 and saves views). The residual max-slew is a **library max-transition guideline** exceeded on ~24 clock buffers at the single worst (ss) corner — the clock is functionally fine (setup/hold closed *using* these slews). The submitted roster shipped with comparable DRV residuals. Chasing it fully green is a quality/margin improvement, not a blocker.
