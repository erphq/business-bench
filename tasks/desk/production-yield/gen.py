#!/usr/bin/env python3
"""production-yield: a month of batch records to yield and scrap per production line, by weight.

    python gen.py [--seed N] [--naive DIR]

Business: a snack co-packer with three lines (bars, granola, date bites). Operators write output the way each
line counts it - cases, loose pieces, bags, kilograms, grams - and the plant manager wants yield and scrap by line.

Traps (each caught by a check, see task.yaml):
  * output and scrap are in cs, pcs, bags, kg and g; pieces/cases/bags convert with the spec sheet
                                                                          (checks: Bar good kg; Granola good kg; Bites scrap kg)
  * rework batches reprocess scrap already charged to a parent batch: input not counted again, recovered output
    comes off the parent's scrap                                          (checks: Bar scrap kg; yields; plant input)
  * trial batches are not production                                      (check: plant input kg)
  * the summary must be live formulas                                     (check: live formulas)
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


LINES = ["Bar line", "Granola line", "Bites line"]
# sku, description, line, unit weight g, units per case, bag weight g
SPECS = [("BAR-OAT-42", "Oat & honey bar 42 g", "Bar line", 42, 24, None),
         ("BAR-PB-42", "Peanut butter bar 42 g", "Bar line", 42, 24, None),
         ("BAR-CHO-45", "Dark chocolate bar 45 g", "Bar line", 45, 20, None),
         ("GRN-HON-340", "Honey almond granola 340 g", "Granola line", None, 12, 340),
         ("GRN-CIN-500", "Cinnamon granola 500 g", "Granola line", None, 8, 500),
         ("BITE-DATE-12", "Date & cacao bites 12 g", "Bites line", 12, 60, None),
         ("BITE-COCO-14", "Coconut bites 14 g", "Bites line", 14, 50, None)]
SPEC = {s[0]: s for s in SPECS}
PREFIX = {"Bar line": "BR", "Granola line": "GR", "Bites line": "BT"}
TRIAL_SKUS = [("BAR-PRO-50", "Bar line"), ("GRN-KETO-300", "Granola line")]


def build(seed: int) -> dict:
    r = rng(seed)
    batches = []
    days = [d for d in (date(2026, 8, 1) + timedelta(days=i) for i in range(31)) if d.weekday() < 5]
    seq = {}

    def bid(line, d):
        k = (line, d)
        seq[k] = seq.get(k, 0) + 1
        return f"{PREFIX[line]}{d.strftime('%m%d')}-{seq[k]}"

    for line in LINES:
        skus = [s for s in SPECS if s[2] == line]
        for d in days:
            for _ in range(r.choice([1, 2, 2] if line == "Bar line" else [1, 1, 2])):
                sku = r.choice(skus)
                code_, _, _, w, per_case, bag = sku
                if line == "Bar line":
                    inp = money(r, 850, 1300, cents=False)
                    loss = r.uniform(0.006, 0.025); scrap_frac = r.uniform(0.03, 0.08)
                    good_kg = inp * (1 - loss - scrap_frac)
                    pieces = int(good_kg * 1000 / w)
                    if r.random() < 0.7:
                        good_qty, good_unit = pieces // per_case, "cs"
                        good_kg = good_qty * per_case * w / 1000
                    else:
                        good_qty, good_unit = pieces, "pcs"
                        good_kg = pieces * w / 1000
                    scrap_qty = round(inp * scrap_frac, 1); scrap_unit = "kg"; scrap_kg = scrap_qty
                elif line == "Granola line":
                    inp = money(r, 600, 900, cents=False)
                    loss = r.uniform(0.04, 0.07); scrap_frac = r.uniform(0.015, 0.05)
                    good_kg = inp * (1 - loss - scrap_frac)
                    if r.random() < 0.6:
                        bags = int(good_kg * 1000 / bag)
                        good_qty, good_unit, good_kg = bags, "bags", bags * bag / 1000
                    else:
                        good_qty, good_unit = round(good_kg, 1), "kg"
                        good_kg = good_qty
                    scrap_qty = round(inp * scrap_frac, 1); scrap_unit = "kg"; scrap_kg = scrap_qty
                else:
                    inp = money(r, 140, 260, cents=False)
                    loss = r.uniform(0.01, 0.03); scrap_frac = r.uniform(0.03, 0.09)
                    good_kg = inp * (1 - loss - scrap_frac)
                    pieces = int(good_kg * 1000 / w)
                    good_qty, good_unit, good_kg = pieces, "pcs", pieces * w / 1000
                    grams = int(round(inp * scrap_frac * 1000, -1))
                    if r.random() < 0.65:
                        scrap_qty, scrap_unit = grams, "g"
                    else:
                        scrap_qty, scrap_unit = round(grams / 1000, 2), "kg"
                    scrap_kg = grams / 1000
                batches.append({"id": bid(line, d), "date": d, "line": line, "sku": code_, "type": "Production", "of": "",
                                "inp": float(inp), "inp_unit": "kg", "good_qty": good_qty, "good_unit": good_unit, "good_kg": good_kg,
                                "scrap_qty": scrap_qty, "scrap_unit": scrap_unit, "scrap_kg": scrap_kg, "note": ""})
    # rework: a share of a high-scrap parent's scrap goes back through the line a day or two later
    for line, n in (("Bar line", 4), ("Granola line", 2), ("Bites line", 3)):
        parents = sorted([b for b in batches if b["line"] == line and b["type"] == "Production"], key=lambda b: -b["scrap_kg"] / b["inp"])[:8]
        for p in r.sample(parents, n):
            code_, _, _, w, per_case, bag = SPEC[p["sku"]]
            d = p["date"] + timedelta(days=r.choice([1, 2, 3]))
            while d.weekday() >= 5:
                d += timedelta(days=1)
            if d.month != 8:
                continue
            inp = round(p["scrap_kg"] * r.uniform(0.55, 0.85), 1)
            rescrap_kg = inp * r.uniform(0.1, 0.25)
            good_kg = inp - rescrap_kg - inp * 0.01
            if line == "Bar line":
                pcs = int(good_kg * 1000 / w)
                good_qty, good_unit, good_kg = pcs // per_case, "cs", (pcs // per_case) * per_case * w / 1000
                scrap_qty, scrap_unit = round(rescrap_kg, 1), "kg"; rescrap_kg = scrap_qty
            elif line == "Granola line":
                bags = int(good_kg * 1000 / bag)
                good_qty, good_unit, good_kg = bags, "bags", bags * bag / 1000
                scrap_qty, scrap_unit = round(rescrap_kg, 1), "kg"; rescrap_kg = scrap_qty
            else:
                pcs = int(good_kg * 1000 / w)
                good_qty, good_unit, good_kg = pcs, "pcs", pcs * w / 1000
                g = int(round(rescrap_kg * 1000, -1)); scrap_qty, scrap_unit, rescrap_kg = g, "g", g / 1000
            batches.append({"id": bid(line, d), "date": d, "line": line, "sku": p["sku"], "type": "Rework", "of": p["id"],
                            "inp": inp, "inp_unit": "kg", "good_qty": good_qty, "good_unit": good_unit, "good_kg": good_kg,
                            "scrap_qty": scrap_qty, "scrap_unit": scrap_unit, "scrap_kg": rescrap_kg, "note": f"rework of {p['id']} quarantine"})
    # trial batches
    for sku, line in TRIAL_SKUS:
        d = r.choice(days)
        inp = money(r, 150, 260, cents=False)
        batches.append({"id": bid(line, d), "date": d, "line": line, "sku": sku, "type": "Trial", "of": "", "inp": float(inp), "inp_unit": "kg",
                        "good_qty": round(inp * 0.6, 1), "good_unit": "kg", "good_kg": round(inp * 0.6, 1),
                        "scrap_qty": round(inp * 0.35, 1), "scrap_unit": "kg", "scrap_kg": round(inp * 0.35, 1), "note": "R&D trial - new recipe"})
    batches.sort(key=lambda b: (b["date"], b["line"], b["id"]))
    return {"batches": batches}


def totals(batches, rework_rule=True, trials=False, unit_blind=False) -> dict:
    out = {l: {"inp": 0.0, "good": 0.0, "scrap": 0.0} for l in LINES}
    for b in batches:
        if b["type"] == "Trial" and not trials:
            continue
        good = float(b["good_qty"]) if unit_blind and b["good_unit"] != "kg" else b["good_kg"]
        scrap = float(b["scrap_qty"]) if unit_blind and b["scrap_unit"] != "kg" else b["scrap_kg"]
        t = out[b["line"]]
        if b["type"] == "Rework" and rework_rule:
            t["good"] += good
            t["scrap"] += scrap - b["inp"]
        else:
            t["inp"] += b["inp"]; t["good"] += good; t["scrap"] += scrap
    for l in LINES:
        t = out[l]
        t["inp"], t["good"], t["scrap"] = round(t["inp"], 2), round(t["good"], 2), round(t["scrap"], 2)
        t["yield"] = round(t["good"] / t["inp"], 4)
        t["scrap_rate"] = round(t["scrap"] / t["inp"], 4)
    out["plant"] = {k: round(sum(out[l][k] for l in LINES), 2) for k in ("inp", "good", "scrap")}
    out["plant"]["yield"] = round(out["plant"]["good"] / out["plant"]["inp"], 4)
    return out


def acceptable(d: dict) -> bool:
    B = d["batches"]
    t = totals(B)
    if sum(1 for b in B if b["type"] == "Rework") < 8:
        return False
    rw = totals(B, rework_rule=False)
    tr = totals(B, trials=True)
    ub = totals(B, unit_blind=True)
    far = lambda a, b, rel=0.012: abs(a - b) > rel * abs(a)
    if not far(t["Bar line"]["scrap"], rw["Bar line"]["scrap"]) or abs(t["Bar line"]["yield"] - rw["Bar line"]["yield"]) < 0.003:
        return False
    if abs(t["Bites line"]["yield"] - rw["Bites line"]["yield"]) < 0.003:
        return False
    if not far(t["plant"]["inp"], rw["plant"]["inp"], 0.003) or not far(t["plant"]["inp"], tr["plant"]["inp"], 0.003):
        return False
    if not far(t["Bar line"]["good"], ub["Bar line"]["good"]) or not far(t["Granola line"]["good"], ub["Granola line"]["good"]) \
            or not far(t["Bites line"]["scrap"], ub["Bites line"]["scrap"]):
        return False
    # a pinned line figure must not also be a single batch's number on a row that names the same line
    for l, v in (("Bar line", t["Bar line"]["good"]), ("Bar line", t["Bar line"]["scrap"]), ("Granola line", t["Granola line"]["good"]),
                 ("Bites line", t["Bites line"]["scrap"])):
        for b in B:
            if b["line"] == l and any(abs(x - v) <= 0.012 * v for x in (b["inp"], b["good_kg"], b["scrap_kg"], float(b["good_qty"]), float(b["scrap_qty"]))):
                return False
    if any(abs(x - t["plant"]["inp"]) <= 0.01 * t["plant"]["inp"] for b in B for x in (float(b["good_qty"]), float(b["scrap_qty"]))):
        return False
    for l in LINES:
        row = [t[l]["inp"], t[l]["good"], t[l]["scrap"]]
        if len({round(x) for x in row}) < 3:
            return False
        if t[l]["scrap"] <= 0:
            return False
        # a rate read as a percentage must not collide with a kilogram figure on the same row
        if any(abs(x - t[l]["yield"] * 100) < 0.5 or abs(x - t[l]["scrap_rate"] * 100) < 0.5 for x in row):
            return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_workbook(rows: list[list], note: str) -> dict:
    """rows: [batch, date, line, sku, type, rework_of, input_kg, good_kg, scrap_kg, counted_input_kg, counted_good_kg, counted_scrap_kg]"""
    n = len(rows) + 1
    summ = []
    for i, l in enumerate(LINES, start=2):
        rng_ = f"Batches!$C$2:$C${n},$A{i}"
        summ.append([l, f"=ROUND(SUMIFS(Batches!$J$2:$J${n},{rng_}),2)", f"=ROUND(SUMIFS(Batches!$K$2:$K${n},{rng_}),2)",
                     f"=ROUND(SUMIFS(Batches!$L$2:$L${n},{rng_}),2)", f"=IF(B{i}=0,0,ROUND(C{i}/B{i},4))", f"=IF(B{i}=0,0,ROUND(D{i}/B{i},4))"])
    summ.append(["Plant total", "=SUM(B2:B4)", "=SUM(C2:C4)", "=SUM(D2:D4)", "=IF(B5=0,0,ROUND(C5/B5,4))", "=IF(B5=0,0,ROUND(D5/B5,4))"])
    summ.append([])
    summ.append([note])
    return {"Yield by line": {"header": ["Line", "Input (kg)", "Good output (kg)", "Scrap (kg)", "Yield", "Scrap rate"], "rows": summ,
                              "widths": {"A": 16, "B": 12, "C": 16, "D": 12}},
            "Batches": {"header": ["batch", "date", "line", "sku", "type", "rework_of", "input_kg", "good_kg", "scrap_kg",
                                   "counted_input_kg", "counted_good_kg", "counted_scrap_kg"], "rows": rows, "widths": {"D": 14}}}


def batch_rows(B, rework_rule=True, trials=False) -> list[list]:
    rows = []
    for b in B:
        g, s = round(b["good_kg"], 3), round(b["scrap_kg"], 3)
        if b["type"] == "Trial" and not trials:
            ci, cg, cs = 0, 0, 0
        elif b["type"] == "Rework" and rework_rule:
            ci, cg, cs = 0, g, round(s - b["inp"], 3)
        else:
            ci, cg, cs = b["inp"], g, s
        rows.append([b["id"], b["date"].isoformat(), b["line"], b["sku"], b["type"], b["of"], b["inp"], g, s, ci, cg, cs])
    return rows


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    B = d["batches"]
    t = totals(B)

    # ---- workspace
    r = rng(seed + 29)
    body = []
    for b in B:
        def q(x, unit):
            if unit in ("pcs", "cs", "bags", "g"):
                return f"{int(x):,}" if r.random() < 0.5 else str(int(x))
            return f"{x:g}"
        body.append([b["id"], b["date"].strftime("%d/%m/%Y"), b["line"], b["sku"], b["type"], b["of"], q(b["inp"], "kg"), b["inp_unit"],
                     q(b["good_qty"], b["good_unit"]), b["good_unit"], q(b["scrap_qty"], b["scrap_unit"]), b["scrap_unit"], b["note"]])
    write_csv(os.path.join(ws, "batch_records_2026-08.csv"),
              ["Batch", "Date", "Line", "SKU", "Batch type", "Rework of", "Qty in", "Unit in", "Good qty", "Good unit", "Scrap qty",
               "Scrap unit", "Operator notes"], body, preamble=["MES batch record export - August 2026 - dates DD/MM/YYYY", ""])
    write_xlsx(os.path.join(ws, "product_specs.xlsx"), {"Specs": {
        "merged_title": "Finished goods specifications (QA-SPEC-004 rev 7)",
        "header": ["SKU", "Description", "Line", "Unit weight (g)", "Units per case", "Bag net weight (g)"],
        "rows": [[s[0], s[1], s[2], s[3] if s[3] else "", s[4], s[5] if s[5] else ""] for s in SPECS] +
                [["BAR-PRO-50", "Protein bar 50 g (in development)", "Bar line", 50, 20, ""]],
        "widths": {"A": 14, "B": 32, "C": 14, "D": 16, "E": 14, "F": 18}}}, creator="QA")
    write_text(os.path.join(ws, "note_from_tomasz.txt"),
               "August yield report\n\n"
               "I need yield and scrap for each line for August, and for the plant as a whole.\n\n"
               "Do it all by weight. Input is the kilograms of mix charged to the batch. The operators record good output and\n"
               "scrap the way their line counts them - cases, pieces, bags, kilograms or grams - so convert with the spec\n"
               "sheet (a case of bars is the units per case times the bar weight; a bag is its net weight).\n\n"
               "  yield      = good output kg / input kg\n"
               "  scrap rate = scrap kg / input kg\n\n"
               "Rework: when a batch has a lot of rejects we quarantine them and run them back through the line later as a\n"
               "Rework batch, which names the batch it came from. That material was already input on the original batch, so do\n"
               "not count a rework batch's input again. Whatever the rework batch turns into good product counts as good output\n"
               "for the line, and it is no longer scrap - take the rework input off the scrap. Anything the rework batch rejects\n"
               "again is scrap.\n\n"
               "Trial batches are R&D and not production. Leave them out.\n\n"
               "The totals need to stay as formulas so I can drop September's records in.\n\n"
               "Tomasz\n")

    # ---- reference
    write_csv(os.path.join(ref, "yield_by_line.csv"), ["line", "input_kg", "good_kg", "scrap_kg", "yield", "scrap_rate"],
              [[l, f"{t[l]['inp']:.2f}", f"{t[l]['good']:.2f}", f"{t[l]['scrap']:.2f}", f"{t[l]['yield']:.4f}", f"{t[l]['scrap_rate']:.4f}"] for l in LINES] +
              [["Plant total", f"{t['plant']['inp']:.2f}", f"{t['plant']['good']:.2f}", f"{t['plant']['scrap']:.2f}", f"{t['plant']['yield']:.4f}", ""]])
    rw, tr, ub = totals(B, rework_rule=False), totals(B, trials=True), totals(B, unit_blind=True)
    write_json(os.path.join(ref, "notes.json"), {
        "yield_pins": [[l, t[l]["yield"]] for l in LINES], "plant": t["plant"],
        "rework_batches": [b["id"] for b in B if b["type"] == "Rework"], "trial_batches": [b["id"] for b in B if b["type"] == "Trial"],
        "naive": {"rework_as_production": {l: rw[l] for l in LINES}, "trials_counted_plant_input": tr["plant"]["inp"],
                  "units_ignored": {l: ub[l] for l in LINES}}})

    # ---- reference solution
    note = ("By weight. Cases = units per case x unit weight, bags = net weight, grams / 1000. Rework batches add no input; their good "
            "output counts and their input comes off scrap. Trial batches excluded.")
    write_xlsx(os.path.join(sol, "yield.xlsx"), report_workbook(batch_rows(B), note), creator="reference")

    write_task_yaml(HERE, {
        "id": "production-yield", "track": "desk", "category": "reports",
        "title": "August yield and scrap by production line",
        "ask": ("Tomasz wants August's yield and scrap for each production line from the batch records. Save it as yield.xlsx with "
                "live formulas; his note in the folder says how he wants it worked out.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the Bar line records good output mostly in cases and sometimes loose pieces; three bar SKUs have "
            "different weights and case packs (42 g x 24, 45 g x 20), so a single conversion or a raw sum of the quantity column is wrong "
            "(checks: Bar line good output kg; yield per line)",
            "Granola output is in bags of 340 g or 500 g on some batches and in kg on others (check: Granola line good output kg)",
            "Bites scrap is in grams on most batches and kilograms on the rest; adding the column as kilograms inflates scrap about "
            "a thousandfold (check: Bites line scrap kg)",
            "rework batches reprocess quarantined rejects from a named parent batch: their input must not be counted again and the "
            "rework input comes off scrap; treated as ordinary batches they double-count input and leave the recovered product in "
            "scrap (checks: Bar line scrap kg; yield per line; plant input kg)",
            "two R&D trial batches (one on the Bar line, one on Granola) sit in the same export, and the spec sheet lists the trial "
            "bar's weight (check: plant input kg)",
            "dates are DD/MM/YYYY per the export's preamble line, and counts come with and without thousands separators "
            "(check: plant input kg)",
            "the summary has to be live formulas so next month's records can be dropped in (check: live formulas)",
        ],
        "checks": [
            {"type": "file_exists", "name": "yield.xlsx exists", "path": "yield.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "yield.xlsx", "min_count": 8},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "yield.xlsx"},
            {"type": "xlsx_value_present", "name": "Bar line good output kg (cases and pieces converted)", "path": "yield.xlsx",
             "expected": t["Bar line"]["good"], "rel_tol": cent_tol(t["Bar line"]["good"], 0.004), "near_text": "bar"},
            {"type": "xlsx_value_present", "name": "Bar line scrap kg (rework netted)", "path": "yield.xlsx",
             "expected": t["Bar line"]["scrap"], "rel_tol": cent_tol(t["Bar line"]["scrap"], 0.004), "near_text": "bar"},
            {"type": "xlsx_value_present", "name": "Granola line good output kg (bags converted)", "path": "yield.xlsx",
             "expected": t["Granola line"]["good"], "rel_tol": cent_tol(t["Granola line"]["good"], 0.004), "near_text": "granola"},
            {"type": "xlsx_value_present", "name": "Bites line scrap kg (grams converted, rework netted)", "path": "yield.xlsx",
             "expected": t["Bites line"]["scrap"], "rel_tol": cent_tol(t["Bites line"]["scrap"], 0.004), "near_text": "bites"},
            {"type": "xlsx_value_present", "name": "plant input kg (no rework or trial input)", "path": "yield.xlsx",
             "expected": t["plant"]["inp"], "rel_tol": cent_tol(t["plant"]["inp"], 0.002), "near_text": "total"},
            {"type": "custom", "name": "yield per line", "module": "check.py"},
        ],
    })
    print(f"seed={seed} batches={len(B)} rework={sum(1 for b in B if b['type'] == 'Rework')} totals={t} "
          f"naive_rework_yield={ {l: rw[l]['yield'] for l in LINES} }")


def write_naive(d: dict, out: str) -> None:
    """Quantities summed as written whatever the unit, rework and trial batches treated as ordinary batches."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for b in d["batches"]:
        g = float(b["good_qty"]); s = float(b["scrap_qty"])
        rows.append([b["id"], b["date"].isoformat(), b["line"], b["sku"], b["type"], b["of"], b["inp"], g, s, b["inp"], g, s])
    write_xlsx(os.path.join(out, "yield.xlsx"), report_workbook(rows, "naive"), creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(1000):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 1000 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
