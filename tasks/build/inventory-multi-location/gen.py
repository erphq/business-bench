#!/usr/bin/env python3
"""Deterministic seed generator for the inventory-multi-location build task.

    python gen.py [--seed N]

Writes:
  seed/items.csv          106 rows -> 100 items (exact duplicates, a trailing-space item number with the
                          description in capitals, unit costs partly as "$3,480.00" strings, category case variants)
  seed/stock.csv          236 rows (CRLF) -> 231 stock lines across Reno, Sacramento, Stockton (warehouse written as
                          codes and variants, item numbers that lost their leading zero, on-hand with thousands
                          separators, exact duplicate rows, mixed count dates, one impossible negative on-hand)
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the canonical public variant (checklist.md quotes its numbers). Other seeds re-roll item numbers,
which warehouses stock what, quantities, and jitter costs; counts.json is recomputed from the truth.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import argparse_seed, date_variant, write_csv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

WAREHOUSES = ["Reno", "Sacramento", "Stockton"]
LEADS = {"Reno": "Dale Brennan", "Sacramento": "Marisol Vega", "Stockton": "Anh Tran"}
RESTRICTED = "Sacramento"
WAREHOUSE_VARIANTS = {"Reno": ["RENO", "Reno NV", "RNO"], "Sacramento": ["SAC", "Sacramento CA", "sacramento"],
                      "Stockton": ["STK", "Stockton ", "stockton"]}
STOCK_SHARE = {"Reno": 0.85, "Sacramento": 0.78, "Stockton": 0.67}
ADJUST_REASONS = ["Damaged", "Count correction", "Theft or loss", "Found stock", "Expired"]
N_ITEMS = 100
N_ITEM_EXACT_DUPES = 4
N_ITEM_TRIM_DUPES = 2
N_STOCK_EXACT_DUPES = 5
NEGATIVE_ON_HAND = -4
MAX_ON_HAND = 1450
APPROVAL_LIMIT = 500.00

ITEM_COLUMNS = ["Item #", "Description", "Category", "UOM", "Unit Cost", "Preferred Supplier"]
STOCK_COLUMNS = ["Warehouse", "Item #", "Bin", "On Hand", "Reorder Point", "Last Counted"]

# (description, category, uom, unit cost)
CATALOG = [
    ("Multifold paper towels 16/250", "Paper Goods", "Case", 38.50), ("C-fold paper towels 12/150", "Paper Goods", "Case", 34.20),
    ("Hardwound roll towel 8in x 800ft 6/cs", "Paper Goods", "Case", 42.75), ("Center-pull towel 6/600", "Paper Goods", "Case", 39.90),
    ("Jumbo toilet tissue 9in 12/cs", "Paper Goods", "Case", 36.40), ("Standard bath tissue 2-ply 96/cs", "Paper Goods", "Case", 52.80),
    ("Coreless toilet tissue 36/cs", "Paper Goods", "Case", 48.60), ("Facial tissue 30/100", "Paper Goods", "Case", 29.75),
    ("Dinner napkin 1/8 fold 3000/cs", "Paper Goods", "Case", 44.10), ("Beverage napkin white 4000/cs", "Paper Goods", "Case", 27.30),
    ("Dispenser napkin 6000/cs", "Paper Goods", "Case", 41.20), ("Toilet seat covers 20/250", "Paper Goods", "Case", 31.60),
    ("Kitchen roll towel 30/85", "Paper Goods", "Case", 33.90), ("Wiper roll blue 4/cs", "Paper Goods", "Case", 58.25),
    ("Can liner 24x33 0.6mil 1000/cs", "Can Liners", "Case", 24.80), ("Can liner 33x40 1.2mil 250/cs", "Can Liners", "Case", 32.40),
    ("Can liner 38x58 1.5mil 100/cs", "Can Liners", "Case", 29.90), ("Can liner 40x46 16mic 250/cs", "Can Liners", "Case", 27.60),
    ("Can liner 43x47 1.5mil black 100/cs", "Can Liners", "Case", 30.75), ("Can liner 24x24 8mic 1000/cs", "Can Liners", "Case", 21.40),
    ("Can liner 30x37 13mic 500/cs", "Can Liners", "Case", 26.10), ("Compostable bag 33 gal 150/cs", "Can Liners", "Case", 68.90),
    ("Recycling liner clear 40x46 250/cs", "Can Liners", "Case", 34.30), ("Contractor bag 42 gal 3mil 32/cs", "Can Liners", "Case", 38.90),
    ("Neutral floor cleaner 4x1 gal", "Chemicals", "Case", 46.80), ("Glass cleaner ready-to-use 12x32oz", "Chemicals", "Case", 28.40),
    ("Disinfectant quat concentrate 4x1 gal", "Chemicals", "Case", 62.50), ("Degreaser heavy duty 4x1 gal", "Chemicals", "Case", 54.30),
    ("Bathroom cleaner acid 12x32oz", "Chemicals", "Case", 36.90), ("Floor finish 25% solids 5 gal", "Chemicals", "Pail", 118.00),
    ("Floor stripper 5 gal", "Chemicals", "Pail", 96.50), ("Dish detergent manual 4x1 gal", "Chemicals", "Case", 38.70),
    ("Dishmachine detergent 5 gal", "Chemicals", "Pail", 84.20), ("Rinse aid 5 gal", "Chemicals", "Pail", 92.40),
    ("Sanitizer quat 4x1 gal", "Chemicals", "Case", 58.60), ("Foaming hand soap 6x1000ml", "Chemicals", "Case", 64.80),
    ("Hand sanitizer gel 4x1000ml", "Chemicals", "Case", 49.90), ("Carpet extraction cleaner 4x1 gal", "Chemicals", "Case", 52.10),
    ("Oven and grill cleaner 12x32oz", "Chemicals", "Case", 41.30), ("Stainless steel polish 12x17oz", "Chemicals", "Case", 44.70),
    ("Bleach 6% 6x1 gal", "Chemicals", "Case", 18.90), ("Enzyme drain treatment 4x1 gal", "Chemicals", "Case", 71.40),
    ("Graffiti remover 12x16oz", "Chemicals", "Case", 88.60), ("Odor neutralizer 12x15oz", "Chemicals", "Case", 39.50),
    ("Nitrile gloves powder-free M 10x100", "Gloves", "Case", 72.40), ("Nitrile gloves powder-free L 10x100", "Gloves", "Case", 72.40),
    ("Nitrile gloves powder-free XL 10x100", "Gloves", "Case", 74.10), ("Vinyl gloves L 10x100", "Gloves", "Case", 38.60),
    ("Poly food service gloves 10x500", "Gloves", "Case", 22.80), ("Latex gloves M 10x100", "Gloves", "Case", 61.20),
    ("Chemical resistant gloves 12 pair", "Gloves", "Dozen", 44.90), ("Cut resistant gloves L 12 pair", "Gloves", "Dozen", 96.00),
    ("Foam cup 12oz 1000/cs", "Disposables", "Case", 36.20), ("Paper hot cup 12oz 1000/cs", "Disposables", "Case", 58.40),
    ("Hot cup lid 12-20oz 1000/cs", "Disposables", "Case", 42.90), ("Clear PET cup 16oz 1000/cs", "Disposables", "Case", 64.30),
    ("Straw wrapped jumbo 12x250", "Disposables", "Case", 19.80), ("Clamshell container 9x9 200/cs", "Disposables", "Case", 47.60),
    ("Fiber takeout box 8x8 200/cs", "Disposables", "Case", 71.20), ("Deli container 32oz 240/cs", "Disposables", "Case", 52.90),
    ("Portion cup 2oz 2500/cs", "Disposables", "Case", 34.70), ("Heavy cutlery fork 1000/cs", "Disposables", "Case", 24.60),
    ("Heavy cutlery knife 1000/cs", "Disposables", "Case", 26.30), ("Cutlery kit fork-knife-napkin 250/cs", "Disposables", "Case", 29.40),
    ("Foil sheet 12x10.75 500x6", "Disposables", "Case", 48.20), ("Film wrap 18in x 2000ft", "Disposables", "Roll", 21.90),
    ("Aluminum pan full size 50/cs", "Disposables", "Case", 63.70), ("Pizza box 16in 50/bundle", "Disposables", "Bundle", 27.80),
    ("Paper plate 9in 500/cs", "Disposables", "Case", 33.10), ("Bakery bag 6.5x9 1000/cs", "Disposables", "Case", 17.60),
    ("Hair net 144/box", "Disposables", "Box", 12.60),
    ("Wet mop head 24oz cotton 12/cs", "Janitorial Tools", "Case", 42.60), ("Microfiber flat mop pad 18in 12/pk", "Janitorial Tools", "Pack", 38.40),
    ("Mop bucket with wringer 35qt", "Janitorial Tools", "Each", 124.00), ("Upright angle broom", "Janitorial Tools", "Each", 11.80),
    ("Push broom 24in", "Janitorial Tools", "Each", 24.90), ("Lobby dust pan with broom", "Janitorial Tools", "Each", 19.60),
    ("Microfiber cloths 16x16 12/pk", "Janitorial Tools", "Pack", 9.80), ("Toilet bowl brush with caddy", "Janitorial Tools", "Each", 7.40),
    ("Window squeegee 14in", "Janitorial Tools", "Each", 13.20), ("Wet floor sign", "Janitorial Tools", "Each", 16.70),
    ("Trigger sprayer 32oz 12/pk", "Janitorial Tools", "Pack", 14.30), ("Scrub sponge 20/cs", "Janitorial Tools", "Case", 18.40),
    ("Stainless scrubber 12/pk", "Janitorial Tools", "Pack", 11.90), ("Grill brick 12/cs", "Janitorial Tools", "Case", 26.40),
    ("Floor pad 20in red 5/cs", "Janitorial Tools", "Case", 28.60), ("Floor pad 20in black stripping 5/cs", "Janitorial Tools", "Case", 31.20),
    ("Trash receptacle 32 gal gray", "Janitorial Tools", "Each", 38.90), ("Dolly for 32 gal receptacle", "Janitorial Tools", "Each", 29.50),
    ("Foam soap dispenser 1000ml", "Janitorial Tools", "Each", 21.30), ("Roll towel dispenser mechanical", "Janitorial Tools", "Each", 46.80),
    ("Jumbo tissue dispenser twin", "Janitorial Tools", "Each", 39.40),
    ("Backpack vacuum 6qt", "Equipment", "Each", 389.00), ("Upright vacuum 14in commercial", "Equipment", "Each", 264.00),
    ("Wet dry vac 16 gal", "Equipment", "Each", 312.00), ("Carpet extractor 12 gal", "Equipment", "Each", 1240.00),
    ("Floor burnisher 20in 1500rpm", "Equipment", "Each", 1890.00), ("Floor machine 17in 175rpm", "Equipment", "Each", 985.00),
    ("Auto scrubber 20in battery", "Equipment", "Each", 3480.00), ("Pressure washer electric 2000psi", "Equipment", "Each", 649.00),
    ("Air mover 3-speed", "Equipment", "Each", 158.00), ("Hand dryer high speed", "Equipment", "Each", 438.00),
    ("Chemical dispensing station 4-product", "Equipment", "Each", 214.00), ("Scrubber battery 12V AGM", "Equipment", "Each", 229.00),
    ("Vacuum bags 10/pk", "Equipment", "Pack", 18.60), ("Squeegee blade set 20in", "Equipment", "Set", 42.80),
]
SUPPLIERS = ["Pacific Paper Co", "Valley Chemical Supply", "Summit Poly", "WestPak Disposables", "Truckee Janitorial Wholesale",
             "Gold Country Equipment", "Delta Glove & Safety"]
FORCED = ["Auto scrubber 20in battery", "Floor burnisher 20in 1500rpm", "Graffiti remover 12x16oz",
          "Scrub sponge 20/cs", "Wet floor sign", "Push broom 24in", "Hand sanitizer gel 4x1000ml", "Portion cup 2oz 2500/cs",
          "Straw wrapped jumbo 12x250", "Degreaser heavy duty 4x1 gal", "Foam cup 12oz 1000/cs", "Grill brick 12/cs"]
SEARCH_CANDIDATES = ["burnisher", "graffiti", "extractor", "enzyme", "compostable", "dolly", "hair net", "pizza box"]


def fmt_cost(v: float, currency: bool) -> str:
    return f"${v:,.2f}" if currency else f"{v:.2f}"


def fmt_qty(q: int) -> str:
    return f"{q:,}" if q >= 1000 else str(q)


def build(rng: random.Random, seed: int) -> dict:
    # ------------------------------------------------------------------ items
    optional = [c for c in CATALOG if c[0] not in FORCED]
    rng.shuffle(optional)
    chosen = [c for c in CATALOG if c[0] in FORCED] + optional[:N_ITEMS - len(FORCED)]
    chosen.sort(key=lambda c: CATALOG.index(c))
    numbers = set()
    items = []
    for desc, cat, uom, cost in chosen:
        while True:
            n = f"0{rng.randint(1000, 9999)}" if rng.random() < 0.3 else str(rng.randint(10000, 69999))
            if n not in numbers:
                numbers.add(n)
                break
        if seed != 0:
            cost = round(cost * rng.uniform(0.9, 1.1), 2)
        items.append({"no": n, "desc": desc, "cat": cat, "uom": uom, "cost": cost,
                      "supplier": SUPPLIERS[["Paper Goods", "Chemicals", "Can Liners", "Disposables", "Janitorial Tools", "Equipment", "Gloves"].index(cat)]})
    by_desc = {it["desc"]: it for it in items}

    # ------------------------------------------------------------------ stock lines (truth)
    lines = []
    for it in items:
        whs = [w for w in WAREHOUSES if rng.random() < STOCK_SHARE[w]] or [rng.choice(WAREHOUSES)]
        for w in whs:
            equip = it["cat"] == "Equipment"
            rp = rng.randint(1, 3) if equip else rng.choice([10, 12, 15, 20, 24, 30, 40, 50, 60])
            k = rng.random()
            if k < 0.08:
                oh = rng.randint(0, rp - 1)
            elif k < 0.11:
                oh = rp
            else:
                oh = rp + rng.randint(1, 12 if equip else 320)
            lines.append({"wh": w, "item": it, "rp": rp, "oh": oh,
                          "bin": f"{rng.choice('ABCDEF')}-{rng.randint(1, 24):02d}-{rng.randint(1, 5)}",
                          "counted": date(2026, 6, 1) + timedelta(days=rng.randint(0, 95))})

    def line(desc, wh):
        return next((ln for ln in lines if ln["item"]["desc"] == desc and ln["wh"] == wh), None)

    def force(desc, wh, oh, rp):
        ln = line(desc, wh)
        if ln is None:
            ln = {"wh": wh, "item": by_desc[desc], "rp": rp, "oh": oh, "bin": f"B-{rng.randint(1, 24):02d}-1",
                  "counted": date(2026, 6, 1) + timedelta(days=rng.randint(0, 95))}
            lines.append(ln)
        ln["oh"], ln["rp"] = oh, rp
        return ln

    # roles pinned onto named items so the checklist can cite them
    transfer_item = "Hand sanitizer gel 4x1000ml"
    force(transfer_item, "Reno", 48, 15)
    force(transfer_item, "Sacramento", 6, 10)
    adjust_item = "Scrub sponge 20/cs"
    by_desc[adjust_item]["cost"] = 18.40
    force(adjust_item, "Reno", 45, 8)
    force(adjust_item, "Sacramento", 60, 12)
    alert_item = "Degreaser heavy duty 4x1 gal"
    force(alert_item, "Reno", 15, 12)
    at_rp_item = "Portion cup 2oz 2500/cs"
    force(at_rp_item, "Reno", 12, 12)
    above_rp_item = "Foam cup 12oz 1000/cs"
    force(above_rp_item, "Reno", 13, 12)
    boundary_item = "Push broom 24in"
    by_desc[boundary_item]["cost"] = 20.00
    force(boundary_item, "Sacramento", 40, 10)
    negative_item = "Wet floor sign"
    force(negative_item, "Stockton", NEGATIVE_ON_HAND, 10)
    force(negative_item, "Reno", 22, 10)
    max_item = "Straw wrapped jumbo 12x250"
    force(max_item, "Reno", MAX_ON_HAND, 60)
    for w in WAREHOUSES:
        ln = line(max_item, w)
        if ln and w != "Reno":
            ln["oh"] = min(ln["oh"], 900)
    search_item = "Floor burnisher 20in 1500rpm"
    for w, (oh, rp) in zip(WAREHOUSES, [(3, 1), (2, 1), (1, 1)]):
        force(search_item, w, oh, rp)
    oos_item = "Grill brick 12/cs"
    force(oos_item, "Reno", 36, 12)
    for ln in lines:  # nothing else may exceed the pinned maximum on-hand
        if ln["oh"] >= MAX_ON_HAND and ln["item"]["desc"] != max_item:
            ln["oh"] = 999
    lines.sort(key=lambda ln: (WAREHOUSES.index(ln["wh"]), ln["item"]["no"]))

    # leading-zero item for the link check: a zero-led item stocked at all three warehouses
    zero_items = sorted((it for it in items if it["no"].startswith("0") and it["desc"] not in
                         {transfer_item, adjust_item, alert_item, at_rp_item, above_rp_item, boundary_item, negative_item,
                          max_item, search_item, oos_item}
                         and all(line(it["desc"], w) for w in WAREHOUSES)), key=lambda it: it["no"])
    zero_item = zero_items[0]
    specials = {transfer_item, adjust_item, alert_item, at_rp_item, above_rp_item, boundary_item, negative_item, max_item,
                search_item, oos_item, zero_item["desc"]}
    test_item = sorted((it for it in items if it["desc"] not in specials and line(it["desc"], "Stockton") is None
                        and it["cat"] != "Equipment"), key=lambda it: it["no"])[0]

    # ------------------------------------------------------------------ written files
    currency_descs = sorted([it["desc"] for it in items if it["cat"] == "Equipment" and it["cost"] >= 200] +
                            [it["desc"] for it in rng.sample([i for i in items if i["cat"] != "Equipment" and i["desc"] not in (adjust_item, boundary_item)], 6)])
    trim_src = rng.sample([i for i in range(N_ITEMS) if not items[i]["no"].startswith("0") and items[i]["desc"] not in FORCED], N_ITEM_TRIM_DUPES)
    exact_src = rng.sample([i for i in range(N_ITEMS) if i not in trim_src], N_ITEM_EXACT_DUPES)
    item_rows = []
    cat_variant_rows = 0
    for i, it in enumerate(items):
        cat_w = it["cat"]
        if rng.random() < 0.12:
            cat_w = rng.choice([it["cat"].upper(), it["cat"].lower()])
            cat_variant_rows += 1
        row = [it["no"], it["desc"], cat_w, it["uom"], fmt_cost(it["cost"], it["desc"] in currency_descs), it["supplier"]]
        item_rows.append(row)
    for i in exact_src:
        item_rows.append(list(item_rows[i]))
    for i in trim_src:
        it = items[i]
        item_rows.append([it["no"] + " ", it["desc"].upper(), it["cat"], it["uom"], fmt_cost(it["cost"], False), it["supplier"]])
    rng.shuffle(item_rows)

    stock_rows = []
    dropped_zero_rows = 0
    for ln in lines:
        wh_w = ln["wh"] if rng.random() < 0.7 else rng.choice(WAREHOUSE_VARIANTS[ln["wh"]])
        no = ln["item"]["no"]
        if no.startswith("0") and (rng.random() < 0.5 or (ln["item"] is zero_item and ln["wh"] == "Reno")):
            no = no.lstrip("0")
            dropped_zero_rows += 1
        stock_rows.append([wh_w, no, ln["bin"], fmt_qty(ln["oh"]), str(ln["rp"]), date_variant(ln["counted"], rng.choice([0, 1, 2, 3, 4, 6]))])
    dupe_src = rng.sample(range(len(stock_rows)), N_STOCK_EXACT_DUPES)
    for i in dupe_src:
        stock_rows.append(list(stock_rows[i]))
    rng.shuffle(stock_rows)

    # ------------------------------------------------------------------ truth figures
    def val(ln, keep_negative=False):
        q = ln["oh"] if keep_negative else max(ln["oh"], 0)
        return q * ln["item"]["cost"]

    def value(wh=None, keep_negative=False, cat=None):
        return round(sum(val(ln, keep_negative) for ln in lines if (wh is None or ln["wh"] == wh) and (cat is None or ln["item"]["cat"] == cat)), 2)

    def alerts(wh=None):
        return [ln for ln in lines if ln["oh"] <= ln["rp"] and (wh is None or ln["wh"] == wh)]

    per_wh = {w: {"lines": sum(1 for ln in lines if ln["wh"] == w), "reorder_alerts": len(alerts(w)),
                  "lines_exactly_at_reorder_point": sum(1 for ln in lines if ln["wh"] == w and ln["oh"] == ln["rp"]),
                  "value": value(w), "value_if_negative_kept": value(w, True)} for w in WAREHOUSES}
    by_cost_text = sorted(item_rows, key=lambda r: r[4], reverse=True)
    by_oh_text = sorted(stock_rows, key=lambda r: r[3], reverse=True)
    max_cost_item = max(items, key=lambda it: it["cost"])
    assert sum(1 for it in items if it["cost"] == max_cost_item["cost"]) == 1
    assert sum(1 for ln in lines if ln["oh"] == MAX_ON_HAND) == 1
    search_term = next(t for t in SEARCH_CANDIDATES
                       if sum(1 for it in items if t in it["desc"].lower() or t in it["cat"].lower() or t in it["supplier"].lower()) == 1
                       and any(t in it["desc"].lower() for it in items))
    search_lines = [ln for ln in lines if search_term in ln["item"]["desc"].lower()]
    cats = sorted({it["cat"] for it in items})
    t_reno, t_sac = line(transfer_item, "Reno"), line(transfer_item, "Sacramento")
    adj = line(adjust_item, "Reno")
    neg = line(negative_item, "Stockton")
    total = value()

    counts = {
        "seed": seed,
        "company": {"warehouses": WAREHOUSES, "leads": LEADS, "restricted_login": LEADS[RESTRICTED], "restricted_warehouse": RESTRICTED,
                    "roles": {"admin": "Admin (owner)", "staff": "Warehouse Lead", "viewer": "Bookkeeper (read-only)"},
                    "adjustment_reasons_suggested": ADJUST_REASONS},
        "tester_records": {"item": test_item["no"], "description": test_item["desc"], "warehouse": "Stockton", "on_hand": 0,
                           "reorder_point": 5, "note": "stock items the tester creates use this item at Stockton (not stocked there) and are deleted when the item is done"},
        "items": {
            "file_rows_excluding_header": len(item_rows),
            "exact_duplicate_rows": N_ITEM_EXACT_DUPES,
            "trailing_space_duplicate_rows": N_ITEM_TRIM_DUPES,
            "unique_items_after_dedupe": N_ITEMS,
            "dedupe_rule": "Two rows are the same item when Item # matches after trimming spaces; item numbers are text and keep leading zeros.",
            "wrong_counts": {"no_dedupe": len(item_rows), "exact_rows_only": len(item_rows) - N_ITEM_EXACT_DUPES},
            "trailing_space_duplicates": sorted(f"{items[i]['no']} {items[i]['desc']}" for i in trim_src),
            "items_with_leading_zero": sum(1 for it in items if it["no"].startswith("0")),
            "categories": cats,
            "category_rows_in_other_case": cat_variant_rows,
            "currency_string_cost_rows": len(currency_descs),
            "highest_unit_cost": {"item": max_cost_item["no"], "description": max_cost_item["desc"],
                                  "file_value": fmt_cost(max_cost_item["cost"], max_cost_item["desc"] in currency_descs),
                                  "numeric": max_cost_item["cost"],
                                  "text_sort_would_put_first": f"{by_cost_text[0][0].strip()} {by_cost_text[0][1]} ({by_cost_text[0][4]})"},
        },
        "stock": {
            "file_rows_excluding_header": len(stock_rows),
            "exact_duplicate_rows": N_STOCK_EXACT_DUPES,
            "unique_stock_lines": len(lines),
            "dedupe_rule": "A stock line is one item at one warehouse; warehouse names normalise RNO/RENO/Reno NV -> Reno, SAC/sacramento/Sacramento CA -> Sacramento, STK/stockton/'Stockton ' -> Stockton; item numbers written without their leading zero link to the zero-led item.",
            "wrong_counts": {"no_dedupe": len(stock_rows)},
            "rows_with_leading_zero_dropped": dropped_zero_rows,
            "per_warehouse": per_wh,
            "reorder_rule": "a line needs reordering when On Hand is at or below its Reorder Point",
            "reorder_alerts": len(alerts()),
            "lines_exactly_at_reorder_point": sum(1 for ln in lines if ln["oh"] == ln["rp"]),
            "reorder_alerts_if_strictly_below": sum(1 for ln in lines if ln["oh"] < ln["rp"]),
            "inventory_value": total,
            "inventory_value_if_negative_line_kept_at_minus_4": value(keep_negative=True),
            "negative_on_hand": {"item": negative_item and by_desc[negative_item]["no"], "description": negative_item, "warehouse": "Stockton",
                                 "on_hand": NEGATIVE_ON_HAND, "unit_cost": by_desc[negative_item]["cost"],
                                 "value_difference_if_kept": round(-NEGATIVE_ON_HAND * by_desc[negative_item]["cost"], 2)},
            "max_on_hand": {"item": by_desc[max_item]["no"], "description": max_item, "warehouse": "Reno", "file_value": fmt_qty(MAX_ON_HAND),
                            "text_sort_would_put_first": f"{by_oh_text[0][1]} at {by_oh_text[0][0].strip()} ({by_oh_text[0][3]})"},
            "leading_zero_link_check": {"item": zero_item["no"], "description": zero_item["desc"],
                                        "on_hand": {w: line(zero_item["desc"], w)["oh"] for w in WAREHOUSES},
                                        "reno_row_written_as": zero_item["no"].lstrip("0")},
            "reorder_examples": {
                "at_point": {"item": by_desc[at_rp_item]["no"], "description": at_rp_item, "warehouse": "Reno", "on_hand": 12, "reorder_point": 12},
                "one_above": {"item": by_desc[above_rp_item]["no"], "description": above_rp_item, "warehouse": "Reno", "on_hand": 13, "reorder_point": 12},
            },
            "search_check": {"term": search_term, "expected_results": len(search_lines), "item": by_desc[search_item]["no"]},
            "filter_check": {"field": "Warehouse", "value": "Stockton", "expected_results": per_wh["Stockton"]["lines"]},
            "sort_check": {"field": "On Hand", "direction": "descending", "first": f"{by_desc[max_item]['no']} {max_item} at Reno"},
            "export_check": {"rows": len(lines), "columns": ["Item #", "Description", "Warehouse", "On Hand", "Reorder Point"]},
            "out_of_scope_line": {"item": by_desc[oos_item]["no"], "description": oos_item, "warehouse": "Reno", "on_hand": 36},
        },
        "dashboard": {"reorder_alerts": len(alerts()), "inventory_value": total,
                      "inventory_value_if_negative_line_kept_at_minus_4": value(keep_negative=True),
                      "reno_value": per_wh["Reno"]["value"], "items": N_ITEMS,
                      "restricted_reorder_alerts": per_wh[RESTRICTED]["reorder_alerts"]},
        "checks": {
            "transfer": {"item": by_desc[transfer_item]["no"], "description": transfer_item, "qty": 10, "from": "Reno", "to": "Sacramento",
                         "from_before": t_reno["oh"], "from_after": t_reno["oh"] - 10, "to_before": t_sac["oh"], "to_after": t_sac["oh"] + 10,
                         "to_reorder_point": t_sac["rp"], "value_change": 0.0, "over_limit_qty": t_reno["oh"] + 1,
                         "company_alerts_after": len(alerts()) - 1},
            "adjustment": {"item": by_desc[adjust_item]["no"], "description": adjust_item, "warehouse": "Reno", "qty": -3,
                           "unit_cost": adj["item"]["cost"], "on_hand_before": adj["oh"], "on_hand_after": adj["oh"] - 3,
                           "value_change": round(-3 * adj["item"]["cost"], 2), "value_decrease": round(3 * adj["item"]["cost"], 2), "reason": "Damaged",
                           "company_value_after": round(total - 3 * adj["item"]["cost"], 2),
                           "reno_value_after": round(per_wh["Reno"]["value"] - 3 * adj["item"]["cost"], 2)},
            "alert_trigger": {"item": by_desc[alert_item]["no"], "description": alert_item, "warehouse": "Reno", "on_hand_before": 15,
                              "reorder_point": 12, "adjust_by": -3, "on_hand_after": 12,
                              "reno_alerts_before": per_wh["Reno"]["reorder_alerts"], "reno_alerts_after": per_wh["Reno"]["reorder_alerts"] + 1,
                              "company_alerts_before": len(alerts()), "company_alerts_after": len(alerts()) + 1},
            "restricted_transfer_out": {"item": by_desc[transfer_item]["no"], "qty": 1, "from": "Sacramento", "to": "Reno",
                                        "sacramento_after": t_sac["oh"] - 1, "reno_after": t_reno["oh"] + 1},
        },
        "changes": {
            "1_valuation_report": {
                "categories": cats,
                "by_category_and_warehouse": {c: {w: value(w, cat=c) for w in WAREHOUSES} | {"total": value(cat=c)} for c in cats},
                "warehouse_totals": {w: per_wh[w]["value"] for w in WAREHOUSES},
                "grand_total": total,
                "grand_total_if_negative_line_kept": value(keep_negative=True),
                "negative_line_category": by_desc[negative_item]["cat"],
                "negative_line_alternative": {"category": by_desc[negative_item]["cat"], "warehouse": "Stockton",
                                              "cell_if_kept": round(value("Stockton", True, by_desc[negative_item]["cat"]), 2),
                                              "category_total_if_kept": round(value(None, True, by_desc[negative_item]["cat"]), 2),
                                              "stockton_total_if_kept": per_wh["Stockton"]["value_if_negative_kept"]},
            },
            "2_adjustment_approval": {"limit": APPROVAL_LIMIT, "rule": "adjustments worth more than 500.00 at cost wait for admin approval; 500.00 or less apply at once",
                                      "over_limit": {"item": by_desc[adjust_item]["no"], "description": adjust_item, "warehouse": "Sacramento", "qty": -30,
                                                     "unit_cost": 18.40, "value": 552.00, "on_hand_before": 60, "on_hand_after_approval": 30,
                                                     "company_value_after_approval": round(total - 552.00, 2)},
                                      "at_limit": {"item": by_desc[boundary_item]["no"], "description": boundary_item, "warehouse": "Sacramento", "qty": -25,
                                                   "unit_cost": 20.00, "value": 500.00, "on_hand_before": 40, "on_hand_after": 15,
                                                   "company_value_after": round(total - 500.00, 2)}},
            "3_two_step_transfer": {"item": by_desc[transfer_item]["no"], "description": transfer_item, "qty": 10, "from": "Reno", "to": "Sacramento",
                                    "reno_after_ship": t_reno["oh"] - 10, "sacramento_after_ship": t_sac["oh"], "in_transit_after_ship": 10,
                                    "sacramento_after_receipt": t_sac["oh"] + 10, "in_transit_after_receipt": 0,
                                    "sacramento_if_received_twice": t_sac["oh"] + 20,
                                    "company_value_unchanged": total},
        },
    }
    return {"item_rows": item_rows, "stock_rows": stock_rows, "counts": counts}


def main() -> None:
    seed = argparse_seed(0)
    rng = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    out = build(rng, seed)
    write_csv(os.path.join(SEED_DIR, "items.csv"), ITEM_COLUMNS, out["item_rows"])
    write_csv(os.path.join(SEED_DIR, "stock.csv"), STOCK_COLUMNS, out["stock_rows"], crlf=True)
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out["counts"], indent=2) + "\n")
    s = out["counts"]["stock"]
    print(f"items.csv: {out['counts']['items']['file_rows_excluding_header']} rows -> {N_ITEMS} items")
    print(f"stock.csv: {s['file_rows_excluding_header']} rows -> {s['unique_stock_lines']} lines "
          f"{ {w: v['lines'] for w, v in s['per_warehouse'].items()} }; alerts {s['reorder_alerts']}; value {s['inventory_value']:.2f}")


if __name__ == "__main__":
    main()
