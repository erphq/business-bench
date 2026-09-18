#!/usr/bin/env python3
"""shipping-rate-lookup: this week's outbound orders priced against the parcel carrier's zone and rate card.

    python gen.py [--seed N] [--naive DIR]

Business: a ceramics studio in Portland, Oregon that ships pottery by a regional ground carrier and wants to
check the carrier's invoice before paying it.

Traps (each caught by a check, see task.yaml):
  * zones go by the first three digits of the ZIP, but the export went through a spreadsheet and three
    New England / New Jersey ZIPs lost their leading zero ("5401"); ZIP+4 values also appear   (check: zone)
  * billable weight is the actual weight rounded UP to the next whole pound: 6.0 stays 6, 6.1 is 7, and four
    small parcels are weighed in ounces                                                          (check: billable weight)
  * large package rule from the rate card terms: longest side over 48 in (not always the first dimension,
    exactly 48 is not over) bills at least 30 lb plus a surcharge                               (checks: billable weight; shipping cost)
  * the residential surcharge only exists in the carrier's email: any label without a business name,
    and a Company cell of 'N/A', '-' or 'none' is not a business name                           (check: shipping cost)
  * the rate workbook still carries last year's ground table on its first sheet                (check: shipping cost)
"""
from __future__ import annotations

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

ZONES = [("005", "099", 8), ("100", "199", 8), ("200", "299", 8), ("300", "349", 8), ("350", "399", 7), ("400", "499", 7),
         ("500", "599", 6), ("600", "699", 6), ("700", "799", 6), ("800", "816", 5), ("820", "831", 5), ("832", "838", 4),
         ("840", "847", 4), ("850", "865", 5), ("870", "884", 5), ("889", "898", 4), ("900", "935", 4), ("936", "961", 3),
         ("970", "979", 2), ("980", "994", 3)]
DESTS = [("Portland", "OR", "97209"), ("Eugene", "OR", "97401"), ("Bend", "OR", "97701"), ("Tacoma", "WA", "98402"),
         ("Seattle", "WA", "98101"), ("Sacramento", "CA", "95814"), ("San Diego", "CA", "92101"), ("Boise", "ID", "83702"),
         ("Salt Lake City", "UT", "84111"), ("Las Vegas", "NV", "89101"), ("Denver", "CO", "80202"), ("Boulder", "CO", "80302"),
         ("Cheyenne", "WY", "82001"), ("Tucson", "AZ", "85701"), ("Santa Fe", "NM", "87501"), ("Austin", "TX", "78701"),
         ("Omaha", "NE", "68102"), ("Kansas City", "MO", "64105"), ("Chicago", "IL", "60601"), ("Madison", "WI", "53703"),
         ("Minneapolis", "MN", "55401"), ("Columbus", "OH", "43215"), ("Ann Arbor", "MI", "48104"), ("Nashville", "TN", "37203"),
         ("Atlanta", "GA", "30303"), ("Savannah", "GA", "31401"), ("Raleigh", "NC", "27601"), ("Richmond", "VA", "23219"),
         ("Pittsburgh", "PA", "15222"), ("Brooklyn", "NY", "11201")]
LEADING_ZERO = [("Burlington", "VT", "05401"), ("Hoboken", "NJ", "07030"), ("Portland", "ME", "04101")]
BASE_2026 = {2: 9.85, 3: 10.60, 4: 11.95, 5: 12.80, 6: 13.90, 7: 14.75, 8: 15.60}
PER_LB_2026 = {2: 0.62, 3: 0.81, 4: 1.05, 5: 1.28, 6: 1.52, 7: 1.74, 8: 1.96}
RESIDENTIAL = 4.95
LARGE_SURCHARGE = 28.00
LARGE_MIN_LB = 30
MAX_LB = 70
ITEMS = ["Stoneware mug set", "Serving platter", "Dinner plates x4", "Floor vase", "Planter large", "Bud vase trio", "Ramen bowls x2",
         "Pitcher", "Lamp base", "Umbrella stand", "Cake stand", "Salad bowl", "Tile sample box", "Wall planter"]
BUSINESSES = ["Juniper Street Cafe", "Foxglove Interiors", "Ivy Lane Florist", "Larkspur Yoga", "Driftwood Studio", "Nightjar Coffee Roasters",
              "Riverbend Physio", "Wren & Sparrow Bookshop", "Quarry Road Nursery", "Blue Heron Consulting", "Harbor Light Marine",
              "Tamarack Brewing", "Glassworks Optical", "Orchard Hill Dental"]


def zone_for(zip5: str) -> int:
    p = zip5[:3]
    for lo, hi, z in ZONES:
        if lo <= p <= hi:
            return z
    raise ValueError(zip5)


def rate(zone: int, lb: int, year: int = 2026) -> float:
    base = BASE_2026[zone] + PER_LB_2026[zone] * (lb - 1)
    if year == 2025:
        base *= 0.94
    return round(base + 1e-9, 2)


def build(seed: int) -> dict:
    r = rng(seed)
    orders = []
    n = 62
    dests = [r.choice(DESTS) for _ in range(n - 3)] + LEADING_ZERO
    r.shuffle(dests)
    for i, (city, st, z5) in enumerate(dests):
        f, l = person(r)
        biz = r.choice(BUSINESSES) if r.random() < 0.55 else ""
        dims = sorted([r.randint(6, 22), r.randint(6, 22), r.randint(8, 30)], reverse=True)
        w = round(r.uniform(1.2, 24.0), 1)
        orders.append({"id": f"UC-{5310 + i * 3 + r.randint(0, 2)}", "name": f"{f} {l}", "company": biz, "company_shown": biz,
                       "addr": f"{r.randint(12, 9899)} {r.choice(STREETS)}", "city": city, "state": st, "zip5": z5,
                       "zip_shown": z5, "weight": w, "weight_shown": f"{w}", "dims": dims, "item": r.choice(ITEMS)})
    idx = list(range(n))
    r.shuffle(idx)
    cursor = 0

    def take(k, cond=lambda o: True):
        nonlocal cursor
        got = []
        while len(got) < k:
            o = orders[idx[cursor % n]]
            cursor += 1
            if o.get("role") is None and cond(o):
                got.append(o)
        return got

    for o in orders:
        if o["zip5"] in {z for _, _, z in LEADING_ZERO}:
            o["zip_shown"] = o["zip5"].lstrip("0")
            o["role"] = "leading_zero"
    for o in take(6, lambda o: not o["zip5"].startswith("0")):
        o["zip_shown"] = f"{o['zip5']}-{r.randint(1000, 9999)}"
        o["role"] = "zip4"
    for o in take(3):
        o["company"] = ""
        o["company_shown"] = r.choice(["N/A", "-", "none"])
        o["role"] = "na_company"
    for o in take(4):
        oz = r.randint(5, 15)
        o["weight"] = oz / 16
        o["weight_shown"] = f"{oz} oz"
        o["dims"] = sorted([r.randint(4, 9), r.randint(4, 9), r.randint(3, 8)], reverse=True)
        o["role"] = "ounces"
    for o in take(5):
        w = r.randint(2, 18)
        o["weight"] = float(w)
        o["weight_shown"] = f"{w}.0"
        o["role"] = "whole_pound"
    big = take(4)
    big[0]["dims"], big[0]["weight"] = [52, 16, 14], round(r.uniform(11, 19), 1)
    big[1]["dims"], big[1]["weight"] = [54, 20, 12], round(r.uniform(31.2, 38.8), 1)
    big[2]["dims"], big[2]["weight"] = [50, 18, 18], round(r.uniform(14, 22), 1)
    big[3]["dims"], big[3]["weight"] = [48, 14, 12], round(r.uniform(12, 20), 1)
    for o, role in zip(big, ["large", "large_heavy", "large", "exactly_48"]):
        o["weight_shown"] = f"{o['weight']}"
        o["role"] = role
    # dims as printed: the longest side is not always first
    for o in orders:
        d = list(o["dims"])
        k = r.random()
        if o.get("role") in ("large", "large_heavy") or k < 0.4:
            d = [d[1], d[0], d[2]] if r.random() < 0.5 else [d[2], d[1], d[0]]
        o["dims_shown"] = " x ".join(str(x) for x in d)
    # truth
    for o in orders:
        o["zone"] = zone_for(o["zip5"])
        bill = math.ceil(round(o["weight"], 4) - 1e-9)
        bill = max(bill, 1)
        large = max(o["dims"]) > 48
        if large:
            bill = max(bill, LARGE_MIN_LB)
        o["billable"] = bill
        o["large"] = large
        o["residential"] = not o["company"]
        o["cost"] = round(rate(o["zone"], bill) + (RESIDENTIAL if o["residential"] else 0) + (LARGE_SURCHARGE if large else 0), 2)
    return {"orders": orders}


def acceptable(d: dict) -> bool:
    orders = d["orders"]
    for o in orders:
        if o.get("role") == "leading_zero":
            wrong = o["zip_shown"][:3]
            zw = next((z for lo, hi, z in ZONES if lo <= wrong <= hi), None)
            if zw == o["zone"]:
                return False
        if o.get("role") is None and o["weight"] == int(o["weight"]):
            return False
        if o["billable"] > MAX_LB:
            return False
    if sum(1 for o in orders if o["residential"]) < 18:
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    orders = d["orders"]

    rows = [[o["id"], "09/11/2026", o["name"], o["company_shown"], o["addr"], o["city"], o["state"], o["zip_shown"],
             o["weight_shown"], o["dims_shown"], o["item"]] for o in orders]
    write_csv(os.path.join(ws, "orders_to_ship_2026-09-11.csv"),
              ["Order #", "Order Date", "Ship To Name", "Ship To Company", "Address", "City", "State", "ZIP", "Weight (lb)",
               "Dims (in)", "Contents"], rows, crlf=True)

    zone_rows = [[f"{lo}-{hi}" if lo != hi else lo, z] for lo, hi, z in ZONES]
    zones_hdr = ["Zone"] + [z for z in range(2, 9)]
    old = [[lb] + [rate(z, lb, 2025) for z in range(2, 9)] for lb in range(1, MAX_LB + 1)]
    new = [[lb] + [rate(z, lb) for z in range(2, 9)] for lb in range(1, MAX_LB + 1)]
    write_xlsx(os.path.join(ws, "cascade_parcel_rate_card.xlsx"), {
        "Ground 2025": {"merged_title": "Cascade Parcel Ground - daily rates effective January 1, 2025 (USD)",
                        "header": ["Weight (lb)"] + [f"Zone {z}" for z in range(2, 9)], "rows": old,
                        "number_formats": {c: "0.00" for c in "BCDEFGH"}},
        "Ground 2026": {"merged_title": "Cascade Parcel Ground - daily rates effective January 1, 2026 (USD)",
                        "header": ["Weight (lb)"] + [f"Zone {z}" for z in range(2, 9)], "rows": new,
                        "number_formats": {c: "0.00" for c in "BCDEFGH"}},
        "Zones from 972": {"merged_title": "Zone chart - origin ZIP 972xx (Portland, OR)",
                           "preamble": [["Use the first three digits of the destination ZIP."]],
                           "header": ["Destination ZIP prefix", "Zone"], "rows": zone_rows, "widths": {"A": 24}},
        "Terms": {"header": ["Rating terms (2026)"], "rows": [
            ["Billable weight is the actual package weight rounded up to the next whole pound. Fractions of a pound always round up."],
            ["Large Package: a package whose longest side exceeds 48 inches is billed at no less than 30 lb billable weight"],
            [f"and is assessed a Large Package surcharge of ${LARGE_SURCHARGE:.2f} per package in addition to the transportation charge."],
            ["Rates shown are per package and exclude accessorial charges. Accessorials are published separately."],
        ], "widths": {"A": 110}},
    }, creator="Cascade Parcel")

    write_email_thread(os.path.join(ws, "email_cascade_residential.txt"), [
        {"from": "Tomasz Kowalski <tkowalski@cascadeparcel.com>", "to": "shipping@umberceramics.com", "date": "Mon, 17 Aug 2026 13:05",
         "subject": "Accessorial update - residential deliveries",
         "body": ("Hi team,\n\nA heads-up ahead of your next invoice. From September 1 we are adding a residential delivery surcharge of "
                  f"${RESIDENTIAL:.2f} per package on ground shipments.\n\nFor billing we treat any label that does not carry a business "
                  "name as a residential delivery, whatever the street address looks like. Your large package and weight terms are "
                  "unchanged from the rate card.\n\nBest,\nTomasz\nCascade Parcel - Account Management")},
        {"from": "Mateo Alvarez <mateo@umberceramics.com>", "to": "shipping@umberceramics.com", "date": "Fri, 11 Sep 2026 17:40",
         "subject": "Re: Accessorial update - residential deliveries",
         "body": ("Forwarding so we have it. Cascade's invoice for this week's pickups will show up Monday and I want to check it "
                  "line by line. For every order in today's export give me order_id, zone, billable_weight and shipping_cost "
                  "(what Cascade should charge us for that package, all surcharges in).\n\nMateo")},
    ])

    header = ["order_id", "zone", "billable_weight", "shipping_cost"]
    out = [[o["id"], o["zone"], o["billable"], f"{o['cost']:.2f}"] for o in orders]
    write_csv(os.path.join(ref, "orders_shipping.csv"), header, out)
    write_csv(os.path.join(sol, "orders_shipping.csv"), header, out)
    roles = {}
    for o in orders:
        if o.get("role"):
            roles.setdefault(o["role"], []).append(o["id"])
    write_json(os.path.join(ref, "notes.json"), {"roles": roles, "total_cost": round(sum(o["cost"] for o in orders), 2),
                                                 "residential_count": sum(1 for o in orders if o["residential"])})
    must_zone = roles["leading_zero"] + roles["zip4"][:2]
    must_weight = roles["ounces"] + roles["whole_pound"] + roles["large"] + roles["large_heavy"]
    must_cost = roles["na_company"] + roles["large"] + roles["large_heavy"] + roles["exactly_48"] + roles["leading_zero"]
    write_task_yaml(HERE, {
        "id": "shipping-rate-lookup", "track": "desk", "category": "spreadsheet",
        "title": "Work out what the carrier should charge per order",
        "ask": ("Before Cascade's invoice arrives I want to know what each of today's orders should cost to ship. "
                "Use their rate card and the emails in the folder, and save it as orders_shipping.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "zones go by the first three ZIP digits, but three East Coast ZIPs lost their leading zero in the export (05401 is written "
            "5401, so its first three digits read as 540, a different zone) and six carry a ZIP+4 suffix (check: zone)",
            "billable weight is actual weight rounded up to the next whole pound: 6.0 stays 6 while 6.1 bills as 7, so rounding to "
            "nearest or adding one to every weight is wrong, and four small parcels are weighed in ounces (check: billable weight)",
            "the large package rule in the Terms sheet: longest side over 48 in bills at least 30 lb plus $28.00; the long side is "
            "printed second or third on some labels, one large parcel already weighs over 30 lb and bills at its own weight, and a "
            "48 in box is not over the limit (checks: billable weight; shipping cost)",
            f"the ${RESIDENTIAL:.2f} residential surcharge is only in the carrier's email: any label without a business name, and three "
            "orders carry 'N/A', '-' or 'none' in the Company column, which is not a business name (check: shipping cost)",
            "the rate workbook opens on last year's Ground 2025 table, about 6% cheaper than the 2026 table on the next sheet "
            "(check: shipping cost)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "orders_shipping.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every order priced", "path": "orders_shipping.csv", "column": "order_id",
             "ref": "orders_shipping.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "orders_shipping.csv", "equals_ref": "orders_shipping.csv"},
            {"type": "csv_values_match", "name": "zone", "path": "orders_shipping.csv", "ref": "orders_shipping.csv", "key": "order_id",
             "columns": ["zone"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0, "must_match_keys": must_zone},
            {"type": "csv_values_match", "name": "billable weight", "path": "orders_shipping.csv", "ref": "orders_shipping.csv",
             "key": "order_id", "columns": ["billable_weight"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0,
             "must_match_keys": must_weight},
            {"type": "csv_values_match", "name": "shipping cost", "path": "orders_shipping.csv", "ref": "orders_shipping.csv",
             "key": "order_id", "columns": ["shipping_cost"], "numeric": True, "tolerance": 0.011, "min_accuracy": 1.0,
             "must_match_keys": must_cost},
        ],
    })
    print(f"seed={seed} orders={len(orders)} residential={sum(1 for o in orders if o['residential'])} roles={ {k: len(v) for k, v in roles.items()} }")


def write_naive(d: dict, out: str) -> None:
    """First three characters of the ZIP as written, weight rounded to nearest, 2025 table, no surcharges."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for o in d["orders"]:
        p = o["zip_shown"][:3]
        z = next((zz for lo, hi, zz in ZONES if lo <= p <= hi), 8)
        w = o["weight"]
        bill = max(1, int(round(w)))
        rows.append([o["id"], z, bill, f"{rate(z, bill, 2025):.2f}"])
    write_csv(os.path.join(out, "orders_shipping.csv"), ["order_id", "zone", "billable_weight", "shipping_cost"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
