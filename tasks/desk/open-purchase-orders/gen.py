#!/usr/bin/env python3
"""open-purchase-orders: what is still to come on each purchase order line, from the open PO report and the dock log.

    python gen.py [--seed N] [--naive DIR]

Business: a craft brewery buying packaging, ingredients and taproom supplies. Purchasing orders in the
vendor's unit (boxes of carriers, boxes of lids); the dock logs what arrives, mostly in eaches.

Traps (each caught by a check, see task.yaml):
  * PO lines ordered in boxes, receipts logged in eaches (and a few in boxes) (checks: open quantity; lines still open)
  * partial receipts spread over several log rows                            (check: open quantity)
  * over-received lines listed with open 0 and flagged OVER                   (check: over-receipt flag)
  * the vendor emails cancel one line and short-close another                 (check: lines still open)
  * a return to vendor is logged as a positive quantity with Type=Return      (check: open quantity)
  * the log types the PO line four ways; receipts for a closed July PO are in the log (check: open quantity)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# item, description, purchase uom, units per purchase uom, vendor, unit cost range (per purchase unit)
ITEMS = [
    ("CAR-4PK", "4-pack can carrier, black", "BX", 250, "Pacific Packaging", 38, 52),
    ("LID-202", "202 can end, silver", "BX", 500, "Northwest Can Supply", 21, 29),
    ("CAN-16", "16oz can, bright", "BX", 200, "Northwest Can Supply", 44, 58),
    ("TRY-4X6", "Corrugated tray, 4x6", "BX", 50, "Pacific Packaging", 31, 40),
    ("KEG-CAP", "Keg cap, red", "BX", 100, "BSG Craft Brewing", 17, 24),
    ("GLS-PNT", "Pint glass, logo", "BX", 24, "Promo Print Co", 62, 80),
    ("CST-LOGO", "Coaster, logo", "BX", 500, "Promo Print Co", 45, 60),
    ("LBL-HAZY", "Shrink sleeve, Hazy IPA", "BX", 1000, "Pacific Packaging", 95, 120),
    ("HOP-CIT", "Citra hop pellets 11 lb", "EA", 1, "BSG Craft Brewing", 118, 140),
    ("MLT-2ROW", "2-row base malt 55 lb bag", "EA", 1, "BSG Craft Brewing", 38, 47),
    ("YST-US05", "Dry yeast US-05 500 g", "EA", 1, "BSG Craft Brewing", 52, 66),
    ("CLN-PBW", "PBW cleaner 50 lb pail", "EA", 1, "BSG Craft Brewing", 150, 185),
    ("TSH-M", "T-shirt, logo, M", "EA", 1, "Promo Print Co", 8, 12),
    ("TSH-L", "T-shirt, logo, L", "EA", 1, "Promo Print Co", 8, 12),
]
ITEM = {i[0]: i for i in ITEMS}
VENDORS = sorted({i[4] for i in ITEMS})
AS_OF = date(2026, 9, 10)
RECEIVERS = ["J. Ortiz", "M. Kim", "Tanner B."]


def ref_variant(po: int, line: int, style: int) -> str:
    return [f"{po}-{line:02d}", f"PO {po}-{line}", f"{po}/{line}", f"PO#{po} ln {line}"][style % 4]


def build(seed: int) -> dict:
    r = rng(seed)
    lines = []
    po_no = 4461
    d0 = date(2026, 7, 21)
    while len(lines) < 38:
        vendor = VENDORS[(po_no * 7 + r.randint(0, 3)) % len(VENDORS)]
        pool = [i for i in ITEMS if i[4] == vendor]
        n = min(len(pool), r.randint(2, 4))
        podate = d0 + timedelta(days=(po_no - 4461) * 3 + r.randint(0, 2))
        for ln, it in enumerate(r.sample(pool, n), start=1):
            code_, desc, uom, pack, _, lo, hi = it
            qty = r.randint(3, 14) if uom == "BX" else r.choice([10, 12, 20, 24, 30, 40, 50, 60])
            lines.append({"po": po_no, "line": ln, "ref": f"{po_no}-{ln:02d}", "item": code_, "desc": desc, "uom": uom,
                          "pack": pack, "qty": qty, "cost": round(r.uniform(lo, hi), 2), "vendor": vendor, "date": podate,
                          "ordered_ea": qty * pack})
        po_no += 1
    # scenarios, with the trap structure pinned
    box = [x for x in lines if x["uom"] == "BX" and x["qty"] >= 4]
    each = [x for x in lines if x["uom"] == "EA"]
    r.shuffle(box); r.shuffle(each)
    if len(box) < 11 or len(each) < 8:
        return {"bad": True}
    plan = {}
    for x in box[:4]: plan[x["ref"]] = "partial"
    for x in box[4:7]: plan[x["ref"]] = "full"
    plan[box[7]["ref"]] = "over"
    plan[box[8]["ref"]] = "shortclose"
    plan[box[9]["ref"]] = "rtv"
    plan[box[10]["ref"]] = "cancel"
    for x in each[:3]: plan[x["ref"]] = "partial"
    for x in each[3:6]: plan[x["ref"]] = "full"
    for x in each[6:8]: plan[x["ref"]] = "over"
    rest = [x for x in lines if x["ref"] not in plan]
    for x in rest:
        plan[x["ref"]] = r.choice(["none", "full", "full", "partial", "none"])
    receipts = []

    used_days: dict = {}

    def add(x, ea, kind="Receipt", in_boxes=False, note=""):
        lo = x["date"] + timedelta(days=4)
        hi = AS_OF - timedelta(days=1)
        taken = used_days.setdefault(x["ref"], [])
        start = max([lo] + [t + timedelta(days=2) for t in taken])
        span = (hi - start).days
        day = start + timedelta(days=r.randint(0, max(0, min(span, 12)))) if span >= 0 else hi
        taken.append(day)
        if in_boxes and x["uom"] == "BX" and ea % x["pack"] == 0:
            qty, unit = ea // x["pack"], r.choice(["BX", "box", "bx"])
        else:
            qty, unit = ea, r.choice(["EA", "ea", "each", "EA"])
        receipts.append({"date": day, "type": kind, "po": x["po"], "line": x["line"], "item": x["item"], "qty": qty,
                         "unit": unit, "ea": ea if kind == "Receipt" else -ea, "note": note})

    def split(total, parts, pack):
        if parts == 1:
            return [total]
        if pack > 1 and total % pack == 0 and total // pack >= parts:
            boxes = total // pack
            cuts = sorted(r.sample(range(1, boxes), parts - 1))
            return [(b - a) * pack for a, b in zip([0] + cuts, cuts + [boxes])]
        cuts = sorted(r.sample(range(1, total), parts - 1))
        return [b - a for a, b in zip([0] + cuts, cuts + [total])]

    boxed_logged = set()
    for x in lines:
        s = plan[x["ref"]]
        o, pack = x["ordered_ea"], x["pack"]
        if s == "partial":
            k = r.randint(1, min(3, x["qty"] - 1)) if pack > 1 else r.randint(1, 3)
            got = (r.randint(1, x["qty"] - 1) * pack) if pack > 1 else r.randint(max(1, o // 5), o - 2)
            if pack > 1 and got // pack < k:
                k = 1
            for i, part in enumerate(split(got, k, pack)):
                boxed = pack > 1 and i == 0 and len(boxed_logged) < 3
                if boxed: boxed_logged.add(x["ref"])
                add(x, part, in_boxes=boxed)
        elif s == "full":
            k = r.randint(1, 2)
            for part in split(o, k, pack):
                add(x, part)
        elif s == "over":
            extra = pack if pack > 1 else r.randint(2, 6)
            for part in split(o, 2, pack) if o >= 2 else [o]:
                add(x, part)
            add(x, extra, note="extra on pallet, kept")
        elif s == "shortclose":
            got = max(1, x["qty"] // 2) * pack
            add(x, got)
        elif s == "rtv":
            add(x, o)
            back = pack * r.randint(1, 2)
            add(x, back, kind="Return", note="crushed on arrival - RTV, replacement coming")
    # closed July PO, still in the dock log
    old = [{"date": date(2026, 8, 3), "type": "Receipt", "po": 4448, "line": 1, "item": "MLT-2ROW", "qty": 40, "unit": "EA", "ea": 40, "note": ""},
           {"date": date(2026, 8, 3), "type": "Receipt", "po": 4448, "line": 2, "item": "HOP-CIT", "qty": 6, "unit": "EA", "ea": 6, "note": ""},
           {"date": date(2026, 8, 5), "type": "Receipt", "po": 4451, "line": 1, "item": "CAN-16", "qty": 12, "unit": "BX", "ea": 2400, "note": ""}]
    receipts = sorted(receipts + old, key=lambda z: (z["date"], z["po"], z["line"]))
    for i, z in enumerate(receipts):
        z["style"] = r.randrange(4)
        z["by"] = r.choice(RECEIVERS)

    out = []
    for x in lines:
        s = plan[x["ref"]]
        rec = sum(z["ea"] for z in receipts if z["po"] == x["po"] and z["line"] == x["line"])
        x["received_ea"] = rec
        x["scenario"] = s
        if s in ("cancel", "shortclose"):
            continue
        over = rec > x["ordered_ea"]
        opn = max(x["ordered_ea"] - rec, 0)
        if opn > 0 or over:
            out.append({"ref": x["ref"], "item": x["item"], "ordered": x["ordered_ea"], "received": rec, "open": opn,
                        "flag": "OVER" if over else ""})
    return {"lines": lines, "receipts": receipts, "plan": plan, "out": out, "boxed_logged": sorted(boxed_logged)}


def acceptable(d: dict) -> bool:
    if d.get("bad"):
        return False
    plan = d["plan"]
    if sum(1 for v in plan.values() if v == "partial") < 7 or len(d["boxed_logged"]) < 2:
        return False
    # a partial box line must have a receipt typed in a non-canonical way, so an exact-text join misses it
    partial_box = [x for x in d["lines"] if plan[x["ref"]] == "partial" and x["uom"] == "BX"]
    styled = [x for x in partial_box if any(z["po"] == x["po"] and z["line"] == x["line"] and z["style"] != 0
                                            for z in d["receipts"])]
    # receipts on one line never share a day (they would read as duplicate entries)
    seen = set()
    for z in d["receipts"]:
        k = (z["po"], z["line"], z["date"])
        if k in seen:
            return False
        seen.add(k)
    return len(styled) >= 2 and 12 <= len(d["out"]) <= 26


def naive_rows(d: dict) -> list[list]:
    """Sum the Qty column per line as written (boxes and eaches alike, returns added), compare with the report's
    Qty Ordered in its own unit, ignore the vendor emails."""
    rows = []
    for x in d["lines"]:
        rec = sum(z["qty"] for z in d["receipts"] if z["po"] == x["po"] and z["line"] == x["line"] and z["style"] == 0)
        opn = x["qty"] - rec
        if opn != 0:
            rows.append([x["ref"], x["item"], x["qty"], rec, max(opn, 0), "OVER" if opn < 0 else ""])
    return rows


HEADER = ["po_line", "item", "ordered", "received", "open", "flag"]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_csv(os.path.join(naive_dir, "open_po_lines.csv"), HEADER, naive_rows(d))
        return
    ws, ref, sol = task_dirs(HERE)
    plan = d["plan"]
    lines = d["lines"]
    cancel = next(x for x in lines if plan[x["ref"]] == "cancel")
    short = next(x for x in lines if plan[x["ref"]] == "shortclose")
    short_got = short["received_ea"] // short["pack"]

    write_csv(os.path.join(ws, "open_po_report_2026-09-10.csv"),
              ["PO Line", "PO Date", "Vendor", "Item", "Description", "Qty Ordered", "UoM", "Unit Cost", "Line Status"],
              [[x["ref"], x["date"].strftime("%m/%d/%Y"), x["vendor"], x["item"], x["desc"], x["qty"], x["uom"],
                f"{x['cost']:.2f}", "Open"] for x in sorted(lines, key=lambda z: (z["po"], z["line"]))],
              preamble=["Open Purchase Orders - all vendors", "As of 09/10/2026"], crlf=True)
    write_csv(os.path.join(ws, "item_master.csv"),
              ["Item", "Description", "Stock UoM", "Purchase UoM", "Units per Purchase UoM", "Default Vendor"],
              [[i[0], i[1], "EA", i[2], i[3], i[4]] for i in ITEMS])
    log_rows = []
    for z in d["receipts"]:
        log_rows.append([z["date"], z["type"], ref_variant(z["po"], z["line"], z["style"]), z["item"], z["qty"], z["unit"],
                         z["by"], z["note"]])
    write_xlsx(os.path.join(ws, "dock_receiving_log.xlsx"), {"Log": {
        "merged_title": "Dock receiving log - Tamarack Brewing",
        "header": ["Date", "Type", "PO / line", "Item", "Qty", "Unit", "Received by", "Note"], "rows": log_rows,
        "widths": {"A": 12, "C": 16, "D": 12, "G": 12, "H": 40}}}, creator="Dock tablet")
    write_email_thread(os.path.join(ws, "email_thread_purchasing.txt"), [
        {"from": f"Orders <orders@{cancel['vendor'].lower().replace(' ', '')}.com>", "to": "Leila Haddad <leila@tamarackbrewing.com>",
         "date": "Thu, 4 Sep 2026 10:12", "subject": f"Your PO #{cancel['po']} - line change",
         "body": (f"Hi Leila,\n\nThe manufacturer has discontinued {cancel['desc']} ({cancel['item']}). We have cancelled "
                  f"line {cancel['line']} of your PO #{cancel['po']} ({cancel['qty']} {cancel['uom']}). The rest of the "
                  "order is unaffected.\n\nSorry for the trouble.")},
        {"from": f"Orders <orders@{short['vendor'].lower().replace(' ', '')}.com>", "to": "Leila Haddad <leila@tamarackbrewing.com>",
         "date": "Mon, 8 Sep 2026 15:40", "subject": f"PO {short['po']} backorder",
         "body": (f"Leila - we could only ship {short_got} of the {short['qty']} boxes of {short['desc'].lower()} on "
                  f"PO {short['po']}. The balance is backordered until December, so we have closed it out on our side. "
                  "Place a new order when you want them.")},
        {"from": "Leila Haddad <leila@tamarackbrewing.com>", "to": "you", "date": "Wed, 10 Sep 2026 08:05",
         "subject": "FW: PO changes - open PO list please",
         "body": ("Forwarding the two vendor emails above. Both of those are done as far as we are concerned - we are "
                  "not waiting on anything more from those lines.\n\n"
                  "Can you work out what is actually still coming on our open POs? The PO report doesn't know about "
                  "receiving, the dock log does. The dock tablet counts eaches, so I want every quantity in eaches. "
                  "When something gets sent back to the vendor it's on the log as a Return, and the vendor owes us "
                  "that quantity again.\n\n"
                  "Columns: PO line (as it is on the PO report, like 4461-01), item, ordered, received, open, flag. "
                  "One row for each line that still has something to come. If we got more than we ordered, list "
                  "the line too with open as 0 and OVER in the flag so I can call the vendor; otherwise leave the "
                  "flag blank.")}])

    rows = [[o["ref"], o["item"], o["ordered"], o["received"], o["open"], o["flag"]] for o in d["out"]]
    write_csv(os.path.join(ref, "open_po_lines.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "open_po_lines.csv"), HEADER, rows)
    write_json(os.path.join(ref, "notes.json"), {"plan": plan, "cancelled": cancel["ref"], "short_closed": short["ref"],
                                                  "boxed_logged": d["boxed_logged"]})

    partial_box = [x["ref"] for x in lines if plan[x["ref"]] == "partial" and x["uom"] == "BX"]
    partial_ea = [x["ref"] for x in lines if plan[x["ref"]] == "partial" and x["uom"] == "EA"]
    rtv = [x["ref"] for x in lines if plan[x["ref"]] == "rtv"]
    over = [o["ref"] for o in d["out"] if o["flag"]]
    write_task_yaml(HERE, {
        "id": "open-purchase-orders", "track": "desk", "category": "spreadsheet",
        "title": "What is still coming on our purchase orders",
        "ask": ("Leila needs to know what is still coming on our open purchase orders. Check the PO report against "
                "the dock log and save open_po_lines.csv; her email has the vendor changes and how she wants it.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the PO report orders cartons, lids, cans and glasses in boxes (BX) while the dock log counts eaches; "
            "without the item master's units per box a 6-box order looks like it was over-received by the first "
            "250-each delivery (checks: open quantity per line; lines still open)",
            "one receiver logs some deliveries in boxes ('BX', 'box', 'bx') on the same lines as eaches, so the unit "
            "column has to be read row by row (check: open quantity per line)",
            "most open lines were received in two or three partial deliveries on different days (check: open quantity per line)",
            "three lines were over-received (an extra box on the pallet, a few extra bags); they stay on the list with "
            "open 0 and OVER in the flag, not a negative open quantity (check: over-receipt flag)",
            "one vendor cancelled a line (never received) and another short-closed a half-delivered line; both are in "
            "forwarded emails that name the PO in the vendor's words, and both lines must drop off the list "
            "(check: lines still open)",
            "a return to vendor is logged with a positive quantity and Type=Return; it reopens that quantity instead "
            "of adding to what was received (check: open quantity per line)",
            "the log writes the PO line four ways ('4461-02', 'PO 4461-2', '4461/2', 'PO#4461 ln 2') and still holds "
            "receipts for two closed July POs that are not on the report (check: open quantity per line)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "open_po_lines.csv", "columns": HEADER},
            {"type": "csv_set_equal", "name": "lines still open", "path": "open_po_lines.csv", "column": "po_line",
             "ref": "open_po_lines.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "open_po_lines.csv", "equals_ref": "open_po_lines.csv"},
            {"type": "csv_values_match", "name": "open quantity per line", "path": "open_po_lines.csv",
             "ref": "open_po_lines.csv", "key": "po_line", "columns": ["ordered", "received", "open"], "numeric": True,
             "tolerance": 0, "min_accuracy": 1.0, "must_match_keys": partial_box + partial_ea[:1] + rtv},
            {"type": "csv_values_match", "name": "over-receipt flag", "path": "open_po_lines.csv", "ref": "open_po_lines.csv",
             "key": "po_line", "columns": ["flag"], "min_accuracy": 1.0, "must_match_keys": over},
        ],
    })
    print(f"seed={seed} lines={len(lines)} open={len(d['out'])} over={over} plan-counts",
          {k: sum(1 for v in plan.values() if v == k) for k in set(plan.values())})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
