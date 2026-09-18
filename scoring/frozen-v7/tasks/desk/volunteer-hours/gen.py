#!/usr/bin/env python3
"""volunteer-hours: a food bank's tablet sign-ins and typed-up paper sheets -> hours per volunteer per program.

    python gen.py [--seed N] [--naive DIR]

Business: Eastside Community Food Bank reports volunteer hours to the county for July and August on the county's
template: one row per volunteer (roster id), a column of hours for each program and a total.

Traps (each caught by a check, see task.yaml):
  * people sign in under nicknames, "Last, First", initials and odd capitalisation; the roster resolves them to one id
                                                                                   (checks: volunteers who served; every program)
  * overnight shelter shifts run 9pm to 7am, so time out is earlier than time in    (check: overnight shelter hours)
  * some shifts were signed on both the tablet and the paper sheet, and the tablet double-records a few taps;
    a shift counts once                                                              (check: pantry and tutoring hours)
  * staff sign in on the same sheets and are not volunteers                         (check: volunteers who served)
  * the paper clipboards run into the first week of September                        (check: meal delivery hours)
  * paper sheets use a 12-hour clock ("9:15 PM"), the tablet a 24-hour clock        (check: total hours)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

NICK = {"Robert": "Bob", "William": "Bill", "Elizabeth": "Liz", "Jennifer": "Jen", "Michael": "Mike", "Christopher": "Chris",
        "Margaret": "Maggie", "Richard": "Rick", "Daniel": "Dan", "Patricia": "Trish", "Joseph": "Joe", "Thomas": "Tom",
        "Susan": "Sue", "Anthony": "Tony", "Kimberly": "Kim", "Rebecca": "Becky", "Steven": "Steve", "Matthew": "Matt",
        "Nicholas": "Nick", "Deborah": "Deb", "Kenneth": "Ken", "Timothy": "Tim", "Jonathan": "Jon", "Dorothy": "Dot"}
PROGRAMS = ["pantry", "meal_delivery", "overnight_shelter", "tutoring"]
TABLET_NAME = {"pantry": "Food Pantry", "meal_delivery": "Meal Delivery", "overnight_shelter": "Overnight Shelter", "tutoring": "Youth Tutoring"}
PAPER_SHEET = {"pantry": "Pantry", "meal_delivery": "Delivery drivers", "overnight_shelter": "Shelter overnight", "tutoring": "Tutoring"}
# program -> (weekdays, start hh:mm, end hh:mm)
SCHED = {"pantry": ((1, 3, 5), (9, 0), (12, 0)), "meal_delivery": ((0, 2, 4), (10, 30), (13, 30)),
         "overnight_shelter": ((4, 5), (21, 0), (7, 0)), "tutoring": ((0, 2), (15, 30), (17, 30))}
HEADER = ["volunteer_id", "volunteer_name", "pantry_hours", "meal_delivery_hours", "overnight_shelter_hours", "tutoring_hours", "total_hours"]


def hours(tin: tuple, tout: tuple) -> float:
    a, b = tin[0] * 60 + tin[1], tout[0] * 60 + tout[1]
    if b <= a:
        b += 24 * 60
    return (b - a) / 60


def build(seed: int) -> dict:
    r = rng(seed)
    firsts = [f for f in FIRST if f not in NICK.values()]
    roster, used = [], set()
    nick_pool = list(NICK)
    while len(roster) < 27:
        kind = "Staff" if len(roster) >= 24 else "Volunteer"
        f = r.choice(nick_pool) if (kind == "Volunteer" and r.random() < 0.45) else r.choice(firsts)
        l = r.choice(LAST)
        pref = NICK.get(f) if r.random() < 0.85 else None
        keys = {(f[0], l), (f, l)} | ({(pref, l)} if pref else set())
        if any(k in used for k in keys) or l in {x["last"] for x in roster}:
            continue
        used |= keys
        roster.append({"first": f, "last": l, "pref": pref, "kind": kind, "email": email_for(r, f, l)})
    r.shuffle(roster)
    for i, p in enumerate(roster):
        p["id"] = f"V-{1040 + i * 3 + r.randint(0, 2)}"
    vols = [p for p in roster if p["kind"] == "Volunteer"]
    staff = [p for p in roster if p["kind"] == "Staff"]
    inactive = vols[-3:]            # on the roster, never signed in
    active = vols[:-3]
    sessions = []                   # truth sessions (who, program, date, tin, tout)
    days = [date(2026, 7, 1) + timedelta(days=i) for i in range(62)]
    for k, p in enumerate(active):
        progs = r.sample(PROGRAMS, r.choice([1, 1, 2]))
        if k < 5 and "overnight_shelter" not in progs:
            progs[0] = "overnight_shelter"
        if 5 <= k < 10 and "pantry" not in progs:
            progs[-1] = "pantry"
        for prog in progs:
            wd, st, en = SCHED[prog]
            cands = [d for d in days if d.weekday() in wd and not (prog == "overnight_shelter" and d == date(2026, 8, 31))]
            for d in sorted(r.sample(cands, r.randint(3, 8))):
                s_min = st[0] * 60 + st[1] + r.choice([0, 0, 0, 15, 30, -15])
                e_min = en[0] * 60 + en[1] + r.choice([0, 0, 0, 15, -15, -30])
                sessions.append({"who": p, "prog": prog, "date": d, "tin": divmod(s_min % 1440, 60), "tout": divmod(e_min % 1440, 60), "k": r.random()})
    staff_sessions = []
    for p, prog in zip(staff, ["overnight_shelter", "pantry", "meal_delivery"]):
        wd, st, en = SCHED[prog]
        for d in sorted(r.sample([d for d in days if d.weekday() in wd and d != date(2026, 8, 31)], 6)):
            staff_sessions.append({"who": p, "prog": prog, "date": d, "tin": st, "tout": en, "k": r.random()})
    sept = []
    for p in r.sample([x for x in active], 5):
        prog = "meal_delivery"
        d = r.choice([date(2026, 9, 2), date(2026, 9, 4)])
        sept.append({"who": p, "prog": prog, "date": d, "tin": (10, 30), "tout": (13, 30), "k": r.random()})
    # recording: tablet or paper; some on both; some tablet double taps
    tablet, paper = [], []
    for s in sessions + staff_sessions:
        u = r.random()
        if u < 0.14:
            tablet.append(s); paper.append(s); s["dup"] = "both"
        elif u < 0.62:
            tablet.append(s)
            if r.random() < 0.08:
                tablet.append(s); s["dup"] = "tap"
        else:
            paper.append(s)
    paper += sept
    per = {p["id"]: {g: 0.0 for g in PROGRAMS} for p in active}
    for s in sessions:
        per[s["who"]["id"]][s["prog"]] += hours(s["tin"], s["tout"])
    return {"roster": roster, "active": active, "staff": staff, "inactive": inactive, "sessions": sessions, "staff_sessions": staff_sessions,
            "sept": sept, "tablet": tablet, "paper": paper, "per": per}


def acceptable(d: dict) -> bool:
    s = d["sessions"]
    shelter_people = {x["who"]["id"] for x in s if x["prog"] == "overnight_shelter"}
    dup_pantry_tut = [x for x in s if x.get("dup") and x["prog"] in ("pantry", "tutoring")]
    dup_any = [x for x in s if x.get("dup")]
    if len(shelter_people) < 4 or len(dup_pantry_tut) < 3 or len(dup_any) < 8:
        return False
    if not any(x.get("dup") == "tap" for x in s) or not any(x.get("dup") == "both" for x in s):
        return False
    # every September row belongs to someone who also delivers meals in the period? not required; they must change a total
    if not all(d["per"][x["who"]["id"]]["meal_delivery"] >= 0 for x in d["sept"]):
        return False
    # nicknames must actually be used by people who served
    if sum(1 for p in d["active"] if p["pref"]) < 6:
        return False
    return True


def name_variant(r, p: dict) -> str:
    f = p["pref"] if (p["pref"] and r.random() < 0.6) else p["first"]
    style = r.random()
    if style < 0.45: s = f"{f} {p['last']}"
    elif style < 0.6: s = f"{p['last']}, {f}"
    elif style < 0.72: s = f"{f[0]}. {p['last']}"
    elif style < 0.84: s = f"{f} {p['last']}".lower()
    else: s = f"{f} {p['last']}".upper()
    return name_noise(r, s) if r.random() < 0.3 else s


def t24(t: tuple) -> str:
    return f"{t[0]:02d}:{t[1]:02d}"


def t12(t: tuple) -> str:
    h, m = t
    return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    ref_rows = []
    for p in sorted(d["active"], key=lambda p: p["id"]):
        h = d["per"][p["id"]]
        ref_rows.append([p["id"], f"{p['first']} {p['last']}"] + [f"{h[g]:.2f}" for g in PROGRAMS] + [f"{sum(h.values()):.2f}"])
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 5)
    write_xlsx(os.path.join(ws, "volunteer_roster.xlsx"), {"Roster": {
        "header": ["ID", "First name", "Last name", "Goes by", "Email", "Role", "Status"],
        "rows": [[p["id"], p["first"], p["last"], p["pref"] or "", p["email"], p["kind"], "Inactive" if p in d["inactive"] else "Active"]
                 for p in sorted(d["roster"], key=lambda p: p["id"])],
        "widths": {"B": 14, "C": 14, "E": 30}}}, creator="Volunteer coordinator")
    trows = []
    for i, s in enumerate(sorted(d["tablet"], key=lambda s: (s["date"], s["tin"], s["k"]))):
        trows.append([f"K{58210 + i}", s["date"].isoformat(), name_variant(r, s["who"]), TABLET_NAME[s["prog"]], t24(s["tin"]), t24(s["tout"])])
    write_csv(os.path.join(ws, "kiosk_signins_2026-07-01_to_2026-08-31.csv"), ["Entry", "Shift date", "Name", "Program", "In", "Out"], trows, crlf=True)
    sheets = {}
    for g in PROGRAMS:
        rows = [[s["date"].strftime("%m/%d/%Y"), name_variant(r, s["who"]), t12(s["tin"]), t12(s["tout"])]
                for s in sorted([x for x in d["paper"] if x["prog"] == g], key=lambda s: (s["date"], s["tin"], s["k"]))]
        sheets[PAPER_SHEET[g]] = {"merged_title": f"{PAPER_SHEET[g]} sign-in clipboard (typed up)", "header": ["Date", "Name", "Time in", "Time out"],
                                  "rows": rows, "widths": {"A": 12, "B": 24, "C": 11, "D": 11}}
    write_xlsx(os.path.join(ws, "paper_signin_sheets_typed.xlsx"), sheets, creator="Front desk")
    write_csv(os.path.join(ws, "county_volunteer_hours_template.csv"), HEADER, [])
    write_text(os.path.join(ws, "note_from_gloria.txt"),
               "County volunteer hours - July and August\n\n"
               "The county wants hours for July 1 to August 31 on their template (it's in the folder): one row per volunteer, "
               "using the ID from our roster, with hours in each program column and a total. Only people who actually volunteered "
               "in those two months - leave off anyone with no hours.\n\n"
               "Where the hours come from: the kiosk by the door, plus the paper clipboards we use when the kiosk is down or the "
               "drivers leave from the loading dock. Nicole typed the clipboards up. Some people signed both the kiosk and the clipboard "
               "for the same shift, and the kiosk sometimes records a tap twice - same person, same program, same day, same times "
               "is one shift. The clipboards were not cleared at the end of August, so there are a few September rows on them.\n\n"
               "People sign in however they like (Bob, Robert, Smith R.) - the roster has the name they go by. Staff sign in too "
               "for the shelter and the pantry; the county only wants volunteers.\n\n"
               "The overnight shelter shift starts in the evening and ends the next morning - count it on the date it started.\n\n"
               "Hours to two decimals is fine.\n\n- Gloria\n")
    write_csv(os.path.join(ref, "volunteer_hours.csv"), HEADER, ref_rows)
    write_csv(os.path.join(sol, "volunteer_hours.csv"), HEADER, ref_rows)
    shelter_ids = sorted({s["who"]["id"] for s in d["sessions"] if s["prog"] == "overnight_shelter"})
    dup_ids = sorted({s["who"]["id"] for s in d["sessions"] if s.get("dup") and s["prog"] in ("pantry", "tutoring")})
    sept_ids = sorted({s["who"]["id"] for s in d["sept"]})
    nick_ids = sorted({p["id"] for p in d["active"] if p["pref"]})
    write_json(os.path.join(ref, "notes.json"), {"staff": [p["id"] for p in d["staff"]], "inactive": [p["id"] for p in d["inactive"]],
                                                  "shelter_ids": shelter_ids, "duplicate_ids": dup_ids, "september_ids": sept_ids,
                                                  "tablet_rows": len(d["tablet"]), "paper_rows": len(d["paper"])})
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    write_task_yaml(HERE, {
        "id": "volunteer-hours", "track": "desk", "category": "reports",
        "title": "Volunteer hours per program for the county",
        "ask": ("The county wants our volunteer hours for July and August, per volunteer and per program. Everything is in the folder and "
                "Gloria's note explains the sign-ins. Save it as volunteer_hours.csv in the county's format.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "people sign in as nicknames (Bob for Robert), \"Last, First\", initials, all caps or lower case, with stray spaces; the roster's "
            "Goes by column resolves each to one id, and a name-as-typed grouping splits one volunteer into several "
            "(checks: volunteers who served; pantry and tutoring hours; total hours)",
            "overnight shelter shifts run from 9pm to 7am, so time out is earlier than time in; a plain difference goes negative "
            "(check: overnight shelter hours)",
            f"{sum(1 for s in d['sessions'] if s.get('dup') == 'both')} shifts were signed on both the kiosk and a clipboard and "
            f"{sum(1 for s in d['sessions'] if s.get('dup') == 'tap')} kiosk taps were recorded twice; each shift counts once "
            "(check: pantry and tutoring hours)",
            "three staff sign in on the same kiosk and clipboards and the roster has three inactive volunteers with no sign-ins; "
            "neither belongs in the file (checks: volunteers who served; row count)",
            "the meal delivery clipboard runs into September; those rows are outside the period (check: meal delivery hours)",
            "clipboards use a 12-hour clock (\"9:15 PM\") and dates as MM/DD/YYYY on four sheets with merged titles; the kiosk uses "
            "24-hour times and ISO dates (check: total hours)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "county template columns", "path": "volunteer_hours.csv", "columns": HEADER},
            {"type": "csv_set_equal", "name": "volunteers who served", "path": "volunteer_hours.csv", "column": "volunteer_id",
             "ref": "volunteer_hours.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "volunteer_hours.csv", "equals_ref": "volunteer_hours.csv"},
            {"type": "csv_values_match", "name": "overnight shelter hours", "path": "volunteer_hours.csv", "ref": "volunteer_hours.csv",
             "key": "volunteer_id", "columns": ["overnight_shelter_hours"], "must_match_keys": shelter_ids, **num},
            {"type": "csv_values_match", "name": "pantry and tutoring hours", "path": "volunteer_hours.csv", "ref": "volunteer_hours.csv",
             "key": "volunteer_id", "columns": ["pantry_hours", "tutoring_hours"], "must_match_keys": dup_ids, **num},
            {"type": "csv_values_match", "name": "meal delivery hours", "path": "volunteer_hours.csv", "ref": "volunteer_hours.csv",
             "key": "volunteer_id", "columns": ["meal_delivery_hours"], "must_match_keys": sept_ids, **num},
            {"type": "csv_values_match", "name": "total hours", "path": "volunteer_hours.csv", "ref": "volunteer_hours.csv",
             "key": "volunteer_id", "columns": ["total_hours"], **num},
        ],
    })
    print(f"seed={seed} active={len(d['active'])} sessions={len(d['sessions'])} tablet={len(d['tablet'])} paper={len(d['paper'])} "
          f"dups={sum(1 for s in d['sessions'] if s.get('dup'))} shelter={shelter_ids}")


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: stack kiosk and clipboard rows, group by the name as typed matched exactly to the roster's
    first + last name, subtract times without handling midnight, keep every row."""
    os.makedirs(out, exist_ok=True)
    full = {f"{p['first']} {p['last']}".lower(): p for p in d["roster"]}
    per = {}
    r = rng(1)
    for s in d["tablet"] + d["paper"]:
        nm = name_variant(r, s["who"]).strip().lower()
        p = full.get(nm)
        if not p:
            continue
        a = s["tin"][0] * 60 + s["tin"][1]; b = s["tout"][0] * 60 + s["tout"][1]
        per.setdefault(p["id"], {g: 0.0 for g in PROGRAMS})[s["prog"]] += (b - a) / 60
    rows = [[i, ""] + [f"{h[g]:.2f}" for g in PROGRAMS] + [f"{sum(h.values()):.2f}"] for i, h in sorted(per.items())]
    write_csv(os.path.join(out, "volunteer_hours.csv"), HEADER, rows)


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
