#!/usr/bin/env python3
"""gradebook-weighted: final percentages and letter grades from an LMS gradebook export, weights and a syllabus.

    python gen.py [--seed N] [--naive DIR]

Business: an adult-education centre running a bookkeeping certificate course. The LMS exports raw points; the
instructor's grading rules are spread across the syllabus, the export's Weights tab and her email.

Traps (each caught by a check, see task.yaml):
  * lowest quiz dropped per the syllabus                                  (check: final grade per student)
  * EX is excused (left out of its category); blank is missing and scores zero (check: final grade per student)
  * an excused absence exists only in the instructor's email (blank cell)  (check: final grade per student)
  * a Points Possible row sits under the header; items are out of 10/20/50/40/100 (check: final grade per student)
  * weights are on the export's Weights tab, and the syllabus still has the old split (check: final grade per student)
  * a withdrawn student is left off                                        (check: final grade per student)
  * live formulas                                                           (check: live formulas)
"""
from __future__ import annotations
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

QUIZ = [f"Quiz {i}" for i in range(1, 7)]
HW = [f"HW {i}" for i in range(1, 6)]
ITEMS = QUIZ + HW + ["Midterm", "Project", "Final Exam"]
POSSIBLE = {**{q: 10 for q in QUIZ}, **{h: 20 for h in HW}, "Midterm": 50, "Project": 40, "Final Exam": 100}
WEIGHTS = [("Quizzes", 0.15), ("Homework", 0.25), ("Midterm", 0.20), ("Project", 0.10), ("Final Exam", 0.30)]
OLD_WEIGHTS = [("Quizzes", 0.15), ("Homework", 0.25), ("Midterm", 0.20), ("Project", 0.15), ("Final Exam", 0.25)]
SCALE = [(0, "F"), (60, "D"), (70, "C-"), (73, "C"), (77, "C+"), (80, "B-"), (83, "B"), (87, "B+"), (90, "A-"), (93, "A")]
CUTS = [c for c, _ in SCALE[1:]]


def letter(p: float) -> str:
    out = "F"
    for c, l in SCALE:
        if p >= c:
            out = l
    return out


def final_pct(scores: dict, *, drop=True, ex_zero=False, blank_skip=False, excused_extra=(), weights=WEIGHTS) -> float:
    def val(item):
        v = scores.get(item)
        if item in excused_extra:
            return None
        if v == "EX":
            return 0.0 if ex_zero else None
        if v is None:
            return None if blank_skip else 0.0
        return float(v)

    qs = [val(q) / 10 for q in QUIZ if val(q) is not None]
    if drop and len(qs) > 1:
        qs.remove(min(qs))
    quiz = sum(qs) / len(qs)
    hs = [val(h) / 20 for h in HW if val(h) is not None]
    hw = sum(hs) / len(hs)
    cat = {"Quizzes": quiz, "Homework": hw, "Midterm": (val("Midterm") or 0) / 50, "Project": (val("Project") or 0) / 40,
           "Final Exam": (val("Final Exam") or 0) / 100}
    return 100 * sum(w * cat[c] for c, w in weights)


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = []
    for f, l in people(r, 60):
        used = {p[0] for p in ppl} | {p[1] for p in ppl}
        if f not in used and l not in used and f != l:
            ppl.append((f, l))
        if len(ppl) == 23:
            break
    students = []
    for i, (f, l) in enumerate(ppl):
        a = r.uniform(0.60, 0.97)
        sc = {}
        for it in ITEMS:
            p = POSSIBLE[it]
            v = max(0, min(p, round(p * (a + r.uniform(-0.14, 0.08)))))
            sc[it] = v
        students.append({"id": str(4410100 + r.randint(0, 899) * 11 + i), "first": f, "last": l, "scores": sc, "a": a})
    # ordinary noise: a few missing homework/quiz cells and two EX cells
    pool = students[5:22]
    for s in r.sample(pool, 5):
        s["scores"][r.choice(HW + QUIZ)] = None
    for s in r.sample(pool, 2):
        s["scores"][r.choice(HW)] = "EX"
    s_ex, s_email, s_missing, s_proj, s_drop = students[:5]
    withdrawn = students[22]
    s_ex["scores"]["HW 3"] = "EX"
    s_ex["scores"]["HW 1"] = min(20, s_ex["scores"]["HW 1"] + 2)
    s_email["scores"]["Quiz 4"] = None
    s_email["scores"]["Quiz 2"] = None
    s_missing["scores"]["HW 2"] = None
    s_missing["scores"]["HW 4"] = None
    s_proj["scores"]["Project"] = 39
    s_proj["scores"]["Final Exam"] = r.randint(52, 62)
    s_drop["scores"]["Quiz 5"] = r.randint(1, 3)
    for it in ["HW 4", "HW 5", "Quiz 5", "Quiz 6", "Project", "Final Exam"]:
        withdrawn["scores"][it] = None
    r.shuffle(students)
    enrolled = [s for s in students if s is not withdrawn]
    for s in enrolled:
        s["final"] = final_pct(s["scores"], excused_extra=("Quiz 4",) if s is s_email else ())
        s["letter"] = letter(s["final"])
    return {"students": students, "enrolled": enrolled, "withdrawn": withdrawn, "s_ex": s_ex, "s_email": s_email,
            "s_missing": s_missing, "s_proj": s_proj, "s_drop": s_drop}


def acceptable(d: dict) -> bool:
    for s in d["enrolled"]:
        if any(abs(s["final"] - c) < 0.3 for c in CUTS):
            return False
    sc = lambda s, **kw: final_pct(s["scores"], **kw)  # noqa: E731
    e = d["s_email"]
    checks = [
        abs(sc(d["s_drop"], drop=False) - d["s_drop"]["final"]) > 0.6,
        abs(sc(d["s_ex"], ex_zero=True) - d["s_ex"]["final"]) > 0.6,
        abs(sc(e) - e["final"]) > 0.6,
        abs(sc(d["s_missing"], blank_skip=True) - d["s_missing"]["final"]) > 0.6,
        abs(sc(d["s_proj"], weights=OLD_WEIGHTS) - d["s_proj"]["final"]) > 0.6,
        len({s["letter"] for s in d["enrolled"]}) >= 6,
    ]
    return all(checks)


def solution_sheets(d: dict, *, naive: bool = False) -> dict:
    rows = []
    e = d["s_email"]
    studs = d["students"] if naive else d["enrolled"]
    for s in studs:
        line = [s["id"], f"{s['last']}, {s['first']}"]
        for it in ITEMS:
            v = s["scores"][it]
            if not naive and s is e and it == "Quiz 4":
                v = "EX"
            if v is None:
                v = "" if naive else 0
            line.append(v)
        rows.append(line)
    grade_rows = []
    for i, s in enumerate(studs, start=2):
        if naive:
            # average of whatever is entered, points as if they were percentages, equal weights, no drop
            grade_rows.append([s["id"], f"{s['last']}, {s['first']}", f"=ROUND(AVERAGE(Scores!C{i}:P{i}),1)",
                               f"=VLOOKUP(C{i},Scale!$A$2:$B$11,2,TRUE)"])
            continue
        q = f"Scores!C{i}:H{i}"; h = f"Scores!I{i}:M{i}"
        grade_rows.append([
            s["id"], f"{s['last']}, {s['first']}",
            f"=100*(SUM({q})-MIN({q}))/(COUNTIF({q},\">=0\")-1)/10",
            f"=100*SUM({h})/(COUNTIF({h},\">=0\")*20)",
            f"=100*Scores!N{i}/50", f"=100*Scores!O{i}/40", f"=100*Scores!P{i}/100",
            f"=ROUND(C{i}*Weights!$B$2+D{i}*Weights!$B$3+E{i}*Weights!$B$4+F{i}*Weights!$B$5+G{i}*Weights!$B$6,1)",
            f"=VLOOKUP(H{i},Scale!$A$2:$B$11,2,TRUE)"])
    header = ["Student ID", "Student", "Quizzes %", "Homework %", "Midterm %", "Project %", "Final Exam %", "Final %", "Letter"]
    if naive:
        header = ["Student ID", "Student", "Final %", "Letter"]
    return {
        "Final Grades": {"header": header, "rows": grade_rows, "widths": {"B": 24}},
        "Scores": {"header": ["Student ID", "Student"] + ITEMS, "rows": rows, "widths": {"B": 24}},
        "Weights": {"header": ["Category", "Weight"], "rows": [[c, w] for c, w in WEIGHTS]},
        "Scale": {"header": ["Minimum %", "Letter"], "rows": [[c, l] for c, l in SCALE]},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_xlsx(os.path.join(naive_dir, "grades.xlsx"), solution_sheets(d, naive=True), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    grade_rows = [["Points Possible", ""] + [POSSIBLE[it] for it in ITEMS]]
    for s in sorted(d["students"], key=lambda z: z["last"]):
        grade_rows.append([s["id"], f"{s['last']}, {s['first']}"] + [s["scores"][it] for it in ITEMS])
    write_xlsx(os.path.join(ws, "BKP-110_gradebook_export.xlsx"), {
        "Grades": {"merged_title": "BKP-110 Bookkeeping Fundamentals - Summer 2026 - Gradebook",
                   "header": ["Student ID", "Student"] + ITEMS, "rows": grade_rows, "widths": {"A": 16, "B": 24}},
        "Weights": {"header": ["Category", "Weight"], "rows": [[c, w] for c, w in WEIGHTS], "number_formats": {"B": "0%"},
                    "widths": {"A": 14}},
    }, creator="LMS export")
    write_text(os.path.join(ws, "syllabus_BKP-110_summer2026.md"), (
        "# BKP-110 Bookkeeping Fundamentals\n\nLakeview Adult Learning Center, Summer 2026. Instructor: Dana Okafor.\n\n"
        "## Course work\n\n- Six weekly quizzes (10 points each)\n- Five homework sets (20 points each)\n"
        "- Midterm exam (50 points)\n- Bookkeeping project (40 points)\n- Final exam (100 points)\n\n"
        "## How your grade is calculated\n\n| Category | Weight |\n|---|---|\n" +
        "".join(f"| {c} | {int(w * 100)}% |\n" for c, w in OLD_WEIGHTS) +
        "\nEach category is the percentage of points earned in that category.\n\n"
        "- Your lowest quiz score is dropped.\n"
        "- Work that is not turned in scores zero.\n"
        "- Excused work (documented absence) is not counted for or against you; it is left out of its category.\n\n"
        "## Letter grades\n\n| Final % | Letter |\n|---|---|\n" +
        "".join(f"| {c} and above | {l} |\n" for c, l in reversed(SCALE[1:])) + "| below 60 | F |\n"))
    e, w = d["s_email"], d["withdrawn"]
    write_email_thread(os.path.join(ws, "email_from_dana.txt"), [
        {"from": "Dana Okafor <dokafor@lakeviewlearning.org>", "to": "you", "date": "Mon, 17 Aug 2026 18:22",
         "subject": "BKP-110 final grades",
         "body": ("Hi - I've exported the gradebook. Could you work out the final grades? The registrar wants the "
                  "final percentage (one decimal) and the letter for every student.\n\n"
                  "A few things the export doesn't know:\n\n"
                  "1. Use the weights on the Weights tab of the export. We dropped the second project in week 3 and I "
                  "moved that weight onto the final exam. The syllabus still shows the old split.\n\n"
                  "2. In the gradebook EX means excused, and a blank means they never turned it in.\n\n"
                  f"3. {e['first']} {e['last']} had a documented absence on the day of Quiz 4. I never entered the EX, "
                  "so the cell is blank - please treat it as excused.\n\n"
                  f"4. {w['first']} {w['last']} withdrew in July. The registrar records a W, so leave that student off the "
                  "grade sheet.\n\n"
                  "Please send it as a spreadsheet with the formulas in, so I can check a couple of students by hand.\n\n"
                  "Thanks,\nDana")}])

    header = ["student_id", "student", "final_pct", "letter"]
    rows = [[s["id"], f"{s['last']}, {s['first']}", f"{s['final']:.2f}", s["letter"]] for s in sorted(d["enrolled"], key=lambda z: z["last"])]
    write_csv(os.path.join(ref, "grades.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {
        "withdrawn": {"id": w["id"], "first": w["first"], "last": w["last"]},
        "students": {s["id"]: {"first": s["first"], "last": s["last"], "final": round(s["final"], 3), "letter": s["letter"]}
                     for s in d["enrolled"]},
        "traps": {"excused_in_gradebook": d["s_ex"]["id"], "excused_by_email": e["id"], "missing_work": d["s_missing"]["id"],
                  "weights_change": d["s_proj"]["id"], "dropped_quiz": d["s_drop"]["id"]}})
    write_xlsx(os.path.join(sol, "grades.xlsx"), solution_sheets(d), creator="reference")
    write_task_yaml(HERE, {
        "id": "gradebook-weighted", "track": "desk", "category": "spreadsheet",
        "title": "Final weighted grades for the bookkeeping course",
        "ask": ("Final grades for BKP-110 are due to the registrar. Work them out from Dana's gradebook export and save "
                "grades.xlsx with the formulas in; her email and the syllabus have the rules.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the syllabus drops each student's lowest quiz; one student bombed Quiz 5, and averaging all six quizzes "
            "moves their grade (check: final grade per student)",
            "EX cells are excused and leave the category; blank cells are missing work and score zero - treating EX as "
            "zero or skipping blanks moves those students (check: final grade per student)",
            "one student's Quiz 4 is blank but the instructor's email excuses it; the same student also missed Quiz 2, so "
            "as a zero Quiz 4 is not simply the dropped quiz (check: final grade per student)",
            "a Points Possible row sits under the header and items are out of 10, 20, 50, 40 and 100 points; averaging "
            "raw points or reading that row as a student breaks every grade (check: final grade per student)",
            "the export's Weights tab has the current split (project 10%, final 30%) and the syllabus still has the old "
            "one (15%/25%); a student with a strong project and a weak final shows the difference "
            "(check: final grade per student)",
            "one student withdrew; the row is still in the export with half the work blank and must not get a letter "
            "(check: final grade per student)",
            "the instructor wants to check students by hand, so the grades must be live formulas (check: live formulas)",
        ],
        "checks": [
            {"type": "file_exists", "name": "grades.xlsx exists", "path": "grades.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "grades.xlsx", "min_count": 22},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "grades.xlsx"},
            {"type": "custom", "name": "final grade per student", "module": "check.py"},
        ],
    })
    print(f"seed={seed}", [(s["last"], round(s["final"], 1), s["letter"]) for s in d["enrolled"]][:8])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(3000):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
