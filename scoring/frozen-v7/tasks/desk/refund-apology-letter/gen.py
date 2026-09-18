#!/usr/bin/env python3
"""refund-apology-letter: a customer's complaint about a cracked skillet, the web shop's order export and the
current returns policy become the reply that states the refund.

    python gen.py [--seed N]

Business: an online cookware shop. A customer ordered a cookware set, two cast iron skillets and a utensil set
with a Labor Day discount code; one skillet arrived cracked and the set came a few days late on standard shipping.
She asks for the skillet's list price, her shipping and a gift card for the delay.

Traps (each caught by a check, see task.yaml):
  * her email quotes the order number with two digits swapped, and that number is a real order of another
    customer in the export; her name and email find her own order          (checks: correct order number; wrong order number not used)
  * the skillet line is quantity 2 with the discount code allocated across the order and tax charged per line; the
    policy refunds what was paid for the damaged item (price after the code plus its tax), so the refund is one
    unit's discounted price plus its tax, not the $64 list price she asks for and not the whole line   (check: refund amount per policy)
  * the export is a Shopify-style file: order-level fields sit only on each order's first line, amounts are text,
    and it carries a BOM and CRLF endings                                  (check: refund amount per policy)
  * the policy updated in July says refunds are processed within 5 business days; the 2025 saved replies still
    say 7-10 business days                                                  (check: processing time)
  * she asks for her shipping back and a gift card for the late set; the policy refunds shipping only when a whole
    order arrives damaged and offers no credits or gift cards for late standard deliveries, and the saved replies
    promise both                                                            (check: no promise the policy forbids)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

SHOP = "Copperleaf Kitchen Supply"
DOMAIN = "copperleafkitchen.com"
TAX = Decimal("0.075")
CODE = "LABORDAY15"
PCT = Decimal("0.15")
CATALOG = [("Tri-Ply Stainless 10-Piece Set", "TPS-10PC", ["389.00", "419.00", "359.00"]),
           ("Pre-Seasoned Cast Iron Skillet 12in", "CI-SK12", ["64.00", "72.00", "56.00"]),
           ("Silicone Utensil Set 6pc", "SIL-UT6", ["28.00", "24.00", "32.00"]),
           ("Carbon Steel Wok 14in", "CS-WK14", ["79.00"]), ("Enameled Dutch Oven 5.5qt", "EDO-55", ["149.00", "169.00"]),
           ("Chef Knife 8in", "KN-CH8", ["119.00"]), ("Bamboo Cutting Board L", "BB-CBL", ["36.00"]),
           ("Cast Iron Skillet 10in", "CI-SK10", ["48.00"]), ("Sheet Pan Half Size 2pk", "SP-HALF2", ["34.00"]),
           ("Stainless Saucepan 3qt", "TPS-SP3", ["89.00"]), ("Wooden Spoon Set 3pc", "WS-3PC", ["19.00"]),
           ("Spice Jar Set 12", "SJ-12", ["42.00"])]


def cents(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def price_order(lines, code_pct):
    """lines: [(name, sku, qty, unit Decimal)] -> per-line dicts with discount allocation and per-line tax."""
    out = []
    for name, sku, qty, unit in lines:
        gross = unit * qty
        disc = cents(gross * code_pct) if code_pct else Decimal("0.00")
        net = gross - disc
        out.append(dict(name=name, sku=sku, qty=qty, unit=unit, gross=gross, disc=disc, net=net, tax=cents(net * TAX)))
    return out


def build(seed: int) -> dict:
    r = rng(seed * 7 + 11)
    set_price = Decimal(r.choice(CATALOG[0][2]))
    # skillet price: one unit after the code and its tax must land on whole cents, so the per-unit refund is exact
    sk_choices = [p for p in CATALOG[1][2] if (Decimal(p) * (1 - PCT) * TAX) == cents(Decimal(p) * (1 - PCT) * TAX)]
    sk_price = Decimal(r.choice(sk_choices))
    ut_price = Decimal(r.choice(CATALOG[2][2]))
    ppl, firsts = [], set()
    while len(ppl) < 16:
        f, l = person(r)
        if f not in firsts and l not in {x[1] for x in ppl}:
            firsts.add(f); ppl.append((f, l))
    cust = {"first": ppl[0][0], "last": ppl[0][1]}
    cust["email"] = email_for(r, cust["first"], cust["last"])
    base = r.randint(104100, 104800)
    # her order number has distinct 3rd- and 4th-from-last digits so the swap is a different number
    while True:
        digits = str(base)
        if digits[-2] != digits[-1] and digits[-1] != "0":
            break
        base += 1
    her_no = f"CK-{base}"
    wrong_no = f"CK-{digits[:-2]}{digits[-1]}{digits[-2]}"
    lines = [(CATALOG[0][0], CATALOG[0][1], 1, set_price), (CATALOG[1][0], CATALOG[1][1], 2, sk_price), (CATALOG[2][0], CATALOG[2][1], 1, ut_price)]
    her_lines = price_order(lines, PCT)
    shipping = Decimal("14.95")
    sk = her_lines[1]
    unit_net = cents(sk["net"] / 2)
    unit_tax = cents(sk["tax"] / 2)
    assert unit_net * 2 == sk["net"] and unit_tax * 2 == sk["tax"], "skillet line must split evenly"
    refund = unit_net + unit_tax
    her_order = dict(no=her_no, name=f"{cust['first']} {cust['last']}", email=cust["email"], lines=her_lines, code=CODE,
                     shipping=shipping, method="Standard (5-7 business days)", created=datetime(2026, 8, 27, 20, 41),
                     city=r.choice(CITIES))
    # the other orders of the week, including the real CK number her typo points at
    others = []
    used = {base}
    order_days = [datetime(2026, 8, 24, 7, 0) + timedelta(minutes=r.randint(0, 60 * 24 * 9)) for _ in range(14)]
    for i in range(14):
        n = base + r.randint(-60, 60)
        while n in used or str(n) == wrong_no[3:]:
            n += 1
        used.add(n)
        pr = ppl[i + 1]
        k = r.randint(1, 3)
        items = r.sample(CATALOG[3:], k)
        ls = [(nm, sku, r.choice([1, 1, 1, 2]), Decimal(r.choice(ps))) for nm, sku, ps in items]
        use_code = r.random() < 0.4
        others.append(dict(no=f"CK-{n}", name=f"{pr[0]} {pr[1]}", email=email_for(r, pr[0], pr[1]), lines=price_order(ls, PCT if use_code else None),
                           code=CODE if use_code else "", shipping=Decimal(r.choice(["0.00", "9.95", "14.95", "24.95"])),
                           method=r.choice(["Standard (5-7 business days)", "Express (2 business days)"]), created=order_days[i], city=r.choice(CITIES)))
    pr = ppl[15]
    wrong_lines = price_order([("Cast Iron Skillet 10in", "CI-SK10", 1, Decimal("48.00")), ("Wooden Spoon Set 3pc", "WS-3PC", 1, Decimal("19.00"))], None)
    others.append(dict(no=wrong_no, name=f"{pr[0]} {pr[1]}", email=email_for(r, pr[0], pr[1]), lines=wrong_lines, code="", shipping=Decimal("9.95"),
                       method="Standard (5-7 business days)", created=datetime(2026, 8, 27, 11, 5), city=r.choice(CITIES)))
    orders = others + [her_order]
    orders.sort(key=lambda o: o["created"])
    wrong_refund = wrong_lines[0]["net"] + wrong_lines[0]["tax"]
    naive = {"list_price": sk_price, "line_total": sk["net"] + sk["tax"], "unit_no_tax": unit_net, "ask_total": sk_price + shipping + Decimal("25.00"),
             "wrong_order_skillet": wrong_refund, "list_plus_tax": cents(sk_price * (1 + TAX))}
    assert len({refund, *naive.values()}) == len(naive) + 1, naive
    return dict(cust=cust, her=her_order, orders=orders, wrong_no=wrong_no, refund=refund, unit_net=unit_net, unit_tax=unit_tax,
                sk_price=sk_price, shipping=shipping, naive=naive, delivered=date(2026, 9, 3))


def m(x: Decimal) -> str:
    return f"{x:.2f}"


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    cust, her = d["cust"], d["her"]
    # ---- order export, Shopify style: order-level fields only on the first line of each order
    header = ["Name", "Email", "Financial Status", "Paid at", "Fulfillment Status", "Accepts Marketing", "Currency", "Subtotal", "Shipping",
              "Taxes", "Total", "Discount Code", "Discount Amount", "Shipping Method", "Created at", "Lineitem quantity", "Lineitem name",
              "Lineitem price", "Lineitem sku", "Lineitem discount", "Lineitem tax", "Billing Name", "Shipping City", "Shipping Province"]
    rows = []
    for o in d["orders"]:
        sub = sum((l["net"] for l in o["lines"]), Decimal("0"))
        tax = sum((l["tax"] for l in o["lines"]), Decimal("0"))
        disc = sum((l["disc"] for l in o["lines"]), Decimal("0"))
        total = sub + tax + o["shipping"]
        stamp = o["created"].replace(second=(o["created"].minute * 7) % 60).strftime("%Y-%m-%d %H:%M:%S -0700")
        for i, l in enumerate(o["lines"]):
            first = i == 0
            rows.append([o["no"], o["email"], "paid" if first else "", stamp if first else "", "fulfilled" if first else "", "no" if first else "",
                         "USD" if first else "", m(sub) if first else "", m(o["shipping"]) if first else "", m(tax) if first else "",
                         m(total) if first else "", o["code"] if first else "", m(disc) if first and o["code"] else ("" if not first else "0.00"),
                         o["method"] if first else "", stamp if first else "", l["qty"], l["name"], m(l["unit"]), l["sku"], m(l["disc"]), m(l["tax"]),
                         o["name"] if first else "", o["city"][0] if first else "", o["city"][1] if first else ""])
    write_csv(os.path.join(ws, "orders_export_2026-08-24_to_2026-09-02.csv"), header, rows, bom=True, crlf=True)

    # ---- the complaint, forwarded by the owner
    owner = "Leila Haddad"
    set_name = her["lines"][0]["name"]
    write_email_thread(os.path.join(ws, "email_customer_complaint.txt"), [
        {"from": f"{cust['first']} {cust['last']} <{cust['email']}>", "to": f"hello@{DOMAIN}", "date": "Fri, 4 Sep 2026 07:52",
         "subject": f"Cracked skillet - order #{d['wrong_no']}",
         "body": (f"Hi,\n\nI'm writing about my order #{d['wrong_no']}. I ordered two of the 12 inch cast iron skillets (one is a gift for my sister), "
                  f"the {set_name.lower()} and the utensil set. Everything finally arrived yesterday, September 3rd, and one of the skillets has a crack "
                  "right through the handle where it joins the pan. Photo attached. The other skillet is fine and I'm keeping it.\n\n"
                  f"I have to be honest, I'm pretty disappointed. The cookware set showed up almost a week after the date your site gave me, "
                  f"and now a cracked pan. I paid ${m(d['sk_price'])} for that skillet and I'd like that back, plus the ${m(d['shipping'])} I paid for shipping "
                  "since the order clearly wasn't handled well. I also think a $25 gift card would be fair for the delay and the hassle.\n\n"
                  "I don't want a replacement, just the refund please.\n\nThanks,\n"
                  f"{cust['first']} {cust['last']}")},
        {"from": f"{owner} <leila@{DOMAIN}>", "to": "support@copperleafkitchen.com", "date": "Fri, 4 Sep 2026 09:30",
         "subject": f"FW: Cracked skillet - order #{d['wrong_no']}",
         "body": ("Can you draft a reply to her for me to look over? Stick to the returns policy we put up in July. "
                  "I checked the photo and the crack is real, so the damage claim is approved.\n\nLeila")},
    ])

    # ---- the current policy
    write_text(os.path.join(ws, "returns_and_refunds_policy.md"),
        f"# Returns & Refunds\n\n_{SHOP} - last updated July 1, 2026. This replaces all earlier versions._\n\n"
        "## Returns of unused items\n\n"
        "Unused items in their original packaging can be returned within 30 days of delivery for a refund of the price paid. "
        "Return shipping for unwanted items is the customer's responsibility. Cookware that has been used or seasoned cannot be returned "
        "unless it is defective.\n\n"
        "## Items that arrive damaged or defective\n\n"
        "Tell us within 30 days of delivery and include a photo. Once we approve the claim we will, at your choice, send a replacement or "
        "refund what you paid for the damaged item: its price after any discount code applied to the order, plus the sales tax charged on it. "
        "Where an order line has more than one unit, we refund only the damaged units. You don't need to send the damaged item back.\n\n"
        "## Shipping charges\n\n"
        "Original shipping charges are not refunded, except when every item in the order arrives damaged or we shipped the wrong items.\n\n"
        "## Delivery times\n\n"
        "Delivery dates for standard shipping are estimates, not guarantees. We don't offer credits, gift cards or discount codes as compensation "
        "for late standard deliveries. If an Express order arrives after its guaranteed date, we refund the Express shipping charge.\n\n"
        "## How refunds are paid\n\n"
        "Refunds go back to the original payment method and are processed within 5 business days of approval. "
        "Your bank may take a few extra days to post the refund to your statement. We don't issue store credit or gift cards in place of a refund.\n")

    # ---- distractor: old saved replies
    write_text(os.path.join(ws, "support_saved_replies_2025.txt"),
        "SAVED REPLIES - support inbox (updated March 2025)\n"
        "==================================================\n\n"
        "[Damaged item - refund]\n"
        "Hi {first name},\n\nI'm so sorry your {item} arrived damaged! We've refunded the item and your original shipping, and we've added a $15 store "
        "credit to your account for the trouble. Refunds take 7-10 business days to process. No need to send anything back.\n\n"
        "[Damaged item - replacement]\n"
        "Hi {first name},\n\nSorry about that! A replacement {item} ships today and you'll get tracking by email. Keep or recycle the damaged one.\n\n"
        "[Late delivery]\n"
        "Hi {first name},\n\nThanks for your patience. Carriers have been slow this season. As a thank-you, here is a code for 10% off your next order: "
        "SORRY10.\n\n"
        "[Where is my refund]\n"
        "Hi {first name},\n\nRefunds take 7-10 business days to process, and then your bank may need a few more days.\n")

    # ---- reference and reference solution
    facts = {"order_no": her["no"], "wrong_no": d["wrong_no"], "refund": float(d["refund"]), "unit_net": float(d["unit_net"]),
             "unit_tax": float(d["unit_tax"]), "shipping": float(d["shipping"]), "naive": {k: float(v) for k, v in d["naive"].items()}}
    write_json(os.path.join(ref, "facts.json"), facts)
    letter = (f"Subject: Your cracked skillet - order {her['no']}\n\n"
              f"Hi {cust['first']},\n\n"
              f"Thank you for letting us know, and I'm sorry one of your 12-inch cast iron skillets arrived cracked. That's not the condition "
              f"anything should reach you in, and thank you for sending the photo.\n\n"
              f"I found your order under {her['no']} (the number in your email had two digits swapped). We've approved your damage claim for the one "
              "cracked skillet and, as you asked, we're refunding it rather than sending a replacement.\n\n"
              f"Your refund is ${m(d['refund'])}. That is what you paid for that skillet: the ${m(d['sk_price'])} price less your {CODE} discount, "
              f"which comes to ${m(d['unit_net'])}, plus the ${m(d['unit_tax'])} sales tax charged on it. "
              "It goes back to your original payment method, and we process refunds within 5 business days. "
              "Your bank may take a few extra days to show it on your statement. There's no need to send the cracked skillet back.\n\n"
              "I understand the cookware set arriving later than the estimate was frustrating, and I'm sorry for that. "
              "Our policy doesn't let us refund the original shipping charge when only part of an order is damaged, and we're not able to offer "
              "gift cards or credits for standard deliveries that arrive after the estimated date. I know that isn't everything you asked for, "
              "and I wanted to be straightforward with you about it.\n\n"
              "If anything else in the order isn't right, just reply to this email and we'll take care of it.\n\n"
              f"Best regards,\n\n{owner}\n{SHOP}\n")
    write_text(os.path.join(sol, "response.md"), letter)

    write_task_yaml(HERE, {
        "id": "refund-apology-letter", "track": "desk", "category": "drafting",
        "title": "Reply to a customer about a cracked skillet",
        "ask": (f"{cust['first']} {cust['last']} emailed us about a cracked skillet and a late delivery. Please draft my reply to her, sticking to our "
                "refund policy, and save it as response.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"her email quotes order #{d['wrong_no']}, two digits swapped; that number is another customer's order in the export, and her name and email find {her['no']} (checks: correct order number; no promise the policy forbids and no wrong order number)",
            f"the skillet line is quantity 2 with the {CODE} code allocated per line and tax charged per line; one unit's price after the code plus its tax is ${m(d['refund'])}, not the ${m(d['sk_price'])} list price she asks for, the whole line (${m(d['naive']['line_total'])}) or the price without tax (${m(d['unit_net'])}) (check: refund amount per policy)",
            "the export is Shopify style: order-level fields sit only on each order's first line, amounts are text, and it has a BOM and CRLF endings (check: refund amount per policy)",
            "the July policy processes refunds within 5 business days; the 2025 saved replies still say 7-10 business days (check: processing time)",
            "she asks for her shipping back and a $25 gift card for the late set; the policy refunds shipping only when every item arrives damaged and offers no credits for late standard deliveries, while the saved replies promise a shipping refund, store credit and a discount code (check: no promise the policy forbids and no wrong order number)",
        ],
        "checks": [
            {"type": "file_exists", "name": "response.md exists", "path": "response.md"},
            {"type": "text_contains_all", "name": "correct order number", "path": "response.md", "phrases": [her["no"][3:]]},
            {"type": "text_sentence_matches", "name": "refund amount per policy", "path": "response.md",
             "all": [r"refund", rf"(?<![\d.]){int(d['refund'])}\.{int(d['refund'] * 100) % 100:02d}(?!\d)"]},
            {"type": "text_sentence_matches", "name": "processing time", "path": "response.md",
             "all": [r"(\b5\b|\bfive\b)[\s-]*(business|working)[\s-]*days?"],
             "none": [r"(\b7\b|\bseven\b)\s*(-|–|to)\s*(\b10\b|\bten\b)", r"\b(10|ten)\s+(business|working)\s+days"]},
            {"type": "custom", "name": "no promise the policy forbids and no wrong order number", "module": "check.py"},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
