# SPDX-License-Identifier: Apache-2.0
"""Add dummy poly2 fill lines to the meme macro.

The macro is metal-only art covering ~42% of the die; with the engines gone
there is almost no poly left on the chip and die-level rule PL.8 (poly2
coverage >= 14%) fails. The rule text itself prescribes the fix: "Dummy poly2
lines must be added." A uniform horizontal line screen (2 um lines at 5 um
pitch = 40% local coverage) across the macro puts the die at ~17% poly2 by
itself, comfortably above the floor. Drawn on the active poly2 layer (30/0)
so both the in-flow density check and the precheck count it; the lines are
floating wires over field oxide (no diffusion -> no devices, same class as
the floating halftone metal, invisible under the metal art).
"""
import argparse

import klayout.db as db

parser = argparse.ArgumentParser()
parser.add_argument("gds")
parser.add_argument("--line", type=float, default=2.0, help="line width (um)")
parser.add_argument("--pitch", type=float, default=5.0, help="line pitch (um)")
args = parser.parse_args()

ly = db.Layout()
ly.read(args.gds)
top = ly.top_cell()
bbox = top.dbbox()
poly2 = ly.layer(db.LayerInfo(30, 0))

n = 0
y = bbox.bottom
while y + args.line <= bbox.top:
    top.shapes(poly2).insert(db.DBox(bbox.left, y, bbox.right, y + args.line))
    y += args.pitch
    n += 1

ly.write(args.gds)
cov = 100.0 * n * args.line * bbox.width() / bbox.area()
print(f"added {n} poly2 lines ({args.line}/{args.pitch} um) -> "
      f"{cov:.1f}% macro poly coverage")
