#!/usr/bin/env python3
"""commission-clawbacks: audit paid commissions against later customer refunds at a hearth and stove retailer.

    python gen.py [--seed N] [--naive DIR]

Business: a fireplace, stove and chimney-liner retailer with commissioned showroom reps. Commissions are paid on
the 15th for the prior month's deals; refunds within 120 days take the commission back. One rep left in July.

Traps (each caught by a check, see task.yaml):
  * the rate is the one paid at the time, from that month's statement: graduated monthly bands, a deal that crossed
    the band has a blended rate, and the plan changed on 1 July                              (check: clawback amounts)
  * partial refunds take back the same share of the commission, and one deal has two            (check: clawback amounts)
  * refunds more than 120 days after the sale take nothing back; day 120 still counts          (check: clawback amounts)
  * the June 15 run already recovered some refunds; one earlier refund was missed and is still due (checks: which refunds; row count)
  * the terminated rep's clawbacks come only out of his held final check, oldest refund first    (checks: recovered; written off)
  * house deals were never commissioned                                                          (check: clawback amounts)
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

MONTHS = [(2026, 3), (2026, 4), (2026, 5), (2026, 6), (2026, 7)]
PLAN_A = (30000.0, 0.04, 0.07)   # through June
PLAN_B = (40000.0, 0.05, 0.08)   # from 1 July
PRODUCTS = ["Wood stove install", "Gas insert install", "Pellet stove", "Chimney liner kit", "Outdoor fireplace", "Electric fireplace wall",
            "Masonry heater consult", "Gas log set", "Hearth pad and venting"]


def r2(x: float) -> float:
    return float(f"{x + (1e-9 if x >= 0 else -1e-9):.2f}")


def build(seed: int) -> dict:
    r = rng(seed)
    names = [f"{f} {l}" for f, l in people(r, 5)]
    reps = [{"name": n, "status": "Active", "term": None} for n in names[:4]]
    derek = {"name": names[4], "status": "Terminated", "term": date(2026, 7, 17)}
    reps.append(derek)
    customers = [f"{f} {l}" for f, l in people(r, 260)]
    deals = []
    seq = 10400
    for (y, m) in MONTHS:
        plan = PLAN_A if (y, m) < (2026, 7) else PLAN_B
        dim = calendar.monthrange(y, m)[1]
        for rep in reps + [{"name": "House", "status": "House"}]:
            if rep is derek and m == 7:
                n = 1
            elif rep.get("status") == "House":
                n = 2
            else:
                n = r.randint(4, 7)
            for k in range(n):
                day = r.randint(1, 16 if (rep is derek and m == 7) else dim)
                amt = float(r.randrange(1800, 14500, 25)) + r.choice([0.0, 0.5, 0.95])
                if rep is derek and m == 7:
                    amt = float(r.randrange(2800, 4200, 25))
                seq += r.randint(1, 9)
                deals.append({"no": f"ES{seq}", "rep": rep["name"], "sold": date(y, m, day), "amount": amt, "plan": plan,
                              "customer": customers.pop(), "product": r.choice(PRODUCTS)})
    # commission per deal, graduated on the rep's cumulative month in sale order
    for (y, m) in MONTHS:
        for rep in reps:
            mine = sorted([d for d in deals if d["rep"] == rep["name"] and (d["sold"].year, d["sold"].month) == (y, m)],
                          key=lambda d: (d["sold"], d["no"]))
            cum = 0.0
            for d in mine:
                band, lo, hi = d["plan"]
                below = max(0.0, min(d["amount"], band - cum))
                above = d["amount"] - below
                d["commission"] = r2(below * lo + above * hi)
                d["rate_label"] = f"{lo:.0%}" if above == 0 else (f"{hi:.0%}" if below == 0 else f"{lo:.0%}/{hi:.0%}")
                d["crossed"] = below > 0 and above > 0
                cum += d["amount"]
    for d in deals:
        if d["rep"] == "House":
            d["commission"], d["rate_label"], d["crossed"] = 0.0, "-", False
    final_check = r2(sum(d["commission"] for d in deals if d["rep"] == derek["name"] and d["sold"].month == 7))
    return {"reps": reps, "derek": derek, "deals": deals, "final_check": final_check, "r": r}


def add_refunds(d: dict, r) -> bool:
    deals, derek = d["deals"], d["derek"]
    refunds = []
    active = [x for x in deals if x["rep"] not in ("House", derek["name"])]

    def mk(deal, when, amount, reason, tag):
        if tag not in ("logged", "missed", "outside_window", "day_120") and when < date(2026, 6, 16):
            when = date(2026, 6, 16) + timedelta(days=r.randint(0, 9))
        refunds.append({"deal": deal, "date": when, "amount": r2(amount), "reason": reason, "tag": tag})

    crossed = [x for x in active if x["crossed"] and x["sold"].month == 5]
    top = [x for x in active if x["rate_label"] == "7%" and x["sold"].month == 5]
    julyb = [x for x in active if x["sold"].month == 7 and x["rate_label"] in ("5%", "8%")]
    if not crossed or not top or not julyb:
        return False
    c = r.choice(crossed)
    mk(c, c["sold"] + timedelta(days=r.randint(40, 80)), c["amount"] * 0.3, "Returned blower kit", "partial_crossed")
    t = r.choice(top)
    mk(t, t["sold"] + timedelta(days=r.randint(30, 70)), t["amount"], "Cancelled install - full refund", "full_top")
    jb = r.choice(julyb)
    mk(jb, jb["sold"] + timedelta(days=r.randint(15, 35)), jb["amount"] * 0.25, "Price adjustment", "plan_b_partial")
    pool = [x for x in active if x not in (c, t, jb) and x["sold"].month == 4 and x["sold"].day <= 20]
    out = r.choice(pool)
    mk(out, out["sold"] + timedelta(days=121 + r.randint(0, 20)), out["amount"] * 0.5, "Warranty goodwill refund", "outside_window")
    edge = r.choice([x for x in pool if x is not out])
    mk(edge, edge["sold"] + timedelta(days=120), edge["amount"] * 0.2, "Hearth pad returned", "day_120")
    two = r.choice([x for x in active if x["sold"].month == 5 and x not in (c, t, jb, out, edge)])
    mk(two, two["sold"] + timedelta(days=20), two["amount"] * 0.15, "Missing trim pieces", "two_partials_1")
    mk(two, refunds[-1]["date"] + timedelta(days=41), two["amount"] * 0.25, "Damaged glass door", "two_partials_2")
    house = [x for x in deals if x["rep"] == "House" and x["sold"].month in (5, 6)]
    h = r.choice(house)
    mk(h, h["sold"] + timedelta(days=25), h["amount"], "Cancelled - full refund", "house")
    # the terminated rep: three refunds on large March-June deals whose clawbacks exceed the held check
    dk = sorted([x for x in deals if x["rep"] == derek["name"] and x["sold"].month in (4, 5, 6)], key=lambda x: -x["commission"])[:3]
    dk.sort(key=lambda x: x["sold"])
    when = [date(2026, 7, 2), date(2026, 7, 29), date(2026, 8, 12)]
    shares = [0.5, 1.0, 0.4]
    for k, (x, w, s) in enumerate(zip(dk, when, shares)):
        if (w - x["sold"]).days > 120 or w <= x["sold"]:
            return False
        mk(x, w, x["amount"] * s, r.choice(["Cancelled install", "Returned unit", "Chimney failed inspection - refund"]), f"derek_{k}")
    # already recovered on the June 15 statement (in the log) and one that was missed
    early = [x for x in active if x["sold"].month in (3, 4) and x not in (c, t, jb, out, edge, two)]
    picks = r.sample(early, 5)
    for k, x in enumerate(picks):
        mk(x, x["sold"] + timedelta(days=r.randint(10, 45)), x["amount"] * r.choice([0.2, 0.5, 1.0]), "Refund", "logged" if k < 4 else "missed")
    for x in r.sample([x for x in active if x not in picks and x not in (c, t, jb, out, edge, two) and x["sold"].month >= 5], 6):
        w = max(x["sold"] + timedelta(days=r.randint(12, 90)), date(2026, 6, 16) + timedelta(days=r.randint(0, 30)))
        if w <= date(2026, 8, 31):
            mk(x, w, x["amount"] * r.choice([0.1, 0.25, 0.4, 1.0]), r.choice(["Refund", "Returned accessory", "Service credit"]), "plain")
    for rf in refunds:
        if rf["tag"] == "logged" and rf["date"] > date(2026, 6, 10):
            rf["date"] = date(2026, 6, 10) - timedelta(days=r.randint(0, 20))
        if rf["tag"] == "missed":
            rf["date"] = min(rf["date"], date(2026, 5, 28))
    refunds = [rf for rf in refunds if rf["date"] <= date(2026, 8, 31) and rf["date"] > rf["deal"]["sold"]]
    for rf in refunds:
        if rf["tag"] not in ("outside_window",) and (rf["date"] - rf["deal"]["sold"]).days > 120:
            return False
    refunds.sort(key=lambda x: (x["date"], x["deal"]["no"]))
    for i, rf in enumerate(refunds):
        rf["id"] = f"RF-{2200 + i * 3}"
    d["refunds"] = refunds

    # truth
    held = d["final_check"]
    for rf in refunds:
        deal = rf["deal"]
        days = (rf["date"] - deal["sold"]).days
        rf["days"] = days
        rf["in_scope"] = rf["tag"] != "logged"
        rf["clawback"] = r2(deal["commission"] * rf["amount"] / deal["amount"]) if days <= 120 else 0.0
        rf["recovered"], rf["written_off"] = rf["clawback"], 0.0
    for rf in [x for x in refunds if x["deal"]["rep"] == derek["name"] and x["in_scope"]]:
        take = min(held, rf["clawback"])
        rf["recovered"], rf["written_off"] = r2(take), r2(rf["clawback"] - take)
        held = r2(held - take)
    dsum = sum(x["clawback"] for x in refunds if x["tag"].startswith("derek"))
    if dsum <= d["final_check"] + 50 or refunds[[x["tag"] for x in refunds].index("derek_0")]["clawback"] >= d["final_check"]:
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    add_refunds(d, d["r"])
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    deals, refunds, derek = d["deals"], d["refunds"], d["derek"]

    sheets = {}
    for (y, m) in MONTHS:
        mine = sorted([x for x in deals if (x["sold"].year, x["sold"].month) == (y, m)], key=lambda x: (x["rep"], x["sold"], x["no"]))
        rows = [[x["rep"], x["no"], x["customer"], x["sold"], x["product"], x["amount"], x["rate_label"], x["commission"]] for x in mine]
        paid = date(y + (m == 12), m % 12 + 1, 15)
        sheets[f"{calendar.month_abbr[m]} {y}"] = {
            "merged_title": f"Commission statement - {calendar.month_name[m]} {y} deals (paid {paid.strftime('%b %d, %Y')})",
            "header": ["Rep", "Deal", "Customer", "Sale Date", "Product", "Deal Amount", "Rate", "Commission"],
            "rows": rows, "number_formats": {"F": "#,##0.00", "H": "#,##0.00"}, "widths": {"A": 18, "C": 20, "E": 24}}
    write_xlsx(os.path.join(ws, "commission_statements_mar-jul_2026.xlsx"), sheets, creator="Emberline Payroll")

    rrows = [[rf["id"], rf["date"].strftime("%m/%d/%Y"), rf["deal"]["no"].replace("ES", "ES-"), rf["deal"]["customer"], money_str(rf["amount"], 1), rf["reason"]]
             for rf in refunds]
    write_csv(os.path.join(ws, "refunds_export_2026-04-01_to_2026-08-31.csv"), ["Refund #", "Refund Date", "Sales Order", "Customer", "Refund Amount", "Reason"],
              rrows, preamble=["Emberline Hearth & Stove - customer refunds", "Printed 09/02/2026"])
    logged = [rf for rf in refunds if rf["tag"] == "logged"]
    write_csv(os.path.join(ws, "clawbacks_taken_on_2026-06-15_statement.csv"), ["Rep", "Refund #", "Sales Order", "Clawback"],
              [[rf["deal"]["rep"], rf["id"], rf["deal"]["no"], f"{rf['clawback']:.2f}"] for rf in logged])
    write_csv(os.path.join(ws, "sales_reps.csv"), ["Rep", "Status", "Termination Date", "Note"],
              [[x["name"], x["status"], x["term"].isoformat() if x["term"] else "", "" if not x["term"] else
                f"July commission check of ${d['final_check']:,.2f} is being held; it is the only money we can still recover clawbacks from"]
               for x in d["reps"]] + [["House", "House account", "", "Owner-sold deals, no commission"]])
    write_text(os.path.join(ws, "commission_plan_2026_H2.md"), f"""# Emberline showroom commission plan - effective July 1, 2026

Commission is paid on the 15th of the month for the prior month's delivered deals.

## Rates

Graduated on each rep's total deals for the month, in the order they were sold: every dollar earns the rate of the
band it falls in.

| Monthly deal total | Rate |
|---|---|
| First $40,000 | 5% |
| Above $40,000 | 8% |

(Until June 30 the bands were 4% on the first $30,000 and 7% above. Statements show what was actually paid.)

## Refunds and clawbacks

1. If a customer is refunded within 120 days of the sale date (day 120 counts), the commission paid on that deal
   is taken back in the same proportion as the refund: a 30% refund takes back 30% of that deal's commission. Use
   the commission actually paid on the statement, round each clawback to the cent.
2. Refunds after 120 days take nothing back.
3. Clawbacks come off the rep's next commission check. Anything already taken on an earlier statement is not taken again.
4. When a rep has left, clawbacks can only come out of commission we still owe them. Apply their refunds oldest first
   until that money runs out; the rest is written off.
5. House deals carry no commission.
""")
    write_text(os.path.join(ws, "note_from_colleen.txt"), """We have not run clawbacks since the June 15 statement. Can you go through every refund that is not already
on that statement's clawback list and tell me what we take back? One line per refund in clawbacks.csv:
refund_id, rep, clawback, recovered, written_off. Put a line in even when the clawback comes to zero.

- Colleen
""")

    scope = [rf for rf in refunds if rf["in_scope"]]
    header = ["refund_id", "rep", "clawback", "recovered", "written_off"]
    out = [[rf["id"], rf["deal"]["rep"], f"{rf['clawback']:.2f}", f"{rf['recovered']:.2f}", f"{rf['written_off']:.2f}"] for rf in scope]
    write_csv(os.path.join(ref, "clawbacks.csv"), header, out)
    write_csv(os.path.join(sol, "clawbacks.csv"), header, out)
    write_json(os.path.join(ref, "notes.json"), {"final_check": d["final_check"], "refunds": [
        {"id": rf["id"], "tag": rf["tag"], "deal": rf["deal"]["no"], "sold": rf["deal"]["sold"].isoformat(), "refund_date": rf["date"].isoformat(),
         "days": rf["days"], "deal_amount": rf["deal"]["amount"], "commission": rf["deal"]["commission"], "rate": rf["deal"]["rate_label"],
         "refund": rf["amount"], "clawback": rf["clawback"], "recovered": rf["recovered"], "written_off": rf["written_off"]} for rf in refunds]})
    tg = {}
    for rf in refunds:
        tg.setdefault(rf["tag"], rf)
    rid = lambda t: tg[t]["id"]
    dk = [rf["id"] for rf in scope if rf["tag"].startswith("derek")]
    write_task_yaml(HERE, {
        "id": "commission-clawbacks", "track": "desk", "category": "bookkeeping",
        "title": "Commission clawbacks on refunded deals since June",
        "ask": ("We haven't taken back any commissions for refunds since the June 15 statement. Colleen's note says what she needs, "
                "and the statements, refunds and plan are all in the folder. Save it as clawbacks.csv.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            f"the rate is what the statement paid, not the plan document's current bands: {rid('full_top')} was paid at 7% under the old "
            f"plan, {rid('partial_crossed')}'s deal crossed the monthly band and carries a blended 4%/7% commission, and "
            f"{rid('plan_b_partial')} is a July deal under the new bands (check: clawback amounts)",
            f"partial refunds take back the same share of that deal's commission; {rid('two_partials_1')} and {rid('two_partials_2')} "
            "are two partial refunds on one deal (check: clawback amounts)",
            f"{rid('outside_window')} came more than 120 days after the sale and takes nothing back, while {rid('day_120')} lands on "
            "day 120 and still counts (check: clawback amounts)",
            f"four refunds are already on the June 15 clawback list and must not be taken twice, but {rid('missed')} from "
            f"{tg['missed']['date'].strftime('%-d %B')} was missed and is still due although it predates the list (checks: which refunds; row count)",
            f"{derek['name']} left on 17 July; his clawbacks ({', '.join(dk)}) come only out of the held ${d['final_check']:,.2f} "
            "check, oldest refund first, and the rest is written off (checks: recovered from the rep; written off)",
            f"{rid('house')} refunds a house deal that never paid commission (check: clawback amounts)",
            "the refund export writes sales orders as ES-10452 where the statements say ES10452, under a two-line preamble "
            "(check: clawback amounts)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "clawbacks.csv", "columns": header},
            {"type": "csv_set_equal", "name": "which refunds", "path": "clawbacks.csv", "column": "refund_id", "ref": "clawbacks.csv", "normalize": ["alnum"]},
            {"type": "csv_row_count", "name": "row count", "path": "clawbacks.csv", "equals_ref": "clawbacks.csv"},
            {"type": "csv_values_match", "name": "clawback amounts", "path": "clawbacks.csv", "ref": "clawbacks.csv", "key": "refund_id",
             "columns": ["clawback"], "numeric": True, "tolerance": 0.011, "min_accuracy": 1.0,
             "must_match_keys": [rid(t) for t in ("full_top", "partial_crossed", "plan_b_partial", "two_partials_1", "two_partials_2",
                                                  "outside_window", "day_120", "house", "missed")]},
            {"type": "csv_values_match", "name": "recovered from the rep", "path": "clawbacks.csv", "ref": "clawbacks.csv", "key": "refund_id",
             "columns": ["recovered"], "numeric": True, "tolerance": 0.011, "min_accuracy": 1.0, "must_match_keys": dk},
            {"type": "csv_values_match", "name": "written off", "path": "clawbacks.csv", "ref": "clawbacks.csv", "key": "refund_id",
             "columns": ["written_off"], "numeric": True, "tolerance": 0.011, "min_accuracy": 1.0, "must_match_keys": dk},
        ],
    })
    print(f"seed={seed} deals={len(deals)} refunds={len(refunds)} in scope={len(scope)} final check={d['final_check']}")
    for rf in refunds:
        x = rf["deal"]
        print(f"  {rf['id']} {rf['tag']:15} {x['rep'][:14]:14} {x['no']} sold={x['sold']} +{rf['days']:3}d amt={x['amount']:>9.2f} {x['rate_label']:6} "
              f"comm={x['commission']:>7.2f} refund={rf['amount']:>9.2f} claw={rf['clawback']:>7.2f} rec={rf['recovered']:>7.2f} wo={rf['written_off']:.2f}")


def write_naive(d: dict, out: str) -> None:
    """Every refund in the export, clawback = refund x the current plan's 5% rate, no window, everyone recovers in full."""
    os.makedirs(out, exist_ok=True)
    rows = [[rf["id"], rf["deal"]["rep"], f"{rf['amount'] * 0.05:.2f}", f"{rf['amount'] * 0.05:.2f}", "0.00"] for rf in d["refunds"]]
    write_csv(os.path.join(out, "clawbacks.csv"), ["refund_id", "rep", "clawback", "recovered", "written_off"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if add_refunds(d_, d_["r"]):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
