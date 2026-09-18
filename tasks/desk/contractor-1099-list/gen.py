#!/usr/bin/env python3
"""contractor-1099-list: a landscaping company's 2025 vendor transaction export and W-9 roster into the
e-file service's 1099-NEC recipient import.

    python gen.py [--seed N] [--naive DIR]

Business: Cedar & Pine Landscaping pays crews, tree and irrigation subcontractors, a lawyer and its accountant.
The bookkeeper ran the vendor transaction list wide (Dec 2024 to Jan 2026) and it lists bills as well as the
payments of those bills. The accountant's email carries the rules; the W-9s were typed into a roster.

Traps (each caught by a check, see task.yaml):
  * corporations are left out by the W-9 tax classification, including LLCs taxed as C or S  (check: who gets a 1099)
  * a law firm that is an S corporation still gets one; the accountant's own P.C. does not      (check: who gets a 1099)
  * threshold "$600 or more" from the email: one vendor lands on exactly $600.00                 (check: who gets a 1099)
  * vendor refunds reduce the total: one drops below the line, one stays with a lower figure     (checks: who gets a 1099; box 1)
  * only payments dated in 2025 count; the export runs Dec 2024 to Jan 2026                     (checks: who gets a 1099; box 1)
  * bills and the payments of those bills are both listed; only payments are money paid          (check: box 1)
  * template mapping: W-9 line 1 name, line 2 DBA, TIN digits and type, city/state/ZIP split     (checks: names; address)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["recipient_name", "dba_name", "tin_type", "recipient_tin", "address", "city", "state", "zip", "box1_nonemployee_comp"]
IND = "Individual/sole proprietor or single-member LLC"
YEAR0, YEAR1 = date(2025, 1, 1), date(2025, 12, 31)

# role, qb display name, legal (line 1), dba (line 2), classification, llc class, service
FIXED = [
    ("law_corp", "Copperfield Law", "Copperfield Law, P.C.", "", "S Corporation", "", "legal"),
    ("cpa_corp", "Mossbank Accounting", "Mossbank Accounting, P.C.", "", "S Corporation", "", "bookkeeping and tax"),
    ("c_corp", "Valley Small Engine", "Valley Small Engine Repair, Inc.", "", "C Corporation", "", "mower repair"),
    ("llc_s", "Summit Tree Care", "Summit Tree Care LLC", "", "Limited liability company", "S", "tree removal"),
    ("llc_c", "Brightline Pest", "Brightline Pest Solutions LLC", "", "Limited liability company", "C", "pest control"),
    ("llc_p", "Two Rivers Irrigation", "Two Rivers Irrigation LLC", "", "Limited liability company", "P", "irrigation"),
    ("partnership", "Garcia & Nguyen Snow", "Garcia & Nguyen Snow Removal", "", "Partnership", "", "snow removal"),
    ("smllc", None, None, "Hardscape LLC", IND, "", "stone and patio work"),
    ("exact600", None, None, "", IND, "", "gutter cleaning"),
    ("under", None, None, "", IND, "", "leaf pickup"),
    ("refund_drop", None, None, "", IND, "", "mulch spreading"),
    ("refund_keep", None, None, "Lawn Care", IND, "", "mowing crew"),
    ("dec2024", None, None, "", IND, "", "fence repair"),
    ("jan2026", None, None, "", IND, "", "holiday lighting"),
    ("plain1", None, None, "Landscape Design", IND, "", "design"),
    ("plain2", None, None, "", IND, "", "planting crew"),
    ("plain3", None, None, "Sod & Seed", IND, "", "sod install"),
    ("plain4", None, None, "", IND, "", "equipment hauling"),
    ("plain5", None, None, "", IND, "", "aeration"),
]


def tin(r: random.Random, kind: str) -> str:
    if kind == "SSN":
        d = f"{r.randint(100, 899)}{r.randint(10, 99)}{r.randint(1000, 9999)}"
        return d
    return f"{r.randint(10, 88)}{r.randint(1000000, 9999999)}"


def fmt_tin(d: str, kind: str) -> str:
    return f"{d[:3]}-{d[3:5]}-{d[5:]}" if kind == "SSN" else f"{d[:2]}-{d[2:]}"


def split_amount(r, total: float, n: int) -> list[float]:
    """n payments that add to total, whole-dollar amounts of broadly similar size, the way crews invoice."""
    cents = int(round(total * 100))
    whole = cents // 100
    weights = [r.uniform(0.6, 1.4) for _ in range(n)]
    parts = [int(whole * w / sum(weights)) for w in weights]
    parts[-1] += whole - sum(parts)
    parts = [p * 100 for p in parts]
    parts[-1] += cents - sum(parts)
    return [p / 100 for p in parts]


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = people(r, 40)
    vendors, txns = [], []
    pi = 0
    for role, qb, legal, dba, cls, llc, service in FIXED:
        v = {"role": role, "classification": cls, "llc": llc, "service": service}
        if legal is None:
            f, l = ppl[pi]; pi += 1
            v["legal"] = f"{f} {l}"
            v["dba"] = f"{l} {dba}" if dba else ""
            v["qb"] = v["dba"] if v["dba"] and r.random() < 0.7 else f"{f[0]}. {l}"
            if role == "smllc":
                v["qb"] = v["dba"]
        else:
            v["legal"], v["dba"], v["qb"] = legal, dba, qb
        v["tin_type"] = "SSN" if cls == IND and r.random() < 0.8 else "EIN"
        v["tin"] = tin(r, v["tin_type"])
        line, city, st, z = address(r)
        v.update(street=line, city=city, state=st, zip=z)
        vendors.append(v)
    # make sure at least one reportable vendor has a leading-zero ZIP
    zero = [c for c in CITIES if c[2].startswith("0")]
    tgt = next(v for v in vendors if v["role"] == "plain2")
    tgt["city"], tgt["state"], tgt["zip"] = zero[seed % len(zero)]

    def pay_rows(v, amounts, start, end, with_bills=True):
        for amt in amounts:
            d = day_in(r, start, end, weekday_only=True)
            bill_d = d - timedelta(days=r.randint(8, 30))
            if with_bills and r.random() < 0.75 and bill_d >= date(2024, 12, 1):
                txns.append({"date": bill_d, "type": "Bill", "num": f"{r.randint(1000, 9999)}", "vendor": v, "amount": amt,
                             "memo": f"{v['service']}", "paid": False})
                txns.append({"date": d, "type": r.choice(["Bill Payment (Check)", "Bill Payment (Check)", "Bill Payment (ACH)"]),
                             "num": "", "vendor": v, "amount": amt, "memo": "", "paid": True})
            else:
                txns.append({"date": d, "type": "Check", "num": "", "vendor": v, "amount": amt,
                             "memo": f"{v['service']}", "paid": True})

    for v in vendors:
        role = v["role"]
        if role == "exact600":
            pay_rows(v, [250.00, 350.00], YEAR0, YEAR1)
        elif role == "under":
            pay_rows(v, split_amount(r, 587.50, 2), YEAR0, YEAR1)
        elif role == "refund_drop":
            pay_rows(v, [640.00], date(2025, 4, 1), date(2025, 6, 30))
            txns.append({"date": date(2025, 7, 14), "type": "Deposit", "num": "", "vendor": v, "amount": -75.00,
                         "memo": "Refund - overbilled, one visit rained out", "paid": True})
        elif role == "refund_keep":
            total = float(r.randint(24, 60) * 100)
            pay_rows(v, split_amount(r, total, 6), YEAR0, YEAR1)
            txns.append({"date": date(2025, 9, 22), "type": "Deposit", "num": "", "vendor": v, "amount": -float(r.randint(12, 30) * 10),
                         "memo": "Refund - crew missed two scheduled mows", "paid": True})
        elif role == "dec2024":
            pay_rows(v, split_amount(r, float(r.randint(8, 14) * 100), 2), date(2024, 12, 2), date(2024, 12, 31))
            pay_rows(v, split_amount(r, float(r.randint(12, 30) * 50), 3), YEAR0, YEAR1)
        elif role == "jan2026":
            pay_rows(v, [float(r.randint(38, 55) * 10)], date(2025, 11, 1), date(2025, 12, 19))
            pay_rows(v, [float(r.randint(20, 40) * 10)], date(2026, 1, 5), date(2026, 1, 23))
        elif role in ("law_corp", "cpa_corp", "c_corp", "llc_s", "llc_c"):
            pay_rows(v, split_amount(r, float(r.randint(20, 90) * 100) + r.choice([0, 0.5, 0.75]), r.randint(3, 6)), YEAR0, YEAR1)
        else:
            n = r.randint(3, 9)
            pay_rows(v, split_amount(r, float(r.randint(15, 180) * 100) + r.choice([0, 0.25, 0.5]), n), YEAR0, YEAR1)
            if r.random() < 0.5:
                pay_rows(v, [float(r.randint(2, 12) * 50)], date(2024, 12, 2), date(2024, 12, 31))
    # a couple of noise rows: a December 2024 bill paid in January 2025 belongs to 2025
    v = next(x for x in vendors if x["role"] == "plain1")
    amt = float(r.randint(6, 18) * 100)
    txns.append({"date": date(2024, 12, 18), "type": "Bill", "num": f"{r.randint(1000, 9999)}", "vendor": v, "amount": amt,
                 "memo": v["service"], "paid": False})
    txns.append({"date": date(2025, 1, 8), "type": "Bill Payment (Check)", "num": "", "vendor": v, "amount": amt, "memo": "", "paid": True})

    txns.sort(key=lambda t: (t["date"], t["vendor"]["qb"], t["type"]))
    chk = 4100
    for t in txns:
        if t["type"] in ("Check", "Bill Payment (Check)"):
            chk += 1
            t["num"] = str(chk)

    for v in vendors:
        paid = sum(t["amount"] for t in txns if t["vendor"] is v and t["paid"] and YEAR0 <= t["date"] <= YEAR1)
        v["box1"] = round(paid, 2)
        corp = v["classification"] in ("C Corporation", "S Corporation") or v["llc"] in ("C", "S")
        v["reportable"] = (not corp or v["role"] == "law_corp") and v["box1"] >= 600.00 - 1e-9
    return {"vendors": vendors, "txns": txns}


def recipients(d):
    return sorted([v for v in d["vendors"] if v["reportable"]], key=lambda v: v["legal"])


def out_rows(d):
    return [[v["legal"], v["dba"], v["tin_type"], v["tin"], v["street"], v["city"], v["state"], v["zip"], f"{v['box1']:.2f}"]
            for v in recipients(d)]


def acceptable(d) -> bool:
    by = {v["role"]: v for v in d["vendors"]}
    need_in = ["law_corp", "llc_p", "partnership", "smllc", "exact600", "refund_keep", "dec2024"]
    need_out = ["cpa_corp", "c_corp", "llc_s", "llc_c", "under", "refund_drop", "jan2026"]
    if not all(by[k]["reportable"] for k in need_in) or any(by[k]["reportable"] for k in need_out):
        return False
    if abs(by["exact600"]["box1"] - 600.0) > 1e-9:
        return False
    # the Dec-2024-inclusive total, the Jan-2026-inclusive total and the bill-double total must all differ
    for role in ("dec2024", "refund_keep", "plain1"):
        v = by[role]
        wide = sum(t["amount"] for t in d["txns"] if t["vendor"] is v and t["paid"])
        allrows = sum(t["amount"] for t in d["txns"] if t["vendor"] is v and YEAR0 <= t["date"] <= YEAR1)
        if abs(wide - v["box1"]) < 1 and abs(allrows - v["box1"]) < 1:
            return False
    jan = by["jan2026"]
    if sum(t["amount"] for t in d["txns"] if t["vendor"] is jan and t["paid"]) < 600:
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 5)

    # ---- workspace ----
    write_csv(os.path.join(ws, "vendor_transactions_2024-12_to_2026-01.csv"),
              ["Date", "Transaction Type", "Num", "Vendor", "Memo/Description", "Amount"],
              [[date_variant(t["date"], 1), t["type"], t["num"], t["vendor"]["qb"], t["memo"], money_str(t["amount"], 0)]
               for t in d["txns"]],
              preamble=["Cedar & Pine Landscaping", "Transaction List by Vendor", "December 1, 2024 - January 31, 2026", ""],
              bom=True, crlf=True)
    roster = []
    for v in sorted(d["vendors"], key=lambda v: v["qb"].lower()):
        roster.append([v["qb"], v["legal"], v["dba"], v["classification"], v["llc"], fmt_tin(v["tin"], v["tin_type"]),
                       v["street"], f"{v['city']}, {v['state']} {v['zip']}",
                       date_variant(day_in(r, date(2023, 2, 1), date(2025, 3, 31)), 0)])
    write_xlsx(os.path.join(ws, "w9_roster.xlsx"), {"W-9s on file": {
        "merged_title": "Vendor W-9s on file (typed from the forms)",
        "header": ["QuickBooks vendor", "Name (W-9 line 1)", "Business name (line 2)", "Federal tax classification",
                   "LLC tax classification", "TIN", "Address (line 5)", "City, state, ZIP (line 6)", "W-9 signed"],
        "rows": roster, "widths": {"A": 24, "B": 32, "C": 26, "D": 44, "E": 12, "F": 14, "G": 26, "H": 24, "I": 12}}},
        creator="Cedar & Pine")
    write_csv(os.path.join(ws, "filewell_1099nec_template.csv"), TEMPLATE,
              [["Jane Q Example", "Example Hauling", "SSN", "123456789", "100 Main St", "Anytown", "OR", "97201", "1250.00"]])
    write_text(os.path.join(ws, "filewell_import_notes.txt"), (
        "Filewell - 1099-NEC recipient import\n"
        "\n"
        "Upload one CSV built on filewell_1099nec_template.csv: the same nine columns in the same order.\n"
        "One row per recipient who will receive a 1099-NEC. Do not include anyone who is not getting a form.\n"
        "\n"
        "recipient_name         the name exactly as on line 1 of the recipient's W-9.\n"
        "dba_name               line 2 of the W-9 (business name / disregarded entity name), blank if none.\n"
        "tin_type               SSN or EIN, as the TIN on the W-9 is formatted (000-00-0000 is an SSN, 00-0000000 an EIN).\n"
        "recipient_tin          nine digits, no dashes or spaces.\n"
        "address                street address (W-9 line 5).\n"
        "city, state, zip       from W-9 line 6, in three columns; state as the two-letter code; zip as five digits, keep\n"
        "                       any leading zero.\n"
        "box1_nonemployee_comp  total nonemployee compensation for the tax year, a plain number with two decimals.\n"))
    law = next(v for v in d["vendors"] if v["role"] == "law_corp")
    write_email_thread(os.path.join(ws, "email_from_accountant.txt"), [
        {"from": "Nadia Haddad <nadia@mossbank.cpa>", "to": "Rosa Ramirez <rosa@cedarpine.co>", "date": "Mon, 12 Jan 2026 10:05",
         "subject": "1099-NECs for 2025",
         "body": ("Hi Rosa, time for the 1099s. Send me the Filewell import file and I will review and file.\n\n"
                  "Who gets one: anyone you paid $600 or more for services during 2025. (The $2,000 threshold you may "
                  "have read about applies to payments made from 2026 on, not to these.) Go by the date you paid, not "
                  "the date of the bill, so something you paid in January 2026 for December work is next year's, and a "
                  "December 2024 bill you paid in January 2025 counts for 2025.\n\n"
                  "Corporations generally don't get one. Use the tax classification they ticked on the W-9 - and an "
                  "LLC counts as a corporation only if they wrote C or S as its tax classification; a partnership LLC "
                  "or a single-member LLC does get one. The exception is lawyers: legal fees get a 1099-NEC even when "
                  f"the firm is incorporated, so {law['legal']} is in. We're a P.C. too but we are not lawyers, so leave "
                  "Mossbank off.\n\n"
                  "If a vendor refunded you money during the year, that comes off what you paid them. And your export "
                  "lists the bills as well as the payments of those bills - only count the payments.")}])

    # ---- reference and solution ----
    rows = out_rows(d)
    write_csv(os.path.join(ref, "1099_vendors.csv"), TEMPLATE, rows)
    write_csv(os.path.join(sol, "1099_vendors.csv"), TEMPLATE, rows)
    by = {v["role"]: v for v in d["vendors"]}
    write_json(os.path.join(ref, "notes.json"), {v["role"]: {"legal": v["legal"], "box1": v["box1"], "reportable": v["reportable"]}
                                                  for v in d["vendors"]})
    pins = sorted(by[k]["tin"] for k in ("refund_keep", "dec2024", "plain1", "exact600", "law_corp", "llc_p", "smllc"))
    write_task_yaml(HERE, {
        "id": "contractor-1099-list", "track": "desk", "category": "reformatting",
        "title": "2025 1099-NEC recipients into the e-file service's import file",
        "ask": ("Nadia needs our 2025 1099 list in the Filewell import format - their template and notes are in the folder, "
                "and her email says who gets one. Save it as 1099_vendors.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "corporations are left out by the tax classification on the W-9 roster, and an LLC is a corporation only when its "
            "LLC tax classification is C or S; the partnership LLC and the single-member LLC stay (check: who gets a 1099)",
            f"{law['legal']} is an S corporation but legal fees are always reported, while the accountant's own P.C. "
            "is left off (check: who gets a 1099)",
            "the threshold comes from the email as $600 or more (not the $2,000 that applies from 2026): one vendor totals "
            "exactly $600.00 and is in, another $587.50 and is out (check: who gets a 1099)",
            "vendor refunds are Deposit rows with negative amounts: one vendor's $640.00 less a $75.00 refund falls to $565.00 "
            "and drops out, another stays with a lower box 1 (checks: who gets a 1099; box 1 amounts)",
            "the export runs December 2024 to January 2026; a December 2024 payment is not 2025 and a January 2026 payment "
            "pushes one vendor over $600 if counted, while a December 2024 bill paid in January 2025 does count "
            "(checks: who gets a 1099; box 1 amounts)",
            "the transaction list carries each Bill as well as its Bill Payment for the same amount; summing the vendor's "
            "rows roughly doubles box 1 (check: box 1 amounts)",
            "the template wants the W-9 line 1 name rather than the QuickBooks vendor name, line 2 as dba_name, the TIN as "
            "nine digits with SSN or EIN by its W-9 format, and line 6 split into city, state and a ZIP that keeps its "
            "leading zero (checks: template columns; W-9 names and TIN type; mailing address)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns", "path": "1099_vendors.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "who gets a 1099", "path": "1099_vendors.csv", "column": "recipient_tin",
             "ref": "1099_vendors.csv", "normalize": ["digits"]},
            {"type": "csv_row_count", "name": "row count", "path": "1099_vendors.csv", "equals_ref": "1099_vendors.csv"},
            {"type": "csv_values_match", "name": "box 1 amounts", "path": "1099_vendors.csv", "ref": "1099_vendors.csv",
             "key": "recipient_tin", "columns": ["box1_nonemployee_comp"], "numeric": True, "tolerance": 0.005,
             "min_accuracy": 1.0, "must_match_keys": pins},
            {"type": "csv_values_match", "name": "W-9 names and TIN type", "path": "1099_vendors.csv", "ref": "1099_vendors.csv",
             "key": "recipient_tin", "columns": ["recipient_name", "dba_name", "tin_type"], "min_accuracy": 1.0,
             "must_match_keys": sorted(by[k]["tin"] for k in ("smllc", "refund_keep", "plain1", "plain3"))},
            {"type": "csv_values_match", "name": "mailing address", "path": "1099_vendors.csv", "ref": "1099_vendors.csv",
             "key": "recipient_tin", "columns": ["address", "city", "state", "zip"], "min_accuracy": 1.0,
             "must_match_keys": [by["plain2"]["tin"]]},
        ],
    })
    print(f"seed={seed}: {len(rows)} recipients of {len(d['vendors'])} vendors; {len(d['txns'])} export rows")
    for v in d["vendors"]:
        print(f"  {v['role']:12} {v['legal']:36} {v['box1']:>10.2f} {'IN' if v['reportable'] else 'out'}")


def write_naive(d: dict, out: str) -> None:
    """Sum every row per vendor over the whole export, keep totals over $600, exclude nothing, QuickBooks names."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for v in d["vendors"]:
        tot = round(sum(t["amount"] for t in d["txns"] if t["vendor"] is v), 2)
        if tot > 600:
            rows.append([v["qb"], "", v["tin_type"], v["tin"], v["street"], v["city"], v["state"], v["zip"], f"{tot:.2f}"])
    write_csv(os.path.join(out, "1099_vendors.csv"), TEMPLATE, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(300):
        s = a.seed * 1000 + attempt
        if acceptable(build(s)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(s, a.naive)
