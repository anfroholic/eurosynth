# Meme Chip — Hookup, Test & PUF Characterization Guide

This is the bring-up manual for the `meme` branch chip (wafer.space GF180MCU,
slot `1x0p5`, die 3932 × 2531 µm): the doge-art die with a **48-tap passive
analog PUF** that makes every fabricated part a unique, unclonable "NFT".

What's on the chip:

| Thing | What it is | How you test it |
|---|---|---|
| The doge | Metal halftone art on all 5 metal layers, fills the core | Microscope. Captions legible; a dickbutt hides in the glint of the right eye's pupil |
| Wow counter | 26-bit free counter, 4 blinker outputs | Power + clock + reset → watch 4 pads blink |
| Analog PUF | 48 passive poly-resistor dividers hidden in the dogecoin medallions | Force 1 V across 2 rail pads, meter 48 tap pads. No power needed |

Everything is one 5 V domain. The PUF is completely passive — it can (and
should) be read with the chip **unpowered**.

---

## 1. Die orientation and pad numbering

Hold the die with the doge upright (captions readable). Then:

- **South (bottom)** edge: 24 pads, `clk` is the leftmost (nearest the
  bottom-left corner).
- **West (left)** edge: 12 pads, numbered bottom → top.
- **East (right)** edge: 12 pads, numbered bottom → top.
- **North (top)** edge: 24 pads, numbered left → right.

All pads are 75 µm wide. Coordinates below are die µm of the **pad center**
along its edge (origin = bottom-left die corner). If your parts come packaged
or on a carrier, map these die pads to package pins with the wafer.space
`1x0p5` bond-out sheet — the ring order below is the ground truth.

### South edge (left → right)

| # | Pad | x center | Function |
|---|---|---|---|
| 1 | `clk` | 482.5 | Clock input (Schmitt trigger, 5 V CMOS) |
| 2 | `rst_n` | 611.5 | Active-low sync reset (no internal pull — must drive) |
| 3 | `bidir[0]` | 740.5 | Blinker out ~0.37 Hz @ 25 MHz clk |
| 4 | `bidir[1]` | 869.5 | Blinker out ~0.75 Hz |
| 5 | `DVSS` | 998.5 | Ground |
| 6 | `DVDD` | 1127.5 | +5 V |
| 7 | `bidir[2]` | 1256.5 | Blinker out ~1.5 Hz |
| 8 | `bidir[3]` | 1385.5 | Blinker out ~3 Hz |
| 9–18 | `analog[8..17]` | 1514.5 … 2675.5 (pitch 129) | PUF taps t6–t15 |
| 19 | `DVSS` | 2804.5 | Ground |
| 20 | `DVDD` | 2933.5 | +5 V |
| 21–24 | `analog[18..21]` | 3062.5 … 3449.5 | PUF taps t16–t19 |

### West edge (bottom → top)

| # | Pad | y center | Function |
|---|---|---|---|
| 1 | `VSS` | 490 | Core ground |
| 2 | `VDD` | 631 | Core +5 V |
| 3 | `analog[0]` | 772 | **PUF Vhi force rail** |
| 4 | `analog[1]` | 913 | **PUF Vlo force rail** |
| 5–10 | `analog[2..7]` | 1054 … 1759 (pitch 141) | PUF taps t0–t5 |
| 11 | `DVSS` | 1900 | Ground |
| 12 | `DVDD` | 2041 | +5 V |

### East edge (bottom → top)

| # | Pad | y center | Function |
|---|---|---|---|
| 1 | `DVSS` | 490 | Ground |
| 2 | `DVDD` | 631 | +5 V |
| 3–10 | `analog[22..29]` | 772 … 1759 (pitch 141) | PUF taps t20–t27 |
| 11 | `DVSS` | 1900 | Ground |
| 12 | `DVDD` | 2041 | +5 V |

### North edge (left → right)

| # | Pad | x center | Function |
|---|---|---|---|
| 1–4 | `analog[30..33]` | 482.5 … 869.5 (pitch 129) | PUF taps t28–t31 |
| 5 | `DVSS` | 998.5 | Ground |
| 6 | `DVDD` | 1127.5 | +5 V |
| 7–18 | `analog[34..45]` | 1256.5 … 2675.5 | PUF taps t32–t43 |
| 19 | `DVSS` | 2804.5 | Ground |
| 20 | `DVDD` | 2933.5 | +5 V |
| 21–24 | `analog[46..49]` | 3062.5 … 3449.5 | PUF taps t44–t47 |

**Rule of thumb:** tap number `t_k` lives on pad `analog[k+2]`. `analog[0]` =
Vhi, `analog[1]` = Vlo, both on the west edge just above the VSS/VDD pair.

Power summary: 7 × DVDD + 1 × VDD → tie **all** to +5 V. 7 × DVSS + 1 × VSS →
tie **all** to 0 V. (In this chip I/O and core are the same 5 V domain.)

---

## 2. PUF architecture (what you're measuring)

Each of the 48 taps is the midpoint of an identical 2-resistor divider:

```
 Vhi (analog[0]) ──[ R_top ~3.5 kΩ ]──●── tap t_k (analog[k+2])
                                      │
 Vlo (analog[1]) ──[ R_bot ~3.5 kΩ ]──●
```

- Resistors: `ppolyf_u` P+ unsalicided poly, W 0.8 µm × L 8 µm, ~350 Ω/sq →
  ~3.5 kΩ nominal each, ±20 % global process spread.
- All 48 dividers hang in parallel across the shared Vhi/Vlo rails
  (~7 kΩ / 48 ≈ **146 Ω** nominal rail-to-rail, plus a few tens of ohms of
  on-die rail metal).
- The dividers sit in 6 clusters of 8 hidden inside the doge's dogecoin
  medallions; connectivity of all 50 nets is LVS-verified in signoff.

The fingerprint is the **local random mismatch** between R_top and R_bot of
each divider. The divider ratio

```
r_k = (V_tap_k − Vlo) / (Vhi − Vlo)   ≈ 0.5 ± layout offset ± die mismatch
```

cancels the global ±20 % process spread and first-order temperature drift —
only the per-die random mismatch (order 0.1–1 %, i.e. roughly 0.5–10 mV at
1 V force) plus a **fixed per-tap layout offset** (rail IR drop and strap
asymmetry, identical on every die) survives. You remove the layout offset by
subtracting the per-tap average over your chip population; what's left is the
unclonable per-die fingerprint, ~4–5 usable bits per tap, ~240 bits total.

Tap ↔ medallion cluster map (for die probing / debugging):

| Cluster | Die location (LL, µm) | Taps |
|---|---|---|
| R1 | (680, 1113) west side | t0–t3, t6–t9 |
| R2 | (760, 1594) west side | t4, t5, t10–t15 |
| R5 | (3190, 680) east side | t16–t23 |
| R6 | (3140, 1130) east side | t28–t35 |
| R4 | (3200, 1487) east side | t24–t27, t44–t47 |
| R3 | (3100, 1842) east side | t36–t43 |

---

## 3. PUF readout hookup

The analog pads are bare feed-throughs — **no ESD clamps**. Use a wrist
strap, ground your bench, and touch the pads only with proper probes.

```
                         ┌──────────────────────┐
  Bench PSU / SMU        │        meme chip     │
  1.000 V, I-lim 20 mA   │                      │
   (+) ──────────────────┤ analog[0]  Vhi       │
   (−) ──────┬───────────┤ analog[1]  Vlo       │
             │           │                      │
   DMM (−) ──┘           │ analog[2..49]        │
   DMM (+) ── probe ─────┤   = taps t0..t47     │
                         │                      │
   (optional: DVSS ──┐   │                      │
    tied to bench ───┴───┤ DVSS                 │
    ground)              └──────────────────────┘
```

Setup:

1. **Chip unpowered.** Optionally tie one DVSS pad to bench ground so the
   substrate doesn't float. Keep Vhi/Vlo between 0 and +5 V relative to it.
2. **Force:** 1.000 V from a bench supply or SMU across `analog[0]` (Vhi, +)
   and `analog[1]` (Vlo, −). Current limit 20 mA. Expect **5.5–9 mA** to flow
   (all 48 dividers in parallel; the exact value tracks the ±20 % global
   sheet-resistance lot spread — it is itself a coarse process readout).
   - Don't force much above 2 V: at 1 V each divider dissipates only ~0.14 mW
     (negligible self-heating) and current density in the 0.8 µm poly is
     comfortable; at 5 V you're near ~1 mA per 0.8 µm bar for no fingerprint
     benefit (mismatch is a *ratio* — amplitude scales but so does noise
     sensitivity of nothing; 1 V is plenty).
3. **Sense the rails at the pads**, not at the supply: the force leads carry
   ~7 mA, so 1 Ω of contact resistance = 7 mV of error. Either use a 4-wire
   SMU with sense leads on the pads, or measure `V(analog[0])` and
   `V(analog[1])` with the same DMM/probe you use for the taps and use those
   values as Vhi/Vlo in the math.
4. **Meter each tap** `analog[2] … analog[49]` to the Vlo sense point. Tap
   source impedance is ~1.75 kΩ, so even a 10 MΩ DMM adds only ~0.02 %
   (systematic, common to all taps — it cancels in the population-mean
   subtraction). High-Z mode (>1 GΩ) is nicer but not required.
   **Resolution matters more than impedance:** the die-to-die signal is
   single-digit millivolts, so use a 5½-digit DMM (10 µV) or average many
   4½-digit readings.

For characterizing more than a couple of chips, build a jig: 3 × 16:1 analog
mux (e.g. CD74HC4067, powered from a clean 5 V, address lines from any MCU)
between the 48 tap pins and one DMM input. The taps are hi-Z sense lines, so
mux on-resistance (~70 Ω against a 10 MΩ meter) is irrelevant.

### Continuity / bonding sanity check (do this first, per chip)

With an ohmmeter (chip unpowered, PSU disconnected):

| Measurement | Expect | Meaning if open/way off |
|---|---|---|
| `analog[0]` ↔ `analog[1]` | ~150–250 Ω | Broken Vhi or Vlo bond — chip unreadable |
| any tap ↔ `analog[0]` | ~1.8–2.4 kΩ | That tap's bond or divider is broken |
| any tap ↔ `analog[1]` | ~1.8–2.4 kΩ | Same |
| any analog pad ↔ DVSS | open (>10 MΩ) | Short — bad die/bond |

---

## 4. PUF measurement & characterization procedure

### Per-chip read (enrollment)

1. Note chip serial (write one on the package/carrier), temperature.
2. Hook up as above, force 1.000 V.
3. Record `Vhi`, `Vlo` (sensed at pads), then `V[0..47]` for taps t0–t47.
4. Compute the 48 ratios `r_k = (V_k − Vlo) / (Vhi − Vlo)`.
5. **Repeat the full sweep 5–10×** (re-probe included) and average. The
   per-tap standard deviation across repeats is your measurement noise
   `σ_meas` — record it; it sets how many bits each tap is worth.
6. Optional self-check: swap the force polarity (Vhi ↔ Vlo). Each ratio must
   come back as `1 − r_k` within noise. If not, you have a sensing problem.

Store one CSV row per read:

```
chip_id, read_n, temp_C, vhi, vlo, v_t0, v_t1, ..., v_t47
```

### Population characterization (turns readings into fingerprints)

After you've enrolled several chips:

1. Per tap, compute the population mean `µ_k` over all chips. This is the
   fixed layout offset (rail IR drop etc.) — the same on every die.
2. Each chip's fingerprint is the deviation vector `d_k = r_k − µ_k`,
   48 values, typically a few ×0.1 % each.
3. Quality metrics to check:
   - **Repeatability (same chip):** RMS of `d_k` across re-reads ≪ spread
     across chips. Aim for σ_meas at least 4–8× smaller than σ_pop.
   - **Uniqueness (across chips):** per-tap `d_k` should look zero-mean
     random across chips; any two chips' fingerprint vectors should differ
     wildly (correlation ≈ 0).
   - **Bits per tap:** ≈ log2(σ_pop / σ_meas). With clean measurements
     expect 4–5 bits × 48 taps ≈ 200–240 bits — billions of billions of
     unique IDs for a run of thousands of chips.

Reference implementation (feed it your enrollment CSV):

```python
import csv, hashlib
from collections import defaultdict
from statistics import mean, stdev

reads = defaultdict(list)                      # chip_id -> list of ratio vectors
for row in csv.DictReader(open("puf_reads.csv")):
    vhi, vlo = float(row["vhi"]), float(row["vlo"])
    r = [(float(row[f"v_t{k}"]) - vlo) / (vhi - vlo) for k in range(48)]
    reads[row["chip_id"]].append(r)

chips = {cid: [mean(col) for col in zip(*rs)] for cid, rs in reads.items()}
mu    = [mean(col) for col in zip(*chips.values())]          # layout offset
fp    = {cid: [r - m for r, m in zip(rs, mu)] for cid, rs in chips.items()}

# noise floor & population spread per tap
sig_meas = [mean(stdev(col) for col in zip(*rs)) for rs in reads.values()]
sig_pop  = [stdev(col) for col in zip(*chips.values())]
print("mean bits/tap ≈", mean(( (p/m).bit_length() if m else 0)
      for p, m in zip(sig_pop, [max(s, 1e-9) for s in [mean(sig_meas)]*48])))

# human-readable NFT id: quantize deviations to 0.05% bins and hash
for cid, d in fp.items():
    q = tuple(round(x / 5e-4) for x in d)
    print(cid, hashlib.sha256(str(q).encode()).hexdigest()[:16])
```

To later **verify** a chip against its enrollment: re-read its 48 ratios,
form `d_k`, and compare to the stored vector — genuine if
`max|Δd_k| < ~5·σ_meas` (equivalently, the two vectors' correlation is ≈ 1).
Matching raw deviation vectors is far more robust than re-deriving hashed
bits; keep the hash only as the public "token ID" and the vector as the
authentication record. Re-verify within ±10 °C of enrollment for the
tightest margins (ratios cancel temperature to first order, but not
perfectly).

Why this is unforgeable in practice: the mismatch is set by atomic-scale
poly granularity at fabrication. Nobody — including the original fab — can
place resistors to hit 48 chosen ratios at the 0.1 % level, and the
population entropy (~240 bits) makes a lookalike die astronomically
unlikely.

---

## 5. Powered test — the wow counter blinkers

This proves the digital side (pad ring, clock tree, reset) is alive.

Hookup:

1. **Power:** all DVDD + VDD pads → +5.0 V; all DVSS + VSS pads → 0 V.
   100 nF decoupling close to the chip. Current draw is tiny (one 26-bit
   counter).
2. **Clock:** 0–5 V square wave into `clk` (south pad 1). Anything from DC
   to tens of MHz works; 25 MHz gives the designed blink rates.
3. **Reset:** `rst_n` (south pad 2) has **no internal pull** — it must be
   driven. 10 kΩ pull-up to 5 V plus a push-button to ground works: hold low
   for a few clock edges, release. (Reset is synchronous — the clock must be
   running for reset to take effect.)
4. **Observe** `bidir[0..3]` (south pads 3, 4, 7, 8) with a scope, logic
   analyzer, or an LED + ~2 kΩ to ground on each.

Expected (blink frequency = f_clk / 2^(26−n) for blinker n):

| Pad | @ 25 MHz | @ 1 MHz |
|---|---|---|
| `bidir[0]` | 0.37 Hz | 0.015 Hz |
| `bidir[1]` | 0.75 Hz | 0.03 Hz |
| `bidir[2]` | 1.5 Hz | 0.06 Hz |
| `bidir[3]` | 3 Hz | 0.12 Hz |

Each output is exactly half the frequency of its neighbor — four related
square waves confirm the whole counter, clock path and reset in one look.
Much wow.

The PUF can be read while the chip is powered (the dividers are passive and
not connected to any logic) — just keep Vhi/Vlo within 0…5 V of DVSS.

---

## 6. Gotchas checklist

- **No ESD protection on the 50 analog pads.** Ground yourself. This is the
  most likely way to kill a PUF pad.
- **Sense the rails at the pads** (Kelvin). ~7 mA flows in the force path;
  lead/contact drops are bigger than the fingerprint if you sense at the
  supply.
- **Millivolts matter:** 5½-digit DMM or heavy averaging.
- **`rst_n` floats** — always drive or pull it when powered, or the bidir
  pads may sit mid-rail.
- **Don't exceed ~2 V force** across Vhi/Vlo (self-heating buys nothing;
  ratios are amplitude-independent).
- Die pad ↔ package pin mapping comes from the wafer.space `1x0p5` bond-out
  sheet; the per-edge order in §1 is the authoritative die-side reference
  (extracted from `librelane/slots/slot_1x0p5.yaml` +
  `ip/meme_puf/script/gen_routes_all.py`, LVS-verified in the final signoff
  run).
- The fixed per-tap layout offsets mean **raw ratios are not the
  fingerprint** — always subtract the per-tap population mean first.
