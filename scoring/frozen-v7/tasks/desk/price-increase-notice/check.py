"""The mailing note names every annual-contract customer with its renewal date, and does not leave off the customer
that converted to month-to-month.

A customer is recognised by the first word of its business name. An annual customer passes when one line or sentence
names it together with its renewal date (October 31, Oct 31, 10/31, 2026-10-31 or 31 October; the year is optional).
The converted customer fails the check only where the note presents it as one to leave off: a line or sentence names
it with an annual/leave-off/renewal cue or a date, and says nothing that clears it (month-to-month, no longer annual,
the annual term ended, include it or send it the letter, none of those negated); or it is a bare entry in a list or
table under an intro line that says to leave these customers off. A clearing word in the very next sentence counts
when that sentence refers back to it ("Its annual contract ended in June, so include it."). A recipient list or an
explanation that names it without any leave-off cue is not a leave-off entry. Expected names come from
reference/notes.json.
"""
import glob
import json
import os
import re

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
CLEAR = re.compile(r"(month[- ]to[- ]month|\bmonthly\b|no longer (on )?an? annual|no longer annual|not (on )?an? annual|"
                   r"not (be )?(left off|leave|excluded|exclude|exempt|grandfathered|removed|skipped)|"
                   r"\bdoes get\b|\bdo get\b|should (get|receive)|will (get|receive)|\bgets the\b|\breceives the\b|"
                   r"\bended\b|\bexpired\b|\bconverted\b|\blapsed\b|\bfinished\b|\bran out\b|"
                   r"\binclude (it|them)\b|\b(be|is|are|stays?|remains?) (included|on the (mailing|list))\b|\binclude[sd]?\b[^.;]{0,20}\b(mailing|letter|recipients)\b|"
                   r"\bkeep (it|them) on\b|\bsend (it |them )?(the |this )?(letter|notice)|\bsend (it |them )?to\b|\bmail (it|them) (the|this)\b)", re.I)
# a clearing word that is itself negated ("do not include", "don't send") clears nothing
NEGATED = re.compile(r"(\bnot\b|n't\b|\bnever\b|\bno\b|\bnor\b)\W+(\w+\W+)?$", re.I)
# the customer presented as one to leave off: annual, leave off, keeps its price, renews
LEAVE_OFF = re.compile(r"\bannual|leave\b[^.;]{0,40}\boff\b|left off|\boff the (mailing|list)|\bexclud|\bexempt|grandfather|"
                       r"keeps? (their |its )?(current|existing|old|present) pric|\brenew|"
                       r"(do not|don't|shouldn't|should not|won't|will not|not to|doesn't|does not)\s+(get|receive|send|mail|include)|\bskip\b|\bhold (back|off)\b|remove from", re.I)
ANY_DATE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b|\b\d{1,2}\s+(of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|"
                      r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b|\b\d{4}-\d{2}-\d{2}\b", re.I)
REFERS_BACK = re.compile(r"^\W*(it|its|it's|they|their|this customer|that customer|this one|that one)\b", re.I)
LIST_LINE = re.compile(r"^\s*([-*+]\s|\d+[.)]\s|\|)")
# an intro line that heads the recipient list, whatever it goes on to say about exclusions
RECIPIENTS_HEAD = re.compile(r"^\W*(mailing list|mail(ing)? to|recipients|send (the |this )?(letter|notice)? ?to|send to|who (gets|receives))", re.I)


def _clears(piece):
    return any(not NEGATED.search(piece[:m.start()]) for m in CLEAR.finditer(piece))


def _leave_off(piece):
    return any(not NEGATED.search(piece[:m.start()]) for m in LEAVE_OFF.finditer(piece))


def _date_re(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    mon = MONTHS[m - 1]
    return re.compile(rf"({mon}|{mon[:3]}\.?|{mon[:4]}\.?)\s+0?{d}(st|nd|rd|th)?\b|\b0?{d}(st|nd|rd|th)?\s+(of\s+)?({mon}|{mon[:3]})\b|"
                      rf"\b0?{m}/0?{d}(/(20)?{y % 100})?\b|\b{y}-{m:02d}-{d:02d}\b", re.I)


def _pieces(text):
    # a sentence break, but not after a month abbreviation ("Jan. 31") or a.m./p.m.
    return [p for p in re.split(r"(?<=[.!?])(?<!\b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\.)(?<!Sept\.)(?<![ap]\.m\.)\s+|\n+", text) if p.strip()]


def _left_off_mentions(text, crx):
    """Pieces that present the converted customer as one to leave off the mailing."""
    lines = text.splitlines()
    bad = []
    for li, line in enumerate(lines):
        if not crx.search(line):
            continue
        pieces = _pieces(line)
        for pi, p in enumerate(pieces):
            if not crx.search(p):
                continue
            nxt = pieces[pi + 1] if pi + 1 < len(pieces) else next((l for l in lines[li + 1:] if l.strip()), "")
            if _clears(p) or (REFERS_BACK.search(nxt) and _clears(nxt)):
                continue
            if _leave_off(p) or ANY_DATE.search(p):
                bad.append(p); continue
            if LIST_LINE.match(line):
                head = next((lines[j] for j in range(li - 1, -1, -1) if lines[j].strip() and not LIST_LINE.match(lines[j])), "")
                if head and _leave_off(head) and not _clears(head) and not RECIPIENTS_HEAD.search(head):
                    bad.append(p)
    return bad


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
    wrong = _left_off_mentions(text, crx)
    out.append({"name": f"{name}: {conv} is not left off", "passed": not wrong,
                "detail": f"named as if still annual: {wrong[0][:120]!r}" if wrong else f"{conv} not listed as an annual customer"})
    return out
