# SPDX-License-Identifier: Apache-2.0
"""Generate meme_puf_cluster: 8 identical n=2 PUF dividers (1 tap each) in the
4x2 grid that fits a medallion cluster keepout (80.6 x 44.9 um, see
ip/meme/script/carve_puf.py + ip/meme/puf_spec.json), plus internal rails and
tap fan-out to WEST-edge pins.

Pre-req: the n=2 bank cell:
  python script/build_bank.py --n 2 --out gds/meme_puf_bank2.gds --cell meme_puf_bank2

Cluster-local frame = keepout LL. Layout:
  banks   4 cols x 2 rows at (6 + c*18.65, 6 + r*19.45)  (bank 12.65 wide)
  rails   M2 horizontal, full width: HI y12.3..16.3, LO y17.3..21.3 (4um --
          they carry the force current; banks are M1-only so M2/M3 pass over)
  taps    M3 horizontal trunks y = 23.4 + k*1.1 (k=0..7), 0.6 wide
  lanes   vertical connectors in the 6um column gaps: HI/LO exit each bank's
          LEFT edge, tap exits RIGHT. A vertical M2 lane may never cross a
          rail it doesn't belong to, so the crossings M3-hop through the free
          windows (below the HI rail / between LO rail top 21.3 and trunk
          band bottom 23.1):
            row0 HI  : M2 straight up into the HI rail (no crossing)
            row0 LO  : M1 drop to y10.9, via stack, M3 lane over the HI rail
                       into a via at LO rail center
            row0 tap : M1 drop to y10.0, via stack, M3 lane over BOTH rails to
                       y21.9, M2 window up to its trunk (crossing other trunks
                       on M2), via onto the trunk
            row1 HI  : M2 down to y22.1, M3 hop over the LO rail, via at y15.5
                       inside the HI rail
            row1 LO  : M2 straight down into the LO rail (crosses only the M3
                       trunk band)
            row1 tap : M2 straight to its trunk + via
  pins    WEST edge (x0..0.5): HI/LO on Metal2 (the rail ends), t0..t7 on
          Metal3 (the trunk ends) -- all inside the channel band y11.45..33.45,
          which matches the carved 22um channel EXACTLY (channel is centered on
          the keepout). Right-side clusters are placed FN (x-mirror): pin y
          positions are unchanged, pins land on the east edge.
Tap order: t{k} = bank k in reading order (row0 c0..c3 = t0..t3, row1 = t4..t7).
All vias single-cut (0.26 + 0.5um pads): taps are hi-Z sense lines and the
force current is a brief ~0.7mA/bank readout, well within one via.
"""
import re
import klayout.db as db

BANK_GDS = "gds/meme_puf_bank2.gds"
BANK_LEF = "lef/meme_puf_bank2.lef"
BANK_CELL = "meme_puf_bank2"
OUT_CELL = "meme_puf_cluster"

M1, M2, M3 = (34, 0), (36, 0), (42, 0)
V1, V2 = (35, 0), (38, 0)
BND = (0, 0)
VIA, OVL = 0.26, 0.12

CLUS_W, CLUS_H = 80.6, 44.9
BX, BY = 6.0, 6.0                    # bank grid origin
PX_, PY_ = 18.65, 19.45              # bank grid pitch
RAIL_W = 4.0
HI_Y0, LO_Y0 = 12.3, 17.3            # rail bottoms (M2)
TAP_Y0, TAP_PITCH, TAP_W = 23.4, 1.1, 0.6   # M3 trunk centers = TAP_Y0+k*1.1
LANE_W = 0.7
PAD = 0.25                           # half-size of a single-via landing pad

# ---- bank pin rects + size from LEF (bank-local um) ----
lef = open(BANK_LEF).read()
SIZE = tuple(map(float, re.search(r"SIZE ([\d.]+) BY ([\d.]+)", lef).groups()))
bpins = {}
for name, body in re.findall(r"PIN (\w+)(.*?)END \1", lef, re.S):
    x0, y0, x1, y1 = map(float, re.search(r"RECT ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)", body).groups())
    bpins[name] = (x0, y0, x1, y1)
print(f"bank2: {SIZE[0]}x{SIZE[1]} um, pins {list(bpins)}")

ly = db.Layout(); ly.dbu = 0.001
bank_src = db.Layout(); bank_src.read(BANK_GDS)
bank_cell = ly.create_cell(BANK_CELL)
bank_cell.copy_tree(bank_src.top_cell())
top = ly.create_cell(OUT_CELL)

def box(cell, layer, x0, y0, x1, y1):
    cell.shapes(ly.layer(*layer)).insert(db.Box(round(x0*1000), round(y0*1000), round(x1*1000), round(y1*1000)))

def via_1(layer_lo, layer_hi, via, xc, yc):
    """Single via + 0.5um landing squares on both metals."""
    box(top, via, xc-VIA/2, yc-VIA/2, xc+VIA/2, yc+VIA/2)
    for m in (layer_lo, layer_hi):
        box(top, m, xc-PAD, yc-PAD, xc+PAD, yc+PAD)

PINSHAPES = {}   # pin name -> list[(layer, rect)]
def note(pin, layer, r):
    PINSHAPES.setdefault(pin, []).append((layer, r))

# ---- place banks ----
for r in range(2):
    for c in range(4):
        ox, oy = BX + c*PX_, BY + r*PY_
        top.insert(db.CellInstArray(bank_cell.cell_index(), db.Trans(db.Vector(round(ox*1000), round(oy*1000)))))

# ---- rails (M2, full width to the west edge = the HI/LO pins) ----
box(top, M2, 0.0, HI_Y0, CLUS_W - 2.0, HI_Y0 + RAIL_W)
box(top, M2, 0.0, LO_Y0, CLUS_W - 2.0, LO_Y0 + RAIL_W)
note("HI", M2, (0.0, HI_Y0, 0.5, HI_Y0 + RAIL_W))
note("LO", M2, (0.0, LO_Y0, 0.5, LO_Y0 + RAIL_W))

HI_C = HI_Y0 + RAIL_W/2              # 14.3
LO_C = LO_Y0 + RAIL_W/2              # 19.3
HOP_LO = 22.1                        # via y above LO rail / below trunk band
TAP_WIN = 21.9                       # row0 tap: M3->M2 window via y

def m1_stub(pin_rect, ox, oy, lane_x):
    """M1 from the pin rect sideways to lane_x (bank edge strips verified
    empty at pin heights). Returns pin center y."""
    x0, y0, x1, y1 = pin_rect
    pyc = (y0+y1)/2 + oy
    sx0, sx1 = sorted((x0 + ox, x1 + ox, lane_x - 0.35, lane_x + 0.35))[::3]
    box(top, M1, sx0, pyc - 0.5, sx1, pyc + 0.5)
    return pyc

def m2_seg(x, ya, yb):
    yl, yh = sorted((ya, yb))
    box(top, M2, x - LANE_W/2, yl - PAD, x + LANE_W/2, yh + PAD)

def m3_seg(x, ya, yb):
    yl, yh = sorted((ya, yb))
    box(top, M3, x - LANE_W/2, yl - PAD, x + LANE_W/2, yh + PAD)

def m1_drop(x, ya, yb):
    yl, yh = sorted((ya, yb))
    box(top, M1, x - 0.35, yl - PAD, x + 0.35, yh + 0.5)

# ---- per-bank connections ----
for r in range(2):
    for c in range(4):
        k = r*4 + c
        ox, oy = BX + c*PX_, BY + r*PY_
        # HI and LO exit the bank's LEFT edge -> lanes in the left column gap
        hi_lane, lo_lane = ox - 2.2, ox - 3.6
        tap_lane = ox + SIZE[0] + 1.4
        trunk_y = TAP_Y0 + k*TAP_PITCH

        hy = m1_stub(bpins["HI"], ox, oy, hi_lane)   # r0: 9.6   r1: 29.05
        ly_ = m1_stub(bpins["LO"], ox, oy, lo_lane)  # r0: 11.8  r1: 31.25
        ty = m1_stub(bpins["t1"], ox, oy, tap_lane)  # r0: 10.7  r1: 30.15

        if r == 0:
            # HI: straight up into the HI rail
            via_1(M1, M2, V1, hi_lane, hy)
            m2_seg(hi_lane, hy, HI_C)
            # LO: M1 drop below the rails, M3 over the HI rail, via at LO center
            via_1(M1, M2, V1, lo_lane, 10.9); m1_drop(lo_lane, 10.9, ly_)
            via_1(M2, M3, V2, lo_lane, 10.9)
            m3_seg(lo_lane, 10.9, LO_C)
            via_1(M2, M3, V2, lo_lane, LO_C)
            # tap: M1 drop, M3 over both rails, M2 window up to the trunk
            via_1(M1, M2, V1, tap_lane, 10.0); m1_drop(tap_lane, 10.0, ty)
            via_1(M2, M3, V2, tap_lane, 10.0)
            m3_seg(tap_lane, 10.0, TAP_WIN)
            via_1(M2, M3, V2, tap_lane, TAP_WIN)
            m2_seg(tap_lane, TAP_WIN, trunk_y)
            via_1(M2, M3, V2, tap_lane, trunk_y)
        else:
            # HI: M2 down, M3 hop over the LO rail, land inside the HI rail
            via_1(M1, M2, V1, hi_lane, hy)
            m2_seg(hi_lane, hy, HOP_LO)
            via_1(M2, M3, V2, hi_lane, HOP_LO)
            m3_seg(hi_lane, HOP_LO, 15.5)
            via_1(M2, M3, V2, hi_lane, 15.5)
            # LO: straight down into the LO rail (M3 trunk band passes over)
            via_1(M1, M2, V1, lo_lane, ly_)
            m2_seg(lo_lane, ly_, LO_C)
            # tap: straight to its trunk
            via_1(M1, M2, V1, tap_lane, ty)
            m2_seg(tap_lane, ty, trunk_y)
            via_1(M2, M3, V2, tap_lane, trunk_y)

        # M3 trunk to the west edge (= the tap pin)
        box(top, M3, 0.0, trunk_y - TAP_W/2, tap_lane + LANE_W/2, trunk_y + TAP_W/2)
        note(f"t{k}", M3, (0.0, trunk_y - TAP_W/2, 0.5, trunk_y + TAP_W/2))

# boundary
box(top, BND, 0.0, 0.0, CLUS_W, CLUS_H)
ly.write("gds/meme_puf_cluster.gds")

# ---- LEF (pins WEST edge; OBS = leave to the strap macro; here the cluster
# body itself blocks placement as CLASS BLOCK) ----
LNAME = {M1: "Metal1", M2: "Metal2", M3: "Metal3"}
# Declared SIZE is a small dummy: the 6 cluster instances sit INSIDE the meme
# art macro's bbox, and overlapping full-size FIXED macros double-count the
# bin density in RePlAce -> GPL-0305 divergence on this nearly-empty design.
# PIN/OBS geometry is emitted at its true coordinates beyond the SIZE box
# (LEF permits; same dodge as puf_routes' die-wide geometry).
L = ["VERSION 5.7 ;", "  NOWIREEXTENSIONATPIN ON ;", '  DIVIDERCHAR "/" ;',
     '  BUSBITCHARS "[]" ;', f"MACRO {OUT_CELL}", "  CLASS BLOCK ;",
     f"  FOREIGN {OUT_CELL} ;", "  ORIGIN 0.000 0.000 ;",
     "  SIZE 10.000 BY 10.000 ;"]
for pin in ["HI", "LO"] + [f"t{k}" for k in range(8)]:
    L += [f"  PIN {pin}", "    DIRECTION INOUT ;", "    USE ANALOG ;", "    PORT"]
    for layer, (x0, y0, x1, y1) in PINSHAPES[pin]:
        L += [f"      LAYER {LNAME[layer]} ;",
              f"        RECT {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} ;"]
    L += ["    END", f"  END {pin}"]
L += ["  OBS", "      LAYER Metal1 ;",
      f"        RECT 0.000 0.000 {CLUS_W:.3f} {CLUS_H:.3f} ;",
      "      LAYER Metal2 ;",
      f"        RECT 0.000 0.000 {CLUS_W:.3f} {CLUS_H:.3f} ;",
      "      LAYER Metal3 ;",
      f"        RECT 0.000 0.000 {CLUS_W:.3f} {CLUS_H:.3f} ;",
      "  END", f"END {OUT_CELL}", "END LIBRARY", ""]
open("lef/meme_puf_cluster.lef", "w").write("\n".join(L))

pins = ["HI", "LO"] + [f"t{k}" for k in range(8)]
open("vh/meme_puf_cluster.v", "w").write(
    "// meme_puf_cluster: 8 passive PUF dividers + rails (blackbox).\n"
    "(* blackbox *)\nmodule meme_puf_cluster (" + ", ".join(pins) + ");\n"
    "  inout " + ", ".join(pins) + ";\nendmodule\n")
open("lib/meme_puf_cluster.lib", "w").write(
    "library (meme_puf_cluster) {\n"
    "  input_threshold_pct_fall: 50.0;\n  input_threshold_pct_rise: 50.0;\n"
    "  output_threshold_pct_fall: 50.0;\n  output_threshold_pct_rise: 50.0;\n"
    "  slew_lower_threshold_pct_fall: 20.0;\n  slew_lower_threshold_pct_rise: 20.0;\n"
    "  slew_upper_threshold_pct_fall: 80.0;\n  slew_upper_threshold_pct_rise: 80.0;\n"
    "  cell (meme_puf_cluster) {\n" +
    "".join(f"    pin ({p}) {{ direction: inout; }}\n" for p in pins) +
    "  }\n}\n")
print(f"wrote gds/lef/vh/lib for {OUT_CELL} ({CLUS_W}x{CLUS_H})")
print("pin y (cluster-local):",
      {p: PINSHAPES[p][0][1][1] for p in pins})

# ---- east (pre-mirrored) variant: meme_puf_cluster_e, placed N ----
# FN placement of a dummy-SIZE macro is broken: odb, magic and klayout all
# compute the flip about the DECLARED SIZE box (10x10), so the true
# out-of-box geometry lands CLUS_W-10 = 70.6um west of intended (round-7
# LVS 75 / DRC storm). The east clusters therefore use this pre-mirrored
# cell with plain N orientation; pin/OBS coords below are the exact ones an
# FN flip about the TRUE width would have produced (x -> CLUS_W - x).
E_CELL = OUT_CELL + "_e"
ly2 = db.Layout(); ly2.dbu = 0.001
src = ly2.create_cell("__src")
src.copy_tree(top)
top_e = ly2.create_cell(E_CELL)
top_e.insert(db.CellInstArray(src.cell_index(),
                              db.Trans(2, True, round(CLUS_W*1000), 0)))
top_e.flatten(-1, True)
ly2.write("gds/meme_puf_cluster_e.gds")

def mx(r):
    x0, y0, x1, y1 = r
    return (CLUS_W - x1, y0, CLUS_W - x0, y1)

L = ["VERSION 5.7 ;", "  NOWIREEXTENSIONATPIN ON ;", '  DIVIDERCHAR "/" ;',
     '  BUSBITCHARS "[]" ;', f"MACRO {E_CELL}", "  CLASS BLOCK ;",
     f"  FOREIGN {E_CELL} ;", "  ORIGIN 0.000 0.000 ;",
     "  SIZE 10.000 BY 10.000 ;"]
for pin in pins:
    L += [f"  PIN {pin}", "    DIRECTION INOUT ;", "    USE ANALOG ;", "    PORT"]
    for layer, r in PINSHAPES[pin]:
        x0, y0, x1, y1 = mx(r)
        L += [f"      LAYER {LNAME[layer]} ;",
              f"        RECT {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} ;"]
    L += ["    END", f"  END {pin}"]
L += ["  OBS", "      LAYER Metal1 ;",
      f"        RECT 0.000 0.000 {CLUS_W:.3f} {CLUS_H:.3f} ;",
      "      LAYER Metal2 ;",
      f"        RECT 0.000 0.000 {CLUS_W:.3f} {CLUS_H:.3f} ;",
      "      LAYER Metal3 ;",
      f"        RECT 0.000 0.000 {CLUS_W:.3f} {CLUS_H:.3f} ;",
      "  END", f"END {E_CELL}", "END LIBRARY", ""]
open(f"lef/{E_CELL}.lef", "w").write("\n".join(L))

open(f"vh/{E_CELL}.v", "w").write(
    "// meme_puf_cluster_e: pre-mirrored east cluster (blackbox).\n"
    f"(* blackbox *)\nmodule {E_CELL} (" + ", ".join(pins) + ");\n"
    "  inout " + ", ".join(pins) + ";\nendmodule\n")
open(f"lib/{E_CELL}.lib", "w").write(
    f"library ({E_CELL}) {{\n"
    "  input_threshold_pct_fall: 50.0;\n  input_threshold_pct_rise: 50.0;\n"
    "  output_threshold_pct_fall: 50.0;\n  output_threshold_pct_rise: 50.0;\n"
    "  slew_lower_threshold_pct_fall: 20.0;\n  slew_lower_threshold_pct_rise: 20.0;\n"
    "  slew_upper_threshold_pct_fall: 80.0;\n  slew_upper_threshold_pct_rise: 80.0;\n"
    f"  cell ({E_CELL}) {{\n" +
    "".join(f"    pin ({p}) {{ direction: inout; }}\n" for p in pins) +
    "  }\n}\n")
print(f"wrote gds/lef/vh/lib for {E_CELL} (mirrored)")
