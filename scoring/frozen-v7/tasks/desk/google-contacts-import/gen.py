#!/usr/bin/env python3
"""google-contacts-import: a landscaper's hand-kept phone list turned into a Google Contacts import CSV.

    python gen.py [--seed N]

Business: Cedar & Pine Landscaping is moving the office to Google Workspace. The phone list is a workbook the
office manager has typed into for years: section heading rows instead of a type column, names written
"Last, First" or with a bracketed remark, several numbers typed into one cell, and wrapped lines.

Traps (each caught by a check, see task.yaml):
  * names come as "First Last", "Last, First", "LAST, FIRST M.", "First M. Last", with a bracketed remark, or
    as "Company - First Last" for suppliers                                   (checks: one contact per person; first and middle names; organization)
  * the Phone cell holds one to three numbers with labels before or after (c:, cell, h, home, w, office, fax)
    or none; each lands in its own Phone slot with Google's label, unlabeled numbers are Mobile  (check: phones typed)
  * bracketed remarks in names and non-number text in the Phone cell belong in Notes with the Notes column
                                                                             (check: notes carried and names clean)
  * three wrapped lines have a blank Name and carry another number or a note for the contact above
                                                                             (checks: row count; phones typed; notes carried and names clean)
  * section heading rows (CLIENTS, PAST CLIENTS, SUPPLIERS, SUBS) decide the label; they are not contacts
                                                                             (checks: labels; row count)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["First Name", "Middle Name", "Last Name", "Organization Name", "E-mail 1 - Label", "E-mail 1 - Value",
            "Phone 1 - Label", "Phone 1 - Value", "Phone 2 - Label", "Phone 2 - Value", "Phone 3 - Label", "Phone 3 - Value",
            "Notes", "Labels"]
SECTIONS = [("CLIENTS - CURRENT", "Clients", 24), ("PAST CLIENTS", "Former Clients", 6), ("SUPPLIERS", "Suppliers", 6),
            ("SUBS", "Subcontractors", 5)]
SUPPLIERS = ["Quarry Road Nursery", "Front Range Stone Supply", "Mile High Irrigation", "Boulder Mulch & Soil", "Summit Equipment Rental",
             "Aspen Sod Farms", "Peak Fence Co", "Canyon Tree Service", "Flatirons Concrete", "Ridgeline Electric", "Clear Creek Hardscapes"]
REMARKS = ["gate code 4412", "dog in back yard", "use side gate", "key under mat", "HOA approval needed", "lives out of state in winter"]
TRAILERS = ["don't call before 9am", "text first", "ask for Jim", "after 3pm only"]
LABEL_WORDS = {"Mobile": ["c", "cell", "mobile", "C"], "Home": ["h", "home", "H"], "Work": ["w", "work", "office", "o"], "Work Fax": ["fax"]}
NOTES_COL = ["Weekly mow Apr-Oct", "Spring cleanup only", "Sprinkler blowout in Oct", "Snow removal contract", "Pays by check",
             "Installed patio 2024", "Aeration + overseed", "", "", "", "", ""]
TRADE_NOTES = ["Net 30", "Bills monthly", "Account #CP-2291", "COD only", "Delivers Tue/Thu", "Insurance cert on file", "", ""]


def fmt_num(r, d: str) -> str:
    return phone_variant(d, r.choice([0, 1, 3, 3, 4, 6]))


def build(seed: int) -> dict:
    r = rng(seed)
    contacts = []
    lasts = set()
    used_digits = set()

    def new_digits():
        while True:
            d = phone_digits(r)
            if d not in used_digits:
                used_digits.add(d); return d
    for heading, label, n in SECTIONS:
        for k in range(n):
            while True:
                f, l = person(r)
                if l not in lasts:
                    lasts.add(l); break
            c = {"first": f, "last": l, "middle": "", "org": "", "label": label, "section": heading, "tags": set(),
                 "notes": [], "phones": []}
            if label in ("Suppliers", "Subcontractors"):
                c["org"] = SUPPLIERS[len([x for x in contacts if x["org"]]) % len(SUPPLIERS)]
            contacts.append(c)
    clients = [c for c in contacts if c["label"] in ("Clients", "Former Clients")]
    trade = [c for c in contacts if c["org"]]
    # name styles for people without an org
    styles = ["plain"] * 12 + ["comma"] * 6 + ["comma_caps"] * 2 + ["middle"] * 4 + ["comma_middle"] * 2 + ["remark"] * 4
    r.shuffle(styles)
    for c, st in zip(clients, styles):
        c["name_style"] = st
        if "middle" in st:
            c["middle"] = r.choice("ABDEJKLMRST") + "."
        if st != "plain":
            c["tags"].add("name")
    for c in clients[len(styles):]:
        c["name_style"] = "plain"
    remark_people = [c for c in clients if c["name_style"] == "remark"]
    for c, rem in zip(remark_people, r.sample(REMARKS, len(remark_people))):
        c["remark"] = rem; c["notes"].append(rem); c["tags"].add("notes")
    for c in trade:
        c["name_style"] = r.choice(["dash", "colon", "dash"])
        c["tags"].add("org")
    # phones: 1 to 3 numbers
    for c in contacts:
        k = r.random()
        if c["org"]:
            labs = ["Work", "Mobile"] if k < 0.5 else ["Mobile"] if k < 0.8 else ["Work", "Work Fax"]
        else:
            labs = ["Mobile"] if k < 0.4 else ["Mobile", "Home"] if k < 0.75 else ["Home", "Mobile", "Work"] if k < 0.88 else ["Home"]
        c["phones"] = [(lab, new_digits()) for lab in labs]
        if len(labs) > 1 or labs[0] != "Mobile":
            c["tags"].add("phones")
    # emails
    for c in contacts:
        c["email"] = ""
        if r.random() < 0.6:
            dom = None
            if c["org"]:
                dom = c["org"].lower().replace(" & ", "").replace(" ", "") + ".com"
            c["email"] = email_for(r, c["first"], c["last"], dom)
    # notes column
    for c in contacts:
        c["note_col"] = r.choice(TRADE_NOTES if c["org"] else NOTES_COL)
        if c["note_col"]:
            c["notes"].append(c["note_col"])
    # trailing remarks inside the phone cell
    for c in r.sample([c for c in clients if "remark" not in c], 3):
        t = r.choice(TRAILERS)
        c["trailer"] = t; c["notes"].append(t); c["tags"].add("notes")
    # wrapped lines: two add a number, one adds a note
    wrap = r.sample([c for c in contacts if len(c["phones"]) == 1 and "trailer" not in c], 3)
    for c in wrap[:2]:
        c["wrap_phone"] = ("Work", new_digits()); c["phones"].append(c["wrap_phone"]); c["tags"].update({"phones", "wrap"})
    wrap[2]["wrap_note"] = r.choice(["prefers text", "renewal due Nov", "wife Karen also on account"])
    wrap[2]["notes"].append(wrap[2]["wrap_note"]); wrap[2]["tags"].update({"notes", "wrap"})
    for c in contacts:
        if c["label"] != "Clients":
            c["tags"].add("label")
    return {"contacts": contacts}


def render_name(c):
    f, m, l = c["first"], c["middle"], c["last"]
    st = c["name_style"]
    if st == "plain":
        return f"{f} {l}"
    if st == "comma":
        return f"{l}, {f}"
    if st == "comma_caps":
        return f"{l}, {f}".upper()
    if st == "middle":
        return f"{f} {m} {l}"
    if st == "comma_middle":
        return f"{l}, {f} {m}"
    if st == "remark":
        return f"{f} {l} ({c['remark']})"
    if st == "dash":
        return f"{c['org']} - {f} {l}"
    return f"{c['org']}: {f} {l}"


def render_phones(r, c):
    phones = [p for p in c["phones"] if p != c.get("wrap_phone")]
    if len(phones) == 1 and phones[0][0] == "Mobile" and r.random() < 0.6:
        s = fmt_num(r, phones[0][1])
    else:
        parts = []
        after = r.random() < 0.35
        for lab, d in phones:
            word = r.choice(LABEL_WORDS[lab])
            num = fmt_num(r, d)
            if after:
                parts.append(f"{num} ({word})")
            else:
                parts.append(f"{word}: {num}" if r.random() < 0.5 else f"{word} {num}")
        s = r.choice([" / ", ", ", "; ", "\n"]).join(parts)
    if c.get("trailer"):
        s += f" - {c['trailer']}"
    return s


def emit(seed: int) -> None:
    d = build(seed)
    contacts = d["contacts"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 5)
    rows = []
    for heading, label, _ in SECTIONS:
        rows.append([heading, "", "", ""])
        for c in [c for c in contacts if c["section"] == heading]:
            rows.append([render_name(c), render_phones(r, c), c["email"], c["note_col"]])
            if c.get("wrap_phone"):
                lab, dig = c["wrap_phone"]
                rows.append(["", f"also {r.choice(LABEL_WORDS[lab])} {fmt_num(r, dig)}", "", ""])
            if c.get("wrap_note"):
                rows.append(["", "", "", c["wrap_note"]])
        rows.append(["", "", "", ""])
    write_xlsx(os.path.join(ws, "phone_list.xlsx"), {"Phone list": {
        "merged_title": "Cedar & Pine Landscaping - PHONE LIST (office copy, updated Aug 2026)",
        "header": ["Name", "Phone", "Email", "Notes"], "rows": rows, "widths": {"A": 44, "B": 52, "C": 34, "D": 30}}},
        creator="Cedar & Pine Office")
    write_csv(os.path.join(ws, "google_contacts_template.csv"), TEMPLATE, [])
    write_text(os.path.join(ws, "notes_for_google_import.txt"), (
        "From Beth (office), for whoever moves the phone list into Google Contacts\n"
        "\n"
        "I downloaded Google's CSV layout (google_contacts_template.csv), so please fill that in exactly, one row per person\n"
        "on the phone list. Some things about how I kept the list:\n"
        "\n"
        "- Names: I typed them however I felt like that day. Put first, middle and last in their own columns. For\n"
        "  suppliers and subs I wrote the company in front of the person; the company goes in Organization Name.\n"
        "- Anything in brackets after a name is a note to myself, not part of the name. Put it in Notes.\n"
        "- Phone: I often typed two or three numbers in one cell. Each number needs its own Phone slot (Phone 1,\n"
        "  Phone 2, Phone 3, in the order I wrote them) with Google's label: Mobile, Home, Work or Work Fax.\n"
        "  c / cell / mobile is Mobile, h / home is Home, w / work / o / office is Work, fax is Work Fax. A number with\n"
        "  no label is a cell phone. If I wrote anything in the phone cell that is not a number (like \"text first\"),\n"
        "  that goes in Notes too.\n"
        "- Where the Name cell is empty, that line is just the person above it running over onto a second line.\n"
        "- Notes: keep what is in my Notes column, plus the bits above. Separate them with a semicolon.\n"
        "- Labels: the heading rows tell you what someone is. Clients under CLIENTS - CURRENT get the label Clients,\n"
        "  PAST CLIENTS get Former Clients, SUPPLIERS get Suppliers and SUBS get Subcontractors.\n"
        "- E-mail 1 - Label is Home for clients and past clients, Work for suppliers and subs.\n"))
    out = sorted(contacts, key=lambda c: c["last"])
    rows = []
    for c in out:
        ph = c["phones"] + [("", "")] * (3 - len(c["phones"]))
        cells = []
        for lab, dig in ph:
            cells += [lab, f"({dig[:3]}) {dig[3:6]}-{dig[6:]}" if dig else ""]
        email_label = "" if not c["email"] else ("Work" if c["org"] else "Home")
        rows.append([c["first"], c["middle"], c["last"], c["org"], email_label, c["email"]] + cells + ["; ".join(c["notes"]), c["label"]])
    write_csv(os.path.join(ref, "google_contacts.csv"), TEMPLATE, rows)
    write_csv(os.path.join(sol, "google_contacts.csv"), TEMPLATE, rows)
    write_json(os.path.join(ref, "truth.json"), {
        "phones": {c["last"]: [[lab, dig] for lab, dig in c["phones"]] for c in out},
        "notes": {c["last"]: c["notes"] for c in out},
        "must_phones": sorted(c["last"] for c in out if "phones" in c["tags"]),
        "must_notes": sorted(c["last"] for c in out if "notes" in c["tags"])})

    def keys(tag):
        return sorted(c["last"] for c in out if tag in c["tags"])
    write_task_yaml(HERE, {
        "id": "google-contacts-import", "track": "desk", "category": "reformatting",
        "title": "Move the office phone list into Google Contacts",
        "ask": ("We're switching to Google Workspace and I want our phone list in Google Contacts. Beth left notes on how she kept the "
                "list, and Google's CSV layout is in the folder. Save the import file as google_contacts.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "names are typed as First Last, Last, First, LAST, FIRST M., First M. Last, with a bracketed remark, or as Company - First Last and Company: First Last; splitting on the first space puts surnames in First Name and companies in the name (checks: one contact per person; first and middle names; organization)",
            "the Phone cell holds one to three numbers with labels before or after the number (c:, cell, h, home, w, o, office, fax) or no label at all; each number takes its own slot with Google's Mobile / Home / Work / Work Fax label and an unlabeled number is Mobile (check: phones typed)",
            "four names carry a bracketed remark (gate code, dog in yard) and three phone cells end with an instruction (text first, don't call before 9am); both belong in Notes alongside the Notes column, never in the name (check: notes carried and names clean)",
            "three wrapped lines have a blank Name: two add another number and one adds a note to the contact above; importing them as contacts or dropping them loses data (checks: row count; phones typed; notes carried and names clean)",
            "there is no type column; heading rows (CLIENTS - CURRENT, PAST CLIENTS, SUPPLIERS, SUBS) decide the label and are not contacts themselves (checks: labels; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Google template columns, exact order", "path": "google_contacts.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one contact per person", "path": "google_contacts.csv", "column": "Last Name",
             "ref": "google_contacts.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "google_contacts.csv", "equals_ref": "google_contacts.csv"},
            {"type": "csv_values_match", "name": "first and middle names", "path": "google_contacts.csv", "ref": "google_contacts.csv",
             "key": "Last Name", "columns": ["First Name", "Middle Name"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": keys("name")},
            {"type": "csv_values_match", "name": "organization", "path": "google_contacts.csv", "ref": "google_contacts.csv",
             "key": "Last Name", "columns": ["Organization Name"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": keys("org")},
            {"type": "csv_values_match", "name": "labels", "path": "google_contacts.csv", "ref": "google_contacts.csv",
             "key": "Last Name", "columns": ["Labels"], "min_accuracy": 1.0, "must_match_keys": keys("label")},
            {"type": "custom", "name": "phones typed; notes carried and names clean", "module": "check.py"},
        ],
    })
    print(f"seed={seed}: {len(contacts)} contacts; " + ", ".join(f"{t}={len(keys(t))}" for t in ("name", "org", "phones", "notes", "wrap", "label")))


if __name__ == "__main__":
    emit(argparse_seed())
