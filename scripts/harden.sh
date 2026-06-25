#!/usr/bin/env bash
# scripts/harden.sh — RTL -> GDSII hardening (the Docker flow). Runs librelane
# inside the prebuilt LibreLane Docker image (which already contains librelane —
# so NO Nix devshell). Output views are saved to ./final.
#
# Usage:  bash scripts/harden.sh              # uses .env / defaults (SLOT=1x0p5)
#         SLOT=1x1 bash scripts/harden.sh     # override the slot
#
# Prereqs: `bash scripts/pdk.sh` has populated ./pdk.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# Design knobs (defaults match a gf180mcuD / slot 1x0p5 wafer.space half slot).
PDK=${PDK:-gf180mcuD}
SCL=${SCL:-gf180mcu_fd_sc_mcu7t5v0}
PAD=${PAD:-gf180mcu_fd_io}
SRAM=${SRAM:-gf180mcu_fd_ip_sram}
SLOT=${SLOT:-1x0p5}

# macros_5v.yaml goes with the 5V SRAM macro library; otherwise macros_3v3.yaml.
if [ "${SRAM}" = "gf180mcu_fd_ip_sram" ]; then MACROS=5v; else MACROS=3v3; fi

# Generate the per-slot RTL defines first (chip_top.sv includes them).
bash scripts/gen_defines.sh

export MSYS_NO_PATHCONV=1   # Windows/Git-Bash mount-path fix

# The librelane command line — runs inside the harden container, PDK at /pdk.
LIBRELANE_CMD="SRAM_DEFINE=SRAM_${SRAM} librelane \
    librelane/slots/slot_${SLOT}.yaml \
    librelane/macros/macros_${MACROS}.yaml \
    librelane/config.yaml \
    --pdk ${PDK} --pdk-root /pdk --manual-pdk \
    --scl ${SCL} --pad ${PAD} \
    --save-views-to /work/final"

exec docker compose run --rm \
    -e SLOT="${SLOT}" -e PDK="${PDK}" -e SCL="${SCL}" -e PAD="${PAD}" -e SRAM="${SRAM}" \
    harden bash -lc "${LIBRELANE_CMD}"
