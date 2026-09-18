#!/usr/bin/env python3
"""class-roster-changes: fall vs spring enrollment, adds and drops per course at an adult learning center.

    python gen.py [--seed N] [--naive DIR]

Business: a nonprofit adult learning center (ESL, GED prep, citizenship, computer skills). Fall rosters are the
instructors' own workbook, one tab per section; spring came out of the new registration system as one flat
export. The board wants to know how each course held on to its students.

Traps (each caught by a check, see task.yaml):
  * two students married over the break and registered under new names (the coordinator's email)
                                                                          (checks: added; dropped)
  * a few students sit in both sections of the same course, and some moved section between terms
                                                                          (checks: fall enrolled; spring enrolled; added; dropped)
  * withdrawn students are marked only in a free-text notes column, spelled several ways
                                                                          (checks: fall enrolled; spring enrolled; dropped)
  * fall names are "LAST, First" with stray spaces, spring names are "First Last" (checks: added; dropped)
  * the spring waitlist is in the folder and is not enrollment             (check: spring enrolled)
  * one course ran only in fall and one only in spring; both need a row   (check: one row per course)
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# code, title, fall sections, spring sections, schedule per section
COURSES = [
    ("ESL-101", "English for Beginners", ["A", "B"], ["A", "B"]),
    ("ESL-201", "Intermediate English", ["A"], ["A"]),
    ("GED-110", "GED Math", ["A", "B"], ["A", "B"]),
    ("GED-120", "GED Reasoning Through Language Arts", ["A"], ["A"]),
    ("CIT-100", "Citizenship Test Prep", ["A"], ["A"]),
    ("CMP-101", "Computer Basics", ["A", "B"], ["A"]),
    ("CMP-150", "Spreadsheets for Work", [], ["A"]),
    ("SEW-101", "Sewing Basics", ["A"], []),
]
SCHEDULE = {"A": "Mon/Wed 9:30-11:30", "B": "Tue/Thu 6:00-8:00 pm"}
WD_NOTES = ["Withdrew 01/28", "WD - moved away", "withdrawn (refund issued)", "W/D", "withdrew - work schedule"]
FALL_WD_NOTES = ["dropped week 3", "Withdrew 10/20", "W/D - no longer attending"]
OTHER_NOTES = ["needs large print", "paid", "sliding scale", "late start", "has own laptop", "", "", "", "", "", "", ""]


def build(seed: int) -> dict:
    r = rng(seed)
    pool, seen = [], set()
    while len(pool) < 170:
        f, l = person(r)
        if (f, l) not in seen:
            seen.add((f, l))
            pool.append({"pid": len(pool), "first": f, "last": l, "phone": phone_digits(r)})
    # married names come from outside the surname pool, so they can never collide with another student
    free_lasts = ["Whitfield", "Castellano", "Brennan", "Okonkwo", "Delgado", "Novak", "Sorensen", "Fitzgerald", "Kowalski", "Marchetti"]
    r.shuffle(free_lasts)

    fall_rows, spring_rows = [], []      # dicts: course, section, pid, note, name override
    truth = {}
    renamed = []
    for code, title, fsecs, ssecs in COURSES:
        fall, spring = set(), set()
        if fsecs:
            n = r.randint(22, 30) if len(fsecs) == 2 else r.randint(12, 18)
            fall = set(p["pid"] for p in r.sample(pool, n))
        cont = set()
        if fsecs and ssecs:
            cont = set(r.sample(sorted(fall), int(len(fall) * r.uniform(0.6, 0.78))))
        adds = set()
        if ssecs:
            n_add = r.randint(4, 8) if fsecs else r.randint(12, 16)
            adds = set(p["pid"] for p in r.sample([p for p in pool if p["pid"] not in fall], n_add))
        spring = cont | adds
        truth[code] = {"fall": fall, "spring": spring, "title": title}
        # ---- fall section rows ----
        fsec_of = {}
        for pid in sorted(fall):
            fsec_of[pid] = r.choice(fsecs)
            fall_rows.append({"course": code, "section": fsec_of[pid], "pid": pid, "note": r.choice(OTHER_NOTES)})
        if len(fsecs) == 2:     # people in both sections
            for pid in r.sample(sorted(fall), 2 if code != "GED-110" else 1):
                other = "B" if fsec_of[pid] == "A" else "A"
                fall_rows.append({"course": code, "section": other, "pid": pid, "note": r.choice(OTHER_NOTES)})
        if fsecs:               # fall withdrawals: on the sheet, never enrolled for the count, not back in spring
            wd = [p["pid"] for p in r.sample([p for p in pool if p["pid"] not in fall and p["pid"] not in spring], 1)]
            for pid in wd:
                fall_rows.append({"course": code, "section": r.choice(fsecs), "pid": pid, "note": r.choice(FALL_WD_NOTES), "withdrawn": True})
        # ---- spring rows ----
        for pid in sorted(spring):
            if len(ssecs) == 2:
                sec = fsec_of.get(pid, r.choice(ssecs))
                if pid in fsec_of and r.random() < 0.25:
                    sec = "B" if sec == "A" else "A"
            else:
                sec = ssecs[0]
            spring_rows.append({"course": code, "section": sec, "pid": pid, "note": r.choice(OTHER_NOTES)})
        if len(ssecs) == 2:
            for pid in r.sample(sorted(spring), 1 if code == "ESL-101" else 2):
                sec = next(x["section"] for x in spring_rows if x["pid"] == pid and x["course"] == code)
                spring_rows.append({"course": code, "section": "B" if sec == "A" else "A", "pid": pid, "note": ""})
        if ssecs:               # spring withdrawals: on the export with a note, not enrolled
            pool_wd = [p["pid"] for p in pool if p["pid"] not in fall and p["pid"] not in spring]
            wd_new = r.sample(pool_wd, 1) if code in ("ESL-201", "CMP-150") else []
            for pid in wd_new:
                spring_rows.append({"course": code, "section": ssecs[0], "pid": pid, "note": r.choice(WD_NOTES), "withdrawn": True})
            if fsecs and code in ("ESL-101", "GED-120", "CIT-100"):
                gone = r.choice(sorted(fall - spring))
                spring_rows.append({"course": code, "section": ssecs[-1], "pid": gone, "note": r.choice(WD_NOTES), "withdrawn": True})
    # two students married over the break: continuing in at least one course
    continuing = {}
    for code, t in truth.items():
        for pid in t["fall"] & t["spring"]:
            continuing.setdefault(pid, []).append(code)
    women = [pid for pid in sorted(continuing) if pool[pid]["first"] in
             ("Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen", "Lisa", "Nancy",
              "Betty", "Margaret", "Sandra", "Ashley", "Kimberly", "Emily", "Donna", "Michelle", "Carol", "Amanda", "Melissa",
              "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura", "Cynthia", "Kathleen", "Amy", "Angela", "Anna", "Priya",
              "Fatima", "Amara", "Ingrid", "Sofia", "Aisha", "Chloe", "Nadia", "Leila")]
    for pid in r.sample(women, 2):
        renamed.append({"pid": pid, "old_last": pool[pid]["last"], "new_last": free_lasts.pop()})
    new_last = {x["pid"]: x["new_last"] for x in renamed}
    waitlist = []
    for code in ("ESL-101", "GED-110", "CMP-150", "CIT-100"):
        for p in r.sample([p for p in pool if p["pid"] not in truth[code]["spring"]], 2):
            waitlist.append({"course": code, "pid": p["pid"]})
    return {"pool": pool, "truth": truth, "fall_rows": fall_rows, "spring_rows": spring_rows, "renamed": renamed,
            "new_last": new_last, "waitlist": waitlist}


def counts(d: dict) -> dict:
    out = {}
    for code, _, _, _ in COURSES:
        t = d["truth"][code]
        out[code] = {"fall": len(t["fall"]), "spring": len(t["spring"]), "added": len(t["spring"] - t["fall"]),
                     "dropped": len(t["fall"] - t["spring"])}
    return out


def naive_counts(d: dict) -> dict:
    """Seats per course (withdrawn rows included), people matched on the name as written."""
    pool, nl = d["pool"], d["new_last"]
    out = {}
    for code, _, _, _ in COURSES:
        f = [x for x in d["fall_rows"] if x["course"] == code]
        s = [x for x in d["spring_rows"] if x["course"] == code]
        fn = {(pool[x["pid"]]["first"], pool[x["pid"]]["last"]) for x in f}
        sn = {(pool[x["pid"]]["first"], nl.get(x["pid"], pool[x["pid"]]["last"])) for x in s}
        out[code] = {"fall": len(f), "spring": len(s), "added": len(sn - fn), "dropped": len(fn - sn)}
    return out


def acceptable(d: dict) -> bool:
    c = counts(d)
    rn_courses = {code for code, t in d["truth"].items() for x in d["renamed"] if x["pid"] in (t["fall"] & t["spring"])}
    return len(rn_courses) >= 2 and all(v["fall"] != v["spring"] or v["fall"] == 0 for v in c.values())


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    pool = d["pool"]
    header = ["course", "fall_enrolled", "spring_enrolled", "added", "dropped"]
    if naive_dir:
        nc = naive_counts(d)
        write_csv(os.path.join(naive_dir, "roster_changes.csv"), header,
                  [[code, nc[code]["fall"], nc[code]["spring"], nc[code]["added"], nc[code]["dropped"]] for code, _, _, _ in COURSES])
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 11)
    titles = {c[0]: c[1] for c in COURSES}
    instructors = ["Ms. Halvorsen", "Mr. Delacroix", "Ms. Abernathy", "Mr. Quintero", "Ms. Vukovic", "Mr. Ashdown"]

    # ---- fall workbook: one tab per section ----
    sheets = {}
    for code, title, fsecs, _ in COURSES:
        for sec in fsecs:
            rows = [x for x in d["fall_rows"] if x["course"] == code and x["section"] == sec]
            r.shuffle(rows)
            rows.sort(key=lambda x: pool[x["pid"]]["last"])
            out = []
            for i, x in enumerate(rows, 1):
                p = pool[x["pid"]]
                nm = f"{p['last'].upper() if r.random() < 0.5 else p['last']}, {p['first']}"
                out.append([i, name_noise(r, nm) if r.random() < 0.3 else nm, phone_variant(p["phone"], r.randrange(7)), x["note"]])
            sheets[f"{code}-{sec}"] = {"merged_title": f"{code}-{sec} {title} - {SCHEDULE[sec]}",
                                       "preamble": [[f"Instructor: {r.choice(instructors)}", "", "Fall 2025"]],
                                       "header": ["#", "Student (Last, First)", "Phone", "Notes"], "rows": out,
                                       "widths": {"B": 30, "C": 16, "D": 28}}
    write_xlsx(os.path.join(ws, "fall_2025_rosters.xlsx"), sheets, creator="Instructors")

    # ---- spring export ----
    srows = []
    for x in d["spring_rows"]:
        p = pool[x["pid"]]
        last = d["new_last"].get(x["pid"], p["last"])
        reg = date_variant(day_in(r, date(2025, 12, 1), date(2026, 1, 20)), 1)
        srows.append([f"{x['course']}-{x['section']}", titles[x["course"]], f"{p['first']} {last}", reg, x["note"], r.random()])
    srows.sort(key=lambda row: (row[0], row[5]))
    write_csv(os.path.join(ws, "spring_2026_enrollment_export.csv"),
              ["Section", "Course Title", "Student Name", "Registered", "Notes"], [row[:5] for row in srows], bom=True, crlf=True)
    wl = [[f"{w['course']}", titles[w["course"]], f"{pool[w['pid']]['first']} {d['new_last'].get(w['pid'], pool[w['pid']]['last'])}", i + 1]
          for i, w in enumerate(d["waitlist"])]
    write_csv(os.path.join(ws, "spring_2026_waitlist.csv"), ["Course", "Course Title", "Student Name", "Position"], wl)
    rn = d["renamed"]
    write_email_thread(os.path.join(ws, "email_from_coordinator.txt"), [
        {"from": "Renata Szabo <rszabo@eastsidelearning.org>", "to": "you", "date": "Mon, 9 Feb 2026 16:05",
         "subject": "fall vs spring numbers for the board",
         "body": ("For Thursday's board packet I need to show how each course held on to its students from fall to spring. "
                  "The fall rosters are the instructors' workbook (a tab per section) and spring is the export from the new "
                  "registration system.\n\n"
                  "For every course we ran in either term: how many were enrolled in fall, how many in spring, how many were "
                  "added (in the course in spring but not in fall) and how many dropped (in it in fall but not in spring). "
                  "Count people per course, not seats - a section is just a time slot.\n\n"
                  "Anyone who withdrew isn't enrolled, even if they're still listed. The instructors write that in the notes "
                  "however they feel like it.\n\n"
                  f"Also, two of our students got married over the break and registered for spring under their new names: "
                  f"{pool[rn[0]['pid']]['first']} {rn[0]['old_last']} is now {pool[rn[0]['pid']]['first']} {rn[0]['new_last']}, and "
                  f"{pool[rn[1]['pid']]['first']} {rn[1]['old_last']} is now {pool[rn[1]['pid']]['first']} {rn[1]['new_last']}.\n\n"
                  "Save it as a csv with columns course, fall_enrolled, spring_enrolled, added, dropped, using the course code "
                  "(like ESL-101).\n\nThank you!\nRenata")}])

    c = counts(d)
    rows = [[code, c[code]["fall"], c[code]["spring"], c[code]["added"], c[code]["dropped"]] for code, _, _, _ in COURSES]
    write_csv(os.path.join(ref, "roster_changes.csv"), header, rows)
    write_csv(os.path.join(sol, "roster_changes.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {"renamed": [{"first": pool[x["pid"]]["first"], "old_last": x["old_last"], "new_last": x["new_last"]}
                                                             for x in rn], "naive": naive_counts(d)})
    write_task_yaml(HERE, {
        "id": "class-roster-changes", "track": "desk", "category": "spreadsheet",
        "title": "Fall to spring enrollment, adds and drops by course",
        "ask": ("Renata needs fall-to-spring enrollment changes for every course for the board packet. Save it as "
                "roster_changes.csv; her email explains what she wants counted.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "two students married over the break and appear in spring under new last names (named in Renata's email); matched "
            "on the written name they become a drop and an add in every course they continued (checks: added per course; dropped per course)",
            "a few students hold seats in both sections of ESL-101, GED-110 or CMP-101, and continuing students moved between the "
            "morning and evening sections; counting seats or diffing sections inflates enrollment and invents adds and drops "
            "(checks: fall enrolled per course; spring enrolled per course)",
            "withdrawals exist only in the notes column ('W/D', 'Withdrew 01/28', 'withdrawn (refund issued)', 'dropped week 3') "
            "on both terms; those rows are not enrollment, and a fall student withdrawn in spring is a drop "
            "(checks: fall enrolled per course; spring enrolled per course; dropped per course)",
            "fall tabs write names 'LAST, First' with stray spaces under a merged title and an instructor line; spring writes "
            "'First Last' with a BOM and CRLF endings (checks: added per course; dropped per course)",
            "the spring waitlist sits in the folder in the same shape as an enrollment list (check: spring enrolled per course)",
            "SEW-101 ran only in fall and CMP-150 only in spring; both need a row with zeros where the course did not run "
            "(check: one row per course)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "roster_changes.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per course", "path": "roster_changes.csv", "column": "course",
             "ref": "roster_changes.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_values_match", "name": "fall enrolled per course", "path": "roster_changes.csv", "ref": "roster_changes.csv",
             "key": "course", "columns": ["fall_enrolled"], "numeric": True, "tolerance": 0.01},
            {"type": "csv_values_match", "name": "spring enrolled per course", "path": "roster_changes.csv", "ref": "roster_changes.csv",
             "key": "course", "columns": ["spring_enrolled"], "numeric": True, "tolerance": 0.01},
            {"type": "csv_values_match", "name": "added per course", "path": "roster_changes.csv", "ref": "roster_changes.csv",
             "key": "course", "columns": ["added"], "numeric": True, "tolerance": 0.01},
            {"type": "csv_values_match", "name": "dropped per course", "path": "roster_changes.csv", "ref": "roster_changes.csv",
             "key": "course", "columns": ["dropped"], "numeric": True, "tolerance": 0.01},
        ],
    })
    print(f"seed={seed}")
    nc = naive_counts(d)
    for code, _, _, _ in COURSES:
        print(f"  {code}: truth {c[code]}  naive {nc[code]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(500):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
