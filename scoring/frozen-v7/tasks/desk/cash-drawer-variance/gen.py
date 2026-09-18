#!/usr/bin/env python3
"""cash-drawer-variance: a barbershop's August close-of-day reports against the credit union's deposits.

    python gen.py [--seed N] [--naive DIR]

Business: Copper Comb Barber Co. runs two cash drawers - the front desk for haircuts and a retail counter for
pomade and razors - and is closed on Mondays. Whoever closes pays the day's card tips to the barbers in cash out of
the front drawer, bags both drawers' cash together and drops the bag at the credit union the next morning the shop
is open. The owner wants the cash that should have gone in the bag against what the bank actually credited, per day.

Traps (each caught by a check, see task.yaml):
  * each bag is deposited the next open day, so Sunday's takings reach the bank on Tuesday and the 30 August bag in
    September; matching deposits to the same date shifts every day                    (checks: deposited per day; variance)
  * two drawers per day go in one bag; either drawer alone is wrong                     (check: expected deposit per day)
  * card tips come out of the front drawer in cash; cash tips declared never touch it   (check: expected deposit per day)
  * the retail drawer's Z report was reprinted one day and the reprint repeats the row  (check: expected deposit per day)
  * a bank deposit correction a few days later belongs to the bag it corrects           (checks: deposited per day; variance)
  * the July 31 bag lands on 1 August and card settlements sit in the same export        (check: deposited per day)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

D = Decimal
PAIDOUT_WHY = ["towel service", "coffee and creamer", "window cleaner", "hot towel cabinet part", "barbicide refill", "stamps"]


def cents(r, lo, hi) -> Decimal:
    return D(r.randint(int(lo * 100), int(hi * 100))) / 100


def open_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() != 0:          # closed Mondays
            out.append(d)
        d += timedelta(days=1)
    return out


def next_open(d: date) -> date:
    n = d + timedelta(days=1)
    while n.weekday() == 0:
        n += timedelta(days=1)
    return n


def build(seed: int) -> dict:
    r = rng(seed)
    days = open_days(date(2026, 8, 1), date(2026, 8, 31))
    z = r.randint(4100, 4600)
    reports, day_rows = [], []
    short_days = set(r.sample(days[2:-2], 4))
    corr_day = r.choice([d for d in days[3:-4] if d not in short_days])
    reprint_day = r.choice([d for d in days if d not in short_days and d != corr_day])
    short_vals = dict(zip(sorted(short_days), r.sample([D("-5.00"), D("-10.00"), D("3.50"), D("-12.25"), D("1.75"), D("-40.00"), D("-7.60")], 4)))
    corr_val = r.choice([D("-20.00"), D("-50.00"), D("10.00")])
    for d in days:
        weekend = d.weekday() >= 4
        front = {"cash": cents(r, 380, 760) + (cents(r, 150, 320) if weekend else 0), "refunds": D("0.00"), "paidouts": D("0.00"),
                 "card": cents(r, 900, 1900) + (cents(r, 400, 800) if weekend else 0), "card_tips": cents(r, 110, 260),
                 "cash_tips": cents(r, 40, 150), "po_note": ""}
        retail = {"cash": cents(r, 35, 190), "refunds": D("0.00"), "paidouts": D("0.00"), "card": cents(r, 120, 480),
                  "card_tips": D("0.00"), "cash_tips": D("0.00"), "po_note": ""}
        if r.random() < 0.3:
            front["paidouts"] = cents(r, 8, 46)
            front["po_note"] = r.choice(PAIDOUT_WHY)
        if r.random() < 0.18:
            retail["refunds"] = cents(r, 18, 42)
        expected = sum(x["cash"] - x["refunds"] - x["paidouts"] - x["card_tips"] for x in (front, retail))
        variance = D("0.00")
        if d in short_days:
            variance = short_vals[d]
        bag = expected + variance                       # what went in the bag
        correction = D("0.00")
        if d == corr_day:
            correction = corr_val
        deposited = bag + correction
        for name, x in (("Front desk", front), ("Retail counter", retail)):
            z += 1
            reports.append({"date": d, "drawer": name, "z": z, "x": x, "reprint": False})
        day_rows.append({"date": d, "expected": expected, "bag": bag, "correction": correction, "deposited": deposited,
                         "variance": deposited - expected, "front": front, "retail": retail, "deposit_date": next_open(d)})
    # a reprinted retail Z report
    orig = [x for x in reports if x["date"] == reprint_day and x["drawer"] == "Retail counter"][0]
    reports.insert(reports.index(orig) + 1, {"date": reprint_day, "drawer": "Retail counter", "z": orig["z"], "x": orig["x"], "reprint": True})
    return {"days": day_rows, "reports": reports, "corr_day": corr_day, "reprint_day": reprint_day, "short_days": sorted(short_days),
            "july_bag": cents(r, 520, 980), "k": r.random(), "seed": seed}


def acceptable(d: dict) -> bool:
    rows = d["days"]
    # variances visibly move under a same-date match
    exp = [x["expected"] for x in rows]
    if len(set(exp)) != len(exp):
        return False
    if not any(x["front"]["paidouts"] > 0 for x in rows):
        return False
    rp = [x for x in rows if x["date"] == d["reprint_day"]][0]
    if rp["retail"]["cash"] - rp["retail"]["refunds"] < 30:
        return False
    corr = [x for x in rows if x["date"] == d["corr_day"]][0]
    if next_open(d["corr_day"]) in d["short_days"] or corr["date"] - timedelta(days=1) in d["short_days"]:
        return False
    return all(x["variance"] != 0 or x["date"] not in d["short_days"] for x in rows)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["date", "expected_deposit", "deposited", "variance", "note"]
    by_dep = {x["deposit_date"]: x for x in d["days"]}
    if naive_dir:
        # same-date matching, POS "cash in drawer" of both drawers with the reprint, tips ignored
        rows = []
        for x in d["days"]:
            exp = sum(rep["x"]["cash"] - rep["x"]["refunds"] - rep["x"]["paidouts"] for rep in d["reports"] if rep["date"] == x["date"])
            dep = by_dep[x["date"]]["bag"] if x["date"] in by_dep else (d["july_bag"] if x["date"] == date(2026, 8, 1) else D("0"))
            rows.append([x["date"].isoformat(), f"{exp:.2f}", f"{dep:.2f}", f"{dep - exp:.2f}", ""])
        write_csv(os.path.join(naive_dir, "drawer_variance.csv"), header, rows)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 3)

    # ---- POS close-of-day export
    zrows = []
    for rep in d["reports"]:
        x = rep["x"]
        float_amt = D("150.00")
        in_drawer = float_amt + x["cash"] - x["refunds"] - x["paidouts"]
        zrows.append([rep["date"].strftime("%a %m/%d/%Y"), rep["drawer"], f"Z{rep['z']}" + (" (reprint)" if rep["reprint"] else ""),
                      f"{float_amt:.2f}", f"{x['cash']:.2f}", f"{x['refunds']:.2f}", f"{x['paidouts']:.2f}", x["po_note"],
                      f"{x['card']:.2f}", f"{x['card_tips']:.2f}", f"{x['cash_tips']:.2f}", f"{in_drawer:.2f}"])
    write_csv(os.path.join(ws, "shearline_pos_close_of_day_2026-08.csv"),
              ["Business Day", "Drawer", "Z Report", "Starting Float", "Cash Sales", "Cash Refunds", "Paid Outs", "Paid Out Memo",
               "Card Sales (incl tips)", "Card Tips", "Cash Tips Declared", "Cash Expected In Drawer"], zrows,
              preamble=["ShearLine POS - Close of day (Z) reports", "Location: Copper Comb Barber Co. | 08/01/2026 - 08/31/2026"], crlf=True)

    # ---- credit union export
    bank = []
    bank.append([date(2026, 8, 1), "ATM DEPOSIT CU BRANCH 0412", "", d["july_bag"]])
    for x in d["days"]:
        bank.append([x["deposit_date"], "ATM DEPOSIT CU BRANCH 0412", "", x["bag"]])
        if x["correction"]:
            when = x["deposit_date"] + timedelta(days=r.randint(3, 5))
            memo = f"DEPOSIT ADJUSTMENT - ATM DEP {x['deposit_date'].strftime('%m/%d/%y')} COUNT DIFFERENCE"
            if x["correction"] < 0:
                bank.append([when, memo, -x["correction"], ""])
            else:
                bank.append([when, memo, "", x["correction"]])
    settle_day = date(2026, 8, 1)
    while settle_day <= date(2026, 9, 4):
        if settle_day.weekday() < 5:
            bank.append([settle_day, "SHEARLINE PAYMENTS SETTLEMENT", "", cents(r, 1400, 3900)])
        settle_day += timedelta(days=1)
    for when, memo, lo, hi in ((date(2026, 8, 3), "ACH DEBIT RIVERSIDE PROPERTIES RENT", 3200, 3200), (date(2026, 8, 14), "ACH DEBIT GUSTO PAYROLL", 4800, 6900),
                               (date(2026, 8, 28), "ACH DEBIT GUSTO PAYROLL", 4800, 6900), (date(2026, 8, 20), "POS PURCHASE BARBER DEPOT", 180, 460),
                               (date(2026, 8, 7), "ACH DEBIT PACIFIC GAS & ELECTRIC", 210, 390)):
        bank.append([when, memo, cents(r, lo, hi), ""])
    bank = [b for b in bank if b[0] <= date(2026, 9, 4)]
    bank.sort(key=lambda b: (b[0], b[1]))
    bal = cents(r, 8000, 14000)
    rows = []
    for when, memo, debit, credit in bank:
        bal = bal - (debit or 0) + (credit or 0)
        rows.append([when.strftime("%m/%d/%Y"), memo, f"{debit:,.2f}" if debit != "" else "", f"{credit:,.2f}" if credit != "" else "", f"{bal:,.2f}"])
    write_csv(os.path.join(ws, "summit_cu_checking_2026-08-01_to_2026-09-04.csv"), ["Date", "Description", "Withdrawal", "Deposit", "Balance"],
              rows, preamble=["Summit Community Credit Union", "Business Checking ****6630", ""], bom=True)

    owner = "Marcus Ruiz"
    write_text(os.path.join(ws, "note_from_marcus.txt"),
               "Cash drawer check - August\n\n"
               "I think we are losing cash somewhere and I want to see it day by day before I talk to the closers.\n\n"
               "How closing works here:\n"
               "- Two drawers: the front desk (haircuts) and the retail counter (products). Both start the day with a $150 float that\n"
               "  stays in the drawer overnight.\n"
               "- At close, whoever is on pays the barbers their card tips in cash out of the front drawer. Cash tips go straight into\n"
               "  the barbers' pockets and never touch a drawer - the POS only records them for payroll.\n"
               "- Paid outs (towels, coffee and so on) come out of the drawer during the day and the POS already knows about them.\n"
               "- Then both drawers' cash, less the floats, goes in ONE bag, and the bag goes in the night drop at Summit the next\n"
               "  morning we are open. We are closed Mondays, so Sunday's bag goes in on Tuesday.\n"
               "- Card sales settle to the account by themselves, so ignore those.\n"
               "- Once in a while the credit union counts a bag differently and posts an adjustment a few days later that names the\n"
               "  deposit. That is still that bag.\n\n"
               "What I want back is drawer_variance.csv, one row for every day we were open in August: the date (like 2026-08-04),\n"
               "what should have gone in the bag (expected_deposit), what the bank actually credited for that day's bag after any\n"
               "adjustment (deposited), the variance (deposited minus expected, so short is negative), and a note on any day that is\n"
               "off saying what you found.\n\n"
               "- Marcus\n")

    def why(x):
        if x["correction"] and x["variance"] == x["correction"]:
            return f"Bank adjusted the {x['deposit_date'].strftime('%m/%d')} deposit by {x['correction']:+.2f} after counting the bag"
        if x["variance"] < 0:
            return "Bag short against the close-of-day reports"
        if x["variance"] > 0:
            return "Bag over against the close-of-day reports"
        return ""
    rows = [[x["date"].isoformat(), f"{x['expected']:.2f}", f"{x['deposited']:.2f}", f"{x['variance']:.2f}", why(x)] for x in d["days"]]
    write_csv(os.path.join(ref, "drawer_variance.csv"), header, rows)
    write_csv(os.path.join(sol, "drawer_variance.csv"), header, rows)
    sundays = [x["date"].isoformat() for x in d["days"] if x["date"].weekday() == 6]
    write_json(os.path.join(ref, "notes.json"), {"correction_day": d["corr_day"].isoformat(), "reprint_day": d["reprint_day"].isoformat(),
                                                  "short_days": [x.isoformat() for x in d["short_days"]], "sundays": sundays})
    corr = d["corr_day"].isoformat()
    last = d["days"][-1]["date"].isoformat()
    paid_out_day = [x["date"].isoformat() for x in d["days"] if x["front"]["paidouts"] > 0][0]
    write_task_yaml(HERE, {
        "id": "cash-drawer-variance", "track": "desk", "category": "bookkeeping",
        "title": "August cash drawer variance by day",
        "ask": "Marcus wants to see where cash is going missing. Compare August's close-of-day reports with the bank deposits, day by day, following his note. Save it as drawer_variance.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "each bag goes in the night drop the next morning the shop is open, so a deposit dated Tuesday is Sunday's bag and the "
            f"{last} bag reaches the bank in September; matching deposits to the business day's own date shifts every row "
            "(checks: deposited per day; variance per day)",
            "both drawers go in one bag, and the POS 'Cash Expected In Drawer' includes the $150 float and ignores the card tips paid "
            "out of the front drawer at close (check: expected deposit per day)",
            "cash tips declared never enter a drawer; subtracting them as well as the card tips understates the bag every day "
            "(check: expected deposit per day)",
            f"the retail counter's Z report for {d['reprint_day'].isoformat()} was reprinted and the reprint repeats the row with the "
            "same Z number (check: expected deposit per day)",
            f"the credit union posted a count-difference adjustment several days after the deposit of the {corr} bag; it belongs to "
            f"{corr}, not to the day it posted (checks: deposited per day; variance per day)",
            "the bank export opens with July 31's bag on 1 August, carries daily card settlements, rent and payroll in the same columns, "
            "and has a preamble and a BOM; the POS export writes days as 'Sat 08/01/2026' (check: deposited per day)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "drawer_variance.csv", "columns": header[:4]},
            {"type": "csv_set_equal", "name": "every open day", "path": "drawer_variance.csv", "column": "date", "ref": "drawer_variance.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "drawer_variance.csv", "equals_ref": "drawer_variance.csv"},
            {"type": "csv_values_match", "name": "expected deposit per day", "path": "drawer_variance.csv", "ref": "drawer_variance.csv",
             "key": "date", "columns": ["expected_deposit"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [d["reprint_day"].isoformat(), paid_out_day]},
            {"type": "csv_values_match", "name": "deposited per day", "path": "drawer_variance.csv", "ref": "drawer_variance.csv",
             "key": "date", "columns": ["deposited"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": sorted({corr, last, sundays[0]})},
            {"type": "csv_values_match", "name": "variance per day", "path": "drawer_variance.csv", "ref": "drawer_variance.csv",
             "key": "date", "columns": ["variance"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": sorted({corr} | {x.isoformat() for x in d["short_days"]})},
        ],
    })
    print(f"seed={seed} days={len(d['days'])} corr={corr} reprint={d['reprint_day']} shorts={[str(x) for x in d['short_days']]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
