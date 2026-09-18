#!/usr/bin/env python3
"""event-announcement: a winery's planning sheet for the wine club harvest dinner and the events thread become the
announcement that goes out to club members.

    python gen.py [--seed N]

Business: a family winery with a wine club. The events coordinator filled in the planning sheet at the end of
August; since then the caterer's conflict moved the dinner a week, the owner moved the RSVP deadline with it, and the
estate manager corrected the seating and the address guests should drive to. Nothing has gone out to members yet.

Traps (each caught by a check, see task.yaml):
  * the sheet says Saturday October 17; the caterer is double-booked and the owner moves the dinner to Saturday
    October 24 in the thread                                        (check: dates and seating)
  * the owner pushes the RSVP deadline back a week, from October 5 to October 12  (check: dates and seating)
  * the sheet's address is the tasting room on Old Mill Road; the estate manager says the pavilion is reached from
    its own entrance on Ridgecrest Lane and GPS to the tasting room ends at a locked gate  (check: pavilion address)
  * the sheet's capacity of 120 is the standing reception count; seated for a plated dinner the pavilion holds 96
                                                                    (checks: seated capacity; dates and seating)
  * last spring's release party announcement sits in the folder as a style example with its own date, prices,
    RSVP date and a 60-guest limit                                  (checks: ticket prices; spring party details absent)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

WINERY = "Blackthorn Ridge Winery"
DOMAIN = "blackthornridge.com"
OLD_DATE = date(2026, 10, 17)
NEW_DATE = date(2026, 10, 24)
OLD_RSVP = date(2026, 10, 5)
NEW_RSVP = date(2026, 10, 12)
SPRING_DATE = date(2026, 4, 18)
SPRING_RSVP = date(2026, 4, 10)


def long(d: date) -> str:
    return d.strftime("%A, %B %-d, %Y")


def build(seed: int) -> dict:
    r = rng(seed * 13 + 5)
    ppl, firsts = [], set()
    while len(ppl) < 5:
        f, l = person(r)
        if f not in firsts:
            firsts.add(f); ppl.append((f, l))
    P = {k: {"first": f, "last": l, "full": f"{f} {l}"} for k, (f, l) in zip(["coordinator", "owner", "caterer", "estate", "chef"], ppl)}
    member = r.choice([95, 105, 110])
    guest = member + r.choice([g for g in (20, 25, 30) if member + g != 120])
    spring_member = member - 30
    spring_guest = spring_member + 15
    assert len({member, guest, spring_member, spring_guest, 120, 96, 60}) == 7
    tasting_no = r.randint(3100, 4800)
    pavilion_no = tasting_no + r.choice([290, 350, 410])
    city, st, z = r.choice([("Carlton", "OR", "97111"), ("Dundee", "OR", "97115"), ("Yamhill", "OR", "97148")])
    phone = f"503555{r.randint(1000, 1999)}"
    return dict(P=P, member=member, guest=guest, spring_member=spring_member, spring_guest=spring_guest, tasting=f"{tasting_no} Old Mill Road",
                pavilion=f"{pavilion_no} Ridgecrest Lane", pavilion_no=pavilion_no, city=city, st=st, zip=z, phone=phone,
                seated=96, standing=120, spring_limit=60)


def emit(seed: int) -> None:
    d = build(seed)
    P = d["P"]
    ws, ref, sol = task_dirs(HERE)
    ph = phone_variant(d["phone"], 0)
    # ---- planning sheet
    rows = [
        ["Event", "Wine Club Harvest Dinner"],
        ["Date", OLD_DATE],
        ["Reception (pavilion terrace)", "5:30 PM"],
        ["Dinner seating", "6:30 PM"],
        ["Venue", "Hilltop Pavilion at Blackthorn Ridge"],
        ["Venue address", f"{d['tasting']}, {d['city']}, {d['st']} {d['zip']}"],
        ["Capacity", d["standing"]],
        ["Member ticket", f"${d['member']}.00"],
        ["Guest ticket", f"${d['guest']}.00"],
        ["Guests per member", "up to 2"],
        ["RSVP deadline", OLD_RSVP],
        ["RSVP to", f"events@{DOMAIN} or the tasting room, {ph}"],
        ["Menu", "Four courses by Fennel & Flame Catering, paired with the 2023 Estate Pinot Noir and 2024 Reserve Chardonnay"],
        ["Dress", "Garden casual; the pavilion is open-sided, bring a layer"],
        ["Payment", "Charged to the card on file for club members after RSVP"],
        ["Status", "Draft - nothing sent to members yet"],
    ]
    budget = [["Catering (plated, per cover)", 38, d["standing"], f"=B2*C2"], ["Wine pour allowance (bottles)", 22, 40, "=B3*C3"],
              ["Rentals: linens, lanterns", 640, 1, "=B4*C4"], ["Staff (servers, 5 hrs)", 28, 30, "=B5*C5"]]
    write_xlsx(os.path.join(ws, "harvest_dinner_2026_planning.xlsx"), {
        "Event details": {"merged_title": f"{WINERY} - Harvest Dinner planning sheet", "preamble": [[f"Filled in by {P['coordinator']['first']}, 28 Aug 2026"]],
                          "header": ["Item", "Detail"], "rows": rows, "widths": {"A": 30, "B": 70}},
        "Budget": {"header": ["Line", "Unit cost", "Qty", "Total"], "rows": budget, "widths": {"A": 32}},
    }, creator="Events")

    # ---- thread
    write_email_thread(os.path.join(ws, "email_thread_harvest_dinner.txt"), [
        {"from": f"{P['coordinator']['full']} <{P['coordinator']['first'].lower()}@{DOMAIN}>", "to": f"{P['owner']['full']} <{P['owner']['first'].lower()}@{DOMAIN}>",
         "date": "Fri, 28 Aug 2026 16:05", "subject": "Harvest dinner - planning sheet",
         "body": ("Planning sheet for the harvest dinner is in the shared folder. Nothing has gone out to club members yet; I'd like the announcement "
                  "to go out as soon as we've locked the details.\n\n" + P['coordinator']['full'] + "\nEvents Coordinator")},
        {"from": f"{P['caterer']['full']} <{P['caterer']['first'].lower()}@fennelandflame.com>", "to": f"{P['coordinator']['first'].lower()}@{DOMAIN}",
         "date": "Tue, 8 Sep 2026 10:22", "subject": "RE: Harvest dinner - planning sheet",
         "body": (f"Hi {P['coordinator']['first']},\n\nI'm so sorry, we've been double-booked on the 17th of October (a wedding we confirmed in the spring and "
                  "somehow didn't cross-check). We could do the following Saturday, October 24, with the same menu and staffing. "
                  "Let me know as soon as you can.\n\n" + P['caterer']['first'])},
        {"from": f"{P['owner']['full']} <{P['owner']['first'].lower()}@{DOMAIN}>", "to": f"{P['coordinator']['first'].lower()}@{DOMAIN}",
         "date": "Wed, 9 Sep 2026 07:48", "subject": "RE: Harvest dinner - planning sheet",
         "body": ("We're not changing caterers this close. Let's move the dinner to Saturday the 24th. Same reception and dinner times. "
                  "Push the RSVP deadline back a week as well, so Monday, October 12.\n\n" + P['owner']['full'] + "\nOwner, " + WINERY)},
        {"from": f"{P['estate']['full']} <{P['estate']['first'].lower()}@{DOMAIN}>", "to": f"{P['coordinator']['first'].lower()}@{DOMAIN}",
         "date": "Thu, 10 Sep 2026 13:15", "subject": "RE: Harvest dinner - planning sheet",
         "body": ("Two things before the announcement goes out.\n\n"
                  f"1) The 120 on the sheet is the pavilion's standing reception number. For a plated dinner at 12 tables of 8 we seat {d['seated']}, "
                  "and I don't want to squeeze in more tables.\n\n"
                  f"2) Please don't give guests the tasting room address ({d['tasting']}). The pavilion has its own entrance and GPS to the tasting room "
                  f"ends at the locked vineyard gate after 5. Guests should drive to {d['pavilion']}, {d['city']}, {d['st']} {d['zip']} and park in the "
                  "gravel lot beside the pavilion.\n\n" + P['estate']['full'] + "\nEstate Manager")},
    ])

    # ---- distractor: last spring's announcement
    write_text(os.path.join(ws, "announcement_spring_release_party_2026.md"),
        f"# You're invited: Spring Release Party\n\n"
        f"Dear club members,\n\n"
        f"Join us on **{long(SPRING_DATE)}** from 2:00 to 5:00 PM in the Barrel Room at {d['tasting']}, {d['city']}, for the first pours of our spring releases, "
        "small bites from the kitchen and live music on the patio.\n\n"
        f"- Members: ${d['spring_member']} per person; guests: ${d['spring_guest']} per person\n"
        f"- Space is limited to {d['spring_limit']} guests\n"
        f"- RSVP by {SPRING_RSVP.strftime('%B %-d')} to events@{DOMAIN} or call the tasting room at {ph}\n\n"
        "We can't wait to raise a glass with you.\n\n"
        f"{P['owner']['full']} and the {WINERY} team\n")

    facts = {"event_date": NEW_DATE.isoformat(), "old_date": OLD_DATE.isoformat(), "rsvp": NEW_RSVP.isoformat(), "old_rsvp": OLD_RSVP.isoformat(),
             "spring_date": SPRING_DATE.isoformat(), "spring_rsvp": SPRING_RSVP.isoformat(), "seated": d["seated"], "standing": d["standing"],
             "spring_limit": d["spring_limit"], "pavilion": d["pavilion"], "member": d["member"], "guest": d["guest"]}
    write_json(os.path.join(ref, "facts.json"), facts)
    ann = (f"# Wine Club Harvest Dinner\n\n"
           f"Dear club members,\n\n"
           f"Please join us for our Wine Club Harvest Dinner on {long(NEW_DATE)}, at the Hilltop Pavilion at {WINERY}.\n\n"
           f"The evening begins with a reception on the pavilion terrace at 5:30 PM, and dinner is seated at 6:30 PM. Fennel & Flame Catering "
           "is preparing four courses paired with our 2023 Estate Pinot Noir and 2024 Reserve Chardonnay.\n\n"
           "## Details\n\n"
           f"- Where: Hilltop Pavilion, {d['pavilion']}, {d['city']}, {d['st']} {d['zip']}. Please drive to this address, not the tasting room; "
           "the pavilion has its own entrance and parking in the gravel lot beside it.\n"
           f"- Tickets: ${d['member']} per member and ${d['guest']} per guest. Members may bring up to 2 guests. Tickets are charged to the card on file after you RSVP.\n"
           f"- Seating: the dinner is limited to {d['seated']} seated guests, so please reply early.\n"
           f"- RSVP by Monday, October 12, 2026 to events@{DOMAIN} or call the tasting room at {ph}.\n"
           "- Dress: garden casual. The pavilion is open-sided, so bring a layer for the evening.\n\n"
           "We look forward to celebrating the harvest with you.\n\n"
           f"{P['owner']['full']} and the {WINERY} team\n")
    write_text(os.path.join(sol, "announcement.md"), ann)

    write_task_yaml(HERE, {
        "id": "event-announcement", "track": "desk", "category": "drafting",
        "title": "Announcement for the wine club harvest dinner",
        "ask": (f"Can you write the announcement for the wine club harvest dinner so I can send it to members? The planning sheet and "
                f"{P['coordinator']['first']}'s email thread are in the folder. Save it as announcement.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the planning sheet says {long(OLD_DATE)}; the caterer is double-booked and the owner moves the dinner to {long(NEW_DATE)} in the thread (check: dates and seating)",
            f"the owner pushes the RSVP deadline back a week, from October 5 to October 12; the sheet still shows October 5 (check: dates and seating)",
            f"the sheet's address is the tasting room ({d['tasting']}); the estate manager says guests must drive to the pavilion entrance at {d['pavilion']} (check: pavilion address)",
            f"the sheet's capacity of {d['standing']} is the standing reception count; seated for the plated dinner the pavilion holds {d['seated']} (checks: seated capacity; dates and seating)",
            f"last spring's release party announcement is in the folder as a style example with April dates, ${d['spring_member']}/${d['spring_guest']} prices and a {d['spring_limit']}-guest limit (checks: ticket prices; spring party details absent)",
        ],
        "checks": [
            {"type": "file_exists", "name": "announcement.md exists", "path": "announcement.md"},
            {"type": "custom", "name": "dates and seating", "module": "check.py"},
            {"type": "text_matches_all", "name": "pavilion address", "path": "announcement.md",
             "patterns": [rf"\b{d['pavilion_no']}\s+Ridgecrest\s+(Lane|Ln\b)"]},
            {"type": "text_sentence_matches", "name": "seated capacity", "path": "announcement.md",
             "all": [rf"(?<![\d$.]){d['seated']}(?![\d.])", r"(guest|seat|people|person|attendee|capacity|limited|spot|place|table)"],
             "none": [rf"(?<![\d$.]){d['standing']}(?![\d.])"]},
            {"type": "text_numbers_present", "name": "ticket prices", "path": "announcement.md", "numbers": [d["member"], d["guest"]], "rel_tol": 0.0001},
            {"type": "text_not_contains", "name": "spring party details absent", "path": "announcement.md",
             "phrases": [f"${d['spring_member']}", f"${d['spring_guest']}", "Barrel Room"]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
