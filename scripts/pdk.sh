#!/usr/bin/env bash
# scripts/pdk.sh — fetch the gf180mcuD PDK into ./pdk (one-time, ~4 GB).
# Runs `ciel` inside the harden container (which ships ciel), so you need no
# local PDK tooling. The PDK lands on the host at $PDK_ROOT (default ./pdk),
# bind-mounted to /pdk in the container.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PDK=${PDK:-gf180mcuD}
PDK_COMMIT=${PDK_COMMIT:-019cf7a3e0de79bb0e4b6213758882d283c65816}

export MSYS_NO_PATHCONV=1   # Windows/Git-Bash mount-path fix

exec docker compose run --rm harden \
    ciel enable "${PDK_COMMIT}" --pdk-root /pdk --pdk-family "${PDK}" --include-libraries all
