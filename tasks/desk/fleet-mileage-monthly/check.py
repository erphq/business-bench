"""Miles per van per month, with the missing month left empty and flagged.

The deliverable is one line per van per month. Vans are matched on their number (VAN-04, Van 4, V04), months
on any common spelling (2026-04, 2026-04-01, Apr 2026, April 2026, 04/2026). Every van-month with readings
must carry the reference miles within one mile; the month with no readings must have empty miles (not 0)
and something in the flag column. Expected values come from reference/mileage.csv.
"""
import csv
import glob
import io
import os
import re

MONTH_NAMES = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


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
        year = year if len(year) == 4 else "20" + year
        return f"{year}-{MONTH_NAMES[m.group(1)]:02d}"
    return None


def _van(v):
    m = re.search(r"(\d+)", str(v))
    return int(m.group(1)) if m else None


def _col(header, *names):
    norm = [re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_") for h in header]
    for n in names:
        for i, h in enumerate(norm):
            if h == n:
                return i
    for n in names:
        for i, h in enumerate(norm):
            if n in h:
                return i
    return None


def _num(v):
    s = re.sub(r"[,\s]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None


def check(ws, ref):
    name = "miles per van and month"
    hits = sorted(glob.glob(os.path.join(ws, "mileage.csv"))) or sorted(glob.glob(os.path.join(ws, "**", "mileage.csv"), recursive=True))
    if not hits:
        return [{"name": name, "passed": False, "detail": "mileage.csv not found"}]
    try:
        raw = open(hits[0], "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        rows = list(csv.reader(io.StringIO(raw)))
        header, body = rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"mileage.csv unreadable: {e}"}]
    iv, im, imi, ifl = _col(header, "vehicle", "van", "unit"), _col(header, "month", "period"), _col(header, "miles", "mileage"), \
        _col(header, "flag", "flags", "note", "notes", "comment")
    if None in (iv, im, imi):
        return [{"name": name, "passed": False, "detail": f"need vehicle, month and miles columns; header {header}"}]
    got = {}
    for r in body:
        cell = lambda i: r[i] if i is not None and i < len(r) else ""
        key = (_van(cell(iv)), _month(cell(im)))
        got[key] = (cell(imi).strip(), cell(ifl).strip())
    with open(os.path.join(ref, "mileage.csv"), encoding="utf-8") as f:
        truth = list(csv.DictReader(f))
    wrong, gap_bad = [], []
    for t in truth:
        key = (_van(t["vehicle"]), t["month"])
        g = got.get(key)
        if t["miles"] == "":
            if g is None or g[0] != "" or not g[1]:
                gap_bad.append(f"{t['vehicle']} {t['month']}: expected empty miles and a flag, got {g}")
            continue
        want = float(t["miles"])
        n = _num(g[0]) if g else None
        if n is None or abs(n - want) > 1.0:
            wrong.append(f"{t['vehicle']} {t['month']}: expected {want:.0f}, got {g[0] if g else 'no row'}")
    ok = not wrong and not gap_bad
    detail = (f"{len(wrong)} van-months wrong: {wrong[:6]}; " if wrong else "") + ("; ".join(gap_bad) if gap_bad else "")
    return [{"name": name, "passed": ok, "detail": detail or f"{len(truth)} van-months right, missing month left empty and flagged"}]
