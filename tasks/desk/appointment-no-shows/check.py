"""No-shows and no-show rate for every tutor and month.

Rows are matched on the tutor's last name and on the month in any common spelling (2026-04, Apr 2026, April,
04/2026). The no-show count must equal the reference exactly, and the rate must match either as a fraction
(0.0833) or as a percentage (8.33 or "8.33%"), within 0.15 of a percentage point. Expected values come from
reference/no_show_rates.csv, so nothing here is pinned to a seed. The booked count (sessions on the book) must also
match exactly, since the winter file the owner asked to follow carries it.
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
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(%?)\s*", str(v).replace(",", ""))
    return (float(m.group(1)), bool(m.group(2))) if m else (None, False)


def check(ws, ref):
    name = "no-shows and rate per tutor and month"
    hits = sorted(glob.glob(os.path.join(ws, "no_show_rates.csv"))) or sorted(
        glob.glob(os.path.join(ws, "**", "no_show_rates.csv"), recursive=True))
    if not hits:
        return [{"name": name, "passed": False, "detail": "no_show_rates.csv not found"}]
    try:
        raw = open(hits[0], "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        rows = list(csv.reader(io.StringIO(raw)))
        header, body = rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"no_show_rates.csv unreadable: {e}"}]
    it, im = _col(header, "tutor", "provider"), _col(header, "month", "period")
    ins, ir = _col(header, "no_shows", "noshows", "no_show_count"), _col(header, "no_show_rate", "rate", "no_show_pct")
    ib = _col(header, "booked", "sessions_booked", "on_book", "sessions")
    if None in (it, im, ins, ir, ib) or ins == ir:
        return [{"name": name, "passed": False, "detail": f"need tutor, month, booked, no_shows and no_show_rate columns; header {header}"}]
    with open(os.path.join(ref, "no_show_rates.csv"), encoding="utf-8") as f:
        truth = list(csv.DictReader(f))
    got = []
    for r in body:
        cell = lambda i: r[i] if i < len(r) else ""
        got.append((cell(it).lower(), _month(cell(im)), cell(ins), cell(ir), cell(ib)))
    bad = []
    for t in truth:
        last = t["tutor"].split()[-1].lower()
        match = [g for g in got if re.search(r"\b" + re.escape(last) + r"\b", g[0]) and g[1] == t["month"]]
        if not match:
            bad.append(f"{t['tutor']} {t['month']}: no row")
            continue
        _, _, ns, rate, bk = match[0]
        want_n, want_r, want_b = int(t["no_shows"]), float(t["no_show_rate"]), int(t["booked"])
        n, _ = _num(ns)
        b, _ = _num(bk)
        rv, pct = _num(rate)
        rate_ok = rv is not None and ((abs(rv - want_r) <= 0.0015 and not pct) or abs(rv - want_r * 100) <= 0.15)
        if n is None or int(round(n)) != want_n or b is None or int(round(b)) != want_b or not rate_ok:
            bad.append(f"{t['tutor']} {t['month']}: expected {want_n} of {want_b} booked ({want_r:.2%}), got {ns!r} of {bk!r} ({rate!r})")
    return [{"name": name, "passed": not bad,
             "detail": (f"{len(bad)} of {len(truth)} wrong: " + "; ".join(bad[:6])) if bad else f"{len(truth)} tutor-months match"}]
