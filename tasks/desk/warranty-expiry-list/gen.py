#!/usr/bin/env python3
"""warranty-expiry-list: equipment whose warranty runs out in the next 90 days, from a hand-kept register.

    python gen.py [--seed N] [--naive DIR]

Business: a two-location animal hospital. The practice manager's assistant keeps the equipment register in a
workbook: install date, warranty term as typed from the paperwork, and a notes column where extended
warranties get written down. The manager wants a call list before coverage lapses.

Traps (each caught by a check, see task.yaml):
  * warranty terms are typed as "36 mo", "2 yrs", "1 year", "90 days"             (checks: expiring assets; days left)
  * extended warranties live in the notes: "+24 months" or "extended to 12/15/2026" (checks: expiring assets; days left)
  * split terms "1 yr labor / 3 yr parts": the manager's email says parts decides (check: expiring assets)
  * one install date is in the future; the email says those are last year's typos  (checks: expiring assets; days left)
  * the as-of date is in the ask; already-lapsed items stay off the list          (checks: expiring assets; days left)
  * a Disposed tab lists retired equipment in the same layout                     (check: expiring assets)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

AS_OF = date(2026, 10, 5)
HORIZON = AS_OF + timedelta(days=90)
EQUIPMENT = [("Digital X-ray generator", "Sound Imaging"), ("Autoclave 23L", "Midmark"), ("Anesthesia machine", "Vetland"),
             ("Dental unit with scaler", "iM3"), ("Centrifuge", "StatSpin"), ("Chemistry analyzer", "IDEXX"),
             ("Hematology analyzer", "IDEXX"), ("Surgical LED light", "Burton"), ("Patient warming system", "Bair Hugger"),
             ("Ultrasound", "Butterfly"), ("Multiparameter monitor", "Mindray"), ("Oxygen concentrator", "DeVilbiss"),
             ("Kennel HVAC condenser", "Carrier"), ("Commercial washer", "Speed Queen"), ("Commercial dryer", "Speed Queen"),
             ("Exam table, hydraulic", "Shor-Line"), ("Ice machine", "Hoshizaki"), ("Refrigerator, vaccine", "Helmer"),
             ("Infusion pump", "Heska"), ("Laser therapy unit", "Companion"), ("Microscope", "Olympus"), ("Endoscope tower", "Karl Storz"),
             ("Cage bank dryer", "Shor-Line"), ("Server and backup NAS", "Synology"), ("Reception PCs (4)", "Dell"),
             ("Phone system", "Weave"), ("Generator, standby", "Generac"), ("Scale, walk-on", "Shor-Line"),
             ("Blood pressure monitor", "SunTech"), ("ECG unit", "Cardell"), ("Tonometer", "TonoVet"), ("Water heater", "Rheem")]
LOCATIONS = ["Main St", "Eastside"]
EASTSIDE_OPEN = date(2025, 11, 12)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, d.day)


def term_text(months: int | None, days: int | None, style: int) -> str:
    if days:
        return f"{days} days"
    if months % 12 == 0 and style % 3 != 0:
        y = months // 12
        return [f"{y} yr" if y == 1 else f"{y} yrs", f"{y} year" if y == 1 else f"{y} years"][style % 2]
    return [f"{months} months", f"{months} mo", f"{months} mos."][style % 3]


def build(seed: int) -> dict:
    r = rng(seed)
    eq = list(EQUIPMENT)
    r.shuffle(eq)
    assets = []
    tags = list(range(1107, 1107 + 17 * 40, 17))
    r.shuffle(tags)
    tag = iter(tags)

    def asset(kind, months=None, days=None, end_target=None, **kw):
        name, vendor = eq[len(assets)]
        a = {"tag": f"LH-{next(tag):04d}", "name": name, "vendor": vendor, "kind": kind, "months": months, "days": days,
             "loc": r.choice(LOCATIONS), "note": "", "style": r.randrange(6), "k": r.random()}
        a.update(kw)
        if end_target is not None:      # choose the install date so the base term ends on end_target
            if days:
                a["install"] = end_target - timedelta(days=days)
            else:
                t = add_months(end_target.replace(day=min(end_target.day, 28)), -months)
                a["install"] = t
        assets.append(a)
        return a

    def in_window():
        return AS_OF + timedelta(days=r.randint(4, 86))

    def before(lo, hi):
        return AS_OF - timedelta(days=r.randint(lo, hi))

    def after(lo, hi):
        return HORIZON + timedelta(days=r.randint(lo, hi))

    # plainly expiring, terms written every which way
    for months in r.sample([12, 24, 36, 18, 60], 4):
        asset("plain_in", months=months, end_target=in_window())
    asset("days_in", days=90, end_target=in_window())
    # extended warranty pushes a lapsed base term into the window
    a = asset("ext_into", months=12, end_target=None)
    ext_end = in_window()
    a["install"] = add_months(ext_end.replace(day=min(ext_end.day, 28)), -24)
    a["ext_months"] = 12
    a["note"] = f"Extended warranty +12 months purchased {date_variant(add_months(a['install'], 11), 1)}"
    # extended warranty pushes an in-window base term out of the window
    a = asset("ext_out", months=24, end_target=in_window())
    a["ext_months"] = 24
    a["note"] = f"ext. warranty +24 mo (PO {r.randint(4100, 4999)})"
    # explicit extended end date inside the window
    a = asset("ext_date", months=36, end_target=before(100, 300))
    a["ext_end"] = in_window()
    a["note"] = f"Service plan - coverage extended to {date_variant(a['ext_end'], 1)}"
    # split terms: parts decides
    a = asset("split_parts_in", months=36, end_target=in_window())
    a["labor_months"] = 12
    a = asset("split_labor_in", months=36, end_target=None)
    labor_end = in_window()
    a["install"] = add_months(labor_end.replace(day=min(labor_end.day, 28)), -12)
    a["labor_months"] = 12
    # future install date: typed with next year's year
    a = asset("future", months=12, end_target=None)
    a["loc"] = "Eastside"
    a["install"] = EASTSIDE_OPEN
    a["typed_install"] = EASTSIDE_OPEN.replace(year=EASTSIDE_OPEN.year + 1)
    a["note"] = "installed for the Eastside opening"
    # just lapsed, and just beyond the window
    for _ in range(2):
        asset("lapsed", months=r.choice([12, 24, 36]), end_target=before(5, 40))
    for _ in range(2):
        asset("beyond", months=r.choice([12, 24, 36]), end_target=after(5, 45))
    while len(assets) < 28:
        months = r.choice([12, 24, 36, 60])
        end = r.choice([before(120, 900), after(60, 700)])
        asset("other", months=months, end_target=end)
    disposed = []
    for i in range(3):
        name, vendor = eq[28 + i]
        months = r.choice([12, 24])
        end = in_window() if i < 2 else before(200, 400)
        disposed.append({"tag": f"LH-{next(tag):04d}", "name": name, "vendor": vendor, "months": months,
                         "install": add_months(end.replace(day=min(end.day, 28)), -months), "loc": r.choice(LOCATIONS),
                         "disposed": AS_OF - timedelta(days=r.randint(30, 200)), "style": r.randrange(6)})
    # ---- truth ----
    for a in assets:
        if a["days"]:
            end = a["install"] + timedelta(days=a["days"])
        else:
            end = add_months(a["install"], a["months"])
        if a.get("ext_months"):
            end = add_months(end, a["ext_months"])
        if a.get("ext_end"):
            end = a["ext_end"]
        a["end"] = end
        a["expiring"] = AS_OF <= end <= HORIZON
    return {"assets": assets, "disposed": disposed}


def naive_end(a: dict) -> date:
    """install date as typed + the first number in the term, notes ignored."""
    install = a.get("typed_install", a["install"])
    if a["days"]:
        return install + timedelta(days=a["days"])
    if a.get("labor_months"):
        return add_months(install, a["labor_months"])
    return add_months(install, a["months"])


def acceptable(d: dict) -> bool:
    for a in d["assets"]:
        if a["kind"] != "future" and a["install"] > AS_OF - timedelta(days=7):
            return False
    for a in d["disposed"]:
        if a["install"] > AS_OF - timedelta(days=7):
            return False
    for a in d["assets"]:
        for edge in (AS_OF, HORIZON):
            if abs((a["end"] - edge).days) <= 2:
                return False
    exp = {a["tag"] for a in d["assets"] if a["expiring"]}
    naive = {a["tag"] for a in d["assets"] if AS_OF <= naive_end(a) <= HORIZON}
    kinds = {a["kind"]: a for a in d["assets"]}
    return (kinds["ext_into"]["tag"] in exp and kinds["ext_out"]["tag"] not in exp and kinds["future"]["tag"] in exp
            and kinds["split_parts_in"]["tag"] in exp and kinds["split_labor_in"]["tag"] not in exp
            and kinds["ext_date"]["tag"] in exp and len(naive ^ exp) >= 5 and 8 <= len(exp) <= 12)


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["asset_tag", "equipment", "location", "warranty_end", "days_left"]
    if naive_dir:
        rows = []
        for a in d["assets"] + [dict(x, days=None, kind="disposed") for x in d["disposed"]]:
            e = naive_end(a)
            if AS_OF <= e <= HORIZON:
                rows.append([a["tag"], a["name"], a["loc"], e.isoformat(), (e - AS_OF).days])
        write_csv(os.path.join(naive_dir, "expiring_warranties.csv"), header, rows)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 21)

    def install_cell(dt: date, style: int):
        return [dt, date_variant(dt, 1), dt, date_variant(dt, 0), date_variant(dt, 3), dt][style % 6]

    reg = []
    for a in sorted(d["assets"], key=lambda x: x["k"]):
        shown = a.get("typed_install", a["install"])
        if a.get("labor_months"):
            term = f"{a['labor_months'] // 12} yr labor / {a['months'] // 12} yr parts"
        else:
            term = term_text(a["months"], a["days"], a["style"])
        reg.append([a["tag"], a["name"], a["vendor"], a["loc"], install_cell(shown, a["style"]), term, a["note"]])
    reg.sort(key=lambda row: (row[3], row[0]))
    disp = [[x["tag"], x["name"], x["vendor"], x["loc"], install_cell(x["install"], x["style"]), term_text(x["months"], None, x["style"]),
             x["disposed"]] for x in d["disposed"]]
    write_xlsx(os.path.join(ws, "equipment_register.xlsx"), {
        "Equipment": {"merged_title": "Larch Hollow Animal Hospital - equipment register",
                      "header": ["Asset Tag", "Equipment", "Vendor", "Location", "Install Date", "Warranty", "Notes"], "rows": reg,
                      "widths": {"B": 28, "C": 16, "E": 16, "F": 24, "G": 52}},
        "Disposed": {"header": ["Asset Tag", "Equipment", "Vendor", "Location", "Install Date", "Warranty", "Disposed On"], "rows": disp,
                     "widths": {"B": 28, "E": 16, "G": 14}},
    }, creator="Front office")
    write_csv(os.path.join(ws, "warranty_calls_2025.csv"), ["Asset Tag", "Equipment", "Expires", "Called vendor?"],
              [[a["tag"], a["name"], date_variant(add_months(a["install"], 12), 1), r.choice(["yes", "no", "left voicemail"])]
               for a in r.sample(d["assets"], 6)])
    write_email_thread(os.path.join(ws, "email_from_practice_manager.txt"), [
        {"from": "Denise Arkwright <denise@larchhollowvet.com>", "to": "you", "date": "Fri, 2 Oct 2026 17:12",
         "subject": "warranty list",
         "body": ("I want to call vendors before coverage runs out, not after. Can you go through the equipment register and "
                  "pull everything whose warranty ends in the next 90 days? Anything that's already lapsed is a lost cause, "
                  "leave it off.\n\n"
                  "A few things to know about Kayla's register. Warranty terms are typed the way they appear on the paperwork. "
                  "Where the labor and parts coverage are different, parts is what matters to us. When we bought an extended "
                  "warranty or a service plan she wrote it in the notes, and that's the real end date.\n\n"
                  "She also fat-fingered at least one install date into the future - nothing on that tab hasn't been installed "
                  "yet, so any date after today is the same day a year earlier.\n\n"
                  "Last year's call list is in the folder too; ignore it. Columns: asset tag, equipment, location, warranty end "
                  "date, days left.\n\nDenise")}])

    exp = sorted([a for a in d["assets"] if a["expiring"]], key=lambda a: a["end"])
    rows = [[a["tag"], a["name"], a["loc"], a["end"].isoformat(), (a["end"] - AS_OF).days] for a in exp]
    write_csv(os.path.join(ref, "expiring_warranties.csv"), header, rows)
    write_csv(os.path.join(sol, "expiring_warranties.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {"as_of": AS_OF, "horizon": HORIZON,
                                                  "kinds": {a["tag"]: a["kind"] for a in d["assets"]},
                                                  "ends": {a["tag"]: a["end"] for a in d["assets"]}})
    write_task_yaml(HERE, {
        "id": "warranty-expiry-list", "track": "desk", "category": "spreadsheet",
        "title": "Equipment warranties running out in the next 90 days",
        "ask": ("Treat today as October 5, 2026. Denise wants a list of the equipment whose warranty runs out in the next 90 days "
                "so she can call the vendors; the register and her email are in the folder. Save it as expiring_warranties.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "warranty terms are typed as '36 mo', '18 mos.', '2 yrs', '1 year' and '90 days'; reading every number as months "
            "or years moves assets in and out of the window (checks: expiring assets; days left)",
            "extended warranties exist only in the notes, as '+12 months', '+24 mo' or 'coverage extended to <date>': one lapsed "
            "base term is back in the window, one in-window base term is pushed out, and one service plan sets its own end date "
            "(checks: expiring assets; days left)",
            "two assets carry '1 yr labor / 3 yr parts'; the email says parts decides, so the first number in the cell is the "
            "wrong term for both (check: expiring assets)",
            "one Eastside install date is typed a year in the future; per the email it is the same day a year earlier, which "
            "puts its twelve-month warranty in the window (checks: expiring assets; days left)",
            "the ask fixes today as October 5, 2026, so the machine clock gives the wrong window; two warranties lapsed a few "
            "weeks earlier and stay off, two end just after the 90 days (checks: expiring assets; days left)",
            "install dates are a mix of real date cells and three text formats under a merged title, and a Disposed tab lists "
            "retired equipment whose original terms would land in the window (check: expiring assets)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "expiring_warranties.csv", "columns": ["asset_tag", "days_left"]},
            {"type": "csv_set_equal", "name": "expiring assets", "path": "expiring_warranties.csv", "column": "asset_tag",
             "ref": "expiring_warranties.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "one row per asset", "path": "expiring_warranties.csv", "equals_ref": "expiring_warranties.csv"},
            {"type": "csv_values_match", "name": "days left", "path": "expiring_warranties.csv", "ref": "expiring_warranties.csv",
             "key": "asset_tag", "columns": ["days_left"], "numeric": True, "tolerance": 1.0},
        ],
    })
    print(f"seed={seed} expiring={len(exp)}")
    for a in d["assets"]:
        print(f"  {a['tag']} {a['kind']:15} install={a['install']} end={a['end']} exp={a['expiring']} naive={naive_end(a)}")


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
