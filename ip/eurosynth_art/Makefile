MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

PDK_ROOT ?= $(MAKEFILE_DIR)/../../gf180mcu
PDK ?= gf180mcuD

# --- art tunables (override on the command line, e.g. `make art SCREEN=8`) ---
IMG        ?= image/ws_evzr.png
CELL       ?= eurosynth_art
PIXEL_SIZE ?= 0.60
WIDTH      ?= 800
HEIGHT     ?= 800
# Halftone: 'control' = colour picks style per region (black=solid, grey=hlines,
# yellow=45, green=mesh, cyan=135, blue=dots, magenta=vlines, red=Xmesh).
HALFTONE   ?= control
SCREEN     ?= 6
LINE_WIDTH ?= 2
SOLID_BELOW ?= 96
SHADE_BELOW ?= 210
FOREGROUND ?= "34/0" "36/0" "42/0" "46/0" "81/0"
BOUNDARY   ?= "0/0" "152/5"

all: art drc
.PHONY: all

art:
	python3 script/make_gds.py $(IMG) gds/$(CELL).gds --cellname $(CELL) --invert --merge \
	  --pixel-size $(PIXEL_SIZE) --width $(WIDTH) --height $(HEIGHT) \
	  --halftone $(HALFTONE) --screen $(SCREEN) --line-width $(LINE_WIDTH) \
	  --solid-below $(SOLID_BELOW) --shade-below $(SHADE_BELOW) \
	  --foreground $(FOREGROUND) --boundary $(BOUNDARY)
.PHONY: art

drc:
	PDK_ROOT=${PDK_ROOT} PDK=${PDK} klayout -b -zz -r ${PDK_ROOT}/${PDK}/libs.tech/klayout/tech/drc/gf180mcu.drc -rd input=gds/$(CELL).gds -rd report=report.lyrdb -rd feol=false -rd beol=true
.PHONY: drc
