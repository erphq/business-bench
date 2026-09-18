#!/usr/bin/env python3
"""reorder-list: what a bike shop should reorder this week and how much, from stock, settings, suppliers and open POs.

    python gen.py [--seed N] [--naive DIR]

Business: an independent bike shop. The POS exports stock per location; reorder points and pack sizes live in a
settings export; supplier lead times are in a list the owner keeps; open purchase orders come from the POS.

Traps (each caught by a check, see task.yaml):
  * on-order quantity (ordered minus already received) reduces need            (checks: items to reorder; order quantity)
  * cancelled PO lines are not on order                                           (check: items to reorder)
  * order quantities round up to whole packs                                      (check: order quantity)
  * a discontinued brand and one discontinued item stay off the list (the note)   (check: items to reorder)
  * items stocked in two locations must be summed                                 (check: items to reorder)
  * lead times written in days and weeks                                          (check: order quantity)
"""
from __future__ import annotations
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

SUPPLIERS = [("QBP", 5, "5 days"), ("BTI", 7, "7 days"), ("Kestrel Components", 10, "10 days"),
             ("Orange Seal Co", 14, "2 weeks"), ("Shimano Direct", 21, "3 weeks"), ("Light & Motion", 12, "12 days")]
LEAD = {s: d for s, d, _ in SUPPLIERS}
COVER_DAYS = 28
# sku, description, supplier, pack size
ITEMS = [
    ("TUB-700-25", "Tube 700x25c presta 48mm", "QBP", 10), ("TUB-700-32", "Tube 700x28-32c presta", "QBP", 10),
    ("TUB-29-24", "Tube 29x2.1-2.4 presta", "QBP", 10), ("TUB-26-195", "Tube 26x1.95 schrader", "QBP", 10),
    ("TUB-20-175", "Tube 20x1.75 schrader", "BTI", 5), ("TIR-700-28", "Tire 700x28c folding", "QBP", 2),
    ("TIR-29-23", "Tire 29x2.3 tubeless ready", "QBP", 2), ("TIR-650B-47", "Tire 650bx47 gravel", "BTI", 2),
    ("CHN-11", "Chain 11-speed 116L", "Shimano Direct", 5), ("CHN-12", "Chain 12-speed 126L", "Shimano Direct", 5),
    ("CHN-9", "Chain 9-speed 116L", "Shimano Direct", 5), ("CAS-11-34", "Cassette 11-speed 11-34", "Shimano Direct", 1),
    ("PAD-RES", "Disc brake pads resin", "Shimano Direct", 10), ("PAD-MET", "Disc brake pads metal", "Shimano Direct", 10),
    ("PAD-RIM", "Rim brake pads road", "BTI", 4), ("CBL-BRK", "Brake cable stainless", "BTI", 25),
    ("CBL-SHF", "Shift cable stainless", "BTI", 25), ("GRP-LOK", "Lock-on grips black", "Kestrel Components", 6),
    ("TAPE-BLK", "Bar tape black", "Kestrel Components", 6), ("SDL-CMF", "Comfort saddle", "Kestrel Components", 2),
    ("LUB-DRY", "Chain lube dry 4oz", "BTI", 12), ("LUB-WET", "Chain lube wet 4oz", "BTI", 12),
    ("SEAL-4", "Tubeless sealant 4oz", "Orange Seal Co", 12), ("SEAL-32", "Tubeless sealant 32oz", "Orange Seal Co", 4),
    ("VLV-TL44", "Tubeless valves 44mm pair", "Orange Seal Co", 10), ("PATCH-6", "Patch kit 6pc", "QBP", 24),
    ("CO2-16", "CO2 cartridge 16g threaded", "QBP", 20), ("PUMP-MINI", "Mini pump", "QBP", 4),
    ("LGT-F800", "Front light 800 lumen", "Light & Motion", 4), ("LGT-R100", "Rear light 100 lumen", "Light & Motion", 4),
    ("BTL-24", "Water bottle 24oz", "BTI", 12), ("CAGE-AL", "Bottle cage alloy", "BTI", 6),
    ("ROT-160", "Disc rotor 160mm 6-bolt", "Shimano Direct", 2), ("BELL-BR", "Bell brass", "BTI", 6),
    ("TOOL-MULTI", "Multi-tool 14 function", "QBP", 4), ("GLV-M", "Gloves full finger M", "Kestrel Components", 3),
]


def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    for sku, desc, sup, pack in ITEMS:
        lo, hi = (0.4, 2.2) if pack >= 10 else (0.2, 0.9) if pack >= 4 else (0.08, 0.5)
        daily = round(r.uniform(lo, hi), 2)
        safety = max(2, int(round(daily * r.uniform(3, 6))))
        rop = int(math.ceil(daily * LEAD[sup] + safety))
        items.append({"sku": sku, "desc": desc, "sup": sup, "pack": pack, "daily": daily, "rop": rop, "status": "Active",
                      "locs": [], "po": []})
    I = {x["sku"]: x for x in items}
    discontinued_brand = "Kestrel Components"
    disc_item = "CHN-9"
    for x in items:
        if x["sup"] == discontinued_brand or x["sku"] == disc_item:
            x["disc"] = True
    # on-hand stock, mostly one location, some split across floor and back room
    for x in items:
        k = r.random()
        oh = max(0, int(x["rop"] * r.uniform(0.2, 1.8)))
        x["locs"] = [("Sales floor", oh)]
    # trap items
    candidates = [x for x in items if not x.get("disc") and x["rop"] >= 8]
    r.shuffle(candidates)
    t_weeks = next(x for x in candidates if LEAD[x["sup"]] in (14, 21))
    candidates.remove(t_weeks)
    t_onorder, t_partial, t_cancel, t_two_hide, t_two_low = candidates[:5]
    # on hand below ROP but an open PO lifts it above
    t_onorder["locs"] = [("Sales floor", max(0, t_onorder["rop"] - r.randint(2, 5)))]
    pk = t_onorder["pack"]
    t_onorder["po"].append({"ordered": pk * (math.ceil(t_onorder["rop"] / pk) + r.randint(1, 2)), "received": 0, "status": "Open"})
    # partially received PO: the remainder is not enough, the full ordered qty would be
    pk = t_partial["pack"]
    got = pk * max(1, math.ceil(4 / pk))
    t_partial["locs"] = [("Sales floor", max(0, t_partial["rop"] - got - r.randint(0, 2)))]
    t_partial["po"].append({"ordered": got + pk * max(1, math.ceil(3 / pk)), "received": got, "status": "Partial"})
    # cancelled PO would lift it above ROP
    t_cancel["locs"] = [("Sales floor", max(0, t_cancel["rop"] - 3))]
    pk = t_cancel["pack"]
    t_cancel["po"].append({"ordered": pk * max(2, math.ceil(8 / pk)), "received": 0, "status": "Cancelled"})
    # split locations: floor alone is under ROP, the total is not
    t_two_hide["locs"] = [("Sales floor", max(1, t_two_hide["rop"] // 3)), ("Back room", t_two_hide["rop"])]
    # split locations: still low in total, but the back room changes the quantity
    t_two_low["locs"] = [("Sales floor", max(1, t_two_low["rop"] // 4)), ("Back room", max(1, t_two_low["rop"] // 3))]
    # lead time in weeks: make sure the item needs ordering
    t_weeks["locs"] = [("Sales floor", max(0, t_weeks["rop"] - r.randint(1, 4)))]
    # discontinued but low: must not be ordered
    for x in items:
        if x.get("disc") and (r.random() < 0.6 or x["sku"] == disc_item):
            x["locs"] = [("Sales floor", r.randint(0, max(1, x["rop"] // 2)))]
    # a few ordinary open POs on other items
    others = [x for x in items if not x["po"] and not x.get("disc") and x not in (t_two_hide, t_two_low, t_weeks)]
    for x in r.sample(others, 5):
        x["po"].append({"ordered": x["pack"] * r.randint(1, 3), "received": 0, "status": "Open"})

    def need(x, *, on_order=True, cancelled_counts=False, partial_full=False, first_loc=False, round_packs=True,
             weeks_as_days=False, include_disc=False):
        if x.get("disc") and not include_disc:
            return 0
        oh = x["locs"][0][1] if first_loc else sum(q for _, q in x["locs"])
        oo = 0
        if on_order:
            for p in x["po"]:
                if p["status"] == "Cancelled" and not cancelled_counts:
                    continue
                oo += p["ordered"] if partial_full else p["ordered"] - p["received"]
        avail = oh + oo
        if avail > x["rop"]:
            return 0
        lead = LEAD[x["sup"]]
        if weeks_as_days and lead in (14, 21):
            lead = lead // 7
        target = x["daily"] * (lead + COVER_DAYS)
        q = target - avail
        if q <= 0:
            return 0
        return int(math.ceil(q / x["pack"]) * x["pack"]) if round_packs else int(math.ceil(q))

    truth = {x["sku"]: need(x) for x in items}
    return {"items": items, "need": need, "truth": truth, "traps": {
        "onorder": t_onorder["sku"], "partial": t_partial["sku"], "cancel": t_cancel["sku"], "two_hide": t_two_hide["sku"],
        "two_low": t_two_low["sku"], "weeks": t_weeks["sku"]}}


def acceptable(d: dict) -> bool:
    I = {x["sku"]: x for x in d["items"]}
    need, t, tr = d["need"], d["truth"], d["traps"]
    if t[tr["onorder"]] != 0 or need(I[tr["onorder"]], on_order=False) == 0:
        return False
    if t[tr["partial"]] == 0 or need(I[tr["partial"]], partial_full=True) == t[tr["partial"]]:
        return False
    if t[tr["cancel"]] == 0 or need(I[tr["cancel"]], cancelled_counts=True) != 0:
        return False
    if t[tr["two_hide"]] != 0 or need(I[tr["two_hide"]], first_loc=True) == 0:
        return False
    if t[tr["two_low"]] == 0 or need(I[tr["two_low"]], first_loc=True) == t[tr["two_low"]]:
        return False
    if t[tr["weeks"]] == 0 or need(I[tr["weeks"]], weeks_as_days=True) == t[tr["weeks"]]:
        return False
    low_disc = [x["sku"] for x in d["items"] if x.get("disc") and need(x, include_disc=True) > 0]
    if "CHN-9" not in low_disc or len(low_disc) < 3:
        return False
    ordered = [x for x in d["items"] if t[x["sku"]] > 0]
    unrounded_differs = sum(1 for x in ordered if need(x, round_packs=False) != t[x["sku"]])
    # the target: only items whose next pack is really needed; target covers at least one full pack
    return 10 <= len(ordered) <= 20 and unrounded_differs >= 6


HEADER = ["sku", "description", "supplier", "order_qty"]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    items, t = d["items"], d["truth"]
    if naive_dir:
        # first stock row per SKU, every PO line's ordered quantity (cancelled too), no pack rounding, lead time digits
        os.makedirs(naive_dir, exist_ok=True)
        rows = []
        for x in items:
            q = d["need"](x, cancelled_counts=True, partial_full=True, first_loc=True, round_packs=False,
                          weeks_as_days=True, include_disc=True)
            if q > 0:
                rows.append([x["sku"], x["desc"], x["sup"], q])
        write_csv(os.path.join(naive_dir, "reorder.csv"), HEADER, rows)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 7)
    stock_rows = []
    for x in items:
        for loc, q in x["locs"]:
            stock_rows.append([x["sku"], x["desc"], loc, q, x["daily"]])
    stock_rows.sort(key=lambda z: (z[0], z[2] != "Sales floor"))
    write_xlsx(os.path.join(ws, "stock_on_hand_2026-09-12.xlsx"), {"Stock": {
        "merged_title": "Zephyr Bike Works - inventory by location",
        "preamble": [["Exported 09/12/2026 from POS"]],
        "header": ["SKU", "Description", "Location", "On Hand", "Avg Daily Sales (90d)"], "rows": stock_rows,
        "widths": {"A": 14, "B": 32, "C": 14}}}, creator="POS")
    write_csv(os.path.join(ws, "item_settings_export.csv"), ["SKU", "Description", "Primary Vendor", "Reorder Point", "Pack Qty"],
              [[x["sku"], x["desc"], x["sup"], x["rop"], x["pack"]] for x in items], bom=True, crlf=True)
    write_csv(os.path.join(ws, "vendor_lead_times.csv"), ["Vendor", "Rep", "Lead time", "Order method"],
              [[s, f"{pf} {pl}", txt, r.choice(["portal", "email", "phone"])]
               for (s, _, txt), (pf, pl) in zip(SUPPLIERS, people(r, len(SUPPLIERS)))])
    po_rows = []
    pon = 2210
    for x in sorted(items, key=lambda z: z["sku"]):
        for p in x["po"]:
            pon += 1
            po_rows.append([f"PO-{pon}", x["sup"], x["sku"], p["ordered"], p["received"], p["status"],
                            f"09/{r.randint(14, 30):02d}/2026" if p["status"] != "Cancelled" else ""])
    r.shuffle(po_rows)
    write_csv(os.path.join(ws, "open_purchase_orders.csv"), ["PO", "Vendor", "SKU", "Qty Ordered", "Qty Received", "Status", "Expected"],
              po_rows)
    write_text(os.path.join(ws, "note_from_nadia.txt"), (
        "Reorder run for this week.\n\n"
        "Anything at or below its reorder point needs ordering - but count what is already on order (whatever "
        "hasn't arrived yet on open POs) as if it were on the shelf, and count both the floor and the back room. "
        "Cancelled POs are not coming.\n\n"
        f"How much: enough to get us through the vendor's lead time plus four weeks of sales. So average daily "
        f"sales x (lead time in days + {COVER_DAYS}), minus what we have and what's on order. Vendors only sell "
        "in packs, so round up to a full pack.\n\n"
        "Do not reorder anything from Kestrel Components - we are dropping the brand and selling through what's "
        "left. Same for the 9-speed chains, nobody asks for them anymore.\n\n"
        "Send me reorder.csv with sku, description, supplier and order_qty (in units, not packs), one line per "
        "item we need to order.\n\n"
        "Nadia\n"))

    rows = [[x["sku"], x["desc"], x["sup"], t[x["sku"]]] for x in items if t[x["sku"]] > 0]
    write_csv(os.path.join(ref, "reorder.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "reorder.csv"), HEADER, rows)
    tr = d["traps"]
    write_json(os.path.join(ref, "notes.json"), {"traps": tr, "truth_all": t,
                                                  "discontinued_low": [x["sku"] for x in items if x.get("disc") and d["need"](x, include_disc=True) > 0]})
    must = [tr["partial"], tr["two_low"], tr["weeks"], tr["cancel"]]
    write_task_yaml(HERE, {
        "id": "reorder-list", "track": "desk", "category": "spreadsheet",
        "title": "This week's reorder list for the bike shop",
        "ask": ("Can you do this week's reorder run? Nadia's note has how she works it out - I need reorder.csv with "
                "what to order and how many.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            f"one item is under its reorder point on the shelf but an open PO already covers it ({tr['onorder']}); "
            "ignoring on-order stock puts it on the list (check: items to reorder)",
            f"a partially received PO ({tr['partial']}) still has only the unreceived remainder on order; counting "
            "the full ordered quantity understates the order (check: order quantity)",
            f"a cancelled PO line ({tr['cancel']}) would lift its item above the reorder point if it were counted "
            "(checks: items to reorder; order quantity)",
            "every order rounds up to the vendor's pack size (tubes by 10, cables by 25, bottles by 12); the raw "
            "shortfall is almost never a whole pack (check: order quantity)",
            "Kestrel Components is being dropped and the 9-speed chain is discontinued, both only in the note and "
            "both with items below their reorder points (check: items to reorder)",
            f"stock is exported per location: {tr['two_hide']} is low on the sales floor but fine with the back "
            f"room, and {tr['two_low']} needs ordering either way but in a different quantity "
            "(checks: items to reorder; order quantity)",
            "lead times are text: '5 days', '2 weeks', '3 weeks'; reading the number alone shrinks the cover for "
            "Orange Seal and Shimano items; the settings export also carries a BOM and CRLF endings "
            "(check: order quantity)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "reorder.csv", "columns": HEADER},
            {"type": "csv_set_equal", "name": "items to reorder", "path": "reorder.csv", "column": "sku", "ref": "reorder.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "reorder.csv", "equals_ref": "reorder.csv"},
            {"type": "csv_values_match", "name": "order quantity", "path": "reorder.csv", "ref": "reorder.csv", "key": "sku",
             "columns": ["order_qty"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0, "must_match_keys": must},
        ],
    })
    print(f"seed={seed} to order={len(rows)} traps={tr}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(2000):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
