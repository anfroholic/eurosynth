# SPDX-License-Identifier: Apache-2.0
"""De-dither doge.png back to continuous tone.

The source meme is a pre-rendered 2-level halftone (levels 26/239 only).
Resampling a baked dither onto the metal grid is the documented DRC
catastrophe (503k violations on the early gear attempt), so we Gaussian-blur
it back to continuous-tone grey here; make_gds.py --halftone control then
re-screens it on-grid (black -> solid-screen lines, grey -> clustered dots,
white -> empty).
"""
import argparse

from PIL import Image, ImageFilter

parser = argparse.ArgumentParser()
parser.add_argument("src")
parser.add_argument("dst")
parser.add_argument("--radius", type=float, default=12.0,
                    help="Gaussian blur radius in source px (dither pitch is "
                         "~13-40px at 4000px wide)")
args = parser.parse_args()

im = Image.open(args.src)
bg = Image.new("RGBA", im.size, "WHITE")
bg.paste(im, (0, 0), im)
g = bg.convert("L").filter(ImageFilter.GaussianBlur(args.radius))
# make_gds pastes the source via its alpha channel, so ship opaque RGBA
g.convert("RGBA").save(args.dst)
print(f"wrote {args.dst} (blur r={args.radius})")
