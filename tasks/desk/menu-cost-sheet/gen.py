#!/usr/bin/env python3
"""menu-cost-sheet: plate cost and margin for every dish on a bistro's fall menu.

    python gen.py [--seed N] [--naive DIR]

Business: a 40-seat neighbourhood bistro. The chef keeps recipe cards in a workbook (one block per dish,
quantities as they go on the plate) and buys almost everything from one foodservice distributor, whose
price sheet quotes a price per pack. Nobody has ever costed the menu.

Traps (each caught by a check, see task.yaml):
  * the distributor prices per pack (5 KG, 3 L TIN, 500 G), recipes are in grams and millilitres
                                                                    (checks: every dish; Risotto plate cost)
  * brioche buns are priced per case of 12, the recipe uses one bun  (check: Smash Burger plate cost)
  * trim loss: recipe weights are plate weights, so cost divides by the yield, not adds the percent
                                                                    (check: Seared Salmon plate cost)
  * a few recipe lines are written in kg or L while the rest are g/ml (checks: Risotto and Salmon plate cost)
  * June's price sheet is still in the folder; September is current (check: Risotto plate cost)
  * the recipe card puts the dish name on the block's first row only; menu prices are text (check: every dish)
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# item key: (description on the price sheet, pack text, pack size in base units, base unit, base price)
ITEMS = {
    "salmon":    ("Salmon side, skin-on, fresh", "5 KG", 5000, "g", 148.00),
    "potato":    ("Russet potatoes", "20 KG SACK", 20000, "g", 31.00),
    "butter":    ("Butter, unsalted", "2 KG", 2000, "g", 19.40),
    "lemon":     ("Lemons", "EA", 1, "each", 0.55),
    "parsley":   ("Flat-leaf parsley", "1 KG", 1000, "g", 12.20),
    "beef":      ("Ground beef 80/20", "5 KG", 5000, "g", 58.00),
    "bun":       ("Brioche buns 4.5in", "CS/12", 12, "each", 10.20),
    "cheddar":   ("Cheddar, sliced", "2.5 KG", 2500, "g", 29.75),
    "onion":     ("Yellow onions", "10 KG SACK", 10000, "g", 13.00),
    "canola":    ("Canola oil", "15 L JUG", 15000, "ml", 38.00),
    "arborio":   ("Arborio rice", "5 KG", 5000, "g", 31.60),
    "mushroom":  ("Cremini mushrooms", "2.5 KG", 2500, "g", 22.40),
    "parmesan":  ("Parmigiano Reggiano", "1 KG", 1000, "g", 32.80),
    "stock":     ("Chicken stock, low sodium", "4 L", 4000, "ml", 14.40),
    "wine":      ("White wine, cooking", "4 L", 4000, "ml", 22.60),
    "linguine":  ("Linguine, dried", "5 KG", 5000, "g", 18.25),
    "thigh":     ("Chicken thighs, boneless", "5 KG", 5000, "g", 41.00),
    "cream":     ("Heavy cream 36%", "1 L", 1000, "ml", 6.20),
    "garlic":    ("Garlic, peeled", "1 KG", 1000, "g", 11.10),
    "flour":     ("All-purpose flour", "10 KG", 10000, "g", 14.30),
    "tomato":    ("San Marzano tomatoes", "2.5 KG TIN", 2500, "g", 12.60),
    "mozz":      ("Fresh mozzarella", "1 KG", 1000, "g", 17.90),
    "olive":     ("Extra virgin olive oil", "3 L TIN", 3000, "ml", 44.50),
    "basil":     ("Basil, fresh", "500 G", 500, "g", 14.20),
    "greens":    ("Mixed greens", "1.5 KG", 1500, "g", 16.80),
}
# what the recipe card calls the ingredient
CARD_NAME = {"salmon": "Salmon side", "potato": "Russet potatoes", "butter": "Butter", "lemon": "Lemon",
             "parsley": "Parsley", "beef": "Ground beef", "bun": "Brioche bun", "cheddar": "Cheddar slices",
             "onion": "Yellow onion", "canola": "Canola oil", "arborio": "Arborio rice", "mushroom": "Cremini mushrooms",
             "parmesan": "Parmesan", "stock": "Chicken stock", "wine": "White wine", "linguine": "Linguine",
             "thigh": "Chicken thighs", "cream": "Heavy cream", "garlic": "Garlic", "flour": "Flour",
             "tomato": "San Marzano tomatoes", "mozz": "Mozzarella", "olive": "Olive oil", "basil": "Basil",
             "greens": "Mixed greens"}
LOSS = {"salmon": 0.30, "potato": 0.15, "onion": 0.10, "parsley": 0.35}

# dish -> [(item, plate qty in base units, unit as written on the card)]; unit "kg"/"L" means the card shows qty/1000
DISHES = [
    ("Seared Salmon", [("salmon", 190, "g"), ("potato", 220, "kg"), ("butter", 20, "g"), ("lemon", 0.5, "each"), ("parsley", 6, "g")]),
    ("Smash Burger", [("beef", 170, "g"), ("bun", 1, "each"), ("cheddar", 40, "g"), ("onion", 30, "g"), ("potato", 250, "g"), ("canola", 40, "ml")]),
    ("Mushroom Risotto", [("arborio", 90, "g"), ("mushroom", 140, "g"), ("parmesan", 40, "g"), ("butter", 25, "g"), ("stock", 400, "L"),
                          ("onion", 50, "g"), ("wine", 60, "ml")]),
    ("Chicken Linguine", [("linguine", 120, "g"), ("thigh", 160, "g"), ("cream", 100, "ml"), ("garlic", 10, "g"), ("parmesan", 15, "g"), ("parsley", 5, "g")]),
    ("Margherita Flatbread", [("flour", 150, "g"), ("tomato", 90, "g"), ("mozz", 100, "g"), ("olive", 15, "ml"), ("basil", 4, "g")]),
    ("Crispy Chicken Sandwich", [("thigh", 180, "g"), ("bun", 1, "each"), ("flour", 40, "g"), ("canola", 60, "ml"), ("greens", 30, "g")]),
    ("Caesar Salad", [("greens", 120, "g"), ("parmesan", 20, "g"), ("lemon", 0.5, "each"), ("olive", 20, "ml"), ("garlic", 4, "g")]),
]
KEYWORD = {"Seared Salmon": "salmon", "Smash Burger": "burger", "Mushroom Risotto": "risotto", "Chicken Linguine": "linguine",
           "Margherita Flatbread": "flatbread", "Crispy Chicken Sandwich": "sandwich", "Caesar Salad": "caesar"}
MENU_PRICES = {"Seared Salmon": [26, 27, 28], "Smash Burger": [15, 16, 17], "Mushroom Risotto": [18, 19, 20],
               "Chicken Linguine": [19, 20, 21], "Margherita Flatbread": [13, 14, 15], "Crispy Chicken Sandwich": [14, 15, 16],
               "Caesar Salad": [11, 12, 13]}
SECTION = {"Seared Salmon": "Mains", "Smash Burger": "Handhelds", "Mushroom Risotto": "Mains", "Chicken Linguine": "Mains",
           "Margherita Flatbread": "Small plates", "Crispy Chicken Sandwich": "Handhelds", "Caesar Salad": "Small plates"}
UNIT_SPELL = {"g": ["g", "g", "gr", "G"], "ml": ["ml", "ml", "mL"], "each": ["each", "ea", "pc"], "kg": ["kg"], "L": ["L", "ltr"]}


def build(seed: int) -> dict:
    r = rng(seed)
    sept, june = {}, {}
    for k, (_, _, _, _, base) in ITEMS.items():
        p = round(base * r.uniform(0.9, 1.1), 2)
        sept[k] = p
        june[k] = round(p * r.uniform(0.86, 0.95), 2)
    dishes = []
    for name, lines in DISHES:
        out = []
        for item, qty, unit in lines:
            if ITEMS[item][3] != "each":
                q = max(5, int(round(qty * r.uniform(0.88, 1.12) / 5.0)) * 5)
            else:
                q = qty
            out.append({"item": item, "qty": q, "unit": unit, "k": r.random()})
        price = float(r.choice(MENU_PRICES[name])) + r.choice([0.0, 0.5])
        dishes.append({"name": name, "lines": out, "price": price})

    def cost(prices, d, case_as_each=False, loss_mode="divide", raw_kg=False):
        tot = 0.0
        for ln in d["lines"]:
            item = ln["item"]
            per = prices[item] / (1 if (case_as_each and item == "bun") else ITEMS[item][2])
            loss = LOSS.get(item, 0.0)
            if loss_mode == "divide":
                per = per / (1 - loss)
            elif loss_mode == "multiply":
                per = per * (1 + loss)
            q = ln["qty"] / 1000 if (raw_kg and ln["unit"] in ("kg", "L")) else ln["qty"]
            tot += q * per
        return tot

    for d in dishes:
        d["cost"] = round(cost(sept, d), 4)
        d["margin"] = round(d["price"] - d["cost"], 4)
        d["margin_pct"] = round(d["margin"] / d["price"], 6)
        d["variants"] = {
            "case_as_each": cost(sept, d, case_as_each=True),
            "no_loss": cost(sept, d, loss_mode="none"),
            "multiply_loss": cost(sept, d, loss_mode="multiply"),
            "raw_kg": cost(sept, d, raw_kg=True),
            "june": cost(june, d),
        }
    return {"sept": sept, "june": june, "dishes": dishes}


def acceptable(d: dict) -> bool:
    by = {x["name"]: x for x in d["dishes"]}

    def moves(dish, variant, rel=0.02):
        x = by[dish]
        return abs(x["variants"][variant] - x["cost"]) > rel * x["cost"]

    if not (moves("Smash Burger", "case_as_each") and moves("Seared Salmon", "no_loss")
            and moves("Seared Salmon", "multiply_loss") and moves("Seared Salmon", "raw_kg")
            and moves("Mushroom Risotto", "raw_kg") and moves("Mushroom Risotto", "june", 0.04)):
        return False
    for x in d["dishes"]:
        # a sensible food cost, and every figure on the dish's row distinct from the others
        if not (0.12 <= x["cost"] / x["price"] <= 0.45):
            return False
        vals = [x["cost"], x["price"], x["margin"], x["margin_pct"], 1 - x["margin_pct"], x["margin_pct"] * 100, (1 - x["margin_pct"]) * 100]
        for i, a in enumerate(vals):
            for b in vals[i + 1:]:
                if abs(a - b) <= 0.03 * max(abs(a), abs(b)):
                    return False
        # a misread cost must not land on another acceptable margin form
        for v in x["variants"].values():
            if abs(v - x["cost"]) > 0.005 * x["cost"] and abs((x["price"] - v) - x["cost"]) <= 0.02 * x["cost"]:
                return False
    return True


# --------------------------------------------------------------------------- deliverable

def workbook_sheets(d: dict, prices: dict, case_as_each=False, loss_mode="divide", raw_kg=False) -> dict:
    keys = list(ITEMS)
    price_rows = []
    for i, k in enumerate(keys, start=2):
        desc, pack, size, unit, _ = ITEMS[k]
        loss = LOSS.get(k, 0.0) if loss_mode != "none" else 0.0
        size_used = 1 if (case_as_each and k == "bun") else size
        usable = f"=F{i}*(1+G{i})" if loss_mode == "multiply" else f"=F{i}/(1-G{i})"
        # A card name, B description, C pack, D pack size, E base unit, F cost per unit, G loss, H usable cost, I pack price
        price_rows.append([CARD_NAME[k], desc, pack, size_used, unit, f"=I{i}/D{i}", loss, usable, prices[k]])
    n_items = len(keys) + 1
    line_rows = []
    li = 2
    for x in d["dishes"]:
        for ln in x["lines"]:
            written = ln["qty"] / 1000 if ln["unit"] in ("kg", "L") else ln["qty"]
            conv = f"=C{li}" if raw_kg else f'=IF(D{li}="kg",C{li}*1000,IF(D{li}="L",C{li}*1000,C{li}))'
            line_rows.append([x["name"], CARD_NAME[ln["item"]], written, ln["unit"], conv,
                              f"=VLOOKUP(B{li},Prices!$A$2:$H${n_items},8,FALSE)", f"=E{li}*F{li}"])
            li += 1
    n_lines = li - 1
    menu_rows = []
    for i, x in enumerate(d["dishes"], start=2):
        menu_rows.append([x["name"], f"=SUMIF(Lines!$A$2:$A${n_lines},A{i},Lines!$G$2:$G${n_lines})", x["price"],
                          f"=C{i}-B{i}", f"=ROUND(D{i}/C{i},4)", f"=ROUND(B{i}/C{i},4)"])
    return {
        "Menu": {"header": ["Dish", "Plate cost", "Menu price", "Gross margin", "Margin %", "Food cost %"], "rows": menu_rows,
                 "number_formats": {"B": "0.00", "C": "0.00", "D": "0.00", "E": "0.0%", "F": "0.0%"}, "widths": {"A": 26}},
        "Lines": {"header": ["Dish", "Ingredient", "Qty on card", "Unit", "Qty (g/ml/each)", "Usable cost per unit", "Line cost"],
                  "rows": line_rows, "widths": {"A": 26, "B": 22}},
        "Prices": {"header": ["Ingredient", "Harbor description", "Pack", "Pack size (g/ml/each)", "Unit", "Cost per unit",
                              "Trim loss", "Usable cost per unit", "Pack price (Sept)"], "rows": price_rows,
                   "widths": {"A": 20, "B": 30}},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        # the obvious reading: a pack price per each for the case, trim added as a percentage on top,
        # and the card's kg/L lines taken as grams and millilitres
        write_xlsx(os.path.join(naive_dir, "menu_costs.xlsx"),
                   workbook_sheets(d, d["sept"], case_as_each=True, loss_mode="multiply", raw_kg=True), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 77)

    # ---- recipe cards: one block per dish, dish name on the first row only ----
    card_rows = []
    for x in d["dishes"]:
        card_rows.append([x["name"], "", "", "", "serves 1"])
        for ln in x["lines"]:
            if ln["unit"] in ("kg", "L"):
                qty, unit = ln["qty"] / 1000, UNIT_SPELL[ln["unit"]][int(ln["k"] * len(UNIT_SPELL[ln["unit"]]))]
            else:
                qty, unit = ln["qty"], UNIT_SPELL[ln["unit"]][int(ln["k"] * len(UNIT_SPELL[ln["unit"]]))]
            note = {"salmon": "skin, pin bone, portion", "potato": "peeled", "onion": "diced", "parsley": "leaves only",
                    "garlic": "minced", "basil": "torn"}.get(ln["item"], "")
            card_rows.append(["", CARD_NAME[ln["item"]], qty, unit, note])
        card_rows.append(["", "", "", "", ""])
    menu_rows = []
    for x in d["dishes"]:
        p = x["price"]
        txt = f"${p:,.2f}" if r.random() < 0.6 else (f"{p:.2f}" if p != int(p) else f"{int(p)}")
        menu_rows.append([x["name"], txt, SECTION[x["name"]]])
    write_xlsx(os.path.join(ws, "recipe_cards_fall_2026.xlsx"), {
        "Recipe cards": {"merged_title": "Fall 2026 recipe cards - plate quantities", "header": ["Dish", "Ingredient", "Qty", "Unit", "Prep"],
                         "rows": card_rows, "widths": {"A": 26, "B": 24, "E": 26}},
        "Menu": {"header": ["Dish", "Menu price", "Section"], "rows": menu_rows, "widths": {"A": 26}},
    }, creator="Dana")

    def price_rows(prices, reorder_seed):
        rows = []
        for k, (desc, pack, _, _, _) in ITEMS.items():
            rows.append([f"{r.randint(100000, 999999)}", desc.upper() if r.random() < 0.3 else desc, pack, money_str(prices[k], 1)])
        rr = rng(reorder_seed)
        rr.shuffle(rows)
        return rows

    write_csv(os.path.join(ws, "harbor_price_sheet_2026-09.csv"), ["Item #", "Description", "Pack", "Price"], price_rows(d["sept"], seed + 1),
              preamble=["Harbor Foodservice - customer price list", "Account 44817 | prices effective 09/01/2026 | price is per pack"],
              bom=True, crlf=True)
    write_csv(os.path.join(ws, "harbor_price_sheet_2026-06.csv"), ["Item #", "Description", "Pack", "Price"], price_rows(d["june"], seed + 2),
              preamble=["Harbor Foodservice - customer price list", "Account 44817 | prices effective 06/01/2026 | price is per pack"],
              bom=True, crlf=True)
    loss_lines = "\n".join(f"  - {CARD_NAME[k]}: we lose about {int(v * 100)}%" for k, v in LOSS.items())
    write_text(os.path.join(ws, "note_from_dana.txt"),
               "Costing the fall menu\n"
               "\n"
               "The quantities on my cards are what ends up on the plate, not what we buy. Most things go on the\n"
               "plate the way they come in, but a few lose weight on the prep table first:\n"
               f"{loss_lines}\n"
               "\n"
               "So those cost more per plate than the price sheet suggests. Work it from what's left after trim:\n"
               "a kilo of salmon side only gives us 700 g we can serve, so a gram on the plate costs the kilo\n"
               "price divided by 700, not the kilo price plus 30%.\n"
               "\n"
               "Use Harbor's September sheet. The June one is still in the folder because I was comparing, but\n"
               "those prices are gone.\n"
               "\n"
               "Menu prices are on the second tab of my recipe workbook. I want to see what each plate costs us\n"
               "and what we keep out of the menu price.\n"
               "\n"
               "- Dana\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "dish_costs.csv"), ["dish", "plate_cost", "menu_price", "gross_margin", "margin_pct"],
              [[x["name"], f"{x['cost']:.4f}", f"{x['price']:.2f}", f"{x['margin']:.4f}", f"{x['margin_pct']:.6f}"] for x in d["dishes"]])
    write_json(os.path.join(ref, "notes.json"), {
        "dishes": {x["name"]: {"keyword": KEYWORD[x["name"]], "cost": round(x["cost"], 4), "price": x["price"],
                               "margin": round(x["margin"], 4), "margin_pct": x["margin_pct"]} for x in d["dishes"]},
        "sept_prices": d["sept"], "loss": LOSS})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "menu_costs.xlsx"), workbook_sheets(d, d["sept"]), creator="reference")

    by = {x["name"]: x for x in d["dishes"]}
    write_task_yaml(HERE, {
        "id": "menu-cost-sheet", "track": "desk", "category": "spreadsheet",
        "title": "Cost out the fall menu, plate by plate",
        "ask": ("Can you cost out every dish on the fall menu from Dana's recipe cards and the Harbor price sheet, so I can see what "
                "each plate costs us and what we keep? Save it as menu_costs.xlsx with the math as live formulas. Dana left a note "
                "about how the kitchen counts it.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "Harbor quotes one price per pack (5 KG, 20 KG SACK, 3 L TIN, 500 G) while the cards are in grams and millilitres, so "
            "every line needs the pack price divided by the pack size in the card's unit (checks: plate cost and margin, every dish; "
            "Mushroom Risotto plate cost)",
            "brioche buns are the one line priced per case (CS/12); taking the case price as the price of a bun adds most of a case "
            "to the burger and the chicken sandwich (check: Smash Burger plate cost)",
            "card weights are plate weights; salmon, potatoes, onions and parsley lose 30/15/10/35% on the prep table and Dana's "
            "note says to divide by what is left, so adding the percent on top undercosts the salmon (check: Seared Salmon plate cost)",
            "a few card lines are written in kg or L (the salmon plate's potatoes, the risotto's stock) among grams and millilitres; reading them as "
            "grams costs them at a thousandth (checks: Seared Salmon plate cost; Mushroom Risotto plate cost)",
            "June's price sheet sits beside September's with the same layout and lower prices; Dana's note says September is "
            "current (check: Mushroom Risotto plate cost)",
            "the recipe card names the dish only on the first row of each block and the menu tab holds prices as '$28.00' text; "
            "a flat read loses which dish a line belongs to (check: plate cost and margin, every dish)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "menu_costs.xlsx", "min_count": len(d["dishes"])},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "menu_costs.xlsx"},
            {"type": "xlsx_value_present", "name": "Smash Burger plate cost", "path": "menu_costs.xlsx",
             "expected": round(by["Smash Burger"]["cost"], 2), "rel_tol": 0.005, "near_text": "burger"},
            {"type": "xlsx_value_present", "name": "Seared Salmon plate cost", "path": "menu_costs.xlsx",
             "expected": round(by["Seared Salmon"]["cost"], 2), "rel_tol": 0.005, "near_text": "salmon"},
            {"type": "xlsx_value_present", "name": "Mushroom Risotto plate cost", "path": "menu_costs.xlsx",
             "expected": round(by["Mushroom Risotto"]["cost"], 2), "rel_tol": 0.005, "near_text": "risotto"},
            {"type": "custom", "name": "plate cost and margin, every dish", "module": "check.py"},
        ],
    })
    print(f"seed={seed}")
    for x in d["dishes"]:
        print(f"  {x['name']:24} cost={x['cost']:.2f} price={x['price']:.2f} margin={x['margin']:.2f} ({x['margin_pct']:.1%})")


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
