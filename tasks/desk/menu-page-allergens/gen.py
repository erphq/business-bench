#!/usr/bin/env python3
"""menu-page-allergens: a noodle bar's menu workbook as one HTML menu page with allergens spelled out.

    python gen.py [--seed N] [--naive DIR]

Business: a ramen and dumpling bar opening its fall menu. The kitchen keeps the menu in a workbook with allergen
codes and a tab of price changes; the chef keeps an 86 list of dishes the kitchen cannot make.

Traps (each caught by a check, see task.yaml):
  * allergen codes are two letters and mixed with dietary markers: SF is shellfish (not fish), SE sesame and SY
    soy, GF means a gluten-free option and V vegan, neither an allergen   (check: page structure: allergens per dish)
  * codes are separated by commas, slashes or spaces and typed in either case (check: page structure: allergens per dish)
  * the chef's 86 list takes dishes off, typed in lower case             (checks: 86'd dishes left off; one row per dish)
  * the fall price changes tab overrides the Menu tab                     (checks: new prices; page structure: price per dish)
  * some prices are text ('$14', '13.5')                                  (check: page structure: price per dish)
"""
from __future__ import annotations
import argparse
import html
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

ALLERGENS = {"G": "Gluten", "D": "Dairy", "E": "Egg", "SY": "Soy", "SE": "Sesame", "P": "Peanut", "TN": "Tree nuts",
             "F": "Fish", "SF": "Shellfish"}
MARKERS = {"V": "Vegan", "GF": "Gluten-free option on request"}
ALLERGEN_RX = {"Gluten": r"\bgluten\b(?![- ]?free)|\bwheat\b", "Dairy": r"\bdairy\b|\bmilk\b",
               "Egg": r"\beggs?\b", "Soy": r"\bsoy(a|bean|beans)?\b", "Sesame": r"\bsesame\b",
               "Peanut": r"\bpeanuts?\b", "Tree nuts": r"\btree[- ]?nuts?\b", "Fish": r"(?<!shell)\bfish\b",
               "Shellfish": r"\bshellfish\b|\bcrustaceans?\b|\bmollus(c|k)s?\b"}
SECTIONS = ["Small plates", "Dumplings", "Ramen", "Rice bowls", "Sweets", "Drinks"]
SECTION_RX = {"Small plates": r"\bsmall plates?\b|\bstarters?\b", "Dumplings": r"\bdumplings?\b",
              "Ramen": r"\bramen\b", "Rice bowls": r"\brice bowls?\b|\bbowls\b|\bdonburi\b",
              "Sweets": r"\bsweets?\b|\bdesserts?\b", "Drinks": r"\bdrinks?\b|\bbeverages?\b"}
# section, dish, codes, price (dollars)
DISHES = [
    ("Small plates", "Smashed cucumber salad", ["SE", "SY", "V"], 7.0), ("Small plates", "Edamame with chili salt", ["SY", "V", "GF"], 6.0),
    ("Small plates", "Karaage chicken", ["G", "SY", "E"], 11.0), ("Small plates", "Crispy tofu bites", ["SY", "G", "V"], 9.0),
    ("Small plates", "Charred shishito peppers", ["SY", "GF"], 8.0),
    ("Dumplings", "Pork and chive gyoza", ["G", "SY", "SE"], 10.0), ("Dumplings", "Shrimp har gow", ["G", "SF"], 12.0),
    ("Dumplings", "Mushroom potstickers", ["G", "SY", "V"], 10.0), ("Dumplings", "Kimchi dumplings", ["G", "SY", "F"], 10.5),
    ("Dumplings", "Crab rangoon", ["G", "SF", "D", "E"], 11.0),
    ("Ramen", "Tonkotsu ramen", ["G", "SY", "E", "SE"], 17.0), ("Ramen", "Shoyu chicken ramen", ["G", "SY", "E"], 16.0),
    ("Ramen", "Spicy miso ramen", ["G", "SY", "SE", "P"], 17.0), ("Ramen", "Vegan tantanmen", ["G", "SY", "SE", "P", "V"], 16.0),
    ("Ramen", "Yuzu shio ramen", ["G", "F", "SF"], 18.0),
    ("Rice bowls", "Chashu rice bowl", ["SY", "E", "SE"], 15.0), ("Rice bowls", "Salmon poke bowl", ["F", "SY", "SE", "GF"], 16.0),
    ("Rice bowls", "Mapo tofu bowl", ["SY", "GF"], 14.0), ("Rice bowls", "Katsu curry", ["G", "E", "D"], 15.5),
    ("Sweets", "Kuro goma ice cream", ["D", "E", "SE"], 7.0), ("Sweets", "Matcha mochi", [], 6.0),
    ("Sweets", "Yuzu cheesecake", ["D", "E", "G"], 8.0),
    ("Drinks", "Hojicha latte", ["D"], 5.5), ("Drinks", "Calpico soda", ["D"], 4.5), ("Drinks", "Yuzu lemonade", [], 4.5),
    ("Drinks", "Ramune", [], 4.0),
]
NOTES = ["", "", "", "spicy", "new this fall", "house favorite", "limited", ""]


def build(seed: int) -> dict:
    r = rng(seed)
    dishes = []
    for sec, name, codes, price in DISHES:
        p = price + r.choice([0, 0, 0.5, 1.0, -0.5])
        dishes.append({"section": sec, "name": name, "codes": list(codes), "old": p, "price": p,
                       "allergens": sorted({ALLERGENS[c] for c in codes if c in ALLERGENS})})
    # 86 list: one dumpling, one bowl, one sweet or drink
    cands = [[d for d in dishes if d["section"] == "Dumplings" and d["name"] != "Shrimp har gow"],
             [d for d in dishes if d["section"] == "Rice bowls"], [d for d in dishes if d["section"] in ("Sweets",)]]
    out86 = [r.choice(c) for c in cands]
    for d in out86:
        d["out"] = True
    # fall price changes for five live dishes (never a dish on the 86 list)
    live = [d for d in dishes if not d.get("out")]
    changed = r.sample([d for d in live if d["section"] in ("Small plates", "Dumplings", "Ramen", "Rice bowls")], 5)
    for d in changed:
        d["price"] = d["old"] + r.choice([0.5, 1.0, 1.5, 2.0])
        d["changed"] = True
    return {"dishes": dishes, "live": live, "out86": out86, "changed": changed}


def naive_allergens(raw: str) -> set:
    """Letter-by-letter reading of the code cell against the one-letter codes, plus every two-letter code as a substring."""
    out = set()
    s = raw.upper()
    for code, nm in ALLERGENS.items():
        if len(code) == 2 and code in s.replace(" ", "").replace(",", "").replace("/", ""):
            out.add(nm)
    for ch in re.sub(r"[^A-Z]", "", s):
        if ch in ALLERGENS:
            out.add(ALLERGENS[ch])
    return out


def acceptable(d: dict) -> bool:
    for x in d["dishes"]:
        for y in d["dishes"]:
            if x is not y and x["name"].lower() in y["name"].lower():
                return False
    changed = d["changed"]
    if not any("GF" in x["codes"] for x in d["live"]):
        return False
    return len(pinned_prices(d)) >= 2


def pinned_prices(d: dict) -> list:
    """New prices that no other dish shows and no dish had before, so finding one on the page means the change was applied."""
    out = []
    for c in d["changed"]:
        others = [x["price"] for x in d["dishes"] if x is not c] + [x["old"] for x in d["dishes"]]
        if all(abs(c["price"] - o) > 0.001 for o in others):
            out.append(c["price"])
    return out


def code_cell(r, codes: list) -> str:
    if not codes:
        return ""
    cs = [c.lower() if r.random() < 0.15 else c for c in codes]
    sep = r.choice([", ", "/", " ", ","])
    return sep.join(cs)


def price_cell(r, p: float):
    k = r.random()
    if k < 0.2:
        return f"${p:g}"
    if k < 0.35:
        return f"{p:g}"
    return p


def page_html(d: dict) -> str:
    live = d["live"]
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           "<title>Tanuki Street Noodles - fall menu</title>", "<style>",
           "body{font-family:Georgia,'Times New Roman',serif;margin:28px auto;max-width:720px;color:#222;padding:0 16px}",
           "h1{text-align:center;margin-bottom:4px}", "h2{margin-top:30px;border-bottom:1px solid #222;padding-bottom:3px}",
           ".dish{display:flex;justify-content:space-between;gap:12px;margin-top:10px}",
           ".name{font-weight:bold}", ".allergens{font-size:13px;color:#555;margin-top:2px}", "</style>", "</head>", "<body>",
           "<h1>Tanuki Street Noodles</h1>", "<p style=\"text-align:center\">Fall menu, from 15 September 2026</p>",
           "<p>Allergens are listed under each dish. Please tell your server about any allergy; our kitchen handles "
           "all of them and cannot promise against cross-contact.</p>"]
    for sec in SECTIONS:
        ds = [x for x in live if x["section"] == sec]
        if not ds:
            continue
        out.append(f"<h2>{sec}</h2>")
        for x in ds:
            al = ", ".join(x["allergens"]) if x["allergens"] else "none of the major allergens"
            extra = []
            if "V" in x["codes"]:
                extra.append("vegan")
            if "GF" in x["codes"]:
                extra.append("gluten-free option on request")
            ex = f" &middot; {', '.join(extra)}" if extra else ""
            out.append(f'<div class="item"><div class="dish"><span class="name">{html.escape(x["name"])}</span>'
                       f'<span class="price">${x["price"]:.2f}</span></div>'
                       f'<div class="allergens">Contains: {al}{ex}</div></div>')
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    dishes, live = d["dishes"], d["live"]
    r = rng(seed + 17)
    for x in dishes:
        x["code_raw"] = code_cell(r, x["codes"])
        x["price_raw"] = price_cell(r, x["old"])
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    write_xlsx(os.path.join(ws, "menu_master_fall_2026.xlsx"), {
        "Menu": {"header": ["Section", "Dish", "Price", "Allergens", "Kitchen notes"],
                 "rows": [[x["section"], x["name"], x["price_raw"], x["code_raw"], r.choice(NOTES)] for x in dishes],
                 "widths": {"A": 14, "B": 30, "D": 16, "E": 18}},
        "Allergen key": {"header": ["Code", "Meaning", "Type"],
                         "rows": [[c, n, "Allergen"] for c, n in ALLERGENS.items()] +
                                 [[c, n, "Dietary marker - not an allergen"] for c, n in MARKERS.items()],
                         "widths": {"B": 34, "C": 32}},
        "Fall price changes": {"merged_title": "Price changes from 15 Sept 2026 (approved by Kenji)",
                               "header": ["Dish", "Old price", "New price"],
                               "rows": [[x["name"], x["old"], x["price"]] for x in d["changed"]],
                               "widths": {"A": 30}},
    }, creator="Kitchen")
    write_text(os.path.join(ws, "86_list_from_chef.txt"),
               "86 LIST - fall menu launch\n\n"
               + "".join(f"- {x['name'].lower()}   ({reason})\n" for x, reason in
                         zip(d["out86"], ["supplier is out until October", "not enough hands on the line for it",
                                          "pastry chef on leave"]))
               + "\nThese do not go on the printed or online menu until I say so.\n- Kenji\n")
    write_text(os.path.join(ws, "note_from_mei.txt"),
               "From: Mei Tanaka\nTo: you\nDate: Sun, 13 Sep 2026 22:15\nSubject: menu page for the website and the QR code\n\n"
               "We open the fall menu on Tuesday and I need the menu as a single web page - it goes behind the QR code on "
               "the tables and on the website, so one HTML file with everything in it and no scripts - the website builder "
               "strips them.\n\n"
               "Keep the sections in the order they are in the workbook. Every dish with its price and its allergens.\n\n"
               "Guests do not know our kitchen codes, so write the allergens out in words (gluten, soy, sesame and so on). "
               "The Allergen key tab says what each code means. V and GF are in the same column but they are not "
               "allergens, so they must never show up as one.\n\n"
               "Prices: the Fall price changes tab has the new prices from the 15th, and those are the prices on this "
               "menu.\n\n"
               "Anything on Kenji's 86 list stays off the page.\n\n"
               "Mei\n")
    write_json(os.path.join(ref, "expected.json"), {
        "dishes": [{"name": x["name"], "section": x["section"], "price": x["price"], "allergens": x["allergens"]} for x in live],
        "out86": [x["name"] for x in d["out86"]], "allergen_rx": ALLERGEN_RX, "section_rx": SECTION_RX,
    })
    write_text(os.path.join(sol, "index.html"), page_html(d))
    gf = [x["name"] for x in live if "GF" in x["codes"]]
    sf = [x["name"] for x in live if "SF" in x["codes"] and "F" not in x["codes"]]
    traps = [
        f"GF in the allergen column means a gluten-free option and V means vegan; reading GF as G plus F puts gluten "
        f"and fish on {', '.join(gf[:3])} (check: page structure: allergens per dish)",
        f"SF is shellfish, not fish, and SE is sesame, SY soy; a first-letter or substring reading gives "
        f"{', '.join(sf[:2])} fish and scatters soy and sesame (check: page structure: allergens per dish)",
        "codes are separated by ', ', '/', ',' or a space and some are lower case, so splitting on commas alone "
        "leaves 'G/SY' and 'SE SY' as unknown codes (check: page structure: allergens per dish)",
        "the chef's 86 list takes three dishes off and names them in lower case (checks: 86'd dishes left off; "
        "page structure: one row per dish)",
        "five dishes have new prices on the Fall price changes tab; the Menu tab still shows the old ones "
        "(checks: new prices on the menu; page structure: price per dish)",
        "some Menu-tab prices are text ('$14', '13.5') rather than numbers (check: page structure: price per dish)",
    ]
    write_task_yaml(HERE, {
        "id": "menu-page-allergens", "track": "desk", "category": "tooling",
        "title": "Fall menu page with allergens for the QR code",
        "ask": "Can you make the fall menu page for the QR code on the tables? Everything's in the menu workbook, and "
               "Mei's note and Kenji's 86 list are in the folder. Save it as index.html.\n",
        "followup": None, "timeout_s": 1200,
        "traps": traps,
        "checks": [
            {"type": "file_exists", "name": "index.html exists", "path": "index.html"},
            {"type": "text_contains_all", "name": "every dish on the menu", "path": "index.html",
             "phrases": [x["name"] for x in live]},
            {"type": "text_not_contains", "name": "86'd dishes left off", "path": "index.html",
             "phrases": [x["name"] for x in d["out86"]]},
            {"type": "text_numbers_present", "name": "new prices on the menu", "path": "index.html",
             "numbers": pinned_prices(d), "rel_tol": 0.0000001},
            {"type": "custom", "name": "page structure", "module": "check.py"},
        ],
    })
    print(f"seed={seed} live={len(live)} out={[x['name'] for x in d['out86']]} changed={[(x['name'], x['old'], x['price']) for x in d['changed']]}")


def write_naive(d: dict, out: str) -> None:
    """The obvious reading: the Menu tab as it stands (old prices, 86'd dishes kept), codes read letter by letter and
    by substring, markers treated like any other code."""
    os.makedirs(out, exist_ok=True)
    parts = ["<html><body><h1>Menu</h1>"]
    for sec in SECTIONS:
        parts.append(f"<h2>{sec}</h2><ul>")
        for x in [y for y in d["dishes"] if y["section"] == sec]:
            al = sorted(naive_allergens(x["code_raw"]))
            price = float(str(x["price_raw"]).replace("$", ""))
            parts.append(f"<li>{html.escape(x['name'])} ${price:.2f} - {', '.join(al)}</li>")
        parts.append("</ul>")
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
