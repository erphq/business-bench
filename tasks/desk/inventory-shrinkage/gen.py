#!/usr/bin/env python3
"""inventory-shrinkage: net shrinkage at average cost per category from a Sunday-night count at a pet supply store.

    python gen.py [--seed N] [--naive DIR]

Business: an independent pet supply store that counts the floor once a year after close. The POS on-hand export
was pulled the next morning, after the store had opened, taken a delivery and made sales.

Traps (each caught by a check, see task.yaml):
  * shrink is valued at average cost, not retail                                        (checks: category values; total)
  * the export was run Monday 11:15 am: Monday sales, returns and the 9:30 delivery before it must be backed out,
    Sunday sales before 5 pm and Monday afternoon sales must not                          (checks: category values; total)
  * damaged stock pulled before the count but not yet written off comes out of expected and is reported as damage,
    not shrink; damage already written off is already out of the system                 (checks: damage value; category values)
  * shrink is net within a category: overages offset shortages                           (checks: category values; total)
  * a locked case was not counted (blank on the sheet), which is not a count of zero      (checks: Aquarium value; total)
  * the values must be live formulas                                                     (checks: live formulas; no error cells)
"""
from __future__ import annotations
import argparse
import math
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CUTOFF = datetime(2026, 8, 30, 17, 0)
EXPORT = datetime(2026, 8, 31, 11, 15)
CATS = {
    "Dog Food": [("Kibble Grain-Free Salmon 24lb", 41.80, 72.99), ("Kibble Lamb & Rice 30lb", 38.25, 64.99), ("Canned Beef Stew 13oz", 1.92, 3.49),
                 ("Senior Formula 15lb", 29.40, 52.99), ("Puppy Chicken 12lb", 22.15, 39.99), ("Raw Frozen Patties 6lb", 24.60, 44.99),
                 ("Limited Ingredient Duck 22lb", 46.10, 79.99), ("Canned Turkey Pate 13oz", 2.05, 3.79), ("Freeze-Dried Topper 8oz", 9.85, 18.99),
                 ("Weight Control 28lb", 35.70, 61.99), ("Large Breed Chicken 34lb", 44.35, 76.99)],
    "Cat Food": [("Indoor Adult 16lb", 27.90, 48.99), ("Canned Tuna Flakes 3oz", 0.74, 1.39), ("Kitten Chicken 7lb", 16.35, 29.99),
                 ("Grain-Free Whitefish 11lb", 25.20, 44.99), ("Pouch Variety 12pk", 7.80, 13.99), ("Hairball Formula 14lb", 24.45, 42.99),
                 ("Canned Salmon Pate 5.5oz", 1.18, 2.19), ("Urinary Care 8lb", 21.60, 37.99), ("Freeze-Dried Minnows 1oz", 4.10, 7.99)],
    "Treats & Chews": [("Bully Stick 12in", 3.95, 8.99), ("Dental Chews 30ct", 14.20, 26.99), ("Training Bites 16oz", 6.85, 12.99),
                       ("Yak Cheese Chew L", 7.40, 14.99), ("Salmon Skins 4oz", 5.15, 10.99), ("Beef Trachea 6in", 2.60, 5.49),
                       ("Cat Crunchy Treats 6oz", 2.35, 4.99), ("Peanut Butter Biscuits 2lb", 5.90, 11.99), ("Elk Antler M", 11.25, 22.99),
                       ("Pig Ear Single", 1.45, 3.29), ("Jerky Chicken Strips 10oz", 8.30, 15.99)],
    "Toys": [("Rope Tug Large", 4.80, 11.99), ("Squeaky Plush Fox", 5.25, 12.99), ("Rubber Chew Ball M", 6.10, 13.99), ("Cat Wand Feather", 2.70, 6.99),
             ("Puzzle Feeder Level 2", 11.40, 24.99), ("Catnip Mice 3pk", 1.95, 4.99), ("Fetch Launcher", 13.80, 29.99), ("Laser Pointer", 4.35, 9.99)],
    "Aquarium": [("20 Gallon Tank Kit", 68.50, 129.99), ("Canister Filter 40gal", 74.20, 139.99), ("Tropical Flakes 2.2oz", 3.85, 7.99),
                 ("Water Conditioner 16oz", 5.60, 11.49), ("Aquarium Heater 100W", 14.90, 29.99), ("LED Light Bar 24in", 27.30, 54.99),
                 ("Gravel Natural 25lb", 9.10, 18.99), ("Test Strips 50ct", 8.45, 17.99), ("Betta Pellets 1oz", 2.30, 4.99)],
    "Grooming": [("Oatmeal Shampoo 16oz", 5.20, 11.99), ("Slicker Brush M", 6.75, 14.99), ("Nail Clipper Pro", 7.90, 16.99), ("Ear Cleaner 4oz", 4.15, 9.49),
                 ("Deshedding Tool L", 14.60, 32.99), ("Detangling Spray 8oz", 4.70, 10.49), ("Paw Balm 2oz", 3.40, 8.99)],
}


def cent_tol(expected: float, rel: float = 0.01) -> float:
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))


def r2(x: float) -> float:
    return float(f"{x + (1e-9 if x >= 0 else -1e-9):.2f}")


def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    for ci, (cat, prods) in enumerate(CATS.items()):
        for pi, (name, cost, retail) in enumerate(prods):
            c = r2(cost * r.uniform(0.95, 1.05))
            items.append({"sku": f"{cat[:2].upper()}-{1040 + ci * 100 + pi * 7}", "name": name, "cat": cat, "cost": c, "retail": retail,
                          "counted_truth": r.randint(3, 48)})
    # true shrink: most items match, some short, a few over
    for cat in CATS:
        mine = [it for it in items if it["cat"] == cat]
        over = r.sample(mine, 2)
        for it in mine:
            it["loss"] = -r.randint(1, 2) if it in over else (r.randint(1, 4) if r.random() < 0.5 else 0)
    movements = []   # {at, type, sku, qty}

    def mv(it, at, typ, qty):
        movements.append({"at": at, "type": typ, "item": it, "qty": qty})

    for it in r.sample(items, 22):      # Sunday before the cutoff (in both count and snapshot)
        mv(it, datetime(2026, 8, 30, r.randint(12, 16), r.randint(0, 59)), "Sale", r.randint(1, 3))
    for it in r.sample(items, 18):      # Monday morning before the export: must be backed out
        mv(it, datetime(2026, 8, 31, r.randint(9, 10), r.randint(0, 59)), "Sale", r.randint(1, 3))
    for it in r.sample(items, 3):
        mv(it, datetime(2026, 8, 31, 10, r.randint(5, 50)), "Return", 1)
    rec = r.sample([x for x in items if x["cat"] in ("Dog Food", "Cat Food", "Treats & Chews")], 6)
    for it in rec:
        mv(it, datetime(2026, 8, 31, 9, 34), "Receipt", r.choice([6, 12, 12, 24]))
    for it in r.sample(items, 9):       # Monday afternoon, after the export: not in the snapshot
        mv(it, datetime(2026, 8, 31, r.randint(12, 17), r.randint(0, 59)), "Sale", r.randint(1, 2))
    movements.sort(key=lambda m: (m["at"], m["item"]["sku"]))

    damage = []   # pulled before the count
    for it in r.sample([x for x in items if x["cat"] in ("Dog Food", "Cat Food", "Treats & Chews", "Aquarium")], 7):
        damage.append({"item": it, "qty": r.randint(1, 3), "date": datetime(2026, 8, r.randint(18, 29), r.randint(9, 17), 0),
                       "posted": False, "reason": ("cracked glass" if it["cat"] == "Aquarium" else "crushed can" if "Canned" in it["name"]
                                                   else "past best-by date" if it["cat"] == "Treats & Chews" else r.choice(["torn bag", "water damage"]))})
    for dm in damage[:3]:
        dm["posted"] = True
    uncounted = [x for x in items if x["cat"] == "Aquarium" and x["cost"] > 20][:2]
    for it in uncounted:
        it["loss"] = 0

    # construct the snapshot so the story holds: counted = expected - loss
    for it in items:
        unposted = sum(dm["qty"] for dm in damage if dm["item"] is it and not dm["posted"])
        sold_after = sum(m["qty"] for m in movements if m["item"] is it and m["type"] == "Sale" and CUTOFF <= m["at"] <= EXPORT)
        ret_after = sum(m["qty"] for m in movements if m["item"] is it and m["type"] == "Return" and CUTOFF <= m["at"] <= EXPORT)
        rec_after = sum(m["qty"] for m in movements if m["item"] is it and m["type"] == "Receipt" and CUTOFF <= m["at"] <= EXPORT)
        counted = it["counted_truth"]
        expected = counted + it["loss"]                         # at the cutoff, after unposted damage came out
        at_cutoff_system = expected + unposted                  # the POS still carries the unposted damage
        it["snapshot"] = at_cutoff_system - sold_after + ret_after + rec_after
        it["expected"] = expected
        it["counted"] = None if it in uncounted else counted
        it["unposted"] = unposted
        it["value"] = 0.0 if it in uncounted else r2((expected - counted) * it["cost"])
    cats = {c: r2(sum(it["value"] for it in items if it["cat"] == c)) for c in CATS}
    total = r2(sum(cats.values()))
    damage_value = r2(sum(dm["qty"] * dm["item"]["cost"] for dm in damage if not dm["posted"]))
    return {"items": items, "movements": movements, "damage": damage, "uncounted": uncounted, "cats": cats, "total": total,
            "damage_value": damage_value}


def naive_values(d: dict) -> dict:
    """Snapshot less counted, at retail, blanks as zero, shortages only."""
    out = {}
    for it in d["items"]:
        diff = it["snapshot"] - (it["counted"] or 0)
        out[it["cat"]] = out.get(it["cat"], 0.0) + max(diff, 0) * it["retail"]
    return out


def acceptable(d: dict) -> bool:
    cats, nv = d["cats"], naive_values(d)
    if any(v <= 20 for v in cats.values()):
        return False
    for c in CATS:   # each category moves under the shortcut and under each single mistake
        if abs(nv[c] - cats[c]) < 5:
            return False
        at_cost_no_cutoff = sum((it["snapshot"] - (it["counted"] if it["counted"] is not None else it["snapshot"])) * it["cost"] for it in d["items"] if it["cat"] == c)
        if abs(at_cost_no_cutoff - cats[c]) < 2:
            return False
        shortages_only = sum(max(it["value"], 0) for it in d["items"] if it["cat"] == c)
        if abs(shortages_only - cats[c]) < 2:
            return False
    aq_blank_zero = cats["Aquarium"] + sum(it["expected"] * it["cost"] for it in d["uncounted"])
    if abs(aq_blank_zero - cats["Aquarium"]) < 50:
        return False
    vals = list(cats.values()) + [d["total"], d["damage_value"]]
    if len({round(v, 2) for v in vals}) != len(vals):
        return False
    return True


def report_sheets(items: list[dict], damage_rows: list[list], cats: list[str]) -> dict:
    n = len(items) + 1
    detail = []
    for i, it in enumerate(items, start=2):
        detail.append([it["sku"], it["name"], it["cat"], it["expected"], "" if it["counted"] is None else it["counted"], it["cost"],
                       f'=IF(E{i}="","not counted",D{i}-E{i})', f'=IF(E{i}="",0,G{i}*F{i})'])
    m = len(damage_rows) + 1
    summary = []
    for j, c in enumerate(cats, start=2):
        summary.append([c, f"=SUMIF(Detail!$C$2:$C${n},A{j},Detail!$H$2:$H${n})"])
    last = len(cats) + 1
    summary.append(["Total net shrinkage", f"=SUM(B2:B{last})"])
    summary.append([])
    summary.append(["Damaged, set aside before the count (not shrinkage)", f"=SUM(Damage!E2:E{m})"])
    return {
        "Summary": {"header": ["Category", "Net shrinkage at average cost"], "rows": summary, "widths": {"A": 48, "B": 30},
                    "number_formats": {"B": "#,##0.00"}},
        "Detail": {"header": ["SKU", "Item", "Category", "Expected at count", "Counted", "Avg cost", "Units short", "Shrink value"],
                   "rows": detail, "widths": {"B": 32, "C": 16}},
        "Damage": {"header": ["SKU", "Item", "Qty", "Avg cost", "Value"],
                   "rows": [row[:4] + [f"=C{i}*D{i}"] for i, row in enumerate(damage_rows, start=2)], "widths": {"B": 32}},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    items, cats = d["items"], d["cats"]
    r = rng(seed + 3)

    write_csv(os.path.join(ws, "pos_on_hand_export_2026-08-31_1115.csv"), ["SKU", "Description", "Department", "On Hand", "Avg Cost", "Retail"],
              [[it["sku"], it["name"], it["cat"], it["snapshot"], f"{it['cost']:.2f}", f"{it['retail']:.2f}"] for it in items],
              preamble=["Bramble & Hound Pet Supply - Inventory On Hand", "Run: 08/31/2026 11:15 AM"], bom=True)
    count_rows = []
    order = sorted(items, key=lambda it: (it["cat"] != "Aquarium", r.random()))
    initials = ["MK", "DT", "JR"]
    for it in order:
        count_rows.append([it["sku"], it["name"], "" if it["counted"] is None else it["counted"],
                           "locked case - key missing" if it["counted"] is None else "", r.choice(initials)])
    write_xlsx(os.path.join(ws, "floor_count_2026-08-30.xlsx"), {"Count": {
        "merged_title": "Annual floor count - Sunday 08/30/2026 after close",
        "preamble": [["Count started 5:00 PM once the doors were locked", "", "", "", ""]],
        "header": ["SKU", "Item", "Qty Counted", "Notes", "Counter"], "rows": count_rows, "widths": {"B": 32, "D": 26}}}, creator="Bramble & Hound")
    write_csv(os.path.join(ws, "pos_item_movements_2026-08-30_to_2026-08-31.csv"), ["Timestamp", "Type", "SKU", "Qty", "Register"],
              [[m["at"].strftime("%m/%d/%Y %I:%M %p"), m["type"], m["item"]["sku"], m["qty"] if m["type"] != "Sale" else -m["qty"],
                "Receiving" if m["type"] == "Receipt" else r.choice(["REG1", "REG2"])] for m in d["movements"]])
    write_csv(os.path.join(ws, "damage_log_august.csv"), ["Logged", "SKU", "Item", "Qty", "Reason", "Written off in POS"],
              [[dm["date"].strftime("%Y-%m-%d %H:%M"), dm["item"]["sku"], dm["item"]["name"], dm["qty"], dm["reason"],
                "Yes 08/28" if dm["posted"] else "No"] for dm in sorted(d["damage"], key=lambda x: x["date"])])
    write_text(os.path.join(ws, "note_from_rhea.txt"), """Shrinkage for the insurance renewal and the accountant

We counted the floor Sunday night after we closed at 5. I did not get the on-hand report out of the POS until
Monday late morning, after we had opened, sold things and put away the Monday delivery - so the report is not what
we had on the shelves when we counted. Anything that happened after 5 pm Sunday and before the report ran needs
taking back out of it.

The damaged stuff in the back room (torn bags, dented cans, the cracked tank) was pulled before the count, so it
was not counted. Some of it I already wrote off in the POS, some I have not. Damage is not shrinkage - show it on its
own line.

The accountant wants shrinkage at our average cost, not retail, net by department (if we found extra of something,
that offsets what is missing in the same department), as a positive dollar figure when we are short, and a total.
Anything the count sheet left blank was not counted - leave it out, do not treat it as zero.

Please make it shrinkage.xlsx with formulas so she can follow it.

- Rhea
""")

    damage_rows = [[dm["item"]["sku"], dm["item"]["name"], dm["qty"], dm["item"]["cost"]] for dm in d["damage"] if not dm["posted"]]
    write_xlsx(os.path.join(sol, "shrinkage.xlsx"), report_sheets(items, damage_rows, list(CATS)), creator="reference")
    write_csv(os.path.join(ref, "shrinkage_by_category.csv"), ["category", "net_shrinkage"], [[c, f"{v:.2f}"] for c, v in cats.items()] +
              [["TOTAL", f"{d['total']:.2f}"], ["DAMAGE (not shrinkage)", f"{d['damage_value']:.2f}"]])
    write_csv(os.path.join(ref, "item_detail.csv"), ["sku", "category", "snapshot", "expected", "counted", "avg_cost", "value"],
              [[it["sku"], it["cat"], it["snapshot"], it["expected"], "" if it["counted"] is None else it["counted"], f"{it['cost']:.2f}", f"{it['value']:.2f}"] for it in items])

    def pin(name, value, near):
        return {"type": "xlsx_value_present", "name": name, "path": "shrinkage.xlsx", "expected": value, "rel_tol": cent_tol(value), "near_text": near}
    write_task_yaml(HERE, {
        "id": "inventory-shrinkage", "track": "desk", "category": "bookkeeping",
        "title": "Shrinkage by department from the Sunday floor count",
        "ask": ("Rhea needs our shrinkage from Sunday's floor count for the insurance renewal. The count sheet, the POS reports and "
                "her note are in the folder. Save it as shrinkage.xlsx.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the export carries retail beside average cost and the note wants average cost; valuing at retail roughly doubles every "
            "department (checks: Dog Food value; Treats & Chews value; total net shrinkage)",
            "the on-hand report ran Monday 11:15 am: Monday-morning sales and returns and the 9:34 am delivery happened after the count and "
            "must be backed out of it, while Sunday sales before 5 pm and Monday afternoon sales are already consistent and need nothing "
            "(checks: Dog Food value; Cat Food value; total net shrinkage)",
            "damaged stock was pulled before the count: the lines not yet written off still sit in the POS and come out of expected as "
            "a separate damage figure, while the lines marked written off are already gone from the report "
            "(checks: damage set aside; Cat Food value)",
            "shrink is net within a department, so the few items found over offset the shortages; totalling shortages alone overstates "
            "every department (checks: Treats & Chews value; total net shrinkage)",
            f"two aquarium items in a locked case ({', '.join(it['sku'] for it in d['uncounted'])}) are blank on the count sheet; they were "
            "not counted and stay out, where a blank read as zero adds hundreds of dollars (checks: Aquarium value; total net shrinkage)",
            "the figures must be live formulas that recalculate clean (checks: live formulas; no error cells)",
        ],
        "checks": [
            {"type": "file_exists", "name": "shrinkage.xlsx exists", "path": "shrinkage.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "shrinkage.xlsx", "min_count": 6},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "shrinkage.xlsx"},
            pin("Dog Food value", cats["Dog Food"], "dog food"),
            pin("Cat Food value", cats["Cat Food"], "cat food"),
            pin("Treats & Chews value", cats["Treats & Chews"], "treats"),
            pin("Aquarium value", cats["Aquarium"], "aquarium"),
            pin("total net shrinkage", d["total"], "total"),
            pin("damage set aside", d["damage_value"], "damage"),
        ],
    })
    print(f"seed={seed} items={len(items)} movements={len(d['movements'])} cats={cats} total={d['total']} damage={d['damage_value']}")
    print("naive:", {k: round(v, 2) for k, v in naive_values(d).items()})


def write_naive(d: dict, out: str) -> None:
    """Snapshot less counted at retail, blanks as zero, shortages only, pasted values, no damage line."""
    os.makedirs(out, exist_ok=True)
    nv = naive_values(d)
    rows = [[c, round(v, 2)] for c, v in nv.items()] + [["Total", round(sum(nv.values()), 2)]]
    write_xlsx(os.path.join(out, "shrinkage.xlsx"), {"Summary": {"header": ["Department", "Shrinkage"], "rows": rows}}, creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(600):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
