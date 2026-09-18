#!/usr/bin/env python3
"""amazon-inventory-loader: a bike shop's product sheet turned into an Amazon Inventory Loader file (subset of columns).

    python gen.py [--seed N]

Business: Zephyr Bike Works sells new and used parts in the shop and on Amazon, some shipped by the shop and some
stored at Amazon (FBA). The owner keeps one product sheet; Amazon's Inventory Loader wants coded columns.

All ASINs are synthetic (10 characters starting "BZ", a prefix Amazon does not issue) and all UPCs start with 2,
the restricted-circulation range, so no identifier here belongs to a real product.

Traps (each caught by a check, see task.yaml):
  * the Amazon ID column mixes 10-character ASINs and 12-digit UPCs; product-id-type is 1 for an ASIN and 3 for a
    UPC, and the shop SKU never goes in product-id; rows with no Amazon ID cannot use this file (checks: product id and type; one row per sku)
  * conditions are typed freely; "open box" is Used; Like New on Amazon, and refurbished items stay off Amazon
    because the shop is not approved for Renewed                               (checks: item condition code; one row per sku)
  * price is shelf price plus $6.00 for items the shop ships and plus 12% for FBA items, and the in-store Sale
    Price column is ignored                                                    (check: price rules)
  * quantity is on hand minus units held for store customers, never below 0, for items the shop ships; FBA rows
    leave quantity blank and use fulfillment-center-id AMAZON_NA instead of DEFAULT (check: quantity and fulfillment)
  * discontinued items are still live on Amazon and stay in the file with add-delete d; everything else is a
                                                                               (check: add-delete)
"""
from __future__ import annotations
import os, sys
from decimal import Decimal, ROUND_HALF_UP
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["sku", "product-id", "product-id-type", "price", "item-condition", "quantity", "add-delete", "item-note", "fulfillment-center-id"]
PRODUCTS = [("11-speed cassette 11-32", 89.0), ("Hydraulic disc brake set", 219.0), ("Carbon seatpost 27.2mm", 149.5), ("Road pedals", 119.0),
            ("GPS bike computer", 249.0), ("Tubeless sealant 16oz", 24.5), ("11-speed chain", 42.0), ("Race saddle", 99.0),
            ("Handlebar tape - black", 28.0), ("Carbon bottle cage", 36.0), ("Mini pump", 32.5), ("Frame bag 1.5L", 54.0),
            ("Alloy wheelset 700c", 489.0), ("Rear derailleur 11-speed", 139.0), ("Crankset 172.5mm", 279.0), ("Helmet - medium", 129.0),
            ("Floor pump with gauge", 69.5), ("Torque wrench 2-14Nm", 84.0), ("Tire 700x28 folding", 58.0), ("Tire levers (3)", 9.5),
            ("Rear light 150lm", 44.0), ("Front light 800lm", 89.5), ("Cleats - 6 degree float", 26.0), ("Chain checker tool", 16.5),
            ("Multi-tool 16 function", 38.0), ("Stem 100mm -6deg", 64.0), ("Flat bar 760mm", 72.0), ("Brake pads (pair)", 19.5),
            ("Inner tube 700x25-32", 8.5), ("Kickstand adjustable", 27.0), ("Bar end mirror", 21.0), ("Spoke wrench", 11.0),
            ("Derailleur hanger #12", 29.0), ("Bottom bracket BSA", 49.5), ("Headset 1-1/8", 59.0), ("Saddle bag small", 23.5)]
CONDITIONS = {"new": ("11", ["New", "new", "NEW"]), "open_box": ("1", ["New - open box", "Open box"]),
              "like_new": ("1", ["Used - Like New", "like new (used)"]), "very_good": ("2", ["Used - Very Good", "very good (used)"]),
              "good": ("3", ["Used - Good", "used, good"]), "acceptable": ("4", ["Used - Acceptable", "used - acceptable"]),
              "refurb": (None, ["Refurbished", "Refurb (shop rebuilt)"])}
NOTES = {"open_box": ["Opened, never mounted", "Box opened for photos"], "like_new": ["Ridden once", "No visible wear"],
         "very_good": ["Light scuffs on clamp", "Minor wear, fully serviced"], "good": ["Visible scratches, works perfectly", "Some wear on teeth"],
         "acceptable": ["Heavy cosmetic wear", "Missing original box and bolts"]}


def money(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    used_ids = set()

    def asin():
        while True:
            a = "BZ" + code(r, 8, "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789")
            if a not in used_ids:
                used_ids.add(a); return a

    def upc():
        while True:
            body = "2" + "".join(r.choice("0123456789") for _ in range(10))
            odd = sum(int(body[i]) for i in range(0, 11, 2)); even = sum(int(body[i]) for i in range(1, 11, 2))
            u = body + str((10 - (odd * 3 + even) % 10) % 10)
            if u not in used_ids:
                used_ids.add(u); return u
    consumable = ("sealant", "chain", "tape", "tube", "levers", "pads", "cleats", "tire ")
    durable = [p for p in PRODUCTS if not any(w in p[0].lower() for w in consumable)]
    other = [p for p in PRODUCTS if p not in durable]
    r.shuffle(durable); r.shuffle(other)
    used_plan = ["open_box"] * 3 + ["like_new"] * 3 + ["very_good"] * 3 + ["good"] * 3 + ["acceptable"] * 2 + ["refurb"] * 3
    plan = list(zip(used_plan, durable[:len(used_plan)])) + [("new", p) for p in (durable[len(used_plan):] + other)[:17]]
    r.shuffle(plan)
    for k, (cond, (name, shelf)) in enumerate(plan):
        it = {"sku": f"ZBW-{1040 + 13 * k}", "name": name, "shelf": Decimal(str(shelf + r.choice([0, 0, 5, 10, -2]))), "cond": cond, "tags": set(),
              "fba": r.random() < 0.35, "status": "Active", "sale": ""}
        if cond != "new":
            it["shelf"] = money(it["shelf"] * Decimal("0.7")).quantize(Decimal("1")) + Decimal("0.50") * r.choice([0, 1])
        it["id_kind"] = "upc" if r.random() < 0.3 else "asin"
        it["pid"] = upc() if it["id_kind"] == "upc" else asin()
        it["on_hand"] = r.randint(0, 9) if cond == "new" else 1
        it["held"] = 0
        items.append(it)
    active = [i for i in items if i["cond"] != "refurb"]
    # two rows with no Amazon ID at all
    for it in r.sample([i for i in active if i["cond"] == "new"], 2):
        it["pid"] = ""; it["id_kind"] = "none"; it["tags"].add("excluded")
    for it in items:
        if it["cond"] == "refurb":
            it["tags"].add("excluded")
    listed = [i for i in items if "excluded" not in i["tags"]]
    # make sure both fulfilment channels and both id kinds appear among listed rows
    listed[0]["fba"] = True; listed[1]["fba"] = False
    if not any(i["id_kind"] == "upc" for i in listed):
        listed[2]["id_kind"] = "upc"; listed[2]["pid"] = upc()
    for it in listed:
        if it["id_kind"] == "upc":
            it["tags"].add("pid")
        if it["cond"] != "new":
            it["tags"].add("cond")
        it["tags"].add("price_fba" if it["fba"] else "price_mfn")
    # store holds on merchant-fulfilled new stock, one of them holding everything
    mfn_new = [i for i in listed if not i["fba"] and i["cond"] == "new" and i["on_hand"] >= 2]
    for it in r.sample(mfn_new, min(3, len(mfn_new))):
        it["held"] = r.randint(1, it["on_hand"] - 1); it["tags"].add("qty")
    if mfn_new:
        extra = r.choice([i for i in listed if not i["fba"] and i["cond"] == "new" and i["held"] == 0 and i["on_hand"] > 0] or mfn_new)
        extra["held"] = extra["on_hand"] + 1; extra["tags"].add("qty")
    for it in listed:
        if it["fba"]:
            it["tags"].add("qty")
    # discontinued
    for it in r.sample([i for i in listed if i["cond"] == "new"], 3):
        it["status"] = "Discontinued"; it["on_hand"] = 0; it["held"] = 0; it["tags"].add("discontinued")
    # in-store sale prices on some rows
    for it in r.sample(items, 7):
        it["sale"] = money(it["shelf"] * Decimal("0.85"))
        it["tags"].add("sale")
    for it in items:
        it["price"] = money(it["shelf"] * Decimal("1.12")) if it["fba"] else it["shelf"] + Decimal("6.00")
        it["qty"] = "" if it["fba"] else str(max(0, it["on_hand"] - it["held"]))
        it["fc"] = "AMAZON_NA" if it["fba"] else "DEFAULT"
        it["cond_code"] = CONDITIONS[it["cond"]][0]
        it["note"] = r.choice(NOTES[it["cond"]]) if it["cond"] in NOTES else ""
    return {"items": items}


def emit(seed: int) -> None:
    d = build(seed)
    items = d["items"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 37)
    rows = []
    for it in items:
        cond_text = r.choice(CONDITIONS[it["cond"]][1])
        shelf = it["shelf"]
        shelf_text = r.choice([f"${shelf:,.2f}", f"{shelf:.2f}", f"{int(shelf)}" if shelf == shelf.to_integral() else f"{shelf:.2f}"])
        pid = int(it["pid"]) if it["id_kind"] == "upc" and r.random() < 0.5 else it["pid"]
        rows.append([it["sku"], it["name"], pid, cond_text, it["note"], it["on_hand"], it["held"] or "", "FBA" if it["fba"] else r.choice(["Merchant", "We ship", "Merchant"]),
                     shelf_text, f"${it['sale']:.2f}" if it["sale"] else "", it["status"]])
    write_xlsx(os.path.join(ws, "amazon_listing_sheet.xlsx"), {"Products": {
        "header": ["Shop SKU", "Product", "Amazon ID", "Condition", "Condition Notes", "On Hand", "Held for Store", "Fulfilled By",
                   "Shelf Price", "Sale Price", "Status"],
        "rows": rows, "widths": {"B": 30, "C": 16, "D": 22, "E": 34, "H": 12, "I": 12}, "freeze": "A2"}}, creator="Zephyr Bike Works")
    write_csv(os.path.join(ws, "Inventory_Loader_template.csv"), TEMPLATE, [], delimiter=",")
    write_text(os.path.join(ws, "amazon_upload_notes.txt"), (
        "Amazon inventory upload - how we do it (Carlos)\n"
        "\n"
        "We use the Inventory Loader because everything we sell already has a product page on Amazon; this file only\n"
        "attaches our offer to it. Use Inventory_Loader_template.csv, those columns in that order, one row per product.\n"
        "\n"
        "sku                    our Shop SKU, exactly.\n"
        "product-id             the Amazon ID from the sheet: either an ASIN (10 characters, starts with B) or a UPC\n"
        "                       (12 digits). Never our shop SKU. A product with no Amazon ID can't go in this file at\n"
        "                       all (it needs a full listing), so leave it out.\n"
        "product-id-type        what kind of ID product-id is: 1 = ASIN, 2 = ISBN, 3 = UPC, 4 = EAN.\n"
        "price                  our Amazon price, not the shelf price. Items we ship ourselves: shelf price + $6.00 to\n"
        "                       cover shipping. FBA items: shelf price + 12% to cover Amazon's fees, to the cent. In-store\n"
        "                       sale prices never go on Amazon.\n"
        "item-condition         Amazon's code: 11 = New, 1 = Used; Like New, 2 = Used; Very Good, 3 = Used; Good,\n"
        "                       4 = Used; Acceptable, 10 = Refurbished. Amazon does not allow anything that has been opened\n"
        "                       to be sold as New, so open box goes up as Used; Like New. We are NOT approved for Amazon\n"
        "                       Renewed, which is the only way to sell refurbished, so refurbished items stay off Amazon.\n"
        "quantity               for items we ship: On Hand minus what is Held for Store customers, never less than 0.\n"
        "                       For FBA items leave it blank; Amazon counts what is in their warehouse.\n"
        "add-delete             a to add or update. Discontinued products are still live on Amazon from last year's upload,\n"
        "                       so keep them in the file, filled in as usual, with d so Amazon takes the offer down.\n"
        "item-note              the condition notes, blank for new items.\n"
        "fulfillment-center-id  DEFAULT for items we ship, AMAZON_NA for FBA.\n"))
    out = sorted([i for i in items if "excluded" not in i["tags"]], key=lambda i: i["sku"])
    rrows = [[i["sku"], i["pid"], "3" if i["id_kind"] == "upc" else "1", f"{i['price']:.2f}", i["cond_code"], i["qty"],
              "d" if i["status"] == "Discontinued" else "a", i["note"], i["fc"]] for i in out]
    write_csv(os.path.join(ref, "amazon_inventory.csv"), TEMPLATE, rrows)
    write_csv(os.path.join(sol, "amazon_inventory.csv"), TEMPLATE, rrows)

    def keys(*tags):
        return sorted(i["sku"] for i in out if any(t in i["tags"] for t in tags))
    write_json(os.path.join(ref, "notes.json"), {t: keys(t) for t in ("pid", "cond", "price_fba", "price_mfn", "sale", "qty", "discontinued")} |
               {"excluded": sorted(i["sku"] for i in items if "excluded" in i["tags"])})
    write_task_yaml(HERE, {
        "id": "amazon-inventory-loader", "track": "desk", "category": "reformatting",
        "title": "Build the Amazon inventory upload from the product sheet",
        "ask": ("Please get our products ready for Amazon: turn amazon_listing_sheet.xlsx into an Inventory Loader file using the "
                "template. My notes on how we list things are in the folder. Save it as amazon_inventory.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the Amazon ID column mixes 10-character ASINs with 12-digit UPCs (some stored as numbers); product-id-type is 1 for ASINs and 3 for UPCs, the shop SKU never goes in product-id, and two products with no Amazon ID are left out (checks: product id and type; one row per sku)",
            "conditions are typed freely (New - open box, like new (used), used, good, Refurb (shop rebuilt)); open box is code 1 Used; Like New, and three refurbished items stay off Amazon entirely (checks: item condition code; one row per sku)",
            "price is shelf price + $6.00 for items the shop ships and shelf price + 12% for FBA items; copying the shelf price, using one rule for both, or taking the in-store Sale Price moves the price (check: price rules)",
            "quantity is On Hand minus Held for Store for shop-shipped items, floored at 0 where holds exceed stock, blank for FBA, with fulfillment-center-id DEFAULT or AMAZON_NA (check: quantity and fulfillment)",
            "three discontinued products are still live on Amazon and must stay in the file with add-delete d, not be dropped (checks: add-delete; one row per sku)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Inventory Loader columns, exact order", "path": "amazon_inventory.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one row per sku", "path": "amazon_inventory.csv", "column": "sku", "ref": "amazon_inventory.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "amazon_inventory.csv", "equals_ref": "amazon_inventory.csv"},
            {"type": "csv_values_match", "name": "product id and type", "path": "amazon_inventory.csv", "ref": "amazon_inventory.csv", "key": "sku",
             "columns": ["product-id", "product-id-type"], "min_accuracy": 1.0, "must_match_keys": keys("pid")},
            {"type": "csv_values_match", "name": "item condition code", "path": "amazon_inventory.csv", "ref": "amazon_inventory.csv", "key": "sku",
             "columns": ["item-condition"], "min_accuracy": 1.0, "must_match_keys": keys("cond")},
            {"type": "csv_values_match", "name": "price rules", "path": "amazon_inventory.csv", "ref": "amazon_inventory.csv", "key": "sku",
             "columns": ["price"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": keys("price_fba", "sale")},
            {"type": "custom", "name": "quantity and fulfillment", "module": "check.py"},
            {"type": "csv_values_match", "name": "add-delete", "path": "amazon_inventory.csv", "ref": "amazon_inventory.csv", "key": "sku",
             "columns": ["add-delete"], "min_accuracy": 1.0, "must_match_keys": keys("discontinued")},
        ],
    })
    print(f"seed={seed}: {len(items)} sheet rows, {len(out)} in file; " + ", ".join(f"{t}={len(keys(t))}" for t in ("pid", "cond", "price_fba", "sale", "qty", "discontinued")))


if __name__ == "__main__":
    emit(argparse_seed())
