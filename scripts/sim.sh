#!/usr/bin/env bash
# scripts/sim.sh — run any command inside the eurosynth sim container with this
# repo mounted at /work. Handy for ad-hoc iverilog/vvp calls; the full green
# check lives in scripts/sim_all.sh.
#
# Examples:
#   bash scripts/sim.sh iverilog -V
#   bash scripts/sim.sh bash -lc 'iverilog -g2012 -I src -o /tmp/a.vvp src/ks_engine.sv tb/tb_ks_engine.sv && vvp /tmp/a.vvp'
set -euo pipefail

# git prints the repo root as a Windows path (C:/Users/...) which Docker Desktop
# mounts directly. MSYS_NO_PATHCONV stops Git Bash from mangling the :/work part.
REPO_WIN="$(git rev-parse --show-toplevel)"
export MSYS_NO_PATHCONV=1

# Build the image on demand if it isn't there yet (matches docker-compose tag).
if ! docker image inspect eurosynth-sim >/dev/null 2>&1; then
    docker compose build sim
fi

exec docker run --rm -i \
    -v "${REPO_WIN}:/work" \
    -w /work \
    eurosynth-sim "$@"
