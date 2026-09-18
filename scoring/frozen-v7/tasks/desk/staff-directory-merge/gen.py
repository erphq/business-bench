#!/usr/bin/env python3
"""staff-directory-merge: the HR export and the IT (Google Workspace) user list into one staff directory.

    python gen.py [--seed N] [--naive DIR]

Business: a physiotherapy clinic group with about forty staff. HR is the source of truth for who works here,
their title and department; IT has the real mailbox and the desk extension. The website directory uses a third
set of department names.

Traps (each caught by a check, see task.yaml):
  * department names differ in HR, IT and on the website; the note maps HR's to the website's,
    and IT files aquatic therapists under Physio                          (check: department per person)
  * terminated staff whose Google accounts are still active                 (checks: people in the directory; row count)
  * preferred names ("Bob" for Robert) in HR; IT shows legal or preferred    (check: name as people go by)
  * shared mailboxes and a contractor in IT only                             (check: people in the directory)
  * a married name change: HR's work email is stale, the employee id joins   (checks: people in the directory; name)
  * a rehire with a terminated old HR record under a different employee id  (check: row count)
  * three IT accounts have no employee id and must be joined on email       (check: title and extension)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

DOMAIN = "riverbendphysio.com"
# HR department, IT department, website department, titles, headcount
DEPTS = [
    ("100 - Clinical PT", "Physio", "Physical Therapy", ["Physical Therapist", "PT Assistant", "Rehab Aide"], 13),
    ("105 - Aquatic Therapy", "Physio", "Aquatic Therapy", ["Aquatic Therapist", "Aquatic Therapy Aide"], 4),
    ("110 - Clinical OT", "OT", "Occupational Therapy", ["Occupational Therapist", "COTA"], 6),
    ("200 - Front Office", "Reception", "Patient Services", ["Patient Coordinator", "Front Desk Lead"], 7),
    ("300 - Billing & Insurance", "Billing", "Billing", ["Billing Specialist", "Insurance Verifier"], 5),
    ("400 - Management", "Admin", "Leadership", ["Clinic Director", "Operations Manager", "HR & Payroll Manager"], 3),
]
NICK = {"Robert": "Bob", "William": "Bill", "Elizabeth": "Beth", "Jennifer": "Jen", "Michael": "Mike",
        "Christopher": "Chris", "Patricia": "Trish", "Margaret": "Maggie", "Joseph": "Joe", "Thomas": "Tom",
        "Daniel": "Dan", "Kimberly": "Kim", "Rebecca": "Becca", "Dmitri": "Dima", "Hiroshi": "Hiro", "Nicholas": "Nick"}


def build(seed: int) -> dict:
    r = rng(seed)
    total = sum(dp[4] for dp in DEPTS) + 6       # + terminated
    nick_first = r.sample(sorted(NICK), 7)
    names = []
    seen = set()
    for fn in nick_first:
        ln = r.choice(LAST)
        names.append((fn, ln)); seen.add((fn, ln))
    for fn, ln in people(r, total * 2):
        if len(names) >= total:
            break
        if (fn, ln) in seen or fn in NICK or any(x[1] == ln for x in names):
            continue
        names.append((fn, ln)); seen.add((fn, ln))
    r.shuffle(names)
    staff = []
    emp = 1004
    for dept in DEPTS:
        for k in range(dept[4]):
            fn, ln = names.pop()
            emp += r.randint(1, 9)
            title = dept[3][0] if k == 0 else r.choice(dept[3])
            if dept[0].startswith("400"):
                title = dept[3][k]
            staff.append({"id": str(emp), "first": fn, "last": ln, "pref": NICK.get(fn, "") if fn in NICK else "",
                          "dept": dept, "title": title, "status": "Active", "hire": date(2015, 1, 5) + timedelta(days=r.randint(0, 3800)),
                          "term": None, "ext": str(200 + len(staff) * 3 + r.randint(0, 2))})
    # six terminated
    for k in range(6):
        fn, ln = names.pop()
        emp += r.randint(1, 9)
        dept = r.choice(DEPTS[:5])
        hire = date(2016, 3, 1) + timedelta(days=r.randint(0, 3000))
        staff.append({"id": str(emp), "first": fn, "last": ln, "pref": NICK.get(fn, ""), "dept": dept,
                      "title": r.choice(dept[3]), "status": "Terminated", "hire": hire,
                      "term": date(2026, 1, 10) + timedelta(days=r.randint(0, 220)), "ext": str(600 + k)})
    r.shuffle(staff)
    active = [s for s in staff if s["status"] == "Active"]
    for s in r.sample(active, 2):
        s["status"] = "On Leave"
    # not every nickname-able person uses a nickname; keep five preferred names
    with_pref = [s for s in active if s["pref"]]
    for s in with_pref[5:]:
        s["pref"] = ""
    # one married name change
    changed = r.choice([s for s in active if not s["pref"]])
    changed["old_last"] = changed["last"]
    changed["last"] = r.choice([x for x in LAST if x not in {s["last"] for s in staff}])
    # one rehire: an old terminated record for the same person
    rehire = r.choice([s for s in active if s is not changed and not s["pref"]])
    old = dict(rehire); old.update(id=str(int(rehire["id"]) - 700 + r.randint(0, 50)), status="Terminated",
                                   hire=date(2014, 6, 2), term=date(2019, 8, 30), title=r.choice(rehire["dept"][3]), rehire_old=True)
    rehire["hire"] = date(2024, 2, 12)
    staff.append(old)
    # employee numbers follow hire order, as HR systems issue them
    num = 1001
    for s in sorted(staff, key=lambda z: (z["hire"], z["last"])):
        num += r.randint(1, 6)
        s["id"] = str(num)

    def email_of(s, use_pref):
        fn = (s["pref"] if (use_pref and s["pref"]) else s["first"]).lower()
        return f"{fn}.{s['last'].lower()}@{DOMAIN}"

    for s in staff:
        s["it_uses_pref"] = bool(s["pref"]) and r.random() < 0.5
        s["email"] = email_of(s, s["it_uses_pref"])
    # HR work email: mostly the same address, differently cased; stale for the name change
    for s in staff:
        s["hr_email"] = s["email"].upper() if r.random() < 0.25 else s["email"]
    changed["hr_email"] = f"{(changed['pref'] or changed['first']).lower()}.{changed['old_last'].lower()}@{DOMAIN}"
    old["hr_email"] = rehire["email"]
    # IT user list
    it = []
    no_id = r.sample([s for s in staff if s["status"] != "Terminated" and s is not changed and s is not rehire], 3)
    for s in staff:
        if s.get("rehire_old"):
            continue
        if s["status"] == "Terminated":
            continue
        it.append({"email": s["email"], "first": s["pref"] if s["it_uses_pref"] else s["first"], "last": s["last"],
                   "dept": s["dept"][1], "id": "" if s in no_id else s["id"], "ext": s["ext"], "status": "Active",
                   "ou": "/Staff/" + s["dept"][1]})
    term = [s for s in staff if s["status"] == "Terminated" and not s.get("rehire_old")]
    for i, s in enumerate(term):
        if i < 2:
            it.append({"email": s["email"], "first": s["first"], "last": s["last"], "dept": s["dept"][1], "id": s["id"],
                       "ext": s["ext"], "status": "Active", "ou": "/Staff/" + s["dept"][1]})
        elif i < 5:
            it.append({"email": s["email"], "first": s["first"], "last": s["last"], "dept": s["dept"][1], "id": s["id"],
                       "ext": "", "status": "Suspended", "ou": "/Former staff"})
    for box, fn, ln, ext in [("frontdesk", "Front", "Desk", "100"), ("billing", "Billing", "Team", "300"),
                             ("fax", "Fax", "Inbox", ""), ("scheduling", "Scheduling", "Riverbend", "101")]:
        it.append({"email": f"{box}@{DOMAIN}", "first": fn, "last": ln, "dept": "", "id": "", "ext": ext, "status": "Active",
                   "ou": "/Shared mailboxes"})
    cf, cl = r.choice([p for p in people(r, 10) if p[1] not in {s["last"] for s in staff}])
    it.append({"email": f"{cf.lower()}.{cl.lower()}@{DOMAIN}", "first": cf, "last": cl, "dept": "IT", "id": "", "ext": "",
               "status": "Active", "ou": "/Contractors"})
    r.shuffle(it)
    directory = []
    for s in staff:
        if s["status"] == "Terminated":
            continue
        directory.append({"name": f"{s['pref'] or s['first']} {s['last']}", "email": s["email"], "department": s["dept"][2],
                          "title": s["title"], "extension": s["ext"]})
    directory.sort(key=lambda z: z["name"].split()[-1] + " " + z["name"])
    return {"staff": staff, "it": it, "directory": directory, "changed": changed, "rehire": rehire, "no_id": no_id,
            "term_active": term[:2]}


def acceptable(d: dict) -> bool:
    prefs = [s for s in d["staff"] if s["pref"] and s["status"] != "Terminated"]
    it_legal = [s for s in prefs if not s["it_uses_pref"]]
    aquatic = [s for s in d["staff"] if s["dept"][0].startswith("105") and s["status"] != "Terminated"]
    emails = [x["email"] for x in d["it"]]
    return len(prefs) >= 4 and len(it_legal) >= 2 and len(aquatic) == 4 and len(set(emails)) == len(emails)


HEADER = ["name", "email", "department", "title", "extension"]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        # every active IT account, IT's own names and departments
        os.makedirs(naive_dir, exist_ok=True)
        hr_by_email = {s["hr_email"].lower(): s for s in d["staff"]}
        rows = []
        for u in d["it"]:
            if u["status"] != "Active":
                continue
            s = hr_by_email.get(u["email"])
            rows.append([f"{u['first']} {u['last']}", u["email"], u["dept"], s["title"] if s else "", u["ext"]])
        write_csv(os.path.join(naive_dir, "directory.csv"), HEADER, rows)
        return
    ws, ref, sol = task_dirs(HERE)
    hr_rows = []
    for s in sorted(d["staff"], key=lambda z: int(z["id"])):
        hr_rows.append([s["id"], s["first"], s["last"], s["pref"], s["title"], s["dept"][0], "Riverbend - Eugene"
                        if int(s["id"]) % 3 else "Riverbend - Springfield", s["status"], s["hire"].strftime("%m/%d/%Y"),
                        s["term"].strftime("%m/%d/%Y") if s["term"] else "", s["hr_email"]])
    write_csv(os.path.join(ws, "hr_employee_export_2026-09-10.csv"),
              ["Employee #", "Legal First Name", "Legal Last Name", "Preferred Name", "Job Title", "Department", "Location",
               "Employment Status", "Hire Date", "Termination Date", "Work Email"], hr_rows, bom=True)
    write_csv(os.path.join(ws, "google_workspace_users.csv"),
              ["Email Address [Required]", "First Name [Required]", "Last Name [Required]", "Status [READ ONLY]",
               "Org Unit Path [Required]", "Employee ID", "Department", "Work Phone Extension"],
              [[u["email"], u["first"], u["last"], u["status"], u["ou"], u["id"], u["dept"], u["ext"]] for u in d["it"]])
    mapping = "\n".join(f"  {hr:<28} -> {web}" for hr, _, web, _, _ in DEPTS)
    write_text(os.path.join(ws, "note_from_colleen.txt"), (
        "Website staff directory - please build the list\n\n"
        "We're putting a staff directory on the new website. HR (BambooHR) is the only list of who actually works "
        "here, what their job title is and which department they're in. IT's Google list has everyone's real "
        "email address and desk extension, but it also has a lot that isn't a person, and IT's departments haven't "
        "been touched in years.\n\n"
        "Rules:\n"
        "- Only current staff. Terminated people come off even if IT hasn't shut their account yet. People on "
        "leave stay on.\n"
        "- Use the name people go by: their preferred first name if HR has one, otherwise their legal first name, "
        "plus last name.\n"
        "- Email is their Google address, not whatever HR has on file.\n"
        "- The website uses these department names (from HR's department):\n"
        f"{mapping}\n\n"
        "Send it back as directory.csv with name, email, department, title and extension.\n\n"
        "Colleen\n"))

    rows = [[x["name"], x["email"], x["department"], x["title"], x["extension"]] for x in d["directory"]]
    write_csv(os.path.join(ref, "directory.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "directory.csv"), HEADER, rows)
    aquatic = [s["email"] for s in d["staff"] if s["dept"][0].startswith("105") and s["status"] != "Terminated"]
    prefs = [s["email"] for s in d["staff"] if s["pref"] and s["status"] != "Terminated"]
    write_json(os.path.join(ref, "notes.json"), {"changed": d["changed"]["email"], "rehire": d["rehire"]["email"],
                                                  "no_id": [s["email"] for s in d["no_id"]],
                                                  "terminated_active_in_it": [s["email"] for s in d["term_active"]],
                                                  "aquatic": aquatic, "preferred": prefs})
    write_task_yaml(HERE, {
        "id": "staff-directory-merge", "track": "desk", "category": "spreadsheet",
        "title": "One staff directory from HR and IT",
        "ask": ("Colleen needs the staff directory for the new website, put together from the HR export and IT's "
                "Google user list. Her note has the rules - save it as directory.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "HR departments are cost-centre names ('105 - Aquatic Therapy'), IT's are old short names and the website "
            "wants a third set from the note; IT files the four aquatic therapists under Physio, so mapping from "
            "IT's field makes them Physical Therapy (check: department per person)",
            "two terminated staff still have active Google accounts and three more are suspended; the directory "
            "follows HR's status (checks: people in the directory; row count)",
            "five people have a preferred first name in HR ('Bob' for Robert); IT shows the legal name for some of "
            "them, so IT's first name column is wrong for the website (check: name as people go by)",
            "IT's list has four shared mailboxes (frontdesk@, billing@, fax@, scheduling@) and a contractor who is "
            "not in HR (check: people in the directory)",
            "one person changed their last name; HR's work email still has the old name, so an email join misses "
            "them and the Employee ID is the only link (checks: people in the directory; name as people go by)",
            "one person was rehired and has an old terminated HR record under a different employee number with the "
            "same email; joining HR to IT on email picks up both records and the old job title "
            "(checks: row count; title and extension)",
            "three Google accounts have no Employee ID, and a quarter of HR's work emails are upper-case; those "
            "people join on the email address, case-insensitively (check: title and extension)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "directory.csv", "columns": HEADER},
            {"type": "csv_set_equal", "name": "people in the directory", "path": "directory.csv", "column": "email",
             "ref": "directory.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "directory.csv", "equals_ref": "directory.csv"},
            {"type": "csv_values_match", "name": "department per person", "path": "directory.csv", "ref": "directory.csv",
             "key": "email", "columns": ["department"], "min_accuracy": 1.0, "must_match_keys": aquatic},
            {"type": "csv_values_match", "name": "name as people go by", "path": "directory.csv", "ref": "directory.csv",
             "key": "email", "columns": ["name"], "min_accuracy": 1.0, "must_match_keys": prefs + [d["changed"]["email"]]},
            {"type": "csv_values_match", "name": "title and extension", "path": "directory.csv", "ref": "directory.csv",
             "key": "email", "columns": ["title", "extension"], "min_accuracy": 1.0,
             "must_match_keys": [s["email"] for s in d["no_id"]]},
        ],
    })
    print(f"seed={seed} directory={len(rows)} it={len(d['it'])} hr={len(hr_rows)}")


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
