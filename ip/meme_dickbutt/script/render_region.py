# SPDX-License-Identifier: Apache-2.0
"""Rasterise one metal layer of a GDS over a small um window, so we can eyeball
the merged dickbutt sitting in the eye keepout. metal = dark."""
import sys
import klayout.db as db
from PIL import Image, ImageDraw

GDS = sys.argv[1] if len(sys.argv) > 1 else "gds/meme_db_butt.gds"
X0, Y0, X1, Y1 = 1285.0, 768.0, 1388.0, 858.0     # um window (eye)
LAYER = (34, 0)                                    # Metal1
PPU = 14                                            # px per um
OUT = sys.argv[2] if len(sys.argv) > 2 else "../meme_dickbutt/out/merged_eye_m1.png"


def main():
    ly = db.Layout()
    ly.read(GDS)
    top = ly.top_cell()
    li = ly.find_layer(*LAYER)
    W = round((X1 - X0) * PPU)
    H = round((Y1 - Y0) * PPU)
    im = Image.new("L", (W, H), 235)               # empty = light
    d = ImageDraw.Draw(im)
    box = db.Box(round(X0 / ly.dbu), round(Y0 / ly.dbu),
                 round(X1 / ly.dbu), round(Y1 / ly.dbu))
    it = db.RecursiveShapeIterator(ly, top, li, box)
    n = 0
    while not it.at_end():
        poly = it.shape().polygon
        if poly is not None:
            gp = poly.transformed(it.trans())
            pts = []
            for p in gp.each_point_hull():
                ux = (p.x * ly.dbu - X0) * PPU
                uy = (Y1 - p.y * ly.dbu) * PPU     # flip y for image
                pts.append((ux, uy))
            if len(pts) >= 3:
                d.polygon(pts, fill=30)
                n += 1
        it.next()
    im.save(OUT)
    print(f"{OUT}: {n} Metal1 polys in window {X0},{Y0}-{X1},{Y1} um ({W}x{H}px)")


if __name__ == "__main__":
    main()
