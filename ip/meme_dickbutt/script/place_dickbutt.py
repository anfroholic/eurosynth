# SPDX-License-Identifier: Apache-2.0
"""Merge the crisp Metal1 dickbutt (gds/smallest_M1.gds) into the doge macro at
the eye keepout. The dickbutt keeps its OWN 0.23um grid -- it is NOT re-screened
at the doge's 1um pitch (that would erase it). We drop its Metal1 (34/0) polygons,
centred on the white keepout, into a region that screened to EMPTY, so the
line-art sits isolated on a clean field (findable under SEM, DRC-clean).

Placement centre in macro-um comes from the master-px keepout centre via the
make_gds transform:  gx = px * 2790/4000 ,  gy = 1499.5 - py * 1500/2250 .
"""
import sys
import klayout.db as db

DOGE = "gds/meme_db.gds"
BUTT = "../meme_dickbutt/gds/smallest_M1.gds"
OUT = "gds/meme_db_butt.gds"
M1 = (34, 0)

# keepout centre in master px (matches clean_eye.KEEP_C)
PX, PY = 1915, 1031
GX = PX * 2790.0 / 4000.0
GY = 1499.5 - PY * 1500.0 / 2250.0


def main():
    ly = db.Layout()
    ly.read(DOGE)
    top = ly.top_cell()
    m1 = ly.layer(*M1)

    bl = db.Layout()
    bl.read(BUTT)
    assert abs(bl.dbu - ly.dbu) < 1e-9, "dbu mismatch"     # both 0.001 -> no scaling
    btop = bl.top_cell()
    reg = db.Region()
    for s in btop.shapes(bl.find_layer(*M1)).each():
        reg.insert(s.polygon)

    bb = reg.bbox()                                         # dickbutt dbu (== doge dbu)
    cx = (bb.left + bb.right) // 2
    cy = (bb.bottom + bb.top) // 2
    # snap placement to GF180's 5nm manufacturing grid: the sprite's own coords
    # are multiples of 230nm (on-grid), so a grid-multiple offset keeps every
    # vertex on-grid. An un-snapped offset put the whole dickbutt 2nm off-grid
    # -> 294 metal1_OFFGRID errors (the ONLY DRC fails in the full-chip signoff).
    GRID = 5
    tx = round(GX / ly.dbu / GRID) * GRID                   # keepout centre, grid-snapped
    ty = round(GY / ly.dbu / GRID) * GRID
    reg.transform(db.Trans(tx - cx, ty - cy))              # integer translate
    top.shapes(m1).insert(reg)

    ly.write(OUT)
    fb = reg.bbox()
    print(f"merged dickbutt Metal1 -> {OUT}")
    print(f"  keepout centre macro-um = ({GX:.1f}, {GY:.1f})")
    print(f"  dickbutt bbox in doge (um) = "
          f"({fb.left*ly.dbu:.2f},{fb.bottom*ly.dbu:.2f})-"
          f"({fb.right*ly.dbu:.2f},{fb.top*ly.dbu:.2f})")


if __name__ == "__main__":
    main()
