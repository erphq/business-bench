#!/usr/bin/env python3
"""team-directory-page: a playhouse's HR export as a one-file staff directory grouped by department.

    python gen.py [--seed N] [--naive DIR]

Business: a nonprofit community theatre with a box office, a scene shop and an education program. The HR system
exports one row per job (people with a second job appear twice), department codes rather than names, and keeps
departed staff with a Terminated status and an effective date.

Traps (each caught by a check, see task.yaml):
  * Terminated staff whose last day has passed come off                     (checks: former staff left off; one row per person)
  * one Terminated line has a last day later this month (notice given) and stays  (checks: current staff named; one row per person)
  * Preferred name holds a first name, a whole name, or nothing              (check: page structure: name people go by)
  * departments are codes; the Scene Shop code was folded into Production      (check: page structure: department per person)
  * people with a secondary job appear twice; they belong once, under the primary job
                                                                             (checks: page structure: one row per person, department per person)
  * staff on leave stay listed                                               (check: current staff named)
"""
from __future__ import annotations
import argparse
import html
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TODAY = date(2026, 9, 14)
DEPTS = [("ADM", "Administration"), ("BOX", "Box Office"), ("DEV", "Development"), ("EDU", "Education"),
         ("FOH", "Front of House"), ("MKT", "Marketing"), ("PRD", "Production"), ("SCN", "Scene Shop")]
DEPT_NAME = dict(DEPTS)
SHOWN = ["Administration", "Box Office", "Development", "Education", "Front of House", "Marketing", "Production"]
LABELS = {"Administration": r"\badministration\b", "Box Office": r"\bbox office\b", "Development": r"\bdevelopment\b",
          "Education": r"\beducation\b", "Front of House": r"\bfront of house\b", "Marketing": r"\bmarketing\b",
          "Production": r"\bproduction\b", "Scene Shop": r"\bscene shop\b"}
TITLES = {"ADM": ["Managing Director", "Finance Manager", "Office Coordinator", "HR Generalist"],
          "BOX": ["Box Office Manager", "Ticketing Associate", "Ticketing Associate", "Patron Services Lead"],
          "DEV": ["Development Director", "Grants Writer", "Donor Relations Associate"],
          "EDU": ["Education Director", "Teaching Artist", "Teaching Artist", "Youth Program Coordinator"],
          "FOH": ["House Manager", "Usher Captain", "Concessions Lead"],
          "MKT": ["Marketing Director", "Graphic Designer", "Social Media Coordinator"],
          "PRD": ["Production Manager", "Stage Manager", "Lighting Supervisor", "Costume Shop Manager", "Sound Engineer"],
          "SCN": ["Technical Director", "Scenic Carpenter", "Scenic Painter"]}
# legal first -> preferred first
NICK = [("Katherine", "Kate"), ("William", "Bill"), ("Elizabeth", "Liz"), ("Alejandro", "Alex"), ("Margaret", "Peggy"),
        ("Robert", "Robin"), ("Jonathan", "Jon"), ("Susanna", "Sam"), ("Theodore", "Ted"), ("Rebecca", "Becca")]
PLAIN_FIRST = ["Priya", "Wei", "Carlos", "Fatima", "Hiroshi", "Amara", "Luis", "Ingrid", "Omar", "Sofia", "Kwame", "Yuki",
               "Mateo", "Aisha", "Dmitri", "Chloe", "Rahul", "Nadia", "Tomasz", "Leila", "Marcus", "Dana", "Grace",
               "Felix", "Noor", "Elena", "Jamal", "Iris", "Oscar", "Maya", "Hugo", "Zara", "Ruth", "Emeka"]
LASTS = ["Okafor", "Lindqvist", "Haddad", "Osei", "Mensah", "Tanaka", "Ramos", "Castillo", "Nguyen", "Patel", "Brooks",
         "Foster", "Alvarez", "Bennett", "Kowalski", "Moreau", "Sato", "Ferreira", "Novak", "Abara", "Quinlan", "Varga",
         "Delacroix", "Ibsen", "Marsh", "Oyelaran", "Pruitt", "Rasmussen", "Szabo", "Thorne", "Underwood", "Whitlock",
         "Yilmaz", "Zelenko", "Achebe", "Birch", "Carrow", "Dunmore", "Ellery", "Galloway"]


def build(seed: int) -> dict:
    r = rng(seed)
    lasts = r.sample(LASTS, 36)
    firsts = r.sample(PLAIN_FIRST, 26)
    nicks = r.sample(NICK, 7)
    staff = []
    li = fi = 0
    for code, _ in DEPTS:
        for title in TITLES[code]:
            staff.append({"code": code, "title": title})
    r.shuffle(staff)
    for s in staff:
        s["last"] = lasts[li]; li += 1
    # names: 7 people go by a nickname (4 typed as first name only, 3 as a whole name), 2 by a changed whole name
    for i, s in enumerate(staff):
        if i < 7:
            s["legal_first"], s["pref_first"] = nicks[i]
            s["preferred_raw"] = s["pref_first"] if i < 4 else f"{s['pref_first']} {s['last']}"
            s["display"] = f"{s['pref_first']} {s['last']}"
        else:
            s["legal_first"] = s["pref_first"] = firsts[fi]; fi += 1
            s["preferred_raw"] = ""
            s["display"] = f"{s['legal_first']} {s['last']}"
    # one person uses a hyphenated married name that only the preferred field carries
    mar = staff[7]
    mar["pref_last"] = f"{mar['last']}-{lasts[li]}"; li += 1
    mar["preferred_raw"] = f"{mar['legal_first']} {mar['pref_last']}"
    mar["display"] = mar["preferred_raw"]
    for s in staff:
        s["status"], s["effective"] = "Active", date(2019 + r.randint(0, 6), r.randint(1, 12), r.randint(1, 28))
        s["dept"] = "Production" if s["code"] == "SCN" else DEPT_NAME[s["code"]]
        s["ext"] = r.randint(2100, 2399)
        s["emp_id"] = f"LSP{r.randint(1000, 9999)}"
        user = f"{s['pref_first'][0]}{s.get('pref_last', s['last']).split('-')[0]}".lower()
        s["email"] = f"{user}@lanternstreetplayhouse.org"
    md = next(s for s in staff if s["title"] == "Managing Director")
    # departures: four terminated in the past (one per a few departments), one with a last day ahead
    pool = [s for s in staff if s["preferred_raw"] == "" and s is not mar and s is not md]
    gone = r.sample(pool, 5)
    for s in gone[:4]:
        s["status"], s["effective"] = "Terminated", date(2026, r.randint(3, 8), r.randint(1, 28))
    notice = gone[4]
    notice["status"], notice["effective"] = "Terminated", date(2026, 9, r.randint(18, 30))
    leave = r.sample([s for s in staff if s["status"] == "Active" and s is not md], 2)
    for s in leave:
        s["status"] = "Leave of absence"
    # secondary jobs: two current people also hold a second job in another department
    second = r.sample([s for s in staff if s["status"] != "Terminated" and s["code"] not in ("SCN",)], 2)
    extra_jobs = []
    for s, (code, title) in zip(second, [("EDU", "Teaching Artist"), ("FOH", "Usher")]):
        if s["code"] == code:
            code, title = ("BOX", "Ticketing Associate")
        extra_jobs.append({"of": s, "code": code, "title": title})
    current = [s for s in staff if not (s["status"] == "Terminated" and s["effective"] < TODAY)]
    return {"staff": staff, "current": current, "gone": gone[:4], "notice": notice, "leave": leave, "mar": mar,
            "extra": extra_jobs, "md": md}


def acceptable(d: dict) -> bool:
    staff = d["staff"]
    disp = [s["display"].lower() for s in staff]
    legal = [f"{s['legal_first']} {s['last']}".lower() for s in staff]
    allnames = set(disp) | set(legal)
    for a in allnames:
        for b in allnames:
            if a != b and a in b and not (a.split()[-1] == b.split()[-1].split("-")[0]):
                return False
    emails = [s["email"] for s in staff]
    if len(set(emails)) != len(emails):
        return False
    # a former employee's first name must not be anyone else's first name (keeps exclusions unambiguous)
    for g in d["gone"]:
        if any(s is not g and (s["pref_first"] == g["pref_first"] or s["legal_first"] == g["legal_first"]) for s in staff):
            return False
    # scene shop people and at least one nickname in Production after the fold
    if sum(1 for s in d["current"] if s["code"] == "SCN") < 3:
        return False
    if any(x["of"]["code"] == x["code"] for x in d["extra"]):
        return False
    return len({s["ext"] for s in staff}) == len(staff)


def page_html(d: dict) -> str:
    cur = d["current"]
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           "<title>Lantern Street Playhouse - staff directory</title>", "<style>",
           "body{font-family:'Gill Sans','Trebuchet MS',sans-serif;margin:24px;color:#222;max-width:880px}",
           "h2{margin-top:26px;border-bottom:2px solid #7a1f2b;color:#7a1f2b}",
           "table{border-collapse:collapse;width:100%}", "td,th{text-align:left;padding:5px 8px;border-bottom:1px solid #e4e4e4}",
           "</style>", "</head>", "<body>", "<h1>Lantern Street Playhouse staff directory</h1>",
           "<p>Current staff as of 14 September 2026. Extensions dial from any lobby phone.</p>"]
    for dept in SHOWN:
        people_ = sorted([s for s in cur if s["dept"] == dept], key=lambda s: s["display"].split()[-1])
        if not people_:
            continue
        out.append(f"<h2>{dept}</h2>")
        out.append("<table><thead><tr><th>Name</th><th>Title</th><th>Email</th><th>Ext.</th></tr></thead><tbody>")
        for s in people_:
            out.append(f"<tr><td>{html.escape(s['display'])}</td><td>{html.escape(s['title'])}</td>"
                       f"<td>{s['email']}</td><td>x{s['ext']}</td></tr>")
        out.append("</tbody></table>")
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


def export_rows(d: dict, r) -> list[list]:
    rows = []
    for s in d["staff"]:
        rows.append([s["emp_id"], s["legal_first"], s["last"], s["preferred_raw"], s["code"], s["title"], "Primary",
                     s["email"], s["ext"], s["status"], s["effective"].strftime("%m/%d/%Y")])
    for x in d["extra"]:
        s = x["of"]
        rows.append([s["emp_id"], s["legal_first"], s["last"], s["preferred_raw"], x["code"], x["title"], "Secondary",
                     s["email"], s["ext"], s["status"], date(2025, r.randint(1, 12), r.randint(1, 28)).strftime("%m/%d/%Y")])
    rows.sort(key=lambda x: x[0])
    return rows


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    cur = d["current"]
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 3)
    write_csv(os.path.join(ws, "hris_jobs_export_2026-09-14.csv"),
              ["Employee ID", "Legal first name", "Legal last name", "Preferred name", "Dept code", "Job title", "Job type",
               "Work email", "Desk ext", "Employment status", "Status effective"], export_rows(d, r), crlf=True)
    write_csv(os.path.join(ws, "department_codes.csv"), ["Code", "Department", "Notes"],
              [[c, n, "Folded into Production (PRD) from 1 July 2026 - same crew, one department" if c == "SCN" else ""]
               for c, n in DEPTS])
    md = d["md"]
    write_text(os.path.join(ws, "note_from_managing_director.txt"),
               f"From: {md['display']}, Managing Director\nTo: you\nDate: Mon, 14 Sep 2026 08:40\n"
               "Subject: new staff directory page\n\n"
               "The printed directory by the stage door is two seasons out of date. I would like a directory page we "
               "can put on the backstage screen and send round - one HTML file, nothing it has to load, no scripts (the "
               "screens are locked down).\n\n"
               "Group people by department, with each person's name, job title, work email and desk extension.\n\n"
               "Names: use the name people actually go by. The Preferred name field is what they asked us to use - "
               "some people typed only a first name there, some typed their whole name. If it is empty, use the legal "
               "name. Please do not print someone's legal first name when they have told us otherwise.\n\n"
               "Anyone whose employment has ended is off the page. A few people have given notice and HR already "
               "marks them Terminated with their last day; they are still with us until that day, so keep them. "
               "People on leave are still staff.\n\n"
               "Some people hold two jobs here. List everyone once, under their main job.\n\n"
               f"{md['pref_first']}\n")
    write_json(os.path.join(ref, "expected.json"), {
        "staff": [{"display": s["display"], "legal": f"{s['legal_first']} {s['last']}", "legal_first": s["legal_first"],
                   "pref_first": s["pref_first"], "email": s["email"], "ext": s["ext"], "title": s["title"],
                   "department": s["dept"]} for s in sorted(cur, key=lambda s: (s["dept"], s["display"]))],
        "former": [{"display": s["display"], "legal": f"{s['legal_first']} {s['last']}", "email": s["email"]} for s in d["gone"]],
        "labels": LABELS,
    })
    write_text(os.path.join(sol, "index.html"), page_html(d))
    nt, mar = d["notice"], d["mar"]
    scn = [s for s in cur if s["code"] == "SCN"]
    traps = [
        "four people are Terminated with a last day before today; they are off the page entirely "
        "(checks: former staff left off; page structure: one row per person)",
        f"{nt['display']} is also marked Terminated but the effective date is {nt['effective'].isoformat()}, after "
        "today: notice given, still on staff (checks: every current staff member named; page structure: one row per person)",
        f"Preferred name holds a first name for some people (the page shows it with the legal last name), a whole "
        f"name for others, and nothing for most; {mar['display']} uses a married name only the Preferred field "
        "carries, and seven people's legal first names must not be printed (check: page structure: name people go by)",
        f"departments are codes, and SCN (Scene Shop) was folded into Production in July, so "
        f"{', '.join(s['display'] for s in scn)} belong under Production (check: page structure: department per person)",
        "two people hold a secondary job in another department and appear on two export rows; each is listed once, "
        "under the primary job (checks: page structure: one row per person; page structure: department per person)",
        "two people are on Leave of absence and stay listed (check: every current staff member named)",
    ]
    write_task_yaml(HERE, {
        "id": "team-directory-page", "track": "desk", "category": "tooling",
        "title": "Staff directory page for the backstage screen",
        "ask": f"Please build the new staff directory page from this morning's HR export. {md['pref_first']}'s note says "
               "what goes on it. Save it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "every current staff member named", "path": "index.html",
             "phrases": [s["display"] for s in sorted(cur, key=lambda s: s["display"])]},
            {"type": "text_not_contains", "name": "former staff left off", "path": "index.html",
             "phrases": [s["display"] for s in d["gone"]] + [s["email"] for s in d["gone"]]},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} current={len(cur)} gone={[s['display'] for s in d['gone']]} notice={nt['display']}")


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: every export row that is not Terminated, legal first name + last name, grouped by the
    department code's name, Scene Shop as its own department."""
    os.makedirs(out, exist_ok=True)
    rows = [x for x in export_rows(d, rng(1)) if x[9] != "Terminated"]
    parts = ["<html><body><h1>Staff directory</h1>"]
    for code, name in DEPTS:
        xs = [x for x in rows if x[4] == code]
        if not xs:
            continue
        parts.append(f"<h2>{name}</h2><ul>")
        for x in xs:
            parts.append(f"<li>{x[1]} {x[2]}, {x[5]}, {x[7]}, x{x[8]}</li>")
        parts.append("</ul>")
    parts.append("</body></html>\n")
    write_text(os.path.join(out, "index.html"), "\n".join(parts))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(2000):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
