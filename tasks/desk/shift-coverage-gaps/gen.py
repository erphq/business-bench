#!/usr/bin/env python3
"""shift-coverage-gaps: uncovered operator-hours per day for an answering service's published week.

    python gen.py [--seed N] [--naive DIR]
    python gen.py --list-knobs
    python gen.py --rules 8 --trap-count split=4+cancelled=3 --out DIR    # a harder task; the answer moves
    python gen.py --describe [--rules N ...]                                # content counts of this draw

Business: Lanternline Answering Service in Omaha, a 24/7 after-hours answering service for doctors, vets and
trades. The scheduling app exports the published week one row per shift; the operations manager keeps the
minimum number of operators per time band and wants to know how short each day is before the week starts.

Traps (each caught by a check, see task.yaml):
  * overnight shifts ('11:00 PM - 7:00 AM') cover hours on the next calendar day; Sunday 4 October's night
    shift covers Monday morning, and Sunday 11 October's late hours fall outside the week (check: uncovered hours per day)
  * one shift is still on the schedule but its comment says it was cancelled with no cover (check: uncovered hours per day)
  * split shifts are one row with two pieces ('6:00 AM - 10:00 AM, 5:00 PM - 9:00 PM'); first start to last
    end covers the middle of the day that nobody works              (check: uncovered hours per day)
  * trainees shadow and do not count toward coverage                (check: uncovered hours per day)
  * shortfall is counted per operator per half hour, and extra staff in one band never offsets another
                                                                     (check: uncovered hours per day)
  * the export starts on the Sunday before the week                  (checks: one row per day; row count)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from bizgen.knobs import Knob, KnobSet, add_knob_args, describe_json, output_dirs, parse_knob_args, record  # noqa: E402

# Difficulty knobs (docs/authoring-knobs.md). The defaults are the published task and leave every draw as it was.
KNOBS = KnobSet(
    Knob("rules", "rules", default=5, levels=(5, 6, 7, 8),
         changes="time bands in the minimum-staffing table (5 at the default); each added band splits one with a "
                 "different minimum", measure="rules"),
    Knob("trap_count.split", "trap-count", default=2, levels=(2, 3, 4),
         changes="split shifts written as one row with two pieces", measure="trap_instances.split"),
    Knob("trap_count.cancelled", "trap-count", default=1, levels=(1, 2, 3),
         changes="shifts still on the schedule whose comment says they were cancelled", measure="trap_instances.cancelled"),
)

WEEK = [date(2026, 10, 5) + timedelta(days=i) for i in range(7)]
EXPORT_DAYS = [date(2026, 10, 4)] + WEEK
# (from hour, to hour, weekday need, saturday need, sunday need)
BANDS = [(0, 6, 2, 2, 2), (6, 8, 3, 2, 2), (8, 17, 2, 3, 3), (17, 22, 4, 3, 3), (22, 24, 3, 3, 3)]
TYPES = {  # name: list of (start hour, end hour) pieces, hours may exceed 24 for overnight
    "OVN1": [(22, 30)], "OVN2": [(23, 31)], "EARLY": [(6, 14.5)], "DAY": [(7, 15.5)], "MID": [(9, 17.5)],
    "SWING": [(14, 22.5)], "EVE": [(16, 24.5)], "LATE": [(17, 25.5)], "SPLIT": [(6, 10), (17, 21)], "SPLIT2": [(7, 11), (16, 20)],
}
WEEKDAY_MIX = {"OVN1": (1, 2), "OVN2": (0, 1), "EARLY": (1, 2), "DAY": (0, 1), "MID": (0, 1), "SWING": (1, 2), "EVE": (1, 1), "LATE": (0, 1)}
WEEKEND_MIX = {"OVN1": (1, 2), "OVN2": (0, 1), "EARLY": (0, 1), "DAY": (1, 2), "MID": (1, 1), "SWING": (1, 1), "EVE": (0, 1), "LATE": (0, 1)}
SPLIT_DAYS = {date(2026, 10, 7): "SPLIT", date(2026, 10, 10): "SPLIT2"}
CANCEL_DAY = date(2026, 10, 8)
TRAINEE_DAY = date(2026, 10, 9)
# Minimum-staffing tables with more bands (knob "rules"): each level splits one more band of the published table.
BAND_SETS = {
    6: [(0, 6, 2, 2, 2), (6, 8, 3, 2, 2), (8, 12, 2, 3, 3), (12, 17, 3, 3, 3), (17, 22, 4, 3, 3), (22, 24, 3, 3, 3)],
    7: [(0, 6, 2, 2, 2), (6, 8, 3, 2, 2), (8, 12, 2, 3, 3), (12, 17, 3, 3, 3), (17, 20, 4, 3, 3), (20, 22, 4, 4, 3),
        (22, 24, 3, 3, 3)],
    8: [(0, 4, 2, 2, 2), (4, 6, 3, 2, 2), (6, 8, 3, 2, 2), (8, 12, 2, 3, 3), (12, 17, 3, 3, 3), (17, 20, 4, 3, 3),
        (20, 22, 4, 4, 3), (22, 24, 3, 3, 3)],
}
CANCEL_NOTES = ["CANCELLED - no-show, nobody picked it up", "CANCELLED - family emergency, open shift not filled"]


def need(d: date, slot: int, bands=BANDS) -> int:
    h = slot / 2
    for a, b, wk, sat, sun in bands:
        if a <= h < b:
            return sun if d.weekday() == 6 else sat if d.weekday() == 5 else wk
    raise ValueError


def fmt_t(h: float) -> str:
    h = h % 24
    hh, mm = int(h), int(round((h - int(h)) * 60))
    return datetime(2026, 1, 1, hh, mm).strftime("%I:%M %p").lstrip("0")


def span(s: dict) -> tuple[datetime, datetime]:
    base = datetime.combine(s["date"], datetime.min.time())
    return base + timedelta(hours=TYPES[s["type"]][0][0]), base + timedelta(hours=TYPES[s["type"]][-1][1])


def build(seed: int, knobs=KNOBS.defaults()) -> dict:
    r = rng(seed)
    staff = [f"{f} {l}" for f, l in people(r, 20)]
    shifts = []
    for d in EXPORT_DAYS:
        mix = WEEKEND_MIX if d.weekday() >= 5 else WEEKDAY_MIX
        for t, (lo, hi) in mix.items():
            for _ in range(r.randint(lo, hi)):
                shifts.append({"date": d, "type": t, "pos": "Operator", "comment": ""})
        if d in SPLIT_DAYS:
            shifts.append({"date": d, "type": SPLIT_DAYS[d], "pos": "Operator", "comment": "split"})
        if d == TRAINEE_DAY:
            shifts.append({"date": d, "type": "SWING", "pos": "Trainee", "comment": "shadowing Friday evening"})
    # the cancelled shift: an evening shift on the cancel day
    cands = [s for s in shifts if s["date"] == CANCEL_DAY and s["type"] in ("SWING", "EVE")]
    r.choice(cands)["comment"] = "CANCELLED - called out sick, no cover found"
    # supervisors take calls too
    for s in r.sample([s for s in shifts if s["type"] in ("DAY", "MID", "SWING") and s["pos"] == "Operator"], 4):
        s["pos"] = "Supervisor"
    # assign people so nobody works two shifts within 8 hours
    shifts.sort(key=lambda s: (s["date"], TYPES[s["type"]][0][0], s["type"]))
    free_at = {p: datetime(2026, 10, 1) for p in staff}
    for s in shifts:
        start = datetime.combine(s["date"], datetime.min.time()) + timedelta(hours=TYPES[s["type"]][0][0])
        end = datetime.combine(s["date"], datetime.min.time()) + timedelta(hours=TYPES[s["type"]][-1][1])
        ok = [p for p in staff if free_at[p] + timedelta(hours=8) <= start]
        p = min(ok, key=lambda p: (free_at[p], staff.index(p))) if r.random() < 0.5 else r.choice(ok)
        s["who"] = p
        free_at[p] = end
    if knobs.canonical:
        return {"shifts": shifts, "staff": staff, "bands": BANDS, "split_days": list(SPLIT_DAYS), "cancel_days": [CANCEL_DAY]}

    # knob-only content, drawn from its own stream after every default draw (none of this runs at the defaults)
    rk = rng(seed + 3_000_017)
    split_days = list(SPLIT_DAYS)
    cancel_days = [CANCEL_DAY]
    for x in sorted(rk.sample([x for x in WEEK if x not in SPLIT_DAYS], knobs.trap_count("split") - 2)):
        s = {"date": x, "type": rk.choice(["SPLIT", "SPLIT2"]), "pos": "Operator", "comment": "split"}
        start, end = span(s)
        # someone with 8 hours' rest either side of the split day
        ok = [p for p in staff if all(e + timedelta(hours=8) <= start or end + timedelta(hours=8) <= b
                                      for b, e in (span(t) for t in shifts if t["who"] == p))]
        s["who"] = rk.choice(ok)
        shifts.append(s)
        split_days.append(x)
    for i, x in enumerate(sorted(rk.sample([x for x in WEEK if x != CANCEL_DAY], knobs.trap_count("cancelled") - 1))):
        cands = [s for s in shifts if s["date"] == x and s["type"] in ("SWING", "EVE") and s["pos"] == "Operator" and not s["comment"]]
        rk.choice(cands)["comment"] = CANCEL_NOTES[i]
        cancel_days.append(x)
    shifts.sort(key=lambda s: (s["date"], TYPES[s["type"]][0][0], s["type"]))
    return {"shifts": shifts, "staff": staff, "bands": BAND_SETS.get(knobs["rules"], BANDS), "split_days": split_days,
            "cancel_days": cancel_days}


def coverage(shifts, cancelled=False, split_whole=False, clip_midnight=False, trainees=False, bands=BANDS) -> dict:
    staffed = {d: [0] * 48 for d in WEEK}
    for s in shifts:
        if s["comment"].startswith("CANCELLED") and not cancelled:
            continue
        if s["pos"] == "Trainee" and not trainees:
            continue
        pieces = TYPES[s["type"]]
        if split_whole:
            pieces = [(pieces[0][0], pieces[-1][1])]
        for a, b in pieces:
            if clip_midnight:
                b = min(b, 24)
            k = a
            while k < b:
                day = s["date"] + timedelta(days=int(k // 24))
                if day in staffed:
                    staffed[day][int((k % 24) * 2)] += 1
                k += 0.5
    return {d: sum(max(0, need(d, i, bands) - staffed[d][i]) * 0.5 for i in range(48)) for d in WEEK}


def acceptable(d: dict) -> bool:
    bands = d["bands"]
    truth = coverage(d["shifts"], bands=bands)
    if sum(1 for v in truth.values() if v > 0) < 5:
        return False
    variants = {"cancelled": (coverage(d["shifts"], cancelled=True, bands=bands), d["cancel_days"]),
                "split": (coverage(d["shifts"], split_whole=True, bands=bands), d["split_days"]),
                "clip": (coverage(d["shifts"], clip_midnight=True, bands=bands), [WEEK[0]]),
                "trainee": (coverage(d["shifts"], trainees=True, bands=bands), [TRAINEE_DAY])}
    for name, (cov, days) in variants.items():
        if any(cov[x] == truth[x] for x in days):
            return False
    # a netting reading (a day's required hours minus its staffed hours) differs on most days
    if sum(1 for x in WEEK if netting(d["shifts"], bands)[x] != truth[x]) < 4:
        return False
    return True


def netting(shifts, bands=BANDS) -> dict:
    staffed = {d: [0] * 48 for d in WEEK}
    for s in shifts:
        if s["comment"].startswith("CANCELLED") or s["pos"] == "Trainee":
            continue
        for a, b in TYPES[s["type"]]:
            k = a
            while k < b:
                day = s["date"] + timedelta(days=int(k // 24))
                if day in staffed:
                    staffed[day][int((k % 24) * 2)] += 1
                k += 0.5
    return {d: max(0.0, sum(need(d, i, bands) - staffed[d][i] for i in range(48)) * 0.5) for d in WEEK}


def counts(d: dict, knobs) -> dict:
    """--describe: what this draw contains."""
    sh = d["shifts"]
    return {"rows": len(sh), "entities": len(d["staff"]), "rules": len(d["bands"]), "documents": 3,
            "trap_instances": {"split": sum(len(TYPES[s["type"]]) > 1 for s in sh),
                               "cancelled": sum(s["comment"].startswith("CANCELLED") for s in sh),
                               "trainee": sum(s["pos"] == "Trainee" for s in sh)}}


def emit(seed: int, naive_dir: str | None, knobs=KNOBS.defaults(), out: str | None = None) -> None:
    d = build(seed, knobs)
    bands = d["bands"]
    truth = coverage(d["shifts"], bands=bands)
    header = ["date", "uncovered_hours"]
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        nv = coverage(d["shifts"], cancelled=True, split_whole=True, clip_midnight=True, trainees=True, bands=bands)
        write_csv(os.path.join(naive_dir, "coverage_gaps.csv"), header, [[x.isoformat(), f"{nv[x]:g}"] for x in WEEK])
        return
    here, (ws, ref, sol) = output_dirs(HERE, out, task_dirs)

    rows = []
    for s in d["shifts"]:
        pieces = TYPES[s["type"]]
        text = ", ".join(f"{fmt_t(a)} - {fmt_t(b)}" for a, b in pieces)
        hours = sum(b - a for a, b in pieces) - (0.5 if len(pieces) == 1 and pieces[0][1] - pieces[0][0] >= 8.5 else 0)
        rows.append([s["who"], s["pos"], f"{s['date'].month:02d}/{s['date'].day:02d}/{s['date'].year}", s["date"].strftime("%a"),
                     text, f"{hours:.2f}", "" if s["comment"] == "split" else s["comment"]])
    write_csv(os.path.join(ws, "published_schedule_2026-10-04_to_2026-10-11.csv"),
              ["Employee", "Position", "Date", "Day", "Shift", "Paid Hours", "Comments"], rows, bom=True, crlf=True)
    band_rows = [[f"{a:02d}:00", f"{b:02d}:00" if b < 24 else "24:00 (midnight)", wk, sat, sun] for a, b, wk, sat, sun in bands]
    write_xlsx(os.path.join(ws, "minimum_coverage.xlsx"), {"Minimum operators": {
        "merged_title": "Minimum operators on the phones", "header": ["From", "To", "Mon-Fri", "Saturday", "Sunday"],
        "rows": band_rows, "widths": {"A": 10, "B": 18}}}, creator="Gwen Foster")
    write_text(os.path.join(ws, "note_from_gwen.txt"),
               "Coverage check before the week of October 5\n"
               "\n"
               "The schedule for Monday 5 October to Sunday 11 October is published. Before it goes live I want to know\n"
               "how short we are each day against the minimums on my coverage sheet.\n"
               "\n"
               "How to count it:\n"
               "- Work through each day in half hours. For every half hour, compare how many people are on the phones\n"
               "  with the minimum for that time. Each missing person for a half hour is half an uncovered hour - if we\n"
               "  need 4 and have 2, that half hour is a whole uncovered hour. Having extra people at one time doesn't\n"
               "  make up for being short at another.\n"
               "- Hours belong to the calendar day they fall on. Night shifts run past midnight, so a shift that starts\n"
               "  Sunday night covers Monday morning. The export starts with Sunday the 4th for that reason.\n"
               "- Operators and supervisors both take calls. Trainees are shadowing and don't count.\n"
               "- Some people work a split day; the app puts both pieces in one row. They're off between the pieces.\n"
               "- If a comment says a shift was cancelled, it isn't happening, even if the app still shows it.\n"
               "\n"
               "Save it as coverage_gaps.csv with one line per day, Monday to Sunday: date (like 2026-10-05) and\n"
               "uncovered_hours.\n"
               "\n"
               "Gwen\n")

    ref_rows = [[x.isoformat(), f"{truth[x]:g}"] for x in WEEK]
    write_csv(os.path.join(ref, "coverage_gaps.csv"), header, ref_rows)
    write_csv(os.path.join(sol, "coverage_gaps.csv"), header, ref_rows)
    notes = {
        "variants": {k: {x.isoformat(): v for x, v in cov.items()} for k, cov in (
            ("cancelled_counted", coverage(d["shifts"], cancelled=True, bands=bands)),
            ("split_as_one_block", coverage(d["shifts"], split_whole=True, bands=bands)),
            ("overnight_clipped_at_midnight", coverage(d["shifts"], clip_midnight=True, bands=bands)),
            ("trainee_counted", coverage(d["shifts"], trainees=True, bands=bands)))},
        "cancel_day": CANCEL_DAY.isoformat(), "split_days": [x.isoformat() for x in d["split_days"]], "trainee_day": TRAINEE_DAY.isoformat()}
    if len(d["cancel_days"]) > 1:
        notes["cancel_days"] = [x.isoformat() for x in d["cancel_days"]]
    write_json(os.path.join(ref, "notes.json"), notes)
    # With more planted instances the trap sentences name them all (the sentences are unchanged at the defaults).
    cancel_text = (f"a shift on {CANCEL_DAY.isoformat()} still appears with its hours but the comment says it was cancelled "
                   if len(d["cancel_days"]) == 1 else
                   f"shifts on {', '.join(x.isoformat() for x in sorted(d['cancel_days']))} still appear with their hours but the comments "
                   "say they were cancelled ")

    spec = {
        "id": "shift-coverage-gaps", "track": "desk", "category": "spreadsheet",
        "title": "How short the published week is against minimum coverage",
        "ask": ("Before next week's schedule goes live, Gwen wants to know how many hours we're short each day against "
                "her minimums. Use the published schedule and her coverage sheet and save coverage_gaps.csv - her note "
                "says how to count.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "night shifts ('10:00 PM - 6:00 AM', '11:00 PM - 7:00 AM', '5:00 PM - 1:30 AM') cover the next calendar "
            "day; Sunday 4 October's night shifts are the only cover early on Monday 5 October, and cutting shifts at "
            "midnight or dropping the Sunday rows leaves Monday badly short (check: uncovered hours per day)",
            f"{cancel_text}"
            "with no cover (check: uncovered hours per day)",
            f"split shifts on {', '.join(x.isoformat() for x in sorted(d['split_days']))} are one row with two pieces; reading "
            "first start to last end puts someone on the phones through the middle of the day "
            "(check: uncovered hours per day)",
            f"a trainee shadows the {TRAINEE_DAY.isoformat()} evening and does not count, while supervisors do "
            "(check: uncovered hours per day)",
            "shortfall is per missing operator per half hour; netting a day's staffed hours against its required "
            "hours lets surplus in one band hide a gap in another, and the Paid Hours column deducts a half-hour break "
            "that does not leave the phones empty (check: uncovered hours per day)",
            "the export starts on Sunday 4 October for the night shift, so a day-per-row output that keeps that date "
            "has eight rows (checks: one row per day; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "coverage_gaps.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per day", "path": "coverage_gaps.csv", "column": "date",
             "ref": "coverage_gaps.csv", "normalize": ["strip"]},
            {"type": "csv_row_count", "name": "row count", "path": "coverage_gaps.csv", "equals_ref": "coverage_gaps.csv"},
            {"type": "csv_values_match", "name": "uncovered hours per day", "path": "coverage_gaps.csv", "ref": "coverage_gaps.csv",
             "key": "date", "columns": ["uncovered_hours"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0},
        ],
    }
    write_task_yaml(here, record(spec, "shift-coverage-gaps", seed, knobs))
    print(f"seed={seed} shifts={len(d['shifts'])}")
    print("truth:", {x.isoformat(): v for x, v in truth.items()})
    print("naive:", {x.isoformat(): v for x, v in coverage(d["shifts"], True, True, True, True, bands).items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    add_knob_args(ap, KNOBS)
    a = ap.parse_args()
    knobs = parse_knob_args(a, KNOBS)
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt, knobs)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    if a.describe:
        print(describe_json("shift-coverage-gaps", a.seed * 1000 + attempt, knobs, counts(d_, knobs)))
        raise SystemExit(0)
    emit(a.seed * 1000 + attempt, a.naive, knobs, a.out)
