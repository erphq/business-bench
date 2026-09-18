#!/usr/bin/env python3
"""rent-roll-build: an October 1 rent roll for a two-building apartment owner from three system exports.

    python gen.py [--seed N] [--naive DIR]

Business: a family that owns two small walk-up apartment buildings (Alder Court, 14 units, and Birch House,
10 units) and runs them on a cheap property-management app. The lender wants a rent roll; the app can only
export its unit list, its lease table and its tenant table separately.

Traps (each caught by a check, see task.yaml):
  * three units carry an old, ended lease and the new lease that replaced it      (checks: total monthly rent; every unit)
  * three tenants are month-to-month on a lease that ended months ago: still occupied, not expiring, and paying
    the $75 month-to-month fee the owner's email describes                         (checks: Month-to-month rent; every unit)
  * rent is text: "$1,250/mo", "1250 / month", "$1,250.00 monthly"                 (check: total monthly rent)
  * three units have no current lease (never leased, moved out, signed but not moved in) and must appear as vacant
                                                                                   (check: every unit)
  * both buildings number their units 101-205, and the lease export names the property in three spellings
                                                                                   (check: every unit)
  * the renewal window is October 1 to December 31 inclusive; one lease ends December 31, one January 31
                                                                                   (check: every unit)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

AS_OF = date(2026, 10, 1)
WINDOW_END = date(2026, 12, 31)
MTM_FEE = 75
BUILDINGS = [("Alder Court", "A", [101, 102, 103, 104, 105, 106, 107, 201, 202, 203, 204, 205, 206, 207]),
             ("Birch House", "B", [101, 102, 103, 104, 105, 201, 202, 203, 204, 205])]
PROPERTY_SPELL = {"Alder Court": ["Alder Court", "Alder Ct", "ALDER COURT"], "Birch House": ["Birch House", "Birch Hse", "BIRCH HOUSE"]}
MARKET = {0: (1050, 1150), 1: (1250, 1400), 2: (1550, 1800), 3: (1950, 2200)}


def month_end(y: int, m: int) -> date:
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def lease_start_for(end: date) -> date:
    """A twelve-month lease that ends on `end` (a month end) started on the first of the following month a year earlier."""
    return date(end.year - 1, end.month + 1, 1) if end.month != 12 else date(end.year, 1, 1)


def rent_text(v: int, style: int) -> str:
    return [f"${v:,}/mo", f"{v} / month", f"${v:,.2f} monthly", f"${v:,}/mo", f"${v:,.2f}"][style % 5]


def build(seed: int) -> dict:
    r = rng(seed)
    units = []
    for bname, prefix, nums in BUILDINGS:
        for n in nums:
            beds = r.choice([0, 1, 1, 2, 2, 3]) if n % 100 != 1 else r.choice([2, 3])
            lo, hi = MARKET[beds]
            units.append({"id": f"{prefix}-{n}", "building": bname, "num": n, "beds": beds, "baths": 1 if beds < 2 else r.choice([1, 2]),
                          "sqft": {0: 460, 1: 640, 2: 880, 3: 1090}[beds] + r.randint(-4, 6) * 10,
                          "market": int(round(r.uniform(lo, hi) / 25.0)) * 25})
    order = list(range(len(units)))
    r.shuffle(order)
    roles = (["never"] + ["moved_out"] + ["preleased"] + ["released"] * 3 + ["mtm"] * 3 + ["expiring"] * 6 + ["current"] * 9)
    for idx, role in zip(order, roles):
        units[idx]["role"] = role
    # tenants with unique last names
    names, seen_last = [], set()
    while len(names) < 48:
        f, l = person(r)
        if l not in seen_last:
            seen_last.add(l); names.append((f, l))
    tid = iter(range(1040, 2000, 3))
    tenants = []

    def new_tenant():
        f, l = names[len(tenants)]
        t = {"id": f"T-{next(tid)}", "first": f, "last": l, "phone": phone_digits(r), "email": email_for(r, f, l)}
        tenants.append(t)
        return t

    leases = []
    lid = iter(range(3101, 9999, 7))

    def lease(u, start, end, rent, notes="", roommates=False):
        ts = [new_tenant()]
        if roommates:
            ts.append(new_tenant())
        lz = {"id": f"L-{next(lid)}", "unit": u["id"], "tenants": ts, "start": start, "end": end, "rent": rent, "notes": notes,
              "style": r.randrange(5), "date_style": r.choice([1, 0, 1]), "prop_style": r.randrange(3), "k": r.random()}
        leases.append(lz)
        return lz

    expiring_ends = [date(2026, 10, 31), date(2026, 12, 31)] + [month_end(2026, r.choice([10, 11, 12])) for _ in range(4)]
    later_ends = [date(2027, 1, 31)] + [month_end(2027, r.randint(2, 9)) for _ in range(8)]
    for u in units:
        base = u["market"] - int(round(r.uniform(0, 120) / 5.0)) * 5
        role = u["role"]
        u["current"] = None
        u["former"] = None
        if role == "never":
            u["note"] = "renovated this summer, not yet listed"
        elif role == "moved_out":
            old = lease(u, date(2025, 9, 1), date(2026, 8, 31), base - 25)
            u["former"] = old
        elif role == "preleased":
            old = lease(u, date(2025, 9, 16), date(2026, 9, 15), base - 50)
            lease(u, date(2026, 10, 15), date(2027, 10, 14), base + 25, notes="signed 9/20, keys 10/15")
            u["former"] = old
        elif role == "released":
            end_old = month_end(2026, r.choice([5, 6, 7]))
            old = lease(u, lease_start_for(end_old), end_old, base - r.choice([60, 75, 90, 110]))
            start_new = end_old + timedelta(days=r.choice([1, 16, 31]))
            new = lease(u, start_new, date(start_new.year + 1, start_new.month, start_new.day) - timedelta(days=1), base + 25,
                        roommates=r.random() < 0.3)
            u["current"], u["former"] = new, old
        elif role == "mtm":
            end = month_end(2026, r.choice([3, 5, 6, 8]))
            cur = lease(u, lease_start_for(end), end, base - r.choice([40, 65, 85]),
                        notes=r.choice(["MTM", "month to month since lease end", "went month-to-month"]))
            u["current"], u["mtm"] = cur, True
        elif role == "expiring":
            end = expiring_ends.pop()
            u["current"] = lease(u, lease_start_for(end), end, base, roommates=r.random() < 0.25)
        else:
            end = later_ends.pop()
            u["current"] = lease(u, lease_start_for(end), end, base, roommates=r.random() < 0.2)
        u.setdefault("mtm", False)
        u.setdefault("note", "")
        if u["current"]:
            u["rent"] = u["current"]["rent"] + (MTM_FEE if u["mtm"] else 0)
            u["expiring"] = (not u["mtm"]) and AS_OF <= u["current"]["end"] <= WINDOW_END
        else:
            u["rent"] = 0
            u["expiring"] = False
    total = sum(u["rent"] for u in units)
    return {"units": units, "leases": leases, "tenants": tenants, "total": total}


def acceptable(d: dict) -> bool:
    units = d["units"]
    # the naive lease-driven total (every lease, no fee) must move well away from the truth
    naive_total = sum(lz["rent"] for lz in d["leases"])
    if abs(naive_total - d["total"]) < 0.05 * d["total"]:
        return False
    for u in units:
        if u["mtm"]:
            rent = u["rent"]
            if abs(u["market"] - rent) <= 0.01 * rent or abs(u["current"]["rent"] - rent) <= 0.01 * rent:
                return False
    # every occupied rent unique enough that a row check cannot be satisfied by a neighbour's number
    rents = [u["rent"] for u in units if u["current"]]
    if len(set(rents)) < len(rents) - 4:
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def roll_rows(d: dict) -> list[list]:
    rows = []
    for u in d["units"]:
        cur = u["current"]
        bb = f"{'Studio' if u['beds'] == 0 else str(u['beds']) + ' bd'}/{u['baths']} ba"
        if cur:
            names = " & ".join(f"{t['first']} {t['last']}" for t in cur["tenants"])
            status = "Month-to-month" if u["mtm"] else "Occupied"
            note = "lease ended " + cur["end"].isoformat() + "; $75 month-to-month fee" if u["mtm"] else ""
            rows.append([u["id"], u["building"], bb, u["sqft"], u["market"], names, cur["start"], cur["end"], cur["rent"],
                         MTM_FEE if u["mtm"] else 0, None, status, "Yes" if u["expiring"] else "", note])
        else:
            pre = [lz for lz in d["leases"] if lz["unit"] == u["id"] and lz["start"] > AS_OF]
            note = f"pre-leased from {pre[0]['start'].isoformat()}" if pre else u["note"]
            rows.append([u["id"], u["building"], bb, u["sqft"], u["market"], "VACANT", None, None, 0, 0, None, "Vacant", "", note])
    for i, row in enumerate(rows, start=2):
        row[10] = f"=I{i}+J{i}"
    return rows


def roll_sheets(rows: list[list]) -> dict:
    n = len(rows) + 1
    tail = [
        [],
        ["Total monthly rent", "", "", "", f"=SUM(E2:E{n})", "", "", "", f"=SUM(I2:I{n})", f"=SUM(J2:J{n})", f"=SUM(K2:K{n})"],
        ["Occupied units", "", "", "", "", "", "", "", "", "", f'=COUNTIF(L2:L{n},"Occupied")+COUNTIF(L2:L{n},"Month-to-month")'],
        ["Vacant units", "", "", "", "", "", "", "", "", "", f'=COUNTIF(L2:L{n},"Vacant")'],
        ["Leases expiring Oct 1 - Dec 31", "", "", "", "", "", "", "", "", "", f'=COUNTIF(M2:M{n},"Yes")'],
    ]
    return {"Rent roll": {"header": ["Unit", "Building", "Bed/Bath", "Sq ft", "Market rent", "Tenant", "Lease start", "Lease end",
                                     "Lease rent", "MTM fee", "Monthly rent", "Status", "Expiring by 12/31", "Notes"],
                          "rows": rows + tail, "widths": {"A": 9, "B": 13, "F": 30, "G": 12, "H": 12, "L": 15, "N": 36}, "freeze": "A2"}}


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    by_id = {u["id"]: u for u in d["units"]}
    if naive_dir:
        # one row per lease from the lease table, joined to tenants; ended leases read as expiring; no vacant units
        os.makedirs(naive_dir, exist_ok=True)
        rows = []
        for i, lz in enumerate(sorted(d["leases"], key=lambda x: (x["unit"], x["start"])), start=2):
            u = by_id[lz["unit"]]
            rows.append([u["id"], u["building"], "", u["sqft"], u["market"], " & ".join(f"{t['first']} {t['last']}" for t in lz["tenants"]),
                         lz["start"], lz["end"], lz["rent"], 0, f"=I{i}+J{i}", "Occupied", "Yes" if lz["end"] <= WINDOW_END else "", ""])
        write_xlsx(os.path.join(naive_dir, "rent_roll.xlsx"), roll_sheets(rows), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 5)

    write_xlsx(os.path.join(ws, "unit_list.xlsx"), {"Units": {
        "merged_title": "Unit directory - Alder Court & Birch House",
        "header": ["Unit ID", "Building", "Beds", "Baths", "Sq Ft", "Market Rent"],
        "rows": [[u["id"], u["building"], "Studio" if u["beds"] == 0 else u["beds"], u["baths"], u["sqft"], u["market"]] for u in d["units"]],
        "widths": {"B": 14}}}, creator="RentEasy")
    lrows = []
    for lz in sorted(d["leases"], key=lambda x: x["k"]):
        u = by_id[lz["unit"]]
        unit_txt = [str(u["num"]), f"#{u['num']}", f"Apt {u['num']}"][int(lz["k"] * 3)]
        lrows.append([lz["id"], PROPERTY_SPELL[u["building"]][lz["prop_style"]], unit_txt, "; ".join(t["id"] for t in lz["tenants"]),
                      date_variant(lz["start"], lz["date_style"]), date_variant(lz["end"], lz["date_style"]),
                      rent_text(lz["rent"], lz["style"]), money_str(float(lz["rent"]), 1), lz["notes"]])
    write_csv(os.path.join(ws, "lease_export_2026-10-01.csv"),
              ["Lease #", "Property", "Unit", "Tenant IDs", "Start", "End", "Rent", "Deposit", "Notes"], lrows,
              preamble=["RentEasy lease table export", "Exported 10/01/2026 07:02"], bom=True, crlf=True)
    trows = [[t["id"], t["last"], t["first"], phone_variant(t["phone"], r.randrange(7)), t["email"]] for t in d["tenants"]]
    r.shuffle(trows)
    write_csv(os.path.join(ws, "tenants.csv"), ["Tenant ID", "Last Name", "First Name", "Phone", "Email"], trows)
    write_email_thread(os.path.join(ws, "email_from_owner.txt"), [
        {"from": "Carol Whitcombe <carol@alderbirchrentals.com>", "to": "you", "date": "Wed, 30 Sep 2026 18:40",
         "subject": "rent roll for the bank",
         "body": ("The bank wants a rent roll as of October 1 for the refinance. RentEasy only lets me export the three tables, "
                  "so they're all in the folder.\n\n"
                  "Every unit in both buildings has to be on it, including the empty ones - the bank counts them. For each unit "
                  "I need who is living there on the 1st, their lease dates and what they pay us each month, and a total at the "
                  "bottom.\n\n"
                  "A few people stayed on after their lease ran out and are month to month now. RentEasy still shows their old "
                  "lease rent, but month-to-month tenants pay an extra $75 a month on top of it (we bill it as a separate "
                  "charge), so put their real monthly amount on the roll.\n\n"
                  "Also flag any lease that ends between October 1 and December 31 so I know whose renewals to start. The "
                  "month-to-month people don't have a lease to renew, so leave them off that.\n\nThanks,\nCarol")}])

    # ---- reference ----
    ref_rows = []
    for u in d["units"]:
        cur = u["current"]
        ref_rows.append([u["id"], u["building"], str(u["num"]),
                         "vacant" if not cur else ("month-to-month" if u["mtm"] else "occupied"),
                         cur["tenants"][0]["last"] if cur else "", u["rent"], "yes" if u["expiring"] else "no",
                         u["former"]["tenants"][0]["last"] if (not cur and u["former"]) else ""])
    write_csv(os.path.join(ref, "rent_roll.csv"), ["unit", "building", "unit_number", "status", "tenant_last", "monthly_rent", "expiring",
                                                  "former_tenant_last"], ref_rows)
    mtm_units = [u for u in d["units"] if u["mtm"]]
    write_json(os.path.join(ref, "notes.json"), {"as_of": AS_OF, "window_end": WINDOW_END, "total_monthly_rent": d["total"],
                                                  "vacant": [u["id"] for u in d["units"] if not u["current"]],
                                                  "expiring": [u["id"] for u in d["units"] if u["expiring"]],
                                                  "month_to_month": [u["id"] for u in mtm_units],
                                                  "released": [u["id"] for u in d["units"] if u["role"] == "released"]})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "rent_roll.xlsx"), roll_sheets(roll_rows(d)), creator="reference")

    mtm = mtm_units[0]
    write_task_yaml(HERE, {
        "id": "rent-roll-build", "track": "desk", "category": "spreadsheet",
        "title": "October rent roll for the bank",
        "ask": ("Carol needs a rent roll for the bank from the RentEasy exports in this folder. Save it as rent_roll.xlsx with the "
                "total as a formula; her email says what goes on it.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "three units carry both an ended lease and the new lease that replaced it; one row per lease keeps the old tenant on "
            "the roll and adds the old rent to the total (checks: total monthly rent; every unit with tenant, rent and renewal flag)",
            "three tenants are month to month on leases that ended between March and August: they are occupied, they are not "
            "renewals, and per Carol's email they pay the lease rent plus the $75 fee RentEasy does not show "
            "(checks: month-to-month rent with the fee; every unit with tenant, rent and renewal flag)",
            "rent is text in five shapes ('$1,250/mo', '1250 / month', '$1,250.00 monthly') and the deposit column beside it is "
            "also money (check: total monthly rent)",
            "three units have no lease in force on October 1 - one never leased, one moved out in August, one signed for October "
            "15 - and a roll built from the lease table drops them (check: every unit with tenant, rent and renewal flag)",
            "both buildings number units 101 to 205 and the lease export writes the property as 'Alder Ct' / 'ALDER COURT' and "
            "the unit as '101', '#101' or 'Apt 101'; joining on the unit number alone crosses the buildings "
            "(check: every unit with tenant, rent and renewal flag)",
            "the renewal window is October 1 to December 31 inclusive: one lease ends on December 31 and one on January 31, and "
            "ended leases and month-to-month tenants are not renewals (check: every unit with tenant, rent and renewal flag)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "rent_roll.xlsx", "min_count": 1},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "rent_roll.xlsx"},
            {"type": "xlsx_value_present", "name": "total monthly rent", "path": "rent_roll.xlsx",
             "expected": float(d["total"]), "rel_tol": float(f"{0.9 / d['total']:.8f}"), "near_text": "total"},
            {"type": "xlsx_value_present", "name": "month-to-month rent with the fee", "path": "rent_roll.xlsx",
             "expected": float(mtm["rent"]), "rel_tol": 0.0005, "near_text": mtm["current"]["tenants"][0]["last"].lower()},
            {"type": "custom", "name": "every unit with tenant, rent and renewal flag", "module": "check.py"},
        ],
    })
    print(f"seed={seed} total={d['total']} leases={len(d['leases'])} expiring={sum(u['expiring'] for u in d['units'])}")


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
