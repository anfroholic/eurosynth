MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

PDK_ROOT ?= $(MAKEFILE_DIR)/../../gf180mcu
PDK ?= gf180mcuD

# --- meme tunables ---
# Source is a pre-dithered 2-level halftone; preprocess blurs it back to
# continuous tone (r=6 keeps the captions crisp) and make_gds re-screens it
# on-grid. Macro fills the 1x0p5 core: 2790x1500 um at 1.0 um pixels, leaving
# a stdcell band below and routing margins around (see macros_5v.yaml).
IMG        ?= image/doge.png
PREPPED    ?= image/doge_prepped.png
BLUR       ?= 6
CELL       ?= meme
PIXEL_SIZE ?= 1.0
WIDTH      ?= 2790
HEIGHT     ?= 1500
HALFTONE   ?= control
SCREEN     ?= 5
SOLID_SCREEN ?= 20
LINE_WIDTH ?= 2
FOREGROUND ?= "34/0" "36/0" "42/0" "46/0" "81/0"
BOUNDARY   ?= "0/0" "152/5"

all: art drc
.PHONY: all

art:
	python3 script/preprocess.py $(IMG) $(PREPPED) --radius $(BLUR)
	python3 script/make_gds.py $(PREPPED) gds/$(CELL).gds --cellname $(CELL) --invert --merge \
	  --pixel-size $(PIXEL_SIZE) --width $(WIDTH) --height $(HEIGHT) \
	  --halftone $(HALFTONE) --screen $(SCREEN) --solid-screen $(SOLID_SCREEN) \
	  --line-width $(LINE_WIDTH) \
	  --foreground $(FOREGROUND) --boundary $(BOUNDARY)
	python3 script/add_poly_fill.py gds/$(CELL).gds
	python3 script/carve_gds.py
.PHONY: art

drc:
	PDK_ROOT=${PDK_ROOT} PDK=${PDK} klayout -b -zz -r ${PDK_ROOT}/${PDK}/libs.tech/klayout/tech/drc/gf180mcu.drc -rd input=gds/$(CELL).gds -rd report=report.lyrdb -rd feol=false -rd beol=true
.PHONY: drc
