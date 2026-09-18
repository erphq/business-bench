"""Rate per order.

The combined rate is legitimately written as a fraction (0.08845) or a percent (8.845 or 8.845%). For every order
that is not exempt, the deliverable's rate must equal reference/rates_expected.csv within 0.00001 as a fraction;
orders shipped where the business does not collect must read 0 (a blank counts as 0). Exempt orders are not
graded here, since either their location rate or 0 is a fair reading.
"""
import csv
import glob
import io
import os
import re


def _norm(h):
    return re.sub(r"[^a-z0-9]+", "_", str(h).strip().lower()).strip("_")


def _rate(v):
    s = str(v).strip()
    if not s:
        return 0.0
    pct = "%" in s
    try:
        x = float(re.sub(r"[^0-9.\-]", "", s))
    except ValueError:
        return None
    return x / 100 if (pct or x > 1) else x


def check(ws, ref):
    name = "rate per order"
    hits = sorted(glob.glob(os.path.join(ws, "orders_tax.csv"))) or sorted(glob.glob(os.path.join(ws, "**", "orders_tax.csv"), recursive=True))
    if not hits:
        return [{"name": name, "passed": False, "detail": "orders_tax.csv not found"}]
    try:
        raw = open(hits[0], "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        rows = list(csv.reader(io.StringIO(raw)))
        header = [_norm(h) for h in rows[0]]
        io_, ir = header.index("order_id"), header.index("rate")
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"need order_id and rate columns: {e}"}]
    got = {}
    for r in rows[1:]:
        if len(r) > max(io_, ir):
            got[r[io_].strip().lower()] = _rate(r[ir])
    truth = list(csv.DictReader(open(os.path.join(ref, "rates_expected.csv"), encoding="utf-8")))
    wrong, graded = [], 0
    for t in truth:
        if t["graded"] != "yes":
            continue
        graded += 1
        g = got.get(t["order_id"].lower())
        if g is None or abs(g - float(t["rate_fraction"])) > 0.00001:
            wrong.append(f"{t['order_id']} got {g} want {t['rate_fraction']}")
    return [{"name": name, "passed": not wrong, "detail": f"{graded - len(wrong)}/{graded} rates right" + (f"; {wrong[:5]}" if wrong else "")}]
