"""Custom grader for schedule-change-notices.

Reads every file under a notices/ folder in the workspace and reference/facts.json (built from gen.py's truth).

  * no notices for unchanged staff: no file name carries the first and last name of an agent whose week did not change
  * changed shifts in local time: for every change, the affected agent's notice has a unit (a line, a paragraph, or a
    heading section) naming the day (weekday or date) together with the new local start and end time; a dropped shift
    needs the day and a word saying it is off or removed. Paragraphs and sections that name another changed day of
    the same agent do not count, so one row's times cannot be read against another row's day.
  * unchanged shifts not listed: no line of a notice gives one of the agent's unchanged working days that shift's start
    time. A time belongs to the day named nearest to it on the line (the preceding day on a tie), so a changed overnight
    shift that ends on the next, unchanged day ("Thursday 24 Sep | 1:30 PM - 10:00 PM | 5:30 PM - 2:00 AM (Friday)")
    does not read as listing that day
  * time zone named: each notice names the agent's zone (Pacific/PT/PDT, Mountain/MT/MDT, Eastern/ET/EDT)

Times match 12-hour forms (5:30 PM, 5:30pm, 5:30p, 5 PM for whole hours) and 24-hour forms (17:30); a bare 9:00
without am/pm is accepted only for morning times.
"""
from __future__ import annotations

import glob
import json
import os
import re

DAYS = {"Monday": r"\bmon(day)?\b\.?", "Tuesday": r"\btue(s|sday)?\b\.?", "Wednesday": r"\bwed(nesday)?\b\.?",
        "Thursday": r"\bthu(r|rs|rsday)?\b\.?", "Friday": r"\bfri(day)?\b\.?", "Saturday": r"\bsat(urday)?\b\.?",
        "Sunday": r"\bsun(day)?\b\.?"}
ZONES = {"Pacific": r"(pacific|\bpt\b|\bpdt\b|los angeles)", "Mountain": r"(mountain|\bmt\b|\bmdt\b|boise|denver)",
         "Eastern": r"(eastern|\bet\b|\bedt\b|new york)"}
REMOVED = r"(\boff\b|cancel|remov|no longer|not (scheduled|working|on)|dropped|deleted|\bnone\b|no shift|day off|\bcut\b|\bn/?a\b|not working)"


def _day(weekday: str, iso: str) -> str:
    y, m, d = iso.split("-")
    m, d = int(m), int(d)
    return (rf"({DAYS[weekday]}|(?<!\d){m}/{d}(?!\d)|(?<!\d)0?{m}/{d:02d}(?!\d)|{iso}|\b{d}(st|nd|rd|th)?\s+sep|\bsep(t(ember)?)?\.?\s+{d}\b)")


def _time(h: int, m: int) -> str:
    h12 = h % 12 or 12
    ap = "a" if h < 12 else "p"
    pats = [rf"(?<![\d:]){h12}:{m:02d}\s*{ap}\.?(\s?m\.?)?(?![a-z])", rf"(?<![\d:]){h:02d}:{m:02d}(?!\s*[ap]\.?m?\b)(?!\d)"]
    if h < 10:
        pats.append(rf"(?<![\d:]){h}:{m:02d}(?!\s*[ap]\.?m?\b)(?!\d)" if h < 12 else "")
    if m == 0:
        pats.append(rf"(?<![\d:]){h12}\s*{ap}\.?(\s?m\.?)?(?![a-z])")
    if h == 0 and m == 0:
        pats.append(r"midnight")
    if h == 12 and m == 0:
        pats.append(r"\bnoon\b")
    return "(" + "|".join(p for p in pats if p) + ")"


# Any day named on a line: a weekday, or a date written as 9/25, 25 Sep, Sept 25 or 2026-09-25.
ANY_DAY = r"(" + "|".join(DAYS.values()) + r"|(?<![\d:/.])\d{1,2}/\d{1,2}(?:/\d{2,4})?(?![\d/])|\b\d{1,2}(st|nd|rd|th)?\s+sep\w*|\bsep(t(ember)?)?\.?\s+\d{1,2}\b|\b\d{4}-\d{2}-\d{2}\b)"


def _gives_day_time(line: str, day_pat: str, time_pat: str) -> bool:
    """The line gives `time_pat` to the day matched by `day_pat`: the day mention nearest the time is that day's."""
    own = [m.span() for m in re.finditer(day_pat, line, re.I)]
    if not own:
        return False
    spans = sorted(set(own) | {m.span() for m in re.finditer(ANY_DAY, line, re.I)})
    for tm in re.finditer(time_pat, line, re.I):
        a, b = tm.span()
        def dist(sp):
            gap = a - sp[1] if sp[1] <= a else sp[0] - b if sp[0] >= b else 0
            return (max(gap, 0), 0 if sp[1] <= a else 1)
        near = min(spans, key=dist)
        if any(near[0] < o[1] and o[0] < near[1] for o in own):
            return True
    return False


def _units(text: str) -> list[tuple[str, bool]]:
    lines = [l for l in text.splitlines() if l.strip()]
    out = [(l, True) for l in lines]
    out += [(p, False) for p in re.split(r"\n\s*\n", text) if p.strip()]
    section = []
    for l in text.splitlines():
        s = l.strip()
        if s.startswith("#") or (s.startswith("**") and s.rstrip(":").endswith("**")):
            if section:
                out.append(("\n".join(section), False))
            section = [s]
        elif s:
            section.append(s)
    if section:
        out.append(("\n".join(section), False))
    return out


def _notice_files(ws: str) -> list[str]:
    hits = [p for p in glob.glob(os.path.join(ws, "**", "*"), recursive=True)
            if os.path.isfile(p) and "/notices/" in p.replace(os.sep, "/") and "/.proto" not in p and "/.codex" not in p]
    return sorted(hits)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def check(ws: str, ref: str) -> list[dict]:
    facts = json.load(open(os.path.join(ref, "facts.json"), encoding="utf-8"))
    files = _notice_files(ws)
    if not files:
        return [{"name": "notices exist", "passed": False, "detail": "no files under a notices/ folder"}]
    by_person = {}
    for p in files:
        base = _norm(os.path.splitext(os.path.basename(p))[0])
        by_person[base] = p

    def file_for(first, last):
        for base, p in by_person.items():
            if _norm(first) in base and _norm(last) in base:
                return p
        return None

    extra = [f"{u['first']} {u['last']}" for u in facts["unchanged"] if file_for(u["first"], u["last"])]
    res = [{"name": "no notices for unchanged staff", "passed": not extra,
            "detail": f"files for unchanged agents: {extra}" if extra else f"{len(files)} notice file(s), none for unchanged agents"}]

    bad_changes, listed_unchanged, no_zone, missing = [], [], [], []
    for c in facts["changed"]:
        p = file_for(c["first"], c["last"])
        who = f"{c['first']} {c['last']}"
        if not p:
            missing.append(who)
            continue
        text = open(p, encoding="utf-8", errors="replace").read()
        units = _units(text)
        day_pats = [_day(x["weekday"], x["date"]) for x in c["changes"]]
        for x, dp in zip(c["changes"], day_pats):
            others = [o for o in day_pats if o is not dp]
            ok = False
            for u, fine in units:
                if not re.search(dp, u, re.I):
                    continue
                if not fine and any(re.search(o, u, re.I) for o in others):
                    continue
                if x["kind"] == "removed":
                    if re.search(REMOVED, u, re.I | re.M):
                        ok = True; break
                elif re.search(_time(*x["new_start"]), u, re.I) and re.search(_time(*x["new_end"]), u, re.I):
                    ok = True; break
            if not ok:
                bad_changes.append(f"{who}: {x['kind']} {x['weekday']}")
        for ud in c["unchanged_days"]:
            dp = _day(ud["weekday"], ud["date"])
            tp = _time(*ud["start"])
            if any(fine and _gives_day_time(u, dp, tp) for u, fine in units):
                listed_unchanged.append(f"{who}: {ud['weekday']}")
        if not re.search(ZONES[c["zone"]], text, re.I):
            no_zone.append(who)
    res.append({"name": "changed shifts in local time", "passed": not bad_changes and not missing,
                "detail": (f"missing notices {missing}; " if missing else "") + (f"not found: {bad_changes}" if bad_changes else "every change found with its local day and times")})
    res.append({"name": "unchanged shifts not listed", "passed": not listed_unchanged,
                "detail": f"unchanged shifts listed: {listed_unchanged}" if listed_unchanged else "none listed"})
    res.append({"name": "time zone named", "passed": not no_zone and not missing,
                "detail": f"no zone in: {no_zone}" if no_zone else "every notice names its zone"})
    return res
