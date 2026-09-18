#!/usr/bin/env python3
"""procurement-savings: a craft brewery's quote log and PO export -> negotiated savings per purchasing category.

    python gen.py [--seed N] [--naive DIR]

Business: Tamarack Brewing's buyer logs every supplier quote (and every revised quote) in a workbook; the ERP
exports purchase orders in USD. Finance counts savings as the first quoted price, converted at budget rates,
less the PO price, times the quantity actually ordered.

Traps (each caught by a check, see task.yaml):
  * hop quotes are in EUR and malt quotes in CAD; the PO export is USD, so the quote price must be converted
    at the budget rates in the email before it is compared                       (checks: Hops savings; Malt savings)
  * PO quantities differ from quoted quantities; savings use the quantity ordered (checks: Malt savings; Packaging savings)
  * negotiated quotes carry a revision 2 at a lower price; the baseline is revision 1 (checks: Hops savings; Cleaning savings)
  * two POs were cancelled and still sit in the export                          (check: Packaging savings)
  * one cleaning PO came in above the quote (a surcharge); it counts as negative savings, not zero (check: Cleaning savings)
  * spot buys with no quote reference are not savings; PO export money is "$1,234.50" text behind a preamble and a BOM
                                                                                  (check: total savings)
"""
from __future__ import annotations
import argparse
import os
import sys
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


RATES = {"USD": 1.0, "EUR": 1.08, "CAD": 0.73}
CATS = ["Malt & grain", "Hops", "Packaging", "Cleaning & sanitation", "Lab & QA"]
PINNED = {"Hops": "hops", "Malt & grain": "malt", "Packaging": "packaging", "Cleaning & sanitation": "cleaning"}
# category -> (supplier, currency, [(code, description, uom, price lo, price hi, qty lo, qty hi)])
SUPPLIERS = {
    "Malt & grain": [("Prairie Heritage Malting Ltd.", "CAD", [
        ("MLT-2ROW-55", "2-Row pale malt, 55 lb bag", "bag", 48, 58, 90, 240),
        ("MLT-MUN-55", "Munich malt, 55 lb bag", "bag", 54, 64, 40, 120),
        ("MLT-C60-55", "Crystal 60L malt, 55 lb bag", "bag", 58, 68, 30, 90)])],
    "Hops": [("Hopfenhaus Hallertau GmbH", "EUR", [
        ("HOP-HMF-KG", "Hallertau Mittelfrueh T90 pellets", "kg", 16, 22, 120, 360),
        ("HOP-TET-KG", "Tettnanger T90 pellets", "kg", 15, 21, 100, 300),
        ("HOP-SAZ-KG", "Saaz-type Spalter Select T90 pellets", "kg", 14, 19, 80, 240)])],
    "Packaging": [("Great Lakes Can Co.", "USD", [
        ("CAN-16-BRT", "16 oz can, bright (per 1,000)", "1000", 140, 176, 30, 90),
        ("CAR-4PK-1000", "4-pack carrier (per 1,000)", "1000", 62, 80, 20, 60),
        ("TRY-24-EA", "24-can case tray", "each", 0.45, 0.62, 3000, 9000)])],
    "Cleaning & sanitation": [("Northwest Chem Supply", "USD", [
        ("CHM-CIP-55", "Caustic CIP cleaner, 55 gal drum", "drum", 380, 460, 6, 16),
        ("CHM-PAA-5", "Peracetic acid sanitizer, 5 gal", "pail", 95, 125, 14, 40),
        ("CHM-ACD-5", "Acid rinse, 5 gal", "pail", 70, 92, 12, 36)])],
    "Lab & QA": [("Cascade Lab Supply", "USD", [
        ("LAB-ATP-100", "ATP test swabs, box of 100", "box", 215, 260, 4, 12),
        ("LAB-VIA-KIT", "Yeast viability stain kit", "kit", 118, 150, 3, 9)])],
}
SPOT = [("Lab & QA", "Amazon Business", "LAB-PIP-SET", "Pipette set, adjustable", "set", 189.00, 2),
        ("Cleaning & sanitation", "Home Depot Pro", "CHM-RAG-50", "Shop towels, box of 50", "box", 32.50, 12),
        ("Packaging", "Uline", "PKG-TAPE-36", "Carton tape, 36 rolls", "case", 64.80, 5)]


def build(seed: int) -> dict:
    r = rng(seed)
    quotes, lines = [], []      # quotes: rev rows; lines: PO lines (truth carries the join)
    qn, pon = 100 + r.randint(0, 40), 5200 + r.randint(0, 300)
    start = date(2026, 1, 5)
    plan = []                   # (category, supplier, ccy, item)
    for cat in CATS:
        for sup, ccy, items in SUPPLIERS[cat]:
            for it in items:
                n = 2 if cat in ("Malt & grain", "Hops", "Packaging") else 1
                if cat == "Cleaning & sanitation" and it[0] == "CHM-CIP-55":
                    n = 2
                for _ in range(n):
                    plan.append((cat, sup, ccy, it))
    r.shuffle(plan)
    # forced structure
    rev2_cats = {"Hops", "Cleaning & sanitation", "Malt & grain", "Packaging"}
    qty_diff_cats = {"Malt & grain", "Packaging", "Lab & QA"}
    for k, (cat, sup, ccy, it) in enumerate(plan):
        code, desc, uom, plo, phi, qlo, qhi = it
        qdate = start + timedelta(days=int(k * 150 / len(plan)) + r.randint(0, 4))
        qn += r.randint(1, 3)
        qref = f"Q26-{qn:04d}"
        p1 = round(r.uniform(plo, phi), 3 if plo < 5 else 2)
        qqty = r.randrange(qlo, qhi + 1, 1000 if qlo >= 1000 else (10 if qlo >= 30 else 1))
        rev2 = cat in rev2_cats and r.random() < 0.6
        p2 = round(p1 * (1 - r.uniform(0.045, 0.09)), 3 if plo < 5 else 2) if rev2 else None
        quotes.append({"ref": qref, "rev": 1, "date": qdate, "sup": sup, "code": code, "desc": desc, "uom": uom, "qty": qqty, "price": p1, "ccy": ccy})
        if rev2:
            quotes.append({"ref": qref, "rev": 2, "date": qdate + timedelta(days=r.randint(3, 9)), "sup": sup, "code": code, "desc": desc,
                           "uom": uom, "qty": qqty, "price": p2, "ccy": ccy})
        pdate = qdate + timedelta(days=r.randint(12, 24))
        paid_local = p2 if rev2 else round(p1 * (1 - r.uniform(0.0, 0.025)), 3 if plo < 5 else 2)
        actual = RATES[ccy] * (1 + r.uniform(-0.025, 0.025)) if ccy != "USD" else 1.0
        po_unit = round(paid_local * actual, 3 if plo < 5 else 2)
        if cat in qty_diff_cats and r.random() < 0.65:
            step = 1000 if qlo >= 1000 else (10 if qlo >= 30 else 1)
            po_qty = max(step, qqty + r.choice([-3, -2, -1, 1, 2, 3, 4]) * step)
        else:
            po_qty = qqty
        pon += r.randint(1, 4)
        lines.append({"po": f"PO-{pon}", "date": pdate, "status": r.choice(["Closed", "Closed", "Received", "Open"]), "sup": sup, "qref": qref,
                      "cat": cat, "code": code, "desc": desc, "uom": uom, "qty": po_qty, "unit": po_unit, "ccy": ccy,
                      "p1": p1, "p_last": p2 if rev2 else p1, "qqty": qqty, "k": r.random()})
    # the surcharge line: a cleaning PO above the quote
    cl = [x for x in lines if x["cat"] == "Cleaning & sanitation" and x["p_last"] == x["p1"]] or \
        [x for x in lines if x["cat"] == "Cleaning & sanitation"]
    sur = r.choice(cl)
    sur["unit"] = round(sur["p1"] * r.uniform(1.06, 1.10), 2); sur["surcharge"] = True
    # two cancelled POs, one of them packaging
    pk = [x for x in lines if x["cat"] == "Packaging" and not x.get("surcharge")]
    c1 = r.choice(pk); c1["status"] = "Cancelled"
    other = [x for x in lines if x["cat"] in ("Malt & grain", "Lab & QA") and x["status"] != "Cancelled"] or \
        [x for x in lines if x["cat"] != "Packaging" and not x.get("surcharge")]
    c2 = r.choice(other); c2["status"] = "Cancelled"
    # spot buys
    for cat, sup, code, desc, uom, price, qty in SPOT:
        pon += r.randint(1, 4)
        lines.append({"po": f"PO-{pon}", "date": day_in(r, date(2026, 1, 12), date(2026, 6, 20)), "status": "Closed", "sup": sup, "qref": "",
                      "cat": cat, "code": code, "desc": desc, "uom": uom, "qty": qty, "unit": price, "ccy": "USD", "p1": None, "p_last": None,
                      "qqty": None, "k": r.random()})
    # merge a few same-supplier lines into multi-line POs by date proximity (same PO number)
    lines.sort(key=lambda x: (x["date"], x["k"]))
    for a, b in zip(lines, lines[1:]):
        if (a["sup"] == b["sup"] and (b["date"] - a["date"]).days <= 12 and a["qref"] and b["qref"]
                and "Cancelled" not in (a["status"], b["status"])):
            b["po"], b["date"], b["status"] = a["po"], a["date"], a["status"]
    # PO numbers run in date order, as the ERP issues them
    renum, nxt = {}, 5200 + r.randint(0, 300)
    for x in lines:
        if x["po"] not in renum:
            nxt += r.randint(1, 4); renum[x["po"]] = f"PO-{nxt}"
        x["po"] = renum[x["po"]]
    quotes.sort(key=lambda q: (q["date"], q["ref"], q["rev"]))

    def savings(x, base="p1", qty="qty", fx=True, floor=False):
        if not x["qref"]:
            return 0.0
        b = x[base] * (RATES[x["ccy"]] if fx else 1.0)
        v = round((b - x["unit"]) * x[qty], 2)
        return max(v, 0.0) if floor else v

    def by_cat(include_cancelled=False, **kw):
        out = {c: 0.0 for c in CATS}
        for x in lines:
            if x["status"] == "Cancelled" and not include_cancelled:
                continue
            out[x["cat"]] = round(out[x["cat"]] + savings(x, **kw), 2)
        return out
    truth = by_cat()
    for x in lines:
        x["counts"] = bool(x["qref"]) and x["status"] != "Cancelled"
        x["baseline_usd"] = round(x["p1"] * RATES[x["ccy"]], 4) if x["qref"] else None
        x["saving"] = savings(x) if x["counts"] else 0.0
    naive = {"no_fx": by_cat(fx=False), "quote_qty": by_cat(qty="qqty"), "last_rev": by_cat(base="p_last"),
             "cancelled_in": by_cat(include_cancelled=True), "floor": by_cat(floor=True)}
    spend = {c: round(sum(x["unit"] * x["qty"] for x in lines if x["cat"] == c and x["counts"]), 2) for c in CATS}
    base_val = {c: round(sum(x["baseline_usd"] * x["qty"] for x in lines if x["cat"] == c and x["counts"]), 2) for c in CATS}
    return {"quotes": quotes, "lines": lines, "truth": truth, "naive": naive, "spend": spend, "base_val": base_val,
            "total": round(sum(truth.values()), 2)}


def acceptable(d: dict) -> bool:
    t, n = d["truth"], d["naive"]
    for c in PINNED:
        v = t[c]
        if abs(v) < 900:
            return False
        row = [d["spend"][c], d["base_val"][c], v / d["base_val"][c] if d["base_val"][c] else 0]
        if any(abs(o - v) <= 0.01 * abs(v) for o in row):
            return False
    if t["Cleaning & sanitation"] <= 0 or d["total"] <= 0:
        return False
    moved = lambda var, c: abs(n[var][c] - t[c]) > 0.03 * abs(t[c])
    need = {"no_fx": ["Hops", "Malt & grain"], "quote_qty": ["Malt & grain", "Packaging"], "last_rev": ["Hops", "Cleaning & sanitation"],
            "cancelled_in": ["Packaging"], "floor": ["Cleaning & sanitation"]}
    for var, cats in need.items():
        if not all(moved(var, c) for c in cats):
            return False
    # every pinned category figure stands apart from the others
    vals = [t[c] for c in PINNED] + [d["total"]]
    if len({round(v) for v in vals}) != len(vals):
        return False
    return True


def lines_sheet(lines: list[dict]) -> tuple[dict, int]:
    rows = []
    for i, x in enumerate(lines, start=2):
        rows.append([x["po"], x["date"], x["status"], x["sup"], x["cat"], x["code"], x["qref"] or "", x["ccy"] if x["qref"] else "",
                     x["p1"] if x["qref"] else "", RATES[x["ccy"]] if x["qref"] else "",
                     f"=IF(G{i}=\"\",0,ROUND(I{i}*J{i},4))", x["qty"], x["unit"],
                     1 if x["counts"] else 0,
                     f"=N{i}*K{i}*L{i}", f"=N{i}*M{i}*L{i}", f"=ROUND(O{i}-P{i},2)"])
    return {"header": ["po_number", "po_date", "status", "supplier", "category", "item_code", "quote_ref", "quote_currency",
                       "quote_rev1_unit_price", "budget_rate_to_usd", "baseline_unit_usd", "po_qty", "po_unit_usd", "counts",
                       "baseline_value_usd", "po_value_usd", "savings_usd"], "rows": rows,
            "widths": {"A": 11, "B": 11, "D": 28, "E": 22, "F": 14}}, len(lines) + 1


def workbook(lines: list[dict]) -> dict:
    ls, n = lines_sheet(lines)
    summ = []
    for i, c in enumerate(CATS, start=2):
        summ.append([c, f"=SUMIF(Lines!$E$2:$E${n},A{i},Lines!$O$2:$O${n})", f"=SUMIF(Lines!$E$2:$E${n},A{i},Lines!$P$2:$P${n})",
                     f"=SUMIF(Lines!$E$2:$E${n},A{i},Lines!$Q$2:$Q${n})", f"=IF(B{i}=0,0,ROUND(D{i}/B{i},4))"])
    last = 1 + len(CATS); T = last + 1
    summ.append(["Total savings", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})", f"=IF(B{T}=0,0,ROUND(D{T}/B{T},4))"])
    summ.append([])
    summ.append(["Savings = (revision-1 quote price x budget rate - PO unit price) x PO quantity. Cancelled POs and spot buys without a quote are excluded; price increases are negative savings."])
    return {"Summary": {"header": ["Category", "Quoted value (USD)", "PO value (USD)", "Savings (USD)", "Savings %"], "rows": summ,
                        "number_formats": {"B": "#,##0.00", "C": "#,##0.00", "D": "#,##0.00", "E": "0.0%"}, "widths": {"A": 24, "B": 18, "C": 16, "D": 15}},
            "Lines": ls}


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    t = d["truth"]
    # ---- workspace
    write_xlsx(os.path.join(ws, "supplier_quotes_log_2026.xlsx"), {"Quotes": {
        "merged_title": "Supplier quotes 2026 - purchasing", "preamble": [["Kept by: Jess Okafor", "", "", "", "", "", "", "", "Revised quotes get a new Rev row"]],
        "header": ["Quote #", "Rev", "Quote date", "Supplier", "Item code", "Description", "Qty quoted", "UOM", "Unit price", "Currency"],
        "rows": [[q["ref"], q["rev"], q["date"], q["sup"], q["code"], q["desc"], q["qty"], q["uom"], q["price"], q["ccy"]] for q in d["quotes"]],
        "widths": {"A": 11, "C": 12, "D": 30, "E": 14, "F": 38}}}, creator="Purchasing")
    write_csv(os.path.join(ws, "po_export_2026-01-01_2026-06-30.csv"),
              ["PO Number", "PO Date", "Status", "Supplier", "Quote Ref", "Category", "Item Code", "Description", "Qty", "UOM", "Unit Cost (USD)", "Line Total (USD)"],
              [[x["po"], date_variant(x["date"], 1), x["status"], x["sup"], x["qref"], x["cat"], x["code"], x["desc"], x["qty"], x["uom"],
                money_str(x["unit"], 1) if x["unit"] >= 1 else f"${x['unit']:.3f}", money_str(round(x["unit"] * x["qty"], 2), 1)] for x in d["lines"]],
              preamble=["Purchase order lines - Tamarack Brewing", "Created 01/01/2026 to 06/30/2026, all statuses"], bom=True, crlf=True)
    write_email_thread(os.path.join(ws, "email_from_ruth_finance.txt"), [
        {"from": "Jess Okafor <jess@tamarackbrewing.com>", "to": "Ruth Mensah <ruth@tamarackbrewing.com>", "date": "Mon, 6 Jul 2026 09:02",
         "subject": "savings number for the owners",
         "body": "Ruth - the owners asked what my negotiating actually saved in the first half. How do you want it counted so it matches your books?"},
        {"from": "Ruth Mensah <ruth@tamarackbrewing.com>", "to": "Jess Okafor <jess@tamarackbrewing.com>", "date": "Mon, 6 Jul 2026 11:40",
         "subject": "RE: savings number for the owners",
         "body": ("Here is how finance counts it, per PO line:\n\n"
                  "  savings = (the supplier's first quoted unit price, in USD) - (the PO unit cost) x the quantity on the PO\n\n"
                  "The baseline is Rev 1 of the quote. The later revisions are the result of your negotiating, so measuring against them would hide "
                  "exactly what we want to show. Use the quantity we actually ordered, not the quantity the supplier quoted on.\n\n"
                  "Hallertau quotes in euros and Prairie Heritage in Canadian dollars. Convert quotes at our 2026 budget rates, not the day's rate: "
                  "1 EUR = 1.08 USD, 1 CAD = 0.73 USD. The PO export is already in USD. Don't round the converted unit price; work each line out in full and round the line's savings to the cent.\n\n"
                  "Cancelled POs saved nothing. Spot buys without a quote have no baseline, so leave them out of savings. And if a PO came in "
                  "above the quote, that is negative savings - it stays in, it does not become zero.\n\n"
                  "By category please, with a total.\n\nRuth")}])
    # ---- reference
    write_csv(os.path.join(ref, "savings_by_category.csv"), ["category", "quoted_value_usd", "po_value_usd", "savings_usd"],
              [[c, f"{d['base_val'][c]:.2f}", f"{d['spend'][c]:.2f}", f"{t[c]:.2f}"] for c in CATS] + [["TOTAL", "", "", f"{d['total']:.2f}"]])
    write_json(os.path.join(ref, "notes.json"), {"naive": d["naive"], "cancelled": [x["po"] for x in d["lines"] if x["status"] == "Cancelled"],
                                                  "surcharge_po": [x["po"] for x in d["lines"] if x.get("surcharge")], "total": d["total"]})
    # ---- reference solution
    write_xlsx(os.path.join(sol, "savings.xlsx"), workbook(d["lines"]), creator="reference")
    write_task_yaml(HERE, {
        "id": "procurement-savings", "track": "desk", "category": "reports",
        "title": "First-half purchasing savings by category",
        "ask": ("The owners want to know what Jess's negotiating saved us in the first half, by category. Her quote log and the PO export are in "
                "the folder, and Ruth's email says how finance counts it. Save it as savings.xlsx with live formulas.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "Hallertau quotes are in EUR and Prairie Heritage quotes in CAD while PO unit costs are USD; comparing unconverted quote prices "
            "turns hop savings negative and inflates malt savings several times over (checks: Hops savings; Malt savings)",
            "PO quantities differ from the quoted quantities on most malt and packaging lines; savings use the quantity ordered, so quote total "
            "minus PO total is wrong (checks: Malt savings; Packaging savings)",
            "negotiated quotes have a Rev 2 row at a lower price; the baseline is Rev 1, and joining on the latest revision shrinks savings to "
            "almost nothing (checks: Hops savings; Cleaning savings)",
            f"{sum(1 for x in d['lines'] if x['status'] == 'Cancelled')} cancelled POs still sit in the export, one of them packaging "
            "(check: Packaging savings)",
            "one cleaning PO came in 6-10% above its quote (a supplier surcharge); it is negative savings and must not be floored at zero "
            "(check: Cleaning savings)",
            "spot buys have no quote reference and no baseline; the PO export carries a two-line preamble, a BOM, CRLF endings and "
            "\"$1,234.50\" text money, and multi-line POs repeat the PO number (check: total savings)",
        ],
        "checks": [
            {"type": "file_exists", "name": "savings.xlsx exists", "path": "savings.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "savings.xlsx", "min_count": 10},
            {"type": "xlsx_no_errors", "name": "no formula errors", "path": "savings.xlsx"},
            {"type": "xlsx_value_present", "name": "Hops savings", "path": "savings.xlsx", "expected": t["Hops"], "rel_tol": 0.001, "rounding": f"EUR quotes converted at the {RATES['EUR']:.2f} budget rate", "near_text": "hops"},
            {"type": "xlsx_value_present", "name": "Malt savings", "path": "savings.xlsx", "expected": t["Malt & grain"], "rel_tol": 0.001, "rounding": f"CAD quotes converted at the {RATES['CAD']:.2f} budget rate", "near_text": "malt"},
            {"type": "xlsx_value_present", "name": "Packaging savings", "path": "savings.xlsx", "expected": t["Packaging"], "rel_tol": cent_tol(t["Packaging"], 0.005), "near_text": "packaging"},
            {"type": "xlsx_value_present", "name": "Cleaning savings", "path": "savings.xlsx", "expected": t["Cleaning & sanitation"], "rel_tol": cent_tol(t["Cleaning & sanitation"], 0.005), "near_text": "cleaning"},
            {"type": "xlsx_value_present", "name": "total savings", "path": "savings.xlsx", "expected": d["total"], "rel_tol": 0.001, "rounding": "includes EUR and CAD quotes converted at budget rates", "near_text": "total"},
        ],
    })
    print(f"seed={seed} quotes={len(d['quotes'])} lines={len(d['lines'])} truth={t} total={d['total']}")
    for k, v in d["naive"].items():
        print(f"  naive {k}: {v}")


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: join each PO line to the latest quote revision, compare the quote price as printed (no FX),
    keep every PO line including cancelled ones."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for c in CATS:
        s = sum((x["p_last"] - x["unit"]) * x["qty"] for x in d["lines"] if x["cat"] == c and x["qref"])
        rows.append([c, round(s, 2)])
    rows.append(["Total savings", f"=SUM(B2:B{len(CATS) + 1})"])
    write_xlsx(os.path.join(out, "savings.xlsx"), {"Summary": {"header": ["Category", "Savings"], "rows": rows}}, creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(2000):
        d_ = build(a.seed * 10000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 10000 + attempt, a.naive)
