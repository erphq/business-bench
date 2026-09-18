#!/usr/bin/env python3
"""maintenance-notices: a plumbing contractor's riser valve schedule, its follow-up email, the building contact list and
the property manager's note become one water shutoff notice per building.

    python gen.py [--seed N]

Business: a five-building apartment community. The contractor is replacing the domestic water riser valves in four of
the buildings in October; residents need a notice for their own building.

Traps (each caught by a check, see task.yaml):
  * the contractor's later email moves Cypress House a week (valves on backorder)      (check: each notice carries its own facts)
  * the same email widens Birch House's shutoff: two risers feed it, so water is off 8:00 to 15:00, not 09:00 to 13:00
                                                                                         (check: each notice carries its own facts)
  * the schedule is in 24-hour text times; the manager wants am/pm, and Aspen's water comes back at noon (check: each notice carries its own facts)
  * Dogwood House has two work days with different hours, each in its own row             (check: each notice carries its own facts)
  * residents call their building's superintendent, not the contractor's crew lead whose cell is on the schedule; Birch's
    super is on vacation that week and the manager names the relief super              (check: each notice carries its own facts)
  * Elm House is on the schedule with no work (valves done in 2024) and gets no notice    (check: each notice carries its own facts)
"""
from __future__ import annotations
import os, sys
from datetime import date, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COMMUNITY = "Meadowbrook Terrace"
MANAGER_CO = "Larkin Residential"
CONTRACTOR = "Rivera Mechanical"
BUILDINGS = ["Aspen", "Birch", "Cypress", "Dogwood", "Elm"]


def ci(word: str) -> str:
    return "notices/*" + "".join(f"[{c.upper()}{c.lower()}]" for c in word) + "*"


def build(seed: int) -> dict:
    r = rng(seed * 29 + 13)
    used_f, ppl = set(), []
    while len(ppl) < 9:
        f, l = person(r)
        if f not in used_f:
            used_f.add(f); ppl.append((f, l))
    phones = set()
    def ph():
        while True:
            p = phone_digits(r)
            if p not in phones:
                phones.add(p); return p
    street = r.choice(["Meadowbrook Drive", "Terrace Lane", "Brook Hollow Road"])
    nums = sorted(r.sample(range(100, 900, 20), 5))
    B = {}
    for i, b in enumerate(BUILDINGS):
        B[b] = {"name": f"{b} House", "address": f"{nums[i]} {street}", "super": f"{ppl[i][0]} {ppl[i][1]}", "super_phone": ph()}
    # Cypress and Dogwood share one super in real life; keep them distinct people here but same office line
    relief = {"name": f"{ppl[5][0]} {ppl[5][1]}", "phone": ph()}
    crew = {"name": f"{ppl[6][0]} {ppl[6][1]}", "phone": ph()}
    manager = {"name": f"{ppl[7][0]} {ppl[7][1]}", "first": ppl[7][0]}
    office = ph()
    emergency = ph()
    work = {
        "Aspen": [dict(day=date(2026, 10, 14), start=(8, 0), end=(12, 0))],
        "Birch": [dict(day=date(2026, 10, 15), start=(8, 0), end=(15, 0), sched_start=(9, 0), sched_end=(13, 0))],
        "Cypress": [dict(day=date(2026, 10, 27), sched_day=date(2026, 10, 20), start=(8, 30), end=(12, 30))],
        "Dogwood": [dict(day=date(2026, 10, 21), start=(9, 0), end=(14, 0)), dict(day=date(2026, 10, 22), start=(9, 0), end=(11, 30))],
    }
    units = {"Aspen": "All units (one riser)", "Birch": "All units", "Cypress": "All units", "Dogwood": ["Units 101-118 (east riser)", "Units 119-136 (west riser)"]}
    return dict(B=B, relief=relief, crew=crew, manager=manager, office=office, emergency=emergency, work=work, units=units)


def hm(t) -> str:
    return f"{t[0]:02d}:{t[1]:02d}"


def ampm(t) -> str:
    h, m = t
    if (h, m) == (12, 0):
        return "12:00 noon"
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def emit(seed: int) -> None:
    d = build(seed)
    B, W = d["B"], d["work"]
    ws, ref, sol = task_dirs(HERE)
    # ---- contractor schedule
    rows = []
    for b in BUILDINGS:
        if b == "Elm":
            rows.append([B[b]["name"], "", "No work - riser valves replaced 2024", "", "", "", "", ""])
            continue
        for i, w in enumerate(W[b]):
            u = d["units"][b][i] if isinstance(d["units"][b], list) else d["units"][b]
            rows.append([B[b]["name"], w.get("sched_day", w["day"]), "Replace domestic water riser shutoff valves", u,
                         hm(w.get("sched_start", w["start"])), hm(w.get("sched_end", w["end"])), d["crew"]["name"], phone_variant(d["crew"]["phone"], 3)])
    write_xlsx(os.path.join(ws, "riser_valve_schedule_rivera_mechanical.xlsx"), {
        "Schedule": {"merged_title": f"{CONTRACTOR} - {COMMUNITY} riser valve replacement - October 2026",
                     "preamble": [["Prepared 2026-09-18. Times are water OFF / water back ON (estimated)."]],
                     "header": ["Building", "Date", "Work", "Units affected", "Water off", "Water on (est.)", "Crew lead", "Crew lead cell"],
                     "rows": rows, "widths": {"A": 16, "B": 12, "C": 40, "D": 28, "G": 18, "H": 16}},
    }, creator=CONTRACTOR)
    # ---- contractor follow-up
    cy, bi = W["Cypress"][0], W["Birch"][0]
    write_email_thread(os.path.join(ws, "email_from_rivera_mechanical.txt"), [
        {"from": f"{d['crew']['name']} <scheduling@riveramechanical.com>", "to": f"{d['manager']['name']} <{d['manager']['first'].lower()}@larkinresidential.com>",
         "date": "Tue, 29 Sep 2026 14:12", "subject": "Meadowbrook riser valves - two changes",
         "body": (f"Hi {d['manager']['first']},\n\nTwo changes to the schedule we sent on the 18th:\n\n"
                  f"1. Cypress House: the 2-inch valves are on backorder, so Cypress moves from Tuesday October 20 to Tuesday October 27. Same hours.\n\n"
                  "2. Birch House: when we walked it last week we found it's fed by two risers, not one. We'll need the water off from 8:00 in the morning "
                  "until 3:00 in the afternoon that day instead of 9 to 1. Date doesn't change.\n\n"
                  "Everything else stays as scheduled.\n\n" + d["crew"]["name"] + f"\n{CONTRACTOR}")}])
    # ---- contacts
    crows = [[B[b]["name"], B[b]["address"], B[b]["super"], phone_variant(B[b]["super_phone"], [0, 1, 3, 0, 2][i]), phone_variant(d["office"], 0)]
             for i, b in enumerate(BUILDINGS)]
    write_csv(os.path.join(ws, "building_contacts.csv"), ["Building", "Address", "Superintendent", "Super cell", "Leasing office"], crows)
    # ---- manager note
    write_text(os.path.join(ws, "note_from_property_manager.txt"),
        f"From {d['manager']['name']}, {MANAGER_CO} - Sept 30\n\n"
        f"The riser valve work at {COMMUNITY} needs resident notices. Rivera's schedule and their email from yesterday are in the folder.\n\n"
        "- One notice per building that has work, named after the building, in a notices folder. Buildings with no work don't get one.\n"
        "- Each notice: the date(s), the time the water goes off and the time it's expected back on (write times as am/pm, residents don't read 24-hour times), "
        "which units are affected, and what to do: fill some containers the night before, don't start the dishwasher or laundry during the shutoff, "
        "and run the cold tap for a minute afterwards if the water looks cloudy.\n"
        "- Questions go to the building's superintendent. Give their cell. Residents should NOT call Rivera's crew.\n"
        f"- {B['Birch']['super']} (Birch) is on vacation October 12-16. For Birch, give the relief super, {d['relief']['name']}, cell {phone_variant(d['relief']['phone'], 0)}.\n"
        f"- For a water emergency after hours the 24-hour maintenance line is {phone_variant(d['emergency'], 0)}.\n")

    # ---- reference + solution
    facts = {"buildings": []}
    for b in BUILDINGS:
        if b == "Elm":
            facts["buildings"].append({"key": "elm", "name": B[b]["name"], "gets_notice": False})
            continue
        contact = d["relief"]["phone"] if b == "Birch" else B[b]["super_phone"]
        facts["buildings"].append({
            "key": b.lower(), "name": B[b]["name"], "gets_notice": True, "contact_phone": contact,
            "days": [{"date": w["day"].isoformat(), "start": list(w["start"]), "end": list(w["end"])} for w in W[b]],
            "stale_dates": [w["sched_day"].isoformat() for w in W[b] if "sched_day" in w],
            "stale_times": [list(t) for w in W[b] for t in (w.get("sched_start"), w.get("sched_end")) if t and t not in (w["start"], w["end"])],
            "wrong_phones": [d["crew"]["phone"]] + [B[o]["super_phone"] for o in BUILDINGS if o != b] + ([B["Birch"]["super_phone"]] if b == "Birch" else []) +
                            ([d["relief"]["phone"]] if b != "Birch" else []),
        })
    write_json(os.path.join(ref, "facts.json"), facts)
    for b in BUILDINGS:
        if b == "Elm":
            continue
        contact_name = d["relief"]["name"] + " (relief superintendent)" if b == "Birch" else B[b]["super"] + " (superintendent)"
        contact_phone = d["relief"]["phone"] if b == "Birch" else B[b]["super_phone"]
        lines = [f"# Water shutoff notice - {B[b]['name']}", "", f"{B[b]['address']}", "",
                 "Dear residents,", "",
                 f"{CONTRACTOR} will replace the domestic water riser valves in {B[b]['name']}. The water will be turned off during the work:", ""]
        for i, w in enumerate(W[b]):
            u = d["units"][b][i] if isinstance(d["units"][b], list) else d["units"][b]
            lines.append(f"- **{w['day'].strftime('%A, %B %-d, %Y')}**: water off from {ampm(w['start'])} until about {ampm(w['end'])}. Affected: {u.lower()}.")
        lines += ["", "Please:", "", "- Fill a few containers with water the night before.",
                  "- Don't start the dishwasher or laundry while the water is off.",
                  "- When the water comes back, run the cold tap for a minute if it looks cloudy.", "",
                  f"Questions: {contact_name}, cell {phone_variant(contact_phone, 0)}.",
                  f"After-hours water emergencies: 24-hour maintenance line {phone_variant(d['emergency'], 0)}.", "",
                  f"Thank you,", f"{d['manager']['name']}", f"{MANAGER_CO}", ""]
        write_text(os.path.join(sol, "notices", f"{b}_House.md"), "\n".join(lines))

    write_task_yaml(HERE, {
        "id": "maintenance-notices", "track": "desk", "category": "drafting",
        "title": "Water shutoff notices for the riser valve work",
        "ask": (f"Please write the resident notices for next month's water shutoffs at {COMMUNITY} - one for each building, in a notices folder. "
                f"{d['manager']['first']}'s note says what goes in them.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the contractor's later email moves Cypress House from October 20 to October 27 (check: each notice carries its own facts)",
            "the same email widens Birch House's shutoff to 8:00 AM - 3:00 PM from the scheduled 09:00-13:00 (check: each notice carries its own facts)",
            "the schedule gives 24-hour text times and the manager wants am/pm; Aspen's water comes back at 12:00, noon (check: each notice carries its own facts)",
            "Dogwood House has two work days with different hours on separate rows; its notice needs both (check: each notice carries its own facts)",
            f"residents call their own building's superintendent, not the contractor crew lead whose cell is on every schedule row; Birch's super is on vacation that week, so Birch's notice gives the relief super {d['relief']['name']} (check: each notice carries its own facts)",
            "Elm House is on the schedule with no work and gets no notice (check: each notice carries its own facts)",
        ],
        "checks": [
            {"type": "file_exists", "name": "notice for Aspen House", "path": ci("aspen")},
            {"type": "file_exists", "name": "notice for Birch House", "path": ci("birch")},
            {"type": "file_exists", "name": "notice for Cypress House", "path": ci("cypress")},
            {"type": "file_exists", "name": "notice for Dogwood House", "path": ci("dogwood")},
            {"type": "custom", "name": "each notice carries its own facts", "module": "check.py"},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
