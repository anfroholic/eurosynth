# SPDX-License-Identifier: Apache-2.0
"""Generate puf_routes: pre-drawn metal straps tying the PUF bank pins to the
analog pads' ASIG5V terminals.

WHY STRAPS: the pad nets (analog_PAD[i]) are SPECIAL pad-ring nets -- OpenROAD's
router never routes new terminals onto them, so without pre-drawn copper the
bank would be physically floating (and electrically useless on silicon).

WHY LEF *PINS* (round-3 finding): LibreLane's Magic.SpiceExtraction runs in
ABSTRACT mode (lef read for every macro, never gds) -- LEF OBS geometry is NOT
conductive there, so an obstruction-only strap macro extracts as empty and LVS
still sees the bank floating even though the GDS copper is verifiably merged.
In abstract mode the only conductors are LEF PIN PORT rects; magic unifies ALL
PORT rects of one PIN as one electrical node EVEN IF DISJOINT (see the io pad's
own .ext: multiple disjoint DVSS port rects share one node). So each strap is a
LEF PIN whose PORT contains:
  - the real strap copper (M1/M2/M3), overlapping the bank's M1 pin port, and
  - a small M5 "tab" drawn on top of the pad's solid M5 bond pad, overlapping
    the pad's ASIG5V LEF port rect (the pad's ONLY abstract-mode conductor --
    its M2 fingers are not in the LEF). Physically the tab is coincident metal
    on the bond stack: zero effect, no DRC.
Extraction then merges pad port <-> tab <->(pin identity)<-> straps <-> bank
pin, and LVS matches the verilog (module now has real inout ports wired to
analog_PAD[*] in chip_top.sv). The same rects are ALSO emitted as OBS so
pdngen/router treat them as blockages exactly as before.

Physical scheme (all die um, left-edge pads):
  pad ASIG5V = 8 Metal2 fingers ending flush at die x=374.39 (u-span
  15.34..59.66, symmetric -> mirror-proof); the neighboring DVDD/DVSS bus
  fingers sit 0.30 above/below that span and also end at x=374.39, and the
  pad's outermost vertical M3 bus rail ends at x=374.39. Per net:
    M5 tab      10x10 inside the bond-pad opening (die x[45,55])
    M2 collar   over the ASIG5V finger tips, inset 0.02 from the finger span
                so clearance to the power fingers is 0.32 (round-3: a 0.2
                OVERHANG left only 0.10 -> 84 M2.2a/M3.2a slivers)
    via2 stack  collar -> M3
    M3 trunk    horizontal at the pad's y-centre to a per-net vertical lane;
                left edge at 374.90 (>=0.51 clear of the pad M3 rail; round-3
                started it at 374.50 = 0.11 gap = M3.2a)
    M2 lane     vertical to the bank pin's y (via2 at each corner)
    M3 stub     across to over the pin (M2 stubs short against other lanes),
                then via2+via1 down to the bank's M1 pin rect

Vias: Via1 35/0, Via2 38/0; 0.26 square, metal overlap 0.12 all around.
Layers: Metal1 34/0, Metal2 36/0, Metal3 42/0, Metal5 81/0.
"""
import re
import json
import klayout.db as db

# ---- chip facts (from final DEF + floorplan; see eurosynth-meme-puf memory) ----
PAD_INNER_X = 376.0                 # left-edge pad CELLS span die x[26,376]
PAD_METAL_END = 374.39              # pad-internal M2 fingers / M3 rail end here
PADS = {                            # net -> pad lower-left die y (75 um tall)
    "HI": 1721.5,                   # analog[0]
    "t1": 1580.5,                   # analog[1]
    "t2": 1439.5,                   # analog[2]
    "LO": 1298.5,                   # analog[3]
}
FINGER_LO, FINGER_HI = 15.34, 59.66  # ASIG5V finger u-span within the 75um pad
# ASIG5V abstract port (per pad .ext): m5 bond rect, die x[28,88] y[pad+7.5,+67.5],
# u-symmetric -> mirror-proof. Solid drawn M5 verified die x[26,91.3] y[pad+3.5,+71.5].
TAB_X0, TAB_X1 = 45.0, 55.0
TAB_V0, TAB_V1 = 32.5, 42.5          # pad-relative y
BANK_XY = (500.0, 1540.0)            # meme_puf_bank placement (macros_5v.yaml)
BANK_LEF = "lef/meme_puf_bank.lef"

M1, M2, M3, M5 = (34, 0), (36, 0), (42, 0), (81, 0)
V1, V2 = (35, 0), (38, 0)
BND = (0, 0)
VIA, OVL = 0.26, 0.12               # via size / metal overlap
TRUNK_W = 2.0                        # M3 trunk width
LANE_W = 1.4                         # M2 lane width
ORIGIN = (43.0, 1290.0)              # macro origin (die um) = min shape x - 2

# ---- bank pin rects from its LEF (die um) ----
lef = open(BANK_LEF).read()
pins = {}
for name, body in re.findall(r"PIN (\w+)(.*?)END \1", lef, re.S):
    x0, y0, x1, y1 = map(float, re.search(r"RECT ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)", body).groups())
    pins[name] = (x0 + BANK_XY[0], y0 + BANK_XY[1], x1 + BANK_XY[0], y1 + BANK_XY[1])

ly = db.Layout(); ly.dbu = 0.001
top = ly.create_cell("puf_routes")
LNAME = {M1: "Metal1", M2: "Metal2", M3: "Metal3", M5: "Metal5"}
NET_SHAPES = {n: [] for n in PADS}   # net -> [(layer, x0,y0,x1,y1)] macro-local um

def box(net, layer, x0, y0, x1, y1):
    lx0, ly0 = x0 - ORIGIN[0], y0 - ORIGIN[1]
    lx1, ly1 = x1 - ORIGIN[0], y1 - ORIGIN[1]
    top.shapes(ly.layer(*layer)).insert(db.Box(
        round(lx0 * 1000), round(ly0 * 1000), round(lx1 * 1000), round(ly1 * 1000)))
    if net is not None and layer in LNAME:
        NET_SHAPES[net].append((layer, lx0, ly0, lx1, ly1))

def via_stack(net, layer, xc, yc):
    box(net, layer, xc - VIA / 2, yc - VIA / 2, xc + VIA / 2, yc + VIA / 2)

def via_pad(net, metal, via, xc, yc):
    """2x2 via array with generous metal overlap on `metal` at (xc,yc)."""
    pitch = VIA + 0.30
    for dx in (-pitch / 2, pitch / 2):
        for dy in (-pitch / 2, pitch / 2):
            via_stack(net, via, xc + dx, yc + dy)
    half = pitch / 2 + VIA / 2 + OVL
    box(net, metal, xc - half, yc - half, xc + half, yc + half)

# per-net vertical M2 lane x (staggered, left of the bank; >=1.6 clear space)
LANES = {"HI": 486.0, "t1": 489.0, "t2": 492.0, "LO": 495.0}
# per-net stub y (bank-local). Stubs are on METAL3: an M2 stub is impossible --
# any M2 lane rising past another net's M2 stub would short (verified M2.2a).
# M3 stubs cross the M2 lanes freely; only stub-vs-stub spacing matters:
# 1.0-wide on a ~1.45 pitch = 0.4-0.45 gaps (M3 min 0.3), each inside its
# pin's y-span (HI [3.1,4.1] t1 [3.1,6.3] t2 [5.3,8.5] LO [7.5,8.5]), and LO
# low enough that its M1 via blob clears the bank's floating dummy-bar strap
# above (y>=8.7, M1 space 0.23).
STUB_Y = {"HI": 3.6, "t1": 5.05, "t2": 6.5, "LO": 7.9}
STUB_W = 1.0

extents = []
spec = {"nets": {}}
for net, pad_y in PADS.items():
    # collar inset 0.02 into the finger span: 0.30 finger gap + 0.02 = 0.32
    # clearance to the DVDD/DVSS fingers (M2 space 0.28)
    fy0, fy1 = pad_y + FINGER_LO + 0.02, pad_y + FINGER_HI - 0.02
    trunk_y = pad_y + 37.5
    lane_x = LANES[net]
    px0, py0, px1, py1 = pins[net]
    stub_y = STUB_Y[net] + BANK_XY[1]
    # via rows must land on/next to the pin; our own M1 blob bridges any
    # sub-0.1um stub overhang past the pin edge
    assert py0 - 0.1 <= stub_y <= py1 + 0.1, f"{net}: stub y {stub_y} outside pin {py0}-{py1}"
    # 0. M5 tab on the bond pad (the abstract-mode handle to the pad net)
    box(net, M5, TAB_X0, pad_y + TAB_V0, TAB_X1, pad_y + TAB_V1)
    # 1. M2 collar over the finger tips (overlap 1.39um onto the fingers)
    box(net, M2, PAD_INNER_X - 3.0, fy0, PAD_INNER_X + 2.0, fy1)
    # 2. via2 pad collar->M3 at trunk start
    via_pad(net, M3, V2, PAD_INNER_X - 0.5, trunk_y)
    box(net, M2, PAD_INNER_X - 2.0, trunk_y - 1.0, PAD_INNER_X + 1.0, trunk_y + 1.0)
    # 3. M3 trunk to the lane (left edge 0.51 clear of the pad M3 rail)
    box(net, M3, PAD_METAL_END + 0.51, trunk_y - TRUNK_W / 2, lane_x + LANE_W / 2 + 0.5, trunk_y + TRUNK_W / 2)
    # 4. via2 trunk->M2 lane, lane vertical to stub y, via2 back up to M3
    via_pad(net, M3, V2, lane_x, trunk_y)
    via_pad(net, M2, V2, lane_x, trunk_y)
    ylo, yhi = sorted((trunk_y, stub_y))
    box(net, M2, lane_x - LANE_W / 2, ylo - LANE_W / 2, lane_x + LANE_W / 2, yhi + LANE_W / 2)
    via_pad(net, M2, V2, lane_x, stub_y)
    via_pad(net, M3, V2, lane_x, stub_y)
    # 5. M3 stub across to over the pin (M3 crosses the other M2 lanes freely),
    #    then via2+via1 stack down to the M1 pin rect
    pin_cx = (px0 + px1) / 2
    sx0, sx1 = sorted((lane_x, pin_cx))
    box(net, M3, sx0 - STUB_W / 2, stub_y - STUB_W / 2, sx1 + STUB_W / 2, stub_y + STUB_W / 2)
    via_pad(net, M3, V2, pin_cx, stub_y)
    via_pad(net, M2, V2, pin_cx, stub_y)
    via_pad(net, M2, V1, pin_cx, stub_y)
    via_pad(net, M1, V1, pin_cx, stub_y)
    extents += [(TAB_X0, pad_y + TAB_V0), (PAD_INNER_X - 3.0, fy0), (px1 + 1, py1 + 1), (lane_x, trunk_y)]
    spec["nets"][net] = {"pad_y": pad_y, "trunk_y": trunk_y, "lane_x": lane_x,
                         "pin": [px0, py0, px1, py1], "stub_y": stub_y,
                         "tab": [TAB_X0, pad_y + TAB_V0, TAB_X1, pad_y + TAB_V1]}

# boundary
xs = [e[0] for e in extents]; ys = [e[1] for e in extents]
bx0, by0 = min(xs) - 2, min(ys) - 2
bx1, by1 = max(xs) + 16, max(ys) + 60
box(None, BND, bx0, by0, bx1, by1)
ly.write("gds/puf_routes.gds")

SIZEX, SIZEY = bx1 - ORIGIN[0], by1 - ORIGIN[1]
# LEF: one PIN per net (PORT = every strap rect; magic unifies all PORT rects
# of a pin as ONE node, which is what merges tab<->straps), plus the same rects
# as OBS so pdngen/the router treat them as hard blockages (pin geometry alone
# is NOT respected by pdngen).
L = ["VERSION 5.7 ;", "  NOWIREEXTENSIONATPIN ON ;", '  DIVIDERCHAR "/" ;',
     '  BUSBITCHARS "[]" ;', "MACRO puf_routes", "  CLASS BLOCK ;",
     "  FOREIGN puf_routes ;", "  ORIGIN 0.000 0.000 ;",
     f"  SIZE {SIZEX:.3f} BY {SIZEY:.3f} ;"]
for net in PADS:
    L += [f"  PIN {net}", "    DIRECTION INOUT ;", "    USE ANALOG ;", "    PORT"]
    cur = None
    for layer, x0, y0, x1, y1 in NET_SHAPES[net]:
        if LNAME[layer] != cur:
            cur = LNAME[layer]
            L.append(f"      LAYER {cur} ;")
        L.append(f"        RECT {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} ;")
    L += ["    END", f"  END {net}"]
L.append("  OBS")
for lyr in (M1, M2, M3, M5):
    rects = [s for n in PADS for s in NET_SHAPES[n] if s[0] == lyr]
    if not rects: continue
    L.append(f"      LAYER {LNAME[lyr]} ;")
    for _, x0, y0, x1, y1 in rects:
        L.append(f"        RECT {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} ;")
L += ["  END", "END puf_routes", "END LIBRARY", ""]
open("lef/puf_routes.lef", "w").write("\n".join(L))
open("vh/puf_routes.v", "w").write(
    "// puf_routes: pre-drawn pad<->PUF straps. Real copper (the PUF's current\n"
    "// path) exposed as LEF pins so abstract-mode extraction sees the merge;\n"
    "// ports are wired to analog_PAD[*] in chip_top.sv.\n"
    "(* blackbox *)\nmodule puf_routes (HI, t1, t2, LO);\n"
    "  inout HI, t1, t2, LO;\nendmodule\n")
# OpenSTA (CheckMacroInstances) requires the 8 threshold attributes even in a
# dummy lib -- omitting them kills the flow at step 11.
open("lib/puf_routes.lib", "w").write("""library (puf_routes) {
  input_threshold_pct_fall: 50.0;
  input_threshold_pct_rise: 50.0;
  output_threshold_pct_fall: 50.0;
  output_threshold_pct_rise: 50.0;
  slew_lower_threshold_pct_fall: 20.0;
  slew_lower_threshold_pct_rise: 20.0;
  slew_upper_threshold_pct_fall: 80.0;
  slew_upper_threshold_pct_rise: 80.0;

  cell (puf_routes) {
    pin (HI) { direction: inout; }
    pin (t1) { direction: inout; }
    pin (t2) { direction: inout; }
    pin (LO) { direction: inout; }
  }
}
""")
json.dump(spec, open("puf_routes_spec.json", "w"), indent=1)
print(f"wrote gds/puf_routes.gds + lef/vh/lib  origin={ORIGIN} size={SIZEX:.1f}x{SIZEY:.1f}")
print(f"macros_5v.yaml location: [{ORIGIN[0]}, {ORIGIN[1]}]")
