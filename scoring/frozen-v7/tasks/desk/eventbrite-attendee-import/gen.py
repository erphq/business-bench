#!/usr/bin/env python3
"""eventbrite-attendee-import: a community choir's Google Form sign-ups reshaped into Eventbrite's attendee import.

    python gen.py [--seed N] [--naive DIR]

Business: Oak Hollow Community Choir sold its first seats for the December concert through a Google Form before
the Eventbrite page existed. The committee wants those people loaded into Eventbrite as orders so the door list and
the capacity count come from one place.

Traps (each caught by a check, see task.yaml):
  * the form's ticket options are labels with prices ("Kids 12 & under - free"); Eventbrite needs its own ticket type
    names spelled exactly                                                     (check: ticket type)
  * "How many?" is free text (two, a pair, just me, blank); blank means one  (check: quantity)
  * a family pass is one ticket however many people the family wrote        (check: quantity)
  * one person filled the form twice and the later response replaces the first (checks: one order per email; quantity; ticket type)
  * June's test response is not an order                                    (checks: one order per email; row count)
  * a few names were typed Last, First                                      (check: first and last name)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["First Name", "Last Name", "Email", "Ticket Type", "Quantity"]
# form label, eventbrite name, price, weight, quantity range
TICKETS = [("Adult - $20", "General Admission", 20.00, 10, (1, 4)),
           ("Senior 65+ - $15", "Senior (65+)", 15.00, 6, (1, 2)),
           ("Student (with ID) - $10", "Student", 10.00, 3, (1, 3)),
           ("Kids 12 & under - free", "Child (12 and under)", 0.00, 3, (1, 3)),
           ("Family pass - $50 (2 adults + up to 3 kids)", "Family Pass", 50.00, 4, (1, 1)),
           ("I'm a guest of a choir member - $12", "Choir Member Guest", 12.00, 4, (1, 4))]
WORDS = {1: ["1", "just me", "one", ""], 2: ["2", "two", "a pair", "2 tickets"], 3: ["3", "three", "3 please"], 4: ["4", "four", "4 tix"]}


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = people(r, 44)
    orders = []
    t = datetime(2026, 9, 21, 19, 2, 11)
    for i, (f, l) in enumerate(ppl[:40]):
        tk = r.choices(TICKETS, [x[3] for x in TICKETS])[0]
        q = r.randint(*tk[4])
        t += timedelta(minutes=r.randint(9, 900), seconds=r.randint(0, 59))
        orders.append({"first": f, "last": l, "email": email_for(r, f, l), "tk": tk, "q": q, "ts": t})
    emails = [o["email"] for o in orders]
    assert len(set(emails)) == len(emails)
    fam = [o for o in orders if o["tk"][1] == "Family Pass"]
    blank = [o for o in orders if o["q"] == 1 and o["tk"][1] != "Family Pass"]
    dup_src = r.choice([o for o in orders[:25] if o["tk"][1] in ("General Admission", "Senior (65+)")])
    dup = dict(dup_src)
    dup["ts"] = dup_src["ts"] + timedelta(days=3, minutes=r.randint(10, 400))
    dup["q"] = dup_src["q"] + 1 if dup_src["q"] < 4 else 2
    dup["tk"] = TICKETS[5] if dup_src["tk"][1] == "General Admission" else TICKETS[0]
    dup["comment"] = ("Sorry, filling this in again - " + (f"my partner sings in the choir, so it's {dup['q']} guest tickets"
                      if dup["tk"][1] == "Choir Member Guest" else f"it's {dup['q']} adult tickets, not senior") + ". Please ignore my first one.")
    final = [dup if o is dup_src else o for o in orders]
    return {"orders": orders, "dup_src": dup_src, "dup": dup, "final": final, "fam": fam, "blank": blank}


def acceptable(d: dict) -> bool:
    types = {o["tk"][1] for o in d["final"]}
    return len(types) == len(TICKETS) and len(d["fam"]) >= 3 and len(d["blank"]) >= 4


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    r = rng(seed + 13)
    resp = []
    last_first = r.sample([o for o in d["orders"] if o is not d["dup_src"]], 3)
    for o in d["orders"]:
        tk, q = o["tk"], o["q"]
        if tk[1] == "Family Pass":
            how = r.choice([f"{r.randint(4, 5)} of us", f"family of {r.randint(3, 5)}", r.choice(["2 adults 2 kids", "2 adults 3 kids", "me, my husband + 2 kids"]), "5"])
        else:
            how = r.choice(WORDS[q])
        name = f"{o['last']}, {o['first']}" if o in last_first else f"{o['first']} {o['last']}"
        name = name.lower() if r.random() < 0.12 else name
        email = o["email"] if r.random() > 0.2 else email_case_noise(r, o["email"])
        o["how"], o["name_typed"] = how, name
        resp.append([o["ts"], name, email, tk[0], how, r.choice(["", "", "", "Can't wait!", "Is there parking?", "wheelchair seating please"])])
    dup = d["dup"]
    resp.append([dup["ts"], f"{dup['first']} {dup['last']}", dup["email"].upper(), dup["tk"][0], str(dup["q"]), dup["comment"]])
    resp.append([datetime(2026, 9, 21, 18, 40, 5), "TEST june", "june@oakhollowchoir.org", TICKETS[0][0], "2", "test - delete"])
    resp.sort(key=lambda x: x[0])
    if naive_dir:
        write_naive(resp, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    write_xlsx(os.path.join(ws, "concert_signups_form_responses.xlsx"), {"Form Responses 1": {
        "header": ["Timestamp", "Your name", "Email address", "Which tickets?", "How many?", "Anything else we should know?"],
        "rows": [[x[0].strftime("%m/%d/%Y %H:%M:%S")] + x[1:] for x in resp], "widths": {"A": 20, "B": 22, "C": 30, "D": 40, "F": 40}}},
        creator="Google Forms")
    write_csv(os.path.join(ws, "eventbrite_ticket_types.csv"), ["Ticket type", "Price", "Quantity available", "Sales end"],
              [[tk[1], f"{tk[2]:.2f}", r.choice([40, 60, 120]), "12/12/2026 7:00 PM"] for tk in TICKETS])
    write_csv(os.path.join(ws, "eventbrite_attendee_import_template.csv"), HEADER,
              [["Alex", "Example", "alex.example@example.com", "General Admission", "2"]])
    write_email_thread(os.path.join(ws, "email_from_june.txt"), [
        {"from": "June Whitaker <june@oakhollowchoir.org>", "to": "you", "date": "Mon, 5 Oct 2026 20:12",
         "subject": "Moving the concert sign-ups into Eventbrite",
         "body": ("Hi! Now the Eventbrite page is up I'd like everyone who signed up on the Google Form loaded in as attendees, "
                  "so the door list and the numbers all come from Eventbrite. They have an import - template attached, and the "
                  "ticket types as they are set up on the event.\n\n"
                  "A few things:\n"
                  "- One row per person who signed up, with their ticket type and how many tickets.\n"
                  "- Ticket Type has to be exactly the Eventbrite name or the import rejects the row. The form wording is "
                  "different (I wrote it before we set up Eventbrite).\n"
                  "- The form asked 'How many?' and people typed all sorts. If they left it blank it's one ticket. The Family "
                  "Pass is ONE ticket for the whole family, no matter how many people they said.\n"
                  "- If someone filled the form in more than once, their latest response is the one that counts.\n"
                  "- My test response from the first night is in there too, please leave that out.\n"
                  "- First and last name in their own columns.\n\nThanks so much,\nJune")}])

    rows = [[o["first"], o["last"], o["email"], o["tk"][1], str(1 if o["tk"][1] == "Family Pass" else o["q"])]
            for o in sorted(d["final"], key=lambda o: o["ts"])]
    write_csv(os.path.join(ref, "eventbrite_attendees.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "eventbrite_attendees.csv"), HEADER, rows)
    words = [o["email"] for o in d["orders"] if o["tk"][1] != "Family Pass" and not o["how"].strip().isdigit()]
    qty_pins = sorted(set([o["email"] for o in d["fam"]] + words + [d["dup"]["email"]]))
    type_pins = sorted({next(o["email"] for o in d["final"] if o["tk"][1] == tk[1]) for tk in TICKETS} | {d["dup"]["email"]})
    name_pins = sorted(o["email"] for o in last_first)
    write_json(os.path.join(ref, "notes.json"), {"rows": len(rows), "duplicate": d["dup"]["email"], "test": "june@oakhollowchoir.org",
                                                  "family": [o["email"] for o in d["fam"]]})
    write_task_yaml(HERE, {
        "id": "eventbrite-attendee-import", "track": "desk", "category": "reformatting",
        "title": "Load the concert sign-ups into Eventbrite",
        "ask": ("June wants the people who signed up for the winter concert on our Google Form loaded into Eventbrite. Can you "
                "make the import file from the form responses and save it as eventbrite_attendees.csv? Her email, the "
                "template and the ticket types are in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the form's ticket choices are labels with prices ('Adult - $20', 'Kids 12 & under - free', 'I'm a guest of a "
            "choir member - $12'); Eventbrite rejects anything but its own names (General Admission, Child (12 and under), "
            "Choir Member Guest ...) (check: ticket type)",
            "'How many?' is free text: 'two', 'a pair', '3 please', '4 tix', 'just me', and blank, which June says is one "
            "(check: quantity)",
            f"{len(d['fam'])} Family Pass responses answered with head counts ('family of 4', '2 adults 3 kids', '5'); a family "
            "pass is one ticket, so copying the number oversells the event (check: quantity)",
            "one person submitted twice three days apart, the second time in capitals with a different ticket type and count "
            "and a comment asking to ignore the first; the later response is the order (checks: one order per email; "
            "quantity; ticket type)",
            "June's own test response ('TEST june', 'test - delete') is the first row of the sheet and is not an order "
            "(checks: one order per email; row count)",
            "three names were typed 'Last, First' and some are all lowercase; splitting on the first space puts the comma "
            "and surname in First Name (check: first and last name)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Eventbrite template columns, exact order", "path": "eventbrite_attendees.csv",
             "columns": HEADER, "exact": True},
            {"type": "csv_set_equal", "name": "one order per email", "path": "eventbrite_attendees.csv", "column": "Email",
             "ref": "eventbrite_attendees.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "eventbrite_attendees.csv", "equals_ref": "eventbrite_attendees.csv"},
            {"type": "csv_values_match", "name": "ticket type", "path": "eventbrite_attendees.csv", "ref": "eventbrite_attendees.csv",
             "key": "Email", "columns": ["Ticket Type"], "min_accuracy": 1.0, "must_match_keys": type_pins},
            {"type": "csv_values_match", "name": "quantity", "path": "eventbrite_attendees.csv", "ref": "eventbrite_attendees.csv",
             "key": "Email", "columns": ["Quantity"], "numeric": True, "tolerance": 0.001, "min_accuracy": 1.0, "must_match_keys": qty_pins},
            {"type": "csv_values_match", "name": "first and last name", "path": "eventbrite_attendees.csv", "ref": "eventbrite_attendees.csv",
             "key": "Email", "columns": ["First Name", "Last Name"], "min_accuracy": 1.0, "must_match_keys": name_pins},
        ],
    })
    print(f"seed={seed} responses={len(resp)} rows={len(rows)} family={len(d['fam'])} dup={d['dup']['email']}")


def write_naive(resp: list, out: str) -> None:
    """The obvious reshape: every response a row, the form label as the ticket type, the digits in How many? as the
    quantity (blank when there are none), the name split on the first space, first response kept on a repeat email."""
    import re
    os.makedirs(out, exist_ok=True)
    rows, seen = [], set()
    for ts, name, email, label, how, comment in resp:
        e = email.strip().lower()
        if e in seen:
            continue
        seen.add(e)
        first, _, last = name.strip().partition(" ")
        digits = re.findall(r"\d+", how)
        rows.append([first, last, e, label, digits[0] if digits else ""])
    write_csv(os.path.join(out, "eventbrite_attendees.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(300):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
