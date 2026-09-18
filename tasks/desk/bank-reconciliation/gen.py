#!/usr/bin/env python3
"""bank-reconciliation: August bank statement against the checking account ledger, with last month's reconciliation.

    python gen.py [--seed N] [--naive DIR]

Business: Westbrook Plumbing, a twelve-van plumbing contractor. The office manager keys checks and deposits into
the books; the bank export and the general-ledger detail for account 1010 are in the folder with July's
reconciliation, which left three checks and one deposit outstanding.

Traps (each caught by a check, see task.yaml):
  * one of July's outstanding checks still has not cleared; it is not in August's ledger at all  (checks: outstanding total; adjusted balance)
  * two of July's checks and July's deposit in transit clear in August - not bank-only items      (check: adjusted balance)
  * two receipts the books record separately went to the bank as one deposit                      (check: deposits in transit)
  * a check was keyed into the books with two digits swapped; the bank's cleared amount is right   (checks: adjusted balance; items)
  * bank fee, returned customer check, returned-item fee and interest are not in the books        (check: adjusted balance)
  * bank export has debit/credit columns and a running balance; the ledger has a beginning balance
    row and a total row                                                                            (check: adjusted balance)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

SUPPLIERS = ["Ferguson Supply", "Winnelson Co", "Pacific Pipe & Valve", "Home Depot Pro", "Coastal Water Heaters", "Metro Rooter Parts",
             "Northside Fleet Fuel", "Valley Van Upfitters", "Cascade Tool Rental", "Sierra Backflow Testing", "City Permit Office",
             "Redline Uniforms", "Apex Drain Cameras", "Bayview Plumbing Wholesale"]
CUSTOMERS = ["Redwood Property Mgmt", "Oakhurst Pediatrics", "Tamarack Brewing", "Lakeside Veterinary", "Juniper Street Cafe",
             "Valley Forge Storage", "Meridian Title", "Harbor Light Marine", "Ellington Bakeries", "Uptown Fitness"]
ACH = [("Gusto", "Payroll", "GUSTO PAYROLL {d}"), ("Harbor Trust Visa", "Card payment", "HARBOR TRUST VISA AUTOPAY"),
       ("Ally Commercial", "Van loan", "ALLY COMMERCIAL LOAN PMT"), ("State Farm", "Insurance", "STATE FARM RO 27 INS PREM"),
       ("City Water Utility", "Utilities", "CITY OF TACOMA UTIL AUTOPAY")]
START, END = date(2026, 8, 1), date(2026, 8, 31)


def c(x: float) -> float:
    return round(x + 0.0, 2)


def build(seed: int) -> dict:
    r = rng(seed)
    b0 = c(r.uniform(31000, 46000))
    # ---- July reconciliation carried in ----
    jul_oc = []
    for num, day in zip(sorted(r.sample(range(5284, 5299), 3)), sorted(r.sample(range(22, 31), 3))):
        jul_oc.append({"num": num, "date": date(2026, 7, day), "payee": r.choice(SUPPLIERS), "amount": c(r.uniform(280, 2400))})
    jul_dit = {"date": date(2026, 7, 31), "payee": "Deposit", "amount": c(r.uniform(2500, 7800))}
    g0 = c(b0 + jul_dit["amount"] - sum(x["amount"] for x in jul_oc))
    carried = jul_oc[1]              # still outstanding at 31 Aug

    # ---- August books ----
    led = []   # {date, type, num, name, memo, amount (+in/-out), bank_amount, clears: date|None, tag}
    checknum = 5300
    for d in sorted(day_in(r, START, date(2026, 8, 28), weekday_only=True) for _ in range(19)):
        checknum += r.choice([1, 1, 1, 2])
        led.append({"date": d, "type": "Check", "num": checknum, "name": r.choice(SUPPLIERS), "memo": "", "amount": -c(r.uniform(140, 3900)),
                    "tag": "check"})
    for name, memo, desc in ACH:
        times = 2 if name == "Gusto" else 1
        for k in range(times):
            d = date(2026, 8, 14) if (name == "Gusto" and k == 0) else date(2026, 8, 28) if name == "Gusto" else day_in(r, START, date(2026, 8, 27), True)
            lo, hi = {"Gusto": (14000, 19000), "Harbor Trust Visa": (1500, 6200), "Ally Commercial": (780, 1240),
                      "State Farm": (610, 1450), "City Water Utility": (180, 690)}[name]
            amt = c(r.uniform(lo, hi))
            led.append({"date": d, "type": "Expense", "num": "", "name": name, "memo": memo, "amount": -amt, "tag": "ach", "desc": desc})
    for _ in range(13):
        d = day_in(r, START, date(2026, 8, 28), weekday_only=True)
        led.append({"date": d, "type": "Deposit", "num": "", "name": r.choice(CUSTOMERS), "memo": "Customer payment", "amount": c(r.uniform(650, 9400)),
                    "tag": "deposit"})
    # two receipts the same day that went to the bank as one deposit
    split_day = date(2026, 8, 19)
    pair = [{"date": split_day, "type": "Deposit", "num": "", "name": nm, "memo": "Customer payment", "amount": c(r.uniform(900, 4200)), "tag": "batched"}
            for nm in r.sample(CUSTOMERS, 2)]
    led += pair
    # deposit in transit: made after banking hours on the 31st
    dit = {"date": END, "type": "Deposit", "num": "", "name": r.choice(CUSTOMERS), "memo": "Customer payment - night drop", "amount": c(r.uniform(2800, 8600)),
           "tag": "dit"}
    led.append(dit)
    led.sort(key=lambda x: (x["date"], x["type"], str(x["num"])))

    checks = [x for x in led if x["tag"] == "check"]
    oc_aug = sorted(r.sample(checks[-8:], 3), key=lambda x: x["num"])
    for x in oc_aug:
        x["tag"] = "oc"
    swap = r.choice([x for x in checks if x not in oc_aug and x["tag"] == "check"])
    # keyed with two digits swapped: bank amount has hundreds and thousands swapped, e.g. 1,524.00 -> books 1,254.00
    while True:
        th, hu = r.randint(1, 3), r.randint(4, 8)
        tens = r.randint(0, 99)
        bank_amt = th * 1000 + hu * 100 + tens + r.choice([0, 0.5, 0.25, 0.75])
        book_amt = hu * 1000 + th * 100 + tens + (bank_amt % 1)
        if th != hu:
            break
    # books entered the larger or smaller figure: pick the one where the books understate the payment half the time
    if r.random() < 0.5:
        swap["amount"], swap["bank_amount"] = -c(book_amt), -c(bank_amt)
    else:
        swap["amount"], swap["bank_amount"] = -c(bank_amt), -c(book_amt)
    swap["tag"] = "swap"

    # ---- bank side ----
    bank = []   # {date, desc, num, amount}
    for x in jul_oc:
        if x is not carried:
            bank.append({"date": date(2026, 8, r.randint(3, 11)), "desc": f"CHECK {x['num']}", "num": x["num"], "amount": -x["amount"], "src": "july_oc"})
    bank.append({"date": date(2026, 8, 3), "desc": "DEPOSIT", "num": "", "amount": jul_dit["amount"], "src": "july_dit"})
    for x in led:
        if x["tag"] in ("oc", "dit", "batched"):
            continue
        lag = r.randint(1, 4)
        d = x["date"] + timedelta(days=lag)
        if d > END:
            d = END
        if x["tag"] in ("check", "swap"):
            bank.append({"date": d, "desc": f"CHECK {x['num']}", "num": x["num"], "amount": x.get("bank_amount", x["amount"]), "src": "check"})
        elif x["tag"] == "ach":
            bank.append({"date": x["date"], "desc": x["desc"].format(d=x["date"].strftime("%m%d%y")), "num": "", "amount": x["amount"], "src": "ach"})
        else:
            bank.append({"date": d, "desc": r.choice(["DEPOSIT", "REMOTE DEPOSIT", "MOBILE DEPOSIT"]), "num": "", "amount": x["amount"], "src": "deposit"})
    bank.append({"date": split_day + timedelta(days=1), "desc": "DEPOSIT", "num": "", "amount": c(pair[0]["amount"] + pair[1]["amount"]), "src": "batched"})
    # a customer check deposited this month bounced
    bounced_dep = r.choice([x for x in led if x["tag"] == "deposit" and x["date"] < date(2026, 8, 20)])
    nsf = c(r.uniform(700, min(2400, bounced_dep["amount"] - 50)))
    nsf_day = bounced_dep["date"] + timedelta(days=r.randint(5, 8))
    fee = float(r.choice([35, 30, 25]))
    ret_fee = float(r.choice([12, 15]))
    interest = c(r.uniform(2.1, 9.8))
    bank_only = [
        {"date": nsf_day, "desc": f"RETURNED ITEM - NSF {bounced_dep['name'].upper()[:18]}", "num": "", "amount": -nsf, "src": "nsf", "label": "returned customer check (NSF)"},
        {"date": nsf_day, "desc": "RETURNED ITEM FEE", "num": "", "amount": -ret_fee, "src": "retfee", "label": "returned item fee"},
        {"date": END, "desc": "MONTHLY MAINTENANCE FEE", "num": "", "amount": -fee, "src": "fee", "label": "monthly service charge"},
        {"date": END, "desc": "INTEREST PAID", "num": "", "amount": interest, "src": "interest", "label": "interest earned"},
    ]
    bank += bank_only
    bank.sort(key=lambda x: (x["date"], 0 if x["amount"] > 0 else 1, x["desc"]))
    bal = b0
    for x in bank:
        bal = c(bal + x["amount"])
        x["balance"] = bal
    b1 = bal
    g1 = c(g0 + sum(x["amount"] for x in led))

    oc_total = c(sum(x["amount"] for x in oc_aug) * -1 + carried["amount"])
    dit_total = c(dit["amount"])
    swap_diff = c(swap["bank_amount"] - swap["amount"])     # negative when the bank paid more than the books show
    book_adj = c(sum(x["amount"] for x in bank_only) + swap_diff)
    adj_bank = c(b1 + dit_total - oc_total)
    adj_book = c(g1 + book_adj)
    assert abs(adj_bank - adj_book) < 0.005, (adj_bank, adj_book)
    return {"b0": b0, "g0": g0, "b1": b1, "g1": g1, "jul_oc": jul_oc, "jul_dit": jul_dit, "carried": carried, "led": led,
            "bank": bank, "bank_only": bank_only, "oc_aug": oc_aug, "dit": dit, "pair": pair, "swap": swap, "swap_diff": swap_diff,
            "oc_total": oc_total, "dit_total": dit_total, "book_adj": book_adj, "adjusted": adj_bank}


def naive_figures(d: dict) -> dict:
    """August ledger against August bank, one-to-one by amount: no carry-over, batched pair left in transit, swap ignored."""
    oc = c(-sum(x["amount"] for x in d["oc_aug"]))
    dit = c(d["dit"]["amount"] + sum(x["amount"] for x in d["pair"]))
    return {"oc": oc, "dit": dit, "adj_bank": c(d["b1"] + dit - oc)}


def acceptable(d: dict) -> bool:
    n = naive_figures(d)
    pins = [d["oc_total"], d["dit_total"], d["adjusted"]]
    if abs(n["oc"] - d["oc_total"]) < 5 or abs(n["dit"] - d["dit_total"]) < 5 or abs(n["adj_bank"] - d["adjusted"]) < 5:
        return False
    if len({round(p) for p in pins}) < 3:
        return False
    if abs(d["swap_diff"]) < 100:
        return False
    # no pinned figure may already be sitting in the raw inputs
    raw = {abs(x["amount"]) for x in d["led"]} | {abs(x["amount"]) for x in d["bank"]} | {x["balance"] for x in d["bank"]} | \
          {d["b0"], d["g0"], d["b1"], d["g1"], d["jul_dit"]["amount"]} | {x["amount"] for x in d["jul_oc"]}
    if any(abs(p - q) <= 0.011 for p in (d["oc_total"], d["adjusted"]) for q in raw):
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def rec_workbook(d: dict, path: str, naive: bool = False) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    s = wb.active
    s.title = "Reconciliation"
    oc_items = [(x["num"], x["date"], x["name"], -x["amount"]) for x in d["oc_aug"]]
    if not naive:
        oc_items = [(d["carried"]["num"], d["carried"]["date"], d["carried"]["payee"], d["carried"]["amount"])] + oc_items
    dit_items = [(d["dit"]["date"], d["dit"]["name"], d["dit"]["amount"])]
    if naive:
        dit_items += [(x["date"], x["name"], x["amount"]) for x in d["pair"]]
    o = wb.create_sheet("Outstanding items")
    o.append(["Outstanding checks"]); o["A1"].font = Font(bold=True)
    o.append(["Check no", "Date written", "Payee", "Amount"])
    for num, dt, payee, amt in oc_items:
        o.append([num, dt, payee, amt])
    oc_first, oc_last = 3, 2 + len(oc_items)
    o.append(["Total outstanding checks", None, None, f"=SUM(D{oc_first}:D{oc_last})"])
    oc_total_row = oc_last + 1
    o.append([])
    o.append(["Deposits in transit"]); o.cell(row=o.max_row, column=1).font = Font(bold=True)
    o.append(["Date", "Received from", "", "Amount"])
    dit_first = o.max_row + 1
    for dt, nm, amt in dit_items:
        o.append([dt, nm, None, amt])
    dit_last = o.max_row
    o.append(["Total deposits in transit", None, None, f"=SUM(D{dit_first}:D{dit_last})"])
    dit_total_row = o.max_row

    rows = [
        ["Westbrook Plumbing - bank reconciliation, checking 1010, 31 August 2026"],
        [],
        ["Balance per bank statement, 31 Aug 2026", d["b1"]],
        ["Add: deposits in transit", f"='Outstanding items'!D{dit_total_row}"],
        ["Less: outstanding checks", f"='Outstanding items'!D{oc_total_row}"],
        ["Adjusted bank balance", "=B3+B4-B5"],
        [],
        ["Balance per books, 31 Aug 2026", d["g1"]],
    ]
    adj = [] if naive else [[f"Less: {x['label']}", -x["amount"]] if x["amount"] < 0 else [f"Add: {x['label']}", x["amount"]] for x in d["bank_only"]]
    if not naive:
        sw = d["swap"]
        adj.append([f"Check {sw['num']} keyed as {-sw['amount']:,.2f}, cleared at {-sw['bank_amount']:,.2f}: correction", d["swap_diff"]])
    start = len(rows) + 1
    for a in adj:
        rows.append(a)
    end = len(rows)
    if adj:
        signs = []
        for i, a in enumerate(adj, start=start):
            if a[0].startswith("Less"):
                signs.append(f"-B{i}")
            else:
                signs.append(f"+B{i}")
        rows.append(["Adjusted book balance", "=B8" + "".join(signs)])
    else:
        rows.append(["Adjusted book balance", "=B8"])
    adj_book_row = len(rows)
    rows.append([])
    rows.append(["Difference (should be zero)", f"=ROUND(B6-B{adj_book_row},2)"])
    for rr in rows:
        s.append(rr)
    s["A1"].font = Font(bold=True)
    s.column_dimensions["A"].width = 58
    s.column_dimensions["B"].width = 16

    m = wb.create_sheet("Matched")
    m.append(["Book date", "Type", "Num", "Name", "Book amount", "Bank date", "Bank description", "Bank amount"])
    bank_left = list(d["bank"])
    for x in d["led"]:
        if x["tag"] in ("oc", "dit", "batched") and not (x["tag"] == "batched"):
            continue
        if x["tag"] == "batched":
            b = next(b for b in bank_left if b["src"] == "batched")
        elif x["tag"] in ("check", "swap"):
            b = next(b for b in bank_left if b["num"] == x["num"])
        else:
            b = next(b for b in bank_left if b["src"] in ("ach", "deposit") and abs(b["amount"] - x["amount"]) < 0.005)
        if x["tag"] != "batched":
            bank_left.remove(b)
        m.append([x["date"], x["type"], x["num"], x["name"], x["amount"], b["date"], b["desc"], b.get("amount") if x["tag"] != "batched" else b["amount"]])
    for b in bank_left:
        if b["src"] in ("july_oc", "july_dit"):
            m.append(["July reconciliation", "Check" if b["src"] == "july_oc" else "Deposit", b["num"], "cleared from July's outstanding list",
                      b["amount"], b["date"], b["desc"], b["amount"]])
    for sh in (m, o):
        for col, w in zip("ABCDEFGH", (14, 12, 8, 26, 14, 12, 34, 14)):
            sh.column_dimensions[col].width = w
        for row in sh.iter_rows():
            for cell in row:
                if isinstance(cell.value, date):
                    cell.number_format = "yyyy-mm-dd"
    wb.move_sheet("Reconciliation", offset=-2)
    from datetime import datetime as _dt
    wb.properties.created = _dt(2026, 1, 15, 9, 0, 0); wb.properties.modified = _dt(2026, 1, 15, 9, 0, 0)
    wb.properties.creator = "reference"; wb.properties.lastModifiedBy = "reference"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    freeze_zip(path)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        rec_workbook(d, os.path.join(naive_dir, "reconciliation.xlsx"), naive=True)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 31)

    # ---- workspace: bank export ----
    brows = []
    for x in d["bank"]:
        debit = money_str(-x["amount"], 0) if x["amount"] < 0 else ""
        credit = money_str(x["amount"], 0) if x["amount"] > 0 else ""
        brows.append([date_variant(x["date"], 1), x["desc"], x["num"], debit, credit, money_str(x["balance"], 0)])
    write_csv(os.path.join(ws, "harbor_trust_checking_2026-08.csv"), ["Posted Date", "Description", "Check Number", "Debit", "Credit", "Balance"],
              brows + [["", "Ending balance", "", "", "", money_str(d["b1"], 0)]],
              preamble=["Harbor Trust - Business Checking ****4471", "Westbrook Plumbing LLC",
                        f"Statement period 08/01/2026 - 08/31/2026", f'Beginning balance,"{money_str(d["b0"], 1)}"', ""],
              bom=True, crlf=True)

    # ---- workspace: general ledger detail ----
    grows = [["", "", "", "", "Beginning balance", None, None, d["g0"]]]
    bal = d["g0"]
    for x in d["led"]:
        bal = c(bal + x["amount"])
        grows.append([x["date"], x["type"], x["num"] if x["num"] != "" else None, x["name"], x["memo"],
                      x["amount"] if x["amount"] > 0 else None, -x["amount"] if x["amount"] < 0 else None, bal])
    grows.append(["", "", "", "", "Total for 1010 Checking", c(sum(x["amount"] for x in d["led"] if x["amount"] > 0)),
                  c(-sum(x["amount"] for x in d["led"] if x["amount"] < 0)), d["g1"]])
    write_xlsx(os.path.join(ws, "gl_1010_checking_2026-08.xlsx"), {"GL Detail": {
        "merged_title": "Westbrook Plumbing - General Ledger Detail - 1010 Checking - August 2026",
        "header": ["Date", "Transaction type", "Num", "Name", "Memo", "Debit", "Credit", "Balance"],
        "rows": grows, "widths": {"A": 12, "B": 16, "C": 8, "D": 26, "E": 28, "F": 12, "G": 12, "H": 13},
        "number_formats": {"F": "#,##0.00", "G": "#,##0.00", "H": "#,##0.00"}}}, creator="Westbrook Books")

    # ---- workspace: July reconciliation ----
    jul_rows = [["Balance per bank statement, 31 Jul 2026", "", "", d["b0"]], ["", "", "", ""],
                ["Deposits in transit", "", "", ""],
                [d["jul_dit"]["date"], "Deposit - night drop", "", d["jul_dit"]["amount"]],
                ["Outstanding checks", "", "", ""]]
    for x in d["jul_oc"]:
        jul_rows.append([x["date"], f"Check {x['num']}", x["payee"], x["amount"]])
    tot_jul_oc = c(sum(x["amount"] for x in d["jul_oc"]))
    jul_rows += [["", "Total outstanding checks", "", tot_jul_oc], ["", "", "", ""],
                 ["Adjusted bank balance", "", "", d["g0"]], ["Balance per books, 31 Jul 2026", "", "", d["g0"]], ["Difference", "", "", 0]]
    write_xlsx(os.path.join(ws, "bank_rec_2026-07.xlsx"), {"July": {
        "merged_title": "Bank reconciliation - checking 1010 - July 2026 (prepared by Alma, reviewed)",
        "header": ["Item", "Detail", "Payee", "Amount"], "rows": jul_rows,
        "widths": {"A": 40, "B": 26, "C": 24, "D": 14}, "number_formats": {"D": "#,##0.00"}}}, creator="Westbrook Books")

    write_email_thread(os.path.join(ws, "email_from_dean.txt"), [
        {"from": "Dean Westbrook <dean@westbrookplumbing.com>", "to": "you", "date": "Tue, 8 Sep 2026 07:55",
         "subject": "August bank rec",
         "body": ("Alma is out, can you do August's bank reconciliation? Same idea as her July one in the folder: what "
                  "matched between the bank and the books, what is still outstanding either way, and anything on the bank "
                  "statement that never made it into the books. It has to come out to zero, to the cent, and I'd like the "
                  "totals to be formulas so I can see how you got there.")},
        {"from": "Dean Westbrook <dean@westbrookplumbing.com>", "to": "you", "date": "Tue, 8 Sep 2026 08:10",
         "subject": "RE: August bank rec",
         "body": ("Two more things. Bank charges, interest and bounced customer checks get booked from the statement, so "
                  "treat those as adjustments on the book side. And if the bank and the books disagree on the amount of a "
                  "check, the bank is right - they pay what's written on the check. Alma sometimes fat-fingers the entry.")}])

    # ---- reference ----
    write_json(os.path.join(ref, "rec.json"), {
        "bank_ending": d["b1"], "book_ending": d["g1"], "outstanding_checks_total": d["oc_total"], "deposits_in_transit_total": d["dit_total"],
        "book_adjustments_total": d["book_adj"], "adjusted_balance": d["adjusted"],
        "outstanding_checks": [{"num": d["carried"]["num"], "amount": d["carried"]["amount"], "carried_from_july": True}] +
                              [{"num": x["num"], "amount": c(-x["amount"]), "carried_from_july": False} for x in d["oc_aug"]],
        "deposits_in_transit": [{"date": d["dit"]["date"].isoformat(), "amount": d["dit"]["amount"]}],
        "swap": {"num": d["swap"]["num"], "book": c(-d["swap"]["amount"]), "bank": c(-d["swap"]["bank_amount"]), "difference": c(abs(d["swap_diff"]))},
        "bank_only": [{"desc": x["desc"], "amount": x["amount"]} for x in d["bank_only"]],
        "cleared_check_numbers": sorted([x["num"] for x in d["led"] if x["tag"] in ("check", "swap")] +
                                        [x["num"] for x in d["jul_oc"] if x is not d["carried"]]),
        "naive": naive_figures(d)})
    rec_workbook(d, os.path.join(sol, "reconciliation.xlsx"))

    tol = lambda x: round(0.01 / max(abs(x), 1), 9)
    sw = d["swap"]
    write_task_yaml(HERE, {
        "id": "bank-reconciliation", "track": "desk", "category": "bookkeeping",
        "title": "August bank reconciliation for the checking account",
        "ask": ("Can you do the August bank reconciliation for our checking account? The bank export, the ledger and Alma's July "
                "rec are in the folder, and Dean's email says what he wants. Save it as reconciliation.xlsx.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"check {d['carried']['num']} was outstanding on July's reconciliation and still has not cleared; it is not in August's "
            "ledger, so comparing only August's ledger with August's statement drops it from the outstanding list "
            "(checks: outstanding checks and deposits in transit totals; adjusted balance; both sides tie and items listed)",
            f"July's other two outstanding checks and its deposit in transit clear on the August statement; they are old book "
            "entries, not bank items to book again (checks: adjusted balance; both sides tie and items listed)",
            "two customer receipts the books record separately on 19 August reached the bank as one deposit the next day; "
            "matching one to one by amount leaves both in transit and the combined deposit unexplained "
            "(check: outstanding checks and deposits in transit totals)",
            f"check {sw['num']} is in the books at {-sw['amount']:,.2f} but cleared the bank at {-sw['bank_amount']:,.2f} (two digits "
            f"swapped); Dean's email says the bank is right, so the books take a {abs(d['swap_diff']):,.2f} correction and without it "
            "the reconciliation is off by that amount (checks: adjusted balance; both sides tie and items listed)",
            "the monthly fee, a bounced customer check, its returned-item fee and the interest credit are only on the statement and "
            "belong on the book side (checks: adjusted balance; both sides tie and items listed)",
            "the bank export has separate debit and credit columns, a running balance and an ending-balance line under a preamble; "
            "the ledger has a beginning-balance row and a total row that a plain column sum double counts "
            "(checks: adjusted balance; both sides tie and items listed)",
        ],
        "checks": [
            {"type": "file_exists", "name": "reconciliation.xlsx exists", "path": "reconciliation.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "reconciliation.xlsx", "min_count": 4},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "reconciliation.xlsx"},
            {"type": "custom", "name": "outstanding checks and deposits in transit totals", "module": "check_totals.py"},
            {"type": "xlsx_value_present", "name": "adjusted balance", "path": "reconciliation.xlsx",
             "expected": d["adjusted"], "rel_tol": tol(d["adjusted"]), "near_text": "adjusted"},
            {"type": "custom", "name": "both sides tie and items listed", "module": "check.py"},
        ],
    })
    print(f"seed={seed}: bank {d['b0']} -> {d['b1']}, books {d['g0']} -> {d['g1']}")
    print(f"  OC {d['oc_total']} DIT {d['dit_total']} book adj {d['book_adj']} adjusted {d['adjusted']} swap {d['swap_diff']}")
    print("  naive:", naive_figures(d))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        s = a.seed * 1000 + attempt
        if acceptable(build(s)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(s, a.naive)
