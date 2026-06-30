# Hierarchical hardening: turning engines into macros

> Living design doc + the seed for a starter-kit writeup. Plain-language on purpose:
> it should make sense to someone who has never done a hierarchical ASIC flow.

## Why we're doing this

The flat flow (synthesize *everything* into one big netlist, place & route it all at
once) hit two walls on `chip_top`:

1. **Timing/DRV won't close at the slow corner.** A handful of huge-fanout nets
   (250–1543 loads) inside the engines get scattered across the whole pad-limited
   die, so their wires are long, their slews blow past the limit, and ~10k max-slew
   violations survive to signoff. Global knobs (placement density) just trade the
   slew for routing congestion.
2. **Iteration takes ~9–14 hours.** A single change means re-running the entire
   chip — synthesis, place, route, and a multi-hour static-timing pass over 9 PVT
   corners. Detailed routing on the congested layout sometimes never finishes.

Both have the same cure: **stop solving the whole chip at once.** The design is
already a set of independent engines. If we harden each big engine *by itself* —
small area, its own routing, its own timing closure — its high-fanout nets stay
local (short wires → good slew) and its run is small and fast. Then the top level
just drops the finished engines in as pre-built blocks and wires up the thin glue.

## What a "macro" is in this flow

This template already does hierarchical integration — you just may not have noticed.
The wafer.space marker blocks (`qrcode_id`, `shuttle_id`, `logo`, …) in
`librelane/macros/macros_5v.yaml` are pre-hardened blocks dropped into the chip. The
flow integrates each one from **four files + a placement**:

| Artifact | What it is | Who reads it |
|---|---|---|
| `gds` | the actual layout (polygons) | final chip assembly / streamout |
| `lef` | the *abstract*: outline, pin locations, routing blockages (internals hidden) | placement & routing at the top |
| `lib` | a timing model of the block (per PVT corner) | static timing analysis at the top |
| `vh`  | a black-box Verilog declaration (ports, no body) | synthesis at the top |
| `instances:` (in yaml) | where to place it: `location: [x, y]`, `orientation` | floorplanning |

So "make an engine a macro" = **produce those four artifacts for the engine, then add
it to a macros yaml with a placement.** We generate them ourselves (by hardening the
engine) instead of downloading them.

## The design, profiled

Relative size + where the troublesome structures live (from the flat netlist):

| Engine | Size | Big / high-fanout structure | Macro it? |
|---|---|---|---|
| `u_ks` (Karplus–Strong) | **largest** | `ks.line` delay line (~20k nets) | **yes** |
| `u_neural` | large | `mem` (385 words) + MAC datapath | **yes — pilot** |
| `u_chaos` | large | Lorenz state `lx/ly/lz` | **yes** |
| `u_sid`, `u_bb`, `u_spi` | small | — | no (leave flat at top) |
| spine glue, voice mux | tiny | — | no (stays at top) |

Only the big three are worth the per-block overhead. The small engines + the spine
glue stay flat in the top-level run.

## Plan (staged — prove it on one block first)

**Phase 1 — Pilot: `neural_osc` as a macro.** Chosen because it has the cleanest
interface (clk, rst_n, sample_tick, pitch[9:0], morph[7:0], w_we/w_addr/w_wdata,
sample[15:0]), we understand it best, and it has golden-vector verification to prove
the macro still behaves bit-exactly. Goal: get one engine all the way through
block-harden → abstract → top-integration before touching the others.

  1. **Block config** (`librelane/blocks/neural_osc/`): harden `neural_osc` alone with
     the standard (Classic) flow — *no padring* (pads belong only to `chip_top`),
     its own small die/core, its own clock, its own PDN. This run is small → fast,
     and closes timing for just this block.
  2. **Generate the four artifacts** into `ip/neural_osc/` (gds, lef, lib, vh).
  3. **Integrate at the top**: tell top-level synthesis to treat `neural_osc` as a
     black box, add it to the macros yaml with a `location`, route the glue.
  4. **Verify**: top-level gate-level sim still matches the golden vectors.

**Phase 2 — Roll out** the same recipe to `ks` and `chaos`.

**Phase 3 — Starter-kit writeup**: distill this doc + the working configs into an
educational guide for the wafer.space starter kit (what a macro is, why hierarchy,
the four artifacts, the gotchas we hit).

## Honest costs / risks (so expectations are set)

- This is a real flow change, not a config tweak. The first block-harden will need
  iteration (block die size, pin placement, PDN, clock margin).
- Each block needs its own power plan, and the top PDN must connect to the block's
  power pins.
- The top sees each engine only through its `.lib` — so a block must be *timing-
  characterized* (the harden produces per-corner `.lib`s; we must keep them in sync
  with the block RTL).
- Block boundaries must be registered (they are here — engines register their
  `sample` output and run off `sample_tick`), so cross-boundary paths are short.
- Payoff: each engine closes in a small fast run, and re-hardening one engine no
  longer means a full-chip run — which is what kills the 9–14 h iteration loop.

## Status / checklist

- [ ] Phase 1.1 — neural_osc block config drafted (`librelane/blocks/neural_osc/`)
- [ ] Phase 1.1 — block hardens cleanly (timing closes standalone)
- [ ] Phase 1.2 — four artifacts generated into `ip/neural_osc/`
- [ ] Phase 1.3 — integrated + placed at top; top routes
- [ ] Phase 1.4 — top gate sim matches golden vectors
- [ ] Phase 2 — ks, chaos
- [ ] Phase 3 — starter-kit writeup
