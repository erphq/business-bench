#!/usr/bin/env python3
"""variants-flatten: an outdoor shop's nested catalog sheet (product rows with indented variant rows) into the
flat one-row-per-variant import file of the inventory platform it is moving to.

    python gen.py [--seed N] [--naive DIR]

Business: Granite Peak Outfitters keeps its fall catalog the way the owner likes to read it: a product row with
the price, then indented lines for the sizes and colours, typed as briefly as possible ("S, M, L / Olive").
Stockwell, the new inventory platform, wants one row per sellable variant.

Traps (each caught by a check, see task.yaml):
  * variant lines carry no product code or name; heading rows (OUTERWEAR) are not products   (checks: skus; mapped fields)
  * one line can stand for several combinations ("S, M, L / Olive", "10L, 20L / Yellow, Blue")  (checks: skus; row count)
  * blank price inherits the product price, "+10" adds to it, a full price overrides            (check: prices)
  * sold-out variants ("0", "sold out", "on order", "-", oversold "-2") stay at 0 / out_of_stock (checks: skus; stock)
  * products without options are one row whose sku is the product code                         (checks: skus; mapped fields)
  * last spring's upload is in the folder with old prices and an old variant list                (checks: prices; skus)
"""
from __future__ import annotations

import argparse
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["product_code", "product_name", "sku", "option1_name", "option1_value", "option2_name", "option2_value",
            "price", "inventory_qty", "availability"]

# Catalog structure is fixed across seeds (so pinned SKUs stay valid); prices and stock re-roll.
# line = (values per option, price spec, stock spec)
#   price spec: None (inherit) | ("plus", n) | ("abs", x)
#   stock spec: ("n", k) | ("each", k) | ("zero",) | ("soldout",) | ("onorder",) | ("dash",) | ("oversold", k)
CATALOG = [
    ("OUTERWEAR", [
        ("TJ24", "Ridgeline Trail Jacket", ["Size", "Color"], (119, 139), [
            ([["S"], ["Black"]], None, ("n",)),
            ([["M"], ["Black"]], None, ("n",)),
            ([["L"], ["Black"]], None, ("n",)),
            ([["XL"], ["Black"]], ("plus", 10), ("n",)),
            ([["S", "M", "L"], ["Olive"]], None, ("each",)),
            ([["XL"], ["Olive"]], ("plus", 10), ("soldout",)),
        ]),
        ("FV11", "Summit Fleece Vest", ["Size", "Color"], (68, 82), [
            ([["S", "M", "L", "XL"], ["Navy", "Rust"]], None, ("each",)),
            ([["M"], ["Sand"]], ("abs", 0.8), ("n",)),
            ([["L"], ["Sand"]], ("abs", 0.8), ("zero",)),
        ]),
        ("RS03", "Storm Shell Pants", ["Size"], (92, 108), [
            ([["S"]], None, ("n",)),
            ([["M"]], None, ("oversold",)),
            ([["L"]], None, ("n",)),
            ([["XL"]], ("plus", 8), ("n",)),
        ]),
    ]),
    ("SOCKS & SMALL GOODS", [
        ("WS3P", "Merino Wool Socks 3-Pack", ["Size"], (22, 28), [
            ([["S", "M", "L"]], None, ("each",)),
            ([["XL"]], ("plus", 2), ("onorder",)),
        ]),
        ("HL300", "Headlamp 300lm", [], (39, 49), [(None, None, ("n",))]),
        ("WB10", "Insulated Water Bottle", ["Size", "Color"], (28, 36), [
            ([["750ML"], ["Blue"]], None, ("n",)),
            ([["750ML"], ["Orange"]], None, ("soldout",)),
            ([["1L"], ["Blue", "Green"]], ("plus", 6), ("each",)),
        ]),
        ("MC01", "Waterproof Map Case", [], (12, 18), [(None, None, ("zero",))]),
    ]),
    ("CAMP", [
        ("CS01", "Two-Burner Camp Stove", [], (84, 96), [(None, None, ("n",))]),
        ("TP22", "Carbon Trekking Poles", ["Color"], (74, 86), [
            ([["Slate"]], None, ("n",)),
            ([["Red"]], None, ("dash",)),
            ([["Green"]], ("abs", 0.85), ("n",)),
        ]),
        ("DB20", "Roll-Top Dry Bag", ["Size", "Color"], (24, 30), [
            ([["10L"], ["Yellow", "Blue"]], None, ("each",)),
            ([["20L"], ["Yellow", "Blue"]], ("plus", 5), ("each",)),
            ([["35L"], ["Blue"]], ("abs", 1.45), ("n",)),
        ]),
        ("TN2P", "Backcountry Tent 2P", ["Color"], (309, 349), [
            ([["Sand"]], None, ("n",)),
            ([["Olive"]], ("plus", 20), ("n",)),
            ([["Orange"]], None, ("zero",)),
        ]),
        ("SP40", "Insulated Sleeping Pad", ["Size"], (109, 129), [
            ([["Regular"]], None, ("n",)),
            ([["Long"]], ("plus", 15), ("onorder",)),
            ([["Wide"]], ("plus", 25), ("n",)),
        ]),
    ]),
]


def build(seed: int) -> dict:
    r = rng(seed)
    products, lines_out, variants = [], [], []
    for section, prods in CATALOG:
        lines_out.append({"kind": "section", "text": section})
        for code_, name, opts, (lo, hi), lines in prods:
            base = float(r.randint(lo, hi)) + (0.0 if r.random() < 0.6 else 0.5)
            prod = {"code": code_, "name": name, "opts": opts, "price": base}
            products.append(prod)
            if not opts:
                stock_spec = lines[0][2]
                qty, stock_text = stock_value(r, stock_spec)
                lines_out.append({"kind": "product", "prod": prod, "stock_text": stock_text})
                variants.append({"prod": prod, "values": [], "price": base, "qty": qty, "sku": code_, "tag": "no_options"})
                continue
            lines_out.append({"kind": "product", "prod": prod, "stock_text": ""})
            for values, pspec, sspec in lines:
                if pspec is None:
                    price, ptext, ptag = base, "", "inherit"
                elif pspec[0] == "plus":
                    price, ptext, ptag = base + pspec[1], r.choice([f"+{pspec[1]}", f"+${pspec[1]}", f"+{pspec[1]}.00"]), "plus"
                else:
                    price = float(round(base * pspec[1]))
                    ptext, ptag = money_str(price, r.choice([1, 2])), "override"
                qty, stock_text = stock_value(r, sspec)
                combos = list(itertools.product(*values))
                for combo in combos:
                    tag = ptag
                    if len(combos) > 1:
                        tag += "+combo"
                    if qty == 0:
                        tag += "+oos"
                    variants.append({"prod": prod, "values": list(combo), "price": price, "qty": qty,
                                     "sku": "-".join([code_] + [v.upper() for v in combo]), "tag": tag})
                lines_out.append({"kind": "variant", "prod": prod, "values": values, "price_text": ptext,
                                  "stock_text": stock_text})
    return {"products": products, "lines": lines_out, "variants": variants}


def stock_value(r, spec):
    k = spec[0]
    if k == "n":
        q = r.randint(2, 18)
        return q, str(q)
    if k == "each":
        q = r.randint(2, 9)
        return q, r.choice([f"{q} each", f"{q} ea", f"{q} each size"])
    if k == "zero":
        return 0, "0"
    if k == "soldout":
        return 0, r.choice(["sold out", "SOLD OUT", "Sold out"])
    if k == "onorder":
        return 0, r.choice(["on order", "on order (Oct)", "none - on order"])
    if k == "dash":
        return 0, "-"
    if k == "oversold":
        return 0, f"-{r.randint(1, 3)}"
    raise ValueError(k)


def availability(qty: int) -> str:
    return "in_stock" if qty > 0 else "out_of_stock"


def flat_rows(d: dict) -> list[list]:
    rows = []
    for v in sorted(d["variants"], key=lambda x: x["sku"]):
        p = v["prod"]
        o1n = p["opts"][0] if len(p["opts"]) > 0 else ""
        o2n = p["opts"][1] if len(p["opts"]) > 1 else ""
        o1v = v["values"][0] if len(v["values"]) > 0 else ""
        o2v = v["values"][1] if len(v["values"]) > 1 else ""
        rows.append([p["code"], p["name"], v["sku"], o1n, o1v, o2n, o2v, f"{v['price']:.2f}", v["qty"], availability(v["qty"])])
    return rows


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 77)

    # ---- workspace: the nested catalog ----
    xrows = []
    for ln in d["lines"]:
        if ln["kind"] == "section":
            xrows.append(["", ln["text"], "", "", "", ""])
        elif ln["kind"] == "product":
            p = ln["prod"]
            price_txt = money_str(p["price"], r.choice([1, 1, 2, 6]))
            xrows.append([p["code"], p["name"], " / ".join(p["opts"]), price_txt, ln["stock_text"], ""])
        else:
            vals = " / ".join(", ".join(vs) for vs in ln["values"])
            indent = r.choice(["    ", "   - ", "  > "])
            note = ""
            if ln["stock_text"] in ("0",) or "on order" in ln["stock_text"]:
                note = r.choice(["reorder placed", "ask Tom", ""])
            xrows.append(["", indent + vals, "", ln["price_text"], ln["stock_text"], note])
    write_xlsx(os.path.join(ws, "product_catalog_fall.xlsx"), {"Fall 2026": {
        "merged_title": "Granite Peak Outfitters - Fall 2026 catalog",
        "preamble": [["Stock as of 8 Sep 2026", "", "", "", "", ""]],
        "header": ["Code", "Product / variant", "Options", "Price", "Stock", "Notes"],
        "rows": xrows, "widths": {"A": 9, "B": 34, "C": 14, "D": 10, "E": 16, "F": 18}}}, creator="Granite Peak")

    write_csv(os.path.join(ws, "stockwell_variant_template.csv"), TEMPLATE,
              [["DEMO1", "Demo Rain Hat", "DEMO1-M-RED", "Size", "M", "Color", "Red", "34.00", "7", "in_stock"]])
    write_text(os.path.join(ws, "stockwell_import_notes.txt"), (
        "Stockwell - variant import, field notes\n"
        "\n"
        "Use stockwell_variant_template.csv as-is: same columns, same order, same header spelling.\n"
        "One row per sellable variant. A variant is one combination of option values (one size in one colour).\n"
        "\n"
        "product_code    the parent product's code. Every variant of a product repeats it.\n"
        "product_name    the parent product's name, repeated on every variant row.\n"
        "sku             unique per row.\n"
        "option1_name    the first option (e.g. Size). option1_value is that variant's value.\n"
        "option2_name    the second option if the product has one (e.g. Color), otherwise blank; same for option2_value.\n"
        "                A product with no options is a single row with all four option columns blank.\n"
        "price           the selling price of that variant as a plain number, two decimals, no currency sign.\n"
        "inventory_qty   whole units on hand, never negative. 0 when nothing is on the shelf.\n"
        "availability    in_stock when inventory_qty is above 0, otherwise out_of_stock.\n"
        "\n"
        "Rows with out_of_stock still import; customers see them as sold out.\n"))
    write_email_thread(os.path.join(ws, "note_from_june.txt"), [
        {"from": "June Okafor <june@granitepeak.com>", "to": "you", "date": "Tue, 8 Sep 2026 17:40",
         "subject": "catalog into Stockwell",
         "body": ("The fall catalog sheet is the current one - ignore the spring upload file, those prices are old.\n\n"
                  "How I write the sheet, since it only makes sense to me: a line with a code is the product and its price. "
                  "The indented lines under it are the sizes and colours in the order the Options column gives them. "
                  "When a line says \"S, M, L / Olive\" I mean every one of those sizes in olive, and the stock figure is "
                  "for each of them. A blank price means the product price. \"+10\" means ten dollars more than the "
                  "product price. A full price like $59.00 is that variant's own price (clearance).\n\n"
                  "Our SKUs are the product code followed by each option value, with dashes, all capitals - TJ24-M-OLIVE. "
                  "Things without sizes or colours just use the product code.\n\n"
                  "Sold out, on order, a dash, or a minus number (the till oversold it) all mean none on the shelf. "
                  "Keep those in, I want them to show as sold out, not disappear.")}])
    # distractor: last spring's upload, old prices, fewer variants, right format
    spring = []
    for row in flat_rows(d):
        if row[0] in ("TJ24", "HL300", "WB10", "CS01", "TP22") and row[2] not in ("TJ24-XL-OLIVE", "WB10-1L-GREEN"):
            old = float(row[7]) - r.choice([5, 6, 10])
            spring.append(row[:7] + [f"{old:.2f}", r.randint(0, 15), "in_stock"])
    for row in spring:
        row[9] = availability(row[8])
    write_csv(os.path.join(ws, "stockwell_upload_2026-03.csv"), TEMPLATE, spring)

    # ---- reference and solution ----
    rows = flat_rows(d)
    write_csv(os.path.join(ref, "variants_flat.csv"), TEMPLATE, rows)
    write_csv(os.path.join(sol, "variants_flat.csv"), TEMPLATE, rows)
    v = d["variants"]
    pins_price = sorted(x["sku"] for x in v if x["tag"].split("+")[0] in ("plus", "override") or "+combo" in x["tag"])
    pins_stock = sorted(x["sku"] for x in v if "+oos" in x["tag"] or x["tag"] == "no_options" or "+combo" in x["tag"])
    pins_map = sorted(x["sku"] for x in v if x["tag"] == "no_options" or "+combo" in x["tag"])
    write_json(os.path.join(ref, "notes.json"), {"variants": len(v), "combo_skus": sorted(x["sku"] for x in v if "+combo" in x["tag"]),
                                                  "out_of_stock_skus": sorted(x["sku"] for x in v if x["qty"] == 0),
                                                  "no_option_skus": sorted(x["sku"] for x in v if x["tag"] == "no_options")})
    combo_lines = sum(1 for ln in d["lines"] if ln["kind"] == "variant" and len(list(itertools.product(*ln["values"]))) > 1)
    lost = sum(1 for x in v if "+combo" in x["tag"]) - combo_lines
    write_task_yaml(HERE, {
        "id": "variants-flatten", "track": "desk", "category": "reformatting",
        "title": "Flatten the nested fall catalog into the inventory platform's variant import",
        "ask": ("We're loading the fall catalog into Stockwell and they want one row per variant using their template; "
                "their notes and June's note about how she writes the sheet are in the folder. Save it as variants_flat.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "variant lines are indented under their product with no code or name of their own, and heading rows (OUTERWEAR, CAMP) "
            "are not products; each variant must repeat its parent's code and name (checks: one row per variant; product and option fields)",
            "one line can stand for several combinations - 'S, M, L / Olive' is three variants and 'S, M, L, XL / Navy, Rust' is "
            f"eight - with the stock figure ('4 each') applying to each; copying each line as one row loses {lost} variants "
            "(checks: one row per variant; row count; stock quantity; availability)",
            "a blank price inherits the product row's price, '+10' / '+$10' adds to it and a full price is the variant's own "
            "clearance price; reading '+10' as 10 or leaving blanks blank breaks every variant price (check: prices)",
            "sold-out variants are written '0', 'sold out', 'on order (Oct)', '-' and an oversold '-2'; they stay in the file "
            "with inventory 0 and out_of_stock rather than being dropped or imported negative (checks: one row per variant; "
            "stock quantity; availability)",
            "products with no options (headlamp, map case, stove) carry their price and stock on the product row and become one "
            "row whose sku is the bare product code with blank option columns (checks: one row per variant; product and option fields)",
            "last spring's upload sits in the folder in the right format but with old prices and a shorter variant list; "
            "June's note says ignore it (checks: prices; one row per variant)",
            "the template's ten columns in exact order, SKUs built from the house pattern TJ24-M-OLIVE, and the template's "
            "availability spellings (checks: template columns; one row per variant; stock quantity; availability)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns", "path": "variants_flat.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one row per variant", "path": "variants_flat.csv", "column": "sku", "ref": "variants_flat.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "variants_flat.csv", "equals_ref": "variants_flat.csv"},
            {"type": "csv_values_match", "name": "prices", "path": "variants_flat.csv", "ref": "variants_flat.csv", "key": "sku",
             "columns": ["price"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": pins_price},
            {"type": "csv_values_match", "name": "stock quantity", "path": "variants_flat.csv", "ref": "variants_flat.csv", "key": "sku",
             "columns": ["inventory_qty"], "numeric": True, "tolerance": 0.001, "min_accuracy": 1.0, "must_match_keys": pins_stock},
            {"type": "csv_values_match", "name": "availability", "path": "variants_flat.csv", "ref": "variants_flat.csv", "key": "sku",
             "columns": ["availability"], "min_accuracy": 1.0, "must_match_keys": pins_stock},
            {"type": "csv_values_match", "name": "product and option fields", "path": "variants_flat.csv", "ref": "variants_flat.csv",
             "key": "sku", "columns": ["product_code", "product_name", "option1_name", "option1_value", "option2_name", "option2_value"],
             "min_accuracy": 1.0, "must_match_keys": pins_map},
        ],
    })
    print(f"seed={seed}: {len(v)} variants, {sum(1 for x in v if x['qty'] == 0)} out of stock, "
          f"{sum(1 for x in v if '+combo' in x['tag'])} from combination lines")


def write_naive(d: dict, out: str) -> None:
    """Forward-fill the product code and name, one row per sheet line, '+10' read as 10, blank price left blank,
    non-numeric stock dropped as a row."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for ln in d["lines"]:
        if ln["kind"] == "product":
            cur = ln["prod"]
            if not cur["opts"]:
                q = ln["stock_text"]
                if q.lstrip("-").isdigit():
                    rows.append([cur["code"], cur["name"], cur["code"], "", "", "", "", f"{cur['price']:.2f}", q, availability(int(q))])
        elif ln["kind"] == "variant":
            p = ln["prod"]
            vals = [", ".join(vs) for vs in ln["values"]]
            q = ln["stock_text"].split()[0]
            if not q.lstrip("-").isdigit():
                continue
            price = ln["price_text"].replace("+", "").replace("$", "")
            rows.append([p["code"], p["name"], "-".join([p["code"]] + [x.upper().replace(", ", "-") for x in vals]),
                         p["opts"][0], vals[0], p["opts"][1] if len(p["opts"]) > 1 else "", vals[1] if len(vals) > 1 else "",
                         price, q, availability(int(q))])
    write_csv(os.path.join(out, "variants_flat.csv"), TEMPLATE, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
