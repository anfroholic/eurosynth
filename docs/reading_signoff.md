# Did my chip actually pass? (reading signoff like a pro)

> Newcomer-focused. This is the doc I wish I'd had: I hardened a design, saw
> **Antenna / LVS / DRC -> Passed ✅**, and thought I was done. I wasn't. The chip
> was failing timing by ~25 ns and I had no idea, because nothing red ever appeared.

## A chip has to pass TWO different questions

| Question | What it checks | Where the answer lives |
|---|---|---|
| **1. Can it be fabricated?** | geometry & wiring rules: DRC, LVS, antenna | the *manufacturability* report |
| **2. Will it run at the target clock — in the worst case?** | **timing**: setup, hold, slew, cap | `metrics.json` (numbers, not a "Passed") |

The trap: the manufacturability report only answers **question 1**. It is happy to
print "Passed ✅" for a layout that is fabricable but **cannot run at speed**. Nothing
in that report mentions timing. If you stop there, you ship a chip that's a beautiful,
manufacturable brick.

## The one command that answers both

```bash
python3 scripts/signoff_report.py <run-dir>      # e.g. final_roster_v7
```

It reads `metrics.json` and prints **both halves on one screen**, then exits non-zero
if anything fails:

```
PHYSICAL -- can it be fabricated?
  [PASS] DRC (magic)      0 ...
  [PASS] LVS              0 ...
  [PASS] Antenna          0 ...
TIMING -- will it run at the target clock, worst-case corner?
  [PASS] Hold             WNS +0.068 ns
  [FAIL] Setup            WNS -24.945 ns  @ max_ss_125C_4v50   (TNS -99,075 ns)
  [FAIL] Max slew         9458 violation(s)  @ max_ss_125C_4v50
 VERDICT
   Manufacturable : YES
   Timing-closed  : NO
```

That `[FAIL] Setup -24.945 ns` is the thing the manufacturability report will never
show you.

## How to read the timing numbers

- **WNS (Worst Negative Slack)** — the single worst path's margin. **Positive = good**
  (met timing with room to spare). **Negative = failed** by that many nanoseconds.
- **TNS (Total Negative Slack)** — all failing paths added up. A small negative TNS =
  a few slow paths (fixable). A *huge* negative TNS (tens of thousands of ns) = the
  whole design is failing — a structural problem, not one stubborn path.
- **Max slew / max cap** — signal edges too slow / wires too heavy. These are design-
  *rule* violations: they must be 0 regardless of clock speed (slowing the clock does
  **not** fix them).

## Corners: why "it works on my bench" isn't "it passed"

The same chip is analyzed under several **PVT corners** (Process, Voltage,
Temperature):

- **ff** — fast silicon, cold, high voltage → everything is *fast* → easy to pass.
- **tt** — typical → roughly room-temperature bench conditions.
- **ss** — slow silicon, **hot (125 °C), low voltage (4.5 V)** → everything is *slow*
  → the hardest to pass, and the one a real product must survive.

A design can pass `tt`/`ff` with margin (so it runs fine on your bench) and still
fail `ss` badly. **Signoff means passing the worst corner (`ss`), not the easy one.**
That's why my "working" chip wasn't actually closed: it would likely run at room
temperature but isn't guaranteed when hot and undervolted.

## Make it impossible to miss

Don't rely on remembering to look. Wire the scorecard into the flow so it runs
**automatically at the end of every harden** and fails loudly:

```bash
# at the end of your harden script, after the run finishes:
python3 scripts/signoff_report.py "$(ls -dt librelane/runs/RUN_* | head -1)" || \
  echo ">>> SIGNOFF NOT CLEAN -- read the scorecard above before trusting this run."
```

Now a green "Passed ✅" on manufacturability can never be mistaken for a finished chip:
you always see the timing verdict right after, and the non-zero exit code makes CI (or
a Makefile target) stop on it.
