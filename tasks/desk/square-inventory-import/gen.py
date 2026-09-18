#!/usr/bin/env python3
"""square-inventory-import: an outdoor shop's stock count sheet and old register prices turned into Square's item import.

    python gen.py [--seed N]

Business: Granite Peak Outfitters is replacing its old RegisterOne till with Square. The September stock count
lists one row per size; the register's price export stores prices in cents per style; Square wants one row per
variation with its item library conventions.

Traps (each caught by a check, see task.yaml):
  * every size is its own row; Square needs the item name repeated per variation without the size the count sheet
    sometimes appended, the size as Variation Name and Option Value with Option Name Size, and one-size products
    as a single variation named Regular with no option                         (check: item and variation names)
  * sizes are typed Small / sm / Med / LG / X-Large / 2XL; the SKU is the style number, a dash and the size code,
    or the style number alone for one-size products                           (checks: one row per variation; item and variation names)
  * the register exports prices in cents (12900 is $129.00)                    (check: price in dollars)
  * department codes are written only on the first row of each block, and HIKE was folded into Accessories
                                                                               (check: category)
  * oversold counts are negative and import as 0                               (check: quantity on hand)
  * the register export still lists retired styles that are not on the count sheet (checks: one row per variation; row count)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

LOCATION = "Granite Peak Outfitters"
TEMPLATE = ["Token", "Item Name", "Variation Name", "SKU", "Description", "Category", "Price", "Option Name 1", "Option Value 1",
            f"New Quantity {LOCATION}"]
CATEGORY = {"OUT": "Jackets & Outerwear", "BASE": "Base Layers", "FTW": "Footwear", "CAMP": "Camp & Kitchen", "ACC": "Accessories",
            "HIKE": "Accessories"}
# dept, style, name, price, sizes ("" = one size), description
STYLES = [("OUT", "TJ4410", "Trail Jacket - Slate", 129.00, ["S", "M", "L", "XL"], "Packable 2.5-layer shell"),
          ("OUT", "TJ4411", "Trail Jacket - Moss", 129.00, ["XS", "S", "M", "L"], "Packable 2.5-layer shell"),
          ("OUT", "DV3150", "Down Vest - Black", 149.00, ["S", "M", "L", "XL", "XXL"], "650-fill down vest"),
          ("OUT", "RS2090", "Rain Shell - Ember", 179.00, ["M", "L", "XL"], "Seam-sealed rain shell"),
          ("BASE", "MC1200", "Merino Crew - Charcoal", 89.00, ["S", "M", "L", "XL"], "200gsm merino crew"),
          ("BASE", "ML1210", "Merino Leggings - Black", 79.00, ["XS", "S", "M", "L"], "200gsm merino leggings"),
          ("BASE", "WS0300", "Wool Sock 3pk", 24.00, [""], "Midweight hiking socks"),
          ("FTW", "RB2200", "Ridge Hiking Boot", 189.00, ["8", "9", "9.5", "10", "11"], "Waterproof leather boot"),
          ("FTW", "CM2100", "Camp Moc", 69.00, ["8", "9", "10"], "Insulated camp shoe"),
          ("CAMP", "CS0100", "Camp Stove", 89.00, [""], "Canister stove with igniter"),
          ("CAMP", "TP0900", "Titanium Pot 900ml", 54.00, [""], "Titanium cook pot"),
          ("CAMP", "WB0010", "Water Bottle 1L", 32.00, [""], "Insulated steel bottle"),
          ("ACC", "HL0300", "Headlamp 300lm", 45.00, [""], "Rechargeable headlamp"),
          ("ACC", "BN0500", "Beanie - Rust", 28.00, [""], "Rib-knit wool beanie"),
          ("HIKE", "TK0200", "Trekking Pole Pair", 79.00, [""], "Aluminum trekking poles"),
          ("HIKE", "DB0020", "Dry Bag 20L", 29.00, [""], "Roll-top dry bag"),
          ("HIKE", "MP0001", "Map Case", 14.00, [""], "Waterproof map case")]
RETIRED = [("TJ3300", "Trail Jacket - Navy (2024)", 11900, "OUT"), ("GS0400", "Gaiter Short", 3400, "HIKE"),
           ("CL0120", "Camp Lantern", 3900, "CAMP"), ("FL1000", "Fleece Pullover - Grey", 6900, "BASE")]
SIZE_WORDS = {"XS": ["XS", "X-Small"], "S": ["S", "Small", "sm"], "M": ["M", "Med", "Medium"], "L": ["L", "LG", "Large"],
              "XL": ["XL", "X-Large"], "XXL": ["XXL", "2XL"]}
ONE_SIZE_WORDS = ["", "OS", "One Size", "n/a"]


def build(seed: int) -> dict:
    r = rng(seed)
    variants = []
    for dept, style, name, price, sizes, desc in STYLES:
        base_price = price + r.choice([0.0, 0.0, 5.0, -5.0, 10.0])
        for size in sizes:
            v = {"dept": dept, "style": style, "name": name, "price": base_price, "size": size, "desc": desc, "tags": set()}
            v["sku"] = f"{style}-{size}" if size else style
            v["variation"] = size if size else "Regular"
            v["qty"] = r.choice([0, 1, 2, 3, 4, 5, 6, 8, 10, 12])
            if not size:
                v["tags"].add("regular")
            variants.append(v)
    # size words on the count sheet
    for v in variants:
        if v["size"] in SIZE_WORDS:
            v["size_text"] = r.choice(SIZE_WORDS[v["size"]])
            if v["size_text"] != v["size"]:
                v["tags"].add("size_word")
        elif v["size"]:
            v["size_text"] = v["size"]
        else:
            v["size_text"] = r.choice(ONE_SIZE_WORDS)
        v["name_text"] = v["name"]
    sized = [v for v in variants if v["size"]]
    for v in r.sample(sized, 6):
        v["name_text"] = f"{v['name']} ({v['size_text'] or v['size']})"; v["tags"].add("name_suffix")
    for v in r.sample([v for v in variants if v["qty"] > 0], 3):
        v["qty_text"] = -r.randint(1, 3); v["qty"] = 0; v["tags"].add("negative")
    for v in variants:
        v.setdefault("qty_text", v["qty"])
        if v["dept"] == "HIKE":
            v["tags"].add("hike")
    return {"variants": variants}


def emit(seed: int) -> None:
    d = build(seed)
    variants = d["variants"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 23)
    rows = []
    last_dept = None
    order = ["OUT", "BASE", "FTW", "CAMP", "ACC", "HIKE"]
    for dept in order:
        for v in [v for v in variants if v["dept"] == dept]:
            size_cell = v["size_text"]
            if v["dept"] == "FTW":
                size_cell = float(v["size"]) if "." in v["size"] else int(v["size"])
            rows.append([dept if dept != last_dept else "", v["style"], v["name_text"], size_cell, v["qty_text"],
                         r.choice(["", "", "", "A-12", "B-03", "backroom", "window"])])
            last_dept = dept
    write_xlsx(os.path.join(ws, "stock_count_2026-09.xlsx"), {"Count": {
        "merged_title": "Granite Peak Outfitters - full stock count, 7 Sept 2026",
        "preamble": [["Counted by: Omar, Leila", "", "", "", "", "Negative = sold before it was received"]],
        "header": ["Dept", "Style #", "Description", "Size", "On Hand", "Bin"], "rows": rows,
        "widths": {"B": 10, "C": 34, "F": 30}, "freeze": "A4"}}, creator="Granite Peak")
    styles = {}
    for v in variants:
        styles.setdefault(v["style"], v)
    pos = [[s, v["name"], str(int(round(v["price"] * 100))), "TAXABLE", v["dept"]] for s, v in styles.items()]
    pos += [[s, nm, str(c), "TAXABLE", dp] for s, nm, c, dp in RETIRED]
    pos.sort(key=lambda x: x[0])
    write_csv(os.path.join(ws, "registerone_price_export.csv"), ["item_code", "item_desc", "price", "tax_class", "dept"], pos, crlf=True)
    write_csv(os.path.join(ws, "square_item_import_template.csv"), TEMPLATE, [
        ["", "Example Fleece", "S", "EX100-S", "Sample item with sizes", "Base Layers", "59.00", "Size", "S", "4"],
        ["", "Example Fleece", "M", "EX100-M", "Sample item with sizes", "Base Layers", "59.00", "Size", "M", "6"],
        ["", "Example Carabiner", "Regular", "EX200", "Sample item without sizes", "Accessories", "9.50", "", "", "12"]])
    write_text(os.path.join(ws, "square_setup_notes.txt"), (
        "Square item import - how we're setting it up (Leila, 8 Sept)\n"
        "\n"
        "Fill in square_item_import_template.csv (delete the three Example rows). Square reads it one row per variation.\n"
        "\n"
        "Only what is on the September count sheet goes in. The RegisterOne export still has styles we retired; skip those.\n"
        "\n"
        "Token: leave blank, Square creates it for new items.\n"
        "Item Name: the product name as the customer sees it, WITHOUT the size (the count sheet sometimes has the size in\n"
        "  brackets after the name). Same Item Name on every row for that product so Square groups the sizes.\n"
        "Variation Name: the size, written XS, S, M, L, XL or XXL for clothing and the plain number for shoes (8, 9.5).\n"
        "  Products that don't come in sizes have one variation called Regular (that's Square's default name).\n"
        "Option Name 1 / Option Value 1: Size and the same size as Variation Name. Leave both blank for Regular.\n"
        "SKU: style number, a dash, then the size as above (TJ4410-M, RB2200-9.5). One-size products use the style number\n"
        "  on its own.\n"
        "Description: the short description is fine to leave blank, I'll add copy later.\n"
        "Category: our Square categories are Jackets & Outerwear (OUT), Base Layers (BASE), Footwear (FTW),\n"
        "  Camp & Kitchen (CAMP), Accessories (ACC). The old HIKE department was folded into Accessories.\n"
        "  On the count sheet the Dept is only written where a new department starts.\n"
        "Price: dollars and cents. Heads up, RegisterOne exports prices in CENTS (12900 = $129.00). Price is per style,\n"
        "  every size costs the same.\n"
        f"New Quantity {LOCATION}: the On Hand count. Anything negative is stuff we sold before it was received into the old\n"
        "  system; put 0.\n"))
    out = sorted(variants, key=lambda v: v["sku"])
    rrows = [["", v["name"], v["variation"], v["sku"], "", CATEGORY[v["dept"]], f"{v['price']:.2f}", "Size" if v["size"] else "",
              v["size"], str(v["qty"])] for v in out]
    write_csv(os.path.join(ref, "square_items.csv"), TEMPLATE, rrows)
    write_csv(os.path.join(sol, "square_items.csv"), TEMPLATE, rrows)

    def keys(*tags):
        return sorted(v["sku"] for v in out if any(t in v["tags"] for t in tags))
    write_json(os.path.join(ref, "notes.json"), {t: keys(t) for t in ("regular", "size_word", "name_suffix", "negative", "hike")})
    write_task_yaml(HERE, {
        "id": "square-inventory-import", "track": "desk", "category": "reformatting",
        "title": "Load the stock count into Square's item import",
        "ask": ("We're switching the till to Square. Can you turn our September stock count into Square's item import? Prices are in "
                "the old register export, and Leila's setup notes and Square's template are in the folder. Save it as square_items.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "each size is its own count-sheet row and some descriptions carry the size in brackets; Square needs the bare Item Name repeated per variation, the size as Variation Name and Option Value with Option Name Size, and one-size products as a single Regular variation with blank options (check: item and variation names)",
            "sizes are typed Small / sm / Med / LG / X-Large / 2XL / OS / n/a and shoe sizes are numbers; the SKU is style-size (TJ4410-M, RB2200-9.5) or the bare style for one-size products, so copying the Size cell breaks the key (checks: one row per variation; item and variation names)",
            "RegisterOne exports prices in cents per style (12900 is $129.00); copying the column makes every price a hundred times too high (check: price in dollars)",
            "Dept is written only on the first row of each block, so most rows have a blank department, and HIKE was folded into Accessories (check: category)",
            "three oversold counts are negative and must import as 0 (check: quantity on hand)",
            "the register export lists four retired styles not on the count sheet; joining from the register side adds rows for them, and the template keeps three example rows to delete (checks: one row per variation; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Square template columns, exact order", "path": "square_items.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one row per variation", "path": "square_items.csv", "column": "SKU", "ref": "square_items.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "square_items.csv", "equals_ref": "square_items.csv"},
            {"type": "csv_values_match", "name": "item and variation names", "path": "square_items.csv", "ref": "square_items.csv", "key": "SKU",
             "columns": ["Item Name", "Variation Name", "Option Name 1", "Option Value 1"], "min_accuracy": 1.0,
             "must_match_keys": keys("regular", "size_word", "name_suffix")},
            {"type": "csv_values_match", "name": "price in dollars", "path": "square_items.csv", "ref": "square_items.csv", "key": "SKU",
             "columns": ["Price"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "category", "path": "square_items.csv", "ref": "square_items.csv", "key": "SKU",
             "columns": ["Category"], "min_accuracy": 1.0, "must_match_keys": keys("hike")},
            {"type": "csv_values_match", "name": "quantity on hand", "path": "square_items.csv", "ref": "square_items.csv", "key": "SKU",
             "columns": [f"New Quantity {LOCATION}"], "numeric": True, "tolerance": 0.001, "min_accuracy": 1.0, "must_match_keys": keys("negative")},
        ],
    })
    print(f"seed={seed}: {len(variants)} variations; " + ", ".join(f"{t}={len(keys(t))}" for t in ("regular", "size_word", "name_suffix", "negative", "hike")))


if __name__ == "__main__":
    emit(argparse_seed())
