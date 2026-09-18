#!/usr/bin/env python3
"""fleet-cost-per-mile: fuel card transactions, shop invoices and a month-end odometer log to cost per mile per vehicle.

    python gen.py [--seed N] [--naive DIR]

Business: a plumbing and heating contractor near the Canadian border with ten service vans and box trucks.
The owner wants what each vehicle cost per mile to run in the first half, fuel plus shop work.

Traps (each caught by a check, see task.yaml):
  * fill-ups at Quebec stations are in litres (USD amounts); gallons and MPG need the conversion   (check: Van 26 gallons)
  * Van 24 was sold on 17 April; its miles run to the odometer on the bill of sale, not the last month-end read
                                                                                                   (checks: Van 24 miles; Van 24 cost per mile)
  * Van 30 replaced it on 20 April and its miles start at the delivery odometer                   (check: fleet miles)
  * the fuel card also buys car washes and snacks, which are not vehicle running costs             (check: fleet total cost)
  * the shop invoices name some vans by licence plate                                              (check: Van 22 total cost)
  * totals as live formulas                                                                        (check: live formulas)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

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


L_PER_GAL = 3.785411784
START, END = date(2025, 12, 31), date(2026, 6, 30)
SALE_DATE, DELIVERY_DATE = date(2026, 4, 17), date(2026, 4, 20)
MONTH_ENDS = [date(2025, 12, 31), date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 30)]
# unit, vehicle, fuel, mpg range, daily miles range
UNITS = [("Van 21", "2022 Ford Transit 250", "Unleaded", (14.5, 17.0), (48, 72)),
         ("Van 22", "2021 Ford Transit 250", "Unleaded", (14.0, 16.5), (52, 80)),
         ("Van 23", "2023 Ram ProMaster 2500", "Unleaded", (13.5, 16.0), (40, 66)),
         ("Van 24", "2017 Chevrolet Express 2500", "Unleaded", (11.5, 13.5), (55, 82)),
         ("Van 25", "2024 Ford Transit 350", "Unleaded", (13.0, 15.5), (45, 70)),
         ("Van 26", "2022 Ram ProMaster 3500", "Unleaded", (12.5, 15.0), (70, 98)),
         ("Truck 27", "2020 Isuzu NPR-HD box truck", "Diesel", (9.0, 11.0), (35, 58)),
         ("Truck 28", "2023 Isuzu NPR-HD box truck", "Diesel", (9.5, 11.5), (30, 52)),
         ("Van 29", "2019 Ford Transit 250", "Unleaded", (13.0, 15.5), (50, 76)),
         ("Van 30", "2026 Ford Transit 250", "Unleaded", (15.0, 17.5), (55, 80))]
SOLD, NEW, CANADA, PLATE_UNIT = "Van 24", "Van 30", "Van 26", "Van 22"
STATIONS_US = [("Stewart's Shops #312", "Burlington", "VT"), ("Maplefields", "Williston", "VT"), ("Irving Oil", "St Albans", "VT"),
               ("Sunoco 0441", "Plattsburgh", "NY"), ("Mobil Mart", "Essex Jct", "VT"), ("Champlain Farms", "S Burlington", "VT")]
STATIONS_CA = [("Petro-Canada", "Saint-Jean-sur-Richelieu", "QC"), ("Ultramar", "Lacolle", "QC"), ("Esso", "Granby", "QC")]
SHOPS = ["Champlain Fleet Service", "Green Mountain Truck & Diesel", "Firestone Complete Auto Care #0551", "Burlington Ford"]
WORK = [("Oil and filter change", 85, 160), ("Front brake pads and rotors", 380, 720), ("Tires - set of 4 LT245/75R16", 780, 1150),
        ("Tire rotation and balance", 45, 90), ("Battery replacement", 180, 290), ("Serpentine belt", 140, 260), ("State inspection", 35, 55),
        ("Wiper blades and fluids", 30, 70), ("Rear leaf spring shackles", 420, 860), ("Check engine light - O2 sensor", 260, 480),
        ("Ladder rack repair", 150, 340), ("Alignment", 95, 150)]


def plate(r) -> str:
    return f"{code(r, 3, 'ABCDEFGHJKLMNPRSTUVWXYZ')}{r.randint(100, 999)}"


def build(seed: int) -> dict:
    r = rng(seed)
    veh = {}
    for unit, desc, fuel, (m_lo, m_hi), (d_lo, d_hi) in UNITS:
        start_odo = r.randint(4000, 9000) if unit == "Van 25" else r.randint(18000, 96000)
        if unit == SOLD:
            start_odo = r.randint(81000, 89000)
        v = {"unit": unit, "desc": desc, "fuel": fuel, "mpg": r.uniform(m_lo, m_hi), "plate": plate(r), "vin6": code(r, 6, "0123456789ABCDEFGHJKLMNPRSTUVWXYZ"),
             "odo": {}, "fills": [], "shop": [], "other": []}
        first = DELIVERY_DATE if unit == NEW else START
        last = SALE_DATE if unit == SOLD else END
        odo = r.randint(9, 31) if unit == NEW else start_odo
        v["first"], v["last"], v["start_odo"] = first, last, odo
        v["odo"][first] = odo
        tank_miles = 0.0
        d = first + timedelta(days=1)
        while d <= last:
            miles = 0 if d.weekday() == 6 else (r.uniform(d_lo, d_hi) * (0.4 if d.weekday() == 5 else 1.0))
            odo += miles
            tank_miles += miles
            v["odo"][d] = odo
            if tank_miles > r.uniform(260, 360) and d.weekday() != 6:
                gal = tank_miles / (v["mpg"] * r.uniform(0.95, 1.05))
                canada = (unit == CANADA and r.random() < 0.45) or (unit == "Van 23" and r.random() < 0.08)
                price = (r.uniform(3.72, 4.39) if fuel == "Diesel" else r.uniform(3.02, 3.79)) + (0.35 if canada else 0)
                v["fills"].append({"date": d, "gal": gal, "price_gal": price, "canada": canada})
                tank_miles = 0.0
            d += timedelta(days=1)
        v["end_odo"] = odo
        v["miles"] = odo - v["start_odo"]
        # shop work
        n_jobs = 1 if unit == NEW else r.randint(3, 6)
        for _ in range(n_jobs):
            w, lo, hi = r.choice(WORK[:1] + WORK[7:8] + WORK[10:11]) if unit == NEW else r.choice(WORK)
            jd = day_in(r, first + timedelta(days=3), last - timedelta(days=1), weekday_only=True)
            parts = money(r, lo * 0.4, hi * 0.6); labor = money(r, lo * 0.4, hi * 0.5)
            tax = round(parts * 0.06, 2)
            v["shop"].append({"date": jd, "work": w, "parts": parts, "labor": labor, "tax": tax, "total": round(parts + labor + tax, 2),
                              "shop": r.choice(SHOPS)})
        if unit == SOLD:
            jd = date(2026, 4, r.randint(6, 10))
            parts, labor = money(r, 240, 420), money(r, 180, 300)
            v["shop"].append({"date": jd, "work": "Pre-sale repairs - exhaust leak, detail", "parts": parts, "labor": labor,
                              "tax": round(parts * 0.06, 2), "total": round(parts * 1.06 + labor, 2), "shop": "Champlain Fleet Service"})
        # non-fuel card purchases
        for _ in range(r.randint(3, 9)):
            od = day_in(r, first + timedelta(days=1), last, weekday_only=True)
            if r.random() < 0.55:
                v["other"].append({"date": od, "product": "CAR WASH", "qty": 1, "uom": "EA", "amt": r.choice([12.0, 14.0, 18.0])})
            else:
                amt = money(r, 4, 26)
                v["other"].append({"date": od, "product": "MERCHANDISE", "qty": 1, "uom": "EA", "amt": amt})
        veh[unit] = v
    # finalize money
    for v in veh.values():
        for f in v["fills"]:
            if f["canada"]:
                f["qty"] = round(f["gal"] * L_PER_GAL, 2); f["uom"] = "LTR"
                f["unit_price"] = round(f["price_gal"] / L_PER_GAL, 3)
                f["gal_true"] = f["qty"] / L_PER_GAL
            else:
                f["qty"] = round(f["gal"], 3); f["uom"] = "GAL"
                f["unit_price"] = round(f["price_gal"], 3)
                f["gal_true"] = f["qty"]
            f["amt"] = round(f["qty"] * f["unit_price"], 2)
        v["gallons"] = round(sum(f["gal_true"] for f in v["fills"]), 2)
        v["fuel_cost"] = round(sum(f["amt"] for f in v["fills"]), 2)
        v["maint"] = round(sum(s["total"] for s in v["shop"]), 2)
        v["total"] = round(v["fuel_cost"] + v["maint"], 2)
        v["miles_i"] = int(round(v["end_odo"])) - int(round(v["start_odo"]))
        v["cpm"] = round(v["total"] / v["miles_i"], 4)
        v["mpg_calc"] = round(v["miles_i"] / v["gallons"], 2)
    return {"veh": veh}


def odo_on(v, d):
    return int(round(v["odo"][d]))


def acceptable(d: dict) -> bool:
    V = d["veh"]
    sold, new, ca, pu = V[SOLD], V[NEW], V[CANADA], V[PLATE_UNIT]
    # sold van: naive miles stop at the 31 March read
    naive_miles = odo_on(sold, date(2026, 3, 31)) - odo_on(sold, START)
    if sold["miles_i"] - naive_miles < 700 or abs(sold["total"] / naive_miles - sold["cpm"]) < 0.03:
        return False
    if not any(s["date"] > date(2026, 3, 31) for s in sold["shop"]) or not any(f["date"] > date(2026, 3, 31) for f in sold["fills"]):
        return False
    # Canada van: litres read as gallons
    naive_gal = sum(f["qty"] for f in ca["fills"])
    if sum(1 for f in ca["fills"] if f["canada"]) < 6 or abs(naive_gal - ca["gallons"]) < 0.2 * ca["gallons"]:
        return False
    fleet_total = sum(v["total"] for v in V.values())
    other = sum(o["amt"] for v in V.values() for o in v["other"])
    if other < 0.012 * fleet_total:
        return False
    fleet_miles = sum(v["miles_i"] for v in V.values())
    new_naive = odo_on(new, date(2026, 6, 30)) - odo_on(new, date(2026, 4, 30))
    if (new["miles_i"] - new_naive) < 0.006 * fleet_miles or (sold["miles_i"] - naive_miles) < 0.008 * fleet_miles:
        return False
    if len(pu["shop"]) < 4:
        return False
    # pinned figures stand apart on their rows
    for v in (sold, ca, pu):
        row = [v["miles_i"], v["gallons"], v["fuel_cost"], v["maint"], v["total"], v["mpg_calc"], v["cpm"], v["start_odo"], v["end_odo"]]
        for val in (v["miles_i"], v["gallons"], v["total"]):
            if sum(1 for x in row if abs(x - val) <= 0.01 * val) > 1:
                return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_workbook(fuel_rows, shop_rows, miles_rows, note) -> dict:
    """fuel_rows: [date, unit, product, qty, uom, gallons, amount, counted]; shop_rows: [date, invoice, unit, work, total];
    miles_rows: [unit, start_date, start_odometer, end_date, end_odometer]"""
    nf, ns = len(fuel_rows) + 1, len(shop_rows) + 1
    summ = []
    units = [u[0] for u in UNITS]
    for i, u in enumerate(units, start=2):
        mrow = i
        summ.append([u, f"=Miles!E{mrow}-Miles!C{mrow}",
                     f"=ROUND(SUMIFS(Fuel!$F$2:$F${nf},Fuel!$B$2:$B${nf},$A{i},Fuel!$H$2:$H${nf},1),2)",
                     f"=IF(C{i}=0,0,ROUND(B{i}/C{i},2))",
                     f"=ROUND(SUMIFS(Fuel!$G$2:$G${nf},Fuel!$B$2:$B${nf},$A{i},Fuel!$H$2:$H${nf},1),2)",
                     f"=ROUND(SUMIFS(Shop!$E$2:$E${ns},Shop!$C$2:$C${ns},$A{i}),2)",
                     f"=E{i}+F{i}", f"=IF(B{i}=0,0,ROUND(G{i}/B{i},4))"])
    last = len(units) + 1
    summ.append(["Fleet total", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f"=IF(C{last + 1}=0,0,ROUND(B{last + 1}/C{last + 1},2))",
                 f"=SUM(E2:E{last})", f"=SUM(F2:F{last})", f"=SUM(G2:G{last})", f"=IF(B{last + 1}=0,0,ROUND(G{last + 1}/B{last + 1},4))"])
    summ.append([])
    summ.append([note])
    return {"Cost per mile": {"header": ["Vehicle", "Miles", "Gallons", "MPG", "Fuel cost", "Shop cost", "Total cost", "Cost per mile"],
                              "rows": summ, "widths": {"A": 14, "E": 12, "F": 12, "G": 12, "H": 13}},
            "Miles": {"header": ["unit", "from", "odometer_from", "to", "odometer_to"], "rows": miles_rows},
            "Fuel": {"header": ["date", "unit", "product", "quantity", "uom", "gallons", "amount", "counted"], "rows": fuel_rows},
            "Shop": {"header": ["date", "invoice", "unit", "work", "total"], "rows": shop_rows, "widths": {"D": 36}}}


def truth_rows(d):
    V = d["veh"]
    fuel_rows, shop_rows = [], []
    for u, *_ in UNITS:
        v = V[u]
        for f in v["fills"]:
            fuel_rows.append([f["date"].isoformat(), u, v["fuel"], f["qty"], f["uom"], round(f["gal_true"], 3), f["amt"], 1])
        for o in v["other"]:
            fuel_rows.append([o["date"].isoformat(), u, o["product"], o["qty"], o["uom"], 0, o["amt"], 0])
        for s in v["shop"]:
            shop_rows.append([s["date"].isoformat(), s.get("inv", ""), u, s["work"], s["total"]])
    miles_rows = [[u, V[u]["first"].isoformat(), int(round(V[u]["start_odo"])), V[u]["last"].isoformat(), int(round(V[u]["end_odo"]))] for u, *_ in UNITS]
    return fuel_rows, shop_rows, miles_rows


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    V = d["veh"]
    r = rng(seed + 41)
    # invoice numbers and how the shop names each vehicle
    inv = 21800
    shop_all = sorted([(s["date"], u, s) for u, v in V.items() for s in v["shop"]], key=lambda x: (x[0], x[1]))
    for dt, u, s in shop_all:
        inv += r.randint(3, 40)
        s["inv"] = f"W{inv}"
        s["named"] = V[u]["plate"] if (u == PLATE_UNIT or r.random() < 0.12) else (u.upper() if r.random() < 0.3 else u)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)

    # ---- workspace
    tx = []
    for u, v in V.items():
        card = f"{r.randint(1000, 9999)}"
        for f in v["fills"]:
            st = r.choice(STATIONS_CA if f["canada"] else STATIONS_US)
            tx.append((datetime.combine(f["date"], datetime.min.time()) + timedelta(hours=r.randint(6, 17), minutes=r.randint(0, 59)),
                       card, u.upper().replace(" ", ""), st, "DIESEL #2" if v["fuel"] == "Diesel" else "UNLEADED REG", f["qty"], f["uom"], f["unit_price"], f["amt"]))
        for o in v["other"]:
            st = r.choice(STATIONS_US)
            tx.append((datetime.combine(o["date"], datetime.min.time()) + timedelta(hours=r.randint(6, 17), minutes=r.randint(0, 59)),
                       card, u.upper().replace(" ", ""), st, o["product"], o["qty"], o["uom"], o["amt"], o["amt"]))
    tx.sort(key=lambda x: (x[0], x[2]))
    write_csv(os.path.join(ws, "fuel_card_transactions_2026H1.csv"),
              ["Transaction Date", "Card Last 4", "Vehicle ID", "Merchant", "City", "State/Prov", "Product", "Quantity", "UOM", "Unit Price (USD)", "Amount (USD)"],
              [[t[0].strftime("%m/%d/%Y %H:%M"), t[1], t[2], t[3][0], t[3][1], t[3][2], t[4], f"{t[5]:g}", t[6], f"{t[7]:.3f}", f"{t[8]:.2f}"] for t in tx],
              preamble=["WEX Fleet - Transaction detail - Account 0496-00-812 WESTBROOK PLUMBING & HEATING", "Posting period 01/01/2026 - 06/30/2026", ""],
              crlf=True)
    write_csv(os.path.join(ws, "shop_invoices_2026H1.csv"), ["Invoice", "Date", "Vehicle", "Shop", "Work performed", "Parts", "Labor", "Tax", "Invoice total"],
              [[s["inv"], dt.strftime("%Y-%m-%d"), s["named"], s["shop"], s["work"], f"{s['parts']:.2f}", f"{s['labor']:.2f}", f"{s['tax']:.2f}",
                f"${s['total']:,.2f}"] for dt, u, s in shop_all])
    odo_rows = []
    for u, *_ in UNITS:
        v = V[u]
        line = [u]
        for me in MONTH_ENDS:
            if v["first"] <= me <= v["last"]:
                line.append(odo_on(v, me))
            elif u == SOLD and me > SALE_DATE:
                line.append("sold")
            else:
                line.append("")
        odo_rows.append(line)
    write_xlsx(os.path.join(ws, "fleet_list_and_odometers.xlsx"), {
        "Fleet": {"merged_title": "Westbrook Plumbing & Heating - vehicles", "header": ["Unit", "Vehicle", "Plate (VT)", "VIN (last 6)", "Fuel", "Status"],
                  "rows": [[u, V[u]["desc"], V[u]["plate"], V[u]["vin6"], V[u]["fuel"],
                            f"Sold {SALE_DATE.strftime('%d %b %Y')} - odometer on bill of sale {odo_on(V[u], SALE_DATE):,}" if u == SOLD else
                            f"In service {DELIVERY_DATE.strftime('%d %b %Y')} - delivered with {int(round(V[u]['start_odo']))} miles" if u == NEW else "Active"]
                           for u, *_ in UNITS],
                  "widths": {"A": 10, "B": 30, "C": 12, "D": 12, "F": 52}},
        "Odometer month-end": {"header": ["Unit"] + [me.strftime("%d %b %Y") for me in MONTH_ENDS], "rows": odo_rows,
                               "widths": {"A": 10}}}, creator="Office")
    write_text(os.path.join(ws, "note_from_carla.txt"),
               "Cost per mile, January to June\n\n"
               "For each vehicle I want miles driven, fuel and what we paid the shops, and the cost per mile, plus gallons and MPG so\n"
               "Dave can see which vans are thirsty. Fleet total at the bottom.\n\n"
               "- Miles come from the odometer tab: the 31 Dec reading to the 30 Jun reading. Van 24 went to the dealer in April, and\n"
               "  Van 30 replaced it; the Fleet tab has the odometer on the bill of sale and the miles Van 30 was delivered with.\n"
               "- Fuel is the fuel card. Only count the fuel itself - the card also gets used for car washes and the odd coffee and\n"
               "  snacks, and those are not what it costs to run the van.\n"
               "- When Luc's crew works the Quebec jobs they fill up over the border and WEX shows those in litres. The dollar amounts\n"
               "  are already in US dollars.\n"
               "- Shop cost is the invoice total. Champlain Fleet writes the licence plate instead of the unit number on some invoices.\n\n"
               "Carla\n")

    # ---- reference
    units = [u[0] for u in UNITS]
    write_csv(os.path.join(ref, "fleet_costs.csv"), ["vehicle", "miles", "gallons", "mpg", "fuel_cost", "shop_cost", "total_cost", "cost_per_mile"],
              [[u, V[u]["miles_i"], f"{V[u]['gallons']:.2f}", f"{V[u]['mpg_calc']:.2f}", f"{V[u]['fuel_cost']:.2f}", f"{V[u]['maint']:.2f}",
                f"{V[u]['total']:.2f}", f"{V[u]['cpm']:.4f}"] for u in units])
    fleet_total = round(sum(V[u]["total"] for u in units), 2)
    fleet_miles = sum(V[u]["miles_i"] for u in units)
    sold = V[SOLD]
    write_json(os.path.join(ref, "notes.json"), {
        "fleet_total_cost": fleet_total, "fleet_miles": fleet_miles, "fleet_cost_per_mile": round(fleet_total / fleet_miles, 4),
        "sold": {"unit": SOLD, "sale_odometer": odo_on(sold, SALE_DATE), "march_odometer": odo_on(sold, date(2026, 3, 31)), "miles": sold["miles_i"]},
        "canada_litre_fills": {u: sum(1 for f in V[u]["fills"] if f["canada"]) for u in units},
        "non_fuel_card_spend": round(sum(o["amt"] for u in units for o in V[u]["other"]), 2),
        "plate_named_invoices": [s["inv"] for u in units for s in V[u]["shop"] if s["named"] == V[u]["plate"]]})

    # ---- reference solution
    fuel_rows, shop_rows, miles_rows = truth_rows(d)
    note = ("Miles = odometer at the end of the period (Van 24: bill of sale) less the start (Van 30: delivery). Gallons convert litres at "
            "3.785411784 L per US gallon. Car washes and merchandise on the fuel card are excluded. Shop cost is the invoice total; plates "
            "matched to units from the Fleet tab.")
    write_xlsx(os.path.join(sol, "fleet_costs.xlsx"), report_workbook(fuel_rows, shop_rows, miles_rows, note), creator="reference")

    write_task_yaml(HERE, {
        "id": "fleet-cost-per-mile", "track": "desk", "category": "reports",
        "title": "Cost per mile per vehicle for the first half",
        "ask": ("Can you work out what each of our vehicles cost per mile to run from January to June? Save it as fleet_costs.xlsx with "
                "live formulas. Carla's note says where everything comes from.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"fill-ups at Quebec stations are in litres (UOM LTR) with the amount already in US dollars; Van 26 has "
            f"{sum(1 for f in V[CANADA]['fills'] if f['canada'])} of them and adding the Quantity column as gallons inflates its gallons "
            "and wrecks its MPG (check: Van 26 gallons)",
            f"Van 24 was sold on {SALE_DATE.isoformat()} and the odometer tab says 'sold' from April; its miles run to the "
            f"{odo_on(sold, SALE_DATE):,} on the bill of sale (Fleet tab), while its April fuel and pre-sale repairs are real costs, so "
            "stopping at the 31 March read overstates its cost per mile (checks: Van 24 miles; Van 24 cost per mile)",
            f"Van 30 entered service on {DELIVERY_DATE.isoformat()} with its delivery miles on the Fleet tab and no reading before 30 April; "
            "starting from the 30 April read loses its first ten days (check: fleet miles)",
            "the fuel card also carries car washes and merchandise (qty 1, UOM EA) that Carla excludes (check: fleet total cost)",
            "Champlain Fleet names Van 22 by its licence plate on every invoice (and a few other vans some of the time), and unit names come "
            "as 'Van 22', 'VAN 22' and 'VAN22'; a join on the unit number alone drops those invoices (check: Van 22 total cost)",
            "the WEX export has a three-line preamble and CRLF endings and invoice totals are '$1,234.56' text (check: fleet total cost)",
            "the summary has to be live formulas (check: live formulas)",
        ],
        "checks": [
            {"type": "file_exists", "name": "fleet_costs.xlsx exists", "path": "fleet_costs.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "fleet_costs.xlsx", "min_count": 10},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "fleet_costs.xlsx"},
            {"type": "xlsx_value_present", "name": "Van 26 gallons (litres converted)", "path": "fleet_costs.xlsx",
             "expected": V[CANADA]["gallons"], "rel_tol": 0.001, "rounding": "Quebec fill-ups converted from litres to US gallons", "near_text": "van 26"},
            {"type": "xlsx_value_present", "name": "Van 24 miles (to the bill of sale)", "path": "fleet_costs.xlsx",
             "expected": sold["miles_i"], "rel_tol": cent_tol(sold["miles_i"], 0.002), "near_text": "van 24"},
            {"type": "xlsx_value_present", "name": "Van 24 cost per mile", "path": "fleet_costs.xlsx",
             "expected": sold["cpm"], "rel_tol": 0.005, "near_text": "van 24"},
            {"type": "xlsx_value_present", "name": "Van 22 total cost (plate-named invoices included)", "path": "fleet_costs.xlsx",
             "expected": V[PLATE_UNIT]["total"], "rel_tol": cent_tol(V[PLATE_UNIT]["total"], 0.004), "near_text": "van 22"},
            {"type": "xlsx_value_present", "name": "fleet total cost (no car washes or snacks)", "path": "fleet_costs.xlsx",
             "expected": fleet_total, "rel_tol": cent_tol(fleet_total, 0.004), "near_text": "total"},
            {"type": "xlsx_value_present", "name": "fleet miles", "path": "fleet_costs.xlsx",
             "expected": fleet_miles, "rel_tol": cent_tol(fleet_miles, 0.004), "near_text": "total"},
        ],
    })
    print(f"seed={seed} fleet_total={fleet_total} miles={fleet_miles} " +
          " ".join(f"{u}:{V[u]['miles_i']}mi/{V[u]['gallons']}gal/${V[u]['total']}/{V[u]['cpm']}" for u in units))


def write_naive(d: dict, out: str) -> None:
    """Every card line as fuel with Quantity read as gallons, shop invoices joined on the unit number only, miles from the
    first to the last month-end reading present."""
    os.makedirs(out, exist_ok=True)
    V = d["veh"]
    fuel_rows, shop_rows, miles_rows = [], [], []
    for u, *_ in UNITS:
        v = V[u]
        for f in v["fills"]:
            fuel_rows.append([f["date"].isoformat(), u, v["fuel"], f["qty"], f["uom"], f["qty"], f["amt"], 1])
        for o in v["other"]:
            fuel_rows.append([o["date"].isoformat(), u, o["product"], o["qty"], o["uom"], 0, o["amt"], 1])
        for s in v["shop"]:
            named = s["named"].replace("VAN ", "Van ")
            shop_rows.append([s["date"].isoformat(), s["inv"], named if named.startswith("Van") or named.startswith("Truck") else s["named"], s["work"], s["total"]])
        reads = [(me, odo_on(v, me)) for me in MONTH_ENDS if v["first"] <= me <= v["last"]]
        miles_rows.append([u, reads[0][0].isoformat(), reads[0][1], reads[-1][0].isoformat(), reads[-1][1]])
    write_xlsx(os.path.join(out, "fleet_costs.xlsx"), report_workbook(fuel_rows, shop_rows, miles_rows, "naive"), creator="naive")


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
