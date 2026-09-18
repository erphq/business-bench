#!/usr/bin/env python3
"""promo-code-analysis: August promo code usage and revenue per code, with expired and unknown codes called out.

    python gen.py [--seed N] [--naive DIR]

Business: an independent bookshop selling online and at the till. Marketing runs a handful of codes; the till
lets staff type any code and apply a manual discount, and the website kept one summer code alive past its end.

Traps (each caught by a check, see task.yaml):
  * codes typed in mixed case with stray spaces ("summer reads15 ")      (checks: codes used; orders per code)
  * stacked codes on one order count for each code                      (checks: orders per code; revenue per code)
  * SUMMERREADS15 used after its end date: those orders do not count     (checks: orders per code; revenue per code)
  * codes that ended months ago are EXPIRED, codes not on the list UNKNOWN (check: status per code)
  * revenue is subtotal less discount, not the order total              (check: revenue per code)
  * cancelled orders count for nothing                                   (check: orders per code)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MONTH0, MONTH1 = date(2026, 8, 1), date(2026, 8, 31)
# code, campaign, type, value, start, end
CODES = [
    ("SUMMERREADS15", "Summer reading", "percent", 15, date(2026, 7, 1), date(2026, 8, 15)),
    ("BACKTOSCHOOL", "Back to school", "percent", 10, date(2026, 8, 10), date(2026, 9, 10)),
    ("FREESHIP50", "Free shipping over $50", "freeship", 0, date(2026, 1, 1), date(2026, 12, 31)),
    ("BOOKCLUB20", "Book club members", "fixed100", 20, date(2026, 8, 1), date(2026, 8, 31)),
    ("TEACHER10", "Educators", "percent", 10, date(2026, 1, 1), date(2026, 12, 31)),
    ("SPRING2026", "Spring sale", "percent", 20, date(2026, 3, 20), date(2026, 5, 31)),
    ("MOTHERSDAY", "Mother's Day", "fixed", 10, date(2026, 5, 1), date(2026, 5, 10)),
    ("HOLIDAY25", "Holiday preview", "percent", 25, date(2026, 11, 20), date(2026, 12, 24)),
]
UNKNOWN = [("SUMMERREAD15", "percent", 15), ("WELCOME5", "fixed", 5), ("BOOKCLUB2O", "fixed100", 20)]
CODE = {c[0]: c for c in CODES}
TITLES = ["The Overstory", "Braiding Sweetgrass", "Tomorrow, and Tomorrow", "Demon Copperhead", "Lessons in Chemistry",
          "The Covenant of Water", "Project Hail Mary", "Klara and the Sun", "The Lincoln Highway", "Remarkably Bright",
          "Piranesi", "North Woods", "James", "Intermezzo", "The Anxious Generation", "Atomic Habits"]


def disc_for(kind: str, value: float, sub: float) -> float:
    if kind == "percent":
        return round(sub * value / 100.0, 2)
    if kind == "fixed":
        return float(value)
    if kind == "fixed100":
        return float(value) if sub >= 100 else 0.0
    return 0.0


SPACED = {"SUMMERREADS15": "SUMMER READS15", "BACKTOSCHOOL": "BACK TO SCHOOL", "FREESHIP50": "FREE SHIP 50",
          "BOOKCLUB20": "BOOK CLUB 20", "TEACHER10": "TEACHER 10", "SPRING2026": "SPRING 2026", "MOTHERSDAY": "MOTHERS DAY",
          "SUMMERREAD15": "SUMMER READ15", "WELCOME5": "WELCOME 5", "BOOKCLUB2O": "BOOK CLUB 2O"}


def spell(r, code_: str) -> str:
    k = r.random()
    if k < 0.40: s = code_
    elif k < 0.58: s = code_.lower()
    elif k < 0.70: s = code_.capitalize()
    elif k < 0.80: s = SPACED[code_]
    elif k < 0.88: s = SPACED[code_].lower()
    else: s = SPACED[code_].title()
    if r.random() < 0.2:
        s = " " + s if r.random() < 0.5 else s + " "
    return s


def build(seed: int) -> dict:
    r = rng(seed)
    orders = []
    n = 430
    for i in range(n):
        day = MONTH0 + timedelta(days=r.randint(0, 30))
        ts = datetime(day.year, day.month, day.day, r.randint(8, 21), r.randint(0, 59))
        channel = "Online Store" if r.random() < 0.62 else "POS"
        sub = round(sum(r.uniform(12, 38) for _ in range(r.choice([1, 1, 2, 2, 3, 4]))), 2)
        ship = 0.0 if channel == "POS" else (5.99 if sub < 50 else 7.99)
        codes = []
        k = r.random()
        valid_now = [c for c in CODES if c[4] <= day <= c[5] and (c[2] != "freeship" or (sub >= 50 and channel == "Online Store"))]
        if k < 0.34 and valid_now:
            codes = [r.choice(valid_now)[0]]
        elif k < 0.40 and channel == "Online Store" and sub >= 50:
            other = [c for c in valid_now if c[2] == "percent"]
            codes = ["FREESHIP50"] + ([r.choice(other)[0]] if other else [])
        orders.append({"id": f"WS-{58210 + i}", "ts": ts, "day": day, "channel": channel, "sub": sub, "ship": ship,
                       "codes": codes, "status": "completed"})
    # SUMMERREADS15 kept working online for a week after it ended
    late = [o for o in orders if date(2026, 8, 16) <= o["day"] <= date(2026, 8, 23) and o["channel"] == "Online Store" and not o["codes"]]
    for o in r.sample(late, 6):
        o["codes"] = ["SUMMERREADS15"]
    # expired codes typed at the till, one online
    plain = [o for o in orders if not o["codes"]]
    r.shuffle(plain)
    for o in plain[:4]:
        o["codes"] = ["SPRING2026"]
    for o in plain[4:6]:
        o["codes"] = ["MOTHERSDAY"]; o["channel"] = "POS"; o["ship"] = 0.0
    for o, (u, _, _) in zip(plain[6:12], [UNKNOWN[0], UNKNOWN[0], UNKNOWN[1], UNKNOWN[1], UNKNOWN[1], UNKNOWN[2]]):
        o["codes"] = [u]; o["channel"] = "POS"; o["ship"] = 0.0
    # stacked on the till: TEACHER10 with BACKTOSCHOOL
    for o in plain[12:15]:
        if o["day"] >= date(2026, 8, 10):
            o["codes"] = ["BACKTOSCHOOL", "TEACHER10"]
    # book club orders need a $100 basket
    for o in orders:
        if "BOOKCLUB20" in o["codes"] and o["sub"] < 100:
            o["sub"] = round(o["sub"] + 100, 2)
            o["ship"] = 0.0 if o["channel"] == "POS" else 7.99
    # discounts, shipping, tax, total
    unk = {u[0]: u for u in UNKNOWN}
    for o in orders:
        d_ = 0.0
        for c in o["codes"]:
            if c in CODE:
                kind, val = CODE[c][2], CODE[c][3]
            else:
                kind, val = unk[c][1], unk[c][2]
            if kind == "freeship" and o["sub"] >= 50:
                o["ship"] = 0.0
            d_ += disc_for(kind, val, o["sub"])
        o["disc"] = round(d_, 2)
        o["tax"] = round((o["sub"] - o["disc"]) * 0.0725, 2)
        o["total"] = round(o["sub"] - o["disc"] + o["ship"] + o["tax"], 2)
    # cancelled orders, some with codes
    coded = [o for o in orders if o["codes"]]
    for o in r.sample(coded, 5) + r.sample([o for o in orders if not o["codes"]], 4):
        o["status"] = "cancelled"
    orders.sort(key=lambda z: z["ts"])
    for i, o in enumerate(orders):
        o["id"] = f"WS-{58210 + i}"
    for o in orders:
        o["typed"] = ", ".join(spell(r, c) for c in o["codes"]) if o["codes"] else ""
        if len(o["codes"]) == 2 and r.random() < 0.5:
            o["typed"] = o["typed"].replace(", ", ",")

    # ---- truth ----
    agg = {}
    for o in orders:
        if o["status"] == "cancelled":
            continue
        for c in o["codes"]:
            if c in CODE:
                _, _, _, _, start, end = CODE[c]
                if end < MONTH0 or start > MONTH1:
                    status = "EXPIRED" if end < MONTH0 else "NOT STARTED"
                elif not (start <= o["day"] <= end):
                    continue   # used outside its window this month: does not count
                else:
                    status = "OK"
            else:
                status = "UNKNOWN"
            a = agg.setdefault(c, {"code": c, "orders": 0, "revenue": 0.0, "status": status})
            a["orders"] += 1
            a["revenue"] = round(a["revenue"] + o["sub"] - o["disc"], 2)
    return {"orders": orders, "agg": agg}


def variants(d: dict) -> dict:
    """Per-code (orders, revenue) under naive readings."""
    out = {}
    for name in ("total_revenue", "no_window", "first_code_only", "keep_cancelled"):
        agg = {}
        for o in d["orders"]:
            if o["status"] == "cancelled" and name != "keep_cancelled":
                continue
            codes = o["codes"][:1] if name == "first_code_only" else o["codes"]
            for c in codes:
                if c in CODE and name != "no_window":
                    _, _, _, _, start, end = CODE[c]
                    if MONTH0 <= end and start <= MONTH1 and not (start <= o["day"] <= end):
                        continue
                a = agg.setdefault(c, [0, 0.0])
                a[0] += 1
                a[1] += o["total"] if name == "total_revenue" else o["sub"] - o["disc"]
        out[name] = agg
    return out


def acceptable(d: dict) -> bool:
    agg, v = d["agg"], variants(d)
    if any(a["status"] == "NOT STARTED" for a in agg.values()):
        return False
    need = ["SUMMERREADS15", "FREESHIP50", "TEACHER10", "BACKTOSCHOOL", "SPRING2026", "MOTHERSDAY", "SUMMERREAD15", "WELCOME5"]
    if any(c not in agg for c in need):
        return False
    if v["no_window"]["SUMMERREADS15"][0] == agg["SUMMERREADS15"]["orders"]:
        return False
    if v["first_code_only"].get("TEACHER10", [0])[0] == agg["TEACHER10"]["orders"]:
        return False
    if v["keep_cancelled"]["SUMMERREADS15"][0] == agg["SUMMERREADS15"]["orders"] and \
       v["keep_cancelled"]["FREESHIP50"][0] == agg["FREESHIP50"]["orders"]:
        return False
    for c in ("SUMMERREADS15", "FREESHIP50", "BACKTOSCHOOL"):
        if abs(v["total_revenue"][c][1] - agg[c]["revenue"]) < 0.02 * agg[c]["revenue"]:
            return False
    return True


HEADER = ["code", "orders", "revenue", "status"]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        # split on commas, upper-case and strip, count every order, revenue = order total, everything OK
        os.makedirs(naive_dir, exist_ok=True)
        agg = {}
        for o in d["orders"]:
            for c in [x.strip().upper() for x in o["typed"].split(",") if x.strip()]:
                a = agg.setdefault(c, [0, 0.0])
                a[0] += 1; a[1] += o["total"]
        write_csv(os.path.join(naive_dir, "promo_summary.csv"), HEADER,
                  [[c, a[0], f"{a[1]:.2f}", "OK"] for c, a in sorted(agg.items())])
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 11)
    rows = []
    for o in sorted(d["orders"], key=lambda z: z["ts"]):
        rows.append([o["id"], o["ts"].strftime("%Y-%m-%d %H:%M"), o["channel"], o["status"], f"{o['sub']:.2f}",
                     f"{o['disc']:.2f}", f"{o['ship']:.2f}", f"{o['tax']:.2f}", f"{o['total']:.2f}", o["typed"]])
    write_csv(os.path.join(ws, "orders_2026-08.csv"),
              ["Order", "Created", "Channel", "Status", "Subtotal", "Discount", "Shipping", "Tax", "Total", "Discount codes"],
              rows, crlf=True)
    write_xlsx(os.path.join(ws, "promo_codes_2026.xlsx"), {"Codes": {
        "merged_title": "Promo codes 2026 (marketing)",
        "header": ["Code", "Campaign", "Discount", "Starts", "Ends", "Notes"],
        "rows": [[c, camp, {"percent": f"{val}% off", "fixed": f"${val} off", "fixed100": f"${val} off $100+",
                            "freeship": "Free shipping $50+"}[kind], start, end,
                  {"SUMMERREADS15": "website + till", "HOLIDAY25": "not live yet"}.get(c, "")]
                 for c, camp, kind, val, start, end in CODES],
        "widths": {"A": 16, "B": 24, "C": 20, "D": 12, "E": 12, "F": 18}}}, creator="Marketing")
    write_email_thread(os.path.join(ws, "email_from_hannah.txt"), [
        {"from": "Hannah Brooks <hannah@wrensparrowbooks.com>", "to": "you", "date": "Tue, 2 Sep 2026 09:40",
         "subject": "August promo codes",
         "body": ("Could you pull together how our promo codes did in August? For each code: how many orders used it "
                  "and how much revenue those orders brought in. By revenue I mean what we took for the books - "
                  "subtotal less the discount. Shipping and tax aren't ours.\n\n"
                  "Things to know:\n"
                  "- Codes aren't case sensitive and the till ignores spaces, so 'summer reads15' is SUMMERREADS15. "
                  "Please report the codes in capitals as they appear on marketing's list.\n"
                  "- People can stack codes. If an order used two codes, count it under both.\n"
                  "- Cancelled orders don't count.\n"
                  "- SUMMERREADS15 ended on 15 August (the end date is the last good day) but Tom didn't switch it off on "
                  "the website for another week. Orders that used it after the 15th don't count for the campaign.\n"
                  "- The till lets staff type anything. If a code is on the list but finished before August, mark it "
                  "EXPIRED. If it isn't on the list at all, mark it UNKNOWN - I want to see those with their orders "
                  "and revenue so I can talk to the team. Everything else is OK.\n\n"
                  "Save it as promo_summary.csv with code, orders, revenue, status - one row per code used in August.")}])

    ref_rows = [[a["code"], a["orders"], f"{a['revenue']:.2f}", a["status"]] for a in sorted(d["agg"].values(), key=lambda z: z["code"])]
    write_csv(os.path.join(ref, "promo_summary.csv"), HEADER, ref_rows)
    write_csv(os.path.join(sol, "promo_summary.csv"), HEADER, ref_rows)
    write_json(os.path.join(ref, "notes.json"), {"variants": {k: {c: [n, round(v_, 2)] for c, (n, v_) in vv.items()}
                                                              for k, vv in variants(d).items()}})
    must = ["SUMMERREADS15", "FREESHIP50", "TEACHER10", "SPRING2026", "SUMMERREAD15"]
    write_task_yaml(HERE, {
        "id": "promo-code-analysis", "track": "desk", "category": "spreadsheet",
        "title": "How the August promo codes did",
        "ask": ("Hannah wants to know how each promo code did in August, including any codes that shouldn't have "
                "gone through. Use the order export and marketing's code list and save promo_summary.csv; her email "
                "has the details.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "codes are typed in mixed case with spaces inside and around them ('summer reads15', ' Freeship50'); "
            "grouping the raw text splits one code into several rows (checks: codes used; orders per code)",
            "online orders stack FREESHIP50 with a percent code and the till stacks BACKTOSCHOOL with TEACHER10, "
            "sometimes with no space after the comma; each order counts under both codes "
            "(checks: orders per code; revenue per code)",
            "SUMMERREADS15 kept working on the website for a week after its 15 August end date; the orders from "
            "16 August on must not count toward it (checks: orders per code; revenue per code)",
            "SPRING2026 and MOTHERSDAY are on marketing's list but ended in May, so they are EXPIRED; SUMMERREAD15, "
            "WELCOME5 and BOOKCLUB2O (letter O) are not on the list at all and are UNKNOWN (checks: status per code; codes used)",
            "revenue is subtotal less discount; the Total column adds shipping and tax (check: revenue per code)",
            "five cancelled orders carry codes and count for nothing (check: orders per code)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "promo_summary.csv", "columns": HEADER},
            {"type": "csv_set_equal", "name": "codes used", "path": "promo_summary.csv", "column": "code",
             "ref": "promo_summary.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "promo_summary.csv", "equals_ref": "promo_summary.csv"},
            {"type": "csv_values_match", "name": "orders per code", "path": "promo_summary.csv", "ref": "promo_summary.csv",
             "key": "code", "columns": ["orders"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0, "must_match_keys": must},
            {"type": "csv_values_match", "name": "revenue per code", "path": "promo_summary.csv", "ref": "promo_summary.csv",
             "key": "code", "columns": ["revenue"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": must},
            {"type": "csv_values_match", "name": "status per code", "path": "promo_summary.csv", "ref": "promo_summary.csv",
             "key": "code", "columns": ["status"], "min_accuracy": 1.0},
        ],
    })
    print(f"seed={seed}", ref_rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(1000):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
