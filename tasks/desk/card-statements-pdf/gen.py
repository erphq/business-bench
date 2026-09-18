#!/usr/bin/env python3
"""card-statements-pdf: three company card statements (one scanned) -> every August card transaction, fees on the purchase.

    python gen.py [--seed N] [--naive DIR]

Business: Fjord & Fell Adventures, a Bozeman tour operator that runs Iceland and Canadian Rockies trips, pays trip costs on
two card accounts. The bookkeeper books card spend by transaction date and wants each foreign fee on the purchase it belongs to.

Traps (each caught by a check, see task.yaml):
  * the Summit Bank card's statements run the 18th to the 17th, so both carry lines outside August, and posting dates differ
    from transaction dates across the month ends                                   (checks: one row per transaction; row count)
  * foreign transaction fees: Summit prints each as its own line with its own reference under the purchase; Harborline folds
    the fee into the purchase amount and notes it underneath                        (checks: one row per transaction; amounts; foreign fees)
  * payments and credits: a leading minus on Summit, a CR suffix on Harborline       (check: amounts)
  * Harborline's statement is one account ending in one number with two cardholder sections, each headed by its own card
    number, and prints Post Date before Trans Date                                  (check: cards and dates)
  * the Summit statement for 18 August to 17 September arrived by mail and is an image-only scan (checks: descriptions; amounts)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["txn_ref", "card_last4", "trans_date", "description", "amount", "foreign_fee"]
US = [("COSTCO WHSE #0891", 180, 420), ("REI 0144 BOZEMAN", 90, 360), ("SHELL OIL 57444", 55, 95), ("ADOBE *CREATIVE CLD", 54.99, 54.99),
      ("GOOGLE *GSUITE", 43.20, 43.20), ("MOUNTAIN WEST PRINTING", 120, 260), ("BOZEMAN YELLOWSTONE AIRPORT PKG", 48, 96),
      ("GALLATIN OUTDOOR SUPPLY", 70, 240), ("MAILCHIMP", 79, 79), ("STAPLES 0442", 25, 110)]
FX = [("STORMUR 4X4 RENTAL EHF", "ISK", 0.00719, 60000, 190000), ("HOTEL BRIMNES", "ISK", 0.00719, 70000, 240000),
      ("KAFFI HRAUN", "ISK", 0.00719, 9000, 30000), ("SOLVIK MARKET", "ISK", 0.00719, 12000, 45000),
      ("BANFF TRAIL OUTFITTERS", "CAD", 0.7288, 180, 900), ("LAKE LOUISE LODGE CAD", "CAD", 0.7288, 300, 1100)]


def build(seed: int) -> dict:
    r = rng(seed)
    used = set()

    def ref(n):
        while True:
            v = str(r.randint(10 ** (n - 1), 10 ** n - 1))
            if v not in used:
                used.add(v); return v
    last4 = r.sample(range(1000, 9999), 4)
    A_card, B_acct, B1, B2 = (str(x) for x in last4)
    holders = people(r, 2)
    us = list(US); r.shuffle(us)
    fx = list(FX); r.shuffle(fx)
    usi, fxi = iter(us * 3), iter(fx * 3)
    T = []   # every printed line, truth

    def add(stmt, card, td, pd, kind, desc=None, amount=None, fxinfo=None, section=None):
        if kind == "us":
            desc, lo, hi = next(usi)
            amount = round(r.uniform(lo, hi), 2)
        if kind == "fx":
            desc, ccy, rate, lo, hi = next(fxi)
            famt = float(r.randrange(lo, hi, 100)) if ccy == "ISK" else round(r.uniform(lo, hi), 2)
            amount = round(famt * rate, 2)
            fxinfo = {"ccy": ccy, "famt": famt, "rate": rate, "fee": round(amount * 0.03, 2), "fee_ref": ref(12) if stmt.startswith("A") else None}
        T.append({"stmt": stmt, "card": card, "td": td, "pd": pd, "kind": kind, "desc": desc, "amount": round(amount, 2), "fx": fxinfo,
                  "ref": ref(12) if stmt.startswith("A") else f"{ref(11)}", "section": section})
    D = lambda m, d: date(2026, m, d)
    # Summit Bank Visa, period 18 Jul - 17 Aug
    add("A1", A_card, D(7, 16), D(7, 18), "us")
    add("A1", A_card, D(7, 24), D(7, 25), "fx")
    add("A1", A_card, D(7, 31), D(8, 3), "us")
    add("A1", A_card, D(8, 1), D(8, 3), "us")
    add("A1", A_card, D(8, 5), D(8, 5), "pay", "PAYMENT RECEIVED - THANK YOU", -float(r.randrange(2400, 5200, 50)))
    add("A1", A_card, D(8, 7), D(8, 9), "fx")
    add("A1", A_card, D(8, 10), D(8, 11), "us")
    add("A1", A_card, D(8, 12), D(8, 12), "fee", "ANNUAL MEMBERSHIP FEE", 95.00)
    add("A1", A_card, D(8, 14), D(8, 16), "fx")
    add("A1", A_card, D(8, 16), D(8, 17), "refund", "REI 0144 BOZEMAN - RETURN", -round(r.uniform(40, 120), 2))
    # Summit Bank Visa, period 18 Aug - 17 Sep (scanned)
    add("A2", A_card, D(8, 18), D(8, 19), "us")
    add("A2", A_card, D(8, 21), D(8, 23), "fx")
    add("A2", A_card, D(8, 25), D(8, 26), "us")
    add("A2", A_card, D(8, 30), D(9, 1), "fx")
    add("A2", A_card, D(9, 3), D(9, 3), "pay", "PAYMENT RECEIVED - THANK YOU", -float(r.randrange(2400, 5200, 50)))
    add("A2", A_card, D(9, 8), D(9, 9), "us")
    add("A2", A_card, D(9, 12), D(9, 14), "us")
    # Harborline CU business Mastercard, August, two cardholders
    add("B", B1, D(7, 30), D(8, 1), "us", section=0)
    add("B", B1, D(8, 4), D(8, 5), "us", section=0)
    add("B", B1, D(8, 11), D(8, 12), "fx", section=0)
    add("B", B1, D(8, 22), D(8, 22), "pay", "AUTOPAY PAYMENT - THANK YOU", -float(r.randrange(1800, 4200, 25)), section=0)
    add("B", B1, D(8, 27), D(8, 28), "us", section=0)
    add("B", B2, D(8, 6), D(8, 7), "fx", section=1)
    add("B", B2, D(8, 15), D(8, 17), "refund", "GALLATIN OUTDOOR SUPPLY CREDIT", -round(r.uniform(30, 90), 2), section=1)
    add("B", B2, D(8, 19), D(8, 20), "us", section=1)
    add("B", B2, D(8, 29), D(8, 31), "fx", section=1)
    rows = []
    for t in T:
        if t["td"].month != 8:
            continue
        fee = t["fx"]["fee"] if t["fx"] else 0.0
        rows.append([t["ref"], t["card"], t["td"].isoformat(), t["desc"], f"{t['amount']:.2f}", f"{fee:.2f}"])
    return {"T": T, "rows": rows, "A_card": A_card, "B_acct": B_acct, "B_cards": (B1, B2), "holders": holders}


def render(ws: str, d: dict, seed: int) -> dict:
    P = os.path.join(ws, "card_statements")
    os.makedirs(P, exist_ok=True)
    T = d["T"]
    files = {}
    # A1: Summit Bank, Helvetica, trans date first, fee lines of their own, minus for credits
    A1 = [t for t in T if t["stmt"] == "A1"]
    rows = [["Trans date", "Post date", "Reference", "Description", "Amount"]]
    for t in A1:
        desc = t["desc"]
        if t["fx"]:
            f = t["fx"]
            famt = f"{f['famt']:,.0f}" if f["ccy"] == "ISK" else f"{f['famt']:,.2f}"
            desc += f"<br/><font size=7>{f['ccy']} {famt} &nbsp;rate {f['rate']}</font>"
        rows.append([t["td"].strftime("%m/%d"), t["pd"].strftime("%m/%d"), t["ref"], desc, f"{t['amount']:,.2f}"])
        if t["fx"]:
            rows.append([t["td"].strftime("%m/%d"), t["pd"].strftime("%m/%d"), t["fx"]["fee_ref"], "FOREIGN TRANSACTION FEE", f"{t['fx']['fee']:,.2f}"])
    prev_bal = round(-min(t["amount"] for t in A1) + 412.37, 2)
    new_bal = round(prev_bal + sum(t["amount"] + (t["fx"]["fee"] if t["fx"] else 0) for t in A1), 2)
    files["A1"] = f"SummitBank_Visa_{d['A_card']}_2026-08-17.pdf"
    write_pdf_document(os.path.join(P, files["A1"]), [
        ("title", "Summit Bank Business Visa"), ("small", "FJORD &amp; FELL ADVENTURES LLC - 21 N Willson Ave, Bozeman MT 59715"), ("hr", None),
        ("kv", [("Account number", f"XXXX XXXX XXXX {d['A_card']}"), ("Statement closing date", "08/17/2026"),
                ("Billing period", "07/18/2026 - 08/17/2026"), ("Previous balance", f"${prev_bal:,.2f}"), ("New balance", f"${new_bal:,.2f}"), ("Payment due date", "09/12/2026")]), ("spacer", 8),
        ("h", "Transactions"), ("table", rows, {"col_widths": [55, 55, 90, 230, 70], "shade_header": True}), ("spacer", 6),
        ("small", "Foreign transaction fee: 3% of the U.S. dollar amount of each transaction made in a foreign currency. "
                  "Credits and payments are shown with a minus sign.")], pagesize="letter", font="Helvetica", base_size=9)
    # A2: scan of the next Summit statement
    A2 = [t for t in T if t["stmt"] == "A2"]
    L = ["SUMMIT BANK BUSINESS VISA", "FJORD AND FELL ADVENTURES LLC", f"ACCOUNT ENDING {d['A_card']}", "BILLING PERIOD 08/18/2026 - 09/17/2026", "",
         "TRANS DATE / POST DATE / REFERENCE", "DESCRIPTION / AMOUNT", ""]
    for t in A2:
        L.append(f"{t['td'].strftime('%m/%d')}  {t['pd'].strftime('%m/%d')}  REF {t['ref']}")
        L.append(f"   {t['desc']}  {t['amount']:.2f}")
        if t["fx"]:
            f = t["fx"]
            famt = f"{f['famt']:.0f}" if f["ccy"] == "ISK" else f"{f['famt']:.2f}"
            L.append(f"   {f['ccy']} {famt} RATE {f['rate']}")
            L.append(f"{t['td'].strftime('%m/%d')}  {t['pd'].strftime('%m/%d')}  REF {f['fee_ref']}")
            L.append(f"   FOREIGN TRANSACTION FEE  {f['fee']:.2f}")
    L += ["", "CREDITS AND PAYMENTS SHOWN WITH A MINUS SIGN"]
    files["A2"] = f"scan_summit_statement_{d['A_card']}_sept.pdf"
    write_scan_pdf(os.path.join(P, files["A2"]), L, font_size=30, skew_deg=0.4, noise=400, seed=seed * 29 + 1)
    # B: Harborline CU, Times, A4, post date first, two cardholder sections, CR suffix, fee folded into the amount
    B = [t for t in T if t["stmt"] == "B"]
    blocks = [("right", "HARBORLINE CREDIT UNION<br/>Business Mastercard Statement"), ("spacer", 4),
              ("p", f"FJORD &amp; FELL ADVENTURES LLC<br/>Account number ending {d['B_acct']}<br/>Statement period: August 1 - August 31, 2026"), ("spacer", 6)]
    for sec in (0, 1):
        h = d["holders"][sec]
        items = [t for t in B if t["section"] == sec]
        rows = [["Post Date", "Trans Date", "Ref #", "Description", "Amount"]]
        for t in items:
            amt = round(t["amount"] + (t["fx"]["fee"] if t["fx"] else 0), 2)
            desc = t["desc"]
            if t["fx"]:
                f = t["fx"]
                famt = f"{f['famt']:,.0f}" if f["ccy"] == "ISK" else f"{f['famt']:,.2f}"
                desc += f"<br/><font size=7>{famt} {f['ccy']} - includes foreign transaction fee of ${f['fee']:.2f}</font>"
            amt_s = f"{abs(amt):,.2f}CR" if amt < 0 else f"{amt:,.2f}"
            rows.append([t["pd"].strftime("%b %d"), t["td"].strftime("%b %d"), t["ref"], desc, amt_s])
        total = round(sum(t["amount"] + (t["fx"]["fee"] if t["fx"] else 0) for t in items), 2)
        blocks += [("h", f"{h[0].upper()} {h[1].upper()} - CARD ENDING {d['B_cards'][sec]}"),
                   ("table", rows, {"col_widths": [55, 55, 80, 230, 70], "grid": True}),
                   ("right", f"Total for card ending {d['B_cards'][sec]}: {abs(total):,.2f}{'CR' if total < 0 else ''}"), ("spacer", 6)]
    blocks += [("small", "CR = credit. Transactions made in a foreign currency include a 3% foreign transaction fee in the amount shown.")]
    files["B"] = f"Harborline_Mastercard_{d['B_acct']}_Aug2026.pdf"
    write_pdf_document(os.path.join(P, files["B"]), blocks, pagesize="a4", font="Times-Roman", base_size=10)
    return files


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    files = render(ws, d, seed)
    write_text(os.path.join(ws, "note_from_ingrid.txt"),
               "August card transactions\n\n"
               "Can you key everything on the company cards for August into card_transactions.csv? The statements are in card_statements. "
               "I book cards by the date of the transaction, not when the bank posted it, and I want one row per transaction:\n\n"
               "txn_ref - the bank's reference number for the transaction\n"
               "card_last4 - last four digits of the card it was made on\n"
               "trans_date - YYYY-MM-DD\n"
               "description - the merchant or payment line as printed (first line only)\n"
               "amount - in dollars; purchases and fees positive, payments, refunds and credits negative. For foreign purchases leave the bank's "
               "foreign transaction fee out of this amount...\n"
               "foreign_fee - ...and put it here, on the purchase it belongs to. 0 if none.\n\n"
               "Ingrid\n")
    write_csv(os.path.join(ref, "card_transactions.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "card_transactions.csv"), HEADER, d["rows"])
    T = d["T"]
    aug = lambda t: t["td"].month == 8
    fxr = [t["ref"] for t in T if t["fx"] and aug(t)]
    signed = [t["ref"] for t in T if t["amount"] < 0 and aug(t)]
    brefs = [t["ref"] for t in T if t["stmt"] == "B" and aug(t)]
    a2 = [t for t in T if t["stmt"] == "A2"]
    figs = []
    for t in a2:
        if not aug(t):
            continue
        figs += [t["ref"], f"{t['amount']:.2f}", t["desc"], t["td"].strftime("%m/%d")]
        if t["fx"]:
            figs += [t["fx"]["fee_ref"], f"{t['fx']['fee']:.2f}"]
    write_json(os.path.join(ref, "notes.json"), {"files": files, "fee_refs": [t["fx"]["fee_ref"] for t in T if t["fx"] and t["fx"]["fee_ref"]],
                                                  "outside_august": [t["ref"] for t in T if not aug(t)],
                                                  "scan_figures": {f"card_statements/{files['A2']}": figs}})
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    C = "card_transactions.csv"
    write_task_yaml(HERE, {
        "id": "card-statements-pdf", "track": "desk", "category": "extraction",
        "title": "August transactions from the company card statements",
        "ask": "Please key all of August's company card transactions from the statements in the folder into card_transactions.csv. Ingrid's note has how she books them.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the Summit Bank card's statements run 18 July to 17 August and 18 August to 17 September, so each carries July or September "
            "transactions, and three lines post in a different month from their transaction date (31 July posted 3 August, 30 August posted "
            "1 September, 30 July posted 1 August on Harborline); August is by transaction date (checks: one row per transaction; row count)",
            "foreign transaction fees: Summit prints each as its own 'FOREIGN TRANSACTION FEE' line with its own reference under the purchase, "
            "while Harborline folds the 3% fee into the purchase amount and notes it underneath; the fee belongs in foreign_fee on the purchase "
            "row and out of the amount (checks: one row per transaction; amounts; foreign fees)",
            "payments, refunds and credits are shown with a leading minus on Summit and a CR suffix on Harborline (check: amounts)",
            f"Harborline's statement is for an account ending {d['B_acct']} with two cardholder sections headed 'CARD ENDING {d['B_cards'][0]}' and "
            f"'CARD ENDING {d['B_cards'][1]}', and it prints Post Date before Trans Date (check: cards and dates)",
            "the Summit statement for 18 August to 17 September is an image-only scan (checks: descriptions; amounts; foreign fees)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": C, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per transaction", "path": C, "column": "txn_ref", "ref": C, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": C, "equals_ref": C},
            {"type": "csv_values_match", "name": "cards and dates", "path": C, "ref": C, "key": "txn_ref", "columns": ["card_last4", "trans_date"],
             "min_accuracy": 1.0, "must_match_keys": brefs},
            {"type": "csv_values_match", "name": "descriptions", "path": C, "ref": C, "key": "txn_ref", "columns": ["description"],
             "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": [t["ref"] for t in a2 if aug(t)]},
            {"type": "csv_values_match", "name": "amounts", "path": C, "ref": C, "key": "txn_ref", "columns": ["amount"],
             "must_match_keys": fxr + signed, **num},
            {"type": "csv_values_match", "name": "foreign fees", "path": C, "ref": C, "key": "txn_ref", "columns": ["foreign_fee"],
             "must_match_keys": fxr, **num},
        ],
    })
    print(f"seed={seed} rows={len(d['rows'])} files={len(files)}")


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: every line on every statement (July and September too), Summit fee lines as rows of their own,
    Harborline amounts as printed with the fee inside and CR read as positive, the account number as the card for Harborline,
    and the first date column as the transaction date."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for t in d["T"]:
        if t["stmt"] == "B":
            amt = abs(round(t["amount"] + (t["fx"]["fee"] if t["fx"] else 0), 2))
            rows.append([t["ref"], d["B_acct"], t["pd"].isoformat(), t["desc"], f"{amt:.2f}", "0.00"])
        else:
            rows.append([t["ref"], t["card"], t["td"].isoformat(), t["desc"], f"{t['amount']:.2f}", "0.00"])
            if t["fx"]:
                rows.append([t["fx"]["fee_ref"], t["card"], t["td"].isoformat(), "FOREIGN TRANSACTION FEE", f"{t['fx']['fee']:.2f}", "0.00"])
    write_csv(os.path.join(out, "card_transactions.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, build(a.seed), a.naive)
