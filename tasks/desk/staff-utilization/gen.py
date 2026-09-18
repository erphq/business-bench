#!/usr/bin/env python3
"""staff-utilization: an accounting firm's September time entries, HR roster and leave export to utilization per person.

    python gen.py [--seed N]

Business: Mossbank Accounting, an eight-person CPA practice. The managing partner reviews billable utilization
every month; September has a firm holiday, a new starter, two part-timers and a handful of leave requests in
various states.

Traps (each caught by a check, see task.yaml):
  * part-timers' capacity comes from the HR sheet's weekly hours (24 and 30), and full-time is 37.5 a week, not 40
                                                                   (checks: Omar Haddad capacity; utilization per person)
  * Labor Day (7 September) is a firm holiday; a leave request spanning it counts it in the HR system's Days
    column, so subtracting Days takes the holiday off twice       (check: Kenneth Oduya capacity)
  * a vacation that starts in August carries its whole length in Days; only the September weekdays count
                                                                   (check: Priya Raman capacity)
  * rejected, cancelled and pending requests are not leave; a half day is half a day (checks: Omar Haddad capacity;
    utilization per person)
  * the new senior started on 14 September; capacity runs from the start date (check: Hannah Brooks capacity)
  * internal time (admin, training, marketing) is logged but never billable; write-offs are marked N
                                                                   (check: utilization per person)
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

M_START, M_END = date(2026, 9, 1), date(2026, 9, 30)
HOLIDAY = date(2026, 9, 7)
# id, name, title, employment, hours/week, start, billable share of client time, overtime habit
STAFF = [
    ("E101", "Dana Mossbank", "Managing partner", "Full-time", 37.5, date(2014, 3, 3), 0.62, 1.12),
    ("E102", "Kenneth Oduya", "Senior accountant", "Full-time", 37.5, date(2019, 8, 12), 0.86, 1.05),
    ("E103", "Priya Raman", "Senior accountant", "Full-time", 37.5, date(2020, 1, 6), 0.84, 1.04),
    ("E104", "Tomasz Wojcik", "Staff accountant", "Full-time", 37.5, date(2023, 6, 19), 0.80, 1.00),
    ("E105", "Grace Lin", "Staff accountant", "Part-time", 24.0, date(2024, 2, 5), 0.78, 0.98),
    ("E106", "Omar Haddad", "Bookkeeper", "Part-time", 30.0, date(2022, 9, 26), 0.88, 1.00),
    ("E107", "Hannah Brooks", "Senior accountant", "Full-time", 37.5, date(2026, 9, 14), 0.55, 0.95),
    ("E108", "Luis Ortega", "Senior accountant", "Full-time", 37.5, date(2018, 4, 2), 0.83, 1.06),
]
CLIENT_SERVICES = ["Monthly bookkeeping", "Payroll processing", "1120-S preparation", "1065 preparation", "Advisory",
                   "Sales tax filing", "Year-end close", "Review engagement"]
INTERNAL = ("Mossbank Accounting (internal)", ["Admin", "CPE training", "Marketing", "Practice meeting"])


def weekdays(a: date, b: date):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def build(seed: int) -> dict:
    r = rng(seed)
    clients = [c[0] for c in pick(r, COMPANIES, 16)]
    info = {s[0]: s for s in STAFF}
    work_days = [d for d in weekdays(M_START, M_END) if d != HOLIDAY]

    # ---- leave requests: (id, type, from, to, days column, status, part) ----
    leave = [
        ("E103", "Vacation", date(2026, 8, 27), date(2026, 9, 2), None, "Approved", 1.0),
        ("E102", "Vacation", date(2026, 9, 4), date(2026, 9, 8), None, "Approved", 1.0),
        ("E104", "Vacation", date(2026, 9, 16), date(2026, 9, 18), None, "Rejected", 1.0),
        ("E104", "Sick", date(2026, 9, 24), date(2026, 9, 24), None, "Approved", 1.0),
        ("E106", "Personal", date(2026, 9, 11), date(2026, 9, 11), None, "Approved", 0.5),
        ("E105", "Sick", date(2026, 9, 29), date(2026, 9, 29), None, "Approved", 1.0),
        ("E108", "Vacation", date(2026, 9, 21), date(2026, 9, 25), None, "Approved", 1.0),
        ("E108", "Vacation", date(2026, 9, 28), date(2026, 9, 29), None, "Cancelled", 1.0),
        ("E101", "Vacation", date(2026, 10, 12), date(2026, 10, 16), None, "Pending", 1.0),
        ("E106", "Jury duty", date(2026, 9, r.choice([15, 16, 17])), None, None, "Pending", 1.0),
    ]
    rows = []
    for sid, typ, a, b, _, status, part in leave:
        b = b or a
        hr_days = sum(1 for _ in weekdays(a, b)) * part       # the HR system counts every weekday, holiday included
        rows.append({"id": sid, "type": typ, "from": a, "to": b, "days": hr_days, "status": status, "part": part})
    leave = rows
    off = {s[0]: {} for s in STAFF}                            # id -> {date: fraction off}
    for lv in leave:
        if lv["status"] != "Approved":
            continue
        for d in weekdays(lv["from"], lv["to"]):
            if M_START <= d <= M_END and d != HOLIDAY:
                off[lv["id"]][d] = off[lv["id"]].get(d, 0) + lv["part"]

    # ---- time entries ----
    entries = []
    for sid, name, title, emp, wk, start, bill_share, ot in STAFF:
        daily = wk / 5
        for d in weekdays(M_START, M_END):
            if d < start:
                continue
            frac = 1 - off[sid].get(d, 0)
            if d == HOLIDAY:
                if sid == "E101" and r.random() < 0.7:
                    entries.append({"date": d, "id": sid, "client": r.choice(clients), "service": "Advisory", "hours": 2.0, "bill": "Y"})
                continue
            if frac <= 0:
                continue
            hours_today = daily * frac * ot * r.uniform(0.85, 1.12)
            internal_share = r.uniform(0.05, 0.2) if sid != "E101" else r.uniform(0.2, 0.35)
            if sid == "E107":
                internal_share = r.uniform(0.3, 0.5) if d < date(2026, 9, 21) else r.uniform(0.1, 0.25)   # onboarding
            chunks = r.randint(1, 4)
            for c in range(chunks):
                h = round(hours_today / chunks * 4) / 4
                if h <= 0:
                    continue
                if r.random() < internal_share:
                    entries.append({"date": d, "id": sid, "client": INTERNAL[0], "service": r.choice(INTERNAL[1]), "hours": h, "bill": "N"})
                else:
                    bill = "Y" if r.random() < bill_share / (1 - 0.12) else "N"
                    entries.append({"date": d, "id": sid, "client": r.choice(clients), "service": r.choice(CLIENT_SERVICES), "hours": h, "bill": bill})
    entries.sort(key=lambda e: (e["date"], e["id"], e["client"]))

    # ---- truth ----
    out = []
    for sid, name, title, emp, wk, start, *_ in STAFF:
        days = sum(1 for d in work_days if d >= start)
        leave_days = sum(v for d, v in off[sid].items() if d >= start)
        cap = round((days - leave_days) * wk / 5, 2)
        billable = round(sum(e["hours"] for e in entries if e["id"] == sid and e["bill"] == "Y"), 2)
        logged = round(sum(e["hours"] for e in entries if e["id"] == sid), 2)
        hr_leave = sum(lv["days"] for lv in leave if lv["id"] == sid and lv["status"] == "Approved" and lv["from"] <= M_END and lv["to"] >= M_START)
        out.append({"id": sid, "name": name, "wk": wk, "start": start, "work_days": days, "leave_days": leave_days, "capacity": cap,
                    "billable": billable, "logged": logged, "util": round(billable / cap, 4),
                    "naive_cap_40": round((len(list(weekdays(M_START, M_END))) - 0) * 8, 2),
                    "naive_cap_hrdays": round((days - hr_leave) * wk / 5, 2),
                    "naive_cap_allstatus": round((days - sum(lv["days"] for lv in leave if lv["id"] == sid and lv["from"] <= M_END and lv["to"] >= M_START)) * wk / 5, 2)})
    firm_cap = round(sum(o["capacity"] for o in out), 2)
    firm_bill = round(sum(o["billable"] for o in out), 2)
    return {"entries": entries, "leave": leave, "staff": out, "by_id": {o["id"]: o for o in out}, "firm_cap": firm_cap,
            "firm_bill": firm_bill, "firm_util": round(firm_bill / firm_cap, 4), "clients": clients}


def acceptable(d: dict) -> bool:
    for o in d["staff"]:
        row = [o["wk"], o["work_days"], o["capacity"], o["billable"], o["logged"], o["util"] * 100, o["leave_days"]]
        for key in ("capacity",):
            v = o[key]
            if any(abs(v - w) <= 0.01 * v for w in row if w is not v):
                return False
        if not 0.35 <= o["util"] <= 1.05:
            return False
        if any(abs(o["util"] * 100 - w) <= 1.0 for w in (o["billable"], o["logged"], o["capacity"], o["wk"])):
            return False
    b = d["by_id"]
    if b["E102"]["naive_cap_hrdays"] == b["E102"]["capacity"] or b["E103"]["naive_cap_hrdays"] == b["E103"]["capacity"]:
        return False
    vals = [o["capacity"] for o in d["staff"]] + [o["billable"] for o in d["staff"]] + [d["firm_bill"]]
    return all(abs(d["firm_cap"] - v) > 0.01 * d["firm_cap"] for v in vals)


# --------------------------------------------------------------------------- deliverables

def util_sheets(d: dict) -> dict:
    staff = d["staff"]
    time_rows = [[e["id"], e["date"].isoformat(), e["hours"], 1 if e["bill"] == "Y" else 0] for e in d["entries"]]
    leave_rows = []
    for lv in d["leave"]:
        if lv["status"] != "Approved":
            continue
        for dd in weekdays(lv["from"], lv["to"]):
            if M_START <= dd <= M_END and dd != HOLIDAY:
                leave_rows.append([lv["id"], dd.isoformat(), lv["part"], lv["type"]])
    nt, nl = len(time_rows) + 1, len(leave_rows) + 1
    rows = []
    for i, o in enumerate(staff, start=2):
        rows.append([o["id"], o["name"], o["wk"], o["start"].isoformat() if o["start"] > M_START else "", o["work_days"],
                     f"=SUMIFS(Leave!$C$2:$C${nl},Leave!$A$2:$A${nl},A{i})", f"=E{i}-F{i}", f"=C{i}/5", f"=ROUND(G{i}*H{i},2)",
                     f"=SUMIFS(Time!$C$2:$C${nt},Time!$A$2:$A${nt},A{i},Time!$D$2:$D${nt},1)",
                     f"=SUMIFS(Time!$C$2:$C${nt},Time!$A$2:$A${nt},A{i})", f"=IF(I{i}=0,0,ROUND(J{i}/I{i},4))"])
    last = len(staff) + 1
    rows.append(["", "Total firm", "", "", "", f"=SUM(F2:F{last})", f"=SUM(G2:G{last})", "", f"=SUM(I2:I{last})",
                 f"=SUM(J2:J{last})", f"=SUM(K2:K{last})", f"=IF(I{last + 1}=0,0,ROUND(J{last + 1}/I{last + 1},4))"])
    rows.append([])
    rows.append(["", "September 2026 has 22 weekdays; Labor Day (7 Sep) is a firm holiday, leaving 21 working days. Capacity = "
                     "(working days from start date - approved leave days) x weekly hours / 5. Utilization = billable hours / capacity."])
    return {"Utilization": {"header": ["Staff ID", "Name", "Hours per week", "Started", "Working days", "Approved leave days",
                                       "Available days", "Hours per day", "Capacity hours", "Billable hours", "Hours logged", "Utilization"],
                            "rows": rows, "widths": {"B": 20, "I": 14, "J": 14, "L": 12},
                            "number_formats": {"L": "0.0%"}},
            "Time": {"header": ["staff id", "date", "hours", "billable"], "rows": time_rows},
            "Leave": {"header": ["staff id", "date", "day fraction", "type"], "rows": leave_rows}}



def cent_tolerant(spec: dict) -> dict:
    """Figures computed from exact source data tie to the cent: every workbook pin gets a tolerance under 1.00."""
    for c in spec["checks"]:
        if c["type"] == "xlsx_value_present" and not c.get("rounding"):
            exp = abs(float(c["expected"]))
            c["rel_tol"] = min(float(c.get("rel_tol", 0.005)), float(f"{0.9 / max(exp, 1.0):.2g}"))
    return spec


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    names = {s[0]: s[1] for s in STAFF}

    # ---- workspace ----
    write_csv(os.path.join(ws, "time_entries_september_2026.csv"),
              ["Work Date", "Staff", "Client", "Service", "Hours", "Billable"],
              [[e["date"].strftime("%m/%d/%Y"), f"{names[e['id']].split()[1]}, {names[e['id']].split()[0]}", e["client"], e["service"],
                f"{e['hours']:.2f}", e["bill"]] for e in d["entries"]],
              preamble=["Mossbank Accounting - Time Detail", "Period: 09/01/2026 - 09/30/2026"], crlf=True)
    write_xlsx(os.path.join(ws, "hr_roster.xlsx"), {"Staff": {
        "header": ["Employee ID", "Name", "Title", "Employment", "Standard hours / week", "Start date", "Manager"],
        "rows": [[s[0], s[1], s[2], s[3], s[4], s[5], "" if s[0] == "E101" else "Dana Mossbank"] for s in STAFF]
                + [["E090", "Mei Chen", "Office manager", "Full-time", 37.5, date(2016, 5, 9), "Dana Mossbank"]],
        "widths": {"B": 18, "C": 20, "E": 22, "F": 12}},
        "Holidays 2026": {"header": ["Date", "Holiday", "Office"],
                          "rows": [[date(2026, 1, 1), "New Year's Day", "Closed"], [date(2026, 5, 25), "Memorial Day", "Closed"],
                                   [date(2026, 7, 3), "Independence Day (observed)", "Closed"], [HOLIDAY, "Labor Day", "Closed"],
                                   [date(2026, 10, 12), "Columbus Day", "Open"], [date(2026, 11, 26), "Thanksgiving", "Closed"],
                                   [date(2026, 11, 27), "Day after Thanksgiving", "Closed"], [date(2026, 12, 25), "Christmas Day", "Closed"]],
                          "widths": {"B": 28}}}, creator="HR")
    write_csv(os.path.join(ws, "leave_requests_export.csv"),
              ["Employee ID", "Employee", "Leave Type", "Start", "End", "Days", "Status", "Submitted"],
              [[lv["id"], names[lv["id"]], lv["type"], lv["from"].isoformat(), lv["to"].isoformat(), f"{lv['days']:g}", lv["status"],
                (lv["from"] - timedelta(days=12)).isoformat()] for lv in sorted(d["leave"], key=lambda x: (x["from"], x["id"]))])
    write_text(os.path.join(ws, "note_from_dana.txt"),
               "September utilization, please, same as we talk about it in partner meetings: billable hours divided by the hours\n"
               "each person was actually available.\n\n"
               "Available hours are the working days in the month times the person's standard day - their standard week from the\n"
               "HR roster divided by five. Working days are weekdays the office is open, less any approved leave. Anyone who\n"
               "started this month is counted from their start date. Mei is admin and is not on the report.\n\n"
               "One row per person with their available hours, billable hours and utilization, and a firm total at the bottom.\n\n"
               "Dana\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "utilization.csv"), ["staff_id", "name", "capacity_hours", "billable_hours", "utilization"],
              [[o["id"], o["name"], f"{o['capacity']:.2f}", f"{o['billable']:.2f}", f"{o['util']:.4f}"] for o in d["staff"]])
    write_json(os.path.join(ref, "notes.json"), {
        "utilization": {o["name"]: o["util"] for o in d["staff"]}, "firm_utilization": d["firm_util"],
        "capacity": {o["name"]: o["capacity"] for o in d["staff"]}, "firm_capacity": d["firm_cap"], "firm_billable": d["firm_bill"],
        "working_days": 21, "holiday": HOLIDAY.isoformat(),
        "naive": {o["name"]: {"cap_40h_22d": o["naive_cap_40"], "cap_hr_days_column": o["naive_cap_hrdays"],
                              "cap_all_statuses": o["naive_cap_allstatus"]} for o in d["staff"]}})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "utilization.xlsx"), util_sheets(d), creator="reference")

    b = d["by_id"]
    write_task_yaml(HERE, cent_tolerant({
        "id": "staff-utilization", "track": "desk", "category": "spreadsheet",
        "title": "September billable utilization per person",
        "ask": ("Dana wants September's utilization for everyone from the time entries, the HR roster and the leave export. "
                "Build utilization.xlsx with live formulas - her note says how the firm counts it.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "capacity comes from the roster's standard week: full-time is 37.5 hours (7.5 a day, not 8) and the two part-timers "
            "work 24 and 30 hours (checks: Omar Haddad capacity; utilization per person)",
            "Labor Day (7 September, on the roster's holiday tab) is a firm holiday, leaving 21 working days; Kenneth's approved "
            "4-8 September vacation shows 3 in the HR Days column because it counts the holiday, so subtracting Days takes the "
            "holiday off twice (check: Kenneth Oduya capacity)",
            "Priya's vacation runs 27 August to 2 September and its Days column carries all five weekdays; only 1 and 2 September "
            "come off September (check: Priya Raman capacity)",
            "rejected, cancelled and pending requests sit in the same export and are not leave; Omar's personal day is a half day "
            "(checks: Omar Haddad capacity; utilization per person)",
            "Hannah Brooks started on 14 September, so her capacity covers 13 working days, not the month "
            "(check: Hannah Brooks capacity)",
            "internal admin, training and marketing time is logged under the firm itself and marked N, as are write-offs; the "
            "time export names staff 'Last, First' under a two-line preamble with CRLF endings, and the roster also lists the "
            "office manager, who is not on the report (checks: utilization per person; firm capacity total)",
        ],
        "checks": [
            {"type": "file_exists", "name": "utilization.xlsx exists", "path": "utilization.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "utilization.xlsx", "min_count": 16},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "utilization.xlsx"},
            {"type": "xlsx_value_present", "name": "Omar Haddad capacity (part-time, half day)", "path": "utilization.xlsx",
             "expected": b["E106"]["capacity"], "rel_tol": 0.002, "near_text": "omar"},
            {"type": "xlsx_value_present", "name": "Kenneth Oduya capacity (leave over the holiday)", "path": "utilization.xlsx",
             "expected": b["E102"]["capacity"], "rel_tol": 0.002, "near_text": "kenneth"},
            {"type": "xlsx_value_present", "name": "Priya Raman capacity (leave from August)", "path": "utilization.xlsx",
             "expected": b["E103"]["capacity"], "rel_tol": 0.002, "near_text": "priya"},
            {"type": "xlsx_value_present", "name": "Hannah Brooks capacity (started 14 Sep)", "path": "utilization.xlsx",
             "expected": b["E107"]["capacity"], "rel_tol": 0.002, "near_text": "hannah"},
            {"type": "xlsx_value_present", "name": "firm capacity total", "path": "utilization.xlsx",
             "expected": d["firm_cap"], "rel_tol": 0.002, "near_text": "total"},
            {"type": "custom", "name": "utilization per person", "module": "check.py"},
        ],
    }))
    print(f"seed={seed} entries={len(d['entries'])}")
    for o in d["staff"]:
        print("  ", {k: v for k, v in o.items() if k != "start"})
    print("  firm", d["firm_cap"], d["firm_bill"], d["firm_util"])


if __name__ == "__main__":
    s = argparse_seed()
    for attempt in range(800):
        if acceptable(build(s * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 800 attempts")
    emit(s * 1000 + attempt)
