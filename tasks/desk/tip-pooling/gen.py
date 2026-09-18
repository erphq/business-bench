#!/usr/bin/env python3
"""tip-pooling: a ramen restaurant's week of card tips, cash envelopes and punches to each person's share per shift.

    python gen.py [--seed N] [--naive DIR]

Business: Kinjo Ramen, lunch and dinner six and a half days a week. The POS stamps each check with the time it was
closed; the manager counts the cash tip envelope at the end of each shift; the time clock exports punches with a
date and two clock times. The owner's memo carries the pool rules and a largest-remainder rounding convention.

Traps (each caught by a check, see task.yaml):
  * tips pool by shift, not by day or by week, and a check's shift comes from its close time   (check: tip shares per person per shift)
  * checks closed after midnight belong to the night before, including two from the previous week (check: tip shares)
  * shares are weighted by hours, and dinner punch-outs after midnight read "12:40 AM"          (check: tip shares)
  * the GM and kitchen manager clock in and work but do not share; the shift lead does          (check: managers take nothing)
  * one server works lunch into dinner without clocking out; hours split at 4:00 PM            (check: tip shares)
  * cash envelopes add to the pool, voided checks' tips do not                                 (check: tip shares)
  * shares round down to the cent and the leftover cents go by largest remainder, so each shift
    ties to its pool exactly                                                                   (check: tip shares - ties)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

WEEK = [date(2026, 8, 10) + timedelta(days=k) for k in range(7)]  # Mon .. Sun
BOUNDARY = 16 * 60
ROSTER = [("Server", 5), ("Shift Lead", 1), ("Bartender", 2), ("Host", 2), ("Busser", 2), ("Line Cook", 3), ("Dishwasher", 2),
          ("General Manager", 1), ("Kitchen Manager", 1)]
NEED = {"lunch": {"Server": 2, "Bartender": 1, "Host": 1, "Busser": 1, "Line Cook": 2, "Dishwasher": 1},
        "dinner": {"Server": 3, "Bartender": 2, "Host": 1, "Busser": 2, "Line Cook": 2, "Dishwasher": 1}}


def shifts():
    out = []
    for d in WEEK:
        if d.weekday() != 0:
            out.append((d, "lunch"))
        out.append((d, "dinner"))
    return out


def clock(m: int) -> str:
    m %= 24 * 60
    h, mm = divmod(m, 60)
    return f"{(h - 1) % 12 + 1}:{mm:02d} {'AM' if h < 12 else 'PM'}"


def q(r, lo: int, hi: int) -> int:
    """A punch time; the clock rounds punches to the quarter hour."""
    return 15 * r.randint((lo + 14) // 15, hi // 15)


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, sum(n for _, n in ROSTER))
    staff = []
    k = 0
    for role, n in ROSTER:
        for _ in range(n):
            f, l = names[k]; k += 1
            staff.append({"first": f, "last": l, "name": f"{f} {l}", "role": role, "manager": "Manager" in role})
    by_role = {}
    for s in staff:
        by_role.setdefault(s["role"], []).append(s)
    lead = by_role["Shift Lead"][0]
    gm, km = by_role["General Manager"][0], by_role["Kitchen Manager"][0]
    double_day = WEEK[5]  # Saturday
    double = r.choice(by_role["Server"])

    # ---- punches: (person, date, in_min, out_min) with out_min possibly past midnight (> 1440)
    punches = []
    for d, sh in shifts():
        crew = []
        for role, n in NEED[sh].items():
            pool = list(by_role[role]) + ([lead] if role == "Server" else [])
            if role == "Server" and d.weekday() >= 4 and sh == "dinner":
                n += 1
            crew += r.sample(pool, min(n, len(pool)))
        if r.random() < 0.7 or (d.weekday() >= 4 and sh == "dinner"):
            crew.append(gm if sh == "dinner" or r.random() < 0.5 else km)
        if sh == "dinner" and r.random() < 0.5:
            crew.append(km)
        crew = list({id(c): c for c in crew}.values())
        if (d, sh) == (double_day, "lunch"):
            crew = [c for c in crew if c is not double]
        if (d, sh) == (double_day, "dinner"):
            crew = [c for c in crew if c is not double]
        for p in crew:
            if sh == "lunch":
                t_in = q(r, 10 * 60 + 15, 11 * 60 + 15)
                t_out = q(r, 14 * 60 + 30, 15 * 60 + 45)
            else:
                t_in = q(r, 16 * 60 + 15, 17 * 60)
                late = d.weekday() >= 4
                t_out = q(r, 24 * 60, 24 * 60 + 60) if late and r.random() < 0.7 else q(r, 21 * 60 + 30, 23 * 60 + 30)
            punches.append({"p": p, "date": d, "in": t_in, "out": t_out, "shift": sh})
    punches.append({"p": double, "date": double_day, "in": q(r, 10 * 60 + 30, 11 * 60), "out": q(r, 21 * 60 + 15, 22 * 60 + 30),
                    "shift": "double"})

    # ---- checks
    checks = []
    seq = r.randint(40100, 40900)
    for d, sh in shifts():
        n = r.randint(26, 40) if sh == "lunch" else r.randint(48, 75)
        late = d.weekday() >= 4 and sh == "dinner"
        for _ in range(n):
            seq += 1
            if sh == "lunch":
                t = r.randint(11 * 60 + 20, 15 * 60 + 25)
            elif late and r.random() < 0.12:
                t = r.randint(24 * 60 + 2, 24 * 60 + 50)
            else:
                t = r.randint(17 * 60 + 5, 23 * 60 + 15)
            total = r.randint(1800, 16500)
            pay = "Cash" if r.random() < 0.18 else r.choice(["Visa", "Mastercard", "Amex", "Discover", "Apple Pay"])
            tip = 0 if pay == "Cash" or r.random() < 0.05 else int(round(total * r.uniform(0.15, 0.24)))
            checks.append({"no": seq, "date": d, "min": t, "total": total, "pay": pay, "tip": tip, "status": "Closed", "shift": (d, sh)})
    # two checks from the Sunday before, closed after midnight on Monday morning
    for _ in range(2):
        seq_prev = r.randint(40000, 40090)
        total = r.randint(3000, 9000)
        checks.append({"no": seq_prev, "date": WEEK[0] - timedelta(days=1), "min": r.randint(24 * 60 + 5, 24 * 60 + 40), "total": total,
                       "pay": "Visa", "tip": int(round(total * 0.2)), "status": "Closed", "shift": None})
    for c in r.sample([c for c in checks if c["tip"] > 0 and c["shift"]], 3):
        c["status"] = "Voided"
    servers = [s for s in staff if s["role"] in ("Server", "Shift Lead", "Bartender")]
    for c in checks:
        c["server"] = r.choice(servers)["name"]

    # ---- cash envelopes
    envelopes = {(d, sh): r.randint(3, 16) * 1000 + r.choice([0, 0, 500, 250, 750]) for d, sh in shifts()}

    # ---- truth
    minutes = {}
    for pu in punches:
        p = pu["p"]
        if p["manager"]:
            continue
        if pu["shift"] == "double":
            minutes[(pu["date"], "lunch", p["name"])] = BOUNDARY - pu["in"]
            minutes[(pu["date"], "dinner", p["name"])] = pu["out"] - BOUNDARY
        else:
            key = (pu["date"], pu["shift"], p["name"])
            minutes[key] = minutes.get(key, 0) + pu["out"] - pu["in"]
    pools, rows = {}, []
    for d, sh in shifts():
        card = sum(c["tip"] for c in checks if c["shift"] == (d, sh) and c["status"] == "Closed")
        pool = card + envelopes[(d, sh)]
        pools[(d, sh)] = pool
        crew = sorted([(name, m) for (dd, ss, name), m in minutes.items() if (dd, ss) == (d, sh)])
        M = sum(m for _, m in crew)
        base = [(name, m, pool * m // M, pool * m % M) for name, m in crew]
        left = pool - sum(b[2] for b in base)
        last_of = {s["name"]: (s["last"], s["first"]) for s in staff}
        order = sorted(base, key=lambda b: (-b[3], -b[1], last_of[b[0]]))
        bonus = {b[0]: 1 for b in order[:left]}
        for name, m, fl, rem in base:
            rows.append({"date": d, "shift": sh, "name": name, "minutes": m, "share": fl + bonus.get(name, 0), "exact": pool * m / M})
        assert sum(x["share"] for x in rows if (x["date"], x["shift"]) == (d, sh)) == pool
    return {"staff": staff, "punches": punches, "checks": checks, "envelopes": envelopes, "pools": pools, "rows": rows,
            "double": double, "gm": gm, "km": km, "lead": lead, "double_day": double_day}


def naive_rows(d: dict) -> list[dict]:
    """Card tips only, pooled by calendar day of the check, split evenly among everyone who punched in that day,
    rounded half up."""
    out = []
    for day in WEEK:
        pool = sum(c["tip"] for c in d["checks"] if c["date"] == day and c["status"] == "Closed")
        crew = sorted({pu["p"]["name"] for pu in d["punches"] if pu["date"] == day})
        for sh in ("lunch", "dinner"):
            if (day, sh) not in d["pools"]:
                continue
            names = sorted({pu["p"]["name"] for pu in d["punches"] if pu["date"] == day and pu["shift"] in (sh, "double")})
            for n in names:
                out.append({"date": day, "shift": sh, "name": n, "minutes": 0, "share": int(round(pool / len(crew) / 2))})
    return out


def acceptable(d: dict) -> bool:
    rows = d["rows"]
    # the largest-remainder step must matter: some shift where plain half-up rounding misses the pool
    misses = 0
    for key, pool in d["pools"].items():
        half_up = sum(int(x["exact"] + 0.5) for x in rows if (x["date"], x["shift"]) == key)
        misses += half_up != pool
    if misses < 3:
        return False
    # after-midnight checks exist on Friday and Saturday dinner
    if sum(1 for c in d["checks"] if c["shift"] and c["min"] >= 1440) < 4:
        return False
    # the GM and kitchen manager both actually clock in
    names = {pu["p"]["name"] for pu in d["punches"]}
    if d["gm"]["name"] not in names or d["km"]["name"] not in names or d["lead"]["name"] not in names:
        return False
    # the managers' last names are graded as absent, so nobody who shares may contain them
    for m in (d["gm"], d["km"]):
        for s in d["staff"]:
            if s is not m and (m["last"].lower() in s["last"].lower() or m["last"].lower() in s["first"].lower()):
                return False
    return True


# --------------------------------------------------------------------------- emit

def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["date", "shift", "employee", "hours", "tip_share"]
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_csv(os.path.join(naive_dir, "tip_distribution.csv"), header,
                  [[x["date"].isoformat(), x["shift"].title(), x["name"], "", f"{x['share'] / 100:.2f}"] for x in naive_rows(d)])
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 9)

    # ---- workspace: POS tips export
    pos = []
    for c in sorted(d["checks"], key=lambda c: (c["date"], c["min"], c["no"])):
        closed_day = c["date"] + timedelta(days=c["min"] // 1440)
        pos.append([c["no"], closed_day.strftime("%m/%d/%Y"), clock(c["min"]), c["server"], c["pay"], f"{c['total'] / 100:.2f}",
                    f"{c['tip'] / 100:.2f}", c["status"]])
    write_csv(os.path.join(ws, "pos_checks_2026-08-10_to_2026-08-16.csv"),
              ["Check #", "Closed date", "Closed time", "Server", "Tender", "Check total", "Tip", "Status"], pos,
              preamble=["Kinjo Ramen - Closed checks with tips", "Export window: 08/10/2026 12:00 AM - 08/17/2026 03:00 AM"], crlf=True)

    # ---- workspace: cash envelopes
    env_rows = []
    for (dd, sh), amt in d["envelopes"].items():
        who = d["gm"]["name"] if sh == "dinner" else d["km"]["name"]
        env_rows.append([dd, sh.title(), money_str(amt / 100, 1), who, ""])
    env_rows.sort(key=lambda x: (x[0], x[1] != "Lunch"))
    write_xlsx(os.path.join(ws, "cash_tip_envelopes_wk33.xlsx"), {"Envelopes": {
        "merged_title": "Cash tip envelopes - week of Aug 10",
        "header": ["Date", "Shift", "Cash counted", "Counted by", "Note"], "rows": env_rows, "widths": {"C": 14, "D": 20, "E": 24}}},
        creator="Kinjo Ramen")

    # ---- workspace: time clock
    tc = []
    role_of = {s["name"]: s["role"] for s in d["staff"]}
    for pu in sorted(d["punches"], key=lambda pu: (pu["date"], pu["in"], pu["p"]["last"])):
        tc.append([f"{pu['p']['last']}, {pu['p']['first']}", role_of[pu["p"]["name"]], pu["date"].strftime("%a %m/%d/%Y"), clock(pu["in"]),
                   clock(pu["out"]), f"{(pu['out'] - pu['in']) / 60:.2f}" if pu["out"] < 1440 else ""])
    write_csv(os.path.join(ws, "timeclock_punches_wk33.csv"), ["Employee", "Job", "Date", "Clock in", "Clock out", "Paid hours"], tc)

    # ---- workspace: owner's memo
    write_text(os.path.join(ws, "tip_pool_memo.txt"),
               "KINJO RAMEN - HOW THE TIP POOL WORKS\n"
               "(posted by the office, from Hana - updated June 2026)\n\n"
               "1. Tips are pooled by shift. Lunch tips go to the people who worked lunch, dinner tips to the people who worked dinner.\n"
               "   The pool for a shift is the card tips on that shift's closed checks plus that shift's cash envelope. Voided checks\n"
               "   do not count. We pay card tips out in full and eat the card fee.\n\n"
               "2. The POS stamps each check with the time it was closed. Closed before 4:00 PM is lunch; 4:00 PM or later is dinner.\n"
               "   Checks closed after midnight belong to the dinner shift of the night before.\n\n"
               "3. Everyone hourly who worked the shift shares, front and back of house, including shift leads. Managers (anyone whose\n"
               "   job title says Manager) and I do not take from the pool, even on nights we run food or pour drinks.\n\n"
               "4. Your share is by the hours you worked on that shift, clock in to clock out. The Paid hours column on the clock\n"
               "   export is blank when you clock out after midnight; just count to your clock-out time. If you work lunch straight into\n"
               "   dinner without clocking out, your time before 4:00 PM counts for lunch and your time from 4:00 PM on counts for dinner.\n\n"
               "5. Rounding, so every shift pays out exactly what came in: work each share out exactly, cut it down to the cent, then\n"
               "   hand out the leftover cents one at a time, first to the person who lost the biggest fraction of a cent. If two people\n"
               "   lost the same fraction, the one with more hours on the shift goes first, then alphabetical by last name.\n\n"
               "6. The payout sheet for payroll: one line per person per shift, with the date, the shift (Lunch or Dinner), the\n"
               "   employee's name as it is on the time clock, their hours on that shift, and their tip share.\n")

    # ---- reference and solution
    last_first = {s["name"]: f"{s['last']}, {s['first']}" for s in d["staff"]}
    body = [[x["date"].isoformat(), x["shift"].title(), last_first[x["name"]], f"{x['minutes'] / 60:.2f}", f"{x['share'] / 100:.2f}"]
            for x in sorted(d["rows"], key=lambda x: (x["date"], x["shift"] != "lunch", x["name"]))]
    write_csv(os.path.join(ref, "tip_distribution.csv"), header, body)
    write_csv(os.path.join(sol, "tip_distribution.csv"), header, body)
    write_json(os.path.join(ref, "notes.json"), {
        "pools": {f"{dd.isoformat()} {sh}": f"{v / 100:.2f}" for (dd, sh), v in d["pools"].items()},
        "managers_excluded": [d["gm"]["name"], d["km"]["name"]], "double": d["double"]["name"], "double_day": d["double_day"].isoformat(),
        "total_pool": f"{sum(d['pools'].values()) / 100:.2f}"})

    dbl, gm, km, lead = d["double"], d["gm"], d["km"], d["lead"]
    after = sum(1 for c in d["checks"] if c["shift"] and c["min"] >= 1440)
    write_task_yaml(HERE, {
        "id": "tip-pooling", "track": "desk", "category": "bookkeeping",
        "title": "Split last week's tip pool by shift",
        "ask": "Can you split last week's tips for payroll? The POS export, the cash envelope sheet, the time clock and Hana's tip pool memo are all in the folder. Save it as tip_distribution.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "tips pool per shift (13 of them, no Monday lunch) and a check's shift comes from its close time; pooling by day or by "
            "week, or by the server on the check, moves every share (check: tip shares per person per shift)",
            f"{after} checks on Friday to Sunday dinner closed after midnight carry the next calendar date and belong to the night "
            "before, and two checks closed early Monday belong to the previous week's Sunday and are not in this payout "
            "(check: tip shares per person per shift)",
            "shares are by hours on the shift; dinner punch-outs after midnight read '12:40 AM' with a blank Paid hours cell, so a "
            "plain time difference goes negative (check: tip shares per person per shift)",
            f"{gm['name']} (General Manager) and {km['name']} (Kitchen Manager) clock in on most shifts and must get nothing, while "
            f"{lead['name']} (Shift Lead) shares (check: managers take nothing)",
            f"{dbl['name']} works Saturday lunch straight into dinner on one punch; the hours split at 4:00 PM into both pools "
            "(check: tip shares per person per shift)",
            "cash envelopes are a separate workbook with '$1,250.00' text amounts and add to each shift's pool; three voided checks "
            "still show a tip (check: tip shares per person per shift)",
            "shares are cut down to the cent and the leftover cents go one at a time by largest lost fraction, then hours, then last "
            "name; rounding each share half-up leaves several shifts a cent or two off their pool "
            "(check: tip shares per person per shift - ties)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "payout sheet columns", "path": "tip_distribution.csv", "columns": header},
            {"type": "csv_row_count", "name": "one line per person per shift", "path": "tip_distribution.csv", "equals_ref": "tip_distribution.csv"},
            {"type": "text_not_contains", "name": "managers take nothing", "path": "tip_distribution.csv", "phrases": [gm["last"], km["last"]]},
            {"type": "custom", "name": "tip shares per person per shift", "module": "check.py"},
        ],
    })
    print(f"seed={seed} rows={len(d['rows'])} pools={sum(d['pools'].values()) / 100:.2f} double={dbl['name']} gm={gm['name']} km={km['name']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a_ = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a_.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a_.seed * 1000 + attempt, a_.naive)
