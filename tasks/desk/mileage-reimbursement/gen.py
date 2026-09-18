#!/usr/bin/env python3
"""mileage-reimbursement: a home health agency's August driving logs to what each clinician is owed.

    python gen.py [--seed N] [--naive DIR]

Business: Brightside Home Health sends nurses, aides and therapists to patients' homes. Most log trips in a mileage
app; one therapist keeps an odometer sheet. The controller's emails carry the policy: the 2026 rate, personal trips
out, driving between home and the office is commuting, the first business leg out of home and the last one back
lose the clinician's one-way commute (never below zero), and a round-trip line is two legs.

Traps (each caught by a check, see task.yaml):
  * personal errands are in the same log                                          (check: reimbursement per person)
  * home-to-office legs are commuting, and the first and last home legs of a work
    day lose the commute distance, floored at zero                               (checks: miles; reimbursement)
  * round-trip lines hold the one-way distance                                    (check: reimbursement per person)
  * one therapist logs odometer readings in a workbook, not the app                (checks: one row per clinician; reimbursement)
  * the older email carries last year's rate                                      (check: reimbursement per person)
  * the app export runs from late July into September                             (check: reimbursable miles)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

RATE = Decimal("0.725")
OLD_RATE = Decimal("0.70")
ROLES = ["RN", "RN", "LPN", "HHA", "RN", "PT", "HHA", "LPN", "OT"]
STOPS = ["Medline supply depot", "Quest lab - Elm Dr", "Walgreens #3310", "CVS Pharmacy - Main St"]
ERRANDS = ["Target", "Kroger", "Planet Fitness", "Kids' school", "Costco", "Dentist"]


def cents(miles_tenths: int, rate: Decimal) -> int:
    return int((Decimal(miles_tenths) / 10 * rate * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, len(ROLES))
    staff = []
    for i, ((f, l), role) in enumerate(zip(names, ROLES)):
        staff.append({"id": f"BH-{r.randint(100, 999)}", "first": f, "last": l, "name": f"{f} {l}", "role": role,
                      "commute": r.randint(45, 150), "trips": [], "kind": "plain"})
    ids = set()
    for s in staff:
        while s["id"] in ids:
            s["id"] = f"BH-{r.randint(100, 999)}"
        ids.add(s["id"])
    personal, commuter, roundtrip, odometer = staff[0], staff[1], staff[2], staff[5]
    personal["kind"], commuter["kind"], roundtrip["kind"], odometer["kind"] = "personal", "commuter", "roundtrip", "odometer"
    commuter["commute"] = r.randint(160, 210)

    days = [date(2026, 7, 27) + timedelta(days=k) for k in range(40)]  # 27 Jul .. 4 Sep
    patients = [f"Pt {r.randint(1000, 9999)}" for _ in range(60)]

    def leg(lo, hi):
        return r.randint(lo, hi)

    def stamp(trips, start_min):
        t = start_min
        for tr in trips:
            tr["time"] = t
            drive = max(4, tr["miles"] * 2 // 10)
            t += drive * (2 if tr["rt"] else 1) + (10 if tr["rt"] else 0) + r.randint(35, 70)

    for s in staff:
        c = s["commute"]
        pool = r.sample(patients, 14)
        for d in days:
            if d.weekday() >= 5:
                wk = []
                if s is roundtrip and d.weekday() == 5 and 8 <= d.day <= 29 and d.month == 8 and r.random() < 0.6:
                    wk.append({"date": d, "from": "Home", "to": r.choice(pool), "purpose": "Patient visit",
                               "miles": leg(c + 20, c + 90), "rt": True})
                if s["kind"] in ("personal", "odometer") and r.random() < 0.5:
                    e = r.choice(ERRANDS); m = leg(20, 140)
                    wk += [{"date": d, "from": "Home", "to": e, "purpose": "Personal", "miles": m, "rt": False},
                           {"date": d, "from": e, "to": "Home", "purpose": "Personal", "miles": m + r.randint(-5, 5), "rt": False}]
                stamp(wk, 9 * 60 + r.randint(0, 90))
                s["trips"] += wk
                continue
            if r.random() < 0.12:
                continue  # day off
            k = r.randint(2, 5)
            visits = r.sample(pool, k)
            pattern = r.random()
            seq = []
            if pattern < 0.2:
                seq.append(("Home", "Office", "Team meeting", c))
                seq.append(("Office", visits[0], "Patient visit", leg(25, 140)))
            else:
                near = s is commuter and r.random() < 0.6
                seq.append(("Home", visits[0], "Patient visit", leg(20, c - 20) if near else leg(30, 220)))
            for a, b in zip(visits, visits[1:]):
                seq.append((a, b, "Patient visit", leg(18, 160)))
            if pattern > 0.85:
                seq.append((visits[-1], "Office", "Charting / drop paperwork", leg(25, 140)))
                seq.append(("Office", "Home", "Drive home", c))
            else:
                near = s is commuter and r.random() < 0.6
                seq.append((visits[-1], "Home", "Drive home", leg(20, c - 20) if near else leg(30, 220)))
            trips = [{"date": d, "from": a, "to": b, "purpose": p, "miles": m, "rt": False} for a, b, p, m in seq]
            if s is not odometer and (s is roundtrip or r.random() < 0.15):
                j = r.randint(1, len(trips) - 1)
                stop = r.choice(STOPS)
                trips.insert(j, {"date": d, "from": trips[j]["from"], "to": stop, "purpose": "Supply pickup",
                                 "miles": leg(25, 110), "rt": True})
            if s is personal and r.random() < 0.3:
                e = r.choice(ERRANDS); m = leg(15, 90)
                trips += [{"date": d, "from": "Home", "to": e, "purpose": "Personal", "miles": m, "rt": False},
                          {"date": d, "from": e, "to": "Home", "purpose": "Personal", "miles": m, "rt": False}]
            stamp(trips, 7 * 60 + 20 + r.randint(0, 70))
            s["trips"] += trips

    # ---- truth: reimbursable tenths of a mile per clinician, August only
    for s in staff:
        c = s["commute"]
        total = 0
        by_day = {}
        for t in s["trips"]:
            by_day.setdefault(t["date"], []).append(t)
        for d, trips in by_day.items():
            if d.month != 8:
                continue
            biz = [t for t in trips if t["purpose"] != "Personal"]
            legs = []  # (from, to, miles) with round trips expanded
            for t in biz:
                legs.append((t["from"], t["to"], t["miles"]))
                if t["rt"]:
                    legs.append((t["to"], t["from"], t["miles"]))
            out_i = next((i for i, lg in enumerate(legs) if lg[0] == "Home"), None)
            in_i = max((i for i, lg in enumerate(legs) if lg[1] == "Home"), default=None)
            for i, (a, b, m) in enumerate(legs):
                if {a, b} == {"Home", "Office"}:
                    continue
                if i in (out_i, in_i):
                    m = max(0, m - c)
                total += m
        s["miles"] = total
        s["pay"] = cents(total, RATE)
    return {"staff": staff, "by_kind": {s["kind"]: s for s in staff if s["kind"] != "plain"}}


def naive(d: dict) -> dict:
    """Every August line's miles as logged (odometer differences for the paper log), times the rate."""
    out = {}
    for s in d["staff"]:
        tot = sum(t["miles"] for t in s["trips"] if t["date"].month == 8)
        out[s["id"]] = (tot, cents(tot, RATE))
    return out


def no_floor_miles(s: dict) -> int:
    total = 0
    by_day = {}
    for t in s["trips"]:
        by_day.setdefault(t["date"], []).append(t)
    for dd, trips in by_day.items():
        if dd.month != 8:
            continue
        legs = []
        for t in trips:
            if t["purpose"] == "Personal":
                continue
            legs.append((t["from"], t["to"], t["miles"]))
            if t["rt"]:
                legs.append((t["to"], t["from"], t["miles"]))
        out_i = next((i for i, lg in enumerate(legs) if lg[0] == "Home"), None)
        in_i = max((i for i, lg in enumerate(legs) if lg[1] == "Home"), default=None)
        for i, (a, b, m) in enumerate(legs):
            if {a, b} == {"Home", "Office"}:
                continue
            total += m - s["commute"] if i in (out_i, in_i) else m
    return total


def acceptable(d: dict) -> bool:
    nv = naive(d)
    for s in d["staff"]:
        if s["miles"] <= 0 or abs(nv[s["id"]][1] - s["pay"]) < 100:
            return False
    com = d["by_kind"]["commuter"]
    if com["miles"] - no_floor_miles(com) < 100:
        return False
    rt = d["by_kind"]["roundtrip"]
    if sum(1 for t in rt["trips"] if t["rt"] and t["from"] == "Home" and t["date"].month == 8) < 1:
        return False
    per = d["by_kind"]["personal"]
    if sum(t["miles"] for t in per["trips"] if t["purpose"] == "Personal" and t["date"].month == 8) < 200:
        return False
    if len({s["pay"] for s in d["staff"]}) != len(d["staff"]):
        return False
    return True


# --------------------------------------------------------------------------- emit

def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["employee_id", "employee", "reimbursable_miles", "reimbursement"]
    if naive_dir:
        nv = naive(d)
        os.makedirs(naive_dir, exist_ok=True)
        write_csv(os.path.join(naive_dir, "reimbursement.csv"), header,
                  [[s["id"], s["name"], f"{nv[s['id']][0] / 10:.1f}", f"{nv[s['id']][1] / 100:.2f}"] for s in d["staff"] if s["kind"] != "odometer"])
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 3)
    k = d["by_kind"]
    odo = k["odometer"]

    # ---- workspace: staff sheet
    write_xlsx(os.path.join(ws, "field_staff.xlsx"), {"Staff": {
        "header": ["Employee ID", "Name", "Role", "Home to office (miles, one way)", "Logs mileage in"],
        "rows": [[s["id"], f"{s['last']}, {s['first']}", s["role"], s["commute"] / 10, "Paper odometer sheet" if s is odo else "MileTrack app"]
                 for s in sorted(d["staff"], key=lambda s: s["last"])],
        "widths": {"B": 22, "D": 30, "E": 22}}}, creator="HR")

    # ---- workspace: app export (everyone but the odometer logger)
    rows = []
    for s in d["staff"]:
        if s is odo:
            continue
        for t in s["trips"]:
            hh, mm = divmod(t["time"], 60)
            clock = f"{(hh - 1) % 12 + 1}:{mm:02d} {'AM' if hh < 12 else 'PM'}"
            rows.append([t["date"], clock, s["name"] if r.random() < 0.85 else s["name"].upper(), t["from"], t["to"], t["purpose"],
                         f"{t['miles'] / 10:.1f}", "Yes" if t["rt"] else "", t["time"]])
    rows.sort(key=lambda x: (x[0], x[2].lower(), x[8]))
    write_csv(os.path.join(ws, "miletrack_export.csv"), ["Trip date", "Start time", "Driver", "From", "To", "Purpose", "Miles", "Round trip"],
              [[x[0].strftime("%m/%d/%Y")] + x[1:8] for x in rows],
              preamble=["MileTrack - Trips export", "Account: Brightside Home Health | Range: 07/27/2026 - 09/04/2026"], bom=True)

    # ---- workspace: odometer sheet for one therapist
    odo_rows = []
    reading = r.randint(41200, 68800) * 10
    for t in sorted(odo["trips"], key=lambda t: t["date"]):
        if t["rt"]:
            raise AssertionError("odometer logger has no round-trip lines")
        start = reading
        end = start + t["miles"]
        odo_rows.append([t["date"], t["from"], t["to"], t["purpose"], start / 10, end / 10])
        reading = end + (r.randint(0, 60) if r.random() < 0.3 else 0)
    write_xlsx(os.path.join(ws, f"odometer_log_{odo['last'].lower()}_jul-sep.xlsx"), {"Log": {
        "merged_title": f"{odo['name']} - vehicle log (2019 Subaru Outback)",
        "header": ["Date", "From", "To", "Purpose", "Odometer start", "Odometer end"], "rows": odo_rows,
        "number_formats": {"E": "0.0", "F": "0.0"}, "widths": {"B": 24, "C": 24, "D": 26}}}, creator=odo["name"])

    # ---- workspace: the controller's emails
    write_email_thread(os.path.join(ws, "mileage_policy_emails.txt"), [
        {"from": "Denise Park <dpark@brightsidehomehealth.org>", "to": "Field staff <field@brightsidehomehealth.org>",
         "date": "Mon, 6 Jan 2025 08:05", "subject": "Mileage rate for 2025",
         "body": "Hi all,\n\nFor 2025 we reimburse business driving at 70 cents a mile. Keep logging every trip in MileTrack.\n\nDenise"},
        {"from": "Denise Park <dpark@brightsidehomehealth.org>", "to": "Field staff <field@brightsidehomehealth.org>",
         "date": "Tue, 16 Dec 2025 15:30", "subject": "Mileage reimbursement from January 1, 2026",
         "body": ("Hi all,\n\nStarting January 1, 2026 the rate goes up to 72.5 cents a mile. A few reminders, because the auditors asked us "
                  "to apply the policy exactly:\n\n"
                  "- Personal trips are not reimbursed and are ignored for everything below.\n"
                  "- Driving between home and the office is commuting and is not reimbursed.\n"
                  "- Each day, your first business trip out of home and your last business trip back home each have your normal "
                  "one-way commute taken off them, never below zero (unless that trip is to or from the office, which is commuting "
                  "and pays nothing). Your commute distance is on the HR staff sheet.\n"
                  "- A trip marked round trip is two legs, out and back, each at the distance on the line. If a round trip starts at "
                  "home, the way out is your first trip out of home and the way back is your last trip home.\n"
                  "- Everything else (patient to patient, office to patient, supply runs) is reimbursed in full.\n\n"
                  "Denise")},
        {"from": "Denise Park <dpark@brightsidehomehealth.org>", "to": "you", "date": "Fri, 4 Sep 2026 17:10",
         "subject": "August mileage",
         "body": (f"Can you run August mileage for payroll? MileTrack exported a bit wide, I only want August trips. {odo['first']} still "
                  "logs on an odometer sheet instead of the app; that workbook is in the folder too.\n\n"
                  "I need a file with one line per clinician: employee ID, name, reimbursable miles, and the reimbursement in dollars "
                  "(their August miles times the rate, rounded to the cent).\n\nDenise")}])

    # ---- reference and solution
    body = [[s["id"], s["name"], f"{s['miles'] / 10:.1f}", f"{s['pay'] / 100:.2f}"] for s in sorted(d["staff"], key=lambda s: s["id"])]
    write_csv(os.path.join(ref, "reimbursement.csv"), header, body)
    write_csv(os.path.join(sol, "reimbursement.csv"), header, body)
    write_json(os.path.join(ref, "notes.json"), {"rate": str(RATE), "kinds": {kk: s["id"] for kk, s in k.items()},
                                                  "total_reimbursement": f"{sum(s['pay'] for s in d['staff']) / 100:.2f}"})
    pins = [k["personal"]["id"], k["commuter"]["id"], k["roundtrip"]["id"], odo["id"]]
    per, com, rt = k["personal"], k["commuter"], k["roundtrip"]
    write_task_yaml(HERE, {
        "id": "mileage-reimbursement", "track": "desk", "category": "bookkeeping",
        "title": "August mileage reimbursement for the field staff",
        "ask": "Denise needs August mileage worked out for payroll. Everything is in the folder, including her emails about the policy. Save it as reimbursement.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"{per['name']} ({per['id']}) logs weekend and evening personal errands in the app; they come out entirely "
            "(check: reimbursement per clinician)",
            "home-to-office and office-to-home legs are commuting and pay nothing, and the first business leg out of home and the last "
            f"one back each lose the clinician's one-way commute, never below zero; {com['name']} ({com['id']}) has a "
            f"{com['commute'] / 10:.1f}-mile commute and many shorter first and last legs, so an unfloored deduction goes negative "
            "(checks: reimbursable miles; reimbursement per clinician)",
            f"round-trip lines carry the one-way distance and count twice; {rt['name']} ({rt['id']}) has daily supply runs and Saturday "
            "home-to-patient round trips where both legs lose the commute (check: reimbursement per clinician)",
            f"{odo['name']} ({odo['id']}) is not in the app export at all; those miles are odometer end less start in a separate workbook, "
            "which also holds personal trips and July and September lines (checks: one row per clinician; reimbursement per clinician)",
            "the 2025 email says 70 cents; the December 2025 email sets 72.5 cents for 2026 (check: reimbursement per clinician)",
            "the app export runs 27 July to 4 September, carries a two-line preamble and a BOM, and upper-cases some driver names "
            "(checks: reimbursable miles; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "reimbursement.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per clinician", "path": "reimbursement.csv", "column": "employee_id",
             "ref": "reimbursement.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "reimbursement.csv", "equals_ref": "reimbursement.csv"},
            {"type": "csv_values_match", "name": "reimbursable miles", "path": "reimbursement.csv", "ref": "reimbursement.csv",
             "key": "employee_id", "columns": ["reimbursable_miles"], "numeric": True, "tolerance": 0.05, "min_accuracy": 1.0,
             "must_match_keys": pins},
            {"type": "csv_values_match", "name": "reimbursement per clinician", "path": "reimbursement.csv", "ref": "reimbursement.csv",
             "key": "employee_id", "columns": ["reimbursement"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": pins},
        ],
    })
    print(f"seed={seed}", [(s["id"], s["kind"], s["commute"], s["miles"] / 10, s["pay"] / 100) for s in d["staff"]])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a_ = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a_.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a_.seed * 1000 + attempt, a_.naive)
