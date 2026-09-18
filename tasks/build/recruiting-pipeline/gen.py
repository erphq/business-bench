#!/usr/bin/env python3
"""Deterministic seed generator for the recruiting-pipeline build task.

    python gen.py [--seed N]

Writes:
  seed/roles.csv          requisitions (re-exported rows, manager names written three ways, salary as "$150,000" / "150k")
  seed/candidates.csv     one row per application from the old applicant tracker (repeated rows, re-applications with the
                          email in different capitals, people who applied to two roles, two different people with one name,
                          role ids written "REQ-0131" / "131" / "REQ-131", stage words from two eras, one impossible hire date)
  reference/counts.json   every figure checklist.md and changes/*.md quote, computed from the ground truth

Seed 0 is the public variant that checklist.md quotes. Other seeds re-roll people, dates, salaries, and stages;
counts.json is recomputed from the truth, so re-derive checklist numbers from it.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import FIRST, LAST, EMAIL_DOMAINS, phone_variant, write_csv  # noqa: E402

SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")
AS_OF = date(2026, 9, 11)

MANAGERS = {
    "Engineering": ("Ken Okafor", ["K. Okafor", "Okafor, Ken"]),
    "Sales": ("Maria Santos", ["M. Santos", "Santos, Maria"]),
    "Customer Success": ("Jordan Reyes", ["J. Reyes"]),
    "Product & Design": ("Aisha Bello", ["A. Bello"]),
}
RESTRICTED = "Ken Okafor"
TITLES = {
    "Engineering": [("Senior Backend Engineer", 150, 185), ("Frontend Engineer", 120, 150), ("Staff Platform Engineer", 185, 230),
                    ("Data Engineer", 135, 165), ("QA Automation Engineer", 105, 130), ("Engineering Manager", 180, 215),
                    ("DevOps Engineer", 135, 170), ("Mobile Engineer", 125, 160), ("Security Engineer", 150, 190),
                    ("Machine Learning Engineer", 165, 245)],
    "Sales": [("Account Executive", 85, 110), ("Sales Development Rep", 55, 70), ("Enterprise Account Executive", 120, 150),
              ("Sales Engineer", 125, 155), ("Revenue Operations Analyst", 80, 100), ("Sales Manager", 130, 160)],
    "Customer Success": [("Customer Success Manager", 80, 100), ("Support Specialist", 50, 65), ("Implementation Consultant", 85, 110),
                         ("Support Team Lead", 75, 90), ("Onboarding Specialist", 60, 75)],
    "Product & Design": [("Product Manager", 140, 175), ("Senior Product Designer", 130, 165), ("UX Researcher", 110, 140),
                         ("Product Analyst", 95, 120), ("Technical Writer", 85, 105)],
}
MULTI_OPENING = {"Account Executive": 3, "Sales Development Rep": 2, "Support Specialist": 2}
DEPT_WEIGHTS = {"Engineering": 22, "Sales": 16, "Customer Success": 12, "Product & Design": 10}
LOCATIONS = ["Remote (US)", "Remote (US)", "Austin, TX", "Denver, CO", "Chicago, IL"]
SOURCES = ["LinkedIn", "LinkedIn", "Referral", "Careers page", "Careers page", "Indeed", "Agency", "Wellfound"]
N_ROLES = 60
FIRST_REQ = 101
N_ROLE_DUPES = 2
N_CANDIDATES = 196
N_DUAL = 5
N_EXACT_DUPES = 6
N_CASE_DUPES = 4
ACTIVE = ("Applied", "Screen", "Interview", "Offer")
STAGE_WORDS = {"Applied": ["Applied", "Applied", "New applicant"], "Screen": ["Phone Screen", "Screening"],
               "Interview": ["Interview", "Onsite"], "Offer": ["Offer", "Offer Extended"], "Hired": ["Hired"],
               "Rejected": ["Rejected", "Rejected", "Not selected"], "Withdrawn": ["Withdrawn"], "Declined offer": ["Offer declined"]}
ROLE_COLUMNS = ["Req ID", "Title", "Department", "Hiring Manager", "Location", "Salary Min", "Salary Max", "Openings",
                "Opened", "Status", "Filled On"]
CAND_COLUMNS = ["Candidate", "Email", "Phone", "Req ID", "Role", "Source", "Applied", "Stage", "Stage Date",
                "Expected Salary", "Hired On", "Notes"]
NOTES = ["", "", "", "", "", "Relocating from Seattle", "Needs visa sponsorship", "Strong portfolio", "Referred by a current employee",
         "Asked about hybrid schedule", "Available in 30 days", "Counter-offer risk", "Returned recruiter call", "Second-round no-show, rescheduled"]


def fmt_date(d: date, style: int) -> str:
    return [d.isoformat(), f"{d.month}/{d.day}/{d.year}", d.strftime("%d-%b-%Y"), f"{d.strftime('%b')} {d.day}, {d.year}"][style % 4]


def fmt_salary(v: int, style: int) -> str:
    return [f"${v:,}", f"{v}", f"{v // 1000}k" if v % 1000 == 0 else f"{v}"][style % 3]


def req_label(n: int) -> str:
    return f"REQ-{n:04d}"


def build(seed: int, attempt: int) -> dict:
    rng = random.Random(seed * 1000 + attempt)

    # ---------------- roles
    roles = []
    depts = [d for d, w in DEPT_WEIGHTS.items() for _ in range(w)]
    rng.shuffle(depts)
    depts = depts[:N_ROLES]
    span_days = (AS_OF - date(2025, 3, 3)).days - 20
    opened_days = sorted(int(span_days * (1 - rng.random() ** 1.5)) for _ in range(N_ROLES))  # hiring accelerated this year
    for k, (dept, off) in enumerate(zip(depts, opened_days)):
        title, lo, hi = rng.choice(TITLES[dept])
        opened = date(2025, 3, 3) + timedelta(days=off)
        age = (AS_OF - opened).days
        r = rng.random()
        if age > 200:
            status = "Filled" if r < 0.90 else "Cancelled"
        elif age > 90:
            status = "Filled" if r < 0.50 else "Open" if r < 0.82 else "On hold" if r < 0.92 else "Cancelled"
        else:
            status = "Open" if r < 0.80 else "On hold" if r < 0.90 else "Filled"
        band_lo, band_hi = lo * 1000 + rng.choice([0, 5000]), hi * 1000 + rng.choice([0, 5000, 10000])
        roles.append({"no": FIRST_REQ + k, "title": title, "dept": dept, "manager": MANAGERS[dept][0],
                      "location": rng.choice(LOCATIONS), "min": band_lo, "max": band_hi,
                      "openings": MULTI_OPENING.get(title, 1), "opened": opened, "status": status, "filled_on": None})
    # the offer-band test role: a Ken role opened this week, one opening, no applicants yet
    test_role = {"no": FIRST_REQ + N_ROLES, "title": "Senior Backend Engineer", "dept": "Engineering", "manager": RESTRICTED,
                 "location": "Remote (US)", "min": 150000, "max": 185000, "openings": 1, "opened": date(2026, 9, 8),
                 "status": "Open", "filled_on": None}
    roles.append(test_role)
    by_no = {r["no"]: r for r in roles}

    # ---------------- people
    manager_names = {m for m, _ in MANAGERS.values()}
    manager_last = {m.split(" ")[1] for m in manager_names}
    names = [(f, l) for f in FIRST for l in LAST if l not in manager_last and f not in ("Ken", "Maria", "Jordan", "Aisha")]
    rng.shuffle(names)
    people = []
    used = set()
    for i in range(N_CANDIDATES):
        f, l = names[i]
        dom = rng.choice(EMAIL_DOMAINS)
        email = rng.choice([f"{f}.{l}", f"{f[0]}{l}", f"{f}{l}{rng.randint(1, 99)}", f"{l}.{f}"]).lower() + "@" + dom
        while email in used:
            email = f"{f}.{l}{rng.randint(100, 999)}@{dom}".lower()
        used.add(email)
        people.append({"name": f"{f} {l}", "email": email, "phone": f"512555{rng.randint(1000, 9999)}", "source": rng.choice(SOURCES)})
    # two different people with one name
    pair_a, pair_b = 0, 1
    people[pair_b]["name"] = people[pair_a]["name"]
    fa, la = people[pair_a]["name"].split(" ")
    people[pair_a]["email"] = f"{fa}.{la}@gmail.com".lower()
    people[pair_b]["email"] = f"{fa[0]}{la}{rng.randint(60, 99)}@outlook.com".lower()

    # ---------------- applications
    apps = []
    open_like = [r for r in roles if r is not test_role]
    weights = [6 if r["status"] == "Open" else 2 if r["status"] == "Filled" else 1 for r in open_like]
    role_for = [rng.choices(open_like, weights=weights)[0] for _ in people]
    # every filled role needs at least as many applicants as openings
    for r in open_like:
        if r["status"] == "Filled":
            have = sum(1 for x in role_for if x is r)
            for _ in range(r["openings"] + 1 - have):
                idx = rng.randrange(len(people))
                role_for[idx] = r
    for i, (p, r) in enumerate(zip(people, role_for)):
        apps.append({"person": i, "role": r["no"], "stage": None, "applied": None, "stage_date": None, "hired_on": None,
                     "expected": None, "notes": rng.choice(NOTES), "flag": None})
    # dual applicants: a second application to a role with a different manager
    dual_people = rng.sample([i for i in range(2, len(people))], N_DUAL)
    for i in dual_people:
        first_role = by_no[apps[i]["role"]]
        others = [r for r in open_like if r["manager"] != first_role["manager"] and r["status"] == first_role["status"]]
        if not others:
            raise ValueError("no second role")
        r2 = rng.choice(others)
        apps.append({"person": i, "role": r2["no"], "stage": None, "applied": None, "stage_date": None, "hired_on": None,
                     "expected": None, "notes": "", "flag": None})

    # stages and dates, role by role
    for r in open_like:
        mine = [a for a in apps if a["role"] == r["no"]]
        rng.shuffle(mine)
        end = AS_OF
        if r["status"] == "Filled":
            hires = [a for a in mine if a["person"] not in dual_people][: r["openings"]]
            if len(hires) < r["openings"]:
                raise ValueError("not enough hires")
            for a in mine:
                a["stage"] = "Hired" if a in hires else rng.choices(["Rejected", "Withdrawn", "Declined offer"], weights=[80, 12, 8])[0]
        elif r["status"] == "Cancelled":
            for a in mine:
                a["stage"] = rng.choice(["Rejected", "Withdrawn"])
        elif r["status"] == "On hold":
            for a in mine:
                a["stage"] = rng.choice(["Applied", "Screen", "Rejected"])
        else:
            for a in mine:
                a["stage"] = rng.choices(["Applied", "Screen", "Interview", "Offer", "Rejected", "Withdrawn"], weights=[30, 24, 20, 6, 16, 4])[0]
        for a in mine:
            span = max(3, (end - r["opened"]).days - (40 if a["stage"] == "Hired" else 2))
            a["applied"] = r["opened"] + timedelta(days=rng.randint(1, span))
            if a["stage"] == "Hired":
                a["hired_on"] = a["applied"] + timedelta(days=rng.randint(14, 58))
                if a["hired_on"] > AS_OF:
                    a["hired_on"] = AS_OF
                a["stage_date"] = a["hired_on"]
            else:
                a["stage_date"] = min(AS_OF, a["applied"] + timedelta(days=rng.randint(0, 30)))
            if rng.random() < 0.9:
                a["expected"] = int(round(rng.uniform(r["min"] * 0.95, r["max"] * 1.08) / 1000.0)) * 1000
        if r["status"] == "Filled":
            r["filled_on"] = max(a["hired_on"] for a in mine if a["stage"] == "Hired")
    # dual applicants keep the same activity on both applications (both in process, or both closed)
    for i in dual_people:
        mine = [a for a in apps if a["person"] == i]
        if (mine[0]["stage"] in ACTIVE) != (mine[1]["stage"] in ACTIVE):
            mine[1]["stage"] = rng.choice(["Applied", "Screen"]) if mine[0]["stage"] in ACTIVE else "Rejected"
            if mine[1]["stage"] == "Hired":
                raise ValueError("dual hired")
    if sum(1 for i in dual_people if all(a["stage"] in ACTIVE for a in apps if a["person"] == i)) < 2:
        raise ValueError("need active dual applicants")
    # the impossible hire: Hired On typed before Applied
    hired = [a for a in apps if a["stage"] == "Hired"]
    bad = rng.choice(hired)
    bad["hired_on"] = bad["applied"] - timedelta(days=rng.randint(30, 50))
    bad["stage_date"] = bad["hired_on"]
    bad["flag"] = "hired_before_applied"
    # unique top expected salary, written as a currency string
    top_app = max((a for a in apps if a["expected"]), key=lambda a: a["expected"])
    top_app["expected"] = max(a["expected"] for a in apps if a["expected"]) + 7000

    # ---------------- rows
    role_rows = []
    for r in roles:
        mgr_canon, variants = MANAGERS[r["dept"]]
        role_rows.append({
            "Req ID": req_label(r["no"]), "Title": r["title"], "Department": r["dept"],
            "Hiring Manager": mgr_canon if rng.random() < 0.65 else rng.choice(variants),
            "Location": r["location"], "Salary Min": fmt_salary(r["min"], rng.randrange(3)), "Salary Max": fmt_salary(r["max"], rng.randrange(3)),
            "Openings": str(r["openings"]), "Opened": fmt_date(r["opened"], rng.randrange(4)),
            "Status": rng.choice({"Open": ["Open", "Open", "open"], "Filled": ["Filled", "Filled", "Closed - filled"],
                                  "On hold": ["On hold", "On Hold"], "Cancelled": ["Cancelled"]}[r["status"]]),
            "Filled On": fmt_date(r["filled_on"], rng.randrange(4)) if r["filled_on"] else "", "_no": r["no"], "_role": "unique"})
    top_role = max(roles, key=lambda r: r["max"])
    if sum(1 for r in roles if r["max"] == top_role["max"]) != 1:
        raise ValueError("salary max tie")
    next(x for x in role_rows if x["_no"] == top_role["no"])["Salary Max"] = fmt_salary(top_role["max"], 0)
    tr = next(x for x in role_rows if x["_no"] == test_role["no"])
    tr.update({"Hiring Manager": "Okafor, Ken", "Salary Min": "150k", "Salary Max": "$185,000"})
    dup_roles = rng.sample([x for x in role_rows if x["_no"] != test_role["no"]], N_ROLE_DUPES)
    role_rows_out = sorted(role_rows + [dict(x, _role="exact_duplicate") for x in dup_roles], key=lambda x: x["_no"])

    cand_rows = []
    for a in apps:
        p, r = people[a["person"]], by_no[a["role"]]
        s = rng.random()
        req_out = req_label(r["no"]) if s < 0.6 else str(r["no"]) if s < 0.8 else f"REQ-{r['no']}"
        cand_rows.append({
            "Candidate": p["name"], "Email": p["email"], "Phone": phone_variant(p["phone"], rng.randrange(7)),
            "Req ID": req_out, "Role": r["title"], "Source": p["source"], "Applied": fmt_date(a["applied"], rng.randrange(4)),
            "Stage": rng.choice(STAGE_WORDS[a["stage"]]), "Stage Date": fmt_date(a["stage_date"], rng.randrange(4)),
            "Expected Salary": "" if not a["expected"] else fmt_salary(a["expected"], rng.randrange(3)),
            "Hired On": fmt_date(a["hired_on"], rng.randrange(4)) if a["hired_on"] else "", "Notes": a["notes"],
            "_app": a, "_role": "unique"})
    pb_row = next(x for x in cand_rows if x["_app"]["person"] == pair_b)
    pb_row["Notes"] = f"Not the same person as the other {people[pair_a]['name']} (checked by phone)"
    top_row = next(x for x in cand_rows if x["_app"] is top_app)
    top_row["Expected Salary"] = fmt_salary(top_app["expected"], 0)
    k_row = next((x for x in cand_rows if x["_app"]["expected"] and x["_app"]["expected"] % 1000 == 0 and x["Expected Salary"].endswith("k")
                  and x["_app"] is not top_app and x["_app"]["person"] not in dual_people + [pair_a, pair_b]
                  and by_no[x["_app"]["role"]]["manager"] == RESTRICTED), None)
    if k_row is None:
        raise ValueError("no k-salary example")
    pool = [x for x in cand_rows if x["_app"]["person"] not in dual_people + [pair_a, pair_b] and x["_app"]["flag"] is None
            and x is not top_row and x is not k_row]
    picks = rng.sample(pool, N_EXACT_DUPES + N_CASE_DUPES)
    extra = [dict(x, _role="exact_duplicate") for x in picks[:N_EXACT_DUPES]]
    for x in picks[N_EXACT_DUPES:]:
        p = people[x["_app"]["person"]]
        local, _, dom = p["email"].partition("@")
        extra.append(dict(x, Email=rng.choice([p["email"].upper(), local.capitalize() + "@" + dom, local + "@" + dom.upper()]),
                          Phone=phone_variant(p["phone"], rng.randrange(7)), Notes="re-applied", _role="same_email_different_case"))
    cand_rows_out = cand_rows + extra
    rng.shuffle(cand_rows_out)
    for n, x in enumerate(cand_rows_out, start=2):
        x["_line"] = n
    return {"roles": roles, "role_rows": role_rows_out, "people": people, "apps": apps, "cand_rows": cand_rows_out,
            "dual": dual_people, "pair": (pair_a, pair_b), "bad": bad, "top_app": top_app, "top_role": top_role,
            "test_role": test_role, "k_row": k_row}


def summarize(t: dict) -> dict:
    roles, people, apps = t["roles"], t["people"], t["apps"]
    by_no = {r["no"]: r for r in roles}
    ken_roles = [r for r in roles if r["manager"] == RESTRICTED]
    ken_people = sorted({a["person"] for a in apps if by_no[a["role"]]["manager"] == RESTRICTED})
    active_people = sorted({a["person"] for a in apps if a["stage"] in ACTIVE})
    ken_active = sorted({a["person"] for a in apps if a["stage"] in ACTIVE and by_no[a["role"]]["manager"] == RESTRICTED})
    offers = [a for a in apps if a["stage"] == "Offer"]
    hires = [a for a in apps if a["stage"] == "Hired"]
    good_hires = [a for a in hires if a["flag"] is None]
    tth = sum((a["hired_on"] - a["applied"]).days for a in good_hires) / len(good_hires)
    tth_naive = sum((a["hired_on"] - a["applied"]).days for a in hires) / len(hires)
    if not 18 <= sum(1 for r in roles if r["status"] == "Open") <= 26 or len(active_people) < 50:
        raise ValueError("pipeline too thin")
    if abs(tth * 10 - round(tth * 10)) > 0.42 or abs(tth_naive - tth) < 0.3:
        raise ValueError("time-to-hire too close to a rounding edge")
    by_dept = {}
    for d in MANAGERS:
        hs = [a for a in good_hires if by_no[a["role"]]["dept"] == d]
        if not hs:
            raise ValueError("department without hires")
        v = sum((a["hired_on"] - a["applied"]).days for a in hs) / len(hs)
        if abs(v * 10 - round(v * 10)) > 0.42:
            raise ValueError("department time-to-hire near a rounding edge")
        by_dept[d] = {"hires": len(hs), "average_days": round(v, 1)}

    # search term: a last name whose substring hits exactly the candidates bearing it, in every exported text field
    def person_text(i):
        rows = [x for x in t["cand_rows"] if x["_app"]["person"] == i]
        return " ".join(" ".join(str(x[c]) for c in CAND_COLUMNS) for x in rows).lower()
    texts = {i: person_text(i) for i in range(len(people))}
    all_role_text = " ".join(" ".join(str(x[c]) for c in ROLE_COLUMNS) for x in t["role_rows"]).lower()
    search = None
    for last in sorted({p["name"].split(" ")[1] for p in people}):
        term = last.lower()
        by_name = [i for i, p in enumerate(people) if term in p["name"].lower()]
        anywhere = [i for i in range(len(people)) if term in texts[i]]
        dup_hit = any(x["_role"] != "unique" and x["_app"]["person"] in by_name for x in t["cand_rows"])
        if 3 <= len(by_name) <= 4 and by_name == anywhere and term not in all_role_text and dup_hit and len(term) >= 5:
            search = (last, by_name)
            break
    if search is None:
        raise ValueError("no search term")
    source_hits = sorted({i for i, p in enumerate(people) if p["source"] == "Agency" and any(a["person"] == i for a in apps)})
    top = t["top_app"]
    unique_rows = [x for x in t["cand_rows"] if x["_role"] == "unique" and x["Expected Salary"]]
    text_top = max(unique_rows, key=lambda x: x["Expected Salary"])
    if text_top["_app"] is top:
        raise ValueError("text sort would pass")
    oos_pool = [i for i in range(len(people)) if i not in ken_people and i not in t["dual"] and i not in t["pair"]
                and any(a["person"] == i and by_no[a["role"]]["manager"] == "Maria Santos" and a["stage"] in ACTIVE for a in apps)]
    oos = people[sorted(oos_pool)[0]]
    oos_app = next(a for a in apps if people[a["person"]] is oos)

    dual_info = []
    for i in t["dual"]:
        mine = [a for a in apps if a["person"] == i]
        dual_info.append({"candidate": people[i]["name"], "email": people[i]["email"],
                          "roles": [{"req": req_label(a["role"]), "title": by_no[a["role"]]["title"], "manager": by_no[a["role"]]["manager"],
                                     "stage": a["stage"]} for a in mine]})
    dual_active = next(d for d in dual_info if all(x["stage"] in ACTIVE for x in d["roles"]) and any(x["manager"] == RESTRICTED for x in d["roles"])) \
        if any(all(x["stage"] in ACTIVE for x in d["roles"]) and any(x["manager"] == RESTRICTED for x in d["roles"]) for d in dual_info) else None
    if dual_active is None:
        raise ValueError("need an active dual applicant with a Ken role")
    pa, pb = (people[i] for i in t["pair"])
    pa_app = next(a for a in apps if a["person"] == t["pair"][0])
    pb_app = next(a for a in apps if a["person"] == t["pair"][1])
    bad = t["bad"]
    bad_row = next(x for x in t["cand_rows"] if x["_app"] is bad and x["_role"] == "unique")
    k_row = t["k_row"]
    # pipeline report example: the Ken role with the most applications that is open
    ken_open = [r for r in ken_roles if r["status"] == "Open" and r is not t["test_role"]]
    pipe_role = max(ken_open, key=lambda r: (sum(1 for a in apps if a["role"] == r["no"]), -r["no"]))
    pipe = {s: sum(1 for a in apps if a["role"] == pipe_role["no"] and a["stage"] == s) for s in STAGE_WORDS}
    declined = sum(1 for a in apps if a["stage"] == "Declined offer")
    manager_spellings = sorted({x["Hiring Manager"] for x in t["role_rows"]})
    if len({req_label(r["no"]) for r in roles}) != len(roles):
        raise ValueError("role ids")
    status_counts = {s: sum(1 for r in roles if r["status"] == s) for s in ("Open", "On hold", "Filled", "Cancelled")}
    uniq_role_rows = [x for x in t["role_rows"] if x["_role"] == "unique"]
    role_text_top = max(uniq_role_rows, key=lambda x: x["Salary Max"])
    if role_text_top["_no"] == t["top_role"]["no"]:
        raise ValueError("role text sort would pass")
    link_candidates = []
    for r in roles:
        rows_r = [x for x in t["cand_rows"] if x["_role"] == "unique" and x["_app"]["role"] == r["no"]]
        forms = sorted({x["Req ID"] for x in rows_r})
        if any(f.isdigit() for f in forms) and len(forms) >= 3:
            link_candidates.append((len(rows_r), -r["no"], r, forms, rows_r))
    if not link_candidates:
        raise ValueError("no linked-role example")
    _, _, link_role, link_forms, link_rows = max(link_candidates, key=lambda z: (z[0], z[1]))

    counts = {
        "baseline": {
            "STAFF_ROLE": "Hiring manager",
            "VIEWER_ROLE": "Read-only (the CEO)",
            "MAIN_ENTITY": "candidate",
            "MAIN_ENTITY_PLURAL": "candidates",
            "restricted_user": RESTRICTED,
            "SCOPE_COUNT": len(ken_people),
            "OUT_OF_SCOPE_EXAMPLE": {"candidate": oos["name"], "req": req_label(oos_app["role"]), "title": by_no[oos_app["role"]]["title"],
                                     "manager": by_no[oos_app["role"]]["manager"]},
            "KPI_1": {"name": "active candidates", "value": len(active_people), "scoped_value": len(ken_active),
                      "definition": "people with at least one application at Applied, Screen, Interview, or Offer"},
            "KPI_2": {"name": "open roles", "value": status_counts["Open"]},
            "KPI_3": {"name": "offers out", "value": len(offers)},
            "KPI_4": {"name": "average time to hire (days)", "value": round(tth, 1), "hires_counted": len(good_hires),
                      "naive_including_impossible_row": round(tth_naive, 1)},
            "SEARCH_TERM": search[0], "SEARCH_COUNT": len(search[1]), "search_hits": [people[i]["name"] for i in search[1]],
            "FILTER_FIELD": "source", "FILTER_VALUE": "Agency", "FILTER_COUNT": len(source_hits),
            "SORT_FIELD": "expected salary", "SORT_TOP": {"candidate": people[top["person"]]["name"], "expected_salary": top["expected"],
                                                          "file_value": f"${top['expected']:,}"},
            "text_sort_top_would_be": {"candidate": people[text_top["_app"]["person"]]["name"], "file_value": text_top["Expected Salary"]},
            "EXPORT_ROWS": len(people),
            "EXPORT_COLUMNS": ["name", "email", "role", "stage", "source"],
            "REQUIRED_FIELD": "an email address",
        },
        "roles": {
            "file_rows_excluding_header": len(t["role_rows"]),
            "exact_duplicate_rows": N_ROLE_DUPES,
            "unique_roles": len(roles),
            "by_status": status_counts,
            "per_manager": {m: sum(1 for r in roles if r["manager"] == m) for m, _ in MANAGERS.values()},
            "manager_spellings_in_file": manager_spellings,
            "ken_open_roles": sum(1 for r in ken_roles if r["status"] == "Open"),
            "highest_salary_max": {"req": req_label(t["top_role"]["no"]), "title": t["top_role"]["title"], "salary_max": t["top_role"]["max"],
                                   "file_value": fmt_salary(t["top_role"]["max"], 0),
                                   "text_sort_top_would_be": {"req": req_label(role_text_top["_no"]), "file_value": role_text_top["Salary Max"]}},
            "linked_role_example": {"req": req_label(link_role["no"]), "title": link_role["title"], "manager": link_role["manager"],
                                    "applications": len(link_rows), "id_forms_in_candidates_file": link_forms},
            "status_words": {"Open": ["Open", "open"], "Filled": ["Filled", "Closed - filled"], "On hold": ["On hold", "On Hold"], "Cancelled": ["Cancelled"]},
            "offer_band_test_role": {"req": req_label(t["test_role"]["no"]), "title": t["test_role"]["title"], "manager": RESTRICTED,
                                     "salary_min": 150000, "salary_max": 185000, "file_values": {"Salary Min": "150k", "Salary Max": "$185,000"},
                                     "openings": 1, "applications": 0, "over_band_offer": 190000},
        },
        "candidates": {
            "file_rows_excluding_header": len(t["cand_rows"]),
            "exact_duplicate_rows": N_EXACT_DUPES,
            "same_email_different_case_rows": N_CASE_DUPES,
            "unique_candidates": len(people),
            "unique_applications": len(apps),
            "dedupe_rule": "A candidate is a person, keyed by Email after trimming and lowercasing; each person keeps every distinct role they applied to. Rows repeating the same person and role collapse into one application. Same name with different emails = different people.",
            "req_id_forms": ["REQ-0131", "131", "REQ-131"],
            "duplicate_rows": [{"candidate": x["Candidate"], "email_as_written": x["Email"], "kind": x["_role"], "file_line": x["_line"]}
                               for x in t["cand_rows"] if x["_role"] != "unique"],
            "dual_applicants": dual_info,
            "dual_active_with_ken_role": dual_active,
            "same_name_pair": {"name": pa["name"], "first": {"email": pa["email"], "req": req_label(pa_app["role"]), "title": by_no[pa_app["role"]]["title"]},
                               "second": {"email": pb["email"], "req": req_label(pb_app["role"]), "title": by_no[pb_app["role"]]["title"]}},
            "k_salary_example": {"candidate": k_row["Candidate"], "file_value": k_row["Expected Salary"], "value": k_row["_app"]["expected"]},
            "impossible_hire": {"candidate": people[bad["person"]]["name"], "req": req_label(bad["role"]), "days": (bad["hired_on"] - bad["applied"]).days,
                                "applied": bad["applied"].isoformat(),
                                "hired_on": bad["hired_on"].isoformat(), "file_values": {"Applied": bad_row["Applied"], "Hired On": bad_row["Hired On"]}},
            "stage_mapping": STAGE_WORDS,
            "by_stage_applications": {s: sum(1 for a in apps if a["stage"] == s) for s in STAGE_WORDS},
            "naive_alternatives": {"rows": len(t["cand_rows"]), "exact_repeats_removed": len(t["cand_rows"]) - N_EXACT_DUPES,
                                   "one_per_application": len(apps), "people_with_case_sensitive_email": len(people) + N_CASE_DUPES,
                                   "people_merged_by_name": len({p["name"] for p in people})},
        },
        "time_to_hire": {
            "definition": "days from Applied to Hired On, averaged over hired applications, excluding the impossible row",
            "hires": len(hires), "hires_counted": len(good_hires), "average_days": round(tth, 1),
            "naive_including_impossible_row": round(tth_naive, 1), "by_department": by_dept,
        },
        "changes": {
            "c1_pipeline_role": {"req": req_label(pipe_role["no"]), "title": pipe_role["title"], "by_stage": pipe},
            "c1_offer_acceptance": {"hired": len(hires), "declined": declined, "rate_percent": round(100 * len(hires) / (len(hires) + declined), 1)},
            "c1_ken_roles": len(ken_roles),
            "c1_offer_acceptance_bounds_percent": [round(100 * len(hires) / (len(hires) + declined) - 0.1, 1), round(100 * len(hires) / (len(hires) + declined) + 0.1, 1)],
        },
        "test_inputs": {
            "role": req_label(t["test_role"]["no"]), "candidates": ["QA Alex Stone", "QA Blair Stone"],
            "interview": {"interviewer": RESTRICTED, "first": "10:00 for 60 minutes", "overlapping": "10:30 for 60 minutes", "next_free": "11:00 for 60 minutes"},
            "offers": {"approved_offer": 180000, "over_band": 190000, "at_band_max": 185000},
        },
    }
    rate = 100 * len(hires) / (len(hires) + declined)
    if abs(rate * 10 - round(rate * 10)) > 0.42:
        raise ValueError("acceptance rate near a rounding edge")
    return counts


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    seed = ap.parse_args().seed
    last = None
    for attempt in range(300):
        try:
            truth = build(seed, attempt)
            counts = summarize(truth)
            break
        except (ValueError, StopIteration) as e:
            last = e
    else:
        raise SystemExit(f"no valid draw: {last}")
    counts = {"seed": seed, "attempt": attempt, **counts}
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "roles.csv"), ROLE_COLUMNS, [[x[c] for c in ROLE_COLUMNS] for x in truth["role_rows"]])
    write_csv(os.path.join(SEED_DIR, "candidates.csv"), CAND_COLUMNS, [[x[c] for c in CAND_COLUMNS] for x in truth["cand_rows"]], crlf=True)
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(counts, indent=2) + "\n")
    b = counts["baseline"]
    print(f"roles {counts['roles']['file_rows_excluding_header']} -> {counts['roles']['unique_roles']}; candidates "
          f"{counts['candidates']['file_rows_excluding_header']} rows -> {counts['candidates']['unique_candidates']} people / "
          f"{counts['candidates']['unique_applications']} applications; Ken sees {b['SCOPE_COUNT']}; attempt {attempt}")


if __name__ == "__main__":
    main()
