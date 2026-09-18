#!/usr/bin/env python3
"""inventory-tracker-page: the workshop's supplies stock as one self-contained HTML page for the pour-station tablet.

    python gen.py [--seed N] [--naive DIR]

Business: a small-batch soap and candle workshop. The counting app exports supplies with an on-hand figure in
whatever unit the counter chose, a reorder point in the unit it was set up with, and the supplier's cost basis.

Traps (each caught by a check, see task.yaml):
  * on-hand and reorder point are in different units on some lines (grams against kilos, litres against
    millilitres); comparing the raw numbers misses two low items and invents one      (check: low-stock section)
  * the note's rule is at or below the reorder point; two lines sit exactly on it   (check: low-stock section)
  * archived lines are still in the export, all under their reorder points            (checks: archived lines left off;
                                                                                        low-stock section; one row per item)
  * cost is quoted per kg, per L, per case, per pack or per roll while stock is counted in grams, millilitres
    and single pieces, so value is not on-hand times cost                              (checks: total stock value; totals row)
  * the export is in bin order with names typed in capitals or with stray spaces; A to Z has to ignore both
                                                                                       (check: sorted A to Z)
  * last month's export sits in the folder with different counts                     (checks: total stock value; low-stock section)
"""
from __future__ import annotations
import argparse
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# name, measure (mass | volume | count), cost basis for count items (pieces per costed unit, label)
MASS = ["Olive oil pomace", "Coconut oil refined", "Shea butter", "Cocoa butter", "Castor oil", "Sweet almond oil",
        "Avocado oil", "Rice bran oil", "Sodium hydroxide lye", "Soy container wax", "Beeswax pellets", "Coconut apricot wax",
        "Kaolin clay", "Activated charcoal", "Colloidal oatmeal", "Stearic acid", "Citric acid", "Epsom salt"]
VOLUME = ["Lavender essential oil", "Eucalyptus essential oil", "Peppermint essential oil", "Cedarwood fragrance oil",
          "Vanilla bean fragrance oil", "Vegetable glycerin", "Witch hazel extract"]
COUNT = [("Cotton wicks", 1, "each"), ("Wooden wicks", 1, "each"), ("Amber glass jars", 24, "case of 24"),
         ("Candle tins", 48, "case of 48"), ("Kraft soap boxes", 100, "pack of 100"),
         ("Jar labels", 500, "roll of 500"), ("Muslin soap bags", 50, "pack of 50")]
LOW_RX = r"\blow\b|running low|below (the |its )?reorder|at or below|reorder now|to reorder|needs? (re)?order"
AS_OF = "12 September 2026"


def sku_for(name: str, i: int) -> str:
    letters = "".join(w[0] for w in name.replace("-", " ").split() if w[0].isalpha()).upper()[:3]
    return f"FH-{letters}{100 + i * 7}"


def build(seed: int) -> dict:
    r = rng(seed)
    mass = r.sample(MASS, 13)
    vol = r.sample(VOLUME, 7)
    cnt = r.sample(COUNT, 7)
    items = []

    def add(name, measure, role, **kw):
        it = {"name": name, "measure": measure, "role": role, "status": "Active"}
        it.update(kw)
        items.append(it)
        return it

    def kg_cost():
        return round(r.randint(28, 260) * 0.10, 2)          # $2.80 - $26.00 per kg, multiple of 0.10

    def l_cost():
        return round(r.randint(60, 1400) * 0.10, 2)         # $6.00 - $140.00 per L

    # ---- mass lines (stock base unit: grams) ----
    m_roles = ["at_g", "below_g", "plain_low_kg", "near_above_kg"] + ["ok_g"] * 4 + ["ok_kg"] * 3 + ["archived", "ok_kg"]
    for name, role in zip(mass, m_roles):
        reorder_kg = r.choice([2, 3, 4, 5, 6, 8, 10])
        if role == "at_g":
            g, cu = reorder_kg * 1000, "g"
        elif role == "below_g":
            g, cu = r.randint(4, reorder_kg * 10 - 3) * 100, "g"       # e.g. 1,400 g against 3 kg
        elif role == "plain_low_kg":
            g, cu = r.randint(3, reorder_kg * 10 - 4) * 100, "kg"
        elif role == "near_above_kg":
            g, cu = reorder_kg * 1000 + r.randint(1, 3) * 100, "kg"
        elif role == "ok_g":
            g, cu = r.randint(reorder_kg * 10 + 6, reorder_kg * 10 + 60) * 100, "g"
        elif role == "archived":
            g, cu = r.randint(0, reorder_kg * 5) * 100, "kg"
        else:
            g, cu = r.randint(reorder_kg * 10 + 8, reorder_kg * 10 + 150) * 100, "kg"
        add(name, "mass", role, base=g, count_unit=cu, reorder_base=reorder_kg * 1000, reorder_unit="kg",
            cost=kg_cost(), cost_per="kg", status="Archived" if role == "archived" else "Active")

    # ---- volume lines (stock base unit: millilitres) ----
    v_roles = ["above_l_vs_ml", "below_ml_vs_l", "ok_ml", "ok_l", "ok_l", "archived", "ok_ml"]
    for name, role in zip(vol, v_roles):
        if role == "above_l_vs_ml":            # 1.5 L on hand, reorder at 500 ml: fine, but 1.5 < 500
            reorder_ml, ru = r.choice([250, 500, 750]), "ml"
            ml, cu = r.randint(12, 30) * 100, "L"
        elif role == "below_ml_vs_l":          # 700 ml on hand, reorder at 1 L: low, but 700 > 1
            reorder_ml, ru = r.choice([1000, 2000]), "L"
            ml, cu = r.randint(3, reorder_ml // 100 - 2) * 100, "ml"
        elif role == "ok_ml":
            reorder_ml, ru = r.choice([200, 300, 500]), "ml"
            ml, cu = reorder_ml + r.randint(3, 20) * 100, "ml"
        elif role == "archived":
            reorder_ml, ru = r.choice([500, 1000]), "ml"
            ml, cu = r.randint(0, 3) * 100, "ml"
        else:
            reorder_ml, ru = r.choice([2000, 3000, 5000]), "L"
            ml, cu = reorder_ml + r.randint(10, 60) * 100, "L"
        add(name, "volume", role, base=ml, count_unit=cu, reorder_base=reorder_ml, reorder_unit=ru, cost=l_cost(),
            cost_per="L", status="Archived" if role == "archived" else "Active")

    # ---- count lines (pieces) ----
    c_roles = ["at_count", "plain_low_count", "ok_count", "ok_count", "archived", "ok_count", "ok_count"]
    for (name, per, label), role in zip(cnt, c_roles):
        reorder = per * r.choice([2, 3, 4]) if per > 1 else r.choice([100, 150, 200])
        if role == "at_count":
            qty = reorder
        elif role == "plain_low_count":
            qty = reorder - (per if per > 1 else 10) * r.randint(1, 1 if per > 1 else 8)
        elif role == "archived":
            qty = r.randint(0, max(1, reorder // 3))
        else:
            qty = reorder + (per if per > 1 else 5) * r.randint(2, 12)
        piece_cents = r.randint(4, 95) if per >= 50 else r.randint(35, 260)
        cost = round(piece_cents * per / 100.0, 2)
        add(name, "count", role, base=qty, count_unit="each", reorder_base=reorder, reorder_unit="each",
            cost=cost, cost_per=label, per=per, status="Archived" if role == "archived" else "Active")

    for i, it in enumerate(items):
        it["sku"] = sku_for(it["name"], i)
        it["bin"] = f"{r.choice('ABCD')}-{r.randint(1, 6)}"
        it["raw"] = raw_name(r, it["name"])
        it["raw_prev"] = raw_name(r, it["name"])
    # value at cost, exact to the cent by construction
    for it in items:
        if it["measure"] == "mass":
            cents = it["base"] * round(it["cost"] * 100) / 1000       # grams * cents per kg / 1000
        elif it["measure"] == "volume":
            cents = it["base"] * round(it["cost"] * 100) / 1000
        else:
            cents = it["base"] * round(it["cost"] * 100) / it["per"]
        it["value_cents"] = round(cents)
        it["exact"] = abs(cents - round(cents)) < 1e-6
    active = [it for it in items if it["status"] == "Active"]
    low = [it for it in active if it["base"] <= it["reorder_base"]]
    total_cents = sum(it["value_cents"] for it in active)

    # last month's export: same lines, different counts
    prev = {}
    for it in items:
        if it["measure"] == "count":
            prev[it["sku"]] = it["base"] + r.randint(-2, 12) * (it.get("per", 1) if it.get("per", 1) > 1 else 10)
        else:
            prev[it["sku"]] = max(0, it["base"] + r.randint(-5, 25) * 100)
    return {"items": items, "active": active, "low": low, "total_cents": total_cents, "prev": prev}


def shown(qty_base: int, measure: str, unit: str) -> float:
    if measure == "mass":
        return qty_base / 1000 if unit == "kg" else qty_base
    if measure == "volume":
        return qty_base / 1000 if unit == "L" else qty_base
    return qty_base


def fmt_qty(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}".rstrip("0").rstrip(".")


def naive_low(it: dict) -> bool:
    return shown(it["base"], it["measure"], it["count_unit"]) < shown(it["reorder_base"], it["measure"], it["reorder_unit"])


def naive_value_cents(it: dict) -> int:
    return round(shown(it["base"], it["measure"], it["count_unit"]) * it["cost"] * 100)


def acceptable(d: dict) -> bool:
    items = d["items"]
    if not all(it["exact"] for it in items):
        return False
    low_names = {it["name"] for it in d["low"]}
    naive = {it["name"] for it in items if naive_low(it)}
    if len(low_names) != 6 or naive == low_names:
        return False
    naive_total = sum(naive_value_cents(it) for it in items)
    if abs(naive_total - d["total_cents"]) < 5000:
        return False
    if any(it["value_cents"] == d["total_cents"] for it in items):
        return False
    # a raw sort of the export names (capitals, leading spaces) must not already be A to Z
    active = d["active"]
    if [it["raw"] for it in sorted(active, key=lambda x: x["raw"])] == [it["raw"] for it in sorted(active, key=lambda x: x["name"].lower())]:
        return False
    # bin order must not be A to Z either
    if sorted(active, key=lambda it: (it["bin"], it["sku"])) == sorted(active, key=lambda x: x["name"].lower()):
        return False
    return True


def raw_name(r, name: str) -> str:
    k = r.random()
    if k < 0.18:
        return name.upper()
    if k < 0.30:
        return " " + name
    if k < 0.38:
        return name.lower()
    return name


def usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def page_html(d: dict, active: list, low: list, total_cents: int, title_note: str = "") -> str:
    def qty(it, base):
        unit = {"mass": "kg", "volume": "L", "count": "each"}[it["measure"]]
        if it["measure"] != "count" and base < 1000:
            unit = "g" if it["measure"] == "mass" else "ml"
            return f"{fmt_qty(base)} {unit}"
        if it["measure"] == "count":
            return f"{base:,} each"
        return f"{fmt_qty(base / 1000)} {unit}"

    lines = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
             "<title>Supplies stock - Fennel Hollow Soapworks</title>",
             "<style>",
             "body{font-family:Georgia,serif;margin:24px;color:#222}",
             "table{border-collapse:collapse;width:100%;margin-bottom:24px}",
             "th,td{border-bottom:1px solid #ccc;padding:6px 8px;text-align:left}",
             "td.n,th.n{text-align:right}",
             "section.low{border:2px solid #a33;padding:8px 16px;margin-bottom:24px}",
             "tfoot td{font-weight:bold;border-top:2px solid #222}",
             "</style>", "</head>", "<body>",
             "<h1>Supplies stock</h1>",
             f"<p>Counts from the stock export of {AS_OF}.{title_note}</p>",
             '<section class="low">', f"<h2>Low stock ({len(low)} items at or below reorder point)</h2>",
             "<table>", "<thead><tr><th>Item</th><th class=\"n\">On hand</th><th class=\"n\">Reorder point</th></tr></thead>",
             "<tbody>"]
    for it in sorted(low, key=lambda x: x["name"].lower()):
        lines.append(f"<tr><td>{html.escape(it['name'])}</td><td class=\"n\">{qty(it, it['base'])}</td>"
                     f"<td class=\"n\">{qty(it, it['reorder_base'])}</td></tr>")
    lines += ["</tbody>", "</table>", "</section>", "<h2>All supplies (A to Z)</h2>", "<table>",
              "<thead><tr><th>Item</th><th>SKU</th><th class=\"n\">On hand</th><th class=\"n\">Reorder point</th>"
              "<th class=\"n\">Value at cost</th></tr></thead>", "<tbody>"]
    for it in sorted(active, key=lambda x: x["name"].lower()):
        lines.append(f"<tr><td>{html.escape(it['name'])}</td><td>{it['sku']}</td><td class=\"n\">{qty(it, it['base'])}</td>"
                     f"<td class=\"n\">{qty(it, it['reorder_base'])}</td><td class=\"n\">{usd(it['value_cents'])}</td></tr>")
    lines += ["</tbody>",
              f"<tfoot><tr><td>Total ({len(active)} items)</td><td></td><td></td><td></td>"
              f"<td class=\"n\">{usd(total_cents)}</td></tr></tfoot>",
              "</table>", "</body>", "</html>", ""]
    return "\n".join(lines)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    items, active, low = d["items"], d["active"], d["low"]
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    by_bin = sorted(items, key=lambda it: (it["bin"], it["sku"]))

    def export_rows(counts: dict | None) -> list[list]:
        rows = []
        for it in by_bin:
            base = it["base"] if counts is None else counts[it["sku"]]
            rows.append([it["bin"], it["sku"], it["raw"] if counts is None else it["raw_prev"], it["status"],
                         fmt_qty(shown(base, it["measure"], it["count_unit"])), it["count_unit"],
                         fmt_qty(shown(it["reorder_base"], it["measure"], it["reorder_unit"])), it["reorder_unit"],
                         f"{it['cost']:.2f}", it["cost_per"]])
        return rows

    header = ["Bin", "SKU", "Item", "Status", "On hand", "Count unit", "Reorder at", "Reorder unit", "Unit cost", "Cost per"]
    write_csv(os.path.join(ws, "stock_on_hand_2026-09-12.csv"), header, export_rows(None),
              preamble=["Fennel Hollow Soapworks - stock on hand", "Exported 09/12/2026 4:07 PM by marta"], bom=True, crlf=True)
    write_csv(os.path.join(ws, "stock_on_hand_2026-08-14.csv"), header, export_rows(d["prev"]),
              preamble=["Fennel Hollow Soapworks - stock on hand", "Exported 08/14/2026 3:52 PM by marta"], bom=True, crlf=True)
    write_text(os.path.join(ws, "note_from_marta.txt"),
               "From: Marta Lindqvist\nTo: you\nDate: Sat, 12 Sep 2026 16:20\nSubject: stock page for the tablet\n\n"
               "The tablet at the pour station has no signal half the time, so what I want is one page it can open "
               "on its own, nothing it has to fetch, and no scripts - the tablet's locked-down browser blocks them.\n\n"
               "Everything we still stock, A to Z by name, with how much is on hand and what it is worth at cost. "
               "Put the unit next to every quantity - last month somebody read 800 grams of shea as 800 kilos and "
               "nearly skipped an order.\n\n"
               "At the top I want a Low stock section: anything sitting at or below its reorder point, so whoever "
               "does the Friday order sees it first. At the reorder point counts as low, that is the whole point "
               "of the number.\n\n"
               "Under the main list, a total row with the value of everything on hand at cost.\n\n"
               "Archived lines are things we stopped making or buying. They are still in the export because the app "
               "never deletes anything - leave them off the page completely.\n\n"
               "Costs are whatever the supplier quotes, so check the Cost per column before you multiply anything.\n\n"
               "Marta\n")

    # ---- reference ----
    def base_unit(it):
        return {"mass": "g", "volume": "ml", "count": "each"}[it["measure"]]
    write_json(os.path.join(ref, "expected.json"), {
        "items": [{"name": it["name"], "sku": it["sku"], "measure": it["measure"], "on_hand_base": it["base"],
                   "base_unit": base_unit(it), "reorder_base": it["reorder_base"], "value": it["value_cents"] / 100,
                   "low": it in low, "role": it["role"]} for it in sorted(active, key=lambda x: x["name"].lower())],
        "archived": [it["name"] for it in items if it["status"] == "Archived"],
        "archived_skus": [it["sku"] for it in items if it["status"] == "Archived"],
        "low": sorted(it["name"] for it in low),
        "total_value": d["total_cents"] / 100,
        "low_rx": LOW_RX,
    })
    write_text(os.path.join(sol, "index.html"), page_html(d, active, low, d["total_cents"]))

    traps = [
        "on-hand and reorder point are in different units on some lines: a mass line counted in grams against a "
        "reorder point in kilos is low while its raw number looks huge, and a volume line counted in litres against "
        "a reorder point in millilitres is fine while its raw number looks tiny (check: page structure: low-stock section)",
        "Marta's rule is at or below the reorder point, and two lines (one counted in grams against kilos, one in "
        "pieces) sit exactly on it (check: page structure: low-stock section)",
        "three Archived lines are still in the export, all under their reorder points; they belong nowhere on the page "
        "(checks: archived lines left off; page structure: one row per item)",
        "cost is quoted per kg, per L, per case of 24 or 48, per pack or per roll while stock is counted in grams, "
        "millilitres, kilos, litres and pieces, so on hand times unit cost overstates the total by thousands "
        "(checks: total stock value; page structure: totals row)",
        "the export is in bin order and some names are typed in capitals, lower case or with a leading space, so a raw "
        "sort puts them out of place (check: page structure: sorted A to Z)",
        "last month's export sits next to this month's with the same lines and different counts "
        "(checks: total stock value; page structure: low-stock section)",
    ]
    write_task_yaml(HERE, {
        "id": "inventory-tracker-page", "track": "desk", "category": "tooling",
        "title": "Stock page for the workshop tablet",
        "ask": "Can you turn the latest stock export into the stock page for the pour-station tablet? Marta's note says "
               "what she wants on it. Save it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "every stocked item named", "path": "index.html",
             "phrases": [it["name"] for it in sorted(active, key=lambda x: x["name"].lower())]},
            {"type": "text_not_contains", "name": "archived lines left off", "path": "index.html",
             "phrases": [it["name"] for it in items if it["status"] == "Archived"]},
            {"type": "text_numbers_present", "name": "total stock value", "path": "index.html",
             "numbers": [d["total_cents"] / 100], "rel_tol": 0.0000001},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} active={len(active)} low={[it['name'] for it in low]} total={d['total_cents'] / 100:.2f}")


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: every export line in export order, raw on-hand against raw reorder number with '<',
    value = on hand x unit cost."""
    items = sorted(d["items"], key=lambda it: (it["bin"], it["sku"]))
    os.makedirs(out, exist_ok=True)
    rows, low = [], []
    for it in items:
        oh = fmt_qty(shown(it["base"], it["measure"], it["count_unit"]))
        ro = fmt_qty(shown(it["reorder_base"], it["measure"], it["reorder_unit"]))
        line = (f"<tr><td>{html.escape(it['raw'].strip())}</td><td>{oh} {it['count_unit']}</td>"
                f"<td>{ro} {it['reorder_unit']}</td><td>{usd(naive_value_cents(it))}</td></tr>")
        rows.append(line)
        if naive_low(it):
            low.append(f"<li>{html.escape(it['raw'].strip())}</li>")
    total = sum(naive_value_cents(it) for it in items)
    write_text(os.path.join(out, "index.html"),
               "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Stock</title></head><body>\n"
               "<h1>Stock</h1>\n<h2>Low stock</h2>\n<ul>\n" + "\n".join(low) + "\n</ul>\n"
               "<table><tr><th>Item</th><th>On hand</th><th>Reorder at</th><th>Value</th></tr>\n" + "\n".join(rows) +
               f"\n<tr><td>Total</td><td></td><td></td><td>{usd(total)}</td></tr></table>\n</body></html>\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
