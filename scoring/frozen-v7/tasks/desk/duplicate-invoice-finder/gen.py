#!/usr/bin/env python3
"""duplicate-invoice-finder: an AP bills register (Q3) to a list of probable duplicate bills.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * the same vendor is typed five ways (ALL CAPS, Inc./LLC, "&" vs "and", stray spaces); three
    duplicate pairs only surface once vendors are matched on the real company name (check: flagged bills)
  * invoice numbers carry clerk prefixes (INV-, #, Inv #, No.); three pairs share a number under
    different prefixes, one of them with a keying error in the amount and one 15 days apart, so
    neither "same amount within 10 days" nor "exact invoice number" alone finds them (check: flagged bills)
  * vendor credits mirror bills (same amount, one even the same invoice number) and are never
    duplicates (check: credits and recurring bills not flagged)
  * monthly recurring bills repeat the same amount 28-35 days apart and stay (check: credits and
    recurring bills not flagged)
  * two vendors share an invoice number: not a pair (check: row count)
  * amounts are text in five styles ("$1,240.00", "1240.00", "1,240.00 USD"); dates in four formats
    (checks: amount of the duplicate; days apart)
  * one pair is dated the same day: the lower Ref No. is the original (check: paired with the original)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

SUFFIX = ["", "", " Inc.", ", LLC", " Inc", " LLC", " Co."]
PREFIX = ["", "", "INV-", "INV", "#", "Inv #", "No. "]
DATE_STYLES_OK = [0, 1, 3, 6]          # never day-first
AMT_STYLES = [0, 1, 1, 2, 4, 6]        # style 3 drops cents, never used on a cents amount
Q3_START, Q3_END = date(2026, 7, 1), date(2026, 9, 10)
Q2_START, Q2_END = date(2026, 4, 1), date(2026, 6, 28)
WINDOW = 10
MEMOS = ["Job {j} materials", "Job {j} - shingles", "Job {j} flashing and drip edge", "Delivery to yard", "Equipment rental wk {w}",
         "Job {j} dumpster", "Safety supplies", "Job {j} underlayment", "Fuel - crew trucks", "Job {j} gutters", "Permit fees job {j}"]


def vendor_variant(r, name: str) -> str:
    s = name + r.choice(SUFFIX)
    k = r.random()
    if k < 0.16: s = s.upper()
    elif k < 0.23: s = s.lower()
    elif k < 0.31: s = s + "  " if r.random() < 0.5 else "  " + s
    elif k < 0.40: s = s.replace(" & ", " and ")
    elif k < 0.46: s = s.replace(" ", "  ", 1)
    return s


def typed_inv(r, core: int, prefix: str | None = None) -> str:
    return (r.choice(PREFIX) if prefix is None else prefix) + str(core)


def build(seed: int) -> dict:
    r = rng(seed)
    comps = pick(r, COMPANIES, 17)
    vendors = [{"id": f"V{100 + i:03d}", "name": n, "domain": d, "terms": r.choice(["Net 30", "Net 30", "Net 45", "Net 15"]),
                "category": r.choice(["Materials", "Subcontract", "Equipment", "Fuel", "Disposal", "Office"])} for i, (n, d, _) in enumerate(comps)]
    active = vendors[:14]                     # three extra vendors sit in the master only
    used_amounts: set[float] = set()

    def fresh_amount(lo=85.0, hi=9800.0) -> float:
        while True:
            a = money(r, lo, hi)
            if a not in used_amounts and round(a) != a:
                used_amounts.add(a); return a

    def memo(vi: int) -> str:
        return r.choice(MEMOS).format(j=r.randint(4400, 4499), w=r.randint(27, 36))

    bills: list[dict] = []
    inv_next = {}
    for vi, v in enumerate(active):
        inv_next[vi] = r.randint(1000, 60000)
        for _ in range(r.randint(5, 9)):
            inv_next[vi] += r.randint(1, 40)
            bills.append({"vi": vi, "core": inv_next[vi], "date": day_in(r, Q3_START, Q3_END, True), "amount": fresh_amount(),
                          "type": "Bill", "memo": memo(vi), "prefix": None, "amt_style": None, "role": "base"})

    def new_core(vi: int) -> int:
        inv_next[vi] += r.randint(1, 40); return inv_next[vi]

    def clone(o: dict, **kw) -> dict:
        d = dict(o); d.update(kw); return d

    def shift(o: dict, lo: int, hi: int) -> date:
        d = o["date"] + timedelta(days=r.randint(lo, hi))
        return min(d, Q3_END)

    base = [b for b in bills]
    r.shuffle(base)
    originals = iter(base)
    pairs: list[tuple[dict, dict, str]] = []     # (original-ish, duplicate-ish, kind)
    # P1-P3: vendor spelled differently on the two rows, same number, same amount, 0-6 days apart
    for _ in range(3):
        o = next(originals)
        d = clone(o, date=shift(o, 0, 6), role="dup", force_variant=True, memo=o["memo"])
        pairs.append((o, d, "vendor variant")); bills.append(d)
    # P4-P6: same number under a different prefix. P5 has a keying error in the amount; P6 is 15 days apart.
    o = next(originals); d = clone(o, date=shift(o, 1, 6), role="dup", prefix="INV-"); o["prefix"] = ""; pairs.append((o, d, "prefix")); bills.append(d)
    o = next(originals)
    s = f"{o['amount']:.2f}".replace(".", "")
    swapped = s[:-4] + s[-3] + s[-4] + s[-2:]        # transpose two digits -> keying error
    ke = round(int(swapped) / 100, 2)
    if ke == o["amount"] or ke in used_amounts: ke = round(o["amount"] + 90.0, 2)
    used_amounts.add(ke)
    d = clone(o, date=shift(o, 1, 8), role="dup", prefix="#", amount=ke); o["prefix"] = "INV-"; pairs.append((o, d, "prefix + keying error")); bills.append(d)
    o = next(originals); d = clone(o, date=o["date"] + timedelta(days=15), role="dup", prefix="Inv #"); o["prefix"] = ""
    if d["date"] > Q3_END: o["date"] = Q3_END - timedelta(days=15); d["date"] = Q3_END
    pairs.append((o, d, "prefix, 15 days")); bills.append(d)
    # P7-P8: different invoice numbers, same amount within the window, amounts formatted differently
    for styles in ((1, 2), (4, 6)):
        o = next(originals)
        d = clone(o, core=new_core(o["vi"]), date=shift(o, 2, 8), role="dup", amt_style=styles[1]); o["amt_style"] = styles[0]
        pairs.append((o, d, "amount, different number")); bills.append(d)
    # P9: same day, same everything: the lower Ref No. is the original
    o = next(originals); d = clone(o, role="dup"); pairs.append((o, d, "same day")); bills.append(d)
    # P10: plain exact duplicate three days later
    o = next(originals); d = clone(o, date=shift(o, 3, 3), role="dup"); pairs.append((o, d, "plain")); bills.append(d)

    decoys: list[dict] = []
    # D1-D3: recurring monthly bills, same amount 28-35 days apart, different numbers (one runs three months)
    rec_vendors = r.sample(range(len(active)), 3)
    for k, vi in enumerate(rec_vendors):
        amt = fresh_amount(400, 3200)
        d0 = day_in(r, Q3_START, date(2026, 7, 12), True)
        n = 3 if k == 0 else 2
        m = r.choice(["Monthly yard lease", "Equipment lease - lift", "Uniform service", "Portable toilets - monthly", "Storage unit rent"])
        for i in range(n):
            b = {"vi": vi, "core": new_core(vi), "date": d0 + timedelta(days=sum(r.randint(28, 35) for _ in range(i))), "amount": amt,
                 "type": "Bill", "memo": m, "prefix": None, "amt_style": None, "role": "recurring"}
            bills.append(b); decoys.append(b)
    # D4: a vendor credit with the same amount as a bill from the same vendor, four days later
    o = next(originals)
    c = clone(o, core=new_core(o["vi"]), date=shift(o, 2, 5), amount=-o["amount"], type="Vendor Credit", memo=f"Credit - returned goods", role="credit", prefix="CM-")
    bills.append(c); decoys.append(c)
    # D5: a vendor credit that quotes the bill's invoice number (an RMA against that invoice)
    o = next(originals)
    c = clone(o, date=shift(o, 3, 9), amount=-round(o["amount"] * r.choice([1.0, 0.5]), 2), type="Vendor Credit", memo=f"Credit against inv {o['core']} - damaged pallet", role="credit", prefix="INV-")
    bills.append(c); decoys.append(c)
    # D6: two different vendors share an invoice number, close dates, different amounts
    o = next(originals)
    other_vi = r.choice([i for i in range(len(active)) if i != o["vi"]])
    b = {"vi": other_vi, "core": o["core"], "date": shift(o, 0, 4), "amount": fresh_amount(), "type": "Bill", "memo": memo(other_vi), "prefix": None, "amt_style": None, "role": "same number other vendor"}
    bills.append(b); decoys.append(b)
    # D7: same vendor, same amount, 12 days apart, different numbers: outside the window
    o = next(originals)
    if o["date"] + timedelta(days=12) > Q3_END: o["date"] = Q3_END - timedelta(days=12)
    b = clone(o, core=new_core(o["vi"]), date=o["date"] + timedelta(days=12), memo=memo(o["vi"]), role="outside window")
    bills.append(b); decoys.append(b)

    # entry order: by date, then chance; Ref No. follows entry order
    for b in bills: b["k"] = r.random()
    bills.sort(key=lambda b: (b["date"], b["k"]))
    for i, b in enumerate(bills):
        b["ref"] = f"BILL-{2001 + i}"
        b["vendor_typed"] = vendor_variant(r, active[b["vi"]]["name"])
        if b["prefix"] is None: b["prefix"] = r.choice(PREFIX)
        b["inv_typed"] = b["prefix"] + str(b["core"])
        if b["amt_style"] is None: b["amt_style"] = r.choice(AMT_STYLES)
        b["date_style"] = r.choice(DATE_STYLES_OK)
    for o, d, kind in pairs:
        if d.get("force_variant"):
            while d["vendor_typed"].strip().lower() == o["vendor_typed"].strip().lower():
                d["vendor_typed"] = vendor_variant(r, active[d["vi"]]["name"])
        else:
            d["vendor_typed"] = o["vendor_typed"]          # only the three "vendor variant" pairs differ in spelling

    # ground truth from the clean structures, then a sanity pass of the rule over the same structures
    truth = []
    for o, d, kind in pairs:
        a, b = sorted((o, d), key=lambda x: (x["date"], x["ref"]))
        truth.append({"ref_no": b["ref"], "duplicate_of": a["ref"], "vendor": active[b["vi"]]["name"], "invoice_no": b["inv_typed"],
                      "amount": b["amount"], "days_apart": (b["date"] - a["date"]).days, "kind": kind})
    found = set()
    real = [b for b in bills if b["type"] == "Bill"]
    for i in range(len(real)):
        for j in range(i + 1, len(real)):
            x, y = real[i], real[j]
            if x["vi"] != y["vi"]: continue
            if x["core"] == y["core"] or (x["amount"] == y["amount"] and abs((x["date"] - y["date"]).days) <= WINDOW):
                found.add(tuple(sorted((x["ref"], y["ref"]))))
    planned = {tuple(sorted((t["ref_no"], t["duplicate_of"]))) for t in truth}
    assert found == planned, f"rule sweep disagrees with the plan: extra={found - planned} missing={planned - found}"
    truth.sort(key=lambda t: t["ref_no"])
    # prior-quarter register (distractor): same vendors, numbers well below this quarter's
    old = []
    for vi, v in enumerate(active):
        for _ in range(r.randint(2, 4)):
            old.append({"vi": vi, "core": r.randint(100, 900), "date": day_in(r, Q2_START, Q2_END, True), "amount": fresh_amount(), "type": "Bill",
                        "memo": memo(vi), "vendor_typed": vendor_variant(r, v["name"]), "prefix": r.choice(PREFIX), "amt_style": r.choice(AMT_STYLES), "date_style": r.choice(DATE_STYLES_OK)})
    old.sort(key=lambda b: b["date"])
    for i, b in enumerate(old):
        b["ref"] = f"BILL-{1801 + i}"; b["inv_typed"] = b["prefix"] + str(b["core"])
    return {"vendors": vendors, "active": active, "bills": bills, "truth": truth, "decoys": decoys, "old": old}


def register_rows(bills: list[dict], active: list[dict]) -> list[list]:
    rows = []
    for b in bills:
        terms = int(active[b["vi"]]["terms"].split()[-1])
        amt = b["amount"]
        if b["type"] == "Vendor Credit":
            amt_s = money_str(amt, 5 if b["amt_style"] in (0, 2, 4) else 1)      # "(7,932.51)" or "($7,932.51)"
        else:
            amt_s = money_str(amt, b["amt_style"])
        rows.append([b["ref"], b["type"], b["vendor_typed"], b["inv_typed"], date_variant(b["date"], b["date_style"]),
                     date_variant(b["date"] + timedelta(days=terms), b["date_style"]), amt_s, b["memo"]])
    return rows


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    header = ["Ref No.", "Type", "Vendor", "Invoice No.", "Invoice Date", "Due Date", "Amount", "Memo"]
    rows = register_rows(d["bills"], d["active"])
    total = sum(b["amount"] for b in d["bills"])
    rows.append(["", "", "TOTAL", "", "", "", money_str(total, 1), ""])
    write_csv(os.path.join(ws, "ap_bills_register_2026-07-01_to_2026-09-10.csv"), header, rows, crlf=True)
    old_rows = register_rows(d["old"], d["active"])
    old_rows.append(["", "", "TOTAL", "", "", "", money_str(sum(b["amount"] for b in d["old"]), 1), ""])
    write_csv(os.path.join(ws, "ap_bills_register_2026-04-01_to_2026-06-30.csv"), header, old_rows, crlf=True)
    vrows = [[v["id"], v["name"], v["terms"], v["category"], "Active" if v in d["active"] else "Inactive"] for v in d["vendors"]]
    write_xlsx(os.path.join(ws, "vendor_list.xlsx"), {"Vendors": {"merged_title": "Vendor master - Pinnacle Roofing",
               "header": ["Vendor ID", "Vendor Name", "Terms", "Category", "Status"], "rows": vrows, "widths": {"B": 32}}}, creator="Accounting")
    write_text(os.path.join(ws, "note_from_marcus.txt"),
        "Before I release the September check run I want a list of bills that look like they were entered twice.\n"
        "Use the register export for this quarter (the April-June one is just there for reference, ignore it).\n\n"
        "Call a pair a probable duplicate when it is the same vendor and either\n"
        "  (a) the invoice number is the same once you ignore the INV-, #, Inv #, No. and similar prefixes the clerks type in, or\n"
        f"  (b) the amount is identical and the invoice dates are within {WINDOW} days of each other.\n"
        "Vendor credits are never duplicates and never pair with anything, even when they quote a bill's number.\n"
        "Same-amount bills more than ten days apart are our monthly recurring ones (yard lease, uniforms, toilets), leave those alone.\n"
        "Vendors get typed however the clerk feels like it that day (caps, Inc, LLC, extra spaces), so match on the real company\n"
        "name from vendor_list.xlsx, not the exact spelling.\n\n"
        "For each pair the earlier-dated bill is the original; if both carry the same date, the lower Ref No. is the original.\n"
        "List the other one as the duplicate, one row per duplicate, with these columns:\n"
        "ref_no, duplicate_of, vendor, invoice_no, amount, days_apart\n"
        "(amount as a plain number, days_apart as a whole number of days between the two invoice dates).\n\n"
        "Marcus\n")
    out_header = ["ref_no", "duplicate_of", "vendor", "invoice_no", "amount", "days_apart"]
    out_rows = [[t["ref_no"], t["duplicate_of"], t["vendor"], t["invoice_no"], f"{t['amount']:.2f}", t["days_apart"]] for t in d["truth"]]
    write_csv(os.path.join(ref, "possible_duplicates.csv"), out_header, out_rows)
    write_csv(os.path.join(sol, "possible_duplicates.csv"), out_header, out_rows)
    decoy_ids = sorted(b["ref"] for b in d["decoys"])
    write_json(os.path.join(ref, "notes.json"), {"pairs": [{k: v for k, v in t.items()} for t in d["truth"]],
               "decoys": [{"ref": b["ref"], "role": b["role"], "vendor": d["active"][b["vi"]]["name"], "amount": b["amount"]} for b in d["decoys"]],
               "register_rows": len(d["bills"])})
    write_task_yaml(HERE, {
        "id": "duplicate-invoice-finder", "track": "desk", "category": "spreadsheet",
        "title": "Find bills that were entered twice before the check run",
        "ask": "Go through this quarter's AP register and list the bills that look like they were entered twice. Marcus's note has how we decide. Save the list as possible_duplicates.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the same vendor is typed five ways (ALL CAPS, Inc./LLC, & vs and, stray spaces); three pairs only surface once vendors are matched on the real company name (check: flagged bills)",
            "invoice numbers carry clerk prefixes (INV-, #, Inv #, No.); three pairs share a number under different prefixes, one with a keying error in the amount and one 15 days apart, so neither same-amount-within-10-days nor exact-number matching alone finds them (check: flagged bills)",
            "two vendor credits mirror bills from the same vendor (same amount; one quotes the bill's invoice number) and are never duplicates (check: credits and recurring bills not flagged)",
            "three vendors have monthly recurring bills with identical amounts 28-35 days apart, one running three months; they stay (check: credits and recurring bills not flagged)",
            "two different vendors share an invoice number with close dates; not a pair, and one same-vendor same-amount pair is 12 days apart (check: row count)",
            "amounts are text in five styles ($1,240.00 / 1240.00 / 1,240.00 USD / $ 1,240.00); dates in four formats (checks: amount of the duplicate; days apart)",
            "one pair carries the same invoice date: the lower Ref No. is the original (check: paired with the original)",
            "the register ends with a TOTAL footer row and a prior-quarter register sits beside it as a distractor (check: row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "possible_duplicates.csv", "columns": ["ref_no", "duplicate_of", "amount", "days_apart"]},
            {"type": "csv_set_equal", "name": "flagged bills", "path": "possible_duplicates.csv", "column": "ref_no", "ref": "possible_duplicates.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "possible_duplicates.csv", "equals_ref": "possible_duplicates.csv"},
            {"type": "csv_values_match", "name": "paired with the original", "path": "possible_duplicates.csv", "ref": "possible_duplicates.csv", "key": "ref_no",
             "columns": ["duplicate_of"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "amount of the duplicate", "path": "possible_duplicates.csv", "ref": "possible_duplicates.csv", "key": "ref_no",
             "columns": ["amount"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "days apart", "path": "possible_duplicates.csv", "ref": "possible_duplicates.csv", "key": "ref_no",
             "columns": ["days_apart"], "numeric": True, "tolerance": 0.001, "min_accuracy": 1.0},
            {"type": "text_not_contains", "name": "credits and recurring bills not flagged", "path": "possible_duplicates.csv", "phrases": decoy_ids},
        ],
    })
    print(f"seed={seed} register_rows={len(d['bills'])} pairs={len(d['truth'])} decoys={len(d['decoys'])}")
    for t in d["truth"]: print("  ", t["ref_no"], "->", t["duplicate_of"], t["kind"], t["amount"], t["days_apart"])


if __name__ == "__main__":
    emit(argparse_seed())
