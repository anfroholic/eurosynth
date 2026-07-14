# SPDX-License-Identifier: Apache-2.0
"""Build a meme_puf resistor BANK -- boosted-amplitude analog-PUF fingerprint.

N small unsalicided P+ poly units (ppolyf_u) in a plain series string:

    HI --[R0]-- t1 --[R1]-- t2 -- ... --[R(N-1)]-- LO
              (tap1)     (tap2)      (tap N-1)

vs the first prototype (W=1/L=20, 3 bars), the units here are minimum-geometry
(W=0.8um / short L) so the per-unit random mismatch sigma ~ 1/sqrt(W*L) is much
larger -> a bigger, easier-to-read fingerprint. We deliberately DO NOT common-
centroid: for a PUF both the random mismatch AND the process gradient are
per-die-stable, so keeping them maximises entropy. Two DUMMY bars flank the
string so the active units see a reproducible edge environment (stable re-reads).

Readout: force a voltage across HI/LO (the 2 clean analog pads); measure each tap
voltage with a hi-Z meter via a repurposed bidir pad. Nominal tap ratios cancel
temperature + global process; the residual per-die deviation is the fingerprint.

Stack (pres.rb): Poly2 + Pplus(>=0.3 ovl) + SAB + RES_MK over the body,
Contacts on salicided landings (>=0.22 clear of SAB), Metal1 straps/pins.
"""
import argparse
import klayout.db as db

POLY=(30,0); PPLUS=(31,0); SAB=(49,0); RESMK=(110,5); CONT=(33,0); M1=(34,0); M1LBL=(34,10); BND=(0,0)
PINRECTS={}   # node name -> (x1,y1,x2,y2) in final (shifted) um, for the LEF

ap=argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=4, help="active units in the string")
ap.add_argument("--w", type=float, default=0.8, help="unit width um (PRES.1 min 0.8)")
ap.add_argument("--lbody", type=float, default=8.0, help="unit resistive length um")
ap.add_argument("--out", default="gds/meme_puf.gds")
ap.add_argument("--cell", default="meme_puf")
ap.add_argument("--sabgap", type=float, default=0.22,
                help="contact near-edge to SAB gap um. Magic's PRES.7 templayers "
                     "(gf180mcuD.tech res_cont_space_min/max) require near edge "
                     ">=0.22 AND far edge <=0.44 -- with a 0.22 contact that "
                     "forces EXACTLY 0.22 (sweep-verified: 0.22 passes, 0.25 "
                     "and 0.30 flag 'too far', <0.22 flags 'too close').")
ap.add_argument("--no-companions", action="store_true",
                help="emit only the GDS (for DRC sweeps)")
a=ap.parse_args()

S=1.0
W=a.w; LBODY=a.lbody; PITCH=2.2
BARLEN=LBODY+3.0                 # +landings
CO=0.22
SAB_X0, SAB_X1 = 1.4, BARLEN-1.4
# Contact-to-SAB gap: see --sabgap help; magic forces exactly 0.22.
SABGAP=a.sabgap
CXL = SAB_X0 - SABGAP - CO/2     # near edge at SAB_X0-SABGAP
CXR = BARLEN - CXL
NDUM=1                            # dummy bars each side

ly=db.Layout(); ly.dbu=0.001
top=ly.create_cell(a.cell)
def box(layer,x1,y1,x2,y2):
    top.shapes(ly.layer(*layer)).insert(db.Box(round((x1+S)*1000),round((y1+S)*1000),
                                                round((x2+S)*1000),round((y2+S)*1000)))
def contact(xc,yc): box(CONT,xc-CO/2,yc-CO/2,xc+CO/2,yc+CO/2)
def label(n,xc,yc): top.shapes(ly.layer(*M1LBL)).insert(db.Text(n,db.Trans(round((xc+S)*1000),round((yc+S)*1000))))

Ntot=a.n+2*NDUM
def bar_y(i): return i*PITCH        # bottom edge of bar i (0..Ntot-1)

# poly + implant/SAB/RES_MK + contacts for every bar (active + dummy identical)
for i in range(Ntot):
    by=bar_y(i)
    box(POLY,0.0,by,BARLEN,by+W)
    box(SAB, SAB_X0,by-0.3,SAB_X1,by+W+0.3)
    box(RESMK,SAB_X0,by-0.3,SAB_X1,by+W+0.3)
    contact(CXL,by+W/2); contact(CXR,by+W/2)
# one Pplus over everything
box(PPLUS,-0.35,-0.35,BARLEN+0.35,(Ntot-1)*PITCH+W+0.35)

def yc(i): return bar_y(i)+W/2
HW=0.5
def m1(x1,y1,x2,y2): box(M1,x1,y1,x2,y2)
def pin(name,x1,y1,x2,y2,lx,ly):
    box(M1,x1,y1,x2,y2); label(name,lx,ly)
    PINRECTS[name]=(x1+S,y1+S,x2+S,y2+S)

# ---- series string over the ACTIVE bars (indices NDUM .. NDUM+n-1) ----
act=list(range(NDUM,NDUM+a.n))
# serpentine: connect consecutive active bars, alternating the side, so the
# string threads HI(top-left) ... LO. node names: HI, t1..t(n-1), LO.
for k,bi in enumerate(act):
    if k==0:
        pin("HI",CXL-HW,yc(bi)-HW,CXL+HW,yc(bi)+HW,CXL,yc(bi))
    # strap to previous bar
    if k>0:
        prev=act[k-1]
        side_x = CXR if (k%2==1) else CXL     # alternate connection side
        pin(f"t{k}", side_x-HW, min(yc(prev),yc(bi))-HW, side_x+HW, max(yc(prev),yc(bi))+HW,
            side_x, (yc(prev)+yc(bi))/2)
# LO on the free end of the last active bar = OPPOSITE side from its incoming
# strap (side_x for k=n-1), so bar(n-1)'s other contact isn't left floating.
last=act[-1]
last_in_side = CXR if ((a.n-1) % 2 == 1) else CXL
lo_x = CXL if last_in_side == CXR else CXR
pin("LO",lo_x-HW,yc(last)-HW,lo_x+HW,yc(last)+HW,lo_x,yc(last))

# ---- dummies: tie each dummy bar's two ends together to a local strap (inert) ----
for bi in list(range(0,NDUM))+list(range(NDUM+a.n,Ntot)):
    m1(CXL-HW,yc(bi)-HW,CXL+HW,yc(bi)+HW)
    m1(CXR-HW,yc(bi)-HW,CXR+HW,yc(bi)+HW)

MAXX=BARLEN+0.65; MAXY=(Ntot-1)*PITCH+W+0.65
box(BND,-0.65,-0.65,MAXX,MAXY)
ly.write(a.out)
Runit=350*LBODY/W
SIZEX=round((MAXX+S)*1000)/1000.0; SIZEY=round((MAXY+S)*1000)/1000.0
print(f"wrote {a.out}  cell={a.cell}  size={SIZEX:.2f} x {SIZEY:.2f} um")
print(f"units: {a.n} active + {2*NDUM} dummy, W={W} L={LBODY} -> R_unit~{Runit:.0f} ohm, string~{a.n*Runit:.0f} ohm")
print(f"taps (fingerprint values): {a.n-1}  ; nodes: HI, {', '.join('t%d'%k for k in range(1,a.n))}, LO")
print(f"amplitude vs W1/L20 baseline: ~{( (1*20)/(W*LBODY) )**0.5:.1f}x mismatch sigma")

# ---- companion deliverables (LEF / stub / lib / spice) ----
import os, sys
if a.no_companions:
    sys.exit(0)
base=os.path.dirname(os.path.dirname(a.out))  # ip/meme_puf
order=["HI"]+[f"t{k}" for k in range(1,a.n)]+["LO"]
def w(p,s): open(os.path.join(base,p),"w").write(s)
# LEF
lef=[f"VERSION 5.7 ;","  NOWIREEXTENSIONATPIN ON ;",'  DIVIDERCHAR "/" ;','  BUSBITCHARS "[]" ;',
     f"MACRO {a.cell}","  CLASS BLOCK ;",f"  FOREIGN {a.cell} ;","  ORIGIN 0.000 0.000 ;",
     f"  SIZE {SIZEX:.3f} BY {SIZEY:.3f} ;"]
for nm in order:
    x1,y1,x2,y2=PINRECTS[nm]
    lef+=[f"  PIN {nm}","    DIRECTION INOUT ;","    USE ANALOG ;","    PORT","      LAYER Metal1 ;",
          f"        RECT {x1:.3f} {y1:.3f} {x2:.3f} {y2:.3f} ;","    END",f"  END {nm}"]
lef+=[f"END {a.cell}","END LIBRARY",""]
w(f"lef/{a.cell}.lef","\n".join(lef))
# verilog blackbox stub
ports=", ".join(order)
w(f"vh/{a.cell}.v",
  f"// {a.cell}: passive analog-PUF resistor bank. Blackbox for the digital flow;\n"
  f"// terminals are analog nets tied straight to pad bond nodes.\n"
  f"(* blackbox *)\nmodule {a.cell} ({ports});\n  inout {ports};\nendmodule\n")
# lib
lib=[f"library ({a.cell}) {{"]
for k in ("input_threshold_pct_fall","input_threshold_pct_rise","output_threshold_pct_fall",
          "output_threshold_pct_rise","slew_lower_threshold_pct_fall","slew_lower_threshold_pct_rise",
          "slew_upper_threshold_pct_fall","slew_upper_threshold_pct_rise"):
    lib.append(f"  {k}: {'20.0' if 'lower' in k else '80.0' if 'upper' in k else '50.0'};")
lib.append(f"  cell ({a.cell}) {{")
for nm in order: lib.append(f"    pin ({nm}) {{ direction: inout; }}")
lib+=["  }","}",""]
w(f"lib/{a.cell}.lib","\n".join(lib))
# spice subckt (series of ppolyf_u, bulk->VSUB)
sp=[f"* {a.cell} -- analog-PUF resistor bank, {a.n} x ppolyf_u (~350 ohm/sq) in series",
    f".subckt {a.cell} {' '.join(order)} VSUB"]
chain=order  # HI t1 .. LO in electrical order
for i in range(a.n):
    n1,n2=chain[i],chain[i+1]
    sp.append(f"XR{i} {n1} {n2} VSUB ppolyf_u r_width={W}u r_length={LBODY}u")
sp+=[f".ends {a.cell}",""]
w(f"spice/{a.cell}.spice","\n".join(sp))
print(f"wrote lef/vh/lib/spice for {a.cell}  (pins: {' '.join(order)})")
