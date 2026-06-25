# Makefile — convenience front door over the eurosynth Docker flow.
#
# NOTE: Windows has no `make`. From a Windows host drive the flow with the
# scripts directly (they need only docker + docker compose):
#
#   cp .env.example .env            # (once) knobs; SLOT defaults to 1x0p5
#   bash scripts/sim_all.sh         # the green check (standalone TB suite)
#   bash scripts/pdk.sh             # fetch the gf180mcuD PDK into ./pdk (~4 GB)
#   bash scripts/harden.sh          # RTL -> GDSII; views saved to ./final
#
# On Linux/Mac/WSL (with make) these targets wrap the exact same scripts, so the
# scripts stay the single source of truth.
SLOT ?= 1x0p5

.DEFAULT_GOAL := help

help: ## Show this help message
	@echo 'eurosynth — Docker build flow.  Usage: make [target] [SLOT=1x0p5]'
	@echo ''
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'
.PHONY: help

build: ## Build both Docker images (sim + harden)
	docker compose build sim harden
.PHONY: build

build-sim: ## Build the simulation Docker image
	docker compose build sim
.PHONY: build-sim

build-harden: ## Build the hardening Docker image (LibreLane + pmap shim)
	docker compose build harden
.PHONY: build-harden

defines: ## Write src/generated_defines.svh from the current SLOT/SRAM
	SLOT=$(SLOT) bash scripts/gen_defines.sh
.PHONY: defines

sim: ## Run the standalone TB suite (the no-PDK green check)
	bash scripts/sim_all.sh
.PHONY: sim

test: sim ## Alias for `sim`
.PHONY: test

pdk: ## Fetch the gf180mcuD PDK into ./pdk (one-time, ~4 GB)
	bash scripts/pdk.sh
.PHONY: pdk

harden: ## Harden RTL -> GDSII (Docker); output in ./final
	SLOT=$(SLOT) bash scripts/harden.sh
.PHONY: harden

open-klayout: ## Open the most recent hardening run in KLayout
	docker compose run --rm harden bash -lc \
	    'librelane librelane/slots/slot_$(SLOT).yaml librelane/macros/macros_5v.yaml librelane/config.yaml --pdk gf180mcuD --pdk-root /pdk --manual-pdk --scl gf180mcu_fd_sc_mcu7t5v0 --pad gf180mcu_fd_io --last-run --flow OpenInKLayout'
.PHONY: open-klayout

open-openroad: ## Open the most recent hardening run in OpenROAD
	docker compose run --rm harden bash -lc \
	    'librelane librelane/slots/slot_$(SLOT).yaml librelane/macros/macros_5v.yaml librelane/config.yaml --pdk gf180mcuD --pdk-root /pdk --manual-pdk --scl gf180mcu_fd_sc_mcu7t5v0 --pad gf180mcu_fd_io --last-run --flow OpenInOpenROAD'
.PHONY: open-openroad

clean: ## Remove generated sim/harden artifacts (keeps the PDK in ./pdk)
	rm -rf cocotb/sim_build cocotb/results.xml cocotb/__pycache__ \
	       librelane/runs final src/generated_defines.svh
.PHONY: clean
