"""Custom grader for rfq-email: every bought part is requested at the job quantity, the stock kit is left off, and the
two dates are the purchasing lead's.

  * line quantities: for each bought part in reference/facts.json, the line that names its part number (or the few
    lines after it, up to the next part number) carries the per-bench quantity times the job's bench count
  * stock kit left off: the fastener kit's part number or name appears only where the text says it is excluded or from stock
  * parts delivery date: a line or sentence about delivery, the dock or a need-by date carries the dock date
  * quote due date: a line or sentence about quotes, pricing or responses carries the quote due date
Part numbers match with hyphens, spaces or neither; dates match the common written forms.
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


DELIVER = re.compile(r"deliver|\bdock\b|on[- ]site|in hand|arriv|receiv|need(ed)? (by|on|no later)|no later than|required (by|on)|\bship|\bdue\b", re.I)
QUOTE = re.compile(r"quot|pric|respon|reply|submit|\bbid|proposal|return", re.I)
EXCLUDE = re.compile(r"stock|\bnot\b|n't\b|exclud|omit|left off|leave|separate|no need|without|except|\bno\b", re.I)


def _pn(no):
    return re.compile(r"(?<![A-Za-z0-9])" + r"[-\s]?".join(re.escape(p) for p in no.split("-")) + r"(?![A-Za-z0-9])", re.I)


def check(ws, ref):
    names = ["line quantities", "stock kit left off", "parts delivery date", "quote due date"]
    p = find(ws, "rfq.md")
    if not p:
        return [result(n, False, "no rfq.md in workspace") for n in names]
    f = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    text = read(p)
    lines = text.splitlines()
    pns = {l["no"]: _pn(l["no"]) for l in f["lines"]}
    all_pns = list(pns.values()) + [_pn(f["stock_part"])]
    bad = []
    for l in f["lines"]:
        rx = pns[l["no"]]
        idxs = [i for i, ln in enumerate(lines) if rx.search(ln)]
        if not idxs:
            bad.append(f"{l['no']} not listed"); continue
        ok = False
        for i in idxs:
            end = i + 1
            while end < len(lines) and end < i + 6 and not any(o.search(lines[end]) for o in all_pns):
                end += 1
            window = "\n".join(lines[i:end])
            for o in all_pns:
                window = o.sub(" ", window)
            if has_num(window, l["qty"], 0.001):
                ok = True; break
        if not ok:
            bad.append(f"{l['no']} without quantity {l['qty']}")
    stock_rx = re.compile(_pn(f["stock_part"]).pattern + r"|fastener kit|t-?bolt", re.I)
    stock_bad = [s[:100] for s in sentences(text) if stock_rx.search(s) and not EXCLUDE.search(s)]
    dock = re.compile(date_rx(f["dock_by"]), re.I)
    quote = re.compile(date_rx(f["quote_due"]), re.I)
    us = units(text)
    dock_ok = any(dock.search(u) and DELIVER.search(u) for u in us)
    quote_ok = any(quote.search(u) and QUOTE.search(u) for u in us)
    return [
        result(names[0], not bad, "; ".join(bad[:6]) or f"all {len(f['lines'])} bought parts at {f['benches']} benches"),
        result(names[1], not stock_bad, "; ".join(stock_bad[:2]) or "fastener kit not requested"),
        result(names[2], dock_ok, f"dock date {f['dock_by']} stated" if dock_ok else f"no delivery line or sentence carries {f['dock_by']}"),
        result(names[3], quote_ok, f"quote due {f['quote_due']} stated" if quote_ok else f"no quote line or sentence carries {f['quote_due']}"),
    ]
