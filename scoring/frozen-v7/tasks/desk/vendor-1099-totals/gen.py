#!/usr/bin/env python3
"""vendor-1099-totals: 2025 reportable payment totals per non-corporate vendor for an event rental company.

    python gen.py [--seed N] [--naive DIR]

Business: a tent and party rental company that pays freelance crew, DJs, photographers and repair shops from one
operating account by check, ACH, Zelle, wire, company cards, PayPal and Venmo. Vendors fill in an online W-9 form.

Traps (each caught by a check, see task.yaml):
  * card, PayPal and Venmo payments are the processors' to report; check, ACH, Zelle and wire count  (check: totals)
  * a refund comes off the method it came back through: a credit to the card does not reduce the
    reportable total, a refund check or Zelle does                                               (check: totals)
  * corporations are read from the form, including an LLC taxed as C or S                          (check: which vendors)
  * two vendors filled in the form twice; the newest submission decides                            (check: which vendors)
  * the bank lists one photographer under her legal name and her trade name; the TIN joins them    (check: totals)
  * a sole proprietor paid only by card and PayPal has nothing reportable and stays off the list    (check: which vendors)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

IND = "Individual/sole proprietor or single-member LLC"
REPORTABLE = {"check", "ach", "zelle", "wire"}

# (tag, legal name, dba, classification, llc_class, tin type, payee spellings, methods weights, second form)
VENDORS = [
    ("two_names", "Marisol Vega", "Vega Frames Photography", IND, "", "SSN", ["Vega Frames Photography", "Marisol Vega"], ["check", "zelle", "amex"], None),
    ("smllc", "Northbeat DJ Services LLC", "", IND, "", "EIN", ["Northbeat DJ Services"], ["ach", "zelle"], None),
    ("llc_p", "Tentline Crew LLC", "", "Limited liability company", "P", "EIN", ["Tentline Crew LLC"], ["ach", "check", "visa"], None),
    ("llc_s", "Harborside Linen LLC", "Harborside Linen", "Limited liability company", "S", "EIN", ["Harborside Linen"], ["ach", "check"], None),
    ("ccorp", "Ridgeway Party Supply, Inc.", "", "C corporation", "", "EIN", ["Ridgeway Party Supply"], ["ach", "amex"], None),
    ("scorp", "Bayview Generator Service Inc", "", "S corporation", "", "EIN", ["Bayview Generator Svc"], ["check", "ach"], None),
    ("became_scorp", "Luis Ortiz", "Ortiz Lighting & Rigging", IND, "", "SSN", ["Ortiz Lighting & Rigging"], ["check", "zelle"],
     ("Ortiz Lighting & Rigging Inc", "", "S corporation", "", "EIN")),
    ("fixed_form", "Oak & Ember Catering", "", "C corporation", "", "EIN", ["Oak & Ember Catering"], ["ach", "check", "visa"],
     ("Oak & Ember Catering", "", "Partnership", "", "EIN")),
    ("card_only", "Priya Raman", "Petal & Stem Florals", IND, "", "SSN", ["Petal & Stem Florals"], ["amex", "paypal"], None),
    ("refund_check", "Hollis Tent Repair", "", "Partnership", "", "EIN", ["Hollis Tent Repair"], ["check", "ach"], None),
    ("refund_card", "Kwame Mensah", "Mensah Mobile Welding", IND, "", "SSN", ["Mensah Mobile Welding"], ["check", "amex", "zelle"], None),
    ("venmo_mix", "Dana Whitfield", "", IND, "", "SSN", ["Dana Whitfield"], ["venmo", "ach", "venmo"], None),
    ("wire", "Cascade Staging Partners", "", "Partnership", "", "EIN", ["Cascade Staging Partners"], ["wire", "ach"], None),
    ("plain_1", "Tomasz Kowalczyk", "", IND, "", "SSN", ["Tomasz Kowalczyk"], ["zelle", "check"], None),
    ("plain_2", "Aisha Bello", "Bello Event Design", IND, "", "SSN", ["Bello Event Design"], ["ach", "check", "visa"], None),
    ("plain_3", "Riverbank Sound LLC", "", "Limited liability company", "P", "EIN", ["Riverbank Sound"], ["ach"], None),
    ("plain_4", "Graystone Portable Toilets Inc.", "", "C corporation", "", "EIN", ["Graystone Portable Toilets"], ["ach", "check"], None),
    ("plain_5", "Hiroshi Tanaka", "Tanaka Valet", IND, "", "SSN", ["Tanaka Valet"], ["check", "paypal", "zelle"], None),
    ("plain_6", "Summit Forklift Rental LLC", "", "Limited liability company", "C", "EIN", ["Summit Forklift Rental"], ["ach", "amex"], None),
]
NON_VENDORS = [("Pacific Gas & Power", ["ach"]), ("Harbor Trust Equipment Loan", ["ach"]), ("Tallyrun Payroll", ["ach"]),
               ("Home Depot", ["amex", "visa"]), ("Google Workspace", ["amex"])]
METHOD_TEXT = {"check": lambda r: f"Check #{r.randint(2100, 2899)}", "ach": lambda r: "ACH", "zelle": lambda r: "Zelle",
               "wire": lambda r: "Wire out", "amex": lambda r: "Amex x1008", "visa": lambda r: "Visa x4417",
               "paypal": lambda r: "PayPal", "venmo": lambda r: "Venmo Business"}


def corp(classification: str, llc: str) -> bool:
    return classification in ("C corporation", "S corporation") or (classification == "Limited liability company" and llc in ("C", "S"))


def build(seed: int) -> dict:
    r = rng(seed)
    used = set()

    def tin4():
        while True:
            x = str(r.randint(1001, 9899))
            if x not in used and "0" != x[0]:
                used.add(x)
                return x

    vendors = []
    for tag, legal, dba, cls, llc, tt, payees, methods, second in VENDORS:
        v = {"tag": tag, "legal": legal, "dba": dba, "forms": [], "payees": payees, "methods": methods, "tin4": tin4(), "tin_type": tt}
        first_sub = datetime(2024, 3, 1) + timedelta(days=r.randint(0, 600), minutes=r.randint(0, 900))
        v["forms"].append({"at": first_sub, "legal": legal, "dba": dba, "cls": cls, "llc": llc, "tin_type": tt, "tin4": v["tin4"]})
        if second:
            l2, d2, c2, llc2, tt2 = second
            t4 = v["tin4"] if tt2 == tt else tin4()
            v["forms"][0]["at"] = datetime(2024, 2, 12, 10, 4) if tag == "became_scorp" else datetime(2025, 1, 8, 9, 40)
            v["forms"].append({"at": datetime(2025, 5, 19, 15, 22) if tag == "became_scorp" else datetime(2025, 1, 9, 8, 15),
                               "legal": l2, "dba": d2, "cls": c2, "llc": llc2, "tin_type": tt2, "tin4": t4})
        vendors.append(v)

    payments = []   # {date, payee, method_key, method_text, amount, memo, vendor}
    memos = ["crew labor", "event services", "invoice", "repairs", "setup/teardown", "rental support", "deposit", "balance due"]
    for v in vendors:
        n = r.randint(6, 13)
        for k in range(n):
            m = v["methods"][k % len(v["methods"])] if k < len(v["methods"]) else r.choice(v["methods"])
            payee = v["payees"][k % len(v["payees"])]
            amt = money(r, 180, 2400)
            payments.append({"date": date(2025, 1, 3) + timedelta(days=r.randint(0, 360)), "payee": payee, "method": m,
                             "text": METHOD_TEXT[m](r), "amount": amt, "memo": r.choice(memos), "vendor": v})
        # refunds
        if v["tag"] == "refund_check":
            payments.append({"date": date(2025, 8, 14), "payee": v["payees"][0], "method": "check", "text": "Deposit - vendor refund check",
                             "amount": -money(r, 300, 700), "memo": "refund overbilled repair", "vendor": v})
        if v["tag"] == "refund_card":
            payments.append({"date": date(2025, 10, 2), "payee": v["payees"][0], "method": "amex", "text": "Amex x1008 credit",
                             "amount": -money(r, 350, 800), "memo": "refund - job cancelled", "vendor": v})
            payments.append({"date": date(2025, 11, 20), "payee": v["payees"][0], "method": "zelle", "text": "Zelle received",
                             "amount": -money(r, 90, 160), "memo": "refund - unused welding rod", "vendor": v})
        if v["tag"] == "venmo_mix":
            payments.append({"date": date(2025, 6, 30), "payee": v["payees"][0], "method": "venmo", "text": "Venmo Business refund",
                             "amount": -money(r, 60, 140), "memo": "refund - overpaid", "vendor": v})
    for name, methods in NON_VENDORS:
        for k in range(r.randint(3, 8)):
            m = r.choice(methods)
            payments.append({"date": date(2025, 1, 3) + timedelta(days=r.randint(0, 360)), "payee": name, "method": m,
                             "text": METHOD_TEXT[m](r), "amount": money(r, 90, 3200), "memo": "monthly", "vendor": None})
    payments.sort(key=lambda p: (p["date"], p["payee"], p["amount"]))

    for v in vendors:
        latest = max(v["forms"], key=lambda f: f["at"])
        v["latest"] = latest
        v["corp"] = corp(latest["cls"], latest["llc"])
        v["reportable"] = round(sum(p["amount"] for p in payments if p["vendor"] is v and p["method"] in REPORTABLE), 2)
        v["all_in"] = round(sum(p["amount"] for p in payments if p["vendor"] is v), 2)
        v["on_list"] = (not v["corp"]) and v["reportable"] > 0
    return {"vendors": vendors, "payments": payments}


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 11)

    rows = []
    for p in d["payments"]:
        amt = money_str(p["amount"], 1)
        rows.append([p["date"].strftime("%m/%d/%Y"), p["payee"], p["memo"], p["text"],
                     "Vendor refund" if p["amount"] < 0 else "Payment", amt])
    write_csv(os.path.join(ws, "operating_account_payments_2025.csv"),
              ["Date", "Payee", "Memo", "Method", "Type", "Amount"], rows,
              preamble=["Juniper Hollow Event Rentals - payments and vendor refunds", "01/01/2025 to 12/31/2025"], crlf=True)

    frows = []
    subs = [(f, v) for v in d["vendors"] for f in v["forms"]]
    subs.sort(key=lambda x: x[0]["at"])
    for i, (f, v) in enumerate(subs):
        city, st, _ = r.choice(CITIES)
        frows.append([f"W9-{3170 + i * 4}", f["at"].strftime("%Y-%m-%d %H:%M"), f["legal"], f["dba"], f["cls"], f["llc"],
                      f["tin_type"], f"***-**-{f['tin4']}" if f["tin_type"] == "SSN" else f"**-***{f['tin4']}", f"{city}, {st}"])
    write_csv(os.path.join(ws, "w9_form_responses_export.csv"),
              ["Submission ID", "Submitted", "Line 1 - Name (as shown on your income tax return)",
               "Line 2 - Business name/disregarded entity name", "Line 3a - Federal tax classification",
               "LLC tax classification (C, S, or P)", "TIN type", "TIN", "City, State"], frows, quote_all=True)

    write_email_thread(os.path.join(ws, "email_from_tamsin.txt"), [
        {"from": "Tamsin Rourke <tamsin@rourkeledger.com>", "to": "Gabe <gabe@juniperhollowrentals.com>", "date": "Mon, 12 Jan 2026 09:30",
         "subject": "1099 totals for 2025",
         "body": ("Hi Gabe,\n\nBefore I prepare the 1099s I need the 2025 totals per vendor. How I want them counted:\n\n"
                  "1. Only vendors who filled in your W-9 form count; the utility, the equipment loan and payroll are not vendors for this.\n"
                  "2. Leave out corporations - a C or S corporation, and an LLC that told us it is taxed as a C or S corporation. "
                  "Individuals, single-member LLCs, partnerships and LLCs taxed as partnerships stay in.\n"
                  "3. If someone filled in the form more than once, the most recent submission replaces the earlier one.\n"
                  "4. Anything you paid by credit card, PayPal or Venmo is reported by the card company or the app, not by us, so "
                  "leave those payments out. Checks, ACH, Zelle and wires count.\n"
                  "5. Refunds from a vendor come off the total only if the money came back the same reportable way (a refund check "
                  "you deposited, a Zelle back to you). A refund credited back to the card or to PayPal or Venmo just reverses a card or app "
                  "payment that was never in the total.\n"
                  "6. Some people show up in the bank under their business name and sometimes under their own name - it is the "
                  "same TIN, one line.\n\n"
                  "Send me vendor_totals.csv with vendor (the line 1 name from their latest form), tin_last4 (just the four digits) "
                  "and reportable_total. Skip anyone whose reportable total comes to zero. I will apply the threshold myself.\n\n"
                  "Thanks,\nTamsin")}])

    listed = sorted([v for v in d["vendors"] if v["on_list"]], key=lambda v: v["latest"]["legal"].lower())
    header = ["vendor", "tin_last4", "reportable_total"]
    out = [[v["latest"]["legal"], v["latest"]["tin4"], f"{v['reportable']:.2f}"] for v in listed]
    write_csv(os.path.join(ref, "vendor_totals.csv"), header, out)
    write_csv(os.path.join(sol, "vendor_totals.csv"), header, out)
    write_json(os.path.join(ref, "notes.json"), {v["tag"]: {"legal": v["latest"]["legal"], "tin4": v["latest"]["tin4"], "corp": v["corp"],
                                                            "reportable": v["reportable"], "all_methods": v["all_in"]} for v in d["vendors"]})
    by = {v["tag"]: v for v in d["vendors"]}
    t4 = lambda tag: by[tag]["latest"]["tin4"]
    write_task_yaml(HERE, {
        "id": "vendor-1099-totals", "track": "desk", "category": "bookkeeping",
        "title": "2025 reportable totals per vendor, cards and corporations out",
        "ask": ("Tamsin needs our 2025 vendor totals so she can prepare the 1099s. The bank payments and the W-9 form responses "
                "are in the folder and her email says how to count. Save it as vendor_totals.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "card, PayPal and Venmo payments are reported by the processor and leave the total, while Zelle and wires stay; "
            f"Dana Whitfield ({t4('venmo_mix')}) is paid by Venmo and ACH and only the ACH counts (check: reportable totals)",
            f"refunds come off only when they came back a reportable way: Hollis Tent Repair ({t4('refund_check')}) deposited a "
            f"refund check that reduces its total, Mensah Mobile Welding's ({t4('refund_card')}) card credit does not while its "
            "Zelle refund does, and a Venmo refund changes nothing (check: reportable totals)",
            "corporations come from line 3a and the LLC letter on the form: Harborside Linen and Summit Forklift Rental are LLCs "
            "taxed as S and C corporations and drop out, while Tentline Crew and Riverbank Sound are LLCs taxed as partnerships and "
            "stay (check: which vendors)",
            "two vendors submitted the form twice: Luis Ortiz first filled it in under his own name and SSN, then resubmitted in "
            "May 2025 for Ortiz Lighting & Rigging Inc, an S corporation with its own EIN, so he drops out; Oak & Ember Catering "
            "first ticked C corporation by mistake and corrected it to Partnership the next day, so it stays (checks: which vendors; row count)",
            f"Marisol Vega is paid as both 'Vega Frames Photography' and 'Marisol Vega'; the bank payee does not match the form's "
            f"line 1 name, and splitting her by payee halves her total (checks: reportable totals; line 1 names)",
            f"Petal & Stem Florals ({t4('card_only')}) is a sole proprietor paid only by Amex and PayPal, so nothing is reportable "
            "and she stays off the list (checks: which vendors; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "vendor_totals.csv", "columns": header},
            {"type": "csv_set_equal", "name": "which vendors", "path": "vendor_totals.csv", "column": "tin_last4",
             "ref": "vendor_totals.csv", "normalize": ["digits"]},
            {"type": "csv_row_count", "name": "row count", "path": "vendor_totals.csv", "equals_ref": "vendor_totals.csv"},
            {"type": "csv_values_match", "name": "reportable totals", "path": "vendor_totals.csv", "ref": "vendor_totals.csv",
             "key": "tin_last4", "columns": ["reportable_total"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0,
             "must_match_keys": [t4(x) for x in ("two_names", "venmo_mix", "refund_check", "refund_card", "wire", "llc_p", "fixed_form")]},
            {"type": "csv_values_match", "name": "line 1 names", "path": "vendor_totals.csv", "ref": "vendor_totals.csv",
             "key": "tin_last4", "columns": ["vendor"], "normalize": ["alnum"], "min_accuracy": 1.0,
             "must_match_keys": [t4(x) for x in ("two_names", "refund_card", "fixed_form")]},
        ],
    })
    print(f"seed={seed} payments={len(d['payments'])} on list={len(listed)}")
    for v in d["vendors"]:
        print(f"  {v['tag']:14} {v['latest']['legal'][:30]:30} corp={v['corp']!s:5} reportable={v['reportable']:>10.2f} all={v['all_in']:>10.2f} list={v['on_list']}")


def write_naive(d: dict, out: str) -> None:
    """Sum every row per payee (all methods, all refunds), look the payee up on the FIRST form by line 1 or line 2 name,
    drop only 'C corporation' and 'S corporation' ticks."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for v in d["vendors"]:
        f = v["forms"][0]
        if f["cls"] in ("C corporation", "S corporation"):
            continue
        for payee in v["payees"]:
            tot = round(sum(p["amount"] for p in d["payments"] if p["payee"] == payee), 2)
            rows.append([f["legal"], f["tin4"], f"{tot:.2f}"])
    write_csv(os.path.join(out, "vendor_totals.csv"), ["vendor", "tin_last4", "reportable_total"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
