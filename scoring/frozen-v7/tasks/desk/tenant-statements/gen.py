#!/usr/bin/env python3
"""tenant-statements: five landlord statements for two rented spaces -> one third-quarter tenant ledger.

    python gen.py [--seed N] [--naive DIR]

Business: Fernhill Dance Academy rents Suite 210 at Cannery Row Commons (statements from Wexford Property Services) and
storage unit B-4 at Tidewater Self Storage. The bookkeeper wants every charge and payment for July to September once.

Traps (each caught by a check, see task.yaml):
  * statement periods overlap: the two storage statements both cover August, and Wexford's August statement starts on
    20 July and repeats the 22 July payment                                         (checks: one row per entry; row count)
  * the storage rent was prepaid in June; "Prepaid rent applied" credits each month are not payments in the quarter
                                                                                     (checks: one row per entry; row count)
  * late fees: Wexford's sits in the activity table and is waived by a credit on the September statement; the storage
    late charge is printed in a "Fees assessed" box under the activity table          (checks: one row per entry; entry types; amounts)
  * Wexford prints payments and credits in parentheses; the storage statements print Charges and Credits columns, both positive (check: amounts)
  * the July statement opens with a balance forward and a 29 June payment, outside the quarter (check: one row per entry)
  * Wexford's September statement is an image-only scan                            (checks: descriptions; amounts)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["entry_ref", "unit", "entry_date", "entry_type", "description", "amount"]
Q_START, Q_END = date(2026, 7, 1), date(2026, 9, 30)


def paren(x: float) -> str:
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def build(seed: int) -> dict:
    r = rng(seed)
    used = set()

    def ref(prefix, lo, hi):
        while True:
            v = f"{prefix}{r.randint(lo, hi)}"
            if v not in used:
                used.add(v); return v
    D = lambda m, d: date(2026, m, d)
    rent = float(r.choice([2850, 2975, 3100, 3225]))
    cam = r.choice([412.50, 438.75, 465.00])
    util = [round(r.uniform(78, 195), 2) for _ in range(4)]   # May (billed June), June, July, August
    late = round(rent * 0.05, 2)
    W = []   # Wexford Suite 210 entries (truth, including out-of-quarter)

    def w(dt, kind, desc, amt, pre):
        W.append({"ref": ref(pre, 240000, 249999), "date": dt, "type": kind, "desc": desc, "amount": round(amt, 2), "unit": "Suite 210"})
    w(D(6, 29), "payment", "Payment - thank you (ACH)", -util[0], "PM-")
    w(D(7, 1), "charge", "Base rent July 2026", rent, "CH-")
    w(D(7, 1), "charge", "CAM estimate July 2026", cam, "CH-")
    w(D(7, 3), "payment", "Payment - thank you (ACH)", -(rent + cam), "PM-")
    w(D(7, 14), "charge", "Electric submeter reimbursement June", util[1], "CH-")
    w(D(7, 22), "payment", "Payment - thank you (check 3318)", -util[1], "PM-")
    w(D(8, 1), "charge", "Base rent August 2026", rent, "CH-")
    w(D(8, 1), "charge", "CAM estimate August 2026", cam, "CH-")
    w(D(8, 6), "late_fee", "Late fee - rent received after the 5th", late, "LF-")
    w(D(8, 9), "payment", "Payment - thank you (ACH)", -(rent + cam), "PM-")
    w(D(8, 14), "charge", "Electric submeter reimbursement July", util[2], "CH-")
    w(D(8, 21), "payment", "Payment - thank you (check 3342)", -util[2], "PM-")
    w(D(9, 1), "charge", "Base rent September 2026", rent, "CH-")
    w(D(9, 1), "charge", "CAM estimate September 2026", cam, "CH-")
    w(D(9, 2), "payment", "Payment - thank you (ACH)", -(rent + cam), "PM-")
    w(D(9, 10), "credit", "Late fee waived - August", -late, "CR-")
    w(D(9, 14), "charge", "Electric submeter reimbursement August", util[3], "CH-")
    w(D(9, 19), "payment", "Payment - thank you (check 3367)", -util[3], "PM-")
    bf_w = util[0]   # balance forward on 25 June: the May electric charge
    # Tidewater Self Storage unit B-4
    srent = float(r.choice([145, 165, 185]))
    card = 25.00
    lc = 15.00
    T = []

    def t(dt, kind, desc, amt, include=True, box=False):
        T.append({"ref": str(ref("", 5530000, 5539999)), "date": dt, "type": kind, "desc": desc, "amount": round(amt, 2), "unit": "Storage B-4",
                  "include": include, "box": box})
    t(D(7, 1), "charge", "Monthly rent - July", srent)
    t(D(7, 1), "applied", "Prepaid rent applied", -srent, include=False)
    t(D(8, 1), "charge", "Monthly rent - August", srent)
    t(D(8, 1), "applied", "Prepaid rent applied", -srent, include=False)
    t(D(8, 12), "charge", "Gate access card replacement", card)
    t(D(9, 1), "charge", "Monthly rent - September", srent)
    t(D(9, 1), "applied", "Prepaid rent applied", -srent, include=False)
    t(D(9, 5), "late_fee", "Late charge - unpaid balance", lc, box=True)
    t(D(9, 8), "payment", "Payment received - card", -(card + lc))
    rows = []
    for e in W + T:
        if e.get("include", True) and Q_START <= e["date"] <= Q_END:
            rows.append([e["ref"], e["unit"], e["date"].isoformat(), e["type"], e["desc"], f"{e['amount']:.2f}"])
    return {"W": W, "T": T, "rows": rows, "bf_w": bf_w, "prepaid": round(3 * srent, 2)}


def running(entries, opening):
    bal = opening; out = []
    for e in entries:
        bal = round(bal + e["amount"], 2); out.append((e, bal))
    return out, bal


def render(ws: str, d: dict, seed: int) -> dict:
    P = os.path.join(ws, "statements")
    os.makedirs(P, exist_ok=True)
    W, T = d["W"], d["T"]
    files = {}
    # Wexford statements: periods 26 Jun-25 Jul, 20 Jul-25 Aug (re-cut cycle), 26 Aug-25 Sep (scanned)
    periods = [("jul", date(2026, 6, 26), date(2026, 7, 25)), ("aug", date(2026, 7, 20), date(2026, 8, 25)), ("sep", date(2026, 8, 26), date(2026, 9, 25))]
    for key, a, b in periods:
        before = [e for e in W if e["date"] < a]
        opening = round(d["bf_w"] + sum(e["amount"] for e in before), 2)
        inper = [e for e in W if a <= e["date"] <= b]
        lines, closing = running(inper, opening)
        if key != "sep":
            rows = [["Date", "Doc #", "Description", "Amount", "Balance"], [a.strftime("%m/%d/%Y"), "", "Balance forward", "", paren(opening)]]
            rows += [[e["date"].strftime("%m/%d/%Y"), e["ref"], e["desc"], paren(e["amount"]), paren(bal)] for e, bal in lines]
            files[key] = f"Wexford_Suite210_statement_{b.strftime('%Y-%m')}.pdf"
            write_pdf_document(os.path.join(P, files[key]), [
                ("title", "Tenant Statement"), ("p", "WEXFORD PROPERTY SERVICES<br/>Cannery Row Commons - 400 Cannery Row, Suite 100, Monterey CA 93940"),
                ("hr", None),
                ("kv", [("Tenant", "Fernhill Dance Academy LLC"), ("Premises", "Suite 210"), ("Statement period", f"{a.strftime('%m/%d/%Y')} - {b.strftime('%m/%d/%Y')}"),
                        ("Statement date", b.strftime("%B %-d, %Y"))]), ("spacer", 8),
                ("table", rows, {"col_widths": [62, 70, 220, 75, 75], "shade_header": True}), ("spacer", 6),
                ("right", f"<b>Balance due {paren(closing)}</b>"),
                ("small", "Rent and CAM are due on the 1st; a late fee of 5% of base rent applies to rent received after the 5th. "
                          "Amounts in parentheses are payments and credits." + (" This statement's cycle was moved to start 07/20 after the "
                                                                                 "accounting system change." if key == "aug" else ""))],
                pagesize="letter", font="Helvetica", base_size=9.5)
        else:
            L = ["WEXFORD PROPERTY SERVICES", "TENANT STATEMENT", "", "TENANT FERNHILL DANCE ACADEMY LLC", "PREMISES SUITE 210",
                 f"PERIOD {a.strftime('%m/%d/%Y')} TO {b.strftime('%m/%d/%Y')}", "",
                 f"{a.strftime('%m/%d/%Y')}  BALANCE FORWARD  {opening:.2f}", ""]
            for e, bal in lines:
                L.append(f"{e['date'].strftime('%m/%d/%Y')}  {e['ref']}  {e['desc']}")
                L.append(f"      AMOUNT {e['amount']:.2f}   BALANCE {bal:.2f}")
            L += ["", f"BALANCE DUE  {closing:.2f}", "NEGATIVE AMOUNTS ARE PAYMENTS AND CREDITS"]
            files[key] = "scan_wexford_sept_statement.pdf"
            write_scan_pdf(os.path.join(P, files[key]), L, font_size=30, skew_deg=0.4, noise=450, seed=seed * 11 + 4)
    # Tidewater Self Storage: two overlapping two-month statements
    for key, a, b in (("st1", date(2026, 7, 1), date(2026, 8, 31)), ("st2", date(2026, 8, 1), date(2026, 9, 30))):
        before = [e for e in T if e["date"] < a]
        opening = round(sum(e["amount"] for e in before), 2)
        inper = [e for e in T if a <= e["date"] <= b]
        table_entries = [e for e in inper if not e["box"]]
        box = [e for e in inper if e["box"]]
        lines, closing = running(inper, opening)
        bal_of = {id(e): bal for e, bal in lines}
        rows = [["Date", "Trans ID", "Description", "Charges", "Credits", "Balance"]]
        rows.append([a.strftime("%d %b %Y"), "", "Opening balance", "", "", f"{opening:,.2f}"])
        for e in table_entries:
            ch = f"{e['amount']:,.2f}" if e["amount"] > 0 else ""
            cr = f"{-e['amount']:,.2f}" if e["amount"] < 0 else ""
            rows.append([e["date"].strftime("%d %b %Y"), e["ref"], e["desc"], ch, cr, f"{bal_of[id(e)]:,.2f}"])
        blocks = [
            ("right", "TIDEWATER SELF STORAGE<br/>1880 Del Monte Blvd, Seaside CA 93955"), ("spacer", 4), ("h", "Account Activity Statement"),
            ("p", f"Account holder: Fernhill Dance Academy<br/>Unit: B-4 (10x15 climate)<br/>Activity from {a.strftime('%d %b %Y')} through {b.strftime('%d %b %Y')}"),
            ("spacer", 6), ("table", rows, {"col_widths": [72, 60, 175, 58, 58, 58], "grid": True}), ("spacer", 6)]
        if box:
            blocks += [("h", "Fees assessed this period"),
                       ("table", [["Date", "Trans ID", "Fee", "Amount"]] + [[e["date"].strftime("%d %b %Y"), e["ref"], e["desc"], f"{e['amount']:,.2f}"] for e in box],
                        {"col_widths": [70, 70, 200, 60]})]
        blocks += [("spacer", 6), ("right", f"Ending balance {closing:,.2f}"),
                   ("small", "Prepaid rent on file is applied on the 1st of each month. Late charges post on the 5th for any unpaid balance.")]
        files[key] = f"TidewaterStorage_B4_{a.strftime('%b')}-{b.strftime('%b')}_2026.pdf"
        write_pdf_document(os.path.join(P, files[key]), blocks, pagesize="a4", font="Times-Roman", base_size=10)
    return files


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    files = render(ws, d, seed)
    write_text(os.path.join(ws, "note_from_camille.txt"),
               "Q3 rent ledger\n\n"
               "For the quarter close I need a ledger of everything on our two rented spaces for July 1 to September 30 - the studio "
               "(Suite 210, Wexford) and the storage unit (B-4 at Tidewater). All the statements they sent are in the statements folder. "
               "We prepaid the storage unit for July through September back in June, so that money is already on the books.\n\n"
               "Please save it as tenant_ledger.csv, one row per charge or payment, with:\n"
               "  entry_ref   the landlord's document or transaction number for the line\n"
               "  unit        Suite 210 or Storage B-4\n"
               "  entry_date  YYYY-MM-DD\n"
               "  entry_type  charge, late_fee, payment or credit (credit = something they reversed or waived)\n"
               "  description as printed\n"
               "  amount      charges and late fees positive, payments and credits negative\n\n"
               "Each thing only once, even if two statements show it. Balance lines aren't entries.\n\nCamille\n")
    write_csv(os.path.join(ref, "tenant_ledger.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "tenant_ledger.csv"), HEADER, d["rows"])
    W, T = d["W"], d["T"]
    inq = lambda e: Q_START <= e["date"] <= Q_END
    sep = [e for e in W if date(2026, 8, 26) <= e["date"] <= date(2026, 9, 25)]
    typed = [e["ref"] for e in W + T if e["type"] in ("late_fee", "credit", "payment") and inq(e)]
    signed = [e["ref"] for e in W + T if e["amount"] < 0 and e.get("include", True) and inq(e)] + [e["ref"] for e in T if e["box"]]
    scan_figs = [x for e in sep for x in (e["ref"], e["desc"], f"AMOUNT {e['amount']:.2f}")]
    write_json(os.path.join(ref, "notes.json"), {"files": files, "prepaid_applied": [e["ref"] for e in T if not e["include"]],
                                                  "out_of_quarter": [e["ref"] for e in W if not inq(e)],
                                                  "scan_figures": {f"statements/{files['sep']}": scan_figs}})
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    P = "tenant_ledger.csv"
    lf = [e for e in W if e["type"] == "late_fee"][0]
    write_task_yaml(HERE, {
        "id": "tenant-statements", "track": "desk", "category": "extraction",
        "title": "Third-quarter ledger from the landlord statements",
        "ask": ("Can you turn the landlord statements for the studio and the storage unit into a ledger for Q3? Save it as tenant_ledger.csv - "
                "Camille's note says how she wants it.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "statement periods overlap: Tidewater's July-August and August-September statements both list every August line, and Wexford's "
            "August statement was re-cut to start on 20 July so it repeats the 22 July check payment; each entry once "
            "(checks: one row per entry; row count)",
            "the storage unit was prepaid in June and each month shows a 'Prepaid rent applied' credit beside the rent; those are not payments "
            "or credits in the quarter and have no row (checks: one row per entry; row count)",
            f"late fees: Wexford's {lf['ref']} sits in the activity table and is waived by a credit on the September statement, and Tidewater's "
            "late charge is printed only in a 'Fees assessed this period' box under the activity table (checks: one row per entry; entry types; amounts)",
            "Wexford prints payments and credits in parentheses with a running balance, while Tidewater prints separate Charges and Credits "
            "columns with both positive (check: amounts)",
            "the July statement opens with a balance forward and a 29 June payment that falls before the quarter (checks: one row per entry; row count)",
            "Wexford's September statement is an image-only scan (checks: descriptions; amounts)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per entry", "path": P, "column": "entry_ref", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "unit and date", "path": P, "ref": P, "key": "entry_ref", "columns": ["unit", "entry_date"],
             "normalize": ["alnum"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "entry types", "path": P, "ref": P, "key": "entry_ref", "columns": ["entry_type"],
             "min_accuracy": 1.0, "must_match_keys": typed},
            {"type": "csv_values_match", "name": "descriptions", "path": P, "ref": P, "key": "entry_ref", "columns": ["description"],
             "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": [e["ref"] for e in sep]},
            {"type": "csv_values_match", "name": "amounts", "path": P, "ref": P, "key": "entry_ref", "columns": ["amount"],
             "must_match_keys": signed, **num},
        ],
    })
    print(f"seed={seed} rows={len(d['rows'])} files={len(files)}")


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: every line on every statement with a reference (overlaps repeated, the June payment and the
    prepaid-rent credits kept), the fees box missed, amounts copied as positive figures, everything typed charge or payment."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for e in d["W"]:
        rows.append([e["ref"], e["unit"], e["date"].isoformat(), "payment" if e["amount"] < 0 else "charge", e["desc"], f"{abs(e['amount']):.2f}"])
        if e["date"] == date(2026, 7, 22):
            rows.append(rows[-1][:])
    for e in d["T"]:
        if e["box"]:
            continue
        rows.append([e["ref"], e["unit"], e["date"].isoformat(), "payment" if e["amount"] < 0 else "charge", e["desc"], f"{abs(e['amount']):.2f}"])
        if e["date"].month == 8:
            rows.append(rows[-1][:])
    write_csv(os.path.join(out, "tenant_ledger.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, build(a.seed), a.naive)
