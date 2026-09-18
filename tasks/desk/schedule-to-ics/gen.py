#!/usr/bin/env python3
"""schedule-to-ics: a dog-training school's fall class schedule workbook turned into an iCalendar file.

    python gen.py [--seed N] [--naive DIR]

Business: Copper Creek Dog Training in Denver runs weekly classes, test days and the odd webinar. The owner keeps the
season in a workbook and wants an "add to calendar" file for the website that behaves on members' phones.

Traps (each caught by a check, see task.yaml):
  * times are Mountain time and the file must say so; the Tuesday and Saturday classes run across the 1 November
    clock change, so floating times or fixed UTC offsets land an hour off     (checks: times carry the time zone; weekly series)
  * the webinar row's times are Eastern, noted only in the Notes column        (check: times carry the time zone)
  * weekly classes go in as one repeating event: one ends on a date, the other after six sessions (check: weekly series)
  * the 10 November puppy class is cancelled and not made up                    (check: weekly series)
  * the test day and the two-day fun match are all-day events; iCalendar all-day ends are exclusive (check: all-day events)
  * the workbook opens on last summer's sheet                                   (check: every fall event and nothing else)
"""
from __future__ import annotations
import argparse
import importlib.util
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("ics_common_schedule_to_ics", os.path.join(HERE, "ics_common.py"))
ics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ics)

TZ = "America/Denver"
VTIMEZONE = ["BEGIN:VTIMEZONE", "TZID:America/Denver", "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0700", "TZOFFSETTO:-0600", "TZNAME:MDT",
             "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT", "BEGIN:STANDARD",
             "TZOFFSETFROM:-0600", "TZOFFSETTO:-0700", "TZNAME:MST", "DTSTART:19701101T020000",
             "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD", "END:VTIMEZONE"]


def build(seed: int) -> dict:
    r = rng(seed)
    trainers = r.sample(["Marcus Reyes", "Priya Natarajan", "Tom Lindqvist", "Dana Okafor", "Kwame Mensah"], 3)
    speaker = r.choice(["Dr. Amara Osei", "Dr. Leila Haddad", "Dr. Hiroshi Tanaka"])
    puppy_start, puppy_until, cancelled = date(2026, 9, 29), date(2026, 11, 17), date(2026, 11, 10)
    puppy_dates = [puppy_start + timedelta(days=7 * k) for k in range(8)]
    rover_start = date(2026, 10, 3)
    rover_dates = [rover_start + timedelta(days=7 * k) for k in range(6)]
    fall = [
        {"summary": "Puppy Kindergarten", "kind": "series", "who": trainers[0], "where": "Training barn",
         "dates": [x for x in puppy_dates if x != cancelled], "all_dates": puppy_dates, "t": (18, 30), "mins": 60,
         "until": puppy_until, "count": None, "byday": "TU", "exdate": cancelled, "tz": TZ},
        {"summary": "Reactive Rover Small Group", "kind": "series", "who": trainers[1], "where": "Back field",
         "dates": rover_dates, "all_dates": rover_dates, "t": (9, 0), "mins": 90, "until": None, "count": 6, "byday": "SA",
         "exdate": None, "tz": TZ},
        {"summary": "CGC Test Day", "kind": "allday", "who": f"{trainers[0]} & {trainers[1]}", "where": "Training barn",
         "start": date(2026, 10, 17), "end": date(2026, 10, 18)},
        {"summary": "Canine Body Language Webinar", "kind": "timed", "who": speaker, "where": "Online (Zoom link in your email)",
         "day": date(2026, 10, 21), "t": (12, 0), "mins": 60, "tz": "America/New_York"},
        {"summary": "Fall Agility Fun Match", "kind": "allday", "who": trainers[2], "where": "Arapahoe County Fairgrounds arena",
         "start": date(2026, 11, 7), "end": date(2026, 11, 9)},
        {"summary": "Open Barn Night", "kind": "timed", "who": "All trainers", "where": "Training barn",
         "day": date(2026, 11, 20), "t": (18, 0), "mins": 120, "tz": TZ},
    ]
    summer = [
        {"summary": "Puppy Kindergarten", "kind": "series", "dates": [date(2026, 6, 2) + timedelta(days=7 * k) for k in range(8)],
         "t": (18, 30), "mins": 60},
        {"summary": "Sniff and Stroll Social", "kind": "timed", "day": date(2026, 7, 11), "t": (8, 0), "mins": 90},
        {"summary": "Dock Diving Demo Day", "kind": "allday", "start": date(2026, 8, 15), "end": date(2026, 8, 16)},
    ]
    return {"fall": fall, "summer": summer, "trainers": trainers, "speaker": speaker, "cancelled": cancelled}


def utc(tz: str, d: date, hm: tuple) -> datetime:
    return ics.us_local_to_utc(tz, datetime(d.year, d.month, d.day, hm[0], hm[1]))


def ref_events(d: dict) -> list[dict]:
    out = []
    for e in d["fall"]:
        if e["kind"] == "series":
            occ = [utc(e["tz"], x, e["t"]) for x in e["dates"]]
            out.append({"summary": e["summary"], "kind": "series", "first_date": e["dates"][0].isoformat(),
                        "start_utc": occ[0].isoformat(), "end_utc": (occ[0] + timedelta(minutes=e["mins"])).isoformat(),
                        "occurrences_utc": [o.isoformat() for o in occ], "minutes": e["mins"],
                        "local_time": f"{e['t'][0]:02d}:{e['t'][1]:02d}"})
        elif e["kind"] == "timed":
            s = utc(e["tz"], e["day"], e["t"])
            out.append({"summary": e["summary"], "kind": "timed", "first_date": e["day"].isoformat(), "start_utc": s.isoformat(),
                        "end_utc": (s + timedelta(minutes=e["mins"])).isoformat(), "minutes": e["mins"]})
        else:
            out.append({"summary": e["summary"], "kind": "allday", "first_date": e["start"].isoformat(),
                        "start_date": e["start"].isoformat(), "end_date": e["end"].isoformat()})
    return out


def fold(line: str) -> list[str]:
    b = line.encode("utf-8")
    if len(b) <= 75:
        return [line]
    parts, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        limit = 75 if not parts else 74
        if len(cur) + len(cb) > limit:
            parts.append(cur.decode("utf-8")); cur = b""
        cur += cb
    parts.append(cur.decode("utf-8"))
    return [parts[0]] + [" " + p for p in parts[1:]]


def esc(s: str) -> str:
    bs = chr(92)
    return s.replace(bs, bs + bs).replace(";", bs + ";").replace(",", bs + ",").replace("\n", bs + "n")


def reference_ics(d: dict) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Copper Creek Dog Training//Fall schedule//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "X-WR-CALNAME:Copper Creek Dog Training - Fall 2026", f"X-WR-TIMEZONE:{TZ}"] + VTIMEZONE
    for i, e in enumerate(d["fall"]):
        ev = ["BEGIN:VEVENT", f"UID:fall2026-{i + 1}@coppercreekdogs.com", "DTSTAMP:20260915T160000Z", f"SUMMARY:{esc(e['summary'])}"]
        if e["kind"] == "allday":
            ev += [f"DTSTART;VALUE=DATE:{e['start']:%Y%m%d}", f"DTEND;VALUE=DATE:{e['end']:%Y%m%d}", "TRANSP:TRANSPARENT"]
        else:
            first = e["all_dates"][0] if e["kind"] == "series" else e["day"]
            s = datetime(first.year, first.month, first.day, *e["t"])
            en = s + timedelta(minutes=e["mins"])
            ev += [f"DTSTART;TZID={e['tz']}:{s:%Y%m%dT%H%M%S}", f"DTEND;TZID={e['tz']}:{en:%Y%m%dT%H%M%S}"]
            if e["kind"] == "series":
                if e["until"]:
                    last = utc(e["tz"], e["until"], e["t"])
                    ev.append(f"RRULE:FREQ=WEEKLY;BYDAY={e['byday']};UNTIL={last:%Y%m%dT%H%M%SZ}")
                else:
                    ev.append(f"RRULE:FREQ=WEEKLY;BYDAY={e['byday']};COUNT={e['count']}")
                if e["exdate"]:
                    x = e["exdate"]
                    ev.append(f"EXDATE;TZID={e['tz']}:{datetime(x.year, x.month, x.day, *e['t']):%Y%m%dT%H%M%S}")
        desc = f"With {e['who']}."
        if e["summary"] == "Puppy Kindergarten":
            desc += " No class on 10 November (cancelled, not made up). Bring treats, a flat collar and a 6-foot leash."
        ev += [f"LOCATION:{esc(e['where'])}", f"DESCRIPTION:{esc(desc)}", "END:VEVENT"]
        lines += ev
    lines.append("END:VCALENDAR")
    out = []
    for ln in lines:
        out += fold(ln)
    return "\r\n".join(out) + "\r\n"


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)

    def hm(t):
        h, m = t
        return f"{(h - 1) % 12 + 1}:{m:02d} {'AM' if h < 12 else 'PM'}"

    def rows_for(events, fall: bool):
        rows = []
        for e in events:
            if e["kind"] == "series":
                first, last = e["dates"][0], (e.get("all_dates") or e["dates"])[-1]
                end_t = (datetime(2000, 1, 1, *e["t"]) + timedelta(minutes=e["mins"]))
                if e.get("count"):
                    rep, end_cell = f"Weekly - {e['count']} sessions", ""
                else:
                    rep, end_cell = "Weekly", last
                note = ""
                if fall and e.get("exdate"):
                    note = f"NO CLASS 11/10 - {e['who'].split()[0]} is at the CPDT conference. Cancelled, not made up."
                rows.append([e["summary"], e.get("who", ""), e.get("where", "Training barn"), first.strftime("%A") + "s", first,
                             end_cell, hm(e["t"]), hm((end_t.hour, end_t.minute)), rep, note])
            elif e["kind"] == "timed":
                end_t = datetime(2000, 1, 1, *e["t"]) + timedelta(minutes=e["mins"])
                note = ""
                if e.get("tz") == "America/New_York":
                    note = f"Times are EASTERN - {d['speaker']} is presenting from Raleigh."
                rows.append([e["summary"], e.get("who", ""), e.get("where", "Training barn"), e["day"].strftime("%A"), e["day"], "",
                             hm(e["t"]), hm((end_t.hour, end_t.minute)), "One-off", note])
            else:
                days = (e["end"] - e["start"]).days
                note = "Evaluator on site all day, book a slot at the desk" if days == 1 else "Sat & Sun - put it in as all day both days"
                rows.append([e["summary"], e.get("who", ""), e.get("where", "Training barn"),
                             e["start"].strftime("%A") if days == 1 else "Sat-Sun", e["start"], e["end"] - timedelta(days=1),
                             "All day", "", "One-off", note if fall else ""])
        return rows

    header = ["Class / event", "Instructor", "Location", "Day", "Start date", "End date", "Start time", "End time", "Repeats", "Notes"]
    write_xlsx(os.path.join(ws, "class_schedule_2026.xlsx"), {
        "Summer 2026": {"merged_title": "SUMMER 2026 (finished)", "header": header, "rows": rows_for(d["summer"], False),
                        "widths": {"A": 30, "C": 22, "J": 50}},
        "Fall 2026": {"merged_title": "FALL 2026 - Copper Creek Dog Training", "header": header, "rows": rows_for(d["fall"], True),
                      "widths": {"A": 30, "B": 22, "C": 34, "J": 60}}}, creator="Copper Creek")
    write_text(os.path.join(ws, "note_from_jess.txt"),
               "Calendar file for the website - fall\n"
               "\n"
               "Can we get the fall schedule into one calendar file (.ics) so people can click \"add to calendar\"\n"
               "on the website? Only fall - summer is done.\n"
               "\n"
               "- Event name exactly as the class is written on the schedule.\n"
               "- We're in Denver, so times are Mountain time unless the row says otherwise. PLEASE put the time\n"
               "  zone on the events. Last spring's file (spring_2026_classes.ics, still in the folder) didn't have\n"
               "  one and after the clocks changed everybody's phone showed puppy class an hour off.\n"
               "- Weekly classes should be ONE repeating event, not a separate event for every week, so people add\n"
               "  the whole series in one go. The repeat should stop when the class ends.\n"
               "- If a week is cancelled it must not show up on anyone's calendar.\n"
               "- Test day and the fun match are all-day things - all-day events, not midnight to midnight.\n"
               "- Location from the Location column. The instructor can go in the description.\n"
               "\n"
               "Thanks! - Jess\n")
    spring = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Google Inc//Google Calendar 70.9054//EN", "X-WR-CALNAME:Copper Creek Spring"]
    for k in range(6):
        x = date(2026, 3, 3) + timedelta(days=7 * k)
        spring += ["BEGIN:VEVENT", f"DTSTART:{x:%Y%m%d}T183000", f"DTEND:{x:%Y%m%d}T193000", f"UID:spring-puppy-{k + 1}@coppercreekdogs.com",
                   "SUMMARY:Puppy Kindergarten (spring)", "LOCATION:Training barn", "END:VEVENT"]
    spring += ["BEGIN:VEVENT", "DTSTART:20260418", "DTEND:20260418", "UID:spring-cgc@coppercreekdogs.com", "SUMMARY:CGC Test Day (spring)",
               "END:VEVENT", "END:VCALENDAR"]
    write_bytes(os.path.join(ws, "spring_2026_classes.ics"), ("\r\n".join(spring) + "\r\n").encode())
    events = ref_events(d)
    write_json(os.path.join(ref, "events.json"), events)
    ics_text = reference_ics(d)
    write_bytes(os.path.join(ref, "schedule.ics"), ics_text.encode("utf-8"))
    write_bytes(os.path.join(sol, "schedule.ics"), ics_text.encode("utf-8"))

    write_task_yaml(HERE, {
        "id": "schedule-to-ics", "track": "desk", "category": "reformatting",
        "title": "Fall class schedule as a calendar file for the website",
        "ask": ("Can you turn our fall class schedule into a calendar file people can add from the website? Save it as "
                "schedule.ics. Jess's note says how she wants it.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "times must carry the Mountain time zone (TZID or correctly converted UTC); floating times with no zone, or "
            "UTC computed with September's -06:00 offset, put the post-1-November Open Barn Night an hour off "
            "(checks: times carry the time zone; weekly series, occurrences and cancellation)",
            "the webinar row's times are Eastern ('Times are EASTERN' in the Notes column only), so 12:00 PM is 10:00 in "
            "Denver (check: times carry the time zone)",
            "Puppy Kindergarten and Reactive Rover must each be one VEVENT with a weekly RRULE, and both cross the 1 November "
            "clock change, so an RRULE anchored in UTC drifts an hour for the November sessions; Puppy K stops on its end "
            "date (UNTIL) and Reactive Rover after '6 sessions' with no end date (COUNT) "
            "(check: weekly series, occurrences and cancellation)",
            "the 10 November Puppy Kindergarten session is cancelled and not made up; it must be removed with EXDATE or a "
            "cancelled RECURRENCE-ID override, and the series still runs to 17 November (seven sessions) "
            "(check: weekly series, occurrences and cancellation)",
            "CGC Test Day and the Sat-Sun Fall Agility Fun Match are all-day events: DTSTART;VALUE=DATE with an exclusive "
            "end, so the fun match ends 20261109; the workbook's End date is inclusive and midnight-to-midnight times are "
            "not all-day (check: all-day events)",
            "the workbook opens on the finished 'Summer 2026' sheet, which also has a Puppy Kindergarten series, and last "
            "spring's .ics in the folder uses floating times, one event per week and an all-day DTEND equal to DTSTART; "
            "summer and spring events must not be in the file and the spring file is not a pattern to copy "
            "(checks: every fall event and nothing else; times carry the time zone)",
        ],
        "checks": [
            {"type": "file_exists", "name": "schedule.ics exists", "path": "schedule.ics"},
            {"type": "custom", "name": "every fall event and nothing else", "module": "check.py"},
            {"type": "custom", "name": "times carry the time zone", "module": "check_times.py"},
            {"type": "custom", "name": "weekly series, occurrences and cancellation", "module": "check_series.py"},
            {"type": "custom", "name": "all-day events", "module": "check_allday.py"},
        ],
    })
    print(f"seed={seed} fall events={len(events)} speaker={d['speaker']}")


def write_naive(d: dict, out: str) -> None:
    """The obvious export: one VEVENT per session with floating local times (the webinar at 12:00 as written, the
    cancelled week included), all-day events with DTEND on the last day."""
    os.makedirs(out, exist_ok=True)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//naive//EN"]
    k = 0
    for e in d["fall"]:
        if e["kind"] == "allday":
            k += 1
            lines += ["BEGIN:VEVENT", f"UID:n{k}", f"SUMMARY:{e['summary']}", f"DTSTART;VALUE=DATE:{e['start']:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{e['end'] - timedelta(days=1):%Y%m%d}", "END:VEVENT"]
            continue
        days = e["all_dates"] if e["kind"] == "series" else [e["day"]]
        for x in days:
            k += 1
            s = datetime(x.year, x.month, x.day, *e["t"])
            lines += ["BEGIN:VEVENT", f"UID:n{k}", f"SUMMARY:{e['summary']}", f"DTSTART:{s:%Y%m%dT%H%M%S}",
                      f"DTEND:{s + timedelta(minutes=e['mins']):%Y%m%dT%H%M%S}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    write_bytes(os.path.join(out, "schedule.ics"), ("\r\n".join(lines) + "\r\n").encode())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
