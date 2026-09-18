#!/usr/bin/env python3
"""Deterministic seed generator for the expense-claims build task.

    python gen.py [--seed N]

Writes:
  seed/employees.csv        HR export: one exact duplicate row and three people re-imported with an
                            upper-cased email and an unpadded employee id; manager emails in mixed case
  seed/expense_policy.csv   20 categories x 3 grades: per-item limits as "250", "$1,500.00", or "no limit"
  seed/claims.csv           claim lines (a claim has one to four lines): duplicated lines, currency
                            strings, employee ids padded three ways, one expense dated after submission
  reference/counts.json     every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the public variant checklist.md quotes. Other seeds re-roll staff names, claim contents, and
amounts; the managers named in the ask and the policy table stay fixed. counts.json is recomputed.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, write_csv, write_text  # noqa: E402

SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")
DOMAIN = "tallgrass.io"
COMPANY = "Tallgrass Analytics"
RECEIPT_THRESHOLD = 75.00
GRADES = ["Staff", "Manager", "Executive"]
CEO = ("Victor Almeida", "Executive", "Chief Executive Officer")
MANAGERS = [  # name, department, number of direct reports
    ("Grace Liu", "Sales", 12),
    ("Samuel Okoye", "Engineering", 15),
    ("Hannah Weiss", "Customer Success", 9),
    ("Luis Moreno", "Marketing", 7),
    ("Ellen Park", "Finance & Operations", 5),
    ("Priya Raman", "Product", 5),
]
RESTRICTED = "Grace Liu"
ADMIN = "Ellen Park"
STAFF_TITLES = {
    "Sales": ["Account Executive", "Sales Development Rep", "Solutions Consultant"],
    "Engineering": ["Software Engineer", "Senior Software Engineer", "Data Engineer", "QA Engineer"],
    "Customer Success": ["Customer Success Manager", "Support Specialist", "Implementation Lead"],
    "Marketing": ["Content Marketer", "Demand Gen Specialist", "Designer"],
    "Finance & Operations": ["Accountant", "Office Manager", "People Partner"],
    "Product": ["Product Manager", "Product Designer", "UX Researcher"],
}
# category, GL code, Staff, Manager, Executive limit per item (None = no limit), staff-typical range
POLICY = [
    ("Airfare", "6110", 600, 900, None, (180, 580)),
    ("Hotel", "6120", 250, 325, 450, (120, 245)),
    ("Meals - Travel", "6130", 60, 75, 100, (12, 58)),
    ("Client Entertainment", "6140", 150, 300, 600, (40, 145)),
    ("Mileage", "6150", 300, 300, 300, (15, 290)),
    ("Taxi & Rideshare", "6160", 80, 100, 150, (12, 78)),
    ("Parking & Tolls", "6170", 50, 50, 75, (5, 48)),
    ("Rail & Bus", "6180", 200, 250, 300, (20, 190)),
    ("Car Rental", "6190", 120, 150, 200, (45, 115)),
    ("Conference Fees", "6210", 1500, 2000, 3500, (250, 1450)),
    ("Training & Courses", "6220", 1200, 1500, 2500, (150, 1150)),
    ("Books & Subscriptions", "6230", 100, 150, 250, (12, 95)),
    ("Software", "6310", 200, 300, 500, (10, 190)),
    ("Office Supplies", "6320", 100, 150, 200, (8, 95)),
    ("Home Office Equipment", "6330", 400, 500, 750, (40, 390)),
    ("Phone & Internet", "6340", 90, 120, 150, (30, 85)),
    ("Client Gifts", "6410", 75, 150, 250, (20, 72)),
    ("Team Events", "6420", 150, 500, 1000, (40, 145)),
    ("Postage & Shipping", "6510", 100, 150, 200, (5, 95)),
    ("Visa & Passport", "6520", 250, 250, 400, (60, 240)),
]
LIMIT = {c: dict(zip(GRADES, (s, m, e))) for c, _, s, m, e, _ in POLICY}
RANGE = {c: r for c, *_, r in POLICY}
PURPOSES = {
    "travel": ["Client visit - Denver", "Client visit - Chicago", "Customer onboarding trip", "Sales kickoff",
               "Partner summit", "Regional roadshow", "Site visit - Austin"],
    "office": ["Home office setup", "Team supplies", "Quarterly subscriptions", "Onboarding kit"],
    "learning": ["Industry conference", "Certification course", "Q3 training"],
    "people": ["Team offsite", "Client dinner", "Customer appreciation"],
}
PURPOSE_CATS = {
    "travel": ["Airfare", "Hotel", "Meals - Travel", "Taxi & Rideshare", "Parking & Tolls", "Rail & Bus", "Car Rental", "Mileage"],
    "office": ["Office Supplies", "Home Office Equipment", "Software", "Books & Subscriptions", "Phone & Internet", "Postage & Shipping"],
    "learning": ["Conference Fees", "Training & Courses", "Hotel", "Meals - Travel", "Airfare", "Visa & Passport"],
    "people": ["Client Entertainment", "Team Events", "Client Gifts", "Meals - Travel"],
}
DESCRIPTIONS = {
    "Airfare": ["Round trip economy", "One-way flight", "Flight change fee"], "Hotel": ["2 nights", "1 night", "Conference hotel"],
    "Meals - Travel": ["Dinner", "Lunch", "Breakfast"], "Client Entertainment": ["Dinner with client", "Client lunch"],
    "Mileage": ["Drive to client site", "Drive to airport"], "Taxi & Rideshare": ["Airport ride", "Ride to client"],
    "Parking & Tolls": ["Airport parking", "Garage parking"], "Rail & Bus": ["Train ticket", "Bus fare"],
    "Car Rental": ["Rental car 1 day", "Rental car 2 days"], "Conference Fees": ["Registration", "Workshop pass"],
    "Training & Courses": ["Online course", "Certification exam"], "Books & Subscriptions": ["Book", "Annual subscription"],
    "Software": ["Monthly license", "Plugin"], "Office Supplies": ["Notebooks and pens", "Printer toner"],
    "Home Office Equipment": ["Monitor", "Desk chair", "Keyboard"], "Phone & Internet": ["Home internet share", "Phone bill share"],
    "Client Gifts": ["Gift basket", "Thank-you gift"], "Team Events": ["Team lunch", "Offsite activity"],
    "Postage & Shipping": ["Courier", "Shipping samples"], "Visa & Passport": ["Visa fee", "Passport renewal"],
}
N_CLAIMS = {"Paid": 58, "Approved": 14, "Submitted": 30, "Rejected": 10}
N_DUP_LINES = {"Approved": 2, "Paid": 2, "Submitted": 2}
SAFE_DATE_STYLES = [0, 1, 2, 3, 4]
YES = ["Yes", "Yes", "Yes", "Y", "yes", "attached"]


def eid(n: int) -> str:
    return f"E-{n:04d}"


def money_text(v: float, rng: random.Random, force_dollar: bool = False) -> str:
    if force_dollar:
        return f"${v:,.2f}"
    k = rng.random()
    if k < 0.18:
        return f"${v:,.2f}"
    if k < 0.30 and v >= 1000:
        return f"{v:,.2f}"
    if k < 0.40:
        return f"{v:.2f}".rstrip("0").rstrip(".") if v == int(v) else f"{v:.2f}"
    return f"{v:.2f}"


def limit_text(v, rng: random.Random) -> str:
    if v is None:
        return rng.choice(["no limit", "No limit"])
    return rng.choice([f"{v}", f"{v:.2f}", f"${v:,.2f}"]) if v < 1000 else rng.choice([f"${v:,.2f}", f"{v:,.2f}"])


def build(seed: int) -> dict:
    rng = random.Random(seed)

    # ------------------------------------------------------------------ employees
    fixed = {CEO[0]} | {m[0] for m in MANAGERS}
    fixed_first = {n.split()[0] for n in fixed}
    pool = [(f, l) for f in FIRST for l in LAST if f not in fixed_first]
    rng.shuffle(pool)
    surnames_fixed = {n.split()[1] for n in fixed}
    staff_names: list[str] = []
    used_last: dict[str, int] = {}
    for f, l in pool:
        if len(staff_names) == sum(m[2] for m in MANAGERS):
            break
        if l in surnames_fixed or used_last.get(l, 0) >= 2:
            continue
        used_last[l] = used_last.get(l, 0) + 1
        staff_names.append(f"{f} {l}")

    employees: list[dict] = []

    def email_of(name: str) -> str:
        return name.lower().replace(" ", ".") + "@" + DOMAIN

    employees.append({"name": CEO[0], "dept": "Executive", "title": CEO[2], "grade": "Executive", "manager": None})
    for mname, dept, _ in MANAGERS:
        employees.append({"name": mname, "dept": dept, "title": f"{dept} Manager" if dept != "Finance & Operations" else "Finance Manager",
                          "grade": "Manager", "manager": CEO[0]})
    it = iter(staff_names)
    for mname, dept, n in MANAGERS:
        for _ in range(n):
            employees.append({"name": next(it), "dept": dept, "title": rng.choice(STAFF_TITLES[dept]), "grade": "Staff", "manager": mname})
    assert len(employees) == 60
    ids = list(range(1, 61))
    rng.shuffle(ids)
    for e, n in zip(employees, ids):
        e["id"] = eid(n)
        e["num"] = n
        e["email"] = email_of(e["name"])
        e["start"] = date(2017, 3, 1) + timedelta(days=rng.randint(0, 3300))
        e["cost_center"] = {"Executive": "100", "Sales": "210", "Engineering": "310", "Customer Success": "220",
                            "Marketing": "230", "Finance & Operations": "120", "Product": "320"}[e["dept"]]
    by_name = {e["name"]: e for e in employees}
    assert len({e["email"] for e in employees}) == 60

    def manager_email_text(e: dict) -> str:
        if not e["manager"]:
            return ""
        em = by_name[e["manager"]]["email"]
        if rng.random() < 0.22:
            local, _, dom = em.partition("@")
            return rng.choice([".".join(p.capitalize() for p in local.split(".")) + "@" + dom.capitalize(), em.upper()])
        return em

    emp_rows: list[dict] = []
    for e in employees:
        emp_rows.append({"e": e, "role": "unique", "cells": [
            e["id"], e["name"], e["email"], e["dept"], e["title"],
            e["grade"] if rng.random() > 0.12 else e["grade"].lower(),
            manager_email_text(e), date_variant(e["start"], rng.choice(SAFE_DATE_STYLES)), e["cost_center"]]})
    staff = [e for e in employees if e["grade"] == "Staff"]
    grace_reports = [e for e in staff if e["manager"] == RESTRICTED]
    # force at least two of Grace's reports to carry a case-variant manager email (the scope trap)
    variant_reports = rng.sample(grace_reports, 3)
    for r in emp_rows:
        if r["e"] in variant_reports:
            r["cells"][6] = "Grace.Liu@Tallgrass.io"
    exact_dup = rng.choice([e for e in staff if e["manager"] != RESTRICTED])
    reimported = rng.sample([e for e in staff if e is not exact_dup], 3)
    for e in [exact_dup]:
        orig = next(r for r in emp_rows if r["e"] is e)
        emp_rows.append({"e": e, "role": "exact_duplicate", "cells": list(orig["cells"])})
    for e in reimported:
        emp_rows.append({"e": e, "role": "reimported", "cells": [
            f"E-{e['num']}", e["name"].upper(), e["email"].upper(), e["dept"], "", e["grade"],
            by_name[e["manager"]]["email"], date_variant(e["start"], 3), e["cost_center"]]})
    rng.shuffle(emp_rows)
    for line, r in enumerate(emp_rows, start=2):
        r["line"] = line

    # ------------------------------------------------------------------ policy rows
    policy_rows = []
    variant_cat_rows = set(rng.sample(range(60), 5))
    k = 0
    for cat, gl, s, m, x, _ in POLICY:
        for grade, lim in zip(GRADES, (s, m, x)):
            name = cat
            if k in variant_cat_rows:
                name = rng.choice([cat + " ", cat.lower(), " " + cat])
            policy_rows.append([name, gl if rng.random() > 0.15 else "0" + gl, grade, limit_text(lim, rng),
                                "Receipt required over $75" if rng.random() < 0.3 else ""])
            k += 1

    # ------------------------------------------------------------------ claims
    claimants = employees[:]  # everyone files; staff file most
    weights = [1 if e["grade"] != "Staff" else 3 for e in claimants]
    statuses = [s for s, n in N_CLAIMS.items() for _ in range(n)]
    rng.shuffle(statuses)
    claims: list[dict] = []
    for st in statuses:
        e = rng.choices(claimants, weights)[0]
        if st == "Paid":
            sub = date(2026, 3, 2) + timedelta(days=rng.randint(0, 150))
            batch = f"RB-2026-{sub.month + 1:02d}"
        elif st == "Approved":
            sub, batch = date(2026, 8, 14) + timedelta(days=rng.randint(0, 24)), ""
        elif st == "Submitted":
            sub, batch = date(2026, 8, 20) + timedelta(days=rng.randint(0, 22)), ""
        else:
            sub, batch = date(2026, 3, 2) + timedelta(days=rng.randint(0, 185)), ""
        kind = rng.choice(list(PURPOSES))
        claims.append({"e": e, "status": st, "submitted": sub, "batch": batch, "kind": kind,
                       "purpose": rng.choice(PURPOSES[kind]), "lines": []})
    # guarantees the checklist relies on
    grace = by_name[RESTRICTED]
    ceo = by_name[CEO[0]]
    if not any(c["e"] is grace and c["status"] == "Submitted" for c in claims):
        next(c for c in claims if c["status"] == "Submitted" and c["e"]["grade"] == "Staff")["e"] = grace
    approved = [c for c in claims if c["status"] == "Approved"]
    others = {id(c["e"]) for c in approved[2:]}
    twice = rng.choice([e for e in staff if e["manager"] != RESTRICTED and id(e) not in others])
    approved[0]["e"] = twice
    approved[1]["e"] = twice
    claims.sort(key=lambda c: (c["submitted"], c["e"]["id"]))
    for i, c in enumerate(claims):
        c["no"] = f"C-{1001 + i}"

    def amount_for(cat: str) -> float:
        lo, hi = RANGE[cat]
        return round(rng.uniform(lo, hi), 2)

    for c in claims:
        n_lines = rng.choices([1, 2, 3, 4], [45, 30, 18, 7])[0]
        cats = rng.sample(PURPOSE_CATS[c["kind"]], min(n_lines, len(PURPOSE_CATS[c["kind"]])))
        for cat in cats:
            amt = amount_for(cat)
            lim = LIMIT[cat][c["e"]["grade"]]
            if lim is not None and amt > lim:
                amt = round(lim * 0.9, 2)
            exp = c["submitted"] - timedelta(days=rng.randint(1, 25))
            c["lines"].append({"cat": cat, "amount": amt, "date": exp, "desc": rng.choice(DESCRIPTIONS[cat])})

    submitted = [c for c in claims if c["status"] == "Submitted"]
    # over-policy lines: five Staff claims, one line each, above the Staff limit
    over_specs = [("Hotel", 312.40), ("Airfare", 742.00), ("Meals - Travel", 86.25), ("Home Office Equipment", 529.99), ("Hotel", 289.00)]
    staff_sub = [c for c in submitted if c["e"]["grade"] == "Staff" and c["e"] is not grace]
    over_claims = rng.sample(staff_sub, len(over_specs))
    travel_purposes = PURPOSES["travel"]
    for c, (cat, amt) in zip(over_claims, over_specs):
        if cat in PURPOSE_CATS["travel"] and c["kind"] not in ("travel", "learning"):
            c["kind"], c["purpose"] = "travel", travel_purposes[int(c["no"][2:]) % len(travel_purposes)]
        elif cat not in PURPOSE_CATS[c["kind"]]:
            c["kind"], c["purpose"] = "office", "Home office setup"
        c["lines"][0] = {"cat": cat, "amount": amt, "date": c["submitted"] - timedelta(days=rng.randint(2, 12)), "desc": rng.choice(DESCRIPTIONS[cat])}
    # grade trap: a manager's Hotel line of 312.40 is inside the Manager limit
    mgr_sub = [c for c in submitted if c["e"]["grade"] == "Manager" and c["e"] is not grace]
    if not mgr_sub:
        cand = next(c for c in submitted if c not in over_claims and c["e"] is not grace)
        cand["e"] = by_name["Samuel Okoye"]
        mgr_sub = [cand]
    grade_trap = mgr_sub[0]
    grade_trap["kind"], grade_trap["purpose"] = "travel", "Client visit - Chicago"
    grade_trap["lines"][0] = {"cat": "Hotel", "amount": 312.40, "date": grade_trap["submitted"] - timedelta(days=4), "desc": "2 nights"}
    # no-limit trap: the CEO's airfare
    ceo_claim = next((c for c in submitted if c["e"] is ceo), None)
    if ceo_claim is None:
        ceo_claim = next(c for c in submitted if c not in over_claims and c is not grade_trap and c["e"] is not grace)
        ceo_claim["e"] = ceo
    ceo_claim["kind"], ceo_claim["purpose"] = "travel", "Partner summit"
    ceo_claim["lines"][0] = {"cat": "Airfare", "amount": 1850.00, "date": ceo_claim["submitted"] - timedelta(days=6), "desc": "Round trip business class"}
    # impossible value: expense dated a year after the claim was submitted
    bad_claim = next(c for c in submitted if c not in over_claims and c is not grade_trap and c is not ceo_claim
                     and c["e"]["manager"] != RESTRICTED and c["e"] is not grace)
    bad_line = bad_claim["lines"][-1]
    bad_line["date"] = date(bad_claim["submitted"].year + 1, bad_claim["submitted"].month, max(1, bad_claim["submitted"].day - 5))

    def total(c: dict) -> float:
        return round(sum(l["amount"] for l in c["lines"]), 2)

    def over_lines(c: dict) -> list[dict]:
        return [l for l in c["lines"] if LIMIT[l["cat"]][c["e"]["grade"]] is not None and l["amount"] > LIMIT[l["cat"]][c["e"]["grade"]]]

    assert sum(1 for c in submitted if over_lines(c)) == len(over_specs)
    assert all(not over_lines(c) for c in claims if c["status"] != "Submitted")

    # the largest claim total must be unique and hold a dollar-string line
    top = max(claims, key=total)
    assert sum(1 for c in claims if total(c) == total(top)) == 1

    # ------------------------------------------------------------------ claim line rows
    line_rows: list[dict] = []
    for c in claims:
        e = c["e"]
        for j, l in enumerate(c["lines"], start=1):
            k = rng.random()
            id_text = e["id"] if k < 0.72 else (f"E-{e['num']}" if k < 0.88 else str(e["num"]))
            if e in reimported and rng.random() < 0.5:
                id_text = f"E-{e['num']}"
            name_text = e["name"] if rng.random() > 0.1 else e["name"].upper()
            force = c is top and l is max(c["lines"], key=lambda x: x["amount"])
            receipt = rng.choice(YES) if l["amount"] > RECEIPT_THRESHOLD else rng.choice(["No", "", "", "Yes", "N"])
            line_rows.append({"c": c, "l": l, "cells": [
                c["no"], id_text, name_text, date_variant(c["submitted"], rng.choice(SAFE_DATE_STYLES)), c["purpose"],
                date_variant(l["date"], rng.choice(SAFE_DATE_STYLES)),
                l["cat"] if rng.random() > 0.08 else l["cat"].lower(), l["desc"], money_text(l["amount"], rng, force),
                receipt, c["status"] if rng.random() > 0.12 else c["status"].upper(), c["batch"]]})
    # a claim's submitted date is written once per export row; keep it identical across a claim's lines
    for c in claims:
        rows_c = [r for r in line_rows if r["c"] is c]
        for r in rows_c[1:]:
            r["cells"][3] = rows_c[0]["cells"][3]
    dup_rows = []
    for st, n in N_DUP_LINES.items():
        cands = [r for r in line_rows if r["c"]["status"] == st and r["c"] is not bad_claim and r["c"] not in over_claims]
        dup_rows += rng.sample(cands, n)
    rows_out = [dict(r, dup=False) for r in line_rows] + [dict(r, cells=list(r["cells"]), dup=True) for r in dup_rows]
    # keep a claim's lines together (exports are sorted by claim), duplicates land right after their original
    order = {c["no"]: i for i, c in enumerate(claims)}
    rows_out.sort(key=lambda r: (order[r["c"]["no"]], r["c"]["lines"].index(r["l"]), r["dup"]))
    for line, r in enumerate(rows_out, start=2):
        r["line"] = line

    # ------------------------------------------------------------------ figures
    def in_scope(c: dict) -> bool:
        return c["e"] is grace or c["e"]["manager"] == RESTRICTED

    by_status = {s: [c for c in claims if c["status"] == s] for s in N_CLAIMS}
    awaiting = round(sum(total(c) for c in by_status["Approved"]), 2)
    paid_total = round(sum(total(c) for c in by_status["Paid"]), 2)
    over_claim_list = [c for c in submitted if over_lines(c)]
    # item 17: an approved claim with a duplicated line and more than one line
    dup_claims = [r["c"] for r in dup_rows]
    item17 = next((c for c in dup_claims if c["status"] == "Approved" and len(c["lines"]) > 1), dup_claims[0])
    dup_line_17 = next(r["l"] for r in dup_rows if r["c"] is item17)
    # search target: a staff member with a surname nobody else has and two or three claims
    search_emp = None
    for e in sorted(staff, key=lambda e: e["id"]):
        last = e["name"].split()[1]
        n = sum(1 for c in claims if c["e"] is e)
        if 2 <= n <= 3 and sum(1 for x in employees if last.lower() in x["name"].lower()) == 1 and e["manager"] != RESTRICTED:
            search_emp = e
            break
    assert search_emp is not None
    # out-of-scope example: an Engineering staff claim
    oos = next(c for c in claims if c["e"]["dept"] == "Engineering" and c["e"]["grade"] == "Staff" and c["status"] == "Submitted"
               and c is not bad_claim and c not in over_claim_list)
    grace_own_sub = next(c for c in claims if c["e"] is grace and c["status"] == "Submitted")
    # the employee login used from item 21: a Sales staff member (Grace's report) with at least one claim
    emp_x = max(grace_reports, key=lambda e: (sum(1 for c in claims if c["e"] is e), e["id"]))
    raw_text_top = max(rows_out, key=lambda r: r["cells"][8])

    def naive_amount(text: str) -> float:  # an import that cannot read "$1,325.34" or "1,273.50" stores nothing
        try:
            return float(text)
        except ValueError:
            return 0.0
    naive_totals = {}
    for r in line_rows:
        naive_totals[r["c"]["no"]] = round(naive_totals.get(r["c"]["no"], 0.0) + naive_amount(r["cells"][8]), 2)
    naive_top = max(naive_totals.items(), key=lambda kv: kv[1])
    dept_spend = {}
    for dept in ["Executive"] + [m[1] for m in MANAGERS]:
        dept_spend[dept] = round(sum(total(c) for c in by_status["Paid"] + by_status["Approved"] if c["e"]["dept"] == dept), 2)
    over_by_cat: dict[str, int] = {}
    for c in submitted:
        for l in over_lines(c):
            over_by_cat[l["cat"]] = over_by_cat.get(l["cat"], 0) + 1
    twice_claims = [c for c in by_status["Approved"] if c["e"] is twice]
    assert len(twice_claims) == 2

    def cinfo(c: dict) -> dict:
        return {"claim": c["no"], "employee": c["e"]["name"], "employee_id": c["e"]["id"], "grade": c["e"]["grade"],
                "department": c["e"]["dept"], "status": c["status"], "total": total(c),
                "file_lines": [r["line"] for r in rows_out if r["c"] is c]}

    cap_lines = [("Hotel", 300.00, True), ("Meals - Travel", 48.50, False), ("Taxi & Rideshare", 92.00, True)]
    cap_claimed = round(sum(a for _, a, _ in cap_lines), 2)
    cap_reimb = round(sum(min(a, LIMIT[c]["Staff"]) for c, a, _ in cap_lines), 2)

    counts = {
        "seed": seed,
        "company": COMPANY,
        "admin": f"{ADMIN} (finance manager)",
        "restricted_login": f"{RESTRICTED} (Sales manager)",
        "receipt_threshold": RECEIPT_THRESHOLD,
        "baseline": {
            "staff_role": "Manager",
            "viewer_role": "Viewer",
            "main_entity": "claim",
            "main_entity_plural": "claims",
            "scope_rule": f"{RESTRICTED}'s own claims and her direct reports' claims",
            "scope_count": sum(1 for c in claims if in_scope(c)),
            "out_of_scope_example": cinfo(oos),
            "kpis": [
                {"name": "Claims awaiting approval (status Submitted)", "value": len(submitted)},
                {"name": "Approved, awaiting reimbursement", "value": awaiting},
                {"name": "Reimbursed in 2026 (status Paid)", "value": paid_total},
                {"name": "Submitted claims over policy", "value": len(over_claim_list)},
            ],
            "scoped_kpi_1": sum(1 for c in submitted if in_scope(c)),
            "scope_count_if_manager_email_matched_case_sensitively": sum(
                1 for c in claims if c["e"] is grace or (c["e"]["manager"] == RESTRICTED and next(
                    r["cells"][6] for r in emp_rows if r["e"] is c["e"] and r["role"] == "unique") == grace["email"])),
            "search": {"term": search_emp["name"].split()[1], "employee": search_emp["name"],
                       "count": sum(1 for c in claims if c["e"] is search_emp),
                       "claims": [c["no"] for c in claims if c["e"] is search_emp]},
            "filter": {"field": "Status", "value": "Paid", "count": len(by_status["Paid"]),
                       "line_rows_with_status_paid_as_written": sum(1 for r in rows_out if r["cells"][10] == "Paid")},
            "sort": {"field": "Total", "top": cinfo(top), "top_line_file_value": f"${max(l['amount'] for l in top['lines']):,.2f}",
                     "top_if_currency_strings_unread": {"claim": naive_top[0], "total": naive_top[1]}},
            "export": {"rows": len(claims), "columns": ["Claim No", "Employee", "Submitted", "Status", "Total"]},
            "required_field": "Purpose",
        },
        "employees": {
            "file_rows_excluding_header": len(emp_rows),
            "exact_duplicate_rows": 1,
            "reimported_rows": 3,
            "unique_employees": len(employees),
            "dedupe_rule": "Same person when Work Email matches after lowercasing (the re-imported rows also carry the unpadded employee id).",
            "wrong_counts": {"no_dedupe": len(emp_rows), "exact_rows_only": len(emp_rows) - 1},
            "per_grade": {g: sum(1 for e in employees if e["grade"] == g) for g in GRADES},
            "restricted_direct_reports": len(grace_reports),
            "restricted_reports_with_case_variant_manager_email": sorted(
                r["e"]["name"] for r in emp_rows if r["role"] == "unique" and r["e"]["manager"] == RESTRICTED and r["cells"][6] != grace["email"]),
            "restricted_reports_if_manager_email_matched_exactly": sum(
                1 for r in emp_rows if r["role"] == "unique" and r["cells"][6] == grace["email"]),
            "reimported_employees": [{"name": e["name"], "id": e["id"], "file_lines": sorted(r["line"] for r in emp_rows if r["e"] is e)} for e in reimported],
            "exact_duplicate_employee": {"name": exact_dup["name"], "file_lines": sorted(r["line"] for r in emp_rows if r["e"] is exact_dup)},
            "employee_login_for_item_21": {"name": emp_x["name"], "id": emp_x["id"], "email": emp_x["email"],
                                           "claims": sum(1 for c in claims if c["e"] is emp_x)},
        },
        "policy": {
            "file_rows_excluding_header": len(policy_rows),
            "categories": len(POLICY),
            "limits": {c: LIMIT[c] for c, *_ in POLICY},
            "category_name_variant_rows": len(variant_cat_rows),
        },
        "claims": {
            "file_rows_excluding_header": len(rows_out),
            "duplicate_line_rows": len(dup_rows),
            "unique_lines": len(line_rows),
            "claims": len(claims),
            "per_status": {s: len(v) for s, v in by_status.items()},
            "wrong_counts": {"line_rows_as_claims": len(rows_out), "unique_lines_as_claims": len(line_rows)},
            "item17_claim_with_duplicated_line": {**cinfo(item17), "total_with_duplicate_kept": round(total(item17) + dup_line_17["amount"], 2),
                                                  "duplicated_line": {"category": dup_line_17["cat"], "amount": dup_line_17["amount"]}},
            "expense_after_submission": {**cinfo(bad_claim), "submitted": bad_claim["submitted"].isoformat(),
                                         "expense_date": bad_line["date"].isoformat(), "category": bad_line["cat"],
                                         "file_values": next([r["cells"][3], r["cells"][5]] for r in rows_out if r["l"] is bad_line)},
            "awaiting_reimbursement": {"claims": len(by_status["Approved"]), "total": awaiting,
                                       "total_with_duplicates_kept": round(awaiting + sum(r["l"]["amount"] for r in dup_rows if r["c"]["status"] == "Approved"), 2),
                                       "employee_with_two_approved_claims": {"name": twice["name"], "claims": [c["no"] for c in twice_claims],
                                                                             "owed": round(sum(total(c) for c in twice_claims), 2)}},
            "reimbursed_2026_after_batch": round(paid_total + awaiting, 2),
            "over_policy_submitted_claims": [dict(cinfo(c), over_line={"category": over_lines(c)[0]["cat"], "amount": over_lines(c)[0]["amount"],
                                                                       "limit": LIMIT[over_lines(c)[0]["cat"]][c["e"]["grade"]]}) for c in over_claim_list],
            "grade_trap_not_over": dict(cinfo(grade_trap), line={"category": "Hotel", "amount": 312.40, "limit": LIMIT["Hotel"]["Manager"], "staff_limit": LIMIT["Hotel"]["Staff"]}),
            "no_limit_trap_not_over": dict(cinfo(ceo_claim), line={"category": "Airfare", "amount": 1850.00, "limit": "no limit"}),
            "restricted_own_submitted_claim": cinfo(grace_own_sub),
        },
        "app_items": {
            "receipt_test": {"category": "Client Entertainment", "staff_limit": LIMIT["Client Entertainment"]["Staff"],
                             "rejected_without_receipt": 75.01, "accepted_without_receipt": 75.00},
            "cap_test": {"employee": emp_x["name"], "grade": "Staff",
                         "lines": [{"category": c, "amount": a, "receipt": r, "limit": LIMIT[c]["Staff"], "reimbursable": min(a, LIMIT[c]["Staff"])} for c, a, r in cap_lines],
                         "claimed": cap_claimed, "reimbursable": cap_reimb},
            "awaiting_after_cap_claim_approved": cap_reimb,
        },
        "changes": {
            "1_paid_plus_approved_by_department": dept_spend,
            "1_sales_after_cap_claim": round(dept_spend["Sales"] + cap_reimb, 2),
            "1_per_extra_cap_claim": {"sales": cap_reimb, "hotel_lines": 1, "taxi_lines": 1, "restricted_lines": 2},
            "1_over_limit_lines_by_category_imported": dict(sorted(over_by_cat.items())),
            "1_over_limit_lines_by_category_with_cap_claim": dict(sorted({**over_by_cat, "Hotel": over_by_cat.get("Hotel", 0) + 1,
                                                                          "Taxi & Rideshare": over_by_cat.get("Taxi & Rideshare", 0) + 1}.items())),
            "1_restricted_over_limit_lines": sum(len(over_lines(c)) for c in submitted if in_scope(c)) + 2,
            "2_mileage_rate": 0.70,
            "2_mileage_tests": {"120_miles": 84.00, "500_miles_claimed": 350.00, "500_miles_reimbursable": 300.00, "200_miles_no_receipt": 140.00,
                                "taxi_line_without_receipt_blocked": 76.00},
            "3_second_approval_over": 1000.00,
            "3_tests": {"over": 1250.00, "boundary": 1000.00},
        },
    }
    assert sum(dept_spend.values()) == round(paid_total + awaiting, 2) or abs(sum(dept_spend.values()) - (paid_total + awaiting)) < 0.01

    header_e = ["Employee ID", "Name", "Work Email", "Department", "Title", "Grade", "Manager Email", "Start Date", "Cost Center"]
    header_p = ["Category", "GL Code", "Grade", "Limit per Item", "Notes"]
    header_c = ["Claim No", "Employee ID", "Employee", "Submitted", "Purpose", "Expense Date", "Category", "Description",
                "Amount", "Receipt", "Status", "Reimbursement Batch"]
    return {"counts": counts, "employees": (header_e, [r["cells"] for r in emp_rows]), "policy": (header_p, policy_rows),
            "claims": (header_c, [r["cells"] for r in rows_out])}


def main() -> None:
    seed = argparse_seed()
    out = build(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "employees.csv"), *out["employees"])
    write_csv(os.path.join(SEED_DIR, "expense_policy.csv"), *out["policy"])
    write_csv(os.path.join(SEED_DIR, "claims.csv"), *out["claims"])
    write_text(os.path.join(REF_DIR, "counts.json"), json.dumps(out["counts"], indent=2) + "\n")
    c = out["counts"]
    print(f"employees.csv {c['employees']['file_rows_excluding_header']} rows -> {c['employees']['unique_employees']}; "
          f"expense_policy.csv {c['policy']['file_rows_excluding_header']} rows; claims.csv {c['claims']['file_rows_excluding_header']} rows -> "
          f"{c['claims']['claims']} claims; scope {c['baseline']['scope_count']}")


if __name__ == "__main__":
    main()
