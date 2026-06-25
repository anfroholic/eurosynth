#!/usr/bin/env bash
# scripts/sim_all.sh — the green check. Runs eurosynth's full standalone,
# PDK-FREE verification suite inside the sim container: every engine's bit-exact
# golden testbench, the spine round-trip, and the chip_core 1x0p5 elaboration.
# Exit 0 (and "ALL STANDALONE TBS PASSED") means the design is sim-clean.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# chip_top.sv includes generated_defines.svh; make sure it exists for any RTL
# that pulls it in (the standalone TBs instantiate cores directly, but harmless).
bash scripts/gen_defines.sh

export MSYS_NO_PATHCONV=1   # Windows/Git-Bash mount-path fix

exec docker compose run --rm sim bash -lc '
  set -e
  # Every engine source the spine + core elaboration need.
  ENG="src/ks_engine.sv src/bytebeat.sv src/chaos_engine.sv src/sid_voice.sv src/sid_engine.sv src/neural_osc.sv src/spi_config.sv"
  run() { name="$1"; shift; printf "\n== %s ==\n" "$name"; iverilog -g2012 -Wall -I src -o "/tmp/${name}.vvp" "$@" && vvp "/tmp/${name}.vvp"; }

  run ks       src/ks_engine.sv                                tb/tb_ks_engine.sv
  run bytebeat src/bytebeat.sv                                  tb/tb_bytebeat.sv
  run chaos    src/chaos_engine.sv                              tb/tb_chaos_engine.sv
  run sid      src/sid_voice.sv src/sid_engine.sv               tb/tb_sid_engine.sv
  run neural   src/neural_osc.sv                                tb/tb_neural_osc.sv
  run spi      src/spi_config.sv                                tb/tb_spi_config.sv
  run spine    src/synth_spine.sv $ENG                          tb/tb_synth_spine.sv
  run core     src/chip_core.sv src/synth_spine.sv $ENG         tb/tb_chip_core_elab.sv

  printf "\nALL STANDALONE TBS PASSED\n"
'
