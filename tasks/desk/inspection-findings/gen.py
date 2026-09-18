#!/usr/bin/env python3
"""inspection-findings: six inspection reports across three child care centers -> one row per open finding.

    python gen.py [--seed N] [--naive DIR]

Business: Little Acorn Early Learning runs three centers (Maple Street, Riverside, Hilltop). The operations director keeps one
corrective-action list of every open inspection finding with a severity on the company's scale and a due date.

Traps (each caught by a check, see task.yaml):
  * severity words differ by inspector: Imminent hazard / Serious / Minor (fire), High / Medium / Low (licensing), Priority /
    Priority Foundation / Core (health), Priority 1 / 2 / 3 (insurer); mapped by the policy note, where the health "Priority"
    is high but the insurer's "Priority 2" is medium                                  (check: severity)
  * repeated findings: the fire re-inspection lists an August item as NOT CORRECTED with a raised severity and a new date,
    and the insurer's audit repeats a March recommendation from a report not in the folder; one row each, keyed to the
    original report, severity and due date from the latest                             (checks: one row per open finding; severity; due dates)
  * closed items: corrected on site (COS), corrected during inspection, three August fire items closed on the re-inspection,
    and last year's Hilltop fire report where everything is closed                     (checks: one row per open finding; row count)
  * due dates given as periods ("within 14 days", "immediately") or by a footnote rule (Core items within 90 days) (check: due dates)
  * the insurer's playground audit is an image-only scan                               (checks: descriptions; due dates)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["finding_ref", "site", "source", "inspection_date", "description", "severity", "due_date"]
SEV = {"Imminent hazard": "high", "Serious": "medium", "Minor": "low", "High": "high", "Medium": "medium", "Low": "low",
       "Priority": "high", "Priority Foundation": "medium", "Core": "low", "Priority 1": "high", "Priority 2": "medium", "Priority 3": "low"}


def build(seed: int) -> dict:
    r = rng(seed)
    D = lambda m, d: date(2026, m, d)
    fire1 = D(8, r.randint(3, 6))
    fire2 = D(9, r.randint(1, 3))
    lic = D(8, r.randint(18, 21))
    health = D(8, r.randint(25, 28))
    ins = D(9, r.randint(8, 10))
    ins_prev = D(3, r.randint(9, 13))
    n_fire1, n_fire2 = f"FM-26-{r.randint(400, 440):04d}", f"FM-26-{r.randint(470, 499):04d}"
    n_lic = f"LIC-2026-{r.randint(11000, 11999)}"
    n_hd = f"HD-{r.randint(77000, 77999)}"
    n_ins, n_ins_prev = f"LC-{r.randint(5500, 5599)}", f"LC-{r.randint(5300, 5399)}"
    F = []

    def f(ref, site, source, dt, desc, sev_word, due, status, **kw):
        F.append({"ref": ref, "site": site, "source": source, "date": dt, "desc": desc, "sev_word": sev_word, "due": due, "status": status, **kw})
    d1, d2, d3 = r.choice([10, 14]), r.choice([5, 7]), r.choice([30, 45])
    # fire inspection, Maple Street
    f(f"{n_fire1}-1", "Maple Street", "fire", fire1, "Kitchen fire extinguisher past its annual inspection tag", "Serious", fire1 + timedelta(d1), "closed_later", period=f"within {d1} days")
    f(f"{n_fire1}-2", "Maple Street", "fire", fire1, "Exit sign over the rear door not illuminated", "Serious", fire1 + timedelta(d2), "closed_later", period=f"within {d2} days")
    f(f"{n_fire1}-3", "Maple Street", "fire", fire1, "Extension cord used as permanent wiring in Toddler Room 2", "Minor", fire1 + timedelta(d3), "repeat", period=f"within {d3} days")
    f(f"{n_fire1}-4", "Maple Street", "fire", fire1, "Storage within 18 inches of sprinkler heads in the supply closet", "Minor", None, "cos", period="Corrected on site")
    f(f"{n_fire1}-5", "Maple Street", "fire", fire1, "Fire alarm control panel showing a trouble signal", "Imminent hazard", fire1, "closed_later", period="immediately")
    rep = F[2]
    rep["sev_word_latest"], rep["due_latest"] = "Serious", fire2 + timedelta(14)
    f(f"{n_fire2}-1", "Maple Street", "fire", fire2, "Fire door to the east hallway held open with a door wedge", "Serious", fire2 + timedelta(7), "open", period="within 7 days")
    # licensing, Riverside
    f(f"{n_lic}-1", "Riverside", "licensing", lic, "Lead teacher's pediatric first aid and CPR certification expired", "High", lic + timedelta(14), "open", printed_due=True)
    f(f"{n_lic}-2", "Riverside", "licensing", lic, "Medication log missing parent authorization for one child", "Medium", lic + timedelta(30), "open", printed_due=True)
    f(f"{n_lic}-3", "Riverside", "licensing", lic, "Emergency contact cards incomplete for two children", "Low", None, "during", printed_due=True)
    f(f"{n_lic}-4", "Riverside", "licensing", lic, "Cot spacing less than 18 inches in the Infant Room", "Low", lic + timedelta(60), "open", printed_due=True)
    f(f"{n_lic}-5", "Riverside", "licensing", lic, "Diapering station sanitizer below required concentration", "High", lic, "during", printed_due=True)
    # health, Hilltop kitchen
    f(f"{n_hd}-1", "Hilltop", "health", health, "Milk in classroom refrigerator held at 47F", "Priority", None, "cos")
    f(f"{n_hd}-2", "Hilltop", "health", health, "No thermometer in the kitchen reach-in cooler", "Priority Foundation", health + timedelta(10), "open", period="Correct within 10 days")
    f(f"{n_hd}-3", "Hilltop", "health", health, "Kitchen hand sink blocked by a cart", "Priority Foundation", None, "cos")
    f(f"{n_hd}-4", "Hilltop", "health", health, "Stained ceiling tile above dry storage", "Core", health + timedelta(90), "open", period="See note")
    f(f"{n_hd}-5", "Hilltop", "health", health, "Food handler card not on file for the assistant cook", "Core", health + timedelta(90), "open", period="See note")
    # insurer playground audit, Riverside (scanned)
    f(f"{n_ins}-R-1", "Riverside", "insurance", ins, "Mulch under climber only 4 in deep, 9 in required", "Priority 1", ins + timedelta(30), "open", period="within 30 days")
    f(f"{n_ins}-R-2", "Riverside", "insurance", ins, "Toddler yard gate latch does not self-close", "Priority 2", ins + timedelta(14), "open", period="within 14 days")
    f(f"{n_ins}-R-3", "Riverside", "insurance", ins, "Swing hanger bolt missing its locking nut", "Priority 1", ins + timedelta(7), "open", period="within 7 days")
    f(f"{n_ins_prev}-R-4", "Riverside", "insurance", ins_prev, "Sand box has no cover", "Priority 3", ins + timedelta(60), "open", period="within 60 days", repeat_in=n_ins)
    rows = []
    for x in F:
        if x["status"] not in ("open", "repeat"):
            continue
        sev = SEV[x.get("sev_word_latest", x["sev_word"])]
        due = x.get("due_latest", x["due"])
        rows.append([x["ref"], x["site"], x["source"], x["date"].isoformat(), x["desc"], sev, due.isoformat()])
    return {"F": F, "rows": rows, "n": {"fire1": n_fire1, "fire2": n_fire2, "lic": n_lic, "hd": n_hd, "ins": n_ins, "ins_prev": n_ins_prev},
            "dates": {"fire1": fire1, "fire2": fire2, "lic": lic, "health": health, "ins": ins, "ins_prev": ins_prev}}


def render(ws: str, d: dict, seed: int) -> dict:
    P = os.path.join(ws, "inspection_reports")
    os.makedirs(P, exist_ok=True)
    F = {x["ref"]: x for x in d["F"]}
    n, dt = d["n"], d["dates"]
    files = {}
    by = lambda prefix: [x for x in d["F"] if x["ref"].startswith(prefix + "-")]
    # fire inspection, Helvetica
    rows = [["Item", "Violation", "Classification", "Correction required"]]
    for x in by(n["fire1"]):
        rows.append([x["ref"].rsplit("-", 1)[1], x["desc"], x["sev_word"], x["period"]])
    files["fire1"] = f"FireInspection_MapleStreet_{n['fire1']}.pdf"
    write_pdf_document(os.path.join(P, files["fire1"]), [
        ("title", "Fire Safety Inspection Report"), ("small", "Cedar Falls Fire Prevention Bureau - 220 Division St"), ("hr", None),
        ("kv", [("Report no.", n["fire1"]), ("Occupancy", "Little Acorn Early Learning - Maple Street (E occupancy, day care)"),
                ("Date of inspection", dt["fire1"].strftime("%B %-d, %Y")), ("Inspector", "Capt. R. Delgado")]), ("spacer", 8),
        ("table", rows, {"col_widths": [35, 250, 90, 110], "grid": True, "shade_header": True}), ("spacer", 6),
        ("small", "Correction periods run from the date of inspection. A re-inspection will be scheduled after the longest correction period."),
        ("small", "Classifications: Imminent hazard - correct immediately; Serious; Minor.")], pagesize="letter", font="Helvetica", base_size=9)
    # fire re-inspection, Helvetica, narrative list
    rep = [x for x in by(n["fire1"]) if x["status"] in ("closed_later", "repeat")]
    blocks = [("title", "Re-inspection Report"), ("small", "Cedar Falls Fire Prevention Bureau"), ("hr", None),
              ("p", f"Report no. {n['fire2']} - Little Acorn Early Learning, Maple Street - re-inspection of {n['fire1']} - "
                    f"{dt['fire2'].strftime('%m/%d/%Y')}"), ("h", f"Items from report {n['fire1']}")]
    for x in rep:
        item = x["ref"].rsplit("-", 1)[1]
        if x["status"] == "closed_later":
            blocks.append(("p", f"Item {item} - {x['desc']}: <b>Corrected. CLOSED.</b>"))
        else:
            blocks.append(("p", f"Item {item} - {x['desc']}: <b>NOT CORRECTED - REPEAT VIOLATION.</b> Classification raised to "
                                f"{x['sev_word_latest']}. Correct by {x['due_latest'].strftime('%m/%d/%Y')}."))
    blocks.append(("h", "New violations"))
    for x in by(n["fire2"]):
        blocks.append(("p", f"Item {x['ref'].rsplit('-', 1)[1]} - {x['desc']} - {x['sev_word']} - correct {x['period']}."))
    blocks.append(("small", "Item 4 of the original report was corrected on site and is not re-inspected."))
    files["fire2"] = f"FireReinspection_MapleStreet_{n['fire2']}.pdf"
    write_pdf_document(os.path.join(P, files["fire2"]), blocks, pagesize="letter", font="Helvetica", base_size=10)
    # licensing, Times, A4, printed due dates and statuses
    rows = [["No.", "Rule", "Finding", "Risk level", "Corrective action due", "Status"]]
    rules = ["102.21(c)", "102.47(a)", "102.18(b)", "102.60(d)", "102.33(f)"]
    for x, rule in zip(by(n["lic"]), rules):
        status = "Corrected during inspection" if x["status"] == "during" else "Open"
        due = x["due"].strftime("%m/%d/%Y") if x["status"] != "during" else "-"
        rows.append([x["ref"].rsplit("-", 1)[1], rule, x["desc"], x["sev_word"], due, status])
    files["lic"] = f"Licensing_Riverside_{dt['lic'].strftime('%Y%m%d')}.pdf"
    write_pdf_document(os.path.join(P, files["lic"]), [
        ("right", "Department of Early Learning<br/>Child Care Licensing Division"), ("spacer", 4), ("title", "Monitoring Inspection"),
        ("p", f"Inspection number {n['lic']}<br/>Facility: Little Acorn Early Learning - Riverside<br/>Visit date: {dt['lic'].strftime('%d %B %Y')}"),
        ("spacer", 6), ("table", rows, {"col_widths": [28, 55, 190, 50, 70, 80], "grid": True}), ("spacer", 6),
        ("small", "Risk levels: High, Medium, Low. Items corrected during the inspection are recorded for history only.")],
        pagesize="a4", font="Times-Roman", base_size=9.5)
    # health, Courier
    rows = [["ITEM", "OBSERVATION", "TYPE", "CORRECTION"]]
    for x in by(n["hd"]):
        corr = "COS" if x["status"] == "cos" else x["period"].upper()
        rows.append([x["ref"].rsplit("-", 1)[1], x["desc"].upper(), x["sev_word"].upper(), corr])
    files["hd"] = f"HealthDept_Hilltop_kitchen_{n['hd']}.pdf"
    write_pdf_document(os.path.join(P, files["hd"]), [
        ("h", "COUNTY ENVIRONMENTAL HEALTH - FOOD ESTABLISHMENT INSPECTION"),
        ("p", f"INSPECTION # {n['hd']}<br/>ESTABLISHMENT LITTLE ACORN EARLY LEARNING - HILLTOP (KITCHEN)<br/>DATE {dt['health'].strftime('%m-%d-%Y')}<br/>"
              "TYPE ROUTINE"), ("spacer", 6),
        ("table", rows, {"col_widths": [40, 260, 110, 110], "grid": True}), ("spacer", 6),
        ("small", "COS = CORRECTED ON SITE DURING INSPECTION. NOTE: CORE VIOLATIONS MUST BE CORRECTED WITHIN 90 CALENDAR DAYS OF THE INSPECTION."),
        ("small", "PRIORITY AND PRIORITY FOUNDATION VIOLATIONS NOT CORRECTED ON SITE MUST BE CORRECTED WITHIN THE TIME STATED.")],
        pagesize="letter", font="Courier", base_size=8.5)
    # insurer audit, scanned
    L = ["HEARTHSTONE MUTUAL - LOSS CONTROL", "PLAYGROUND SAFETY AUDIT", "", f"REPORT {n['ins']}", "INSURED LITTLE ACORN EARLY LEARNING",
         "LOCATION RIVERSIDE CENTER", f"SURVEY DATE {dt['ins'].strftime('%m/%d/%Y')}", "", "RECOMMENDATIONS", ""]
    for x in by(n["ins"]):
        L += [f"R-{x['ref'].rsplit('-', 1)[1]}  {x['desc']}", f"    {x['sev_word'].upper()}  COMPLETE {x['period'].upper()}", ""]
    old = F[f"{n['ins_prev']}-R-4"]
    L += [f"REPEAT OF {n['ins_prev']} R-4 ({dt['ins_prev'].strftime('%m/%d/%Y')})", f"    {old['desc']}", f"    {old['sev_word'].upper()}  COMPLETE {old['period'].upper()}",
          "", "COMPLETION PERIODS RUN FROM THE SURVEY DATE"]
    files["ins"] = f"scan_playground_audit_riverside.pdf"
    write_scan_pdf(os.path.join(P, files["ins"]), L, font_size=30, skew_deg=0.4, noise=400, seed=seed * 41 + 8)
    # last year's Hilltop fire report, all closed
    files["old"] = "FireInspection_Hilltop_2025.pdf"
    write_pdf_document(os.path.join(P, files["old"]), [
        ("title", "Fire Safety Inspection Report"), ("small", "Cedar Falls Fire Prevention Bureau"), ("hr", None),
        ("kv", [("Report no.", "FM-25-0918"), ("Occupancy", "Little Acorn Early Learning - Hilltop"), ("Date of inspection", "October 14, 2025")]),
        ("spacer", 6),
        ("table", [["Item", "Violation", "Classification", "Status"], ["1", "Missing fire drill log entries for August and September", "Minor", "Closed 11/02/2025"],
                   ["2", "Blocked access to electrical panel in storage room", "Serious", "Closed 10/21/2025"]],
         {"col_widths": [35, 260, 90, 100], "grid": True, "shade_header": True})], pagesize="letter", font="Helvetica", base_size=9)
    return files


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    files = render(ws, d, seed)
    write_text(os.path.join(ws, "corrective_action_policy.txt"),
               "LITTLE ACORN EARLY LEARNING - CORRECTIVE ACTION LIST\n\n"
               "Every open finding from any inspection (fire, licensing, health, insurance) goes on the list, one row per finding.\n\n"
               "finding_ref      the report number and the item number where the finding was FIRST reported, joined with a hyphen\n"
               "                 (FM-26-0000-3, LC-0000-R-2). A finding that comes back on a later report keeps its first reference.\n"
               "site             Maple Street, Riverside or Hilltop\n"
               "source           fire, licensing, health or insurance\n"
               "inspection_date  date of the inspection where it was first reported, YYYY-MM-DD\n"
               "description      as the inspector wrote it\n"
               "severity         high, medium or low on our scale:\n"
               "                   high   - imminent hazard, high risk, health code Priority, insurer Priority 1\n"
               "                   medium - serious, medium risk, health code Priority Foundation, insurer Priority 2\n"
               "                   low    - minor, low risk, health code Core, insurer Priority 3\n"
               "                 If a later report changes the classification, use the latest one.\n"
               "due_date         the date it must be corrected by, YYYY-MM-DD. Work it out when the report gives a number of days;\n"
               "                 'immediately' means the inspection date. A later report's new date replaces the old one.\n\n"
               "Anything corrected on site, corrected during the inspection, or closed on a later report is not open and stays off the list.\n")
    write_csv(os.path.join(ref, "findings.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "findings.csv"), HEADER, d["rows"])
    n = d["n"]
    Fm = {x["ref"]: x for x in d["F"]}
    ins = [x for x in d["F"] if x["source"] == "insurance"]
    figs = [x for y in ins for x in (y["desc"], y["sev_word"].upper(), f"COMPLETE {y['period'].upper()}")] + [n["ins"], d["dates"]["ins"].strftime("%m/%d/%Y"),
            f"REPEAT OF {n['ins_prev']} R-4 ({d['dates']['ins_prev'].strftime('%m/%d/%Y')})"] + [f"R-{y['ref'].rsplit('-', 1)[1]}" for y in ins if y["ref"].startswith(n["ins"])]
    write_json(os.path.join(ref, "notes.json"), {"files": files, "closed": [x["ref"] for x in d["F"] if x["status"] not in ("open", "repeat")],
                                                  "scan_figures": {f"inspection_reports/{files['ins']}": figs}})
    P = "findings.csv"
    rep_fire, rep_ins = f"{n['fire1']}-3", f"{n['ins_prev']}-R-4"
    periods = [x["ref"] for x in d["F"] if x["status"] == "open" and x.get("period")]
    write_task_yaml(HERE, {
        "id": "inspection-findings", "track": "desk", "category": "extraction",
        "title": "Open findings from this season's inspection reports",
        "ask": ("Please go through the inspection reports in the folder and build our corrective action list as findings.csv. "
                "The policy file explains how we track them.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "severity words differ by inspector: Imminent hazard/Serious/Minor on the fire reports, High/Medium/Low on licensing, "
            "Priority/Priority Foundation/Core on the health report and Priority 1/2/3 on the insurer's audit; the policy maps them, so the "
            "health report's 'Priority' is high while the insurer's 'Priority 2' is medium (check: severity)",
            f"the fire re-inspection {n['fire2']} lists item 3 of {n['fire1']} as NOT CORRECTED with its classification raised from Minor to Serious "
            f"and a new correction date, and the insurer's audit repeats recommendation R-4 of {n['ins_prev']}, a March report not in the folder; "
            f"each is one row keyed {rep_fire} and {rep_ins}, with the first inspection date and the latest severity and due date "
            "(checks: one row per open finding; site, source and date; severity; due dates)",
            "closed items stay off the list: the August fire report's item 4 corrected on site and its items 1, 2 and 5 marked 'Corrected. CLOSED.' "
            "on the re-inspection, two licensing items corrected during the inspection, two health items marked COS, and last year's Hilltop "
            "fire report whose items are all closed (checks: one row per open finding; row count)",
            "due dates are printed as periods ('within 14 days', 'COMPLETE WITHIN 30 DAYS'), as 'immediately', or only by the health report's "
            "footnote that Core violations are due within 90 calendar days (check: due dates)",
            "the insurer's playground audit is an image-only scan (checks: descriptions; due dates)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per open finding", "path": P, "column": "finding_ref", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "site, source and date", "path": P, "ref": P, "key": "finding_ref",
             "columns": ["site", "source", "inspection_date"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": [rep_fire, rep_ins]},
            {"type": "csv_values_match", "name": "descriptions", "path": P, "ref": P, "key": "finding_ref", "columns": ["description"],
             "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": [x["ref"] for x in ins]},
            {"type": "csv_values_match", "name": "severity", "path": P, "ref": P, "key": "finding_ref", "columns": ["severity"], "min_accuracy": 1.0,
             "must_match_keys": [rep_fire] + [x["ref"] for x in d["F"] if x["status"] == "open" and x["source"] in ("health", "insurance")]},
            {"type": "csv_values_match", "name": "due dates", "path": P, "ref": P, "key": "finding_ref", "columns": ["due_date"], "min_accuracy": 1.0,
             "must_match_keys": [rep_fire, rep_ins] + periods},
        ],
    })
    print(f"seed={seed} open={len(d['rows'])} printed={len(d['F'])}")


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: every item on every report except last year's (closed statuses ignored), the repeat keyed to the
    report it appears on, the inspector's severity word lower-cased, due dates only where a date is printed."""
    os.makedirs(out, exist_ok=True)
    rows = []
    n = d["n"]
    for x in d["F"]:
        ref = x["ref"]
        if x.get("repeat_in"):
            ref = f"{x['repeat_in']}-R-4"
        due = x["due"].isoformat() if x.get("printed_due") and x["due"] else ""
        rows.append([ref, x["site"], x["source"], x["date"].isoformat(), x["desc"], x["sev_word"].lower(), due])
    rep = [x for x in d["F"] if x["status"] == "repeat"][0]
    rows.append([f"{n['fire2']}-3", rep["site"], "fire", d["dates"]["fire2"].isoformat(), rep["desc"], "serious", rep["due_latest"].isoformat()])
    write_csv(os.path.join(out, "findings.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, build(a.seed), a.naive)
