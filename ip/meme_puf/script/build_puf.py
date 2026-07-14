# SPDX-License-Identifier: Apache-2.0
"""Build the meme_puf analog-PUF resistor macro.

Three identical unsalicided P+ poly resistors (ppolyf_u, ~350 ohm/sq) in a
series-serpentine divider:

    A --[R1]-- T1 --[R2]-- T2 --[R3]-- B

Force a voltage across A/B, measure the tap voltages at T1 (~2/3) and T2 (~1/3).
The *nominal* ratios cancel global process and temperature; what survives is the
per-die random local mismatch between the three bars -- the unclonable PUF
fingerprint, read passively with a precision ratiometric meter.

GF180 P+ poly-resistor stack (see pres.rb):
  Poly2 30/0   resistor bars (W >= 0.8um; here 1.0um)
  Pplus 31/0   implant, >= 0.3um overlap of poly (PRES.5)
  SAB   49/0   salicide block over the resistive body, >= 0.28um width
               overlap (PRES.6), >= 0.22um clear of the end contacts (PRES.7)
  RES_MK 110/5 resistor marking, coincident with SAB (PRES.9a)
  Contact 33/0 0.22um exact (CO.1), on the salicided landing ends
  Metal1 34/0  terminals + the serpentine series straps + the 4 pins
"""
import klayout.db as db

# --- layers ---
POLY = (30, 0); PPLUS = (31, 0); SAB = (49, 0)
RESMK = (110, 5); CONT = (33, 0); M1 = (34, 0)
M1LBL = (34, 10)   # Metal1_Label (pin names for LVS)
BND = (0, 0)  # cell boundary / prBoundary

# --- geometry (um) ---
S = 1.0            # global shift so all coords are positive
W = 1.0            # resistor width  (> 0.8 min, margin)
LBODY = 20.0       # resistive (SAB-covered) length -> ~7 kOhm at 350 ohm/sq
PITCH = 3.0        # vertical bar pitch (2.0um poly-poly space >> 0.4 min)
BARLEN = 23.0      # full poly bar length incl. salicided landings
CO = 0.22          # contact size
CXL = 0.7          # left contact x-center (in poly landing)
CXR = 22.3         # right contact x-center
SAB_X0, SAB_X1 = 1.4, 21.6   # SAB/RES_MK body extent (clears contacts by 0.59)

ly = db.Layout(); ly.dbu = 0.001
top = ly.create_cell("meme_puf")


def box(layer, x1, y1, x2, y2):
    top.shapes(ly.layer(*layer)).insert(
        db.Box(round((x1 + S) * 1000), round((y1 + S) * 1000),
               round((x2 + S) * 1000), round((y2 + S) * 1000)))


def contact(xc, yc):
    box(CONT, xc - CO / 2, yc - CO / 2, xc + CO / 2, yc + CO / 2)


def label(name, xc, yc):
    top.shapes(ly.layer(*M1LBL)).insert(
        db.Text(name, db.Trans(round((xc + S) * 1000), round((yc + S) * 1000))))


bars_y = [0.0, PITCH, 2 * PITCH]          # bottom edges of the 3 bars
for by in bars_y:
    # poly bar
    box(POLY, 0.0, by, BARLEN, by + W)
    # SAB + RES_MK over the resistive body (0.3um poly-width overlap)
    box(SAB,   SAB_X0, by - 0.3, SAB_X1, by + W + 0.3)
    box(RESMK, SAB_X0, by - 0.3, SAB_X1, by + W + 0.3)
    # end contacts on the salicided landings
    contact(CXL, by + W / 2)
    contact(CXR, by + W / 2)

# one Pplus rectangle enclosing all poly by >= 0.35um (PRES.5 needs 0.3)
box(PPLUS, -0.35, -0.35, BARLEN + 0.35, 2 * PITCH + W + 0.35)

# --- Metal1: 4 pins + series-serpentine straps ---
# node A  : left contact of R1 (bar0)
# node T1 : right contacts of R1 & R2 strapped  (bar0.R + bar1.R)
# node T2 : left  contacts of R2 & R3 strapped  (bar1.L + bar2.L)
# node B  : right contact of R3 (bar2)
y0 = bars_y[0] + W / 2; y1 = bars_y[1] + W / 2; y2 = bars_y[2] + W / 2
HW = 0.5  # half-width of the metal straps/pins

def m1(x1, y1_, x2, y2_):
    box(M1, x1, y1_, x2, y2_)

# A pin  (bar0 left)
m1(CXL - HW, y0 - HW, CXL + HW, y0 + HW)
# B pin  (bar2 right)
m1(CXR - HW, y2 - HW, CXR + HW, y2 + HW)
# T1 strap (right side, bar0 <-> bar1)
m1(CXR - HW, y0 - HW, CXR + HW, y1 + HW)
# T2 strap (left side, bar1 <-> bar2)
m1(CXL - HW, y1 - HW, CXL + HW, y2 + HW)

# pin labels (for LVS port identification)
label("A",  CXL, y0)
label("B",  CXR, y2)
label("T1", CXR, y1)
label("T2", CXL, y1)

# --- cell boundary ---
MAX_X = BARLEN + 0.65
MAX_Y = 2 * PITCH + W + 0.65
box(BND, -0.65, -0.65, MAX_X, MAX_Y)

ly.write("gds/meme_puf.gds")
sizex = round((MAX_X + S) * 1000) / 1000.0
sizey = round((MAX_Y + S) * 1000) / 1000.0
print(f"wrote gds/meme_puf.gds  size={sizex} x {sizey} um")
print(f"per-segment R ~= 350 * {LBODY}/{W} = {350*LBODY/W:.0f} ohm ; divider total ~= {3*350*LBODY/W:.0f} ohm")
