"""Custom grader for event-announcement: the announcement carries the moved dates and the seated capacity.

  * event date: the new dinner date appears (it differs from the RSVP deadline, so any mention counts)
  * RSVP deadline: the new deadline sits in a line or sentence that mentions RSVP, replying, booking or reserving
  * superseded dates absent: neither the sheet's original dinner date nor its original RSVP date, nor last spring's
    dates, appear anywhere
  * standing count not given as capacity: no line or sentence gives the 120 standing reception number as guests, seats
    or capacity
Dates match the common written forms (October 24, Oct. 24, 24 October 2026, 10/24/2026, 2026-10-24). Values come from
reference/facts.json.
"""
from __future__ import annotations

import glob
import json
import os
import re

# ---------------------------------------------------------------- shared text helpers (dates, times, units)

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
# Abbreviations whose full stop is not a sentence end ("8 a.m. to 3 p.m.", "Oct. 14", "410 Harlan St. Apt 2").
_ABBR = re.compile(r"\b(a\.m|p\.m|e\.g|i\.e|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
                   r"st|ave|rd|dr|ln|blvd|ste|no|mr|mrs|ms|inc|co|approx|vs|ext|tel|ph|dept|pkwy|hwy|jr|sr|sec|sect|para|u\.s)\.", re.I)
NEG = re.compile(r"(\bnot\b|n't\b|\bno\b|\bnever\b|\bunable\b|\bcannot\b|\bwithout\b|\bnon-?refundable\b|\binstead of\b|\brather than\b|\bno longer\b)", re.I)


def find(ws: str, pattern: str):
    hits = sorted(glob.glob(os.path.join(ws, pattern)))
    if not hits:
        hits = sorted(glob.glob(os.path.join(ws, "**", pattern), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _protect(text: str) -> str:
    return _ABBR.sub(lambda m: m.group(0).replace(".", "․"), text)


def sentences(text: str) -> list[str]:
    t = _protect(text)
    out = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if s.strip()]
    return [s.replace("․", ".") for s in out]


def units(text: str) -> list[str]:
    """Lines (table rows, list items), paragraphs, sentences and semicolon clauses: the places a fact can sit together."""
    out = [l for l in text.splitlines() if l.strip()]
    out += [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    for s in sentences(text):
        out.append(s)
        out += [c for c in s.split(";") if c.strip()]
    return out


def date_rx(iso: str) -> str:
    """One calendar date in the common written forms: 14 October 2026, October 14, 2026, Oct. 14, 10/14/2026, 10/14, 2026-10-14.
    A year written next to the date must be the right one ("March 15, 2024" is not March 15, 2027)."""
    y, m, d = (int(x) for x in iso.split("-"))
    mon = MONTHS[m - 1]
    names = rf"{mon}|{mon[:3]}\.?" + (r"|sept\.?" if m == 9 else "")
    other_year = rf"(?!,?\s+(?!{y}\b)\d{{4}}\b)"
    mm = rf"0?{m}" if m < 10 else rf"{m}"
    return (rf"(?:\b(?:{names})\s+0?{d}(?:st|nd|rd|th)?\b(?![:/]\d){other_year}"
            rf"|\b0?{d}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{names})(?![a-z]){other_year}"
            rf"|(?<![\d/.$]){mm}/0?{d}(?:/(?:{y}|{y % 100:02d}))?(?![\d/])"
            rf"|\b{y}-{m:02d}-{d:02d}\b)")


def time_rx(h: int, mi: int) -> str:
    """A clock time: 3:00 PM, 3 p.m., 3pm, 15:00; a bare 8:00 counts only for morning times."""
    h12 = h % 12 or 12
    ap = "a" if h < 12 else "p"
    pats = [rf"(?<![\d:]){h12}[:.]{mi:02d}\s*{ap}\.?\s*m\b\.?", rf"(?<![\d:$]){h:02d}:{mi:02d}(?!\d)(?!\s*[ap]\.?\s*m\b)"]
    if mi == 0:
        pats.append(rf"(?<![\d:.$]){h12}\s*{ap}\.?\s*m\b\.?")
    if h < 10:
        pats.append(rf"(?<![\d:$]){h}:{mi:02d}(?!\d)(?!\s*[ap]\.?\s*m\b)")
    if h == 12 and mi == 0:
        pats.append(r"\bnoon\b|\bmidday\b")
    return "(?:" + "|".join(pats) + ")"


def phone_rx(digits10: str) -> str:
    a, b, c = digits10[:3], digits10[3:6], digits10[6:]
    return rf"(?<!\d)(?:\+?1[\s.-]?)?\(?{a}\)?[\s.-]*{b}[\s.-]*{c}(?!\d)"


NUM = re.compile(r"\(?-?[$€£]?\s?\d[\d,]*(?:\.\d+)?\)?")


def numbers(text: str) -> list[float]:
    out = []
    for m in NUM.finditer(text):
        try:
            out.append(float(re.sub(r"[^0-9.]", "", m.group(0)).strip(".") or "x"))
        except ValueError:
            pass
    return out


def has_num(text: str, want: float, tol: float = 0.005) -> bool:
    return any(abs(v - want) <= tol for v in numbers(text))


def result(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(ok), "detail": detail}
# ---------------------------------------------------------------- end shared helpers


RSVP = re.compile(r"rsvp|r\.s\.v\.p|\breply\b|\brespond|\bregister|\bregistration|\breserv|\bbook|\bsign up|\blet us know|\bdeadline", re.I)
CAP = re.compile(r"guest|seat|people|person|attendee|capacity|limited|spot|place", re.I)


def check(ws, ref):
    names = ["event date", "RSVP deadline", "superseded dates absent", "standing count not given as capacity"]
    p = find(ws, "announcement.md")
    if not p:
        return [result(n, False, "no announcement.md in workspace") for n in names]
    f = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    text = read(p)
    us = units(text)
    new = re.compile(date_rx(f["event_date"]), re.I)
    rsvp = re.compile(date_rx(f["rsvp"]), re.I)
    ev_ok = bool(new.search(text))
    rs_ok = any(rsvp.search(u) and RSVP.search(u) for u in us)
    stale = [k for k in ("old_date", "old_rsvp", "spring_date", "spring_rsvp") if re.search(date_rx(f[k]), text, re.I)]
    std = re.compile(rf"(?<![\d$.]){f['standing']}(?![\d.])")
    cap_bad = [u[:100] for u in sentences(text) + [l for l in text.splitlines() if l.strip()] if std.search(u) and CAP.search(u)]
    return [
        result(names[0], ev_ok, f"{f['event_date']} stated" if ev_ok else f"no line or sentence gives the dinner date {f['event_date']}"),
        result(names[1], rs_ok, f"RSVP by {f['rsvp']} stated" if rs_ok else f"no RSVP line or sentence carries {f['rsvp']}"),
        result(names[2], not stale, "no superseded date" if not stale else "superseded dates present: " + ", ".join(f"{k} {f[k]}" for k in stale)),
        result(names[3], not cap_bad, "standing count not used" if not cap_bad else "; ".join(cap_bad[:2])),
    ]
