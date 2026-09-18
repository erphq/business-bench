#!/usr/bin/env python3
"""appointment-no-shows: no-show rate per tutor per month at a tutoring center, under its 24-hour policy.

    python gen.py [--seed N] [--naive DIR]

Business: an after-school tutoring center with a handful of tutors and a booking app parents use directly.
The owner bills late cancellations like no-shows and wants each tutor's no-show rate for the spring term.

Traps (each caught by a check, see task.yaml):
  * the app and the front desk write the outcome five ways for a no-show and three for a kept session
                                                                            (check: no-shows and rate per tutor and month)
  * a family cancellation less than 24 hours before the start is a no-show under the policy; the start time is
    "03/04/2026 4:00 PM" and the cancel time "2026-03-03 17:12", with cases on both sides of the line
                                                                            (check: no-shows and rate per tutor and month)
  * cancellations by the tutor or the center never count, however late      (check: no-shows and rate per tutor and month)
  * double-clicked bookings: the same student, tutor and start time twice   (check: no-shows and rate per tutor and month)
  * cancellations with notice come off the book, so they are not in the denominator (check: no-shows and rate per tutor and month)
  * a session belongs to the month it was scheduled for, not the month it was booked or cancelled
                                                                            (check: no-shows and rate per tutor and month)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MONTHS = ["2026-03", "2026-04", "2026-05"]
TUTORS = [("Grace", "Adeyemi", "Math"), ("Owen", "Fairbanks", "Reading"), ("Lucia", "Ferreira", "Chemistry"),
          ("Samir", "Qureshi", "SAT Prep"), ("Hannah", "Voss", "Writing"), ("Theo", "Lindgren", "Math")]
NEW_TUTOR = ("Maren", "Holt", "Biology")      # starts in April
NOSHOW = ["No-show", "No Show", "NS", "noshow", "Absent - no call"]
KEPT = ["Attended", "Completed", "Present"]
CANCEL = ["Cancelled", "Canceled", "cancelled"]


def mkey(d) -> str:
    return f"{d.year}-{d.month:02d}"


def build(seed: int) -> dict:
    r = rng(seed)
    students = [f"{f} {l}" for f, l in people(r, 70)]
    tutors = [f"{f} {l}" for f, l, _ in TUTORS] + [f"{NEW_TUTOR[0]} {NEW_TUTOR[1]}"]
    sessions = []
    bid = iter(range(51020, 99999, 7))
    for t_i, tutor in enumerate(tutors):
        base_ns = r.uniform(0.04, 0.16)
        day = date(2026, 3, 2) if t_i < len(TUTORS) else date(2026, 4, 6)
        while day <= date(2026, 5, 29):
            if day.weekday() < 5:
                slots = r.sample([15, 16, 17, 18], r.randint(1, 3))
            elif day.weekday() == 5 and t_i % 2 == 0:
                slots = r.sample([9, 10, 11, 12], r.randint(1, 3))
            else:
                slots = []
            for h in slots:
                start = datetime(day.year, day.month, day.day, h, r.choice([0, 0, 30]))
                booked = start - timedelta(days=r.randint(2, 20), hours=r.randint(0, 9), minutes=r.randint(0, 59))
                s = {"id": f"BK-{next(bid)}", "student": r.choice(students), "tutor": tutor, "start": start, "booked": booked,
                     "cancel_at": None, "cancel_by": "", "k": r.random()}
                x = r.random()
                if x < base_ns:
                    s["outcome"] = "noshow"
                elif x < base_ns + 0.12:
                    s["outcome"] = "cancel"
                    s["cancel_by"] = r.choices(["Parent", "Student", "Tutor", "Center"], weights=[55, 15, 18, 12])[0]
                    hours = r.choice([r.uniform(0.5, 23.0), r.uniform(26, 120), r.uniform(26, 120)])
                    s["cancel_at"] = start - timedelta(hours=hours)
                else:
                    s["outcome"] = "kept"
                sessions.append(s)
            day += timedelta(days=1)
    # boundary cancellations on both sides of 24 hours, by families, and late ones by tutors / the center
    by_tutor = {t: [s for s in sessions if s["tutor"] == t and s["outcome"] == "kept"] for t in tutors}
    for t in tutors:
        picks = r.sample(by_tutor[t], 5)
        for s, (hours, who) in zip(picks, [(23.5, "Parent"), (24.75, "Parent"), (20.0, "Tutor"), (-0.25, "Parent"), (13.0, "Center")]):
            s["outcome"] = "cancel"
            s["cancel_by"] = who
            s["cancel_at"] = s["start"] - timedelta(hours=hours)
    # a month-boundary late cancel: a 1 April session cancelled the evening of 31 March
    firsts = [s for s in sessions if s["start"].date() in (date(2026, 4, 1), date(2026, 5, 1)) and s["outcome"] == "kept"]
    for s in firsts[:2]:
        s["outcome"] = "cancel"; s["cancel_by"] = "Parent"
        s["cancel_at"] = s["start"] - timedelta(hours=r.uniform(16, 22))
    # truth outcome per session
    for s in sessions:
        if s["outcome"] == "cancel":
            late = (s["start"] - s["cancel_at"]) < timedelta(hours=24)
            s["counts"] = "noshow" if (late and s["cancel_by"] in ("Parent", "Student")) else "off"
        else:
            s["counts"] = s["outcome"]
    # double-clicked bookings: an identical second row one minute later
    dups = []
    for s in r.sample([s for s in sessions if s["outcome"] == "kept"], 4) + r.sample([s for s in sessions if s["outcome"] == "noshow"], 4):
        d = dict(s)
        d["id"] = f"BK-{next(bid)}"
        d["booked"] = s["booked"] + timedelta(minutes=1)
        d["dup_of"] = s["id"]
        d["k"] = r.random()
        dups.append(d)
    for s in sessions + dups:
        pool = NOSHOW if s["outcome"] == "noshow" else KEPT if s["outcome"] == "kept" else CANCEL
        s["status"] = r.choice(pool)
        if s.get("dup_of"):
            s["status"] = next(x for x in sessions if x["id"] == s["dup_of"])["status"]
    stats = {}
    for s in sessions:
        key = (s["tutor"], mkey(s["start"]))
        st = stats.setdefault(key, {"booked": 0, "noshows": 0})
        if s["counts"] in ("kept", "noshow"):
            st["booked"] += 1
        if s["counts"] == "noshow":
            st["noshows"] += 1
    for st in stats.values():
        st["rate"] = st["noshows"] / st["booked"] if st["booked"] else 0.0
    return {"sessions": sessions, "dups": dups, "stats": stats, "tutors": tutors, "students": students}


def naive_stats(d: dict) -> dict:
    """No-show spellings normalised, every cancellation dropped, duplicates kept, month by booking date."""
    out = {}
    for s in d["sessions"] + d["dups"]:
        key = (s["tutor"], mkey(s["booked"]))
        st = out.setdefault(key, {"booked": 0, "noshows": 0})
        if s["outcome"] == "cancel":
            continue
        st["booked"] += 1
        st["noshows"] += s["outcome"] == "noshow"
    for st in out.values():
        st["rate"] = st["noshows"] / st["booked"] if st["booked"] else 0.0
    return out


def acceptable(d: dict) -> bool:
    st, nv = d["stats"], naive_stats(d)
    if any(v["noshows"] == 0 for v in st.values()):
        return False
    wrong = sum(1 for k, v in st.items() if k not in nv or nv[k]["noshows"] != v["noshows"] or abs(nv[k]["rate"] - v["rate"]) > 0.002)
    # rates must be distinguishable as fraction vs percent and from each other within a tutor
    return wrong >= len(st) - 3 and all(v["rate"] > 0.01 for v in st.values())


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["tutor", "month", "booked", "no_shows", "no_show_rate"]
    if naive_dir:
        nv = naive_stats(d)
        write_csv(os.path.join(naive_dir, "no_show_rates.csv"), header,
                  [[t, m, v["booked"], v["noshows"], f"{v['rate']:.4f}"] for (t, m), v in sorted(nv.items()) if m in MONTHS])
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 29)
    subj = {f"{f} {l}": s for f, l, s in TUTORS + [NEW_TUTOR]}
    rows = []
    seq = 51020
    for s in sorted(d["sessions"] + d["dups"], key=lambda s: (s["booked"], s["k"])):
        start_txt = s["start"].strftime("%m/%d/%Y %I:%M %p").replace(" 0", " ")
        seq += 1 + int(s["k"] * 6)
        rows.append([f"BK-{seq}", s["booked"].strftime("%Y-%m-%d %H:%M"), s["student"], s["tutor"], subj[s["tutor"]], start_txt,
                     "60", s["status"], s["cancel_at"].strftime("%Y-%m-%d %H:%M") if s["cancel_at"] else "", s["cancel_by"]])
    write_csv(os.path.join(ws, "bookings_export_2026-03-01_2026-05-31.csv"),
              ["Booking ID", "Booked On", "Student", "Tutor", "Subject", "Session Start", "Minutes", "Status", "Cancelled At", "Cancelled By"],
              rows, bom=True)
    write_text(os.path.join(ws, "attendance_policy.txt"),
               "Brightpath Learning Center - attendance and cancellation policy (front desk copy)\n"
               "\n"
               "1. Families must cancel at least 24 hours before the session starts. A cancellation with less than 24\n"
               "   hours' notice is billed and recorded as a no-show.\n"
               "2. A cancellation with 24 hours' notice or more takes the session off the book. It is not a no-show and\n"
               "   it is not a booked session.\n"
               "3. If a tutor or the center cancels, it is never held against the family, however late.\n"
               "4. No-show rate = no-shows / sessions on the book (sessions kept + no-shows).\n"
               "5. The booking app sometimes records the same session twice when a parent taps Book twice. Same student,\n"
               "   same tutor, same start time is one session.\n"
               "6. Sessions are reported in the month they were scheduled for.\n")
    win = []
    for f, l, _ in TUTORS:
        for m in ("2025-12", "2026-01", "2026-02"):
            b = r.randint(28, 52)
            n = r.randint(1, 7)
            win.append([f"{f} {l}", m, b, n, f"{n / b:.4f}"])
    write_csv(os.path.join(ws, "no_show_rates_winter_term.csv"), header, win)
    write_text(os.path.join(ws, "note_from_owner.txt"),
               "Can you do the spring version of the winter no-show file? Same layout, one line per tutor per month for\n"
               "March, April and May. Use the policy the way the front desk applies it.\n"
               "\n"
               "- Priyanka\n")
    ref_rows = [[t, m, v["booked"], v["noshows"], f"{v['rate']:.6f}"] for (t, m), v in sorted(d["stats"].items(), key=lambda kv: (d["tutors"].index(kv[0][0]), kv[0][1]))]
    write_csv(os.path.join(ref, "no_show_rates.csv"), header, ref_rows)
    write_csv(os.path.join(sol, "no_show_rates.csv"), header, [row[:4] + [f"{float(row[4]):.4f}"] for row in ref_rows])
    n_late = sum(1 for s in d["sessions"] if s["outcome"] == "cancel" and s["counts"] == "noshow")
    write_json(os.path.join(ref, "notes.json"), {"late_family_cancellations": n_late, "duplicate_rows": len(d["dups"]),
                                                  "tutor_or_center_late_cancels": sum(1 for s in d["sessions"] if s["outcome"] == "cancel"
                                                                                      and s["cancel_by"] in ("Tutor", "Center")
                                                                                      and s["start"] - s["cancel_at"] < timedelta(hours=24))})
    write_task_yaml(HERE, {
        "id": "appointment-no-shows", "track": "desk", "category": "spreadsheet",
        "title": "Spring no-show rates by tutor under the 24-hour policy",
        "ask": ("Priyanka wants the spring no-show rates for each tutor, month by month, from the booking export. Save it as "
                "no_show_rates.csv; her note and the attendance policy are in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "a no-show is written 'No-show', 'No Show', 'NS', 'noshow' or 'Absent - no call' and a kept session 'Attended', "
            "'Completed' or 'Present'; matching one spelling undercounts both sides (check: no-shows and rate per tutor and month)",
            f"{n_late} family cancellations came less than 24 hours before the start and are no-shows under policy rule 1; each "
            "tutor has one at 23.5 hours, one at 24.75 hours and one after the session began, and the start is written "
            "'03/04/2026 4:00 PM' while the cancel time is '2026-03-03 17:12', so a date-only difference gets the boundary wrong "
            "(check: no-shows and rate per tutor and month)",
            "cancellations by the tutor or the center are never no-shows, including the late ones every tutor has "
            "(check: no-shows and rate per tutor and month)",
            "eight sessions were booked twice a minute apart with the same student, tutor, start and status; counting both "
            "inflates the book and the no-shows (check: no-shows and rate per tutor and month)",
            "cancellations with notice come off the book, so the denominator is kept sessions plus no-shows, not every row "
            "(check: no-shows and rate per tutor and month)",
            "the export is sorted by booking time and some April and May sessions were booked or cancelled the month before; "
            "the month is the session's own month (check: no-shows and rate per tutor and month)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "winter file columns", "path": "no_show_rates.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every tutor", "path": "no_show_rates.csv", "column": "tutor", "ref": "no_show_rates.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "one row per tutor and month", "path": "no_show_rates.csv", "equals_ref": "no_show_rates.csv"},
            {"type": "custom", "name": "no-shows and rate per tutor and month", "module": "check.py"},
        ],
    })
    print(f"seed={seed} sessions={len(d['sessions'])} dups={len(d['dups'])} late_family={n_late}")
    nv = naive_stats(d)
    for k, v in sorted(d["stats"].items()):
        print(" ", k, v, nv.get(k))


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
