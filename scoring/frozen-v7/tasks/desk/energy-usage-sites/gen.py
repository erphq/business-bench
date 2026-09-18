#!/usr/bin/env python3
"""energy-usage-sites: monthly kWh per property from cumulative meter reads, with the gap flagged.

    python gen.py [--seed N] [--naive DIR]

Business: a property manager with five commercial buildings. The meter reader walks the sites every
four weeks or so, writes down what the register says, and nobody has ever turned that into monthly usage.

Traps (each caught by a check, see task.yaml):
  * the readings are cumulative register totals, not usage        (checks: every site total)
  * reads land mid-month, so usage has to be split across the boundary (checks: every site total)
  * one site's meter was replaced mid-March and the new one starts at zero (check: Mill Street total)
  * one site has two meters and needs both                       (check: Riverside total)
  * one site has no read after 31 May, so June cannot be computed (checks: Depot Lane total; memo names the gap)
"""
from __future__ import annotations
import argparse
import calendar
import os
import sys
from datetime import date, timedelta

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

MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]
SITES = ["Hawthorn Court", "Mill Street Lofts", "Union Square Retail", "Riverside Business Park", "Depot Lane Storage"]
SWAP_SITE = "Mill Street Lofts"
SWAP_DATE = date(2026, 3, 18)
TWO_METER_SITE = "Riverside Business Park"
GAP_SITE = "Depot Lane Storage"
GAP_MONTH = "2026-06"
SEASON = {1: 1.22, 2: 1.16, 3: 1.02, 4: 0.92, 5: 0.96, 6: 1.12, 7: 1.2, 12: 1.25}
READ_DATES = {
    "Hawthorn Court": [date(2025, 12, 31), date(2026, 1, 29), date(2026, 2, 25), date(2026, 3, 26),
                       date(2026, 4, 23), date(2026, 5, 27), date(2026, 7, 2)],
    "Mill Street Lofts": [date(2025, 12, 31), date(2026, 1, 27), date(2026, 2, 26), date(2026, 3, 26),
                          date(2026, 4, 27), date(2026, 5, 26), date(2026, 7, 3)],
    "Union Square Retail": [date(2025, 12, 31), date(2026, 2, 2), date(2026, 3, 3), date(2026, 3, 31),
                            date(2026, 4, 29), date(2026, 6, 1), date(2026, 7, 6)],
    "Riverside Business Park": [date(2025, 12, 31), date(2026, 1, 28), date(2026, 2, 24), date(2026, 3, 25),
                                date(2026, 4, 28), date(2026, 5, 28), date(2026, 7, 1)],
    "Depot Lane Storage": [date(2025, 12, 31), date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 26),
                           date(2026, 4, 25), date(2026, 5, 31)],
}
METERS = {"Hawthorn Court": ["MTR-8801"], "Mill Street Lofts": ["MTR-8802"], "Union Square Retail": ["MTR-8803"],
          "Riverside Business Park": ["MTR-8804", "MTR-8805"], "Depot Lane Storage": ["MTR-8806"]}
NEW_METER = "MTR-9317"
BASE_DAILY = {"Hawthorn Court": 410.0, "Mill Street Lofts": 305.0, "Union Square Retail": 690.0,
              "Riverside Business Park": (520.0, 240.0), "Depot Lane Storage": 148.0}


def build(seed: int) -> dict:
    r = rng(seed)

    def daily(base, d):
        return base * SEASON.get(d.month, 1.0) * (0.9 + 0.2 * r.random())

    reads = []          # {site, meter, date, reg, kind}
    for site in SITES:
        dates = READ_DATES[site]
        bases = BASE_DAILY[site]
        bases = bases if isinstance(bases, tuple) else (bases,)
        for mi, meter in enumerate(METERS[site]):
            base = bases[mi]
            reg = float(r.randint(120000, 880000))
            cur_meter = meter
            reads.append({"site": site, "meter": cur_meter, "date": dates[0], "reg": round(reg, 0), "kind": "Actual"})
            for k in range(1, len(dates)):
                d0, d1 = dates[k - 1], dates[k]
                day = d0 + timedelta(days=1)
                while day <= d1:
                    if site == SWAP_SITE and day == SWAP_DATE:
                        reads.append({"site": site, "meter": cur_meter, "date": SWAP_DATE, "reg": round(reg, 0),
                                      "kind": "Final read - meter removed"})
                        cur_meter = NEW_METER
                        reg = 0.0
                        reads.append({"site": site, "meter": cur_meter, "date": SWAP_DATE, "reg": 0,
                                      "kind": "Install - new meter"})
                    reg += daily(base, day)
                    day += timedelta(days=1)
                reads.append({"site": site, "meter": cur_meter, "date": d1, "reg": round(reg, 0),
                              "kind": "Estimated" if r.random() < 0.12 else "Actual"})

    # ---- truth: pro-rate each interval over the days it covers ----
    monthly = {(s, m): 0.0 for s in SITES for m in MONTHS}
    covered = {}
    for site in SITES:
        for meter in set(x["meter"] for x in reads if x["site"] == site):
            seq = sorted([x for x in reads if x["site"] == site and x["meter"] == meter], key=lambda x: x["date"])
            days = set()
            for a, b in zip(seq, seq[1:]):
                n = (b["date"] - a["date"]).days
                if n <= 0:
                    continue
                per_day = (b["reg"] - a["reg"]) / n
                for i in range(n):
                    day = a["date"] + timedelta(days=i + 1)
                    days.add(day)
                    key = (site, f"{day.year}-{day.month:02d}")
                    if key in monthly:
                        monthly[key] += per_day
            covered[(site, meter)] = days
    reported = {}
    for site in SITES:
        meters = sorted(set(x["meter"] for x in reads if x["site"] == site))
        # a replaced meter covers the first part of the year and its replacement the rest, so the
        # site is covered where the meters' days taken together are covered
        site_days = set().union(*(covered[(site, mt)] for mt in meters))
        for m in MONTHS:
            y, mm = int(m[:4]), int(m[5:])
            all_days = {date(y, mm, dd) for dd in range(1, calendar.monthrange(y, mm)[1] + 1)}
            reported[(site, m)] = all_days <= site_days
    kwh = {k: round(v, 1) if reported[k] else None for k, v in monthly.items()}
    site_tot = {s: round(sum(kwh[(s, m)] for m in MONTHS if kwh[(s, m)] is not None), 1) for s in SITES}
    month_tot = {m: round(sum(kwh[(s, m)] for s in SITES if kwh[(s, m)] is not None), 1) for m in MONTHS}
    reads.sort(key=lambda x: (x["date"], x["site"], x["meter"]))
    for i, x in enumerate(reads):
        x["id"] = f"RD-{31000 + i}"
    return {"reads": reads, "kwh": kwh, "reported": reported, "site_tot": site_tot, "month_tot": month_tot,
            "grand": round(sum(site_tot.values()), 1)}


def acceptable(d: dict) -> bool:
    kwh, rep, tot = d["kwh"], d["reported"], d["site_tot"]
    if rep[(GAP_SITE, GAP_MONTH)] or not all(rep[(GAP_SITE, m)] for m in MONTHS if m != GAP_MONTH):
        return False
    for s in SITES:
        for m in MONTHS:
            if s != GAP_SITE and not rep[(s, m)]:
                return False
    # every pinned total must stand apart from the others and from any monthly cell
    vals = [tot[s] for s in SITES] + [d["grand"]]
    for s in (TWO_METER_SITE, SWAP_SITE, GAP_SITE):
        v = tot[s]
        if sum(1 for x in vals if abs(x - v) <= 0.02 * v) > 1:
            return False
        row = [kwh[(s, m)] for m in MONTHS if kwh[(s, m)] is not None]
        if any(abs(x - v) <= 0.02 * v for x in row):
            return False
    # an invented June for the gap site has to matter
    may = kwh[(GAP_SITE, "2026-05")]
    if may < 0.08 * tot[GAP_SITE]:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(data_rows: list[list]) -> dict:
    n = len(data_rows) + 1
    rows = []
    for i, s in enumerate(SITES, start=2):
        line = [s]
        for j, m in enumerate(MONTHS):
            c = chr(ord("B") + j)
            line.append(f'=IF(SUMIFS(Data!$D$2:$D${n},Data!$A$2:$A${n},$A{i},Data!$B$2:$B${n},{c}$1)=0,"no reading",'
                        f"ROUND(SUMIFS(Data!$C$2:$C${n},Data!$A$2:$A${n},$A{i},Data!$B$2:$B${n},{c}$1),1))")
        line.append(f"=SUM(B{i}:G{i})")
        rows.append(line)
    last = 1 + len(SITES)
    rows.append(["Total - all sites"] + [f"=SUM({c}2:{c}{last})" for c in "BCDEFGH"])
    rows.append([])
    rows.append([f"{GAP_SITE} has no meter read after 31 May 2026, so June cannot be calculated and is shown as "
                 "no reading rather than estimated. Usage between two reads is spread evenly over the days between "
                 "them."])
    return {
        "Data": {"header": ["site", "month", "kwh", "reported"], "rows": data_rows,
                 "widths": {"A": 26, "B": 12, "C": 12}},
        "Report": {"header": ["Site"] + MONTHS + ["Total kWh"], "rows": rows,
                   "widths": {"A": 26, "H": 13}},
    }


def clean_rows(d: dict) -> list[list]:
    return [[s, m, d["kwh"][(s, m)] if d["kwh"][(s, m)] is not None else 0, 1 if d["reported"][(s, m)] else 0]
            for s in SITES for m in MONTHS]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    kwh, tot = d["kwh"], d["site_tot"]

    # ---- workspace ----
    write_csv(os.path.join(ws, "meter_readings_export.csv"),
              ["Reading ID", "Site", "Meter", "Read date", "Register (kWh)", "Read type", "Read by"],
              [[x["id"], name_noise(rng(sum(ord(c) for c in x["id"])), x["site"]), x["meter"],
                date_variant(x["date"], sum(ord(c) for c in x["id"]) % 3),
                f"{int(x['reg']):,}" if sum(ord(c) for c in x["id"]) % 2 else f"{int(x['reg'])}",
                x["kind"], "M. Tanaka" if sum(ord(c) for c in x["id"]) % 3 else "R. Haddad"]
               for x in d["reads"]],
              preamble=["Meter reading export", "Registers as read on site - cumulative totals"], bom=True, crlf=True)
    stable_xlsx(os.path.join(ws, "site_meter_register.xlsx"), {"Meters": {
        "merged_title": "Meters on the portfolio",
        "header": ["Site", "Meter", "Serves", "Status"],
        "rows": [["Hawthorn Court", "MTR-8801", "Whole building", "Active"],
                 ["Mill Street Lofts", "MTR-8802", "Whole building", "Removed 18 Mar 2026"],
                 ["Mill Street Lofts", NEW_METER, "Whole building", "Active from 18 Mar 2026"],
                 ["Union Square Retail", "MTR-8803", "Whole building", "Active"],
                 ["Riverside Business Park", "MTR-8804", "Building A", "Active"],
                 ["Riverside Business Park", "MTR-8805", "Building B", "Active"],
                 ["Depot Lane Storage", "MTR-8806", "Whole site", "Active"]],
        "widths": {"A": 26, "B": 12, "C": 18, "D": 24}}}, creator="Facilities")
    write_email_thread(os.path.join(ws, "email_from_facilities.txt"), [
        {"from": "Omar Haddad <omar@redwoodpm.com>", "to": "you", "date": "Mon, 6 Jul 2026 08:30",
         "subject": "electricity by month, first half",
         "body": ("The owners want electricity use by building, month by month, for January to June. All I have is "
                  "what the meter reader writes down, which is the number on the register - the running total on the "
                  "meter, not what the building used.\n\n"
                  "He never gets round on the first of the month, so the reads land wherever they land. Spread the "
                  "usage between two reads evenly across the days between them: count from the day after the earlier "
                  "read up to and including the day of the later read. It is what the utility does and the owners "
                  "are used to seeing it that way.")},
        {"from": "Omar Haddad <omar@redwoodpm.com>", "to": "you", "date": "Mon, 6 Jul 2026 08:52",
         "subject": "RE: electricity by month, first half",
         "body": ("Two things about the meters. Mill Street had its meter changed out in March - the old one was read "
                  "and pulled the same day and the new one started from zero, so do not let the numbers frighten you. "
                  "And Riverside is two meters, one per building; the owners see Riverside as one property.\n\n"
                  "If there is a month you cannot work out, leave it blank and say so in the memo. I would rather "
                  "have a hole in the table than a number somebody invented - we bill tenants off this.")}])

    # ---- reference ----
    write_csv(os.path.join(ref, "kwh_by_site_month.csv"), ["site", "month", "kwh", "note"],
              [[s, m, f"{kwh[(s, m)]:.1f}" if kwh[(s, m)] is not None else "",
                "" if kwh[(s, m)] is not None else "no read covering this month"] for s in SITES for m in MONTHS])
    write_csv(os.path.join(ref, "site_totals.csv"), ["site", "kwh"],
              [[s, f"{tot[s]:.1f}"] for s in SITES] + [["ALL", f"{d['grand']:.1f}"]])
    write_json(os.path.join(ref, "notes.json"), {
        "gap": {"site": GAP_SITE, "month": GAP_MONTH}, "swap": {"site": SWAP_SITE, "date": SWAP_DATE.isoformat(),
                                                                "new_meter": NEW_METER},
        "two_meter_site": TWO_METER_SITE, "month_totals": d["month_tot"], "grand_total": d["grand"],
        "reading_rows": len(d["reads"])})

    # ---- reference solution ----
    stable_xlsx(os.path.join(sol, "energy.xlsx"), report_sheets(clean_rows(d)), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    write_task_yaml(HERE, {
        "id": "energy-usage-sites", "track": "desk", "category": "reports",
        "title": "Monthly electricity by building from meter reads",
        "ask": ("The owners want electricity by building for January to June, month by month. Build it as energy.xlsx "
                "with live formulas and put anything I should know in memo.md. Omar's email explains how the meter "
                "reads work.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the Register column is the meter's running total, not usage; summing it gives a number in the millions "
            "and even differencing it needs the reads in meter order (checks: Riverside total; Mill Street total; "
            "total across the portfolio)",
            "reads land mid-month, so each interval has to be split across the month boundary by days; assigning a "
            "whole interval to the month of its later read moves every figure and loses the last days of June "
            "(checks: Hawthorn Court total; total across the portfolio)",
            f"the {SWAP_SITE} meter was read, removed and replaced on {SWAP_DATE.isoformat()} and the new meter starts "
            "at zero, so a plain difference over that site's reads produces a large negative March "
            "(check: Mill Street total)",
            f"{TWO_METER_SITE} is two meters, one per building, read on the same days; using one of them halves the "
            "site (check: Riverside total)",
            f"{GAP_SITE} has no read after 31 May, so June cannot be computed for it - the report must leave it out "
            "rather than repeat May, and its half-year total covers five months "
            f"(checks: Depot Lane total; memo names the missing June read)",
            "registers are written '482,119' and '482119', dates come in three formats, some reads are marked "
            "Estimated (they still count), and the export carries a preamble, a BOM and CRLF endings "
            "(check: total across the portfolio)",
        ],
        "checks": [
            {"type": "file_exists", "name": "energy.xlsx exists", "path": "energy.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "energy.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "energy.xlsx"},
            {"type": "xlsx_value_present", "name": "Riverside total (both meters)", "path": "energy.xlsx",
             "expected": tot[TWO_METER_SITE], "rel_tol": 0.001, "rounding": "kWh prorated by day between meter reads", "near_text": "riverside"},
            {"type": "xlsx_value_present", "name": "Mill Street total (meter replaced in March)", "path": "energy.xlsx",
             "expected": tot[SWAP_SITE], "rel_tol": 0.001, "rounding": "kWh prorated by day between meter reads", "near_text": "mill street"},
            {"type": "xlsx_value_present", "name": "Depot Lane total (five months, June not invented)", "path": "energy.xlsx",
             "expected": tot[GAP_SITE], "rel_tol": 0.001, "rounding": "kWh prorated by day between meter reads", "near_text": "depot lane"},
            {"type": "xlsx_value_present", "name": "Hawthorn Court total", "path": "energy.xlsx",
             "expected": tot["Hawthorn Court"], "rel_tol": 0.001, "rounding": "kWh prorated by day between meter reads", "near_text": "hawthorn"},
            {"type": "xlsx_value_present", "name": "total across the portfolio", "path": "energy.xlsx",
             "expected": d["grand"], "rel_tol": 0.001, "rounding": "kWh prorated by day between meter reads", "near_text": "total"},
            {"type": "text_numbers_present", "name": "memo carries the portfolio and Depot Lane totals", "path": "memo.md",
             "numbers": [d["grand"], tot[GAP_SITE]], "rel_tol": 0.01},
            {"type": "text_sentence_matches", "name": "memo names the missing June read", "path": "memo.md",
             "all": [r"\bdepot lane\b", r"(\bjune\b|\bjun\b|\b2026-06\b|\b06/2026\b)",
                     r"(\bno\b[^.;]{0,40}\b(read|reading|readings|data)\b|\bmissing\b|\bgap\b|\bnot been read\b|"
                     r"\bhas not been read\b|\bnever read\b|\bcannot be (calculated|computed|worked out)\b|\bblank\b)"],
             "none": [r"(rather than (a |an )?(missing|gap)|\bnot (a |an )?(missing|gap)\b)"]},
        ],
    })
    print(f"seed={seed} reads={len(d['reads'])}")
    print("site totals:", tot, "grand:", d["grand"])
    print("gap row:", {m: kwh[(GAP_SITE, m)] for m in MONTHS})
    print("swap row:", {m: kwh[(SWAP_SITE, m)] for m in MONTHS})


def memo_text(d: dict) -> str:
    kwh, tot = d["kwh"], d["site_tot"]
    busiest = max(SITES, key=lambda s: tot[s])
    return f"""# Electricity by building, January to June 2026

The portfolio used {d['grand']:,.1f} kWh over the six months. {busiest} is the heaviest building at
{tot[busiest]:,.1f} kWh; {GAP_SITE} is the lightest at {tot[GAP_SITE]:,.1f} kWh.

**Depot Lane Storage has no meter read after 31 May, so June is missing for that site** - the June cell is left
as "no reading" rather than estimated, and the {tot[GAP_SITE]:,.1f} kWh total covers January to May only. Please
get the meter read before the tenant is billed for the quarter.

Two things about how the table is built:

1. The export holds register totals, not usage, so each month is the difference between reads, split across the
   month boundary by days.
2. The Mill Street meter was swapped on {SWAP_DATE.strftime('%-d %B')} and the replacement started from zero; March
   for that building is the old meter up to the swap plus the new one afterwards. Riverside is both building
   meters added together.
"""


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: difference the register column in date order per site (which breaks at the
    meter swap and mixes the two Riverside meters), and put each interval in the month of its later read."""
    os.makedirs(out, exist_ok=True)
    agg = {(s, m): 0.0 for s in SITES for m in MONTHS}
    for s in SITES:
        seq = sorted([x for x in d["reads"] if x["site"] == s], key=lambda x: (x["date"], x["meter"]))
        for a, b in zip(seq, seq[1:]):
            key = (s, f"{b['date'].year}-{b['date'].month:02d}")
            if key in agg:
                agg[key] += b["reg"] - a["reg"]
    rows = [[s, m, round(agg[(s, m)], 1), 1] for s in SITES for m in MONTHS]
    stable_xlsx(os.path.join(out, "energy.xlsx"), report_sheets(rows), creator="naive")
    write_text(os.path.join(out, "memo.md"),
               "# Electricity by building\n\nUsage is reported for all five buildings for January through June. "
               "The readings were differenced month by month and every site has a full six months of data.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
