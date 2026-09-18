"""card-expense-coding: what each cardholder owes back.

Travel meal overage is graded per cardholder per trip day (the policy says to take it off the day's largest meal,
but any split within the day's meals is accepted); personal charges are graded per transaction; every other charge
must owe nothing. Blank employee_owes reads as 0. Figures come from reference/owes.json and reference/coded.csv.
"""
import csv
import glob
import io
import json
import os
import re


def _find(ws, name):
    hits = sorted(glob.glob(os.path.join(ws, name))) or sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    return hits[0] if hits else None


def _norm(c):
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _rows(path):
    if path.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        vals = [list(r) for r in load_workbook(path, data_only=True).active.iter_rows(values_only=True)]
        hdr, body = [_norm(h) for h in vals[0]], vals[1:]
        return [{h: ("" if v is None else str(v)) for h, v in zip(hdr, row)} for row in body]
    text = open(path, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    rd = list(csv.reader(io.StringIO(text)))
    hdr = [_norm(h) for h in rd[0]]
    return [dict(zip(hdr, row)) for row in rd[1:]]


def _num(v):
    s = str(v).strip()
    if s == "" or s == "-":
        return 0.0
    neg = s.startswith("(") or s.startswith("-")
    try:
        x = float(re.sub(r"[^0-9.]", "", s))
    except ValueError:
        return None
    return -x if neg else x


def check(ws, ref):
    name = "employee owes"
    p = _find(ws, "coded.csv")
    if not p:
        return [{"name": name, "passed": False, "detail": "coded.csv not found"}]
    try:
        rows = _rows(p)
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"unreadable: {e}"}]
    if not rows or "txn_id" not in rows[0] or "employee_owes" not in rows[0]:
        return [{"name": name, "passed": False, "detail": f"need txn_id and employee_owes columns; have {list(rows[0]) if rows else []}"}]
    got = {}
    bad = 0
    for r in rows:
        x = _num(r.get("employee_owes", ""))
        if x is None:
            bad += 1
            continue
        k = str(r["txn_id"]).strip().upper()
        got[k] = got.get(k, 0.0) + x
    owes = json.load(open(os.path.join(ref, "owes.json")))
    out = []

    wrong_days = []
    meal_ids = set()
    for day in owes["meal_days"]:
        ids = [i.upper() for i in day["txn_ids"]]
        meal_ids.update(ids)
        s = sum(got.get(i, 0.0) for i in ids)
        if abs(s - day["over"]) > 0.011:
            wrong_days.append(f"{day['cardholder']} {day['date']}: {s:.2f} (want {day['over']:.2f}, cap {day['cap']:.2f}, spent {day['spent']:.2f})")
    out.append({"name": "travel meal overage per cardholder per day", "passed": not wrong_days,
                "detail": f"{len(owes['meal_days']) - len(wrong_days)}/{len(owes['meal_days'])} trip days right" + (f"; wrong: {wrong_days}" if wrong_days else "")})

    wrong_p = [f"{i}: {got.get(i.upper(), 0.0):.2f} (want {amt:.2f})" for i, amt in sorted(owes["personal"].items()) if abs(got.get(i.upper(), 0.0) - amt) > 0.011]
    out.append({"name": "personal charges owed in full", "passed": not wrong_p,
                "detail": f"{len(owes['personal']) - len(wrong_p)}/{len(owes['personal'])} right" + (f"; wrong: {wrong_p}" if wrong_p else "")})

    others = {k: v for k, v in got.items() if k not in meal_ids and k not in {i.upper() for i in owes["personal"]} and abs(v) > 0.011}
    out.append({"name": "nothing owed on business charges", "passed": not others and bad == 0,
                "detail": ("none" if not others else f"owed on: {sorted(others)[:8]}") + (f"; {bad} unreadable amounts" if bad else "")})
    return out
