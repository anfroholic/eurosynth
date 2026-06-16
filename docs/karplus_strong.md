# Karplus-Strong plucked-string engine (`ks_engine`)

## What it is / why it's first

Karplus-Strong (KS) synthesis makes a convincing plucked-string / percussive tone
from almost nothing: fill a short delay line ("the string") with a burst of noise,
then circulate it through itself while a gentle low-pass-ish feedback filter bleeds
off energy each pass. The noise burst is the "pluck"; the recirculating, slowly
decaying filtered signal is the ringing string. It is the ideal **first real voice
engine** because it is tiny, purely integer, completely deterministic, and exercises
the whole engine contract end-to-end (reset, `sample_tick` advance, stable registered
`sample`, mux slot) -- so it shakes out the spine + verification flow before the
harder engines (chaos, SID, bytebeat, neural) land. See `NOTES.md`
("The engine contract" and "Engine roadmap").

## Ports (matches the contract in NOTES.md exactly)

| port          | dir | width                  | meaning |
|---------------|-----|------------------------|---------|
| `clk`         | in  | 1                      | system clock |
| `rst_n`       | in  | 1                      | active-low synchronous reset |
| `sample_tick` | in  | 1                      | 1-clk audio-rate strobe; the sustain step happens on this pulse |
| `pluck`       | in  | 1                      | 1-clk strobe: (re)excite the string with a fresh noise burst |
| `period`      | in  | `$clog2(NMAX)` (=10)   | delay length N, sets pitch; valid range 2..NMAX-1 |
| `sample`      | out | `signed [SAMPLE_W-1:0]`| current output, registered, stable between ticks |

## Parameters (chosen defaults)

| parameter     | default        | meaning |
|---------------|----------------|---------|
| `SAMPLE_W`    | 16             | sample bit width (signed two's complement) |
| `NMAX`        | 1024           | delay-line depth = maximum period (lowest pitch) |
| `DECAY_NUM`   | 2047           | feedback-gain numerator |
| `DECAY_SHIFT` | 12             | feedback gain = `DECAY_NUM / 2^DECAY_SHIFT` = 2047/4096 ≈ **0.49976** |
| `LFSR_SEED`   | `16'hACE1`     | initial LFSR state (also reset value) -> reproducible noise burst |
| `LFSR_POLY`   | `16'hB400`     | Galois taps: x^16 + x^14 + x^13 + x^11 + 1 (maximal-length 16-bit) |

The pair `(DECAY_NUM, DECAY_SHIFT)` together encode a fixed-point feedback gain
strictly **below 1/2 per tap** (the two-tap average `(out+prev)` already supplies the
×2), which keeps the loop strictly contractive (decaying) and -- crucially -- keeps
the stored value inside 15-bit magnitude so no saturation logic is needed (see
overflow analysis).

## The exact integer algorithm (this is the contract the RTL implements)

State: `signed [15:0] line[0..NMAX-1]` (the delay line / "string"), index `ptr`, a
16-bit `lfsr`, and effective length `N = clamp(period, 2, NMAX-1)`.

**Galois LFSR step** (deterministic noise; identical in Python and Verilog):
```
lsb  = lfsr & 1
lfsr = lfsr >> 1
if lsb: lfsr = lfsr XOR LFSR_POLY      // 16-bit
```
The seeded sample value = the 16-bit `lfsr` word reinterpreted as **two's-complement
signed 16-bit**.

**Pluck (re-excite):** reset `lfsr = LFSR_SEED`, then for i in 0..N-1: step the lfsr,
write `line[i] = signed16(lfsr)`. Set `ptr = 0`.
(In RTL this is incremental -- one write per clk after the `pluck` strobe, a
synthesizable single write port; it completes within N clks, well before the next
`sample_tick`. The Python model does it at sample granularity -- same final buffer.)

**Sustain step** (on each `sample_tick`, when not seeding):
```
out  = line[ptr]
prev = line[(ptr + N - 1) mod N]
acc  = (out + prev) * DECAY_NUM        // signed, compute in >= 32-bit
new  = acc >>> DECAY_SHIFT             // ARITHMETIC right shift (floor toward -inf)
line[ptr] = new[15:0]                  // low 16 bits; |new| < 32768 so no overflow
ptr  = (ptr + 1) mod N
sample <= out                          // registered output = value read THIS tick
```

**Reset:** line all 0, `ptr = 0`, `lfsr = LFSR_SEED`, `sample = 0`.

## Fixed-point / overflow analysis

Let `g = DECAY_NUM / 2^DECAY_SHIFT = 2047/4096 < 1/2`. Each new sample is
`new = floor( (out + prev) * g )`. With `|out|, |prev| <= 32767` (15-bit magnitude max
after the very first pluck, where samples are LFSR words in `[-32768, 32767]`):

```
|out + prev| <= 65535
|new| <= 65535 * 2047 / 4096 = 32766.5...  -> floor magnitude <= 32766 < 2^15 = 32768
```

So the stored value always fits in **15-bit magnitude**: there is never a true
two's-complement overflow of the 16-bit store, and **no saturation logic is required**.
After the first sustain pass the amplitudes only shrink (the loop is contractive,
`g < 1/2` with two taps gives an effective loop gain < 1), so the bound stays
comfortable. The golden run was instrumented and the worst observed `|new|` was
**19204** (well under 32768), confirming the bound empirically.

**Truncation / rounding convention:** the right shift is an **arithmetic** shift
(`>>>` in Verilog on a signed operand), i.e. it **floors toward -infinity** (e.g.
`-1 >> 1 == -1`, not `0`). This is matched bit-for-bit in the Python model by using
plain Python `int` and `>>` (which also floors toward -inf for negatives). The store
keeps the **low 16 bits** and reinterprets them as two's complement
(`new & 0xFFFF` then sign-extend), so model and RTL agree exactly even at the wrap
boundary. There is **no rounding** -- pure truncation toward -inf.

## Decay / pitch notes

- **Pitch:** the loop period is `N` samples, so the fundamental is approximately
  `f ≈ fs / N`. At `fs ≈ 48.8 kHz` (clk = 50 MHz, `BCLK_DIV = 16`; see NOTES "Timing"),
  `N = 48` gives `f ≈ 48800 / 48 ≈ 1017 Hz` (roughly a high C). Valid `N` is
  `2..NMAX-1`; `N = NMAX-1 = 1023` is the lowest note, `≈ 47.7 Hz`.
- **Decay:** each circulation of the string applies the two-tap filter with per-tap
  gain `g ≈ 0.49976`. The averaging tap is a one-pole low-pass, so higher harmonics
  die faster than the fundamental (the classic KS "pluck then mellow" timbre). The
  fundamental's amplitude is multiplied by roughly `2g ≈ 0.9995` per loop (each loop =
  `N` ticks). Time to fall to `1/e`:
  `loops ≈ 1 / (1 - 2g) ≈ 1 / 0.000488 ≈ 2048 loops`, i.e.
  `2048 * N / fs ≈ 2048 * 48 / 48800 ≈ 2.0 s` of audible ring at `N = 48`. Lower
  notes (larger `N`) ring proportionally longer. To shorten/lengthen sustain, lower/
  raise `DECAY_NUM` (toward / away from `2^(DECAY_SHIFT-1) = 2048`).

## Golden-vector test plan

- **Reference model:** `models/ks_ref.py` (pure Python stdlib, plain-int arithmetic).
  Functions: `to_signed16`, `lfsr_step`, class `KS` (`reset`, `pluck`, `tick`).
- **Scenario (the TB mirrors these EXACTLY):** reset, apply one `pluck` with
  `period = PGOLDEN = 48`, then run `NSAMP = 256` sustain steps, capturing `sample`
  (= the value read this tick, `out`) on each step. Constants:
  `DECAY_NUM=2047`, `DECAY_SHIFT=12`, `LFSR_SEED=0xACE1`, `LFSR_POLY=0xB400`,
  `NMAX=1024`.
- **Output format:** `models/ks_golden.hex`, one line per sample, **4-digit lowercase
  hex** of the 16-bit two's-complement value (e.g. `-1 -> ffff`, `-7568 -> e270`),
  no header -- parses cleanly with Verilog `$readmemh`.
- **First 8 golden samples (decimal):** `-7568, 28984, 14492, 7246, 3623, -19693,
  -4727, -15676`. **Last 4:** `1615, 2948, 3421, 2893`. **min = -30857, max = 32216**
  (oscillates around zero and decays -- eyeball sanity check).
- **Pass criterion:** the RTL testbench drives the identical scenario, captures
  `sample` each `sample_tick`, and compares against `models/ks_golden.hex` with
  **0 mismatches**. Any single differing word is a hard failure.
- **Regenerate:** `python3 models/ks_ref.py` (no args) deterministically rebuilds the
  golden file and prints the scenario params plus the first-8 / last-4 / min / max
  values for a human sanity check.

## AREA caveat

A `NMAX = 1024`-deep × 16-bit delay line is **16 Kbit of state** -- large. For v0 it is
an **inferred reg-array RAM** (a `reg [15:0] line [0:NMAX-1]`) which is fine for
simulation and for proving the contract, but it is **not** how this should reach real
silicon: synthesizing 1024×16 flops is area-hungry and timing-unfriendly. Production
options: (1) instantiate a proper **SRAM macro** (the GF180MCU
`gf180mcu_..._sram512x8...` parts the template removed -- see NOTES "Integrating into
the template" step 4 and "SRAM macros were removed"), reading `out`/`prev` and writing
`new` within the audio frame; or (2) pick a **smaller `NMAX`** sufficient for the
lowest desired note. The contract (ports, algorithm, golden vector) is independent of
which memory backs `line`, so swapping in an SRAM macro later does not change behavior.
