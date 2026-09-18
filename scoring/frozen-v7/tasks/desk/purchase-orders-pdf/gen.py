#!/usr/bin/env python3
"""purchase-orders-pdf: customer purchase orders in five layouts (one faxed, one two pages, one revised) -> order-entry lines.

    python gen.py [--seed N] [--naive DIR]

Business: Ironwood Fabrication, a small metal fabricator, receives customer POs as email attachments. The order
desk keys every PO line into the order system from an import template.

Traps (each caught by a check, see task.yaml):
  * Westbrook Plumbing's PO runs onto a second page with the column header repeated; its lines are numbered 10, 20, 30
    and each line has its own need-by date                                    (checks: one row per PO line; need-by dates)
  * Northfield Auto Body prints only the extended amount per line, headed "Amount"; the unit price is amount / qty
                                                                                (check: quantities and unit prices)
  * Pemberton HVAC sent revision 1 and then revision 2 of the same PO number; revision 2 changes a quantity and strikes
    out a line marked CANCELLED, and the file names do not say which is which (checks: one row per PO line; quantities and unit prices; line amounts)
  * Pemberton prints the extended price before the unit price                  (check: line amounts)
  * the Silverline Logistics PO is a faxed image                               (checks: one row per PO line; part numbers and descriptions)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from reportlab.pdfbase import pdfmetrics  # noqa: E402
try:
    pdfmetrics.registerFont(pdfmetrics.Font("Times", "Times-Roman", "WinAnsiEncoding"))
except Exception:
    pass

HEADER = ["po_line_ref", "customer_id", "po_number", "po_date", "line", "part_number", "description", "quantity", "unit_price",
          "line_amount", "need_by"]
CUSTOMERS = [("C-310", "Pinnacle Roofing"), ("C-322", "Northfield Auto Body"), ("C-341", "Westbrook Plumbing"), ("C-356", "Pemberton HVAC"),
             ("C-367", "Silverline Logistics"), ("C-305", "Acme Industrial"), ("C-379", "Granite Peak Outfitters"), ("C-388", "Harbor Light Marine")]
CID = {n: i for i, n in CUSTOMERS}
CATALOG = [("IF-BRK-1040", "Galvanized L-bracket 4x4x3/16, drilled"), ("IF-BRK-1062", "Galvanized U-bracket 6in, slotted"),
           ("IF-FLS-2210", "Drip edge flashing 10ft 24ga, painted"), ("IF-FLS-2234", "Step flashing 5x7 aluminum, bundle of 50"),
           ("IF-HRL-3302", "Stainless handrail post 42in"), ("IF-HRL-3318", "Handrail end cap, brushed"),
           ("IF-PLT-4105", "Base plate 8x8x1/2 with 4 holes"), ("IF-PLT-4121", "Gusset plate 6x6x3/8"),
           ("IF-SPT-5010", "Pipe support clamp 2in, epoxy coated"), ("IF-SPT-5024", "Pipe support clamp 4in, epoxy coated"),
           ("IF-SPT-5040", "Trapeze hanger kit 24in"), ("IF-SPT-5066", "Seismic brace kit, 3/8 rod"),
           ("IF-BOX-6003", "Service box enclosure 12x12x6"), ("IF-BOX-6017", "Service box enclosure 16x16x8"),
           ("IF-CUR-7101", "Equipment curb 36x36, 14ga"), ("IF-CUR-7140", "Duct support rail 8ft"),
           ("IF-GRD-8008", "Condenser guard cage 36in"), ("IF-GRD-8015", "Bumper guard, powder coat yellow"),
           ("IF-RCK-9002", "Pallet rack upright protector 12in"), ("IF-RCK-9019", "Dock plate lip bracket")]


def build(seed: int) -> dict:
    r = rng(seed)
    cat = list(CATALOG)
    band = {"BRK": (3, 15), "FLS": (8, 40), "HRL": (40, 120), "PLT": (12, 60), "SPT": (4, 22), "BOX": (60, 180), "CUR": (150, 400),
            "GRD": (80, 260), "RCK": (20, 70)}
    price = {p: round(r.uniform(*band[p.split("-")[1]]), 2) for p, _ in cat}
    for p in ("IF-SPT-5040", "IF-SPT-5066"):      # hanger and brace kits cost more than a clamp
        price[p] = round(r.uniform(25, 90), 2)
    desc = dict(cat)
    pos = {}

    def lines(parts, lo, hi, step=1):
        return [{"part": p, "desc": desc[p], "qty": r.randrange(lo, hi + 1, step), "unit": price[p]} for p in parts]
    pos["pinnacle"] = {"cust": "Pinnacle Roofing", "no": f"PR-{r.randint(24000, 24999)}", "date": date(2026, 9, r.randint(1, 4)),
                       "lines": lines(r.sample([p for p, _ in cat if "FLS" in p or "BRK" in p], 4), 20, 300, 10)}
    pos["northfield"] = {"cust": "Northfield Auto Body", "no": f"NAB-{r.randint(900, 999):04d}", "date": date(2026, 9, r.randint(3, 7)),
                         "lines": lines(r.sample([p for p, _ in cat if "GRD" in p or "RCK" in p or "PLT" in p], 4), 2, 24)}
    wb_parts = [p for p, _ in cat if "SPT" in p or "BOX" in p or "PLT" in p or "BRK" in p]
    wlines = []
    for k in range(44):
        p = wb_parts[k % len(wb_parts)] if k < len(wb_parts) else r.choice(wb_parts)
        wlines.append({"part": p, "desc": desc[p], "qty": r.randrange(4, 120, 2), "unit": price[p]})
    pos["westbrook"] = {"cust": "Westbrook Plumbing", "no": f"45000{r.randint(18000, 18999)}", "date": date(2026, 9, r.randint(6, 9)), "lines": wlines}
    pem = lines(r.sample([p for p, _ in cat if "CUR" in p or "GRD" in p or "SPT" in p or "HRL" in p], 4), 2, 40)
    pos["pemberton"] = {"cust": "Pemberton HVAC", "no": f"PH-{r.randint(7000, 7999)}", "date": date(2026, 9, r.randint(8, 10)), "lines": pem}
    pos["silverline"] = {"cust": "Silverline Logistics", "no": f"SL-PO-{r.randint(3000, 3999)}", "date": date(2026, 9, r.randint(10, 14)),
                         "lines": lines(r.sample([p for p, _ in cat if "RCK" in p or "GRD" in p or "BRK" in p], 3), 6, 60, 6)}
    # line numbers and need-by dates
    for k, po in pos.items():
        step = 10 if k == "westbrook" else 1
        hdr_need = po["date"] + timedelta(days=r.randint(21, 35))
        po["need_by"] = hdr_need
        for i, x in enumerate(po["lines"], start=1):
            x["line"] = i * step
            x["need"] = (po["date"] + timedelta(days=r.choice([14, 21, 28, 35, 42]))) if k == "westbrook" else hdr_need
    # Pemberton revision 2: line 2 quantity changes, line 3 cancelled
    rev1 = [dict(x) for x in pem]
    rev2 = [dict(x) for x in pem]
    rev2[1]["qty"] = rev1[1]["qty"] + r.choice([4, 6, 10]) if rev1[1]["qty"] <= 6 else rev1[1]["qty"] + r.choice([-4, -2, 4, 6, 10])
    rev2[2]["cancelled"] = True
    pos["pemberton"]["rev1"], pos["pemberton"]["lines"] = rev1, rev2
    pos["pemberton"]["rev1_date"] = pos["pemberton"]["date"]
    pos["pemberton"]["date"] = pos["pemberton"]["date"] + timedelta(days=r.randint(3, 6))
    rows = []
    for k in ("pinnacle", "northfield", "westbrook", "pemberton", "silverline"):
        po = pos[k]
        for x in po["lines"]:
            if x.get("cancelled"):
                continue
            rows.append({"po_line_ref": f"{po['no']}-{x['line']}", "customer_id": CID[po["cust"]], "po_number": po["no"],
                         "po_date": po["date"].isoformat(), "line": x["line"], "part_number": x["part"], "description": x["desc"],
                         "quantity": x["qty"], "unit_price": x["unit"], "line_amount": round(x["qty"] * x["unit"], 2), "need_by": x["need"].isoformat()})
    return {"pos": pos, "rows": rows}


def money(x: float) -> str:
    return f"{x:,.2f}"


def westbrook_pdf(path: str, po: dict) -> None:
    """ERP-style two-page PO with a page footer, built directly so the footer can say which page it is."""
    from reportlab import rl_config
    rl_config.invariant = 1
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    st = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=11)
    hd = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15, leading=19)

    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica", 8)
        canvas.drawString(18 * mm, 10 * mm, f"Purchase order {po['no']}  -  page {doc.page}")
        canvas.drawRightString(LETTER[0] - 18 * mm, 10 * mm, "Westbrook Plumbing - Purchasing")
        canvas.restoreState()
    doc = SimpleDocTemplate(path, pagesize=LETTER, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
                            title="", author="", subject="", creator="", producer="")
    total = round(sum(x["qty"] * x["unit"] for x in po["lines"]), 2)
    story = [Paragraph("WESTBROOK PLUMBING", hd), Paragraph("1180 Water St, Tacoma, WA 98402 - purchasing@westbrookplumbing.example", st), Spacer(1, 8),
             Table([[Paragraph(f"<b>Purchase Order</b> {po['no']}<br/>Order date {po['date'].strftime('%m/%d/%Y')}<br/>Buyer: R. Okafor", st),
                     Paragraph("<b>Vendor</b><br/>Ironwood Fabrication<br/>77 Mill Rd, Tacoma, WA 98402", st),
                     Paragraph("<b>Ship to</b><br/>Westbrook Plumbing warehouse<br/>Dock 3, 1180 Water St", st)]], colWidths=[62 * mm, 55 * mm, 55 * mm]),
             Spacer(1, 6), Paragraph("Deliver each line by its need-by date. Partial shipments accepted. Reference the PO number and line on every "
                                     "packing slip. Payment Net 45.", st), Spacer(1, 8)]
    data = [["Ln", "Material", "Description", "Need by", "Qty", "Unit price", "Net value"]]
    for x in po["lines"]:
        data.append([str(x["line"]), x["part"], Paragraph(x["desc"], st), x["need"].strftime("%m/%d/%Y"), str(x["qty"]), money(x["unit"]),
                     money(x["qty"] * x["unit"])])
    data.append(["", "", Paragraph("<b>Total net value USD</b>", st), "", "", "", money(total)])
    t = Table(data, colWidths=[12 * mm, 26 * mm, 62 * mm, 20 * mm, 12 * mm, 20 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
                           ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black), ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f2f2f2")]),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("ALIGN", (4, 0), (-1, -1), "RIGHT")]))
    story.append(t)
    story += [Spacer(1, 10), Paragraph("Terms: this order is subject to Westbrook Plumbing standard purchase terms. Certifications of galvanizing "
                                       "required with the first shipment.", st)]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def pemberton_pdf(path: str, po: dict, rev: int) -> None:
    ls = po["rev1"] if rev == 1 else po["lines"]
    d = po["rev1_date"] if rev == 1 else po["date"]
    rows = [["#", "Qty", "Part #", "Description", "Ext. price", "Unit price"]]
    for x in ls:
        cells = [str(x["line"]), str(x["qty"]), x["part"], x["desc"], money(x["qty"] * x["unit"]), money(x["unit"])]
        if x.get("cancelled"):
            cells = [f"<strike>{c}</strike>" for c in cells]
            cells[3] += f" CANCELLED {d.strftime('%m/%d')}"
        rows.append(cells)
    live = [x for x in ls if not x.get("cancelled")]
    total = round(sum(x["qty"] * x["unit"] for x in live), 2)
    blocks = [("title", "PEMBERTON HVAC"), ("small", "Mechanical contractors - 402 Ridge Rd, Omaha NE 68102"), ("hr", None),
              ("kv", [("PO number", po["no"]), ("Revision", f"{rev}" + ("" if rev == 1 else " - supersedes revision 1")),
                      ("Issued", d.strftime("%B %-d, %Y")), ("Required on site", po["need_by"].strftime("%B %-d, %Y")),
                      ("Supplier", "Ironwood Fabrication")]), ("spacer", 8),
              ("table", rows, {"col_widths": [20, 35, 75, 200, 70, 70], "grid": True}), ("spacer", 6), ("right", f"PO total: ${money(total)}")]
    if rev == 2:
        blocks.append(("small", "Revision 2: quantity changed on line 2; line 3 cancelled by the site foreman. Build to this revision."))
    write_pdf_document(path, blocks, pagesize="letter", font="Times", base_size=10)


def render(ws: str, d: dict, seed: int) -> None:
    P = os.path.join(ws, "customer_pos")
    os.makedirs(P, exist_ok=True)
    pos = d["pos"]
    a = pos["pinnacle"]
    write_pdf_document(os.path.join(P, f"PO {a['no']}.pdf"), [
        ("title", "Purchase Order"), ("p", "<b>Pinnacle Roofing, Inc.</b><br/>55 Prospect Ave, Boise, ID 83702"), ("spacer", 6),
        ("kv", [("PO No.", a["no"]), ("PO Date", a["date"].strftime("%m/%d/%Y")), ("Vendor", "Ironwood Fabrication"),
                ("Deliver by", a["need_by"].strftime("%m/%d/%Y")), ("Terms", "Net 30")]), ("spacer", 8),
        ("table", [["Line", "Part No.", "Description", "Qty", "Unit Price", "Extended"]] +
         [[x["line"], x["part"], x["desc"], x["qty"], f"${money(x['unit'])}", f"${money(x['qty'] * x['unit'])}"] for x in a["lines"]],
         {"col_widths": [34, 84, 190, 40, 70, 80], "shade_header": True}), ("spacer", 6),
        ("right", f"<b>Order total ${money(sum(x['qty'] * x['unit'] for x in a['lines']))}</b>"),
        ("small", "Please confirm receipt of this order within 2 business days.")], pagesize="letter", font="Helvetica", base_size=10)
    b = pos["northfield"]
    write_pdf_document(os.path.join(P, f"Northfield_order_{b['no']}.pdf"), [
        ("right", f"ORDER {b['no']}<br/>{b['date'].strftime('%-d %b %Y')}"), ("h", "Northfield Auto Body"),
        ("p", "22 Elm Dr, Madison WI 53703 - parts@northfieldauto.example"), ("hr", None),
        ("p", f"To: Ironwood Fabrication. Please supply the following. Required: {b['need_by'].strftime('%-d %b %Y')}."), ("spacer", 6),
        ("table", [["Item", "Part", "Description", "Qty", "UOM", "Amount"]] +
         [[x["line"], x["part"], x["desc"], x["qty"], "EA", money(x["qty"] * x["unit"])] for x in b["lines"]],
         {"col_widths": [36, 72, 190, 36, 42, 80], "grid": True}), ("spacer", 6),
        ("kv", [("Order value", money(sum(x["qty"] * x["unit"] for x in b["lines"]))), ("Authorised", "D. Kowalski, shop manager")])],
        pagesize="a4", font="Times", base_size=10)
    westbrook_pdf(os.path.join(P, f"WPL_PO_{pos['westbrook']['no']}.pdf"), pos["westbrook"])
    e = pos["pemberton"]
    pemberton_pdf(os.path.join(P, f"Pemberton PO {e['no']}.pdf"), e, rev=1)
    pemberton_pdf(os.path.join(P, f"Pemberton PO {e['no']} (1).pdf"), e, rev=2)
    s = pos["silverline"]
    write_scan_pdf(os.path.join(P, f"fax_{s['date'].strftime('%Y%m%d')}_0932.pdf"), [
        "SILVERLINE LOGISTICS", "FAX TO: IRONWOOD FABRICATION", "", "PURCHASE ORDER", f"PO NUMBER: {s['no']}", f"PO DATE: {s['date'].strftime('%m/%d/%Y')}",
        f"SHIP BY: {s['need_by'].strftime('%m/%d/%Y')}", "", "LINE PART NUMBER  QTY  EACH  TOTAL"]
        + [f"{x['line']}  {x['part']}  {x['qty']}  {x['unit']:.2f}  {x['qty'] * x['unit']:.2f}" for x in s["lines"]]
        + ["", "DESCRIPTIONS"] + [f"{x['line']}  {x['desc'].upper()}" for x in s["lines"]]
        + ["", f"ORDER TOTAL: {sum(x['qty'] * x['unit'] for x in s['lines']):.2f}", "APPROVED BY M. OSEI"],
        font_size=30, seed=seed + 5, skew_deg=0.4, noise=400)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    render(ws, d, seed)
    write_csv(os.path.join(ws, "customer_list.csv"), ["customer_id", "customer_name", "terms"], [[i, n, "Net 30"] for i, n in sorted(CUSTOMERS)])
    write_csv(os.path.join(ws, "order_entry_template.csv"), HEADER, [])
    write_text(os.path.join(ws, "note_from_carla.txt"),
               "Order entry from customer POs\n\n"
               "Everything that came in this week is in customer_pos. The order system imports the template, one row per PO line:\n\n"
               "  po_line_ref   the PO number, a hyphen, and the line number exactly as the PO prints it\n"
               "  customer_id   from customer_list.csv\n"
               "  po_number     as printed\n"
               "  po_date       the date on the PO, YYYY-MM-DD\n"
               "  line          the customer's line number as printed\n"
               "  part_number   our part number (IF-...)\n"
               "  description   as printed\n"
               "  quantity      pieces\n"
               "  unit_price    price per piece\n"
               "  line_amount   quantity x unit price\n"
               "  need_by       when the customer needs that line, YYYY-MM-DD\n\n"
               "Customers send changes as a new revision of the same PO number - we build to the latest revision only, and its "
               "PO date is the date of that revision. A line that is struck out or marked cancelled is not ordered; leave it out and "
               "keep the other line numbers as they are.\n\n- Carla\n")
    rows = [[x[h] if not isinstance(x[h], float) else f"{x[h]:.2f}" for h in HEADER] for x in d["rows"]]
    write_csv(os.path.join(ref, "po_lines.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "po_lines.csv"), HEADER, rows)
    pos = d["pos"]
    refs = lambda k: [f"{pos[k]['no']}-{x['line']}" for x in pos[k]["lines"] if not x.get("cancelled")]
    e = pos["pemberton"]
    write_json(os.path.join(ref, "notes.json"), {"cancelled_line": f"{e['no']}-3", "rev1_qty_line2": e["rev1"][1]["qty"],
                                                  "westbrook_lines": len(pos["westbrook"]["lines"])})
    P = "po_lines.csv"
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    write_task_yaml(HERE, {
        "id": "purchase-orders-pdf", "track": "desk", "category": "extraction",
        "title": "Key this week's customer POs into order entry",
        "ask": ("Please get this week's customer purchase orders into the order entry template so we can import them. Carla's note has the "
                "details. Save it as po_lines.csv.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            f"Westbrook Plumbing's PO {pos['westbrook']['no']} has {len(pos['westbrook']['lines'])} lines running onto a second page with the "
            "column header repeated, lines numbered 10, 20, 30 and a different need-by date on each line "
            "(checks: one row per PO line; row count; need-by dates)",
            "Northfield Auto Body prints only the extended amount per line under the heading Amount, so reading it as the unit price "
            "overstates every line; the unit price is amount divided by quantity (check: quantities and unit prices)",
            f"Pemberton HVAC's PO {e['no']} arrived twice: revision 1 and, in the file with (1) in its name, revision 2, which changes the "
            "quantity on line 2, strikes through line 3 marked CANCELLED and carries a later PO date "
            "(checks: one row per PO line; quantities and unit prices; line amounts; PO header fields)",
            "Pemberton prints the extended price before the unit price, so column position is not a safe guide (check: line amounts)",
            f"the Silverline Logistics PO {pos['silverline']['no']} is a faxed image with the descriptions listed apart from the price lines "
            "(checks: one row per PO line; part numbers and descriptions)",
            "customer names print as Pinnacle Roofing, Inc. and similar and map to ids in the customer list; PO dates come in four formats "
            "(check: PO header fields)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per PO line", "path": P, "column": "po_line_ref", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "PO header fields", "path": P, "ref": P, "key": "po_line_ref",
             "columns": ["customer_id", "po_number", "po_date", "line"], "min_accuracy": 1.0, "must_match_keys": refs("pemberton")},
            {"type": "csv_values_match", "name": "part numbers and descriptions", "path": P, "ref": P, "key": "po_line_ref",
             "columns": ["part_number", "description"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": refs("silverline")},
            {"type": "csv_values_match", "name": "quantities and unit prices", "path": P, "ref": P, "key": "po_line_ref",
             "columns": ["quantity", "unit_price"], "must_match_keys": refs("northfield") + refs("pemberton"), **num},
            {"type": "csv_values_match", "name": "line amounts", "path": P, "ref": P, "key": "po_line_ref", "columns": ["line_amount"],
             "must_match_keys": refs("pemberton"), **num},
            {"type": "csv_values_match", "name": "need-by dates", "path": P, "ref": P, "key": "po_line_ref", "columns": ["need_by"],
             "min_accuracy": 1.0, "must_match_keys": refs("westbrook")},
        ],
    })
    print(f"seed={seed} rows={len(rows)} pos=" + ", ".join(f"{k}:{v['no']}" for k, v in pos.items()))


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: first page of every PDF only (Westbrook stops where page 1 ends), every file read (both
    Pemberton revisions, struck line included), the Northfield Amount column taken as the unit price."""
    os.makedirs(out, exist_ok=True)
    pos = d["pos"]; rows = []
    for k in ("pinnacle", "northfield", "westbrook", "pemberton", "silverline"):
        po = pos[k]
        groups = [po["rev1"], po["lines"]] if k == "pemberton" else [po["lines"]]
        for ls in groups:
            for x in (ls[:32] if k == "westbrook" else ls):
                unit = round(x["qty"] * x["unit"], 2) if k == "northfield" else x["unit"]
                rows.append([f"{po['no']}-{x['line']}", CID[po["cust"]], po["no"], po["date"].isoformat(), x["line"], x["part"], x["desc"],
                             x["qty"], unit, round(x["qty"] * unit, 2), x["need"].isoformat()])
    write_csv(os.path.join(out, "po_lines.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
