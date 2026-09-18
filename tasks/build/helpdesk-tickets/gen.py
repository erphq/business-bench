#!/usr/bin/env python3
"""Deterministic seed generator for the helpdesk-tickets build task.

    python gen.py [--seed N]

Writes:
  seed/clients.csv        managed-service clients: exact duplicate rows and rows repeating a client under
                          its web domain written www.X / X.COM with "LLC" on the name, fees as strings
  seed/contacts.csv       client contacts: exact duplicate rows, the same email in another case, contacts
                          with no email (distinct people), client names in capitals
  seed/tickets.csv        July and August 2026 tickets: exact duplicate rows, ticket numbers written
                          HD-10917 / #10917 / 10917, priorities in six spellings, mixed timestamps,
                          tickets with a blank Client that belong to their contact's company, and one
                          ticket resolved before it was created
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Every imported response deadline falls before 2026-09-01, so the escalated count holds for any later
test date. Agent names are fixed across seeds (the ask names Sam Delgado); other seeds re-roll clients,
contacts, and tickets, and counts.json is recomputed from the truth.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import COMPANIES, FIRST, LAST, argparse_seed, phone_digits, phone_variant, write_csv, write_json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

AGENTS = ["Priya Nair", "Sam Delgado", "Jordan Blake", "Mei Chen", "Andre Silva", "Kate Morrison"]
RESTRICTED = "Sam Delgado"
OTHER = "Priya Nair"
SLA_HOURS = {1: 1, 2: 4, 3: 8, 4: 24}
PRIORITY_WEIGHTS = {1: 8, 2: 22, 3: 45, 4: 25}
PRIORITY_SPELLINGS = {1: ["P1", "p1", "1 - Critical", "P1 (Critical)"], 2: ["P2", "p2", "2 - High", "P2 (High)"],
                      3: ["P3", "p3", "3 - Normal", "P3 (Normal)"], 4: ["P4", "p4", "4 - Low", "P4 (Low)"]}
OPEN_STATUSES = ["New", "Open", "In Progress", "Waiting on client"]
EXTRA_CLIENTS = [("Harlow Pediatric Dentistry", "harlowpeds.com"), ("Ridgeview Animal Hospital", "ridgeviewanimal.com"),
                 ("Sterling & Voss CPAs", "sterlingvoss.com"), ("Canopy Coworking", "canopycowork.com"), ("Blue Mesa Title", "bluemesatitle.com"),
                 ("Northgate Chiropractic", "northgatechiro.com"), ("Pinewood Property Group", "pinewoodpg.com"), ("Lantern Hill Winery", "lanternhillwine.com"),
                 ("Summit Ridge Surveying", "summitridgesurvey.com"), ("Crescent Moon Bakery", "crescentmoonbakes.com"), ("Oakmont Insurance Agency", "oakmontins.com"),
                 ("Fairway Physical Therapy", "fairwaypt.com"), ("Granger Tool & Die", "grangertool.com"), ("Seaside Realty Partners", "seasiderp.com"),
                 ("Tallgrass Veterinary", "tallgrassvet.com"), ("Bramble & Birch Florals", "bramblebirch.com"), ("Keystone Freight Brokers", "keystonefb.com"),
                 ("Willowbrook Senior Care", "willowbrookcare.org")]
SUBJECTS = ["VPN won't connect", "VPN slow from home office", "Outlook keeps asking for password", "New starter laptop setup", "Printer offline",
            "Shared drive access request", "MFA reset", "Wi-Fi drops in conference room", "Phishing email reported", "Backup job failed",
            "Server disk space alert", "Teams audio not working", "License renewal question", "Firewall blocking website", "Password reset",
            "Laptop running slow", "Accounting software won't open", "Scan to email broken", "Offboarding user", "Domain renewal",
            "Suspicious login alert", "Monitor flickering", "Mailbox full", "Door badge reader offline", "Calendar sharing not working"]
NOTES = ["Reset credentials and confirmed with user.", "Replaced toner and cleared queue.", "Re-imaged device and restored profile.",
         "Adjusted firewall rule; site loads.", "Renewed license and emailed confirmation.", "Freed 40 GB on data volume; alert cleared.",
         "Re-enrolled MFA device.", "Granted access via security group.", "Updated VPN client to current version.", "Confirmed phishing, blocked sender."]
N_CLIENTS = 60
N_CLIENT_EXACT, N_CLIENT_DOMAIN = 2, 2
N_CONTACTS = 150
N_CONTACT_EXACT, N_CONTACT_CASE = 4, 6
N_CONTACT_NO_EMAIL = 3
N_TICKETS = 250
N_TICKET_EXACT, N_TICKET_NUMBER = 5, 5
N_BLANK_CLIENT = 8


def ts(t: datetime, style: int) -> str:
    h12 = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return [t.strftime("%Y-%m-%d %H:%M"), f"{t.month}/{t.day}/{t.year} {h12}:{t.minute:02d} {ampm}",
            t.strftime("%d-%b-%Y %H:%M"), t.strftime("%m/%d/%y %H:%M")][style]


def tnum(n: int, style: int) -> str:
    return [f"HD-{n}", f"#{n}", f"{n}", f"hd-{n}"][style]


def usd(c: int) -> str:
    return f"{c / 100:,.2f}"


def main() -> None:
    seed = argparse_seed()
    r = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)

    # ------------------------------------------------------------------ clients
    pool = [(n, d) for n, d, _ in COMPANIES] + EXTRA_CLIENTS
    r.shuffle(pool)
    clients = []
    acct_nums = r.sample(range(1001, 1999), N_CLIENTS)
    for i, (name, domain) in enumerate(pool[:N_CLIENTS]):
        clients.append({"acct": acct_nums[i], "name": name, "domain": domain, "tier": r.choice(["Gold", "Silver", "Silver", "Bronze"]),
                        "agent": r.choice(AGENTS) if i >= 5 else "", "fee": r.choice([45000, 65000, 89000, 120000, 145000, 210000]),
                        "start": date(2019, 1, 1) + timedelta(days=r.randint(0, 2400)), "contacts": []})
    r.shuffle(clients)

    # ------------------------------------------------------------------ contacts
    pairs = [(f, l) for f in FIRST for l in LAST]
    r.shuffle(pairs)
    contacts = []
    for i in range(N_CONTACTS):
        c = clients[i % N_CLIENTS] if i < N_CLIENTS * 2 else r.choice(clients)
        f, l = pairs[i]
        email = f"{f[0]}{l}@{c['domain']}".lower()
        if any(x["email"] == email for x in contacts):
            email = f"{f}.{l}@{c['domain']}".lower()
        ct = {"first": f, "last": l, "email": email, "phone": phone_digits(r), "client": c,
              "role": r.choice(["Primary", "Staff", "Staff", "Billing"]), "portal": r.choice(["Yes", "Yes", "No"])}
        contacts.append(ct)
        c["contacts"].append(ct)
    emails = [ct["email"] for ct in contacts]
    assert len(set(emails)) == len(emails)
    no_email = r.sample([ct for ct in contacts if len(ct["client"]["contacts"]) >= 2], N_CONTACT_NO_EMAIL)
    for ct in no_email:
        ct["email"] = ""
        ct["portal"] = "No"

    # ------------------------------------------------------------------ tickets
    start, end = datetime(2026, 7, 1, 7, 0), datetime(2026, 8, 31, 12, 0)
    ticket_nums = r.sample(range(10100, 12900), N_TICKETS)
    weights = [r.choice([1, 1, 2, 3, 5]) for _ in clients]
    tickets = []
    for i in range(N_TICKETS):
        c = r.choices(clients, weights=weights)[0]
        with_email = [ct for ct in c["contacts"] if ct["email"]]
        if not with_email:
            c = next(x for x in clients if any(ct["email"] for ct in x["contacts"]))
            with_email = [ct for ct in c["contacts"] if ct["email"]]
        ct = r.choice(with_email)
        while True:
            d = start + timedelta(days=r.randint(0, (end - start).days))
            if d.weekday() < 5 or r.random() < 0.15:
                break
        created = d.replace(hour=r.randint(7, 18), minute=r.randint(0, 59))
        p = r.choices(list(PRIORITY_WEIGHTS), weights=list(PRIORITY_WEIGHTS.values()))[0]
        sla_min = SLA_HOURS[p] * 60
        agent = c["agent"] if c["agent"] and r.random() < 0.7 else r.choice(AGENTS)
        tickets.append({"num": ticket_nums[i], "client": c, "contact": ct, "created": created, "p": p, "subject": r.choice(SUBJECTS),
                        "agent": agent, "sla_min": sla_min})
    tickets.sort(key=lambda t: t["created"])
    late_cut = datetime(2026, 8, 20)
    for t in tickets:
        if t["created"] < late_cut:
            t["state"] = r.choices(["Closed", "Resolved", "open_responded"], weights=[70, 25, 5])[0]
        else:
            t["state"] = r.choices(["Closed", "Resolved", "open_responded", "open_unresponded"], weights=[20, 15, 35, 30])[0]
        if t["state"] == "open_unresponded":
            t["fr"] = None
            t["status"] = "New"
            due = t["created"] + timedelta(minutes=t["sla_min"])
            if due >= datetime(2026, 9, 1):
                t["created"] = datetime(2026, 8, 31, 0, 0) - timedelta(minutes=t["sla_min"] + r.randint(30, 600))
            if r.random() < 0.2:
                t["agent"] = ""
        else:
            if r.random() < 0.8:
                delay = r.randint(3, int(t["sla_min"] * 0.95))
            else:
                delay = r.randint(int(t["sla_min"] * 1.1) + 1, int(t["sla_min"] * 3))
            latest = datetime(2026, 8, 31, 21, 0)
            if t["created"] + timedelta(minutes=delay) > latest:
                delay = max(3, min(delay, int((latest - t["created"]).total_seconds() // 60)))
            t["fr"] = t["created"] + timedelta(minutes=delay)
            if t["state"] == "open_responded":
                t["status"] = r.choice(["Open", "In Progress", "In Progress", "Waiting on client"])
            else:
                t["status"] = t["state"]
                t["resolved"] = min(t["fr"] + timedelta(minutes=r.randint(20, 60 * 72)), datetime(2026, 8, 31, 22, 0))
                if t["resolved"] <= t["fr"]:
                    t["resolved"] = t["fr"] + timedelta(minutes=10)
                t["note"] = r.choice(NOTES)
    tickets.sort(key=lambda t: t["created"])

    # the unique latest ticket (sort target): open, responded, created 2026-08-31 11:52, written 12-hour style
    top = r.choice([t for t in tickets if t["status"] in ("Open", "In Progress") and t["created"] >= datetime(2026, 8, 25)])
    later = [t for t in tickets if t["created"] >= datetime(2026, 8, 31, 11, 52) and t is not top]
    for t in later:
        t["created"] = t["created"].replace(hour=9, minute=r.randint(0, 59))
        if t.get("fr") and t["fr"] <= t["created"]:
            t["fr"] = t["created"] + timedelta(minutes=5)
    top["created"] = datetime(2026, 8, 31, 11, 52)
    top["fr"] = top["created"] + timedelta(minutes=18)
    tickets.sort(key=lambda t: t["created"])
    assert sum(1 for t in tickets if t["created"] == top["created"]) == 1

    # impossible: a July closed ticket resolved before it was created
    bad = r.choice([t for t in tickets if t["status"] == "Closed" and t["created"].month == 7 and t["created"].day > 3])
    bad["resolved_written"] = bad["created"] - timedelta(hours=r.randint(5, 40))

    # blank Client on a few tickets (their contact's email identifies the company)
    blank_client = r.sample([t for t in tickets if t is not bad and t is not top], N_BLANK_CLIENT)
    for t in blank_client:
        t["blank_client"] = True

    # ------------------------------------------------------------------ client portal test client: one with 6..12 tickets incl. a blank-client ticket
    def tickets_of(c):
        return [t for t in tickets if t["client"] is c]

    portal_cands = sorted([c for c in clients if 6 <= len(tickets_of(c)) <= 14 and any(t.get("blank_client") for t in tickets_of(c))
                           and any(ct["email"] for ct in c["contacts"])], key=lambda c: c["acct"])
    if not portal_cands:
        c = sorted([c for c in clients if 6 <= len(tickets_of(c)) <= 14], key=lambda c: c["acct"])[0]
        t = r.choice(tickets_of(c))
        t["blank_client"] = True
        portal_cands = [c]
    portal = r.choice(portal_cands)
    # the portal client has one ticket waiting on the client (change request 3)
    if not any(t["status"] == "Waiting on client" for t in tickets_of(portal)):
        w = max([t for t in tickets_of(portal) if t is not bad and t is not top and not t.get("blank_client")], key=lambda t: t["created"])
        if not w.get("fr"):
            w["fr"] = w["created"] + timedelta(minutes=min(w["sla_min"] // 2, 120))
        w.update(status="Waiting on client", state="open_responded")
        w.pop("resolved", None)
        w.pop("note", None)

    # guarantees for other seeds, applied without drawing from the generator (seed 0 needs none of them)
    def open_responded(t):
        return t["status"] in ("Open", "In Progress") and t.get("fr") is not None and t is not top

    if not any(open_responded(t) and t["agent"] == RESTRICTED for t in tickets):
        sorted([t for t in tickets if open_responded(t) and not t.get("blank_client")], key=lambda t: t["num"])[0]["agent"] = RESTRICTED
    if not any(open_responded(t) and (t["fr"] - t["created"]).total_seconds() > t["sla_min"] * 60 for t in tickets):
        late = sorted([t for t in tickets if open_responded(t) and t["agent"] != RESTRICTED], key=lambda t: t["num"])[0]
        late["fr"] = late["created"] + timedelta(minutes=late["sla_min"] + 45)
    if not any(t["client"] is portal and t["status"] in ("Resolved", "Closed") and t is not bad for t in tickets):
        rp = sorted([t for t in tickets_of(portal) if t.get("fr") and t["status"] not in OPEN_STATUSES + ["Waiting on client"]] or
                    [t for t in tickets_of(portal) if t.get("fr") and t["status"] != "Waiting on client"], key=lambda t: t["num"])[0]
        rp.update(status="Resolved", resolved=rp["fr"] + timedelta(hours=2), note=NOTES[0])

    # ------------------------------------------------------------------ write clients.csv
    for c in clients:
        c["fee_str"] = r.choice([f"${c['fee'] / 100:,.2f}", f"{c['fee'] // 100}", f"{c['fee'] / 100:,.2f}"])
    client_rows = [{"c": c, "kind": "unique", "cols": [f"A-{c['acct']}", c["name"], c["domain"], c["tier"], c["agent"], c["start"].isoformat(), c["fee_str"]]}
                   for c in clients]
    dsrc = r.sample([c for c in clients if c is not portal], N_CLIENT_EXACT + N_CLIENT_DOMAIN)
    for c in dsrc[:N_CLIENT_EXACT]:
        client_rows.append({"c": c, "kind": "exact_duplicate", "cols": list(client_rows[clients.index(c)]["cols"])})
    for c in dsrc[N_CLIENT_EXACT:]:
        client_rows.append({"c": c, "kind": "same_domain", "cols": ["", c["name"] + " LLC", r.choice([f"www.{c['domain']}", c["domain"].upper()]), c["tier"],
                                                                   c["agent"], c["start"].strftime("%m/%d/%Y"), c["fee_str"]]})
    r.shuffle(client_rows)
    for i, row in enumerate(client_rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "clients.csv"), ["Account #", "Client", "Domain", "Tier", "Account Agent", "Contract Start", "Monthly Fee"],
              [row["cols"] for row in client_rows])

    # ------------------------------------------------------------------ write contacts.csv
    def ccols(ct, email=None, client_name=None):
        return [ct["first"], ct["last"], ct["email"] if email is None else email, phone_variant(ct["phone"], r.randrange(7)),
                client_name or ct["client"]["name"], ct["role"], ct["portal"]]

    contact_rows = []
    for ct in contacts:
        cname = ct["client"]["name"].upper() if r.random() < 0.05 else ct["client"]["name"]
        contact_rows.append({"ct": ct, "kind": "unique", "cols": ccols(ct, client_name=cname)})
    csrc = r.sample([ct for ct in contacts if ct["email"]], N_CONTACT_EXACT + N_CONTACT_CASE)
    for ct in csrc[:N_CONTACT_EXACT]:
        contact_rows.append({"ct": ct, "kind": "exact_duplicate", "cols": list(contact_rows[contacts.index(ct)]["cols"])})
    for ct in csrc[N_CONTACT_EXACT:]:
        contact_rows.append({"ct": ct, "kind": "same_email_other_case", "cols": ccols(ct, email=r.choice([ct["email"].upper(), ct["email"].capitalize(), ct["email"].title()]))})
    r.shuffle(contact_rows)
    for i, row in enumerate(contact_rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "contacts.csv"), ["First Name", "Last Name", "Email", "Phone", "Client", "Role", "Portal Access"],
              [row["cols"] for row in contact_rows])

    # ------------------------------------------------------------------ write tickets.csv
    for t in tickets:
        t["ts_style"] = r.randrange(4)
        t["num_style"] = r.choices([0, 1, 2, 3], weights=[70, 10, 12, 8])[0]
        t["prio_str"] = r.choice(PRIORITY_SPELLINGS[t["p"]])
        t["status_str"] = r.choice([t["status"], t["status"], t["status"].lower()])
        t["email_str"] = t["contact"]["email"] if r.random() < 0.85 else t["contact"]["email"].upper()
        t["agent_str"] = t["agent"] if r.random() < 0.9 else t["agent"].lower()
    top["ts_style"] = 1

    def tcols(t, num_style=None):
        resolved = t.get("resolved_written", t.get("resolved"))
        return [tnum(t["num"], t["num_style"] if num_style is None else num_style), ts(t["created"], t["ts_style"]),
                "" if t.get("blank_client") else t["client"]["name"], t["email_str"], t["subject"], t["prio_str"], t["status_str"], t["agent_str"],
                ts(t["fr"], t["ts_style"]) if t.get("fr") else "", ts(resolved, t["ts_style"]) if resolved else "", t.get("note", "")]

    ticket_rows = [{"t": t, "kind": "unique", "cols": tcols(t)} for t in tickets]
    tsrc = r.sample([t for t in tickets if t is not top and t is not bad and t["client"] is not portal], N_TICKET_EXACT + N_TICKET_NUMBER)
    for t in tsrc[:N_TICKET_EXACT]:
        ticket_rows.insert(r.randint(0, len(ticket_rows)), {"t": t, "kind": "exact_duplicate", "cols": tcols(t)})
    for t in tsrc[N_TICKET_EXACT:]:
        t["num_style"] = 0
        for row in ticket_rows:
            if row["t"] is t:
                row["cols"][0] = tnum(t["num"], 0)
        ticket_rows.insert(r.randint(0, len(ticket_rows)), {"t": t, "kind": "same_number_written_differently", "cols": tcols(t, num_style=r.choice([1, 2, 3]))})
    for i, row in enumerate(ticket_rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "tickets.csv"),
              ["Ticket #", "Created", "Client", "Contact Email", "Subject", "Priority", "Status", "Assigned To", "First Response", "Resolved", "Resolution Note"],
              [row["cols"] for row in ticket_rows])

    # ------------------------------------------------------------------ figures
    def is_open(t):
        return t["status"] in OPEN_STATUSES

    def within(t):
        return t.get("fr") is not None and (t["fr"] - t["created"]).total_seconds() <= t["sla_min"] * 60

    open_t = [t for t in tickets if is_open(t)]
    escalated = [t for t in open_t if t.get("fr") is None]
    aug = [t for t in tickets if t["created"].month == 8]
    aug_met = [t for t in aug if within(t)]
    aug_resp = [t for t in aug if t.get("fr")]
    avg_fr = sum((t["fr"] - t["created"]).total_seconds() / 60 for t in aug_resp) / len(aug_resp)
    resolved_aug = [t for t in tickets if t.get("resolved") and t["resolved"].month == 8 and t is not bad]
    sam = [t for t in tickets if t["agent"] == RESTRICTED]
    vpn = [t for t in tickets if "VPN" in t["subject"]]
    prio_counts = {f"P{p}": sum(1 for t in tickets if t["p"] == p) for p in SLA_HOURS}

    def tl(t):
        return {"ticket": tnum(t["num"], 0), "client": t["client"]["name"], "contact_email": t["contact"]["email"], "subject": t["subject"],
                "priority": f"P{t['p']}", "file_priority": t["prio_str"], "status": t["status"], "file_status": t["status_str"], "agent": t["agent"],
                "created": t["created"].strftime("%Y-%m-%d %H:%M"), "file_created": ts(t["created"], t["ts_style"]),
                "first_response": t["fr"].strftime("%Y-%m-%d %H:%M") if t.get("fr") else None,
                "response_minutes": int((t["fr"] - t["created"]).total_seconds() // 60) if t.get("fr") else None,
                "sla_hours": SLA_HOURS[t["p"]], "within_sla": within(t), "blank_client_in_file": bool(t.get("blank_client")),
                "file_numbers": sorted({row["cols"][0] for row in ticket_rows if row["t"] is t}), "file_lines": sorted(row["line"] for row in ticket_rows if row["t"] is t)}

    missed_example = r.choice(sorted([t for t in aug if t.get("fr") and not within(t) and t["p"] == 2 and not t.get("blank_client")]
                                     or [t for t in aug if t.get("fr") and not within(t) and not t.get("blank_client")], key=lambda t: t["num"]))
    met_example = r.choice(sorted([t for t in aug if within(t) and t["p"] == 4 and (t["fr"] - t["created"]).total_seconds() > 16 * 3600], key=lambda t: t["num"])
                           or sorted([t for t in aug if within(t) and t["p"] == 4], key=lambda t: t["num"]))
    esc_include = r.choice(sorted([t for t in escalated if t["agent"]], key=lambda t: t["num"]))
    esc_exclude_late = r.choice(sorted([t for t in open_t if t.get("fr") and not within(t)], key=lambda t: t["num"]))
    other_scope = r.choice(sorted([t for t in tickets if t["agent"] == OTHER and t["client"] is not portal], key=lambda t: t["num"]))
    close_test = r.choice(sorted([t for t in open_t if t["agent"] == RESTRICTED and t.get("fr") and t["status"] != "Waiting on client"], key=lambda t: t["num"]))
    other_client_ticket = r.choice(sorted([t for t in tickets if t["client"] is not portal and not t.get("blank_client")], key=lambda t: t["num"]))
    portal_tickets = tickets_of(portal)
    portal_contact = next(ct for ct in portal["contacts"] if ct["email"])

    def client_row(c):
        return {"client": c["name"], "account": f"A-{c['acct']}", "domain": c["domain"], "agent": c["agent"],
                "file_lines": sorted(row["line"] for row in client_rows if row["c"] is c),
                "file_rows": [row["cols"] for row in client_rows if row["c"] is c]}

    def per_client_aug(c):
        ts_ = [t for t in aug if t["client"] is c]
        resp = [t for t in ts_ if t.get("fr")]
        met = [t for t in ts_ if within(t)]
        return {"client": c["name"], "tickets": len(ts_), "within_sla": len(met), "pct": round(len(met) / len(ts_) * 100, 1) if ts_ else None,
                "avg_first_response_minutes": round(sum((t["fr"] - t["created"]).total_seconds() / 60 for t in resp) / len(resp), 1) if resp else None}

    report_clients = sorted([c for c in clients if c is not portal and len([t for t in aug if t["client"] is c]) >= 5],
                            key=lambda c: (-len([t for t in aug if t["client"] is c]), c["acct"]))[:2]
    unassigned_client = next(c for c in clients if not c["agent"] and c is not portal)
    sam_client = sorted([c for c in clients if c["agent"] == RESTRICTED], key=lambda c: c["acct"])[0]
    mei_client = sorted([c for c in clients if c["agent"] == "Mei Chen"], key=lambda c: c["acct"])[0]
    waiting = r.choice(sorted([t for t in portal_tickets if t["status"] == "Waiting on client"], key=lambda t: t["num"]))
    resolved_portal = r.choice(sorted([t for t in portal_tickets if t["status"] == "Resolved"], key=lambda t: t["num"])
                               or sorted([t for t in portal_tickets if t["status"] in ("Resolved", "Closed")], key=lambda t: t["num"]))
    client_dup_domain = dsrc[N_CLIENT_EXACT]
    contact_case = csrc[N_CONTACT_EXACT]

    counts = {
        "seed": seed,
        "valid_test_dates": ["2026-09-01", None],
        "date_dependence": "Every imported response deadline is before 2026-09-01, so the escalated count holds for any test date from 2026-09-01; August figures are fixed.",
        "rules": {
            "sla_first_response_hours": {f"P{p}": h for p, h in SLA_HOURS.items()},
            "within_sla": "first response no later than created + the priority's hours (clock hours)",
            "sla_pct_august": "tickets created in August 2026 answered within SLA / all tickets created in August 2026 (unanswered ones count as missed)",
            "escalated": "open ticket (New, Open, In Progress, Waiting on client) with no first response after its deadline",
            "resolved_august": "tickets whose Resolved time is in August 2026 (the impossible ticket excluded)",
            "priority": "the digit in P1 / p1 / 1 - Critical / P1 (Critical)",
        },
        "clients": {"file_rows_excluding_header": len(client_rows), "exact_duplicate_rows": N_CLIENT_EXACT, "same_domain_rows": N_CLIENT_DOMAIN, "wrong_count_only_exact_duplicates_removed": len(client_rows) - N_CLIENT_EXACT,
                    "unique_clients": N_CLIENTS, "dedupe_rule": "same web domain after dropping www. and case",
                    "same_domain_example": client_row(client_dup_domain), "exact_duplicate_example": client_row(dsrc[0]),
                    "without_account_agent": sum(1 for c in clients if not c["agent"])},
        "contacts": {"file_rows_excluding_header": len(contact_rows), "exact_duplicate_rows": N_CONTACT_EXACT, "same_email_other_case_rows": N_CONTACT_CASE,
                     "unique_contacts": N_CONTACTS, "without_email": [{"name": f"{ct['first']} {ct['last']}", "client": ct["client"]["name"]} for ct in no_email],
                     "same_email_example": {"name": f"{contact_case['first']} {contact_case['last']}", "email": contact_case["email"], "client": contact_case["client"]["name"],
                                            "emails_as_written": sorted({row["cols"][2] for row in contact_rows if row["ct"] is contact_case}),
                                            "file_lines": sorted(row["line"] for row in contact_rows if row["ct"] is contact_case)}},
        "tickets": {"file_rows_excluding_header": len(ticket_rows), "exact_duplicate_rows": N_TICKET_EXACT, "same_number_rows": N_TICKET_NUMBER,
                    "unique_tickets": N_TICKETS, "per_priority": prio_counts,
                    "per_status": {s: sum(1 for t in tickets if t["status"] == s) for s in OPEN_STATUSES + ["Resolved", "Closed"]},
                    "same_number_example": tl(tsrc[N_TICKET_EXACT]), "exact_duplicate_example": tl(tsrc[0]),
                    "blank_client_tickets": [tl(t) for t in sorted(blank_client, key=lambda t: t["num"])],
                    "impossible": tl(bad) | {"file_resolved": ts(bad["resolved_written"], bad["ts_style"])},
                    "august_created": len(aug), "august_within_sla": len(aug_met), "august_responded": len(aug_resp),
                    "august_sla_pct": round(len(aug_met) / len(aug) * 100, 1),
                    "wrong_sla_pct_responded_only": round(len(aug_met) / len(aug_resp) * 100, 1),
                    "august_avg_first_response_minutes": round(avg_fr, 1),
                    "missed_example": tl(missed_example), "met_example": tl(met_example),
                    "escalated_count": len(escalated), "escalated_include": tl(esc_include), "not_escalated_responded_late": tl(esc_exclude_late)},
        "baseline": {
            "STAFF_ROLE": "Agent", "VIEWER_ROLE": "Read-only", "MAIN_ENTITY": "ticket", "MAIN_ENTITY_PLURAL": "tickets",
            "SCOPE_RULE": f"tickets assigned to {RESTRICTED}", "SCOPE_COUNT": len(sam), "OUT_OF_SCOPE_EXAMPLE": tl(other_scope),
            "KPI_1": "Open tickets", "KPI_1_VALUE": len(open_t),
            "KPI_2": "Escalated tickets", "KPI_2_VALUE": len(escalated),
            "KPI_3": "First responses within SLA, August 2026", "KPI_3_VALUE": f"{round(len(aug_met) / len(aug) * 100, 1)}% ({len(aug_met)} of {len(aug)})",
            "KPI_4": "Tickets resolved in August 2026", "KPI_4_VALUE": len(resolved_aug),
            "SCOPED_KPI_1_VALUE": sum(1 for t in open_t if t["agent"] == RESTRICTED),
            "SEARCH_TERM": "VPN", "SEARCH_COUNT": len(vpn),
            "FILTER_FIELD": "Priority", "FILTER_VALUE": "P1", "FILTER_COUNT": prio_counts["P1"],
            "SORT_FIELD": "Created", "SORT_TOP": tl(top),
            "EXPORT_ROWS": N_TICKETS, "EXPORT_COLUMNS": ["Ticket #", "Client", "Priority", "Status", "Assigned To", "Created"],
            "REQUIRED_FIELD": "Subject",
        },
        "portal": {"client": portal["name"], "contact": f"{portal_contact['first']} {portal_contact['last']}", "contact_email": portal_contact["email"],
                   "tickets": len(portal_tickets), "blank_client_tickets": sorted(tnum(t["num"], 0) for t in portal_tickets if t.get("blank_client")),
                   "other_client_ticket": tl(other_client_ticket)},
        "close_test": tl(close_test),
        "change_1_report": {"clients": [per_client_aug(c) for c in report_clients], "portal_client": per_client_aug(portal)},
        "change_2_autoassign": {"client_with_agent": {"client": mei_client["name"], "agent": "Mei Chen"},
                                "restricted_agent_client": {"client": sam_client["name"], "agent": RESTRICTED},
                                "client_without_agent": {"client": unassigned_client["name"]}},
        "change_3_portal": {"waiting_ticket": tl(waiting), "resolved_ticket": tl(resolved_portal)},
    }
    write_json(os.path.join(REF_DIR, "counts.json"), counts)
    b = counts["baseline"]
    print(f"clients {len(client_rows)} -> {N_CLIENTS}; contacts {len(contact_rows)} -> {N_CONTACTS}; tickets {len(ticket_rows)} -> {N_TICKETS}; "
          f"open {b['KPI_1_VALUE']}, escalated {b['KPI_2_VALUE']}, SLA {b['KPI_3_VALUE']}, resolved Aug {b['KPI_4_VALUE']}; Sam {b['SCOPE_COUNT']}; portal {portal['name']} {len(portal_tickets)}")


if __name__ == "__main__":
    main()
