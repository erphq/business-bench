#!/usr/bin/env python3
"""bom-cost-rollup: material cost per finished product from a multi-level BOM export and a price list.

    python gen.py [--seed N] [--naive DIR]

Business: a steel-furniture fabricator (workbenches, shelving, carts). Engineering's system exports the
bill of materials as parent/component lines, one level at a time; purchasing keeps the price list.
The accountant wants a standard material cost for the five products they sell.

Traps (each caught by a check, see task.yaml):
  * the BOM is parent/component pairs three levels deep; quantities multiply down through
    subassemblies (4 legs x 2.75 ft of tube each)                   (checks: every product cost)
  * fasteners are priced per 100 on the price list (Per column)        (checks: shelving rack; every product cost)
  * the drawer unit has a superseded Rev A still in the export next to Rev B (checks: 72in workbench; tool station)
  * the new casters are not on the August list; the email carries the price, and last year's
    list in the folder has an old one                                  (check: mobile cart)
  * the export carries a two-line preamble, BOM and CRLF; an obsolete product's BOM is still in it
  * totals must be live formulas                                        (check: live formulas)
"""
from __future__ import annotations
import argparse
import os
import sys

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


# code, description, per (1 or 100), price range, uom
PARTS = [
    ("TUB-2020", "Steel tube 2x2 11ga", "ft", 3.40, 4.20),
    ("TUB-1515", "Steel tube 1.5x1.5 14ga", "ft", 2.10, 2.70),
    ("ANG-1010", "Steel angle 1x1 x 1/8", "ft", 0.95, 1.35),
    ("PLT-0404", "Base plate 4x4 x 1/4", "each", 2.40, 3.10),
    ("LEV-58", "Leveling foot 5/8-11", "each", 2.80, 3.60),
    ("TOP-7230", "Maple butcher block top 72x30", "each", 170.0, 205.0),
    ("TOP-4830", "Maple butcher block top 48x30", "each", 118.0, 140.0),
    ("SHF-4818", "Steel shelf panel 48x18", "each", 19.0, 26.0),
    ("SHT-1624", "Sheet steel 16ga 24x48", "each", 27.0, 35.0),
    ("BLT-M10", "Hex bolt M10x30 zinc", "100", 12.50, 16.90),
    ("NUT-M10", "Nylock nut M10", "each", 0.06, 0.11),
    ("SLD-18", "Drawer slide 18in full extension (pair)", "each", 15.0, 20.0),
    ("SLD-18L", "Drawer slide 18in light duty (pair)", "each", 8.5, 11.0),
    ("PUL-01", "Drawer pull 4in", "each", 3.80, 4.80),
    ("CST-5", "Caster 5in swivel with brake", "each", 13.50, 15.90),
    ("PEG-2448", "Pegboard panel 24x48", "each", 16.0, 21.0),
    ("OUT-6", "Power strip 6-outlet 15A", "each", 24.0, 31.0),
    ("HDL-12", "Push handle 12in", "each", 6.0, 9.0),
]
UOM = {"ft": "FT", "each": "EA", "100": "EA"}
FT_PARTS = {p[0] for p in PARTS if p[2] == "ft"}
CASTER = "CST-5"
BOLT = "BLT-M10"
NEW_SLIDE, OLD_SLIDE = "SLD-18", "SLD-18L"

PRODUCTS = [("IW-7230", "Workbench 72in with drawers"), ("IW-4830", "Workbench 48in"),
            ("IW-SR5", "Shelving rack 5-tier"), ("IW-MC2", "Mobile cart 2-shelf"), ("IW-TS1", "Tool station")]
SUB_DESC = {"SA-LEG": "Leg assembly", "SA-FRM72": "Frame weldment 72", "SA-FRM48": "Frame weldment 48",
            "SA-DBX": "Drawer box", "SA-DRW": "Drawer unit", "SA-UPR": "Upright frame", "SA-CKT": "Caster kit",
            "SA-FRMC": "Cart frame", "SA-SHF": "Shelf assembly 48x18", "SA-PEG": "Pegboard panel assembly", "IW-6030": "Workbench 60in (discontinued)"}


def build(seed: int) -> dict:
    r = rng(seed)
    price = {}
    for code_, desc, per, lo, hi in PARTS:
        price[code_] = round(r.uniform(lo, hi), 2)
    old_price = {k: round(v * r.uniform(0.88, 0.95), 2) for k, v in price.items()}
    old_price[CASTER] = round(price[CASTER] * r.uniform(0.72, 0.82), 2)
    leg_ft = r.choice([2.5, 2.75, 3.0])
    q = lambda *opts: r.choice(opts)  # noqa: E731
    # bom[parent] = list of (rev, status, component, qty)
    bom = {
        "SA-LEG": [("B", "Released", "TUB-2020", leg_ft), ("B", "Released", "PLT-0404", 1), ("B", "Released", "LEV-58", 1)],
        "SA-FRM72": [("A", "Released", "SA-LEG", 4), ("A", "Released", "TUB-2020", q(12.5, 13.0, 13.5)),
                     ("A", "Released", BOLT, 8)],
        "SA-FRM48": [("A", "Released", "SA-LEG", 4), ("A", "Released", "TUB-2020", q(8.5, 9.0, 9.5)),
                     ("A", "Released", BOLT, 8)],
        "SA-DBX": [("A", "Released", "SHT-1624", 0.5), ("A", "Released", "PUL-01", 1)],
        "SA-DRW": [("A", "Superseded", "SA-DBX", 1), ("A", "Superseded", OLD_SLIDE, 1), ("A", "Superseded", BOLT, 4),
                   ("B", "Released", "SA-DBX", 1), ("B", "Released", NEW_SLIDE, 1), ("B", "Released", BOLT, q(6, 8))],
        "SA-UPR": [("A", "Released", "TUB-1515", q(11.0, 12.0)), ("A", "Released", "ANG-1010", q(3.0, 3.5)),
                   ("A", "Released", "PLT-0404", 2)],
        "SA-CKT": [("C", "Released", CASTER, 4), ("C", "Released", BOLT, 16), ("C", "Released", "NUT-M10", 16)],
        "SA-FRMC": [("A", "Released", "TUB-1515", q(13.0, 14.0, 15.0)), ("A", "Released", "ANG-1010", q(5.0, 6.0)),
                    ("A", "Released", "HDL-12", 1), ("A", "Released", BOLT, 8)],
        "SA-PEG": [("A", "Released", "PEG-2448", 1), ("A", "Released", "ANG-1010", q(7.0, 8.0)),
                   ("A", "Released", BOLT, 6)],
        "IW-7230": [("D", "Released", "SA-FRM72", 1), ("D", "Released", "TOP-7230", 1), ("D", "Released", "SA-DRW", 2),
                    ("D", "Released", BOLT, 12), ("D", "Released", "NUT-M10", 12)],
        "IW-4830": [("C", "Released", "SA-FRM48", 1), ("C", "Released", "TOP-4830", 1), ("C", "Released", "SA-DRW", 1),
                    ("C", "Released", BOLT, 8), ("C", "Released", "NUT-M10", 8)],
        "IW-SR5": [("B", "Released", "SA-UPR", 2), ("B", "Released", "SHF-4818", 5), ("B", "Released", BOLT, 40),
                   ("B", "Released", "NUT-M10", 40)],
        "SA-SHF": [("A", "Released", "SHF-4818", 1), ("A", "Released", "ANG-1010", q(6.0, 7.0)),
                   ("A", "Released", BOLT, 4), ("A", "Released", "NUT-M10", 4)],
        "IW-MC2": [("A", "Released", "SA-FRMC", 1), ("A", "Released", "SA-CKT", 1), ("A", "Released", "SA-SHF", 2),
                   ("A", "Released", BOLT, 8)],
        "IW-TS1": [("A", "Released", "SA-FRM48", 1), ("A", "Released", "SA-PEG", 1), ("A", "Released", "SA-CKT", 1),
                   ("A", "Released", "SA-DRW", 3), ("A", "Released", "OUT-6", 1), ("A", "Released", "SHF-4818", 1)],
        "IW-6030": [("B", "Obsolete", "SA-FRM48", 1), ("B", "Obsolete", "TOP-4830", 1), ("B", "Obsolete", BOLT, 8)],
    }
    return {"price": price, "old_price": old_price, "bom": bom}


def explode(bom: dict, item: str, mult: float = 1.0, *, multiply: bool = True, superseded: bool = False,
            level: int = 1, path: str = "") -> list[tuple]:
    """Leaf lines (component, extended qty, level, path) under item."""
    out = []
    for rev, status, comp, qty in bom[item]:
        if status == "Superseded" and not superseded:
            continue
        ext = mult * qty if multiply else qty
        p = f"{path} > {comp}" if path else comp
        if comp in bom:
            out += explode(bom, comp, ext, multiply=multiply, superseded=superseded, level=level + 1, path=p)
        else:
            out.append((comp, ext, level, p))
    return out


def unit_cost(price: dict, comp: str, per100_as_each: bool = False) -> float:
    per = next(p[2] for p in PARTS if p[0] == comp)
    return price[comp] if (per != "100" or per100_as_each) else price[comp] / 100.0


def cost(d: dict, item: str, **kw) -> float:
    price = kw.pop("price", d["price"])
    each = kw.pop("per100_as_each", False)
    return round(sum(ext * unit_cost(price, c, each) for c, ext, _, _ in explode(d["bom"], item, **kw)), 2)


def truth(d: dict) -> dict:
    return {code_: cost(d, code_) for code_, _ in PRODUCTS}


def variants(d: dict) -> dict:
    old_caster = dict(d["price"]); old_caster[CASTER] = d["old_price"][CASTER]
    return {
        "no_multiply": {c: cost(d, c, multiply=False) for c, _ in PRODUCTS},
        "per100_each": {c: cost(d, c, per100_as_each=True) for c, _ in PRODUCTS},
        "superseded": {c: cost(d, c, superseded=True) for c, _ in PRODUCTS},
        "old_caster": {c: cost(d, c, price=old_caster) for c, _ in PRODUCTS},
        "old_list": {c: cost(d, c, price=d["old_price"]) for c, _ in PRODUCTS},
    }


def acceptable(d: dict) -> bool:
    t = truth(d); v = variants(d)
    vals = sorted(t.values())
    if any(b - a < 0.03 * b for a, b in zip(vals, vals[1:])):
        return False
    moves = lambda name, codes: all(abs(v[name][c] - t[c]) > 0.02 * t[c] for c in codes)  # noqa: E731
    return (moves("no_multiply", [c for c, _ in PRODUCTS]) and moves("per100_each", [c for c, _ in PRODUCTS])
            and moves("superseded", ["IW-7230", "IW-TS1"]) and moves("old_caster", ["IW-MC2"])
            and moves("old_list", [c for c, _ in PRODUCTS]))


# --------------------------------------------------------------------------- files

def price_rows(price: dict, include_caster: bool) -> list[list]:
    rows = []
    vendors = {"TUB": "Dorsey Metals", "ANG": "Dorsey Metals", "PLT": "Dorsey Metals", "SHT": "Dorsey Metals",
               "BLT": "Fastenal", "NUT": "Fastenal", "LEV": "Fastenal", "TOP": "Hardwood Supply Co",
               "SHF": "Westgate Storage", "SLD": "Accuride dealer", "PUL": "Accuride dealer", "CST": "Silverline Casters",
               "PEG": "Westgate Storage", "OUT": "Grainger", "HDL": "Grainger"}
    for code_, desc, per, _, _ in PARTS:
        if code_ == CASTER and not include_caster:
            continue
        rows.append([code_, desc, vendors[code_.split("-")[0]], f"${price[code_]:,.2f}", per])
    return rows


def solution_sheets(d: dict, rows_by_product: dict | None = None, unit_per: dict | None = None) -> dict:
    price = d["price"]
    parts = [p for p in PARTS]
    prow = []
    for i, (code_, desc, per, _, _) in enumerate(parts, start=2):
        per_n = 100 if per == "100" else 1
        if unit_per is not None:
            per_n = unit_per.get(code_, per_n)
        note = "email 3 Sep (not on August list)" if code_ == CASTER else ("per 100" if per == "100" else per)
        prow.append([code_, desc, price[code_] if unit_per is None else unit_per.get("_price", price)[code_], per_n,
                     f"=ROUND(C{i}/D{i},4)", note])
    np_ = len(prow) + 1
    erow = []
    for code_, _ in PRODUCTS:
        lines = rows_by_product[code_] if rows_by_product else explode(d["bom"], code_)
        for comp, ext, level, path in lines:
            erow.append([code_, level, path, comp, round(ext, 4)])
    ne = len(erow) + 1
    for i, row in enumerate(erow, start=2):
        row += [f"=VLOOKUP(D{i},Prices!$A$2:$E${np_},5,FALSE)", f"=ROUND(E{i}*F{i},4)"]
    srow = []
    for i, (code_, desc) in enumerate(PRODUCTS, start=2):
        srow.append([code_, desc, f"=ROUND(SUMIF(Exploded!$A$2:$A${ne},A{i},Exploded!$G$2:$G${ne}),2)"])
    return {
        "Summary": {"header": ["Item", "Description", "Material cost"], "rows": srow, "widths": {"A": 12, "B": 32, "C": 15}},
        "Exploded": {"header": ["Product", "Level", "Path", "Component", "Extended qty", "Unit cost", "Extended cost"],
                     "rows": erow, "widths": {"C": 44}},
        "Prices": {"header": ["Part", "Description", "Price", "Per", "Unit cost", "Note"], "rows": prow,
                   "widths": {"B": 40, "F": 30}},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    t = truth(d)
    if naive_dir:
        # The obvious shortcut: take every line under a product at its own qty-per (no multiplying down the tree),
        # every revision in the export, the Price column as the price of one unit, and last year's caster price.
        os.makedirs(naive_dir, exist_ok=True)
        rows = {c: explode(d["bom"], c, multiply=False, superseded=True) for c, _ in PRODUCTS}
        naive_price = dict(d["price"]); naive_price[CASTER] = d["old_price"][CASTER]
        per = {p[0]: 1 for p in PARTS}; per["_price"] = naive_price
        write_xlsx(os.path.join(naive_dir, "assembly_costs.xlsx"), solution_sheets(d, rows, per), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)

    bom_rows = []
    for parent in ["IW-4830", "IW-6030", "IW-7230", "IW-MC2", "IW-SR5", "IW-TS1", "SA-CKT", "SA-DBX", "SA-DRW",
                   "SA-FRM48", "SA-FRM72", "SA-FRMC", "SA-LEG", "SA-PEG", "SA-SHF", "SA-UPR"]:
        pdesc = dict(PRODUCTS).get(parent) or SUB_DESC[parent]
        for seq, (rev, status, comp, qty) in enumerate(d["bom"][parent], start=1):
            cdesc = dict(PRODUCTS).get(comp) or SUB_DESC.get(comp) or next(p[1] for p in PARTS if p[0] == comp)
            uom = UOM[next(p[2] for p in PARTS if p[0] == comp)] if comp not in d["bom"] else "EA"
            qtxt = f"{qty:.2f}" if isinstance(qty, float) and qty != int(qty) else f"{int(qty)}"
            bom_rows.append([parent, pdesc, rev, status, seq * 10, comp, cdesc, qtxt, uom])
    write_csv(os.path.join(ws, "bom_export_2026-09-02.csv"),
              ["Parent Item", "Parent Description", "Rev", "Status", "Seq", "Component", "Component Description",
               "Qty Per", "UoM"], bom_rows,
              preamble=["Ironwood Fabrication - Bill of Materials (single level, all parents)", "Printed 09/02/2026 07:41"],
              bom=True, crlf=True)
    write_xlsx(os.path.join(ws, "price_list_2026-08.xlsx"), {"Prices": {
        "merged_title": "Purchased parts price list - August 2026",
        "preamble": [["Maintained by purchasing (K. Osei). Prices exclude freight."]],
        "header": ["Part", "Description", "Vendor", "Price", "Per"], "rows": price_rows(d["price"], False),
        "widths": {"A": 12, "B": 40, "C": 22, "D": 12, "E": 8}}}, creator="Purchasing")
    write_xlsx(os.path.join(ws, "price_list_2025.xlsx"), {"Prices": {
        "merged_title": "Purchased parts price list - 2025",
        "header": ["Part", "Description", "Vendor", "Price", "Per"], "rows": price_rows(d["old_price"], True),
        "widths": {"A": 12, "B": 40, "C": 22, "D": 12, "E": 8}}}, creator="Purchasing")
    write_email_thread(os.path.join(ws, "email_from_dale.txt"), [
        {"from": "Dale Morgan <dale@ironwoodfab.com>", "to": "you", "date": "Wed, 3 Sep 2026 16:05",
         "subject": "material cost per product",
         "body": ("Ruth (our accountant) needs a standard material cost for the five things we actually sell: "
                  "IW-7230, IW-4830, IW-SR5, IW-MC2 and IW-TS1. Material only - no labor, no powder coat, no freight.\n\n"
                  "Engineering exported the bills of materials this morning; the subassemblies have their own bills "
                  "in the same export. Use whatever revision is current; engineering changed the drawer slides in the "
                  "spring and the old revision is still sitting in the system.\n\n"
                  "Prices: use Kwame's August price list. Ignore the 2025 one, it's only there because nobody "
                  "cleans up this folder.")},
        {"from": "Dale Morgan <dale@ironwoodfab.com>", "to": "you", "date": "Wed, 3 Sep 2026 16:22",
         "subject": "RE: material cost per product",
         "body": (f"Forgot one thing. We switched caster suppliers in July and the new casters ({CASTER}) aren't on "
                  f"the August list yet. Silverline quoted ${d['price'][CASTER]:.2f} each, use that.\n\n"
                  "Please build it so I can change a price and see the product costs move - Ruth will ask "
                  "again when steel goes up.")}])

    # ---- reference ----
    write_csv(os.path.join(ref, "assembly_costs.csv"), ["item", "description", "material_cost"],
              [[c, desc, f"{t[c]:.2f}"] for c, desc in PRODUCTS])
    v = variants(d)
    write_json(os.path.join(ref, "notes.json"), {"costs": t, "naive_variants": v, "caster_price": d["price"][CASTER]})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "assembly_costs.xlsx"), solution_sheets(d), creator="reference")

    names = {"IW-7230": "72in workbench", "IW-4830": "48in workbench", "IW-SR5": "shelving rack",
             "IW-MC2": "mobile cart", "IW-TS1": "tool station"}
    checks = [
        {"type": "file_exists", "name": "assembly_costs.xlsx exists", "path": "assembly_costs.xlsx"},
        {"type": "xlsx_has_formulas", "name": "live formulas", "path": "assembly_costs.xlsx", "min_count": 5},
        {"type": "xlsx_no_errors", "name": "no error cells", "path": "assembly_costs.xlsx"},
    ]
    for c, _ in PRODUCTS:
        checks.append({"type": "xlsx_value_present", "name": f"{c} {names[c]} cost", "path": "assembly_costs.xlsx",
                       "expected": t[c], "rel_tol": cent_tol(t[c]), "near_text": c.lower()})
    write_task_yaml(HERE, {
        "id": "bom-cost-rollup", "track": "desk", "category": "spreadsheet",
        "title": "Material cost per product from the bill of materials",
        "ask": ("Our accountant needs the material cost of each product we sell. Work it out from the BOM export and "
                "the price list and give me assembly_costs.xlsx, built so I can change a price later. Dale's email "
                "has the details.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the BOM export is single-level parent/component lines three levels deep (product > frame > leg > tube, "
            "product > drawer unit > drawer box > sheet); each quantity has to be multiplied by every quantity above "
            "it, and taking each line at its own qty-per undercounts legs, tube, shelves and drawer boxes "
            "(checks: IW-7230 72in workbench cost; IW-TS1 tool station cost; IW-MC2 mobile cart cost)",
            "bolts are priced per 100 on the August list (the Per column says 100); reading the Price column as the "
            "price of one bolt multiplies the rack's cost several times over (check: IW-SR5 shelving rack cost)",
            "the drawer unit SA-DRW still has its superseded Rev A lines in the export next to Rev B; counting both "
            "doubles the drawer box and adds the old light-duty slides to every product with drawers "
            "(checks: IW-7230 72in workbench cost; IW-TS1 tool station cost)",
            "the new casters are not on the August price list; the second email carries the quote, and the 2025 list "
            "still in the folder has an older, lower caster price and lower prices for everything else "
            "(checks: IW-MC2 mobile cart cost; IW-4830 48in workbench cost)",
            "the export has a two-line preamble above the header, a BOM and CRLF endings, and prices on the list are "
            "text like '$15.07' under a merged title row (check: IW-4830 48in workbench cost)",
            "the owner wants to change a price and see costs move, so the product costs must be live formulas "
            "(check: live formulas)",
        ],
        "checks": checks,
    })
    print(f"seed={seed}", t)


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
