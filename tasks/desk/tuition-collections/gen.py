#!/usr/bin/env python3
"""tuition-collections: spring tuition collected vs outstanding by program for a Montessori school.

    python gen.py [--seed N] [--naive DIR]

Business: a 90-family independent school. Invoices come out of the billing system, payments out of the
bank feed, and the scholarships and sibling discounts live in the bursar's own spreadsheet.

Traps (each caught by a check, see task.yaml):
  * payment plans, with installments scheduled after the cut-off       (checks: Primary collected; total collected)
  * returned ACH payments still sit in the export                      (checks: Primary collected; total collected)
  * scholarships and sibling discounts are credits, not money received (checks: Toddler credits; Elementary outstanding)
  * sibling discounts are a percentage of that child's tuition         (check: Toddler credits)
  * payments with no family id carry the invoice in the bank memo      (check: Primary collected)
  * the autumn invoices are in the folder and are paid in the same feed (checks: total collected; total net due)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))



# bizgen.write_xlsx leaves openpyxl's save-time wall clock in docProps/core.xml, so two runs a
# second apart produce different bytes and the validator's determinism check fails intermittently.
# Local workaround (tasks/lib is not ours to change): pin dcterms:modified and re-freeze the zip.
import io as _io  # noqa: E402
import re as _re  # noqa: E402
import zipfile as _zip  # noqa: E402


def stable_xlsx(path: str, sheets: dict, creator: str = "Export") -> None:
    write_xlsx(path, sheets, creator=creator)
    with _zip.ZipFile(path) as z:
        items = sorted((n, z.read(n)) for n in z.namelist())
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as out:
        for name, data in items:
            if name == "docProps/core.xml":
                data = _re.sub(rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>",
                               b'<dcterms:modified xsi:type="dcterms:W3CDTF">2026-01-15T09:00:00Z</dcterms:modified>',
                               data)
            zi = _zip.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = _zip.ZIP_DEFLATED
            out.writestr(zi, data)
    write_bytes(path, buf.getvalue())

CUTOFF = date(2026, 6, 5)
PROGRAMS = [("Toddler", 4800.00, 18), ("Primary", 5400.00, 26), ("Lower Elementary", 6200.00, 22), ("Afterschool", 1150.00, 24)]
PROGRAM_NAMES = [p[0] for p in PROGRAMS]
METHODS = ["ACH", "Check", "Card", "ACH", "Bank transfer"]


def build(seed: int) -> dict:
    r = rng(seed)
    fams, inv_no, pay_no = [], 4000, 8000
    invoices, spring, autumn = [], [], []
    for prog, tuition, n in PROGRAMS:
        for i in range(n):
            first, last = person(r)
            fam = f"F-{1200 + len(fams)}"
            fams.append(fam)
            for term, pool in (("Spring 2026", spring), ("Autumn 2025", autumn)):
                inv_no += 1
                amt = tuition if term == "Spring 2026" else round(tuition * 0.96, 2)
                inv = {"no": f"INV-2026-{inv_no}" if term == "Spring 2026" else f"INV-2025-{inv_no}",
                       "fam": fam, "student": f"{first} {last}", "prog": prog, "term": term, "amount": amt,
                       "due": date(2026, 2, 10) if term == "Spring 2026" else date(2025, 9, 10)}
                pool.append(inv)
                invoices.append(inv)

    # ---- credits: scholarships in dollars, sibling discounts as a percentage ----
    credits = []
    for inv in r.sample(spring, 11):
        amt = round(r.choice([1200.0, 1800.0, 2400.0, 900.0]), 2)
        credits.append({"inv": inv, "kind": "Scholarship", "raw": amt, "pct": None,
                        "amount": min(amt, inv["amount"]), "note": r.choice(["Board award", "Need-based award", "Tuition assistance"])})
    sib_pool = [i for i in spring if not any(c["inv"] is i for c in credits)]
    for inv in r.sample(sib_pool, 12):
        pct = r.choice([5, 10, 10, 15])
        credits.append({"inv": inv, "kind": "Sibling discount", "raw": pct, "pct": pct,
                        "amount": round(inv["amount"] * pct / 100.0, 2), "note": "Second child"})
    credits.sort(key=lambda c: c["inv"]["no"])

    net_due_by_inv = {}
    for inv in spring:
        c = sum(x["amount"] for x in credits if x["inv"] is inv)
        net_due_by_inv[inv["no"]] = round(inv["amount"] - c, 2)

    # ---- payments ----
    payments = []

    def pay(inv, amount, when, status, fam_blank=False):
        nonlocal pay_no
        pay_no += 1
        payments.append({"id": f"PMT-{pay_no}", "inv": inv, "amount": round(amount, 2), "date": when,
                         "status": status, "method": r.choice(METHODS), "fam_blank": fam_blank,
                         "payer": inv["student"].split()[-1] + " family"})

    for inv in spring:
        due = net_due_by_inv[inv["no"]]
        plan = r.choice(["full", "full", "three", "three", "five", "none"])
        if plan == "none":
            continue
        if plan == "full":
            frac = r.choice([1.0, 1.0, 1.0, 0.6])
            pay(inv, due * frac, day_in(r, date(2026, 1, 20), date(2026, 3, 15)), "Cleared")
        else:
            n = 3 if plan == "three" else 5
            each = round(due / n, 2)
            start = date(2026, 2, 5)
            for k in range(n):
                when = start + timedelta(days=30 * k + r.randint(0, 4))
                status = "Cleared" if when <= CUTOFF else "Scheduled"
                pay(inv, each, when, status)
    # a handful of ACH payments came back
    for p in r.sample([x for x in payments if x["status"] == "Cleared"], 4):
        p["status"] = "Returned"
    # six payments arrived with no family id, only the invoice in the bank memo
    for p in r.sample([x for x in payments if x["status"] == "Cleared" and x["inv"]["prog"] == "Primary"], 3):
        p["fam_blank"] = True
    for p in r.sample([x for x in payments if x["status"] == "Cleared" and x["inv"]["prog"] != "Primary"], 3):
        p["fam_blank"] = True
    # the autumn invoices are settled through the same bank feed, inside the same window
    for inv in r.sample(autumn, 14):
        pay(inv, net_due_by_inv.get(inv["no"], inv["amount"]) * r.choice([1.0, 0.5]),
            day_in(r, date(2026, 1, 10), date(2026, 5, 20)), "Cleared")
    payments.sort(key=lambda p: (p["date"], p["id"]))

    # ---- truth ----
    def prog_sum(items, prog, val):
        return round(sum(val(x) for x in items if x["prog"] == prog), 2)

    billed = {p: prog_sum(spring, p, lambda i: i["amount"]) for p in PROGRAM_NAMES}
    cred = {p: round(sum(c["amount"] for c in credits if c["inv"]["prog"] == p), 2) for p in PROGRAM_NAMES}
    counted = [p for p in payments if p["status"] == "Cleared" and p["date"] <= CUTOFF and p["inv"]["term"] == "Spring 2026"]
    coll = {p: round(sum(x["amount"] for x in counted if x["inv"]["prog"] == p), 2) for p in PROGRAM_NAMES}
    net = {p: round(billed[p] - cred[p], 2) for p in PROGRAM_NAMES}
    out = {p: round(net[p] - coll[p], 2) for p in PROGRAM_NAMES}
    tot = {"billed": round(sum(billed.values()), 2), "credits": round(sum(cred.values()), 2),
           "net": round(sum(net.values()), 2), "collected": round(sum(coll.values()), 2),
           "outstanding": round(sum(out.values()), 2)}
    return {"spring": spring, "autumn": autumn, "credits": credits, "payments": payments, "counted": counted,
            "billed": billed, "cred": cred, "coll": coll, "net": net, "out": out, "tot": tot}


def acceptable(d: dict) -> bool:
    coll, cred, out, tot = d["coll"], d["cred"], d["out"], d["tot"]
    scheduled = round(sum(p["amount"] for p in d["payments"] if p["status"] == "Scheduled"), 2)
    returned = round(sum(p["amount"] for p in d["payments"] if p["status"] == "Returned"), 2)
    autumn_paid = round(sum(p["amount"] for p in d["payments"] if p["inv"]["term"] != "Spring 2026"), 2)
    blank = round(sum(p["amount"] for p in d["counted"] if p["fam_blank"]), 2)
    if scheduled < 0.05 * tot["collected"] or returned < 0.01 * tot["collected"] or autumn_paid < 0.05 * tot["collected"]:
        return False
    if blank < 0.02 * tot["collected"]:
        return False
    for p in ("Primary",):
        p_sched = sum(x["amount"] for x in d["payments"] if x["status"] == "Scheduled" and x["inv"]["prog"] == p)
        p_blank = sum(x["amount"] for x in d["counted"] if x["fam_blank"] and x["inv"]["prog"] == p)
        p_ret = sum(x["amount"] for x in d["payments"] if x["status"] == "Returned" and x["inv"]["prog"] == p)
        if p_sched < 0.03 * coll[p] or p_blank < 0.02 * coll[p] or p_ret < 0.005 * coll[p]:
            return False
    # the sibling percentages must matter: reading "10" as ten dollars moves the Toddler credit line
    sib_t = sum(c["amount"] for c in d["credits"] if c["pct"] and c["inv"]["prog"] == "Toddler")
    if sib_t < 0.08 * cred["Toddler"]:
        return False
    # pinned figures unique on their row
    def unique(prog, v):
        row = [d["billed"][prog], d["cred"][prog], d["net"][prog], d["coll"][prog], d["out"][prog]]
        return sum(1 for x in row if abs(x - v) <= max(abs(v) * 0.005, 0.01)) == 1
    if not (unique("Primary", coll["Primary"]) and unique("Toddler", cred["Toddler"])
            and unique("Lower Elementary", out["Lower Elementary"])):
        return False
    trow = [tot["billed"], tot["credits"], tot["net"], tot["collected"], tot["outstanding"]]
    for v in (tot["net"], tot["collected"]):
        if sum(1 for x in trow if abs(x - v) <= max(abs(v) * 0.005, 0.01)) != 1:
            return False
    if out["Lower Elementary"] < 1000:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(inv_rows, cred_rows, pay_rows) -> dict:
    n, m, p = len(inv_rows) + 1, len(cred_rows) + 1, len(pay_rows) + 1
    rows = []
    for i, prog in enumerate(PROGRAM_NAMES, start=2):
        rows.append([prog,
                     f"=SUMIF(Invoices!$D$2:$D${n},$A{i},Invoices!$E$2:$E${n})",
                     f"=SUMIF(Credits!$B$2:$B${m},$A{i},Credits!$C$2:$C${m})",
                     f"=B{i}-C{i}",
                     f"=SUMIF(Payments!$C$2:$C${p},$A{i},Payments!$D$2:$D${p})",
                     f"=D{i}-E{i}"])
    last = 1 + len(PROGRAM_NAMES)
    rows.append(["All programs"] + [f"=SUM({c}2:{c}{last})" for c in "BCDEF"])
    rows.append([])
    rows.append([f"Spring 2026 term, position at {CUTOFF.isoformat()}. Credits are scholarships and sibling "
                 "discounts; they reduce what is owed and are not money received."])
    return {
        "Invoices": {"header": ["invoice_no", "family_id", "student", "program", "billed"], "rows": inv_rows,
                     "widths": {"A": 16, "C": 22, "D": 18}},
        "Credits": {"header": ["invoice_no", "program", "credit_amount"], "rows": cred_rows, "widths": {"A": 16, "B": 18}},
        "Payments": {"header": ["payment_id", "invoice_no", "program", "amount"], "rows": pay_rows,
                     "widths": {"A": 14, "B": 16, "C": 18}},
        "Report": {"header": ["Program", "Billed", "Credits", "Net due", "Collected", "Outstanding"], "rows": rows,
                   "widths": {"A": 20, "B": 12, "C": 12, "D": 12, "E": 12, "F": 13}},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    billed, cred, coll, net, out, tot = d["billed"], d["cred"], d["coll"], d["net"], d["out"], d["tot"]

    # ---- workspace ----
    def inv_rows(pool):
        return [[i["no"], i["fam"], i["student"], i["prog"], i["term"],
                 money_str(i["amount"], sum(ord(c) for c in i["no"]) % 2 * 4 + 1),
                 date_variant(i["due"], sum(ord(c) for c in i["no"]) % 3)]
                for i in sorted(pool, key=lambda x: x["no"])]

    hdr = ["Invoice No", "Family ID", "Student", "Program", "Term", "Amount", "Due"]
    write_csv(os.path.join(ws, "invoices_spring_2026.csv"), hdr, inv_rows(d["spring"]),
              preamble=["Tuition invoices - Spring 2026 term"], bom=True)
    write_csv(os.path.join(ws, "invoices_autumn_2025.csv"), hdr, inv_rows(d["autumn"]),
              preamble=["Tuition invoices - Autumn 2025 term (closed)"])
    write_csv(os.path.join(ws, "payments_bank_feed.csv"),
              ["Payment ID", "Received", "Family ID", "Payer", "Applied to", "Amount", "Method", "Status", "Memo"],
              [[p["id"], date_variant(p["date"], sum(ord(c) for c in p["id"]) % 3),
                "" if p["fam_blank"] else p["inv"]["fam"], p["payer"],
                "" if p["fam_blank"] else p["inv"]["no"],
                money_str(p["amount"], 1), p["method"], p["status"],
                f"Ref {p['inv']['no']}" if p["fam_blank"] else ""] for p in d["payments"]],
              preamble=["Bank feed - tuition receipts", "01/05/2026 through 06/30/2026"], crlf=True)
    stable_xlsx(os.path.join(ws, "credits_and_discounts.xlsx"), {"Credits": {
        "merged_title": "Scholarships and discounts - Spring 2026",
        "preamble": [["Bursar's working sheet. Percentages are of that child's tuition."]],
        "header": ["Student", "Family ID", "Program", "Credit type", "Value", "Applies to invoice", "Notes"],
        "rows": [[c["inv"]["student"], c["inv"]["fam"], c["inv"]["prog"], c["kind"],
                  f"{c['pct']}%" if c["pct"] else money_str(c["raw"], 1), c["inv"]["no"], c["note"]]
                 for c in d["credits"]],
        "widths": {"A": 22, "C": 18, "D": 18, "F": 16, "G": 22}}}, creator="Bursar")
    write_text(os.path.join(ws, "note_from_the_bursar.txt"),
               "Where we stand on spring tuition\n"
               "\n"
               f"Please run the numbers as at {CUTOFF.strftime('%B %-d')}, the last day of the bank feed I trust.\n"
               "\n"
               "Scholarships and sibling discounts are credits. They come off what the family owes; they are not\n"
               "money in the account, so please do not count them as collected. A sibling discount is a percentage\n"
               "of that child's own tuition.\n"
               "\n"
               "Most families are on a payment plan, so their invoice arrives in three or five pieces. The bank feed\n"
               "shows the whole plan including the instalments still to come, and a few payments came back to us.\n"
               "Only money that has actually landed counts.\n"
               "\n"
               "The autumn file is there because the trustees asked about it last week. It is a closed term and is\n"
               "not part of this report - but some of those invoices were settled in this same feed.\n"
               "\n"
               "- Ingrid\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "collections_by_program.csv"),
              ["program", "billed", "credits", "net_due", "collected", "outstanding"],
              [[p, f"{billed[p]:.2f}", f"{cred[p]:.2f}", f"{net[p]:.2f}", f"{coll[p]:.2f}", f"{out[p]:.2f}"]
               for p in PROGRAM_NAMES] +
              [["ALL", f"{tot['billed']:.2f}", f"{tot['credits']:.2f}", f"{tot['net']:.2f}",
                f"{tot['collected']:.2f}", f"{tot['outstanding']:.2f}"]])
    write_json(os.path.join(ref, "notes.json"), {
        "cutoff": CUTOFF.isoformat(),
        "scheduled_after_cutoff": round(sum(p["amount"] for p in d["payments"] if p["status"] == "Scheduled"), 2),
        "returned_payments": round(sum(p["amount"] for p in d["payments"] if p["status"] == "Returned"), 2),
        "autumn_payments_in_feed": round(sum(p["amount"] for p in d["payments"] if p["inv"]["term"] != "Spring 2026"), 2),
        "payments_without_family_id": sum(1 for p in d["payments"] if p["fam_blank"]),
        "sibling_discount_credits": round(sum(c["amount"] for c in d["credits"] if c["pct"]), 2)})

    # ---- reference solution ----
    ir = [[i["no"], i["fam"], i["student"], i["prog"], i["amount"]] for i in sorted(d["spring"], key=lambda x: x["no"])]
    cr = [[c["inv"]["no"], c["inv"]["prog"], c["amount"]] for c in d["credits"]]
    pr = [[p["id"], p["inv"]["no"], p["inv"]["prog"], p["amount"]] for p in sorted(d["counted"], key=lambda x: x["id"])]
    stable_xlsx(os.path.join(sol, "collections.xlsx"), report_sheets(ir, cr, pr), creator="reference")

    write_task_yaml(HERE, {
        "id": "tuition-collections", "track": "desk", "category": "reports",
        "title": "Spring tuition collected and outstanding by program",
        "ask": ("Where do we stand on spring tuition, program by program - what has actually come in and what is "
                "still owed? Save it as collections.xlsx with live formulas. Ingrid's note explains the credits "
                "and the payment plans.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "most families are on a three or five instalment plan and the bank feed carries the instalments that "
            "have not happened yet, marked Scheduled with dates after the cut-off; a plain sum of the amount column "
            "books money the school has not received (checks: Primary collected; total collected)",
            "four ACH payments came back and are still in the feed as Returned (checks: Primary collected; total collected)",
            "scholarships and sibling discounts are credits against what is owed, not receipts; treating them as "
            "payments overstates collections and leaves outstanding wrong "
            "(checks: Toddler credits; Lower Elementary outstanding)",
            "sibling discounts are written as a percentage ('10%') of that child's tuition while scholarships are "
            "dollar amounts, in the same Value column (check: Toddler credits)",
            "six payments arrived with no family id and no invoice in the Applied to column - only 'Ref INV-...' in "
            "the bank memo; dropping them understates collections (check: Primary collected)",
            "the closed autumn term is in the folder and fourteen of its invoices were settled inside the same bank "
            "feed window, so the receipts must be matched to spring invoices "
            "(checks: total collected; total net due)",
            "amounts are '$5,400.00' text, dates come in three formats and the exports carry preambles, a BOM and "
            "CRLF endings (check: total collected)",
        ],
        "checks": [
            {"type": "file_exists", "name": "collections.xlsx exists", "path": "collections.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "collections.xlsx", "min_count": 10},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "collections.xlsx"},
            {"type": "xlsx_value_present", "name": "Primary collected", "path": "collections.xlsx",
             "expected": coll["Primary"], "rel_tol": cent_tol(coll["Primary"], 0.005), "near_text": "primary"},
            {"type": "xlsx_value_present", "name": "Toddler credits (percentage discounts computed)", "path": "collections.xlsx",
             "expected": cred["Toddler"], "rel_tol": cent_tol(cred["Toddler"], 0.005), "near_text": "toddler"},
            {"type": "xlsx_value_present", "name": "Lower Elementary outstanding", "path": "collections.xlsx",
             "expected": out["Lower Elementary"], "rel_tol": cent_tol(out["Lower Elementary"], 0.005), "near_text": "elementary"},
            {"type": "xlsx_value_present", "name": "total net due after credits", "path": "collections.xlsx",
             "expected": tot["net"], "rel_tol": cent_tol(tot["net"], 0.005), "near_text": "net"},
            {"type": "xlsx_value_present", "name": "total collected", "path": "collections.xlsx",
             "expected": tot["collected"], "rel_tol": cent_tol(tot["collected"], 0.005), "near_text": "collected"},
        ],
    })
    print(f"seed={seed} spring={len(d['spring'])} autumn={len(d['autumn'])} credits={len(d['credits'])} "
          f"payments={len(d['payments'])} counted={len(d['counted'])}")
    print("billed:", billed, "\ncredits:", cred, "\ncollected:", coll, "\nnet:", net, "\noutstanding:", out)
    print("totals:", tot)


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: every payment row in the feed is collected, every credit Value is a dollar amount."""
    os.makedirs(out, exist_ok=True)
    ir = [[i["no"], i["fam"], i["student"], i["prog"], i["amount"]] for i in sorted(d["spring"], key=lambda x: x["no"])]
    cr = [[c["inv"]["no"], c["inv"]["prog"], float(c["raw"])] for c in d["credits"]]
    pr = [[p["id"], p["inv"]["no"], p["inv"]["prog"], p["amount"]] for p in sorted(d["payments"], key=lambda x: x["id"])]
    stable_xlsx(os.path.join(out, "collections.xlsx"), report_sheets(ir, cr, pr), creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
