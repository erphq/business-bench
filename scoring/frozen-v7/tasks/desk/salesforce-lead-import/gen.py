#!/usr/bin/env python3
"""salesforce-lead-import: a freight broker's marketing leads sheet turned into a Salesforce lead import file.

    python gen.py [--seed N]

Business: Silverline Logistics collects leads from its website, ads, trade shows and referrals in one
spreadsheet. Sales is moving to Salesforce, whose admin has locked Lead Source, Lead Status and the
State/Country picklists, and who assigns leads by Salesforce username.

Traps (each caught by a check, see task.yaml):
  * the Source column is free text in two dozen spellings; each must land on the org's Lead Source picklist
    value by the admin's definitions                                           (check: lead source picklist)
  * the sheet's Status words map onto Salesforce's four Lead Status values      (check: lead status picklist)
  * countries are written USA / U.S. / Canada / UK / Deutschland / Mexico or left blank beside a state;
    the picklists need ISO codes (UK is GB) and state codes for US and Canada   (check: country and state codes)
  * Rep is a first name or initials; Lead Owner is the Salesforce username, which differs from the email for
    two users; a rep who left and blank reps go to the sales manager            (check: lead owner username)
  * Company is required; leads without one take the [not provided] placeholder (check: company placeholder)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["First Name", "Last Name", "Company", "Title", "Email", "Phone", "Lead Source", "Lead Status", "City",
            "State/Province Code", "Country Code", "Lead Owner"]
DOMAIN = "silverlinelogistics.com"
# canonical picklist value -> free-text spellings seen in the sheet
SOURCES = {
    "Web": ["Website", "web form", "Quote request form", "website chat", "web"],
    "Advertisement": ["LinkedIn ad", "Google Ads", "PPC", "linkedin sponsored post"],
    "Trade Show": ["Tradeshow", "Trade show - MODEX", "booth scan", "Business card (FreightWorld expo)"],
    "Partner Referral": ["Partner", "Referral - partner (Dorsey Freight)", "carrier referral"],
    "Employee Referral": ["employee referral", "Staff referral - Tomasz"],
    "Phone Inquiry": ["Inbound call", "Called in", "phone"],
    "Purchased List": ["ZoomInfo list", "purchased list"],
}
STATUSES = {"Open - Not Contacted": ["New", "new", ""], "Working - Contacted": ["Contacted", "Working", "Left VM"],
            "Closed - Not Converted": ["Dead", "Not interested", "Unqualified"]}
US_STATES = {"TX": "Texas", "IL": "Illinois", "GA": "Georgia", "OH": "Ohio", "TN": "Tennessee", "CA": "California", "WA": "Washington",
             "NJ": "New Jersey", "AZ": "Arizona", "NC": "North Carolina"}
US_CITIES = {"TX": ["Dallas", "Houston", "Laredo"], "IL": ["Chicago", "Joliet"], "GA": ["Atlanta", "Savannah"], "OH": ["Columbus", "Cincinnati"],
             "TN": ["Memphis", "Nashville"], "CA": ["Ontario", "Long Beach", "Fresno"], "WA": ["Tacoma", "Kent"], "NJ": ["Newark", "Edison"],
             "AZ": ["Phoenix", "Tucson"], "NC": ["Charlotte", "Greensboro"]}
CA_PROV = {"ON": ("Ontario", ["Toronto", "Mississauga", "Hamilton"]), "BC": ("British Columbia", ["Vancouver", "Delta"]),
           "QC": ("Quebec", ["Montreal", "Laval"]), "AB": ("Alberta", ["Calgary", "Edmonton"])}
MX_CITIES = ["Monterrey", "Guadalajara", "Querétaro", "Ciudad Juárez"]
GB_CITIES = ["Birmingham", "Felixstowe", "Manchester"]
DE_CITIES = ["Hamburg", "Duisburg", "Frankfurt am Main"]
COUNTRY_TEXT = {"US": ["USA", "United States", "U.S.", "US", "United States of America"], "CA": ["Canada", "CAN"],
                "MX": ["Mexico", "México"], "GB": ["UK", "United Kingdom", "England"], "DE": ["Germany", "Deutschland"]}
TITLES = ["Logistics Manager", "Director of Supply Chain", "Shipping Coordinator", "VP Operations", "Owner", "Purchasing Manager",
          "Warehouse Manager", "Transportation Analyst", "Office Manager", "COO"]
# (first, last, alias, username local part differs from email?)
USERS = [("Dana", "Okafor", "dokaf", False, True), ("Marcus", "Kim", "mkim", True, True), ("Tomasz", "Lindqvist", "tlind", False, True),
         ("Sofia", "Reyes", "sreye", True, True), ("Luis", "Ramos", "lramo", False, False), ("Priya", "Natarajan", "pnata", False, True)]


def build(seed: int) -> dict:
    r = rng(seed)
    users = []
    for f, l, alias, differs, active in USERS:
        email = f"{f.lower()}.{l.lower()}@{DOMAIN}"
        username = f"{f[0].lower()}{l.lower()}@{DOMAIN}.sales" if differs else email
        users.append({"first": f, "last": l, "alias": alias, "email": email, "username": username, "active": active})
    manager = users[5]
    rep_labels = {  # how the sheet refers to each user
        "Dana": ["Dana", "D. Okafor", "DO"], "Marcus": ["Marcus", "MK", "Marcus K"], "Tomasz": ["Tomasz", "Tom L", "TL"],
        "Sofia": ["Sofia", "S. Reyes", "SR"], "Luis": ["Luis", "LR"], "Priya": ["Priya"]}
    n = 48
    ppl = people(r, n)
    prospects = [c for c in COMPANIES if c[1] != DOMAIN]
    leads = []
    countries = ["US"] * 31 + ["CA"] * 7 + ["MX"] * 4 + ["GB"] * 3 + ["DE"] * 3
    r.shuffle(countries)
    src_plan = []
    for canon, spellings in SOURCES.items():
        for s in spellings:
            src_plan.append((canon, s))
    while len(src_plan) < n:
        canon = r.choice(["Web", "Web", "Trade Show", "Advertisement"])
        src_plan.append((canon, r.choice(SOURCES[canon])))
    r.shuffle(src_plan)
    used_emails = set()
    for k in range(n):
        f, l = ppl[k]
        comp = r.choice(prospects)
        no_company = False
        c = {"first": f, "last": l, "title": r.choice(TITLES), "tags": set(), "country": countries[k]}
        c["source"], c["source_text"] = src_plan[k]
        if c["source_text"] != c["source"]:
            c["tags"].add("source")
        c["company"], dom = comp[0], comp[1]
        email = email_for(r, f, l, dom)
        while email in used_emails:
            email = email_for(r, f, l, dom)
        used_emails.add(email)
        c["email"] = email
        c["phone"] = phone_variant(phone_digits(r), r.randrange(7))
        leads.append(c)
    # leads with no company: personal email domains
    for c in r.sample(leads, 5):
        c["company"] = ""
        email = email_for(r, c["first"], c["last"])
        while email in used_emails:
            email = email_for(r, c["first"], c["last"])
        used_emails.add(email)
        c["email"] = email
        c["tags"].add("no_company")
    # geography
    for c in leads:
        cc = c["country"]
        if cc == "US":
            st = r.choice(list(US_STATES))
            c.update(city=r.choice(US_CITIES[st]), state=st)
            c["state_text"] = US_STATES[st] if r.random() < 0.2 else st
            c["country_text"] = "" if r.random() < 0.25 else r.choice(COUNTRY_TEXT["US"])
        elif cc == "CA":
            pv = r.choice(list(CA_PROV))
            c.update(city=r.choice(CA_PROV[pv][1]), state=pv)
            c["state_text"] = CA_PROV[pv][0] if r.random() < 0.5 else pv
            c["country_text"] = r.choice(COUNTRY_TEXT["CA"])
        else:
            city = r.choice({"MX": MX_CITIES, "GB": GB_CITIES, "DE": DE_CITIES}[cc])
            c.update(city=city, state="", state_text="", country_text=r.choice(COUNTRY_TEXT[cc]))
            c["phone"] = {"MX": f"+52 81 5550 {r.randint(1000, 9999)}", "GB": f"+44 121 496 0{r.randint(100, 999)}",
                          "DE": f"+49 40 5550{r.randint(1000, 9999)}"}[cc]
        if c["country_text"] not in ("US", "CA") or c["state_text"] != c["state"]:
            c["tags"].add("geo")
    # make sure the Ontario-city-in-California and a blank US country both exist
    us = [c for c in leads if c["country"] == "US"]
    us[0].update(city="Ontario", state="CA", state_text="CA", country_text=""); us[0]["tags"].add("geo")
    # status
    for c in leads:
        canon = r.choice(["Open - Not Contacted", "Open - Not Contacted", "Working - Contacted", "Closed - Not Converted"])
        c["status"] = canon; c["status_text"] = r.choice(STATUSES[canon])
        if c["status_text"] != canon:
            c["tags"].add("status")
    # owners
    active = [u for u in users if u["active"] and u is not manager]
    for c in leads:
        u = r.choice(active)
        c["owner"] = u; c["rep_text"] = r.choice(rep_labels[u["first"]])
        if u["username"] != u["email"]:
            c["tags"].add("owner")
    for c in r.sample([c for c in leads if "owner" not in c["tags"]], 4):
        c["owner"] = manager; c["rep_text"] = r.choice(rep_labels["Luis"]); c["tags"].add("owner")
    for c in r.sample([c for c in leads if "owner" not in c["tags"]], 2):
        c["owner"] = manager; c["rep_text"] = ""; c["tags"].add("owner")
    d0 = date(2026, 7, 1)
    for c in leads:
        c["date_in"] = day_in(r, d0, date(2026, 9, 5))
    leads.sort(key=lambda c: c["date_in"])
    return {"users": users, "leads": leads, "manager": manager}


def emit(seed: int) -> None:
    d = build(seed)
    leads, users, manager = d["leads"], d["users"], d["manager"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 11)
    rows = []
    for c in leads:
        rows.append([c["date_in"], name_noise(r, c["first"]).strip(), c["last"], c["company"], c["title"],
                     c["email"] if r.random() < 0.8 else c["email"].upper(), c["phone"], c["source_text"], c["city"], c["state_text"],
                     c["country_text"], c["rep_text"], c["status_text"],
                     r.choice(["", "", "", "wants LTL quote", "asked about cross-border", "follow up after Labor Day", "sent rate sheet"])])
    write_xlsx(os.path.join(ws, "leads_master_Q3.xlsx"), {"Leads": {
        "header": ["Date In", "First Name", "Last Name", "Company", "Title", "Email", "Phone", "Source", "City", "State", "Country", "Rep",
                   "Status", "Notes"],
        "rows": rows, "widths": {"D": 26, "E": 24, "F": 34, "H": 30, "N": 30}, "freeze": "A2"},
        "Picklist ideas (old)": {"header": ["Source ideas from 2024 planning"],
                                 "rows": [["Web"], ["Social"], ["Events"], ["Referral"], ["Cold outreach"]]}}, creator="Silverline Marketing")
    write_csv(os.path.join(ws, "salesforce_users_export.csv"), ["Full Name", "Alias", "Username", "Email", "Role", "Active"],
              [[f"{u['first']} {u['last']}", u["alias"], u["username"], u["email"],
                "Sales Manager" if u is manager else "Account Executive", "TRUE" if u["active"] else "FALSE"] for u in users]
              + [["Integration User", "integ", f"integration@{DOMAIN}.sales", f"it@{DOMAIN}", "System", "TRUE"]], bom=True, crlf=True)
    write_csv(os.path.join(ws, "sf_lead_import_template.csv"), TEMPLATE,
              [["Pat", "Sample", "Example Foods", "Buyer", "pat.sample@examplefoods.com", "(555) 010-0100", "Web", "Open - Not Contacted",
                "Dallas", "TX", "US", f"someone@{DOMAIN}"]])
    write_text(os.path.join(ws, "salesforce_admin_notes.txt"), (
        "Salesforce lead import - notes from Wei Tanaka (our Salesforce consultant), 9 Sept 2026\n"
        "\n"
        "Use sf_lead_import_template.csv: same columns, same order, one row per lead, drop the Pat Sample row.\n"
        "\n"
        "LEAD SOURCE is a restricted picklist. Only these values import; anything else fails the row.\n"
        "  Web                 our website: contact form, quote request form, website chat\n"
        "  Advertisement       anything we paid to show: LinkedIn ads or sponsored posts, Google Ads / PPC\n"
        "  Trade Show          booth scans and business cards from any event\n"
        "  Partner Referral    sent to us by a partner, carrier or reseller\n"
        "  Employee Referral   sent to us by someone on our own staff\n"
        "  Phone Inquiry       they called us\n"
        "  Purchased List      bought or rented lists (ZoomInfo etc.)\n"
        "  Other               only if none of the above fits\n"
        "\n"
        "LEAD STATUS (restricted):\n"
        "  Open - Not Contacted     new, nobody has reached out yet (blank status in the sheet means new)\n"
        "  Working - Contacted      we have reached out or talked to them, including voicemails\n"
        "  Closed - Converted       (not used for this import)\n"
        "  Closed - Not Converted   dead, unqualified or not interested\n"
        "\n"
        "STATE AND COUNTRY: State and Country/Territory picklists are switched on, so the import takes codes, not names.\n"
        "Country Code is the two-letter ISO 3166 code (United States US, Canada CA, Mexico MX, United Kingdom GB, Germany DE).\n"
        "State/Province Code is the two-letter code for US states and Canadian provinces only; leave it blank for every\n"
        "other country. A blank country in the sheet is a US lead (marketing only leaves it off for US ones).\n"
        "\n"
        "COMPANY is required on a lead. If there is no company, put [not provided] exactly like that, which is what\n"
        "web-to-lead does.\n"
        "\n"
        "LEAD OWNER: the import wizard matches owners on their Salesforce USERNAME, not their email address, and a couple\n"
        "of ours are different, so use the Username column of the users export. Luis left in August and his user is\n"
        "deactivated; his leads and any lead without a rep go to Priya Natarajan.\n"))
    header = TEMPLATE
    out = sorted(leads, key=lambda c: c["email"])
    rows = [[c["first"], c["last"], c["company"] or "[not provided]", c["title"], c["email"], c["phone"], c["source"], c["status"],
             c["city"], c["state"], c["country"], c["owner"]["username"]] for c in out]
    write_csv(os.path.join(ref, "sf_leads.csv"), header, rows)
    write_csv(os.path.join(sol, "sf_leads.csv"), header, rows)

    def keys(tag):
        return sorted(c["email"] for c in out if tag in c["tags"])
    write_json(os.path.join(ref, "notes.json"), {t: keys(t) for t in ("source", "status", "geo", "owner", "no_company")})
    write_task_yaml(HERE, {
        "id": "salesforce-lead-import", "track": "desk", "category": "reformatting",
        "title": "Turn the Q3 leads sheet into a Salesforce lead import",
        "ask": ("Sales is moving to Salesforce and our Q3 leads need to go in. Please turn leads_master_Q3.xlsx into their import "
                "file using the template; the consultant's notes and the users export are in the folder. Save it as sf_leads.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the Source column is free text in twenty-odd spellings (booth scan, PPC, Quote request form, carrier referral, Called in, Staff referral - Tomasz) that must land on the admin's restricted Lead Source values by their definitions (check: lead source picklist)",
            "Status words (New, blank, Left VM, Dead, Unqualified) map onto Salesforce's Lead Status labels (check: lead status picklist)",
            "countries come as USA / U.S. / United States of America / CAN / UK / England / Deutschland / México or blank beside a US state, and states as codes or full names; the picklists need ISO codes (the UK is GB), state codes only for US and Canada, and Ontario CA is a city in California (check: country and state codes)",
            "Rep is a first name or initials; Lead Owner is the Salesforce username, which differs from the email for two users, and Luis's leads plus blank reps go to Priya because his user is deactivated (check: lead owner username)",
            "five leads have no company; Company is required and takes the [not provided] placeholder (check: company placeholder)",
            "the template carries a sample row and the workbook a second sheet of old picklist ideas that are not the org's values (checks: one row per lead; lead source picklist)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Salesforce template columns, exact order", "path": "sf_leads.csv", "columns": header, "exact": True},
            {"type": "csv_set_equal", "name": "one row per lead", "path": "sf_leads.csv", "column": "Email", "ref": "sf_leads.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "sf_leads.csv", "equals_ref": "sf_leads.csv"},
            {"type": "csv_values_match", "name": "lead source picklist", "path": "sf_leads.csv", "ref": "sf_leads.csv", "key": "Email",
             "columns": ["Lead Source"], "min_accuracy": 1.0, "must_match_keys": keys("source")},
            {"type": "csv_values_match", "name": "lead status picklist", "path": "sf_leads.csv", "ref": "sf_leads.csv", "key": "Email",
             "columns": ["Lead Status"], "min_accuracy": 1.0, "must_match_keys": keys("status")},
            {"type": "csv_values_match", "name": "country and state codes", "path": "sf_leads.csv", "ref": "sf_leads.csv", "key": "Email",
             "columns": ["Country Code", "State/Province Code"], "min_accuracy": 1.0, "must_match_keys": keys("geo")},
            {"type": "csv_values_match", "name": "lead owner username", "path": "sf_leads.csv", "ref": "sf_leads.csv", "key": "Email",
             "columns": ["Lead Owner"], "min_accuracy": 1.0, "must_match_keys": keys("owner")},
            {"type": "csv_values_match", "name": "company placeholder", "path": "sf_leads.csv", "ref": "sf_leads.csv", "key": "Email",
             "columns": ["Company"], "min_accuracy": 1.0, "must_match_keys": keys("no_company")},
        ],
    })
    print(f"seed={seed}: {len(leads)} leads; " + ", ".join(f"{t}={len(keys(t))}" for t in ("source", "status", "geo", "owner", "no_company")))


if __name__ == "__main__":
    emit(argparse_seed())
