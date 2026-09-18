#!/usr/bin/env python3
"""plan-change-proration: prorated charges and credits for mid-month plan changes at a studio-scheduling SaaS.

    python gen.py [--seed N] [--naive DIR]

Business: a small software company selling class-scheduling software to dance and yoga studios on monthly and
annual plans. The billing sync broke in February, so three months of plan changes were never prorated.

Traps (each caught by a check, see task.yaml):
  * days in the month are calendar days (28, 31, 30), counted from the change date to month end inclusive
                                                                                     (checks: days prorated; amounts)
  * the proration is the new plan for the remaining days less the unused old plan; downgrades are credits (check: amounts)
  * a change undone the same day is not a change                                    (checks: which changes; row count)
  * the log is in UTC and the billing day is Pacific time: a change logged early 1 April UTC was made 31 March
                                                                                     (checks: days prorated; amounts)
  * two upgrades for one studio in the same month: the second starts from the plan the first put it on (check: amounts)
  * nonprofit studios pay 20% less on both sides of the proration                     (check: amounts)
  * annual-billed studios are prorated at renewal by the account team, not here       (checks: which changes; row count)
"""
from __future__ import annotations
import argparse
import calendar
import os
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

PLANS = [("solo", "Solo", 39.00), ("studio", "Studio", 119.00), ("studio_plus", "Studio Plus", 189.00), ("multi", "Multi-site", 289.00)]
PRICE = {c: p for c, _, p in PLANS}
ORDER = [c for c, _, _ in PLANS]
STUDIO_WORDS = ["Dance Academy", "Yoga Loft", "Pilates Studio", "Ballet School", "Movement Collective", "Barre Studio",
                "Martial Arts Dojo", "Aerial Arts", "Hot Yoga", "Tap & Jazz Studio", "Climbing Club", "Swim School"]
PLACES = ["Juniper", "Copperline", "Northgate", "Willow Creek", "Harbor", "Sagebrush", "Maple Row", "Bluebird", "Cedar Hill",
          "Lakeshore", "Foxglove", "Riverside", "Ironbridge", "Sunset", "Meadowbrook", "Stonegate", "Larkspur", "Pinecrest",
          "Seabright", "Alder", "Thornbury", "Kestrel", "Oakmont", "Brightwater"]


def pacific_offset(dt_utc: datetime) -> timedelta:
    """US Pacific: PDT (UTC-7) from 2026-03-08 10:00 UTC to 2026-11-01 09:00 UTC, else PST (UTC-8)."""
    start, end = datetime(2026, 3, 8, 10, 0), datetime(2026, 11, 1, 9, 0)
    return timedelta(hours=-7) if start <= dt_utc < end else timedelta(hours=-8)


def local_date(dt_utc: datetime) -> date:
    return (dt_utc + pacific_offset(dt_utc)).date()


def r2(x: float) -> float:
    return float(f"{x + (1e-9 if x >= 0 else -1e-9):.2f}")


def build(seed: int) -> dict:
    r = rng(seed)
    names = [f"{p} {w}" for p, w in zip(r.sample(PLACES, 24), [r.choice(STUDIO_WORDS) for _ in range(24)])]
    accounts = []
    for i, n in enumerate(names):
        accounts.append({"id": f"ACC-{4100 + i * 13}", "name": n, "billing": "Monthly", "discount": "",
                         "plan": r.choice(["solo", "solo", "studio", "studio", "studio_plus", "multi"])})
    acc = {a["id"]: a for a in accounts}
    # fixed roles
    roles = ["feb_upgrade", "feb_downgrade", "utc_boundary", "double_1", "reversal", "nonprofit_up", "annual", "annual_2",
             "apr_up", "apr_down", "mar_up", "nonprofit_down"]
    role_acc = {role: accounts[i] for i, role in enumerate(roles)}
    role_acc["nonprofit_up"]["discount"] = "Nonprofit 20%"
    role_acc["nonprofit_down"]["discount"] = "Nonprofit 20%"
    accounts[15]["discount"] = "Nonprofit 20%"
    role_acc["annual"]["billing"] = "Annual"
    role_acc["annual_2"]["billing"] = "Annual"
    accounts[18]["billing"] = "Annual"

    def up(code, k=1):
        return ORDER[min(ORDER.index(code) + k, len(ORDER) - 1)]

    def down(code):
        return ORDER[max(ORDER.index(code) - 1, 0)]

    for role in ("feb_upgrade", "utc_boundary", "double_1", "reversal", "nonprofit_up", "apr_up", "mar_up", "annual"):
        role_acc[role]["plan"] = r.choice(["solo", "studio"])
    for role in ("feb_downgrade", "apr_down", "nonprofit_down", "annual_2"):
        role_acc[role]["plan"] = r.choice(["studio_plus", "multi"])

    def utc(local_day: date, hh: int, mm: int) -> datetime:
        naive = datetime(local_day.year, local_day.month, local_day.day, hh, mm)
        off = timedelta(hours=-8)
        guess = naive - off
        off = pacific_offset(guess)
        return naive - off

    events = []   # {id, utc, account, old, new, by}
    staff = ["jonah.b", "support-bot", "maria.l", "self-serve"]

    def change(a, day, hh, mm, new, by=None):
        events.append({"utc": utc(day, hh, mm), "account": a, "old": a["plan"], "new": new, "by": by or r.choice(staff)})
        a["plan"] = new

    plan_before = {a["id"]: a["plan"] for a in accounts}
    change(role_acc["feb_upgrade"], date(2026, 2, 11), 10, 5, up(role_acc["feb_upgrade"]["plan"], 2))
    change(role_acc["feb_downgrade"], date(2026, 2, 17), 15, 40, down(role_acc["feb_downgrade"]["plan"]))
    change(role_acc["nonprofit_up"], date(2026, 2, 23), 9, 12, up(role_acc["nonprofit_up"]["plan"]))
    change(role_acc["annual"], date(2026, 2, 19), 11, 30, up(role_acc["annual"]["plan"]))
    change(role_acc["double_1"], date(2026, 3, 4), 13, 22, up(role_acc["double_1"]["plan"]))
    change(role_acc["mar_up"], date(2026, 3, 9), 16, 48, up(role_acc["mar_up"]["plan"], 2))
    a = role_acc["reversal"]; orig = a["plan"]
    change(a, date(2026, 3, 12), 14, 2, up(orig, 2), by="self-serve")
    change(a, date(2026, 3, 12), 14, 19, orig, by="maria.l")
    change(role_acc["double_1"], date(2026, 3, 19), 10, 51, up(role_acc["double_1"]["plan"]))
    change(role_acc["nonprofit_down"], date(2026, 3, 24), 12, 3, down(role_acc["nonprofit_down"]["plan"]))
    change(role_acc["utc_boundary"], date(2026, 3, 31), 22, 40, up(role_acc["utc_boundary"]["plan"]))
    change(role_acc["annual_2"], date(2026, 4, 8), 9, 0, down(role_acc["annual_2"]["plan"]))
    change(role_acc["apr_up"], date(2026, 4, 14), 17, 25, up(role_acc["apr_up"]["plan"]))
    change(role_acc["apr_down"], date(2026, 4, 27), 8, 44, down(role_acc["apr_down"]["plan"]))
    # a handful of ordinary changes on other monthly accounts
    others = [x for x in accounts[12:] if x["billing"] == "Monthly"]
    for x in r.sample(others, 6):
        day = date(2026, 2, 2) + timedelta(days=r.randint(0, 86))
        new = up(x["plan"]) if x["plan"] != "multi" and r.random() < 0.6 else down(x["plan"])
        if new == x["plan"]:
            new = up(x["plan"])
        change(x, day, r.randint(8, 18), r.randint(0, 59), new)
    events.sort(key=lambda e: e["utc"])
    for i, e in enumerate(events):
        e["id"] = f"PC-{30210 + i * 7}"

    # truth
    rev_ids = {e["id"] for e in events if e["account"] is role_acc["reversal"]}
    out = []
    for e in events:
        a = e["account"]
        e["local"] = local_date(e["utc"])
        if a["billing"] == "Annual" or e["id"] in rev_ids:
            e["billable"] = False
            continue
        e["billable"] = True
        dim = calendar.monthrange(e["local"].year, e["local"].month)[1]
        days = dim - e["local"].day + 1
        f = 0.8 if a["discount"] else 1.0
        old_p, new_p = r2(PRICE[e["old"]] * f), r2(PRICE[e["new"]] * f)
        credit = r2(old_p * days / dim)
        charge = r2(new_p * days / dim)
        e.update({"dim": dim, "days": days, "credit": credit, "charge": charge, "amount": r2(charge - credit)})
        out.append(e)
    return {"accounts": accounts, "events": events, "billable": out, "roles": role_acc, "plan_before": plan_before}


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    events, roles = d["events"], d["roles"]

    rows = [[e["id"], e["utc"].strftime("%Y-%m-%dT%H:%M:%SZ"), e["account"]["id"], "plan.changed", e["old"], e["new"], e["by"]] for e in events]
    write_csv(os.path.join(ws, "plan_change_events_2026-02-01_to_2026-04-30.csv"),
              ["event_id", "occurred_at_utc", "account_id", "event_type", "previous_plan", "new_plan", "actor"], rows)
    write_xlsx(os.path.join(ws, "accounts_export_2026-05-02.xlsx"), {"Accounts": {
        "header": ["Account ID", "Studio", "Billing Cycle", "Discount", "Current Plan"],
        "rows": [[a["id"], a["name"], a["billing"], a["discount"], dict((c, n) for c, n, _ in PLANS)[a["plan"]]] for a in d["accounts"]],
        "widths": {"B": 30, "C": 14, "D": 16, "E": 14}}}, creator="Tempo Billing")
    write_csv(os.path.join(ws, "price_book_2026.csv"), ["plan_code", "display_name", "monthly_price_usd", "annual_price_usd"],
              [[c, n, f"{p:.2f}", f"{p * 10:.2f}"] for c, n, p in PLANS])
    write_text(os.path.join(ws, "proration_rules_from_jonah.md"), """# Catch-up prorations - how billing works

The billing sync stopped posting prorations on February 1, so none of the plan changes since then were charged or
credited. We are fixing it on the May invoices.

**How a mid-month change is prorated**

- Monthly plans bill on the 1st for the whole month, in advance.
- A change takes effect on the day it is made, and that day is on the new plan. The proration covers the days from
  the change date to the last day of that month, counting both.
- Use the real number of days in that month.
- The studio gets back the unused part of the old plan and pays for the same days on the new plan:
  credit = old monthly price x days / days in month, charge = new monthly price x days / days in month, each rounded to
  the cent; the proration is charge minus credit. A downgrade gives a negative number (a credit on the next invoice).
- Nonprofit studios have 20% off their plan, so both prices are 20% lower for them.
- If a studio changes plan twice in a month, each change is prorated on its own from its own date.

**What to leave out**

- A change that is undone on the same day (someone clicks the wrong plan and support switches it back) is not a
  change. Leave both events out.
- Annual-billed studios are prorated at renewal by the account team. Leave them out of this.

**Dates**

The event log is in UTC. Our billing day is Pacific time, so convert before you decide which day a change happened.

**What I need**

prorations.csv with one line per change: change_id (the event id), account_id, effective_date, days (the days
prorated) and proration.

- Jonah
""")

    header = ["change_id", "account_id", "effective_date", "days", "proration"]
    out = [[e["id"], e["account"]["id"], e["local"].isoformat(), e["days"], f"{e['amount']:.2f}"] for e in d["billable"]]
    write_csv(os.path.join(ref, "prorations.csv"), header, out)
    write_csv(os.path.join(sol, "prorations.csv"), header, out)
    write_json(os.path.join(ref, "notes.json"), [{k: (v if not isinstance(v, (date, datetime, dict)) else (v["id"] if isinstance(v, dict) else v.isoformat()))
                                                  for k, v in e.items()} for e in events])

    def ev(role, n=0):
        return [e for e in events if e["account"] is roles[role]][n]
    utc_e = ev("utc_boundary")
    rev = [e["id"] for e in events if e["account"] is roles["reversal"]]
    annual = [e["id"] for e in events if e["account"]["billing"] == "Annual"]
    rounding = "day-based proration, charge and credit each rounded to the cent as Jonah's note states"
    amount_keys = [ev("feb_upgrade")["id"], ev("feb_downgrade")["id"], utc_e["id"], ev("double_1", 0)["id"], ev("double_1", 1)["id"],
                   ev("nonprofit_up")["id"], ev("nonprofit_down")["id"], ev("apr_up")["id"]]
    write_task_yaml(HERE, {
        "id": "plan-change-proration", "track": "desk", "category": "bookkeeping",
        "title": "Catch-up prorations for February to April plan changes",
        "ask": ("The billing sync never charged or credited any plan changes since February. Work out the prorations for "
                "everything in the change log following Jonah's rules and save them as prorations.csv so we can put them on the May invoices.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"months have 28, 31 and 30 days and the day of the change counts: {ev('feb_upgrade')['id']} on 11 February prorates "
            "18 of 28 days, so a 30-day month or an exclusive count moves every line (checks: days prorated; proration amounts)",
            f"a proration is the new plan for the remaining days less the unused old plan, so charging the new price alone overbills "
            f"upgrades and downgrades such as {ev('feb_downgrade')['id']} come out negative (check: proration amounts)",
            f"{rev[0]} and {rev[1]} move one studio up two plans and back 17 minutes later on the same day; neither is a change "
            "(checks: which changes; row count)",
            f"the log is UTC and billing days are Pacific: {utc_e['id']} is stamped {utc_e['utc'].strftime('%Y-%m-%d %H:%M')} UTC but "
            "was made at 10:40 pm on 31 March, so it prorates one day of March rather than all of April "
            "(checks: days prorated; proration amounts)",
            f"{ev('double_1', 0)['id']} and {ev('double_1', 1)['id']} upgrade one studio twice in March; the second change's credit "
            "is for the plan the first one put it on, not the plan it started the month on (check: proration amounts)",
            f"nonprofit studios ({roles['nonprofit_up']['id']}, {roles['nonprofit_down']['id']}) carry 20% off in the accounts "
            "export, which applies to both the credit and the charge (check: proration amounts)",
            f"the change log also holds {len(annual)} changes on annual-billed studios, which the account team prorates at renewal "
            "(checks: which changes; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "prorations.csv", "columns": header},
            {"type": "csv_set_equal", "name": "which changes", "path": "prorations.csv", "column": "change_id", "ref": "prorations.csv",
             "normalize": ["alnum"]},
            {"type": "csv_row_count", "name": "row count", "path": "prorations.csv", "equals_ref": "prorations.csv"},
            {"type": "csv_values_match", "name": "days prorated", "path": "prorations.csv", "ref": "prorations.csv", "key": "change_id",
             "columns": ["days"], "numeric": True, "tolerance": 0.0, "min_accuracy": 1.0,
             "must_match_keys": [ev("feb_upgrade")["id"], utc_e["id"], ev("apr_down")["id"]]},
            {"type": "csv_values_match", "name": "proration amounts", "path": "prorations.csv", "ref": "prorations.csv", "key": "change_id",
             "columns": ["proration"], "numeric": True, "tolerance": 0.011, "rounding": rounding, "min_accuracy": 1.0,
             "must_match_keys": amount_keys},
        ],
    })
    print(f"seed={seed} events={len(events)} billable={len(d['billable'])}")
    for e in events:
        a = e["account"]
        print(f"  {e['id']} {e['utc']:%m-%d %H:%M}Z local={e['local']} {a['id']} {a['billing']:7} {a['discount'] or '-':13} {e['old']:>11}->{e['new']:<11}"
              + (f" days={e['days']}/{e['dim']} amt={e['amount']}" if e["billable"] else " (out)"))


def write_naive(d: dict, out: str) -> None:
    """Every event, UTC date, 30-day month, (new - old) list price x remaining / 30."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for e in d["events"]:
        day = e["utc"].date()
        days = 30 - day.day + 1
        rows.append([e["id"], e["account"]["id"], day.isoformat(), max(days, 1), f"{(PRICE[e['new']] - PRICE[e['old']]) * days / 30:.2f}"])
    write_csv(os.path.join(out, "prorations.csv"), ["change_id", "account_id", "effective_date", "days", "proration"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, a.naive)
