#!/usr/bin/env python3
"""credit-notes-apply: September returns at a pet-supply wholesaler turned into credit notes and applied to open invoices.

    python gen.py [--seed N] [--naive DIR]
    python gen.py --list-knobs
    python gen.py --cross-doc 2 --trap-count spill_over=3 --out DIR    # a harder task; the answer moves
    python gen.py --describe [--scale N ...]                            # content counts of this draw

Business: Kibble Crate Distributors sells food, treats and grooming supplies to independent pet shops and groomers
at a per-customer discount. The warehouse logs returns against RMAs; the AR clerk turns them into credit notes and
applies them. The returns policy carries the rules: credit at the net price charged, a 15% restocking fee only for
customer-side reasons, inspection status, and the order of application.

Traps (each caught by a check, see task.yaml):
  * credit is at the discounted unit price on the original invoice line, not the list price    (check: credit and fee per RMA)
  * the restocking fee applies line by line, only to ordered-in-error and overstock returns     (check: credit and fee per RMA)
  * a credit larger than its invoice's open balance spills to the customer's oldest other open
    invoice, and a credit against an invoice already paid goes straight to the oldest open ones (checks: applied and unapplied; invoice balances)
  * a customer with no open invoices keeps the whole credit on account                          (check: applied and unapplied)
  * one customer has two RMAs; the second names the invoice the first one already reduced      (checks: applied and unapplied; invoice balances)
  * rejected lines earn nothing, and an RMA still pending inspection gets no credit note yet    (checks: credit notes issued; credit and fee per RMA)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from bizgen.knobs import Knob, KnobSet, add_knob_args, describe_json, output_dirs, parse_knob_args, record  # noqa: E402

# Difficulty knobs (docs/authoring-knobs.md). The defaults are the published task and leave every draw as it was.
KNOBS = KnobSet(
    Knob("scale", "scale", default=1, levels=(1, 2, 4),
         changes="paid invoices per customer in the June-September invoice history are multiplied by N", measure="rows"),
    Knob("cross_doc", "cross-doc", default=0, levels=(0, 1, 2),
         changes="1: the invoice lines show list prices only and each customer's discount lives in a separate customer "
                 "price agreement; 2: three customers' agreed discounts also changed during the summer, so the invoice date "
                 "picks the agreement row", measure="cross_doc"),
    Knob("trap_count.spill_over", "trap-count", default=1, levels=(1, 2, 3),
         changes="credit notes larger than their partly paid invoice's open balance, spilling to the customer's oldest "
                 "other open invoice", measure="trap_instances.spill_over"),
)

SHOPS = ["Paws & Claws Pet Supply", "Barkside Grooming", "Whisker Lane Pets", "The Feed Bin", "Fin & Feather Aquatics",
         "Happy Tails Boutique", "Mudroom Dog Wash", "Tailwind Pet Market", "Scratch & Sniff Pets", "Four Paws Farm Store",
         "Bayside Bark & Bath", "Mountain Mutt Outfitters", "Kitty Corner Pet Shop", "Hound Hollow Grooming"]
ITEMS = [("KC-DF-30", "Grain-free dog food 30 lb", "58.40"), ("KC-CF-16", "Indoor cat food 16 lb", "41.20"),
         ("KC-TR-SB", "Salmon bites treats 12 oz (case of 12)", "86.00"), ("KC-LT-40", "Clumping litter 40 lb", "22.75"),
         ("KC-SH-OAT", "Oatmeal shampoo 1 gal", "34.90"), ("KC-CL-PRO", "Professional clipper kit", "189.00"),
         ("KC-BR-SL", "Slicker brush (case of 6)", "47.10"), ("KC-LE-6", "Nylon leash 6 ft (case of 10)", "63.50"),
         ("KC-BD-L", "Orthopedic bed large", "74.25"), ("KC-AQ-FL", "Aquarium filter cartridges (24)", "52.80"),
         ("KC-BS-25", "Wild bird seed 25 lb", "27.60"), ("KC-CH-BU", "Bully sticks 6 in (bulk 50)", "96.40"),
         ("KC-TY-RO", "Rope toy assortment (case of 24)", "71.30"), ("KC-DT-KIT", "Dental care kit (case of 12)", "68.90"),
         ("KC-FL-3", "Flea and tick drops 3-pack (case of 6)", "118.20"), ("KC-CR-M", "Wire crate medium", "84.75")]
FEE_REASONS = ["Ordered in error", "Overstock"]
NOFEE_REASONS = ["Damaged in transit", "Defective", "Wrong item shipped", "Manufacturer recall"]
D = Decimal


def c2(x) -> Decimal:
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def build(seed: int, knobs=KNOBS.defaults()) -> dict:
    r = rng(seed)
    scale = knobs["scale"]
    shops = r.sample(SHOPS, 12)
    disc = {s: D(r.choice(["0.05", "0.08", "0.10", "0.12", "0.15"])) for s in shops}
    invoices = []

    def make_invoice(cust, when, status, rr=None):
        rr = rr or r
        lines = []
        for sku, desc, lp in rr.sample(ITEMS, rr.randint(3, 5)):
            q = rr.randint(3, 14)
            net = c2(D(lp) * (1 - disc[cust]))
            lines.append({"sku": sku, "desc": desc, "list": D(lp), "net": net, "qty": q, "total": net * q})
        amount = sum(l["total"] for l in lines)
        inv = {"seq": len(invoices), "cust": cust, "date": when, "due": when + timedelta(days=30), "lines": lines,
               "amount": amount, "paid": D("0.00"), "status": status}
        if status == "paid":
            inv["paid"] = amount
        elif status == "partial":
            inv["paid"] = c2(amount * D(str(rr.uniform(0.45, 0.8))))
        invoices.append(inv)
        return inv

    for cust in shops:
        for _ in range(r.randint(2, 4) * scale):
            make_invoice(cust, day_in(r, date(2026, 6, 2), date(2026, 8, 20), weekday_only=True), "paid")
        for _ in range(r.randint(1, 3)):
            make_invoice(cust, day_in(r, date(2026, 7, 20), date(2026, 9, 25), weekday_only=True), r.choice(["open", "open", "partial"]))
    # the customer with nothing open
    no_open = shops[3]
    for inv in invoices:
        if inv["cust"] == no_open:
            inv["status"], inv["paid"] = "paid", inv["amount"]

    def open_bal(inv):
        return inv["amount"] - inv["paid"]

    def opens(cust):
        return sorted([i for i in invoices if i["cust"] == cust and open_bal(i) > 0], key=lambda i: (i["date"], i["seq"]))

    # guarantee the structural cases
    exceed_c, paid_c, pair_c = shops[1], shops[2], shops[4]
    for cust, n in ((exceed_c, 3), (paid_c, 2), (pair_c, 2)):
        while len(opens(cust)) < n:
            make_invoice(cust, day_in(r, date(2026, 7, 20), date(2026, 9, 18), weekday_only=True), "open")

    # knob-only content, drawn from its own stream after the default draws (none of this runs at the defaults)
    nspill, xdoc = knobs.trap_count("spill_over"), knobs["cross_doc"]
    spill_c, disc_changes, rk = shops[10:10 + nspill - 1], [], None
    if nspill > 1 or xdoc > 1:
        rk = rng(seed + 7_000_003)
        for cust in spill_c:
            while len(opens(cust)) < 3:
                make_invoice(cust, day_in(rk, date(2026, 7, 20), date(2026, 9, 18), weekday_only=True), "open", rk)
        if xdoc > 1:
            # three customers' agreed discounts changed during the summer; lines on invoices from that date use the new one
            # windows: shops[2]'s paid invoices mostly predate its change; shops[4]'s change falls between its open invoices
            o4 = opens(shops[4])
            mid = o4[0]["date"] + (o4[-1]["date"] - o4[0]["date"]) / 2 + timedelta(days=1)
            for cust, lo, hi in ((shops[0], date(2026, 7, 6), date(2026, 8, 7)), (shops[2], date(2026, 8, 21), date(2026, 9, 10)),
                                 (shops[4], mid, mid)):
                when = day_in(rk, lo, hi)
                new = D(rk.choice([x for x in ("0.05", "0.08", "0.10", "0.12", "0.15") if D(x) != disc[cust]]))
                disc_changes.append((cust, when, disc[cust], new))
                for inv in invoices:
                    if inv["cust"] == cust and inv["date"] >= when:
                        for l in inv["lines"]:
                            l["net"] = c2(l["list"] * (1 - new))
                            l["total"] = l["net"] * l["qty"]
                        old_amount, inv["amount"] = inv["amount"], sum(l["total"] for l in inv["lines"])
                        if inv["status"] == "paid" or inv["paid"] == old_amount:
                            inv["paid"] = inv["amount"]
                        elif inv["paid"] > 0:
                            inv["paid"] = c2(inv["amount"] * inv["paid"] / old_amount)

    # invoice numbers run with the invoice date, as the billing system issues them
    start = r.randint(30100, 30400)
    for inv in sorted(invoices, key=lambda i: (i["date"], i["seq"])):
        start += r.choice([1, 1, 1, 2, 3])
        inv["no"] = f"INV-{start}"
    rmas = []
    rma_nums = sorted(r.sample(range(101, 199), 12))
    rma_seq = iter(rma_nums)

    def rma(cust, inv, spec, role, when=None, rr=None, seq=None):
        rr = rr or r
        lines = []
        pool = list(inv["lines"])
        rr.shuffle(pool)
        for (reason, frac, insp), line in zip(spec, pool):
            q = max(1, min(line["qty"], round(line["qty"] * frac)))
            lines.append({"sku": line["sku"], "desc": line["desc"], "qty": q, "net": line["net"], "list": line["list"], "reason": reason,
                          "insp": insp})
        earliest = max(date(2026, 9, 1), inv["date"] + timedelta(days=3))
        if when is None or when < earliest:
            when = day_in(rr, earliest, max(earliest, date(2026, 9, 29)), weekday_only=False)
        x = {"no": f"RMA-2609-{seq or next(rma_seq)}", "cust": cust, "inv": inv, "lines": lines, "role": role, "date": when}
        rmas.append(x)
        return x

    A = "Accepted"
    rma(shops[0], opens(shops[0])[0], [(r.choice(FEE_REASONS), 0.5, A), (r.choice(NOFEE_REASONS), 0.4, A)], "fee_mix")
    big_open = min(opens(exceed_c)[1:], key=lambda i: open_bal(i))
    if big_open["status"] != "partial":
        big_open["status"], big_open["paid"] = "partial", c2(big_open["amount"] * D(str(r.uniform(0.5, 0.75))))
    rma(exceed_c, big_open, [(r.choice(NOFEE_REASONS), 1.0, A), (r.choice(NOFEE_REASONS), 1.0, A), (r.choice(FEE_REASONS), 1.0, A)], "exceeds")
    paid_inv = r.choice([i for i in invoices if i["cust"] == paid_c and i["status"] == "paid"])
    rma(paid_c, paid_inv, [(r.choice(NOFEE_REASONS), 1.0, A), (r.choice(FEE_REASONS), 0.8, A), (r.choice(NOFEE_REASONS), 1.0, A)], "paid_invoice")
    rma(no_open, r.choice([i for i in invoices if i["cust"] == no_open]), [(r.choice(FEE_REASONS), 0.6, A)], "no_open")
    rma(shops[5], opens(shops[5])[-1], [(r.choice(NOFEE_REASONS), 0.5, A), (r.choice(FEE_REASONS), 0.7, "Rejected - opened / not resaleable")], "rejected_line")
    rma(shops[6], opens(shops[6])[0], [(r.choice(NOFEE_REASONS), 0.5, "Pending inspection"), (r.choice(FEE_REASONS), 0.5, "Pending inspection")], "pending")
    p_invs = opens(pair_c)
    first = rma(pair_c, p_invs[-1], [(r.choice(NOFEE_REASONS), 1.0, A), (r.choice(NOFEE_REASONS), 1.0, A), (r.choice(NOFEE_REASONS), 1.0, A)],
                "pair_first", when=date(2026, 9, r.randint(3, 10)))
    rma(pair_c, p_invs[0], [(r.choice(NOFEE_REASONS), 0.9, A), (r.choice(FEE_REASONS), 0.9, A)], "pair_second",
        when=max(first["date"] + timedelta(days=r.randint(4, 12)), date(2026, 9, r.randint(15, 25))))
    for k in (7, 8, 9):
        cust = shops[k]
        rma(cust, opens(cust)[0], [(r.choice(FEE_REASONS + NOFEE_REASONS), r.uniform(0.2, 0.5), A)], "plain")
    if spill_c:
        # more credits that outrun a partly paid invoice (trap_count.spill_over > 1)
        spare = iter(rk.sample([n for n in range(101, 199) if n not in rma_nums], len(spill_c)))
        for k, cust in enumerate(spill_c):
            big = min(opens(cust)[1:], key=lambda i: open_bal(i))
            if big["status"] != "partial":
                big["status"], big["paid"] = "partial", c2(big["amount"] * D(str(rk.uniform(0.5, 0.75))))
            rma(cust, big, [(rk.choice(NOFEE_REASONS), 1.0, A), (rk.choice(FEE_REASONS), 1.0, A), (rk.choice(NOFEE_REASONS), 1.0, A)],
                f"exceeds_{k + 2}", rr=rk, seq=next(spare))
    rmas.sort(key=lambda x: x["no"])

    # ---- truth
    bal = {i["no"]: open_bal(i) for i in invoices if open_bal(i) > 0}
    notes = []
    for x in rmas:
        acc = [l for l in x["lines"] if l["insp"] == A]
        if not acc:
            continue
        gross = sum(l["qty"] * l["net"] for l in acc)
        fee = sum(c2(D("0.15") * l["qty"] * l["net"]) for l in acc if l["reason"] in FEE_REASONS)
        credit = gross - fee
        left = credit
        applied_to = []
        targets = []
        if x["inv"]["no"] in bal and bal[x["inv"]["no"]] > 0:
            targets.append(x["inv"]["no"])
        targets += [i["no"] for i in sorted(invoices, key=lambda i: (i["date"], i["seq"]))
                    if i["cust"] == x["cust"] and i["no"] in bal and i["no"] != x["inv"]["no"]]
        for t in targets:
            if left <= 0:
                break
            take = min(left, bal[t])
            if take > 0:
                bal[t] -= take
                left -= take
                applied_to.append((t, take))
        notes.append({"rma": x["no"], "cust": x["cust"], "gross": gross, "fee": fee, "credit": credit, "applied": credit - left,
                      "unapplied": left, "to": applied_to, "role": x["role"]})
    open_list = sorted([i for i in invoices if open_bal(i) > 0], key=lambda i: (i["cust"], i["date"], i["seq"]))
    return {"shops": shops, "disc": disc, "invoices": invoices, "open_list": open_list, "rmas": rmas, "notes": notes, "bal": bal,
            "open_bal": {i["no"]: open_bal(i) for i in open_list}, "disc_changes": disc_changes}


def acceptable(d: dict, knobs=KNOBS.defaults()) -> bool:
    by = {n["role"]: n for n in d["notes"]}
    extra = knobs.trap_count("spill_over") - 1
    if "pending" in by or len(d["notes"]) != 10 + extra:
        return False
    if d["disc_changes"]:
        # the agreement's effective dates must matter: some credited RMA names an invoice from before its customer's change
        ch = {c: w for c, w, _, _ in d["disc_changes"]}
        credited = {n["rma"] for n in d["notes"]}
        if not any(x["cust"] in ch and x["inv"]["date"] < ch[x["cust"]] for x in d["rmas"] if x["no"] in credited):
            return False
    for k in range(extra):
        n = by.get(f"exceeds_{k + 2}")
        if not n or len(n["to"]) < 2 or n["unapplied"] != 0:
            return False
    ex, pi, no, p1, p2 = by["exceeds"], by["paid_invoice"], by["no_open"], by["pair_first"], by["pair_second"]
    if not (len(ex["to"]) >= 2 and ex["unapplied"] == 0):
        return False
    if not (len(pi["to"]) >= 2 and pi["unapplied"] == 0):
        return False
    if no["unapplied"] != no["credit"] or no["credit"] <= 0:
        return False
    # the first of the pair spills into the invoice the second one names, and the second then runs out of open invoices
    second_named = [x for x in d["rmas"] if x["role"] == "pair_second"][0]["inv"]["no"]
    if second_named not in [t for t, _ in p1["to"]]:
        return False
    if p2["unapplied"] <= 0 or p2["applied"] <= 0:
        return False
    # an invoice cleared to zero, and the invoices touched by spills do not end on a round coincidence
    if not any(v == 0 for v in d["bal"].values()):
        return False
    fm = by["fee_mix"]
    if fm["fee"] <= 0 or fm["unapplied"] != 0:
        return False
    # the oldest open invoice of the spill customers differs from the newest, so order matters
    if any(x["date"] > date(2026, 9, 30) or x["date"] <= x["inv"]["date"] for x in d["rmas"]):
        return False
    return all(n["credit"] > 0 for n in d["notes"])


def counts(d: dict, knobs) -> dict:
    """--describe: what this draw contains."""
    xdoc = knobs["cross_doc"]
    return {"rows": sum(len(i["lines"]) for i in d["invoices"]), "entities": len(d["shops"]), "rules": 7,
            "documents": 4 + (xdoc > 0), "cross_doc": xdoc,
            "rmas": len(d["rmas"]), "credit_notes": len(d["notes"]), "open_invoices": len(d["open_list"]),
            "trap_instances": {"spill_over": sum(n["role"].startswith("exceeds") for n in d["notes"]),
                               "discount_changes": len(d["disc_changes"])}}


def emit(seed: int, naive_dir: str | None, knobs=KNOBS.defaults(), out: str | None = None) -> None:
    d = build(seed, knobs)
    xdoc = knobs["cross_doc"]
    cn_header = ["rma", "customer", "restocking_fee", "credit_amount", "applied", "unapplied"]
    ib_header = ["invoice", "customer", "balance"]
    if naive_dir:
        bal = dict(d["open_bal"])
        rows = []
        for x in d["rmas"]:
            gross = sum(l["qty"] * l["list"] for l in x["lines"])
            rows.append([x["no"], x["cust"], "0.00", f"{gross:.2f}", f"{gross:.2f}", "0.00"])
            if x["inv"]["no"] in bal:
                bal[x["inv"]["no"]] -= gross
        write_csv(os.path.join(naive_dir, "credit_notes.csv"), cn_header, rows)
        write_csv(os.path.join(naive_dir, "invoice_balances.csv"), ib_header,
                  [[i["no"], i["cust"], f"{bal[i['no']]:.2f}"] for i in d["open_list"]])
        return
    here, (ws, ref, sol) = output_dirs(HERE, out, task_dirs)
    r = rng(seed + 5)

    # ---- workspace: RMA log
    log = []
    for x in d["rmas"]:
        cust = x["cust"]
        shown = cust.upper() if r.random() < 0.25 else (cust + r.choice(["", "", " LLC", " Inc."]))
        inv_ref = x["inv"]["no"] if r.random() < 0.6 else x["inv"]["no"].replace("INV-", "")
        for l in x["lines"]:
            log.append([x["no"], date_variant(x["date"], r.choice([0, 1])), shown, inv_ref, l["sku"], l["desc"], l["qty"], l["reason"], l["insp"]])
    write_csv(os.path.join(ws, "rma_returns_log_2026-09.csv"),
              ["RMA", "Received", "Customer", "Orig Invoice", "SKU", "Item", "Qty Returned", "Return Reason", "Inspection"], log,
              preamble=["Warehouse returns log - September 2026"], bom=True)

    # ---- workspace: invoice lines (June to September)
    lines = []
    for inv in sorted(d["invoices"], key=lambda i: (i["date"], i["no"])):
        for l in inv["lines"]:
            lines.append([inv["no"], inv["date"].strftime("%m/%d/%Y"), inv["cust"], l["sku"], l["desc"], l["qty"], f"{l['list']:.2f}",
                          f"{int(d['disc'][inv['cust']] * 100)}%", f"{l['net']:.2f}", f"{l['total']:,.2f}"])
    if xdoc:
        # the discount lives in the customer price agreements, not on the invoice lines (cross_doc >= 1)
        lines = [row[:7] for row in lines]
        agree = []
        for cust in sorted(d["shops"]):
            ch = [c for c in d["disc_changes"] if c[0] == cust]
            if ch:
                _, when, old, new = ch[0]
                agree.append([cust, f"{int(old * 100)}%", "2026-01-01", (when - timedelta(days=1)).isoformat()])
                agree.append([cust, f"{int(new * 100)}%", when.isoformat(), ""])
            else:
                agree.append([cust, f"{int(d['disc'][cust] * 100)}%", "2026-01-01", ""])
        write_csv(os.path.join(ws, "customer_price_agreements.csv"),
                  ["Customer", "Account discount off list", "Effective from", "Effective to"], agree)
    write_csv(os.path.join(ws, "invoice_lines_2026-06-01_to_2026-09-30.csv"),
              ["Invoice", "Invoice Date", "Customer", "SKU", "Description", "Qty", "List Price", "Cust Discount", "Unit Price", "Line Total"][:7 if xdoc else 10],
              lines, crlf=True)

    # ---- workspace: open AR before credits
    ar = [[i["no"], i["cust"], i["date"], i["due"], float(i["amount"]), float(i["paid"]), float(i["amount"] - i["paid"])] for i in d["open_list"]]
    write_xlsx(os.path.join(ws, "open_invoices_2026-09-30.xlsx"), {"Open AR": {
        "merged_title": "Kibble Crate Distributors - open invoices at 30 Sep 2026 (before September credit notes)",
        "header": ["Invoice", "Customer", "Invoice date", "Due date", "Invoice total", "Paid to date", "Open balance"],
        "rows": ar, "number_formats": {"E": "#,##0.00", "F": "#,##0.00", "G": "#,##0.00"}, "widths": {"B": 28, "C": 12, "D": 12}}},
        creator="Accounts receivable")

    write_text(os.path.join(ws, "returns_and_credits_policy.md"),
               "# Returns and credit notes\n\n"
               "_Kibble Crate Distributors - accounts receivable procedure, revised March 2026_\n\n"
               "## When a return earns credit\n\n"
               "- Only lines the warehouse marks **Accepted** at inspection are credited. Rejected lines get nothing. Lines still pending "
               "inspection wait for next month's run.\n"
               "- The credit for a line is the quantity returned times the unit price the customer actually paid on the original invoice "
               "(after their account discount), not the list price.\n\n" + ("" if not xdoc else
               "- Invoice lines show list prices. The unit price charged is the list price less the customer's account discount from "
               "`customer_price_agreements.csv`" + (", using the agreement in force on the invoice date," if xdoc > 1 else "") +
               " rounded to the cent per unit.\n\n") +
               "## Restocking fee\n\n"
               "- Returns for **Ordered in error** or **Overstock** carry a 15% restocking fee: 15% of that line's credit, rounded to the cent, "
               "line by line.\n"
               "- No fee when the return is our fault or the maker's: damaged in transit, defective, wrong item shipped, recalls.\n\n"
               "## Credit notes\n\n"
               "- One credit note per RMA, numbered with the RMA number. Its amount is the credited lines less any restocking fees.\n"
               "- Apply credit notes in RMA number order.\n"
               "- Apply a credit note first to the invoice named on the RMA, up to that invoice's open balance. Whatever is left goes to the "
               "same customer's other open invoices, oldest invoice date first. If the named invoice is already paid, start with the oldest "
               "open invoice.\n"
               "- Anything still left stays on the customer's account as unapplied credit. We do not cut refund checks from this run.\n\n"
               "## What to hand back\n\n"
               "- `credit_notes.csv`: rma, customer, restocking_fee, credit_amount, applied, unapplied - one row per credit note issued.\n"
               "- `invoice_balances.csv`: invoice, customer, balance - every invoice on the open AR report, with its balance after the credit "
               "notes (0.00 when a credit clears it).\n")

    # ---- reference
    cn_rows = [[n["rma"], n["cust"], f"{n['fee']:.2f}", f"{n['credit']:.2f}", f"{n['applied']:.2f}", f"{n['unapplied']:.2f}"] for n in d["notes"]]
    ib_rows = [[i["no"], i["cust"], f"{d['bal'][i['no']]:.2f}"] for i in d["open_list"]]
    for base in (ref, sol):
        write_csv(os.path.join(base, "credit_notes.csv"), cn_header, cn_rows)
        write_csv(os.path.join(base, "invoice_balances.csv"), ib_header, ib_rows)
    write_json(os.path.join(ref, "notes.json"), {"notes": [{"rma": n["rma"], "role": n["role"], "gross": f"{n['gross']:.2f}",
                                                           "applied_to": [[t, f"{a:.2f}"] for t, a in n["to"]]} for n in d["notes"]],
                                                  "no_credit_note": [x["no"] for x in d["rmas"] if x["role"] == "pending"]})
    by = {n["role"]: n for n in d["notes"]}
    rma_role = {x["role"]: x for x in d["rmas"]}
    touched = sorted({t for role in ("exceeds", "paid_invoice", "pair_first", "pair_second") for t, _ in by[role]["to"]}
                     | {t for n in d["notes"] if n["role"].startswith("exceeds_") for t, _ in n["to"]})
    # knobbed output only: prose naming the extra spill-over notes and the price agreement
    spills = [by[f"exceeds_{k + 2}"] for k in range(knobs.trap_count("spill_over") - 1)]
    more_spill = "".join(f"; so does {n['rma']} for {n['cust']}" for n in spills)
    price_trap = ("the returns log has no prices; each line is credited at the discounted unit price on the original invoice, and every customer "
                  "has a 5-15% account discount, so quantity times list price over-credits every note (check: credit and fee per RMA)")
    if xdoc:
        price_trap = ("the returns log has no prices and the invoice lines show list prices only; each line is credited at list less the "
                      "customer's discount from the price agreements, rounded to the cent per unit, so quantity times list price "
                      "over-credits every note" + ("" if xdoc < 2 else "; " + ", ".join(
                          f"{c}{chr(39) if c.endswith('s') else chr(39) + 's'} discount went from {int(o * 100)}% to {int(n * 100)}% on {w.day} {w.strftime('%B')}"
                          for c, w, o, n in d["disc_changes"]) + ", so the invoice date picks the rate") +
                      " (check: credit and fee per RMA)")
    spec = {
        "id": "credit-notes-apply", "track": "desk", "category": "bookkeeping",
        "title": "Turn September returns into credit notes and apply them",
        "ask": ("Can you turn September's returns into credit notes and apply them to what customers owe? Our returns policy in "
                "the folder has the rules. I need credit_notes.csv and invoice_balances.csv back.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            price_trap,
            f"{by['fee_mix']['rma']} mixes an ordered-in-error or overstock line with a no-fault line; the 15% fee comes off the first line "
            "only, and plain restocking-fee lines appear on other notes (check: credit and fee per RMA)",
            f"{by['exceeds']['rma']} credits more than its invoice's open balance (the invoice is partly paid); the rest goes to "
            f"{by['exceeds']['cust']}'s oldest other open invoice, not the newest and not left as a negative balance{more_spill} "
            "(checks: applied and unapplied per RMA; invoice balances after credits)",
            f"{by['paid_invoice']['rma']} names an invoice that was paid in full in August, so the whole credit goes to "
            f"{by['paid_invoice']['cust']}'s open invoices oldest first, reaching more than one (checks: applied and unapplied per RMA; "
            "invoice balances after credits)",
            f"{by['no_open']['cust']} has no open invoices at all, so {by['no_open']['rma']} stays entirely on account as unapplied "
            "credit (check: applied and unapplied per RMA)",
            f"{by['pair_first']['cust']} has two RMAs: {by['pair_first']['rma']} spills into the oldest invoice, which is the invoice "
            f"{by['pair_second']['rma']} names, so the second note finds less open than the report shows and ends with unapplied credit "
            "(checks: applied and unapplied per RMA; invoice balances after credits)",
            f"a rejected line on {by['rejected_line']['rma']} earns nothing, and {rma_role['pending']['no']} is still pending inspection "
            "and gets no credit note this month (checks: credit notes issued; credit and fee per RMA)",
            "the log writes customers upper-cased or with Inc./LLC, gives the invoice with or without its INV- prefix, and carries a "
            "preamble line and a BOM (check: credit and fee per RMA)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "credit note columns", "path": "credit_notes.csv", "columns": cn_header},
            {"type": "csv_set_equal", "name": "credit notes issued", "path": "credit_notes.csv", "column": "rma", "ref": "credit_notes.csv"},
            {"type": "csv_values_match", "name": "credit and fee per RMA", "path": "credit_notes.csv", "ref": "credit_notes.csv", "key": "rma",
             "columns": ["restocking_fee", "credit_amount"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [by["fee_mix"]["rma"], by["rejected_line"]["rma"]]},
            {"type": "csv_values_match", "name": "applied and unapplied per RMA", "path": "credit_notes.csv", "ref": "credit_notes.csv",
             "key": "rma", "columns": ["applied", "unapplied"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [by[k]["rma"] for k in ("exceeds", "paid_invoice", "no_open", "pair_first", "pair_second")]
             + [n["rma"] for n in spills]},
            {"type": "csv_set_equal", "name": "every open invoice listed", "path": "invoice_balances.csv", "column": "invoice",
             "ref": "invoice_balances.csv"},
            {"type": "csv_values_match", "name": "invoice balances after credits", "path": "invoice_balances.csv", "ref": "invoice_balances.csv",
             "key": "invoice", "columns": ["balance"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": touched},
        ],
    }
    write_task_yaml(here, record(spec, "credit-notes-apply", seed, knobs))
    print(f"seed={seed} notes={len(d['notes'])} open={len(d['open_list'])} " + " ".join(f"{n['role']}:{n['credit']}/{n['unapplied']}" for n in d["notes"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    add_knob_args(ap, KNOBS)
    a = ap.parse_args()
    knobs = parse_knob_args(a, KNOBS)
    for attempt in range(2000):
        d = build(a.seed * 1000 + attempt, knobs)
        if acceptable(d, knobs):
            break
    else:
        raise SystemExit("no acceptable draw")
    if a.describe:
        print(describe_json("credit-notes-apply", a.seed * 1000 + attempt, knobs, counts(d, knobs)))
        raise SystemExit(0)
    emit(a.seed * 1000 + attempt, a.naive, knobs, a.out)
