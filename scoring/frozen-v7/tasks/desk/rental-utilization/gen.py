#!/usr/bin/env python3
"""rental-utilization: days out per machine per month for an equipment rental yard, January to June.

    python gen.py [--seed N] [--naive DIR]

Business: Summit Tool & Lift Rental in Boise. The counter system exports one line per rental contract with
the machine name as it was on the day. The owner wants days out per machine per month for the insurer's
utilization schedule.

Traps (each caught by a check, see task.yaml):
  * rentals cross month ends (and one December rental runs into January); days go to the month they fall in
                                                                            (check: days out per month)
  * a day is any calendar day the machine was off the yard, counting the day out and the day back; a
    same-day return is one day, so return minus out undercounts every rental (check: days out per month)
  * Skid Steer #2 was rebuilt and renamed in April; its rentals are under two names and it is one machine
    under its current name                                                   (checks: every machine; row count)
  * a machine that comes back in the morning and goes out again that afternoon was out one day, not two
                                                                            (check: days out per month)
  * cancelled reservations sit in the log with dates; contracts still out count through 30 June
                                                                            (checks: days out per month; half-year total)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MACHINES = [  # tag, current name, category, kind
    ("EX-01", "Kubota KX040 Mini Excavator", "Earthmoving", "big"),
    ("EX-02", "Kubota U17 Mini Excavator", "Earthmoving", "big"),
    ("SS-01", "Skid Steer #1", "Earthmoving", "big"),
    ("SS-02", "Bobcat T76 Track Loader", "Earthmoving", "big"),
    ("SL-19", "Genie GS-1930 Scissor Lift", "Aerial", "lift"),
    ("SL-26", "Genie GS-2632 Scissor Lift", "Aerial", "lift"),
    ("BL-45", "JLG 450AJ Boom Lift", "Aerial", "lift"),
    ("TD-01", "Toro Dingo TX 1000", "Earthmoving", "big"),
    ("AC-01", "Towable Air Compressor 185 CFM", "Tools", "small"),
    ("PW-01", "Hot Water Pressure Washer", "Tools", "small"),
    ("PC-01", "Plate Compactor", "Tools", "small"),
    ("GN-01", "Generator 7kW", "Tools", "small"),
]
RENAMED_TAG, OLD_NAME, RENAME_DATE = "SS-02", "Skid Steer #2", date(2026, 4, 13)
MONTHS = [(2026, m) for m in range(1, 7)]
COLS = ["jan", "feb", "mar", "apr", "may", "jun"]
END = date(2026, 6, 30)
CUSTOMERS = ["Treasure Valley Builders", "Boise River Homes", "Harris Concrete", "Owyhee Fence Co", "Northend Remodel",
             "Capitol Painting", "Ridge to River Trails", "Garden City Excavating", "Walk-in customer", "Kuna Pools",
             "Eagle Sprinkler & Turf", "Idaho Signworks", "Parkcenter Property Svcs", "Meridian Stucco", "Walk-in customer"]


def build(seed: int) -> dict:
    r = rng(seed)
    contracts = []
    for tag, name, cat, kind in MACHINES:
        day = date(2025, 12, 1) + timedelta(days=r.randint(0, 10))
        while day <= END:
            if kind == "small":
                length = 0 if r.random() < 0.45 else r.randint(1, 3)
            elif kind == "lift":
                length = r.randint(1, 12)
            else:
                length = 0 if r.random() < 0.1 else r.randint(1, 8)
            out_dt = datetime(day.year, day.month, day.day, r.randint(6, 13), r.choice([0, 15, 30, 45]))
            ret = day + timedelta(days=length)
            ret_dt = datetime(ret.year, ret.month, ret.day, r.randint(8, 17) if length else r.randint(14, 18), r.choice([0, 10, 20, 40, 50]))
            if length == 0 and ret_dt <= out_dt:
                ret_dt = out_dt + timedelta(hours=3)
            contracts.append({"tag": tag, "out": out_dt, "ret": ret_dt if ret <= END else None, "status": "Closed" if ret <= END else "Out",
                              "cust": r.choice(CUSTOMERS)})
            if ret > END:
                break
            g = r.random()
            if g < 0.10:
                day = ret            # back out the same afternoon
            else:
                day = ret + timedelta(days=r.randint(1, 9 if kind != "small" else 6))
    # make sure the back-to-back case has an afternoon departure after a morning return
    for a, b in zip(contracts, contracts[1:]):
        if a["tag"] == b["tag"] and a["ret"] and a["ret"].date() == b["out"].date():
            a["ret"] = a["ret"].replace(hour=8, minute=40)
            b["out"] = b["out"].replace(hour=13, minute=30)
            if a["out"] >= a["ret"]:
                a["out"] = a["out"].replace(hour=6, minute=30)
    # cancelled reservations
    for _ in range(r.randint(5, 8)):
        tag = r.choice([m[0] for m in MACHINES])
        day = day_in(r, date(2026, 1, 5), date(2026, 6, 20))
        contracts.append({"tag": tag, "out": datetime(day.year, day.month, day.day, 8, 0), "ret": None, "status": "Cancelled",
                          "cust": r.choice(CUSTOMERS), "due": day + timedelta(days=r.randint(1, 5))})
    contracts.sort(key=lambda c: (c["out"], c["tag"]))
    for i, c in enumerate(contracts):
        c["no"] = f"RC-{25950 + i}"
        if "due" not in c:
            if c["ret"]:
                c["due"] = max(c["out"].date(), c["ret"].date() + timedelta(days=r.choice([0, 0, 0, 1, 1, -1, 2])))
            else:
                c["due"] = date(2026, 7, r.randint(1, 6))
        name = dict((m[0], m[1]) for m in MACHINES)[c["tag"]]
        c["name"] = OLD_NAME if c["tag"] == RENAMED_TAG and c["out"].date() < RENAME_DATE else name
    # ---- truth ----
    days = {m[0]: set() for m in MACHINES}
    for c in contracts:
        if c["status"] == "Cancelled":
            continue
        start = c["out"].date()
        stop = c["ret"].date() if c["ret"] else END
        dd = start
        while dd <= stop:
            if date(2026, 1, 1) <= dd <= END:
                days[c["tag"]].add(dd)
            dd += timedelta(days=1)
    table = {tag: [sum(1 for x in days[tag] if (x.year, x.month) == ym) for ym in MONTHS] for tag in days}
    return {"contracts": contracts, "table": table}


def naive_table(d: dict) -> dict:
    """Return minus out, all in the month it went out, by the name on the contract, skipping open and December."""
    out = {}
    for c in d["contracts"]:
        if c["status"] != "Closed" or c["out"].year != 2026:
            continue
        row = out.setdefault(c["name"], [0] * 6)
        row[c["out"].month - 1] += (c["ret"].date() - c["out"].date()).days
    return out


def acceptable(d: dict) -> bool:
    cs = d["contracts"]
    live = [c for c in cs if c["status"] != "Cancelled"]
    cross = [c for c in live if c["ret"] and c["ret"].month != c["out"].month and c["out"].year == 2026]
    if len(cross) < 6 or not any(c["out"].year == 2025 and c["ret"] and c["ret"].year == 2026 for c in live):
        return False
    if sum(1 for c in live if c["ret"] and c["ret"].date() == c["out"].date()) < 8:
        return False
    b2b = [(a, b) for a, b in zip(live, live[1:]) if False]
    by_tag = {}
    for c in live:
        by_tag.setdefault(c["tag"], []).append(c)
    b2b = sum(1 for t, lst in by_tag.items() for a, b in zip(lst, lst[1:]) if a["ret"] and a["ret"].date() == b["out"].date())
    if b2b < 2:
        return False
    ss2 = by_tag.get(RENAMED_TAG, [])
    if sum(1 for c in ss2 if c["out"].date() < RENAME_DATE and c["out"].year == 2026) < 3 or sum(1 for c in ss2 if c["out"].date() >= RENAME_DATE) < 3:
        return False
    if sum(1 for c in cs if c["status"] == "Out") < 1 or sum(1 for c in cs if c["status"] == "Out") > 4:
        return False
    # the open contract must have gone out before the last few days so it matters
    if not any(c["status"] == "Out" and c["out"].date() <= date(2026, 6, 27) for c in cs):
        return False
    # every machine's months are not all equal to the naive ones
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["machine"] + COLS + ["total"]
    names = {m[0]: m[1] for m in MACHINES}
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        nt = naive_table(d)
        write_csv(os.path.join(naive_dir, "utilization.csv"), header, [[n] + row + [sum(row)] for n, row in sorted(nt.items())])
        return
    ws, ref, sol = task_dirs(HERE)

    def fmt(dt):
        return f"{dt.month}/{dt.day}/{dt.year} {dt.strftime('%I:%M %p').lstrip('0')}"

    rows = []
    for c in d["contracts"]:
        nm = c["name"] + (" " if sum(map(ord, c["no"])) % 9 == 0 else "")
        rows.append([c["no"], c["cust"], nm, fmt(c["out"]), f"{c['due'].month}/{c['due'].day}/{c['due'].year}",
                     fmt(c["ret"]) if c["ret"] else "", c["status"]])
    write_csv(os.path.join(ws, "rental_contracts_export_2026-07-01.csv"),
              ["Contract", "Customer", "Equipment", "Date Out", "Due Back", "Date Returned", "Status"], rows,
              preamble=["Summit Tool & Lift Rental - Contract History", "Date Out between 12/01/2025 and 06/30/2026"], crlf=True)
    write_xlsx(os.path.join(ws, "equipment_list.xlsx"), {"Fleet": {
        "header": ["Asset Tag", "Name", "Category", "In Service", "Notes"],
        "rows": [[tag, name, cat, date(2023 + (i % 3), 3 + i % 8, 1),
                  f"Engine rebuilt and converted to tracks - renamed from {OLD_NAME} on {RENAME_DATE.month}/{RENAME_DATE.day}/{RENAME_DATE.year}"
                  if tag == RENAMED_TAG else ""] for i, (tag, name, cat, _) in enumerate(MACHINES)],
        "widths": {"A": 10, "B": 32, "C": 12, "D": 12, "E": 70}}}, creator="Summit Tool & Lift Rental")
    write_text(os.path.join(ws, "note_from_hank.txt"),
               "Utilization for the insurance renewal\n"
               "\n"
               "The insurer wants to know how hard each machine works: days out per machine for every month,\n"
               "January to June. The contract history from the counter system is in the folder, with the fleet list.\n"
               "\n"
               "How we count a day: any calendar day the machine was off the yard. The day it goes out counts and the\n"
               "day it comes back counts, whatever the time. Out at 7 in the morning and back by 5 the same day is one\n"
               "day. If a machine comes back in the morning and goes out again that afternoon, that is still one day -\n"
               "the insurer wants days the machine was out, not contract-days.\n"
               "\n"
               "A rental that runs over a month end counts in both months, each day in its own month. Cancelled\n"
               "reservations never left the yard. Anything still out when I ran the export counts through 30 June.\n"
               "\n"
               "One line for every machine on the fleet list, under the name it has now, even if it didn't go out.\n"
               "Columns: machine, jan, feb, mar, apr, may, jun, total. Save it as utilization.csv.\n"
               "\n"
               "- Hank\n")

    # ---- reference ----
    ref_rows = [[names[tag]] + d["table"][tag] + [sum(d["table"][tag])] for tag, *_ in MACHINES]
    write_csv(os.path.join(ref, "utilization.csv"), header, ref_rows)
    write_csv(os.path.join(sol, "utilization.csv"), header, ref_rows)
    write_json(os.path.join(ref, "notes.json"), {"renamed": {"tag": RENAMED_TAG, "old": OLD_NAME, "new": names[RENAMED_TAG],
                                                              "date": RENAME_DATE.isoformat()},
                                                  "open_contracts": [c["no"] for c in d["contracts"] if c["status"] == "Out"],
                                                  "cancelled": [c["no"] for c in d["contracts"] if c["status"] == "Cancelled"]})

    write_task_yaml(HERE, {
        "id": "rental-utilization", "track": "desk", "category": "spreadsheet",
        "title": "Days out per machine per month for the insurer",
        "ask": ("The insurer wants days out for each of our machines, month by month for January to June. Work it out "
                "from the contract history and save it as utilization.csv - Hank's note says how we count.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "rentals cross month ends and a December rental runs into January; putting a whole rental in the month it "
            "went out moves days between months and loses January's share (check: days out per month)",
            "a day is any calendar day off the yard, counting the day out and the day back, so a same-day return is "
            "one day; Date Returned minus Date Out gives zero for same-day rentals and undercounts every other rental "
            "by one (checks: days out per month; half-year total)",
            f"{OLD_NAME} was rebuilt and renamed {names[RENAMED_TAG]} on {RENAME_DATE.isoformat()}; grouping on the "
            "contract's Equipment text gives two rows for one machine, and Skid Steer #1 keeps its name "
            "(checks: every machine under its current name; row count)",
            "a machine returned in the morning and rented again that afternoon was out one day, so adding up rental "
            "days per contract counts that day twice (check: days out per month)",
            f"cancelled reservations carry a Date Out and a Due Back; {sum(1 for c in d['contracts'] if c['status'] == 'Out')} "
            "contracts are still Out with no return date and count through 30 June (checks: days out per month; half-year total)",
            "the export has a two-line preamble, CRLF endings, 12-hour times and a trailing space on some equipment "
            "names (check: every machine under its current name)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "utilization.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every machine under its current name", "path": "utilization.csv",
             "column": "machine", "ref": "utilization.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "utilization.csv", "equals_ref": "utilization.csv"},
            {"type": "csv_values_match", "name": "days out per month", "path": "utilization.csv", "ref": "utilization.csv",
             "key": "machine", "columns": COLS, "numeric": True, "tolerance": 0, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "half-year total", "path": "utilization.csv", "ref": "utilization.csv",
             "key": "machine", "columns": ["total"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0},
        ],
    })
    print(f"seed={seed} contracts={len(d['contracts'])}")
    for tag, *_ in MACHINES:
        print(f"  {names[tag]:34} {d['table'][tag]} {sum(d['table'][tag])}")


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
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
