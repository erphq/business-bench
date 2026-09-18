"""Each weekly class is one VEVENT with a weekly RRULE whose active occurrences (after EXDATE, cancelled overrides and
the rule's COUNT or UNTIL) are exactly the reference sessions, at the right instant on both sides of the clock change,
each lasting the class length."""
import importlib.util
import os
from datetime import date, datetime, timedelta

_s = importlib.util.spec_from_file_location("ics_common_schedule_to_ics", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ics_common.py"))
ics = importlib.util.module_from_spec(_s); _s.loader.exec_module(ics)
NAME = "weekly series, occurrences and cancellation"


def check(ws, ref):
    events, tzdefs, err = ics.load(ws)
    if err:
        return [{"name": NAME, "passed": False, "detail": err}]
    bad, n = [], 0
    for r in ics.load_ref(ref):
        if r["kind"] != "series":
            continue
        n += 1
        ev = ics.pick_master(events, r["summary"], date.fromisoformat(r["first_date"]), tzdefs)
        if ev is None:
            bad.append(f"{r['summary']}: not found"); continue
        if not ics.prop(ev, "RRULE"):
            bad.append(f"{r['summary']}: not a repeating event (no RRULE)"); continue
        occ, why = ics.active_occurrences(ev, events, tzdefs)
        if occ is None:
            bad.append(f"{r['summary']}: {why}"); continue
        if any(o["utc"] is None for o, _ in occ):
            bad.append(f"{r['summary']}: occurrences have no usable time zone"); continue
        got = sorted(o["utc"] for o, _ in occ)
        want = sorted(datetime.fromisoformat(x) for x in r["occurrences_utc"])
        if got != want:
            extra = [f"{x:%m-%d %H:%M}Z" for x in got if x not in want]
            miss = [f"{x:%m-%d %H:%M}Z" for x in want if x not in got]
            bad.append(f"{r['summary']}: {len(got)} sessions vs {len(want)}; unexpected={extra[:5]} missing={miss[:5]}"); continue
        if any(l is None or l != timedelta(minutes=r["minutes"]) for _, l in occ):
            bad.append(f"{r['summary']}: sessions do not last {r['minutes']} minutes")
    return [{"name": NAME, "passed": not bad, "detail": "; ".join(bad[:4]) if bad else f"{n} series match session for session"}]
