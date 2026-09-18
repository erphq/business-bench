#!/usr/bin/env python3
"""ynab-transactions-import: a credit union checking export turned into YNAB's CSV file-import format.

    python gen.py [--seed N] [--naive DIR]

Business: Pell & Fairweather Bookbinding, a two-person bindery, budgets its business checking account in YNAB.
The credit union's direct import broke in August, so September goes in by file.

Traps (each caught by a check, see task.yaml):
  * one Amount column, always positive, with a DEBIT/CREDIT type; YNAB wants Outflow and Inflow, the other
    side left empty                                                          (check: outflow and inflow)
  * payees come from the owner's rename rules, first matching rule wins, and overlapping rules
    (AMAZON PRIME before AMAZON, UPS STORE before UPS) make a last-match loop wrong; transfers use
    YNAB's "Transfer : Account" payee                                       (check: payee)
  * YNAB's Memo is the bank Reference with its leading zeros, not the bank's Memo column (check: one row per transaction)
  * YNAB matches on the purchase date: Tran Date (MM/DD/YY in the export) written MM/DD/YYYY, not Post Date
                                                                             (check: date)
  * the export starts Aug 20; YNAB already has everything with a transaction date through Aug 31, and one
    Aug 31 purchase posted on Sep 1                                          (checks: one row per transaction; row count)
  * pending rows have no reference yet and must wait                          (check: row count)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["Date", "Payee", "Memo", "Outflow", "Inflow"]
# (match text, payee) in the owner's order: first match wins
RULES = [("AMAZON PRIME", "Amazon Prime"), ("ONLINE TRANSFER", "Transfer : Studio Savings"), ("AMAZON", "Amazon"),
         ("AMZN", "Amazon"), ("TALAS", "Talas"), ("HOLLANDER", "Hollander's"), ("UPS STORE", "The UPS Store"),
         ("UPS", "UPS"), ("USPS", "USPS"), ("ETSY", "Etsy"), ("PAYPAL", "PayPal"), ("SQUARE", "Square"),
         ("ADOBE", "Adobe"), ("COMCAST", "Comcast"), ("PGANDE", "PG&E"), ("MILLBROOK PROP", "Millbrook Properties"),
         ("SHOPIFY", "Shopify"), ("BLUE BOTTLE", "Blue Bottle Coffee"), ("OFFICE DEPOT", "Office Depot"),
         ("CASCADE CU", "Cascade Credit Union")]
# (description template, type, lo, hi, weight)
KINDS = [
    ("DBT CRD {mmdd} AMZN MKTP US*{c6} SEATTLE WA", "DEBIT", 12, 140, 3),
    ("POS PURCHASE {mmdd} TALAS DIV OF TECHNICAL LIB BROOKLYN NY", "DEBIT", 60, 480, 3),
    ("ACH DEBIT HOLLANDERS DECORATIVE ANN ARBOR MI", "DEBIT", 45, 390, 2),
    ("DBT CRD {mmdd} THE UPS STORE #4402 PORTLAND OR", "DEBIT", 9, 65, 2),
    ("ACH DEBIT UPS BILLING {c6}", "DEBIT", 20, 140, 2),
    ("DBT CRD {mmdd} USPS PO 4057120331 PORTLAND OR", "DEBIT", 6, 48, 3),
    ("DBT CRD {mmdd} PAYPAL *ETSY LABELS 402-935-7733 CA", "DEBIT", 8, 40, 2),
    ("ACH DEBIT PAYPAL INST XFER {c6}", "DEBIT", 20, 90, 1),
    ("ACH CREDIT ETSY INC PAYOUT {c6}", "CREDIT", 180, 1400, 3),
    ("ACH CREDIT SQUARE INC SDV{c6}", "CREDIT", 90, 900, 3),
    ("DBT CRD {mmdd} BLUE BOTTLE COFFEE PORTLAND OR", "DEBIT", 4.5, 18, 2),
    ("POS PURCHASE {mmdd} OFFICE DEPOT #2231 PORTLAND OR", "DEBIT", 12, 160, 1),
]
# monthly bills on fixed days: (day of month, description, amount or (lo, hi))
BILLS = [(1, "ACH DEBIT MILLBROOK PROPERTIES RENT", 1850.0), (5, "ACH DEBIT ADOBE *CREATIVE CLOUD", 59.99),
         (8, "ACH DEBIT SHOPIFY* {c6}", 39.0), (10, "ACH DEBIT PGANDE WEB ONLINE", (80, 210)),
         (28, "ACH DEBIT COMCAST BUSINESS 8155", 129.9)]
BANK_MEMO = {"DBT CRD": "POS DEBIT NON-PIN", "POS PURCHASE": "POS PURCHASE PIN", "ACH DEBIT": "ELECTRONIC WITHDRAWAL",
             "ACH CREDIT": "ELECTRONIC DEPOSIT", "ONLINE": "HOME BANKING TRANSFER"}


def payee_for(desc: str) -> str:
    u = desc.upper()
    for m, p in RULES:
        if m in u:
            return p
    raise ValueError(desc)


def last_match_payee(desc: str) -> str:
    out = None
    for m, p in RULES:
        if m in desc.upper():
            out = p
    return out


def build(seed: int) -> dict:
    r = rng(seed)
    txns = []
    weights = [k[4] for k in KINDS]
    start, end = date(2026, 8, 20), date(2026, 9, 12)
    d = start
    while d <= end:
        for _ in range(r.choice([0, 1, 1, 2, 2, 3]) if d.weekday() < 5 else r.choice([0, 1])):
            k = r.choices(KINDS, weights)[0]
            desc = k[0].format(mmdd=d.strftime("%m%d"), c6=code(r, 6, "0123456789"))
            amt = k[2] if k[2] == k[3] else money(r, k[2], k[3])
            lag = 0 if desc.startswith("ACH") else min(r.choice([1, 1, 2, 3]), (end - d).days)
            txns.append({"tran": d, "post": d + timedelta(days=lag), "desc": desc, "type": k[1], "amt": amt})
        d += timedelta(days=1)
    for day, desc, amt in BILLS:
        for mm in (8, 9):
            dd = date(2026, mm, day)
            if start <= dd <= end:
                txns.append({"tran": dd, "post": dd, "type": "DEBIT", "desc": desc.format(c6=code(r, 6, "0123456789")),
                             "amt": money(r, *amt) if isinstance(amt, tuple) else amt})
    # transfers to and from savings
    for dd, typ, amt in ((date(2026, 8, 25), "DEBIT", 500.0), (date(2026, 9, 4), "DEBIT", 750.0), (date(2026, 9, 9), "CREDIT", 1200.0)):
        txns.append({"tran": dd, "post": dd, "type": typ, "amt": amt,
                     "desc": f"ONLINE TRANSFER {'TO' if typ == 'DEBIT' else 'FROM'} SAVINGS XXXXXX0093"})
    # a refund from a merchant is an inflow with the merchant as payee
    txns.append({"tran": date(2026, 9, 8), "post": date(2026, 9, 10), "type": "CREDIT", "amt": money(r, 20, 90),
                 "desc": f"DBT CRD RETURN 0908 AMZN MKTP US*{code(r, 6, '0123456789')} SEATTLE WA"})
    # the boundary purchase: bought Aug 31, posted Sep 1 - already in YNAB
    txns.append({"tran": date(2026, 8, 31), "post": date(2026, 9, 1), "type": "DEBIT", "amt": money(r, 60, 300),
                 "desc": "POS PURCHASE 0831 TALAS DIV OF TECHNICAL LIB BROOKLYN NY"})
    # overlapping-rule rows that a last-match loop gets wrong
    txns.append({"tran": date(2026, 9, 3), "post": date(2026, 9, 4), "type": "DEBIT", "amt": 14.99,
                 "desc": f"DBT CRD 0903 AMAZON PRIME*{code(r, 6, '0123456789')} AMZN.COM/BILL WA"})
    txns.append({"tran": date(2026, 9, 10), "post": date(2026, 9, 11), "type": "DEBIT", "amt": money(r, 9, 40),
                 "desc": "DBT CRD 0910 THE UPS STORE #4402 PORTLAND OR"})
    txns.append({"tran": date(2026, 9, 2), "post": date(2026, 9, 3), "type": "DEBIT", "amt": money(r, 8, 40),
                 "desc": "DBT CRD 0902 PAYPAL *ETSY LABELS 402-935-7733 CA"})
    txns.sort(key=lambda t: (t["post"], t["desc"]))
    used = set()
    for t in txns:
        while True:
            ref_ = f"{r.randint(0, 99999):09d}" if r.random() < 0.7 else f"{r.randint(100000, 999999999):09d}"
            if ref_ not in used:
                break
        used.add(ref_)
        t["ref"] = ref_
        t["status"] = "Posted"
    # pending: bought in the last two days, not posted, no reference yet
    for dd in (date(2026, 9, 11), date(2026, 9, 12), date(2026, 9, 12)):
        k = r.choice([k for k in KINDS if k[1] == "DEBIT" and k[2] != k[3]])
        txns.append({"tran": dd, "post": None, "desc": k[0].format(mmdd=dd.strftime("%m%d"), c6=code(r, 6, "0123456789")), "type": "DEBIT",
                     "amt": money(r, k[2], k[3]), "ref": "", "status": "Pending"})
    refs = [t["ref"] for t in txns if t["ref"]]
    assert len(set(refs)) == len(refs)
    keep = [t for t in txns if t["status"] == "Posted" and t["tran"] >= date(2026, 9, 1)]
    return {"txns": txns, "keep": keep}


def acceptable(d: dict) -> bool:
    keep = d["keep"]
    overlap = [t for t in keep if payee_for(t["desc"]) != last_match_payee(t["desc"])]
    inflows = [t for t in keep if t["type"] == "CREDIT"]
    lagged = [t for t in keep if t["post"] != t["tran"]]
    return len(overlap) >= 3 and len(inflows) >= 5 and len(lagged) >= 8 and 26 <= len(keep) <= 45


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    bal = 8420.55
    bank_rows = []
    for t in d["txns"]:
        if t["status"] == "Posted":
            bal = round(bal + (t["amt"] if t["type"] == "CREDIT" else -t["amt"]), 2)
        prefix = next(p for p in BANK_MEMO if t["desc"].startswith(p))
        amt = f"{t['amt']:,.2f}" if t["amt"] >= 1000 else f"{t['amt']:.2f}"
        bank_rows.append([t["post"].isoformat() if t["post"] else "", t["tran"].strftime("%m/%d/%y"), t["ref"], t["desc"],
                          BANK_MEMO[prefix], amt, t["type"], t["status"], f"{bal:.2f}" if t["status"] == "Posted" else ""])
    write_csv(os.path.join(ws, "cascade_cu_checking_0820-0912.csv"),
              ["Post Date", "Tran Date", "Reference", "Description", "Memo", "Amount", "Type", "Status", "Balance"], bank_rows,
              preamble=["Cascade Credit Union", "Business Checking ******4471", "Transactions 08/20/2026 - 09/12/2026", ""],
              crlf=True)
    write_csv(os.path.join(ws, "ynab_payee_rules.csv"), ["Order", "If description contains", "Rename payee to"],
              [[i + 1, m.title() if i % 3 == 0 else m.lower() if i % 3 == 1 else m, p] for i, (m, p) in enumerate(RULES)])
    write_csv(os.path.join(ws, "ynab_import_template.csv"), HEADER,
              [["09/01/2026", "Sample Payee", "000000123", "12.50", ""], ["09/01/2026", "Sample Refund", "000000124", "", "12.50"]])
    write_text(os.path.join(ws, "ynab_import_notes.txt"),
               "How I load the checking account into YNAB by file (bank sync is broken again)\n"
               "- Wren\n"
               "\n"
               "YNAB already has everything up to and including August 31 (by the date I actually bought\n"
               "things), so only September goes in. The bank export always starts a couple of weeks early.\n"
               "\n"
               "Leave out anything still pending - it gets a new reference when it posts and I end up with\n"
               "doubles.\n"
               "\n"
               "Columns exactly like the template: Date, Payee, Memo, Outflow, Inflow.\n"
               "\n"
               "Date - the Tran Date, not the Post Date. YNAB matches on the day the purchase happened.\n"
               "  My file import is set to MM/DD/YYYY, four-digit year.\n"
               "Payee - put the bank description through my payee rules (ynab_payee_rules.csv). Go down the\n"
               "  list in order and use the FIRST rule whose text is in the description (capitals don't\n"
               "  matter). Transfers to/from savings come out as YNAB transfers that way.\n"
               "Memo - the bank's Reference number, exactly as it is on the export including the zeros in\n"
               "  front. That's how I find things later. NOT the bank's Memo column, that's just noise.\n"
               "Outflow / Inflow - money out (DEBIT) goes in Outflow, money in (CREDIT) goes in Inflow.\n"
               "  Plain numbers, and leave the other column empty on each row.\n")

    rows = [[t["tran"].strftime("%m/%d/%Y"), payee_for(t["desc"]), t["ref"], f"{t['amt']:.2f}" if t["type"] == "DEBIT" else "",
             f"{t['amt']:.2f}" if t["type"] == "CREDIT" else ""] for t in d["keep"]]
    write_csv(os.path.join(ref, "ynab.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "ynab.csv"), HEADER, rows)
    keep = d["keep"]
    payee_pins = sorted({t["ref"] for t in keep if payee_for(t["desc"]) != last_match_payee(t["desc"]) or "TRANSFER" in t["desc"]})
    flow_pins = sorted({t["ref"] for t in keep if t["type"] == "CREDIT"})
    date_pins = sorted({t["ref"] for t in keep if t["post"] != t["tran"]})[:12]
    boundary = next(t for t in d["txns"] if t["tran"] == date(2026, 8, 31) and t["post"] == date(2026, 9, 1))
    write_json(os.path.join(ref, "notes.json"), {"rows": len(rows), "boundary_ref_excluded": boundary["ref"],
                                                  "pending": sum(1 for t in d["txns"] if t["status"] == "Pending")})
    write_task_yaml(HERE, {
        "id": "ynab-transactions-import", "track": "desk", "category": "reformatting",
        "title": "September checking transactions into YNAB",
        "ask": ("The bank sync in YNAB is broken again. Can you turn the checking export into a file I can import and "
                "save it as ynab.csv? My notes on how I do it, the payee rules and YNAB's template are in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the export has one positive Amount column and a DEBIT/CREDIT Type; YNAB wants DEBIT in Outflow and CREDIT "
            "in Inflow with the other side empty, and the Amazon return, the Etsy and Square payouts and the transfer "
            "from savings are inflows (check: outflow and inflow)",
            "payees come from the rename rules in order, first match wins; AMAZON PRIME sits above AMAZON and UPS STORE "
            "above UPS, so a loop that lets the last matching rule win names them Amazon and UPS; transfers come out "
            "as 'Transfer : Studio Savings' (check: payee)",
            "YNAB's Memo is the bank Reference kept as text with its leading zeros (000041882); reading the column as a "
            "number or copying the bank's Memo column (ELECTRONIC WITHDRAWAL) loses the key "
            "(check: one row per transaction)",
            "card purchases post one to three days after the purchase; Date is the Tran Date, which the export writes "
            "as MM/DD/YY, written MM/DD/YYYY; using Post Date shifts most card rows (check: date)",
            "the export starts Aug 20 and YNAB already has everything with a transaction date through Aug 31; a Talas "
            "purchase made Aug 31 posted Sep 1, so filtering on Post Date imports it twice "
            "(checks: one row per transaction; row count)",
            "three pending rows at the end have no Post Date and no Reference and must wait until they post "
            f"(check: row count, {len(rows)} rows)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "YNAB template columns, exact order", "path": "ynab.csv", "columns": HEADER, "exact": True},
            {"type": "csv_set_equal", "name": "one row per transaction", "path": "ynab.csv", "column": "Memo", "ref": "ynab.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "ynab.csv", "equals_ref": "ynab.csv"},
            {"type": "csv_values_match", "name": "date", "path": "ynab.csv", "ref": "ynab.csv", "key": "Memo", "columns": ["Date"],
             "normalize": ["strip"], "min_accuracy": 1.0, "must_match_keys": date_pins},
            {"type": "csv_values_match", "name": "payee", "path": "ynab.csv", "ref": "ynab.csv", "key": "Memo", "columns": ["Payee"],
             "min_accuracy": 1.0, "must_match_keys": payee_pins},
            {"type": "csv_values_match", "name": "outflow and inflow", "path": "ynab.csv", "ref": "ynab.csv", "key": "Memo",
             "columns": ["Outflow", "Inflow"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": flow_pins},
        ],
    })
    print(f"seed={seed} export={len(d['txns'])} keep={len(rows)} payee_pins={len(payee_pins)} flow_pins={len(flow_pins)}")


def write_naive(d: dict, out: str) -> None:
    """The obvious mapping: posted rows with Post Date in September, Post Date as the date, a rules loop where the
    last match wins, Amount into Outflow for DEBIT and Inflow for CREDIT, the reference kept as text."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for t in d["txns"]:
        if t["status"] != "Posted" or t["post"] < date(2026, 9, 1):
            continue
        rows.append([t["post"].strftime("%m/%d/%Y"), last_match_payee(t["desc"]), t["ref"],
                     f"{t['amt']:.2f}" if t["type"] == "DEBIT" else "", f"{t['amt']:.2f}" if t["type"] == "CREDIT" else ""])
    write_csv(os.path.join(out, "ynab.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(300):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
