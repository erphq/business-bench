#!/usr/bin/env python3
"""long-to-wide-attendance: kiosk check-ins and a coach's absence sheet pivoted into the district's attendance grid.

    python gen.py [--seed N] [--naive DIR]

Business: Gearhouse Robotics Club runs an after-school robotics program on Tuesdays and Thursdays, funded by
the school district's out-of-school-time grant. The district wants attendance as one row per enrolled student
and one column per scheduled session, coded P / T / E / U.

Traps (each caught by a check, see task.yaml):
  * no record for a student on a day is a blank cell, not U; the in-service day has no records at all
                                                                           (check: every session cell)
  * codes come from two sources: kiosk check-ins after 3:40 PM are T, the coach's sheet gives E or U,
    and a check-in beats the coach's absent mark on the same day        (check: every session cell)
  * the kiosk is shared with Chess Club; one enrolled student has only a chess check-in on a robotics day
                                                                           (check: every session cell)
  * the kiosk shows preferred names (Alex, Tony); the grid wants the roster's legal Last, First
                                                                           (checks: one row per student; every session cell)
  * a student who never checked in still gets a row, and a guest who is not enrolled does not
                                                                           (checks: one row per student; row count)
  * rows sorted by name                                                    (check: rows sorted by student name)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

START = date(2026, 9, 15)
SESSIONS = [START + timedelta(days=k) for k in range(0, 45) if (START + timedelta(days=k)).weekday() in (1, 3)]
CLOSED = date(2026, 10, 13)
PREFERRED = [("Alejandro", "Alex"), ("Thanh", "Tony"), ("Katherine", "Kate")]
EXCUSED_REASONS = ["dentist", "sick", "family trip, parent emailed", "orchestra concert", "doctor appt"]
UNEXCUSED_REASONS = ["no show", "no word from family", "didn't come, no note"]


def hdr(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def build(seed: int) -> dict:
    r = rng(seed)
    firsts = [f for f in FIRST if f not in {p[0] for p in PREFERRED} and f not in {p[1] for p in PREFERRED}]
    names = set()
    students = []
    for legal, pref in PREFERRED:
        last = r.choice(LAST)
        students.append({"first": legal, "last": last, "pref": pref})
        names.add((legal, last))
    while len(students) < 18:
        f, l = r.choice(firsts), r.choice(LAST)
        if (f, l) in names or any(s["last"] == l for s in students):
            continue
        names.add((f, l))
        students.append({"first": f, "last": l, "pref": f})
    for s in students:
        s["name"] = f"{s['last']}, {s['first']}"
        s["display"] = f"{s['pref']} {s['last']}"
    r.shuffle(students)
    late_joiner = students[0]
    late_joiner["start"] = date(2026, 10, 1)
    never = students[1]
    chess_kid = students[2]
    conflict_kid = students[3]
    dup_kid = students[4]
    codes = {}
    for s in students:
        for d in SESSIONS:
            if d == CLOSED or d < s.get("start", START) or s is never:
                codes[(s["name"], d)] = ""
                continue
            x = r.random()
            codes[(s["name"], d)] = "P" if x < 0.68 else "T" if x < 0.78 else "E" if x < 0.85 else "U" if x < 0.91 else ""
    open_days = [d for d in SESSIONS if d != CLOSED]
    # forced cells for the trap students
    chess_day = r.choice(open_days[2:])
    codes[(chess_kid["name"], chess_day)] = ""
    conflict_day = r.choice([d for d in open_days if d != chess_day])
    codes[(conflict_kid["name"], conflict_day)] = "T"
    dup_day = r.choice(open_days)
    codes[(dup_kid["name"], dup_day)] = "P"
    edge_kid = students[5]
    edge_day = r.choice(open_days)
    codes[(edge_kid["name"], edge_day)] = "P"

    kiosk, coach = [], []
    for s in students:
        for d in SESSIONS:
            c = codes[(s["name"], d)]
            if c in ("P", "T"):
                if s is edge_kid and d == edge_day:
                    t = datetime(d.year, d.month, d.day, 15, 40)
                elif c == "P":
                    t = datetime(d.year, d.month, d.day, 15, r.randint(2, 39), r.randint(0, 59))
                else:
                    t = datetime(d.year, d.month, d.day, 15, 41) + timedelta(minutes=r.randint(0, 38), seconds=r.randint(0, 59))
                kiosk.append([t, s["display"], "Robotics Club"])
                if s is dup_kid and d == dup_day:
                    kiosk.append([t + timedelta(minutes=2, seconds=13), s["display"], "Robotics Club"])
            elif c in ("E", "U"):
                coach.append([d, s, c])
    coach.append([conflict_day, conflict_kid, "U"])            # coach marked absent before the late check-in
    kiosk.append([datetime(chess_day.year, chess_day.month, chess_day.day, 15, r.randint(5, 30), r.randint(0, 59)),
                  chess_kid["display"], "Chess Club"])
    # other chess club kids, and a guest who came to robotics once
    for d in [x for x in SESSIONS if x != CLOSED][::2]:
        for _ in range(r.randint(2, 4)):
            f, l = person(r)
            kiosk.append([datetime(d.year, d.month, d.day, 15, r.randint(0, 50), r.randint(0, 59)), f"{f} {l}", "Chess Club"])
    guest_day = r.choice(open_days)
    gf, gl = r.choice(firsts), r.choice([x for x in LAST if x not in {s["last"] for s in students}])
    kiosk.append([datetime(guest_day.year, guest_day.month, guest_day.day, 15, 12, 40), f"Guest - {gf} {gl}", "Robotics Club"])
    kiosk.sort(key=lambda x: (x[0], x[1]))
    coach.sort(key=lambda x: (x[0], x[1]["last"]))
    students_sorted = sorted(students, key=lambda s: s["name"].lower())
    return {"students": students, "sorted": students_sorted, "codes": codes, "kiosk": kiosk, "coach": coach,
            "late_joiner": late_joiner, "never": never, "chess": (chess_kid, chess_day), "conflict": (conflict_kid, conflict_day),
            "dup": (dup_kid, dup_day), "edge": (edge_kid, edge_day), "guest": f"{gf} {gl}"}


def acceptable(d: dict) -> bool:
    # the sort order must differ from the roster order and from a first-name sort
    names = [s["name"] for s in d["students"]]
    by_first = sorted(d["students"], key=lambda s: s["display"].lower())
    return names != [s["name"] for s in d["sorted"]] and [s["name"] for s in by_first] != [s["name"] for s in d["sorted"]]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 11)
    header = ["Student Name"] + [hdr(x) for x in SESSIONS]
    write_csv(os.path.join(ws, "district_attendance_template.csv"), header,
              [["Example, Student"] + ["P", "P", "T", "", "E", "U", "P"] + [""] * (len(SESSIONS) - 7)])
    write_csv(os.path.join(ws, "kiosk_checkins_fall.csv"), ["Check-in Time", "Name", "Program", "Device"],
              [[t.strftime("%Y-%m-%d %H:%M:%S"), n, p, "Lobby iPad"] for t, n, p in d["kiosk"]], bom=True, crlf=True)
    coach_rows = []
    for dd, s, c in d["coach"]:
        style = r.randrange(3)
        who = s["name"] if style == 0 else f"{s['pref']} {s['last']}" if style == 1 else f"{s['last'].lower()}, {s['first'].lower()}"
        reason = r.choice(EXCUSED_REASONS if c == "E" else UNEXCUSED_REASONS)
        coach_rows.append([dd, who, reason, "Y" if c == "E" else "N"])
    coach_rows.insert(sum(1 for x in d["coach"] if x[0] < CLOSED), [CLOSED, "(no club - district in-service day)", "", ""])
    write_xlsx(os.path.join(ws, "coach_absence_sheet.xlsx"), {"Absences": {
        "header": ["Date", "Student", "Reason", "Excused?"], "rows": coach_rows, "widths": {"A": 12, "B": 30, "C": 30}}},
        creator="Coach Rivera")
    write_xlsx(os.path.join(ws, "roster_fall_2026.xlsx"), {"Roster": {
        "merged_title": "Gearhouse Robotics Club - Fall 2026 enrollment",
        "header": ["Last Name", "First Name (legal)", "Goes by", "Grade", "Start Date"],
        "rows": [[s["last"], s["first"], s["pref"] if s["pref"] != s["first"] else "", r.choice([6, 7, 8]),
                  s.get("start", START)] for s in d["students"]],
        "widths": {"A": 16, "B": 20, "C": 12, "E": 12}}}, creator="Gearhouse")
    write_text(os.path.join(ws, "district_attendance_instructions.txt"),
               "Out-of-School-Time Grant - attendance submission (fall session)\n"
               "Lakemont Unified School District, Expanded Learning Office\n"
               "\n"
               "Please return attendance on the attached template, one file per program.\n"
               "\n"
               "- One row per enrolled student, including students who did not attend. Do not include\n"
               "  visitors, siblings or trial-day guests. Delete the example row.\n"
               "- Student Name must be the legal name as it appears on your enrollment roster, written\n"
               "  Last, First. Do not use nicknames.\n"
               "- Rows in alphabetical order by Student Name.\n"
               "- Keep the date columns exactly as they are in the template, one per scheduled session.\n"
               "- Codes:  P = present   T = tardy   E = excused absence   U = unexcused absence\n"
               "- Leave a cell blank when you have no record for that student on that day. Do not fill\n"
               "  blanks with U; we treat a blank as not scheduled or unknown.\n"
               "\n"
               "Program rules we agreed with Gearhouse:\n"
               "- Sessions start at 3:30 PM. A check-in after 3:40 PM is T; 3:40 PM or earlier is P.\n"
               "- Excused and unexcused absences come from the coach's absence sheet (Excused? Y = E, N = U).\n"
               "- If a student has a Robotics Club check-in on a day the coach also marked them absent, the\n"
               "  check-in stands (they arrived late after the coach took the register).\n")

    rows = [[s["name"]] + [d["codes"][(s["name"], x)] for x in SESSIONS] for s in d["sorted"]]
    write_csv(os.path.join(ref, "attendance_grid.csv"), header, rows)
    write_csv(os.path.join(sol, "attendance_grid.csv"), header, rows)
    must = sorted({d["chess"][0]["name"], d["conflict"][0]["name"], d["dup"][0]["name"], d["edge"][0]["name"],
                   d["late_joiner"]["name"], d["never"]["name"]} | {s["name"] for s in d["students"] if s["pref"] != s["first"]})
    write_json(os.path.join(ref, "notes.json"), {"order": [s["name"] for s in d["sorted"]], "must": must,
                                                  "chess": [d["chess"][0]["name"], hdr(d["chess"][1])],
                                                  "conflict": [d["conflict"][0]["name"], hdr(d["conflict"][1])],
                                                  "edge_1540": [d["edge"][0]["name"], hdr(d["edge"][1])], "guest": d["guest"]})
    write_task_yaml(HERE, {
        "id": "long-to-wide-attendance", "track": "desk", "category": "reformatting",
        "title": "Fall attendance grid for the district grant",
        "ask": ("The district needs our fall robotics attendance on their grid. Can you build it from the kiosk "
                "check-ins and the coach's absence sheet? Their instructions, template and our roster are in the "
                "folder - save it as attendance_grid.csv.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "a student with no kiosk check-in and no coach entry on a day gets a blank cell, not U; the late joiner "
            "is blank before 1 October, one enrolled student never came, and the 10/13 in-service column is blank "
            "for everyone (check: every session cell)",
            "codes are derived: a kiosk check-in after 3:40 PM is T and 3:40 PM exactly is P; the coach's sheet gives "
            "E or U from its Excused? column; writing Present/Late words or copying the reason fails "
            "(check: every session cell)",
            "the coach marked one student absent on a day that student checked in late; the check-in wins, so the "
            "cell is T, not U, and one student scanned twice two minutes apart is still a single P "
            "(check: every session cell)",
            "the kiosk is shared with Chess Club; one enrolled robotics student has only a Chess Club check-in on a "
            "robotics day, which must stay blank (check: every session cell)",
            "the kiosk shows preferred names (Alex, Tony, Kate) and the coach types names three ways; the grid wants "
            "the roster's legal name as Last, First (checks: one row per enrolled student; every session cell)",
            "a trial-day guest checked in to Robotics Club and is not enrolled; the student who never attended still "
            "needs a row (checks: one row per enrolled student; row count)",
            "rows must be alphabetical by Last, First, not in roster or kiosk order (check: rows sorted by student name)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "district template columns, exact order", "path": "attendance_grid.csv",
             "columns": header, "exact": True},
            {"type": "csv_set_equal", "name": "one row per enrolled student", "path": "attendance_grid.csv",
             "column": "Student Name", "ref": "attendance_grid.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "attendance_grid.csv", "equals_ref": "attendance_grid.csv"},
            {"type": "csv_values_match", "name": "every session cell", "path": "attendance_grid.csv", "ref": "attendance_grid.csv",
             "key": "Student Name", "columns": [hdr(x) for x in SESSIONS], "min_accuracy": 1.0, "must_match_keys": must},
            {"type": "custom", "name": "rows sorted by student name", "module": "check.py"},
        ],
    })
    print(f"seed={seed} students={len(d['students'])} kiosk={len(d['kiosk'])} coach={len(d['coach'])} must={must}")


def write_naive(d: dict, out: str) -> None:
    """The obvious pivot: every kiosk row is P (any program), every coach row is U, names as the kiosk shows
    them, blanks for the rest, rows in first-seen order."""
    os.makedirs(out, exist_ok=True)
    grid, order = {}, []
    for t, n, p in d["kiosk"]:
        if n not in grid:
            grid[n] = {}; order.append(n)
        grid[n][t.date()] = "P"
    for dd, s, c in d["coach"]:
        n = f"{s['pref']} {s['last']}"
        if n not in grid:
            grid[n] = {}; order.append(n)
        grid[n].setdefault(dd, "U")
    header = ["Student Name"] + [hdr(x) for x in SESSIONS]
    write_csv(os.path.join(out, "attendance_grid.csv"), header, [[n] + [grid[n].get(x, "") for x in SESSIONS] for n in order])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(200):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
