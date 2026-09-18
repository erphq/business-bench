#!/usr/bin/env python3
"""mailchimp-audience-import: three signup sources for a pottery studio become one Mailchimp audience import.

    python gen.py [--seed N]

Business: a ceramics studio collects emails at the farmers market (paper sheets typed up), through workshop
registrations, and from a website popup. The owner wants one import file for the Mailchimp audience.

Traps (each caught by a check, see task.yaml):
  * people who unsubscribed in Mailchimp signed up again on paper or in a workshop; they stay out, and the
    unsubscribed export writes their email in a different case      (checks: one row per subscriber; row count)
  * the same person appears in two or three sources with the email in different case or with spaces; one row per
    address, carrying the tags of every source they signed up through, even where they only opted in once
                                                                    (checks: row count; tags per subscriber)
  * rows that did not opt in (N, FALSE, No) and typo emails without an @ or a domain stay out
                                                                    (check: one row per subscriber)
  * tags must use the audience's existing spellings from the note, comma-separated in one cell (check: tags per subscriber)
  * birthdays arrive as "Jul 4", "4 July", "7/4", "July 4th" and must be MM/DD (check: birthday merge field)
  * the market sheet has one Name column with "LAST, First" and first-name-only entries; names come from whichever
    source has them                                                 (check: name merge fields)
"""
from __future__ import annotations
import os, re, sys
from datetime import date, datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["Email Address", "First Name", "Last Name", "Phone Number", "Birthday", "Tags"]
TAG = {"market": "Farmers Market", "workshop": "Workshop", "website": "Website"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def bday_text(m: int, d: int, style: int) -> str:
    return [f"{MONTHS[m - 1]} {d}", f"{d} {FULL[m - 1]}", f"{m}/{d}", f"{FULL[m - 1]} {ordinal(d)}", f"{m:02d}/{d:02d}"][style % 5]


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 808)
    ppl, seen_emails, seen_names = [], set(), set()
    while len(ppl) < 96:
        f, l = person(r)
        if (f, l) in seen_names:
            continue
        e = email_for(r, f, l)
        if e in seen_emails:
            continue
        seen_names.add((f, l)); seen_emails.add(e)
        m = r.randint(1, 12); dd = r.randint(1, 28)
        ppl.append({"first": f, "last": l, "email": e, "phone": phone_digits(r) if r.random() < 0.6 else "",
                    "bday": (m, dd) if r.random() < 0.65 else None, "sources": set(), "consent": {}, "unsub": False, "invalid": False})
    # source membership
    for p in ppl:
        k = r.random()
        if k < 0.42: p["sources"] = {"market"}
        elif k < 0.62: p["sources"] = {"website"}
        elif k < 0.76: p["sources"] = {"workshop"}
        elif k < 0.86: p["sources"] = {"market", "website"}
        elif k < 0.93: p["sources"] = {"market", "workshop"}
        elif k < 0.97: p["sources"] = {"workshop", "website"}
        else: p["sources"] = {"market", "workshop", "website"}
    for p in ppl:
        for s in sorted(p["sources"]):
            p["consent"][s] = r.random() < {"market": 0.84, "workshop": 0.72, "website": 0.95}[s]
    multi = [p for p in ppl if len(p["sources"]) > 1]
    # at least three multi-source people who opted in on only one of their sources
    for p in multi[:3]:
        srcs = sorted(p["sources"])
        for i, s in enumerate(srcs):
            p["consent"][s] = i == 0
    # unsubscribed people who signed up again (all opted in, so only the unsub list keeps them out)
    unsub_people = r.sample([p for p in ppl if p not in multi[:3]], 5)
    for p in unsub_people:
        p["unsub"] = True
        for s in sorted(p["sources"]):
            p["consent"][s] = True
    # typo emails on the market sheet, market-only people
    typo_people = r.sample([p for p in ppl if p["sources"] == {"market"} and not p["unsub"]], 4)
    for p, kind in zip(typo_people, ["noat", "nodot", "comma", "space"]):
        p["invalid"] = kind
        p["consent"]["market"] = True
    # birthdays only exist in workshop/website sources
    for p in ppl:
        if not ({"workshop", "website"} & p["sources"]):
            p["bday"] = None
    final = [p for p in ppl if not p["unsub"] and not p["invalid"] and any(p["consent"].values())]
    return {"ppl": ppl, "final": final, "multi_one_consent": multi[:3], "unsub": unsub_people, "typos": typo_people}


def typo(e: str, kind: str) -> str:
    local, dom = e.split("@")
    return {"noat": f"{local}{dom}", "nodot": f"{local}@{dom.split('.')[0]}", "comma": f"{local}@{dom.replace('.', ',')}",
            "space": f"{local} at {dom}"}[kind]


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed * 1000 + 809)
    ppl = d["ppl"]

    # ---- farmers market sheets (typed up) ----
    market = []
    last_comma = r.sample([p for p in ppl if "market" in p["sources"]], 5)
    first_only = r.sample([p for p in ppl if "market" in p["sources"] and len(p["sources"]) > 1 and p not in last_comma], 3)
    for p in ppl:
        if "market" not in p["sources"]:
            continue
        name = f"{p['first']} {p['last']}"
        if p in last_comma: name = f"{p['last'].upper()}, {p['first']}"
        elif p in first_only: name = p["first"]
        elif r.random() < 0.15: name = name.lower()
        email = typo(p["email"], p["invalid"]) if p["invalid"] else p["email"]
        if len(p["sources"]) > 1 or p["unsub"]:
            email = email_case_noise(r, email)
        day = date(2026, 8, r.choice([1, 8, 15, 22, 29]))
        market.append([day.strftime("%m/%d/%Y"), name, email, "Y" if p["consent"]["market"] else "N", r.choice(["", "", "loves the blue glaze", "asked about kids class", ""])])
    market.sort(key=lambda x: x[0])
    write_csv(os.path.join(ws, "farmers_market_signups_aug.csv"), ["Date", "Name", "Email", "OK to email? (Y/N)", "Notes"], market)

    # ---- workshop registrations ----
    wrows = []
    for p in ppl:
        if "workshop" not in p["sources"]:
            continue
        email = email_case_noise(r, p["email"]) if (len(p["sources"]) > 1 or p["unsub"]) and r.random() < 0.6 else p["email"]
        b = bday_text(*p["bday"], r.randrange(4)) if p["bday"] else ""
        wrows.append([p["first"], p["last"], email, phone_variant(p["phone"], r.randrange(7)) if p["phone"] else "", b,
                      r.choice(["Wheel Throwing 101", "Glaze Lab", "Hand-Building Weekend"]), bool(p["consent"]["workshop"])])
    write_xlsx(os.path.join(ws, "workshop_registrations_summer.xlsx"), {"Registrations": {
        "merged_title": "Summer workshop registrations", "header": ["First", "Last", "E-mail", "Phone", "Birthday", "Workshop", "Newsletter opt-in"],
        "rows": wrows, "widths": {"C": 32, "F": 24}}}, creator="Studio")

    # ---- website popup export ----
    web = []
    for p in ppl:
        if "website" not in p["sources"]:
            continue
        email = email_case_noise(r, p["email"]) if (len(p["sources"]) > 1 or p["unsub"]) and r.random() < 0.6 else p["email"]
        when = datetime(2026, 6, 1, 9, 0) + timedelta(minutes=r.randint(0, 60 * 24 * 90))
        web.append([when.strftime("%Y-%m-%d %H:%M"), email, p["first"], p["last"], f"{p['bday'][0]:02d}/{p['bday'][1]:02d}" if p["bday"] else "",
                    "Yes" if p["consent"]["website"] else "No"])
    web.sort(key=lambda x: x[0])
    write_csv(os.path.join(ws, "website_popup_form_export.csv"), ["Submitted On", "Email Address", "First Name", "Last Name", "Birthday (MM/DD)", "Consent"],
              web, bom=True)

    # ---- mailchimp unsubscribed export (their emails, lower case; plus others never on these sheets) ----
    unsub_rows = []
    for p in d["unsub"]:
        unsub_rows.append([p["email"].lower(), p["first"], p["last"], "2026-0{}-{:02d} 14:22:10".format(r.randint(3, 7), r.randint(1, 28)), "Spring kiln sale"])
    while len(unsub_rows) < 22:
        f, l = person(r)
        e = email_for(r, f, l)
        if any(e == p["email"] for p in ppl):
            continue
        unsub_rows.append([e, f, l, "2026-0{}-{:02d} 09:{:02d}:00".format(r.randint(1, 8), r.randint(1, 28), r.randint(0, 59)), r.choice(["Spring kiln sale", "Holiday market", ""])])
    r.shuffle(unsub_rows)
    write_csv(os.path.join(ws, "mailchimp_unsubscribed_2026-09-01.csv"), ["Email Address", "First Name", "Last Name", "UNSUB_TIME", "UNSUB_CAMPAIGN_TITLE"], unsub_rows)

    write_csv(os.path.join(ws, "mailchimp_import_template.csv"), TEMPLATE, [])

    write_text(os.path.join(ws, "note_from_ines.txt"), """Mailchimp import - please read

Everyone from this summer goes into one file for the Umber Ceramics audience. Use Mailchimp's template columns.

- Only people who said yes to email (Y on the market sheet, the opt-in box ticked on workshop registrations, Consent
  Yes on the website form). If someone said yes anywhere, they're in.
- Anyone on the unsubscribed export stays out, even if they signed up again this summer. Mailchimp won't take them
  back and I don't want the complaint.
- One row per email address. People signed up in more than one place and typed their email differently.
- Skip anything that isn't a real email address (the market sheet has a few smudged ones).
- Tags: tag everyone with every place they signed up, even the places they didn't tick yes. Use the tags we already
  have in Mailchimp, spelled exactly: Farmers Market, Workshop, Website. Several tags go in the one Tags cell
  separated by commas.
- First Name / Last Name split properly (the market sheet only has one name box, and some people wrote LAST, First).
- Birthday is Mailchimp's birthday field: MM/DD, no year.
- Phone as the person gave it is fine.

Ines
""")

    out = []
    for p in sorted(d["final"], key=lambda p: p["email"]):
        tags = ",".join(sorted(TAG[s] for s in p["sources"]))
        out.append([p["email"], p["first"], p["last"], fmt_phone(p["phone"]) if p["phone"] and "workshop" in p["sources"] else "",
                    f"{p['bday'][0]:02d}/{p['bday'][1]:02d}" if p["bday"] else "", tags])
    for dd in (ref, sol):
        write_csv(os.path.join(dd, "mailchimp_import.csv"), TEMPLATE, out)

    final = d["final"]
    bday_trap = [p["email"] for p in final if p["bday"] and "workshop" in p["sources"] and "website" not in p["sources"]][:8]
    lc = [p for p in ppl if "market" in p["sources"]]
    write_task_yaml(HERE, {
        "id": "mailchimp-audience-import", "track": "desk", "category": "reformatting",
        "title": "Summer signups into one Mailchimp audience import",
        "ask": "Put everyone who signed up with us this summer into one Mailchimp import file using their template. Ines's note has the rules. Save it as mailchimp_import.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"{len(d['unsub'])} people on the unsubscribed export signed up again and opted in; the export writes their email in lower case while the sheets use other casing, so an exact-match filter misses them (checks: one row per subscriber; row count)",
            "people appear in two or three sources with the email upper-cased, capitalised or padded with spaces; one row per address (checks: row count; tags per subscriber)",
            "three multi-source people opted in on only one of their sources; they are in, and tagged with every source (check: tags per subscriber)",
            "rows with N, an unticked opt-in or Consent No stay out unless the person said yes elsewhere; four market-sheet emails are smudged (no @, no dot, comma for dot, ' at ') and stay out (check: one row per subscriber)",
            "tags must be the audience's spellings Farmers Market / Workshop / Website, several in one comma-separated cell (check: tags per subscriber)",
            "workshop birthdays are free text ('Jul 4', '4 July', '7/4', 'July 4th') and must become MM/DD (check: birthday merge field)",
            "the market sheet has one Name column with five 'LAST, First' entries and three first-name-only entries whose last name is on another source (check: name merge fields)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Mailchimp template columns in order", "path": "mailchimp_import.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one row per subscriber", "path": "mailchimp_import.csv", "column": "Email Address", "ref": "mailchimp_import.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "mailchimp_import.csv", "equals_ref": "mailchimp_import.csv"},
            {"type": "custom", "name": "tags per subscriber", "module": "check.py"},
            {"type": "csv_values_match", "name": "birthday merge field", "path": "mailchimp_import.csv", "ref": "mailchimp_import.csv", "key": "Email Address",
             "columns": ["Birthday"], "normalize": ["strip"], "min_accuracy": 1.0, "must_match_keys": bday_trap},
            {"type": "csv_values_match", "name": "name merge fields", "path": "mailchimp_import.csv", "ref": "mailchimp_import.csv", "key": "Email Address",
             "columns": ["First Name", "Last Name"], "min_accuracy": 1.0,
             "must_match_keys": [p["email"] for p in final if p["email"] in {x["email"] for x in lc} and (p["last"].upper() + ", " + p["first"]) in {m[1] for m in market}]
                                + [p["email"] for p in final if p["first"] in {m[1] for m in market} and "market" in p["sources"]]},
        ],
    })


def fmt_phone(d10: str) -> str:
    return f"({d10[:3]}) {d10[3:6]}-{d10[6:]}"


if __name__ == "__main__":
    emit(argparse_seed())
