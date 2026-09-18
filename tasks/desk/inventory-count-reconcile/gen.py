#!/usr/bin/env python3
"""inventory-count-reconcile: two counters' physical count sheets against the system stock export.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * counters wrote cases and eaches under five unit spellings; convert with the case quantity  (check: counted quantity in each)
  * bin A14 is on both sheets, once in cases and once in eaches; counted once it matches      (check: items that are off)
  * two SKUs have negative system stock; the variance is against the negative figure          (check: system quantity and variance)
  * five count lines carry old SKUs from the August relabel list                              (check: items that are off)
  * four bins were never counted; those items are off by the full system quantity            (check: items that are off)
  * the system export has a BOM, CRLF line ends and a two-line report preamble                (check: system quantity and variance)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

def write_xlsx_pinned(path: str, sheets: dict, creator: str = "Export") -> None:
    """write_xlsx, then pin dcterms:modified: openpyxl re-stamps it with the wall clock inside save(),
    so two runs a second apart differ in bytes. (Local workaround; the library writer is otherwise fixed.)"""
    import re as _re, zipfile as _zip, io as _io
    write_xlsx(path, sheets, creator=creator)
    with _zip.ZipFile(path) as zin:
        items = [(zi.filename, zin.read(zi.filename)) for zi in zin.infolist()]
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zout:
        for name, data in items:
            if name == "docProps/core.xml":
                data = _re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", rb"\g<1>2026-01-15T09:00:00Z\g<2>", data)
            zi = _zip.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = _zip.ZIP_DEFLATED
            zout.writestr(zi, data)
    write_bytes(path, buf.getvalue())

# (name, case qty)  coffee roastery warehouse
ITEMS = [("House Blend 12 oz bag", 6), ("Espresso Roast 12 oz bag", 6), ("Decaf Colombia 12 oz bag", 6), ("Ethiopia Yirgacheffe 12 oz bag", 6),
         ("Guatemala Antigua 12 oz bag", 6), ("Cold Brew Blend 2 lb bag", 4), ("House Blend 5 lb bag", 4), ("Espresso Roast 5 lb bag", 4),
         ("Single-serve pods 10 ct", 12), ("Hot cup 12 oz sleeve of 50", 20), ("Hot cup 16 oz sleeve of 50", 20), ("Cup lid 12/16 oz sleeve of 100", 10),
         ("Cold cup 20 oz sleeve of 50", 20), ("Cold cup lid sleeve of 100", 10), ("Paper filter #4 box of 100", 12), ("Paper filter basket box of 250", 12),
         ("Vanilla syrup 750 ml", 6), ("Caramel syrup 750 ml", 6), ("Hazelnut syrup 750 ml", 6), ("Oat milk 32 oz carton", 12),
         ("Whole milk 1 gal", 4), ("Chocolate sauce 64 oz", 6), ("Matcha powder 1 lb", 8), ("Chai concentrate 32 oz", 12),
         ("Sugar packets box of 2000", 1), ("Stir sticks box of 1000", 10), ("Napkins case of 3000", 1), ("Bottled water 500 ml", 24),
         ("Sparkling water 12 oz can", 24), ("Kombucha 16 oz bottle", 12), ("Croissant frozen", 48), ("Muffin frozen", 24),
         ("Bagel frozen 6 pk", 8), ("Cookie dough puck", 96), ("Cleaning tablets 100 ct", 12), ("Descaler 1 L", 6),
         ("Gift card blank", 100), ("Branded tumbler 16 oz", 12), ("Branded tote bag", 25), ("Merch tee M", 12)]
UNITS_CASE_M = ["cs", "CS", "cs", "case"]; UNITS_EA_M = ["ea", "Ea", "ea", "EA"]
UNITS_CASE_D = ["case", "CASE", "cases", "case"]; UNITS_EA_D = ["each", "pcs", "units", "each"]

def build(seed: int) -> dict:
    r = rng(seed)
    items = []
    for i, (name, cq) in enumerate(ITEMS):
        items.append({"sku": f"NJ-{1100 + i * 7 + r.randint(0, 5)}", "name": name, "case_qty": cq, "bins": []})
    # bins: A01..A22 (Maria), B01..B20 (Devon); most items in one bin, six items in two bins
    bins = [f"A{i:02d}" for i in range(1, 23)] + [f"B{i:02d}" for i in range(1, 21)]
    two_bin = r.sample(items, 2)
    order = items[:]; r.shuffle(order)
    bi = 0
    for it in order:
        it["bins"].append(bins[bi]); bi += 1
    for it in two_bin:
        it["bins"].append(bins[bi]); bi += 1
    assert bi == len(bins)
    # system qty per bin (eaches); make a few multiples of case qty
    for it in items:
        it["sys_by_bin"] = {}
        for b in it["bins"]:
            q = r.randint(1, 14) * it["case_qty"] if r.random() < 0.6 else r.randint(3, 120)
            it["sys_by_bin"][b] = q
    # negative system stock on two single-bin items
    neg = r.sample([i for i in items if len(i["bins"]) == 1], 2)
    for it, q in zip(neg, (-4, -18)):
        it["sys_by_bin"][it["bins"][0]] = q
    # count per bin (eaches): 45% exact, rest off by a bit; uncounted bins (four, in aisle B and A), never the negatives/A14
    a14_item = next(i for i in items if "A14" in i["bins"])
    protected = set([id(a14_item)] + [id(i) for i in neg])
    uncounted_bins = r.sample([b for b in bins if b not in ("A14",) and all(b not in i["bins"] for i in neg)], 4)
    for it in items:
        it["count_by_bin"] = {}
        for b in it["bins"]:
            if b in uncounted_bins: continue
            sysq = it["sys_by_bin"][b]
            if id(it) in protected and b == "A14": it["count_by_bin"][b] = sysq; continue
            if id(it) in protected: it["count_by_bin"][b] = max(0, sysq + r.choice([2, 3, 5])); continue
            it["count_by_bin"][b] = sysq if r.random() < 0.45 else max(0, sysq + r.choice([-6, -3, -2, -1, 1, 2, 4, 6, 12]))
    # A14 counted once in Maria's sheet as cases; make sure it is a case multiple
    q = a14_item["sys_by_bin"]["A14"]; cq = a14_item["case_qty"]
    if q % cq or q == 0:
        q = max(1, q // cq + 1) * cq; a14_item["sys_by_bin"]["A14"] = q; a14_item["count_by_bin"]["A14"] = q
    # relabel list: 8 old->new; 5 used on Maria's sheet (aisle A items, not A14)
    relabel_pool = [i for i in items if i["bins"][0].startswith("A") and i is not a14_item and i not in neg]
    relabeled = r.sample(relabel_pool, 8)
    for it in relabeled:
        it["old_sku"] = f"NJ-{int(it['sku'][3:]) - 700 + r.randint(0, 3)}"
    used_old = relabeled[:5]
    # ground truth per item
    truth = []
    for it in items:
        s = sum(it["sys_by_bin"].values()); c = sum(it["count_by_bin"].values())
        truth.append({"sku": it["sku"], "name": it["name"], "system": s, "counted": c, "variance": c - s})
    off = [t for t in truth if t["variance"] != 0]
    return {"items": items, "truth": truth, "off": off, "neg": neg, "a14": a14_item, "relabeled": relabeled, "used_old": used_old,
            "uncounted_bins": uncounted_bins, "bins": bins}

def emit(seed: int) -> None:
    d = build(seed); r = rng(seed + 77)
    ws, ref, sol = task_dirs(HERE)
    items = d["items"]
    # system export
    srows = []
    for it in items:
        for b in it["bins"]:
            srows.append([it["sku"], it["name"], b, it["sys_by_bin"][b], it["case_qty"], "07/31/2026"])
    srows.sort(key=lambda x: x[2])
    write_csv(os.path.join(ws, "stock_on_hand_export_2026-09-12.csv"), ["SKU", "Item", "Bin", "On Hand (EA)", "Case Qty", "Last Counted"], srows,
              preamble=["Nightjar Coffee Roasters - Stock status by bin", "Generated 09/12/2026 06:00 by warehouse.system"], bom=True, crlf=True)
    write_csv(os.path.join(ws, "sku_relabel_aug2026.csv"), ["old_sku", "new_sku", "item"], [[it["old_sku"], it["sku"], it["name"]] for it in d["relabeled"]])
    used_old_ids = set(id(i) for i in d["used_old"])
    # Maria: aisle A, xlsx, cs/ea, old labels on five lines
    mrows = []
    for b in [x for x in d["bins"] if x.startswith("A")]:
        it = next(i for i in items if b in i["bins"])
        if b not in it["count_by_bin"]: continue
        q = it["count_by_bin"][b]; cq = it["case_qty"]
        sku = it["old_sku"] if id(it) in used_old_ids else it["sku"]
        if cq > 1 and q % cq == 0 and r.random() < 0.7:
            mrows.append([b, sku, q // cq, r.choice(UNITS_CASE_M), "old label" if id(it) in used_old_ids and r.random() < 0.5 else ""])
        else:
            mrows.append([b, sku, q, r.choice(UNITS_EA_M), ""])
    write_xlsx_pinned(os.path.join(ws, "count_sheet_maria_aisleA.xlsx"), {"Count": {
        "merged_title": "Physical count 9/12 - aisle A - counter: Maria", "header": ["Bin", "SKU", "Qty", "Unit", "Notes"], "rows": mrows,
        "widths": {"B": 12, "E": 16}}}, creator="Maria")
    # Devon: aisle B csv, plus A14 at the top (duplicate of Maria's, in eaches)
    a14 = d["a14"]; q = a14["count_by_bin"]["A14"]
    drows = [["A14", a14["sku"], q, "each", "started here by mistake"]]
    for b in [x for x in d["bins"] if x.startswith("B")]:
        it = next(i for i in items if b in i["bins"])
        if b not in it["count_by_bin"]: continue
        q = it["count_by_bin"][b]; cq = it["case_qty"]
        if cq > 1 and q % cq == 0 and r.random() < 0.6:
            drows.append([b, it["sku"], q // cq, r.choice(UNITS_CASE_D), ""])
        else:
            drows.append([b, it["sku"], q, r.choice(UNITS_EA_D), ""])
    write_csv(os.path.join(ws, "count_devon_aisleB.csv"), ["bin", "item_code", "counted", "uom", "comment"], drows, crlf=True)
    write_email_thread(os.path.join(ws, "email_from_rosa.txt"), [
        {"from": "Rosa Delgado <rosa@nightjar.coffee>", "to": "you", "date": "Sat, 12 Sep 2026 15:40", "subject": "count sheets from this morning",
         "body": ("Both count sheets are in the folder with the stock export from this morning.\n\n"
                  "A few things: Devon started in aisle A by mistake and did A14 before I sent him over to B, so that bin is on "
                  "both sheets. Count it once. Some of aisle A still has the old shelf labels from before the August renumbering, "
                  "so Maria wrote whatever was on the label; the relabel list is in the folder.\n\n"
                  "Where they counted in cases, use the case quantity from the export to get to eaches. If a bin is not on either "
                  "sheet nobody counted it, so the count for that stock is zero. The system has a couple of negative quantities, "
                  "compare against what it actually says.\n\nI want one line per item that is off, with what the system has, "
                  "what we counted, and the difference. Items that match do not need to be in it. - Rosa")}])
    header = ["sku", "item", "system_qty", "counted_qty", "variance"]
    rows = [[t["sku"], t["name"], t["system"], t["counted"], t["variance"]] for t in d["off"]]
    write_csv(os.path.join(ref, "variances.csv"), header, rows)
    write_csv(os.path.join(sol, "variances.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {"negative_stock": [i["sku"] for i in d["neg"]], "a14_item": a14["sku"],
                                                  "old_skus_used": {i["old_sku"]: i["sku"] for i in d["used_old"]},
                                                  "uncounted_bins": d["uncounted_bins"], "items_off": len(d["off"]), "items_total": len(items)})
    uncounted_skus = [next(i["sku"] for i in items if b in i["bins"]) for b in d["uncounted_bins"]]
    case_lines = [row[1] for row in mrows if row[3] in UNITS_CASE_M][:3]
    must = sorted(set([i["sku"] for i in d["neg"]] + [i["sku"] for i in d["used_old"] if i["sku"] in {t["sku"] for t in d["off"]}] +
                      [s for s in uncounted_skus if s in {t["sku"] for t in d["off"]}] + [s for s in case_lines if s in {t["sku"] for t in d["off"]}]))
    write_task_yaml(HERE, {
        "id": "inventory-count-reconcile", "track": "desk", "category": "spreadsheet",
        "title": "Reconcile the physical count against the system stock",
        "ask": "We counted the warehouse on Saturday. Compare the two count sheets against the stock export and give me variances.csv; Rosa's email explains how the count went.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "counters wrote cases and eaches under five unit spellings (cs, CS, case, cases, ea, each, pcs, units); case lines convert with the export's case quantity (check: counted quantity in each)",
            "bin A14 is on both sheets, Maria in cases and Devon in eaches; counted once it matches the system, counted twice it becomes a false variance (check: items that are off)",
            "two SKUs have negative system stock; the variance is against the negative figure, not against zero (check: system quantity and variance)",
            "five of Maria's lines use old SKUs from the August relabel list; joined as written they look like unknown items and the real items look uncounted (check: items that are off)",
            "four bins were never counted, so those items are off by their full system quantity and must appear (check: items that are off)",
            "the stock export carries a BOM, CRLF line ends and a two-line preamble; two items sit in two bins and must be summed (check: system quantity and variance)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "variances.csv", "columns": ["sku", "system_qty", "counted_qty", "variance"]},
            {"type": "csv_set_equal", "name": "items that are off", "path": "variances.csv", "column": "sku", "ref": "variances.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "variances.csv", "equals_ref": "variances.csv"},
            {"type": "csv_values_match", "name": "counted quantity in each", "path": "variances.csv", "ref": "variances.csv", "key": "sku",
             "columns": ["counted_qty"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0, "must_match_keys": must},
            {"type": "csv_values_match", "name": "system quantity and variance", "path": "variances.csv", "ref": "variances.csv", "key": "sku",
             "columns": ["system_qty", "variance"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0, "must_match_keys": [i["sku"] for i in d["neg"]]},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
