# SPDX-License-Identifier: Apache-2.0
"""Rescue the SMALL text: emit it as crisp Metal1 polygons and blank it out of
the image, so it bypasses the blur+halftone pipeline that destroys it (same
architecture as the dickbutt eye merge).

WHY: blur(r6) + control-halftone + the 2um min-feature erosion in make_gds
turn every stroke thinner than ~4um into unreadable dot-smear. The quote
strips (~28um text), credits (~20um), the angled Doctorow quote and the 34um
medallion captions all die. The BIG doge-speak words survive (thick strokes +
white halos) and are untouched here.

Two sources of crisp geometry:
  image/just_text.png -- artist-supplied text-only layer (same 4000x2250
    canvas as the master, black text on white). Supersedes the earlier
    dither-vs-text extraction heuristics, which damaged letters that touched
    dither dots. The thin canvas frame is stripped; ink = luma<128 taken 1:1.
  regenerated captions -- the medallion captions are programmatic (carve_puf
    text_um, 34um comicbd @4deg); re-render the same text/font/pos at 2x
    supersample (0.35um cells > 0.23um M1 floor) and rasterise.
Both go to gds/crisp_text.gds in MACRO um (transform gx=px*2790/4000,
gy=1499.5-py*1500/2250, same as place_dickbutt; all vertices snapped to the
5nm manufacturing grid -- off-grid = metal1_OFFGRID, bitten before). The
carved master gets the ink (dilated 14px, halo-style; blur(r6) re-greys ~4um of the wipe) painted WHITE ->
the halftone leaves a clean field and the crisp text sits isolated on it.

In:  image/ddoge_carved_db.png + image/just_text.png
Out: image/ddoge_carved_db_txt.png + gds/crisp_text.gds
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import klayout.db as db

SRC = "image/ddoge_carved_db.png"
TXT = "image/just_text.png"
DST = "image/ddoge_carved_db_txt.png"
GDS = "gds/crisp_text.gds"
M1 = (34, 0)
FRAME = 8            # px: the export has a thin black canvas frame -- strip it

# master px -> macro um (must match place_dickbutt.py)
SX, SY = 2790.0 / 4000.0, 1500.0 / 2250.0
Y0 = 1499.5
# die um -> master px (must match carve_puf.py)
ART_X0, ART_Y0 = 571.0, 532.0
PXX, PXY = 4000.0 / 2790.0, 2250.0 / 1500.0

# programmatic captions: (name, text, centre die um) -- from carve_puf.MEDALLIONS
CAPTIONS = [
    ("cap_unique",      "much unique",      (810.0, 1048.0)),
    ("cap_fingerprint", "very fingerprint", (1085.0, 1645.0)),
    ("cap_entropy",     "such entropy",     (2800.0, 1855.0)),
    ("cap_random",      "so random",        (2830.0, 1500.0)),
    ("cap_wow",         "wow",              (3080.0, 655.0)),
    ("cap_nft",         "very NFT",         (3060.0, 1110.0)),
]
CAP_H_UM, CAP_ANGLE, CAP_FONT = 34.0, 4.0, "C:/Windows/Fonts/comicbd.ttf"
SS = 2  # caption supersample (render px = master px / SS)

im = Image.open(SRC).convert("RGBA")
H, W = im.height, im.width

ly = db.Layout(); ly.dbu = 0.001
top = ly.create_cell("crisp_text")
m1 = ly.layer(*M1)

def snap5(nm):
    """GF180 manufacturing grid is 5nm; off-grid vertices = metal1_OFFGRID."""
    return round(nm / 5) * 5

def px_region(mask, x_off, y_off, k=1):
    """Boolean mask at k-x supersampled master px -> merged Region (macro dbu).
    (x_off, y_off) are the mask origin in the SAME kx units."""
    r = db.Region()
    ys, xs = np.nonzero(mask)
    for y in np.unique(ys):
        row = xs[ys == y]
        splits = np.nonzero(np.diff(row) > 1)[0]
        starts = np.concatenate(([0], splits + 1))
        ends = np.concatenate((splits, [len(row) - 1]))
        py = y + y_off
        gy1 = snap5(round((Y0 - py * SY / k) * 1000))
        gy0 = snap5(round((Y0 - (py + 1) * SY / k) * 1000))
        for s, e in zip(starts, ends):
            px0, px1 = row[s] + x_off, row[e] + 1 + x_off
            r.insert(db.Box(snap5(round(px0 * SX / k * 1000)), gy0,
                            snap5(round(px1 * SX / k * 1000)), gy1))
    r.merge()
    return r

def close_region(r):
    """Geometric closing (+120nm/-120nm): anti-aliased diagonal pixel steps
    create corner-touching polygons = zero-width pinches and zero-space corner
    gaps (174 M1 width/space violations in the first merged macro). Closing
    fills anything narrower than 0.24um; real letter gaps are >=0.6um. 120 is
    a 5nm multiple, so vertices stay on the manufacturing grid."""
    r.size(120); r.merge(); r.size(-120); r.merge()
    return r

def caption_layer(text, k):
    """Render one caption exactly like carve_puf.text_um at k-x supersample."""
    fpx = round(CAP_H_UM * PXY * k)
    font = ImageFont.truetype(CAP_FONT, fpx)
    bb = font.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    lay = Image.new("L", (tw + 8 * k, th + 8 * k), 0)
    ImageDraw.Draw(lay).text((4 * k - bb[0], 4 * k - bb[1]), text, font=font, fill=255)
    lay = lay.rotate(CAP_ANGLE, expand=True, resample=Image.BICUBIC)
    return np.asarray(lay) > 127, lay.size

paint = np.zeros((H, W), bool)          # px to wipe white in the image
total = 0

# ---- artist text layer, 1:1 ----
tl = np.asarray(Image.open(TXT).convert("L"))
assert tl.shape == (H, W), f"just_text.png is {tl.shape}, master is {(H, W)}"
ink = tl < 128
ink[:FRAME, :] = ink[-FRAME:, :] = ink[:, :FRAME] = ink[:, -FRAME:] = False
keep = close_region(px_region(ink, 0, 0))
total += keep.count()
top.shapes(m1).insert(keep)
print(f"just_text.png: {keep.count()} polys, {keep.area()/1e6:.0f} um^2 ink")
paint |= np.asarray(Image.fromarray((ink * 255).astype(np.uint8))
                    .filter(ImageFilter.MaxFilter(29))) > 0

# ---- regenerated captions ----
for name, text, (dx, dy) in CAPTIONS:
    pcx, pcy = (dx - ART_X0) * PXX, 2250.0 - (dy - ART_Y0) * PXY
    mask, (lw, lh) = caption_layer(text, SS)
    ox = round(pcx * SS - lw / 2)
    oy = round(pcy * SS - lh / 2)
    keep = close_region(px_region(mask, ox, oy, k=SS))
    total += keep.count()
    top.shapes(m1).insert(keep)
    print(f"{name:16s} regenerated: {keep.count():4d} polys, {keep.area()/1e6:7.0f} um^2")
    mask1, (lw1, lh1) = caption_layer(text, 1)
    ox1, oy1 = round(pcx - lw1 / 2), round(pcy - lh1 / 2)
    m1im = Image.fromarray((mask1 * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(29))
    d = np.asarray(m1im) > 0
    ys, xs = np.nonzero(d)
    paint[np.clip(ys + oy1, 0, H - 1), np.clip(xs + ox1, 0, W - 1)] = True

ly.write(GDS)
WHITE = np.array([239, 239, 239, 255], np.uint8)
arr = np.asarray(im).copy()
arr[paint] = WHITE
Image.fromarray(arr).save(DST)
# The same mask must be re-applied AFTER the blur (build_art.py): blurring the
# wiped master leaves a grey GRADIENT at the wipe edge, and the halftone grows
# dots through the marginal-spacing regime there (10nm dot-to-dot gaps).
Image.fromarray((paint * 255).astype(np.uint8)).save("image/_text_wipe_mask.png")
print(f"{GDS}: {total} M1 polys;  {DST}: {int(paint.sum())} px wiped white")
