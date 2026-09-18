#!/usr/bin/env python3
"""superbill-codes: six superbills and therapy notes from one clinic week -> one charge-entry line per billed code.

    python gen.py [--seed N] [--naive DIR]

Business: Summit Ridge Sports Medicine and Physical Therapy. The billing coordinator keys every superbill into the charge
entry import: one row per billed procedure code with its modifiers, units and the charge from the practice fee schedule.

Traps (each caught by a check, see task.yaml):
  * modifiers are written four ways: hyphen-joined to the code ("99214-25"), in a Mod column, after the code on the scan
    ("GP KX"), and once at the top of the therapy note for every code below it           (checks: procedure codes; modifiers)
  * units: the therapy note prints minutes beside units, the typed flowsheet writes "x2", the checkbox form leaves Units
    blank for single-unit codes; the charge is units times the fee                       (checks: units; charges)
  * one line on the typed flowsheet is marked VOID (entered in error) and is not billed  (checks: one row per billed line; row count)
  * the checkbox form lists every common code with a fee; only the rows marked X were done (check: one row per billed line)
  * the forms still print last year's fees; the charge comes from the schedule in effect on the date of service, and one
    late superbill from 29 June falls under the old schedule                            (check: charges)
  * the Thursday therapy visit is an image-only scan                                     (checks: modifiers; units)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["line_ref", "encounter_no", "account_no", "service_date", "cpt_code", "modifiers", "units", "charge"]
# code: (description, fee from 2025-07-01, fee from 2026-07-01)
CODES = {
    "99202": ("New patient visit, straightforward", 120, 125), "99203": ("New patient visit, low", 175, 182),
    "99212": ("Established patient, straightforward", 85, 88), "99213": ("Established patient, low", 130, 135),
    "99214": ("Established patient, moderate", 190, 198), "20550": ("Injection, tendon sheath or ligament", 95, 99),
    "20610": ("Arthrocentesis/injection, major joint", 145, 152), "20611": ("Major joint injection with ultrasound", 210, 219),
    "73560": ("X-ray knee, 1 or 2 views", 68, 72), "73030": ("X-ray shoulder, 2 views", 62, 65), "29530": ("Strapping, knee", 38, 40),
    "97161": ("PT evaluation, low complexity", 150, 158), "97162": ("PT evaluation, moderate complexity", 165, 172),
    "97110": ("Therapeutic exercise, each 15 min", 42, 44), "97140": ("Manual therapy, each 15 min", 40, 42),
    "97112": ("Neuromuscular re-education, each 15 min", 45, 47), "97530": ("Therapeutic activities, each 15 min", 48, 50),
    "97035": ("Ultrasound, each 15 min", 22, 23), "97750": ("Physical performance test, each 15 min", 55, 57),
}
NEW_FROM = date(2026, 7, 1)
MD_FORM = ["99202", "99203", "99212", "99213", "99214", "20550", "20610", "20611", "73560", "73030", "29530"]


def fee(code: str, dos: date) -> float:
    return float(CODES[code][2] if dos >= NEW_FROM else CODES[code][1])


def build(seed: int) -> dict:
    r = rng(seed)
    pts = people(r, 6)
    encs = sorted(r.sample(range(40100, 40999), 6))
    accts = [f"A{n}" for n in r.sample(range(10200, 18999), 6)]
    side = lambda: r.choice(["RT", "LT"])
    E = []
    # S1 checkbox physician form, Mod and Units columns, blank units = 1
    s1 = side()
    E.append({"key": "S1", "enc": str(encs[0]), "acct": accts[0], "pt": pts[0], "dos": date(2026, 9, 8), "provider": "Dr. Helen Park",
              "lines": [("99214", ["25"], 1), ("20610", [s1], 1), ("73560", [s1], 1)]})
    # S2 checkbox list in prose lines, modifiers hyphen-joined
    E.append({"key": "S2", "enc": str(encs[1]), "acct": accts[1], "pt": pts[1], "dos": date(2026, 9, 9), "provider": "Dr. Helen Park",
              "lines": [("99203", [], 1), ("20550", [side()], 1), ("29530", [], r.choice([1, 2]))]})
    # S3 therapy daily note, GP stated once at the top, minutes and units
    m = [r.choice([40, 44]), r.choice([18, 22]), r.choice([25, 28])]  # 83-94 timed minutes = 6 units
    E.append({"key": "S3", "enc": str(encs[2]), "acct": accts[2], "pt": pts[2], "dos": date(2026, 9, 9), "provider": "Marcus Lee, PT, DPT",
              "lines": [("97110", ["GP"], 3), ("97140", ["GP"], 1), ("97112", ["GP"], 2)], "minutes": m})
    # S4 typed flowsheet, hyphen modifiers, x2, one VOID line
    E.append({"key": "S4", "enc": str(encs[3]), "acct": accts[3], "pt": pts[3], "dos": date(2026, 9, 10), "provider": "Marcus Lee, PT, DPT",
              "lines": [("97162", ["GP"], 1), ("97110", ["GP"], 2), ("97140", ["GP", "59"], r.choice([1, 2]))], "void": ("97530", ["GP"], 2)})
    # S5 late June superbill, old fee schedule
    E.append({"key": "S5", "enc": str(encs[4] - 700), "acct": accts[4], "pt": pts[4], "dos": date(2026, 6, 29), "provider": "Dr. Omar Haddad",
              "lines": [("99213", ["25"], 1), ("20611", [side()], 1)]})
    # S6 scanned therapy visit
    E.append({"key": "S6", "enc": str(encs[5]), "acct": accts[5], "pt": pts[5], "dos": date(2026, 9, 10), "provider": "Dana Cruz, PTA",
              "lines": [("97110", ["GP", "KX"], r.choice([2, 3])), ("97530", ["GP", "KX"], 2), ("97035", ["GP"], 1)]})
    rows = []
    for e in E:
        for code, mods, units in e["lines"]:
            rows.append([f"{e['enc']}-{code}", e["enc"], e["acct"], e["dos"].isoformat(), code, " ".join(mods), str(units),
                         f"{units * fee(code, e['dos']):.2f}"])
    return {"encs": E, "rows": rows}


def render(ws: str, d: dict, seed: int) -> dict:
    E = {e["key"]: e for e in d["encs"]}
    P = os.path.join(ws, "superbills_week_2026-09-07")
    os.makedirs(P, exist_ok=True)
    files = {}
    head = "SUMMIT RIDGE SPORTS MEDICINE &amp; PHYSICAL THERAPY"
    # S1: checkbox table, every common code listed with the printed (old) fee
    e = E["S1"]
    marked = {c: (mods, u) for c, mods, u in e["lines"]}
    rows = [["", "CPT", "Description", "Fee", "Units", "Mod"]]
    for c in MD_FORM:
        if c in marked:
            mods, u = marked[c]
            rows.append(["X", c, CODES[c][0], f"{CODES[c][1]:.2f}", "" if u == 1 else u, " ".join(mods)])
        else:
            rows.append(["", c, CODES[c][0], f"{CODES[c][1]:.2f}", "", ""])
    files["S1"] = f"superbill_{e['enc']}.pdf"
    write_pdf_document(os.path.join(P, files["S1"]), [
        ("title", "Superbill"), ("p", head + "<br/>1180 Ridgeview Pkwy, Boulder CO 80302  |  Tax ID on file"), ("hr", None),
        ("kv", [("Patient", f"{e['pt'][1]}, {e['pt'][0]}"), ("Account #", e["acct"]), ("Encounter #", e["enc"]),
                ("Date of service", e["dos"].strftime("%m/%d/%Y")), ("Rendering provider", e["provider"])]), ("spacer", 8),
        ("table", rows, {"col_widths": [22, 45, 250, 55, 45, 45], "grid": True, "shade_header": True}), ("spacer", 6),
        ("small", "Mark X for each service performed. Units blank = 1. Fees shown are the practice fee schedule effective 07/01/2025."),
        ("spacer", 10), ("p", "Provider signature: ______________________")], pagesize="letter", font="Helvetica", base_size=9)
    # S2: checkbox lines as prose, Times, modifiers hyphen-joined to the code
    e = E["S2"]
    marked = {c: (mods, u) for c, mods, u in e["lines"]}
    body = []
    for c in MD_FORM:
        if c in marked:
            mods, u = marked[c]
            code_s = "-".join([c] + mods)
            body.append(("p", f"[X] {code_s} &nbsp; {CODES[c][0]} &nbsp; ${CODES[c][1]:.2f}" + (f" &nbsp; x{u}" if u > 1 else "")))
        else:
            body.append(("p", f"[ &nbsp;] {c} &nbsp; {CODES[c][0]} &nbsp; ${CODES[c][1]:.2f}"))
    files["S2"] = f"encounter_form_{e['dos'].strftime('%m%d')}_{e['pt'][1].lower()}.pdf"
    write_pdf_document(os.path.join(P, files["S2"]), [
        ("right", head.replace("&amp;", "and") + "<br/>Encounter Form"), ("spacer", 6),
        ("p", f"Enc #{e['enc']} &nbsp;&nbsp; DOS {e['dos'].strftime('%B %-d, %Y')} &nbsp;&nbsp; Acct# {e['acct']}"),
        ("p", f"Patient: {e['pt'][0]} {e['pt'][1]} &nbsp;&nbsp; Provider: {e['provider']}"), ("hr", None),
        ("h", "Office visits, procedures and imaging")] + body + [
        ("spacer", 8), ("small", "Modifiers are written after the code. Quantity other than 1 is written as x2, x3.")],
        pagesize="letter", font="Times-Roman", base_size=11)
    # S3: therapy daily note, GP once at the top, minutes and units columns
    e = E["S3"]
    files["S3"] = f"PT_daily_note_{e['enc']}.pdf"
    trows = [["Code", "Service", "Minutes", "Units"]] + [[c, CODES[c][0], mnt, u] for (c, mods, u), mnt in zip(e["lines"], e["minutes"])]
    write_pdf_document(os.path.join(P, files["S3"]), [
        ("title", "Physical Therapy Daily Note"), ("small", head),
        ("table", [["Visit / encounter", "Account", "Date", "Therapist"], [e["enc"], e["acct"], e["dos"].strftime("%Y-%m-%d"), e["provider"]]],
         {"col_widths": [100, 90, 90, 170], "grid": True}), ("spacer", 6),
        ("p", f"Patient: {e['pt'][0]} {e['pt'][1]}. Dx: right knee pain, post-op week 6. Tolerated treatment well, progressed step-downs."),
        ("h", "Billing"), ("p", "<b>Modifier GP applies to every therapy code billed below.</b>"),
        ("table", trows, {"col_widths": [50, 250, 60, 50], "shade_header": True}), ("spacer", 6),
        ("small", f"Total timed minutes {sum(e['minutes'])}. Units per the 8-minute rule."),
        ("spacer", 8), ("p", "Plan: continue 2x/week, reassess in 4 visits.")], pagesize="a4", font="Times-Roman", base_size=10)
    # S4: typed flowsheet, Courier, hyphen modifiers, x2, VOID line
    e = E["S4"]
    vc, vm, vu = e["void"]
    trows = [["CODE", "SERVICE", "QTY", "STATUS"]]
    ln = list(e["lines"])
    for i, (c, mods, u) in enumerate(ln):
        trows.append(["-".join([c] + mods), CODES[c][0].upper(), f"x{u}", "billed"])
        if i == 1:
            trows.append(["-".join([vc] + vm), CODES[vc][0].upper(), f"x{vu}", "VOID - entered in error (KT)"])
    files["S4"] = f"flowsheet_{e['pt'][1].upper()}_{e['dos'].strftime('%Y%m%d')}.pdf"
    write_pdf_document(os.path.join(P, files["S4"]), [
        ("h", "SUMMIT RIDGE PT - TREATMENT FLOWSHEET / CHARGE SLIP"),
        ("p", f"ENCOUNTER NO {e['enc']}<br/>ACCOUNT {e['acct']}<br/>PATIENT {e['pt'][1].upper()}, {e['pt'][0].upper()}<br/>"
              f"SERVICE DATE {e['dos'].strftime('%d-%b-%Y').upper()}<br/>THERAPIST {e['provider'].upper()}"), ("spacer", 6),
        ("table", trows, {"col_widths": [110, 220, 40, 130], "grid": True}), ("spacer", 6),
        ("small", "INITIAL EVAL COMPLETED. HEP ISSUED. 97140 DISTINCT FROM 97162 - SEPARATE REGION.")], pagesize="letter", font="Courier", base_size=9)
    # S5: late June superbill, different form: only performed services listed with CPT / Mod / Units / Fee
    e = E["S5"]
    files["S5"] = f"superbill_{e['enc']}_late_entry.pdf"
    write_pdf_document(os.path.join(P, files["S5"]), [
        ("table", [["SUMMIT RIDGE SPORTS MEDICINE", "LATE ENTRY"], ["Charge ticket", f"Encounter {e['enc']}"]],
         {"col_widths": [300, 170], "shade_header": True}), ("spacer", 8),
        ("kv", [("Patient", f"{e['pt'][0]} {e['pt'][1]}"), ("Account", e["acct"]), ("Visit date", e["dos"].strftime("%b %d %Y")),
                ("Physician", e["provider"])], {"col_widths": [90, 250]}), ("spacer", 8),
        ("table", [["CPT", "Mod", "Units", "Description", "Fee"]] +
         [[c, " ".join(mods), u, CODES[c][0], f"${CODES[c][1]:.2f}"] for c, mods, u in e["lines"]], {"col_widths": [50, 50, 40, 250, 60]}),
        ("spacer", 8), ("small", "Found in the June tray on 09/08/2026 and never entered. Please key with the original visit date.")],
        pagesize="a4", font="Helvetica", base_size=10)
    # S6: scanned therapy visit
    e = E["S6"]
    files["S6"] = f"scan_{e['dos'].strftime('%m%d')}_{e['enc']}.pdf"
    lines = ["SUMMIT RIDGE PHYSICAL THERAPY", "VISIT CHARGE SLIP", "", f"ENCOUNTER {e['enc']}", f"ACCOUNT {e['acct']}",
             f"PATIENT {e['pt'][0].upper()} {e['pt'][1].upper()}", f"DATE {e['dos'].month}/{e['dos'].day}/{e['dos'].year}",
             f"CLINICIAN {e['provider'].upper()}", "", "CODE  MODIFIERS  UNITS", ""]
    lines += [f"{c}  {' '.join(mods)}  {u} UNIT{'S' if u > 1 else ''}" for c, mods, u in e["lines"]]
    lines += ["", "KX - THRESHOLD REACHED, MEDICALLY NECESSARY", "SIGNED DANA CRUZ PTA"]
    write_scan_pdf(os.path.join(P, files["S6"]), lines, font_size=32, skew_deg=0.4, noise=450, seed=seed * 17 + 3)
    return files


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    files = render(ws, d, seed)
    write_csv(os.path.join(ws, "fee_schedule.csv"), ["cpt_code", "description", "fee", "effective_from", "effective_to"],
              [[c, v[0], f"{v[1]:.2f}", "2025-07-01", "2026-06-30"] for c, v in sorted(CODES.items())] +
              [[c, v[0], f"{v[2]:.2f}", "2026-07-01", ""] for c, v in sorted(CODES.items())])
    write_text(os.path.join(ws, "note_from_renee.txt"),
               "Charge entry for this week's superbills\n\n"
               "The superbills and therapy slips are in the folder. The charge import wants one row per procedure code we actually "
               "billed, saved as superbill_lines.csv:\n\n"
               "  line_ref       encounter number, a hyphen, the five-digit code (40412-97110)\n"
               "  encounter_no   digits only\n"
               "  account_no     as printed (A12345)\n"
               "  service_date   YYYY-MM-DD, the date of the visit\n"
               "  cpt_code       the five-digit code only, no modifiers attached\n"
               "  modifiers      every modifier that applies to that line, two characters each, separated by a space, in the order "
               "the form gives them; blank if none\n"
               "  units          billed units (not minutes)\n"
               "  charge         units times the fee from fee_schedule.csv in effect on the date of service. Ignore the fees printed "
               "on the forms, the form stock is old.\n\n"
               "Anything crossed out or voided on a slip was not billed.\n\nRenee\n")
    write_csv(os.path.join(ref, "superbill_lines.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "superbill_lines.csv"), HEADER, d["rows"])
    E = {e["key"]: e for e in d["encs"]}
    refs = lambda k: [f"{E[k]['enc']}-{c}" for c, _, _ in E[k]["lines"]]
    s6 = E["S6"]
    scan_figs = [s6["enc"], s6["acct"], f"{s6['dos'].month}/{s6['dos'].day}/{s6['dos'].year}"] + \
                [f"{c}  {' '.join(m)}  {u} UNIT" for c, m, u in s6["lines"]]
    write_json(os.path.join(ref, "notes.json"), {"files": files, "void": f"{E['S4']['enc']}-{E['S4']['void'][0]}",
                                                  "scan_figures": {f"superbills_week_2026-09-07/{files['S6']}": scan_figs}})
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    P = "superbill_lines.csv"
    write_task_yaml(HERE, {
        "id": "superbill-codes", "track": "desk", "category": "extraction",
        "title": "Key this week's superbills for charge entry",
        "ask": ("This week's superbills are in the folder - can you get them into superbill_lines.csv for charge entry? "
                "Renee's note has how the import wants it.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "modifiers are written four ways: hyphen-joined to the code on the encounter form and the typed flowsheet (99214-25, 97140-GP-59), "
            "in a Mod column on the checkbox superbill and the late ticket, after the code on the scan (GP KX), and once in bold above the "
            "therapy note's table for every code below it; the code column must hold the bare code (checks: procedure codes; modifiers)",
            "the therapy note prints minutes beside units, the typed flowsheet writes quantities as x2, and the checkbox superbill leaves Units "
            "blank for one unit; charge is units times the fee, not the fee (checks: units; charges)",
            f"the typed flowsheet for encounter {E['S4']['enc']} lists {E['S4']['void'][0]} marked 'VOID - entered in error'; it is not billed "
            "(checks: one row per billed line; row count)",
            "the checkbox superbill and the encounter form list all eleven common codes with fees; only the rows marked X were performed "
            "(checks: one row per billed line; row count)",
            f"every form prints the 2025 fees; charges come from the schedule in effect on the date of service, which is the 2026 fee for "
            f"September visits and the 2025 fee for the late ticket {E['S5']['enc']} dated 29 June (check: charges)",
            f"the Thursday therapy slip for encounter {E['S6']['enc']} is an image-only scan (checks: modifiers; units)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per billed line", "path": P, "column": "line_ref", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "encounter, account and date", "path": P, "ref": P, "key": "line_ref",
             "columns": ["encounter_no", "account_no", "service_date"], "min_accuracy": 1.0, "must_match_keys": refs("S5") + refs("S6")},
            {"type": "csv_values_match", "name": "procedure codes", "path": P, "ref": P, "key": "line_ref", "columns": ["cpt_code"],
             "min_accuracy": 1.0, "must_match_keys": refs("S2") + refs("S4")},
            {"type": "csv_values_match", "name": "modifiers", "path": P, "ref": P, "key": "line_ref", "columns": ["modifiers"],
             "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": refs("S3") + refs("S4") + refs("S6")},
            {"type": "csv_values_match", "name": "units", "path": P, "ref": P, "key": "line_ref", "columns": ["units"],
             "must_match_keys": refs("S1") + refs("S3") + refs("S4") + refs("S6"), **num},
            {"type": "csv_values_match", "name": "charges", "path": P, "ref": P, "key": "line_ref", "columns": ["charge"],
             "must_match_keys": refs("S1") + refs("S5"), **num},
        ],
    })
    print(f"seed={seed} rows={len(d['rows'])} files={len(files)}")


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: every coded line on a slip keyed (the VOID line too), the code copied as written (99214-25),
    only modifiers printed beside a code, the first number on the line as units (minutes on the therapy note, 1 where blank or x2),
    and the printed form fee times units."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for e in d["encs"]:
        lines = list(e["lines"]) + ([e["void"]] if "void" in e else [])
        for i, (c, mods, u) in enumerate(lines):
            code_s, mod_s, units = c, " ".join(mods), u
            if e["key"] in ("S2", "S4"):
                code_s, mod_s = "-".join([c] + mods), ""
            if e["key"] == "S3":
                mod_s, units = "", e["minutes"][i]
            if e["key"] == "S4":
                units = 1
            rows.append([f"{e['enc']}-{c}", e["enc"], e["acct"], e["dos"].isoformat(), code_s, mod_s, units, f"{units * CODES[c][1]:.2f}"])
    write_csv(os.path.join(out, "superbill_lines.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, build(a.seed), a.naive)
