#!/usr/bin/env python3
"""kpi-scorecard-page: a commercial cleaning company's August operations scorecard as one HTML page.

    python gen.py [--seed N] [--naive DIR]

Business: a commercial cleaning contractor with office and clinic contracts. Branch managers key monthly numbers
into an ops tracker (rates as fractions, three month formats, revisions as extra rows); the owner keeps targets in
a workbook and the direction of each metric in her head, or rather in a note.

Traps (each caught by a check, see task.yaml):
  * five metrics are lower-is-better per the note                          (check: page structure: met or missed)
  * a figure exactly on its target counts as met                           (check: page structure: met or missed)
  * rates are fractions in the tracker and '95%' text or 0.9 in the targets workbook; the page shows percents
                                                                           (checks: rates shown as percents; page structure: figures)
  * one metric has no target yet and gets neither met nor missed           (check: page structure: no-target metric)
  * the tracker holds June, July and August in three month formats          (check: page structure: figures)
  * a revised August figure replaces the first entry and flips its result  (checks: page structure: figures, met or missed)
  * a retired metric still has June rows in the tracker                     (check: retired carpet metric left off)
"""
from __future__ import annotations
import argparse
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# name, kind (pct | usd | num1 | count), lower is better, target
METRICS = [
    ("On-time arrival rate", "pct", False, 0.95), ("Inspection pass rate", "pct", False, 0.92),
    ("Client renewal rate", "pct", False, 0.90), ("Staff turnover", "pct", True, 0.04),
    ("Complaints per 100 visits", "num1", True, 1.5), ("Callbacks for re-cleans", "count", True, 12),
    ("Supply cost per site", "usd", True, 185.00), ("Revenue per labor hour", "usd", False, 38.50),
    ("Lost-time injuries", "count", True, 0), ("New client inquiries", "count", None, None),
]
RETIRED = "Carpet cleaning jobs"
MONTH_STYLES = {"2026-06": ["2026-06", "Jun-26", "06/2026"], "2026-07": ["2026-07", "Jul-26", "07/2026"],
                "2026-08": ["2026-08", "Aug-26", "08/2026"]}


def met(kind_lower: bool, actual: float, target: float) -> bool:
    return actual <= target + 1e-9 if kind_lower else actual >= target - 1e-9


def draw(r, kind: str, target, lower, want_met: bool | None, exact: bool = False):
    if target is None:
        return float(r.randint(14, 41))
    if exact:
        return target
    if kind == "pct":
        step = r.randint(3, max(4, min(40, int(target * 1000 * 0.5)))) / 1000
        good = target - step if lower else target + step
        bad = target + step if lower else target - step
        v = good if want_met else bad
        return round(min(max(v, 0.005), 0.999), 3)
    if kind == "usd":
        step = r.randint(150, int(target * 12)) / 100                  # up to 12% off target
        return round((target - step if lower else target + step) if want_met else (target + step if lower else target - step), 2)
    if kind == "num1":
        step = r.randint(1, 9) / 10
        return round((target - step if lower else target + step) if want_met else (target + step if lower else target - step), 1)
    step = r.randint(1, 6)
    if target == 0:
        return 0 if want_met else r.randint(1, 3)
    return (target - step if lower else target + step) if want_met else (target + step if lower else target - step)


def build(seed: int) -> dict:
    r = rng(seed)
    ms = []
    lower_names = [m[0] for m in METRICS if m[2]]
    exact_name = r.choice(["Callbacks for re-cleans", "Complaints per 100 visits"])
    revised_name = r.choice(["Inspection pass rate", "On-time arrival rate"])
    for name, kind, lower, target in METRICS:
        want = r.random() < 0.55
        if lower:
            # lower-is-better metrics must read differently under a higher-is-better reading
            want = r.random() < 0.7
        actual = draw(r, kind, target, lower, want, exact=(name == exact_name))
        m = {"name": name, "kind": kind, "lower": lower, "target": target, "actual": actual}
        if name == revised_name:
            # first entry met, revision after re-inspection misses (or the other way round)
            first_met = r.random() < 0.5
            m["first"] = draw(r, kind, target, lower, first_met)
            m["actual"] = draw(r, kind, target, lower, not first_met)
        m["met"] = None if target is None else met(bool(lower), m["actual"], target)
        ms.append(m)
    hist = {}
    for m in ms:
        for mon in ("2026-06", "2026-07"):
            if m["target"] is None:
                hist[(m["name"], mon)] = float(r.randint(10, 45))
            else:
                hist[(m["name"], mon)] = draw(r, m["kind"], m["target"], m["lower"], r.random() < 0.5)
    return {"metrics": ms, "hist": hist, "exact": exact_name, "revised": revised_name}


def acceptable(d: dict) -> bool:
    ms = [m for m in d["metrics"] if m["target"] is not None]
    n_met = sum(1 for m in ms if m["met"])
    if not 3 <= n_met <= 6:
        return False
    flips = [m for m in ms if m["lower"] and met(False, m["actual"], m["target"]) != m["met"]]
    if len(flips) < 3:
        return False
    rev = next(m for m in d["metrics"] if m["name"] == d["revised"])
    if met(False, rev["first"], rev["target"]) == rev["met"]:
        return False
    # July must not equal August for any metric (a wrong month has to show)
    for m in d["metrics"]:
        if abs(d["hist"][(m["name"], "2026-07")] - m["actual"]) < 1e-9:
            return False
    return True


def fmt_value(kind: str, v) -> str:
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "usd":
        return f"${v:,.2f}"
    if kind == "num1":
        return f"{v:.1f}"
    return f"{int(v)}"


def raw_value(r, kind: str, v) -> str:
    if kind == "pct":
        return f"{v:.3f}".rstrip("0").rstrip(".") if r.random() < 0.3 else f"{v:.3f}"
    if kind == "usd":
        return f"{v:.2f}"
    if kind == "num1":
        return f"{v:.1f}"
    return str(int(v))


def page_html(d: dict) -> str:
    ms = d["metrics"]
    scored = [m for m in ms if m["target"] is not None]
    n_met = sum(1 for m in scored if m["met"])
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           "<title>August 2026 operations scorecard</title>", "<style>",
           "body{font-family:Arial,Helvetica,sans-serif;margin:24px;color:#1b1b1b;max-width:820px}",
           "table{border-collapse:collapse;width:100%}", "th,td{padding:7px 9px;border-bottom:1px solid #ddd;text-align:left}",
           "td.n{text-align:right}", ".met{font-weight:bold;color:#1d6b33}", ".missed{font-weight:bold;color:#a12626}",
           "</style>", "</head>", "<body>", "<h1>Operations scorecard - August 2026</h1>",
           f"<p><strong>{n_met} of {len(scored)} targets met</strong> in August.</p>",
           "<table><thead><tr><th>Metric</th><th>August</th><th>Target</th><th>Better when</th><th>Result</th></tr></thead><tbody>"]
    for m in ms:
        if m["target"] is None:
            out.append(f"<tr><td>{html.escape(m['name'])}</td><td class=\"n\">{fmt_value(m['kind'], m['actual'])}</td>"
                       "<td class=\"n\">-</td><td>-</td><td>No target</td></tr>")
            continue
        res = '<span class="met">Met</span>' if m["met"] else '<span class="missed">Missed</span>'
        out.append(f"<tr><td>{html.escape(m['name'])}</td><td class=\"n\">{fmt_value(m['kind'], m['actual'])}</td>"
                   f"<td class=\"n\">{fmt_value(m['kind'], m['target'])}</td><td>{'lower' if m['lower'] else 'higher'}</td>"
                   f"<td>{res}</td></tr>")
    out += ["</tbody></table>", "</body>", "</html>", ""]
    return "\n".join(out)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    ms = d["metrics"]
    r = rng(seed + 9)
    rows = []
    branches = ["North", "South"]
    for mon in ("2026-06", "2026-07", "2026-08"):
        for m in ms:
            style = r.choice(MONTH_STYLES[mon])
            if mon == "2026-08":
                if m["name"] == d["revised"]:
                    rows.append([style, m["name"], raw_value(r, m["kind"], m["first"]), "09/02/2026", "Priya", ""])
                    rows.append([r.choice(MONTH_STYLES[mon]), m["name"], raw_value(r, m["kind"], m["actual"]), "09/08/2026",
                                 "Priya", "revised after the re-inspection of the clinic contracts"])
                else:
                    rows.append([style, m["name"], raw_value(r, m["kind"], m["actual"]), "09/03/2026", r.choice(["Priya", "Marcus"]), ""])
            else:
                entered = "07/02/2026" if mon == "2026-06" else "08/04/2026"
                rows.append([style, m["name"], raw_value(r, m["kind"], d["hist"][(m["name"], mon)]), entered,
                             r.choice(["Priya", "Marcus"]), ""])
        if mon == "2026-06":
            rows.append([r.choice(MONTH_STYLES[mon]), RETIRED, str(r.randint(30, 60)), "07/02/2026", "Marcus",
                         "last month before the Eastside sale"])
    rows.sort(key=lambda x: (x[1], x[3]))
    if naive_dir:
        write_naive(d, rows, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    write_csv(os.path.join(ws, "ops_tracker_export.csv"), ["Month", "Metric", "Value", "Entered", "Entered by", "Comment"],
              rows, bom=True, crlf=True)

    def target_cell(m):
        if m["target"] is None:
            return "TBD"
        if m["kind"] == "pct":
            return f"{m['target'] * 100:g}%" if r.random() < 0.6 else m["target"]
        return m["target"]
    write_xlsx(os.path.join(ws, "scorecard_targets_2026.xlsx"), {"Targets": {
        "merged_title": "2026 scorecard targets (approved in January)",
        "header": ["Metric", "Target", "Owner", "How we measure it"],
        "rows": [[m["name"], target_cell(m), r.choice(["Ops", "Sales", "HR", "Finance"]),
                  {"pct": "share of the month's total, from the tracker", "usd": "dollars, monthly",
                   "num1": "per 100 scheduled visits", "count": "count for the month"}[m["kind"]]] for m in ms],
        "widths": {"A": 30, "B": 12, "D": 46}}}, creator="Owner")
    lower = [m["name"] for m in ms if m["lower"]]
    write_text(os.path.join(ws, "note_from_ruth.txt"),
               "From: Ruth Achebe\nTo: you\nDate: Mon, 14 Sep 2026 07:55\nSubject: August scorecard page\n\n"
               "I want the August scorecard as a web page I can open in the Thursday branch meeting and email to "
               "the managers afterwards - one file, nothing to install, and no scripts because our email filter strips "
               "them.\n\n"
               "Every metric we track, with August's number, the target and whether we met it or missed it - "
               "just the words Met or Missed. And a line at the top with how many targets we met.\n\n"
               "Not every number is better when it goes up. Lower is better for: " + "; ".join(lower) + ". "
               "Everything else we want higher. Landing exactly on a target counts as meeting it.\n\n"
               "Show rates as percentages - the tracker stores them as decimals and the managers do not read "
               "0.943 as 94.3%.\n\n"
               "New client inquiries has no target yet (sales still has not agreed one), so show the number but no "
               "Met or Missed - put No target.\n\n"
               "If somebody revised a number in the tracker, the revision is the one that counts.\n\n"
               "Carpet cleaning went with the Eastside branch sale in June, so that line is finished - it does not "
               "belong on the scorecard any more.\n\n"
               "Ruth\n")
    scored = [m for m in ms if m["target"] is not None]
    write_json(os.path.join(ref, "expected.json"), {
        "metrics": [{"name": m["name"], "kind": m["kind"], "actual": m["actual"] * 100 if m["kind"] == "pct" else m["actual"],
                     "target": None if m["target"] is None else (m["target"] * 100 if m["kind"] == "pct" else m["target"]),
                     "met": m["met"]} for m in ms],
        "met_count": sum(1 for m in scored if m["met"]), "scored": len(scored),
    })
    write_text(os.path.join(sol, "index.html"), page_html(d))
    rev = next(m for m in ms if m["name"] == d["revised"])
    pct = [m for m in ms if m["kind"] == "pct"]
    traps = [
        "the note makes five metrics lower-is-better (turnover, complaints, callbacks, supply cost, injuries); a "
        "higher-is-better reading flips at least three results (check: page structure: met or missed)",
        f"{d['exact']} lands exactly on its target, which the note counts as met (check: page structure: met or missed)",
        "rates are fractions in the tracker (0.943) and targets are '95%' text or 0.9 numbers in the workbook; the "
        "page shows percents (checks: rates shown as percents; page structure: figures)",
        "New client inquiries has no target (TBD in the workbook) and must read No target, not Met or Missed "
        "(check: page structure: no-target metric)",
        "the tracker still carries June rows for Carpet cleaning jobs, a service sold off with a branch; it has no "
        "target and no August figure and is off the scorecard (check: retired carpet metric left off)",
        "the tracker holds June, July and August, typed '2026-08', 'Aug-26' and '08/2026'; the page is August only "
        "(checks: page structure: figures; rates shown as percents)",
        f"{rev['name']} has two August rows; the later one is a revision that changes the result "
        "(checks: page structure: figures; page structure: met or missed)",
    ]
    write_task_yaml(HERE, {
        "id": "kpi-scorecard-page", "track": "desk", "category": "tooling",
        "title": "August operations scorecard page",
        "ask": "Ruth wants the August scorecard as a web page for Thursday's branch meeting. The numbers are in the "
               "tracker export and the targets workbook, and her note explains the rest. Save it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "every metric listed", "path": "index.html",
             "phrases": [m["name"] for m in ms] + ["no target"]},
            {"type": "text_not_contains", "name": "retired carpet metric left off", "path": "index.html",
             "phrases": [RETIRED]},
            {"type": "text_numbers_present", "name": "rates shown as percents", "path": "index.html",
             "numbers": [round(m["actual"] * 100, 1) for m in pct], "rel_tol": 0.0004},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} met={[m['name'] for m in scored if m['met']]}")


def write_naive(d: dict, rows: list, out: str) -> None:
    """The obvious reading: tracker rows whose Month reads '2026-08' (else the metric's first row), figures as
    stored, every metric higher-is-better with a strict comparison, targets parsed as numbers."""
    os.makedirs(out, exist_ok=True)
    pick = {}
    for mon, name, val, *_ in rows:
        if name not in pick or (mon == "2026-08" and pick[name][0] != "2026-08"):
            pick[name] = (mon, float(val))
    parts = ["<html><body><h1>Scorecard</h1><table>"]
    for m in d["metrics"]:
        v = pick[m["name"]][1]
        if m["target"] is None:
            res = "Missed"
        else:
            res = "Met" if v > m["target"] else "Missed"
        parts.append(f"<tr><td>{m['name']}</td><td>{v}</td><td>{m['target']}</td><td>{res}</td></tr>")
    parts.append("</table></body></html>\n")
    write_text(os.path.join(out, "index.html"), "\n".join(parts))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(2000):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
