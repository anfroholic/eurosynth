# Metal-size limits the halftone renderer must respect (GF180MCU)

*Paste this into the Halftone Studio / renderer spec. It encodes the hard silicon
limit that turns "art" into "DRC-clean art." Derived + DRC-verified on the eurosynth
art macros (gf180mcuD, `beol=true`), 2026-07-03.*

## The one hard limit: max solid metal width (MSLOT / wide-metal slotting)

**A filled metal region may be long, but its *short* dimension (width) must stay
under ~30 µm.** Any region that is ≥ ~30 µm in **both** directions is "wide metal"
and the PDK requires it to be slotted; an unslotted wide blob fails DRC
(`MSLOT.*`, one hit per metal layer M1–M5).

- Long + thin is fine: a strip 5 µm tall × 400 µm long passes (short dim 5 µm).
- Square-ish + big fails: a ~30 × 30 µm solid pad fails (both dims ≥ 30 µm).
- Verified: a solid blob was clean at 480 µm macro scale, tripped MSLOT at 520 µm.
- Verified: line-screened strips up to ~11 µm tall of *any* length are clean.

**Renderer rule (enforce at synthesis time):**
> Never emit a connected solid-metal component whose **minimum width exceeds ~28 µm**
> (keep a margin under the 30 µm rule). If a region would be larger than that in both
> axes, break it up — screen it (lines/dots/mesh) so every resulting metal strip is
> thin in at least one axis.

This is a *geometry* rule, so it must be applied **after** the screen is synthesised
on-grid, on the actual metal polygons — not on the source image.

## Translating to pixels

The renderer works in pixels at `pixel_size` µm/px. Convert the limit once:

```
max_solid_short_px = floor(30 / pixel_size) - safety_margin
# pixel_size = 0.60 µm  ->  30/0.60 = 50 px  ->  cap solid strips at ~46 px short-dim
```

So at 0.60 µm/px, keep any solid feature under ~46 px in its narrow dimension. Our
`solid_screen = 20` fill (18 px = 10.8 µm strips) sits comfortably under this.

## Minimum feature / gap (the other floor)

- PDK metal minimums: width/space ≥ 0.23 µm (M1) / 0.28 µm (M2–M5); min area 0.1444 µm².
- **Binding constraint is not the PDK floor — it's the cleanup pass.** The 2×2
  morphological open needs every feature *and* every gap to be **≥ 2 px** to survive
  (a 1 px line or 1 px gap gets erased and can leave sub-min slivers). At 0.60 µm/px,
  2 px = 1.2 µm, already well above the PDK min. So: **min feature = min gap = 2 px.**

## How the line-fill knob stays clean at any density

`solid_screen = P` fills a "solid" region with horizontal lines of `feature = P-2`,
`gap = 2` px. Every emitted strip is `feature` px tall (short dim) and arbitrarily long:

- Clean for **any** pitch as long as `feature < max_solid_short_px` (≈46 px @ 0.6 µm).
- Density = `(P-2)/P`, so higher pitch = darker. `P=20` ≈ 90 % fill, still clean.
- **Upper bound caveat:** if `P` gets so large that a whole letter-body/stroke is
  thinner than one pitch, it receives *no* gap and reverts to a fully solid 2-D blob —
  which can then exceed 30 µm in both axes and re-trip MSLOT. Cap the pitch so a gap
  falls inside every fillable region (P ≈ 20 was the safe max for the blackletter logo).

## What the renderer does NOT need to handle

These are **die-level** rules that any isolated metal-only macro trips and that clear at
chip integration (dummy fill / full floorplan) — not the renderer's job, don't chase them:

- `M1.4 M2.4 M3.4 M4.4 M5.4` — per-layer minimum metal density
- `MT.3` — top-metal density
- `PL.8` — a passivation/dummy rule

A clean isolated art macro therefore floors at **7 "benign" violations, zero of them
width/space/area/MSLOT.** That "7 and only 7" is the renderer's pass/fail target.
