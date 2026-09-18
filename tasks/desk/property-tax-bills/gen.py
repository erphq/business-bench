#!/usr/bin/env python3
"""property-tax-bills: this year's property tax bills from two counties, plus a delinquent notice -> one row per parcel.

    python gen.py [--seed N] [--naive DIR]

Business: Pine Hollow RV Resort owns five parcels across Juniper County and Keel County. The bookkeeper logs each year's bills
(assessed value, exemptions, total and both installments with due dates) so the payments get scheduled.

Traps (each caught by a check, see task.yaml):
  * two installments: Juniper prints both halves with a due date and a later "delinquent after" date; Keel prints only the
    total and the rule (equal halves, odd cent on the first); the scan prints its stubs second installment first
                                                                                      (checks: installments; due dates)
  * exemptions: a homeowner exemption on the manager's residence, a farm-use exemption on the Keel pasture, and Keel prints
    market value above the assessed value (40% of market)                           (check: assessed values and exemptions)
  * Juniper prints "Total ad valorem tax" and then special assessments before "Total taxes and assessments" (check: total tax)
  * a Keel delinquent notice for last year's second installment on the storage yard is not a bill; that parcel is flagged
    and the penalty stays out of this year's total                                 (checks: one row per parcel; county and delinquency flag)
  * parcel numbers print without hyphens on the scan and with a trailing sub-parcel code on Keel bills (check: one row per parcel)
  * the vacant lot's bill is an image-only scan                                    (checks: installments; due dates)
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

HEADER = ["parcel_number", "county", "assessed_value", "exemptions", "taxable_value", "total_tax", "first_installment", "first_due",
          "second_installment", "second_due", "prior_year_delinquent"]
J_LEVIES = [("Juniper County general fund", 2.8150), ("Pine Hollow School District 14", 4.9022), ("Juniper Fire District 3", 1.4100),
            ("Juniper County library", 0.3950), ("School bond 2019", 0.6620)]
K_RATE = [("Keel County", 0.8420), ("Keel Unified Schools", 1.1375), ("North Keel Water District", 0.1290), ("Keel Community College", 0.1545)]
J_DUE = (date(2026, 11, 1), date(2027, 2, 1))
J_DELQ = (date(2026, 12, 10), date(2027, 4, 10))
K_DUE = (date(2026, 10, 31), date(2027, 3, 31))


def c2(x: float) -> float:
    return round(x + 1e-9, 2)


def build(seed: int) -> dict:
    r = rng(seed)
    P = []

    def juniper(key, apn, desc, land, imp, exempt, specials, layout):
        assessed = land + imp
        taxable = assessed - exempt
        levies = [(n, rate, c2(taxable * rate / 1000)) for n, rate in J_LEVIES]
        adval = c2(sum(x[2] for x in levies))
        total = c2(adval + sum(v for _, v in specials))
        cents = round(total * 100)
        first, second = math.ceil(cents / 2) / 100, math.floor(cents / 2) / 100
        P.append({"key": key, "county": "Juniper", "apn": apn, "desc": desc, "land": land, "imp": imp, "assessed": assessed, "exempt": exempt,
                  "taxable": taxable, "levies": levies, "adval": adval, "specials": specials, "total": total, "first": first, "second": second,
                  "due": J_DUE, "delq": J_DELQ, "layout": layout, "delinquent": False})

    def keel(key, apn, desc, market, exempt, weed, layout):
        assessed = round(market * 0.40)
        taxable = assessed - exempt
        rate = sum(x[1] for x in K_RATE)
        lines = [(n, rt, c2(taxable * rt / 100)) for n, rt in K_RATE]
        total = c2(sum(x[2] for x in lines) + weed)
        cents = round(total * 100)
        first, second = math.ceil(cents / 2) / 100, math.floor(cents / 2) / 100
        P.append({"key": key, "county": "Keel", "apn": apn, "desc": desc, "market": market, "assessed": assessed, "exempt": exempt, "taxable": taxable,
                  "lines": lines, "weed": weed, "total": total, "first": first, "second": second, "due": K_DUE, "layout": layout, "delinquent": False,
                  "rate": rate})
    b1, b2 = r.randint(210, 260), r.randint(10, 60)
    juniper("J1", f"041-{b1}-17", "Campground and RV sites, 22.4 ac", r.randrange(380000, 460000, 500), r.randrange(1050000, 1250000, 500), 0,
            [("Solid waste service fee", float(r.choice([486.00, 512.00]))), ("Street lighting district", 38.20)], "A")
    juniper("J2", f"041-{b1}-18", "Manager residence", r.randrange(88000, 104000, 500), r.randrange(215000, 248000, 500), 7000,
            [("Solid waste service fee", 212.00)], "A")
    juniper("J3", f"041-{b1 + 2}-05", "Vacant lot (overflow parking)", r.randrange(38000, 52000, 500), 0, 0, [], "SCAN")
    keel("K1", f"207-00{b2}-00", "Storage yard", r.randrange(420000, 520000, 1000), 0, 45.00, "B")
    keel("K2", f"207-01{b2}-00", "Pasture (farm use)", r.randrange(1150000, 1320000, 1000), r.randrange(280000, 330000, 1000), 0.0, "B")
    for p in P:
        if (round(p["total"] * 100) % 2) == 0 and (p["county"] == "Keel" or p["layout"] == "SCAN"):
            return {"ok": False}
    k1 = [p for p in P if p["key"] == "K1"][0]
    k1["delinquent"] = True
    prior_second = c2(k1["second"] * r.uniform(0.94, 0.98))
    penalty = c2(prior_second * 0.10)
    notice = {"apn": k1["apn"], "year": "2025-26", "amount": prior_second, "penalty": penalty, "cost": 33.00,
              "total": c2(prior_second + penalty + 33.00), "notice_no": f"DQ-26-{r.randint(1000, 9999)}"}
    rows = []
    for p in P:
        rows.append([p["apn"], p["county"], str(p["assessed"]), str(p["exempt"]), str(p["taxable"]), f"{p['total']:.2f}", f"{p['first']:.2f}",
                     p["due"][0].isoformat(), f"{p['second']:.2f}", p["due"][1].isoformat(), "yes" if p["delinquent"] else "no"])
    return {"ok": True, "P": P, "notice": notice, "rows": rows}


def render(ws: str, d: dict, seed: int) -> dict:
    B = os.path.join(ws, "tax_bills_2026-27")
    os.makedirs(B, exist_ok=True)
    files = {}
    owner = "PINE HOLLOW RV RESORT LLC<br/>1 Hollow Creek Rd, Pine Hollow"
    for p in d["P"]:
        if p["layout"] == "A":
            files[p["key"]] = f"Juniper_County_{p['apn']}.pdf"
            lev = [["Taxing district", "Rate per $1,000", "Amount"]] + [[n, f"{rt:.4f}", f"{amt:,.2f}"] for n, rt, amt in p["levies"]]
            lev.append(["<b>Total ad valorem tax</b>", "", f"<b>{p['adval']:,.2f}</b>"])
            spec = [["Special assessments", "", "Amount"]] + [[n, "", f"{v:,.2f}"] for n, v in p["specials"]]
            spec.append(["<b>Total taxes and assessments</b>", "", f"<b>{p['total']:,.2f}</b>"])
            write_pdf_document(os.path.join(B, files[p["key"]]), [
                ("title", "Juniper County Property Tax Statement"), ("small", "Office of the Treasurer - Tax year 2026-2027 (July 1, 2026 - June 30, 2027)"),
                ("hr", None),
                ("kv", [("Parcel (APN)", p["apn"]), ("Owner", owner), ("Situs / description", p["desc"])]), ("spacer", 6),
                ("table", [["Assessed land", "Assessed improvements", "Total assessed value", "Exemptions", "Net taxable value"],
                           [f"{p['land']:,}", f"{p['imp']:,}", f"{p['assessed']:,}",
                            f"{p['exempt']:,} (homeowner)" if p["exempt"] else "0", f"{p['taxable']:,}"]],
                 {"col_widths": [85, 105, 105, 95, 100], "grid": True, "shade_header": True}), ("spacer", 8),
                ("table", lev, {"col_widths": [260, 100, 100]}), ("spacer", 4),
                ("table", spec, {"col_widths": [260, 100, 100]}), ("spacer", 10),
                ("table", [["Installment", "Amount", "Due", "Delinquent after"],
                           ["1st installment", f"{p['first']:,.2f}", p["due"][0].strftime("%m/%d/%Y"), p["delq"][0].strftime("%m/%d/%Y")],
                           ["2nd installment", f"{p['second']:,.2f}", p["due"][1].strftime("%m/%d/%Y"), p["delq"][1].strftime("%m/%d/%Y")]],
                 {"col_widths": [110, 100, 100, 110], "grid": True}), ("spacer", 6),
                ("small", "A 10% penalty is added to any installment not paid by its delinquency date.")], pagesize="letter", font="Helvetica", base_size=9)
        elif p["layout"] == "B":
            files[p["key"]] = f"KeelCounty_secured_tax_{p['apn'].replace('-', '')}.pdf"
            lines = [["Levy", "Rate %", "Tax"]] + [[n, f"{rt:.4f}", f"{amt:,.2f}"] for n, rt, amt in p["lines"]]
            if p["weed"]:
                lines.append(["Weed abatement assessment", "", f"{p['weed']:,.2f}"])
            write_pdf_document(os.path.join(B, files[p["key"]]), [
                ("right", "COUNTY OF KEEL<br/>Tax Collector<br/>2026-2027 Secured Property Tax Bill"), ("spacer", 6),
                ("p", f"Assessor's parcel number: {p['apn']}-000<br/>Assessed to: Pine Hollow RV Resort LLC<br/>Property: {p['desc']}"), ("spacer", 6),
                ("kv", [("Market (real cash) value", f"${p['market']:,}"), ("Assessed value (40% of market)", f"${p['assessed']:,}"),
                        ("Less exemption - farm use" if p["exempt"] else "Less exemptions", f"${p['exempt']:,}"),
                        ("Taxable value", f"${p['taxable']:,}")], {"col_widths": [200, 120]}), ("spacer", 6),
                ("table", lines, {"col_widths": [240, 80, 100], "grid": True}), ("spacer", 6),
                ("h", f"TOTAL TAX DUE ${p['total']:,.2f}"),
                ("p", f"The total may be paid in two equal installments: the first due {p['due'][0].strftime('%B %-d, %Y')} and the second due "
                      f"{p['due'][1].strftime('%B %-d, %Y')}. Where the total does not divide evenly, the extra cent is added to the first installment."),
                ("small", "Keel County does not mail a second bill for the second installment.")], pagesize="a4", font="Times-Roman", base_size=10)
        else:
            files[p["key"]] = f"scan_juniper_{p['apn'].replace('-', '')}.pdf"
            apn = p["apn"].replace("-", "")
            L = ["JUNIPER COUNTY PROPERTY TAX STATEMENT", "TAX YEAR 2026-2027", "", f"APN {apn}", "PINE HOLLOW RV RESORT LLC",
                 p["desc"].upper(), "", f"TOTAL ASSESSED VALUE  {p['assessed']}", "EXEMPTIONS  0", f"NET TAXABLE VALUE  {p['taxable']}", "",
                 f"TOTAL AD VALOREM TAX  {p['adval']:.2f}", "SPECIAL ASSESSMENTS  0.00", f"TOTAL TAXES AND ASSESSMENTS  {p['total']:.2f}", "",
                 "- - - - - - DETACH AND RETURN WITH PAYMENT - - - - - -", "",
                 f"2ND INSTALLMENT  APN {apn}", f"AMOUNT {p['second']:.2f}  DUE {p['due'][1].strftime('%m/%d/%Y')}",
                 f"DELINQUENT AFTER {p['delq'][1].strftime('%m/%d/%Y')}", "",
                 f"1ST INSTALLMENT  APN {apn}", f"AMOUNT {p['first']:.2f}  DUE {p['due'][0].strftime('%m/%d/%Y')}",
                 f"DELINQUENT AFTER {p['delq'][0].strftime('%m/%d/%Y')}"]
            write_scan_pdf(os.path.join(B, files[p["key"]]), L, font_size=30, skew_deg=0.4, noise=400, seed=seed * 23 + 9)
    n = d["notice"]
    files["NOTICE"] = f"KeelCounty_notice_{n['notice_no']}.pdf"
    write_pdf_document(os.path.join(B, files["NOTICE"]), [
        ("title", "NOTICE OF DELINQUENT PROPERTY TAX"), ("p", "COUNTY OF KEEL - TAX COLLECTOR"), ("hr", None),
        ("p", f"NOTICE NO {n['notice_no']}<br/>PARCEL {n['apn']}-000<br/>ASSESSEE PINE HOLLOW RV RESORT LLC<br/>TAX YEAR {n['year']}"), ("spacer", 6),
        ("table", [["ITEM", "AMOUNT"], ["2ND INSTALLMENT UNPAID (DUE 03/31/2026)", f"{n['amount']:,.2f}"], ["DELINQUENT PENALTY 10%", f"{n['penalty']:,.2f}"],
                   ["COST", f"{n['cost']:,.2f}"], ["AMOUNT REQUIRED TO REDEEM", f"{n['total']:,.2f}"]], {"col_widths": [300, 120], "grid": True}),
        ("spacer", 6), ("p", "PAY BY 10/15/2026 TO AVOID ADDITIONAL INTEREST OF 1.5% PER MONTH. THIS NOTICE DOES NOT INCLUDE 2026-2027 TAXES.")],
        pagesize="letter", font="Courier", base_size=9)
    return files


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    files = render(ws, d, seed)
    rng_ = rng(seed + 5)
    sold = f"041-{rng_.randint(300, 399)}-02"
    write_csv(os.path.join(ws, "parcels.csv"), ["parcel_number", "county", "description", "status"],
              [[p["apn"], p["county"], p["desc"], "owned"] for p in d["P"]] + [[sold, "Juniper", "Former caretaker cabin lot", "sold 2026-05-14"]])
    write_text(os.path.join(ws, "note_from_walt.txt"),
               "Property taxes 2026-27\n\n"
               "The county bills came in (tax_bills_2026-27 folder). Please log them in tax_bills.csv so I can schedule the payments - one row "
               "per parcel we got a bill for:\n\n"
               "parcel_number: as it appears in parcels.csv\n"
               "county: Juniper or Keel\n"
               "assessed_value: the assessed value before exemptions (whole dollars)\n"
               "exemptions: total exemptions, 0 if none\n"
               "taxable_value: assessed value less exemptions\n"
               "total_tax: the whole bill for 2026-27, everything the county wants for the year\n"
               "first_installment, second_installment: the amounts\n"
               "first_due, second_due: the date each installment is due (YYYY-MM-DD) - I want the due date, not the last day before penalties\n"
               "prior_year_delinquent: yes if the county says we still owe anything from an earlier year on that parcel, otherwise no\n\n"
               "Walt\n")
    write_csv(os.path.join(ref, "tax_bills.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "tax_bills.csv"), HEADER, d["rows"])
    P = {p["key"]: p for p in d["P"]}
    sc = P["J3"]
    apn = sc["apn"].replace("-", "")
    figs = [apn, str(sc["assessed"]), f"{sc['total']:.2f}", f"AMOUNT {sc['first']:.2f}  DUE {sc['due'][0].strftime('%m/%d/%Y')}",
            f"AMOUNT {sc['second']:.2f}  DUE {sc['due'][1].strftime('%m/%d/%Y')}", "2ND INSTALLMENT", "1ST INSTALLMENT"]
    write_json(os.path.join(ref, "notes.json"), {"files": files, "notice": d["notice"], "sold_parcel": sold,
                                                  "scan_figures": {f"tax_bills_2026-27/{files['J3']}": figs}})
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    T = "tax_bills.csv"
    k = lambda *keys: [P[x]["apn"] for x in keys]
    write_task_yaml(HERE, {
        "id": "property-tax-bills", "track": "desk", "category": "extraction",
        "title": "Log this year's property tax bills",
        "ask": "This year's property tax bills are in the folder. Please log them in tax_bills.csv - Walt's note says what he needs to schedule the payments.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "two installments: Juniper prints both halves with a due date and a later 'delinquent after' date, Keel prints only the total with "
            "the rule (equal halves, the odd cent on the first), and the scanned bill's tear-off stubs print the second installment above the "
            "first (checks: installments; due dates)",
            f"exemptions: a 7,000 homeowner exemption on {P['J2']['apn']} and a farm-use exemption on the Keel pasture {P['K2']['apn']}; Keel "
            "prints the market value above the assessed value, which is 40% of market (check: assessed values and exemptions)",
            "Juniper prints 'Total ad valorem tax' first and adds solid waste and lighting special assessments before 'Total taxes and "
            "assessments' (check: total tax)",
            f"a Keel notice of delinquent tax for last year's second installment on the storage yard {P['K1']['apn']} sits among the bills; it "
            "is not a 2026-27 bill, the parcel is flagged yes, and its penalty and redemption amount stay out of this year's total "
            "(checks: one row per parcel; county and delinquency flag; total tax)",
            "parcel numbers print without hyphens on the scan and with a trailing '-000' on Keel bills; the parcel list's format is wanted, and a "
            "sold parcel in the list has no bill (checks: one row per parcel; row count)",
            f"the vacant lot's bill {P['J3']['apn']} is an image-only scan (checks: installments; due dates)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": T, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per parcel", "path": T, "column": "parcel_number", "ref": T, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": T, "equals_ref": T},
            {"type": "csv_values_match", "name": "county and delinquency flag", "path": T, "ref": T, "key": "parcel_number",
             "columns": ["county", "prior_year_delinquent"], "min_accuracy": 1.0, "must_match_keys": k("K1")},
            {"type": "csv_values_match", "name": "assessed values and exemptions", "path": T, "ref": T, "key": "parcel_number",
             "columns": ["assessed_value", "exemptions", "taxable_value"], "must_match_keys": k("J2", "K1", "K2"), **num},
            {"type": "csv_values_match", "name": "total tax", "path": T, "ref": T, "key": "parcel_number", "columns": ["total_tax"],
             "must_match_keys": k("J1", "J2", "K1"), **num},
            {"type": "csv_values_match", "name": "installments", "path": T, "ref": T, "key": "parcel_number",
             "columns": ["first_installment", "second_installment"], "must_match_keys": k("K1", "K2", "J3"), **num},
            {"type": "csv_values_match", "name": "due dates", "path": T, "ref": T, "key": "parcel_number", "columns": ["first_due", "second_due"],
             "min_accuracy": 1.0, "must_match_keys": k("J1", "J2", "J3")},
        ],
    })
    print(f"seed={seed} parcels={len(d['rows'])} " + ", ".join(f"{p['apn']}={p['total']}" for p in d["P"]))


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: the first value on each bill as assessed (market value on Keel), exemptions only where Juniper's
    table shows them, the first total printed (ad valorem on Juniper), Keel halves rounded independently, the scan's first stub read
    as the first installment, the delinquency dates as due dates, parcel numbers as printed, no delinquency flag."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for p in d["P"]:
        if p["county"] == "Juniper":
            first, second = (p["second"], p["first"]) if p["layout"] == "SCAN" else (p["first"], p["second"])
            apn = p["apn"].replace("-", "") if p["layout"] == "SCAN" else p["apn"]
            rows.append([apn, "Juniper", p["assessed"], p["exempt"], p["taxable"], f"{p['adval']:.2f}", f"{first:.2f}", p["delq"][0].isoformat(),
                         f"{second:.2f}", p["delq"][1].isoformat(), "no"])
        else:
            half = round(p["total"] / 2, 2)
            rows.append([p["apn"] + "-000", "Keel", p["market"], 0, p["market"], f"{p['total']:.2f}", f"{half:.2f}", p["due"][0].isoformat(),
                         f"{half:.2f}", p["due"][1].isoformat(), "no"])
    write_csv(os.path.join(out, "tax_bills.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if d_["ok"]:
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, d_, a.naive)
