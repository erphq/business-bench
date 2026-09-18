#!/usr/bin/env python3
"""Deterministic seed generator for the memberships-club build task.

    python gen.py [--seed N]

Writes:
  seed/members.csv        member export from the old club system: exact duplicate rows, rows that repeat
                          a member number written 412 / M00412 with the email in another case, families
                          that share one email (distinct members), stale "Active" status on lapsed
                          members, cancelled spelled three ways, plan and fee strings, mixed dates, and
                          one impossible date of birth
  seed/checkins.csv       door scans for 25 July to 31 August 2026: double scans a minute or two apart,
                          member numbers written three ways, four timestamp formats (12- and 24-hour)
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Expiry dates avoid 2026-09-01 to 2027-02-28, so active/lapsed figures hold for any test date in that
window. Trainer names are fixed across seeds (the ask names Jess Alvarez); other seeds re-roll members,
dates, and scans, and counts.json is recomputed from the truth.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, email_for, money_str, phone_digits, phone_variant, write_csv, write_json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

TRAINERS = ["Jess Alvarez", "Kofi Mensah", "Tom Brennan", "Aiko Tanaka", "Ravi Desai", "Mia Kowalczyk"]
RESTRICTED = "Jess Alvarez"
OTHER = "Kofi Mensah"
PLANS = {"Monthly": (6500, 1), "Quarterly": (18000, 3), "Annual": (66000, 12)}
N_CURRENT, N_LAPSED, N_CANCELLED = 152, 37, 31
N_EXACT_DUPES, N_NUMBER_DUPES = 4, 5
N_DOUBLE_SCANS = 12
DOUBLE_SCAN_WINDOW_MIN = 5
GAP_START, GAP_END = date(2026, 9, 1), date(2027, 2, 28)
CHECKIN_START, CHECKIN_END = date(2026, 7, 25), date(2026, 8, 31)
FREEZE_DAYS = 30
EARLY_ANNUAL_DISCOUNT = 0.05
RESERVED_SURNAMES = {"Whitfield", "Okonkwo", "Brannigan"}
HOUR_WEIGHTS = {5: 2, 6: 9, 7: 8, 8: 5, 9: 4, 10: 3, 11: 3, 12: 6, 13: 4, 14: 2, 15: 2, 16: 5, 17: 10, 18: 9, 19: 6, 20: 3, 21: 1}
MEMBER_COLUMNS = ["Member #", "First Name", "Last Name", "Email", "Phone", "Plan", "Joined", "Expires", "Fee", "Trainer",
                  "Status", "Date of Birth", "Notes"]
NOTES = ["", "", "", "", "", "", "Prefers mornings", "Referred by a friend", "Knee injury - check with trainer",
         "Corporate discount ended", "Moved from Off-Peak", "Locker 114", "Student ID on file", "Paid by card on file"]


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def rand_date(r, a: date, b: date) -> date:
    return a + timedelta(days=r.randint(0, (b - a).days))


def num_str(n: int, style: int) -> str:
    return [f"M-{n:05d}", f"M{n:05d}", f"{n:05d}", f"{n}"][style]


def usd(c: int) -> str:
    return f"{c / 100:,.2f}"


def ts_str(t: datetime, style: int) -> str:
    h12 = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return [
        t.strftime("%Y-%m-%d %H:%M"),
        f"{t.month}/{t.day}/{t.year} {h12}:{t.minute:02d} {ampm}",
        t.strftime("%d-%b-%Y %H:%M"),
        t.strftime("%m/%d/%y %H:%M"),
    ][style]


def main() -> None:
    seed = argparse_seed()
    r = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)

    # ------------------------------------------------------------------ members (truth)
    n_total = N_CURRENT + N_LAPSED + N_CANCELLED
    pairs = [(f, l) for f in FIRST for l in LAST if l not in RESERVED_SURNAMES and f not in ("Marcus", "Dana")]
    r.shuffle(pairs)
    specials = [("Laura", "Whitfield", "fam_w"), ("Ethan", "Whitfield", "fam_w"), ("Martin", "Whitfield", None),
                ("Grace", "Okonkwo", "fam_o"), ("Daniel", "Okonkwo", "fam_o"), ("Sean", "Brannigan", "fam_b"), ("Maeve", "Brannigan", "fam_b")]
    family_email = {"fam_w": "thewhitfields@gmail.com", "fam_o": "okonkwo.home@yahoo.com", "fam_b": "brannigans@outlook.com"}
    names = [(f, l, fam) for f, l, fam in specials] + [(f, l, None) for f, l in pairs[:n_total - len(specials)]]
    numbers = r.sample(range(100, 2600), n_total)
    groups = ["current"] * N_CURRENT + ["lapsed"] * N_LAPSED + ["cancelled"] * N_CANCELLED
    rest_groups = groups[:]
    for _ in specials:
        rest_groups.remove("current")
    r.shuffle(rest_groups)
    members, used_emails = [], set(family_email.values())
    for i, (first, last, fam) in enumerate(names):
        group = "current" if i < len(specials) else rest_groups[i - len(specials)]
        plan = r.choices(list(PLANS), weights=[45, 25, 30])[0]
        if fam:
            email = family_email[fam]
        else:
            email = email_for(r, first, last)
            while email in used_emails:
                email = email_for(r, first, last)
            used_emails.add(email)
        members.append({"num": numbers[i], "first": first, "last": last, "email": email, "fam": fam, "group": group,
                        "plan": plan, "phone": phone_digits(r), "trainer": r.choice(TRAINERS) if r.random() < 0.48 else "",
                        "dob": rand_date(r, date(1952, 1, 1), date(2008, 6, 30)), "note": r.choice(NOTES)})

    def set_expiry(m, forced=None):
        if forced:
            m["expires"] = forced
        elif m["group"] == "current":
            hi = {"Monthly": date(2027, 4, 30), "Quarterly": date(2027, 6, 30), "Annual": date(2027, 12, 20)}[m["plan"]]
            m["expires"] = rand_date(r, date(2027, 3, 1), hi)
        elif m["group"] == "lapsed":
            m["expires"] = rand_date(r, date(2025, 10, 1), date(2026, 8, 31))
        else:
            m["expires"] = rand_date(r, date(2024, 9, 1), date(2026, 8, 31))
        m["joined"] = rand_date(r, date(2019, 3, 1), add_months(m["expires"], -PLANS[m["plan"]][1]) - timedelta(days=1))

    for m in members:
        set_expiry(m)

    specials_ids = {id(m) for m in members[:len(specials)]}
    pool = [m for m in members if id(m) not in specials_ids]

    def pick(group, plan=None, trainer=None, exclude=()):
        cands = [m for m in pool if m["group"] == group and (plan is None or m["plan"] == plan)
                 and (trainer is None or m["trainer"] == trainer) and all(m is not x for x in exclude) and not m.get("role")]
        return r.choice(cands)

    roles = {}

    def assign(role, m, **kw):
        m["role"] = role
        roles[role] = m
        for k, v in kw.items():
            m[k] = v
        return m

    assign("renew_active", pick("current", "Quarterly"), trainer="")
    set_expiry(roles["renew_active"], date(2027, 4, 18))
    assign("renew_lapsed", pick("lapsed", "Annual"), trainer="")
    set_expiry(roles["renew_lapsed"], date(2026, 6, 30))
    assign("freeze", pick("current", "Monthly"), trainer="")
    set_expiry(roles["freeze"], date(2027, 4, 10))
    assign("lapsed_door", pick("lapsed"))
    set_expiry(roles["lapsed_door"], rand_date(r, date(2026, 2, 1), date(2026, 7, 31)))
    assign("cancelled", pick("cancelled"))
    set_expiry(roles["cancelled"], date(2026, 5, 31))
    assign("door_ok", pick("current"), trainer="")
    assign("checkin_member", pick("current", trainer=RESTRICTED))
    assign("dob", pick("current"))
    assign("top_expiry", pick("current", "Annual"))
    set_expiry(roles["top_expiry"], date(2027, 12, 30))
    assign("early_annual", pick("current", "Annual"), trainer="")
    set_expiry(roles["early_annual"], date(2027, 5, 2))
    assign("lapsed_annual", pick("lapsed", "Annual"), trainer="")
    set_expiry(roles["lapsed_annual"], date(2026, 3, 15))
    assign("early_quarterly", pick("current", "Quarterly"), trainer="")
    set_expiry(roles["early_quarterly"], date(2027, 5, 20))
    assign("cancel_request", pick("current"), trainer="")
    assign("other_scope", pick("current", trainer=OTHER))
    assert all(not (GAP_START <= m["expires"] <= GAP_END) for m in members)
    assert sum(1 for m in members if m["expires"] == date(2027, 12, 30)) == 1

    # file text for each member
    status_text = {"current": ["Active", "Active", "active", "ACTIVE"], "lapsed": ["Active", "Active", "Expired"],
                   "cancelled": ["Cancelled", "Canceled", "CANCELLED"]}
    for m in members:
        m["status_str"] = r.choice(status_text[m["group"]])
        if m.get("role") in ("renew_lapsed", "lapsed_door"):
            m["status_str"] = "Active"
        if m.get("role") == "cancelled":
            m["status_str"] = "Canceled"
        m["plan_str"] = r.choice([m["plan"], m["plan"], m["plan"], m["plan"].lower(), m["plan"].upper(), m["plan"] + " "])
        m["fee_str"] = money_str(PLANS[m["plan"]][0] / 100, r.choice([1, 1, 2, 3, 6]))
        m["joined_str"] = date_variant(m["joined"], r.choice([0, 1, 2, 3, 4]))
        m["expires_str"] = date_variant(m["expires"], r.choice([0, 1, 2, 3, 4]))
        m["dob_str"] = date_variant(m["dob"], r.choice([0, 1, 1, 2]))
        m["phone_str"] = phone_variant(m["phone"], r.randrange(7))
        m["trainer_str"] = m["trainer"] if r.random() < 0.85 else m["trainer"].lower()
    roles["dob"]["dob_str"] = "2031-04-17"
    roles["top_expiry"]["expires_str"] = date_variant(date(2027, 12, 30), 2)

    def cols(m, num_style=0, email=None, phone=None, joined=None):
        return [num_str(m["num"], num_style), m["first"], m["last"], email if email is not None else m["email"],
                phone or m["phone_str"], m["plan_str"], joined or m["joined_str"], m["expires_str"], m["fee_str"],
                m["trainer_str"], m["status_str"], m["dob_str"], m["note"]]

    rows = [{"m": m, "kind": "unique", "cols": cols(m)} for m in members]
    martin = members[2]
    dup_pool = [m for m in pool if not m.get("role")]
    r.shuffle(dup_pool)
    exact = [martin] + dup_pool[:N_EXACT_DUPES - 1]
    numdup = dup_pool[N_EXACT_DUPES - 1:N_EXACT_DUPES - 1 + N_NUMBER_DUPES]
    for m in exact:
        rows.append({"m": m, "kind": "exact_duplicate", "cols": cols(m)})
    for m in numdup:
        rows.append({"m": m, "kind": "same_number_written_differently", "cols": cols(
            m, num_style=r.choice([1, 3, 3]), email=m["email"].upper() if r.random() < 0.5 else m["email"].capitalize(),
            phone=phone_variant(m["phone"], r.randrange(7)), joined=date_variant(m["joined"], 3))})
    r.shuffle(rows)
    for i, row in enumerate(rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "members.csv"), MEMBER_COLUMNS, [row["cols"] for row in rows])

    # ------------------------------------------------------------------ check-ins (truth)
    days = [CHECKIN_START + timedelta(days=i) for i in range((CHECKIN_END - CHECKIN_START).days + 1)]
    aug_days = [d for d in days if d.month == 8]
    july_days = [d for d in days if d.month == 7]
    current = [m for m in members if m["group"] == "current"]
    hours_list, weights = list(HOUR_WEIGHTS), list(HOUR_WEIGHTS.values())
    visits = []

    def visit(m, d, hour=None, minute=None):
        if any(v["m"] is m and v["t"].date() == d for v in visits):
            return None
        h = hour if hour is not None else r.choices(hours_list, weights=weights)[0]
        t = datetime(d.year, d.month, d.day, h, minute if minute is not None else r.randint(0, 59))
        v = {"m": m, "t": t, "door": "Main" if r.random() < 0.8 else "Side"}
        visits.append(v)
        return v

    cm = roles["checkin_member"]
    cm_aug = r.sample(aug_days, 9)
    for d in cm_aug:
        visit(cm, d, minute=r.randint(0, 50))
    visit(cm, r.choice(july_days))
    regulars = r.sample([m for m in current if m.get("role") not in ("checkin_member",)], 78)
    for m in regulars:
        for _ in range(r.choice([1, 1, 2, 2, 3, 4, 5, 6])):
            visit(m, r.choice(days))
    # the door_ok member and the freeze member have visited before; the renew/lapsed ones have not
    visit(roles["door_ok"], r.choice(aug_days))
    visits = [v for v in visits if v is not None]

    def aug_visits():
        return [v for v in visits if v["t"].month == 8]

    def hour_counts():
        c = {}
        for v in aug_visits():
            c[v["t"].hour] = c.get(v["t"].hour, 0) + 1
        return c

    while True:
        hc = hour_counts()
        top = max(hc.values())
        if sum(1 for n in hc.values() if n == top) == 1:
            break
        busiest = sorted(h for h, n in hc.items() if n == top)[-1]
        for _ in range(20):
            if visit(r.choice(regulars), r.choice(aug_days), hour=busiest):
                break

    visits.sort(key=lambda v: (v["t"], v["m"]["num"]))
    # double scans: second row 1-3 minutes later; two of them on the check-in member
    cm_visits = [v for v in visits if v["m"] is cm and v["t"].month == 8 and v["t"].minute <= 55]
    others = [v for v in visits if v["m"] is not cm and v["t"].minute <= 55]
    doubled = r.sample(cm_visits, 2) + r.sample(others, N_DOUBLE_SCANS - 2)
    scan_rows = []
    for v in visits:
        v["num_style"] = r.choices([0, 2, 3], weights=[60, 20, 20])[0]
        v["ts_style"] = r.randrange(4)
        v["name_str"] = f"{v['m']['first']} {v['m']['last']}"
        if r.random() < 0.08:
            v["name_str"] = v["name_str"].upper()
        scan_rows.append({"v": v, "t": v["t"], "kind": "visit"})
    for k, v in enumerate(doubled):
        t2 = v["t"] + timedelta(minutes=r.randint(1, 3))
        scan_rows.append({"v": v, "t": t2, "kind": "double_scan"})
    cm_rows = [row for row in scan_rows if row["v"]["m"] is cm]
    for row in cm_rows[:2]:
        row["v"]["num_style"] = 3
    scan_rows.sort(key=lambda s: (s["t"], s["v"]["m"]["num"], s["kind"]))
    for i, s in enumerate(scan_rows, start=2):
        s["line"] = i
    write_csv(os.path.join(SEED_DIR, "checkins.csv"), ["Member #", "Name", "Checked In", "Door"],
              [[num_str(s["v"]["m"]["num"], s["v"]["num_style"]), s["v"]["name_str"], ts_str(s["t"], s["v"]["ts_style"]), s["v"]["door"]]
               for s in scan_rows])
    # no two real visits of one member within the double-scan window
    for m in members:
        ts = sorted(v["t"] for v in visits if v["m"] is m)
        assert all((b - a).total_seconds() > 3600 for a, b in zip(ts, ts[1:]))

    # ------------------------------------------------------------------ figures
    def label(m):
        return {"member_no": num_str(m["num"], 0), "name": f"{m['first']} {m['last']}", "plan": m["plan"],
                "expires": m["expires"].isoformat(), "file_expires": m["expires_str"], "file_status": m["status_str"],
                "trainer": m["trainer"], "group": m["group"], "file_lines": sorted(rw["line"] for rw in rows if rw["m"] is m)}

    cur = [m for m in members if m["group"] == "current"]
    lapsed = [m for m in members if m["group"] == "lapsed"]
    cancelled = [m for m in members if m["group"] == "cancelled"]
    mine = [m for m in members if m["trainer"] == RESTRICTED]
    aug = aug_visits()
    hc = hour_counts()
    busiest = max(hc, key=hc.get)
    plan_counts = {p: sum(1 for m in members if m["plan"] == p) for p in PLANS}
    whitfields = [m for m in members if m["last"] == "Whitfield"]
    cm_aug_n = sum(1 for v in aug if v["m"] is cm)
    cm_rows_aug = sum(1 for s in scan_rows if s["v"]["m"] is cm and s["t"].month == 8)
    cm_last = max(v["t"] for v in visits if v["m"] is cm)
    cm_last_row = next(s for s in scan_rows if s["v"]["m"] is cm and s["t"] == cm_last)
    mine_aug = sum(1 for v in aug if v["m"]["trainer"] == RESTRICTED)

    ea, la, eq = roles["early_annual"], roles["lapsed_annual"], roles["early_quarterly"]
    counts = {
        "seed": seed,
        "valid_test_dates": [GAP_START.isoformat(), GAP_END.isoformat()],
        "date_dependence": "No imported expiry falls between 2026-09-01 and 2027-02-28, so active and lapsed counts hold for any test date in that window.",
        "rules": {
            "active": "not cancelled and expiry on or after the test date",
            "lapsed": "not cancelled and expiry before the test date (the file's Status column is stale for lapsed members)",
            "cancelled": "Status Cancelled, Canceled, or CANCELLED",
            "renewal": "adds one plan term (1, 3, or 12 months) to the current expiry if not yet lapsed, or to the renewal date if lapsed; the renewal amount is the plan price",
            "plan_prices": {p: usd(c) for p, (c, _) in PLANS.items()},
            "freeze": "up to 60 days; pushes expiry back by the frozen days; a frozen member cannot check in",
            "double_scan": f"a second scan of the same member within {DOUBLE_SCAN_WINDOW_MIN} minutes is the same visit",
        },
        "members": {
            "file_rows_excluding_header": len(rows),
            "exact_duplicate_rows": N_EXACT_DUPES,
            "same_number_rows": N_NUMBER_DUPES,
            "wrong_count_only_exact_duplicates_removed": len(rows) - N_EXACT_DUPES,
            "wrong_cancelled_missing_canceled_spelling": sum(1 for m in cancelled if m["status_str"] != "Canceled"),
            "wrong_lapsed_missing_canceled_spelling": len(lapsed) + sum(1 for m in cancelled if m["status_str"] == "Canceled"),
            "unique_members": len(members),
            "dedupe_rule": "same member number after dropping the M prefix, hyphen, and leading zeros; a shared email is not a duplicate",
            "active": len(cur), "lapsed": len(lapsed), "cancelled": len(cancelled),
            "lapsed_with_file_status_active": sum(1 for m in lapsed if m["status_str"] == "Active"),
            "wrong_lapsed_trusting_file_status": sum(1 for m in lapsed if m["status_str"] != "Active"),
            "wrong_lapsed_including_cancelled": len(lapsed) + len(cancelled),
            "cancelled_by_spelling": {sp: sum(1 for m in cancelled if m["status_str"] == sp) for sp in sorted({m["status_str"] for m in cancelled})},
            "freeze_rejection_member": label(members[0]),
            "cancelled_spellings": sorted({m["status_str"] for m in cancelled}),
            "plan_counts": plan_counts,
            "same_number_example": label(numdup[0]) | {"numbers_as_written": sorted({rw["cols"][0] for rw in rows if rw["m"] is numdup[0]})},
            "exact_duplicate_example": label(exact[1]),
            "families_sharing_email": {fam: {"email": family_email[fam], "members": [label(m) for m in members if m["fam"] == fam]}
                                       for fam in ("fam_w", "fam_o", "fam_b")},
            "impossible_dob": label(roles["dob"]) | {"file_dob": "2031-04-17"},
        },
        "checkins": {
            "file_rows_excluding_header": len(scan_rows),
            "double_scan_rows": N_DOUBLE_SCANS,
            "visits_total": len(visits),
            "visits_july": len(visits) - len(aug),
            "visits_august": len(aug),
            "august_rows_without_collapsing": sum(1 for s in scan_rows if s["t"].month == 8),
            "checkin_member": label(cm) | {"august_visits": cm_aug_n, "august_file_rows": cm_rows_aug, "july_visits": 1,
                                           "numbers_as_written": sorted({num_str(cm["num"], s["v"]["num_style"]) for s in scan_rows if s["v"]["m"] is cm}),
                                           "last_visit": cm_last.strftime("%Y-%m-%d %H:%M"), "last_visit_file_value": ts_str(cm_last, cm_last_row["v"]["ts_style"])},
            "restricted_trainer_client_visits_august": mine_aug,
        },
        "baseline": {
            "STAFF_ROLE": "Trainer", "VIEWER_ROLE": "Read-only", "MAIN_ENTITY": "member", "MAIN_ENTITY_PLURAL": "members",
            "SCOPE_RULE": f"members whose trainer is {RESTRICTED}", "SCOPE_COUNT": len(mine),
            "OUT_OF_SCOPE_EXAMPLE": label(roles["other_scope"]),
            "KPI_1": "Active members", "KPI_1_VALUE": len(cur),
            "KPI_2": "Lapsed members", "KPI_2_VALUE": len(lapsed),
            "KPI_3": "Check-ins in August 2026", "KPI_3_VALUE": len(aug),
            "KPI_4": "Cancelled members", "KPI_4_VALUE": len(cancelled),
            "SCOPED_KPI_1_VALUE": sum(1 for m in cur if m["trainer"] == RESTRICTED),
            "SEARCH_TERM": "Whitfield", "SEARCH_COUNT": len(whitfields),
            "FILTER_FIELD": "Plan", "FILTER_VALUE": "Quarterly", "FILTER_COUNT": plan_counts["Quarterly"],
            "SORT_FIELD": "Expires", "SORT_TOP": label(roles["top_expiry"]),
            "EXPORT_ROWS": len(members), "EXPORT_COLUMNS": ["Member #", "Name", "Plan", "Expires", "Trainer", "Status"],
            "REQUIRED_FIELD": "Plan",
        },
        "roles": {k: label(v) for k, v in sorted(roles.items())},
        "renewal_check": {"member": label(roles["renew_active"]), "new_expiry": add_months(date(2027, 4, 18), 3).isoformat(), "amount": usd(PLANS["Quarterly"][0])},
        "lapsed_renewal_check": {"member": label(roles["renew_lapsed"]), "new_expiry": "test date plus 12 months",
                                 "wrong_expiry_from_old_date": add_months(date(2026, 6, 30), 12).isoformat(), "amount": usd(PLANS["Annual"][0])},
        "freeze_check": {"member": label(roles["freeze"]), "days": FREEZE_DAYS, "new_expiry": (date(2027, 4, 10) + timedelta(days=FREEZE_DAYS)).isoformat(),
                         "rejected_days": 61},
        "change_1_hours": {"busiest_hour": f"{busiest:02d}:00-{busiest:02d}:59", "busiest_count": hc[busiest],
                           "six_am_count": hc.get(6, 0), "six_pm_count": hc.get(18, 0), "august_total": len(aug),
                           "per_hour": {f"{h:02d}": n for h, n in sorted(hc.items())},
                           "side_door_august": sum(1 for v in aug if v["door"] == "Side")},
        "change_2_discount": {
            "early_annual": label(ea) | {"new_expiry": add_months(ea["expires"], 12).isoformat(), "amount": usd(round(PLANS["Annual"][0] * (1 - EARLY_ANNUAL_DISCOUNT)))},
            "lapsed_annual": label(la) | {"new_expiry": "test date plus 12 months", "amount": usd(PLANS["Annual"][0])},
            "early_quarterly": label(eq) | {"new_expiry": add_months(eq["expires"], 3).isoformat(), "amount": usd(PLANS["Quarterly"][0])},
        },
        "change_3_cancellation": {"member": label(roles["cancel_request"]), "active_after_approval": len(cur) - 1, "cancelled_after_approval": len(cancelled) + 1},
    }
    write_json(os.path.join(REF_DIR, "counts.json"), counts)
    b = counts["baseline"]
    print(f"members {len(rows)} rows -> {len(members)} (active {len(cur)}, lapsed {len(lapsed)}, cancelled {len(cancelled)}); "
          f"checkins {len(scan_rows)} rows -> {len(visits)} visits, {len(aug)} in August; Jess {b['SCOPE_COUNT']}")


if __name__ == "__main__":
    main()
