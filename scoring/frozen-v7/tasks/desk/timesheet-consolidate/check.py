"""Hours per person per payroll week, keyed on (employee, week).

The table has two rows per person, so the built-in per-key check cannot key it. This reads hours.csv (or an
.xlsx saved under that name), finds the employee, week, regular, overtime and total columns by name, reads the
week as the Saturday it ends on (the Sunday it starts on is accepted too), and compares with
reference/hours.csv within 0.02 hours. Hours may be decimals or H:MM.

check.py grades total hours; check_overtime.py reuses evaluate() to grade the regular/overtime split.
"""
import csv
import glob
import io
import os
import re
from datetime import date, datetime, timedelta

TOL = 0.02
FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%Y/%m/%d", "%b %d %Y", "%B %d %Y",
           "%a %m/%d/%Y", "%A, %B %d, %Y", "%Y-%m-%d %H:%M:%S"]


def _norm(c):
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    for f in FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def _hours(v):
    s = str(v if v is not None else "").strip()
    m = re.fullmatch(r"(\d+):(\d{2})", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    try:
        return float(re.sub(r"[^0-9.\-]", "", s)) if re.search(r"\d", s) else None
    except ValueError:
        return None


def _rows(path):
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(path, data_only=True)
        grid = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
        grid = [r for r in grid if any(c not in (None, "") for c in r)]
        if not grid:
            return [], []
        return [_norm(c) for c in grid[0]], grid[1:]
    raw = open(path, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    grid = [r for r in csv.reader(io.StringIO(raw)) if any(c.strip() for c in r)]
    if not grid:
        return [], []
    return [_norm(c) for c in grid[0]], grid[1:]


def _find(cols, *patterns, exclude=()):
    for pat in patterns:
        for i, c in enumerate(cols):
            if re.search(pat, c) and not any(re.search(x, c) for x in exclude):
                return i
    return None


def load_output(ws):
    hits = sorted(glob.glob(os.path.join(ws, "hours.csv"))) or sorted(glob.glob(os.path.join(ws, "**", "hours.csv"), recursive=True))
    if not hits:
        return None, "hours.csv not found"
    cols, rows = _rows(hits[0])
    ie = _find(cols, r"^employee$", r"^employee_name$", r"^name$", r"employee", r"worker", r"name")
    iw = _find(cols, r"^week_ending$", r"week_end", r"week")
    ir = _find(cols, r"^regular", r"regular", r"^reg")
    io_ = _find(cols, r"^overtime", r"overtime", r"^ot(_|$)")
    it = _find(cols, r"^total_hours$", r"^total", r"total")
    missing = [n for n, i in (("employee", ie), ("week", iw), ("regular", ir), ("overtime", io_), ("total", it)) if i is None]
    if missing:
        return None, f"columns not found: {missing}; have {cols}"
    out = {}
    for r in rows:
        get = lambda i: r[i] if i < len(r) else None
        d = _date(get(iw))
        if d is None:
            continue
        if d.weekday() == 6:          # a week-start Sunday names the same week
            d = d + timedelta(days=6)
        key = (str(get(ie) or "").strip().lower(), d.isoformat())
        out[key] = {"regular": _hours(get(ir)), "overtime": _hours(get(io_)), "total": _hours(get(it))}
    return out, ""


def load_reference(ref):
    with open(os.path.join(ref, "hours.csv"), encoding="utf-8") as f:
        return {(r["employee"].strip().lower(), r["week_ending"]): {k: float(r[k + "_hours"]) for k in ("regular", "overtime", "total")}
                for r in csv.DictReader(f)}


def evaluate(ws, ref, fields, name):
    got, err = load_output(ws)
    if got is None:
        return [{"name": name, "passed": False, "detail": err}]
    want = load_reference(ref)
    bad = []
    for key, w in sorted(want.items()):
        g = got.get(key)
        if g is None:
            bad.append(f"{key[0]} w/e {key[1]}: no row")
            continue
        for fld in fields:
            if g[fld] is None or abs(g[fld] - w[fld]) > TOL:
                bad.append(f"{key[0]} w/e {key[1]} {fld}: got {g[fld]}, expected {w[fld]:.2f}")
    return [{"name": name, "passed": not bad, "detail": "; ".join(bad[:6]) if bad else f"{len(want)} person-weeks match"}]


def check(ws, ref):
    return evaluate(ws, ref, ["total"], "total hours per person-week")
