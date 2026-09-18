#!/usr/bin/env python3
"""zendesk-users-import: an IT support firm's client contact export turned into a Zendesk user import CSV.

    python gen.py [--seed N]

Business: Blue Heron Consulting is a managed IT provider for small offices. Its helpdesk moves to Zendesk, where
the client companies already exist as organizations. Every client contact becomes an end user in the right
organization, with the plan tag and ticket visibility the support lead describes.

Traps (each caught by a check, see task.yaml):
  * CRM account names are loose ("ACME INDUSTRIAL", "Brightwater Dental - Westside", "Tamarack Brewing Co.") and must
    become the Zendesk organization name exactly; one client is not in Zendesk yet and stays blank
                                                                              (check: organization and external id)
  * three people are contacts on two accounts; Zendesk takes one organization per user, and the CRM note on one of
    the two rows says which; external_id comes from the row that is kept      (checks: one row per person; organization and external id)
  * "Portal Admin" in the CRM is our client portal, not Zendesk: every contact is an end-user, and only primary
    contacts get organization-wide ticket visibility                         (check: role and restriction)
  * plan tags come from the account's support plan; "Pro (legacy)" is Managed Pro and tags are lowercase with
    underscores                                                               (check: plan tag)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["name", "email", "external_id", "role", "restriction", "organization", "tags", "phone", "notes"]
PLANS = {"Managed Pro": "plan_managed_pro", "Managed Essentials": "plan_managed_essentials", "Break/Fix": "plan_break_fix",
         "Pro (legacy)": "plan_managed_pro"}
TITLES = ["Office Manager", "Owner", "Bookkeeper", "Front Desk", "Practice Manager", "Operations Lead", "Associate", "Technician",
          "Controller", "Receptionist", "Project Manager"]
CLIENTS = ["Acme Industrial", "Brightwater Dental", "Tamarack Brewing", "Juniper Street Cafe", "Lakeside Veterinary", "Meridian Title",
           "Dorsey Freight", "Copperfield Law", "Orchard Hill Dental", "Riverbend Physio", "Fernbrook Montessori", "Hollowell Electric",
           "Wren & Sparrow Bookshop", "Everline Insurance"]
NEW_CLIENT = ("Kingfisher Charters", "kingfishercharters.com")


def build(seed: int) -> dict:
    r = rng(seed)
    dom = {n: d for n, d, _ in COMPANIES}
    orgs = []
    for k, name in enumerate(CLIENTS):
        plan = r.choice(["Managed Pro", "Managed Pro", "Managed Essentials", "Break/Fix"])
        orgs.append({"name": name, "domain": dom[name], "zd_id": 360001200000 + 4711 * (k + 1), "plan": plan, "crm_id": f"AC-{1100 + 7 * k}"})
    for o in r.sample([o for o in orgs if o["plan"] == "Managed Pro"], 2):
        o["plan_text"] = "Pro (legacy)"
    for o in orgs:
        o.setdefault("plan_text", o["plan"])
        n = o["name"]
        o["crm_name"] = r.choice([n, n.upper(), f"{n} Inc.", f"{n} LLC", n])
    for o in orgs:
        if o["name"] == "Tamarack Brewing":
            o["crm_name"] = "Tamarack Brewing Co."
        if o["name"] == "Brightwater Dental":
            o["sites"] = ["Brightwater Dental - Westside", "Brightwater Dental - Downtown"]
    new_org = {"name": "", "domain": NEW_CLIENT[1], "plan": "Managed Essentials", "plan_text": "Managed Essentials",
               "crm_name": NEW_CLIENT[0], "crm_id": "AC-1199", "new": True}
    contacts = []
    used = set()
    names = set()
    for o in orgs + [new_org]:
        for k in range(r.choice([2, 3, 3, 4])):
            while True:
                f, l = person(r)
                em = email_for(r, f, l, o["domain"]) if r.random() < 0.8 else email_for(r, f, l)
                if em not in used and (f, l) not in names:
                    used.add(em); names.add((f, l)); break
            c = {"first": f, "last": l, "email": em, "org": o, "title": r.choice(TITLES), "primary": k == 0, "tags": set(),
                 "portal_admin": False, "phone": phone_variant(phone_digits(r), r.randrange(7)), "note": ""}
            c["crm_account"] = r.choice(o["sites"]) if o.get("sites") else o["crm_name"]
            if c["crm_account"] != o["name"] or not em.endswith(o["domain"]):
                c["tags"].add("org")
            if o.get("new"):
                c["tags"].add("org")
            if o["plan_text"] != o["plan"]:
                c["tags"].add("plan")
            contacts.append(c)
    for c in r.sample([c for c in contacts if not c["primary"]], 5) + r.sample([c for c in contacts if c["primary"]], 3):
        c["portal_admin"] = True; c["tags"].add("role")
    for c in contacts:
        if c["primary"]:
            c["tags"].add("role")
    # three people on two accounts
    rows = []
    for c in contacts:
        rows.append({"contact": c, "account": c["crm_account"], "org": c["org"], "primary": c["primary"], "portal_admin": c["portal_admin"],
                     "note": "", "id": None})
    dup_specs = []
    zd_orgs = orgs[:]
    pairs = r.sample(zd_orgs, 6)
    kinds = [("bookkeeper", "Outside bookkeeper for both accounts. File tickets under {keep}, that account pays the retainer."),
             ("moved", "Moved from {other} to {keep} in July 2026."),
             ("contractor", "Part-time IT contact at both. Primary org: {keep}.")]
    for i, (kind, text) in enumerate(kinds):
        a, b = pairs[2 * i], pairs[2 * i + 1]
        while True:
            f, l = person(r)
            em = email_for(r, f, l, "haddadbooks.com" if kind == "bookkeeper" else None)
            if em not in used and (f, l) not in names:
                used.add(em); names.add((f, l)); break
        keep, other = (b, a)
        c = {"first": f, "last": l, "email": em, "org": keep, "title": "Bookkeeper" if kind == "bookkeeper" else "IT Contact", "primary": False,
             "tags": {"dup", "org"}, "portal_admin": False, "phone": phone_variant(phone_digits(r), r.randrange(7)), "note": ""}
        if keep["plan_text"] != keep["plan"] or other["plan"] != keep["plan"]:
            c["tags"].add("plan")
        contacts.append(c)
        note = text.format(keep=keep["name"], other=other["name"])
        note_on_kept = i != 1   # the "moved" note sits on the old account's row
        rows.append({"contact": c, "account": other["crm_name"], "org": other, "primary": False, "portal_admin": False,
                     "note": "" if note_on_kept else note, "id": None, "kept": False})
        rows.append({"contact": c, "account": keep["crm_name"], "org": keep, "primary": False, "portal_admin": False,
                     "note": note if note_on_kept else "", "id": None, "kept": True})
        dup_specs.append(c)
    r.shuffle(rows)
    for k, row in enumerate(rows):
        row["id"] = f"CT-{40100 + 3 * k}"
    for row in rows:
        c = row["contact"]
        if row.get("kept", True):
            c["external_id"] = row["id"]
    return {"orgs": orgs, "contacts": contacts, "rows": rows, "new_org": new_org}


def emit(seed: int) -> None:
    d = build(seed)
    orgs, contacts, rows = d["orgs"], d["contacts"], d["rows"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 31)
    xrows = []
    for row in rows:
        c, o = row["contact"], row["org"]
        email = c["email"] if r.random() < 0.75 else c["email"].upper() if r.random() < 0.5 else c["email"].capitalize()
        xrows.append([row["id"], row["account"], o["crm_id"], c["first"], c["last"], email, c["phone"], c["title"],
                      "Y" if row["primary"] else "N", "Y" if row["portal_admin"] else "N", o["plan_text"], row["note"]])
    xrows.sort(key=lambda x: (x[1].lower(), x[4]))
    write_xlsx(os.path.join(ws, "client_contacts_export.xlsx"), {"Contacts": {
        "header": ["Contact ID", "Client Account", "Account ID", "First Name", "Last Name", "Email", "Phone", "Title", "Primary Contact",
                   "Portal Admin", "Support Plan", "Notes"],
        "rows": xrows, "widths": {"B": 32, "F": 36, "H": 18, "K": 20, "L": 60}, "freeze": "A2"}}, creator="HaloDesk PSA")
    write_csv(os.path.join(ws, "zendesk_organizations_export.csv"),
              ["id", "name", "external_id", "domain_names", "tags", "created_at"],
              [[str(o["zd_id"]), o["name"], "", o["domain"], "", f"2026-08-{10 + k % 18:02d}T15:{k * 7 % 60:02d}:00Z"]
               for k, o in enumerate(sorted(orgs, key=lambda o: o["zd_id"]))])
    write_csv(os.path.join(ws, "zendesk_user_import_template.csv"), TEMPLATE, [])
    write_text(os.path.join(ws, "zendesk_import_rules.txt"), (
        "Zendesk user import - rules (Amara, support lead)\n"
        "\n"
        "Template: zendesk_user_import_template.csv, same columns, same order. One row per person. Zendesk matches users on\n"
        "email, so a person listed twice in the CRM is still one user.\n"
        "\n"
        "name          First Last\n"
        "email         their email\n"
        "external_id   the CRM Contact ID. For someone listed on two accounts, the Contact ID from the account you file\n"
        "              them under.\n"
        "role          end-user for every client contact. The CRM's Portal Admin flag is about our client portal and has\n"
        "              nothing to do with Zendesk; agents and admins are our own staff and are not in this file.\n"
        "restriction   organization for each account's primary contact (they see every ticket from their company);\n"
        "              requested for everyone else (they see only their own tickets).\n"
        "organization  the organization name exactly as it is in Zendesk (see zendesk_organizations_export.csv). The CRM\n"
        "              spells accounts its own way and splits Brightwater Dental into two sites; Zendesk has one\n"
        "              organization per client company. Kingfisher Charters signed last week and is not set up in Zendesk\n"
        "              yet: import their people with organization blank and I will attach them later.\n"
        "              Our Zendesk plan allows one organization per user. The three people who are contacts on two accounts\n"
        "              have a note in the CRM on one of their rows saying where they belong.\n"
        "tags          one tag for the support plan of the organization they are filed under: plan_managed_pro,\n"
        "              plan_managed_essentials or plan_break_fix. Accounts still showing the old \"Pro (legacy)\" plan are on\n"
        "              Managed Pro.\n"
        "phone         as in the CRM\n"
        "notes         leave blank\n"))
    out = sorted(contacts, key=lambda c: c["email"])
    rrows = [[f"{c['first']} {c['last']}", c["email"], c["external_id"], "end-user", "organization" if c["primary"] else "requested",
              c["org"]["name"], PLANS[c["org"]["plan_text"]], c["phone"], ""] for c in out]
    write_csv(os.path.join(ref, "zendesk_users.csv"), TEMPLATE, rrows)
    write_csv(os.path.join(sol, "zendesk_users.csv"), TEMPLATE, rrows)

    def keys(tag):
        return sorted(c["email"] for c in out if tag in c["tags"])
    write_json(os.path.join(ref, "notes.json"), {t: keys(t) for t in ("org", "dup", "role", "plan")})
    write_task_yaml(HERE, {
        "id": "zendesk-users-import", "track": "desk", "category": "reformatting",
        "title": "Import client contacts as Zendesk users",
        "ask": ("Our helpdesk is moving to Zendesk and the client companies are already set up there. Please turn the CRM contact "
                "export into the user import file; Amara's rules, the organizations export and the template are in the folder. "
                "Save it as zendesk_users.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "CRM account names are loose (ALL CAPS, Inc., LLC, Tamarack Brewing Co.) and Brightwater Dental is split into two site accounts; organization must be the Zendesk name exactly, and the new Kingfisher Charters account is not in Zendesk so its people get a blank organization (check: organization and external id)",
            "three people are contacts on two accounts under the same email; the note that decides their organization sits on the kept row for two of them and on the other row for the person who moved, and external_id must come from the kept row (checks: one row per person; organization and external id)",
            "eight contacts are Portal Admins in the CRM, which is not a Zendesk role: everyone is end-user, and restriction is organization only for each account's primary contact (check: role and restriction)",
            "the plan tag follows the organization the person is filed under, and accounts still marked Pro (legacy) take plan_managed_pro; plan names are not tags until lowercased with underscores (check: plan tag)",
            "emails arrive in mixed case and the two-account people appear twice, so a plain row copy imports duplicate users (checks: one row per person; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Zendesk template columns, exact order", "path": "zendesk_users.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one row per person", "path": "zendesk_users.csv", "column": "email", "ref": "zendesk_users.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "zendesk_users.csv", "equals_ref": "zendesk_users.csv"},
            {"type": "csv_values_match", "name": "organization and external id", "path": "zendesk_users.csv", "ref": "zendesk_users.csv",
             "key": "email", "columns": ["organization", "external_id"], "min_accuracy": 1.0, "must_match_keys": keys("org")},
            {"type": "csv_values_match", "name": "role and restriction", "path": "zendesk_users.csv", "ref": "zendesk_users.csv",
             "key": "email", "columns": ["role", "restriction"], "min_accuracy": 1.0, "must_match_keys": keys("role")},
            {"type": "csv_values_match", "name": "plan tag", "path": "zendesk_users.csv", "ref": "zendesk_users.csv",
             "key": "email", "columns": ["tags"], "min_accuracy": 1.0, "must_match_keys": keys("plan")},
        ],
    })
    print(f"seed={seed}: {len(rows)} CRM rows, {len(contacts)} users; " + ", ".join(f"{t}={len(keys(t))}" for t in ("org", "dup", "role", "plan")))


if __name__ == "__main__":
    emit(argparse_seed())
