#!/usr/bin/env python3
"""gusto-employee-import: a brewery's HR roster workbook turned into Gusto's employee upload file.

    python gen.py [--seed N]

Business: Tamarack Brewing (a production brewhouse, two taprooms, one remote sales rep) is moving payroll to
Gusto. The office manager keeps a roster workbook that mixes current staff, people who left and contractors.

Traps (each caught by a check, see task.yaml):
  * the roster's SSN column holds masked last-four values in four spellings; Gusto rejects partial numbers,
    so the column stays blank                                                  (check: SSN left blank)
  * salaried pay is written per year, per month or per paycheck (biweekly); Gusto wants the annual figure,
    and a few rows have a blank Pay Type where the Per column decides           (checks: rate; employee type and payment unit)
  * salaried staff split into Salary/No overtime and Salary/Eligible for overtime by the OT Exempt column
                                                                               (check: employee type and payment unit)
  * rehired staff start on their rehire date; hire dates come as real dates and three text formats (check: start date)
  * locations are short names; the Old Market taproom moved, the office sits at the brewhouse, and the remote
    rep's work address is the home address in the Notes column               (check: work address)
  * terminated staff and 1099 contractors share the sheet and stay out; staff on leave stay in
                                                                               (checks: one row per employee; row count)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["First Name", "Last Name", "Personal Email", "SSN", "Start Date", "Work Address", "Job Title", "Department",
            "Employee Type", "Rate", "Payment Unit"]
ADDR = {
    "pearl": "1850 Pearl St, Boulder, CO 80302",
    "brew": "6400 Arapahoe Rd Unit 4, Boulder, CO 80303",
    "oldmarket": "455 Walnut St, Fort Collins, CO 80524",
}
OLD_MARKET_OLD = "212 Walnut St, Fort Collins, CO 80524"
REMOTE_HOME = "2231 Clarkson St, Denver, CO 80205"
LOC_LABELS = {"pearl": ["Pearl St Taproom", "Pearl St", "Taproom - Pearl"], "brew": ["Brewhouse", "Production"],
              "office": ["Office"], "oldmarket": ["Old Market", "Old Market Taproom", "Ft Collins taproom"]}
HOURLY_JOBS = [("Bartender", "Taproom"), ("Server", "Taproom"), ("Barback", "Taproom"), ("Line Cook", "Kitchen"),
               ("Cellar Operator", "Production"), ("Canning Line Operator", "Production"), ("Packaging Tech", "Production"),
               ("Dishwasher", "Kitchen"), ("Host", "Taproom"), ("Delivery Driver", "Distribution")]
SALARY_JOBS = [("Head Brewer", "Production", "brew"), ("Taproom Manager", "Taproom", None), ("Kitchen Manager", "Kitchen", None),
               ("Quality Lab Lead", "Production", "brew"), ("Bookkeeper", "Admin", "office"), ("Events Coordinator", "Taproom", None),
               ("Marketing Manager", "Admin", "office"), ("Assistant Brewer", "Production", "brew")]
SSN_STYLES = ["XXX-XX-{d}", "***-**-{d}", "{d}", "xxx-xx-{d}"]


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = people(r, 39)
    emps = []
    used = set()
    for k, (f, l) in enumerate(ppl):
        em = email_for(r, f, l)
        while em in used:
            em = email_for(r, f, l)
        used.add(em)
        e = {"first": f, "last": l, "email": em, "ssn4": f"{r.randint(0, 9999):04d}", "tags": set(),
             "status": "Active", "worker": "W-2", "rehire": None, "notes": ""}
        e["hire"] = day_in(r, date(2016, 3, 1), date(2026, 7, 31))
        emps.append(e)
    # roles: 9 salaried, the rest hourly; indexes chosen so every trap is present for every seed
    salaried = emps[:9]
    hourly = emps[9:]
    sal_units = ["year", "year", "year", "year", "biweekly", "biweekly", "monthly", "year", "biweekly"]
    exempt = [True, True, False, True, True, False, True, True, True]
    for k, e in enumerate(salaried):
        title, dept, loc = SALARY_JOBS[k % len(SALARY_JOBS)] if k < len(SALARY_JOBS) else ("Sales Rep", "Sales", "remote")
        if k == 8:
            title, dept, loc = "Sales Rep", "Sales", "remote"
        e.update(title=title, dept=dept, loc=loc or r.choice(["pearl", "oldmarket"]), pay="Salary", exempt=exempt[k], unit=sal_units[k])
        if e["unit"] == "biweekly":
            per_check = r.randint(1900, 2700) + r.choice([0.0, 0.5])
            e["raw_rate"] = per_check; e["annual"] = round(per_check * 26, 2)
            e["tags"].add("per_paycheck")
        elif e["unit"] == "monthly":
            per_month = float(r.randint(38, 60) * 125)
            e["raw_rate"] = per_month; e["annual"] = round(per_month * 12, 2)
            e["tags"].add("per_month")
        else:
            annual = float(r.randint(48, 88) * 1000)
            e["raw_rate"] = annual; e["annual"] = annual
        if not e["exempt"]:
            e["tags"].add("ot_eligible")
    for e in hourly:
        title, dept = r.choice(HOURLY_JOBS)
        loc = "brew" if dept in ("Production", "Distribution") else r.choice(["pearl", "pearl", "oldmarket"])
        e.update(title=title, dept=dept, loc=loc, pay="Hourly", exempt=None, unit="hour")
        e["raw_rate"] = r.randint(62, 112) * 0.25
    # remote rep
    rep = salaried[8]
    rep["notes"] = f"Fully remote. Works from home: {REMOTE_HOME}"
    rep["tags"].add("remote")
    # blank Pay Type on three hourly rows and one annual salaried row
    for e in r.sample(hourly[:-7], 3) + [salaried[3]]:
        e["tags"].add("blank_paytype")
    # rehires
    for e in r.sample(hourly[:12], 2):
        e["hire"] = day_in(r, date(2017, 1, 1), date(2021, 12, 31))
        e["rehire"] = day_in(r, date(2025, 3, 1), date(2026, 6, 30), weekday_only=True)
        e["tags"].add("rehire")
        e["notes"] = r.choice(["Rehired after two seasons away", "Came back 2025", "Rehire - see old file"])
    # leavers and contractors (from the tail of hourly so salaried trap rows stay in)
    tail = hourly[-7:]
    for e in tail[:4]:
        e["status"] = r.choice(["Terminated", "Term", "Terminated"])
        e["tags"].add("excluded")
        e["notes"] = r.choice(["Last day 07/31/2026", "Moved to Portland", "Seasonal - did not return", "Resigned"])
    for e in tail[4:]:
        e["worker"] = r.choice(["1099", "Contractor"])
        e["tags"].add("excluded")
        e["title"] = r.choice(["Label Designer", "Draft Line Cleaning", "Sign Painter"])
        e["dept"] = "Contract"
        e["pay"] = "Hourly"
        e["raw_rate"] = float(r.randint(40, 85))
        e["notes"] = "Paid on invoice"
    for e in r.sample([e for e in hourly[:-7] if "rehire" not in e["tags"]], 2):
        e["status"] = r.choice(["On leave", "LOA"])
        e["tags"].add("on_leave")
    # at least four kept staff at Old Market
    kept_hourly = [e for e in hourly[:-7]]
    n_old = sum(1 for e in emps if e["loc"] == "oldmarket" and "excluded" not in e["tags"])
    for e in [e for e in kept_hourly if e["loc"] == "pearl"][: max(0, 4 - n_old)]:
        e["loc"] = "oldmarket"
    for e in emps:
        if "excluded" in e["tags"]:
            continue
        if e["loc"] == "oldmarket":
            e["tags"].add("old_market")
        if e["loc"] == "office":
            e["tags"].add("office")
    # date renderings: most real dates, a third text in three formats
    for e in emps:
        k = r.random()
        e["hire_style"] = "date" if k < 0.62 else r.choice(["us", "iso", "long"])
        if e["hire_style"] != "date" and "excluded" not in e["tags"]:
            e["tags"].add("text_date")
    return {"emps": emps}


def render_date(d: date | None, style: str):
    if d is None:
        return ""
    if style == "date":
        return d
    return {"us": f"{d.month}/{d.day}/{d.year}", "iso": d.isoformat(), "long": f"{d:%B} {d.day}, {d.year}"}[style]


def roster_rows(r, emps):
    rows = []
    for k, e in enumerate(emps):
        loc_label = "Remote (see notes)" if e["loc"] == "remote" else r.choice(LOC_LABELS[e["loc"]])
        pay_type = "" if "blank_paytype" in e["tags"] else (r.choice(["Hourly", "H", "hourly"]) if e["pay"] == "Hourly" else r.choice(["Salary", "S", "Salaried"]))
        per = {"hour": r.choice(["hr", "/hr", "hour"]), "year": r.choice(["yr", "annual", "year"]), "biweekly": "biweekly",
               "monthly": r.choice(["monthly", "mo"])}[e["unit"]]
        if e["pay"] == "Hourly":
            rate = r.choice([f"${e['raw_rate']:.2f}", f"{e['raw_rate']:g}", f"{e['raw_rate']:.2f}"])
        else:
            rate = r.choice([f"${e['raw_rate']:,.2f}", f"{e['raw_rate']:,.2f}", f"{e['raw_rate']:.2f}"])
        ot = "" if e["pay"] == "Hourly" else ("Y" if e["exempt"] else "N")
        rehire = e["rehire"] if e["rehire"] else ""
        ssn = SSN_STYLES[k % len(SSN_STYLES)].format(d=e["ssn4"])
        rows.append([f"TB-{101 + k}", name_noise(r, e["first"]).strip(), e["last"], e["email"] if r.random() < 0.7 else e["email"].capitalize(),
                     ssn, render_date(e["hire"], e["hire_style"]), rehire, e["status"], e["worker"], e["title"], e["dept"], loc_label,
                     pay_type, rate, per, ot, e["notes"]])
    return rows


def expected_row(e):
    start = e["rehire"] or e["hire"]
    addr = REMOTE_HOME if e["loc"] == "remote" else ADDR["brew" if e["loc"] in ("brew", "office") else e["loc"]]
    if e["pay"] == "Hourly":
        etype, rate, unit = "Paid by the hour", f"{e['raw_rate']:.2f}", "Hour"
    else:
        etype = "Salary/No overtime" if e["exempt"] else "Salary/Eligible for overtime"
        rate, unit = f"{e['annual']:.2f}", "Year"
    return [e["first"], e["last"], e["email"], "", start.strftime("%m/%d/%Y"), addr, e["title"], e["dept"], etype, rate, unit]


def emit(seed: int) -> None:
    d = build(seed)
    emps = d["emps"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 7)
    order = list(range(len(emps)))
    r.shuffle(order)
    shuffled = [emps[i] for i in order]
    write_xlsx(os.path.join(ws, "HR_master_roster.xlsx"), {"Roster": {
        "merged_title": "Tamarack Brewing - staff roster (HR master)",
        "preamble": [["Last updated 9/8/2026 by Dana", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "Do not email this file"]],
        "header": ["Emp #", "First", "Last", "Personal Email", "SSN (last 4)", "Hire Date", "Rehire Date", "Status", "Worker Type",
                   "Position", "Dept", "Location", "Pay Type", "Rate", "Per", "OT Exempt", "Notes"],
        "rows": roster_rows(r, shuffled), "widths": {"D": 32, "E": 14, "F": 16, "G": 14, "J": 22, "L": 20, "Q": 44}, "freeze": "A4"}},
        creator="Tamarack Office")
    write_csv(os.path.join(ws, "gusto_employee_upload_template.csv"), TEMPLATE,
              [["Jane", "Example", "jane.example@gmail.com", "", "04/06/2026", ADDR["pearl"], "Server", "Taproom", "Paid by the hour", "16.50", "Hour"]])
    write_email_thread(os.path.join(ws, "email_from_dana.txt"), [
        {"from": "Gusto Onboarding <onboarding@gusto-partners.example>", "to": "Dana Morgan <dana@tamarackbrewing.com>",
         "date": "Thu, 3 Sep 2026 10:02", "subject": "Your employee upload file",
         "body": ("Hi Dana,\n\nWhen you are ready to bring your team over, use the upload template attached (one row per employee, "
                  "same columns in the same order, keep the header row, delete our sample row).\n\n"
                  "A few things that trip people up:\n"
                  "- Start Date is MM/DD/YYYY. It is the date the person started this current stretch of employment, so for a rehire "
                  "it is the rehire date, not the original hire date.\n"
                  "- Employee Type must be exactly one of these three values:\n    Paid by the hour\n    Salary/No overtime\n    Salary/Eligible for overtime\n"
                  "- Rate is a plain number. Hourly employees get their hourly rate with Payment Unit Hour. Salaried employees get "
                  "their annual salary with Payment Unit Year, even if you think of their pay per paycheck or per month.\n"
                  "- SSN: only fill it in if you have the full nine digits. A partial or masked number fails validation and "
                  "blocks the whole upload. Leave it blank and each employee enters it themselves during onboarding.\n"
                  "- Work Address has to match one of your company work addresses in Gusto character for character. For anyone "
                  "who works fully remote, Gusto needs their home address as the work address instead.\n"
                  "- Contractors are added separately in the Contractors section, so do not include them here, and only "
                  "include people you are still paying (people on leave count).\n\nThanks,\nThe Gusto onboarding team")},
        {"from": "Dana Morgan <dana@tamarackbrewing.com>", "to": "you", "date": "Mon, 8 Sep 2026 16:40",
         "subject": "FW: Your employee upload file",
         "body": ("Can you build the Gusto upload from my roster? A few things only I know:\n\n"
                  "Our work addresses as they are set up in Gusto:\n"
                  f"  Pearl Street taproom   {ADDR['pearl']}\n"
                  f"  Brewhouse              {ADDR['brew']}\n"
                  f"  Old Market taproom     {ADDR['oldmarket']}\n"
                  f"Gusto still lists {OLD_MARKET_OLD} too but that is the old Old Market space we left in March, it is marked "
                  "inactive, do not use it.\n\n"
                  "Office people sit at the brewhouse. Production and delivery are brewhouse too.\n"
                  "On the roster, OT Exempt = Y means the salaried person does not get overtime, N means they do. Pay Type is blank "
                  "on a few rows where I never filled it in; the Per column tells you how they are paid.\n\n"
                  "Dana")}])
    header = TEMPLATE
    keep = sorted([e for e in emps if "excluded" not in e["tags"]], key=lambda e: (e["last"], e["first"]))
    rows = [expected_row(e) for e in keep]
    write_csv(os.path.join(ref, "gusto_employees.csv"), header, rows)
    write_csv(os.path.join(sol, "gusto_employees.csv"), header, rows)

    def keys(*tags):
        return sorted(e["email"] for e in keep if any(t in e["tags"] for t in tags))
    pay_keys = keys("per_paycheck", "per_month", "blank_paytype", "ot_eligible")
    date_keys = keys("rehire", "text_date")
    addr_keys = keys("old_market", "remote", "office")
    write_json(os.path.join(ref, "notes.json"), {
        "excluded_emails": sorted(e["email"] for e in emps if "excluded" in e["tags"]),
        "on_leave": keys("on_leave"), "rehires": keys("rehire"), "per_paycheck": keys("per_paycheck"), "per_month": keys("per_month"),
        "blank_paytype": keys("blank_paytype"), "ot_eligible": keys("ot_eligible"), "remote": keys("remote")})
    write_task_yaml(HERE, {
        "id": "gusto-employee-import", "track": "desk", "category": "reformatting",
        "title": "Build the Gusto employee upload from the HR roster",
        "ask": ("We're moving payroll to Gusto. Can you turn my HR roster into their employee upload using the template in the "
                "folder? Dana forwarded what Gusto told us and added our addresses. Save it as gusto_employees.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the roster's SSN column holds masked last-four values (XXX-XX-1234, ***-**-1234, 1234, xxx-xx-1234); Gusto rejects partial numbers so the column must stay blank (check: SSN left blank)",
            "salaried pay is written per year, per month or per biweekly paycheck and Gusto wants the annual salary with Payment Unit Year; copying the roster figure leaves four salaries at a paycheck or monthly amount (check: rate)",
            "Pay Type is blank on four rows where the Per column decides, and salaried staff split into Salary/No overtime or Salary/Eligible for overtime by the OT Exempt column (check: employee type and payment unit)",
            "two rehires must start on the Rehire Date, and hire dates arrive as real dates plus three text formats that must become MM/DD/YYYY (check: start date)",
            "Location holds short names; Old Market must use the new Walnut St address, not the inactive one, Office maps to the brewhouse, and the remote sales rep's work address is the home address in Notes (check: work address)",
            "four terminated staff and three 1099 contractors sit on the same sheet and stay out, while two people on leave stay in; the sheet also has a merged title and a note row above the header (checks: one row per employee; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Gusto template columns, exact order", "path": "gusto_employees.csv", "columns": header, "exact": True},
            {"type": "csv_set_equal", "name": "one row per employee", "path": "gusto_employees.csv", "column": "Personal Email",
             "ref": "gusto_employees.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "gusto_employees.csv", "equals_ref": "gusto_employees.csv"},
            {"type": "csv_values_match", "name": "SSN left blank", "path": "gusto_employees.csv", "ref": "gusto_employees.csv",
             "key": "Personal Email", "columns": ["SSN"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "employee type and payment unit", "path": "gusto_employees.csv", "ref": "gusto_employees.csv",
             "key": "Personal Email", "columns": ["Employee Type", "Payment Unit"], "min_accuracy": 1.0, "must_match_keys": pay_keys},
            {"type": "csv_values_match", "name": "rate", "path": "gusto_employees.csv", "ref": "gusto_employees.csv",
             "key": "Personal Email", "columns": ["Rate"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": pay_keys},
            {"type": "csv_values_match", "name": "start date", "path": "gusto_employees.csv", "ref": "gusto_employees.csv",
             "key": "Personal Email", "columns": ["Start Date"], "min_accuracy": 1.0, "must_match_keys": date_keys},
            {"type": "csv_values_match", "name": "work address", "path": "gusto_employees.csv", "ref": "gusto_employees.csv",
             "key": "Personal Email", "columns": ["Work Address"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": addr_keys},
        ],
    })
    print(f"seed={seed}: {len(emps)} roster rows, {len(keep)} in upload; pay traps {len(pay_keys)}, date traps {len(date_keys)}, address traps {len(addr_keys)}")


if __name__ == "__main__":
    emit(argparse_seed())
