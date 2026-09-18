"""Custom grader for supplier-dispute-letter: every disputed invoice line is identified with its own amount.

For each disputed line in reference/facts.json, some unit of the letter must identify the line (its invoice line
number, its item code, or words from its description) and state its disputed amount. A unit is a table row, a
list item with its continuation lines, a sentence, or a clause split on semicolons. A row or list item that
identifies more than one disputed line only counts at sentence or clause level, so amounts cannot be borrowed.
"""
from __future__ import annotations

import glob
import json
import os
import re

NUM = re.compile(r"\(?-?[$€£]?\s?\d[\d,]*(?:\.\d+)?\)?")


def _find(ws: str, name: str):
    hits = sorted(glob.glob(os.path.join(ws, name)))
    if not hits:
        hits = sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _nums(s: str) -> list[float]:
    out = []
    for m in NUM.finditer(s):
        try:
            out.append(float(re.sub(r"[^0-9.\-]", "", m.group(0))))
        except ValueError:
            pass
    return out


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


def _ref_pattern(x: dict) -> str:
    n = x["line"]
    parts = [rf"\bline\s*(?:no\.?|#|number|item)?\s*{n}\b", rf"(?:^|\|)\s*#?\s*{n}\s*(?:\||$)", rf"#\s*{n}\b", x["kw"]]
    if x["sku"] != "FUEL":
        parts.append(re.escape(x["sku"]))
    return "(" + "|".join(parts) + ")"


def check(ws: str, ref: str) -> list[dict]:
    p = _find(ws, "dispute.md")
    if not p:
        return [{"name": "disputed lines with amounts", "passed": False, "detail": "no dispute.md in workspace"}]
    text = open(p, encoding="utf-8", errors="replace").read()
    facts = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    disputed = facts["disputed"]
    units = []
    for item in _items(text):
        units.append((item, False))
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", item):
            units.append((sent, True))
            for clause in sent.split(";"):
                units.append((clause, True))
    out = []
    for x in disputed:
        pat = _ref_pattern(x)
        others = [_ref_pattern(o) for o in disputed if o is not x]
        ok = False
        for unit, fine in units:
            if not re.search(pat, unit, re.I):
                continue
            if not fine and any(re.search(o, unit, re.I) for o in others):
                continue
            if any(abs(v - x["amount"]) <= 0.005 for v in _nums(unit)):
                ok = True
                break
        out.append({"name": f"line {x['line']} ({x['sku']}) disputed for {x['amount']:.2f}", "passed": ok,
                    "detail": "identified with its amount" if ok else "no row, item or sentence identifies this line with its disputed amount"})
    return out
