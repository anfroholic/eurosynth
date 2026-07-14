# SPDX-License-Identifier: Apache-2.0
"""Carve the PUF 'dogecoin medallions' into the ddoge master image.

Reads image/ddoge.png (MASTER -- never modified), writes:
  image/ddoge_carved.png   -- art with 6 coin medallions + trace channels painted
  puf_spec.json            -- all geometry in die-um: cluster keep-outs, channel
                              rects, coin centers. Single source of truth for the
                              bank placements and the meme LEF OBS carving.

Concept: each of the user's 6 approved free regions (freespace.svg) hosts a
dogecoin medallion -- halftone coin ring, Comic Sans "D-stroke" glyph, and the
8-bank PUF cluster keep-out sitting under the glyph like a mint mark. A walled
'PCB trace' channel runs from the cluster to the nearest art edge; the real
routed metal will run inside it. Doge-speak captions where the region allows.

Painted BLACK -> metal (ring/glyph/caption become halftone-screened art).
Painted WHITE -> empty  (keep-out for banks + routing channels).

Geometry mapping (art macro 2790x1500 um at die [571,532]; image 4000x2250):
  px/um is ANISOTROPIC: x 4000/2790 = 1.4337, y 2250/1500 = 1.5
  Circles in um-space are ellipses in px-space (drawn per-axis) so they are
  round on silicon.
"""
import json
from PIL import Image, ImageDraw, ImageFont

SRC = "image/ddoge.png"
DST = "image/ddoge_carved.png"
SPEC = "puf_spec.json"

ART_X0, ART_Y0 = 571.0, 532.0        # die um of art origin
ART_W, ART_H = 2790.0, 1500.0
IMG_W, IMG_H = 4000, 2250
SX = IMG_W / ART_W                    # 1.4337 px/um
SY = IMG_H / ART_H                    # 1.5    px/um

def to_px(die_x, die_y):
    """die um -> image px (y flips)."""
    return ((die_x - ART_X0) * SX, IMG_H - (die_y - ART_Y0) * SY)

# ---- cluster geometry (die um) ----
# 8 banks (12.65 x 13.45 um) in a 4x2 grid, 6 um gaps, + 4 um border margin.
BANK_W, BANK_H, GAP = 12.65, 13.45, 6.0
CLUS_W = 4 * BANK_W + 3 * GAP         # 68.6
CLUS_H = 2 * BANK_H + GAP             # 32.9
KO_MARGIN = 6.0                       # white margin around the cluster
FRAME = 4.0                           # black frame wall around the keep-out
CHAN_W = 22.0                         # routing channel width (um)
CHAN_WALL = 4.0                       # black channel walls

# ---- the six medallions: per-region placement (die um) ----
# region: user rect (from freespace.svg); coin diameter sized to fit its height.
MEDALLIONS = [
    # name    coin centre (die um)   coin dia  channel dir  caption, caption pos (die um)
    ("R1", (720.0, 1168.0), 170.0, "left",  "much unique",      (810.0, 1048.0)),
    # caption to the RIGHT of the coin (within region R2), clear of "so chips"
    ("R2", (800.0, 1645.0), 150.0, "left",  "very fingerprint", (1085.0, 1645.0)),
    # channel goes RIGHT (region reaches the art's right edge); "up" would cut
    # through the top quote strip.
    ("R3", (3140.0, 1891.0), 140.0, "right", "such entropy",    (2800.0, 1855.0)),
    ("R4", (3240.0, 1536.0), 140.0, "right","so random",        (2830.0, 1500.0)),
    ("R5", (3230.0, 735.0), 170.0, "right", "wow",              (3080.0, 655.0)),
    # R6 is only ~111 um tall -> no coin; a plain 'chip pill' frame instead.
    ("R6", (3180.0, 1152.0), 0.0,  "right", "very NFT",         (3060.0, 1110.0)),
]

im = Image.open(SRC).convert("RGBA")
dr = ImageDraw.Draw(im)
BLACK, WHITE = (26, 26, 26, 255), (239, 239, 239, 255)

def ellipse_um(cx, cy, rx_um, ry_um, fill=None, outline=None, width_um=4.0):
    px, py = to_px(cx, cy)
    rx, ry = rx_um * SX, ry_um * SY
    dr.ellipse([px - rx, py - ry, px + rx, py + ry], fill=fill,
               outline=outline, width=max(2, round(width_um * SX)))

def rect_um(x0, y0, x1, y1, fill):
    p0 = to_px(x0, y1); p1 = to_px(x1, y0)   # note y flip: y1 -> top
    dr.rectangle([p0[0], p0[1], p1[0], p1[1]], fill=fill)

def text_um(s, cx, cy, h_um, font_file="comicbd.ttf", fill=BLACK, angle=0.0):
    """Centered text, height ~h_um on silicon. Drawn via a rotated overlay."""
    fpx = round(h_um * SY)
    font = ImageFont.truetype(f"C:/Windows/Fonts/{font_file}", fpx)
    bb = font.getbbox(s)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    lay = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((4 - bb[0], 4 - bb[1]), s, font=font, fill=fill)
    if angle:
        lay = lay.rotate(angle, expand=True, resample=Image.BICUBIC)
    px, py = to_px(cx, cy)
    im.alpha_composite(lay, (round(px - lay.width / 2), round(py - lay.height / 2)))

spec = {"units": "die_um", "banks": [], "channels": [], "coins": []}

for name, (cx, cy), dia, chan_dir, caption, cap_pos in MEDALLIONS:
    r = dia / 2.0
    if dia > 0:
        # coin: white disc, double ring (outer bold + inner fine), Ð glyph on top
        ellipse_um(cx, cy, r, r, fill=WHITE)
        ellipse_um(cx, cy, r, r, outline=BLACK, width_um=7.0)
        ellipse_um(cx, cy, r - 12, r - 12, outline=BLACK, width_um=2.5)
        text_um("Ð", cx, cy + r * 0.36, dia * 0.42)     # Ð upper half
        ko_cy = cy - r * 0.38                                 # cluster low half
    else:
        ko_cy = cy                                            # R6 pill: no coin
    # cluster keep-out + black frame wall
    kw, kh = CLUS_W / 2 + KO_MARGIN, CLUS_H / 2 + KO_MARGIN
    rect_um(cx - kw - FRAME, ko_cy - kh - FRAME, cx + kw + FRAME, ko_cy + kh + FRAME, BLACK)
    rect_um(cx - kw, ko_cy - kh, cx + kw, ko_cy + kh, WHITE)
    spec["coins"].append({"name": name, "center": [cx, cy], "dia": dia})
    spec["banks"].append({"region": name, "cluster_keepout":
                          [cx - kw, ko_cy - kh, cx + kw, ko_cy + kh]})
    # channel: from keep-out edge to the art boundary, walls + white core.
    # ALL coords in die um; art spans x[ART_X0, ART_X0+ART_W] y[ART_Y0, ART_Y0+ART_H].
    if chan_dir == "left":
        cx0, cy0, cx1, cy1 = ART_X0, ko_cy - CHAN_W / 2, cx - kw, ko_cy + CHAN_W / 2
    elif chan_dir == "right":
        cx0, cy0, cx1, cy1 = cx + kw, ko_cy - CHAN_W / 2, ART_X0 + ART_W, ko_cy + CHAN_W / 2
    else:  # "up"
        cx0, cy0, cx1, cy1 = cx - CHAN_W / 2, ko_cy + kh, cx + CHAN_W / 2, ART_Y0 + ART_H
    # walls first (black, wider), then white core
    if chan_dir in ("left", "right"):
        rect_um(cx0, cy0 - CHAN_WALL, cx1, cy1 + CHAN_WALL, BLACK)
    else:
        rect_um(cx0 - CHAN_WALL, cy0, cx1 + CHAN_WALL, cy1, BLACK)
    rect_um(cx0, cy0, cx1, cy1, WHITE)
    spec["channels"].append({"region": name, "dir": chan_dir,
                             "rect_die_um": [cx0, cy0, cx1, cy1]})
    # caption
    if caption:
        text_um(caption, cap_pos[0], cap_pos[1], 34.0, angle=4.0)

# convert channel/bank coords in spec to true die um for downstream tools
for b in spec["banks"]:
    b["cluster_keepout"] = [b["cluster_keepout"][0], b["cluster_keepout"][1],
                            b["cluster_keepout"][2], b["cluster_keepout"][3]]

im.save(DST)
json.dump(spec, open(SPEC, "w"), indent=1)
print(f"wrote {DST} + {SPEC}")
print(f"6 medallions, cluster keepout {2*(CLUS_W/2+KO_MARGIN):.0f}x{2*(CLUS_H/2+KO_MARGIN):.0f} um, channel {CHAN_W} um")
