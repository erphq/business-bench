#!/usr/bin/env python3
"""hubspot-deals-import: a roofing contractor's pipeline workbook turned into a HubSpot deals import file.

    python gen.py [--seed N]

Business: Pinnacle Roofing tracks commercial bids and residential jobs on two tabs of one workbook. They set up two
HubSpot pipelines with their own stage names and already imported their companies; the deals come next.

Traps (each caught by a check, see task.yaml):
  * each tab is its own pipeline with its own stage labels; the workbook's stage words (Bid out, Awarded, Value
    engineering, Inspected, Ghosted, No bid, On hold) map by the stage definitions in the note (check: pipeline and stage)
  * amounts are "$48,500", "48.5k", "~12,000", "$1.15M", "rev 52,000 (was 48,500)", TBD or real numbers; HubSpot
    takes a plain number, the latest revision, and blank for TBD                (check: amount)
  * closed deals close on their Closed On date even though an old Expected Close is still filled; open deals use
    Expected Close, where a month means its last day and a quarter its last day (check: close date)
  * the Client column is a loose spelling; the association uses the Company Domain Name from the companies export,
    "Northfield Auto" is resolved by the contact's email domain, and homeowners have no company (check: company domain)
  * the Archive 2025 tab is last year's closed work and stays out               (checks: one deal per bid; row count)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["Bid Number", "Deal Name", "Pipeline", "Deal Stage", "Amount", "Close Date", "Company Domain Name"]
COMM = {"Lead In": ["New", "lead", "New lead"], "Site Walk Scheduled": ["Site walk", "Walkthrough sched.", "Site visit booked"],
        "Proposal Sent": ["Bid out", "Proposal sent", "On hold - budget"], "Negotiation": ["Negotiating", "Revising price", "Value engineering"],
        "Closed Won": ["Won", "Awarded", "Signed"], "Closed Lost": ["Lost", "Went w/ competitor", "No bid"]}
RES = {"New Inquiry": ["Inquiry", "Called in", "Web lead"], "Inspection Booked": ["Inspection set", "Inspected"],
       "Estimate Sent": ["Estimate sent", "Quote given"], "Closed Won": ["Sold", "Won"], "Closed Lost": ["Lost", "Too expensive", "Ghosted"]}
EXTRA_COMPANIES = [("Northfield Auto Glass", "northfieldautoglass.com"), ("Sunrise Ridge HOA", "sunriseridgehoa.org"),
                   ("Aspen Court Condominiums", "aspencourtcondos.com"), ("Summit Charter School", "summitcharter.org"),
                   ("Maple Grove Senior Living", "maplegroveliving.com"), ("Front Range Self Storage", "frontrangestorage.com")]
COMM_JOBS = ["TPO roof replacement", "Re-roof Bldg {b}", "Metal roof retrofit", "Roof coating - warehouse", "Skylight + flashing repair",
             "Tear-off and replace, {b} wing", "Parapet and coping repair", "Gutter + downspout replacement", "Hail damage repair Bldg {b}"]
RES_JOBS = ["Asphalt shingle replacement", "Hail claim - full re-roof", "Leak repair", "Cedar shake to composite", "Gutters and fascia",
            "Chimney flashing", "Attic ventilation + ridge vent"]


def last_of_month(y: int, m: int) -> date:
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def build(seed: int) -> dict:
    r = rng(seed)
    companies = [(n, d) for n, d, _ in COMPANIES if n not in ("Pinnacle Roofing",)] + EXTRA_COMPANIES
    comm_clients = r.sample([c for c in companies if not c[0].startswith("Northfield")], 16) + [("Northfield Auto Body", "northfieldauto.com"),
                                                                                                ("Northfield Auto Glass", "northfieldautoglass.com")]
    deals = []
    # commercial
    comm_stage_plan = (["Lead In"] * 4 + ["Site Walk Scheduled"] * 4 + ["Proposal Sent"] * 6 + ["Negotiation"] * 4 +
                       ["Closed Won"] * 6 + ["Closed Lost"] * 5)
    r.shuffle(comm_stage_plan)
    for k, stage in enumerate(comm_stage_plan):
        client = comm_clients[k % len(comm_clients)] if k < len(comm_clients) else r.choice(comm_clients[:16])
        f, l = person(r)
        dl = {"bid": f"C-26-{k + 1:03d}", "pipeline": "Commercial Bids", "stage": stage, "client": client, "tags": set(),
              "job": r.choice(COMM_JOBS).format(b=r.choice("ABCDE")), "contact_email": f"{f[0].lower()}{l.lower()}@{client[1]}",
              "amount": float(r.randint(16, 900) * 500), "stage_text": r.choice(COMM[stage])}
        deals.append(dl)
    # residential: homeowners and property managers / HOAs
    res_stage_plan = ["New Inquiry"] * 4 + ["Inspection Booked"] * 4 + ["Estimate Sent"] * 5 + ["Closed Won"] * 5 + ["Closed Lost"] * 4
    r.shuffle(res_stage_plan)
    res_companies = [c for c in companies if c[0] in ("Sunrise Ridge HOA", "Aspen Court Condominiums", "Redwood Property Mgmt",
                                                       "Maple Grove Senior Living")]
    for k, stage in enumerate(res_stage_plan):
        f, l = person(r)
        homeowner = k % 3 != 0
        client = ("", "") if homeowner else res_companies[k % len(res_companies)]
        dl = {"bid": f"R-26-{k + 1:03d}", "pipeline": "Residential Jobs", "stage": stage, "client": client, "tags": set(),
              "job": r.choice(RES_JOBS), "homeowner": f"{f} {l}" if homeowner else "",
              "contact_email": email_for(r, f, l) if homeowner else f"{f[0].lower()}{l.lower()}@{client[1]}",
              "amount": float(r.randint(12, 76) * 500), "stage_text": r.choice(RES[stage])}
        if homeowner:
            dl["tags"].add("homeowner")
        deals.append(dl)
    for dl in deals:
        dl["tags"].add("stage")
    # amounts
    open_early = [d for d in deals if d["stage"] in ("Lead In", "New Inquiry", "Site Walk Scheduled")]
    for d in r.sample(open_early, 3):
        d["amount"] = None; d["amount_text"] = "TBD"; d["tags"].add("amount")
    styles = ["num", "dollar", "k", "tilde", "rev", "dollar", "num", "plain_commas"]
    for d in deals:
        if d["amount"] is None:
            continue
        st = r.choice(styles)
        a = d["amount"]
        if st == "num":
            d["amount_text"] = a
        elif st == "dollar":
            d["amount_text"] = f"${a:,.0f}"
        elif st == "k" and a % 100 == 0:
            d["amount_text"] = f"{a / 1000:g}k"
        elif st == "tilde" and a % 1000 == 0:
            d["amount_text"] = f"~{a:,.0f}"
        elif st == "rev":
            old = a - r.randint(2, 12) * 500 if a > 7000 else a + 1500
            d["amount_text"] = f"rev {a:,.0f} (was {old:,.0f})"
        else:
            d["amount_text"] = f"{a:,.2f}"
        if not isinstance(d["amount_text"], float):
            d["tags"].add("amount")
    big = next(d for d in deals if d["pipeline"] == "Commercial Bids" and d["stage"] == "Negotiation")
    big["amount"] = 1150000.0; big["amount_text"] = "$1.15M"; big["tags"].add("amount")
    # dates
    for d in deals:
        closed = d["stage"].startswith("Closed")
        if closed:
            d["close"] = day_in(r, date(2026, 1, 12), date(2026, 9, 5), weekday_only=True)
            d["closed_text"] = d["close"] if r.random() < 0.6 else f"{d['close'].month}/{d['close'].day}/{d['close'].year % 100:02d}"
            guess = d["close"] + timedelta(days=r.randint(-40, 40))
            d["expected_text"] = guess
            d["tags"].add("date")
        else:
            d["closed_text"] = ""
            k = r.random()
            if k < 0.35:
                d["close"] = day_in(r, date(2026, 9, 15), date(2026, 12, 20), weekday_only=True); d["expected_text"] = d["close"]
            elif k < 0.55:
                d["close"] = day_in(r, date(2026, 9, 15), date(2026, 12, 20), weekday_only=True)
                d["expected_text"] = f"{d['close'].month}/{d['close'].day}/{d['close'].year}"; d["tags"].add("date")
            elif k < 0.72:
                m = r.choice([10, 11, 12]); d["close"] = last_of_month(2026, m)
                d["expected_text"] = f"{d['close']:%b} 2026"; d["tags"].add("date")
            elif k < 0.85:
                m = r.choice([9, 10, 11]); d["close"] = last_of_month(2026, m)
                d["expected_text"] = f"end of {['Sept', 'Oct', 'Nov'][m - 9]}"; d["tags"].add("date")
            else:
                q = r.choice([("Q4", date(2026, 12, 31)), ("Q1 2027", date(2027, 3, 31))])
                d["close"] = q[1]; d["expected_text"] = q[0]; d["tags"].add("date")
    # client spellings
    for d in deals:
        name, dom = d["client"]
        if not name:
            d["client_text"] = d["homeowner"]; continue
        variants = [name, name.upper(), f"{name} Inc", name.replace("Property Mgmt", "PM").replace("Condominiums", "Condos"),
                    name.replace(" & ", " and ")]
        d["client_text"] = r.choice(variants)
        if d["client_text"] != name:
            d["tags"].add("company")
    for d in deals:
        if d["client"][0].startswith("Northfield"):
            d["client_text"] = "Northfield Auto"; d["tags"].add("company")
    for d in r.sample([d for d in deals if d["client"][0] and not d["client"][0].startswith("Northfield")], 6):
        d["contact_email"] = ""
    # archive tab
    archive = []
    for k in range(9):
        name, dom = r.choice(comm_clients[:16])
        stage = r.choice(["Closed Won", "Closed Lost"])
        close = day_in(r, date(2025, 3, 1), date(2025, 12, 15), weekday_only=True)
        archive.append([f"C-25-{k + 31:03d}", r.choice(COMM_JOBS).format(b=r.choice("ABC")), name, "", r.choice(COMM[stage]),
                        float(r.randint(20, 400) * 500), close - timedelta(days=20), close, ""])
    return {"deals": deals, "archive": archive, "companies": companies}


def emit(seed: int) -> None:
    d = build(seed)
    deals, archive, companies = d["deals"], d["archive"], d["companies"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 29)
    estimators = ["Hiroshi", "Dana", "Marcus"]
    comm_rows = [[dl["bid"], dl["job"], dl["client_text"], dl["contact_email"], r.choice(estimators), dl["stage_text"],
                  dl["amount_text"], dl["expected_text"], dl["closed_text"], r.choice(["", "", "", "needs insurance cert", "GC is Kiewit",
                                                                                         "prevailing wage", "phased over two summers"])]
                 for dl in deals if dl["pipeline"] == "Commercial Bids"]
    res_rows = [[dl["bid"], dl["client_text"], dl["job"], dl["contact_email"], dl["stage_text"], dl["amount_text"], dl["expected_text"],
                 dl["closed_text"], r.choice(["", "", "insurance claim", "HOA approval needed", "financing"])]
                for dl in deals if dl["pipeline"] == "Residential Jobs"]
    write_xlsx(os.path.join(ws, "pipeline_2026.xlsx"), {
        "Commercial": {"header": ["Bid #", "Job", "Client", "Client Contact Email", "Estimator", "Stage", "Bid Amount", "Expected Close",
                                  "Closed On", "Notes"], "rows": comm_rows, "widths": {"B": 30, "C": 28, "D": 34, "G": 26, "J": 26}, "freeze": "A2"},
        "Residential": {"header": ["Job #", "Customer", "Work", "Email", "Status", "Quote", "Expected Close", "Closed On", "Notes"],
                        "rows": res_rows, "widths": {"B": 28, "C": 30, "D": 34, "F": 26}, "freeze": "A2"},
        "Archive 2025": {"header": ["Bid #", "Job", "Client", "Client Contact Email", "Stage", "Bid Amount", "Expected Close", "Closed On", "Notes"],
                         "rows": archive, "widths": {"B": 30, "C": 28}}}, creator="Pinnacle Roofing")
    comp_rows = [[n, dm, r.choice(["Denver", "Boulder", "Lakewood", "Aurora", "Golden"]), r.choice(["Customer", "Lead", "Opportunity"])]
                 for n, dm in sorted(companies)]
    write_csv(os.path.join(ws, "hubspot_companies_export.csv"), ["Record ID", "Company name", "Company Domain Name", "City", "Lifecycle Stage"],
              [[str(18800000 + 37 * k), *row] for k, row in enumerate(comp_rows)], bom=True)
    write_csv(os.path.join(ws, "hubspot_deals_import_template.csv"), TEMPLATE, [])
    write_text(os.path.join(ws, "hubspot_setup_notes.md"), (
        "# HubSpot deals import\n\n"
        "From Marcus. Companies are already in HubSpot (export attached). Now the deals, using the template columns in that order.\n"
        "Import both tabs of the pipeline workbook, one deal per bid or job number. The Archive 2025 tab is last year's work;\n"
        "leave it out.\n\n"
        "**Bid Number** is a custom deal property so we can match things later: the Bid # / Job # as written.\n\n"
        "**Deal Name** is the job description (the Job column on Commercial, the Work column on Residential).\n\n"
        "**Pipeline and Deal Stage** have to match HubSpot's labels exactly. The Commercial tab goes in the *Commercial Bids*\n"
        "pipeline, the Residential tab in *Residential Jobs*.\n\n"
        "Commercial Bids stages:\n\n"
        "- Lead In: a new request we have not visited yet\n"
        "- Site Walk Scheduled: a site walk or visit is booked\n"
        "- Proposal Sent: our bid is with the client, including bids they have put on hold\n"
        "- Negotiation: we are revising price or scope with them (value engineering counts)\n"
        "- Closed Won: awarded or signed\n"
        "- Closed Lost: they went with someone else, or we decided not to bid\n\n"
        "Residential Jobs stages:\n\n"
        "- New Inquiry: a call or web lead\n"
        "- Inspection Booked: the roof inspection is booked or done but no estimate has gone out yet\n"
        "- Estimate Sent: the homeowner has our estimate or quote\n"
        "- Closed Won: sold\n"
        "- Closed Lost: lost, too expensive, or they stopped answering\n\n"
        "**Amount** is a plain number (no $ or commas). If the bid was revised, use the latest number. TBD stays blank.\n\n"
        "**Close Date** is YYYY-MM-DD. For won and lost deals it is the date in Closed On (ignore whatever the old Expected\n"
        "Close says). For open deals it is Expected Close; where we only wrote a month, use the last day of that month, and\n"
        "for a quarter use the last day of the quarter (Q4 means Q4 2026).\n\n"
        "**Company Domain Name** is how HubSpot links the deal to the company, so copy the domain from the companies export.\n"
        "The Client column is typed loosely. Where the name alone is ambiguous, the contact's email domain tells you which\n"
        "company it is. Residential jobs for private homeowners have no company: leave it blank.\n"))
    out = sorted(deals, key=lambda x: x["bid"])
    rows = [[dl["bid"], dl["job"], dl["pipeline"], dl["stage"], "" if dl["amount"] is None else f"{dl['amount']:.2f}", dl["close"].isoformat(),
             dl["client"][1]] for dl in out]
    write_csv(os.path.join(ref, "hubspot_deals.csv"), TEMPLATE, rows)
    write_csv(os.path.join(sol, "hubspot_deals.csv"), TEMPLATE, rows)

    def keys(tag):
        return sorted(dl["bid"] for dl in out if tag in dl["tags"])
    write_json(os.path.join(ref, "notes.json"), {t: keys(t) for t in ("stage", "amount", "date", "company", "homeowner")})
    write_task_yaml(HERE, {
        "id": "hubspot-deals-import", "track": "desk", "category": "reformatting",
        "title": "Import the roofing pipeline into HubSpot deals",
        "ask": ("Our companies are in HubSpot now; next are the deals from pipeline_2026.xlsx. Marcus wrote up how our pipelines are set "
                "up, and the companies export and HubSpot's template are in the folder. Save the import as hubspot_deals.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "each tab is its own pipeline with its own stage labels, and the workbook's stage words (Bid out, On hold - budget, Value engineering, Awarded, No bid, Inspected, Quote given, Ghosted) must map by the stage definitions; copying Status or Stage fails the import (check: pipeline and stage)",
            "amounts come as $48,500, 48.5k, ~12,000, $1.15M, rev 52,000 (was 48,500), 12,400.00, TBD or real numbers; HubSpot needs a plain number, the latest revision and blank for TBD (check: amount)",
            "won and lost deals still carry an old Expected Close and must close on their Closed On date (some typed 8/12/26); open deals written Oct 2026, end of Sept, Q4 or Q1 2027 take the last day of that month or quarter (check: close date)",
            "the Client column is a loose spelling (REDWOOD PROPERTY MGMT, Redwood PM, Aspen Court Condos, an added Inc); the association needs the domain from the companies export, two Northfield companies are both typed Northfield Auto and only the contact email tells them apart, and homeowner jobs get no domain (check: company domain)",
            "the Archive 2025 tab holds nine closed deals from last year that must stay out (checks: one deal per bid; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "HubSpot template columns, exact order", "path": "hubspot_deals.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one deal per bid", "path": "hubspot_deals.csv", "column": "Bid Number", "ref": "hubspot_deals.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "hubspot_deals.csv", "equals_ref": "hubspot_deals.csv"},
            {"type": "csv_values_match", "name": "pipeline and stage", "path": "hubspot_deals.csv", "ref": "hubspot_deals.csv", "key": "Bid Number",
             "columns": ["Pipeline", "Deal Stage"], "min_accuracy": 1.0, "must_match_keys": keys("stage")},
            {"type": "custom", "name": "amount", "module": "check.py"},
            {"type": "csv_values_match", "name": "close date", "path": "hubspot_deals.csv", "ref": "hubspot_deals.csv", "key": "Bid Number",
             "columns": ["Close Date"], "min_accuracy": 1.0, "must_match_keys": keys("date")},
            {"type": "csv_values_match", "name": "company domain", "path": "hubspot_deals.csv", "ref": "hubspot_deals.csv", "key": "Bid Number",
             "columns": ["Company Domain Name"], "min_accuracy": 1.0, "must_match_keys": keys("company") + keys("homeowner")},
        ],
    })
    print(f"seed={seed}: {len(deals)} deals + {len(archive)} archived; " + ", ".join(f"{t}={len(keys(t))}" for t in ("stage", "amount", "date", "company", "homeowner")))


if __name__ == "__main__":
    emit(argparse_seed())
