"""One row per tutor and month.

The row count must equal the reference (one row per tutor-month with sessions). Priyanka's note asks for "one line
per tutor per month for March, April and May", so a tutor who had no sessions in one of those months (Maren Holt
started in April) may also carry a zero line for it. Such a row counts only when its tutor is a reference tutor, its
month is one of the reference months, that tutor-month is absent from the reference, booked and no-shows are 0 (or
blank) and the rate is 0, blank or a non-numeric marker such as N/A. At most one zero row per missing tutor-month is
set aside; every other row counts toward the total, so a duplicate row, a stray month or a zero row carrying real
figures still fails. A file whose raw count already equals the reference passes exactly as under the old row count.
Expected values come from reference/no_show_rates.csv.
"""
import csv
import fnmatch
import glob
import io
import os
import re

FILE = "no_show_rates.csv"
MONTH_NAMES = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _find(ws):
    hits = sorted(glob.glob(os.path.join(ws, FILE))) or sorted(glob.glob(os.path.join(ws, "**", FILE), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    if not hits:
        for base, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if d not in (".proto", ".codex", "node_modules", ".git")]
            hits += [os.path.join(base, f) for f in files if fnmatch.fnmatch(f.lower(), FILE)]
        hits.sort()
    return hits[0] if hits else None


def _month(v):
    s = str(v).strip().lower()
    m = re.search(r"(20\d\d)[-/.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"\b(\d{1,2})[-/.](20\d\d)\b", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.search(r"\b([a-z]{3})[a-z]*\.?[\s\-']*(20\d\d|\d\d)?\b", s)
    if m and m.group(1) in MONTH_NAMES:
        year = m.group(2) or "2026"
        return f"{year if len(year) == 4 else '20' + year}-{MONTH_NAMES[m.group(1)]:02d}"
    return None


def _col(header, *names):
    norm = [re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_") for h in header]
    for n in names:
        if n in norm:
            return norm.index(n)
    for n in names:
        for i, h in enumerate(norm):
            if n in h:
                return i
    return None


def _num(v):
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*%?\s*", str(v).replace(",", ""))
    return float(m.group(1)) if m else None


def _zero_count(v):
    return str(v).strip() == "" or _num(v) == 0


def _zero_rate(v):
    n = _num(v)
    return n is None or n == 0   # blank, 0, 0%, or a marker like N/A or a dash


def check(ws, ref):
    name = "one row per tutor and month"
    p = _find(ws)
    with open(os.path.join(ref, FILE), encoding="utf-8") as f:
        truth = list(csv.DictReader(f))
    want = len(truth)
    if not p:
        return [{"name": name, "passed": False, "detail": f"{FILE} not found"}]
    try:
        raw = open(p, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\r\n", "\n").replace("\r\n", "\n")
        rows = [r for r in csv.reader(io.StringIO(raw)) if r]
        header, body = rows[0], rows[1:]
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"{FILE} unreadable: {e}"}]
    n = len(body)
    it, im = _col(header, "tutor", "provider"), _col(header, "month", "period")
    ins, ir = _col(header, "no_shows", "noshows", "no_show_count"), _col(header, "no_show_rate", "rate", "no_show_pct")
    ib = _col(header, "booked", "sessions_booked", "on_book", "sessions")
    zero_rows = []
    if None not in (it, im, ins, ir, ib) and ins != ir:
        tutors = {t["tutor"].split()[-1].lower() for t in truth}
        months = {t["month"] for t in truth}
        have = {(t["tutor"].split()[-1].lower(), t["month"]) for t in truth}
        open_cells = {(t, m) for t in tutors for m in months} - have
        for r in body:
            cell = lambda i: r[i] if i < len(r) else ""
            mon = _month(cell(im))
            last = next((t for t in tutors if re.search(r"\b" + re.escape(t) + r"\b", cell(it).lower())), None)
            if (last, mon) in open_cells and _zero_count(cell(ib)) and _zero_count(cell(ins)) and _zero_rate(cell(ir)):
                open_cells.discard((last, mon))
                zero_rows.append(f"{cell(it).strip()} {mon}")
    # a count that already equals the reference passes exactly as before; the zero rows only explain an extra line
    passed = n == want or n - len(zero_rows) == want
    detail = f"{n} rows, expected {want}" + (f" plus optional zero rows; set aside {zero_rows}" if zero_rows else "")
    return [{"name": name, "passed": passed, "detail": detail}]
