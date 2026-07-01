#!/usr/bin/env python3
"""
signoff_report.py -- an honest, all-in-one "did my chip actually pass?" scorecard.

Why this exists
---------------
After a harden, it is easy to look at the manufacturability report (Antenna / LVS /
DRC -> "Passed!") and conclude you are done. You are NOT. Those checks only ask
"can this be fabricated?" They say nothing about "will it run at the target speed,
in the worst-case operating conditions?" -- that lives in the TIMING numbers, in a
different file, and a failure there shows up as a number you have to know to look
for, not a red word. This script puts BOTH halves on one screen so the gap can't
hide.

Usage
-----
    python3 scripts/signoff_report.py <run-dir-or-metrics.json>
    python3 scripts/signoff_report.py final_roster_v7
    python3 scripts/signoff_report.py librelane/runs/RUN_2026-06-28_19-10-15

Exit code is non-zero if anything fails -- so you (or CI) can't accidentally ignore it.
"""
import json
import os
import sys

# Colors only when writing to a real terminal (clean in logs / CI / pipes).
_C = sys.stdout.isatty()
GREEN, RED, YEL, DIM, OFF = (("\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m")
                            if _C else ("", "", "", "", ""))
OK, BAD, WARN = f"{GREEN}PASS{OFF}", f"{RED}FAIL{OFF}", f"{YEL}WARN{OFF}"


def find_metrics(arg):
    """Accept a metrics.json, a run dir, or a deliverable dir; return the json path."""
    if os.path.isfile(arg):
        return arg
    for cand in (os.path.join(arg, "metrics.json"),
                 os.path.join(arg, "final", "metrics.json")):
        if os.path.isfile(cand):
            return cand
    sys.exit(f"no metrics.json found at/under: {arg}")


def worst_corner(m, prefix):
    """Return (worst_value, corner_name) over every '<prefix>__corner:<name>' key.
    'worst' = most negative (for slack) / largest (for counts)."""
    hits = {k.split("corner:")[-1]: v for k, v in m.items()
            if k.startswith(prefix + "__corner:") and isinstance(v, (int, float))}
    if not hits:
        return (m.get(prefix), None)
    # slack metrics: worst = min; count metrics: worst = max
    pick = min if "__ws" in prefix or "__tns" in prefix else max
    name = pick(hits, key=hits.get)
    return (hits[name], name)


def first(m, *keys, default=0):
    for k in keys:
        if k in m:
            return m[k]
    return default


def line(verdict, label, detail):
    print(f"  [{verdict}] {label:<16} {detail}")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = find_metrics(sys.argv[1])
    m = json.load(open(path))
    fails = 0

    print("=" * 64)
    print(f" SIGNOFF SCORECARD  {DIM}{path}{OFF}")
    print("=" * 64)

    # ---- PHYSICAL: can it be fabricated? (the part people DO look at) ----------
    print(f"\n{DIM}PHYSICAL -- can it be fabricated?{OFF}")
    drc = first(m, "magic__drc_error__count", "route__drc_errors", default=0)
    klay = first(m, "klayout__drc_error__count", "design__klayout_drc_error__count", default=0)
    lvs = first(m, "design__lvs_error__count", "lvs__total__errors", default=0)
    ant = first(m, "antenna__violating__nets", "route__antenna_violations", default=0)
    for label, n in [("DRC (magic)", drc), ("DRC (klayout)", klay),
                     ("LVS", lvs), ("Antenna", ant)]:
        ok = (n == 0)
        fails += not ok
        line(OK if ok else BAD, label, f"{n} error(s)/violation(s)")

    # ---- TIMING: will it run at speed, worst-case? (the part people MISS) ------
    print(f"\n{DIM}TIMING -- will it run at the target clock, worst-case corner?{OFF}")

    hold, hcorner = worst_corner(m, "timing__hold__ws")
    ok = hold is None or hold >= 0
    fails += not ok
    line(OK if ok else BAD, "Hold", f"WNS {hold:+.3f} ns" + (f"  @ {hcorner}" if hcorner else "")
         if hold is not None else "n/a")

    setup, scorner = worst_corner(m, "timing__setup__ws")
    tns, _ = worst_corner(m, "timing__setup__tns")
    ok = setup is None or setup >= 0
    fails += not ok
    detail = (f"WNS {setup:+.3f} ns  @ {scorner}" if setup is not None else "n/a")
    if tns:
        detail += f"   (TNS {tns:,.0f} ns)"
    line(OK if ok else BAD, "Setup", detail)

    slew, slcorner = worst_corner(m, "design__max_slew_violation__count")
    cap, cpcorner = worst_corner(m, "design__max_cap_violation__count")
    fano = first(m, "design__max_fanout_violation__count", default=0)
    for label, n, corner in [("Max slew", slew, slcorner), ("Max cap", cap, cpcorner)]:
        n = n or 0
        ok = (n == 0)
        fails += not ok
        line(OK if ok else BAD, label, f"{n} violation(s)" + (f"  @ {corner}" if corner else ""))
    # fanout violations are a yellow flag, not a hard fail on their own
    line(OK if fano == 0 else WARN, "Max fanout", f"{fano} net(s) over limit")

    # ---- VERDICT: the lesson, spelled out -------------------------------------
    manufacturable = (drc == 0 and klay == 0 and lvs == 0 and ant == 0)
    timing_closed = ((setup is None or setup >= 0) and (hold is None or hold >= 0)
                     and (slew or 0) == 0 and (cap or 0) == 0)
    print("\n" + "-" * 64)
    print(" VERDICT")
    print(f"   Manufacturable : {GREEN+'YES'+OFF if manufacturable else RED+'NO'+OFF}"
          "   (DRC / LVS / antenna)")
    print(f"   Timing-closed  : {GREEN+'YES'+OFF if timing_closed else RED+'NO'+OFF}"
          "   (setup / hold / slew / cap)")
    if manufacturable and not timing_closed:
        print(f"\n   {YEL}Fabricable, but not timing-closed.{OFF} The manufacturability")
        print("   report only checks geometry, so it says 'Passed' -- but the worst-case")
        print("   corner (ss = hot + low voltage) does not meet timing. Not a clean signoff.")
    print("=" * 64)

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
