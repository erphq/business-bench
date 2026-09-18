"""Custom grader for policy-update-memo: the moved clause is not reported as a change, and the memo gives the owner's
effective date.

  * phone clause not reported as changed: no sentence about phone use while driving says it is new, added, removed,
    updated, revised, stricter or otherwise changed, unless the same sentence says it moved, was renumbered or is
    unchanged
  * effective date: a line or sentence about the policies taking effect carries November 1, 2026 in any common form
  * PDF effective date only as a correction: October 1, 2026 (printed on the final PDF, which is not being reprinted)
    may appear only where the memo retires it: the date itself is negated ("not October 1 as printed"), its sentence
    says it is wrong, superseded, no longer applies or was moved from, or its sentence or an adjacent sentence in the
    same paragraph sets it against November 1 with a contrast or a pointer to the printed copy ("the PDF still says
    October 1; the policies take effect November 1"). November 1 negated in that pairing ("October 1, not November
    1") does not count. The old rule banned the date outright, which failed the natural correction of the PDF.
Dates come from reference/facts.json.
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


PHONE = re.compile(r"\bphones?\b|handheld|hands-free|cell|texting|while driving", re.I)
CHANGED = re.compile(r"chang|updat|revis|\bnew\b|\badd(ed|s)?\b|remov|delet|dropp|stricter|tighten|replac|introduc|no longer|\bnow (bans?|prohibits?|requires?|says)|eliminat|rewrit|reword", re.I)
SAME = re.compile(r"unchanged|not changed|no change|same (as|wording|rule)|identical|\bmoved\b|renumber|reorder|relocat|new (place|position|location|section number)|"
                  r"didn't change|did not change|hasn't changed|has not changed|haven't changed|have not changed|only (its|the) (place|position|number|location)|still the same", re.I)
EFFECT = re.compile(r"effective|take[sn]? effect|taking effect|in effect|start|begin|apply|applies|from|as of|go(es)? live|kick", re.I)


# A negation attached to the date itself: "not October 1", "instead of October 1", "rather than the October 1 date".
NEG_BEFORE = re.compile(r"\b(?:not|never|instead of|rather than|no longer|nor)\s+(?:(?:the|on|from|of|by|as of)\s+)?$", re.I)
# The sentence itself retires the date.
RETIRED = re.compile(r"wrong|incorrect|inaccurate|outdated|out[- ]of[- ]date|\btypos?\b|misprint|\berrors?\b|mistak|\bignor|disregard|supersed|overrid|"
                     r"cross(?:ed)? (?:it |that |this )?out|no longer (?:appl|valid|correct|current|stand|hold|the)|"
                     r"(?:not|n['’]t) (?:the )?(?:correct|right|current|valid|actual|real|final)\b|"
                     r"(?:changed|moved|pushed(?: back)?|postponed|delayed|shifted) from|originally|previously|initially|\bold (?:date|start)", re.I)
# A contrast or a pointer to the printed copy, for a sentence that pairs the date with November 1.
CONTRAST = re.compile(r"instead|\bnot\b|n['’]t\b|rather|no longer|\bmov|\bpush|postpon|delay|later|\bwas\b|\bwere\b|printed|print|\bpdf\b|handbook|"
                      r"document|booklet|copy|cover|says|\bshows?\b|lists?|reads|states|still|replac|chang|correct|\bbut\b|however|although|though|"
                      r"whereas|\bwhile\b|→|->|=>|new (?:date|start)", re.I)
# For a date paired across adjacent sentences, the sentence with November 1 must itself correct: plain memo words
# ("updated", "new", "now") do not tie two sentences together.
NEIGHBOUR_CUE = re.compile(r"instead|\bnot\b|n['’]t\b|rather than|no longer|\bmoved\b|pushed|postpon|delay|\blater\b|replac|supersed|\bbut\b|"
                           r"however|although|correct(?:ed|ion)?\b|\bactual|\breal\b|printed|\bpdf\b|\bignor|disregard", re.I)
_LIST = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def _paragraph_sentences(text: str) -> list[list[str]]:
    """Sentences grouped by paragraph (blank-line blocks); list items and table rows are separate lines, hard-wrapped
    prose lines are re-joined."""
    paras: list[list[str]] = []
    for block in re.split(r"\n\s*\n", text):
        lines: list[str] = []
        for raw in block.splitlines():
            if not raw.strip():
                continue
            if lines and not _LIST.match(raw) and "|" not in raw and "|" not in lines[-1] and not raw.lstrip().startswith("#") \
                    and not lines[-1].lstrip().startswith("#"):
                lines[-1] = lines[-1].rstrip() + " " + raw.strip()
            else:
                lines.append(raw)
        sents = [s for l in lines for s in sentences(l)]
        if sents:
            paras.append(sents)
    return paras


def _stale_date_uncorrected(text: str, stale_rx, right_rx) -> list[str]:
    def right_in(s: str) -> bool:   # November 1 stated, not negated ("October 1, not November 1" does not count)
        return any(not NEG_BEFORE.search(s[:r.start()]) for r in right_rx.finditer(s))

    bad: list[str] = []
    for sents in _paragraph_sentences(text):
        for k, sent in enumerate(sents):
            nbrs = sents[max(0, k - 1):k] + sents[k + 1:k + 2]
            for m in stale_rx.finditer(sent):
                before, after = sent[:m.start()], sent[m.end():]
                struck = before.rstrip().endswith("~~") or re.match(r"(?:,?\s*\d{4})?~~", after) is not None
                ok = (struck
                      or bool(NEG_BEFORE.search(before))                                    # "not October 1"
                      or bool(RETIRED.search(sent))                                         # "October 1 no longer applies"
                      or (right_in(sent) and bool(CONTRAST.search(sent)))                   # "the PDF says October 1, but ... November 1"
                      or any(right_in(s) and NEIGHBOUR_CUE.search(s) for s in nbrs)         # "... October 1. We start November 1 instead."
                      or (bool(CONTRAST.search(sent)) and any(RETIRED.search(s) for s in nbrs)))  # "The PDF says October 1. Ignore that date."
                if not ok:
                    bad.append(sent.strip()[:120])
    return bad

def check(ws, ref):
    names = ["phone clause not reported as changed", "effective date", "PDF effective date only as a correction"]
    p = find(ws, "memo.md")
    if not p:
        return [result(n, False, "no memo.md in workspace") for n in names]
    f = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    text = read(p)
    bad = [s[:120] for s in sentences(text) if PHONE.search(s) and CHANGED.search(s) and not SAME.search(s)]
    eff = re.compile(date_rx(f["effective"]), re.I)
    eff_ok = any(eff.search(u) and EFFECT.search(u) for u in units(text))
    stale = _stale_date_uncorrected(text, re.compile(date_rx(f["pdf_effective"]), re.I), eff)
    return [
        result(names[0], not bad, "; ".join(bad[:2]) or "phone clause not described as a change"),
        result(names[1], eff_ok, f"effective {f['effective']} stated" if eff_ok else f"no line or sentence gives the effective date {f['effective']}"),
        result(names[2], not stale, f"PDF date given without a correction: {stale[0]!r}" if stale else "October 1 not given as the effective date"),
    ]
