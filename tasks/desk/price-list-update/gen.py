#!/usr/bin/env python3
"""price-list-update: apply a supplier's price-change letter (PDF) to our master price list (xlsx).

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * the letter raises whole categories by a percentage AND lists fixed new prices for a handful of
    items; two of the fixed-price items sit inside a raised category and the table price wins  (check: new prices to the cent)
  * percentage results must be rounded to the cent; the grader tolerates 0.001              (check: new prices to the cent)
  * five items are discontinued and must disappear from the list, not be zeroed              (check: item set)
  * one valve is renumbered; the old code goes, the new code carries the valve increase      (check: item set; new prices)
  * a quarter of the master list's prices are stored as text ("$38.50")                       (check: new prices to the cent)
  * last year's notice sits in the folder with different percentages                          (check: new prices to the cent)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

def write_xlsx_pinned(path: str, sheets: dict, creator: str = "Export") -> None:
    """write_xlsx, then pin dcterms:modified: openpyxl re-stamps it with the wall clock inside save(),
    so two runs a second apart differ in bytes. (Local workaround; the library writer is otherwise fixed.)"""
    import re as _re, zipfile as _zip, io as _io
    write_xlsx(path, sheets, creator=creator)
    with _zip.ZipFile(path) as zin:
        items = [(zi.filename, zin.read(zi.filename)) for zi in zin.infolist()]
    fixed = []
    for name, data in items:
        if name == "docProps/core.xml":
            data = _re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", rb"\g<1>2026-01-15T09:00:00Z\g<2>", data)
        fixed.append((name, data))
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zout:
        for name, data in fixed:
            zi = _zip.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = _zip.ZIP_DEFLATED
            zout.writestr(zi, data)
    write_bytes(path, buf.getvalue())

SIZES = ['1/2"', '3/4"', '1"', '1-1/4"', '1-1/2"', '2"']
CATS = {
    "Fittings": ("FT", 1000, ["Elbow 90 {s} copper", "Tee {s} copper", "Coupling {s} PEX crimp", "Adapter {s} MIP x C", "Elbow 45 {s} PVC sch 40", "Union {s} brass"]),
    "Valves": ("VL", 2000, ["Ball valve {s} brass FIP", "Gate valve {s} bronze", "Check valve {s} spring", "Pressure reducing valve {s}", "Stop valve {s} quarter turn"]),
    "Pipe & Tube": ("PT", 3000, ["Copper type L {s} x 10 ft", "PVC sch 40 {s} x 10 ft", "PEX-A {s} x 100 ft coil", "CPVC {s} x 10 ft", "Black iron {s} x 21 ft"]),
    "Fixtures": ("FX", 4000, ["Kitchen faucet single handle", "Lavatory faucet 4 in centerset", "Toilet 1.28 gpf elongated", "Shower valve trim kit", "Water heater 40 gal gas",
                              "Water heater 50 gal electric", "Garbage disposal 1/2 HP", "Sump pump 1/3 HP", "Utility sink 24 in", "Laundry faucet 2 handle"]),
    "Tools": ("TL", 5000, ["Tubing cutter 1/8-1-1/8 in", "PEX crimp tool 1/2-3/4 in", "Basin wrench 11 in", "Pipe wrench 14 in", "Torch kit MAPP", "Drain auger 25 ft",
                           "Deburring tool", "Inspection mirror telescoping"]),
    "Consumables": ("CS", 6000, ["Solder lead-free 1 lb", "Flux paste 4 oz", "PVC cement 8 oz", "Primer purple 8 oz", "Thread seal tape 1/2 x 520 in", "Pipe dope 8 oz",
                                 "Emery cloth roll 1-1/2 x 10 yd", "Nitrile gloves box of 100", "Shop towels roll"]),
}
UOM = {"Fittings": "EA", "Valves": "EA", "Pipe & Tube": "LEN", "Fixtures": "EA", "Tools": "EA", "Consumables": "EA"}
PRICE_RANGE = {"Fittings": (1.2, 24), "Valves": (9, 140), "Pipe & Tube": (6, 95), "Fixtures": (85, 1300), "Tools": (14, 260), "Consumables": (2.5, 38)}

def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    for cat, (prefix, base, templates) in CATS.items():
        n = {"Fittings": 14, "Valves": 10, "Pipe & Tube": 10, "Fixtures": 10, "Tools": 8, "Consumables": 9}[cat]
        used = set(); k = 0
        while k < n:
            t = r.choice(templates)
            desc = t.format(s=r.choice(SIZES)) if "{s}" in t else t
            if desc in used: continue
            used.add(desc); k += 1
            lo, hi = PRICE_RANGE[cat]
            items.append({"code": f"{prefix}-{base + r.randint(1, 899):04d}", "desc": desc, "cat": cat, "uom": UOM[cat], "price": money(r, lo, hi)})
    # unique codes
    seen = set(); out = []
    for it in items:
        while it["code"] in seen:
            it["code"] = it["code"][:-1] + str((int(it["code"][-1]) + 1) % 10)
        seen.add(it["code"]); out.append(it)
    items = out
    pct = {"Fittings": 4.5, "Valves": 4.5, "Pipe & Tube": 7.0}
    # no percentage result may land exactly on a half cent (Excel rounds half up, Python floats may not)
    from decimal import Decimal
    for it in items:
        if it["cat"] in pct:
            while (Decimal(str(it["price"])) * (100 + Decimal(str(pct[it["cat"]])))) % 1 == Decimal("0.5"):
                it["price"] = round(it["price"] + 0.01, 2)
    by_cat = {c: [i for i in items if i["cat"] == c] for c in CATS}
    # fixed new prices: 3 fixtures, 2 tools, 1 consumable, 2 fittings (override)
    fixed = r.sample(by_cat["Fixtures"], 3) + r.sample(by_cat["Tools"], 2) + r.sample(by_cat["Consumables"], 1) + r.sample(by_cat["Fittings"], 2)
    for it in fixed:
        it["fixed"] = round(it["price"] * r.uniform(1.06, 1.18), 2)
        if it["fixed"] == round(it["price"] * (1 + pct.get(it["cat"], 0) / 100), 2): it["fixed"] = round(it["fixed"] + 0.4, 2)
    fixed_set = set(id(i) for i in fixed)
    # discontinued: 1 fitting, 1 pipe, 1 valve, 2 consumables (none already fixed)
    pool = lambda c: [i for i in by_cat[c] if id(i) not in fixed_set]
    disc = r.sample(pool("Fittings"), 1) + r.sample(pool("Pipe & Tube"), 1) + r.sample(pool("Valves"), 1) + r.sample(pool("Consumables"), 2)
    disc_set = set(id(i) for i in disc)
    # renumbered valve (not discontinued, not fixed)
    renamed = r.choice([i for i in by_cat["Valves"] if id(i) not in disc_set and id(i) not in fixed_set])
    renamed["new_code"] = "VL-" + str(2900 + r.randint(1, 99))
    while renamed["new_code"] in seen: renamed["new_code"] = "VL-" + str(2900 + r.randint(1, 99))
    # rounding-sensitive percent items: fractional cent at least 0.002 from the rounded value
    def frac_gap(it):
        raw = it["price"] * (1 + pct[it["cat"]] / 100); return abs(raw - round(raw, 2))
    sensitive = [i for i in items if i["cat"] in pct and id(i) not in fixed_set and id(i) not in disc_set and frac_gap(i) >= 0.002]
    # new prices (ground truth)
    final = []
    for it in items:
        if id(it) in disc_set: continue
        if "fixed" in it: newp = it["fixed"]
        elif it["cat"] in pct: newp = round(it["price"] * (1 + pct[it["cat"]] / 100), 2)
        else: newp = it["price"]
        final.append({"code": it.get("new_code", it["code"]), "desc": it["desc"], "cat": it["cat"], "uom": it["uom"], "price": newp})
    must = [i["code"] for i in fixed if i["cat"] == "Fittings"] + [renamed["new_code"]] + [i["code"] for i in sensitive[:3]] + [fixed[0]["code"]]
    return {"items": items, "pct": pct, "fixed": fixed, "disc": disc, "renamed": renamed, "final": final, "must": must, "sensitive": sensitive}

def emit(seed: int) -> None:
    d = build(seed); r = rng(seed + 1000)
    ws, ref, sol = task_dirs(HERE)
    # master list: title + preamble, header on row 3, a quarter of the prices as "$x" text
    rows = []
    for it in d["items"]:
        p = it["price"]
        rows.append([it["code"], it["desc"], it["cat"], it["uom"], money_str(p, 1) if r.random() < 0.25 else p, ""])
    write_xlsx_pinned(os.path.join(ws, "ironwood_price_list_2025.xlsx"), {"Price List": {
        "merged_title": "Ironwood Fabrication - supplier price list (effective 2025-10-01)",
        "preamble": [["Maintained by Westbrook Plumbing purchasing", "", "", "", "Prices in USD", ""]],
        "header": ["Item Code", "Description", "Category", "UOM", "Unit Price", "Notes"], "rows": rows,
        "number_formats": {"E": "0.00"}, "widths": {"A": 12, "B": 36, "C": 14, "E": 12}, "freeze": "A4"}}, creator="Purchasing")
    pct = d["pct"]; fx = d["fixed"]; disc = d["disc"]; rn = d["renamed"]
    write_pdf_document(os.path.join(ws, "ironwood_price_notice_2026.pdf"), [
        ("title", "Ironwood Fabrication"), ("small", "4410 Foundry Row, Tacoma WA 98402  |  orders@ironwoodfab.com"), ("hr", None),
        ("kv", [("Date", "September 8, 2026"), ("To", "Westbrook Plumbing, Purchasing"), ("Subject", "Price adjustment effective October 1, 2026")]),
        ("spacer", 6),
        ("p", "Dear customer,"),
        ("p", "Copper and brass costs have moved again this year and we are adjusting our list as follows, effective for all orders "
              "shipped on or after October 1, 2026. Please update your records; the items and codes below refer to our current price list."),
        ("h", "1. General increases by category"),
        ("table", [["Category", "Increase"]] + [[c, f"+{v:.1f}%"] for c, v in pct.items()] + [["All other categories", "no change"]], {"col_widths": [200, 100], "shade_header": True}),
        ("small", "Percentage increases apply to the current unit price and are rounded to the nearest cent."),
        ("h", "2. Items moving to a fixed new price"),
        ("p", "The following items are repriced individually. Where an item in this table also falls under a category increase above, "
              "the price in this table applies instead of the percentage."),
        ("table", [["Item code", "Description", "Current", "New price"]] + [[i["code"], i["desc"], money_str(i["price"], 1), money_str(i["fixed"], 1)] for i in fx],
         {"col_widths": [70, 210, 70, 70], "align_right": [2, 3], "grid": True}),
        ("h", "3. Discontinued items"),
        ("p", "The items below are discontinued and will not be available after September 30, 2026. Remove them from your price list; "
              "we will ship remaining stock at the current price until then."),
        ("table", [["Item code", "Description"]] + [[i["code"], i["desc"]] for i in disc], {"col_widths": [80, 260]}),
        ("h", "4. Renumbered item"),
        ("p", f"{rn['code']} ({rn['desc']}) has been renumbered to {rn['new_code']} in our new catalog. It is the same product; "
              f"list it under the new code. The valve increase in section 1 applies to it."),
        ("spacer", 8),
        ("p", "Questions to your account manager, Hiroshi Tanaka, 253-555-0142."),
        ("p", "Kind regards,\nIronwood Fabrication, Sales Administration"),
    ], font="Helvetica", base_size=10)
    # distractor: last year's notice with different numbers
    old_pct = {"Fittings": 3.0, "Pipe & Tube": 5.5}
    write_pdf_document(os.path.join(ws, "ironwood_price_notice_2025.pdf"), [
        ("title", "Ironwood Fabrication"), ("hr", None),
        ("kv", [("Date", "September 9, 2025"), ("To", "Westbrook Plumbing, Purchasing"), ("Subject", "Price adjustment effective October 1, 2025")]),
        ("p", "Effective October 1, 2025 the following category increases apply. All other prices are unchanged."),
        ("table", [["Category", "Increase"]] + [[c, f"+{v:.1f}%"] for c, v in old_pct.items()], {"col_widths": [200, 100]}),
        ("p", "This notice has been applied to your list already (see the effective date on your price list)."),
    ], font="Courier", base_size=10)
    write_text(os.path.join(ws, "note_from_gary.txt"),
               "The 2025 letter is already in the list we have, ignore it. The September 2026 one is what needs applying.\n"
               "Keep the same columns as the current file, headings in the top row and no title above them, so I can paste it straight into the ordering system. - Gary\n")
    header = ["item_code", "description", "category", "uom", "unit_price"]
    rows = [[f["code"], f["desc"], f["cat"], f["uom"], f["price"]] for f in d["final"]]
    write_csv(os.path.join(ref, "price_list.csv"), header, rows)
    write_xlsx_pinned(os.path.join(sol, "price_list_2026.xlsx"), {"Price List": {
        "header": ["Item Code", "Description", "Category", "UOM", "Unit Price"], "rows": rows,
        "number_formats": {"E": "0.00"}, "widths": {"A": 12, "B": 36, "C": 14, "E": 12}, "freeze": "A2"}}, creator="Purchasing")
    write_json(os.path.join(ref, "notes.json"), {"percent_by_category": pct, "fixed_price_items": [i["code"] for i in fx],
                                                  "fixed_inside_raised_category": [i["code"] for i in fx if i["cat"] in pct],
                                                  "discontinued": [i["code"] for i in disc], "renumbered": {rn["code"]: rn["new_code"]},
                                                  "rounding_sensitive": [i["code"] for i in d["sensitive"]]})
    write_task_yaml(HERE, {
        "id": "price-list-update", "track": "desk", "category": "spreadsheet",
        "title": "Apply the supplier's price letter to our master price list",
        "ask": "Ironwood sent their price letter for October. Apply it to our current price list and save the updated list as price_list_2026.xlsx. Gary's note is in the folder.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the letter raises three categories by a percentage and reprices eight items to fixed amounts; two fixed items sit inside a raised category and the table price wins over the percentage (check: new prices to the cent)",
            "percentage results carry fractions of a cent and must be rounded; the grader allows 0.001 (check: new prices to the cent)",
            "five items are discontinued and must be removed, not left at the old price or zeroed (check: item set)",
            f"one valve is renumbered ({rn['code']} to {rn['new_code']}); the old code must go and the new code carries the valve increase (check: item set)",
            "a quarter of the master prices are stored as text such as $38.50, header sits on row 3 under a merged title (check: new prices to the cent)",
            "last year's notice with different percentages is in the folder and already applied; using it double-counts (check: new prices to the cent)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "price_list_2026.xlsx", "columns": header},
            {"type": "csv_set_equal", "name": "item set", "path": "price_list_2026.xlsx", "column": "item_code", "ref": "price_list.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "price_list_2026.xlsx", "equals_ref": "price_list.csv"},
            {"type": "csv_values_match", "name": "new prices to the cent", "path": "price_list_2026.xlsx", "ref": "price_list.csv", "key": "item_code",
             "columns": ["unit_price"], "numeric": True, "tolerance": 0.001, "min_accuracy": 1.0, "must_match_keys": d["must"]},
            {"type": "csv_values_match", "name": "descriptions and categories carried over", "path": "price_list_2026.xlsx", "ref": "price_list.csv", "key": "item_code",
             "columns": ["description", "category"], "min_accuracy": 1.0},
            {"type": "xlsx_no_errors", "name": "workbook opens clean", "path": "price_list_2026.xlsx"},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
