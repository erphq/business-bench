#!/usr/bin/env python3
"""quickbooks-customer-import: a landscaping company's CRM account export becomes a QuickBooks Online customer import.

    python gen.py [--seed N]

Business: a landscaping and snow-removal company moving invoicing into QuickBooks Online. The CRM export has one
row per account with the whole billing address in one cell; the bookkeeper set up the import template and wrote
the rules.

Traps (each caught by a check, see task.yaml):
  * display names must be unique across customers and vendors: two active residential customers share a name
    (city in parentheses), one commercial customer has the same name as a vendor already in QuickBooks
    ("(Customer)" suffix), and an inactive account shares a name with an active one but is filtered out first, so
    the active one keeps its plain name                             (check: display names)
  * the address is one cell in five layouts: suite on its own segment or inside the street, no comma before the
    state, a line break, ZIP+4, a state spelled out, a ZIP that lost its leading zero (checks: street lines; city, state and ZIP)
  * phones in seven formats, two with extensions that QuickBooks' phone field should not carry (check: phone format)
  * payment terms in eight spellings map to the four QuickBooks terms  (check: terms)
  * leads and inactive accounts stay out                             (checks: one row per active customer; row count)
  * residential customers have no company name                       (check: company name)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["Display Name", "Company Name", "First Name", "Last Name", "Email", "Phone", "Billing Street 1", "Billing Street 2",
            "Billing City", "Billing State", "Billing ZIP", "Billing Country", "Terms", "Taxable"]
STATE_NAMES = {"OR": "Oregon", "TX": "Texas", "CO": "Colorado", "WI": "Wisconsin", "NC": "North Carolina", "ID": "Idaho",
               "VT": "Vermont", "NM": "New Mexico", "MI": "Michigan", "GA": "Georgia", "WA": "Washington", "AZ": "Arizona",
               "VA": "Virginia", "CA": "California", "OH": "Ohio", "NE": "Nebraska", "RI": "Rhode Island"}
TERMS_SPELL = {"Net 30": ["NET30", "Net 30 days", "30", "2% 10 Net 30", "net 30"], "Net 15": ["Net15", "15 days"],
               "Net 60": ["net 60", "60 days"], "Due on receipt": ["COD", "Upon receipt", "Due on receipt"]}
COMMERCIAL = ["Harbor Light Marine", "Meridian Title", "Oakhurst Pediatrics", "Redwood Property Mgmt", "Tamarack Brewing",
              "Uptown Fitness", "Westbrook Plumbing", "Fernbrook Montessori", "Valley Forge Storage", "Riverbend Physio",
              "Orchard Hill Dental", "Mossbank Accounting", "Larkspur Yoga", "Copperfield Law"]
ZIP_LEAD0 = [("Providence", "RI", "02903"), ("Burlington", "VT", "05401")]


def fmt_phone(d10: str) -> str:
    return f"({d10[:3]}) {d10[3:6]}-{d10[6:]}"


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 707)
    used_names, accts = set(), []
    cities = [c for c in CITIES if c[2][0] != "0"]

    def resident():
        while True:
            f, l = person(r)
            if (f, l) not in used_names:
                used_names.add((f, l)); return f, l

    aid = 3100
    def add(kind, name_first, name_last, company, city, status="Active", street2=None, layout=None, terms=None, phone_ext=False):
        nonlocal aid
        aid += r.randint(3, 17)
        c, st, z = city
        street = f"{r.randint(12, 9899)} {r.choice(STREETS)}"
        dom = [d for n, d, _ in COMPANIES if n == company]
        email = email_for(r, name_first, name_last, dom[0] if dom else None)
        while any(a["email"] == email for a in accts):
            email = email_for(r, name_first, name_last, dom[0] if dom else None)
        t_std = terms or r.choice(["Net 30", "Net 30", "Net 15", "Due on receipt", "Net 60"])
        a = {"id": f"ACC-{aid}", "kind": kind, "first": name_first, "last": name_last, "company": company, "email": email,
             "phone": phone_digits(r), "phone_ext": (f" x{r.randint(10, 299)}" if r.random() < 0.5 else f" ext. {r.randint(10, 299)}") if phone_ext else "",
             "street": street, "street2": street2, "city": c, "state": st, "zip": z, "zip4": None, "layout": layout or r.choice(["comma", "comma", "nocomma", "newline"]),
             "terms": t_std, "terms_raw": r.choice(TERMS_SPELL[t_std]), "exempt": r.random() < 0.2 if kind == "Commercial" else False,
             "status": status}
        accts.append(a)
        return a

    comms = r.sample(COMMERCIAL, 9)
    if "Westbrook Plumbing" not in comms:
        comms[0] = "Westbrook Plumbing"
    for i, comp in enumerate(comms):
        f, l = resident()
        add("Commercial", f, l, comp, r.choice(cities), street2=(f"{r.choice(['Suite', 'Ste'])} {r.randint(100, 450)}" if i % 3 == 0 else None))
    for i in range(16):
        f, l = resident()
        add("Residential", f, l, None, r.choice(cities), street2=(f"{r.choice(['Unit', 'Apt'])} {r.randint(1, 30)}{r.choice(['', 'B'])}" if i % 5 == 0 else None))
    # same-name active residential pair in different cities
    f, l = resident()
    c1, c2 = r.sample(cities, 2)
    twin1 = add("Residential", f, l, None, c1)
    twin2 = add("Residential", f, l, None, c2)
    # inactive account sharing a name with an active residential one
    f2, l2 = resident()
    solo = add("Residential", f2, l2, None, r.choice(cities))
    ghost = add("Residential", f2, l2, None, r.choice([c for c in cities if c[0] != solo["city"]]), status="Inactive")
    # leads
    for _ in range(3):
        f, l = resident()
        add("Residential", f, l, None, r.choice(cities), status="Lead")
    f, l = resident()
    add("Commercial", f, l, r.choice([c for c in COMMERCIAL if c not in comms]), r.choice(cities), status="Lead")
    # address layouts on specific active rows
    active = [a for a in accts if a["status"] == "Active"]
    plain = [a for a in active if a not in (twin1, twin2, solo)]
    lead0 = r.sample(plain, 2)
    for a, (c, st, z) in zip(lead0, ZIP_LEAD0):
        a["city"], a["state"], a["zip"], a["layout"] = c, st, z, "lostzero"
    rest = [a for a in plain if a not in lead0]
    zip4 = r.sample(rest, 2)
    for a in zip4:
        a["zip4"] = f"{r.randint(1000, 9999)}"
    spelled = r.sample([a for a in rest if a not in zip4], 2)
    for a in spelled:
        a["layout"] = "spelled"
    inline_suite = [a for a in rest if a["street2"] and a not in spelled][:2]
    for a in inline_suite:
        a["layout"] = "inline2"
    ext_rows = r.sample([a for a in rest if a not in zip4], 2)
    for a in ext_rows:
        a["phone_ext"] = f" x{r.randint(10, 299)}" if a is ext_rows[0] else f" ext. {r.randint(10, 299)}"
    r.shuffle(accts)
    return {"accts": accts, "twins": (twin1, twin2), "solo": solo, "ghost": ghost, "lead0": lead0, "zip4": zip4,
            "spelled": spelled, "inline": inline_suite, "ext": ext_rows}


def address_cell(a: dict) -> str:
    z = a["zip"] + (f"-{a['zip4']}" if a["zip4"] else "")
    s2 = a["street2"]
    if a["layout"] == "lostzero":
        z = a["zip"].lstrip("0")
        return f"{a['street']}{', ' + s2 if s2 else ''}, {a['city']} {a['state']} {z}"
    if a["layout"] == "spelled":
        return f"{a['street']}{', ' + s2 if s2 else ''}, {a['city']}, {STATE_NAMES[a['state']]} {z}"
    if a["layout"] == "inline2":
        return f"{a['street']} {s2}, {a['city']}, {a['state']} {z}"
    if a["layout"] == "nocomma":
        return f"{a['street']}{', ' + s2 if s2 else ''}, {a['city']} {a['state']} {z}"
    if a["layout"] == "newline":
        return f"{a['street']}{' ' + s2 if s2 else ''}\n{a['city']}, {a['state']} {z}"
    return f"{a['street']}{', ' + s2 if s2 else ''}, {a['city']}, {a['state']} {z}"


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed * 1000 + 708)
    accts = d["accts"]

    rows = []
    for a in accts:
        name = a["company"] if a["kind"] == "Commercial" else f"{a['first']} {a['last']}"
        rows.append([a["id"], name, a["kind"], f"{a['first']} {a['last']}", a["email"],
                     phone_variant(a["phone"], r.randrange(7)) + a["phone_ext"], address_cell(a), a["terms_raw"],
                     "Y" if a["exempt"] else "N", a["status"]])
    write_xlsx(os.path.join(ws, "crm_accounts_export_2026-09-10.xlsx"), {"Accounts": {
        "merged_title": "Cedar & Pine Landscaping - CRM accounts export", "preamble": [["Exported 2026-09-10 by admin. All account statuses."]],
        "header": ["Account ID", "Account Name", "Account Type", "Primary Contact", "Email", "Phone", "Billing Address", "Payment Terms", "Tax Exempt", "Status"],
        "rows": rows, "widths": {"B": 28, "D": 22, "E": 34, "G": 48}}}, creator="CRM")

    write_csv(os.path.join(ws, "QBO_Customer_Import_Template.csv"), TEMPLATE, [])

    vendors = ["Westbrook Plumbing", "Pemberton HVAC", "Quarry Road Nursery", "Hollowell Electric", "Silverline Logistics",
               "Granite Peak Outfitters", "Dorsey Freight"]
    write_csv(os.path.join(ws, "qbo_vendor_list.csv"), ["Vendor", "Company name", "Phone", "Open balance"],
              [[v, v, fmt_phone(phone_digits(r)), f"{r.randint(0, 4000)}.00"] for v in vendors])

    write_text(os.path.join(ws, "qbo_import_rules_from_marisol.txt"), """QuickBooks customer import - rules

Use the template (QBO_Customer_Import_Template.csv), same columns, same order.

- Only Active accounts. Leads and Inactive accounts stay in the CRM.
- Display Name: commercial accounts use the account name; residential accounts use the contact's first and last
  name. QuickBooks will not accept a display name that is already used by another customer OR by a vendor:
    * if two customers in this import end up with the same name, add their city in parentheses,
      e.g. "Dana Cruz (Boise)"
    * if a customer has the same name as one of our vendors (qbo_vendor_list.csv), add " (Customer)" to the
      customer, e.g. "Acme Supply (Customer)"
- Company Name: the account name for commercial accounts, blank for residential.
- First Name / Last Name: the primary contact.
- Phone as (206) 555-0142. No extensions, the phone field chokes on them.
- Billing address split into Street 1, Street 2 (suite, unit, apt - only if there is one), City, State (two-letter
  code), ZIP (five digits - drop any +4, and Excel ate the leading zero on a few New England ZIPs), Country US.
- Terms must be one of QuickBooks' terms: Due on receipt, Net 15, Net 30, Net 60. COD and upon receipt are Due on
  receipt; anything with Net 30 in it is Net 30.
- Taxable: No for tax-exempt accounts, Yes for everyone else.

Marisol
""")

    out = []
    active = [a for a in accts if a["status"] == "Active"]
    names = {}
    for a in active:
        base = a["company"] if a["kind"] == "Commercial" else f"{a['first']} {a['last']}"
        names.setdefault(base, []).append(a)
    for a in sorted(active, key=lambda a: a["id"]):
        base = a["company"] if a["kind"] == "Commercial" else f"{a['first']} {a['last']}"
        disp = base
        if len(names[base]) > 1:
            disp = f"{base} ({a['city']})"
        if base in vendors:
            disp = f"{base} (Customer)"
        a["display"] = disp
        out.append([disp, a["company"] or "", a["first"], a["last"], a["email"], fmt_phone(a["phone"]), a["street"], a["street2"] or "",
                    a["city"], a["state"], a["zip"], "US", a["terms"], "No" if a["exempt"] else "Yes"])
    for dd in (ref, sol):
        write_csv(os.path.join(dd, "qbo_customers.csv"), TEMPLATE, out)

    t1, t2 = d["twins"]
    west = next(a for a in active if a["company"] == "Westbrook Plumbing")
    odd_terms = [a["email"] for a in active if a["terms_raw"] in ("30", "2% 10 Net 30", "COD", "Upon receipt", "15 days", "60 days", "Net15")][:8]
    street_trap = [a["email"] for a in d["inline"]] + [a["email"] for a in active if a["street2"] and a["layout"] == "newline"][:1] \
        + [a["email"] for a in active if not a["street2"]][:1]
    addr_trap = [a["email"] for a in d["lead0"] + d["zip4"] + d["spelled"]]
    resident_trap = [a["email"] for a in active if a["kind"] == "Residential"][:2]
    uniq = lambda xs: list(dict.fromkeys(xs))
    write_task_yaml(HERE, {
        "id": "quickbooks-customer-import", "track": "desk", "category": "reformatting",
        "title": "CRM accounts into a QuickBooks Online customer import",
        "ask": "We're moving invoicing to QuickBooks Online. Turn the CRM export into the customer import file using Marisol's template and rules, and save it as qbo_customers.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"two active residential customers are both named {t1['first']} {t1['last']} ({t1['city']} and {t2['city']}) and need the city in parentheses (check: display names)",
            "Westbrook Plumbing is a commercial customer and also a vendor in qbo_vendor_list.csv, so its display name is 'Westbrook Plumbing (Customer)' (check: display names)",
            f"an inactive account shares the name {d['solo']['first']} {d['solo']['last']} with an active one; filtering to Active first leaves the active customer's plain name, deduplicating before filtering wrongly adds a city (check: display names)",
            "the billing address is one cell: suite as its own segment or inline after the street, no comma before the state, a line break before the city, ZIP+4, two states spelled out, and two Providence/Burlington ZIPs that lost their leading zero (checks: street lines; city, state and ZIP)",
            "phones come in seven formats and two carry extensions (x123, ext. 45) that must be dropped; the template wants (206) 555-0142 (check: phone format)",
            "payment terms are written NET30, 30, '2% 10 Net 30', COD, Upon receipt, Net15, '15 days', '60 days' and must be QuickBooks' Due on receipt / Net 15 / Net 30 / Net 60 (check: terms)",
            "three leads and one inactive account stay out (checks: one row per active customer; row count)",
            "residential customers have a blank Company Name (check: company name)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns in order", "path": "qbo_customers.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one row per active customer", "path": "qbo_customers.csv", "column": "Email", "ref": "qbo_customers.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "qbo_customers.csv", "equals_ref": "qbo_customers.csv"},
            {"type": "csv_values_match", "name": "display names", "path": "qbo_customers.csv", "ref": "qbo_customers.csv", "key": "Email",
             "columns": ["Display Name"], "min_accuracy": 1.0, "must_match_keys": [t1["email"], t2["email"], west["email"], d["solo"]["email"]]},
            {"type": "csv_values_match", "name": "company name", "path": "qbo_customers.csv", "ref": "qbo_customers.csv", "key": "Email",
             "columns": ["Company Name"], "min_accuracy": 1.0, "must_match_keys": resident_trap},
            {"type": "csv_values_match", "name": "street lines", "path": "qbo_customers.csv", "ref": "qbo_customers.csv", "key": "Email",
             "columns": ["Billing Street 1", "Billing Street 2"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": uniq(street_trap)},
            {"type": "csv_values_match", "name": "city, state and ZIP", "path": "qbo_customers.csv", "ref": "qbo_customers.csv", "key": "Email",
             "columns": ["Billing City", "Billing State", "Billing ZIP"], "normalize": ["strip", "lower"], "min_accuracy": 1.0, "must_match_keys": uniq(addr_trap)},
            {"type": "csv_values_match", "name": "phone format", "path": "qbo_customers.csv", "ref": "qbo_customers.csv", "key": "Email",
             "columns": ["Phone"], "normalize": ["strip"], "min_accuracy": 1.0, "must_match_keys": [a["email"] for a in d["ext"]]},
            {"type": "csv_values_match", "name": "terms", "path": "qbo_customers.csv", "ref": "qbo_customers.csv", "key": "Email",
             "columns": ["Terms"], "min_accuracy": 1.0, "must_match_keys": odd_terms},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
