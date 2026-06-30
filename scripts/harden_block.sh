#!/usr/bin/env bash
# scripts/harden_block.sh — harden ONE engine as a standalone MACRO (hierarchical
# flow). Unlike scripts/harden.sh (the full chip: slot + pads + chip macros), this
# runs the plain standard-cell flow on a single block and saves its macro views
# (gds / lef / lib / nl) to ip/<block>/ so the top level can drop it in.
#
# Usage:  bash scripts/harden_block.sh neural_osc
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

BLOCK="${1:?usage: bash scripts/harden_block.sh <block>   (e.g. neural_osc)}"
CFG="librelane/blocks/${BLOCK}/config.yaml"
[ -f "$CFG" ] || { echo "no block config at $CFG"; exit 1; }

PDK=${PDK:-gf180mcuD}
SCL=${SCL:-gf180mcu_fd_sc_mcu7t5v0}

export MSYS_NO_PATHCONV=1

# Classic flow, NO padring / NO slot / NO chip macros. Save the macro views to
# ip/<block>/ (same place the wafer.space IP macros live), so a macros yaml can
# later point the top level at them.
LIBRELANE_CMD="librelane ${CFG} \
    --pdk ${PDK} --pdk-root /pdk --manual-pdk \
    --scl ${SCL} \
    --save-views-to /work/ip/${BLOCK}"

echo "[harden_block] hardening '${BLOCK}' (Classic flow, no pads) -> ip/${BLOCK}/"
exec docker compose run --rm \
    -e PDK="${PDK}" -e SCL="${SCL}" \
    harden bash -lc "${LIBRELANE_CMD}"
