#!/usr/bin/env bash
# scripts/pdk.sh — fetch the gf180mcuD PDK into ./pdk (one-time, ~4 GB).
# Runs `ciel` inside the harden container (which ships ciel), so you need no
# local PDK tooling. The PDK lands on the host at $PDK_ROOT (default ./pdk),
# bind-mounted to /pdk in the container.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PDK=${PDK:-gf180mcuD}
# d658698b = template 1.5.7 / precheck 1.7.1 pin: brings the density rules from
# the legacy wafer.space PDK fork that had not yet been upstreamed to Open PDKs.
PDK_COMMIT=${PDK_COMMIT:-d658698bd8bcf4e05fc7b5991a701247ba0d744c}

export MSYS_NO_PATHCONV=1   # Windows/Git-Bash mount-path fix

exec docker compose run --rm harden \
    ciel enable "${PDK_COMMIT}" --pdk-root /pdk --pdk-family "${PDK}" --include-libraries all
