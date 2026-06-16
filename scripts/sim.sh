#!/usr/bin/env bash
# Run any command inside the eurosynth-sim container with this repo mounted at
# /work. This is the ONE place the Docker invocation lives, so neither humans
# nor sub-agents have to remember the Windows<->Linux path-mount incantation.
#
# Examples:
#   bash scripts/sim.sh iverilog -V                       # check the toolchain
#   bash scripts/sim.sh bash -lc 'iverilog -g2012 -o /tmp/a.vvp src/*.sv tb/foo.sv && vvp /tmp/a.vvp'
#   bash scripts/sim.sh make sim                          # template's cocotb flow
set -euo pipefail

# git prints the repo root as a Windows path (C:/Users/...) which Docker Desktop
# mounts directly. MSYS_NO_PATHCONV stops Git Bash from mangling the :/work part.
REPO_WIN="$(git rev-parse --show-toplevel)"
export MSYS_NO_PATHCONV=1

exec docker run --rm -i \
    -v "${REPO_WIN}:/work" \
    -w /work \
    eurosynth-sim "$@"
