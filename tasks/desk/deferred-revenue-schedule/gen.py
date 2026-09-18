#!/usr/bin/env python3
"""deferred-revenue-schedule: annual dispatch-software plans to a 2026 deferred revenue roll-forward.

    python gen.py [--seed N] [--naive DIR]

Business: Tallgrass Dispatch sells dispatch and invoicing software to towing companies. Most customers prepay a
year; a few pay month to month. The outside CPA wants the 2026 deferred revenue schedule for the year-end file and
his email carries the method: one twelfth a month, a 15th-of-the-month start rule, upgrade add-ons over the months
left, cancellations with a refund less a kept $250 fee, and deferred revenue as everything invoiced and not earned.

Traps (each caught by a check, see task.yaml):
  * a plan starting after the 15th earns from the next month                      (check: late-start contract)
  * a plan started in late 2025 is mid-term on 1 January; only its 2026 months count (check: carried-over contract)
  * a mid-term upgrade's add-on is earned over the months left in the term         (check: upgraded contract)
  * a cancellation stops recognition, the refund leaves deferred revenue and the
    kept $250 fee is revenue in the cancellation month                             (check: cancelled contract)
  * a renewal invoiced in December for a January start earns nothing in 2026 but
    sits in the year-end deferred balance                                          (check: deferred balance)
  * a quote and two monthly-billed customers sit in the export                     (checks: total recognized; deferred)
  * fees are text with a dollar sign, the export has a title and a preamble row    (check: total recognized)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from openpyxl.utils import get_column_letter  # noqa: E402

FY = 2026
CANCEL_FEE = 25000  # cents
MONTHS = [(FY, m) for m in range(1, 13)]
LABELS = [f"{FY}-{m:02d}" for m in range(1, 13)]
TOWING = ["Ace Towing & Recovery", "Blue Line Wrecker Service", "Big Sky Heavy Tow", "Crossroads Roadside", "Dixon Brothers Towing",
          "Eastgate Auto Recovery", "Frontier Flatbed Co", "Gateway Tow & Transport", "Hilltop Wrecker", "Interstate Recovery Group",
          "Jensen Towing", "Keystone Roadside Assist", "Lone Pine Towing", "Metro Impound Services", "Northstar Heavy Wreck",
          "Old Mill Auto Tow", "Pioneer Tow Line", "Quick Hook Towing", "Redline Recovery", "Summit Wrecker & Salvage",
          "Tri-County Towing", "Valley Flatbed Service", "Westside Tow & Storage", "Yellow Jacket Towing"]
PLANS = [("Solo", 99), ("Fleet 5", 249), ("Fleet 15", 499), ("Fleet 40", 899), ("Unlimited", 1499)]
PLAN_RATE = dict(PLANS)
UPGRADE_TO = {"Solo": "Fleet 5", "Fleet 5": "Fleet 15", "Fleet 15": "Fleet 40", "Fleet 40": "Unlimited"}


def midx(y: int, m: int) -> int:
    return y * 12 + m - 1


def ym(i: int) -> tuple[int, int]:
    return i // 12, i % 12 + 1


def first_earning_month(d: date) -> int:
    return midx(d.year, d.month) + (0 if d.day <= 15 else 1)


def build(seed: int) -> dict:
    r = rng(seed)
    names = r.sample(TOWING, 21)
    ids = [f"TD-{n}" for n in sorted(r.sample(range(2040, 2140), 21))]
    r.shuffle(ids)
    contracts = []

    def new(role, start, plan, billing="Annual", status="Active", invoice_date=None):
        c = {"id": ids[len(contracts)], "customer": names[len(contracts)], "role": role, "plan": plan, "billing": billing,
             "start": start, "monthly": PLAN_RATE[plan] * 100, "status": status, "invoice_date": invoice_date or start,
             "invoice": f"INV-{r.randint(10000, 19999)}", "changes": []}
        c["fee"] = c["monthly"] * 12
        contracts.append(c)
        return c

    carry_a = new("carry_a", date(2025, 9, r.randint(2, 15)), r.choice(PLANS[1:4])[0])
    carry = new("carry", date(2025, 11, r.randint(17, 28)), r.choice(PLANS[1:4])[0])
    late = new("late", date(2026, r.choice([3, 4, 5]), r.randint(17, 28)), r.choice(PLANS[1:])[0])
    up = new("upgrade", date(2026, r.choice([4, 5]), r.randint(2, 14)), r.choice(["Fleet 5", "Fleet 15"]))
    can = new("cancel", date(2026, r.choice([1, 2, 3]), r.randint(2, 14)), r.choice(["Fleet 15", "Fleet 40", "Unlimited"]))
    expiring = new("expiring", date(2026, 1, r.randint(2, 12)), r.choice(PLANS[1:4])[0])
    for _ in range(9):
        new("plain", day_in(r, date(2026, 1, 5), date(2026, 11, 26), weekday_only=True), r.choice(PLANS)[0])
    new("plain25", date(2025, 12, r.randint(1, 12)), r.choice(PLANS[:3])[0])
    renewal = new("renewal", date(2027, 1, 1), expiring["plan"], status="Active - renewal",
                  invoice_date=date(2026, 12, r.randint(10, 18)))
    renewal["customer"] = expiring["customer"]
    quote = new("quote", date(2026, 11, 1), r.choice(PLANS[2:])[0], status="Quote - not signed")
    quote["invoice"] = ""; quote["invoice_date"] = None
    for _ in range(2):
        mo = new("monthly", day_in(r, date(2026, 2, 1), date(2026, 7, 28)), r.choice(PLANS[:3])[0], billing="Monthly")
        mo["invoice"] = "monthly"; mo["invoice_date"] = None

    # ---- changes: an upgrade, a cancellation, a no-charge seat change
    up_date = date(2026, r.choice([8, 9]), r.randint(3, 27))
    new_plan = UPGRADE_TO[up["plan"]]
    term_end = first_earning_month(up["start"]) + 11
    u0 = first_earning_month(up_date)
    left = term_end - u0 + 1
    diff = PLAN_RATE[new_plan] * 100 - up["monthly"]
    up["changes"].append({"date": up_date, "type": "Upgrade", "amount": diff * left, "left": left, "new_plan": new_plan, "diff": diff})
    can_date = date(2026, r.choice([8, 9, 10]), r.randint(3, 27))
    last = midx(can_date.year, can_date.month) - (1 if can_date.day <= 15 else 0)
    earned_months = last - first_earning_month(can["start"]) + 1
    refund = (12 - earned_months) * can["monthly"] - CANCEL_FEE
    can["changes"].append({"date": can_date, "type": "Cancel", "amount": refund, "last": last, "earned_months": earned_months})
    can["status"] = f"Cancelled {can_date.strftime('%m/%d/%Y')}"
    seat = r.choice([c for c in contracts if c["role"] == "plain"])
    seat["changes"].append({"date": date(2026, r.choice([5, 6, 7]), r.randint(2, 26)), "type": "Seats", "amount": 0})
    for c in contracts:
        if c["billing"] == "Annual" and c["status"] == "Active" and first_earning_month(c["start"]) + 11 < midx(FY + 1, 1):
            c["status"] = "Renewed" if c is expiring else "Ended"

    # ---- truth, in cents
    rows = []
    y0, y1 = midx(FY, 1), midx(FY, 12)
    opening = 0
    invoiced = [0] * 12
    refunded = [0] * 12
    for c in contracts:
        if c["role"] in ("quote", "monthly"):
            continue
        f0 = first_earning_month(c["start"])
        sched = {f0 + k: c["monthly"] for k in range(12)}
        addon = refund_amt = 0
        for ch in c["changes"]:
            if ch["type"] == "Upgrade":
                for k in range(first_earning_month(ch["date"]), f0 + 12):
                    sched[k] += ch["diff"]
                addon = ch["amount"]
                invoiced[ch["date"].month - 1] += addon
            elif ch["type"] == "Cancel":
                for k in list(sched):
                    if k > ch["last"]:
                        sched[k] = 0
                cm = midx(ch["date"].year, ch["date"].month)
                sched[cm] = sched.get(cm, 0) + CANCEL_FEE
                refund_amt = ch["amount"]
                refunded[ch["date"].month - 1] += refund_amt
        before = sum(v for k, v in sched.items() if k < y0)
        fy = [sched.get(k, 0) for k in range(y0, y1 + 1)]
        inv = c["invoice_date"]
        if inv.year < FY:
            opening += c["fee"] - before
        elif inv.year == FY:
            invoiced[inv.month - 1] += c["fee"]
        deferred = c["fee"] + addon - refund_amt - before - sum(fy)
        assert deferred >= 0, (c["id"], deferred)
        rows.append({"c": c, "before": before, "fy": fy, "total": sum(fy), "addon": addon, "refund": refund_amt, "deferred": deferred})
    recognized = [sum(rw["fy"][i] for rw in rows) for i in range(12)]
    closing, bal = [], opening
    openings = []
    for i in range(12):
        openings.append(bal)
        bal = bal + invoiced[i] - refunded[i] - recognized[i]
        closing.append(bal)
    deferred_total = sum(rw["deferred"] for rw in rows)
    assert closing[-1] == deferred_total, (closing[-1], deferred_total)
    rows.sort(key=lambda rw: rw["c"]["id"])
    return {"contracts": contracts, "rows": rows, "recognized": recognized, "invoiced": invoiced, "refunded": refunded,
            "openings": openings, "closing": closing, "opening": opening, "grand": sum(recognized), "deferred_total": deferred_total,
            "roles": {c["role"]: c for c in contracts if c["role"] not in ("plain", "monthly")}}


# --------------------------------------------------------------------------- the shortcut

def naive_rows(d: dict) -> list[dict]:
    """Every row in the export, the start month always counts, the change log ignored."""
    out = []
    for c in d["contracts"]:
        f0 = midx(c["start"].year, c["start"].month)
        sched = {f0 + k: c["monthly"] for k in range(12)}
        before = sum(v for k, v in sched.items() if k < midx(FY, 1))
        fy = [sched.get(midx(FY, 1) + i, 0) for i in range(12)]
        out.append({"c": c, "before": before, "fy": fy, "total": sum(fy), "addon": 0, "refund": 0,
                    "deferred": c["fee"] - before - sum(fy)})
    return out


def acceptable(d: dict) -> bool:
    by = {rw["c"]["id"]: rw for rw in d["rows"]}
    nv = {rw["c"]["id"]: rw for rw in naive_rows(d)}
    for role in ("late", "carry", "upgrade", "cancel"):
        c = d["roles"][role]
        rw = by[c["id"]]
        t = rw["total"]
        others = [c["fee"], c["monthly"], rw["addon"], rw["refund"], rw["before"], rw["deferred"], c["monthly"] * 12] + rw["fy"]
        if any(abs(t - o) <= 100 for o in others):
            return False
        if abs(nv[c["id"]]["total"] - t) < 1000:
            return False
    if abs(sum(rw["total"] for rw in naive_rows(d)) - d["grand"]) < 5000:
        return False
    # the year-end deferred balance stands apart from every other month end and from the opening balance
    if any(abs(x - d["deferred_total"]) <= 100 for x in d["closing"][:-1] + [d["opening"]]):
        return False
    # monthly recognized figures are distinct enough that the line check is not satisfied by accident
    if len({v for v in d["recognized"]}) < 12:
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def workbook(rows: list[dict], openings0: int, invoiced: list[int], refunded: list[int]) -> dict:
    n = len(rows)
    first_m = 7
    cL, cR = get_column_letter(first_m), get_column_letter(first_m + 11)
    tot_c, def_c = get_column_letter(first_m + 12), get_column_letter(first_m + 13)
    detail = []
    for i, rw in enumerate(rows, start=2):
        c = rw["c"]
        detail.append([c["id"], c["customer"], c["fee"] / 100, rw["addon"] / 100, rw["refund"] / 100, rw["before"] / 100]
                      + [v / 100 for v in rw["fy"]]
                      + [f"=SUM({cL}{i}:{cR}{i})", f"=C{i}+D{i}-E{i}-F{i}-{tot_c}{i}"])
    tr = n + 2
    detail.append(["Total", ""] + [f"=SUM({get_column_letter(j)}2:{get_column_letter(j)}{n + 1})" for j in range(3, first_m + 14)])
    sched = []
    for i in range(12):
        er = i + 2
        sched.append([LABELS[i], openings0 / 100 if i == 0 else f"=F{er - 1}", invoiced[i] / 100, refunded[i] / 100,
                      f"=Contracts!{get_column_letter(first_m + i)}{tr}", f"=B{er}+C{er}-D{er}-E{er}"])
    sched.append(["Total 2026", "", "=SUM(C2:C13)", "=SUM(D2:D13)", "=SUM(E2:E13)", "=F13"])
    money_cols = {get_column_letter(j): "#,##0.00" for j in range(2, 7)}
    return {
        "Schedule": {"header": ["Month", "Opening deferred revenue", "Invoiced", "Refunded", "Revenue recognized",
                                "Closing deferred revenue"], "rows": sched, "number_formats": money_cols,
                     "widths": {"A": 12, "B": 24, "C": 14, "D": 14, "E": 20, "F": 24}},
        "Contracts": {"header": ["Contract", "Customer", "Annual fee", "Upgrade add-on", "Refund", "Earned before 2026"]
                      + LABELS + ["2026 recognized", "Deferred at 2026-12-31"], "rows": detail,
                      "number_formats": {get_column_letter(j): "#,##0.00" for j in range(3, first_m + 14)},
                      "widths": {"A": 10, "B": 28}, "freeze": "C2"},
    }


def naive_workbook(d: dict) -> dict:
    rows = naive_rows(d)
    invoiced = [0] * 12
    opening = 0
    for rw in rows:
        c = rw["c"]
        if c["start"].year < FY:
            opening += c["fee"] - rw["before"]
        elif c["start"].year == FY:
            invoiced[c["start"].month - 1] += c["fee"]
    return workbook(rows, opening, invoiced, [0] * 12)


# --------------------------------------------------------------------------- emit

def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_xlsx(os.path.join(naive_dir, "deferred_revenue.xlsx"), naive_workbook(d), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 11)
    roles = d["roles"]

    # ---- workspace: billing export
    export = []
    for c in d["contracts"]:
        if c["billing"] == "Monthly":
            value = f"${c['monthly'] / 100:,.2f} / mo"
        else:
            value = money_str(c["fee"] / 100, 1)
        export.append([c["id"], c["customer"], c["plan"], c["billing"], c["start"], "12 months", value, c["invoice"],
                       c["invoice_date"], c["status"]])
    r.shuffle(export)
    write_xlsx(os.path.join(ws, "billing_contracts_export.xlsx"), {"Contracts": {
        "merged_title": "Tallgrass Dispatch - subscription contracts",
        "preamble": [["Exported 01/06/2027 by nadia@tallgrassdispatch.com", "", "", "", "", "", "", "", "", ""]],
        "header": ["Contract", "Customer", "Plan", "Billing", "Start date", "Term", "Contract value", "Invoice #", "Invoice date", "Status"],
        "rows": export, "widths": {"B": 28, "E": 12, "G": 16, "I": 12, "J": 22}, "freeze": "A4"}}, creator="Billing")

    # ---- workspace: change log
    log = []
    for c in d["contracts"]:
        for ch in c["changes"]:
            if ch["type"] == "Upgrade":
                log.append([ch["date"], c["id"], c["customer"], "Plan upgrade",
                            f"{c['plan']} to {ch['new_plan']}, prorated for the rest of the term", money_str(ch["amount"] / 100, 1)])
            elif ch["type"] == "Cancel":
                log.append([ch["date"], c["id"], c["customer"], "Cancellation",
                            "Cancelled by customer; unused months refunded less early-cancellation fee", money_str(-ch["amount"] / 100, 5)])
            else:
                log.append([ch["date"], c["id"], c["customer"], "Seat change", "Added 2 driver seats - included in plan, no charge", "$0.00"])
    other = r.choice([c for c in d["contracts"] if c["role"] == "plain" and not c["changes"]])
    log.append([date(2026, 3, r.randint(2, 27)), other["id"], other["customer"], "Payment method", "Card on file updated", ""])
    log.sort(key=lambda x: x[0])
    write_csv(os.path.join(ws, "billing_change_log_2026.csv"), ["Date", "Contract", "Customer", "Change", "Details", "Amount billed / (refunded)"],
              [[x[0].strftime("%m/%d/%Y")] + x[1:] for x in log], preamble=["Billing change log", "01/01/2026 - 12/31/2026"], crlf=True)

    # ---- workspace: the CPA's email
    write_email_thread(os.path.join(ws, "email_from_graham_cpa.txt"), [
        {"from": "Graham Whitfield <graham@whitfieldcpa.com>", "to": "Nadia Ruiz <nadia@tallgrassdispatch.com>",
         "date": "Mon, 4 Jan 2027 10:12", "subject": "2026 year-end: deferred revenue",
         "body": ("Hi Nadia,\n\nFor the 2026 file I need the deferred revenue roll-forward for the annual plans. Same method as last year:\n\n"
                  "- An annual plan is earned evenly over its twelve months, one twelfth each month.\n"
                  "- Month one: a plan that starts on or before the 15th earns in its start month; a plan that starts on the 16th or later "
                  "starts earning the following month.\n"
                  "- Upgrades: the prorated add-on in your change log is earned evenly over the months left in the term, starting with the "
                  "upgrade month under the same 15th rule. The original fee keeps earning as before.\n"
                  "- Cancellations: dated on or before the 15th, that month earns nothing; dated after the 15th, that month is the last one "
                  "earned. Nothing is earned after it. The refund comes straight out of deferred revenue.\n"
                  "- Monthly-billed customers are invoiced as they go and never carry a deferred balance, so leave them out. Same for "
                  "anything that is not signed.\n"
                  "- Deferred revenue at any month end is everything invoiced on an annual plan that has not been earned yet.\n\n"
                  "What I need back: one line per month for 2026 showing the opening balance, invoiced, refunded, revenue recognized and the "
                  "closing deferred balance, with a total line, plus the contract-by-contract detail behind it so I can trace a number to a "
                  "customer. Keep the math live so I can follow it.\n\nThanks,\nGraham")},
        {"from": "Nadia Ruiz <nadia@tallgrassdispatch.com>", "to": "Graham Whitfield <graham@whitfieldcpa.com>",
         "date": "Mon, 4 Jan 2027 11:40", "subject": "RE: 2026 year-end: deferred revenue",
         "body": ("Will do. The contract export and the change log are both in the folder.\n\n"
                  "One thing that changed since last year: our terms now let us keep a $250 early-cancellation fee when someone cancels an "
                  "annual plan, so refunds are the unused months less $250.\n\nNadia")},
        {"from": "Graham Whitfield <graham@whitfieldcpa.com>", "to": "Nadia Ruiz <nadia@tallgrassdispatch.com>",
         "date": "Mon, 4 Jan 2027 12:05", "subject": "RE: 2026 year-end: deferred revenue",
         "body": "Good to know. The $250 you keep is earned when they cancel - book it as revenue in the month the cancellation is dated.\n\nGraham"}])

    # ---- reference
    write_csv(os.path.join(ref, "contracts.csv"), ["contract", "customer", "recognized_2026", "deferred_2026_12_31"],
              [[rw["c"]["id"], rw["c"]["customer"], f"{rw['total'] / 100:.2f}", f"{rw['deferred'] / 100:.2f}"] for rw in d["rows"]])
    write_csv(os.path.join(ref, "schedule.csv"), ["month", "opening", "invoiced", "refunded", "recognized", "closing"],
              [[LABELS[i], f"{d['openings'][i] / 100:.2f}", f"{d['invoiced'][i] / 100:.2f}", f"{d['refunded'][i] / 100:.2f}",
                f"{d['recognized'][i] / 100:.2f}", f"{d['closing'][i] / 100:.2f}"] for i in range(12)])
    write_json(os.path.join(ref, "notes.json"), {
        "recognized_by_month": {LABELS[i]: round(d["recognized"][i] / 100, 2) for i in range(12)},
        "total_recognized_2026": round(d["grand"] / 100, 2), "deferred_2026_12_31": round(d["deferred_total"] / 100, 2),
        "opening_deferred_2026_01_01": round(d["opening"] / 100, 2),
        "excluded": [c["id"] for c in d["contracts"] if c["role"] in ("quote", "monthly")],
        "pinned": {k: roles[k]["id"] for k in ("late", "carry", "upgrade", "cancel", "renewal")}})

    # ---- reference solution
    write_xlsx(os.path.join(sol, "deferred_revenue.xlsx"), workbook(d["rows"], d["opening"], d["invoiced"], d["refunded"]),
               creator="Tallgrass Dispatch")

    by = {rw["c"]["id"]: rw for rw in d["rows"]}

    def pin(name, role):
        cid = roles[role]["id"]
        return {"type": "xlsx_value_present", "name": name, "path": "deferred_revenue.xlsx",
                "expected": round(by[cid]["total"] / 100, 2), "rel_tol": 0.000001, "near_text": cid.lower()}

    upc, canc, late, carry, ren = roles["upgrade"], roles["cancel"], roles["late"], roles["carry"], roles["renewal"]
    uch, cch = upc["changes"][0], canc["changes"][0]
    write_task_yaml(HERE, {
        "id": "deferred-revenue-schedule", "track": "desk", "category": "bookkeeping",
        "title": "2026 deferred revenue schedule for the annual plans",
        "ask": ("Graham needs the 2026 deferred revenue schedule for the year-end file, and his email in the folder says how he wants it "
                "done. Save it as deferred_revenue.xlsx.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"{late['id']} starts {late['start'].isoformat()}, after the 15th, so it earns from the following month; counting the start "
            "month moves a twelfth of its fee into 2026 (check: late-start contract)",
            f"{carry['id']} started {carry['start'].isoformat()} and is mid-term on 1 January; under the 15th rule its first month is "
            "December 2025, so eleven months land in 2026 and its unearned balance opens the year (check: carried-over contract)",
            f"{upc['id']} upgraded on {uch['date'].isoformat()}; the {uch['amount'] / 100:,.2f} add-on is earned over the "
            f"{uch['left']} months left in the term, most of them in 2027, not all at once and not over twelve months "
            "(check: upgraded contract)",
            f"{canc['id']} cancelled on {cch['date'].isoformat()}; recognition stops, the refund leaves deferred revenue, and the kept "
            "$250 fee from the second email is revenue in the cancellation month, so a schedule that just stops (or keeps running) "
            "is wrong (check: cancelled contract)",
            f"{ren['id']} is a renewal invoiced {ren['invoice_date'].isoformat()} for a 1 January 2027 start; it earns nothing in 2026 "
            "but its full fee is in the year-end deferred balance (check: deferred balance at year end)",
            "the export also holds an unsigned quote and two monthly-billed customers whose contract value is a monthly price; none of "
            "them belong on the schedule (checks: total recognized in 2026; deferred balance at year end)",
            "contract values are text ('$5,988.00', '$249.00 / mo') under a merged title and a preamble row, the change log has a "
            "two-line preamble, CRLF endings, a no-charge seat change and a card update (checks: total recognized in 2026; revenue recognized, one line per month)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "deferred_revenue.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no formula errors", "path": "deferred_revenue.xlsx"},
            {"type": "custom", "name": "revenue recognized, one line per month", "module": "check.py"},
            {"type": "xlsx_value_present", "name": "total recognized in 2026", "path": "deferred_revenue.xlsx",
             "expected": round(d["grand"] / 100, 2), "rel_tol": 0.000001, "near_text": "total"},
            {"type": "xlsx_value_present", "name": "deferred balance at year end", "path": "deferred_revenue.xlsx",
             "expected": round(d["deferred_total"] / 100, 2), "rel_tol": 0.000001, "near_text": "deferred"},
            pin("late-start contract", "late"),
            pin("carried-over contract", "carry"),
            pin("upgraded contract", "upgrade"),
            pin("cancelled contract", "cancel"),
        ],
    })
    print(f"seed={seed} contracts={len(d['rows'])} grand={d['grand'] / 100:.2f} deferred={d['deferred_total'] / 100:.2f} "
          f"opening={d['opening'] / 100:.2f}")
    for k in ("late", "carry", "upgrade", "cancel"):
        print(k, roles[k]["id"], by[roles[k]["id"]]["total"] / 100)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
