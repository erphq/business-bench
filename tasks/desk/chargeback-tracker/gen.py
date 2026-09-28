#!/usr/bin/env python3
"""chargeback-tracker: chargeback cases to status, disputed amount, evidence deadline and net loss for a candle shop.

    python gen.py [--seed N] [--naive DIR]
    python gen.py --list-traps
    python gen.py --traps-off reminders,retrievals --out DIR   # same draw, those pitfalls removed, same answer
    python gen.py --mutant holidays --out DIR                  # a deliverable that falls for one trap

Business: an online candle and home-fragrance shop. The card processor exports every dispute notice it sends,
including reminders, amendments and retrieval requests, and a separate file of decisions.

Traps (each caught by a check, see task.yaml):
  * evidence is due 7 business days after the FIRST notice, skipping weekends and the bank holidays listed; the
    export's Respond By column is a calendar-day estimate                                     (check: evidence deadlines)
  * reminder notices repeat a case with a later notice date                                   (checks: one row per case; deadlines)
  * amendment notices lower the disputed amount; the deadline still runs from the first notice (checks: net loss; deadlines)
  * retrieval requests are not chargebacks: no money moved, no row                             (checks: one row per case; row count)
  * outcomes come from a second file; Accepted by merchant is a loss; a win returns the $20 fee (checks: status; net loss)
  * partial chargebacks dispute less than the order total                                       (check: net loss)
"""
from __future__ import annotations
import argparse
import os
import shutil
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from bizgen.traps import TrapSet, add_trap_args, parse_trap_args, variant_dirs, active_trap_text  # noqa: E402

# Every trap sentence in task.yaml, keyed. Switchable traps are removed when the notice export is written, so build()
# and its random draws are identical in every variant and the correct answer never moves.
TRAPS = TrapSet(
    switchable={
        "reminders": "reminder notices repeat three cases with later notice dates (off: reminders not exported)",
        "retrievals": "two retrieval requests sit in the notice export (off: not exported)",
    },
    fixed={
        "holidays": "evidence is due 7 business days after the first notice, skipping weekends and the listed holidays",
        "amendment": "an amendment halves one case's disputed amount; its deadline is unchanged",
        "decisions": "decisions come from a second file; Accepted by merchant is a loss and a win returns the fee",
        "partials": "two cases dispute only part of the order",
    },
)
# task.yaml trap sentences, in order, and the trap each one describes
TRAP_KEYS = ["holidays", "reminders", "amendment", "retrievals", "decisions", "partials"]

HOLIDAYS = [(date(2026, 5, 25), "Memorial Day"), (date(2026, 6, 19), "Juneteenth"), (date(2026, 7, 3), "Independence Day (observed)"),
            (date(2026, 9, 7), "Labor Day"), (date(2026, 10, 12), "Columbus Day"), (date(2026, 11, 11), "Veterans Day"),
            (date(2026, 11, 26), "Thanksgiving Day"), (date(2026, 12, 25), "Christmas Day")]
HOL = {h for h, _ in HOLIDAYS}
FEE = 20.00
REASONS = [("10.4", "Fraud - card absent"), ("13.1", "Merchandise not received"), ("13.3", "Not as described"),
           ("13.6", "Credit not processed"), ("13.2", "Cancelled recurring"), ("4853", "Cardholder dispute"), ("4837", "No cardholder authorization")]


def business_days_after(d: date, n: int) -> date:
    k = 0
    while k < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in HOL:
            k += 1
    return d


def build(seed: int) -> dict:
    r = rng(seed)
    cases = []
    first_dates = {
        "holiday_labor": date(2026, 9, 1), "holiday_july": date(2026, 6, 29), "holiday_june": date(2026, 6, 16),
        "reminder": date(2026, 8, 5), "amended": date(2026, 7, 21), "partial_won": date(2026, 7, 8),
        "accepted": date(2026, 8, 12), "lost": date(2026, 6, 23), "friday_notice": date(2026, 8, 28),
        "partial_open": date(2026, 9, 9),
    }
    tags = list(first_dates) + [f"plain_{i}" for i in range(9)]
    for i, tag in enumerate(tags):
        d0 = first_dates.get(tag) or date(2026, 6, 15) + timedelta(days=r.randint(0, 86))
        while d0.weekday() >= 5 or d0 in HOL:
            d0 += timedelta(days=1)
        order_amt = money(r, 38, 260)
        disputed = order_amt
        if tag.startswith("partial"):
            disputed = round(order_amt * r.choice([0.35, 0.4, 0.5]), 2)
        code, reason = r.choice(REASONS)
        cases.append({"tag": tag, "first": d0, "order_amt": order_amt, "disputed_initial": disputed, "disputed": disputed,
                      "order": f"FC-{58200 + r.randint(0, 3999)}", "card": str(r.randint(1001, 9899)), "reason": f"{code} {reason}"})
    cases.sort(key=lambda c: (c["first"], c["order"]))
    for i, c in enumerate(cases):
        c["id"] = f"DP-{7734100 + i * 37}"
    by = {c["tag"]: c for c in cases}

    notices = []
    for c in cases:
        notices.append({"case": c, "date": c["first"], "type": "Chargeback", "amount": c["disputed_initial"], "note": "Funds withdrawn"})
    rem = by["reminder"]
    notices.append({"case": rem, "date": rem["first"] + timedelta(days=5), "type": "Reminder", "amount": rem["disputed"], "note": "No response received yet"})
    for c in [by["plain_2"], by["plain_5"]]:
        notices.append({"case": c, "date": business_days_after(c["first"], 3), "type": "Reminder", "amount": c["disputed"], "note": "No response received yet"})
    am = by["amended"]
    am["disputed"] = round(am["disputed_initial"] * 0.5, 2)
    notices.append({"case": am, "date": am["first"] + timedelta(days=6), "type": "Amendment", "amount": am["disputed"],
                    "note": f"Issuer amended disputed amount from {am['disputed_initial']:.2f} to {am['disputed']:.2f}; difference credited"})
    # retrieval requests: not chargebacks
    rr = []
    for k in range(2):
        d0 = date(2026, 7, 14) + timedelta(days=17 * k + 3)
        rr.append({"id": f"DP-{7733900 + k * 11}", "first": d0, "order": f"FC-{58200 + r.randint(0, 3999)}", "card": str(r.randint(1001, 9899)),
                   "order_amt": money(r, 40, 180), "reason": "RR Retrieval request - copy of receipt"})
    for x in rr:
        notices.append({"case": x, "date": x["first"], "type": "Retrieval Request", "amount": x["order_amt"], "note": "Provide receipt; no funds withdrawn"})
    notices.sort(key=lambda n: (n["date"], n["case"]["id"]))
    for i, n in enumerate(notices):
        n["id"] = f"N{902100 + i * 5}"

    # outcomes
    outcomes = {}
    fixed = {"partial_won": "Won", "accepted": "Accepted by merchant", "lost": "Lost", "holiday_june": "Won", "holiday_july": "Lost"}
    for c in cases:
        oc = fixed.get(c["tag"])
        if oc is None and c["tag"].startswith("plain") and c["first"] < date(2026, 8, 10):
            oc = r.choice(["Won", "Lost"])
        if oc:
            outcomes[c["id"]] = {"outcome": oc, "decided": business_days_after(c["first"], r.randint(18, 30))}

    for c in cases:
        c["due"] = business_days_after(c["first"], 7)
        oc = outcomes.get(c["id"])
        if oc is None:
            c["status"] = "open"
        elif oc["outcome"] == "Won":
            c["status"] = "won"
        else:
            c["status"] = "lost"
        c["net_loss"] = 0.0 if c["status"] == "won" else round(c["disputed"] + FEE, 2)
    return {"cases": cases, "notices": notices, "outcomes": outcomes, "rr": rr, "by": by}


def acceptable(d: dict) -> bool:
    by = d["by"]
    for tag in ("holiday_labor", "holiday_july", "holiday_june"):
        c = by[tag]
        plain = c["first"]; k = 0
        while k < 7:
            plain += timedelta(days=1)
            if plain.weekday() < 5:
                k += 1
        if plain == c["due"]:
            return False
    return all(c["id"] for c in d["cases"])


def emit(seed: int, naive_dir: str | None, traps: TrapSet = TRAPS, out: str | None = None,
         mutant: str | None = None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    if mutant:
        write_mutant(d, mutant, out)
        return
    here = out or HERE
    ws, ref, sol = task_dirs(HERE) if out is None else variant_dirs(out)
    if out is not None:  # the custom check travels with the copy so it can be graded on its own
        shutil.copyfile(os.path.join(HERE, "check.py"), os.path.join(out, "check.py"))
    r = rng(seed + 5)
    cases, notices, outcomes, by = d["cases"], d["notices"], d["outcomes"], d["by"]
    if not (traps.on("reminders") and traps.on("retrievals")):
        drop = set()
        if not traps.on("reminders"):
            drop.add("Reminder")
        if not traps.on("retrievals"):
            drop.add("Retrieval Request")
        notices = [n for n in notices if n["type"] not in drop]

    rows = []
    for n in notices:
        c = n["case"]
        rows.append([n["id"], c["id"], n["date"].strftime("%b %d, %Y"), n["type"], c["order"], f"**** {c['card']}", c["reason"],
                     f"${c['order_amt']:,.2f}", f"${n['amount']:,.2f}", (n["date"] + timedelta(days=10)).strftime("%b %d, %Y"), n["note"]])
    write_csv(os.path.join(ws, "ridgepay_dispute_notices_2026-06-01_to_2026-09-11.csv"),
              ["Notice ID", "Case ID", "Notice Date", "Notice Type", "Order #", "Card", "Reason", "Transaction Amount",
               "Disputed Amount", "Respond By (est.)", "Message"], rows)
    orows = [[cid, o["decided"].strftime("%m/%d/%Y"), o["outcome"]] for cid, o in sorted(outcomes.items(), key=lambda kv: kv[1]["decided"])]
    write_csv(os.path.join(ws, "ridgepay_dispute_decisions_2026-09-11.csv"), ["Case", "Decision Date", "Decision"], orows,
              preamble=["Ridgepay Merchant Services - dispute decisions", "Merchant: Fernhill Candle Co. (MID 4471-0092)"], crlf=True)
    write_text(os.path.join(ws, "holidays_2026.txt"),
               "Bank holidays observed by Ridgepay in 2026 (no business day)\n\n" + "\n".join(f"{h.isoformat()}  {n}" for h, n in HOLIDAYS) + "\n")
    write_text(os.path.join(ws, "ridgepay_dispute_guide.md"), """# Ridgepay merchant dispute guide (excerpt)

## Notice types

- **Chargeback** - the cardholder's bank has disputed a transaction. The disputed amount and a $20.00 dispute fee are
  withdrawn from your settlement the same day.
- **Reminder** - sent while a chargeback is still waiting for your response. It does not open a new case or change the deadline.
- **Amendment** - the issuing bank changed the disputed amount. The difference is returned to you. The deadline does not change.
- **Retrieval Request** - the bank wants a copy of the receipt. No funds are withdrawn and no fee is charged. It is not a chargeback.

## Deadlines

Your evidence must reach us within **7 business days after the date of the first Chargeback notice** for the case. The
notice date itself does not count. Business days exclude Saturdays, Sundays and the bank holidays we observe. The
"Respond By (est.)" date on notices is a calendar estimate for card-network timelines; do not rely on it.

## Decisions

- **Won** - the disputed amount and the $20.00 fee are returned to you.
- **Lost** - the disputed amount and the fee are not returned.
- **Accepted by merchant** - you chose not to contest. Treated as lost.
""")
    write_text(os.path.join(ws, "note_from_june.txt"), """Can you get the chargeback tracker up to date? One line per case (not per notice - Ridgepay sends a
lot of repeats) in chargebacks.csv with:

case_id, disputed_amount, status (open, won or lost), evidence_due, net_loss

net_loss is what the case has cost us so far: the disputed amount plus the fee while it is still open or once we
lost it, and nothing if we won.

Thanks - June
""")

    header = ["case_id", "disputed_amount", "status", "evidence_due", "net_loss"]
    out = [[c["id"], f"{c['disputed']:.2f}", c["status"], c["due"].isoformat(), f"{c['net_loss']:.2f}"] for c in cases]
    write_csv(os.path.join(ref, "chargebacks.csv"), header, out)
    write_csv(os.path.join(sol, "chargebacks.csv"), header, out)
    write_json(os.path.join(ref, "cases.json"), [{"case_id": c["id"], "tag": c["tag"], "first_notice": c["first"].isoformat(),
                                                  "evidence_due": c["due"].isoformat(), "status": c["status"], "disputed": c["disputed"],
                                                  "net_loss": c["net_loss"]} for c in cases])
    cid = lambda t: by[t]["id"]
    due_keys = [cid(t) for t in ("holiday_labor", "holiday_july", "holiday_june", "reminder", "amended", "friday_notice")]
    spec = {
        "id": "chargeback-tracker", "track": "desk", "category": "bookkeeping",
        "title": "Chargeback tracker with evidence deadlines",
        "ask": ("Please bring our chargeback tracker up to date from the Ridgepay exports in the folder - June's note says what "
                "she wants and the dispute guide explains the rules. Save it as chargebacks.csv.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": active_trap_text([
            f"evidence is due 7 business days after the first notice, skipping weekends and the listed holidays: {cid('holiday_labor')} "
            f"(1 Sep) runs past Labor Day to {by['holiday_labor']['due'].isoformat()}, {cid('holiday_july')} past 3 July and "
            f"{cid('holiday_june')} past Juneteenth; the export's Respond By column is a 10-calendar-day estimate the guide says "
            "not to use (check: evidence deadlines)",
            f"reminder notices repeat {cid('reminder')} and two other cases with later notice dates; they are not new cases and the "
            "deadline still runs from the first notice (checks: one row per case; evidence deadlines)",
            f"an amendment halves {cid('amended')}'s disputed amount six days later; the lower amount is what is disputed and what "
            "the still-open case costs, while its deadline is unchanged (checks: disputed amounts; net loss; evidence deadlines)",
            f"two retrieval requests ({', '.join(x['id'] for x in d['rr'])}) are in the same export but moved no money and are not "
            "chargebacks (checks: one row per case; row count)",
            f"decisions are in a separate file: Accepted by merchant ({cid('accepted')}) is a loss, and a won case costs nothing "
            "because the $20 fee comes back too; undecided cases stay open with the amount and fee out (checks: status; net loss)",
            f"{cid('partial_won')} and {cid('partial_open')} dispute only part of the order, so the transaction amount overstates "
            "them (checks: disputed amounts; net loss)",
        ], TRAP_KEYS, traps),
        "checks": [
            {"type": "csv_columns", "name": "tracker columns", "path": "chargebacks.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per case", "path": "chargebacks.csv", "column": "case_id", "ref": "chargebacks.csv",
             "normalize": ["alnum"]},
            {"type": "csv_row_count", "name": "row count", "path": "chargebacks.csv", "equals_ref": "chargebacks.csv"},
            {"type": "custom", "name": "evidence deadlines", "module": "check.py"},
            {"type": "csv_values_match", "name": "status", "path": "chargebacks.csv", "ref": "chargebacks.csv", "key": "case_id",
             "columns": ["status"], "min_accuracy": 1.0, "must_match_keys": [cid(t) for t in ("accepted", "partial_won", "amended", "partial_open")]},
            {"type": "csv_values_match", "name": "disputed amounts", "path": "chargebacks.csv", "ref": "chargebacks.csv", "key": "case_id",
             "columns": ["disputed_amount"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0,
             "must_match_keys": [cid(t) for t in ("amended", "partial_won", "partial_open")]},
            {"type": "csv_values_match", "name": "net loss", "path": "chargebacks.csv", "ref": "chargebacks.csv", "key": "case_id",
             "columns": ["net_loss"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0,
             "must_match_keys": [cid(t) for t in ("amended", "partial_won", "partial_open", "accepted", "lost")]},
        ],
    }
    if not traps.canonical:
        spec["variant"] = {"of": "chargeback-tracker", "draw": seed, "traps_off": sorted(traps.off)}
    write_task_yaml(here, spec)
    write_json(os.path.join(ref, "deadline_keys.json"), due_keys)
    print(f"seed={seed} cases={len(cases)} notices={len(notices)}")
    for c in cases:
        print(f"  {c['id']} {c['tag']:14} first={c['first']} {c['first']:%a} due={c['due']} status={c['status']:5} disputed={c['disputed']:>7.2f} net={c['net_loss']:.2f}")


def write_naive(d: dict, out: str) -> None:
    """One row per notice, Respond By as the deadline, transaction amount as disputed, status from decisions (Accepted kept as-is)."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for n in d["notices"]:
        c = n["case"]
        oc = d["outcomes"].get(c["id"], {}).get("outcome", "open")
        rows.append([c["id"], f"{c['order_amt']:.2f}", oc.lower(), (n["date"] + timedelta(days=10)).isoformat(),
                     f"{0 if oc == 'Won' else c['order_amt'] + FEE:.2f}"])
    write_csv(os.path.join(out, "chargebacks.csv"), ["case_id", "disputed_amount", "status", "evidence_due", "net_loss"], rows)


# --------------------------------------------------------------------------- per-trap mutants

def weekdays_after(d: date, n: int) -> date:
    """7 business days counting weekends only: the listed holidays missed (holidays mutant)."""
    k = 0
    while k < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            k += 1
    return d


def write_mutant(d: dict, trap: str, out: str) -> None:
    """chargebacks.csv right in every respect except that it falls for `trap`."""
    if trap not in TRAP_KEYS:
        raise KeyError(trap)
    by_case = {}
    for n in d["notices"]:
        by_case.setdefault(n["case"]["id"], []).append(n)
    rows = []
    for c in d["cases"]:
        disputed, status, due = c["disputed"], c["status"], c["due"]
        if trap == "holidays":        # weekends skipped, the bank holidays counted as business days
            due = weekdays_after(c["first"], 7)
        elif trap == "amendment" and c["tag"] == "amended":
            # the amendment read as the case's latest chargeback notice: the deadline restarts from it, and the amount
            # is still the one on the first notice
            last = max(n["date"] for n in by_case[c["id"]])
            due, disputed = business_days_after(last, 7), c["disputed_initial"]
        elif trap == "partials" and c["tag"].startswith("partial"):   # the transaction amount taken as disputed
            disputed = c["order_amt"]
        elif trap == "decisions":
            oc = d["outcomes"].get(c["id"], {}).get("outcome")
            if oc == "Accepted by merchant":   # not a Won or a Lost, so left open
                status = "open"
        if status == "won":
            net = FEE if trap == "decisions" else 0.0   # decisions: a win still costs the fee
        else:
            net = round(disputed + FEE, 2)
        if trap == "reminders":       # every Chargeback or Reminder notice read as a case, due 7 business days after it
            for n in by_case[c["id"]]:
                if n["type"] in ("Chargeback", "Reminder"):
                    rows.append([c["id"], f"{disputed:.2f}", status, business_days_after(n["date"], 7).isoformat(), f"{net:.2f}"])
            continue
        rows.append([c["id"], f"{disputed:.2f}", status, due.isoformat(), f"{net:.2f}"])
    if trap == "retrievals":          # the retrieval requests tracked as open chargebacks
        for x in d["rr"]:
            rows.append([x["id"], f"{x['order_amt']:.2f}", "open", business_days_after(x["first"], 7).isoformat(),
                         f"{x['order_amt'] + FEE:.2f}"])
    os.makedirs(out, exist_ok=True)
    write_csv(os.path.join(out, "chargebacks.csv"), ["case_id", "disputed_amount", "status", "evidence_due", "net_loss"], rows)


# Grader-blind: the 'reminders' mutant (one row per Chargeback or Reminder notice, three cases repeated) passes its cited
# check "one row per case": csv_set_equal compares the set of case ids, so a repeated id is invisible to it. It fails
# "evidence deadlines" and "row count" (not cited for this trap). Kept in code, out of MUTANTS.
MUTANTS = {k: write_mutant for k in TRAP_KEYS if k != "reminders"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    add_trap_args(ap)
    a = ap.parse_args()
    traps = parse_trap_args(a, TRAPS, MUTANTS, TRAP_KEYS)
    for attempt in range(200):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    # The acceptance loop always runs on the full task, so a variant or mutant shares the canonical draw.
    emit(a.seed * 1000 + attempt, a.naive, traps, a.out, a.mutant)
