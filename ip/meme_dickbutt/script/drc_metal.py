# SPDX-License-Identifier: Apache-2.0
"""Targeted metal width/space DRC in pure klayout.db, so we can check the merged
macro without the full PDK deck (whose antenna rules need the Docker klayout).
These are the rules the dickbutt merge can actually affect: GF180 M1 0.23/0.23,
M2-M5 0.28/0.28, MetalTop 0.44 width / 0.46 space. Reports violation counts."""
import sys
import klayout.db as db

GDS = sys.argv[1] if len(sys.argv) > 1 else "gds/meme_db_butt.gds"
RULES = [                       # (name, layer, datatype, min_width, min_space)
    ("M1", 34, 0, 0.23, 0.23),
    ("M2", 36, 0, 0.28, 0.28),
    ("M3", 42, 0, 0.28, 0.28),
    ("M4", 46, 0, 0.28, 0.28),
    ("MetalTop", 81, 0, 0.44, 0.46),   # 81 = top metal (5LM) -> MT.1/MT.2a
]


def main():
    ly = db.Layout()
    ly.read(GDS)
    total = 0
    for name, l, d, minw, mins in RULES:
        li = ly.find_layer(l, d)
        if li is None:
            print(f"  {name:9s} ({l}/{d}): layer absent")
            continue
        reg = db.Region(ly.top_cell().begin_shapes_rec(li))
        reg.merge()
        w = reg.width_check(round(minw / ly.dbu))
        s = reg.space_check(round(mins / ly.dbu))
        nw, ns = w.size(), s.size()
        total += nw + ns
        flag = "" if (nw + ns) == 0 else "  <<< VIOLATIONS"
        print(f"  {name:9s} ({l}/{d}): width<{minw} = {nw:5d}   space<{mins} = {ns:5d}{flag}")
    print(f"[{GDS}] total metal width/space violations = {total}")


if __name__ == "__main__":
    main()
