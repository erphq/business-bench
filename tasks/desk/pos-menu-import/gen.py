#!/usr/bin/env python3
"""pos-menu-import: a boba shop's fall menu workbook turned into the new POS's menu import with modifier groups.

    python gen.py [--seed N] [--naive DIR]

Business: Tidewater Boba (two counters, one kitchen) is moving to the TillTap POS. The manager keeps the menu in a
workbook: a Menu sheet with category headings and an 86 column, and a Modifiers sheet where each group's code and
pick rule sit on its first row only. TillTap imports one CSV where items, modifier groups and modifiers are all rows.

Traps (each caught by a check, see task.yaml):
  * modifier groups and their options are rows of their own; each option needs its group's code as Parent Code,
    written only on the group's first row in the workbook                     (check: record type, name, parent and category)
  * pick rules ("Pick 1", "Up to 3", "Optional") become Min/Max; items list their group codes, not names
                                                                               (check: min, max and group codes)
  * prices are "$5.25", "5.5", "+$0.75", "+.60", "free"; TillTap wants plain numbers (check: prices as plain numbers)
  * 86'd items and 86'd options stay out, and so does the Taro Add-ins group, which only the 86'd taro milk tea uses
                                                                               (checks: one row per item, group and modifier; row count)
  * category headings are plural section rows ("MILK TEAS"); TillTap's categories are singular (check: record type, name, parent and category)
"""
from __future__ import annotations
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["Record Type", "Code", "Name", "Parent Code", "Category", "Price", "Min Select", "Max Select", "Modifier Groups"]
SECTIONS = [("MILK TEAS", "Milk Tea"), ("FRUIT TEAS", "Fruit Tea"), ("SLUSHES", "Slush"), ("SNACKS", "Snacks")]
# plu, name, base price, group names
ITEMS = {
    "MILK TEAS": [("T101", "Classic Black Milk Tea", 5.25, ["Size", "Sweetness", "Ice", "Toppings"]),
                  ("T102", "Jasmine Green Milk Tea", 5.25, ["Size", "Sweetness", "Ice", "Toppings"]),
                  ("T103", "Brown Sugar Boba Milk", 6.25, ["Size", "Ice", "Toppings"]),
                  ("T104", "Taro Milk Tea", 5.75, ["Size", "Sweetness", "Ice", "Taro Add-ins"]),
                  ("T105", "Thai Milk Tea", 5.50, ["Size", "Sweetness", "Ice", "Toppings"]),
                  ("T106", "Matcha Latte", 5.95, ["Size", "Sweetness", "Ice", "Milk Swap", "Toppings"]),
                  ("T107", "Hojicha Latte", 5.95, ["Size", "Sweetness", "Milk Swap", "Ice"]),
                  ("T108", "Roasted Oolong Milk Tea", 5.25, ["Size", "Sweetness", "Ice", "Toppings"])],
    "FRUIT TEAS": [("F201", "Passion Fruit Green Tea", 5.00, ["Size", "Sweetness", "Ice", "Toppings"]),
                   ("F202", "Mango Jasmine Tea", 5.00, ["Size", "Sweetness", "Ice", "Toppings"]),
                   ("F203", "Lychee Oolong", 5.25, ["Size", "Sweetness", "Ice", "Toppings"]),
                   ("F204", "Strawberry Hibiscus", 5.25, ["Size", "Sweetness", "Ice"]),
                   ("F205", "Peach Black Tea", 5.00, ["Size", "Sweetness", "Ice", "Toppings"])],
    "SLUSHES": [("S301", "Mango Slush", 6.00, ["Toppings"]), ("S302", "Watermelon Slush", 6.00, ["Toppings"]),
                ("S303", "Coconut Slush", 6.25, ["Toppings"])],
    "SNACKS": [("K401", "Popcorn Chicken", 7.50, ["Sauce"]), ("K402", "Sweet Potato Fries", 5.50, ["Sauce"]),
               ("K403", "Egg Waffle", 6.00, ["Waffle Drizzle"]), ("K404", "Mochi Donut", 3.25, [])],
}
# code, name, rule text, (min, max), options [(code, name, upcharge)]
GROUPS = [
    ("MG-SIZE", "Size", "Pick 1", (1, 1), [("SZ-REG", "Regular", 0.0), ("SZ-LG", "Large", 1.00)]),
    ("MG-SWEET", "Sweetness", "Pick 1", (1, 1), [("SW-0", "0% sweet", 0.0), ("SW-25", "25% sweet", 0.0), ("SW-50", "50% sweet", 0.0),
                                                  ("SW-75", "75% sweet", 0.0), ("SW-100", "100% sweet", 0.0)]),
    ("MG-ICE", "Ice", "Pick 1", (1, 1), [("ICE-NO", "No ice", 0.0), ("ICE-LESS", "Less ice", 0.0), ("ICE-REG", "Regular ice", 0.0),
                                          ("ICE-HOT", "Hot", 0.0)]),
    ("MG-TOP", "Toppings", "Up to 3", (0, 3), [("TP-PEARL", "Tapioca pearls", 0.75), ("TP-CRYS", "Crystal boba", 0.75),
                                                ("TP-LYCH", "Lychee jelly", 0.60), ("TP-PUD", "Egg pudding", 0.85),
                                                ("TP-RBEAN", "Red bean", 0.75), ("TP-FOAM", "Cheese foam", 1.25),
                                                ("TP-POPMG", "Popping mango", 0.75)]),
    ("MG-MILK", "Milk Swap", "Optional", (0, 1), [("MK-OAT", "Oat milk", 0.70), ("MK-ALM", "Almond milk", 0.70),
                                                   ("MK-LF", "Lactose-free milk", 0.50)]),
    ("MG-TARO", "Taro Add-ins", "Optional", (0, 1), [("TA-PASTE", "Taro paste", 0.95), ("TA-BALL", "Taro balls", 0.95)]),
    ("MG-SAUCE", "Sauce", "Up to 2", (0, 2), [("SC-MAYO", "Spicy mayo", 0.0), ("SC-PLUM", "Plum powder", 0.50),
                                               ("SC-CHILI", "Sweet chili", 0.0)]),
    ("MG-DRIZ", "Waffle Drizzle", "Optional", (0, 1), [("DZ-NUT", "Nutella", 1.00), ("DZ-COND", "Condensed milk", 0.50)]),
]
GROUP_CODE = {g[1]: g[0] for g in GROUPS}
STATUS_86 = ["86", "86'd", "86 - out til Oct", "86'd (supplier)"]


def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    for sec, cat in SECTIONS:
        for plu, name, price, groups in ITEMS[sec]:
            items.append({"plu": plu, "name": name, "price": round(price + r.choice([0, 0, 0.25, -0.25]), 2), "groups": groups,
                          "sec": sec, "cat": cat, "out": False})
    by = {x["plu"]: x for x in items}
    by["T104"]["out"] = True                                      # the only user of Taro Add-ins
    for plu in r.sample(["T107", "F204", "S302", "K404", "F203", "T108"], 3):
        by[plu]["out"] = True
    opts_out = {"TP-POPMG", r.choice(["MK-LF", "SC-PLUM", "DZ-COND", "TP-RBEAN"])}
    used = {g for x in items if not x["out"] for g in x["groups"]}
    groups = []
    for code_, name, rule, mm, opts in GROUPS:
        groups.append({"code": code_, "name": name, "rule": rule, "mm": mm, "out": name not in used,
                       "opts": [{"code": c, "name": n, "up": round(u, 2), "out": c in opts_out} for c, n, u in opts]})
    return {"items": items, "groups": groups}


def price_text(r, v: float, upcharge: bool) -> str:
    if upcharge:
        if v == 0:
            return r.choice(["free", "0", "", "-"])
        return r.choice([f"+${v:.2f}", f"+{v:.2f}".replace("+0.", "+."), f"${v:.2f}", f"+{v:g}"])
    return r.choice([f"${v:.2f}", f"{v:g}", f"{v:.2f}", f"$ {v:.2f}"])


def ref_rows(d: dict) -> list[list]:
    rows = []
    for x in d["items"]:
        if x["out"]:
            continue
        rows.append(["ITEM", x["plu"], x["name"], "", x["cat"], f"{x['price']:.2f}", "", "", "|".join(GROUP_CODE[g] for g in x["groups"])])
    for g in d["groups"]:
        if g["out"]:
            continue
        rows.append(["MODIFIER_GROUP", g["code"], g["name"], "", "", "", str(g["mm"][0]), str(g["mm"][1]), ""])
        for o in g["opts"]:
            if not o["out"]:
                rows.append(["MODIFIER", o["code"], o["name"], g["code"], "", f"{o['up']:.2f}", "", "", ""])
    return rows


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    r = rng(seed + 9)
    menu_rows, mod_rows = [], []
    for sec, _ in SECTIONS:
        menu_rows.append(["", sec])
        for x in [x for x in d["items"] if x["sec"] == sec]:
            status = r.choice(STATUS_86) if x["out"] else r.choice(["", "", "", "NEW"] if x["plu"] in ("T106", "S303") else ["", ""])
            x["price_text"] = price_text(r, x["price"], False)
            menu_rows.append([x["plu"], x["name"], x["price_text"], ", ".join(x["groups"]) if x["groups"] else "none", status])
    for g in d["groups"]:
        for k, o in enumerate(g["opts"]):
            o["price_text"] = price_text(r, o["up"], True)
            mod_rows.append([g["code"] if k == 0 else "", g["name"] if k == 0 else "", g["rule"] if k == 0 else "", o["code"], o["name"],
                             o["price_text"], r.choice(STATUS_86[:2]) if o["out"] else ""])
    if naive_dir:
        write_naive(d, menu_rows, mod_rows, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    write_xlsx(os.path.join(ws, "tidewater_fall_menu.xlsx"), {
        "Menu": {"merged_title": "Tidewater Boba - fall menu (both counters)", "header": ["PLU", "Item", "Price", "Modifier groups", "86"],
                 "rows": menu_rows, "widths": {"B": 28, "D": 40, "E": 18}},
        "Modifiers": {"header": ["Group code", "Group", "Rule", "Option code", "Option", "Upcharge", "86"], "rows": mod_rows,
                      "widths": {"B": 16, "E": 20}}}, creator="Tidewater Boba")
    write_csv(os.path.join(ws, "tilltap_menu_import_template.csv"), HEADER, [
        ["ITEM", "X100", "Example Drink", "", "Example Category", "4.50", "", "", "MG-EX1|MG-EX2"],
        ["MODIFIER_GROUP", "MG-EX1", "Example Size", "", "", "", "1", "1", ""],
        ["MODIFIER", "EX-L", "Example Large", "MG-EX1", "", "0.80", "", "", ""]])
    write_text(os.path.join(ws, "tilltap_setup_notes.txt"),
               "TillTap menu import - notes from the onboarding call (Kwame, 10 Sept)\n"
               "\n"
               "One file, TillTap's template columns in order, example rows deleted. Three kinds of row:\n"
               "  ITEM            one per menu item. Code = PLU. Category = TillTap category. Price = menu price.\n"
               "                  Modifier Groups = the group CODES the item uses, in the order the menu sheet lists\n"
               "                  them, separated by | (no spaces). Blank if the item has no modifiers.\n"
               "  MODIFIER_GROUP  one per group. Code = group code. Min Select / Max Select from the rule:\n"
               "                  Pick 1 = 1 and 1, Up to N = 0 and N, Optional = 0 and 1. Price blank.\n"
               "  MODIFIER        one per option. Code = option code. Parent Code = the group's code. Price = the\n"
               "                  upcharge (0.00 when it's free or blank). Category blank.\n"
               "\n"
               "Prices: numbers only - no $, no +, two decimals is fine (5.25, 0.75, 0.00).\n"
               "\n"
               "TillTap categories (spell them exactly like this): Milk Tea, Fruit Tea, Slush, Snacks.\n"
               "\n"
               "Anything 86'd on the fall sheet does NOT go in - items or options, however it's written in\n"
               "the 86 column. And don't load a modifier group that no item on the import uses, TillTap shows\n"
               "empty groups on the screen.\n")

    rows = ref_rows(d)
    write_csv(os.path.join(ref, "pos_menu.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "pos_menu.csv"), HEADER, rows)
    parent_pins = sorted({row[1] for row in rows if row[0] == "MODIFIER"} | {row[1] for row in rows if row[0] == "ITEM"})
    mm_pins = sorted({row[1] for row in rows if row[0] == "MODIFIER_GROUP"} | {x["plu"] for x in d["items"] if not x["out"] and len(x["groups"]) > 1})
    price_pins = sorted({o["code"] for g in d["groups"] if not g["out"] for o in g["opts"] if not o["out"] and not re.fullmatch(r"\d+(\.\d+)?", o["price_text"] or "x")}
                        | {x["plu"] for x in d["items"] if not x["out"] and not re.fullmatch(r"\d+(\.\d+)?", x["price_text"])})
    out_items = [x["plu"] for x in d["items"] if x["out"]]
    out_opts = [o["code"] for g in d["groups"] for o in g["opts"] if o["out"] and not g["out"]]
    write_json(os.path.join(ref, "notes.json"), {"rows": len(rows), "items_86": out_items, "options_86": out_opts,
                                                  "groups_unused": [g["code"] for g in d["groups"] if g["out"]], "price_pins": price_pins})
    write_task_yaml(HERE, {
        "id": "pos-menu-import", "track": "desk", "category": "reformatting",
        "title": "Load the fall menu into the new POS with modifiers",
        "ask": ("We go live on TillTap next week. Can you turn our fall menu workbook into their menu import, modifiers "
                "included, and save it as pos_menu.csv? Kwame's notes from the setup call and their template are in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "modifier groups and their options are rows of their own (MODIFIER_GROUP and MODIFIER); on the Modifiers sheet the "
            "group code, name and rule sit only on each group's first row, so options further down have a blank group and "
            "need it filled down into Parent Code (check: record type, name, parent and category)",
            "pick rules become Min/Max (Pick 1 = 1/1, Up to 3 = 0/3, Optional = 0/1), and each item's Modifier groups cell "
            "lists group NAMES that must become codes joined with | in the listed order "
            "(check: min, max and group codes)",
            "menu prices are '$5.25', '$ 5.00', '5.5' and upcharges '+$0.75', '+.6', 'free', '-' or blank; copying the "
            "text leaves $ and + in a numeric field and free options without 0.00 (check: prices as plain numbers)",
            f"{len(out_items)} items and {len(out_opts)} options are 86'd, written '86', \"86'd\", '86 - out til Oct' and "
            "\"86'd (supplier)\"; they stay out (checks: one row per item, group and modifier; row count)",
            "the Taro Add-ins group is not 86'd itself, but its only item (Taro Milk Tea) is, so the group and both of its "
            "options stay out as unused (checks: one row per item, group and modifier; row count)",
            "category comes from plural section rows (MILK TEAS, FRUIT TEAS, SLUSHES, SNACKS) above each block, not a column; "
            "TillTap's picklist is Milk Tea, Fruit Tea, Slush, Snacks (check: record type, name, parent and category)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "TillTap template columns, exact order", "path": "pos_menu.csv", "columns": HEADER, "exact": True},
            {"type": "csv_set_equal", "name": "one row per item, group and modifier", "path": "pos_menu.csv", "column": "Code",
             "ref": "pos_menu.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "pos_menu.csv", "equals_ref": "pos_menu.csv"},
            {"type": "csv_values_match", "name": "record type, name, parent and category", "path": "pos_menu.csv", "ref": "pos_menu.csv",
             "key": "Code", "columns": ["Record Type", "Name", "Parent Code", "Category"], "min_accuracy": 1.0, "must_match_keys": parent_pins},
            {"type": "csv_values_match", "name": "min, max and group codes", "path": "pos_menu.csv", "ref": "pos_menu.csv",
             "key": "Code", "columns": ["Min Select", "Max Select", "Modifier Groups"], "normalize": ["strip", "lower"],
             "min_accuracy": 1.0, "must_match_keys": mm_pins},
            {"type": "custom", "name": "prices as plain numbers", "module": "check.py"},
        ],
    })
    print(f"seed={seed} rows={len(rows)} items_86={out_items} options_86={out_opts} price_pins={len(price_pins)}")


def write_naive(d: dict, menu_rows: list, mod_rows: list, out: str) -> None:
    """The obvious copy: every row on both sheets, prices copied as written, the section heading as category,
    groups without fill-down, group names in Modifier Groups, no Min/Max."""
    os.makedirs(out, exist_ok=True)
    rows, sec = [], ""
    for row in menu_rows:
        if row[0] == "":
            sec = row[1]; continue
        rows.append(["ITEM", row[0], row[1], "", sec.title(), row[2], "", "", row[3].replace(", ", "|")])
    for row in mod_rows:
        if row[0]:
            rows.append(["MODIFIER_GROUP", row[0], row[1], "", "", "", "", "", ""])
        rows.append(["MODIFIER", row[3], row[4], row[0], "", row[5], "", "", ""])
    write_csv(os.path.join(out, "pos_menu.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
