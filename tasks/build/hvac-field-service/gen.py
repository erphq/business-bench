#!/usr/bin/env python3
"""Deterministic seed generator for the hvac-field-service build task.

    python gen.py [--seed N]

Writes:
  seed/customers.csv      ~120 rows exported from an old system (messy on purpose)
  seed/parts.csv          60 parts with currency strings, padded SKUs, one bad on-hand
  reference/counts.json   true counts after dedupe plus the constants checklist.md cites, including the
                          dashboard and baseline figures for items 21 to 31 (added 13 September 2026)

Seed 0 is the canonical public variant (checklist.md quotes its numbers). Other seeds
re-roll names, phones, dates, and jitter part prices for sealed variants; counts.json is
always recomputed from the rows actually written, so re-derive checklist numbers from it.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED_DIR = HERE / "seed"
REF_DIR = HERE / "reference"

# ----------------------------------------------------------------------------- pools

FIRST = [
    "Marlene", "Robert", "Angela", "Terrence", "Beverly", "Kwame", "Patricia", "Luis",
    "Deborah", "Hector", "Carol", "Jamal", "Sandra", "Dmitri", "Linda", "Raymond",
    "Yolanda", "Frank", "Nadia", "Gerald", "Theresa", "Omar", "Janet", "Curtis",
    "Rosa", "Douglas", "Gloria", "Vincent", "Brenda", "Anthony", "Sharon", "Leon",
    "Diane", "Marcus", "Cheryl", "Ernest", "Kathleen", "Felix", "Judith", "Warren",
    "Lorraine", "Ivan", "Pamela", "Reggie", "Denise", "Harold", "Tamika", "Stanley",
    "Joyce", "Ahmed", "Ruth", "Clifford", "Sonia", "Eugene", "Maureen", "Darnell",
    "Phyllis", "Nathan", "Irene", "Wesley", "Bonnie", "Salvador", "Elaine", "Gus",
]
LAST = [
    "Okafor", "Delgado", "Whitfield", "Brandt", "Kowalski", "Mensah", "Sullivan",
    "Ortega", "Tanaka", "Reynolds", "Petrov", "Abernathy", "Chandler", "Nguyen",
    "Fitzgerald", "Barnes", "Castillo", "Lindqvist", "Hargrove", "Osei", "Duffy",
    "Vasquez", "Kessler", "McBride", "Alvarado", "Pruitt", "Schaefer", "Iyer",
    "Womack", "Grimes", "Haddad", "Beaumont", "Tolliver", "Ruiz", "Kaminski",
    "Ferrell", "Oyelaran", "Stroud", "Baptiste", "Novak", "Gaines", "Hollis",
    "Pacheco", "Rademacher", "Yates", "Ibarra", "Coyle", "Vandenberg", "Sprague",
    "Ashworth", "Delacroix", "Mattson", "Quintero", "Hensley", "Boateng", "Larkin",
    "Winslow", "Farrukh", "Eberhardt", "Cortez", "Muldoon", "Sikorski", "Trent",
]
BUSINESSES = [
    ("Northgate Apartments LLC", "northgateapartmentsoh.com"),
    ("Maple Street Dental", "maplestreetdentaloh.com"),
    ("Riverside Community Church", "riversidecc-dayton.org"),
    ("Kettering Family Practice", "ketteringfamilypractice.net"),
    ("Brookside Veterinary Clinic", "brooksidevetoh.com"),
    ("Stonebridge Storage", "stonebridgestorageoh.com"),
    ("Miami Valley Auto Body", "mvautobodyoh.com"),
    ("Wright View Diner", "wrightviewdiner.com"),
    ("Beavercreek Montessori", "beavercreekmontessori.org"),
    ("Pine Ridge Senior Living", "pineridgeseniorliving-oh.com"),
    ("Oakwood Dry Cleaners", "oakwooddrycleanersoh.com"),
    ("Fairborn Fitness 24", "fairbornfitness24.com"),
    ("The Corner Bakery on Main", "cornerbakerymain.com"),
    ("Sunrise Daycare Center", "sunrisedaycare-oh.org"),
    ("Great Miami Brewing Co.", "greatmiamibrewing.com"),
    ("Wilmington Pike Plaza Management", "wpplazamgmt.com"),
    ("Bella Vista Pizzeria", "bellavistapizzaoh.com"),
    ("Trinity Lutheran School", "trinitylutheranschool-oh.org"),
    ("Grange Hall Event Center", "grangehallevents.com"),
    ("Valley Orthodontics", "valleyorthooh.com"),
    ("Salem Avenue Laundromat", "salemavelaundry.com"),
    ("Heritage Funeral Home", "heritagefuneral-oh.com"),
    ("Miamisburg Fraternal Hall", "miamisburgfraternalhall.org"),
    ("Xenia Feed & Seed", "xeniafeedandseed.com"),
    ("Springboro Self Storage", "springboroselfstorage.com"),
    ("Far Hills Veterinary", "farhillsvet.com"),
    ("Lakeview Office Park", "lakeviewofficepark-oh.com"),
    ("Dixie Highway Tire & Lube", "dixietireandlube.com"),
]
STREETS = [
    "Maple St", "Oak Ave", "Far Hills Ave", "Wilmington Pike", "Salem Ave", "Main St",
    "N Dixie Dr", "Woodman Dr", "Stroop Rd", "Dorothy Ln", "Shroyer Rd", "Patterson Rd",
    "E 3rd St", "Brown St", "Linden Ave", "Smithville Rd", "Needmore Rd", "Wayne Ave",
    "Hempstead Station Dr", "Bigger Rd", "Whipp Rd", "Rahn Rd", "Alex Bell Rd",
    "Spring Valley Pike", "Clyo Rd", "Yankee St", "Grange Hall Rd", "Dayton-Xenia Rd",
    "Fairfield Rd", "N Fairfield Rd", "Kemp Rd", "Indian Ripple Rd", "Beaver Valley Rd",
    "Brandt Pike", "Chambersburg Rd", "Old Troy Pike", "Taylorsville Rd", "Central Ave",
    "Linden Ave", "Byers Rd", "Lyons Rd", "Miamisburg-Centerville Rd", "Austin Blvd",
]
CITIES = [
    ("Dayton", "OH", "45402"), ("Dayton", "OH", "45410"), ("Dayton", "OH", "45420"),
    ("Kettering", "OH", "45429"), ("Kettering", "OH", "45440"), ("Beavercreek", "OH", "45431"),
    ("Centerville", "OH", "45459"), ("Huber Heights", "OH", "45424"), ("Miamisburg", "OH", "45342"),
    ("Springboro", "OH", "45066"), ("Xenia", "OH", "45385"), ("Fairborn", "OH", "45324"),
    ("Vandalia", "OH", "45377"), ("Oakwood", "OH", "45419"), ("West Carrollton", "OH", "45449"),
]
RES_UNITS = ["Apt 4B", "Apt 2", "Unit 12", "#3", "Apt 1A", "Unit 7", "Apt 10C", "#14", "Lot 22"]
COM_UNITS = ["Ste 200", "Suite 110", "Ste 305", "Bldg C", "Unit B", "Ste 12", "Suite 4"]
PROVIDERS = ["gmail.com"] * 5 + ["yahoo.com"] * 2 + [
    "outlook.com", "att.net", "sbcglobal.net", "hotmail.com", "icloud.com", "woh.rr.com",
]
REPS = ["Dana", "Marcus", "Priya"]
REP_SPLIT = {"Dana": 58, "Marcus": 37, "Priya": 17}  # sums to 112 unique customers
NOTES = [
    "", "", "", "", "", "", "",
    "Gate code 4412", "Dog in backyard - call first", "Prefers text", "Furnace replaced 2024",
    "Net 30", "Call before arriving", "Key under mat (back door)", "Maintenance plan - spring/fall",
    "Unit on roof, needs ladder", "Billing goes to property manager", "Spanish speaking",
    "Do not schedule before 10am", "Owner travels - tenant is contact",
    "Past due balance - collect before work", "Elderly - allow extra time",
    "2 systems (up/down)", "Heat pump + gas backup", "Access through alley",
]

N_RESIDENTIAL = 84
N_COMMERCIAL = 28
N_UNIQUE = N_RESIDENTIAL + N_COMMERCIAL  # 112
N_EXACT_DUPES = 5
N_NEAR_DUPES = 3
N_BLANK_EMAIL = 6
N_ALLCAPS = 4

CUSTOMER_COLUMNS = ["Customer", "Contact", "Phone", "Email", "Service Address", "Rep", "Last Service", "Notes"]
PARTS_COLUMNS = ["SKU", "Description", "Unit Cost", "Sell Price", "On Hand"]

# (sku, description, unit_cost, sell_price, on_hand)
PARTS = [
    ("CAP-45-5-440", "Run capacitor 45/5 MFD 440V dual", 9.80, 38.50, 24),
    ("CAP-35-5-440", "Run capacitor 35/5 MFD 440V dual", 8.90, 36.00, 18),
    ("CAP-40-5-440", "Run capacitor 40/5 MFD 440V dual", 9.20, 37.00, 15),
    ("CAP-5-370", "Run capacitor 5 MFD 370V", 3.10, 19.00, 30),
    ("CAP-7.5-370", "Run capacitor 7.5 MFD 370V", 3.40, 21.00, 22),
    ("CTR-1P-30A", "Contactor 1 pole 30A 24V coil", 11.50, 42.00, 20),
    ("CTR-2P-30A", "Contactor 2 pole 30A 24V coil", 13.75, 48.00, 16),
    ("CTR-2P-40A", "Contactor 2 pole 40A 24V coil", 16.20, 55.00, 9),
    ("MTR-COND-14HP", "Condenser fan motor 1/4 HP 1075 RPM", 118.00, 289.00, 6),
    ("MTR-COND-13HP", "Condenser fan motor 1/3 HP 1075 RPM", 132.00, 315.00, 4),
    ("MTR-BLW-12HP", "Blower motor 1/2 HP PSC 115V", 164.00, 389.00, 5),
    ("MTR-BLW-34HP", "Blower motor 3/4 HP PSC 115V", 189.00, 445.00, 3),
    ("MTR-ECM-12HP", "ECM blower motor 1/2 HP with module", 412.00, 895.00, 2),
    ("MTR-IND-80", "Draft inducer motor assembly 80% furnace", 148.00, 349.00, 5),
    ("MTR-IND-90", "Draft inducer motor assembly 90% furnace", 176.00, 399.00, 3),
    ("IGN-HSI-80V", "Hot surface igniter 80V silicon nitride", 22.00, 79.00, 14),
    ("IGN-HSI-120V", "Hot surface igniter 120V silicon carbide", 18.50, 69.00, 11),
    ("FLM-SENSOR", "Flame sensor universal", 6.40, 45.00, 26),
    ("PSW-SNGL", "Pressure switch single -0.60 WC", 19.80, 74.00, 12),
    ("PSW-DUAL", "Pressure switch dual stage", 34.00, 118.00, 6),
    ("LSW-ROLLOUT", "Rollout limit switch 350F", 8.20, 44.00, 15),
    ("LSW-HIGH-L190", "High limit switch L190", 12.40, 58.00, 9),
    ("GV-24V-1STG", "Gas valve 24V single stage NG", 74.00, 219.00, 5),
    ("GV-24V-2STG", "Gas valve 24V two stage NG", 98.00, 279.00, 3),
    ("CB-FURN-UNIV", "Furnace control board universal", 88.00, 249.00, 6),
    ("CB-HP-DEFROST", "Heat pump defrost control board", 64.00, 189.00, 4),
    ("XFMR-40VA", "Transformer 40VA 120/24V", 14.60, 52.00, 17),
    ("XFMR-75VA", "Transformer 75VA 120/24V", 22.30, 72.00, 6),
    ("RLY-DPDT-24V", "Relay DPDT 24V coil", 7.10, 29.00, 21),
    ("TST-PRO-1", "Thermostat programmable 1H/1C", 34.00, 129.00, 12),
    ("TST-PRO-2", "Thermostat programmable 2H/2C", 48.00, 169.00, 7),
    ("TST-WIFI", "Thermostat Wi-Fi color touchscreen", 129.00, 299.00, 5),
    ("TST-NONPRO", "Thermostat non-programmable 1H/1C", 19.00, 79.00, 15),
    ("REF-410A-25", "Refrigerant R-410A 25 lb cylinder", 210.00, 640.00, 4),
    ("REF-22-30", "Refrigerant R-22 30 lb cylinder (reclaimed)", 690.00, 1450.00, 1),
    ("REF-454B-20", "Refrigerant R-454B 20 lb cylinder", 285.00, 795.00, 2),
    ("FLT-16x25x1", "Pleated filter 16x25x1 MERV 8 (case of 12)", 28.00, 58.00, -3),
    ("FLT-20x25x1", "Pleated filter 20x25x1 MERV 8 (case of 12)", 30.00, 62.00, 8),
    ("FLT-16x20x1", "Pleated filter 16x20x1 MERV 8 (case of 12)", 26.00, 54.00, 11),
    ("FLT-20x25x4", "Media filter 20x25x4 MERV 11", 21.00, 49.00, 14),
    ("FLT-16x25x4", "Media filter 16x25x4 MERV 11", 20.00, 47.00, 9),
    ("TXV-3T-410A", "TXV valve 3 ton R-410A", 62.00, 179.00, 4),
    ("TXV-2T-410A", "TXV valve 2 ton R-410A", 58.00, 169.00, 3),
    ("CMP-3T-R410A", "Scroll compressor 3 ton R-410A", 1240.00, 2480.00, 2),
    ("CMP-2T-R410A", "Scroll compressor 2 ton R-410A", 980.00, 1960.00, 1),
    ("COIL-EVAP-3T", "Evaporator coil 3 ton cased", 640.00, 1380.00, 2),
    ("COIL-EVAP-2T", "Evaporator coil 2 ton cased", 560.00, 1220.00, 1),
    ("PMP-COND-115", "Condensate pump 115V", 31.00, 98.00, 9),
    ("FSW-FLOAT", "Condensate float safety switch", 9.40, 39.00, 19),
    ("DRN-PVC-34-10", "PVC drain line 3/4 in x 10 ft", 4.10, 14.00, 28),
    ("DISC-60A-NF", "Disconnect box 60A non-fused", 12.90, 44.00, 12),
    ("WHIP-6FT", "Whip 6 ft liquid-tight with fittings", 10.20, 34.00, 16),
    ("LS-38-34-25", "Line set 3/8 x 3/4 x 25 ft", 98.00, 245.00, 5),
    ("LS-38-78-30", "Line set 3/8 x 7/8 x 30 ft", 136.00, 329.00, 3),
    ("PAD-36x36", "Equipment pad 36x36x3", 38.00, 89.00, 6),
    ("TAPE-FOIL-3", "Foil tape 3 in x 50 yd", 9.60, 24.00, 22),
    ("MASTIC-1GAL", "Duct mastic 1 gal", 17.00, 42.00, 7),
    ("UV-BULB-24", "UV lamp replacement bulb 24 in", 44.00, 129.00, 4),
    ("HUM-PAD-35", "Humidifier water panel #35", 8.80, 32.00, 13),
    ("SURGE-AC-1P", "Surge protector for condenser 1 phase", 41.00, 139.00, 6),
]
CURRENCY_STRING_SKUS = [
    "MTR-ECM-12HP", "TST-WIFI", "REF-410A-25", "REF-22-30", "REF-454B-20",
    "CMP-3T-R410A", "CMP-2T-R410A", "COIL-EVAP-3T", "COIL-EVAP-2T", "LS-38-34-25",
]
TRAILING_SPACE_SKUS = ["IGN-HSI-80V", "DISC-60A-NF"]
NEGATIVE_ON_HAND_SKU = "FLT-16x25x1"

# constants the checklist's invoice and on-hand items are built from
INVOICE_LINES = [("CAP-45-5-440", 2), ("MTR-COND-14HP", 1)]
LABOR_HOURS = 2.5
LABOR_RATE = 95.00
ON_HAND_CHECK = ("CAP-45-5-440", 2)

# ----------------------------------------------------------------------------- helpers


def fmt_phone(area: str, line: str, style: int) -> str:
    b, c = line[:3], line[3:]
    return [
        f"({area}) {b}-{c}",
        f"{area}-{b}-{c}",
        f"{area}.{b}.{c}",
        f"{area}{b}{c}",
        f"+1 {area} {b} {c}",
        f"{area} {b}-{c}",
    ][style]


def fmt_date(d: date, style: int) -> str:
    return [
        d.isoformat(),
        f"{d.month}/{d.day}/{d.year}",
        f"{d.month:02d}/{d.day:02d}/{d.year % 100:02d}",
        d.strftime("%d-%b-%Y"),
        f"{d.strftime('%B')} {d.day}, {d.year}",
    ][style]


def money_string(v: float) -> str:
    return f"${v:,.2f}"


def case_variant(email: str, rng: random.Random) -> str:
    """Return the same address with different capitalization (never identical)."""
    local, _, domain = email.partition("@")
    options = [
        local.title() + "@" + domain.title(),
        local.upper() + "@" + domain,
        local.capitalize() + "@" + domain,
        local + "@" + domain.upper(),
    ]
    options = [o for o in options if o != email]
    return rng.choice(options)


# ----------------------------------------------------------------------------- customers


def build_customers(rng: random.Random) -> dict:
    # phone pool: fictional 555-01xx block across two area codes -> 200 unique numbers
    phone_pool = [(area, f"555{100 + i:04d}") for area in ("937", "513") for i in range(100)]
    rng.shuffle(phone_pool)

    name_pairs = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(name_pairs)
    res_names = name_pairs[:N_RESIDENTIAL]
    contact_pool = name_pairs[N_RESIDENTIAL:N_RESIDENTIAL + N_COMMERCIAL]

    rep_list = [rep for rep, n in REP_SPLIT.items() for _ in range(n)]
    rng.shuffle(rep_list)

    d0, d1 = date(2024, 1, 5), date(2026, 8, 31)
    span = (d1 - d0).days

    uniques: list[dict] = []
    used_emails: dict[str, int] = {}

    def address(commercial: bool) -> str:
        num = rng.randint(100, 9899)
        street = rng.choice(STREETS)
        city, st, zc = rng.choice(CITIES)
        unit = ""
        if commercial and rng.random() < 0.45:
            unit = " " + rng.choice(COM_UNITS)
        elif not commercial and rng.random() < 0.18:
            unit = " " + rng.choice(RES_UNITS)
        return f"{num} {street}{unit}, {city}, {st} {zc}"

    def last_service() -> str:
        if rng.random() < 0.10:
            return ""
        d = d0 + timedelta(days=rng.randint(0, span))
        return fmt_date(d, rng.randrange(5))

    for i, (first, last) in enumerate(res_names):
        prov = rng.choice(PROVIDERS)
        pattern = rng.randrange(4)
        email = [
            f"{first}.{last}@{prov}",
            f"{first[0]}{last}@{prov}",
            f"{first}{last}{rng.randint(55, 99)}@{prov}",
            f"{last}.{first}@{prov}",
        ][pattern].lower()
        while email in used_emails:
            email = f"{first}.{last}{rng.randint(1, 99)}@{prov}".lower()
        used_emails[email] = 1
        area, line = phone_pool.pop()
        name = f"{first} {last}"
        uniques.append({
            "Customer": name,
            "Contact": name if rng.random() < 0.6 else "",
            "Phone": fmt_phone(area, line, rng.randrange(6)),
            "Email": email,
            "Service Address": address(commercial=False),
            "Rep": rep_list.pop(),
            "Last Service": last_service(),
            "Notes": rng.choice(NOTES),
            "_kind": "residential",
        })

    for (biz, domain), (cf, cl) in zip(BUSINESSES, contact_pool):
        email = rng.choice([f"{cf}@{domain}", f"{cf[0]}{cl}@{domain}", f"office@{domain}", f"{cf}.{cl}@{domain}"]).lower()
        used_emails[email] = 1
        area, line = phone_pool.pop()
        uniques.append({
            "Customer": biz,
            "Contact": f"{cf} {cl}",
            "Phone": fmt_phone(area, line, rng.randrange(6)),
            "Email": email,
            "Service Address": address(commercial=True),
            "Rep": rep_list.pop(),
            "Last Service": last_service(),
            "Notes": rng.choice(NOTES),
            "_kind": "commercial",
        })

    assert len(uniques) == N_UNIQUE and not rep_list

    # pick disjoint roles among the unique residential customers
    res_idx = [i for i, c in enumerate(uniques) if c["_kind"] == "residential"]
    rng.shuffle(res_idx)
    blank_email_idx = res_idx[:N_BLANK_EMAIL]
    allcaps_idx = res_idx[N_BLANK_EMAIL:N_BLANK_EMAIL + N_ALLCAPS]
    newest_idx, second_idx = res_idx[N_BLANK_EMAIL + N_ALLCAPS], res_idx[N_BLANK_EMAIL + N_ALLCAPS + 1]
    reserved = set(res_idx[:N_BLANK_EMAIL + N_ALLCAPS + 2])

    for i in blank_email_idx:
        uniques[i]["Email"] = ""
    for i in allcaps_idx:
        uniques[i]["Customer"] = uniques[i]["Customer"].upper()
        uniques[i]["Contact"] = uniques[i]["Contact"].upper()
    # newest Last Service is ISO so a string sort cannot accidentally rank it first;
    # second newest is US-style, which a string sort *would* rank above the ISO row.
    uniques[newest_idx]["Last Service"] = fmt_date(date(2026, 9, 3), 0)
    uniques[second_idx]["Last Service"] = fmt_date(date(2026, 9, 1), 1)

    # duplicates: exact copies and same-email-different-case copies, drawn from the rest
    dupe_candidates = [i for i in range(N_UNIQUE) if i not in reserved and uniques[i]["Email"]]
    # keep one commercial account among the exact dupes so a business name is a search target
    com_candidates = [i for i in dupe_candidates if uniques[i]["_kind"] == "commercial"]
    exact_idx = [rng.choice(com_candidates)]
    pool = [i for i in dupe_candidates if i not in exact_idx]
    rng.shuffle(pool)
    exact_idx += pool[:N_EXACT_DUPES - 1]
    near_idx = pool[N_EXACT_DUPES - 1:N_EXACT_DUPES - 1 + N_NEAR_DUPES]

    rows: list[dict] = [dict(c, _origin=i, _role="unique") for i, c in enumerate(uniques)]
    for i in exact_idx:
        rows.append(dict(uniques[i], _origin=i, _role="exact_duplicate"))
    for i in near_idx:
        src = uniques[i]
        older = d0 + timedelta(days=rng.randint(0, span // 2))
        rows.append(dict(
            src,
            Contact="",
            Phone=fmt_phone(*_phone_parts(src["Phone"]), (rng.randrange(5) + 1) % 6),
            Email=case_variant(src["Email"], rng),
            **{"Last Service": fmt_date(older, rng.randrange(5))},
            Notes=rng.choice(["", "", "duplicate?", "re-entered by front desk", "see other card"]),
            _origin=i, _role="near_duplicate",
        ))

    rng.shuffle(rows)
    for line_no, r in enumerate(rows, start=2):  # header is line 1
        r["_line"] = line_no

    per_rep = {rep: sum(1 for c in uniques if c["Rep"] == rep) for rep in REPS}
    dupe_groups = []
    for i in exact_idx + near_idx:
        members = [r for r in rows if r["_origin"] == i]
        dupe_groups.append({
            "customer": uniques[i]["Customer"],
            "rep": uniques[i]["Rep"],
            "kind": "exact" if i in exact_idx else "same_email_different_case",
            "emails_as_written": [m["Email"] for m in members],
            "file_lines": sorted(m["_line"] for m in members),
        })

    counts = {
        "file_rows_excluding_header": len(rows),
        "exact_duplicate_rows": N_EXACT_DUPES,
        "same_email_different_case_rows": N_NEAR_DUPES,
        "unique_customers_after_dedupe": N_UNIQUE,
        "dedupe_rule": (
            "Two rows are the same customer when their Email matches after trimming and lowercasing, "
            "or when Email is blank on both and Customer + Service Address match. Blank-email rows are "
            "all distinct customers and must not be collapsed into one."
        ),
        "rows_with_blank_email": N_BLANK_EMAIL,
        "blank_email_customers": sorted(uniques[i]["Customer"] for i in blank_email_idx),
        "all_caps_name_rows": N_ALLCAPS,
        "rows_with_unit_in_address": sum(
            1 for c in uniques if any(u in c["Service Address"] for u in RES_UNITS + COM_UNITS)
        ),
        "rows_with_blank_last_service": sum(1 for r in rows if not r["Last Service"]),
        "per_rep_after_dedupe": per_rep,
        "per_rep_file_rows": {rep: sum(1 for r in rows if r["Rep"] == rep) for rep in REPS},
        "newest_last_service": {
            "customer": uniques[newest_idx]["Customer"],
            "rep": uniques[newest_idx]["Rep"],
            "file_value": uniques[newest_idx]["Last Service"],
            "iso": "2026-09-03",
        },
        "second_newest_last_service": {
            "customer": uniques[second_idx]["Customer"],
            "file_value": uniques[second_idx]["Last Service"],
            "iso": "2026-09-01",
        },
        "duplicate_groups": dupe_groups,
        "search_targets": {
            "exact_duplicate_business": next(g for g in dupe_groups if g["kind"] == "exact" and uniques[exact_idx[0]]["Customer"] == g["customer"])["customer"],
            "same_email_different_case": dupe_groups[N_EXACT_DUPES]["customer"],
        },
    }
    return {"rows": rows, "counts": counts}


def _phone_parts(p: str) -> tuple[str, str]:
    digits = "".join(ch for ch in p if ch.isdigit())
    digits = digits[-10:]
    return digits[:3], digits[3:]


# ----------------------------------------------------------------------------- parts


def build_parts(rng: random.Random, seed: int) -> dict:
    rows = []
    numeric = []
    for sku, desc, cost, sell, on_hand in PARTS:
        if seed != 0:  # sealed variants jitter prices; seed 0 keeps the canonical round numbers
            f = rng.uniform(0.9, 1.1)
            cost = round(cost * f, 2)
            sell = round(sell * f, 2)
        numeric.append((sku, desc, cost, sell, on_hand))
        sku_out = sku + " " if sku in TRAILING_SPACE_SKUS else sku
        if sku in CURRENCY_STRING_SKUS:
            cost_out, sell_out = money_string(cost), money_string(sell)
        else:
            cost_out, sell_out = f"{cost:.2f}", f"{sell:.2f}"
        rows.append({
            "SKU": sku_out, "Description": desc, "Unit Cost": cost_out,
            "Sell Price": sell_out, "On Hand": str(on_hand),
        })

    price = {sku: sell for sku, _, _, sell, _ in numeric}
    on_hand = {sku: oh for sku, _, _, _, oh in numeric}
    max_sku = max(numeric, key=lambda r: r[3])
    assert sum(1 for r in numeric if r[3] == max_sku[3]) == 1, "max sell price must be unique"
    parts_total = round(sum(price[s] * q for s, q in INVOICE_LINES), 2)
    labor_total = round(LABOR_HOURS * LABOR_RATE, 2)

    counts = {
        "file_rows_excluding_header": len(rows),
        "unique_skus_after_trim": len({r["SKU"].strip() for r in rows}),
        "skus_with_trailing_space": [s + " " for s in TRAILING_SPACE_SKUS],
        "currency_string_rows": len(CURRENCY_STRING_SKUS),
        "currency_string_skus": list(CURRENCY_STRING_SKUS),
        "negative_on_hand": {"sku": NEGATIVE_ON_HAND_SKU, "on_hand": on_hand[NEGATIVE_ON_HAND_SKU]},
        "highest_sell_price": {
            "sku": max_sku[0],
            "file_value": money_string(max_sku[3]) if max_sku[0] in CURRENCY_STRING_SKUS else f"{max_sku[3]:.2f}",
            "numeric": max_sku[3],
        },
        "invoice_check": {
            "lines": [{"sku": s, "qty": q, "sell_price": price[s], "line_total": round(price[s] * q, 2)} for s, q in INVOICE_LINES],
            "parts_total": parts_total,
            "labor_hours": LABOR_HOURS,
            "labor_rate": LABOR_RATE,
            "labor_total": labor_total,
            "expected_invoice_total": round(parts_total + labor_total, 2),
        },
        "on_hand_check": {
            "sku": ON_HAND_CHECK[0],
            "before": on_hand[ON_HAND_CHECK[0]],
            "qty_used": ON_HAND_CHECK[1],
            "after": on_hand[ON_HAND_CHECK[0]] - ON_HAND_CHECK[1],
        },
    }
    return {"rows": rows, "counts": counts}


# ----------------------------------------------------------------------------- enterprise baseline (added 13 September 2026)

# The seed exports carry customers and parts only: no jobs and no invoices exist until the app creates them.
IMPORTED_JOBS: list[dict] = []
IMPORTED_INVOICES: list[dict] = []
DASHBOARD_MONTH = "the calendar month in which the tester reads the dashboard"


def baseline_counts(customers: dict, parts: dict) -> tuple[dict, dict]:
    """Figures the enterprise-baseline items 21 to 31 quote. Pure: draws nothing from the rng, so the seed
    files and every figure items 1 to 20 quote stay byte-identical."""
    c, p = customers["counts"], parts["counts"]
    rows = customers["rows"]
    uniques = [r for r in rows if r["_role"] == "unique"]

    def text(r: dict) -> str:
        return " ".join(str(r[col]) for col in CUSTOMER_COLUMNS).lower()

    # search term: a surname from an exact-duplicate group that only customer names contain, chosen so the
    # repeated rows inflate a naive result the most
    best = None
    for g in c["duplicate_groups"]:
        if g["kind"] != "exact":
            continue
        term = g["customer"].split()[-1]
        t = term.lower()
        by_name = [r for r in uniques if t in r["Customer"].lower()]
        anywhere = [r for r in uniques if t in text(r)]
        raw = [r for r in rows if t in text(r)]
        if len(by_name) >= 2 and len(by_name) == len(anywhere):
            gain = len(raw) - len(by_name)
            if best is None or gain > best[0]:
                best = (gain, term, sorted(r["Customer"] for r in by_name), len(raw))
    filter_rep = min(REPS, key=lambda rep: c["per_rep_after_dedupe"][rep])
    open_jobs = sum(1 for j in IMPORTED_JOBS if j.get("status") not in ("closed", "completed", "done"))
    invoiced = round(float(sum(i.get("total", 0.0) for i in IMPORTED_INVOICES)), 2)
    dashboard = {
        "customers": c["unique_customers_after_dedupe"],
        "parts": p["unique_skus_after_trim"],
        "open_jobs_at_import": open_jobs,
        "invoiced_this_month_at_import": invoiced,
        "note": ("The seed has no jobs or invoices, so open jobs and this month's invoiced total start at 0 and 0.00; "
                 "by item 28 they must equal the jobs list's not-closed jobs and the sum of invoices dated in "
                 + DASHBOARD_MONTH + " (items 14 to 19 create jobs; closing jobs in items 16 to 18 creates invoices, 603.50 among them)."),
        "scoped_customers": dict(c["per_rep_after_dedupe"]),
    }
    baseline = {
        "STAFF_ROLE": "Sales rep",
        "VIEWER_ROLE": "Read-only (the bookkeeper)",
        "MAIN_ENTITY": "customer",
        "MAIN_ENTITY_PLURAL": "customers",
        "SCOPE_RULE": "the rep's customers",
        "SCOPE_COUNT": dict(c["per_rep_after_dedupe"]),
        "OUT_OF_SCOPE_EXAMPLES": {"Priya": c["search_targets"]["exact_duplicate_business"],
                                  "Marcus": next(g["customer"] for g in c["duplicate_groups"] if g["rep"] == "Marcus" and g["kind"] == "exact"),
                                  "Dana": c["newest_last_service"]["customer"]},
        "KPI_1": {"name": "customers", "value": dashboard["customers"], "scoped_value": dict(c["per_rep_after_dedupe"])},
        "KPI_2": {"name": "parts", "value": dashboard["parts"]},
        "KPI_3": {"name": "open jobs", "value_at_import": open_jobs},
        "KPI_4": {"name": "invoiced this month", "value_at_import": invoiced},
        "SEARCH_TERM": best[1], "SEARCH_COUNT": len(best[2]), "search_hits": best[2], "search_rows_in_file": best[3],
        "FILTER_FIELD": "Rep", "FILTER_VALUE": filter_rep, "FILTER_COUNT": c["per_rep_after_dedupe"][filter_rep],
        "SORT_FIELD": "Last Service", "SORT_TOP": c["newest_last_service"]["customer"],
        "EXPORT_ROWS": c["unique_customers_after_dedupe"],
        "EXPORT_COLUMNS": ["Customer", "Phone", "Email", "Service Address", "Rep"],
        "REQUIRED_FIELD": "a customer name",
    }
    return dashboard, baseline


# ----------------------------------------------------------------------------- main


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    SEED_DIR.mkdir(exist_ok=True)
    REF_DIR.mkdir(exist_ok=True)

    customers = build_customers(rng)
    parts = build_parts(rng, args.seed)

    write_csv(SEED_DIR / "customers.csv", CUSTOMER_COLUMNS, customers["rows"])
    write_csv(SEED_DIR / "parts.csv", PARTS_COLUMNS, parts["rows"])

    dashboard, baseline = baseline_counts(customers, parts)
    counts = {
        "seed": args.seed,
        "customers": customers["counts"],
        "parts": parts["counts"],
        "dashboard": dashboard,
        "baseline": baseline,
    }
    (REF_DIR / "counts.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")

    c, p = customers["counts"], parts["counts"]
    print(f"customers.csv: {c['file_rows_excluding_header']} rows -> {c['unique_customers_after_dedupe']} unique "
          f"(per rep {c['per_rep_after_dedupe']})")
    print(f"parts.csv: {p['file_rows_excluding_header']} rows; invoice check total "
          f"{p['invoice_check']['expected_invoice_total']:.2f}; on-hand {p['on_hand_check']}")


if __name__ == "__main__":
    main()
