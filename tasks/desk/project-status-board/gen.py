#!/usr/bin/env python3
"""project-status-board: the crew's task board for one remodel job as a single printable HTML page.

    python gen.py [--seed N] [--naive DIR]

Business: a residential remodeling contractor running a kitchen job and a bathroom job at once. The project app
lets anyone type a status, exports one row per assignee, and keeps both jobs in the same export.

Traps (each caught by a check, see task.yaml):
  * statuses are typed freely (WIP, Started, todo, Complete, Finished, Closed, blank) and map to three columns
                                                                       (checks: page structure: column per card, column counts)
  * On hold counts as In progress and a blank status as Not started, per the note
                                                                       (checks: page structure: column per card, column counts)
  * a task with two people on it is exported once per assignee          (checks: page structure: one card per task, column counts)
  * blocked means waiting on a task that is not Done yet; several tasks list dependencies that are already finished
    under another spelling                                              (check: page structure: BLOCKED marks)
  * the bathroom job's tasks are in the same export                     (checks: bathroom job left off; page structure: one card per task)
"""
from __future__ import annotations
import argparse
import html
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

JOB = "Alder Street kitchen"
OTHER = "Hillcrest bathroom"
# id suffix, title, dependencies (by suffix), phase (lower phases happen first)
KITCHEN = [
    (1, "Sign contract and collect deposit", [], 0), (2, "Pull building permit", [1], 0),
    (3, "Protect floors and hang dust walls", [1], 1), (4, "Demo upper and lower cabinets", [3], 1),
    (5, "Remove soffit over sink wall", [4], 1), (6, "Haul demo debris", [4], 2),
    (7, "Rough plumbing for island sink", [5, 2], 2), (8, "Rough electrical and new circuits", [5, 2], 2),
    (9, "Rough-in inspection", [7, 8], 3), (10, "Insulate exterior wall", [9], 4),
    (11, "Hang and tape drywall", [10], 4), (12, "Prime and paint walls", [11], 5),
    (13, "Order cabinets", [1], 0), (14, "Cabinet delivery", [13], 3),
    (15, "Install base cabinets", [12, 14], 6), (16, "Install wall cabinets", [15], 6),
    (17, "Countertop template visit", [15], 7), (18, "Countertop install", [17], 8),
    (19, "Tile backsplash", [18], 9), (20, "Install sink and faucet", [18], 9),
    (21, "Connect dishwasher", [20], 10), (22, "Install range hood", [16], 7),
    (23, "Under-cabinet lighting", [16], 7), (24, "Patch hardwood floor", [15], 7),
    (25, "Final electrical inspection", [23, 22], 10), (26, "Homeowner walkthrough", [25, 19, 21], 11),
]
BATH = ["Remove tub surround", "Set shower pan", "Install vanity", "Tile shower walls", "Replace exhaust fan",
        "Order glass shower door", "Paint bathroom ceiling", "Plumbing inspection for bath"]
SPELL = {"Not started": ["Not started", "not started", "To do", "todo", "Open", ""],
         "In progress": ["In progress", "in progress", "WIP", "Started", "Doing"],
         "Done": ["Done", "done", "Complete", "Completed", "Finished", "Closed"]}
COLUMNS = ["Not started", "In progress", "Done"]
LABELS = {"Not started": r"\bnot[ -]started\b|\bto[ -]?do\b", "In progress": r"\bin[ -]progress\b",
          "Done": r"\bdone\b|\bcompleted?\b|\bfinished\b"}
CREW = ["Luis Ortiz", "Dana Kelly", "Tomasz Nowak", "Aisha Mensah", "Ryan Brooks", "Wei Chen"]


def build(seed: int) -> dict:
    r = rng(seed)
    # project clock: everything in phases below `cut` is done, phase `cut` is under way, the rest not started
    cut = r.choice([5, 6, 7])
    tasks = []
    base = 300 + r.randint(0, 60)
    for suf, title, deps, phase in KITCHEN:
        tasks.append({"id": f"T-{base + suf}", "suf": suf, "title": title, "deps": deps, "phase": phase})
    by_suf = {t["suf"]: t for t in tasks}
    for t in tasks:
        if t["phase"] < cut:
            t["col"] = "Done"
        elif t["phase"] == cut:
            t["col"] = "In progress"
        else:
            t["col"] = "Not started"
    # the job is not a clean wave: a couple of later tasks already started, a couple of earlier ones not closed
    late = [t for t in tasks if t["phase"] == cut + 1]
    for t in r.sample(late, min(2, len(late))):
        t["col"] = "In progress"
    early = [t for t in tasks if t["phase"] == cut - 1]
    straggler = r.choice(early)
    straggler["col"] = "In progress"
    for t in tasks:
        t["deps_t"] = [by_suf[s] for s in t["deps"]]
    # a task cannot be Done while something it waits on is open
    changed = True
    while changed:
        changed = False
        for t in tasks:
            if t["col"] == "Done" and any(dt["col"] != "Done" for dt in t["deps_t"]):
                t["col"] = "In progress"; changed = True
    for t in tasks:
        t["blocked"] = t["col"] != "Done" and any(dt["col"] != "Done" for dt in t["deps_t"])
    # spelling of each status
    on_hold = r.choice([t for t in tasks if t["col"] == "In progress"])
    blank = r.choice([t for t in tasks if t["col"] == "Not started" and t is not on_hold])
    for t in tasks:
        if t is on_hold:
            t["raw_status"] = "On hold"
        elif t is blank:
            t["raw_status"] = ""
        else:
            opts = [s for s in SPELL[t["col"]] if s]
            t["raw_status"] = r.choice(opts)
    # assignees; three tasks carry two people
    for t in tasks:
        t["who"] = [r.choice(CREW)]
    for t in r.sample([x for x in tasks if x["col"] != "Done"], 2) + r.sample([x for x in tasks if x["col"] == "Done"], 1):
        t["who"].append(r.choice([c for c in CREW if c not in t["who"]]))
    start = date(2026, 7, 13)
    for t in tasks:
        t["due"] = start + timedelta(days=7 * t["phase"] + r.randint(0, 4))
    bath = []
    for i, title in enumerate(BATH):
        bath.append({"id": f"T-{base + 40 + i}", "title": title, "raw_status": r.choice(SPELL[r.choice(COLUMNS)][:5]),
                     "who": [r.choice(CREW)], "deps": [], "due": date(2026, 8, 3) + timedelta(days=4 * i)})
    return {"tasks": tasks, "bath": bath, "on_hold": on_hold, "blank": blank, "cut": cut}


def naive_col(raw: str) -> str | None:
    return raw if raw in COLUMNS else None


def acceptable(d: dict) -> bool:
    tasks = d["tasks"]
    counts = {c: sum(1 for t in tasks if t["col"] == c) for c in COLUMNS}
    if min(counts.values()) < 4 or len(set(counts.values())) < 3:
        return False
    blocked = [t for t in tasks if t["blocked"]]
    dep_ok = [t for t in tasks if t["col"] != "Done" and t["deps"] and not t["blocked"]]
    if len(blocked) < 3 or len(dep_ok) < 3:
        return False
    # at least two unblocked tasks whose finished dependency is spelled other than "Done"
    tricky = [t for t in dep_ok if any(dt["raw_status"] != "Done" for dt in t["deps_t"])]
    if len(tricky) < 2:
        return False
    if not any(t["blocked"] and t["col"] == "In progress" for t in tasks):
        return False
    if d["on_hold"]["blocked"] and sum(1 for t in tasks if t["col"] == "In progress" and not t["blocked"]) < 2:
        return False
    # the naive exact-spelling reading must lose cards from every column
    for c in COLUMNS:
        if sum(1 for t in tasks if naive_col(t["raw_status"]) == c) == counts[c]:
            return False
    return True


def export_rows(d: dict, r) -> list[list]:
    rows = []
    for t in d["tasks"]:
        for who in t["who"]:
            rows.append([t["id"], JOB, t["title"], who, t["raw_status"], ", ".join(dt["id"] for dt in t["deps_t"]),
                         t["due"].strftime("%m/%d/%Y")])
    for b in d["bath"]:
        rows.append([b["id"], OTHER, b["title"], b["who"][0], b["raw_status"], "", b["due"].strftime("%m/%d/%Y")])
    r.shuffle(rows)
    rows.sort(key=lambda x: x[6][6:] + x[6][:5])
    return rows


def board_html(d: dict) -> str:
    tasks = d["tasks"]
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           f"<title>{JOB} - task board</title>", "<style>",
           "body{font-family:Helvetica,Arial,sans-serif;margin:20px;color:#111}",
           ".board{display:flex;gap:16px;align-items:flex-start}",
           ".col{flex:1;border:1px solid #999;padding:8px}",
           ".col h2{font-size:18px;margin:0 0 8px}",
           ".card{border:1px solid #bbb;padding:6px 8px;margin-bottom:8px}",
           ".card.blocked{border:3px solid #000}",
           ".flag{font-weight:bold;letter-spacing:1px}",
           ".meta{font-size:12px;color:#444}", "</style>", "</head>", "<body>",
           f"<h1>{JOB} - task board</h1>",
           "<p>Status as of 11 September 2026. Cards marked BLOCKED are waiting on a task that is not Done yet.</p>",
           '<div class="board">']
    ids = {t["id"]: t for t in tasks}
    for c in COLUMNS:
        col = sorted([t for t in tasks if t["col"] == c], key=lambda t: (t["due"], t["id"]))
        out.append('<section class="col">')
        out.append(f"<h2>{c} ({len(col)})</h2>")
        for t in col:
            cls = "card blocked" if t["blocked"] else "card"
            flag = '<div class="flag">BLOCKED</div>' if t["blocked"] else ""
            out.append(f'<div class="{cls}">{flag}<div><strong>{html.escape(t["title"])}</strong></div>'
                       f'<div class="meta">{t["id"]} &middot; {html.escape(" and ".join(t["who"]))} &middot; due '
                       f'{t["due"].strftime("%b %d").replace(" 0", " ")}</div></div>')
        out.append("</section>")
    out += ["</div>", "</body>", "</html>", ""]
    return "\n".join(out)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    tasks = d["tasks"]
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 11)
    write_csv(os.path.join(ws, "project_tasks_export_2026-09-11.csv"),
              ["Task ID", "Project", "Task", "Assignee", "Status", "Depends on", "Due date"], export_rows(d, r), crlf=True)
    write_csv(os.path.join(ws, "crew_phone_list.csv"), ["Name", "Role", "Mobile"],
              [[c, role, phone_variant(phone_digits(r), 0)] for c, role in
               zip(CREW, ["Lead carpenter", "Project manager", "Carpenter", "Electrician", "Plumber", "Helper"])])
    hold, blank = d["on_hold"], d["blank"]
    write_text(os.path.join(ws, "note_from_rosa.txt"),
               "From: Rosa Alvarez\nTo: you\nDate: Fri, 11 Sep 2026 07:05\nSubject: board for the Alder Street crew\n\n"
               "Morning. The crew wants the kitchen board back on the wall - I print it on the black and white "
               "printer in the trailer, so it has to be one page that opens without the internet. Plain page, no scripts - "
               "the trailer laptop blocks them.\n\n"
               "Only the Alder Street kitchen. The Hillcrest bathroom is in the same export but that crew has its own "
               "wall.\n\n"
               "Three columns: Not started, In progress, Done, with how many cards are in each column right on the "
               "column heading. One card per task - when two people are on a task the app spits it out twice, but "
               "it is still one task.\n\n"
               "People type whatever they like in the status box. On hold still goes under In progress (we started "
               "it, it is just parked) and a blank status means nobody has touched it yet, so Not started.\n\n"
               "Anything that is waiting on another task that is not Done yet is blocked. Leave it in its column but "
               "print the word BLOCKED on the card - colour does not survive our printer. If everything it waits on "
               "is done, it is not blocked, whatever else it says.\n\n"
               "Rosa\n")
    write_json(os.path.join(ref, "expected.json"), {
        "tasks": [{"id": t["id"], "title": t["title"], "column": t["col"], "blocked": t["blocked"],
                   "raw_status": t["raw_status"]} for t in tasks],
        "other_job": [b["title"] for b in d["bath"]],
        "counts": {c: sum(1 for t in tasks if t["col"] == c) for c in COLUMNS},
        "labels": LABELS,
    })
    write_text(os.path.join(sol, "index.html"), board_html(d))
    counts = {c: sum(1 for t in tasks if t["col"] == c) for c in COLUMNS}
    traps = [
        "statuses are typed freely (WIP, Started, Doing, todo, Open, Complete, Finished, Closed and mixed case); "
        "grouping on the exact text leaves cards in odd columns or off the board "
        "(checks: page structure: column per card; page structure: column counts)",
        f"'{hold['title']}' is On hold, which the note puts under In progress, and '{blank['title']}' has a blank "
        "status, which the note calls Not started (checks: page structure: column per card; page structure: column counts)",
        "three tasks have two people on them and come out once per assignee, so counting export rows inflates the "
        "columns and a row-per-card board shows them twice "
        "(checks: page structure: one card per task; page structure: column counts)",
        "blocked means waiting on a task that is not Done; several open tasks list dependencies that are finished but "
        "spelled Complete, Finished or Closed, so flagging every task with a Depends on value, or reading only 'Done' "
        "as done, marks them BLOCKED wrongly (check: page structure: BLOCKED marks)",
        "an In progress task can still be blocked, and BLOCKED cards stay in their own column rather than a fourth "
        "one (checks: page structure: BLOCKED marks; page structure: column per card)",
        "the Hillcrest bathroom job's tasks are mixed into the same export, dates sorted together "
        "(checks: bathroom job left off; page structure: one card per task)",
    ]
    write_task_yaml(HERE, {
        "id": "project-status-board", "track": "desk", "category": "tooling",
        "title": "Kitchen job task board for the crew wall",
        "ask": "Please make the Alder Street crew board from this morning's task export - Rosa's note has how she "
               "wants it. I need it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "every kitchen task on the board", "path": "index.html",
             "phrases": [t["title"] for t in tasks]},
            {"type": "text_not_contains", "name": "bathroom job left off", "path": "index.html",
             "phrases": [b["title"] for b in d["bath"]]},
            {"type": "text_numbers_present", "name": "column counts present", "path": "index.html",
             "numbers": [counts[c] for c in COLUMNS], "rel_tol": 0},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} counts={counts} blocked={[t['title'] for t in tasks if t['blocked']]}")


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: one card per export row of the kitchen job, columns by exact status text (anything else
    in an 'Other' column), BLOCKED on every card with a Depends on value."""
    os.makedirs(out, exist_ok=True)
    r = rng(1)
    rows = [x for x in export_rows(d, r) if x[1] == JOB]
    cols = {c: [] for c in COLUMNS + ["Other"]}
    for x in rows:
        cols[naive_col(x[4]) or "Other"].append(x)
    parts = ["<html><body><h1>Board</h1>"]
    for c, xs in cols.items():
        parts.append(f"<h2>{c} ({len(xs)})</h2><ul>")
        for x in xs:
            parts.append(f"<li>{'BLOCKED ' if x[5] else ''}{html.escape(x[2])} - {x[3]}</li>")
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
