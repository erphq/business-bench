#!/usr/bin/env python3
"""supplier-dispute-letter: a supplier invoice that does not match the purchase order becomes a dispute letter.

    python gen.py [--seed N]

Business: a small steel fabrication shop buys welding consumables from a distributor under a supply agreement.
The latest invoice bills price increases the shop never accepted, a short shipment, a surcharge and freight.
The operations manager wants a dispute letter to the supplier's receivables team.

Traps (each caught by a check, see task.yaml):
  * two lines are billed at the prices from the supplier's July increase notice; section 4.2 of the agreement
    fixes prices through December and the notice was never accepted, so both lines are disputed
                                                                       (checks: disputed lines with amounts; totals)
  * the flap discs were billed at the ordered quantity but only part was received; the contact tips arrived in
    two deliveries that add up to the full quantity and are not short  (checks: disputed lines with amounts; totals)
  * a fuel surcharge is not allowed under section 4.5                   (check: disputed lines with amounts)
  * the ops note says freight is free over $2,000; the agreement says $2,500 and this order is below it, so the
    freight line stands                                                 (checks: totals; freight-inclusive total absent)
  * one line is billed below the PO price and the note says not to raise it; netting it off understates the
    dispute                                                             (check: totals)
  * the letter must cite the price clause from the agreement             (check: price clause cited)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

BUYER = "Ironwood Fabrication"
SUPPLIER = "Cascade Industrial Supply"

ITEMS = [  # sku, description, keyword regex, price range, qty choices, role
    ("WW-ER70S6-035", "ER70S-6 MIG wire .035, 33 lb spool", r"(\bwire\b|er70s|spool)", (36.0, 44.0), [10, 12, 14], "ok"),
    ("GAS-C25-300", "Argon/CO2 75/25 cylinder refill, 300 cf", r"(argon|co2|c25|cylinder|\bgas\b)", (52.0, 64.0), [8, 10, 12], "price"),
    ("DSC-45-60G", "Flap disc 4.5 in, 60 grit", r"(flap|disc)", (5.4, 7.2), [40, 50], "short"),
    ("TIP-035-10", "Contact tips .035, pack of 10", r"(contact tip|\btips?\b)", (7.4, 9.2), [20, 25], "split"),
    ("GLV-MIG-L", "MIG welding gloves, large", r"(glove)", (11.0, 14.0), [24, 36], "price"),
    ("NZL-58-CONS", "Conical nozzle 5/8 in", r"(nozzle)", (8.6, 10.4), [10, 15], "under"),
    ("ADF-HLM-X9", "Auto-darkening helmet lens, 4.5 x 5.25", r"(lens|helmet)", (18.0, 24.0), [4, 6], "ok"),
]


def r2(x: float) -> float:
    return round(x + 1e-9, 2)


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 404)
    while True:
        lines = []
        for i, (sku, desc, kw, (lo, hi), qtys, role) in enumerate(ITEMS, 1):
            po_price = r2(r.uniform(lo, hi))
            qty = r.choice(qtys)
            inv_price = po_price
            if role == "price":
                inv_price = r2(po_price * r.uniform(1.06, 1.12))
            if role == "under":
                inv_price = r2(po_price - r.choice([0.30, 0.40, 0.50]))
            received = qty
            if role == "short":
                received = qty - 10
            lines.append({"line": i, "sku": sku, "desc": desc, "kw": kw, "role": role, "po_price": po_price, "qty": qty,
                          "inv_price": inv_price, "received": received, "po_ext": r2(po_price * qty), "inv_ext": r2(inv_price * qty)})
        po_total = r2(sum(l["po_ext"] for l in lines))
        inv_sub = r2(sum(l["inv_ext"] for l in lines))
        if not (2080 <= po_total <= 2420 and inv_sub < 2480):
            continue
        break
    surcharge = r2(inv_sub * 0.035)
    freight = float(r.choice([78, 85, 92, 96]))
    inv_total = r2(inv_sub + surcharge + freight)
    disputed = []
    for l in lines:
        if l["role"] == "price":
            disputed.append({"line": l["line"], "sku": l["sku"], "kw": l["kw"], "amount": r2((l["inv_price"] - l["po_price"]) * l["qty"]),
                             "why": f"billed at {l['inv_price']:.2f} instead of the PO price of {l['po_price']:.2f} on {l['qty']} units"})
        if l["role"] == "short":
            disputed.append({"line": l["line"], "sku": l["sku"], "kw": l["kw"], "amount": r2((l["qty"] - l["received"]) * l["inv_price"]),
                             "why": f"billed for {l['qty']} but {l['received']} were received"})
    disputed.append({"line": 8, "sku": "FUEL", "kw": r"(fuel|surcharge)", "amount": surcharge, "why": "fuel surcharge of 3.5%"})
    total_disputed = r2(sum(x["amount"] for x in disputed))
    under = next(l for l in lines if l["role"] == "under")
    netted = r2(total_disputed - (under["po_price"] - under["inv_price"]) * under["qty"])
    return {"lines": lines, "po_total": po_total, "inv_sub": inv_sub, "surcharge": surcharge, "freight": freight,
            "inv_total": inv_total, "disputed": disputed, "total_disputed": total_disputed, "pay_now": r2(inv_total - total_disputed),
            "with_freight": r2(total_disputed + freight), "netted": netted,
            "po_no": f"PO-2026-{r.randint(300, 699):04d}", "inv_no": f"INV-{r.randint(84000, 89999)}",
            "ar_contact": "{} {}".format(*person(r)), "ops": "{} {}".format(*person(r))}


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    L = d["lines"]
    po_date, ship1, ship2, inv_date = date(2026, 8, 10), date(2026, 8, 19), date(2026, 8, 24), date(2026, 8, 25)

    # purchase order export
    write_xlsx(os.path.join(ws, f"{d['po_no']}.xlsx"), {"PO": {
        "merged_title": f"{BUYER} - Purchase Order {d['po_no']}",
        "preamble": [[f"Supplier: {SUPPLIER}", None, None, f"PO date: {po_date.isoformat()}"], ["Terms: Net 30 per supply agreement SA-2025-11", None, None, "Ship to: 4410 Mill Rd, Tacoma WA 98402"], []],
        "header": ["Line", "Item", "Description", "Qty", "UOM", "Unit price", "Extended"],
        "rows": [[l["line"], l["sku"], l["desc"], l["qty"], "EA" if l["sku"] != "TIP-035-10" else "PK", l["po_price"], l["po_ext"]] for l in L]
                + [[None, None, "Merchandise total", None, None, None, d["po_total"]]],
        "number_formats": {"F": "#,##0.00", "G": "#,##0.00"}, "widths": {"B": 16, "C": 42}}}, creator="Purchasing")

    # receiving log: tips arrive in two deliveries, discs short
    rec = []
    for l in L:
        if l["role"] == "split":
            first = l["qty"] - 10
            rec.append([ship1.isoformat(), d["po_no"], l["line"], l["sku"], first, "partial"])
            rec.append([ship2.isoformat(), d["po_no"], l["line"], l["sku"], 10, "balance received"])
        elif l["role"] == "short":
            rec.append([ship1.isoformat(), d["po_no"], l["line"], l["sku"], l["received"], "10 backordered per packing slip"])
        else:
            rec.append([ship1.isoformat(), d["po_no"], l["line"], l["sku"], l["qty"], ""])
    rec.sort(key=lambda x: (x[0], x[2]))
    write_csv(os.path.join(ws, "receiving_log_aug2026.csv"), ["Received", "PO", "PO line", "Item", "Qty received", "Note"], rec, crlf=True)

    # supplier invoice pdf
    tbl = [["#", "Item", "Description", "Qty", "Unit", "Amount"]]
    for l in L:
        tbl.append([str(l["line"]), l["sku"], l["desc"], str(l["qty"]), f"{l['inv_price']:,.2f}", f"{l['inv_ext']:,.2f}"])
    tbl.append(["8", "FUEL", "Fuel surcharge 3.5%", "", "", f"{d['surcharge']:,.2f}"])
    tbl.append(["9", "FRT", "Freight - LTL", "", "", f"{d['freight']:,.2f}"])
    write_pdf_document(os.path.join(ws, f"{SUPPLIER.split()[0]}_invoice_{d['inv_no']}.pdf"), [
        ("title", SUPPLIER), ("small", "2200 Industrial Way, Kent WA 98032 - ar@cascadeindustrial.com"), ("hr", None),
        ("kv", [("Invoice", d["inv_no"]), ("Invoice date", inv_date.strftime("%m/%d/%Y")), ("Customer PO", d["po_no"]),
                ("Bill to", f"{BUYER}, 4410 Mill Rd, Tacoma WA 98402"), ("Terms", "Net 30")]),
        ("spacer", 8), ("table", tbl, {"col_widths": [18, 106, 196, 34, 56, 70], "shade_header": True}),
        ("spacer", 6),
        ("right", f"Subtotal {d['inv_sub']:,.2f}"), ("right", f"Fuel surcharge {d['surcharge']:,.2f}"),
        ("right", f"Freight {d['freight']:,.2f}"), ("right", f"<b>Total due USD {d['inv_total']:,.2f}</b>"),
        ("spacer", 10), ("small", "Prices reflect our 1 August 2026 price adjustment. Past-due balances accrue 1.5% per month."),
    ], font="Helvetica")

    write_text(os.path.join(ws, "supply_agreement_SA-2025-11_excerpt.md"), f"""# Supply Agreement SA-2025-11 (excerpt)

Between {SUPPLIER} ("Supplier") and {BUYER} ("Buyer"). Term: 1 January 2026 to 31 December 2026.

## 4. Prices and charges

4.1 Prices for the items in Schedule A are the prices stated on Buyer's purchase order.

4.2 Prices are fixed for the term of this Agreement. Supplier may change a price only on at least sixty (60) days'
written notice and with Buyer's written acceptance of the new price. Absent acceptance, the price on the purchase
order governs.

4.3 Prices exclude sales tax, which Supplier shall invoice where applicable.

4.4 Volume rebates are set out in Schedule B.

4.5 No fuel, energy, environmental or other surcharges may be added to any invoice unless agreed in writing by Buyer.

## 6. Delivery

6.1 Orders with a merchandise value of $2,500.00 or more ship freight prepaid. Below that value Supplier may invoice
actual freight on the invoice for the order.

6.2 Risk passes on delivery to Buyer's dock.

## 7. Invoicing and disputes

7.1 Payment terms are net thirty (30) days from the invoice date.

7.3 Buyer pays only for quantities received. Backordered quantities are invoiced when shipped.

7.4 Buyer may withhold payment of disputed amounts by notifying Supplier in writing within fifteen (15) days of the
invoice date, identifying the invoice lines and amounts in dispute. Undisputed amounts remain payable on terms.
""")

    write_text(os.path.join(ws, "price_increase_notice_july2026.txt"), f"""{SUPPLIER} - Customer notice
20 July 2026

Dear valued customer,

Due to rising costs from our mills and gas suppliers, prices on shielding gas refills, gloves and apparel will
increase between 6% and 12% effective 1 August 2026. Updated price sheets are available from your account rep.

Thank you for your continued business.
Pricing Team
""")

    ops_first = d["ops"].split()[0]
    write_text(os.path.join(ws, "note_from_ops.txt"), f"""Cascade invoice {d['inv_no']} (our {d['po_no']}) doesn't match. Can you write the dispute letter to their AR team,
attention {d['ar_contact']}? It has to reach them within 15 days of the invoice date. Things I noticed:

- some lines are billed at the new prices from their July letter. We never agreed to that, and section 4.2 of the
  supply agreement fixes prices for the year unless we accept in writing.
- receiving says we did not get everything they billed, check the receiving log against the invoice
- there is a fuel surcharge on it, pretty sure the agreement doesn't allow that
- they charged freight too. Orders over $2,000 ship free under the agreement so that should come off.
- a couple of lines might be billed a bit under the PO. Don't bring those up.

We'll pay the undisputed part now and want a credit memo for the rest. List each line you are disputing with its
amount and the total. Save it as dispute.md.

{ops_first}
""")

    # reference solution
    rows = []
    for x in d["disputed"]:
        l = next((l for l in L if l["line"] == x["line"]), None)
        label = f"Line {x['line']} ({x['sku']}, {l['desc']})" if l else "Line 8 (fuel surcharge)"
        rows.append(f"| {label} | {x['why']} | {x['amount']:,.2f} |")
    letter = f"""{BUYER}
4410 Mill Rd, Tacoma WA 98402

26 August 2026

{SUPPLIER}
Accounts Receivable
Attention: {d['ar_contact']}

**Re: Dispute of invoice {d['inv_no']} dated 25 August 2026, our purchase order {d['po_no']}**

Dear {d['ar_contact']},

Under section 7.4 of Supply Agreement SA-2025-11 we are giving written notice that we dispute part of invoice {d['inv_no']}. The disputed lines and amounts are:

| Invoice line | Reason | Amount disputed (USD) |
|---|---|---|
{chr(10).join(rows)}

Total disputed: ${d['total_disputed']:,.2f}.

The price lines are disputed under section 4.2 of the agreement, which fixes prices for the term unless we accept a new price in writing; we did not accept the increase announced in your notice of 20 July 2026, so the purchase order prices apply. Under section 7.3 we pay only for quantities received. Under section 4.5 no fuel or other surcharge may be added without our written agreement.

We are not disputing the freight charge of ${d['freight']:,.2f}, as the merchandise value of the order is below the $2,500.00 threshold in section 6.1.

We will pay the undisputed amount of ${d['pay_now']:,.2f} on terms. Please issue a credit memo for ${d['total_disputed']:,.2f}, or a corrected invoice.

Sincerely,

{d['ops']}
Operations Manager, {BUYER}
"""
    write_text(os.path.join(sol, "dispute.md"), letter)
    write_json(os.path.join(ref, "facts.json"), {"inv_no": d["inv_no"], "po_no": d["po_no"], "disputed": d["disputed"],
                                                  "total_disputed": d["total_disputed"], "pay_now": d["pay_now"],
                                                  "invoice_total": d["inv_total"], "freight": d["freight"],
                                                  "with_freight": d["with_freight"], "netted": d["netted"]})

    wf = d["with_freight"]
    write_task_yaml(HERE, {
        "id": "supplier-dispute-letter", "track": "desk", "category": "drafting",
        "title": "Dispute letter for a supplier invoice that does not match the PO",
        "ask": f"The Cascade invoice for our last welding supplies order doesn't match what we ordered and received. Please write the dispute letter to their AR team; {ops_first}'s note says what goes in it. Save it as dispute.md.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "two lines (shielding gas, gloves) are billed at the July increase prices; section 4.2 fixes prices unless the buyer accepts in writing, and the notice was never accepted, so the PO price governs (checks: disputed lines with amounts; total disputed and amount paid now)",
            "the flap discs are billed at the ordered 40 or 50 but 10 are backordered per the receiving log; the contact tips arrived in two deliveries that add up to the full quantity and are not short (checks: disputed lines with amounts; total disputed and amount paid now)",
            "the fuel surcharge is barred by section 4.5 and is disputed in full (check: disputed lines with amounts)",
            f"the ops note says freight is free over $2,000, but section 6.1 says $2,500 and the PO merchandise value is ${d['po_total']:,.2f}, so the ${d['freight']:,.2f} freight stands; disputing it gives ${wf:,.2f} (checks: total disputed and amount paid now; freight-inclusive total absent)",
            f"the nozzle line is billed below the PO price and the note says not to raise it; netting it against the overcharges gives ${d['netted']:,.2f} (check: total disputed and amount paid now)",
            "the letter must identify the invoice and PO and cite the price clause from the agreement, not just 'our contract' (checks: invoice and PO referenced; price clause cited)",
        ],
        "checks": [
            {"type": "file_exists", "name": "dispute.md exists", "path": "dispute.md"},
            {"type": "text_contains_all", "name": "invoice and PO referenced", "path": "dispute.md", "phrases": [d["inv_no"], d["po_no"]]},
            {"type": "custom", "name": "disputed lines with amounts", "module": "check.py"},
            {"type": "text_numbers_present", "name": "total disputed and amount paid now", "path": "dispute.md",
             "numbers": [d["total_disputed"], d["pay_now"]], "rel_tol": 0.00001},
            {"type": "text_sentence_matches", "name": "price clause cited", "path": "dispute.md",
             "all": [r"(section|clause|§|paragraph|art(icle)?\.?)\s*4\.2\b", r"(price|pricing)"]},
            {"type": "text_not_contains", "name": "freight-inclusive total absent", "path": "dispute.md",
             "phrases": [f"{wf:,.2f}", f"{wf:.2f}"]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
