#!/usr/bin/env python3
"""wide-to-long-sales: a candle maker's by-month wholesale sales report reshaped into a planning tool's long upload.

    python gen.py [--seed N] [--naive DIR]

Business: Emberline Candle Works sells candles wholesale to gift shops. The owner keeps a QuickBooks
"Sales by Customer Summary" by month (customers down the side, fourteen months across). The new demand
planning tool, Stockcast, wants one row per customer per month.

Traps (each caught by a check, see task.yaml):
  * the year sits only in a merged row above the month names (2025 over Jul-Dec, 2026 over Jan-Aug), and
    "Jul" and "Aug" each appear twice                               (checks: one row per customer-month; customer code and month)
  * blank cells are months with no sales and must be skipped, not uploaded as zero rows (checks: row count; ids)
  * the TOTAL column, the per-region subtotal rows and the grand TOTAL row are not customers (check: ids)
  * a few months are net returns and stay negative                  (check: net sales)
  * last year's upload (through June 2025, already in Stockcast) sits in the folder (check: ids)
"""
from __future__ import annotations
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MONTHS = [(2025, m) for m in range(7, 13)] + [(2026, m) for m in range(1, 9)]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
REGIONS = ["Northeast", "Mid-Atlantic", "Midwest", "West"]
SHOPS = ["Salt & Sage Mercantile", "The Linden Shop", "Hearth and Hollow", "Birchbark Gifts", "Main Street Emporium",
         "Wick & Willow", "Northlight Home", "Copper Kettle Goods", "Juniper & Jade", "The Paper Lantern",
         "Harbor Street Market", "Ferncliff General", "Maple Row Boutique", "Driftwood & Daisy", "Oak & Ember Home",
         "Little River Supply", "Blue Door Gifts", "Honeycomb Collective", "Rosemary Lane", "Stonewall Mercantile",
         "Tansy & Thyme", "Wildflower Trading Co", "Lakehouse Living", "Granary Goods"]
HEADER = ["Record ID", "Customer Code", "Month", "Net Sales"]


def build(seed: int) -> dict:
    r = rng(seed)
    shops = r.sample(SHOPS, 22)
    customers = []
    codes = r.sample(range(1010, 1990), len(shops))
    for i, name in enumerate(shops):
        region = REGIONS[i % len(REGIONS)]
        opened = r.choice([0] * 5 + [2, 4, 7])          # some accounts only start buying partway through
        base = money(r, 180, 1400, cents=False)
        cells = {}
        for k, ym in enumerate(MONTHS):
            if k < opened or r.random() < 0.28:
                continue
            cells[ym] = round(base * r.uniform(0.35, 1.6) + r.choice([0, 0.5, 0.25]), 2)
        customers.append({"code": f"EMB-{codes[i]}", "name": name, "region": region, "cells": cells})
    # net returns: three months where credits beat the invoices
    neg = r.sample([(c, ym) for c in customers for ym in c["cells"]], 3)
    for c, ym in neg:
        c["cells"][ym] = -round(r.uniform(40, 260), 2)
    customers.sort(key=lambda c: (REGIONS.index(c["region"]), c["name"]))
    rows = []
    for c in customers:
        for ym in MONTHS:
            if ym in c["cells"]:
                rows.append({"id": f"{c['code']}-{ym[0]}{ym[1]:02d}", "code": c["code"], "month": f"{ym[0]}-{ym[1]:02d}",
                             "amt": c["cells"][ym]})
    return {"customers": customers, "rows": rows, "neg": [f"{c['code']}-{ym[0]}{ym[1]:02d}" for c, ym in neg]}


def acceptable(d: dict) -> bool:
    # both Augusts must carry sales for several customers so the duplicate header matters
    aug25 = sum(1 for c in d["customers"] if (2025, 8) in c["cells"])
    aug26 = sum(1 for c in d["customers"] if (2026, 8) in c["cells"])
    return aug25 >= 8 and aug26 >= 8 and len({x.split("-")[1] for x in d["neg"]}) == 3


def write_report(path: str, d: dict) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales by Customer"
    ncol = 2 + len(MONTHS) + 1
    ws.cell(row=1, column=1, value="Emberline Candle Works").font = Font(bold=True, size=13)
    ws.cell(row=2, column=1, value="Sales by Customer Summary")
    ws.cell(row=3, column=1, value="July 2025 - August 2026")
    ws.cell(row=4, column=3, value=2025).font = Font(bold=True)
    ws.merge_cells(start_row=4, start_column=3, end_row=4, end_column=8)
    ws.cell(row=4, column=9, value=2026).font = Font(bold=True)
    ws.merge_cells(start_row=4, start_column=9, end_row=4, end_column=16)
    ws.cell(row=4, column=3).alignment = Alignment(horizontal="center")
    ws.cell(row=4, column=9).alignment = Alignment(horizontal="center")
    for j, h in enumerate(["Code", "Customer"] + [MON[m - 1] for _, m in MONTHS] + ["TOTAL"], 1):
        ws.cell(row=5, column=j, value=h).font = Font(bold=True)
    row = 6
    grand = [0.0] * len(MONTHS)
    for region in REGIONS:
        ws.cell(row=row, column=2, value=region).font = Font(bold=True)
        row += 1
        sub = [0.0] * len(MONTHS)
        for c in [c for c in d["customers"] if c["region"] == region]:
            ws.cell(row=row, column=1, value=c["code"])
            ws.cell(row=row, column=2, value=c["name"])
            for k, ym in enumerate(MONTHS):
                if ym in c["cells"]:
                    ws.cell(row=row, column=3 + k, value=c["cells"][ym]).number_format = "#,##0.00"
                    sub[k] += c["cells"][ym]
            ws.cell(row=row, column=ncol, value=round(sum(c["cells"].values()), 2)).number_format = "#,##0.00"
            row += 1
        ws.cell(row=row, column=2, value=f"Total {region}").font = Font(bold=True)
        for k in range(len(MONTHS)):
            if sub[k]:
                ws.cell(row=row, column=3 + k, value=round(sub[k], 2)).number_format = "#,##0.00"
            grand[k] += sub[k]
        ws.cell(row=row, column=ncol, value=round(sum(sub), 2)).number_format = "#,##0.00"
        row += 1
    ws.cell(row=row, column=2, value="TOTAL").font = Font(bold=True)
    for k in range(len(MONTHS)):
        ws.cell(row=row, column=3 + k, value=round(grand[k], 2)).number_format = "#,##0.00"
    ws.cell(row=row, column=ncol, value=round(sum(grand), 2)).number_format = "#,##0.00"
    ws.column_dimensions["B"].width = 26
    ws.freeze_panes = "C6"
    from datetime import datetime as _dt
    wb.properties.created = _dt(2026, 1, 15, 9); wb.properties.modified = _dt(2026, 1, 15, 9)
    wb.properties.creator = "QuickBooks"; wb.properties.lastModifiedBy = "QuickBooks"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb.save(path)
    freeze_zip(path)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 7)
    write_report(os.path.join(ws, "sales_by_customer_by_month.xlsx"), d)
    write_csv(os.path.join(ws, "stockcast_upload_template.csv"), HEADER,
              [["SAMPLE-01-202401", "SAMPLE-01", "2024-01", "1520.00"], ["SAMPLE-01-202403", "SAMPLE-01", "2024-03", "-75.50"]])
    # last year's upload: already loaded, a distractor in the right shape
    old = []
    for c in d["customers"][:14]:
        for m in range(1, 7):
            if r.random() < 0.65:
                old.append([f"{c['code']}-2025{m:02d}", c["code"], f"2025-{m:02d}", f"{money(r, 150, 1500):.2f}"])
    write_csv(os.path.join(ws, "stockcast_upload_2025-06.csv"), HEADER, old)
    write_text(os.path.join(ws, "stockcast_upload_notes.txt"),
               "Stockcast - sales history upload (from our onboarding call, 2 Sept)\n"
               "\n"
               "Stockcast already has everything through June 2025 - that went in last summer\n"
               "(stockcast_upload_2025-06.csv). This upload is July 2025 onwards, straight from the\n"
               "by-month sales report.\n"
               "\n"
               "Use the template columns in that order. One row per customer per calendar month.\n"
               "\n"
               "  Record ID      customer code, a dash, then year and month run together:\n"
               "                 EMB-1234-202510 for October 2025. Stockcast uses it to update a month\n"
               "                 instead of adding it twice if we upload again.\n"
               "  Customer Code  the EMB- code from the report\n"
               "  Month          YYYY-MM\n"
               "  Net Sales      plain number, two decimals, no $ or commas. A month where returns beat\n"
               "                 sales goes in negative.\n"
               "\n"
               "Only months where the customer actually had sales. Stockcast reads a missing month as zero,\n"
               "so do not add rows of 0 for the empty cells. No total or subtotal lines - it only wants\n"
               "customers.\n")

    rows = [[x["id"], x["code"], x["month"], f"{x['amt']:.2f}"] for x in d["rows"]]
    write_csv(os.path.join(ref, "sales_long.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "sales_long.csv"), HEADER, rows)
    jul_dec = [x["id"] for x in d["rows"] if x["month"].startswith("2025")]
    aug25 = [x["id"] for x in d["rows"] if x["month"] == "2025-08"][:3]
    aug26 = [x["id"] for x in d["rows"] if x["month"] == "2026-08"][:3]
    dec_jan = [x["id"] for x in d["rows"] if x["month"] in ("2025-12", "2026-01")][:4]
    month_keys = sorted(set(aug25 + aug26 + dec_jan + jul_dec[:2]))
    write_json(os.path.join(ref, "notes.json"), {"rows": len(rows), "negative_ids": d["neg"], "month_pins": month_keys})

    write_task_yaml(HERE, {
        "id": "wide-to-long-sales", "track": "desk", "category": "reformatting",
        "title": "Reshape the by-month sales report for the planning tool upload",
        "ask": ("We're loading our wholesale sales history into Stockcast. Can you turn the by-month sales report into "
                "their upload format and save it as sales_long.csv? Their template and my notes from the onboarding "
                "call are in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the month header row says only Jul..Dec, Jan..Aug; the year sits in a merged row above (2025 over "
            "Jul-Dec, 2026 over Jan-Aug), so a reader sees the year once per merge and 'Jul' and 'Aug' each appear "
            "twice; stamping one year on every column, or letting the second Jul/Aug overwrite the first, moves or "
            "loses rows (checks: one row per customer-month; customer code and month)",
            "blank cells are months with no sales; melting the grid without dropping them adds a zero row for "
            f"every empty month (checks: row count, {len(d['rows'])} rows; one row per customer-month)",
            "the report carries a TOTAL column, a subtotal row per region (Total Northeast ...) and a grand TOTAL "
            "row with no customer code; melting them uploads fake customers and a TOTAL month "
            "(check: one row per customer-month)",
            "three months are net returns written as negative amounts and must stay negative "
            "(check: net sales)",
            "stockcast_upload_2025-06.csv is last year's upload in exactly the target shape; the notes say it is "
            "already loaded, so appending it adds Jan-Jun 2025 rows (checks: one row per customer-month; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Stockcast template columns, exact order", "path": "sales_long.csv",
             "columns": HEADER, "exact": True},
            {"type": "csv_set_equal", "name": "one row per customer-month", "path": "sales_long.csv", "column": "Record ID",
             "ref": "sales_long.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "sales_long.csv", "equals_ref": "sales_long.csv"},
            {"type": "csv_values_match", "name": "customer code and month", "path": "sales_long.csv", "ref": "sales_long.csv",
             "key": "Record ID", "columns": ["Customer Code", "Month"], "min_accuracy": 1.0, "must_match_keys": month_keys},
            {"type": "csv_values_match", "name": "net sales", "path": "sales_long.csv", "ref": "sales_long.csv",
             "key": "Record ID", "columns": ["Net Sales"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0,
             "must_match_keys": d["neg"]},
        ],
    })
    print(f"seed={seed} customers={len(d['customers'])} rows={len(rows)} neg={d['neg']}")


def write_naive(d: dict, out: str) -> None:
    """The obvious melt: month names read with the first year label (2025) for every column, the second Aug
    overwriting the first, the TOTAL column and subtotal rows kept, blanks skipped."""
    os.makedirs(out, exist_ok=True)
    rows = {}
    for c in d["customers"]:
        for ym in MONTHS:
            if ym in c["cells"]:
                key = f"{c['code']}-2025{ym[1]:02d}"
                rows[key] = [key, c["code"], f"2025-{ym[1]:02d}", f"{c['cells'][ym]:.2f}"]
        rows[f"{c['code']}-TOTAL"] = [f"{c['code']}-TOTAL", c["code"], "TOTAL", f"{sum(c['cells'].values()):.2f}"]
    write_csv(os.path.join(out, "sales_long.csv"), HEADER, list(rows.values()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(200):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
