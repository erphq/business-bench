"""Custom grader for contract-renewal-summary: the term end and notice deadline come from the signed documents, and the
vendor's email figures appear only as corrections.

  * term end: a line or sentence about the term, its end, expiry or renewal carries the end of the initial term
    (March 31, 2027; April 1, 2027 is accepted as the day the renewal would start)
  * notice deadline: a line or sentence about notice, non-renewal or cancelling carries the last day to give notice
    (December 1, 2026, or November 30 for a memo that counts conservatively)
  * notice period: the 120-day period appears with the word days
  * vendor's figures only as corrections: any sentence or line that carries the account manager's renewal date, notice
    date or annual value, or the value with the unsigned draft, must also say it is wrong, outdated or not what was signed
Values come from reference/facts.json.
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


TERMW = re.compile(r"\bterm\b|\bend|expir|renew|runs? (through|until|to)|last day of", re.I)
NOTICEW = re.compile(r"notice|notif|non-?renew|cancel|terminat|opt out|deadline|let (them|brightline) know|tell brightline|in writing", re.I)
CORRECT = re.compile(r"wrong|incorrect|outdated|out of date|out-of-date|stale|mistak|error|not (correct|right|accurate|what|binding|signed|executed|reflect)|"
                     r"n't (correct|right|accurate|reflect|match|binding|signed)|ignor|original|before (the|both|either|any) amendment|old|superseded|draft|unsigned|"
                     r"not signed|pre-amendment|misstat|disregard|inaccurate|does not account|doesn't account|overlook|miss(es|ed|ing)|claims?|says?|quot(es|ed)|states?", re.I)


def _money_rx(v):
    return re.compile(rf"(?<![\d.]){v // 1000},?{v % 1000:03d}(?:\.00)?(?![\d])")


def check(ws, ref):
    names = ["term end date", "notice deadline", "notice period in days", "vendor's figures only as corrections"]
    p = find(ws, "renewal_summary.md")
    if not p:
        return [result(n, False, "no renewal_summary.md in workspace") for n in names]
    f = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    text = read(p)
    us = units(text)
    end_rx = re.compile("|".join(date_rx(x) for x in f["term_end"]), re.I)
    notice_rx = re.compile("|".join(date_rx(x) for x in f["notice_by"]), re.I)
    end_ok = any(end_rx.search(u) and TERMW.search(u) for u in us)
    notice_ok = any(notice_rx.search(u) and NOTICEW.search(u) for u in us)
    days_ok = bool(re.search(rf"(?<![\d.]){f['notice_days']}[\s-]*(calendar[\s-]*)?days?\b|one hundred (and )?twenty[\s-]*days", text, re.I))
    vendor = [re.compile(date_rx(f["am_renew"]), re.I), re.compile(date_rx(f["am_notice"]), re.I), _money_rx(f["am_annual"]), _money_rx(f["naive"]["with_draft"])]
    pool = sentences(text) + [l for l in text.splitlines() if l.strip()]
    bad = [s[:120] for s in pool if any(v.search(s) for v in vendor) and not CORRECT.search(s)]
    return [
        result(names[0], end_ok, "term end stated" if end_ok else f"no term line or sentence carries {f['term_end'][0]}"),
        result(names[1], notice_ok, "notice deadline stated" if notice_ok else f"no notice line or sentence carries {f['notice_by'][0]}"),
        result(names[2], days_ok, f"{f['notice_days']} days stated" if days_ok else f"the {f['notice_days']}-day notice period is not stated"),
        result(names[3], not bad, "; ".join(bad[:2]) or "vendor figures not repeated as fact"),
    ]
