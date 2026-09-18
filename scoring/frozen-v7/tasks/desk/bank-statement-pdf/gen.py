#!/usr/bin/env python3
"""bank-statement-pdf: July and August statements from three accounts to one transactions file.

    python gen.py [--seed N]

Business: a coffee roaster moved its checking account from a credit union to a bank on 1 August and keeps
a savings account at a third institution. The bookkeeper wants every July and August transaction in the
same layout as the June file she keyed by hand.

Traps (each caught by a check, see task.yaml):
  * the bank statement prints Debits and Credits in separate columns next to a running Balance (check: amounts)
  * page 1 ends with "Balance carried forward" and page 2 opens with "Balance brought forward"; neither is a
    transaction, and neither are the summary totals                         (checks: one row per transaction; row count)
  * a payroll debit starts at the foot of page 1 (date, reference, first description line) and its second
    description line, amount and balance print at the top of page 2      (checks: amounts; descriptions; running balances)
  * page 3 lists the checks again under "Checks paid" with a daily balance table (check: row count)
  * the credit union prints one Amount column with a trailing minus on withdrawals ("412.33-") (check: amounts)
  * the savings statement is an image-only scan with opening and closing balance lines (checks: one row per transaction; running balances)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

BIZ = "Nightjar Coffee Roasters LLC"
BIZ_ADDR = ["2208 Alder St", "Eugene, OR 97401"]
CU, HT, NS = "4417", "8823", "2290"


def m2(x): return f"{abs(x):,.2f}"


def build(seed: int) -> dict:
    r = rng(seed)
    used = set()

    def ref(kind):
        while True:
            v = {"cu": str(r.randint(1000000, 9999999)), "ht": str(r.randint(3100000000, 3199999999))}[kind]
            if v not in used:
                used.add(v); return v

    # ---- Cascade Credit Union, July
    cu_open = round(r.uniform(22000, 26000), 2)
    cu = []
    def add(lst, d, rf, desc, amt, desc2=None):
        lst.append(dict(date=d, ref=rf, desc=desc, desc2=desc2, amount=round(amt, 2)))
    J = lambda day: date(2026, 7, day)
    add(cu, J(1), ref("cu"), "SQUARE INC DEPOSIT 070126", r.uniform(2800, 4200))
    add(cu, J(2), ref("cu"), "POS PURCHASE COSTCO WHSE #0891", -r.uniform(300, 520))
    add(cu, J(6), ref("cu"), "SQUARE INC DEPOSIT 070626", r.uniform(3000, 4600))
    chk_cu = None
    add(cu, J(7), ref("cu"), "ACH DEBIT PACIFIC GREEN COFFEE IMP", -float(r.randrange(2000, 3500, 50)))
    add(cu, J(10), ref("cu"), "ACH DEBIT GUSTO PAYROLL NET PAY", -r.uniform(5400, 6600))
    add(cu, J(13), ref("cu"), "SQUARE INC DEPOSIT 071326", r.uniform(3000, 4600))
    add(cu, J(15), ref("cu"), f"TRANSFER TO SAVINGS XX{NS}", -2500.00)
    add(cu, J(17), ref("cu"), "ACH DEBIT CASCADE POWER UTIL", -r.uniform(380, 560))
    add(cu, J(20), ref("cu"), "SQUARE INC DEPOSIT 072026", r.uniform(3000, 4600))
    add(cu, J(24), ref("cu"), "ACH DEBIT GUSTO PAYROLL NET PAY", -r.uniform(5400, 6600))
    add(cu, J(27), ref("cu"), "SQUARE INC DEPOSIT 072726", r.uniform(3000, 4600))
    add(cu, J(28), ref("cu"), "POS PURCHASE RESTAURANT DEPOT 114", -r.uniform(600, 950))
    add(cu, J(31), ref("cu"), "ACCOUNT SERVICE CHARGE", -12.00)
    bal = cu_open
    for t in cu:
        bal = round(bal + t["amount"], 2); t["balance"] = bal
    close_amt = bal
    add(cu, J(31), ref("cu"), "WIRE OUT HARBOR TRUST ACCOUNT CLOSE", -close_amt)
    cu[-1]["balance"] = 0.00

    # ---- Harbor Trust, August (first statement of the new account)
    ht = []
    A = lambda day: date(2026, 8, day)
    add(ht, A(3), ref("ht"), "INCOMING WIRE CASCADE CREDIT UNION", close_amt)
    add(ht, A(3), ref("ht"), "SQUARE INC DEPOSIT 080326", r.uniform(3000, 4600))
    chk = r.randint(1001, 1004)
    add(ht, A(4), str(chk), f"CHECK {chk}", -float(r.randrange(900, 2400, 25)))
    add(ht, A(5), ref("ht"), "POS PURCHASE RESTAURANT DEPOT 114", -r.uniform(600, 950))
    add(ht, A(7), ref("ht"), "WIRE OUT PACIFIC GREEN COFFEE IMPORTS", -float(r.randrange(4000, 6500, 50)))
    add(ht, A(10), ref("ht"), "SQUARE INC DEPOSIT 081026", r.uniform(3000, 4600))
    add(ht, A(11), str(chk + 1), f"CHECK {chk + 1}", -float(r.randrange(300, 900, 5)))
    add(ht, A(12), ref("ht"), f"TRANSFER FROM SAVINGS XX{NS}", 4000.00)
    add(ht, A(13), ref("ht"), "ACH DEBIT CASCADE POWER UTIL", -r.uniform(380, 560))
    split_i = len(ht)
    add(ht, A(14), ref("ht"), "ACH DEBIT GUSTO PAYROLL", -r.uniform(5400, 6600), desc2="PPD ID 4410092113 NET PAY 081426")
    add(ht, A(17), ref("ht"), "SQUARE INC DEPOSIT 081726", r.uniform(3000, 4600))
    add(ht, A(18), str(chk + 2), f"CHECK {chk + 2}", -float(r.randrange(400, 1300, 5)))
    add(ht, A(20), ref("ht"), "ACH DEBIT HARTFORD MUTUAL INS PREM", -r.uniform(610, 790))
    add(ht, A(24), ref("ht"), "SQUARE INC DEPOSIT 082426", r.uniform(3000, 4600))
    add(ht, A(26), ref("ht"), "POS PURCHASE COSTCO WHSE #0891", -r.uniform(300, 520))
    add(ht, A(28), ref("ht"), "ACH DEBIT GUSTO PAYROLL", -r.uniform(5400, 6600), desc2="PPD ID 4410092113 NET PAY 082826")
    add(ht, A(31), ref("ht"), "SQUARE INC DEPOSIT 083126", r.uniform(3000, 4600))
    add(ht, A(31), ref("ht"), "MONTHLY MAINTENANCE FEE", -15.00)
    bal = 0.0
    for t in ht:
        bal = round(bal + t["amount"], 2); t["balance"] = bal
    if min(t["balance"] for t in ht + cu) < 0:
        raise SystemExit("negative balance; adjust draw")

    # ---- Northgate Savings, Jul-Aug (scan)
    ns_open = round(r.uniform(15000, 19000), 2)
    ns = []
    seq = r.randint(10, 60)
    add(ns, J(15), f"S-{seq:04d}", f"TRANSFER FROM CHECKING XX{CU}", 2500.00)
    add(ns, J(31), f"S-{seq + 1:04d}", "INTEREST PAID", round((ns_open + 2500) * 0.0085 / 12, 2))
    add(ns, A(12), f"S-{seq + 2:04d}", f"TRANSFER TO CHECKING XX{HT}", -4000.00)
    bal = ns_open
    for t in ns[:2]:
        bal = round(bal + t["amount"], 2); t["balance"] = bal
    bal = round(bal - 4000, 2); ns[2]["balance"] = bal
    add(ns, A(31), f"S-{seq + 3:04d}", "INTEREST PAID", round(bal * 0.0085 / 12, 2))
    ns[3]["balance"] = round(bal + ns[3]["amount"], 2)
    names = people(r, 2)
    return dict(cu=cu, cu_open=cu_open, ht=ht, split_i=split_i, ns=ns, ns_open=ns_open, chk_cu=chk_cu, marcus=names[0])


# ---------------------------------------------------------------- Harbor Trust statement, drawn on a canvas
def harbor_pdf(path: str, d: dict) -> None:
    from reportlab import rl_config
    rl_config.invariant = 1
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
    ht = d["ht"]; k = d["split_i"]
    c = canvas.Canvas(path, pagesize=LETTER, invariant=1)
    c.setTitle(""); c.setAuthor(""); c.setCreator(""); c.setProducer("")
    W, H = LETTER
    X_DATE, X_REF, X_DESC, X_DEB, X_CRE, X_BAL = 40, 80, 158, 438, 506, 572

    def header(page, cont=False):
        c.setFont("Helvetica-Bold", 15); c.drawString(40, H - 50, "HARBOR TRUST")
        c.setFont("Helvetica", 8); c.drawString(40, H - 62, "1 Harbor Way, Tacoma, WA 98402  |  harbortrust.example  |  1-800-555-0144")
        c.setFont("Helvetica", 9); c.drawRightString(W - 40, H - 50, "Business Checking Statement")
        c.drawRightString(W - 40, H - 62, "Statement period 08/01/2026 - 08/31/2026")
        c.drawRightString(W - 40, H - 74, f"Account number ******{HT}")
        c.setFont("Helvetica", 7.5); c.drawRightString(W - 40, 30, f"Page {page} of 3")
        c.line(40, H - 82, W - 40, H - 82)

    def table_head(y):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(X_DATE, y, "Date"); c.drawString(X_REF, y, "Reference"); c.drawString(X_DESC, y, "Description")
        c.drawRightString(X_DEB, y, "Debits"); c.drawRightString(X_CRE, y, "Credits"); c.drawRightString(X_BAL, y, "Balance")
        c.line(40, y - 4, W - 40, y - 4)
        return y - 16

    def row(y, t, first_line_only=False, continuation=False):
        c.setFont("Helvetica", 8)
        if not continuation:
            c.drawString(X_DATE, y, t["date"].strftime("%m/%d")); c.drawString(X_REF, y, t["ref"]); c.drawString(X_DESC, y, t["desc"])
        if t.get("desc2") and not first_line_only:
            if not continuation:
                y -= 11
            c.drawString(X_DESC, y, t["desc2"])
        if first_line_only:
            return y - 14
        if t["amount"] < 0: c.drawRightString(X_DEB, y, m2(t["amount"]))
        else: c.drawRightString(X_CRE, y, m2(t["amount"]))
        c.drawRightString(X_BAL, y, m2(t["balance"]))
        return y - 14

    deposits = round(sum(t["amount"] for t in ht if t["amount"] > 0), 2)
    debits = round(-sum(t["amount"] for t in ht if t["amount"] < 0), 2)
    # page 1
    header(1)
    c.setFont("Helvetica", 9)
    y = H - 104
    for ln in [BIZ.upper(), *[a.upper() for a in BIZ_ADDR]]:
        c.drawString(40, y, ln); y -= 12
    y -= 10
    c.setFont("Helvetica-Bold", 10); c.drawString(40, y, "Account summary"); y -= 14
    c.setFont("Helvetica", 9)
    for label, val in [("Beginning balance on 08/01/2026", "0.00"), (f"Deposits and other credits ({sum(1 for t in ht if t['amount'] > 0)})", m2(deposits)),
                       (f"Withdrawals and other debits ({sum(1 for t in ht if t['amount'] < 0)})", m2(debits)), ("Ending balance on 08/31/2026", m2(ht[-1]["balance"]))]:
        c.drawString(52, y, label); c.drawRightString(300, y, val); y -= 12
    y -= 6
    c.setFont("Helvetica", 7.5)
    c.drawString(40, y, "Welcome to Harbor Trust. Your first box of checks (1001-1100) has been mailed. Online banking enrollment is available at harbortrust.example.")
    y -= 22
    c.setFont("Helvetica-Bold", 10); c.drawString(40, y, "Transaction detail"); y -= 16
    y = table_head(y)
    c.setFont("Helvetica", 8); c.drawString(X_DESC, y, "Beginning balance"); c.drawRightString(X_BAL, y, "0.00"); y -= 14
    for t in ht[:k]:
        y = row(y, t)
    y = row(y, ht[k], first_line_only=True)
    c.line(40, y + 6, W - 40, y + 6)
    c.setFont("Helvetica-Oblique", 8); c.drawString(X_DESC, y - 6, "Balance carried forward"); c.drawRightString(X_BAL, y - 6, m2(ht[k - 1]["balance"]))
    c.drawString(X_DESC, y - 20, "Continued on next page")
    c.showPage()
    # page 2
    header(2)
    y = H - 104
    c.setFont("Helvetica-Bold", 10); c.drawString(40, y, f"Transaction detail (continued) - account ending {HT}"); y -= 16
    y = table_head(y)
    c.setFont("Helvetica-Oblique", 8); c.drawString(X_DESC, y, "Balance brought forward"); c.drawRightString(X_BAL, y, m2(ht[k - 1]["balance"])); y -= 14
    y = row(y, ht[k], continuation=True)
    for t in ht[k + 1:]:
        y = row(y, t)
    c.line(40, y + 6, W - 40, y + 6)
    c.setFont("Helvetica-Bold", 8); c.drawString(X_DESC, y - 6, "Ending balance"); c.drawRightString(X_BAL, y - 6, m2(ht[-1]["balance"]))
    c.drawRightString(X_DEB, y - 6, m2(debits)); c.drawRightString(X_CRE, y - 6, m2(deposits))
    c.showPage()
    # page 3
    header(3)
    y = H - 104
    c.setFont("Helvetica-Bold", 10); c.drawString(40, y, "Checks paid"); y -= 16
    c.setFont("Helvetica-Bold", 8); c.drawString(40, y, "Check no."); c.drawString(110, y, "Date paid"); c.drawRightString(260, y, "Amount"); y -= 14
    c.setFont("Helvetica", 8)
    for t in ht:
        if t["desc"].startswith("CHECK"):
            c.drawString(40, y, t["ref"]); c.drawString(110, y, t["date"].strftime("%m/%d")); c.drawRightString(260, y, m2(t["amount"])); y -= 12
    y -= 16
    c.setFont("Helvetica-Bold", 10); c.drawString(40, y, "Daily ending balance"); y -= 16
    c.setFont("Helvetica", 8)
    daily = {}
    for t in ht:
        daily[t["date"]] = t["balance"]
    items = sorted(daily.items())
    for i in range(0, len(items), 3):
        x = 40
        for dd, b in items[i:i + 3]:
            c.drawString(x, y, dd.strftime("%m/%d")); c.drawRightString(x + 120, y, m2(b)); x += 180
        y -= 12
    y -= 20
    c.setFont("Helvetica", 7)
    c.drawString(40, y, "In case of errors or questions about your electronic transfers, call 1-800-555-0144 or write to Harbor Trust, PO Box 2210, Tacoma, WA 98401.")
    c.showPage()
    c.save()


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "statements"); os.makedirs(F, exist_ok=True)

    # ---- credit union July (Times-Roman, single amount column with trailing minus)
    cu = d["cu"]
    body = [["Date", "Trace", "Description", "Amount", "Balance"], ["", "", "BEGINNING BALANCE", "", m2(d["cu_open"])]]
    for t in cu:
        amt = m2(t["amount"]) + ("-" if t["amount"] < 0 else "")
        body.append([t["date"].strftime("%b %d"), t["ref"], t["desc"], amt, m2(t["balance"])])
    body.append(["", "", "ENDING BALANCE", "", "0.00"])
    write_pdf_document(os.path.join(F, "CascadeCU_stmt_2026-07.pdf"), [
        ("title", "Cascade Credit Union"), ("small", "Member Services 541-555-0190  |  PO Box 1180, Eugene, OR 97440"), ("hr", None),
        ("kv", [("Member", BIZ), ("Account", f"Business Share Draft ...{CU}"), ("Statement period", "July 1, 2026 through July 31, 2026")],
         {"col_widths": [110, 330]}),
        ("spacer", 8),
        ("p", "Your account was closed on July 31, 2026 at your request. Thank you for banking with Cascade Credit Union."),
        ("spacer", 8),
        ("table", body, {"col_widths": [42, 58, 220, 72, 72], "align_right": [3, 4]}),
        ("spacer", 8),
        ("small", "Amounts followed by a minus sign (-) are withdrawals. Dividends are paid on share savings accounts only."),
    ], font="Times-Roman", base_size=9.5)

    # ---- Harbor Trust August (canvas, three pages)
    harbor_pdf(os.path.join(F, "HarborTrust_BusinessChecking_Aug2026.pdf"), d)

    # ---- Northgate savings (scan)
    ns = d["ns"]
    lines = ["NORTHGATE SAVINGS", "BUSINESS SAVINGS STATEMENT", "", BIZ, f"Account ending {NS}", "Period 07/01/2026 to 08/31/2026", "",
             "DATE REF DESCRIPTION", f"07/01 OPENING BALANCE {m2(d['ns_open'])}"]
    for t in ns:
        sign = "-" if t["amount"] < 0 else "+"
        lines.append(f"{t['date'].strftime('%m/%d')} {t['ref']} {t['desc']}")
        lines.append(f"      amount {sign}{m2(t['amount'])} balance {m2(t['balance'])}")
    lines += [f"08/31 CLOSING BALANCE {m2(ns[-1]['balance'])}", "", "Annual percentage yield earned 0.85%", "Questions? Call 208-555-0133"]
    write_scan_pdf(os.path.join(F, "scan_northgate_savings_jul-aug.pdf"), lines, font_size=32, seed=seed * 5 + 2, skew_deg=0.3, noise=250)

    # ---- June file keyed by hand (the layout to follow)
    rj = rng(seed + 991)
    june = [["txn_ref", "account", "date", "description", "amount", "balance"]]
    jrows = [(3, "SQUARE INC DEPOSIT 060326", round(rj.uniform(2800, 4200), 2)), (5, "POS PURCHASE COSTCO WHSE #0891", -round(rj.uniform(300, 520), 2)),
             (12, "ACH DEBIT GUSTO PAYROLL NET PAY", -round(rj.uniform(5400, 6600), 2)), (15, f"TRANSFER TO SAVINGS XX{NS}", -2500.0),
             (19, "SQUARE INC DEPOSIT 061926", round(rj.uniform(3000, 4600), 2)), (26, "ACH DEBIT GUSTO PAYROLL NET PAY", -round(rj.uniform(5400, 6600), 2)),
             (29, "SQUARE INC DEPOSIT 062926", round(rj.uniform(3000, 4600), 2))]
    jb = round(d["cu_open"] - sum(a for _, _, a in jrows), 2)
    for day, desc, amt in jrows:
        jb = round(jb + amt, 2)
        june.append([str(rj.randint(1000000, 9999999)), CU, f"2026-06-{day:02d}", desc, f"{round(amt, 2):.2f}", f"{jb:.2f}"])
    write_csv(os.path.join(ws, "transactions_2026-06.csv"), june[0], june[1:])

    mf, ml = d["marcus"]
    write_text(os.path.join(ws, "note.txt"),
        f"From {mf}:\n\n"
        "I keyed June by hand (transactions_2026-06.csv). Can you do July and August the same way into transactions.csv? "
        "The statements folder has everything: Cascade CU (closed at the end of July), the new Harbor Trust checking that started in August, "
        "and the Northgate savings statement that came in the mail.\n\n"
        "Same columns as June. txn_ref is the trace, reference, check or sequence number printed for that transaction, account is the last four "
        "digits of the account, money in is positive and money out is negative, and balance is the running balance printed after that transaction.\n")

    header = ["txn_ref", "account", "date", "description", "amount", "balance"]
    rows = []
    for acct, lst in ((CU, d["cu"]), (HT, d["ht"]), (NS, d["ns"])):
        for t in lst:
            desc = t["desc"] + (" " + t["desc2"] if t.get("desc2") else "")
            rows.append([t["ref"], acct, t["date"].isoformat(), desc, f"{t['amount']:.2f}", f"{t['balance']:.2f}"])
    write_csv(os.path.join(ref, "transactions.csv"), header, rows)
    write_csv(os.path.join(sol, "transactions.csv"), header, rows)
    ht = d["ht"]; split = ht[d["split_i"]]
    checks_ht = [t["ref"] for t in ht if t["desc"].startswith("CHECK")]
    cu_debits = [t["ref"] for t in d["cu"] if t["amount"] < 0][:3]
    ht_debits = [t["ref"] for t in ht if t["amount"] < 0][:4]
    write_json(os.path.join(ref, "notes.json"), {"split_ref": split["ref"], "harbor_checks": checks_ht, "carried_forward": ht[d["split_i"] - 1]["balance"],
                                                 "savings_withdrawal_ref": d["ns"][2]["ref"], "cu_debit_refs": cu_debits, "ht_debit_refs": ht_debits})
    write_task_yaml(HERE, {
        "id": "bank-statement-pdf", "track": "desk", "category": "extraction",
        "title": "Key the July and August bank statements into the transactions file",
        "ask": "Please get July and August off the bank statements and into transactions.csv, set up like the June file. Everything's in the folder, including a note on how I did June.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the Harbor Trust statement prints Debits and Credits in separate columns beside a running Balance, so the sign comes from the column; reading every figure as positive or taking the balance column turns debits into deposits (check: amounts)",
            "page 1 ends with a 'Balance carried forward' line and page 2 opens with 'Balance brought forward'; they, the beginning and ending balance lines and the account summary are not transactions (checks: one row per transaction; row count)",
            "the 14 August payroll debit starts at the foot of page 1 with its date, reference and first description line, and its second line, debit and balance print at the top of page 2; it is one transaction with the joined description (checks: amounts; descriptions; running balances)",
            "page 3 lists the three Harbor checks again under 'Checks paid' next to a daily ending balance table; keying them again duplicates those rows (check: row count)",
            "the credit union prints a single Amount column with a trailing minus on withdrawals ('412.33-') and dates as 'Jul 07' (checks: amounts; accounts and dates)",
            "the Northgate savings statement is an image-only scan with signed amounts between opening and closing balance lines (checks: one row per transaction; running balances)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "June file columns", "path": "transactions.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per transaction", "path": "transactions.csv", "column": "txn_ref", "ref": "transactions.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "transactions.csv", "equals_ref": "transactions.csv"},
            {"type": "csv_values_match", "name": "accounts and dates", "path": "transactions.csv", "ref": "transactions.csv", "key": "txn_ref",
             "columns": ["account", "date"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "descriptions", "path": "transactions.csv", "ref": "transactions.csv", "key": "txn_ref",
             "columns": ["description"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": [split["ref"]]},
            {"type": "csv_values_match", "name": "amounts", "path": "transactions.csv", "ref": "transactions.csv", "key": "txn_ref",
             "columns": ["amount"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [split["ref"], d["ns"][2]["ref"]] + cu_debits + ht_debits},
            {"type": "csv_values_match", "name": "running balances", "path": "transactions.csv", "ref": "transactions.csv", "key": "txn_ref",
             "columns": ["balance"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": [split["ref"], d["ns"][-1]["ref"]]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
