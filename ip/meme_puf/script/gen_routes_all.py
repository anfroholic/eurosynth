# SPDX-License-Identifier: Apache-2.0
"""Generate the die-wide puf_routes: pre-drawn copper tying all 50 analog pads
(2 force rails + 48 hi-Z taps) to the 6 medallion PUF clusters.

Architecture (pad tab/collar/trunk proven on the single-bank round-4 chip):
  per pad     M5 bond tab (the pad's only abstract-mode conductor) + M2 collar
              on the ASIG5V fingers + a trunk to its corridor track
  corridors   the margin band between pad metal and the core (d ~ 377..414
              from each die edge). ALL corridor copper is METAL1: the PDN owns
              everything else there -- measured from the round-6 DEF:
                M3 ring bands y 385.26..410.26 AND 411.96..436.96 (mirrored on
                  top at 2118.14..2143.14 / 2091.44..2116.44), full die width
                M4 ring verticals at the mirrored x bands
                M2 ring->pad straps at power pads (6 stripes, [s+1.4,s+73.6],
                  x [3495.9,3560.7] east / [371.3,436.4] west, and the
                  vertical equivalents on N/S power pads)
                M3 DRCFILL patches at the strap stripe ys in the corridor
              Metal1, by contrast, only exists as followpins INSIDE the core
              and inside the pad/corner cells (pad-row M1 ends at d<=375.8;
              corner-cell M1 stays within 381.0 of the corner) -> M1 tracks
              and lanes cross all of it with no hops and no spacing fights.
  layer rule  corridors = M1 (both directions; same-layer bends, no vias).
              Core crossings (cluster branch trunks, R3 jogs) = M3 horizontal
              / M2 vertical: never M1 over the core -- the art is M1.
              Junctions corridor<->branch are V1+V2 via stacks. The macro's
              OBS makes pdngen trim its via stacks off our copper
              (odb-addpdnobstructions; proven round 4/5/6).
  taps        thin (0.7um) -- they carry ~zero current (hi-Z voltage sense)
  rails       4um, one M1 spine: west pads -> left corridor -> bottom ->
              right corridor, with M3 branch trunks into every cluster
  clusters    pins at the carved 22um channel band (west edge, N orient for
              R1/R2; east edge via FN mirror for R3..R6); tap trunks land on
              the cluster's M3 pins, rails via2 onto its M2 pins
Net names match chip_top.sv: analog[0]=HI, analog[1]=LO, analog[k]=t{k-2}.
Tap->cluster map must equal chip_top.sv's cluster wiring.
"""
import json
import klayout.db as db

M1, M2, M3, M5 = (34, 0), (36, 0), (42, 0), (81, 0)
V1, V2 = (35, 0), (38, 0)
BND = (0, 0)
VIA, OVL = 0.26, 0.12
DIE_W, DIE_H = 3932.0, 2531.0
ORIGIN = (43.0, 43.0)

# pad geometry facts (edge-local: s along edge, d = depth from die edge)
PAD_FACE, PAD_METAL_END = 376.0, 374.39
FINGER_LO, FINGER_HI = 15.36, 59.64      # collar span (0.02 inset, round-4 fix)
TAB_D, TAB_S = (45.0, 55.0), (32.5, 42.5)
TRUNK_W, LANE_W, RAIL_W = 2.0, 0.7, 4.0

# corridor tracks (d from die edge), all M1. HI_T=383.5 keeps the 4um rail's
# edge (d381.5) 0.5um clear of the corner cells' M1 (within 381.0 of each
# corner). Tap pitch 1.3 (bend pads 0.5 + wire 0.7 -> 0.7 clear).
HI_T, LO_T = 383.5, 388.2                # rail track centres
TAP_T0, TAP_P = 394.0, 1.3               # tap track 0 centre / pitch (L/R/B)
TAP_T0_TOP = 382.0                       # top corridor tap track 0

# R3's pin band (y 1856..1873) overlaps the s=1862.5 power strap's first M2
# stripe (y 1863.86..1873.36, x 3495.9..3560.7): junction via stacks in the
# corridor would put their M2 pads inside the stripe. So R3's taps and LO
# leave the corridor clear of the stripes and jog vertically over the art at
# x < 3495.9 on M2 (M1 is the art layer -- never M1 over the core).
XJ_TAP0 = 3472.0          # R3 tap jog columns: x = XJ_TAP0 - k*1.3 (k=0..7)
XJ_LO = 3477.0            # R3 LO rail jog column
Y_LO_EXIT = 1846.0        # LO leaves the right corridor at this y (< 1863.9)

# ---- pad table: analog index -> (edge, s0) ----
W_S = [734.5 + 141.0 * i for i in range(8)]
B_S = [1477.0 + 129.0 * i for i in range(10)] + [3025.0 + 129.0 * i for i in range(4)]
E_S = [734.5 + 141.0 * i for i in range(8)]
T_S = [445.0 + 129.0 * i for i in range(4)] + [1219.0 + 129.0 * i for i in range(12)] + [3025.0 + 129.0 * i for i in range(4)]
PADS = {}
for i in range(8):  PADS[i] = ("W", W_S[i])
for i in range(14): PADS[8 + i] = ("B", B_S[i])
for i in range(8):  PADS[22 + i] = ("E", E_S[i])
for i in range(20): PADS[30 + i] = ("T", T_S[i])

def netname(j):
    return "HI" if j == 0 else ("LO" if j == 1 else f"t{j-2}")

# ---- clusters (LL die um, side) + tap map (MUST match chip_top.sv) ----
CLUSTERS = {
    "R1": ((679.7, 1113.25), "L", [2, 3, 4, 5, 8, 9, 10, 11]),
    "R2": ((759.7, 1594.05), "L", [6, 7, 12, 13, 14, 15, 16, 17]),
    "R5": ((3189.7, 680.25), "R", [18, 19, 20, 21, 22, 23, 24, 25]),
    "R4": ((3199.7, 1486.95), "R", [26, 27, 28, 29, 49, 48, 47, 46]),
    "R3": ((3099.7, 1841.95), "R", [38, 39, 40, 41, 42, 43, 44, 45]),
    "R6": ((3139.7, 1129.55), "R", [30, 31, 32, 33, 34, 35, 36, 37]),
}
CLUS_W = 80.6
PIN_HI_Y, PIN_LO_Y = 14.3, 19.3          # cluster-local pin centres (M2, 4um)
PIN_TAP_Y0, PIN_TAP_P = 23.4, 1.1        # t_k centre = 23.4+k*1.1 (M3, 0.6)

# ---- corridor track assignment (per corridor, per net) ----
LTRK, BTRK, RTRK, TTRK = {}, {}, {}, {}
for i, j in enumerate([2, 3, 4, 5, 6, 7] + list(range(8, 18))):
    LTRK[j] = TAP_T0 + i * TAP_P                       # left: W taps + S->left
for i, j in enumerate(list(range(8, 22))):
    BTRK[j] = TAP_T0 + i * TAP_P                       # bottom: all S taps
for i, j in enumerate(list(range(18, 30)) + [46, 47, 48, 49] +
                      list(range(38, 46)) + list(range(30, 38))):
    RTRK[j] = TAP_T0 + i * TAP_P                       # right: 32 nets
# top corridor: tracks and lanes share M1, so a track may never pass over a
# foreign lane below that lane's bend: bend y must DECREASE as bend x
# decreases. j46..49's lanes (x 3522.4..3518.5) sit EAST of j30..37's
# (3506.8..3497.7), so they take the top-most tracks; j38..45 end at the
# westmost jog columns and take the lowest.
for i, j in enumerate([46, 47, 48, 49] + list(range(30, 38)) + list(range(38, 46))):
    TTRK[j] = TAP_T0_TOP + i * TAP_P                   # top: all T taps

# ---- geometry helpers ----
ly = db.Layout(); ly.dbu = 0.001
top = ly.create_cell("puf_routes")
NET_SHAPES = {netname(j): [] for j in range(50)}

def box(net, layer, x0, y0, x1, y1):
    lx0, ly0, lx1, ly1 = x0 - ORIGIN[0], y0 - ORIGIN[1], x1 - ORIGIN[0], y1 - ORIGIN[1]
    top.shapes(ly.layer(*layer)).insert(db.Box(
        round(lx0 * 1000), round(ly0 * 1000), round(lx1 * 1000), round(ly1 * 1000)))
    if net is not None and layer in (M1, M2, M3, M5):
        NET_SHAPES[net].append((layer, lx0, ly0, lx1, ly1))

def via_arr(net, lo, hi, vl, xc, yc, w):
    """lo<->hi via array sized to the wire width w at a junction. Thin sense
    lanes get a SINGLE via (zero current; a 2x2 array's landing pad would
    violate spacing to the neighbouring 1.3-pitch lane)."""
    # pitch gives 0.36 space: V1.2b/V2.2b require >=0.36 between vias in any
    # 4x4-or-larger array (0.30 fails die-level DRC on the wide junctions)
    n = 1 if w < 1.0 else max(2, int(w // 0.62))
    pitch = VIA + 0.36
    span = (n - 1) * pitch
    for ix in range(n):
        for iy in range(n):
            cx, cy = xc - span / 2 + ix * pitch, yc - span / 2 + iy * pitch
            box(net, vl, cx - VIA / 2, cy - VIA / 2, cx + VIA / 2, cy + VIA / 2)
    half = span / 2 + VIA / 2 + OVL
    box(net, lo, xc - half, yc - half, xc + half, yc + half)
    box(net, hi, xc - half, yc - half, xc + half, yc + half)

def via12(net, xc, yc, w):
    via_arr(net, M1, M2, V1, xc, yc, w)

def via_bend(net, xc, yc, w):                 # M2<->M3 (core-crossing bends)
    via_arr(net, M2, M3, V2, xc, yc, w)

def stack13(net, xc, yc, w):                  # corridor M1 <-> branch M3
    via_arr(net, M1, M2, V1, xc, yc, w)
    via_arr(net, M2, M3, V2, xc, yc, w)

def h1(net, y, x0, x1, w):                    # corridor horizontal (M1)
    xa, xb = sorted((x0, x1))
    box(net, M1, xa - w / 2, y - w / 2, xb + w / 2, y + w / 2)

def v1(net, x, y0, y1, w):                    # corridor vertical (M1)
    ya, yb = sorted((y0, y1))
    box(net, M1, x - w / 2, ya - w / 2, x + w / 2, yb + w / 2)

def hseg(net, y, x0, x1, w):                  # core-crossing horizontal (M3)
    xa, xb = sorted((x0, x1))
    box(net, M3, xa - w / 2, y - w / 2, xb + w / 2, y + w / 2)

def vseg(net, x, y0, y1, w):                  # core-crossing vertical (M2)
    ya, yb = sorted((y0, y1))
    box(net, M2, x - w / 2, ya - w / 2, x + w / 2, yb + w / 2)

# edge-local (s,d) -> die (x,y)
def tx(edge, s, d):
    if edge == "W": return (d, s)
    if edge == "E": return (DIE_W - d, s)
    if edge == "B": return (s, d)
    return (s, DIE_H - d)                                # T

def rect_sd(net, layer, edge, s0, s1, d0, d1):
    xa, ya = tx(edge, s0, d0)
    xb, yb = tx(edge, s1, d1)
    box(net, layer, min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb))

# ---- pad interface: tab + collar + trunk to the corridor track ----
def pad_iface(net, edge, s0, track_d):
    rect_sd(net, M5, edge, s0 + TAB_S[0], s0 + TAB_S[1], TAB_D[0], TAB_D[1])
    rect_sd(net, M2, edge, s0 + FINGER_LO, s0 + FINGER_HI, 373.0, 378.0)
    sc = s0 + 37.5
    if edge in ("W", "E"):
        # M3 trunk (horizontal): collar via at d375.6, trunk to the track.
        # d375.6 (not 375.5): the 0.62-pitch via pads reach d-0.87, and the
        # pad cell's own M3 rail ends at d374.39 -> 375.6 keeps M3.2a's 0.28
        # (375.5 left only 0.24 -- 32 klayout violations in round 8).
        # End at track_d+0.25 (the junction pad): a longer overshoot would
        # touch the NEXT lane's branch/stack 1.3um over (t4/t5 short).
        xc, yc = tx(edge, sc, 375.6)
        via_bend(net, xc, yc, TRUNK_W)
        rect_sd(net, M2, edge, sc - 1.0, sc + 1.0, 374.0, 377.0)
        rect_sd(net, M3, edge, sc - TRUNK_W / 2, sc + TRUNK_W / 2, 374.9, track_d + 0.25)
    else:
        # M2 trunk (vertical): the collar is M2 already -- just extend it
        rect_sd(net, M2, edge, sc - TRUNK_W / 2, sc + TRUNK_W / 2, 373.0, track_d + 1.0)
    return tx(edge, sc, track_d)                          # trunk/corridor junction

# ---- cluster pin landings (die coords) ----
def cluster_pin(name, kind, k=0):
    (cx, cy), side, _ = CLUSTERS[name]
    y = cy + (PIN_HI_Y if kind == "HI" else PIN_LO_Y if kind == "LO"
              else PIN_TAP_Y0 + k * PIN_TAP_P)
    x = cx if side == "L" else cx + CLUS_W
    return x, y

def land_tap(net, name, k, from_x):
    """M3 trunk from a corridor x to the cluster tap pin (same layer M3)."""
    x, y = cluster_pin(name, "t", k)
    xin = x + 0.4 if CLUSTERS[name][1] == "L" else x - 0.4   # overlap into pin
    hseg(net, y, from_x, xin, 0.6)
    return y

def land_rail(net, name, kind, from_x):
    """M3 rail trunk to the cluster's M2 rail pin: via right at the edge."""
    x, y = cluster_pin(name, kind)
    side = CLUSTERS[name][1]
    vx = x - 2.6 if side == "L" else x + 2.6
    hseg(net, y, from_x, vx, RAIL_W)
    via_bend(net, vx, y, RAIL_W)
    xin = x + 0.4 if side == "L" else x - 0.4
    box(net, M2, min(vx, xin), y - RAIL_W / 2, max(vx, xin), y + RAIL_W / 2)
    return y

# ---- route all 48 taps ----
for name, ((ccx, ccy), side, taps) in CLUSTERS.items():
    for k, j in enumerate(taps):
        net = netname(j)
        edge, s0 = PADS[j]
        pin_x, pin_y = cluster_pin(name, "t", k)
        if name == "R3":
            # all 8 R3 taps come from T pads; leave the top corridor early at
            # a jog column over the art (junction via stacks in the corridor
            # would land their M2 pads inside the power strap stripes)
            assert edge == "T"
            xj = XJ_TAP0 - k * 1.3
            yT = DIE_H - TTRK[j]
            jx, jy = pad_iface(net, "T", s0, TTRK[j])
            via12(net, jx, yT, LANE_W)                # M2 trunk -> M1 track
            h1(net, yT, jx, xj, LANE_W)
            via12(net, xj, yT, LANE_W)                # M1 -> M2 jog (over art)
            vseg(net, xj, yT, pin_y, LANE_W)
            via_bend(net, xj, pin_y, LANE_W)          # M2 -> M3 branch
            land_tap(net, name, k, xj)
            continue
        if side == "L":
            xL = LTRK[j]
            if edge == "W":
                jx, jy = pad_iface(net, "W", s0, xL)
                if abs(pin_y - jy) < 1.3:
                    # trunk and branch M3 bands overlap: connect directly on
                    # M3 (two 0.55um-apart via stacks would DRC-notch)
                    land_tap(net, name, k, xL)
                    continue
                assert abs(pin_y - jy) >= 1.6         # no unmerged near-miss
                stack13(net, jx, jy, LANE_W)          # M3 trunk -> M1 lane
                v1(net, xL, jy, pin_y, LANE_W)
            else:                                     # edge == "B"
                yB = BTRK[j]
                jx, jy = pad_iface(net, "B", s0, yB)  # M2 trunk down to track
                via12(net, jx, yB, LANE_W)            # -> M1 corridor
                h1(net, yB, jx, xL, LANE_W)
                v1(net, xL, yB, pin_y, LANE_W)        # same layer bend: no via
            stack13(net, xL, pin_y, LANE_W)           # M1 lane -> M3 branch
            land_tap(net, name, k, xL)
        else:
            xR = DIE_W - RTRK[j]
            if edge == "E":
                jx, jy = pad_iface(net, "E", s0, RTRK[j])
                if abs(pin_y - jy) < 1.3:
                    land_tap(net, name, k, xR)
                    continue
                assert abs(pin_y - jy) >= 1.6
                stack13(net, jx, jy, LANE_W)
                v1(net, xR, jy, pin_y, LANE_W)
            elif edge == "B":
                yB = BTRK[j]
                jx, jy = pad_iface(net, "B", s0, yB)
                via12(net, jx, yB, LANE_W)
                h1(net, yB, jx, xR, LANE_W)
                v1(net, xR, yB, pin_y, LANE_W)
            else:                                     # edge == "T"
                yT = DIE_H - TTRK[j]
                jx, jy = pad_iface(net, "T", s0, TTRK[j])
                via12(net, jx, yT, LANE_W)
                h1(net, yT, jx, xR, LANE_W)
                v1(net, xR, yT, pin_y, LANE_W)
            stack13(net, xR, pin_y, LANE_W)
            land_tap(net, name, k, xR)

# ---- rails: spine W pads -> left corridor -> bottom -> right corridor ----
for net, s0, td in (("HI", W_S[0], HI_T), ("LO", W_S[1], LO_T)):
    jx, jy = pad_iface(net, "W", s0, td)
    stack13(net, jx, jy, RAIL_W)                      # M3 trunk -> M1 spine
    xL, yB, xR = td, td, DIE_W - td
    # left corridor spine: from bottom corner to the R2 branch
    lys = [land_rail(net, "R1", net, xL), land_rail(net, "R2", net, xL)]
    v1(net, xL, yB, max(lys), RAIL_W)
    # bottom spine (M1 corner bends just merge -- no vias)
    h1(net, yB, xL, xR, RAIL_W)
    # right corridor spine up to the highest branch (R3)
    rys = [land_rail(net, n, net, xR) for n in ("R5", "R6", "R4")]
    if net == "HI":
        # R3 HI pin y 1856.25 clears the strap stripes: direct branch
        rys.append(land_rail(net, "R3", net, xR))
    else:
        # R3 LO pin y 1861.25 is inside stripe 1: exit the corridor below it
        # and jog up over the art, west of the stripes (M3/M2, never M1)
        hseg(net, Y_LO_EXIT, xR, XJ_LO, RAIL_W)
        via_bend(net, XJ_LO, Y_LO_EXIT, RAIL_W)
        y3 = cluster_pin("R3", "LO")[1]
        vseg(net, XJ_LO, Y_LO_EXIT, y3, RAIL_W)
        via_bend(net, XJ_LO, y3, RAIL_W)
        land_rail(net, "R3", net, XJ_LO)
        rys.append(Y_LO_EXIT)
    v1(net, xR, yB, max(rys), RAIL_W)
    for y in lys:
        stack13(net, xL, y, RAIL_W)                   # M1 spine -> M3 branch
    for y in rys:
        stack13(net, xR, y, RAIL_W)
# tap trunk junction vias on rails' cluster branches are placed by land_rail;
# tap lanes get theirs in the loop above.

# boundary
box(None, BND, ORIGIN[0], ORIGIN[1], DIE_W - ORIGIN[0], DIE_H - ORIGIN[1])
ly.write("gds/puf_routes.gds")

# Declared SIZE is a small dummy (the placement box at [43,43] then ends at
# [343,343] -- inside the pad/corner margin, fully outside the core): OpenROAD
# initialize_floorplan hard-errors (IFP-0002) if a macro's DIMENSIONS exceed
# the core's, and the real footprint is die-wide. All PIN/OBS geometry is
# emitted at its true coordinates beyond the SIZE box, which LEF permits.
SIZEX, SIZEY = 300.0, 300.0
LNAME = {M1: "Metal1", M2: "Metal2", M3: "Metal3", M5: "Metal5"}
L = ["VERSION 5.7 ;", "  NOWIREEXTENSIONATPIN ON ;", '  DIVIDERCHAR "/" ;',
     '  BUSBITCHARS "[]" ;', "MACRO puf_routes", "  CLASS BLOCK ;",
     "  FOREIGN puf_routes ;", "  ORIGIN 0.000 0.000 ;",
     f"  SIZE {SIZEX:.3f} BY {SIZEY:.3f} ;"]
order = ["HI", "LO"] + [f"t{k}" for k in range(48)]
for net in order:
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
    rects = [s for n in order for s in NET_SHAPES[n] if s[0] == lyr]
    if not rects:
        continue
    L.append(f"      LAYER {LNAME[lyr]} ;")
    for _, x0, y0, x1, y1 in rects:
        L.append(f"        RECT {x0:.3f} {y0:.3f} {x1:.3f} {y1:.3f} ;")
L += ["  END", "END puf_routes", "END LIBRARY", ""]
open("lef/puf_routes.lef", "w").write("\n".join(L))

open("vh/puf_routes.v", "w").write(
    "// puf_routes: die-wide pre-drawn pad<->cluster straps (LEF pins so\n"
    "// abstract extraction merges the nets; see gen_routes_all.py).\n"
    "(* blackbox *)\nmodule puf_routes (" + ", ".join(order) + ");\n"
    "  inout " + ", ".join(order) + ";\nendmodule\n")
open("lib/puf_routes.lib", "w").write(
    "library (puf_routes) {\n"
    "  input_threshold_pct_fall: 50.0;\n  input_threshold_pct_rise: 50.0;\n"
    "  output_threshold_pct_fall: 50.0;\n  output_threshold_pct_rise: 50.0;\n"
    "  slew_lower_threshold_pct_fall: 20.0;\n  slew_lower_threshold_pct_rise: 20.0;\n"
    "  slew_upper_threshold_pct_fall: 80.0;\n  slew_upper_threshold_pct_rise: 80.0;\n"
    "  cell (puf_routes) {\n" +
    "".join(f"    pin ({p}) {{ direction: inout; }}\n" for p in order) +
    "  }\n}\n")

json.dump({"origin": ORIGIN, "clusters": {n: c[0] for n, c in CLUSTERS.items()}},
          open("puf_routes_spec.json", "w"), indent=1)
print(f"wrote gds/lef/vh/lib  origin={ORIGIN} size={SIZEX:.0f}x{SIZEY:.0f}")
print(f"macros_5v.yaml: routes_i location [{ORIGIN[0]}, {ORIGIN[1]}]")
