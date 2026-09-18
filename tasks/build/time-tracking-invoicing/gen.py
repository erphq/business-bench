#!/usr/bin/env python3
"""Deterministic seed generator for the time-tracking-invoicing build task.

    python gen.py [--seed N]

Writes:
  seed/clients.csv        64 rows from the billing system -> 60 clients (exact duplicates and
                          same-code rows written C-147 / C-0147 with the name in capitals)
  seed/rates.csv          rate card, one row per client per role, client codes written four ways,
                          rates as currency strings, one impossible negative rate
  seed/time_entries.csv   July and August 2026 timesheet export: exact duplicate rows, durations in
                          four formats, billable flags in eight spellings, July invoice numbers with a
                          few late July entries never invoiced
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the canonical public variant. Consultant names are fixed across seeds (the ask names
Nadia Okafor); other seeds re-roll clients, rates, entries, and durations, and counts.json is
recomputed from the truth, so a sealed variant re-derives its checklist numbers from it.
"""
from __future__ import annotations

import math
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, money_str, write_csv, write_json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

# ----------------------------------------------------------------------------- constants

CONSULTANTS = [  # fixed across seeds
    ("Eleanor Voss", "Partner"), ("Graham Achebe", "Partner"),
    ("Nadia Okafor", "Senior"), ("Marcus Iyer", "Senior"), ("Sofia Lindqvist", "Senior"), ("Daniel Reyes", "Senior"),
    ("Priya Raman", "Associate"), ("Tom Whitaker", "Associate"), ("Hana Kobayashi", "Associate"),
    ("Luis Ortega", "Associate"), ("Chloe Brandt", "Associate"), ("Owen Mensah", "Associate"),
]
ROLE_OF = dict(CONSULTANTS)
ROLES = ["Partner", "Senior", "Associate"]
RESTRICTED = "Nadia Okafor"
OTHER = "Marcus Iyer"
ENTRIES_PER_ROLE = {"Partner": 14, "Senior": 24, "Associate": 22}

CLIENT_NAMES = [
    "Ashgrove Manufacturing", "Bellwether Logistics", "Cairnfield Health Partners", "Delta Ridge Foods",
    "Evergreen Credit Union", "Fairhaven Senior Living", "Granite State Tooling", "Harborview Insurance Group",
    "Ironbark Construction", "Junebug Software", "Kestrel Aviation Services", "Lumen Dental Group",
    "Marlow & Finch LLP", "Northwind Energy Cooperative", "Oakline Furniture", "Pinecrest Schools Trust",
    "Quarterdeck Marine", "Redstone Property Group", "Silverbrook Pharmacy Network", "Tidewater Packaging",
    "Umberline Creative", "Vantage Fleet Solutions", "Westbridge Community Bank", "Yarrow Organics",
    "Zenith Precision Optics", "Alderbrook Clinics", "Brightwater Utilities", "Coppermine Analytics",
    "Dunmore Hospitality", "Ellery Textiles", "Foxhollow Veterinary Group", "Glenmoor Title & Escrow",
    "Highfield Robotics", "Inlet Seafood Distributors", "Jasper Ridge Winery", "Kingsway Transit Authority",
    "Larkfield Printing", "Millbrook Orthopedics", "Newcastle Freight Brokers", "Orchard Lane Grocers",
    "Palmetto Hill Advisors", "Quillon Legal Services", "Roselake Hospitality", "Sagebrush Irrigation",
    "Thornbury School District", "Upland Timber Products", "Vireo Biotech", "Wexford Steelworks",
    "Yellowpine Cabinetry", "Zephyr Wind Partners", "Amberleigh Care Homes", "Blackmoor Quarry Co",
    "Clearspring Water Authority", "Driftwood Home Goods", "Emberly Candle Works", "Fennimore Auto Group",
    "Goldcrest Mills", "Hawthorne Medical Supply", "Isleworth Book Distributors", "Jadeport Imports",
    "Kittering Dairy Cooperative", "Lowell & Pratt Architects", "Moorland Outdoor Supply", "Nettlefield Farms",
]
N_CLIENTS = 60
N_INACTIVE = 8
N_WITH_ENTRIES = 26
N_CLIENT_EXACT_DUPES = 2
N_CLIENT_CODE_DUPES = 2
N_ENTRY_DUPES = 8
N_LATE_JULY = 7
TERMS = ["Net 30", "Net 30", "Net 30", "net 30", "Net 15", "NET 45", "Net 45"]
TASKS = ["Discovery", "Analysis", "Workshop", "Reporting", "Project management"]
NOTES_BILLABLE = [
    "Process mapping session", "Stakeholder interviews", "Draft findings memo", "Steering committee prep",
    "Data request follow-up", "Financial model review", "Board deck revisions", "Vendor evaluation",
    "Weekly status call", "Requirements workshop", "Site visit", "Implementation planning",
    "Cost baseline analysis", "Interview synthesis", "Operating model options", "KPI definitions",
]
NOTES_NONBILLABLE = ["Internal review (no charge)", "Proposal prep", "Write-off: rework on memo", "Team handover"]
YES = ["Yes", "Y", "yes", "TRUE"]
NO = ["No", "N", "no", "FALSE"]
MONTH_START, MONTH_END = date(2026, 7, 1), date(2026, 8, 31)
AUG1 = date(2026, 8, 1)
DISCOUNT_THRESHOLD_CENTS = 1_000_000
SORT_TOP_MINUTES = 465  # 7h 45m, every other entry is at most 7h


# ----------------------------------------------------------------------------- helpers

def q_up(m: int) -> int:
    """Billable quarter-hours: each entry rounded UP to the next 15 minutes."""
    return -(-m // 15)


def q_nearest(m: int) -> int:
    return (m + 7) // 15


def cents(q: int, rate: int) -> int:
    return q * rate * 25  # q/4 hours x rate dollars x 100 cents


def usd(c: int) -> str:
    return f"{c / 100:,.2f}"


def hours(q: int) -> float:
    return q / 4


def fmt_duration(m: int, style: int) -> str:
    h, r = divmod(m, 60)
    if style == 0:
        return f"{h}:{r:02d}"
    if style == 1:
        return f"{m / 60:.2f}"
    if style == 2:
        return f"{m} min"
    return (f"{h}h {r}m" if h and r else f"{h}h") if h else f"{r}m"


def parse_duration_minutes(s: str) -> float:
    s = s.strip()
    if ":" in s:
        h, r = s.split(":"); return int(h) * 60 + int(r)
    if s.endswith(" min"):
        return float(s[:-4])
    if "h" in s or s.endswith("m"):
        tot = 0.0
        for part in s.split():
            tot += float(part[:-1]) * (60 if part.endswith("h") else 1)
        return tot
    return float(s) * 60


def written_q(s: str) -> int:
    return math.ceil(parse_duration_minutes(s) / 15 - 1e-9)


def weekdays(a: date, b: date) -> list[date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def domain_of(name: str) -> str:
    words = [w for w in name.lower().replace("&", " ").split() if w.isalpha()]
    return "".join(words[:2]) + ".com"


# ----------------------------------------------------------------------------- clients and rates

def build_clients(r):
    names = CLIENT_NAMES[:]
    r.shuffle(names)
    names = names[:N_CLIENTS]
    codes = r.sample(range(101, 990), N_CLIENTS)
    leads = [c for c, role in CONSULTANTS if role != "Associate"]
    clients = []
    for i, (name, code) in enumerate(zip(names, codes)):
        fn, ln = r.choice(FIRST), r.choice(LAST)
        rates = {
            "Partner": r.randrange(380, 460, 10),
            "Senior": r.randrange(250, 330, 10),
            "Associate": r.randrange(150, 220, 10),
        }
        clients.append({
            "code": code, "name": name, "contact": f"{fn} {ln}",
            "email": f"{fn[0]}{ln}@{domain_of(name)}".lower(), "terms": r.choice(TERMS),
            "status": "Active", "lead": r.choice(leads), "rates": rates,
        })
    for c in r.sample(clients, N_INACTIVE):
        c["status"] = "Inactive"
    return clients


def code_str(code: int, style: int) -> str:
    return [f"C-{code:04d}", f"C-{code}", f"{code:04d}", f"{code}"][style]


# ----------------------------------------------------------------------------- entries

def build_entries(r, clients):
    active = [c for c in clients if c["status"] == "Active"]
    with_entries = r.sample(active, N_WITH_ENTRIES)
    anchors, others = with_entries[:3], with_entries[3:]
    days = weekdays(MONTH_START, MONTH_END)
    aug_days = [d for d in days if d >= AUG1]
    july_late_days = [d for d in days if date(2026, 7, 24) <= d < AUG1]

    portfolio = {c: [] for c, _ in CONSULTANTS}
    names = [c for c, _ in CONSULTANTS]
    for cl in others:
        for who in r.sample(names, r.choice([1, 2, 2])):
            portfolio[who].append(cl)
    for who in names:
        portfolio[who] += r.sample(anchors, r.choice([1, 2]))

    minute_pool = [15, 20, 25, 30, 40, 45, 50, 60, 70, 75, 80, 90, 95, 100, 105, 120, 135, 150, 165, 180,
                   200, 210, 240, 270, 300, 330, 360, 390, 420]

    def minutes() -> int:
        return r.choice(minute_pool) if r.random() < 0.7 else r.randint(5, 415)

    entries = []

    def add(who, cl, d, m, billable):
        entries.append({"consultant": who, "role": ROLE_OF[who], "client": cl, "date": d, "minutes": m,
                        "billable": billable, "task": r.choice(TASKS),
                        "note": r.choice(NOTES_BILLABLE if billable else NOTES_NONBILLABLE)})

    for who, role in CONSULTANTS:
        n = ENTRIES_PER_ROLE[role] + r.randint(-3, 3)
        weights = [3 if cl in anchors else 1 for cl in portfolio[who]]
        for _ in range(n):
            cl = r.choices(portfolio[who], weights=weights)[0]
            add(who, cl, r.choice(days), minutes(), r.random() < 0.86)

    def aug_billable_cents(cl):
        return sum(cents(q_up(e["minutes"]), cl["rates"][e["role"]]) for e in entries
                   if e["client"] is cl and e["billable"] and e["date"] >= AUG1)

    # anchor Z must clear the 10,000.00 discount threshold in August (change request 2)
    z = anchors[0]
    seniors_up = [c for c, role in CONSULTANTS if role != "Associate"]
    while aug_billable_cents(z) < 1_150_000:
        add(r.choice(seniors_up), z, r.choice(aug_days), r.choice([180, 210, 240, 300]), True)

    # invoice test client X: a non-anchor with 4 to 9 billable August entries
    def aug_billable(cl):
        return [e for e in entries if e["client"] is cl and e["billable"] and e["date"] >= AUG1]

    cands = sorted([cl for cl in others if 4 <= len(aug_billable(cl)) <= 9], key=lambda c: c["code"])
    if not cands:
        cands = sorted(others, key=lambda c: -len(aug_billable(c)))[:1]
        while len(aug_billable(cands[0])) < 4:
            add(r.choice(names), cands[0], r.choice(aug_days), minutes(), True)
    x = r.choice(cands)
    x_staff = sorted({e["consultant"] for e in entries if e["client"] is x})
    if not any(e["client"] is x and not e["billable"] and e["date"] >= AUG1 for e in entries):
        add(r.choice(x_staff), x, r.choice(aug_days), r.choice([30, 45, 60]), False)
    # one X entry must round differently up vs nearest (remainder 1..7)
    xa = aug_billable(x)
    if not any(1 <= e["minutes"] % 15 <= 7 for e in xa):
        xa[0]["minutes"] = 65
    # one X entry with a remainder of 8..14 so rounding the monthly total once differs from per entry
    if sum(1 for e in xa if e["minutes"] % 15) < 2:
        xa[-1]["minutes"] = 50
    # late July entries (billable, never invoiced); X gets one
    x_late = next((e for e in entries if e["client"] is x and e["billable"] and e["date"] in july_late_days), None)
    if x_late is None:
        add(r.choice(x_staff), x, r.choice(july_late_days), r.choice([90, 105, 120]), True)
        x_late = entries[-1]
    late = [x_late]
    pool = [e for e in entries if e["billable"] and e["date"] in july_late_days and e is not x_late and e["client"] is not x]
    r.shuffle(pool)
    late += pool[:N_LATE_JULY - 1]
    for e in entries:
        e["late"] = any(e is l for l in late)

    # the unique longest entry (sort target), billable, August, formatted as "7h 45m"
    top_who = r.choice([c for c, _ in CONSULTANTS if c != RESTRICTED])
    add(top_who, r.choice(portfolio[top_who]), r.choice(aug_days), SORT_TOP_MINUTES, True)
    entries[-1]["forced_style"] = 3
    entries[-1]["late"] = False
    top = entries[-1]

    entries.sort(key=lambda e: (e["date"], e["consultant"], e["client"]["code"], e["minutes"]))
    for i, e in enumerate(entries):
        e["id"] = f"TE-{40001 + i}"
        e["style"] = e.get("forced_style", r.choices([0, 1, 2, 3], weights=[40, 30, 15, 15])[0])
        e["dur"] = fmt_duration(e["minutes"], e["style"])
        assert written_q(e["dur"]) == q_up(e["minutes"]), (e["dur"], e["minutes"])
        e["date_str"] = date_variant(e["date"], r.choice([0, 0, 1, 1, 2, 3, 4, 6]))
        e["billable_str"] = r.choice(YES if e["billable"] else NO)
        e["invoice"] = ""
        if e["billable"] and e["date"] < AUG1 and not e["late"]:
            e["invoice"] = f"INV-2607-{e['client']['code']:04d}"
        v = r.random()
        cname = e["client"]["name"]
        e["client_str"] = cname.upper() if v < 0.06 else (cname + " " if v < 0.10 else cname)
        e["amount"] = cents(q_up(e["minutes"]), e["client"]["rates"][e["role"]])
    return entries, anchors, x, top


# ----------------------------------------------------------------------------- main

def main() -> None:
    seed = argparse_seed()
    r = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)

    clients = build_clients(r)
    entries, anchors, x, top = build_entries(r, clients)
    by_code = {c["code"]: c for c in clients}
    used_clients = {id(e["client"]) for e in entries}

    # ---------------- clients.csv
    client_rows = []
    for c in clients:
        client_rows.append({"src": c, "kind": "unique", "cols": [
            code_str(c["code"], 0), c["name"], c["contact"], c["email"], c["terms"], c["status"], c["lead"], ""]})
    dup_src = r.sample([c for c in clients if id(c) not in (id(x),)], N_CLIENT_EXACT_DUPES + N_CLIENT_CODE_DUPES)
    for c in dup_src[:N_CLIENT_EXACT_DUPES]:
        client_rows.append({"src": c, "kind": "exact_duplicate", "cols": [
            code_str(c["code"], 0), c["name"], c["contact"], c["email"], c["terms"], c["status"], c["lead"], ""]})
    for c in dup_src[N_CLIENT_EXACT_DUPES:]:
        client_rows.append({"src": c, "kind": "same_code_written_differently", "cols": [
            code_str(c["code"], 1), c["name"].upper() + " ", "", c["email"].upper(), c["terms"], c["status"], c["lead"],
            "re-keyed from old billing system"]})
    r.shuffle(client_rows)
    for i, row in enumerate(client_rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "clients.csv"),
              ["Client Code", "Client", "Billing Contact", "Billing Email", "Terms", "Status", "Engagement Lead", "Notes"],
              [row["cols"] for row in client_rows])

    # ---------------- rates.csv
    neg_candidates = sorted([c for c in clients if c["status"] == "Inactive" and id(c) not in used_clients],
                            key=lambda c: c["code"])
    neg_client = r.choice(neg_candidates)
    rate_rows = []
    for c in clients:
        for role in ROLES:
            style = 3 if c is x else r.choices([0, 1, 2, 3], weights=[50, 20, 15, 15])[0]
            rate = c["rates"][role]
            text = money_str(rate, r.choice([0, 1, 1, 2, 3, 6]))
            if c is x:
                text = money_str(rate, 1)
            if c is neg_client and role == "Associate":
                text = f"-${rate:,.2f}"
            role_text = r.choice([role, role, role, role.upper(), role.lower()])
            rate_rows.append([code_str(c["code"], style), role_text, text])
    r.shuffle(rate_rows)
    write_csv(os.path.join(SEED_DIR, "rates.csv"), ["Client Code", "Role", "Hourly Rate"], rate_rows)

    # ---------------- time_entries.csv
    dupe_pool = [e for e in entries if e is not top and e["client"] is not x]
    # the search client S: a non-anchor, non-X client with 5+ entries and a unique first word
    first_words = [c["name"].split()[0].lower() for c in clients]
    s_cands = sorted([c for c in clients if c not in anchors and c is not x and first_words.count(c["name"].split()[0].lower()) == 1
                      and 5 <= sum(1 for e in entries if e["client"] is c) <= 16], key=lambda c: c["code"])
    s_client = r.choice(s_cands)
    s_entry = r.choice([e for e in entries if e["client"] is s_client and e is not top])
    nb_entry = r.choice([e for e in dupe_pool if not e["billable"] and e is not s_entry])
    rest = [e for e in dupe_pool if e is not s_entry and e is not nb_entry]
    dupes = [s_entry, nb_entry] + r.sample(rest, N_ENTRY_DUPES - 2)
    rows = [{"e": e, "kind": "unique"} for e in entries]
    for e in dupes:
        pos = r.randint(0, len(rows))
        rows.insert(pos, {"e": e, "kind": "exact_duplicate"})
    for i, row in enumerate(rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "time_entries.csv"),
              ["Entry ID", "Date", "Consultant", "Role", "Client", "Task", "Notes", "Duration", "Billable", "Invoice #"],
              [[w["e"]["id"], w["e"]["date_str"], w["e"]["consultant"], w["e"]["role"], w["e"]["client_str"], w["e"]["task"],
                w["e"]["note"], w["e"]["dur"], w["e"]["billable_str"], w["e"]["invoice"]] for w in rows])

    # ---------------- truth-derived figures
    def lines_of(e):
        return sorted(w["line"] for w in rows if w["e"] is e)

    unbilled = [e for e in entries if e["billable"] and not e["invoice"]]
    unbilled_cents = sum(e["amount"] for e in unbilled)
    unbilled_q = sum(q_up(e["minutes"]) for e in unbilled)
    aug_bill = [e for e in entries if e["billable"] and e["date"] >= AUG1]
    aug_bill_q = sum(q_up(e["minutes"]) for e in aug_bill)
    clients_unbilled = len({id(e["client"]) for e in unbilled})
    mine = [e for e in entries if e["consultant"] == RESTRICTED]
    mine_unbilled_cents = sum(e["amount"] for e in unbilled if e["consultant"] == RESTRICTED)

    # invoice for X, August 2026
    x_aug = sorted([e for e in aug_bill if e["client"] is x], key=lambda e: e["id"])
    x_total = sum(e["amount"] for e in x_aug)
    x_nearest = sum(cents(q_nearest(e["minutes"]), x["rates"][e["role"]]) for e in x_aug)
    x_raw = round(sum(e["minutes"] / 60 * x["rates"][e["role"]] * 100 for e in x_aug))
    x_late = [e for e in entries if e["client"] is x and e["late"]]
    x_late_cents = sum(e["amount"] for e in x_late)
    x_nb_aug = [e for e in entries if e["client"] is x and not e["billable"] and e["date"] >= AUG1]
    x_nb_as_billable = sum(cents(q_up(e["minutes"]), x["rates"][e["role"]]) for e in x_nb_aug)
    x_unbilled = sum(e["amount"] for e in unbilled if e["client"] is x)
    assert x_total not in (x_nearest, x_raw, x_total + x_late_cents, x_total + x_nb_as_billable)
    assert x_unbilled == x_total + x_late_cents

    def show(e):
        return {"id": e["id"], "date": e["date"].isoformat(), "file_date": e["date_str"], "consultant": e["consultant"],
                "role": e["role"], "client": e["client"]["name"], "file_duration": e["dur"], "minutes": e["minutes"],
                "billed_hours": hours(q_up(e["minutes"])), "rate": e["client"]["rates"][e["role"]] if e["billable"] else None,
                "amount": usd(e["amount"]) if e["billable"] else "0.00", "billable": e["billable"],
                "invoice": e["invoice"], "file_lines": lines_of(e)}

    # locked examples: July invoiced entries, one of Nadia's and one of Marcus's
    single = [e for e in entries if not any(e is d for d in dupes) and e is not top]
    locked_nadia = r.choice(sorted([e for e in single if e["consultant"] == RESTRICTED and e["invoice"]], key=lambda e: e["id"]))
    locked_other = r.choice(sorted([e for e in single if e["consultant"] == OTHER and e["invoice"]], key=lambda e: e["id"]))
    out_of_scope = r.choice(sorted([e for e in single if e["consultant"] == OTHER and e["date"] >= AUG1 and not e["invoice"]],
                                   key=lambda e: e["id"]))
    # duration parse examples: one per written style, non-quarter minutes, not X's (X's entries get locked)
    parse_examples = []
    for style in (0, 1, 2, 3):
        pool = sorted([e for e in single if e["style"] == style and e["minutes"] % 15 and e["client"] is not x
                       and e["minutes"] > 15], key=lambda e: e["id"])
        parse_examples.append(show(r.choice(pool)))
    dup_examples = [show(e) for e in dupes[:2]]

    nonbillable = [e for e in entries if not e["billable"]]
    s_count = sum(1 for e in entries if e["client"] is s_client)
    s_word = s_client["name"].split()[0]
    haystack = [c for c, _ in CONSULTANTS] + TASKS + NOTES_BILLABLE + NOTES_NONBILLABLE + [c["name"] for c in clients if c is not s_client]
    assert not any(s_word.lower() in h.lower() for h in haystack)
    assert sum(1 for e in entries if e["minutes"] >= SORT_TOP_MINUTES) == 1

    # clients file facts
    exact_client = next(rw for rw in client_rows if rw["kind"] == "exact_duplicate")["src"]
    code_client = next(rw for rw in client_rows if rw["kind"] == "same_code_written_differently")["src"]

    def client_lines(c):
        return sorted(rw["line"] for rw in client_rows if rw["src"] is c)


    # change 1: billed hours and billed amount per consultant per month
    def billed(who, month):
        es = [e for e in entries if e["consultant"] == who and e["billable"] and e["date"].month == month]
        return {"billed_hours": hours(sum(q_up(e["minutes"]) for e in es)), "billed_amount": usd(sum(e["amount"] for e in es))}

    per_consultant = {who: {"july": billed(who, 7), "august": billed(who, 8)} for who, _ in CONSULTANTS}
    july_all = [e for e in entries if e["billable"] and e["date"].month == 7]

    # change 2: discount over 10,000.00 on the monthly invoice (pre-discount)
    z = anchors[0]
    z_total = sum(e["amount"] for e in aug_bill if e["client"] is z)
    assert z_total > DISCOUNT_THRESHOLD_CENTS and z_total % 10 == 0
    w_cands = sorted([c for c in clients if c is not z and c is not x and 300_000 <= sum(e["amount"] for e in aug_bill if e["client"] is c) < DISCOUNT_THRESHOLD_CENTS]
                     or [c for c in clients if c is not z and c is not x and 0 < sum(e["amount"] for e in aug_bill if e["client"] is c) < DISCOUNT_THRESHOLD_CENTS],
                     key=lambda c: c["code"])
    w = r.choice(w_cands)
    w_total = sum(e["amount"] for e in aug_bill if e["client"] is w)
    # change 3: draft invoice client Q
    q_cands = sorted([c for c in clients if c not in (x, z, w) and c not in anchors and 3 <= sum(1 for e in aug_bill if e["client"] is c) <= 8],
                     key=lambda c: c["code"])
    qc = r.choice(q_cands)
    q_total = sum(e["amount"] for e in aug_bill if e["client"] is qc)

    counts = {
        "seed": seed,
        "date_dependence": "No figure depends on the test date; all imported entries are dated July or August 2026.",
        "rules": {
            "rounding": "Each entry is rounded UP to the next 15 minutes before billing (7 min -> 0.25 h, 1:16 -> 1.50 h, 0:45 -> 0.75 h).",
            "amount": "billed hours x the client's hourly rate for the consultant's role",
            "unbilled": "billable entries with no invoice",
            "invoice": "one invoice per client per month holding that client's billable, uninvoiced entries dated in that month",
        },
        "rounding_check": {"minutes": [7, 76, 45], "billed_hours": [hours(q_up(m)) for m in (7, 76, 45)],
                           "nearest_quarter_wrong": [hours(q_nearest(m)) for m in (7, 76, 45)],
                           "unrounded_wrong": [round(m / 60, 2) for m in (7, 76, 45)]},
        "clients": {
            "file_rows_excluding_header": len(client_rows),
            "exact_duplicate_rows": N_CLIENT_EXACT_DUPES,
            "same_code_rows": N_CLIENT_CODE_DUPES,
            "wrong_count_only_exact_duplicates_removed": len(client_rows) - N_CLIENT_EXACT_DUPES,
            "unique_clients": N_CLIENTS,
            "active": sum(1 for c in clients if c["status"] == "Active"),
            "inactive": N_INACTIVE,
            "dedupe_rule": "same client code after dropping the C- prefix and leading zeros",
            "exact_duplicate_example": {"client": exact_client["name"], "code": code_str(exact_client["code"], 0), "file_lines": client_lines(exact_client)},
            "same_code_example": {"client": code_client["name"], "codes_as_written": [code_str(code_client["code"], 0), code_str(code_client["code"], 1)],
                                  "file_lines": client_lines(code_client)},
            "search_word_exact_duplicate": exact_client["name"].split()[0],
        },
        "rates": {
            "file_rows_excluding_header": len(rate_rows),
            "roles": ROLES,
            "join_example": {"client": x["name"], "clients_file_code": code_str(x["code"], 0), "rates_file_code": code_str(x["code"], 3),
                             "partner": f"{x['rates']['Partner']:.2f}", "senior": f"{x['rates']['Senior']:.2f}", "associate": f"{x['rates']['Associate']:.2f}"},
            "negative_rate": {"client": neg_client["name"], "code": code_str(neg_client["code"], 0), "role": "Associate",
                              "file_value": f"-${neg_client['rates']['Associate']:,.2f}", "client_has_entries": False},
        },
        "entries": {
            "file_rows_excluding_header": len(rows),
            "exact_duplicate_rows": N_ENTRY_DUPES,
            "unique_entries": len(entries),
            "per_consultant": {who: sum(1 for e in entries if e["consultant"] == who) for who, _ in CONSULTANTS},
            "billable": len(entries) - len(nonbillable),
            "non_billable": len(nonbillable),
            "invoiced_in_file": sum(1 for e in entries if e["invoice"]),
            "late_july_unbilled_entries": sorted(e["id"] for e in entries if e["late"]),
            "duplicate_examples": dup_examples,
            "duration_parse_examples": parse_examples,
            "longest_entry": show(top),
        },
        "baseline": {
            "STAFF_ROLE": "Consultant", "VIEWER_ROLE": "Read-only",
            "MAIN_ENTITY": "time entry", "MAIN_ENTITY_PLURAL": "time entries",
            "SCOPE_RULE": f"their own time entries ({RESTRICTED})",
            "SCOPE_COUNT": len(mine),
            "OUT_OF_SCOPE_EXAMPLE": show(out_of_scope),
            "KPI_1": "Unbilled amount", "KPI_1_VALUE": usd(unbilled_cents),
            "KPI_2": "Unbilled hours", "KPI_2_VALUE": hours(unbilled_q),
            "KPI_3": "Billable hours, August 2026", "KPI_3_VALUE": hours(aug_bill_q),
            "KPI_4": "Clients with unbilled time", "KPI_4_VALUE": clients_unbilled,
            "SCOPED_KPI_1_VALUE": usd(mine_unbilled_cents),
            "SEARCH_TERM": s_word, "SEARCH_COUNT": s_count,
            "FILTER_FIELD": "Billable", "FILTER_VALUE": "No", "FILTER_COUNT": len(nonbillable),
            "SORT_FIELD": "Duration (hours)", "SORT_TOP": top["id"],
            "EXPORT_ROWS": len(entries), "EXPORT_COLUMNS": ["Date", "Consultant", "Client", "Hours", "Billable", "Invoice"],
            "REQUIRED_FIELD": "Client",
            "search_client_has_duplicate_row": True,
        },
        "invoice_check": {
            "client": x["name"], "month": "2026-08",
            "lines": [show(e) for e in x_aug],
            "line_count": len(x_aug),
            "billed_hours": hours(sum(q_up(e["minutes"]) for e in x_aug)),
            "total": usd(x_total),
            "wrong_totals": {"rounded_to_nearest_quarter": usd(x_nearest), "no_rounding": usd(x_raw),
                             "including_late_july": usd(x_total + x_late_cents),
                             "including_non_billable": usd(x_total + x_nb_as_billable)},
            "excluded_late_july": [show(e) for e in x_late],
            "excluded_non_billable_august": [show(e) for e in x_nb_aug],
            "client_unbilled_before": usd(x_unbilled),
            "client_unbilled_wrong": {"late_july_missed": usd(x_total), "non_billable_included": usd(x_unbilled + x_nb_as_billable)},
            "july_invoice_total": usd(x_late_cents),
            "unbilled_drop_after_both_invoices": usd(x_total + x_late_cents),
        },
        "locked_examples": {"admin_edit": show(locked_other), "consultant_edit": show(locked_nadia)},
        "restricted_consultant": {"name": RESTRICTED, "role": ROLE_OF[RESTRICTED], "rate_for_invoice_client": x["rates"][ROLE_OF[RESTRICTED]]},
        "change_1_report": {"per_consultant": per_consultant,
                            "july_all_consultants": {"billed_hours": hours(sum(q_up(e["minutes"]) for e in july_all)),
                                                     "billed_amount": usd(sum(e["amount"] for e in july_all))},
                            "august_all_consultants": {"billed_hours": hours(aug_bill_q), "billed_amount": usd(sum(e["amount"] for e in aug_bill))}},
        "change_2_discount": {
            "threshold": "10,000.00 (strictly over, before discount)",
            "discounted_client": {"client": z["name"], "august_total": usd(z_total), "discount": usd(z_total // 10), "net": usd(z_total - z_total // 10)},
            "undiscounted_client": {"client": w["name"], "august_total": usd(w_total)},
            "boundary_test": {"rate": 250, "hours_no_discount": 40.0, "total_no_discount": "10,000.00",
                              "hours_discount": 40.25, "gross": "10,062.50", "discount": "1,006.25", "net": "9,056.25"},
        },
        "change_3_draft": {"client": qc["name"], "august_total": usd(q_total), "line_count": sum(1 for e in aug_bill if e["client"] is qc),
                           "entries": sorted(e["id"] for e in aug_bill if e["client"] is qc),
                           "client_unbilled": usd(sum(e["amount"] for e in unbilled if e["client"] is qc))},
    }
    write_json(os.path.join(REF_DIR, "counts.json"), counts)
    b = counts["baseline"]
    print(f"clients {len(client_rows)} rows -> {N_CLIENTS}; rates {len(rate_rows)} rows; entries {len(rows)} rows -> {len(entries)}")
    print(f"unbilled {b['KPI_1_VALUE']} / {b['KPI_2_VALUE']} h; Aug billable {b['KPI_3_VALUE']} h; X={x['name']} total {usd(x_total)}")


if __name__ == "__main__":
    main()
