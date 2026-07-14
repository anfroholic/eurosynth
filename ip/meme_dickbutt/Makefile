MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
PDK_ROOT ?= $(MAKEFILE_DIR)/../../pdk
PDK      ?= gf180mcuD
DRC      := $(PDK_ROOT)/$(PDK)/libs.tech/klayout/tech/drc/gf180mcu.drc

# Canonical: the eye-glint dickbutt. Hand-edited 32px sprite mapped 1 px -> 2 um
# (48x64 um), rendered as crisp pixel-art metal. In the doge it is placed as an
# EMPTY cutout inside the solid pupil, so it reads as a bright reflection.
SPRITE ?= image/dickbutt_32_rgba.png
CELL   ?= 2.0
NAME   ?= meme_dickbutt

art:
	python3 script/build.py --mode pixel --sprite $(SPRITE) --cell-um $(CELL) --name $(NAME)
.PHONY: art

# BEOL DRC on the standalone tile. Expect ONLY the whole-die density floors
# (DCF.1b / M1-5.4 / MT.3 / PL.8) -- these need the full chip context (the doge's
# dense art + poly fill) and clear there. Any M#.1/M#.2 (width/space) would be a
# REAL defect; there are none.
drc:
	PDK_ROOT=$(PDK_ROOT) PDK=$(PDK) klayout -b -zz -r $(DRC) \
	  -rd input=gds/$(NAME).gds -rd report=out/drc_$(NAME).lyrdb -rd feol=false -rd beol=true
.PHONY: drc
