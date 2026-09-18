"""Daily hours per person, keyed by (badge, date).

The key is two columns and the date may be written in any common form, which no built-in check expresses.
The person is found by a badge/employee-id column, or by name when there is none. Hours are compared within
0.02 (decimal hours; '8:30' is read as 8.5). Every reference day with hours must be present and right, and the
output must not carry hours for a (person, day) the reference does not have (last week's or next week's shifts).
"""
import csv
import glob
import io
import os
import re
from datetime import datetime

FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%b %d, %Y", "%B %d, %Y", "%a %Y-%m-%d", "%a %m/%d/%Y",
           "%Y/%m/%d", "%m-%d-%Y", "%d %b %Y", "%d %B %Y", "%A, %B %d, %Y", "%a, %b %d, %Y"]


def norm(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def parse_date(v):
    s = str(v or "").strip()
    if not s:
        return None
    s = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?(\s*[ap]m)?$", "", s, flags=re.I)
    for f in FORMATS:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    try:
        from dateutil import parser
        return parser.parse(s, fuzzy=True, dayfirst=False).date()
    except Exception:
        return None


def parse_hours(v):
    s = str(v or "").strip()
    if not s:
        return None
    m = re.fullmatch(r"(\d+):(\d{2})", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60.0
    try:
        return float(re.sub(r"[^0-9.\-]", "", s))
    except ValueError:
        return None


def read_rows(path):
    raw = open(path, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    rows = list(csv.reader(io.StringIO(raw)))
    if not rows:
        return [], []
    return [norm(h) for h in rows[0]], [r for r in rows[1:] if any(c.strip() for c in r)]


def find_output(ws):
    hits = sorted(glob.glob(os.path.join(ws, "hours_audit.csv"))) or sorted(
        glob.glob(os.path.join(ws, "**", "hours_audit.csv"), recursive=True))
    return hits[0] if hits else None


def pick(header, candidates, contains=None):
    for c in candidates:
        if c in header:
            return header.index(c)
    if contains:
        for i, h in enumerate(header):
            if any(k in h for k in contains):
                return i
    return None


def keyed(ws, ref):
    """Return (reference rows by key, output rows by key, error). Rows are dicts with hours and flag."""
    rh, rrows = read_rows(os.path.join(ref, "hours_audit.csv"))
    ref_rows = {}
    name_to_badge = {}
    for r in rrows:
        rec = dict(zip(rh, r))
        key = (rec["badge"], rec["date"])
        ref_rows[key] = {"hours": parse_hours(rec["hours"]), "flag": rec["flag"].strip()}
        name_to_badge[re.sub(r"[^a-z]", "", rec["name"].lower())] = rec["badge"]
    p = find_output(ws)
    if not p:
        return ref_rows, None, "hours_audit.csv not found"
    oh, orows = read_rows(p)
    bi = pick(oh, ["badge", "badge_no", "badge_number", "badge_id", "badge_num", "employee_id", "emp_id", "employee_no",
                   "employee_number", "id"], contains=["badge"])
    ni = pick(oh, ["name", "employee", "employee_name", "staff", "person"], contains=["name"])
    di = pick(oh, ["date", "work_date", "shift_date", "day"], contains=["date"])
    hi = pick(oh, ["hours", "hours_worked", "total_hours", "worked_hours", "hrs"], contains=["hour"])
    fi = pick(oh, ["flag", "flags", "exception", "issue", "note", "notes"], contains=["flag"])
    if di is None or hi is None or (bi is None and ni is None):
        return ref_rows, None, f"could not find person/date/hours columns in {oh}"
    out = {}
    for r in orows:
        r = r + [""] * (len(oh) - len(r))
        badge = re.sub(r"\D", "", r[bi]) if bi is not None else ""
        if not badge and ni is not None:
            nm = re.sub(r"[^a-z]", "", r[ni].lower())
            badge = name_to_badge.get(nm, "")
            if not badge:
                parts = [re.sub(r"[^a-z]", "", x) for x in re.split(r"[ ,]+", r[ni].lower()) if x.strip()]
                badge = name_to_badge.get("".join(reversed(parts)), "")
        d = parse_date(r[di])
        key = (badge, d.isoformat() if d else r[di].strip())
        prev = out.get(key)
        rec = {"hours": parse_hours(r[hi]), "flag": r[fi].strip() if fi is not None else "", "dup": prev is not None}
        out[key] = rec
    return ref_rows, out, None


def check(ws, ref):
    name = "daily hours per person"
    ref_rows, out, err = keyed(ws, ref)
    if err:
        return [{"name": name, "passed": False, "detail": err}]
    bad = []
    for key, rr in sorted(ref_rows.items()):
        if rr["flag"]:
            continue
        got = out.get(key)
        if got is None:
            bad.append(f"{key[0]} {key[1]}: missing")
        elif got["hours"] is None or abs(got["hours"] - rr["hours"]) > 0.02:
            bad.append(f"{key[0]} {key[1]}: {got['hours']} != {rr['hours']:.2f}")
    extra = [k for k, v in out.items() if k not in ref_rows and v["hours"] not in (None, 0.0)]
    detail = []
    if bad:
        detail.append(f"{len(bad)} wrong: " + "; ".join(bad[:6]))
    if extra:
        detail.append(f"hours on days that are not this week's shifts: {sorted(extra)[:6]}")
    ok = not bad and not extra
    n = sum(1 for v in ref_rows.values() if not v["flag"])
    return [{"name": name, "passed": ok, "detail": " | ".join(detail) if detail else f"{n} person-days match"}]
