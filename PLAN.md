# Eurosynth — Overnight Execution Plan

This document is the operating manual for an **unattended** build session. It is
written so a fresh Claude session (or you, in the morning) can pick it up cold.
Read [NOTES.md](NOTES.md) first for *why* the design looks the way it does; this
file is *how* we build the next piece without a human in the loop.

> ### 📌 Live status & key changes (read before resuming)
> - **Target slot is `1x0p5`** (half slot), NOT 1x1. Pad budget 4 in / 46 bidir /
>   4 analog; category split is soft (bidir pads are direction-configurable), only
>   the ~54-pad total is hard. All build commands use `SLOT=1x0p5`. See
>   [docs/template_integration.md](docs/template_integration.md).
> - **[PROGRESS.md](PROGRESS.md) is the live source of truth** for what's done and
>   the (reordered) execution sequence. As of last update: Phase 0 + the
>   Karplus-Strong engine (spec, model, RTL, golden TB — **bit-exact, 0
>   mismatches**) are DONE and pushed. Next: wire KS into the spine + the 1x0p5
>   `chip_core` pin map (Phase 3), then template import (Phase 1).
> - **Verification rail:** standalone Icarus only (no PDK). Full `chip_top` cocotb
>   + `make librelane` GDSII = human PDK session.

---

## 0. TL;DR — what the human has to do

1. **Enable bypass-permissions mode** so tool calls don't prompt while you sleep:
   press **Shift+Tab** to cycle the permission mode until it says *bypass
   permissions*, **or** relaunch Claude Code with `--dangerously-skip-permissions`.
   (Tonight's Phase 0 still ran in normal mode while you were awake — that was on
   purpose, to surface the one-time Docker + `git push` credential checks.)
2. Type **`go`** (or just leave it — see §11 for the auto-resume safety net).
3. Go to bed. In the morning, do the **Morning Checklist (§10)**.

Everything below this line is for the autonomous run.

---

## 1. Goal & current state

**Goal of this session:** integrate the design into the wafer.space template,
build the **Karplus-Strong** plucked-string engine as the first real voice,
verify it end-to-end in simulation, wire it into the spine, and leave the tree
**ready for `make librelane`** (GDSII) — but do NOT run GDSII tonight.

**Locked-in decisions (from tonight's Q&A):**
| Decision | Choice |
|---|---|
| Overnight scope | **RTL + simulation only**; prep GDSII, don't run it |
| First engine | **Karplus-Strong** plucked string |
| Build environment | **Docker** (sim image `eurosynth-sim`) |
| Git | **Commit and push to origin** (work on a branch) |
| Permissions | **Bypass mode** for the unattended window |

**Starting point (verified in Phase 0 tonight):**
- Spine logic ([synth_spine.sv](synth_spine.sv)) simulates green under Icarus.
- `chip_core` ([chip_core.sv](chip_core.sv)) wires the spine to the pad interface.
- Self-checking TB ([tb_synth_spine.sv](tb_synth_spine.sv)) decodes the I2S
  stream and matches every frame.

---

## 2. Orchestration model (how the autonomous run is structured)

**Principle:** sub-agents do small, well-scoped chunks; the **main context
verifies** every chunk by actually running the simulator before moving on. A
sub-agent that *claims* success but whose output fails the sim is rolled back,
not trusted.

```
  main (orchestrator + verifier)
    │  spawn 1 sub-agent per chunk, with a tight prompt + acceptance criteria
    ├──► sub-agent: writes/edits a few files, self-checks, returns a report
    │  main: runs the relevant sim itself (bash scripts/sim.sh ...)
    │        ── pass ─► commit + push, mark chunk done, next chunk
    │        ── fail ─► feed the exact error back to a fix-up sub-agent (max 2
    │                    retries), then re-verify
    └──► repeat
```

Rules for the orchestrator (main context):
- **Never** mark a chunk complete on a sub-agent's say-so. Re-run the sim.
- Keep each sub-agent's blast radius to **1–3 files**. Small chunks = easy verify.
- After each green chunk: `git add -A && git commit && git push`. Small commits.
- If a chunk fails twice, **stop and write the blocker into §12** rather than
  thrash — leave it for the human. Do not invent workarounds that defeat the
  verification (e.g. don't loosen a self-checking TB just to make it pass).
- Progress is tracked in **[PROGRESS.md](PROGRESS.md)** (created on first run):
  one line per chunk with status + commit hash. This is the resume anchor (§11).

---

## 3. The Docker environment (beginner-friendly)

You have never done this before, so here is exactly what each piece is and does.

### 3.1 The simulation image
We built a small Docker image called **`eurosynth-sim`** from
[docker/Dockerfile.sim](docker/Dockerfile.sim). It contains Icarus Verilog
(`iverilog`/`vvp`), Python 3, and **cocotb** (the python verification framework
the template uses). That's all simulation needs. It deliberately does **not**
contain the heavy GDSII toolchain — that's a separate step (§9).

To (re)build it (only needed if the Dockerfile changes):
```bash
docker build -t eurosynth-sim -f docker/Dockerfile.sim .
```

### 3.2 Running anything in the sim image
There is one wrapper, [scripts/sim.sh](scripts/sim.sh), so nobody has to
remember the Windows↔Linux path-mount syntax. It mounts the repo at `/work`
inside the container and runs whatever you pass it:
```bash
# sanity check the toolchain
bash scripts/sim.sh iverilog -V

# run the standalone spine testbench (files at repo root, current layout)
bash scripts/sim.sh bash -lc \
  'iverilog -g2012 -o /tmp/spine.vvp synth_spine.sv tb_synth_spine.sv && vvp /tmp/spine.vvp'

# after template integration, run the cocotb flow the template ships
bash scripts/sim.sh make sim
```
A green spine run prints: `==== SPINE OK: every decoded sample matched ====`.

---

## 4. Repo layout: current → target

**Current (handoff):** four loose files at the repo root.

**Target (after Phase 1 template integration):**
```
eurosynth/
├── src/
│   ├── synth_spine.sv          # moved from root
│   ├── chip_core.sv            # moved from root; replaces template's example core
│   ├── ks_engine.sv            # NEW — Karplus-Strong engine (Phase 2)
│   └── generated_defines.svh   # generated by `make defines`
├── tb/
│   ├── tb_synth_spine.sv       # moved from root
│   └── tb_ks_engine.sv         # NEW — KS self-checking TB (Phase 2)
├── cocotb/                     # from template — `make sim` harness
├── librelane/config.yaml       # from template — VERILOG_FILES lives here
├── models/ks_ref.py            # NEW — golden reference model (Phase 2)
├── docs/karplus_strong.md      # NEW — engine design spec (Phase 2)
├── scripts/sim.sh              # sim wrapper
├── docker/Dockerfile.sim       # sim image
├── NOTES.md  PLAN.md  PROGRESS.md
```

> The template is the wafer.space **gf180mcu-project-template**. Its native flow
> is Nix-based; its make targets are `sim` (cocotb+iverilog), `librelane`
> (RTL→GDSII), `clone-pdk`, `defines`, plus viewer targets. We only need `sim`
> tonight. The top wrapped by cocotb is `chip_top`; our `chip_core` is the user
> core it instantiates.

---

## 5. Phase & chunk plan

Each chunk lists: **who** (sub-agent), **does what**, **acceptance** (how main
verifies). Phases are sequential; chunks within a phase mostly are too.

### Phase 0 — De-risk & baseline  *(done tonight, while human awake)*
- [0a] Build `eurosynth-sim` image. **Accept:** `iverilog -V` runs in container.
- [0b] Run the spine TB in the container. **Accept:** "SPINE OK" line printed.
- [0c] Commit baseline + scaffolding, create branch `overnight/karplus-strong`,
  push to origin. **Accept:** `git push` succeeds (credentials proven).

### Phase 1 — Template integration
- [1a] **Recon agent:** clone the wafer.space template into a scratch dir, read
  its `src/` example core, `librelane/config.yaml`, and `cocotb/chip_top_tb.py`.
  **Return:** the exact module name + port list the harness expects, the
  `VERILOG_FILES` format, and how `chip_core` plugs into `chip_top`. **Accept:**
  report names real files/ports (main spot-checks against the cloned tree).
- [1b] **Integration agent:** copy template files into the repo, move
  `synth_spine.sv`/`chip_core.sv` into `src/`, move TB into `tb/`, reconcile
  `chip_core` ports with what `chip_top` expects, add both `.sv` files to
  `VERILOG_FILES` in `librelane/config.yaml`. Remove the example SRAM macros per
  NOTES §"Integrating". **Accept (main runs):**
  `bash scripts/sim.sh make sim` elaborates and runs (cocotb harness drives the
  pads; design responds — at minimum bclk toggles, no elaboration errors).
- [1c] **Regression:** standalone spine TB still green from `src/`/`tb/` paths.
  **Accept:** "SPINE OK".

### Phase 2 — Karplus-Strong engine (the real work)  *(spec in §6)*
- [2a] **Spec agent:** write [docs/karplus_strong.md](docs/karplus_strong.md):
  algorithm, fixed-point format, exact port list (must satisfy the engine
  contract in NOTES), parameters, and the golden-vector test plan. **Accept:**
  ports match the contract (`clk,rst_n,sample_tick,...,sample[15:0]`); spec is
  internally consistent.
- [2b] **Model agent:** write `models/ks_ref.py` — a bit-exact integer reference
  of the RTL (same delay length, same fixed-point feedback/decay), emitting a
  golden sample vector to `models/ks_golden.txt` for a fixed seed/period/decay.
  **Accept (main runs):** `bash scripts/sim.sh python3 models/ks_ref.py` writes
  a non-trivial vector (oscillates then decays).
- [2c] **RTL agent:** write `src/ks_engine.sv` implementing the spec. Advances
  ONLY on `sample_tick`; output stable between ticks; signed 16-bit. **Accept
  (main runs):** elaborates clean under iverilog (`-g2012`, no errors/latches).
- [2d] **TB agent:** write `tb/tb_ks_engine.sv` — self-checking against
  `models/ks_golden.txt` (read with `$readmemh`/`$fscanf`), comparing the
  engine's `sample` at each `sample_tick`. **Accept (main runs):**
  `iverilog ... && vvp` prints a clear PASS with 0 mismatches; main confirms the
  PASS criterion isn't trivially true (i.e. it really compares N>0 samples).

### Phase 3 — Spine integration + regression
- [3a] **Wire-in agent:** instantiate `ks_engine` in `src/synth_spine.sv`, add a
  mux case (`3'd4: sel_sample = ks_out;`), and expose its `pluck`/`period`
  controls through reserved input pins in `src/chip_core.sv` (per NOTES pin map,
  using `input_in[11:4]`). Update the NOTES pin-map table to match.
  **Accept (main runs):** (1) existing spine TB still "SPINE OK" (no
  regression); (2) a quick added check drives `voice_sel=4` and sees the KS
  output reach the serializer.
- [3b] **cocotb agent:** extend the template's cocotb test to select the KS
  voice and confirm audio frames come out. **Accept:** `make sim` green.

### Phase 4 — GDSII prep & docs (NO hardening run)
- [4a] **Config agent:** confirm `librelane/config.yaml` `VERILOG_FILES` lists
  all three RTL files, `DESIGN_NAME`/top is correct, SRAM macros removed, clock
  defined. **Accept:** main reads config and cross-checks against `src/`.
- [4b] **Docs agent:** update [NOTES.md](NOTES.md) status + engine roadmap
  (KS done), and write the `make librelane` runbook results expectations.
  **Accept:** docs consistent with the tree.
- [4c] **Final verify (main):** full sim suite green, push, write the morning
  report into PROGRESS.md.

---

## 6. Karplus-Strong engine — design spec (authoritative)

Karplus-Strong models a plucked string with a **delay line + lowpass + decay**:

- A delay line of length **N** samples holds the "string". Pitch ≈ `fs / N`.
- On each `sample_tick`: the output is the oldest sample; the new sample pushed
  into the line is a **lowpass** of the two oldest samples, scaled by a **decay**
  factor < 1 so the note fades.
- A **pluck** strobe re-seeds the delay line with a burst (noise or an impulse),
  which is the attack transient.

**Engine contract (from NOTES §"engine contract") — non-negotiable:**
```systemverilog
module ks_engine (
    input  wire               clk,
    input  wire               rst_n,        // active low
    input  wire               sample_tick,  // advance state ONLY here
    input  wire               pluck,        // 1-tick strobe: re-excite the string
    input  wire [9:0]         period,       // delay length N (sets pitch)
    output wire signed [15:0] sample        // current output, held between ticks
);
```

**Fixed-point / implementation guidance:**
- Delay line: a register array `signed [15:0] line [0:NMAX-1]` with `NMAX` = the
  max `period` (e.g. 512 or 1024 → low bass notes). A small RAM is fine; do NOT
  pull in the gf180 SRAM macro yet (keep it as flops/inferred RAM for v0 to keep
  the flow simple — note area cost in the spec).
- Lowpass + decay (classic integer KS): `new = ((a + b) * DECAY_NUM) >> DECAY_SH`
  where `a`,`b` are the two oldest samples. Pick `DECAY_NUM/2^DECAY_SH` slightly
  below 0.5 each (e.g. average then ×0.99) so it decays. Keep it a shift/add —
  no real multiplier needed if you choose power-of-two-friendly constants; if a
  multiply is unavoidable keep it one small signed multiply.
- Seed on `pluck`: simplest deterministic seed is a **+full / −full square or a
  ramp** across the active `period` (deterministic = easy to golden-test).
  An LFSR noise seed sounds better but verify it bit-exactly against the model.
- Output must be **stable between ticks** (registered), per the contract.

**The model (`models/ks_ref.py`) must be bit-exact to the RTL** — same integer
math, same truncation/rounding, same seed — so `tb_ks_engine.sv` can demand a
0-mismatch compare, not a tolerance. This is the whole point: a self-checking,
golden-vector test, exactly like the spine TB already does for the serializer.

---

## 7. Verification strategy

Three independent checks, cheapest first:
1. **Standalone iverilog TBs** (`tb/tb_*.sv`) — fast, no PDK, run on every chunk.
   These are *self-checking* (decode/compare, print PASS/FAIL + mismatch count).
2. **cocotb `make sim`** — exercises the real pad interface like the template's
   harness; catches integration/pinout bugs the standalone TBs can't.
3. **Elaboration cleanliness** — no inferred latches, no width-mismatch warnings,
   no undriven nets (`chip_core` already ties off unused inputs — keep it that
   way for new pins).

Main context runs #1 and #3 after every chunk and #2 after integration chunks.

---

## 8. Git workflow

- Branch: **`overnight/karplus-strong`** (created in Phase 0). `main` holds only
  the clean baseline.
- One commit per green chunk. Message format:
  `phaseN/chunk: <what> — verified <which sim>`.
- Push after each commit so morning review is possible from anywhere.
- Commit trailer on every commit:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Do **not** force-push, rebase, or touch `main`.

---

## 9. The `make librelane` runbook (for the human, LATER — not tonight)

This is the RTL→GDSII step. It is **slow, heavy, and out of scope for the
unattended run** because the first run compiles a large toolchain and the PDK is
multi-GB — not safe to attempt blind overnight. Do this *with eyes on it*, ideally
together. Two paths; pick one:

### Path A — LibreLane's own Docker mode (matches your Docker preference)
1. Install LibreLane locally (needs Python): `pip install librelane`
2. Make sure Docker Desktop is running.
3. From the repo root, harden the **1x0p5** design in a container LibreLane
   manages (run where `make` exists — i.e. WSL2 Ubuntu — since the slot configs
   are assembled by the Makefile):
   ```bash
   SLOT=1x0p5 LIBRELANE_OPTS=--dockerized make librelane
   ```
   The first invocation pulls the toolchain image (large, one-time). `make`
   auto-runs `clone-pdk` + `defines` first.
4. Results land in `librelane/runs/<timestamp>/`; final views copy to `final/`.

### Path B — the template's blessed Nix flow (inside WSL2 Ubuntu)
The template is built around Nix. If Path A fights you, this is the reference:
1. In WSL2 Ubuntu: install Nix + LibreLane per
   `https://librelane.readthedocs.io/en/latest/installation/nix_installation/`.
2. `make clone-pdk` (pulls the gf180mcuD PDK via Ciel — multi-GB, one-time).
3. `nix-shell` (drops you into a shell with the whole toolchain on PATH).
4. `SLOT=1x0p5 make librelane` (the actual hardening; the first run is slow).
5. View results: `SLOT=1x0p5 make librelane-openroad` or `... librelane-klayout`.

> Tonight's job is to make sure that when you run this, `librelane/config.yaml`
> already lists every RTL file and the design elaborates — so the *only* new
> variable is the GDSII tooling itself, not the design.

---

## 10. Morning checklist (human)

1. `git log --oneline overnight/karplus-strong` — skim the chunk commits.
2. Open [PROGRESS.md](PROGRESS.md) — read the status table + any §12 blockers.
3. Run the sims yourself to trust-but-verify:
   ```bash
   bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/spine.vvp src/synth_spine.sv tb/tb_synth_spine.sv && vvp /tmp/spine.vvp'
   bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/ks.vvp src/ks_engine.sv tb/tb_ks_engine.sv && vvp /tmp/ks.vvp'
   bash scripts/sim.sh make sim
   ```
   Want to *see* the waveform? `bash scripts/sim.sh make sim-view` (needs an X
   server on Windows) or open the `.vcd`/`.fst` in your local GTKWave.
4. If everything's green and you like it: merge `overnight/karplus-strong` → `main`.
5. When ready for silicon layout: do the **§9 `make librelane` runbook** with me.

---

## 11. Resume instructions (if the run is interrupted)

If a fresh session has to continue this:
1. Read this file, then [PROGRESS.md](PROGRESS.md) — the last `[x]` line + commit
   hash is where we are.
2. `git checkout overnight/karplus-strong` and confirm `git log` matches PROGRESS.
3. Rebuild the image if needed: `docker build -t eurosynth-sim -f docker/Dockerfile.sim .`
4. Re-run the last completed chunk's acceptance sim to confirm a green starting
   point, then proceed to the next unchecked chunk in §5.

**Auto-resume safety net:** the orchestrator may schedule a wake-up so the build
continues even if a turn ends. PROGRESS.md is the single source of truth for
"what's done" — always reconcile against `git log` before doing new work.

---

## 12. Blockers / open questions (append-only; the run writes here)

- *(none yet — the autonomous run appends any hard stops here instead of
  thrashing, so the human can unblock in the morning)*

### Known non-goals for tonight (do NOT attempt)
- Running `make librelane` / any GDSII hardening (§9 is human-run).
- The neural oscillator engine (headliner) — needs offline weight training.
- SPI config port, real CV/gate input conditioning, analog/TRNG pads.
- Re-adding SRAM macros (KS v0 uses inferred flops/RAM).
