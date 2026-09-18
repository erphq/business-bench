#!/usr/bin/env python3
"""inventory-valuation: a garden center's stock-on-hand export and purchasing cost sheet to a valuation by department.

    python gen.py [--seed N]

Business: Quarry Road Nursery & Garden Center. The accountant needs stock at cost as of 30 September. The till
knows what is on hand; purchasing keeps a sheet of every receipt with what was paid, typed by hand.

Traps (each caught by a check, see task.yaml):
  * the cost sheet has one row per receipt; the most recent receipt's cost is the one to use, and a first-match
    lookup takes the oldest                                         (checks: Trees value; total stock value)
  * costs are typed as text ("$1,249.00", "14.25 ea", "12.5"); a numeric read drops the comma and "ea" rows
                                                                    (checks: Trees value; total stock value)
  * negative on-hand counts are till sales rung before receiving and count as zero (check: Shrubs value)
  * purchasing typed some SKUs in lower case or with a trailing space, so an exact lookup misses them
                                                                    (check: Pots & Planters value)
  * five stocked items have no usable cost (never received, TBD, n/a); they are listed and flagged, not valued
    and not guessed from the retail price                          (checks: items without a cost flagged; total stock value)
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# department, sku prefix, [(item, base cost)]
CATALOG = [
    ("Perennials", "PER", [("Echinacea 'Magnus' 1 gal", 4.10), ("Hosta 'Patriot' 2 gal", 7.85), ("Black-eyed Susan 1 gal", 3.60),
                           ("Lavender 'Hidcote' 1 gal", 4.75), ("Salvia 'May Night' 1 gal", 3.95), ("Coral Bells 1 gal", 5.20),
                           ("Daylily 'Stella de Oro' 1 gal", 3.40), ("Russian Sage 2 gal", 7.10), ("Sedum 'Autumn Joy' 1 gal", 3.85),
                           ("Hellebore 2 gal", 9.60), ("Catmint 'Walker's Low' 1 gal", 4.05), ("Astilbe 1 gal", 4.30)]),
    ("Shrubs", "SHR", [("Hydrangea 'Limelight' 3 gal", 18.50), ("Boxwood 'Green Velvet' 3 gal", 14.20), ("Lilac 5 gal", 24.75),
                       ("Spirea 'Goldflame' 2 gal", 9.80), ("Ninebark 'Diabolo' 3 gal", 16.40), ("Azalea 'Encore' 3 gal", 19.90),
                       ("Rhododendron 5 gal", 27.30), ("Viburnum 5 gal", 23.10), ("Arborvitae 'Emerald Green' 5 gal", 21.60),
                       ("Forsythia 3 gal", 12.40)]),
    ("Trees", "TRE", [("Japanese Maple 'Bloodgood' 7 gal", 84.00), ("Serviceberry 10 gal", 118.00), ("Eastern Redbud 15 gal", 162.00),
                      ("River Birch B&B 2 in", 238.00), ("Honeycrisp Apple 5 gal", 37.50), ("Dwarf Alberta Spruce 5 gal", 42.00),
                      ("Kousa Dogwood 15 gal", 171.00), ("Sugar Maple B&B 3 in", 1249.00), ("Weeping Cherry 15 gal", 189.00)]),
    ("Houseplants", "HOU", [("Monstera 10 in", 22.40), ("Fiddle Leaf Fig 14 in", 48.00), ("Snake Plant 6 in", 7.90), ("Pothos 6 in hanging", 6.30),
                            ("ZZ Plant 8 in", 14.80), ("Peace Lily 8 in", 11.20), ("Bird of Paradise 14 in", 52.50), ("Calathea 6 in", 9.10)]),
    ("Pots & Planters", "POT", [("Glazed pot 14 in cobalt", 21.00), ("Terracotta pot 10 in", 4.60), ("Fiberglass planter 24 in", 68.00),
                                ("Self-watering planter 12 in", 17.40), ("Coco liner hanging basket 14 in", 8.90), ("Cedar window box 30 in", 36.50),
                                ("Glazed pot 18 in celadon", 38.00)]),
    ("Soil & Mulch", "SOI", [("Potting mix 2 cu ft", 8.40), ("Garden soil 1 cu ft", 3.90), ("Hardwood mulch 2 cu ft", 3.20), ("Compost 1 cu ft", 4.50),
                             ("Perlite 8 qt", 5.60), ("Cedar mulch 2 cu ft", 4.80)]),
    ("Tools", "TOL", [("Felco F-2 pruner", 38.00), ("Hori hori knife", 16.50), ("Nitrile garden gloves M", 4.20), ("Galvanized watering can 2 gal", 19.00),
                      ("8-pattern hose nozzle", 7.40), ("Bypass loppers 28 in", 27.90)]),
]
DEPTS = [c[0] for c in CATALOG]
VENDORS = {"Perennials": "Walters Gardens", "Shrubs": "Monrovia", "Trees": "Bailey Nurseries", "Houseplants": "Costa Farms",
           "Pots & Planters": "Campania International", "Soil & Mulch": "Espoma", "Tools": "Gardener's Supply Wholesale"}


def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    for dept, prefix, lst in CATALOG:
        nums = sorted(r.sample(range(10, 900), len(lst)))
        for (name, base), n in zip(lst, nums):
            big = base >= 80
            qty = r.randint(0, 18) if big else r.randint(0, 110)
            items.append({"sku": f"{prefix}-{n:04d}", "name": name, "dept": dept, "qty": qty, "base": base,
                          "retail": round(base * r.uniform(1.9, 2.4), 2)})
    by_dept = {dp: [it for it in items if it["dept"] == dp] for dp in DEPTS}

    # receipts: 1-3 per item across the year, cost drifting between receipts
    receipts = []
    for it in items:
        k = r.choices([1, 2, 3], weights=[4, 4, 2])[0]
        ds = sorted(date(2026, 1, 5) + timedelta(days=r.randint(0, 260)) for _ in range(k))
        cost = it["base"] * r.uniform(0.92, 0.98)
        for d in ds:
            receipts.append({"sku": it["sku"], "date": d, "cost": round(cost, 2), "qty": r.randint(6, 48), "style": "num", "sku_typed": it["sku"]})
            cost *= r.uniform(1.03, 1.12)
    # the Sugar Maple and two more trees have several receipts with a clear price rise
    for it in by_dept["Trees"]:
        if it["name"].startswith("Sugar Maple") or it["name"].startswith("Kousa") or it["name"].startswith("River Birch"):
            receipts = [x for x in receipts if x["sku"] != it["sku"]]
            c0 = it["base"] * 0.9
            for d, c in ((date(2026, 3, 12), c0), (date(2026, 5, 20), c0 * 1.06), (date(2026, 8, 28), c0 * 1.14)):
                receipts.append({"sku": it["sku"], "date": d, "cost": round(c, 2), "qty": r.randint(2, 6), "style": "num", "sku_typed": it["sku"]})
            it["qty"] = max(it["qty"], 4)

    # negative on-hand: two shrubs, one houseplant, one soil line
    for dp, n in (("Shrubs", 2), ("Houseplants", 1), ("Soil & Mulch", 1)):
        for it in r.sample(by_dept[dp], n):
            it["qty"] = -r.randint(2, 9)
    # items without a usable cost
    no_cost = []
    for dp, kind in (("Perennials", "none"), ("Perennials", "none"), ("Houseplants", "TBD"), ("Tools", "n/a"), ("Trees", "blank")):
        cands = [it for it in by_dept[dp] if it not in no_cost and it["qty"] > 0 and not it["name"].startswith(("Sugar Maple", "Kousa", "River Birch"))]
        it = r.choice(cands)
        no_cost.append(it)
        receipts = [x for x in receipts if x["sku"] != it["sku"]]
        if kind != "none":
            receipts.append({"sku": it["sku"], "date": date(2026, 9, r.randint(8, 26)), "cost": None, "qty": r.randint(3, 12),
                             "style": kind, "sku_typed": it["sku"]})
        it["missing"] = kind
    # purchasing typed some SKUs loosely: three in Pots & Planters, two elsewhere
    loose = r.sample([it for it in by_dept["Pots & Planters"] if it["qty"] > 5], 3) + \
        r.sample([it for it in items if it["dept"] in ("Tools", "Soil & Mulch") and it not in no_cost], 2)
    for it in loose:
        for x in receipts:
            if x["sku"] == it["sku"]:
                x["sku_typed"] = it["sku"].lower() if r.random() < 0.5 else it["sku"] + " "
    # text styles for costs
    for x in receipts:
        if x["cost"] is None:
            continue
        x["style"] = r.choices(["dollar", "plain", "short", "ea"], weights=[4, 3, 2, 1])[0]
    receipts.sort(key=lambda x: (x["sku"], x["date"]))

    # ---- truth ----
    latest = {}
    first = {}
    for x in receipts:
        if x["cost"] is None:
            continue
        latest[x["sku"]] = x["cost"]
        first.setdefault(x["sku"], x["cost"])
    for it in items:
        it["cost"] = latest.get(it["sku"])
        it["valued_qty"] = max(it["qty"], 0)
        it["value"] = round(it["valued_qty"] * it["cost"], 2) if it["cost"] is not None else 0.0
    dept_val = {dp: round(sum(it["value"] for it in by_dept[dp]), 2) for dp in DEPTS}
    grand = round(sum(dept_val.values()), 2)
    loose_skus = {it["sku"] for it in loose}
    naive = {
        "first_cost": {dp: round(sum(max(it["qty"], 0) * first[it["sku"]] for it in by_dept[dp] if it["sku"] in first), 2) for dp in DEPTS},
        "negative": {dp: round(sum(it["qty"] * it["cost"] for it in by_dept[dp] if it["cost"] is not None), 2) for dp in DEPTS},
        "exact_lookup": {dp: round(sum(it["value"] for it in by_dept[dp] if it["sku"] not in loose_skus), 2) for dp in DEPTS},
        "retail_guess": round(grand + sum(max(it["qty"], 0) * it["retail"] for it in no_cost), 2),
    }
    return {"items": items, "receipts": receipts, "dept_val": dept_val, "grand": grand, "no_cost": no_cost, "naive": naive,
            "loose": sorted(loose_skus), "by_dept": by_dept}


def acceptable(d: dict) -> bool:
    dv, nv = d["dept_val"], d["naive"]
    if abs(dv["Trees"] - nv["first_cost"]["Trees"]) < 0.04 * dv["Trees"]:
        return False
    if abs(dv["Shrubs"] - nv["negative"]["Shrubs"]) < 0.04 * dv["Shrubs"]:
        return False
    if abs(dv["Pots & Planters"] - nv["exact_lookup"]["Pots & Planters"]) < 0.08 * dv["Pots & Planters"]:
        return False
    vals = list(dv.values()) + [d["grand"]]
    if any(abs(a - b) <= 0.02 * a for i, a in enumerate(vals) for j, b in enumerate(vals) if i != j):
        return False
    sugar = next(it for it in d["items"] if it["name"].startswith("Sugar Maple"))
    return sugar["qty"] >= 4 and all(it["qty"] > 0 for it in d["no_cost"])


# --------------------------------------------------------------------------- deliverables

def cost_text(x: dict) -> str:
    c = x["cost"]
    if x["style"] == "TBD": return "TBD"
    if x["style"] == "n/a": return "n/a"
    if x["style"] == "blank": return ""
    return {"dollar": f"${c:,.2f}", "plain": f"{c:,.2f}", "short": f"{c:g}", "ea": f"{c:.2f} ea"}[x["style"]]


def valuation_sheets(d: dict) -> dict:
    items = sorted(d["items"], key=lambda it: (DEPTS.index(it["dept"]), it["sku"]))
    rows = []
    for i, it in enumerate(items, start=2):
        rows.append([it["sku"], it["name"], it["dept"], it["qty"], f"=MAX(D{i},0)", it["cost"] if it["cost"] is not None else None,
                     f'=IF(F{i}="",0,ROUND(E{i}*F{i},2))', f'=IF(F{i}="","No cost on file - not valued","")'])
    n = len(items) + 1
    summ = []
    for i, dp in enumerate(DEPTS, start=2):
        summ.append([dp, f"=COUNTIF(Items!$C$2:$C${n},A{i})", f"=SUMIF(Items!$C$2:$C${n},A{i},Items!$E$2:$E${n})",
                     f"=SUMIF(Items!$C$2:$C${n},A{i},Items!$G$2:$G${n})"])
    last = len(DEPTS) + 1
    summ.append(["Total stock value", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})"])
    summ.append([])
    summ.append(["Items with no cost on file (listed on Items, left out of the totals)"])
    for it in sorted(d["no_cost"], key=lambda x: x["sku"]):
        summ.append([it["sku"], it["name"], it["dept"], "No cost on file - chase with purchasing"])
    summ.append([])
    summ.append(["Negative on-hand counts are valued at zero. Cost is the most recent receipt on the purchasing sheet."])
    return {"Valuation": {"header": ["Department", "Items", "Units valued", "Value at cost"], "rows": summ,
                          "widths": {"A": 34, "B": 30, "C": 16, "D": 40}},
            "Items": {"header": ["SKU", "Item", "Department", "On hand", "Units valued", "Latest cost", "Value", "Flag"], "rows": rows,
                      "widths": {"B": 34, "C": 16, "H": 30}}}



def cent_tolerant(spec: dict) -> dict:
    """Figures computed from exact source data tie to the cent: every workbook pin gets a tolerance under 1.00."""
    for c in spec["checks"]:
        if c["type"] == "xlsx_value_present" and not c.get("rounding"):
            exp = abs(float(c["expected"]))
            c["rel_tol"] = min(float(c.get("rel_tol", 0.005)), float(f"{0.9 / max(exp, 1.0):.2g}"))
    return spec


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)

    # ---- workspace ----
    pos_items = sorted(d["items"], key=lambda it: it["sku"])
    write_csv(os.path.join(ws, "stock_on_hand_2026-09-30.csv"), ["SKU", "Description", "Department", "On Hand", "Retail Price"],
              [[it["sku"], it["name"], it["dept"], it["qty"], f"{it['retail']:.2f}"] for it in pos_items],
              preamble=["Quarry Road Nursery - Inventory On Hand", "As of 09/30/2026 11:58 PM"], bom=True)
    write_xlsx(os.path.join(ws, "purchasing_receipts_2026.xlsx"), {"Receipts": {
        "merged_title": "Receipts log 2026 - costs as invoiced",
        "preamble": [["Typed from supplier invoices. Most recent line is current cost."]],
        "header": ["Received", "SKU", "Supplier", "Qty", "Unit cost", "Notes"],
        "rows": [[x["date"], x["sku_typed"], VENDORS[next(it["dept"] for it in d["items"] if it["sku"] == x["sku"])], x["qty"], cost_text(x),
                  "price not on invoice" if x["style"] in ("TBD", "blank") else ("consignment - ask Rosa" if x["style"] == "n/a" else "")]
                 for x in sorted(d["receipts"], key=lambda x: (x["date"], x["sku"]))],
        "widths": {"A": 12, "B": 12, "C": 28, "E": 12, "F": 26}}}, creator="Purchasing")
    write_text(os.path.join(ws, "note_from_frank.txt"),
               "Our accountant needs the stock valued at cost as of 30 September, by department, with a grand total.\n\n"
               "Count is the till's on-hand report. Cost is what we last paid - Rosa logs every delivery on the receipts\n"
               "sheet, so the latest line for an item is its cost now.\n\n"
               "The till goes negative when we sell something before the delivery is checked in. Those are really zero, don't\n"
               "let them knock the value down.\n\n"
               "If we have no cost for something, do not guess one. List those items on the sheet, flagged, so Rosa can chase\n"
               "the invoices, and leave them out of the totals.\n\n"
               "Frank\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "valuation_by_item.csv"), ["sku", "department", "on_hand", "units_valued", "latest_cost", "value"],
              [[it["sku"], it["dept"], it["qty"], it["valued_qty"], "" if it["cost"] is None else f"{it['cost']:.2f}", f"{it['value']:.2f}"]
               for it in pos_items])
    write_json(os.path.join(ref, "notes.json"), {
        "department_values": d["dept_val"], "grand_total": d["grand"],
        "no_cost_skus": sorted(it["sku"] for it in d["no_cost"]),
        "no_cost_detail": {it["sku"]: it["missing"] for it in d["no_cost"]},
        "negative_on_hand": sorted(it["sku"] for it in d["items"] if it["qty"] < 0), "loosely_typed_skus": d["loose"],
        "naive": d["naive"]})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "valuation.xlsx"), valuation_sheets(d), creator="reference")

    dv = d["dept_val"]
    write_task_yaml(HERE, cent_tolerant({
        "id": "inventory-valuation", "track": "desk", "category": "spreadsheet",
        "title": "Stock valued at cost by department for the accountant",
        "ask": ("Frank needs our stock valued at cost by department as of 30 September for the accountant. Save it as valuation.xlsx "
                "with live formulas - his note explains the counts and the costs.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the receipts sheet has one line per delivery and costs rose through the year; the latest line is current cost, while a "
            "VLOOKUP or first-match join takes the oldest, which undervalues the trees most (checks: Trees value; total stock value)",
            "unit costs are typed text in four styles ('$1,249.00', '1,249.00', '84', '14.25 ea'); a numeric read loses the comma "
            "and 'ea' rows (checks: Trees value; total stock value)",
            "four items show negative on-hand counts, two of them shrubs; they are valued at zero, not netted against the rest "
            "(check: Shrubs value)",
            "purchasing typed five SKUs in lower case or with a trailing space, three of them pots, so an exact lookup finds no cost "
            "for stocked items (check: Pots & Planters value)",
            "five stocked items have no usable cost (two never received, one TBD, one n/a consignment, one blank); they must be listed "
            "and flagged and left out of the totals rather than guessed at retail (checks: items without a cost are flagged; total "
            "stock value)",
            "the on-hand export carries a two-line preamble and a BOM, and the receipts sheet a merged title and an instruction row "
            "(check: total stock value)",
        ],
        "checks": [
            {"type": "file_exists", "name": "valuation.xlsx exists", "path": "valuation.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "valuation.xlsx", "min_count": 20},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "valuation.xlsx"},
            {"type": "xlsx_value_present", "name": "Trees value (latest receipt cost)", "path": "valuation.xlsx",
             "expected": dv["Trees"], "rel_tol": 0.003, "near_text": "trees"},
            {"type": "xlsx_value_present", "name": "Shrubs value (negative counts at zero)", "path": "valuation.xlsx",
             "expected": dv["Shrubs"], "rel_tol": 0.003, "near_text": "shrubs"},
            {"type": "xlsx_value_present", "name": "Pots & Planters value (loosely typed SKUs)", "path": "valuation.xlsx",
             "expected": dv["Pots & Planters"], "rel_tol": 0.003, "near_text": "pots"},
            {"type": "xlsx_value_present", "name": "total stock value", "path": "valuation.xlsx",
             "expected": d["grand"], "rel_tol": 0.003, "near_text": "total"},
            {"type": "custom", "name": "items without a cost are flagged", "module": "check.py"},
        ],
    }))
    print(f"seed={seed} items={len(d['items'])} receipts={len(d['receipts'])}")
    print("  dept values", dv, "grand", d["grand"])
    print("  naive", d["naive"])
    print("  no cost", [(it["sku"], it["missing"]) for it in d["no_cost"]], "loose", d["loose"])


if __name__ == "__main__":
    s = argparse_seed()
    for attempt in range(800):
        if acceptable(build(s * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 800 attempts")
    emit(s * 1000 + attempt)
