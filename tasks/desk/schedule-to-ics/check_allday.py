"""All-day events are written as dates (VALUE=DATE), start on the right day and end on the exclusive day after the
last day (a missing DTEND counts as one day)."""
import importlib.util
import os
from datetime import date, timedelta

_s = importlib.util.spec_from_file_location("ics_common_schedule_to_ics", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ics_common.py"))
ics = importlib.util.module_from_spec(_s); _s.loader.exec_module(ics)
NAME = "all-day events"


def check(ws, ref):
    events, tzdefs, err = ics.load(ws)
    if err:
        return [{"name": NAME, "passed": False, "detail": err}]
    bad, n = [], 0
    for r in ics.load_ref(ref):
        if r["kind"] != "allday":
            continue
        n += 1
        start = date.fromisoformat(r["start_date"])
        ev = ics.pick_master(events, r["summary"], start, tzdefs)
        if ev is None:
            bad.append(f"{r['summary']}: not found"); continue
        s = ics.dtstart(ev, tzdefs)
        if s is None or s["kind"] != "date":
            bad.append(f"{r['summary']}: DTSTART is not a date (all-day events use VALUE=DATE)"); continue
        if s["date"] != start:
            bad.append(f"{r['summary']}: starts {s['date']}, expected {start}"); continue
        ln = ics.length(ev, s, tzdefs)
        want = date.fromisoformat(r["end_date"]) - start
        if ln != want:
            bad.append(f"{r['summary']}: covers {ln.days if ln is not None else '?'} day(s), expected {want.days} (DTEND is exclusive)")
    return [{"name": NAME, "passed": not bad, "detail": "; ".join(bad) if bad else f"{n} all-day events correct"}]
