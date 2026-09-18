#!/usr/bin/env python3
"""minutes-from-transcript: a food co-op's leadership meeting transcript, the calendar invite, the staff directory and
the general manager's minutes guidelines become the meeting minutes.

    python gen.py [--seed N]

Business: a member-owned grocery co-op. The monthly leadership meeting was recorded and run through a transcription
service a week later; the general manager wants proper minutes.

Traps (each caught by a check, see task.yaml):
  * the transcription export is named and stamped with its upload date a week after the meeting; the meeting date is
    in the calendar invite, and every relative date resolves from it              (check: minutes facts)
  * two decisions are reversed later in the meeting: the freezer repair goes to the second vendor once the cheaper one
    cannot get the part, and Christmas Eve closing moves from 3 pm to 5 pm        (checks: freezer repair decision; minutes facts)
  * action owners are named by first name only; the directory has two people called Marcus and the invite's attendee
    list says which one was there                                                   (check: minutes facts)
  * "next Friday", "two weeks from today", "end of the month" and "before our next meeting" must become calendar dates;
    the guidelines say next Friday is the Friday of the following week and the meeting recurs on the first Monday
                                                                                     (check: minutes facts)
  * the bulk bin expansion is agreed early and never revisited; the Sunday hours idea is parked, not decided
                                                                                     (checks: bulk bins decision; minutes facts)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COOP = "Alder Creek Food Co-op"
DOMAIN = "aldercreek.coop"
MEETING = date(2026, 10, 5)      # first Monday of October
UPLOAD = date(2026, 10, 12)
NEXT_MEETING = date(2026, 11, 2)  # first Monday of November


def next_friday(d: date) -> date:
    """Friday of the following week (the guideline's reading)."""
    monday_next = d + timedelta(days=7 - d.weekday())
    return monday_next + timedelta(days=4)


def build(seed: int) -> dict:
    r = rng(seed * 23 + 9)
    used_f, used_l, ppl = set(), set(), []
    while len(ppl) < 12:
        f, l = person(r)
        if f in used_f or l in used_l or f in used_l or l in used_f or f in ("Marcus",) or l in FIRST:
            continue
        used_f.add(f); used_l.add(l); ppl.append((f, l))
    roles = ["gm", "grocery", "hr", "marketing", "facilities", "produce", "deli", "frontend", "board_chair", "bookkeeper", "wellness", "treasurer"]
    P = {k: {"first": f, "last": l} for k, (f, l) in zip(roles, ppl)}
    P["grocery"]["first"] = "Marcus"
    P["treasurer"]["first"] = "Marcus"
    for v in P.values():
        v["full"] = f"{v['first']} {v['last']}"
    cheap = r.choice([7900, 8400, 8650])
    dear = cheap + r.choice([650, 750, 900])
    bins = r.choice([10, 12, 14])
    bins_budget = bins * r.choice([180, 190, 210])
    actions = [
        dict(key="freezer", owner="grocery", phrase="next Friday", due=next_friday(MEETING), naive_due=next_friday(UPLOAD),
             task="Return Northwind's signed quote to the general manager", keyword=r"northwind|quote|freezer|compressor"),
        dict(key="holiday", owner="hr", phrase="two weeks from today", due=MEETING + timedelta(days=14), naive_due=UPLOAD + timedelta(days=14),
             task="Send the holiday hours schedule to all staff", keyword=r"holiday|schedule|christmas"),
        dict(key="newsletter", owner="marketing", phrase="the end of the month", due=date(2026, 10, 31), naive_due=date(2026, 10, 31),
             task="Draft the November member newsletter", keyword=r"newsletter"),
        dict(key="parking", owner="facilities", phrase="before our next meeting", due=NEXT_MEETING, naive_due=NEXT_MEETING,
             task="Get three bids for restriping the parking lot", keyword=r"parking|restrip|stripe|bids?"),
    ]
    return dict(P=P, cheap=cheap, dear=dear, bins=bins, bins_budget=bins_budget, actions=actions)


def ts(sec: int) -> str:
    return f"[{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}]"


def emit(seed: int) -> None:
    d = build(seed)
    P = d["P"]
    ws, ref, sol = task_dirs(HERE)
    g, m, h, k, fa = (P[x]["first"] for x in ("gm", "grocery", "hr", "marketing", "facilities"))
    cheap, dear = d["cheap"], d["dear"]
    lines = [
        (g, "Okay, it's two minutes past, let's start. First Monday of the month, same as always. I've got Marcus, " + h + ", " + k + " and " + fa + " here. Is the recorder on?"),
        (k, "It's on."),
        (g, "Great. First thing, the walk-in freezer. Marcus, where are we?"),
        (m, f"So the compressor on the walk-in is on its last legs, we've been running the backup unit since Wednesday. I got two quotes. Polar Tech Refrigeration is ${cheap:,} all in, and Northwind Refrigeration is ${dear:,}. Same compressor, Northwind's labor is higher."),
        (fa, "Polar Tech did the produce cooler last year and they were fine."),
        (g, f"Then let's go with Polar Tech at ${cheap:,}. That's decided, Marcus, go ahead and book them."),
        (m, "Will do. I'll text their scheduler right now so we get on the calendar."),
        (g, "Next, the bulk department. " + k + ", you had the proposal on bulk bins."),
        (k, f"Yes. Members keep asking for more bulk, so the proposal is to add {d['bins']} gravity bins on the wall by the coffee grinder. The quote for the bins and the mounting rail is ${d['bins_budget']:,}."),
        (h, "Do we have staff hours to keep them filled?"),
        (k, "Grocery says yes if we fill them on the Tuesday and Friday deliveries."),
        (g, f"Okay. I'm hearing no objections. We're approving the {d['bins']} new bulk bins. " + k + ", you're coordinating the install with Marcus, no date on that yet."),
        (g, "Holiday hours. " + h + "?"),
        (h, "The proposal from the front end team is to close at 3 on Christmas Eve so people can get home. Normal hours the rest of the week, closed Christmas Day."),
        (g, "That seems reasonable. Fine, 3 p.m. on Christmas Eve."),
        (k, "Can we also talk about Sunday hours? A few members asked about opening at 8 instead of 9."),
        (g, "Let's park that one. It needs the staffing numbers first. We'll look at it in January."),
        (g, "Newsletter. " + k + ", is November's newsletter on track?"),
        (k, "It will be. I need the holiday hours and the bulk bins news in it."),
        (g, "Then please get a draft of the November newsletter to me by the end of the month."),
        (k, "Okay."),
        (fa, "Can I raise the parking lot? The lines are basically gone in the back row and we had a fender bender last week."),
        (g, "Yes, that has to happen before winter. " + fa + ", can you get three bids for restriping, and have them before our next meeting?"),
        (fa, "Sure."),
        (h, "Going back to Christmas Eve for a second. I pulled last year's numbers while we were talking. We closed at 3 last year too, and there was a line out the door at quarter to three. We lost sales and had members complaining on the Facebook group for a week."),
        (m, "That matches what my team said. The last two hours on Christmas Eve are huge for grocery."),
        (g, "Okay, I don't want a repeat of that. Let's change it: we close at 5 on Christmas Eve, not 3. " + h + ", once that's settled, please send the holiday schedule out to all staff two weeks from today."),
        (h, "Two weeks from today, got it."),
        (m, "Sorry, one more on the freezer. Polar Tech just texted me back. They can't get the compressor until the middle of November."),
        (fa, "We can't run the walk-in on the backup unit for six weeks."),
        (g, f"No, we can't. Okay, reverse the freezer decision. We go with Northwind at ${dear:,} instead. Marcus, get Northwind's signed quote back to me by next Friday so they can order the part."),
        (m, "Next Friday. Yep."),
        (g, "Anything else? No? Then we're done. Thanks everyone."),
    ]
    sec = 131
    body = []
    r = rng(seed * 31 + 1)
    for spk, txt in lines:
        body.append(f"{ts(sec)} {spk}: {txt}")
        sec += 12 + len(txt) // 4 + r.randint(3, 40)
    out = [f"Transcript export - {COOP}",
           "Title: Monthly leadership meeting",
           f"Uploaded: {UPLOAD.strftime('%a %b %-d, %Y')} 9:02 AM",
           f"Duration: {ts(sec + 20)[1:-1]}",
           "Speakers are labelled by first name as entered at upload.",
           ""] + body
    write_text(os.path.join(ws, f"transcript_{UPLOAD.isoformat()}.txt"), "\n".join(out) + "\n")

    attendees = ["gm", "grocery", "hr", "marketing", "facilities"]
    ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Alder Creek Food Co-op//Calendar//EN", "BEGIN:VEVENT",
           f"UID:leadership-{MEETING.strftime('%Y%m%d')}@{DOMAIN}", "DTSTAMP:20260915T120000Z",
           f"DTSTART;TZID=America/Chicago:{MEETING.strftime('%Y%m%d')}T150000", f"DTEND;TZID=America/Chicago:{MEETING.strftime('%Y%m%d')}T160000",
           "RRULE:FREQ=MONTHLY;BYDAY=1MO", "SUMMARY:Monthly leadership meeting", "LOCATION:Back office / break room",
           f"ORGANIZER;CN={P['gm']['full']}:mailto:{P['gm']['first'].lower()}@{DOMAIN}"]
    for a in attendees:
        ics.append(f"ATTENDEE;CN={P[a]['full']};PARTSTAT=ACCEPTED:mailto:{P[a]['first'].lower()}.{P[a]['last'].lower()}@{DOMAIN}")
    ics.append(f"ATTENDEE;CN={P['treasurer']['full']};PARTSTAT=DECLINED:mailto:{P['treasurer']['first'].lower()}.{P['treasurer']['last'].lower()}@{DOMAIN}")
    ics += ["END:VEVENT", "END:VCALENDAR"]
    write_bytes(os.path.join(ws, "leadership_meeting_invite.ics"), ("\r\n".join(ics) + "\r\n").encode("utf-8"))

    titles = {"gm": ("General Manager", "Management"), "grocery": ("Grocery Manager", "Grocery"), "hr": ("HR & Scheduling Lead", "Management"),
              "marketing": ("Marketing & Member Services", "Member Services"), "facilities": ("Facilities Coordinator", "Operations"),
              "produce": ("Produce Manager", "Produce"), "deli": ("Deli Lead", "Deli"), "frontend": ("Front End Supervisor", "Front End"),
              "board_chair": ("Board Chair (volunteer)", "Board"), "bookkeeper": ("Bookkeeper", "Finance"), "wellness": ("Wellness Buyer", "Wellness"),
              "treasurer": ("Board Treasurer (volunteer)", "Board")}
    rows = []
    for key in ["deli", "grocery", "board_chair", "facilities", "produce", "gm", "treasurer", "hr", "wellness", "marketing", "frontend", "bookkeeper"]:
        v = P[key]
        rows.append([v["last"], v["first"], titles[key][0], titles[key][1], f"{v['first'].lower()}.{v['last'].lower()}@{DOMAIN}", phone_variant(phone_digits(r), 0)])
    write_csv(os.path.join(ws, "staff_directory.csv"), ["Last name", "First name", "Title", "Department", "Email", "Phone"], rows)

    write_text(os.path.join(ws, "minutes_guidelines.txt"),
        f"How we write leadership meeting minutes ({P['gm']['first']}, updated June 2026)\n\n"
        "- Put the date the meeting was held at the top, and who attended (full names).\n"
        "- Decisions: record what we finally decided. If we changed our minds during the meeting, record where we landed, not the first idea.\n"
        "  Things we talked about but parked are not decisions.\n"
        "- Action items: what, who (full name - we have more than one person with some first names), and when, as a calendar date.\n"
        "- Dates: people say things like 'next Friday' in meetings. In our minutes 'next Friday' means the Friday of the following week,\n"
        "  not the Friday coming up this week. 'End of the month' is the last day of that month.\n"
        "- Leadership meets on the first Monday of every month.\n")

    facts = {"meeting": MEETING.isoformat(), "upload": UPLOAD.isoformat(), "cheap_vendor": "Polar Tech", "dear_vendor": "Northwind", "dear": dear, "cheap": cheap,
             "wrong_marcus": P["treasurer"]["last"],
             "actions": [{"key": a["key"], "owner_first": P[a["owner"]]["first"], "owner_last": P[a["owner"]]["last"], "due": a["due"].isoformat(),
                          "naive_due": a["naive_due"].isoformat(), "keyword": a["keyword"], "task": a["task"]} for a in d["actions"]]}
    write_json(os.path.join(ref, "facts.json"), facts)

    long = lambda x: x.strftime("%B %-d, %Y")
    att = ", ".join(P[a]["full"] for a in attendees)
    act_rows = "\n".join(f"| {a['task']} | {P[a['owner']]['full']} | {long(a['due'])} |" for a in d["actions"])
    minutes = (f"# {COOP} - Leadership meeting minutes\n\n"
               f"**Date:** Monday, {long(MEETING)}\n\n"
               f"**Attendees:** {att}\n\n"
               "## Decisions\n\n"
               f"1. Walk-in freezer compressor: the repair goes to Northwind Refrigeration at ${dear:,}. (Polar Tech was chosen first but cannot get the part until mid-November, so the decision was reversed.)\n"
               f"2. Bulk department: approved adding {d['bins']} gravity bulk bins by the coffee grinder (quote ${d['bins_budget']:,}).\n"
               "3. Holiday hours: the store closes at 5:00 PM on Christmas Eve, is closed Christmas Day, and keeps normal hours the rest of the week. (An earlier 3 PM closing was changed after last year's numbers were reviewed.)\n\n"
               "## Discussed, not decided\n\n"
               "- Opening at 8 AM on Sundays: parked until January, pending staffing numbers.\n\n"
               "## Action items\n\n"
               "| Action | Owner | Due |\n|---|---|---|\n"
               f"{act_rows}\n"
               f"| Coordinate the bulk bin install | {P['marketing']['full']} with {P['grocery']['full']} | No date set |\n\n"
               f"Next meeting: Monday, {long(NEXT_MEETING)}.\n")
    write_text(os.path.join(sol, "minutes.md"), minutes)

    write_task_yaml(HERE, {
        "id": "minutes-from-transcript", "track": "desk", "category": "drafting",
        "title": "Minutes from the leadership meeting recording",
        "ask": (f"Can you turn the transcript of our last leadership meeting into proper minutes? My guidelines for minutes are in the folder "
                "with the invite and the staff list. Save them as minutes.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the transcript file is named and stamped with its upload date, {UPLOAD.strftime('%B %-d')}; the meeting was {MEETING.strftime('%A, %B %-d')} per the invite, and relative dates resolve from it (next Friday {next_friday(MEETING).strftime('%B %-d')} not {next_friday(UPLOAD).strftime('%B %-d')}, two weeks from today {(MEETING + timedelta(days=14)).strftime('%B %-d')} not {(UPLOAD + timedelta(days=14)).strftime('%B %-d')}) (check: minutes facts)",
            f"two decisions are reversed later in the meeting: the freezer goes to Northwind at ${dear:,} once Polar Tech (${cheap:,}) cannot get the part, and Christmas Eve closing moves from 3 pm to 5 pm (checks: freezer repair decision; minutes facts)",
            f"owners are named by first name only; the directory has two people called Marcus and the invite shows {P['grocery']['full']} attended while {P['treasurer']['full']} declined (check: minutes facts)",
            "'next Friday', 'two weeks from today', 'the end of the month' and 'before our next meeting' must become calendar dates; the guidelines define next Friday as the following week's and the invite's recurrence gives the first Monday of November (check: minutes facts)",
            f"the {d['bins']} bulk bins are approved early and never revisited, while the Sunday opening idea is parked and is not a decision (checks: bulk bins decision; minutes facts)",
        ],
        "checks": [
            {"type": "file_exists", "name": "minutes.md exists", "path": "minutes.md"},
            {"type": "text_sentence_matches", "name": "freezer repair decision", "path": "minutes.md",
             "all": [r"northwind", rf"\b{dear // 1000},?{dear % 1000:03d}\b"]},
            {"type": "text_sentence_matches", "name": "bulk bins decision", "path": "minutes.md",
             "all": [r"bulk", rf"(?<![\d$,.]){d['bins']}(?![\d,.])|\b{['ten', 'twelve', 'fourteen'][[10, 12, 14].index(d['bins'])]}\b"]},
            {"type": "custom", "name": "minutes facts", "module": "check.py"},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
