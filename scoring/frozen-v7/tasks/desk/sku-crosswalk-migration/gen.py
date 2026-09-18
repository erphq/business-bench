#!/usr/bin/env python3
"""sku-crosswalk-migration: a bike shop's old POS inventory moved onto the distributor's new SKUs.

    python gen.py [--seed N] [--naive DIR]

Business: a two-location bike shop switching point-of-sale systems. The new system uses the distributor's
consolidated catalog codes, so several of the shop's old codes (the same item bought under a second supplier's code,
in bulk packaging, or across model years) collapse into one new code. The distributor sent a crosswalk; the owner wants the opening catalog for the new system.

Traps (each caught by a check, see task.yaml):
  * several old SKUs map to one new SKU and their stock must be added together (check: on hand per SKU)
  * stock is exported per location (Main, Warehouse), two rows for most SKUs (check: on hand per SKU)
  * the crosswalk's Old SKU column carries trailing (and a few leading) spaces, so an exact join misses a
    third of the mappings and those items look unmapped                          (checks: catalog SKUs; on hand per SKU)
  * old SKUs that are not on the crosswalk (house-brand items) must stay, under their old code, marked
    unmapped - not dropped                                                         (checks: catalog SKUs; status)
  * the crosswalk covers the distributor's whole range; new SKUs none of whose old codes the shop stocks
    must not be added                                                              (checks: catalog SKUs; row count)
  * merged items keep the highest of their old prices, and prices are "$34.99" text (check: price)
  * July's draft crosswalk sits beside the final one with five groups mapped differently (check: catalog SKUs)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# (family, new description template, old code suffixes, old description template, sizes, price range).
# Old codes collapse because the shop bought the same item under a supplier's code or in bulk packaging.
FAMILIES = [
    ("TU", "Inner tube {size} Presta 48mm", ["", "-BULK", "-Q"], "Tube {size} presta", ["700x25", "700x28", "700x32", "650x47"], (7, 12)),
    ("TS", "Inner tube {size} Schrader", ["", "-BULK"], "Tube {size} schrader", ["26x2.1", "27.5x2.3", "29x2.2", "20x1.75"], (6, 11)),
    ("CH", "Chain {size}-speed 116L", ["-RTL", "-OEM", "-Q"], "Chain {size}sp", ["9", "10", "11", "12"], (24, 72)),
    ("BP", "Disc brake pads {size} resin", ["", "-OEM"], "Brake pad {size} resin", ["Shimano B01S", "SRAM Level", "Magura MT", "Tektro HD"], (12, 29)),
    ("CT", "Tire {size} folding", ["-MY25", "-MY26"], "Tire {size} fold", ["700x28 Gatorskin", "700x32 Marathon", "29x2.4 Minion", "27.5x2.6 Rekon"], (38, 79)),
    ("GR", "Lock-on grips {size}", ["", "-Q", "-J"], "Grips {size}", ["Ergon GE1", "ODI Ruffian", "ESI Chunky"], (19, 39)),
    ("BT", "Bar tape {size}", ["", "-J"], "Bar tape {size}", ["cork black", "Supacaz black", "Lizard Skins 2.5 black"], (16, 42)),
    ("CO", "CO2 cartridge {size} threaded", ["", "-BOX"], "CO2 {size} thr", ["16g", "25g"], (4, 9)),
    ("LU", "Chain lube {size}", ["", "-Q"], "Lube {size}", ["wet 4oz", "dry 4oz", "wax 4oz"], (9, 18)),
    ("CB", "Brake cable {size}", ["", "-SHOP"], "Cable brake {size}", ["road stainless", "MTB stainless"], (6, 22)),
    ("LT", "Light {size}", [""], "Light {size}", ["front 800lm", "rear 100lm", "front 1500lm"], (35, 129)),
    ("LK", "U-lock {size}", [""], "U-Lock {size}", ["mini 7in", "standard 9in"], (45, 99)),
]
SUFFIX_WORDS = {"": "", "-BULK": " (bulk)", "-Q": " (QBP code)", "-J": " (J&B code)", "-RTL": " retail box", "-OEM": " OEM",
                "-MY25": " 2025", "-MY26": " 2026", "-BOX": " (box of 20, sold each)", "-SHOP": " (shop box)"}
HOUSE = [("ZBW-BOTTLE-21", "Zephyr logo bottle 21oz", 12.99), ("ZBW-CAP-CYC", "Zephyr cycling cap", 24.99),
         ("ZBW-TEE-M", "Zephyr shop tee M", 29.99), ("ZBW-TEE-L", "Zephyr shop tee L", 29.99), ("ZBW-SOCK-SM", "Zephyr socks S/M", 14.99),
         ("ZBW-STICKER", "Zephyr sticker pack", 4.99), ("ZBW-KEYCHAIN", "Zephyr keychain tire lever", 9.99),
         ("ZBW-JERSEY-M", "Zephyr club jersey M", 89.99)]


def build(seed: int) -> dict:
    r = rng(seed)
    groups = []   # {new, new_desc, olds: [{sku, desc, price, carried}]}
    used_new = set()
    for fam, ndesc, variants, odesc, sizes, (plo, phi) in FAMILIES:
        for si, size in enumerate(sizes):
            new = f"{fam}{r.randint(1000, 9899)}"
            while new in used_new:
                new = f"{fam}{r.randint(1000, 9899)}"
            used_new.add(new)
            base = money(r, plo, phi)
            k = len(variants)
            chosen = variants if k == 1 else r.sample(variants, r.randint(1, k))
            olds = []
            for v in chosen:
                code_size = size.replace(" ", "").replace(".", "").upper()[:10]
                vv = v.strip("-")
                sku = f"{fam}-{code_size}" + (f"-{vv}" if vv else "")
                price = round(int(base * r.uniform(0.9, 1.15)) + 0.99, 2)
                olds.append({"sku": sku, "desc": odesc.format(size=size) + SUFFIX_WORDS[v], "price": price, "carried": True})
            groups.append({"new": new, "new_desc": ndesc.format(size=size), "olds": olds})
    # unique old SKUs
    seen = set()
    for g in groups:
        for o in g["olds"]:
            while o["sku"] in seen:
                o["sku"] = o["sku"] + "X"
            seen.add(o["sku"])
    # the distributor's range: some groups the shop never stocked, some variants the shop never stocked
    r.shuffle(groups)
    not_stocked_groups = groups[:5]
    for g in not_stocked_groups:
        for o in g["olds"]:
            o["carried"] = False
    for g in groups[5:]:
        if len(g["olds"]) >= 3 and r.random() < 0.5:
            g["olds"][-1]["carried"] = False
    groups.sort(key=lambda g: g["new"])
    # stock per location
    for g in groups:
        for o in g["olds"]:
            if not o["carried"]:
                continue
            o["stock"] = {"Main": r.randint(0, 18)}
            if r.random() < 0.65:
                o["stock"]["Warehouse"] = r.randint(0, 40)
    house = []
    for sku, desc, price in r.sample(HOUSE, 6):
        house.append({"sku": sku, "desc": desc, "price": price,
                      "stock": {"Main": r.randint(0, 30), **({"Warehouse": r.randint(5, 60)} if r.random() < 0.5 else {})}})
    # truth
    catalog = []
    for g in groups:
        carried = [o for o in g["olds"] if o["carried"]]
        if not carried:
            continue
        catalog.append({"sku": g["new"], "desc": g["new_desc"], "on_hand": sum(sum(o["stock"].values()) for o in carried),
                        "price": max(o["price"] for o in carried), "status": "mapped", "olds": carried})
    for h in house:
        catalog.append({"sku": h["sku"], "desc": h["desc"], "on_hand": sum(h["stock"].values()), "price": h["price"], "status": "unmapped",
                        "olds": [h]})
    # crosswalk spacing: a third of old codes padded
    for g in groups:
        for o in g["olds"]:
            k = r.random()
            o["xw"] = o["sku"] + ("   " if k < 0.22 else " " if k < 0.32 else "") if k >= 0.04 else " " + o["sku"]
    return {"groups": groups, "house": house, "catalog": catalog, "not_stocked": not_stocked_groups}


def acceptable(d: dict) -> bool:
    cat = d["catalog"]
    merged = [c for c in cat if c["status"] == "mapped" and len(c["olds"]) >= 2]
    if len(merged) < 10:
        return False
    # merged groups where the first-listed old price is not the maximum
    if sum(1 for c in merged if c["olds"][0]["price"] != c["price"]) < 4:
        return False
    # padded old codes inside merged groups
    if sum(1 for c in merged if any(o["xw"] != o["sku"] for o in c["olds"])) < 5:
        return False
    # groups with at least one variant not stocked
    partial = [g for g in d["groups"] if any(o["carried"] for o in g["olds"]) and not all(o["carried"] for o in g["olds"])]
    if len(partial) < 2:
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 9)
    groups, house, cat = d["groups"], d["house"], d["catalog"]

    rows = []
    items = [o for g in groups for o in g["olds"] if o["carried"]] + house
    for o in sorted(items, key=lambda o: o["sku"]):
        for loc, qty in o["stock"].items():
            rows.append([o["sku"], o["desc"], loc, qty, f"${o['price']:.2f}", day_in(r, date(2026, 1, 5), date(2026, 9, 12)).strftime("%m/%d/%Y")])
    write_csv(os.path.join(ws, "pos_inventory_by_location.csv"), ["SKU", "Description", "Location", "On Hand", "Retail", "Last Sold"],
              rows, preamble=["Zephyr Bike Works - Inventory by location", "As of 09/12/2026 close"], bom=True)

    xrows = []
    for g in groups:
        for o in g["olds"]:
            xrows.append([o["xw"], o["desc"].upper(), g["new"], g["new_desc"]])
    write_csv(os.path.join(ws, "sku_crosswalk_final_2026-09-09.csv"), ["Old SKU", "Old Description", "New SKU", "New Description"], xrows)

    # July draft: five merged groups split back into separate (wrong) codes, no padding
    drows = []
    merged_groups = [g for g in groups if len(g["olds"]) >= 2]
    split = set(g["new"] for g in r.sample(merged_groups, 5))
    for g in groups:
        for i, o in enumerate(g["olds"]):
            new = g["new"] if g["new"] not in split or i == 0 else f"{g['new'][:2]}{int(g['new'][2:]) + 1 + i}"
            drows.append([o["sku"], o["desc"].upper(), new, g["new_desc"]])
    write_csv(os.path.join(ws, "sku_crosswalk_DRAFT_july.csv"), ["Old SKU", "Old Description", "New SKU", "New Description"], drows)

    write_text(os.path.join(ws, "note_from_carlos.txt"),
               "Opening catalog for the new POS\n"
               "\n"
               "Coastline sent the final crosswalk on the 9th (ignore the July draft, they changed a few groups after we complained).\n"
               "The new system wants one line per SKU with both shops' stock added together. Columns: sku, description, on_hand,\n"
               "price, status.\n"
               "\n"
               "- Where several of our old codes become one new code, add their stock up and use the highest of the old prices so we\n"
               "  never undersell. Use Coastline's new description.\n"
               "- The crosswalk lists their whole range. Only put in what we actually carry - if we don't have any of the old codes\n"
               "  for a new SKU, it doesn't go in.\n"
               "- Anything of ours that isn't on the crosswalk (mostly our own Zephyr stuff) stays in under the old code and old\n"
               "  description with status unmapped so I can deal with it. Everything else is status mapped.\n"
               "\n"
               "Carlos\n")

    header = ["sku", "description", "on_hand", "price", "status"]
    out = [[c["sku"], c["desc"], c["on_hand"], f"{c['price']:.2f}", c["status"]] for c in sorted(cat, key=lambda c: c["sku"])]
    write_csv(os.path.join(ref, "catalog_new.csv"), header, out)
    write_csv(os.path.join(sol, "catalog_new.csv"), header, out)
    merged = [c for c in cat if c["status"] == "mapped" and len(c["olds"]) >= 2]
    padded = [c["sku"] for c in merged if any(o["xw"] != o["sku"] for o in c["olds"])]
    price_sens = [c["sku"] for c in merged if c["olds"][0]["price"] != c["price"]]
    write_json(os.path.join(ref, "notes.json"), {
        "merged_new_skus": [c["sku"] for c in merged], "padded_in_merged": padded, "price_not_first": price_sens,
        "unmapped": [h["sku"] for h in house], "not_stocked_new_skus": [g["new"] for g in d["not_stocked"]],
        "draft_split_groups": sorted(split)})
    must_stock = sorted(set(padded[:4] + [c["sku"] for c in merged][:3]))
    write_task_yaml(HERE, {
        "id": "sku-crosswalk-migration", "track": "desk", "category": "spreadsheet",
        "title": "Move the shop inventory onto the new SKUs",
        "ask": ("We go live on the new register next week. Turn our current inventory into the opening catalog using Coastline's "
                "crosswalk and save it as catalog_new.csv. Carlos's note has the rules.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"{len(merged)} new SKUs each replace two or three old codes (valve lengths, pack sizes, colours); their stock must be added "
            "together, so a lookup that keeps the first old row per new SKU undercounts (check: on hand per SKU)",
            "the inventory export has one row per SKU per location (Main and Warehouse) for most items, under a two-line preamble "
            "and a BOM (check: on hand per SKU)",
            "about a third of the crosswalk's Old SKU cells carry trailing spaces and a few a leading space; an exact join misses "
            "those mappings and the items fall through as unmapped (checks: catalog SKUs; on hand per SKU)",
            f"{len(house)} house-brand items are not on the crosswalk and must stay under their old code with status unmapped, not "
            "be dropped by an inner join (checks: catalog SKUs; status)",
            f"the crosswalk covers the distributor's whole range: {len(d['not_stocked'])} new SKUs have no old code the shop stocks and "
            "must not be added, and some groups include a variant the shop never carried (checks: catalog SKUs; row count)",
            "merged items take the highest of their old prices, which is not the first row's price in "
            f"{len(price_sens)} groups, and prices are '$34.99' text (check: price)",
            "the July draft crosswalk is in the folder with five merged groups split into separate codes (check: catalog SKUs)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "catalog_new.csv", "columns": header},
            {"type": "csv_set_equal", "name": "catalog SKUs", "path": "catalog_new.csv", "column": "sku", "ref": "catalog_new.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "catalog_new.csv", "equals_ref": "catalog_new.csv"},
            {"type": "csv_values_match", "name": "on hand per SKU", "path": "catalog_new.csv", "ref": "catalog_new.csv", "key": "sku",
             "columns": ["on_hand"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0, "must_match_keys": must_stock},
            {"type": "csv_values_match", "name": "price", "path": "catalog_new.csv", "ref": "catalog_new.csv", "key": "sku",
             "columns": ["price"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": price_sens[:4]},
            {"type": "csv_values_match", "name": "status", "path": "catalog_new.csv", "ref": "catalog_new.csv", "key": "sku",
             "columns": ["status"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": [h["sku"] for h in house]},
        ],
    })
    print(f"seed={seed} catalog={len(cat)} merged={len(merged)} padded={len(padded)} price_sens={len(price_sens)} export_rows={len(rows)}")


def write_naive(d: dict, out: str) -> None:
    """Exact join on the crosswalk as written, first export row per old SKU, first old code per new SKU, inner join."""
    os.makedirs(out, exist_ok=True)
    xw = {}
    for g in d["groups"]:
        for o in g["olds"]:
            xw[o["xw"]] = g
    rows, seen = [], set()
    items = [o for g in d["groups"] for o in g["olds"] if o["carried"]]
    for o in sorted(items, key=lambda o: o["sku"]):
        g = xw.get(o["sku"])
        if g is None or g["new"] in seen:
            continue
        seen.add(g["new"])
        first_loc = next(iter(o["stock"].values()))
        rows.append([g["new"], g["new_desc"], first_loc, f"{o['price']:.2f}", "mapped"])
    write_csv(os.path.join(out, "catalog_new.csv"), ["sku", "description", "on_hand", "price", "status"], rows)


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
