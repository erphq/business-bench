#!/usr/bin/env python3
"""Deterministic seed generator for the leave-tracking build task.

    python gen.py [--seed N]

Writes:
  seed/staff.csv            60 rows -> 40 active staff (16 people who have left, one of them re-hired under a new
                            id with the same email, one leaver with a future end date who is still active, exact and
                            email-case duplicates, department names written several ways, balances as "12.5 days")
  seed/leave_requests.csv   153 rows -> 150 requests (employee ids written E0042 / 42 / E42, "Vacation" for annual
                            leave, status case variants and "Canceled", mixed date formats, exact duplicate rows,
                            one request whose end date is before its start)
  seed/holidays.csv         company holiday calendar for 2026 and 2027 with observed dates for weekend holidays
  reference/counts.json     every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the canonical public variant (checklist.md quotes its numbers). Other seeds re-roll people, balances,
and the random requests; the pinned checklist requests keep their dates. counts.json is recomputed from the truth.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, write_csv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

TODAY = date(2026, 9, 13)
DEPTS = [("Operations", "Helen Marsh", 5), ("Engineering", "Rafael Ortiz", 10), ("Customer Support", "Grace Oduya", 9),
         ("Sales", "Martin Keane", 7), ("Finance", "Lena Fischer", 4), ("People & Admin", "Samir Qureshi", 5)]  # 40 people
CEO = "Helen Marsh"
RESTRICTED = "Grace Oduya"
DEPT_VARIANTS = {"Operations": ["Ops", "operations"], "Engineering": ["Eng", "engineering ", "ENGINEERING"],
                 "Customer Support": ["Cust. Support", "customer support", "Support"], "Sales": ["SALES", "sales "],
                 "Finance": ["finance", "FINANCE"], "People & Admin": ["People and Admin", "people & admin"]}
HOLIDAYS = [  # (name, actual date, observed date)
    ("New Year's Day", date(2026, 1, 1), None), ("Martin Luther King Jr. Day", date(2026, 1, 19), None),
    ("Presidents' Day", date(2026, 2, 16), None), ("Memorial Day", date(2026, 5, 25), None), ("Juneteenth", date(2026, 6, 19), None),
    ("Independence Day", date(2026, 7, 4), date(2026, 7, 3)), ("Labor Day", date(2026, 9, 7), None),
    ("Thanksgiving", date(2026, 11, 26), None), ("Day after Thanksgiving", date(2026, 11, 27), None),
    ("Christmas Eve", date(2026, 12, 24), None), ("Christmas Day", date(2026, 12, 25), None), ("New Year's Eve", date(2026, 12, 31), None),
    ("New Year's Day", date(2027, 1, 1), None), ("Martin Luther King Jr. Day", date(2027, 1, 18), None),
    ("Presidents' Day", date(2027, 2, 15), None), ("Memorial Day", date(2027, 5, 31), None), ("Juneteenth", date(2027, 6, 19), date(2027, 6, 18)),
    ("Independence Day", date(2027, 7, 4), date(2027, 7, 5)), ("Labor Day", date(2027, 9, 6), None),
    ("Thanksgiving", date(2027, 11, 25), None), ("Day after Thanksgiving", date(2027, 11, 26), None),
    ("Christmas Eve", date(2027, 12, 24), date(2027, 12, 23)), ("Christmas Day", date(2027, 12, 25), date(2027, 12, 24)),
    ("New Year's Eve", date(2027, 12, 31), None),
]
OFF = {obs or actual for _, actual, obs in HOLIDAYS}
N_LEAVERS = 16
N_STAFF_EXACT_DUPES = 2
N_STAFF_CASE_DUPES = 2
N_REQUESTS = 150
N_REQUEST_EXACT_DUPES = 3
STAFF_COLUMNS = ["Employee ID", "Name", "Email", "Department", "Manager", "Start Date", "End Date", "Annual Leave Remaining"]
REQUEST_COLUMNS = ["Request ID", "Employee ID", "Employee Name", "Type", "Start", "End", "Status", "Submitted", "Notes"]
HOLIDAY_COLUMNS = ["Holiday", "Date", "Observed", "Notes"]
D_STYLES = [0, 1, 2, 3, 4, 6]


def working_days(a: date, b: date) -> int:
    n, d = 0, a
    while d <= b:
        if d.weekday() < 5 and d not in OFF:
            n += 1
        d += timedelta(days=1)
    return n


def add_working(a: date, n: int) -> date:
    d, left = a, n - 1
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in OFF:
            left -= 1
    return d


def half(x: float) -> str:
    return f"{x:g}"


def build(rng: random.Random, seed: int) -> dict:
    named = {m for _, m, _ in DEPTS}
    named_first = {n.split()[0] for n in named} | {"Owen", "Daniel"}
    named_last = {n.split()[1] for n in named} | {"Pratt", "Kim"}
    pairs = [(f, l) for f in FIRST for l in LAST if f not in named_first and l not in named_last]
    rng.shuffle(pairs)
    pi = 0

    def new_name():
        nonlocal pi
        f, l = pairs[pi]
        pi += 1
        return f"{f} {l}"

    ids = rng.sample(range(2, 99), 40 + N_LEAVERS)
    staff = []
    for dept, mgr, n in DEPTS:
        for k in range(n):
            name = mgr if k == 0 else new_name()
            manager = "" if name == CEO else (CEO if k == 0 else mgr)
            staff.append({"name": name, "dept": dept, "manager": manager, "active": True, "end": None,
                          "start": date(2016, 2, 1) + timedelta(days=rng.randint(0, 3400)),
                          "balance": rng.randint(0, 50) / 2})
    for i, s in enumerate(staff):
        s["id"] = ids[i]
        first, last = s["name"].lower().split()[0], s["name"].lower().split()[-1]
        s["email"] = f"{first}.{last}@northgate-analytics.com"
    # an active employee whose last day is still ahead, and a re-hire who reuses his old email
    eng = [s for s in staff if s["dept"] == "Engineering" and s["manager"] == "Rafael Ortiz"]
    owen, daniel = eng[-1], eng[-2]
    owen.update(name="Owen Pratt", email="owen.pratt@northgate-analytics.com", end=date(2026, 10, 30))
    daniel.update(name="Daniel Kim", email="daniel.kim@northgate-analytics.com", start=date(2025, 11, 3))
    leavers = []
    for j in range(N_LEAVERS):
        dept, mgr, _ = rng.choice(DEPTS)
        name = new_name()
        first, last = name.lower().split()
        leavers.append({"name": name, "dept": dept, "manager": mgr if name != mgr else CEO, "active": False,
                        "start": date(2014, 5, 1) + timedelta(days=rng.randint(0, 3000)),
                        "end": date(2024, 1, 15) + timedelta(days=rng.randint(0, 950)),
                        "balance": rng.choice([0, 0, 2.5, 4, 7.5]), "id": ids[40 + j],
                        "email": f"{first}.{last}@northgate-analytics.com"})
    rehire_old = leavers[0]
    rehire_old.update(name="Daniel Kim", email=daniel["email"], dept="Engineering", manager="Rafael Ortiz",
                      start=date(2019, 4, 8), end=date(2024, 6, 28))
    for lv in leavers:
        lv["start"] = min(lv["start"], lv["end"] - timedelta(days=200))

    by_name = {s["name"]: s for s in staff}
    grace_team = [s for s in staff if s["manager"] == RESTRICTED]
    team_sorted = sorted(grace_team, key=lambda s: s["name"])
    M, N, X = team_sorted[0], team_sorted[1], team_sorted[2]
    eng_staff = sorted((s for s in staff if s["dept"] == "Engineering" and s["manager"] == "Rafael Ortiz" and s not in (owen, daniel)), key=lambda s: s["name"])
    Y, T, P = eng_staff[0], eng_staff[1], eng_staff[2]
    sales = sorted((s for s in staff if s["dept"] == "Sales" and s["manager"] == "Martin Keane"), key=lambda s: s["name"])
    Z, W, Q = sales[0], sales[1], sales[2]
    ops = sorted((s for s in staff if s["dept"] == "Operations" and s["manager"] == CEO), key=lambda s: s["name"])
    R, L = ops[0], ops[1]
    fin = sorted((s for s in staff if s["dept"] == "Finance" and s["manager"] == "Lena Fischer"), key=lambda s: s["name"])
    F, B = fin[0], fin[1]
    ppl = sorted((s for s in staff if s["dept"] == "People & Admin" and s["manager"] == "Samir Qureshi"), key=lambda s: s["name"])
    D, E = ppl[0], ppl[1]
    pinned = {id(p) for p in (M, N, X, Y, T, P, Z, W, Q, R, L, F, B, D, E)}
    M["balance"], B["balance"], D["balance"] = 14.0, 3.0, 10.0
    for s in staff:
        if s["balance"] >= 27.5:
            s["balance"] = 25.0
    top = sorted((s for s in staff if id(s) not in pinned and s["manager"] and s not in (owen, daniel)), key=lambda s: s["name"])[3]
    top["balance"] = 27.5

    # ------------------------------------------------------------------ requests
    requests = []

    def add(s, typ, start, end, status, submitted=None, note=""):
        r = {"emp": s, "type": typ, "start": start, "end": end, "status": status, "note": note,
             "submitted": submitted or min(start - timedelta(days=rng.randint(7, 40)), TODAY - timedelta(days=rng.randint(1, 20)))}
        requests.append(r)
        return r

    req_X = add(X, "Annual", date(2026, 10, 13), date(2026, 10, 14), "Approved")
    add(Y, "Annual", date(2026, 10, 12), date(2026, 10, 16), "Approved")
    add(Z, "Annual", date(2026, 10, 14), date(2026, 10, 14), "Approved")
    add(W, "Annual", date(2026, 10, 14), date(2026, 10, 15), "Pending")
    add(R, "Unpaid", date(2026, 10, 14), date(2026, 10, 14), "Rejected")
    req_T = add(T, "Annual", date(2026, 10, 26), date(2026, 10, 30), "Pending")
    req_D = add(D, "Annual", date(2026, 11, 2), date(2026, 11, 9), "Pending")
    req_P = add(P, "Annual", date(2026, 12, 21), date(2026, 12, 31), "Approved")
    req_Q = add(Q, "Annual", date(2026, 6, 29), date(2026, 7, 6), "Approved", note="Family trip")
    req_L = add(L, "Annual", date(2026, 12, 28), date(2026, 12, 30), "Approved")
    req_E = add(E, "Annual", date(2026, 10, 23), date(2026, 10, 21), "Cancelled", note="entered wrong")
    forced = list(requests)

    def blocked(s, a, b):
        if a <= date(2026, 10, 16) and b >= date(2026, 10, 12):
            return True
        if s is M and a <= date(2026, 11, 30) and b >= date(2026, 10, 1):
            return True
        if s is D and a <= date(2026, 11, 13) and b >= date(2026, 11, 1):
            return True
        if s is L or s is P:
            return b >= date(2026, 12, 1) or a >= date(2026, 12, 1)
        return any(r["emp"] is s and r["status"] not in ("Rejected", "Cancelled") and a <= r["end"] and b >= r["start"] for r in requests
                   if r["start"] <= r["end"])

    eligible = [s for s in staff if s["name"] != RESTRICTED]
    while len(requests) < N_REQUESTS:
        s = rng.choice(eligible)
        start = date(2026, 1, 5) + timedelta(days=rng.randint(0, 340))
        if start.weekday() >= 5 or start in OFF:
            continue
        past = start < TODAY
        typ = rng.choices(["Annual", "Sick", "Unpaid"], [70, 20, 10])[0] if past else rng.choices(["Annual", "Unpaid"], [88, 12])[0]
        n = {"Annual": rng.randint(1, 8), "Sick": rng.randint(1, 3), "Unpaid": rng.randint(1, 4)}[typ]
        end = add_working(start, n)
        if end > date(2026, 12, 18) or blocked(s, start, end):
            continue
        if s is owen and start > owen["end"]:
            continue
        if past:
            status = rng.choices(["Approved", "Rejected", "Cancelled"], [80, 8, 12])[0]
        else:
            status = rng.choices(["Approved", "Pending", "Rejected", "Cancelled"], [55, 35, 5, 5])[0]
        add(s, typ, start, end, status)
    requests.sort(key=lambda r: (r["start"], r["emp"]["id"]))
    for k, r in enumerate(requests, start=1):
        r["rid"] = f"LR-2026-{k:04d}"
        r["days"] = working_days(r["start"], r["end"]) if r["start"] <= r["end"] else 0

    # a search target with exactly three requests
    per_emp = {}
    for r in requests:
        per_emp.setdefault(r["emp"]["name"], []).append(r)
    names = [s["name"] for s in staff]
    managers = {m for _, m, _ in DEPTS}
    search_pool = lambda k: sorted(n for n, rs in per_emp.items() if len(rs) == k and id(by_name[n]) not in pinned and n not in managers
                                   and by_name[n] is not top and not any(n.lower() in m.lower() for m in names if m != n))
    search_n = next(k for k in (3, 2, 4, 5) if search_pool(k))
    search = search_pool(search_n)[0]

    # ------------------------------------------------------------------ written files
    all_people = staff + leavers
    rng.shuffle(all_people)

    def staff_row(s, email=None):
        dept_w = s["dept"] if rng.random() < 0.65 else rng.choice(DEPT_VARIANTS[s["dept"]])
        bal = s["balance"]
        bal_w = rng.choice([half(bal), half(bal), f"{half(bal)} days"])
        if s is B:
            bal_w = "3 days"
        if s is top:
            bal_w = "27.5 days"
        return [f"E{s['id']:04d}", s["name"], s["email"] if email is None else email, dept_w, s["manager"],
                date_variant(s["start"], rng.choice(D_STYLES)), date_variant(s["end"], rng.choice(D_STYLES)) if s["end"] else "", bal_w]

    staff_rows = [staff_row(s) for s in all_people]
    exact_src = rng.sample([i for i, s in enumerate(all_people) if s["active"] and id(s) not in pinned and s not in (owen, daniel, top)], N_STAFF_EXACT_DUPES)
    case_src = rng.sample([i for i, s in enumerate(all_people) if s["active"] and id(s) not in pinned and s not in (owen, daniel, top) and i not in exact_src], N_STAFF_CASE_DUPES)
    for i in exact_src:
        staff_rows.append(list(staff_rows[i]))
    case_groups = []
    for i in case_src:
        s = all_people[i]
        variant = s["email"].upper() if rng.random() < 0.5 else s["email"].split("@")[0].title() + "@" + s["email"].split("@")[1]
        row = staff_row(s, email=variant)
        row[7] = staff_rows[i][7]
        staff_rows.append(row)
        case_groups.append({"name": s["name"], "emails_as_written": [s["email"], variant]})
    rng.shuffle(staff_rows)

    type_w = {"Annual": ["Annual", "Annual", "annual", "Vacation"], "Sick": ["Sick", "sick", "SICK"], "Unpaid": ["Unpaid", "unpaid"]}
    status_w = {"Approved": ["Approved", "approved", "APPROVED"], "Pending": ["Pending", "pending"], "Rejected": ["Rejected", "rejected"],
                "Cancelled": ["Cancelled", "Canceled", "canceled"]}
    req_rows = []
    vacation_rows = 0
    id_written = {}
    for r in requests:
        e = r["emp"]["id"]
        idw = rng.choices([f"E{e:04d}", str(e), f"E{e}"], [60, 25, 15])[0]
        tw = rng.choice(type_w[r["type"]])
        if tw == "Vacation":
            vacation_rows += 1
        style_s = 6 if r is req_L else rng.choice(D_STYLES)
        req_rows.append([r["rid"], idw, r["emp"]["name"], tw, date_variant(r["start"], style_s), date_variant(r["end"], rng.choice(D_STYLES)),
                         rng.choice(status_w[r["status"]]), date_variant(r["submitted"], rng.choice(D_STYLES)), r["note"]])
        id_written.setdefault(r["emp"]["name"], set()).add(idw)
    dupe_rows = rng.sample(range(len(req_rows)), N_REQUEST_EXACT_DUPES)
    for i in dupe_rows:
        req_rows.append(list(req_rows[i]))
    rng.shuffle(req_rows)

    hol_rows = []
    for name, actual, obs in HOLIDAYS:
        hol_rows.append([name, date_variant(actual, rng.choice(D_STYLES)), date_variant(obs, 1) if obs else "",
                         "Office closed Friday" if obs and obs.weekday() == 4 else ("Office closed Monday" if obs else "")])

    # ------------------------------------------------------------------ truth
    active = [s for s in staff]
    team_ids = {id(s) for s in grace_team}

    def reqs(status=None, typ=None, team=None):
        return [r for r in requests if (status is None or r["status"] == status) and (typ is None or r["type"] == typ)
                and (team is None or id(r["emp"]) in team)]

    by_text_start = sorted(req_rows, key=lambda row: row[4], reverse=True)
    wrong_q_days = working_days(date(2026, 6, 29), date(2026, 7, 6)) + 1
    off_on = lambda d, status="Approved": sorted(r["emp"]["name"] for r in requests if r["status"] == status and r["start"] <= d <= r["end"])
    link_emp = sorted((n for n, ws in id_written.items() if len(ws) >= 2 and len(per_emp[n]) >= 3 and id(by_name[n]) not in pinned
                       and n != search and n not in managers and by_name[n] is not top), key=lambda n: (-len(id_written[n]), n))[0]
    approved_annual_days = sum(r["days"] for r in reqs("Approved", "Annual"))

    counts = {
        "seed": seed,
        "company": {"people": 40, "departments": [d for d, _, _ in DEPTS], "managers": {d: m for d, m, _ in DEPTS},
                    "restricted_login": RESTRICTED, "restricted_department": "Customer Support",
                    "roles": {"admin": "Admin (HR)", "staff": "Manager", "viewer": "Payroll (read-only)", "extra": "Employee"},
                    "team_rule": "a manager's team is the staff whose Manager is that person",
                    "day_rule": "leave days are working days from Start to End inclusive, excluding Saturdays, Sundays, and holidays on their observed date",
                    "today": TODAY.isoformat()},
        "staff": {
            "file_rows_excluding_header": len(staff_rows),
            "unique_employee_ids": len(staff) + N_LEAVERS,
            "exact_duplicate_rows": N_STAFF_EXACT_DUPES,
            "email_case_duplicate_rows": N_STAFF_CASE_DUPES,
            "former_staff_with_past_end_date": N_LEAVERS,
            "active_staff": len(active),
            "dedupe_rule": "One person per Employee ID. Active means End Date blank or after today (2026-09-13). Daniel Kim has two IDs: E%04d left 2024-06-28, E%04d is active and reuses the same email." % (rehire_old["id"], daniel["id"]),
            "wrong_counts": {"all_rows": len(staff_rows), "ignoring_end_date": len(staff) + N_LEAVERS,
                             "email_dedupe_keeping_the_leaver_row": len(active) - 1, "future_end_date_treated_as_left": len(active) - 1},
            "email_case_groups": case_groups,
            "future_leaver": {"name": owen["name"], "end_date": owen["end"].isoformat()},
            "rehire": {"name": "Daniel Kim", "old_id": f"E{rehire_old['id']:04d}", "new_id": f"E{daniel['id']:04d}", "email": daniel["email"]},
            "example_former_staff": sorted(lv["name"] for lv in leavers[1:4]),
            "per_department": {d: sum(1 for s in active if s["dept"] == d) for d, _, _ in DEPTS},
            "team_sizes": {m: sum(1 for s in active if s["manager"] == m) for _, m, _ in DEPTS},
            "annual_leave_remaining_total": sum(s["balance"] for s in active),
            "balance_examples": {"B": {"name": B["name"], "file_value": "3 days", "balance": 3.0},
                                 "highest": {"name": top["name"], "file_value": "27.5 days", "balance": 27.5},
                                 "P_not_double_deducted": {"name": P["name"], "balance": P["balance"],
                                                           "approved_annual_days_in_file": sum(r["days"] for r in requests if r["emp"] is P and r["status"] == "Approved" and r["type"] == "Annual")}},
        },
        "requests": {
            "file_rows_excluding_header": len(req_rows),
            "exact_duplicate_rows": N_REQUEST_EXACT_DUPES,
            "unique_requests": len(requests),
            "per_status": {st: len(reqs(st)) for st in ("Approved", "Pending", "Rejected", "Cancelled")},
            "per_type": {t: len(reqs(typ=t)) for t in ("Annual", "Sick", "Unpaid")},
            "rows_written_vacation": vacation_rows,
            "employee_id_rule": "Employee ID written E0042, 42, or E42 all mean E0042",
            "id_link_check": {"name": link_emp, "id": f"E{by_name[link_emp]['id']:04d}", "requests": len(per_emp[link_emp]),
                              "id_written_as": sorted(id_written[link_emp])},
            "approved_annual_days_2026": approved_annual_days,
            "end_before_start": {"request": req_E["rid"], "employee": E["name"],
                                 "start": "2026-10-23", "end": "2026-10-21", "status": "Cancelled"},
            "day_checks": {"P": {"name": P["name"], "request": req_P["rid"],
                                 "start": "2026-12-21", "end": "2026-12-31", "days": working_days(date(2026, 12, 21), date(2026, 12, 31))},
                           "Q": {"name": Q["name"], "request": req_Q["rid"], "start": "2026-06-29", "end": "2026-07-06", "days": working_days(date(2026, 6, 29), date(2026, 7, 6)),
                                 "days_if_july_4_used_instead_of_observed_july_3": wrong_q_days}},
            "restricted": {"requests": len(reqs(team=team_ids)), "pending": len(reqs("Pending", team=team_ids))},
            "pending_total": len(reqs("Pending")),
            "search_check": {"term": search, "expected_results": search_n},
            "filter_check": {"field": "Status", "value": "Pending", "expected_results": len(reqs("Pending"))},
            "sort_check": {"field": "Start", "direction": "descending", "first": f"{L['name']} 2026-12-28", "request": req_L["rid"], "file_value": date_variant(date(2026, 12, 28), 6),
                           "text_sort_would_put_first": f"{by_text_start[0][2]} ({by_text_start[0][4]})"},
            "export_check": {"rows": len(requests), "columns": ["Employee", "Type", "Start", "End", "Days", "Status"]},
            "out_of_scope_request": {"request": req_T["rid"], "employee": T["name"], "department": "Engineering",
                                     "start": "2026-10-26", "end": "2026-10-30", "status": "Pending"},
        },
        "dashboard": {"pending_requests": len(reqs("Pending")), "active_staff": len(active),
                      "annual_leave_remaining_days": sum(s["balance"] for s in active), "approved_annual_days_2026": approved_annual_days,
                      "restricted_pending": len(reqs("Pending", team=team_ids))},
        "tester_records": {"employee": M["name"], "type": "Annual", "start": "2026-11-16", "end": "2026-11-16", "status": "Pending",
                           "note": "leave requests the tester creates without a named person use this and are deleted when the item is done"},
        "checks": {
            "approval": {"employee": M["name"], "balance_before": 14.0, "start": "2026-10-05", "end": "2026-10-09",
                         "days": working_days(date(2026, 10, 5), date(2026, 10, 9)), "balance_after": 14.0 - working_days(date(2026, 10, 5), date(2026, 10, 9))},
            "holiday_request": {"employee": M["name"], "start": "2026-11-23", "end": "2026-11-27", "days": working_days(date(2026, 11, 23), date(2026, 11, 27)),
                                "balance_after": 14.0 - working_days(date(2026, 10, 5), date(2026, 10, 9)) - working_days(date(2026, 11, 23), date(2026, 11, 27))},
            "overlap": {"requester": N["name"], "date": "2026-10-14", "warns_about": X["name"], "teammate_request": f"{req_X['rid']} 2026-10-13 to 2026-10-14 (Approved)",
                        "control_employee": F["name"], "control_department": "Finance", "finance_off_on_date": off_on(date(2026, 10, 14)) and
                        [n for n in off_on(date(2026, 10, 14)) if by_name[n]["dept"] == "Finance"]},
            "cancel_restores": {"after_cancelling_5_day_request": 14.0 - working_days(date(2026, 11, 23), date(2026, 11, 27)), "after_cancelling_both": 14.0},
            "sick": {"employee": M["name"], "start": "2026-10-19", "end": "2026-10-20", "days": 2, "balance_after": 14.0},
            "permission": {"own_request_dates": ["2026-11-02", "2026-11-03"], "other_team_request": req_T["rid"]},
        },
        "changes": {
            "1_whos_off": {"date": "2026-10-14", "approved_off": off_on(date(2026, 10, 14)),
                           "departments": {n: by_name[n]["dept"] for n in off_on(date(2026, 10, 14))},
                           "pending_on_date": off_on(date(2026, 10, 14), "Pending"), "rejected_on_date": off_on(date(2026, 10, 14), "Rejected"),
                           "range": ["2026-10-12", "2026-10-16"],
                           "approved_in_range": sorted({r["emp"]["name"] for r in requests if r["status"] == "Approved" and r["start"] <= date(2026, 10, 16) and r["end"] >= date(2026, 10, 12)}),
                           "days_in_range": {r["emp"]["name"]: working_days(max(r["start"], date(2026, 10, 12)), min(r["end"], date(2026, 10, 16)))
                                             for r in requests if r["status"] == "Approved" and r["start"] <= date(2026, 10, 16) and r["end"] >= date(2026, 10, 12)},
                           "customer_support_on_date": [n for n in off_on(date(2026, 10, 14)) if by_name[n]["dept"] == "Customer Support"],
                           "restricted_view_on_date": [n for n in off_on(date(2026, 10, 14)) if by_name[n]["manager"] == RESTRICTED]},
            "2_balance_block": {"low_balance": {"name": B["name"], "balance": 3.0, "refused": {"start": "2026-10-19", "end": "2026-10-22", "days": 4},
                                                "accepted": {"start": "2026-10-19", "end": "2026-10-21", "days": 3}},
                                "pending_counts": {"name": D["name"], "pending_request": req_D["rid"], "balance": 10.0, "pending_days": working_days(date(2026, 11, 2), date(2026, 11, 9)),
                                                   "available": 10.0 - working_days(date(2026, 11, 2), date(2026, 11, 9)),
                                                   "refused": {"start": "2026-11-16", "end": "2026-11-20", "days": 5},
                                                   "accepted": {"start": "2026-11-16", "end": "2026-11-19", "days": 4}}},
            "3_hr_signoff": {"threshold_rule": "more than 10 working days needs HR (admin) approval after the manager",
                             "long": {"employee": M["name"], "start": "2026-10-05", "end": "2026-10-19", "days": working_days(date(2026, 10, 5), date(2026, 10, 19)),
                                      "balance_after_hr": 14.0 - working_days(date(2026, 10, 5), date(2026, 10, 19))},
                             "ten_days": {"employee": M["name"], "start": "2026-11-02", "end": "2026-11-13", "days": working_days(date(2026, 11, 2), date(2026, 11, 13)),
                                          "balance_after_manager": 14.0 - working_days(date(2026, 11, 2), date(2026, 11, 13))}},
        },
    }
    return {"staff_rows": staff_rows, "req_rows": req_rows, "hol_rows": hol_rows, "counts": counts}


def main() -> None:
    seed = argparse_seed(0)
    rng = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    out = build(rng, seed)
    write_csv(os.path.join(SEED_DIR, "staff.csv"), STAFF_COLUMNS, out["staff_rows"])
    write_csv(os.path.join(SEED_DIR, "leave_requests.csv"), REQUEST_COLUMNS, out["req_rows"], crlf=True)
    write_csv(os.path.join(SEED_DIR, "holidays.csv"), HOLIDAY_COLUMNS, out["hol_rows"])
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out["counts"], indent=2) + "\n")
    s, r = out["counts"]["staff"], out["counts"]["requests"]
    print(f"staff.csv: {s['file_rows_excluding_header']} rows -> {s['active_staff']} active {s['per_department']}")
    print(f"leave_requests.csv: {r['file_rows_excluding_header']} rows -> {r['unique_requests']} requests {r['per_status']}; "
          f"approved annual days {r['approved_annual_days_2026']}; restricted {r['restricted']}")


if __name__ == "__main__":
    main()
