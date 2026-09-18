#!/usr/bin/env python3
"""loan-schedule-check: a climbing gym's build-out term loan, the credit union's loan history against the note's terms.

    python gen.py [--seed N] [--naive DIR]

Business: Basalt Bouldering Co., a climbing gym that financed its second wall build-out with a ten-year term loan
from a credit union. The outside accountant books loan interest from the lender's split and wants the eight months
of 2026 checked against the note: interest in arrears on the balance after the previous payment, a rate reset on
1 March 2026, an additional principal payment in May and a returned autopay in June.

Traps (each caught by a check, see task.yaml):
  * interest is paid in arrears, so the March payment still carries February's interest at the old rate; the
    credit union charged the new rate a month early and its later splits carry a few cents more each month
                                                                   (checks: interest per payment; overcharge)
  * the May additional principal payment is all principal and lowers June's interest; computing interest on it,
    or leaving it out, moves every later figure                       (checks: interest per payment; balance)
  * the June autopay was returned and paid again three days later; the reversal line carries positive amounts, so
    adding up the payment rows counts June twice                      (check: total interest)
  * the closing-day amortization schedule in the folder has neither the rate change nor the extra payment
                                                                    (checks: balance; total interest)
  * the export runs from September 2025 to September 2026 under a preamble with amounts as text  (check: total interest)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

OLD_RATE = Decimal("0.0685")
NEW_RATES = [Decimal("0.0735"), Decimal("0.0760"), Decimal("0.0785")]
TERM = 120
FIRST_DUE = date(2024, 12, 1)
HOLIDAYS = {date(2025, 1, 1), date(2026, 1, 1), date(2025, 12, 25), date(2025, 9, 1), date(2026, 9, 7)}
NAMES = ["Tomasz Lindqvist", "Leila Haddad", "Kwame Osei", "Ingrid Tanaka", "Marcus Okafor", "Nadia Mensah"]


def cents(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def near_half_cent(x: Decimal) -> bool:
    frac = (x * 100) % 1
    return abs(frac - Decimal("0.5")) < Decimal("0.002")


def pmt(balance: Decimal, rate: Decimal, n: int) -> Decimal:
    i = float(rate) / 12
    p = float(balance) * i / (1 - (1 + i) ** -n)
    return cents(Decimal(str(p)))


def business_day(d: date) -> date:
    while d.weekday() >= 5 or d in HOLIDAYS:
        d += timedelta(days=1)
    return d


def add_months(d: date, k: int) -> date:
    y, m = divmod(d.month - 1 + k, 12)
    return date(d.year + y, m + 1, d.day)


def build(seed: int) -> dict:
    r = rng(seed)
    principal = Decimal(r.randrange(168000, 236000, 500))
    new_rate = r.choice(NEW_RATES)
    pay0 = pmt(principal, OLD_RATE, TERM)
    extra_amt = Decimal(r.choice([10000, 12500, 15000, 17500, 20000]))
    extra_day = date(2026, 5, r.randint(11, 22))
    while extra_day.weekday() >= 5:
        extra_day += timedelta(days=1)

    # due dates from the first payment through September 2026
    dues = [add_months(FIRST_DUE, k) for k in range(22)]
    assert dues[-1] == date(2026, 9, 1)

    def rate_for(due: date, lender: bool) -> Decimal:
        # interest for the month before the due date at the rate in effect for that month
        if lender:
            return OLD_RATE if due < date(2026, 3, 1) else new_rate
        return OLD_RATE if due <= date(2026, 3, 1) else new_rate

    correct, lender = [], []
    cb = lb = principal
    new_pay = None
    bad_half = False
    for due in dues:
        if due == date(2026, 6, 1):
            # the additional principal payment posted in May, before the June payment
            for rows, bal_name in ((correct, "c"), (lender, "l")):
                pass
            cb -= extra_amt
            lb -= extra_amt
            correct.append({"kind": "extra", "due": None, "posted": extra_day, "pay": extra_amt, "rate": None,
                            "open": cb + extra_amt, "int": Decimal("0.00"), "prin": extra_amt, "close": cb})
            lender.append({"kind": "extra", "posted": extra_day, "pay": extra_amt, "int": Decimal("0.00"), "prin": extra_amt, "close": lb})
        if due == date(2026, 4, 1):
            new_pay = pmt(cb, new_rate, TERM - dues.index(due))
        pay = pay0 if due < date(2026, 4, 1) else new_pay
        rc, rl = rate_for(due, False), rate_for(due, True)
        raw_c, raw_l = cb * rc / 12, lb * rl / 12
        bad_half = bad_half or near_half_cent(raw_c) or near_half_cent(raw_l)
        ic, il = cents(raw_c), cents(raw_l)
        opn = cb
        cb = cb - (pay - ic)
        lb = lb - (pay - il)
        posted = business_day(due)
        correct.append({"kind": "regular", "due": due, "posted": posted, "pay": pay, "rate": rc, "open": opn,
                        "int": ic, "prin": pay - ic, "close": cb})
        lender.append({"kind": "regular", "due": due, "posted": posted, "pay": pay, "int": il, "prin": pay - il, "close": lb})
    return {"principal": principal, "new_rate": new_rate, "pay0": pay0, "new_pay": new_pay, "extra_amt": extra_amt,
            "extra_day": extra_day, "correct": correct, "lender": lender, "bad_half": bad_half,
            "officer": r.choice(["Dana Brooks", "Carlos Rivera", "Amanda Price"]), "accountant": r.choice(NAMES),
            "loan_no": f"CL-{r.randint(40000, 49999)}-{r.randint(10, 99)}", "k": r.random()}


def in_scope(row: dict) -> bool:
    d = row["due"] if row["kind"] == "regular" else row["posted"]
    return date(2026, 1, 1) <= d <= date(2026, 8, 31)


def figures(d: dict) -> dict:
    cor = [x for x in d["correct"] if in_scope(x)]
    len_ = [x for x in d["lender"] if in_scope(x)]
    reg_c = [x for x in cor if x["kind"] == "regular"]
    reg_l = [x for x in len_ if x["kind"] == "regular"]
    total_int = sum(x["int"] for x in reg_c)
    lender_int = sum(x["int"] for x in reg_l)
    return {"rows_c": cor, "rows_l": len_, "interest": [x["int"] for x in reg_c], "lender_interest": [x["int"] for x in reg_l],
            "total_interest": total_int, "lender_total": lender_int, "overcharge": lender_int - total_int,
            "balance": cor[-1]["close"], "lender_balance": len_[-1]["close"], "opening": cor[0]["open"]}


def closing_schedule(d: dict) -> list[list]:
    rows, b = [], d["principal"]
    for k in range(TERM):
        due = add_months(FIRST_DUE, k)
        i = cents(b * OLD_RATE / 12)
        pay = d["pay0"] if k < TERM - 1 else b + i
        b = b - (pay - i)
        rows.append([k + 1, due, float(pay), float(i), float(pay - i), float(b)])
    return rows


def acceptable(d: dict) -> bool:
    if d["bad_half"]:
        return False
    f = figures(d)
    # every interest figure in 2026 is distinct from the lender's except January and February
    if sum(1 for a, b in zip(f["interest"], f["lender_interest"]) if a == b) != 2:
        return False
    if f["overcharge"] < 40:
        return False
    # pinned figures stand apart from anything in the closing-day schedule's interest and balance columns
    cs = closing_schedule(d)
    for pin in (f["total_interest"], f["balance"], f["overcharge"]):
        if any(abs(float(pin) - v) <= 0.05 for row in cs for v in row[3:]):
            return False
    # the naive column sum (reversal counted) and the closing schedule total both miss the total
    naive_total = f["lender_total"] + [x for x in f["rows_l"] if x["kind"] == "regular" and x["due"] == date(2026, 6, 1)][0]["int"]
    closing_total = sum(Decimal(str(row[3])) for row in cs if date(2026, 1, 1) <= row[1] <= date(2026, 8, 31))
    for other in (naive_total, closing_total, f["lender_total"]):
        if abs(other - f["total_interest"]) < 1:
            return False
    return len(set(f["interest"])) == 8


# --------------------------------------------------------------------------- deliverable

def workbook(d: dict, rows_c: list[dict], rows_l: list[dict], lender_only: bool = False) -> dict:
    body = []
    first = 2
    for i, (c, l) in enumerate(zip(rows_c, rows_l)):
        rr = first + i
        label = "Additional principal" if c["kind"] == "extra" else "Regular payment"
        opening = float(c["open"]) if i == 0 else f"=I{rr - 1}"
        if lender_only:
            interest, principal = float(l["int"]), float(l["prin"])
            rate = ""
        elif c["kind"] == "extra":
            interest, principal, rate = 0, f"=D{rr}-G{rr}", ""
        else:
            interest, principal, rate = f"=ROUND(F{rr}*E{rr}/12,2)", f"=D{rr}-G{rr}", float(c["rate"])
        body.append([c["due"].isoformat() if c["due"] else "", c["posted"].isoformat(), label, float(c["pay"]), rate, opening,
                     interest, principal, f"=F{rr}-H{rr}", float(l["int"]), float(l["prin"]), float(l["close"]), f"=J{rr}-G{rr}"])
    last = first + len(body) - 1
    tr = last + 1
    body.append(["Total Jan-Aug 2026", "", "", f"=SUM(D{first}:D{last})", "", "", f"=SUM(G{first}:G{last})", f"=SUM(H{first}:H{last})",
                 "", f"=SUM(J{first}:J{last})", f"=SUM(K{first}:K{last})", "", f"=SUM(M{first}:M{last})"])
    body.append([])
    body.append(["Principal balance after the August payment, per the note", "", "", "", "", "", "", "", f"=I{last}"])
    body.append(["Principal balance after the August payment, per the credit union", "", "", "", "", "", "", "", "", "", "", f"=L{last}"])
    body.append(["Interest overcharged by the credit union", "", "", "", "", "", "", "", "", "", "", "", f"=M{tr}"])
    return {"Loan check": {
        "header": ["Due date", "Posted", "Type", "Payment", "Rate", "Opening balance", "Interest (per note)", "Principal (per note)",
                   "Closing balance (per note)", "Lender interest", "Lender principal", "Lender balance", "Interest difference"],
        "rows": body, "number_formats": {c: "#,##0.00" for c in "DFGHIJKLM"},
        "widths": {"A": 12, "B": 12, "C": 20, "F": 16, "G": 16, "H": 16, "I": 20, "L": 16, "M": 18}, "freeze": "A2"}}


def naive_workbook(d: dict) -> dict:
    """Copy the credit union's split for every 2026 row of the export, returned payment and all."""
    rows = []
    for x in d["lender"]:
        if not in_scope(x):
            continue
        rows.append([x["posted"].isoformat(), "Payment" if x["kind"] == "regular" else "Principal", float(x["pay"]), float(x["int"]),
                     float(x["prin"]), float(x["close"])])
        if x["kind"] == "regular" and x["due"] == date(2026, 6, 1):
            rows.append([x["posted"].isoformat(), "Payment", float(x["pay"]), float(x["int"]), float(x["prin"]), float(x["close"])])
    n = len(rows) + 1
    rows.append(["Total", "", f"=SUM(C2:C{n})", f"=SUM(D2:D{n})", f"=SUM(E2:E{n})", f"=F{n}"])
    return {"Loan": {"header": ["Date", "Type", "Amount", "Interest", "Principal", "Balance"], "rows": rows}}


# --------------------------------------------------------------------------- emit

def export_rows(d: dict) -> list[list]:
    """The credit union's loan history, 1 Sep 2025 to 10 Sep 2026, in its own words."""
    out = []
    start_bal = None
    for x in d["lender"]:
        if x["kind"] == "regular" and x["due"] < date(2025, 9, 1):
            start_bal = x["close"]
    out.append(["08/31/2025", "BALANCE FORWARD", "", "", "", "", money_str(float(start_bal), 0)])
    for x in d["lender"]:
        if x["kind"] == "regular" and x["due"] < date(2025, 9, 1):
            continue
        if x["kind"] == "extra":
            out.append([x["posted"].strftime("%m/%d/%Y"), "ADDITIONAL PRINCIPAL - ONLINE", "Principal only", money_str(float(x["pay"]), 1),
                        money_str(0.0, 1), money_str(float(x["prin"]), 1), money_str(float(x["close"]), 0)])
            continue
        desc = "AUTOPAY LOAN PAYMENT"
        if x["due"] == date(2026, 6, 1):
            before = x["close"] + x["prin"]
            out.append([x["posted"].strftime("%m/%d/%Y"), desc, "Payment", money_str(float(x["pay"]), 1), money_str(float(x["int"]), 1),
                        money_str(float(x["prin"]), 1), money_str(float(x["close"]), 0)])
            ret = x["posted"] + timedelta(days=2)
            out.append([ret.strftime("%m/%d/%Y"), "PAYMENT RETURNED - NSF R01", "Reversal", money_str(float(x["pay"]), 1),
                        money_str(float(x["int"]), 1), money_str(float(x["prin"]), 1), money_str(float(before), 0)])
            again = x["posted"] + timedelta(days=3)
            out.append([again.strftime("%m/%d/%Y"), "LOAN PAYMENT - ONLINE BANKING", "Payment", money_str(float(x["pay"]), 1),
                        money_str(float(x["int"]), 1), money_str(float(x["prin"]), 1), money_str(float(x["close"]), 0)])
            continue
        out.append([x["posted"].strftime("%m/%d/%Y"), desc, "Payment", money_str(float(x["pay"]), 1), money_str(float(x["int"]), 1),
                    money_str(float(x["prin"]), 1), money_str(float(x["close"]), 0)])
    return out


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    f = figures(d)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_xlsx(os.path.join(naive_dir, "loan_check.xlsx"), naive_workbook(d), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    acct = d["accountant"]
    acct_first = acct.split()[0]
    new_rate_pct = f"{float(d['new_rate']) * 100:.2f}%"

    write_csv(os.path.join(ws, "cascade_cu_loan_history_2025-09-01_to_2026-09-10.csv"),
              ["Date", "Description", "Transaction Type", "Amount", "To Interest", "To Principal", "Principal Balance"],
              export_rows(d),
              preamble=["Cascade Credit Union - Commercial Loan Activity",
                        f"Loan {d['loan_no']}  BASALT BOULDERING CO  Term loan - equipment and build-out",
                        "Activity from 09/01/2025 to 09/10/2026"], bom=True, crlf=True)

    write_text(os.path.join(ws, "loan_terms_summary.txt"),
               f"CASCADE CREDIT UNION - COMMERCIAL LENDING\n"
               f"Loan terms summary (provided at closing, 15 October 2024)\n\n"
               f"Borrower:            Basalt Bouldering Co.\n"
               f"Loan number:         {d['loan_no']}\n"
               f"Original principal:  ${float(d['principal']):,.2f}\n"
               f"Term:                120 monthly payments, first payment due 1 December 2024\n"
               f"Initial rate:        6.85% per year, fixed through 28 February 2026\n"
               f"Rate adjustment:     on 1 March 2026 and every 36 months after, to WSJ Prime plus 0.35%\n"
               f"Initial payment:     ${float(d['pay0']):,.2f} per month\n\n"
               "How payments are applied\n"
               "  1. Payments are due on the 1st of each month. A payment received by the 10th is on time.\n"
               "  2. Interest is paid in arrears. Each monthly payment pays the interest for the calendar month before its\n"
               "     due date, at the rate in effect for that month.\n"
               "  3. That interest is the unpaid principal balance after the previous payment, times the annual rate,\n"
               "     divided by 12, rounded to the nearest cent. The rest of the payment reduces principal.\n"
               "  4. Additional principal payments are applied entirely to principal on the day they are received. They\n"
               "     do not change the monthly payment or the next due date.\n"
               "  5. When the rate adjusts, the monthly payment is recalculated and the new amount is due from the\n"
               "     payment after the adjustment date.\n")

    write_text(os.path.join(ws, "rate_change_notice_2026-02-02.txt"),
               "Cascade Credit Union\n"
               "Notice of interest rate and payment change\n\n"
               "2 February 2026\n\n"
               f"Basalt Bouldering Co.\nRe: Loan {d['loan_no']}\n\n"
               f"The interest rate on your loan will change on 1 March 2026 from 6.85% to {new_rate_pct} (WSJ Prime plus 0.35%).\n"
               f"Interest accruing from 1 March 2026 is charged at the new rate.\n\n"
               f"Your monthly payment will change from ${float(d['pay0']):,.2f} to ${float(d['new_pay']):,.2f}, beginning with the payment due\n"
               "1 April 2026. If you pay by autopay, the new amount will be drawn automatically.\n\n"
               f"Questions? Call your loan officer, {d['officer']}, at (208) 555-0148.\n")

    write_email_thread(os.path.join(ws, "email_from_accountant.txt"), [
        {"from": f"{acct} <{acct.split()[0].lower()}@mossbank.cpa>", "to": "Jess Harlan <jess@basaltbouldering.com>",
         "date": "Mon, 14 Sep 2026 09:05", "subject": "Gym loan - can you check the credit union's numbers?",
         "body": (f"Hi Jess,\n\nI have been booking the loan straight from the credit union's split, but with the rate reset in March and "
                  "the extra $" + f"{float(d['extra_amt']):,.0f}" + " you put on it in May I would like it checked before we do the "
                  "third-quarter close.\n\n"
                  "For each payment from January through August, work out the interest and principal the way the loan terms say "
                  "they should be split and put it beside what the credit union actually charged. I need the total interest for "
                  "those eight months, the principal balance after the August payment, and how much extra interest they have charged "
                  "us, if any - I will ask them for a correction. Keep the math live so I can follow it.\n\n"
                  "The old amortization table from closing is in the folder too, for what it is worth.\n\n"
                  f"Thanks,\n{acct_first}")},
        {"from": "Jess Harlan <jess@basaltbouldering.com>", "to": f"{acct} <{acct.split()[0].lower()}@mossbank.cpa>",
         "date": "Mon, 14 Sep 2026 10:22", "subject": "RE: Gym loan - can you check the credit union's numbers?",
         "body": ("Sure. I downloaded the loan activity from online banking and put the terms sheet and the rate notice in the folder.\n\n"
                  "FYI the June autopay bounced because I had moved money to savings for the new wall - I paid it again online a "
                  "few days later, well inside the grace period.\n\nJess")}])

    write_xlsx(os.path.join(ws, "amortization_schedule_at_closing.xlsx"), {"Schedule": {
        "merged_title": f"Amortization schedule - loan {d['loan_no']} - prepared 10/15/2024",
        "preamble": [["Principal", float(d["principal"]), "Rate", 0.0685, "Payments", 120]],
        "header": ["Pmt #", "Due date", "Payment", "Interest", "Principal", "Balance"],
        "rows": closing_schedule(d), "number_formats": {c: "#,##0.00" for c in "CDEF"}, "widths": {"B": 12, "F": 14}}},
        creator="Cascade Credit Union")

    # ---- reference
    rows_c, rows_l = f["rows_c"], f["rows_l"]
    write_csv(os.path.join(ref, "schedule.csv"), ["due_date", "posted", "type", "payment", "rate", "opening", "interest", "principal",
                                                  "closing", "lender_interest", "lender_principal", "lender_balance"],
              [[c["due"].isoformat() if c["due"] else "", c["posted"].isoformat(), c["kind"], f"{c['pay']:.2f}",
                f"{c['rate']}" if c["rate"] else "", f"{c['open']:.2f}", f"{c['int']:.2f}", f"{c['prin']:.2f}", f"{c['close']:.2f}",
                f"{l['int']:.2f}", f"{l['prin']:.2f}", f"{l['close']:.2f}"] for c, l in zip(rows_c, rows_l)])
    write_json(os.path.join(ref, "notes.json"), {
        "interest_by_payment": [float(x) for x in f["interest"]], "total_interest": float(f["total_interest"]),
        "lender_total_interest": float(f["lender_total"]), "overcharge": float(f["overcharge"]), "balance_after_august": float(f["balance"]),
        "lender_balance_after_august": float(f["lender_balance"]), "new_rate": float(d["new_rate"]), "new_payment": float(d["new_pay"]),
        "extra_principal": float(d["extra_amt"]), "extra_date": d["extra_day"].isoformat()})

    write_xlsx(os.path.join(sol, "loan_check.xlsx"), workbook(d, rows_c, rows_l), creator="Mossbank CPA")

    write_task_yaml(HERE, {
        "id": "loan-schedule-check", "track": "desk", "category": "bookkeeping",
        "title": "Check the gym loan's interest and principal split",
        "ask": (f"Can you check our gym loan against what the credit union has been charging? {acct_first}'s email says what the books need, "
                "and the loan paperwork and activity download are in the folder. Save it as loan_check.xlsx.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            f"interest is paid in arrears, so the payment due 1 March 2026 still carries February's interest at 6.85%; the credit union "
            f"charged {new_rate_pct} on it, a month early, and every later split carries a few cents more interest on its higher balance "
            "(checks: interest per payment, one line; interest overcharged by the credit union)",
            f"the {float(d['extra_amt']):,.2f} additional principal payment on {d['extra_day'].isoformat()} is all principal and lowers "
            "June's interest; charging interest on it as if it were a payment, or leaving it out, moves June to August "
            "(checks: interest per payment, one line; principal balance after August)",
            "the June autopay was returned NSF and paid again three days later; the reversal line carries positive amounts, so adding "
            "up the payment rows counts June's interest twice (check: total interest Jan-Aug)",
            "the closing-day amortization table has neither the rate change nor the extra payment, and its balances drift further off "
            "every month from May (checks: principal balance after August; total interest Jan-Aug)",
            "the activity download runs from a September 2025 balance forward to a September 2026 payment, under a three-line preamble "
            "with a BOM, CRLF endings and amounts as '$1,234.56' text (check: total interest Jan-Aug)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "loan_check.xlsx", "min_count": 16},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "loan_check.xlsx"},
            {"type": "custom", "name": "interest per payment, one line", "module": "check.py"},
            {"type": "xlsx_value_present", "name": "total interest Jan-Aug", "path": "loan_check.xlsx",
             "expected": float(f["total_interest"]), "rel_tol": 1e-06, "near_text": "interest"},
            {"type": "xlsx_value_present", "name": "principal balance after August", "path": "loan_check.xlsx",
             "expected": float(f["balance"]), "rel_tol": 1e-07, "near_text": "balance"},
            {"type": "xlsx_value_present", "name": "interest overcharged by the credit union", "path": "loan_check.xlsx",
             "expected": float(f["overcharge"]), "rel_tol": 1e-05, "near_text": "interest"},
        ],
    })
    print(f"seed={seed} principal={d['principal']} rate={d['new_rate']} total_int={f['total_interest']} lender={f['lender_total']} "
          f"over={f['overcharge']} bal={f['balance']} lender_bal={f['lender_balance']}")


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
