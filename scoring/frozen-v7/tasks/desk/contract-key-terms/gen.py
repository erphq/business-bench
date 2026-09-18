#!/usr/bin/env python3
"""contract-key-terms: six service contracts (plus one amendment) to a contract register.

    python gen.py [--seed N]

Business: a self-storage operator with four facilities is setting up a contract register. The ops manager
wants one row per service contract with the vendor, the term we are in today, what we pay per year, and
whether and when the contract rolls over.

Traps (each caught by a check, see task.yaml):
  * three contracts name us first and three name the vendor first; the vendor is the service provider (check: vendor names)
  * fees are per month, quarterly installments of an annual price, per site per month, per visit, and per annum
    billed monthly; the register wants the annual figure                             (check: annual values)
  * the janitorial amendment replaces the monthly fee and extends the initial term; the amendment is not a row
    (checks: annual values; term dates; notice deadlines; row count)
  * the grounds contract's first year ended in June 2026 and rolled over with a 3% escalator (checks: term dates; annual values)
  * notice periods are in days (60, 30) and in months (three, two); months are calendar months (check: notice deadlines)
  * two contracts do not auto-renew, and both still mention renewal or a 90-day proposal (check: renewal terms)
  * a 24-month term from 1 March 2026 ends on 29 February 2028                        (check: term dates)
  * the pest control agreement is an image-only scan                                 (checks: one row per contract; annual values)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CLIENT = "Valley Forge Storage LLC"
AS_OF = date(2026, 9, 14)
MM = 2.8346  # points per mm

POOLS = {
    "janitorial": ["Brightline Janitorial Services, Inc.", "Clearwater Commercial Cleaning LLC", "Spotless Facility Care, Inc."],
    "hvac": ["Northwind Mechanical Services LLC", "Summit Air Systems, Inc.", "Keystone Climate Control LLC"],
    "grounds": ["Greenmantle Grounds Care LLC", "Fieldstone Landscape Co.", "Hedgerow Outdoor Services, Inc."],
    "pest": ["Fairhaven Pest Control Inc.", "Tri-County Pest Solutions Inc.", "Bayside Exterminating Inc."],
    "security": ["Sentinel Alarm Monitoring, Inc.", "Watchpoint Security Systems LLC", "Ironclad Monitoring Corp."],
    "waste": ["Ridgeline Waste Hauling, Inc.", "Blue Valley Disposal LLC", "Crossroads Recycling and Waste Inc."],
}
FACILITIES = ["1180 Mill Rd", "42 Bridge St", "905 Ridge Rd", "2750 Market St"]


def add_months(d: date, n: int) -> date:
    import calendar
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def long(d: date) -> str:
    return d.strftime("%B %-d, %Y")


def usd(x: float) -> str:
    return f"${x:,.2f}"


def build(seed: int) -> dict:
    r = rng(seed)
    v = {k: r.choice(pool) for k, pool in POOLS.items()}
    signers = people(r, 8)
    C = {}
    # C1 janitorial, amended
    m_old = float(r.randrange(3900, 4500, 50)); m_new = m_old + float(r.randrange(350, 600, 50))
    C["jan"] = dict(id=f"JS-2026-{r.randint(300, 699):04d}", vendor=v["janitorial"], start=date(2026, 7, 1), orig_end=date(2027, 6, 30),
                    end=date(2027, 12, 31), monthly_old=m_old, monthly=m_new, annual=round(m_new * 12, 2), auto="yes", renew=12,
                    notice_days=60)
    C["jan"]["deadline"] = C["jan"]["end"] - timedelta(days=60)
    # C2 hvac, no auto renew, quarterly installments
    q = float(r.randrange(2150, 2800, 25))
    C["hvac"] = dict(id=f"PM-{r.randint(1000, 9999)}", vendor=v["hvac"], start=date(2026, 3, 1), end=date(2028, 2, 29), quarterly=q,
                     annual=round(q * 4, 2), auto="no", renew=0, deadline=None)
    # C3 grounds, rolled over with escalator, three months notice
    mg = float(r.randrange(1650, 2100, 5))
    cur = round(mg * 1.03, 2)
    C["grounds"] = dict(id=f"GM-25-{r.randint(100, 999)}", vendor=v["grounds"], start=date(2025, 7, 1), first_end=date(2026, 6, 30),
                        end=date(2027, 6, 30), monthly_first=mg, monthly=cur, annual=round(cur * 12, 2), auto="yes", renew=12)
    C["grounds"]["deadline"] = add_months(C["grounds"]["end"], -3)
    # C4 pest, scan, per visit, month to month, 30 days
    pv = float(r.randrange(135, 195, 5))
    C["pest"] = dict(id=f"PC-{r.randint(40000, 49999)}", vendor=v["pest"], start=date(2026, 8, 1), end=date(2027, 7, 31), per_visit=pv,
                     visits_per_month=2, annual=round(pv * 24, 2), auto="yes", renew=1)
    C["pest"]["deadline"] = C["pest"]["end"] - timedelta(days=30)
    # C5 security, per site per month, does not auto renew
    ps = float(r.randrange(99, 159, 1))
    C["sec"] = dict(id=f"SM-{r.randint(10000, 99999)}", vendor=v["security"], start=date(2025, 11, 1), end=date(2028, 10, 31), per_site=ps,
                    sites=4, annual=round(ps * 4 * 12, 2), auto="no", renew=0, deadline=None)
    # C6 waste, per annum billed monthly, 24-month renewals, two months notice
    pa = float(r.randrange(10200, 14400, 120))
    C["waste"] = dict(id=f"WH-{r.randint(100, 999)}-{r.randint(10, 99)}", vendor=v["waste"], start=date(2024, 10, 1), end=date(2027, 9, 30),
                      annual=pa, auto="yes", renew=24)
    C["waste"]["deadline"] = add_months(C["waste"]["end"], -2)
    return dict(C=C, signers=signers, renee=("Renee", r.choice(LAST)))


def sig(p): return f"{p[0]} {p[1]}"


def emit(seed: int) -> None:
    d = build(seed); C = d["C"]; S = d["signers"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "contracts"); os.makedirs(F, exist_ok=True)

    # ---- C1 janitorial (Helvetica, letter, client first, prose sections)
    j = C["jan"]
    write_pdf_document(os.path.join(F, "Janitorial_Services_Agreement_signed.pdf"), [
        ("title", "Janitorial Services Agreement"), ("small", f"Agreement No. {j['id']}"), ("hr", None),
        ("p", f"This Janitorial Services Agreement (the \"Agreement\") is entered into as of June 12, 2026 by and between {CLIENT}, "
              f"an Oregon limited liability company (\"Client\"), and {j['vendor']} (\"Contractor\")."),
        ("h", "1. Services"),
        ("p", "Contractor will provide nightly office cleaning, restroom sanitation, and weekly floor care at the Client facilities listed in "
              "Exhibit A, in accordance with the scope of work attached as Exhibit B."),
        ("h", "2. Term and Renewal"),
        ("p", f"The initial term of this Agreement begins on {long(j['start'])} and ends on {long(j['orig_end'])} (the \"Initial Term\"). "
              "Thereafter, this Agreement will renew automatically for successive twelve (12) month terms unless either party gives the other "
              "written notice of non-renewal at least sixty (60) days before the end of the then-current term."),
        ("h", "3. Fees"),
        ("p", f"Client will pay Contractor {usd(j['monthly_old'])} per month for the Services, invoiced monthly in arrears and payable net thirty (30) days. "
              "Supplies are included in the monthly fee."),
        ("h", "4. Insurance"),
        ("p", "Contractor will maintain commercial general liability insurance of not less than $1,000,000 per occurrence and will name Client as additional insured."),
        ("spacer", 14),
        ("table", [["CLIENT", "CONTRACTOR"], [CLIENT, j["vendor"]], [f"By: /s/ {sig(S[0])}", f"By: /s/ {sig(S[1])}"],
                   ["Title: Operations Manager", "Title: President"], ["Date: June 12, 2026", "Date: June 12, 2026"]],
         {"col_widths": [85 * MM, 85 * MM]}),
    ], font="Helvetica", base_size=10)

    # ---- C1 amendment (Times-Roman, letter)
    write_pdf_document(os.path.join(F, "Amendment_1_JS_agreement.pdf"), [
        ("title", "Amendment No. 1"), ("p", f"to Janitorial Services Agreement No. {j['id']} dated June 12, 2026"), ("hr", None),
        ("p", f"This Amendment No. 1 is made between {CLIENT} (\"Client\") and {j['vendor']} (\"Contractor\") and is effective September 1, 2026."),
        ("spacer", 4),
        ("p", "Client has added a fourth facility to the scope of the Agreement. The parties therefore agree as follows:"),
        ("p", f"(a) Section 3 (Fees) is amended so that, effective September 1, 2026, the monthly fee is {usd(j['monthly'])} per month."),
        ("p", f"(b) Section 2 (Term and Renewal) is amended so that the Initial Term ends on {long(j['end'])}. The renewal and notice provisions of Section 2 are unchanged."),
        ("p", "(c) Except as set out in this Amendment, the Agreement remains in full force and effect."),
        ("spacer", 16),
        ("kv", [("Client", f"/s/ {sig(S[0])}, Operations Manager, August 25, 2026"), ("Contractor", f"/s/ {sig(S[1])}, President, August 26, 2026")],
         {"col_widths": [30 * MM, 140 * MM]}),
    ], font="Times-Roman", base_size=11.5)

    # ---- C2 hvac (Times-Roman, A4, vendor first, numbered clauses)
    h = C["hvac"]
    write_pdf_document(os.path.join(F, "HVAC_preventive_maintenance_contract.pdf"), [
        ("right", f"Contract # {h['id']}"),
        ("title", "Preventive Maintenance Agreement"), ("spacer", 4),
        ("p", f"This Agreement is made between {h['vendor']} (\"Provider\") and {CLIENT} (\"Customer\")."),
        ("spacer", 6),
        ("p", "<b>1. Scope.</b> Provider will inspect, clean and service the rooftop units, split systems and exhaust fans at each Customer facility "
              "four times per year, and will respond to service calls within four business hours."),
        ("p", f"<b>2. Term.</b> The term of this Agreement shall be twenty-four (24) months commencing {long(h['start'])} (the \"Effective Date\")."),
        ("p", f"<b>3. Price.</b> Annual Agreement Price: {usd(h['annual'])}, payable in four (4) quarterly installments of {usd(h['quarterly'])}. "
              "Repairs outside the scope are quoted separately."),
        ("p", "<b>4. Renewal.</b> This Agreement does not renew automatically. Any extension or renewal must be agreed in writing and signed by both parties. "
              "As a courtesy, Provider will contact Customer ninety (90) days before expiration with a renewal proposal."),
        ("p", "<b>5. Termination.</b> Either party may terminate this Agreement for material breach that is not cured within thirty (30) days of written notice."),
        ("spacer", 14),
        ("p", f"PROVIDER: {h['vendor']}  By: /s/ {sig(S[2])}, Service Manager"),
        ("p", f"CUSTOMER: {CLIENT}  By: /s/ {sig(S[0])}, Operations Manager"),
        ("small", "Date of signature: February 17, 2026"),
    ], pagesize="a4", font="Times-Roman", base_size=11)

    # ---- C3 grounds (Courier, letter, summary box first)
    g = C["grounds"]
    write_pdf_document(os.path.join(F, "grounds_maintenance_contract_2025.pdf"), [
        ("title", "GROUNDS MAINTENANCE CONTRACT"),
        ("kv", [("Contract Number", g["id"]), ("Owner", CLIENT), ("Contractor", g["vendor"]), ("Commencement Date", g["start"].strftime("%m/%d/%Y")),
                ("Initial Term", "12 months"), ("Monthly Price", usd(g["monthly_first"])), ("Sites", "; ".join(FACILITIES))],
         {"col_widths": [48 * MM, 125 * MM]}),
        ("hr", None),
        ("h", "General Conditions"),
        ("p", "1. Work. Contractor shall mow, edge, trim, remove litter and maintain planting beds at each Site weekly from April through October and "
              "every two weeks from November through March."),
        ("p", "2. Renewal. This Contract renews automatically for successive one (1) year terms unless either party notifies the other in writing no "
              "later than three (3) months prior to the expiration of the then-current term. The Monthly Price for each renewal term increases by "
              "three percent (3%) over the Monthly Price in effect during the prior term."),
        ("p", "3. Snow and ice. Snow plowing and ice treatment are billed per event at the rates in Schedule B and are not part of the Monthly Price."),
        ("p", "4. Payment. Contractor invoices on the first of each month; Owner pays within 30 days."),
        ("spacer", 12),
        ("p", f"Signed for Owner: /s/ {sig(S[0])}      Signed for Contractor: /s/ {sig(S[3])}"),
        ("p", "Dated: 06/05/2025"),
    ], font="Courier", base_size=9.5)

    # ---- C4 pest (image-only scan)
    p = C["pest"]
    write_scan_pdf(os.path.join(F, "scan_pest_control_agreement.pdf"), [
        p["vendor"].upper(), "PEST CONTROL SERVICE AGREEMENT", "", f"Agreement No: {p['id']}", "",
        f"Customer: {CLIENT}", "Service at: 4 storage facilities", "", f"Start date: {p['start'].strftime('%m/%d/%Y')}",
        "Initial term: 12 months", "Service visits: 2 per month", f"Price per visit: {usd(p['per_visit'])}", "",
        "Renewal: after the initial term this", "agreement continues month to month", "until either party cancels with 30 days",
        "written notice.", "", "Customer may add sites at the same", "price per visit.", "",
        f"Customer: /s/ {sig(S[0])}", f"Company: /s/ {sig(S[4])}", "Date: 07/22/2026"],
        font_size=34, seed=seed * 7 + 3, skew_deg=0.4, noise=300)

    # ---- C5 security (Helvetica, A4, vendor first, fee table)
    s = C["sec"]
    write_pdf_document(os.path.join(F, "Alarm_Monitoring_Contract.pdf"), [
        ("title", "Alarm Monitoring Services Contract"),
        ("kv", [("Contract ID", s["id"]), ("Installation date", long(s["start"]))], {"col_widths": [40 * MM, 120 * MM]}),
        ("spacer", 6),
        ("p", f"{s['vendor']} (\"Company\") agrees to provide the monitoring services below to {CLIENT} (\"Subscriber\") at the sites listed."),
        ("spacer", 6),
        ("table", [["Service", "Sites", "Monthly fee per site"],
                   ["24/7 intrusion and fire alarm monitoring, cellular backup", str(s["sites"]), usd(s["per_site"])]],
         {"col_widths": [95 * MM, 20 * MM, 45 * MM], "grid": True, "shade_header": True}),
        ("spacer", 8),
        ("h", "Term"),
        ("p", "The initial term of this Contract is thirty-six (36) months from the installation date. This Contract shall not automatically renew; "
              "at the end of the initial term it expires unless Company and Subscriber sign a renewal agreement. Company will send Subscriber a "
              "renewal quotation at least ninety (90) days before the end of the initial term."),
        ("h", "Billing"),
        ("p", "Monitoring fees are billed monthly in advance. Equipment remains the property of Company. Alarm response dispatch fees charged by "
              "local authorities are passed through at cost."),
        ("spacer", 12),
        ("table", [["Company", "Subscriber"], [f"/s/ {sig(S[5])}", f"/s/ {sig(S[0])}"], ["Regional Sales Director", "Operations Manager"], ["10/14/2025", "10/14/2025"]],
         {"col_widths": [80 * MM, 80 * MM]}),
    ], pagesize="a4", font="Helvetica", base_size=9.5)

    # ---- C6 waste (Times-Roman, letter, client first, words for dates)
    w = C["waste"]
    write_pdf_document(os.path.join(F, "WasteHauling_ServiceAgreement.pdf"), [
        ("small", f"Service Agreement {w['id']}"),
        ("title", "Solid Waste and Recycling Service Agreement"), ("hr", None),
        ("p", f"THIS AGREEMENT is made by {CLIENT} (the \"Customer\") and {w['vendor']} (the \"Hauler\")."),
        ("spacer", 4),
        ("p", "<b>Service.</b> Hauler shall furnish one 6-yard refuse container and one 4-yard cardboard container at each Customer facility and empty "
              "each container once per week."),
        ("p", "<b>Term.</b> This Agreement commences on the first day of October, 2024 and continues for a term of thirty-six (36) months. Upon "
              "expiration, this Agreement will automatically renew for additional terms of twenty-four (24) months unless Customer provides "
              "notice of termination not less than two (2) months before expiration."),
        ("p", f"<b>Charges.</b> Customer shall pay {usd(w['annual'])} per annum, billed in twelve equal monthly installments. Extra pickups are "
              "charged at $95.00 each. Hauler may pass through documented increases in landfill disposal fees once per year."),
        ("p", "<b>Default.</b> If Customer fails to pay any invoice within forty-five (45) days, Hauler may suspend service on ten (10) days' notice."),
        ("spacer", 14),
        ("p", f"CUSTOMER: /s/ {sig(S[6])}, Facilities Director      HAULER: /s/ {sig(S[7])}, General Manager"),
        ("p", "Executed September 9, 2024"),
    ], font="Times-Roman", base_size=10.5)

    renee = d["renee"]
    write_text(os.path.join(ws, "note_from_renee.txt"),
        "Hi,\n\n"
        "I'm finally setting up a contract register so we stop getting surprised by renewals. All our signed service contracts are in the "
        "contracts folder. I need contracts.csv with one row per contract and these columns:\n\n"
        "contract_id - the agreement or contract number as printed\n"
        "vendor - the company providing the service, full legal name as written in the contract\n"
        "start_date - the date the contract first started\n"
        "end_date - the end of the term we are in right now. If a contract has already rolled over, that's the end of the renewal term.\n"
        "annual_value - what we pay per year for the contract as it stands today, plain number\n"
        "auto_renew - yes or no\n"
        "renewal_months - how long each automatic renewal lasts, in months (0 if it doesn't renew automatically)\n"
        "notice_deadline - the last day we could send notice so it doesn't roll over at end_date, counting the notice period back from "
        "end_date. Blank if it doesn't renew automatically.\n\n"
        "Dates as YYYY-MM-DD. If an amendment changed something, use the amended terms (the amendment isn't a separate contract). "
        "Take everything as of today, 14 September 2026.\n\n"
        f"Thanks!\n{renee[0]} {renee[1]}\n")

    header = ["contract_id", "vendor", "start_date", "end_date", "annual_value", "auto_renew", "renewal_months", "notice_deadline"]
    order = ["jan", "hvac", "grounds", "pest", "sec", "waste"]
    rows = []
    for k in order:
        c = C[k]
        rows.append([c["id"], c["vendor"], c["start"].isoformat(), c["end"].isoformat(), f"{c['annual']:.2f}", c["auto"], c["renew"],
                     c["deadline"].isoformat() if c["deadline"] else ""])
    write_csv(os.path.join(ref, "contracts.csv"), header, rows)
    write_csv(os.path.join(sol, "contracts.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {
        "amended": {"id": C["jan"]["id"], "original_monthly": C["jan"]["monthly_old"], "original_end": C["jan"]["orig_end"].isoformat()},
        "rolled_over": {"id": C["grounds"]["id"], "first_term_end": C["grounds"]["first_end"].isoformat(), "first_monthly": C["grounds"]["monthly_first"]},
        "naive_notice_90_days_for_3_months": (C["grounds"]["end"] - timedelta(days=90)).isoformat(),
        "naive_notice_60_days_for_2_months": (C["waste"]["end"] - timedelta(days=60)).isoformat(),
        "scan_id": C["pest"]["id"]})
    ids = {k: C[k]["id"] for k in order}
    write_task_yaml(HERE, {
        "id": "contract-key-terms", "track": "desk", "category": "extraction",
        "title": "Pull key terms from our service contracts into a register",
        "ask": "Can you go through our service contracts and put the key terms into contracts.csv, one row per contract? They're in the contracts folder and Renee's note says what she needs.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "three contracts name us first (one in a summary box) and three name the vendor first (the pest scan only in its letterhead), so the first party named is not the vendor; the vendor is the service provider's full legal name (check: vendor names)",
            "fees are stated per month, as quarterly installments of an annual price, per site per month (4 sites), per visit (2 a month), and per annum billed monthly; the register wants the annual figure (check: annual values)",
            "the janitorial amendment raises the monthly fee and extends the initial term to 31 Dec 2027, which moves the notice deadline; the amendment is not a contract of its own (checks: annual values; term dates; notice deadlines; row count)",
            "the grounds contract's first year ended 30 June 2026 and rolled over automatically with a 3% price escalator, so today's term ends 30 June 2027 and the fee is 3% higher than printed (checks: term dates; annual values)",
            "notice periods are written in days (sixty, 30) and in months (three, two); counting months as 30 days moves the grounds and waste deadlines (check: notice deadlines)",
            "the HVAC and alarm contracts do not auto-renew but both mention renewal and a 90-day proposal or quotation; month-to-month continuation on the pest contract is a 1-month renewal (check: renewal terms)",
            "the HVAC term is 'twenty-four (24) months commencing March 1, 2026' and ends on 29 February 2028 (check: term dates)",
            "the pest control agreement is an image-only scan (checks: one row per contract; annual values)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "contracts.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per contract", "path": "contracts.csv", "column": "contract_id", "ref": "contracts.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "contracts.csv", "equals_ref": "contracts.csv"},
            {"type": "csv_values_match", "name": "vendor names", "path": "contracts.csv", "ref": "contracts.csv", "key": "contract_id",
             "columns": ["vendor"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": [ids["jan"], ids["grounds"], ids["waste"]]},
            {"type": "csv_values_match", "name": "term dates", "path": "contracts.csv", "ref": "contracts.csv", "key": "contract_id",
             "columns": ["start_date", "end_date"], "min_accuracy": 1.0, "must_match_keys": [ids["jan"], ids["hvac"], ids["grounds"], ids["waste"]]},
            {"type": "csv_values_match", "name": "annual values", "path": "contracts.csv", "ref": "contracts.csv", "key": "contract_id",
             "columns": ["annual_value"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": list(ids.values())},
            {"type": "csv_values_match", "name": "renewal terms", "path": "contracts.csv", "ref": "contracts.csv", "key": "contract_id",
             "columns": ["auto_renew", "renewal_months"], "min_accuracy": 1.0, "must_match_keys": [ids["hvac"], ids["sec"], ids["pest"], ids["waste"]]},
            {"type": "csv_values_match", "name": "notice deadlines", "path": "contracts.csv", "ref": "contracts.csv", "key": "contract_id",
             "columns": ["notice_deadline"], "min_accuracy": 1.0, "must_match_keys": [ids["jan"], ids["grounds"], ids["waste"], ids["hvac"], ids["sec"]]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
