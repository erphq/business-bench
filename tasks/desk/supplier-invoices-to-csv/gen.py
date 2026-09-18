#!/usr/bin/env python3
"""supplier-invoices-to-csv: eight August supplier documents in eight layouts -> one AP import lines file.

    python gen.py [--seed N] [--naive DIR]

Business: Nightjar Coffee Roasters' bookkeeper keys supplier bills into accounting from an import file. August's
documents: seven invoices (one in EUR, one scanned) and a credit note, plus a statement of account that is not a bill.

Traps (each caught by a check, see task.yaml):
  * the document total sits in different places: at the foot, in a box at the top, or at the top with an account
    balance (including an older unpaid invoice) at the foot                     (check: document totals)
  * the Kaffa Import invoice is in EUR with German number format "1.237,50" and day-first dates (checks: quantities and prices; line amounts and discounts; dates and currency)
  * Bluestem Dairy prints a discount percent per line; Summit Office Supply prints a loyalty discount and delivery
    below the table, which the note says become lines of their own              (checks: line amounts and discounts; one row per line)
  * the Pacific Packaging credit memo prints positive figures; the note wants its quantities and amounts negative
                                                                                  (checks: quantities and prices; line amounts and discounts; document totals)
  * a statement of account from Pacific Packaging lists invoices but is not a bill (check: one row per line)
  * one invoice is an image-only scan                                           (check: one row per line)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from reportlab.pdfbase import pdfmetrics  # noqa: E402
try:  # write_pdf_document builds "<font>-Bold"; alias "Times" so Times-Roman / Times-Bold resolve
    pdfmetrics.registerFont(pdfmetrics.Font("Times", "Times-Roman", "WinAnsiEncoding"))
except Exception:
    pass

HEADER = ["line_ref", "vendor_id", "document_type", "document_number", "document_date", "currency", "description", "quantity",
          "unit_price", "discount_pct", "line_amount", "document_total"]
BUYER = "Nightjar Coffee Roasters\n2210 SE Division St\nPortland, OR 97202"
VENDORS = [("V-2031", "Pacific Packaging Supply"), ("V-2044", "Hollowell Electric"), ("V-2058", "Kaffa Import GmbH"),
           ("V-2062", "Bluestem Dairy Co."), ("V-2077", "Summit Office Supply"), ("V-2085", "Greenline Waste Services"),
           ("V-2090", "Cascade Cup and Lid"), ("V-2012", "Portland General Electric"), ("V-2019", "Rose City Linen"),
           ("V-2096", "Stumptown Equipment Repair")]
VID = {n: i for i, n in VENDORS}


def usd(x: float) -> str:
    return f"${x:,.2f}"


def plain(x: float) -> str:
    return f"{x:,.2f}"


def de(x: float) -> str:
    return eu_money_str(x)


def build(seed: int) -> dict:
    r = rng(seed)
    n = lambda lo, hi: r.randint(lo, hi)
    docs = {}

    def lines_of(spec):
        out = []
        for desc, qty, unit, disc in spec:
            out.append({"desc": desc, "qty": qty, "unit": unit, "disc": disc, "amount": round(qty * unit * (1 - disc / 100), 2)})
        return out
    # A: Pacific Packaging invoice, totals at the foot, tax 0% (Oregon has no sales tax) -> use a packaging fee line instead
    docs["A"] = {"vendor": "Pacific Packaging Supply", "type": "invoice", "no": f"PPS-{n(55100, 55999)}", "date": date(2026, 8, n(3, 6)), "ccy": "USD",
                 "lines": lines_of([("12 oz hot cups, case of 1000", n(3, 6), round(r.uniform(46, 52), 2), 0),
                                    ("Sip lids for 12/16 oz, case of 1000", n(2, 5), round(r.uniform(38, 44), 2), 0),
                                    ("Kraft cup sleeves, case of 1300", n(1, 3), round(r.uniform(54, 62), 2), 0),
                                    ("4-cup carrier trays, case of 300", n(1, 2), round(r.uniform(31, 37), 2), 0)]), "tax_rate": 0.0}
    # B: Hollowell Electric, amount due at the top, account balance at the foot
    docs["B"] = {"vendor": "Hollowell Electric", "type": "invoice", "no": f"HE-2026-{n(810, 880):04d}", "date": date(2026, 8, n(6, 9)), "ccy": "USD",
                 "lines": lines_of([("Service call", 1, 95.00, 0), ("Labor - replace grinder circuit", r.choice([2.5, 3.0, 3.5]), 110.00, 0),
                                    ("20A breaker", n(1, 3), round(r.uniform(17, 21), 2), 0)]), "tax_rate": 0.0,
                 "prev": round(r.uniform(420, 780), 2)}
    # C: Kaffa Import GmbH, EUR, German number format, freight below the table
    docs["C"] = {"vendor": "Kaffa Import GmbH", "type": "invoice", "no": f"RE-2026-{n(400, 499):04d}", "date": date(2026, 8, n(10, 13)), "ccy": "EUR",
                 "lines": lines_of([("Ethiopia Yirgacheffe Grade 1, green, 60 kg bag", n(2, 4), round(r.uniform(398, 440), 2), 0),
                                    ("Colombia Huila Excelso, green, 70 kg bag", n(2, 3), round(r.uniform(452, 490), 2), 0)])
                 + [{"desc": "Freight", "qty": 1, "unit": float(n(160, 210)), "disc": 0, "amount": 0.0, "below": True}], "tax_rate": 0.0}
    # D: Bluestem Dairy, per-line discount percent
    docs["D"] = {"vendor": "Bluestem Dairy Co.", "type": "invoice", "no": f"BD{n(771000, 779999)}", "date": date(2026, 8, n(13, 15)), "ccy": "USD",
                 "lines": lines_of([("Whole milk, 1 gal", n(18, 30), 4.10, r.choice([5, 8])), ("Oat milk barista, 32 oz", n(24, 48), 3.35, r.choice([10, 12])),
                                    ("Half and half, 1 qt", n(8, 16), 2.90, 0), ("Heavy cream, 1 qt", n(4, 10), 5.25, r.choice([5, 0]))]), "tax_rate": 0.0}
    # E: Summit Office Supply, loyalty discount and delivery below the table
    disc_e = float(n(12, 30))
    docs["E"] = {"vendor": "Summit Office Supply", "type": "invoice", "no": f"SOS-INV-{n(39000, 39999)}", "date": date(2026, 8, n(17, 19)), "ccy": "USD",
                 "lines": lines_of([("Thermal receipt paper 3-1/8 in, 50 rolls", n(1, 3), 38.99, 0), ("Toner cartridge 58A", 1, 89.50, 0),
                                    ("Copy paper, case of 10 reams", n(1, 3), 42.00, 0)])
                 + [{"desc": "Loyalty discount", "qty": 1, "unit": -disc_e, "disc": 0, "amount": -disc_e, "below": True},
                    {"desc": "Delivery", "qty": 1, "unit": 12.00, "disc": 0, "amount": 12.00, "below": True}], "tax_rate": 0.0}
    # F: Pacific Packaging credit memo, printed positive
    a = docs["A"]["lines"]
    docs["F"] = {"vendor": "Pacific Packaging Supply", "type": "credit_note", "no": f"CM-{n(20400, 20999)}", "date": date(2026, 8, n(20, 22)), "ccy": "USD",
                 "lines": lines_of([(a[0]["desc"], 1, a[0]["unit"], 0), (a[2]["desc"], 1, a[2]["unit"], 0)]), "tax_rate": 0.0,
                 "ref": docs["A"]["no"]}
    # G: Greenline Waste, scanned
    docs["G"] = {"vendor": "Greenline Waste Services", "type": "invoice", "no": f"GWS-{n(88000, 88999)}", "date": date(2026, 8, n(22, 24)), "ccy": "USD",
                 "lines": lines_of([("Dumpster service August", 1, float(n(360, 410)), 0), ("Fuel surcharge", 1, round(r.uniform(38, 52), 2), 0)]), "tax_rate": 0.0}
    # H: Cascade Cup and Lid, balance due in a box at the top only, a city tax line
    docs["H"] = {"vendor": "Cascade Cup and Lid", "type": "invoice", "no": f"CCL-26-{n(1100, 1299)}", "date": date(2026, 8, n(25, 27)), "ccy": "USD",
                 "lines": lines_of([("16 oz cold cups, case of 1000", n(2, 4), round(r.uniform(58, 66), 2), 0),
                                    ("Strawless lids 16 oz, case of 1000", n(2, 4), round(r.uniform(44, 50), 2), 0),
                                    ("Compostable straws, box of 2000", 1, round(r.uniform(27, 33), 2), 0)]), "tax_rate": 0.0}
    for k, dd in docs.items():
        for x in dd["lines"]:
            if x.get("below"):
                x["amount"] = round(x["qty"] * x["unit"], 2)
        dd["subtotal"] = round(sum(x["amount"] for x in dd["lines"] if not x.get("below")), 2)
        dd["total"] = round(sum(x["amount"] for x in dd["lines"]), 2)
    # H carries a 0.35% city business tax that is in the total but not a line
    docs["H"]["tax"] = round(docs["H"]["total"] * 0.0035, 2)
    docs["H"]["total"] = round(docs["H"]["total"] + docs["H"]["tax"], 2)
    rows = []
    for k in "ABCDEFGH":
        dd = docs[k]
        sign = -1 if dd["type"] == "credit_note" else 1
        for i, x in enumerate(dd["lines"], start=1):
            rows.append({"line_ref": f"{dd['no']}-{i}", "vendor_id": VID[dd["vendor"]], "document_type": dd["type"], "document_number": dd["no"],
                         "document_date": dd["date"].isoformat(), "currency": dd["ccy"], "description": x["desc"],
                         "quantity": sign * x["qty"], "unit_price": x["unit"], "discount_pct": x["disc"], "line_amount": round(sign * x["amount"], 2),
                         "document_total": round(sign * dd["total"], 2)})
    return {"docs": docs, "rows": rows}


def render(ws: str, d: dict, seed: int) -> None:
    docs = d["docs"]
    P = os.path.join(ws, "supplier_documents_2026-08")
    os.makedirs(P, exist_ok=True)
    # A: letter, Helvetica, header kv, shaded table, totals at the foot
    A = docs["A"]
    write_pdf_document(os.path.join(P, f"PacificPackaging_{A['no']}.pdf"), [
        ("title", "PACIFIC PACKAGING SUPPLY CO."), ("small", "1450 NW 15th Ave, Portland, OR 97209  |  ar@pacpacksupply.example"), ("hr", None),
        ("kv", [("Invoice No.", A["no"]), ("Invoice Date", A["date"].strftime("%B %-d, %Y")), ("Terms", "Net 30"), ("Bill To", BUYER)]), ("spacer", 10),
        ("table", [["Item", "Description", "Qty", "Unit Price", "Amount"]] +
         [[f"{i}", x["desc"], x["qty"], usd(x["unit"]), usd(x["amount"])] for i, x in enumerate(A["lines"], 1)],
         {"col_widths": [30, 230, 40, 80, 80], "shade_header": True}), ("spacer", 8),
        ("right", f"Subtotal {usd(A['subtotal'])}"), ("right", "Sales tax (Oregon) $0.00"), ("right", f"<b>INVOICE TOTAL {usd(A['total'])}</b>"),
        ("spacer", 14), ("small", "Thank you for your business. Returns within 30 days with RMA only.")], pagesize="letter", font="Helvetica", base_size=10)
    # B: Times, amount due box at the top, account balance at the foot
    B = docs["B"]
    write_pdf_document(os.path.join(P, f"hollowell_invoice_{B['no']}.pdf"), [
        ("kv", [("AMOUNT DUE THIS INVOICE", usd(B["total"])), ("Due by", "09/05/2026")], {"col_widths": [180, 200]}), ("hr", None),
        ("title", "Hollowell Electric"), ("p", "Licensed electrical contractor #CCB 204417<br/>88 Union St, Portland, OR 97214"), ("spacer", 6),
        ("p", f"Invoice #: {B['no']}<br/>Date of service: {B['date'].strftime('%m/%d/%Y')}<br/>Customer: Nightjar Coffee Roasters (acct 4471)"), ("spacer", 8),
        ("table", [["Service / material", "Hours or qty", "Rate", "Amount"]] +
         [[x["desc"], f"{x['qty']:g}", plain(x["unit"]), plain(x["amount"])] for x in B["lines"]], {"col_widths": [230, 80, 70, 80], "grid": True}),
        ("spacer", 18), ("h", "Account summary"),
        ("kv", [("This invoice", plain(B["total"])), ("Previous balance (invoice HE-2026-0702, unpaid)", plain(B["prev"])),
                ("Total account balance", plain(round(B["total"] + B["prev"], 2)))], {"col_widths": [260, 120]}),
        ("small", "Past-due balances accrue 1.5% per month.")], pagesize="letter", font="Times", base_size=11)
    # C: A4, Times, German/English, German number format, freight under the table
    C = docs["C"]
    items = [x for x in C["lines"] if not x.get("below")]
    fr = [x for x in C["lines"] if x.get("below")][0]
    write_pdf_document(os.path.join(P, f"Kaffa_Rechnung_{C['no']}.pdf"), [
        ("right", "Kaffa Import GmbH<br/>Am Sandtorkai 41, 20457 Hamburg<br/>USt-IdNr. DE 298 441 507"), ("spacer", 10),
        ("p", "An / To: Nightjar Coffee Roasters, 2210 SE Division St, Portland OR 97202, USA"), ("spacer", 8),
        ("title", "Rechnung / Invoice"),
        ("kv", [("Rechnung Nr. / Invoice no.", C["no"]), ("Datum / Date", C["date"].strftime("%d.%m.%Y")), ("Waehrung / Currency", "EUR")],
         {"col_widths": [150, 200]}), ("spacer", 8),
        ("table", [["Pos.", "Beschreibung / Description", "Menge / Qty", "Einzelpreis / Unit price", "Gesamt / Total"]] +
         [[f"{i}", x["desc"], x["qty"], de(x["unit"]), de(x["amount"])] for i, x in enumerate(items, 1)],
         {"col_widths": [30, 200, 60, 90, 80], "grid": True}), ("spacer", 6),
        ("kv", [("Zwischensumme / Subtotal", de(C["subtotal"])), ("Freight", de(fr["amount"])),
                ("USt. 0% (Ausfuhrlieferung / export)", de(0.0)), ("Gesamtbetrag / Total EUR", de(C["total"]))], {"col_widths": [200, 100]}),
        ("spacer", 10), ("small", "Zahlbar innerhalb 30 Tagen / Payable within 30 days. IBAN DE44 2005 0550 1234 5678 90")],
        pagesize="a4", font="Times", base_size=10)
    # D: Courier, grid, per-line discount, total at the foot
    D = docs["D"]
    write_pdf_document(os.path.join(P, f"bluestem_{D['no']}.pdf"), [
        ("title", "BLUESTEM DAIRY CO."), ("p", "Wholesale dairy - route 7"),
        ("kv", [("Delivery ticket / invoice", D["no"]), ("Date", D["date"].isoformat()), ("Stop", "NIGHTJAR COFFEE - DIVISION")]), ("spacer", 6),
        ("table", [["Code", "Product", "Qty", "Price", "Disc %", "Net"]] +
         [[f"BD-{10 + i}", x["desc"], x["qty"], f"{x['unit']:.2f}", f"{x['disc']:g}" if x["disc"] else "-", f"{x['amount']:.2f}"] for i, x in enumerate(D["lines"], 1)],
         {"col_widths": [50, 170, 40, 55, 50, 65], "grid": True}), ("spacer", 6),
        ("right", f"TOTAL DUE {D['total']:.2f}"), ("small", "Discounts reflect your volume tier. Crates must be returned.")],
        pagesize="letter", font="Courier", base_size=9)
    # E: A4, Helvetica, qty first, loyalty discount and delivery below the table
    E = docs["E"]
    items = [x for x in E["lines"] if not x.get("below")]
    below = [x for x in E["lines"] if x.get("below")]
    write_pdf_document(os.path.join(P, f"SummitOffice-{E['no']}.pdf"), [
        ("h", "Summit Office Supply"), ("small", "Order online at summitoffice.example | 503-555-0190"),
        ("table", [["Bill number", "Order date", "Account"], [E["no"], E["date"].strftime("%b %d %Y"), "NIGHT-0093"]], {"col_widths": [150, 150, 150]}),
        ("spacer", 10),
        ("table", [["Qty", "Description", "Price/Unit", "Ext."]] + [[x["qty"], x["desc"], f"$ {x['unit']:,.2f}", f"$ {x['amount']:,.2f}"] for x in items],
         {"col_widths": [40, 250, 80, 80]}), ("spacer", 6),
        ("kv", [("Merchandise", f"$ {E['subtotal']:,.2f}"), (below[0]["desc"], f"-$ {abs(below[0]['amount']):,.2f}"),
                (below[1]["desc"], f"$ {below[1]['amount']:,.2f}"), ("Please pay", f"$ {E['total']:,.2f}")], {"col_widths": [120, 100]})],
        pagesize="a4", font="Helvetica", base_size=9)
    # F: credit memo, positive figures, letter, Helvetica
    F = docs["F"]
    write_pdf_document(os.path.join(P, f"PacificPackaging_{F['no']}.pdf"), [
        ("title", "CREDIT MEMO"), ("p", "PACIFIC PACKAGING SUPPLY CO. - 1450 NW 15th Ave, Portland, OR 97209"), ("hr", None),
        ("kv", [("Credit Memo No.", F["no"]), ("Date", F["date"].strftime("%m/%d/%y")), ("Applies to invoice", F["ref"]),
                ("Reason", "Returned unopened cases (damaged in transit)")]), ("spacer", 10),
        ("table", [["Item", "Description", "Qty returned", "Unit Price", "Credit"]] +
         [[f"{i}", x["desc"], x["qty"], usd(x["unit"]), usd(x["amount"])] for i, x in enumerate(F["lines"], 1)],
         {"col_widths": [30, 230, 70, 70, 70], "shade_header": True}), ("spacer", 8),
        ("right", f"<b>TOTAL CREDIT {usd(F['total'])}</b>"), ("small", "This credit will be applied to your next statement.")],
        pagesize="letter", font="Helvetica", base_size=10)
    # G: scanned
    G = docs["G"]
    write_scan_pdf(os.path.join(P, f"scan_greenline_{G['date'].strftime('%Y%m%d')}.pdf"), [
        "GREENLINE WASTE SERVICES", "PO Box 8812  Portland OR 97208", "", "INVOICE", f"Number:  {G['no']}", f"Date:    {G['date'].strftime('%d-%b-%Y')}",
        "Customer: NIGHTJAR COFFEE ROASTERS", "", "DESCRIPTION              QTY    AMOUNT", "-" * 40]
        + [f"{x['desc']:<25}{x['qty']:>3}  {x['amount']:>8.2f}" for x in G["lines"]]
        + ["-" * 40, f"{'TOTAL DUE':<28}  {G['total']:>8.2f}", "", "Pay online or mail check to PO Box above."], font_size=30, seed=seed + 7, skew_deg=0.7, noise=600)
    # H: A4, balance due in a box at the top, no totals at the foot, extended before unit
    H = docs["H"]
    write_pdf_document(os.path.join(P, f"cascade_cup_lid_{H['no']}.pdf"), [
        ("table", [["CASCADE CUP AND LID", f"BALANCE DUE  USD {H['total']:,.2f}"], ["Wholesale disposables", f"Invoice {H['no']}"],
                   ["Tacoma, WA", f"Issued {H['date'].strftime('%-d %B %Y')}"]], {"col_widths": [260, 220], "grid": True, "shade_header": True}),
        ("spacer", 10), ("p", "Sold to: Nightjar Coffee Roasters, Portland OR"), ("spacer", 6),
        ("table", [["Line", "Amount (USD)", "Qty", "Unit (USD)", "Item"]] +
         [[f"{i}", f"{x['amount']:,.2f}", x["qty"], f"{x['unit']:,.2f}", x["desc"]] for i, x in enumerate(H["lines"], 1)],
         {"col_widths": [30, 80, 35, 70, 250]}), ("spacer", 6),
        ("small", f"Includes Tacoma B&amp;O pass-through of USD {H['tax']:,.2f} in the balance due. Net 15.")], pagesize="a4", font="Helvetica", base_size=9)
    # distractor: statement of account
    write_pdf_document(os.path.join(P, "PacificPackaging_statement_2026-08-31.pdf"), [
        ("title", "Statement of Account"), ("p", "PACIFIC PACKAGING SUPPLY CO."),
        ("kv", [("Customer", "Nightjar Coffee Roasters"), ("Statement date", "08/31/2026")]), ("spacer", 8),
        ("table", [["Date", "Document", "Charges", "Credits", "Balance"],
                   [A["date"].strftime("%m/%d/%Y"), f"Invoice {A['no']}", usd(A["total"]), "", usd(A["total"])],
                   [F["date"].strftime("%m/%d/%Y"), f"Credit memo {F['no']}", "", usd(F["total"]), usd(round(A["total"] - F["total"], 2))]], {"grid": True}),
        ("right", f"Amount due {usd(round(A['total'] - F['total'], 2))}"), ("small", "This is a statement, not an invoice. Please pay from invoices.")],
        pagesize="letter", font="Helvetica", base_size=10)


def acceptable(d: dict) -> bool:
    B, C = d["docs"]["B"], d["docs"]["C"]
    return all(abs(x["amount"]) >= 1000 for x in C["lines"] if not x.get("below")) and B["prev"] > 0


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    rows = [[x[h] if not isinstance(x[h], float) else f"{x[h]:.2f}" for h in HEADER] for x in d["rows"]]
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    render(ws, d, seed)
    write_csv(os.path.join(ws, "vendor_list.csv"), ["vendor_id", "vendor_name", "payment_terms"],
              [[i, nm, "Net 30"] for i, nm in sorted(VENDORS)])
    write_csv(os.path.join(ws, "ap_import_template.csv"), HEADER, [])
    write_text(os.path.join(ws, "note_from_ines.txt"),
               "August bills for the import\n\n"
               "Everything from suppliers for August is in supplier_documents_2026-08. The accounting import takes one row per line on the "
               "template. How to fill it:\n\n"
               "- line_ref: the document number exactly as printed, a hyphen, then the line number (1, 2, 3 ... in the order you enter "
               "the lines for that document).\n"
               "- vendor_id: from vendor_list.csv.\n"
               "- document_type: invoice or credit_note.\n"
               "- document_date: YYYY-MM-DD.\n"
               "- currency: the currency the document is in (USD or EUR). Leave the amounts in that currency - I convert when I post. "
               "Plain numbers, no symbols or thousands separators.\n"
               "- description as printed on the line.\n"
               "- discount_pct: the discount percent printed on the line, 0 if there is none. line_amount is after that discount.\n"
               "- Freight, delivery and discounts printed under the item table are lines too: enter them after the items, quantity 1, "
               "unit price and line amount equal to the amount (negative for a discount). Do not enter subtotal, tax or total rows.\n"
               "- document_total: what that document is for, on every line of it - not the account balance.\n"
               "- Credit memos: make quantity, line_amount and document_total negative so they net off; unit_price stays positive.\n\n"
               "Statements are not bills - skip them.\n\n- Ines\n")
    write_csv(os.path.join(ref, "invoice_lines.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "invoice_lines.csv"), HEADER, rows)
    docs = d["docs"]
    refs = lambda k: [f"{docs[k]['no']}-{i}" for i in range(1, len(docs[k]["lines"]) + 1)]
    write_json(os.path.join(ref, "notes.json"), {k: {"no": v["no"], "total": v["total"], "vendor": v["vendor"]} for k, v in docs.items()})
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    P = "invoice_lines.csv"
    write_task_yaml(HERE, {
        "id": "supplier-invoices-to-csv", "track": "desk", "category": "extraction",
        "title": "Key August supplier bills into the AP import file",
        "ask": ("Can you get all of August's supplier bills into the accounting import file for me? The documents are in the folder and "
                "Ines's note says how the template is filled in. Save it as invoice_lines.csv.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            f"the document total sits in a different place on each layout: at the foot, in a box at the top with no totals at the foot "
            f"(Cascade, which also folds a city tax into it), or at the top with an account balance that adds an older unpaid invoice at "
            f"the foot (Hollowell) (check: document totals)",
            f"Kaffa Import's invoice is in EUR with German number format (\"1.237,50\") and a day-first date, and its freight sits under the "
            f"item table (checks: quantities and prices; line amounts and discounts; dates and currency)",
            "Bluestem Dairy prints a discount percent on some lines, so the net is not quantity times price; Summit Office Supply prints a "
            "loyalty discount and a delivery charge under the table, which the note makes lines of their own "
            "(checks: line amounts and discounts; one row per line)",
            f"the Pacific Packaging credit memo {docs['F']['no']} prints positive figures and must go in with negative quantity, amount and "
            "total (checks: quantities and prices; line amounts and discounts; document totals)",
            "a Pacific Packaging statement of account in the same folder lists the invoice and the credit memo again; it is not a bill "
            "(checks: one row per line; row count)",
            f"the Greenline Waste invoice {docs['G']['no']} is an image-only scan (checks: one row per line; descriptions)",
            "vendor_id comes from the vendor list, where printed names like PACIFIC PACKAGING SUPPLY CO. are spelled differently (check: document identity)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per line", "path": P, "column": "line_ref", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "document identity", "path": P, "ref": P, "key": "line_ref",
             "columns": ["vendor_id", "document_type", "document_number"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "dates and currency", "path": P, "ref": P, "key": "line_ref",
             "columns": ["document_date", "currency"], "min_accuracy": 1.0, "must_match_keys": refs("C")},
            {"type": "csv_values_match", "name": "descriptions", "path": P, "ref": P, "key": "line_ref", "columns": ["description"],
             "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": refs("G")},
            {"type": "csv_values_match", "name": "quantities and prices", "path": P, "ref": P, "key": "line_ref",
             "columns": ["quantity", "unit_price"], "must_match_keys": refs("C") + refs("F"), **num},
            {"type": "csv_values_match", "name": "line amounts and discounts", "path": P, "ref": P, "key": "line_ref",
             "columns": ["discount_pct", "line_amount"], "must_match_keys": refs("C") + refs("D") + refs("E") + refs("F"), **num},
            {"type": "csv_values_match", "name": "document totals", "path": P, "ref": P, "key": "line_ref", "columns": ["document_total"],
             "must_match_keys": refs("B") + refs("F") + refs("H"), **num},
        ],
    })
    print(f"seed={seed} rows={len(rows)} totals=" + ", ".join(f"{k}:{v['no']}={v['total']}" for k, v in docs.items()))


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: item-table rows only (nothing under the tables), figures as printed (credit memo positive,
    EUR read with the comma as a thousands separator, Bluestem net ignored in favour of qty x price), total = the last
    money figure on the page (the Hollowell account balance), statement rows skipped."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for k in "ABCDEFGH":
        dd = d["docs"][k]
        for i, x in enumerate([x for x in dd["lines"] if not x.get("below")], start=1):
            unit, amt, total = x["unit"], round(x["qty"] * x["unit"], 2), dd["total"]
            if k == "C":
                unit, amt, total = float(de(unit).replace(".", "").replace(",", "")), float(de(amt).replace(".", "").replace(",", "")), float(de(total).replace(".", "").replace(",", ""))
            if k == "B":
                total = round(dd["total"] + dd["prev"], 2)
            rows.append([f"{dd['no']}-{i}", VID[dd["vendor"]], dd["type"], dd["no"], dd["date"].isoformat(), "USD", x["desc"], x["qty"], unit, 0, amt, total])
    write_csv(os.path.join(out, "invoice_lines.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(200):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
