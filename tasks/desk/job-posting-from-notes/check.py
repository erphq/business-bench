"""The posting gives the new shift hours on one line and not the kickoff notes' 8:00-4:30 day.

Checked per line rather than per sentence, because "10:00 a.m. to 6:30 p.m." would otherwise split at "a.m.". A time on
the hour is accepted as 10, 10:00, 10 a.m. or 10am; a half hour needs its minutes. Expected times come from
reference/notes.json.
"""
import glob
import json
import os
import re


def _time_rx(t):
    h, mnt = t.split(":")
    if mnt == "00":
        return re.compile(rf"(?<![\d:$.]){h}(:00)?(?![\d:])", re.I)
    return re.compile(rf"(?<![\d:$.]){h}[:.]{mnt}(?!\d)", re.I)


def check(ws, ref):
    name = "schedule hours"
    hits = sorted(glob.glob(os.path.join(ws, "posting.md"))) or sorted(
        h for h in glob.glob(os.path.join(ws, "**", "posting.md"), recursive=True) if "/.proto" not in h and "/.codex" not in h)
    if not hits:
        return [{"name": name, "passed": False, "detail": "posting.md not found"}]
    try:
        notes = json.load(open(os.path.join(ref, "notes.json")))
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"reference unreadable: {e}"}]
    text = open(hits[0], encoding="utf-8", errors="replace").read()
    start, end = _time_rx(notes["start_h"]), _time_rx(notes["end_h"])
    lines = text.splitlines()
    good = [ln for ln in lines if start.search(ln) and end.search(ln)]
    old = [ln for ln in lines if re.search(r"(?<![\d:])4[:.]30(?!\d)", ln)]
    ok = bool(good) and not old
    if ok:
        detail = f"line: {good[0].strip()[:120]!r}"
    elif old:
        detail = f"old 4:30 hours still present: {old[0].strip()[:120]!r}"
    else:
        detail = f"no line gives both {notes['start_h']} and {notes['end_h']}"
    return [{"name": name, "passed": ok, "detail": detail}]
