#!/usr/bin/env python3
"""quarterly-sales-report: a tea wholesaler's order lines and refunds to a Q3 workbook by product and a memo.

    python gen.py [--seed N]

Business: Thistle Leaf Tea Co. sells 1 kg bags of loose tea to cafes and restaurants through a wholesale portal
that syncs orders into the warehouse system in import batches. Refunds are issued from the payments side and
exported separately. The partners want the quarter by product, month by month.

Traps (each caught by a check, see task.yaml):
  * the portal retried one August sync and pushed a whole import batch twice under new order numbers, so an
    order-number dedupe finds nothing                           (checks: Assam Breakfast August; Q3 net total; memo names the batch)
  * Yunnan Gold was renamed Golden Yunnan on 10 August with a new SKU; the catalog carries the old SKU in a
    note, and the quarter must come out as one product           (checks: Golden Yunnan quarter; memo names the rename)
  * refunds are a separate export with positive amounts; they come off the product and month they were issued,
    including a July refund on a June order and refunds quoting the old Yunnan SKU
                                                                 (checks: Masala Chai September; Q3 net total)
  * line totals are "$1,234.00" text and the order export carries a BOM and CRLF endings (check: Q3 net total)
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

Q_START, Q_END = date(2026, 7, 1), date(2026, 9, 30)
MONTHS = ["July", "August", "September"]        # text keys no criteria parser reads as a date
RENAME_DATE = date(2026, 8, 10)
DUP_DAY = date(2026, 8, 19)
# sku, name, price per 1 kg bag, weight
PRODUCTS = [
    ("TL-AB-1", "Assam Breakfast", 38.00, 3.0),
    ("TL-EG-1", "Earl Grey Cream", 44.00, 2.6),
    ("TL-MC-1", "Masala Chai", 41.00, 1.6),
    ("TL-GY-1", "Golden Yunnan", 58.00, 1.3),
    ("TL-SK-1", "Sencha Kagoshima", 62.00, 0.9),
    ("TL-CB-1", "Chamomile Blossom", 36.00, 0.8),
]
OLD_SKU, OLD_NAME, NEW_SKU, NEW_NAME = "TL-YG-1", "Yunnan Gold", "TL-GY-1", "Golden Yunnan"
ACCOUNTS = ["Juniper Street Cafe", "Ellington Bakeries", "Blue Heron Consulting", "Larkspur Yoga", "Uptown Fitness",
            "Wren & Sparrow Bookshop", "Harbor Light Marine", "Driftwood Studio", "Ivy Lane Florist", "Tamarack Brewing",
            "Kestrel Analytics", "Riverbend Physio", "Saltmarsh Kayaks", "Glassworks Optical", "Meridian Title",
            "Zephyr Bike Works", "Fernbrook Montessori", "Umber Ceramics"]
REASONS = ["Stale - past best-by date", "Wrong blend shipped", "Damaged in transit", "Short shipped", "Customer complaint"]


def mkey(d: date) -> str:
    return {7: "July", 8: "August", 9: "September"}[d.month]


def build(seed: int) -> dict:
    r = rng(seed)
    price = {p[0]: p[2] for p in PRODUCTS}
    price[OLD_SKU] = price[NEW_SKU]
    lines = []      # {order, date, account, batch, sku, name, bags, price, total, dup}
    batches = []    # (batch_id, date, [orders])
    order_no = 58200
    d = Q_START
    while d <= Q_END:
        if d.weekday() < 6:
            n_batches = 2 if (d.weekday() in (0, 3) and d != DUP_DAY) else 1
            for bi in range(n_batches):
                bid = f"B{d.month:02d}{d.day:02d}-{bi + 1}"
                orders = []
                for _ in range(r.randint(2, 5)):
                    order_no += 1
                    acct = r.choice(ACCOUNTS)
                    skus, pool = [], list(PRODUCTS)
                    for _ in range(r.choice([1, 1, 2, 2, 3])):       # weighted, without replacement
                        p = r.choices(pool, weights=[q[3] for q in pool])[0]
                        skus.append(p); pool.remove(p)
                    for p in skus:
                        sku, name = p[0], p[1]
                        if sku == NEW_SKU and d < RENAME_DATE:
                            sku, name = OLD_SKU, OLD_NAME
                        bags = r.choice([2, 3, 4, 5, 6, 8, 10, 12])
                        ln = {"order": f"W-{order_no}", "date": d, "account": acct, "batch": bid, "sku": sku,
                              "name": name, "bags": bags, "price": price[sku], "total": round(bags * price[sku], 2),
                              "dup": False}
                        lines.append(ln); orders.append(ln)
                batches.append((bid, d, orders))
            if d == DUP_DAY:   # the retry: the same orders again under the next batch id and fresh order numbers
                orig = [b for b in batches if b[0] == f"B{d.month:02d}{d.day:02d}-1"][0]
                renum = {}
                for ln in orig[2]:
                    if ln["order"] not in renum:
                        order_no += 1
                        renum[ln["order"]] = f"W-{order_no}"
                    lines.append({**ln, "order": renum[ln["order"]], "batch": f"B{d.month:02d}{d.day:02d}-2", "dup": True})
        d += timedelta(days=1)

    # refunds: line-level, issued a few days after the order; one July refund on a June order
    refunds = []
    real = [ln for ln in lines if not ln["dup"]]
    picks = r.sample([ln for ln in real if ln["date"] <= date(2026, 9, 24)], 9)
    forced_ch_sep = [ln for ln in real if ln["sku"] == "TL-MC-1" and date(2026, 9, 1) <= ln["date"] <= date(2026, 9, 22)]
    forced_old_yunnan = [ln for ln in real if ln["sku"] == OLD_SKU and ln["date"] >= date(2026, 7, 28)]
    if forced_ch_sep:
        picks.append(r.choice(forced_ch_sep))
    if forced_old_yunnan:
        picks.append(r.choice(forced_old_yunnan))
    seen = set()
    for ln in picks:
        if id(ln) in seen:
            continue
        seen.add(id(ln))
        rd = ln["date"] + timedelta(days=r.randint(2, 9))
        if ln["sku"] == OLD_SKU:
            rd = max(rd, RENAME_DATE + timedelta(days=r.randint(3, 9)))
        bags = r.randint(max(1, ln["bags"] // 3), ln["bags"])
        refunds.append({"date": min(rd, Q_END), "order": ln["order"], "sku": ln["sku"], "bags": bags,
                        "amount": round(bags * ln["price"], 2), "reason": r.choice(REASONS)})
    refunds.append({"date": date(2026, 7, 2), "order": "W-58137", "sku": "TL-AB-1", "bags": 4, "amount": round(4 * price["TL-AB-1"], 2),
                    "reason": "Damaged in transit"})
    refunds.sort(key=lambda x: (x["date"], x["order"]))

    # ---- truth ----
    def product_of(sku: str) -> str:
        return NEW_NAME if sku in (OLD_SKU, NEW_SKU) else {p[0]: p[1] for p in PRODUCTS}[sku]

    names = [p[1] for p in PRODUCTS]
    gross = {(n, m): 0.0 for n in names for m in MONTHS}
    bags = {(n, m): 0 for n in names for m in MONTHS}
    refund = {(n, m): 0.0 for n in names for m in MONTHS}
    dup_amt = {(n, m): 0.0 for n in names for m in MONTHS}
    for ln in lines:
        k = (product_of(ln["sku"]), mkey(ln["date"]))
        if ln["dup"]:
            dup_amt[k] += ln["total"]
            continue
        gross[k] += ln["total"]; bags[k] += ln["bags"]
    for x in refunds:
        refund[(product_of(x["sku"]), mkey(x["date"]))] += x["amount"]
    net = {k: round(gross[k] - refund[k], 2) for k in gross}
    prod_tot = {n: round(sum(net[(n, m)] for m in MONTHS), 2) for n in names}
    month_tot = {m: round(sum(net[(n, m)] for n in names), 2) for m in MONTHS}
    grand = round(sum(prod_tot.values()), 2)
    dup_batch = f"B{DUP_DAY.month:02d}{DUP_DAY.day:02d}-2"
    return {"lines": lines, "refunds": refunds, "net": net, "gross": gross, "refund": refund, "dup_amt": dup_amt,
            "bags": bags, "prod_tot": prod_tot, "month_tot": month_tot, "grand": grand, "names": names,
            "dup_batch": dup_batch, "orig_batch": dup_batch[:-1] + "1", "product_of": product_of,
            "dup_lines": sum(1 for ln in lines if ln["dup"]), "dup_total": round(sum(ln["total"] for ln in lines if ln["dup"]), 2),
            "refund_total": round(sum(x["amount"] for x in refunds if Q_START <= x["date"] <= Q_END), 2)}


def acceptable(d: dict) -> bool:
    net, names = d["net"], d["names"]
    he_aug, ch_sep = ("Assam Breakfast", "August"), ("Masala Chai", "September")
    if d["dup_amt"][he_aug] < 0.03 * net[he_aug] or d["refund"][ch_sep] < 0.03 * net[ch_sep]:
        return False
    # the renamed tea's quarter is well above either name's share alone
    old = sum(ln["total"] for ln in d["lines"] if ln["sku"] == OLD_SKU and not ln["dup"])
    new = sum(ln["total"] for ln in d["lines"] if ln["sku"] == NEW_SKU and not ln["dup"])
    tot = d["prod_tot"][NEW_NAME]
    if not (0.3 * tot < old < 0.7 * tot and 0.3 * tot < new < 0.7 * tot):
        return False
    if not any(x["sku"] == OLD_SKU for x in d["refunds"]):
        return False
    # every pinned figure is unique on its row
    for n in names:
        vals = [net[(n, m)] for m in MONTHS] + [d["prod_tot"][n]]
        for i, v in enumerate(vals):
            if any(abs(v - w) <= 0.01 * abs(v) for j, w in enumerate(vals) if j != i):
                return False
    vals = list(d["month_tot"].values()) + [d["grand"]]
    if any(abs(a - b) <= 0.01 * a for i, a in enumerate(vals) for j, b in enumerate(vals) if i != j):
        return False
    return 9 <= len(d["refunds"]) <= 13 and d["dup_lines"] >= 6


# --------------------------------------------------------------------------- deliverables

def report_sheets(d: dict) -> dict:
    data = []
    for ln in d["lines"]:
        if ln["dup"]:
            continue
        data.append([d["product_of"](ln["sku"]), mkey(ln["date"]), ln["total"], ln["bags"], ln["order"], ln["sku"], "sale"])
    for x in d["refunds"]:
        if Q_START <= x["date"] <= Q_END:
            data.append([d["product_of"](x["sku"]), mkey(x["date"]), -x["amount"], 0, x["order"], x["sku"], "refund"])
    n = len(data) + 1
    rows = []
    for i, name in enumerate(d["names"], start=2):
        rows.append([name] + [f"=ROUND(SUMIFS(Data!$C$2:$C${n},Data!$A$2:$A${n},$A{i},Data!$B$2:$B${n},{c}$1),2)" for c in "BCD"]
                    + [f"=SUM(B{i}:D{i})", f"=SUMIFS(Data!$D$2:$D${n},Data!$A$2:$A${n},$A{i})"])
    last = len(d["names"]) + 1
    rows.append(["Total"] + [f"=SUM({c}2:{c}{last})" for c in "BCDEF"])
    rows.append([])
    rows.append([f"Net of refunds in the month issued. Import batch {d['dup_batch']} repeats {d['orig_batch']} and is left out. "
                 f"{OLD_NAME} ({OLD_SKU}) is reported as {NEW_NAME}."])
    return {"Q3 by product": {"header": ["Product", *MONTHS, "Q3 net revenue", "Bags sold"], "rows": rows,
                              "widths": {"A": 22, "E": 16}},
            "Data": {"header": ["product", "month", "net amount", "bags", "order", "sku", "kind"], "rows": data}}


def memo_text(d: dict) -> str:
    pt, net = d["prod_tot"], d["net"]
    top = max(d["names"], key=lambda n: pt[n])
    return f"""# Q3 2026 wholesale sales

Net wholesale revenue for July to September was ${d['grand']:,.2f} after ${d['refund_total']:,.2f} of refunds.
{top} was the biggest seller at ${pt[top]:,.2f}.

Things to know:

- Import batch {d['dup_batch']} on 19 August is a duplicate of batch {d['orig_batch']}: the portal retried the sync and pushed the same {d['dup_lines']} order lines again under new order numbers (${d['dup_total']:,.2f}). They are left out.
- {OLD_NAME} was renamed {NEW_NAME} on 10 August and got a new SKU ({OLD_SKU} became {NEW_SKU}). The report shows it as one product, ${pt[NEW_NAME]:,.2f} for the quarter.
- Refunds are taken off the month they were issued, so the 2 July refund on a June order reduces July.
"""



def cent_tolerant(spec: dict) -> dict:
    """Figures computed from exact source data tie to the cent: every workbook pin gets a tolerance under 1.00."""
    for c in spec["checks"]:
        if c["type"] == "xlsx_value_present" and not c.get("rounding"):
            exp = abs(float(c["expected"]))
            c["rel_tol"] = min(float(c.get("rel_tol", 0.005)), float(f"{0.9 / max(exp, 1.0):.2g}"))
    return spec


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)

    # ---- workspace ----
    write_csv(os.path.join(ws, "portal_order_lines_2026-07-01_to_2026-09-30.csv"),
              ["Order #", "Order Date", "Account", "Import Batch", "SKU", "Product", "Bags", "Unit Price", "Line Total"],
              [[ln["order"], ln["date"].strftime("%m/%d/%Y"), ln["account"], ln["batch"], ln["sku"], f"{ln['name']} 1kg",
                ln["bags"], money_str(ln["price"], 1), money_str(ln["total"], 1)]
               for ln in sorted(d["lines"], key=lambda x: (x["date"], x["batch"], x["order"]))],
              bom=True, crlf=True)
    write_csv(os.path.join(ws, "refunds_export_q3.csv"),
              ["Refund Date", "Order", "SKU", "Bags", "Refund Amount", "Reason"],
              [[x["date"].isoformat(), x["order"], x["sku"], x["bags"], f"{x['amount']:.2f}", x["reason"]] for x in d["refunds"]])
    cat = [[p[0], f"{p[1]} 1kg", "Tea", p[2], "Active", f"Renamed from {OLD_NAME} 10 Aug 2026 (old SKU {OLD_SKU})" if p[0] == NEW_SKU else ""]
           for p in PRODUCTS]
    cat += [["TL-CT-50", "Cold Brew Tea Pouches 50x", "Iced tea", 29.00, "Active", "Retail only"],
            ["TL-DS-1", "Darjeeling Second Flush 1kg", "Tea", 96.00, "Discontinued", "Last lot sold May 2026"]]
    write_xlsx(os.path.join(ws, "product_catalog.xlsx"), {"Catalog": {
        "merged_title": "Thistle Leaf Tea Co. - wholesale catalog", "header": ["SKU", "Product", "Category", "Price per bag", "Status", "Notes"],
        "rows": cat, "widths": {"B": 24, "F": 48}}}, creator="Thistle Leaf")
    write_email_thread(os.path.join(ws, "email_from_theo.txt"), [
        {"from": "Theo Lindqvist <theo@thistleleaftea.com>", "to": "you", "date": "Mon, 5 Oct 2026 08:10", "subject": "Q3 numbers",
         "body": ("Partners meeting is Thursday. Can you do the wholesale quarter by product and by month from the portal "
                  "export - revenue net of refunds, refunds coming off the month we issued them - and a short memo with "
                  "anything they should know?")},
        {"from": "Theo Lindqvist <theo@thistleleaftea.com>", "to": "you", "date": "Mon, 5 Oct 2026 08:26", "subject": "RE: Q3 numbers",
         "body": ("One more thing. Portal support closed our ticket from August - they said a sync job timed out one "
                  "afternoon and retried, and 'some orders may have been imported more than once'. They never told me "
                  "which. If you find them, leave them out and tell me in the memo.")}])

    # ---- reference ----
    write_csv(os.path.join(ref, "net_by_product_month.csv"), ["product", "month", "net_revenue", "gross", "refunds"],
              [[n, m, f"{d['net'][(n, m)]:.2f}", f"{d['gross'][(n, m)]:.2f}", f"{d['refund'][(n, m)]:.2f}"] for n in d["names"] for m in MONTHS])
    write_json(os.path.join(ref, "notes.json"), {"duplicate_batch": d["dup_batch"], "original_batch": d["orig_batch"],
                                                  "duplicate_lines": d["dup_lines"], "duplicate_total": d["dup_total"],
                                                  "renamed": {"old": [OLD_SKU, OLD_NAME], "new": [NEW_SKU, NEW_NAME], "date": RENAME_DATE.isoformat()},
                                                  "product_totals": d["prod_tot"], "month_totals": d["month_tot"], "grand": d["grand"],
                                                  "refunds_in_q3": d["refund_total"]})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "q_report.xlsx"), report_sheets(d), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    net = d["net"]
    batch_re = rf"\b{d['orig_batch'][:-2]}-?[12]\b"
    write_task_yaml(HERE, cent_tolerant({
        "id": "quarterly-sales-report", "track": "desk", "category": "reports",
        "title": "Q3 wholesale sales by product, with the odd things called out",
        "ask": ("Theo needs the Q3 wholesale numbers by product, month by month, for the partners meeting. Build q_report.xlsx "
                "with live formulas and write memo.md with anything they should know - his emails have the details.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"a timed-out sync on 19 August retried and pushed import batch {d['orig_batch']} again as {d['dup_batch']}: the same "
            f"accounts, SKUs, bags and totals under new order numbers, so deduplicating on Order # finds nothing "
            f"(checks: Assam Breakfast August; Q3 net revenue total; memo names the duplicate batch)",
            f"{OLD_NAME} ({OLD_SKU}) was renamed {NEW_NAME} ({NEW_SKU}) on 10 August; the old SKU only survives in the "
            f"catalog's Notes column, so a pivot on the Product or SKU column splits the quarter into two rows "
            f"(checks: Golden Yunnan quarter; memo names the renamed product)",
            "refunds are a separate export with positive amounts that come off the product and month they were issued; "
            "one is a 2 July refund on a June order and some quote the old Yunnan SKU (checks: Masala Chai September; "
            "Q3 net revenue total)",
            "line totals are '$1,234.00' text and the order export carries a BOM and CRLF endings; the catalog lists a "
            "retail-only and a discontinued product that sold nothing wholesale (check: Q3 net revenue total)",
        ],
        "checks": [
            {"type": "file_exists", "name": "q_report.xlsx exists", "path": "q_report.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "q_report.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "q_report.xlsx"},
            {"type": "xlsx_value_present", "name": "Golden Yunnan quarter (renamed product as one line)", "path": "q_report.xlsx",
             "expected": d["prod_tot"][NEW_NAME], "rel_tol": 0.005, "near_text": "yunnan"},
            {"type": "xlsx_value_present", "name": "Assam Breakfast August (duplicate batch removed)", "path": "q_report.xlsx",
             "expected": net[("Assam Breakfast", "August")], "rel_tol": 0.005, "near_text": "assam"},
            {"type": "xlsx_value_present", "name": "Masala Chai September (net of refunds)", "path": "q_report.xlsx",
             "expected": net[("Masala Chai", "September")], "rel_tol": 0.005, "near_text": "chai"},
            {"type": "xlsx_value_present", "name": "Q3 net revenue total", "path": "q_report.xlsx",
             "expected": d["grand"], "rel_tol": 0.005, "near_text": "total"},
            {"type": "text_numbers_present", "name": "memo carries the Q3 net revenue", "path": "memo.md",
             "numbers": [d["grand"]], "rel_tol": 0.005},
            {"type": "text_sentence_matches", "name": "memo names the duplicate batch", "path": "memo.md",
             "all": [batch_re, r"(duplicat|twice|double|more than once|re-?import|re-?sent|re-?pushed|repeat|retr(y|ied)|again)"]},
            {"type": "text_sentence_matches", "name": "memo names the renamed product", "path": "memo.md",
             "all": [r"\b(yunnan gold|golden yunnan|yunnan)\b",
                     r"(renam|formerly|previously|used to be|new name|now called|same (product|tea|blend)|became|replaced|old sku|tl-yg-1)"]},
        ],
    }))
    print(f"seed={seed} lines={len(d['lines'])} dup_lines={d['dup_lines']} refunds={len(d['refunds'])}")
    print("  product totals:", d["prod_tot"], "grand:", d["grand"])
    print("  Assam Aug", net[("Assam Breakfast", "August")], "dup", round(d["dup_amt"][("Assam Breakfast", "August")], 2),
          "| Chai Sep", net[("Masala Chai", "September")], "refund", d["refund"][("Masala Chai", "September")])


if __name__ == "__main__":
    s = argparse_seed()
    for attempt in range(500):
        if acceptable(build(s * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(s * 1000 + attempt)
