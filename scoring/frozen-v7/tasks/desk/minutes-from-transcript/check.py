"""Custom grader for minutes-from-transcript: the minutes carry the meeting date, each action's full-name owner and
calendar due date, and only the final version of each reversed decision.

  * meeting date: the date in the calendar invite appears (not only the transcript's upload date)
  * each action: some table row, list item, sentence or clause names the action, the owner's surname and the due date
    resolved from the meeting date; a paragraph or list item that names more than one action only counts at sentence
    or clause level, so one owner cannot be borrowed from a neighbouring action
  * wrong Marcus not a participant: the board treasurer who shares the grocery manager's first name and declined the
    invite is never named as attending, owning an action or deciding anything. Naming him is fine where the mention
    itself says he was absent or declined ("Absent: Marcus Rodriguez", "Marcus Rodriguez (Board Treasurer) declined"),
    where the list or table sits under an absent/declined heading, or where he is named to rule him out ("Marcus Wright,
    not Marcus Rodriguez"). A cue only counts for his mention when no other attendee's name sits between the two.
  * freezer not recorded as going to the first vendor: no sentence or line gives the first vendor as chosen, booked or
    approved unless that sentence says it was reversed, fell through or could not be done, or the same list item or
    paragraph (with its nested sub-items) also records the switch: the second vendor as the one chosen, or the first
    vendor's setback stated in its own sentence; a heading section counts when it states the reversal in so many words
  * Christmas Eve closing: a line or sentence gives the final 5 pm closing, and none gives 3 pm as the closing time
    unless it says that was changed, or the same list item or paragraph goes on to move the closing to 5 pm
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


# A mention of the declined attendee is fine when the mention itself says he was not there, or rules him out.
ABSENT = re.compile(r"absent|absence|declin|apolog|regrets?\b|excused|\bmissed\s+(?:the\s+)?(?:meeting|call)|unavailable|"
                    r"\bnot\s+(?:present|in\s+attendance|attend\w*|at\s+the\s+meeting|there|join\w*)|"
                    r"(?:did|could|was|were|is)\s*(?:not|n't)\s+(?:attend|make|join|present|there|in\s+attendance|at\s+the\s+meeting)|"
                    r"unable\s+to\s+(?:attend|join|make)", re.I)
RULED_OUT = re.compile(r"(?:\bnot\b|n't|\bnever\b|rather\s+than|instead\s+of|as\s+opposed\s+to|other\s+than|confused\s+with|distinct\s+from|"
                       r"\bunlike\b|\bexcluding\b)\W*(?:[\w()'-]+\W+){0,3}$", re.I)
ATTEND_LABEL = re.compile(r"attend(?:ees|ed|ing)|\bpresent\b(?!\s*:?\s*none)|participants|\bowners?\b|assigned|responsible", re.I)
LIST_LINE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\|)")
HEADING_LINE = re.compile(r"^\s*(?:#{1,6}\s|\*\*[^*]+\*\*:?\s*$|__[^_]+__:?\s*$|[^|]{1,80}:\s*(?:\*\*|__)?\s*$|[^|.!?;]{1,60}$)")


def _participant_mentions(text, surname, other_surnames):
    """Mentions of `surname` that present him as taking part: no absent/declined cue attached to the mention, no heading
    over its list saying so, and not named to rule him out."""
    name = re.compile(rf"\b{re.escape(surname)}\b", re.I)
    others = re.compile(r"\b(?:" + "|".join(re.escape(o) for o in other_surnames) + r")\b", re.I) if other_surnames else None
    lines = text.splitlines()
    bad = []
    for li, line in enumerate(lines):
        if not name.search(line):
            continue
        for sent in sentences(line):
            for clause in sent.split(";"):
                for m in name.finditer(clause):
                    if RULED_OUT.search(clause[:m.start()][-80:]):
                        continue
                    attached = False
                    for cue in ABSENT.finditer(clause):
                        lo, hi = (cue.end(), m.start()) if cue.end() <= m.start() else (m.end(), cue.start())
                        between = clause[lo:hi] if lo <= hi else ""
                        if len(between) <= 80 and not (others and others.search(between)) and not ATTEND_LABEL.search(between):
                            attached = True; break
                    if attached:
                        continue
                    if LIST_LINE.match(line) or not clause[:m.start()].strip(" *_|-:"):
                        head = next((lines[j] for j in range(li - 1, -1, -1)
                                     if lines[j].strip() and not LIST_LINE.match(lines[j])), "")
                        if head and HEADING_LINE.match(head) and ABSENT.search(head) and not ATTEND_LABEL.search(ABSENT.sub("", head)):
                            continue
                    bad.append(clause.strip()[:120])
    return bad


# Switching vendors or moving a time, stated in a sentence of its own.
SETBACK = re.compile(r"revers|instead|changed|switch|overturn|supersed|fell through|backed out|no longer|cancel|withdr|replac|"
                     r"unable|cannot|can't|can not|couldn't|could not|won't|unavailable|not available|back-?order|delay", re.I)
STRONG = re.compile(r"revers|instead|changed|switch|overturn|supersed|fell through|backed out|no longer|revis|moved|pushed|extended|updated", re.I)
MOVED = re.compile(r"\bclos\w*|mov(e|ed|ing)\b|push|extend|chang|later|final|instead|revers|revis|decid|agreed|settled|landed", re.I)
CHOSE = r"(?:go(?:ing|es)? with|went with|chose|chosen|select\w*|approv\w*|award\w*|book\w*|hire\w*|decid\w*|contract\w*|goes to|went to|switch\w* to|moved to)"


def _chosen(t, vendor):
    """The sentence gives `vendor` as the one chosen ("we go with Northwind", "Northwind was chosen"), not passed over."""
    v = vendor.pattern
    for m in re.finditer(rf"{CHOSE}(?P<gap>[^.;]{{0,30}}?){v}|{v}(?P<gap2>[^.;]{{0,40}}?){CHOSE}", t, re.I):
        gap = m.group("gap") if m.group("gap") is not None else m.group("gap2")
        if not re.search(r"\bover\b|\bthan\b|instead of|\bnot\b|n't\b|\bnever\b|\bno\b", gap, re.I):
            return True
    return False


def _norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def _contains(block, unit):
    return _norm_ws(unit) in _norm_ws(block)


def _same(a, b):
    return _norm_ws(a) == _norm_ws(b)


def _blocks(text):
    """Paragraphs and list items, each with the indented lines and sub-items under it."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        prev = lines[i - 1].strip() if i else ""
        is_item = bool(LIST_LINE.match(line))
        if not is_item and prev and not prev.startswith("#") and not LIST_LINE.match(lines[i - 1]):
            continue  # a continuation line of a paragraph already started
        ind = len(line) - len(line.lstrip())
        blk = [s]
        for nxt in lines[i + 1:]:
            ns = nxt.strip()
            if not ns or ns.startswith("#"):
                break
            nind = len(nxt) - len(nxt.lstrip())
            if LIST_LINE.match(nxt) and nind <= ind:
                break
            blk.append(ns)
        out.append(" ".join(blk))
    return out


def _sections(text):
    out, cur = [], []
    for line in text.splitlines():
        if re.match(r"^\s*#{1,6}\s", line) or re.match(r"^\s*\*\*[^*]+\*\*:?\s*$", line):
            if cur:
                out.append(" ".join(cur))
            cur = [line.strip()]
        elif line.strip():
            cur.append(line.strip())
    if cur:
        out.append(" ".join(cur))
    return out


def check(ws, ref):
    p = find(ws, "minutes.md")
    f = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    names = ["meeting date"] + [f"action {a['key']}: {a['owner_first']} {a['owner_last']}, due {a['due']}" for a in f["actions"]] + \
            ["other Marcus not named as a participant", "freezer not recorded as the first vendor", "Christmas Eve closing is the final time"]
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
    others = [a["owner_last"] for a in f["actions"] if a["owner_last"].lower() != f["wrong_marcus"].lower()]
    wrong = _participant_mentions(text, f["wrong_marcus"], others)
    res.append(result(names[-3], not wrong, "not named as a participant" if not wrong else
                      f"names {f['wrong_marcus']}, who declined the meeting, without saying so: {wrong[0]!r}"))
    lines = [l for l in text.splitlines() if l.strip()]
    pool = sentences(text) + lines
    first_v = re.compile(r"\s*".join(re.escape(w) for w in f.get("cheap_vendor", "Polar Tech").split()), re.I)
    final_v = re.compile(r"\s*".join(re.escape(w) for w in f.get("dear_vendor", "Northwind").split()), re.I)
    blocks, sections = _blocks(text), _sections(text)

    def vendor_excused(u):
        # the same list item or paragraph records the switch in another sentence; a section only in so many words
        for b in blocks:
            if not _contains(b, u):
                continue
            sents = sentences(b)
            for t in sents:
                if _same(t, u):
                    continue
                if _chosen(t, final_v):
                    return True
                if SETBACK.search(t) and first_v.search(t):
                    return True
        return any(_contains(sec, u) and any(not _same(t, u) and STRONG.search(t) and (first_v.search(t) or final_v.search(t))
                                             for t in sentences(sec)) for sec in sections)

    bad_vendor = [u[:120] for u in pool if first_v.search(u) and DECIDE.search(u) and not REVERSAL.search(u) and not SETBACK.search(u)
                  and not vendor_excused(u)]
    res.append(result(names[-2], not bad_vendor, "; ".join(bad_vendor[:2]) or "Polar Tech not recorded as the final choice"))
    five = re.compile(time_rx(17, 0) + r"|\bclos\w*\s+(at\s+)?5\b(?![:.]?\d)(?!\s*a\.?\s*m)", re.I)
    three = re.compile(time_rx(15, 0) + r"|\bclos\w*\s+(at\s+)?3\b(?![:.]?\d)(?!\s*a\.?\s*m)", re.I)
    fin = any(XMAS.search(u) and five.search(u) for u in units(text))

    def closing_excused(u):
        for b in blocks:
            if _contains(b, u) and any(not _same(t, u) and five.search(t) and not three.search(t) and
                                       (XMAS.search(t) or MOVED.search(t) or STRONG.search(t)) for t in sentences(b)):
                return True
        return any(_contains(sec, u) and any(not _same(t, u) and five.search(t) and not three.search(t) and STRONG.search(t)
                                             for t in sentences(sec)) for sec in sections)

    stale = [u[:120] for u in pool if XMAS.search(u) and three.search(u) and not REVERSAL.search(u) and not closing_excused(u)]
    res.append(result(names[-1], fin and not stale, ("5 pm stated" if fin else "no Christmas Eve line or sentence gives 5 pm") + ("; 3 pm given as final: " + "; ".join(stale[:2]) if stale else "")))
    return res
