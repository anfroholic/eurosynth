# SPDX-License-Identifier: Apache-2.0
"""Standalone 'dickbutt' line-art macro -- iterate on look + manufacturability.

The classic dickbutt is a LINE DRAWING: thin black outline, white interior. On
silicon we render the outline strokes as solid metal (all 5 metals stacked =
opaque art, same as the doge macro) and the interior as empty.

Physical stroke width is fixed by the source proportions and the chosen figure
HEIGHT, NOT by the raster pitch:  w_um = (stroke_px / fig_px) * height_um.
The source's thinnest meaningful strokes are ~2 px of a 313 px figure, so at a
naive height they fall below the ~2 um metal floor and vanish. Two levers keep
them:  (1) make the figure taller,  (2) --thicken the strokes (dilate) so the
thin facial/finger lines come up to min width while the drawing still reads.

Pipeline:  crop to ink -> grayscale -> resize to the metal grid (LANCZOS, smooth
edges) -> threshold -> optional thicken -> 2x2 morphological open + declobber
(guarantees >= 2 grid-px = 2*pixel_size um min width AND min space, no acute
diagonal pinches, exactly like make_gds) -> merged metal boxes + a preview PNG
showing the true as-fabricated metal.

Usage:
  python script/build.py --height-um 150 --pixel-size 0.5 --thicken 1 --name h150
Outputs gds/<name>.gds and out/preview_<name>.png (black = metal).
"""
import argparse
import numpy as np
from PIL import Image
import klayout.db as db

SRC = "image/dick-butt-pixel-art.jpg"
# GF180 metal stack (Metal1..Metal5) -- stacking all five = opaque, and the tile
# trivially clears every per-layer metal-density floor.
METALS = [(34, 0), (36, 0), (42, 0), (46, 0), (81, 0)]
BOUND = (0, 0)


def _erode(m):
    e = m.copy()
    e[1:, :] &= m[:-1, :]; e[:-1, :] &= m[1:, :]
    e[:, 1:] &= m[:, :-1]; e[:, :-1] &= m[:, 1:]
    return e


def _dilate(m):
    d = m.copy()
    d[1:, :] |= m[:-1, :]; d[:-1, :] |= m[1:, :]
    d[:, 1:] |= m[:, :-1]; d[:, :-1] |= m[:, 1:]
    return d


def _open2(metal):
    """2x2 morphological opening (erode then dilate) -- removes sub-2px slivers
    so nothing is thinner than 2 grid pixels. metal is a bool array."""
    e = metal.copy()
    for dx, dy in [(-1, 0), (0, -1), (-1, -1)]:
        e &= np.roll(np.roll(metal, dy, 0), dx, 1)
    d = e.copy()
    for dx, dy in [(1, 0), (0, 1), (1, 1)]:
        d |= np.roll(np.roll(e, dy, 0), dx, 1)
    return d


def _declobber(metal):
    """Break diagonal-only corner touches (2x2 checkerboard): a metal-metal
    diagonal is a zero-width pinch, the complementary empty-empty diagonal a
    zero-space pinch; filling one metal corner removes both."""
    m = metal.copy()
    for _ in range(2):
        a = m[:-1, :-1]; b = m[:-1, 1:]; c = m[1:, :-1]; d = m[1:, 1:]
        fill_bc = a & d & ~b & ~c          # metal on \ , empty on /
        fill_ad = b & c & ~a & ~d          # metal on / , empty on \
        m[:-1, 1:][fill_bc] = True         # fill b
        m[:-1, :-1][fill_ad] = True        # fill a
    return m


def build(height_um, pixel_size, thicken, thr, name):
    im = Image.open(SRC).convert("L")
    a = np.array(im)
    ink = a < thr
    ys, xs = np.where(ink)
    pad = 6
    y0, y1 = max(0, ys.min() - pad), min(a.shape[0], ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(a.shape[1], xs.max() + 1 + pad)
    crop = im.crop((x0, y0, x1, y1))
    fig_px = (y1 - y0)

    # resize to the metal grid: figure height -> height_um / pixel_size grid rows
    gh = max(1, round(height_um / pixel_size))
    gw = max(1, round(crop.width * gh / crop.height))
    g = crop.resize((gw, gh), Image.LANCZOS)
    metal = np.array(g) < thr

    for _ in range(thicken):
        metal = _dilate(metal)

    metal = _declobber(_open2(metal))

    # --- report actual min stroke on-silicon ---
    survivors = []
    m = metal.copy()
    for _ in range(6):
        m = _erode(m)
        survivors.append(int(m.sum()))
    thin_px = 1 + next((k for k, s in enumerate(survivors) if s == 0), 6)  # ~half-width*2
    min_w_um = thin_px * pixel_size
    print(f"[{name}] figure {gw}x{gh} grid @ {pixel_size}um = "
          f"{gw*pixel_size:.1f}x{gh*pixel_size:.1f} um; "
          f"metal cells {int(metal.sum())}; approx thinnest stroke ~{min_w_um:.1f} um")

    # --- preview PNG (true as-fab metal: black = metal) ---
    prev = np.where(metal, 0, 255).astype(np.uint8)
    P = Image.fromarray(prev, "L")
    up = max(1, 900 // gh)
    P.resize((gw * up, gh * up), Image.NEAREST).save(f"out/preview_{name}.png")

    # --- GDS: merge cells into rectangles per row-run, on all metal layers ---
    ly = db.Layout(); ly.dbu = 0.001
    top = ly.create_cell("meme_dickbutt")
    reg = db.Region()
    H = gh
    for y in range(gh):
        row = metal[y]
        x = 0
        while x < gw:
            if row[x]:
                x2 = x
                while x2 < gw and row[x2]:
                    x2 += 1
                # y flip so image-top maps to layout-top
                reg.insert(db.Box(round(x * pixel_size * 1000),
                                  round((H - y - 1) * pixel_size * 1000),
                                  round(x2 * pixel_size * 1000),
                                  round((H - y) * pixel_size * 1000)))
                x = x2
            else:
                x += 1
    reg.merge()
    for lyr in METALS:
        top.shapes(ly.layer(*lyr)).insert(reg)
    top.shapes(ly.layer(*BOUND)).insert(
        db.Box(0, 0, round(gw * pixel_size * 1000), round(gh * pixel_size * 1000)))
    ly.write(f"gds/{name}.gds")
    print(f"[{name}] wrote gds/{name}.gds + out/preview_{name}.png")


def build_pixel(sprite, cell_um, thr, name):
    """Pixel-art render for the hand-edited sprite: map each sprite pixel 1:1 to
    a cell_um metal (ink) / empty square. NO 2x2 open (that would erase the
    single-pixel eye-whites and butt-dots the user added); declobber only, to
    break diagonal corner pinches. min width = min space = cell_um, so cell_um
    >= ~1 keeps clear of GF180 metal min-width/space (0.3/0.28 um)."""
    im = Image.open(sprite).convert("RGBA")
    a = np.array(im)
    op = a[:, :, 3] > 40
    lum = a[:, :, :3].mean(2)
    metal = op & (lum < thr)                      # ink = opaque & dark
    ys, xs = np.where(op)                         # crop to the figure's extent
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    metal = metal[y0:y1, x0:x1]
    metal = _declobber(metal)                     # no _open2: keep 1px features

    gh, gw = metal.shape
    print(f"[{name}] pixel-art {gw}x{gh} px @ {cell_um}um/px = "
          f"{gw*cell_um:.0f}x{gh*cell_um:.0f} um; metal cells {int(metal.sum())}; "
          f"min feature = {cell_um}um")

    prev = np.where(metal, 0, 255).astype(np.uint8)
    up = max(1, 640 // gh)
    Image.fromarray(prev).resize((gw * up, gh * up), Image.NEAREST).save(f"out/preview_{name}.png")

    ly = db.Layout(); ly.dbu = 0.001
    top = ly.create_cell("meme_dickbutt")
    reg = db.Region()
    for y in range(gh):
        row = metal[y]; x = 0
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
    for lyr in METALS:
        top.shapes(ly.layer(*lyr)).insert(reg)
    top.shapes(ly.layer(*BOUND)).insert(db.Box(0, 0, round(gw * cell_um * 1000), round(gh * cell_um * 1000)))
    ly.write(f"gds/{name}.gds")
    print(f"[{name}] wrote gds/{name}.gds + out/preview_{name}.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["line", "pixel"], default="line")
    ap.add_argument("--sprite", default="image/dickbutt_32_rgba.png")
    ap.add_argument("--cell-um", type=float, default=2.0, help="pixel mode: um per sprite pixel")
    ap.add_argument("--height-um", type=float, default=150.0)
    ap.add_argument("--pixel-size", type=float, default=0.5)
    ap.add_argument("--thicken", type=int, default=0, help="stroke dilation passes")
    ap.add_argument("--thr", type=int, default=128, help="ink threshold (0-255)")
    ap.add_argument("--name", default="db")
    a = ap.parse_args()
    if a.mode == "pixel":
        build_pixel(a.sprite, a.cell_um, a.thr, a.name)
    else:
        build(a.height_um, a.pixel_size, a.thicken, a.thr, a.name)
