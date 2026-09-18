"""Every fall event is in schedule.ics (matched by summary and first start) and nothing else is: no summer events,
no per-week copies of a repeating class. Cancelled VEVENTs and RECURRENCE-ID overrides are not counted as extras."""
import importlib.util
import os
from datetime import datetime

_s = importlib.util.spec_from_file_location("ics_common_schedule_to_ics", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ics_common.py"))
ics = importlib.util.module_from_spec(_s); _s.loader.exec_module(ics)
NAME = "every fall event and nothing else"


def _first_matches(ev, r, tzdefs):
    s = ics.dtstart(ev, tzdefs)
    if s is None:
        return False
    if r["kind"] == "allday":
        return s["date"].isoformat() == r["start_date"]
    want = datetime.fromisoformat(r["start_utc"])
    if s["utc"] is not None:
        return s["utc"] == want
    return s["date"].isoformat() == r["first_date"]     # floating times are judged by the time-zone check


def _near(ev, r, tzdefs):
    s = ics.dtstart(ev, tzdefs)
    if s is None:
        return False
    if s["utc"] is not None and r["kind"] != "allday":
        return abs((s["utc"] - datetime.fromisoformat(r["start_utc"])).total_seconds()) <= 26 * 3600
    return s["date"].isoformat() == r["first_date"]


def check(ws, ref):
    events, tzdefs, err = ics.load(ws)
    if err:
        return [{"name": NAME, "passed": False, "detail": err}]
    refs = ics.load_ref(ref)
    live = [e for e in ics.masters(events) if ics.status(e) != "CANCELLED"]
    used, missing = set(), []
    for r in refs:
        want = ics.norm(r["summary"])
        hit = next((i for i, e in enumerate(live) if i not in used and want in ics.norm(ics.summary(e)) and _first_matches(e, r, tzdefs)), None)
        if hit is None:   # right event, wrong hour: presence is judged here, the instant by the time-zone check
            hit = next((i for i, e in enumerate(live) if i not in used and want in ics.norm(ics.summary(e)) and _near(e, r, tzdefs)), None)
        if hit is None:
            missing.append(r["summary"])
        else:
            used.add(hit)
    extra = [f"{ics.summary(e)} @ {ics.dtstart(e, tzdefs)['date'] if ics.dtstart(e, tzdefs) else '?'}" for i, e in enumerate(live) if i not in used]
    ok = not missing and not extra
    return [{"name": NAME, "passed": ok, "detail": f"{len(refs)} fall events found, nothing extra" if ok else
             f"missing={missing} extra={extra[:8]}" + (f" (+{len(extra) - 8} more)" if len(extra) > 8 else "")}]
