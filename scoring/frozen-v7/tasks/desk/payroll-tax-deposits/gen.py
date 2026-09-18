#!/usr/bin/env python3
"""payroll-tax-deposits: federal 941 deposits (amount and due date) for a semiweekly depositor.

    python gen.py [--seed N] [--naive DIR]

Business: a commercial cleaning company whose payroll provider dropped tax filing, so the owner now schedules
the federal deposits in EFTPS herself. Regular runs are every other Friday; three off-cycle runs sit in a
separate workbook.

Traps (each caught by a check, see task.yaml):
  * a deposit is federal income tax plus employee AND employer Social Security and Medicare; state withholding,
    SUI and FUTA sit in the same register and are not part of it                  (check: deposit amounts)
  * the register prints a TOTAL line per check date that repeats the run's sums     (check: deposit amounts)
  * the due date follows the check date's weekday, not the pay period end           (check: due dates)
  * a bank holiday in the three weekdays after the period adds a business day; the office closures listed in
    the same file do not                                                            (check: due dates)
  * the 31 Dec off-cycle run shares a semiweekly period with the 2 Jan run but not a quarter: two deposits due
    the same day; the 26 Mar off-cycle run shares both with 27 Mar: one deposit       (checks: grouping; row count)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

REGULAR = [date(2025, 12, 5), date(2025, 12, 19), date(2026, 1, 2), date(2026, 1, 16), date(2026, 1, 30),
           date(2026, 2, 13), date(2026, 2, 27), date(2026, 3, 13), date(2026, 3, 27)]
OFFCYCLE = [(date(2025, 12, 23), "Holiday bonus"), (date(2025, 12, 31), "Final pay and PTO payout"),
            (date(2026, 3, 26), "Q1 quality incentive")]
FED_HOLIDAYS = [date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 5, 26), date(2025, 6, 19),
                date(2025, 7, 4), date(2025, 9, 1), date(2025, 10, 13), date(2025, 11, 11), date(2025, 11, 27),
                date(2025, 12, 25), date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 5, 25),
                date(2026, 6, 19), date(2026, 7, 4), date(2026, 9, 7), date(2026, 10, 12), date(2026, 11, 11),
                date(2026, 11, 26), date(2026, 12, 25)]
OFFICE_CLOSED = [(date(2025, 12, 24), "closes at noon"), (date(2025, 12, 26), "closed"),
                 (date(2026, 1, 20), "closed for staff safety training"), (date(2026, 3, 16), "closed for the office move")]
HOL = set(FED_HOLIDAYS)


def quarter(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def add_business_day(d: date, hol: set) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5 or d in hol:
        d += timedelta(days=1)
    return d


def period_and_due(check_date: date, hol: set) -> tuple[date, date]:
    wd = check_date.weekday()
    if wd in (2, 3, 4):
        period_end = check_date + timedelta(days=4 - wd)          # Wednesday-Friday period closes Friday
    else:
        period_end = check_date + timedelta(days=(1 - wd) % 7)    # Saturday-Tuesday period closes Tuesday
    days, d = [], period_end
    while len(days) < 3:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days.append(d)
    due = days[-1]
    for _ in range(sum(1 for x in days if x in hol)):
        due = add_business_day(due, hol)
    return period_end, due


def build(seed: int) -> dict:
    r = rng(seed)
    staff = []
    for i, (f, l) in enumerate(people(r, 22)):
        staff.append({"name": f"{f} {l}", "id": f"E{110 + i * 7}", "rate": round(r.uniform(17.5, 31.0), 2),
                      "manager": i < 3, "state_rate": 0.044, "fit_pct": r.uniform(0.055, 0.13)})
    for s in staff[:3]:
        s["rate"] = round(r.uniform(34.0, 46.0), 2)

    def line(s, gross, supplemental=False, ytd_futa=0.0):
        fit = round(gross * (0.22 if supplemental else s["fit_pct"]), 2)
        ss = round(gross * 0.062, 2)
        med = round(gross * 0.0145, 2)
        state = round(gross * s["state_rate"], 2)
        futa_wages = max(0.0, min(gross, 7000.0 - ytd_futa))
        futa = round(futa_wages * 0.006, 2)
        sui = round(gross * 0.017, 2)
        return {"emp": s, "gross": round(gross, 2), "fit": fit, "ss": ss, "med": med, "state": state,
                "er_ss": ss, "er_med": med, "futa": futa, "sui": sui,
                "net": round(gross - fit - ss - med - state, 2)}

    runs = []
    ytd = {}
    for cd in sorted(REGULAR + [d for d, _ in OFFCYCLE]):
        off = next((reason for d, reason in OFFCYCLE if d == cd), None)
        lines = []
        if off is None:
            for s in staff:
                if r.random() < 0.1 and not s["manager"]:
                    continue
                hours = 80.0 if s["manager"] else round(r.uniform(38, 84) * 4) / 4
                gross = s["rate"] * hours
                key = (s["id"], cd.year)
                if key not in ytd:
                    ytd[key] = 0.0 if cd.year == 2026 else (7000.0 if r.random() < 0.8 else round(r.uniform(2500, 6500), 2))
                base = ytd[key]
                ln = line(s, gross, ytd_futa=base)
                ytd[key] = base + ln["gross"]
                lines.append(ln)
        else:
            if off == "Holiday bonus":
                who = staff
                amounts = [150.0 if not s["manager"] else 600.0 for s in who]
            elif off == "Final pay and PTO payout":
                who = [staff[1], staff[7], staff[12]]
                amounts = [round(r.uniform(3100, 4200), 2), round(r.uniform(900, 1400), 2), round(r.uniform(500, 900), 2)]
            else:
                who = r.sample(staff, 9)
                amounts = [float(r.choice([250, 300, 400, 500])) for _ in who]
            for s, a in zip(who, amounts):
                key = (s["id"], cd.year)
                base = ytd.get(key, 7000.0 if cd.year == 2025 else 0.0)
                ln = line(s, a, supplemental=True, ytd_futa=base)
                ytd[key] = base + ln["gross"]
                lines.append(ln)
        runs.append({"check_date": cd, "offcycle": off, "lines": lines})

    groups = {}
    for run in runs:
        pend, due = period_and_due(run["check_date"], HOL)
        k = (pend, quarter(run["check_date"]))
        g = groups.setdefault(k, {"period_end": pend, "quarter": k[1], "due": due, "runs": [], "amount": 0.0})
        g["runs"].append(run)
    for g in groups.values():
        g["amount"] = round(sum(ln["fit"] + ln["ss"] + ln["med"] + ln["er_ss"] + ln["er_med"]
                                for run in g["runs"] for ln in run["lines"]), 2)
    deposits = sorted(groups.values(), key=lambda g: (g["due"], g["quarter"]))
    return {"staff": staff, "runs": runs, "deposits": deposits}


def iso(d: date) -> str:
    return d.isoformat()


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)

    # ---- workspace: regular register (csv), off-cycle workbook, CPA thread, holiday list ----
    hdr = ["Check Date", "Period Start", "Period End", "Employee", "Emp ID", "Gross Pay", "Federal Income Tax",
           "Social Security", "Medicare", "State Income Tax", "Net Pay", "ER Social Security", "ER Medicare",
           "ER FUTA", "ER SUI"]
    rows = []
    fields = ["gross", "fit", "ss", "med", "state", "net", "er_ss", "er_med", "futa", "sui"]
    for run in d["runs"]:
        if run["offcycle"]:
            continue
        cd = run["check_date"]
        pend = cd - timedelta(days=5)
        pstart = pend - timedelta(days=13)
        for ln in sorted(run["lines"], key=lambda x: x["emp"]["name"].split()[-1]):
            rows.append([cd.strftime("%m/%d/%Y"), pstart.strftime("%m/%d/%Y"), pend.strftime("%m/%d/%Y"),
                         ln["emp"]["name"], ln["emp"]["id"]] + [money_str(ln[f], 1) for f in fields])
        tot = [round(sum(ln[f] for ln in run["lines"]), 2) for f in fields]
        rows.append([cd.strftime("%m/%d/%Y"), "", "", "TOTAL FOR CHECK DATE", ""] + [money_str(t, 1) for t in tot])
    write_csv(os.path.join(ws, "tallyrun_payroll_register_2025-12-01_to_2026-03-31.csv"), hdr, rows,
              preamble=["Tallyrun Payroll Register - Sable Creek Commercial Cleaning LLC",
                        "Regular payrolls, check dates 12/01/2025 - 03/31/2026"], bom=True, crlf=True)

    orows = []
    for run in d["runs"]:
        if not run["offcycle"]:
            continue
        for ln in run["lines"]:
            orows.append([run["check_date"], run["offcycle"], ln["emp"]["name"], ln["gross"], ln["fit"], ln["ss"],
                          ln["med"], ln["state"], ln["er_ss"], ln["er_med"], ln["futa"], ln["sui"]])
    write_xlsx(os.path.join(ws, "tallyrun_offcycle_payrolls.xlsx"), {"Off-cycle": {
        "merged_title": "Off-cycle payroll detail - Sable Creek Commercial Cleaning LLC",
        "preamble": [["Supplemental wages, flat-rate federal withholding"]],
        "header": ["Pay Date", "Run Type", "Employee", "Gross Wages", "Federal W/H", "Soc Sec W/H", "Medicare W/H",
                   "State W/H", "Employer Soc Sec", "Employer Medicare", "FUTA", "SUI"],
        "rows": orows, "number_formats": {c: "#,##0.00" for c in "DEFGHIJKL"},
        "widths": {"A": 12, "B": 24, "C": 22}}}, creator="Tallyrun")

    hol_lines = ["Federal Reserve bank holidays (banks closed)", ""]
    for h in FED_HOLIDAYS:
        hol_lines.append(f"{h.strftime('%a %m/%d/%Y')}")
    hol_lines += ["", "Sable Creek office calendar (staff only, banks open)", ""]
    for h, what in OFFICE_CLOSED:
        hol_lines.append(f"{h.strftime('%a %m/%d/%Y')}  office {what}")
    write_text(os.path.join(ws, "holidays_2025-2026.txt"), "\n".join(hol_lines) + "\n")

    write_email_thread(os.path.join(ws, "email_thread_walter_cpa.txt"), [
        {"from": "Nadia Brooks <nadia@sablecreekcleaning.com>", "to": "Walter Lindgren <walter@lindgrenosei.cpa>",
         "date": "Mon, 6 Apr 2026 08:02", "subject": "federal deposits now that Tallyrun dropped tax service",
         "body": ("Walter, Tallyrun confirmed they stopped depositing our federal payroll taxes with the December payrolls, "
                  "so nothing has gone to EFTPS for any check date from December 5 on. I have the regular register and the "
                  "off-cycle sheet they sent. How do I work out what we owe and when each one was due?")},
        {"from": "Walter Lindgren <walter@lindgrenosei.cpa>", "to": "Nadia Brooks <nadia@sablecreekcleaning.com>",
         "date": "Mon, 6 Apr 2026 11:37", "subject": "RE: federal deposits now that Tallyrun dropped tax service",
         "body": ("Nadia, you are a semiweekly depositor, so here is how it works.\n\n"
                  "What goes in a deposit: the federal income tax you withheld, plus Social Security and Medicare - both "
                  "the employees' share that came out of their checks and your matching employer share. State income tax, "
                  "state unemployment (SUI) and FUTA are NOT part of it; FUTA is its own quarterly deposit and the state "
                  "taxes are paid on the state site.\n\n"
                  "When it is due goes by the check date, not the pay period. Checks dated Wednesday, Thursday or Friday "
                  "are due the following Wednesday. Checks dated Saturday, Sunday, Monday or Tuesday are due the following "
                  "Friday. In other words the Wednesday-Friday period and the Saturday-Tuesday period each get three "
                  "business days after the period closes.\n\n"
                  "Holidays: if any of those three weekdays after the period closes is a bank holiday, you get one extra "
                  "business day for each holiday. Use the Federal Reserve list in the holiday file - the days your own "
                  "office is closed do not count, the banks are open.\n\n"
                  "Off-cycle runs (bonuses, final checks) are payrolls like any other. If two check dates fall in the same "
                  "Wednesday-Friday or Saturday-Tuesday period they go in as one deposit, EXCEPT when the check dates are in "
                  "different quarters: then it is two deposits, one for each quarter's 941, even though they are due on the "
                  "same day.")},
        {"from": "Walter Lindgren <walter@lindgrenosei.cpa>", "to": "Nadia Brooks <nadia@sablecreekcleaning.com>",
         "date": "Mon, 6 Apr 2026 11:52", "subject": "RE: federal deposits now that Tallyrun dropped tax service",
         "body": ("One more thing - send me the list before you pay anything so I can work out the late-deposit penalty. "
                  "One line per deposit with the due date, the amount, which quarter's 941 it belongs to and the check "
                  "dates it covers.")},
    ])

    # ---- reference and solution ----
    header = ["due_date", "quarter", "amount", "check_dates"]
    out = [[iso(g["due"]), g["quarter"], f"{g['amount']:.2f}", "; ".join(iso(x["check_date"]) for x in g["runs"])]
           for g in d["deposits"]]
    write_csv(os.path.join(ref, "deposits.csv"), header, out)
    write_csv(os.path.join(sol, "deposits.csv"), header, out)
    write_json(os.path.join(ref, "deposits.json"), [
        {"due_date": iso(g["due"]), "quarter": g["quarter"], "amount": g["amount"],
         "check_dates": [iso(x["check_date"]) for x in g["runs"]], "period_end": iso(g["period_end"])} for g in d["deposits"]])

    by_cd = {tuple(iso(x["check_date"]) for x in g["runs"]): g for g in d["deposits"]}
    jan16 = by_cd[("2026-01-16",)]; dec23 = by_cd[("2025-12-23",)]; mar = by_cd[("2026-03-26", "2026-03-27")]
    write_task_yaml(HERE, {
        "id": "payroll-tax-deposits", "track": "desk", "category": "bookkeeping",
        "title": "Federal payroll tax deposits and due dates since the provider stopped",
        "ask": ("Tallyrun stopped making our federal payroll tax deposits, so I have to catch up in EFTPS myself. Work out "
                "every deposit for the payroll runs in the folder the way Walter's email explains and save it as deposits.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the register carries state income tax, SUI and FUTA beside the federal columns, and the off-cycle sheet the "
            "employer Social Security and Medicare match; a deposit is federal income tax plus both halves of Social "
            "Security and Medicare only, so summing every tax column or leaving out the employer match is wrong "
            "(check: deposit amounts)",
            "every check date in the register ends with a TOTAL FOR CHECK DATE line that repeats the run's sums, so "
            "grouping the rows by check date doubles each regular deposit (check: deposit amounts)",
            "due dates follow the check date's weekday (Wednesday to Friday due the next Wednesday, Saturday to Tuesday "
            "the next Friday); the register's Period End column is a Sunday and using it moves every regular deposit "
            "(check: due dates)",
            f"a bank holiday among the three weekdays after the period adds a business day: the 16 Jan run is due "
            f"{jan16['due'].strftime('%d %b')}, not 21 Jan (Martin Luther King Day), the 13 Feb run 19 Feb, and the 23 Dec "
            f"off-cycle run {dec23['due'].strftime('%d %b')} (Christmas); the office closures listed in the same file "
            "(20 Jan, 16 Mar, 26 Dec) are not bank holidays (check: due dates)",
            "the off-cycle runs are in a separate workbook with different column names: the 31 Dec final-pay run shares "
            "the Wednesday-Friday period with the 2 Jan run but not the quarter, so it is a separate Q4 deposit due the "
            f"same 7 Jan; the 26 Mar incentive run shares both period and quarter with 27 Mar and goes in one "
            f"{mar['amount']:,.2f} deposit (checks: deposits grouped by period and quarter; one line per deposit)",
            "the register is '$1,234.56' text under a two-line preamble with a BOM and CRLF endings, dates are "
            "MM/DD/YYYY (check: deposit amounts)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "deposit list columns", "path": "deposits.csv",
             "columns": ["due_date", "quarter", "amount", "check_dates"]},
            {"type": "csv_row_count", "name": "one line per deposit", "path": "deposits.csv", "equals_ref": "deposits.csv"},
            {"type": "custom", "name": "deposits grouped by period and quarter", "module": "check.py"},
            {"type": "custom", "name": "due dates", "module": "check_due.py"},
            {"type": "custom", "name": "deposit amounts", "module": "check_amounts.py"},
        ],
    })
    print(f"seed={seed} runs={len(d['runs'])} deposits={len(d['deposits'])}")
    for g in d["deposits"]:
        print(" ", iso(g["due"]), g["quarter"], f"{g['amount']:>10.2f}", [iso(x["check_date"]) for x in g["runs"]])


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: one deposit per check date, every tax column summed (TOTAL lines included via the
    register's own totals), due five days after the check date's semiweekly weekday rule with no holiday handling."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for run in d["runs"]:
        cd = run["check_date"]
        amt = sum(ln["fit"] + ln["ss"] + ln["med"] + ln["state"] + ln["er_ss"] + ln["er_med"] + ln["futa"] + ln["sui"]
                  for ln in run["lines"])
        _, due = period_and_due(cd, set())
        rows.append([iso(due), quarter(cd), f"{amt:.2f}", iso(cd)])
    write_csv(os.path.join(out, "deposits.csv"), ["due_date", "quarter", "amount", "check_dates"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
