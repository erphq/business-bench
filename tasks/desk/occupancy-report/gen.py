#!/usr/bin/env python3
"""occupancy-report: a channel-manager reservations export plus a blocked-dates calendar to occupancy per cabin per month.

    python gen.py [--seed N] [--naive DIR]

Business: a family company managing five ski-area cabins for their owners. The owners' quarterly letter needs
Q1 occupancy per cabin per month, counted the way Ruth's note defines it.

Traps (each caught by a check, see task.yaml):
  * stays span month ends (New Year, end of March into April); nights belong to the night slept   (checks: Aspen Q1 nights; rates)
  * the calendar's blocks use DTEND as the morning after (exclusive), one block spans Jan/Feb, one is STATUS:CANCELLED
                                                                                                   (checks: Fox Den available nights; rates)
  * cancelled reservations are in the export, some with a cancellation-fee payout                  (checks: Bear Creek Q1 nights; total)
  * owner stays are in the reservations export as $0 Owner bookings: unavailable, not occupied     (checks: Bear Creek Q1 nights; total)
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

PROPS = ["Aspen Hollow", "Bear Creek Lodge", "Cedar Loft", "Fox Den Cabin", "Summit A-Frame"]
LISTING = {"Aspen Hollow": "Aspen Hollow - 2BR w/ hot tub", "Bear Creek Lodge": "Bear Creek Lodge (6BR, sleeps 14)",
           "Cedar Loft": "Cedar Loft | studio near lifts", "Fox Den Cabin": "Fox Den Cabin - dog friendly", "Summit A-Frame": "Summit A-Frame 3BR"}
RATE = {"Aspen Hollow": 285, "Bear Creek Lodge": 720, "Cedar Loft": 160, "Fox Den Cabin": 240, "Summit A-Frame": 390}
MONTHS = ["2026-01", "2026-02", "2026-03"]
Q_START, Q_END = date(2026, 1, 1), date(2026, 3, 31)
WIN_START, WIN_END = date(2025, 12, 12), date(2026, 4, 19)


def nights_of(ci: date, co: date):
    d = ci
    while d < co:
        yield d
        d += timedelta(days=1)


def mkey(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def build(seed: int) -> dict:
    r = rng(seed)
    blocks, owner, bookings, cancels = [], [], [], []
    for p in PROPS:
        taken = set()
        # blocks from the owner calendar
        plan = []
        if p == "Fox Den Cabin":
            s = date(2026, 1, r.randint(27, 30)); plan.append((s, date(2026, 2, r.randint(2, 4)), "owner hold"))
            s = date(2026, 2, r.randint(14, 18)); plan.append((s, s + timedelta(days=r.randint(3, 5)), "maintenance - wood stove inspection"))
        elif p == "Cedar Loft":
            s = date(2026, 3, r.randint(9, 13)); plan.append((s, s + timedelta(days=r.randint(4, 6)), "maintenance - repaint"))
        elif p == "Summit A-Frame":
            s = date(2026, 1, r.randint(12, 16)); plan.append((s, s + timedelta(days=r.randint(2, 4)), "owner hold"))
            s = date(2026, 4, r.randint(6, 10)); plan.append((s, s + timedelta(days=5), "maintenance - spring deck work"))
        elif p == "Aspen Hollow":
            s = date(2026, 2, r.randint(20, 23)); plan.append((s, s + timedelta(days=2), "maintenance - hot tub service"))
        for s, e, what in plan:
            blocks.append({"prop": p, "start": s, "end": e, "what": what, "status": "CONFIRMED"})
            taken.update(nights_of(s, e))
        # owner stays booked through the channel manager
        if p in ("Bear Creek Lodge", "Aspen Hollow"):
            s = date(2026, r.choice([1, 2, 3]), r.randint(3, 20))
            e = s + timedelta(days=r.randint(3, 6))
            if not taken & set(nights_of(s, e)):
                owner.append({"prop": p, "ci": s, "co": e})
                taken.update(nights_of(s, e))
        # guest stays: walk the season
        d = WIN_START + timedelta(days=r.randint(0, 3))
        if p == "Aspen Hollow":
            ci = date(2025, 12, r.randint(27, 30)); co = date(2026, 1, r.randint(3, 5))
            bookings.append({"prop": p, "ci": ci, "co": co}); taken.update(nights_of(ci, co))
            ci = date(2026, 3, r.randint(26, 28)); co = date(2026, 4, r.randint(2, 4))
            if not taken & set(nights_of(ci, co)):
                bookings.append({"prop": p, "ci": ci, "co": co}); taken.update(nights_of(ci, co))
        while d < WIN_END:
            length = r.choice([2, 2, 3, 3, 4, 5, 7])
            gap = r.choice([0, 0, 1, 1, 2, 3, 4, 6]) + (2 if p == "Bear Creek Lodge" else 0)
            ci = d + timedelta(days=gap); co = ci + timedelta(days=length)
            if co > WIN_END:
                break
            if taken & set(nights_of(ci, co)):
                d = d + timedelta(days=1)
                continue
            bookings.append({"prop": p, "ci": ci, "co": co}); taken.update(nights_of(ci, co))
            d = co
        # a maintenance block that was cancelled and then booked over by guests
        if p == "Cedar Loft":
            b = r.choice([x for x in bookings if x["prop"] == p and date(2026, 2, 3) <= x["ci"] <= date(2026, 2, 20)])
            blocks.append({"prop": p, "start": b["ci"], "end": b["co"] + timedelta(days=1), "what": "maintenance - window replacement (moved to May)",
                           "status": "CANCELLED"})
    # cancellations: dates later rebooked by someone else, or left empty
    for p in PROPS:
        mine = [b for b in bookings if b["prop"] == p and Q_START <= b["ci"] <= date(2026, 3, 20)]
        n = 3 if p == "Bear Creek Lodge" else r.randint(1, 2)
        for b in r.sample(mine, n):
            shift = r.choice([-1, 0, 1])
            cancels.append({"prop": p, "ci": b["ci"] + timedelta(days=shift), "co": b["co"] + timedelta(days=shift + r.choice([0, 1]))})
    # guest details and ids
    rows = []
    for kind, lst in (("guest", bookings), ("owner", owner), ("cancel", cancels)):
        for b in lst:
            f, l = person(r)
            n = (b["co"] - b["ci"]).days
            channel = "Owner" if kind == "owner" else r.choice(["Airbnb", "Airbnb", "Vrbo", "Direct"])
            payout = 0.0 if kind == "owner" else round(n * RATE[b["prop"]] * r.uniform(0.85, 1.15), 2)
            status = "Confirmed" if kind == "owner" else ("Cancelled" if kind == "cancel" else r.choice(["Confirmed", "Checked out"]))
            if kind == "cancel":
                payout = round(payout * r.choice([0.0, 0.0, 0.5]), 2)
            if kind == "guest" and b["ci"] > date(2026, 4, 2):
                status = "Confirmed"
            rows.append({**b, "kind": kind, "guest": f"{f} {l}" if kind != "owner" else "Owner stay", "nights": n, "channel": channel,
                         "payout": payout, "status": status})
    rows.sort(key=lambda x: (x["ci"], x["prop"]))
    for i, x in enumerate(rows):
        x["code"] = f"HM{code(r, 6, 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789')}"
    return {"rows": rows, "blocks": blocks}


def compute(d: dict, booked_kinds=("guest",), blocked_owner=True, dtend_inclusive=False, use_blocks=True, cancelled_blocks=False,
            by_checkin=False) -> dict:
    nights = {(p, m): 0 for p in PROPS for m in MONTHS}
    blocked = {(p, m): 0 for p in PROPS for m in MONTHS}
    for x in d["rows"]:
        if x["kind"] in booked_kinds:
            if by_checkin:
                if mkey(x["ci"]) in MONTHS:
                    nights[(x["prop"], mkey(x["ci"]))] += x["nights"]
            else:
                for n in nights_of(x["ci"], x["co"]):
                    if mkey(n) in MONTHS:
                        nights[(x["prop"], mkey(n))] += 1
        elif x["kind"] == "owner" and blocked_owner:
            for n in nights_of(x["ci"], x["co"]):
                if mkey(n) in MONTHS:
                    blocked[(x["prop"], mkey(n))] += 1
    if use_blocks:
        for b in d["blocks"]:
            if b["status"] == "CANCELLED" and not cancelled_blocks:
                continue
            end = b["end"] + timedelta(days=1) if dtend_inclusive else b["end"]
            for n in nights_of(b["start"], end):
                if mkey(n) in MONTHS:
                    blocked[(b["prop"], mkey(n))] += 1
    out = {"nights": nights, "avail": {}, "occ": {}}
    for p in PROPS:
        for m in MONTHS:
            dim = calendar.monthrange(int(m[:4]), int(m[5:]))[1]
            a = dim - blocked[(p, m)]
            out["avail"][(p, m)] = a
            out["occ"][(p, m)] = round(nights[(p, m)] / a, 4) if a else 0.0
        out["nights"][(p, "Q1")] = sum(nights[(p, m)] for m in MONTHS)
        out["avail"][(p, "Q1")] = sum(out["avail"][(p, m)] for m in MONTHS)
        out["occ"][(p, "Q1")] = round(out["nights"][(p, "Q1")] / out["avail"][(p, "Q1")], 4)
    out["total_nights"] = sum(out["nights"][(p, "Q1")] for p in PROPS)
    out["total_avail"] = sum(out["avail"][(p, "Q1")] for p in PROPS)
    out["total_occ"] = round(out["total_nights"] / out["total_avail"], 4)
    return out


def variants(d):
    return {"cancel": compute(d, booked_kinds=("guest", "cancel")), "owner": compute(d, booked_kinds=("guest", "owner"), blocked_owner=False),
            "inclusive": compute(d, dtend_inclusive=True), "no_blocks": compute(d, use_blocks=False),
            "cancelled_block": compute(d, cancelled_blocks=True), "checkin": compute(d, by_checkin=True)}


def acceptable(d: dict) -> bool:
    t = compute(d)
    v = variants(d)
    # blocks never collide with guest nights (a confirmed block means nobody could book)
    for b in d["blocks"]:
        if b["status"] != "CONFIRMED":
            continue
        nb = set(nights_of(b["start"], b["end"]))
        if any(x["kind"] in ("guest", "owner") and x["prop"] == b["prop"] and nb & set(nights_of(x["ci"], x["co"])) for x in d["rows"]):
            return False
    A, B, F = "Aspen Hollow", "Bear Creek Lodge", "Fox Den Cabin"
    if t["nights"][(A, "Q1")] == v["checkin"]["nights"][(A, "Q1")]:
        return False
    if abs(t["occ"][(A, "2026-01")] - v["checkin"]["occ"][(A, "2026-01")]) < 0.01:
        return False
    for k in ("cancel", "owner"):
        if t["nights"][(B, "Q1")] == v[k]["nights"][(B, "Q1")] or t["total_nights"] == v[k]["total_nights"]:
            return False
    for k in ("inclusive", "no_blocks"):
        if abs(t["occ"][(F, "2026-02")] - v[k]["occ"][(F, "2026-02")]) < 0.01 or t["avail"][(F, "Q1")] == v[k]["avail"][(F, "Q1")]:
            return False
    if abs(t["total_occ"] - v["cancelled_block"]["total_occ"]) < 0.003:
        return False
    # Fox Den's February block has to reach into February from January
    if not any(b["prop"] == F and b["start"].month == 1 and b["end"].month == 2 and b["end"].day > 1 for b in d["blocks"]):
        return False
    # pinned integers stand apart on their rows
    for p, key in ((A, "nights"), (B, "nights"), (F, "avail")):
        val = t[key][(p, "Q1")]
        row = [t["nights"][(p, m)] for m in MONTHS + ["Q1"]] + [t["avail"][(p, m)] for m in MONTHS + ["Q1"]]
        if row.count(val) > 1 or val < 32:
            return False
    for p in PROPS:
        occs = [t["occ"][(p, m)] for m in MONTHS + ["Q1"]]
        if any(abs(a - b) < 0.003 for i, a in enumerate(occs) for b in occs[i + 1:]):
            return False
        if not all(0.35 <= o <= 0.97 for o in occs):
            return False
    if t["total_nights"] in [t["avail"][(p, "Q1")] for p in PROPS] + [t["total_avail"]]:
        return False
    # a rate read as a percentage must not land on one of the row's night counts
    for p, m in ((F, "2026-02"), (A, "2026-01")):
        ints = [t["nights"][(p, mm)] for mm in MONTHS + ["Q1"]] + [t["avail"][(p, mm)] for mm in MONTHS + ["Q1"]]
        if any(abs(i - t["occ"][(p, m)] * 100) <= 0.3 for i in ints):
            return False
    return True


# --------------------------------------------------------------------------- deliverables

def ics_text(blocks: list[dict]) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Juniper Ridge Cabins//Owner calendar 1.4//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Blocked dates - all cabins", "X-WR-TIMEZONE:America/Denver"]
    for i, b in enumerate(sorted(blocks, key=lambda x: (x["start"], x["prop"]))):
        lines += ["BEGIN:VEVENT", f"UID:block-{b['start'].strftime('%Y%m%d')}-{i:03d}@juniperridgecabins.com", "DTSTAMP:20260105T160000Z",
                  f"DTSTART;VALUE=DATE:{b['start'].strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{b['end'].strftime('%Y%m%d')}",
                  f"SUMMARY:{b['prop']}: {b['what']}", f"STATUS:{b['status']}", "TRANSP:OPAQUE", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def report_workbook(nights_rows: list[list], avail_rows: list[list], note: str) -> dict:
    """nights_rows: [property, date] one per occupied night; avail_rows: [property, month, days_in_month, blocked_nights]"""
    n = len(nights_rows) + 1
    a = len(avail_rows) + 1
    summ = []
    for i, p in enumerate(PROPS, start=2):
        row = [p]
        for j, m in enumerate(MONTHS):
            row.append(f'=COUNTIFS(Nights!$A$2:$A${n},$A{i},Nights!$C$2:$C${n},"{m}")')
        row.append(f"=SUM(B{i}:D{i})")
        for j, m in enumerate(MONTHS):
            row.append(f'=SUMIFS(Available!$E$2:$E${a},Available!$A$2:$A${a},$A{i},Available!$B$2:$B${a},"{m}")')
        row.append(f"=SUM(F{i}:H{i})")
        for j in range(3):
            bl, al = "BCD"[j], "FGH"[j]
            row.append(f"=IF({al}{i}=0,0,ROUND({bl}{i}/{al}{i},4))")
        row.append(f"=IF(I{i}=0,0,ROUND(E{i}/I{i},4))")
        summ.append(row)
    last = len(PROPS) + 1
    tot = ["Total"] + [f"=SUM({c}2:{c}{last})" for c in "BCDEFGHI"]
    for j in range(4):
        bl, al = "BCDE"[j], "FGHI"[j]
        tot.append(f"=IF({al}{last + 1}=0,0,ROUND({bl}{last + 1}/{al}{last + 1},4))")
    summ.append(tot)
    summ.append([])
    summ.append([note])
    header = ["Property"] + [f"Booked nights {m}" for m in MONTHS] + ["Booked nights Q1"] + [f"Available nights {m}" for m in MONTHS] + \
             ["Available nights Q1"] + [f"Occupancy {m}" for m in MONTHS] + ["Occupancy Q1"]
    return {"Occupancy": {"header": header, "rows": summ, "widths": {"A": 20}},
            "Nights": {"header": ["property", "night", "month", "reservation"], "rows": nights_rows},
            "Available": {"header": ["property", "month", "days_in_month", "blocked_nights", "available_nights"],
                          "rows": [[p, m, dim, bl, f"=C{i}-D{i}"] for i, (p, m, dim, bl) in enumerate(avail_rows, start=2)]}}


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    t = compute(d)
    rows = d["rows"]

    # ---- workspace
    r = rng(seed + 11)
    body = []
    for x in rows:
        style = r.randrange(3)
        fmt = (lambda dt: dt.isoformat()) if style == 0 else (lambda dt: dt.strftime("%m/%d/%Y")) if style == 1 else (lambda dt: dt.strftime("%b %d %Y"))
        body.append([x["code"], LISTING[x["prop"]], x["guest"], x["channel"], fmt(x["ci"]), fmt(x["co"]), x["nights"], x["status"],
                     f"{x['payout']:.2f}"])
    write_csv(os.path.join(ws, "reservations_export_2026-04-02.csv"),
              ["Confirmation Code", "Listing", "Guest", "Channel", "Check-in", "Check-out", "Nights", "Status", "Payout (USD)"], body,
              bom=True, crlf=True)
    write_bytes(os.path.join(ws, "blocked_dates_all_cabins.ics"), ics_text(d["blocks"]).encode("utf-8"))
    write_text(os.path.join(ws, "occupancy_note_from_ruth.txt"),
               "Occupancy for the owners' Q1 letter\n\n"
               "Each owner wants their cabin's occupancy for January, February and March. We work it the way the owner\n"
               "agreements define it:\n\n"
               "  occupancy = nights a paying guest stayed / nights the cabin was available to rent\n\n"
               "- A night belongs to the date the guest sleeps there. Check-out day is not a night. A stay from 30 March to\n"
               "  2 April is two nights in March and one in April.\n"
               "- Nights the cabin was blocked - owner holds and maintenance on the blocked-dates calendar - were never\n"
               "  available, so they come off the available nights. Events in that calendar end the morning after the last\n"
               "  blocked night, the way calendar apps store all-day events. Anything marked cancelled there did not happen.\n"
               "- When an owner uses their own cabin we book it in the channel manager as an Owner stay with no payout. That is\n"
               "  the owner's time, not a rental: treat those nights as blocked, not occupied.\n"
               "- Cancelled reservations are not stays, even where Airbnb paid us a cancellation fee.\n\n"
               "Ruth\n")

    # ---- reference
    write_csv(os.path.join(ref, "occupancy.csv"),
              ["property", "month", "booked_nights", "available_nights", "occupancy"],
              [[p, m, t["nights"][(p, m)], t["avail"][(p, m)], f"{t['occ'][(p, m)]:.4f}"] for p in PROPS for m in MONTHS + ["Q1"]])
    v = variants(d)
    rate_pins = [["Fox Den Cabin", "2026-02", t["occ"][("Fox Den Cabin", "2026-02")]], ["Aspen Hollow", "2026-01", t["occ"][("Aspen Hollow", "2026-01")]],
                 ["total", "Q1", t["total_occ"]]]
    write_json(os.path.join(ref, "notes.json"), {
        "rate_pins": rate_pins, "total_nights": t["total_nights"], "total_available": t["total_avail"], "total_occupancy": t["total_occ"],
        "naive": {k: {"total_nights": v[k]["total_nights"], "total_occ": v[k]["total_occ"],
                      "fox_feb": v[k]["occ"][("Fox Den Cabin", "2026-02")], "aspen_jan": v[k]["occ"][("Aspen Hollow", "2026-01")]} for k in v}})

    # ---- reference solution
    nights_rows = []
    for x in rows:
        if x["kind"] != "guest":
            continue
        for n in nights_of(x["ci"], x["co"]):
            if mkey(n) in MONTHS:
                nights_rows.append([x["prop"], n.isoformat(), mkey(n), x["code"]])
    avail_rows = []
    for p in PROPS:
        for m in MONTHS:
            dim = calendar.monthrange(int(m[:4]), int(m[5:]))[1]
            avail_rows.append([p, m, dim, dim - t["avail"][(p, m)]])
    note = ("Nights by the date slept (check-out day excluded). Available = days in month less blocked nights: calendar blocks "
            "(DTEND exclusive, cancelled events ignored) and Owner stays. Cancelled reservations excluded.")
    write_xlsx(os.path.join(sol, "occupancy.xlsx"), report_workbook(nights_rows, avail_rows, note), creator="reference")

    write_task_yaml(HERE, {
        "id": "occupancy-report", "track": "desk", "category": "reports",
        "title": "Q1 occupancy per cabin per month",
        "ask": ("I need Q1 occupancy for each of our cabins for the owners' letters - one row per cabin, January to March across. "
                "Save it as occupancy.xlsx with live formulas. Ruth's note says how the owner agreements count it.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "stays cross month ends - a New Year stay checks in during December and one late-March stay checks out in April - and the "
            "export's Nights column is the whole stay; putting all of a stay's nights in its check-in month moves Aspen Hollow's "
            "January and its quarter (checks: Aspen Hollow Q1 booked nights; occupancy rates)",
            "blocked dates are an iCalendar file whose all-day DTEND is the morning after the last blocked night; reading DTEND as a "
            "blocked night takes one extra night off every block, and Fox Den's owner hold runs from late January into February "
            "(checks: Fox Den Cabin Q1 available nights; occupancy rates)",
            "one maintenance block in the calendar is STATUS:CANCELLED and guests stayed on those dates (check: occupancy rates)",
            "cancelled reservations stay in the export, some carrying a cancellation-fee payout, and some overlap the stay that "
            "rebooked the dates; Bear Creek has three (checks: Bear Creek Lodge Q1 booked nights; total Q1 booked nights)",
            "owner stays are $0 'Owner' reservations with status Confirmed; Ruth's note makes those nights blocked rather than "
            "occupied (checks: Bear Creek Lodge Q1 booked nights; total Q1 booked nights)",
            "the listing names carry marketing suffixes ('Cedar Loft | studio near lifts'), check-in and check-out come in three "
            "date formats, and the export has a BOM and CRLF endings (check: total Q1 booked nights)",
        ],
        "checks": [
            {"type": "file_exists", "name": "occupancy.xlsx exists", "path": "occupancy.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "occupancy.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "occupancy.xlsx"},
            {"type": "xlsx_value_present", "name": "Aspen Hollow Q1 booked nights (stays split at month ends)", "path": "occupancy.xlsx",
             "expected": t["nights"][("Aspen Hollow", "Q1")], "rel_tol": 0.001, "near_text": "aspen"},
            {"type": "xlsx_value_present", "name": "Bear Creek Lodge Q1 booked nights (no cancellations or owner stays)", "path": "occupancy.xlsx",
             "expected": t["nights"][("Bear Creek Lodge", "Q1")], "rel_tol": 0.001, "near_text": "bear creek"},
            {"type": "xlsx_value_present", "name": "Fox Den Cabin Q1 available nights (blocks, DTEND exclusive)", "path": "occupancy.xlsx",
             "expected": t["avail"][("Fox Den Cabin", "Q1")], "rel_tol": 0.001, "near_text": "fox den"},
            {"type": "xlsx_value_present", "name": "total Q1 booked nights", "path": "occupancy.xlsx",
             "expected": t["total_nights"], "rel_tol": 0.001, "near_text": "total"},
            {"type": "custom", "name": "occupancy rates for Fox Den February, Aspen Hollow January and the portfolio quarter", "module": "check.py"},
        ],
    })
    print(f"seed={seed} rows={len(rows)} blocks={len(d['blocks'])} nights={ {p: t['nights'][(p, 'Q1')] for p in PROPS} } "
          f"avail={ {p: t['avail'][(p, 'Q1')] for p in PROPS} } total={t['total_nights']}/{t['total_avail']}={t['total_occ']} pins={rate_pins}")


def write_naive(d: dict, out: str) -> None:
    """Every reservation row counted, all nights in the check-in month from the Nights column, blocks ignored."""
    os.makedirs(out, exist_ok=True)
    nights_rows = []
    for x in d["rows"]:
        if mkey(x["ci"]) in MONTHS:
            for k in range(x["nights"]):
                nights_rows.append([x["prop"], x["ci"].isoformat(), mkey(x["ci"]), x["code"]])
    avail_rows = [[p, m, calendar.monthrange(int(m[:4]), int(m[5:]))[1], 0] for p in PROPS for m in MONTHS]
    write_xlsx(os.path.join(out, "occupancy.xlsx"), report_workbook(nights_rows, avail_rows, "naive"), creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(2000):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 2000 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
