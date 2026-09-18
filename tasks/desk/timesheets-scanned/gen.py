#!/usr/bin/env python3
"""timesheets-scanned: phone-scanned weekly caregiver timesheets to hours per person per day.

    python gen.py [--seed N]

Business: a home care agency. Caregivers fill in paper time sheets on three different forms; the office
scans them and payroll wants one line per caregiver per day worked in the two-week pay period.

Traps (each caught by a check, see task.yaml):
  * the old form ends with a TOTAL row, and the visit log prints a DAY TOTAL line under each day's visits;
    reading those as hours double counts or adds a phantom day              (checks: hours per day; one row per person per day)
  * one sheet has no supervisor signature: every row from it is sheet_signed = no (check: signature flag)
  * the visit log has two or three visits on some days that add into one row  (checks: hours per day; row count)
  * the new form prints start, end and unpaid break but no hours              (check: hours per day)
  * the new form lists weekdays only (Sunday first); dates come from the week-ending Saturday (check: one row per person per day)
  * an overnight visit 22:00-06:00 counts on the day it started                (checks: hours per day; one row per person per day)
  * last pay period's sheet is in the folder and must not produce rows         (checks: one row per person per day; row count)
  * every sheet is an image-only scan                                          (check: hours per day)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

AGENCY = "HEARTHSTONE HOME CARE"
P_START = date(2026, 8, 30)   # Sunday
P_END = date(2026, 9, 12)     # Saturday
W1_END, W2_END = date(2026, 9, 5), date(2026, 9, 12)
OLD_END = date(2026, 8, 29)
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DOW_LONG = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CLIENTS = ["M. Alvarez", "R. Kim", "J. Brooks", "S. Patel", "D. Osei", "L. Reyes", "T. Nguyen", "E. Walker"]


def hm(m: int) -> str:
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, 5)
    ids = r.sample(range(101, 199), 3)
    A = dict(id=f"HC-{ids[0]}", name=f"{names[0][0]} {names[0][1]}", layout="A")
    B = dict(id=f"HC-{ids[1]}", name=f"{names[1][0]} {names[1][1]}", layout="B")
    Cg = dict(id=f"HC-{ids[2]}", name=f"{names[2][0]} {names[2][1]}", layout="C")
    sup = f"{names[3][0]} {names[3][1]}"

    def shift(lo_start=420, hi_start=540, lo_len=360, hi_len=570):
        s = r.randrange(lo_start, hi_start + 1, 15); ln = r.randrange(lo_len, hi_len + 1, 15)
        brk = r.choice([30, 45]) if ln > 360 else 0
        return dict(start=s, end=s + ln, brk=brk, hours=(ln - brk) / 60)

    # A: old form, dates printed, hours column, TOTAL row. Mon-Fri week 1, Mon-Sat week 2; plus last period's sheet.
    A["weeks"] = {}
    for wend, days in ((OLD_END, [1, 2, 3, 4, 5]), (W1_END, [1, 2, 3, 4, 5]), (W2_END, [1, 2, 3, 4, 5, 6])):
        wstart = wend - timedelta(days=6)
        A["weeks"][wend] = {wstart + timedelta(days=i): shift() for i in days}
    # B: new form, weekdays only, no hours column; works the Sunday that opens week 1.
    B["weeks"] = {}
    for wend, days in ((W1_END, [0, 1, 3, 4, 6]), (W2_END, [1, 2, 4, 5])):
        wstart = wend - timedelta(days=6)
        B["weeks"][wend] = {wstart + timedelta(days=i): shift(360, 600, 240, 540) for i in days}
    # C: visit log; split days, an overnight visit on Thursday 09/10.
    C_weeks = {}
    for wend in (W1_END, W2_END):
        wstart = wend - timedelta(days=6)
        days = {}
        for i in [1, 2, 3, 4, 5]:
            dd = wstart + timedelta(days=i)
            if wend == W2_END and dd == date(2026, 9, 10):
                days[dd] = [dict(start=22 * 60, end=30 * 60, client=r.choice(CLIENTS))]
                continue
            if wend == W2_END and dd == date(2026, 9, 11):
                s = r.randrange(540, 600, 15); days[dd] = [dict(start=s, end=s + r.randrange(150, 211, 15), client=r.choice(CLIENTS))]
                continue
            nvis = 3 if (i == 2 and wend == W1_END) else (2 if i in (1, 4) else 1)
            t = r.randrange(420, 511, 15); vis = []
            for _ in range(nvis):
                ln = r.randrange(120, 241, 15)
                vis.append(dict(start=t, end=t + ln, client=r.choice(CLIENTS)))
                t = t + ln + r.randrange(45, 121, 15)
            days[dd] = vis
        C_weeks[wend] = days
    Cg["weeks"] = C_weeks
    return dict(A=A, B=B, C=Cg, sup=sup, gloria=("Gloria", r.choice(LAST)))


def emit(seed: int) -> None:
    d = build(seed); A, B, Cc, sup = d["A"], d["B"], d["C"], d["sup"]
    ws, ref, sol = task_dirs(HERE)
    S = os.path.join(ws, "scanned_timesheets"); os.makedirs(S, exist_ok=True)
    rows = []  # truth

    # ---- layout A (portrait, old form)
    for n, (wend, days) in enumerate(sorted(A["weeks"].items())):
        wstart = wend - timedelta(days=6)
        lines = [AGENCY, "WEEKLY TIME SHEET", "", f"Caregiver: {A['name']}", f"Employee #: {A['id']}", f"Week ending: {wend.strftime('%m/%d/%Y')}", "",
                 "DAY DATE IN OUT BREAK HOURS"]
        total = 0.0
        for i in range(7):
            dd = wstart + timedelta(days=i)
            if dd in days:
                s = days[dd]; total += s["hours"]
                lines.append(f"{DOW[dd.weekday()]} {dd.strftime('%m/%d')} {hm(s['start'])} {hm(s['end'])} {s['brk']} {s['hours']:.2f}")
                if P_START <= dd <= P_END:
                    rows.append((A, dd, s["hours"], "yes"))
            else:
                lines.append(f"{DOW[dd.weekday()]} {dd.strftime('%m/%d')} OFF")
        lines += [f"TOTAL {total:.2f}", "", f"Caregiver signature: /s/ {A['name']}", f"Supervisor signature: /s/ {sup}",
                  f"Date: {(wend + timedelta(days=2)).strftime('%m/%d/%Y')}"]
        fn = f"scan_{wend.strftime('%m%d')}_{A['name'].split()[1].lower()}.pdf"
        write_scan_pdf(os.path.join(S, fn), lines, font_size=34, seed=seed * 13 + n, skew_deg=[0.3, -0.35, 0.4][n], noise=300)

    # ---- layout B (landscape, new form, weekdays only, no hours)
    for n, (wend, days) in enumerate(sorted(B["weeks"].items())):
        wstart = wend - timedelta(days=6)
        signed = wend == W1_END
        lines = [f"Time Sheet - Hearthstone Home Care (form HC-7 rev 2026)", f"Name: {B['name']}   Emp ID: {B['id']}",
                 f"Pay week ending Saturday {wend.strftime('%m/%d/%Y')}", "", "Day: start to end, unpaid break"]
        for i in range(7):
            dd = wstart + timedelta(days=i)
            day = DOW_LONG[dd.weekday()]
            if dd in days:
                s = days[dd]
                lines.append(f"{day}: {hm(s['start'])} to {hm(s['end'])}, break {s['brk']} min")
                rows.append((B, dd, s["hours"], "yes" if signed else "no"))
            else:
                lines.append(f"{day}: off")
        total = sum(s["hours"] for s in days.values())
        lines += ["", f"Weekly total hours: {total:.2f}", "", f"Employee signature: /s/ {B['name']}",
                  f"Approved by (supervisor): {'/s/ ' + sup if signed else '______________________'}"]
        fn = f"IMG_{4410 + 7 * n + seed % 50}.pdf"
        write_scan_pdf(os.path.join(S, fn), lines, width=1754, height=1240, font_size=34, seed=seed * 17 + n, skew_deg=[-0.3, 0.35][n], noise=250)

    # ---- layout C (portrait, visit log with day totals)
    for n, (wend, days) in enumerate(sorted(Cc["weeks"].items())):
        lines = ["CAREGIVER VISIT LOG", f"{Cc['id']} {Cc['name']}", f"Week ending {wend.strftime('%m/%d/%Y')}", "", "DATE TIME CLIENT HRS"]
        wk = 0.0
        for dd in sorted(days):
            vis = days[dd]; dt = 0.0
            for v in vis:
                h = (v["end"] - v["start"]) / 60; dt += h
                lines.append(f"{dd.strftime('%m/%d')} {hm(v['start'])}-{hm(v['end'])} {v['client']} {h:.2f}")
            lines.append(f"{dd.strftime('%m/%d')} DAY TOTAL {dt:.2f}")
            wk += dt
            rows.append((Cc, dd, dt, "yes"))
        lines += [f"WEEK TOTAL {wk:.2f}", "", "Visits over midnight: log on the start date.", f"Caregiver: /s/ {Cc['name']}", f"Supervisor: /s/ {sup}"]
        fn = f"visit_log_{Cc['name'].split()[0].lower()}_wk{n + 1}.pdf"
        write_scan_pdf(os.path.join(S, fn), lines, font_size=34, seed=seed * 19 + n, skew_deg=[0.25, -0.3][n], noise=220)

    g = d["gloria"]
    write_text(os.path.join(ws, "note_from_gloria.txt"),
        "Payroll for the Aug 30 - Sep 12 pay period (Sunday to Saturday, two weeks).\n\n"
        "Everyone's paper time sheets are scanned into scanned_timesheets. The payroll upload wants one line per caregiver per day they worked, "
        "saved as timesheet_hours.csv with these columns:\n\n"
        "  entry_id       employee number, an underscore, then the date - like HC-100_2026-08-31\n"
        "  employee_id    employee number as on the sheet\n"
        "  employee_name  as written on the sheet\n"
        "  work_date      YYYY-MM-DD\n"
        "  hours          hours worked that day after unpaid breaks, as a decimal (7.5, not 7:30)\n"
        "  sheet_signed   yes if the sheet that day came from is signed by both the caregiver and a supervisor, otherwise no\n\n"
        "A few rules:\n"
        "- Only days in this pay period. Days off don't get a line.\n"
        "- If someone worked more than one shift or visit on the same day, that's still one line with the hours added up.\n"
        "- A shift or visit that runs past midnight counts entirely on the day it started.\n"
        "- Put unsigned sheets in anyway - I hold those lines until the supervisor signs, so I need the flag right.\n\n"
        f"{g[0]}\n")

    header = ["entry_id", "employee_id", "employee_name", "work_date", "hours", "sheet_signed"]
    out = []
    for who, dd, hrs, sg in sorted(rows, key=lambda x: (x[0]["id"], x[1])):
        out.append([f"{who['id']}_{dd.isoformat()}", who["id"], who["name"], dd.isoformat(), f"{hrs:.2f}", sg])
    write_csv(os.path.join(ref, "timesheet_hours.csv"), header, out)
    write_csv(os.path.join(sol, "timesheet_hours.csv"), header, out)
    unsigned = [f"{B['id']}_{dd.isoformat()}" for dd in sorted(B["weeks"][W2_END])]
    split = [f"{Cc['id']}_{dd.isoformat()}" for wk in Cc["weeks"].values() for dd, v in sorted(wk.items()) if len(v) > 1]
    overnight = f"{Cc['id']}_2026-09-10"
    sunday = f"{B['id']}_2026-08-30"
    b_nohours = [f"{B['id']}_{dd.isoformat()}" for dd in sorted(B["weeks"][W1_END])]
    write_json(os.path.join(ref, "notes.json"), {"unsigned_entries": unsigned, "split_days": split, "overnight": overnight, "sunday_entry": sunday,
                                                 "old_sheet_week_ending": OLD_END.isoformat(), "caregivers": [A["id"], B["id"], Cc["id"]]})
    write_task_yaml(HERE, {
        "id": "timesheets-scanned", "track": "desk", "category": "extraction",
        "title": "Daily hours from the scanned caregiver time sheets",
        "ask": "The caregivers' time sheets for this pay period are scanned in the folder. Can you turn them into timesheet_hours.csv for payroll? Gloria's note explains what the upload needs.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the old form ends with a TOTAL row and the visit log prints a DAY TOTAL line under each day's visits and a WEEK TOTAL at the end; adding every hours figure on a date doubles the visit-log days, and a total row read as a day adds a phantom line (checks: hours per day; one row per person per day)",
            "the second week of the new form has a blank 'Approved by (supervisor)' line; every line from that sheet is sheet_signed = no while the same caregiver's first week is yes (check: signature flag)",
            "the visit log has two or three visits on several days, which add into one line per day (checks: hours per day; row count)",
            "the new form prints start, end and unpaid break minutes but no hours, so hours are end minus start minus the break (check: hours per day)",
            "the new form lists weekday names only, Sunday first, under a week-ending Saturday; the first week's Sunday is 30 August, not 6 September (check: one row per person per day)",
            "an overnight visit 22:00-06:00 on 10 September counts 8 hours on the 10th, not split across two days (checks: hours per day; one row per person per day)",
            "last pay period's sheet (week ending 29 August) is in the folder and its days are outside the period (checks: one row per person per day; row count)",
            "every sheet is an image-only scan on one of three forms, one of them landscape (check: hours per day)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "timesheet_hours.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per person per day", "path": "timesheet_hours.csv", "column": "entry_id", "ref": "timesheet_hours.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "timesheet_hours.csv", "equals_ref": "timesheet_hours.csv"},
            {"type": "csv_values_match", "name": "employee and date", "path": "timesheet_hours.csv", "ref": "timesheet_hours.csv", "key": "entry_id",
             "columns": ["employee_id", "employee_name", "work_date"], "normalize": ["alnum"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "hours per day", "path": "timesheet_hours.csv", "ref": "timesheet_hours.csv", "key": "entry_id",
             "columns": ["hours"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": split + [overnight] + b_nohours},
            {"type": "csv_values_match", "name": "signature flag", "path": "timesheet_hours.csv", "ref": "timesheet_hours.csv", "key": "entry_id",
             "columns": ["sheet_signed"], "min_accuracy": 1.0, "must_match_keys": unsigned + [b_nohours[0]]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
