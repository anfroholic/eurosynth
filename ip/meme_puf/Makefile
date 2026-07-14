MAKEFILE_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

PDK_ROOT ?= $(MAKEFILE_DIR)/../../pdk/ciel/gf180mcu/versions/d658698bd8bcf4e05fc7b5991a701247ba0d744c
PDK ?= gf180mcuD
CELL ?= meme_puf

# meme_puf: passive analog-PUF resistor divider (3x ppolyf_u).
# See script/build_puf.py for the geometry + the pres.rb rules it targets.

all: gds drc
.PHONY: all

gds:
	python3 script/build_puf.py
.PHONY: gds

# Full FEOL+BEOL DRC (this macro is all front-end: poly/implant/SAB/contact).
drc:
	PDK_ROOT=$(PDK_ROOT) PDK=$(PDK) klayout -b -zz \
	  -r $(PDK_ROOT)/$(PDK)/libs.tech/klayout/tech/drc/gf180mcu.drc \
	  -rd input=gds/$(CELL).gds -rd report=report.lyrdb \
	  -rd feol=true -rd beol=true
.PHONY: drc
