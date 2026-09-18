#!/usr/bin/env python3
"""vendor-spend-categories: year-to-date spend per vendor and category for a country inn, from the AP export.

    python gen.py [--seed N] [--naive DIR]

Business: Juniper Hollow Inn, a 22-room inn in Savannah. The bookkeeping system exports every bill, vendor
credit and void for January to August with vendor names typed however the clerk typed them. The housekeeping
manager keeps a vendor-to-category list, and one vendor is on it twice.

Traps (each caught by a check, see task.yaml):
  * vendor names come in two to five spellings; grouping the raw text splits vendors  (checks: Sysco spend; total)
  * vendor credits are exported as positive amounts with Type = Credit; they come off the vendor
                                                            (checks: Coastal Linen spend; total spend)
  * Lowcountry Supply is on the category list twice (Repairs first); the email thread puts it under
    Housekeeping & Amenities                                (checks: Housekeeping total; Repairs total)
  * voided bills stay in the export                          (check: total spend)
  * totals are live formulas                                 (checks: live formulas; no error cells)
"""
from __future__ import annotations
import argparse
import math
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

VENDORS = [  # canonical, category, spellings, (bills per month lo, hi), (amount lo, hi)
    ("Sysco Savannah", "Food & Beverage", ["Sysco Savannah", "SYSCO SAVANNAH INC", "Sysco Savannah, Inc.", "Sysco  Savannah", "sysco savannah llc"], (3, 5), (380, 1650)),
    ("Southern Coffee Roasting Co", "Food & Beverage", ["Southern Coffee Roasting Co", "Southern Coffee Roasting Company", "SOUTHERN COFFEE ROASTING"], (1, 2), (140, 420)),
    ("Coastal Linen Service", "Linen & Laundry", ["Coastal Linen Service", "Coastal Linen Svc", "COASTAL LINEN SERVICE LLC"], (4, 4), (610, 980)),
    ("Lowcountry Supply Co", "Housekeeping & Amenities", ["Lowcountry Supply Co", "Low Country Supply Company", "LOWCOUNTRY SUPPLY CO."], (1, 3), (160, 740)),
    ("Hotel Amenity Group", "Housekeeping & Amenities", ["Hotel Amenity Group", "Hotel Amenity Grp"], (0, 1), (480, 1350)),
    ("Georgia Power", "Utilities", ["Georgia Power", "Georgia Power Co", "GEORGIA POWER COMPANY"], (1, 1), (1450, 2900)),
    ("City of Savannah Water", "Utilities", ["City of Savannah - Water", "CITY OF SAVANNAH WATER & SEWER", "City of Savannah Water"], (1, 1), (390, 720)),
    ("Comcast Business", "Utilities", ["Comcast Business", "COMCAST BUSINESS COMMUNICATIONS"], (1, 1), (289.9, 289.9)),
    ("Chatham Plumbing & Heating", "Repairs & Maintenance", ["Chatham Plumbing & Heating", "Chatham Plumbing and Heating", "CHATHAM PLUMBING"], (0, 2), (180, 1900)),
    ("Tybee Pest Control", "Repairs & Maintenance", ["Tybee Pest Control", "Tybee Pest Ctrl"], (1, 1), (145, 145)),
    ("Booking.com", "Booking & Marketing", ["Booking.com", "Booking.com B.V.", "BOOKING.COM BV"], (1, 1), (1900, 4800)),
    ("Savannah Magazine", "Booking & Marketing", ["Savannah Magazine"], (0, 1), (650, 1200)),
    ("Live Oak Grounds Care", "Grounds", ["Live Oak Grounds Care", "Live Oak Grounds Care LLC"], (2, 2), (310, 460)),
    ("Forsyth Florals", "Guest Experience", ["Forsyth Florals", "FORSYTH FLORALS"], (2, 4), (85, 260)),
]
CATEGORIES = ["Food & Beverage", "Housekeeping & Amenities", "Linen & Laundry", "Utilities", "Repairs & Maintenance",
              "Booking & Marketing", "Grounds", "Guest Experience"]
AMBIG, AMBIG_WRONG = "Lowcountry Supply Co", "Repairs & Maintenance"
MANY_NAMES, CREDIT_VENDOR = "Sysco Savannah", "Coastal Linen Service"


def cent_tol(expected: float) -> float:
    e = abs(float(expected))
    return 0.01 if e <= 1.0 else min(0.01, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))


def build(seed: int) -> dict:
    r = rng(seed)
    txns = []
    for canon, cat, spellings, (lo_n, hi_n), (lo, hi) in VENDORS:
        for m in range(1, 9):
            for _ in range(r.randint(lo_n, hi_n)):
                amt = money(r, lo, hi) if lo != hi else lo
                txns.append({"type": "Bill", "vendor": canon, "raw": r.choice(spellings), "date": date(2026, m, r.randint(1, 28)),
                             "amt": amt, "status": r.choice(["Paid", "Paid", "Paid", "Open"]) if m >= 7 else "Paid",
                             "memo": ""})
    # vendor credits: several on Coastal Linen, a few elsewhere
    bills = [t for t in txns if t["type"] == "Bill"]
    for canon, n in ((CREDIT_VENDOR, 3), (MANY_NAMES, 2), (AMBIG, 1), ("Booking.com", 1)):
        vb = [t for t in bills if t["vendor"] == canon]
        for t in r.sample(vb, n):
            amt = round(t["amt"] * r.uniform(0.08, 0.35), 2)
            memo = {"Coastal Linen Service": "Credit - stained king sheets returned", "Sysco Savannah": "Credit - short shipped",
                    "Lowcountry Supply Co": "Credit - returned case", "Booking.com": "Commission refund - cancelled stay"}[canon]
            txns.append({"type": "Credit", "vendor": canon, "raw": r.choice([s for s in VENDORS if s[0] == canon][0][2]),
                         "date": date(t["date"].year, t["date"].month, min(28, t["date"].day + r.randint(1, 9))),
                         "amt": amt, "status": "Applied", "memo": memo})
    # voided bills (entered twice or by mistake)
    for t in r.sample(bills, 4):
        txns.append({**t, "status": "Voided", "memo": "VOID - entered in error", "date": t["date"]})
    txns.sort(key=lambda t: (t["date"], t["vendor"], t["type"]))
    for i, t in enumerate(txns):
        t["no"] = f"{'VC' if t['type'] == 'Credit' else 'B'}-{2600 + i}"
        t["signed"] = 0.0 if t["status"] == "Voided" else (-t["amt"] if t["type"] == "Credit" else t["amt"])
    cat_of = {v[0]: v[1] for v in VENDORS}
    spend = {v[0]: round(sum(t["signed"] for t in txns if t["vendor"] == v[0]), 2) for v in VENDORS}
    cat_tot = {c: round(sum(spend[v] for v in spend if cat_of[v] == c), 2) for c in CATEGORIES}
    grand = round(sum(spend.values()), 2)
    return {"txns": txns, "spend": spend, "cat_tot": cat_tot, "grand": grand, "cat_of": cat_of}


def acceptable(d: dict) -> bool:
    sp, ct, tx = d["spend"], d["cat_tot"], d["txns"]
    # credit and void effects are material to the cent-tight pins
    cred = sum(t["amt"] for t in tx if t["type"] == "Credit" and t["vendor"] == CREDIT_VENDOR)
    if cred < 100:
        return False
    # the most-varied vendor uses at least four spellings in the export
    if len({t["raw"] for t in tx if t["vendor"] == MANY_NAMES}) < 4:
        return False
    # category totals are not equal to any one vendor in them, and categories differ from each other
    for c in ("Housekeeping & Amenities", "Repairs & Maintenance"):
        if any(abs(ct[c] - sp[v]) < 1 for v in sp if d["cat_of"][v] == c):
            return False
    # pinned figures stand apart from every other vendor and category figure (a one-vendor category equals its vendor)
    vals = [ct[c] for c in CATEGORIES if sum(1 for v in sp if d["cat_of"][v] == c) > 1] + list(sp.values()) + [d["grand"]]
    for x in (sp[MANY_NAMES], sp[CREDIT_VENDOR], ct["Housekeeping & Amenities"], ct["Repairs & Maintenance"], d["grand"]):
        if sum(1 for y in vals if abs(x - y) < 1) > 1:
            return False
    if ct["Repairs & Maintenance"] <= 0 or sp[AMBIG] < 500:
        return False
    return True


def workbook(data_rows: list[list], cat_of: dict) -> dict:
    n = len(data_rows) + 1
    D = lambda c: f"Data!${c}$2:${c}${n}"
    rows = []
    vendors = sorted(cat_of, key=lambda v: (CATEGORIES.index(cat_of[v]), v))
    for i, v in enumerate(vendors, start=2):
        rows.append([v, cat_of[v], f"=ROUND(SUMIFS({D('F')},{D('D')},A{i}),2)"])
    last = 1 + len(vendors)
    rows.append([])
    rows.append(["Category", "", "Spend"])
    start = last + 3
    for j, c in enumerate(CATEGORIES):
        rr = start + j
        rows.append([c, "", f"=ROUND(SUMIFS($C$2:$C${last},$B$2:$B${last},A{rr}),2)"])
    rows.append(["Total spend, January to August 2026", "", f"=ROUND(SUM(C{start}:C{start + len(CATEGORIES) - 1}),2)"])
    rows.append(["Check: vendors add up to", "", f"=ROUND(SUM(C2:C{last}),2)"])
    return {
        "Spend by vendor": {"header": ["Vendor", "Category", "Spend"], "rows": rows,
                            "number_formats": {"C": "#,##0.00"}, "widths": {"A": 36, "B": 26, "C": 14}},
        "Data": {"header": ["no", "date", "type", "vendor", "vendor as exported", "net amount", "status"], "rows": data_rows,
                 "widths": {"D": 28, "E": 34}},
    }


def clean_rows(d: dict) -> list[list]:
    return [[t["no"], t["date"].isoformat(), t["type"], t["vendor"], t["raw"], t["signed"], t["status"]] for t in d["txns"]]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    sp, ct = d["spend"], d["cat_tot"]

    # ---- workspace ----
    rows = [[t["type"], t["no"], t["date"].strftime("%m/%d/%Y"), t["raw"], t["memo"], money_str(t["amt"], 0), t["status"]] for t in d["txns"]]
    write_csv(os.path.join(ws, "ap_transactions_2026-01-01_to_2026-08-31.csv"),
              ["Type", "Num", "Date", "Vendor", "Memo", "Amount", "Status"], rows,
              preamble=["Juniper Hollow Inn", "Vendor Transactions: January 1 - August 31, 2026"], bom=True, crlf=True)
    map_rows = []
    for canon, cat, *_ in VENDORS:
        if canon == AMBIG:
            map_rows.append([canon, AMBIG_WRONG, "ice machine"])
        map_rows.append([canon, cat, ""])
    write_xlsx(os.path.join(ws, "vendor_categories.xlsx"), {"Vendors": {
        "merged_title": "Vendor categories (Deb)", "header": ["Vendor", "Category", "Notes"], "rows": map_rows,
        "widths": {"A": 32, "B": 26, "C": 20}}}, creator="Deb Okafor")
    write_email_thread(os.path.join(ws, "email_thread_vendor_spend.txt"), [
        {"from": "Margaret Hughes <margaret@juniperhollowinn.com>", "to": "you; Deb Okafor <deb@juniperhollowinn.com>",
         "date": "Tue, 8 Sep 2026 10:05", "subject": "What we spend, and with whom",
         "body": "The owners want to see this year's spend so far - January through August - by vendor, grouped into "
                 "Deb's categories, with a total for each category and one for everything. Please use the vendor names "
                 "on Deb's list, whatever the bills say. A workbook with the totals as formulas, so we can reuse it at "
                 "year end."},
        {"from": "Deb Okafor <deb@juniperhollowinn.com>", "to": "you; Margaret Hughes <margaret@juniperhollowinn.com>",
         "date": "Tue, 8 Sep 2026 11:32", "subject": "RE: What we spend, and with whom",
         "body": "My list is in the folder. Lowcountry Supply is on there twice, sorry - we bought the ice machine from "
                 "them back in 2024 and I put it under repairs. Everything we buy from them now is cleaning chemicals, "
                 "trash liners and room supplies, so they belong under Housekeeping & Amenities."},
        {"from": "Margaret Hughes <margaret@juniperhollowinn.com>", "to": "you", "date": "Tue, 8 Sep 2026 12:10",
         "subject": "RE: What we spend, and with whom",
         "body": "Two more things. Vendor credits come off that vendor's spend - Coastal Linen credited us for the "
                 "stained sheets and Booking.com refunded commission on a cancelled stay. Bills count whether or not we've "
                 "paid them yet. And anything marked Voided never happened.\n\nSave it as vendor_spend.xlsx please."}])

    # ---- reference ----
    write_csv(os.path.join(ref, "vendor_spend.csv"), ["vendor", "category", "spend"],
              [[v, d["cat_of"][v], f"{sp[v]:.2f}"] for v in sp])
    write_csv(os.path.join(ref, "category_totals.csv"), ["category", "spend"],
              [[c, f"{ct[c]:.2f}"] for c in CATEGORIES] + [["ALL", f"{d['grand']:.2f}"]])
    write_json(os.path.join(ref, "notes.json"), {"ambiguous_vendor": AMBIG, "resolved_category": d["cat_of"][AMBIG],
                                                  "credits": sum(1 for t in d["txns"] if t["type"] == "Credit"),
                                                  "voided": sum(1 for t in d["txns"] if t["status"] == "Voided")})
    write_xlsx(os.path.join(sol, "vendor_spend.xlsx"), workbook(clean_rows(d), d["cat_of"]), creator="reference")

    hk, rm = "Housekeeping & Amenities", "Repairs & Maintenance"
    write_task_yaml(HERE, {
        "id": "vendor-spend-categories", "track": "desk", "category": "spreadsheet",
        "title": "Year-to-date spend by vendor and category",
        "ask": ("The owners want to see what we've spent this year with each vendor, grouped into Deb's categories. "
                "Build vendor_spend.xlsx from the AP export and keep the totals live - the email thread has the details.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"vendor names are typed two to five ways ('{MANY_NAMES}', 'SYSCO SAVANNAH INC', 'Sysco  Savannah', "
            "'sysco savannah llc'); a pivot on the raw Vendor column splits every vendor and matches few of them to "
            "Deb's list (checks: Sysco Savannah spend; total spend)",
            f"vendor credits are exported with positive amounts and Type = Credit; summing the column adds them to "
            f"spend instead of taking them off, most visibly for {CREDIT_VENDOR} (checks: Coastal Linen spend; "
            "total spend)",
            f"{AMBIG} is on Deb's list twice, under {AMBIG_WRONG} first; a lookup takes the first row, and Deb's email "
            f"puts the vendor under {hk} (checks: Housekeeping & Amenities total; Repairs & Maintenance total)",
            "four bills are voided but stay in the export with their original amounts (check: total spend)",
            "amounts are text with thousands separators under a two-line preamble with a BOM and CRLF endings, and "
            "the category totals must be live formulas that recalculate clean (checks: live formulas; no error cells)",
        ],
        "checks": [
            {"type": "file_exists", "name": "vendor_spend.xlsx exists", "path": "vendor_spend.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "vendor_spend.xlsx", "min_count": 8},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "vendor_spend.xlsx"},
            {"type": "xlsx_value_present", "name": "Sysco Savannah spend", "path": "vendor_spend.xlsx",
             "expected": sp[MANY_NAMES], "rel_tol": cent_tol(sp[MANY_NAMES]), "near_text": "sysco"},
            {"type": "xlsx_value_present", "name": "Coastal Linen spend", "path": "vendor_spend.xlsx",
             "expected": sp[CREDIT_VENDOR], "rel_tol": cent_tol(sp[CREDIT_VENDOR]), "near_text": "coastal linen"},
            {"type": "xlsx_value_present", "name": "Housekeeping & Amenities total", "path": "vendor_spend.xlsx",
             "expected": ct[hk], "rel_tol": cent_tol(ct[hk]), "near_text": "housekeeping"},
            {"type": "xlsx_value_present", "name": "Repairs & Maintenance total", "path": "vendor_spend.xlsx",
             "expected": ct[rm], "rel_tol": cent_tol(ct[rm]), "near_text": "repairs"},
            {"type": "xlsx_value_present", "name": "total spend", "path": "vendor_spend.xlsx",
             "expected": d["grand"], "rel_tol": cent_tol(d["grand"]), "near_text": "total"},
        ],
    })
    print(f"seed={seed} txns={len(d['txns'])} grand={d['grand']}")
    print("spend:", sp); print("categories:", ct)


def write_naive(d: dict, out: str) -> None:
    """Raw vendor text, credits and voids added as they are exported, first category row for every vendor."""
    os.makedirs(out, exist_ok=True)
    cat_first = {v[0]: (AMBIG_WRONG if v[0] == AMBIG else v[1]) for v in VENDORS}
    spell_of = {s: v[0] for v in VENDORS for s in v[2]}
    rows = [[t["no"], t["date"].isoformat(), t["type"], t["raw"], t["raw"], t["amt"], t["status"]] for t in d["txns"]]
    cat_raw = {t["raw"]: cat_first[spell_of[t["raw"]]] for t in d["txns"]}
    write_xlsx(os.path.join(out, "vendor_spend.xlsx"), workbook(rows, cat_raw), creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
