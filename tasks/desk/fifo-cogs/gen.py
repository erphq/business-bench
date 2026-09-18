#!/usr/bin/env python3
"""fifo-cogs: a pet supply store's first-half receipts, till sales and returns to FIFO cost of goods sold by month.

    python gen.py [--seed N] [--naive DIR]

Business: Barkwell Pet Supply, one shop, seven lines that matter to the CPA. Last year's closing FIFO layers come from
the CPA's file, receipts from the receiving log (two lines bought by the case), sales and returns from the till export.
The CPA's email carries the rules: FIFO from the oldest layer, receipts and restocked returns are available for the
day's sales, a return put back on the shelf re-enters at the cost it went out at and comes off COGS that month, a
damaged return is thrown away and changes nothing.

Traps (each caught by a check, see task.yaml):
  * layers run across months, starting with last year's closing layers           (checks: dog food COGS; total COGS)
  * a restocked return comes back at the cost it went out at, as a new layer      (check: cat food COGS)
  * a damaged return is not restocked and leaves COGS alone                        (check: litter COGS)
  * two lines are received by the case; cost per case over the pack size           (check: tug toy COGS)
  * a supplier price list gives 2026 list prices, not what was paid               (check: total COGS)
  * a July receipt and a backordered line sit in the receiving log                (check: dog food on hand at June 30)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from openpyxl.utils import get_column_letter  # noqa: E402

MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]
# sku, description, pack size (1 = each), base unit cost (cents), shelf price (cents), supplier
PRODUCTS = [
    ("DOG-SR25", "Summit Ridge grain-free dog food 25 lb", 1, 4280, 7499, "Heartland Pet Distributors"),
    ("CAT-WF12", "Whisker Farm indoor cat food 12 lb", 1, 2140, 3799, "Heartland Pet Distributors"),
    ("LIT-CC35", "Clumping clay litter 35 lb", 1, 1195, 2199, "Prairie Supply Co"),
    ("HAY-MT05", "Meadow timothy hay 5 lb", 1, 890, 1699, "Prairie Supply Co"),
    ("TOY-TR-L", "TuffRope tug toy, large", 12, 412, 1299, "Fetch & Co Wholesale"),
    ("OIL-SO16", "Wild salmon oil 16 oz", 6, 1135, 2499, "Fetch & Co Wholesale"),
    ("CHW-DC30", "Dental chews, 30 count", 1, 1460, 2899, "Heartland Pet Distributors"),
]
DEMAND = {"DOG-SR25": (34, 52), "CAT-WF12": (22, 34), "LIT-CC35": (30, 46), "HAY-MT05": (14, 24), "TOY-TR-L": (9, 17),
          "OIL-SO16": (8, 14), "CHW-DC30": (12, 22)}
H1_END = date(2026, 6, 30)


def mkey(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def simulate(opening, receipts, sales, returns, extra_layer=None):
    """FIFO by SKU. Returns per-sale pieces, monthly net COGS, ending layers. extra_layer=(sku, date, qty, cost) adds a layer."""
    events = []
    for rc in receipts:
        if rc["status"] == "Received" and rc["date"] <= H1_END:
            events.append((rc["date"], 0, "r", rc))
    if extra_layer:
        events.append((extra_layer["date"], 0, "r", extra_layer))
    for rt in returns:
        events.append((rt["date"], 1, "t", rt))
    for s in sales:
        events.append((s["date"], 2, "s", s))
    events.sort(key=lambda e: (e[0], e[1], e[3].get("seq", 0)))
    layers = {p[0]: [dict(x) for x in opening if x["sku"] == p[0]] for p in PRODUCTS}
    cogs = {(p[0], m): 0 for p in PRODUCTS for m in MONTHS}
    pieces = {}
    for d, _, kind, ev in events:
        sku = ev["sku"]
        if kind == "r":
            layers[sku].append({"sku": sku, "date": d, "qty": ev["units"], "cost": ev["unit_cost"]})
        elif kind == "s":
            need, got = ev["qty"], []
            while need:
                if not layers[sku]:
                    return None
                lay = layers[sku][0]
                take = min(need, lay["qty"])
                got.append((take, lay["cost"]))
                lay["qty"] -= take
                need -= take
                if lay["qty"] == 0:
                    layers[sku].pop(0)
            pieces[ev["receipt"]] = got
            cogs[(sku, mkey(d))] += sum(q * c for q, c in got)
        else:
            orig = pieces.get(ev["orig"])
            if orig is None or len(orig) != 1:
                return None
            cost = orig[0][1]
            ev["cost"] = cost
            if ev["restock"]:
                layers[sku].append({"sku": sku, "date": d, "qty": ev["qty"], "cost": cost})
                layers[sku].sort(key=lambda x: x["date"])
                cogs[(sku, mkey(d))] -= ev["qty"] * cost
    return {"cogs": cogs, "layers": layers, "pieces": pieces}


def build(seed: int) -> dict:
    r = rng(seed)
    opening, receipts, sales, returns = [], [], [], []
    po = r.randint(3100, 3300)
    for sku, desc, pack, base, price, supplier in PRODUCTS:
        c0 = int(base * r.uniform(0.9, 0.96))
        for k, dd in enumerate(sorted(r.sample([date(2025, 11, 7), date(2025, 11, 21), date(2025, 12, 5), date(2025, 12, 19)], 2))):
            q = r.randint(6, 16) if pack == 1 else pack * r.randint(1, 2)
            opening.append({"sku": sku, "date": dd, "qty": q, "cost": c0 + k * r.randint(5, 40)})
        cost = base
        d = date(2026, 1, 1) + timedelta(days=r.randint(8, 20))
        while d <= date(2026, 6, 20):
            cost = int(cost * r.uniform(1.0, 1.06))
            if pack > 1:
                cases = r.randint(2, 4)
                units = cases * pack
                receipts.append({"sku": sku, "date": d, "po": po, "supplier": supplier, "uom_qty": cases, "uom": f"CS{pack}",
                                 "uom_cost": cost * pack, "units": units, "unit_cost": cost, "status": "Received", "seq": 0})
            else:
                lo, hi = DEMAND[sku]
                units = r.randint(lo, hi + 12)
                receipts.append({"sku": sku, "date": d, "po": po, "supplier": supplier, "uom_qty": units, "uom": "EA",
                                 "uom_cost": cost, "units": units, "unit_cost": cost, "status": "Received", "seq": 0})
            po += r.randint(1, 3)
            d += timedelta(days=r.randint(24, 38) if pack == 1 else r.randint(40, 60))
    dog_cost = max(x["unit_cost"] for x in receipts if x["sku"] == "DOG-SR25")
    july = {"sku": "DOG-SR25", "date": date(2026, 7, r.randint(1, 3)), "po": po + 5, "supplier": "Heartland Pet Distributors", "uom_qty": 40,
            "uom": "EA", "uom_cost": int(dog_cost * 1.04), "units": 40, "unit_cost": int(dog_cost * 1.04), "status": "Received", "seq": 0}
    backorder = {"sku": "DOG-SR25", "date": date(2026, 6, r.randint(8, 16)), "po": po + 2, "supplier": "Heartland Pet Distributors",
                 "uom_qty": 30, "uom": "EA", "uom_cost": int(dog_cost * 1.02), "units": 30, "unit_cost": int(dog_cost * 1.02),
                 "status": "Backordered", "seq": 0}
    receipts += [july, backorder]

    # ---- till sales, limited by what is on hand
    on_hand = {p[0]: sum(x["qty"] for x in opening if x["sku"] == p[0]) for p in PRODUCTS}
    rec_by_day = {}
    for rc in receipts:
        if rc["status"] == "Received" and rc["date"] <= H1_END:
            rec_by_day.setdefault(rc["date"], []).append(rc)
    receipt_no = r.randint(51000, 52000)
    day = date(2026, 1, 2)
    seq = 0
    while day <= H1_END:
        for rc in rec_by_day.get(day, []):
            on_hand[rc["sku"]] += rc["units"]
        if day.weekday() != 6:
            for sku, desc, pack, base, price, supplier in PRODUCTS:
                lo, hi = DEMAND[sku]
                daily = r.uniform(lo, hi) / 26
                n = int(daily) + (1 if r.random() < daily - int(daily) else 0)
                for _ in range(n):
                    q = 1 if r.random() < 0.75 else r.randint(2, 3)
                    if on_hand[sku] < q:
                        continue
                    on_hand[sku] -= q
                    receipt_no += 1; seq += 1
                    t = datetime(day.year, day.month, day.day, r.randint(9, 18), r.randint(0, 59))
                    sales.append({"sku": sku, "date": day, "time": t, "qty": q, "price": price, "receipt": f"R{receipt_no}", "seq": seq})
            todays = [x for x in sales if x["date"] == day]
            for x, t in zip(sorted(todays, key=lambda x: x["seq"]), sorted(x["time"] for x in todays)):
                x["time"] = t  # the till's clock runs in the same order as the sales
        day += timedelta(days=1)

    # ---- returns: a restocked cat food return, a damaged litter return, two more restocked elsewhere
    def pick_sale(sku, months):
        cands = [s for s in sales if s["sku"] == sku and s["date"].month in months]
        return r.choice(cands) if cands else None

    plan = [("CAT-WF12", (2, 3), True, "Wrong formula - unopened, back to shelf"),
            ("CAT-WF12", (4, 5), True, "Dog would not eat it - unopened, restocked"),
            ("LIT-CC35", (3, 4), False, "Bag split in car - damaged, discarded"),
            ("CHW-DC30", (2, 4), True, "Duplicate gift - unopened, restocked"),
            ("HAY-MT05", (5, 5), False, "Mold found - damaged, discarded")]
    for sku, months, restock, reason in plan:
        s = pick_sale(sku, months)
        if s is None:
            return {"bad": True}
        seq += 1; receipt_no += 1
        rd = s["date"] + timedelta(days=r.randint(2, 12))
        if rd.weekday() == 6:
            rd += timedelta(days=1)
        returns.append({"sku": sku, "date": rd, "time": datetime(rd.year, rd.month, rd.day, r.randint(10, 17), r.randint(0, 59)),
                        "qty": min(s["qty"], r.choice([1, 1, 2])), "price": s["price"], "orig": s["receipt"], "restock": restock,
                        "reason": reason, "receipt": f"R{receipt_no}", "seq": seq})
    # receipt numbers run in time order across sales and returns, as a till prints them
    for rt in returns:
        rt["seq"] = max(x["seq"] for x in sales if x["time"] <= rt["time"]) + 0.5 if any(x["time"] <= rt["time"] for x in sales) else 0.5
    renum = {}
    for k, x in enumerate(sorted(sales + returns, key=lambda x: (x["time"], x["seq"]))):
        new = f"R{51000 + (seed % 700) + k}"
        renum[x["receipt"]] = new
    for x in sales + returns:
        x["receipt"] = renum[x["receipt"]]
    for rt in returns:
        rt["orig"] = renum[rt["orig"]]
    res = simulate(opening, receipts, sales, returns)
    if res is None:
        return {"bad": True}
    cogs = res["cogs"]
    monthly = [sum(cogs[(p[0], m)] for p in PRODUCTS) for m in MONTHS]
    sku_tot = {p[0]: sum(cogs[(p[0], m)] for m in MONTHS) for p in PRODUCTS}
    ending = {p[0]: sum(x["qty"] * x["cost"] for x in res["layers"][p[0]]) for p in PRODUCTS}
    ending_units = {p[0]: sum(x["qty"] for x in res["layers"][p[0]]) for p in PRODUCTS}
    opening_val = {p[0]: sum(x["qty"] * x["cost"] for x in opening if x["sku"] == p[0]) for p in PRODUCTS}
    purchases = {p[0]: sum(x["units"] * x["unit_cost"] for x in receipts if x["sku"] == p[0] and x["status"] == "Received"
                           and x["date"] <= H1_END) for p in PRODUCTS}
    for p in PRODUCTS:
        assert opening_val[p[0]] + purchases[p[0]] - sku_tot[p[0]] == ending[p[0]], p[0]
    # same-day receipt and restocked return for one SKU would make layer order ambiguous
    for rt in returns:
        if rt["restock"] and any(rc["sku"] == rt["sku"] and rc["date"] == rt["date"] for rc in receipts):
            return {"bad": True}
    return {"opening": opening, "receipts": receipts, "sales": sales, "returns": returns, "cogs": cogs, "monthly": monthly,
            "sku_tot": sku_tot, "ending": ending, "ending_units": ending_units, "opening_val": opening_val, "purchases": purchases,
            "backorder": backorder, "july": july, "total": sum(monthly)}


def price_list(d: dict) -> dict:
    out = {}
    for sku, desc, pack, base, price, supplier in PRODUCTS:
        last = max((x for x in d["receipts"] if x["sku"] == sku and x["status"] == "Received" and x["date"] <= H1_END), key=lambda x: x["date"])
        out[sku] = int(last["unit_cost"] * 1.09)
    return out


def naive(d: dict) -> dict:
    """Units sold less every returned unit, at the supplier's list cost; on hand at list cost too."""
    pl = price_list(d)
    cogs = {(p[0], m): 0 for p in PRODUCTS for m in MONTHS}
    for s in d["sales"]:
        cogs[(s["sku"], mkey(s["date"]))] += s["qty"] * pl[s["sku"]]
    for rt in d["returns"]:
        cogs[(rt["sku"], mkey(rt["date"]))] -= rt["qty"] * pl[rt["sku"]]
    sku_tot = {p[0]: sum(cogs[(p[0], m)] for m in MONTHS) for p in PRODUCTS}
    units = {p[0]: sum(x["qty"] for x in d["opening"] if x["sku"] == p[0])
             + sum(x["uom_qty"] for x in d["receipts"] if x["sku"] == p[0])
             - sum(s["qty"] for s in d["sales"] if s["sku"] == p[0]) for p in PRODUCTS}
    return {"cogs": cogs, "sku_tot": sku_tot, "ending": {k: v * pl[k] for k, v in units.items()}, "ending_units": units,
            "monthly": [sum(cogs[(p[0], m)] for p in PRODUCTS) for m in MONTHS]}


def acceptable(d: dict) -> bool:
    if d.get("bad"):
        return False
    nv = naive(d)
    for sku in ("DOG-SR25", "CAT-WF12", "LIT-CC35", "TOY-TR-L"):
        v = d["sku_tot"][sku]
        if abs(nv["sku_tot"][sku] - v) < 500:
            return False
        others = [d["cogs"][(sku, m)] for m in MONTHS] + [d["ending"][sku], d["opening_val"][sku], d["purchases"][sku]]
        if any(abs(x - v) <= 100 for x in others):
            return False
    ev = d["ending"]["DOG-SR25"]
    others = [d["cogs"][("DOG-SR25", m)] for m in MONTHS] + [d["sku_tot"]["DOG-SR25"], d["opening_val"]["DOG-SR25"], d["purchases"]["DOG-SR25"]]
    if any(abs(x - ev) <= 100 for x in others):
        return False
    if abs(sum(nv["monthly"]) - d["total"]) < 5000:
        return False
    # the restocked cat food return and the damaged litter return each move their SKU's COGS by a visible amount
    cat = [rt for rt in d["returns"] if rt["sku"] == "CAT-WF12"]
    if sum(rt["qty"] * rt["cost"] for rt in cat) < 2000:
        return False
    # dog food sales in some month draw on two layers with different costs
    pieces = simulate(d["opening"], d["receipts"], d["sales"], d["returns"])["pieces"]
    dog_multi = sum(1 for s in d["sales"] if s["sku"] == "DOG-SR25" and len({c for _, c in pieces[s["receipt"]]}) > 1)
    if dog_multi < 1:
        return False
    # counting the backordered line as received changes dog food on hand at June 30
    bo = dict(d["backorder"], status="Received")
    alt = simulate(d["opening"], d["receipts"], d["sales"], d["returns"], extra_layer=bo)
    if alt is None or abs(sum(x["qty"] * x["cost"] for x in alt["layers"]["DOG-SR25"]) - ev) < 1000:
        return False
    if d["ending_units"]["DOG-SR25"] <= 0:
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def workbook(d: dict, cogs: dict, sku_tot: dict, ending_units: dict, opening_val: dict, purchases: dict) -> dict:
    skus = [p[0] for p in PRODUCTS]
    ncol = len(skus)
    last_c = get_column_letter(1 + ncol)
    tot_c = get_column_letter(2 + ncol)
    rows = []
    for i, m in enumerate(MONTHS, start=2):
        rows.append([m] + [cogs[(s, m)] / 100 for s in skus] + [f"=SUM(B{i}:{last_c}{i})"])
    tr = len(MONTHS) + 2
    rows.append(["Total Jan-Jun"] + [f"=SUM({get_column_letter(2 + j)}2:{get_column_letter(2 + j)}{tr - 1})" for j in range(ncol + 1)])
    inv = []
    for i, (sku, desc, *_rest) in enumerate(PRODUCTS, start=2):
        col = get_column_letter(2 + skus.index(sku))
        inv.append([sku, desc, opening_val[sku] / 100, purchases[sku] / 100, f"='COGS by month'!{col}{tr}", f"=C{i}+D{i}-E{i}",
                    ending_units[sku]])
    n = len(PRODUCTS) + 1
    inv.append(["Total", "", f"=SUM(C2:C{n})", f"=SUM(D2:D{n})", f"=SUM(E2:E{n})", f"=SUM(F2:F{n})", f"=SUM(G2:G{n})"])
    return {
        "COGS by month": {"header": ["Month"] + skus + ["Total COGS"], "rows": rows,
                          "number_formats": {get_column_letter(j): "#,##0.00" for j in range(2, 3 + ncol)}, "widths": {"A": 14}},
        "Inventory roll-forward": {"header": ["SKU", "Item", "Opening FIFO value 2026-01-01", "Received Jan-Jun", "COGS Jan-Jun",
                                              "On hand value 2026-06-30", "Units on hand 2026-06-30"], "rows": inv,
                                   "number_formats": {c: "#,##0.00" for c in "CDEF"}, "widths": {"A": 11, "B": 38, "C": 16, "F": 16}},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        nv = naive(d)
        os.makedirs(naive_dir, exist_ok=True)
        pl = price_list(d)
        write_xlsx(os.path.join(naive_dir, "cogs.xlsx"), workbook(d, nv["cogs"], nv["sku_tot"], nv["ending_units"],
                                                                  {k: 0 for k in pl}, {k: nv["ending"][k] + nv["sku_tot"][k] for k in pl}),
                   creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    desc_of = {p[0]: p[1] for p in PRODUCTS}

    # ---- workspace: CPA's closing layers
    write_xlsx(os.path.join(ws, "fifo_layers_2025-12-31.xlsx"), {"Layers": {
        "merged_title": "Barkwell Pet Supply - FIFO inventory layers at 12/31/2025 (prepared by M. Osei CPA)",
        "header": ["SKU", "Description", "Layer received", "Units remaining", "Unit cost", "Extended cost"],
        "rows": [[x["sku"], desc_of[x["sku"]], x["date"], x["qty"], x["cost"] / 100, round(x["qty"] * x["cost"] / 100, 2)]
                 for x in sorted(d["opening"], key=lambda x: (x["sku"], x["date"]))],
        "number_formats": {"E": "#,##0.00", "F": "#,##0.00"}, "widths": {"B": 38, "C": 14}}}, creator="Osei CPA")

    # ---- workspace: receiving log
    rec = []
    for x in sorted(d["receipts"], key=lambda x: (x["date"], x["po"])):
        rec.append([x["date"], f"PO-{x['po']}", x["supplier"], x["sku"], desc_of[x["sku"]], x["uom_qty"] if x["status"] == "Received" else 0,
                    x["uom"], money_str(x["uom_cost"] / 100, 1), money_str(x["uom_qty"] * x["uom_cost"] / 100 if x["status"] == "Received" else 0, 1),
                    x["status"] if x["status"] != "Received" else "Received", f"ordered {x['uom_qty']}" if x["status"] != "Received" else ""])
    write_xlsx(os.path.join(ws, "receiving_log_2026.xlsx"), {"Receiving": {
        "merged_title": "Receiving log 2026 (exported 07/06/2026)",
        "header": ["Date received", "PO", "Supplier", "SKU", "Item", "Qty received", "UOM", "Cost per UOM", "Line total", "Status", "Note"],
        "rows": rec, "widths": {"C": 26, "E": 38, "H": 12, "I": 12, "K": 14}, "freeze": "A3"}}, creator="Barkwell")

    # ---- workspace: till export
    till = []
    for s in d["sales"]:
        till.append([s["receipt"], s["time"], s["sku"], desc_of[s["sku"]], s["qty"], s["price"] / 100, s["qty"] * s["price"] / 100, "Sale", "", ""])
    for rt in d["returns"]:
        till.append([rt["receipt"], rt["time"], rt["sku"], desc_of[rt["sku"]], -rt["qty"], rt["price"] / 100, -rt["qty"] * rt["price"] / 100,
                     "Return", rt["reason"], rt["orig"]])
    till.sort(key=lambda x: (x[1], x[0]))
    write_csv(os.path.join(ws, "till_item_sales_2026-01-01_to_2026-06-30.csv"),
              ["Receipt", "Date", "SKU", "Item", "Qty", "Unit price", "Line total", "Type", "Return reason", "Original receipt"],
              [[x[0], x[1].strftime("%m/%d/%Y %I:%M %p")] + x[2:5] + [f"{x[5]:.2f}", f"{x[6]:.2f}"] + x[7:] for x in till], bom=True)

    # ---- workspace: supplier price list (a distractor: list prices, not what was paid)
    pl = price_list(d)
    write_csv(os.path.join(ws, "supplier_price_list_2026-07.csv"), ["Supplier", "SKU", "Item", "Pack", "List cost per pack", "Effective"],
              [[p[5], p[0], p[1], "each" if p[2] == 1 else f"case of {p[2]}", f"{pl[p[0]] * p[2] / 100:.2f}", "07/01/2026"] for p in PRODUCTS])

    # ---- workspace: CPA email
    write_email_thread(os.path.join(ws, "email_from_cpa_cogs.txt"), [
        {"from": "Mensah Osei <mensah@oseicpa.com>", "to": "Tara Wood <tara@barkwellpet.com>", "date": "Tue, 7 Jul 2026 08:44",
         "subject": "First-half COGS - FIFO",
         "body": ("Hi Tara,\n\nFor the mid-year review I need cost of goods sold on FIFO for the seven lines on my layer sheet, January "
                  "through June. The rules:\n\n"
                  "1. Start from my 12/31/2025 layers. Each sale uses up the oldest units first, at the cost those units were bought at.\n"
                  "2. Receipts count on the day they were received, and anything received (or put back on the shelf) on a day is "
                  "available for that day's sales.\n"
                  "3. Customer returns: if the item goes back on the shelf, take what those units cost when they were sold (look up "
                  "the original receipt) off COGS in the month of the return, and put them back into stock as a new layer at that "
                  "cost, dated the day they came back. If the return was damaged and thrown away, it does not go back into stock and "
                  "COGS stays as it was.\n"
                  "4. Use what we actually paid from the receiving log. Case lines are cost per case - divide by the units in the case.\n\n"
                  "What I need: COGS by month for each of the seven items with monthly totals, and a roll-forward per item from my "
                  "opening value through what was received and COGS to what is left on hand at June 30. Keep it formula-driven.\n\n"
                  "Thanks,\nMensah")}])

    # ---- reference
    write_csv(os.path.join(ref, "cogs_by_month.csv"), ["sku", "month", "cogs"],
              [[s, m, f"{d['cogs'][(s, m)] / 100:.2f}"] for s in (p[0] for p in PRODUCTS) for m in MONTHS])
    write_csv(os.path.join(ref, "rollforward.csv"), ["sku", "opening", "received", "cogs", "ending_value", "ending_units"],
              [[p[0], f"{d['opening_val'][p[0]] / 100:.2f}", f"{d['purchases'][p[0]] / 100:.2f}", f"{d['sku_tot'][p[0]] / 100:.2f}",
                f"{d['ending'][p[0]] / 100:.2f}", d["ending_units"][p[0]]] for p in PRODUCTS])
    write_json(os.path.join(ref, "notes.json"), {"cogs_by_month": {m: round(v / 100, 2) for m, v in zip(MONTHS, d["monthly"])},
                                                  "total_cogs": round(d["total"] / 100, 2),
                                                  "returns": [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in rt.items()}
                                                              for rt in d["returns"]]})

    # ---- reference solution
    write_xlsx(os.path.join(sol, "cogs.xlsx"), workbook(d, d["cogs"], d["sku_tot"], d["ending_units"], d["opening_val"], d["purchases"]),
               creator="Barkwell")

    def pin(name, sku, value):
        return {"type": "xlsx_value_present", "name": name, "path": "cogs.xlsx", "expected": round(value / 100, 2), "rel_tol": 0.000001,
                "near_text": sku.lower()}

    cat_r = [rt for rt in d["returns"] if rt["sku"] == "CAT-WF12"]
    lit_r = [rt for rt in d["returns"] if rt["sku"] == "LIT-CC35"]
    write_task_yaml(HERE, {
        "id": "fifo-cogs", "track": "desk", "category": "bookkeeping",
        "title": "First-half FIFO cost of goods sold",
        "ask": "Mensah needs our cost of goods sold for January to June on FIFO for the mid-year review. His email says how he wants it. Save it as cogs.xlsx.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "each item starts from the CPA's two 2025 layers and each receipt adds a dearer layer, so a sale late in a layer is split "
            "across two costs and months carry layers forward; costing at the latest or an average price moves every month "
            "(checks: dog food COGS; total COGS; cost of goods sold, one line per month)",
            f"{len(cat_r)} cat food returns went back on the shelf; each comes off COGS at the cost the original receipt went out at "
            "and re-enters stock as a new layer dated the return, not at the shelf price and not at the newest cost "
            "(check: cat food COGS)",
            f"the litter return on {lit_r[0]['date'].isoformat()} was damaged and thrown away; it does not come off COGS or go back "
            "into stock, although the till shows it as a negative line (check: litter COGS)",
            "the tug toy and salmon oil are received by the case of 12 and 6; the receiving log's quantity and cost are per case "
            "(check: tug toy COGS)",
            "a supplier price list dated July sits in the folder with list costs about 9% above what was paid "
            "(check: total COGS)",
            f"the receiving log also holds a dog food receipt dated {d['july']['date'].isoformat()} and a backordered dog food line "
            "with nothing received; neither belongs in June 30 stock (check: dog food on hand at June 30)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "cogs.xlsx", "min_count": 10},
            {"type": "xlsx_no_errors", "name": "no formula errors", "path": "cogs.xlsx"},
            {"type": "custom", "name": "cost of goods sold, one line per month", "module": "check.py"},
            {"type": "xlsx_value_present", "name": "total COGS", "path": "cogs.xlsx", "expected": round(d["total"] / 100, 2),
             "rel_tol": 0.000001, "near_text": "total"},
            pin("dog food COGS", "DOG-SR25", d["sku_tot"]["DOG-SR25"]),
            pin("cat food COGS", "CAT-WF12", d["sku_tot"]["CAT-WF12"]),
            pin("litter COGS", "LIT-CC35", d["sku_tot"]["LIT-CC35"]),
            pin("tug toy COGS", "TOY-TR-L", d["sku_tot"]["TOY-TR-L"]),
            pin("dog food on hand at June 30", "DOG-SR25", d["ending"]["DOG-SR25"]),
        ],
    })
    print(f"seed={seed} sales={len(d['sales'])} total={d['total'] / 100:.2f} monthly={[v / 100 for v in d['monthly']]}")
    print({k: v / 100 for k, v in d["sku_tot"].items()}, "dog ending", d["ending"]["DOG-SR25"] / 100)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a_ = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a_.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a_.seed * 1000 + attempt, a_.naive)
