#!/usr/bin/env python3
"""receipts-scanned: twelve phone-scanned receipts from a four-day trip -> one expense table.

    python gen.py [--seed N] [--naive DIR]

Business: a Blue Heron Consulting associate scanned every receipt from a client trip to Denver. The receipts are
image-only PDFs; finance wants one row per receipt on its template.

Traps (each caught by a check, see task.yaml):
  * restaurant and cab slips print an AMOUNT before tip; the tip and the new total are written in by hand, and on
    two slips only the tip is written, so the total must be added up        (check: tips and totals)
  * the Rio Grande Cantina slip was scanned twice: the merchant copy with the tip and a blank customer copy (checks: one row per receipt; tips and totals)
  * card slips date as MM/DD/YY, the hotel and shops as "10 SEP 2026"        (check: dates)
  * the hotel folio lists three nights and lodging tax; parking and fuel have no separate tax (check: subtotals and tax)
  * every receipt is an image; nothing can be read without OCR               (check: merchants)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["receipt_no", "date", "merchant", "subtotal", "tax", "tip", "total"]
A = lambda d: d.strftime("%m/%d/%y")               # card terminal
B = lambda d: d.strftime("%d %b %Y").upper()       # folio / shop register


def build(seed: int) -> dict:
    r = rng(seed)
    nums = set()

    def num(lo, hi):
        while True:
            v = str(r.randint(lo, hi))
            if v not in nums:
                nums.add(v); return v
    c2 = lambda lo, hi: round(r.uniform(lo, hi), 2)
    R = []

    def add(key, merchant, d, sub, tax, tip, total_written, style, **kw):
        tip = round(tip, 2); sub = round(sub, 2); tax = round(tax, 2)
        R.append({"key": key, "merchant": merchant, "date": d, "sub": sub, "tax": tax, "tip": tip,
                  "total": round(sub + tax + tip, 2), "total_written": total_written, "style": style, **kw})
    nights = 3; rate = float(r.choice([209, 219, 229, 239]))
    room = nights * rate
    night_tax = round(rate * 0.1575, 2)
    add("hotel", "Larimer Square Hotel", date(2026, 9, 11), room, nights * night_tax, 0, True, "folio", no=num(40000, 49999), rate=rate,
        nights=nights, night_tax=night_tax)
    fare = c2(31, 44)
    add("cab", "Mile High Cab Co", date(2026, 9, 8), fare, 0, float(r.choice([6, 7, 8])), True, "cab", no=num(5000, 5999))
    s = c2(48, 62)
    add("cantina", "Rio Grande Cantina", date(2026, 9, 8), s, s * 0.0831, float(r.choice([10, 11, 12])), True, "slip", no=num(1000, 1999))
    s = round(r.choice([8.25, 9.50, 10.75]), 2)
    add("coffee", "Corvus Coffee Roasters", date(2026, 9, 9), s, s * 0.0831, 1.00, True, "coffee", no=num(700000, 799999))
    s = c2(26, 36)
    add("snooze", "Snooze an AM Eatery", date(2026, 9, 9), s, s * 0.0831, float(r.choice([5, 6, 7])), False, "slip", no=num(2000, 2999))
    s = c2(40, 56)
    add("fedex", "FedEx Office", date(2026, 9, 9), s, s * 0.0831, 0, True, "shop", no=num(30000, 39999))
    s = c2(128, 156)
    add("guard", "Guard and Grace", date(2026, 9, 10), s, s * 0.0831, float(r.choice([26, 28, 30])), True, "slip", no=num(3000, 3999))
    add("parking", "Pikes Peak Parking", date(2026, 9, 11), 4 * 16.00, 0, 0, True, "parking", no=num(80000, 89999))
    gal = round(r.uniform(9.5, 12.5), 3); ppg = round(r.uniform(3.69, 3.99), 3)
    add("fuel", "Shell", date(2026, 9, 11), round(gal * ppg, 2), 0, 0, True, "fuel", no=num(600, 999), gal=gal, ppg=ppg)
    s = c2(14, 21)
    add("hudson", "Hudson News", date(2026, 9, 11), s, s * 0.0831, 0, True, "shop", no=num(50000, 59999))
    s = c2(88, 104)
    add("tavernetta", "Tavernetta", date(2026, 9, 10), s, s * 0.0831, float(r.choice([18, 20, 22])), False, "slip", no=num(4000, 4999))
    return {"receipts": R}


def lines_for(x: dict, copy: str | None = None) -> list[str]:
    m = x["merchant"].upper()
    if x["style"] == "folio":
        return [m, "1600 LARIMER ST DENVER CO 80202", "", "GUEST FOLIO", f"FOLIO: {x['no']}", "GUEST: DANA OKAFOR",
                f"ARRIVAL: {B(date(2026, 9, 8))}", f"DEPART: {B(x['date'])}", "",
                *[f"{B(date(2026, 9, 8 + i))} ROOM {x['rate']:.2f}" for i in range(x["nights"])],
                *[f"{B(date(2026, 9, 8 + i))} LODGING TAX {x['night_tax']:.2f}" for i in range(x["nights"])], "",
                f"ROOM CHARGES: {x['sub']:.2f}", f"TAXES: {x['tax']:.2f}", f"BALANCE PAID: {x['total']:.2f}",
                "PAID VISA XXXX4417", "", "THANK YOU FOR STAYING WITH US"]
    if x["style"] == "cab":
        return [m, "LICENSED DENVER TAXI", "", f"TRIP ID: {x['no']}", f"DATE: {A(x['date'])}", "FROM: DEN AIRPORT", "TO: 1600 LARIMER ST",
                "", f"FARE: {x['sub']:.2f}", f"TIP ADDED: {x['tip']:.2f}", f"TOTAL CHARGED: {x['total']:.2f}", "",
                "DRIVER 2231 CARD XXXX4417", "TIP AND TOTAL WRITTEN BY DRIVER"]
    if x["style"] == "slip":
        amount = round(x["sub"] + x["tax"], 2)
        if copy == "customer":
            tip_l, tot_l = "TIP ADDED: __________", "TOTAL CHARGED: __________"
        else:
            tip_l = f"TIP ADDED: {x['tip']:.2f}"
            tot_l = f"TOTAL CHARGED: {x['total']:.2f}" if x["total_written"] else "TOTAL CHARGED: __________"
        return [m, "DENVER CO", "", f"CHECK: {x['no']}", f"DATE: {A(x['date'])} TABLE 12", "SERVER: ALEX", "",
                f"SUBTOTAL: {x['sub']:.2f}", f"TAX: {x['tax']:.2f}", f"AMOUNT: {amount:.2f}", "VISA XXXX4417 APPROVED", "",
                "ADD TIP BELOW", tip_l, tot_l, "SIGNATURE X ______________", "", "CUSTOMER COPY" if copy == "customer" else "MERCHANT COPY"]
    if x["style"] == "coffee":
        return [m, "2500 LAWRENCE ST DENVER", "", f"RECEIPT: {x['no']}", f"DATE: {A(x['date'])}", "",
                f"SUBTOTAL: {x['sub']:.2f}", f"TAX: {x['tax']:.2f}", f"TIP AMOUNT: {x['tip']:.2f}", f"TOTAL: {x['total']:.2f}", "",
                "VISA XXXX4417", "THANK YOU"]
    if x["style"] == "shop":
        return [m, "DEN AIRPORT CONCOURSE B" if x["key"] == "hudson" else "1200 LARIMER ST DENVER", f"TRANS: {x['no']}", f"DATE: {B(x['date'])}", "", f"SUBTOTAL: {x['sub']:.2f}", f"SALES TAX: {x['tax']:.2f}",
                f"TOTAL: {x['total']:.2f}", "VISA XXXX4417", "", "NO RETURNS WITHOUT RECEIPT"]
    if x["style"] == "parking":
        return [m, "DENVER INTERNATIONAL AIRPORT", "", f"TICKET: {x['no']}", f"ENTRY: {B(date(2026, 9, 8))}", f"EXIT: {B(x['date'])}",
                "4 DAYS AT 16.00", "", f"TOTAL: {x['total']:.2f}", "TAXES INCLUDED", "VISA XXXX4417"]
    if x["style"] == "fuel":
        return [m, "STATION 57444 PENA BLVD DENVER", "", f"INVOICE: {x['no']}", f"DATE: {A(x['date'])}", "", "PUMP 6 UNLEADED",
                f"{x['gal']:.3f} GAL AT {x['ppg']:.3f}", "", f"TOTAL: {x['total']:.2f}", "VISA XXXX4417"]
    raise ValueError(x["style"])


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    R = d["receipts"]
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    S = os.path.join(ws, "denver_trip_receipts")
    order = ["cab", "cantina", "coffee", "snooze", "fedex", "guard", "tavernetta", "cantina_copy", "hotel", "parking", "fuel", "hudson"]
    names = [f"IMG_{4410 + i * 3}.pdf" for i in range(len(order))]
    rr = rng(seed + 11)
    rr.shuffle(names)
    by = {x["key"]: x for x in R}
    for i, (k, fn) in enumerate(zip(order, names)):
        x = by["cantina"] if k == "cantina_copy" else by[k]
        lines = lines_for(x, "customer" if k == "cantina_copy" else None)
        width = rr.choice([1100, 1240]) if x["style"] != "folio" else 1240
        write_scan_pdf(os.path.join(S, fn), lines, width=width, height=1754, font_size=rr.choice([30, 32]),
                       skew_deg=round(rr.uniform(-0.6, 0.6), 2), noise=rr.randint(250, 500), seed=seed * 31 + i)
    write_csv(os.path.join(ws, "expense_report_template.csv"), HEADER, [])
    write_text(os.path.join(ws, "finance_expense_instructions.txt"),
               "Expense reports - receipts\n\n"
               "Use the template: one row per receipt.\n\n"
               "  receipt_no  the receipt, check, folio, trip, ticket or invoice number printed on it (just the number)\n"
               "  date        the date on the receipt, as YYYY-MM-DD (for the hotel, the checkout date)\n"
               "  merchant    the business name as printed at the top\n"
               "  subtotal    before tax\n"
               "  tax         0 if none is shown separately\n"
               "  tip         0 if none\n"
               "  total       what was actually charged to the card, tip included\n\n"
               "Amounts as plain numbers. If a receipt shows up twice, report it once - we reimburse each charge one time.\n")
    write_text(os.path.join(ws, "note_from_dana.txt"),
               "Receipts from the Denver trip, Sept 8-11. I scanned everything on my phone. I tipped on the card slips at dinner - "
               "I wrote the tips in myself. Can you do the expense report?\n")
    rows = [[x["no"], x["date"].isoformat(), x["merchant"], f"{x['sub']:.2f}", f"{x['tax']:.2f}", f"{x['tip']:.2f}", f"{x['total']:.2f}"]
            for x in sorted(R, key=lambda x: (x["date"], x["no"]))]
    write_csv(os.path.join(ref, "expenses.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "expenses.csv"), HEADER, rows)
    write_json(os.path.join(ref, "notes.json"), {"files": dict(zip(order, names)), "duplicate_receipt": by["cantina"]["no"],
                                                  "tip_only_written": [x["no"] for x in R if not x["total_written"]]})
    tipped = [x["no"] for x in R if x["tip"] > 0]
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    P = "expenses.csv"
    write_task_yaml(HERE, {
        "id": "receipts-scanned", "track": "desk", "category": "extraction",
        "title": "Expense table from scanned trip receipts",
        "ask": ("Dana scanned all her Denver trip receipts. Please turn them into expenses.csv for reimbursement - finance's instructions "
                "and template are in the folder.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the four restaurant slips print an AMOUNT before tip and the tip is written in by hand; on the Snooze and Tavernetta "
            "slips only the tip is written and the total line is blank, so the charge is amount plus tip; the cab tip is also written in "
            "(check: tips and totals)",
            f"the Rio Grande Cantina check {by['cantina']['no']} was scanned twice, a merchant copy with the tip and a customer copy with blank "
            "tip and total lines; one row, carrying the tip (checks: one row per receipt; row count; tips and totals)",
            "card slips date as MM/DD/YY and the hotel, shops and parking as \"11 SEP 2026\"; the template wants YYYY-MM-DD and the hotel "
            "wants its checkout date, not arrival (check: dates)",
            "the hotel folio repeats nightly room and lodging-tax lines above its totals, and parking and fuel print only a total with no "
            "separate tax (check: subtotals and tax)",
            "every receipt is an image-only scan at a slight skew with dust; the text layer is empty (checks: merchants; one row per receipt)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per receipt", "path": P, "column": "receipt_no", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "merchants", "path": P, "ref": P, "key": "receipt_no", "columns": ["merchant"],
             "normalize": ["alnum"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "dates", "path": P, "ref": P, "key": "receipt_no", "columns": ["date"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "subtotals and tax", "path": P, "ref": P, "key": "receipt_no", "columns": ["subtotal", "tax"], **num},
            {"type": "csv_values_match", "name": "tips and totals", "path": P, "ref": P, "key": "receipt_no", "columns": ["tip", "total"],
             "must_match_keys": tipped, **num},
        ],
    })
    print(f"seed={seed} receipts={len(R)} files={len(order)} " + ", ".join(f"{x['key']}:{x['no']}={x['total']}" for x in R))


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: one row per file (the duplicate kept), the printed AMOUNT as the total and no tip on
    slips, dates copied as printed."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for x in d["receipts"] + [d["receipts"][2]]:
        slip = x["style"] == "slip"
        dt = A(x["date"]) if x["style"] in ("slip", "cab", "coffee", "fuel") else B(x["date"])
        total = round(x["sub"] + x["tax"], 2) if slip else x["total"]
        rows.append([x["no"], dt, x["merchant"], f"{x['sub']:.2f}", f"{x['tax']:.2f}", "0.00" if slip else f"{x['tip']:.2f}", f"{total:.2f}"])
    write_csv(os.path.join(out, "expenses.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
