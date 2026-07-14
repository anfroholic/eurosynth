# SPDX-License-Identifier: Apache-2.0
"""Merge the crisp overlays into the freshly screened doge macro:
  1. the Metal1 dickbutt (ip/meme_dickbutt/gds/smallest_M1.gds) centred on the
     eye keepout -- placement grid-snapped to 5nm (see place_dickbutt.py)
  2. the crisp small-text polygons (gds/crisp_text.gds), already in macro um
     and 5nm-snapped by crisp_text.py -- no translation needed.
In:  gds/meme_txt.gds (make_gds + add_poly_fill output, top cell `meme`)
Out: gds/meme.gds (the shipping macro)
"""
import klayout.db as db

DOGE = "gds/meme_txt.gds"
BUTT = "../meme_dickbutt/gds/smallest_M1.gds"
TEXT = "gds/crisp_text.gds"
OUT = "gds/meme.gds"
M1 = (34, 0)

# dickbutt keepout centre in master px (matches clean_eye.KEEP_C)
PX, PY = 1915, 1031
GX = PX * 2790.0 / 4000.0
GY = 1499.5 - PY * 1500.0 / 2250.0
GRID = 5   # nm

ly = db.Layout()
ly.read(DOGE)
top = ly.top_cell()
assert top.name == "meme", top.name
m1 = ly.layer(*M1)

# 1. dickbutt
bl = db.Layout(); bl.read(BUTT)
assert abs(bl.dbu - ly.dbu) < 1e-9, "dbu mismatch"
reg = db.Region()
for s in bl.top_cell().shapes(bl.find_layer(*M1)).each():
    reg.insert(s.polygon)
bb = reg.bbox()
tx = round(GX / ly.dbu / GRID) * GRID - (bb.left + bb.right) // 2
ty = round(GY / ly.dbu / GRID) * GRID - (bb.bottom + bb.top) // 2
reg.transform(db.Trans(tx, ty))
top.shapes(m1).insert(reg)
fb = reg.bbox()
print(f"dickbutt: ({fb.left*ly.dbu:.2f},{fb.bottom*ly.dbu:.2f})-({fb.right*ly.dbu:.2f},{fb.top*ly.dbu:.2f}) um")

# 2. crisp text (already macro-local + snapped)
tl = db.Layout(); tl.read(TEXT)
assert abs(tl.dbu - ly.dbu) < 1e-9, "dbu mismatch"
n = 0
for s in tl.top_cell().shapes(tl.find_layer(*M1)).each():
    top.shapes(m1).insert(s.polygon)
    n += 1
print(f"crisp text: {n} polys merged")

ly.write(OUT)
print(f"wrote {OUT}")
