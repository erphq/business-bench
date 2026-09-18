#!/usr/bin/env python3
"""vendor-contact-merge: two vendor lists (purchasing keeps an xlsx, accounting exported a csv) into one.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * the same vendor appears in both files spelled differently: "Acme Industrial", "ACME Industrial Inc.",
    "Acme Industrial, LLC"; the email domain decides identity          (check: one row per vendor)
  * phones in seven formats; a vendor with two rows has one blank phone (check: phone carried over)
  * accounting's csv has a two-line report preamble and a BOM         (check: one row per vendor)
  * Priya's email says one vendor was dropped last month and must be left out, and that the
    purchasing sheet's payment terms win where the two disagree        (checks: dropped vendor absent; terms)
  * four vendors exist in only one file and must still appear          (check: one row per vendor)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

SUFFIX = ["", " Inc.", ", LLC", " Inc", " LLC", " Co."]
TERMS = ["Net 30", "Net 45", "Net 15", "Due on receipt", "Net 60"]

def build(seed: int) -> dict:
    r = rng(seed)
    comps = pick(r, COMPANIES, 26)
    vendors = []
    for name, domain, _ in comps:
        f, l = person(r)
        vendors.append({"name": name, "domain": domain, "contact": f"{f} {l}", "email": email_for(r, f, l, domain),
                        "phone": phone_digits(r), "terms_purchasing": r.choice(TERMS), "terms_accounting": None,
                        "category": r.choice(["Materials", "Services", "Freight", "Software", "Facilities"])})
    # accounting terms: mostly agree, disagree on 5
    for v in vendors:
        v["terms_accounting"] = v["terms_purchasing"]
    for v in r.sample(vendors, 5):
        v["terms_accounting"] = r.choice([t for t in TERMS if t != v["terms_purchasing"]])
    dropped = vendors[-1]                       # named in Priya's email, appears in both files
    only_purch = vendors[:2]; only_acct = vendors[2:4]
    both = vendors[4:-1]
    # purchasing xlsx rows
    prows = []
    for i, v in enumerate(only_purch + both + [dropped]):
        nm = v["name"] + r.choice(SUFFIX)
        prows.append([nm, v["contact"], v["email"], phone_variant(v["phone"], r.randrange(7)), v["category"], v["terms_purchasing"]])
    r.shuffle(prows)
    # accounting csv rows (different column names and order; two vendors twice, one of them with a blank phone)
    arows = []
    for v in only_acct + both + [dropped]:
        nm = name_noise(r, v["name"] + r.choice(SUFFIX))
        arows.append([code(r, 5, "0123456789"), nm, v["terms_accounting"], phone_variant(v["phone"], r.randrange(7)), v["email"].upper() if r.random() < 0.3 else v["email"]])
    dup_targets = r.sample(both, 2)
    for v in dup_targets:
        arows.append([code(r, 5, "0123456789"), v["name"].upper(), v["terms_accounting"], "", v["email"]])
    blank_phone_vendor = dup_targets[0]
    # the other duplicate: second row carries the phone, first row is blank instead
    for row in arows:
        if row[4].lower() == dup_targets[1]["email"] and row[3]:
            row[3] = ""; break
    r.shuffle(arows)
    final = [v for v in vendors if v is not dropped]
    return {"vendors": vendors, "final": sorted(final, key=lambda v: v["name"].lower()), "prows": prows, "arows": arows,
            "dropped": dropped, "blank_phone_vendor": blank_phone_vendor, "disagree": [v for v in vendors if v["terms_purchasing"] != v["terms_accounting"] and v is not dropped]}

def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    write_xlsx(os.path.join(ws, "vendors_purchasing.xlsx"), {"Vendors": {
        "merged_title": "Approved vendor list (purchasing)", "preamble": [["Owner: Priya", "", "", "", "", "Updated 2026-08-29"]],
        "header": ["Vendor", "Contact", "Email", "Phone", "Category", "Payment Terms"], "rows": d["prows"], "widths": {"A": 30, "C": 32}}},
        creator="Purchasing")
    write_csv(os.path.join(ws, "vendors_accounting_export.csv"), ["VendorID", "Vendor Name", "Terms", "Phone", "Email"], d["arows"],
              preamble=["Vendor master export", f"Run date 09/02/2026"], bom=True, crlf=True)
    dropped = d["dropped"]; dis = d["disagree"][0]
    write_email_thread(os.path.join(ws, "email_from_priya.txt"), [
        {"from": "Priya Natarajan <priya@ironwoodfab.com>", "to": "you", "date": "Wed, 3 Sep 2026 09:14", "subject": "vendor list for the new system",
         "body": ("Can you merge my purchasing sheet with the export accounting sent into one clean list? One row per vendor, "
                  "I do not care which spelling you keep as long as it is the real company name without the Inc/LLC noise. "
                  f"We stopped using {dropped['name']} in August, leave them out entirely.\n\n"
                  "Where the two files disagree on payment terms, mine is right, accounting never updated theirs "
                  f"(for example {dis['name']} is {dis['terms_purchasing']}, not {dis['terms_accounting']}). Keep the phone and email "
                  "if either file has them. Columns: vendor, contact, email, phone, category, payment terms.")}])
    header = ["vendor", "contact", "email", "phone", "category", "payment_terms"]
    rows = [[v["name"], v["contact"], v["email"], v["phone"], v["category"], v["terms_purchasing"]] for v in d["final"]]
    write_csv(os.path.join(ref, "vendors.csv"), header, rows)
    write_csv(os.path.join(sol, "vendors.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {"dropped_vendor": dropped["name"], "blank_phone_vendor_email": d["blank_phone_vendor"]["email"],
                                                  "terms_disagreements": [v["name"] for v in d["disagree"]]})
    write_task_yaml(HERE, {
        "id": "vendor-contact-merge", "track": "desk", "category": "spreadsheet",
        "title": "Merge the purchasing and accounting vendor lists",
        "ask": "Merge our two vendor lists into one clean list for the new system, one row per vendor. Priya's email has the rules. Save it as vendors.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the same vendor is spelled differently across the files (Inc., LLC, ALL CAPS, trailing spaces); the email domain decides identity (check: one row per vendor)",
            "accounting's export has a two-line preamble and a BOM; two vendors appear twice in it, once with a blank phone (checks: one row per vendor; phone carried over)",
            "phones come in seven formats; the grader accepts 10 digits or 11 with a leading 1 (check: phone carried over)",
            f"Priya's email drops one vendor that appears in both files; it must not be in the output (check: dropped vendor absent)",
            "five vendors have different payment terms in the two files; purchasing wins per the email (check: payment terms)",
            "two vendors exist only in purchasing and two only in accounting; all four stay (check: one row per vendor)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "vendors.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per vendor", "path": "vendors.csv", "column": "email", "ref": "vendors.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "vendors.csv", "equals_ref": "vendors.csv"},
            {"type": "csv_values_match", "name": "payment terms (purchasing wins)", "path": "vendors.csv", "ref": "vendors.csv", "key": "email",
             "columns": ["payment_terms"], "min_accuracy": 1.0},
            {"type": "custom", "name": "phone carried over", "module": "check.py"},
            {"type": "text_not_contains", "name": "dropped vendor absent", "path": "vendors.csv", "phrases": [dropped["domain"]]},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
