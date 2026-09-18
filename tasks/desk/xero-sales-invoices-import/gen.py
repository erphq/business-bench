#!/usr/bin/env python3
"""xero-sales-invoices-import: a print shop's job-app invoice export becomes Xero's sales invoice import.

    python gen.py [--seed N]

Business: a Melbourne print and design shop invoices out of a US-built job management app and is moving the
books to Xero. August's invoices must go in through Xero's SalesInvoiceTemplate.csv.

Traps (each caught by a check, see task.yaml):
  * the export is one row per invoice with up to three line columns and a delivery fee; Xero wants one row per line,
    with the delivery fee as its own line and the invoice fields repeated on every line
                                                                   (checks: one row per line; invoice lines)
  * the app writes dates month-first; Xero here is day-first, and due dates come from terms, including "20th of
    the following month"                                           (check: invoice and due dates)
  * contact names must be the existing Xero contact (matched on email), not the name typed into the job app
                                                                   (check: contact names)
  * tax types from the bookkeeper's list: GST on Income, GST Free Income for the overseas customer, BAS Excluded for
    gift vouchers                                                  (check: invoice lines)
  * account codes by line type (design 210, delivery 260, vouchers 835, everything else 200) (check: invoice lines)
  * the invoice discount applies to printing and design lines only, never delivery or vouchers (check: invoice lines)
  * void and draft invoices stay out                               (checks: invoices included; one row per line)
"""
from __future__ import annotations
import calendar, os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TEMPLATE = ["*ContactName", "EmailAddress", "*InvoiceNumber", "Reference", "*InvoiceDate", "*DueDate", "InventoryItemCode",
            "*Description", "*Quantity", "*UnitAmount", "Discount", "*AccountCode", "*TaxType", "Currency"]
ITEMS = [("BC-500", "Business cards, 500, 350gsm matte", 89.00), ("FLY-A5-1000", "A5 flyers, 1000, 150gsm gloss", 145.00),
         ("POS-A2", "A2 posters, satin", 12.50), ("BAN-PVC-2M", "PVC banner 2m x 1m with eyelets", 118.00),
         ("BRO-A4-TRI", "A4 trifold brochures, 500", 265.00), ("STK-CUT", "Die-cut stickers, 250", 96.00),
         ("DES-HR", "Graphic design, per hour", 95.00), ("DES-LOGO", "Logo design package", 650.00),
         ("GIFT-VOUCHER", "Gift voucher", 100.00)]
CUSTOMERS = [  # xero name, app name, domain, country
    ("Harbour Light Marine", "Harbour Light Marine Pty Ltd", "harbourlightmarine.com.au", "Australia"),
    ("Juniper Street Cafe", "Juniper St. Cafe", "juniperstreet.cafe", "Australia"),
    ("Larkspur Yoga", "LARKSPUR YOGA STUDIO", "larkspuryoga.com.au", "Australia"),
    ("Mossbank Accounting", "Mossbank Accounting", "mossbank.com.au", "Australia"),
    ("Riverbend Physio", "Riverbend Physiotherapy", "riverbendphysio.com.au", "Australia"),
    ("Tamarack Brewing Co", "Tamarack Brewing", "tamarackbrewing.com.au", "Australia"),
    ("Kingfisher Charters NZ", "Kingfisher Charters", "kingfishercharters.co.nz", "New Zealand"),
    ("Wren & Sparrow Bookshop", "Wren and Sparrow Books", "wrensparrowbooks.com.au", "Australia"),
]
TERMS = ["14 days", "30 days", "20th of following month", "Due on receipt"]


def due(d: date, terms: str) -> date:
    if terms == "14 days": return d + timedelta(days=14)
    if terms == "30 days": return d + timedelta(days=30)
    if terms == "Due on receipt": return d
    y, m = (d.year + (d.month == 12), d.month % 12 + 1)
    return date(y, m, 20)


def account(code: str, kind: str) -> str:
    if kind == "delivery": return "260"
    if code.startswith("DES-"): return "210"
    if code == "GIFT-VOUCHER": return "835"
    return "200"


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 909)
    invs = []
    num = 2400 + r.randint(0, 300)
    cust_terms = {c[0]: r.choice(TERMS[:3]) for c in CUSTOMERS}
    cust_terms["Juniper Street Cafe"] = "20th of following month"
    cust_terms["Kingfisher Charters NZ"] = "14 days"
    contacts = {c[0]: {"xero": c[0], "app": c[1], "email": f"accounts@{c[2]}", "country": c[3]} for c in CUSTOMERS}
    for i in range(20):
        num += 1
        cust = CUSTOMERS[i % len(CUSTOMERS)] if i < 16 else r.choice(CUSTOMERS)
        d = date(2026, 8, 1) + timedelta(days=r.randint(0, 30))
        status = "Sent" if r.random() < 0.6 else "Paid"
        n_lines = r.choice([1, 2, 2, 3])
        items = r.sample([it for it in ITEMS if it[0] != "GIFT-VOUCHER"], n_lines)
        lines = []
        for code, desc, price in items:
            qty = {"POS-A2": r.choice([10, 20, 25]), "DES-HR": r.choice([1.5, 2, 3, 4.5])}.get(code, r.choice([1, 1, 2]))
            lines.append({"code": code, "desc": desc, "qty": qty, "price": price, "kind": "item"})
        disc = r.choice([0, 0, 0, 5, 10]) if status != "Void" else 0
        delivery = r.choice([0, 0, 15.0, 22.5])
        invs.append({"number": f"INV-{num}", "cust": cust[0], "date": d, "status": status, "lines": lines, "disc": disc,
                     "delivery": delivery, "terms": cust_terms[cust[0]], "ref": f"JOB-{r.randint(7100, 7999)}"})
    # planted structure
    invs[2]["status"] = "Void"
    invs[11]["status"] = "Draft"
    kf = next(v for v in invs if v["cust"] == "Kingfisher Charters NZ" and v["status"] not in ("Void", "Draft"))
    kf["delivery"] = 38.0
    gv = next(v for v in invs if v["cust"] == "Wren & Sparrow Bookshop" and v["status"] not in ("Void", "Draft"))
    gv["lines"] = gv["lines"][:2] + [{"code": "GIFT-VOUCHER", "desc": "Gift voucher", "qty": 3, "price": 50.0, "kind": "item"}]
    gv["disc"] = 10
    gv["delivery"] = 15.0
    jn = next(v for v in invs if v["cust"] == "Juniper Street Cafe" and v["status"] not in ("Void", "Draft"))
    jn["date"] = date(2026, 8, r.choice([3, 5, 7, 11]))
    # make sure several kept invoices have day <= 12 (ambiguous month/day) and a discount with delivery
    amb = [v for v in invs if v["status"] not in ("Void", "Draft") and v is not jn][:4]
    for v in amb:
        v["date"] = date(2026, 8, r.randint(1, 12))
    dd = next(v for v in invs if v["status"] not in ("Void", "Draft") and v not in (gv, kf) and v["disc"] == 0)
    dd["disc"] = 5; dd["delivery"] = 22.5
    for v in invs:
        v["due"] = due(v["date"], v["terms"])
    return {"invs": invs, "contacts": contacts, "kf": kf, "gv": gv, "jn": jn, "amb": amb, "dd": dd}


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed * 1000 + 910)
    C = d["contacts"]

    hdr = ["Invoice #", "Status", "Customer", "Customer Email", "Job Ref", "Invoice Date", "Terms", "Discount %"]
    for k in (1, 2, 3):
        hdr += [f"Line {k} Item", f"Line {k} Description", f"Line {k} Qty", f"Line {k} Price (ex GST)"]
    hdr += ["Delivery Fee (ex GST)", "Total (ex GST)"]
    rows = []
    for v in d["invs"]:
        c = C[v["cust"]]
        row = [v["number"], v["status"], c["app"], c["email"].upper() if r.random() < 0.2 else c["email"], v["ref"],
               v["date"].strftime("%m/%d/%Y"), v["terms"], v["disc"] or ""]
        for k in range(3):
            if k < len(v["lines"]):
                ln = v["lines"][k]
                row += [ln["code"], ln["desc"], ln["qty"], f"${ln['price']:,.2f}"]
            else:
                row += ["", "", "", ""]
        sub = sum(l["qty"] * l["price"] * (1 - (v["disc"] / 100 if l["code"] != "GIFT-VOUCHER" else 0)) for l in v["lines"])
        row += [f"{v['delivery']:.2f}" if v["delivery"] else "", f"{sub + v['delivery']:,.2f}"]
        rows.append(row)
    write_xlsx(os.path.join(ws, "jobflow_invoices_export_2026-08.xlsx"), {"Invoices": {
        "merged_title": "JobFlow - Invoices - 08/01/2026 to 08/31/2026", "header": hdr, "rows": rows,
        "widths": {"C": 30, "D": 34}}}, creator="JobFlow")

    write_csv(os.path.join(ws, "xero_contacts_export.csv"), ["ContactName", "EmailAddress", "AccountNumber", "POCountry"],
              [[c["xero"], c["email"], f"C{100 + i:03d}", c["country"]] for i, c in enumerate(C.values())]
              + [["Quarry Road Nursery", "hello@quarryroad.com.au", "C120", "Australia"], ["Harbour Light Marine (old)", "info@harbourlightmarine.com.au", "C121", "Australia"]])

    write_csv(os.path.join(ws, "SalesInvoiceTemplate.csv"), TEMPLATE, [])

    write_text(os.path.join(ws, "xero_import_notes_from_bec.txt"), """August invoices into Xero

Use Xero's SalesInvoiceTemplate.csv columns as they are.

- One row per invoice line. The contact, email, invoice number, reference (the job ref), invoice date and due date go
  on every row of the invoice. The delivery fee is its own line: InventoryItemCode blank, Description "Delivery",
  Quantity 1.
- Only Sent and Paid invoices. Void and Draft stay out.
- ContactName must be exactly the contact name we already have in Xero (xero_contacts_export.csv), otherwise Xero
  makes a duplicate contact. JobFlow lets staff type whatever, so match on the email address.
- Dates: our Xero is set up for Australia, so DD/MM/YYYY. JobFlow exports month first.
- Due date from the invoice terms: 14 days or 30 days after the invoice date, "20th of following month" is the 20th
  of the next month, "Due on receipt" is the invoice date.
- UnitAmount is the ex-GST price as a plain number. We import tax exclusive.
- Discount is the invoice's Discount % on each printing and design line. Never discount delivery or gift vouchers.
- AccountCode: 210 Design Income for DES- items, 260 Other Revenue for delivery, 835 Gift Voucher Liability for
  gift vouchers, 200 Sales for everything else.
- TaxType, spelled as Xero has them: GST on Income for Australian customers; GST Free Income for customers outside
  Australia (exports), delivery included; BAS Excluded for gift vouchers.
- Currency AUD.

Bec
""")

    out = []
    for v in d["invs"]:
        if v["status"] in ("Void", "Draft"):
            continue
        c = C[v["cust"]]
        overseas = c["country"] != "Australia"
        base = [c["xero"], c["email"], v["number"], v["ref"], v["date"].strftime("%d/%m/%Y"), v["due"].strftime("%d/%m/%Y")]
        for ln in v["lines"]:
            gvline = ln["code"] == "GIFT-VOUCHER"
            tax = "BAS Excluded" if gvline else ("GST Free Income" if overseas else "GST on Income")
            disc = "" if gvline or not v["disc"] else f"{v['disc']:g}"
            out.append(base + [ln["code"], ln["desc"], f"{ln['qty']:g}", f"{ln['price']:.2f}", disc, account(ln["code"], "item"), tax, "AUD"])
        if v["delivery"]:
            out.append(base + ["", "Delivery", "1", f"{v['delivery']:.2f}", "", "260", "GST Free Income" if overseas else "GST on Income", "AUD"])
    for dd in (ref, sol):
        write_csv(os.path.join(dd, "xero_invoices.csv"), TEMPLATE, out)

    renamed = [v["number"] for v in d["invs"] if v["status"] not in ("Void", "Draft") and C[v["cust"]]["app"] != C[v["cust"]]["xero"]]
    date_trap = list(dict.fromkeys([d["jn"]["number"]] + [v["number"] for v in d["amb"]]))
    void = [v["number"] for v in d["invs"] if v["status"] in ("Void", "Draft")]
    write_task_yaml(HERE, {
        "id": "xero-sales-invoices-import", "track": "desk", "category": "reformatting",
        "title": "August job invoices into Xero's sales invoice import",
        "ask": "Please get our August invoices out of JobFlow and into Xero's sales invoice import file. Bec's notes explain how Xero wants it. Save it as xero_invoices.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "JobFlow exports one row per invoice with three line-column groups and a delivery fee column; Xero needs a row per line with the delivery fee as its own line and the contact, number and dates repeated on every row (checks: one row per line; invoice lines; contact names)",
            f"JobFlow dates are month-first and Xero is day-first; {len(d['amb'])} kept invoices fall on days 1 to 12 where a swap still looks like a valid date, and Juniper Street Cafe's '20th of following month' terms put the due date on 20 September (check: invoice and due dates)",
            "seven of eight customers are typed differently in JobFlow (Pty Ltd, Physiotherapy, all caps, 'and' for '&', a missing NZ suffix); ContactName comes from xero_contacts_export.csv by email, and the export also holds a stale 'Harbour Light Marine (old)' contact on a different address (check: contact names)",
            f"Kingfisher Charters NZ is overseas, so its lines and its delivery are GST Free Income; the gift voucher line on {d['gv']['number']} is BAS Excluded (check: invoice lines)",
            "account codes differ by line: DES- items 210, delivery 260, gift vouchers 835, everything else 200 (check: invoice lines)",
            f"invoice discounts go on printing and design lines only; {d['gv']['number']} has a 10% discount, a gift voucher and delivery, and {d['dd']['number']} a 5% discount with delivery (check: invoice lines)",
            f"{void[0]} is Void and {void[1]} is Draft; both stay out (checks: invoices included; one row per line)",
            "prices are '$650.00' text in the export, quantities include 1.5 design hours, and the export's Total column is after discount and must not be imported (check: invoice lines)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Xero template columns in order", "path": "xero_invoices.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "invoices included", "path": "xero_invoices.csv", "column": "*InvoiceNumber",
             "ref": "xero_invoices.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "one row per line", "path": "xero_invoices.csv", "equals_ref": "xero_invoices.csv"},
            {"type": "csv_values_match", "name": "contact names", "path": "xero_invoices.csv", "ref": "xero_invoices.csv", "key": "*InvoiceNumber",
             "columns": ["*ContactName"], "min_accuracy": 1.0, "must_match_keys": renamed},
            {"type": "csv_values_match", "name": "invoice and due dates", "path": "xero_invoices.csv", "ref": "xero_invoices.csv", "key": "*InvoiceNumber",
             "columns": ["*InvoiceDate", "*DueDate"], "normalize": ["strip"], "min_accuracy": 1.0, "must_match_keys": date_trap},
            {"type": "custom", "name": "invoice lines", "module": "check.py"},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
