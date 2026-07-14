# SPDX-License-Identifier: Apache-2.0
"""Preview the REAL fabricated eye: screen the doge eye to true 1um metal, then
Boolean-subtract the line-art dickbutt from the pupil (metal AND NOT butt).
Shows exactly what silicon looks like, and reports the true on-grid stroke width
so we know the cut-out gaps clear the 2um min-space floor."""
import sys
import numpy as np
from PIL import Image
sys.path.insert(0, "../meme/script")
import make_gds as M

UX, UY = 2790 / 4000, 1500 / 2250      # master-px -> die um
DOGE = "../meme/image/doge.png"
JPG = "image/dick-butt-pixel-art.jpg"

# eye crop in master px, and the pupil centre (die-um placement)
CX0, CY0, CX1, CY1 = 1740, 780, 2260, 1220
PUP_MX, PUP_MY = 1985, 1010


def dilate(m, n):
    for _ in range(n):
        d = m.copy()
        d[1:] |= m[:-1]; d[:-1] |= m[1:]; d[:, 1:] |= m[:, :-1]; d[:, :-1] |= m[:, 1:]
        m = d
    return m


def min_width_px(m):
    """largest k such that k erosions leave something = ~half the thinnest... use
    a simple thinnest-run probe: min over rows/cols of longest True run is noisy;
    instead report the fraction removed by one 2x2 open (0 = all >=2px)."""
    opened = M._open2(Image.fromarray(np.where(m, 0, 255).astype("uint8"), "L").convert("1"))
    o = np.array(opened.convert("L")) < 128
    lost = int((m & ~o).sum())
    return lost


def build(height_um, dilate_n, name, gcx, gcy):
    # --- 1um metal of the eye ---
    eye = Image.open(DOGE).convert("RGB").crop((CX0, CY0, CX1, CY1))
    gw, gh = round(eye.width * UX), round(eye.height * UY)
    bw = M._control_halftone(eye, gw, gh, 5, 20, "")     # doge recipe: screen5 solid20
    metal = np.array(bw.convert("L")) < 128              # True = metal

    # --- line-art dickbutt ink mask at height_um (1um grid) ---
    jpg = Image.open(JPG).convert("L")
    a = np.array(jpg); ink = a < 128
    ys, xs = np.where(ink)
    crop = jpg.crop((xs.min() - 4, ys.min() - 4, xs.max() + 5, ys.max() + 5))
    h = round(height_um); w = round(crop.width * h / crop.height)
    bm = np.array(crop.resize((w, h), Image.LANCZOS)) < 128
    bm = dilate(bm, dilate_n)
    lost = min_width_px(bm)
    print(f"[{name}] dickbutt {w}x{h} um, dilate {dilate_n}: "
          f"{'ALL cut-lines >= 2um (clean)' if lost == 0 else str(lost)+' cells thinner than 2um'}")

    # --- place + subtract: explicit grid centre (on the SOLID dark pupil) ---
    x0, y0 = gcx - w // 2, gcy - h // 2
    sub = metal.copy()
    yy, xx = np.where(bm)
    sub[y0 + yy, x0 + xx] = False                        # AND NOT butt

    # --- render zoomed ---
    up = 3
    out = Image.fromarray(np.where(sub, 22, 235).astype("uint8"))
    out.resize((gw * up, gh * up), Image.NEAREST).save(f"out/{name}.png")
    print(f"[{name}] wrote out/{name}.png ({gw}x{gh} um eye, dickbutt at grid {x0},{y0})")


def build_glint(height_um, radius_um, name, gcx, gcy):
    """User's concept: a clean white CIRCLE glint (empty) with a BLACK line-art
    dickbutt (metal strokes) inside it. Renders true 1um metal + reports whether
    the dickbutt strokes clear the 2um min-width floor."""
    eye = Image.open(DOGE).convert("RGB").crop((CX0, CY0, CX1, CY1))
    gw, gh = round(eye.width * UX), round(eye.height * UY)
    bw = M._control_halftone(eye, gw, gh, 5, 20, "")
    metal = np.array(bw.convert("L")) < 128

    # white circle glint = empty
    Y, X = np.ogrid[:gh, :gw]
    circle = (X - gcx) ** 2 + (Y - gcy) ** 2 <= radius_um ** 2
    metal[circle] = False

    # line-art dickbutt ink at height_um, auto-dilate until every stroke >= 2um
    jpg = Image.open(JPG).convert("L"); a = np.array(jpg); ink = a < 128
    ys, xs = np.where(ink); crop = jpg.crop((xs.min() - 4, ys.min() - 4, xs.max() + 5, ys.max() + 5))
    h = round(height_um); w = round(crop.width * h / crop.height)
    bm = np.array(crop.resize((w, h), Image.LANCZOS)) < 128
    d = 0
    while min_width_px(bm) > 0 and d < 4:
        bm = dilate(bm, 1); d += 1
    ok = min_width_px(bm)
    print(f"[{name}] circle r{radius_um}um, dickbutt {w}x{h}um, auto-dilate {d} -> "
          f"{'strokes clean (>=2um)' if ok == 0 else str(ok)+' cells still <2um'}")

    # place dickbutt (metal) centred in the circle
    x0, y0 = gcx - w // 2, gcy - h // 2
    yy, xx = np.where(bm)
    metal[y0 + yy, x0 + xx] = True

    up = 3
    Image.fromarray(np.where(metal, 22, 235).astype("uint8")).resize(
        (gw * up, gh * up), Image.NEAREST).save(f"out/{name}.png")
    print(f"[{name}] wrote out/{name}.png")


def build_glint_pixel(cell_um, radius_um, name, gcx, gcy):
    """User's circle-glint concept + the manufacturable PIXEL sprite: a clean
    white circle (empty) with the black pixel-art dickbutt (metal) inside. The
    sprite's features are uniform cell_um by construction, so it stays crisp."""
    eye = Image.open(DOGE).convert("RGB").crop((CX0, CY0, CX1, CY1))
    gw, gh = round(eye.width * UX), round(eye.height * UY)
    metal = np.array(M._control_halftone(eye, gw, gh, 5, 20, "").convert("L")) < 128

    Y, X = np.ogrid[:gh, :gw]
    metal[(X - gcx) ** 2 + (Y - gcy) ** 2 <= radius_um ** 2] = False   # white circle

    sp = np.array(Image.open("image/dickbutt_32_rgba.png").convert("RGBA"))
    op = sp[:, :, 3] > 40; lum = sp[:, :, :3].mean(2); m = op & (lum < 128)
    ys, xs = np.where(op); m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    k = int(round(cell_um))                                            # cells per sprite px (1um grid)
    m = np.kron(m, np.ones((k, k), bool))
    h, w = m.shape
    x0, y0 = gcx - w // 2, gcy - h // 2
    yy, xx = np.where(m)
    metal[y0 + yy, x0 + xx] = True
    print(f"[{name}] circle r{radius_um}um + pixel dickbutt {w}x{h}um @ {cell_um}um/px")
    up = 3
    Image.fromarray(np.where(metal, 22, 235).astype("uint8")).resize(
        (gw * up, gh * up), Image.NEAREST).save(f"out/{name}.png")


if __name__ == "__main__":
    build_glint_pixel(2.0, 44, "glint_pixel", 195, 120)
    build_glint(150, 92, "glint_line_big", 200, 150)   # elegant but large line-art
