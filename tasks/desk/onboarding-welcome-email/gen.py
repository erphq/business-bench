#!/usr/bin/env python3
"""onboarding-welcome-email: an engineering firm's new hire form, IT's equipment kits, the onboarding email thread and
the first-day information sheet become the welcome email to the new hire.

    python gen.py [--seed N]

Business: a civil engineering consultancy. A project engineer is joining the stormwater group; HR wants the welcome
email drafted with the right first day, manager, equipment and arrival details.

Traps (each caught by a check, see task.yaml):
  * the form says the first day is Monday October 5; HR's follow-up moves it to Monday October 12 because the
    background check clears on the 8th                                      (check: start date, manager and desk phone)
  * the form names the hiring manager, who writes that they move to lead the Denver office on October 1 and that the new
    hire reports to the incoming stormwater lead                             (check: start date, manager and desk phone)
  * the form's equipment kit is the standard engineering kit; the manager asks for the CAD kit instead (16-inch
    workstation, two 27-inch monitors, 3D mouse)                             (checks: CAD kit items; standard kit items absent)
  * both kits include a desk phone; the manager says to skip it because the team uses Teams calling
                                                                              (check: start date, manager and desk phone)
  * the first-day sheet gives an 8:30 arrival for new-hire orientation although regular office hours start at 8:00
                                                                              (check: first-day logistics)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

FIRM = "Palisade Civil Engineering"
DOMAIN = "palisadecivil.com"
FORM_START = date(2026, 10, 5)
START = date(2026, 10, 12)


def build(seed: int) -> dict:
    r = rng(seed * 41 + 19)
    used_f, used_l, ppl = set(), set(), []
    while len(ppl) < 6:
        f, l = person(r)
        if f in used_f or l in used_l or f in used_l or l in used_f or f == l:
            continue
        used_f.add(f); used_l.add(l); ppl.append((f, l))
    P = {k: {"first": f, "last": l, "full": f"{f} {l}"} for k, (f, l) in zip(["hire", "old_mgr", "new_mgr", "hr", "it", "buddy"], ppl)}
    street_no = r.choice([1180, 1420, 2215])
    floor = r.choice([3, 4, 5])
    return dict(P=P, street_no=street_no, floor=floor, salary=r.choice([78500, 82000, 84500]))


KITS = [
    ("ENG-STD", "Laptop, 14-inch (Dell Latitude 7450)", 1, ""),
    ("ENG-STD", "Docking station", 1, ""),
    ("ENG-STD", "Monitor, 24-inch", 2, ""),
    ("ENG-STD", "USB headset", 1, ""),
    ("ENG-STD", "Desk phone (Yealink T54W)", 1, ""),
    ("ENG-CAD", "Mobile workstation, 16-inch (Dell Precision 5690, RTX GPU)", 1, "Civil 3D / Revit users"),
    ("ENG-CAD", "Docking station (Thunderbolt 4)", 1, ""),
    ("ENG-CAD", "Monitor, 27-inch", 2, ""),
    ("ENG-CAD", "3D mouse (3Dconnexion SpaceMouse)", 1, ""),
    ("ENG-CAD", "USB headset", 1, ""),
    ("ENG-CAD", "Desk phone (Yealink T54W)", 1, ""),
    ("ADMIN", "Laptop, 14-inch (Dell Latitude 5450)", 1, ""),
    ("ADMIN", "Monitor, 24-inch", 1, ""),
    ("ADMIN", "Desk phone (Yealink T54W)", 1, ""),
    ("FIELD", "Rugged tablet (Panasonic Toughbook G2)", 1, "Survey crews"),
    ("FIELD", "Hi-vis vest and hard hat", 1, ""),
]


def emit(seed: int) -> None:
    d = build(seed)
    P = d["P"]
    hire, old, new, hr, it, buddy = (P[k] for k in ("hire", "old_mgr", "new_mgr", "hr", "it", "buddy"))
    ws, ref, sol = task_dirs(HERE)
    addr = f"{d['street_no']} Canal Street, Suite {d['floor']}00, Sacramento, CA 95814"
    write_xlsx(os.path.join(ws, f"new_hire_form_{hire['last']}.xlsx"), {
        "New hire": {"merged_title": f"{FIRM} - New hire onboarding form", "preamble": [["Submitted by HR, 2026-09-02"]],
                     "header": ["Field", "Value"],
                     "rows": [["Legal name", hire["full"]], ["Preferred first name", hire["first"]], ["Position", "Project Engineer I"],
                              ["Group", "Stormwater & Drainage"], ["Employment type", "Full-time, exempt"], ["Start date", FORM_START],
                              ["Hiring manager", old["full"]], ["Work location", addr], ["Equipment kit", "ENG-STD"],
                              ["Annual salary", f"${d['salary']:,}"], ["Personal email", email_for(rng(seed), hire["first"], hire["last"])],
                              ["Onboarding buddy", buddy["full"]]],
                     "widths": {"A": 24, "B": 60}}}, creator="HR")
    write_csv(os.path.join(ws, "it_equipment_kits.csv"), ["Kit", "Item", "Qty", "Notes"], [list(k) for k in KITS])
    write_email_thread(os.path.join(ws, "email_thread_onboarding.txt"), [
        {"from": f"{hr['full']} <{hr['first'].lower()}@{DOMAIN}>", "to": f"{old['full']} <{old['first'].lower()}@{DOMAIN}>; {it['full']} <it@{DOMAIN}>",
         "date": "Wed, 2 Sep 2026 10:40", "subject": f"New hire: {hire['full']}, Project Engineer I",
         "body": (f"Hi both,\n\n{hire['full']} accepted our offer for Project Engineer I in Stormwater. The new hire form is in the onboarding folder. "
                  f"First day is Monday, October 5. {it['first']}, the form has the standard engineering kit.\n\n{hr['first']}")},
        {"from": f"{old['full']} <{old['first'].lower()}@{DOMAIN}>", "to": f"{hr['first'].lower()}@{DOMAIN}; it@{DOMAIN}",
         "date": "Thu, 3 Sep 2026 08:15", "subject": f"RE: New hire: {hire['full']}, Project Engineer I",
         "body": (f"Great news. Two things for {it['first']}: {hire['first']} will be in Civil 3D most of the day, so please set up the CAD kit "
                  "instead of the standard one. And skip the desk phone - the whole group moved to Teams calling in the spring.\n\n"
                  f"Also, as you know, I'm moving to lead the Denver office from October 1, so {hire['first']} won't be reporting to me. "
                  f"{new['full']} takes over the Stormwater group and will be {hire['first']}'s manager from day one. "
                  f"{new['first']} is copied on the rest of this.\n\n{old['first']}")},
        {"from": f"{it['full']} <it@{DOMAIN}>", "to": f"{old['first'].lower()}@{DOMAIN}; {hr['first'].lower()}@{DOMAIN}; {new['first'].lower()}@{DOMAIN}",
         "date": "Thu, 3 Sep 2026 11:02", "subject": f"RE: New hire: {hire['full']}, Project Engineer I",
         "body": "Got it: CAD kit, no desk phone. It will be set up at the desk the Friday before the start date.\n\n" + it["first"]},
        {"from": f"{hr['full']} <{hr['first'].lower()}@{DOMAIN}>", "to": f"{old['first'].lower()}@{DOMAIN}; it@{DOMAIN}; {new['first'].lower()}@{DOMAIN}",
         "date": "Wed, 9 Sep 2026 15:27", "subject": f"RE: New hire: {hire['full']}, Project Engineer I",
         "body": (f"Correction on the start date: the background check provider says {hire['first']}'s check won't clear until October 8, so the first day is "
                  f"now Monday, October 12. I've let {hire['first']} know by phone; nothing else changes. I'll send the welcome email this week.\n\n{hr['first']}")},
    ])
    write_text(os.path.join(ws, "first_day_info.md"),
        f"# First day at {FIRM}\n\n_For HR to use in welcome emails. Updated January 2026._\n\n"
        f"**Office:** {addr}. Take the elevator to floor {d['floor']} and check in at reception.\n\n"
        "**Office hours:** 8:00 AM to 5:00 PM, Monday to Friday.\n\n"
        "**New hires:** arrive at 8:30 AM on your first day. Orientation with HR runs 8:30 to 10:00, then your manager takes you to your desk.\n\n"
        "**Parking:** the Canal Street garage entrance is on 12th Street. Bring your ticket to reception to have it validated on your first day.\n\n"
        "**Bring:** original documents for your I-9 - either one List A document (such as a passport) or one List B and one List C document "
        "(such as a driver's license and a Social Security card).\n\n"
        "**Lunch:** your group takes you to lunch on your first day.\n")

    facts = {"start": START.isoformat(), "form_start": FORM_START.isoformat(), "new_mgr_last": new["last"], "old_mgr_last": old["last"],
             "new_mgr": new["full"], "old_mgr": old["full"]}
    write_json(os.path.join(ref, "facts.json"), facts)
    email = (f"Subject: Welcome to {FIRM}, {hire['first']}!\n\n"
             f"Hi {hire['first']},\n\n"
             f"Welcome to {FIRM}! We're excited to have you join the Stormwater & Drainage group as a Project Engineer I.\n\n"
             "## Your first day\n\n"
             f"Your first day is Monday, October 12, 2026. Please arrive at 8:30 AM at {addr}. Take the elevator to floor {d['floor']} and check in "
             "at reception. You'll start with orientation with HR from 8:30 to 10:00.\n\n"
             "Parking: use the Canal Street garage (entrance on 12th Street) and bring your ticket to reception to have it validated.\n\n"
             "Please bring original documents for your I-9: one List A document such as a passport, or one List B and one List C document "
             "such as a driver's license and a Social Security card.\n\n"
             "## Your manager\n\n"
             f"You'll report to {new['full']}, who leads the Stormwater group. After orientation {new['first']} will take you to your desk, and the group "
             "will take you out to lunch.\n\n"
             "## Your equipment\n\n"
             "Your desk will be set up before you arrive with:\n\n"
             "- 16-inch mobile workstation (Dell Precision 5690)\n- Thunderbolt docking station\n- Two 27-inch monitors\n"
             "- 3D mouse (3Dconnexion SpaceMouse)\n- USB headset\n\n"
             "The team uses Teams for calls, so your headset is all you need.\n\n"
             "If you have any questions before your first day, just reply to this email.\n\n"
             f"See you soon,\n\n{hr['full']}\nHuman Resources, {FIRM}\n")
    write_text(os.path.join(sol, "welcome.md"), email)

    write_task_yaml(HERE, {
        "id": "onboarding-welcome-email", "track": "desk", "category": "drafting",
        "title": "Welcome email for the new project engineer",
        "ask": (f"Please write the welcome email for {hire['full']}, our new project engineer. The new hire form, the onboarding emails and the first-day "
                "sheet are in the folder. Save it as welcome.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the form and HR's first email give Monday October 5; HR's follow-up moves the first day to Monday October 12 (check: start date, manager and desk phone)",
            f"the form names {old['full']} as hiring manager, but that manager leaves for the Denver office on October 1 and {new['full']} is the manager from day one (check: start date, manager and desk phone)",
            "the form's kit is ENG-STD (14-inch laptop, two 24-inch monitors); the manager asks for the ENG-CAD kit (16-inch workstation, two 27-inch monitors, 3D mouse) (checks: CAD kit items; standard kit items absent)",
            "both kits list a desk phone and the manager says to skip it because the group uses Teams calling (check: start date, manager and desk phone)",
            "the first-day sheet's office hours start at 8:00 but new hires arrive at 8:30 for orientation (check: first-day logistics)",
        ],
        "checks": [
            {"type": "file_exists", "name": "welcome.md exists", "path": "welcome.md"},
            {"type": "custom", "name": "start date, manager and desk phone", "module": "check.py"},
            {"type": "text_matches_all", "name": "CAD kit items", "path": "welcome.md",
             "patterns": [r"\b27(\s*-?\s*(inch|in\b\.?)|\s*[\"”″])", r"3\s*-?\s*d\s*mouse|space\s*mouse|3dconnexion", r"\b16(\s*-?\s*(inch|in\b\.?)|\s*[\"”″])|workstation|precision"]},
            {"type": "text_not_contains", "name": "standard kit items absent", "path": "welcome.md",
             "phrases": ["latitude", "24-inch", "24 inch", "24\"", "24”", "24-in "]},
            {"type": "text_matches_all", "name": "first-day logistics", "path": "welcome.md",
             "patterns": [r"(?<![\d:])8:30", rf"\b{d['street_no']}\s+Canal"]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
