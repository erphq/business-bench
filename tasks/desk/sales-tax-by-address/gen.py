#!/usr/bin/env python3
"""sales-tax-by-address: sales tax due per order from a ZIP-range rate table, with exemptions and freight rules.

    python gen.py [--seed N] [--naive DIR]

Business: Lumen Lab Kits in Boulder, which sells classroom and home science kits online. Its accountant keeps a
rate table by state and ZIP range for the five states where it collects, with a second sheet saying where
shipping is taxable. The owner's note lists the customers with exemption certificates.

Traps (each caught by a check, see task.yaml):
  * a ZIP inside a city range takes that range's rate, anything else in the state takes the state's
    'all other ZIPs' row; range ends are inclusive and 87571 (Taos) is not in Santa Fe's 87501-87509
                                                                        (checks: tax per order; rate per order)
  * shipping is taxed only where the second sheet says so           (check: tax per order)
  * exempt schools, a science centre and a reseller pay no tax; St. Brigid's certificate expired on 5 September
    and the homeschool co-op is not exempt                           (check: tax per order)
  * orders shipped to states that are not on the table carry no tax   (check: tax per order)
  * the ship-to is one free-text field with ZIP+4 and state names spelled out (checks: tax per order; rate per order)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

STATE_NAMES = {"CO": "Colorado", "WA": "Washington", "TX": "Texas", "AZ": "Arizona", "NM": "New Mexico", "OR": "Oregon",
               "CA": "California", "UT": "Utah", "ID": "Idaho", "NE": "Nebraska"}
RATES = [  # state, zip from, zip to, jurisdiction, rate (as text percent)
    ("CO", 80301, 80310, "Boulder", "8.845"), ("CO", 80201, 80299, "Denver", "8.81"), ("CO", 80901, 80951, "Colorado Springs", "8.20"),
    ("CO", None, None, "All other Colorado ZIPs", "4.90"),
    ("WA", 98101, 98199, "Seattle", "10.35"), ("WA", 98401, 98499, "Tacoma", "10.30"), ("WA", None, None, "All other Washington ZIPs", "8.70"),
    ("TX", 78701, 78799, "Austin", "8.25"), ("TX", 75201, 75398, "Dallas", "8.25"), ("TX", None, None, "All other Texas ZIPs", "6.75"),
    ("AZ", 85001, 85099, "Phoenix", "8.60"), ("AZ", 85701, 85775, "Tucson", "8.70"), ("AZ", None, None, "All other Arizona ZIPs", "6.10"),
    ("NM", 87101, 87199, "Albuquerque", "7.8125"), ("NM", 87501, 87509, "Santa Fe", "8.1875"), ("NM", None, None, "All other New Mexico ZIPs", "6.0625"),
]
SHIP_TAXABLE = {"CO": False, "WA": True, "TX": True, "AZ": False, "NM": True}
PLACES = {  # state: [(city, zip), ...] ; zips chosen to exercise ranges and the defaults
    "CO": [("Boulder", 80302), ("Boulder", 80304), ("Boulder", 80310), ("Denver", 80205), ("Denver", 80218), ("Colorado Springs", 80918),
           ("Colorado Springs", 80951), ("Louisville", 80027), ("Longmont", 80501), ("Fort Collins", 80521), ("Durango", 81301)],
    "WA": [("Seattle", 98103), ("Seattle", 98115), ("Tacoma", 98405), ("Tacoma", 98499), ("Spokane", 99201), ("Bellingham", 98225), ("Olympia", 98501)],
    "TX": [("Austin", 78704), ("Austin", 78745), ("Dallas", 75214), ("Houston", 77002), ("San Antonio", 78205), ("Round Rock", 78664)],
    "AZ": [("Phoenix", 85016), ("Phoenix", 85032), ("Tucson", 85719), ("Flagstaff", 86001), ("Mesa", 85201), ("Tempe", 85281)],
    "NM": [("Albuquerque", 87102), ("Albuquerque", 87110), ("Santa Fe", 87505), ("Taos", 87571), ("Las Cruces", 88001)],
    "OR": [("Portland", 97209), ("Eugene", 97401)], "CA": [("Sacramento", 95814)], "UT": [("Salt Lake City", 84101)],
    "ID": [("Boise", 83702)], "NE": [("Omaha", 68102)],
}
EXEMPT = [  # account, name, state, city, zip, kind
    ("C-1004", "Aspen Ridge Elementary", "CO", "Boulder", 80303, "school"),
    ("C-1011", "Rio Grande STEM Academy", "NM", "Albuquerque", 87102, "school"),
    ("C-1019", "Puget Sound Science Center", "WA", "Seattle", 98109, "nonprofit"),
    ("C-1023", "Books & Beakers", "TX", "Austin", 78704, "reseller"),
    ("C-1030", "St. Brigid Academy", "AZ", "Phoenix", 85016, "expired"),
]
EXPIRED_ACCOUNT, EXPIRED_ON = "C-1030", date(2026, 9, 5)
COOP = ("C-1037", "Mesa Verde Homeschool Co-op", "CO", "Durango", 81301)


def rate_for(state: str, z: int):
    rows = [x for x in RATES if x[0] == state]
    if not rows:
        return None, None
    for st, a, b, jur, rate in rows:
        if a is not None and a <= z <= b:
            return Decimal(rate) / 100, (jur, rate)
    st, a, b, jur, rate = [x for x in rows if x[1] is None][0]
    return Decimal(rate) / 100, (jur, rate)


def build(seed: int) -> dict:
    r = rng(seed)
    orders = []
    names = people(r, 120)
    n = 0

    lines = {}

    def add(cust, acct, state, city, z, d=None):
        nonlocal n
        line = lines.setdefault(acct, address(r)[0])
        sub = money(r, 39, 640)
        ship = 0.0 if sub >= 150 and r.random() < 0.7 else r.choice([8.95, 12.50, 14.95, 18.75, 24.50])
        orders.append({"cust": cust, "acct": acct, "state": state, "city": city, "zip": z, "line": line, "sub": sub, "ship": ship,
                       "date": d or date(2026, 9, r.randint(1, 12)), "plus4": r.random() < 0.2, "style": r.randrange(3)})
        n += 1

    for acct, name, st, city, z, kind in EXEMPT:
        if kind == "expired":
            add(name, acct, st, city, z, date(2026, 9, r.randint(1, 4)))
            add(name, acct, st, city, z, date(2026, 9, r.randint(6, 9)))
            add(name, acct, st, city, z, date(2026, 9, r.randint(10, 12)))
        else:
            for _ in range(r.randint(2, 3)):
                add(name, acct, st, city, z)
    for _ in range(2):
        add(COOP[1], COOP[0], COOP[2], COOP[3], COOP[4])
    # make sure every interesting place is used at least once
    must = [("CO", "Boulder", 80310), ("CO", "Colorado Springs", 80951), ("WA", "Tacoma", 98499), ("NM", "Taos", 87571),
            ("NM", "Santa Fe", 87505), ("CO", "Longmont", 80501), ("TX", "Houston", 77002), ("AZ", "Flagstaff", 86001),
            ("OR", "Portland", 97209), ("CA", "Sacramento", 95814)]
    acct_no = 2000
    for st, city, z in must:
        f, l = names[acct_no - 2000]
        add(f"{f} {l}", f"C-{acct_no}", st, city, z)
        acct_no += 1
    states = list(PLACES)
    weights = [30, 14, 12, 10, 10, 5, 4, 3, 3, 2]
    while len(orders) < 92:
        st = r.choices(states, weights=weights)[0]
        city, z = r.choice(PLACES[st])
        f, l = names[acct_no - 2000]
        add(f"{f} {l}", f"C-{acct_no}", st, city, z)
        acct_no += 1
    orders.sort(key=lambda o: (o["date"], o["acct"], o["sub"]))
    for i, o in enumerate(orders):
        o["id"] = f"LLK-{30412 + i}"
    exempt_accts = {e[0] for e in EXEMPT if e[5] != "expired"}
    for o in orders:
        rate, jur = rate_for(o["state"], o["zip"])
        o["rate"], o["jur"] = rate, jur
        exempt = o["acct"] in exempt_accts or (o["acct"] == EXPIRED_ACCOUNT and o["date"] <= EXPIRED_ON)
        o["exempt"] = exempt
        if rate is None or exempt:
            o["tax"] = Decimal("0.00")
            continue
        base = Decimal(str(o["sub"])) + (Decimal(str(o["ship"])) if SHIP_TAXABLE[o["state"]] else Decimal("0"))
        o["exact"] = base * rate
        o["tax"] = (base * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"orders": orders}


def naive_tax(o) -> Decimal:
    """First table row for the state, shipping always taxed, no exemptions."""
    rows = [x for x in RATES if x[0] == o["state"]]
    if not rows:
        return Decimal("0.00")
    rate = Decimal(rows[0][4]) / 100
    return ((Decimal(str(o["sub"])) + Decimal(str(o["ship"]))) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def acceptable(d: dict) -> bool:
    os_ = d["orders"]
    # no half-cent ties, so the rounding rule never decides a check
    for o in os_:
        if "exact" in o:
            frac = (o["exact"] * 100) % 1
            if abs(frac - Decimal("0.5")) < Decimal("0.02"):
                return False
    # shipping matters on some taxable orders in freight-taxable states and on some in freight-exempt states
    if sum(1 for o in os_ if o["ship"] and o["rate"] and not o["exempt"] and SHIP_TAXABLE[o["state"]]) < 5:
        return False
    if sum(1 for o in os_ if o["ship"] and o["rate"] and not o["exempt"] and not SHIP_TAXABLE[o["state"]]) < 5:
        return False
    if not any(o["ship"] for o in os_ if o["acct"] == EXPIRED_ACCOUNT and o["date"] > EXPIRED_ON):
        pass
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["order_id", "state", "zip", "rate", "tax"]
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        rows = []
        for o in d["orders"]:
            rows_st = [x for x in RATES if x[0] == o["state"]]
            rows.append([o["id"], o["state"], f"{o['zip']:05d}", f"{rows_st[0][4]}%" if rows_st else "0%", f"{naive_tax(o):.2f}"])
        write_csv(os.path.join(naive_dir, "orders_tax.csv"), header, rows)
        return
    ws, ref, sol = task_dirs(HERE)

    def ship_to(o):
        z = f"{o['zip']:05d}" + (f"-{(o['zip'] * 7) % 9000 + 1000}" if o["plus4"] else "")
        st = o["state"] if o["style"] != 2 else STATE_NAMES[o["state"]]
        if o["style"] == 1:
            return f"{o['line']} {o['city']} {st} {z}"
        return f"{o['line']}, {o['city']}, {st} {z}"

    rows = [[o["id"], o["date"].strftime("%m/%d/%Y"), o["cust"], o["acct"], ship_to(o), f"{o['sub']:.2f}", f"{o['ship']:.2f}",
             r_pay] for o, r_pay in zip(d["orders"], [("Card", "PO / Net 30", "Card", "Card", "ACH")[i % 5] for i in range(len(d["orders"]))])]
    write_csv(os.path.join(ws, "orders_2026-09-01_to_2026-09-12.csv"),
              ["Order", "Order Date", "Customer", "Account", "Ship To", "Subtotal", "Shipping", "Payment"], rows)
    write_xlsx(os.path.join(ws, "sales_tax_table_2026.xlsx"), {
        "Rates": {"merged_title": "Combined sales tax rates by ship-to ZIP (effective 1 July 2026)",
                  "header": ["State", "ZIP from", "ZIP to", "Jurisdiction", "Combined rate"],
                  "rows": [[st, a if a else "", b if b else "", jur, f"{rate}%"] for st, a, b, jur, rate in RATES],
                  "widths": {"A": 8, "B": 10, "C": 10, "D": 30, "E": 14}},
        "Shipping": {"header": ["State", "Is shipping taxable?", "Comment"],
                     "rows": [[st, "Yes" if v else "No", "when shown as a separate charge on the invoice" if not v else "delivery charges are part of the sale"]
                              for st, v in SHIP_TAXABLE.items()], "widths": {"B": 20, "C": 48}},
    }, creator="Kessler & Moore CPAs")
    write_text(os.path.join(ws, "note_from_carmen.txt"),
               "Sales tax on the September orders\n"
               "\n"
               "Before I invoice the first batch of September orders I need the sales tax on each one. The rate table\n"
               "from the accountants is in the folder. We only collect in the five states on it; everywhere else is\n"
               "no tax. Inside a state, use the city row when the ship-to ZIP falls between its From and To (both ends\n"
               "count), otherwise the 'all other ZIPs' row for that state. The Shipping sheet says whether shipping\n"
               "gets taxed along with the kits.\n"
               "\n"
               "These customers have exemption certificates on file and pay no tax:\n"
               "  C-1004 Aspen Ridge Elementary\n"
               "  C-1011 Rio Grande STEM Academy\n"
               "  C-1019 Puget Sound Science Center\n"
               "  C-1023 Books & Beakers (resale certificate)\n"
               "  C-1030 St. Brigid Academy - their certificate expired on 5 September and they haven't sent the new one,\n"
               "         so anything they ordered after the 5th is taxable for now.\n"
               "The Mesa Verde Homeschool Co-op keeps asking, but a co-op isn't a school and they don't have a\n"
               "certificate, so they pay tax.\n"
               "\n"
               "Round the tax on each order to the cent. Save it as orders_tax.csv with order_id, state (two letters),\n"
               "zip (five digits), rate (the combined rate you used, 0 where we don't collect) and tax.\n"
               "\n"
               "Carmen\n")

    ref_rows = [[o["id"], o["state"], f"{o['zip']:05d}", f"{o['jur'][1]}%" if o["rate"] is not None else "0%",
                 f"{o['tax']:.2f}"] for o in d["orders"]]
    write_csv(os.path.join(ref, "orders_tax.csv"), header, ref_rows)
    write_csv(os.path.join(sol, "orders_tax.csv"), header, ref_rows)
    write_csv(os.path.join(ref, "rates_expected.csv"), ["order_id", "rate_fraction", "graded"],
              [[o["id"], f"{o['rate']:.6f}" if o["rate"] is not None else "0", "no" if o["exempt"] else "yes"] for o in d["orders"]])
    must = [o["id"] for o in d["orders"] if o["acct"] in (EXPIRED_ACCOUNT, COOP[0]) or o["zip"] in (80310, 80951, 98499, 87571)]
    write_json(os.path.join(ref, "notes.json"), {"must_match": must, "tax_total": f"{sum(o['tax'] for o in d['orders']):.2f}"})

    write_task_yaml(HERE, {
        "id": "sales-tax-by-address", "track": "desk", "category": "spreadsheet",
        "title": "Sales tax on each September order",
        "ask": ("I need the sales tax worked out on each of this month's orders before I invoice them. Use the accountants' "
                "rate table and save orders_tax.csv - my note has the rest.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "rates go by ZIP range inside each state with an 'all other ZIPs' row; the first row for a state gives "
            "Boulder's rate to Durango and Longmont, both range ends count (80310, 80951, 98499), and Taos 87571 "
            "shares Santa Fe's 875 prefix but is outside 87501-87509 (checks: tax per order; rate per order)",
            "shipping is taxed only in Washington, Texas and New Mexico per the Shipping sheet; taxing it everywhere "
            "or nowhere moves every order with a shipping charge (check: tax per order)",
            "four exempt customers pay nothing, St. Brigid Academy's certificate expired on 5 September so its two "
            "later orders are taxable, and the homeschool co-op asks but is not exempt (check: tax per order)",
            "Oregon, California, Utah, Idaho and Nebraska orders are not on the table and carry no tax "
            "(checks: tax per order; rate per order)",
            "the Ship To is one free-text field: some addresses spell the state out ('New Mexico'), some drop the "
            "commas, and some carry ZIP+4, so a split on commas or the last token misreads state and ZIP "
            "(checks: tax per order; rate per order)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "orders_tax.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every order", "path": "orders_tax.csv", "column": "order_id",
             "ref": "orders_tax.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "orders_tax.csv", "equals_ref": "orders_tax.csv"},
            {"type": "csv_values_match", "name": "tax per order", "path": "orders_tax.csv", "ref": "orders_tax.csv",
             "key": "order_id", "columns": ["tax"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0,
             "must_match_keys": must},
            {"type": "custom", "name": "rate per order", "module": "check.py"},
        ],
    })
    print(f"seed={seed} orders={len(d['orders'])} tax_total={sum(o['tax'] for o in d['orders'])}")
    wrong = sum(1 for o in d["orders"] if naive_tax(o) != o["tax"])
    print("naive wrong:", wrong)


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
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
