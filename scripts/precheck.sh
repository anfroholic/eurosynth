#!/usr/bin/env bash
# scripts/precheck.sh — run the wafer.space gf180mcu-precheck (CoB pad-mask
# variant) on the signoff GDS, using the OFFICIAL published precheck image.
#
# The image (ghcr.io/wafer-space/gf180mcu-precheck) bundles the nix devshell
# (klayout/magic/librelane + the qrcode/pillow python deps our harden image
# lacks) AND the precheck's pinned PDK at /workspace/gf180mcu — so it needs
# nothing from ./pdk and matches what the wafer.space platform itself reruns.
#
# Usage:  bash scripts/precheck.sh                       # defaults below
#         GDS=final_chip/gds/chip_top.gds bash scripts/precheck.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PRECHECK_TAG=${PRECHECK_TAG:-1.7.1}
GDS=${GDS:-final/gds/chip_top.gds}
SLOT=${SLOT:-1x0p5}
TOP=${TOP:-chip_top}
OUT=${OUT:-precheck-${PRECHECK_TAG}/run}
# --workers max OOM-kills the KLayout DRC deck workers on this ~118 MB layout;
# 6 keeps memory ~1.2 GB (see PROGRESS.md Phase Fd).
WORKERS=${WORKERS:-6}

mkdir -p "${OUT}"   # --dir must pre-exist or LibreLane errors

export MSYS_NO_PATHCONV=1   # Windows/Git-Bash mount-path fix

# The image ENTRYPOINT (dev-shell) wraps the command in `nix develop`; cwd is
# /workspace where precheck.py + its pinned PDK live.
exec docker run --rm -v "$(pwd):/work" \
    "ghcr.io/wafer-space/gf180mcu-precheck:${PRECHECK_TAG}" \
    python3 precheck.py --slot "${SLOT}" --cob --top "${TOP}" \
      --input "/work/${GDS}" \
      --workers "${WORKERS}" --threads 1 \
      --dir "/work/${OUT}" \
      --output "/work/${OUT}/chip_top.oas"
