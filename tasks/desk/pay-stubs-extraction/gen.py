#!/usr/bin/env python3
"""pay-stubs-extraction: August pay stubs from two payroll providers, a manual check and a scan -> one row per stub.

    python gen.py [--seed N] [--naive DIR]

Business: Larkin & Bose Architects moved payroll from PayCrest to Ledgerline in August. Their CPA wants every August pay
stub keyed with gross, net and each deduction to reconcile payroll to the bank and the general ledger.

Traps (each caught by a check, see task.yaml):
  * every stub prints year-to-date figures beside the period figures: PayCrest puts Current before YTD, Ledgerline puts YTD
    before This period, the scan prints both on each line                          (checks: gross and net; taxes)
  * Ledgerline lists a deduction called "401(k)" under both Before-Tax and After-Tax headings; the after-tax one is the Roth
                                                                                     (checks: pre-tax deductions; after-tax deductions)
  * health cover is split into Medical, Dental and Vision lines that add into one pre-tax health figure (check: pre-tax deductions)
  * one Ledgerline stub carries a Bonus earnings line with a separate federal supplemental withholding line (checks: bonus; taxes)
  * a 24 July PayCrest stub sits in the folder with the August ones                 (checks: one row per stub; row count)
  * one employee's 21 August stub is an image-only scan                            (checks: gross and net; taxes)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["stub_no", "employee_id", "pay_date", "gross_pay", "bonus_pay", "federal_income_tax", "social_security", "medicare",
          "state_income_tax", "pretax_401k", "pretax_health", "roth_401k", "net_pay"]
C2 = lambda x: round(x + 1e-9, 2)


def calc(emp: dict, periods_before: int, bonus: float = 0.0, hours: float | None = None, ot: float = 0.0, history: bool = True) -> dict:
    if emp["kind"] == "salary":
        regular = C2(emp["annual"] / 26)
    else:
        regular = C2(emp["rate"] * (hours if hours is not None else 80))
    overtime = C2(emp.get("rate", 0) * 1.5 * ot)
    gross = C2(regular + overtime + bonus)
    k401 = C2((regular + overtime) * emp["k401"])
    health = C2(sum(emp["health"].values()))
    roth = C2(emp["roth_flat"] if emp.get("roth_flat") else (regular + overtime) * emp.get("roth", 0))
    fica_base = gross - health
    ss, med = C2(fica_base * 0.062), C2(fica_base * 0.0145)
    fit = C2(max(0.0, regular + overtime - k401 - health - 620) * 0.14)
    supp = C2(bonus * 0.22)
    st = C2(max(0.0, gross - k401 - health) * 0.0725)
    net = C2(gross - k401 - health - fit - supp - ss - med - st - roth)
    s = {"regular": regular, "overtime": overtime, "bonus": bonus, "gross": gross, "k401": k401, "health": health, "roth": roth,
         "fit": fit, "supp": supp, "ss": ss, "med": med, "st": st, "net": net, "hours": hours if hours is not None else 80, "ot": ot}
    if history:
        # YTD = this stub plus earlier pay periods at the employee's usual hours, so every YTD column adds up
        prior = calc(emp, 0, hours=emp.get("usual_hours"), ot=emp.get("usual_ot", 0.0), history=False)
        s["ytd"] = {k: C2(s[k] + prior[k] * periods_before) for k in ("regular", "overtime", "bonus", "gross", "k401", "health", "roth",
                                                                     "fit", "supp", "ss", "med", "st", "net")}
        s["ytd_health"] = {hk: C2(hv * (periods_before + 1)) for hk, hv in emp["health"].items()}
    return s


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, 4)
    ids = sorted(r.sample(range(1001, 1060), 4))
    E = [
        {"id": str(ids[0]), "name": names[0], "kind": "salary", "annual": float(r.choice([92000, 96500, 101000])), "k401": 0.06, "roth": 0.0,
         "health": {"Medical": r.choice([142.50, 156.20]), "Dental": 18.20, "Vision": 6.45}, "title": "Project Architect"},
        {"id": str(ids[1]), "name": names[1], "kind": "salary", "annual": float(r.choice([74000, 78000, 81500])), "k401": 0.04, "roth": 0.03,
         "health": {"Medical": r.choice([96.00, 104.75]), "Dental": 18.20}, "title": "Designer"},
        {"id": str(ids[2]), "name": names[2], "kind": "hourly", "rate": float(r.choice([36.50, 38.50, 41.00])), "k401": 0.0, "roth_flat": 50.00,
         "health": {"Medical": r.choice([64.10, 71.30])}, "title": "CAD Technician"},
        {"id": str(ids[3]), "name": names[3], "kind": "hourly", "rate": float(r.choice([22.00, 23.50])), "k401": 0.0, "roth": 0.0, "health": {},
         "title": "Drafter (part-time)"},
    ]
    E[2]["usual_ot"] = float(r.choice([2, 3, 4]))
    E[3]["usual_hours"] = float(r.choice([24, 26, 30]))
    stubs = []
    adv = r.randint(108700, 108800)
    ll = r.randint(420, 460)
    stubs.append({"key": "JUL", "emp": E[0], "provider": "PayCrest", "no": str(adv - 3), "date": date(2026, 7, 24), "period": (date(2026, 7, 6), date(2026, 7, 19)), **calc(E[0], 13)})
    for i, e in enumerate(E[:3]):
        kw = {"ot": float(r.choice([4, 6, 7.5]))} if e["kind"] == "hourly" else {}
        stubs.append({"key": f"PC{i}", "emp": e, "provider": "PayCrest", "no": str(adv + i), "date": date(2026, 8, 7), "period": (date(2026, 7, 20), date(2026, 8, 2)),
                      **calc(e, 14, **kw)})
    stubs.append({"key": "MAN", "emp": E[3], "provider": "Manual", "no": str(r.randint(5510, 5540)), "date": date(2026, 8, 14), "period": (date(2026, 8, 1), date(2026, 8, 14)),
                  **calc(E[3], 15, hours=float(r.choice([28.5, 31.5, 34.0])))})
    stubs.append({"key": "LL0", "emp": E[0], "provider": "Ledgerline", "no": f"LL-{ll:05d}", "date": date(2026, 8, 21), "period": (date(2026, 8, 3), date(2026, 8, 16)),
                  **calc(E[0], 15, bonus=float(r.choice([1500, 2000, 2500])))})
    stubs.append({"key": "LL1", "emp": E[1], "provider": "Ledgerline", "no": f"LL-{ll + 1:05d}", "date": date(2026, 8, 21), "period": (date(2026, 8, 3), date(2026, 8, 16)),
                  **calc(E[1], 15)})
    stubs.append({"key": "SCAN", "emp": E[2], "provider": "Ledgerline", "no": f"LL-{ll + 2:05d}", "date": date(2026, 8, 21), "period": (date(2026, 8, 3), date(2026, 8, 16)),
                  **calc(E[2], 15, ot=float(r.choice([2, 3, 5])))})
    rows = []
    for s in stubs:
        if s["date"].month != 8:
            continue
        rows.append([s["no"], s["emp"]["id"], s["date"].isoformat()] + [f"{x:.2f}" for x in
                    (s["gross"], s["bonus"], C2(s["fit"] + s["supp"]), s["ss"], s["med"], s["st"], s["k401"], s["health"], s["roth"], s["net"])])
    return {"E": E, "stubs": stubs, "rows": rows}


def m(x: float) -> str:
    return f"{x:,.2f}"


def render(ws: str, d: dict, seed: int) -> dict:
    P = os.path.join(ws, "august_pay_stubs")
    os.makedirs(P, exist_ok=True)
    files = {}
    co = "Larkin &amp; Bose Architects LLP - 610 SW Alder St, Portland OR 97205"
    for s in d["stubs"]:
        e = s["emp"]; y = s["ytd"]
        nm = f"{e['name'][0]} {e['name'][1]}"
        if s["provider"] == "PayCrest":
            earn = [["Earnings", "Rate", "Hours", "Current", "YTD"]]
            if e["kind"] == "salary":
                earn.append(["Salary", "", "80.00", m(s["regular"]), m(y["regular"])])
            else:
                earn.append(["Regular", f"{e['rate']:.2f}", f"{s['hours']:.2f}", m(s["regular"]), m(y["regular"])])
                earn.append(["Overtime", f"{e['rate'] * 1.5:.2f}", f"{s['ot']:.2f}", m(s["overtime"]), m(y["overtime"])])
            ded = [["Deductions and taxes", "Type", "Current", "YTD"],
                   ["FED WITHHOLDING", "Tax", m(s["fit"]), m(y["fit"])], ["SOC SEC", "Tax", m(s["ss"]), m(y["ss"])],
                   ["MEDICARE", "Tax", m(s["med"]), m(y["med"])], ["OR STATE TAX", "Tax", m(s["st"]), m(y["st"])]]
            if s["k401"]:
                ded.append(["401K PRE", "Pre-tax", m(s["k401"]), m(y["k401"])])
            for hk, hv in e["health"].items():
                ded.append([f"{hk.upper()} SEC125", "Pre-tax", m(hv), m(s["ytd_health"][hk])])
            if s["roth"]:
                ded.append(["ROTH 401K", "Post-tax", m(s["roth"]), m(y["roth"])])
            files[s["key"]] = f"PayCrest_{e['name'][1]}_{s['date'].isoformat()}.pdf"
            write_pdf_document(os.path.join(P, files[s["key"]]), [
                ("title", "Earnings Statement"), ("small", "PayCrest Payroll Services on behalf of " + co), ("hr", None),
                ("kv", [("Employee", nm), ("Employee ID", e["id"]), ("Advice No.", s["no"]), ("Pay date", s["date"].strftime("%m/%d/%Y")),
                        ("Pay period", f"{s['period'][0].strftime('%m/%d/%Y')} - {s['period'][1].strftime('%m/%d/%Y')}")]), ("spacer", 8),
                ("table", earn, {"col_widths": [150, 60, 60, 100, 100], "shade_header": True}), ("spacer", 8),
                ("table", ded, {"col_widths": [150, 70, 100, 100], "shade_header": True}), ("spacer", 8),
                ("table", [["", "Current", "YTD"], ["Gross pay", m(s["gross"]), m(y["gross"])], ["Net pay", m(s["net"]), m(y["net"])]],
                 {"col_widths": [150, 100, 100], "grid": True}), ("spacer", 6),
                ("small", "Net pay deposited to checking ending 4471. This is a non-negotiable advice.")], pagesize="letter", font="Helvetica", base_size=9)
        elif s["provider"] == "Manual":
            files[s["key"]] = f"manual_check_{s['no']}.pdf"
            write_pdf_document(os.path.join(P, files[s["key"]]), [
                ("h", "LARKIN AND BOSE ARCHITECTS LLP - PAYROLL CHECK STUB"),
                ("p", f"CHECK NO {s['no']}<br/>PAY DATE {s['date'].strftime('%d-%b-%Y').upper()}<br/>EMPLOYEE {nm.upper()}  (EE {e['id']})<br/>"
                      f"PERIOD {s['period'][0].strftime('%m/%d')} - {s['period'][1].strftime('%m/%d/%Y')}"), ("spacer", 6),
                ("table", [["ITEM", "THIS CHECK", "YEAR TO DATE"],
                           [f"REGULAR {s['hours']:.1f} HRS @ {e['rate']:.2f}", m(s["regular"]), m(y["regular"])],
                           ["GROSS", m(s["gross"]), m(y["gross"])], ["FEDERAL W/H", m(s["fit"]), m(y["fit"])],
                           ["FICA SS", m(s["ss"]), m(y["ss"])], ["FICA MED", m(s["med"]), m(y["med"])], ["OREGON W/H", m(s["st"]), m(y["st"])],
                           ["NET CHECK", m(s["net"]), m(y["net"])]], {"col_widths": [200, 100, 120], "grid": True}), ("spacer", 6),
                ("small", "OFF-CYCLE MANUAL CHECK - PART-TIME HOURS NOT IN THE PROVIDER CHANGEOVER RUN. ENTERED BY OFFICE MANAGER.")],
                pagesize="letter", font="Courier", base_size=9)
        elif s["key"] != "SCAN":
            earn = [["Earnings", "Hours", "YTD", "This period"], ["Regular salary", "80.00", m(y["regular"]), m(s["regular"])]]
            if s["bonus"]:
                earn.append(["Bonus - project milestone", "", m(y["bonus"]), m(s["bonus"])])
            earn.append(["<b>Gross earnings</b>", "", m(y["gross"]), m(s["gross"])])
            tax = [["Taxes", "YTD", "This period"], ["Federal Income Tax", m(y["fit"]), m(s["fit"])]]
            if s["supp"]:
                tax.append(["Federal Supplemental (bonus)", m(y["supp"]), m(s["supp"])])
            tax += [["Social Security (OASDI)", m(y["ss"]), m(s["ss"])], ["Medicare (HI)", m(y["med"]), m(s["med"])], ["Oregon Income Tax", m(y["st"]), m(s["st"])]]
            pre = [["Before-Tax Deductions", "YTD", "This period"], ["401(k)", m(y["k401"]), m(s["k401"])]]
            pre += [[hk, m(s["ytd_health"][hk]), m(hv)] for hk, hv in e["health"].items()]
            post = [["After-Tax Deductions", "YTD", "This period"], ["401(k)", m(y["roth"]), m(s["roth"])]] if s["roth"] else \
                   [["After-Tax Deductions", "YTD", "This period"], ["None", "0.00", "0.00"]]
            files[s["key"]] = f"Ledgerline_{s['no']}.pdf"
            write_pdf_document(os.path.join(P, files[s["key"]]), [
                ("table", [["LEDGERLINE PAYROLL", f"NET PAY  {m(s['net'])}"], ["Pay statement", f"Voucher {s['no']}"]],
                 {"col_widths": [270, 200], "grid": True, "shade_header": True}), ("spacer", 6),
                ("p", f"{co}<br/>{nm}, {e['title']} - Employee # {e['id']}<br/>Check date {s['date'].strftime('%B %-d, %Y')} - "
                      f"period {s['period'][0].strftime('%b %-d')} to {s['period'][1].strftime('%b %-d, %Y')}"), ("spacer", 6),
                ("table", earn, {"col_widths": [200, 60, 100, 100]}), ("spacer", 6),
                ("table", tax, {"col_widths": [200, 100, 100]}), ("spacer", 6),
                ("table", pre, {"col_widths": [200, 100, 100]}), ("spacer", 6),
                ("table", post, {"col_widths": [200, 100, 100]}), ("spacer", 6),
                ("small", "Year-to-date amounts include earnings paid by your previous payroll provider.")], pagesize="a4", font="Times-Roman", base_size=10)
        else:
            L = ["LEDGERLINE PAYROLL  PAY STATEMENT", f"VOUCHER {s['no']}", f"EMPLOYEE {nm.upper()}  ID {e['id']}",
                 f"CHECK DATE {s['date'].strftime('%m/%d/%Y')}", "", "ITEM  THIS PERIOD  YEAR TO DATE", "",
                 f"REGULAR {s['hours']:.0f} HRS  {s['regular']:.2f}  YTD {y['regular']:.2f}",
                 f"OVERTIME {s['ot']:.0f} HRS  {s['overtime']:.2f}  YTD {y['overtime']:.2f}",
                 f"GROSS EARNINGS  {s['gross']:.2f}  YTD {y['gross']:.2f}", "",
                 f"FEDERAL INCOME TAX  {s['fit']:.2f}  YTD {y['fit']:.2f}", f"SOCIAL SECURITY  {s['ss']:.2f}  YTD {y['ss']:.2f}",
                 f"MEDICARE  {s['med']:.2f}  YTD {y['med']:.2f}", f"OREGON INCOME TAX  {s['st']:.2f}  YTD {y['st']:.2f}", "",
                 "BEFORE-TAX DEDUCTIONS"] + [f"{hk.upper()}  {hv:.2f}  YTD {s['ytd_health'][hk]:.2f}" for hk, hv in e["health"].items()] + \
                ["AFTER-TAX DEDUCTIONS", f"401K  {s['roth']:.2f}  YTD {y['roth']:.2f}", "", f"NET PAY  {s['net']:.2f}  YTD {y['net']:.2f}"]
            files[s["key"]] = f"scan_paystub_{e['name'][1].lower()}_0821.pdf"
            write_scan_pdf(os.path.join(P, files[s["key"]]), L, font_size=30, skew_deg=0.5, noise=450, seed=seed * 19 + 6)
    return files


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    files = render(ws, d, seed)
    write_csv(os.path.join(ws, "employee_list.csv"), ["employee_id", "name", "title", "pay_type"],
              [[e["id"], f"{e['name'][0]} {e['name'][1]}", e["title"], e["kind"]] for e in d["E"]])
    write_text(os.path.join(ws, "email_from_cpa.txt"),
               "From: Nadia Osei <nadia@mossbank.cpa>\nTo: Office Manager\nDate: Tue, 8 Sep 2026 10:02\nSubject: August payroll detail\n\n"
               "Hi - since you switched providers mid-month I can't pull August from one register. Can you key every pay stub dated in "
               "August into a sheet, one row per stub (pay_stubs.csv), with these columns:\n\n"
               "stub_no (advice, voucher or check number as printed), employee_id, pay_date (YYYY-MM-DD), gross_pay, bonus_pay (0 if none), "
               "federal_income_tax (all federal income tax withheld on that stub), social_security, medicare, state_income_tax, pretax_401k, "
               "pretax_health (medical, dental and vision together), roth_401k (after-tax retirement), net_pay.\n\n"
               "Amounts for that pay period only, plain numbers. I'll tie it out to the bank.\n\nThanks,\nNadia\n")
    write_csv(os.path.join(ref, "pay_stubs.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "pay_stubs.csv"), HEADER, d["rows"])
    S = {s["key"]: s for s in d["stubs"]}
    sc = S["SCAN"]
    figs = [sc["no"], sc["emp"]["id"], f"{sc['gross']:.2f}", f"{sc['net']:.2f}", f"{sc['fit']:.2f}", f"{sc['ss']:.2f}", f"{sc['med']:.2f}",
            f"{sc['st']:.2f}", f"{sc['roth']:.2f}", f"{sc['health']:.2f}"]
    write_json(os.path.join(ref, "notes.json"), {"files": files, "july_stub": S["JUL"]["no"],
                                                  "scan_figures": {f"august_pay_stubs/{files['SCAN']}": figs}})
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    P = "pay_stubs.csv"
    ll = [S[k]["no"] for k in ("LL0", "LL1", "SCAN")]
    pc = [S[k]["no"] for k in ("PC0", "PC1", "PC2")]
    write_task_yaml(HERE, {
        "id": "pay-stubs-extraction", "track": "desk", "category": "extraction",
        "title": "Key the August pay stubs for the CPA",
        "ask": "Nadia needs our August payroll detail from the pay stubs in the folder. Can you put it in pay_stubs.csv the way her email asks?\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "every stub prints year-to-date figures beside the period figures: PayCrest and the manual check put the period first, Ledgerline "
            "puts YTD first and This period last, and the scan prints 'YTD' after each amount; taking the rightmost column gives YTD on "
            "PayCrest (checks: gross and net; taxes; pre-tax deductions)",
            f"Ledgerline lists a deduction called '401(k)' under both the Before-Tax and After-Tax headings on {S['LL1']['no']} and the scan; "
            "the after-tax one is the Roth (checks: pre-tax deductions; after-tax deductions)",
            "health cover is printed as separate Medical, Dental and Vision lines (MEDICAL SEC125, DENTAL SEC125 on PayCrest) that add into one "
            "pre-tax health figure (check: pre-tax deductions)",
            f"{S['LL0']['no']} carries a Bonus earnings line and a separate 'Federal Supplemental (bonus)' withholding line that belongs in "
            "federal income tax (checks: bonus; taxes)",
            f"PayCrest advice {S['JUL']['no']} dated 24 July is in the folder with the August stubs (checks: one row per stub; row count)",
            f"the 21 August stub {S['SCAN']['no']} is an image-only scan (checks: gross and net; taxes; after-tax deductions)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per stub", "path": P, "column": "stub_no", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "employee and pay date", "path": P, "ref": P, "key": "stub_no",
             "columns": ["employee_id", "pay_date"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "gross and net", "path": P, "ref": P, "key": "stub_no", "columns": ["gross_pay", "net_pay"],
             "must_match_keys": pc + ll, **num},
            {"type": "csv_values_match", "name": "bonus", "path": P, "ref": P, "key": "stub_no", "columns": ["bonus_pay"],
             "must_match_keys": [S["LL0"]["no"]], **num},
            {"type": "csv_values_match", "name": "taxes", "path": P, "ref": P, "key": "stub_no",
             "columns": ["federal_income_tax", "social_security", "medicare", "state_income_tax"], "must_match_keys": pc + ll, **num},
            {"type": "csv_values_match", "name": "pre-tax deductions", "path": P, "ref": P, "key": "stub_no", "columns": ["pretax_401k", "pretax_health"],
             "must_match_keys": pc + ll, **num},
            {"type": "csv_values_match", "name": "after-tax deductions", "path": P, "ref": P, "key": "stub_no", "columns": ["roth_401k"],
             "must_match_keys": [S["LL1"]["no"], S["SCAN"]["no"], S["PC1"]["no"]], **num},
        ],
    })
    print(f"seed={seed} stubs={len(d['rows'])} files={len(files)}")


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: every stub in the folder (July too), the rightmost figure on each line (YTD on PayCrest and the
    manual check), every '401(k)' line treated as pre-tax, Medical only as health, the regular federal line only, no bonus column."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for s in d["stubs"]:
        v = s["ytd"] if s["provider"] in ("PayCrest", "Manual") else s
        med_only = (s["ytd_health"] if s["provider"] in ("PayCrest", "Manual") else s["emp"]["health"]).get("Medical", 0.0)
        k401 = v["k401"] + (v["roth"] if s["provider"] == "Ledgerline" else 0)
        roth = 0.0 if s["provider"] == "Ledgerline" else v["roth"]
        rows.append([s["no"], s["emp"]["id"], s["date"].isoformat()] + [f"{x:.2f}" for x in
                    (v["gross"], 0.0, v["fit"], v["ss"], v["med"], v["st"], k401, med_only, roth, v["net"])])
    write_csv(os.path.join(out, "pay_stubs.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, build(a.seed), a.naive)
