#!/usr/bin/env python3
"""client-hours-by-project: a design studio's two time exports to Q3 hours per client project, billable vs not.

    python gen.py [--seed N]

Business: Driftwood Studio, a nine-person design studio. Most of the team tracks time in the desktop
tracker; the photographer and the illustrator use a phone timer app that exports on its own. The studio
manager wants the quarter's hours per client project before the account reviews.

Traps (each caught by a check, see task.yaml):
  * the timer app exports Duration (min) in minutes                        (check: total hours per project)
  * the desktop export mixes decimal hours (1.5) with clock-style entries (1:45)  (check: total hours per project)
  * Harbor Light Marine's catalog project was renamed in August; the old and new names share a project code in
    projects.xlsx and must come out as one row under the current name       (checks: project list; total hours per project)
  * the studio's own time (client Driftwood Studio in the tracker, Internal in the timer app) is excluded
                                                                             (checks: internal time excluded; project list)
  * the timer export runs from late June into October; a project that only had June time must not appear
                                                                             (checks: project list; total hours per project)
  * "Revisions (no charge)" time is never billable, even where the Billable box was ticked; billable flags
    are Yes/No in one export and billable/non-billable tags in the other   (checks: billable hours; unbillable hours)
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

Q_START, Q_END = date(2026, 7, 1), date(2026, 9, 30)
TIMER_START, TIMER_END = date(2026, 6, 22), date(2026, 10, 2)
RENAME_DATE = date(2026, 8, 10)
INTERNAL_CLIENT = "Driftwood Studio"
# code, client, current name, old name (if renamed), active window, weight, status
PROJECTS = [
    ("HLM-07", "Harbor Light Marine", "Catalog 2026", "Spring Catalog", (date(2026, 6, 24), date(2026, 9, 25)), 1.5, "Active"),
    ("HLM-08", "Harbor Light Marine", "Boat Show Signage", None, (date(2026, 8, 17), date(2026, 9, 30)), 0.8, "Active"),
    ("LKV-02", "Lakeside Veterinary", "Clinic Rebrand", None, (date(2026, 6, 22), date(2026, 9, 11)), 1.2, "Active"),
    ("LKV-03", "Lakeside Veterinary", "Appointment Cards", None, (date(2026, 8, 24), date(2026, 10, 2)), 0.7, "Active"),
    ("TMB-11", "Tamarack Brewing", "Fall Seasonal Can Labels", None, (date(2026, 7, 6), date(2026, 9, 18)), 1.1, "Active"),
    ("TMB-12", "Tamarack Brewing", "Taproom Menu Boards", None, (date(2026, 7, 20), date(2026, 8, 28)), 0.6, "Active"),
    ("EVL-04", "Everline Insurance", "Annual Report 2026", None, (date(2026, 7, 1), date(2026, 9, 30)), 1.3, "Active"),
    ("FBM-01", "Fernbrook Montessori", "Enrollment Website", None, (date(2026, 7, 1), date(2026, 8, 21)), 1.0, "Active"),
    ("WSB-05", "Wren & Sparrow Bookshop", "Author Event Posters", None, (date(2026, 8, 3), date(2026, 10, 2)), 0.5, "Active"),
    ("TMB-10", "Tamarack Brewing", "Summer Beer Fest", None, (date(2026, 6, 22), date(2026, 6, 30)), 0.9, "Closed"),
    ("LKV-01", "Lakeside Veterinary", "Holiday Cards 2025", None, None, 0, "Archived"),
    ("DWS-90", INTERNAL_CLIENT, "Portfolio Site Refresh", None, (date(2026, 6, 22), date(2026, 10, 2)), 0.7, "Active"),
    ("DWS-95", INTERNAL_CLIENT, "New Business Pitches", None, (date(2026, 6, 22), date(2026, 10, 2)), 0.6, "Active"),
    ("DWS-99", INTERNAL_CLIENT, "Studio Admin", None, (date(2026, 6, 22), date(2026, 10, 2)), 0.9, "Active"),
]
DESKTOP_STAFF = [("Ines", "Okafor"), ("Marcus", "Lindqvist"), ("Chloe", "Nguyen"), ("Rahul", "Patel"),
                 ("Dana", "Brooks"), ("Wei", "Tanaka"), ("Sofia", "Reyes")]
TIMER_STAFF = ["Nadia Haddad", "Tomasz Kowal"]
TASKS = ["Concept design", "Layout", "Client meeting", "Production art", "Photography", "Copy edits",
         "Project management", "Revisions (no charge)", "Illustration", "Prepress"]
NONBILL_TASKS = {"Revisions (no charge)"}
INTERNAL_TASKS = ["Admin", "Portfolio", "Pitch deck", "Team meeting"]


def weekdays(a: date, b: date):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def build(seed: int) -> dict:
    r = rng(seed)
    desk, timer = [], []          # entries: {date, code, person, task, hours(float), billable(bool), src, raw fields}
    for code, client, name, old, window, weight, status in PROJECTS:
        if not window:
            continue
        internal = client == INTERNAL_CLIENT
        for d in weekdays(*window):
            if r.random() > 0.42 * weight:
                continue
            for _ in range(r.choice([1, 1, 1, 2])):
                if r.random() < 0.3 and d >= TIMER_START:
                    person = r.choice(TIMER_STAFF)
                    minutes = 6 * r.randint(3, 40)
                    task = r.choice(INTERNAL_TASKS) if internal else r.choice(["Photography", "Illustration", "Client meeting", "Travel"])
                    billable = False if internal else (task != "Travel" or r.random() < 0.3)
                    timer.append({"date": d, "code": code, "person": person, "task": task, "minutes": minutes,
                                  "hours": minutes / 60, "billable": billable, "src": "timer",
                                  "start": datetime(d.year, d.month, d.day, r.randint(8, 16), r.choice([0, 5, 10, 20, 30, 45]))})
                else:
                    if d < Q_START or d > Q_END:
                        continue          # the desktop export is the quarter exactly
                    f, l = r.choice(DESKTOP_STAFF)
                    hours = 0.25 * r.randint(1, 26)
                    if internal:
                        task, billable, tick = r.choice(INTERNAL_TASKS), False, "No"
                    else:
                        task = r.choices(TASKS, weights=[3, 4, 2, 3, 1, 2, 2, 2, 1, 1])[0]
                        if task in NONBILL_TASKS:
                            tick = r.choice(["Yes", "No"])
                            billable = False
                        else:
                            billable = r.random() > 0.12
                            tick = "Yes" if billable else "No"
                    style = "clock" if (r.random() < 0.18 and hours != int(hours)) else "decimal"
                    desk.append({"date": d, "code": code, "person": f"{f} {l}", "first": f, "last": l, "task": task,
                                 "hours": hours, "billable": billable, "tick": tick, "style": style, "src": "desk"})
    # guaranteed trap rows so each trap moves a checked figure on every seed
    for d, person, minutes in ((date(2026, 7, 14), "Nadia Haddad", 222), (date(2026, 8, 26), "Tomasz Kowal", 168)):
        timer.append({"date": d, "code": "HLM-07", "person": person, "task": "Photography", "minutes": minutes,
                      "hours": minutes / 60, "billable": True, "src": "timer", "start": datetime(d.year, d.month, d.day, 9, 30)})
    for code, d in (("EVL-04", date(2026, 9, 29)), ("LKV-02", date(2026, 7, 22))):
        f, l = DESKTOP_STAFF[0] if code == "EVL-04" else DESKTOP_STAFF[2]
        desk.append({"date": d, "code": code, "person": f"{f} {l}", "first": f, "last": l, "task": "Revisions (no charge)",
                     "hours": 2.75, "billable": False, "tick": "Yes", "style": "clock", "src": "desk"})
    for code, d in (("EVL-04", date(2026, 6, 29)), ("LKV-02", date(2026, 10, 1)), ("TMB-10", date(2026, 6, 26))):
        timer.append({"date": d, "code": code, "person": TIMER_STAFF[1], "task": "Photography", "minutes": 150,
                      "hours": 2.5, "billable": True, "src": "timer", "start": datetime(d.year, d.month, d.day, 10, 0)})

    desk.sort(key=lambda e: (e["date"], e["person"], e["code"]))
    timer.sort(key=lambda e: (e["start"], e["person"]))
    info = {p[0]: p for p in PROJECTS}

    def shown_name(e):
        code, client, name, old = info[e["code"]][:4]
        return old if (old and e["date"] < RENAME_DATE) else name

    # ---- truth ----
    agg = {}
    for e in desk + timer:
        code, client, name = info[e["code"]][:3]
        if client == INTERNAL_CLIENT or not (Q_START <= e["date"] <= Q_END):
            continue
        a = agg.setdefault(code, {"client": client, "project": name, "billable": 0.0, "unbillable": 0.0})
        a["billable" if e["billable"] else "unbillable"] += e["hours"]
    truth = []
    for code in sorted(agg, key=lambda c: (agg[c]["client"], agg[c]["project"])):
        a = agg[code]
        truth.append({"code": code, "client": a["client"], "project": a["project"], "billable": round(a["billable"], 2),
                      "unbillable": round(a["unbillable"], 2), "total": round(a["billable"] + a["unbillable"], 2)})
    return {"desk": desk, "timer": timer, "truth": truth, "shown_name": shown_name, "info": info}


def acceptable(d: dict) -> bool:
    t = {x["code"]: x for x in d["truth"]}
    if set(t) != {p[0] for p in PROJECTS if p[4] and p[1] != INTERNAL_CLIENT and p[0] != "TMB-10"}:
        return False
    # the renamed project has time under both names, in both exports
    hl_desk = [e for e in d["desk"] if e["code"] == "HLM-07"]
    if not any(e["date"] < RENAME_DATE for e in hl_desk) or not any(e["date"] >= RENAME_DATE for e in hl_desk):
        return False
    if not all(8 <= x["total"] <= 220 and x["billable"] > 0 and x["unbillable"] > 0 for x in d["truth"]):
        return False
    if not any(e["code"] == "HLM-07" and e["date"] < RENAME_DATE for e in d["timer"]):
        return False
    if len({e["code"] for e in d["desk"] if e["style"] == "clock" and info_client(e) != INTERNAL_CLIENT}) < 4:
        return False
    return 170 <= len(d["desk"]) <= 320 and 50 <= len(d["timer"]) <= 130


def info_client(e) -> str:
    return {p[0]: p[1] for p in PROJECTS}[e["code"]]


def fmt_hours(e) -> str:
    h = e["hours"]
    if e["style"] == "clock":
        return f"{int(h)}:{int(round((h - int(h)) * 60)):02d}"
    return f"{h:g}"


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    info = d["info"]

    # ---- workspace ----
    write_csv(os.path.join(ws, "tracker_time_export_2026-07-01_to_2026-09-30.csv"),
              ["Date", "Client", "Project", "Task", "Notes", "Hours", "Billable?", "First Name", "Last Name"],
              [[e["date"].isoformat(), info[e["code"]][1], d["shown_name"](e), e["task"], "", fmt_hours(e), e["tick"],
                e["first"], e["last"]] for e in d["desk"]])
    write_csv(os.path.join(ws, "timer_app_export.csv"),
              ["Member", "Start", "Project", "Description", "Tags", "Duration (min)"],
              [[e["person"], e["start"].strftime("%m/%d/%Y %I:%M %p"),
                ("Internal" if info[e["code"]][1] == INTERNAL_CLIENT else info[e["code"]][1]) + " / " + d["shown_name"](e),
                e["task"], "billable" if e["billable"] else "non-billable", e["minutes"]] for e in d["timer"]],
              bom=True)
    write_xlsx(os.path.join(ws, "projects.xlsx"), {"Projects": {
        "header": ["Project code", "Client", "Project name", "Status", "Last change"],
        "rows": [["HLM-07", "Harbor Light Marine", "Spring Catalog", "Archived", "2026-08-10"],
                 *[[p[0], p[1], p[2], p[6], "2026-08-10" if p[0] == "HLM-07" else ""] for p in PROJECTS]],
        "widths": {"B": 26, "C": 28, "E": 14}}}, creator="Ines Okafor")
    write_text(os.path.join(ws, "note_from_ines.txt"),
               "Account reviews are the week after next and I want Q3's hours (July to September) for every client "
               "project, one row per project, with how much of it we can bill.\n\n"
               "Most of us are in the tracker. Nadia and Tomasz log on the phone timer app, which exports on its own, "
               "so both files count.\n\n"
               "Our own time - portfolio, pitches, admin - does not go in. It shows up under Driftwood Studio in the "
               "tracker and Internal on the timer app.\n\n"
               "Projects get renamed now and then when a client changes their mind about what to call things. The "
               "project code in projects.xlsx never changes, so treat the same code as the same project and use the "
               "name it has now.\n\n"
               "Anything logged to Revisions (no charge) is not billable, whatever the Billable box says - people tick it "
               "out of habit.\n\n"
               "Columns: client, project, billable_hours, unbillable_hours, total_hours. Hours as numbers to two "
               "decimals.\n\nInes\n")

    # ---- reference ----
    header = ["client", "project", "billable_hours", "unbillable_hours", "total_hours"]
    rows = [[t["client"], t["project"], f"{t['billable']:.2f}", f"{t['unbillable']:.2f}", f"{t['total']:.2f}"] for t in d["truth"]]
    write_csv(os.path.join(ref, "client_hours.csv"), header, rows)
    write_csv(os.path.join(sol, "client_hours.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {
        "renamed": {"code": "HLM-07", "old": "Spring Catalog", "new": "Catalog 2026", "date": RENAME_DATE.isoformat()},
        "excluded_client": INTERNAL_CLIENT, "desktop_rows": len(d["desk"]), "timer_rows": len(d["timer"]),
        "timer_rows_outside_q3": sum(1 for e in d["timer"] if not (Q_START <= e["date"] <= Q_END)),
        "clock_style_rows": sum(1 for e in d["desk"] if e["style"] == "clock"),
        "revisions_ticked_billable": sum(1 for e in d["desk"] if e["task"] in NONBILL_TASKS and e["tick"] == "Yes")})

    write_task_yaml(HERE, {
        "id": "client-hours-by-project", "track": "desk", "category": "spreadsheet",
        "title": "Q3 hours per client project, billable and not",
        "ask": ("Ines wants last quarter's hours for every client project, split into billable and unbillable, from the "
                "two time exports. Her note has the details - save it as client_hours.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the phone timer app exports Duration (min) in minutes, with a BOM and client and project run together in one "
            "column; adding minutes to the tracker's hours inflates every project the photographer or illustrator touched "
            "(check: total hours per project)",
            "the tracker's Hours column mixes decimals (1.5) with clock-style entries (2:45), which a numeric parse "
            "drops or reads as 2.45 (check: total hours per project)",
            "Harbor Light Marine's Spring Catalog was renamed Catalog 2026 on 10 August; both names carry code HLM-07 "
            "in projects.xlsx and must come out as one row under the current name (checks: project list; total hours "
            "per project)",
            "the studio's own time sits under Driftwood Studio in the tracker and Internal on the timer app and is "
            "left out (checks: internal time excluded; project list)",
            "the timer export runs from 22 June to 2 October, so June and October time must be dropped, and Summer "
            "Beer Fest only has June time and must not appear (checks: project list; total hours per project)",
            "Revisions (no charge) time is unbillable even where Billable? says Yes, and the timer app marks billing "
            "with billable/non-billable tags instead of Yes/No (checks: billable hours; unbillable hours)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "client_hours.csv", "columns": header},
            {"type": "csv_set_equal", "name": "project list", "path": "client_hours.csv", "column": "project",
             "ref": "client_hours.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "one row per project", "path": "client_hours.csv", "equals_ref": "client_hours.csv"},
            {"type": "csv_values_match", "name": "total hours per project", "path": "client_hours.csv", "ref": "client_hours.csv",
             "key": "project", "columns": ["total_hours"], "numeric": True, "tolerance": 0.011, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "billable hours", "path": "client_hours.csv", "ref": "client_hours.csv",
             "key": "project", "columns": ["billable_hours"], "numeric": True, "tolerance": 0.011, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "unbillable hours", "path": "client_hours.csv", "ref": "client_hours.csv",
             "key": "project", "columns": ["unbillable_hours"], "numeric": True, "tolerance": 0.011, "min_accuracy": 1.0},
            {"type": "text_not_contains", "name": "internal time excluded", "path": "client_hours.csv",
             "phrases": ["Driftwood", "Internal", "Portfolio Site Refresh", "New Business Pitches", "Studio Admin"]},
        ],
    })
    print(f"seed={seed} desk={len(d['desk'])} timer={len(d['timer'])}")
    for t in d["truth"]:
        print("  ", t)


if __name__ == "__main__":
    s = argparse_seed()
    for attempt in range(500):
        if acceptable(build(s * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(s * 1000 + attempt)
