"""Custom grader for faq-from-tickets: the FAQ asks the five most-asked questions, most-asked first, and no others.

Question lines are markdown headings, bold-led lines, Q-prefixed or numbered lines containing a question mark,
and any line that ends with a question mark; only the text up to the first question mark is read. Each is
assigned to at most one topic by keyword (priority order below, so "refund if I cancel" is a cancellation and
"shipping to Canada" is Canada). Topics come from reference/topics.json: the five counted once per customer.
"""
from __future__ import annotations

import glob
import json
import os
import re

TOPICS = [
    ("pause", r"\bpaus|on hold|\bhold (my|the|deliveries|shipments|subscription)|vacation|going away|\bbreak from"),
    ("deadline", r"cut-?off|deadline|too late|how late|last day|in time|by when|when (do|must|should|can) i (need to )?(make|change|edit|update|swap)|\b(change|changes|edit|update|modify|swap|skip)\b.{0,25}\b(next|upcoming)\b|\bswap"),
    ("cancel", r"\bcancel|stop my subscription|end my subscription"),
    ("damaged", r"damag|stale|broken|\btorn\b|ripped|burst|leak|spoil|wrong (coffee|bag|order)|replace|refund|(problem|issue|something wrong) with (my |an |the )?(order|bag|coffee|delivery)|arrived (open|opened|crushed|wet)"),
    ("canada", r"canada|international|outside the (us|u\.s\.?|united states)|overseas|abroad|\bduty\b|\bduties\b"),
    ("freeship", r"free shipping|\bship(s|ping)? (for )?free|shipping (cost|costs|fee|fees|charge|charges|threshold|minimum)|charged (for )?shipping|pay (for )?shipping|how much (is|does) shipping|cost to ship|delivery (fee|charge)"),
    ("grind", r"\bgrind|whole bean|ground coffee"),
    ("gift", r"\bgift"),
    ("decaf", r"decaf"),
]


def _find(ws: str, name: str):
    hits = sorted(glob.glob(os.path.join(ws, name)))
    if not hits:
        hits = sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _questions(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        heading = s.startswith("#")
        bold = s.startswith("**") or s.startswith("__")
        prefixed = bool(re.match(r"^([-*+]\s*)?(\*\*)?(q\d*\s*[:.)]|\d+[.)]\s)", s, re.I)) and "?" in s
        ends_q = s.rstrip("*_ ").endswith("?")
        if not (heading or bold or prefixed or ends_q):
            continue
        out.append(s[: s.index("?") + 1] if "?" in s else s)
    return out


def _topic(q: str):
    low = q.lower()
    for name, pat in TOPICS:
        if re.search(pat, low):
            return name
    return None


def check(ws: str, ref: str) -> list[dict]:
    p = _find(ws, "faq.md")
    if not p:
        return [{"name": "top five questions present", "passed": False, "detail": "no faq.md in workspace"}]
    text = open(p, encoding="utf-8", errors="replace").read()
    truth = json.load(open(os.path.join(ref, "topics.json"), encoding="utf-8"))
    top5 = truth["top5_in_order"]
    seq = []
    for q in _questions(text):
        t = _topic(q)
        if t and t not in seq:
            seq.append(t)
    missing = [t for t in top5 if t not in seq]
    extra = [t for t in seq if t not in top5]
    order = [t for t in seq if t in top5]
    return [
        {"name": "top five questions present", "passed": not missing, "detail": f"question topics in order: {seq}; missing {missing}"},
        {"name": "no question outside the top five", "passed": not extra, "detail": f"extra topics {extra}" if extra else "none"},
        {"name": "most-asked first", "passed": not missing and order == top5, "detail": f"order {order}, expected {top5}"},
    ]
