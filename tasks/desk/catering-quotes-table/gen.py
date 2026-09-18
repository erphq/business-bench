#!/usr/bin/env python3
"""catering-quotes-table: four catering quotes to one normalized comparison table for 85 guests.

    python gen.py [--seed N]

Business: a physiotherapy clinic is hosting a ten-year anniversary dinner. Four caterers quoted a buffet for
"about 80". The office manager wants one comparable row per quote at the confirmed 85 guests, with the
clinic's gratuity policy applied.

Traps (each caught by a check, see task.yaml):
  * two quotes price per person, one is a flat package covering up to 75 guests plus a per-guest charge, and
    one has a 100-guest minimum                                  (checks: pricing basis and guests billed; food and beverage)
  * every quote prints an estimate for 80 guests; the table is for 85 (checks: food and beverage; fees and total)
  * gratuity: one service charge includes staff gratuity, one price includes it, one says not included, one
    prints a suggested 15-20%; the policy adds 18% only where it is not included (checks: gratuity included; gratuity amount)
  * Saffron and Sage lists a plated dinner before the buffet the event is having (check: food and beverage)
  * Olive Branch charges rentals per guest; Blue Ember lists an optional bartender that is not part of the order
    (check: fees and total)
  * the Olive Branch quote is an image-only scan                   (checks: one row per quote; fees and total)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CLIENT = "Riverbend Physio"
GUESTS = 85
QUOTED = 80
POLICY_GRAT = 0.18
MM = 2.8346


def m(x): return f"${x:,.2f}"
def r2(x): return round(x + 1e-9, 2)


def build(seed: int) -> dict:
    r = rng(seed)
    Q = {}
    pp = r.choice([39.50, 41.00, 42.50, 44.00])
    Q["saffron"] = dict(ref=f"SSC-Q{r.randint(1000, 9999)}", caterer="Saffron and Sage Catering", basis="per_person", price=pp, plated=pp + r.choice([12.0, 13.5, 15.0]),
                        svc_pct=0.20, grat_included="no", fee_flat=float(r.choice([150, 175, 195])), min_guests=40)
    pk = float(r.choice([3200, 3400, 3550])); extra = r.choice([36.0, 38.0, 40.0])
    Q["copper"] = dict(ref=f"CKE-{r.randint(26100, 26999)}", caterer="Copper Kettle Events", basis="flat", package=pk, cap=75, extra=extra,
                       svc_pct=0.22, grat_included="yes", fee_flat=float(r.choice([110, 120, 135])))
    pb = r.choice([27.00, 28.50, 29.00])
    Q["ember"] = dict(ref=f"BE{r.randint(400, 899)}-26", caterer="Blue Ember Smokehouse", basis="per_person", price=pb, min_guests=100,
                      svc_pct=0.18, grat_included="no", fee_flat=float(r.choice([85, 95, 110])), bartender=float(r.choice([250, 275, 300])))
    po = r.choice([34.00, 35.50, 36.00])
    Q["olive"] = dict(ref=f"OBK {r.randint(1100, 1999)}", caterer="Olive Branch Kitchen", basis="per_person", price=po, min_guests=60,
                      svc_pct=0.15, grat_included="yes", fee_per_guest=r.choice([4.00, 4.50, 5.25]))
    for k, q in Q.items():
        for n, key in ((GUESTS, "t"), (QUOTED, "e")):
            if q["basis"] == "flat":
                billed = n; fb = q["package"] + max(n - q["cap"], 0) * q["extra"]
            else:
                billed = max(n, q["min_guests"]); fb = billed * q["price"]
            fb = r2(fb); svc = r2(fb * q["svc_pct"]); grat = 0.0 if q["grat_included"] == "yes" else r2(fb * POLICY_GRAT)
            fees = q.get("fee_flat", 0.0) + r2(q.get("fee_per_guest", 0.0) * billed)
            q[key] = dict(billed=billed, fb=fb, svc=svc, grat=grat, fees=r2(fees), total=r2(fb + svc + grat + fees), quoted_total=r2(fb + svc + fees))
    return dict(Q=Q, mgr=person(r), contact=person(r))


def emit(seed: int) -> None:
    d = build(seed); Q = d["Q"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "catering_quotes"); os.makedirs(F, exist_ok=True)
    mg = d["mgr"]

    # ---- Saffron and Sage (Helvetica, letter): two menus, estimate for 80
    s = Q["saffron"]; e = s["e"]
    write_pdf_document(os.path.join(F, "Saffron_and_Sage_proposal.pdf"), [
        ("title", "Saffron and Sage Catering"), ("small", "Event catering  |  hello@saffronsage.example  |  503-555-0114"), ("hr", None),
        ("kv", [("Proposal", s["ref"]), ("Prepared for", f"{mg[0]} {mg[1]}, {CLIENT}"), ("Event", "Anniversary dinner, Saturday October 17, 2026"),
                ("Guest count", f"approximately {QUOTED}")], {"col_widths": [40 * MM, 120 * MM]}),
        ("h", "Menu options"),
        ("table", [["Option", "Includes", "Price"], ["Plated dinner", "Three courses, served", f"{m(s['plated'])} per person"],
                   ["Buffet dinner", "Two proteins, three sides, salad, bread, dessert station", f"{m(s['price'])} per person"]],
         {"col_widths": [35 * MM, 90 * MM, 40 * MM], "grid": True}),
        ("h", "Charges and policies"),
        ("p", f"A service charge of {int(s['svc_pct'] * 100)}% applies to all food and beverage. Gratuity is not included and is left to the host's discretion."),
        ("p", f"Delivery, setup and breakdown: {m(s['fee_flat'])} flat. Minimum {s['min_guests']} guests. Sales tax is added to the final invoice."),
        ("h", f"Estimate - buffet dinner, {QUOTED} guests"),
        ("table", [["", "Amount"], [f"Buffet dinner {QUOTED} x {m(s['price'])}", m(e["fb"])], [f"Service charge {int(s['svc_pct'] * 100)}%", m(e["svc"])],
                   ["Delivery and setup", m(s["fee_flat"])], ["Estimated total (before tax)", m(e["quoted_total"])]], {"col_widths": [110 * MM, 50 * MM]}),
    ], font="Helvetica", base_size=10)

    # ---- Copper Kettle (Times-Roman, A4): flat package with cap and extra guests
    c = Q["copper"]; e = c["e"]
    write_pdf_document(os.path.join(F, f"CopperKettle_{c['ref']}.pdf"), [
        ("right", f"Quote {c['ref']}<br/>Issued September 8, 2026"), ("title", "Copper Kettle Events"), ("spacer", 4),
        ("p", f"Dear {mg[0]}, thank you for considering us for {CLIENT}'s anniversary dinner. We recommend our Harvest Buffet Package."),
        ("spacer", 6),
        ("table", [["Item", "Detail", "Price"], ["Harvest Buffet Package", f"Flat price, includes up to {c['cap']} guests", m(c["package"])],
                   ["Additional guests", f"Each guest over {c['cap']}", f"{m(c['extra'])} each"],
                   ["Chafing and serving equipment rental", "Flat", m(c["fee_flat"])]], {"col_widths": [60 * MM, 65 * MM, 40 * MM]}),
        ("spacer", 6),
        ("p", f"A {int(c['svc_pct'] * 100)}% service charge applies to the package and any additional guests. The service charge includes staff gratuity; no further tip is expected."),
        ("spacer", 6),
        ("p", f"Your estimate for {QUOTED} guests: package {m(c['package'])} + {QUOTED - c['cap']} additional guests + service charge + rental = "
              f"<b>{m(e['quoted_total'])}</b> before tax."),
        ("spacer", 10), ("small", "A 25% deposit reserves the date. Final guest count due 10 days before the event."),
    ], pagesize="a4", font="Times-Roman", base_size=11)

    # ---- Blue Ember (Courier, letter): minimum 100 guests, suggested gratuity, optional bartender
    b = Q["ember"]; e = b["e"]
    write_pdf_document(os.path.join(F, "blue_ember_quote.pdf"), [
        ("title", "BLUE EMBER SMOKEHOUSE"), ("p", "CATERING QUOTE"), ("hr", None),
        ("kv", [("Quote #", b["ref"]), ("Client", CLIENT), ("Date of event", "10/17/2026"), ("Service style", "Buffet")], {"col_widths": [40 * MM, 120 * MM]}),
        ("spacer", 6),
        ("table", [["DESCRIPTION", "RATE"], ["Smokehouse buffet (brisket, chicken, 3 sides, cornbread)", f"{m(b['price'])} / guest"],
                   ["Delivery fee", m(b["fee_flat"])], ["OPTIONAL: bartender, 4 hours", m(b["bartender"])]], {"col_widths": [120 * MM, 45 * MM], "grid": True}),
        ("spacer", 6),
        ("p", f"MINIMUM ORDER: {b['min_guests']} guests. Orders under the minimum are billed at {b['min_guests']} guests."),
        ("p", f"SERVICE CHARGE: {int(b['svc_pct'] * 100)}% of food and beverage."),
        ("p", "SUGGESTED GRATUITY: 15%-20% for staff (not included)."),
        ("p", "Disposable plates, cutlery and napkins included. Sales tax not shown."),
        ("spacer", 6), ("small", f"Estimate at {QUOTED} guests (minimum applies): {m(e['quoted_total'])} excluding optional items and tax."),
    ], font="Courier", base_size=9)

    # ---- Olive Branch (scan): per-guest rentals, gratuity in price
    o = Q["olive"]; e = o["e"]
    write_scan_pdf(os.path.join(F, "scan_olive_branch_quote.pdf"), [
        "OLIVE BRANCH KITCHEN", "Catering Estimate", "", f"Estimate no: {o['ref']}", f"For: {CLIENT}", "Event: Oct 17 2026, buffet", "",
        f"Mediterranean buffet {m(o['price'])} per guest", "  (staff gratuity included in price)", f"Service charge: {int(o['svc_pct'] * 100)}% of food",
        f"Rentals (linens, plates): {m(o['fee_per_guest'])} per guest", f"Minimum: {o['min_guests']} guests", "",
        f"Estimate for {QUOTED} guests:", f"  Food {m(e['fb'])}", f"  Service charge {m(e['svc'])}", f"  Rentals {m(e['fees'])}", f"  Total {m(e['quoted_total'])}", "",
        "Tax added at invoicing.", "Thank you!"], font_size=34, seed=seed * 41 + 8, skew_deg=0.3, noise=220)

    write_text(os.path.join(ws, "note_from_office_manager.txt"),
        "Anniversary dinner - catering comparison\n\n"
        f"We're confirmed at {GUESTS} guests (when we asked for quotes it was about {QUOTED}) and we're doing a buffet. "
        "The four quotes are in catering_quotes. I need quote_comparison.csv with one row per quote so the partners can compare like for like:\n\n"
        "quote_ref - the quote or estimate number as printed\n"
        "caterer\n"
        "pricing_basis - per_person or flat\n"
        "guests_billed - how many guests we'd actually pay for at 85\n"
        "food_beverage - the food cost for our dinner at that count\n"
        "service_charge - the caterer's service charge in dollars\n"
        "gratuity_included - yes if the quote already covers staff gratuity, no if not\n"
        "gratuity - what we'd add under our policy: 18% of food_beverage when gratuity isn't included, 0 when it is\n"
        "fees - delivery, setup and rental charges we'd have to pay (nothing optional)\n"
        "total - food_beverage + service_charge + gratuity + fees\n\n"
        "Leave sales tax out, it's the same rate for all of them. Plain numbers please.\n\n"
        f"{mg[0]}\n")

    header = ["quote_ref", "caterer", "pricing_basis", "guests_billed", "food_beverage", "service_charge", "gratuity_included", "gratuity", "fees", "total"]
    rows = []
    for k in ("saffron", "copper", "ember", "olive"):
        q = Q[k]; t = q["t"]
        rows.append([q["ref"], q["caterer"], q["basis"], t["billed"], f"{t['fb']:.2f}", f"{t['svc']:.2f}", q["grat_included"], f"{t['grat']:.2f}", f"{t['fees']:.2f}", f"{t['total']:.2f}"])
    write_csv(os.path.join(ref, "quote_comparison.csv"), header, rows)
    write_csv(os.path.join(sol, "quote_comparison.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {k: dict(ref=Q[k]["ref"], at80=Q[k]["e"], at85=Q[k]["t"]) for k in Q} | {"plated_price": Q["saffron"]["plated"], "bartender": Q["ember"]["bartender"]})
    ids = {k: Q[k]["ref"] for k in Q}
    write_task_yaml(HERE, {
        "id": "catering-quotes-table", "track": "desk", "category": "extraction",
        "title": "Side-by-side table of the anniversary dinner catering quotes",
        "ask": "Can you put the four catering quotes for the anniversary dinner side by side in quote_comparison.csv so the partners can compare them? My note in the folder has what to include.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "Saffron and Sage, Blue Ember and Olive Branch price per person while Copper Kettle is a flat package covering up to 75 guests plus a price for each additional guest (checks: pricing basis and guests billed; food and beverage)",
            "Blue Ember has a 100-guest minimum and bills 100 at 85 attending, while Olive Branch's 60-guest and Saffron's 40-guest minimums do not bind (checks: pricing basis and guests billed; food and beverage)",
            "every quote prints an estimate for about 80 guests, the count when the quotes were requested, and none of the estimates carries the policy gratuity; the note's 85 changes food, service charge, per-guest rentals and totals (Blue Ember's estimate is already at its minimum) (checks: food and beverage; fees and total)",
            "Copper Kettle's 22% service charge includes staff gratuity and Olive Branch's price includes it, so both carry gratuity 0; Saffron says gratuity is not included and Blue Ember prints a 'suggested gratuity 15%-20%', and both take the policy 18% (checks: gratuity included; gratuity amount)",
            "Saffron and Sage lists a plated dinner above the buffet; the event is a buffet (check: food and beverage)",
            "Olive Branch charges rentals per guest and Blue Ember lists an optional bartender under its delivery fee; the rentals scale with guests and the bartender stays out (check: fees and total)",
            "the Olive Branch estimate is an image-only scan (checks: one row per quote; fees and total)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "quote_comparison.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per quote", "path": "quote_comparison.csv", "column": "quote_ref", "ref": "quote_comparison.csv", "normalize": ["alnum"]},
            {"type": "csv_row_count", "name": "row count", "path": "quote_comparison.csv", "equals_ref": "quote_comparison.csv"},
            {"type": "csv_values_match", "name": "caterers", "path": "quote_comparison.csv", "ref": "quote_comparison.csv", "key": "quote_ref",
             "columns": ["caterer"], "normalize": ["alnum"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "pricing basis and guests billed", "path": "quote_comparison.csv", "ref": "quote_comparison.csv", "key": "quote_ref",
             "columns": ["pricing_basis", "guests_billed"], "min_accuracy": 1.0, "must_match_keys": [ids["copper"], ids["ember"]]},
            {"type": "csv_values_match", "name": "food and beverage", "path": "quote_comparison.csv", "ref": "quote_comparison.csv", "key": "quote_ref",
             "columns": ["food_beverage", "service_charge"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": list(ids.values())},
            {"type": "csv_values_match", "name": "gratuity included", "path": "quote_comparison.csv", "ref": "quote_comparison.csv", "key": "quote_ref",
             "columns": ["gratuity_included"], "min_accuracy": 1.0, "must_match_keys": [ids["copper"], ids["olive"], ids["ember"]]},
            {"type": "csv_values_match", "name": "gratuity amount", "path": "quote_comparison.csv", "ref": "quote_comparison.csv", "key": "quote_ref",
             "columns": ["gratuity"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": list(ids.values())},
            {"type": "csv_values_match", "name": "fees and total", "path": "quote_comparison.csv", "ref": "quote_comparison.csv", "key": "quote_ref",
             "columns": ["fees", "total"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": list(ids.values())},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
