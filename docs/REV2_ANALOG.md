# EuroSynth Rev 2 — Going Analog 🎛️⚡

*A feasibility report: new voices for the second revision, built as real analog
circuits on GF180MCU instead of RTL.*

> 🎧 **Hear the candidates:** [web/rev2/](../web/rev2/index.html) is a PyScript
> preview lab with behavioral simulations of every voice below — play them in the
> browser and pick favorites before any silicon is designed.
> (Live once deployed: `anfroholic.github.io/eurosynth/web/rev2/`.)

**TL;DR recommendation:** Rev 2 should be a **mixed-signal homage to the classic
synth chips (CEM3340 / SSM2044 era)** — keep the proven digital spine as the
controller, and add a small roster of hand-designed analog macros: an **expo-VCO**,
an **OTA-C voltage-controlled filter**, a **VCA**, a **noise source**, and a
**wavefolder**, glued together by an on-chip **DAC + CV bias infrastructure**.
Every analog macro gets its own pads and a standalone signoff recipe, exactly the
way `eurosynth_art` and `meme_puf` were done — that pattern is our biggest rev-1
asset and it transfers directly.

---

## 1. Where rev 1 leaves us

Rev 1 shipped a fully digital 8-slot voice (bypass, saw, square, SID homage,
Karplus-Strong, chaos, bytebeat, neural morphing oscillator) with clean signoff
(DRC/LVS/antenna = 0, precheck PASS) on the wafer.space 1x0p5 slot
(~3.93 × 2.53 mm, 5 V GF180MCU).

Assets that carry straight into an analog rev 2:

- **The spine + SPI config port.** A working digital controller with a 128×16
  register file. In rev 2 this becomes the *brain* that sets analog parameters
  (CV DAC codes, switch matrices, calibration trims) — we don't have to invent a
  control plane.
- **The custom-GDS macro pipeline.** `ip/eurosynth_art` and `ip/meme_puf` proved
  we can author non-standard-cell geometry in Python, run standalone per-macro
  DRC, and drop the result into the chip with declobber/no-fill recipes without
  breaking die-level signoff. An analog macro is *exactly* this workflow, plus a
  schematic and a SPICE deck.
- **`meme_puf` is already analog.** The passive resistor PUF (ppolyf_u recipe,
  ratiometric readout, dedicated pads) was our first analog structure. Rev 2 is
  "that, but with transistors."
- **The golden-model verification culture.** Spec → Python model → golden vector
  → RTL → self-checking TB. The analog translation is: spec → ngspice testbench
  with numeric pass/fail `.measure` criteria → corners → post-layout re-sim.
  Same philosophy, different simulator.

---

## 2. What GF180MCU actually gives us (device inventory)

Checked against the vendored PDK (`d658698b`, gf180mcuD variant, 5LM + MIM).
This is a genuinely good analog process for a synth — it's a 180 nm 5 V node,
the same era and voltage class as real 90s/2000s synth ASICs.

| Category | Devices | Synth relevance |
|---|---|---|
| MOSFETs | `nfet/pfet_03v3`, `_05v0`, `_06v0`, native `nfet_06v0_nvt`, 10 V LDMOS `nfet/pfet_10v0_asym` | OTAs, current mirrors, switches; native NFET for low-Vt input stages; 10 V devices for a hotter output stage or noise breakdown experiments |
| Bipolars | Vertical NPN 0.54×2 → 10×10 µm (4 sizes); PNP 5×0.42 → 10×10 µm | **The headline.** Matched NPN pairs = exponential V/oct converters, translinear VCAs, ladder filters — the CEM/SSM building blocks. (PNPs are substrate-collector; usable for bandgaps, not free-floating.) |
| Resistors | Diffusion (`nplus/pplus`), poly (`npolyf/ppolyf`), **high-sheet `ppolyf_u_1k/2k/3k`** (1–3 kΩ/sq), metal `rm1–rm4`, thick-metal `tm*` | Big on-chip R without big area — we already used `ppolyf_u` in the PUF. Matched R networks → R-2R DACs, ratioed gain stages |
| Capacitors | MIM 1.0/1.5/2.0 fF/µm² (M2M3 → M5M6 stacks), MOS caps 3.3 V/6 V | 10 pF ≈ 71×71 µm — cheap. 100 pF ≈ 0.05 mm² — affordable for a few. 1 nF ≈ 0.5 mm² — only if we really mean it |
| Other | `efuse`, junction diodes, full xschem symbol set, ngspice + Xyce models, Magic/Netgen/KLayout decks, **`gf180mcu_fd_io__asig_5p0` analog pad** | Efuse = per-die calibration storage. The analog pad cell means the template's pad ring can carry true analog signals without abusing digital bidirs |

### The one hard constraint: capacitance vs. audio frequencies

Audio time constants are *enormous* by chip standards. A naive RC at 100 Hz with
10 pF needs R = 160 MΩ. Three honest ways around it, and rev 2 should use all three:

1. **Subthreshold gm-C.** An OTA biased at nA-level currents has gm ≈ 100 nS–10 µS;
   with C = 10–20 pF that puts f = gm/2πC anywhere from ~1 Hz to ~100 kHz,
   *electronically tunable by bias current*. This is how on-chip audio filters are
   really built, and — bonus — **bias current = the CV input**. The filter cutoff
   knob falls out of the topology for free.
2. **External timing caps on pins.** Exactly what CEM3340 (VCO cap) and SSM2044
   (filter caps) did. Costs pads, buys precision and huge time constants
   (envelopes, LFOs). Authentic to the homage.
3. **High-sheet poly R.** `ppolyf_u_3k` at 3 kΩ/sq makes 1–10 MΩ practical in
   modest area for bias networks and leak paths.

Second constraint, cultural: **analog silicon is one-shot with no scope probes
inside.** Mitigation is architectural — §5 and §6.

---

## 3. Proposed rev 2 analog voices & macros

Ordered by tier: A = high confidence first-silicon-works, B = solid but with a
known hard part, C = research/flex. Each entry: what it is, the circuit, the
GF180 primitives, and the risk.

### Tier A — the backbone (do all of these)

**A1. `analog_vco` — Exponential VCO (CEM3340 homage)** ⭐ *the flagship*
- Triangle/saw core: a MIM (or external pin) cap charged by a current source,
  discharged/reversed by a comparator — classic relaxation core.
- In front of it, the sacred circuit of analog synthesis: a **matched NPN pair
  exponential converter**, turning a linear CV into an exponential current →
  **volts-per-octave** pitch tracking. GF180's vertical NPNs (use the 10×10 µm
  devices, cross-coupled quad layout for matching) are exactly what this wants.
- Temperature compensation: the classic tempco-resistor trick doesn't exist
  on-chip, but we have something better — an on-die **PTAT reference** (bandgap
  core, §3 infrastructure) and per-die **efuse calibration**.
- Outputs: saw + triangle + PWM square (comparator vs. a CV).
- Risk: medium-low. The core is forgiving; V/oct *accuracy* is the stretch goal,
  V/oct *behavior* is nearly guaranteed.

**A2. `analog_svf` — OTA-C state-variable filter (2-pole, LP/BP/HP)** ⭐
- Two subthreshold OTA integrators + summing stage = state-variable topology.
  Cutoff = OTA bias current (direct CV control), resonance = a third OTA in the
  damping path — up to self-oscillation, at which point it's *also a sine VCO*.
- All on-chip: 2 × ~20 pF MIM, three OTAs, ~0.01 mm² of active area.
- This is the single highest musical-value-per-risk block on the list.
- Risk: low. gm-C SVFs are textbook; the only tuning question is bias range vs.
  audio band, which ngspice answers before tapeout.

**A3. `analog_vca` — Translinear VCA (Gilbert / diff-pair)**
- NPN differential pair with a current-steering CV, or a full Gilbert cell
  (which doubles as **A6**, the ring modulator, with a mode pin).
- Risk: low. Distortion vs. control-feedthrough tradeoffs are simulable.

**A4. `analog_noise` — White/pink noise source**
- Honest assessment: junction avalanche noise (the classic zener hiss) wants
  ~7–12 V reverse bias; the 10 V LDMOS domain *might* reach usable breakdown on
  a bare junction, but that's uncharacterized territory. The safe design is
  **amplified thermal noise**: a big `ppolyf_u_3k` resistor (or a nA-biased
  MOSFET's channel noise) into a 60–80 dB chopped gain chain.
- Add a switchable gm-C pinking filter (−3 dB/oct approximation, 3–4 poles).
- Risk: low for white-via-thermal; the avalanche variant goes on the test-strip
  (§6) as an experiment, not on the critical path.

**A5. `analog_bias` — Bandgap + bias/CV infrastructure** *(not a voice, but the
block every voice depends on)*
- Bandgap voltage reference (substrate PNPs — their canonical use), PTAT current
  reference, a bias-distribution mirror tree, and an **8–10 bit DAC** the SPI
  spine writes to generate CVs on-chip (matched `ppolyf_u` R-2R, or a binary
  current-steering mirror array).
- This is what makes rev 2 a *chip* instead of a pile of experiments: digital
  spine → SPI → DAC codes → analog CVs → voices. Build and verify it first.
- Risk: low-medium (bandgaps are well-trodden; mismatch sim required).

### Tier B — the character pieces (pick 2–3)

**B1. `analog_ladder` — 4-pole transistor ladder filter (Moog homage)**
- The famous NPN ladder, on our vertical NPNs, with the four ladder caps either
  small MIMs (gm-scaled) or four pins for external caps (the vintage move).
  Feedback resonance tap → self-oscillation.
- Risk: medium. DC operating point across a 4-high ladder stack on a 5 V rail is
  tight (the original ran on ±15 V (later Moogs used lower rails)); needs careful headroom design. If it doesn't
  fit, the diode-ladder variant (B2) stacks shorter.

**B2. `analog_diode_ladder` — Diode ladder (TB-303 flavor)**
- Same idea, diode-connected NPNs, lower stack height, squelchier resonance.
  Cheaper headroom than B1 — if only one ladder makes the die, make it this one
  and let the SVF (A2) cover the "clean" filter role.

**B3. `analog_folder` — Serge/Buchla-style wavefolder** ⭐ *most sound-per-mm²*
- 4–6 cascaded differential pairs with staggered offsets, summed — each pair
  "folds" the waveform once as drive increases. Feed it the VCO triangle and a
  drive CV and you get the whole West-Coast timbre family from ~30 transistors.
- Risk: low-medium. Static nonlinearity, trivially characterized in ngspice;
  mismatch just *changes* the folds, it doesn't break them.

**B4. `analog_drum` — Bridged-T resonator drum voice (808 homage)**
- Bridged-T RC resonator + trigger pulse = 808 kick/tom "ping". Audio-rate decay
  wants big RC: high-sheet poly R (MΩ) × 100 pF MIM gets into range on-chip;
  one external-cap pin makes it a full kick drum. Add the noise source (A4)
  through a VCA snap → snare.
- Risk: medium (area for C, decay-time targets need sim iteration).

**B5. `analog_slew` — OTA slew limiter / AD envelope**
- One OTA + cap + rectifying feedback = slew limiter, which eurorack folks know
  is secretly an envelope generator, an LFO (self-cycled), and a legato machine.
  External cap pin for LFO-rate time constants. Cheap; shares the OTA cell from A2.

### Tier C — research flex (test-strip candidates, not roster commitments)

**C1. `analog_bbd` — Bucket-brigade / switched-cap delay line**
- 256–1024 stages of MOS switch + MIM cap, two-phase clocked from the spine =
  a real BBD-style lo-fi delay/chorus. Charge injection and clock feedthrough
  are the enemies; vintage grit is the aesthetic, so partial failure still
  sounds like a Memory Man. 512 stages × ~0.5 pF ≈ very affordable area; the
  design effort is in the switch/cap cell and the anti-alias assumption.
- High effort, extremely high cool factor. Prototype the cell on the test strip
  in rev 2; ship the full line in rev 3.

**C2. `analog_chua` — Chua's circuit chaos voice**
- The canonical chaotic oscillator, with the inductor replaced by a gyrator
  (2 OTAs) and the nonlinear resistor as a diff-pair — fully integrable, and
  the analog twin of rev 1's digital chaos engine. Double-scroll attractor as
  an audio-rate voice / modulation source.

**C3. `lunetta_bank` — CMOS-abuse voice (Schmitt relaxation oscillators)**
- A bank of standard-cell Schmitt triggers with poly-R + MIM feedback = the
  classic CD40106 "Lunetta" drone synth, on-die. Nearly zero design risk
  (they're just standard cells + passives) and a nice hedge: if every real
  analog block fails, the chip still bleeps analogically.

**C4. `analog_lpg` — Low-pass gate**
- Buchla LPG without the vactrol: one gm-C pole whose bias current is driven by
  a slew-limited (A5) envelope — "ringy" amplitude+brightness gating in one
  block. Mostly a wiring pattern over A2+A5 cells; cheap if those exist.

### Suggested rev 2 roster (fits the ethos: one spine, isolated voices)

| Slot | Macro | Tier |
|---|---|---|
| 1 | `analog_bias` (bandgap, PTAT, CV DACs) | A — build first |
| 2 | `analog_vco` expo VCO | A |
| 3 | `analog_svf` 2-pole OTA filter | A |
| 4 | `analog_vca` / ring-mod (shared Gilbert) | A |
| 5 | `analog_noise` + pinking filter | A |
| 6 | `analog_folder` wavefolder | B |
| 7 | `analog_diode_ladder` **or** `analog_drum` | B |
| 8 | Device test strip + C-tier experiments (BBD cell, avalanche junction, Chua core) | C |
| — | Digital spine, SPI, 2–3 best rev-1 engines retained | carried over |

Signal chain that falls out: **VCO → folder → filter → VCA → out**, noise into
the filter, everything CV-able from SPI. That is a complete East+West-coast
analog voice on one die.

---

## 4. How to actually do analog design — the methods

### 4.1 The classic open-source flow (primary recommendation)

**xschem → ngspice → Magic/KLayout → Netgen → PEX → re-sim.** Everything needed
is *already in our vendored PDK* (`libs.tech/xschem`, `libs.tech/ngspice`,
`libs.tech/magic`, `libs.tech/netgen`, `libs.tech/klayout`, plus Xyce models):

1. **Schematic capture — xschem.** PDK ships full symbol libraries (including
   the `asig_5p0` pad symbol). One `.sch` + testbench per macro, in-repo.
2. **Simulation — ngspice** (Xyce as a second opinion / for big transients).
   Per-macro self-checking deck: `.measure` statements with numeric pass/fail —
   our golden-vector culture, verbatim. Sweep **corners** (typical/ss/ff ×
   temperature × supply — the model libs are sectioned for exactly this) and
   **Monte Carlo mismatch** for anything depending on matching (expo pair, DAC,
   bandgap).
3. **Layout — Magic or KLayout.** Hand layout for the truly analog cells
   (matched quads, common-centroid, guard rings). Magic gives interactive
   DRC + extraction; final signoff stays on our existing KLayout deck.
4. **LVS — Netgen** (schematic netlist vs. extracted layout), plus the KLayout
   LVS deck we already run at die level.
5. **PEX — Magic-extracted parasitics** back into ngspice. Non-negotiable gate
   before integration: the *extracted* netlist must pass the same `.measure`
   criteria as the schematic.
6. **Integration** — the proven `eurosynth_art`/`meme_puf` pattern: standalone
   per-macro DRC recipe, GDS drop-in with declobber + fill exclusion, LVS
   stub/abstract at die level, `asig_5p0` pads for analog I/O, guard-ringed
   macro boundary, dedicated analog VDD/VSS pads (star-routed, not shared with
   the digital core's grid).

New repo machinery this implies: `make asim` (per-macro ngspice regressions in
the docker image, green/red like `make sim`) and an `ip/analog_*/` layout per
macro mirroring the existing custom-macro directories.

### 4.2 Generator-based layout (Python → GDS)

We already author GDS in Python for the art macros. Two upgrades of that skill:

- **Parametric device generators** with `gdstk`/`gdsfactory`: write a
  `matched_npn_quad()`, `ota()`, `r2r_ladder()`, `mim_array()` once, with DRC
  rules baked into the generator, and every macro reuses them. The PUF resistor
  recipe is the existing seed of this library.
- **glayout / OpenFASOC** (the open-source analog-generator ecosystem) has
  GF180MCU support for some generators (OTA, temp-sensor class blocks). Worth
  evaluating as a source of pre-hardened cells — with the caveat that GF180
  coverage is younger than SKY130's; treat outputs as starting points that
  still go through our own sim + signoff, not as trusted IP.

### 4.3 Automated analog P&R (ALIGN, MAGICAL) — *evaluate, don't depend*

Academic analog place-and-route exists and occasionally shines, but maturity on
GF180 is low. Reasonable for a non-critical block as an experiment; the roster
blocks should be hand-laid. Mentioned for completeness.

### 4.4 Silicon-proven IP reuse

Efabless ran open **GF180MCU analog design challenges ("Chipalooza")** —
open-source opamps, bandgaps, LDOs and DACs on this exact PDK exist publicly,
some silicon-validated. Before designing `analog_bias` from scratch, survey
those repos: adopting a proven bandgap/opamp and spending our novelty budget on
the *musical* circuits (VCO, folder, ladder) is the smart trade. License check
(most are Apache-2.0) + our own re-sim required. *(Repo survey = first action
item; availability to be confirmed per-block.)*

### 4.5 The "on-die breadboard" hedge

Dedicate one macro slot to a **device test strip**: isolated single devices and
sub-cells (NPN quad, one OTA, DAC slice, BBD cell, avalanche junction) wired
straight to pads. Costs little area, and after tapeout it turns the chip itself
into our model-validation lab — every rev 3 design gets calibrated against
*measured* rev 2 silicon instead of foundry-model faith. This is the single
best de-risking instrument available to a one-shot hobby tapeout.

### 4.6 Verification doctrine (the golden-model culture, translated)

| Rev 1 (digital) | Rev 2 (analog) |
|---|---|
| Python golden model | ngspice testbench with `.measure` pass/fail |
| Bit-exact golden vector | Numeric spec windows (fc range, THD, V/oct error, PSRR) |
| Self-checking iverilog TB | Self-checking spice deck, `make asim` regression |
| One commit per green engine | One commit per green macro, schematic+sim+layout+PEX |
| STA corners | PVT corners + Monte Carlo mismatch |
| GL sim after harden | Post-PEX re-sim after layout |

Plus analog-only disciplines: common-centroid/interdigitated matching for
anything precision, dummies at array edges, guard rings around every macro,
substrate-noise moat between the digital spine and analog blocks (the spine's
clock is the loudest aggressor on the die — physical separation + separate
supply pads + quiet-clock SPI mode during listening tests).

### 4.7 Board-level reality (unchanged truths)

Eurorack CVs are ±5/±10 V; the die is 0–5 V single-supply. Level shifting stays
on the module PCB regardless of what we integrate — so rev 2's job is the
*voice*, not the front panel. External-cap pins (VCO core, envelope, drum) are
a feature, not a compromise: it's how every classic synth chip did it, and it
lets the module designer choose ranges.

---

## 5. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Untrusted analog models (first analog silicon on this flow) | Medium | Test strip (§4.5); conservative topologies; corners+MC everywhere |
| V/oct accuracy misses musical tolerance (±1 cent/octave-class) | High for first silicon | Ship it anyway with efuse/SPI trim + firmware calibration via the spine; spec "tracks ~5 octaves after cal" not "perfect" |
| Ladder filter headroom on 5 V | Medium | Diode ladder fallback (B2); SVF (A2) is the guaranteed filter |
| Digital spine noise couples into audio | High if ignored | Guard rings, separate analog supply pads, physical moat, quiet-mode clock gating |
| MIM/area budget blowout | Low | Caps costed per-block up front; external-cap pins as pressure valve |
| Analog LVS/extraction flow friction (new for us) | Medium | `meme_puf` LVS learnings; bring up flow on a trivial cell (single OTA) end-to-end *first* |
| One block fails and takes the die with it | Low | Rev-1 isolation ethos: every macro pad-independent; Lunetta bank (C3) as the all-analog-fails hedge |

---

## 6. Proposed milestones

1. **M0 — Flow bring-up:** one OTA through xschem → ngspice → layout → Netgen
   LVS → PEX → re-sim → standalone DRC, in-repo, in docker (`make asim`).
   *This milestone is the whole game; everything after it is repetition.*
2. **M1 — Infrastructure:** `analog_bias` (bandgap + PTAT + CV DAC) green at
   corners + MC; Chipalooza IP survey folded in.
3. **M2 — Backbone voices:** VCO, SVF, VCA, noise — each green schematic → each
   green post-PEX, one commit per macro.
4. **M3 — Character blocks:** folder + (diode ladder | drum); test strip frozen.
5. **M4 — Integration:** macros into chip_top beside the retained digital
   engines; substrate-noise floorplan; die-level DRC/LVS/antenna = 0; precheck
   `--cob` PASS (existing recipe).
6. **M5 — Tapeout + bring-up plan:** per-macro test procedures written *before*
   submission (what to measure, expected windows, cal procedure), mirroring the
   HARDWARE_GUIDE pattern.

---

## 7. Bottom line

Rev 1 proved the flow, the spine, the macro-integration tricks, and the
verification culture. Rev 2's thesis: **the same 180 nm 5 V process that made
the digital chip clean is, historically, a *synth-chip process*** — it has the
matched bipolars, the 1–3 kΩ/sq poly, and the MIM caps that the CEM/SSM
generation was built from. The recommended build is the Tier-A backbone
(bias/DAC, expo-VCO, SVF, VCA, noise) plus a wavefolder and one ladder-family
filter, a test strip for the wild ideas (BBD, avalanche noise, Chua), and the
digital spine kept as conductor. That yields a complete analog voice chain —
**VCO → folder → filter → VCA** — that is simultaneously a working instrument
and the calibration platform for everything we'll want to do in rev 3.
