#!/usr/bin/env python3
"""budget-vs-actual: a marina's annual budget and its GL detail export to a first-half variance report.

    python gen.py [--seed N]

Business: Cove Point Marina (slips, winter storage, haul-outs and a service yard) moved to a new accounting
system in January. The owners approved an annual budget in December; the bookkeeper exported the general
ledger detail on 10 July. Nobody has compared the two yet.

Traps (each caught by a check, see task.yaml):
  * the new system pads account numbers to six digits (410000); the budget has four (4100), and two
    budget lines are split over sub-accounts (410010 transient slips, 530010 diesel)
                                                          (checks: slip rentals actual; fuel variance)
  * the budget is annual; most lines are spread evenly, but five follow the monthly profile in Dale's
    email (slips 35% by June, winter storage 56%, launch/haul-out and shrink-wrap 52%, dock staff 44%)
                                                          (checks: slip rentals budget; winter storage variance; dock staff variance)
  * the GL shows income as negative numbers in parentheses; customer credits on income accounts and
    vendor refunds on cost accounts carry the opposite sign, so taking absolute values inflates both
                                                          (checks: slip rentals actual; fuel variance)
  * variance is favourable-positive: income above budget and costs below budget are positive, costs over
    budget are negative; actual minus budget everywhere flips every cost line (checks: fuel variance; dock staff variance)
  * the export runs to 10 July, so early-July postings sit in it       (checks: slip rentals actual; total expenses actual)
  * crane and equipment rental has spending and no budget line; it belongs on the report with a zero budget
                                                          (check: total expenses actual)
  * the budget sheet carries last year's actuals beside this year's budget, section rows and static totals
                                                          (check: slip rentals budget)
"""
from __future__ import annotations

import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# monthly percentage of the annual budget, January..December
PROFILES = {
    "slips": [0, 0, 0, 5, 12, 18, 20, 20, 15, 10, 0, 0],
    "storage": [16, 16, 16, 8, 0, 0, 0, 0, 0, 8, 18, 18],
    "launch": [0, 0, 6, 24, 18, 4, 0, 0, 4, 20, 22, 2],
    "dock": [0, 0, 0, 8, 16, 20, 20, 20, 16, 0, 0, 0],
}
# code, budget name, type, annual base, profile, GL sub-accounts [(suffix, GL description, share of activity)]
ACCOUNTS = [
    (4100, "Slip rentals", "Income", 540000, "slips",
     [("00", "Slip Rentals - Seasonal", 0.7), ("10", "Slip Rentals - Transient", 0.3)]),
    (4200, "Winter storage", "Income", 320000, "storage", [("00", "Winter Storage", 1.0)]),
    (4300, "Launch and haul-out", "Income", 168000, "launch", [("00", "Launch & Haul-Out Fees", 1.0)]),
    (4400, "Service department labor", "Income", 236000, None, [("00", "Service Labor", 1.0)]),
    (5100, "Yard crew wages", "Expense", 410000, None, [("00", "Yard Crew Wages", 1.0)]),
    (5200, "Seasonal dock staff", "Expense", 152000, "dock", [("00", "Dock Staff Wages - Seasonal", 1.0)]),
    (5300, "Fuel", "Expense", 58800, None, [("00", "Fuel - Gasoline", 0.55), ("10", "Fuel - Diesel", 0.45)]),
    (5400, "Travel lift and equipment repairs", "Expense", 36000, None, [("00", "Travel Lift & Equipment Repairs", 1.0)]),
    (5500, "Shrink-wrap and blocking supplies", "Expense", 41000, "launch", [("00", "Shrink-Wrap & Blocking", 1.0)]),
    (6100, "Office salaries", "Expense", 132000, None, [("00", "Office Salaries", 1.0)]),
    (6200, "Harbor lease", "Expense", 54000, None, [("00", "Harbor Lease - Port", 1.0)]),
    (6300, "Insurance", "Expense", 38400, None, [("00", "Insurance - Marina Operators", 1.0)]),
    (6400, "Vehicle and forklift leases", "Expense", 72000, None, [("00", "Vehicle & Forklift Leases", 1.0)]),
    (6500, "Marketing", "Expense", 18000, None, [("00", "Advertising & Marketing", 1.0)]),
    (6600, "Software and phones", "Expense", 12600, None, [("00", "Software & Telephone", 1.0)]),
    (6700, "Professional fees", "Expense", 15000, None, [("00", "Accounting & Legal", 1.0)]),
]
UNBUDGETED = (6750, "Crane and equipment rental", "Expense", [("00", "Crane & Equipment Rental", 1.0)])
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PERIOD_END = date(2026, 6, 30)
CUSTOMERS = ["Okafor - M/V Tidewater", "Brooks - S/V Halcyon", "Patel - M/V Second Wind", "Lindqvist - S/V Kestrel",
             "Garcia - M/V Blue Moon", "Kingfisher Charters", "Cove Point Yacht Club", "Haddad - S/V Morning Star",
             "Nguyen - M/V Low Tide", "Harbor Light Marine"]
TRANSIENT = ["Transient - Dockwa booking", "Transient - walk-up", "Transient - rally group"]
VENDORS = {5100: ["Payroll - ADP"], 5200: ["Payroll - ADP"], 5300: ["Shell Marine Fuel", "Pilot Diesel"],
           5400: ["Hoist Tech Services", "Travelift Parts Depot"], 5500: ["Dr. Shrink Supply", "Brownell Boat Stands"],
           6100: ["Payroll - ADP"], 6200: ["Port of Cove Point"], 6300: ["Everline Insurance"], 6400: ["Dorsey Freight Leasing"],
           6500: ["Vantage Point Media"], 6600: ["Kestrel Analytics", "Verizon Wireless"],
           6700: ["Mossbank Accounting", "Copperfield Law"], 6750: ["Sunbelt Rentals", "Coastal Crane Rental"]}


def ytd_share(profile: str | None) -> float:
    if profile is None:
        return 6 / 12
    return sum(PROFILES[profile][:6]) / 100


def build(seed: int) -> dict:
    r = rng(seed)
    accts = []
    for code, name, typ, base, prof, subs in ACCOUNTS:
        annual = round(base * r.uniform(0.9, 1.1), -2)
        last_year = round(annual * r.uniform(0.86, 1.04), -2)
        accts.append({"code": code, "name": name, "type": typ, "annual": annual, "last_year": last_year,
                      "profile": prof, "subs": subs})
    accts.append({"code": UNBUDGETED[0], "name": UNBUDGETED[1], "type": "Expense", "annual": 0.0, "last_year": None,
                  "profile": None, "subs": UNBUDGETED[3], "unbudgeted": True})
    by_code = {a["code"]: a for a in accts}

    rows = []   # {date, type, num, name, gl, desc, memo, amount (GL sign), code, kind}
    seq = {"inv": 10400, "bill": 7100, "je": 300, "cm": 900}

    def post(a: dict, d: date, amt_budget_sense: float, kind: str = "normal", memo: str = "") -> None:
        """amt_budget_sense is positive income on income accounts and positive cost on expense accounts."""
        suffix, desc, _ = r.choices(a["subs"], weights=[s[2] for s in a["subs"]])[0]
        sign = -1 if a["type"] == "Income" else 1
        if a["type"] == "Income":
            who = r.choice(TRANSIENT if suffix == "10" else CUSTOMERS)
            typ = "Credit Memo" if kind == "credit" else "Invoice"
            num = ""                    # numbered in date order below
        else:
            vendor = r.choice(VENDORS[a["code"]])
            if a["code"] in (5100, 5200, 6100):
                typ, num, who = "Journal", "", vendor
            elif kind == "refund":
                typ, num, who = "Vendor Credit", f"VC-{seq['bill']}", vendor; seq["bill"] += 1
            else:
                typ, num, who = "Bill", f"B-{seq['bill']}", vendor; seq["bill"] += 1
        if kind in ("credit", "refund"):
            sign = -sign          # opposite sign to the account's normal side
        rows.append({"date": d, "type": typ, "num": num, "name": who, "gl": f"{a['code']}{suffix}", "desc": desc,
                     "memo": memo, "amount": round(sign * amt_budget_sense, 2), "code": a["code"], "kind": kind})

    for a in accts:
        # each line runs over or under budget for the half by a visible margin
        bias = r.uniform(0.86, 0.94) if r.random() < 0.5 else r.uniform(1.06, 1.14)
        for m in range(1, 8):
            if a.get("unbudgeted"):
                target = r.uniform(1400, 3600) if m in (4, 5, 6, 7) else 0.0
            elif a["profile"]:
                target = a["annual"] * PROFILES[a["profile"]][m - 1] / 100 * bias * r.uniform(0.9, 1.1)
            else:
                target = a["annual"] / 12 * bias * r.uniform(0.9, 1.1)
            if target <= 0:
                continue
            hi = 28
            if m == 7:
                if a["code"] not in (4100, 4400, 5100, 5200, 5300, 6200, 6400, 6750):
                    continue
                target *= 0.3          # the first ten days of July
                hi = 9
            k = 1 if a["code"] in (6200, 6300, 6400) else (2 if a["code"] in (5100, 5200, 6100) else r.randint(2, 5))
            cuts = sorted(r.uniform(0.15, 0.85) for _ in range(k - 1))
            for lo_c, hi_c in zip([0.0] + cuts, cuts + [1.0]):
                post(a, date(2026, m, r.randint(1, hi)), round(target * (hi_c - lo_c), 2))

    # customer credit memos on income accounts (reduce income) and vendor refunds on cost accounts (reduce cost)
    for code, n, months in ((4100, 3, (4, 6)), (4200, 1, (1, 4)), (4400, 1, (1, 6))):
        for _ in range(n):
            post(by_code[code], date(2026, r.randint(*months), r.randint(1, 28)), round(r.uniform(380, 1850), 2),
                 kind="credit", memo=r.choice(["Credit - slip not ready", "Credit - service complaint", "Billing correction"]))
    for code, n in ((5300, 2), (5500, 1), (5400, 1)):
        for _ in range(n):
            post(by_code[code], date(2026, r.randint(2, 6), r.randint(1, 28)), round(r.uniform(160, 940), 2),
                 kind="refund", memo=r.choice(["Refund - overcharge", "Returned parts", "Fuel rebate"]))

    rows.sort(key=lambda x: (x["date"], x["gl"], x["num"], x["amount"]))
    for x in rows:                      # the company's own documents are numbered in date order
        if x["type"] == "Invoice":
            x["num"] = str(seq["inv"]); seq["inv"] += r.randint(1, 3)
        elif x["type"] == "Credit Memo":
            x["num"] = f"CM-{seq['cm']}"; seq["cm"] += 1
        elif x["type"] == "Journal":
            x["num"] = f"PR-{seq['je']}"; seq["je"] += 1

    # ---- truth from the structures ----
    actual = {a["code"]: 0.0 for a in accts}
    july = {a["code"]: 0.0 for a in accts}
    for x in rows:
        a = by_code[x["code"]]
        v = -x["amount"] if a["type"] == "Income" else x["amount"]
        if x["date"] <= PERIOD_END:
            actual[a["code"]] += v
        else:
            july[a["code"]] += v
    out = []
    for a in accts:
        yb = round(a["annual"] * ytd_share(a["profile"]), 2)
        ac = round(actual[a["code"]], 2)
        var = round(ac - yb if a["type"] == "Income" else yb - ac, 2)
        out.append({**a, "ytd_budget": yb, "actual": ac, "variance": var,
                    "naive_budget": round(a["annual"] / 2, 2),
                    "naive_actual": round(sum(abs(x["amount"]) for x in rows if x["code"] == a["code"]), 2),
                    "july": round(july[a["code"]], 2)})
    tot = {}
    for typ in ("Income", "Expense"):
        sel = [o for o in out if o["type"] == typ]
        tot[typ] = {"ytd_budget": round(sum(o["ytd_budget"] for o in sel), 2),
                    "actual": round(sum(o["actual"] for o in sel), 2),
                    "variance": round(sum(o["variance"] for o in sel), 2),
                    "annual": round(sum(o["annual"] for o in sel), 2)}
    return {"accts": out, "by_code": {o["code"]: o for o in out}, "rows": rows, "tot": tot}


def acceptable(d: dict) -> bool:
    b = d["by_code"]
    slips, storage, dock, fuel = b[4100], b[4200], b[5200], b[5300]

    def apart(v, others, rel=0.02):
        return all(abs(v - o) > max(abs(v) * rel, 1.0) for o in others if o is not None)

    # the pinned figures stand apart from every other number a natural row carries
    for o, keys in ((slips, ("ytd_budget", "actual")), (storage, ("variance",)), (dock, ("variance",)), (fuel, ("variance",))):
        row = {"annual": o["annual"], "ytd_budget": o["ytd_budget"], "actual": o["actual"], "variance": o["variance"],
               "naive_budget": o["naive_budget"], "naive_actual": o["naive_actual"], "last_year": o["last_year"],
               "flipped": -o["variance"], "naive_variance": o["naive_actual"] - o["naive_budget"]}
        for key in keys:
            if not apart(o[key], [v for k, v in row.items() if k != key]):
                return False
        if abs(o["variance"]) < max(0.05 * o["ytd_budget"], 900):
            return False
    if fuel["variance"] >= 0:
        return False
    # slip rentals actual must move under each naive reading: July, credits, the transient sub-account
    slip_rows = [x for x in d["rows"] if x["code"] == 4100]
    transient = sum(-x["amount"] for x in slip_rows if x["gl"].endswith("10") and x["date"] <= PERIOD_END)
    if transient < 0.2 * slips["actual"] or slips["july"] < 0.02 * slips["actual"]:
        return False
    te = d["tot"]["Expense"]
    if not apart(te["actual"], [te["ytd_budget"], te["variance"], te["annual"], d["tot"]["Income"]["actual"]], 0.01):
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(accts: list[dict], gl_rows: list[list]) -> dict:
    n_gl = len(gl_rows) + 1
    last = len(accts) + 1
    rows = []
    for i, a in enumerate(accts, start=2):
        rows.append([a["code"], a["name"], a["type"], a["annual"],
                     f"=ROUND(D{i}*VLOOKUP(A{i},Profile!$A$2:$N${last},14,FALSE),2)",
                     f"=ROUND(SUMIFS(GL!$C$2:$C${n_gl},GL!$A$2:$A${n_gl},A{i}),2)",
                     f'=IF(C{i}="Income",F{i}-E{i},E{i}-F{i})'])
    rows.append([])
    ti, te = last + 2, last + 3
    for label, typ in (("Total income", "Income"), ("Total expenses", "Expense")):
        rows.append(["", label, ""] + [f'=SUMIF($C$2:$C${last},"{typ}",{c}$2:{c}${last})' for c in "DEFG"])
    rows.append(["", "Net income", "", f"=D{ti}-D{te}", f"=E{ti}-E{te}", f"=F{ti}-F{te}", f"=G{ti}+G{te}"])
    rows.append([])
    rows.append(["", "Variance is positive when it helps profit (income above budget, costs below budget) and negative "
                     "when it hurts. Seasonal lines use the monthly profile from Dale's email; the rest are one twelfth "
                     "a month. Crane and equipment rental has no budget line."])
    prof_rows = []
    for i, a in enumerate(accts, start=2):
        months = PROFILES[a["profile"]] if a["profile"] else [None] * 12
        prof_rows.append([a["code"], *months, f"=IF(SUM(B{i}:M{i})=0,6/12,SUM(B{i}:G{i})/SUM(B{i}:M{i}))"])
    return {
        "Variance": {"header": ["Acct", "Account", "Type", "FY2026 budget", "Budget Jan-Jun", "Actual Jan-Jun",
                                "Variance (+ good / - bad)"],
                     "rows": rows, "widths": {"B": 36, "D": 15, "E": 16, "F": 16, "G": 24}},
        "Profile": {"header": ["Acct", *MONTH_NAMES, "Share Jan-Jun"], "rows": prof_rows},
        "GL": {"header": ["acct", "date", "amount (income and cost positive)", "gl account"], "rows": gl_rows,
               "widths": {"B": 12, "C": 30}},
    }


def gl_clean_rows(d: dict) -> list[list]:
    out = []
    for x in d["rows"]:
        if x["date"] > PERIOD_END:
            continue
        a = d["by_code"][x["code"]]
        v = -x["amount"] if a["type"] == "Income" else x["amount"]
        out.append([x["code"], x["date"].isoformat(), round(v, 2), x["gl"]])
    return out



def cent_tolerant(spec: dict) -> dict:
    """Figures computed from exact source data tie to the cent: every workbook pin gets a tolerance under 1.00."""
    for c in spec["checks"]:
        if c["type"] == "xlsx_value_present" and not c.get("rounding"):
            exp = abs(float(c["expected"]))
            c["rel_tol"] = min(float(c.get("rel_tol", 0.005)), float(f"{0.9 / max(exp, 1.0):.2g}"))
    return spec


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    b, tot = d["by_code"], d["tot"]
    budgeted = [a for a in d["accts"] if not a.get("unbudgeted")]

    # ---- workspace ----
    inc = [a for a in budgeted if a["type"] == "Income"]
    exp = [a for a in budgeted if a["type"] == "Expense"]
    ly_inc, ly_exp = sum(a["last_year"] for a in inc), sum(a["last_year"] for a in exp)
    bi, be = sum(a["annual"] for a in inc), sum(a["annual"] for a in exp)
    brows = [["", "INCOME"]]
    brows += [[a["code"], a["name"], a["last_year"], a["annual"], "seasonal - see my email" if a["profile"] else ""] for a in inc]
    brows += [["", "Total income", ly_inc, bi], [], ["", "EXPENSES"]]
    brows += [[a["code"], a["name"], a["last_year"], a["annual"], "seasonal - see my email" if a["profile"] else ""] for a in exp]
    brows += [["", "Total expenses", ly_exp, be], [], ["", "Net income", ly_inc - ly_exp, bi - be]]
    write_xlsx(os.path.join(ws, "budget_FY2026_approved.xlsx"), {"Budget": {
        "merged_title": "Cove Point Marina - FY2026 operating budget",
        "preamble": [["Approved by the owners 12 Dec 2025"], []],
        "header": ["Acct", "Account", "FY2025 actual", "FY2026 budget", "Notes"],
        "rows": brows, "widths": {"B": 36, "C": 15, "D": 15, "E": 24},
        "number_formats": {"C": "#,##0", "D": "#,##0"}}}, creator="Dale Hoffman")

    gl = [[x["date"].strftime("%m/%d/%Y"), x["type"], x["num"], x["name"], x["gl"], x["desc"], x["memo"],
           money_str(x["amount"], 5)] for x in d["rows"]]
    write_csv(os.path.join(ws, "gl_detail_2026-01-01_to_2026-07-10.csv"),
              ["Date", "Transaction Type", "Num", "Name", "Account", "Account Description", "Memo", "Amount"], gl,
              preamble=["Cove Point Marina", "General Ledger Detail  01/01/2026 - 07/10/2026", "Accrual basis", ""],
              crlf=True)

    def prow(label, p):
        return f"  {label:<37}" + " ".join(f"{v:>3}" for v in p)
    table = "\n".join([f"  {'':<37}" + " ".join(f"{mn:>3}" for mn in MONTH_NAMES),
                       prow("Slip rentals", PROFILES["slips"]),
                       prow("Winter storage", PROFILES["storage"]),
                       prow("Launch and haul-out", PROFILES["launch"]),
                       prow("Shrink-wrap and blocking supplies", PROFILES["launch"]),
                       prow("Seasonal dock staff", PROFILES["dock"])])
    write_email_thread(os.path.join(ws, "email_from_dale.txt"), [
        {"from": "Dale Hoffman <dale@covepointmarina.com>", "to": "you", "date": "Mon, 13 Jul 2026 07:48",
         "subject": "first half vs budget",
         "body": ("The owners meet next week and want to see how January to June went against the budget, line by line. "
                  "The approved budget is the file from December; the GL detail is what Tanya exported from the new "
                  "system on Friday.\n\n"
                  "The budget is annual. Most lines we just spread evenly, a twelfth a month. The seasonal ones we "
                  "budgeted by month as a percentage of the year:\n\n" + table + "\n\nEverything else is even.")},
        {"from": "Dale Hoffman <dale@covepointmarina.com>", "to": "you", "date": "Mon, 13 Jul 2026 08:05",
         "subject": "RE: first half vs budget",
         "body": ("Forgot two things about the new system. It pads the account numbers out to six digits - the first "
                  "four are the budget account and the last two are sub-accounts Tanya set up, so anything starting "
                  "4100 is slip rentals. And it shows income as negative numbers, which confuses everyone. On the "
                  "report I want income and costs both as positive numbers the way the budget has them.\n\n"
                  "For the variance column, positive should mean it helped us - more income than budget or less "
                  "spent than budget - and negative means it hurt. If something has spending but no budget line, "
                  "put it on with a zero budget.")}])

    # ---- reference ----
    write_csv(os.path.join(ref, "variance.csv"), ["acct", "account", "type", "annual_budget", "ytd_budget", "ytd_actual", "variance"],
              [[a["code"], a["name"], a["type"], f"{a['annual']:.2f}", f"{a['ytd_budget']:.2f}", f"{a['actual']:.2f}",
                f"{a['variance']:.2f}"] for a in d["accts"]])
    write_json(os.path.join(ref, "notes.json"), {
        "totals": tot, "july_rows": sum(1 for x in d["rows"] if x["date"] > PERIOD_END), "gl_rows": len(d["rows"]),
        "profiles": PROFILES, "unbudgeted": UNBUDGETED[0],
        "naive": {str(a["code"]): {"budget": a["naive_budget"], "actual": a["naive_actual"]} for a in d["accts"]}})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "variance.xlsx"), report_sheets(d["accts"], gl_clean_rows(d)), creator="reference")

    slips, fuel = b[4100], b[5300]
    write_task_yaml(HERE, cent_tolerant({
        "id": "budget-vs-actual", "track": "desk", "category": "spreadsheet",
        "title": "First-half budget vs actual, line by line",
        "ask": ("The owners want to see how January to June went against the budget, line by line. Put it together as "
                "variance.xlsx with live formulas from the budget file and the GL export - Dale's email says how the "
                "budget is spread and how he wants the variances shown.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the GL pads account numbers to six digits (410000) while the budget has four (4100), and slip rentals and "
            "fuel are split over sub-accounts (410010 transient slips, 530010 diesel), so a join on the raw code or on the "
            "xx00 accounts alone drops activity (checks: slip rentals actual; fuel variance)",
            "the budget is annual; five lines follow Dale's monthly profile (slip rentals 35% by June, winter storage 56%, "
            "launch/haul-out and shrink-wrap 52%, seasonal dock staff 44%) and the rest are a twelfth a month; halving "
            "every line misstates them (checks: slip rentals budget Jan-Jun; winter storage variance; dock staff variance)",
            "income comes out of the GL as negative numbers in parentheses, and customer credit memos on income accounts "
            "and vendor refunds on cost accounts carry the opposite sign; absolute values add them instead of netting "
            "(checks: slip rentals actual; fuel variance)",
            "variance is favourable-positive per the email: income over budget and costs under budget are positive, "
            "costs over budget negative; actual minus budget on every line flips each cost variance "
            "(checks: fuel variance; dock staff variance)",
            "the export runs to 10 July, so early-July invoices, bills and wages sit in the file and are not first-half "
            "actuals (checks: slip rentals actual; total expenses actual)",
            "crane and equipment rental (675000) has spending and no budget line and must be on the report with a zero budget "
            "(check: total expenses actual)",
            "the budget sheet has a merged title, section rows, static totals and last year's actuals beside the FY2026 "
            "budget column, and the GL export carries a four-line report preamble and CRLF endings "
            "(check: slip rentals budget Jan-Jun)",
        ],
        "checks": [
            {"type": "file_exists", "name": "variance.xlsx exists", "path": "variance.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "variance.xlsx", "min_count": 16},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "variance.xlsx"},
            {"type": "xlsx_value_present", "name": "slip rentals budget Jan-Jun (seasonal, 35%)", "path": "variance.xlsx",
             "expected": slips["ytd_budget"], "rel_tol": 0.005, "near_text": "slip"},
            {"type": "xlsx_value_present", "name": "slip rentals actual (transient sub-account, credits, no July)", "path": "variance.xlsx",
             "expected": slips["actual"], "rel_tol": 0.005, "near_text": "slip"},
            {"type": "xlsx_value_present", "name": "winter storage variance (seasonal income)", "path": "variance.xlsx",
             "expected": b[4200]["variance"], "rel_tol": 0.01, "near_text": "winter storage"},
            {"type": "xlsx_value_present", "name": "dock staff variance (seasonal cost, favourable-positive)", "path": "variance.xlsx",
             "expected": b[5200]["variance"], "rel_tol": 0.01, "near_text": "dock staff"},
            {"type": "xlsx_value_present", "name": "fuel variance (over budget is negative)", "path": "variance.xlsx",
             "expected": fuel["variance"], "rel_tol": 0.01, "near_text": "fuel"},
            {"type": "xlsx_value_present", "name": "total expenses actual", "path": "variance.xlsx",
             "expected": tot["Expense"]["actual"], "rel_tol": 0.005, "near_text": "total"},
        ],
    }))
    print(f"seed={seed} gl_rows={len(d['rows'])}")
    for code in (4100, 4200, 5200, 5300, 6750):
        a = b[code]
        print(f"  {code} {a['name']}: annual {a['annual']} ytd_budget {a['ytd_budget']} actual {a['actual']} "
              f"variance {a['variance']} | naive budget {a['naive_budget']} naive actual {a['naive_actual']} july {a['july']}")
    print("  totals:", tot)


if __name__ == "__main__":
    s = argparse_seed()
    for attempt in range(500):
        if acceptable(build(s * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(s * 1000 + attempt)
