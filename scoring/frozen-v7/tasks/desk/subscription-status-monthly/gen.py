#!/usr/bin/env python3
"""subscription-status-monthly: active subscribers and cancellations per month for a coffee subscription.

    python gen.py [--seed N] [--naive DIR]

Business: a small coffee roaster that ships beans on subscription: monthly plans billed on the signup
anniversary, a quarterly plan paid up front, and a free first bag to try. The billing tool exports invoices;
cancellations arrive by email and are logged in the help desk. The owner wants a simple month-by-month count.

Traps (each caught by a check, see task.yaml):
  * the free first bag is a $0.00 trial invoice; trials are not subscribers, and trial users who cancel are not
    cancellations                                                        (checks: active and cancelled by month; June active)
  * a cancellation takes effect when the paid period ends, usually the month after the request
                                                                         (checks: active and cancelled by month; cancellations in April)
  * quarterly subscribers pay once for three months and are active in every one of them
                                                                         (checks: active and cancelled by month; June active)
  * cancelled customers come back: active again from the new paid period, the old cancellation still counts
                                                                         (check: active and cancelled by month)
  * failed charges retried the next day are two invoice rows for one period; void renewals are not payments
                                                                         (check: active and cancelled by month)
  * the counts must be live formulas                                     (check: live formulas)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]
MONTH_END = {m: (date(2026, int(m[5:]) % 12 + 1, 1) - timedelta(days=1)) for m in MONTHS}
EXPORT_FROM, EXPORT_TO = date(2025, 10, 1), date(2026, 7, 5)
PLANS = {"M1": ("Monthly - 1 bag", 19.00, 1), "M2": ("Monthly - 2 bags", 34.00, 1), "Q1": ("Quarterly prepaid - 1 bag/mo", 54.00, 3)}


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, d.day)


def mkey(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def build(seed: int) -> dict:
    r = rng(seed)
    customers, invoices, tickets = [], [], []
    inv_no = iter(range(20417, 99999, 3))
    seen = set()

    def new_customer():
        while True:
            f, l = person(r)
            if (f, l) not in seen:
                seen.add((f, l))
                break
        c = {"id": f"cus_{code(r, 8, 'abcdefghjkmnpqrstuvwxyz23456789')}", "email": email_for(r, f, l), "name": f"{f} {l}",
             "spells": []}
        customers.append(c)
        return c

    def invoice(c, plan, start, amount, status="paid", note=""):
        months = PLANS[plan][2]
        end = add_months(start, months) - timedelta(days=1)
        row = {"no": f"INV-{next(inv_no)}", "cid": c["id"], "email": c["email"], "plan": plan, "start": start, "end": end,
               "amount": amount, "status": status, "created": start, "note": note, "k": r.random()}
        invoices.append(row)
        return row

    def run_spell(c, plan, start, stop_after=None, trial_first=False):
        """Bill from `start` every period; stop after the period that contains `stop_after` (the cancel request)."""
        periods = []
        d = start
        if trial_first:
            invoice(c, plan if plan != "Q1" else "M1", d, 0.0, note="first bag free")
            d = add_months(d, 1)
        while d <= EXPORT_TO:
            row = invoice(c, plan, d, PLANS[plan][1])
            if r.random() < 0.05:                       # failed, then retried and paid the next day
                row["status"] = "failed"
                retry = invoice(c, plan, d, PLANS[plan][1])
                retry["created"] = d + timedelta(days=1)
                row = retry
            periods.append((row["start"], row["end"]))
            if stop_after and row["start"] <= stop_after <= row["end"]:
                nxt = add_months(d, PLANS[plan][2])
                if nxt <= EXPORT_TO:
                    invoice(c, plan, nxt, PLANS[plan][1], status="void", note="subscription cancelled")
                break
            d = add_months(d, PLANS[plan][2])
        c["spells"].append({"plan": plan, "periods": periods, "cancel_request": stop_after,
                            "end": periods[-1][1] if (stop_after and periods) else None})
        return periods

    def plan_choice():
        return r.choices(["M1", "M2", "Q1"], weights=[55, 25, 20])[0]

    # subscribers who started before the export window or during it
    for _ in range(150):
        c = new_customer()
        plan = plan_choice()
        start = date(2025, r.randint(1, 12), r.randint(2, 28)) if r.random() < 0.6 else date(2026, r.randint(1, 6), r.randint(2, 28))
        # roll a pre-2025-10 start forward to its first period inside the export window
        while start < EXPORT_FROM:
            start = add_months(start, PLANS[plan][2])
        cancel = None
        if r.random() < 0.34:
            cancel = start + timedelta(days=r.randint(20, 240))
            if not (date(2026, 1, 1) <= cancel <= date(2026, 6, 10)):
                cancel = None
        trial = start >= date(2026, 1, 1) and r.random() < 0.35
        if trial and cancel and cancel < add_months(start, 1) + timedelta(days=5):
            cancel = add_months(start, 1) + timedelta(days=5)
        run_spell(c, plan, start, stop_after=cancel, trial_first=trial)
    # trial users who never convert (half of them email to cancel)
    for _ in range(14):
        c = new_customer()
        d = date(2026, r.randint(1, 6), r.randint(2, 28))
        invoice(c, "M1", d, 0.0, note="first bag free")
        nxt = add_months(d, 1)
        if nxt <= EXPORT_TO:
            invoice(c, "M1", nxt, PLANS["M1"][1], status="void", note="trial not converted")
        c["trial_only"] = True
        if r.random() < 0.6:
            tickets.append({"email": c["email"], "requested": d + timedelta(days=r.randint(5, 20)), "reason": r.choice(["not for me", "too much coffee", "price", "didn't like the roast"])})
    # cancel-then-come-back customers
    for _ in range(3):
        c = new_customer()
        plan = r.choice(["M1", "M2"])
        start = date(2025, 11, r.randint(2, 28))
        cancel = date(2026, r.choice([1, 2]), r.randint(3, 25))
        run_spell(c, plan, start, stop_after=cancel)
        back = date(2026, r.choice([4, 5]), r.randint(2, 28))
        run_spell(c, plan, back)
        c["came_back"] = True
    for c in customers:
        for sp in c["spells"]:
            if sp["cancel_request"]:
                tickets.append({"email": c["email"], "requested": sp["cancel_request"], "reason": r.choice(
                    ["too much coffee", "moving", "price", "switching roasters", "budget", "going on a long trip"])})
    # ---- truth ----
    active, cancelled = {}, {}
    for m in MONTHS:
        me = MONTH_END[m]
        active[m] = sum(1 for c in customers if any(s <= me <= e for sp in c["spells"] for s, e in sp["periods"]))
        cancelled[m] = sum(1 for c in customers for sp in c["spells"] if sp["end"] and mkey(sp["end"]) == m)
    return {"customers": customers, "invoices": invoices, "tickets": tickets, "active": active, "cancelled": cancelled}


def naive_counts(d: dict) -> tuple[dict, dict]:
    """Active = anyone with an invoice created in the month; cancelled = help-desk requests logged in the month."""
    act = {m: len({i["cid"] for i in d["invoices"] if mkey(i["created"]) == m}) for m in MONTHS}
    can = {m: sum(1 for t in d["tickets"] if mkey(t["requested"]) == m) for m in MONTHS}
    return act, can


def acceptable(d: dict) -> bool:
    act, can = d["active"], d["cancelled"]
    na, nc = naive_counts(d)
    if any(mkey(sp["end"]) == mkey(sp["cancel_request"]) for c in d["customers"] for sp in c["spells"] if sp["end"]) and \
            sum(1 for c in d["customers"] for sp in c["spells"] if sp["end"] and mkey(sp["end"]) != mkey(sp["cancel_request"])) < 8:
        return False
    # pinned figures: June active and April cancellations must be unique among every month's true and naive figures
    others_a = [v for m, v in act.items() if m != "2026-06"] + list(na.values())
    others_c = [v for m, v in can.items() if m != "2026-04"] + list(nc.values())
    if act["2026-06"] in others_a or can["2026-04"] in others_c or can["2026-04"] < 3:
        return False
    # every month's pair distinct from its naive pair, and active never equal to cancelled
    return all(na[m] != act[m] and nc[m] != can[m] for m in MONTHS) and all(act[m] != can[m] for m in MONTHS)


def workbook(d: dict, active: dict | None = None, cancelled: dict | None = None, naive: bool = False) -> dict:
    """Invoices sheet as exported, a Status sheet with one row per customer-month flag, and a Summary of COUNTIFS."""
    status_rows = []
    na_created = {}
    for c in d["customers"]:
        for m in MONTHS:
            me = MONTH_END[m]
            if naive:
                a = int(any(i["cid"] == c["id"] and mkey(i["created"]) == m for i in d["invoices"]))
                x = sum(1 for t in d["tickets"] if t["email"] == c["email"] and mkey(t["requested"]) == m)
            else:
                a = int(any(s <= me <= e for sp in c["spells"] for s, e in sp["periods"]))
                x = sum(1 for sp in c["spells"] if sp["end"] and mkey(sp["end"]) == m)
            if a or x:
                status_rows.append([c["id"], m, a, x])
    n = len(status_rows) + 1
    summary = []
    for i, m in enumerate(MONTHS, start=2):
        summary.append([m, f"=COUNTIFS(Status!$B$2:$B${n},A{i},Status!$C$2:$C${n},1)", f"=SUMIFS(Status!$D$2:$D${n},Status!$B$2:$B${n},A{i})"])
    return {
        "Summary": {"header": ["Month", "Active subscribers (month end)", "Cancellations effective"], "rows": summary,
                    "widths": {"A": 10, "B": 30, "C": 26}},
        "Status": {"header": ["Customer", "Month", "Active at month end", "Cancellation effective"], "rows": status_rows},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_xlsx(os.path.join(naive_dir, "subscriptions.xlsx"), workbook(d, naive=True), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 13)
    rows = []
    seq = 20417
    for i in sorted(d["invoices"], key=lambda x: (x["created"], x["k"])):
        if not (EXPORT_FROM <= i["created"] <= EXPORT_TO):
            continue
        seq += 1 + int(i["k"] * 3)
        rows.append([f"INV-{seq}", i["cid"], i["email"], PLANS[i["plan"]][0], i["start"].isoformat(), i["end"].isoformat(),
                     f"{i['amount']:.2f}", i["status"], i["created"].isoformat(), i["note"]])
    write_csv(os.path.join(ws, "billing_invoices_2025-10-01_2026-07-05.csv"),
              ["invoice", "customer", "customer_email", "plan", "period_start", "period_end", "amount", "status", "created", "memo"],
              rows)
    trows = []
    for n_, t in enumerate(sorted(d["tickets"], key=lambda t: t["requested"]), start=3100):
        email = t["email"].upper() if r.random() < 0.2 else t["email"]
        trows.append([f"#{n_}", date_variant(t["requested"], 1), email, "Cancel subscription", t["reason"], r.choice(["Sam", "Jo", "Sam"])])
    write_csv(os.path.join(ws, "helpdesk_cancellation_tickets.csv"), ["Ticket", "Received", "From", "Subject", "Reason", "Handled by"],
              trows, bom=True, crlf=True)
    write_text(os.path.join(ws, "note_from_owner.txt"),
               "Subscriber counts - how I count them\n"
               "\n"
               "A subscriber is someone paying us for coffee. The free first bag is a trial: they are not a subscriber\n"
               "until their first paid box, and if they cancel during the trial that is not a lost subscriber either.\n"
               "\n"
               "Active in a month means they have a paid period that covers the last day of that month. Quarterly\n"
               "people pay once for three months, so they are active all three.\n"
               "\n"
               "When someone cancels, they keep getting coffee until the end of the period they already paid for.\n"
               "Count the cancellation in the month that paid period ends, not the month they emailed us.\n"
               "\n"
               "If somebody cancels and comes back later, they are active again from their new paid period, and the\n"
               "earlier cancellation still counts in its month.\n"
               "\n"
               "The billing tool retries a failed card the next day, so a failed invoice usually has a paid twin.\n"
               "\n"
               "I want January to June: active subscribers at the end of each month and cancellations in each month.\n"
               "\n"
               "- Wren\n")
    write_csv(os.path.join(ref, "monthly_counts.csv"), ["month", "active", "cancelled"],
              [[m, d["active"][m], d["cancelled"][m]] for m in MONTHS])
    na, nc = naive_counts(d)
    write_json(os.path.join(ref, "notes.json"), {"active": d["active"], "cancelled": d["cancelled"], "naive_active": na, "naive_cancelled": nc,
                                                  "trial_only_customers": sum(1 for c in d["customers"] if c.get("trial_only")),
                                                  "came_back": [c["id"] for c in d["customers"] if c.get("came_back")]})
    write_xlsx(os.path.join(sol, "subscriptions.xlsx"), workbook(d), creator="reference")
    write_task_yaml(HERE, {
        "id": "subscription-status-monthly", "track": "desk", "category": "spreadsheet",
        "title": "Active subscribers and cancellations by month",
        "ask": ("How many coffee subscribers did we have each month this year, January to June, and how many cancelled? Work it "
                "out from the billing export and the help desk tickets and save it as subscriptions.xlsx with the counts as "
                "formulas. My note explains how I count.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the free first bag is a $0.00 invoice: trial users are not subscribers until a paid period, and the trial users "
            "who emailed to cancel are in the help desk file but are not cancellations (checks: active and cancelled by month; "
            "June active subscribers)",
            "a cancellation takes effect at the end of the paid period, which is usually the month after the ticket; counting "
            "tickets by the month received moves most cancellations a month early (checks: active and cancelled by month; "
            "April cancellations)",
            "quarterly subscribers are invoiced once for three months; counting customers invoiced in a month drops them from "
            "two months in three (checks: active and cancelled by month; June active subscribers)",
            "three customers cancel in the winter and resubscribe in April or May under the same customer id: active again "
            "from the new paid period, with their earlier cancellation still counted (check: active and cancelled by month)",
            "failed card charges are retried the next day, so one period has a failed row and a paid row, and cancelled "
            "renewals leave a void invoice after the last paid period (check: active and cancelled by month)",
            "the monthly counts must be live formulas over the invoice data (check: live formulas)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "subscriptions.xlsx", "min_count": 6},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "subscriptions.xlsx"},
            {"type": "custom", "name": "active and cancelled by month", "module": "check.py"},
            {"type": "xlsx_value_present", "name": "June active subscribers", "path": "subscriptions.xlsx",
             "expected": float(d["active"]["2026-06"]), "rel_tol": 0.0001, "near_text": "active"},
            {"type": "xlsx_value_present", "name": "April cancellations", "path": "subscriptions.xlsx",
             "expected": float(d["cancelled"]["2026-04"]), "rel_tol": 0.0001, "near_text": "cancel"},
        ],
    })
    print(f"seed={seed} customers={len(d['customers'])} invoices={len(rows)} tickets={len(d['tickets'])}")
    print("  active   ", d["active"], "\n  naive    ", na)
    print("  cancelled", d["cancelled"], "\n  naive    ", nc)


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
