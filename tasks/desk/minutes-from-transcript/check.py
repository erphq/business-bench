"""Custom grader for minutes-from-transcript: the minutes carry the meeting date, each action's full-name owner and
calendar due date, and only the final version of each reversed decision.

  * meeting date: the date in the calendar invite appears (not only the transcript's upload date)
  * each action: some table row, list item, sentence or clause names the action, the owner's surname and the due date
    resolved from the meeting date; a paragraph or list item that names more than one action only counts at sentence
    or clause level, so one owner cannot be borrowed from a neighbouring action
  * wrong Marcus absent: the board treasurer who shares the grocery manager's first name and declined the invite is not named
  * freezer not recorded as going to the first vendor: no sentence or line gives the first vendor as chosen, booked or
    approved unless it also says that was reversed, changed or fell through
  * Christmas Eve closing: a line or sentence gives the final 5 pm closing, and none gives 3 pm as the closing time
    unless it says that was changed
Dates match the common written forms; times match 5 PM, 5:00 p.m., 17:00. Values come from reference/facts.json.
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


DECIDE = re.compile(r"go(ing)? with|chose|chosen|select|approv|award|\bbook|\bhire|decid|decision|contract|goes to|going to|\bwill (do|handle|repair|replace)|vendor:|assigned", re.I)
REVERSAL = re.compile(r"instead|rather than|revers|changed|switch|dropp|originally|initially|at first|earlier|cancel|\bnot\b|n't\b|no longer|withdr|replac|"
                      r"overturn|unable|cannot|delay|\bbut\b|however|supersed|backed out|fell through|later|revis|previous|prior", re.I)
XMAS = re.compile(r"christmas eve|dec(ember)?\.?\s+24(th)?\b|\b24(th)?\s+(of\s+)?dec|\b12/24\b", re.I)


def _items(text):
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


def _graded_units(text):
    out = [(re.sub(r"\s+", " ", b), False) for b in re.split(r"\n\s*\n", text) if b.strip()]
    out += [(it, False) for it in _items(text)]
    for it in _items(text):
        for s in sentences(it):
            out.append((s, True))
            out += [(c, True) for c in s.split(";") if c.strip()]
    return out


def check(ws, ref):
    p = find(ws, "minutes.md")
    f = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    names = ["meeting date"] + [f"action {a['key']}: {a['owner_first']} {a['owner_last']}, due {a['due']}" for a in f["actions"]] + \
            ["other Marcus not named", "freezer not recorded as the first vendor", "Christmas Eve closing is the final time"]
    if not p:
        return [result(n, False, "no minutes.md in workspace") for n in names]
    text = read(p)
    res = []
    ok = bool(re.search(date_rx(f["meeting"]), text, re.I))
    res.append(result(names[0], ok, f"{f['meeting']} stated" if ok else f"meeting date {f['meeting']} not found"))
    gunits = _graded_units(text)
    for a, nm in zip(f["actions"], names[1:1 + len(f["actions"])]):
        others = [b["keyword"] for b in f["actions"] if b is not a]
        due = re.compile(date_rx(a["due"]), re.I)
        owner = re.compile(rf"\b{re.escape(a['owner_last'])}\b", re.I)
        hit = False
        for u, fine in gunits:
            if not re.search(a["keyword"], u, re.I):
                continue
            if not fine and any(re.search(o, u, re.I) for o in others):
                continue
            if owner.search(u) and due.search(u):
                hit = True; break
        res.append(result(nm, hit, "found in one row, item or sentence" if hit else "no row, item or sentence names this action with that owner's surname and due date"))
    wrong = re.search(rf"\b{re.escape(f['wrong_marcus'])}\b", text, re.I)
    res.append(result(names[-3], not wrong, "not named" if not wrong else f"names {f['wrong_marcus']}, who declined the meeting"))
    lines = [l for l in text.splitlines() if l.strip()]
    pool = sentences(text) + lines
    bad_vendor = [u[:120] for u in pool if re.search(r"polar\s*tech", u, re.I) and DECIDE.search(u) and not REVERSAL.search(u)]
    res.append(result(names[-2], not bad_vendor, "; ".join(bad_vendor[:2]) or "Polar Tech not recorded as the final choice"))
    five = re.compile(time_rx(17, 0) + r"|\bclos\w*\s+(at\s+)?5\b(?![:.]?\d)(?!\s*a\.?\s*m)", re.I)
    three = re.compile(time_rx(15, 0) + r"|\bclos\w*\s+(at\s+)?3\b(?![:.]?\d)(?!\s*a\.?\s*m)", re.I)
    fin = any(XMAS.search(u) and five.search(u) for u in units(text))
    stale = [u[:120] for u in pool if XMAS.search(u) and three.search(u) and not REVERSAL.search(u)]
    res.append(result(names[-1], fin and not stale, ("5 pm stated" if fin else "no Christmas Eve line or sentence gives 5 pm") + ("; 3 pm given as final: " + "; ".join(stale[:2]) if stale else "")))
    return res
