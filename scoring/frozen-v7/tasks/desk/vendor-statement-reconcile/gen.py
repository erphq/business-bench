#!/usr/bin/env python3
"""vendor-statement-reconcile: a plumbing supply house's open-item statement against our AP ledger for that vendor.

    python gen.py [--seed N] [--naive DIR]

Business: Westbrook Plumbing buys fittings, fixtures and water heaters on account from Keystone Plumbing Supply. At
month end Keystone mails an open-item statement (PDF); our books are a vendor transaction report exported from the
accounting system. The office manager's note says how the reconciliation sheet is laid out and what each status means.

Traps (each caught by a check, see task.yaml):
  * document numbers differ in form: 'INV 0418102' on the statement, '418102' in our ledger (checks: one row per open item; status)
  * a credit memo on the statement was never entered in our books, and credits are negative (checks: status; difference)
  * two invoices we paid by a check mailed on the 28th are still open on the statement      (checks: status; difference)
  * two invoices differ by cents: a transposed 1,284.36 / 1,284.63 and a one-cent tax rounding (checks: status; difference)
  * a bill dated after the statement's cutoff is open in our books only                     (check: status)
  * the ledger lists closed bills and payments from June and July alongside the open ones    (checks: one row per open item; row count)
  * the difference column adds up to the gap between the two balances                       (check: variance ties to the balances)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

JOBS = ["Harlow residence remodel", "Pine Ridge Apts bldg C", "St. Anne's parish hall", "Oakview Dental buildout", "Mercer duplex repipe",
        "Lakeshore Diner kitchen", "Birchwood HOA clubhouse", "Service van restock", "Dunmore office tenant fit-out", "Quarry Rd warehouse"]
CUTOFF = date(2026, 8, 28)
STMT_DATE = date(2026, 8, 31)
ST_MATCH, ST_DIFF, ST_BOOKS, ST_STMT, ST_TRANSIT = "matched", "amount differs", "not in our books", "not on statement", "paid - check in transit"


def build(seed: int) -> dict:
    r = rng(seed)
    base = r.randint(417200, 417600)
    docs = []

    def inv(d, amt, kind="INV"):
        nonlocal base
        base += r.randint(3, 29)
        docs.append({"no": base, "kind": kind, "date": d, "amt": amt, "job": r.choice(JOBS)})
        return docs[-1]

    # closed history: June and July bills paid in full, with their payments
    closed = [inv(day_in(r, date(2026, 6, 2), date(2026, 7, 20), True), money(r, 90, 2400)) for _ in range(9)]
    checks = []
    chk = r.randint(10310, 10390)
    for grp in (closed[:3], closed[3:6], closed[6:]):
        chk += r.randint(4, 15)
        checks.append({"no": chk, "date": max(x["date"] for x in grp) + timedelta(days=r.randint(9, 20)), "applied": grp,
                       "amt": round(sum(x["amt"] for x in grp), 2), "transit": False})
    # open on both sides
    open_both = [inv(day_in(r, date(2026, 7, 6), date(2026, 8, 26), True), money(r, 60, 3200)) for _ in range(12)]
    heater = inv(day_in(r, date(2026, 7, 22), date(2026, 8, 20), True), money(r, 1150, 1480))  # water heater, returned part later
    credit_both = {"no": base + r.randint(2, 9), "kind": "CM", "date": day_in(r, date(2026, 8, 3), date(2026, 8, 24), True),
                   "amt": -money(r, 40, 260), "job": r.choice(JOBS)}
    base = credit_both["no"]
    transit = [inv(day_in(r, date(2026, 7, 28), date(2026, 8, 18), True), money(r, 300, 2600)) for _ in range(2)]
    chk += r.randint(4, 15)
    checks.append({"no": chk, "date": date(2026, 8, 28), "applied": transit, "amt": round(sum(x["amt"] for x in transit), 2), "transit": True})
    missing_bill = inv(day_in(r, date(2026, 8, 10), date(2026, 8, 25), True), money(r, 180, 900))
    missing_credit = {"no": base + r.randint(2, 9), "kind": "CM", "date": day_in(r, date(2026, 8, 12), date(2026, 8, 27), True),
                      "amt": -money(r, 120, 480), "job": heater["job"]}
    base = missing_credit["no"]
    # cents differences
    t_stmt = 1000 + r.randint(100, 899) + r.choice([0.36, 0.47, 0.58, 0.69, 0.18, 0.29])
    s = f"{t_stmt:.2f}"
    ours = float(s[:-2] + s[-1] + s[-2])
    transpose = inv(day_in(r, date(2026, 8, 3), date(2026, 8, 21), True), round(t_stmt, 2))
    transpose["ours"] = round(ours, 2)
    rounding = inv(day_in(r, date(2026, 8, 3), date(2026, 8, 21), True), money(r, 200, 900))
    rounding["ours"] = round(rounding["amt"] + r.choice([0.01, -0.01]), 2)
    late_bill = inv(date(2026, 8, r.randint(29, 31)), money(r, 150, 1100))
    c0 = r.randint(10310, 10390)
    for c in sorted(checks, key=lambda c: c["date"]):
        c0 += r.randint(4, 15)
        c["no"] = c0
    # the supplier numbers documents in the order it issues them
    n0 = r.randint(417200, 417600)
    for x in sorted(docs + [credit_both, missing_credit], key=lambda x: (x["date"], r.random())):
        n0 += r.randint(3, 29)
        x["no"] = n0

    # ---- statement side (open items at the cutoff) and ledger side (our open items)
    stmt = open_both + [heater, credit_both] + transit + [missing_bill, missing_credit, transpose, rounding]
    ledger_open = open_both + [heater, credit_both, transpose, rounding, late_bill]
    rows = []
    for x in sorted(stmt + [late_bill], key=lambda x: (x["date"], x["no"])):
        s_amt = x["amt"] if x is not late_bill else 0.0
        if x in transit or x is missing_bill or x is missing_credit:
            o_amt = 0.0
        else:
            o_amt = x.get("ours", x["amt"])
        if x is late_bill:
            st = ST_STMT
        elif x in transit:
            st = ST_TRANSIT
        elif x is missing_bill or x is missing_credit:
            st = ST_BOOKS
        elif abs(s_amt - o_amt) > 0.001:
            st = ST_DIFF
        else:
            st = ST_MATCH
        rows.append({"doc": x, "type": "credit" if x["kind"] == "CM" else "invoice", "stmt": round(s_amt, 2), "ours": round(o_amt, 2),
                     "diff": round(s_amt - o_amt, 2), "status": st})
    stmt_total = round(sum(x["amt"] for x in stmt), 2)
    ours_total = round(sum(x.get("ours", x["amt"]) for x in ledger_open), 2)
    variance = round(stmt_total - ours_total, 2)
    assert abs(round(sum(rw["diff"] for rw in rows), 2) - variance) < 0.005
    return {"docs": docs, "closed": closed, "checks": checks, "open_both": open_both, "heater": heater, "credit_both": credit_both,
            "transit": transit, "missing_bill": missing_bill, "missing_credit": missing_credit, "transpose": transpose, "rounding": rounding,
            "late_bill": late_bill, "stmt": stmt, "ledger_open": ledger_open, "rows": rows, "stmt_total": stmt_total,
            "ours_total": ours_total, "variance": variance}


def naive_rows(d: dict) -> list[dict]:
    """Match statement lines to ledger bills by number, ignore open balances and anything within a dollar, credits as positive."""
    out = []
    ledger_bills = {x["no"]: x.get("ours", x["amt"]) for x in d["docs"] if x["kind"] == "INV" and x is not d["missing_bill"]}
    ledger_bills.update({d["credit_both"]["no"]: d["credit_both"]["amt"]})
    for x in d["stmt"]:
        s_amt = abs(x["amt"])
        o = ledger_bills.get(x["no"])
        if o is None:
            out.append({"doc": x, "type": "invoice", "stmt": s_amt, "ours": 0.0, "diff": s_amt, "status": ST_BOOKS})
        else:
            o = abs(o)
            out.append({"doc": x, "type": "invoice", "stmt": s_amt, "ours": o, "diff": round(s_amt - o, 2),
                        "status": ST_MATCH if abs(s_amt - o) < 1 else ST_DIFF})
    return out


def acceptable(d: dict) -> bool:
    nos = [x["no"] for x in d["docs"]] + [d["credit_both"]["no"], d["missing_credit"]["no"]]
    if len(set(nos)) != len(nos):
        return False
    chk_nos = {c["no"] for c in d["checks"]}
    if chk_nos & set(nos):
        return False
    if abs(d["transpose"]["amt"] - d["transpose"]["ours"]) < 0.09:
        return False
    return abs(d["variance"]) > 50


# --------------------------------------------------------------------------- emit

def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["reference", "type", "statement_amount", "our_amount", "difference", "status"]

    def csv_rows(rows):
        return [[rw["doc"]["no"], rw["type"], f"{rw['stmt']:.2f}", f"{rw['ours']:.2f}", f"{rw['diff']:.2f}", rw["status"]] for rw in rows]

    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_csv(os.path.join(naive_dir, "vendor_recon.csv"), header, csv_rows(naive_rows(d)))
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 21)

    # ---- workspace: the supplier's statement (PDF)
    lines = [["Date", "Document", "Job / PO", "Original", "Open amount", "Age"]]
    for x in sorted(d["stmt"], key=lambda x: (x["date"], x["no"])):
        age = (STMT_DATE - x["date"]).days
        bucket = "Current" if age <= 30 else "31-60" if age <= 60 else "61-90"
        amt = x["amt"]
        lines.append([x["date"].strftime("%m/%d/%y"), f"{x['kind']} {x['no']:07d}", x["job"], f"{amt:,.2f}" if amt > 0 else f"{-amt:,.2f} CR",
                      f"{amt:,.2f}" if amt > 0 else f"{-amt:,.2f} CR", bucket])
    aging = {"Current": 0.0, "31-60": 0.0, "61-90": 0.0}
    for x in d["stmt"]:
        age = (STMT_DATE - x["date"]).days
        aging["Current" if age <= 30 else "31-60" if age <= 60 else "61-90"] += x["amt"]
    write_pdf_document(os.path.join(ws, "keystone_statement_2026-08.pdf"), [
        ("title", "Keystone Plumbing Supply"),
        ("small", "Branch 14 - 2210 Industrial Pkwy - Columbus, OH 43215 - (614) 555-0148"),
        ("hr", None),
        ("kv", [("Statement date", STMT_DATE.strftime("%B %d, %Y")), ("Account", "WESTBR-0092  Westbrook Plumbing LLC"),
                ("Activity through", CUTOFF.strftime("%m/%d/%Y")), ("Terms", "Net 30")]),
        ("spacer", 8),
        ("h", "Open items"),
        ("table", lines, {"col_widths": [52, 82, 150, 70, 76, 50], "shade_header": True}),
        ("spacer", 8),
        ("table", [["Current", "31-60 days", "61-90 days", "TOTAL DUE"],
                   [f"{aging['Current']:,.2f}", f"{aging['31-60']:,.2f}", f"{aging['61-90']:,.2f}", f"{d['stmt_total']:,.2f}"]],
         {"col_widths": [90, 90, 90, 110], "grid": True}),
        ("spacer", 10),
        ("small", "Payments received after the activity date are not reflected. CR = credit memo, deducted from the amount due. "
                  "Please reference invoice numbers on your remittance."),
    ], font="Helvetica", base_size=9)

    # ---- workspace: our AP vendor ledger (CSV)
    led = []
    open_ids = {id(x) for x in d["ledger_open"]}
    for x in d["docs"]:
        if x is d["missing_bill"]:
            continue
        paid = not (id(x) in open_ids)
        amt = x.get("ours", x["amt"])
        led.append([x["date"], "Bill", str(x["no"]), x["job"], "5000 Job Materials", f"{amt:,.2f}", "0.00" if paid else f"{amt:,.2f}", ""])
    cb = d["credit_both"]
    led.append([cb["date"], "Vendor Credit", f"CM{cb['no']}", f"Return - {cb['job']}", "5000 Job Materials", f"{cb['amt']:,.2f}", f"{cb['amt']:,.2f}", ""])
    for c in d["checks"]:
        led.append([c["date"], "Bill Pmt -Check", str(c["no"]), "Keystone Plumbing Supply", "1010 Operating Checking", f"{-c['amt']:,.2f}", "0.00",
                    "Applied to " + ", ".join(str(x["no"]) for x in c["applied"])])
    led.sort(key=lambda x: (x[0], x[2]))
    write_csv(os.path.join(ws, "ap_vendor_ledger_keystone.csv"),
              ["Date", "Transaction Type", "Num", "Memo", "Account", "Amount", "Open Balance", "Payment detail"],
              [[x[0].strftime("%m/%d/%Y")] + x[1:] for x in led],
              preamble=["Westbrook Plumbing LLC", "Vendor Transaction Report - Keystone Plumbing Supply", "June 1 - August 31, 2026", ""],
              crlf=True)

    # ---- workspace: the office manager's note
    write_text(os.path.join(ws, "note_statement_recon.txt"),
               "Keystone statement came in - can you tie it out against our books before I pay them?\n\n"
               "How I do it:\n"
               "- Only open items matter: everything still open on their statement, and every bill or credit still open in our\n"
               "  books (Open Balance not zero). Paid-off bills and the checks that paid them are history.\n"
               "- One line per document. Reference = their document number, digits only, no leading zeros (INV 0418102 is 418102).\n"
               "- Type is invoice or credit. Amounts are what the document does to what we owe: invoices positive, credits negative\n"
               "  with a minus sign. Put 0.00 on the side that does not have the document.\n"
               "- Difference = statement amount minus our amount.\n"
               "- Status, one of:\n"
               "    matched                  - open on both, same amount\n"
               "    amount differs           - open on both, amounts not the same, even by a penny\n"
               "    not in our books         - on their statement, and our ledger has no bill or credit for it at all\n"
               "    not on statement         - open in our books, not on their statement\n"
               "    paid - check in transit  - open on their statement but we already paid it (check not on their statement yet)\n"
               "- Columns: reference, type, statement_amount, our_amount, difference, status. No total line - I add up the\n"
               "  difference column myself and it should come to their total due minus our open balance.\n\n"
               "- Luis\n")

    # ---- reference
    body = csv_rows(d["rows"])
    write_csv(os.path.join(ref, "vendor_recon.csv"), header, body)
    write_csv(os.path.join(sol, "vendor_recon.csv"), header, body)
    write_json(os.path.join(ref, "notes.json"), {"statement_total_due": f"{d['stmt_total']:.2f}", "our_open_balance": f"{d['ours_total']:.2f}",
                                                  "variance": f"{d['variance']:.2f}"})
    pins = [str(x["no"]) for x in d["transit"]] + [str(d["missing_credit"]["no"]), str(d["missing_bill"]["no"]), str(d["transpose"]["no"]),
                                                   str(d["rounding"]["no"]), str(d["late_bill"]["no"]), str(d["credit_both"]["no"])]
    tp, rd = d["transpose"], d["rounding"]
    write_task_yaml(HERE, {
        "id": "vendor-statement-reconcile", "track": "desk", "category": "bookkeeping",
        "title": "Tie out the Keystone supply statement to our books",
        "ask": "Keystone's August statement is in the folder with our ledger for them. Reconcile the two before we pay, Luis's note has how he likes it done. Save it as vendor_recon.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the statement prints 'INV 0418102' and 'CM 0418240' while the ledger uses '418102' and 'CM418240'; matching the raw strings "
            "leaves every line unmatched (checks: one row per open item; status per document)",
            f"credit memo {d['missing_credit']['no']} on the statement was never entered in our books, and credits print with a trailing CR "
            "and must be negative (checks: status per document; difference per document)",
            f"invoices {d['transit'][0]['no']} and {d['transit'][1]['no']} are still open on the statement but check {d['checks'][-1]['no']} "
            "dated 08/28 paid them and had not reached the supplier by its 08/28 activity date; they are paid - check in transit with our amount 0.00, not "
            "'not in our books' and not matched (checks: status per document; difference per document)",
            f"invoice {tp['no']} is {tp['amt']:,.2f} on the statement and {tp['ours']:,.2f} in our ledger, and {rd['no']} differs by one "
            "cent; both are amount differs, which a match within a dollar or a cent calls matched (checks: status per document; "
            "difference per document)",
            f"bill {d['late_bill']['no']} is dated after the statement's 08/28 activity date and is open only in our books "
            "(check: status per document)",
            f"invoice {d['missing_bill']['no']} is on the statement but was never entered as a bill (check: status per document)",
            "the ledger report also carries nine June and July bills with zero open balance and the checks that paid them, under a "
            "four-line preamble with CRLF endings (checks: one row per open item; row count)",
            "the difference column must add up to the statement's total due less our open balance "
            "(check: variance ties to the balances)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "note's columns", "path": "vendor_recon.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per open item", "path": "vendor_recon.csv", "column": "reference", "ref": "vendor_recon.csv",
             "normalize": ["digits"]},
            {"type": "csv_row_count", "name": "row count", "path": "vendor_recon.csv", "equals_ref": "vendor_recon.csv"},
            {"type": "csv_values_match", "name": "status per document", "path": "vendor_recon.csv", "ref": "vendor_recon.csv", "key": "reference",
             "columns": ["status"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": pins},
            {"type": "csv_values_match", "name": "difference per document", "path": "vendor_recon.csv", "ref": "vendor_recon.csv",
             "key": "reference", "columns": ["statement_amount", "our_amount", "difference"], "numeric": True, "tolerance": 0.005,
             "min_accuracy": 1.0, "must_match_keys": pins},
            {"type": "custom", "name": "variance ties to the balances", "module": "check.py"},
        ],
    })
    print(f"seed={seed} rows={len(d['rows'])} stmt_total={d['stmt_total']} ours={d['ours_total']} variance={d['variance']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a_ = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a_.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a_.seed * 1000 + attempt, a_.naive)
