#!/usr/bin/env python3
"""grant-budget-tracking: a watershed nonprofit's grant-tagged expenses against three award budgets, line by line.

    python gen.py [--seed N] [--naive DIR]

Business: Millbrook Watershed Alliance runs stream restoration, a schools program and volunteer water monitoring on
three restricted grants. The bookkeeper tags each expense with a budget line code; shared costs carry a percentage
split. The development director's summary of the award letters carries what each funder will not pay for and how
split amounts round.

Traps (each caught by a check, see task.yaml):
  * split-funded expenses divide by percentage (first grant listed rounded, last takes the rest), not all to the first code
    (checks: restoration personnel remaining; coordinator stipend remaining)
  * the state fund pays for no food, including its half of a split volunteer lunch the county grant does pay for
    (checks: restoration materials remaining; volunteer recognition remaining)
  * costs invoiced before an award starts are not allowable, even when posted after          (check: restoration materials remaining)
  * the county grant pays for no gift cards or alcohol                                       (check: volunteer recognition remaining)
  * the foundation pays for no staff mileage                                                 (check: total disallowed)
  * a vendor credit for returned test kits nets against its line                             (check: monitoring equipment remaining)
  * expenses tagged to general operations are not grant spending                             (check: total disallowed)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

GRANTS = {
    "SCWF": {"name": "State Clean Water Fund - Mill Creek Restoration", "start": date(2026, 1, 1), "end": date(2026, 12, 31),
             "lines": [("SCWF-PER", "Restoration personnel", 3800000), ("SCWF-CON", "Earthwork contractor", 5200000),
                       ("SCWF-MAT", "Restoration materials", 1850000), ("SCWF-MIL", "Field mileage", 240000)]},
    "HFF": {"name": "Hartwell Family Foundation - Watershed Classrooms", "start": date(2026, 2, 1), "end": date(2027, 1, 31),
            "lines": [("HFF-EDU", "Education staff", 2400000), ("HFF-SUP", "Classroom kits", 620000), ("HFF-BUS", "Student buses", 480000),
                      ("HFF-PRT", "Curriculum printing", 210000)]},
    "CPCG": {"name": "County Parks Community Grant - Volunteer Stream Monitoring", "start": date(2026, 3, 1), "end": date(2026, 10, 31),
             "lines": [("CPCG-STI", "Coordinator stipend", 900000), ("CPCG-EQP", "Monitoring equipment", 540000),
                       ("CPCG-VOL", "Volunteer recognition", 150000), ("CPCG-OUT", "Outreach printing", 120000)]},
}
LINE_NAME = {code: name for g in GRANTS.values() for code, name, _ in g["lines"]}
LINE_GRANT = {code: gid for gid, g in GRANTS.items() for code, _, _ in g["lines"]}


def cents_round(x: Decimal) -> int:
    return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build(seed: int) -> dict:
    r = rng(seed)
    exp = []
    seq = [r.randint(2100, 2400)]

    def add(posted, invoiced, vendor, desc, amt, tags, note=""):
        seq[0] += r.randint(1, 4)
        exp.append({"id": f"JE-{seq[0]}", "posted": posted, "invoiced": invoiced, "vendor": vendor, "desc": desc, "amt": amt, "tags": tags,
                    "note": note})
        return exp[-1]

    months = range(1, 9)
    # payroll-like recurring charges
    coord_split = None
    for m in months:
        d = date(2026, m, 28 if m != 2 else 27)
        add(d, d, "Payroll - Gusto", "Restoration crew lead wages", r.randint(290000, 330000), [("SCWF-PER", 100)])
        if m >= 3:
            e = add(d, d, "Payroll - Gusto", "Program coordinator wages (split)", r.randint(310000, 352000) + r.choice([7, 13, 19, 31]),
                    [("SCWF-PER", 60), ("CPCG-STI", 40)])
            coord_split = coord_split or e
        if m >= 2:
            add(d, d, "Payroll - Gusto", "Education specialist wages", r.randint(180000, 215000), [("HFF-EDU", 100)])
    for _ in range(3):
        d = day_in(r, date(2026, 4, 1), date(2026, 8, 20), True)
        add(d, d, "Kessler Excavating", "Streambank grading - Mill Creek reach " + r.choice("ABC"), r.randint(740000, 1350000), [("SCWF-CON", 100)])
    for vendor, desc in (("Prairie Moon Nursery", "Live stakes and plugs"), ("Erosion Supply Co", "Coir logs and matting"),
                         ("Quarry Road Nursery", "Native shrubs"), ("Erosion Supply Co", "Rock for toe protection")):
        d = day_in(r, date(2026, 2, 1), date(2026, 8, 20), True)
        add(d, d, vendor, desc, r.randint(90000, 260000), [("SCWF-MAT", 100)])
    pre = add(date(2026, 1, r.randint(6, 14)), date(2025, 12, r.randint(8, 19)), "Prairie Moon Nursery", "Bare-root order (December invoice)",
              r.randint(110000, 190000), [("SCWF-MAT", 100)])
    food = add(day_in(r, date(2026, 4, 11), date(2026, 5, 16), True), None, "Mill Street Pizza", "Pizza and drinks - restoration volunteer planting day",
               r.randint(16000, 26000), [("SCWF-MAT", 100)])
    for m in (3, 4, 5, 6, 7, 8):
        d = date(2026, m, r.randint(3, 8))
        add(d, d, "Staff mileage reimbursement", "Field mileage - site visits", r.randint(11000, 26000), [("SCWF-MIL", 100)])
    hff_miles = add(date(2026, r.choice([4, 5]), r.randint(9, 22), ), None, "Staff mileage reimbursement", "Mileage - school visits",
                    r.randint(21000, 34000), [("HFF-EDU", 100)])
    hff_miles2 = add(date(2026, r.choice([6, 7]), r.randint(9, 22)), None, "Staff mileage reimbursement", "Mileage - teacher workshop",
                     r.randint(9000, 16000), [("HFF-EDU", 100)])
    for _ in range(3):
        d = day_in(r, date(2026, 2, 10), date(2026, 8, 10), True)
        add(d, d, "Carolina Biological", "Macroinvertebrate classroom kits", r.randint(60000, 140000), [("HFF-SUP", 100)])
    for _ in range(3):
        d = day_in(r, date(2026, 3, 1), date(2026, 6, 5), True)
        add(d, d, "Blue Bird Charter Lines", "Field trip buses", r.randint(52000, 91000), [("HFF-BUS", 100)])
    add(day_in(r, date(2026, 2, 10), date(2026, 3, 20), True), None, "Quill & Ink Print Shop", "Student field guides", r.randint(70000, 110000),
        [("HFF-PRT", 100)])
    for _ in range(2):
        d = day_in(r, date(2026, 3, 5), date(2026, 7, 30), True)
        add(d, d, "LaMotte Company", "Water test kits and reagents", r.randint(80000, 150000), [("CPCG-EQP", 100)])
    kits = [x for x in exp if x["vendor"] == "LaMotte Company"]
    credit = add(max(k["posted"] for k in kits) + (date(2026, 8, 12) - date(2026, 8, 5)), None, "LaMotte Company",
                 "Credit memo - returned damaged reagent case", -r.randint(18000, 32000), [("CPCG-EQP", 100)])
    lunch = add(day_in(r, date(2026, 6, 1), date(2026, 6, 26), True), None, "Riverside Deli", "Volunteer lunch - joint planting and monitoring day",
                r.randint(34000, 52000) + r.choice([1, 3, 7]), [("SCWF-MAT", 50), ("CPCG-VOL", 50)])
    gift = add(day_in(r, date(2026, 7, 6), date(2026, 8, 14), True), None, "Target", "Gift cards - top volunteer monitors", r.randint(20000, 30000),
               [("CPCG-VOL", 100)])
    wine = add(day_in(r, date(2026, 8, 3), date(2026, 8, 21), True), None, "Vintner's Cellar", "Wine for volunteer appreciation dinner",
               r.randint(9000, 16000), [("CPCG-VOL", 100)])
    for _ in range(2):
        d = day_in(r, date(2026, 4, 1), date(2026, 8, 25), True)
        add(d, d, "Grocery Outlet", "Snacks and water - volunteer monitoring training", r.randint(4000, 9500), [("CPCG-VOL", 100)])
    bus_split = add(day_in(r, date(2026, 5, 4), date(2026, 5, 29), True), None, "Blue Bird Charter Lines", "Bus - students and volunteers, creek day (split)",
                    r.randint(60000, 90000) + r.choice([1, 5, 9]), [("HFF-BUS", 70), ("CPCG-OUT", 30)])
    add(day_in(r, date(2026, 3, 10), date(2026, 5, 10), True), None, "Quill & Ink Print Shop", "Monitoring volunteer recruitment flyers",
        r.randint(30000, 52000), [("CPCG-OUT", 100)])
    ops = []
    for vendor, desc in (("Everline Insurance", "General liability insurance"), ("Mossbank Accounting", "Annual audit deposit"),
                         ("Comcast Business", "Office internet")):
        d = day_in(r, date(2026, 1, 15), date(2026, 8, 25), True)
        ops.append(add(d, d, vendor, desc, r.randint(20000, 180000), [("GEN-OPS", 100)]))
    for x in exp:
        if x["invoiced"] is None:
            x["invoiced"] = x["posted"]
    n0 = r.randint(2100, 2400)
    for x in sorted(exp, key=lambda x: (x["posted"], x["vendor"], x["amt"])):
        n0 += r.randint(1, 4)
        x["id"] = f"JE-{n0}"

    # ---- truth
    shares = []  # one per (expense, tag)
    disallowed = []
    for x in exp:
        parts = []
        acc = 0
        for i, (code, pct) in enumerate(x["tags"]):
            if i < len(x["tags"]) - 1:
                a = cents_round(Decimal(x["amt"]) * Decimal(pct) / 100)
            else:
                a = x["amt"] - acc
            acc += a
            parts.append((code, pct, a))
        for code, pct, a in parts:
            reason = None
            if code == "GEN-OPS":
                reason = "general operations, not grant spending"
            else:
                g = GRANTS[LINE_GRANT[code]]
                if x["invoiced"] < g["start"]:
                    reason = "incurred before the award period"
                elif LINE_GRANT[code] == "SCWF" and x in (food, lunch):
                    reason = "food is not allowable on the state fund"
                elif LINE_GRANT[code] == "CPCG" and x is gift:
                    reason = "gift cards are not allowable on the county grant"
                elif LINE_GRANT[code] == "CPCG" and x is wine:
                    reason = "alcohol is not allowable on the county grant"
                elif LINE_GRANT[code] == "HFF" and x in (hff_miles, hff_miles2):
                    reason = "the foundation does not pay staff mileage"
            shares.append({"exp": x, "code": code, "pct": pct, "amt": a, "reason": reason})
            if reason and code != "GEN-OPS":
                disallowed.append(shares[-1])
    spent = {code: sum(s["amt"] for s in shares if s["code"] == code and not s["reason"]) for code in LINE_NAME}
    budget = {code: b for g in GRANTS.values() for code, _, b in g["lines"]}
    remaining = {code: budget[code] - spent[code] for code in LINE_NAME}
    return {"exp": exp, "shares": shares, "disallowed": disallowed, "spent": spent, "budget": budget, "remaining": remaining,
            "disallowed_total": sum(s["amt"] for s in disallowed), "roles": {"coord": coord_split, "pre": pre, "food": food, "lunch": lunch,
                                                                           "gift": gift, "wine": wine, "credit": credit, "bus": bus_split,
                                                                           "miles": hff_miles}}


def naive(d: dict) -> dict:
    """Every tagged dollar counts against its first-listed line in full, nothing disallowed."""
    spent = {code: 0 for code in LINE_NAME}
    for x in d["exp"]:
        code = x["tags"][0][0]
        if code in spent:
            spent[code] += abs(x["amt"])
    return {"spent": spent, "remaining": {c: d["budget"][c] - spent[c] for c in LINE_NAME}, "disallowed_total": 0}


PINS = [("SCWF-MAT", "restoration materials"), ("SCWF-PER", "restoration personnel"), ("CPCG-STI", "coordinator stipend"),
        ("CPCG-VOL", "volunteer recognition"), ("CPCG-EQP", "monitoring equipment")]


def acceptable(d: dict) -> bool:
    nv = naive(d)
    for code, _ in PINS:
        v = d["remaining"][code]
        if abs(nv["remaining"][code] - v) < 500 or v <= 0:
            return False
        dis = sum(s["amt"] for s in d["disallowed"] if s["code"] == code)
        if any(abs(v - o) <= 100 for o in (d["budget"][code], d["spent"][code], dis)):
            return False
    # the split rounding must bite: the coordinator split and the lunch split each carry an odd cent
    for role in ("coord", "lunch", "bus"):
        x = d["roles"][role]
        first = x["tags"][0][1]
        if (x["amt"] * first) % 100 == 0:
            return False
    return all(v > 0 for v in d["remaining"].values())


# --------------------------------------------------------------------------- deliverable

def workbook(d: dict, shares: list[dict], budget: dict) -> dict:
    detail = []
    for s in shares:
        x = s["exp"]
        detail.append([x["id"], x["posted"], x["vendor"], x["desc"], x["amt"] / 100, s["code"], s["pct"] / 100, s["amt"] / 100,
                       "No" if s["reason"] else "Yes", s["reason"] or ""])
    n = len(detail) + 1
    summary = []
    row = 2
    for gid, g in GRANTS.items():
        for code, name, _ in g["lines"]:
            summary.append([g["name"], code, name, budget[code] / 100,
                            f'=SUMIFS(Detail!$H$2:$H${n},Detail!$F$2:$F${n},B{row},Detail!$I$2:$I${n},"Yes")', f"=D{row}-E{row}",
                            f'=SUMIFS(Detail!$H$2:$H${n},Detail!$F$2:$F${n},B{row},Detail!$I$2:$I${n},"No")'])
            row += 1
    last = row - 1
    summary.append(["Total all grants", "", "", f"=SUM(D2:D{last})", f"=SUM(E2:E{last})", f"=SUM(F2:F{last})", f"=SUM(G2:G{last})"])
    return {
        "Summary": {"header": ["Grant", "Line code", "Budget line", "Budget", "Allowable spent to date", "Remaining", "Disallowed"],
                    "rows": summary, "number_formats": {c: "#,##0.00" for c in "DEFG"}, "widths": {"A": 52, "C": 24, "E": 20}},
        "Detail": {"header": ["Entry", "Posted", "Vendor", "Description", "Expense amount", "Line code", "Share", "Charged amount", "Allowable",
                              "Why not"], "rows": detail, "number_formats": {"E": "#,##0.00", "G": "0%", "H": "#,##0.00"},
                   "widths": {"C": 26, "D": 44, "J": 40}},
    }


def naive_workbook(d: dict) -> dict:
    nv = naive(d)
    rows = [[GRANTS[LINE_GRANT[c]]["name"], c, LINE_NAME[c], d["budget"][c] / 100, nv["spent"][c] / 100, f"=D{i}-E{i}"]
            for i, c in enumerate(LINE_NAME, start=2)]
    return {"Summary": {"header": ["Grant", "Line code", "Budget line", "Budget", "Spent", "Remaining"], "rows": rows}}


def tag_text(tags) -> str:
    if len(tags) == 1:
        return tags[0][0]
    return " / ".join(f"{c} {p}%" for c, p in tags)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_xlsx(os.path.join(naive_dir, "grant_tracking.xlsx"), naive_workbook(d), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    ro = d["roles"]

    # ---- workspace: expense export
    rows = [[x["posted"].strftime("%m/%d/%Y"), x["id"], x["vendor"], x["desc"], x["invoiced"].strftime("%m/%d/%Y"), tag_text(x["tags"]),
             money_str(x["amt"] / 100, 5 if x["amt"] < 0 else 0)] for x in sorted(d["exp"], key=lambda x: (x["posted"], x["id"]))]
    write_csv(os.path.join(ws, "expenses_by_budget_line_2026-01_to_2026-08.csv"),
              ["Posted", "Entry", "Vendor", "Description", "Invoice date", "Budget line", "Amount"], rows,
              preamble=["Millbrook Watershed Alliance - Expense detail by budget line", "Jan 1 - Aug 31, 2026 (cash basis)"], crlf=True)

    # ---- workspace: budgets workbook, one sheet per grant
    sheets = {}
    for gid, g in GRANTS.items():
        sheets[gid] = {"merged_title": g["name"],
                       "preamble": [["Award period", f"{g['start'].strftime('%m/%d/%Y')} - {g['end'].strftime('%m/%d/%Y')}"]],
                       "header": ["Line code", "Budget line", "Approved budget"],
                       "rows": [[code, name, money_str(b / 100, 1)] for code, name, b in g["lines"]] + [["", "Total", money_str(sum(b for _, _, b in g["lines"]) / 100, 1)]],
                       "widths": {"A": 14, "B": 26, "C": 18}}
    sheets["GEN"] = {"header": ["Line code", "Budget line", "Note"], "rows": [["GEN-OPS", "General operations", "Unrestricted - not a grant"]],
                     "widths": {"A": 14, "B": 22, "C": 30}}
    write_xlsx(os.path.join(ws, "grant_budgets_2026.xlsx"), sheets, creator="Millbrook Watershed Alliance")

    # ---- workspace: award rules summary
    write_text(os.path.join(ws, "award_terms_summary.txt"),
               "GRANT TERMS CHEAT SHEET - keep with the tracking file\n(from the award letters; Nia, Development)\n\n"
               "State Clean Water Fund (SCWF) - award period 1/1/2026 to 12/31/2026\n"
               "  - Costs are allowable only if incurred inside the award period. Use the invoice date, not the date we posted it.\n"
               "  - No food or beverages of any kind, including volunteer events.\n\n"
               "Hartwell Family Foundation (HFF) - award period 2/1/2026 to 1/31/2027\n"
               "  - Same rule on the award period.\n"
               "  - The foundation does not pay staff mileage or travel, even when it is booked to a staff line.\n\n"
               "County Parks Community Grant (CPCG) - award period 3/1/2026 to 10/31/2026\n"
               "  - Same rule on the award period.\n"
               "  - Food for volunteers is fine. Gift cards and alcohol are never allowable.\n\n"
               "Split-funded costs\n"
               "  - The budget line column shows the split, e.g. 'SCWF-PER 60% / CPCG-STI 40%'. Work out each grant's share of the\n"
               "    expense: every grant but the last one listed is rounded to the cent, and the last one listed gets whatever is left,\n"
               "    so the pieces add back to the expense exactly. Each piece is then allowable or not under its own grant's rules.\n\n"
               "Anything disallowed comes off the grant and gets paid from unrestricted funds. Credits and refunds reduce the line they\n"
               "were booked to. GEN-OPS lines are ordinary operating costs that were never charged to a grant, so they are not grant\n"
               "spending and not disallowed costs either - leave them out.\n\n"
               "For the board packet: for each grant and budget line, the budget, what we have spent that the grant will actually pay\n"
               "for, and what is left, plus what we disallowed. Formulas please, the auditors like to trace them.\n")

    # ---- reference
    write_csv(os.path.join(ref, "lines.csv"), ["grant", "line_code", "budget_line", "budget", "allowable_spent", "remaining", "disallowed"],
              [[LINE_GRANT[c], c, LINE_NAME[c], f"{d['budget'][c] / 100:.2f}", f"{d['spent'][c] / 100:.2f}", f"{d['remaining'][c] / 100:.2f}",
                f"{sum(s['amt'] for s in d['disallowed'] if s['code'] == c) / 100:.2f}"] for c in LINE_NAME])
    write_json(os.path.join(ref, "notes.json"), {
        "disallowed": [{"entry": s["exp"]["id"], "line": s["code"], "amount": f"{s['amt'] / 100:.2f}", "reason": s["reason"]} for s in d["disallowed"]],
        "disallowed_total": f"{d['disallowed_total'] / 100:.2f}", "splits": [x["id"] for x in d["exp"] if len(x["tags"]) > 1]})

    write_xlsx(os.path.join(sol, "grant_tracking.xlsx"), workbook(d, d["shares"], d["budget"]), creator="Millbrook Watershed Alliance")

    def pin(code, near):
        return {"type": "xlsx_value_present", "name": f"{LINE_NAME[code].lower()} remaining", "path": "grant_tracking.xlsx",
                "expected": round(d["remaining"][code] / 100, 2), "rel_tol": 0.000001, "near_text": near}

    write_task_yaml(HERE, {
        "id": "grant-budget-tracking", "track": "desk", "category": "bookkeeping",
        "title": "Grant budget tracking for the board packet",
        "ask": "The board packet needs where we stand on each grant budget through August. Nia's cheat sheet on the award terms is in the folder with the budgets and the expense export. Save it as grant_tracking.xlsx.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the program coordinator's wages are split 'SCWF-PER 60% / CPCG-STI 40%' every month from March and the {ro['bus']['id']} bus is "
            "split 70/30; each grant carries only its percentage (the first listed rounded to the cent, the last taking the remainder), so "
            "charging the whole amount to the first code listed moves both lines (checks: restoration personnel remaining; coordinator "
            "stipend remaining)",
            f"{ro['food']['id']} (volunteer pizza) is tagged to SCWF restoration materials and the state fund pays for no food; {ro['lunch']['id']} "
            "is a volunteer lunch split 50/50 where the SCWF half is disallowed and the CPCG half is fine "
            "(checks: restoration materials remaining; volunteer recognition remaining)",
            f"{ro['pre']['id']} was posted in January but invoiced in December 2025, before the SCWF award period "
            "(check: restoration materials remaining)",
            f"{ro['gift']['id']} (gift cards) and {ro['wine']['id']} (wine) are tagged to CPCG volunteer recognition and are never allowable "
            "(check: volunteer recognition remaining)",
            f"{ro['miles']['id']} and a second staff mileage entry are booked to the HFF education staff line; the foundation pays no mileage "
            "(check: total disallowed)",
            f"{ro['credit']['id']} is a LaMotte credit memo in parentheses that reduces monitoring equipment spending "
            "(check: monitoring equipment remaining)",
            "three general-operations expenses (GEN-OPS) sit in the same export and are neither grant spending nor disallowed costs; amounts are text with "
            "thousands separators under a two-line preamble with CRLF endings (checks: total disallowed; restoration personnel remaining)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "grant_tracking.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no formula errors", "path": "grant_tracking.xlsx"},
            pin("SCWF-MAT", "restoration materials"),
            pin("SCWF-PER", "restoration personnel"),
            pin("CPCG-STI", "coordinator stipend"),
            pin("CPCG-VOL", "volunteer recognition"),
            pin("CPCG-EQP", "monitoring equipment"),
            {"type": "xlsx_value_present", "name": "total disallowed", "path": "grant_tracking.xlsx",
             "expected": round(d["disallowed_total"] / 100, 2), "rel_tol": 0.000001, "near_text": "disallow"},
        ],
    })
    print(f"seed={seed} expenses={len(d['exp'])} disallowed={d['disallowed_total'] / 100:.2f}")
    print({c: d["remaining"][c] / 100 for c in LINE_NAME})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a_ = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a_.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a_.seed * 1000 + attempt, a_.naive)
