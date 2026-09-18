"""Custom grader for maintenance-notices: each building's notice carries that building's own dates, shutoff hours and
contact, and only buildings with work get one.

Notice files are found under a notices/ folder and matched to buildings by the building's name word in the file name
(notices/Birch_House.md, notices/birch.md). For each building in reference/facts.json:
  * work dates: every work day appears in a common written form, and a superseded date does not appear
  * shutoff hours: every day's water-off and water-back-on times appear (8:00 AM, 8 a.m., 08:00; noon for 12:00), and a
    superseded time from the original schedule does not appear
  * contact: the right phone number appears (any separators), and no other building's superintendent, the relief super
    meant for another building, or the contractor's crew lead number appears
  * no notice for a building without work
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


def _notice_files(ws):
    hits = [p for p in glob.glob(os.path.join(ws, "**", "*"), recursive=True)
            if os.path.isfile(p) and "/notices/" in p.replace(os.sep, "/") and "/.proto" not in p and "/.codex" not in p]
    return sorted(hits)


def check(ws, ref):
    f = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    files = _notice_files(ws)
    by = {}
    for p in files:
        stem = re.sub(r"[^a-z0-9]", "", os.path.basename(p).lower())
        for b in f["buildings"]:
            if b["key"] in stem:
                by.setdefault(b["key"], []).append(p)
    res = []
    for b in f["buildings"]:
        if not b["gets_notice"]:
            res.append(result(f"no notice for {b['name']}", b["key"] not in by, "none written" if b["key"] not in by else f"unexpected {by[b['key']]}"))
            continue
        name = f"{b['name']}: dates, hours and contact"
        if b["key"] not in by:
            res.append(result(name, False, "no notice file")); continue
        text = "\n".join(read(p) for p in by[b["key"]])
        bad = []
        for day in b["days"]:
            if not re.search(date_rx(day["date"]), text, re.I):
                bad.append(f"date {day['date']} missing")
            for k in ("start", "end"):
                if not re.search(time_rx(*day[k]), text, re.I):
                    bad.append(f"{day['date']} {k} {day[k][0]:02d}:{day[k][1]:02d} missing")
        for sd in b["stale_dates"]:
            if re.search(date_rx(sd), text, re.I):
                bad.append(f"superseded date {sd} present")
        for st in b["stale_times"]:
            if re.search(time_rx(*st), text, re.I):
                bad.append(f"superseded time {st[0]:02d}:{st[1]:02d} present")
        if not re.search(phone_rx(b["contact_phone"]), text):
            bad.append(f"contact phone {b['contact_phone']} missing")
        for wp in b["wrong_phones"]:
            if re.search(phone_rx(wp), text):
                bad.append(f"wrong phone {wp} present")
        res.append(result(name, not bad, "; ".join(bad) or "all facts present"))
    return res
