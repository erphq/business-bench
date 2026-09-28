#!/usr/bin/env python3
"""plan-change-proration: prorated charges and credits for mid-month plan changes at a studio-scheduling SaaS.

    python gen.py [--seed N] [--naive DIR]
    python gen.py --list-knobs
    python gen.py --scale 3 --rules 3 --cross-doc 1 --out DIR   # a harder task; the answer moves
    python gen.py --describe [--scale N ...]                     # content counts of this draw

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
from bizgen.knobs import Knob, KnobSet, add_knob_args, describe_json, output_dirs, parse_knob_args, record  # noqa: E402

# Difficulty knobs (docs/authoring-knobs.md). The defaults are the published task and leave every draw as it was.
KNOBS = KnobSet(
    Knob("scale", "scale", default=1, levels=(1, 2, 3, 4),
         changes="studios in the accounts export are multiplied by N (24 at 1), the extra ones with their own plan changes",
         measure="rows"),
    Knob("rules", "rules", default=1, levels=(1, 2, 3),
         changes="discount classes in play: 1 is the nonprofit discount only; 2 adds an Education discount (15 percent), "
                 "3 also a Founding discount (10 percent); two studios each, stated in Jonah's note and the accounts export", measure="discount_classes"),
    Knob("cross_doc", "cross-doc", default=0, levels=(0, 1),
         changes="nonprofit status moves out of the accounts export into finance's nonprofit_roster.csv (by studio name, "
                 "with a verified date and a pending entry); only verified studios qualify, from the verified date on",
         measure="documents"),
)
DISC = {"Nonprofit 20%": 0.8, "Education 15%": 0.85, "Founding 10%": 0.9}

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


def knob_content(rk, accounts: list, events: list, change, up, down, staff: list, knobs) -> dict:
    """Knob content from the knob stream `rk`: more studios (scale), more discount classes (rules), the nonprofit
    roster's verified / pending entries (cross_doc). Returns the accounts the task.yaml sentences name."""
    kr = {}
    used = {a["name"] for a in accounts}
    base = len(accounts)
    for i in range(24 * (knobs["scale"] - 1)):
        while (name := f"{rk.choice(PLACES)} {rk.choice(STUDIO_WORDS)}") in used:
            pass
        used.add(name)
        a = {"id": f"ACC-{4100 + (base + i) * 13}", "name": name, "billing": "Annual" if rk.random() < 0.1 else "Monthly",
             "discount": "Nonprofit 20%" if rk.random() < 0.12 else "",
             "plan": rk.choice(["solo", "solo", "studio", "studio", "studio_plus", "multi"])}
        accounts.append(a)
        for off in sorted(rk.sample(range(87), rk.choice([0, 1, 1, 2]))):   # distinct days, so never a same-day undo
            new = up(a["plan"]) if a["plan"] != "multi" and rk.random() < 0.6 else down(a["plan"])
            if new == a["plan"]:
                new = up(a["plan"])
            change(a, date(2026, 2, 2) + timedelta(days=off), rk.randint(8, 18), rk.randint(0, 59), new, by=rk.choice(staff))

    # ordinary monthly studios with no discount; the ones picked below get a change if they had none
    pool = [a for a in accounts[12:24] if a["billing"] == "Monthly" and not a["discount"]]
    rk.shuffle(pool)

    def first_change(a):
        evs = [e for e in events if e["account"] is a]
        if not evs:
            new = up(a["plan"]) if a["plan"] != "multi" else down(a["plan"])
            change(a, date(2026, 2, 2) + timedelta(days=rk.randint(0, 86)), rk.randint(8, 18), rk.randint(0, 59), new,
                   by=rk.choice(staff))
            evs = [events[-1]]
        return evs[0]

    for cls in ["Education 15%", "Founding 10%"][:knobs["rules"] - 1]:
        for _ in range(2):
            a = pool.pop()
            a["discount"] = cls
            first_change(a)
            kr.setdefault(cls, []).append(a)
    if knobs["cross_doc"]:
        z = pool.pop()
        z["discount"] = "Nonprofit 20%"          # a nonprofit only the roster knows about
        first_change(z)
        x = pool.pop()                            # verified only after its change: no discount on it
        x["verified_on"] = local_date(first_change(x)["utc"]) + timedelta(days=rk.randint(3, 20))
        x["roster"] = "Verified"
        y = pool.pop()                            # still pending review: no discount
        first_change(y)
        y["roster"] = "Pending review"
        for a in accounts:
            if a["discount"].startswith("Nonprofit"):
                a["verified_on"] = date(2024, 1, 8) + timedelta(days=rk.randint(0, 640))
                a["roster"] = "Verified"
            if a.get("roster"):
                a["ein"] = f"{rk.randint(10, 99)}-{rk.randint(1000000, 9999999)}"
        kr.update(roster_new=z, roster_late=x, roster_pending=y)
    return kr


def build(seed: int, knobs=KNOBS.defaults()) -> dict:
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
    # knob-only content, drawn from its own stream after every default draw (none of this runs at the defaults)
    knob_roles = {}
    if knobs["scale"] != 1 or knobs["rules"] != 1 or knobs["cross_doc"] != 0:
        knob_roles = knob_content(rng(seed + 7_000_003), accounts, events, change, up, down, staff, knobs)
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
        f = DISC[a["discount"]] if a["discount"] else 1.0
        old_p, new_p = r2(PRICE[e["old"]] * f), r2(PRICE[e["new"]] * f)
        credit = r2(old_p * days / dim)
        charge = r2(new_p * days / dim)
        e.update({"dim": dim, "days": days, "credit": credit, "charge": charge, "amount": r2(charge - credit)})
        out.append(e)
    return {"accounts": accounts, "events": events, "billable": out, "roles": role_acc, "plan_before": plan_before,
            "knob_roles": knob_roles}


def counts(d: dict, knobs) -> dict:
    """--describe: what this draw contains."""
    evs = d["events"]
    classes = {a["discount"] for a in d["accounts"] if a["discount"]}
    return {"rows": len(evs), "entities": len(d["accounts"]), "rules": 6 + len(classes) + knobs["cross_doc"],
            "discount_classes": len(classes), "documents": 4 + knobs["cross_doc"], "billable": len(d["billable"]),
            "trap_instances": {"annual": sum(e["account"]["billing"] == "Annual" for e in evs),
                               "discounted": sum(bool(e["account"]["discount"]) for e in d["billable"]),
                               "reversal": sum(e["account"] is d["roles"]["reversal"] for e in evs),
                               "roster_only": 3 * knobs["cross_doc"]}}


def emit(seed: int, naive_dir: str | None, knobs=KNOBS.defaults(), out: str | None = None) -> None:
    d = build(seed, knobs)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    here, (ws, ref, sol) = output_dirs(HERE, out, task_dirs)
    kr, xdoc = d["knob_roles"], knobs["cross_doc"]
    events, roles = d["events"], d["roles"]

    rows = [[e["id"], e["utc"].strftime("%Y-%m-%dT%H:%M:%SZ"), e["account"]["id"], "plan.changed", e["old"], e["new"], e["by"]] for e in events]
    write_csv(os.path.join(ws, "plan_change_events_2026-02-01_to_2026-04-30.csv"),
              ["event_id", "occurred_at_utc", "account_id", "event_type", "previous_plan", "new_plan", "actor"], rows)
    write_xlsx(os.path.join(ws, "accounts_export_2026-05-02.xlsx"), {"Accounts": {
        "header": ["Account ID", "Studio", "Billing Cycle", "Discount", "Current Plan"],
        "rows": [[a["id"], a["name"], a["billing"], "" if xdoc and a["discount"].startswith("Nonprofit") else a["discount"], dict((c, n) for c, n, _ in PLANS)[a["plan"]]] for a in d["accounts"]],
        "widths": {"B": 30, "C": 14, "D": 16, "E": 14}}}, creator="Tempo Billing")
    write_csv(os.path.join(ws, "price_book_2026.csv"), ["plan_code", "display_name", "monthly_price_usd", "annual_price_usd"],
              [[c, n, f"{p:.2f}", f"{p * 10:.2f}"] for c, n, p in PLANS])
    rules_md = """# Catch-up prorations - how billing works

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
"""
    if not knobs.canonical:   # the knobbed rules, stated where the published note states the nonprofit one
        np_line = "- Nonprofit studios have 20% off their plan, so both prices are 20% lower for them.\n"
        extra = "".join(f"- {c.split()[0]} studios (Discount column \"{c}\") have {c.split()[1]} off their plan, so both prices are "
                        f"{c.split()[1]} lower for them.\n" for c in ["Education 15%", "Founding 10%"][:knobs["rules"] - 1])
        if xdoc:
            np_line = ("- Nonprofit studios have 20% off their plan, so both prices are 20% lower for them. The accounts export no\n"
                       "  longer shows nonprofit status: finance keeps it in nonprofit_roster.csv, by studio name. Only studios\n"
                       "  marked Verified qualify, and only for changes made on or after the date they were verified.\n")
        rules_md = rules_md.replace("- Nonprofit studios have 20% off their plan, so both prices are 20% lower for them.\n", np_line + extra)
    write_text(os.path.join(ws, "proration_rules_from_jonah.md"), rules_md)
    if xdoc:
        ros = sorted((a for a in d["accounts"] if a.get("roster")), key=lambda a: a["name"])
        write_csv(os.path.join(ws, "nonprofit_roster.csv"), ["Studio", "EIN", "Status", "Verified On"],
                  [[a["name"], a["ein"], a["roster"], a["verified_on"].isoformat() if a["roster"] == "Verified" else ""] for a in ros],
                  preamble=["Finance - nonprofit pricing roster (20% off), as of 2026-05-01"])

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
    np_trap = (f"nonprofit studios ({roles['nonprofit_up']['id']}, {roles['nonprofit_down']['id']}) carry 20% off in the accounts "
               "export, which applies to both the credit and the charge (check: proration amounts)")
    more_traps = []
    for cls in ["Education 15%", "Founding 10%"][:knobs["rules"] - 1]:
        more_traps.append(f"{' and '.join(a['id'] for a in kr[cls])} carry {cls} in the accounts export, which Jonah's note applies "
                          "to both the credit and the charge at its own rate, not the nonprofit 20% (check: proration amounts)")
        amount_keys += [e["id"] for a in kr[cls] for e in events if e["account"] is a and e["billable"]]
    if xdoc:
        z, x, y = kr["roster_new"], kr["roster_late"], kr["roster_pending"]
        np_trap = (f"nonprofit status is only on nonprofit_roster.csv, by studio name: {roles['nonprofit_up']['id']}, "
                   f"{roles['nonprofit_down']['id']} and {z['id']} get 20% off both the credit and the charge, {x['id']} was verified "
                   f"only after its change and {y['id']} is still pending, so neither gets it (check: proration amounts)")
        amount_keys += [e["id"] for a in (z, x, y) for e in events if e["account"] is a and e["billable"]]
    spec = {
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
            np_trap,
            *more_traps,
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
    }
    write_task_yaml(here, record(spec, "plan-change-proration", seed, knobs))
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
    add_knob_args(ap, KNOBS)
    a = ap.parse_args()
    knobs = parse_knob_args(a, KNOBS)
    if a.describe:
        print(describe_json("plan-change-proration", a.seed, knobs, counts(build(a.seed, knobs), knobs)))
        raise SystemExit(0)
    emit(a.seed, a.naive, knobs, a.out)
