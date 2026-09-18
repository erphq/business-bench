"""Missing punches are flagged, with no hours, on exactly the right (badge, date) and with the right direction.

A flag counts when the flag cell is non-empty and not a plain 'ok'. The direction is read from the words:
'out' (missing out, no clock-out) or 'in' (missing in, no clock-in); a flag naming both fails. Hours on a
flagged day must be empty or 0 - a day filled in from the schedule is exactly what the note forbids.
"""
import importlib.util
import os
import re

_spec = importlib.util.spec_from_file_location("clock_punch_check", os.path.join(os.path.dirname(os.path.abspath(__file__)), "check.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

OUT_RE = re.compile(r"\bout\b|clock.?out|out.?punch|punch.?out", re.I)
IN_RE = re.compile(r"\bin\b|clock.?in|in.?punch|punch.?in", re.I)


def check(ws, ref):
    name = "missing punches flagged"
    ref_rows, out, err = _base.keyed(ws, ref)
    if err:
        return [{"name": name, "passed": False, "detail": err}]
    want = {k: ("out" if "OUT" in v["flag"].upper() else "in") for k, v in ref_rows.items() if v["flag"]}
    got = {k: v for k, v in out.items() if v["flag"] and v["flag"].strip().lower() not in ("ok", "none", "-", "n/a", "no")}
    bad = []
    for k, direction in sorted(want.items()):
        g = got.get(k)
        if g is None:
            row = out.get(k)
            bad.append(f"{k[0]} {k[1]}: not flagged" + (f" (hours {row['hours']})" if row else " (row missing)"))
            continue
        o, i = bool(OUT_RE.search(g["flag"])), bool(IN_RE.search(g["flag"]))
        if (direction == "out" and not (o and not i)) or (direction == "in" and not (i and not o)):
            bad.append(f"{k[0]} {k[1]}: flag {g['flag']!r} should say missing {direction}")
        if g["hours"] not in (None, 0.0):
            bad.append(f"{k[0]} {k[1]}: flagged day carries {g['hours']} hours")
    extra = sorted(k for k in got if k not in want)
    if extra:
        bad.append(f"flagged but fine: {extra[:6]}")
    return [{"name": name, "passed": not bad, "detail": "; ".join(bad[:8]) if bad else f"{len(want)} flagged days match"}]
