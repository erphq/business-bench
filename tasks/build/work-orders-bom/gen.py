#!/usr/bin/env python3
"""Deterministic seed generator for the work-orders-bom build task.

    python gen.py [--seed N]

Writes:
  seed/parts.csv          inventory: components and finished goods (part numbers that lost their leading zeros,
                          repeated rows, "$16.40" costs, "2,400" quantities)
  seed/boms.csv           flat bill-of-materials export (repeated lines, unpadded component numbers, one line
                          pointing at a part that is not in the parts list)
  seed/work_orders.csv    six months of work orders (repeated rows, an unprefixed WO number, line and status words
                          from two eras, one work order due before it starts)
  reference/counts.json   every figure checklist.md and changes/*.md quote, computed from the ground truth

Seed 0 is the public variant that checklist.md quotes. Other seeds re-roll costs, stock, quantities, dates, and
statuses; counts.json is recomputed from the truth, so re-derive checklist numbers from it.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import write_csv  # noqa: E402

SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")
AS_OF = date(2026, 9, 11)

LINES = {1: ("Line 1 - Tables", "Dale Pruitt", ["Line 1", "L1", "Tables"]),
         2: ("Line 2 - Carts", "Sam Whitaker", ["Line 2", "L2", "Carts"]),
         3: ("Line 3 - Shelving", "Grace Liu", ["Line 3", "L3", "Shelving"])}
RESTRICTED_LINE = 2
TEST_LINE = 1

# (number, description, uom, cost range, on-hand range, reorder point)
COMPONENTS = [
    (1010, "SS304 sheet 16ga 48x96", "sheet", (210, 260), (30, 70), 20), (1011, "SS304 sheet 14ga 48x96", "sheet", (260, 320), (8, 20), 6),
    (1012, "SS304 sheet 18ga 36x96", "sheet", (150, 190), (40, 90), 25), (1013, "SS430 sheet 18ga 36x96", "sheet", (95, 125), (10, 30), 8),
    (1020, "SS304 square tube 1-1/4in x 20ft", "ea", (58, 74), (30, 60), 15), (1021, "SS304 square tube 1in x 20ft", "ea", (44, 58), (20, 45), 12),
    (1022, "SS304 round tube 1-5/8in x 20ft", "ea", (66, 82), (25, 50), 12), (1030, "SS leg 1-5/8in x 34in", "ea", (15, 22), (150, 300), 80),
    (1031, "SS leg 1-5/8in x 30in", "ea", (13, 19), (60, 140), 40), (1032, "SS leg 1-5/8in x 24in", "ea", (11, 16), (20, 60), 20),
    (1040, "Cart upright SS 1in x 36in", "ea", (9, 14), (220, 400), 100), (1041, "Cart upright SS 1in x 30in", "ea", (8, 12), (40, 90), 30),
    (1050, "Shelving post chrome 74in", "ea", (11, 16), (400, 600), 120), (1051, "Shelving post chrome 63in", "ea", (9, 13), (60, 140), 40),
    (1052, "Shelving post SS 74in", "ea", (22, 29), (30, 80), 20), (1053, "Shelving post chrome 86in", "ea", (13, 18), (20, 60), 16),
    (1060, "Wall shelf bracket SS 12in", "ea", (7, 10), (40, 120), 30), (1061, "Wall shelf bracket SS 18in", "ea", (8, 12), (20, 60), 16),
    (2010, "Caster 5in swivel with brake", "ea", (12, 18), (38, 38), 40), (2011, "Caster 5in swivel", "ea", (9, 13), (180, 320), 80),
    (2012, "Caster 5in rigid", "ea", (7, 11), (200, 340), 80), (2013, "Caster 3in swivel", "ea", (5, 8), (60, 160), 40),
    (2014, "Caster 4in swivel with brake", "ea", (10, 15), (30, 90), 24), (2015, "Caster 6in polyurethane swivel", "ea", (18, 26), (12, 40), 12),
    (2020, "Adjustable bullet foot 1-5/8in", "ea", (3, 5), (200, 400), 100), (2021, "Leveling foot for shelving post", "ea", (1, 2), (500, 800), 160),
    (2022, "Flanged foot 1-5/8in", "ea", (5, 8), (40, 120), 30), (2030, "Wire shelf chrome 18x48", "ea", (19, 26), (180, 320), 80),
    (2031, "Wire shelf chrome 24x48", "ea", (23, 31), (400, 600), 120), (2032, "Wire shelf chrome 18x36", "ea", (15, 21), (160, 300), 80),
    (2033, "Wire shelf chrome 24x60", "ea", (29, 37), (100, 220), 60), (2034, "Solid shelf SS 20x36 dunnage", "ea", (42, 55), (20, 50), 12),
    (2035, "Wire shelf chrome 14x36", "ea", (12, 17), (40, 100), 30), (2036, "Wire shelf epoxy green 18x48", "ea", (24, 32), (30, 80), 20),
    (2040, "Split sleeve pair", "ea", (0.35, 0.6), (2000, 3200), 600), (2041, "S-hook shelf connector", "ea", (0.5, 0.9), (200, 500), 100),
    (2050, "Push handle SS 18in", "ea", (16, 24), (60, 140), 30), (2051, "Push handle SS 24in", "ea", (18, 27), (60, 140), 30),
    (2060, "Corner bumper rubber", "ea", (1.5, 2.6), (300, 600), 120), (2061, "Perimeter bumper strip 6ft", "ea", (8, 12), (60, 140), 30),
    (2070, "Sink bowl 18x18x12 SS", "ea", (68, 88), (40, 90), 20), (2071, "Sink bowl 16x20x12 SS", "ea", (72, 92), (10, 30), 8),
    (2080, "Lever waste drain 3.5in", "ea", (18, 26), (40, 90), 20), (2081, "Basket strainer drain 3.5in", "ea", (12, 18), (20, 60), 16),
    (2090, "Deck faucet 8in splash mount", "ea", (62, 84), (20, 60), 12), (2091, "Deck faucet 12in splash mount", "ea", (70, 92), (10, 30), 8),
    (2100, "Pan slide angle 18in pair", "ea", (6, 9), (300, 600), 100), (2110, "Undershelf gusset", "ea", (2, 3.5), (200, 400), 80),
    (2120, "Drawer assembly 20x20 SS", "ea", (48, 64), (10, 30), 8), (2130, "Backsplash 4in SS 60in", "ea", (22, 30), (10, 40), 10),
    (3010, "Bolt 1/4-20 x 3/4 SS", "ea", (0.12, 0.2), (2400, 2400), 800), (3011, "Nylock nut 1/4-20 SS", "ea", (0.07, 0.12), (1800, 3600), 800),
    (3012, "Hex bolt 3/8-16 x 1 SS", "ea", (0.25, 0.4), (900, 1800), 400), (3013, "Flat washer 1/4 SS", "ea", (0.03, 0.06), (1500, 3000), 500),
    (3014, "Carriage bolt 5/16-18 x 1 SS", "ea", (0.2, 0.35), (400, 900), 200), (3020, "Welding wire ER308L 0.035 (lb)", "lb", (11, 15), (60, 140), 40),
    (3021, "Welding rod ER308L 1/16 (lb)", "lb", (12, 17), (20, 60), 15), (3030, "Passivation gel (qt)", "ea", (21, 29), (8, 24), 6),
    (3040, "Rivet SS 3/16", "ea", (0.05, 0.09), (2000, 4000), 800), (3050, "Grinding disc 4-1/2in 60 grit", "ea", (1.8, 2.6), (100, 300), 60),
    (5010, "Carton kit cart", "ea", (6, 9), (120, 260), 60), (5011, "Carton shelving 4-tier", "ea", (4, 6), (300, 500), 90),
    (5012, "Carton shelving 5-tier", "ea", (5, 7), (60, 140), 30), (5020, "Crate table", "ea", (18, 26), (40, 90), 20),
    (5021, "Crate sink", "ea", (22, 30), (10, 30), 8), (5030, "Serial plate label", "ea", (0.6, 1.0), (900, 1600), 300),
    (5031, "Assembly instructions sheet", "ea", (0.1, 0.2), (500, 1500), 200), (5040, "Stretch wrap roll", "ea", (18, 24), (10, 30), 6),
]
ORPHAN = (9950, "Wall anchor kit")

FINISHED = [  # code, description, line, BOM [(component number, qty per)]
    ("TBL-3060", "Work table 30x60 with undershelf", 1, [(1010, 1), (1012, 0.5), (1030, 4), (2020, 4), (1022, 0.5), (2110, 4), (3010, 8), (3011, 8), (3020, 0.5), (5020, 1), (5030, 1)]),
    ("TBL-3072", "Work table 30x72 with undershelf", 1, [(1010, 1.5), (1012, 0.5), (1030, 6), (2020, 6), (1022, 0.5), (2110, 6), (3010, 12), (3011, 12), (3020, 0.75), (5020, 1), (5030, 1)]),
    ("TBL-2448", "Work table 24x48 with undershelf", 1, [(1010, 0.5), (1012, 0.5), (1030, 4), (2020, 4), (2110, 4), (3010, 8), (3011, 8), (3020, 0.5), (5020, 1), (5030, 1)]),
    ("TBL-3048", "Work table 30x48 with undershelf", 1, [(1010, 1), (1012, 0.5), (1030, 4), (2020, 4), (2110, 4), (3010, 8), (3011, 8), (3020, 0.5), (5020, 1), (5030, 1)]),
    ("SNK-1C18", "One-compartment sink 18x18", 1, [(2070, 1), (2080, 1), (2090, 1), (1010, 1), (1030, 4), (2020, 4), (3020, 1), (5021, 1), (5030, 1)]),
    ("SNK-3C18", "Three-compartment sink 18x18", 1, [(2070, 3), (2080, 3), (2090, 2), (1010, 2), (1030, 6), (2020, 6), (3020, 2), (5021, 1), (5030, 1)]),
    ("TBL-EQ-2430", "Equipment stand 24x30", 1, [(1010, 0.5), (1031, 4), (2020, 4), (3010, 4), (3011, 4), (3020, 0.25), (5020, 1), (5030, 1)]),
    ("CRT-1827-2S", "Utility cart 18x27 two shelf", 2, [(1012, 0.5), (1040, 4), (2011, 2), (2012, 2), (2050, 1), (2060, 4), (3010, 16), (3011, 16), (3012, 8), (5010, 1), (5030, 1)]),
    ("CRT-1827-3S", "Utility cart 18x27 three shelf", 2, [(1012, 0.75), (1040, 4), (2011, 2), (2012, 2), (2050, 1), (2060, 4), (3010, 24), (3011, 24), (3012, 8), (5010, 1), (5030, 1)]),
    ("CRT-2436-2S", "Utility cart 24x36 two shelf", 2, [(1012, 1), (1040, 4), (2010, 2), (2012, 2), (2051, 1), (2060, 4), (3010, 16), (3011, 16), (3012, 8), (5010, 1), (5030, 1)]),
    ("CRT-BUS-3S", "Bus cart three shelf", 2, [(1012, 0.75), (1040, 4), (2011, 2), (2012, 2), (2051, 1), (2061, 2), (3010, 24), (3011, 24), (3012, 8), (5010, 1), (5030, 1)]),
    ("CRT-UTIL-HD", "Heavy-duty utility cart 24x48", 2, [(1010, 1), (1020, 0.5), (2015, 4), (2051, 2), (2060, 4), (3010, 24), (3011, 24), (3012, 16), (3020, 0.5), (5010, 1), (5030, 1)]),
    ("DOL-1818", "Dolly 18x18", 2, [(1020, 0.25), (2013, 4), (3040, 8), (3012, 4), (5030, 1)]),
    ("SHF-1848-4T", "Wire shelving 18x48 four tier", 3, [(1050, 4), (2030, 4), (2040, 16), (2021, 4), (5011, 1), (5030, 1)]),
    ("SHF-2448-4T", "Wire shelving 24x48 four tier", 3, [(1050, 4), (2031, 4), (2040, 16), (2021, 4), (5011, 1), (5030, 1)]),
    ("SHF-1836-5T", "Wire shelving 18x36 five tier", 3, [(1050, 4), (2032, 5), (2040, 20), (2021, 4), (5012, 1), (5030, 1)]),
    ("SHF-2460-4T", "Wire shelving 24x60 four tier", 3, [(1050, 4), (2033, 4), (2040, 16), (2021, 4), (5011, 1), (5030, 1)]),
    ("SHF-DUN-2036", "Dunnage rack 20x36", 3, [(2034, 1), (1020, 0.25), (2022, 4), (3014, 8), (5030, 1)]),
    ("RCK-PAN-20", "Pan rack 20 slot", 3, [(1021, 1), (2100, 20), (2012, 2), (2011, 2), (3012, 8), (3040, 40), (5030, 1)]),
    ("SHF-WALL-36", "Wall shelf 12x36", 3, [(1013, 0.25), (1060, 2), (3014, 4), (5030, 1)]),
]
ORPHAN_PARENT = "SHF-WALL-36"
FRACTIONAL = sorted({n for _, _, _, bom in FINISHED for n, q in bom if q != int(q)})
SHORT_PRODUCT, SHORT_COMPONENT, SHORT_QTY = "CRT-2436-2S", 2010, 24
FLOW_PRODUCT, FLOW_QTY = "SHF-2448-4T", 10
ROLLUP_PRODUCT = "CRT-BUS-3S"
BIG_QTY_PRODUCT, BIG_QTY = "SHF-1848-4T", 120
COMMA_PART = 3010
N_WORK_ORDERS = 84
FIRST_WO = 3101

PART_COLUMNS = ["Part No", "Description", "Type", "UoM", "On Hand", "Unit Cost", "Reorder Point", "Bin"]
BOM_COLUMNS = ["Parent", "Parent Description", "Component", "Component Description", "Qty Per", "UoM"]
WO_COLUMNS = ["WO #", "Product", "Qty", "Line", "Status", "Start Date", "Due Date", "Completed On", "Qty Completed", "Supervisor", "Notes"]


def pn(n: int) -> str:
    return f"{n:06d}"


def fmt_date(d: date, style: int) -> str:
    return [d.isoformat(), f"{d.month}/{d.day}/{d.year}", d.strftime("%d-%b-%y"), f"{d.strftime('%b')} {d.day} {d.year}"][style % 4]


def fmt_cost(v: float, style: int) -> str:
    return [f"${v:,.2f}", f"{v:.2f}", f"{v:g}"][style % 3]


def fmt_qty(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:g}"


def build(seed: int, attempt: int) -> dict:
    rng = random.Random(seed * 1000 + attempt)
    parts = {}
    for num, desc, uom, (clo, chi), (olo, ohi), rop in COMPONENTS:
        cost = round(rng.uniform(clo, chi), 2)
        if num in FRACTIONAL:  # cents divisible by 4, so 0.25 / 0.5 / 0.75 of a unit is still whole cents
            cost = round(round(cost / 0.04) * 0.04, 2)
        on_hand = rng.randint(olo, ohi)
        parts[num] = {"no": pn(num), "desc": desc, "type": "Component", "uom": uom, "on_hand": on_hand, "cost": cost, "rop": rop}
    fg = {}
    for code, desc, line, bom in FINISHED:
        fg[code] = {"no": code, "desc": desc, "type": "Finished good", "uom": "ea", "on_hand": rng.randint(0, 24), "line": line, "bom": bom}
    # availability test: the short component must be short by exactly qty_per x qty - on hand, and nothing else short
    short_bom = dict(fg[SHORT_PRODUCT]["bom"])
    for num, q in fg[SHORT_PRODUCT]["bom"]:
        need = q * SHORT_QTY
        if num == SHORT_COMPONENT:
            parts[num]["on_hand"] = int(need) - rng.choice([6, 8, 10, 12])
        elif parts[num]["on_hand"] < need + 5:
            parts[num]["on_hand"] = int(need) + rng.randint(5, 40)
    # start/complete test: every component stays above its reorder point even after three reruns
    for num, q in fg[FLOW_PRODUCT]["bom"]:
        floor = parts[num]["rop"] + int(3 * q * FLOW_QTY) + 5
        if parts[num]["on_hand"] < floor:
            parts[num]["on_hand"] = floor + rng.randint(0, 30)
    # a handful of components are genuinely low (never ones the checklist's stock tests touch)
    protected = set(dict(fg[FLOW_PRODUCT]["bom"])) | set(dict(fg[SHORT_PRODUCT]["bom"])) | {COMMA_PART}
    for num in rng.sample([n for n in sorted(parts) if n not in protected], 6):
        parts[num]["on_hand"] = max(0, parts[num]["rop"] - rng.randint(1, max(2, parts[num]["rop"] // 2)))
    if SHORT_COMPONENT in dict(fg[FLOW_PRODUCT]["bom"]):
        raise ValueError("flow product uses the short component")

    def unit_cost(code: str) -> float:
        exact = sum(round(parts[n]["cost"] * 100) * q for n, q in fg[code]["bom"])  # in cents
        assert abs(exact - round(exact)) < 1e-6, code
        return round(exact) / 100

    # ---------------- work orders
    products = [f for f in FINISHED if f[0] != ORPHAN_PARENT]
    span_start = date(2026, 3, 2)
    starts = sorted(span_start + timedelta(days=rng.randint(0, (date(2026, 10, 2) - span_start).days)) for _ in range(N_WORK_ORDERS))
    wos = []
    for k, start in enumerate(starts):
        code, _, line, _ = rng.choice(products + [f for f in FINISHED if f[0] == ORPHAN_PARENT] if start < date(2026, 6, 1) else products)
        if code.startswith("SHF") or code.startswith("RCK"):
            qty = rng.randrange(10, 85, 5)
        elif code.startswith("CRT") or code.startswith("DOL"):
            qty = rng.randrange(10, 65, 5)
        else:
            qty = rng.randrange(4, 32, 2)
        due = start + timedelta(days=rng.randint(5, 15))
        r = rng.random()
        if start <= AS_OF - timedelta(days=30):
            status = "Completed" if r < 0.94 else "Cancelled"
        elif start <= AS_OF:
            status = "In Progress" if r < 0.55 else "Completed" if r < 0.8 else "Released"
        else:
            status = "Planned" if r < 0.6 else "Released"
        completed_on = None
        if status == "Completed":
            completed_on = min(AS_OF, due + timedelta(days=rng.choice([-3, -2, -1, -1, 0, 0, 0, 1, 2, 5])))
            if completed_on < start:
                completed_on = start
        wos.append({"no": FIRST_WO + k, "product": code, "qty": qty, "line": line, "status": status, "start": start, "due": due,
                    "completed_on": completed_on, "flag": None})
    big = next((w for w in wos if w["product"] == BIG_QTY_PRODUCT and w["status"] == "Completed"), None)
    if big is None:
        raise ValueError("no completed big shelving order")
    big["qty"] = BIG_QTY
    if sum(1 for w in wos if w["qty"] == BIG_QTY) != 1:
        raise ValueError("qty tie")
    if any(w["product"] == ORPHAN_PARENT and w["status"] not in ("Completed", "Cancelled") for w in wos):
        raise ValueError("orphan product has an open work order")
    planned = [w for w in wos if w["status"] == "Planned"]
    if not planned:
        raise ValueError("no planned")
    bad = rng.choice(planned)
    bad["due"] = bad["start"] - timedelta(days=rng.randint(3, 9))
    bad["flag"] = "due_before_start"

    # ---------------- rows: parts
    part_rows = []
    for num in sorted(parts):
        p = parts[num]
        written = p["no"] if rng.random() < 0.72 else str(num)
        oh = p["on_hand"]
        part_rows.append({"Part No": written, "Description": p["desc"], "Type": rng.choice(["Component", "Component", "Purchased", "Raw"]) if num < 3000 else "Component",
                          "UoM": p["uom"], "On Hand": f"{oh:,}" if oh >= 1000 and rng.random() < 0.7 else str(oh),
                          "Unit Cost": fmt_cost(p["cost"], rng.randrange(3)), "Reorder Point": str(p["rop"]),
                          "Bin": f"{rng.choice('ABCDE')}-{rng.randint(1, 12):02d}", "_key": num, "_role": "unique"})
    for code, desc, line, _ in FINISHED:
        part_rows.append({"Part No": code, "Description": desc, "Type": "Finished good", "UoM": "ea", "On Hand": str(fg[code]["on_hand"]),
                          "Unit Cost": "", "Reorder Point": "", "Bin": f"FG-{line}", "_key": code, "_role": "unique"})
    comma = next(r for r in part_rows if r["_key"] == COMMA_PART)
    comma["On Hand"] = f"{parts[COMMA_PART]['on_hand']:,}"
    # repeated rows: three identical, two repeating a component under its unpadded number
    comp_rows = [r for r in part_rows if isinstance(r["_key"], int) and r["_key"] not in dict(fg[FLOW_PRODUCT]["bom"]) and r["_key"] != SHORT_COMPONENT]
    picks = rng.sample(comp_rows, 5)
    extra = [dict(r, _role="exact_duplicate") for r in picks[:3]]
    for r in picks[3:]:
        other = str(r["_key"]) if r["Part No"] == pn(r["_key"]) else pn(r["_key"])
        extra.append(dict(r, **{"Part No": other}, _role="unpadded_duplicate"))
    part_rows_out = part_rows + extra
    part_rows_out.sort(key=lambda r: (str(r["_key"]) if isinstance(r["_key"], str) else f"{r['_key']:06d}", r["_role"]))

    # ---------------- rows: BOMs
    rollup_component_unpadded = None
    bom_rows = []
    for code, desc, line, bom in FINISHED:
        for num, q in bom:
            written = pn(num) if rng.random() < 0.6 else str(num)
            if code == ROLLUP_PRODUCT and num == 1040:
                written = str(num)
                rollup_component_unpadded = written
            bom_rows.append({"Parent": code, "Parent Description": desc, "Component": written, "Component Description": parts[num]["desc"],
                             "Qty Per": fmt_qty(q) if rng.random() < 0.7 else f"{q:.2f}", "UoM": parts[num]["uom"], "_parent": code, "_num": num, "_role": "unique"})
        if code == ORPHAN_PARENT:
            bom_rows.append({"Parent": code, "Parent Description": desc, "Component": str(ORPHAN[0]), "Component Description": ORPHAN[1],
                             "Qty Per": "2", "UoM": "ea", "_parent": code, "_num": ORPHAN[0], "_role": "orphan"})
    # repeated lines: the roll-up product's bolt line plus three others (never on the flow or short product)
    rep = [next(r for r in bom_rows if r["_parent"] == ROLLUP_PRODUCT and r["_num"] == 3010)]
    others = [r for r in bom_rows if r["_parent"] not in (ROLLUP_PRODUCT, FLOW_PRODUCT, SHORT_PRODUCT, ORPHAN_PARENT) and r["_role"] == "unique"]
    rep += rng.sample(others, 3)
    bom_rows_out = list(bom_rows)
    for r in rep:
        i = bom_rows_out.index(r)
        bom_rows_out.insert(i + 1, dict(r, _role="exact_duplicate"))

    # ---------------- rows: work orders
    wo_rows = []
    for w in wos:
        canon, sup, variants = LINES[w["line"]]
        wo_rows.append({
            "WO #": f"WO-{w['no']}", "Product": w["product"], "Qty": str(w["qty"]),
            "Line": canon if rng.random() < 0.55 else rng.choice(variants),
            "Status": rng.choice({"Completed": ["Completed", "Completed", "Complete", "Closed"], "Cancelled": ["Cancelled", "Void"],
                                  "In Progress": ["In Progress", "WIP"], "Released": ["Released", "Rel."], "Planned": ["Planned", "planned"]}[w["status"]]),
            "Start Date": fmt_date(w["start"], rng.randrange(4)), "Due Date": fmt_date(w["due"], rng.randrange(4)),
            "Completed On": fmt_date(w["completed_on"], rng.randrange(4)) if w["completed_on"] else "",
            "Qty Completed": str(w["qty"]) if w["status"] == "Completed" else "0", "Supervisor": sup,
            "Notes": rng.choice(["", "", "", "", "rush", "customer pickup", "weld rework on 2 units", "short on cartons - substituted", "split from larger order"]),
            "_wo": w, "_role": "unique"})
    in_prog = [r for r in wo_rows if r["_wo"]["status"] == "In Progress"]
    done = [r for r in wo_rows if r["_wo"]["status"] == "Completed" and r["_wo"] is not big]
    if not in_prog:
        raise ValueError("nothing in progress")
    dup_ip = rng.choice(in_prog)
    dup_done = rng.choice(done)
    unpref = rng.choice([r for r in done if r is not dup_done])
    wo_rows_out = list(wo_rows)
    for r, role, override in ((dup_ip, "exact_duplicate", {}), (dup_done, "exact_duplicate", {}), (unpref, "unprefixed_number", {"WO #": str(unpref["_wo"]["no"])})):
        wo_rows_out.insert(rng.randint(0, len(wo_rows_out)), dict(r, **override, _role=role))
    return {"parts": parts, "fg": fg, "wos": wos, "part_rows": part_rows_out, "bom_rows": bom_rows_out, "wo_rows": wo_rows_out,
            "big": big, "bad": bad, "unit_cost": {c: unit_cost(c) for c in fg}, "dups": (dup_ip, dup_done, unpref)}


def summarize(t: dict) -> dict:
    parts, fg, wos = t["parts"], t["fg"], t["wos"]
    uc = t["unit_cost"]
    OPEN = ("Planned", "Released", "In Progress")
    open_w = [w for w in wos if w["status"] in OPEN]
    ip = [w for w in wos if w["status"] == "In Progress"]
    wip = round(sum(w["qty"] * uc[w["product"]] for w in ip), 2)
    below = sorted(p["no"] for p in parts.values() if p["on_hand"] < p["rop"])
    line2 = [w for w in wos if w["line"] == RESTRICTED_LINE]
    oos = sorted((w for w in open_w if w["line"] == TEST_LINE), key=lambda w: w["no"])[0]
    # search: a product code that is no other code's substring, with a repeated row among its orders if possible
    codes = sorted(fg)
    search = None
    for c in codes:
        n = sum(1 for w in wos if w["product"] == c)
        if any(c != o and c in o for o in codes) or not 3 <= n <= 6:
            continue
        if any(r["_role"] != "unique" and r["_wo"]["product"] == c for r in t["wo_rows"]):
            search = (c, n)
            break
    if search is None:
        raise ValueError("no search product")
    line3 = sum(1 for w in wos if w["line"] == 3)
    uniq_rows = [r for r in t["wo_rows"] if r["_role"] == "unique"]
    text_top = max(uniq_rows, key=lambda r: r["Qty"])
    if text_top["_wo"] is t["big"]:
        raise ValueError("text sort would pass")
    dup_ip, dup_done, unpref = t["dups"]
    naive_wip = round(wip + dup_ip["_wo"]["qty"] * uc[dup_ip["_wo"]["product"]], 2)
    if abs(naive_wip - wip) < 1:
        raise ValueError("naive wip too close")
    flow = fg[FLOW_PRODUCT]
    short = fg[SHORT_PRODUCT]
    rollup_rows = [r for r in t["bom_rows"] if r["_parent"] == ROLLUP_PRODUCT]
    orphan_rows = [r for r in t["bom_rows"] if r["_role"] == "orphan"]
    bad = t["bad"]
    bad_row = next(r for r in t["wo_rows"] if r["_wo"] is bad and r["_role"] == "unique")
    aug = [w for w in wos if w["status"] == "Completed" and w["completed_on"].year == 2026 and w["completed_on"].month == 8]
    done_all = [w for w in wos if w["status"] == "Completed"]
    on_time = [w for w in done_all if w["completed_on"] <= w["due"]]
    rate = 100 * len(on_time) / len(done_all)
    done_l2 = [w for w in done_all if w["line"] == RESTRICTED_LINE]
    on_time_l2 = [w for w in done_l2 if w["completed_on"] <= w["due"]]
    rate_l2 = 100 * len(on_time_l2) / len(done_l2)
    if abs(rate_l2 * 10 - round(rate_l2 * 10)) > 0.42:
        raise ValueError("line on-time rate near a rounding edge")
    if abs(rate * 10 - round(rate * 10)) > 0.42:
        raise ValueError("on-time rate near a rounding edge")
    comp_rows = [r for r in t["part_rows"] if r["_role"] == "unique" and isinstance(r["_key"], int)]
    unpadded_written = sum(1 for r in comp_rows if not r["Part No"].startswith("00"))
    status_counts = {s: sum(1 for w in wos if w["status"] == s) for s in ("Planned", "Released", "In Progress", "Completed", "Cancelled")}
    for s in ("Planned", "Released", "In Progress"):
        if status_counts[s] < (7 if s == "In Progress" else 4):
            raise ValueError("thin status")
    rep_bom = [r for r in t["bom_rows"] if r["_role"] == "exact_duplicate"]
    rollup_bolt_rows = sum(1 for r in t["bom_rows"] if r["_parent"] == ROLLUP_PRODUCT and r["_num"] == 3010)

    counts = {
        "baseline": {
            "STAFF_ROLE": "Line supervisor",
            "VIEWER_ROLE": "Read-only (the accountant)",
            "MAIN_ENTITY": "work order",
            "MAIN_ENTITY_PLURAL": "work orders",
            "restricted_user": LINES[RESTRICTED_LINE][1],
            "restricted_line": LINES[RESTRICTED_LINE][0],
            "SCOPE_COUNT": len(line2),
            "OUT_OF_SCOPE_EXAMPLE": {"work_order": f"WO-{oos['no']}", "line": LINES[oos["line"]][0], "product": oos["product"], "status": oos["status"]},
            "KPI_1": {"name": "open work orders", "value": len(open_w), "scoped_value": sum(1 for w in open_w if w["line"] == RESTRICTED_LINE),
                      "definition": "Planned, Released, or In Progress"},
            "KPI_2": {"name": "work orders in progress", "value": len(ip)},
            "KPI_3": {"name": "WIP value", "value": wip, "definition": "sum over in-progress work orders of quantity x the product's BOM material cost",
                      "naive_counting_repeated_row": naive_wip},
            "KPI_4": {"name": "parts below reorder point", "value": len(below), "parts": below},
            "SEARCH_TERM": search[0], "SEARCH_COUNT": search[1],
            "FILTER_FIELD": "line", "FILTER_VALUE": LINES[3][0], "FILTER_COUNT": line3,
            "SORT_FIELD": "quantity", "SORT_TOP": {"work_order": f"WO-{t['big']['no']}", "qty": BIG_QTY, "product": BIG_QTY_PRODUCT},
            "text_sort_top_would_be": {"work_order": f"WO-{text_top['_wo']['no']}", "file_value": text_top["Qty"]},
            "EXPORT_ROWS": len(wos),
            "EXPORT_COLUMNS": ["work order number", "product", "quantity", "line", "status", "due date"],
            "REQUIRED_FIELD": "a product",
            "test_line": LINES[TEST_LINE][0],
        },
        "parts": {
            "file_rows_excluding_header": len(t["part_rows"]),
            "exact_duplicate_rows": 3,
            "unpadded_number_duplicate_rows": 2,
            "unique_parts": len(parts) + len(fg),
            "components": len(parts),
            "finished_goods": len(fg),
            "duplicate_rows": [{"written_as": r["Part No"], "part": pn(r["_key"]), "kind": r["_role"]} for r in t["part_rows"] if r["_role"] != "unique"],
            "component_rows_written_without_leading_zeros": unpadded_written,
            "unpadded_example": {"written_as": "1021", "part": pn(1021)},
            "comma_quantity_example": {"part": pn(COMMA_PART), "description": parts[COMMA_PART]["desc"], "file_value": f"{parts[COMMA_PART]['on_hand']:,}",
                                       "on_hand": parts[COMMA_PART]["on_hand"],
                                       "naive_misreadings": [parts[COMMA_PART]["on_hand"] // 1000, parts[COMMA_PART]["on_hand"] / 1000]},
            "below_reorder_point": below,
        },
        "boms": {
            "file_rows_excluding_header": len(t["bom_rows"]),
            "exact_duplicate_lines": len(rep_bom),
            "orphan_lines": len(orphan_rows),
            "unique_component_lines": sum(len(f[3]) for f in FINISHED),
            "finished_goods_with_bom": len(FINISHED),
            "repeated_lines": [{"parent": r["_parent"], "component": pn(r["_num"]), "written_as": r["Component"]} for r in rep_bom],
            "rollup_product": {"code": ROLLUP_PRODUCT, "components": len(fg[ROLLUP_PRODUCT]["bom"]),
                               "lines": [{"component": pn(n), "description": parts[n]["desc"], "qty_per": q, "unit_cost": parts[n]["cost"],
                                          "written_as": next(r["Component"] for r in rollup_rows if r["_num"] == n)} for n, q in fg[ROLLUP_PRODUCT]["bom"]],
                               "bolt_line_rows_in_file": rollup_bolt_rows,
                               "unit_material_cost": uc[ROLLUP_PRODUCT],
                               "naive_unit_material_cost_counting_repeated_line": round(uc[ROLLUP_PRODUCT] + 24 * parts[3010]["cost"], 2)},
            "orphan": {"parent": ORPHAN_PARENT, "component_as_written": str(ORPHAN[0]), "component_padded": pn(ORPHAN[0]), "description": ORPHAN[1],
                       "bom_lines_without_it": len(fg[ORPHAN_PARENT]["bom"])},
        },
        "work_orders": {
            "file_rows_excluding_header": len(t["wo_rows"]),
            "unique_work_orders": len(wos),
            "duplicate_rows": [{"written_as": r["WO #"], "work_order": f"WO-{r['_wo']['no']}", "status": r["_wo"]["status"], "kind": r["_role"]}
                               for r in t["wo_rows"] if r["_role"] != "unique"],
            "by_status": status_counts,
            "status_words": {"Completed": ["Completed", "Complete", "Closed"], "Cancelled": ["Cancelled", "Void"], "In Progress": ["In Progress", "WIP"],
                             "Released": ["Released", "Rel."], "Planned": ["Planned", "planned"]},
            "by_line": {LINES[k][0]: sum(1 for w in wos if w["line"] == k) for k in LINES},
            "line_words": {LINES[k][0]: LINES[k][2] for k in LINES},
            "impossible_dates": {"work_order": f"WO-{bad['no']}", "product": bad["product"], "start": bad["start"].isoformat(), "due": bad["due"].isoformat(),
                                 "file_values": {"Start Date": bad_row["Start Date"], "Due Date": bad_row["Due Date"]}},
        },
        "tests": {
            "availability": {"product": SHORT_PRODUCT, "line": LINES[short["line"]][0], "qty": SHORT_QTY, "component": pn(SHORT_COMPONENT),
                             "component_description": parts[SHORT_COMPONENT]["desc"], "qty_per": dict(short["bom"])[SHORT_COMPONENT],
                             "needed": int(dict(short["bom"])[SHORT_COMPONENT] * SHORT_QTY), "on_hand": parts[SHORT_COMPONENT]["on_hand"],
                             "short_by": int(dict(short["bom"])[SHORT_COMPONENT] * SHORT_QTY) - parts[SHORT_COMPONENT]["on_hand"],
                             "other_components_sufficient": True},
            "flow": {"product": FLOW_PRODUCT, "line": LINES[flow["line"]][0], "qty": FLOW_QTY, "finished_on_hand_before": flow["on_hand"],
                     "finished_on_hand_after": flow["on_hand"] + FLOW_QTY,
                     "components": [{"component": pn(n), "description": parts[n]["desc"], "qty_per": q, "issued": int(q * FLOW_QTY),
                                     "before": parts[n]["on_hand"], "after": parts[n]["on_hand"] - int(q * FLOW_QTY), "reorder_point": parts[n]["rop"]}
                                    for n, q in flow["bom"]],
                     "unit_material_cost": uc[FLOW_PRODUCT], "wip_increase": round(FLOW_QTY * uc[FLOW_PRODUCT], 2),
                     "wip_during": round(wip + FLOW_QTY * uc[FLOW_PRODUCT], 2)},
        },
        "changes": {
            "c1_august_2026_units_completed_by_line": {LINES[k][0]: sum(w["qty"] for w in aug if w["line"] == k) for k in LINES},
            "c1_august_2026_material_cost_by_line": {LINES[k][0]: round(sum(w["qty"] * uc[w["product"]] for w in aug if w["line"] == k), 2) for k in LINES},
            "c1_august_2026_work_orders_completed": len(aug),
            "c1_on_time": {"completed": len(done_all), "on_time": len(on_time), "rate_percent": round(rate, 1),
                           "rule": "Completed On on or before Due Date"},
            "c1_on_time_restricted_line": {"completed": len(done_l2), "on_time": len(on_time_l2), "rate_percent": round(rate_l2, 1)},
            "c1_on_time_bounds_percent": [round(rate - 0.1, 1), round(rate + 0.1, 1)],
            "c1_on_time_restricted_bounds_percent": [round(rate_l2 - 0.1, 1), round(rate_l2 + 0.1, 1)],
            "c2_purchase_request_test": {"part": "QA-BOLT", "on_hand": 50, "reorder_point": 40, "unit_cost": 0.10, "qty_per_kit": 4,
                                         "first_order_qty": 5, "on_hand_after_first": 50 - 4 * 5, "request_qty": 2 * 40 - (50 - 4 * 5),
                                         "second_order_qty": 2, "on_hand_after_second": 50 - 4 * 5 - 4 * 2,
                                         "request_qty_if_updated": 2 * 40 - (50 - 4 * 7),
                                         "on_hand_after_receipt": [50 - 4 * 7 + 2 * 40 - (50 - 4 * 5), 50 - 4 * 7 + 2 * 40 - (50 - 4 * 7)]},
            "c3_quality_check_test": {"qty": FLOW_QTY, "good": 9, "scrap": 1},
            "c1_naive_august_units_with_repeated_rows": {LINES[k][0]: sum(w["qty"] for w in aug if w["line"] == k) + sum(
                r["_wo"]["qty"] for r in t["wo_rows"] if r["_role"] != "unique" and r["_wo"] in aug and r["_wo"]["line"] == k) for k in LINES},
        },
    }
    return counts


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    seed = ap.parse_args().seed
    last = None
    for attempt in range(300):
        try:
            truth = build(seed, attempt)
            counts = summarize(truth)
            break
        except (ValueError, StopIteration) as e:
            last = e
    else:
        raise SystemExit(f"no valid draw: {last}")
    counts = {"seed": seed, "attempt": attempt, **counts}
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "parts.csv"), PART_COLUMNS, [[r[c] for c in PART_COLUMNS] for r in truth["part_rows"]])
    write_csv(os.path.join(SEED_DIR, "boms.csv"), BOM_COLUMNS, [[r[c] for c in BOM_COLUMNS] for r in truth["bom_rows"]])
    write_csv(os.path.join(SEED_DIR, "work_orders.csv"), WO_COLUMNS, [[r[c] for c in WO_COLUMNS] for r in truth["wo_rows"]], bom=True)
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(counts, indent=2) + "\n")
    b = counts["baseline"]
    print(f"parts {counts['parts']['file_rows_excluding_header']} -> {counts['parts']['unique_parts']}; bom lines "
          f"{counts['boms']['file_rows_excluding_header']} -> {counts['boms']['unique_component_lines']}; work orders "
          f"{counts['work_orders']['file_rows_excluding_header']} -> {counts['work_orders']['unique_work_orders']}; "
          f"open {b['KPI_1']['value']}, WIP {b['KPI_3']['value']:,.2f}; attempt {attempt}")


if __name__ == "__main__":
    main()
