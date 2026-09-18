"""Standard-library iCalendar reading for the schedule-to-ics checks (and the generator's reference times).

Unfolds lines, reads VEVENTs (skipping VALARM blocks), resolves DTSTART/DTEND/EXDATE/RDATE/RECURRENCE-ID with a TZID,
a trailing Z, VALUE=DATE or floating time, expands weekly and daily RRULEs in local wall time, applies EXDATE,
cancelled overrides and cancelled masters. Property order, line folding, PRODID and UID formats do not matter.
Time zones resolve through zoneinfo when the host has tz data, otherwise through built-in US rules, aliases for
Windows and legacy names, or the file's own VTIMEZONE definitions.
"""
from __future__ import annotations

import glob
import os
import re
from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc
US_STD = {"America/Denver": -7, "America/New_York": -5, "America/Chicago": -6, "America/Los_Angeles": -8,
          "America/Phoenix": -7, "America/Boise": -7, "America/Detroit": -5, "America/Indiana/Indianapolis": -5}
NO_DST = {"America/Phoenix"}
ALIASES = {"us/mountain": "America/Denver", "mountain standard time": "America/Denver", "mst7mdt": "America/Denver",
           "mountain time (us & canada)": "America/Denver", "america/edmonton": "America/Denver",
           "us/eastern": "America/New_York", "eastern standard time": "America/New_York", "est5edt": "America/New_York",
           "eastern time (us & canada)": "America/New_York", "us/central": "America/Chicago",
           "central standard time": "America/Chicago", "cst6cdt": "America/Chicago", "central time (us & canada)": "America/Chicago",
           "us/pacific": "America/Los_Angeles", "pacific standard time": "America/Los_Angeles", "pst8pdt": "America/Los_Angeles",
           "pacific time (us & canada)": "America/Los_Angeles", "us/arizona": "America/Phoenix",
           "us mountain standard time": "America/Phoenix"}
DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


# ----------------------------------------------------------------------------------------- time zones

def _nth_sunday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    first = d + timedelta(days=(6 - d.weekday()) % 7)
    return first + timedelta(days=7 * (n - 1))


def us_local_to_utc(zone: str, local: datetime) -> datetime:
    std = US_STD[zone]
    off = std
    if zone not in NO_DST and local.year >= 2007:
        start = datetime.combine(_nth_sunday(local.year, 3, 2), datetime.min.time()) + timedelta(hours=2)
        end = datetime.combine(_nth_sunday(local.year, 11, 1), datetime.min.time()) + timedelta(hours=2)
        if start <= local < end:
            off = std + 1
    return (local - timedelta(hours=off)).replace(tzinfo=UTC)


def _canonical(tzid: str) -> str:
    t = tzid.strip().strip('"')
    m = re.search(r"([A-Za-z]+/[A-Za-z_]+(?:/[A-Za-z_]+)?)$", t)   # /mozilla.org/.../America/Denver
    if m and m.group(1) in US_STD:
        return m.group(1)
    return ALIASES.get(t.lower(), t)


def _byday_rule(year: int, month: int, byday: str) -> date | None:
    m = re.fullmatch(r"([+-]?\d)?(MO|TU|WE|TH|FR|SA|SU)", byday.strip().upper())
    if not m:
        return None
    n = int(m.group(1) or 1)
    wd = DAYS.index(m.group(2))
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(wd - d.weekday()) % 7)
        return d + timedelta(days=7 * (n - 1))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    d -= timedelta(days=(d.weekday() - wd) % 7)
    return d + timedelta(days=7 * (n + 1))


def _offset(text: str) -> timedelta | None:
    m = re.fullmatch(r"([+-])(\d{2})(\d{2})(\d{2})?", text.strip())
    if not m:
        return None
    s = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)), seconds=int(m.group(4) or 0))
    return s if m.group(1) == "+" else -s


def vtimezone_local_to_utc(defn: list, local: datetime) -> datetime | None:
    """defn: [(kind, {prop: value})] from a VTIMEZONE; picks the latest onset at or before `local`."""
    best = None
    for kind, props in defn:
        to = _offset(props.get("TZOFFSETTO", ""))
        start = _parse_basic(props.get("DTSTART", ""))
        if to is None or not isinstance(start, datetime):
            continue
        rule = parse_rrule(props.get("RRULE", "")) if props.get("RRULE") else None
        onsets = []
        if rule and rule.get("FREQ") == "YEARLY" and rule.get("BYMONTH") and rule.get("BYDAY"):
            for y in (local.year - 1, local.year):
                d = _byday_rule(y, int(rule["BYMONTH"].split(",")[0]), rule["BYDAY"].split(",")[0])
                if d:
                    onsets.append(datetime.combine(d, start.time()))
        else:
            onsets.append(start)
        for o in onsets:
            if o <= local and (best is None or o > best[0]):
                best = (o, to)
    if best is None:
        return None
    return (local - best[1]).replace(tzinfo=UTC)


def local_to_utc(tzid: str, local: datetime, tzdefs: dict) -> datetime | None:
    """IANA or aliased names first (what calendar apps do), then the file's own VTIMEZONE definition."""
    canon = _canonical(tzid)
    try:
        from zoneinfo import ZoneInfo
        return local.replace(tzinfo=ZoneInfo(canon)).astimezone(UTC)
    except Exception:
        pass
    if canon in US_STD:
        return us_local_to_utc(canon, local)
    if tzid in tzdefs:
        return vtimezone_local_to_utc(tzdefs[tzid], local)
    return None


# ----------------------------------------------------------------------------------------- parsing

def _parse_basic(v: str):
    v = v.strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", v)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z)?", v, re.I)
    if m:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6) or 0))
        return dt.replace(tzinfo=UTC) if m.group(7) else dt
    return None


def unfold(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for line in text.split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return [x for x in out if x.strip()]


def split_line(line: str):
    """NAME;P=V;P2="a:b":VALUE -> (NAME, {P: V}, VALUE)"""
    inq, colon = False, -1
    for i, ch in enumerate(line):
        if ch == '"':
            inq = not inq
        elif ch == ":" and not inq:
            colon = i
            break
    if colon < 0:
        return None
    head, value = line[:colon], line[colon + 1:]
    parts, cur, inq = [], "", False
    for ch in head:
        if ch == '"':
            inq = not inq
        if ch == ";" and not inq:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
    return parts[0].strip().upper(), params, value


def unescape(v: str) -> str:
    return re.sub(r"\\([\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), v)


def read_calendar_text(text: str) -> tuple[list[dict], dict]:
    events, tzdefs = [], {}
    stack: list[str] = []
    cur = None
    tz_cur, tz_sub, tz_props = None, None, None
    for line in unfold(text):
        sp = split_line(line)
        if not sp:
            continue
        name, params, value = sp
        if name == "BEGIN":
            comp = value.strip().upper()
            stack.append(comp)
            if comp == "VEVENT" and len(stack) >= 1:
                cur = {"props": {}}
            elif comp == "VTIMEZONE":
                tz_cur = {"tzid": None, "defs": []}
            elif comp in ("STANDARD", "DAYLIGHT") and tz_cur is not None:
                tz_sub, tz_props = comp, {}
            continue
        if name == "END":
            comp = value.strip().upper()
            if stack and stack[-1] == comp:
                stack.pop()
            if comp == "VEVENT" and cur is not None:
                events.append(cur); cur = None
            elif comp in ("STANDARD", "DAYLIGHT") and tz_cur is not None and tz_props is not None:
                tz_cur["defs"].append((tz_sub, tz_props)); tz_sub, tz_props = None, None
            elif comp == "VTIMEZONE" and tz_cur is not None:
                if tz_cur["tzid"]:
                    tzdefs[tz_cur["tzid"]] = tz_cur["defs"]
                tz_cur = None
            continue
        top = stack[-1] if stack else ""
        if top == "VEVENT" and cur is not None:
            cur["props"].setdefault(name, []).append((params, value))
        elif top in ("STANDARD", "DAYLIGHT") and tz_props is not None:
            tz_props[name] = value
        elif top == "VTIMEZONE" and tz_cur is not None and name == "TZID":
            tz_cur["tzid"] = value.strip()
    return events, tzdefs


def find_ics(ws: str, name: str = "schedule.ics") -> str | None:
    hits = sorted(glob.glob(os.path.join(ws, name))) or sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def load(ws: str):
    p = find_ics(ws)
    if not p:
        return None, None, "schedule.ics not found"
    try:
        text = open(p, "rb").read().decode("utf-8-sig", errors="replace")
        events, tzdefs = read_calendar_text(text)
    except Exception as e:
        return None, None, f"could not parse schedule.ics: {e}"
    if not events:
        return None, None, "schedule.ics has no VEVENT"
    return events, tzdefs, ""


# ----------------------------------------------------------------------------------------- event values

def prop(ev: dict, name: str):
    v = ev["props"].get(name)
    return v[0] if v else None


def summary(ev: dict) -> str:
    p = prop(ev, "SUMMARY")
    return unescape(p[1]).strip() if p else ""


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def status(ev: dict) -> str:
    p = prop(ev, "STATUS")
    return p[1].strip().upper() if p else ""


def parse_value(params: dict, value: str, tzdefs: dict) -> dict | None:
    """-> {"kind": date|local|utc|floating, "date": date, "local": naive or None, "utc": aware UTC or None}"""
    raw = _parse_basic(value)
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return {"kind": "date", "date": raw, "local": None, "utc": None, "tz": None}
    if raw.tzinfo is not None:
        return {"kind": "utc", "date": raw.date(), "local": raw.replace(tzinfo=None), "utc": raw, "tz": "UTC"}
    if params.get("TZID"):
        u = local_to_utc(params["TZID"], raw, tzdefs)
        return {"kind": "local" if u else "unknown-tz", "date": raw.date(), "local": raw, "utc": u, "tz": params["TZID"]}
    return {"kind": "floating", "date": raw.date(), "local": raw, "utc": None, "tz": None}


def dtstart(ev: dict, tzdefs: dict):
    p = prop(ev, "DTSTART")
    return parse_value(p[0], p[1], tzdefs) if p else None


def parse_duration(v: str) -> timedelta | None:
    m = re.fullmatch(r"([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", v.strip().upper())
    if not m:
        return None
    td = timedelta(weeks=int(m.group(2) or 0), days=int(m.group(3) or 0), hours=int(m.group(4) or 0),
                   minutes=int(m.group(5) or 0), seconds=int(m.group(6) or 0))
    return -td if m.group(1) == "-" else td


def length(ev: dict, start: dict, tzdefs: dict):
    """timedelta for timed events (UTC end minus UTC start; wall-clock for floating), days for all-day."""
    p = prop(ev, "DTEND")
    if p:
        end = parse_value(p[0], p[1], tzdefs)
        if end is None:
            return None
        if start["kind"] == "date":
            return (end["date"] - start["date"]) if end["kind"] == "date" else None
        if start["utc"] is not None and end["utc"] is not None:
            return end["utc"] - start["utc"]
        if start["local"] is not None and end["local"] is not None:
            return end["local"] - start["local"]
        return None
    p = prop(ev, "DURATION")
    if p:
        return parse_duration(p[1])
    return timedelta(days=1) if start["kind"] == "date" else timedelta(0)


def parse_rrule(v: str) -> dict:
    out = {}
    for part in v.strip().split(";"):
        if "=" in part:
            k, val = part.split("=", 1)
            out[k.strip().upper()] = val.strip().upper()
    return out


def _values(ev: dict, name: str, tzdefs: dict) -> list[dict]:
    out = []
    for params, value in ev["props"].get(name, []):
        for v in value.split(","):
            pv = parse_value(params, v, tzdefs)
            if pv:
                out.append(pv)
    return out


def _same(a: dict, b: dict) -> bool:
    if a["kind"] == "date" or b["kind"] == "date":
        return a["date"] == b["date"]
    if a["utc"] is not None and b["utc"] is not None:
        return a["utc"] == b["utc"]
    return a["local"] is not None and a["local"] == b["local"]


def expand(ev: dict, tzdefs: dict, cap: int = 400) -> tuple[list[dict] | None, str]:
    """Occurrence starts of a master event before exceptions, as parse_value dicts."""
    start = dtstart(ev, tzdefs)
    if start is None:
        return None, "no readable DTSTART"
    rr = prop(ev, "RRULE")
    occ = [start]
    if rr:
        rule = parse_rrule(rr[1])
        freq = rule.get("FREQ")
        if freq not in ("WEEKLY", "DAILY"):
            return None, f"RRULE FREQ={freq} is not weekly"
        interval = int(rule.get("INTERVAL", "1") or 1)
        count = int(rule["COUNT"]) if rule.get("COUNT", "").isdigit() else None
        until = None
        if rule.get("UNTIL"):
            until = parse_value({"TZID": start["tz"]} if start["kind"] == "local" else {}, rule["UNTIL"], tzdefs)
            if until is None:
                return None, f"unreadable UNTIL {rule['UNTIL']}"
        if count is None and until is None:
            return None, "RRULE has neither COUNT nor UNTIL (repeats forever)"
        base = start["local"] if start["kind"] != "date" else datetime.combine(start["date"], datetime.min.time())
        bydays = [DAYS.index(x[-2:]) for x in rule.get("BYDAY", "").split(",") if x[-2:] in DAYS] or [base.weekday()]
        occ, n = [], 0
        step = 0
        while len(occ) < cap and step < cap:
            if freq == "WEEKLY":
                week0 = base - timedelta(days=base.weekday()) + timedelta(days=7 * interval * step)
                cands = [week0 + timedelta(days=wd) for wd in sorted(set(bydays))]
            else:
                cands = [base + timedelta(days=interval * step)]
            step += 1
            stop = False
            for c in cands:
                if c < base:
                    continue
                if start["kind"] == "date":
                    pv = {"kind": "date", "date": c.date(), "local": None, "utc": None, "tz": None}
                elif start["kind"] == "utc":
                    pv = {"kind": "utc", "date": c.date(), "local": c, "utc": c.replace(tzinfo=UTC), "tz": "UTC"}
                elif start["kind"] == "local":
                    u = local_to_utc(start["tz"], c, tzdefs)
                    pv = {"kind": "local", "date": c.date(), "local": c, "utc": u, "tz": start["tz"]}
                else:
                    pv = {"kind": start["kind"], "date": c.date(), "local": c, "utc": None, "tz": start["tz"]}
                if until is not None:
                    if until["kind"] == "date":
                        if pv["date"] > until["date"]:
                            stop = True; break
                    elif until["utc"] is not None and pv["utc"] is not None:
                        if pv["utc"] > until["utc"]:
                            stop = True; break
                    elif pv["local"] is not None and until["local"] is not None and pv["local"] > until["local"]:
                        stop = True; break
                occ.append(pv); n += 1
                if count is not None and n >= count:
                    stop = True; break
            if stop:
                break
    occ += _values(ev, "RDATE", tzdefs)
    return occ, ""


def active_occurrences(master: dict, events: list[dict], tzdefs: dict) -> tuple[list[tuple[dict, object]] | None, str]:
    """[(start, length)] after EXDATE, cancelled or moved RECURRENCE-ID overrides; empty when the master is cancelled."""
    if status(master) == "CANCELLED":
        return [], "master event is STATUS:CANCELLED"
    occ, err = expand(master, tzdefs)
    if occ is None:
        return None, err
    start = dtstart(master, tzdefs)
    ln = length(master, start, tzdefs)
    ex = _values(master, "EXDATE", tzdefs)
    occ = [o for o in occ if not any(_same(o, e) for e in ex)]
    uid = prop(master, "UID")
    uid = uid[1].strip() if uid else None
    out = [(o, ln) for o in occ]
    for ov in events:
        rid = prop(ov, "RECURRENCE-ID")
        if not rid or ov is master:
            continue
        ouid = prop(ov, "UID")
        if uid is not None and (not ouid or ouid[1].strip() != uid):
            continue
        if uid is None and norm(summary(ov)) != norm(summary(master)):
            continue
        rv = parse_value(rid[0], rid[1], tzdefs)
        if rv is None:
            continue
        keep = [(o, l) for (o, l) in out if not _same(o, rv)]
        if len(keep) == len(out):
            continue
        if status(ov) != "CANCELLED":
            s2 = dtstart(ov, tzdefs) or rv
            keep.append((s2, length(ov, s2, tzdefs)))
        out = keep
    return out, ""


def masters(events: list[dict]) -> list[dict]:
    return [e for e in events if not prop(e, "RECURRENCE-ID")]


def pick_master(events: list[dict], ref_summary: str, ref_date: date, tzdefs: dict) -> dict | None:
    want = norm(ref_summary)
    cands = [e for e in masters(events) if want and want in norm(summary(e)) and status(e) != "CANCELLED"]
    if not cands:
        return None
    def dist(e):
        s = dtstart(e, tzdefs)
        return abs((s["date"] - ref_date).days) if s else 10 ** 6
    return sorted(cands, key=dist)[0]


def load_ref(ref: str) -> list[dict]:
    import json
    return json.load(open(os.path.join(ref, "events.json")))
