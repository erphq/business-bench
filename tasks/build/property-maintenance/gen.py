#!/usr/bin/env python3
"""Deterministic seed generator for the property-maintenance build task.

    python gen.py [--seed N]

Writes:
  seed/units.csv           unit list for six buildings (building names spelled several ways, re-exported rows)
  seed/tenants.csv         lease roster (re-entered tenants, prefixed unit numbers, money strings, one impossible lease)
  seed/vendors.csv         vendor list (vendors typed twice, mixed insurance-expiry dates, "95/hr" rates)
  seed/work_requests.csv   a year of maintenance requests (re-exported rows, unpadded request numbers, messy statuses)
  reference/counts.json    every figure checklist.md and changes/*.md quote, computed from the ground truth

Seed 0 is the public variant that checklist.md quotes. Other seeds re-roll tenants, dates, amounts, statuses,
and which records play each trap; counts.json is recomputed from the truth, so re-derive checklist numbers from it.
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
AS_OF = date(2026, 9, 12)  # export date; everything in the files is on or before it

# ----------------------------------------------------------------------------- buildings and units

BUILDINGS = [
    {"name": "Harbor View", "manager": "Rosa Delgado", "variants": ["Harbor View Apts"],
     "units": [f"{f}{n:02d}" for f in range(1, 5) for n in range(1, 11)], "beds": (1, 2), "sqft": (640, 1040), "rent": (1650, 2350)},
    {"name": "Elm Court", "manager": "Rosa Delgado", "variants": ["ELM COURT"],
     "units": [f"{w}{n}" for w in "AB" for n in range(1, 13)], "beds": (1, 2), "sqft": (600, 900), "rent": (1350, 1850)},
    {"name": "Northgate Lofts", "manager": "Tom Becker", "variants": ["Northgate Lofts LLC"],
     "units": [f"L{f}{n:02d}" for f in range(1, 5) for n in range(1, 10)], "beds": (0, 1), "sqft": (520, 880), "rent": (1550, 2200)},
    {"name": "Cedar Terrace", "manager": "Tom Becker", "variants": ["Cedar Ter.", "CEDAR TERRACE"],
     "units": [str(n) for n in range(1, 29)], "beds": (2, 3), "sqft": (900, 1250), "rent": (1750, 2400)},
    {"name": "Riverside Commons", "manager": "Aisha Khan", "variants": ["Riverside Cmns"],
     "units": [f"{f}{n:02d}" for f in range(1, 5) for n in range(1, 9)], "beds": (1, 2), "sqft": (700, 1000), "rent": (1450, 1950)},
    {"name": "Maple Row Townhomes", "manager": "Aisha Khan", "variants": ["Maple Row"],
     "units": [str(n) for n in range(1, 19)], "beds": (3, 3), "sqft": (1300, 1600), "rent": (2400, 2900)},
]
BUILDING_NAMES = [b["name"] for b in BUILDINGS]
MANAGER_OF = {b["name"]: b["manager"] for b in BUILDINGS}
RESTRICTED = "Rosa Delgado"
RESTRICTED_BUILDINGS = [b["name"] for b in BUILDINGS if b["manager"] == RESTRICTED]
TEST_BUILDING = "Northgate Lofts"      # where the tester creates records (outside the restricted scope)
PREMIUM_UNIT = ("Harbor View", "410")  # the one 3-bed penthouse: the unique highest rent
N_VACANT = 12
N_UNIT_EXACT_DUPES = 5
N_UNIT_VARIANT_DUPES = 3
N_TENANT_EXACT_DUPES = 3
N_TENANT_CASE_DUPES = 4
N_REQUESTS = 150
FIRST_REQUEST_NO = 300
APPROVAL_THRESHOLD = 1500.00

UNIT_COLUMNS = ["Building", "Unit", "Beds", "Baths", "Sq Ft", "Market Rent"]
TENANT_COLUMNS = ["Tenant", "Email", "Phone", "Building", "Unit", "Lease Start", "Lease End", "Monthly Rent", "Balance Due"]
VENDOR_COLUMNS = ["Vendor", "Trade", "Contact", "Phone", "Email", "Insurance Expires", "Hourly Rate", "W-9 On File"]
REQUEST_COLUMNS = ["Request #", "Submitted", "Building", "Unit", "Tenant", "Category", "Description", "Priority",
                   "Status", "Vendor", "Est. Cost", "Actual Cost", "Completed"]

# ----------------------------------------------------------------------------- vendors

VENDORS = [  # (name, trades, domain)
    ("Apex Plumbing, LLC", ["Plumbing"], "apexplumbingtacoma.com"),
    ("Tideline Plumbing & Drain", ["Plumbing"], "tidelineplumbing.com"),
    ("Rooter Brothers", ["Plumbing"], "rooterbros.com"),
    ("Northwest Pipe Works", ["Plumbing"], "nwpipeworks.com"),
    ("ClearFlow Plumbing", ["Plumbing"], "clearflowplumbing.net"),
    ("Crestline Drain Co.", ["Plumbing"], "crestlinedrain.com"),
    ("Harborside Plumbing", ["Plumbing"], "harborsideplumbing.com"),
    ("All-Trades Maintenance", ["General", "Plumbing"], "alltradesmaint.com"),
    ("Brightline Electric", ["Electrical"], "brightlineelectric.com"),
    ("Volt & Wire Electric", ["Electrical"], "voltandwire.com"),
    ("Cascade Electrical Contractors", ["Electrical"], "cascadeelectrical.com"),
    ("Lumen Electric Co.", ["Electrical"], "lumenelectricco.com"),
    ("Pioneer Electric", ["Electrical"], "pioneerelectricwa.com"),
    ("Ironwood Electrical", ["Electrical"], "ironwoodelectrical.com"),
    ("Comfort Air Heating & Cooling", ["HVAC"], "comfortairhc.com"),
    ("Evergreen HVAC", ["HVAC"], "evergreenhvac.com"),
    ("Polar Mechanical", ["HVAC"], "polarmechanical.com"),
    ("Rainier Climate Control", ["HVAC"], "rainierclimate.com"),
    ("AirRight Services", ["HVAC"], "airrightservices.com"),
    ("Keel Mechanical", ["HVAC"], "keelmechanical.com"),
    ("Appliance Doctor NW", ["Appliance"], "appliancedoctornw.com"),
    ("FixRite Appliance Repair", ["Appliance"], "fixriteappliance.com"),
    ("Sound Appliance Service", ["Appliance"], "soundappliance.com"),
    ("Kitchen Pro Repair", ["Appliance"], "kitchenprorepair.com"),
    ("Whirl Appliance Techs", ["Appliance"], "whirltechs.com"),
    ("Summit Pest Solutions", ["Pest Control"], "summitpest.com"),
    ("Evergreen Pest Co.", ["Pest Control"], "evergreenpestco.com"),
    ("Critter Gone", ["Pest Control"], "crittergone.com"),
    ("Pacific Pest Management", ["Pest Control"], "pacificpestmgmt.com"),
    ("Keyway Locksmiths", ["Locksmith"], "keywaylocksmiths.com"),
    ("Secure Lock & Key", ["Locksmith"], "securelockandkey.com"),
    ("Tacoma Lock Shop", ["Locksmith"], "tacomalockshop.com"),
    ("Fresh Coat Painters", ["Painting"], "freshcoatpainters.com"),
    ("Brush & Roll Painting", ["Painting"], "brushandroll.com"),
    ("Pro Finish Painting", ["Painting"], "profinishpainting.com"),
    ("Colorline Painting", ["Painting"], "colorlinepainting.com"),
    ("Plank & Tile Flooring", ["Flooring"], "plankandtile.com"),
    ("Northwest Carpet Care", ["Flooring"], "nwcarpetcare.com"),
    ("Hardwood Revival", ["Flooring"], "hardwoodrevival.com"),
    ("Top Notch Roofing", ["Roofing"], "topnotchroofingwa.com"),
    ("Rain Guard Gutters", ["Roofing"], "rainguardgutters.com"),
    ("Handy Hank's Home Repair", ["General"], "handyhanks.com"),
    ("Fixit Crew", ["General"], "fixitcrew.com"),
    ("Harbor Handyman Services", ["General", "Painting"], "harborhandyman.com"),
    ("Sunday Repairs", ["General"], "sundayrepairs.com"),
    ("Right Hand Maintenance", ["General"], "righthandmaint.com"),
    ("Cornerstone Property Services", ["General"], "cornerstoneps.com"),
    ("TurnKey Make-Ready", ["General", "Cleaning"], "turnkeymakeready.com"),
    ("Main Street Maintenance", ["General"], "mainstreetmaint.com"),
    ("Clearview Glass", ["Glass"], "clearviewglasswa.com"),
    ("Puget Glass & Screen", ["Glass"], "pugetglass.com"),
    ("Greenway Landscaping", ["Landscaping"], "greenwaylandscaping.com"),
    ("Greenleaf Grounds", ["Landscaping"], "greenleafgrounds.com"),
    ("Cutting Edge Lawn", ["Landscaping"], "cuttingedgelawn.com"),
    ("Spotless Turnover Cleaning", ["Cleaning"], "spotlessturnover.com"),
    ("Bright Home Cleaning", ["Cleaning"], "brighthomecleaning.com"),
    ("Sparkle Pros", ["Cleaning"], "sparklepros.com"),
    ("Tacoma Garage Door", ["Doors"], "tacomagaragedoor.com"),
]
VENDOR_DUPES = [("Apex Plumbing, LLC", "Apex Plumbing LLC"), ("Keyway Locksmiths", "KEYWAY LOCKSMITHS")]
EXPIRED_NAMED = "Summit Pest Solutions"
CURRENT_NAMED = "Evergreen Pest Co."
TRADE_OK_NAMED = "Apex Plumbing, LLC"
TRADE_WRONG_NAMED = "Brightline Electric"
N_EXPIRED = 8

CATEGORY_WEIGHTS = [("Plumbing", 26), ("Appliance", 18), ("HVAC", 14), ("General", 16), ("Electrical", 12),
                    ("Pest Control", 8), ("Locksmith", 6)]
DESCRIPTIONS = {
    "Plumbing": ["Kitchen sink drain slow", "Toilet running constantly", "Leak under bathroom sink", "No hot water",
                 "Shower valve dripping", "Tub drain clogged", "Water heater leaking at base", "Low water pressure in kitchen"],
    "Appliance": ["Dishwasher not draining", "Refrigerator not cooling", "Oven igniter clicking, no flame",
                  "Dishwasher door latch broken", "Washer leaking during spin", "Dryer takes three cycles", "Range hood fan dead"],
    "HVAC": ["No heat in unit", "Thermostat blank", "Baseboard heater not working", "Bathroom exhaust fan loud",
             "AC unit rattling", "Furnace filter overdue"],
    "General": ["Closet door off track", "Blinds broken in bedroom", "Cabinet hinge loose", "Hole in drywall behind door",
                "Window screen torn", "Weatherstripping worn at entry door", "Smoke detector chirping"],
    "Electrical": ["Outlet in bedroom dead", "GFCI keeps tripping", "Hallway light flickering", "Breaker trips when microwave runs",
                   "Porch light out"],
    "Pest Control": ["Ants in kitchen", "Mice in pantry", "Wasp nest by balcony", "Cockroach sighting"],
    "Locksmith": ["Lost key, locked out", "Deadbolt sticking", "Mailbox lock broken", "Rekey after move-out"],
}
COMMON_AREA_DESCRIPTIONS = {
    "Electrical": ["Parking lot light out", "Stairwell light flickering"],
    "General": ["Lobby door closer broken", "Trash room door not latching", "Graffiti on garage wall"],
    "Plumbing": ["Laundry room sink clogged", "Irrigation line leaking"],
    "Pest Control": ["Rodent activity near dumpsters"],
}
COST_RANGE = {"Plumbing": (120, 1400), "Appliance": (90, 900), "HVAC": (150, 2600), "General": (60, 800),
              "Electrical": (110, 1200), "Pest Control": (95, 450), "Locksmith": (65, 300)}
BIGGEST_JOB = {"category": "HVAC", "description": "Replace failed rooftop condenser", "est": 6850.00}
SEARCH_TERM = "dishwasher"

# ----------------------------------------------------------------------------- formatting helpers


def fmt_date(d: date, style: int) -> str:
    return [d.isoformat(), f"{d.month}/{d.day}/{d.year}", d.strftime("%d-%b-%Y"), f"{d.strftime('%b')} {d.day} {d.year}"][style % 4]


def fmt_money(v: float, style: int) -> str:
    return [f"${v:,.2f}", f"{v:.0f}" if v == int(v) else f"{v:.2f}", f"{v:.2f}"][style % 3]


def fmt_balance(v: float, style: int) -> str:
    if v < 0:
        return f"(${-v:,.2f})"
    return [f"${v:,.2f}", f"{v:.2f}"][style % 2]


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def unit_sort_key(u: str):
    digits = "".join(ch for ch in u if ch.isdigit())
    return ("".join(ch for ch in u if not ch.isdigit()), int(digits) if digits else 0)


# ----------------------------------------------------------------------------- generation


def build(seed: int, attempt: int) -> dict:
    rng = random.Random(seed * 1000 + attempt)

    # ---------------- units
    units = []  # truth
    for b in BUILDINGS:
        for u in b["units"]:
            beds = rng.randint(*b["beds"])
            sqft = rng.randrange(b["sqft"][0], b["sqft"][1], 10)
            rent = float(rng.randrange(b["rent"][0], b["rent"][1], 25))
            if (b["name"], u) == PREMIUM_UNIT:
                beds, sqft, rent = 3, 1480, 3150.00
            baths = 1 if beds <= 1 else rng.choice([1, 2]) if beds == 2 else 2
            units.append({"building": b["name"], "unit": u, "beds": beds, "baths": baths, "sqft": sqft, "market_rent": rent})
    unit_rows = []
    for x in units:
        b = next(bb for bb in BUILDINGS if bb["name"] == x["building"])
        name = x["building"] if rng.random() < 0.72 else rng.choice(b["variants"])
        unit_rows.append({"Building": name, "Unit": x["unit"], "Beds": "Studio" if x["beds"] == 0 else str(x["beds"]),
                          "Baths": str(x["baths"]), "Sq Ft": str(x["sqft"]), "Market Rent": fmt_money(x["market_rent"], rng.randrange(3)),
                          "_key": (x["building"], x["unit"])})
    unit_rows.sort(key=lambda r: (r["Building"], unit_sort_key(r["Unit"])))
    dupe_rows = []
    picks = rng.sample(range(len(unit_rows)), N_UNIT_EXACT_DUPES + N_UNIT_VARIANT_DUPES)
    for i in picks[:N_UNIT_EXACT_DUPES]:
        dupe_rows.append(dict(unit_rows[i], _dupe="exact"))
    for i in picks[N_UNIT_EXACT_DUPES:]:
        src = unit_rows[i]
        b = next(bb for bb in BUILDINGS if bb["name"] == src["_key"][0])
        other = [n for n in [b["name"]] + b["variants"] if n != src["Building"]]
        dupe_rows.append(dict(src, Building=rng.choice(other), _dupe="variant_name"))
    rng.shuffle(dupe_rows)
    unit_rows_out = unit_rows + dupe_rows

    # ---------------- tenants
    occupied_pool = [x for x in units if (x["building"], x["unit"]) != PREMIUM_UNIT]
    vacant = rng.sample(occupied_pool, N_VACANT)
    vacant_keys = sorted(((v["building"], v["unit"]) for v in vacant), key=lambda k: (BUILDING_NAMES.index(k[0]), unit_sort_key(k[1])))
    vacant_set = set(vacant_keys)
    if not any(k[0] == "Elm Court" for k in vacant_keys) or not any(k[0] == "Maple Row Townhomes" for k in vacant_keys):
        raise ValueError("need a vacant Elm Court and Maple Row unit")
    occupied = [x for x in units if (x["building"], x["unit"]) not in vacant_set]

    names = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(names)
    tenants = []
    used_emails = set()
    for i, x in enumerate(occupied):
        first, last = names[i]
        domain = rng.choice(EMAIL_DOMAINS)
        style = rng.randrange(4)
        email = [f"{first}.{last}", f"{first[0]}{last}", f"{first}{last}{rng.randint(10, 99)}", f"{last}.{first}"][style].lower() + "@" + domain
        while email in used_emails:
            email = f"{first}.{last}{rng.randint(100, 999)}@{domain}".lower()
        used_emails.add(email)
        start = date(rng.randint(2023, 2026), rng.randint(1, 12), 1)
        if start > date(2026, 8, 1):
            start = date(2026, rng.randint(1, 8), 1)
        end = add_months(start, rng.choice([12, 12, 12, 24])) - timedelta(days=1)
        rent = x["market_rent"] - rng.choice([0, 0, 0, 25, 50])
        tenants.append({"name": f"{first} {last}", "email": email, "phone": f"253555{rng.randint(1000, 9999)}",
                        "building": x["building"], "unit": x["unit"], "lease_start": start, "lease_end": end,
                        "rent": rent, "balance": 0.0, "flag": None})
    # balances: some owe, a few carry a credit (written in parentheses)
    idx = list(range(len(tenants)))
    rng.shuffle(idx)
    owing, credits = idx[:20], idx[20:26]
    reserved = set(idx[:26])
    for i in owing:
        tenants[i]["balance"] = float(rng.choice([35, 75, 125, 250, 480, tenants[i]["rent"]]))
    credit_amounts = [-45.00, -25.00, -60.00, -80.00, -110.00, -150.00]
    for i, amt in zip(credits, credit_amounts):
        tenants[i]["balance"] = amt
    credit_named = tenants[credits[0]]
    # same name, different people: one in Harbor View, one in Riverside Commons
    hv = [i for i in range(len(tenants)) if tenants[i]["building"] == "Harbor View" and i not in reserved and tenants[i]["unit"] != PREMIUM_UNIT[1]]
    rc = [i for i in range(len(tenants)) if tenants[i]["building"] == "Riverside Commons" and i not in reserved]
    a, b_ = rng.choice(hv), rng.choice(rc)
    tenants[b_]["name"] = tenants[a]["name"]
    fa, la = tenants[a]["name"].split(" ")
    tenants[b_]["email"] = f"{fa[0]}{la}{rng.randint(60, 99)}@{rng.choice([d for d in EMAIL_DOMAINS if d not in tenants[a]['email']])}".lower()
    reserved |= {a, b_}
    # impossible lease: end typed a year early, so it falls before the start
    pool = [i for i in range(len(tenants)) if i not in reserved]
    bad = rng.choice(pool)
    reserved.add(bad)
    tb = tenants[bad]
    tb["lease_start"] = date(2026, rng.randint(2, 6), 1)
    tb["lease_end"] = add_months(tb["lease_start"], 12) - timedelta(days=1)
    tb["lease_end"] = date(tb["lease_end"].year - 1, tb["lease_end"].month, tb["lease_end"].day)  # wrong year typed
    tb["flag"] = "lease_end_before_start"

    tenant_rows = []
    for i, t in enumerate(tenants):
        u = t["unit"]
        r = rng.random()
        unit_out = u if r < 0.55 else f"Apt {u}" if r < 0.75 else f"#{u}" if r < 0.9 else f"Unit {u}"
        bname = t["building"]
        if rng.random() < 0.25:
            bname = rng.choice(next(bb for bb in BUILDINGS if bb["name"] == bname)["variants"])
        tenant_rows.append({
            "Tenant": t["name"], "Email": t["email"], "Phone": phone_variant(t["phone"], rng.randrange(7)),
            "Building": bname, "Unit": unit_out,
            "Lease Start": fmt_date(t["lease_start"], rng.randrange(4)), "Lease End": fmt_date(t["lease_end"], rng.randrange(4)),
            "Monthly Rent": fmt_money(t["rent"], rng.randrange(3)), "Balance Due": fmt_balance(t["balance"], rng.randrange(2)),
            "_i": i, "_role": "unique"})
    # the premium unit's rent is written as a currency string so a text sort cannot find it
    prem = next(r for r in tenant_rows if tenants[r["_i"]]["building"] == PREMIUM_UNIT[0] and tenants[r["_i"]]["unit"] == PREMIUM_UNIT[1])
    prem["Monthly Rent"] = fmt_money(tenants[prem["_i"]]["rent"], 0)
    # linked-unit example: a Harbor View tenant whose unit is written with a prefix
    pref = [r for r in tenant_rows if tenants[r["_i"]]["building"] == "Harbor View" and not r["Unit"][0].isdigit()
            and r["_i"] not in reserved]
    if not pref:
        raise ValueError("no prefixed Harbor View unit")
    linked = pref[0]
    reserved.add(linked["_i"])
    dup_pool = [r for r in tenant_rows if r["_i"] not in reserved and tenants[r["_i"]]["balance"] == 0]
    dsel = rng.sample(dup_pool, N_TENANT_EXACT_DUPES + N_TENANT_CASE_DUPES)
    extra = []
    for r in dsel[:N_TENANT_EXACT_DUPES]:
        extra.append(dict(r, _role="exact_duplicate"))
    for r in dsel[N_TENANT_EXACT_DUPES:]:
        t = tenants[r["_i"]]
        e = t["email"]
        local, _, dom = e.partition("@")
        variant = rng.choice([local.upper() + "@" + dom, local.capitalize() + "@" + dom.upper(), e.upper()])
        extra.append(dict(r, Email=variant, Phone=phone_variant(t["phone"], (rng.randrange(6) + 1)),
                          **{"Lease Start": fmt_date(t["lease_start"], rng.randrange(4))}, _role="same_email_different_case"))
    tenant_rows_out = tenant_rows + extra
    rng.shuffle(tenant_rows_out)
    for n, r in enumerate(tenant_rows_out, start=2):
        r["_line"] = n

    # ---------------- vendors
    vend = []
    names_v = [v[0] for v in VENDORS]
    expired_pool = [n for n in names_v if n not in (CURRENT_NAMED, TRADE_OK_NAMED, TRADE_WRONG_NAMED, EXPIRED_NAMED)]
    expired = [EXPIRED_NAMED] + rng.sample(expired_pool, N_EXPIRED - 1)
    for name, trades, domain in VENDORS:
        cf, cl = rng.choice(FIRST), rng.choice(LAST)
        if name in expired:
            ins = date(2025, 9, 30) + timedelta(days=rng.randint(0, 273))
            if name == EXPIRED_NAMED:
                ins = date(2026, 3, 31)
        else:
            ins = date(2027, 1, 31) + timedelta(days=rng.randint(0, 330))
            if name == CURRENT_NAMED:
                ins = date(2027, 6, 30)
        rate = float(rng.choice([65, 75, 85, 95, 110, 125, 140]))
        vend.append({"name": name, "trades": trades, "contact": f"{cf} {cl}", "phone": f"253555{rng.randint(1000, 9999)}",
                     "email": rng.choice([f"office@{domain}", f"{cf.lower()}@{domain}", f"dispatch@{domain}"]),
                     "insurance": ins, "rate": rate, "w9": rng.choice(["Y", "Y", "Yes", "N"])})
    vendor_rows = []
    for v in vend:
        rs = rng.randrange(4)
        vendor_rows.append({
            "Vendor": v["name"], "Trade": "; ".join(v["trades"]) if rng.random() < 0.85 else "; ".join(v["trades"]).lower(),
            "Contact": v["contact"], "Phone": phone_variant(v["phone"], rng.randrange(7)), "Email": v["email"],
            "Insurance Expires": fmt_date(v["insurance"], 1 if v["name"] == EXPIRED_NAMED else rng.randrange(4)),
            "Hourly Rate": [f"${v['rate']:.2f}", f"{v['rate']:.0f}", f"{v['rate']:.0f}/hr", ""][rs],
            "W-9 On File": v["w9"], "_name": v["name"], "_role": "unique"})
    for canon, typed in VENDOR_DUPES:
        src = next(r for r in vendor_rows if r["_name"] == canon)
        v = next(x for x in vend if x["name"] == canon)
        vendor_rows.append(dict(src, Vendor=typed, Phone=phone_variant(v["phone"], rng.randrange(7)),
                                **{"Insurance Expires": fmt_date(v["insurance"], rng.randrange(4))}, _role="name_variant_duplicate"))
    vendor_rows.sort(key=lambda r: r["Vendor"].lower())

    # ---------------- work requests
    def vendors_for(category: str, when: date) -> list[str]:
        return [v["name"] for v in vend if category in v["trades"] and (v["insurance"] >= when)]

    tenant_at = {(t["building"], t["unit"]): t for t in tenants}
    weights = [len(b["units"]) for b in BUILDINGS]
    span = (AS_OF - date(2025, 9, 2)).days
    # request volume grew as tenants learned the portal: more requests in recent months
    days = sorted(int(span * (1 - rng.random() ** 1.5)) for _ in range(N_REQUESTS))
    requests = []
    for k, off in enumerate(days):
        submitted = date(2025, 9, 2) + timedelta(days=off)
        bname = rng.choices(BUILDING_NAMES, weights=weights)[0]
        common = rng.random() < 0.10
        if common:
            category = rng.choice(list(COMMON_AREA_DESCRIPTIONS))
            desc = rng.choice(COMMON_AREA_DESCRIPTIONS[category])
            unit, tenant = "", ""
        else:
            category = rng.choices([c for c, _ in CATEGORY_WEIGHTS], weights=[w for _, w in CATEGORY_WEIGHTS])[0]
            desc = rng.choice(DESCRIPTIONS[category])
            unit = rng.choice(next(b for b in BUILDINGS if b["name"] == bname)["units"])
            t = tenant_at.get((bname, unit))
            tenant = t["name"] if t else ""
        age = (AS_OF - submitted).days
        r = rng.random()
        if age > 90:
            status = "Completed" if r < 0.93 else "Cancelled"
        elif age > 40:
            status = "Completed" if r < 0.82 else "Cancelled" if r < 0.87 else "Waiting on Vendor"
        elif age > 14:
            status = "Completed" if r < 0.42 else "Cancelled" if r < 0.46 else "In Progress" if r < 0.68 else "Waiting on Vendor" if r < 0.86 else "Assigned"
        else:
            status = "New" if r < 0.40 else "Assigned" if r < 0.65 else "In Progress" if r < 0.85 else "Waiting on Vendor" if r < 0.95 else "Completed"
        priority = rng.choices(["Emergency", "High", "Normal", "Low"], weights=[5, 20, 60, 15])[0]
        requests.append({"no": FIRST_REQUEST_NO + k, "submitted": submitted, "building": bname, "unit": unit, "tenant": tenant,
                         "category": category, "description": desc, "priority": priority, "status": status,
                         "vendor": "", "est": None, "actual": None, "completed": None})
    # the one big job: an open HVAC request at Harbor View, estimated far above everything else
    recent_hv = [q for q in requests if q["building"] == "Harbor View" and q["unit"] and (AS_OF - q["submitted"]).days <= 30
                 and q["no"] != 412]
    if not recent_hv:
        raise ValueError("no recent Harbor View request")
    big = rng.choice(recent_hv)
    big.update(category=BIGGEST_JOB["category"], description=BIGGEST_JOB["description"], status="Assigned", priority="High")
    for q in requests:
        if q["status"] != "New":
            opts = vendors_for(q["category"], q["submitted"]) or vendors_for(q["category"], date(2025, 1, 1))
            q["vendor"] = rng.choice(opts)
        if q["status"] not in ("New",) and not (q["status"] == "Cancelled" and rng.random() < 0.5):
            lo, hi = COST_RANGE[q["category"]]
            q["est"] = float(rng.randrange(lo, hi, 5))
        if q["status"] == "Completed":
            q["actual"] = round(q["est"] * rng.uniform(0.8, 1.15), 2)
            q["completed"] = min(AS_OF, q["submitted"] + timedelta(days=rng.randint(0, 21)))
    big["est"] = BIGGEST_JOB["est"]
    big["vendor"] = rng.choice([v for v in vendors_for("HVAC", AS_OF)])

    status_variants = {"Completed": ["Completed", "Completed", "Completed", "complete", "Closed"], "Cancelled": ["Cancelled", "Cancelled", "Canceled"],
                       "New": ["New", "New", "New", "new"], "Assigned": ["Assigned"], "In Progress": ["In Progress", "In Progress", "In progress"],
                       "Waiting on Vendor": ["Waiting on Vendor", "Waiting on Vendor", "Waiting - vendor"]}
    req_rows = []
    for q in requests:
        b = next(bb for bb in BUILDINGS if bb["name"] == q["building"])
        req_rows.append({
            "Request #": f"WR-{q['no']:05d}", "Submitted": fmt_date(q["submitted"], rng.randrange(4)),
            "Building": q["building"] if rng.random() < 0.75 else rng.choice(b["variants"]),
            "Unit": "" if not q["unit"] else (q["unit"] if rng.random() < 0.8 else f"Apt {q['unit']}"),
            "Tenant": q["tenant"], "Category": q["category"], "Description": q["description"], "Priority": q["priority"],
            "Status": rng.choice(status_variants[q["status"]]), "Vendor": q["vendor"],
            "Est. Cost": "" if q["est"] is None else fmt_money(q["est"], rng.randrange(3)),
            "Actual Cost": "" if q["actual"] is None else fmt_money(q["actual"], rng.randrange(3)),
            "Completed": "" if q["completed"] is None else fmt_date(q["completed"], rng.randrange(4)),
            "_no": q["no"], "_role": "unique"})
    big_row = next(r for r in req_rows if r["_no"] == big["no"])
    big_row["Est. Cost"] = fmt_money(big["est"], 0)
    # re-exported rows: two identical copies, and two whose request number lost its padding
    named_dupe_no = 412
    open_nos = {q["no"] for q in requests if q["status"] in OPEN}
    others_open = [r for r in req_rows if r["_no"] not in (named_dupe_no, big["no"]) and r["_no"] in open_nos]
    others_any = [r for r in req_rows if r["_no"] not in (named_dupe_no, big["no"])]
    picks = rng.sample(others_open, 2)
    picks.append(rng.choice([r for r in others_any if r not in picks]))
    extra = [dict(picks[0], _role="exact_duplicate"), dict(picks[1], _role="exact_duplicate")]
    src412 = next(r for r in req_rows if r["_no"] == named_dupe_no)
    extra.append(dict(src412, **{"Request #": str(named_dupe_no)}, _role="unpadded_number"))
    extra.append(dict(picks[2], **{"Request #": f"WR-{picks[2]['_no']}"}, _role="unpadded_number"))
    req_rows_out = list(req_rows)
    for e in extra:
        req_rows_out.insert(rng.randint(0, len(req_rows_out)), e)
    for n, r in enumerate(req_rows_out, start=2):
        r["_line"] = n

    return {"units": units, "unit_rows": unit_rows_out, "vacant_keys": vacant_keys, "tenants": tenants,
            "tenant_rows": tenant_rows_out, "credit_named": credit_named, "same_name": (tenants[a], tenants[b_]),
            "bad_lease": tb, "linked": linked, "vendors": vend, "vendor_rows": vendor_rows, "expired": expired,
            "requests": requests, "req_rows": req_rows_out, "big": big}


OPEN = ("New", "Assigned", "In Progress", "Waiting on Vendor")


def summarize(t: dict) -> dict:
    units, tenants, requests, vend = t["units"], t["tenants"], t["requests"], t["vendors"]
    unit_counts = {b: sum(1 for u in units if u["building"] == b) for b in BUILDING_NAMES}
    tenant_keyed = {(x["building"], x["unit"]): x for x in tenants}
    open_q = [q for q in requests if q["status"] in OPEN]
    by_no = {q["no"]: q for q in requests}

    def label(q):
        return f"WR-{q['no']:05d}"

    # search term: count requests whose exported text mentions it (description is the only field that can)
    search_hits = [q for q in requests if SEARCH_TERM in " ".join([q["description"], q["tenant"], q["vendor"], q["building"], q["category"]]).lower()]
    filter_building = "Cedar Terrace"
    filter_hits = [q for q in requests if q["building"] == filter_building]
    max_est = max((q for q in requests if q["est"] is not None), key=lambda q: q["est"])
    assert sum(1 for q in requests if q["est"] == max_est["est"]) == 1
    # a text sort of the written values (descending) must not find the same request
    rows_unique = [r for r in t["req_rows"] if r["_role"] == "unique" and r["Est. Cost"]]
    text_top = max(rows_unique, key=lambda r: r["Est. Cost"])
    assert text_top["_no"] != max_est["no"], "text sort would pass"
    oos = sorted((q for q in open_q if q["building"] == TEST_BUILDING and q["unit"]), key=lambda q: q["submitted"])[-1]

    in_scope = [q for q in requests if q["building"] in RESTRICTED_BUILDINGS]
    if any(sum(1 for q in open_q if q["building"] == bn) < 2 for bn in BUILDING_NAMES):
        raise ValueError("every building needs at least two open requests")
    if not 22 <= len(open_q) <= 34:
        raise ValueError("open backlog out of range")
    if not SEARCH_TERM or not 3 <= len(search_hits) <= 8:
        raise ValueError("search count out of range")
    aug_completed = [q for q in requests if q["status"] == "Completed" and q["completed"].year == 2026 and q["completed"].month == 8]
    completed = [q for q in requests if q["status"] == "Completed"]
    completed_scoped = [q for q in completed if q["building"] in RESTRICTED_BUILDINGS]
    naive_aug = {bn: round(sum(q["actual"] for q in aug_completed if q["building"] == bn)
                         + sum(by_no[r["_no"]]["actual"] for r in t["req_rows"] if r["_role"] != "unique" and by_no[r["_no"]] in aug_completed
                               and by_no[r["_no"]]["building"] == bn), 2) for bn in BUILDING_NAMES}
    rent_top = max(tenants, key=lambda x: x["rent"])
    assert sum(1 for x in tenants if x["rent"] == rent_top["rent"]) == 1
    a, b = t["same_name"]
    linked_t = tenants[t["linked"]["_i"]]
    exp_names = sorted(t["expired"])
    distinct_building_strings = sorted({r["Building"] for r in t["unit_rows"]})
    rows = t["unit_rows"]
    ok_vendor = next(v for v in vend if v["name"] == TRADE_OK_NAMED)
    wrong_vendor = next(v for v in vend if v["name"] == TRADE_WRONG_NAMED)
    plumbing_current = sorted(v["name"] for v in vend if "Plumbing" in v["trades"] and v["insurance"] >= AS_OF)
    open_by_building = {bn: sum(1 for q in open_q if q["building"] == bn) for bn in BUILDING_NAMES}
    closed_exact = ("Completed", "Cancelled")
    naive_open_exact_words = sum(1 for q in requests if next(r["Status"] for r in t["req_rows"] if r["_no"] == q["no"] and r["_role"] == "unique") not in closed_exact)
    naive_open_rows = sum(1 for r in t["req_rows"] if r["Status"].strip().lower() in ("new", "assigned", "in progress", "waiting on vendor", "waiting - vendor"))
    elm_vacant = next(k for k in t["vacant_keys"] if k[0] == "Elm Court")
    maple_vacant = next(k for k in t["vacant_keys"] if k[0] == "Maple Row Townhomes")
    credit = t["credit_named"]

    counts = {
        "baseline": {
            "STAFF_ROLE": "Building manager",
            "VIEWER_ROLE": "Read-only (the accountant)",
            "MAIN_ENTITY": "work request",
            "MAIN_ENTITY_PLURAL": "work requests",
            "restricted_user": RESTRICTED,
            "restricted_buildings": RESTRICTED_BUILDINGS,
            "SCOPE_COUNT": len(in_scope),
            "OUT_OF_SCOPE_EXAMPLE": {"request": label(oos), "building": oos["building"], "unit": oos["unit"], "manager": MANAGER_OF[oos["building"]]},
            "KPI_1": {"name": "open work requests", "value": len(open_q), "scoped_value": sum(1 for q in open_q if q["building"] in RESTRICTED_BUILDINGS)},
            "KPI_2": {"name": "estimated cost of open work requests", "value": round(sum(q["est"] or 0 for q in open_q), 2)},
            "KPI_3": {"name": "vacant units", "value": len(t["vacant_keys"])},
            "KPI_4": {"name": "work requests completed in August 2026", "value": len(aug_completed)},
            "SEARCH_TERM": SEARCH_TERM, "SEARCH_COUNT": len(search_hits), "search_hits": [label(q) for q in search_hits],
            "FILTER_FIELD": "building", "FILTER_VALUE": filter_building, "FILTER_COUNT": len(filter_hits),
            "filter_rows_written_as": sorted({r["Building"] for r in t["req_rows"] if r["_role"] == "unique" and by_no[r["_no"]]["building"] == filter_building}),
            "SORT_FIELD": "estimated cost", "SORT_TOP": {"request": label(max_est), "est_cost": max_est["est"], "file_value": fmt_money(max_est["est"], 0)},
            "text_sort_top_would_be": {"request": f"WR-{text_top['_no']:05d}", "file_value": text_top["Est. Cost"]},
            "EXPORT_ROWS": len(requests),
            "EXPORT_COLUMNS": ["request number", "building", "unit", "category", "status", "estimated cost"],
            "REQUIRED_FIELD": "a building",
            "test_building": TEST_BUILDING,
        },
        "units": {
            "file_rows_excluding_header": len(rows),
            "exact_duplicate_rows": sum(1 for r in rows if r.get("_dupe") == "exact"),
            "variant_name_duplicate_rows": sum(1 for r in rows if r.get("_dupe") == "variant_name"),
            "unique_units": len(units),
            "buildings": len(BUILDING_NAMES),
            "per_building": unit_counts,
            "building_spellings_in_file": distinct_building_strings,
            "distinct_building_spellings_in_file": len(distinct_building_strings),
            "restricted_units": sum(unit_counts[b] for b in RESTRICTED_BUILDINGS),
            "vacant_units": [f"{k[0]} {k[1]}" for k in t["vacant_keys"]],
            "vacant_named": {"elm_court": f"Elm Court {elm_vacant[1]}", "maple_row": f"Maple Row Townhomes {maple_vacant[1]}"},
        },
        "tenants": {
            "file_rows_excluding_header": len(t["tenant_rows"]),
            "exact_duplicate_rows": N_TENANT_EXACT_DUPES,
            "same_email_different_case_rows": N_TENANT_CASE_DUPES,
            "unique_tenants": len(tenants),
            "dedupe_rule": "Two rows are the same tenant when Email matches after trimming and lowercasing. Two tenants with the same name and different emails are different people.",
            "duplicate_rows": [{"tenant": r["Tenant"], "email_as_written": r["Email"], "kind": r["_role"], "file_line": r["_line"]}
                               for r in t["tenant_rows"] if r["_role"] != "unique"],
            "same_name_pair": {"name": a["name"], "first": {"building": a["building"], "unit": a["unit"], "email": a["email"]},
                               "second": {"building": b["building"], "unit": b["unit"], "email": b["email"]}},
            "restricted_tenants": sum(1 for x in tenants if x["building"] in RESTRICTED_BUILDINGS),
            "linked_unit_example": {"tenant": linked_t["name"], "building": linked_t["building"], "unit": linked_t["unit"],
                                    "unit_as_written": t["linked"]["Unit"]},
            "impossible_lease": {"tenant": t["bad_lease"]["name"], "building": t["bad_lease"]["building"], "unit": t["bad_lease"]["unit"],
                                 "lease_start": t["bad_lease"]["lease_start"].isoformat(), "lease_end": t["bad_lease"]["lease_end"].isoformat(),
                                 "file_values": next({"Lease Start": r["Lease Start"], "Lease End": r["Lease End"]} for r in t["tenant_rows"]
                                                     if r["_i"] == tenants.index(t["bad_lease"]) and r["_role"] == "unique")},
            "highest_rent": {"tenant": rent_top["name"], "building": rent_top["building"], "unit": rent_top["unit"], "rent": rent_top["rent"],
                             "file_value": fmt_money(rent_top["rent"], 0)},
            "credit_balance_example": {"tenant": credit["name"], "building": credit["building"], "unit": credit["unit"], "balance": credit["balance"],
                                       "file_value": fmt_balance(credit["balance"], 0)},
            "tenants_with_credit": sum(1 for x in tenants if x["balance"] < 0),
            "total_monthly_rent": round(sum(x["rent"] for x in tenants), 2),
        },
        "vendors": {
            "file_rows_excluding_header": len(t["vendor_rows"]),
            "unique_vendors": len(vend),
            "duplicate_pairs": [{"canonical": c, "typed_as": d} for c, d in VENDOR_DUPES],
            "expired_insurance_as_of_2026_09_13": exp_names,
            "expired_named": {"vendor": EXPIRED_NAMED, "trade": "Pest Control", "insurance_expires": "2026-03-31", "file_value": "3/31/2026"},
            "current_named": {"vendor": CURRENT_NAMED, "trade": "Pest Control", "insurance_expires": "2027-06-30"},
            "trade_ok_named": {"vendor": TRADE_OK_NAMED, "trades": ok_vendor["trades"], "insurance_expires": ok_vendor["insurance"].isoformat()},
            "trade_wrong_named": {"vendor": TRADE_WRONG_NAMED, "trades": wrong_vendor["trades"], "insurance_expires": wrong_vendor["insurance"].isoformat()},
            "plumbing_vendors_with_current_insurance": plumbing_current,
        },
        "work_requests": {
            "file_rows_excluding_header": len(t["req_rows"]),
            "unique_requests": len(requests),
            "duplicate_rows": [{"written_as": r["Request #"], "request": f"WR-{r['_no']:05d}", "kind": r["_role"], "file_line": r["_line"]}
                               for r in t["req_rows"] if r["_role"] != "unique"],
            "status_mapping": {"open": ["New", "new", "Assigned", "In Progress", "In progress", "Waiting on Vendor", "Waiting - vendor"],
                               "closed": ["Completed", "complete", "Closed", "Cancelled", "Canceled"]},
            "open_total": len(open_q),
            "open_by_building": open_by_building,
            "naive_open_rows_counting_duplicates": naive_open_rows,
            "naive_open_if_only_Completed_and_Cancelled_close": naive_open_exact_words,
            "open_by_status": {s: sum(1 for q in open_q if q["status"] == s) for s in OPEN},
            "biggest_job": {"request": label(t["big"]), "building": t["big"]["building"], "unit": t["big"]["unit"], "est_cost": t["big"]["est"]},
            "approval_threshold": APPROVAL_THRESHOLD,
            "approval_test": {"over_threshold_est": 2400.00, "at_threshold_est": 1500.00},
        },
        "changes": {
            "c1_august_2026_actual_cost_by_building": {bn: round(sum(q["actual"] for q in aug_completed if q["building"] == bn), 2) for bn in BUILDING_NAMES},
            "c1_august_2026_actual_cost_total": round(sum(q["actual"] for q in aug_completed), 2),
            "c1_completed_requests": len(completed),
            "c1_average_days_submitted_to_completed": round(sum((q["completed"] - q["submitted"]).days for q in completed) / len(completed), 1),
            "c1_restricted_completed_requests": len(completed_scoped),
            "c1_restricted_average_days": round(sum((q["completed"] - q["submitted"]).days for q in completed_scoped) / len(completed_scoped), 1),
            "c1_naive_august_by_building_counting_repeated_rows": naive_aug,
            "c2_chargeback": {"tenant": credit["name"], "building": credit["building"], "unit": credit["unit"],
                              "balance_before": credit["balance"], "actual_cost": 180.00, "balance_after": round(credit["balance"] + 180.00, 2)},
            "c2_vacant_unit": f"Elm Court {elm_vacant[1]}",
            "c2_naive_balance_if_credit_read_as_owed": round(-credit["balance"] + 180.00, 2),
            "c1_average_days_bounds": [round(sum((q["completed"] - q["submitted"]).days for q in completed) / len(completed) - 0.1, 1),
                                       round(sum((q["completed"] - q["submitted"]).days for q in completed) / len(completed) + 0.1, 1)],
            "c1_restricted_average_days_bounds": [round(sum((q["completed"] - q["submitted"]).days for q in completed_scoped) / len(completed_scoped) - 0.1, 1),
                                                  round(sum((q["completed"] - q["submitted"]).days for q in completed_scoped) / len(completed_scoped) + 0.1, 1)],
        },
        "naive_alternatives": {
            "units_without_dedupe": len(rows), "buildings_if_spellings_kept": len(distinct_building_strings),
            "tenants_case_sensitive_email": len(t["tenant_rows"]) - N_TENANT_EXACT_DUPES,
            "tenants_merged_by_name": len({x["name"] for x in tenants}),
        },
        "test_inputs": {
            "item_21": {"request": "QA1", "building": TEST_BUILDING, "unit": "L101", "category": "Plumbing"},
            "item_24": {"building": "Harbor View", "unit": "101", "over_threshold_est": 2400.00, "at_threshold_est": 1500.00, "vendor": TRADE_OK_NAMED},
            "item_25": {"actual_cost": 185.00},
            "change_2": {"tenant_caused_actual_cost": 180.00, "untagged_actual_cost": 50.00},
            "change_3": {"estimate": 200.00, "attempted_estimate": 900.00, "vendor_actual_cost": 210.00, "visit_date": "2027-01-15",
                         "vendors": [TRADE_OK_NAMED, "Tideline Plumbing & Drain"]},
        },
    }
    return counts


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    seed = ap.parse_args().seed
    last_err = None
    for attempt in range(200):
        try:
            truth = build(seed, attempt)
            counts = summarize(truth)
            break
        except (ValueError, AssertionError, StopIteration) as e:
            last_err = e
    else:
        raise SystemExit(f"no valid draw: {last_err}")
    counts = {"seed": seed, "attempt": attempt, **counts}

    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "units.csv"), UNIT_COLUMNS, [[r[c] for c in UNIT_COLUMNS] for r in truth["unit_rows"]])
    write_csv(os.path.join(SEED_DIR, "tenants.csv"), TENANT_COLUMNS, [[r[c] for c in TENANT_COLUMNS] for r in truth["tenant_rows"]], bom=True, crlf=True)
    write_csv(os.path.join(SEED_DIR, "vendors.csv"), VENDOR_COLUMNS, [[r[c] for c in VENDOR_COLUMNS] for r in truth["vendor_rows"]])
    write_csv(os.path.join(SEED_DIR, "work_requests.csv"), REQUEST_COLUMNS, [[r[c] for c in REQUEST_COLUMNS] for r in truth["req_rows"]])
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(counts, indent=2) + "\n")
    b = counts["baseline"]
    print(f"units {counts['units']['file_rows_excluding_header']} rows -> {counts['units']['unique_units']}; "
          f"tenants {counts['tenants']['file_rows_excluding_header']} -> {counts['tenants']['unique_tenants']}; "
          f"vendors {counts['vendors']['file_rows_excluding_header']} -> {counts['vendors']['unique_vendors']}; "
          f"requests {counts['work_requests']['file_rows_excluding_header']} -> {counts['work_requests']['unique_requests']}; "
          f"open {b['KPI_1']['value']} (scoped {b['KPI_1']['scoped_value']}); attempt {attempt}")


if __name__ == "__main__":
    main()
