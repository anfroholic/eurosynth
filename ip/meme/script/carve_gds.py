# SPDX-License-Identifier: Apache-2.0
"""Carve the PUF cluster keepouts + routing channels out of meme.gds in GDS
space (exact um rects from puf_spec.json).

Why this exists: carve_puf.py paints the keepouts into the master IMAGE, but
the image pixel grid (0.70 x 0.67 um/px) quantizes the box edges, and the
round-7 cluster (80.6 x 44.9) consumes the ENTIRE keepout that carve_puf
painted (old 68.6 x 32.9 cluster + 6 um margin) -- art pixels ended up
nibbling 0.15..0.3 um into the box (M1.2a etc. at every cluster edge).
Worse, add_poly_fill.py runs after the image screen and back-fills the
carved white areas with poly2 lines, which land on top of the bank resistors
(PRES.4 / PL.3a / PP.9 / SB.12 / 'can't overlap' storms at die level).

So: after make_gds + add_poly_fill, subtract the exact spec rects:
  metals (34/36/42/46/81 /0): keepouts + channels expanded 0.40 um
         (>= M1 space 0.23 / M2-M3 space 0.28 to the cluster/branch copper)
  poly2 (30/0):               keepouts expanded 1.50 um
         (>= PRES.4's 1.2 um resistor-poly to unrelated-poly; channels hold
          only M2/M3 branch copper -- poly fill under metal is legal)

Idempotent (subtracting already-empty area is a no-op); runs in place on
gds/meme.gds as the last step of the Makefile art target.
"""
import json

import klayout.db as db

GDS = "gds/meme.gds"
SPEC = "puf_spec.json"
ART_X0, ART_Y0 = 571.0, 532.0        # die um of art origin

MET_LAYERS = [(34, 0), (36, 0), (42, 0), (46, 0), (81, 0)]
POLY_LAYER = (30, 0)
MET_MARGIN, POLY_MARGIN = 0.40, 1.50
# min widths for the post-carve sliver opening (see below)
MINW = {(34, 0): 0.23, (36, 0): 0.28, (42, 0): 0.28, (46, 0): 0.28,
        (81, 0): 0.44, (30, 0): 0.18}

spec = json.load(open(SPEC))
keepouts = [b["cluster_keepout"] for b in spec["banks"]]
channels = [c["rect_die_um"] for c in spec["channels"]]

ly = db.Layout()
ly.read(GDS)
top = ly.top_cell()
dbu = ly.dbu


def region(rects, margin):
    r = db.Region()
    for x0, y0, x1, y1 in rects:
        r.insert(db.Box(round((x0 - ART_X0 - margin) / dbu),
                        round((y0 - ART_Y0 - margin) / dbu),
                        round((x1 - ART_X0 + margin) / dbu),
                        round((y1 - ART_Y0 + margin) / dbu)))
    return r


carves = [(li, region(keepouts + channels, MET_MARGIN)) for li in MET_LAYERS]
carves.append((POLY_LAYER, region(keepouts, POLY_MARGIN)))

for (lnum, dt), carve in carves:
    li = ly.layer(lnum, dt)
    before = db.Region(top.begin_shapes_rec(li))
    removed = before & carve
    after = before - carve
    # The subtraction cuts art pixels along the carve edges, leaving
    # sub-min-width slivers (round-8: 39 Mx.1 flags per metal). Open only the
    # polygons touching the carve (erode+dilate by minw/2 -- exact for the
    # rectilinear art, drops anything thinner than minw).
    h = round(MINW[(lnum, dt)] / 2 / dbu)
    cand = after.interacting(carve)
    opened = cand.sized(-h).sized(h)
    sliver_area = (cand - opened).area() * dbu * dbu
    after = (after - cand) + opened
    top.shapes(li).clear()
    top.shapes(li).insert(after)
    print(f"{lnum}/{dt}: carved {removed.area() * dbu * dbu:.0f} um^2, "
          f"slivers {sliver_area:.2f} um^2 "
          f"({before.count()} -> {after.count()} shapes)")

ly.write(GDS)
print(f"carved {len(keepouts)} keepouts + {len(channels)} channels into {GDS}")
