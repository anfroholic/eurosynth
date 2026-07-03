# Adding custom art to the eurosynth die (top-right open area)

**Feasibility: yes, and the repo already has the exact machinery.** The wafer.space
logo you can see in the top-left of the render is a PNG that gets converted to a GDS
"art macro" and dropped onto the die. We reuse that same path for your art, place it in
the open top-right, and re-harden. PNG and JPEG work directly; SVG needs one extra
rasterize step.

---

## 1. How it works today (the logo is the template)

`ip/gf180mcu_ws_ip__logo/` is a self-contained art macro:
- `image/wafer_space_logo.png` — the source image
- `script/make_gds.py` — a generic **image → GDS** converter (uses KLayout + PIL/Pillow)
- `Makefile` — the one command that builds it (+ runs metal DRC on the result)
- `gds/ lef/ lib/ vh/` — the four macro views the chip flow consumes

The build command (`Makefile`) is:
```
python3 script/make_gds.py image/wafer_space_logo.png gds/<name>.gds \
  --cellname <name> --invert --merge --pixel-size 0.75 --width 191 --height 191 \
  --foreground "34/0" "36/0" "42/0" "46/0" "81/0" --boundary "0/0" "152/5"
```
What each part means:
- **The image is thresholded to 1-bit** (black/white). Every "on" pixel becomes a small
  square of metal. There is no color or grayscale on silicon — a pixel is either metal
  or not — so the art is effectively a **high-contrast silhouette/stencil**. Logos, line
  art, text, and bold graphics work great; photographs turn into blobs.
- `--pixel-size 0.75` = each pixel is 0.75 µm of metal. `--width 191 --height 191`
  rescales the image to 191×191 px → **191 × 0.75 = 143.25 µm** square (that's the logo's
  physical size). So **final size µm = pixels × pixel-size**; you dial size with these.
- `--merge` fuses touching pixels into clean polygons (fewer shapes, DRC-friendly).
- `--foreground "34/0" "36/0" "42/0" "46/0" "81/0"` = the GDS layers drawn on. Those are
  **Metal1, Metal2, Metal3, Metal4, Metal5** — the logo is a solid stack of all five
  metals, which is why it reads boldly in the die photo. You can use fewer layers.
- `--boundary "0/0" "152/5"` draws the cell outline / PR-boundary box.
- The `Makefile`'s `drc` target runs KLayout DRC (`feol=false beol=true` — metal-only,
  since art has no transistors).

The macro's `LEF` marks its whole footprint as an **obstruction on Metal1–5**, so the
router and the power grid treat it as a keep-out and route *around* it — exactly like the
5 engine macros. That's what keeps the art from shorting to the PDN straps.

---

## 2. Supported input formats

| Format | Works? | Notes |
|---|---|---|
| **PNG** | ✅ direct | Best choice. Alpha handled (`--invert-alpha` if the transparency is backwards). |
| **JPEG** | ✅ direct | Pillow reads it; just note JPEG artifacts can fuzz the threshold edges. Prefer a clean, high-contrast source. |
| **SVG** | ⚠️ one extra step | `make_gds.py` uses Pillow, which doesn't read SVG. Rasterize first: `cairosvg art.svg -o art.png -W 1200 -H 1200` (or Inkscape/rsvg). SVG is actually the *ideal* source because it's resolution-independent — render it large, then convert. |

All three become the same 1-bit metal stencil in the end. Pick the art with clean, bold
shapes and strong black/white contrast; tune `--threshold` (default 128) to set where the
cut between "metal" and "empty" falls.

---

## 3. Where it goes (the open top-right)

- **Die area:** ~3932 × 2531 µm. **Core (placeable) area:** ~[442, 442] – [3490, 2089] µm.
- **Engines** sit along the bottom/center: ks (480,480, large), chaos (1680,480),
  neural (2560,480), sid (1680,1420), bytebeat (2100,1420).
- **The open top-right** of the core is roughly **x ∈ [2700, 3490], y ∈ [1400, 2089]** —
  the uniform gold region in the render. That's about **~790 × ~690 µm** of clear space
  (currently just PDN straps over empty silicon).
- The top-right **die corner** already holds the wafer.space `marker` (the diagonal
  corner glyph) at `[$DIE_AREA[2]-281, $DIE_AREA[3]-281]`; art should sit *inside* the
  core, clear of that.

**Suggested placement:** a ~500–650 µm-square art macro with its lower-left corner near
**[2800, 1400]** (spans up to ~[3450, 2050]) — comfortably inside the core, above neural,
right of bytebeat. Exact size/spot is your call; bigger reads better in a die photo, and
there's room to go ~650 µm.

Placement uses the same `MACROS:` mechanism as the logo (in
`librelane/macros/macros_5v.yaml`):
```yaml
  eurosynth_art:
    gds:  [dir::../ip/eurosynth_art/gds/eurosynth_art.gds]
    lef:  [dir::../ip/eurosynth_art/lef/eurosynth_art.lef]
    vh:   [dir::../ip/eurosynth_art/vh/eurosynth_art.v]
    lib:  { <9 corners>: [...] }        # a trivial empty .lib, like the logo's
    instances:
      art_inst: { location: [2800, 1400], orientation: N }
```

---

## 4. Constraints & risks (all manageable)

1. **1-bit only.** No color/gradient. Design for a bold stencil. (Metal is present-or-not.)
2. **Metal DRC (min width/space).** Keep `--pixel-size ≥ ~0.3 µm` and use `--merge` so no
   sliver is below GF180's minimum. The logo's 0.75 µm is safely above the floor.
3. **Metal density (max).** A large *solid* multi-metal block can exceed the max-density
   rule locally. Mitigations: use **line-art/outline** rather than solid fill, use **fewer
   metal layers**, or keep it moderately sized. The `beol` DRC step flags this and we
   adjust before committing.
4. **No PDN short.** Handled automatically: the art is an **obstruction macro**, so PDN
   regenerates around it (same as the engines). We do *not* hand-draw metal into a live
   power region.
5. **LVS "disconnected module."** The art has no pins/nets. It must be added to
   `IGNORE_DISCONNECTED_MODULES` in `librelane/config.yaml` (the 5 markers are already
   there) and instantiated as a `(* keep *)` black box in `src/chip_top.sv` (exactly like
   `gf180mcu_ws_ip__logo wafer_space_logo ();`), or LVS/synthesis will complain.
6. **Antenna.** Metal-only art with no gate connection is an isolated island — no antenna
   ratio to a transistor — so it's a non-issue in practice; the antenna deck still runs.
7. **Bounds.** Must stay inside the core and clear of the sealring/corner marker. The
   suggested coordinates already do.

---

## 5. Step-by-step to actually add it

1. **You provide** the image (PNG/JPEG/SVG) + a rough desired size (e.g. "as big as fits,
   ~600 µm") and which look — solid or outline.
2. Create `ip/eurosynth_art/` mirroring the logo dir (script + Makefile).
3. Generate the GDS: `make_gds.py <img> ... --pixel-size <p> --width <W> --merge
   --foreground <layers> --boundary "0/0" "152/5"` → pick size/layers per §4.
4. Write the matching **LEF** (obstruction block of the art's exact size), a trivial
   **.lib** and **.v** black box (copy the logo's, rename).
5. Add the macro to `macros_5v.yaml` **and** `macros_3v3.yaml` (one dict, per the
   no-deep-merge rule), add it to `IGNORE_DISCONNECTED_MODULES`, and instantiate the
   black box in `src/chip_top.sv`.
6. **Re-harden + re-sign-off** the chip (a full run) and re-run the CoB precheck, since
   the GDS changes. Expect it to stay green — the art is physically inert — but density
   DRC is the one thing to watch, and we tune pixel-size/layers/size if it flags.

**Cost:** one image from you + ~1 full chip re-harden (~45–75 min) + re-precheck. Low
functional risk (no logic touched); the only real iteration point is metal density on a
large solid graphic, which we control via size/outline/layer count.

---

## 6. Recommendation

Send an **SVG or a clean high-contrast PNG** of what you want (a logo, wordmark, or bold
line-art graphic reads best). I'll target a ~550–650 µm outline-style rendering on 2–3
metal layers placed near [2800, 1400], generate the macro, and fold it into the next
chip run so it lands with the rest of signoff. If you want, I can also do a quick
throwaway conversion first so you can *see* the 1-bit stencil before we commit it to a
full harden.
