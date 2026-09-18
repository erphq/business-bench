#!/usr/bin/env python3
"""Deterministic seed generator for the order-management build task.

    python gen.py [--seed N]

Writes:
  seed/customers.csv      150 rows -> 142 customers (exact and email-case duplicates, two different people
                          with the same name, customer type and account manager in mixed case, resale
                          certificate written Yes / Y / on file / Expired / blank)
  seed/products.csv       64 rows -> 60 products (exact duplicates, a trailing-space SKU, prices partly as
                          "$64.00" strings, one impossible negative stock)
  seed/order_lines.csv    one row per order line -> 110 orders (order number written "#1042" or "1042",
                          status case variants and "Canceled", customer emails in other case, mixed dates,
                          Shipping / Tax / Order Total repeated on every line of an order)
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the canonical public variant (checklist.md quotes its numbers). Other seeds re-roll customers,
orders, quantities, and stock; counts.json is recomputed from the truth.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, phone_variant, write_csv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

TAX_RATE = Decimal("0.0825")
RETAIL_SHIPPING = Decimal("7.95")
FREE_SHIPPING_AT = Decimal("75.00")
WHOLESALE_SHIPPING = Decimal("15.00")
DISCOUNT_AT = Decimal("1000.00")
DISCOUNT_RATE = Decimal("0.05")
AMS = [("Jonah Whitaker", 14), ("Priya Raman", 13), ("Carlos Mendes", 11)]  # wholesale accounts per manager -> 38
RESTRICTED_AM = "Jonah Whitaker"
OTHER_AM = "Priya Raman"
N_RETAIL = 104
N_WHOLESALE = 38
N_CUSTOMER_EXACT_DUPES = 5
N_CUSTOMER_CASE_DUPES = 3
N_PRODUCT_EXACT_DUPES = 3
N_ORDERS = 110
STATUS_COUNTS = {"New": 16, "Paid": 12, "Packed": 6, "Shipped": 14, "Delivered": 52, "Cancelled": 10}
OPEN = ["New", "Paid", "Packed"]
SHIPPED = ["Shipped", "Delivered"]

CUSTOMER_COLUMNS = ["Name", "Company", "Email", "Type", "Account Manager", "Resale Certificate", "Phone", "City", "State", "Customer Since"]
PRODUCT_COLUMNS = ["SKU", "Product", "Size", "Retail Price", "Wholesale Price", "Stock"]
ORDER_COLUMNS = ["Order #", "Order Date", "Customer Email", "Status", "SKU", "Qty", "Unit Price", "Shipping", "Tax", "Order Total"]

TEAS = [("GRN", "SENCHA", "Sencha"), ("GRN", "GENMAI", "Genmaicha"), ("GRN", "DRAGON", "Dragonwell"), ("GRN", "JASMIN", "Jasmine Pearls"),
        ("BLK", "ASSAM", "Assam Breakfast"), ("BLK", "EARLGR", "Earl Grey Cream"), ("BLK", "DARJ", "Darjeeling First Flush"),
        ("BLK", "YUNNAN", "Golden Yunnan"), ("BLK", "CHAI", "Masala Chai"), ("OOL", "TIEGUA", "Tieguanyin"), ("OOL", "DHP", "Da Hong Pao"),
        ("OOL", "MILK", "Milk Oolong"), ("WHT", "SILVER", "Silver Needle"), ("WHT", "PEONY", "White Peony"), ("HRB", "CHAMOM", "Chamomile Blossom"),
        ("HRB", "ROOIBO", "Rooibos Vanilla"), ("HRB", "PEPMNT", "Peppermint Leaf"), ("HRB", "HIBISC", "Hibiscus Berry"),
        ("PUR", "SHOU", "Shou Puerh"), ("MAT", "CERMON", "Ceremonial Matcha")]
SIZES = [("2OZ", "2 oz tin", 1.0), ("4OZ", "4 oz pouch", 1.8), ("1LB", "1 lb bag", 5.6)]
BASE_2OZ = [9.00, 9.50, 10.00, 11.00, 12.00, 13.50, 14.00, 16.00]
COMPANIES = ["Blue Door Cafe", "Harvest Moon Grocers", "Kettle & Crumb Bakery", "Northside Co-op", "Little Fern Coffee",
             "Copper Pot Market", "Sparrow Street Books & Cafe", "The Daily Grind", "Wildflower Wellness Spa", "Riverbend Natural Foods",
             "Maple Leaf Diner", "Quiet Hours Yoga Studio", "Brick Oven Collective", "Saltbox Provisions", "Juniper Hill Inn",
             "Greenline Juice Bar", "Oak & Anchor Pub", "Lantern Tea Room", "Pinecone Deli", "Hillcrest Market Hall",
             "Two Rivers Roasters", "Cedar Grove Gift Shop", "Marigold Kitchen", "Morning Glory Bakehouse", "Stonebridge Cafe",
             "The Herbalist's Corner", "Violet Hour Bistro", "Sunday Supply Co", "Willow Creek Grocery", "Foxtail Coffee Bar",
             "Tidewater Hotel", "Meadowlark Market", "Old Mill Pantry", "Paper Lantern Noodles", "Ridgeview Senior Living",
             "Thimble & Thread Cafe", "Wanderlust Books", "Zest Organic Market", "Honeycomb Creamery", "Evergreen Health Foods"]
CITIES = [("Portland", "OR"), ("Seattle", "WA"), ("Boise", "ID"), ("Eugene", "OR"), ("Spokane", "WA"), ("Tacoma", "WA"), ("Bend", "OR")]
D_STYLES = [0, 1, 2, 3, 4, 6]


def cents(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def no_half_cent(x: Decimal) -> bool:
    return (x * 100) % 1 != Decimal("0.5")


def price_order(lines: list[tuple[Decimal, int]], wholesale: bool, exempt: bool, discount: bool = False) -> dict:
    goods = cents(sum((p * q for p, q in lines), Decimal("0")))
    disc = cents(goods * DISCOUNT_RATE) if (discount and wholesale and goods >= DISCOUNT_AT) else Decimal("0.00")
    net = goods - disc
    ship = WHOLESALE_SHIPPING if wholesale else (Decimal("0.00") if goods >= FREE_SHIPPING_AT else RETAIL_SHIPPING)
    raw_tax = Decimal("0") if (wholesale and exempt) else net * TAX_RATE
    assert no_half_cent(raw_tax), f"half-cent tax on {net}"
    tax = cents(raw_tax)
    return {"goods": goods, "discount": disc, "shipping": ship, "tax": tax, "total": net + ship + tax}


def d2(x: Decimal) -> float:
    return float(cents(x))


def build(rng: random.Random, seed: int) -> dict:
    am_first = {a.split()[0] for a, _ in AMS}
    am_last = {a.split()[1] for a, _ in AMS}

    # ------------------------------------------------------------------ products
    products = []
    for fam, code, name in TEAS:
        base = rng.choice(BASE_2OZ)
        for scode, sname, mult in SIZES:
            retail = Decimal(str(round(base * mult * 2) / 2)).quantize(Decimal("0.01"))
            products.append({"sku": f"{fam}-{code}-{scode}", "name": name, "size": sname, "retail": retail,
                             "wholesale": cents(retail * Decimal("0.6")),
                             "stock": rng.randint(5, 60) if scode == "1LB" else rng.randint(10, 150)})
    by_sku = {p["sku"]: p for p in products}
    A, B, C, LOW, NEG, TOP = "BLK-ASSAM-4OZ", "OOL-TIEGUA-4OZ", "HRB-ROOIBO-1LB", "WHT-SILVER-1LB", "HRB-PEPMNT-2OZ", "MAT-CERMON-1LB"
    by_sku[A].update(retail=Decimal("18.00"), wholesale=Decimal("10.80"), stock=40)
    by_sku[B].update(retail=Decimal("24.50"), wholesale=Decimal("14.70"), stock=15)
    by_sku[C].update(retail=Decimal("21.00"), wholesale=Decimal("12.50"), stock=200)
    by_sku[LOW].update(retail=Decimal("96.00"), wholesale=Decimal("57.60"), stock=3)
    by_sku[NEG].update(stock=-2)
    by_sku[TOP].update(retail=Decimal("148.00"), wholesale=Decimal("88.80"))
    for p in products:
        if p["sku"] != TOP and p["retail"] >= Decimal("148.00"):
            p["retail"], p["wholesale"] = Decimal("139.50"), Decimal("83.70")
    special_skus = [A, B, C, LOW, NEG, TOP]

    # ------------------------------------------------------------------ customers
    pairs = [(f, l) for f in FIRST for l in LAST if f not in am_first and l not in am_last and not (f == "Maria" and l == "Lopez")]
    rng.shuffle(pairs)
    customers = []
    for i in range(N_RETAIL):
        f, l = pairs[i]
        city, st = rng.choice(CITIES)
        customers.append({"name": f"{f} {l}", "company": "", "email": f"{f}.{l}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'yahoo.com', 'outlook.com', 'icloud.com', 'proton.me'])}".lower(),
                          "type": "Retail", "am": "", "cert": False, "cert_written": "", "city": city, "state": st,
                          "phone": f"{rng.choice(['503', '206', '208', '541', '509'])}555{rng.randint(1000, 9999)}",
                          "since": date(2021, 3, 1) + timedelta(days=rng.randint(0, 1900))})
    # two different retail customers called Maria Lopez
    for k, i in enumerate(rng.sample(range(N_RETAIL), 2)):
        customers[i]["name"] = "Maria Lopez"
        customers[i]["email"] = ["maria.lopez@gmail.com", "mlopez.tea@outlook.com"][k]
    ams = [a for a, n in AMS for _ in range(n)]
    rng.shuffle(ams)
    companies = rng.sample(COMPANIES, N_WHOLESALE)
    for i, comp in enumerate(companies):
        f, l = pairs[N_RETAIL + i]
        city, st = rng.choice(CITIES)
        dom = comp.lower().replace("&", "and").replace("'", "").replace(" ", "") + ".com"
        cert = rng.random() < 0.7
        customers.append({"name": f"{f} {l}", "company": comp, "email": rng.choice([f"orders@{dom}", f"{f}@{dom}".lower(), f"hello@{dom}"]),
                          "type": "Wholesale", "am": ams[i], "cert": cert, "city": city, "state": st,
                          "phone": f"{rng.choice(['503', '206', '208', '541', '509'])}555{rng.randint(1000, 9999)}",
                          "since": date(2021, 3, 1) + timedelta(days=rng.randint(0, 1900))})
    wholesale = [c for c in customers if c["type"] == "Wholesale"]
    # the restricted manager needs one exempt and one taxable account for the checklist
    jonah = [c for c in wholesale if c["am"] == RESTRICTED_AM]
    jonah.sort(key=lambda c: c["company"])
    w_exempt, w_taxable = jonah[0], jonah[1]
    w_exempt["cert"], w_taxable["cert"] = True, False
    for c in customers:
        if c["type"] == "Wholesale":
            c["cert_written"] = rng.choice(["Yes", "Y", "yes", "On file"]) if c["cert"] else rng.choice(["No", "N", "", "Expired"])
    w_taxable["cert_written"] = "Expired"
    retail = [c for c in customers if c["type"] == "Retail"]
    r_test = sorted((c for c in retail if c["name"] != "Maria Lopez"), key=lambda c: c["name"])[0]

    reserved = {id(w_exempt), id(w_taxable), id(r_test)}
    retail_idx = [i for i, c in enumerate(customers) if c["type"] == "Retail" and id(c) not in reserved and c["name"] != "Maria Lopez"]
    rng.shuffle(retail_idx)
    case_src = retail_idx[:N_CUSTOMER_CASE_DUPES]
    exact_src = rng.sample([i for i in range(len(customers)) if i not in case_src and id(customers[i]) not in reserved], N_CUSTOMER_EXACT_DUPES)

    def cust_row(c, email=None, phone_style=None):
        type_w = c["type"] if rng.random() < 0.7 else rng.choice([c["type"].lower(), c["type"].upper(), c["type"] + " "])
        am_w = c["am"]
        if am_w and rng.random() < 0.3:
            am_w = rng.choice([am_w.lower(), am_w.upper(), am_w + " "])
        return [c["name"], c["company"], c["email"] if email is None else email, type_w, am_w, c["cert_written"],
                phone_variant(c["phone"], rng.randrange(7) if phone_style is None else phone_style), c["city"], c["state"],
                date_variant(c["since"], rng.choice(D_STYLES))]

    cust_rows = [cust_row(c) for c in customers]
    for i in exact_src:
        cust_rows.append(list(cust_rows[i]))
    case_groups = []
    for i in case_src:
        c = customers[i]
        variant = rng.choice([c["email"].upper(), c["email"].capitalize()])
        cust_rows.append(cust_row(c, email=variant))
        case_groups.append({"customer": c["name"], "emails_as_written": [c["email"], variant]})
    rng.shuffle(cust_rows)

    # ------------------------------------------------------------------ orders
    statuses = [s for s, n in STATUS_COUNTS.items() for _ in range(n)]
    rng.shuffle(statuses)
    stock_left = {p["sku"]: p["stock"] for p in products}
    orders = []
    for n in range(N_ORDERS):
        status = statuses[n]
        cust = rng.choice(wholesale) if rng.random() < 0.3 else rng.choice([c for c in retail if id(c) not in reserved])
        is_w = cust["type"] == "Wholesale"
        pool = [p for p in products if p["sku"] not in special_skus] if status in OPEN else [p for p in products if p["sku"] != NEG]
        k = rng.choice([1, 2, 2, 3, 4]) if is_w else rng.choice([1, 1, 1, 2, 2, 3])
        chosen = rng.sample(pool, k)
        lines = []
        for p in chosen:
            q = rng.randint(6, 24) if is_w else rng.choice([1, 1, 1, 2, 3])
            if status in OPEN:
                q = max(1, min(q, stock_left[p["sku"]] // 2))
                stock_left[p["sku"]] -= q
            lines.append((p, q))
        if status in ("Delivered", "Shipped", "Cancelled"):
            d = date(2026, 1, 5) + timedelta(days=rng.randint(0, 235))
        else:
            d = date(2026, 8, 20) + timedelta(days=rng.randint(0, 21))
        orders.append({"no": 1001 + n, "date": d, "cust": cust, "status": status, "lines": lines})
    rng.shuffle(orders)
    for n, o in enumerate(orders):
        o["no"] = 1001 + n
    orders.sort(key=lambda o: (o["date"], o["no"]))
    for n, o in enumerate(orders):
        o["no"] = 1001 + n

    def pricing(o, discount=False):
        is_w = o["cust"]["type"] == "Wholesale"
        return price_order([((p["wholesale"] if is_w else p["retail"]), q) for p, q in o["lines"]], is_w, o["cust"]["cert"], discount)

    # biggest order must be unique and a thousands figure so a text sort misranks it
    for o in orders:  # keep every imported order free of half-cent tax so a recomputation cannot disagree with the file
        for attempt in range(200):
            try:
                o["price"] = pricing(o)
                break
            except AssertionError:
                j = attempt % len(o["lines"])
                pj, qj = o["lines"][j]
                if attempt < 2 * len(o["lines"]):
                    o["lines"][j] = (pj, qj + 1)
                else:  # a price that is a multiple of 4.00 never escapes by quantity; swap the product
                    used = {p["sku"] for p, _ in o["lines"]}
                    swap = rng.choice([p for p in products if p["sku"] not in special_skus and p["sku"] not in used])
                    o["lines"][j] = (swap, max(1, min(qj, swap["stock"] // 2)))
        else:
            raise AssertionError("could not avoid half-cent tax")
        if o["status"] in OPEN:
            assert all(q <= p["stock"] for p, q in o["lines"])
    top = max(orders, key=lambda o: o["price"]["total"])
    assert sum(1 for o in orders if o["price"]["total"] == top["price"]["total"]) == 1
    assert top["price"]["total"] >= 1000

    status_variants = {"New": ["new", "NEW"], "Paid": ["paid", "PAID"], "Packed": ["packed", "PACKED"], "Shipped": ["shipped", "SHIPPED"],
                       "Delivered": ["delivered", "DELIVERED"], "Cancelled": ["Canceled", "canceled", "CANCELLED"]}
    line_rows = []
    top = max(orders, key=lambda o: o["price"]["total"])
    multi = [o for o in orders if len(o["lines"]) >= 3 and o["cust"]["type"] == "Wholesale" and o["status"] in SHIPPED and o is not top]
    check_order = sorted(multi, key=lambda o: o["no"])[0]
    dollar_orders = {o["no"] for o in orders if rng.random() < 0.3} | {top["no"]}
    for o in orders:
        st_w = o["status"] if rng.random() < 0.6 else rng.choice(status_variants[o["status"]])
        email_w = o["cust"]["email"].upper() if rng.random() < 0.12 else o["cust"]["email"]
        dt_w = date_variant(o["date"], rng.choice(D_STYLES))
        pr = o["price"]
        money = (lambda x: f"${x:,.2f}") if o["no"] in dollar_orders else (lambda x: f"{x:.2f}")
        for j, (p, q) in enumerate(o["lines"]):
            no_w = f"#{o['no']}" if (rng.random() < 0.82 and not (o is check_order and j == 1)) else str(o["no"])
            unit = p["wholesale"] if o["cust"]["type"] == "Wholesale" else p["retail"]
            line_rows.append([no_w, dt_w, email_w, st_w, p["sku"], str(q), f"{unit:.2f}", money(pr["shipping"]), money(pr["tax"]), money(pr["total"])])

    # ------------------------------------------------------------------ products file
    prod_rows = []
    currency = set(rng.sample([p["sku"] for p in products if p["sku"] not in (A, B, C)], 14)) | {TOP}
    for p in products:
        fmt = (lambda x: f"${x:,.2f}") if p["sku"] in currency else (lambda x: f"{x:.2f}")
        prod_rows.append([p["sku"], p["name"], p["size"], fmt(p["retail"]), fmt(p["wholesale"]), str(p["stock"])])
    prod_exact = rng.sample(range(len(products)), N_PRODUCT_EXACT_DUPES)
    for i in prod_exact:
        prod_rows.append(list(prod_rows[i]))
    trim_src = next(i for i in rng.sample(range(len(products)), len(products)) if products[i]["sku"] not in special_skus and i not in prod_exact)
    trim_row = list(prod_rows[trim_src])
    trim_row[0] = trim_row[0] + " "
    prod_rows.append(trim_row)
    rng.shuffle(prod_rows)

    # ------------------------------------------------------------------ truth
    def is_open(o):
        return o["status"] in OPEN

    def scoped(o, am=RESTRICTED_AM):
        return o["cust"]["am"] == am

    shipped = [o for o in orders if o["status"] in SHIPPED]
    ship_total = sum((o["price"]["total"] for o in shipped), Decimal("0"))
    ship_tax = sum((o["price"]["tax"] for o in shipped), Decimal("0"))
    line_summed_total = sum((o["price"]["total"] * len(o["lines"]) for o in shipped), Decimal("0"))
    by_text_total = sorted(line_rows, key=lambda r: r[9], reverse=True)
    top_text_no = by_text_total[0][0].lstrip("#")
    two_or_three = {}
    for o in orders:
        if o["cust"]["type"] == "Wholesale":
            two_or_three.setdefault(o["cust"]["company"], []).append(o)
    search_company = next(sorted(c for c, os_ in two_or_three.items() if len(os_) == n and c not in (w_exempt["company"], w_taxable["company"])
                                 and not any(c.lower() in other.lower() for other in COMPANIES if other != c))
                          for n in (3, 2, 4) if any(len(os_) == n and c not in (w_exempt["company"], w_taxable["company"]) for c, os_ in two_or_three.items()))[0]
    oos = sorted((o for o in orders if scoped(o, OTHER_AM) and o is not top and o is not check_order), key=lambda o: o["no"])[0]
    months = sorted({o["date"].month for o in shipped})

    def month_score(m):
        ms = [o for o in shipped if o["date"].month == m]
        r = sum(1 for o in ms if o["cust"]["type"] == "Retail")
        w = sum(1 for o in ms if o["cust"]["type"] == "Wholesale")
        j = sum(1 for o in ms if o["cust"]["am"] == RESTRICTED_AM)
        small = sum(1 for o in ms if o["cust"]["type"] == "Retail" and o["price"]["shipping"] > 0)
        return (min(j, 1), min(small, 1), min(r, w), m)
    report_month = max(months, key=month_score)
    month_names = {m: date(2026, m, 1).strftime("%B") for m in range(1, 13)}
    qty_on_shipped = {p["sku"]: sum(q for o in shipped for pp, q in o["lines"] if pp["sku"] == p["sku"]) for p in products}
    stock_check = max((p for p in products if p["sku"] not in (NEG, LOW)), key=lambda p: (qty_on_shipped[p["sku"]], p["sku"]))
    jonah_customers = [c for c in wholesale if c["am"] == RESTRICTED_AM]

    def month_block(month, typ, am=None):
        os_ = [o for o in shipped if o["date"].month == month and o["cust"]["type"] == typ and (am is None or o["cust"]["am"] == am)]
        return {"orders": len(os_), "goods": d2(sum((o["price"]["goods"] for o in os_), Decimal("0"))),
                "shipping": d2(sum((o["price"]["shipping"] for o in os_), Decimal("0"))),
                "tax": d2(sum((o["price"]["tax"] for o in os_), Decimal("0"))),
                "total": d2(sum((o["price"]["total"] for o in os_), Decimal("0")))}

    pa, pb, pc = by_sku[A], by_sku[B], by_sku[C]
    r1 = price_order([(pa["retail"], 2), (pb["retail"], 1)], False, False)
    r2 = price_order([(pa["retail"], 4), (pb["retail"], 1)], False, False)
    w1 = price_order([(pa["wholesale"], 12)], True, True)
    w2 = price_order([(pa["wholesale"], 12)], True, False)
    d_over = price_order([(pc["wholesale"], 90)], True, False, discount=True)
    d_at = price_order([(pc["wholesale"], 80)], True, True, discount=True)
    d_below = price_order([(pc["wholesale"], 79)], True, True, discount=True)
    d_retail = price_order([(pc["retail"], 48)], False, False, discount=True)
    held = sorted((o for o in orders if o["status"] == "Paid" and scoped(o)), key=lambda o: o["no"])

    def pdict(p):
        return {k: d2(v) for k, v in p.items()}

    counts = {
        "seed": seed,
        "shop": {"account_managers": [a for a, _ in AMS], "restricted_login": RESTRICTED_AM, "other_manager": OTHER_AM,
                 "roles": {"admin": "Admin (owner)", "staff": "Account Manager", "viewer": "Finance (read-only)"},
                 "pricing_rules": {"tax_rate_percent": 8.25, "tax_on": "goods only (after any discount)", "retail_shipping": 7.95,
                                   "retail_free_shipping_at_goods": 75.00, "wholesale_shipping": 15.00,
                                   "wholesale_tax": "none when the resale certificate is Yes / Y / On file; Expired, No, N, or blank are taxed",
                                   "rounding": "tax rounded half-up to the cent"},
                 "status_flow": ["New", "Paid", "Packed", "Shipped", "Delivered"], "cancel_allowed_before": "Shipped"},
        "tester_records": {"retail_customer": r_test["name"], "retail_customer_email": r_test["email"],
                           "wholesale_exempt_customer": w_exempt["company"], "wholesale_taxable_customer": w_taxable["company"],
                           "product_a": {"sku": A, "retail": d2(pa["retail"]), "wholesale": d2(pa["wholesale"]), "stock": pa["stock"]},
                           "product_b": {"sku": B, "retail": d2(pb["retail"]), "wholesale": d2(pb["wholesale"]), "stock": pb["stock"]},
                           "note": "orders the tester creates use these and are deleted when the item is done"},
        "customers": {
            "file_rows_excluding_header": len(cust_rows),
            "exact_duplicate_rows": N_CUSTOMER_EXACT_DUPES,
            "email_case_duplicate_rows": N_CUSTOMER_CASE_DUPES,
            "unique_customers_after_dedupe": len(customers),
            "dedupe_rule": "Two rows are the same customer when Email matches after trimming and lowercasing. The two Maria Lopez rows have different emails: two customers.",
            "wrong_counts": {"no_dedupe": len(cust_rows), "exact_rows_only": len(cust_rows) - N_CUSTOMER_EXACT_DUPES, "name_dedupe": len(customers) - 1},
            "email_case_groups": case_groups,
            "retail": N_RETAIL, "wholesale": N_WHOLESALE,
            "wholesale_with_valid_certificate": sum(1 for c in wholesale if c["cert"]),
            "wholesale_taxable": sum(1 for c in wholesale if not c["cert"]),
            "certificate_written_expired": sum(1 for c in wholesale if c["cert_written"] == "Expired"),
            "per_account_manager": {a: sum(1 for c in wholesale if c["am"] == a) for a, _ in AMS},
            "restricted_customers": sorted(c["company"] for c in jonah_customers),
        },
        "products": {
            "file_rows_excluding_header": len(prod_rows),
            "exact_duplicate_rows": N_PRODUCT_EXACT_DUPES,
            "trailing_space_duplicate_rows": 1,
            "trailing_space_sku": products[trim_src]["sku"],
            "unique_products": len(products),
            "currency_string_price_rows": len(currency),
            "highest_retail_price": {"sku": TOP, "file_value": f"${by_sku[TOP]['retail']:,.2f}", "numeric": d2(by_sku[TOP]["retail"]),
                                     "text_sort_would_put_first": sorted(prod_rows, key=lambda r: r[3], reverse=True)[0][0]},
            "negative_stock": {"sku": NEG, "stock": -2},
            "low_stock_product": {"sku": LOW, "stock": 3, "retail": d2(by_sku[LOW]["retail"])},
            "stock_not_decremented_on_import": {"sku": stock_check["sku"], "file_stock": stock_check["stock"],
                                                "qty_on_imported_shipped_or_delivered_orders": qty_on_shipped[stock_check["sku"]],
                                                "wrong_stock_if_import_decrements": stock_check["stock"] - qty_on_shipped[stock_check["sku"]]},
        },
        "orders": {
            "file_lines_excluding_header": len(line_rows),
            "orders": len(orders),
            "grouping_rule": "lines belong to the same order when Order # matches after removing a leading '#'",
            "lines_written_without_hash": sum(1 for r in line_rows if not r[0].startswith("#")),
            "per_status": {s: sum(1 for o in orders if o["status"] == s) for s in STATUS_COUNTS},
            "status_written_variants": "mixed case, and Canceled / CANCELLED for Cancelled",
            "open_orders": sum(1 for o in orders if is_open(o)),
            "shipped_or_delivered_orders": len(shipped),
            "shipped_sales_total": d2(ship_total),
            "shipped_sales_if_order_total_summed_per_line": d2(line_summed_total),
            "shipped_sales_tax": d2(ship_tax),
            "average_shipped_order_value": d2(ship_total / len(shipped)),
            "restricted": {"orders": sum(1 for o in orders if scoped(o)), "open_orders": sum(1 for o in orders if scoped(o) and is_open(o)),
                           "customers": len(jonah_customers)},
            "check_order": {"order": f"#{check_order['no']}", "customer": check_order["cust"]["company"], "status": check_order["status"],
                            "lines": [{"sku": p["sku"], "qty": q} for p, q in check_order["lines"]], **pdict(check_order["price"]),
                            "note": "one of its lines is written without the #"},
            "largest_order": {"order": f"#{top['no']}", "customer": top["cust"]["company"] or top["cust"]["name"], "total": d2(top["price"]["total"]),
                              "text_sort_would_put_first": f"#{top_text_no}"},
            "search_check": {"term": search_company, "expected_results": len(two_or_three[search_company]), "orders": [f"#{o['no']}" for o in sorted(two_or_three[search_company], key=lambda o: o["no"])]},
            "filter_check": {"field": "Status", "value": "Paid", "expected_results": STATUS_COUNTS["Paid"]},
            "sort_check": {"field": "Order Total", "direction": "descending", "first": f"#{top['no']}"},
            "export_check": {"rows": len(orders), "columns": ["Order #", "Customer", "Status", "Order Date", "Total"]},
            "out_of_scope_order": {"order": f"#{oos['no']}", "customer": oos["cust"]["company"], "account_manager": OTHER_AM},
            "shipped_order_for_cancel_check": f"#{sorted((o for o in orders if o['status'] == 'Shipped'), key=lambda o: o['no'])[0]['no']}",
        },
        "checks": {
            "retail_under_threshold": {"customer": r_test["name"], "lines": [[A, 2], [B, 1]], **pdict(r1)},
            "retail_free_shipping": {"customer": r_test["name"], "lines": [[A, 4], [B, 1]], **pdict(r2)},
            "wholesale_exempt": {"customer": w_exempt["company"], "lines": [[A, 12]], **pdict(w1)},
            "wholesale_taxable": {"customer": w_taxable["company"], "certificate_written": "Expired", "lines": [[A, 12]], **pdict(w2)},
            "ship_decrement": {"order": "the retail_under_threshold order", A: {"before": pa["stock"], "after": pa["stock"] - 2},
                               B: {"before": pb["stock"], "after": pb["stock"] - 1}},
            "backorder": {"sku": LOW, "stock": 3, "order_qty": 5, "customer": r_test["name"], "restock_to": 10, "stock_after_ship": 5},
        },
        "changes": {
            "1_monthly_report": {
                "report_month": f"{month_names[report_month]} 2026",
                "month": {"retail": month_block(report_month, "Retail"), "wholesale": month_block(report_month, "Wholesale")},
                "per_month_totals": {month_names[m]: round(month_block(m, "Retail")["total"] + month_block(m, "Wholesale")["total"], 2) for m in months},
                "year_total": d2(ship_total),
                "cancelled_orders_in_month_excluded": [{"order": f"#{o['no']}", "total": d2(o["price"]["total"])} for o in orders
                                                      if o["status"] == "Cancelled" and o["date"].month == report_month],
                "open_orders_in_month_excluded": sum(1 for o in orders if o["status"] in OPEN and o["date"].month == report_month),
                "restricted_month_wholesale": month_block(report_month, "Wholesale", RESTRICTED_AM),
            },
            "2_wholesale_discount": {
                "rule": "wholesale orders with goods of 1,000.00 or more get 5% off the goods; tax is on the discounted goods; shipping unchanged",
                "over": {"customer": w_taxable["company"], "lines": [[C, 90]], **pdict(d_over),
                         "goods_after_discount": d2(d_over["goods"] - d_over["discount"]),
                         "wrong_tax_if_taxed_before_discount": d2(cents(d_over["goods"] * TAX_RATE))},
                "at_threshold": {"customer": w_exempt["company"], "lines": [[C, 80]], **pdict(d_at)},
                "below": {"customer": w_exempt["company"], "lines": [[C, 79]], **pdict(d_below)},
                "retail_not_discounted": {"customer": r_test["name"], "lines": [[C, 48]], **pdict(d_retail)},
                "product_c": {"sku": C, "retail": d2(pc["retail"]), "wholesale": d2(pc["wholesale"]), "stock": pc["stock"]},
            },
            "3_on_hold": {"order_to_hold": f"#{held[0]['no']}" if held else None, "customer": held[0]["cust"]["company"] if held else None,
                          "status_before": "Paid", "open_orders_unchanged": sum(1 for o in orders if is_open(o))},
        },
    }
    return {"cust_rows": cust_rows, "prod_rows": prod_rows, "line_rows": line_rows, "counts": counts}


def main() -> None:
    seed = argparse_seed(0)
    rng = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    out = build(rng, seed)
    write_csv(os.path.join(SEED_DIR, "customers.csv"), CUSTOMER_COLUMNS, out["cust_rows"])
    write_csv(os.path.join(SEED_DIR, "products.csv"), PRODUCT_COLUMNS, out["prod_rows"])
    write_csv(os.path.join(SEED_DIR, "order_lines.csv"), ORDER_COLUMNS, out["line_rows"], bom=True)
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out["counts"], indent=2) + "\n")
    c, p, o = out["counts"]["customers"], out["counts"]["products"], out["counts"]["orders"]
    print(f"customers.csv: {c['file_rows_excluding_header']} rows -> {c['unique_customers_after_dedupe']} customers {c['per_account_manager']}")
    print(f"products.csv: {p['file_rows_excluding_header']} rows -> {p['unique_products']} products")
    print(f"order_lines.csv: {o['file_lines_excluding_header']} lines -> {o['orders']} orders; open {o['open_orders']}; "
          f"shipped sales {o['shipped_sales_total']:.2f}; restricted {o['restricted']}")


if __name__ == "__main__":
    main()
