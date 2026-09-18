#!/usr/bin/env python3
"""supplier-catalog-imperial: a metric hardware price list turned into an inches-and-pounds catalog priced per piece.

    python gen.py [--seed N] [--naive DIR]

Business: Alder & Awl Woodworking Supply in Eugene, a US dealer for a German cabinet-hardware maker. The
supplier's 2026 dealer price list is in USD but metric, with lengths in mm, cm or m and weights in g or kg,
and prices that cover a piece, a pack or a hundred pieces. The owner's note sets the catalog's rounding rule.

Traps (each caught by a check, see task.yaml):
  * lengths and widths come in mm, cm and m, weights in g and kg, often mixed within a row (a 1 m dowel 8 mm
    wide)                                                (checks: length and width; weight per piece)
  * the Price per column says what the price covers: a piece, a PU (pack), 100 pieces or 1,000 pieces; price
    each divides accordingly                              (check: price each)
  * the rounding rule: lengths to the nearest sixteenth of an inch written as a decimal, weights to three
    decimals of a pound, prices to three decimals        (checks: length and width; weight per piece; price each)
  * discontinued articles are left out                    (checks: every current article; row count)
"""
from __future__ import annotations
import argparse
import os
import sys
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MM_PER_IN = Decimal("25.4")
G_PER_LB = Decimal("453.59237")
# family: (sku stem, description, [length mm options], [width mm], [weight g range], pack options, basis, price range for the basis)
FAMILIES = [
    ("4410", "Full-extension drawer slide, soft close, {l} mm", [300, 350, 400, 450, 500, 550], [45], (620, 1450), [10], "PU", (118, 212)),
    ("2210", "Concealed hinge 110 deg, clip-on, overlay", [113], [35], (92, 104), [50], "100 pcs", (188, 246)),
    ("2230", "Hinge mounting plate, 0 mm", [52], [37], (16, 21), [100], "100 pcs", (39, 58)),
    ("6105", "Shelf support pin 5 mm, nickel", [16], [5], (2, 2), [500], "1000 pcs", (16, 24)),
    ("7120", "Bar pull, brushed steel, CC {c} mm", [168, 200, 232, 360], [12], (85, 240), [1], "piece", (4.2, 11.8)),
    ("8008", "Beech dowel rod {w} mm", [1000], [8, 10, 12], (48, 110), [25], "PU", (19, 44)),
    ("9022", "Birch edge banding, pre-glued, roll", [50000], [22], (540, 580), [1], "piece", (21, 29)),
    ("5710", "Steel table leg, square", [710], [60], (3350, 3480), [4], "PU", (138, 176)),
    ("3430", "Chipboard screw 4.0 x 30, zinc", [30], [4], (1.9, 1.9), [500], "100 pcs", (2.35, 3.10)),
    ("3550", "Chipboard screw 5.0 x 50, zinc", [50], [5], (5.2, 5.2), [200], "100 pcs", (4.10, 5.40)),
    ("5025", "Leg leveler M8, 30 mm base", [25], [30], (21, 24), [20], "PU", (17, 26)),
    ("4250", "Lid stay, soft down", [250], [38], (132, 148), [1], "piece", (13.5, 18.9)),
    ("9119", "Aluminium T-track", [800, 1200], [19], (240, 370), [1], "piece", (16.5, 27.5)),
]


def q(x: Decimal, step: str) -> Decimal:
    return x.quantize(Decimal(step), rounding=ROUND_HALF_UP)


def sixteenth(mm: Decimal) -> Decimal:
    return (mm / MM_PER_IN * 16).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 16


def length_text(r, mm: int) -> str:
    opts = [f"{mm} mm"]
    if mm % 10 == 0:
        opts.append(f"{mm // 10} cm")
    if mm >= 100 and mm % 10 == 0:
        m = Decimal(mm) / 1000
        opts.append(f"{m.normalize():f} m")
    if mm >= 1000:
        opts = [o for o in opts if o.endswith(" m")] + [f"{mm} mm"]
    return r.choice(opts)


def weight_text(r, g: Decimal) -> str:
    if g >= 100 and r.random() < 0.55:
        return f"{(g / 1000).normalize():f} kg"
    return f"{g.normalize():f} g"


def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    for stem, desc, lengths, widths, (wlo, whi), packs, basis, (plo, phi) in FAMILIES:
        for li, L in enumerate(lengths):
            for wi, W in enumerate(widths):
                sku = f"NW-{stem}-{L if len(lengths) > 1 else W if len(widths) > 1 else '01'}"
                g = Decimal(str(round(r.uniform(wlo, whi), 1 if whi < 10 else 0)))
                if len(lengths) > 1 or len(widths) > 1:
                    g = Decimal(str(round(wlo + (whi - wlo) * ((li + wi) / max(1, len(lengths) + len(widths) - 2)) * r.uniform(0.95, 1.0), 0)))
                n_var = len(lengths) * len(widths)
                pos = (li * len(widths) + wi) / (n_var - 1) if n_var > 1 else r.random()
                price = Decimal(str(round((plo + (phi - plo) * pos) * r.uniform(0.97, 1.03), 2)))
                pack = r.choice(packs)
                per = {"piece": 1, "PU": pack, "100 pcs": 100, "1000 pcs": 1000}[basis]
                items.append({"sku": sku, "desc": desc.format(l=L, c=L - 40, w=W), "L": L, "W": W, "g": g, "pack": pack, "basis": basis,
                              "price": price, "per": per, "status": "", "Lt": length_text(r, L), "Wt": length_text(r, W),
                              "gt": weight_text(r, g)})
    # discontinued articles
    for it in r.sample([i for i in items if i["basis"] in ("PU", "piece")], 3):
        it["status"] = "discontinued"
    for it in r.sample([i for i in items if not i["status"]], 3):
        it["status"] = "new 2026"
    for it in items:
        it["L_in"] = sixteenth(Decimal(it["L"]))
        it["W_in"] = sixteenth(Decimal(it["W"]))
        it["lb"] = q(it["g"] / G_PER_LB, "0.001")
        it["each"] = q(it["price"] / it["per"], "0.001")
    return {"items": items}


def acceptable(d: dict) -> bool:
    live = [i for i in d["items"] if i["status"] != "discontinued"]
    for i in d["items"]:
        for mm in (i["L"], i["W"]):
            f = (Decimal(mm) / MM_PER_IN * 16) % 1
            if abs(f - Decimal("0.5")) < Decimal("0.002"):
                return False
        for x in (i["g"] / G_PER_LB * 1000, i["price"] / i["per"] * 1000):
            if abs(x % 1 - Decimal("0.5")) < Decimal("0.002"):
                return False
    # the units vary: at least three cm lengths, three m lengths, four kg weights among live items
    if sum(1 for i in live for t in (i["Lt"], i["Wt"]) if t.endswith(" cm")) < 3:
        return False
    if sum(1 for i in live for t in (i["Lt"], i["Wt"]) if t.endswith(" m")) < 3:
        return False
    if sum(1 for i in live if i["gt"].endswith("kg")) < 4:
        return False
    if not any(i["status"] == "discontinued" and i["basis"] == "PU" for i in d["items"]):
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["sku", "description", "length_in", "width_in", "weight_lb", "pack_qty", "price_each"]
    live = [i for i in d["items"] if i["status"] != "discontinued"]
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        rows = []
        for i in d["items"]:
            ln = float(i["Lt"].split()[0]) / 25.4
            wd = float(i["Wt"].split()[0]) / 25.4
            wt = float(i["gt"].split()[0]) / 453.59237
            rows.append([i["sku"], i["desc"], f"{ln:.2f}", f"{wd:.2f}", f"{wt:.3f}", i["pack"], f"{i['price']:.2f}"])
        write_csv(os.path.join(naive_dir, "catalog_us.csv"), header, rows)
        return
    ws, ref, sol = task_dirs(HERE)

    write_xlsx(os.path.join(ws, "nordwerk_dealer_pricelist_2026_USD.xlsx"), {"Preisliste 2026": {
        "merged_title": "NORDWERK Beschlag GmbH - Dealer price list 2026 - North America (USD, ex works)",
        "preamble": [["PU = packing unit. Prices valid 1 March 2026 until further notice."]],
        "header": ["Art.-Nr.", "Description", "Length", "Width", "Weight / piece", "PU", "Price USD", "Price per", "Status"],
        "rows": [[i["sku"], i["desc"], i["Lt"], i["Wt"], i["gt"], i["pack"], float(i["price"]), i["basis"], i["status"]] for i in d["items"]],
        "number_formats": {"G": "#,##0.00"}, "widths": {"A": 14, "B": 50, "C": 10, "D": 10, "E": 14, "F": 6, "G": 11, "H": 10, "I": 14}}},
        creator="Nordwerk Beschlag GmbH")
    old = [[f"NW-{s}", desc, len_, wid, wt, pk, pr] for s, desc, len_, wid, wt, pk, pr in [
        ("4410-450", "Full-extension drawer slide, soft close, 450 mm", "17.75", "1.75", "2.105", 10, "15.900"),
        ("2210-01", "Concealed hinge 110 deg, clip-on, overlay", "4.4375", "1.375", "0.214", 50, "1.980"),
        ("7120-200", "Bar pull, brushed steel, CC 160 mm", "7.875", "0.5", "0.278", 1, "6.400"),
        ("8008-10", "Beech dowel rod 10 mm", "39.375", "0.375", "0.165", 25, "1.240"),
        ("3430-01", "Chipboard screw 4.0 x 30, zinc", "1.1875", "0.1875", "0.004", 500, "0.026")]]
    write_csv(os.path.join(ws, "catalog_us_2025.csv"), header, old)
    write_text(os.path.join(ws, "note_from_josie.txt"),
               "Nordwerk 2026 prices into our catalog\n"
               "\n"
               "Nordwerk's 2026 dealer price list came in. It's in dollars but everything else is metric, and our\n"
               "catalog is inches and pounds and priced by the piece. Last year's file is in the folder so you can see\n"
               "the layout. Please make catalog_us.csv with sku (their Art.-Nr.), description, length_in, width_in,\n"
               "weight_lb, pack_qty and price_each.\n"
               "\n"
               "- 1 inch is exactly 25.4 mm and 1 pound is exactly 453.59237 g. Watch the units - they write mm, cm and\n"
               "  m, and g and kg, and not always the same way in one row.\n"
               "- Our rounding: lengths and widths to the nearest sixteenth of an inch, written as a decimal (17.6875,\n"
               "  not 17 11/16). Weights to three decimals of a pound. Prices to three decimals, since some hardware\n"
               "  sells for pennies apiece.\n"
               "- The weight on their list is already per piece.\n"
               "- price_each is what one piece costs. Their 'Price per' column says what the price is for: one piece, a\n"
               "  whole PU (pack), or 100 or 1000 pieces. pack_qty is the PU.\n"
               "- Leave out anything they've discontinued.\n"
               "\n"
               "Josie\n")

    ref_rows = [[i["sku"], i["desc"], f"{i['L_in']:f}".rstrip("0").rstrip("."), f"{i['W_in']:f}".rstrip("0").rstrip("."), f"{i['lb']:.3f}",
                 i["pack"], f"{i['each']:.3f}"] for i in live]
    write_csv(os.path.join(ref, "catalog_us.csv"), header, ref_rows)
    write_csv(os.path.join(sol, "catalog_us.csv"), header, ref_rows)
    must_price = [i["sku"] for i in live if i["basis"] != "piece"]
    ex_m = next(i for i in live if i["Lt"].endswith(" m") and i["Wt"].endswith(" mm"))
    ex_cm = next((i for i in live if " cm" in i["Lt"] + " " + i["Wt"] and i["gt"].endswith("kg")),
                 next(i for i in live if " cm" in i["Lt"] + " " + i["Wt"]))
    must_len = [i["sku"] for i in live if any(t.endswith((" cm", " m")) for t in (i["Lt"], i["Wt"]))]
    write_json(os.path.join(ref, "notes.json"), {"discontinued": [i["sku"] for i in d["items"] if i["status"] == "discontinued"],
                                                  "non_piece_prices": must_price, "cm_or_m_rows": must_len})
    write_task_yaml(HERE, {
        "id": "supplier-catalog-imperial", "track": "desk", "category": "spreadsheet",
        "title": "Metric supplier price list into our inch-and-pound catalog",
        "ask": ("Nordwerk sent their 2026 price list in metric. Turn it into our catalog format as catalog_us.csv - Josie's note "
                "has the details.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "lengths and widths are written in mm, cm or m and weights in g or kg, often mixed within one row "
            f"({ex_m['sku']} is '{ex_m['Lt']}' long and '{ex_m['Wt']}' wide, {ex_cm['sku']} is '{ex_cm['Lt']}' by '{ex_cm['Wt']}' "
            f"weighing '{ex_cm['gt']}'); reading every number as mm and grams shrinks those lengths and every kg weight "
            "(checks: length and width; weight per piece)",
            "the Price per column says what the price covers: a piece, the PU (10 slides, 25 dowels, 4 legs), 100 "
            "pieces (hinges, mounting plates and screws packed in 50, 100, 200 or 500), or 1,000 shelf pins; copying Price USD as the piece price or dividing "
            "every price by the PU is wrong (check: price each)",
            "the rounding rule: lengths and widths to the nearest sixteenth of an inch written as a decimal (1.75, "
            "17.6875), weights to three decimals of a pound and prices to three decimals; two-decimal or unrounded "
            "inches miss the length check, and two-decimal weights or prices miss theirs "
            "(checks: length and width; weight per piece; price each)",
            "three articles are marked discontinued and stay out, while 'new 2026' articles stay in "
            "(checks: every current article; row count)",
            "the price list has a merged title row and a note row above the header, and last year's catalog sits in "
            "the folder with the old prices (check: price each)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "catalog_us.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every current article", "path": "catalog_us.csv", "column": "sku",
             "ref": "catalog_us.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "catalog_us.csv", "equals_ref": "catalog_us.csv"},
            {"type": "csv_values_match", "name": "length and width", "path": "catalog_us.csv", "ref": "catalog_us.csv",
             "key": "sku", "columns": ["length_in", "width_in"], "numeric": True, "tolerance": 0.001, "min_accuracy": 1.0,
             "must_match_keys": must_len},
            {"type": "csv_values_match", "name": "weight per piece", "path": "catalog_us.csv", "ref": "catalog_us.csv",
             "key": "sku", "columns": ["weight_lb"], "numeric": True, "tolerance": 0.0006, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "price each", "path": "catalog_us.csv", "ref": "catalog_us.csv",
             "key": "sku", "columns": ["price_each"], "numeric": True, "tolerance": 0.0006, "min_accuracy": 1.0,
             "must_match_keys": must_price},
            {"type": "csv_values_match", "name": "pack quantity", "path": "catalog_us.csv", "ref": "catalog_us.csv",
             "key": "sku", "columns": ["pack_qty"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0},
        ],
    })
    print(f"seed={seed} items={len(d['items'])} live={len(live)}")
    for i in d["items"][:12]:
        print(" ", i["sku"], i["Lt"], i["Wt"], i["gt"], i["pack"], i["price"], i["basis"], "->", i["L_in"], i["W_in"], i["lb"], i["each"], i["status"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
