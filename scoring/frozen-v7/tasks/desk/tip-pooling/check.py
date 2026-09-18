"""Tip pool shares per person per shift, keyed on (date, shift, employee).

No built-in check keys on three columns, so this one does. It accepts the date in the common written forms, the shift as
any word starting with L (lunch) or D (dinner), and the employee as "First Last" or "Last, First". It reports four
things and passes only when all hold:
  rows   - exactly one row for every person who shares in every shift, and nobody else
  shares - every share equals the reference to the cent (the owner's memo prescribes the rounding)
  ties   - the shares in each shift add up to that shift's pool to the cent
  hours  - hours per person per shift within 0.02
"""
import glob
import json
import os
import re
import sys
from datetime import datetime


def _bench():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, os.path.join(root, "bench"))
    import grade  # noqa: E402
    return grade


def _date(v):
    s = str(v).strip()
    s = re.sub(r"\s+00:00:00$", "", s)
    s = re.sub(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+", "", s, flags=re.I)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%b %d %Y", "%b %d, %Y", "%B %d, %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return s.lower()


def _shift(v):
    s = str(v).strip().lower()
    return "lunch" if s.startswith("l") else "dinner" if s.startswith("d") else s


def _person(v):
    return " ".join(sorted(re.findall(r"[a-z0-9]+", str(v).lower())))


def _num(v):
    try:
        return float(re.sub(r"[^0-9.\-]", "", str(v)))
    except ValueError:
        return None


def check(ws, ref):
    grade = _bench()
    hits = sorted(glob.glob(os.path.join(ws, "tip_distribution.csv"))) or sorted(
        glob.glob(os.path.join(ws, "**", "tip_distribution.csv"), recursive=True))
    if not hits:
        return [{"name": "tip distribution", "passed": False, "detail": "tip_distribution.csv not found"}]
    try:
        got = grade.read_table(hits[0])
        need = ["date", "shift", "employee", "hours", "tip_share"]
        missing = [c for c in need if c not in got.columns]
        if missing:
            return [{"name": "tip distribution", "passed": False, "detail": f"missing columns {missing}"}]
        want = grade.read_table(os.path.join(ref, "tip_distribution.csv"))
        pools = json.load(open(os.path.join(ref, "notes.json")))["pools"]
    except Exception as e:
        return [{"name": "tip distribution", "passed": False, "detail": f"unreadable: {e}"}]

    def keyed(df):
        out = {}
        for row in df.to_dict("records"):
            out.setdefault((_date(row["date"]), _shift(row["shift"]), _person(row["employee"])), []).append(row)
        return out

    g, w = keyed(got), keyed(want)
    dupes = [k for k, v in g.items() if len(v) > 1]
    miss = sorted(set(w) - set(g))
    extra = sorted(set(g) - set(w))
    res = [{"name": "rows", "passed": not miss and not extra and not dupes,
            "detail": f"{len(g)} keys / {len(w)} expected; missing={miss[:4]} extra={extra[:4]} duplicated={dupes[:3]}"}]
    bad_share = [k for k in w if k in g and (_num(g[k][0]["tip_share"]) is None or abs(_num(g[k][0]["tip_share"]) - float(w[k][0]["tip_share"])) > 0.005)]
    res.append({"name": "shares", "passed": not bad_share and not miss,
                "detail": f"{len(w) - len(bad_share) - len(miss)}/{len(w)} shares right to the cent; wrong={bad_share[:4]}"})
    sums = {}
    for (dd, sh, _), rows in g.items():
        for row in rows:
            sums[(dd, sh)] = sums.get((dd, sh), 0.0) + (_num(row["tip_share"]) or 0.0)
    bad_tie = []
    for key, pool in pools.items():
        dd, sh = key.split(" ")
        if abs(sums.get((dd, sh), 0.0) - float(pool)) > 0.005:
            bad_tie.append(f"{key}: {sums.get((dd, sh), 0.0):.2f} vs {float(pool):.2f}")
    res.append({"name": "ties", "passed": not bad_tie, "detail": f"{len(pools) - len(bad_tie)}/{len(pools)} shifts tie to the pool; {bad_tie[:3]}"})
    bad_hours = [k for k in w if k in g and (_num(g[k][0]["hours"]) is None or abs(_num(g[k][0]["hours"]) - float(w[k][0]["hours"])) > 0.02)]
    res.append({"name": "hours", "passed": not bad_hours and not miss, "detail": f"wrong={bad_hours[:4]}"})
    return res
