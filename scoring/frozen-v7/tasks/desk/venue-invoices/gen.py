#!/usr/bin/env python3
"""venue-invoices: five venue invoices (one re-issued, one scanned) for September events -> one line-item file.

    python gen.py [--seed N] [--naive DIR]

Business: Sable & Sage Events, a Charleston wedding and event planner, keys every venue invoice into its job-cost
sheet line by line so each client event carries its true venue cost, tax and what is still owed.

Traps (each caught by a check, see task.yaml):
  * deposits already paid are credited four ways: below the totals (Foundry, Old Mill Barn), as an "advance deposit
    applied" line (Harborview) and inside the table in a Credits column printed positive (Magnolia Hall); each is its
    own negative row and the balance due is after it              (checks: one row per invoice line; line types; amounts; balance due)
  * taxes by line: two invoices print a tax amount per line, Magnolia Hall prints only a letter code with the rates in a
    legend, Harborview prints a rate percent, Rosewater prints tax only as category totals under a Type column (check: line tax)
  * Harborview re-issued its invoice after the final guarantee dropped; the superseded original is still in the folder
                                                                    (checks: one row per invoice line; row count)
  * Harborview hosts both the rehearsal dinner and the farewell brunch for the same couple (check: event codes and invoice numbers)
  * the Old Mill Barn invoice is an image-only scan                 (checks: descriptions; balance due)
  * invoice dates are printed in five formats                       (check: invoice dates)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["line_ref", "event_code", "invoice_no", "invoice_date", "line_type", "description", "amount", "tax", "balance_due"]
RATE = {"fb": 0.11, "svc": 0.11, "rent": 0.09, "av": 0.09, "labor": 0.0}
CODE = {"fb": "F", "svc": "F", "rent": "T", "av": "T", "labor": "E"}
TYPE = {"fb": "Food and beverage", "svc": "Service charge", "rent": "Rental", "av": "Rental", "labor": "Labor (exempt)"}


def usd(x: float) -> str:
    return f"${x:,.2f}"


def half_cent(amount: float, rate: float) -> bool:
    c = amount * rate * 100
    return abs((c % 1) - 0.5) < 0.02


def build(seed: int) -> dict:
    r = rng(seed)
    a, b = pick(r, ["Okafor", "Lindqvist", "Haddad", "Mensah", "Tanaka", "Reyes", "Bennett", "Castillo", "Osei", "Morales"], 2)
    couple = f"{a}-{b}"
    fam = r.choice(["Whitaker", "Delgado", "Hampton", "Pryor", "Ashby"])
    corp = r.choice(["Palmetto Health Partners", "Lowcountry Title Group", "Cooper River Credit Union"])
    events = [
        ("EV-2607", f"{couple} rehearsal dinner", date(2026, 9, 18), "Harborview Terrace Hotel"),
        ("EV-2608", f"{couple} wedding", date(2026, 9, 19), "The Foundry at Cooper River"),
        ("EV-2604", f"{couple} farewell brunch", date(2026, 9, 20), "Harborview Terrace Hotel"),
        ("EV-2611", f"{corp} leadership dinner", date(2026, 9, 11), "Magnolia Hall"),
        ("EV-2614", f"{fam} 50th anniversary brunch", date(2026, 9, 13), "Old Mill Barn at Wadmalaw"),
        ("EV-2619", "Tidewater Literacy Council gala", date(2026, 9, 26), "Rosewater Gardens"),
        ("EV-2603", f"{corp} holiday party", date(2026, 12, 11), "Magnolia Hall"),
    ]
    g_wed, g_corp, g_reh, g_reh_orig, g_fam, g_gala = r.randint(128, 156), r.randint(60, 84), r.randint(40, 52), 0, r.randint(70, 95), r.randint(150, 190)
    g_reh_orig = g_reh + r.randint(8, 14)

    def mk(spec):
        out = []
        for desc, qty, unit, cat in spec:
            amt = round(qty * unit, 2)
            out.append({"desc": desc, "qty": qty, "unit": unit, "cat": cat, "amount": amt, "tax": round(amt * RATE[cat] + 1e-9, 2)})
        return out

    def with_svc(spec, pct, label):
        fb = round(sum(q * u for _, q, u, c in spec if c == "fb"), 2)
        return spec + [(label, 1, round(fb * pct, 2), "svc")]

    inv = {}
    spec = [("Venue rental, Saturday evening", 1, float(r.choice([6200, 6500, 6800])), "rent"),
            ("Plated dinner, three courses", g_wed, float(r.choice([84, 86, 88, 92])), "fb"),
            ("Bar package, four hours", g_wed, float(r.choice([36, 38, 42])), "fb")]
    spec = with_svc(spec, 0.22, "Service charge, 22% of food and beverage")
    spec += [("Dance floor and uplighting", 1, float(r.choice([950, 1150, 1275])), "av"),
             ("Event staff hours", r.randint(38, 52), 42.0, "labor")]
    inv["A"] = {"venue": "The Foundry at Cooper River", "no": f"FCR-2026-{r.randint(410, 460):04d}", "date": date(2026, 8, r.randint(21, 26)),
                "event": "EV-2608", "lines": mk(spec), "deposit": float(r.choice([2500, 3000, 3500])), "dep_date": date(2026, 6, r.randint(10, 20))}
    spec = [("Main hall rental, Friday", 1, float(r.choice([3600, 3800, 4100])), "rent"),
            ("Buffet dinner, southern menu", g_corp, float(r.choice([62, 64, 68])), "fb"),
            ("Wine service, per guest", g_corp, float(r.choice([19, 22, 24])), "fb"),
            ("Projector, screen and wireless mics", 1, float(r.choice([420, 480, 525])), "av"),
            ("Coat check attendant", 1, 150.0, "labor"),
            ("Linen upgrade, per table", -(-g_corp // 8), 18.0, "rent")]
    inv["B"] = {"venue": "Magnolia Hall", "no": f"MH-{r.randint(7700, 7899)}", "date": date(2026, 9, r.randint(1, 3)), "event": "EV-2611",
                "lines": mk(spec), "deposit": float(r.choice([1500, 2000])), "dep_date": date(2026, 7, r.randint(1, 9))}
    bev = float(r.randrange(1400, 2100, 5))

    def reh(g, bev_amt):
        s = [("Private dining room, Friday", 1, 1200.0, "rent"), ("Family-style dinner", g, float(72), "fb"),
             ("Beer and wine on consumption", 1, bev_amt, "fb")]
        s = with_svc(s, 0.20, "Service charge 20%")
        return s + [("Audio package", 1, 350.0, "av")]
    no_c = f"HTH-{r.randint(51000, 51999)}"
    dep_c = 1000.0
    inv["C0"] = {"venue": "Harborview Terrace Hotel", "no": no_c, "date": date(2026, 8, r.randint(17, 20)), "event": "EV-2607",
                 "lines": mk(reh(g_reh_orig, float(r.randrange(2200, 2600, 5)))), "deposit": dep_c, "dep_date": date(2026, 7, 15), "guar": g_reh_orig}
    inv["C"] = {"venue": "Harborview Terrace Hotel", "no": f"{no_c}-R1", "date": date(2026, 9, r.randint(7, 9)), "event": "EV-2607",
                "lines": mk(reh(g_reh, bev)), "deposit": dep_c, "dep_date": date(2026, 7, 15), "guar": g_reh}
    spec = [("Barn and grounds rental", 1, float(r.choice([3000, 3200, 3400])), "rent"),
            ("Tables and chairs set", 1, float(r.choice([580, 640, 700])), "rent"),
            ("Farm brunch buffet", g_fam, float(r.choice([36, 38, 41])), "fb"),
            ("Lawn games package", 1, 225.0, "av"),
            ("Cleanup crew", 1, float(r.choice([350, 400, 450])), "labor")]
    inv["D"] = {"venue": "Old Mill Barn at Wadmalaw", "no": str(r.randint(2201, 2399)), "date": date(2026, 9, 1), "event": "EV-2614",
                "lines": mk(spec), "deposit": float(r.choice([1200, 1500])), "dep_date": date(2026, 5, r.randint(26, 30))}
    spec = [("Garden pavilion rental", 1, float(r.choice([5200, 5400, 5750])), "rent"),
            ("Passed hors d'oeuvres, per guest", g_gala, float(r.choice([26, 28, 31])), "fb"),
            ("Seated dinner, per guest", g_gala, float(r.choice([74, 78, 82])), "fb"),
            ("Tent and patio heaters", 1, float(r.choice([1650, 1850, 1990])), "rent"),
            ("Valet attendants", r.randint(4, 6), 180.0, "labor")]
    spec = with_svc(spec, 0.21, "Service charge 21%")
    inv["E"] = {"venue": "Rosewater Gardens", "no": f"RG-26-{r.randint(900, 990):04d}", "date": date(2026, 9, r.randint(4, 8)), "event": "EV-2619",
                "lines": mk(spec), "deposit": 0.0, "dep_date": None}
    for k, v in inv.items():
        v["subtotal"] = round(sum(x["amount"] for x in v["lines"]), 2)
        v["tax"] = round(sum(x["tax"] for x in v["lines"]), 2)
        v["total"] = round(v["subtotal"] + v["tax"], 2)
        v["balance"] = round(v["total"] - v["deposit"], 2)
    rows = []
    for k in "ABCDE":
        v = inv[k]
        n = 0
        for n, x in enumerate(v["lines"], 1):
            rows.append([f"{v['no']}-{n}", v["event"], v["no"], v["date"].isoformat(), "charge", x["desc"], f"{x['amount']:.2f}", f"{x['tax']:.2f}", f"{v['balance']:.2f}"])
        if v["deposit"]:
            rows.append([f"{v['no']}-{n + 1}", v["event"], v["no"], v["date"].isoformat(), "deposit", "Deposit applied", f"{-v['deposit']:.2f}", "0.00", f"{v['balance']:.2f}"])
    ok = not any(half_cent(x["amount"], RATE[x["cat"]]) for v in inv.values() for x in v["lines"])
    return {"inv": inv, "events": events, "rows": rows, "ok": ok, "couple": couple, "corp": corp, "fam": fam}


def render(ws: str, d: dict, seed: int) -> dict:
    inv = d["inv"]
    P = os.path.join(ws, "venue_invoices")
    os.makedirs(P, exist_ok=True)
    ev = {e[0]: e for e in d["events"]}
    files = {}
    # A: The Foundry, letter, Helvetica, tax amount per line, deposit below the totals
    A = inv["A"]
    files["A"] = f"Foundry_CooperRiver_{A['no']}.pdf"
    write_pdf_document(os.path.join(P, files["A"]), [
        ("title", "The Foundry at Cooper River"), ("small", "1 Foundry Way, North Charleston, SC 29405  |  events@thefoundrycr.example"), ("hr", None),
        ("kv", [("Invoice", A["no"]), ("Invoice date", A["date"].strftime("%B %-d, %Y")), ("Client", "Sable &amp; Sage Events"),
                ("Event", f"{d['couple'].replace('-', ' / ')} Wedding, Saturday {ev['EV-2608'][2].strftime('%-d %B %Y')}")]), ("spacer", 10),
        ("table", [["Description", "Qty", "Rate", "Amount", "Tax"]] +
         [[x["desc"], x["qty"], f"{x['unit']:,.2f}", f"{x['amount']:,.2f}", f"{x['tax']:,.2f}"] for x in A["lines"]],
         {"col_widths": [215, 45, 70, 90, 70], "shade_header": True}), ("spacer", 8),
        ("right", f"Subtotal {usd(A['subtotal'])}"), ("right", f"Sales and hospitality tax {usd(A['tax'])}"),
        ("right", f"<b>Invoice total {usd(A['total'])}</b>"),
        ("right", f"Less deposit received {A['dep_date'].strftime('%m/%d/%Y')} (check 4471) -{usd(A['deposit'])}"),
        ("right", f"<b>BALANCE DUE {usd(A['balance'])}</b>"), ("spacer", 12),
        ("small", "Balance due 14 days before the event. Final guest count guarantee due 10 days prior.")], pagesize="letter", font="Helvetica", base_size=10)
    # B: Magnolia Hall, Times, tax code letters with legend, deposit in a Credits column inside the table
    B = inv["B"]
    files["B"] = f"MagnoliaHall_invoice_{B['no'].split('-')[1]}.pdf"
    trows = [[x["desc"], CODE[x["cat"]], x["qty"], f"{x['unit']:,.2f}", f"{x['amount']:,.2f}", ""] for x in B["lines"]]
    trows.append([f"Deposit paid {B['dep_date'].strftime('%m/%d/%Y')} - thank you", "", "", "", "", f"{B['deposit']:,.2f}"])
    write_pdf_document(os.path.join(P, files["B"]), [
        ("right", "MAGNOLIA HALL<br/>210 Meeting Street, Charleston SC 29401<br/>(843) 555-0172"), ("spacer", 6),
        ("title", "Invoice"),
        ("p", f"Invoice number: {B['no']}<br/>Date: {B['date'].strftime('%m/%d/%Y')}<br/>Bill to: Sable &amp; Sage Events<br/>"
              f"Function: {d['corp']} Leadership Dinner ({ev['EV-2611'][2].strftime('%A, %B %-d')})"), ("spacer", 8),
        ("table", [["Item", "Tax", "Qty", "Price", "Extended", "Credits"]] + trows, {"col_widths": [190, 35, 40, 65, 80, 75], "grid": True}),
        ("spacer", 8),
        ("kv", [("Charges", usd(B["subtotal"])), ("Sales tax", usd(B["tax"])), ("Credits", f"({usd(B['deposit'])})"),
                ("Amount due", usd(B["balance"]))], {"col_widths": [120, 110]}), ("spacer", 10),
        ("small", "Tax codes: F = food, beverage and service charge 11.0%; T = rentals and equipment 9.0%; E = exempt labor."),
        ("small", "Payment by check or ACH within 15 days.")], pagesize="letter", font="Times-Roman", base_size=11)
    # C0 / C: Harborview, Courier, A4, tax rate percent column, advance deposit applied
    for k in ("C0", "C"):
        C = inv[k]
        files[k] = f"Harborview_{C['no']}.pdf"
        head = [("title", "HARBORVIEW TERRACE HOTEL"), ("p", "Catering and Events Office - 40 Concord St, Charleston SC 29401")]
        if k == "C":
            head.append(("h", f"REVISED INVOICE - supersedes invoice {inv['C0']['no']} dated {inv['C0']['date'].strftime('%m/%d/%Y')}"))
        write_pdf_document(os.path.join(P, files[k]), head + [
            ("hr", None),
            ("kv", [("Invoice No", C["no"]), ("Issued", C["date"].strftime("%d %b %Y")), ("Account", "SABLE AND SAGE EVENTS"),
                    ("Group", f"{d['couple'].upper()} REHEARSAL DINNER - FRI 18 SEP 2026"), ("Guarantee", f"{C['guar']} guests")],
             {"col_widths": [90, 330]}), ("spacer", 8),
            ("table", [["Ln", "Description", "Qty", "Unit", "Amount", "Tax %"]] +
             [[i, x["desc"], x["qty"], f"{x['unit']:.2f}", f"{x['amount']:.2f}", f"{RATE[x['cat']] * 100:.1f}%"] for i, x in enumerate(C["lines"], 1)],
             {"col_widths": [25, 175, 35, 65, 75, 55]}), ("spacer", 6),
            ("kv", [("Subtotal", f"{C['subtotal']:.2f}"), ("Tax", f"{C['tax']:.2f}"), ("Total", f"{C['total']:.2f}"),
                    ("Advance deposit applied", f"-{C['deposit']:.2f}"), ("Balance due", f"{C['balance']:.2f}")], {"col_widths": [170, 90]}),
            ("small", "Service charge is taxable. Advance deposit received 07/15/2026 is non-refundable.")], pagesize="a4", font="Courier", base_size=9)
    # D: Old Mill Barn, scanned
    D = inv["D"]
    files["D"] = f"scan_oldmillbarn_{D['date'].strftime('%m%d')}.pdf"
    lines = ["OLD MILL BARN AT WADMALAW", "4410 Maybank Hwy  Wadmalaw Island SC 29487", "",
             f"INVOICE {D['no']}", f"DATE {D['date'].month}/{D['date'].day}/{D['date'].year}", "BILL TO SABLE AND SAGE EVENTS",
             f"EVENT {d['fam'].upper()} 50TH ANNIVERSARY BRUNCH 9/13/2026", "",
             "DESCRIPTION  QTY  AMOUNT  TAX", ""]
    lines += [f"{x['desc']}  {x['qty']}  {x['amount']:.2f}  {x['tax']:.2f}" for x in D["lines"]]
    lines += ["", f"SUBTOTAL  {D['subtotal']:.2f}", f"SALES TAX  {D['tax']:.2f}", f"TOTAL  {D['total']:.2f}",
              f"LESS DEPOSIT RECEIVED {D['dep_date'].month}/{D['dep_date'].day}  -{D['deposit']:.2f}", f"BALANCE DUE  {D['balance']:.2f}", "",
              "THANK YOU - PAYABLE ON RECEIPT"]
    write_scan_pdf(os.path.join(P, files["D"]), lines, font_size=30, skew_deg=0.5, noise=500, seed=seed * 13 + 5)
    # E: Rosewater Gardens, A4, Helvetica, Type column, tax only as category totals
    E = inv["E"]
    files["E"] = f"Rosewater_{E['no']}.pdf"
    rent_base = round(sum(x["amount"] for x in E["lines"] if RATE[x["cat"]] == 0.09), 2)
    fb_base = round(sum(x["amount"] for x in E["lines"] if RATE[x["cat"]] == 0.11), 2)
    rent_tax = round(sum(x["tax"] for x in E["lines"] if RATE[x["cat"]] == 0.09), 2)
    fb_tax = round(sum(x["tax"] for x in E["lines"] if RATE[x["cat"]] == 0.11), 2)
    write_pdf_document(os.path.join(P, files["E"]), [
        ("table", [["ROSEWATER GARDENS", f"Invoice {E['no']}"], ["Johns Island, South Carolina", f"Dated {E['date'].strftime('%b %-d %Y')}"]],
         {"col_widths": [260, 200], "shade_header": True}), ("spacer", 8),
        ("p", f"Prepared for Sable &amp; Sage Events - Tidewater Literacy Council Gala, {ev['EV-2619'][2].strftime('%B %-d, %Y')}"), ("spacer", 6),
        ("table", [["#", "Type", "Description", "Qty", "Each", "Line total"]] +
         [[i, TYPE[x["cat"]], x["desc"], x["qty"], f"{x['unit']:,.2f}", f"{x['amount']:,.2f}"] for i, x in enumerate(E["lines"], 1)],
         {"col_widths": [20, 100, 170, 40, 60, 75]}), ("spacer", 6),
        ("kv", [("Taxable rentals", f"{rent_base:,.2f}"), ("Sales tax 9% on rentals", f"{rent_tax:,.2f}"),
                ("Food, beverage and service charge", f"{fb_base:,.2f}"), ("Hospitality and sales tax 11%", f"{fb_tax:,.2f}"),
                ("Labor (not taxed)", f"{round(E['subtotal'] - rent_base - fb_base, 2):,.2f}"), ("Invoice total", f"{E['total']:,.2f}")],
         {"col_widths": [190, 90]}), ("spacer", 8),
        ("small", "No deposit is held for this event. Balance payable within 10 days of the invoice date.")], pagesize="a4", font="Helvetica", base_size=9)
    return files


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    files = render(ws, d, seed)
    write_csv(os.path.join(ws, "event_list.csv"), ["event_code", "event", "event_date", "venue"],
              [[c, n, dt.isoformat(), v] for c, n, dt, v in sorted(d["events"])])
    write_text(os.path.join(ws, "note_from_tamsin.txt"),
               "Venue invoices for September\n\n"
               "Every venue invoice we have for the September events is in venue_invoices. I need them keyed into the job-cost sheet, "
               "one row per invoice line, save as venue_lines.csv with these columns:\n\n"
               "line_ref - the invoice number exactly as the venue prints it, a hyphen, then the line number (1, 2, 3 in the order the "
               "lines are printed). A deposit counts as the last line of its invoice.\n"
               "event_code - from event_list.csv.\n"
               "invoice_no - as printed.\n"
               "invoice_date - YYYY-MM-DD.\n"
               "line_type - charge, or deposit for money we already paid that the venue credits on the invoice.\n"
               "description - as printed. For a deposit row just write Deposit applied.\n"
               "amount - before tax, plain number. Deposits go in negative.\n"
               "tax - the tax on that one line in dollars. Not every venue prints it per line, so work it out from the rate or code "
               "they show and round to the cent. 0 on exempt lines and deposits.\n"
               "balance_due - what the invoice says we still owe after the deposit, repeated on every row of that invoice.\n\n"
               "Venues sometimes re-send an invoice when the count changes. Only the current version gets keyed - the old one is dead.\n\n"
               "Thanks!\nTamsin\n")
    write_csv(os.path.join(ref, "venue_lines.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "venue_lines.csv"), HEADER, d["rows"])
    inv = d["inv"]
    refs = lambda k: [f"{inv[k]['no']}-{i}" for i in range(1, len(inv[k]["lines"]) + (2 if inv[k]["deposit"] else 1))]
    D = inv["D"]
    scan_figs = [D["no"], f"{D['balance']:.2f}", f"{D['tax']:.2f}", f"{D['deposit']:.2f}"] + [x["desc"] for x in D["lines"]] + \
                [f"{x['amount']:.2f}" for x in D["lines"]] + [f"{x['tax']:.2f}" for x in D["lines"]]
    write_json(os.path.join(ref, "notes.json"), {"files": files, "superseded": inv["C0"]["no"],
                                                  "totals": {k: {"no": v["no"], "total": v["total"], "balance": v["balance"]} for k, v in inv.items()},
                                                  "scan_figures": {f"venue_invoices/{files['D']}": scan_figs}})
    num = {"numeric": True, "tolerance": 0.01, "min_accuracy": 1.0}
    P = "venue_lines.csv"
    write_task_yaml(HERE, {
        "id": "venue-invoices", "track": "desk", "category": "extraction",
        "title": "Key the September venue invoices into job costing",
        "ask": ("The venue invoices for our September events are in the folder. Can you key them into venue_lines.csv for job costing? "
                "Tamsin's note explains how she wants it laid out.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "deposits already paid are credited four ways: below the totals (Foundry, Old Mill Barn), as an 'Advance deposit applied' line under "
            "Harborview's totals, and inside Magnolia Hall's item table in a Credits column printed positive; each must become its own negative "
            "deposit row, and balance due is the figure after the deposit, not the invoice total (checks: one row per invoice line; line types; "
            "amounts; balance due)",
            "tax is wanted per line but only the Foundry and Old Mill Barn print it that way: Magnolia Hall prints a letter code (F, T, E) with the "
            "rates in a legend at the foot, Harborview prints a rate percent, and Rosewater prints only category tax totals under a Type column "
            "(check: line tax)",
            f"Harborview re-issued the rehearsal dinner invoice as {inv['C']['no']} when the guarantee dropped; the superseded {inv['C0']['no']} "
            "with more guests and a higher balance is still in the folder (checks: one row per invoice line; row count; amounts)",
            "Harborview hosts both the rehearsal dinner and the farewell brunch for the same couple, and Magnolia Hall hosts two events for the "
            "same company; the event code comes from the event the invoice names (check: event codes and invoice numbers)",
            f"the Old Mill Barn invoice {D['no']} is an image-only scan (checks: descriptions; balance due)",
            f"invoice dates are printed in five formats ('{inv['A']['date'].strftime('%B %-d, %Y')}', '{inv['B']['date'].strftime('%m/%d/%Y')}', "
            f"'{inv['C']['date'].strftime('%d %b %Y')}', '9/1/2026', '{inv['E']['date'].strftime('%b %-d %Y')}') and the sheet wants YYYY-MM-DD (check: invoice dates)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per invoice line", "path": P, "column": "line_ref", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "event codes and invoice numbers", "path": P, "ref": P, "key": "line_ref",
             "columns": ["event_code", "invoice_no"], "min_accuracy": 1.0, "must_match_keys": refs("C") + refs("B")},
            {"type": "csv_values_match", "name": "invoice dates", "path": P, "ref": P, "key": "line_ref", "columns": ["invoice_date"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "descriptions", "path": P, "ref": P, "key": "line_ref", "columns": ["description"],
             "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": refs("D")},
            {"type": "csv_values_match", "name": "line types", "path": P, "ref": P, "key": "line_ref", "columns": ["line_type"], "min_accuracy": 1.0,
             "must_match_keys": [refs(k)[-1] for k in "ABCD"]},
            {"type": "csv_values_match", "name": "amounts", "path": P, "ref": P, "key": "line_ref", "columns": ["amount"],
             "must_match_keys": refs("B") + refs("C"), **num},
            {"type": "csv_values_match", "name": "line tax", "path": P, "ref": P, "key": "line_ref", "columns": ["tax"],
             "must_match_keys": refs("B") + refs("C") + refs("E"), **num},
            {"type": "csv_values_match", "name": "balance due", "path": P, "ref": P, "key": "line_ref", "columns": ["balance_due"],
             "must_match_keys": refs("A") + refs("B") + refs("C") + refs("D"), **num},
        ],
    })
    print(f"seed={seed} rows={len(d['rows'])} " + ", ".join(f"{k}:{v['no']} bal={v['balance']}" for k, v in inv.items()))


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: every invoice file keyed (the superseded original too), item-table rows only (no deposit rows),
    tax copied where a dollar figure is printed on the line and 0 otherwise, balance due = the invoice total, the first event
    at the venue in the event list."""
    os.makedirs(out, exist_ok=True)
    inv = d["inv"]
    first_at = {}
    for c, n, dt, v in sorted(d["events"]):
        first_at.setdefault(v, c)
    rows = []
    for k in ("A", "B", "C0", "C", "D", "E"):
        v = inv[k]
        for n, x in enumerate(v["lines"], 1):
            tax = x["tax"] if k in ("A", "D") else 0.0
            rows.append([f"{v['no']}-{n}", first_at[v["venue"]], v["no"], v["date"].isoformat(), "charge", x["desc"], f"{x['amount']:.2f}",
                         f"{tax:.2f}", f"{v['total']:.2f}"])
    write_csv(os.path.join(out, "venue_lines.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if d_["ok"]:
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, d_, a.naive)
