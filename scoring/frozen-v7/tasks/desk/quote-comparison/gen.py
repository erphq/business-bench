#!/usr/bin/env python3
"""Generator for desk/quote-comparison.

Writes workspace/ (three vendor quote PDFs + notes.txt), reference/ (totals.csv,
breakdown.csv) and reference_solution/ (comparison.xlsx, recommendation.md).

Deterministic: same --seed -> byte-identical output (reportlab invariant mode:
fixed creation date, no random document id). Other seeds re-roll names, quote
numbers and prices but keep the trap structure:

  * Northstar  (USD)  line-item table, freight line, 3% early-payment discount in
                      the terms text, 24-month depot warranty. Cheapest delivered.
  * Kestrel    (EUR)  quantity-break price list where the 40+ tier applies, no
                      extended total printed, shipping included, 12-month warranty.
                      Looks cheapest if the EUR figure is not converted at 1.08;
                      is actually the most expensive once converted.
  * Bluepine   (USD)  lowest unit price, but a mandatory one-time onboarding fee and
                      freight are listed under "Additional charges" with no grand
                      total printed; 36-month on-site warranty; 8-week lead time.
                      Looks cheapest if the fee is ignored; second once included.

Ordering invariants enforced for every seed:
  Northstar < Bluepine < Kestrel (delivered USD)
  Bluepine without setup fee < Northstar            (setup-fee trap flips ranking)
  Kestrel EUR figure (unconverted) < Northstar      (FX trap flips ranking)
  Northstar with the 3% discount is still cheapest  (discount does not change ranking)
"""
from __future__ import annotations
import argparse, csv, os, random, re, zipfile
from datetime import date, datetime, timedelta

from reportlab import rl_config
rl_config.invariant = 1  # stable bytes: fixed timestamps, no random /ID

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
QTY = 40
FX = 1.08

BUYERS = [("Larkspur Analytics", "Dana Whitfield", "1450 Harrison St, Suite 300, San Francisco, CA 94103"),
          ("Northgate Robotics", "Marcus Oyelaran", "88 Colin P Kelly Jr St, San Francisco, CA 94107"),
          ("Fernwood Studio", "Priya Raghavan", "2201 Broadway, Oakland, CA 94612"),
          ("Copperline Labs", "Tomas Lindqvist", "600 Congress Ave, Austin, TX 78701"),
          ("Halcyon Freight Software", "Elena Moreau", "1201 3rd Ave, Seattle, WA 98101")]
NS_REPS = ["Jordan Feld", "Alicia Brandt", "Noah Petrakis", "Simone Achterberg"]
KS_REPS = ["Katrin Vogel", "Lukas Brenner", "Anja Steinmetz", "Felix Hartmann"]
BP_REPS = ["Chris Okonkwo", "Maya Lindstrom", "Devin Park", "Sofia Ramirez"]


def usd(x: float) -> str:
    return f"${x:,.2f}"


def eur_de(x: float) -> str:
    s = f"{x:,.2f}"  # 1,205.00
    return "EUR " + s.replace(",", "X").replace(".", ",").replace("X", ".")  # EUR 1.205,00


def normalize_zip(path: str):
    """Rewrite an xlsx zip with fixed entry timestamps so bytes are reproducible."""
    with zipfile.ZipFile(path) as zin:
        items = [(i.filename, zin.read(i.filename)) for i in zin.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items:
            if name == "docProps/core.xml":  # openpyxl re-stamps modified at save time
                data = re.sub(rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>",
                              b'<dcterms:modified xsi:type="dcterms:W3CDTF">2026-07-01T00:00:00Z</dcterms:modified>', data)
            zi = zipfile.ZipInfo(name, date_time=(2026, 7, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zout.writestr(zi, data)


def pick_numbers(rng: random.Random) -> dict:
    while True:
        u_n = rng.randrange(1215, 1281, 5)
        f_n = rng.randrange(560, 701, 5)
        n_total = QTY * u_n + f_n
        u_b = u_n - rng.randrange(45, 76, 5)
        s_b = rng.randrange(2700, 3301, 50)
        f_b = rng.randrange(980, 1201, 10)
        b_total = QTY * u_b + s_b + f_b
        t40 = rng.randrange(1170, 1261)
        k_eur = QTY * t40
        k_usd = round(k_eur * FX, 2)
        ok = (1.015 * n_total <= b_total <= 1.03 * n_total
              and QTY * u_b + f_b < n_total
              and 1.028 * n_total <= k_usd <= 1.05 * n_total
              and k_usd >= 1.011 * b_total
              and k_eur < n_total
              and 0.97 * QTY * u_n + f_n < b_total)
        if ok:
            break
    t20 = t40 + rng.randrange(40, 56)
    t1 = t20 + rng.randrange(45, 61)
    return dict(u_n=u_n, f_n=f_n, n_total=n_total, disc_n=round(0.03 * QTY * u_n, 2),
                u_b=u_b, s_b=s_b, f_b=f_b, b_total=b_total,
                t1=t1, t20=t20, t40=t40, k_eur=k_eur, k_usd=k_usd)


# ---------------------------------------------------------------- Northstar (USD)
def pdf_northstar(path: str, ctx: dict, num: dict):
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8.5, leading=11, textColor=colors.HexColor("#333333"))
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=0)
    right = ParagraphStyle("r", parent=body, alignment=TA_RIGHT)
    doc = SimpleDocTemplate(path, pagesize=LETTER, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="Northstar Quotation", author="Northstar Technology Partners")
    el = []
    head = Table([[Paragraph("<b>NORTHSTAR TECHNOLOGY PARTNERS</b><br/>2200 Bridgepointe Pkwy, Suite 120<br/>"
                             "San Mateo, CA 94404 · (650) 555-0142 · quotes@northstar-tp.example", body),
                   Paragraph(f"<b>QUOTATION</b><br/>Quote no. {ctx['ns_no']}<br/>Date: {ctx['date'].strftime('%B %d, %Y')}"
                             f"<br/>Valid through: {(ctx['date'] + timedelta(days=30)).strftime('%B %d, %Y')}", right)]],
                 colWidths=[100 * mm, 70 * mm])
    el += [head, Spacer(1, 6), HRFlowable(width="100%", thickness=1, color=colors.black), Spacer(1, 8)]
    el.append(Table([[Paragraph(f"<b>Bill to</b><br/>{ctx['buyer']}<br/>Attn: {ctx['contact']}<br/>{ctx['addr']}", body),
                      Paragraph(f"<b>Ship to</b><br/>{ctx['buyer']}<br/>{ctx['addr']}<br/>Dock delivery, liftgate not required", body),
                      Paragraph(f"<b>Your rep</b><br/>{ctx['ns_rep']}<br/>Payment terms: Net 30<br/>Currency: USD", body)]],
                    colWidths=[60 * mm, 60 * mm, 50 * mm]))
    el.append(Spacer(1, 12))
    rows = [["#", "Part", "Description", "Qty", "Unit price", "Extended"],
            ["1", "NS-LT14P", Paragraph("Lattice 14 Pro business laptop — Intel Core Ultra 7, 32 GB RAM, "
                                        "1 TB NVMe SSD, 14\" 2.8K display, Windows 11 Pro, US keyboard", small),
             str(QTY), usd(num["u_n"]), usd(QTY * num["u_n"])],
            ["2", "NS-DOCK-C", Paragraph("USB-C travel dock, 65 W — included at no charge with each unit", small),
             str(QTY), usd(0), usd(0)],
            ["", "", "", "", "Subtotal", usd(QTY * num["u_n"])],
            ["", "", "", "", "Freight (ground, insured, delivered)", usd(num["f_n"])],
            ["", "", "", "", "TOTAL (USD)", usd(num["n_total"])]]
    t = Table(rows, colWidths=[8 * mm, 22 * mm, 78 * mm, 12 * mm, 30 * mm, 24 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF5")),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9), ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 2), (-1, 2), 0.4, colors.grey), ("FONT", (4, -1), (-1, -1), "Helvetica-Bold", 9.5),
        ("LINEABOVE", (4, -1), (-1, -1), 0.8, colors.black), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el += [t, Spacer(1, 14), Paragraph("<b>Terms and conditions</b>", body), Spacer(1, 3)]
    terms = [
        "Payment terms: Net 30 from invoice date. A 3% early-payment discount on the equipment subtotal "
        "applies if the invoice is paid in full within 10 days.",
        "Warranty: 24 months manufacturer depot warranty on all units (return-to-depot; Northstar covers "
        "inbound freight on warranty repairs). Extended coverage available on request.",
        "Delivery: ships within 10 business days of PO receipt from our Reno, NV distribution center. "
        "Freight quoted above is for one consolidated shipment to the ship-to address.",
        "Prices are in US dollars, exclusive of applicable sales tax. This quotation is valid for 30 days.",
    ]
    for s_ in terms:
        el.append(Paragraph("• " + s_, small))
    el += [Spacer(1, 16), Paragraph(f"Prepared by {ctx['ns_rep']}, Account Executive · Northstar Technology Partners", small)]
    doc.build(el)


# ---------------------------------------------------------------- Kestrel GmbH (EUR)
def pdf_kestrel(path: str, ctx: dict, num: dict):
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontName="Times-Roman", fontSize=10, leading=13.5)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor("#444444"))
    title = ParagraphStyle("t", parent=body, fontName="Times-Bold", fontSize=16, leading=20)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            title="Angebot / Quotation", author="Kestrel Systems GmbH")
    el = []
    el.append(Paragraph("Kestrel Systems GmbH", title))
    el.append(Paragraph("Spaldingstraße 77 · 20097 Hamburg · Deutschland · Tel. +49 40 5550 1180 · vertrieb@kestrel-systems.example", small))
    el += [Spacer(1, 4), HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#888888")), Spacer(1, 10)]
    meta = Table([[Paragraph(f"<b>An / To</b><br/>{ctx['buyer']}<br/>{ctx['contact']}<br/>{ctx['addr']}<br/>USA", body),
                   Paragraph(f"<b>Angebot / Quotation</b><br/>Nr. / No.: {ctx['ks_no']}<br/>"
                             f"Datum / Date: {ctx['date'].strftime('%d.%m.%Y')}<br/>"
                             f"Gültig bis / Valid until: {(ctx['date'] + timedelta(days=30)).strftime('%d.%m.%Y')}<br/>"
                             f"Ihr Ansprechpartner / Your contact: {ctx['ks_rep']}", body)]],
                 colWidths=[85 * mm, 81 * mm])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [meta, Spacer(1, 12)]
    el.append(Paragraph("Sehr geehrte Damen und Herren, / Dear Sir or Madam,", body))
    el.append(Spacer(1, 4))
    el.append(Paragraph("vielen Dank für Ihre Anfrage. Gerne unterbreiten wir Ihnen folgendes Angebot. / "
                        "Thank you for your enquiry. We are pleased to submit the following offer.", body))
    el.append(Spacer(1, 10))
    el.append(Paragraph("<b>Position 1 — Falke Book 14</b>", body))
    el.append(Paragraph("Business-Notebook, Intel Core Ultra 7, 32 GB RAM, 1 TB SSD, 14\" WQXGA, Windows 11 Pro, "
                        "Tastatur EN-US / Business notebook, Intel Core Ultra 7, 32 GB RAM, 1 TB SSD, 14\" WQXGA, "
                        "Windows 11 Pro, EN-US keyboard. Art.-Nr. FB14-U7-32-1T", body))
    el.append(Spacer(1, 8))
    tiers = [["Menge / Quantity", "Stückpreis netto / Unit price (net)"],
             ["1 – 19 Stück / units", eur_de(num["t1"])],
             ["20 – 39 Stück / units", eur_de(num["t20"])],
             ["ab 40 Stück / 40+ units", eur_de(num["t40"])]]
    t = Table(tiers, colWidths=[80 * mm, 70 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Times-Bold", 10), ("FONT", (0, 1), (-1, -1), "Times-Roman", 10),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F2F2")), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    el += [t, Spacer(1, 6)]
    el.append(Paragraph(f"Angefragte Menge / Requested quantity: <b>{QTY} Stück / units</b>. "
                        "Der Staffelpreis gilt je Bestellung. / The tier price applies per order.", body))
    el.append(Spacer(1, 12))
    el.append(Paragraph("<b>Konditionen / Conditions</b>", body))
    cond = [["Versand / Shipping", "inklusive / included — DAP (Incoterms 2020), Lieferung an Ihre US-Adresse / delivered to your US address"],
            ["Lieferzeit / Lead time", "3 – 4 Wochen ab Bestellung / 3 – 4 weeks from order"],
            ["Zahlung / Payment", "30 Tage netto / net 30 days, Banküberweisung / bank transfer"],
            ["Gewährleistung / Warranty", "12 Monate / 12 months, Bring-in (Einsendung an Kestrel Hamburg / return to Kestrel Hamburg)"],
            ["Währung / Currency", "Alle Preise in EUR, netto. Exportlieferung außerhalb der EU – es wird keine Umsatzsteuer berechnet. / "
                                   "All prices in EUR, net. Export delivery outside the EU – no VAT is charged."]]
    ct = Table([[Paragraph(a, body), Paragraph(b, body)] for a, b in cond], colWidths=[48 * mm, 118 * mm])
    ct.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el += [ct, Spacer(1, 14)]
    el.append(Paragraph("Mit freundlichen Grüßen / Kind regards,<br/>" + ctx["ks_rep"] + "<br/>Kestrel Systems GmbH – Vertrieb Export", body))
    el += [Spacer(1, 18), HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#AAAAAA")), Spacer(1, 3)]
    el.append(Paragraph("Kestrel Systems GmbH · Sitz Hamburg · Amtsgericht Hamburg HRB 148 233 · Geschäftsführer: Dr. Henrik Faber · "
                        "USt-IdNr. DE 311 908 442 · Es gelten unsere Allgemeinen Geschäftsbedingungen.", small))
    doc.build(el)


# ---------------------------------------------------------------- Bluepine (USD)
def pdf_bluepine(path: str, ctx: dict, num: dict):
    ss = getSampleStyleSheet()
    teal = colors.HexColor("#1F6F78")
    body = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14)
    small = ParagraphStyle("s", parent=body, fontSize=8.5, leading=11.5, textColor=colors.HexColor("#3A3A3A"))
    white = ParagraphStyle("w", parent=body, textColor=colors.white, fontName="Helvetica-Bold", fontSize=20, leading=24)
    whites = ParagraphStyle("ws", parent=body, textColor=colors.white, fontSize=9.5, leading=12, alignment=TA_RIGHT)
    sec = ParagraphStyle("sec", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=teal, spaceBefore=10)
    doc = SimpleDocTemplate(path, pagesize=LETTER, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm,
                            title="Bluepine Quote", author="Bluepine Computing")
    el = []
    band = Table([[Paragraph("bluepine", white),
                   Paragraph(f"Quote {ctx['bp_no']}<br/>{ctx['date'].strftime('%b %d, %Y')} · valid 45 days<br/>"
                             f"Rep: {ctx['bp_rep']} · sales@bluepine.example", whites)]],
                 colWidths=[90 * mm, 84 * mm])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), teal), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                              ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12)]))
    el += [band, Spacer(1, 12)]
    el.append(Paragraph(f"<b>Prepared for</b> {ctx['contact']}, {ctx['buyer']} · {ctx['addr']}", body))
    el.append(Paragraph("Bluepine Computing · 4100 Lakeside Dr, Richmond, CA 94806", small))
    el.append(Paragraph("Pricing summary", sec))
    ps = [["Configuration", Paragraph("Ridge 14 — Intel Core Ultra 7, 32 GB RAM, 1 TB NVMe, 14\" 2.8K, Windows 11 Pro, "
                                      "3-year on-site warranty included", small)],
          ["Unit price", usd(num["u_b"])],
          ["Quantity", str(QTY)],
          ["Equipment subtotal", usd(QTY * num["u_b"])]]
    pt = Table(ps, colWidths=[48 * mm, 126 * mm])
    pt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, teal), ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#BBD3D6")),
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF3F4")), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9.5),
                            ("FONT", (1, 1), (1, -1), "Helvetica", 10), ("FONT", (1, -1), (1, -1), "Helvetica-Bold", 11),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    el.append(pt)
    el.append(Paragraph("Additional charges", sec))
    ac = [[Paragraph("Onboarding &amp; imaging fee — one-time; required for all new accounts (asset tagging, "
                     "image load, MDM enrollment)", small), usd(num["s_b"])],
          [Paragraph("Freight — LTL, insured, delivered to your dock (one shipment)", small), usd(num["f_b"])]]
    at = Table(ac, colWidths=[140 * mm, 34 * mm])
    at.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#BBD3D6")), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("FONT", (1, 0), (1, -1), "Helvetica", 10),
                            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    el.append(at)
    el.append(Paragraph("Service and support", sec))
    for s_ in ["Warranty: 36 months, on-site next-business-day repair by a Bluepine technician. Accidental damage excluded.",
               "Lead time: 8 weeks from PO — Ridge units are built to order in our Richmond facility.",
               "Dedicated onboarding specialist for the first 90 days. Phone and chat support, 6am–6pm Pacific."]:
        el.append(Paragraph("• " + s_, body))
    el.append(Paragraph("Terms", sec))
    el.append(Paragraph("Prices in USD, exclusive of sales tax. Payment: 50% with PO, balance Net 15 after delivery. "
                        "This quote is valid for 45 days from the date above.", small))
    doc.build(el)


def write_reference_solution(sol: str, num: dict, use_formulas: bool = False):
    """Literal values by default. --formulas emits live formulas instead; the shipped
    bench/grade.py cannot see recalculated values (its *.xlsx glob misses the
    upper-cased file the `formulas` engine writes), so literals keep the reference
    solution gradable until that is fixed."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    wb.properties.created = datetime(2026, 7, 1); wb.properties.modified = datetime(2026, 7, 1)
    wb.properties.creator = "reference"; wb.properties.lastModifiedBy = "reference"
    ws = wb.active
    ws.title = "Comparison"
    hdr = ["Vendor", "Currency", "Unit price (quote ccy)", "Qty", "Equipment subtotal (quote ccy)",
           "Setup fee (quote ccy)", "Freight (quote ccy)", "Quote total (quote ccy)", "FX to USD",
           "Delivered total (USD)", "Warranty (months)", "Warranty type", "Lead time", "Notes"]
    ws.append(hdr)
    for c in ws[1]:
        c.font = Font(bold=True)
    data = [
        ("Northstar Technology Partners", "USD", num["u_n"], QTY, 0, num["f_n"], 1.0, 24, "Depot (return-to-depot)", "10 business days",
         f"3% early-payment discount ({usd(num['disc_n'])}) only if paid within 10 days; not applied."),
        ("Kestrel Systems GmbH", "EUR", num["t40"], QTY, 0, 0, FX, 12, "Bring-in (return to Hamburg)", "3-4 weeks",
         "40+ tier applies (EUR 1.205,00-style pricing); shipping included (DAP); converted at 1.08."),
        ("Bluepine Computing", "USD", num["u_b"], QTY, num["s_b"], num["f_b"], 1.0, 36, "On-site next-business-day", "8 weeks",
         "Mandatory one-time onboarding & imaging fee plus freight; no grand total printed on the quote."),
    ]
    usd_totals = []
    for i, (v, ccy, unit, qty, setup, freight, fx, wm, wt, lead, note) in enumerate(data, start=2):
        sub = unit * qty
        tot = sub + setup + freight
        usd_totals.append(round(tot * fx, 2))
        if use_formulas:
            ws.append([v, ccy, unit, qty, f"=C{i}*D{i}", setup, freight, f"=E{i}+F{i}+G{i}", fx, f"=H{i}*I{i}", wm, wt, lead, note])
        else:
            ws.append([v, ccy, unit, qty, sub, setup, freight, tot, fx, round(tot * fx, 2), wm, wt, lead, note])
    ws.append([])
    ws.append(["Cheapest delivered (USD)", None, None, None, None, None, None, None, None,
               "=MIN(J2:J4)" if use_formulas else min(usd_totals)])
    ws.append(["Recommended", "Bluepine Computing"])
    for col_, w in zip("ABCDEFGHIJKLMN", (30, 9, 20, 6, 26, 20, 18, 22, 10, 22, 16, 26, 16, 70)):
        ws.column_dimensions[col_].width = w
    wb.save(os.path.join(sol, "comparison.xlsx")); normalize_zip(os.path.join(sol, "comparison.xlsx"))

    n, b, k = num["n_total"], num["b_total"], num["k_usd"]
    md = f"""# Laptop quote comparison — 40 units, delivered

| Vendor | Delivered total (USD) | Warranty | Lead time |
|---|---|---|---|
| Northstar Technology Partners | {usd(n)} | 24 months, depot | ~2 weeks |
| Bluepine Computing | {usd(b)} | 36 months, on-site next-business-day | 8 weeks |
| Kestrel Systems GmbH | {usd(k)} (EUR {num['k_eur']:,.2f} at 1.08) | 12 months, bring-in to Hamburg | 3-4 weeks |

## Recommendation: Bluepine

Pick Bluepine. It is {usd(b - n)} ({(b - n) / n * 100:.1f}%) more than the cheapest delivered price
(Northstar) but carries a 36-month on-site warranty versus Northstar's 24-month return-to-depot
coverage and Kestrel's 12 months. Given that warranty is the priority, that premium buys the
strongest coverage of the three by a wide margin. The one caveat is lead time: Bluepine builds to
order and quotes 8 weeks, so if the machines are needed sooner, Northstar (ships in about 10
business days) is the fallback.

## What changes the picture if you misread the quotes

- Kestrel looks cheapest on paper (EUR {num['k_eur']:,.2f}) but is the most expensive once converted
  at 1.08, and it has the weakest warranty. It does apply the 40+ tier price of EUR {num['t40']:,.2f}
  (not the 1-19 or 20-39 tier), and shipping is included.
- Bluepine's unit price is the lowest, but the mandatory one-time onboarding fee ({usd(num['s_b'])})
  and freight ({usd(num['f_b'])}) are listed separately without a grand total; they are part of the
  delivered cost.
- Northstar's 3% early-payment discount ({usd(num['disc_n'])}) applies only if paid within 10 days.
  Even if taken, Northstar stays cheapest and the ranking does not change.
"""
    with open(os.path.join(sol, "recommendation.md"), "w") as f:
        f.write(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--formulas", action="store_true",
                    help="write live formulas into reference_solution/comparison.xlsx instead of literal values")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    num = pick_numbers(rng)
    buyer, contact, addr = BUYERS[args.seed % len(BUYERS)]
    ctx = dict(buyer=buyer, contact=contact, addr=addr,
               date=date(2026, 9, 1) + timedelta(days=rng.randint(0, 9)),
               ns_no=f"NS-Q-{26000 + rng.randint(100, 899)}", ks_no=f"KS-2026-{rng.randint(1000, 4999)}",
               bp_no=f"#BP-{rng.randint(10000, 19999)}",
               ns_rep=rng.choice(NS_REPS), ks_rep=rng.choice(KS_REPS), bp_rep=rng.choice(BP_REPS))

    ws = os.path.join(HERE, "workspace")
    ref = os.path.join(HERE, "reference")
    sol = os.path.join(HERE, "reference_solution")
    for d in (ws, ref, sol):
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))

    pdf_northstar(os.path.join(ws, "quote_northstar.pdf"), ctx, num)
    pdf_kestrel(os.path.join(ws, "quote_kestrel_gmbh.pdf"), ctx, num)
    pdf_bluepine(os.path.join(ws, "quote_bluepine.pdf"), ctx, num)
    with open(os.path.join(ws, "notes.txt"), "w") as f:
        f.write("We need 40 laptops minimum, delivered. Convert EUR at 1.08. Warranty matters, we got burned last time.\n")

    with open(os.path.join(ref, "totals.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vendor", "total_usd"])
        w.writerow(["Northstar", f"{num['n_total']:.2f}"])
        w.writerow(["Kestrel GmbH", f"{num['k_usd']:.2f}"])
        w.writerow(["Bluepine", f"{num['b_total']:.2f}"])
    with open(os.path.join(ref, "breakdown.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["vendor", "currency", "unit_price", "qty", "equipment_subtotal", "setup_fee", "freight",
                    "quote_total", "fx", "delivered_total_usd", "warranty_months", "lead_time", "trap_value_if_misread"])
        w.writerow(["Northstar", "USD", num["u_n"], QTY, QTY * num["u_n"], 0, num["f_n"], num["n_total"], 1.0,
                    f"{num['n_total']:.2f}", 24, "10 business days", f"discounted={num['n_total'] - num['disc_n']:.2f}"])
        w.writerow(["Kestrel GmbH", "EUR", num["t40"], QTY, num["k_eur"], 0, 0, num["k_eur"], FX,
                    f"{num['k_usd']:.2f}", 12, "3-4 weeks",
                    f"unconverted={num['k_eur']:.2f}; tier20={QTY * num['t20'] * FX:.2f}; tier1={QTY * num['t1'] * FX:.2f}"])
        w.writerow(["Bluepine", "USD", num["u_b"], QTY, QTY * num["u_b"], num["s_b"], num["f_b"], num["b_total"], 1.0,
                    f"{num['b_total']:.2f}", 36, "8 weeks", f"no_setup_fee={QTY * num['u_b'] + num['f_b']:.2f}"])
    write_reference_solution(sol, num, use_formulas=args.formulas)

    print(f"seed={args.seed} Northstar={num['n_total']:.2f} Bluepine={num['b_total']:.2f} Kestrel={num['k_usd']:.2f} "
          f"(EUR {num['k_eur']:.2f}; tiers {num['t1']}/{num['t20']}/{num['t40']}); "
          f"Bluepine w/o setup={QTY * num['u_b'] + num['f_b']:.2f}; Northstar discounted={num['n_total'] - num['disc_n']:.2f}")
    print("task.yaml expected values are pinned to seed 0; update them if you re-roll the seed.")


if __name__ == "__main__":
    main()
