#!/usr/bin/env python3
"""xero-sales-invoices-import: a print shop's job-app invoice export becomes Xero's sales invoice import.

    python gen.py [--seed N]
    python gen.py --list-traps
    python gen.py --traps-off contacts,void_draft --out DIR   # same draw, those pitfalls removed, same answer
    python gen.py --mutant discount --out DIR                 # a deliverable that falls for one trap

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
from bizgen.traps import TrapSet, add_trap_args, parse_trap_args, variant_dirs, active_trap_text  # noqa: E402

# Every trap in task.yaml, keyed. Switchable traps are removed at render time only, so build() and its
# random draws are identical in every variant and the correct answer never moves.
TRAPS = TrapSet(
    switchable={
        "dates": "JobFlow dates are month-first, Xero is day-first",
        "contacts": "customer names typed differently in JobFlow, upper-cased emails and a stale Xero contact",
        "void_draft": "a Void and a Draft invoice are in the export",
        "format_noise": "'$650.00' text prices and an after-discount Total column",
    },
    fixed={
        "layout": "one row per invoice in JobFlow, one row per line (delivery its own line) in Xero",
        "tax": "GST Free Income for the overseas customer, BAS Excluded for gift vouchers",
        "accounts": "account codes by line type",
        "discount": "discount on printing and design lines only",
    },
)
# task.yaml trap sentences, in order, and the trap each one describes
TRAP_KEYS = ["layout", "dates", "contacts", "tax", "accounts", "discount", "void_draft", "format_noise"]

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


def export_sheets(d: dict, r, traps: TrapSet) -> dict:
    """The JobFlow export workbook. With every trap on this is exactly the canonical workbook."""
    C = d["contacts"]
    noisy = traps.on("format_noise")
    when = (lambda x: x.strftime("%m/%d/%Y")) if traps.on("dates") else (lambda x: x.isoformat())
    hdr = ["Invoice #", "Status", "Customer", "Customer Email", "Job Ref", "Invoice Date", "Terms", "Discount %"]
    for k in (1, 2, 3):
        hdr += [f"Line {k} Item", f"Line {k} Description", f"Line {k} Qty", f"Line {k} Price (ex GST)"]
    hdr += ["Delivery Fee (ex GST)", "Total (ex GST)"] if noisy else ["Delivery Fee (ex GST)"]
    rows = []
    for v in d["invs"]:
        c = C[v["cust"]]
        upper = r.random() < 0.2  # drawn for every invoice, so a variant shares the canonical draw
        if not traps.on("void_draft") and v["status"] in ("Void", "Draft"):
            continue
        if traps.on("contacts"):
            row = [v["number"], v["status"], c["app"], c["email"].upper() if upper else c["email"], v["ref"],
                   when(v["date"]), v["terms"], v["disc"] or ""]
        else:
            row = [v["number"], v["status"], c["xero"], c["email"], v["ref"], when(v["date"]), v["terms"], v["disc"] or ""]
        for k in range(3):
            if k < len(v["lines"]):
                ln = v["lines"][k]
                row += [ln["code"], ln["desc"], ln["qty"], f"${ln['price']:,.2f}" if noisy else ln["price"]]
            else:
                row += ["", "", "", ""]
        sub = sum(l["qty"] * l["price"] * (1 - (v["disc"] / 100 if l["code"] != "GIFT-VOUCHER" else 0)) for l in v["lines"])
        if noisy:
            row += [f"{v['delivery']:.2f}" if v["delivery"] else "", f"{sub + v['delivery']:,.2f}"]
        else:
            row += [v["delivery"] or ""]
        rows.append(row)
    return {"Invoices": {
        "merged_title": "JobFlow - Invoices - " + ("08/01/2026 to 08/31/2026" if traps.on("dates") else "2026-08-01 to 2026-08-31"),
        "header": hdr, "rows": rows, "widths": {"C": 30, "D": 34}}}


def xero_rows(d: dict, trap: str | None = None) -> list[list]:
    """The import rows. With trap=None this is the correct answer; with a trap key, the rows an agent that is right
    except that it falls for that one trap would write."""
    C = d["contacts"]
    out = []
    for v in d["invs"]:
        if v["status"] in ("Void", "Draft") and trap != "void_draft":
            continue
        c = C[v["cust"]]
        overseas = c["country"] != "Australia"
        fmt = "%m/%d/%Y" if trap == "dates" else "%d/%m/%Y"   # the export's month-first dates copied straight across
        base = [c["app"] if trap == "contacts" else c["xero"], c["email"], v["number"], v["ref"], v["date"].strftime(fmt),
                v["due"].strftime(fmt)]
        first = len(out)
        for ln in v["lines"]:
            gvline = ln["code"] == "GIFT-VOUCHER"
            tax = "BAS Excluded" if gvline else ("GST Free Income" if overseas else "GST on Income")
            disc = "" if gvline or not v["disc"] else f"{v['disc']:g}"
            acct = account(ln["code"], "item")
            price = f"{ln['price']:.2f}"
            if trap == "tax":            # every line taxed as a domestic sale
                tax = "GST on Income"
            elif trap == "accounts":     # every line to Sales
                acct = "200"
            elif trap == "discount" and v["disc"]:  # the discount put on every line
                disc = f"{v['disc']:g}"
            elif trap == "format_noise":  # the export's '$650.00' text carried into UnitAmount
                price = f"${ln['price']:,.2f}"
            out.append(base + [ln["code"], ln["desc"], f"{ln['qty']:g}", price, disc, acct, tax, "AUD"])
        if v["delivery"] and trap != "layout":  # the delivery column not turned into its own line
            dtax = "GST on Income" if trap == "tax" else ("GST Free Income" if overseas else "GST on Income")
            ddisc = f"{v['disc']:g}" if trap == "discount" and v["disc"] else ""
            out.append(base + ["", "Delivery", "1", f"{v['delivery']:.2f}", ddisc, "200" if trap == "accounts" else "260", dtax,
                               "AUD"])
        if trap == "layout":             # invoice fields left on the first row only, not filled down
            for row in out[first + 1:]:
                row[0], row[1], row[3], row[4], row[5] = "", "", "", "", ""
    return out


def import_notes(traps: TrapSet) -> str:
    return ("""August invoices into Xero

Use Xero's SalesInvoiceTemplate.csv columns as they are.

- One row per invoice line. The contact, email, invoice number, reference (the job ref), invoice date and due date go
  on every row of the invoice. The delivery fee is its own line: InventoryItemCode blank, Description "Delivery",
  Quantity 1.
""" + ("- Only Sent and Paid invoices. Void and Draft stay out.\n" if traps.on("void_draft") else "- Only Sent and Paid invoices.\n")
        + ("""- ContactName must be exactly the contact name we already have in Xero (xero_contacts_export.csv), otherwise Xero
  makes a duplicate contact. JobFlow lets staff type whatever, so match on the email address.
""" if traps.on("contacts") else """- ContactName must be exactly the contact name we already have in Xero (xero_contacts_export.csv), otherwise Xero
  makes a duplicate contact.
""") + ("""- Dates: our Xero is set up for Australia, so DD/MM/YYYY. JobFlow exports month first.
""" if traps.on("dates") else """- Dates: our Xero is set up for Australia, so DD/MM/YYYY. JobFlow exports YYYY-MM-DD.
""") + """- Due date from the invoice terms: 14 days or 30 days after the invoice date, "20th of following month" is the 20th
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


def emit(seed: int, traps: TrapSet = TRAPS, out_dir: str | None = None, mutant: str | None = None) -> None:
    d = build(seed)
    if mutant:
        write_mutant(d, mutant, out_dir)
        return
    here = out_dir or HERE
    ws, ref, sol = task_dirs(HERE) if out_dir is None else variant_dirs(out_dir)
    if out_dir is not None:  # the custom grader module travels with the task
        import shutil
        shutil.copyfile(os.path.join(HERE, "check.py"), os.path.join(out_dir, "check.py"))
    r = rng(seed * 1000 + 910)
    C = d["contacts"]

    write_xlsx(os.path.join(ws, "jobflow_invoices_export_2026-08.xlsx"), export_sheets(d, r, traps), creator="JobFlow")

    write_csv(os.path.join(ws, "xero_contacts_export.csv"), ["ContactName", "EmailAddress", "AccountNumber", "POCountry"],
              [[c["xero"], c["email"], f"C{100 + i:03d}", c["country"]] for i, c in enumerate(C.values())]
              + [["Quarry Road Nursery", "hello@quarryroad.com.au", "C120", "Australia"]]
              + ([["Harbour Light Marine (old)", "info@harbourlightmarine.com.au", "C121", "Australia"]] if traps.on("contacts") else []))

    write_csv(os.path.join(ws, "SalesInvoiceTemplate.csv"), TEMPLATE, [])

    write_text(os.path.join(ws, "xero_import_notes_from_bec.txt"), import_notes(traps))

    out = xero_rows(d)
    for dd in (ref, sol):
        write_csv(os.path.join(dd, "xero_invoices.csv"), TEMPLATE, out)

    renamed = [v["number"] for v in d["invs"] if v["status"] not in ("Void", "Draft") and C[v["cust"]]["app"] != C[v["cust"]]["xero"]]
    date_trap = list(dict.fromkeys([d["jn"]["number"]] + [v["number"] for v in d["amb"]]))
    void = [v["number"] for v in d["invs"] if v["status"] in ("Void", "Draft")]
    spec = {
        "id": "xero-sales-invoices-import", "track": "desk", "category": "reformatting",
        "title": "August job invoices into Xero's sales invoice import",
        "ask": "Please get our August invoices out of JobFlow and into Xero's sales invoice import file. Bec's notes explain how Xero wants it. Save it as xero_invoices.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": active_trap_text([
            "JobFlow exports one row per invoice with three line-column groups and a delivery fee column; Xero needs a row per line with the delivery fee as its own line and the contact, number and dates repeated on every row (checks: one row per line; invoice lines; contact names)",
            f"JobFlow dates are month-first and Xero is day-first; {len(d['amb'])} kept invoices fall on days 1 to 12 where a swap still looks like a valid date, and Juniper Street Cafe's '20th of following month' terms put the due date on 20 September (check: invoice and due dates)",
            "seven of eight customers are typed differently in JobFlow (Pty Ltd, Physiotherapy, all caps, 'and' for '&', a missing NZ suffix); ContactName comes from xero_contacts_export.csv by email, and the export also holds a stale 'Harbour Light Marine (old)' contact on a different address (check: contact names)",
            f"Kingfisher Charters NZ is overseas, so its lines and its delivery are GST Free Income; the gift voucher line on {d['gv']['number']} is BAS Excluded (check: invoice lines)",
            "account codes differ by line: DES- items 210, delivery 260, gift vouchers 835, everything else 200 (check: invoice lines)",
            f"invoice discounts go on printing and design lines only; {d['gv']['number']} has a 10% discount, a gift voucher and delivery, and {d['dd']['number']} a 5% discount with delivery (check: invoice lines)",
            f"{void[0]} is Void and {void[1]} is Draft; both stay out (checks: invoices included; one row per line)",
            "prices are '$650.00' text in the export, quantities include 1.5 design hours, and the export's Total column is after discount and must not be imported (check: invoice lines)",
        ], TRAP_KEYS, traps),
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
    }
    if not traps.canonical:
        # A variant: same draw, same checks and reference, fewer pitfalls.
        spec["variant"] = {"of": "xero-sales-invoices-import", "draw": seed, "traps_off": sorted(traps.off)}
    write_task_yaml(here, spec)


# --------------------------------------------------------------------------- per-trap mutants

def write_mutant(d: dict, trap: str, out: str) -> None:
    if trap not in TRAP_KEYS:
        raise KeyError(trap)
    os.makedirs(out, exist_ok=True)
    write_csv(os.path.join(out, "xero_invoices.csv"), TEMPLATE, xero_rows(d, trap))


MUTANTS = {k: write_mutant for k in TRAP_KEYS}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--seed", type=int, default=0)
    add_trap_args(ap)
    a = ap.parse_args()
    traps = parse_trap_args(a, TRAPS, MUTANTS, TRAP_KEYS)
    emit(a.seed, traps, a.out, a.mutant)
