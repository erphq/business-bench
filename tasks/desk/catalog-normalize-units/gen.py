#!/usr/bin/env python3
"""catalog-normalize-units: a grocery co-op's old catalog, sizes in free text, into the new POS import columns.

    python gen.py [--seed N] [--naive DIR]

Business: a neighbourhood food co-op moving to a new point-of-sale system. The old system kept the size as
whatever the buyer typed ("1.5L", "6 x 330ml", "Case of 24 / 250 ml"), sometimes only inside the description.
The new POS wants pack quantity, size of one unit and a unit from a fixed list, plus the new category names.

Traps (each caught by a check, see task.yaml):
  * the same size is written "1.5L", "1500 ml" and "1,5 l"                         (check: unit size)
  * packs are "6 x 330ml", "330ml x 6", "12pk 355 mL", "Case of 24 / 250 ml", "4-pack" (checks: pack quantity; unit size)
  * kilograms and litres must become g and ml, counted goods are ea; the unit list is exact and lower case
                                                                                     (checks: unit; unit size)
  * old departments are in any capitalisation and the new category list is case-sensitive (check: category)
  * the manager's note renames Household, Dairy and Grocery                          (check: category)
  * a blank Size column means the size is inside the description                     (checks: unit size; pack quantity)
  * discontinued items (status DISC) do not go into the new system                  (check: every active item)
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# new category, old department spellings
DEPTS = {"Beverages": ["Beverages", "BEVERAGES", "beverages"], "Bulk": ["Bulk Foods", "BULK FOODS", "bulk foods"],
         "Dairy & Eggs": ["Dairy", "DAIRY", "dairy"], "Home & Cleaning": ["Household", "HOUSEHOLD", "household"],
         "Pantry": ["Grocery", "GROCERY", "grocery"], "Personal Care": ["Personal Care", "PERSONAL CARE", "personal care"],
         "Snacks": ["Snacks", "SNACKS", "snacks"]}
# name, category, kind -> list of (pack, size, unit) choices
PRODUCTS = [
    ("Sparkling Water Lime", "Beverages", "can_pack"), ("Sparkling Water Grapefruit", "Beverages", "can_pack"),
    ("Kombucha Ginger", "Beverages", "bottle"), ("Cold Brew Coffee", "Beverages", "bottle"), ("Oat Milk Barista", "Dairy & Eggs", "carton"),
    ("Orange Juice Pulp Free", "Beverages", "big_bottle"), ("Olive Oil Extra Virgin", "Pantry", "big_bottle"),
    ("Apple Cider Vinegar", "Pantry", "bottle"), ("Maple Syrup Grade A", "Pantry", "bottle"), ("Coconut Water", "Beverages", "can_pack"),
    ("Root Beer", "Beverages", "can_pack"), ("Whole Milk", "Dairy & Eggs", "big_bottle"), ("Greek Yogurt Plain", "Dairy & Eggs", "tub"),
    ("Butter Unsalted", "Dairy & Eggs", "block"), ("Free Range Eggs Large", "Dairy & Eggs", "dozen"), ("Cheddar Aged", "Dairy & Eggs", "block"),
    ("Rolled Oats", "Bulk", "bulk"), ("Brown Rice Long Grain", "Bulk", "bulk"), ("Red Lentils", "Bulk", "bulk"), ("Raw Almonds", "Bulk", "bulk"),
    ("Chickpeas Dried", "Bulk", "bulk"), ("Trail Mix", "Snacks", "bag"), ("Dark Chocolate 70%", "Snacks", "bar_pack"),
    ("Sea Salt Kettle Chips", "Snacks", "bag"), ("Granola Bars Honey Oat", "Snacks", "bar_pack"), ("Peanut Butter Crunchy", "Pantry", "jar"),
    ("Tomato Passata", "Pantry", "jar"), ("Spaghetti Durum", "Pantry", "bag"), ("Crushed Tomatoes", "Pantry", "tin_pack"),
    ("Black Beans", "Pantry", "tin_pack"), ("Green Tea", "Pantry", "tea"), ("Chamomile Tea", "Pantry", "tea"),
    ("Dish Soap Lemon", "Home & Cleaning", "bottle"), ("Laundry Liquid Unscented", "Home & Cleaning", "big_bottle"),
    ("All Purpose Cleaner Refill", "Home & Cleaning", "big_bottle"), ("Compostable Trash Bags", "Home & Cleaning", "count"),
    ("Beeswax Wraps", "Home & Cleaning", "count_pack"), ("Sponges Plant Based", "Home & Cleaning", "count"),
    ("Shampoo Bar Rosemary", "Personal Care", "block"), ("Toothpaste Fluoride Free", "Personal Care", "tube"),
    ("Cotton Swabs Bamboo", "Personal Care", "count"), ("Body Wash Lavender", "Personal Care", "bottle"),
    ("Deodorant Stick", "Personal Care", "tube"), ("Hand Soap Refill", "Personal Care", "big_bottle"), ("Lip Balm", "Personal Care", "count_pack"),
    ("Honey Raw Wildflower", "Pantry", "jar"), ("Coconut Yogurt", "Dairy & Eggs", "tub"), ("Almond Milk Unsweetened", "Dairy & Eggs", "carton"),
    ("Sourdough Crackers", "Snacks", "bag"), ("Seaweed Snacks", "Snacks", "bar_pack"), ("Lemonade Sparkling", "Beverages", "bottle_pack"),
    ("Ginger Beer", "Beverages", "bottle_pack"), ("Cashews Roasted", "Bulk", "bulk"), ("Quinoa White", "Bulk", "bulk"),
]
SIZES = {
    "can_pack": [(12, 355, "ml"), (6, 330, "ml"), (8, 250, "ml")], "bottle": [(1, 500, "ml"), (1, 750, "ml"), (1, 473, "ml")],
    "big_bottle": [(1, 1500, "ml"), (1, 1000, "ml"), (1, 2000, "ml"), (1, 3000, "ml")], "carton": [(1, 946, "ml"), (1, 1000, "ml")],
    "tub": [(1, 500, "g"), (1, 750, "g")], "block": [(1, 250, "g"), (1, 200, "g"), (1, 454, "g")], "dozen": [(1, 12, "ea")],
    "bulk": [(1, 1000, "g")], "bag": [(1, 150, "g"), (1, 500, "g"), (1, 1000, "g")], "bar_pack": [(3, 100, "g"), (6, 35, "g"), (10, 5, "g")],
    "jar": [(1, 500, "g"), (1, 680, "g"), (1, 340, "g")], "tin_pack": [(4, 398, "ml"), (2, 796, "ml")], "tea": [(1, 20, "ea"), (2, 20, "ea")],
    "count": [(1, 100, "ea"), (1, 20, "ea"), (1, 3, "ea")], "count_pack": [(3, 1, "ea"), (2, 1, "ea")], "tube": [(1, 100, "ml"), (1, 75, "g")],
    "bottle_pack": [(4, 355, "ml"), (4, 250, "ml")],
}
# product-specific sizes where the kind's defaults would be silly
OVERRIDE = {"Dark Chocolate 70%": [(1, 100, "g"), (3, 100, "g")], "Granola Bars Honey Oat": [(6, 35, "g"), (5, 40, "g")],
            "Seaweed Snacks": [(10, 5, "g"), (6, 5, "g")], "Sourdough Crackers": [(1, 200, "g"), (1, 150, "g")],
            "Sea Salt Kettle Chips": [(1, 150, "g"), (1, 227, "g")], "Trail Mix": [(1, 300, "g"), (1, 500, "g")],
            "Spaghetti Durum": [(1, 500, "g"), (1, 1000, "g")], "Compostable Trash Bags": [(1, 20, "ea"), (1, 30, "ea")],
            "Sponges Plant Based": [(1, 3, "ea"), (1, 2, "ea")], "Cotton Swabs Bamboo": [(1, 100, "ea"), (1, 200, "ea")],
            "Deodorant Stick": [(1, 75, "g")], "Toothpaste Fluoride Free": [(1, 100, "ml"), (1, 75, "ml")],
            "Honey Raw Wildflower": [(1, 500, "g"), (1, 340, "g")], "Tomato Passata": [(1, 680, "g")],
            "Peanut Butter Crunchy": [(1, 500, "g"), (1, 340, "g")]}
RATE = {"ml": 0.0045, "g": 0.011, "ea": 0.22}


def size_text(pack: int, size: float, unit: str, style: int) -> str:
    """Free text the way a buyer typed it. Styles rotate so every trap shape appears."""
    def one(style2):
        if unit == "ml":
            if size >= 1000 and style2 % 3 == 0:
                v = size / 1000
                return f"{v:g}L" if style2 % 2 == 0 else f"{v:g} ltr"
            if size >= 1000 and style2 % 3 == 1:
                return f"{str(size / 1000).replace('.', ',').rstrip('0').rstrip(',')} l"
            return [f"{size:g}ml", f"{size:g} mL", f"{size:g}ML", f"{size:g} ml"][style2 % 4]
        if unit == "g":
            if size >= 1000 and style2 % 2 == 0:
                return [f"{size / 1000:g}kg", f"{size / 1000:g} KG"][style2 % 4 // 2]
            return [f"{size:g}g", f"{size:g} G", f"{size:g} gr", f"{size:g} g"][style2 % 4]
        if size == 12 and pack == 1 and style2 % 2 == 0:
            return "1 dozen"
        return [f"{size:g} ct", f"{size:g} pcs", f"{size:g} count", f"{size:g}ct"][style2 % 4]
    if unit == "ea" and size == 1 and pack > 1:
        return [f"{pack} pack", f"{pack}-pack", f"pk of {pack}"][style % 3]
    if pack == 1:
        return one(style)
    shapes = [f"{pack} x {one(style)}", f"{one(style)} x {pack}", f"{pack}pk {one(style)}", f"Case of {pack} / {one(style)}",
              f"{pack}-pack {one(style)}", f"{pack}x{one(style)}"]
    return shapes[style % len(shapes)]


def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    codes = r.sample(range(10100, 49999), len(PRODUCTS))
    for i, (name, cat, kind) in enumerate(PRODUCTS):
        pack, size, unit = r.choice(OVERRIDE.get(name, SIZES[kind]))
        rate = RATE[unit] * (0.2 if name == "Cotton Swabs Bamboo" else 2.0 if name in ("Raw Almonds", "Cashews Roasted", "Maple Syrup Grade A", "Olive Oil Extra Virgin") else 1.0)
        floor = 3.99 if cat in ("Personal Care", "Home & Cleaning") else 1.99
        price = max(floor, round(pack * size * rate * r.uniform(0.8, 1.25) * 2) / 2 - 0.01)
        items.append({"sku": str(codes[i]), "name": name, "cat": cat, "kind": kind, "pack": pack, "size": float(size), "unit": unit,
                      "price": price, "style": r.randrange(12), "dept_style": r.randrange(3), "in_desc": r.random() < 0.2,
                      "status": "Active", "k": r.random()})
    # force the showcase shapes onto particular items so every trap is present in every draw
    big = [x for x in items if x["unit"] == "ml" and x["size"] >= 1000 and x["pack"] == 1]
    packs = [x for x in items if x["pack"] > 1 and x["unit"] != "ea"]
    for j, x in enumerate(big[:3]):
        x["style"] = [0, 1, 2][j]               # 1.5L / 1,5 l / 1500ml
    for j, x in enumerate(packs[:6]):
        x["style"] = j
        x["in_desc"] = False
    for x in r.sample([x for x in items if x not in packs[:6] and x not in big[:3]], 3):
        x["in_desc"] = True
    for x in r.sample(items, 4):
        x["status"] = "DISC"
    return {"items": items}


def truth_rows(d: dict) -> list[list]:
    out = []
    for x in d["items"]:
        if x["status"] != "Active":
            continue
        size = int(x["size"]) if float(x["size"]).is_integer() else x["size"]
        out.append([x["sku"], x["name"], x["cat"], x["pack"], size, x["unit"], f"{x['price']:.2f}"])
    return out


def naive_rows(d: dict) -> list[list]:
    """First number in the size text as the size, unit letters as typed (lower-cased), pack 1 unless 'x' is present,
    department title-cased as the category, discontinued items kept."""
    import re
    out = []
    for x in d["items"]:
        txt = size_text(x["pack"], x["size"], x["unit"], x["style"])
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)?", txt)
        num = float(m.group(1).replace(",", ".")) if m else ""
        unit = (m.group(2) or "").lower() if m else ""
        pack = x["pack"] if (" x " in txt) else 1
        cat = DEPTS[x["cat"]][x["dept_style"]].title()
        out.append([x["sku"], x["name"], cat, pack, num, unit, f"{x['price']:.2f}"])
    return out


def acceptable(d: dict) -> bool:
    items = d["items"]
    styles = {size_text(x["pack"], x["size"], x["unit"], x["style"]) for x in items}
    has = lambda pat: any(pat in s for s in styles)
    return (has("L") or has("ltr")) and has(",") and has("Case of") and has(" x ") and has("pk") \
        and sum(1 for x in items if x["status"] == "DISC") == 4


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["sku", "name", "category", "pack_qty", "unit_size", "unit", "price"]
    if naive_dir:
        write_csv(os.path.join(naive_dir, "catalog_clean.csv"), header, naive_rows(d))
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 17)
    rows = []
    for x in sorted(d["items"], key=lambda x: x["k"]):
        st = size_text(x["pack"], x["size"], x["unit"], x["style"])
        desc = x["name"].upper() if r.random() < 0.4 else x["name"]
        if x["in_desc"]:
            desc, size_cell = f"{desc} {st}", ""
        else:
            size_cell = st
        rows.append([x["sku"], desc, size_cell, DEPTS[x["cat"]][x["dept_style"]], money_str(x["price"], 1), x["status"]])
    write_xlsx(os.path.join(ws, "old_pos_items_export.xlsx"), {"Items": {
        "merged_title": "ShopKeep item export - all departments", "header": ["Item Code", "Description", "Size", "Department", "Price", "Status"],
        "rows": rows, "widths": {"B": 40, "C": 22, "D": 16}}}, creator="ShopKeep")
    write_csv(os.path.join(ws, "new_pos_import_template.csv"), header,
              [["00000", "Example Sparkling Water", "Beverages", 12, 355, "ml", "9.99"], ["00001", "Example Dish Soap", "Home & Cleaning", 1, 750, "ml", "5.49"]])
    write_text(os.path.join(ws, "import_field_guide.txt"),
               "Fieldstone POS - product import field guide\n"
               "\n"
               "sku        Your item code. Must be unique.\n"
               "name       Product name as it should print on the receipt.\n"
               "category   Must match one of your store's categories exactly, including capital letters:\n"
               "           Beverages | Bulk | Dairy & Eggs | Home & Cleaning | Pantry | Personal Care | Snacks\n"
               "pack_qty   How many units are sold together as one item. A single item is 1.\n"
               "unit_size  The size of ONE unit, as a number only.\n"
               "unit       One of: ml | g | ea  (lower case). Volumes in millilitres, weights in grams.\n"
               "           For counted goods (tea bags, swabs, eggs) use ea and put the count in one package in unit_size.\n"
               "price      Selling price as a number, no currency symbol.\n"
               "\n"
               "Rows that do not match these rules are rejected by the importer.\n")
    write_text(os.path.join(ws, "note_from_manager.txt"),
               "Catalog move - notes\n"
               "\n"
               "The new POS uses the new department names from the board meeting: Household is now Home & Cleaning,\n"
               "Dairy is now Dairy & Eggs, and Grocery is now Pantry. Everything else keeps its name.\n"
               "\n"
               "Anything marked DISC in ShopKeep is gone from the shelves, don't bring it over.\n"
               "\n"
               "Bulk bins are priced per kilo in ShopKeep, so treat those as 1000 g.\n"
               "\n"
               "- Teodora\n")
    rows_t = truth_rows(d)
    write_csv(os.path.join(ref, "catalog_clean.csv"), header, rows_t)
    write_csv(os.path.join(sol, "catalog_clean.csv"), header, rows_t)
    write_json(os.path.join(ref, "notes.json"), {"discontinued": [x["sku"] for x in d["items"] if x["status"] == "DISC"],
                                                  "size_in_description": [x["sku"] for x in d["items"] if x["in_desc"]]})
    write_task_yaml(HERE, {
        "id": "catalog-normalize-units", "track": "desk", "category": "spreadsheet",
        "title": "Normalize the catalog sizes for the new POS",
        "ask": ("We're moving the shop to the new POS. Turn the ShopKeep item export into a file the new system will import, "
                "using their template and field guide, and save it as catalog_clean.csv. Teodora's note has the changes.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the same size is typed '1.5L', '1,5 l', '1.5 ltr' and '1500ml'; unit_size is always millilitres, so 1500 "
            "(check: unit size)",
            "multipacks are written '6 x 330ml', '330ml x 6', '12pk 355 mL', 'Case of 24 / 250 ml', '4-pack' and '6x35g'; the "
            "pack count goes in pack_qty and the size of one unit in unit_size (checks: pack quantity; unit size)",
            "kg and litre sizes must become g and ml, and counted goods ('100 ct', '20 pcs', '1 dozen', '3-pack') are ea with the "
            "count in unit_size; the guide's unit list is exact and lower case, so 'mL', 'G', 'gr', 'pcs' are rejected "
            "(checks: unit; unit size)",
            "departments come as 'BEVERAGES', 'bulk foods' or 'Personal Care' and the new category list is case-sensitive "
            "('Bulk', not 'Bulk Foods' or 'BULK') (check: category)",
            "Teodora's note renames Household to Home & Cleaning, Dairy to Dairy & Eggs and Grocery to Pantry (check: category)",
            "a blank Size cell means the size was typed at the end of the description (checks: unit size; pack quantity)",
            "four items are marked DISC and must not be imported (check: every active item)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns in order", "path": "catalog_clean.csv", "columns": header, "exact": True},
            {"type": "csv_set_equal", "name": "every active item", "path": "catalog_clean.csv", "column": "sku", "ref": "catalog_clean.csv",
             "normalize": ["strip"]},
            {"type": "csv_values_match", "name": "pack quantity", "path": "catalog_clean.csv", "ref": "catalog_clean.csv", "key": "sku",
             "columns": ["pack_qty"], "numeric": True, "tolerance": 0.001},
            {"type": "csv_values_match", "name": "unit size", "path": "catalog_clean.csv", "ref": "catalog_clean.csv", "key": "sku",
             "columns": ["unit_size"], "numeric": True, "tolerance": 0.01},
            {"type": "csv_values_match", "name": "unit", "path": "catalog_clean.csv", "ref": "catalog_clean.csv", "key": "sku",
             "columns": ["unit"], "normalize": ["strip"]},
            {"type": "csv_values_match", "name": "category", "path": "catalog_clean.csv", "ref": "catalog_clean.csv", "key": "sku",
             "columns": ["category"], "normalize": ["strip"]},
        ],
    })
    print(f"seed={seed} items={len(d['items'])} active={len(rows_t)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(500):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
