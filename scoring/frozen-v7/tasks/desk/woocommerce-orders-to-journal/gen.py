#!/usr/bin/env python3
"""woocommerce-orders-to-journal: a coffee roaster's August WooCommerce order export turned into a journal import.

    python gen.py [--seed N]

Business: Nightjar Coffee Roasters sells beans, brewing gear, mugs and subscriptions online. Grace, the outside
bookkeeper, wants August's web sales as journal entries she can import into the books, one journal per paid order
and one per refund, following her chart of accounts.

Traps (each caught by a check, see task.yaml):
  * the export is one row per line item and repeats the order-level shipping, tax, discount, total and refund on
    every item row; summing those columns per row inflates them               (checks: journals balance; account amounts per journal)
  * only paid orders are booked: completed and processing yes; cancelled, failed, pending payment and on-hold
    (bank transfer never arrived) no                                           (checks: journal numbers; row count)
  * a fully refunded order still gets its sale journal plus a refund journal on the refund date; partial refunds
    on completed orders get a refund journal for the refunded amount; a refund dated 2 September belongs to next
    month's file                                                               (checks: journal numbers; account amounts per journal; journal dates)
  * the cart discount is a debit to Sales Discounts, not netted out of product sales  (check: account amounts per journal)
  * the clearing account depends on the payment method (Stripe, PayPal, bank transfer) (check: account amounts per journal)
  * subscription products are tagged "Coffee > Blends, Subscriptions" and book to Subscription Sales, not Coffee
                                                                               (check: account amounts per journal)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["Journal No", "Journal Date", "Account Code", "Description", "Debit", "Credit"]
ACCOUNTS = {"1000": "Business Checking", "1210": "Stripe Clearing", "1220": "PayPal Clearing", "2200": "Sales Tax Payable",
            "4000": "Coffee Sales", "4010": "Equipment Sales", "4020": "Subscription Sales", "4030": "Merchandise Sales",
            "4100": "Shipping Income", "4900": "Sales Discounts", "4950": "Sales Returns & Refunds"}
# name, sku, price, categories, account
CATALOG = [("Ethiopia Guji - 12oz", "COF-ETH-12", 19.50, "Coffee > Single Origin", "4000"),
           ("Colombia Huila - 12oz", "COF-COL-12", 18.00, "Coffee > Single Origin", "4000"),
           ("Kenya Nyeri - 12oz", "COF-KEN-12", 21.00, "Coffee > Single Origin", "4000"),
           ("Night Owl Espresso Blend - 12oz", "COF-NOE-12", 16.50, "Coffee > Blends", "4000"),
           ("House Blend - 2lb", "COF-HSE-2LB", 38.00, "Coffee > Blends", "4000"),
           ("Decaf Swiss Water - 12oz", "COF-DEC-12", 17.50, "Coffee > Single Origin", "4000"),
           ("Pour-over Dripper", "EQP-DRIP", 28.00, "Brewing Equipment", "4010"),
           ("Gooseneck Kettle", "EQP-KETTLE", 64.00, "Brewing Equipment", "4010"),
           ("Hand Burr Grinder", "EQP-GRIND", 119.00, "Brewing Equipment", "4010"),
           ("Paper Filters (100)", "EQP-FILT", 7.50, "Brewing Equipment", "4010"),
           ("Coffee Subscription - 2 bags/mo", "SUB-2BAG", 34.00, "Coffee > Blends, Subscriptions", "4020"),
           ("Coffee Subscription - 1 bag/mo", "SUB-1BAG", 18.00, "Coffee > Single Origin, Subscriptions", "4020"),
           ("Nightjar Mug", "MER-MUG", 16.00, "Merch", "4030"),
           ("Canvas Tote", "MER-TOTE", 22.00, "Merch", "4030")]
PAY = {"stripe": ("Credit Card (Stripe)", "1210"), "paypal": ("PayPal", "1220"), "bank": ("Direct bank transfer", "1000")}
STATES = ["CO"] * 5 + ["CA", "TX", "NY", "WA", "OR", "IL", "AZ", "UT"]
CO_RATE = 0.041


def money2(x: float) -> float:
    return float(f"{x + 1e-9:.2f}")


def build(seed: int) -> dict:
    r = rng(seed)
    orders = []
    n = 62
    ppl = people(r, n)
    start = 10871 + r.randint(0, 40)
    others = ["completed"] * 44 + ["cancelled"] * 3 + ["failed"] * 3 + ["on-hold"] * 3 + ["pending"] * 3
    r.shuffle(others)
    for p in sorted(r.sample(range(5, 40), 2)):
        others.insert(p, "refunded")
    plan_status = others + ["processing"] * 4  # paid, not yet shipped: the last orders of the month
    for k in range(n):
        f, l = ppl[k]
        dt = datetime(2026, 8, 1, 6, 0) + timedelta(minutes=int(k * (30 * 24 * 60 / n)) + r.randint(0, 300))
        o = {"no": str(start + k), "dt": dt, "customer": f"{f} {l}", "state": r.choice(STATES), "status": plan_status[k], "tags": set(),
             "refund": 0.0, "refund_date": None}
        items = []
        for sku_i in r.sample(range(len(CATALOG)), r.choice([1, 1, 2, 2, 3, 4])):
            name, sku, price, cats, acct = CATALOG[sku_i]
            qty = r.choice([1, 1, 1, 2, 3]) if not sku.startswith(("EQP-GRIND", "EQP-KETTLE", "SUB-")) else 1
            items.append({"name": name, "sku": sku, "price": price, "cats": cats, "acct": acct, "qty": qty, "sub": money2(price * qty)})
        o["items"] = items
        o["pay"] = r.choice(["stripe"] * 7 + ["paypal"] * 3)
        o["coupon"] = r.random() < 0.18
        orders.append(o)
    # bank transfers: on-hold ones never paid, one completed paid by transfer
    for o in orders:
        if o["status"] == "on-hold":
            o["pay"] = "bank"
    paid_bank = next(o for o in orders if o["status"] == "completed")
    paid_bank["pay"] = "bank"; paid_bank["tags"].add("bank")
    # guarantee a subscription line, a multi-category order with a discount, and a PayPal order among completed ones
    comp = [o for o in orders if o["status"] == "completed" and o is not paid_bank]
    sub_o = comp[1]
    if not any(i["sku"].startswith("SUB-") for i in sub_o["items"]):
        name, sku, price, cats, acct = CATALOG[10]
        sub_o["items"].append({"name": name, "sku": sku, "price": price, "cats": cats, "acct": acct, "qty": 1, "sub": price})
    disc_o = comp[2]
    disc_o["coupon"] = True
    if len({i["acct"] for i in disc_o["items"]}) < 2:
        name, sku, price, cats, acct = CATALOG[8] if disc_o["items"][0]["acct"] != "4010" else CATALOG[4]
        disc_o["items"].append({"name": name, "sku": sku, "price": price, "cats": cats, "acct": acct, "qty": 1, "sub": price})
    comp[3]["pay"] = "paypal"
    for o in orders:
        o["subtotal"] = money2(sum(i["sub"] for i in o["items"]))
        o["discount"] = money2(o["subtotal"] * 0.10) if o["coupon"] else 0.0
        o["shipping"] = 0.0 if o["subtotal"] >= 60 else 7.95
        o["tax"] = money2((o["subtotal"] - o["discount"]) * CO_RATE) if o["state"] == "CO" else 0.0
        o["total"] = money2(o["subtotal"] - o["discount"] + o["shipping"] + o["tax"])
        if any(i["sku"].startswith("SUB-") for i in o["items"]):
            o["tags"].add("subscription")
        if o["discount"]:
            o["tags"].add("discount")
        if len(o["items"]) > 1:
            o["tags"].add("multi")
        if o["pay"] == "paypal":
            o["tags"].add("paypal")
    # refunds
    for o in [o for o in orders if o["status"] == "refunded"]:
        o["refund"] = o["total"]; o["refund_date"] = (o["dt"] + timedelta(days=r.randint(2, 6))).date(); o["tags"].add("refund")
    early = [o for o in comp if o["dt"].day <= 24 and o is not sub_o and o is not disc_o]
    for o in early[4:6]:
        it = o["items"][0]
        o["refund"] = money2(it["price"]); o["refund_date"] = (o["dt"] + timedelta(days=r.randint(3, 6))).date(); o["tags"].add("refund")
    late = next(o for o in reversed(comp) if o["dt"].day >= 26 and o is not sub_o and o is not disc_o and not o["refund"])
    late["refund"] = money2(late["items"][0]["price"]); late["refund_date"] = date(2026, 9, 2); late["tags"].add("september_refund")
    return {"orders": orders}


def journal_lines(o) -> list[tuple]:
    """(journal_no, date, account, description, debit, credit) for the sale journal and any August refund journal."""
    lines = []
    if o["status"] not in ("completed", "processing", "refunded"):
        return lines
    jn, d = f"WC-{o['no']}", o["dt"].date().isoformat()
    pay_title, clearing = PAY[o["pay"]]
    lines.append((jn, d, clearing, f"Order #{o['no']} - {pay_title}", o["total"], 0.0))
    if o["discount"]:
        lines.append((jn, d, "4900", f"Order #{o['no']} - discount", o["discount"], 0.0))
    by_acct: dict[str, float] = {}
    for i in o["items"]:
        by_acct[i["acct"]] = money2(by_acct.get(i["acct"], 0.0) + i["sub"])
    for acct in sorted(by_acct):
        lines.append((jn, d, acct, f"Order #{o['no']} - {ACCOUNTS[acct].lower()}", 0.0, by_acct[acct]))
    if o["shipping"]:
        lines.append((jn, d, "4100", f"Order #{o['no']} - shipping", 0.0, o["shipping"]))
    if o["tax"]:
        lines.append((jn, d, "2200", f"Order #{o['no']} - sales tax", 0.0, o["tax"]))
    if o["refund"] and o["refund_date"] <= date(2026, 8, 31):
        rj, rd = f"WC-{o['no']}-R", o["refund_date"].isoformat()
        lines.append((rj, rd, "4950", f"Refund on order #{o['no']}", o["refund"], 0.0))
        lines.append((rj, rd, clearing, f"Refund on order #{o['no']} - {pay_title}", 0.0, o["refund"]))
    return lines


def fmt(x: float) -> str:
    return "" if not x else f"{x:.2f}"


def emit(seed: int) -> None:
    d = build(seed)
    orders = d["orders"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 17)
    rows = []
    for o in orders:
        for i in o["items"]:
            rows.append([o["no"], o["dt"].strftime("%Y-%m-%d %H:%M:%S"), o["status"], PAY[o["pay"]][0], o["customer"], o["state"], i["sku"], i["name"],
                         i["cats"], i["qty"], f"{i['price']:.2f}", f"{i['sub']:.2f}", f"{o['discount']:.2f}", f"{o['shipping']:.2f}",
                         f"{o['tax']:.2f}", f"{o['total']:.2f}", f"{o['refund']:.2f}" if o["refund"] else "",
                         o["refund_date"].isoformat() if o["refund_date"] else ""])
    write_csv(os.path.join(ws, "woocommerce_orders_2026-08.csv"),
              ["Order Number", "Order Date", "Order Status", "Payment Method Title", "Customer Name", "Billing State", "SKU", "Item Name",
               "Product Categories", "Quantity", "Item Cost", "Line Subtotal", "Cart Discount", "Order Shipping", "Order Tax", "Order Total",
               "Refund Amount", "Refund Date"], rows, bom=True)
    write_csv(os.path.join(ws, "journal_import_template.csv"), TEMPLATE,
              [["WC-10000", "2026-07-31", "1210", "Order #10000 - Credit Card (Stripe)", "25.00", ""],
               ["WC-10000", "2026-07-31", "4000", "Order #10000 - coffee sales", "", "25.00"]])
    chart = "\n".join(f"| {k} | {v} |" for k, v in ACCOUNTS.items())
    write_text(os.path.join(ws, "bookkeeping_rules.md"), (
        "# Web store sales into the books\n\n"
        "From Grace (Mossbank Accounting). I import journals with `journal_import_template.csv`: those six columns in that\n"
        "order, one line per account per journal, amounts positive with the Debit or the Credit filled (never both), and no\n"
        "zero lines. Account Code is the four-digit number only. Dates are YYYY-MM-DD.\n\n"
        "## Chart of accounts (the ones the web store touches)\n\n"
        "| Code | Account |\n|---|---|\n" + chart + "\n\n"
        "## Which orders\n\n"
        "Book an order only if it was paid: `completed` and `processing` orders, and `refunded` orders (they were paid first).\n"
        "`cancelled`, `failed`, `pending` (payment) and `on-hold` (waiting for a bank transfer that has not arrived) are not\n"
        "sales yet and stay out.\n\n"
        "## Sale journal\n\n"
        "One journal per paid order, Journal No `WC-<order number>`, dated the day the order was placed.\n\n"
        "- Debit the clearing account for the payment method with the order total: Credit Card (Stripe) 1210, PayPal 1220,\n"
        "  Direct bank transfer 1000.\n"
        "- Debit 4900 Sales Discounts with the cart discount. Do not net the discount out of product sales.\n"
        "- Credit product sales with the line subtotals (before discount) by category: Coffee 4000, Brewing Equipment 4010,\n"
        "  Subscriptions 4020, Merch 4030. Subscription products also carry a Coffee category in WooCommerce; they are\n"
        "  subscription sales.\n"
        "- Credit 4100 Shipping Income with the shipping charged and 2200 Sales Tax Payable with the tax.\n\n"
        "## Refunds\n\n"
        "A refund gets its own journal, Journal No `WC-<order number>-R`, dated the refund date: debit 4950 Sales Returns &\n"
        "Refunds and credit the same clearing account the order was paid through, for the refunded amount. Do not split tax\n"
        "out of refunds; I true up sales tax on returns at quarter end. A fully refunded order therefore has two journals.\n\n"
        "This file is for August only. Anything dated in September waits for next month's file.\n"))
    lines = [ln for o in orders for ln in journal_lines(o)]
    rrows = [[jn, dt, acct, desc, fmt(dr), fmt(cr)] for jn, dt, acct, desc, dr, cr in lines]
    write_csv(os.path.join(ref, "journal.csv"), TEMPLATE, rrows)
    write_csv(os.path.join(sol, "journal.csv"), TEMPLATE, rrows)
    by_tag = lambda t: sorted({f"WC-{o['no']}" for o in orders if t in o["tags"] and o["status"] in ("completed", "processing", "refunded")})
    trap_journals = sorted(set(by_tag("discount") + by_tag("subscription") + by_tag("paypal") + by_tag("bank") + by_tag("refund") +
                               [j + "-R" for j in by_tag("refund")] + by_tag("september_refund") + by_tag("multi")))
    write_json(os.path.join(ref, "truth.json"), {
        "trap_journals": trap_journals,
        "excluded_orders": sorted(o["no"] for o in orders if o["status"] not in ("completed", "processing", "refunded")),
        "september_refund_order": next(o["no"] for o in orders if "september_refund" in o["tags"]),
        "total_debits": round(sum(ln[4] for ln in lines), 2), "total_credits": round(sum(ln[5] for ln in lines), 2)})
    n_j = len({ln[0] for ln in lines})
    write_task_yaml(HERE, {
        "id": "woocommerce-orders-to-journal", "track": "desk", "category": "reformatting",
        "title": "Turn August web store orders into journal entries",
        "ask": ("Grace needs August's web store sales as journal entries she can import. The WooCommerce export is in the folder "
                "along with her rules and import template. Save it as journal.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the export is one row per line item and repeats the order's discount, shipping, tax, total and refund on every item row; adding those per row inflates every multi-item order (checks: journals balance; account amounts per journal)",
            "only paid orders are booked: completed, processing and refunded yes; three cancelled, three failed, three pending and three on-hold bank transfers no (checks: journal numbers; row count)",
            "two fully refunded orders keep their sale journal and add a WC-<n>-R journal dated the refund date, two completed orders have partial refunds that need -R journals for the refunded amount only, and one refund dated 2 September stays out of the August file (checks: journal numbers; account amounts per journal; journal dates)",
            "the cart discount must be a debit to 4900 Sales Discounts with product sales credited at the undiscounted line subtotals; netting the discount into sales moves the account amounts (check: account amounts per journal)",
            "the clearing account follows the payment method: Stripe 1210, PayPal 1220 and the one bank transfer that was paid 1000 (check: account amounts per journal)",
            "subscription products carry both a Coffee and a Subscriptions category and must credit 4020, not 4000 (check: account amounts per journal)",
            "every journal must balance to the cent and total debits must equal total credits; one line per account per journal (checks: journals balance; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "journal template columns, exact order", "path": "journal.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "journal numbers", "path": "journal.csv", "column": "Journal No", "ref": "journal.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count (one line per account per journal)", "path": "journal.csv", "equals_ref": "journal.csv"},
            {"type": "custom", "name": "journals balance", "module": "check.py"},
            {"type": "custom", "name": "account amounts per journal; journal dates", "module": "check_amounts.py"},
        ],
    })
    print(f"seed={seed}: {len(orders)} orders, {len(rows)} export rows, {n_j} journals, {len(lines)} lines; trap journals {len(trap_journals)}; "
          f"debits {sum(ln[4] for ln in lines):.2f} credits {sum(ln[5] for ln in lines):.2f}")


if __name__ == "__main__":
    emit(argparse_seed())
