# SPDX-License-Identifier: Apache-2.0
"""Rebuild the dickbutt GDS from the user's hand-edited KLayout capture
(image/dickbutt_edited.png). The capture shows METAL as a purple crosshatch
(+ solid purple butt-dot ovals) and EMPTY as white cut-outs, on a pink boundary
hatch. We recover a clean metal mask, rasterise it at 0.5um/cell (36x48um total,
matching px1p5's footprint) and emit merged polygons + preview. Every feature is
>= 0.5um, comfortably over GF180's 0.30um metal min."""
import numpy as np
from PIL import Image
import klayout.db as db

SRC = "image/dickbutt_edited.png"
CELL_UM = 0.5                      # emitted grid pitch (overridable via argv)
GW, GH = None, None
ALL_METALS = [(34, 0), (36, 0), (42, 0), (46, 0), (81, 0)]
METALS = ALL_METALS
BOUND = (0, 0)


def _grow(m, n, op):
    for _ in range(n):
        t = m.copy()
        if op == "dil":
            t[1:] |= m[:-1]; t[:-1] |= m[1:]; t[:, 1:] |= m[:, :-1]; t[:, :-1] |= m[:, 1:]
        else:
            t[1:] &= m[:-1]; t[:-1] &= m[1:]; t[:, 1:] &= m[:, :-1]; t[:, :-1] &= m[:, 1:]
        m = t
    return m


def _declobber(m):
    m = m.copy()
    for _ in range(2):
        a = m[:-1, :-1]; b = m[:-1, 1:]; c = m[1:, :-1]; d = m[1:, 1:]
        m[:-1, 1:][a & d & ~b & ~c] = True
        m[:-1, :-1][b & c & ~a & ~d] = True
    return m


def extract_metal():
    im = np.array(Image.open(SRC).convert("RGB")).astype(int)
    R, G, B = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    # purple hatch [128,0,255] + dark oval [96,0,128]; exclude blue/red/olive grid
    metal = (R > 60) & (R < 205) & (G < 95) & (B > 115)
    metal = _grow(metal, 6, "dil")     # close: fuse hatch lines into solid fill...
    metal = _grow(metal, 6, "ero")     # ...keeping the big white cut-outs as holes
    return metal


def build(name, cell_um=CELL_UM, layers=METALS):
    metal = extract_metal()
    H0, W0 = metal.shape
    gh = round(48.0 / cell_um)
    gw = round(gh * W0 / H0)
    small = np.array(Image.fromarray((metal * 255).astype("uint8")).resize((gw, gh), Image.BILINEAR)) > 110
    small = _declobber(small)

    # preview
    up = max(1, 720 // gh)
    Image.fromarray(np.where(small, 0, 255).astype("uint8")).resize(
        (gw * up, gh * up), Image.NEAREST).save(f"out/preview_{name}.png")

    # GDS
    ly = db.Layout(); ly.dbu = 0.001
    top = ly.create_cell("meme_dickbutt")
    reg = db.Region()
    for y in range(gh):
        row = small[y]; x = 0
        while x < gw:
            if row[x]:
                x2 = x
                while x2 < gw and row[x2]:
                    x2 += 1
                reg.insert(db.Box(round(x * cell_um * 1000), round((gh - y - 1) * cell_um * 1000),
                                  round(x2 * cell_um * 1000), round((gh - y) * cell_um * 1000)))
                x = x2
            else:
                x += 1
    reg.merge()
    for lyr in layers:
        top.shapes(ly.layer(*lyr)).insert(reg)
    top.shapes(ly.layer(*BOUND)).insert(db.Box(0, 0, round(gw * cell_um * 1000), round(gh * cell_um * 1000)))
    ly.write(f"gds/{name}.gds")
    print(f"[{name}] {gw}x{gh} cells @ {cell_um}um = {gw*cell_um:.1f}x{gh*cell_um:.1f} um; "
          f"metal cells {int(small.sum())}; wrote gds/{name}.gds + out/preview_{name}.png")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        cell = float(sys.argv[1]); name = sys.argv[2]
        layers = ALL_METALS if len(sys.argv) < 4 or sys.argv[3] == "all" else [(34, 0)]
        build(name, cell, layers)
    else:
        build("meme_dickbutt")
