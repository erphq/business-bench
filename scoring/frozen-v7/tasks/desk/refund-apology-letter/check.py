"""Custom grader for refund-apology-letter: the reply promises nothing the policy forbids and does not treat the
mistyped order number as the customer's order.

  * no shipping refund promised: no sentence or clause says the shipping charge is refunded, reimbursed or included,
    unless it negates that, reports what the customer asked for, states the policy's limit ("refunded only when every
    item arrives damaged") or turns the request down ("declined", "outside our policy")
  * no compensation promised: no sentence or clause offers a gift card, store or account credit, voucher, coupon or a
    code for a future order, unless it negates that, reports the customer's request, turns it down, or describes the
    superseded saved-reply template
  Soft-wrapped lines are joined before sentences are split, and a limit in one clause does not excuse a promise in another.
  * wrong order number not used: a sentence that carries the swapped number must also carry the right one or say it
    was a typo, a different order, or that nothing under it is hers
Values come from reference/facts.json, so nothing here is pinned to a seed.
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


SHIP = re.compile(r"\bshipping\b|\bpostage\b|\bdelivery (charge|fee|cost)", re.I)
REFUNDISH = re.compile(r"refund|reimburs|\bcredit|\bback\b|\binclud|\bplus\b|\bcover", re.I)
PROMISE = re.compile(r"\b(we|we'll|we will|we've|we have|i've|i have|i will|i'll|you'll|you will|will be|has been|have been|is being|are being|also|including|includes|plus|along with)\b", re.I)
COMP = re.compile(r"gift ?card|store credit|account credit|shop credit|\bvoucher|\bcoupon|goodwill|credit (of|for)\b|\$\s?\d+(\.\d\d)?\s+(credit|gift)|"
                  r"(discount|promo) code (for|toward|towards|on|off) (your|a) (next|future)|off your next|on your next order", re.I)
REPORTED = re.compile(r"\b(asked|ask for|requested|request|mentioned|wanted|want|would like|you'd like|suggested|hoping|hoped)\b", re.I)
CORRECTION = re.compile(r"typo|swap|transpos|mistyp|meant|actually|correct|different|another|belongs|rather than|instead of|\bnot\b|n't\b|"
                        r"\bnothing\b|\bnone\b|\bno\s+(?:such\s+|matching\s+)?(?:order|record|match)", re.I)
# A clause that states the policy's limit or turns the request down is not a promise: a restrictive condition
# ("refunded only when every item arrives damaged", "except when", "unless"), a refusal ("declined", "outside our
# policy"), or a description of the superseded saved-reply template the letter is not using.
RESTRICT = re.compile(r"\bonly\s+(?:[\w’']+\s+){0,3}?(?:when|if|where)\b|\bexcept\s+(?:when|if|where)\b|\bunless\b|\bdeclin(?:e|es|ed|ing)\b|"
                      r"\b(?:outside|against|beyond)\s+(?:of\s+)?(?:our|the|this|that|store)?\s*(?:\w+\s+){0,2}?polic|"
                      r"\bineligible\b|\bnot eligible\b|\bdo(?:es)?\s*n[’']t qualify|\btemplates?\b|\bsaved repl", re.I)
# clauses of one sentence: a policy limit in one clause does not excuse a promise in another
# ("our policy refunds shipping only when every item arrives damaged, but we've refunded yours anyway")
SPLIT = re.compile(r";|,?\s+\b(?:but|however|although|though|yet)\b|,\s+(?:and\s+|so\s+)?(?=(?:we|i)\b)", re.I)


def _ship_promise(c: str) -> bool:
    return bool(SHIP.search(c) and REFUNDISH.search(c) and PROMISE.search(c))


def check(ws, ref):
    p = find(ws, "response.md")
    names = ["no shipping refund promised", "no gift card or credit promised", "wrong order number not used as hers"]
    if not p:
        return [result(n, False, "no response.md in workspace") for n in names]
    facts = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    text = read(p)
    # soft-wrapped lines are joined first, so "does not offer\ngift cards" keeps its negation
    sents = sentences(unwrap(text))
    bad_ship, bad_comp = [], []
    for s in sents:
        if NEG.search(s) or REPORTED.search(s):
            continue
        clauses = [c for c in SPLIT.split(s) if c.strip()]
        ship = any(_ship_promise(c) and not RESTRICT.search(c) for c in clauses)
        # a promise spread over clauses ("we've refunded the skillet; shipping too") is judged on the whole sentence
        ship = ship or (_ship_promise(s) and not any(_ship_promise(c) for c in clauses) and not RESTRICT.search(s))
        if ship:
            bad_ship.append(s[:120])
        if any(COMP.search(c) and not RESTRICT.search(c) for c in clauses):
            bad_comp.append(s[:120])
    wrong = facts["wrong_no"][3:]
    right = facts["order_no"][3:]
    bad_no = [s[:120] for s in sents if re.search(rf"(?<!\d){wrong}(?!\d)", s) and not re.search(rf"(?<!\d){right}(?!\d)", s) and not CORRECTION.search(s)]
    return [
        result(names[0], not bad_ship, "; ".join(bad_ship[:3]) or "no sentence promises the shipping charge back"),
        result(names[1], not bad_comp, "; ".join(bad_comp[:3]) or "no sentence offers a gift card, credit or future-order code"),
        result(names[2], not bad_no, "; ".join(bad_no[:3]) or f"the swapped number {facts['wrong_no']} is not used as her order"),
    ]
