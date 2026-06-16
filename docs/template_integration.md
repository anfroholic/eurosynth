# Template integration reference (wafer.space gf180mcu-project-template)

Durable capture of the template recon so a fresh session does NOT need to re-clone
and re-read it. Reference clone lives at the **sibling** path
`C:/Users/anfro/Documents/GitHub/gf180mcu-project-template` (NOT inside this repo).

> **TARGET SLOT: `1x0p5` (half slot).** Changed from the original `1x1`. See pad
> budget below — this is the single most important consequence.

---

## Slot pad budgets (from template `src/slot_defines.svh`)

| slot         | INPUT pads | BIDIR pads | ANALOG pads |
|--------------|-----------:|-----------:|------------:|
| 1x1 (old)    | 12         | 40         | 2           |
| **1x0p5 (NEW target)** | **4** | **46** | **4** |
| 0p5x1        | 4          | 44         | 6           |
| 0p5x0p5      | 4          | 38         | 4           |

**Consequence for our design — pad category split is SOFT, only the total budget
is hard.** The 46 bidir pads are direction-configurable per bit (`bidir_oe`/
`bidir_ie`), so any of them can be an INPUT or an OUTPUT. Net I/O to assign
freely = **4 + 46 + 4 = 54 signal pads** (≈50 usable for logic; analog is
separate). So "only 4 dedicated input pads" is NOT a constraint: put
`voice_sel[2:0]` + `bypass_en` on the 4 input pads, and place KS `pluck`/`period`
(and any future CV/gates/SPI) on **bidir pads set as inputs** — we have ample
room. Design rule: assign functions to whatever pads are convenient, just stay
within 54 total. The engine DSP is slot-independent; only `chip_core` pad wiring
and the NOTES pin map change.

---

## Build / sim invocation for 1x0p5
- Hardening (human PDK session): `SLOT=1x0p5 make librelane`
- cocotb sim (human PDK session): `SLOT=1x0p5 make sim`
- `make defines` writes `src/generated_defines.svh` with `` `define SLOT_1X0P5 ``.
- LibreLane configs picked up: `librelane/slots/slot_1x0p5.yaml` +
  `librelane/macros/macros_${MACROS}.yaml` + `librelane/config.yaml`.

---

## The user core contract (our `chip_core.sv` must match EXACTLY)
Top module is **`chip_top`** (`src/chip_top.sv`); it instantiates our core as
`i_chip_core` with these exact param/port names (do NOT rename):
```systemverilog
chip_core #(.NUM_INPUT_PADS(...), .NUM_BIDIR_PADS(...), .NUM_ANALOG_PADS(...))
  i_chip_core (
    .clk, .rst_n,
    .input_in, .input_pu, .input_pd,
    .bidir_in, .bidir_out, .bidir_oe, .bidir_cs, .bidir_sl, .bidir_ie,
    .bidir_pu, .bidir_pd,
    .analog
    // + VDD/VSS under `USE_POWER_PINS
  );
```
Our existing `src/chip_core.sv` ALREADY matches this contract and is SRAM-free
(the template's example core had two SRAMs; ours does not).

## Verilog file lists to update when adding RTL
- `librelane/config.yaml`: `VERILOG_FILES:` list (currently `../src/chip_top.sv`,
  `../src/chip_core.sv`). Add `../src/synth_spine.sv` and `../src/ks_engine.sv`.
  `DESIGN_NAME: chip_top`. Clock: `CLOCK_PORT: clk_PAD`, `CLOCK_PERIOD: 40` (25 MHz).
- `cocotb/chip_top_tb.py` (~lines 117-118): append the same RTL sources to the
  non-GL `sources` list. Toplevel `chip_top`. Test drives whole pad vectors:
  `dut.clk_PAD`, `dut.rst_n_PAD`, `dut.input_PAD` (write), `dut.bidir_PAD` (read).
  cocotb cannot write individual bits of a vector — drive the whole `input_PAD`.

## SRAM removal (needed for hardening config consistency; harmless for sim)
Our core has no SRAM, so for `make librelane` to not look for missing instances,
remove from the template copy:
- the SRAM macro block + `PDN_MACRO_CONNECTIONS` for `i_chip_core.sram_0/sram_1`
  in `librelane/macros/macros_5v.yaml` (and `macros_3v3.yaml`);
- the SRAM model source line in `cocotb/chip_top_tb.py` (~line 125).
The SRAM `` `define `` plumbing in `chip_top.sv` can stay (unused/harmless).

## Hard gotchas
1. `make defines` MUST run before any build — RTL `` `include "generated_defines.svh" ``
   (then `slot_defines.svh`). That file is gitignored/regenerated.
2. `` `default_nettype none `` is in force — declare every net; restore `wire` at EOF.
3. Do NOT rename pad-ring generate blocks in `chip_top.sv` (`bidir`, `inputs`,
   `analog`, `*_pads`) — the slot YAMLs reference them by instance path.
4. Keep tapeout IP instances in `chip_top.sv` (`qrcode_id`, `shuttle_id`,
   `project_id`, `marker` — marked "necessary for tapeout"). The `logo` is optional.
5. Keep `IGNORE_DISCONNECTED_MODULES` (output-only bidir pads leave `.Y` unused).
6. The template's `make sim`/`make librelane` need the **PDK** (multi-GB `ciel`
   fetch) + nix toolchain → **human PDK session**, not the light Docker sim image.

## What our light Docker sim CAN verify (no PDK)
Standalone Icarus on pure RTL: `src/synth_spine.sv`, `src/ks_engine.sv`, their
TBs in `tb/`, and a `chip_core` elaboration (it has no PDK deps; feed it the
1x0p5 pad-count params). `chip_top` (pad ring) needs PDK pad models → not tonight.
