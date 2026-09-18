"""Custom grader for fundraising-appeal: the letter states the match and the foundation's deadline, not the notes' one.

  * match amount: a line or sentence about the match (match, matched, double, Osei) carries the match cap
  * match deadline: a line or sentence about the match carries the foundation's end date in any common written form
  * notes' deadline not given for the match: no sentence about the match gives December 31 as its deadline (a sentence
    that retires the notes' date, "November 30, not December 31", or a year-end tax clause is fine; "match" as an
    ordinary verb, "does not match the public rule", is not about the match)
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


# ---------------------------------------------------------------- superseded-value helpers
# A stale value (an old date, the first-planned hours, a replaced figure) may appear in correct text when the text
# retires it: "moved from October 20", "not December 31", "(was 9 AM to 1 PM)", "the 9 AM to 1 PM first planned",
# "raised the goal from $450,000 to $525,000". These helpers decide that from the words around the mention, never
# from one sanctioned phrasing.

_WD = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)"
_MO = r"(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
# words that can sit between a cue and the value without changing what the cue refers to
_FILL = (rf"(?:the|a|an|on|at|for|to|until|till|through|thru|by|from|as|of|its|our|your|their|this|that|those|these|about|around|"
         rf"approximately|roughly|nearly|almost|some|just|only|even|and|between|date|day|time|times|hours?|window|deadline|figure|amount|total|goal|"
         rf"{_WD}|{_MO}|\d[\d,.:]*|[ap]\.?m\.?|noon|morning|afternoon|\$[\d,.]+)")
_GAP = rf"(?:[\s\W]*{_FILL}\b\.?)"

# a negation or substitution directly before the value: "not December 31", "rather than Tuesday, October 20", "(not 9 AM to 1 PM)"
_NEG_BEFORE = re.compile(rf"(?:\bnot\b|n[’']t\b|\bno longer\b|\bnever\b|\brather than\b|\binstead of\b|\bin place of\b|\bdisregard\b|\bignore\b|"
                         rf"\breplac(?:es|ing|ed)\b|\bsupersed(?:es|ing|ed)\b){_GAP}{{0,6}}[\s\W]*$", re.I)
# an earlier plan or past state: "originally scheduled for October 20", "previously 9 to 1", "was October 20", "the old date of"
_PAST_BEFORE = re.compile(r"(?:\b(?:originally|previously|initially|formerly|earlier|first\s+(?:planned|scheduled|announced|listed|set|given|stated|proposed|quoted|reported|posted|sent|shared|published|circulated))\b"
                          r"(?:\W+[\w’'-]+){0,4}?"
                          r"|\b(?:original|old|older|previous|prior|initial|former|outdated|out-of-date|superseded|stale|incorrect|wrong|earlier)\b(?:\W+[\w’'-]+){0,2}?"
                          r"|\b(?:was|were|had been|used to be)\b(?:\W+[\w’'-]+){0,1}?)"
                          rf"{_GAP}{{0,4}}[\s\W]*$", re.I)
# a change away from the value: "moved from", "rescheduled from", "pushed back a week from", "raised the goal from", "up from"
_CHANGE_FROM = re.compile(rf"(?:\b(?:mov|reschedul|chang|postpon|push|shift|delay|updat|revis|extend|widen|lengthen|expand|rais|increas|"
                          rf"bump|correct|adjust|up)\w*\b(?:\W+[\w’'-]+){{0,3}}?\W+from){_GAP}{{0,4}}[\s\W]*$", re.I)
# a cue right after the value: "9 AM to 1 PM first planned", "October 20 (as originally scheduled)", "October 20 is no longer the date"
_AFTER = re.compile(rf"^{_GAP}{{0,6}}[\s\W]*(?:\b(?:as\s+|that\s+was\s+|which\s+was\s+|we\s+)?(?:first|originally|initially|previously|earlier)\s+"
                    rf"(?:planned|scheduled|announced|listed|set|given|stated|proposed|quoted|reported|said|posted|sent)\b"
                    rf"|\b(?:is|was|were|are|has been|have been)\s+(?:now\s+)?(?:no longer|not\b|cancel|postpon|moved|changed|replaced|superseded|dropped|wrong|"
                    rf"incorrect|outdated|out of date|stale)"
                    rf"|\bno longer\b|\bnow\s+(?:moved|changed|replaced|superseded)\b|→|->|⟶|⇒"
                    rf"|\b(?:but\s+|and\s+)?(?:the\s+)?(?:correct|actual|updated|revised|right)\s+(?:date|day|time|times|hours|window|figure|amount|total|goal|deadline)\b"
                    rf"|\b(?:the\s+)?new\s+(?:date|day|deadline|goal|figure)\s+(?:is|will be)\b)", re.I)
# a sentence that sets the stale value against the current one: "the notes say $259,000, but the export gives $240,714.58"
_CONTRAST = re.compile(r"\bbut\b|\bhowever\b|\bwhereas\b|\bwhile\b|\balthough\b|\binstead\b|\brather\b|\bnot\b|n[’']t\b|\bactual(?:ly)?\b|\bin fact\b|"
                       r"\bstale\b|\boutdated\b|\bout of date\b|\bsupersed|\bcorrect|\bupdated\b|\bchanged\b|\bmoved\b|\brescheduled\b|\bnow\b|\bnew\b|"
                       r"\bgoverns?\b|\bprecedence\b|\boverrid", re.I)


def retired_at(unit: str, start: int, end: int, current: re.Pattern | None = None) -> bool:
    """True when the stale value at unit[start:end] is presented as the old or wrong value, not as a current fact."""
    before, after = unit[:start], unit[end:]
    if before.count("~~") % 2 == 1 and "~~" in after:          # struck through: ~~October 20~~
        return True
    if _NEG_BEFORE.search(before) or _PAST_BEFORE.search(before) or _CHANGE_FROM.search(before) or _AFTER.search(after):
        return True
    if current is not None and _CONTRAST.search(unit[:start] + " " * (end - start) + unit[end:]):
        # the current value must stand in the same sentence as a live fact, not itself be the negated one
        # ("matched through December 31, not just November 30" retires November 30, not December 31)
        for m in current.finditer(unit):
            if m.end() <= start or m.start() >= end:
                b = unit[:m.start()]
                if not (_NEG_BEFORE.search(b) or _PAST_BEFORE.search(b) or _CHANGE_FROM.search(b) or _AFTER.search(unit[m.end():])):
                    return True
    return False


def unwrap(text: str) -> str:
    """Join soft-wrapped lines inside a paragraph or list item, so a sentence broken across lines keeps its words together.
    A line that ends a sentence or a clause (. ! ? ,), a heading, an email header line, a list marker, a table row or a
    blank line still breaks; a label ending in a colon joins the line it introduces ("Match deadline:" / "November 30")."""
    out: list[str] = []
    for line in text.split("\n"):
        s = line.strip()
        starts_block = (not s) or bool(re.match(r"(#{1,6}\s|[-*+•]\s|\d+[.)]\s|\||>)", s))
        prev = out[-1].strip() if out else ""
        if prev and not starts_block and not re.search(r"[.!?,|]\**\s*$", prev) and not prev.startswith(("#", "|")) \
                and not re.match(r"\W*(?:subject|re|to|from|date|cc|bcc)\W*:", prev, re.I):
            out[-1] = out[-1].rstrip() + " " + s
        else:
            out.append(line)
    return "\n".join(out)
# ---------------------------------------------------------------- end superseded-value helpers


MATCHW = re.compile(r"\bmatch|\bdoubl|\btwice\b|osei|challenge", re.I)
# "match" as an ordinary verb ("the board report figure does not match the public rule", "numbers need to match the
# export") is not the matching gift; the grant sense keeps its object ("agreed to match gifts", "will match every dollar")
VERB_MATCH = re.compile(r"\b(?:do|does|did|don[’']t|doesn[’']t|didn[’']t|not|won[’']t|to|must|should|would)\s+match(?:es|ed)?\b"
                        r"(?!\s+(?:every|each|all|any|gifts?|donations?|contributions?|your|dollar|up\s+to|new|the\s+first|them|it|\$))", re.I)
# a sentence that refers back to the match without naming it
ANAPHOR = re.compile(r"\b(?:the|this|that|its|our)\s+(?:deadline|offer|challenge|window|cut-?off|match(?:ing)?\s+(?:period|window|deadline))\b|"
                     r"\b(?:it|this|that|the offer)\s+(?:ends|runs|expires|lasts|closes|is good)\b|\bto (?:qualify|be matched|be doubled|double)\b", re.I)
# the notes' date attributed to its source ("Shirley's August 30 note said December 31") and corrected in the same or the
# next sentence is a report of the stale date, not the letter's deadline
REPORTED = re.compile(r"\b(?:notes?|entry|report|memo|shirley[’']?s?)\b[^.]{0,60}?\b(?:say|says|said|state|states|stated|list|lists|listed|"
                      r"give|gives|gave|show|shows|showed|quote|quotes|quoted|put|puts|had|has|mention|mentions|mentioned|cite|cites|cited)\b|"
                      r"\b(?:in|from|per)\s+(?:the\s+|shirley[’']?s?\s+)?(?:\w+\s+){0,3}?(?:notes?|report|memo|entry)\b", re.I)
CORRECTION = re.compile(r"\bstale\b|\boutdated\b|\bout of date\b|\bsupersed|\bwrong\b|\bincorrect|\binaccurate|\bno longer\b|\bold\b|"
                        r"\bearlier\b|\bprevious|\boriginal|\bcorrected\b|\bcorrection\b|\binstead\b|\brather than\b|\bgoverns?\b|"
                        r"\bprecedence\b|\boverrid|\bdoes not\b|\bdoesn[’']t\b|(?:\bnot|n[’']t)\s+(?:the\s+)?(?:current|right|correct|accurate|latest|final|official)\b", re.I)
# a year-end tax sentence may name December 31 without meaning the match deadline
TAX = re.compile(r"\btax|deductib|year[- ]end|calendar year|end of the year", re.I)


def _about_match(s: str) -> bool:
    for m in MATCHW.finditer(s):
        if not m.group(0).lower().startswith("match"):
            return True
        v = VERB_MATCH.search(s, max(0, m.start() - 12))
        if not (v and v.start() <= m.start() < v.end()):
            return True
    return False


def _clause(s: str, start: int, end: int) -> str:
    a = max(s.rfind(c, 0, start) for c in ",;()—–")
    bs = [i for i in (s.find(c, end) for c in ",;()—–") if i >= 0]
    return s[a + 1:(min(bs) if bs else len(s))]


def check(ws, ref):
    names = ["match amount stated", "match deadline from the foundation's letter", "notes' December 31 not given as the match deadline"]
    p = find(ws, "appeal.md")
    if not p:
        return [result(n, False, "no appeal.md in workspace") for n in names]
    f = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    text = read(p)
    us = [u for u in units(text) if MATCHW.search(u)]
    amt = any(has_num(u, f["match"], 0.5) or re.search(rf"\b{f['match'] // 1000}\s*k\b", u, re.I) for u in us)
    end = re.compile(date_rx(f["match_end"]), re.I)
    dl = any(end.search(u) for u in us)
    wrong = re.compile(date_rx(f["notes_match_end"]), re.I)
    # the notes' date fails only where a sentence about the match gives it as the deadline; a sentence that retires it
    # ("the match ends November 30, not December 31", "the notes said December 31, but the letter says November 30")
    # or uses it for the tax year is fine
    # A sentence that points back at the match ("The deadline is December 31.") counts with the sentence before it.
    bad = []
    sents = sentences(unwrap(text))
    for i, u in enumerate(sents):
        if not (_about_match(u) or (i > 0 and ANAPHOR.search(u) and _about_match(sents[i - 1]))):
            continue
        for m in wrong.finditer(u):
            if TAX.search(_clause(u, m.start(), m.end())) or retired_at(u, m.start(), m.end(), current=end):
                continue
            nxt = sents[i + 1] if i + 1 < len(sents) else ""
            if REPORTED.search(u[:m.start()]) and (end.search(u) or CORRECTION.search(u) or CORRECTION.search(nxt)):
                continue
            bad.append(u[:120]); break
    return [
        result(names[0], amt, f"match of {f['match']:,} stated" if amt else f"no match sentence carries {f['match']:,}"),
        result(names[1], dl, f"{f['match_end']} stated with the match" if dl else f"no match sentence carries {f['match_end']}"),
        result(names[2], not bad, "; ".join(bad[:2]) or "December 31 not tied to the match"),
    ]
