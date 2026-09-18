#!/usr/bin/env python3
"""delivery-performance: on-time delivery by hub, and why the late ones were late, for a final-mile carrier.

    python gen.py [--seed N] [--naive DIR]

Business: a three-hub furniture and appliance delivery operation. The handhelds stamp every scan in UTC,
the customer was promised a window in local time, and big items sometimes arrive on two trucks.

Traps (each caught by a check, see task.yaml):
  * promised windows are hours, not days                       (checks: Portland on time; on-time rates)
  * scan times are UTC, hub windows are local                  (checks: Portland on time; on-time rates)
  * split shipments arrive on two stops and count once         (checks: Denver shipments delivered; total delivered)
  * attempted, refused and cancelled stops are not deliveries  (checks: Denver shipments delivered; total delivered)
  * late reasons are free text over five buckets plus blanks   (check: weather delays)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


# bizgen.write_xlsx leaves openpyxl's save-time wall clock in docProps/core.xml, so two runs a
# second apart produce different bytes and the validator's determinism check fails intermittently.
# Local workaround (tasks/lib is not ours to change): pin dcterms:modified and re-freeze the zip.
import io as _io  # noqa: E402
import re as _re  # noqa: E402
import zipfile as _zip  # noqa: E402


def stable_xlsx(path: str, sheets: dict, creator: str = "Export") -> None:
    write_xlsx(path, sheets, creator=creator)
    with _zip.ZipFile(path) as z:
        items = sorted((n, z.read(n)) for n in z.namelist())
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as out:
        for name, data in items:
            if name == "docProps/core.xml":
                data = _re.sub(rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>",
                               b'<dcterms:modified xsi:type="dcterms:W3CDTF">2026-01-15T09:00:00Z</dcterms:modified>',
                               data)
            zi = _zip.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = _zip.ZIP_DEFLATED
            out.writestr(zi, data)
    write_bytes(path, buf.getvalue())

# hub, UTC offset in August, shipments
HUBS = [("Portland", -7, 132), ("Denver", -6, 118), ("Austin", -5, 124)]
HUB_NAMES = [h[0] for h in HUBS]
WINDOWS = [("AM", 8 * 60, 12 * 60), ("PM", 12 * 60, 17 * 60), ("08:00-10:00", 8 * 60, 10 * 60),
           ("13:00-15:00", 13 * 60, 15 * 60), ("All day", 8 * 60, 17 * 60)]
REASONS = [
    ("Weather", ["weather", "Weather - storm", "WEATHER DELAY", "heavy rain, weather", "weather hold"]),
    ("Mechanical", ["truck breakdown", "Mechanical", "vehicle issue", "MECHANICAL - lift gate", "breakdown on route"]),
    ("Customer", ["customer not home", "Customer NH", "customer asked for later", "customer unavailable"]),
    ("Address", ["address wrong", "Address issue", "bad address on the order", "ADDRESS - gate code"]),
    ("Route volume", ["route volume", "overloaded route", "Route volume - extra stops", "too many stops"]),
]
BUCKETS = [b for b, _ in REASONS] + ["Not recorded"]
NON_DELIVERED = ["Attempted - no access", "Refused at door", "Cancelled by retailer", "Attempted - customer absent"]
ITEMS = ["Sectional sofa", "Refrigerator", "Washer/dryer pair", "Dining set", "Mattress set", "Wall oven",
         "Recliner", "Bedroom set", "Chest freezer"]


def build(seed: int) -> dict:
    r = rng(seed)
    customers = people(r, 120)
    stops, shipments, sid, stop_id = [], [], 60000, 900000
    for hub, off, n in HUBS:
        for _ in range(n):
            sid += 1
            wlabel, wstart, wend = r.choice(WINDOWS)
            day = date(2026, 8, r.randint(3, 28))
            first, last = r.choice(customers)
            sh = {"id": f"SHP-{sid}", "hub": hub, "off": off, "day": day, "wlabel": wlabel,
                  "wstart": wstart, "wend": wend, "cust": f"{first} {last}", "item": r.choice(ITEMS),
                  "split": False, "status": "Delivered", "on_time": None, "bucket": ""}
            shipments.append(sh)
    # a slice of shipments never completed at all
    for sh in r.sample(shipments, 34):
        sh["status"] = r.choice(NON_DELIVERED)
    # some big items go out on two trucks
    for sh in r.sample([s for s in shipments if s["status"] == "Delivered"], 26):
        sh["split"] = True

    for sh in shipments:
        on_time = r.random() < (0.60 if sh["split"] else r.choice([0.78, 0.82, 0.86]))
        if sh["status"] != "Delivered":
            sh["mins"] = [sh["wstart"] + r.randint(0, max(sh["wend"] - sh["wstart"], 30))]
            continue
        if sh["split"]:
            first_m = sh["wstart"] + r.randint(0, max((sh["wend"] - sh["wstart"]) // 2, 20))
            if on_time:
                last_m = min(sh["wend"] - r.randint(3, 40), sh["wend"])
            else:                                   # the second truck misses the window
                last_m = sh["wend"] + r.randint(25, 210)
            sh["mins"] = [first_m, max(last_m, first_m + 45)]
        else:
            sh["mins"] = [sh["wstart"] + r.randint(0, max(sh["wend"] - sh["wstart"] - 5, 10))] if on_time \
                else [sh["wend"] + r.randint(8, 240)]
        sh["on_time"] = 1 if sh["mins"][-1] <= sh["wend"] else 0
        if not sh["on_time"]:
            if r.random() < 0.12:
                sh["bucket"], sh["reason"] = "Not recorded", ""
            else:
                b, texts = r.choice(REASONS)
                sh["bucket"], sh["reason"] = b, r.choice(texts)
        else:
            sh["reason"] = ""

    for sh in shipments:
        sh["stops"] = []
        for i, m in enumerate(sh["mins"]):
            stop_id += 1
            local = datetime(sh["day"].year, sh["day"].month, sh["day"].day) + timedelta(minutes=m)
            utc = local - timedelta(hours=sh["off"])
            sh["stops"].append({"stop": f"ST-{stop_id}", "utc": utc, "local": local, "seq": i,
                                "pieces": r.randint(1, 3),
                                "status": sh["status"] if not sh["split"] else "Delivered"})
        stops += [dict(s, sh=sh) for s in sh["stops"]]
    stops.sort(key=lambda s: (s["utc"], s["stop"]))

    delivered = [s for s in shipments if s["status"] == "Delivered"]
    by_hub = {h: [s for s in delivered if s["hub"] == h] for h in HUB_NAMES}
    cnt = {h: len(by_hub[h]) for h in HUB_NAMES}
    ont = {h: sum(s["on_time"] for s in by_hub[h]) for h in HUB_NAMES}
    late = {h: cnt[h] - ont[h] for h in HUB_NAMES}
    rate = {h: round(ont[h] / cnt[h], 4) for h in HUB_NAMES}
    buckets = {b: sum(1 for s in delivered if s["bucket"] == b) for b in BUCKETS}
    tot = {"delivered": sum(cnt.values()), "on_time": sum(ont.values()), "late": sum(late.values())}
    tot["rate"] = round(tot["on_time"] / tot["delivered"], 4)
    return {"shipments": shipments, "stops": stops, "delivered": delivered, "cnt": cnt, "ont": ont,
            "late": late, "rate": rate, "buckets": buckets, "tot": tot}


def acceptable(d: dict) -> bool:
    cnt, ont, late, buckets, tot = d["cnt"], d["ont"], d["late"], d["buckets"], d["tot"]
    if buckets["Weather"] < 6 or buckets["Not recorded"] < 3:
        return False
    if len({round(v, 4) for v in d["rate"].values()}) < 3:
        return False
    for h in HUB_NAMES:
        if not 0.7 <= d["rate"][h] <= 0.93:
            return False
        row = [cnt[h], ont[h], late[h]]
        if len(set(row)) < 3:
            return False
        splits = sum(1 for s in d["delivered"] if s["hub"] == h and s["split"])
        nd = sum(1 for s in d["shipments"] if s["hub"] == h and s["status"] != "Delivered")
        if splits < 3 or nd < 6:
            return False
        # the last piece of a split shipment decides: at least two shipments where the first
        # stop was inside the window and the second was not
        flips = sum(1 for s in d["delivered"] if s["hub"] == h and s["split"] and s["on_time"] == 0
                    and s["mins"][0] <= s["wend"])
        if flips < 2:
            return False
    # counting the UTC stamp as local time has to wreck the on-time counts
    naive_ont = sum(1 for s in d["delivered"]
                    if (s["mins"][-1] - s["off"] * 60) <= s["wend"] and (s["mins"][-1] - s["off"] * 60) >= 0)
    if naive_ont > 0.25 * tot["on_time"]:
        return False
    if len({cnt[h] for h in HUB_NAMES}) < 3 or tot["delivered"] in cnt.values():
        return False
    if buckets["Weather"] in (cnt[h] for h in HUB_NAMES):
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(data_rows: list[list]) -> dict:
    n = len(data_rows) + 1
    rows = []
    for i, h in enumerate(HUB_NAMES, start=2):
        rows.append([h, f"=COUNTIF(Data!$B$2:$B${n},$A{i})",
                     f"=SUMIF(Data!$B$2:$B${n},$A{i},Data!$F$2:$F${n})",
                     f"=B{i}-C{i}",
                     f'=IF(B{i}=0,"n/a",ROUND(C{i}/B{i},4))'])
    last = 1 + len(HUB_NAMES)
    rows.append(["Total - all hubs", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})",
                 f'=IF(B{last + 1}=0,"n/a",ROUND(C{last + 1}/B{last + 1},4))'])
    rows.append([])
    rows.append(["Why the late ones were late", "Shipments"])
    start = last + 4
    for k, b in enumerate(BUCKETS):
        rows.append([b, f"=COUNTIF(Data!$G$2:$G${n},$A{start + k})"])
    rows.append(["Total late", f"=SUM(B{start}:B{start + len(BUCKETS) - 1})"])
    rows.append([])
    rows.append(["On time means the last piece of the shipment landed inside the promised window, in hub local "
                 "time. Attempted, refused and cancelled stops are not deliveries."])
    return {
        "Data": {"header": ["shipment_id", "hub", "promised_window_local", "last_piece_local", "window_end_local",
                            "on_time", "late_reason"], "rows": data_rows,
                 "widths": {"A": 14, "C": 22, "D": 20, "E": 20, "G": 16}},
        "Report": {"header": ["Hub", "Shipments delivered", "On time", "Late", "On-time %"], "rows": rows,
                   "widths": {"A": 26, "B": 20, "C": 11, "D": 9, "E": 12}},
    }


def clean_rows(d: dict) -> list[list]:
    out = []
    for s in sorted(d["delivered"], key=lambda x: x["id"]):
        end = datetime(s["day"].year, s["day"].month, s["day"].day) + timedelta(minutes=s["wend"])
        out.append([s["id"], s["hub"], f"{s['day'].isoformat()} {s['wlabel']}",
                    s["stops"][-1]["local"].strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"),
                    s["on_time"], s["bucket"]])
    return out


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    cnt, ont, late, buckets, tot = d["cnt"], d["ont"], d["late"], d["buckets"], d["tot"]

    # ---- workspace ----
    rows = []
    for s in d["stops"]:
        sh = s["sh"]
        rows.append([s["stop"], sh["id"], sh["hub"], sh["cust"], sh["item"], s["pieces"],
                     date_variant(sh["day"], sum(ord(c) for c in s["stop"]) % 2), sh["wlabel"],
                     s["utc"].strftime("%Y-%m-%dT%H:%M:%SZ"), s["status"],
                     sh.get("reason", "") if s["seq"] == len(sh["stops"]) - 1 else ""])
    write_csv(os.path.join(ws, "deliveries_august_2026.csv"),
              ["Stop ID", "Shipment", "Hub", "Customer", "Item", "Pieces", "Promised date", "Promised window",
               "Scanned at", "Stop status", "Late reason"], rows,
              preamble=["Final mile - stop scans", "08/01/2026 - 08/31/2026"], bom=True)
    write_text(os.path.join(ws, "dispatch_notes.txt"),
               "Reading the stop file (please read this before you start)\n"
               "\n"
               "Scanned at is what the handheld sends, and the handheld talks UTC. Our hubs do not: in August\n"
               "Portland runs seven hours behind UTC, Denver six, Austin five. The promised window is what the\n"
               "customer was told, in their own time.\n"
               "\n"
               "Windows: AM is 08:00 to 12:00, PM is 12:00 to 17:00, All day is 08:00 to 17:00, and the rest are\n"
               "written out. A delivery is on time if it is in the window - the day alone is not good enough, that\n"
               "is the whole argument we keep having with the retailers.\n"
               "\n"
               "Big items go out on two trucks. Both stops carry the same shipment number. It is one delivery to\n"
               "the customer and it is only on time if the last piece is in the window.\n"
               "\n"
               "Attempted, refused and cancelled stops are not deliveries. Leave them out of the percentage.\n"
               "\n"
               "The drivers type the late reason however they like. We report five reasons - weather, mechanical,\n"
               "customer, address, route volume - and everything else, including the blanks, is not recorded.\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "hub_performance.csv"), ["hub", "delivered", "on_time", "late", "on_time_rate"],
              [[h, cnt[h], ont[h], late[h], f"{d['rate'][h]:.4f}"] for h in HUB_NAMES] +
              [["ALL", tot["delivered"], tot["on_time"], tot["late"], f"{tot['rate']:.4f}"]])
    write_csv(os.path.join(ref, "late_reasons.csv"), ["bucket", "shipments"],
              [[b, buckets[b]] for b in BUCKETS] + [["ALL LATE", tot["late"]]])
    write_json(os.path.join(ref, "notes.json"), {
        "on_time_rates": {h: d["rate"][h] for h in HUB_NAMES}, "all_hubs_rate": tot["rate"],
        "split_shipments": sum(1 for s in d["delivered"] if s["split"]),
        "non_delivered_stops": sum(1 for s in d["shipments"] if s["status"] != "Delivered"),
        "stop_rows": len(d["stops"])})

    # ---- reference solution ----
    stable_xlsx(os.path.join(sol, "delivery.xlsx"), report_sheets(clean_rows(d)), creator="reference")

    write_task_yaml(HERE, {
        "id": "delivery-performance", "track": "desk", "category": "reports",
        "title": "On-time delivery by hub, and why the late ones were late",
        "ask": ("I need August's on-time delivery by hub and a breakdown of why the late ones were late. Save it as "
                "delivery.xlsx with live formulas. Dispatch's notes explain how the stop file reads.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the promise is a window inside the day (AM, PM, All day, 13:00-15:00), so comparing dates alone marks "
            "hours-late deliveries as on time (checks: Portland on time; on-time rates per hub)",
            "every scan is stamped in UTC while the windows are hub local time (Portland -7, Denver -6, Austin -5 in "
            "August); without the offset almost nothing lands inside its window and some scans roll to the next day "
            "(checks: Portland on time; on-time rates per hub)",
            "big items ship on two trucks under one shipment number, so the stop file has more rows than deliveries; "
            "the shipment counts once and is on time only if the last piece is inside the window "
            "(checks: Denver shipments delivered; total delivered)",
            "attempted, refused and cancelled stops sit in the same file and are not deliveries "
            "(checks: Denver shipments delivered; total delivered)",
            "late reasons are free text ('WEATHER DELAY', 'heavy rain, weather', 'truck breakdown', 'Customer NH') "
            "over the five buckets dispatch reports, and some late stops have no reason at all "
            "(check: weather delays)",
            "the on-time percentage is graded as a fraction or a percentage, but it must be there for every hub "
            "(check: on-time rates per hub)",
        ],
        "checks": [
            {"type": "file_exists", "name": "delivery.xlsx exists", "path": "delivery.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "delivery.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "delivery.xlsx"},
            {"type": "xlsx_value_present", "name": "Portland on time", "path": "delivery.xlsx",
             "expected": ont["Portland"], "rel_tol": 0.001, "near_text": "portland"},
            {"type": "xlsx_value_present", "name": "Denver shipments delivered", "path": "delivery.xlsx",
             "expected": cnt["Denver"], "rel_tol": 0.001, "near_text": "denver"},
            {"type": "xlsx_value_present", "name": "weather delays", "path": "delivery.xlsx",
             "expected": buckets["Weather"], "rel_tol": 0.001, "near_text": "weather"},
            {"type": "xlsx_value_present", "name": "total shipments delivered", "path": "delivery.xlsx",
             "expected": tot["delivered"], "rel_tol": 0.001, "near_text": "total"},
            {"type": "custom", "name": "on-time rates per hub", "module": "check.py"},
        ],
    })
    print(f"seed={seed} shipments={len(d['shipments'])} stop_rows={len(d['stops'])} delivered={tot['delivered']}")
    print("delivered:", cnt, "on time:", ont, "late:", late)
    print("rates:", d["rate"], "all:", tot["rate"])
    print("buckets:", buckets)


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: one row per stop, the UTC stamp read as local time, and on time
    means it arrived on the promised day."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for s in sorted(d["stops"], key=lambda x: x["stop"]):
        sh = s["sh"]
        end = datetime(sh["day"].year, sh["day"].month, sh["day"].day) + timedelta(minutes=sh["wend"])
        rows.append([sh["id"], sh["hub"], f"{sh['day'].isoformat()} {sh['wlabel']}",
                     s["utc"].strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"),
                     1 if s["utc"].date() == sh["day"] else 0, sh.get("reason", "")])
    stable_xlsx(os.path.join(out, "delivery.xlsx"), report_sheets(rows), creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(600):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 600 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
