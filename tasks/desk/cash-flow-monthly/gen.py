#!/usr/bin/env python3
"""cash-flow-monthly: a caterer's checking and savings exports to money in and out by month, with a memo.

    python gen.py [--seed N]

Business: Fernwood Catering Co. banks event deposits, card payments and corporate lunch accounts in an operating checking account and
keeps a tax reserve in a savings account at a different bank. The owner wants March to August money in and money
out before a meeting with the bank about a line of credit.

Traps (each caught by a check, see task.yaml):
  * transfers between the two business accounts show up in both exports (a debit in one, a credit in the other,
    sometimes a day apart across a month end) and are not money in or out    (checks: June money in; total money in)
  * a transfer to the owner's personal account looks the same but is a real outflow (check: August money out)
  * the checking export lists pending items and two September postings after the August rows (check: August money out)
  * June carries a spike of overdraft and returned-item fees across both accounts; the memo must name it
                                                                            (checks: June bank fees; memo names the June fee spike)
  * the coffee roaster that supplies the caterer's event coffee has FEE inside COFFEE, so a substring search for fees overcounts
                                                                            (check: June bank fees)
  * the savings export pays the quarterly estimated tax directly and uses signed amounts in parentheses with an
    opening-balance row; checking uses separate Debit and Credit columns    (checks: June money out; total money in)
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MONTHS = [3, 4, 5, 6, 7, 8]
MONTH_NAME = {3: "March", 4: "April", 5: "May", 6: "June", 7: "July", 8: "August"}
CHK, SAV, OWNER = "2210", "4471", "8832"
P_START, P_END = date(2026, 3, 1), date(2026, 8, 31)


def month_days(m: int) -> int:
    return {3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30}[m]


def build(seed: int) -> dict:
    r = rng(seed)
    tx = []   # {acct, date, desc, amount (+in/-out), kind: in|out|transfer|pending, fee}

    def add(acct, d, desc, amount, kind=None, fee=False):
        kind = kind or ("in" if amount > 0 else "out")
        tx.append({"acct": acct, "date": d, "desc": desc, "amount": round(amount, 2), "kind": kind, "fee": fee})

    def bday(d: date) -> date:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    for m in MONTHS + [9]:
        last = 2 if m == 9 else month_days(m)
        season = {3: 0.8, 4: 0.9, 5: 1.05, 6: 1.2, 7: 1.3, 8: 1.25, 9: 1.1}[m]
        for day in range(1, last + 1):
            d = date(2026, m, day)
            if d.weekday() in (0, 1, 2, 3, 4) and r.random() < 0.8:
                add(CHK, d, f"SQUARE INC DEPOSIT {d.strftime('%m%d')} FERNWOOD CATERI", r.uniform(700, 2600) * season)
        for d in (date(2026, m, 1), date(2026, m, 8), date(2026, m, 15), date(2026, m, 22)):
            if d.day <= last:
                add(CHK, bday(d), "ACH CREDIT KESTREL ANALYTICS LUNCH PROGRAM", r.uniform(3800, 8200) * season)
        if m == 9:
            continue
        for d in (date(2026, m, 12), date(2026, m, 26)):
            add(CHK, bday(d), "ACH DEBIT GUSTO PAYROLL NET", -r.uniform(9200, 11800) * (1.1 if m >= 6 else 1.0))
            add(CHK, bday(d), "ACH DEBIT GUSTO TAX", -r.uniform(2600, 3400))
        add(CHK, date(2026, m, 1), "CHECK 1" + str(400 + m) + " HARBORVIEW COMMISSARY KITCHEN RENT", -6850.00)
        add(CHK, bday(date(2026, m, r.randint(3, 9))), "ACH DEBIT SYSCO SEATTLE", -r.uniform(3200, 6100) * season)
        add(CHK, bday(date(2026, m, r.randint(14, 24))), "DEBIT CARD RESTAURANT DEPOT", -r.uniform(1800, 4200) * season)
        add(CHK, bday(date(2026, m, r.randint(5, 20))), "DEBIT CARD NIGHTJAR COFFEE ROASTERS", -r.uniform(280, 820))
        add(CHK, bday(date(2026, m, r.randint(10, 25))), "ACH DEBIT PARTY RENTAL LTD LINENS TENTS", -r.uniform(2400, 5200) * season)
        add(CHK, bday(date(2026, m, r.randint(18, 24))), "ACH DEBIT PUGET SOUND ENERGY", -r.uniform(1300, 2300))
        add(CHK, bday(date(2026, m, 20)), "WA DEPT REVENUE SALES TAX", -r.uniform(1500, 2600) * season)
        add(CHK, date(2026, m, month_days(m)), "MONTHLY SERVICE FEE", -25.00, fee=True)
        add(SAV, date(2026, m, month_days(m)), "DIVIDEND EARNED", round(r.uniform(18, 42), 2))
        if m == 4:
            add(CHK, date(2026, 4, 14), "WIRE TRANSFER FEE", -30.00, fee=True)
            add(CHK, date(2026, 4, 14), "OUTGOING WIRE HOBART COMBI OVEN", -18400.00)
        # monthly tax reserve sweep (not in June: the account was short)
        if m != 6:
            sweep = round(r.choice([2500, 3000, 3500]), 2)
            d_out = date(2026, m, month_days(m)) if m in (3, 7) else bday(date(2026, m, 25))
            d_in = bday(d_out + timedelta(days=1)) if m in (3, 7) else d_out
            add(CHK, d_out, f"ONLINE TRANSFER TO SAVINGS XXXXXX{SAV}", -sweep, kind="transfer")
            add(SAV, d_in, f"TRANSFER FROM CHECKING XXXXXX{CHK}", sweep, kind="transfer")
    # June: the account runs short after payroll and the tax payment
    for d, desc, amt in ((date(2026, 6, 8), "OVERDRAFT FEE", 38.0), (date(2026, 6, 8), "OVERDRAFT FEE", 38.0), (date(2026, 6, 9), "NSF RETURNED ITEM FEE", 38.0),
                         (date(2026, 6, 9), "OVERDRAFT FEE", 38.0), (date(2026, 6, 10), "NSF RETURNED ITEM FEE", 38.0), (date(2026, 6, 26), "OVERDRAFT FEE", 38.0),
                         (date(2026, 6, 29), "OVERDRAFT FEE", 38.0), (date(2026, 6, 30), "ACCOUNT ANALYSIS FEE", 64.0)):
        add(CHK, d, desc, -amt, fee=True)
    add(SAV, date(2026, 6, 10), f"TRANSFER TO CHECKING XXXXXX{CHK}", -15000.00, kind="transfer")
    add(CHK, date(2026, 6, 10), f"ONLINE TRANSFER FROM SAVINGS XXXXXX{SAV}", 15000.00, kind="transfer")
    add(SAV, date(2026, 6, 15), "IRS USATAXPYMT 2026 Q2 ESTIMATE", -round(r.uniform(8200, 9800), 2))
    add(SAV, date(2026, 6, 30), "EXCESS WITHDRAWAL FEE", -15.00, fee=True)
    add(SAV, date(2026, 4, 15), "IRS USATAXPYMT 2026 Q1 ESTIMATE", -round(r.uniform(7200, 8400), 2))
    # August: owner's draw to a personal account, and pending items at the end of the export
    add(CHK, date(2026, 8, 14), f"ONLINE TRANSFER TO XXXXXX{OWNER} REF DRAW", -6000.00)
    pend = [(date(2026, 8, 30), "PENDING DEBIT CARD RESTAURANT DEPOT", -r.uniform(900, 1600)),
            (date(2026, 8, 31), "PENDING ACH DEBIT SYSCO SEATTLE", -r.uniform(2800, 4400)),
            (date(2026, 8, 31), "PENDING DEPOSIT SQUARE INC", r.uniform(900, 2100))]
    for d, desc, amt in pend:
        add(CHK, d, desc, amt, kind="pending")

    tx.sort(key=lambda t: (t["acct"], t["date"], t["kind"] == "pending", t["desc"]))

    # ---- truth ----
    inflow = {m: 0.0 for m in MONTHS}; outflow = {m: 0.0 for m in MONTHS}; fees = {m: 0.0 for m in MONTHS}
    naive = {"in_with_transfers": {m: 0.0 for m in MONTHS}, "out_with_transfers_pending": {m: 0.0 for m in MONTHS},
             "fees_substring": {m: 0.0 for m in MONTHS}, "out_checking_only": {m: 0.0 for m in MONTHS}}
    for t in tx:
        if not (P_START <= t["date"] <= P_END):
            continue
        m = t["date"].month
        if t["kind"] == "in":
            inflow[m] += t["amount"]
        elif t["kind"] == "out":
            outflow[m] += -t["amount"]
            if t["acct"] == CHK:
                naive["out_checking_only"][m] += -t["amount"]
        if t["fee"]:
            fees[m] += -t["amount"]
        if "FEE" in t["desc"].upper() and t["amount"] < 0:
            naive["fees_substring"][m] += -t["amount"]
        if t["amount"] > 0:
            naive["in_with_transfers"][m] += t["amount"]
        else:
            naive["out_with_transfers_pending"][m] += -t["amount"]
    r2 = lambda dct: {k: round(v, 2) for k, v in dct.items()}
    inflow, outflow, fees = r2(inflow), r2(outflow), r2(fees)
    naive = {k: r2(v) for k, v in naive.items()}
    tot_in, tot_out = round(sum(inflow.values()), 2), round(sum(outflow.values()), 2)
    return {"tx": tx, "inflow": inflow, "outflow": outflow, "fees": fees, "tot_in": tot_in, "tot_out": tot_out,
            "net": {m: round(inflow[m] - outflow[m], 2) for m in MONTHS}, "naive": naive}


def acceptable(d: dict) -> bool:
    inf, out, fees, nv = d["inflow"], d["outflow"], d["fees"], d["naive"]
    rows = {"in": [inf[m] for m in MONTHS] + [d["tot_in"]], "out": [out[m] for m in MONTHS] + [d["tot_out"]]}
    for vals in rows.values():
        if any(abs(a - b) <= 0.01 * a for i, a in enumerate(vals) for j, b in enumerate(vals) if i != j):
            return False
    if abs(out[8] - nv["out_with_transfers_pending"][8]) < 0.03 * out[8]:
        return False
    if abs(d["tot_in"] - sum(nv["in_with_transfers"].values())) < 0.02 * d["tot_in"]:
        return False
    if fees[6] < 5 * max(fees[m] for m in MONTHS if m != 6) or abs(fees[6] - nv["fees_substring"][6]) < 100:
        return False
    # the net line never lands on a checked figure
    checked = [inf[6], out[6], out[8], d["tot_in"]]
    return all(abs(v - n) > 0.01 * abs(v) for v in checked for n in d["net"].values())


# --------------------------------------------------------------------------- deliverables

def cash_sheets(d: dict) -> dict:
    data = []
    for t in d["tx"]:
        if not (P_START <= t["date"] <= P_END):
            continue
        data.append([("Checking " if t["acct"] == CHK else "Savings ") + t["acct"], t["date"].isoformat(), MONTH_NAME[t["date"].month],
                     t["desc"], t["amount"], t["kind"], 1 if t["fee"] else 0])
    n = len(data) + 1
    cols = "BCDEFG"
    rows = [
        ["Money in"] + [f'=ROUND(SUMIFS(Transactions!$E$2:$E${n},Transactions!$C$2:$C${n},{c}$1,Transactions!$F$2:$F${n},"in"),2)' for c in cols] + ["=SUM(B2:G2)"],
        ["Money out"] + [f'=ROUND(-SUMIFS(Transactions!$E$2:$E${n},Transactions!$C$2:$C${n},{c}$1,Transactions!$F$2:$F${n},"out"),2)' for c in cols] + ["=SUM(B3:G3)"],
        ["Net cash flow"] + [f"={c}2-{c}3" for c in cols] + ["=H2-H3"],
        [],
        ["Bank fees (included in money out)"] + [f"=ROUND(-SUMIFS(Transactions!$E$2:$E${n},Transactions!$C$2:$C${n},{c}$1,Transactions!$G$2:$G${n},1),2)" for c in cols] + ["=SUM(B6:G6)"],
        [],
        ["Both accounts. Transfers between checking 2210 and savings 4471 are left out; the draw to account 8832 is a real outflow. "
         "Pending items and September postings are not included."],
    ]
    return {"Cash flow": {"header": ["Fernwood Catering Co.", *[MONTH_NAME[m] for m in MONTHS], "Mar-Aug total"], "rows": rows,
                          "widths": {"A": 34, "H": 16}},
            "Transactions": {"header": ["account", "date", "month", "description", "amount", "kind", "bank fee"], "rows": data,
                             "widths": {"D": 46}}}


def memo_text(d: dict) -> str:
    f = d["fees"]
    usual = max(f[m] for m in MONTHS if m != 6)
    return f"""# Cash flow, March to August 2026

Across both accounts the business took in ${d['tot_in']:,.2f} and paid out ${d['tot_out']:,.2f}, a net
{'increase' if d['tot_in'] >= d['tot_out'] else 'decrease'} of ${abs(d['tot_in'] - d['tot_out']):,.2f}.

- Bank fees spiked in June: ${f[6]:,.2f} of overdraft, returned-item and analysis fees, against no more than ${usual:,.2f} in any other month. Checking went overdrawn in the second week of June and again at month end, and $15,000 was moved back from savings on 10 June.
- Transfers between checking and savings are left out of both columns; the $6,000 transfer to account 8832 in August is an owner's draw and counts as money out.
- Pending items at the end of the checking export and the September postings are not included.
"""



def cent_tolerant(spec: dict) -> dict:
    """Figures computed from exact source data tie to the cent: every workbook pin gets a tolerance under 1.00."""
    for c in spec["checks"]:
        if c["type"] == "xlsx_value_present" and not c.get("rounding"):
            exp = abs(float(c["expected"]))
            c["rel_tol"] = min(float(c.get("rel_tol", 0.005)), float(f"{0.9 / max(exp, 1.0):.2g}"))
    return spec


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)

    # ---- workspace ----
    chk = [t for t in d["tx"] if t["acct"] == CHK]
    posted = [t for t in chk if t["kind"] != "pending"]
    pending = [t for t in chk if t["kind"] == "pending"]
    write_csv(os.path.join(ws, "first_meridian_checking_x2210.csv"),
              ["Posting Date", "Description", "Debit", "Credit", "Status"],
              [[t["date"].strftime("%m/%d/%Y"), t["desc"], f"{-t['amount']:.2f}" if t["amount"] < 0 else "",
                f"{t['amount']:.2f}" if t["amount"] > 0 else "", "Posted"] for t in posted]
              + [[t["date"].strftime("%m/%d/%Y"), t["desc"], f"{-t['amount']:.2f}" if t["amount"] < 0 else "",
                  f"{t['amount']:.2f}" if t["amount"] > 0 else "", "Pending"] for t in pending],
              preamble=["First Meridian Bank - Business Checking XXXXXX2210", "Transactions 03/01/2026 through 09/02/2026", ""])
    sav = [t for t in d["tx"] if t["acct"] == SAV]
    bal = 41250.00
    srows = [["03/01/2026", "Opening balance", "", f"{bal:,.2f}"]]
    for t in sav:
        bal += t["amount"]
        srows.append([t["date"].strftime("%m/%d/%Y"), t["desc"], money_str(t["amount"], 5) if t["amount"] < 0 else f"{t['amount']:,.2f}", f"{bal:,.2f}"])
    write_csv(os.path.join(ws, "cascade_cu_savings_4471.csv"), ["Date", "Description", "Amount", "Balance"], srows, bom=True, crlf=True)
    write_text(os.path.join(ws, "note_from_jonah.txt"),
               "I'm meeting the bank about a line of credit and they want to see cash flow for March through August.\n\n"
               "Both accounts count - operating checking at First Meridian (ends 2210) and the tax reserve savings at Cascade\n"
               "(ends 4471). Month by month I need money in and money out, both as positive numbers the way the bank's own\n"
               "summary shows them, and the net. Moving money between our own two accounts is not money in or out. Only\n"
               "count what has actually cleared.\n\n"
               "Put bank fees on their own line too - the loan officer always asks - and write me a short memo with anything\n"
               "that stands out before I walk in.\n\n"
               "Jonah\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "cash_by_month.csv"), ["month", "money_in", "money_out", "net", "bank_fees"],
              [[MONTH_NAME[m], f"{d['inflow'][m]:.2f}", f"{d['outflow'][m]:.2f}", f"{d['net'][m]:.2f}", f"{d['fees'][m]:.2f}"] for m in MONTHS])
    write_json(os.path.join(ref, "notes.json"), {"total_in": d["tot_in"], "total_out": d["tot_out"], "fee_spike_month": "June",
                                                  "fees": {MONTH_NAME[m]: d["fees"][m] for m in MONTHS},
                                                  "naive": {k: {MONTH_NAME[m]: v[m] for m in MONTHS} for k, v in d["naive"].items()}})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "cashflow.xlsx"), cash_sheets(d), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    inf, out, fees = d["inflow"], d["outflow"], d["fees"]
    write_task_yaml(HERE, cent_tolerant({
        "id": "cash-flow-monthly", "track": "desk", "category": "reports",
        "title": "Money in and out by month for the bank meeting",
        "ask": ("Jonah is meeting the bank about a line of credit and needs March to August cash flow from our two bank exports. "
                "Build cashflow.xlsx with live formulas and a short memo.md - his note says what he wants.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the monthly tax-reserve sweep appears as a debit in checking and a credit in savings (twice across a month end, a day "
            "apart), and in June $15,000 came back from savings; counting either side inflates money in and money out "
            "(checks: June money in; total money in)",
            "the 14 August transfer to account 8832 reads like the sweeps but goes to the owner's personal account and is a real "
            "outflow (check: August money out)",
            "the checking export ends with three Pending rows and carries September postings after the August rows "
            "(check: August money out)",
            "June has overdraft, returned-item and analysis fees in checking and an excess-withdrawal fee in savings, several times any "
            "other month's; the memo must name the June fee spike (checks: June bank fees; memo names the June fee spike)",
            "the caterer buys event coffee from NIGHTJAR COFFEE ROASTERS every month, so a substring search for FEE picks up coffee as a bank fee "
            "(check: June bank fees)",
            "the savings export pays the quarterly estimated tax straight to the IRS, uses one signed Amount column with parentheses, "
            "a running balance, an opening-balance row, a BOM and CRLF endings, while checking has Debit and Credit columns and a "
            "three-line preamble (checks: June money out; total money in)",
        ],
        "checks": [
            {"type": "file_exists", "name": "cashflow.xlsx exists", "path": "cashflow.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "cashflow.xlsx", "min_count": 18},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "cashflow.xlsx"},
            {"type": "xlsx_value_present", "name": "June money in (transfer from savings left out)", "path": "cashflow.xlsx",
             "expected": inf[6], "rel_tol": 0.003, "near_text": "in"},
            {"type": "xlsx_value_present", "name": "June money out (fees and the IRS payment from savings)", "path": "cashflow.xlsx",
             "expected": out[6], "rel_tol": 0.003, "near_text": "out"},
            {"type": "xlsx_value_present", "name": "August money out (owner's draw in, pending out)", "path": "cashflow.xlsx",
             "expected": out[8], "rel_tol": 0.003, "near_text": "out"},
            {"type": "xlsx_value_present", "name": "total money in, March to August", "path": "cashflow.xlsx",
             "expected": d["tot_in"], "rel_tol": 0.003, "near_text": "in"},
            {"type": "xlsx_value_present", "name": "June bank fees", "path": "cashflow.xlsx",
             "expected": fees[6], "rel_tol": 0.01, "near_text": "fee"},
            {"type": "text_numbers_present", "name": "memo carries the June fee total", "path": "memo.md",
             "numbers": [fees[6]], "rel_tol": 0.01},
            {"type": "text_sentence_matches", "name": "memo names the June fee spike", "path": "memo.md",
             "all": [r"(\bjune\b|\bjun\b|\b2026-06\b|\b06/2026\b)", r"(\bfees?\b|\bcharges?\b|\boverdraft|\bnsf\b)",
                     r"(spike|jump|surge|rose|higher|increase|unusual|more than|times|overdraft|nsf|returned|jumped|up from|above|elevated)"],
             "none": [r"(no (unusual|spike|jump)|not (unusual|a spike)|normal (fees|level))"]},
        ],
    }))
    print(f"seed={seed} tx={len(d['tx'])}")
    print("  in", inf, "out", out, "fees", fees, "tot", d["tot_in"], d["tot_out"])
    print("  naive", d["naive"])


if __name__ == "__main__":
    s = argparse_seed()
    for attempt in range(800):
        if acceptable(build(s * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 800 attempts")
    emit(s * 1000 + attempt)
