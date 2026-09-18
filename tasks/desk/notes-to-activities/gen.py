#!/usr/bin/env python3
"""notes-to-activities: a sign shop's spreadsheet account notes split into one CRM activity per dated note.

    python gen.py [--seed N] [--naive DIR]

Business: Northstar Sign Co. makes storefront, monument and wayfinding signs for local businesses. Sales has kept an
accounts tracker in a workbook since last November, with every call, email and site visit typed into one Notes cell.
They are moving to Pipedrive and want the history as activities.

Traps (each caught by a check, see task.yaml):
  * a Notes cell holds several entries separated by new lines, " | " or " ; ", and some entries wrap onto a second
    line with no date of their own                                         (checks: row count; activity date and type)
  * entry dates are written 3/14, 03/14/26, Mar 14, March 14th, 14 Mar, the 14th of March, Tue 3/10; entries
    without a year are Nov-Dec 2025 or Jan-Aug 2026; some bodies mention a later install date that is not an
    activity                                                               (checks: activity date and type; row count)
  * owner initials are written JM, jm, J.M., (KT) or left off; left off means the account's rep; MB left the company
    and her history goes to Sofia Cruz                                     (check: owner)
  * type comes from the keyword table in the notes                        (check: activity date and type)
  * accounts with an empty Notes cell get no activity                     (check: accounts with activities)
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["Account ID", "Organization", "Activity Date", "Type", "Owner Email", "Note"]
USERS = [("Jason Miller", "JM", "jason.miller@northstarsigns.com", "Active"),
         ("Kara Thompson", "KT", "kara.thompson@northstarsigns.com", "Active"),
         ("Diego Perez", "DP", "diego.perez@northstarsigns.com", "Active"),
         ("Sofia Cruz", "SC", "sofia.cruz@northstarsigns.com", "Active"),
         ("Maria Bennett", "MB", "maria.bennett@northstarsigns.com", "Deactivated")]
EMAIL = {u[1]: u[2] for u in USERS}
EMAIL["MB"] = EMAIL["SC"]            # deactivated user's history goes to Sofia
BODIES = {
    "Call": ["called, left vm about the {thing}", "called the owner, wants pricing on the {thing}", "phoned re: permit status for the {thing}",
             "call with GM, budget is tight until next quarter", "left voicemail, no answer on the {thing} proof"],
    "Email": ["emailed revised quote for the {thing}", "sent quote for {thing} plus install", "emailed proof v2 of the {thing}",
              "email from office mgr - they approved colors", "sent quote, install booked for {install}"],
    "Meeting": ["site visit, measured the {thing} wall", "met with facilities about the {thing}", "stopped by with vinyl samples",
                "walkthrough with landlord for the {thing}", "met owner on site, install booked for {install}"],
}
THINGS = ["monument sign", "channel letters", "lobby sign", "window graphics", "pylon sign", "wayfinding package", "A-frame",
          "vehicle wrap", "blade sign", "ADA room signs"]
COMPANIES_ = ["Harbor Point Dental", "Evergreen Credit Union", "Cascade Physical Therapy", "Mill Creek Brewing", "Summit Title Co",
              "Riverside Veterinary", "Lighthouse Church", "Pioneer Hardware", "Bluebird Preschool", "Copperline Salon",
              "Grandview Apartments", "Two Rivers Realty", "Orchard Park HOA", "Fern Hill Pediatrics", "Keystone Auto Glass",
              "Willamette Yoga", "Sunrise Senior Living", "Hilltop Pizza Co", "Maplewood Library Friends", "Beacon Insurance Group",
              "Tidepool Aquarium Shop", "Redstone Chiropractic", "Canyon View Motel", "Juniper Ridge Winery"]
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def date_text(r, d: date, style: int) -> str:
    return [f"{d.month}/{d.day}", f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}", f"{MONTH_ABBR[d.month - 1]} {d.day}",
            f"{MONTH_FULL[d.month - 1]} {ordinal(d.day)}", f"{d.day} {MONTH_ABBR[d.month - 1]}",
            f"the {ordinal(d.day)} of {MONTH_FULL[d.month - 1]}", f"{d.strftime('%a')} {d.month}/{d.day}",
            f"{d.month}/{d.day}/{d.year}"][style % 8]


def build(seed: int) -> dict:
    r = rng(seed)
    comps = r.sample(COMPANIES_, 22)
    reps = ["JM", "KT", "DP", "MB"]
    accounts = []
    ids = r.sample(range(1001, 1499), len(comps))
    for i, c in enumerate(comps):
        acct = {"id": f"NS-{ids[i]}", "name": c, "rep": reps[i % 4], "notes": []}
        n = 0 if i in (3, 11, 17) else r.choice([1, 2, 2, 3, 3, 4, 5])
        days = sorted(r.sample(range(0, (date(2026, 8, 31) - date(2025, 11, 3)).days), n))
        for k, dd in enumerate(days):
            d = date(2025, 11, 3) + timedelta(days=dd)
            typ = r.choice(list(BODIES))
            body = r.choice(BODIES[typ]).format(thing=r.choice(THINGS), install=f"{r.randint(9, 11)}/{r.randint(1, 28)}")
            who_roll = r.random()
            who = acct["rep"] if who_roll < 0.6 else r.choice(["JM", "KT", "DP", "SC"]) if who_roll < 0.85 else None
            if who == "MB" and d > date(2026, 1, 15):
                who = "SC"                                   # Maria left mid-January; Sofia signs from then on
            acct["notes"].append({"date": d, "type": typ, "body": body, "initials": who})
        # distinct dates only
        seen, uniq = set(), []
        for nt in acct["notes"]:
            if nt["date"] not in seen:
                seen.add(nt["date"]); uniq.append(nt)
        acct["notes"] = uniq
        accounts.append(acct)
    return {"accounts": accounts}


def owner_of(acct: dict, note: dict) -> str:
    return EMAIL[note["initials"] or acct["rep"]]


def render_cell(r, acct: dict) -> tuple[str, list]:
    """Returns the Notes cell text and, per note, how it was written (for pins)."""
    notes = list(acct["notes"])
    if r.random() < 0.4:
        notes.reverse()                                       # some reps type newest first
    parts, meta = [], []
    for nt in notes:
        style = r.randrange(8)
        if nt["date"].year == 2025 and style in (1, 7):
            style = 0                                         # year-less forms carry the Nov/Dec trap
        dt = date_text(r, nt["date"], style)
        ini = nt["initials"]
        ini_txt = "" if not ini else r.choice([ini, ini.lower(), f"{ini[0]}.{ini[1]}.", ini])
        layout = r.randrange(4)
        if not ini:
            entry = f"{dt} - {nt['body']}"
        elif layout == 0:
            entry = f"{dt} {ini_txt} - {nt['body']}"
        elif layout == 1:
            entry = f"{dt}: {nt['body']} ({ini_txt})"
        elif layout == 2:
            entry = f"{ini_txt} {dt} {nt['body']}"
        else:
            entry = f"({dt} {ini_txt}) {nt['body']}"
        if r.random() < 0.2:
            entry += "\n   " + r.choice(["they want it before the grand opening", "follow up after the board meets",
                                         "owner prefers texts", "need the landlord sign-off first"])
        parts.append(entry)
        meta.append({"date": nt["date"], "style": style, "wrapped": "\n   " in entry, "ini": ini_txt})
    seps = [r.choice(["\n", " | ", " ; ", "\n\n"]) for _ in parts[1:]]
    cell = parts[0] if parts else ""
    for sep, p in zip(seps, parts[1:]):
        cell += sep + p
    return cell, meta


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    r = rng(seed + 17)
    cells = {}
    metas = {}
    for a in d["accounts"]:
        cells[a["id"]], metas[a["id"]] = render_cell(r, a)
    if naive_dir:
        write_naive(d, cells, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    write_xlsx(os.path.join(ws, "accounts_tracker.xlsx"), {"Accounts": {
        "header": ["Account ID", "Company", "City", "Stage", "Rep", "Notes"],
        "rows": [[a["id"], a["name"], r.choice(["Salem", "Portland", "Beaverton", "Tigard", "Lake Oswego", "Gresham"]),
                  r.choice(["Prospect", "Quoted", "Won", "Lost", "Installed"]), a["rep"], cells[a["id"]]] for a in d["accounts"]],
        "widths": {"B": 26, "F": 90}}}, creator="Northstar Sales")
    write_csv(os.path.join(ws, "pipedrive_users_export.csv"), ["Name", "Email", "Role", "Status"],
              [[u[0], u[2], "Regular user" if u[1] != "JM" else "Admin", u[3]] for u in USERS])
    write_csv(os.path.join(ws, "pipedrive_activities_template.csv"), HEADER,
              [["NS-0000", "Example Co", "2026-01-31", "Call", "someone@northstarsigns.com", "called about example"]])
    write_text(os.path.join(ws, "crm_move_notes.md"),
               "# Moving the tracker notes into Pipedrive\n"
               "\n"
               "From Jason, 11 Sept. Pipedrive's activity import is set up with the template in this folder.\n"
               "\n"
               "- One activity per note. Most Notes cells have several notes in them. Each note starts with the date it\n"
               "  happened; a line that just carries on from the note above is part of that note, not a new one.\n"
               "- We started the tracker in November 2025. If a note doesn't say the year, it's November or December 2025\n"
               "  or January to August 2026. A date later in the text (like an install date) is not a new note.\n"
               "- Activity Date as YYYY-MM-DD.\n"
               "- Type is Call, Email or Meeting:\n"
               "  - Call: called, call, phoned, left vm, left voicemail\n"
               "  - Email: emailed, email, sent quote\n"
               "  - Meeting: met, site visit, stopped by, walkthrough\n"
               "- Owner Email is the Pipedrive user who did it. The initials on the note are the person (JM = Jason Miller\n"
               "  and so on, however they're typed). No initials means it was the account's rep.\n"
               "- Maria Bennett (MB) left in January and her login is deactivated; Pipedrive won't take activities for her,\n"
               "  so everything that would be hers goes under Sofia Cruz, who took over her accounts.\n"
               "- Note: the text of the note is fine as it is, without the date and initials.\n"
               "- Accounts with nothing in Notes don't need anything.\n")

    rows, owner_pins, date_pins = [], set(), set()
    for a in d["accounts"]:
        mm = {m["date"]: m for m in metas[a["id"]]}
        for nt in sorted(a["notes"], key=lambda x: x["date"]):
            key = f"{a['id']}|{nt['date'].isoformat()}"
            rows.append([a["id"], a["name"], nt["date"].isoformat(), nt["type"], owner_of(a, nt), nt["body"]])
            m = mm[nt["date"]]
            if nt["initials"] is None or a["rep"] == "MB" and nt["initials"] in (None, "MB") or "." in m["ini"] or m["ini"].islower():
                owner_pins.add(key)
            if nt["date"].year == 2025 or m["style"] in (3, 5, 6) or m["wrapped"] or "install booked" in nt["body"]:
                date_pins.add(key)
    write_csv(os.path.join(ref, "activities.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "activities.csv"), HEADER, rows)
    write_json(os.path.join(ref, "notes.json"), {"activities": len(rows), "owner_pins": sorted(owner_pins), "date_pins": sorted(date_pins)})
    write_task_yaml(HERE, {
        "id": "notes-to-activities", "track": "desk", "category": "reformatting",
        "title": "Split the tracker notes into Pipedrive activities",
        "ask": ("We're moving sales onto Pipedrive. Can you turn the notes in our accounts tracker into their activity import "
                "and save it as activities.csv? Jason's notes on how he wants it and the template are in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "each Notes cell holds several dated entries separated by a new line, a blank line, ' | ' or ' ; ', and some "
            "entries wrap onto an indented second line with no date; splitting on new lines alone both merges and splits "
            f"activities (checks: row count, {len(rows)} activities; activity date and type)",
            "entry dates are written 3/14, 03/14/26, Mar 14, March 14th, 14 Mar, 'the 14th of March' and 'Tue 3/10', "
            "sometimes after the initials; year-less November and December entries are 2025, so a parser that defaults to "
            "the current year puts them ten months in the future (check: activity date and type)",
            "bodies such as 'sent quote, install booked for 10/15' carry a second date that is not an activity; splitting on "
            "every date adds rows (checks: row count; activity date and type)",
            "initials are written JM, jm, J.M., (KT) or left off; left off means the account's Rep, and MB (Maria Bennett, "
            "deactivated) maps to Sofia Cruz, including notes on MB accounts with no initials (check: owner)",
            "Type comes from the keyword table (left vm is a Call, sent quote is an Email, stopped by is a Meeting) "
            "(check: activity date and type)",
            "three accounts have an empty Notes cell and get no activity (check: accounts with activities)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Pipedrive template columns, exact order", "path": "activities.csv", "columns": HEADER, "exact": True},
            {"type": "csv_set_equal", "name": "accounts with activities", "path": "activities.csv", "column": "Account ID", "ref": "activities.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "activities.csv", "equals_ref": "activities.csv"},
            {"type": "csv_values_match", "name": "activity date and type", "path": "activities.csv", "ref": "activities.csv",
             "key": ["Account ID", "Activity Date"], "columns": ["Type"], "min_accuracy": 1.0, "must_match_keys": sorted(date_pins)},
            {"type": "csv_values_match", "name": "owner", "path": "activities.csv", "ref": "activities.csv",
             "key": ["Account ID", "Activity Date"], "columns": ["Owner Email"], "min_accuracy": 1.0, "must_match_keys": sorted(owner_pins)},
        ],
    })
    print(f"seed={seed} activities={len(rows)} owner_pins={len(owner_pins)} date_pins={len(date_pins)}")


def write_naive(d: dict, cells: dict, out: str) -> None:
    """The obvious split: one activity per line of the cell, the first date-looking token parsed with the current year,
    initials looked up as written (MB kept as Maria), no initials left blank, type from the first keyword found."""
    os.makedirs(out, exist_ok=True)
    rows = []
    mon = {m.lower(): i + 1 for i, m in enumerate(MONTH_ABBR)}
    for a in d["accounts"]:
        for line in cells[a["id"]].split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.search(r"(\d{1,2})/(\d{1,2})", line)
            if m:
                dt = date(2026, int(m.group(1)), int(m.group(2)))
            else:
                m2 = re.search(r"(\d{1,2})(?:st|nd|rd|th)? (?:of )?([A-Z][a-z]{2})|([A-Z][a-z]{2})[a-z]* (\d{1,2})", line)
                if not m2:
                    continue
                if m2.group(1):
                    dt = date(2026, mon[m2.group(2).lower()], int(m2.group(1)))
                else:
                    dt = date(2026, mon[m2.group(3).lower()], int(m2.group(4)))
            ini = re.search(r"\b(JM|KT|DP|SC|MB)\b", line)
            owner = {u[1]: u[2] for u in USERS}.get(ini.group(1)) if ini else ""
            typ = "Call" if re.search(r"call|phoned|vm|voicemail", line) else "Email" if re.search(r"email|sent quote", line) else "Meeting"
            rows.append([a["id"], a["name"], dt.isoformat(), typ, owner, line])
    write_csv(os.path.join(out, "activities.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
