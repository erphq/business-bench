#!/usr/bin/env python3
"""ap-aging: payables aging by vendor at 31 August for a cidery, with a memo naming the most overdue bill.

    python gen.py [--seed N] [--naive DIR]

Business: a cider maker buying fruit, glass, labels, CO2, barrels and freight on a mix of vendor terms. The owner
wants the aging for the bank's line-of-credit review.

Traps (each caught by a check, see task.yaml):
  * aging runs from the due date, and terms come from the vendor list unless the bill carries its own    (checks: bucket totals)
  * Net 30 EOM is due 30 days after the end of the bill's month; 2% 10 Net 30 is due in 30 days          (checks: bucket totals)
  * the export has Amount and Open Balance; partly paid bills age on what is still open                  (check: total payables)
  * a credit that names an open bill comes off that bill; one naming nothing, or a bill already paid, sits in
    Current as a negative for that vendor                                                                  (checks: vendor totals; current)
  * two Draft bills are not approved and are not payables                                                  (check: total payables)
  * the most overdue bill is not the one with the oldest bill date                                         (check: memo names the bill)
"""
from __future__ import annotations
import argparse
import calendar
import math
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

AS_OF = date(2026, 8, 31)
BUCKETS = ["Current", "1-30", "31-60", "61-90", "Over 90"]
VENDORS = [  # name, prefix, default terms, amount range
    ("Orchard Valley Fruit Co.", "OVF", "Net 30 EOM", (1800, 9800)),
    ("Cascade Glass Packaging", "CGP", "2% 10 Net 30", (1200, 6400)),
    ("Label Lab Printing", "LL", "Net 15", (380, 2600)),
    ("Summit Gas & Welding Supply", "SGW", "Net 30", (160, 900)),
    ("Northline Freight", "NLF", "Net 45", (240, 1900)),
    ("Barrel & Stave Cooperage", "BSC", "Net 60", (2400, 8800)),
    ("Pacific Corrugated Box", "PCB", "Net 30", (600, 3400)),
    ("Cedar Ridge Electric", "CRE", "Due on receipt", (280, 1600)),
    ("Hopkins Family Pears", "HFP", "Net 30", (900, 4200)),
    ("Brightline Pest Control", "BPC", "Net 15", (95, 240)),
]


def due_date(bill_date: date, terms: str) -> date:
    t = terms.lower()
    if "receipt" in t:
        return bill_date
    if "eom" in t:
        end = date(bill_date.year, bill_date.month, calendar.monthrange(bill_date.year, bill_date.month)[1])
        return end + timedelta(days=int(t.split()[1]))
    n = int(t.split("net")[-1].strip())
    return bill_date + timedelta(days=n)


def bucket(days_past: int) -> str:
    if days_past <= 0:
        return "Current"
    if days_past <= 30:
        return "1-30"
    if days_past <= 60:
        return "31-60"
    if days_past <= 90:
        return "61-90"
    return "Over 90"


def r2(x: float) -> float:
    return float(f"{x + (1e-9 if x >= 0 else -1e-9):.2f}")


def cent_tol(expected: float, rel: float = 0.01) -> float:
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))


def build(seed: int) -> dict:
    r = rng(seed)
    bills = []
    seqs = {p: r.randint(20100, 20900) for _, p, _, _ in VENDORS}

    def add(vendor, bill_date, amount, terms_override="", paid=0.0, status="Open", tag=""):
        name, prefix, terms, _ = vendor
        seqs[prefix] += r.randint(3, 40)
        bills.append({"vendor": name, "no": f"{prefix}-{seqs[prefix]}", "date": bill_date, "amount": r2(amount), "paid": r2(paid),
                      "terms_override": terms_override, "terms": terms_override or terms, "status": status, "tag": tag})
        return bills[-1]

    V = {v[0]: v for v in VENDORS}
    # fixed trap bills
    add(V["Barrel & Stave Cooperage"], date(2026, 3, 12), 7420.00, tag="oldest_date")
    add(V["Label Lab Printing"], date(2026, 4, 20), 1865.40, tag="most_overdue")
    add(V["Orchard Valley Fruit Co."], date(2026, 7, 14), 8240.00, tag="eom_current")      # EOM: due Aug 30 -> 1 day; Net 30 would be Aug 13
    add(V["Orchard Valley Fruit Co."], date(2026, 6, 1), 6135.50, tag="eom_june")          # due Jul 30 -> 32 days; Net 30 -> 61
    add(V["Cascade Glass Packaging"], date(2026, 8, 10), 4380.00, tag="discount_terms")    # due Sep 9 -> current; Net 10 -> 11 days
    add(V["Pacific Corrugated Box"], date(2026, 7, 10), 2960.00, terms_override="Net 60", tag="override")  # due Sep 8 -> current
    add(V["Hopkins Family Pears"], date(2026, 6, 22), 3890.00, paid=2000.00, tag="partial")
    add(V["Cascade Glass Packaging"], date(2026, 6, 29), 5210.00, tag="credit_target")
    add(V["Northline Freight"], date(2026, 8, 28), 1460.00, status="Draft", tag="draft")
    add(V["Barrel & Stave Cooperage"], date(2026, 8, 20), 6900.00, status="Draft", tag="draft")
    # ordinary bills
    for v in VENDORS:
        lo, hi = v[3]
        for _ in range(r.randint(2, 5)):
            bd = date(2026, 5, 20) + timedelta(days=r.randint(0, 102))
            amt = money(r, lo, hi)
            paid = r2(amt * r.choice([0.25, 0.5])) if r.random() < 0.15 else 0.0
            add(v, bd, amt, paid=paid)
    bills.sort(key=lambda b: (b["date"], b["no"]))

    credits = []
    tgt = next(b for b in bills if b["tag"] == "credit_target")
    credits.append({"no": "VC-1182", "vendor": tgt["vendor"], "date": date(2026, 7, 21), "amount": 640.00, "applies": tgt["no"],
                    "memo": "Broken case credit - 32 cases", "tag": "applied"})
    credits.append({"no": "VC-1190", "vendor": "Northline Freight", "date": date(2026, 8, 6), "amount": 385.00, "applies": "",
                    "memo": "Rebill correction - duplicate fuel surcharge", "tag": "unapplied"})
    credits.append({"no": "VC-1194", "vendor": "Summit Gas & Welding Supply", "date": date(2026, 8, 14), "amount": 212.50,
                    "applies": "SGW-19877", "memo": "Cylinder deposit refund", "tag": "paid_bill"})

    open_nos = {b["no"] for b in bills if b["status"] == "Open"}
    rows = []   # truth lines that age: bills (net of applied credits) and unapplied credits
    for b in bills:
        if b["status"] != "Open":
            continue
        cred = sum(c["amount"] for c in credits if c["applies"] == b["no"])
        b["open"] = r2(b["amount"] - b["paid"] - cred)
        b["due"] = due_date(b["date"], b["terms"])
        b["days"] = (AS_OF - b["due"]).days
        b["bucket"] = bucket(b["days"])
        rows.append({"vendor": b["vendor"], "ref": b["no"], "open": b["open"], "bucket": b["bucket"], "days": b["days"],
                     "date": b["date"], "terms": b["terms"], "due": b["due"]})
    for c in credits:
        if c["applies"] not in open_nos:
            rows.append({"vendor": c["vendor"], "ref": c["no"], "open": -c["amount"], "bucket": "Current", "days": 0, "date": c["date"],
                         "terms": "credit", "due": None})
    vendors = sorted({v[0] for v in VENDORS})
    grid = {(v, k): r2(sum(x["open"] for x in rows if x["vendor"] == v and x["bucket"] == k)) for v in vendors for k in BUCKETS}
    vtot = {v: r2(sum(grid[(v, k)] for k in BUCKETS)) for v in vendors}
    btot = {k: r2(sum(grid[(v, k)] for v in vendors)) for k in BUCKETS}
    total = r2(sum(vtot.values()))
    past_due = r2(sum(btot[k] for k in BUCKETS[1:]))
    oldest = max((b for b in bills if b["status"] == "Open"), key=lambda b: b["days"])
    return {"bills": bills, "credits": credits, "rows": rows, "grid": grid, "vtot": vtot, "btot": btot, "total": total,
            "past_due": past_due, "oldest": oldest, "vendors": vendors}


def naive_buckets(d: dict) -> dict:
    """Age from the bill date, Amount column, drafts in, credits ignored."""
    out = {k: 0.0 for k in BUCKETS}
    for b in d["bills"]:
        out[bucket((AS_OF - b["date"]).days - 0)] += b["amount"]
    return out


def acceptable(d: dict) -> bool:
    bills = {b["tag"]: b for b in d["bills"] if b["tag"]}
    if d["oldest"]["tag"] != "most_overdue":
        return False
    if bills["eom_current"]["bucket"] != "1-30" or bills["override"]["bucket"] != "Current":
        return False
    btot, vtot, total = d["btot"], d["vtot"], d["total"]
    nb = naive_buckets(d)
    for k in ("Current", "31-60", "Over 90"):
        if abs(nb[k] - btot[k]) < 5:
            return False
    # bucket-by-bill-date with correct amounts must also move the pinned buckets
    alt = {k: 0.0 for k in BUCKETS}
    for x in d["rows"]:
        alt[bucket((AS_OF - x["date"]).days) if x["terms"] != "credit" else "Current"] += x["open"]
    for k in ("Current", "31-60"):
        if abs(alt[k] - btot[k]) < 5:
            return False
    eom = bills["eom_june"]
    if bucket((AS_OF - (eom["date"] + timedelta(days=30))).days) == eom["bucket"]:
        return False
    disc = bills["discount_terms"]
    if bucket((AS_OF - (disc["date"] + timedelta(days=10))).days) == disc["bucket"]:
        return False
    vals = [btot[k] for k in BUCKETS] + list(vtot.values()) + [total, d["past_due"]]
    if len({round(v, 2) for v in vals}) != len(vals):
        return False
    if any(v <= 0 for v in btot.values()):
        return False
    return True


def report_sheets(d: dict) -> dict:
    rows = sorted(d["rows"], key=lambda x: (x["vendor"], x["date"], x["ref"]))
    n = len(rows) + 1
    lines = [[x["vendor"], x["ref"], x["date"], x["terms"], x["due"] if x["due"] else "", x["days"] if x["due"] else "", x["open"], x["bucket"]]
             for x in rows]
    summary = []
    for i, v in enumerate(d["vendors"], start=2):
        line = [v]
        for j, k in enumerate(BUCKETS):
            col = chr(ord("B") + j)
            line.append(f'=SUMIFS(Bills!$G$2:$G${n},Bills!$A$2:$A${n},$A{i},Bills!$H$2:$H${n},{col}$1)')
        line.append(f"=SUM(B{i}:F{i})")
        summary.append(line)
    last = len(d["vendors"]) + 1
    summary.append(["Total"] + [f"=SUM({c}2:{c}{last})" for c in "BCDEFG"])
    summary.append(["Total past due", f"=SUM(C{last + 1}:F{last + 1})"])
    return {
        "Aging": {"header": ["Vendor"] + BUCKETS + ["Total"], "rows": summary, "widths": {"A": 30, "B": 12, "C": 12, "D": 12, "E": 12, "F": 12, "G": 14},
                  "number_formats": {c: "#,##0.00" for c in "BCDEFG"}},
        "Bills": {"header": ["Vendor", "Bill / credit", "Date", "Terms", "Due date", "Days past due", "Open amount", "Bucket"], "rows": lines,
                  "widths": {"A": 30, "B": 12, "C": 12, "D": 14, "E": 12}, "number_formats": {"G": "#,##0.00"}},
    }


def memo_text(d: dict) -> str:
    o = d["oldest"]
    btot = d["btot"]
    return f"""# Accounts payable aging - 31 August 2026

We owe vendors {d['total']:,.2f} in total, of which {d['past_due']:,.2f} is past due. By bucket: current {btot['Current']:,.2f},
1-30 days {btot['1-30']:,.2f}, 31-60 days {btot['31-60']:,.2f}, 61-90 days {btot['61-90']:,.2f} and over 90 days {btot['Over 90']:,.2f}.

The most overdue bill is {o['no']} from {o['vendor']} for {o['open']:,.2f}, dated {o['date'].strftime('%d %B %Y')} on {o['terms']} terms and now {o['days']} days past due.

How the aging was built: every bill ages from its due date under the vendor's terms (or the bill's own terms where it has
them); Net 30 EOM runs from the end of the bill's month and 2% 10 Net 30 is due at 30 days. Balances are what is still
open after partial payments. The Cascade Glass credit came off the bill it names; the Northline Freight credit and the
Summit Gas credit for a bill already paid are shown as negatives in Current. The two draft bills are not included.
"""


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 9)
    bills, credits = d["bills"], d["credits"]

    rows = []
    for b in bills:
        style = r.randrange(3)
        rows.append([b["no"], b["vendor"], date_variant(b["date"], [1, 0, 3][style]), b["terms_override"], money_str(b["amount"], 1),
                     money_str(r2(b["amount"] - b["paid"]), 1), b["status"]])
    write_csv(os.path.join(ws, "bills_export_2026-08-31.csv"), ["Bill No", "Vendor", "Bill Date", "Terms", "Amount", "Open Balance", "Status"],
              rows, preamble=["Two Rivers Cider Works - Unpaid Bills", "As of 08/31/2026 (terms shown only where the bill overrides the vendor default)"], crlf=True)
    write_xlsx(os.path.join(ws, "vendor_list.xlsx"), {"Vendors": {
        "header": ["Vendor", "Default Terms", "Category", "Contact"],
        "rows": [[v[0], v[2], cat, f"{f} {l}"] for v, cat, (f, l) in zip(VENDORS, ["Fruit", "Packaging", "Packaging", "CO2 and gases", "Freight",
                                                                                  "Barrels", "Packaging", "Facilities", "Fruit", "Facilities"], people(r, 10))],
        "widths": {"A": 30, "B": 16, "C": 14, "D": 20}}}, creator="Two Rivers")
    write_csv(os.path.join(ws, "vendor_credits_open.csv"), ["Credit No", "Vendor", "Credit Date", "Amount", "Apply To Bill", "Memo"],
              [[c["no"], c["vendor"], c["date"].strftime("%m/%d/%Y"), f"{c['amount']:.2f}", c["applies"], c["memo"]] for c in credits])
    write_text(os.path.join(ws, "note_from_wes.txt"), """The bank wants an AP aging as of August 31 for the line of credit review.

- Age every bill from when it was due, not when it was dated. Terms are on the vendor list; a bill only has terms
  in the export when we agreed something different for that bill, and then those win.
- "Net 30 EOM" means 30 days after the end of the month the bill is dated. On the Cascade Glass terms the 2% is only
  if we pay in 10 days - the bill is due at 30.
- Buckets: current (not due yet), 1-30, 31-60, 61-90 and over 90 days past due.
- Use what we still owe on each bill - some are partly paid.
- Vendor credits that name a bill come off that bill. A credit that doesn't name a bill we still owe goes in current
  as a negative for that vendor.
- Drafts aren't approved bills. Leave them out.

Put the aging by vendor, with totals, in ap_aging.xlsx with formulas, and write memo.md for the bank with the total we
owe, how much of it is past due, and the bill that has been overdue the longest.

- Wes
""")

    write_xlsx(os.path.join(sol, "ap_aging.xlsx"), report_sheets(d), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))
    vendors, grid, vtot, btot = d["vendors"], d["grid"], d["vtot"], d["btot"]
    write_csv(os.path.join(ref, "aging_by_vendor.csv"), ["vendor"] + BUCKETS + ["total"],
              [[v] + [f"{grid[(v, k)]:.2f}" for k in BUCKETS] + [f"{vtot[v]:.2f}"] for v in vendors] +
              [["TOTAL"] + [f"{btot[k]:.2f}" for k in BUCKETS] + [f"{d['total']:.2f}"]])
    write_csv(os.path.join(ref, "aged_lines.csv"), ["vendor", "ref", "date", "terms", "due", "days_past_due", "open", "bucket"],
              [[x["vendor"], x["ref"], x["date"].isoformat(), x["terms"], x["due"].isoformat() if x["due"] else "", x["days"], f"{x['open']:.2f}", x["bucket"]]
               for x in d["rows"]])
    o = d["oldest"]
    ob = next(b for b in bills if b["tag"] == "oldest_date")
    write_json(os.path.join(ref, "notes.json"), {"total": d["total"], "past_due": d["past_due"], "most_overdue": o["no"], "oldest_bill_date": ob["no"]})

    def pin(name, value, near):
        return {"type": "xlsx_value_present", "name": name, "path": "ap_aging.xlsx", "expected": value, "rel_tol": cent_tol(value), "near_text": near}
    digits = o["no"].split("-")[1]
    write_task_yaml(HERE, {
        "id": "ap-aging", "track": "desk", "category": "bookkeeping",
        "title": "Payables aging by vendor for the line of credit review",
        "ask": ("The bank wants our accounts payable aging as of August 31. Wes's note says how to do it and the bills, vendor list "
                "and credits are in the folder. Save the aging as ap_aging.xlsx and the write-up as memo.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "bills age from the due date under each vendor's terms from the vendor list, and the export only shows terms where a bill "
            "overrides them (a Pacific Corrugated bill on Net 60 is still current); aging from the bill date pushes most of the book a "
            "bucket older (checks: current bucket total; 31-60 bucket total)",
            "Orchard Valley is Net 30 EOM, so its 1 June bill is due 30 July and 32 days late rather than 61, and its 14 July bill only a "
            "day late; Cascade Glass's 10 August bill on 2% 10 Net 30 is due 9 September and still current, not 11 days late "
            "(checks: current bucket total; 1-30 bucket total; 31-60 bucket total)",
            "the export has Amount beside Open Balance and partly paid bills age on the open part; the Hopkins Family Pears bill is "
            "half paid (checks: total payables; Hopkins Family Pears total)",
            "credit VC-1182 names an open Cascade Glass bill and comes off it; VC-1190 names no bill and VC-1194 names a Summit Gas bill "
            "that is already paid, so both sit in Current as negatives (checks: Northline Freight total; Summit Gas total; current bucket total)",
            "two Draft bills (Northline Freight and Barrel & Stave) are not approved and are not payables (checks: total payables; Northline Freight total)",
            f"the bill overdue longest is {o['no']} from {o['vendor']} ({o['days']} days past due); Barrel & Stave's {ob['no']} has the "
            "oldest bill date but Net 60 terms (check: memo names the most overdue bill)",
        ],
        "checks": [
            {"type": "file_exists", "name": "ap_aging.xlsx exists", "path": "ap_aging.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "ap_aging.xlsx", "min_count": 10},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "ap_aging.xlsx"},
            pin("total payables", d["total"], "total"),
            pin("current bucket total", btot["Current"], "total"),
            pin("1-30 bucket total", btot["1-30"], "total"),
            pin("31-60 bucket total", btot["31-60"], "total"),
            pin("Northline Freight total", vtot["Northline Freight"], "northline"),
            pin("Summit Gas total", vtot["Summit Gas & Welding Supply"], "summit gas"),
            pin("Hopkins Family Pears total", vtot["Hopkins Family Pears"], "hopkins"),
            {"type": "text_numbers_present", "name": "memo carries total and past due", "path": "memo.md",
             "numbers": [d["total"], d["past_due"]], "rel_tol": 0.00001},
            {"type": "text_sentence_matches", "name": "memo names the most overdue bill", "path": "memo.md",
             "all": [rf"\b{o['no'].split('-')[0]}\s*-?\s*{digits}\b",
                     r"(oldest|longest|most (overdue|past due|late)|furthest|overdue the longest|largest number of days|most days)"],
},
        ],
    })
    print(f"seed={seed} bills={len(bills)} total={d['total']} past_due={d['past_due']} buckets={btot} oldest={o['no']} {o['days']}d")
    print("vendors:", vtot)


def write_naive(d: dict, out: str) -> None:
    """Age from bill date on the Amount column, drafts and all, credits ignored, memo names the oldest bill date."""
    os.makedirs(out, exist_ok=True)
    rows = {}
    for b in d["bills"]:
        k = bucket((AS_OF - b["date"]).days)
        rows.setdefault(b["vendor"], {x: 0.0 for x in BUCKETS})[k] += b["amount"]
    lines = [[v] + [round(rows[v][k], 2) for k in BUCKETS] + [round(sum(rows[v].values()), 2)] for v in sorted(rows)]
    tot = [round(sum(l[i] for l in lines), 2) for i in range(1, 7)]
    write_xlsx(os.path.join(out, "ap_aging.xlsx"), {"Aging": {"header": ["Vendor"] + BUCKETS + ["Total"], "rows": lines + [["Total"] + tot]}}, creator="naive")
    ob = min(d["bills"], key=lambda b: b["date"])
    write_text(os.path.join(out, "memo.md"), f"# AP aging\n\nWe owe {tot[-1]:,.2f}. The oldest bill is {ob['no']} from {ob['vendor']}.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(600):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
