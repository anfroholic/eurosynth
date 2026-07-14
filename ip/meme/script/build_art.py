# SPDX-License-Identifier: Apache-2.0
"""One-command rebuild of the shipping doge macro (gds/meme.gds).

Chain: crisp_text (text GDS + wiped master + wipe mask) -> preprocess blur
-> POST-BLUR re-wipe (hard white edges so the halftone doesn't create
marginal dot spacing in the blur gradient) -> make_gds halftone
-> add_poly_fill -> merge_overlays (dickbutt + crisp text) -> metal DRC.
Run from ip/meme/."""
import subprocess
import sys
import numpy as np
from PIL import Image

def run(*args):
    print("+", " ".join(args))
    subprocess.run([sys.executable, *args], check=True)

run("script/crisp_text.py")
run("script/preprocess.py", "image/ddoge_carved_db_txt.png", "image/_prep_txt.png", "--radius", "6")

# post-blur re-wipe
# NB: keep the RGBA mode preprocess writes -- make_gds mis-reads an L-mode
# image (first attempt came out tone-inverted)
prep = Image.open("image/_prep_txt.png").convert("RGBA")
mask = np.asarray(Image.open("image/_text_wipe_mask.png")) > 0
arr = np.asarray(prep).copy()
arr[mask] = (239, 239, 239, 255)
Image.fromarray(arr).save("image/_prep_txt.png")
print("re-applied text wipe post-blur")

run("script/make_gds.py", "image/_prep_txt.png", "gds/meme_txt.gds", "--cellname", "meme",
    "--invert", "--merge", "--pixel-size", "1.0", "--width", "2790", "--height", "1500",
    "--halftone", "control", "--screen", "5", "--solid-screen", "20", "--line-width", "2",
    "--foreground", "34/0", "36/0", "42/0", "46/0", "81/0", "--boundary", "0/0", "152/5")
run("script/add_poly_fill.py", "gds/meme_txt.gds")
run("script/merge_overlays.py")
run("../meme_dickbutt/script/drc_metal.py", "gds/meme.gds")
