#!/usr/bin/env python3
"""expense-report-audit: an environmental consultancy's August expense reports checked against its travel policy.

    python gen.py [--seed N] [--naive DIR]

Business: Fernwood Environmental Services sends field technicians to sample soil and groundwater at client sites
around the inland Northwest. Expense reports come out of the expense tool as one line per expense; the approved
trip log lives in a separate workbook; the policy has numbered sections. The controller wants every line in the
reports awaiting approval that breaks the policy, with the section and the amount not to pay.

Traps (each caught by a check, see task.yaml):
  * the per diem rate depends on the trip's destination tier; a Tier A rate claimed for a standard city is over by
    the difference, not wholly disallowed                                        (checks: amount disallowed; flagged lines)
  * a day trip earns no per diem, and a per diem the day after an approved trip ends is outside the trip
                                                                                   (checks: flagged lines; policy section)
  * meal receipts on a day the same person claims per diem are not paid; meals on a day trip or a local client
    lunch are                                                                     (checks: flagged lines; policy section)
  * the receipt threshold is $75.00 or more: exactly $75.00 without a receipt fails, $74.99 passes, and per diem
    lines never need one                                                          (checks: flagged lines; row count)
  * lodging above the nightly cap loses the excess only; the cap depends on the tier (check: amount disallowed)
  * a hotel night already paid on a July report and a rental car already claimed on the employee's first August
    report are submitted again; two colleagues sharing a hotel on the same night are not duplicates
                                                                                   (checks: flagged lines; amount disallowed)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, timedelta
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

D = Decimal
TIER_A = ["Seattle", "Portland", "Denver", "Salt Lake City"]
STANDARD = ["Twin Falls", "Pocatello", "Missoula", "Elko", "Bend", "Lewiston", "Idaho Falls"]
PER_DIEM = {"A": D("79.00"), "S": D("61.00")}
LODGING_CAP = {"A": D("245.00"), "S": D("165.00")}
HOTELS = {"A": ["Hyatt Place", "Residence Inn", "Hotel Indigo", "Courtyard"], "S": ["Hampton Inn", "Best Western Plus", "La Quinta", "Holiday Inn Express"]}
STAFF = ["Rebecca Alvarez", "Tomasz Nguyen", "Amara Collins", "Luis Bennett", "Chloe Haddad", "Kwame Foster"]


def cents(r, lo, hi) -> Decimal:
    return D(r.randint(int(lo * 100), int(hi * 100))) / 100


def tier(city: str) -> str:
    return "A" if city in TIER_A else "S"


def build(seed: int) -> dict:
    r = rng(seed)
    staff = r.sample(STAFF, 5)
    line_seq = [r.randint(58000, 58300)]
    lines, trips = [], []
    flags = {}   # line_id -> (section, amount, role)

    def lid():
        line_seq[0] += r.randint(1, 4)
        return f"EXL-{line_seq[0]}"

    def add(emp, rep, when, cat, merchant, city, amount, receipt, memo, role=None, section=None, disallow=None):
        ln = {"id": lid(), "emp": emp, "rep": rep, "date": when, "cat": cat, "merchant": merchant, "city": city, "amount": amount,
              "receipt": receipt, "memo": memo}
        lines.append(ln)
        if section:
            flags[ln["id"]] = (section, disallow, role)
        return ln

    reports = {}

    def report(emp, name, submitted, status):
        rid = f"ER-{r.randint(2100, 2999)}"
        while rid in reports:
            rid = f"ER-{r.randint(2100, 2999)}"
        reports[rid] = {"id": rid, "emp": emp, "name": name, "submitted": submitted, "status": status}
        return rid

    def trip(emp, city, dep, ret, purpose):
        t = {"no": f"T-26-{len(trips) + 71:03d}", "emp": emp, "city": city, "dep": dep, "ret": ret, "purpose": purpose}
        trips.append(t)
        return t

    def overnight(emp, rep, t, skip_pd=(), meal_days=(), hotel=None, hotel_rate=None):
        tr = tier(t["city"])
        hotel = hotel or r.choice(HOTELS[tr])
        d = t["dep"]
        while d <= t["ret"]:
            if d not in skip_pd:
                add(emp, rep, d, "Per diem", "Per diem - M&IE", t["city"], PER_DIEM[tr], "No", f"{t['no']} per diem")
            if d < t["ret"]:
                rate = hotel_rate if hotel_rate is not None else cents(r, 118, 158) if tr == "S" else cents(r, 188, 236)
                add(emp, rep, d, "Lodging", f"{hotel} {t['city']}", t["city"], rate, "Yes", f"{t['no']} night of {d.strftime('%m/%d')}")
            d += timedelta(days=1)
        return hotel

    purposes = ["Groundwater sampling - monitoring wells", "Phase II soil borings", "Stormwater inspection", "Tank closure sampling",
                "Vapor intrusion survey", "Wetland delineation"]
    e0, e1, e2, e3, e4 = staff

    # ---- July report of e0, already paid, with a hotel night that comes back in August
    jul_rep = report(e0, "July field work", date(2026, 7, 31), "Paid")
    tj = trip(e0, r.choice(STANDARD), date(2026, 7, r.randint(27, 28)), date(2026, 7, 30), r.choice(purposes))
    jul_hotel = overnight(e0, jul_rep, tj)
    jul_night = [l for l in lines if l["rep"] == jul_rep and l["cat"] == "Lodging"][-1]
    add(e0, jul_rep, tj["dep"], "Fuel", "Chevron", tj["city"], cents(r, 42, 70), "Yes", "Truck 14 fuel")

    # ---- e0 August: re-lists the July night (duplicate), plus a standard-city trip claimed at the Tier A rate
    rep0 = report(e0, "August 1-31", date(2026, 9, 2), "Submitted")
    dup = add(e0, rep0, jul_night["date"], "Lodging", jul_night["merchant"], jul_night["city"], jul_night["amount"], "Yes",
              f"{tj['no']} hotel (missed on last report)", role="dup_prior_report", section="5.1", disallow=jul_night["amount"])
    t0 = trip(e0, r.choice(STANDARD), date(2026, 8, r.randint(10, 12)), None, r.choice(purposes))
    t0["ret"] = t0["dep"] + timedelta(days=2)
    overnight(e0, rep0, t0, skip_pd=(t0["dep"] + timedelta(days=1),))
    wrong = add(e0, rep0, t0["dep"] + timedelta(days=1), "Per diem", "Per diem - M&IE", t0["city"], PER_DIEM["A"], "No", f"{t0['no']} per diem",
                role="tier_rate", section="2.1", disallow=PER_DIEM["A"] - PER_DIEM["S"])
    add(e0, rep0, t0["dep"], "Supplies", "Grainger", t0["city"], D("74.99"), "No", "Bailers and nitrile gloves")
    for k in range(3):   # daily site parking, same merchant and amount on different days: not duplicates
        add(e0, rep0, t0["dep"] + timedelta(days=k), "Parking", "City of " + t0["city"] + " parking", t0["city"], D("14.00"), "No", "Site parking")

    # ---- e1: two August reports; the second re-claims the rental car from the first; a meal on a per-diem day
    rep1a = report(e1, "Aug 1-15", date(2026, 8, 17), "Submitted")
    rep1b = report(e1, "Aug 16-31", date(2026, 9, 1), "Submitted")
    t1 = trip(e1, r.choice(TIER_A), date(2026, 8, r.randint(3, 5)), None, r.choice(purposes))
    t1["ret"] = t1["dep"] + timedelta(days=3)
    overnight(e1, rep1a, t1)
    car_amt = cents(r, 212, 388)
    car = add(e1, rep1a, t1["ret"], "Car rental", "Enterprise Rent-A-Car", t1["city"], car_amt, "Yes", f"{t1['no']} 4-day rental")
    meal_pd = add(e1, rep1a, t1["dep"] + timedelta(days=1), "Meals", r.choice(["Rock Bottom Brewery", "Olive Garden", "Red Robin"]), t1["city"],
                  cents(r, 24, 58), "Yes", "Dinner", role="meal_on_per_diem", section="2.2", disallow=None)
    flags[meal_pd["id"]] = ("2.2", meal_pd["amount"], "meal_on_per_diem")
    t1b = trip(e1, r.choice(STANDARD), date(2026, 8, r.randint(18, 20)), None, r.choice(purposes))
    t1b["ret"] = t1b["dep"] + timedelta(days=2)
    overnight(e1, rep1b, t1b)
    add(e1, rep1b, car["date"], "Car rental", "Enterprise Rent-A-Car", car["city"], car_amt, "Yes", "Rental car - trip " + t1["no"],
        role="dup_earlier_august", section="5.1", disallow=car_amt)
    add(e1, rep1b, t1b["dep"], "Airfare", "Alaska Airlines", "Boise", cents(r, 186, 340), "No", "Flight to site",
        role="no_receipt_big", section="4.1", disallow=None)
    flags[lines[-1]["id"]] = ("4.1", lines[-1]["amount"], "no_receipt_big")

    # ---- e2 and e3 share a Tier A hotel on the same nights (not duplicates); e2 lodges at exactly the cap
    t2 = trip(e2, r.choice([c for c in TIER_A if c != t1["city"]]), date(2026, 8, r.randint(24, 25)), None, r.choice(purposes))
    t2["ret"] = t2["dep"] + timedelta(days=2)
    t3 = trip(e3, t2["city"], t2["dep"], t2["ret"], t2["purpose"])
    rep2 = report(e2, "August expenses", date(2026, 9, 3), "Submitted")
    rep3 = report(e3, "Aug 2026", date(2026, 9, 3), "Submitted")
    shared_hotel = r.choice(HOTELS["A"])
    overnight(e2, rep2, t2, hotel=shared_hotel, hotel_rate=LODGING_CAP["A"])
    overnight(e3, rep3, t3, hotel=shared_hotel, hotel_rate=LODGING_CAP["A"])
    # e3: an extra per diem the day after the trip ended, and the $75.00 line without a receipt
    after = add(e3, rep3, t3["ret"] + timedelta(days=1), "Per diem", "Per diem - M&IE", t3["city"], PER_DIEM["A"], "No", f"{t3['no']} per diem",
                role="per_diem_after_trip", section="2.1", disallow=PER_DIEM["A"])
    exact = add(e3, rep3, t3["dep"], "Supplies", "Home Depot", t3["city"], D("75.00"), "No", "Sample cooler and ice",
                role="receipt_exact_75", section="4.1", disallow=D("75.00"))
    add(e2, rep2, t2["dep"] - timedelta(days=r.randint(3, 6)), "Meals", "Local client lunch - Boise", "Boise", cents(r, 38, 72), "Yes",
        "Lunch with city engineer (not travel)")
    add(e2, rep2, date(2026, 8, r.randint(5, 12)), "Meals", "Bittercreek Alehouse", "Boise", cents(r, 44, 71), "Yes", "Client lunch - Ada County")

    # ---- e4: a day trip with a per diem, and a standard-city hotel above the cap
    rep4 = report(e4, "August field expenses", date(2026, 9, 1), "Submitted")
    dt = r.choice([date(2026, 8, k) for k in range(4, 8)])
    td = trip(e4, r.choice(STANDARD), dt, dt, "Day trip - " + r.choice(purposes))
    add(e4, rep4, dt, "Per diem", "Per diem - M&IE", td["city"], PER_DIEM["S"], "No", f"{td['no']} per diem",
        role="day_trip_per_diem", section="2.1", disallow=PER_DIEM["S"])
    add(e4, rep4, dt, "Fuel", "Pilot Travel Center", td["city"], cents(r, 44, 69), "Yes", "Truck 9 fuel - day trip")
    t4 = trip(e4, r.choice([c for c in STANDARD if c != td["city"]]), date(2026, 8, r.randint(17, 19)), None, r.choice(purposes))
    t4["ret"] = t4["dep"] + timedelta(days=3)
    hotel4 = overnight(e4, rep4, t4)
    over_night = [l for l in lines if l["rep"] == rep4 and l["cat"] == "Lodging"][1]
    over_night["amount"] = cents(r, 179, 214)
    over_night["memo"] += " (only room left - rodeo week)"
    flags[over_night["id"]] = ("3.1", over_night["amount"] - LODGING_CAP["S"], "lodging_over_cap")
    add(e4, rep4, t4["dep"], "Fuel", "Maverik", t4["city"], cents(r, 58, 73), "No", "Truck 9 fuel")

    # report numbers run with the submission date, as the expense tool issues them
    renum, n = {}, r.randint(2280, 2400)
    for rp in sorted(reports.values(), key=lambda x: (x["submitted"], x["emp"])):
        n += r.randint(3, 40)
        renum[rp["id"]] = f"ER-{n}"
    reports = {renum[k]: dict(v, id=renum[k]) for k, v in reports.items()}
    for l in lines:
        l["rep"] = renum[l["rep"]]
    lines.sort(key=lambda l: (reports[l["rep"]]["submitted"], l["rep"], l["date"], l["id"]))
    return {"staff": staff, "lines": lines, "trips": trips, "reports": reports, "flags": flags, "jul_rep": renum[jul_rep],
            "roles": {v[2]: k for k, v in flags.items()}}


def acceptable(d: dict) -> bool:
    ids = [l["id"] for l in d["lines"]]
    if len(set(ids)) != len(ids):
        return False
    seen = {}
    for l in d["lines"]:
        key = (l["emp"], l["date"], l["merchant"], l["amount"])
        if key in seen and l["id"] not in d["flags"]:
            return False
        seen.setdefault(key, l["id"])
        # no accidental receipt violations or caps
        if l["id"] not in d["flags"]:
            if l["cat"] != "Per diem" and l["amount"] >= 75 and l["receipt"] != "Yes":
                return False
            if l["cat"] == "Lodging" and l["amount"] > LODGING_CAP[tier(l["city"])]:
                return False
    pd_days = {(l["emp"], l["date"]) for l in d["lines"] if l["cat"] == "Per diem"}
    for l in d["lines"]:
        if l["cat"] == "Meals" and (l["emp"], l["date"]) in pd_days and l["id"] not in d["flags"]:
            return False
    return len(d["flags"]) == 9


def violations(d: dict) -> list[list]:
    by = {l["id"]: l for l in d["lines"]}
    out = []
    for lid_, (sec, amt, role) in sorted(d["flags"].items()):
        l = by[lid_]
        out.append([lid_, l["rep"], l["emp"], sec, f"{amt:.2f}", REASONS[role]])
    return out


REASONS = {
    "dup_prior_report": "Same hotel night was already paid on the July report",
    "tier_rate": "Per diem claimed at the Tier A rate for a standard-rate city",
    "meal_on_per_diem": "Meal receipt on a day per diem was claimed",
    "no_receipt_big": "No receipt for a line of $75.00 or more",
    "dup_earlier_august": "Rental car already claimed on the employee's first August report",
    "per_diem_after_trip": "Per diem claimed the day after the approved trip ended",
    "receipt_exact_75": "No receipt for a line of $75.00 or more",
    "day_trip_per_diem": "Per diem claimed on a day trip with no overnight stay",
    "lodging_over_cap": "Lodging above the nightly cap for a standard-rate city",
}


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["line_id", "report_id", "employee", "policy_section", "amount_disallowed", "reason"]
    if naive_dir:
        # receipts over 75 missing (per diem included), lodging over $165 anywhere, per diem over $61, duplicates within a report
        out, seen = [], set()
        for l in d["lines"]:
            if d["reports"][l["rep"]]["status"] != "Submitted":
                continue
            if l["amount"] > 75 and l["receipt"] == "No":
                out.append([l["id"], l["rep"], l["emp"], "4.1", f"{l['amount']:.2f}", "no receipt"])
            elif l["cat"] == "Lodging" and l["amount"] > 165:
                out.append([l["id"], l["rep"], l["emp"], "3.1", f"{l['amount'] - 165:.2f}", "over cap"])
            elif l["cat"] == "Per diem" and l["amount"] > 61:
                out.append([l["id"], l["rep"], l["emp"], "2.1", f"{l['amount'] - 61:.2f}", "over rate"])
            key = (l["rep"], l["date"], l["merchant"], l["amount"])
            if key in seen:
                out.append([l["id"], l["rep"], l["emp"], "5.1", f"{l['amount']:.2f}", "duplicate"])
            seen.add(key)
        write_csv(os.path.join(naive_dir, "violations.csv"), header, out)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 9)

    rows = []
    for l in d["lines"]:
        rp = d["reports"][l["rep"]]
        rows.append([rp["id"], rp["name"], l["emp"], rp["submitted"].strftime("%m/%d/%Y"), rp["status"], l["id"], l["date"].strftime("%m/%d/%Y"),
                     l["cat"], l["merchant"], l["city"], money_str(float(l["amount"]), r.choice([0, 1, 2])), l["receipt"], l["memo"]])
    write_csv(os.path.join(ws, "expensly_report_lines_2026-07-31_to_2026-09-04.csv"),
              ["Report ID", "Report Name", "Employee", "Submitted", "Report Status", "Line ID", "Expense Date", "Category", "Merchant",
               "City", "Amount", "Receipt Attached", "Memo"], rows, bom=True, crlf=True)

    trows = [[t["no"], t["emp"], t["city"], t["dep"], t["ret"], t["purpose"], "Approved"] for t in sorted(d["trips"], key=lambda t: t["no"])]
    extra = trows[:]
    unapproved_emp = d["staff"][3]
    extra.append([f"T-26-{len(trows) + 71:03d}", unapproved_emp, r.choice(STANDARD), date(2026, 9, 14), date(2026, 9, 16),
                  "Tank closure sampling", "Pending"])
    write_xlsx(os.path.join(ws, "approved_trips_jul-sep_2026.xlsx"), {"Trips": {
        "merged_title": "Field travel approvals - Q3 2026",
        "header": ["Trip #", "Employee", "Destination", "Depart", "Return", "Purpose", "Approval"], "rows": extra,
        "widths": {"B": 18, "C": 16, "D": 12, "E": 12, "F": 40}}}, creator="Operations")

    write_text(os.path.join(ws, "travel_and_expense_policy_2026.md"),
               "# Fernwood Environmental Services - Travel and Expense Policy\n\n_Effective 1 January 2026_\n\n"
               "## 1. Scope\n\n"
               "1.1 This policy covers expenses employees incur on company business. Field travel must be on the approved trip log before "
               "the trip starts; the log's depart and return dates define the trip.\n\n"
               "## 2. Meals and incidentals\n\n"
               "2.1 **Per diem.** On an approved trip with at least one overnight stay, employees may claim one per diem for each calendar day "
               "from the depart date to the return date, inclusive, at the rate for the trip's destination:\n\n"
               "| Destination | Per diem per day |\n|---|---|\n"
               f"| Tier A: {', '.join(TIER_A)} | $79.00 |\n| All other destinations | $61.00 |\n\n"
               "A trip that leaves and returns on the same day earns no per diem. A per diem claimed above the destination rate is paid at "
               "the rate.\n\n"
               "2.2 **Meals on per diem days.** The per diem covers every meal that day. Meal receipts dated on a day the same employee "
               "claims a per diem are not reimbursed.\n\n"
               "2.3 Business meals with clients and meals on day trips are reimbursed at cost with a receipt.\n\n"
               "## 3. Lodging\n\n"
               "3.1 Lodging is reimbursed per night up to a cap: $245.00 in Tier A destinations and $165.00 elsewhere. The part of a night "
               "above the cap is not reimbursed, whatever the reason.\n\n"
               "## 4. Receipts\n\n"
               "4.1 Every expense line of $75.00 or more needs an itemized receipt attached. A line without one is not reimbursed. Per diem "
               "lines do not need receipts.\n\n"
               "## 5. Duplicates\n\n"
               "5.1 An expense may be claimed once. When the same employee claims the same expense (same date, merchant and amount) on more "
               "than one report, the later submission is not reimbursed.\n")

    ctrl = "Ingrid Castillo"
    write_email_thread(os.path.join(ws, "email_from_ingrid.txt"), [
        {"from": f"{ctrl} <ingrid@fernwoodenv.com>", "to": "ap@fernwoodenv.com", "date": "Fri, 4 Sep 2026 15:12",
         "subject": "August expense reports - audit before we pay",
         "body": ("Before the reports go to payroll next week, please audit every report that is still waiting for approval against the "
                  "2026 policy (the July report is only in the export because it overlaps; it has already been paid).\n\n"
                  "I want violations.csv with one row for each expense line that breaks the policy: line_id, report_id, employee, the "
                  "policy_section it breaks (like 3.1), amount_disallowed (only the part we should not pay) and a short reason. Lines "
                  "that are fine stay off the list.\n\nIngrid")}])

    v = violations(d)
    for base in (ref, sol):
        write_csv(os.path.join(base, "violations.csv"), header, v)
    write_json(os.path.join(ref, "notes.json"), {"flags": {k: {"section": s, "amount": f"{a:.2f}", "role": role} for k, (s, a, role) in d["flags"].items()}})
    ro = d["roles"]
    write_task_yaml(HERE, {
        "id": "expense-report-audit", "track": "desk", "category": "bookkeeping",
        "title": "Audit August expense reports against the travel policy",
        "ask": "Please audit the expense reports waiting for approval before we pay them - Ingrid's email says what she needs, and the policy and trip log are in the folder. Save the list as violations.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"{ro['tier_rate']} claims the $79.00 Tier A per diem on a trip to a standard city; only the $18.00 above the $61.00 rate is "
            "disallowed, not the whole line (check: amount disallowed per line)",
            f"{ro['day_trip_per_diem']} is a per diem on a trip that left and returned the same day, and {ro['per_diem_after_trip']} is a "
            "per diem the day after an approved trip ended; neither is over any rate, so only the trip log shows them "
            "(checks: flagged lines; policy section per flagged line)",
            f"{ro['meal_on_per_diem']} is a dinner receipt on a day the same technician claimed per diem; two client lunches in Boise "
            "on days without a per diem are fine (checks: flagged lines; policy section per flagged line)",
            f"the receipt rule is $75.00 or more: {ro['receipt_exact_75']} at exactly $75.00 without a receipt fails, a $74.99 line passes, "
            "and every per diem line shows Receipt Attached = No but needs none (checks: flagged lines; row count)",
            f"{ro['lodging_over_cap']} is a standard-city hotel night above the $165.00 cap, which loses only the excess, while a Tier A "
            "night at exactly $245.00 and Tier A nights around $200 are within their cap (checks: amount disallowed per line; flagged lines)",
            f"{ro['dup_prior_report']} re-submits a hotel night already paid on the July report, and {ro['dup_earlier_august']} "
            "re-claims a rental car from the same employee's first August report; two colleagues at the same hotel on the same nights and "
            "daily site parking at the same amount are not duplicates (checks: flagged lines; amount disallowed per line)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "violations.csv",
             "columns": ["line_id", "report_id", "policy_section", "amount_disallowed"]},
            {"type": "csv_set_equal", "name": "flagged lines", "path": "violations.csv", "column": "line_id", "ref": "violations.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "violations.csv", "equals_ref": "violations.csv"},
            {"type": "csv_values_match", "name": "amount disallowed per line", "path": "violations.csv", "ref": "violations.csv",
             "key": "line_id", "columns": ["amount_disallowed"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [ro["tier_rate"], ro["lodging_over_cap"], ro["dup_prior_report"], ro["dup_earlier_august"]]},
            {"type": "custom", "name": "policy section per flagged line", "module": "check.py"},
        ],
    })
    print(f"seed={seed} lines={len(d['lines'])} flags={len(d['flags'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
