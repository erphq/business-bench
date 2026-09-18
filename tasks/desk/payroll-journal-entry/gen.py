#!/usr/bin/env python3
"""payroll-journal-entry: one semi-monthly payroll register into the balanced journal entry for the books.

    python gen.py [--seed N] [--naive DIR]

Business: Pemberton HVAC runs payroll through its provider twice a month. The provider's register export has the
employee table with a totals row and, below it, the company's own taxes and benefit contributions. The accountant's
email maps it to the chart of accounts and says how the entry is built.

Traps (each caught by a check, see task.yaml):
  * employer taxes and contributions live in a second section under the employee totals     (checks: account amounts; debits equal credits)
  * deductions are liabilities: wages are expensed gross, 401(k)/medical/garnishment credited  (check: account amounts)
  * FICA payable carries the employee and employer halves; 401(k) and health payables include the company's share
                                                                                             (check: account amounts)
  * reimbursements ride in net pay but are not wages                                        (checks: account amounts; debits equal credits)
  * the owner's salary is officer compensation, not office wages                            (check: account amounts)
  * the register has a totals row that a column sum double counts                           (checks: account amounts; debits equal credits)
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

ACCOUNTS = [
    ("1010", "Operating checking", "Bank"), ("1020", "Payroll clearing (inactive since 2025)", "Bank"),
    ("2100", "Accrued wages payable", "Other current liability"), ("2110", "Federal income tax withheld", "Other current liability"),
    ("2115", "FICA payable (Social Security & Medicare)", "Other current liability"), ("2120", "State income tax withheld", "Other current liability"),
    ("2130", "FUTA payable", "Other current liability"), ("2135", "State unemployment (SUI) payable", "Other current liability"),
    ("2140", "401(k) payable", "Other current liability"), ("2145", "Health insurance payable", "Other current liability"),
    ("2150", "Wage garnishments payable", "Other current liability"),
    ("6010", "Wages - field technicians", "Expense"), ("6020", "Wages - office & admin", "Expense"), ("6030", "Officer compensation", "Expense"),
    ("6040", "Contract labor", "Expense"), ("6110", "Payroll tax expense", "Expense"), ("6120", "Employee benefits - health", "Expense"),
    ("6130", "Employee benefits - retirement", "Expense"), ("6310", "Employee expense reimbursements", "Expense"),
]
NAMES = {a: n for a, n, _ in ACCOUNTS}


def c(x):
    return round(x + 0.0, 2)


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = people(r, 15)
    emps = []
    for i, (f, l) in enumerate(ppl[:14]):
        if i == 0:
            role, dept, title = "officer", "OFC", "Owner / President"
        elif i <= 3:
            role, dept, title = "office", "OFC", r.choice(["Office manager", "Dispatcher", "Bookkeeper"])
        else:
            role, dept, title = "field", "FLD", r.choice(["HVAC technician", "Lead technician", "Installer", "Apprentice"])
        e = {"name": f"{l}, {f}", "first": f, "dept": dept, "title": title, "role": role}
        if role == "field":
            lo, hi = {"Apprentice": (20, 26), "Installer": (26, 33), "HVAC technician": (31, 39), "Lead technician": (38, 46)}[title]
            rate = money(r, lo, hi)
            reg_h = float(r.choice([80, 80, 88, 76, 84]))
            ot_h = float(r.choice([0, 0, 2.5, 4, 6, 8.5]))
            e.update(pay_type="Hourly", reg_h=reg_h, ot_h=ot_h, reg=c(rate * reg_h), ot=c(rate * 1.5 * ot_h))
        else:
            annual = {"officer": r.choice([168000, 180000, 192000]), "office": r.choice([52000, 58500, 61000, 67000])}[role]
            e.update(pay_type="Salary", reg_h=86.67, ot_h=0.0, reg=c(annual / 24), ot=0.0)
        e["bonus"] = float(r.choice([0, 0, 0, 250, 500])) if role == "field" else 0.0
        e["reimb"] = c(money(r, 18, 140)) if role == "field" and r.random() < 0.45 else 0.0
        e["gross"] = c(e["reg"] + e["ot"] + e["bonus"])
        e["k401"] = c(e["gross"] * r.choice([0, 0.03, 0.05, 0.06])) if role != "officer" else c(e["gross"] * 0.10)
        enrolled = r.random() < 0.7 or role == "officer"
        e["med"] = float(r.choice([95.0, 210.0])) if enrolled else 0.0
        e["er_med"] = 420.00 if enrolled else 0.0
        e["garn"] = 150.00 if i == 7 else 0.0
        e["ss"] = 0.0 if role == "officer" else c(e["gross"] * 0.062)      # owner is past the Social Security wage base
        e["medicare"] = c(e["gross"] * 0.0145)
        taxable = e["gross"] - e["k401"] - e["med"]
        e["fit"] = c(taxable * r.uniform(0.07, 0.15))
        e["sit"] = c(taxable * r.uniform(0.035, 0.05))
        e["net"] = c(e["gross"] - e["fit"] - e["ss"] - e["medicare"] - e["sit"] - e["k401"] - e["med"] - e["garn"] + e["reimb"])
        e["er_ss"] = e["ss"]
        e["er_medicare"] = e["medicare"]
        e["futa"] = c(e["gross"] * 0.006) if i == 13 else 0.0              # a July hire still under the FUTA wage base
        e["sui"] = c(e["gross"] * 0.021) if i in (12, 13) else 0.0
        e["match"] = c(min(e["k401"], e["gross"] * 0.04)) if role != "officer" else 0.0
        e["method"] = "Check" if i in (5, 11) else "Direct deposit"
        emps.append(e)
    emps.sort(key=lambda e: e["name"])
    T = lambda k: c(sum(e[k] for e in emps))
    je = {
        "6010": c(sum(e["gross"] for e in emps if e["role"] == "field")),
        "6020": c(sum(e["gross"] for e in emps if e["role"] == "office")),
        "6030": c(sum(e["gross"] for e in emps if e["role"] == "officer")),
        "6110": c(T("er_ss") + T("er_medicare") + T("futa") + T("sui")),
        "6120": T("er_med"),
        "6130": T("match"),
        "6310": T("reimb"),
        "1010": -T("net"),
        "2110": -T("fit"),
        "2115": -c(T("ss") + T("medicare") + T("er_ss") + T("er_medicare")),
        "2120": -T("sit"),
        "2130": -T("futa"),
        "2135": -T("sui"),
        "2140": -c(T("k401") + T("match")),
        "2145": -c(T("med") + T("er_med")),
        "2150": -T("garn"),
    }
    assert abs(sum(je.values())) < 0.005, sum(je.values())
    return {"emps": emps, "je": je, "T": {k: T(k) for k in ("reg", "ot", "bonus", "reimb", "gross", "fit", "ss", "medicare", "sit", "k401", "med", "garn",
                                                             "net", "er_ss", "er_medicare", "futa", "sui", "match", "er_med")}}


def emit(seed, naive_dir):
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    emps, T = d["emps"], d["T"]
    owner = next(e for e in emps if e["role"] == "officer")
    header = ["Employee", "Dept", "Title", "Pay type", "Reg hours", "OT hours", "Regular", "Overtime", "Bonus", "Gross earnings",
              "Federal income tax", "Social Security", "Medicare", "State income tax", "401(k)", "Medical (pre-tax)", "Garnishment",
              "Reimbursements", "Net pay", "Payment"]
    rows = []
    for e in emps:
        rows.append([e["name"], e["dept"], e["title"], e["pay_type"], e["reg_h"], e["ot_h"] or None, e["reg"], e["ot"] or None, e["bonus"] or None,
                     e["gross"], e["fit"], e["ss"], e["medicare"], e["sit"], e["k401"] or None, e["med"] or None, e["garn"] or None,
                     e["reimb"] or None, e["net"], e["method"]])
    rows.append(["Company totals", "", "", "", c(sum(e["reg_h"] for e in emps)), c(sum(e["ot_h"] for e in emps)), T["reg"], T["ot"], T["bonus"], T["gross"],
                 T["fit"], T["ss"], T["medicare"], T["sit"], T["k401"], T["med"], T["garn"], T["reimb"], T["net"], ""])
    rows.append([])
    rows.append(["Employer taxes & contributions (not deducted from employees)"])
    rows.append(["Item", "", "", "", "", "", "", "", "", "Amount"])
    for label, key in (("Employer Social Security", "er_ss"), ("Employer Medicare", "er_medicare"), ("Federal unemployment (FUTA)", "futa"),
                       ("State unemployment (SUI)", "sui"), ("401(k) employer match", "match"), ("Employer medical contribution", "er_med")):
        rows.append([label, "", "", "", "", "", "", "", "", T[key]])
    rows.append(["Total employer cost", "", "", "", "", "", "", "", "", c(T["er_ss"] + T["er_medicare"] + T["futa"] + T["sui"] + T["match"] + T["er_med"])])
    rows.append([])
    rows.append(["Funding: net pay debited from operating account 09/03/2026; taxes impounded by provider 09/03/2026"])
    write_xlsx(os.path.join(ws, "payroll_register_2026-09-04.xlsx"), {"Payroll register": {
        "merged_title": "Pemberton HVAC - Payroll register - Pay period 08/16/2026 to 08/31/2026 - Check date 09/04/2026",
        "header": header, "rows": rows, "widths": {"A": 26, "C": 18, "J": 14, "S": 12},
        "number_formats": {col: "#,##0.00" for col in "GHIJKLMNOPQRS"}}}, creator="Payroll provider")
    write_csv(os.path.join(ws, "chart_of_accounts.csv"), ["Account", "Name", "Type"], [list(a) for a in ACCOUNTS])
    write_email_thread(os.path.join(ws, "email_from_grace.txt"), [
        {"from": "Grace Lindqvist <grace@mossbank.cpa>", "to": "you", "date": "Fri, 4 Sep 2026 10:15",
         "subject": "journal entry for today's payroll",
         "body": ("Can you turn today's payroll register into the journal entry for the books? One entry dated the check date, "
                  "one line per account, and it has to balance.\n\n"
                  "The import takes account_number, account_name, debit and credit.\n\n"
                  f"- Wages go in at gross by department: field techs to 6010, office to 6020. {owner['first']}'s salary is officer "
                  "compensation, 6030.\n"
                  "- What the company pays on top - its half of Social Security and Medicare, FUTA and SUI - is payroll tax "
                  "expense, 6110, and it's owed until the provider files, so it's a liability too. Social Security and "
                  "Medicare, both halves, sit together in 2115.\n"
                  "- What comes out of people's pay is owed to somebody else, not an expense: withholding to 2110 and 2120, "
                  "401(k) to 2140, their medical premium to 2145, the garnishment to 2150. Our 401(k) match (6130) and our "
                  "medical contribution (6120) are owed to the same places.\n"
                  "- Mileage and tool reimbursements are paid with payroll but they aren't wages - 6310.\n"
                  "- Net pay, checks and direct deposit alike, comes out of operating checking, 1010.")}])
    header_out = ["account_number", "account_name", "debit", "credit"]
    order = ["6010", "6020", "6030", "6110", "6120", "6130", "6310", "1010", "2110", "2115", "2120", "2130", "2135", "2140", "2145", "2150"]
    rows_out = []
    for a in order:
        v = d["je"][a]
        rows_out.append([a, NAMES[a], f"{v:.2f}" if v > 0 else "", f"{-v:.2f}" if v < 0 else ""])
    write_csv(os.path.join(ref, "payroll_je.csv"), header_out, rows_out)
    write_csv(os.path.join(sol, "payroll_je.csv"), header_out, rows_out)
    write_json(os.path.join(ref, "je.json"), {"net_by_account": d["je"], "total_debits": c(sum(v for v in d["je"].values() if v > 0)), "register_totals": T})
    write_task_yaml(HERE, {
        "id": "payroll-journal-entry", "track": "desk", "category": "bookkeeping",
        "title": "Journal entry for the 4 September payroll",
        "ask": ("Grace needs the journal entry for today's payroll so she can import it. The register and our chart of accounts are "
                "in the folder, and her email explains how she books it. Save it as payroll_je.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the company's own Social Security, Medicare, FUTA, SUI, 401(k) match and medical contribution are in a second block "
            "below the employee totals; reading only the employee table gives an entry that still balances but leaves out "
            f"{sum(d['je'][a] for a in ('6110', '6120', '6130')):,.2f} of cost and the matching liabilities "
            "(checks: account amounts; debits equal credits)",
            "wages are expensed at gross; 401(k), medical premiums and the garnishment are credited to payables rather than netted "
            "out of the wage lines (check: account amounts)",
            "2115 carries both halves of Social Security and Medicare and 2140/2145 include the company's match and medical "
            "contribution; one person is past the Social Security wage base so that column is not 6.2% of gross "
            "(check: account amounts)",
            "reimbursements are paid inside net pay but sit outside gross earnings; they debit 6310, and adding them to wages or "
            "leaving them out unbalances the lines (checks: account amounts; debits equal credits)",
            f"{owner['first']}'s salary as owner belongs in 6030 officer compensation, though the register lists the owner in the office department "
            "(check: account amounts)",
            "the employee table ends in a Company totals row and the employer block has its own total; summing whole columns "
            "doubles every figure (checks: account amounts; debits equal credits)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "import columns", "path": "payroll_je.csv", "columns": header_out},
            {"type": "csv_set_equal", "name": "accounts used", "path": "payroll_je.csv", "column": "account_number", "ref": "payroll_je.csv",
             "normalize": ["digits"]},
            {"type": "csv_row_count", "name": "one line per account", "path": "payroll_je.csv", "equals_ref": "payroll_je.csv"},
            {"type": "custom", "name": "account amounts", "module": "check.py"},
            {"type": "custom", "name": "debits equal credits", "module": "check_balance.py"},
        ],
    })
    print(f"seed={seed}: gross {T['gross']} net {T['net']} JE {d['je']}")


def write_naive(d, out):
    """Employee table only: wages at gross into one office/field split by Dept code, withholdings and deductions credited,
    reimbursements left inside the wage lines, no employer block."""
    os.makedirs(out, exist_ok=True)
    emps, T = d["emps"], d["T"]
    je = {"6010": c(sum(e["gross"] + e["reimb"] for e in emps if e["dept"] == "FLD")), "6020": c(sum(e["gross"] + e["reimb"] for e in emps if e["dept"] == "OFC")),
          "1010": -T["net"], "2110": -T["fit"], "2115": -c(T["ss"] + T["medicare"]), "2120": -T["sit"], "2140": -T["k401"], "2145": -T["med"], "2150": -T["garn"]}
    rows = [[a, NAMES[a], f"{v:.2f}" if v > 0 else "", f"{-v:.2f}" if v < 0 else ""] for a, v in je.items()]
    write_csv(os.path.join(out, "payroll_je.csv"), ["account_number", "account_name", "debit", "credit"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
