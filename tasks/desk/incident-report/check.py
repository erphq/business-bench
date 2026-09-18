"""Custom grader for incident-report: every corrective action carries its final owner and due date.

The safety manager's thread changes two actions after the notes were written (a later due date for the guard,
a new owner for the refresher). For each action in reference/facts.json, some unit of the report must name
the action, the owner's surname and the due date in any common date spelling. A unit is a table row, a list
item with its continuation lines, a paragraph, a sentence, or a clause split on semicolons; a list item or
paragraph that names more than one action only counts at sentence or clause level, so one owner cannot be
borrowed from a neighbouring action.
"""
from __future__ import annotations

import glob
import json
import os
import re


def _find(ws: str, name: str):
    hits = sorted(glob.glob(os.path.join(ws, name)))
    if not hits:
        hits = sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _items(text: str) -> list[str]:
    items, cur = [], []
    for line in text.splitlines():
        s = line.strip()
        starts = (not s) or s.startswith(("|", "#", "-", "*", "+")) or re.match(r"^\d+[.)]\s", s)
        if starts and cur:
            items.append(" ".join(cur)); cur = []
        if s:
            cur.append(s)
    if cur:
        items.append(" ".join(cur))
    return items


def _units(text: str) -> list[tuple[str, bool]]:
    """(unit, fine) pairs; fine units are sentences or clauses, coarse units are items and paragraphs."""
    out = []
    for block in [b for b in re.split(r"\n\s*\n", text) if b.strip()] + _items(text):
        out.append((re.sub(r"\s+", " ", block), False))
    for item in _items(text):
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", item):
            out.append((sent, True))
            for clause in sent.split(";"):
                out.append((clause, True))
    return out


def check(ws: str, ref: str) -> list[dict]:
    name = "corrective actions with owners and due dates"
    p = _find(ws, "incident_report.md")
    if not p:
        return [{"name": name, "passed": False, "detail": "no incident_report.md in workspace"}]
    text = open(p, encoding="utf-8", errors="replace").read()
    facts = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    actions = facts["actions"]
    units = _units(text)
    results = []
    for a in actions:
        others = [b["keyword"] for b in actions if b is not a]
        ok = False
        for unit, fine in units:
            if not re.search(a["keyword"], unit, re.I):
                continue
            if not fine and any(re.search(o, unit, re.I) for o in others):
                continue
            if re.search(rf"\b{re.escape(a['owner'])}\b", unit, re.I) and re.search(a["due_regex"], unit, re.I):
                ok = True
                break
        results.append({"name": f"{a['action']}: owner {a['owner']}, due {a['due']}", "passed": ok,
                        "detail": "found in one row, item or sentence" if ok else "no row, item or sentence names this action with that owner and due date"})
    return results
