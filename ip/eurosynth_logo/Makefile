MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

PDK_ROOT ?= $(MAKEFILE_DIR)/../../gf180mcu
PDK ?= gf180mcuD

# --- art tunables (override on the command line, e.g. `make art SCREEN=8`) ---
# Top-left banner box of locations.png: aspect ~2.92, ~1058 x 362 um on the die.
IMG        ?= image/eurosynth.png
CELL       ?= eurosynth_logo
PIXEL_SIZE ?= 0.60
WIDTH      ?= 1764
HEIGHT     ?= 604
# Halftone: 'control' = colour picks style per region (Halftone Studio v1.1:
# grey=clustered dots, red=Xmesh, orange=brick, yellow=45, green=mesh, cyan=135,
# blue=hlines, violet=weave, magenta=vlines). Matches the /studio preview.
HALFTONE   ?= control
SCREEN     ?= 5
# Fill the solid (black) blackletter strokes with a dense hline screen (feature =
# pitch-2, gap 2px) instead of flat metal, so no solid run exceeds 30um -> clears
# MSLOT at the full banner size. 20 = near-solid bold (densest still-clean pitch;
# gaps every 12um guarantee no letter-body solid >30um). 0 = flat solid (MSLOT).
SOLID_SCREEN ?= 20
# Force the lone colour region (the lavender drop-shadow) to a distinct texture so
# it separates from the hline letters. 'dots' = clustered-dot stipple (soft shadow).
COLOR_STYLE ?= dots
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
	  --halftone $(HALFTONE) --screen $(SCREEN) --solid-screen $(SOLID_SCREEN) --color-style $(COLOR_STYLE) --line-width $(LINE_WIDTH) \
	  --solid-below $(SOLID_BELOW) --shade-below $(SHADE_BELOW) \
	  --foreground $(FOREGROUND) --boundary $(BOUNDARY)
.PHONY: art

drc:
	PDK_ROOT=${PDK_ROOT} PDK=${PDK} klayout -b -zz -r ${PDK_ROOT}/${PDK}/libs.tech/klayout/tech/drc/gf180mcu.drc -rd input=gds/$(CELL).gds -rd report=report.lyrdb -rd feol=false -rd beol=true
.PHONY: drc
