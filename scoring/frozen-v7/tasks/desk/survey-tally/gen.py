#!/usr/bin/env python3
"""survey-tally: member survey averages and counts per question for a coworking space.

    python gen.py [--seed N] [--naive DIR]

Business: Foundry Commons Coworking in Columbus. The annual member survey ran on a form tool for two weeks in
August; the export has one row per submission with the answers as text. The community manager's note says how
the space scores it.

Traps (each caught by a check, see task.yaml):
  * three statements are worded negatively and are scored in reverse so a higher average is always better
                                                                   (check: average per question)
  * "N/A" and skipped answers are not scores and do not count as responses (checks: responses per question; average)
  * members who submitted twice (sometimes with the email in different case) count once, with their last
    submission                                                    (checks: responses per question; average)
  * staff test submissions on the space's own domain are excluded  (check: responses per question)
  * question 8 was added three days in, so earlier rows are blank for it   (check: responses per question)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

QUESTIONS = [
    ("The Wi-Fi is fast and reliable.", False),
    ("The front desk team is helpful.", False),
    ("The kitchen and coffee area are kept clean.", False),
    ("It is hard to find a quiet place to take a call.", True),
    ("Booking a meeting room is easy.", False),
    ("I feel part of a community here.", False),
    ("I often can't find a desk when I arrive.", True),
    ("The monthly member events are worth attending.", False),
    ("The space is too cold or too warm most days.", True),
    ("I would recommend Foundry Commons to a friend.", False),
]
LABELS = {5: "Strongly agree", 4: "Agree", 3: "Neither agree nor disagree", 2: "Disagree", 1: "Strongly disagree"}
Q8_ADDED = datetime(2026, 8, 6, 9, 0)
NA = "N/A"
# how members feel on average about each statement as worded (1..5)
LEAN = [3.6, 4.4, 3.2, 3.7, 2.6, 3.9, 2.4, 3.3, 3.5, 4.1]


def build(seed: int) -> dict:
    r = rng(seed)
    members = people(r, 104)
    subs = []
    t0 = datetime(2026, 8, 3, 8, 0)

    def answers():
        out = []
        for qi, lean in enumerate(LEAN):
            if r.random() < (0.16 if qi in (7, 4) else 0.05):
                out.append(NA)
            elif r.random() < 0.03:
                out.append("")
            else:
                x = max(1, min(5, round(r.gauss(lean, 1.0))))
                out.append(x)
        return out

    for f, l in members[:96]:
        ts = t0 + timedelta(minutes=r.randint(0, 13 * 24 * 60))
        subs.append({"ts": ts, "email": email_for(r, f, l), "ans": answers(), "test": False})
    # second submissions: changed answers, later, email case sometimes different
    for s in r.sample(subs, 13):
        again = dict(s)
        again["ts"] = s["ts"] + timedelta(hours=r.randint(2, 120))
        again["ans"] = answers()
        again["email"] = s["email"].upper() if r.random() < 0.4 else (s["email"].capitalize() if r.random() < 0.5 else s["email"])
        subs.append(again)
    # staff tests
    for i, who in enumerate(["amara", "test", "frontdesk"]):
        subs.append({"ts": t0 + timedelta(hours=1 + i * 30), "email": f"{who}@foundrycommons.co",
                     "ans": [5 if j % 2 == 0 else 1 for j in range(10)], "test": True})
    subs.sort(key=lambda s: s["ts"])
    for s in subs:
        if s["ts"] < Q8_ADDED:
            s["ans"][7] = ""
    return {"subs": subs}


def tally(subs, reverse=True, dedupe="last", tests=False, na_as=None) -> dict:
    pool = [s for s in subs if tests or not s["test"]]
    if dedupe:
        keep = {}
        for s in sorted(pool, key=lambda s: s["ts"]):
            k = s["email"].strip().lower()
            if dedupe == "last" or k not in keep:
                keep[k] = s
        pool = list(keep.values())
    out = {}
    for qi, (_, rev) in enumerate(QUESTIONS):
        scores = []
        for s in pool:
            a = s["ans"][qi]
            if a == "":
                continue
            if a == NA:
                if na_as is None:
                    continue
                scores.append(na_as)
                continue
            scores.append(6 - a if (rev and reverse) else a)
        out[f"Q{qi + 1}"] = (len(scores), round(sum(scores) / len(scores) + 1e-9, 2) if scores else None)
    return out


def acceptable(d: dict) -> bool:
    t = tally(d["subs"])
    for qi, (_, rev) in enumerate(QUESTIONS):
        n, avg = t[f"Q{qi + 1}"]
        if rev and abs(avg - 3) < 0.25:
            return False
        # the exact average must not sit on a half-cent so rounding is unambiguous
        pool_scores = None
    first = tally(d["subs"], dedupe="first")
    if sum(1 for q in t if abs(first[q][1] - t[q][1]) > 0.006) < 4:
        return False
    nodup = tally(d["subs"], dedupe=None)
    if sum(1 for q in t if nodup[q][0] != t[q][0]) < 8:
        return False
    na3 = tally(d["subs"], na_as=3)
    if sum(1 for q in t if na3[q][0] != t[q][0]) < 6:
        return False
    return True


def half_cent_safe(d: dict) -> bool:
    t = tally(d["subs"])
    keep = {}
    for s in sorted([s for s in d["subs"] if not s["test"]], key=lambda s: s["ts"]):
        keep[s["email"].strip().lower()] = s
    for qi, (_, rev) in enumerate(QUESTIONS):
        sc = [6 - s["ans"][qi] if rev else s["ans"][qi] for s in keep.values() if s["ans"][qi] not in ("", NA)]
        x = sum(sc) / len(sc) * 100
        if abs(x - int(x) - 0.5) < 0.02:
            return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["question", "responses", "average"]
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        nv = tally(d["subs"], reverse=False, dedupe=None, tests=True)
        write_csv(os.path.join(naive_dir, "survey_summary.csv"), header, [[q, n, f"{a:.2f}"] for q, (n, a) in nv.items()])
        return
    ws, ref, sol = task_dirs(HERE)
    t = tally(d["subs"])

    def label(a, i):
        if a in ("", NA):
            return a
        lab = LABELS[a]
        return lab.title() if i % 11 == 3 else lab

    rows = []
    for i, s in enumerate(d["subs"]):
        rows.append([s["ts"].strftime("%-m/%-d/%Y %H:%M:%S"), s["email"]] + [label(a, i + j) for j, a in enumerate(s["ans"])])
    write_csv(os.path.join(ws, "member_survey_2026_responses.csv"),
              ["Timestamp", "Email Address"] + [f"{i + 1}. {q}" for i, (q, _) in enumerate(QUESTIONS)], rows)
    last_year = [[f"Q{i + 1}", r_n, f"{a:.2f}"] for i, (r_n, a) in enumerate(
        [(71, 3.41), (74, 4.52), (73, 3.05), (70, 2.66), (61, 2.88), (72, 3.77), (73, 3.12), (58, 3.30), (69, 2.71), (74, 4.08)])]
    write_csv(os.path.join(ws, "survey_summary_2025.csv"), header, last_year)
    write_text(os.path.join(ws, "note_from_amara.txt"),
               "Scoring the member survey\n"
               "\n"
               "Same as last year, please - the 2025 summary is in the folder so you can see the layout. Here is how we\n"
               "score it:\n"
               "\n"
               "- Strongly agree is 5, Agree 4, Neither agree nor disagree 3, Disagree 2, Strongly disagree 1.\n"
               "- Questions 4, 7 and 9 are worded the other way round (agreeing means something is wrong), so score them\n"
               "  in reverse: Strongly agree is 1 up to Strongly disagree 5. That way a higher average is always better\n"
               "  and the board can read the whole column the same way.\n"
               "- N/A isn't a score, and neither is a question someone skipped. Leave them out of both the average and\n"
               "  the number of responses.\n"
               "- A few people filled it in twice. Count each member once, using their last submission - the form\n"
               "  doesn't care about capital letters in the email but they're the same person.\n"
               "- Our own test runs from foundrycommons.co addresses don't count.\n"
               "\n"
               "Save it as survey_summary.csv with question (Q1 to Q10), responses and average (two decimals).\n"
               "\n"
               "Amara\n")

    ref_rows = [[q, n, f"{a:.2f}"] for q, (n, a) in t.items()]
    write_csv(os.path.join(ref, "survey_summary.csv"), header, ref_rows)
    write_csv(os.path.join(sol, "survey_summary.csv"), header, ref_rows)
    write_json(os.path.join(ref, "notes.json"), {"submissions": len(d["subs"]), "members": len({s["email"].lower() for s in d["subs"] if not s["test"]}),
                                                  "unreversed": tally(d["subs"], reverse=False), "keep_first": tally(d["subs"], dedupe="first"),
                                                  "no_dedupe": tally(d["subs"], dedupe=None)})
    write_task_yaml(HERE, {
        "id": "survey-tally", "track": "desk", "category": "spreadsheet",
        "title": "Member survey scores per question",
        "ask": ("The member survey closed - can you score it for the board, question by question? The responses export is "
                "in the folder; save survey_summary.csv the way Amara's note describes.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "questions 4, 7 and 9 are negatively worded and scored in reverse (Strongly agree = 1); scoring them like "
            "the others flips their averages around 3 (check: average per question)",
            "N/A and skipped answers are neither scores nor responses; counting N/A as 0 or as a neutral 3 moves both "
            "the counts and the averages, most on the meeting room and events questions (checks: responses per "
            "question; average per question)",
            "13 members submitted twice, some with the email in capitals on the second go; each counts once with the "
            "last submission, so keeping the first or both moves every count and several averages "
            "(checks: responses per question; average per question)",
            "three staff test runs from foundrycommons.co addresses answer 5 and 1 alternately (check: responses per "
            "question)",
            "question 8 was added on 6 August, so earlier submissions are blank for it and answers mix 'Strongly agree' "
            "with 'Strongly Agree' (check: responses per question)",
            "last year's summary sits in the folder with the same layout and different figures (check: average per question)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "survey_summary.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per question", "path": "survey_summary.csv", "column": "question",
             "ref": "survey_summary.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "survey_summary.csv", "equals_ref": "survey_summary.csv"},
            {"type": "csv_values_match", "name": "responses per question", "path": "survey_summary.csv", "ref": "survey_summary.csv",
             "key": "question", "columns": ["responses"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "average per question", "path": "survey_summary.csv", "ref": "survey_summary.csv",
             "key": "question", "columns": ["average"], "numeric": True, "tolerance": 0.006, "min_accuracy": 1.0,
             "must_match_keys": ["Q4", "Q7", "Q9"]},
        ],
    })
    print(f"seed={seed} submissions={len(d['subs'])}")
    print("truth:", t)
    print("unreversed:", tally(d["subs"], reverse=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_) and half_cent_safe(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
