# SPDX-License-Identifier: Apache-2.0
"""Generate puf_blocker: an empty row-killing macro (129 x 48 um) placed over
each std-cell band that a puf_routes branch bundle crosses in the two side
strips beside the art (west x442..571, east x3361..3490).

Why: the branch bundles cross the strips as M2/M3 OBS spanning the full strip
width, so pdngen cannot drop ANY M1->M4 via stack for the rows in those bands
and hard-fails (PDN-0179; exactly 6 channels, one per cluster's bundle).
Rows crossed only by the VERTICAL R3 jogs still strap fine (the via stacks
just move along x), so only the 6 horizontal bands need killing:

  instance   at (yaml)        covers PDN channel
  bw1        [442, 1113]      (442.4,1116.9)-(560.6,1152.8)   R1 bundle
  bw2        [442, 1595]      (442.4,1599.1)-(560.6,1631.0)   R2 bundle
  be5        [3361,  682]     (3371.2,685.7)-(3489.9,717.7)   R5 bundle
  be6        [3361, 1132]     (3371.2,1136.5)-(3489.9,1168.5) R6 bundle
  be4        [3361, 1489]     (3371.2,1493.2)-(3489.9,1525.2) R4 bundle
  be3        [3361, 1842]     (3371.2,1846.0)-(3489.9,1881.9) R3 HI/LO exit

Full-strip blockers (129x1642) are NOT usable: with the strips gone, RePlAce
diverges (GPL-0305) on this nearly-empty design -- the small band blockers
keep the free-space topology close to the (converging) round-6 floorplan.
OBS is Metal1 ONLY: M2+ stay free for the detailed router and for our own
pre-drawn branch copper.
"""
import klayout.db as db

W, H = 129.0, 48.0
CELL = "puf_blocker"

ly = db.Layout(); ly.dbu = 0.001
top = ly.create_cell(CELL)
top.shapes(ly.layer(0, 0)).insert(db.Box(0, 0, round(W*1000), round(H*1000)))
ly.write("gds/puf_blocker.gds")

open("lef/puf_blocker.lef", "w").write(f"""VERSION 5.7 ;
  NOWIREEXTENSIONATPIN ON ;
  DIVIDERCHAR "/" ;
  BUSBITCHARS "[]" ;
MACRO {CELL}
  CLASS BLOCK ;
  FOREIGN {CELL} ;
  ORIGIN 0.000 0.000 ;
  SIZE {W:.3f} BY {H:.3f} ;
  OBS
      LAYER Metal1 ;
        RECT 0.000 0.000 {W:.3f} {H:.3f} ;
  END
END {CELL}
END LIBRARY
""")

open("vh/puf_blocker.v", "w").write(
    "// puf_blocker: row-killing band blocker (see gen_blocker.py).\n"
    "(* blackbox *)\nmodule puf_blocker;\nendmodule\n")

open("lib/puf_blocker.lib", "w").write(
    "library (puf_blocker) {\n"
    "  input_threshold_pct_fall: 50.0;\n  input_threshold_pct_rise: 50.0;\n"
    "  output_threshold_pct_fall: 50.0;\n  output_threshold_pct_rise: 50.0;\n"
    "  slew_lower_threshold_pct_fall: 20.0;\n  slew_lower_threshold_pct_rise: 20.0;\n"
    "  slew_upper_threshold_pct_fall: 80.0;\n  slew_upper_threshold_pct_rise: 80.0;\n"
    "\n  cell (puf_blocker) {\n  }\n}\n")
print(f"wrote gds/lef/vh/lib for {CELL} ({W}x{H})")
