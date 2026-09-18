"""payroll-tax-deposits: deposits.csv graded on the check dates each deposit covers.

A deposit is identified by the set of check dates it covers (parsed from the check_dates cell in any common date
style, several dates separated however the author likes). check() grades the grouping and the quarter label,
check_due() the due date, check_amounts() the amount to the cent. Truth comes from reference/deposits.json.
"""
import csv
import glob
import io
import json
import os
import re
from datetime import date, datetime

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _find(ws, name):
    hits = sorted(glob.glob(os.path.join(ws, name))) or sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    return hits[0] if hits else None


def _norm(c):
    return re.sub(r"[^a-z0-9]+", "_", str(c or "").strip().lower()).strip("_")


def _rows(path):
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        vals = [["" if v is None else str(v) for v in r] for r in load_workbook(path, data_only=True).active.iter_rows(values_only=True)]
    else:
        text = open(path, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        vals = list(csv.reader(io.StringIO(text)))
    if not vals:
        return []
    hdr = [_norm(h) for h in vals[0]]
    return [dict(zip(hdr, row)) for row in vals[1:] if any(str(x).strip() for x in row)]


def _year_for(month):
    return 2025 if month == 12 else 2026


def dates_in(text):
    """Every date mentioned in a cell: 2026-01-02, 01/02/2026, 1/2/26, 1/2, Jan 2 2026, 2 Jan, January 2."""
    s = str(text or "")
    out = []
    for m in re.finditer(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
        out.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    s2 = re.sub(r"\d{4}-\d{1,2}-\d{1,2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?", " ", s)
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", s2):
        mo, dy = int(m.group(1)), int(m.group(2))
        y = m.group(3)
        y = (2000 + int(y) if len(y) == 2 else int(y)) if y else _year_for(mo)
        out.append((y, mo, dy))
    s3 = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", s2)
    for m in re.finditer(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(\d{4}))?", s3):
        mo = MONTHS.get(m.group(1)[:3].lower())
        if mo:
            y = int(m.group(3)) if m.group(3) else _year_for(mo)
            out.append((y, mo, int(m.group(2))))
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?(?:\s+(\d{4}))?", s3):
        mo = MONTHS.get(m.group(2)[:3].lower())
        if mo:
            y = int(m.group(3)) if m.group(3) else _year_for(mo)
            out.append((y, mo, int(m.group(1))))
    res = []
    for y, mo, dy in out:
        try:
            dd = date(y, mo, dy)
        except ValueError:
            continue
        if dd not in res:
            res.append(dd)
    return res


def quarter_of(text, fallback_date=None):
    s = str(text or "").lower()
    q = None
    m = re.search(r"q\s*([1-4])", s) or re.search(r"\b([1-4])\s*(?:st|nd|rd|th)?\s*q", s)
    if m:
        q = int(m.group(1))
    else:
        for w, n in (("first", 1), ("second", 2), ("third", 3), ("fourth", 4)):
            if w in s:
                q = n
    if q is None:
        return None
    y = re.search(r"(20\d\d)", s)
    year = int(y.group(1)) if y else (2025 if q == 4 else 2026)
    return f"{year}-Q{q}"


def money(v):
    s = str(v or "").strip()
    if not s:
        return None
    neg = s.startswith("(") or s.startswith("-")
    try:
        x = float(re.sub(r"[^0-9.]", "", s))
    except ValueError:
        return None
    return -x if neg else x


def _col(row, *cands):
    for c in cands:
        if c in row:
            return row[c]
    for k in row:
        if any(c in k for c in cands):
            return row[k]
    return ""


# The amount column: a header naming the amount wins over one that only says "deposit" ("Deposit Amount" over
# "Deposit No"), and a header that names a date, a count or an id is never the amount ("Deposit Due Date", "Deposit #").
_NOT_AMOUNT = re.compile(r"(?:^|_)(?:due|date|dates|no|num|number|id|count|seq|quarter|qtr|941|check|checks|pay|payroll|period|covers?|covered)(?:_|$)")


def _amount_col(row):
    if "amount" in row:
        return row["amount"]
    keys = [k for k in row if not _NOT_AMOUNT.search(k)]
    for cand in ("amount", "deposit", "total", "tax", "owed", "usd"):
        for k in keys:
            if cand in k:
                return row[k]
    return ""


def load(ws, ref):
    truth = json.load(open(os.path.join(ref, "deposits.json")))
    p = _find(ws, "deposits.csv")
    if not p:
        return truth, None, "deposits.csv not found"
    got = {}
    for r in _rows(p):
        cds = tuple(sorted(dates_in(_col(r, "check_dates", "check_date", "pay_dates", "covers"))))
        if not cds:
            continue
        due = dates_in(_col(r, "due_date", "due"))
        got.setdefault(cds, []).append({"due": due[0] if due else None, "quarter": quarter_of(_col(r, "quarter", "941", "qtr")),
                                        "amount": money(_amount_col(r))})
    return truth, got, ""


def _key(t):
    return tuple(sorted(date.fromisoformat(x) for x in t["check_dates"]))


def check(ws, ref):
    truth, got, err = load(ws, ref)
    name = "deposits grouped by period and quarter"
    if got is None:
        return [{"name": name, "passed": False, "detail": err}]
    want = {_key(t): t for t in truth}
    bad = []
    for k, t in want.items():
        rows = got.get(k)
        if not rows:
            bad.append(f"no deposit covering exactly {[x.isoformat() for x in k]}")
        elif len(rows) > 1:
            bad.append(f"{len(rows)} lines cover {[x.isoformat() for x in k]}")
        elif rows[0]["quarter"] != t["quarter"]:
            bad.append(f"{[x.isoformat() for x in k]}: quarter {rows[0]['quarter']} != {t['quarter']}")
    extra = [k for k in got if k not in want]
    for k in extra:
        bad.append(f"unexpected deposit covering {[x.isoformat() for x in k]}")
    return [{"name": name, "passed": not bad, "detail": "; ".join(bad[:6]) if bad else f"{len(want)} deposits grouped right"}]


def check_due(ws, ref):
    truth, got, err = load(ws, ref)
    name = "due dates"
    if got is None:
        return [{"name": name, "passed": False, "detail": err}]
    bad = []
    for t in truth:
        rows = got.get(_key(t)) or []
        due = rows[0]["due"] if len(rows) == 1 else None
        if due is None or due.isoformat() != t["due_date"]:
            bad.append(f"{t['check_dates']}: {due.isoformat() if due else 'missing'} != {t['due_date']}")
    return [{"name": name, "passed": not bad, "detail": "; ".join(bad[:6]) if bad else f"{len(truth)} due dates right"}]


def check_amounts(ws, ref):
    truth, got, err = load(ws, ref)
    name = "deposit amounts"
    if got is None:
        return [{"name": name, "passed": False, "detail": err}]
    bad = []
    for t in truth:
        rows = got.get(_key(t)) or []
        amt = rows[0]["amount"] if len(rows) == 1 else None
        if amt is None or abs(amt - t["amount"]) > 0.01:
            bad.append(f"{t['check_dates']}: {amt} != {t['amount']:.2f}")
    return [{"name": name, "passed": not bad, "detail": "; ".join(bad[:6]) if bad else f"{len(truth)} amounts tie to the cent"}]
