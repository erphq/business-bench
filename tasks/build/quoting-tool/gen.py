#!/usr/bin/env python3
"""Deterministic seed generator for the quoting-tool build task.

    python gen.py [--seed N]

Writes:
  seed/products.csv       60 products x board feet and labor cost: exact duplicates, SKUs re-keyed in
                          lower case or with a trailing space, labor costs as "$1,280.00" strings
  seed/materials.csv      60 lumber prices per board foot: duplicate rows, "$16.37" strings, mixed units and dates
  seed/quotes.csv         quote lines since November 2025: duplicated lines, discounts written "5%" or
                          "0.05", rep names in mixed case, SKU/material codes in mixed case, one negative quantity
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the public variant checklist.md quotes. Other seeds re-roll customers, quote contents, prices,
and lumber costs; counts.json is recomputed, so re-derive the checklist from it.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import COMPANIES, FIRST, LAST, argparse_seed, date_variant, write_csv, write_text  # noqa: E402

SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")
COMPANY = "Fernhill Furniture Works"
REPS = ["Jordan Price", "Aaliyah Brooks", "Sven Lindqvist"]
RESTRICTED = "Aaliyah Brooks"
MARGIN_FLOOR = 0.30
DISCOUNT_APPROVAL_OVER = 0.10
# type code, name, board feet, labor, family
TYPES = [
    ("DT60", 'Dining Table 60"', 38, 1150, "table"), ("DT72", 'Dining Table 72"', 44, 1280, "table"),
    ("DT84", 'Dining Table 84"', 52, 1420, "table"), ("DT96", 'Dining Table 96"', 60, 1560, "table"),
    ("CT", "Coffee Table", 18, 520, "table"), ("CON", "Console Table", 16, 480, "table"),
    ("WD", "Writing Desk", 28, 860, "case"), ("BS4", "Bookshelf, 4 shelves", 32, 640, "case"),
    ("SB", "Sideboard", 46, 1380, "case"), ("DR6", "Dresser, 6 drawers", 54, 1620, "case"),
    ("NS", "Nightstand", 12, 390, "case"), ("BN48", 'Bench 48"', 14, 360, "seat"),
    ("DC", "Dining Chair", 7, 310, "seat"), ("BST", "Bar Stool", 6, 280, "seat"), ("BFQ", "Bed Frame, Queen", 48, 1180, "case"),
]
COLLECTIONS = [("SHK", "Shaker", 1.00, 1.00), ("MCM", "Mid-Century", 1.00, 1.10), ("FRM", "Farmhouse", 1.15, 1.00), ("STD", "Studio", 0.95, 0.95)]
SPECIES = [("WAL", "Walnut", 12.40), ("WO", "White Oak", 8.90), ("RO", "Red Oak", 6.20), ("CHE", "Cherry", 9.60),
           ("HM", "Hard Maple", 7.40), ("ASH", "Ash", 5.80), ("HIC", "Hickory", 6.60), ("SAP", "Sapele", 10.20),
           ("MAH", "Mahogany", 13.80), ("POP", "Poplar", 3.90)]
THICK = [("44", "4/4", 1.00), ("64", "6/4", 1.18), ("84", "8/4", 1.32)]
GRADES = [("FAS", "FAS", 1.00), ("SEL", "Select", 0.86)]
SUPPLIERS = ["Northland Hardwoods", "Keystone Lumber Co.", "Riverside Timber", "Appalachian Sawmill Supply"]
FAMILY_THICK = {"table": ["84", "64"], "case": ["64", "44"], "seat": ["44", "64"]}
STATUS_COUNTS = {"Won": 30, "Lost": 36, "Expired": 10, "Sent": 24, "Draft": 20}
OPEN = ("Draft", "Sent")
N_DUP_LINES = 5
SAFE_DATE_STYLES = [0, 1, 2, 3, 4]


def r5(x: float) -> float:
    return float(int(round(x / 5.0)) * 5)


def build(seed: int) -> dict:
    rng = random.Random(seed)

    # ------------------------------------------------------------------ products
    products: list[dict] = []
    for ccode, cname, bf_mult, lab_mult in COLLECTIONS:
        for tcode, tname, bf, labor, fam in TYPES:
            b = round(bf * bf_mult)
            lab = r5(labor * lab_mult)
            if seed != 0:
                lab = r5(lab * rng.uniform(0.92, 1.08))
            products.append({"sku": f"{ccode}-{tcode}", "name": f"{cname} {tname}", "collection": cname, "bf": b,
                             "labor": lab, "family": fam, "lead": rng.choice([6, 8, 8, 10, 12])})
    assert len(products) == 60
    prod = {p["sku"]: p for p in products}

    # ------------------------------------------------------------------ materials
    materials: list[dict] = []
    for scode, sname, base in SPECIES:
        if seed != 0:
            base = round(base * rng.uniform(0.9, 1.1), 2)
        for tcode, tname, tm in THICK:
            for gcode, gname, gm in GRADES:
                materials.append({"code": f"{scode}-{tcode}-{gcode}", "name": f"{sname} {tname} {gname}", "species": sname,
                                  "thick": tname, "tcode": tcode, "grade": gname, "cost": round(base * tm * gm, 2)})
    mat = {m["code"]: m for m in materials}
    top_mat = max(materials, key=lambda m: m["cost"])
    assert sum(1 for m in materials if m["cost"] == top_mat["cost"]) == 1

    def unit_cost(sku: str, code: str) -> float:
        return round(prod[sku]["bf"] * mat[code]["cost"] + prod[sku]["labor"], 2)

    def margin(price: float, disc: float, cost: float) -> float:
        net = price * (1 - disc)
        return (net - cost) / net

    # ------------------------------------------------------------------ product rows
    prod_rows: list[dict] = []
    dollar_labor = set(rng.sample([p["sku"] for p in products], 12)) | {"SHK-DT72"}
    for p in products:
        list_price = r5((p["bf"] * 9.5 + p["labor"]) / 0.55)
        p["list"] = list_price
        labor_txt = f"${p['labor']:,.2f}" if p["sku"] in dollar_labor else (f"{p['labor']:.2f}" if rng.random() < 0.6 else f"{p['labor']:.0f}")
        prod_rows.append({"p": p, "role": "unique", "cells": [p["sku"], p["name"], p["collection"], str(p["bf"]), labor_txt,
                                                              f"{list_price:,.2f}" if rng.random() < 0.3 else f"{list_price:.2f}", str(p["lead"])]})
    exact_prod = rng.sample([r for r in prod_rows if r["p"]["sku"] != "SHK-DT72"], 2)
    for r in exact_prod:
        prod_rows.append({"p": r["p"], "role": "exact_duplicate", "cells": list(r["cells"])})
    rekey = rng.sample([r for r in prod_rows if r["role"] == "unique" and r not in exact_prod and r["p"]["sku"] != "SHK-DT72"], 2)
    rekey_forms = []
    for k, r in enumerate(rekey):
        form = r["p"]["sku"].lower() if k == 0 else r["p"]["sku"] + " "
        rekey_forms.append(form)
        cells = list(r["cells"])
        cells[0] = form
        prod_rows.append({"p": r["p"], "role": "rekeyed", "cells": cells})
    rng.shuffle(prod_rows)
    for line, r in enumerate(prod_rows, start=2):
        r["line"] = line

    # ------------------------------------------------------------------ material rows
    mat_rows: list[dict] = []
    for m in materials:
        cost_txt = f"${m['cost']:.2f}" if (rng.random() < 0.25 or m is top_mat) else f"{m['cost']:.2f}"
        unit = rng.choice(["bf", "bf", "BF", "board ft"])
        updated = date(2026, 1, 5) + timedelta(days=rng.randint(0, 220))
        mat_rows.append({"m": m, "cells": [m["code"], m["name"], m["species"], m["thick"], m["grade"], unit, cost_txt,
                                           rng.choice(SUPPLIERS), date_variant(updated, rng.choice(SAFE_DATE_STYLES))]})
    mat_dupes = rng.sample(mat_rows, 2)
    mat_rows += [{"m": r["m"], "cells": list(r["cells"])} for r in mat_dupes]
    rng.shuffle(mat_rows)
    text_top_mat = max(mat_rows, key=lambda r: r["cells"][6])

    # ------------------------------------------------------------------ customers
    people = [(f, l) for f in FIRST for l in LAST if l not in ("Price", "Brooks", "Lindqvist")]
    rng.shuffle(people)
    lasts_used: set[str] = set()
    customers: list[str] = []
    for f, l in people:
        if l in lasts_used:
            continue
        lasts_used.add(l)
        customers.append(f"{f} {l}")
        if len(customers) == 70:
            break
    customers += [c[0] for c in rng.sample(COMPANIES, 20)]

    # ------------------------------------------------------------------ quotes
    statuses = [s for s, n in STATUS_COUNTS.items() for _ in range(n)]
    rng.shuffle(statuses)
    quotes: list[dict] = []
    for st in statuses:
        if st in OPEN:
            qd = date(2026, 7, 20) + timedelta(days=rng.randint(0, 52))
        elif st == "Expired":
            qd = date(2025, 11, 3) + timedelta(days=rng.randint(0, 200))
        else:
            qd = date(2025, 11, 3) + timedelta(days=rng.randint(0, 280))
        if st in OPEN:
            disc = rng.choice([0, 0, 0, 0.05, 0.05, 0.10])
        else:
            disc = rng.choice([0, 0, 0.05, 0.05, 0.10, 0.12, 0.15])
        quotes.append({"status": st, "date": qd, "disc": disc, "rep": rng.choice(REPS),
                       "customer": rng.choice(customers), "lines": [],
                       "decided": qd + timedelta(days=rng.randint(5, 40)) if st in ("Won", "Lost") else None})
    quotes.sort(key=lambda q: (q["date"], q["customer"]))
    for i, q in enumerate(quotes):
        q["no"] = f"Q-{2101 + i}"

    def pick_line(q: dict, lo: float, hi: float) -> dict:
        p = rng.choice(products)
        t = rng.choice(FAMILY_THICK[p["family"]])
        code = f"{rng.choice(SPECIES)[0]}-{t}-{rng.choice(['FAS', 'FAS', 'SEL'])}"
        qty = rng.randint(2, 8) if p["sku"].endswith(("-DC", "-BST")) else rng.choice([1, 1, 1, 2])
        cost = unit_cost(p["sku"], code)
        for _ in range(200):
            m = rng.uniform(lo, hi)
            price = r5(cost / (1 - m) / (1 - q["disc"]))
            if lo <= margin(price, q["disc"], cost) <= hi:
                break
        else:
            raise AssertionError("no price")
        return {"sku": p["sku"], "code": code, "qty": qty, "price": price, "cost": cost}

    for q in quotes:
        n = rng.choices([1, 2, 3], [45, 35, 20])[0]
        lo = 0.35 if q["status"] in OPEN else 0.32
        q["lines"] = [pick_line(q, lo, 0.55) for _ in range(n)]

    open_quotes = [q for q in quotes if q["status"] in OPEN]
    reserved: set[str] = set()

    def take(cands: list[dict]) -> dict:
        c = rng.choice([q for q in cands if q["no"] not in reserved])
        reserved.add(c["no"])
        return c

    # margin traps on open quotes
    q_a = take([q for q in open_quotes if q["status"] == "Sent" and q["disc"] == 0 and q["rep"] != RESTRICTED])
    q_c = take([q for q in open_quotes if q["disc"] == 0.10])
    q_b = take([q for q in open_quotes if q["status"] == "Sent" and q["rep"] != RESTRICTED])
    extra_flag = [take([q for q in open_quotes]) for _ in range(2)]

    def force_margin(q: dict, lo: float, hi: float, before_lo=None, before_hi=None) -> dict:
        line = q["lines"][0]
        for _ in range(2000):
            m = rng.uniform(lo, hi)
            price = r5(line["cost"] / (1 - m) / (1 - q["disc"]))
            after = margin(price, q["disc"], line["cost"])
            before = margin(price, 0, line["cost"])
            if lo <= after <= hi and (before_lo is None or before_lo <= before <= before_hi):
                line["price"] = price
                return line
        raise AssertionError("cannot force margin")

    force_margin(q_a, 0.265, 0.285)
    force_margin(q_c, 0.255, 0.275, 0.33, 0.35)
    force_margin(q_b, 0.305, 0.318)
    for q in extra_flag:
        force_margin(q, 0.20, 0.29)

    # negative quantity on a Draft quote
    q_neg = take([q for q in open_quotes if q["status"] == "Draft" and len(q["lines"]) >= 2 and q["rep"] != RESTRICTED])
    neg_line = q_neg["lines"][1]
    neg_line["qty"] = -2

    # item 19: one of the restricted rep's Sent quotes the tester marks Lost
    q_s = take([q for q in open_quotes if q["status"] == "Sent" and q["rep"] == RESTRICTED])

    def line_total(q: dict, l: dict) -> float:
        return l["qty"] * l["price"]

    def total(q: dict) -> float:
        return round(sum(line_total(q, l) for l in q["lines"]) * (1 - q["disc"]), 2)

    def flagged(q: dict) -> bool:
        return q["status"] in OPEN and any(l["qty"] > 0 and margin(l["price"], q["disc"], l["cost"]) < MARGIN_FLOOR for l in q["lines"])

    flagged_quotes = [q for q in quotes if flagged(q)]
    assert {q["no"] for q in flagged_quotes} == {q_a["no"], q_c["no"]} | {q["no"] for q in extra_flag}
    assert all(margin(l["price"], q["disc"], l["cost"]) >= 0.32 for q in quotes if q["status"] not in OPEN for l in q["lines"])
    assert all(q["disc"] <= DISCOUNT_APPROVAL_OVER for q in open_quotes)

    top = max(quotes, key=total)
    assert sum(1 for q in quotes if total(q) == total(top)) == 1

    # ------------------------------------------------------------------ quote line rows
    def disc_text(d: float) -> str:
        if d == 0:
            return rng.choice(["0", "", "0%"])
        return rng.choice([f"{int(round(d * 100))}%", f"{int(round(d * 100))}%", f"{d:.2f}".rstrip("0")])

    def rep_text(r: str) -> str:
        k = rng.random()
        return r if k > 0.2 else rng.choice([r.lower(), r.upper(), r + " "])

    def price_text(v: float, force: bool = False) -> str:
        if force or rng.random() < 0.3:
            return f"${v:,.2f}"
        return f"{v:.2f}" if rng.random() < 0.7 else f"{v:,.2f}"

    q_rows: list[dict] = []
    for q in quotes:
        d_txt = disc_text(q["disc"])
        r_txt = rep_text(q["rep"])
        qd_txt = date_variant(q["date"], rng.choice(SAFE_DATE_STYLES))
        dd_txt = date_variant(q["decided"], rng.choice(SAFE_DATE_STYLES)) if q["decided"] else ""
        for l in q["lines"]:
            sku_txt = l["sku"] if rng.random() > 0.12 else rng.choice([l["sku"].lower(), l["sku"] + " "])
            code_txt = l["code"] if rng.random() > 0.1 else l["code"].lower()
            force = q is top and l is max(q["lines"], key=lambda x: x["qty"] * x["price"])
            q_rows.append({"q": q, "l": l, "dup": False, "cells": [
                q["no"], qd_txt, r_txt, q["customer"], q["status"] if rng.random() > 0.1 else q["status"].lower(), d_txt,
                sku_txt, code_txt, str(l["qty"]), price_text(l["price"], force), dd_txt]})
    if q_c["disc"] == 0.10:  # the after-discount trap reads best when the discount is written as a fraction
        for r in q_rows:
            if r["q"] is q_c:
                r["cells"][5] = "0.1"
    dup_src = rng.sample([r for r in q_rows if r["q"]["no"] not in reserved and r["q"]["status"] in ("Won", "Sent")], N_DUP_LINES)
    q_rows += [dict(r, cells=list(r["cells"]), dup=True) for r in dup_src]
    order = {q["no"]: i for i, q in enumerate(quotes)}
    q_rows.sort(key=lambda r: (order[r["q"]["no"]], r["q"]["lines"].index(r["l"]), r["dup"]))
    for line, r in enumerate(q_rows, start=2):
        r["line"] = line

    # ------------------------------------------------------------------ figures
    by_status = {s: [q for q in quotes if q["status"] == s] for s in STATUS_COUNTS}

    def rate(won: int, lost: int) -> float:
        return round(100.0 * won / (won + lost), 1)

    def rep_counts(rep: str) -> tuple[int, int]:
        return (sum(1 for q in by_status["Won"] if q["rep"] == rep), sum(1 for q in by_status["Lost"] if q["rep"] == rep))

    won_n, lost_n = len(by_status["Won"]), len(by_status["Lost"])
    aw, al = rep_counts(RESTRICTED)
    sent_value = round(sum(total(q) for q in by_status["Sent"]), 2)
    won_value = round(sum(total(q) for q in by_status["Won"]), 2)
    dup_quotes = [r["q"] for r in dup_src]
    q17 = next((q for q in dup_quotes if q["status"] == "Won" and q["disc"] > 0), dup_quotes[0])
    dup_line17 = next(r["l"] for r in dup_src if r["q"] is q17)
    # search: a person customer with a surname used once and exactly two quotes
    search = None
    for c in sorted(set(q["customer"] for q in quotes)):
        parts = c.split()
        if len(parts) != 2 or c in [x[0] for x in COMPANIES]:
            continue
        n = sum(1 for q in quotes if q["customer"] == c)
        if n == 2 and sum(1 for x in customers if parts[1].lower() in x.lower()) == 1:
            search = c
            break
    assert search
    oos = next(q for q in by_status["Sent"] if q["rep"] == "Jordan Price" and q["no"] not in reserved)

    # tester-built lines
    t_sku, t_code = "SHK-DT72", "WAL-84-FAS"
    t_cost = unit_cost(t_sku, t_code)
    blocked_disc = 0.05
    chair_sku, chair_code, chair_qty = "SHK-DC", "WAL-44-FAS", 6
    chair_cost = unit_cost(chair_sku, chair_code)
    dt96_cost = unit_cost("SHK-DT96", "WAL-84-FAS")
    if seed == 0:  # the public checklist quotes these round prices
        t_price, blocked_price, chair_price = 4250.00, 3000.00, 640.00
    else:  # sealed variants: derive prices that keep the same margin relationships
        t_price = r5(t_cost / (1 - 0.53))
        blocked_price = next(p for p in (r5(t_cost / (1 - m / 1000)) for m in range(305, 345)) if margin(p, blocked_disc, t_cost) < MARGIN_FLOOR <= margin(p, 0, t_cost))
        chair_price = r5(chair_cost / (1 - 0.40))
    t_margin = round(100 * margin(t_price, 0, t_cost), 2)
    floor_price = round(t_cost / (1 - MARGIN_FLOOR), 2)
    assert margin(blocked_price, blocked_disc, t_cost) < MARGIN_FLOOR <= margin(blocked_price, 0, t_cost)
    conv_disc = 0.05
    conv_total = round((t_price * 1 + chair_price * chair_qty) * (1 - conv_disc), 2)
    assert margin(chair_price, conv_disc, chair_cost) >= MARGIN_FLOOR and margin(t_price, conv_disc, t_cost) >= MARGIN_FLOOR
    approve_disc = 0.12
    assert margin(t_price, approve_disc, t_cost) >= MARGIN_FLOOR

    collection_won: dict[str, float] = {c[1]: 0.0 for c in COLLECTIONS}
    for q in by_status["Won"]:
        for l in q["lines"]:
            collection_won[prod[l["sku"]]["collection"]] += l["qty"] * l["price"] * (1 - q["disc"])
    collection_won = {k: round(v, 2) for k, v in collection_won.items()}
    conv_by_collection = {"Shaker": conv_total}
    restricted_collection_won: dict[str, float] = {c[1]: 0.0 for c in COLLECTIONS}
    for q in by_status["Won"]:
        if q["rep"] != RESTRICTED:
            continue
        for l in q["lines"]:
            restricted_collection_won[prod[l["sku"]]["collection"]] += l["qty"] * l["price"] * (1 - q["disc"])
    restricted_collection_won["Shaker"] += conv_total
    restricted_collection_won = {k: round(v, 2) for k, v in restricted_collection_won.items()}
    rep_rates_after = {}
    for rep in REPS:
        w, lo_ = rep_counts(rep)
        if rep == RESTRICTED:
            w, lo_ = w + 1, lo_ + 1  # item 19 marks one of hers Lost; item 25's won quote is hers
        rep_rates_after[rep] = {"won": w, "lost": lo_, "win_rate_pct": rate(w, lo_)}

    def qinfo(q: dict) -> dict:
        return {"quote": q["no"], "customer": q["customer"], "rep": q["rep"], "status": q["status"], "discount": q["disc"],
                "total": total(q), "file_lines": [r["line"] for r in q_rows if r["q"] is q and not r["dup"]]}

    def linfo(q: dict, l: dict) -> dict:
        return {"sku": l["sku"], "material": l["code"], "qty": l["qty"], "unit_price": l["price"], "unit_cost": l["cost"],
                "board_feet": prod[l["sku"]]["bf"], "labor": prod[l["sku"]]["labor"], "material_cost_per_bf": mat[l["code"]]["cost"],
                "margin_before_discount_pct": round(100 * margin(l["price"], 0, l["cost"]), 2),
                "margin_after_discount_pct": round(100 * margin(l["price"], q["disc"], l["cost"]), 2)}

    counts = {
        "seed": seed,
        "company": COMPANY,
        "admin": "the owner",
        "reps": REPS,
        "restricted_login": RESTRICTED,
        "rules": {"margin_floor_after_discount": MARGIN_FLOOR, "discount_needs_approval_over": DISCOUNT_APPROVAL_OVER,
                  "unit_cost": "board feet x material cost per board foot + labor cost",
                  "margin": "(unit price x (1 - discount) - unit cost) / (unit price x (1 - discount))",
                  "win_rate": "won / (won + lost); Expired, Sent, and Draft excluded"},
        "baseline": {
            "staff_role": "Sales Rep",
            "viewer_role": "Viewer",
            "main_entity": "quote",
            "main_entity_plural": "quotes",
            "scope_rule": f"quotes owned by {RESTRICTED}",
            "scope_count": sum(1 for q in quotes if q["rep"] == RESTRICTED),
            "out_of_scope_example": qinfo(oos),
            "kpis": [
                {"name": "Open quotes (Draft or Sent)", "value": len(open_quotes)},
                {"name": "Win rate (won / (won + lost))", "value_pct": rate(won_n, lost_n), "won": won_n, "lost": lost_n},
                {"name": "Out for decision (Sent value after discount)", "value": sent_value},
                {"name": "Won value after discount", "value": won_value},
            ],
            "scoped_kpi_1": sum(1 for q in open_quotes if q["rep"] == RESTRICTED),
            "search": {"term": search.split()[1], "customer": search, "count": 2,
                       "quotes": [q["no"] for q in quotes if q["customer"] == search]},
            "filter": {"field": "Status", "value": "Won", "count": won_n},
            "sort": {"field": "Total", "top": qinfo(top)},
            "export": {"rows": len(quotes), "columns": ["Quote No", "Customer", "Rep", "Status", "Total"]},
            "required_field": "Customer",
            "wrong": {"win_rate_over_all_quotes_pct": round(100.0 * won_n / len(quotes), 1),
                      "win_rate_counting_expired_as_lost_pct": rate(won_n, lost_n + len(by_status["Expired"])),
                      "scope_if_rep_matched_as_written": len({r["q"]["no"] for r in q_rows if r["cells"][2] == RESTRICTED})},
        },
        "products": {
            "file_rows_excluding_header": len(prod_rows),
            "exact_duplicate_rows": 2,
            "rekeyed_duplicate_rows": 2,
            "rekeyed_forms": rekey_forms,
            "unique_products": len(products),
            "per_collection": {c[1]: 15 for c in COLLECTIONS},
            "shk_dt72": {"board_feet": prod["SHK-DT72"]["bf"], "labor": prod["SHK-DT72"]["labor"],
                         "labor_file_value": next(r["cells"][4] for r in prod_rows if r["p"]["sku"] == "SHK-DT72")},
            "shk_dc": {"board_feet": prod["SHK-DC"]["bf"], "labor": prod["SHK-DC"]["labor"]},
        },
        "materials": {
            "file_rows_excluding_header": len(mat_rows),
            "exact_duplicate_rows": 2,
            "unique_materials": len(materials),
            "highest_cost": {"code": top_mat["code"], "cost": top_mat["cost"], "file_value": f"${top_mat['cost']:.2f}"},
            "text_sort_top": {"code": text_top_mat["cells"][0], "file_value": text_top_mat["cells"][6]},
            "wal_84_fas": mat["WAL-84-FAS"]["cost"],
            "wal_44_fas": mat["WAL-44-FAS"]["cost"],
        },
        "quotes": {
            "file_rows_excluding_header": len(q_rows),
            "duplicate_line_rows": N_DUP_LINES,
            "quotes": len(quotes),
            "per_status": {s: len(v) for s, v in by_status.items()},
            "per_rep": {rep: sum(1 for q in quotes if q["rep"] == rep) for rep in REPS},
            "item17_quote_with_duplicated_line": {**qinfo(q17), "discount_as_written": next(r["cells"][5] for r in q_rows if r["q"] is q17),
                                                  "total_with_duplicate_kept": round(total(q17) + dup_line17["qty"] * dup_line17["price"] * (1 - q17["disc"]), 2),
                                                  "total_ignoring_discount": round(sum(l["qty"] * l["price"] for l in q17["lines"]), 2)},
            "negative_quantity": {**qinfo(q_neg), "sku": neg_line["sku"], "qty": -2},
            "win_rate": {"company_pct": rate(won_n, lost_n), "won": won_n, "lost": lost_n, "decided": won_n + lost_n,
                         "restricted_decided": aw + al,
                         "restricted_pct": rate(aw, al), "restricted_won": aw, "restricted_lost": al,
                         "mark_lost_quote": qinfo(q_s),
                         "company_after_mark_lost_pct": rate(won_n, lost_n + 1),
                         "restricted_after_mark_lost_pct": rate(aw, al + 1)},
            "margin_flagged_open_quotes": [dict(qinfo(q), lines=[linfo(q, l) for l in q["lines"]]) for q in flagged_quotes],
            "q_a_flagged": dict(qinfo(q_a), line=linfo(q_a, q_a["lines"][0])),
            "q_c_flagged_after_discount": dict(qinfo(q_c), line=linfo(q_c, q_c["lines"][0]),
                                               discount_as_written=next(r["cells"][5] for r in q_rows if r["q"] is q_c)),
            "q_b_not_flagged": dict(qinfo(q_b), line=linfo(q_b, q_b["lines"][0])),
        },
        "app_items": {
            "line_test": {"sku": t_sku, "material": t_code, "board_feet": prod[t_sku]["bf"], "material_cost_per_bf": mat[t_code]["cost"],
                          "labor": prod[t_sku]["labor"], "unit_cost": t_cost, "unit_price": t_price, "margin_pct": t_margin},
            "floor_test": {"price": blocked_price, "discount": blocked_disc, "net": round(blocked_price * (1 - blocked_disc), 2),
                           "margin_after_discount_pct": round(100 * margin(blocked_price, blocked_disc, t_cost), 2),
                           "margin_without_discount_pct": round(100 * margin(blocked_price, 0, t_cost), 2),
                           "floor_price_no_discount": floor_price},
            "discount_test": {"discount": approve_disc, "unit_price": t_price, "margin_after_discount_pct": round(100 * margin(t_price, approve_disc, t_cost), 2),
                              "allowed_without_approval": 0.10},
            "conversion_test": {"lines": [{"sku": t_sku, "material": t_code, "qty": 1, "unit_price": t_price, "unit_cost": t_cost},
                                          {"sku": chair_sku, "material": chair_code, "qty": chair_qty, "unit_price": chair_price, "unit_cost": chair_cost,
                                           "margin_after_discount_pct": round(100 * margin(chair_price, conv_disc, chair_cost), 2)}],
                                "discount": conv_disc, "subtotal": t_price + chair_price * chair_qty, "total": conv_total},
        },
        "changes": {
            "1_won_value_by_collection_imported": collection_won,
            "1_won_value_by_collection_with_item25": {k: round(v + conv_by_collection.get(k, 0.0), 2) for k, v in collection_won.items()},
            "1_rep_win_rates_after_items_19_and_25": rep_rates_after,
            "1_restricted_won_value_by_collection_with_item25": restricted_collection_won,
            "1_restricted_shaker_won_value_imported": round(restricted_collection_won["Shaker"] - conv_total, 2),
            "1_per_extra_conversion_test": {"won_value": conv_total, "restricted_won": 1, "restricted_decided": 1},
            "2_deposit_rate": 0.5,
            "2_deposit_on_item25_order": round(conv_total * 0.5, 2),
            "3_shop_review_at_or_over": 10000.00,
            "3_tests": {"over": {"sku": "SHK-DT96", "material": "WAL-84-FAS", "qty": 2, "unit_price": 5000.00, "total": 10000.00},
                        "under": {"sku": "SHK-DT96", "material": "WAL-84-FAS", "qty": 2, "unit_price": 4995.00, "total": 9990.00},
                        "margins_pct": {"5000": round(100 * margin(5000.0, 0, dt96_cost), 2),
                                        "4995": round(100 * margin(4995.0, 0, dt96_cost), 2)}},
            "2_second_order_test": {"sku": chair_sku, "material": chair_code, "qty": 2, "unit_price": chair_price, "discount": 0,
                                    "total": 2 * chair_price, "deposit": round(chair_price, 2),
                                    "margin_pct": round(100 * margin(chair_price, 0, chair_cost), 2)},
        },
    }
    assert margin(4995.0, 0, dt96_cost) >= MARGIN_FLOOR

    header_p = ["SKU", "Product", "Collection", "Board Feet", "Labor Cost", "List Price", "Lead Time (weeks)"]
    header_m = ["Code", "Material", "Species", "Thickness", "Grade", "Unit", "Cost per Unit", "Supplier", "Price Updated"]
    header_q = ["Quote No", "Quote Date", "Rep", "Customer", "Status", "Discount", "SKU", "Material", "Qty", "Unit Price", "Decision Date"]
    return {"counts": counts, "products": (header_p, [r["cells"] for r in prod_rows]),
            "materials": (header_m, [r["cells"] for r in mat_rows]), "quotes": (header_q, [r["cells"] for r in q_rows])}


def main() -> None:
    seed = argparse_seed()
    out = build(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "products.csv"), *out["products"])
    write_csv(os.path.join(SEED_DIR, "materials.csv"), *out["materials"])
    write_csv(os.path.join(SEED_DIR, "quotes.csv"), *out["quotes"])
    write_text(os.path.join(REF_DIR, "counts.json"), json.dumps(out["counts"], indent=2) + "\n")
    c = out["counts"]
    print(f"products.csv {c['products']['file_rows_excluding_header']} rows; materials.csv {c['materials']['file_rows_excluding_header']} rows; "
          f"quotes.csv {c['quotes']['file_rows_excluding_header']} rows -> {c['quotes']['quotes']} quotes; scope {c['baseline']['scope_count']}")


if __name__ == "__main__":
    main()
