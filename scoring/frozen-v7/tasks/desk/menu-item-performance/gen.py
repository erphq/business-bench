#!/usr/bin/env python3
"""menu-item-performance: a cafe's August POS item export -> menu items ranked by quantity and by margin.

    python gen.py [--seed N] [--naive DIR]

Business: Juniper Street Cafe exports item-level sales from its POS. The owner wants every menu item with quantity,
net sales, food cost and margin, ranked both ways, using the recipe cost sheet.

Traps (each caught by a check, see task.yaml):
  * modifiers ("+ Oat milk", "+ Add bacon") are separate lines with their own price; they are not menu items, and
    their price and cost belong to the item they were added to                (checks: Latte margin; Breakfast Sandwich margin)
  * comped items print a full gross price and a discount to zero; they count in quantity and cost but earn nothing,
    while voided lines were never made and count nowhere                      (checks: Cold Brew quantity; Breakfast Sandwich margin)
  * Avocado Toast was renamed Smashed Avocado Toast on 15 August; both names are in the export, only the new one in
    the cost sheet                                                            (check: Smashed Avocado Toast quantity)
  * staff meals carry a 50% discount; sales are the net price, not the gross  (check: total margin)
  * July's export sits in the folder                                          (check: total margin)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))


# name, menu group, price, plate cost, weight
MENU = [("Drip Coffee", "Coffee & Tea", 3.00, 0.45, 14), ("Latte", "Coffee & Tea", 5.25, 1.10, 12), ("Cappuccino", "Coffee & Tea", 4.75, 0.95, 7),
        ("Cold Brew", "Coffee & Tea", 4.50, 0.70, 8), ("Chai Tea", "Coffee & Tea", 4.75, 0.90, 5),
        ("Breakfast Sandwich", "Breakfast", 9.50, 3.10, 9), ("Smashed Avocado Toast", "Breakfast", 11.00, 3.60, 7), ("Oatmeal Bowl", "Breakfast", 7.50, 1.60, 4),
        ("Turkey Club", "Lunch", 13.50, 4.80, 6), ("Soup of the Day", "Lunch", 7.00, 2.00, 5), ("Greek Salad", "Lunch", 12.00, 3.90, 4),
        ("Croissant", "Bakery", 3.75, 1.05, 7), ("Blueberry Muffin", "Bakery", 3.50, 0.85, 6), ("Chocolate Chip Cookie", "Bakery", 2.75, 0.60, 6)]
OLD_NAME, NEW_NAME, RENAME_DAY = "Avocado Toast", "Smashed Avocado Toast", date(2026, 8, 15)
# modifier, price, cost, parents, probability per parent line
MODS = [("Oat milk", 0.75, 0.30, ("Latte", "Cappuccino", "Cold Brew"), 0.28), ("Extra shot", 1.00, 0.35, ("Latte", "Cappuccino"), 0.18),
        ("Vanilla syrup", 0.60, 0.12, ("Latte", "Cold Brew"), 0.15), ("Add bacon", 2.50, 1.05, ("Breakfast Sandwich", "Turkey Club"), 0.35),
        ("Add egg", 1.50, 0.40, ("Breakfast Sandwich", "Smashed Avocado Toast"), 0.22), ("Add avocado", 2.00, 0.95, ("Breakfast Sandwich", "Greek Salad"), 0.16),
        ("Gluten-free bread", 1.50, 0.70, ("Smashed Avocado Toast", "Turkey Club"), 0.10), ("No onions", 0.00, 0.00, ("Turkey Club", "Greek Salad"), 0.12)]
SERVERS = ["Kai", "Maribel", "Theo", "Ines", "Rashid"]
PINNED_QTY = ["Smashed Avocado Toast", "Cold Brew"]
PINNED_MARGIN = ["Latte", "Breakfast Sandwich"]


def gen_month(r, y: int, m: int, ndays: int, check0: int) -> list[dict]:
    names = [x[0] for x in MENU]; weights = [x[4] for x in MENU]
    price = {x[0]: x[2] for x in MENU}
    lines = []; chk = check0
    for dd in range(1, ndays + 1):
        day = date(y, m, dd)
        for _ in range(r.randint(38, 52)):
            chk += 1
            t = datetime(y, m, dd, 7, 0) + timedelta(minutes=r.randint(0, 8 * 60))
            server = r.choice(SERVERS)
            staff = r.random() < 0.04
            comp_check = r.random() < 0.02
            for _ in range(r.choice([1, 1, 2, 2, 3])):
                nm = r.choices(names, weights)[0]
                shown = (OLD_NAME if day < RENAME_DAY else NEW_NAME) if nm == NEW_NAME else nm
                comp = comp_check or r.random() < 0.012
                void = (not comp) and r.random() < 0.015
                disc = "Comp - manager" if comp else ("Staff meal 50%" if staff else "")
                base = {"check": chk, "time": t, "server": server, "item": nm, "shown": shown, "void": void, "comp": comp, "staff": staff, "disc": disc}
                lines.append({**base, "kind": "item", "name": shown, "group": next(x[1] for x in MENU if x[0] == nm), "parent": "", "gross": price[nm]})
                for mod, mp, mc, parents, p in MODS:
                    if nm in parents and r.random() < p:
                        lines.append({**base, "kind": "mod", "name": f"+ {mod}", "group": "Modifiers", "parent": shown, "gross": mp, "mod": mod})
    for x in lines:
        x["discount"] = x["gross"] if (x["comp"] and not x["void"]) else (round(x["gross"] * 0.5, 2) if x["staff"] and not x["void"] else 0.0)
        x["net"] = 0.0 if x["void"] else round(x["gross"] - x["discount"], 2)
    return lines


def aggregate(lines, *, roll_mods=True, count_voids=False, drop_zero=False, merge_rename=True, use_gross=False):
    cost = {x[0]: x[3] for x in MENU}; mcost = {x[0]: x[2] for x in MODS}
    out = {}
    for x in lines:
        if x["void"] and not count_voids:
            continue
        if drop_zero and x["net"] == 0 and x["gross"] > 0:
            continue
        key = x["item"] if merge_rename else x["shown"]
        if x["kind"] == "mod" and not roll_mods:
            continue
        a = out.setdefault(key, {"qty": 0, "sales": 0.0, "cost": 0.0})
        sale = x["gross"] if use_gross else x["net"]
        if x["kind"] == "item":
            a["qty"] += 1; a["cost"] += cost[x["item"]]
        else:
            a["cost"] += mcost[x["mod"]]
        a["sales"] += sale
    for a in out.values():
        a["sales"] = round(a["sales"], 2); a["cost"] = round(a["cost"], 2); a["margin"] = round(a["sales"] - a["cost"], 2)
    return out


def build(seed: int) -> dict:
    r = rng(seed)
    aug = gen_month(r, 2026, 8, 31, 40210)
    jul = gen_month(r, 2026, 7, 31, 37100)
    truth = aggregate(aug)
    naive = {"no_mods": aggregate(aug, roll_mods=False), "count_voids": aggregate(aug, count_voids=True), "drop_comps": aggregate(aug, drop_zero=True),
             "split_rename": aggregate(aug, merge_rename=False), "gross": aggregate(aug, use_gross=True)}
    total_margin = round(sum(a["margin"] for a in truth.values()), 2)
    return {"aug": aug, "jul": jul, "truth": truth, "naive": naive, "total_margin": total_margin}


def ranks(truth: dict, field: str) -> dict:
    order = sorted(truth, key=lambda k: (-truth[k][field], k))
    return {k: i + 1 for i, k in enumerate(order)}


def acceptable(d: dict) -> bool:
    t, n = d["truth"], d["naive"]
    rq, rm = ranks(t, "qty"), ranks(t, "margin")
    if len({t[k]["qty"] for k in t}) != len(t) or len({t[k]["margin"] for k in t}) != len(t):
        return False
    for k in PINNED_QTY + PINNED_MARGIN:
        f = "qty" if k in PINNED_QTY else "margin"
        v = t[k][f]
        row = [t[k][g] for g in ("qty", "sales", "cost", "margin") if g != f] + [rq[k], rm[k], round(t[k]["margin"] / t[k]["sales"], 4)]
        if any(abs(o - v) <= max(0.01 * abs(v), 1) for o in row):
            return False
    moved = lambda var, k, f, tol: abs(n[var].get(k, {f: 0})[f] - t[k][f]) > tol * abs(t[k][f])
    if not (moved("no_mods", "Latte", "margin", 0.02) and moved("no_mods", "Breakfast Sandwich", "margin", 0.02)):
        return False
    if not (moved("count_voids", "Cold Brew", "qty", 0.004) and moved("drop_comps", "Cold Brew", "qty", 0.004)):
        return False
    if not moved("drop_comps", "Breakfast Sandwich", "margin", 0.01):
        return False
    if not moved("split_rename", NEW_NAME, "qty", 0.02):
        return False
    tm = d["total_margin"]
    if abs(sum(a["margin"] for a in n["gross"].values()) - tm) <= 0.01 * tm:
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    hdr = ["Check #", "Opened", "Server", "Menu Group", "Item", "Parent Item", "Qty", "Gross Price", "Discount", "Discount Reason", "Net Price", "Voided"]

    def rows(lines):
        return [[x["check"], x["time"].strftime("%m/%d/%Y %I:%M %p"), x["server"], x["group"], x["name"], x["parent"], 1, f"{x['gross']:.2f}",
                 f"{x['discount']:.2f}", x["disc"] if not x["void"] else "", f"{x['net']:.2f}", "Yes" if x["void"] else "No"] for x in lines]
    write_csv(os.path.join(ws, "pos_item_details_2026-08.csv"), hdr, rows(d["aug"]))
    write_csv(os.path.join(ws, "pos_item_details_2026-07.csv"), hdr, rows(d["jul"]))
    write_xlsx(os.path.join(ws, "recipe_costs.xlsx"), {
        "Menu items": {"merged_title": "Plate costs - updated 15 Aug 2026", "header": ["Item", "Menu group", "Menu price", "Plate cost"],
                       "rows": [[x[0], x[1], x[2], x[3]] for x in MENU], "number_formats": {"C": "0.00", "D": "0.00"}, "widths": {"A": 24, "B": 16}},
        "Modifiers": {"header": ["Modifier", "Charge", "Cost"], "rows": [[m[0], m[1], m[2]] for m in MODS], "widths": {"A": 20}}}, creator="Kitchen")
    write_text(os.path.join(ws, "note_from_marcus.txt"),
               "Menu review for August\n\n"
               "I want to see every menu item for August with how many we sold, what it brought in, what it cost us, and the margin in "
               "dollars - ranked by how many we sold and ranked by margin, so I can see what to push and what to cut.\n\n"
               "How to read the POS export:\n"
               "- Modifiers print as their own lines (the ones starting with +). They are not menu items. What we charge for them and "
               "what they cost belong to the item they were added to - an oat milk latte is a latte.\n"
               "- Sales are what the customer actually paid, the Net Price. Staff meals are half price.\n"
               "- Comps are on the house: the food still went out, so count the item and its cost, but it earned nothing.\n"
               "- Voided lines were rung in by mistake and never made. Ignore them completely.\n"
               f"- We renamed {OLD_NAME} to {NEW_NAME} on August 15 - same dish. Report it once under the new name; the cost sheet "
               "only has the new name.\n\n"
               "Plate costs are in the recipe sheet Rosa updated.\n\n- Marcus\n")
    t = d["truth"]; rq, rm = ranks(t, "qty"), ranks(t, "margin")
    order = sorted(t, key=lambda k: rm[k])
    write_csv(os.path.join(ref, "menu_performance.csv"), ["item", "quantity", "net_sales", "food_cost", "margin", "rank_quantity", "rank_margin"],
              [[k, t[k]["qty"], f"{t[k]['sales']:.2f}", f"{t[k]['cost']:.2f}", f"{t[k]['margin']:.2f}", rq[k], rm[k]] for k in order])
    write_json(os.path.join(ref, "notes.json"), {"total_margin": d["total_margin"], "naive": {v: {k: a for k, a in n.items() if k in PINNED_QTY + PINNED_MARGIN + [OLD_NAME]}
                                                                                          for v, n in d["naive"].items()},
                                                  "voids": sum(1 for x in d["aug"] if x["void"] and x["kind"] == "item"),
                                                  "comps": sum(1 for x in d["aug"] if x["comp"] and x["kind"] == "item")})
    rows_ = []
    for i, k in enumerate(order, start=2):
        rows_.append([k, next(x[1] for x in MENU if x[0] == k), t[k]["qty"], t[k]["sales"], t[k]["cost"], f"=ROUND(D{i}-E{i},2)",
                      f"=IF(D{i}=0,0,ROUND(F{i}/D{i},4))", rq[k], rm[k]])
    n = len(order) + 1
    rows_.append(["Total", "", f"=SUM(C2:C{n})", f"=SUM(D2:D{n})", f"=SUM(E2:E{n})", f"=SUM(F2:F{n})", f"=IF(D{n + 1}=0,0,ROUND(F{n + 1}/D{n + 1},4))", "", ""])
    rows_.append([])
    rows_.append(["Modifier charges and costs are included in their item. Comps count in quantity and cost with no sales; voids are excluded."])
    write_xlsx(os.path.join(sol, "menu_performance.xlsx"), {"August 2026": {
        "header": ["Item", "Menu group", "Quantity sold", "Net sales", "Food cost", "Margin $", "Margin %", "Rank by quantity", "Rank by margin"],
        "rows": rows_, "number_formats": {"D": "#,##0.00", "E": "#,##0.00", "G": "0.0%"}, "widths": {"A": 24, "B": 14}}}, creator="reference")
    write_task_yaml(HERE, {
        "id": "menu-item-performance", "track": "desk", "category": "reports",
        "title": "August menu items ranked by sales and margin",
        "ask": ("I'm redoing the menu. Using the August POS export and Rosa's cost sheet, show me every item ranked by how many we sold and by "
                "margin - my note has how to read the export. Save it as menu_performance.xlsx.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "modifiers (\"+ Oat milk\", \"+ Add bacon\") are separate lines with their own price and a Parent Item; they are not menu items "
            "and their charge and cost roll into the parent, so dropping or ranking them separately moves the parent's margin "
            "(checks: Latte margin; Breakfast Sandwich margin)",
            f"{sum(1 for x in d['aug'] if x['comp'] and x['kind'] == 'item')} comped items show a full discount to a zero net price and still "
            f"count in quantity and cost, while {sum(1 for x in d['aug'] if x['void'] and x['kind'] == 'item')} voided items were never made; "
            "counting every line or dropping every zero line both miss (checks: Cold Brew quantity; Breakfast Sandwich margin)",
            f"{OLD_NAME} became {NEW_NAME} on 15 August; both names are in the export and only the new one is in the cost sheet "
            f"(check: {NEW_NAME} quantity)",
            "staff meals are half price, so the Gross Price column overstates sales; sales are the Net Price (check: total margin)",
            "July's POS export sits in the folder with the same columns (check: total margin)",
        ],
        "checks": [
            {"type": "file_exists", "name": "menu_performance.xlsx exists", "path": "menu_performance.xlsx"},
            {"type": "xlsx_no_errors", "name": "no formula errors", "path": "menu_performance.xlsx"},
            {"type": "xlsx_value_present", "name": f"{NEW_NAME} quantity", "path": "menu_performance.xlsx", "expected": t[NEW_NAME]["qty"],
             "rel_tol": cent_tol(t[NEW_NAME]["qty"], 0.001), "near_text": "smashed avocado"},
            {"type": "xlsx_value_present", "name": "Cold Brew quantity", "path": "menu_performance.xlsx", "expected": t["Cold Brew"]["qty"],
             "rel_tol": cent_tol(t["Cold Brew"]["qty"], 0.001), "near_text": "cold brew"},
            {"type": "xlsx_value_present", "name": "Latte margin", "path": "menu_performance.xlsx", "expected": t["Latte"]["margin"],
             "rel_tol": cent_tol(t["Latte"]["margin"], 0.004), "near_text": "latte"},
            {"type": "xlsx_value_present", "name": "Breakfast Sandwich margin", "path": "menu_performance.xlsx", "expected": t["Breakfast Sandwich"]["margin"],
             "rel_tol": cent_tol(t["Breakfast Sandwich"]["margin"], 0.004), "near_text": "breakfast sandwich"},
            {"type": "xlsx_value_present", "name": "total margin", "path": "menu_performance.xlsx", "expected": d["total_margin"],
             "rel_tol": cent_tol(d["total_margin"], 0.004), "near_text": "total"},
        ],
    })
    print(f"seed={seed} aug_lines={len(d['aug'])} jul_lines={len(d['jul'])} total_margin={d['total_margin']}")
    for k in PINNED_QTY + PINNED_MARGIN:
        print(f"  {k}: {t[k]} naive=" + ", ".join(f"{v}:{d['naive'][v].get(k, {}).get('qty')}/{d['naive'][v].get(k, {}).get('margin')}" for v in d["naive"]))


def write_naive(d: dict, out: str) -> None:
    """The obvious pivot: every line of the export grouped by Item name as printed (modifiers become their own rows,
    both toast names stay apart), quantity = count of lines, sales = Net Price, cost looked up by name (0 if missing)."""
    os.makedirs(out, exist_ok=True)
    cost = {x[0]: x[3] for x in MENU}
    agg = {}
    for x in d["aug"]:
        a = agg.setdefault(x["name"], [0, 0.0, 0.0])
        a[0] += 1; a[1] += x["net"]; a[2] += cost.get(x["name"], 0.0)
    rows = [[k, v[0], round(v[1], 2), round(v[2], 2), round(v[1] - v[2], 2)] for k, v in sorted(agg.items(), key=lambda kv: -kv[1][0])]
    rows.append(["Total", "", "", "", round(sum(v[1] - v[2] for v in agg.values()), 2)])
    write_xlsx(os.path.join(out, "menu_performance.xlsx"), {"Items": {"header": ["Item", "Qty", "Sales", "Cost", "Margin"], "rows": rows}}, creator="naive")


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
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
