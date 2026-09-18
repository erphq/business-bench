#!/usr/bin/env python3
"""schedule-change-notices: the revised workforce-management export against the published schedule becomes
one notice per affected agent, and nothing for anyone whose week did not change.

    python gen.py [--seed N]

Business: an insurance claims contact center with agents in three offices (Portland, Boise, Raleigh). The
published schedule is in each office's local time; the scheduling system's revised export is in UTC.

Traps (each caught by a check, see task.yaml):
  * the export is in UTC and the published grid in local time, so a straight comparison flags every agent; the
    offices are in three zones (Pacific, Mountain, Eastern, all on daylight time that week)
                                                                    (checks: no notices for unchanged staff; changed shifts in local time)
  * closing shifts start in the evening local time and fall on the next UTC date; two unchanged closers look moved
    by a day, and one changed late shift must still be reported on its local day (Thursday)
                                                                    (checks: no notices for unchanged staff; changed shifts in local time)
  * the export renames queues for several agents and repeats one shift row; neither is a schedule change
                                                                    (check: no notices for unchanged staff)
  * a notice lists only the changed shifts, not the whole week       (check: unchanged shifts not listed)
  * each notice names the agent's time zone                          (check: time zone named)
  * swaps, cuts and additions all count as changes, including a 30-minute later finish (checks: one file_exists per affected agent)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

WEEK = [date(2026, 9, 21) + timedelta(days=i) for i in range(7)]  # Mon..Sun
DAYN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
OFFICES = {"Portland": ("America/Los_Angeles", -7, "Pacific"), "Boise": ("America/Boise", -6, "Mountain"),
           "Raleigh": ("America/New_York", -4, "Eastern")}
SHIFTS = {"early": ((7, 0), (15, 30)), "day": ((8, 0), (16, 30)), "mid": ((10, 0), (18, 30)), "late": ((13, 30), (22, 0)),
          "close": ((17, 0), (25, 30)), "night": ((17, 30), (26, 0)), "day_long": ((8, 0), (17, 0))}
PATTERNS = [[0, 1, 2, 3, 4], [1, 2, 3, 4, 5], [2, 3, 4, 5, 6], [0, 1, 3, 4, 5], [0, 2, 3, 4, 6]]


def local_str(hm: tuple[int, int]) -> str:
    h, m = hm
    h %= 24
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{'a' if h < 12 else 'p'}"


def pretty(hm: tuple[int, int]) -> str:
    h, m = hm
    h %= 24
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def to_utc(day: date, hm: tuple[int, int], offset: int) -> datetime:
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=hm[0] - offset, minutes=hm[1])


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 505)
    names = []
    tokens = []
    while len(names) < 14:
        f, l = person(r)
        lf, ll = f.lower(), l.lower()
        if any(lf in t or t in lf or ll in t or t in ll for t in tokens) or lf == ll:
            continue
        tokens += [lf, ll]
        names.append((f, l))
    offices = ["Portland"] * 6 + ["Boise"] * 4 + ["Raleigh"] * 4
    staff = []
    for i, ((f, l), off) in enumerate(zip(names, offices)):
        staff.append({"id": f"E{4102 + i * 7}", "first": f, "last": l, "office": off, "tz": OFFICES[off][0],
                      "offset": OFFICES[off][1], "zone": OFFICES[off][2],
                      "email": f"{f.lower()}.{l.lower()}@everline.com"})
    # roles by position
    P1, P2, PC1, PC2, P5, P6, M1, M2, M3, M4, E1, E2, E3, E4 = staff
    base_kind = {id(P1): "early", id(P2): "late", id(PC1): "close", id(PC2): "close", id(P5): "day", id(P6): "mid",
                 id(M1): "day", id(M2): "early", id(M3): "mid", id(M4): "day", id(E1): "day", id(E2): "early", id(E3): "mid", id(E4): "late"}
    for s in staff:
        pat = list(r.choice(PATTERNS))
        s["old"] = {i: SHIFTS[base_kind[id(s)]] for i in pat}
        s["new"] = dict(s["old"])
    # constraints per changed agent
    def ensure(s, days_on, days_off=()):
        for dd in days_on:
            if dd not in s["old"]:
                s["old"][dd] = SHIFTS[base_kind[id(s)]]
        for dd in days_off:
            s["old"].pop(dd, None)
        while len(s["old"]) > 5:
            extra = [k for k in s["old"] if k not in days_on]
            s["old"].pop(extra[-1])
        s["new"] = dict(s["old"])
    changes = {}
    ensure(P1, [1]); P1["new"][1] = SHIFTS["mid"]
    changes[P1["id"]] = [("moved", 1)]
    ensure(P2, [3]); P2["new"][3] = SHIFTS["night"]
    changes[P2["id"]] = [("moved", 3)]
    ensure(M1, [2], [5]); del M1["new"][2]; M1["new"][5] = SHIFTS["day"]
    changes[M1["id"]] = [("removed", 2), ("added", 5)]
    ensure(M2, [0]); del M2["new"][0]
    changes[M2["id"]] = [("removed", 0)]
    ensure(E1, [0], [6]); E1["new"][0] = SHIFTS["day_long"]; E1["new"][6] = SHIFTS["mid"]
    changes[E1["id"]] = [("moved", 0), ("added", 6)]
    queues = ["Claims - Auto", "Claims - Home", "Policy Service", "Billing"]
    for s in staff:
        s["queue"] = r.choice(queues)
        s["new_queue"] = s["queue"]
    for s in r.sample([PC1, P5, M3, E2, E3], 3):
        s["new_queue"] = r.choice([q for q in queues if q != s["queue"]])
    dup_agent = r.choice([P6, M4, E4])
    return {"staff": staff, "changes": changes, "dup_agent": dup_agent["id"], "closers": [PC1["id"], PC2["id"]]}


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    staff = d["staff"]

    write_csv(os.path.join(ws, "agent_roster.csv"), ["Employee ID", "Name", "Office", "Time zone", "Email"],
              [[s["id"], f"{s['first']} {s['last']}", s["office"], s["tz"], s["email"]] for s in staff])

    header = ["Agent", "Office", "Queue"] + [f"{DAYN[i][:3]} {WEEK[i].month}/{WEEK[i].day}" for i in range(7)]
    grid = []
    for s in sorted(staff, key=lambda s: (s["office"], s["last"])):
        row = [f"{s['last']}, {s['first']}", s["office"], s["queue"]]
        for i in range(7):
            sh = s["old"].get(i)
            row.append(f"{local_str(sh[0])}-{local_str(sh[1])}" if sh else "OFF")
        grid.append(row)
    write_xlsx(os.path.join(ws, "schedule_week_2026-09-21_published.xlsx"), {"Week of 21 Sep": {
        "merged_title": "Claims Contact Center - published schedule, week of 21 Sep 2026",
        "preamble": [["All times are local to the agent's office. Published 11 Sep 2026."]],
        "header": header, "rows": grid, "widths": {"A": 22, "C": 16, **{c: 14 for c in "DEFGHIJ"}}}}, creator="WFM")

    rows = []
    sid = 88100
    for s in staff:
        for i in sorted(s["new"]):
            st, en = s["new"][i]
            a, b = to_utc(WEEK[i], st, s["offset"]), to_utc(WEEK[i], en, s["offset"])
            rows.append([a, s, b])
    rows.sort(key=lambda x: (x[0], x[1]["id"]))
    out = []
    for a, s, b in rows:
        sid += 1
        out.append([f"SH-{sid}", s["id"], f"{s['first']} {s['last']}", a.strftime("%Y-%m-%dT%H:%M:%SZ"), b.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    s["new_queue"], "rev2"])
        if s["id"] == d["dup_agent"] and not any(o[1] == s["id"] and o[-1] == "rev2-dup" for o in out):
            out.append([f"SH-{sid}", s["id"], f"{s['first']} {s['last']}", a.strftime("%Y-%m-%dT%H:%M:%SZ"), b.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        s["new_queue"], "rev2-dup"])
    for o in out:
        if o[-1] == "rev2-dup":
            o[-1] = "rev2"
    write_csv(os.path.join(ws, "wfm_shift_export_week38_rev2.csv"),
              ["shift_id", "employee_id", "employee_name", "start_utc", "end_utc", "queue", "revision"], out)

    write_text(os.path.join(ws, "email_from_renata.txt"), """From: Renata Oyelaran <renata.oyelaran@everline.com>
To: you
Date: Mon, 14 Sep 2026 10:22
Subject: Revised schedule for week of 9/21 - notices

The revised schedule for next week came out of WFM this morning (the rev2 export). Can you write the change
notices? Rules:

- Only people whose shifts actually changed get a notice. If someone's week is the same, no file for them.
- In each notice list only the shifts that changed: the day, the old time and the new time. Added and dropped
  shifts count. Don't list the rest of their week.
- WFM exports in UTC. Our agents think in their office's local time, so put times in local time and say which
  time zone.
- Queue changes are handled separately by the team leads, they are not schedule changes.
- One file per person in a notices folder, named first-last in lower case, e.g. notices/dana-cruz.md

Thanks,
Renata
""")

    # ---- truth + reference notices ----
    changed = {s["id"]: s for s in staff if s["id"] in d["changes"]}
    facts = {"changed": [], "unchanged": []}
    for s in staff:
        if s["id"] not in changed:
            facts["unchanged"].append({"first": s["first"], "last": s["last"]})
            continue
        items = []
        lines = []
        for kind, i in d["changes"][s["id"]]:
            old, new = s["old"].get(i), s["new"].get(i)
            day_label = f"{DAYN[i]} {WEEK[i].day} Sep"
            items.append({"kind": kind, "weekday": DAYN[i], "date": WEEK[i].isoformat(),
                          "new_start": [new[0][0] % 24, new[0][1]] if new else None, "new_end": [new[1][0] % 24, new[1][1]] if new else None})
            lines.append(f"| {day_label} | {pretty(old[0]) + ' - ' + pretty(old[1]) if old else 'Off'} | "
                         f"{pretty(new[0]) + ' - ' + pretty(new[1]) if new else 'Off (shift removed)'} |")
        unchanged_days = [{"weekday": DAYN[i], "date": WEEK[i].isoformat(), "start": [sh[0][0] % 24, sh[0][1]]}
                          for i, sh in sorted(s["new"].items()) if s["old"].get(i) == sh]
        facts["changed"].append({"first": s["first"], "last": s["last"], "zone": s["zone"], "changes": items, "unchanged_days": unchanged_days})
        body = f"""# Schedule change: week of 21 September 2026

Hi {s['first']},

Your schedule for the week of 21 September 2026 has changed. All times below are {s['zone']} Time, local to the {s['office']} office.

| Day | Old shift | New shift |
|---|---|---|
{chr(10).join(lines)}

Your other shifts this week are unchanged.

Renata Oyelaran
"""
        write_text(os.path.join(sol, "notices", f"{s['first'].lower()}-{s['last'].lower()}.md"), body)
    write_json(os.path.join(ref, "facts.json"), facts)

    def ci_glob(first: str, last: str) -> str:
        cls = lambda w: "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else c for c in w)
        return f"notices/*{cls(first)}*{cls(last)}*"

    checks = []
    for c in facts["changed"]:
        checks.append({"type": "file_exists", "name": f"notice for {c['first']} {c['last']}", "path": ci_glob(c["first"], c["last"])})
    checks.append({"type": "custom", "name": "notices carry their own changes", "module": "check.py"})
    P1, P2, M1, M2, E1 = [s for s in staff if s["id"] in d["changes"]][:5]
    write_task_yaml(HERE, {
        "id": "schedule-change-notices", "track": "desk", "category": "drafting",
        "title": "Schedule change notices for next week's revised rota",
        "ask": "WFM put out a revised schedule for the week of 9/21. Please write the change notices for the agents it affects; Renata's email has the rules. Put them in a notices folder.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the rev2 export is in UTC and the published grid is local time in three zones (Portland Pacific UTC-7, Boise Mountain UTC-6, Raleigh Eastern UTC-4 that week), so comparing the raw times flags all 14 agents (check: notices carry their own changes)",
            f"{P1['first']} {P1['last']}'s Tuesday moves from 7:00 AM to 10:00 AM Pacific; the export shows 14:00Z and 17:00Z, and a notice in UTC fails (check: notices carry their own changes)",
            f"closing shifts start in the evening local time and land on the next UTC date: two unchanged Portland closers look moved by a day, and {P2['first']} {P2['last']}'s changed late shift (Thursday 5:30 PM to 2:00 AM) appears under Friday in UTC (check: notices carry their own changes)",
            "the export renames the queue for three agents and repeats one shift row for another; neither is a schedule change and those agents get no file (check: notices carry their own changes)",
            f"{M1['first']} {M1['last']} swaps Wednesday for Saturday, {M2['first']} {M2['last']} loses Monday, and {E1['first']} {E1['last']} finishes 30 minutes later on Monday and gains Sunday; dropped and added shifts count as changes (checks: notice for each affected agent; notices carry their own changes)",
            "a notice lists only the changed shifts, not the agent's whole week (check: notices carry their own changes)",
            "each notice names the agent's time zone (check: notices carry their own changes)",
        ],
        "checks": checks,
    })


if __name__ == "__main__":
    emit(argparse_seed())
