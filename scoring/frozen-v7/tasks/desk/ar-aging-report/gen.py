#!/usr/bin/env python3
"""ar-aging-report: a seafood distributor's invoice, payment and credit memo exports to an aging as of month end.

    python gen.py [--seed N]

Business: Yellowtail Seafood supplies restaurants and cafes on Net 15/30/45 terms. The lender wants an accounts
receivable aging as of 31 August for the borrowing-base certificate; the bookkeeper pulled the exports on
8 September, so they already carry a week of September.

Traps (each caught by a check, see task.yaml):
  * the invoice export is as of 8 September: its Balance column already reflects September payments and it
    lists September invoices                                   (checks: total receivables; Harbor-side customer balance)
  * partially paid invoices age on their remaining balance from the original due date (check: 31-60 bucket total)
  * buckets run on days past the due date (terms differ by customer), not days since the invoice date
                                                               (check: 31-60 bucket total)
  * credit memos come off the invoice they name; one names no invoice and comes off that customer's oldest open
    invoice; one is dated in September and does not count yet (check: credit customer over-90 balance)
  * the memo must name the three customers with the most past due as of 31 August; the biggest balance overall
    is mostly current, and one top-three customer paid a big old invoice on 3 September
                                                               (checks: memo top three; memo total past due)
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

AS_OF = date(2026, 8, 31)
EXPORT = date(2026, 9, 8)
BUCKETS = ["Current", "1-30 days", "31-60 days", "61-90 days", "Over 90 days"]   # no label a criteria parser reads as a date
CUSTOMERS = [  # name, terms, monthly volume, payment habit (mean days late, spread)
    ("Juniper Street Cafe", 15, 3, (4, 6)), ("Harborview Oyster Bar", 30, 7, (24, 20)), ("Tamarack Brewing", 30, 3, (8, 8)),
    ("Ellington Bakeries", 15, 2, (2, 4)), ("The Saltwater Grill", 45, 9, (-5, 6)), ("Pier 9 Fish House", 30, 6, (38, 25)),
    ("Blue Heron Catering", 30, 4, (16, 14)), ("Nightjar Supper Club", 15, 1, (1, 3)), ("Riverbend Bistro", 30, 5, (52, 30)),
    ("Copper Kettle Diner", 15, 4, (10, 10)), ("Larkspur Hotel Kitchen", 45, 6, (12, 12)), ("Driftwood Taqueria", 30, 3, (30, 25)),
    ("Mossbank Country Club", 30, 4, (20, 15)), ("Kingfisher Charters Galley", 15, 2, (5, 5)),
]
BIG_CURRENT = "The Saltwater Grill"      # largest balance overall, nearly all current
SEPT_PAYER = "Pier 9 Fish House"         # clears a large old invoice on 3 September
CREDIT_CUST = "Riverbend Bistro"         # carries the unapplied credit memo


def bucket(days_past: int) -> str:
    if days_past <= 0: return "Current"
    if days_past <= 30: return "1-30 days"
    if days_past <= 60: return "31-60 days"
    if days_past <= 90: return "61-90 days"
    return "Over 90 days"


def build(seed: int) -> dict:
    r = rng(seed)
    invoices, payments, credits = [], [], []
    num = 31200
    for name, terms, vol, (late, spread) in CUSTOMERS:
        d = date(2026, 3, 1) + timedelta(days=r.randint(0, 6))
        while d <= EXPORT:
            num += 1
            amt = round(r.uniform(900, 7800) * (1.6 if name == BIG_CURRENT else 1.0), 2)
            invoices.append({"no": f"YS-{num}", "cust": name, "date": d, "terms": terms, "due": d + timedelta(days=terms), "amount": amt})
            d += timedelta(days=max(2, int(r.gauss(30 / vol, 30 / vol / 3))))
    invoices.sort(key=lambda i: (i["date"], i["cust"]))
    for i, inv in enumerate(invoices):
        inv["no"] = f"YS-{31201 + i}"
    habit = {c[0]: c[3] for c in CUSTOMERS}
    pnum = 5100
    for inv in invoices:
        late, spread = habit[inv["cust"]]
        pay = inv["due"] + timedelta(days=int(r.gauss(late, spread)))
        pay = max(pay, inv["date"] + timedelta(days=3))
        k = r.random()
        if pay > EXPORT or k < 0.05:
            continue                                   # not paid yet
        if k < 0.13:                                   # partial payment, rest still open
            part = round(inv["amount"] * r.choice([0.25, 0.4, 0.5, 0.6]), 2)
            payments.append({"date": pay, "cust": inv["cust"], "inv": inv["no"], "amount": part})
        else:
            payments.append({"date": pay, "cust": inv["cust"], "inv": inv["no"], "amount": inv["amount"]})

    # trap scaffolding: the September payer clears its two oldest open invoices on 3 September
    def open_at(cust, when):
        out = []
        for inv in invoices:
            if inv["cust"] != cust or inv["date"] > when:
                continue
            paid = sum(p["amount"] for p in payments if p["inv"] == inv["no"] and p["date"] <= when)
            if inv["amount"] - paid > 0.005:
                out.append((inv, round(inv["amount"] - paid, 2)))
        return out
    old = sorted([x for x in open_at(SEPT_PAYER, AS_OF) if (AS_OF - x[0]["due"]).days > 30], key=lambda x: x[0]["date"])[:2]
    for inv, bal in old:
        payments[:] = [p for p in payments if p["inv"] != inv["no"]]
        payments.append({"date": date(2026, 9, 3), "cust": SEPT_PAYER, "inv": inv["no"], "amount": inv["amount"]})
    # a partial payment on an invoice that lands in 31-60 as of 31 August
    cands = [inv for inv in invoices if 31 <= (AS_OF - inv["due"]).days <= 60 and inv["cust"] not in (SEPT_PAYER, BIG_CURRENT)]
    part_inv = r.choice(cands)
    payments[:] = [p for p in payments if p["inv"] != part_inv["no"]]
    payments.append({"date": part_inv["due"] + timedelta(days=5), "cust": part_inv["cust"], "inv": part_inv["no"],
                     "amount": round(part_inv["amount"] * 0.45, 2)})

    # credit memos
    cnum = 880
    applied = r.sample([inv for inv in invoices if inv["date"] <= date(2026, 8, 20) and inv["cust"] != CREDIT_CUST], 5)
    for inv in applied:
        cnum += 1
        cm = {"no": f"CM-{cnum}", "cust": inv["cust"], "date": inv["date"] + timedelta(days=r.randint(1, 4)),
              "inv": inv["no"], "amount": round(inv["amount"] * r.choice([0.1, 0.15, 0.2]), 2),
              "reason": r.choice(["Short shipped", "Temperature complaint", "Pricing error", "Returned product"])}
        credits.append(cm)
        for p in payments:          # the customer short-pays by the credit, never overpays
            if p["inv"] == inv["no"]:
                p["date"] = max(p["date"], cm["date"] + timedelta(days=1))
                p["amount"] = round(min(p["amount"], inv["amount"] - cm["amount"]), 2)
    cnum += 1
    credits.append({"no": f"CM-{cnum}", "cust": CREDIT_CUST, "date": date(2026, 8, 18), "inv": "", "amount": 0.0,
                    "reason": "Spoiled delivery - goodwill credit"})
    unapplied = credits[-1]
    sept_credit_inv = r.choice([inv for inv in invoices if inv["date"] <= AS_OF and inv["cust"] not in (CREDIT_CUST,)
                                and not any(p["inv"] == inv["no"] and p["date"] <= EXPORT for p in payments)])
    cnum += 1
    credits.append({"no": f"CM-{cnum}", "cust": sept_credit_inv["cust"], "date": date(2026, 9, 4), "inv": sept_credit_inv["no"],
                    "amount": round(sept_credit_inv["amount"] * 0.3, 2), "reason": "Pricing error"})

    # ---- balances as of a date ----
    def balances(when: date) -> dict:
        bal = {}
        for inv in invoices:
            if inv["date"] > when:
                continue
            paid = sum(p["amount"] for p in payments if p["inv"] == inv["no"] and p["date"] <= when)
            cred = sum(c["amount"] for c in credits if c["inv"] == inv["no"] and c["date"] <= when)
            bal[inv["no"]] = round(inv["amount"] - paid - cred, 2)
        # unapplied credits come off the customer's oldest open invoice
        for c in credits:
            if c["inv"] or c["date"] > when:
                continue
            opens = sorted([inv for inv in invoices if inv["cust"] == c["cust"] and bal.get(inv["no"], 0) > 0.005],
                           key=lambda i: (i["date"], i["no"]))
            left = c["amount"]
            for inv in opens:
                take = min(left, bal[inv["no"]])
                bal[inv["no"]] = round(bal[inv["no"]] - take, 2)
                left = round(left - take, 2)
                if left <= 0:
                    break
        return bal

    # size the unapplied credit below the oldest open balance of that customer
    b0 = balances(AS_OF)
    opens = sorted([inv for inv in invoices if inv["cust"] == CREDIT_CUST and b0.get(inv["no"], 0) > 0.005], key=lambda i: (i["date"], i["no"]))
    if not opens:
        return {"ok": False}
    unapplied["amount"] = round(b0[opens[0]["no"]] * r.uniform(0.35, 0.6), 2)
    unapplied["target"] = opens[0]["no"]

    bal = balances(AS_OF)
    by_no = {inv["no"]: inv for inv in invoices}
    open_items = []
    for no, b in bal.items():
        if b > 0.005:
            inv = by_no[no]
            dpd = (AS_OF - inv["due"]).days
            open_items.append({**inv, "balance": b, "dpd": dpd, "bucket": bucket(dpd)})
    open_items.sort(key=lambda x: (x["cust"], x["date"]))
    names = [c[0] for c in CUSTOMERS]
    grid = {(n, bk): 0.0 for n in names for bk in BUCKETS}
    for it in open_items:
        grid[(it["cust"], it["bucket"])] += it["balance"]
    grid = {k: round(v, 2) for k, v in grid.items()}
    cust_tot = {n: round(sum(grid[(n, bk)] for bk in BUCKETS), 2) for n in names}
    past_due = {n: round(cust_tot[n] - grid[(n, "Current")], 2) for n in names}
    bucket_tot = {bk: round(sum(grid[(n, bk)] for n in names), 2) for bk in BUCKETS}
    total = round(sum(cust_tot.values()), 2)
    total_past_due = round(total - bucket_tot["Current"], 2)
    top3 = sorted(names, key=lambda n: -past_due[n])[:4]

    # naive readings
    exp_bal = balances(EXPORT)
    naive_total_export = round(sum(b for b in exp_bal.values() if b > 0.005), 2)
    naive_pd_export = {n: 0.0 for n in names}
    for no, b in exp_bal.items():
        if b > 0.005 and (EXPORT - by_no[no]["due"]).days > 0:
            naive_pd_export[by_no[no]["cust"]] += b
    naive_grid_invdate = {bk: 0.0 for bk in BUCKETS}
    for it in open_items:
        naive_grid_invdate[bucket((AS_OF - it["date"]).days)] += it["balance"]
    return {"ok": True, "invoices": invoices, "payments": sorted(payments, key=lambda p: (p["date"], p["inv"])),
            "credits": renumber(sorted(credits, key=lambda c: (c["date"], c["cust"]))), "exp_bal": exp_bal, "open_items": open_items,
            "grid": grid, "cust_tot": cust_tot, "past_due": past_due, "bucket_tot": bucket_tot, "total": total,
            "total_past_due": total_past_due, "rank": top3, "names": names, "unapplied": unapplied,
            "naive_total_export": naive_total_export, "naive_pd_export": naive_pd_export,
            "naive_invdate": {k: round(v, 2) for k, v in naive_grid_invdate.items()}, "part_inv": part_inv["no"]}


def renumber(credits: list[dict]) -> list[dict]:
    for i, c in enumerate(credits):
        c["no"] = f"CM-{881 + i}"
    return credits


def acceptable(d: dict) -> bool:
    if not d.get("ok"):
        return False
    pd_, ct, rank = d["past_due"], d["cust_tot"], d["rank"]
    top3 = rank[:3]
    if SEPT_PAYER not in top3 or BIG_CURRENT in top3:
        return False
    if max(ct, key=ct.get) != BIG_CURRENT or pd_[BIG_CURRENT] > 0.25 * ct[BIG_CURRENT]:
        return False
    if pd_[rank[2]] < 1.08 * pd_[rank[3]] or pd_[rank[1]] < 1.04 * pd_[rank[2]] or pd_[rank[0]] < 1.04 * pd_[rank[1]]:
        return False
    naive_top = sorted(d["names"], key=lambda n: -d["naive_pd_export"][n])[:3]
    if SEPT_PAYER in naive_top:
        return False
    bt = d["bucket_tot"]
    row = [bt[b] for b in BUCKETS] + [d["total"]]
    for v in row:
        if sum(1 for w in row if abs(v - w) <= 0.01 * abs(v)) > 1:
            return False
    if abs(bt["31-60 days"] - d["naive_invdate"]["31-60 days"]) < 0.05 * bt["31-60 days"] or abs(d["total"] - d["naive_total_export"]) < 0.03 * d["total"]:
        return False
    g = d["grid"]
    cc = [g[(CREDIT_CUST, b)] for b in BUCKETS] + [ct[CREDIT_CUST]]
    if g[(CREDIT_CUST, "Over 90 days")] < 500 or sum(1 for w in cc if abs(g[(CREDIT_CUST, "Over 90 days")] - w) <= 0.01 * g[(CREDIT_CUST, "Over 90 days")]) > 1:
        return False
    target = next(it for it in d["open_items"] if it["no"] == d["unapplied"]["target"])
    if target["bucket"] != "Over 90 days":
        return False
    sp = [g[(SEPT_PAYER, b)] for b in BUCKETS]
    if sum(1 for w in sp if abs(ct[SEPT_PAYER] - w) <= 0.01 * ct[SEPT_PAYER]) > 0:
        return False
    return all(ct[n] > 0 for n in d["names"] if n != "Nightjar Supper Club")


# --------------------------------------------------------------------------- deliverables

def aging_sheets(d: dict) -> dict:
    items = [[it["cust"], it["no"], it["date"].isoformat(), it["due"].isoformat(), it["dpd"], it["bucket"], it["balance"]]
             for it in d["open_items"]]
    n = len(items) + 1
    rows = []
    names = [nm for nm in d["names"] if d["cust_tot"][nm] > 0.005]
    for i, nm in enumerate(names, start=4):
        rows.append([nm] + [f'=ROUND(SUMIFS(Items!$G$2:$G${n},Items!$A$2:$A${n},$A{i},Items!$F$2:$F${n},{c}$3),2)'
                            for c in "BCDEF"] + [f"=SUM(B{i}:F{i})", f"=G{i}-B{i}"])
    last = len(names) + 3
    rows.append(["Total"] + [f"=SUM({c}4:{c}{last})" for c in "BCDEFGH"])
    return {"Aging": {"merged_title": "Yellowtail Seafood - receivables aging as of 31 Aug 2026",
                      "preamble": [["Days past due date; balances as they stood on 31 Aug 2026"]],
                      "header": ["Customer", *BUCKETS, "Total", "Past due"], "rows": rows,
                      "widths": {"A": 28, "G": 14, "H": 14}},
            "Items": {"header": ["customer", "invoice", "invoice date", "due date", "days past due", "bucket", "balance"],
                           "rows": items, "widths": {"A": 28}}}


def memo_text(d: dict) -> str:
    pd_, top = d["past_due"], d["rank"][:3]
    return f"""# Receivables aging as of 31 August 2026

Total receivables were ${d['total']:,.2f}, of which ${d['total_past_due']:,.2f} was past due.

The three customers with the most past due:

1. {top[0]}: ${pd_[top[0]]:,.2f} past due.
2. {top[1]}: ${pd_[top[1]]:,.2f} past due.
3. {top[2]}: ${pd_[top[2]]:,.2f} past due.

{SEPT_PAYER} paid its two oldest invoices on 3 September, so it looks clean in the September export, but on 31 August
it was still in the top three. {BIG_CURRENT} carries the largest balance but almost all of it is current.
"""



def cent_tolerant(spec: dict) -> dict:
    """Figures computed from exact source data tie to the cent: every workbook pin gets a tolerance under 1.00."""
    for c in spec["checks"]:
        if c["type"] == "xlsx_value_present" and not c.get("rounding"):
            exp = abs(float(c["expected"]))
            c["rel_tol"] = min(float(c.get("rel_tol", 0.005)), float(f"{0.9 / max(exp, 1.0):.2g}"))
    return spec


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    by_no = {inv["no"]: inv for inv in d["invoices"]}

    # ---- workspace ----
    exp_rows = []
    for inv in d["invoices"]:
        bal = d["exp_bal"][inv["no"]]
        paid = round(inv["amount"] - bal, 2)
        status = "Paid" if bal <= 0.005 else ("Partially Paid" if paid > 0.005 else "Open")
        exp_rows.append([inv["no"], inv["cust"], inv["date"].strftime("%m/%d/%Y"), f"Net {inv['terms']}", inv["due"].strftime("%m/%d/%Y"),
                         money_str(inv["amount"], 0), money_str(paid, 0), money_str(max(bal, 0), 0), status])
    write_csv(os.path.join(ws, "invoice_register_export_2026-09-08.csv"),
              ["Invoice No", "Customer", "Invoice Date", "Terms", "Due Date", "Amount", "Paid/Credited", "Balance", "Status"], exp_rows,
              preamble=["Yellowtail Seafood - Invoice Register", "Run 09/08/2026 07:12 - all invoices since 03/01/2026"], crlf=True)
    write_csv(os.path.join(ws, "customer_payments.csv"), ["Deposit Date", "Customer", "Applied To", "Amount", "Method"],
              [[p["date"].isoformat(), p["cust"], p["inv"], f"{p['amount']:.2f}", "ACH" if int(p["inv"][-1]) % 3 else "Check"]
               for p in d["payments"]])
    write_csv(os.path.join(ws, "credit_memos.csv"), ["Credit Memo", "Date", "Customer", "Against Invoice", "Amount", "Reason"],
              [[c["no"], c["date"].strftime("%m/%d/%Y"), c["cust"], c["inv"], money_str(c["amount"], 1), c["reason"]] for c in d["credits"]])
    write_text(os.path.join(ws, "note_from_ingrid.txt"),
               "The bank wants our receivables aging as of 31 August for the borrowing base certificate. Tomas pulled\n"
               "the exports this morning, so they run a week past month end.\n\n"
               "What I need:\n"
               "- every customer's balance as it stood on 31 August, split Current / 1-30 / 31-60 / 61-90 / Over 90 days\n"
               "  past the due date, with totals\n"
               "- a credit memo comes off the invoice it was written against. If it isn't against an invoice, take it off\n"
               "  that customer's oldest open invoice.\n\n"
               "And a short memo I can forward: total receivables, how much is past due, and the three customers with the\n"
               "most money past due and how much each owes past due.\n\n"
               "Ingrid\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "aging_by_customer.csv"), ["customer", *["current", "days_1_30", "days_31_60", "days_61_90", "over_90"], "total", "past_due"],
              [[n, *[f"{d['grid'][(n, b)]:.2f}" for b in BUCKETS], f"{d['cust_tot'][n]:.2f}", f"{d['past_due'][n]:.2f}"] for n in d["names"]])
    write_json(os.path.join(ref, "notes.json"), {
        "as_of": AS_OF.isoformat(), "top3": [{"customer": n, "past_due": d["past_due"][n]} for n in d["rank"][:3]],
        "fourth": {"customer": d["rank"][3], "past_due": d["past_due"][d["rank"][3]]},
        "bucket_totals": d["bucket_tot"], "total": d["total"], "total_past_due": d["total_past_due"],
        "unapplied_credit": {k: v for k, v in d["unapplied"].items()}, "partial_payment_invoice": d["part_inv"],
        "naive": {"total_from_export_balance": d["naive_total_export"], "invoice_date_buckets": d["naive_invdate"]}})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "aging.xlsx"), aging_sheets(d), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    g, bt = d["grid"], d["bucket_tot"]
    write_task_yaml(HERE, cent_tolerant({
        "id": "ar-aging-report", "track": "desk", "category": "reports",
        "title": "Receivables aging at month end for the bank",
        "ask": ("Ingrid needs the receivables aging as of 31 August for the bank. Build aging.xlsx with live formulas from the exports "
                "and write memo.md she can forward - her note says what goes in both.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the invoice register was run on 8 September: its Balance and Status columns already reflect September payments and "
            "credits, and it lists invoices dated in September; balances must be rebuilt as of 31 August from the payment and "
            "credit memo dates (checks: total receivables; Pier 9 Fish House balance)",
            f"{SEPT_PAYER} cleared its two oldest invoices on 3 September, so it looks current in the register but was one of "
            "the three largest past-due accounts on 31 August (checks: memo names the top three past-due customers; Pier 9 Fish "
            "House balance)",
            "partially paid invoices stay open for the unpaid part and age from their original due date (check: 31-60 bucket total)",
            "buckets count days past the due date and terms run Net 15, 30 or 45 by customer; aging from the invoice date "
            "shifts invoices a bucket older (check: 31-60 bucket total)",
            f"credit memos come off the invoice they name; the goodwill credit to {CREDIT_CUST} names no invoice and comes off its "
            "oldest open invoice, which is over 90 days; a 4 September credit does not count yet (check: Riverbend Bistro over 90)",
            f"{BIG_CURRENT} has the largest balance but nearly all of it is current, so ranking by total balance picks the wrong "
            "top three (check: memo names the top three past-due customers)",
            "amounts in the register are '1,234.00' text, the register has a two-line preamble and CRLF endings, and credit memo "
            "dates are US-style (check: total receivables)",
        ],
        "checks": [
            {"type": "file_exists", "name": "aging.xlsx exists", "path": "aging.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "aging.xlsx", "min_count": 20},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "aging.xlsx"},
            {"type": "xlsx_value_present", "name": "total receivables as of 31 August", "path": "aging.xlsx",
             "expected": d["total"], "rel_tol": 0.003, "near_text": "total"},
            {"type": "xlsx_value_present", "name": "31-60 bucket total", "path": "aging.xlsx",
             "expected": bt["31-60 days"], "rel_tol": 0.005, "near_text": "total"},
            {"type": "xlsx_value_present", "name": "Pier 9 Fish House balance (September payment not yet received)", "path": "aging.xlsx",
             "expected": d["cust_tot"][SEPT_PAYER], "rel_tol": 0.005, "near_text": "pier 9"},
            {"type": "xlsx_value_present", "name": "Riverbend Bistro over 90 (unapplied credit on the oldest invoice)", "path": "aging.xlsx",
             "expected": g[(CREDIT_CUST, "Over 90 days")], "rel_tol": 0.005, "near_text": "riverbend"},
            {"type": "text_numbers_present", "name": "memo carries total receivables and total past due", "path": "memo.md",
             "numbers": [d["total"], d["total_past_due"]], "rel_tol": 0.005},
            {"type": "custom", "name": "memo names the top three past-due customers", "module": "check.py"},
        ],
    }))
    print(f"seed={seed} invoices={len(d['invoices'])} open={len(d['open_items'])} payments={len(d['payments'])} credits={len(d['credits'])}")
    print("  bucket totals", bt, "total", d["total"], "past due", d["total_past_due"])
    print("  rank", [(n, d["past_due"][n]) for n in d["rank"]])
    print("  naive total", d["naive_total_export"], "naive 31-60 by inv date", d["naive_invdate"]["31-60 days"])
    print("  pier 9", d["cust_tot"][SEPT_PAYER], "riverbend over 90", g[(CREDIT_CUST, "Over 90 days")], "unapplied", d["unapplied"])


if __name__ == "__main__":
    s = argparse_seed()
    for attempt in range(1500):
        if acceptable(build(s * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 1500 attempts")
    emit(s * 1000 + attempt)
