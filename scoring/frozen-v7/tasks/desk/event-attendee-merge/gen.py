#!/usr/bin/env python3
"""event-attendee-merge: ticketing export, the paper sign-up sheet and the waitlist into one door list.

    python gen.py [--seed N] [--naive DIR]

Business: an independent bookshop hosting a ticketed author evening. Most people bought online, regulars signed
the paper sheet at the till, and the overflow went on a waitlist form; the owner emailed the waitlist when seats
came free.

Traps (each caught by a check, see task.yaml):
  * the ticketing export is one row per ticket; a two-ticket order repeats the buyer's name and email, so a
    dedupe on email loses the guest and a row count doubles the person          (check: guests per booking)
  * one buyer placed two separate one-ticket orders: still one booking with a guest (check: guests per booking)
  * cancelled and refunded tickets stay in the export; one buyer cancelled and rebooked, so dropping every
    email that ever had a cancelled row loses a real attendee                   (checks: cancelled tickets left off; one line per booking)
  * the same people are on the paper sheet and online with emails in different case and with stray spaces (check: row count)
  * two walk-ups gave only a phone number; a dedupe on the blank email column collapses them into one (checks: walk-ups kept; row count)
  * only waitlisters the owner's email says confirmed come in, one of them under a nickname; a declined one and
    the uncontacted rest stay off                                               (checks: unconfirmed waitlist left off; one line per booking)
  * guests are written 'just me', '+1', 'me + 1', '2 of us' on paper and as a party size on the waitlist (check: guests per booking)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

NICK = {"Elizabeth": "Liz", "Jennifer": "Jen", "Katherine": "Kate", "Rebecca": "Becky", "Margaret": "Maggie", "Robert": "Bob",
        "William": "Will", "Michael": "Mike", "Christopher": "Chris", "Thomas": "Tom", "Daniel": "Dan", "Joseph": "Joe",
        "Patricia": "Trish", "Deborah": "Deb", "Kimberly": "Kim", "Nicholas": "Nick", "Jonathan": "Jon", "Timothy": "Tim",
        "Anthony": "Tony", "Matthew": "Matt", "Stephanie": "Steph", "Samantha": "Sam", "Richard": "Rick", "Kenneth": "Ken"}
PAPER_GUESTS = {0: ["just me", "me", "just me", "myself"], 1: ["+1", "me + 1", "2 of us", "me & partner"], 2: ["3 of us", "me +2"]}


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = []
    seen = set()
    while len(ppl) < 80:
        f, l = person(r)
        if (f, l) in seen or l in {p["last"] for p in ppl if p["first"] == f}:
            continue
        seen.add((f, l))
        ppl.append({"first": f, "last": l, "email": email_for(r, f, l), "phone": phone_digits(r)})
    emails = set()
    for p in ppl:                           # unique emails
        while p["email"] in emails:
            p["email"] = p["email"].replace("@", f"{r.randint(1, 9)}@")
        emails.add(p["email"])
    nick_pool = [p for p in ppl if p["first"] in NICK]
    if len(nick_pool) < 1:
        return {"bad": True}
    nick_person = nick_pool[0]
    rest = [p for p in ppl if p is not nick_person]
    r.shuffle(rest)
    eb_buyers = rest[:40]
    two_order = eb_buyers[0]
    rebook = eb_buyers[1]
    cancelled_only = rest[40:45]
    paper_unique = rest[45:51]
    walkups = rest[51:53]
    wait_promoted = [nick_person] + rest[53:56]
    wait_declined = rest[56]
    wait_uncontacted = rest[57:62]

    # ---- ticket orders ----
    orders = []
    t0 = datetime(2026, 8, 3, 9, 0)
    for i, p in enumerate(eb_buyers):
        qty = 2 if r.random() < 0.3 else 1
        if p is two_order:
            qty = 1
        orders.append({"buyer": p, "qty": qty, "status": "Attending", "when": t0 + timedelta(minutes=r.randint(0, 60 * 24 * 30))})
    orders.append({"buyer": two_order, "qty": 1, "status": "Attending", "when": t0 + timedelta(days=33, minutes=r.randint(0, 600))})
    for p in cancelled_only:
        orders.append({"buyer": p, "qty": r.choice([1, 1, 2]), "status": r.choice(["Cancelled", "Refunded"]),
                       "when": t0 + timedelta(minutes=r.randint(0, 60 * 24 * 30))})
    # the rebooker's first order was cancelled before the one that stands
    reb = next(o for o in orders if o["buyer"] is rebook)
    orders.append({"buyer": rebook, "qty": r.choice([1, 2]), "status": "Refunded", "when": reb["when"] - timedelta(days=4)})
    orders.sort(key=lambda o: o["when"])
    for n, o in enumerate(orders):
        o["no"] = f"{1461200000 + n * 37 + r.randint(0, 30)}"

    # ---- paper sheet: 4 online buyers again (same party size), 6 paper-only, 2 walk-ups with no email ----
    single_or_pair = [p for p in eb_buyers[2:] if sum(o["qty"] for o in orders if o["buyer"] is p and o["status"] == "Attending") in (1, 2)]
    paper_dups = r.sample(single_or_pair, 4)
    paper = []
    for p in paper_dups:
        g = sum(o["qty"] for o in orders if o["buyer"] is p and o["status"] == "Attending") - 1
        paper.append({"p": p, "guests": g, "email_shown": email_case_noise(r, p["email"])})
    for p in paper_unique:
        g = r.choice([0, 0, 1, 1, 2])
        paper.append({"p": p, "guests": g, "email_shown": p["email"] if r.random() < 0.5 else email_case_noise(r, p["email"])})
    for p in walkups:
        paper.append({"p": p, "guests": r.choice([0, 1]), "email_shown": ""})
    r.shuffle(paper)

    # the five people Nadia emailed are the top of the list; everyone after them was never contacted
    waitlist = []
    top = wait_promoted + [wait_declined]
    r.shuffle(top)
    when = datetime(2026, 8, 27, 18, 0)
    for p in top + wait_uncontacted:
        when = when + timedelta(minutes=r.randint(180, 60 * 40))
        waitlist.append({"p": p, "party": r.choice([1, 1, 2]), "when": when})

    # ---- truth ----
    final = {}
    order_of = []
    for o in orders:
        if o["status"] != "Attending":
            continue
        k = o["buyer"]["email"]
        if k not in final:
            final[k] = {"p": o["buyer"], "tickets": 0, "source": "online"}
            order_of.append(k)
        final[k]["tickets"] += o["qty"]
    for k in final:
        final[k]["guests"] = final[k]["tickets"] - 1
    walk_rows = []
    for row in paper:
        p = row["p"]
        if not row["email_shown"]:
            walk_rows.append({"p": p, "guests": row["guests"], "email": ""})
            continue
        if p["email"] in final:
            assert final[p["email"]]["guests"] == row["guests"]
            continue
        final[p["email"]] = {"p": p, "guests": row["guests"], "source": "paper"}
    for w in waitlist:
        if w["p"] in wait_promoted:
            final[w["p"]["email"]] = {"p": w["p"], "guests": w["party"] - 1, "source": "waitlist"}
    return {"ppl": ppl, "orders": orders, "paper": paper, "waitlist": waitlist, "final": final, "walk_rows": walk_rows,
            "two_order": two_order, "rebook": rebook, "cancelled_only": cancelled_only, "paper_dups": paper_dups,
            "walkups": walkups, "promoted": wait_promoted, "declined": wait_declined, "uncontacted": wait_uncontacted,
            "nick_person": nick_person}


def acceptable(d: dict) -> bool:
    if d.get("bad"):
        return False
    orders = d["orders"]
    pairs = [o for o in orders if o["status"] == "Attending" and o["qty"] == 2]
    if len(pairs) < 6:
        return False
    if not any(p["guests"] >= 1 for p in d["paper"] if p["p"] in d["paper_dups"]):
        return False
    if not any(p["guests"] == 0 for p in d["paper"] if p["p"] in d["paper_dups"]):
        return False
    if not any(w["party"] == 2 for w in d["waitlist"] if w["p"] in d["promoted"]):
        return False
    if not any(w["party"] == 1 for w in d["waitlist"] if w["p"] in d["promoted"]):
        return False
    if d["walkups"][0]["last"] == d["walkups"][1]["last"]:
        return False
    # forbidden emails and walk-up names must not hide inside another line of the right answer
    lines = [f"{v['p']['first']} {v['p']['last']},{k},{v['guests']}".lower() for k, v in d["final"].items()]
    lines += [f"{w['p']['first']} {w['p']['last']},,{w['guests']}".lower() for w in d["walk_rows"]]
    forbidden = [p["email"] for p in d["cancelled_only"] + d["uncontacted"] + [d["declined"]]]
    if any(f in ln for f in forbidden for ln in lines):
        return False
    for w in d["walkups"]:
        nm = f"{w['first']} {w['last']}".lower()
        if sum(1 for ln in lines if nm in ln) != 1:
            return False
    # the declined waitlister must not share a surname with anyone who is coming
    coming_last = {v["p"]["last"] for v in d["final"].values()}
    if d["declined"]["last"] in coming_last or d["nick_person"]["last"] in {p["last"] for p in d["ppl"] if p is not d["nick_person"]}:
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 5)

    # ticketing export: one row per ticket
    rows = []
    for o in d["orders"]:
        b = o["buyer"]
        for t in range(o["qty"]):
            rows.append([o["no"], o["when"].strftime("%Y-%m-%d %H:%M:%S"), f"{o['no']}{t + 1:03d}", b["first"], b["last"], b["email"],
                         "General Admission", "25.00", "Eventbrite Completed",
                         o["status"]])
    write_csv(os.path.join(ws, "eventbrite_attendees_report.csv"),
              ["Order #", "Order Date", "Attendee #", "First Name", "Last Name", "Email", "Ticket Type", "Total Paid", "Order Type",
               "Attendee Status"], rows, bom=True)

    # paper sheet typed up at the till
    prow = []
    for row in d["paper"]:
        p = row["p"]
        nm = f"{p['first']} {p['last']}"
        if row["email_shown"] and r.random() < 0.3:
            nm = nm.upper()
        prow.append([nm, row["email_shown"], phone_variant(p["phone"], r.randrange(7)) if (not row["email_shown"] or r.random() < 0.6) else "",
                     r.choice(PAPER_GUESTS[row["guests"]])])
    write_xlsx(os.path.join(ws, "signup_sheet_at_till.xlsx"), {"Sheet1": {
        "merged_title": "Author evening sign-up (in store)", "header": ["Name", "Email", "Phone", "How many coming"], "rows": prow,
        "widths": {"A": 24, "B": 32, "C": 16, "D": 12}}}, creator="Till")

    wrows = []
    for w in d["waitlist"]:
        p = w["p"]
        wrows.append([w["when"].strftime("%m/%d/%Y %H:%M"), f"{p['first']} {p['last']}", p["email"], str(w["party"])])
    write_csv(os.path.join(ws, "waitlist_form_responses.csv"), ["Timestamp", "Full name", "Email address", "How many in your party?"], wrows)

    np_ = d["nick_person"]
    promoted_names = [f"{NICK[np_['first']]} {np_['last']}"] + [f"{p['first']} {p['last']}" for p in d["promoted"][1:]]
    r.shuffle(promoted_names)
    dec = d["declined"]
    write_email_thread(os.path.join(ws, "email_thread_door_list.txt"), [
        {"from": "Nadia Haddad <nadia@wrensparrowbooks.com>", "to": "shop@wrensparrowbooks.com", "date": "Mon, 14 Sep 2026 10:02",
         "subject": "Door list for Thursday",
         "body": ("We had a run of cancellations and refunds last week, so I emailed the top of the waitlist on Friday.\n\n"
                  f"Confirmed and coming: {', '.join(promoted_names[:-1])} and {promoted_names[-1]}. "
                  f"{dec['first']} {dec['last']} said thanks but can't make it now. I haven't contacted anyone else on the waitlist, "
                  "so nobody else from that list is coming.")},
        {"from": "Nadia Haddad <nadia@wrensparrowbooks.com>", "to": "shop@wrensparrowbooks.com", "date": "Mon, 14 Sep 2026 10:20",
         "subject": "Re: Door list for Thursday",
         "body": ("Forgot the actual ask. Can someone put together the door list from the online tickets, the paper sheet from the till "
                  "and the waitlist people above?\n\n"
                  "One line per booking: name, email, guests (how many people they are bringing besides themselves). A cancelled or "
                  "refunded ticket is not coming. Regulars who signed the paper sheet and then bought online are one booking, not two, "
                  "and if someone bought on more than one order it is still one booking, the extra tickets are their guests. "
                  "Keep the walk-ups who only left a phone number, they are coming.\n\nThanks, Nadia")},
    ])

    header = ["name", "email", "guests"]
    out = []
    for k, v in sorted(d["final"].items(), key=lambda kv: (kv[1]["p"]["last"], kv[1]["p"]["first"])):
        out.append([f"{v['p']['first']} {v['p']['last']}", k, v["guests"]])
    for w in d["walk_rows"]:
        out.append([f"{w['p']['first']} {w['p']['last']}", "", w["guests"]])
    write_csv(os.path.join(ref, "attendees.csv"), header, out)
    # the per-email checks read a copy without the phone-only walk-ups (a blank key cannot identify a row)
    write_csv(os.path.join(ref, "bookings_with_email.csv"), header, [row for row in out if row[1]])
    write_csv(os.path.join(sol, "attendees.csv"), header, out)
    headcount = sum(1 + row[2] for row in out)
    write_json(os.path.join(ref, "notes.json"), {
        "bookings": len(out), "headcount": headcount, "two_order_buyer": d["two_order"]["email"], "rebooked": d["rebook"]["email"],
        "cancelled_only": [p["email"] for p in d["cancelled_only"]], "paper_duplicates": [p["email"] for p in d["paper_dups"]],
        "walkups": [f"{p['first']} {p['last']}" for p in d["walkups"]], "promoted": [p["email"] for p in d["promoted"]],
        "nickname": {"email": np_["email"], "written_as": f"{NICK[np_['first']]} {np_['last']}"}, "declined": dec["email"],
        "uncontacted": [p["email"] for p in d["uncontacted"]]})

    pair_buyers = sorted({o["buyer"]["email"] for o in d["orders"] if o["status"] == "Attending" and o["qty"] == 2})
    paper_guests = [row["p"]["email"] for row in d["paper"] if row["email_shown"] and row["guests"] >= 1]
    wait_pairs = [w["p"]["email"] for w in d["waitlist"] if w["p"] in d["promoted"] and w["party"] == 2]
    must = sorted(set(pair_buyers[:3] + [d["two_order"]["email"], d["rebook"]["email"]] + paper_guests[:3] + wait_pairs))
    write_task_yaml(HERE, {
        "id": "event-attendee-merge", "track": "desk", "category": "spreadsheet",
        "title": "Door list for the author evening",
        "ask": ("Thursday's author evening needs a final door list from the online tickets, the paper sign-up sheet and the waitlist. "
                "Nadia's emails say who is in. Save it as attendees.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the ticketing export is one row per ticket and a two-ticket order repeats the buyer's name and email on both rows; "
            "a dedupe on email drops the guest and keeping both rows lists the buyer twice (checks: guests per booking; one line per booking)",
            f"{d['two_order']['first']} {d['two_order']['last']} bought two one-ticket orders a month apart; it is one booking "
            "with one guest (check: guests per booking)",
            f"{len(d['cancelled_only'])} buyers' tickets are Cancelled or Refunded and must be left off, while "
            f"{d['rebook']['first']} {d['rebook']['last']} refunded one order and booked again, so dropping every email that ever "
            "had a refunded row loses a real attendee (checks: cancelled tickets left off; one line per booking)",
            "four regulars are on the paper sheet and online, their emails typed in capitals or with stray spaces on paper; they are "
            "one booking each (checks: one line per booking; row count)",
            "two walk-ups left only a phone number; a dedupe on the email column treats the two blanks as one person "
            "(checks: walk-ups kept; row count)",
            f"only the four waitlisters Nadia confirmed come in, one written as {NICK[np_['first']]} where the form says "
            f"{np_['first']}; the one who declined and the five never contacted stay off (checks: unconfirmed waitlist left off; "
            "one line per booking)",
            "guests are written 'just me', '+1', 'me + 1', '2 of us', '3 of us' on paper, as a party size on the waitlist, and as "
            "extra ticket rows online (check: guests per booking)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "attendees.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one line per booking (emails)", "path": "attendees.csv", "column": "email", "ref": "bookings_with_email.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "attendees.csv", "equals_ref": "attendees.csv"},
            {"type": "csv_values_match", "name": "guests per booking", "path": "attendees.csv", "ref": "bookings_with_email.csv", "key": "email",
             "columns": ["guests"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0, "must_match_keys": must},
            {"type": "text_contains_all", "name": "walk-ups kept", "path": "attendees.csv",
             "phrases": [f"{p['first']} {p['last']}" for p in d["walkups"]]},
            {"type": "text_not_contains", "name": "cancelled tickets left off", "path": "attendees.csv",
             "phrases": [p["email"] for p in d["cancelled_only"]]},
            {"type": "text_not_contains", "name": "unconfirmed waitlist left off", "path": "attendees.csv",
             "phrases": [dec["email"]] + [p["email"] for p in d["uncontacted"]]},
        ],
    })
    print(f"seed={seed} bookings={len(out)} headcount={headcount} ticket_rows={len(rows)}")


def write_naive(d: dict, out: str) -> None:
    """Stack the three files, drop duplicate emails as written (case-sensitive), ignore status and the email, guests blank-as-0."""
    os.makedirs(out, exist_ok=True)
    rows, seen = [], set()
    for o in d["orders"]:
        b = o["buyer"]
        for _ in range(o["qty"]):
            if b["email"] in seen:
                continue
            seen.add(b["email"])
            rows.append([f"{b['first']} {b['last']}", b["email"], 0])
    for row in d["paper"]:
        e = row["email_shown"]
        if e in seen:
            continue
        seen.add(e)
        rows.append([f"{row['p']['first']} {row['p']['last']}", e, row["guests"]])
    for w in d["waitlist"]:
        if w["p"]["email"] in seen:
            continue
        seen.add(w["p"]["email"])
        rows.append([f"{w['p']['first']} {w['p']['last']}", w["p"]["email"], w["party"] - 1])
    write_csv(os.path.join(out, "attendees.csv"), ["name", "email", "guests"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
