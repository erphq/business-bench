#!/usr/bin/env python3
"""vendor-price-sheets: a wholesale bakery loads its suppliers' new price sheets for every item on its ordering guide.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * Pacific Packaging's superseded March list is in the folder as PPS_pricelist_FINAL.pdf, with lower prices and
    different quantity breaks; the October list says it supersedes all earlier lists   (checks: unit price at our order quantity; next price break)
  * the mill prices flour per hundredweight with a per-cwt volume allowance; a 50 lb bag is half a cwt and the rye
    comes in 25 lb bags                                                                  (check: unit price at our order quantity)
  * the dairy prints list prices only and gives its 5% and 8% quantity discounts in a footnote (checks: unit price at our order quantity; order total)
  * one order quantity sits exactly on a break (10 cases buys the 10-24 price) and items already at the best
    price carry 0 as the next break                                                      (check: next price break)
  * the dairy's butter lines are market priced with their own effective date, earlier than the rest of the sheet
                                                                                        (check: effective dates)
  * the coffee roaster's sheet is an image-only fax                                     (checks: one row per item; vendor names)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

BUYER = "Rosa Alvarez"
BAKERY = "Ellington Bakeries"

def build(seed: int) -> dict:
    r = rng(seed)
    items = []  # dict(sku, vendor, name, qty, unit, unit_price, next_break, effective, ...)
    # --- Pacific Packaging Supply: per-case tier prices 1-9 / 10-24 / 25+; superseded list 1-9 / 10-49 / 50+
    pps = [("PPS-4410", "Bakery box 10x10x4 white, 100/cs", "Cake boxes 10in", 12),
           ("PPS-4412", "Bakery box 12x12x5 white, 100/cs", "Cake boxes 12in", 10),
           ("PPS-2206", "Pastry bag 18in disposable, 500/cs", "Piping bags", 6),
           ("PPS-7708", "Deli paper 12x12 dry wax, 6000/cs", "Deli sheets", 30),
           ("PPS-3310", "Cake board 10in round gold, 100/cs", "Cake boards 10in", 4)]
    pps_rows = []
    for sku, desc, ours, qty in pps:
        t1 = money(r, 38, 96); t2 = round(t1 * 0.94, 2); t3 = round(t1 * 0.89, 2)
        o1 = round(t1 * 0.95, 2); o2 = round(o1 * 0.93, 2); o3 = round(o1 * 0.87, 2)
        tiers = [(1, t1), (10, t2), (25, t3)]
        price = [p for m, p in tiers if qty >= m][-1]
        nxt = next((m for m, _ in tiers if m > qty), 0)
        items.append(dict(sku=sku, vendor="Pacific Packaging Supply", ours=ours, qty=qty, unit="case", unit_price=price, next_break=nxt,
                          effective=date(2026, 10, 1)))
        pps_rows.append((sku, desc, (t1, t2, t3), (o1, o2, o3)))
    # --- Cascade Mill & Grain: per cwt, allowance per item per delivery: 10-39 bags -1.50/cwt, 40+ -3.00/cwt
    cmg = [("CMG-101", "Bread flour, high gluten", "Bread flour", 50, 40, [41.80, 42.60, 43.40]),
           ("CMG-104", "All-purpose flour, unbleached", "AP flour", 50, 12, [36.40, 37.20, 38.60]),
           ("CMG-120", "Whole wheat flour, stone ground", "Whole wheat flour", 50, 6, [44.20, 45.80, 46.60]),
           ("CMG-230", "Rye flour, medium", "Rye flour", 25, 4, [46.40, 47.60, 48.80])]
    cmg_rows = []
    for sku, desc, ours, lb, qty, choices in cmg:
        cwt = r.choice(choices)
        allow = 3.00 if qty >= 40 else 1.50 if qty >= 10 else 0.0
        price = round((cwt - allow) * lb / 100, 2)
        assert abs((cwt - allow) * lb / 100 - price) < 1e-9
        nxt = 10 if qty < 10 else 40 if qty < 40 else 0
        items.append(dict(sku=sku, vendor="Cascade Mill & Grain", ours=ours, qty=qty, unit=f"bag ({lb} lb)", unit_price=price, next_break=nxt,
                          effective=date(2026, 9, 15)))
        cmg_rows.append((sku, desc, f"{lb} lb", cwt))
    # --- Bluestem Dairy: list only; footnote 24-71 5% off, 72+ 8% off; butter market priced, effective 10/01
    bd = [("BD-2210", "Butter, unsalted AA, 36 lb case", "Butter 36 lb case", "case", 3, True, list(range(128, 156, 2))),
          ("BD-2215", "European-style butter 82%, 1 lb print", "Euro butter 1 lb", "lb", 72, True, [5, 6, 7]),
          ("BD-3104", "Heavy cream 40%, 1/2 gal", "Heavy cream", "1/2 gal", 24, False, [8, 9, 10]),
          ("BD-4001", "Cream cheese, 3 lb loaf", "Cream cheese loaf", "loaf", 30, False, [11, 12, 13])]
    bd_rows = []
    for sku, desc, ours, unit, qty, butter, choices in bd:
        lst = float(r.choice(choices))
        disc = 0.08 if qty >= 72 else 0.05 if qty >= 24 else 0.0
        price = round(lst * (1 - disc), 2)
        nxt = 24 if qty < 24 else 72 if qty < 72 else 0
        items.append(dict(sku=sku, vendor="Bluestem Dairy", ours=ours, qty=qty, unit=unit, unit_price=price, next_break=nxt,
                          effective=date(2026, 10, 1) if butter else date(2026, 10, 5)))
        bd_rows.append((sku, desc, unit, lst, butter))
    # --- Nightjar Coffee Roasters (fax scan): per 5 lb bag, 1-4 / 5-9 / 10+
    nj = [("NJ-01", "HOUSE ESPRESSO", "Espresso beans", 8), ("NJ-02", "DECAF SWISS WATER", "Decaf beans", 2), ("NJ-05", "COLD BREW COARSE", "Cold brew grind", 10)]
    nj_rows = []
    for sku, desc, ours, qty in nj:
        p1 = float(r.choice([48, 50, 52, 55, 58])); p2 = p1 - 2.50; p3 = p1 - 5.00
        tiers = [(1, p1), (5, p2), (10, p3)]
        price = [p for m, p in tiers if qty >= m][-1]
        nxt = next((m for m, _ in tiers if m > qty), 0)
        items.append(dict(sku=sku, vendor="Nightjar Coffee Roasters", ours=ours, qty=qty, unit="bag (5 lb)", unit_price=price, next_break=nxt,
                          effective=date(2026, 9, 1)))
        nj_rows.append((sku, desc, (p1, p2, p3)))
    for it in items:
        it["total"] = round(it["qty"] * it["unit_price"], 2)
    return dict(items=items, pps=pps_rows, cmg=cmg_rows, bd=bd_rows, nj=nj_rows)

def m2(x: float) -> str: return f"${x:,.2f}"

def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    P = os.path.join(ws, "price_sheets"); os.makedirs(P, exist_ok=True)

    # Pacific Packaging, current (Helvetica, gridded tier table)
    rows = [["SKU", "Description", "1-9 cs", "10-24 cs", "25+ cs"]] + [[s, desc, m2(t[0]), m2(t[1]), m2(t[2])] for s, desc, t, _ in d["pps"]]
    write_pdf_document(os.path.join(P, "PacificPackaging_Oct2026.pdf"), [
        ("title", "Pacific Packaging Supply"), ("small", "Bakery and Foodservice Price List  |  1840 Water St, Tacoma, WA 98402  |  orders@pacpacksupply.com"),
        ("hr", None),
        ("p", "<b>Effective October 1, 2026.</b> This price list supersedes all previous price lists. Prices are per case, F.O.B. Tacoma; "
              "quantity pricing is by the number of cases of each item on one order."),
        ("spacer", 6),
        ("table", rows, {"grid": True, "shade_header": True, "col_widths": [70, 210, 60, 65, 60]}),
        ("spacer", 8), ("small", "Freight prepaid on orders over $750. Prices subject to change with 30 days' notice.")],
        font="Helvetica", base_size=10)
    # Pacific Packaging, superseded March list (named FINAL)
    rows = [["Item", "Description", "Qty 1-9", "Qty 10-49", "Qty 50+"]] + [[s, desc, m2(o[0]), m2(o[1]), m2(o[2])] for s, desc, _, o in d["pps"]]
    write_pdf_document(os.path.join(P, "PPS_pricelist_FINAL.pdf"), [
        ("title", "Pacific Packaging Supply - Price List"), ("p", "Case prices. Quantity pricing by cases per item per order."), ("spacer", 4),
        ("table", rows, {"col_widths": [70, 210, 60, 65, 60]}),
        ("spacer", 10), ("small", "Prices effective March 1, 2026 until further notice.  Pacific Packaging Supply, Tacoma WA.")],
        font="Helvetica", base_size=10)
    # Cascade Mill & Grain (Times-Roman, A4, per cwt with allowance in prose)
    rows = [["Code", "Product", "Bag", "Price per cwt"]] + [[s, desc, bag, m2(cwt)] for s, desc, bag, cwt in d["cmg"]]
    write_pdf_document(os.path.join(P, "cascade_mill_fall_prices.pdf"), [
        ("right", "September 2, 2026"), ("title", "Cascade Mill &amp; Grain"), ("small", "Stone-milled flours since 1961  |  Eugene, OR 97401"), ("spacer", 6),
        ("p", "To our bakery customers: the prices below apply to all deliveries on or after September 15, 2026. All flour prices are quoted per "
              "hundredweight (cwt, 100 lb) and are invoiced by the bag."),
        ("spacer", 6), ("table", rows, {"col_widths": [60, 200, 60, 90]}), ("spacer", 6),
        ("p", "<b>Volume allowance.</b> Applied to each product separately on a single delivery: 10 to 39 bags, less $1.50 per cwt; "
              "40 bags or more, less $3.00 per cwt. Allowances are deducted on the invoice."),
        ("spacer", 10), ("p", "With thanks for your business,<br/>Cascade Mill &amp; Grain Sales Office")],
        font="Times-Roman", pagesize="a4", base_size=11)
    # Bluestem Dairy (Courier, list only, discounts and butter dates in footnotes)
    rows = [["Item #", "Description", "Unit", "List"]] + [[s + ("*" if butter else ""), desc, unit, m2(lst)] for s, desc, unit, lst, butter in d["bd"]]
    write_pdf_document(os.path.join(P, "Bluestem_Dairy_wholesale.pdf"), [
        ("kv", [("Customer", BAKERY), ("Sheet date", "09/28/2026"), ("Prices effective", "10/05/2026")]), ("hr", None),
        ("title", "BLUESTEM DAIRY - WHOLESALE PRICE SHEET"), ("spacer", 4),
        ("table", rows, {"shade_header": True, "col_widths": [70, 230, 60, 60]}),
        ("spacer", 8),
        ("small", "* Butter is market priced. Butter prices marked * are effective 10/01/2026 through 10/31/2026 and replace the September butter prices."),
        ("small", "Quantity discounts, per item per order: 24 to 71 units, 5% off list. 72 units or more, 8% off list."),
        ("small", "Bluestem Dairy Co-op, Madison WI. Net 15.")],
        font="Courier", base_size=9.5)
    # Nightjar Coffee Roasters (fax scan)
    lines = ["NIGHTJAR COFFEE ROASTERS", "WHOLESALE PRICE LIST", "EFFECTIVE SEPTEMBER 1, 2026", "", "ALL PRICES PER 5 LB BAG", "",
             "ITEM   COFFEE              1-4     5-9     10+"]
    for sku, desc, (p1, p2, p3) in d["nj"]:
        lines.append(f"{sku:<6} {desc:<18} {p1:>6.2f}  {p2:>6.2f}  {p3:>6.2f}")
    lines += ["", "QTY BREAKS BY BAGS OF EACH COFFEE", "PER ORDER. NET 30.", "", "FAX TO: ELLINGTON BAKERIES - ROSA"]
    write_scan_pdf(os.path.join(P, "fax_nightjar_0901.pdf"), lines, font_size=30, seed=seed + 21, skew_deg=-0.6, noise=600)

    # ordering guide (merged title, preamble)
    grows = [[it["ours"], it["sku"], it["qty"], it["unit"]] for it in d["items"]]
    order = [5, 0, 12, 9, 2, 15, 6, 13, 1, 10, 7, 3, 14, 11, 8, 4]
    grows = [grows[i] for i in order]
    write_xlsx(os.path.join(ws, "ordering_guide.xlsx"), {"Weekly order": {
        "merged_title": f"{BAKERY} - weekly ordering guide", "preamble": [["Usual quantities per order", "", "", "Updated 9/2026"]],
        "header": ["Item", "Vendor SKU", "Usual Order Qty", "Order Unit"], "rows": grows, "widths": {"A": 24, "B": 14, "C": 16, "D": 14}}},
        creator="Purchasing")
    write_text(os.path.join(ws, "note_from_rosa.txt"),
        "Hi,\n\nThe fall price sheets are in the price_sheets folder. Before I load them into the ordering system I need prices.csv with one row "
        "for every item on the ordering guide:\n\n"
        "sku - the vendor SKU as on the guide\n"
        "vendor - the supplier's name as printed on its price sheet\n"
        "unit_price - what we pay per order unit (the unit on the guide) when we order our usual quantity\n"
        "order_total - usual quantity times unit_price\n"
        "next_break_qty - the order quantity at which the next cheaper price starts, 0 if we already get the best price\n"
        "effective_date - the date that price takes effect, YYYY-MM-DD\n\n"
        "Current prices only, please.\n\nRosa\n")

    header = ["sku", "vendor", "unit_price", "order_total", "next_break_qty", "effective_date"]
    rows = [[it["sku"], it["vendor"], f"{it['unit_price']:.2f}", f"{it['total']:.2f}", it["next_break"], it["effective"].isoformat()] for it in d["items"]]
    write_csv(os.path.join(ref, "prices.csv"), header, rows)
    write_csv(os.path.join(sol, "prices.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {"superseded_prices": {s: o for s, _, _, o in d["pps"]}})
    write_task_yaml(HERE, {
        "id": "vendor-price-sheets", "track": "desk", "category": "extraction",
        "title": "Load the fall supplier price sheets for the ordering guide",
        "ask": "The suppliers sent their fall price sheets. Get the prices for everything on our ordering guide into prices.csv so Rosa can load them - her note says what she needs.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "Pacific Packaging's superseded March list sits in the folder as PPS_pricelist_FINAL.pdf with lower prices and 10-49 / 50+ breaks; the October list says it supersedes all earlier lists (checks: unit price at our order quantity; next price break)",
            "the mill quotes flour per hundredweight with a per-cwt volume allowance; a 50 lb bag is half a cwt after the allowance, and the rye comes in 25 lb bags (check: unit price at our order quantity)",
            "the dairy sheet prints list prices only; the 5% (24-71) and 8% (72+) quantity discounts are in a footnote under the table (checks: unit price at our order quantity; order total)",
            "the 12in cake boxes are ordered 10 cases at a time, exactly on the 10-24 break, and items already on the top tier carry 0 as the next break (check: next price break)",
            "the dairy's butter lines are market priced and take effect 10/01, while the rest of the sheet takes effect 10/05; the mill's date is in its covering prose (check: effective dates)",
            "the coffee roaster's list is an image-only fax (checks: one row per item; vendor names)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "prices.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per item", "path": "prices.csv", "column": "sku", "ref": "prices.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "prices.csv", "equals_ref": "prices.csv"},
            {"type": "csv_values_match", "name": "vendor names", "path": "prices.csv", "ref": "prices.csv", "key": "sku", "columns": ["vendor"],
             "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": ["NJ-01"]},
            {"type": "csv_values_match", "name": "unit price at our order quantity", "path": "prices.csv", "ref": "prices.csv", "key": "sku",
             "columns": ["unit_price"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": ["PPS-4410", "CMG-101", "CMG-230", "BD-3104", "BD-2215", "NJ-01"]},
            {"type": "csv_values_match", "name": "order total", "path": "prices.csv", "ref": "prices.csv", "key": "sku",
             "columns": ["order_total"], "numeric": True, "tolerance": 0.05, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "next price break", "path": "prices.csv", "ref": "prices.csv", "key": "sku",
             "columns": ["next_break_qty"], "numeric": True, "tolerance": 0.0, "min_accuracy": 1.0, "must_match_keys": ["PPS-4410", "PPS-4412", "PPS-7708", "BD-3104"]},
            {"type": "csv_values_match", "name": "effective dates", "path": "prices.csv", "ref": "prices.csv", "key": "sku",
             "columns": ["effective_date"], "min_accuracy": 1.0, "must_match_keys": ["BD-2210", "BD-2215", "BD-4001", "CMG-104"]},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
