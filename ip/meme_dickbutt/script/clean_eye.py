# SPDX-License-Identifier: Apache-2.0
"""Prepare the doge master for the crisp-dickbutt merge.

The ddoge master carries the OLD, unmanufacturable line-art dickbutt drawn into
the eye catchlight, and the catchlight itself is a light-grey dithered region
(sparse dots) that would re-screen to sparse metal -- not a clean field. We:

  1. erase the old dickbutt (paint white over it), and
  2. paint a solid-WHITE keepout patch where the new crisp dickbutt will land,
     so it classifies as EMPTY metal (a clean, isolated field on every layer).

Output is a new master (…_db.png); the real doge art is regenerated from it and
the crisp `smallest_M1.gds` is merged into the keepout afterwards (place_dickbutt).
Nothing here touches the shipping master.
"""
import sys
from PIL import Image, ImageDraw

SRC = "../meme/image/ddoge_carved.png"
DST = "../meme/image/ddoge_carved_db.png"

# --- master-px geometry (window verified on out/eyegrid_carved.png) ---
# old dickbutt to erase: fill with pupil-black so the catchlight reads clean
# (it straddled the catchlight/pupil edge; black just restores the dark pupil).
OLD = (1948, 940, 2016, 996)          # x0,y0,x1,y1
# clean keepout for the NEW dickbutt: the widest clear part of the lower
# catchlight column (already light, but we force it pure-white so it screens to
# EMPTY, not sparse dots). 58x68 px hosts the 24x33 px sprite with ~10px margin.
KEEP_C = (1915, 1031)                 # centre (master px)
KEEP_HW, KEEP_HH = 34, 40             # half-width/height (post-blur core still
                                      # >~48x60px, hosts 24x33 sprite + margin)


def main():
    im = Image.open(SRC).convert("RGBA")
    d = ImageDraw.Draw(im)
    d.rectangle(OLD, fill=(0, 0, 0))                             # erase old -> pupil
    cx, cy = KEEP_C
    d.ellipse((cx - KEEP_HW, cy - KEEP_HH, cx + KEEP_HW, cy + KEEP_HH),
              fill=(255, 255, 255))                              # white keepout
    im.save(DST)
    print(f"wrote {DST}: erased old {OLD}, keepout ellipse @ {KEEP_C} "
          f"r=({KEEP_HW},{KEEP_HH})")


if __name__ == "__main__":
    main()
