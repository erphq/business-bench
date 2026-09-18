#!/usr/bin/env python3
"""prepaid-amortization: a commercial cleaning contractor's 2026 prepaid expense schedule.

    python gen.py [--seed N] [--naive DIR]

Business: Brightline Commercial Cleaning pays its insurance, route software, association dues and equipment service
contract a year at a time and books the payments to 1450 Prepaid expenses. Nobody booked amortization during 2026.
The CPA wants the 2026 schedule: amortization by days of coverage, the last covered month taking the rounding, the
register's dates over the GL memo, a cancelled policy whose short-rate refund arrives the following month, and last
year's closing schedule for the items that carry in.

Traps (each caught by a check, see task.yaml):
  * coverage that starts mid-month earns only its days in the first month          (checks: Keystone auto; expense by month)
  * the workers' comp policy was bound ten days late; the GL memo still shows 1 April  (check: Cascadia workers' comp)
  * the cancelled policy stops the day before cancellation; the refund arrives the next month and the unused premium
    it does not cover is expensed in the cancellation month                        (checks: Summit floater; balance)
  * two 2025 items carry in from last year's schedule with their remaining balance    (checks: expense by month; total)
  * a lease security deposit is sitting in 1450 and is not a prepaid expense          (checks: balance; total)
"""
from __future__ import annotations

import argparse
import calendar
import os
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from openpyxl.utils import get_column_letter  # noqa: E402

D = Decimal
FY = 2026
LABELS = [f"{FY}-{m:02d}" for m in range(1, 13)]


def c2(x) -> Decimal:
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def month_iter(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def schedule(amount: Decimal, start: date, end: date, stop: date | None = None) -> dict:
    """{(y, m): expense}. Days of coverage in the month / days in the coverage period, rounded; last covered month takes
    the rest. With `stop` (last covered day after a cancellation) months after it are dropped and no residual applies."""
    total_days = (end - start).days + 1
    months = list(month_iter(start, end))
    out = {}
    for y, m in months:
        a = max(start, date(y, m, 1))
        b = min(end, date(y, m, calendar.monthrange(y, m)[1]))
        if stop is not None:
            if a > stop:
                break
            b = min(b, stop)
        days = (b - a).days + 1
        out[(y, m)] = c2(amount * days / total_days)
    if stop is None:
        last = months[-1]
        out[last] = amount - sum(v for k, v in out.items() if k != last)
    return out


def build(seed: int) -> dict:
    r = rng(seed)
    items = []

    def item(key, vendor, what, ref, amount, start, end, paid, gl_memo=None, cancel=None):
        it = {"key": key, "vendor": vendor, "what": what, "ref": ref, "amount": D(amount), "start": start, "end": end, "paid": paid,
              "gl_memo": gl_memo, "cancel": cancel}
        items.append(it)
        return it

    gl_start = date(2025, 7, 1)
    item("carry_gl", "Harborline Mutual Insurance", "General liability policy", f"GL-{r.randint(400000, 499999)}",
         f"{r.randint(9000, 14000)}.00", gl_start, date(2026, 6, 30), date(2025, 6, 24))
    sw_start = date(2025, 10, r.randint(10, 20))
    item("carry_sw", "RouteWise Software", "Route planning software - annual", f"RW-{r.randint(10000, 99999)}",
         f"{r.randint(3800, 6200)}.00", sw_start, sw_start.replace(year=2026) - timedelta(days=1), sw_start - timedelta(days=5))
    item("carry_done", "Northwest Cleaning Contractors Assn", "2025 membership dues", "NWCCA-2025", "2400.00", date(2025, 1, 1), date(2025, 12, 31),
         date(2025, 1, 6))
    auto_start = date(2026, 3, r.randint(12, 20))
    item("midmonth", "Keystone Commercial Auto", "Commercial auto policy - 9 vans", f"KCA-{r.randint(200000, 299999)}",
         f"{r.randint(18000, 26000)}.00", auto_start, auto_start.replace(year=2027) - timedelta(days=1), auto_start - timedelta(days=r.randint(3, 8)))
    wc_memo_start = date(2026, 4, 1)
    wc_start = date(2026, 4, r.randint(8, 13))
    item("late_bind", "Cascadia Workers' Comp Fund", "Workers' compensation policy", f"WC-{r.randint(700000, 799999)}",
         f"{r.randint(7000, 12000)}.00", wc_start, wc_start.replace(year=2027) - timedelta(days=1), date(2026, 3, r.randint(24, 30)),
         gl_memo=(wc_memo_start, wc_memo_start.replace(year=2027) - timedelta(days=1)))
    fl_start = date(2026, 2, 1)
    cancel_on = date(2026, r.choice([8, 9]), r.randint(8, 20))
    item("cancel", "Summit Specialty Underwriters", "Inland marine floater - floor machines", f"SSU-{r.randint(30000, 39999)}",
         f"{r.randint(3200, 5800)}.00", fl_start, date(2027, 1, 31), date(2026, 1, r.randint(22, 29)), cancel=cancel_on)
    item("dues", "Northwest Cleaning Contractors Assn", "2026 membership dues", "NWCCA-2026", "2650.00", date(2026, 1, 1), date(2026, 12, 31),
         date(2026, 1, r.randint(5, 9)))
    ms_start = date(2026, 6, 1)
    item("service", "ScrubPro Equipment Service", "Floor equipment service contract", f"SP-{r.randint(1000, 9999)}",
         f"{r.randint(4500, 7000)}.00", ms_start, date(2027, 5, 31), date(2026, 5, r.randint(18, 28)))

    # ---- truth
    rows = []
    for it in items:
        stop = it["cancel"] - timedelta(days=1) if it["cancel"] else None
        sch = schedule(it["amount"], it["start"], it["end"], stop)
        before = sum(v for (y, m), v in sch.items() if y < FY)
        months = [sch.get((FY, m), D("0")) for m in range(1, 13)]
        refund = D("0")
        refund_date = None
        if it["cancel"]:
            unused = it["amount"] - sum(sch.values())
            refund = c2(unused * D("0.85"))
            months[it["cancel"].month - 1] += unused - refund
            refund_date = it["cancel"] + timedelta(days=r.randint(24, 34))
            it["refund"], it["refund_date"], it["unused"] = refund, refund_date, unused
        opening = it["amount"] - before if it["paid"].year < FY else D("0")
        additions = it["amount"] if it["paid"].year == FY else D("0")
        total = sum(months)
        closing = opening + additions - refund - total
        rows.append({"it": it, "before": before, "months": months, "opening": opening, "additions": additions, "refund": refund,
                     "total": total, "closing": closing, "sched": sch})
    deposit = {"vendor": "Riverside Industrial Properties", "amount": D(f"{r.choice([4200, 4800, 5400])}.00"), "date": date(2026, 8, 3)}
    monthly = [sum(rw["months"][i] for rw in rows) for i in range(12)]
    return {"rows": rows, "deposit": deposit, "monthly": monthly, "total": sum(monthly), "closing": sum(rw["closing"] for rw in rows),
            "opening": sum(rw["opening"] for rw in rows), "k": r.random()}


def naive_rows(d: dict) -> dict:
    """Twelve equal months from the month paid, GL memo dates, cancellation ignored, deposit included."""
    out = {}
    for rw in d["rows"]:
        it = rw["it"]
        per = c2(it["amount"] / 12)
        m0 = it["paid"].year * 12 + it["paid"].month - 1
        out[it["key"]] = sum(per for k in range(12) if (m0 + k) // 12 == FY)
    out["deposit"] = c2(d["deposit"]["amount"] / 12) * (12 - d["deposit"]["date"].month + 1)
    return out


def acceptable(d: dict) -> bool:
    by = {rw["it"]["key"]: rw for rw in d["rows"]}
    nv = naive_rows(d)
    for key in ("midmonth", "late_bind", "cancel"):
        rw = by[key]
        others = [rw["opening"], rw["additions"], rw["refund"], rw["closing"], rw["it"]["amount"]] + rw["months"]
        if any(abs(rw["total"] - o) <= D("1") for o in others):
            return False
        if abs(nv[key] - rw["total"]) < 20:
            return False
    # the late bind moves the figure by more than a dollar compared with the memo dates
    lb = by["late_bind"]["it"]
    memo = schedule(lb["amount"], lb["gl_memo"][0], lb["gl_memo"][1])
    if abs(sum(v for (y, m), v in memo.items() if y == FY) - by["late_bind"]["total"]) < 50:
        return False
    if len(set(d["monthly"])) < 12:
        return False
    if abs(d["closing"] - d["total"]) < 100:
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def workbook(d: dict) -> dict:
    rows = []
    first_m = 9
    cL, cR = get_column_letter(first_m), get_column_letter(first_m + 11)
    tot_c, close_c = get_column_letter(first_m + 12), get_column_letter(first_m + 13)
    n = len(d["rows"])
    for i, rw in enumerate(d["rows"], start=2):
        it = rw["it"]
        last_day = (it["cancel"] - timedelta(days=1)) if it["cancel"] else it["end"]
        rows.append([it["vendor"], it["what"], it["start"].isoformat(), last_day.isoformat(), float(it["amount"]), float(rw["opening"]),
                     float(rw["additions"]), float(rw["refund"])] + [float(v) for v in rw["months"]]
                    + [f"=SUM({cL}{i}:{cR}{i})", f"=F{i}+G{i}-H{i}-{tot_c}{i}"])
    tr = n + 2
    rows.append(["Total", "", "", "", ""] + [f"=SUM({get_column_letter(j)}2:{get_column_letter(j)}{n + 1})" for j in range(6, first_m + 14)])
    roll = []
    for i in range(12):
        er = i + 2
        col = get_column_letter(first_m + i)
        additions = sum(rw["additions"] for rw in d["rows"] if rw["it"]["paid"].year == FY and rw["it"]["paid"].month == i + 1)
        refunds = sum(rw["refund"] for rw in d["rows"] if rw["it"].get("refund_date") and rw["it"]["refund_date"].month == i + 1)
        roll.append([LABELS[i], f"=Schedule!F{tr}" if i == 0 else f"=F{er - 1}", float(additions), float(refunds),
                     f"=Schedule!{col}{tr}", f"=B{er}+C{er}-D{er}-E{er}"])
    roll.append(["Total 2026", "", "=SUM(C2:C13)", "=SUM(D2:D13)", "=SUM(E2:E13)", "=F13"])
    money = {get_column_letter(j): "#,##0.00" for j in range(5, first_m + 14)}
    return {
        "Schedule": {"header": ["Vendor", "Item", "Coverage start", "Last covered day", "Amount paid", "Balance 2026-01-01", "Paid in 2026",
                                "Refund received"] + LABELS + ["Expense 2026", "Balance 2026-12-31"],
                     "rows": rows, "number_formats": money, "widths": {"A": 30, "B": 36}, "freeze": "C2"},
        "Roll-forward": {"header": ["Month", "Opening prepaid balance", "Paid", "Refunds", "Amortization expense", "Closing prepaid balance"],
                         "rows": roll, "number_formats": {c: "#,##0.00" for c in "BCDEF"}, "widths": {"B": 22, "E": 22, "F": 22}},
    }


def naive_workbook(d: dict) -> dict:
    nv = naive_rows(d)
    rows = [[rw["it"]["vendor"], rw["it"]["what"], float(rw["it"]["amount"]), float(nv[rw["it"]["key"]])] for rw in d["rows"] if rw["it"]["paid"].year == FY]
    rows.append([d["deposit"]["vendor"], "Deposit", float(d["deposit"]["amount"]), float(nv["deposit"])])
    k = len(rows) + 1
    rows.append(["Total", "", f"=SUM(C2:C{k})", f"=SUM(D2:D{k})"])
    return {"Prepaids": {"header": ["Vendor", "Item", "Paid", "2026 expense"], "rows": rows}}


# --------------------------------------------------------------------------- emit

def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_xlsx(os.path.join(naive_dir, "prepaids.xlsx"), naive_workbook(d), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 13)
    by = {rw["it"]["key"]: rw for rw in d["rows"]}

    # ---- GL detail for 1450
    gl = []
    for rw in d["rows"]:
        it = rw["it"]
        if it["paid"].year != FY:
            continue
        s, e = it["gl_memo"] if it["gl_memo"] else (it["start"], it["end"])
        gl.append([it["paid"], "Bill Payment (Check)", "", it["vendor"],
                   f"{it['ref']} {it['what'].split(' - ')[0].lower()} {s.strftime('%m/%d/%y')}-{e.strftime('%m/%d/%y')}", it["amount"], ""])
    gl.append([d["deposit"]["date"], "Bill Payment (Check)", "", d["deposit"]["vendor"],
               "Security deposit - Unit 4 warehouse lease", d["deposit"]["amount"], ""])
    cn = by["cancel"]["it"]
    gl.append([cn["refund_date"], "Deposit", "", cn["vendor"], f"Return premium - {cn['ref']} cancelled eff {cn['cancel'].strftime('%m/%d/%y')}",
               "", cn["refund"]])
    gl.sort(key=lambda x: x[0])
    chk = r.randint(8100, 8400)
    for x in gl:
        if x[1].startswith("Bill Payment"):
            chk += r.randint(9, 60)
            x[2] = str(chk)
    bal = d["opening"]
    glrows = [["", "", "", "", "Beginning Balance", "", "", f"{bal:,.2f}"]]
    for when, typ, num, name, memo, debit, credit in gl:
        bal = bal + (debit or 0) - (credit or 0)
        glrows.append([when.strftime("%m/%d/%Y"), typ, num, name, memo, f"{debit:,.2f}" if debit != "" else "",
                       f"{credit:,.2f}" if credit != "" else "", f"{bal:,.2f}"])
    glrows.append(["", "", "", "", "Total for 1450 Prepaid Expenses", f"{sum(x[5] for x in gl if x[5] != ''):,.2f}",
                   f"{sum(x[6] for x in gl if x[6] != ''):,.2f}", f"{bal:,.2f}"])
    write_csv(os.path.join(ws, "gl_detail_1450_prepaid_expenses_2026.csv"), ["Date", "Transaction Type", "Num", "Name", "Memo/Description",
                                                                             "Debit", "Credit", "Balance"],
              glrows, preamble=["Brightline Commercial Cleaning LLC", "General Ledger - 1450 Prepaid Expenses", "January 1 - December 31, 2026", ""],
              crlf=True)

    # ---- register
    reg = []
    for rw in d["rows"]:
        it = rw["it"]
        status = "Active"
        if it["end"] < date(2026, 1, 1):
            status = "Expired"
        if it["cancel"]:
            status = f"Cancelled effective {it['cancel'].strftime('%m/%d/%Y')} (short-rate)"
        note = ""
        if it["key"] == "late_bind":
            note = f"Bound late - effective date moved from {it['gl_memo'][0].strftime('%m/%d')} per final dec page"
        reg.append([it["vendor"], it["what"], it["ref"], it["start"], it["end"], f"${it['amount']:,.2f}", status, note])
    r.shuffle(reg)
    write_xlsx(os.path.join(ws, "insurance_and_contracts_register.xlsx"), {"Register": {
        "merged_title": "Insurance policies and annual contracts",
        "preamble": [["Maintained by the office manager from declarations pages and signed contracts.", "", "", "", "", "", "", ""]],
        "header": ["Vendor", "Coverage / contract", "Policy or contract #", "Effective", "Expires", "Premium / price", "Status", "Notes"],
        "rows": reg, "widths": {"A": 32, "B": 38, "C": 16, "D": 12, "E": 12, "F": 14, "G": 36, "H": 48}}}, creator="Office")

    # ---- last year's closing schedule
    prev = []
    for rw in d["rows"]:
        it = rw["it"]
        if it["paid"].year >= FY:
            continue
        m25 = [float(rw["sched"].get((2025, m), D("0"))) for m in range(1, 13)]
        prev.append([it["vendor"], it["what"], it["start"], it["end"], float(it["amount"])] + m25
                    + [float(sum(rw["sched"].get((2025, m), D("0")) for m in range(1, 13))), float(it["amount"] - rw["before"])])
    write_xlsx(os.path.join(ws, "prepaid_schedule_2025_final.xlsx"), {"2025": {
        "merged_title": "Prepaid expenses - 2025 amortization (final, tied to the 12/31/2025 trial balance)",
        "header": ["Vendor", "Item", "Start", "End", "Amount"] + [f"2025-{m:02d}" for m in range(1, 13)] + ["2025 expense", "Balance 12/31/2025"],
        "rows": prev, "widths": {"A": 30, "B": 34}}}, creator="Whitfield CPA")

    write_email_thread(os.path.join(ws, "email_from_cpa.txt"), [
        {"from": "Graham Okafor <graham@okaforcpa.com>", "to": "Tina Brooks <tina@brightlineclean.com>", "date": "Tue, 12 Jan 2027 08:47",
         "subject": "Year-end: prepaid expenses",
         "body": ("Hi Tina,\n\nNo amortization went through 1450 during 2026, so I need the 2026 prepaid schedule before I can close the year. "
                  "Please use the same method as the 2025 schedule:\n\n"
                  "- Each policy or contract is expensed by days of coverage: for each month, the amount paid times the days covered in that "
                  "month, divided by the days in the whole coverage period (count the effective date and the expiry date), rounded to the cent. "
                  "The last month of coverage takes whatever is left so each item expenses exactly what was paid.\n"
                  "- Use the dates in the register. It is kept from the final declarations pages, so where a GL memo disagrees, the register wins.\n"
                  "- A cancelled policy covers through the day before its cancellation date and nothing after. The return premium comes off the "
                  "prepaid balance when the check arrives; whatever is left of that policy's unused premium that the refund does not cover is "
                  "expensed in the month of cancellation.\n"
                  "- Anything in 1450 that is not a prepaid expense should not be on the schedule - tell me and I will reclass it.\n\n"
                  "What I need: every item with its balance at 1 January, what was paid in 2026, refunds, the expense for each month and "
                  "the balance at 31 December, plus the monthly totals and a total for the year. Please keep it live.\n\n"
                  "Thanks,\nGraham")}])

    # ---- reference
    write_csv(os.path.join(ref, "items.csv"), ["vendor", "item", "opening", "paid_2026", "refund", "expense_2026", "closing"],
              [[rw["it"]["vendor"], rw["it"]["what"], f"{rw['opening']:.2f}", f"{rw['additions']:.2f}", f"{rw['refund']:.2f}", f"{rw['total']:.2f}",
                f"{rw['closing']:.2f}"] for rw in d["rows"]])
    write_json(os.path.join(ref, "notes.json"), {"expense_by_month": {LABELS[i]: float(d["monthly"][i]) for i in range(12)},
                                                  "total_2026": float(d["total"]), "closing_2026_12_31": float(d["closing"]),
                                                  "opening_2026_01_01": float(d["opening"]), "excluded_deposit": float(d["deposit"]["amount"])})
    write_xlsx(os.path.join(sol, "prepaids.xlsx"), workbook(d), creator="Brightline Commercial Cleaning")

    def pin(name, key, near):
        exp = float(by[key]["total"])
        return {"type": "xlsx_value_present", "name": name, "path": "prepaids.xlsx", "expected": exp, "rel_tol": round(0.05 / exp, 9),
                "rounding": "amortized by days of coverage, rounded to the cent per month", "near_text": near}

    mm, lb, cn = by["midmonth"]["it"], by["late_bind"]["it"], by["cancel"]["it"]
    write_task_yaml(HERE, {
        "id": "prepaid-amortization", "track": "desk", "category": "bookkeeping",
        "title": "2026 prepaid expense amortization schedule",
        "ask": "Graham needs our 2026 prepaid expense schedule to close the year - his email explains the method. Save it as prepaids.xlsx.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the Keystone auto policy starts {mm['start'].isoformat()}, so March earns only its days of coverage and the policy runs into "
            "March 2027; twelve equal months from the payment month overstates 2026 (checks: Keystone auto 2026 expense; expense by month, one line)",
            f"the GL memo dates the Cascadia workers' comp policy from {lb['gl_memo'][0].isoformat()}, but the register (which the email says "
            f"wins) shows it was bound late and effective {lb['start'].isoformat()} (check: Cascadia workers' comp 2026 expense)",
            f"the Summit floater was cancelled effective {cn['cancel'].isoformat()}: expense stops the day before, the {cn['refund']:,.2f} "
            f"return premium does not arrive until {cn['refund_date'].isoformat()}, and the {cn['unused'] - cn['refund']:,.2f} of unused "
            "premium it does not cover is expensed in the cancellation month; running the policy all year or dropping the loss is wrong "
            "(checks: Summit floater 2026 expense; balance at 31 December)",
            "the general liability policy and the route software started in 2025 and carry into 2026 with the balances on last year's "
            "schedule, which the GL shows only as a beginning balance (checks: expense by month, one line; total 2026 expense)",
            f"a {d['deposit']['amount']:,.2f} warehouse lease security deposit was booked to 1450 and is not a prepaid expense "
            "(checks: balance at 31 December; total 2026 expense)",
            "the GL export has a four-line preamble, a beginning-balance row and a total row, CRLF endings and amounts as text; the "
            "register's premiums are '$1,234.00' text under a merged title and a note row (check: total 2026 expense)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "prepaids.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "prepaids.xlsx"},
            {"type": "custom", "name": "expense by month, one line", "module": "check.py"},
            {"type": "xlsx_value_present", "name": "total 2026 expense", "path": "prepaids.xlsx", "expected": float(d["total"]),
             "rel_tol": round(0.05 / float(d["total"]), 9), "rounding": "amortized by days of coverage, rounded to the cent per month",
             "near_text": "total"},
            {"type": "xlsx_value_present", "name": "balance at 31 December", "path": "prepaids.xlsx", "expected": float(d["closing"]),
             "rel_tol": round(0.05 / float(d["closing"]), 9), "rounding": "amortized by days of coverage, rounded to the cent per month",
             "near_text": "balance"},
            pin("Keystone auto 2026 expense", "midmonth", "keystone"),
            pin("Cascadia workers' comp 2026 expense", "late_bind", "cascadia"),
            pin("Summit floater 2026 expense", "cancel", "summit"),
        ],
    })
    print(f"seed={seed} total={d['total']} closing={d['closing']} opening={d['opening']} "
          + " ".join(f"{k}={by[k]['total']}" for k in ("midmonth", "late_bind", "cancel", "carry_gl", "carry_sw")))


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
