#!/usr/bin/env python3
"""fleet-mileage-monthly: monthly miles per service van from the odometer readings drivers type at the pump.

    python gen.py [--seed N] [--naive DIR]

Business: a plumbing contractor with eight service vans on fuel cards. The only odometer record is what the
drivers key in at the pump, which lands in the fuel-card export sorted by the day the bank posted it. The
insurer wants miles per van per month for the first half.

Traps (each caught by a check, see task.yaml):
  * the export is sorted by posted date, so readings are out of order and month-end fill-ups post the next month
                                                                              (check: miles per van and month)
  * the first rows are late-December fill-ups posted in January: they are January's starting point
                                                                              (check: miles per van and month)
  * VAN-06's instrument cluster was replaced in March and restarted at zero; the shop log has the reading at the swap
                                                                              (check: miles per van and month)
  * VAN-04 has no readings in April: the month stays blank and flagged, and May covers March to May
                                                                              (checks: miles per van and month; a row for every van and month)
  * the card system writes the van three ways (VAN-03, VAN 03, Van 03)       (check: every van)
  * car-wash and wiper-fluid purchases carry no odometer                     (check: miles per van and month)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

VANS = [f"VAN-{i:02d}" for i in range(1, 9)]
MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]
RESET_VAN, RESET_DAY = "VAN-06", date(2026, 3, 17)
GAP_VAN, GAP_MONTH = "VAN-04", "2026-04"
MODELS = ["2021 Ford Transit 250", "2022 Ford Transit 250", "2020 Ram ProMaster 2500", "2023 Ford Transit 350",
          "2021 Chevrolet Express 2500", "2019 Ram ProMaster 2500", "2022 Nissan NV2500", "2024 Ford Transit 250"]
SITES = ["SHELL 57444", "CHEVRON 0091", "COSTCO GAS #0891", "76 STATION 2210", "ARCO 42117", "SPEEDWAY 8812"]


def mkey(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def build(seed: int) -> dict:
    r = rng(seed)
    drivers = [f"{f} {l}" for f, l in people(r, len(VANS))]
    vans = []
    txns = []
    for i, v in enumerate(VANS):
        odo = r.randint(18000, 96000)
        daily = r.uniform(45, 95)
        displayed_offset = 0          # what the dash shows = true odometer - offset (after the reset)
        reset_old = None
        readings = []                 # (day, displayed reading)
        day = date(2025, 12, 22)
        next_fill = day + timedelta(days=r.randint(1, 3))
        while day <= date(2026, 6, 30):
            if day.weekday() < 5:
                odo += daily * r.uniform(0.6, 1.4)
            elif day.weekday() == 5 and r.random() < 0.3:
                odo += daily * r.uniform(0.2, 0.6)
            if v == RESET_VAN and day == RESET_DAY:
                reset_old = int(odo)
                displayed_offset = int(odo)
                odo += r.uniform(3, 12)           # the drive back from the dealer, on the new cluster
            if day >= next_fill:
                gap = (v == GAP_VAN and mkey(day) == GAP_MONTH)
                if not gap:
                    readings.append((day, int(odo) - displayed_offset))
                next_fill = day + timedelta(days=r.randint(3, 5))
            day += timedelta(days=1)
        vans.append({"id": v, "driver": drivers[i], "model": MODELS[i], "plate": f"{r.choice('ABCDEFGHJK')}{r.randint(10, 99)}-{code(r, 3)}",
                     "readings": readings, "reset_old": reset_old})
        for day, reading in readings:
            txns.append({"van": v, "day": day, "odo": reading, "kind": "fuel", "k": r.random()})
        for _ in range(r.randint(2, 4)):
            d = day_in(r, date(2026, 1, 5), date(2026, 6, 26))
            if v == GAP_VAN and mkey(d) == GAP_MONTH:
                continue
            txns.append({"van": v, "day": d, "odo": None, "kind": r.choice(["CAR WASH", "WIPER FLUID", "DEF FLUID"]), "k": r.random()})
    for t in txns:
        lag = r.choice([1, 1, 1, 2, 2, 3]) + (2 if t["day"].weekday() >= 4 else 0)
        t["posted"] = t["day"] + timedelta(days=lag)
        t["style"] = r.randrange(3)
        t["gallons"] = round(r.uniform(14.0, 26.0), 3) if t["kind"] == "fuel" else None
        t["amount"] = round(t["gallons"] * r.uniform(3.55, 4.25), 2) if t["kind"] == "fuel" else round(r.uniform(6, 18), 2)
        t["site"] = r.choice(SITES)
    txns = [t for t in txns if date(2026, 1, 1) <= t["posted"] <= date(2026, 7, 2)]
    # ---- truth, from the readings that made it into the export: last reading of the month minus last reading before it ----
    miles, flags = {}, {}
    for van in vans:
        rd = sorted((t["day"], t["odo"]) for t in txns if t["van"] == van["id"] and t["odo"] is not None)
        van["exported"] = rd
        known = [(d, o) for d, o in rd if d.month == 12 and d.year == 2025]
        last = known[-1][1] if known else None
        last_month = "2025-12"
        for m in MONTHS:
            inm = [(d, o) for d, o in rd if mkey(d) == m]
            if not inm:
                miles[(van["id"], m)] = None
                flags[(van["id"], m)] = "no readings"
                continue
            end = inm[-1][1]
            if last is None:
                val = None
            elif van["id"] == RESET_VAN and m == mkey(RESET_DAY):
                val = (van["reset_old"] - last) + end
                flags[(van["id"], m)] = "cluster replaced"
            else:
                val = end - last
                if last_month != MONTHS[MONTHS.index(m) - 1] and m != "2026-01":
                    flags[(van["id"], m)] = f"covers {last_month} to {m}"
            miles[(van["id"], m)] = val
            last, last_month = end, m
    return {"vans": vans, "txns": txns, "miles": miles, "flags": flags, "drivers": drivers}


def naive_miles(d: dict) -> dict:
    """Bucket by posted month, file order, miles = last reading minus first reading inside the month."""
    out = {}
    rows = sorted([t for t in d["txns"] if t["odo"] is not None], key=lambda t: (t["posted"], t["k"]))
    for van in VANS:
        for m in MONTHS:
            vals = [t["odo"] for t in rows if t["van"] == van and mkey(t["posted"]) == m]
            out[(van, m)] = (vals[-1] - vals[0]) if vals else None
    return out


def acceptable(d: dict) -> bool:
    vans = {v["id"]: v for v in d["vans"]}
    if any(not any(day.year == 2025 for day, _ in v["exported"]) for v in d["vans"]):
        return False
    if any(d["miles"][(v, m)] is None for v in VANS for m in MONTHS if (v, m) != (GAP_VAN, GAP_MONTH)):
        return False
    rv = vans[RESET_VAN]["exported"]
    if not any(day < RESET_DAY and mkey(day) == "2026-03" for day, _ in rv) or not any(day > RESET_DAY and mkey(day) == "2026-03" for day, _ in rv):
        return False
    # at least one month-end fill-up per van posts in the next month, and the file order differs from date order
    crossing = sum(1 for t in d["txns"] if t["odo"] is not None and mkey(t["posted"]) != mkey(t["day"]))
    if crossing < 10:
        return False
    nm = naive_miles(d)
    wrong = sum(1 for k, v in d["miles"].items() if v is not None and (nm.get(k) is None or abs(nm[k] - v) > 1))
    return wrong >= 30


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["vehicle", "month", "miles", "flag"]
    if naive_dir:
        nm = naive_miles(d)
        write_csv(os.path.join(naive_dir, "mileage.csv"), header,
                  [[v, m, nm[(v, m)], ""] for v in VANS for m in MONTHS if nm[(v, m)] is not None])
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 3)
    vans = {v["id"]: v for v in d["vans"]}

    write_xlsx(os.path.join(ws, "vehicle_list.xlsx"), {"Fleet": {
        "merged_title": "Service vehicles - active fleet",
        "header": ["Unit", "Year / Make / Model", "Plate", "Assigned driver", "Fuel card (last 4)"],
        "rows": [[v["id"], v["model"], v["plate"], v["driver"], f"{r.randint(1000, 9999)}"] for v in d["vans"]],
        "widths": {"B": 28, "D": 22}}}, creator="Office")
    rows = []
    for t in sorted(d["txns"], key=lambda t: (t["posted"], t["k"])):
        v = vans[t["van"]]
        van_txt = [t["van"], t["van"].replace("-", " "), "Van " + t["van"][-2:]][t["style"]]
        rows.append([f"****{1000 + VANS.index(t['van']) * 1111 % 9000}",
                     v["driver"].upper(), van_txt, date_variant(t["day"], 1), date_variant(t["posted"], 1), t["site"],
                     "UNLEADED" if t["kind"] == "fuel" else t["kind"], "" if t["gallons"] is None else f"{t['gallons']:.3f}",
                     money_str(t["amount"], 1), "" if t["odo"] is None else t["odo"]])
    write_csv(os.path.join(ws, "fuel_card_export_2026-01-01_2026-07-02.csv"),
              ["Card", "Driver", "Vehicle", "Transaction Date", "Posted Date", "Merchant", "Product", "Gallons", "Amount", "Odometer"],
              rows, preamble=["FleetFuel Pro - transaction detail by posted date", "Posted 01/01/2026 - 07/02/2026"], crlf=True)
    rv = vans[RESET_VAN]
    shop = [["RO-5102", "01/14/2026", "VAN-02", "Oil change, tire rotation", "Northfield Auto Body", "$184.20", ""],
            ["RO-5188", "02/03/2026", "VAN-07", "Replace front brake pads", "Northfield Auto Body", "$412.75", ""],
            ["RO-5254", date_variant(RESET_DAY, 1), RESET_VAN,
             f"Instrument cluster failed - replaced under warranty. Old cluster read {rv['reset_old']:,} at removal; "
             "new cluster starts at 0 (dealer could not program mileage)", "Valley Ford", "$0.00", "warranty"],
            ["RO-5290", "04/09/2026", "VAN-01", "Oil change", "Northfield Auto Body", "$96.40", ""],
            ["RO-5317", "05/21/2026", "VAN-05", "Replace rear shocks", "Northfield Auto Body", "$688.00", ""]]
    write_csv(os.path.join(ws, "shop_log_2026.csv"), ["RO #", "Date", "Unit", "Work done", "Shop", "Cost", "Notes"], shop)
    write_text(os.path.join(ws, "note_from_ops.txt"),
               "Mileage for the insurance renewal\n"
               "\n"
               "The carrier wants miles driven per van for each month January through June. The only odometer we have is\n"
               "what the guys punch in at the pump, so it comes from the fuel card export. Go by the day they fueled, and a\n"
               "month's miles are the last reading in that month minus the last reading before it.\n"
               "\n"
               "If a van has no reading at all in a month, do not put 0 - the van was out working, we just don't have a\n"
               "number. Leave the miles empty and flag it. The next month with a reading then covers everything since\n"
               "the last one; flag that month too so nobody thinks it was a monster month.\n"
               "\n"
               "Anything the shop did that touches the odometer is in the shop log.\n"
               "\n"
               "One line per van per month please: vehicle (like VAN-01), month (2026-01), miles, flag.\n"
               "\n"
               "- Tom\n")

    out = []
    for v in VANS:
        for m in MONTHS:
            mi = d["miles"][(v, m)]
            out.append([v, m, "" if mi is None else mi, d["flags"].get((v, m), "")])
    write_csv(os.path.join(ref, "mileage.csv"), header, out)
    write_csv(os.path.join(sol, "mileage.csv"), header, out)
    write_json(os.path.join(ref, "notes.json"), {"reset": {"van": RESET_VAN, "day": RESET_DAY, "old_reading": rv["reset_old"]},
                                                  "gap": {"van": GAP_VAN, "month": GAP_MONTH}})
    write_task_yaml(HERE, {
        "id": "fleet-mileage-monthly", "track": "desk", "category": "spreadsheet",
        "title": "Monthly miles per van for the insurer",
        "ask": ("The insurance renewal needs miles per van per month for January to June, worked out from the fuel card export. "
                "Save it as mileage.csv. Tom's note says how he wants it counted.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the export is sorted by posted date, one to five days after the fill-up, so readings are out of order and month-end "
            "fill-ups post in the next month; bucketing or ordering by posted date moves miles between months "
            "(check: miles per van and month)",
            "the first rows are late-December fill-ups posted in January; they are January's starting reading, and a max-minus-min "
            "inside each month drops the miles driven between the last fill-up of one month and the first of the next "
            "(check: miles per van and month)",
            "VAN-06's instrument cluster was replaced in March and restarted at zero; the shop log carries the old reading at the "
            "swap, so March is (old reading minus February's last) plus March's last reading on the new cluster "
            "(check: miles per van and month)",
            "VAN-04 has no readings at all in April: the April row stays with empty miles and a flag rather than 0, and May's "
            "miles run from the last March reading (checks: miles per van and month; a row for every van and month)",
            "the card system writes the unit as 'VAN-03', 'VAN 03' or 'Van 03'; grouping on the raw text splits every van into "
            "three (check: every van)",
            "car-wash, wiper and DEF purchases carry no odometer and sit between fill-ups (check: miles per van and month)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "mileage.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every van", "path": "mileage.csv", "column": "vehicle", "ref": "mileage.csv",
             "normalize": ["alnum"]},
            {"type": "csv_row_count", "name": "a row for every van and month", "path": "mileage.csv", "equals_ref": "mileage.csv"},
            {"type": "custom", "name": "miles per van and month", "module": "check.py"},
        ],
    })
    print(f"seed={seed} reset_old={rv['reset_old']}")
    for v in VANS:
        print(" ", v, [d["miles"][(v, m)] for m in MONTHS])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(500):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
