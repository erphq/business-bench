#!/usr/bin/env python3
"""dept-expense-report: a quarter of employee expense lines to spend by department by month, with overruns.

    python gen.py [--seed N] [--naive DIR]

Business: a 40-person media agency. The expense tool exports every line with the cost center the employee
picked; finance reports by department against the annual budgets the CFO set in January.

Traps (each caught by a check, see task.yaml):
  * cost centers are written four ways ("4200", "CC-4200", "4200 - Events", "Events (4200)") and roll up to
    five departments through the cost-center workbook                               (check: Marketing Q2 total)
  * lines with no cost center belong to the employee's home cost center on the People sheet, which writes
    names "Last, First"                                                              (check: Production Q2 total)
  * budgets are annual in Hiroshi's note and phased evenly, so the quarter's budget is a quarter of it
                                                                                     (checks: memo overruns)
  * the NAB booth was charged to Events; the thread first proposes a split, then the CFO moves all of it to
    Sales East                                                                       (checks: Sales Q2 total; Marketing Q2 total; memo)
  * Rejected and Draft lines are in the export and are not spend                     (check: total spend)
  * March-dated expenses approved in April stay in closed Q1                          (check: total spend)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))


DEPTS = ["Sales", "Marketing", "Creative", "Production", "Operations"]
CENTERS = [("3100", "Sales - East", "Sales"), ("3200", "Sales - West", "Sales"),
           ("4100", "Brand", "Marketing"), ("4200", "Events", "Marketing"), ("4300", "Digital", "Marketing"),
           ("5100", "Design", "Creative"), ("5200", "Copy & Content", "Creative"),
           ("6100", "Video", "Production"), ("6200", "Photo", "Production"),
           ("7100", "Office & Facilities", "Operations"), ("7200", "IT", "Operations"), ("7300", "Finance & HR", "Operations")]
CC_NAME = {c: n for c, n, _ in CENTERS}
CC_DEPT = {c: d for c, _, d in CENTERS}
MONTHS = ["2026-04", "2026-05", "2026-06"]
MLABEL = {"2026-04": "April", "2026-05": "May", "2026-06": "June"}
HEADCOUNT = {"Sales": 7, "Marketing": 6, "Creative": 7, "Production": 8, "Operations": 5}
# category, merchants, amount range, weight
SPEND = {
    "Sales": [("Travel", ["DELTA AIR", "UNITED AIRLINES", "MARRIOTT HTL", "HERTZ RENT-A-CAR", "UBER *TRIP"], (180, 1400), 5),
              ("Client meals", ["TST* THE PARLOUR", "CHIPOTLE 1882", "CAPITAL GRILLE", "PANERA BREAD #601"], (45, 420), 5),
              ("Software", ["LINKEDIN PREMIUM", "ZOOM.US 888-799-9666"], (40, 160), 1)],
    "Marketing": [("Advertising", ["FACEBK *ADS", "GOOGLE *ADS", "LINKEDIN ADS"], (400, 3200), 4),
                  ("Events", ["PP*EVENTBRITE", "CONVENTION CTR SVCS", "SIGNARAMA"], (150, 2400), 3),
                  ("Software", ["MAILCHIMP", "ADOBE *CREATIVE CLD", "CANVA"], (30, 300), 2)],
    "Creative": [("Software", ["ADOBE *CREATIVE CLD", "FIGMA", "SHUTTERSTOCK"], (30, 520), 4),
                 ("Supplies", ["BLICK ART MATERIALS", "STAPLES 0442", "AMZN Mktp US*2K4JR7"], (25, 380), 3),
                 ("Meals", ["STARBUCKS #04512", "SQ *BLUE BOTTLE"], (12, 95), 2)],
    "Production": [("Equipment rental", ["LENSRENTALS.COM", "BORROWLENSES", "SAMYS CAMERA"], (220, 2600), 4),
                   ("Travel", ["SHELL OIL 57444", "HERTZ RENT-A-CAR", "MARRIOTT HTL"], (60, 900), 3),
                   ("Crew meals", ["COSTCO WHSE #0891", "CHIPOTLE 1882"], (80, 520), 2)],
    "Operations": [("Office", ["COSTCO WHSE #0891", "OFFICE DEPOT 2231", "IKEA EMERYVILLE"], (40, 900), 3),
                   ("IT", ["GITHUB INC", "SLACK T0123", "GOOGLE *GSUITE", "THE HOME DEPOT #4402"], (20, 1200), 3),
                   ("Postage", ["USPS PO 0561", "FEDEX 78123"], (15, 140), 1)],
}
BOOTH = {"merchant": "NAB SHOW EXHIBITOR SVCS", "category": "Events", "date": date(2026, 4, 14), "cc": "4200"}


def cc_written(r, cc: str) -> str:
    k = r.randrange(4)
    return [cc, f"CC-{cc}", f"{cc} - {CC_NAME[cc]}", f"{CC_NAME[cc]} ({cc})"][k]


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, sum(HEADCOUNT.values()))
    staff, k = [], 0
    for dept in DEPTS:
        ccs = [c for c, _, d in CENTERS if d == dept]
        for _ in range(HEADCOUNT[dept]):
            f, l = names[k]; k += 1
            staff.append({"first": f, "last": l, "dept": dept, "home": r.choice(ccs)})
    lines = []

    def add(emp, d, cat, merchant, amt, cc, status, kind="normal"):
        lines.append({"emp": emp, "date": d, "cat": cat, "merchant": merchant, "amt": round(amt, 2), "cc": cc,
                      "status": status, "kind": kind})

    for emp in staff:
        ccs = [c for c, _, d in CENTERS if d == emp["dept"]]
        for mk in MONTHS:
            y, m = int(mk[:4]), int(mk[5:])
            for _ in range(r.randint(2, 5)):
                cat, merchants, (lo, hi), _w = r.choices(SPEND[emp["dept"]], [s[3] for s in SPEND[emp["dept"]]])[0]
                d = day_in(r, date(y, m, 1), date(y, m, 30 if m in (4, 6) else 31))
                cc = emp["home"] if r.random() < 0.7 else r.choice(ccs)
                status = r.choices(["Reimbursed", "Approved", "Rejected", "Draft"], [0.62, 0.30, 0.05, 0.03])[0]
                add(emp, d, cat, r.choice(merchants), money(r, lo, hi), cc, status)
    # blank cost center: Production crew on shoots, plus a few elsewhere; always counted
    prod = [e for e in staff if e["dept"] == "Production"]
    for _ in range(9):
        e = r.choice(prod)
        cat, merchants, (lo, hi), _w = r.choice(SPEND["Production"])
        mk = r.choice(MONTHS); y, m = int(mk[:4]), int(mk[5:])
        add(e, day_in(r, date(y, m, 1), date(y, m, 28)), cat, r.choice(merchants), money(r, max(lo, 400), hi), "",
            r.choice(["Reimbursed", "Approved"]), "blank")
    for _ in range(4):
        e = r.choice([x for x in staff if x["dept"] != "Production"])
        cat, merchants, (lo, hi), _w = r.choice(SPEND[e["dept"]])
        mk = r.choice(MONTHS); y, m = int(mk[:4]), int(mk[5:])
        add(e, day_in(r, date(y, m, 1), date(y, m, 28)), cat, r.choice(merchants), money(r, lo, hi), "", "Reimbursed", "blank")
    # March-dated lines approved in April
    for _ in range(7):
        e = r.choice(staff)
        cat, merchants, (lo, hi), _w = r.choice(SPEND[e["dept"]])
        add(e, day_in(r, date(2026, 3, 16), date(2026, 3, 31)), cat, r.choice(merchants), money(r, lo, hi),
            r.choice([c for c, _, d in CENTERS if d == e["dept"]]), "Reimbursed", "march")
    # the booth
    events_lead = [e for e in staff if e["dept"] == "Marketing"][0]
    booth_amt = money(r, 8200, 11800)
    add(events_lead, BOOTH["date"], BOOTH["category"], BOOTH["merchant"], booth_amt, BOOTH["cc"], "Reimbursed", "booth")

    lines.sort(key=lambda x: (x["date"], x["emp"]["last"], x["amt"]))
    rep_no = {}
    for i, x in enumerate(lines):
        key = (x["emp"]["last"], x["date"].month)
        rep_no.setdefault(key, f"ER-2026-{400 + len(rep_no):04d}")
        x["report"] = rep_no[key]
        x["line"] = f"{i + 1:05d}"
    return {"staff": staff, "lines": lines, "booth_amt": booth_amt, "events_lead": events_lead}


def truth_dept(x) -> str | None:
    if x["kind"] == "booth":
        return "Sales"
    cc = x["cc"] or x["emp"]["home"]
    return CC_DEPT[cc]


def truth_cc(x) -> str:
    return "3100" if x["kind"] == "booth" else (x["cc"] or x["emp"]["home"])


def counted(x) -> bool:
    return x["status"] in ("Approved", "Reimbursed") and x["date"] >= date(2026, 4, 1)


def aggregate(lines, dept_of=truth_dept, count=counted) -> dict:
    agg = {(d, m): 0.0 for d in DEPTS for m in MONTHS}
    for x in lines:
        if not count(x):
            continue
        mk = f"{x['date'].year}-{x['date'].month:02d}"
        d = dept_of(x)
        if d in DEPTS and mk in MONTHS:
            agg[(d, mk)] += x["amt"]
    out = {k: round(v, 2) for k, v in agg.items()}
    for d in DEPTS:
        out[(d, "Q2")] = round(sum(agg[(d, m)] for m in MONTHS), 2)
    out["total"] = round(sum(out[(d, "Q2")] for d in DEPTS), 2)
    return out


def set_budgets(d: dict) -> bool:
    r = rng(len(d["lines"]) * 7919 + int(d["booth_amt"] * 100))
    L = d["lines"]
    t = aggregate(L)
    no_booth = aggregate(L, dept_of=lambda x: CC_DEPT[x["cc"] or x["emp"]["home"]])
    no_blank = aggregate(L, dept_of=lambda x: None if not x["cc"] and x["kind"] != "booth" else truth_dept(x))
    booth = d["booth_amt"]
    q = {}
    # Sales: over only with the booth
    lo, hi = t[("Sales", "Q2")] - (booth - 1500), t[("Sales", "Q2")] - 1500
    q["Sales"] = _quarter_budget(r, lo, hi)
    # Marketing: over only without the booth
    lo, hi = t[("Marketing", "Q2")] + 1200, t[("Marketing", "Q2")] + booth - 1200
    q["Marketing"] = _quarter_budget(r, lo, hi)
    # Production: over with the blank cost-center lines, under without them
    lo, hi = max(t[("Production", "Q2")] - 4500, no_blank[("Production", "Q2")] + 600), t[("Production", "Q2")] - 800
    q["Production"] = _quarter_budget(r, lo, hi)
    for dept in ("Creative", "Operations"):
        lo = t[(dept, "Q2")] + 2500
        q[dept] = _quarter_budget(r, lo, lo + 5000)
    if None in q.values():
        return False
    d["q_budget"] = q
    d["annual"] = {k: v * 4 for k, v in q.items()}
    d["over"] = {k: round(t[(k, "Q2")] - q[k], 2) for k in DEPTS}
    d["t"], d["no_booth"], d["no_blank"] = t, no_booth, no_blank
    return True


def _quarter_budget(r, lo: float, hi: float):
    """a quarter budget that is a quarter of an annual figure in whole thousands"""
    cands = [a * 250 for a in range(int(lo // 250) + 1, int(hi // 250) + 1) if lo < a * 250 < hi]
    return r.choice(cands) if cands else None


def acceptable(d: dict) -> bool:
    if not set_budgets(d):
        return False
    t, q = d["t"], d["q_budget"]
    over = [k for k in DEPTS if d["over"][k] > 0]
    if over != ["Sales", "Production"]:
        return False
    if sum(1 for x in d["lines"] if x["kind"] == "blank" and x["emp"]["dept"] == "Production") < 6:
        return False
    # pinned figures stand apart from everything else on their rows and from each other
    for dept in ("Sales", "Marketing", "Production"):
        v = t[(dept, "Q2")]
        others = [t[(dept, m)] for m in MONTHS] + [q[dept], d["over"][dept], d["annual"][dept]]
        if any(abs(v - o) <= 0.02 * v for o in others):
            return False
    vals = [t[(k, "Q2")] for k in DEPTS] + [t["total"]]
    if len({round(v, -2) for v in vals}) < len(vals):
        return False
    # the naive readings move every pinned figure
    split = t[("Sales", "Q2")] - d["booth_amt"] / 2
    if abs(split - t[("Sales", "Q2")]) < 0.02 * t[("Sales", "Q2")]:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_workbook(rows: list[list], budgets: dict, note: str) -> dict:
    """rows: [line, expense_date, month, employee, merchant, category, amount, cost_center, department, status, counted]"""
    n = len(rows) + 1
    summ = []
    for i, dept in enumerate(DEPTS, start=2):
        line = [dept]
        for j, mk in enumerate(MONTHS):
            L = "BCD"[j]
            line.append(f"=ROUND(SUMIFS(Lines!$G$2:$G${n},Lines!$I$2:$I${n},$A{i},Lines!$C$2:$C${n},{L}$1,Lines!$K$2:$K${n},1),2)")
        line += [f"=ROUND(SUM(B{i}:D{i}),2)", f"=Budget!B{i}/4", f"=ROUND(E{i}-F{i},2)", f'=IF(G{i}>0,"Over budget","Within budget")']
        summ.append(line)
    last = len(DEPTS) + 1
    summ.append(["Total"] + [f"=ROUND(SUM({L}2:{L}{last}),2)" for L in "BCDEFG"])
    summ.append([])
    summ.append([note])
    return {
        "Summary": {"header": ["Department"] + MONTHS + ["Q2 total", "Q2 budget", "Over (under) budget", "Status"], "rows": summ,
                    "widths": {"A": 14, "E": 12, "F": 12, "G": 18, "H": 14}},
        "Budget": {"header": ["Department", "Annual budget"], "rows": [[k, budgets[k]] for k in DEPTS]},
        "Lines": {"header": ["line", "expense_date", "month", "employee", "merchant", "category", "amount", "cost_center",
                             "department", "status", "counted"], "rows": rows, "widths": {"D": 20, "E": 26}},
    }


def memo_text(d: dict) -> str:
    t, q, over = d["t"], d["q_budget"], d["over"]
    return f"""# Q2 2026 expenses by department

Expense spend for April to June came to ${t['total']:,.2f} across the five departments.

Two departments are over their Q2 budget (a quarter of the annual budget):

- Sales is over budget by ${over['Sales']:,.2f}: ${t[('Sales', 'Q2')]:,.2f} against ${q['Sales']:,.2f}. The NAB Show
  booth (${d['booth_amt']:,.2f}), which Hiroshi moved from Events to Sales - East, is what puts Sales over.
- Production is over budget by ${over['Production']:,.2f}: ${t[('Production', 'Q2')]:,.2f} against ${q['Production']:,.2f},
  including shoot expenses filed without a cost center.

Marketing (${t[('Marketing', 'Q2')]:,.2f}), Creative and Operations are within budget. Rejected and draft lines are left
out, and expenses dated in March stay in Q1.
"""


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    set_budgets(d)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    L, t, q = d["lines"], d["t"], d["q_budget"]
    lead = d["events_lead"]
    booth = next(x for x in L if x["kind"] == "booth")

    # ---- workspace
    r = rng(seed + 17)
    write_csv(os.path.join(ws, "expense_lines_2026-04-01_to_2026-06-30.csv"),
              ["Report ID", "Line", "Employee", "Expense Date", "Merchant", "Category", "Amount", "Cost Center", "Status"],
              [[x["report"], x["line"], f"{x['emp']['first']} {x['emp']['last']}", x["date"].strftime("%m/%d/%Y"), x["merchant"],
                x["cat"], money_str(x["amt"], 1), cc_written(r, x["cc"]) if x["cc"] else "", x["status"]] for x in L],
              preamble=["Expense lines - approval activity 04/01/2026 to 06/30/2026", ""], crlf=True)
    write_xlsx(os.path.join(ws, "cost_centers.xlsx"), {
        "Cost centers": {"merged_title": "Chart of cost centers - FY2026", "header": ["Code", "Cost center", "Department", "Owner"],
                         "rows": [[c, n, dep, ""] for c, n, dep in CENTERS], "widths": {"B": 22, "C": 14}},
        "People": {"header": ["Employee", "Home cost center", "Title"],
                   "rows": sorted([[f"{e['last']}, {e['first']}", int(e["home"]), e["dept"] + " team"] for e in d["staff"]]),
                   "widths": {"A": 24, "B": 18, "C": 18}}}, creator="Finance")
    write_text(os.path.join(ws, "budget_note_from_hiroshi.txt"),
               "Q2 expense report - what I need\n\n"
               "Spend by department for April, May and June, and a short memo on anyone over budget.\n\n"
               "Budgets below are the annual expense budgets the partners approved in January. We phase them evenly\n"
               "through the year.\n\n"
               + "".join(f"  {k:<11} ${d['annual'][k]:,}\n" for k in DEPTS) +
               "\nOnly lines that were approved or already reimbursed are spend. Put each expense in the month it was\n"
               "incurred, not the month it was approved. Q1 is closed, so anything dated March stays out even if it\n"
               "was approved in April.\n\n"
               "If someone left the cost center blank, charge it to their home cost center on the People tab.\n\n"
               "- Hiroshi\n")
    write_email_thread(os.path.join(ws, "email_thread_nab_booth.txt"), [
        {"from": f"{lead['first']} {lead['last']} <{lead['first'].lower()}@vantagepointmedia.com>", "to": "Hiroshi Tanaka <hiroshi@vantagepointmedia.com>",
         "date": "Tue, 21 Apr 2026 10:02", "subject": "NAB booth on my card",
         "body": (f"The NAB Show booth (${d['booth_amt']:,.2f}, {booth['report']} line {booth['line']}) went through on my card "
                  "and the tool coded it to Events. The booth was really for the sales team's client meetings. Could we split it "
                  "half Events, half Sales?")},
        {"from": "Marcus Reed <marcus@vantagepointmedia.com>", "to": "Hiroshi Tanaka <hiroshi@vantagepointmedia.com>",
         "date": "Tue, 21 Apr 2026 11:37", "subject": "RE: NAB booth on my card",
         "body": "A split works for me."},
        {"from": "Hiroshi Tanaka <hiroshi@vantagepointmedia.com>", "to": f"{lead['first']} {lead['last']}, Marcus Reed",
         "date": "Wed, 22 Apr 2026 08:15", "subject": "RE: NAB booth on my card",
         "body": ("No split. Trade shows moved into the Sales budget in January, so the whole booth is Sales - East (3100). "
                  "I cannot recode it in the tool after reimbursement, so whoever builds the quarterly report please move it by hand.")},
        {"from": f"{lead['first']} {lead['last']} <{lead['first'].lower()}@vantagepointmedia.com>", "to": "Hiroshi Tanaka",
         "date": "Wed, 22 Apr 2026 08:40", "subject": "RE: NAB booth on my card", "body": "Understood, thanks."}])

    # ---- reference
    write_csv(os.path.join(ref, "dept_month.csv"), ["department"] + MONTHS + ["q2_total", "q2_budget", "over_under"],
              [[k] + [f"{t[(k, m)]:.2f}" for m in MONTHS] + [f"{t[(k, 'Q2')]:.2f}", q[k], f"{d['over'][k]:.2f}"] for k in DEPTS])
    write_json(os.path.join(ref, "notes.json"), {
        "total": t["total"], "booth_amount": d["booth_amt"], "booth_line": booth["line"], "over_budget": {k: d["over"][k] for k in DEPTS},
        "annual_budget": d["annual"], "excluded_lines": {"rejected_or_draft": sum(1 for x in L if x["status"] in ("Rejected", "Draft")),
                                                          "march_dated": sum(1 for x in L if x["kind"] == "march")},
        "blank_cost_center_lines": sum(1 for x in L if not x["cc"]),
        "naive_q2": {"no_booth_move": {k: d["no_booth"][(k, "Q2")] for k in DEPTS}, "blank_dropped": {k: d["no_blank"][(k, "Q2")] for k in DEPTS}}})

    # ---- reference solution
    rows = [[x["line"], x["date"].isoformat(), f"{x['date'].year}-{x['date'].month:02d}", f"{x['emp']['first']} {x['emp']['last']}",
             x["merchant"], x["cat"], x["amt"], truth_cc(x), truth_dept(x), x["status"], 1 if counted(x) else 0] for x in L]
    note = ("Spend by expense date; approved and reimbursed lines only; March-dated lines excluded. Blank cost centers use the "
            "employee's home cost center. The NAB booth is moved to Sales - East per Hiroshi. Q2 budget = annual / 4.")
    write_xlsx(os.path.join(sol, "dept_expenses.xlsx"), report_workbook(rows, d["annual"], note), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    over_words = r"(\bover\b|\bexceed|\babove\b|\boverr?un|\boverspen[dt]|\bbeyond\b)"
    write_task_yaml(HERE, {
        "id": "dept-expense-report", "track": "desk", "category": "reports",
        "title": "Q2 expenses by department against budget",
        "ask": ("Hiroshi wants Q2 expenses by department, month by month, and a note on who went over budget. Build it as "
                "dept_expenses.xlsx with live formulas and write the memo as memo.md. His note and the booth thread are in "
                "the folder with the export.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the export writes cost centers four ways ('4200', 'CC-4200', '4200 - Events', 'Events (4200)') and twelve cost centers "
            "roll up to five departments through cost_centers.xlsx; a group-by on the raw column gives neither departments nor "
            "stable groups (check: Marketing Q2 total)",
            "13 lines have no cost center, most of them Production shoot costs; Hiroshi's note sends them to the employee's home "
            "cost center on the second (People) sheet, which writes names 'Last, First'; dropping them leaves Production under "
            "budget (checks: Production Q2 total; memo says Production is over budget)",
            "the budgets in the note are annual and phased evenly, so the Q2 budget is a quarter of each figure; compared with the "
            "annual figure nobody is over (checks: memo says Sales is over budget; memo carries both overrun amounts)",
            "the NAB booth was coded to Events; the thread first proposes a half-and-half split, then the CFO's later message moves "
            "all of it to Sales - East; left in Marketing, Marketing looks over and Sales under, and split, both totals are wrong "
            "(checks: Sales Q2 total; Marketing Q2 total; memo says Sales is over budget)",
            "Rejected and Draft lines sit in the same export and are not spend (check: total Q2 spend)",
            "the export is by approval activity, so seven March-dated expenses approved in April are in it and belong to closed Q1 "
            "(check: total Q2 spend)",
            "amounts are '$1,234.56' text, dates are MM/DD/YYYY and the export has a two-line preamble with CRLF endings "
            "(check: total Q2 spend)",
        ],
        "checks": [
            {"type": "file_exists", "name": "dept_expenses.xlsx exists", "path": "dept_expenses.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "dept_expenses.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "dept_expenses.xlsx"},
            {"type": "xlsx_value_present", "name": "Sales Q2 total (booth moved in)", "path": "dept_expenses.xlsx",
             "expected": t[("Sales", "Q2")], "rel_tol": cent_tol(t[("Sales", "Q2")], 0.005), "near_text": "sales"},
            {"type": "xlsx_value_present", "name": "Marketing Q2 total (booth moved out)", "path": "dept_expenses.xlsx",
             "expected": t[("Marketing", "Q2")], "rel_tol": cent_tol(t[("Marketing", "Q2")], 0.005), "near_text": "marketing"},
            {"type": "xlsx_value_present", "name": "Production Q2 total (blank cost centers resolved)", "path": "dept_expenses.xlsx",
             "expected": t[("Production", "Q2")], "rel_tol": cent_tol(t[("Production", "Q2")], 0.005), "near_text": "production"},
            {"type": "xlsx_value_present", "name": "total Q2 spend", "path": "dept_expenses.xlsx",
             "expected": t["total"], "rel_tol": cent_tol(t["total"], 0.005), "near_text": "total"},
            {"type": "text_sentence_matches", "name": "memo says Sales is over budget", "path": "memo.md",
             "all": [r"\bsales\b", over_words, r"\bbudget"],
             "none": [r"\bsales\b\W+(is|was|came in|finished|ended|stayed|remained|are)?\W*(under|within|below|inside)\b",
                      r"(\bnot\b|n't\b|\bnever\b)[^.;]{0,15}\bover\b"]},
            {"type": "text_sentence_matches", "name": "memo says Production is over budget", "path": "memo.md",
             "all": [r"\bproduction\b", over_words, r"\bbudget"],
             "none": [r"\bproduction\b\W+(is|was|came in|finished|ended|stayed|remained)?\W*(under|within|below|inside)\b",
                      r"(\bnot\b|n't\b|\bnever\b)[^.;]{0,15}\bover\b"]},
            {"type": "text_numbers_present", "name": "memo carries both overrun amounts", "path": "memo.md",
             "numbers": [d["over"]["Sales"], d["over"]["Production"]], "rel_tol": 0.01},
        ],
    })
    print(f"seed={seed} lines={len(L)} q2={ {k: t[(k, 'Q2')] for k in DEPTS} } total={t['total']} budget={q} over={d['over']}")


def write_naive(d: dict, out: str) -> None:
    """Every line in the export, raw cost center digits mapped to departments with blanks left unassigned, the booth
    left in Events, annual budgets compared with the quarter."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for x in d["lines"]:
        dept = CC_DEPT[x["cc"]] if x["cc"] else "Unassigned"
        rows.append([x["line"], x["date"].isoformat(), f"{x['date'].year}-{x['date'].month:02d}", x["emp"]["first"], x["merchant"],
                     x["cat"], x["amt"], x["cc"], dept, x["status"], 1])
    wb = report_workbook(rows, {k: v * 4 for k, v in d["annual"].items()}, "naive")
    write_xlsx(os.path.join(out, "dept_expenses.xlsx"), wb, creator="naive")
    write_text(os.path.join(out, "memo.md"), "# Q2 expenses\n\nEvery department is within its budget for the year. Marketing spent the most, "
               "mainly on advertising and the NAB booth.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(800):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 800 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
