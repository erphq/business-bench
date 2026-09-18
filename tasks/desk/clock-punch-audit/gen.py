#!/usr/bin/env python3
"""clock-punch-audit: a week of time-clock punches to hours per person per day, with missing punches flagged.

    python gen.py [--seed N] [--naive DIR]

Business: a wholesale bakery. The night crew starts at 9-11pm and clocks out after sunrise, the counter works
days, the driver clocks out between morning and afternoon runs. Payroll wants a clean day-by-day hours audit.

Traps (each caught by a check, see task.yaml):
  * overnight shifts cross midnight and belong to the day they started      (check: daily hours per person)
  * the export starts with outs from last week's Sunday night shift and runs to Monday noon,
    so it holds next week's first punches                                  (checks: daily hours per person; row count)
  * double taps a minute or two apart count once                            (check: daily hours per person)
  * a missing out-punch is flagged with no hours, not filled from the schedule (check: missing punches flagged)
  * a missing in-punch likewise                                             (check: missing punches flagged)
  * the driver's two runs on one day are added, not first-in to last-out   (check: daily hours per person)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

WEEK0 = date(2026, 8, 31)          # Monday
DAYS = [WEEK0 + timedelta(days=i) for i in range(7)]
EXPORT_FROM = datetime(2026, 8, 31, 0, 0)
EXPORT_TO = datetime(2026, 9, 7, 12, 0)

# badge, role, pattern: list of (day offsets from WEEK0, [(start "HH:MM", minutes), ...])
STAFF = [
    ("1041", "Night baker", [((-1, 0, 1, 2, 3), [("22:00", 510)])]),
    ("1047", "Night baker", [((0, 1, 2, 3, 4), [("23:00", 450)])]),
    ("1052", "Weekend night baker", [((4, 5, 6), [("21:00", 540)])]),
    ("1063", "Counter (early)", [((0, 1, 2, 3, 4), [("06:00", 510)])]),
    ("1066", "Counter (late)", [((2, 3, 4, 5, 6), [("11:00", 510)])]),
    ("1070", "Counter (weekend)", [((5, 6, 7), [("07:00", 480)])]),
    ("1078", "Delivery driver", [((0, 1, 2, 3, 4, 5, 7), [("05:30", 240), ("15:00", 180)])]),
    ("1083", "Cake decorator", [((1, 2, 3, 4, 5), [("08:00", 510)])]),
    ("1089", "Porter", [((0, 2, 4), [("16:00", 390)])]),
]


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, len(STAFF))
    staff = [{"badge": b, "role": role, "name": f"{f} {l}", "pattern": pat} for (b, role, pat), (f, l) in zip(STAFF, names)]
    shifts = []   # {badge, start, end, sched_start, sched_end}
    for s in staff:
        for offs, parts in s["pattern"]:
            for off in offs:
                day = WEEK0 + timedelta(days=off)
                for hhmm, mins in parts:
                    h, m = map(int, hhmm.split(":"))
                    sched = datetime(day.year, day.month, day.day, h, m)
                    start = sched + timedelta(minutes=r.randint(-9, 6))
                    end = sched + timedelta(minutes=mins + r.randint(-4, 12))
                    shifts.append({"badge": s["badge"], "start": start, "end": end, "sched": sched,
                                   "sched_end": sched + timedelta(minutes=mins), "day": day})
    # trap placement
    by = lambda b, off, i=0: [x for x in shifts if x["badge"] == b and x["day"] == WEEK0 + timedelta(days=off)][i]  # noqa: E731
    miss_out = [by("1047", r.choice([1, 2])), by("1066", r.choice([3, 4]))]
    miss_in = [by("1083", r.choice([2, 4]))]
    for x in miss_out: x["missing"] = "out"
    for x in miss_in: x["missing"] = "in"
    punches = []   # {badge, ts, dir, source}
    for x in shifts:
        if x.get("missing") != "in":
            punches.append({"badge": x["badge"], "ts": x["start"], "dir": "In", "source": "Kiosk"})
        if x.get("missing") != "out":
            punches.append({"badge": x["badge"], "ts": x["end"], "dir": "Out", "source": "Kiosk"})
    # a manager-added out punch (a legitimate correction, it counts)
    mgr = by("1063", r.choice([1, 2]))
    for p in punches:
        if p["badge"] == mgr["badge"] and p["ts"] == mgr["end"]:
            p["source"] = "Manager add"
    # double taps
    dup_targets = [(by("1047", 3), "In"), (by("1063", 4), "Out"), (by("1078", 2, 1), "In"), (by("1052", 5), "Out")]
    for x, direction in dup_targets:
        ts = x["start"] if direction == "In" else x["end"]
        punches.append({"badge": x["badge"], "ts": ts + timedelta(minutes=r.randint(1, 3), seconds=0), "dir": direction,
                        "source": "Kiosk", "dup": True})
    punches = [p for p in punches if EXPORT_FROM <= p["ts"] <= EXPORT_TO]
    punches.sort(key=lambda p: (p["ts"], p["badge"]))

    # ---- truth: shifts that started Mon-Sun of this week ----
    name_of = {s["badge"]: s["name"] for s in staff}
    rows = {}
    for x in shifts:
        if not (WEEK0 <= x["day"] <= DAYS[-1]):
            continue
        key = (x["badge"], x["day"])
        row = rows.setdefault(key, {"badge": x["badge"], "name": name_of[x["badge"]], "date": x["day"], "mins": 0, "flag": ""})
        if x.get("missing"):
            row["flag"] = f"MISSING {x['missing'].upper()}"
        else:
            row["mins"] += int((x["end"] - x["start"]).total_seconds() // 60)
    out = []
    for key in sorted(rows, key=lambda k: (k[0], k[1])):
        row = rows[key]
        hours = "" if row["flag"] else round(row["mins"] / 60.0, 2)
        out.append({"badge": row["badge"], "name": row["name"], "date": row["date"], "hours": hours, "flag": row["flag"]})
    return {"staff": staff, "shifts": shifts, "punches": punches, "out": out, "miss_out": miss_out, "miss_in": miss_in}


def acceptable(d: dict) -> bool:
    names = [s["name"] for s in d["staff"]]
    last = [n.split()[1] for n in names]
    return len(set(last)) == len(last)


def naive_rows(d: dict) -> list[list]:
    """Group punches by calendar date, first In to last Out; a missing punch is filled from the schedule."""
    name_of = {s["badge"]: s["name"] for s in d["staff"]}
    groups = {}
    for p in d["punches"]:
        groups.setdefault((p["badge"], p["ts"].date()), []).append(p)
    rows = []
    for (b, day), ps in sorted(groups.items()):
        ins = [p["ts"] for p in ps if p["dir"] == "In"]
        outs = [p["ts"] for p in ps if p["dir"] == "Out"]
        if ins and outs and max(outs) > min(ins):
            hrs = (max(outs) - min(ins)).total_seconds() / 3600
        else:
            hrs = 8.0
        rows.append([b, name_of[b], day.isoformat(), f"{hrs:.2f}", ""])
    return rows


HEADER = ["badge", "name", "date", "hours", "flag"]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_csv(os.path.join(naive_dir, "hours_audit.csv"), HEADER, naive_rows(d))
        return
    ws, ref, sol = task_dirs(HERE)
    name_of = {s["badge"]: s["name"] for s in d["staff"]}
    terminals = {"In": ["Back door", "Back door", "Front counter"], "Out": ["Back door", "Front counter", "Back door"]}
    prow = []
    for i, p in enumerate(d["punches"]):
        t = p["ts"]
        prow.append([p["badge"], name_of[p["badge"]], t.strftime("%m/%d/%Y"), t.strftime("%I:%M %p").lstrip("0"),
                     p["dir"], terminals[p["dir"]][(int(p["badge"]) + i) % 3], p["source"]])
    write_csv(os.path.join(ws, "timeclock_export_2026-08-31_to_09-07.csv"),
              ["Badge #", "Employee Name", "Punch Date", "Punch Time", "In/Out", "Terminal", "Source"], prow,
              preamble=["TimeClock Plus - Punch Detail", "Range: 08/31/2026 12:00 AM - 09/07/2026 12:00 PM"], crlf=True)
    sched_rows = []
    for x in sorted(d["shifts"], key=lambda z: (z["sched"], z["badge"])):
        if WEEK0 <= x["day"] <= DAYS[-1]:
            sched_rows.append([x["day"], x["day"].strftime("%a"), name_of[x["badge"]],
                               x["sched"].strftime("%H:%M"), x["sched_end"].strftime("%H:%M"),
                               next(s["role"] for s in d["staff"] if s["badge"] == x["badge"])])
    write_xlsx(os.path.join(ws, "schedule_week_of_aug31.xlsx"), {"Schedule": {
        "merged_title": "Posted schedule - week of Aug 31",
        "header": ["Date", "Day", "Employee", "Start", "End", "Position"], "rows": sched_rows,
        "widths": {"A": 12, "C": 22, "F": 22}}}, creator="Manager")
    write_text(os.path.join(ws, "note_from_bea.txt"), (
        "Payroll for the week of Aug 31 (Mon) through Sep 6 (Sun)\n\n"
        "I exported the punches from the clock. It runs from Monday midnight to the following Monday noon so the "
        "night crew's clock-outs on Monday morning are in there.\n\n"
        "How I count it:\n"
        "- A shift belongs to the day it started. The bakers who start at night get the whole shift on that day.\n"
        "- Anything that started before Monday the 31st was last week and is already paid. Anything that "
        "starts on Monday the 7th is next week.\n"
        "- The clock sometimes records the same tap twice a minute or two apart. That is one punch, the first one.\n"
        "- If someone forgot to punch in or out, do NOT fill it in from the schedule and do not guess. Put the "
        "day in with the hours empty and write MISSING IN or MISSING OUT in the flag so I can ask them.\n\n"
        "What I need back: hours_audit.csv, one line per person per day they worked, with columns badge, name, "
        "date (2026-08-31 style), hours (decimal, two places, e.g. 8.25) and flag. Leave the flag empty when "
        "the day is fine.\n\n"
        "- Bea\n"))

    rows = [[o["badge"], o["name"], o["date"].isoformat(), "" if o["hours"] == "" else f"{o['hours']:.2f}", o["flag"]]
            for o in d["out"]]
    write_csv(os.path.join(ref, "hours_audit.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "hours_audit.csv"), HEADER, rows)
    write_json(os.path.join(ref, "notes.json"), {
        "missing_out": [[x["badge"], x["day"].isoformat()] for x in d["miss_out"]],
        "missing_in": [[x["badge"], x["day"].isoformat()] for x in d["miss_in"]],
        "names": name_of})
    write_task_yaml(HERE, {
        "id": "clock-punch-audit", "track": "desk", "category": "spreadsheet",
        "title": "Weekly hours audit from time-clock punches",
        "ask": ("Bea needs last week's hours from the time clock before she runs payroll. Turn the punch export into "
                "hours_audit.csv; her note says how she counts shifts.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the night bakers clock in at 9-11pm and out after 6am, so grouping punches by calendar date splits every "
            "night shift into an in-only day and an out-only day; the shift belongs to the day it started "
            "(check: daily hours per person)",
            "the export opens with a Monday-morning out from last week's Sunday night shift and runs to noon on "
            "Monday 7 September, so it also holds the driver's first run and a counter clock-in from next week; "
            "none of these are this week's days (checks: daily hours per person; row count)",
            "four punches were recorded twice one to three minutes apart; pairing them in sequence creates "
            "zero-length shifts and throws every later pairing for that person off by one "
            "(check: daily hours per person)",
            "two people forgot to clock out; the posted schedule in the folder makes it easy to fill the out-punch "
            "in, but the note wants the day flagged MISSING OUT with no hours (check: missing punches flagged)",
            "the decorator forgot to clock in one day and only the out-punch exists (check: missing punches flagged)",
            "the delivery driver clocks out between the morning and afternoon runs; first-in to last-out on a "
            "driver day pays the three-hour gap (check: daily hours per person)",
            "times are 12-hour ('10:04 PM') under a two-line preamble, and one out-punch was added by a manager, "
            "which counts (check: daily hours per person)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "hours_audit.csv", "columns": HEADER},
            {"type": "csv_row_count", "name": "row count", "path": "hours_audit.csv", "equals_ref": "hours_audit.csv"},
            {"type": "custom", "name": "daily hours per person", "module": "check.py"},
            {"type": "custom", "name": "missing punches flagged", "module": "check_flags.py"},
        ],
    })
    print(f"seed={seed} punches={len(d['punches'])} rows={len(rows)} flagged={[r_ for r_ in rows if r_[4]]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
