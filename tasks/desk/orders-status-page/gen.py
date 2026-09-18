#!/usr/bin/env python3
"""orders-status-page: an online plant shop's week of orders as one HTML page with status counts and revenue.

    python gen.py [--seed N] [--naive DIR]

Business: a small online houseplant shop that packs and ships from a greenhouse. The storefront exports one row
per line item with the platform's fulfilment codes, repeats order-level fields (shipping) on every line, and
includes the owner's own test orders.

Traps (each caught by a check, see task.yaml):
  * nine platform codes map to six statuses the team uses                    (checks: page structure: status per order, status counts)
  * cancelled and voided orders stay listed and counted but earn nothing     (checks: revenue this week; page structure: revenue line)
  * the export is one row per line item                                      (checks: page structure: one row per order, order totals)
  * shipping is repeated on every line of an order                           (checks: page structure: order totals; revenue this week)
  * orders tagged test are the owner checking the checkout                  (checks: test orders left off; page structure: one row per order)
  * last week's export is in the folder                                      (checks: page structure: one row per order; revenue this week)
"""
from __future__ import annotations
import argparse
import html
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CODES = {"AWAITING_PAYMENT": "Awaiting payment", "PAID_UNFULFILLED": "To pack", "PARTIALLY_FULFILLED": "To pack",
         "ON_HOLD": "On hold", "FULFILLED": "Shipped", "IN_TRANSIT": "Shipped", "DELIVERED": "Delivered",
         "CANCELLED": "Cancelled", "VOIDED": "Cancelled"}
STATUSES = ["Awaiting payment", "To pack", "On hold", "Shipped", "Delivered", "Cancelled"]
LABELS = {"Awaiting payment": r"\bawaiting payment\b", "To pack": r"\bto pack\b", "On hold": r"\bon hold\b",
          "Shipped": r"\bshipped\b", "Delivered": r"\bdelivered\b", "Cancelled": r"\bcancell?ed\b"}
PLANTS = [("Monstera deliciosa 6in", 3400), ("Snake plant Laurentii 4in", 1800), ("Pothos Marble Queen 4in", 1400),
          ("Fiddle leaf fig 10in", 6800), ("ZZ plant 6in", 2900), ("Calathea orbifolia 6in", 3600),
          ("String of pearls 4in hanging", 2200), ("Rubber plant Burgundy 8in", 4400), ("Hoya carnosa 4in", 1900),
          ("Peace lily 6in", 2600), ("Bird of paradise 10in", 7200), ("Terracotta pot 6in", 900),
          ("Ceramic planter white 8in", 2400), ("Houseplant potting mix 8qt", 1300), ("Moisture meter", 1100)]


def build(seed: int) -> dict:
    r = rng(seed)
    start = datetime(2026, 9, 7, 6, 0)
    names = people(r, 60)
    orders = []
    n = 44
    base = 4300 + r.randint(0, 400)
    code_plan = (["AWAITING_PAYMENT"] * 3 + ["PAID_UNFULFILLED"] * 7 + ["PARTIALLY_FULFILLED"] * 2 + ["ON_HOLD"] * 2 +
                 ["FULFILLED"] * 9 + ["IN_TRANSIT"] * 6 + ["DELIVERED"] * 11 + ["CANCELLED"] * 2 + ["VOIDED"] * 2)
    r.shuffle(code_plan)
    for i in range(n):
        f, l = names[i]
        lines = []
        for _ in range(r.choice([1, 1, 1, 2, 2, 3, 4])):
            plant, cents = r.choice(PLANTS)
            if any(x[0] == plant for x in lines):
                continue
            lines.append((plant, r.choice([1, 1, 1, 2, 3]), cents))
        sub = sum(q * c for _, q, c in lines)
        ship = 0 if sub >= 7500 else r.choice([895, 1295])
        orders.append({"no": f"GR-{base + i}", "customer": f"{f} {l}", "code": code_plan[i], "lines": lines,
                       "ship": ship, "created": start + timedelta(minutes=r.randint(0, 7 * 24 * 60 - 400)), "test": False})
    # two test orders placed by the owner, one of them still unfulfilled
    tests = []
    for j, code in enumerate(["PAID_UNFULFILLED", "CANCELLED"]):
        plant, cents = r.choice(PLANTS)
        tests.append({"no": "", "customer": "Hana Okafor", "code": code, "lines": [(plant, 1, cents)],
                      "ship": 895, "created": start + timedelta(days=2 + 3 * j, hours=5, minutes=r.randint(0, 50)), "test": True})
    for i, o in enumerate(sorted(orders + tests, key=lambda o: o["created"])):
        o["no"] = f"GR-{base + i}"
    orders.sort(key=lambda o: o["created"])
    for o in orders + tests:
        o["status"] = CODES[o["code"]]
        o["total"] = sum(q * c for _, q, c in o["lines"]) + o["ship"]
    real = orders
    revenue = sum(o["total"] for o in real if o["status"] != "Cancelled")
    counts = {s: sum(1 for o in real if o["status"] == s) for s in STATUSES}
    # last week's export: different orders
    prev = []
    for i in range(30):
        f, l = names[45 + (i % 15)]
        plant, cents = r.choice(PLANTS)
        prev.append({"no": f"GR-{base - 30 + i}", "customer": f"{f} {l}", "code": r.choice(["DELIVERED", "IN_TRANSIT", "FULFILLED"]),
                     "lines": [(plant, 1, cents)], "ship": 895, "created": start - timedelta(days=7) + timedelta(hours=5 * i), "test": False})
    return {"orders": real, "tests": tests, "revenue": revenue, "counts": counts, "prev": prev}


def acceptable(d: dict) -> bool:
    orders = d["orders"]
    multi = [o for o in orders if len(o["lines"]) > 1]
    if len(multi) < 12:
        return False
    if not any(o["status"] == "Cancelled" and len(o["lines"]) > 1 for o in orders):
        return False
    if sum(1 for o in orders if len(o["lines"]) > 1 and o["ship"] > 0) < 4:
        return False
    # the Hana Okafor test customer must be the only order under that name
    if any(o["customer"] == "Hana Okafor" for o in orders):
        return False
    customers = [o["customer"] for o in orders]
    return len(set(customers)) == len(customers)


def usd(c: int) -> str:
    return f"${c / 100:,.2f}"


def export_rows(orders: list, r) -> list[list]:
    rows = []
    for o in orders:
        for plant, q, c in o["lines"]:
            rows.append([o["no"], o["created"].strftime("%Y-%m-%d %H:%M"), o["customer"], o["code"],
                         "test" if o["test"] else r.choice(["", "", "", "gift", "repeat customer", ""]),
                         plant, q, f"{c / 100:.2f}", f"{o['ship'] / 100:.2f}"])
    return rows


def page_html(d: dict) -> str:
    orders, counts = d["orders"], d["counts"]
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           "<title>Orders this week - Greenhouse Row</title>", "<style>",
           "body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;margin:24px;color:#1f2a1f}",
           ".counts{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}",
           ".counts div{border:1px solid #9bb59b;padding:8px 12px}",
           "table{border-collapse:collapse;width:100%}", "th,td{padding:5px 8px;border-bottom:1px solid #dde5dd;text-align:left}",
           "td.n{text-align:right}", "</style>", "</head>", "<body>",
           "<h1>Orders this week (7 to 13 September 2026)</h1>",
           f"<p><strong>Revenue this week: {usd(d['revenue'])}</strong> from {sum(1 for o in orders if o['status'] != 'Cancelled')} "
           f"orders (cancelled orders not counted). {len(orders)} orders in total.</p>",
           '<div class="counts">']
    for s in STATUSES:
        out.append(f"<div>{s}: <strong>{counts[s]}</strong></div>")
    out += ["</div>", "<table><thead><tr><th>Order</th><th>Placed</th><th>Customer</th><th>Items</th><th>Status</th>"
            "<th class=\"n\">Order total</th></tr></thead><tbody>"]
    for o in orders:
        items = sum(q for _, q, _ in o["lines"])
        out.append(f"<tr><td>{o['no']}</td><td>{o['created'].strftime('%a %d %b')}</td><td>{html.escape(o['customer'])}</td>"
                   f"<td class=\"n\">{items}</td><td>{o['status']}</td><td class=\"n\">{usd(o['total'])}</td></tr>")
    out += ["</tbody></table>", "</body>", "</html>", ""]
    return "\n".join(out)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    orders, tests = d["orders"], d["tests"]
    r = rng(seed + 13)
    rows = export_rows(sorted(orders + tests, key=lambda o: o["created"]), r)
    if naive_dir:
        write_naive(d, rows, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    header = ["Order", "Created at", "Customer", "Fulfillment status", "Tags", "Lineitem name", "Lineitem quantity",
              "Lineitem price", "Shipping"]
    write_csv(os.path.join(ws, "orders_export_2026-09-07_to_2026-09-13.csv"), header, rows, bom=True)
    write_csv(os.path.join(ws, "orders_export_2026-08-31_to_2026-09-06.csv"), header, export_rows(d["prev"], r), bom=True)
    write_text(os.path.join(ws, "note_from_hana.txt"),
               "From: Hana Okafor\nTo: you\nDate: Sun, 13 Sep 2026 18:10\nSubject: weekly orders page\n\n"
               "Every Monday the packing team asks me where things stand, so I would like a page I can leave open on "
               "the packing-bench laptop: one HTML file, no logins, nothing it has to load, and no scripts - that laptop's "
               "browser is locked down.\n\n"
               "At the top, how many orders are in each status, and the week's revenue. Under that a table with one row "
               "per order: order number, customer, status and the order total.\n\n"
               "The store uses its own codes for status. We talk about orders like this:\n"
               "  AWAITING_PAYMENT = Awaiting payment\n"
               "  PAID_UNFULFILLED and PARTIALLY_FULFILLED = To pack (a part-shipped order still has something to pack)\n"
               "  ON_HOLD = On hold\n"
               "  FULFILLED and IN_TRANSIT = Shipped\n"
               "  DELIVERED = Delivered\n"
               "  CANCELLED and VOIDED = Cancelled\n\n"
               "Order total is the items plus shipping. The export repeats the shipping charge on every line of an "
               "order, but we only charge it once.\n\n"
               "Cancelled orders stay in the table and in the counts so the team knows not to pack them, but they are "
               "not revenue. Everything else is.\n\n"
               "Anything tagged test is me trying the checkout - leave those off completely.\n\n"
               "Hana\n")
    write_json(os.path.join(ref, "expected.json"), {
        "orders": [{"no": o["no"], "customer": o["customer"], "status": o["status"], "total": o["total"] / 100}
                   for o in orders],
        "tests": [o["no"] for o in tests], "previous": [o["no"] for o in d["prev"]],
        "counts": d["counts"], "revenue": d["revenue"] / 100, "labels": LABELS,
    })
    write_text(os.path.join(sol, "index.html"), page_html(d))
    multi_c = next(o for o in orders if o["status"] == "Cancelled" and len(o["lines"]) > 1)
    traps = [
        "the export carries nine platform codes that map to six statuses (two codes each for To pack, Shipped and "
        "Cancelled); counting the raw codes splits those columns (checks: page structure: status counts; page "
        "structure: status per order)",
        f"four orders are CANCELLED or VOIDED; they stay in the table and the counts but not in revenue, and "
        f"{multi_c['no']} has several lines (checks: revenue this week; page structure: revenue line)",
        "the export is one row per line item, so a row-per-line table repeats orders and inflates every count "
        "(checks: page structure: one row per order; page structure: status counts)",
        "shipping is repeated on every line of a multi-line order; adding it per line overstates order totals and "
        "revenue (checks: page structure: order totals; revenue this week)",
        "two orders tagged test (one of them CANCELLED, one PAID_UNFULFILLED) are the owner trying the checkout and "
        "come off the page (checks: test orders left off; page structure: one row per order)",
        "last week's export sits beside this week's with other order numbers (checks: page structure: one row per "
        "order; revenue this week)",
    ]
    write_task_yaml(HERE, {
        "id": "orders-status-page", "track": "desk", "category": "tooling",
        "title": "This week's orders page for the packing bench",
        "ask": "Hana wants this week's orders as a page for the packing-bench laptop - her note has what goes on it. "
               "Please save it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "every order listed", "path": "index.html",
             "phrases": [o["no"] for o in orders]},
            {"type": "text_not_contains", "name": "test orders left off", "path": "index.html",
             "phrases": [o["no"] for o in tests] + [o["no"] for o in d["prev"][:10]]},
            {"type": "text_numbers_present", "name": "revenue this week", "path": "index.html",
             "numbers": [d["revenue"] / 100], "rel_tol": 0.0000001},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} orders={len(orders)} revenue={d['revenue'] / 100:.2f} counts={d['counts']}")


def write_naive(d: dict, rows: list, out: str) -> None:
    """The obvious reading: a row per export line with the raw code, counts of raw codes, revenue = sum over every
    line of quantity x price + shipping, test and cancelled included."""
    os.makedirs(out, exist_ok=True)
    counts = {}
    revenue = 0.0
    for x in rows:
        counts[x[3]] = counts.get(x[3], 0) + 1
        revenue += int(x[6]) * float(x[7]) + float(x[8])
    parts = ["<html><body><h1>Orders</h1>", f"<p>Revenue: ${revenue:,.2f}</p><ul>"]
    parts += [f"<li>{k}: {v}</li>" for k, v in counts.items()]
    parts.append("</ul><table>")
    for x in rows:
        parts.append(f"<tr><td>{x[0]}</td><td>{html.escape(x[2])}</td><td>{x[3]}</td><td>{int(x[6]) * float(x[7]) + float(x[8]):.2f}</td></tr>")
    parts.append("</table></body></html>\n")
    write_text(os.path.join(out, "index.html"), "\n".join(parts))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(2000):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
