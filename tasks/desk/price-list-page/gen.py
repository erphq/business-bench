#!/usr/bin/env python3
"""price-list-page: a letterpress card studio's wholesale price list for shops, as one self-contained HTML page.

    python gen.py [--seed N] [--naive DIR]

Business: a two-person letterpress studio selling greeting cards, notebooks and prints wholesale to gift shops.
The shop platform exports the catalog with retail and wholesale prices typed as text, pack sizes typed as text,
and statuses typed three ways.

Traps (each caught by a check, see task.yaml):
  * wholesale prices are text ('$2.25', 'USD 2.25', '2.25 ea', '$3.5') next to a retail column   (check: page structure: unit and pack prices)
  * pack price is per-card price times pack size less the note's pack discount (10% on 6, 15% on 12, none on
    notebooks and prints); pack sizes are typed '6 pk', 'box of 6', '12-pack', 'set of 3', 'single'
                                                                      (checks: key pack prices; page structure: unit and pack prices)
  * discontinued lines are marked Discontinued, DISC or disc., and one is flagged only in its name (checks: discontinued lines left off; one row per product)
  * the whole Wedding category is discontinued                     (check: discontinued lines left off)
  * category order comes from the note, not the alphabet or the export (check: page structure: category order)
"""
from __future__ import annotations
import argparse
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

ORDER = ["Holiday", "Birthday", "Thank You", "Sympathy", "Everyday", "Notebooks", "Art Prints"]
CODES = {"Holiday": "HOL", "Birthday": "BDY", "Thank You": "TY", "Sympathy": "SYM", "Everyday": "EVD",
         "Notebooks": "NB", "Art Prints": "PRT", "Wedding": "WED"}
POOL = {
    "Holiday": ["Frosted pinecone", "Snowy owl", "Candlelit window", "Pine sprig", "Winter fox", "Starry sleigh ride"],
    "Birthday": ["Balloon bouquet", "Cake with sparklers", "Rocket candle", "Party hat corgi", "Confetti burst"],
    "Thank You": ["Grateful garden", "Pressed fern", "Hummingbird note", "Paper crane", "Tulip bunch"],
    "Sympathy": ["Forget-me-nots", "Quiet harbor", "Willow branch", "Evening lantern"],
    "Everyday": ["Sunny lemon", "Blue bicycle", "Tiny cactus", "Letterpress alphabet", "Paper boats"],
    "Notebooks": ["Pocket notebook kraft", "Dot grid journal", "Lined jotter trio"],
    "Art Prints": ["Harbor map print", "Botanical fern print", "Bee study print"],
    "Wedding": ["Just married tandem", "Rings and roses"],
}
LABELS = {"Holiday": r"\bholidays?\b", "Birthday": r"\bbirthdays?\b", "Thank You": r"\bthank[- ]?yous?\b",
          "Sympathy": r"\bsympathy\b", "Everyday": r"\beveryday\b", "Notebooks": r"\bnotebooks?\b|\bjournals?\b",
          "Art Prints": r"\bart prints?\b|\bprints?\b"}


def discount(cat: str, pack: int) -> float:
    if cat in ("Notebooks", "Art Prints"):
        return 0.0
    return {6: 0.10, 12: 0.15}.get(pack, 0.0)


def build(seed: int) -> dict:
    r = rng(seed)
    prods = []
    for cat, names in POOL.items():
        take = names if cat in ("Notebooks", "Art Prints", "Wedding", "Sympathy") else r.sample(names, len(names) - 1)
        for nm in take:
            if cat in ("Notebooks",):
                pack, cents = 3, r.randint(420, 980)
            elif cat == "Art Prints":
                pack, cents = 1, r.randint(9, 28) * 100 + r.choice([0, 50])
            else:
                pack = r.choice([6, 6, 12])
                cents = r.randint(34, 70) * 5                              # $1.70 - $3.50, multiple of 5 cents
            prods.append({"name": nm, "cat": cat, "pack": pack, "cents": cents, "status": "Active"})
    for p in prods:
        disc = discount(p["cat"], p["pack"])
        exact = p["cents"] * p["pack"] * (1 - disc)
        p["pack_cents"] = int(round(exact))
        p["exact"] = abs(exact - round(exact)) < 1e-6
        p["retail_cents"] = int(round(p["cents"] * 2.2 / 5.0)) * 5 if p["cat"] not in ("Art Prints",) else p["cents"] * 2
    # discontinued: the wedding category, one status-typed line in three categories, one flagged only in its name
    for p in prods:
        if p["cat"] == "Wedding":
            p["status"] = r.choice(["Discontinued", "DISC"])
    live_cards = [p for p in prods if p["cat"] in ("Holiday", "Birthday", "Thank You", "Everyday")]
    for p, word in zip(r.sample(live_cards, 3), ["Discontinued", "DISC", "disc."]):
        p["status"] = word
    name_flag = r.choice([p for p in prods if p["status"] == "Active" and p["cat"] in ("Holiday", "Birthday", "Everyday", "Thank You")])
    name_flag["name_flag"] = True
    for i, p in enumerate(sorted(prods, key=lambda x: (x["cat"], x["name"]))):
        p["sku"] = f"{CODES[p['cat']]}-{100 + i * 3}"
    active = [p for p in prods if p["status"] == "Active" and not p.get("name_flag")]
    return {"prods": prods, "active": active, "name_flag": name_flag}


def price_text(r, cents: int) -> str:
    v = cents / 100
    style = r.randrange(6)
    if style == 0:
        return f"${v:.2f}"
    if style == 1:
        return f"{v:.2f}"
    if style == 2:
        return f"USD {v:.2f}"
    if style == 3:
        return f"{v:.2f} ea"
    if style == 4:
        return f"${v:g}" if cents % 10 == 0 else f"${v:.2f}"
    return f" {v:.2f}"


def pack_text(r, pack: int) -> str:
    return r.choice({1: ["1", "single", "1 ea"], 3: ["3", "set of 3", "3 pk"], 6: ["6", "6 pk", "box of 6"],
                     12: ["12", "12-pack", "box of 12"]}[pack])


def acceptable(d: dict) -> bool:
    if not all(p["exact"] for p in d["prods"]):
        return False
    active = d["active"]
    # at least three 12-packs and five 6-packs among live cards, and no unit price equal to a pack price elsewhere
    if sum(1 for p in active if p["pack"] == 12) < 3 or sum(1 for p in active if p["pack"] == 6) < 5:
        return False
    names = [p["name"].lower() for p in d["prods"]]
    for a in names:
        for b in names:
            if a != b and a in b:
                return False
    return len({p["pack_cents"] for p in active}) >= len(active) - 3


def usd(c: int) -> str:
    return f"${c / 100:,.2f}"


def page_html(active: list) -> str:
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           "<title>Paper Heron Press - wholesale price list</title>", "<style>",
           "body{font-family:'Palatino Linotype',Palatino,serif;margin:28px;color:#2b2b2b;max-width:860px}",
           "h1{margin-bottom:0}", "h2{margin-top:28px;border-bottom:1px solid #2b2b2b}",
           "table{border-collapse:collapse;width:100%}",
           "th,td{padding:5px 6px;text-align:left;border-bottom:1px solid #e2e2e2}",
           "td.n,th.n{text-align:right}", "</style>", "</head>", "<body>",
           "<h1>Paper Heron Press</h1>",
           "<p>Wholesale price list, fall 2026. Prices in US dollars. Cards ship in boxed packs; the pack price "
           "includes the pack discount.</p>"]
    for cat in ORDER:
        ps = sorted([p for p in active if p["cat"] == cat], key=lambda p: p["name"].lower())
        if not ps:
            continue
        out.append(f"<h2>{cat}</h2>")
        out.append("<table><thead><tr><th>Item</th><th>SKU</th><th class=\"n\">Pack</th>"
                   "<th class=\"n\">Price each</th><th class=\"n\">Pack price</th></tr></thead><tbody>")
        for p in ps:
            out.append(f"<tr><td>{html.escape(p['name'])}</td><td>{p['sku']}</td><td class=\"n\">{p['pack']}</td>"
                       f"<td class=\"n\">{usd(p['cents'])}</td><td class=\"n\">{usd(p['pack_cents'])}</td></tr>")
        out.append("</tbody></table>")
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    prods, active = d["prods"], d["active"]
    r = rng(seed + 5)
    for p in prods:
        p["price_raw"] = price_text(r, p["cents"])
        p["pack_raw"] = pack_text(r, p["pack"])
        p["name_raw"] = f"DISCONTINUED - {p['name']}" if p.get("name_flag") else p["name"]
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    rows = [[p["sku"], p["name_raw"], p["cat"], p["pack_raw"], usd(p["retail_cents"]), p["price_raw"], p["status"],
             r.choice(["", "", "", "restock Oct", "low paper stock", ""]) if p["status"] == "Active" else ""]
            for p in sorted(prods, key=lambda x: x["sku"])]
    write_csv(os.path.join(ws, "shop_catalog_export_2026-09-10.csv"),
              ["SKU", "Product name", "Category", "Pack qty", "Retail price", "Wholesale price", "Status", "Internal note"],
              rows, bom=True)
    write_text(os.path.join(ws, "note_from_nadia.txt"),
               "Subject: wholesale price list for the fall buyers\nFrom: Nadia Osei\nDate: Thu, 10 Sep 2026\n\n"
               "The shop buyers want our fall wholesale list before the trade show, and I would like to send it as a "
               "single web page they can open from the email - one file, nothing loaded from anywhere else, and no scripts, "
               "because half the buyers' email systems strip them.\n\n"
               "It is the wholesale list, so wholesale prices only. Group it by category in this order, because "
               "buyers read from the top and holiday is what they are ordering right now:\n\n"
               "  1. Holiday\n  2. Birthday\n  3. Thank You\n  4. Sympathy\n  5. Everyday\n  6. Notebooks\n"
               "  7. Art Prints\n\n"
               "For every item show the price each and the pack price. Cards only go out in boxed packs: the pack "
               "price is the price each times the number in the box, less 10% for a box of 6 and 15% for a box of 12. "
               "Notebooks and prints never get a pack discount.\n\n"
               "Anything discontinued stays off the list - we are out of wedding cards altogether. People have "
               "marked discontinued lines in different ways over the years, so look carefully.\n\n"
               "Nadia\n")
    write_csv(os.path.join(ws, "wholesale_prices_fall_2025.csv"), ["SKU", "Product", "Wholesale"],
              [[p["sku"], p["name"], f"{max(p['cents'] - r.choice([0, 10, 15, 25]), 100) / 100:.2f}"] for p in sorted(prods, key=lambda x: x["sku"])])
    gone = [p for p in prods if p not in active]
    write_json(os.path.join(ref, "expected.json"), {
        "products": [{"name": p["name"], "sku": p["sku"], "category": p["cat"], "pack": p["pack"],
                      "each": p["cents"] / 100, "pack_price": p["pack_cents"] / 100} for p in active],
        "discontinued": [{"name": p["name"], "sku": p["sku"]} for p in gone],
        "order": ORDER, "labels": LABELS,
    })
    write_text(os.path.join(sol, "index.html"), page_html(active))
    key = [p for p in active if p["pack"] == 12][:2] + [p for p in active if p["pack"] == 6][:2]
    nf = d["name_flag"]
    traps = [
        "wholesale prices are typed as text in six styles ('$2.25', '2.25', 'USD 2.25', '2.25 ea', '$3.5', a leading "
        "space) beside a retail column that is roughly double (check: page structure: unit and pack prices)",
        "the pack price is price each times pack size less 10% on a box of 6 and 15% on a box of 12, with no discount "
        "on notebooks or prints; pack sizes are typed '6 pk', 'box of 12', '12-pack', 'set of 3', 'single' "
        "(checks: key pack prices; page structure: unit and pack prices)",
        "discontinued lines are marked Discontinued, DISC or disc. in the status column "
        "(checks: discontinued lines left off; page structure: one row per product)",
        f"'{nf['name']}' has an Active status but its name was typed 'DISCONTINUED - {nf['name']}' "
        "(checks: discontinued lines left off; page structure: one row per product)",
        "the Wedding category is discontinued in full, so it has no section at all (check: discontinued lines left off)",
        "the note sets the category order (Holiday first); the export is in SKU order and an alphabetical page puts "
        "Art Prints first (check: page structure: category order)",
        "last fall's wholesale price file sits beside the export with older prices (check: page structure: unit and pack prices)",
    ]
    write_task_yaml(HERE, {
        "id": "price-list-page", "track": "desk", "category": "tooling",
        "title": "Fall wholesale price list page for shop buyers",
        "ask": "Can you make our fall wholesale price list page for the shop buyers from the catalog export? Nadia's "
               "note has the rules. Save it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "every live product listed", "path": "index.html",
             "phrases": [p["name"] for p in sorted(active, key=lambda x: x["name"])]},
            {"type": "text_not_contains", "name": "discontinued lines left off", "path": "index.html",
             "phrases": [p["name"] for p in gone]},
            {"type": "text_numbers_present", "name": "key pack prices", "path": "index.html",
             "numbers": [p["pack_cents"] / 100 for p in key], "rel_tol": 0.0000001},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} active={len(active)} gone={[p['name'] for p in gone]}")


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: status exactly 'Discontinued' drops a line, the leading number of each text field is the
    value, pack price = price x pack with no discount, categories alphabetical."""
    import re
    os.makedirs(out, exist_ok=True)
    keep = [p for p in d["prods"] if p["status"] != "Discontinued"]
    parts = ["<html><body><h1>Wholesale price list</h1>"]
    for cat in sorted({p["cat"] for p in keep}):
        parts.append(f"<h2>{cat}</h2><table>")
        for p in [x for x in keep if x["cat"] == cat]:
            each = float(re.sub(r"[^0-9.]", "", p["price_raw"]))
            m = re.search(r"\d+", p["pack_raw"])
            pack = int(m.group(0)) if m else 1
            parts.append(f"<tr><td>{html.escape(p['name_raw'])}</td><td>{pack}</td><td>${each:.2f}</td><td>${each * pack:.2f}</td></tr>")
        parts.append("</table>")
    parts.append("</body></html>\n")
    write_text(os.path.join(out, "index.html"), "\n".join(parts))


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
