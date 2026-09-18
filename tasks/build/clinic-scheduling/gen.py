#!/usr/bin/env python3
"""Deterministic seed generator for the clinic-scheduling build task. All patients are fictional.

    python gen.py [--seed N]

Writes:
  seed/patients.csv       patient register: exact duplicate rows, patients re-registered under a second
                          record number with the name in capitals and the birth date in another format,
                          three pairs of different patients who share a name, padded record numbers
  seed/roster.csv         dated therapist shifts 2026-08-03 to 2026-09-26 (one row per shift): times written
                          8:00 AM, 08:00, 8am, or 13:00; therapist names in mixed case; no shifts on Labor Day
  seed/appointments.csv   appointments in the same window: duplicated rows, durations written 45, 45 min,
                          0:45, or 1h, record numbers with and without padding, one double-booked pair
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the public variant checklist.md quotes. Other seeds re-roll patients, who books which slot,
and statuses; the weekly roster pattern and the forced test slots stay fixed. counts.json is recomputed.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, write_csv, write_text  # noqa: E402

SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")
CLINIC = "Northshore Physiotherapy"
RESTRICTED = "Lena Fischer"
# weekday (0 = Monday), start, end, room
PATTERN = {
    "Lena Fischer": [(0, "08:00", "11:00", "Room 1"), (2, "13:00", "16:00", "Room 2"), (4, "09:00", "12:00", "Room 1")],
    "Sam Okafor": [(0, "13:00", "16:00", "Room 1"), (3, "08:00", "11:00", "Room 2")],
    "Priya Nair": [(1, "08:00", "11:00", "Room 1"), (2, "13:00", "16:00", "Room 3")],
    "Marcus Bell": [(1, "16:00", "19:00", "Gym"), (4, "13:00", "16:00", "Room 2")],
    "Hana Sato": [(2, "08:00", "11:00", "Room 1"), (5, "09:00", "12:00", "Room 2")],
    "Diego Ramos": [(0, "16:00", "19:00", "Gym"), (2, "16:00", "19:00", "Gym")],
}
THERAPISTS = list(PATTERN)
WINDOW = (date(2026, 8, 3), date(2026, 9, 26))
CLOSED = {date(2026, 9, 7)}  # Labor Day
PAST_END = date(2026, 9, 12)  # appointments on or before this date have an outcome; later ones are booked or cancelled
TYPES = [("Initial Assessment", 60), ("Follow-up", 45), ("Follow-up", 45), ("Follow-up", 45), ("Short Follow-up", 30)]
NOTES = ["L knee OA - progress strengthening", "Post-op ACL wk 8", "Low back pain, extension bias", "R shoulder impingement",
         "Ankle sprain grade II", "Neck pain, desk posture", "Plantar fasciitis", "Hip replacement rehab wk 4",
         "Tennis elbow", "Rotator cuff repair wk 10", "", "", ""]
REFERRALS = ["GP referral", "GP referral", "Self", "Insurance", "Sports club", "Orthopedic surgeon"]
N_PATIENTS = 150
N_EXACT_DUP, N_REREG, N_NAME_TWINS = 5, 4, 3
N_DUP_APPTS = 6
SAFE_DATE_STYLES = [0, 1, 2, 3, 4]
DOB_STYLES = [0, 1, 2, 3]  # birth dates never use style 4, the two-digit year (12/17/49 would read as 2049)


def four_digit_year(style: int) -> int:
    return 1 if style == 4 else style


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def fmt_time(minutes: int, style: int) -> str:
    h, m = divmod(minutes, 60)
    h12 = h % 12 or 12
    ap = "AM" if h < 12 else "PM"
    return [f"{h:02d}:{m:02d}", f"{h12}:{m:02d} {ap}", f"{h}:{m:02d}", (f"{h12}{ap.lower()}" if m == 0 else f"{h12}:{m:02d}{ap.lower()}")][style % 4]


def fmt_duration(d: int, style: int) -> str:
    return [f"{d}", f"{d} min", f"{d // 60}:{d % 60:02d}", ("1h" if d == 60 else f"{d}")][style % 4]


def build(seed: int) -> dict:
    rng = random.Random(seed)

    # ------------------------------------------------------------------ patients
    therapist_words = {w for t in THERAPISTS for w in t.split()}
    names = [(f, l) for f in FIRST for l in LAST if f not in therapist_words and l not in therapist_words]
    rng.shuffle(names)
    patients: list[dict] = []
    it = iter(names)
    used_names: set[tuple[str, str]] = set()
    while len(patients) < N_PATIENTS - N_NAME_TWINS:
        f, l = next(it)
        if (f, l) in used_names:
            continue
        used_names.add((f, l))
        patients.append({"first": f, "last": l})
    twins = rng.sample(patients, N_NAME_TWINS)
    for t in twins:
        patients.append({"first": t["first"], "last": t["last"], "twin_of": t})
    for p in patients:
        p["dob"] = date(1941, 1, 1) + timedelta(days=rng.randint(0, 22000))
        p["phone"] = f"978555{rng.randint(1000, 9999)}"
        p["email"] = f"{p['first'].lower()}.{p['last'].lower()}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'yahoo.com', 'outlook.com', 'icloud.com'])}"
        p["referral"] = rng.choice(REFERRALS)
        p["status"] = "Discharged" if rng.random() < 0.2 else "Active"
        p["registered"] = date(2024, 1, 2) + timedelta(days=rng.randint(0, 940))
        p["therapist"] = rng.choice(THERAPISTS)
        p["alias"] = None
    for t in twins:  # twins get clearly different birth decades
        other = next(p for p in patients if p.get("twin_of") is t)
        if abs((other["dob"] - t["dob"]).days) < 3650:
            other["dob"] = date(t["dob"].year - 25 if t["dob"].year > 1970 else t["dob"].year + 25, t["dob"].month, min(t["dob"].day, 28))
    mrns = rng.sample(range(1200, 9800), N_PATIENTS + N_REREG)
    for p, n in zip(patients, mrns):
        p["num"], p["mrn"] = n, f"{n:06d}"
    plain = [p for p in patients if "twin_of" not in p and p not in twins]
    rereg = rng.sample([p for p in plain if p["status"] == "Active"], N_REREG)
    for p, n in zip(rereg, mrns[N_PATIENTS:]):
        p["alias_num"], p["alias"] = n, f"{n:06d}"

    pat_rows: list[dict] = []
    for p in patients:
        pat_rows.append({"p": p, "role": "unique", "cells": [
            p["mrn"] if rng.random() > 0.15 else str(p["num"]), p["first"], p["last"], date_variant(p["dob"], four_digit_year(rng.choice(SAFE_DATE_STYLES))),
            p["phone"] if rng.random() < 0.5 else f"({p['phone'][:3]}) {p['phone'][3:6]}-{p['phone'][6:]}", p["email"], p["referral"],
            p["status"] if rng.random() > 0.12 else p["status"].lower(), date_variant(p["registered"], rng.choice(SAFE_DATE_STYLES))]})
    for p in rereg:
        orig_style = next(r for r in pat_rows if r["p"] is p)["cells"][3]
        style = next(s for s in DOB_STYLES if date_variant(p["dob"], s) != orig_style)
        pat_rows.append({"p": p, "role": "reregistered", "cells": [
            p["alias"], p["first"], p["last"].upper(), date_variant(p["dob"], style), p["phone"], p["email"].capitalize(), "Self",
            "Active", date_variant(date(2026, rng.randint(5, 8), rng.randint(1, 28)), rng.choice(SAFE_DATE_STYLES))]})
    dup_src = rng.sample([r for r in pat_rows if r["role"] == "unique" and r["p"] not in rereg and "twin_of" not in r["p"] and r["p"] not in twins], N_EXACT_DUP)
    pat_rows += [{"p": r["p"], "role": "exact_duplicate", "cells": list(r["cells"])} for r in dup_src]
    rng.shuffle(pat_rows)
    for line, r in enumerate(pat_rows, start=2):
        r["line"] = line

    # ------------------------------------------------------------------ roster
    shifts: list[dict] = []
    d = WINDOW[0]
    while d <= WINDOW[1]:
        if d not in CLOSED:
            for t in THERAPISTS:
                for wd, s, e, room in PATTERN[t]:
                    if d.weekday() == wd:
                        shifts.append({"t": t, "date": d, "start": hm(s), "end": hm(e), "room": room})
        d += timedelta(days=1)
    shifts.sort(key=lambda s: (s["date"], s["start"], s["t"]))
    roster_rows = []
    for s in shifts:
        st = rng.randrange(4)
        tname = s["t"] if rng.random() > 0.15 else rng.choice([s["t"].upper(), s["t"].lower(), s["t"] + " "])
        email = s["t"].lower().replace(" ", ".") + "@northshorephysio.example"
        roster_rows.append([date_variant(s["date"], rng.choice(SAFE_DATE_STYLES)), tname, email, fmt_time(s["start"], st), fmt_time(s["end"], st), s["room"]])

    # ------------------------------------------------------------------ appointment slots
    appts: list[dict] = []

    def add(t: str, dd: date, start: int, dur: int, typ: str, status: str, patient=None, forced=None) -> dict:
        a = {"t": t, "date": dd, "start": start, "dur": dur, "type": typ, "status": status, "p": patient, "forced": forced}
        appts.append(a)
        return a

    forced_days = {("Lena Fischer", date(2026, 9, 11)), ("Lena Fischer", date(2026, 9, 16)), ("Lena Fischer", date(2026, 9, 23)), ("Priya Nair", date(2026, 9, 16)), ("Marcus Bell", date(2026, 9, 15)), ("Diego Ramos", date(2026, 9, 14))}
    for s in shifts:
        if (s["t"], s["date"]) in forced_days:
            continue
        future = s["date"] > PAST_END
        cur = s["start"]
        while True:
            typ, dur = rng.choice(TYPES)
            if cur + dur > s["end"]:
                break
            if rng.random() < (0.66 if future else 0.27):
                cur += 15
                continue
            if future:
                status = "Booked" if rng.random() < 0.88 else "Cancelled"
            else:
                status = rng.choices(["Completed", "No-show", "Cancelled", "Late cancel"], [82, 6, 7, 5])[0]
            add(s["t"], s["date"], cur, dur, typ, status)
            cur += dur + rng.choice([0, 0, 0, 15])
    # sealed variants keep appointments.csv under 300 rows (seed 0 has 274 generated slots and never trims)
    while len(appts) > 276:
        appts.remove(rng.choice(appts))
    # forced test days
    add("Lena Fischer", date(2026, 9, 11), hm("10:30"), 45, "Follow-up", "Completed")
    add("Lena Fischer", date(2026, 9, 11), hm("11:15"), 45, "Follow-up", "Completed")
    t_sep23 = add("Lena Fischer", date(2026, 9, 23), hm("13:00"), 45, "Follow-up", "Booked", forced="sep23")
    t_lena_booked = add("Lena Fischer", date(2026, 9, 16), hm("13:00"), 45, "Follow-up", "Booked", forced="lena_booked")
    t_lena_cancel = add("Lena Fischer", date(2026, 9, 16), hm("15:00"), 45, "Follow-up", "Cancelled", forced="lena_cancelled")
    t_priya = add("Priya Nair", date(2026, 9, 16), hm("14:30"), 45, "Follow-up", "Booked", forced="priya_patient_q")
    add("Priya Nair", date(2026, 9, 16), hm("13:00"), 60, "Initial Assessment", "Booked")
    t_conf_a = add("Marcus Bell", date(2026, 9, 15), hm("16:00"), 60, "Initial Assessment", "Booked", forced="conflict_a")
    t_conf_b = add("Marcus Bell", date(2026, 9, 15), hm("16:30"), 45, "Follow-up", "Booked", forced="conflict_b")
    add("Marcus Bell", date(2026, 9, 15), hm("17:30"), 45, "Follow-up", "Booked")
    t_canc_a = add("Diego Ramos", date(2026, 9, 14), hm("16:00"), 45, "Follow-up", "Cancelled", forced="cancel_overlap_a")
    t_canc_b = add("Diego Ramos", date(2026, 9, 14), hm("16:15"), 45, "Follow-up", "Booked", forced="cancel_overlap_b")
    add("Diego Ramos", date(2026, 9, 14), hm("17:15"), 30, "Short Follow-up", "Booked")

    # ------------------------------------------------------------------ assign patients
    active = [p for p in patients if p["status"] == "Active"]
    by_t = {t: [p for p in patients if p["therapist"] == t] for t in THERAPISTS}
    role_patients: set[int] = set()
    noshow_merge = rereg[0]      # one no-show under each record number
    recall_dup = rereg[1]        # completed under one number, booked under the other
    recall_cancel = rng.choice([p for p in active if p not in rereg and "twin_of" not in p and p not in twins])
    discharged_ex = rng.choice([p for p in patients if p["status"] == "Discharged" and "twin_of" not in p and p not in twins])
    patient_q = rng.choice([p for p in active if p not in rereg and p is not recall_cancel and "twin_of" not in p and p not in twins])
    tester_patient = rng.choice([p for p in active if p not in rereg and p not in (recall_cancel, patient_q) and "twin_of" not in p and p not in twins])
    tester_patient2 = rng.choice([p for p in active if p not in rereg and p not in (recall_cancel, patient_q, tester_patient) and "twin_of" not in p and p not in twins])
    for p in (noshow_merge, recall_dup, recall_cancel, discharged_ex, patient_q, tester_patient, tester_patient2):
        role_patients.add(id(p))

    def busy(p: dict, a: dict) -> bool:
        return any(b["p"] is p and b["date"] == a["date"] and b is not a for b in appts)

    appts.sort(key=lambda a: (a["date"], a["start"], a["t"]))
    for a in appts:
        if a["forced"] == "priya_patient_q":
            a["p"] = patient_q
            continue
        future = a["date"] > PAST_END
        pool = [p for p in by_t[a["t"]] if id(p) not in role_patients and (not future or p["status"] == "Active")]
        if rng.random() < 0.25:
            pool = [p for p in patients if id(p) not in role_patients and (not future or p["status"] == "Active")]
        for _ in range(50):
            p = rng.choice(pool)
            if not busy(p, a):
                break
        a["p"] = p
    # role patients: rewrite a handful of past slots
    past_completed = [a for a in appts if a["status"] == "Completed" and a["forced"] is None and a["date"].month == 8]
    rng.shuffle(past_completed)
    pc = iter(past_completed)

    def claim(p: dict, status: str | None = None) -> dict:
        a = next(pc)
        a["p"] = p
        if status:
            a["status"] = status
        return a

    noshow_a = claim(noshow_merge, "No-show"); noshow_a["via_alias"] = False
    noshow_b = claim(noshow_merge, "No-show"); noshow_b["via_alias"] = True
    claim(noshow_merge)
    rc1 = claim(recall_dup); rc1["via_alias"] = False
    rd_booked = next(a for a in appts if a["status"] == "Booked" and a["forced"] is None and a["t"] != "Lena Fischer")
    rd_booked["p"], rd_booked["via_alias"] = recall_dup, True
    claim(recall_cancel)
    claim(recall_cancel)
    rc_cancel = next(a for a in appts if a["status"] == "Cancelled" and a["date"] > PAST_END and a["forced"] is None)
    rc_cancel["p"] = recall_cancel
    claim(discharged_ex)
    claim(tester_patient)
    claim(tester_patient2)
    t_lena_booked["p"] = rng.choice([p for p in active if id(p) not in role_patients])
    t_lena_cancel["p"] = rng.choice([p for p in active if id(p) not in role_patients and p is not t_lena_booked["p"]])
    for a in (t_conf_a, t_conf_b, t_canc_a, t_canc_b, t_sep23):
        if a["p"] is None or id(a["p"]) in role_patients:
            a["p"] = rng.choice([p for p in active if id(p) not in role_patients])
    # no role patient may keep accidental extra no-shows or bookings
    for a in appts:
        if a["p"] in (recall_cancel, discharged_ex) and a["status"] == "Booked":
            a["p"] = rng.choice([p for p in active if id(p) not in role_patients])
        if a["p"] is noshow_merge and a["status"] == "No-show" and a not in (noshow_a, noshow_b):
            a["status"] = "Completed"
    # discharged patients never hold a booking
    for a in appts:
        if a["status"] == "Booked" and a["p"]["status"] == "Discharged":
            a["p"] = rng.choice([p for p in active if id(p) not in role_patients])

    # repair pass: no ordinary patient may sit in two live appointments on the same day
    protected = {id(a) for a in (noshow_a, noshow_b, rc1, rd_booked, rc_cancel, t_priya)}
    for _ in range(3):
        for a in appts:
            if id(a) in protected or id(a["p"]) in role_patients:
                continue
            if busy(a["p"], a) or (a["date"] > PAST_END and a["p"]["status"] != "Active"):
                a["p"] = next(p for p in rng.sample(active, len(active)) if id(p) not in role_patients and not busy(p, a))

    appts.sort(key=lambda a: (a["date"], a["start"], a["t"]))
    for i, a in enumerate(appts):
        a["id"] = f"A-{30001 + i}"

    def overlaps(a: dict, b: dict) -> bool:
        return a["date"] == b["date"] and a["start"] < b["start"] + b["dur"] and b["start"] < a["start"] + a["dur"]

    live = [a for a in appts if a["status"] not in ("Cancelled", "Late cancel")]
    therapist_conflicts = [(a, b) for i, a in enumerate(live) for b in live[i + 1:] if a["t"] == b["t"] and overlaps(a, b)]
    assert [(a["id"], b["id"]) for a, b in therapist_conflicts] == [(t_conf_a["id"], t_conf_b["id"])], therapist_conflicts
    patient_conflicts = [(a, b) for i, a in enumerate(live) for b in live[i + 1:] if a["p"] is b["p"] and overlaps(a, b)]
    assert not patient_conflicts, [(a["id"], b["id"]) for a, b in patient_conflicts]

    # ------------------------------------------------------------------ appointment rows
    latest_appt = max(appts, key=lambda a: (a["date"], a["start"]))
    appt_rows: list[dict] = []
    for a in appts:
        p = a["p"]
        use_alias = a.get("via_alias", None)
        if use_alias is None:
            use_alias = bool(p["alias"]) and rng.random() < 0.5
            if p is recall_dup or p is noshow_merge:
                use_alias = False
        if use_alias:
            mrn_txt = p["alias"] if rng.random() < 0.5 else str(p["alias_num"])
            last_txt = p["last"].upper()
        else:
            mrn_txt = p["mrn"] if rng.random() < 0.7 else str(p["num"])
            last_txt = p["last"]
        st = rng.randrange(4)
        appt_rows.append({"a": a, "dup": False, "cells": [
            a["id"], date_variant(a["date"], 1 if a is latest_appt and rng.choice(SAFE_DATE_STYLES) is not None else rng.choice(SAFE_DATE_STYLES)), fmt_time(a["start"], st), fmt_duration(a["dur"], rng.randrange(4)),
            mrn_txt, f"{p['first']} {last_txt}", a["t"] if rng.random() > 0.1 else a["t"].upper(), a["type"],
            a["status"] if rng.random() > 0.1 else a["status"].upper(), rng.choice(NOTES) if a["date"] <= PAST_END else ""]})
    dup_src_a = rng.sample([r for r in appt_rows if r["a"]["forced"] is None and r["a"]["p"] not in (noshow_merge, recall_dup, recall_cancel)], N_DUP_APPTS)
    appt_rows += [dict(r, cells=list(r["cells"]), dup=True) for r in dup_src_a]
    order = {a["id"]: i for i, a in enumerate(appts)}
    appt_rows.sort(key=lambda r: (order[r["a"]["id"]], r["dup"]))
    for line, r in enumerate(appt_rows, start=2):
        r["line"] = line

    # ------------------------------------------------------------------ figures
    def pname(p: dict) -> str:
        return f"{p['first']} {p['last']}"

    booked = [a for a in appts if a["status"] == "Booked"]
    aug_shifts = [s for s in shifts if s["date"].month == 8]
    aug = [a for a in appts if a["date"].month == 8]

    def util(t=None) -> dict:
        rost = sum(s["end"] - s["start"] for s in aug_shifts if t is None or s["t"] == t)
        done = sum(a["dur"] for a in aug if a["status"] == "Completed" and (t is None or a["t"] == t))
        return {"completed_minutes": done, "rostered_minutes": rost, "pct": round(100.0 * done / rost, 1)}

    def week_util(t: str, monday: date) -> dict:
        days = {monday + timedelta(days=k) for k in range(7)}
        rost = sum(s["end"] - s["start"] for s in shifts if s["t"] == t and s["date"] in days)
        done = sum(a["dur"] for a in appts if a["status"] == "Completed" and a["t"] == t and a["date"] in days)
        return {"completed_minutes": done, "rostered_minutes": rost, "pct": round(100.0 * done / rost, 1) if rost else None}

    noshows = {}
    for a in appts:
        if a["status"] == "No-show":
            noshows[id(a["p"])] = noshows.get(id(a["p"]), 0) + 1
    flagged = [p for p in patients if noshows.get(id(p), 0) >= 2]

    def has(p: dict, status: str) -> bool:
        return any(a["p"] is p and a["status"] == status for a in appts)

    recall = [p for p in patients if p["status"] == "Active" and has(p, "Completed") and not has(p, "Booked")]
    assert recall_cancel in recall and recall_dup not in recall and discharged_ex not in recall
    assert noshow_merge in flagged
    # wrong readings: record numbers not merged
    def split_count_recall() -> int:
        n = 0
        for p in patients:
            if p["status"] != "Active":
                continue
            for via in ([False, True] if p["alias"] else [False]):
                rows_p = [r["a"] for r in appt_rows if not r["dup"] and r["a"]["p"] is p and (r["cells"][4].lstrip("0") in ((p["alias"] or "").lstrip("0"),)) == via]
                if any(a["status"] == "Completed" for a in rows_p) and not any(a["status"] == "Booked" for a in rows_p):
                    n += 1
        return n

    lena = [a for a in appts if a["t"] == RESTRICTED]
    oos = next(a for a in booked if a["t"] == "Sam Okafor" and a["forced"] is None and id(a["p"]) not in role_patients and not a["p"]["alias"])
    search_p = None
    for p in sorted(patients, key=lambda p: p["mrn"]):
        n = sum(1 for a in appts if a["p"] is p)
        if 2 <= n <= 4 and not p["alias"] and "twin_of" not in p and p not in twins and id(p) not in role_patients \
                and sum(1 for q in patients if p["last"].lower() in q["last"].lower()) == 1:
            search_p = p
            break
    assert search_p
    latest = max(appts, key=lambda a: (a["date"], a["start"]))
    assert sum(1 for a in appts if (a["date"], a["start"]) == (latest["date"], latest["start"])) == 1
    text_top = max((r for r in appt_rows if not r["dup"]), key=lambda r: (r["cells"][1], r["cells"][2]))
    free_slot = None
    for sh in shifts:
        if sh["date"] <= PAST_END or sh["t"] == RESTRICTED or (sh["t"], sh["date"]) in forced_days:
            continue
        taken = sorted((a["start"], a["start"] + a["dur"]) for a in appts if a["t"] == sh["t"] and a["date"] == sh["date"])
        cur = sh["start"]
        for st0, en0 in taken + [(sh["end"], sh["end"])]:
            if st0 - cur >= 90:
                free_slot = {"therapist": sh["t"], "date": sh["date"].isoformat(), "start": fmt_time(cur, 0), "minutes": 45,
                             "second_start": fmt_time(cur + 45, 0)}
                break
            cur = max(cur, en0)
        if free_slot:
            break
    assert free_slot
    future_lena_days = sorted({a["date"] for a in lena if a["date"] > PAST_END and a["date"] != date(2026, 9, 16)})
    lena_day = max(future_lena_days, key=lambda d0: (sum(1 for a in lena if a["date"] == d0), -d0.toordinal()))
    lena_day_appts = [a for a in lena if a["date"] == lena_day]
    rc_cancel_row = next(r for r in appt_rows if r["a"] is rc_cancel)

    def ainfo(a: dict) -> dict:
        return {"appointment": a["id"], "date": a["date"].isoformat(), "start": fmt_time(a["start"], 0), "minutes": a["dur"],
                "patient": pname(a["p"]), "therapist": a["t"], "status": a["status"],
                "file_lines": [r["line"] for r in appt_rows if r["a"] is a and not r["dup"]]}

    dur_examples = {}
    for r in appt_rows:
        txt = r["cells"][3]
        if (":" in txt or "h" in txt) and txt not in dur_examples:
            dur_examples[txt] = ainfo(r["a"])
    noshow_rows = [r for r in appt_rows if r["a"] in (noshow_a, noshow_b)]
    aug_noshow_by_patient = {}
    for a in aug:
        if a["status"] == "No-show":
            aug_noshow_by_patient[pname(a["p"])] = aug_noshow_by_patient.get(pname(a["p"]), 0) + 1
    lena_aug_noshow_patients = {}
    for a in aug:
        if a["status"] == "No-show" and a["t"] == RESTRICTED:
            lena_aug_noshow_patients[pname(a["p"])] = lena_aug_noshow_patients.get(pname(a["p"]), 0) + 1
    aug_noshow_patient_ids = {id(a["p"]) for a in aug if a["status"] == "No-show"}
    lena_patient_names = {pname(a["p"]) for a in lena}
    stranger = next(p for p in sorted(patients, key=lambda p: p["mrn"]) if pname(p) not in lena_patient_names and not p["alias"]
                    and "twin_of" not in p and p not in twins and any(a["p"] is p for a in appts))

    counts = {
        "seed": seed,
        "clinic": CLINIC,
        "admin": "the clinic director",
        "therapists": THERAPISTS,
        "restricted_login": RESTRICTED,
        "roster_pattern": {t: [{"weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][wd], "start": s, "end": e} for wd, s, e, _ in PATTERN[t]] for t in THERAPISTS},
        "baseline": {
            "staff_role": "Therapist",
            "viewer_role": "Viewer",
            "main_entity": "appointment",
            "main_entity_plural": "appointments",
            "scope_rule": f"appointments where {RESTRICTED} is the therapist",
            "scope_count": len(lena),
            "scope_count_if_therapist_matched_as_written": sum(1 for r in appt_rows if not r["dup"] and r["cells"][6] == RESTRICTED),
            "out_of_scope_example": ainfo(oos),
            "kpis": [
                {"name": "Booked appointments (status Booked)", "value": len(booked)},
                {"name": "Utilization, August 2026 (completed minutes / rostered minutes)", "value_pct": util()["pct"], **util()},
                {"name": "No-shows, August 2026", "value": sum(1 for a in aug if a["status"] == "No-show")},
                {"name": "Recall list (active, at least one completed visit, nothing booked)", "value": len(recall)},
            ],
            "scoped_kpi_1": sum(1 for a in booked if a["t"] == RESTRICTED),
            "search": {"term": search_p["last"], "patient": pname(search_p), "count": sum(1 for a in appts if a["p"] is search_p),
                       "appointments": [a["id"] for a in appts if a["p"] is search_p]},
            "filter": {"field": "Status", "value": "No-show", "count": sum(1 for a in appts if a["status"] == "No-show"),
                       "count_if_matched_as_written": sum(1 for r in appt_rows if not r["dup"] and r["cells"][8] == "No-show")},
            "sort": {"field": "Date and start time", "top": ainfo(latest),
                     "top_file_values": next(r["cells"][1:3] for r in appt_rows if r["a"] is latest),
                     "text_sort_top": {"appointment": text_top["cells"][0], "file_values": text_top["cells"][1:3]}},
            "export": {"rows": len(appts), "columns": ["Date", "Start Time", "Patient", "Therapist", "Status"]},
            "required_field": "Patient",
        },
        "patients": {
            "file_rows_excluding_header": len(pat_rows),
            "exact_duplicate_rows": N_EXACT_DUP,
            "reregistered_rows": N_REREG,
            "unique_patients": len(patients),
            "dedupe_rule": "Same patient when first name, last name (ignoring case) and date of birth (whatever the format) all match. Same name with a different date of birth is a different patient.",
            "wrong_counts": {"no_dedupe": len(pat_rows), "exact_rows_only": len(pat_rows) - N_EXACT_DUP, "name_only_dedupe": len(patients) - N_NAME_TWINS},
            "same_name_pairs": [{"name": pname(t), "dobs": sorted([t["dob"].isoformat(), next(p for p in patients if p.get("twin_of") is t)["dob"].isoformat()])} for t in twins],
            "reregistered": [{"name": pname(p), "record_numbers": [p["mrn"], p["alias"]],
                              "rows_as_written": sorted(({"line": r["line"], "record": r["cells"][0], "last_name": r["cells"][2], "dob": r["cells"][3]}
                                                        for r in pat_rows if r["p"] is p), key=lambda x: x["line"])} for p in rereg],
            "per_status": {s: sum(1 for p in patients if p["status"] == s) for s in ("Active", "Discharged")},
        },
        "roster": {
            "file_rows_excluding_header": len(roster_rows),
            "therapists": len(THERAPISTS),
            "august_rostered_hours": {t: util(t)["rostered_minutes"] / 60 for t in THERAPISTS},
            "no_shifts_on": "2026-09-07",
        },
        "appointments": {
            "file_rows_excluding_header": len(appt_rows),
            "duplicate_rows": N_DUP_APPTS,
            "appointments": len(appts),
            "per_status": {s: sum(1 for a in appts if a["status"] == s) for s in ("Completed", "No-show", "Cancelled", "Late cancel", "Booked")},
            "duration_examples": dur_examples,
            "import_conflict": {"a": ainfo(t_conf_a), "b": ainfo(t_conf_b)},
            "cancelled_overlap_not_conflict": {"cancelled": ainfo(t_canc_a), "booked": ainfo(t_canc_b)},
            "no_show_merge": {"patient": pname(noshow_merge), "record_numbers": [noshow_merge["mrn"], noshow_merge["alias"]],
                              "no_shows": [dict(ainfo(r["a"]), record_as_written=r["cells"][4]) for r in noshow_rows]},
            "patients_with_two_or_more_no_shows": len(flagged),
            "flagged_patients": sorted(pname(p) for p in flagged),
            "recall": {"count": len(recall), "includes_cancelled_only": {"patient": pname(recall_cancel), "cancelled_appointment": ainfo(rc_cancel),
                                                                          "status_as_written": rc_cancel_row["cells"][8]},
                       "excludes_discharged": pname(discharged_ex),
                       "excludes_booked_under_second_record": {"patient": pname(recall_dup), "record_numbers": [recall_dup["mrn"], recall_dup["alias"]],
                                                               "booked_appointment": dict(ainfo(rd_booked), record_as_written=next(r["cells"][4] for r in appt_rows if r["a"] is rd_booked))},
                       "count_if_record_numbers_not_merged": split_count_recall(),
                       "count_if_discharged_included": len(recall) + sum(1 for p in patients if p["status"] == "Discharged" and has(p, "Completed") and not has(p, "Booked"))},
            "utilization_august": {"clinic": util(), **{t: util(t) for t in THERAPISTS}},
        },
        "app_items": {
            "booking_test": {"existing": ainfo(t_lena_booked), "cancelled": ainfo(t_lena_cancel),
                             "overlap_start": "13:30", "back_to_back_start": "13:45", "cancelled_slot_start": "15:00", "minutes": 45,
                             "tester_patient": pname(tester_patient), "tester_patient_for_cancelled_slot": pname(tester_patient2)},
            "patient_conflict_test": {"patient": pname(patient_q), "existing": ainfo(t_priya), "lena_start": "14:30", "minutes": 30},
            "baseline_create_slot": free_slot,
            "no_show_test": {"patient": pname(tester_patient), "no_shows_before": noshows.get(id(tester_patient), 0), "date": "2026-09-11",
                             "starts": ["09:00", "09:45"], "minutes": 45, "restricted_existing_that_day": [ainfo(a) for a in lena if a["date"] == date(2026, 9, 11)],
                             "flagged_after": len(flagged) + 1},
            "restricted_day": {"date": lena_day.isoformat(), "appointments": len(lena_day_appts),
                               "by_status": {s: sum(1 for a in lena_day_appts if a["status"] == s) for s in ("Booked", "Cancelled")}},
        },
        "changes": {
            "1_week_of_2026_08_24_utilization": {t: week_util(t, date(2026, 8, 24)) for t in THERAPISTS},
            "1_august_no_shows_by_patient": dict(sorted(aug_noshow_by_patient.items())),
            "1_august_no_show_patients": len(aug_noshow_patient_ids),
            "1_august_patients_with_two_or_more": sorted(pname(p) for p in patients if sum(1 for a in aug if a["p"] is p and a["status"] == "No-show") >= 2),
            "1_restricted_august_no_shows_by_patient": dict(sorted(lena_aug_noshow_patients.items())),
            "2_type_minutes": {"Initial Assessment": 60, "Follow-up": 45, "Short Follow-up": 30},
            "2_restricted_shift_2026_09_23": {"start": "13:00", "end": "16:00", "existing": ainfo(t_sep23)},
            "2_tests": {"short_follow_up_at": "14:00", "short_ends": "14:30", "initial_at": "14:30", "initial_ends": "15:30",
                        "outside_shift": "16:00", "unrostered_day": "2026-09-22 10:00", "runs_past_end": "15:30 Follow-up (ends 16:15)",
                        "ends_at_end": "15:30 Short Follow-up (ends 16:00)"},
            "3_notes_example": next(dict(ainfo(r["a"]), note=r["cells"][9]) for r in appt_rows if r["cells"][9] and r["a"]["t"] == RESTRICTED and not r["dup"] and r["a"]["status"] == "Completed"),
            "3_patient_not_on_restricted_schedule": {"patient": pname(stranger), "record": stranger["mrn"]},
            "3_patient_on_restricted_schedule": (lambda p: {"patient": pname(p), "restricted_appointments": [a["id"] for a in lena if a["p"] is p]})(
                noshow_merge if any(a["p"] is noshow_merge for a in lena) else lena[0]["p"]),
        },
    }
    assert noshows.get(id(tester_patient), 0) == 0
    assert not any(a["p"] in (tester_patient, tester_patient2) and a["date"] in (date(2026, 9, 11), date(2026, 9, 16)) for a in appts)
    assert not any(a["p"] is patient_q and a["date"] == date(2026, 9, 16) and a is not t_priya for a in appts)

    header_p = ["Patient ID", "First Name", "Last Name", "Date of Birth", "Phone", "Email", "Referral Source", "Status", "Registered"]
    header_r = ["Date", "Therapist", "Email", "Start", "End", "Room"]
    header_a = ["Appt ID", "Date", "Start Time", "Duration", "Patient ID", "Patient", "Therapist", "Type", "Status", "Notes"]
    return {"counts": counts, "patients": (header_p, [r["cells"] for r in pat_rows]), "roster": (header_r, roster_rows),
            "appointments": (header_a, [r["cells"] for r in appt_rows])}


def main() -> None:
    seed = argparse_seed()
    out = build(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "patients.csv"), *out["patients"])
    write_csv(os.path.join(SEED_DIR, "roster.csv"), *out["roster"])
    write_csv(os.path.join(SEED_DIR, "appointments.csv"), *out["appointments"])
    write_text(os.path.join(REF_DIR, "counts.json"), json.dumps(out["counts"], indent=2) + "\n")
    c = out["counts"]
    print(f"patients.csv {c['patients']['file_rows_excluding_header']} rows -> {c['patients']['unique_patients']}; roster.csv "
          f"{c['roster']['file_rows_excluding_header']} rows; appointments.csv {c['appointments']['file_rows_excluding_header']} rows -> "
          f"{c['appointments']['appointments']}; scope {c['baseline']['scope_count']}")


if __name__ == "__main__":
    main()
