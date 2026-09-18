#!/usr/bin/env python3
"""Deterministic seed generator for the vendor-onboarding build task.

    python gen.py [--seed N]

Writes:
  seed/vendors.csv        vendor master merged from two old systems: exact duplicate rows, vendors
                          re-entered under a second number with the Tax ID written without its dash,
                          unpadded vendor numbers, category and stage case noise, currency strings
  seed/documents.csv      onboarding documents received, one row per document, filed under whichever
                          vendor number the clerk had (padded, unpadded, or the second system's number)
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the public variant that checklist.md quotes. Other seeds re-roll names, numbers, amounts,
and which vendors carry each trap; counts.json is recomputed, so re-derive the checklist from it.
Insurance dates are either on or before 2026-08-28 (lapsed) or in 2028, so the lapsed and
expiring-within-30-days figures hold for any test date from 2026-09-01 to 2027-12-01.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, phone_variant, write_csv, write_text  # noqa: E402

SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

COMPANY = "Bellhaven Foods"
ADMIN = "Carla Brennan (procurement lead)"
MANAGERS = {  # manager -> categories, in the order the ask lists them
    "Rosa Delgado": ["Ingredients", "Packaging"],
    "Dev Malhotra": ["Logistics"],
    "Mei Chen": ["Facilities"],
    "Tom Okafor": ["IT & Services"],
}
RESTRICTED = "Rosa Delgado"
CATEGORY_MANAGER = {c: m for m, cs in MANAGERS.items() for c in cs}
CATEGORIES = ["Ingredients", "Packaging", "Logistics", "Facilities", "IT & Services"]
PER_CATEGORY = {"Ingredients": 32, "Packaging": 22, "Logistics": 22, "Facilities": 22, "IT & Services": 18}
N_UNIQUE = sum(PER_CATEGORY.values())  # 116
STAGES = ["New", "Documents", "Review", "Approved", "Rejected"]
STAGE_COUNTS = {"New": 18, "Documents": 22, "Review": 10, "Approved": 58, "Rejected": 8}
ONBOARDING = ("New", "Documents", "Review")
N_EXACT_DUPES = 6
N_REENTERED = 4
N_BLANK_TAX = 5
N_LAPSED = 6
N_UNPADDED_ROWS = 8
TERMS = ["Net 30", "Net 30", "Net 45", "Net 60", "2% 10 Net 30"]

W9, COI, COC, FSC = "W-9", "Certificate of Insurance", "Code of Conduct", "Food Safety Certificate"
DOC_VARIANTS = {
    W9: ["W9", "w-9"],
    COI: ["COI", "Cert. of Insurance"],
    COC: ["Signed Code of Conduct", "code of conduct"],
    FSC: ["Food safety cert"],
}
GENERAL_DOCS = [W9, COI, COC]

NAME_POOLS = {
    "Ingredients": (["Prairie", "Sunridge", "Coastal", "Blue Ridge", "Harvest Valley", "Golden Plains", "Cedar Creek",
                     "Riverbend", "Northfield", "Willow Brook", "Heartland", "Lakeshore", "Red Barn", "Old Mill",
                     "Meadowlark", "Bramble Hill", "Sweetwater", "Copper Kettle"],
                    ["Grain Co.", "Dairy", "Spice Traders", "Sugar Refining", "Orchards", "Flour Mills", "Oils Inc.",
                     "Egg Farms", "Cocoa Importers", "Nut Company", "Honey LLC", "Produce"]),
    "Packaging": (["Apex", "Keystone", "Northstar", "Clearview", "Pinnacle", "Ironclad", "Bluewater", "Crestline",
                   "Liberty", "Ridgeway", "Tidewater", "Granite State"],
                  ["Packaging Inc.", "Corrugated", "Films LLC", "Labels & Print", "Containers", "Carton Co.",
                   "Closures", "Pallet Supply"]),
    "Logistics": (["Cold Chain", "Interstate", "Great Lakes", "Midland", "Frontier", "Crossroads", "Tri-County",
                   "Highway 30", "Bluegrass", "Ridgeline", "Lone Pine", "Twin Rivers"],
                  ["Carriers", "Freight LLC", "Logistics", "Transport Inc.", "Trucking", "Warehousing", "Express"]),
    "Facilities": (["Precision", "Allied", "Metro", "Cornerstone", "Guardian", "Brightline", "Superior", "Tri-State",
                    "Hometown", "Reliable", "Pioneer", "Summit"],
                   ["Mechanical", "Electric LLC", "Pest Control", "Janitorial", "Fire Protection", "Roofing Inc.",
                    "Refrigeration Service", "Landscaping", "Industrial Supply"]),
    "IT & Services": (["Brightpath", "Quantum", "Clearwater", "Ironbridge", "Lumen", "Northwind", "Sterling",
                       "Vector", "Catalyst", "Oakline"],
                      ["IT Solutions", "Consulting", "Staffing", "Software Inc.", "Networks", "Payroll Services",
                       "Legal LLP", "CPA Group"]),
}
SAFE_DATE_STYLES = [0, 1, 2, 3, 4]  # never the day-first style


def vno(n: int) -> str:
    return f"V-{n:04d}"


def slug(name: str) -> str:
    keep = "".join(ch for ch in name.lower() if ch.isalnum() or ch == " ")
    words = [w for w in keep.split() if w not in ("inc", "llc", "llp", "co")]
    return "".join(words[:3])


def tax_fmt(digits: str) -> str:
    return f"{digits[:2]}-{digits[2:]}"


def money_out(v: float, rng: random.Random, force_dollar: bool = False) -> str:
    if force_dollar:
        return f"${v:,.2f}"
    k = rng.random()
    if k < 0.15:
        return f"${v:,.2f}"
    if k < 0.32:
        return f"{v:,.2f}"
    return f"{v:.2f}"


def noisy(text: str, rng: random.Random, p: float) -> str:
    if rng.random() >= p:
        return text
    return rng.choice([text.lower(), text.upper(), text + " ", " " + text])


def build(seed: int) -> dict:
    rng = random.Random(seed)

    # ------------------------------------------------------------------ unique vendors
    names_used: set[str] = set()
    vendors: list[dict] = []
    for cat in CATEGORIES:
        places, kinds = NAME_POOLS[cat]
        combos = [f"{p} {k}" for p in places for k in kinds]
        rng.shuffle(combos)
        taken_places: dict[str, int] = {}
        for combo in combos:
            if sum(1 for v in vendors if v["category"] == cat) == PER_CATEGORY[cat]:
                break
            place = next(p for p in places if combo.startswith(p + " "))
            if combo in names_used or taken_places.get(place, 0) >= 3:
                continue
            taken_places[place] = taken_places.get(place, 0) + 1
            names_used.add(combo)
            vendors.append({"name": combo, "category": cat, "place": place})
    assert len(vendors) == N_UNIQUE

    stage_list = [s for s in STAGES for _ in range(STAGE_COUNTS[s])]
    rng.shuffle(stage_list)
    rng.shuffle(vendors)
    tax_seen: set[str] = set()
    people = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(people)
    for i, v in enumerate(vendors):
        v["no"] = vno(i + 1)
        v["stage"] = stage_list[i]
        while True:
            digits = f"{rng.randint(10, 98)}{rng.randint(1000000, 9999999)}"
            if digits not in tax_seen:
                tax_seen.add(digits)
                break
        v["tax"] = digits
        first, last = people[i]
        v["contact"] = f"{first} {last}"
        v["email"] = f"{first.lower()}.{last.lower()}@{slug(v['name'])}.com"
        v["phone"] = f"{rng.choice([312, 414, 515, 608, 612, 816])}555{rng.randint(1000, 1999):04d}"[:10]
        v["terms"] = rng.choice(TERMS)
        if v["stage"] == "Approved":
            hi = 480000 if v["category"] in ("Ingredients", "Packaging") else 160000
            v["spend"] = round(rng.uniform(2500, hi), 2)
            v["added"] = date(2019, 1, 1) + timedelta(days=rng.randint(0, 2300))
        else:
            v["spend"] = None
            v["added"] = date(2026, 3, 1) + timedelta(days=rng.randint(0, 175))
        v["lapsed"] = False
        v["alias"] = None

    by_stage = {s: [v for v in vendors if v["stage"] == s] for s in STAGES}

    # ------------------------------------------------------------------ trap roles (disjoint)
    reserved: set[str] = set()

    def take(pool: list[dict], n: int, pred=lambda v: True) -> list[dict]:
        cands = [v for v in pool if v["no"] not in reserved and pred(v)]
        got = rng.sample(cands, n)
        reserved.update(v["no"] for v in got)
        return got

    rosa_cats = MANAGERS[RESTRICTED]
    blank_tax = take(by_stage["New"], N_BLANK_TAX)
    for v in blank_tax:
        v["tax"] = ""
    # vendor B: Ingredients vendor at Documents holding the three general documents but no food safety certificate
    vendor_b = take(by_stage["Documents"], 1, lambda v: v["category"] == "Ingredients")[0]
    # vendor G: a Packaging vendor at New that Rosa moves to Documents
    vendor_g = take(by_stage["New"], 1, lambda v: v["category"] == "Packaging")[0]
    # vendor A: approved Packaging vendor whose documents are filed under unpadded numbers
    vendor_a = take(by_stage["Approved"], 1, lambda v: v["category"] == "Packaging")[0]
    # vendor D: approved Packaging vendor with exactly the three general documents (complete)
    vendor_d = take(by_stage["Approved"], 1, lambda v: v["category"] == "Packaging")[0]
    # vendor F: Review vendor whose insurance certificate expires before it was issued
    vendor_f = take(by_stage["Review"], 1, lambda v: v["category"] not in rosa_cats)[0]
    # lapsed insurance: six approved vendors, at least two of them Rosa's
    lapsed = take(by_stage["Approved"], 2, lambda v: v["category"] in rosa_cats)
    lapsed += take(by_stage["Approved"], N_LAPSED - 2, lambda v: v["category"] not in rosa_cats)
    for v in lapsed:
        v["lapsed"] = True
    # vendor E: approved Facilities vendor the tester moves in and out of the 30-day window
    vendor_e = take(by_stage["Approved"], 1, lambda v: v["category"] == "Facilities")[0]
    # vendor E2: approved Packaging vendor for change request 2
    vendor_e2 = take(by_stage["Approved"], 1, lambda v: v["category"] == "Packaging")[0]
    # re-entered duplicates (second system): approved vendors with a Tax ID
    reentered = take(by_stage["Approved"], N_REENTERED, lambda v: v["tax"] != "")
    vendor_c = reentered[0]
    vendor_h = reentered[1]  # the item-10 search target
    for k, v in enumerate(reentered):
        v["alias"] = f"SUP-{rng.randint(2000, 2999)}"
    assert len({v["alias"] for v in reentered}) == N_REENTERED
    # out-of-scope example: an approved Logistics vendor (Dev's)
    out_of_scope = take(by_stage["Approved"], 1, lambda v: v["category"] == "Logistics")[0]
    exact_dupes = take(vendors, N_EXACT_DUPES, lambda v: v["tax"] != "")

    # the highest annual spend must be written with a dollar sign and be unique
    approved = by_stage["Approved"]
    top = max(approved, key=lambda v: v["spend"])
    assert sum(1 for v in approved if v["spend"] == top["spend"]) == 1

    # ------------------------------------------------------------------ vendors.csv rows
    unpadded = set(v["no"] for v in rng.sample([v for v in vendors if v["no"] not in reserved], N_UNPADDED_ROWS - 1))
    unpadded.add(vendor_a["no"])

    def vendor_row(v: dict, *, no=None, name=None, tax=None, category=None, stage=None, added=None, spend_force=False) -> list:
        num = no if no is not None else (f"V-{int(v['no'][2:])}" if v["no"] in unpadded else v["no"])
        return [
            num,
            name if name is not None else v["name"],
            category if category is not None else noisy(v["category"], rng, 0.14),
            tax if tax is not None else (tax_fmt(v["tax"]) if v["tax"] else ""),
            v["contact"],
            v["email"],
            phone_variant(v["phone"], rng.randrange(7)),
            v["terms"],
            "" if v["spend"] is None else money_out(v["spend"], rng, spend_force),
            stage if stage is not None else noisy(v["stage"], rng, 0.16),
            date_variant(added or v["added"], rng.choice(SAFE_DATE_STYLES)),
        ]

    rows: list[dict] = []
    for v in vendors:
        rows.append({"v": v, "role": "unique", "cells": vendor_row(v, spend_force=(v is top))})
    for v in exact_dupes:
        orig = next(r for r in rows if r["v"] is v)
        rows.append({"v": v, "role": "exact_duplicate", "cells": list(orig["cells"])})
    for v in reentered:
        if v["name"].endswith(" Inc."):
            name2 = v["name"][:-5] + ", Inc."
        elif v["name"].endswith(" LLC"):
            name2 = v["name"][:-4] + ", LLC"
        else:
            name2 = v["name"].upper()
        rows.append({"v": v, "role": "reentered", "cells": vendor_row(
            v, no=v["alias"], name=name2, tax=v["tax"], category=v["category"].lower(),
            added=date(2025, 6, 1) + timedelta(days=rng.randint(0, 300)))})
    rng.shuffle(rows)
    for line, r in enumerate(rows, start=2):
        r["line"] = line

    # ------------------------------------------------------------------ documents.csv rows
    def ref_number(v: dict, force_variant: bool = False) -> str:
        n = int(v["no"][2:])
        if force_variant:
            return rng.choice([f"V-{n}", f"{n:04d}", f"v-{n:04d}"])
        if rng.random() < 0.10:
            return rng.choice([f"V-{n}", f"{n:04d}", f"v-{n:04d}"])
        return v["no"]

    def doc_name(kind: str) -> str:
        return rng.choice(DOC_VARIANTS[kind]) if rng.random() < 0.2 else kind

    def fut_expiry() -> date:
        return date(2028, 1, 10) + timedelta(days=rng.randint(0, 340))

    docs: list[dict] = []

    def add_doc(v: dict, kind: str, *, number=None, issued=None, expires=None, vendor_name=None) -> None:
        if v["stage"] == "Approved":
            if kind in (COI, FSC):
                if expires is None:
                    expires = fut_expiry()
                if issued is None:
                    issued = expires - timedelta(days=730)
                    if issued > date(2026, 8, 20):
                        issued = date(2026, 1, 5) + timedelta(days=rng.randint(0, 200))
                received = issued + timedelta(days=rng.randint(1, 12))
            else:
                received = date(2024, 2, 1) + timedelta(days=rng.randint(0, 900))
        else:  # documents arrive after the vendor was added; certificates were issued a little earlier
            received = v["added"] + timedelta(days=rng.randint(1, 20))
            if kind in (COI, FSC):
                if issued is None:
                    issued = received - timedelta(days=rng.randint(1, 30))
                if expires is None:
                    expires = issued + timedelta(days=730)
        docs.append({
            "v": v, "kind": kind, "expires": expires, "issued": issued,
            "cells": [
                number if number is not None else ref_number(v),
                vendor_name if vendor_name is not None else noisy(v["name"], rng, 0.08).strip(),
                doc_name(kind),
                date_variant(received, rng.choice(SAFE_DATE_STYLES)),
                date_variant(issued, rng.choice(SAFE_DATE_STYLES)) if issued else "",
                date_variant(expires, rng.choice(SAFE_DATE_STYLES)) if expires else "",
            ],
        })

    def required(v: dict) -> list[str]:
        return GENERAL_DOCS + ([FSC] if v["category"] == "Ingredients" else [])

    missing_by_vendor: dict[str, list[str]] = {}
    for v in vendors:
        req = required(v)
        if v["stage"] in ("Approved", "Review"):
            have = list(req)
        elif v["stage"] == "Documents":
            if v is vendor_b:
                have = list(GENERAL_DOCS)
            else:
                n_missing = rng.choice([1, 1, 2])
                missing = rng.sample(req, n_missing)
                if v["category"] == "Ingredients" and missing == [FSC]:
                    missing = [W9]  # vendor B is the only one missing just the food safety certificate
                have = [d for d in req if d not in missing]
        elif v["stage"] == "Rejected":
            have = rng.sample(GENERAL_DOCS, rng.choice([0, 1, 1, 2]))
        else:
            have = []
        missing_by_vendor[v["no"]] = [d for d in req if d not in have]
        for kind in have:
            if v is vendor_a:
                add_doc(v, kind, number=ref_number(v, force_variant=True))
            elif v is vendor_c and kind == COI:
                add_doc(v, kind, number=v["alias"], vendor_name=v["name"].upper())
            elif v["alias"] and kind == W9:
                add_doc(v, kind, number=v["alias"])
            elif v is vendor_f and kind == COI:
                add_doc(v, kind, issued=date(2026, 3, 16), expires=date(2025, 3, 16))
            elif v["lapsed"] and kind == COI:
                exp = date(2025, 11, 1) + timedelta(days=rng.randint(0, 300))
                add_doc(v, kind, expires=exp, issued=exp - timedelta(days=365))
            else:
                add_doc(v, kind)
    # the documents export repeats a few rows
    doc_dupes = rng.sample([d for d in docs if d["v"]["stage"] == "Approved"], 4)
    for d in doc_dupes:
        docs.append(dict(d, cells=list(d["cells"]), dup=True))
    rng.shuffle(docs)

    for d in docs:
        if d["v"]["lapsed"] and d["kind"] == COI:
            assert d["expires"] <= date(2026, 8, 28)

    # ------------------------------------------------------------------ figures
    def in_scope(v: dict) -> bool:
        return v["category"] in MANAGERS[RESTRICTED]

    onboarding = [v for v in vendors if v["stage"] in ONBOARDING]
    approved_spend = round(sum(v["spend"] for v in approved), 2)
    lapsed_sorted = sorted(lapsed, key=lambda v: v["name"])
    search_term = vendor_h["place"]
    search_hits = sorted(v["name"] for v in vendors if search_term.lower() in v["name"].lower())
    assert 1 <= len(search_hits) <= 4, search_hits
    filter_count = sum(1 for v in vendors if v["category"] == "Packaging")
    raw_text_top = max((r for r in rows if r["cells"][8]), key=lambda r: r["cells"][8])

    wrong_rosa_exact = sum(1 for r in rows if r["role"] == "unique" and r["cells"][2] in MANAGERS[RESTRICTED])
    spend_by_cat = {c: round(sum(v["spend"] for v in approved if v["category"] == c), 2) for c in CATEGORIES}
    lapsed_by_manager = {m: sum(1 for v in lapsed if CATEGORY_MANAGER[v["category"]] == m) for m in MANAGERS}

    def vinfo(v: dict) -> dict:
        return {"name": v["name"], "vendor_no": v["no"], "category": v["category"],
                "manager": CATEGORY_MANAGER[v["category"]], "stage": v["stage"]}

    file_lines = lambda v: sorted(r["line"] for r in rows if r["v"] is v)  # noqa: E731

    counts = {
        "seed": seed,
        "company": COMPANY,
        "admin": ADMIN,
        "category_managers": MANAGERS,
        "restricted_login": RESTRICTED,
        "valid_for_test_dates": "2026-09-01 to 2027-12-01 (insurance expiries are on or before 2026-08-28 or in 2028)",
        "baseline": {
            "staff_role": "Category Manager",
            "viewer_role": "Viewer",
            "main_entity": "vendor",
            "main_entity_plural": "vendors",
            "scope_rule": f"vendors in {RESTRICTED}'s categories, Ingredients and Packaging",
            "scope_count": sum(1 for v in vendors if in_scope(v)),
            "out_of_scope_example": vinfo(out_of_scope),
            "kpis": [
                {"name": "Vendors in onboarding (stage New, Documents, or Review)", "value": len(onboarding)},
                {"name": "Approved vendors", "value": len(approved)},
                {"name": "Approved vendors with insurance lapsed or expiring within 30 days", "value": len(lapsed)},
                {"name": "Annual spend with approved vendors", "value": approved_spend},
            ],
            "scoped_kpi_1": sum(1 for v in onboarding if in_scope(v)),
            "search": {"term": search_term, "count": len(search_hits), "matches": search_hits,
                       "count_without_dedupe": sum(1 for r in rows if search_term.lower() in r["cells"][1].lower())},
            "filter": {"field": "Category", "value": "Packaging", "count": filter_count,
                       "count_exact_text_match": sum(1 for r in rows if r["role"] == "unique" and r["cells"][2] == "Packaging")},
            "sort": {"field": "Annual Spend", "top": top["name"], "top_file_value": next(r["cells"][8] for r in rows if r["v"] is top and r["role"] == "unique"),
                     "top_numeric": top["spend"], "text_sort_top": raw_text_top["cells"][1], "text_sort_top_file_value": raw_text_top["cells"][8]},
            "export": {"rows": N_UNIQUE, "columns": ["Vendor No", "Vendor Name", "Category", "Tax ID", "Stage", "Annual Spend"]},
            "required_field": "Category",
        },
        "vendors": {
            "file_rows_excluding_header": len(rows),
            "exact_duplicate_rows": N_EXACT_DUPES,
            "reentered_duplicate_rows": N_REENTERED,
            "unique_vendors_after_dedupe": N_UNIQUE,
            "dedupe_rule": "Two rows are the same vendor when their Tax ID digits match (dash or no dash). Rows with a blank Tax ID are all different vendors.",
            "wrong_counts": {"no_dedupe": len(rows), "exact_rows_only": len(rows) - N_EXACT_DUPES,
                             "blank_tax_ids_collapsed": N_UNIQUE - (N_BLANK_TAX - 1)},
            "per_category": {c: sum(1 for v in vendors if v["category"] == c) for c in CATEGORIES},
            "per_manager": {m: sum(1 for v in vendors if CATEGORY_MANAGER[v["category"]] == m) for m in MANAGERS},
            "restricted_scope_if_category_matched_as_written": wrong_rosa_exact,
            "per_stage": {s: len(by_stage[s]) for s in STAGES},
            "blank_tax_id_vendors": sorted(v["name"] for v in blank_tax),
            "unpadded_number_rows": N_UNPADDED_ROWS,
            "reentered_groups": [
                {"name": v["name"], "category": v["category"], "numbers": [v["no"], v["alias"]],
                 "tax_ids_as_written": [tax_fmt(v["tax"]), v["tax"]],
                 "names_as_written": [next(r["cells"][1] for r in rows if r["v"] is v and r["role"] == "unique"),
                                      next(r["cells"][1] for r in rows if r["v"] is v and r["role"] == "reentered")],
                 "file_lines": file_lines(v)} for v in reentered],
            "exact_duplicate_vendors": sorted(v["name"] for v in exact_dupes),
        },
        "documents": {
            "file_rows_excluding_header": len(docs),
            "duplicate_rows": len(doc_dupes),
            "required": {"all vendors": GENERAL_DOCS, "Ingredients vendors also": [FSC]},
            "vendors_with_complete_documents": sum(1 for v in vendors if not missing_by_vendor[v["no"]]),
            "vendor_a_unpadded_numbers": {**vinfo(vendor_a), "numbers_as_filed": sorted({d["cells"][0] for d in docs if d["v"] is vendor_a}),
                                          "documents": GENERAL_DOCS},
            "vendor_c_filed_under_second_number": {**vinfo(vendor_c), "second_number": vendor_c["alias"],
                                                   "documents_under_second_number": [k for k in GENERAL_DOCS if any(
                                                       d["v"] is vendor_c and d["kind"] == k and d["cells"][0] == vendor_c["alias"] for d in docs)],
                                                   "file_lines": sorted(i + 2 for i, d in enumerate(docs) if d["v"] is vendor_c)},
            "vendor_b_missing_food_safety": {**vinfo(vendor_b), "has": GENERAL_DOCS, "missing": [FSC]},
            "vendor_d_packaging_complete": {**vinfo(vendor_d), "has": GENERAL_DOCS},
            "vendor_f_expiry_before_issue": {**vinfo(vendor_f), "issued": "2026-03-16", "expires": "2025-03-16",
                                             "file_values": next(d["cells"][4:6] for d in docs if d["v"] is vendor_f and d["kind"] == COI)},
            "vendor_g_new_packaging": vinfo(vendor_g),
            "vendor_e_window_test": vinfo(vendor_e),
            "vendor_e2_renewal_task_test": vinfo(vendor_e2),
            "lapsed_approved_vendors": [
                {**vinfo(v), "coi_expires": next(d["expires"].isoformat() for d in docs if d["v"] is v and d["kind"] == COI),
                 "coi_expires_file_value": next(d["cells"][5] for d in docs if d["v"] is v and d["kind"] == COI),
                 "coi_document_name_as_written": next(d["cells"][2] for d in docs if d["v"] is v and d["kind"] == COI)}
                for v in lapsed_sorted],
        },
        "app_items": {
            "approved_after_vendor_b_approved": len(approved) + 1,
            "window_test": {"in_window_days_from_today": 20, "out_of_window_days_from_today": 45,
                            "figure_in_window": len(lapsed) + 1, "figure_out_of_window": len(lapsed)},
        },
        "changes": {
            "1_approved_spend_by_category": spend_by_cat,
            "1_lapsed_or_expiring_by_manager": lapsed_by_manager,
            "1_lapsed_vendor_names_by_manager": {m: sorted(v["name"] for v in lapsed if CATEGORY_MANAGER[v["category"]] == m) for m in MANAGERS},
            "2_restricted_renewal_tasks_from_import": lapsed_by_manager[RESTRICTED],
            "2_restricted_open_tasks_after_clearview_expiry_set": lapsed_by_manager[RESTRICTED] + 1,
            "2_renewal_task_vendor": vinfo(vendor_e2),
            "2_restricted_lapsed_vendors": sorted(v["name"] for v in lapsed if in_scope(v)),
            "3_stages_in_order": ["New", "Documents", "Review", "Compliance", "Approved", "Rejected"],
            "3_all_vendors_visible_to_compliance": N_UNIQUE,
        },
    }
    assert abs(sum(spend_by_cat.values()) - approved_spend) < 0.005

    header_v = ["Vendor No", "Vendor Name", "Category", "Tax ID", "Contact", "Email", "Phone", "Payment Terms",
                "Annual Spend", "Stage", "Added On"]
    header_d = ["Vendor No", "Vendor", "Document", "Received", "Issued", "Expires"]
    return {"counts": counts, "vendors": (header_v, [r["cells"] for r in rows]),
            "documents": (header_d, [d["cells"] for d in docs])}


def main() -> None:
    seed = argparse_seed()
    out = build(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "vendors.csv"), *out["vendors"])
    write_csv(os.path.join(SEED_DIR, "documents.csv"), *out["documents"])
    write_text(os.path.join(REF_DIR, "counts.json"), json.dumps(out["counts"], indent=2) + "\n")
    c = out["counts"]
    print(f"vendors.csv {c['vendors']['file_rows_excluding_header']} rows -> {c['vendors']['unique_vendors_after_dedupe']} vendors; "
          f"documents.csv {c['documents']['file_rows_excluding_header']} rows; scope {c['baseline']['scope_count']}")


if __name__ == "__main__":
    main()
