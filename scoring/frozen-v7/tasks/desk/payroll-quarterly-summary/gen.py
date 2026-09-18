#!/usr/bin/env python3
"""payroll-quarterly-summary: a year of payroll runs -> gross, taxes withheld and net per quarter.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * quarters go by check date, not pay-period end; two biweekly runs straddle a quarter boundary   (checks: Q1 gross; Q4 gross)
  * off-cycle runs (a termination check, a missed-hours run, the December bonus run) live in a
    separate xlsx export and count in the quarter they were paid                                    (checks: Q2 gross; Q3 net; Q4 net)
  * three corrections appear as a full reversal row (negative, in parentheses) plus a reissue row;
    they net, they are not dropped or abs()ed                                                       (checks: Q1 gross; Q3 net)
  * the register carries employer-side Social Security and Medicare columns; taxes withheld are the
    employee columns only                                                                            (check: Q2 taxes withheld)
  * register amounts are "$1,234.56" text, negatives "($123.45)"                                    (every value check)
"""
from __future__ import annotations
import os, sys
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


FIRST_CHECK = date(2025, 1, 10)                       # biweekly Fridays; period ends the Saturday 6 days before
N_RUNS = 26
ROLES = [("Head baker", 2900, 3400), ("Baker", 2000, 2500), ("Pastry cook", 1900, 2300), ("Counter lead", 1700, 2000),
         ("Counter", 1250, 1650), ("Delivery driver", 1500, 1900), ("Office manager", 2400, 2700), ("Dishwasher", 1150, 1400)]
Q = lambda d: (d.month - 1) // 3 + 1


def paycheck(r, emp, gross):
    fed = round(gross * emp["fed_rate"], 2); st = round(gross * emp["state_rate"], 2)
    ss = round(gross * 0.062, 2); med = round(gross * 0.0145, 2)
    k = round(gross * emp["k401"], 2); health = emp["health"]
    net = round(gross - fed - st - ss - med - k - health, 2)
    return {"gross": gross, "fed": fed, "state": st, "ss": ss, "med": med, "er_ss": ss, "er_med": med, "k401": k, "health": health, "net": net}


def build(seed: int) -> dict:
    r = rng(seed)
    emps = []
    for i, (f, l) in enumerate(people(r, 14)):
        role, lo, hi = ROLES[i % len(ROLES)]
        emps.append({"id": f"E{101 + i}", "name": f"{f} {l}", "role": role, "base": r.randrange(lo, hi, 5),
                     "fed_rate": r.choice([0.08, 0.10, 0.12, 0.14, 0.16]), "state_rate": r.choice([0.04, 0.045, 0.05, 0.055]),
                     "k401": r.choice([0, 0, 0.03, 0.04, 0.05, 0.06]), "health": r.choice([0, 85.0, 85.0, 140.0])})
    term = emps[9]; term_last_regular = date(2025, 5, 2)
    runs = []       # every payroll row in truth: dict(check_date, period_end, run_type, source, emp, amounts)
    for k in range(N_RUNS):
        cd = FIRST_CHECK + timedelta(days=14 * k); pe = cd - timedelta(days=6)
        for e in emps:
            if e is term and cd > term_last_regular: continue
            gross = round(e["base"] + r.choice([0, 0, 0, 40, 80, 120, -60, 160]) + r.randint(0, 99) / 100, 2)
            runs.append({"check_date": cd, "period_end": pe, "run_type": "Regular", "source": "register", "emp": e, **paycheck(r, e, gross)})
    # corrections: reverse an earlier check in full on a later run, reissue with a higher gross (missed overtime)
    corrections = []
    for (run_idx, emp_idx) in [(3, 2), (5, 7), (16, 4)]:
        orig = next(x for x in runs if x["emp"] is emps[emp_idx] and x["check_date"] == FIRST_CHECK + timedelta(days=14 * (run_idx - 1)))
        cd = FIRST_CHECK + timedelta(days=14 * run_idx)
        rev = {**orig, "check_date": cd, "run_type": "Correction", "source": "register"}
        for f in ("gross", "fed", "state", "ss", "med", "er_ss", "er_med", "k401", "health", "net"):
            rev[f] = round(-orig[f], 2)
        reissue = {"check_date": cd, "period_end": orig["period_end"], "run_type": "Correction", "source": "register", "emp": orig["emp"],
                   **paycheck(r, orig["emp"], round(orig["gross"] + r.choice([310.0, 420.0, 505.0]), 2))}
        corrections += [rev, reissue]
    runs += corrections
    # off-cycle runs, exported separately
    off = []
    off.append({"check_date": date(2025, 5, 9), "period_end": date(2025, 5, 3), "run_type": "Off-cycle: final pay", "source": "offcycle", "emp": term,
                **paycheck(r, term, round(term["base"] * 1.6 + r.randint(0, 99) / 100, 2))})
    for e in (emps[1], emps[6]):
        off.append({"check_date": date(2025, 8, 14), "period_end": date(2025, 8, 9), "run_type": "Off-cycle: missed hours", "source": "offcycle", "emp": e,
                    **paycheck(r, e, round(r.randrange(380, 720, 5) + r.randint(0, 99) / 100, 2))})
    for e in emps:
        if e is term: continue
        off.append({"check_date": date(2025, 12, 19), "period_end": date(2025, 12, 13), "run_type": "Off-cycle: bonus", "source": "offcycle", "emp": e,
                    **paycheck(r, e, float(r.randrange(600, 2600, 50)))})
    runs += off
    runs.sort(key=lambda x: (x["check_date"], x["source"], x["emp"]["id"], x["gross"]))

    def agg(rows, qf, gross_f=lambda x: x["gross"], tax_f=lambda x: x["fed"] + x["state"] + x["ss"] + x["med"]):
        out = {q: {"gross": 0.0, "taxes": 0.0, "net": 0.0, "fed": 0.0, "state": 0.0, "ss": 0.0, "med": 0.0, "k401": 0.0, "health": 0.0} for q in (1, 2, 3, 4)}
        for x in rows:
            q = qf(x); o = out[q]
            o["gross"] += gross_f(x); o["taxes"] += tax_f(x); o["net"] += x["net"]
            for f in ("fed", "state", "ss", "med", "k401", "health"): o[f] += x[f]
        return {q: {k: round(v, 2) for k, v in o.items()} for q, o in out.items()}
    truth = agg(runs, lambda x: Q(x["check_date"]))
    naive = {
        "by_period": agg(runs, lambda x: Q(x["period_end"])),
        "no_offcycle": agg([x for x in runs if x["source"] == "register"], lambda x: Q(x["check_date"])),
        "drop_negatives": agg([x for x in runs if x["gross"] > 0], lambda x: Q(x["check_date"])),
        "abs_negatives": agg(runs, lambda x: Q(x["check_date"]), gross_f=lambda x: abs(x["gross"])),
        "with_er_taxes": agg(runs, lambda x: Q(x["check_date"]), tax_f=lambda x: x["fed"] + x["state"] + x["ss"] + x["med"] + x["er_ss"] + x["er_med"]),
    }
    return {"emps": emps, "runs": runs, "truth": truth, "naive": naive, "term": term, "corrections": corrections, "off": off}


CHECKED = [(1, "gross"), (2, "gross"), (2, "taxes"), (3, "net"), (4, "gross"), (4, "net")]


def acceptable(d: dict) -> bool:
    t = d["truth"]
    for q, f in CHECKED:
        v = t[q][f]
        # no other figure on the same summary row within 1%
        others = [t[q][g] for g in ("gross", "taxes", "net", "fed", "state", "ss", "med", "k401", "health") if g != f]
        if any(abs(o - v) <= 0.01 * v for o in others): return False
    # every naive variant must be caught by at least one checked figure by more than 1%
    for name, var in d["naive"].items():
        if not any(abs(var[q][f] - t[q][f]) > 0.01 * t[q][f] for q, f in CHECKED): return False
    return True


def emit(seed: int) -> None:
    for attempt in range(100):
        d = build(seed * 1000 + attempt)
        if acceptable(d): break
    else:
        raise SystemExit("no acceptable draw")
    ws, ref, sol = task_dirs(HERE)
    reg = [x for x in d["runs"] if x["source"] == "register"]
    write_csv(os.path.join(ws, "payroll_register_2025.csv"),
              ["Check Date", "Pay Period Start", "Pay Period End", "Run Type", "Employee ID", "Employee", "Gross Pay", "Federal W/H", "State W/H",
               "Social Security EE", "Medicare EE", "Social Security ER", "Medicare ER", "401(k) EE", "Health Ins", "Net Pay"],
              [[date_variant(x["check_date"], 1), date_variant(x["period_end"] - timedelta(days=13), 1), date_variant(x["period_end"], 1), x["run_type"],
                x["emp"]["id"], x["emp"]["name"], money_str(x["gross"], 1), money_str(x["fed"], 1), money_str(x["state"], 1), money_str(x["ss"], 1),
                money_str(x["med"], 1), money_str(x["er_ss"], 1), money_str(x["er_med"], 1), money_str(x["k401"], 1), money_str(x["health"], 1),
                money_str(x["net"], 1)] for x in reg],
              preamble=["Payroll Register - Ellington Bakeries - 01/01/2025 to 12/31/2025", ""], crlf=True)
    write_xlsx(os.path.join(ws, "offcycle_runs_2025.xlsx"), {"Off-cycle": {
        "merged_title": "Off-cycle payroll runs - 2025", "preamble": [["Company: Ellington Bakeries", "", "", "", "", "", "", "", "", "", "", "Exported 01/06/2026"]],
        "header": ["Pay Date", "Run", "Emp #", "Name", "Gross", "Fed Tax", "State Tax", "Soc Sec", "Medicare", "401(k)", "Medical", "Net"],
        "rows": [[x["check_date"], x["run_type"].replace("Off-cycle: ", "").title(), x["emp"]["id"], x["emp"]["name"], x["gross"], x["fed"], x["state"],
                  x["ss"], x["med"], x["k401"], x["health"], x["net"]] for x in d["off"]],
        "number_formats": {c: "#,##0.00" for c in "EFGHIJKL"}, "widths": {"A": 12, "B": 14, "D": 24}}}, creator="PayrollPro")
    write_text(os.path.join(ws, "note_from_accountant.txt"),
               "Hi,\n\nFor the 941 reconciliation I need 2025 payroll by quarter: gross wages, total taxes withheld from employees "
               "(federal, state, Social Security and Medicare - the employee side only, not the company match), and net pay. "
               "Quarters go by check date, not by the pay period the check covers, because that is how the deposits were made.\n\n"
               "PayrollPro exports off-cycle runs separately from the regular register; those count in the quarter they were paid, same as everything else.\n\n"
               "Thanks,\nDeborah\n")
    t = d["truth"]
    write_csv(os.path.join(ref, "quarters.csv"), ["quarter", "gross", "federal", "state", "social_security", "medicare", "taxes_withheld", "k401", "health", "net"],
              [[f"Q{q}", f"{t[q]['gross']:.2f}", f"{t[q]['fed']:.2f}", f"{t[q]['state']:.2f}", f"{t[q]['ss']:.2f}", f"{t[q]['med']:.2f}", f"{t[q]['taxes']:.2f}",
                f"{t[q]['k401']:.2f}", f"{t[q]['health']:.2f}", f"{t[q]['net']:.2f}"] for q in (1, 2, 3, 4)])
    write_json(os.path.join(ref, "notes.json"), {"naive": d["naive"], "terminated_employee": d["term"]["name"],
                                                  "correction_rows": len(d["corrections"]), "offcycle_rows": len(d["off"])})
    # ---- reference solution
    run_rows = [[x["check_date"], f"Q{Q(x['check_date'])}", x["period_end"], x["run_type"], x["source"], x["emp"]["id"], x["emp"]["name"],
                 x["gross"], x["fed"], x["state"], x["ss"], x["med"], round(x["fed"] + x["state"] + x["ss"] + x["med"], 2), x["k401"], x["health"], x["net"]]
                for x in d["runs"]]
    n = len(run_rows) + 1
    def sumif(col, i): return f"=SUMIF(Runs!$B$2:$B${n},A{i},Runs!${col}$2:${col}${n})"
    summ = [[f"Q{q}", sumif("H", i), sumif("I", i), sumif("J", i), sumif("K", i), sumif("L", i), f"=SUM(C{i}:F{i})", sumif("N", i), sumif("O", i), sumif("P", i)]
            for i, q in enumerate((1, 2, 3, 4), start=2)]
    summ.append(["Total 2025"] + [f"=SUM({c}2:{c}5)" for c in "BCDEFGHIJ"])
    summ.append([])
    summ.append(["Quarters by check date. Off-cycle runs included. Corrections (reversal + reissue) netted. Taxes withheld = employee federal, state, Social Security, Medicare."])
    write_xlsx(os.path.join(sol, "payroll_q.xlsx"), {
        "Summary": {"header": ["Quarter", "Gross wages", "Federal W/H", "State W/H", "Social Security EE", "Medicare EE", "Taxes withheld", "401(k)", "Health", "Net pay"],
                    "rows": summ, "number_formats": {c: "#,##0.00" for c in "BCDEFGHIJ"}, "widths": {"A": 12, "B": 14, "G": 15, "J": 14}},
        "Runs": {"header": ["check_date", "quarter", "period_end", "run_type", "source", "employee_id", "employee", "gross", "federal", "state", "social_security",
                            "medicare", "taxes_withheld", "k401", "health", "net"], "rows": run_rows, "widths": {"A": 12, "C": 12, "D": 24, "G": 22}},
    }, creator="reference")
    write_task_yaml(HERE, {
        "id": "payroll-quarterly-summary", "track": "desk", "category": "reports",
        "title": "2025 payroll by quarter for the accountant",
        "ask": ("Deborah needs our 2025 payroll summarized by quarter: gross wages, taxes withheld and net pay. Both payroll exports are in the folder and "
                "her note says how she wants it counted. Save it as payroll_q.xlsx with live formulas so she can trace the totals.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "quarters go by check date (the note); the 04/04 and 10/03 runs cover pay periods ending in the prior quarter (checks: Q1 gross; Q4 gross)",
            f"{len(d['off'])} off-cycle rows (final pay in May, missed hours in August, the December bonus run) are in a separate xlsx with different column names and a merged title; they count (checks: Q2 gross; Q3 net; Q4 net)",
            "three corrections appear as a full reversal row in parentheses plus a reissue row on a later check date; net them, do not drop or abs the negatives (checks: Q1 gross; Q3 net)",
            "the register has employer-side Social Security and Medicare columns; taxes withheld are the employee columns only (check: Q2 taxes withheld)",
            'register amounts are "$1,234.56" text with "($1,234.56)" negatives, dates are MM/DD/YYYY, and the csv has a two-line preamble (check: Q1 gross)',
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "payroll_q.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no formula errors", "path": "payroll_q.xlsx"},
            {"type": "xlsx_value_present", "name": "Q1 gross", "path": "payroll_q.xlsx", "expected": t[1]["gross"], "rel_tol": cent_tol(t[1]["gross"], 0.005), "near_text": "q1"},
            {"type": "xlsx_value_present", "name": "Q2 gross", "path": "payroll_q.xlsx", "expected": t[2]["gross"], "rel_tol": cent_tol(t[2]["gross"], 0.005), "near_text": "q2"},
            {"type": "xlsx_value_present", "name": "Q2 taxes withheld", "path": "payroll_q.xlsx", "expected": t[2]["taxes"], "rel_tol": cent_tol(t[2]["taxes"], 0.005), "near_text": "q2"},
            {"type": "xlsx_value_present", "name": "Q3 net", "path": "payroll_q.xlsx", "expected": t[3]["net"], "rel_tol": cent_tol(t[3]["net"], 0.005), "near_text": "q3"},
            {"type": "xlsx_value_present", "name": "Q4 gross", "path": "payroll_q.xlsx", "expected": t[4]["gross"], "rel_tol": cent_tol(t[4]["gross"], 0.005), "near_text": "q4"},
            {"type": "xlsx_value_present", "name": "Q4 net", "path": "payroll_q.xlsx", "expected": t[4]["net"], "rel_tol": cent_tol(t[4]["net"], 0.005), "near_text": "q4"},
            {"type": "xlsx_value_present", "name": "year gross", "path": "payroll_q.xlsx", "expected": round(sum(t[q]["gross"] for q in t), 2), "rel_tol": cent_tol(round(sum(t[q]["gross"] for q in t), 2), 0.005), "near_text": "total"},
        ],
    })
    print(f"seed={seed} attempt={attempt} rows={len(d['runs'])} truth={{{', '.join(f'Q{q}: g={t[q]['gross']} t={t[q]['taxes']} n={t[q]['net']}' for q in t)}}}")


if __name__ == "__main__":
    emit(argparse_seed())
