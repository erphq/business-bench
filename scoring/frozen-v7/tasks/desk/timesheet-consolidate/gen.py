#!/usr/bin/env python3
"""timesheet-consolidate: six crew timesheets in three layouts into one payroll table with weekly overtime.

    python gen.py [--seed N] [--naive DIR]

Business: a landscaping company with three crews. Each crew lead turns in a weekly sheet in their own format;
the office manager keys payroll from one table, one line per person per payroll week.

Traps (each caught by a check, see task.yaml):
  * the install crew writes a 12-hour clock; half-day Saturdays end at "12:30 PM", which a blanket +12 for PM
    turns into half past midnight the next day                               (check: total hours per person-week)
  * lunch is a separate column on the install sheets, missing on the maintenance grid (policy: 30 min off any
    shift over 6 hours) and already taken off on the irrigation sheets       (check: total hours per person-week)
  * the irrigation sheets use day-first dates and run Monday to Sunday: the first Sunday belongs to the second
    payroll week and the last Sunday to the next pay period                   (checks: total hours per person-week; row count)
  * overtime is over 40 in a payroll week across every crew: one labourer splits a week between two crews and
    only crosses 40 once both sheets are added, and another has 40+ one week and under 40 the next, so a
    pay-period (over 80) reading pays no overtime                            (check: overtime per person-week)
  * the maintenance grid carries a two-line preamble and a crew-total row that is not a person (checks: people; row count)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

P_START = date(2026, 8, 30)                     # Sunday
WEEK_END = [date(2026, 9, 5), date(2026, 9, 12)]
SITES = ["Riverbend HOA", "Laurel Ct commons", "Hawthorn office park", "Magnolia Dr residence", "Union St library",
         "Ridge Rd church", "Maple St townhomes", "Willow Way school"]


def week_of(d: date) -> int | None:
    if P_START <= d <= WEEK_END[0]:
        return 0
    if WEEK_END[0] < d <= WEEK_END[1]:
        return 1
    return None


def q(r, lo_h: float, hi_h: float) -> int:
    """a clock time in minutes on the quarter hour"""
    return int(r.randint(int(lo_h * 4), int(hi_h * 4)) * 15)


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = []
    while len(ppl) < 7:
        f, l = person(r)
        if f in {p[0] for p in ppl} or l in {p[1] for p in ppl}:
            continue
        ppl.append((f, l))
    names = [f"{f} {l}" for f, l in ppl]
    install_lead, install_hand, floater, maint_lead, maint_hand, irr_lead, irr_hand = names
    shifts = []   # {emp, date, crew, start, end, lunch, net}

    days = [P_START + timedelta(days=i) for i in range(15)]    # Sun 30 Aug .. Sun 13 Sep
    for d in days:
        wd = d.weekday()                                          # Mon 0 .. Sun 6
        wk = 0 if d <= WEEK_END[0] else 1
        # install crew: Mon-Fri long days, a Saturday half day in week one
        for emp in (install_lead, install_hand, floater):
            if d > WEEK_END[1] or wd == 6:
                continue
            if emp == floater and not (wk == 0 and wd in (0, 1, 2)):
                continue
            if wd == 5:
                if wk == 0 and emp in (install_lead, install_hand):
                    st = q(r, 7, 7.5)
                    en = r.choice([12 * 60 + 30, 12 * 60 + 15, 12 * 60 + 45])
                    shifts.append({"emp": emp, "date": d, "crew": "install", "start": st, "end": en, "lunch": 0})
                continue
            st = q(r, 6.5, 7.5)
            en = q(r, 14.75, 16.5) if emp != install_hand or wk == 0 else q(r, 14.0, 15.0)
            lunch = r.choice([30, 30, 30, 45, 0])
            shifts.append({"emp": emp, "date": d, "crew": "install", "start": st, "end": en, "lunch": lunch})
        # maintenance crew: Mon-Fri, the floater joins Thu-Sat in week one and all of week two
        for emp in (maint_lead, maint_hand, floater):
            if d > WEEK_END[1] or wd == 6:
                continue
            if emp == floater and wk == 0 and wd not in (3, 4, 5):
                continue
            if wd == 5 and not (emp == floater and wk == 0):
                continue
            if wd == 4 and emp == maint_hand and wk == 1:
                st = q(r, 6.0, 6.5); en = st + r.choice([270, 300, 330])       # short Friday: 4.5-5.5 h, no lunch taken off
            elif wd == 5:
                st = q(r, 6.5, 7.0); en = st + r.choice([300, 330])            # floater's Saturday, under 6 h
            else:
                st = q(r, 6.5, 7.5); en = q(r, 14.5, 16.0)
            shifts.append({"emp": emp, "date": d, "crew": "maintenance", "start": st, "end": en, "lunch": None})
        # irrigation crew: Monday to Sunday sheets, net hours only; works both Sundays
        for emp in (irr_lead, irr_hand):
            if d == P_START:
                continue
            if wd == 5 and r.random() < 0.5:
                continue
            net_q = r.randint(24, 34) if wd < 5 else r.randint(16, 24)     # quarter hours
            if wd == 6:
                net_q = r.randint(18, 28)
            shifts.append({"emp": emp, "date": d, "crew": "irrigation", "start": None, "end": None, "lunch": None,
                           "net": net_q * 15})
    for s in shifts:
        if s["crew"] == "install":
            s["net"] = s["end"] - s["start"] - s["lunch"]
        elif s["crew"] == "maintenance":
            gross = s["end"] - s["start"]
            s["net"] = gross - (30 if gross > 360 else 0)
        s["week"] = week_of(s["date"])
    totals = {}
    for s in shifts:
        if s["week"] is None:
            continue
        key = (s["emp"], s["week"])
        totals[key] = totals.get(key, 0) + s["net"]
    table = []
    for emp in names:
        for wk in (0, 1):
            mins = totals.get((emp, wk), 0)
            if not mins:
                continue
            tot = mins / 60
            table.append({"emp": emp, "week_ending": WEEK_END[wk], "total": tot, "regular": min(tot, 40.0), "overtime": max(tot - 40.0, 0.0)})
    return {"names": names, "roles": {"install_lead": install_lead, "install_hand": install_hand, "floater": floater,
                                      "maint_lead": maint_lead, "maint_hand": maint_hand, "irr_lead": irr_lead, "irr_hand": irr_hand},
            "shifts": shifts, "table": table, "totals": totals}


def acceptable(d: dict) -> bool:
    ro, sh, tot = d["roles"], d["shifts"], d["totals"]
    fl = ro["floater"]
    w1_install = sum(s["net"] for s in sh if s["emp"] == fl and s["week"] == 0 and s["crew"] == "install")
    w1_maint = sum(s["net"] for s in sh if s["emp"] == fl and s["week"] == 0 and s["crew"] == "maintenance")
    if not (w1_install < 2400 and w1_maint < 2400 and w1_install + w1_maint >= 2400 + 90):
        return False
    hand = ro["install_hand"]
    if not (tot[(hand, 0)] >= 2400 + 120 and tot[(hand, 1)] <= 2400 - 180 and tot[(hand, 0)] + tot[(hand, 1)] <= 4800):
        return False
    # the two leads with long weeks also clear 40 somewhere, so overtime is not a one-person column
    if sum(1 for (e, w), m in tot.items() if m > 2400) < 3:
        return False
    if sum(1 for (e, w), m in tot.items() if m <= 2400) < 4:
        return False
    # no maintenance shift sits exactly at 6 hours gross
    if any(s["crew"] == "maintenance" and s["end"] - s["start"] == 360 for s in sh):
        return False
    return True


# --------------------------------------------------------------------------- file writers

def clock12(m: int) -> str:
    h, mm = divmod(m, 60)
    suf = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{mm:02d} {suf}"


def clock24(m: int, style: int) -> str:
    h, mm = divmod(m, 60)
    return f"{h:02d}:{mm:02d}" if style == 0 else f"{h}:{mm:02d}"


def hours_str(mins: int) -> str:
    v = mins / 60
    return f"{v:g}" if v != int(v) else f"{int(v)}"


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 31)
    ro, sh = d["roles"], d["shifts"]
    first = lambda n: n.split()[0]

    # install crew: one xlsx per payroll week, 12-hour clock, lunch column
    for wk, label in ((0, "0830"), (1, "0906")):
        rows = []
        for s in sorted((s for s in sh if s["crew"] == "install" and s["week"] == wk), key=lambda s: (s["date"], s["emp"])):
            rows.append([s["date"].strftime("%-m/%-d/%Y"), s["emp"], clock12(s["start"]), clock12(s["end"]), s["lunch"], r.choice(SITES)])
        write_xlsx(os.path.join(ws, f"install_crew_timesheet_{label}.xlsx"), {"Time": {
            "merged_title": f"Install crew timesheet - week of {(P_START + timedelta(days=7 * wk)).strftime('%b %-d')} - lead: {ro['install_lead']}",
            "header": ["Date", "Employee", "Time In", "Time Out", "Lunch (min)", "Job"], "rows": rows,
            "widths": {"A": 12, "B": 20, "C": 11, "D": 11, "F": 24}}}, creator=ro["install_lead"])

    # maintenance crew: one csv grid per payroll week, 24-hour ranges, a crew-total row
    for wk in (0, 1):
        wk_days = [P_START + timedelta(days=7 * wk + i) for i in range(7)]
        header = ["Employee"] + [dd.strftime("%a %-m/%-d") for dd in wk_days] + ["Notes"]
        rows, day_tot = [], [0] * 7
        for emp in (ro["maint_lead"], ro["maint_hand"], ro["floater"]):
            cells = []
            for i, dd in enumerate(wk_days):
                s = next((s for s in sh if s["crew"] == "maintenance" and s["emp"] == emp and s["date"] == dd), None)
                if s is None:
                    cells.append("")
                    continue
                style = r.randrange(2)
                sep = "-" if r.random() < 0.7 else " - "
                cells.append(f"{clock24(s['start'], style)}{sep}{clock24(s['end'], style)}")
                day_tot[i] += s["end"] - s["start"]
            note = "splits the week with install crew" if emp == ro["floater"] and wk == 0 else ""
            rows.append([emp] + cells + [note])
        rows.append(["Crew total (hrs)"] + [hours_str(t) if t else "" for t in day_tot] + [""])
        write_csv(os.path.join(ws, f"maintenance_crew_week_{wk_days[0].isoformat()}.csv"), header, rows,
                  preamble=[f"Maintenance crew - weekly time - {ro['maint_lead']}", f"Week starting {wk_days[0].strftime('%m/%d/%Y')}"], crlf=True)

    # irrigation crew: Monday-to-Sunday sheets, day-first dates, net hours
    for i, mon in enumerate((date(2026, 8, 31), date(2026, 9, 7))):
        sun = mon + timedelta(days=6)
        rows = []
        for s in sorted((s for s in sh if s["crew"] == "irrigation" and mon <= s["date"] <= sun), key=lambda s: (s["date"], s["emp"])):
            rows.append([s["date"].strftime("%d/%m/%Y"), s["emp"], r.choice(SITES), s["net"] / 60])
        write_xlsx(os.path.join(ws, f"irrigation_{'a' if i == 0 else 'b'}_{ro['irr_lead'].split()[0].lower()}.xlsx"), {"Hours": {
            "merged_title": f"Irrigation crew hours {mon.strftime('%d/%m')} to {sun.strftime('%d/%m/%Y')}",
            "header": ["Date", "Name", "Site", "Hrs (lunch off)"], "rows": rows,
            "number_formats": {"D": "0.00"}, "widths": {"A": 12, "B": 20, "C": 24}}}, creator=ro["irr_lead"])

    write_text(os.path.join(ws, "note_from_rachel.txt"),
               "Payroll for Aug 30 - Sep 12\n"
               "\n"
               "All six crew sheets for the pay period are in this folder. I key payroll from one table: one line per person\n"
               "per payroll week, with employee, week_ending (the Saturday), regular_hours, overtime_hours and total_hours.\n"
               "\n"
               "- Payroll weeks run Sunday to Saturday. Overtime is anything over 40 hours in a payroll week, counting every\n"
               "  crew the person worked on that week.\n"
               "- Pay is time worked less unpaid lunch. " + first(ro["install_lead"]) + " writes the lunch actually taken in its own column (0 means they worked through)."
               + "\n  " + first(ro["maint_lead"]) + "'s sheets are start and finish only, so take our standard 30 minute lunch off any shift\n"
               "  longer than 6 hours. "
               + first(ro["irr_lead"]) + "'s hours already have lunch taken off.\n"
               "- " + first(ro["irr_lead"]) + "'s sheets run Monday to Sunday because of the weekend irrigation starts. A Sunday on those sheets belongs to\n"
               "  the payroll week that starts that day; the last Sunday on the second one is next pay period, leave it for then.\n"
               "\n"
               "Rachel\n")

    header = ["employee", "week_ending", "regular_hours", "overtime_hours", "total_hours"]
    rows = [[t["emp"], t["week_ending"].isoformat(), f"{t['regular']:.2f}", f"{t['overtime']:.2f}", f"{t['total']:.2f}"] for t in d["table"]]
    write_csv(os.path.join(ref, "hours.csv"), header, rows)
    write_csv(os.path.join(sol, "hours.csv"), header, rows)
    next_sunday = [s for s in sh if s["week"] is None]
    write_json(os.path.join(ref, "notes.json"), {
        "roles": ro, "moved_sunday": "2026-09-06", "next_period_sunday_minutes": sum(s["net"] for s in next_sunday),
        "noon_half_days": [[s["emp"], s["date"].isoformat(), clock12(s["end"])] for s in sh if s["crew"] == "install" and 720 <= s["end"] < 780],
        "overtime_rows": [[t["emp"], t["week_ending"].isoformat(), t["overtime"]] for t in d["table"] if t["overtime"] > 0]})

    write_task_yaml(HERE, {
        "id": "timesheet-consolidate", "track": "desk", "category": "spreadsheet",
        "title": "Consolidate the crew timesheets for payroll",
        "ask": ("Can you pull the crew timesheets for this pay period into one table for payroll, overtime worked out? "
                "Save it as hours.csv. Rachel's note says how we count hours.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the install crew sheets use a 12-hour clock and the Saturday half days end at '12:15 PM' to '12:45 PM'; adding 12 to "
            "every PM time turns those into shifts ending after midnight (check: total hours per person-week)",
            "lunch is its own column on the install sheets (30, 45 or 0 minutes), absent on the maintenance grid where the note's "
            "30-minute rule applies only to shifts over 6 hours (short Friday and Saturday shifts keep every minute), and already taken "
            "off on the irrigation sheets, so deducting it everywhere or nowhere moves most rows (check: total hours per person-week)",
            "the irrigation sheets write dates day-first (06/09/2026 is 6 September) and run Monday to Sunday: the first Sunday "
            "moves into the second payroll week and the last Sunday (13/09) is next pay period; filing each sheet as one payroll "
            "week puts both Sundays in the wrong place (checks: total hours per person-week; row count)",
            f"{ro['floater']} works Monday to Wednesday on the install crew and Thursday to Saturday on maintenance in the first week; "
            "neither sheet reaches 40 on its own but the week does, and the table needs one line per week for that person, not one per sheet "
            "(checks: overtime per person-week; row count)",
            f"{ro['install_hand']} works over 40 in the first week and under 40 in the second, under 80 for the period; a "
            "pay-period overtime reading pays no overtime at all (check: overtime per person-week)",
            "the maintenance grid has a two-line preamble, CRLF endings, ranges written '06:30-15:00' and '6:30 - 15:00', and a "
            "'Crew total (hrs)' row that is not a person (checks: people on the table; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "hours.csv", "columns": header},
            {"type": "csv_set_equal", "name": "people on the table", "path": "hours.csv", "column": "employee", "ref": "hours.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count (one line per person per week)", "path": "hours.csv", "equals_ref": "hours.csv"},
            {"type": "custom", "name": "total hours per person-week", "module": "check.py"},
            {"type": "custom", "name": "overtime per person-week", "module": "check_overtime.py"},
        ],
    })
    print(f"seed={seed} shifts={len(sh)} rows={len(d['table'])}")
    for t in d["table"]:
        print(f"  {t['emp']:22} {t['week_ending']} total={t['total']:.2f} ot={t['overtime']:.2f}")


def write_naive(d: dict, out: str) -> None:
    """Per-sheet reading: each file is one payroll week, gross clock time with +12 on every PM, no lunch rules,
    Tomasz's two sheets kept as two lines, overtime over 80 for the period."""
    os.makedirs(out, exist_ok=True)
    per = {}
    for s in d["shifts"]:
        if s["crew"] == "irrigation":
            wk = 0 if s["date"] <= date(2026, 9, 6) else 1
            mins = s["net"]
        else:
            wk = s["week"]
            end = s["end"] + (720 if 720 <= s["end"] < 780 else 0)   # "12:30 PM" read as 24:30
            mins = end - s["start"]
        key = (s["emp"], s["crew"], wk)
        per[key] = per.get(key, 0) + mins
    rows = []
    for (emp, crew, wk), mins in sorted(per.items()):
        tot = mins / 60
        rows.append([emp, WEEK_END[wk].isoformat(), f"{tot:.2f}", "0.00", f"{tot:.2f}"])
    write_csv(os.path.join(out, "hours.csv"), ["employee", "week_ending", "regular_hours", "overtime_hours", "total_hours"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(600):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 600 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
