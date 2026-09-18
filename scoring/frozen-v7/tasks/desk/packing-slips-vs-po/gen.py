#!/usr/bin/env python3
"""packing-slips-vs-po: this week's packing slips matched against the open purchase order lines.

    python gen.py [--seed N]

Business: a bike shop receives parts from four distributors. The receiving lead wants every open PO line
with what has actually arrived so far, what is still open, and any substitutions.

Traps (each caught by a check, see task.yaml):
  * slips print Ordered, Shipped and Backordered side by side; received is what shipped    (check: received quantities)
  * Cascadia sent a second slip that fills part of the first slip's backorders; receipts add up across slips
    (checks: received quantities; line status)
  * Trailhead shipped a different headlamp in place of the one ordered; it counts against the PO line and the
    substitute SKU is recorded, but the substitute is not a PO line of its own  (checks: substitutions; one row per PO line)
  * the Velo Parts slip is an image-only scan with no PO number; the vendor and SKUs tie it to the one open Velo PO
    (check: received quantities)
  * Summit's packing list is organized by carton and the same SKU is split across two cartons (check: received quantities)
  * a PO line nothing shipped for stays at zero received with status open        (checks: line status; one row per PO line)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

SHOP = "Zephyr Bike Works"
SHOP_ADDR = "77 Water St, Burlington, VT 05401"
MM = 2.8346

VENDORS = {
    "cascadia": ("Cascadia Cycle Supply", [("TB-700x28-PV", "Tube 700x25-32c presta 48mm", 3.40), ("TB-29x2.4-SV", "Tube 29x2.1-2.4 schrader", 4.10),
                                          ("CB-BRK-ROAD", "Brake cable road stainless 1.5mm", 1.95), ("HT-BLK-3M", "Handlebar tape black cork", 9.80),
                                          ("CN-KMC-X11", "Chain 11-speed 118L", 24.50)]),
    "trailhead": ("Trailhead Distribution", [("HL-300", "Headlamp 300 lumen USB-C", 21.00), ("TL-50", "Tail light 50 lumen", 11.25),
                                            ("LK-UBOLT-M", "U-lock medium with bracket", 32.00), ("BL-HANDLE-B", "Bell brass handlebar", 6.40)]),
    "velo": ("Velo Parts Direct", [("CS-11-32", "Cassette 11-speed 11-32T", 48.00), ("BP-DISC-R", "Disc brake pads resin pair", 7.90),
                                  ("RT-160-6B", "Rotor 160mm 6-bolt", 18.60), ("DR-RD-11M", "Derailleur hanger universal", 12.30)]),
    "summit": ("Summit Tire and Tube Co", [("TR-700x32-GRV", "Tire 700x32 gravel folding", 27.50), ("TR-29x2.4-TRL", "Tire 29x2.4 trail TR", 41.00),
                                          ("SL-SEAL-16", "Tubeless sealant 16oz", 12.75)]),
}
SUB = ("HL-400", "Headlamp 400 lumen USB-C")


def build(seed: int) -> dict:
    r = rng(seed)
    nums = r.sample(range(20100, 20999), 4)
    pos = {}
    for (key, (vname, items)), num, pdate in zip(VENDORS.items(), nums, [date(2026, 8, 24), date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 31)]):
        lines = []
        for i, (sku, desc, cost) in enumerate(items, 1):
            q = r.choice([6, 8, 10, 12, 20, 24]) if key != "summit" else r.choice([12, 18, 24])
            lines.append(dict(po=f"PO-{num}", line=i, sku=sku, desc=desc, cost=cost, ordered=q, received=0, sub=""))
        pos[key] = dict(num=f"PO-{num}", vendor=vname, date=pdate, lines=lines)
    ca, tr, ve, su = (pos[k]["lines"] for k in ("cascadia", "trailhead", "velo", "summit"))
    # Cascadia slip 1: lines 1,2,3 full; line 4 partial (backorder); line 5 fully backordered
    ca[3]["ordered"] = 12; ca[4]["ordered"] = 10
    s1 = [(ca[0], ca[0]["ordered"], 0), (ca[1], ca[1]["ordered"], 0), (ca[2], ca[2]["ordered"], 0), (ca[3], 7, 5), (ca[4], 0, 10)]
    # Cascadia slip 2 (backorder release): line 4 remaining 5, line 5 partial 6 of 10
    s2 = [(ca[3], 5, 0), (ca[4], 6, 4)]
    # Trailhead: substitute headlamp, full; tail light partial with backorder; lock full; bell not shipped (no slip line)
    tr[0]["ordered"] = 8; tr[1]["ordered"] = 12
    s3 = [(tr[0], 8, 0), (tr[1], 9, 3), (tr[2], tr[2]["ordered"], 0)]
    # Velo (scan, no PO no.): cassette, pads, rotor shipped; hanger not
    s4 = [(ve[0], ve[0]["ordered"], 0), (ve[1], ve[1]["ordered"], 0), (ve[2], ve[2]["ordered"] - 2, 2)]
    # Summit: two cartons, gravel tire split across cartons, sealant full, trail tire short
    su[0]["ordered"] = 24; su[1]["ordered"] = 12; su[2]["ordered"] = 12
    cartons = [[(su[0], 12), (su[1], 6)], [(su[0], 10), (su[2], 12)]]
    for slip in (s1, s2, s3, s4):
        for ln, shipped, _ in slip:
            ln["received"] += shipped
    for carton in cartons:
        for ln, q in carton:
            ln["received"] += q
    tr[0]["sub"] = SUB[0]
    slip_nos = r.sample(range(100000, 999999), 5)
    return dict(pos=pos, s1=s1, s2=s2, s3=s3, s4=s4, cartons=cartons, slip_nos=slip_nos, lead=person(r), buyer=person(r))


def emit(seed: int) -> None:
    d = build(seed); pos = d["pos"]; sn = d["slip_nos"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "packing_slips"); os.makedirs(F, exist_ok=True)

    # ---- open PO export (xlsx with title and preamble)
    rows = []
    for key in ("cascadia", "trailhead", "velo", "summit"):
        p = pos[key]
        for ln in p["lines"]:
            rows.append([p["num"], ln["line"], p["vendor"], ln["sku"], ln["desc"], ln["ordered"], ln["cost"], p["date"], "Open"])
    by = d["buyer"]
    write_xlsx(os.path.join(ws, "open_purchase_orders.xlsx"), {"Open PO lines": {
        "merged_title": f"{SHOP} - Open purchase order lines", "preamble": [[f"Printed by {by[0][0]}. {by[1]} on 09/08/2026"]],
        "header": ["PO Number", "Line", "Vendor", "SKU", "Description", "Qty Ordered", "Unit Cost", "PO Date", "Status"], "rows": rows,
        "widths": {"A": 12, "C": 26, "D": 16, "E": 34}}}, creator="Purchasing")

    ca = pos["cascadia"]
    # ---- Cascadia slip 1 (Helvetica, letter, grid table with ordered/shipped/backordered)
    def cascadia(fn, slip_no, ship_date, lines, note, font, size="letter"):
        write_pdf_document(os.path.join(F, fn), [
            ("title", "Cascadia Cycle Supply"), ("small", "4410 Industrial Way, Portland, OR 97210  |  orders@cascadiacycle.example"), ("hr", None),
            ("kv", [("PACKING SLIP", f"No. {slip_no}"), ("Ship date", ship_date), ("Customer PO", ca["num"]), ("Ship to", f"{SHOP}, {SHOP_ADDR}")],
             {"col_widths": [40 * MM, 120 * MM]}),
            ("spacer", 8),
            ("table", [["Item", "Description", "Ordered", "Shipped", "Backordered"]] +
                      [[ln["sku"], ln["desc"], ln["ordered"], shp, bo] for ln, shp, bo in lines],
             {"col_widths": [32 * MM, 68 * MM, 22 * MM, 22 * MM, 26 * MM], "grid": True, "shade_header": True}),
            ("spacer", 6), ("p", note), ("spacer", 10), ("small", "Packed by: WH-3   Cartons: 2   Please report shortages within 5 business days."),
        ], pagesize=size, font=font, base_size=9.5)
    cascadia("Cascadia_PS_{}.pdf".format(sn[0]), sn[0], "09/01/2026", d["s1"],
             "Backordered items will ship automatically as soon as stock arrives. No additional freight will be charged.", "Helvetica")
    cascadia("Cascadia_PS_{}_backorder.pdf".format(sn[1]), sn[1], "09/07/2026", d["s2"],
             "BACKORDER RELEASE - this shipment fills backorders from an earlier packing slip. Ordered shows your original order quantity.", "Times-Roman")

    # ---- Trailhead (Courier, A4, substitution note)
    tr = pos["trailhead"]
    body = [["Line", "Product", "Qty ord", "Qty ship", "B/O"]]
    for ln, shp, bo in d["s3"]:
        if ln["sku"] == "HL-300":
            body.append([str(ln["line"]), f"{SUB[0]} {SUB[1]}<br/>** SUBSTITUTE for HL-300 Headlamp 300 lumen - no charge upgrade **", ln["ordered"], shp, bo])
        else:
            body.append([str(ln["line"]), f"{ln['sku']} {ln['desc']}", ln["ordered"], shp, bo])
    write_pdf_document(os.path.join(F, f"trailhead_packlist_{sn[2]}.pdf"), [
        ("right", f"Packing list {sn[2]}"), ("title", "TRAILHEAD DISTRIBUTION"), ("small", "Reno, NV  |  775-555-0161"), ("spacer", 4),
        ("p", f"Sold to / Ship to: {SHOP}<br/>{SHOP_ADDR}"), ("p", f"Your order: {tr['num']}     Shipped: 09/03/2026 via ground"), ("hr", None),
        ("table", body, {"col_widths": [14 * MM, 100 * MM, 18 * MM, 20 * MM, 14 * MM]}),
        ("spacer", 6), ("p", "Items not listed on this packing list have not shipped and remain on order."),
    ], pagesize="a4", font="Courier", base_size=8.5)

    # ---- Velo (scan, no PO number)
    ve = pos["velo"]
    lines = ["VELO PARTS DIRECT", "PACKING SLIP", "", f"Slip #: {sn[3]}", "Date: 09/04/2026", f"Ship to: {SHOP}", SHOP_ADDR, "Customer PO: (none given)",
             "Ref: phone order", ""]
    for ln, shp, bo in d["s4"]:
        lines.append(f"Item {ln['sku']}")
        lines.append(f"  {ln['desc']}")
        lines.append(f"  Ordered: {ln['ordered']}   Shipped: {shp}")
    lines += ["", "Balance of order ships when available.", "Received by: ____________"]
    write_scan_pdf(os.path.join(F, "scan_0904_slip.pdf"), lines, font_size=32, seed=seed * 3 + 9, skew_deg=0.3, noise=240)

    # ---- Summit (Helvetica, carton-by-carton packing list)
    su = pos["summit"]
    blocks = [("title", "Summit Tire and Tube Co"), ("p", f"PACKING LIST {sn[4]}  |  Ship date September 5, 2026  |  PO reference {su['num']}"), ("hr", None),
              ("p", f"Deliver to: {SHOP}, {SHOP_ADDR}")]
    for i, carton in enumerate(d["cartons"], 1):
        blocks += [("h", f"Carton {i} of {len(d['cartons'])}"),
                   ("table", [["SKU", "Description", "Qty in carton"]] + [[ln["sku"], ln["desc"], q] for ln, q in carton], {"col_widths": [45 * MM, 85 * MM, 35 * MM]})]
    blocks += [("spacer", 8), ("small", "Quantities are per carton. Short-shipped items are backordered and will ship separately.")]
    write_pdf_document(os.path.join(F, f"Summit_packing_list_{sn[4]}.pdf"), blocks, font="Helvetica", base_size=10)

    lead = d["lead"]
    write_text(os.path.join(ws, "note_from_receiving.txt"),
        "Receiving update for purchasing\n\n"
        "This week's packing slips are in packing_slips. Please check them against the open PO lines and give me receipts.csv, "
        "one row for every line on the open PO list:\n\n"
        "po_line          PO number, a hyphen, and the line number (PO-12345-2)\n"
        "sku              the SKU on the PO line\n"
        "qty_ordered      from the PO\n"
        "qty_received     everything that has physically arrived for that line so far, across all slips\n"
        "qty_open         ordered minus received\n"
        "substitute_sku   if the vendor shipped a different item in place of the one ordered, the SKU they shipped; otherwise blank\n"
        "status           received (nothing open), partial (some arrived, some open) or open (nothing arrived)\n\n"
        "Substitutes we keep, so they count against the line they replaced.\n\n"
        f"{lead[0]}\n")

    header = ["po_line", "sku", "qty_ordered", "qty_received", "qty_open", "substitute_sku", "status"]
    out = []
    for key in ("cascadia", "trailhead", "velo", "summit"):
        for ln in pos[key]["lines"]:
            op = max(ln["ordered"] - ln["received"], 0)
            st = "received" if op == 0 else ("partial" if ln["received"] > 0 else "open")
            out.append([f"{ln['po']}-{ln['line']}", ln["sku"], ln["ordered"], ln["received"], op, ln["sub"], st])
    write_csv(os.path.join(ref, "receipts.csv"), header, out)
    write_csv(os.path.join(sol, "receipts.csv"), header, out)
    pl = lambda key, i: f"{pos[key]['num']}-{i}"
    write_json(os.path.join(ref, "notes.json"), {"backorder_lines": [pl("cascadia", 4), pl("cascadia", 5), pl("trailhead", 2)], "sub_line": pl("trailhead", 1),
                                                 "unshipped": [pl("trailhead", 4), pl("velo", 4)], "velo_lines": [pl("velo", i) for i in (1, 2, 3)],
                                                 "carton_split": pl("summit", 1),
                                                 "slip1_only": {pl("cascadia", 4): 7, pl("cascadia", 5): 0}})
    write_task_yaml(HERE, {
        "id": "packing-slips-vs-po", "track": "desk", "category": "extraction",
        "title": "Match this week's packing slips to the open POs",
        "ask": "Can you check this week's packing slips against our open purchase orders and give me receipts.csv? The receiving note says what purchasing needs on it.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the Cascadia and Trailhead slips print ordered, shipped and backordered quantities side by side; received is what shipped, not what was ordered (check: received quantities)",
            "Cascadia's second slip is a backorder release for the same PO: one line backordered on the first slip is completed and another is only partly filled, so receipts add across both slips and the second slip's 'Ordered' column repeats the original quantity (checks: received quantities; line status)",
            "Trailhead shipped HL-400 in place of the HL-300 on the PO; it counts against the HL-300 line with substitute_sku HL-400 and is not a line of its own (checks: substitutions; one row per PO line)",
            "the Velo Parts slip is an image-only scan that says 'Customer PO: (none given)'; its vendor and SKUs tie it to the one open Velo PO (check: received quantities)",
            "Summit's packing list is laid out by carton and the gravel tire appears in both cartons; reading one carton under-counts the line (check: received quantities)",
            "the Trailhead bell and the Velo derailleur hanger are not on any slip; they stay on the list at zero received with status open (checks: line status; one row per PO line)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "receipts.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per PO line", "path": "receipts.csv", "column": "po_line", "ref": "receipts.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "receipts.csv", "equals_ref": "receipts.csv"},
            {"type": "csv_values_match", "name": "SKUs and ordered quantities", "path": "receipts.csv", "ref": "receipts.csv", "key": "po_line",
             "columns": ["sku", "qty_ordered"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "received quantities", "path": "receipts.csv", "ref": "receipts.csv", "key": "po_line",
             "columns": ["qty_received", "qty_open"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [pl("cascadia", 4), pl("cascadia", 5), pl("trailhead", 2), pl("velo", 1), pl("velo", 3), pl("summit", 1)]},
            {"type": "csv_values_match", "name": "substitutions", "path": "receipts.csv", "ref": "receipts.csv", "key": "po_line",
             "columns": ["substitute_sku"], "min_accuracy": 1.0, "must_match_keys": [pl("trailhead", 1)]},
            {"type": "csv_values_match", "name": "line status", "path": "receipts.csv", "ref": "receipts.csv", "key": "po_line",
             "columns": ["status"], "min_accuracy": 1.0, "must_match_keys": [pl("cascadia", 5), pl("trailhead", 4), pl("velo", 4), pl("summit", 2)]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
