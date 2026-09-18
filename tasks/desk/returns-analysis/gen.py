#!/usr/bin/env python3
"""returns-analysis: a Q2 order export plus a returns export -> return rate per product and a reason breakdown.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * exchanges and store credits are returns for the rate, but only refunds and store credits are refunded dollars;
    the export's amount column carries a value on exchange rows too                 (checks: units returned; refunded dollars)
  * the type column carries eleven spellings of three types ("Refund", "REFUND", "Exch", "Store credit", ...)  (check: refunded dollars)
  * reasons are free text; Mateo's note maps keywords to five buckets                (checks: sizing units; damaged units)
  * one product was renamed on May 1 with the same SKU; both names appear in both files (checks: renamed product sold/returned)
  * the returns export has a two-line preamble, a BOM and "$12.00" text amounts        (check: refunded dollars)
  * a Q1 returns export sits in the folder as a distractor; the ask is Q2 only         (check: total units returned)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))


Q2_START, Q2_END = date(2026, 4, 1), date(2026, 6, 30)
RENAME_DAY = date(2026, 5, 1)
OLD_NAME, NEW_NAME, RENAMED_SKU = "Camp Stove", "Summit Stove", "CS-01"
TYPE_SPELLINGS = {
    "Refund": ["Refund", "refund", "REFUND", "Refund "],
    "Exchange": ["Exchange", "Exch", "exchange", "EXCHANGE"],
    "Store credit": ["Store Credit", "Store credit", "store credit"],
}
# bucket -> free-text reasons; every phrase carries exactly one keyword from the note
REASONS = {
    "Sizing": ["too small", "Too small, need a larger one", "runs large", "didnt fit", "Fit was off", "too tight in the shoulders", "TOO SMALL", "sleeves too short - fit"],
    "Damaged": ["arrived broken", "torn seam", "Damaged in shipping", "zipper broken", "cracked lid", "Broken buckle", "DAMAGED box, item scratched"],
    "Not as described": ["color different from photos", "not as described", "Not what I expected", "lighter than described", "Different color than the picture"],
    "Changed mind": ["changed mind", "no longer needed", "Ordered by mistake", "found it cheaper", "Changed my mind", "duplicate order by mistake"],
    "Wrong item": ["wrong item shipped", "got the wrong size sent", "Received a different item", "sent the wrong color", "WRONG ITEM in the box"],
}
KEYWORDS = {"Sizing": "small, large, fit, tight, short", "Damaged": "broken, torn, damaged, cracked, scratched",
            "Not as described": "described, expected, photos, picture", "Changed mind": "mind, needed, mistake, cheaper",
            "Wrong item": "wrong, different item"}


def build(seed: int) -> dict:
    r = rng(seed)
    products = [(n, s, p) for n, s, p in PRODUCTS["retail"]]
    exchange_heavy_sku = "TJ-M-BLU"                     # the jacket: exchanges for size
    # ---- Q2 order lines
    orders = []
    oid = 30400 + r.randint(0, 99)
    for i in range(760):
        d = day_in(r, Q2_START, Q2_END)
        name, sku, price = r.choice(products)
        qty = r.choice([1, 1, 1, 1, 2, 2, 3])
        shown = name if not (sku == RENAMED_SKU and d >= RENAME_DAY) else NEW_NAME
        orders.append({"order_id": f"ORD-{oid + i}", "date": d, "sku": sku, "product": shown, "qty": qty, "price": price})
    orders.sort(key=lambda o: (o["date"], o["order_id"]))
    sold = {}
    for o in orders:
        sold[o["sku"]] = sold.get(o["sku"], 0) + o["qty"]
    # ---- Q2 returns: each against a Q2 order, dated 3-20 days after the order, inside Q2
    returns = []
    cands = [o for o in orders if o["date"] + timedelta(days=3) <= Q2_END]
    picked = r.sample(cands, 118)
    rma = 7100 + r.randint(0, 50)
    for o in sorted(picked, key=lambda o: o["order_id"]):
        d = min(o["date"] + timedelta(days=r.randint(3, 20)), Q2_END)
        if o["sku"] == exchange_heavy_sku:
            typ = r.choice(["Exchange", "Exchange", "Exchange", "Refund", "Store credit"])
            bucket = r.choice(["Sizing", "Sizing", "Sizing", "Changed mind", "Not as described"])
        else:
            typ = r.choice(["Refund", "Refund", "Refund", "Refund", "Exchange", "Exchange", "Store credit"])
            bucket = r.choice(["Sizing", "Damaged", "Damaged", "Not as described", "Changed mind", "Changed mind", "Wrong item"])
        qty = 1 if o["qty"] == 1 else r.choice([1, 1, o["qty"]])
        shown = o["sku"] != RENAMED_SKU and o["product"] or (NEW_NAME if d >= RENAME_DAY else OLD_NAME)
        returns.append({"rma_id": f"RMA-{rma}", "date": d, "order_id": o["order_id"], "sku": o["sku"], "product": shown,
                        "qty": qty, "type": typ, "type_shown": r.choice(TYPE_SPELLINGS[typ]),
                        "bucket": bucket, "reason": r.choice(REASONS[bucket]), "amount": round(qty * o["price"], 2)})
        rma += r.choice([1, 1, 1, 2])
    returns.sort(key=lambda x: (x["date"], x["rma_id"]))
    # ---- truth aggregates
    per = {}
    for n, s, p in products:
        per[s] = {"sku": s, "product": NEW_NAME if s == RENAMED_SKU else n, "sold": sold.get(s, 0), "returned": 0, "refund_units": 0,
                  "exchange_units": 0, "refunded": 0.0}
    for x in returns:
        a = per[x["sku"]]
        a["returned"] += x["qty"]
        if x["type"] == "Exchange":
            a["exchange_units"] += x["qty"]
        else:
            a["refund_units"] += x["qty"]; a["refunded"] = round(a["refunded"] + x["amount"], 2)
    buckets = {b: 0 for b in REASONS}
    for x in returns:
        buckets[x["bucket"]] += x["qty"]
    # naive variants the checks must distinguish from the truth
    naive_name_sold = sum(o["qty"] for o in orders if o["product"] == NEW_NAME)          # post-rename rows only
    naive_name_ret = sum(x["qty"] for x in returns if x["product"] == NEW_NAME)
    naive_refund_only = sum(x["qty"] for x in returns if x["sku"] == exchange_heavy_sku and x["type"] == "Refund")
    naive_amount_total = round(sum(x["amount"] for x in returns), 2)
    refunded_total = round(sum(a["refunded"] for a in per.values()), 2)
    # ---- Q1 distractor returns (older RMAs, same shape)
    q1 = []
    for i in range(41):
        d = day_in(r, date(2026, 1, 2), date(2026, 3, 31))
        name, sku, price = r.choice(products)
        bucket = r.choice(list(REASONS))
        q1.append({"rma_id": f"RMA-{6800 + i * 2 + r.randint(0, 1)}", "date": d, "order_id": f"ORD-{29000 + r.randint(0, 999)}", "sku": sku,
                   "product": name, "qty": 1, "type_shown": r.choice(TYPE_SPELLINGS[r.choice(list(TYPE_SPELLINGS))]),
                   "reason": r.choice(REASONS[bucket]), "amount": price})
    q1.sort(key=lambda x: (x["date"], x["rma_id"]))
    return {"orders": orders, "returns": returns, "per": per, "buckets": buckets, "q1": q1, "products": products,
            "exchange_heavy_sku": exchange_heavy_sku, "refunded_total": refunded_total,
            "naive": {"name_sold": naive_name_sold, "name_ret": naive_name_ret, "refund_only": naive_refund_only, "amount_total": naive_amount_total}}


def acceptable(d: dict) -> bool:
    """Every checked figure must differ from its naive miscomputation and from the other cells on its row."""
    per, n = d["per"], d["naive"]
    ren, ex = per[RENAMED_SKU], per[d["exchange_heavy_sku"]]
    if n["name_sold"] == ren["sold"] or n["name_ret"] == ren["returned"]: return False
    if n["refund_only"] == ex["returned"] or ex["exchange_units"] == 0: return False
    if abs(n["amount_total"] - d["refunded_total"]) < 0.02 * d["refunded_total"]: return False
    for a in (ren, ex):   # the checked count must not equal another number on the same summary row
        cells = [a["sold"], a["returned"], a["refund_units"], a["exchange_units"], round(a["refunded"])]
        if len(set(cells)) != len(cells): return False
    b = d["buckets"]
    if len(set(b.values())) != len(b) or min(b.values()) < 5: return False
    return True


def emit(seed: int) -> None:
    for attempt in range(300):
        d = build(seed * 1000 + attempt)
        if acceptable(d): break
    else:
        raise SystemExit("no acceptable draw")
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 77)
    # orders export: clean-ish csv, ISO dates
    write_csv(os.path.join(ws, "orders_export_2026-Q2.csv"), ["order_id", "order_date", "sku", "product_name", "qty", "unit_price"],
              [[o["order_id"], o["date"].isoformat(), o["sku"], o["product"], o["qty"], f"{o['price']:.2f}"] for o in d["orders"]])
    # returns export: preamble + BOM + CRLF, US dates, $ amounts
    def ret_rows(items):
        return [[x["rma_id"], date_variant(x["date"], 1), x["order_id"], x["sku"], name_noise(r, x["product"]), x["qty"], x["type_shown"],
                 x["reason"], money_str(x["amount"], 1)] for x in items]
    hdr = ["RMA", "Return Date", "Order", "SKU", "Product", "Qty", "Type", "Reason", "Amount"]
    write_csv(os.path.join(ws, "returns_export_2026-Q2.csv"), hdr, ret_rows(d["returns"]),
              preamble=["Returns report - Granite Peak Outfitters", "Exported 07/02/2026 by RMA module"], bom=True, crlf=True)
    write_csv(os.path.join(ws, "returns_export_2026-Q1.csv"), hdr, ret_rows(d["q1"]),
              preamble=["Returns report - Granite Peak Outfitters", "Exported 04/01/2026 by RMA module"], bom=True, crlf=True)
    kw = "\n".join(f"  {b}: {KEYWORDS[b]}" for b in REASONS)
    write_text(os.path.join(ws, "note_from_mateo.txt"),
               "Return reasons - how we bucket them\n\n"
               "The RMA screen is free text so the reasons are all over the place. Put each one in the bucket whose keyword it contains:\n\n"
               f"{kw}\n\n"
               "Every reason in the export contains one of those words. Count units (the Qty column), not RMAs.\n\n"
               "Two other things. Exchanges and store credits are still returns - the item came back - so they count toward the return rate "
               "along with refunds. But exchanges do not cost us a refund, so when you total refunded dollars use refunds and store credits only, "
               "even though the export prints an amount on every row.\n\n"
               f"Also we renamed {OLD_NAME} to {NEW_NAME} on May 1 (same SKU {RENAMED_SKU}); both names show up in both exports. Report it once, as {NEW_NAME}.\n"
               "Return rate = units returned / units sold in the quarter.\n\n- Mateo\n")
    # ---- reference
    per = [d["per"][s] for _, s, _ in d["products"]]
    write_csv(os.path.join(ref, "per_product.csv"), ["sku", "product", "units_sold", "units_returned", "refund_units", "exchange_units", "return_rate", "refunded_dollars"],
              [[a["sku"], a["product"], a["sold"], a["returned"], a["refund_units"], a["exchange_units"], f"{a['returned'] / a['sold']:.4f}", f"{a['refunded']:.2f}"] for a in per])
    write_csv(os.path.join(ref, "reasons.csv"), ["reason", "units"], [[b, n] for b, n in d["buckets"].items()])
    total_ret = sum(a["returned"] for a in per)
    total_sold = sum(a["sold"] for a in per)
    ex_ = d["per"][d["exchange_heavy_sku"]]
    write_json(os.path.join(ref, "notes.json"), {"refunded_total": d["refunded_total"], "total_units_returned": total_ret,
                                                  "rates": {"total": round(total_ret / total_sold, 4), ex_["product"].lower(): round(ex_["returned"] / ex_["sold"], 4)},
                                                  "total_units_sold": sum(a["sold"] for a in per), "naive": d["naive"]})
    # ---- reference solution workbook (live formulas)
    sales_rows = [[a["sku"], a["product"], a["sold"]] for a in per]
    ret_rows_clean = [[x["rma_id"], x["date"], x["order_id"], x["sku"], d["per"][x["sku"]]["product"], x["qty"], x["type"], x["bucket"],
                       x["amount"] if x["type"] != "Exchange" else 0.0] for x in d["returns"]]
    nR = len(ret_rows_clean) + 1
    F = 3                                  # Summary data starts on row 3 (row 1 merged title, row 2 header)
    summ = []
    for i, a in enumerate(per, start=F):
        summ.append([a["sku"], a["product"],
                     f"=VLOOKUP(A{i},Sales!$A$2:$C${len(per) + 1},3,FALSE)",
                     f"=SUMIF(Returns!$D$2:$D${nR},A{i},Returns!$F$2:$F${nR})",
                     f'=SUMIFS(Returns!$F$2:$F${nR},Returns!$D$2:$D${nR},A{i},Returns!$G$2:$G${nR},"Refund")+SUMIFS(Returns!$F$2:$F${nR},Returns!$D$2:$D${nR},A{i},Returns!$G$2:$G${nR},"Store credit")',
                     f'=SUMIFS(Returns!$F$2:$F${nR},Returns!$D$2:$D${nR},A{i},Returns!$G$2:$G${nR},"Exchange")',
                     f"=IF(C{i}=0,0,ROUND(D{i}/C{i},4))",
                     f"=SUMIF(Returns!$D$2:$D${nR},A{i},Returns!$I$2:$I${nR})"])
    last = F + len(per) - 1; T = last + 1
    summ.append(["Total", "", f"=SUM(C{F}:C{last})", f"=SUM(D{F}:D{last})", f"=SUM(E{F}:E{last})", f"=SUM(F{F}:F{last})", f"=IF(C{T}=0,0,ROUND(D{T}/C{T},4))", f"=SUM(H{F}:H{last})"])
    reasons = [[b, f"=SUMIF(Returns!$H$2:$H${nR},A{i},Returns!$F$2:$F${nR})", f"=IF(Summary!$D${T}=0,0,ROUND(B{i}/Summary!$D${T},4))"]
               for i, b in enumerate(REASONS, start=2)]
    reasons.append(["Total", f"=SUM(B2:B{len(REASONS) + 1})", ""])
    write_xlsx(os.path.join(sol, "returns.xlsx"), {
        "Summary": {"merged_title": "Q2 2026 returns by product (Apr-Jun)", "header": ["SKU", "Product", "Units sold", "Units returned", "Refund units", "Exchange units", "Return rate", "Refunded dollars"],
                    "rows": summ, "number_formats": {"G": "0.0%", "H": "#,##0.00"}, "widths": {"B": 22, "C": 12, "D": 14, "E": 13, "F": 15, "G": 12, "H": 16}},
        "Reasons": {"header": ["Reason", "Units returned", "Share"], "rows": reasons, "number_formats": {"C": "0.0%"}, "widths": {"A": 18, "B": 15}},
        "Sales": {"header": ["sku", "product", "units_sold"], "rows": sales_rows, "widths": {"B": 22}},
        "Returns": {"header": ["rma_id", "return_date", "order_id", "sku", "product", "qty", "type", "reason_bucket", "refund_amount"],
                    "rows": ret_rows_clean, "widths": {"B": 12, "E": 22, "H": 18}},
    }, creator="reference")
    ren, ex = d["per"][RENAMED_SKU], d["per"][d["exchange_heavy_sku"]]
    write_task_yaml(HERE, {
        "id": "returns-analysis", "track": "desk", "category": "reports",
        "title": "Q2 return rate by product and reason",
        "ask": ("Put together a Q2 returns report for me from the order and returns exports in this folder: return rate by product and a breakdown "
                "of why things come back. Mateo's note explains how we bucket the reasons. Save it as returns.xlsx with live formulas.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "exchanges and store credits are returns for the rate, but only refunds and store credits are refunded dollars; the export prints an amount on exchange rows too (checks: units returned for the jacket; return rates, quarter total and the jacket; refunded dollars)",
            'the Type column carries eleven spellings of three types ("Refund", "REFUND", "Exch", "Store credit", ...) (check: refunded dollars)',
            "reasons are free text; the note maps keywords to five buckets (checks: sizing units; damaged units)",
            f"{OLD_NAME} became {NEW_NAME} on May 1 with the same SKU {RENAMED_SKU}; both names appear in both exports (checks: renamed product units sold; renamed product units returned)",
            'the returns export has a two-line preamble, a BOM, CRLF line endings, US dates and "$12.00" text amounts (check: refunded dollars)',
            "a Q1 returns export sits in the folder as a distractor; only Q2 counts (checks: total units returned; return rates, quarter total and the jacket)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "returns.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no formula errors", "path": "returns.xlsx"},
            {"type": "xlsx_value_present", "name": "renamed product units sold", "path": "returns.xlsx", "expected": ren["sold"], "rel_tol": cent_tol(ren["sold"], 0.001), "near_text": NEW_NAME.lower()},
            {"type": "xlsx_value_present", "name": "renamed product units returned", "path": "returns.xlsx", "expected": ren["returned"], "rel_tol": cent_tol(ren["returned"], 0.001), "near_text": NEW_NAME.lower()},
            {"type": "xlsx_value_present", "name": "units returned for the jacket (exchanges count)", "path": "returns.xlsx", "expected": ex["returned"], "rel_tol": cent_tol(ex["returned"], 0.001), "near_text": ex["product"].lower()},
            {"type": "xlsx_value_present", "name": "refunded dollars", "path": "returns.xlsx", "expected": d["refunded_total"], "rel_tol": cent_tol(d["refunded_total"], 0.005), "near_text": "refund"},
            {"type": "xlsx_value_present", "name": "total units returned", "path": "returns.xlsx", "expected": total_ret, "rel_tol": cent_tol(total_ret, 0.001), "near_text": "total"},
            {"type": "custom", "name": "return rates, quarter total and the jacket", "module": "check.py"},
            {"type": "xlsx_value_present", "name": "sizing units", "path": "returns.xlsx", "expected": d["buckets"]["Sizing"], "rel_tol": cent_tol(d["buckets"]["Sizing"], 0.001), "near_text": "sizing"},
            {"type": "xlsx_value_present", "name": "damaged units", "path": "returns.xlsx", "expected": d["buckets"]["Damaged"], "rel_tol": cent_tol(d["buckets"]["Damaged"], 0.001), "near_text": "damaged"},
        ],
    })
    print(f"seed={seed} attempt={attempt} orders={len(d['orders'])} returns={len(d['returns'])} refunded={d['refunded_total']} "
          f"renamed sold/ret={ren['sold']}/{ren['returned']} (naive {d['naive']['name_sold']}/{d['naive']['name_ret']}) "
          f"jacket ret={ex['returned']} (refund-only {d['naive']['refund_only']}) buckets={d['buckets']}")


if __name__ == "__main__":
    emit(argparse_seed())
