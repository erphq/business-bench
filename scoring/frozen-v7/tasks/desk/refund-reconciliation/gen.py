#!/usr/bin/env python3
"""refund-reconciliation: an inn's August refund log from its booking system against the card processor's export.

    python gen.py [--seed N] [--naive DIR]

Business: The Larkin House Inn, a twelve-room inn. The front desk logs every refund in the property management system
(PMS), then keys card refunds into the processor's terminal, sometimes a day or three later. The owner reconciles the
month's refunds against the processor export, which runs a few days past month end. Last month's reconciliation is in
the folder and doubles as the template; the owner's note carries the status rules.

Traps (each caught by a check, see task.yaml):
  * the processor export mixes charges, payouts and fees with refunds, and a full refund's fee comes back, so its net
    differs from the refund                                                              (checks: amounts; status)
  * one refund went to two cards: two processor lines, one PMS refund                    (checks: amounts; status)
  * one booking has two partial refunds on different days                               (check: one row per refund)
  * a failed processor attempt is not a refund, whether or not a retry succeeded          (checks: status; variance)
  * late-August refunds settle in September; late-July refunds settle in August and are
    last month's timing items                                                            (checks: status; one row per refund)
  * September's own refunds are in the export and are not part of August                 (check: one row per refund)
  * refunds paid by check never touch the processor                                      (check: one row per refund)
  * a keyed amount and a refund made straight in the processor dashboard don't match     (checks: status; variance)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

B62 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
STAFF = ["Maya (front desk)", "Jonah (front desk)", "Evelyn (manager)"]
S_MATCH, S_TIMING, S_PRIOR, S_DIFF, S_NOPROC, S_NOPMS = ("matched", "timing - settled in September", "prior month timing", "amount differs",
                                                        "not in processor", "not in PMS")


def build(seed: int) -> dict:
    r = rng(seed)
    guests = people(r, 60)
    gi = iter(guests)
    book_no = [r.randint(24100, 24400)]
    rf_no = [r.randint(10400, 10480)]

    def booking():
        book_no[0] += r.randint(3, 17)
        f, l = next(gi)
        return {"ref": f"LH-{book_no[0]}", "guest": f"{f} {l}", "last4": f"{r.randint(1000, 9999)}", "nightly": r.randint(18, 42) * 1000}

    def pid(prefix):
        return prefix + "_" + code(r, 24, B62)

    pms, proc, recon, july = [], [], [], []

    def charge(b, when, nights):
        amt = b["nightly"] * nights + r.randint(0, 9) * 500
        fee = round(amt * 0.029) + 30
        proc.append({"id": pid("ch"), "type": "charge", "status": "succeeded", "created": when, "amount": amt, "fee": fee,
                     "desc": f"Booking {b['ref']} {b['guest'].split()[-1]}", "last4": b["last4"]})
        return amt, fee

    def refund_line(b, when, amt, fee_back, status="succeeded", last4=None):
        proc.append({"id": pid("re"), "type": "refund", "status": status, "created": when, "amount": -amt, "fee": -fee_back,
                     "desc": f"Refund {b['ref']} {b['guest'].split()[-1]}", "last4": last4 or b["last4"]})
        return proc[-1]

    def pms_refund(b, issued, amt, reason, method="Card"):
        rf_no[0] += r.randint(1, 3)
        pms.append({"id": f"RF-{rf_no[0]}", "issued": issued, "booking": b["ref"], "guest": b["guest"], "reason": reason, "method": method,
                    "amount": amt, "staff": r.choice(STAFF)})
        return pms[-1]

    def at(d, h0=8, h1=21):
        return datetime(d.year, d.month, d.day, r.randint(h0, h1), r.randint(0, 59))

    # ---- prior month: two July refunds that settled in August (from July's recon)
    for _ in range(2):
        b = booking()
        charge(b, at(date(2026, 7, r.randint(1, 20))), r.randint(2, 4))
        issued = date(2026, 7, r.randint(30, 31))
        amt = b["nightly"]
        rf_no[0] += r.randint(1, 3)
        row = {"id": f"RF-{rf_no[0]}", "issued": issued, "booking": b["ref"], "amount": amt}
        july.append(row)
        pl = refund_line(b, at(date(2026, 8, r.randint(1, 3))), amt, 0)
        recon.append({"refund_id": row["id"], "booking": b["ref"], "pms": amt, "proc": amt, "status": S_PRIOR, "proc_ids": [pl["id"]], "role": "prior"})
    rf_no[0] += r.randint(4, 9)

    days = sorted(day_in(r, date(2026, 8, 2), date(2026, 8, 26)) for _ in range(20))
    di = iter(days)

    # ---- plain matches: cancellations (full refund, fee returned) and partial refunds (no fee back)
    for k in range(9):
        b = booking()
        d = next(di)
        nights = r.randint(2, 4)
        amt_c, fee_c = charge(b, at(d - timedelta(days=r.randint(6, 40))), nights)
        if k % 3 == 0:
            amt, fee_back, reason = amt_c, fee_c, "Cancellation within policy - full refund"
        else:
            amt, fee_back, reason = b["nightly"] * r.randint(1, nights - 1) if nights > 1 else b["nightly"], 0, r.choice(
                ["Early departure - unused night", "Service recovery - AC outage", "Partial cancellation - one room"])
        p = pms_refund(b, d, amt, reason)
        pl = refund_line(b, at(d + timedelta(days=r.choice([0, 0, 1]))), amt, fee_back)
        recon.append({"refund_id": p["id"], "booking": b["ref"], "pms": amt, "proc": amt, "status": S_MATCH, "proc_ids": [pl["id"]],
                      "role": "full" if fee_back else "plain"})
    # ---- one refund split over two cards
    b = booking()
    d = next(di)
    amt_c, fee_c = charge(b, at(d - timedelta(days=20)), 3)
    amt = b["nightly"] * 3
    p = pms_refund(b, d, amt, "Group cancellation - paid on two cards")
    part = r.randint(35, 65) * amt // 100
    other4 = f"{r.randint(1000, 9999)}"
    p1 = refund_line(b, at(d), part, 0)
    p2 = refund_line(b, at(d), amt - part, 0, last4=other4)
    recon.append({"refund_id": p["id"], "booking": b["ref"], "pms": amt, "proc": amt, "status": S_MATCH, "proc_ids": [p1["id"], p2["id"]], "role": "twocard"})
    # ---- one booking, two partial refunds on different days
    b = booking()
    d1 = next(di)
    charge(b, at(d1 - timedelta(days=15)), 4)
    first = r.randint(40, 90) * 100
    p = pms_refund(b, d1, first, "Service recovery - noisy room")
    pl = refund_line(b, at(d1), first, 0)
    recon.append({"refund_id": p["id"], "booking": b["ref"], "pms": first, "proc": first, "status": S_MATCH, "proc_ids": [pl["id"]], "role": "partial1"})
    d2 = d1 + timedelta(days=r.randint(2, 4))
    p = pms_refund(b, d2, b["nightly"], "Early departure - unused night")
    pl = refund_line(b, at(d2), b["nightly"], 0)
    recon.append({"refund_id": p["id"], "booking": b["ref"], "pms": b["nightly"], "proc": b["nightly"], "status": S_MATCH, "proc_ids": [pl["id"]],
                  "role": "partial2"})
    # ---- failed then retried: matched on the retry
    b = booking()
    d = next(di)
    charge(b, at(d - timedelta(days=12)), 2)
    amt = b["nightly"]
    p = pms_refund(b, d, amt, "Early departure - unused night")
    refund_line(b, at(d), amt, 0, status="failed")
    pl = refund_line(b, at(d + timedelta(days=2)), amt, 0)
    recon.append({"refund_id": p["id"], "booking": b["ref"], "pms": amt, "proc": amt, "status": S_MATCH, "proc_ids": [pl["id"]], "role": "retry"})
    # ---- failed, never retried: not in processor
    b = booking()
    d = next(di)
    charge(b, at(d - timedelta(days=9)), 3)
    amt = b["nightly"] + r.randint(1, 8) * 500
    p = pms_refund(b, d, amt, "Service recovery - late check-in")
    refund_line(b, at(d), amt, 0, status="failed")
    recon.append({"refund_id": p["id"], "booking": b["ref"], "pms": amt, "proc": 0, "status": S_NOPROC, "proc_ids": [], "role": "failed"})
    # ---- keyed amount differs (transposed digits)
    b = booking()
    d = next(di)
    charge(b, at(d - timedelta(days=30)), 4)
    while True:
        amt = r.randint(1001, 1899) * 100
        s = str(amt // 100)
        keyed = int(s[0] + s[2] + s[1] + s[3:]) * 100 if len(s) >= 3 else amt
        if keyed != amt:
            break
    p = pms_refund(b, d, amt, "Partial cancellation - two nights")
    pl = refund_line(b, at(d + timedelta(days=1)), keyed, 0)
    recon.append({"refund_id": p["id"], "booking": b["ref"], "pms": amt, "proc": keyed, "status": S_DIFF, "proc_ids": [pl["id"]], "role": "diff"})
    # ---- refund made in the processor dashboard, never logged in the PMS
    b = booking()
    d = next(di)
    charge(b, at(d - timedelta(days=5)), 2)
    amt = r.randint(5, 15) * 1000
    pl = refund_line(b, at(d), amt, 0)
    pl["desc"] = f"Refund {b['ref']} goodwill - owner"
    recon.append({"refund_id": pl["id"], "booking": b["ref"], "pms": 0, "proc": amt, "status": S_NOPMS, "proc_ids": [pl["id"]], "role": "nopms"})
    # ---- refunds by check: PMS only, not part of the reconciliation
    checks = []
    for _ in range(2):
        b = booking()
        d = next(di)
        checks.append(pms_refund(b, d, r.randint(8, 30) * 1000, "Damage deposit returned", method="Check"))
    # ---- late August, settled in September
    for _ in range(2):
        b = booking()
        d = date(2026, 8, r.randint(28, 31))
        charge(b, at(d - timedelta(days=14)), 3)
        amt = b["nightly"] * r.randint(1, 2)
        p = pms_refund(b, d, amt, "Early departure - unused nights")
        pl = refund_line(b, at(date(2026, 9, r.randint(1, 2))), amt, 0)
        recon.append({"refund_id": p["id"], "booking": b["ref"], "pms": amt, "proc": amt, "status": S_TIMING, "proc_ids": [pl["id"]], "role": "timing"})
    # ---- September's own refunds (next month's reconciliation)
    for _ in range(2):
        b = booking()
        refund_line(b, at(date(2026, 9, r.randint(2, 4))), b["nightly"], 0)
    # ---- noise: other charges and payouts
    for _ in range(26):
        b = booking()
        charge(b, at(day_in(r, date(2026, 8, 1), date(2026, 9, 5))), r.randint(1, 5))
    for d in [date(2026, 8, 1) + timedelta(days=k) for k in range(0, 36, 3)]:
        proc.append({"id": pid("po"), "type": "payout", "status": "paid", "created": datetime(d.year, d.month, d.day, 6, 0), "amount": -r.randint(150000, 900000),
                     "fee": 0, "desc": "Payout to Harbor Trust ****4410", "last4": ""})
    proc.sort(key=lambda x: x["created"])
    # the PMS numbers refunds in the order they are issued
    renum, n0 = {}, int(july[-1]["id"][3:]) + r.randint(4, 9)
    for p in sorted(pms, key=lambda x: (x["issued"], int(x["id"][3:]))):
        n0 += r.randint(1, 3)
        renum[p["id"]] = f"RF-{n0}"
    for p in pms:
        p["id"] = renum[p["id"]]
    for rw in recon:
        rw["refund_id"] = renum.get(rw["refund_id"], rw["refund_id"])
    pms.sort(key=lambda x: (x["issued"], x["id"]))
    variance = sum(rw["pms"] - rw["proc"] for rw in recon)
    return {"pms": pms, "proc": proc, "recon": recon, "july": july, "checks": checks, "variance": variance}


def naive_rows(d: dict) -> list[dict]:
    """Every PMS refund (checks included) against the net of all processor refund lines for its booking in August."""
    out = []
    for p in d["pms"]:
        net = -sum(x["amount"] - x["fee"] for x in d["proc"] if x["type"] == "refund" and p["booking"] in x["desc"] and x["created"].month == 8)
        out.append({"refund_id": p["id"], "booking": p["booking"], "pms": p["amount"], "proc": net,
                    "status": S_MATCH if net == p["amount"] else S_DIFF if net else S_NOPROC})
    return out


def acceptable(d: dict) -> bool:
    full = [rw for rw in d["recon"] if rw["role"] == "full"]
    if not full:
        return False
    return d["variance"] != 0 and len({rw["refund_id"] for rw in d["recon"]}) == len(d["recon"])


# --------------------------------------------------------------------------- emit

def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["refund_id", "booking_ref", "pms_amount", "processor_amount", "difference", "status"]

    def body(rows):
        return [[rw["refund_id"], rw["booking"], f"{rw['pms'] / 100:.2f}", f"{rw['proc'] / 100:.2f}", f"{(rw['pms'] - rw['proc']) / 100:.2f}", rw["status"]]
                for rw in rows]

    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_csv(os.path.join(naive_dir, "refund_recon.csv"), header, body(naive_rows(d)))
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 17)

    # ---- workspace: PMS refund log
    write_csv(os.path.join(ws, "pms_refunds_2026-08.csv"), ["Refund #", "Issued", "Booking", "Guest", "Reason", "Method", "Amount", "Issued by"],
              [[p["id"], p["issued"].strftime("%m/%d/%Y"), p["booking"], p["guest"], p["reason"], p["method"], money_str(p["amount"] / 100, 1), p["staff"]]
               for p in d["pms"]], preamble=["The Larkin House Inn - Refunds issued", "Report period: 08/01/2026 to 08/31/2026"])

    # ---- workspace: processor export
    write_csv(os.path.join(ws, "clearpath_balance_activity_2026-08-01_to_2026-09-05.csv"),
              ["id", "type", "status", "created", "amount", "fee", "net", "currency", "description", "card_last4"],
              [[x["id"], x["type"], x["status"], x["created"].strftime("%Y-%m-%d %H:%M"), f"{x['amount'] / 100:.2f}", f"{x['fee'] / 100:.2f}",
                f"{(x['amount'] - x['fee']) / 100:.2f}", "usd", x["desc"], x["last4"]] for x in d["proc"]], bom=True)

    # ---- workspace: July's reconciliation (the template, and where last month's timing items are)
    jrows = []
    seqj = int(d["july"][0]["id"][3:]) - r.randint(40, 60)
    for _ in range(9):
        seqj += r.randint(2, 6)
        b = f"LH-{r.randint(23700, 24090)}"
        a = r.randint(9, 45) * 1000
        jrows.append([f"RF-{seqj}", b, f"{a / 100:.2f}", f"{a / 100:.2f}", "0.00", "matched"])
    for j in d["july"]:
        jrows.append([j["id"], j["booking"], f"{j['amount'] / 100:.2f}", f"{j['amount'] / 100:.2f}", "0.00", "timing - settled in August"])
    write_csv(os.path.join(ws, "refund_recon_2026-07.csv"), header, jrows)

    # ---- workspace: owner's note
    write_text(os.path.join(ws, "note_refund_recon.txt"),
               "August refund reconciliation - notes to self (and whoever does it this month)\n\n"
               "- July's file is the layout. One line per refund in the PMS log, plus a line for anything the processor refunded that\n"
               "  has no PMS refund. refund_id is our RF number; if the PMS never had it, use the processor's refund id.\n"
               "- Only card refunds go through Clearpath. Refunds we paid by check are not part of this.\n"
               "- Match on the refund amount itself (the amount column), not net. On a full refund Clearpath gives back its fee, so\n"
               "  net will not equal the refund. Charges, payouts and fees in the export are not refunds. A failed refund is not a refund.\n"
               "- A refund can go back to more than one card. Add the pieces up.\n"
               "- The front desk sometimes keys the refund a few days after logging it. The export runs to Sep 5 so late-August\n"
               "  refunds can be found: if it went through in September, it is 'timing - settled in September'. The July\n"
               "  file's timing items should have come through in early August - give each one a line with its July PMS amount\n"
               "  and status 'prior month timing'. Anything else created in September belongs to next month.\n"
               "- Statuses: matched, timing - settled in September, prior month timing, amount differs, not in processor, not in PMS.\n"
               "- Amounts are positive refund amounts. 0.00 where a side has nothing. processor_amount is what actually went through,\n"
               "  wherever it landed. difference = pms_amount minus processor_amount, so the column adds up to what is still\n"
               "  unexplained.\n")

    # ---- reference
    rows = sorted(d["recon"], key=lambda rw: rw["refund_id"])
    write_csv(os.path.join(ref, "refund_recon.csv"), header, body(rows))
    write_csv(os.path.join(sol, "refund_recon.csv"), header, body(rows))
    write_json(os.path.join(ref, "notes.json"), {"variance": f"{d['variance'] / 100:.2f}", "roles": {rw["role"]: rw["refund_id"] for rw in d["recon"]},
                                                  "check_refunds_excluded": [c["id"] for c in d["checks"]]})
    role = {}
    for rw in d["recon"]:
        role.setdefault(rw["role"], rw)
    pins = [role[k]["refund_id"] for k in ("full", "twocard", "retry", "failed", "diff", "nopms", "timing", "prior")]
    write_task_yaml(HERE, {
        "id": "refund-reconciliation", "track": "desk", "category": "bookkeeping",
        "title": "Reconcile August refunds to the card processor",
        "ask": "Can you reconcile August's refunds against Clearpath? The PMS refund log, their export, July's reconciliation and my notes are in the folder. Save it as refund_recon.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"on full refunds such as {role['full']['refund_id']} Clearpath returns its fee, so the net column is smaller than the refund; "
            "matching on net calls them amount differs, and the export also holds charges and payouts (checks: status per refund; "
            "amounts per refund)",
            f"{role['twocard']['refund_id']} went back to two cards: two processor lines that only match the PMS refund added together "
            "(checks: status per refund; amounts per refund)",
            f"booking {role['partial1']['booking']} has two partial refunds on different days, {role['partial1']['refund_id']} and "
            f"{role['partial2']['refund_id']}; keying the reconciliation by booking loses one (checks: one row per refund; row count)",
            f"{role['retry']['refund_id']} failed once and succeeded two days later, while {role['failed']['refund_id']} failed and was never "
            "retried; counting failed lines as refunds doubles one and hides the other (checks: status per refund; variance ties to the "
            "unexplained items)",
            f"{role['timing']['refund_id']} and another late-August refund went through on 1-2 September (timing), and two July refunds "
            "from July's file went through in early August and need prior month timing lines with their July amounts "
            "(checks: status per refund; one row per refund)",
            "two refunds created 2-4 September belong to September's PMS refunds and are not August items, and two PMS refunds were paid "
            "by check and never touch the processor (checks: one row per refund; row count)",
            f"{role['diff']['refund_id']} was keyed into the terminal with transposed digits, and {role['nopms']['refund_id']} is a goodwill "
            "refund the owner made in the dashboard with no PMS entry (checks: status per refund; variance ties to the unexplained items)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "July's columns", "path": "refund_recon.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per refund", "path": "refund_recon.csv", "column": "refund_id", "ref": "refund_recon.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "refund_recon.csv", "equals_ref": "refund_recon.csv"},
            {"type": "csv_values_match", "name": "status per refund", "path": "refund_recon.csv", "ref": "refund_recon.csv", "key": "refund_id",
             "columns": ["status"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": pins},
            {"type": "csv_values_match", "name": "amounts per refund", "path": "refund_recon.csv", "ref": "refund_recon.csv", "key": "refund_id",
             "columns": ["pms_amount", "processor_amount", "difference"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0,
             "must_match_keys": pins},
            {"type": "custom", "name": "variance ties to the unexplained items", "module": "check.py"},
        ],
    })
    print(f"seed={seed} recon rows={len(d['recon'])} pms={len(d['pms'])} proc={len(d['proc'])} variance={d['variance'] / 100:.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a_ = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a_.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a_.seed * 1000 + attempt, a_.naive)
