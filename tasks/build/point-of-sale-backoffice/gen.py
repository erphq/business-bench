#!/usr/bin/env python3
"""Deterministic seed generator for the point-of-sale-backoffice build task.

    python gen.py [--seed N]

Writes:
  seed/items.csv           menu items for two cafes (re-typed codes and names, repeated rows, "$5.25" prices,
                           store availability words, one negative price)
  seed/modifiers.csv       one row per modifier per category it applies to (repeated rows, "+$0.75" / "75c" / "free")
  seed/daily_takings.csv   July and August 2026 nightly cash-ups from two tills (store names spelled five ways,
                           a day exported twice, mixed dates and money strings)
  seed/item_sales.csv      monthly item sales per store (month written three ways, repeated rows, lower-case codes)
  reference/counts.json    every figure checklist.md and changes/*.md quote, computed from the ground truth

Seed 0 is the public variant that checklist.md quotes. Other seeds re-roll sales, variances, costs, and which rows
repeat; counts.json is recomputed from the truth, so re-derive checklist numbers from it.
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

STORES = {"H": ("Harbor Street", "Nina Castillo", ["Harbor St", "HARBOR ST."], ["Nina Castillo", "Tomasz Nowak", "Leila Haddad"]),
          "M": ("Mill Road", "Owen Brooks", ["Mill Rd", "MILL RD"], ["Owen Brooks", "Chloe Kim", "Mateo Ruiz"])}
RESTRICTED = "M"
VARIANCE_LIMIT = 5.00
FOLLOW_UP_LIMIT = 20.00
SEARCH_CLOSER = "Tomasz"

# code, name, category, price, cost range, sold at (B / H / M), active
ITEMS = [
    ("ESP-SGL", "Espresso single", "Coffee", 3.00, (0.35, 0.5), "B", True), ("ESP-DBL", "Espresso double", "Coffee", 3.50, (0.6, 0.85), "B", True),
    ("AMR-12", "Americano 12oz", "Coffee", 3.75, (0.6, 0.85), "B", True), ("AMR-16", "Americano 16oz", "Coffee", 4.25, (0.8, 1.05), "B", True),
    ("LAT-12", "Latte 12oz", "Coffee", 4.75, (0.95, 1.2), "B", True), ("LAT-16", "Latte 16oz", "Coffee", 5.25, (1.15, 1.45), "B", True),
    ("CAP-12", "Cappuccino 12oz", "Coffee", 4.75, (0.9, 1.15), "B", True), ("FLW-8", "Flat white 8oz", "Coffee", 4.50, (0.85, 1.1), "B", True),
    ("MOC-12", "Mocha 12oz", "Coffee", 5.25, (1.2, 1.5), "B", True), ("MOC-16", "Mocha 16oz", "Coffee", 5.75, (1.45, 1.8), "B", True),
    ("COR-6", "Cortado 6oz", "Coffee", 4.25, (0.7, 0.95), "B", True), ("MAC-4", "Macchiato 4oz", "Coffee", 3.75, (0.6, 0.8), "B", True),
    ("DRP-12", "Drip coffee 12oz", "Coffee", 2.75, (0.3, 0.45), "B", True), ("DRP-16", "Drip coffee 16oz", "Coffee", 3.25, (0.4, 0.55), "B", True),
    ("CHA-12", "Chai latte 12oz", "Coffee", 4.95, (1.0, 1.3), "B", True), ("CHA-16", "Chai latte 16oz", "Coffee", 5.45, (1.25, 1.55), "B", True),
    ("HOT-12", "Hot chocolate 12oz", "Coffee", 4.25, (0.9, 1.2), "B", True), ("BRV-12", "Breve 12oz", "Coffee", 5.00, (1.2, 1.5), "M", True),
    ("CBR-16", "Cold brew 16oz", "Cold Drinks", 4.75, (0.7, 0.95), "B", True), ("CBR-20", "Cold brew 20oz", "Cold Drinks", 5.25, (0.85, 1.1), "B", True),
    ("ICL-16", "Iced latte 16oz", "Cold Drinks", 5.50, (1.15, 1.45), "B", True), ("NIT-16", "Nitro cold brew 16oz", "Cold Drinks", 5.75, (0.9, 1.2), "H", True),
    ("LEM-16", "Lemonade 16oz", "Cold Drinks", 3.95, (0.6, 0.85), "B", True), ("ITE-16", "Iced tea 16oz", "Cold Drinks", 3.50, (0.35, 0.5), "B", True),
    ("SPK-12", "Sparkling water 12oz", "Cold Drinks", 2.95, (0.9, 1.1), "B", True), ("TEA-EB", "English breakfast tea", "Tea", 3.25, (0.3, 0.45), "B", True),
    ("TEA-GR", "Sencha green tea", "Tea", 3.25, (0.35, 0.5), "B", True), ("TEA-CM", "Chamomile tea", "Tea", 3.25, (0.3, 0.45), "B", True),
    ("TEA-EG", "Earl grey tea", "Tea", 3.25, (0.3, 0.45), "B", True), ("MAT-12", "Matcha latte 12oz", "Tea", 5.25, (1.3, 1.65), "B", True),
    ("MAT-16", "Matcha latte 16oz", "Tea", 5.75, (1.55, 1.9), "B", True), ("CRS-BUT", "Butter croissant", "Pastry", 3.75, (1.1, 1.4), "B", True),
    ("CRS-ALM", "Almond croissant", "Pastry", 4.50, (1.4, 1.75), "B", True), ("CRS-CHO", "Chocolate croissant", "Pastry", 4.25, (1.3, 1.6), "B", True),
    ("MUF-BLU", "Blueberry muffin", "Pastry", 3.50, (0.9, 1.2), "B", True), ("SCN-CHE", "Cheddar scone", "Pastry", 3.95, (1.0, 1.3), "B", True),
    ("COO-CHO", "Chocolate chip cookie", "Pastry", 2.75, (0.55, 0.8), "B", True), ("BRN-SAL", "Salted brownie", "Pastry", 3.95, (0.9, 1.2), "B", True),
    ("CIN-ROL", "Cinnamon roll", "Pastry", 4.25, (1.05, 1.35), "B", True), ("BAN-BRD", "Banana bread slice", "Pastry", 3.75, (0.8, 1.05), "B", True),
    ("DON-GLZ", "Glazed doughnut", "Pastry", 2.95, (0.7, 0.95), "M", True), ("KGA-MAN", "Kouign-amann", "Pastry", 4.75, (1.5, 1.85), "H", True),
    ("TST-AVO", "Avocado toast", "Food", 9.50, (2.9, 3.6), "B", True), ("BAG-LOX", "Bagel with lox", "Food", 11.25, (3.8, 4.6), "H", True),
    ("BRK-SAN", "Breakfast sandwich", "Food", 8.75, (2.6, 3.2), "B", True), ("GRN-YOG", "Granola yogurt bowl", "Food", 7.25, (2.0, 2.5), "B", True),
    ("QCH-SPN", "Spinach quiche", "Food", 7.95, (2.3, 2.8), "B", True), ("SND-TUR", "Turkey pesto sandwich", "Food", 10.50, (3.4, 4.1), "B", True),
    ("SND-VEG", "Veggie wrap", "Food", 9.75, (2.8, 3.4), "B", True), ("SOU-DAY", "Soup of the day", "Food", 6.50, (1.6, 2.1), "M", True),
    ("OAT-BWL", "Oatmeal bowl", "Food", 6.25, (1.2, 1.6), "B", False), ("BNS-HSE", "House blend beans 12oz", "Retail", 16.00, (6.5, 7.5), "B", True),
    ("BNS-ETH", "Ethiopia beans 12oz", "Retail", 19.00, (8.0, 9.2), "B", True), ("BNS-DEC", "Decaf beans 12oz", "Retail", 17.00, (7.2, 8.2), "B", True),
    ("MUG-LOG", "Logo mug", "Retail", 18.00, (5.5, 6.8), "B", True), ("TUM-16", "Travel tumbler 16oz", "Retail", 28.00, (9.5, 11.5), "B", True),
    ("PMP-SCN", "Pumpkin scone", "Pastry", 4.25, (1.1, 1.4), "B", False),
]
NEG_PRICE_CODE = "COO-CHO"
AUDIT_CODE = "LAT-16"
RETYPED = [("CRS-ALM", "crs-alm", "Almond Croissant "), ("LAT-16", "lat-16", "Latte 16 oz")]
SOLD_AT_WORDS = {"B": ["Both", "Both", "All stores"], "H": ["Harbor St only", "Harbor only"], "M": ["Mill Rd only", "Mill only"]}

MODIFIERS = [  # name, group, price change, categories
    ("Whole milk", "Milk", 0.0, ["Coffee", "Tea", "Cold Drinks"]), ("Skim milk", "Milk", 0.0, ["Coffee", "Tea", "Cold Drinks"]),
    ("Oat milk", "Milk", 0.75, ["Coffee", "Tea", "Cold Drinks"]), ("Almond milk", "Milk", 0.75, ["Coffee", "Tea", "Cold Drinks"]),
    ("Soy milk", "Milk", 0.60, ["Coffee", "Tea", "Cold Drinks"]), ("Half & half", "Milk", 0.50, ["Coffee", "Tea", "Cold Drinks"]),
    ("Coconut milk", "Milk", 0.75, ["Coffee", "Tea", "Cold Drinks"]),
    ("Vanilla", "Syrup", 0.60, ["Coffee", "Tea", "Cold Drinks"]), ("Caramel", "Syrup", 0.60, ["Coffee", "Tea", "Cold Drinks"]),
    ("Hazelnut", "Syrup", 0.60, ["Coffee", "Tea", "Cold Drinks"]), ("Sugar-free vanilla", "Syrup", 0.60, ["Coffee", "Tea", "Cold Drinks"]),
    ("Lavender", "Syrup", 0.75, ["Coffee", "Tea", "Cold Drinks"]), ("Pumpkin spice", "Syrup", 0.85, ["Coffee", "Tea", "Cold Drinks"]),
    ("Honey", "Syrup", 0.40, ["Coffee", "Tea", "Cold Drinks"]),
    ("Extra shot", "Espresso", 1.00, ["Coffee", "Cold Drinks"]), ("Decaf", "Espresso", 0.0, ["Coffee", "Cold Drinks"]),
    ("Half-caf", "Espresso", 0.0, ["Coffee", "Cold Drinks"]),
    ("Whipped cream", "Extras", 0.50, ["Coffee", "Cold Drinks"]), ("Cold foam", "Extras", 1.25, ["Cold Drinks"]),
    ("Extra hot", "Extras", 0.0, ["Coffee", "Tea"]), ("Iced", "Extras", 0.0, ["Coffee", "Tea"]), ("Light ice", "Extras", 0.0, ["Cold Drinks"]),
    ("Add bacon", "Food add-ons", 2.50, ["Food"]), ("Add avocado", "Food add-ons", 1.75, ["Food"]), ("Gluten-free bread", "Food add-ons", 1.25, ["Food"]),
    ("Add egg", "Food add-ons", 1.50, ["Food"]), ("Toasted", "Food add-ons", 0.0, ["Food"]),
    ("Warmed", "Pastry", 0.0, ["Pastry"]), ("Side of butter", "Pastry", 0.50, ["Pastry"]), ("Side of jam", "Pastry", 0.50, ["Pastry"]),
    ("Extra tea bag", "Tea", 0.50, ["Tea"]), ("Lemon slice", "Tea", 0.0, ["Tea"]),
]
OAT_75C_CATEGORY = "Tea"

ITEM_COLUMNS = ["Item Code", "Item Name", "Category", "Price", "Cost", "Sold At", "Active"]
MOD_COLUMNS = ["Modifier", "Group", "Price Change", "Applies To"]
TAKINGS_COLUMNS = ["Date", "Store", "Transactions", "Gross Sales", "Discounts", "Card Sales", "Cash Counted", "Closed By", "Notes"]
SALES_COLUMNS = ["Month", "Store", "Item Code", "Item Name", "Qty Sold", "Net Sales"]


def fmt_date(d: date, style: int) -> str:
    return [d.isoformat(), f"{d.month}/{d.day}/{d.year}", d.strftime("%d-%b-%Y"), f"{d.strftime('%b')} {d.day}, {d.year}"][style % 4]


def fmt_money(v: float, style: int) -> str:
    return [f"${v:,.2f}", f"{v:.2f}", f"{v:,.2f}"][style % 3]


def fmt_delta(v: float, style: int) -> str:
    if v == 0:
        return ["0", "$0.00", "free"][style % 3]
    return [f"+${v:.2f}", f"{v:.2f}", f"{int(round(v * 100))}c" if v < 1 else f"+{v:.2f}"][style % 3]


def cents(v: float) -> int:
    return int(round(v * 100))


def build(seed: int, attempt: int) -> dict:
    rng = random.Random(seed * 1000 + attempt)
    items = []
    for code, name, cat, price, (clo, chi), sold, active in ITEMS:
        items.append({"code": code, "name": name, "cat": cat, "price": price, "cost": round(rng.uniform(clo, chi), 2), "sold": sold,
                      "active": active, "flag": None})
    by_code = {i["code"]: i for i in items}

    # ---------------- daily takings
    takings = []
    d = date(2026, 7, 1)
    closers = {k: v[3] for k, v in STORES.items()}
    while d <= date(2026, 8, 31):
        for s in ("H", "M"):
            if s == "M" and d.weekday() == 0:
                continue  # Mill Road is closed on Mondays
            weekend = d.weekday() >= 5
            lo, hi = {("H", False): (1600, 2400), ("H", True): (2400, 3400), ("M", False): (1000, 1600), ("M", True): (1500, 2300)}[(s, weekend)]
            gross = cents(rng.uniform(lo, hi)) / 100
            disc = cents(gross * rng.uniform(0.01, 0.04)) / 100
            net = round(gross - disc, 2)
            card = cents(net * rng.uniform(0.72, 0.86)) / 100
            expected = round(net - card, 2)
            r = rng.random()
            if r < 0.55:
                var = 0.0
            elif r < 0.85:
                var = round(rng.choice([-1, 1]) * rng.uniform(0.05, 3.0), 2)
            elif r < 0.95:
                var = round(rng.choice([-1, -1, 1]) * rng.uniform(5.25, 15.0), 2)
            else:
                var = round(-rng.uniform(20.5, 45.0), 2)
            counted = round(expected + var, 2)
            tx = max(40, int(round(net / rng.uniform(9.4, 11.6))))
            takings.append({"date": d, "store": s, "tx": tx, "gross": gross, "disc": disc, "net": net, "card": card, "expected": expected,
                            "counted": counted, "var": var, "closer": rng.choices(closers[s], weights=[5, 2, 3])[0],
                            "notes": rng.choice(["", "", "", "", "", "", "rain all day", "street fair", "espresso machine down 2 hrs",
                                                 "card reader offline 30 min", "short staffed", "catering pickup"])})
        d += timedelta(days=1)
    # the unique best day: a Harbor Street Saturday in mid August
    best = next(t for t in takings if t["store"] == "H" and t["date"] == date(2026, 8, 15))
    best["gross"] = 3612.75
    best["disc"] = cents(best["gross"] * 0.021) / 100
    best["net"] = round(best["gross"] - best["disc"], 2)
    best["card"] = cents(best["net"] * 0.8) / 100
    best["expected"] = round(best["net"] - best["card"], 2)
    best["counted"] = round(best["expected"] + best["var"], 2)
    if sum(1 for t in takings if t["gross"] >= 3612.75) != 1:
        raise ValueError("best day not unique")
    # example day for the variance item: a Harbor Street day short by more than the limit
    shorts = [t for t in takings if t["store"] == "H" and -15.0 <= t["var"] < -VARIANCE_LIMIT and t["date"].month == 8]
    if not shorts:
        raise ValueError("no short example")
    example = shorts[0]
    if len([t for t in takings if t["var"] < -FOLLOW_UP_LIMIT]) < 3:
        raise ValueError("too few follow-ups")

    # ---------------- item sales per store and month, scaled to about the takings
    sales = []
    base_qty = {"Coffee": (220, 900), "Cold Drinks": (90, 420), "Tea": (60, 260), "Pastry": (120, 520), "Food": (60, 300), "Retail": (6, 40)}
    for month in (7, 8):
        for s in ("H", "M"):
            month_net = sum(t["net"] for t in takings if t["store"] == s and t["date"].month == month)
            target = month_net * rng.uniform(0.975, 0.995)
            rows = []
            for it in items:
                if it["sold"] not in ("B", s):
                    continue
                if not it["active"] and month == 8:
                    continue
                lo, hi = base_qty[it["cat"]]
                qty = rng.randint(lo, hi) if s == "H" else rng.randint(int(lo * 0.65), int(hi * 0.65))
                uplift = rng.uniform(1.03, 1.12) if it["cat"] in ("Coffee", "Cold Drinks", "Tea") else rng.uniform(1.0, 1.04)
                rows.append([it, qty, qty * it["price"] * uplift * rng.uniform(0.97, 0.99)])
            scale = target / sum(r[2] for r in rows)
            for it, qty, raw in rows:
                q = max(1, int(round(qty * scale)))
                sales.append({"month": month, "store": s, "code": it["code"], "qty": q, "net": round(raw * scale, 2)})

    # ---------------- rows: items
    item_rows = []
    for it in items:
        price = it["price"]
        written_price = fmt_money(price, rng.randrange(3)) if rng.random() < 0.8 else f"{price:g}"
        if it["code"] == NEG_PRICE_CODE:
            written_price = f"-{price:.2f}"
            it["flag"] = "negative_price"
        item_rows.append({"Item Code": it["code"], "Item Name": it["name"], "Category": it["cat"], "Price": written_price,
                          "Cost": fmt_money(it["cost"], rng.randrange(2) + 1) if rng.random() < 0.85 else f"${it['cost']:.2f}",
                          "Sold At": rng.choice(SOLD_AT_WORDS[it["sold"]]), "Active": rng.choice(["Y", "Yes"]) if it["active"] else rng.choice(["N", "No"]),
                          "_code": it["code"], "_role": "unique"})
    top_price_row = next(r for r in item_rows if r["_code"] == "TUM-16")
    top_price_row["Price"] = "$28.00"
    audit_row = next(r for r in item_rows if r["_code"] == AUDIT_CODE)
    audit_row["Price"] = "$5.25"
    extra = []
    for code, code_written, name_written in RETYPED:
        src = next(r for r in item_rows if r["_code"] == code)
        extra.append(dict(src, **{"Item Code": code_written, "Item Name": name_written}, _role="retyped_duplicate"))
    for r in rng.sample([r for r in item_rows if r["_code"] not in (NEG_PRICE_CODE, AUDIT_CODE, "CRS-ALM")], 2):
        extra.append(dict(r, _role="exact_duplicate"))
    item_rows_out = item_rows + extra
    item_rows_out.sort(key=lambda r: (r["Category"], r["_code"], r["_role"]))

    # ---------------- rows: modifiers
    mod_rows = []
    for name, group, delta, cats in MODIFIERS:
        for cat in cats:
            style = rng.randrange(3)
            written = fmt_delta(delta, style)
            if name == "Oat milk" and cat == OAT_75C_CATEGORY:
                written = "75c"
            mod_rows.append({"Modifier": name, "Group": group, "Price Change": written, "Applies To": cat, "_name": name, "_role": "unique"})
    oat_coffee = next(r for r in mod_rows if r["_name"] == "Oat milk" and r["Applies To"] == "Coffee")
    oat_coffee["Price Change"] = "+$0.75"
    rep = [dict(oat_coffee, Modifier="Oat Milk", _role="retyped_duplicate"),
           dict(next(r for r in mod_rows if r["_name"] == "Caramel" and r["Applies To"] == "Cold Drinks"), Modifier="caramel", _role="retyped_duplicate"),
           dict(rng.choice([r for r in mod_rows if r["_name"] not in ("Oat milk", "Caramel")]), _role="exact_duplicate")]
    mod_rows_out = list(mod_rows)
    for r in rep:
        mod_rows_out.insert(rng.randint(0, len(mod_rows_out)), r)

    # ---------------- rows: takings
    tk_rows = []
    for t in takings:
        name, _, variants, _ = STORES[t["store"]]
        tk_rows.append({"Date": fmt_date(t["date"], rng.randrange(4)), "Store": name if rng.random() < 0.6 else rng.choice(variants),
                        "Transactions": str(t["tx"]), "Gross Sales": fmt_money(t["gross"], rng.randrange(3)),
                        "Discounts": fmt_money(t["disc"], rng.randrange(3)), "Card Sales": fmt_money(t["card"], rng.randrange(3)),
                        "Cash Counted": fmt_money(t["counted"], rng.randrange(3)), "Closed By": t["closer"], "Notes": t["notes"],
                        "_t": t, "_role": "unique"})
    next(r for r in tk_rows if r["_t"] is best)["Gross Sales"] = "$3,612.75"
    tk_rows.sort(key=lambda r: (r["_t"]["date"], r["_t"]["store"]))
    dup_pool = [r for r in tk_rows if r["_t"] is not best and r["_t"] is not example and r["_t"]["date"].month == 7]
    dsel = rng.sample(dup_pool, 2)
    tk_rows_out = list(tk_rows)
    for r in dsel:
        tk_rows_out.insert(tk_rows_out.index(r) + rng.randint(1, 6), dict(r, _role="exact_duplicate"))

    # ---------------- rows: item sales
    month_words = {7: ["Jul 2026", "2026-07", "July 2026"], 8: ["Aug 2026", "2026-08", "August 2026"]}
    sales_rows = []
    for x in sales:
        it = by_code[x["code"]]
        sales_rows.append({"Month": rng.choice(month_words[x["month"]]), "Store": STORES[x["store"]][0] if rng.random() < 0.7 else STORES[x["store"]][2][0],
                           "Item Code": x["code"] if rng.random() < 0.85 else x["code"].lower(), "Item Name": it["name"],
                           "Qty Sold": str(x["qty"]), "Net Sales": fmt_money(x["net"], rng.randrange(3)), "_x": x, "_role": "unique"})
    return {"items": items, "item_rows": item_rows_out, "mod_rows": mod_rows_out, "takings": takings, "tk_rows": tk_rows_out,
            "sales": sales, "sales_rows": sales_rows, "best": best, "example": example, "tk_dups": dsel}


def summarize(t: dict, rng_rep: random.Random) -> dict:
    items, takings, sales = t["items"], t["takings"], t["sales"]
    by_code = {i["code"]: i for i in items}
    aug = [x for x in takings if x["date"].month == 8]
    total_net = round(sum(x["net"] for x in takings), 2)
    m_net = round(sum(x["net"] for x in takings if x["store"] == RESTRICTED), 2)
    over = [x for x in aug if abs(x["var"]) > VARIANCE_LIMIT]
    closer_hits = [x for x in takings if SEARCH_CLOSER.lower() in (x["closer"] + " " + x["notes"]).lower()]
    uniq_tk = [r for r in t["tk_rows"] if r["_role"] == "unique"]
    text_top = max(uniq_tk, key=lambda r: r["Gross Sales"])
    if text_top["_t"] is t["best"]:
        raise ValueError("text sort would pass")

    # item performance: August net sales, both stores combined
    combined = {}
    for x in sales:
        if x["month"] == 8:
            c = combined.setdefault(x["code"], {"qty": 0, "net": 0.0})
            c["qty"] += x["qty"]
            c["net"] = round(c["net"] + x["net"], 2)
    ranking = sorted(combined.items(), key=lambda kv: -kv[1]["net"])
    nets = [v["net"] for _, v in ranking[:7]]
    if any(nets[i] - nets[i + 1] < 25 for i in range(6)):
        raise ValueError("top items too close")
    # repeat an August row of the item ranked 6th or 7th, so counting it twice reshuffles the top five
    cand = [x for x in sales if x["month"] == 8 and x["code"] in (ranking[5][0], ranking[6][0])]
    rep_sale = max(cand, key=lambda x: x["net"])
    naive = dict((k, v["net"]) for k, v in combined.items())
    naive[rep_sale["code"]] = round(naive[rep_sale["code"]] + rep_sale["net"], 2)
    naive_top5 = [k for k, _ in sorted(naive.items(), key=lambda kv: -kv[1])[:5]]
    if rep_sale["code"] not in naive_top5:
        raise ValueError("repeated sale row does not move the ranking")
    other = rng_rep.choice([r for r in t["sales_rows"] if r["_x"]["month"] == 7])
    rep_rows = [next(r for r in t["sales_rows"] if r["_x"] is rep_sale), other]
    for r in rep_rows:
        t["sales_rows"].insert(t["sales_rows"].index(r) + rng_rep.randint(1, 9), dict(r, _role="exact_duplicate"))

    m_aug = {}
    for x in sales:
        if x["month"] == 8 and x["store"] == RESTRICTED:
            m_aug[x["code"]] = x
    m_rank = sorted(m_aug.values(), key=lambda x: -x["net"])
    if m_rank[0]["net"] - m_rank[1]["net"] < 25:
        raise ValueError("mill top item too close")
    lat = {s: next(x for x in sales if x["month"] == 8 and x["store"] == s and x["code"] == AUDIT_CODE) for s in ("H", "M")}

    mods = MODIFIERS
    groups = sorted({g for _, g, _, _ in mods})
    coffee_mods = [n for n, _, _, cats in mods if "Coffee" in cats]
    ex = t["example"]
    ex_row = next(r for r in t["tk_rows"] if r["_t"] is ex and r["_role"] == "unique")
    follow = sorted((x for x in takings if x["var"] < -FOLLOW_UP_LIMIT), key=lambda x: (x["date"], x["store"]))

    def month_store(month, s, key):
        return round(sum(x[key] for x in takings if x["date"].month == month and x["store"] == s), 2)

    aug_ticket = {STORES[s][0]: round(month_store(8, s, "net") / sum(x["tx"] for x in aug if x["store"] == s), 2) for s in ("H", "M")}
    weekday = {}
    for s in ("H", "M"):
        wd = {}
        for x in aug:
            if x["store"] == s:
                wd.setdefault(x["date"].strftime("%A"), []).append(x["net"])
        weekday[STORES[s][0]] = {k: round(sum(v) / len(v), 2) for k, v in wd.items()}
    h_best_day = max(weekday["Harbor Street"].items(), key=lambda kv: kv[1])
    second = sorted(weekday["Harbor Street"].values())[-2]
    if h_best_day[1] - second < 40:
        raise ValueError("weekday too close")
    item_rows = t["item_rows"]
    uniq_items = [r for r in item_rows if r["_role"] == "unique"]
    text_price_top = max(uniq_items, key=lambda r: r["Price"])
    sold_counts = {k: sum(1 for i in items if i["sold"] == k) for k in ("B", "H", "M")}

    counts = {
        "baseline": {
            "STAFF_ROLE": "Store manager",
            "VIEWER_ROLE": "Read-only (the bookkeeper)",
            "MAIN_ENTITY": "daily sales entry",
            "MAIN_ENTITY_PLURAL": "daily sales entries",
            "restricted_user": STORES[RESTRICTED][1],
            "restricted_store": STORES[RESTRICTED][0],
            "SCOPE_COUNT": sum(1 for x in takings if x["store"] == RESTRICTED),
            "OUT_OF_SCOPE_EXAMPLE": {"store": "Harbor Street", "date": t["best"]["date"].isoformat()},
            "KPI_1": {"name": "total net sales", "value": total_net, "scoped_value": m_net, "definition": "sum of Gross Sales minus Discounts over all daily entries"},
            "KPI_2": {"name": "August 2026 net sales", "value": round(sum(x["net"] for x in aug), 2)},
            "KPI_3": {"name": "August 2026 cash over or short", "value": round(sum(x["var"] for x in aug), 2),
                      "definition": "sum over entries of Cash Counted - (Gross - Discounts - Card Sales)"},
            "KPI_4": {"name": "August 2026 days more than 5.00 over or short", "value": len(over)},
            "SEARCH_TERM": SEARCH_CLOSER, "SEARCH_COUNT": len(closer_hits),
            "FILTER_FIELD": "store", "FILTER_VALUE": "Mill Road", "FILTER_COUNT": sum(1 for x in takings if x["store"] == "M"),
            "SORT_FIELD": "gross sales", "SORT_TOP": {"store": "Harbor Street", "date": t["best"]["date"].isoformat(), "gross": t["best"]["gross"]},
            "text_sort_top_would_be": {"store": STORES[text_top["_t"]["store"]][0], "date": text_top["_t"]["date"].isoformat(), "file_value": text_top["Gross Sales"]},
            "EXPORT_ROWS": len(takings),
            "EXPORT_COLUMNS": ["date", "store", "gross sales", "discounts", "card sales", "cash counted"],
            "REQUIRED_FIELD": "a store",
        },
        "items": {
            "file_rows_excluding_header": len(item_rows),
            "exact_duplicate_rows": sum(1 for r in item_rows if r["_role"] == "exact_duplicate"),
            "retyped_duplicate_rows": [{"code_written": c, "name_written": n, "item": code} for code, c, n in RETYPED],
            "unique_items": len(items),
            "sold_at_both": sold_counts["B"], "harbor_only": sold_counts["H"], "mill_only": sold_counts["M"],
            "inactive": sorted(i["code"] for i in items if not i["active"]),
            "harbor_menu": sold_counts["B"] + sold_counts["H"], "mill_menu": sold_counts["B"] + sold_counts["M"],
            "highest_price": {"code": "TUM-16", "name": by_code["TUM-16"]["name"], "price": 28.00, "file_value": "$28.00",
                              "text_sort_top_would_be": {"code": text_price_top["_code"], "file_value": text_price_top["Price"]}},
            "negative_price": {"code": NEG_PRICE_CODE, "name": by_code[NEG_PRICE_CODE]["name"], "file_value": f"-{by_code[NEG_PRICE_CODE]['price']:.2f}"},
            "audit_item": {"code": AUDIT_CODE, "name": by_code[AUDIT_CODE]["name"], "price": by_code[AUDIT_CODE]["price"], "new_price": 5.50},
        },
        "modifiers": {
            "file_rows_excluding_header": len(t["mod_rows"]),
            "unique_modifiers": len(mods),
            "groups": groups,
            "modifier_category_rows_unique": sum(len(c) for _, _, _, c in mods),
            "repeated_rows": [{"written_as": r["Modifier"], "applies_to": r["Applies To"], "kind": r["_role"]} for r in t["mod_rows"] if r["_role"] != "unique"],
            "oat_milk": {"price_change": 0.75, "written_as": ["+$0.75", "75c"]},
            "coffee_item_modifiers": len(coffee_mods),
            "coffee_item_modifier_names": coffee_mods,
        },
        "takings": {
            "file_rows_excluding_header": len(t["tk_rows"]),
            "unique_entries": len(takings),
            "harbor_entries": sum(1 for x in takings if x["store"] == "H"), "mill_entries": sum(1 for x in takings if x["store"] == "M"),
            "store_spellings": ["Harbor Street", "Harbor St", "HARBOR ST.", "Mill Road", "Mill Rd", "MILL RD"],
            "repeated_rows": [{"store": STORES[r["_t"]["store"]][0], "date": r["_t"]["date"].isoformat()} for r in t["tk_dups"]],
            "july_net_by_store": {STORES[s][0]: month_store(7, s, "net") for s in ("H", "M")},
            "naive_july_net_by_store_counting_repeats": {STORES[s][0]: round(month_store(7, s, "net") + sum(r["_t"]["net"] for r in t["tk_dups"] if r["_t"]["store"] == s), 2) for s in ("H", "M")},
            "variance_example": {"store": "Harbor Street", "date": ex["date"].isoformat(), "gross": ex["gross"], "discounts": ex["disc"], "card": ex["card"],
                                 "counted": ex["counted"], "net": ex["net"], "cash_expected": ex["expected"], "variance": ex["var"],
                                 "file_values": {c: ex_row[c] for c in ("Date", "Store", "Gross Sales", "Discounts", "Card Sales", "Cash Counted")}},
            "variance_test_entry": {"gross": 1850.00, "discounts": 42.50, "card": 1402.30, "counted": 398.00, "net": 1807.50, "cash_expected": 405.20, "variance": -7.20},
            "variance_limit": VARIANCE_LIMIT,
            "august_days_over_limit": [{"store": STORES[x["store"]][0], "date": x["date"].isoformat(), "variance": x["var"]} for x in over],
        },
        "item_sales": {
            "file_rows_excluding_header": len(t["sales_rows"]),
            "unique_rows": len(sales),
            "repeated_rows": [{"month": r["_x"]["month"], "store": STORES[r["_x"]["store"]][0], "code": r["_x"]["code"], "net": r["_x"]["net"]} for r in rep_rows],
            "august_top5_both_stores": [{"code": k, "name": by_code[k]["name"], "qty": v["qty"], "net": v["net"]} for k, v in ranking[:5]],
            "august_6th_and_7th": [{"code": k, "name": by_code[k]["name"], "net": v["net"]} for k, v in ranking[5:7]],
            "naive_top5_counting_repeated_row": naive_top5,
            "mill_road_august_top": {"code": m_rank[0]["code"], "name": by_code[m_rank[0]["code"]]["name"], "qty": m_rank[0]["qty"], "net": m_rank[0]["net"]},
            "mill_road_august_second": {"code": m_rank[1]["code"], "name": by_code[m_rank[1]["code"]]["name"], "net": m_rank[1]["net"]},
            "latte_16_august": {STORES[s][0]: {"qty": lat[s]["qty"], "net": lat[s]["net"]} for s in ("H", "M")},
        },
        "changes": {
            "c1_august_average_ticket": aug_ticket,
            "c1_august_transactions": {STORES[s][0]: sum(x["tx"] for x in aug if x["store"] == s) for s in ("H", "M")},
            "c1_august_net": {STORES[s][0]: month_store(8, s, "net") for s in ("H", "M")},
            "c1_august_weekday_average_net": weekday,
            "c1_harbor_best_weekday": {"day": h_best_day[0], "average_net": h_best_day[1]},
            "c1_mill_best_weekday": dict(zip(("day", "average_net"), max(weekday["Mill Road"].items(), key=lambda kv: kv[1]))),
            "c2_follow_up_limit": FOLLOW_UP_LIMIT,
            "c2_import_days_short_over_limit": [{"store": STORES[x["store"]][0], "date": x["date"].isoformat(), "variance": x["var"]} for x in follow],
            "c2_mill_road_days_short_over_limit": sum(1 for x in follow if x["store"] == RESTRICTED),
            "c2_test_entries": [{"date": "2026-09-03", "gross": 1000.00, "discounts": 0.00, "card": 800.00, "counted": 175.00, "variance": -25.00, "on_list": True},
                                {"date": "2026-09-04", "gross": 1000.00, "discounts": 0.00, "card": 800.00, "counted": 180.00, "variance": -20.00, "on_list": False}],
        },
        "naive_alternatives": {"items_without_dedupe": len(item_rows), "items_codes_case_sensitive": len(item_rows) - sum(1 for r in item_rows if r["_role"] == "exact_duplicate"),
                               "modifiers_one_per_row": [sum(len(c) for _, _, _, c in mods), len(t["mod_rows"])], "oat_milk_if_75c_read_as_dollars": 75.00},
        "test_inputs": {
            "default_entry": {"store": "Harbor Street", "gross": 1000.00, "discounts": 0.00, "card": 1000.00, "counted": 0.00},
            "item_20": [{"store": "Mill Road", "date": "2026-09-01", "gross": 1200.00, "discounts": 0.00, "card": 900.00, "counted": 292.00, "variance": -8.00, "needs_note": True},
                        {"store": "Mill Road", "date": "2026-09-02", "gross": 1200.00, "discounts": 0.00, "card": 900.00, "counted": 305.00, "variance": 5.00, "needs_note": False}],
            "item_21": {"duplicate": ["Harbor Street", "2026-08-10"], "allowed": ["Mill Road", "2026-08-10"]},
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
            counts = summarize(truth, random.Random(seed * 1000 + attempt + 500000))
            break
        except (ValueError, StopIteration) as e:
            last = e
    else:
        raise SystemExit(f"no valid draw: {last}")
    counts = {"seed": seed, "attempt": attempt, **counts}
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "items.csv"), ITEM_COLUMNS, [[r[c] for c in ITEM_COLUMNS] for r in truth["item_rows"]])
    write_csv(os.path.join(SEED_DIR, "modifiers.csv"), MOD_COLUMNS, [[r[c] for c in MOD_COLUMNS] for r in truth["mod_rows"]])
    write_csv(os.path.join(SEED_DIR, "daily_takings.csv"), TAKINGS_COLUMNS, [[r[c] for c in TAKINGS_COLUMNS] for r in truth["tk_rows"]], crlf=True)
    write_csv(os.path.join(SEED_DIR, "item_sales.csv"), SALES_COLUMNS, [[r[c] for c in SALES_COLUMNS] for r in truth["sales_rows"]], bom=True)
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(counts, indent=2) + "\n")
    b = counts["baseline"]
    print(f"items {counts['items']['file_rows_excluding_header']} -> {counts['items']['unique_items']}; modifiers "
          f"{counts['modifiers']['file_rows_excluding_header']} rows -> {counts['modifiers']['unique_modifiers']}; takings "
          f"{counts['takings']['file_rows_excluding_header']} -> {counts['takings']['unique_entries']}; item sales "
          f"{counts['item_sales']['file_rows_excluding_header']} -> {counts['item_sales']['unique_rows']}; total net {b['KPI_1']['value']:,.2f}; attempt {attempt}")


if __name__ == "__main__":
    main()
