#!/usr/bin/env python3
"""event-schedule-page: a beekeepers' conference session sheet as a one-file HTML schedule by day, room and time.

    python gen.py [--seed N] [--naive DIR]

Business: a regional beekeepers' association running its two-day fall conference at a college in Fort Collins.
The registration platform exports sessions with UTC start times and a duration; volunteers typed the rooms.

Traps (each caught by a check, see task.yaml):
  * start times are UTC; the page is in Mountain time (UTC-6 in October)      (check: page structure: local start times)
  * Friday evening sessions carry Saturday's date in UTC                       (check: page structure: day and room)
  * a session holds its room for its duration; overlaps are start-before-other-ends, back-to-back is fine
                                                                                (check: page structure: CONFLICT marks)
  * rooms are typed 'Room 104', 'Rm 104', '104'; one overlap only shows once they are read as one room
                                                                                (checks: page structure: CONFLICT marks, day and room)
  * a cancelled session sits on top of another in the same room               (checks: cancelled session left off; CONFLICT marks)
  * the workbook's first sheet is the August draft with older times            (check: page structure: local start times)
"""
from __future__ import annotations
import argparse
import html
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

OFFSET = timedelta(hours=6)          # MDT = UTC-6
ROOMS = ["Main Hall", "Room 104", "Room 106", "Extraction Lab", "Courtyard"]
ROOM_SPELL = {"Main Hall": ["Main Hall", "Main hall", "MAIN HALL"], "Room 104": ["Room 104", "Rm 104", "104"],
              "Room 106": ["Room 106", "Rm 106", "room 106"], "Extraction Lab": ["Extraction Lab", "Extraction lab", "Ext. Lab"],
              "Courtyard": ["Courtyard", "courtyard"]}
ROOM_RX = {"Main Hall": r"\bmain hall\b", "Room 104": r"(?<![\d:.$])104(?![\d:])", "Room 106": r"(?<![\d:.$])106(?![\d:])",
           "Extraction Lab": r"\bextraction lab\b|\bext\.? lab\b", "Courtyard": r"\bcourtyard\b"}
DAY_RX = {"Fri": r"\bfri(day)?\b|\boct(ober)?\.?\s+0?2\b|\b0?2\s+oct(ober)?\b|\b10/0?2\b|\b2026-10-02\b",
          "Sat": r"\bsat(urday)?\b|\boct(ober)?\.?\s+0?3\b|\b0?3\s+oct(ober)?\b|\b10/0?3\b|\b2026-10-03\b"}
FLAG_RX = r"\bconflicts?\b|\bconflicting\b|\boverlap(s|ping|ped)?\b|\bclash(es|ing)?\b|\bdouble[- ]?booked\b"

TALKS = ["Queen rearing basics", "Reading a frame like a pro", "Varroa monitoring by the numbers", "Swarm traps that work",
         "Winter feeding decisions", "Pollinator gardens for small lots", "Selling honey at farmers markets",
         "Nuc management in year one", "Treatment-free hives: the evidence", "Hive scales and sensors",
         "Native bees and honey bees", "Splitting colonies in spring", "Labeling rules for honey jars",
         "Wax moth and small hive beetle", "Mentoring new beekeepers", "Building a top bar hive"]
LABS = ["Honey extraction walkthrough", "Creamed honey workshop", "Microscope lab: nosema testing", "Comb honey cutting",
        "Wax rendering hands-on", "Sugar roll mite counts"]


def build(seed: int) -> dict:
    r = rng(seed)
    talks = r.sample(TALKS, 13)
    labs = r.sample(LABS, 5)
    sat_shift = r.choice([0, 15])
    sessions = []

    def add(day, room, hh, mm, dur, title, status="Confirmed", tag=""):
        local = datetime(2026, 10, day, hh, mm) + (timedelta(minutes=sat_shift) if day == 3 else timedelta(0))
        s = {"day": "Fri" if day == 2 else "Sat", "room": room, "start": local, "dur": dur, "title": title,
             "status": status, "tag": tag}
        sessions.append(s)
        return s

    # Friday evening (all after 6 pm UTC-wise lands on Saturday)
    add(2, "Courtyard", 18, 0, 120, "Welcome social and honey tasting")
    add(2, "Extraction Lab", 18, 30, 60, "Mead making demo")
    add(2, "Extraction Lab", 19, 30, 60, labs[0], tag="b2b")                 # back-to-back with the mead demo
    add(2, "Room 104", 19, 0, 75, "New beekeeper orientation")
    # Saturday, Main Hall: the keynote runs long into the next talk
    add(3, "Main Hall", 8, 30, 15, "Opening remarks")
    add(3, "Main Hall", 8, 45, 75, "Keynote: bees in a changing climate", tag="ovA")
    add(3, "Main Hall", 9, 45, 60, talks[0], tag="ovA")
    add(3, "Main Hall", 11, 0, 60, talks[1])
    add(3, "Main Hall", 13, 30, 60, talks[2])
    add(3, "Main Hall", 14, 45, 60, talks[3])
    add(3, "Main Hall", 16, 0, 30, "Raffle and closing")
    # Room 104: back-to-back pair, then an overlap hidden by the room spelling
    add(3, "Room 104", 10, 0, 90, talks[4], tag="b2b")
    add(3, "Room 104", 11, 30, 45, talks[5], tag="b2b")
    add(3, "Room 104", 13, 30, 60, talks[6], tag="ovB")
    add(3, "Room 104", 14, 15, 45, talks[7], tag="ovB")
    add(3, "Room 104", 15, 15, 60, talks[8])
    # Room 106
    add(3, "Room 106", 10, 0, 60, talks[9])
    add(3, "Room 106", 11, 15, 60, talks[10])
    add(3, "Room 106", 13, 30, 90, talks[11], tag="b2b")
    add(3, "Room 106", 15, 0, 45, talks[12], tag="b2b")
    # Extraction Lab: a cancelled lab sits over a live one
    add(3, "Extraction Lab", 10, 0, 120, labs[1])
    add(3, "Extraction Lab", 13, 30, 60, labs[2])
    cancelled = add(3, "Extraction Lab", 14, 0, 60, labs[3], status="Cancelled")
    add(3, "Extraction Lab", 15, 0, 60, labs[4])
    add(3, "Courtyard", 12, 15, 75, "Lunch and vendor tables")

    speakers = people(r, len(sessions))
    for s, (f, l) in zip(sessions, speakers):
        s["speaker"] = f"{f} {l}"
        s["end"] = s["start"] + timedelta(minutes=s["dur"])
        s["utc"] = s["start"] + OFFSET
    live = [s for s in sessions if s["status"] != "Cancelled"]
    for s in sessions:
        s["conflict"] = s["status"] != "Cancelled" and any(
            o is not s and o["room"] == s["room"] and o["start"] < s["end"] and s["start"] < o["end"] for o in live)
    # room spellings: the hidden overlap pair is typed two ways
    for s in sessions:
        s["room_raw"] = r.choice(ROOM_SPELL[s["room"]])
    ovb = [s for s in sessions if s["tag"] == "ovB"]
    ovb[0]["room_raw"], ovb[1]["room_raw"] = "Room 104", r.choice(["Rm 104", "104"])
    ids = r.sample(range(210, 299), len(sessions))
    for s, i in zip(sessions, ids):
        s["id"] = f"S{i}"
    # the August draft: same sessions, several at different times, the cancelled one still live
    draft = []
    for s in sessions:
        moved = s["start"] + timedelta(minutes=r.choice([0, 0, 0, -30, 30, 60]))
        draft.append((s, moved + OFFSET))
    return {"sessions": sessions, "live": live, "cancelled": cancelled, "draft": draft}


def naive_conflicts(sessions: list) -> set:
    out = set()
    for s in sessions:
        for o in sessions:
            if o is not s and o["room_raw"] == s["room_raw"] and o["utc"] < s["utc"] + timedelta(minutes=s["dur"]) \
                    and s["utc"] < o["utc"] + timedelta(minutes=o["dur"]):
                out.add(s["title"])
    return out


def acceptable(d: dict) -> bool:
    truth = {s["title"] for s in d["live"] if s["conflict"]}
    if len(truth) != 4:
        return False
    if naive_conflicts(d["sessions"]) == truth:
        return False
    titles = [s["title"] for s in d["sessions"]]
    return len(set(titles)) == len(titles)


def fmt_time(t: datetime) -> str:
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def schedule_html(d: dict) -> str:
    live = d["live"]
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           "<title>Fall Honey Conference 2026 - schedule</title>", "<style>",
           "body{font-family:Verdana,Geneva,sans-serif;margin:24px;color:#1d1d1d;max-width:900px}",
           "h2{border-bottom:2px solid #c68a12;padding-bottom:4px}",
           "h3{margin-bottom:4px}",
           "table{border-collapse:collapse;width:100%;margin-bottom:12px}",
           "td{border-bottom:1px solid #ddd;padding:5px 8px;vertical-align:top}",
           "td.time{white-space:nowrap;width:170px}",
           ".conflict{font-weight:bold;color:#9b1c1c}", "</style>", "</head>", "<body>",
           "<h1>Fall Honey Conference 2026</h1>",
           "<p>All times are Mountain Daylight Time (Fort Collins). Sessions marked CONFLICT overlap another session "
           "in the same room.</p>"]
    for day, label in (("Fri", "Friday, October 2"), ("Sat", "Saturday, October 3")):
        out.append(f"<h2>{label}</h2>")
        for room in ROOMS:
            ss = sorted([s for s in live if s["day"] == day and s["room"] == room], key=lambda s: s["start"])
            if not ss:
                continue
            out.append(f"<h3>{room}</h3>")
            out.append("<table><tbody>")
            for s in ss:
                flag = ' <span class="conflict">CONFLICT</span>' if s["conflict"] else ""
                out.append(f'<tr><td class="time">{fmt_time(s["start"])} - {fmt_time(s["end"])}</td>'
                           f'<td><strong>{html.escape(s["title"])}</strong>{flag}<br>{html.escape(s["speaker"])}</td></tr>')
            out.append("</tbody></table>")
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    sessions, live = d["sessions"], d["live"]
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    order = sorted(sessions, key=lambda s: s["id"])
    header = ["Session ID", "Title", "Presenter", "Room", "Start (UTC)", "Duration (min)", "Status"]
    write_xlsx(os.path.join(ws, "fall_conference_sessions.xlsx"), {
        "Draft v1 (Aug)": {"header": header,
                           "rows": [[s["id"], s["title"], s["speaker"], s["room"], m.strftime("%Y-%m-%dT%H:%M:00Z"),
                                     s["dur"], "Confirmed"] for s, m in sorted(d["draft"], key=lambda x: x[0]["id"])],
                           "widths": {"B": 40, "C": 22, "E": 22}},
        "Sessions": {"header": header,
                     "rows": [[s["id"], s["title"], s["speaker"], s["room_raw"], s["utc"].strftime("%Y-%m-%dT%H:%M:00Z"),
                               s["dur"], s["status"]] for s in order],
                     "widths": {"B": 40, "C": 22, "E": 22}, "freeze": "A2"},
    }, creator="Hivemind Registrations")
    write_text(os.path.join(ws, "note_from_ingrid.txt"),
               "From: Ingrid Haddad <program@frontrangebees.org>\nTo: you\nDate: Sun, 13 Sep 2026 19:48\n"
               "Subject: schedule page for the conference\n\n"
               "Could you turn the session sheet into the schedule page? It goes on the lobby screen and the "
               "volunteers' phones, so one HTML file that works without a connection and without scripts (the lobby "
               "screen's kiosk browser has them switched off).\n\n"
               "Use the Sessions tab. The draft tab is from August and half of it has moved since.\n\n"
               "Lay it out by day, then by room, sessions in time order, with start and end times. Everything we "
               "are running is in Fort Collins, so the page is Mountain time - the platform exports every start "
               "time in UTC and nobody in the building thinks in UTC.\n\n"
               "Anything marked Cancelled comes off the page.\n\n"
               "The volunteers type the rooms however they like. If two sessions end up in the same room at the "
               "same time, keep both on the page but put the word CONFLICT on each of them so I can sort it out "
               "with the presenters. A session that starts the minute the one before it ends is fine, that is how "
               "we planned the day.\n\n"
               "Thanks!\nIngrid\n")
    write_csv(os.path.join(ws, "room_capacity.csv"), ["Room", "Seats", "Projector"],
              [["Main Hall", 220, "yes"], ["Room 104", 60, "yes"], ["Room 106", 45, "yes"],
               ["Extraction Lab", 24, "no"], ["Courtyard", 150, "no"]])
    write_json(os.path.join(ref, "expected.json"), {
        "sessions": [{"title": s["title"], "day": s["day"], "room": s["room"], "start_h": s["start"].hour,
                      "start_m": s["start"].minute, "conflict": s["conflict"], "utc_h": s["utc"].hour}
                     for s in sorted(live, key=lambda s: (s["day"], s["start"], s["room"]))],
        "cancelled": d["cancelled"]["title"],
        "room_rx": ROOM_RX, "day_rx": DAY_RX, "flag_rx": FLAG_RX,
    })
    write_text(os.path.join(sol, "index.html"), schedule_html(d))
    ovb = [s for s in sessions if s["tag"] == "ovB"]
    cx = d["cancelled"]
    traps = [
        "every start time in the sheet is UTC and the conference runs on Mountain Daylight Time, six hours behind; "
        "a page that prints the sheet's times has the keynote before breakfast (check: page structure: local start times)",
        "Friday evening sessions start after midnight UTC, so the sheet dates them 2026-10-03; grouping by the sheet's "
        "date puts all four on Saturday (check: page structure: day and room)",
        "the sheet gives a duration, not an end time; the keynote runs 75 minutes into the next Main Hall talk, while "
        "two pairs of sessions are back to back (one ends the minute the next starts) and are not conflicts "
        "(check: page structure: CONFLICT marks)",
        f"rooms are typed 'Room 104', 'Rm 104', '104', 'MAIN HALL' and 'Ext. Lab'; '{ovb[0]['title']}' and "
        f"'{ovb[1]['title']}' overlap in Room 104 but are typed two ways, so grouping on the text misses the conflict "
        "(checks: page structure: CONFLICT marks; page structure: day and room)",
        f"'{cx['title']}' is Cancelled and starts inside another Extraction Lab session; leaving it on the page "
        "also marks that session CONFLICT wrongly (checks: cancelled session left off; page structure: CONFLICT marks)",
        "the workbook opens on an August draft tab with the same sessions at older times and no cancellation "
        "(checks: page structure: local start times; cancelled session left off)",
    ]
    write_task_yaml(HERE, {
        "id": "event-schedule-page", "track": "desk", "category": "tooling",
        "title": "Conference schedule page for the lobby screen",
        "ask": "Ingrid needs the conference schedule as a web page for the lobby screen and the volunteers' phones. "
               "Her note explains what she wants; the sessions are in the workbook. Save it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "every running session listed", "path": "index.html",
             "phrases": [s["title"] for s in sorted(live, key=lambda s: s["title"])]},
            {"type": "text_not_contains", "name": "cancelled session left off", "path": "index.html",
             "phrases": [cx["title"]]},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} live={len(live)} conflicts={[s['title'] for s in live if s['conflict']]}")


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: the Sessions tab as exported (UTC times and dates, rooms as typed, cancelled included),
    CONFLICT where the typed room text matches and times overlap."""
    os.makedirs(out, exist_ok=True)
    ss = sorted(d["sessions"], key=lambda s: (s["utc"], s["room_raw"]))
    flagged = naive_conflicts(d["sessions"])
    parts = ["<html><body><h1>Schedule</h1><table><tr><th>Date</th><th>Time</th><th>Room</th><th>Session</th></tr>"]
    for s in ss:
        parts.append(f"<tr><td>{s['utc'].strftime('%Y-%m-%d')}</td><td>{s['utc'].strftime('%H:%M')}</td>"
                     f"<td>{s['room_raw']}</td><td>{html.escape(s['title'])}{' CONFLICT' if s['title'] in flagged else ''}</td></tr>")
    parts.append("</table></body></html>\n")
    write_text(os.path.join(out, "index.html"), "\n".join(parts))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
