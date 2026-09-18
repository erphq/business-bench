#!/usr/bin/env python3
"""shopify-product-import: an outdoor shop's fall catalog workbook becomes a Shopify product import CSV.

    python gen.py [--seed N]

Business: a two-store outdoor retailer opening its online shop. The catalog lives in a workbook, one row per
SKU; Shopify wants one handle per product with a row per variant, in its template's column order.

Traps (each caught by a check, see task.yaml):
  * variants go under one handle per style; product-level fields sit on the first row only; option names follow
    the note (Color then Size; Size alone; Title / Default Title for one-variant products)
                                                                   (checks: handles; option values; first-row product fields)
  * handles for new products follow the slug rules in the note (& to and, apostrophes and accents dropped, en dash
    and parentheses collapse to one hyphen); three products already in the store keep the handle from the November
    export                                                         (check: handles)
  * Retail is filled only on each style's first row, 2XL is $5 more, and a sale price moves retail into Compare At
                                                                   (checks: variant price; compare-at and bare-number prices)
  * prices must be bare numbers ("$1,249.00" is text in the catalog) (check: compare-at and bare-number prices)
  * weights come in lb, oz and kg and must be whole grams         (check: grams)
  * negative on-hand counts import as 0                           (check: inventory quantity)
  * Excel dropped the leading zero from some UPCs                 (check: barcodes)
  * discontinued styles and one discontinued variant are left out  (checks: one row per SKU; row count)
"""
from __future__ import annotations
import os, re, sys, unicodedata
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags", "Published", "Option1 Name",
            "Option1 Value", "Option2 Name", "Option2 Value", "Variant SKU", "Variant Grams", "Variant Inventory Tracker",
            "Variant Inventory Qty", "Variant Inventory Policy", "Variant Fulfillment Service", "Variant Price",
            "Variant Compare At Price", "Variant Requires Shipping", "Variant Taxable", "Variant Barcode", "Variant Weight Unit", "Status"]

# style, name, brand, category, colors, sizes, price, sale, weight(value, unit), status, existing handle
STYLES = [
    ("GP-1001", "Men's Ridgeline Rain Jacket", "Granite Peak", "Jackets", ["Blue", "Black"], ["S", "M", "L", "XL", "2XL"], 129.00, None, (1.1, "lb"), "Active", "mens-ridgeline-jacket"),
    ("GP-1002", "Women's Ridgeline Rain Jacket", "Granite Peak", "Jackets", ["Teal", "Plum"], ["XS", "S", "M", "L"], 129.00, None, (0.95, "lb"), "Active", None),
    ("GP-2040", "Hike & Bike Merino Socks (3-Pack)", "Thistle Wool Co.", "Socks", [], ["S", "M", "L"], 24.00, None, (7.5, "oz"), "Active", "merino-hike-socks-3pk"),
    ("GP-3100", "Trail Runner 2.0", "Switchback", "Footwear", ["Slate", "Moss"], ["8", "9", "10", "11"], 139.95, None, (0.62, "kg"), "Active", None),
    ("GP-4010", "Café Enamel Camp Mug", "Granite Peak", "Camp Kitchen", [], [], 18.00, None, (9.0, "oz"), "Active", "enamel-camp-mug"),
    ("GP-5020", "Summit 20L Daypack", "Granite Peak", "Packs", ["Red", "Forest", "Black"], [], 89.00, 69.00, (1.4, "lb"), "Active", None),
    ("GP-6003", "Basecamp 4P Tent", "Ridgeway", "Tents", ["Sand", "Olive"], [], 1249.00, None, (4.35, "kg"), "Active", None),
    ("GP-7001", "Alpine Down Vest", "Granite Peak", "Jackets", ["Black", "Rust"], ["M", "L", "2XL"], 149.00, None, (11.2, "oz"), "Coming Soon", None),
    ("GP-8015", "Kids' Puddle Boots", "Switchback", "Footwear", [], ["Toddler 8", "Toddler 9", "Toddler 10"], 39.50, None, (0.8, "lb"), "Active", None),
    ("GP-9002", "Trekking Poles – Pair", "Ridgeway", "Accessories", [], [], 79.00, None, (540, "g"), "Active", None),
    ("GP-9900", "Classic Canvas Hat", "Granite Peak", "Accessories", ["Khaki"], ["S/M", "L/XL"], 32.00, None, (4.0, "oz"), "Discontinued", None),
]
COLOR_CODE = {"Blue": "BLU", "Black": "BLK", "Teal": "TEA", "Plum": "PLM", "Slate": "SLT", "Moss": "MOS", "Red": "RED", "Forest": "FOR",
              "Sand": "SND", "Olive": "OLV", "Rust": "RST", "Khaki": "KHK"}
GRAMS = {"lb": 453.59237, "oz": 28.349523125, "kg": 1000.0, "g": 1.0}


def slug(name: str) -> str:
    s = name.replace("&", " and ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace("'", "").replace("’", "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def upc_check(d11: str) -> str:
    odd = sum(int(c) for c in d11[0::2]); even = sum(int(c) for c in d11[1::2])
    return d11 + str((10 - (odd * 3 + even) % 10) % 10)


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 606)
    variants = []
    for (style, name, brand, cat, colors, sizes, price, sale, (wv, wu), status, existing) in STYLES:
        combos = [(c, z) for c in (colors or [None]) for z in (sizes or [None])]
        handle = existing or slug(name)
        for k, (c, z) in enumerate(combos):
            sku = style.replace("-", "") + (f"-{COLOR_CODE[c]}" if c else "") + (f"-{z.replace('Toddler ', 'T').replace('/', '')}" if z else "")
            lead0 = r.random() < 0.3
            upc = upc_check(("0" if lead0 else str(r.randint(6, 8))) + f"{r.randint(0, 9999999999):010d}")
            p = price + (5.0 if z == "2XL" else 0.0)
            onhand = r.randint(0, 40)
            wjit = round(wv * (1 + (0.04 if z in ("L", "XL", "2XL", "11") else 0)), 2) if wu != "g" else wv
            variants.append({"style": style, "name": name, "brand": brand, "cat": cat, "color": c, "size": z, "sku": sku,
                             "upc": upc, "retail": p, "sale": (sale + (5.0 if z == "2XL" else 0.0)) if sale else None,
                             "weight": (wjit, wu), "onhand": onhand, "status": status, "handle": handle, "first": k == 0,
                             "colors": colors, "sizes": sizes, "discontinued_variant": False})
    # one discontinued variant inside an active style, two negative counts, one explicit leading-zero upc on a trap row
    jacket = [v for v in variants if v["style"] == "GP-1001"]
    jacket[-1]["discontinued_variant"] = True     # Black 2XL
    for v in r.sample([v for v in variants if v["status"] == "Active" and not v["first"]], 2):
        v["onhand"] = -r.randint(1, 3)
    keep = [v for v in variants if v["status"] != "Discontinued" and not v["discontinued_variant"]]
    return {"variants": variants, "keep": keep}


def option_names(v: dict) -> tuple[str, str]:
    if v["colors"] and v["sizes"]:
        return "Color", "Size"
    if v["colors"]:
        return "Color", ""
    if v["sizes"]:
        return "Size", ""
    return "Title", ""


def option_values(v: dict) -> tuple[str, str]:
    if v["colors"] and v["sizes"]:
        return v["color"], v["size"]
    if v["colors"]:
        return v["color"], ""
    if v["sizes"]:
        return v["size"], ""
    return "Default Title", ""


def grams(v: dict) -> int:
    val, unit = v["weight"]
    return int(val * GRAMS[unit] + 0.5)


def fmt_num(x: float) -> str:
    return f"{x:.2f}"


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed * 1000 + 607)

    # ---- catalog workbook (one row per SKU; retail only on the first row of a style) ----
    rows = []
    for v in d["variants"]:
        price_cell = None
        if v["first"]:
            price_cell = f"${v['retail']:,.2f}" if v["retail"] >= 1000 or r.random() < 0.5 else v["retail"]
        sale_cell = (f"{v['sale']:.2f}" if v["first"] else None) if v["sale"] else None
        wv, wu = v["weight"]
        wtxt = f"{wv:g} {wu}" if r.random() < 0.7 else f"{wv:g}{wu}"
        upc_cell = int(v["upc"]) if v["upc"].startswith("0") else v["upc"]
        status = "Discontinued" if v["discontinued_variant"] else v["status"]
        rows.append([v["style"], v["name"], v["brand"], v["cat"], v["color"] or "", v["size"] or "", v["sku"], upc_cell,
                     price_cell, sale_cell, wtxt, v["onhand"], status])
    write_xlsx(os.path.join(ws, "catalog_fall_2026.xlsx"), {"Catalog": {
        "merged_title": "Granite Peak Outfitters - Fall 2026 catalog", "preamble": [["Prices USD. Retail applies to every size of a style unless noted."]],
        "header": ["Style #", "Product Name", "Brand", "Category", "Color", "Size", "SKU", "UPC", "Retail", "Sale Price", "Weight", "On Hand", "Status"],
        "rows": rows, "widths": {"B": 36, "G": 20, "H": 16}}}, creator="Merchandising")

    # ---- Shopify template (header + Shopify-style sample rows) ----
    sample = [
        ["example-hiking-hat", "Example Hiking Hat", "<p>Sample product</p>", "Example Brand", "", "Hats", "sample", "TRUE", "Size", "S/M", "", "",
         "EX-HAT-SM", "85", "shopify", "10", "deny", "manual", "25.00", "", "TRUE", "TRUE", "", "g", "active"],
        ["example-hiking-hat", "", "", "", "", "", "", "", "", "L/XL", "", "", "EX-HAT-LXL", "90", "shopify", "4", "deny", "manual", "25.00", "",
         "TRUE", "TRUE", "", "g", ""],
    ]
    write_csv(os.path.join(ws, "product_template.csv"), TEMPLATE, sample)

    # ---- November export of the live store (existing handles, old prices) ----
    exp_header = ["Handle", "Title", "Vendor", "Type", "Published", "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value",
                  "Variant SKU", "Variant Price", "Status"]
    exp = []
    for (style, name, brand, cat, colors, sizes, price, sale, w, status, existing) in STYLES:
        if not existing:
            continue
        for k, v in enumerate([x for x in d["variants"] if x["style"] == style][:3]):
            n1, n2 = option_names(v); o1, o2 = option_values(v)
            exp.append([existing, name if k == 0 else "", brand if k == 0 else "", cat if k == 0 else "", "TRUE" if k == 0 else "",
                        n1 if k == 0 else "", o1, n2 if k == 0 else "", o2, v["sku"], f"{price - 10 if price > 50 else price - 2:.2f}", "active" if k == 0 else ""])
    write_csv(os.path.join(ws, "shopify_products_export_2025-11.csv"), exp_header, exp)

    write_text(os.path.join(ws, "import_notes_from_jess.txt"), """Getting the fall catalog into Shopify - notes

- Use the columns in Shopify's product_template.csv exactly, same order.
- One product per style number. Each color/size is a variant row under the same handle. Product fields (Title, Body,
  Vendor, Type, Tags, Published, Status, and the option names) go on the first row of each product only, like the
  sample; the other variant rows just repeat the handle and fill the variant columns.
- Handles: products already on the store (see the November export) keep their existing handle or Shopify creates
  duplicates. New handles: lower case, & becomes "and", drop apostrophes and accents, anything else that isn't a
  letter or a number becomes a single hyphen, no hyphens at either end.
- Options: Color first, then Size. Products that only come in sizes use Size as Option1; products that only come in
  colors use Color. One-variant products use Option1 Name "Title" and Option1 Value "Default Title".
- Price: plain numbers, no $ or commas. Retail is only filled on the first row of each style and applies to all its
  variants, except 2XL which is $5 more. Where there is a sale price, that is the Variant Price and retail goes in
  Variant Compare At Price (2XL still +$5 on both). Otherwise leave Compare At blank.
- Variant Grams: the Weight column in grams, whole numbers. Weight Unit g.
- On Hand goes to Variant Inventory Qty. Negative counts are miscounts, import them as 0.
- UPCs are 12 digits. Excel dropped the leading zero on some of them, put it back.
- Status: Active -> active with Published TRUE. Coming Soon -> draft with Published FALSE. Anything Discontinued
  (whole style or a single variant) stays out of the file.
- Vendor is the Brand column, Type is the Category. Inventory Tracker shopify, Inventory Policy deny, Fulfillment
  Service manual, Requires Shipping TRUE, Taxable TRUE.
""")

    # ---- reference ----
    out = []
    for v in d["keep"]:
        n1, n2 = option_names(v); o1, o2 = option_values(v)
        first = v["sku"] == next(x["sku"] for x in d["keep"] if x["style"] == v["style"])
        price = v["sale"] if v["sale"] else v["retail"]
        compare = fmt_num(v["retail"]) if v["sale"] else ""
        active = v["status"] == "Active"
        out.append([v["handle"], v["name"] if first else "", "", v["brand"] if first else "", "", v["cat"] if first else "", "",
                    ("TRUE" if active else "FALSE") if first else "", n1 if first else "", o1, n2 if first else "", o2, v["sku"], grams(v),
                    "shopify", max(0, v["onhand"]), "deny", "manual", fmt_num(price), compare, "TRUE", "TRUE", v["upc"], "g",
                    ("active" if active else "draft") if first else ""])
    write_csv(os.path.join(sol, "shopify_products.csv"), TEMPLATE, out)
    write_csv(os.path.join(ref, "shopify_products.csv"), TEMPLATE, out)
    # per-product truth for the first-row check
    products = []
    for style in dict.fromkeys(v["style"] for v in d["keep"]):
        v = next(x for x in d["keep"] if x["style"] == style)
        n1, n2 = option_names(v)
        products.append({"handle": v["handle"], "title": v["name"], "option1_name": n1, "option2_name": n2,
                         "status": "active" if v["status"] == "Active" else "draft", "published": "TRUE" if v["status"] == "Active" else "FALSE"})
    write_json(os.path.join(ref, "products.json"), products)

    keep = d["keep"]
    sku_of = lambda style, pred=lambda v: True: [v["sku"] for v in keep if v["style"] == style and pred(v)]
    handle_trap = sku_of("GP-1001")[:1] + sku_of("GP-3100")[:1] + sku_of("GP-2040")[:1] + sku_of("GP-4010") + sku_of("GP-1002")[:1] + sku_of("GP-8015")[:1] + sku_of("GP-9002")
    option_trap = sku_of("GP-2040")[:2] + sku_of("GP-4010") + sku_of("GP-5020")[:1] + sku_of("GP-9002")
    price_trap = [v["sku"] for v in keep if v["size"] == "2XL"] + [v["sku"] for v in keep if not v["first"]][:3] + sku_of("GP-5020") + sku_of("GP-6003")
    qty_trap = [v["sku"] for v in keep if v["onhand"] < 0]
    upc_trap = [v["sku"] for v in keep if v["upc"].startswith("0")][:6]
    uniq = lambda xs: list(dict.fromkeys(xs))
    write_task_yaml(HERE, {
        "id": "shopify-product-import", "track": "desk", "category": "reformatting",
        "title": "Fall catalog into Shopify's product import",
        "ask": "We're launching the online store. Turn the fall catalog into a Shopify product import using their template; Jess's notes have the rules. Save it as shopify_products.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "one catalog row per SKU must become one handle per style with a row per variant; product fields and option names belong on the first row only, as in Shopify's sample (checks: handles; first-row product fields and prices)",
            "new handles follow Jess's slug rules: \"Hike & Bike\" -> hike-and-bike, \"Men's\" -> mens, \"Café\" -> cafe, the en dash in \"Trekking Poles – Pair\" and the parentheses in \"(3-Pack)\" collapse to one hyphen (check: handles)",
            "three styles already live in the November export keep their existing handles (mens-ridgeline-jacket, merino-hike-socks-3pk, enamel-camp-mug), which the slug rule would change; the export's old prices are not this season's (check: handles)",
            "socks and kids' boots only have sizes (Option1 Size), the daypack and tent only colors (Option1 Color), the mug and poles are single-variant (Title / Default Title) (checks: option values; first-row product fields)",
            "Retail is filled only on each style's first row, 2XL is $5 more, and the daypack's sale price becomes the Variant Price with retail in Compare At; the tent's retail is the text \"$1,249.00\" (checks: variant price; first-row product fields and prices)",
            "weights are written in lb, oz, kg and g, sometimes without a space, and must become whole grams (check: grams)",
            "two variants have negative on-hand counts that import as 0 (check: inventory quantity)",
            "Excel dropped the leading zero from several UPCs, which must be 12 digits again (check: barcodes)",
            "the Classic Canvas Hat style and the Men's Ridgeline Black 2XL variant are discontinued and stay out; Alpine Down Vest is Coming Soon, so draft and Published FALSE (checks: one row per SKU; row count; first-row product fields)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Shopify template columns in order", "path": "shopify_products.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one row per SKU", "path": "shopify_products.csv", "column": "Variant SKU",
             "ref": "shopify_products.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "shopify_products.csv", "equals_ref": "shopify_products.csv"},
            {"type": "csv_values_match", "name": "handles", "path": "shopify_products.csv", "ref": "shopify_products.csv", "key": "Variant SKU",
             "columns": ["Handle"], "min_accuracy": 1.0, "must_match_keys": uniq(handle_trap)},
            {"type": "csv_values_match", "name": "option values", "path": "shopify_products.csv", "ref": "shopify_products.csv", "key": "Variant SKU",
             "columns": ["Option1 Value", "Option2 Value"], "min_accuracy": 1.0, "must_match_keys": uniq(option_trap)},
            {"type": "csv_values_match", "name": "variant price", "path": "shopify_products.csv", "ref": "shopify_products.csv", "key": "Variant SKU",
             "columns": ["Variant Price"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": uniq(price_trap)},
            {"type": "csv_values_match", "name": "grams", "path": "shopify_products.csv", "ref": "shopify_products.csv", "key": "Variant SKU",
             "columns": ["Variant Grams"], "numeric": True, "tolerance": 1.0, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "inventory quantity", "path": "shopify_products.csv", "ref": "shopify_products.csv", "key": "Variant SKU",
             "columns": ["Variant Inventory Qty"], "numeric": True, "tolerance": 0.0, "min_accuracy": 1.0, "must_match_keys": qty_trap},
            {"type": "csv_values_match", "name": "barcodes", "path": "shopify_products.csv", "ref": "shopify_products.csv", "key": "Variant SKU",
             "columns": ["Variant Barcode"], "normalize": ["strip"], "min_accuracy": 1.0, "must_match_keys": upc_trap},
            {"type": "custom", "name": "first-row product fields and prices", "module": "check.py"},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
