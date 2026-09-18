"""bizgen: shared, deterministic generators for Business Harness Bench tasks.

Import from a task's gen.py with:

    import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'lib'))
    from bizgen import *

Everything here is seeded through a `random.Random` you pass in; nothing reads the clock.
Writers produce byte-identical files for the same inputs (fixed zip timestamps, fixed document
properties, reportlab invariant mode), so `python gen.py --seed 0` twice gives the same bytes.
"""
from __future__ import annotations

import csv
import io
import json
import os
import random
import re
import shutil
import sqlite3
import zipfile
from datetime import date, datetime, timedelta

# --------------------------------------------------------------------------- pools

FIRST = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "David", "Elizabeth",
         "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen",
         "Christopher", "Lisa", "Daniel", "Nancy", "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra",
         "Donald", "Ashley", "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
         "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Dorothy", "George", "Melissa", "Timothy", "Deborah",
         "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon", "Jeffrey", "Laura", "Ryan", "Cynthia",
         "Jacob", "Kathleen", "Gary", "Amy", "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna",
         "Priya", "Wei", "Carlos", "Fatima", "Hiroshi", "Amara", "Luis", "Ingrid", "Omar", "Sofia", "Kwame",
         "Yuki", "Mateo", "Aisha", "Dmitri", "Chloe", "Rahul", "Nadia", "Tomasz", "Leila", "Marcus", "Dana"]
LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
        "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
        "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
        "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
        "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts", "Gomez",
        "Phillips", "Evans", "Turner", "Diaz", "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart",
        "Morris", "Morales", "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson",
        "Bailey", "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks",
        "Chavez", "Wood", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes", "Price", "Alvarez", "Castillo",
        "Patel", "Myers", "Long", "Ross", "Foster", "Okafor", "Tanaka", "Lindqvist", "Haddad", "Osei", "Mensah"]
# (name, domain, industry)
COMPANIES = [("Acme Industrial", "acmeindustrial.com", "manufacturing"), ("Brightwater Dental", "brightwaterdental.com", "clinic"),
             ("Cedar & Pine Landscaping", "cedarpine.co", "landscaping"), ("Dorsey Freight", "dorseyfreight.com", "logistics"),
             ("Ellington Bakeries", "ellingtonbakes.com", "food"), ("Foxglove Interiors", "foxgloveinteriors.com", "design"),
             ("Granite Peak Outfitters", "granitepeak.com", "retail"), ("Harbor Light Marine", "harborlightmarine.com", "marine"),
             ("Ironwood Fabrication", "ironwoodfab.com", "manufacturing"), ("Juniper Street Cafe", "juniperstreet.cafe", "food"),
             ("Kestrel Analytics", "kestrelanalytics.io", "software"), ("Lakeside Veterinary", "lakesidevet.com", "clinic"),
             ("Meridian Title", "meridiantitle.com", "legal"), ("Northfield Auto Body", "northfieldauto.com", "auto"),
             ("Oakhurst Pediatrics", "oakhurstpeds.org", "clinic"), ("Pinnacle Roofing", "pinnacleroofing.com", "construction"),
             ("Quarry Road Nursery", "quarryroad.com", "retail"), ("Redwood Property Mgmt", "redwoodpm.com", "property"),
             ("Silverline Logistics", "silverlinelogistics.com", "logistics"), ("Tamarack Brewing", "tamarackbrewing.com", "food"),
             ("Uptown Fitness", "uptownfit.com", "fitness"), ("Vantage Point Media", "vantagepointmedia.com", "media"),
             ("Westbrook Plumbing", "westbrookplumbing.com", "trades"), ("Yellowtail Seafood", "yellowtailseafood.com", "food"),
             ("Blue Heron Consulting", "blueheronconsulting.com", "services"), ("Copperfield Law", "copperfieldlaw.com", "legal"),
             ("Driftwood Studio", "driftwoodstudio.design", "design"), ("Everline Insurance", "everline.com", "insurance"),
             ("Fernbrook Montessori", "fernbrookmontessori.org", "education"), ("Glassworks Optical", "glassworksoptical.com", "retail"),
             ("Hollowell Electric", "hollowellelectric.com", "trades"), ("Ivy Lane Florist", "ivylaneflorist.com", "retail"),
             ("Kingfisher Charters", "kingfishercharters.com", "marine"), ("Larkspur Yoga", "larkspuryoga.com", "fitness"),
             ("Mossbank Accounting", "mossbank.cpa", "services"), ("Nightjar Coffee Roasters", "nightjar.coffee", "food"),
             ("Orchard Hill Dental", "orchardhilldental.com", "clinic"), ("Pemberton HVAC", "pembertonhvac.com", "trades"),
             ("Quill & Ink Print Shop", "quillandink.print", "print"), ("Riverbend Physio", "riverbendphysio.com", "clinic"),
             ("Saltmarsh Kayaks", "saltmarshkayaks.com", "retail"), ("Thistle & Thread Alterations", "thistlethread.com", "retail"),
             ("Umber Ceramics", "umberceramics.com", "craft"), ("Valley Forge Storage", "valleyforgestorage.com", "property"),
             ("Wren & Sparrow Bookshop", "wrensparrowbooks.com", "retail"), ("Zephyr Bike Works", "zephyrbikes.com", "retail")]
STREETS = ["Maple St", "Oak Ave", "Cedar Ln", "Elm Dr", "Pine Rd", "Birch Ct", "Willow Way", "Spruce Blvd", "Ash St",
           "Hickory Pl", "Chestnut Ave", "Walnut St", "Poplar Rd", "Sycamore Ln", "Magnolia Dr", "Laurel Ct", "Juniper Way",
           "Hawthorn Blvd", "Alder St", "Dogwood Ave", "Main St", "Church St", "Mill Rd", "Park Ave", "Lake Dr", "Ridge Rd",
           "River St", "Hill St", "Union St", "Market St", "Water St", "Bridge St", "School St", "Prospect Ave", "Highland Ave"]
CITIES = [("Portland", "OR", "97209"), ("Austin", "TX", "78701"), ("Denver", "CO", "80202"), ("Madison", "WI", "53703"),
          ("Raleigh", "NC", "27601"), ("Boise", "ID", "83702"), ("Asheville", "NC", "28801"), ("Burlington", "VT", "05401"),
          ("Santa Fe", "NM", "87501"), ("Ann Arbor", "MI", "48104"), ("Boulder", "CO", "80302"), ("Eugene", "OR", "97401"),
          ("Savannah", "GA", "31401"), ("Tacoma", "WA", "98402"), ("Tucson", "AZ", "85701"), ("Richmond", "VA", "23219"),
          ("Sacramento", "CA", "95814"), ("Columbus", "OH", "43215"), ("Omaha", "NE", "68102"), ("Providence", "RI", "02903")]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "hotmail.com", "aol.com", "protonmail.com", "me.com"]
BANKS = ["First Meridian Bank", "Cascade Credit Union", "Harbor Trust", "Northgate Savings", "Union Plains Bank"]
# merchant string as it appears on a card statement, category, plain name
MERCHANTS = [("AMZN Mktp US*2K4JR7", "office", "Amazon"), ("UBER *TRIP", "travel", "Uber"), ("DELTA AIR 0062341", "travel", "Delta"),
             ("STARBUCKS #04512", "meals", "Starbucks"), ("SQ *BLUE BOTTLE", "meals", "Blue Bottle"), ("WEWORK 1201", "office", "WeWork"),
             ("ADOBE *CREATIVE CLD", "software", "Adobe"), ("GOOGLE *GSUITE", "software", "Google Workspace"), ("NOTION LABS", "software", "Notion"),
             ("ZOOM.US 888-799-9666", "software", "Zoom"), ("COSTCO WHSE #0891", "office", "Costco"), ("THE HOME DEPOT #4402", "office", "Home Depot"),
             ("IKEA EMERYVILLE", "office", "IKEA"), ("CB2 STORE 0231", "office", "CB2"), ("SHELL OIL 57444", "travel", "Shell"),
             ("MARRIOTT HTL", "travel", "Marriott"), ("USPS PO 0561", "shipping", "USPS"), ("FEDEX 78123", "shipping", "FedEx"),
             ("UPS*1Z8834", "shipping", "UPS"), ("LINKEDIN PREMIUM", "marketing", "LinkedIn"), ("FACEBK *ADS", "marketing", "Meta Ads"),
             ("GOOGLE *ADS", "marketing", "Google Ads"), ("MAILCHIMP", "marketing", "Mailchimp"), ("SLACK T0123", "software", "Slack"),
             ("GITHUB INC", "software", "GitHub"), ("OFFICE DEPOT 2231", "office", "Office Depot"), ("CHIPOTLE 1882", "meals", "Chipotle"),
             ("PANERA BREAD #601", "meals", "Panera"), ("LYFT *RIDE", "travel", "Lyft"), ("HERTZ RENT-A-CAR", "travel", "Hertz"),
             ("VERIZON WRLS", "utilities", "Verizon"), ("COMCAST BUSINESS", "utilities", "Comcast"), ("PG&E", "utilities", "PG&E"),
             ("STAPLES 0442", "office", "Staples"), ("TST* THE PARLOUR", "meals", "The Parlour"), ("PP*EVENTBRITE", "marketing", "Eventbrite")]
PRODUCTS = {  # industry -> (name, sku, unit price)
    "hvac": [("Run capacitor 45/5 440V", "CAP-45-5-440", 38.50), ("Condenser fan motor 1/4HP", "MTR-COND-14HP", 289.00),
             ("Contactor 40A 24V", "CNT-40A-24V", 42.00), ("Filter 16x25x1", "FLT-16x25x1", 6.75), ("R-410A 25lb", "REF-410A-25", 210.00),
             ("Thermostat WiFi", "TST-WIFI", 149.00), ("Igniter HSI 80V", "IGN-HSI-80V", 31.20), ("Disconnect 60A NF", "DISC-60A-NF", 24.90)],
    "retail": [("Trail Jacket M", "TJ-M-BLU", 129.00), ("Trail Jacket L", "TJ-L-BLU", 129.00), ("Wool Sock 3pk", "WS-3PK", 24.00),
               ("Water Bottle 1L", "WB-1L", 32.00), ("Headlamp 300lm", "HL-300", 45.00), ("Camp Stove", "CS-01", 89.00),
               ("Trekking Pole pair", "TP-PR", 79.00), ("Dry Bag 20L", "DB-20", 29.00), ("Map Case", "MC-01", 14.00)],
    "food": [("Sourdough Loaf", "BRD-SD", 8.50), ("Baguette", "BRD-BG", 4.25), ("Croissant", "PST-CR", 3.75),
             ("Almond Croissant", "PST-ACR", 4.50), ("Cinnamon Roll", "PST-CN", 4.00), ("Coffee 12oz bag", "COF-12", 16.00),
             ("Sandwich Turkey", "SND-TK", 11.50), ("Soup 16oz", "SOUP-16", 7.00), ("Cookie", "CK-01", 2.75)],
    "software": [("Starter plan monthly", "PLAN-STR-M", 49.00), ("Team plan monthly", "PLAN-TEAM-M", 199.00),
                 ("Business plan monthly", "PLAN-BIZ-M", 499.00), ("Extra seat", "SEAT-1", 15.00), ("Onboarding package", "SVC-ONB", 750.00),
                 ("Priority support annual", "SVC-SUP-A", 1200.00)],
    "trades": [("Service call", "SVC-CALL", 95.00), ("Labor hour", "LAB-HR", 110.00), ("Water heater 50gal", "WH-50", 1180.00),
               ("PEX 1/2in 100ft", "PEX-12-100", 62.00), ("Ball valve 3/4in", "BV-34", 18.50), ("Garbage disposal 1/2HP", "GD-12", 165.00),
               ("Faucet kitchen", "FCT-K", 210.00), ("Sump pump 1/3HP", "SP-13", 240.00)],
}
SERVICES = [("Consulting hour", 175.00), ("Design retainer", 2500.00), ("Monthly bookkeeping", 450.00), ("Website maintenance", 300.00),
            ("Photography half day", 900.00), ("Training workshop", 1800.00), ("Support plan", 250.00), ("Audit", 3200.00)]

# --------------------------------------------------------------------------- randomness helpers

def rng(seed: int) -> random.Random:
    return random.Random(seed)

def pick(r: random.Random, pool, n: int, distinct: bool = True):
    return r.sample(list(pool), n) if distinct else [r.choice(list(pool)) for _ in range(n)]

def person(r: random.Random) -> tuple[str, str]:
    return r.choice(FIRST), r.choice(LAST)

def people(r: random.Random, n: int) -> list[tuple[str, str]]:
    out, seen = [], set()
    while len(out) < n:
        p = person(r)
        if p not in seen:
            seen.add(p); out.append(p)
    return out

def email_for(r: random.Random, first: str, last: str, domain: str | None = None) -> str:
    styles = [f"{first}.{last}", f"{first[0]}{last}", f"{first}{last}{r.randint(1, 99)}", f"{first}_{last}", f"{last}.{first}"]
    return f"{r.choice(styles)}@{domain or r.choice(EMAIL_DOMAINS)}".lower()

def address(r: random.Random) -> tuple[str, str, str, str]:
    city, st, z = r.choice(CITIES)
    line = f"{r.randint(12, 9899)} {r.choice(STREETS)}"
    if r.random() < 0.2:
        line += f" {r.choice(['Suite', 'Ste', 'Unit', '#', 'Apt'])} {r.randint(1, 450)}"
    return line, city, st, z

def phone_digits(r: random.Random) -> str:
    return f"{r.choice([206, 303, 415, 512, 608, 617, 720, 802, 919, 971])}555{r.randint(100, 999):03d}{r.randint(0, 9)}"

def money(r: random.Random, lo: float, hi: float, cents: bool = True) -> float:
    v = r.uniform(lo, hi)
    return round(v, 2) if cents else float(round(v))

def code(r: random.Random, n: int, alphabet: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789") -> str:
    return "".join(r.choice(alphabet) for _ in range(n))

def day_in(r: random.Random, start: date, end: date, weekday_only: bool = False) -> date:
    while True:
        d = start + timedelta(days=r.randint(0, (end - start).days))
        if not weekday_only or d.weekday() < 5:
            return d

# --------------------------------------------------------------------------- messiness (the traps' raw material)

PHONE_STYLES = ["({a}) {b}-{c}", "{a}.{b}.{c}", "+1 {a} {b} {c}", "{a}-{b}-{c}", "{a}{b}{c}", "1-{a}-{b}-{c}", "+1 ({a}) {b}-{c}"]

def phone_variant(digits10: str, style: int) -> str:
    a, b, c = digits10[:3], digits10[3:6], digits10[6:]
    return PHONE_STYLES[style % len(PHONE_STYLES)].format(a=a, b=b, c=c)

DATE_STYLES = ["%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y", "%B %d, %Y", "%m/%d/%y", "%d.%m.%Y", "%b %d %Y"]

def date_variant(d: date, style: int) -> str:
    """style 5 is day-first (European); use it only where the file says so or where the trap intends ambiguity."""
    return d.strftime(DATE_STYLES[style % len(DATE_STYLES)])

def money_str(x: float, style: int = 0) -> str:
    """0 "1,240.00"  1 "$1,240.00"  2 "1240.00"  3 "1240"  4 "1,240.00 USD"  5 "(1,240.00)" for negatives  6 "$ 1,240.00"  7 "-1,240.00" """
    neg = x < 0; a = abs(x)
    s = {0: f"{a:,.2f}", 1: f"${a:,.2f}", 2: f"{a:.2f}", 3: f"{a:.0f}", 4: f"{a:,.2f} USD", 5: f"{a:,.2f}", 6: f"$ {a:,.2f}", 7: f"{a:,.2f}"}[style % 8]
    if neg:
        return f"({s})" if style % 8 in (5, 1, 6) else f"-{s}"
    return s

def eu_money_str(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def name_noise(r: random.Random, s: str) -> str:
    k = r.random()
    if k < 0.10: return s.upper()
    if k < 0.16: return s.lower()
    if k < 0.28: return f"  {s}" if r.random() < 0.5 else f"{s}  "
    if k < 0.34: return s.replace(" ", "  ", 1)
    return s

def email_case_noise(r: random.Random, e: str) -> str:
    k = r.random()
    if k < 0.4: return e.upper()
    if k < 0.7: return e.capitalize()
    return e + " " if r.random() < 0.5 else " " + e

def with_bom_crlf(text: str, bom: bool = True, crlf: bool = True) -> bytes:
    t = text.replace("\n", "\r\n") if crlf else text
    return ("﻿" + t).encode("utf-8") if bom else t.encode("utf-8")

# --------------------------------------------------------------------------- writers

def ensure_clean(*dirs: str) -> None:
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True); os.makedirs(d, exist_ok=True)

def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def write_bytes(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

def write_csv(path: str, header: list[str] | None, rows: list[list], delimiter: str = ",", bom: bool = False,
              crlf: bool = False, preamble: list[str] | None = None, quote_all: bool = False) -> None:
    """preamble: junk lines before the header (report title, export date, blank line). Deterministic."""
    buf = io.StringIO()
    for line in preamble or []:
        buf.write(line + "\n")
    w = csv.writer(buf, delimiter=delimiter, quoting=csv.QUOTE_ALL if quote_all else csv.QUOTE_MINIMAL, lineterminator="\n")
    if header: w.writerow(header)
    for row in rows: w.writerow(["" if v is None else v for v in row])
    write_bytes(path, with_bom_crlf(buf.getvalue(), bom=bom, crlf=crlf))

def read_csv(path: str) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]

def freeze_zip(path: str) -> None:
    """Rewrite a zip (xlsx/docx) with fixed timestamps and sorted entries so identical content is identical bytes."""
    with zipfile.ZipFile(path) as zin:
        items = sorted((zi.filename, zin.read(zi.filename)) for zi in zin.infolist())
    # openpyxl stamps the wall clock into docProps/core.xml at save time; pin every W3CDTF timestamp there.
    items = [(n, re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:)", rb"\g<1>2026-01-15T09:00:00Z\g<2>", d)
              if n == "docProps/core.xml" else d) for n, d in items]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items:
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(zi, data)
    write_bytes(path, buf.getvalue())

def write_xlsx(path: str, sheets: dict[str, dict], creator: str = "Export") -> None:
    """sheets: {sheet_name: {"preamble": [[cells]...], "header": [...], "rows": [[...]...],
                            "number_formats": {col_letter: "0.00"}, "widths": {col_letter: 14},
                            "merged_title": "Text" (merged across header width on row 1), "freeze": "A2",
                            "bold_header": True, "formulas_ok": True}}
    Cells that are Python date/datetime become real dates; strings stay strings (so "$1,240.00" is a text trap).
    Strings starting with '=' are written as formulas."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook(); wb.remove(wb.active)
    for name, spec in sheets.items():
        ws = wb.create_sheet(title=name[:31])
        row_i = 1
        if spec.get("merged_title"):
            width = max(len(spec.get("header") or []), 1)
            ws.cell(row=1, column=1, value=spec["merged_title"]).font = Font(bold=True, size=13)
            if width > 1: ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
            row_i = 2
        for pre in spec.get("preamble", []):
            for j, v in enumerate(pre, 1):
                if v is not None and v != "": ws.cell(row=row_i, column=j, value=v)
            row_i += 1
        if spec.get("header"):
            for j, h in enumerate(spec["header"], 1):
                c = ws.cell(row=row_i, column=j, value=h)
                if spec.get("bold_header", True): c.font = Font(bold=True)
            row_i += 1
        for row in spec.get("rows", []):
            for j, v in enumerate(row, 1):
                if v is None or v == "": continue
                c = ws.cell(row=row_i, column=j, value=v)
                if isinstance(v, (date, datetime)): c.number_format = "yyyy-mm-dd"
            row_i += 1
        for col_letter, fmt in (spec.get("number_formats") or {}).items():
            for cell in ws[col_letter]:
                if cell.row > 1 and isinstance(cell.value, (int, float)): cell.number_format = fmt
        for col_letter, w in (spec.get("widths") or {}).items():
            ws.column_dimensions[col_letter].width = w
        if spec.get("freeze"): ws.freeze_panes = spec["freeze"]
    fixed = datetime(2026, 1, 15, 9, 0, 0)
    wb.properties.created = fixed; wb.properties.modified = fixed
    wb.properties.creator = creator; wb.properties.lastModifiedBy = creator
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wb.save(path); freeze_zip(path)

def read_xlsx_rows(path: str, sheet: str | None = None) -> list[list]:
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb.active
    return [list(r) for r in ws.iter_rows(values_only=True)]

def write_email_thread(path: str, messages: list[dict]) -> None:
    """messages: [{"from": "Sarah <sarah@x.com>", "to": "...", "date": "Tue, 9 Sep 2026 08:12", "subject": "...", "body": "..."}]
    Rendered oldest first, like a forwarded thread pasted into a text file; later messages quote nothing (keeps it readable)."""
    parts = []
    for m in messages:
        parts.append(f"From: {m['from']}\nTo: {m['to']}\nDate: {m['date']}\nSubject: {m['subject']}\n\n{m['body'].rstrip()}\n")
    write_text(path, "\n-----Original Message-----\n\n".join(parts))

def write_sqlite(path: str, tables: dict[str, tuple[list[str], list[list]]]) -> None:
    """tables: {name: (columns, rows)}. Column types are TEXT unless every value is int/float."""
    if os.path.exists(path): os.remove(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path)
    for name, (cols, rows) in tables.items():
        types = []
        for j in range(len(cols)):
            vals = [r[j] for r in rows if r[j] is not None and r[j] != ""]
            types.append("REAL" if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals) else "TEXT")
        con.execute(f"CREATE TABLE {name} ({', '.join(f'{c} {t}' for c, t in zip(cols, types))})")
        con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' for _ in cols)})", [[None if v == "" else v for v in r] for r in rows])
    con.commit(); con.close()

def _rl_invariant():
    from reportlab import rl_config
    rl_config.invariant = 1

def write_pdf_document(path: str, blocks: list, pagesize: str = "letter", font: str = "Helvetica", base_size: float = 10) -> None:
    """A deterministic text PDF. blocks is a list of:
        ("title", text) ("h", text) ("p", text) ("kv", [(k, v), ...]) ("table", [header, row, row...], {"col_widths": [..], "align_right": [idx...]})
        ("spacer", height_pt) ("hr", None) ("right", text) ("small", text)
    Layout is intentionally varied by the caller (fonts, order of blocks), so extraction cannot rely on one template.
    Text is reportlab Paragraph markup: escape a literal & < > as &amp; &lt; &gt; (html.escape does it)."""
    _rl_invariant()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, LETTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    ps = LETTER if pagesize == "letter" else A4
    bold = {"Times-Roman": "Times-Bold", "Times": "Times-Bold", "Courier": "Courier-Bold", "Helvetica": "Helvetica-Bold"}.get(font, font + "-Bold")
    doc = SimpleDocTemplate(path, pagesize=ps, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="", author="", subject="", creator="", producer="")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=base_size + 8, leading=base_size + 11, spaceAfter=6),
        "h": ParagraphStyle("h", fontName=bold, fontSize=base_size + 2, leading=base_size + 5, spaceBefore=6, spaceAfter=3),
        "p": ParagraphStyle("p", fontName=font, fontSize=base_size, leading=base_size + 3.5),
        "small": ParagraphStyle("s", fontName=font, fontSize=base_size - 2, leading=base_size + 1, textColor=colors.HexColor("#555555")),
        "right": ParagraphStyle("r", fontName=font, fontSize=base_size, leading=base_size + 3.5, alignment=TA_RIGHT),
    }
    story = []
    for kind, payload, *opts in blocks:
        o = opts[0] if opts else {}
        if kind in ("title", "h", "p", "small", "right"):
            story.append(Paragraph(str(payload).replace("\n", "<br/>"), st[kind]))
        elif kind == "spacer":
            story.append(Spacer(1, payload))
        elif kind == "hr":
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#888888"), spaceBefore=4, spaceAfter=4))
        elif kind == "kv":
            t = Table([[Paragraph(f"<b>{k}</b>", st["p"]), Paragraph(str(v), st["p"])] for k, v in payload], colWidths=o.get("col_widths", [45 * mm, 110 * mm]))
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 1)]))
            story.append(t)
        elif kind == "table":
            data = [[Paragraph(str(c), st["p"]) for c in row] for row in payload]
            t = Table(data, colWidths=o.get("col_widths"), repeatRows=1)
            style = [("FONTNAME", (0, 0), (-1, 0), bold), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                     ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2)]
            if o.get("grid"): style.append(("GRID", (0, 0), (-1, -1), 0.3, colors.grey))
            if o.get("shade_header"): style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")))
            t.setStyle(TableStyle(style))
            story.append(t)
    doc.build(story)

def write_scan_pdf(path: str, lines: list[str], width: int = 1240, height: int = 1754, font_size: int = 30,
                   skew_deg: float = 0.6, noise: int = 400, seed: int = 0) -> None:
    """An image-only PDF that looks like a phone scan of a printed page: OCR is the only way to read it.
    lines are drawn top-down in a monospace-ish default font; blank strings leave a gap. Deterministic for a seed."""
    from PIL import Image, ImageDraw, ImageFont
    r = random.Random(seed)
    img = Image.new("L", (width, height), 245)
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New.ttf", font_size)
    except Exception:
        try: f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
        except Exception: f = ImageFont.load_default()
    y = 110
    for ln in lines:
        if ln: d.text((110, y), ln, fill=25, font=f)
        y += int(font_size * 1.45)
    for _ in range(noise):  # dust
        x, yy = r.randint(0, width - 1), r.randint(0, height - 1)
        d.point((x, yy), fill=r.randint(120, 200))
    img = img.rotate(skew_deg, resample=Image.BICUBIC, fillcolor=240)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img.save(path, "PDF", resolution=150.0)
    # Pillow stamps the wall clock into /CreationDate and /ModDate; pin them (same length keeps the xref valid).
    data = open(path, "rb").read()
    data = re.sub(rb"(/(?:Creation|Mod)Date \(D:)\d{14}Z\)", rb"\g<1>20260115090000Z)", data)
    write_bytes(path, data)

def write_json(path: str, obj) -> None:
    write_text(path, json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")

# --------------------------------------------------------------------------- task plumbing

def task_dirs(here: str) -> tuple[str, str, str]:
    """(workspace, reference, reference_solution) under the task folder, wiped clean."""
    ws, ref, sol = (os.path.join(here, d) for d in ("workspace", "reference", "reference_solution"))
    ensure_clean(ws, ref, sol)
    return ws, ref, sol

def write_task_yaml(here: str, spec: dict) -> None:
    """spec keys in order: id, track, category, title, ask, followup, timeout_s, traps, checks. Block style for ask."""
    import yaml

    class Dumper(yaml.SafeDumper):
        pass

    def str_presenter(dumper, data):
        if "\n" in data or len(data) > 90:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)
    Dumper.add_representer(str, str_presenter)
    order = ["id", "track", "category", "title", "ask", "followup", "timeout_s", "traps", "checks"]
    ordered = {k: spec[k] for k in order if k in spec}
    ordered.update({k: v for k, v in spec.items() if k not in ordered})
    write_text(os.path.join(here, "task.yaml"), yaml.dump(ordered, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=110))

def argparse_seed(default: int = 0) -> int:
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=default)
    return ap.parse_args().seed

__all__ = [n for n in dir() if not n.startswith("_") and n not in ("annotations", "csv", "io", "json", "os", "random", "re", "shutil", "sqlite3", "zipfile")]
