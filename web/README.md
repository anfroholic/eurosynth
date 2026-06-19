# `web/` — the chip's voices in a browser (PyScript)

[`index.html`](index.html) is a **self-contained** playground that runs all five of
the chip's sound engines live in the browser. It uses
[PyScript / Pyodide](https://pyscript.net) to execute the project's **bit-exact
integer reference models** (`models/*_ref.py`) — the same Python the silicon is
verified against — directly in WebAssembly. Nothing is pre-recorded: every clip is
synthesized sample-by-sample at the chip's true **12 kHz** rate when you press play,
then handed to the Web Audio API.

The five voices and their controls:

| Voice | Engine | Controls on the page |
|---|---|---|
| 3 | **SID** | note, per-voice waveform (saw/tri/pulse/noise), pulse width, ring-mod, hard-sync |
| 4 | **Karplus–Strong** | delay length `N` (pitch), ring time; single pluck or arpeggio |
| 5 | **Chaos** | map (logistic / CA / Lorenz), `r_seed`, CA rate, optional `r_seed` sweep |
| 6 | **Bytebeat** | formula 0–3, speed `t_inc`, length |
| 7 | **Neural** | pitch bus, morph (sweep or static), length — *the morphing bass* |

Each panel has **▶ Play** and **⬇ WAV** (downloads the exact clip as a 12 kHz mono
WAV).

## Run it

It's one static file with no build step. Any static server works:

```bash
# from the repo root
python -m http.server 8000
# then open http://localhost:8000/web/
```

It also runs unchanged on **GitHub Pages** (serve the repo; the page is at `/web/`).
First load pulls the Pyodide runtime from a CDN (a few seconds); after that the
voices are instant except the neural one, which renders a full neural-net forward
pass per sample (~2–3 s for a 3 s clip).

## Faithfulness

The engine code inside `index.html` is ported verbatim from the golden models and
is checked to be **bit-identical** to them (KS, Bytebeat, Chaos, SID, Neural all
match their `*_golden.hex` scenarios). The canonical source of truth remains
`models/*_ref.py`; if you change an engine there, re-sync the copy here.
