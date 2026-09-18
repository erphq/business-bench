"""One-off timed events and the first session of each weekly class start and end at the right instant: the times carry
a time zone (TZID or UTC) and the webinar's Eastern times are honored."""
import importlib.util
import os
from datetime import datetime

_s = importlib.util.spec_from_file_location("ics_common_schedule_to_ics", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ics_common.py"))
ics = importlib.util.module_from_spec(_s); _s.loader.exec_module(ics)
NAME = "times carry the time zone"


def check(ws, ref):
    events, tzdefs, err = ics.load(ws)
    if err:
        return [{"name": NAME, "passed": False, "detail": err}]
    bad, n = [], 0
    for r in ics.load_ref(ref):
        if r["kind"] == "allday":
            continue
        n += 1
        from datetime import date
        ev = ics.pick_master(events, r["summary"], date.fromisoformat(r["first_date"]), tzdefs)
        if ev is None:
            bad.append(f"{r['summary']}: not found"); continue
        s = ics.dtstart(ev, tzdefs)
        if s is None or s["kind"] == "date":
            bad.append(f"{r['summary']}: no timed DTSTART"); continue
        if s["utc"] is None:
            bad.append(f"{r['summary']}: {s['kind']} time {s['local']} has no usable time zone"); continue
        want_s, want_e = datetime.fromisoformat(r["start_utc"]), datetime.fromisoformat(r["end_utc"])
        ln = ics.length(ev, s, tzdefs)
        if s["utc"] != want_s:
            bad.append(f"{r['summary']}: starts {s['utc']:%Y-%m-%d %H:%M}Z, expected {want_s:%Y-%m-%d %H:%M}Z")
        elif ln is None or s["utc"] + ln != want_e:
            bad.append(f"{r['summary']}: ends {(s['utc'] + ln) if ln is not None else '?'}, expected {want_e:%Y-%m-%d %H:%M}Z")
    return [{"name": NAME, "passed": not bad, "detail": "; ".join(bad[:6]) if bad else f"{n} timed events at the right instant"}]
