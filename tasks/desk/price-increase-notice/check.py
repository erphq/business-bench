"""The mailing note names every annual-contract customer with its renewal date, and does not leave off the customer
that converted to month-to-month.

A customer is recognised by the first word of its business name. An annual customer passes when one line or sentence
names it together with its renewal date (October 31, Oct 31, 10/31, 2026-10-31 or 31 October; the year is optional).
The converted customer fails the check when any line or sentence names it without saying it is month-to-month, no
longer annual, or does receive the letter. Expected names come from reference/notes.json.
"""
import glob
import json
import os
import re

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
CLEAR = re.compile(r"(month[- ]to[- ]month|no longer (on )?an? annual|no longer annual|not (on )?an? annual|not (be )?(left off|excluded|exempt|grandfathered)|"
                   r"\bdoes get\b|\bdo get\b|should (get|receive)|will (get|receive)|\bgets the\b|\breceives the\b|ended|expired|converted|lapsed)", re.I)


def _date_re(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    mon = MONTHS[m - 1]
    return re.compile(rf"({mon}|{mon[:3]}\.?|{mon[:4]}\.?)\s+0?{d}(st|nd|rd|th)?\b|\b0?{d}(st|nd|rd|th)?\s+(of\s+)?({mon}|{mon[:3]})\b|"
                      rf"\b0?{m}/0?{d}(/(20)?{y % 100})?\b|\b{y}-{m:02d}-{d:02d}\b", re.I)


def _pieces(text):
    # a sentence break, but not after a month abbreviation ("Jan. 31") or a.m./p.m.
    return [p for p in re.split(r"(?<=[.!?])(?<!\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\.)(?<!Sept\.)(?<![ap]\.m\.)\s+|\n+", text) if p.strip()]


def check(ws, ref):
    name = "mailing note names the annual-contract customers"
    hits = sorted(glob.glob(os.path.join(ws, "notice.md"))) or sorted(
        h for h in glob.glob(os.path.join(ws, "**", "notice.md"), recursive=True) if "/.proto" not in h and "/.codex" not in h)
    if not hits:
        return [{"name": name, "passed": False, "detail": "notice.md not found"}]
    try:
        notes = json.load(open(os.path.join(ref, "notes.json")))
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"reference unreadable: {e}"}]
    text = open(hits[0], encoding="utf-8", errors="replace").read()
    pieces = _pieces(text)
    key = lambda n: re.escape(n.split()[0])
    out = []
    missing = []
    for c in notes["annual"]:
        rx, drx = re.compile(rf"\b{key(c['name'])}\b", re.I), _date_re(c["renewal"])
        if not any(rx.search(p) and drx.search(p) for p in pieces):
            missing.append(f"{c['name']} with renewal {c['renewal']}")
    out.append({"name": f"{name}: each with its renewal date", "passed": not missing,
                "detail": ("missing " + "; ".join(missing)) if missing else f"all {len(notes['annual'])} annual customers listed with renewal dates"})
    conv = notes["converted"]
    crx = re.compile(rf"\b{key(conv)}\b", re.I)
    wrong = [p for p in pieces if crx.search(p) and not CLEAR.search(p)]
    out.append({"name": f"{name}: {conv} is not left off", "passed": not wrong,
                "detail": f"named as if still annual: {wrong[0][:120]!r}" if wrong else f"{conv} not listed as an annual customer"})
    return out
