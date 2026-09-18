#!/usr/bin/env python3
"""commission-calculation: August commissions for a team-sales desk on a graduated plan, with refund recoveries.

    python gen.py [--seed N] [--naive DIR]

Business: an outdoor outfitter's team-sales desk (uniforms and gear for schools and clubs). Five reps, a written
commission plan, last month's statement, this month's CRM export and accounting's refund log.

Traps (each caught by a check, see task.yaml):
  * bands are graduated on the rep's cumulative month: each dollar earns its band's rate, so paying the whole
    month at the top band reached (or rating each deal by its own size) overpays       (check: Osei commission)
  * refunds are recovered at the rate the refunded deal was paid: July deals at the rate on July's statement,
    August deals at the band their dollars fell in by close date - not the rep's current top band
                                                                                         (checks: Brooks, Kim net payout)
  * one rep moved to a senior plan from August 1, named only in the director's email; her refunded July deal
    stays at the July standard rate                                                     (check: Haddad net payout)
  * split deals name two reps and credit half to each                                  (checks: Osei commission; total)
  * the CRM export carries open quotes and lost deals with amounts                     (check: total net payout)
  * the statement must be live formulas                                                 (check: live formulas)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))


STANDARD = [(20000.0, 0.03), (50000.0, 0.05), (float("inf"), 0.08)]
SENIOR = [(40000.0, 0.05), (float("inf"), 0.09)]
ACCOUNTS = ["Riverbend High School", "Northfield Youth Soccer", "Oakhurst Rowing Club", "Cedar Valley Middle School", "Lakeside Lacrosse",
            "Summit Nordic Ski Team", "Harbor City FC", "Pine Ridge Cross Country", "Fernbrook Montessori", "Westbrook Little League",
            "Granite State Climbing Gym", "Union Plains Rugby", "Magnolia Swim Club", "Tamarack Trail Runners", "Ironwood Hockey Assoc.",
            "Silverline Cycling Club", "Kingfisher Sailing School", "Larkspur Dance Academy", "Quarry Road Scouts", "Uptown Fitness"]


def band_rate(bands, lo: float, hi: float) -> float | None:
    """the single rate for dollars in (lo, hi], or None if the span crosses a threshold"""
    prev = 0.0
    for top, rate in bands:
        if lo >= prev - 1e-9 and hi <= top + 1e-9:
            return rate
        prev = top
    return None


def graduated(bands, amount: float) -> float:
    total, prev = 0.0, 0.0
    for top, rate in bands:
        if amount > prev:
            total += (min(amount, top) - prev) * rate
        prev = top
    return total


def sequence(deals: list[dict], bands) -> None:
    """deals already in close-date/order order for one rep: stamp cumulative position, commission and single rate"""
    cum = 0.0
    for dl in deals:
        lo, hi = cum, cum + dl["credit"]
        dl["lo"], dl["hi"] = lo, hi
        dl["commission"] = round(graduated(bands, hi) - graduated(bands, lo), 2)
        dl["rate"] = band_rate(bands, lo, hi)
        cum = hi


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = []
    while len(ppl) < 5:
        f, l = person(r)
        if l in {p[1] for p in ppl} or l in ("Osei", "Brooks", "Haddad", "Kim", "Ward") or "kim" in f.lower():
            continue
        ppl.append((f, l))
    reps = ["Kwame Osei", "Rebecca Brooks", "Laila Haddad", "Daniel Kim", f"{ppl[0][0]} Ward"]
    A, B, H, C, D = reps
    targets_aug = {A: (58000, 76000), B: (21000, 34000), H: (47000, 64000), C: (56000, 72000), D: (30000, 46000)}
    targets_jul = {A: (40000, 60000), B: (52000, 66000), H: (22000, 40000), C: (35000, 55000), D: (26000, 45000)}

    def month_deals(year, month, targets, days_in):
        out = []
        for rep in reps:
            goal = r.uniform(*targets[rep])
            tot = 0.0
            while tot < goal:
                amt = round(r.uniform(1400, 9800), 2)
                out.append({"rep": rep, "reps": [rep], "amount": amt, "date": date(year, month, r.randint(1, days_in)), "k": r.random()})
                tot += amt
        return out

    jul = month_deals(2026, 7, targets_jul, 31)
    aug = month_deals(2026, 8, targets_aug, 31)
    # two August split deals: Osei with Ward, Osei with Kim
    for partner in (D, C):
        amt = round(r.uniform(6000, 11000), 2)
        aug.append({"rep": A, "reps": [A, partner], "amount": amt, "date": date(2026, 8, r.randint(3, 27)), "k": r.random()})
    seq = 71800
    for month in (jul, aug):
        month.sort(key=lambda x: (x["date"], x["k"]))
        for dl in month:
            seq += r.randint(1, 4)
            dl["id"] = f"SO-{seq}"
    # credited lines per rep
    def credited(month, plan_for):
        lines = {rep: [] for rep in reps}
        for dl in month:
            share = 1.0 / len(dl["reps"])
            for rp in dl["reps"]:
                lines[rp].append({"id": dl["id"], "date": dl["date"], "rep": rp, "credit": round(dl["amount"] * share, 2), "deal": dl})
        for rp in reps:
            sequence(lines[rp], plan_for(rp))
        return lines

    jul_lines = credited(jul, lambda rp: STANDARD)
    aug_lines = credited(aug, lambda rp: SENIOR if rp == H else STANDARD)

    # noise rows in the August CRM export: open quotes and lost deals
    noise = []
    for _ in range(9):
        rp = r.choice(reps)
        noise.append({"rep": rp, "reps": [rp], "amount": round(r.uniform(1800, 12000), 2), "date": date(2026, 8, r.randint(1, 31)),
                      "stage": r.choice(["Quote Sent", "Quote Sent", "Closed Lost", "Negotiation"]), "k": r.random()})
    for n in noise:
        seq += r.randint(1, 4)
        n["id"] = f"SO-{seq}"

    # refunds processed in August
    def pick(lines, cond):
        cands = [ln for ln in lines if len(ln["deal"]["reps"]) == 1 and ln["rate"] is not None and cond(ln)]
        return r.choice(cands) if cands else None

    refunds = []
    rb = pick(jul_lines[B], lambda ln: ln["rate"] == 0.08)
    rh = pick(jul_lines[H], lambda ln: ln["rate"] == 0.03)
    rc = pick(aug_lines[C], lambda ln: ln["rate"] == 0.03)
    rd = pick(jul_lines[D], lambda ln: ln["rate"] == 0.05)
    if not all([rb, rh, rc, rd]):
        return {"bad": True}
    for ln, frac, origin in ((rb, 1.0, "jul"), (rh, 1.0, "jul"), (rc, round(r.uniform(0.3, 0.6), 2), "aug"), (rd, round(r.uniform(0.35, 0.8), 2), "jul")):
        amt = round(ln["credit"] * frac, 2)
        refunds.append({"line": ln, "amount": amt, "rate": ln["rate"], "recovery": round(amt * ln["rate"], 2), "origin": origin,
                        "date": date(2026, 8, r.randint(4, 28)) if origin == "jul" else ln["date"] + timedelta(days=r.randint(2, 6))})
    for rf in refunds:
        if rf["date"] > date(2026, 8, 31):
            rf["date"] = date(2026, 8, 31)
    refunds.sort(key=lambda x: x["date"])
    for i, rf in enumerate(refunds):
        rf["id"] = f"RF-{2208 + i * 3}"

    stmt = {}
    for rp in reps:
        bookings = round(sum(ln["credit"] for ln in aug_lines[rp]), 2)
        plan = SENIOR if rp == H else STANDARD
        comm = round(graduated(plan, bookings), 2)
        rec = round(sum(rf["recovery"] for rf in refunds if rf["line"]["rep"] == rp), 2)
        stmt[rp] = {"plan": "Senior" if rp == H else "Standard", "bookings": bookings, "commission": comm, "recoveries": rec,
                    "net": round(comm - rec, 2)}
    total_net = round(sum(s["net"] for s in stmt.values()), 2)
    return {"reps": reps, "jul": jul, "aug": aug, "jul_lines": jul_lines, "aug_lines": aug_lines, "noise": noise, "refunds": refunds,
            "stmt": stmt, "total_net": total_net}


def naive_stmt(d: dict) -> dict:
    """whole month at the top band reached, standard plan for everyone, split deals credited to the first rep,
    quotes and lost deals included, recoveries at the rep's current top band."""
    reps = d["reps"]
    book = {rp: 0.0 for rp in reps}
    for dl in d["aug"]:
        book[dl["reps"][0]] += dl["amount"]
    for n in d["noise"]:
        book[n["rep"]] += n["amount"]
    out = {}
    for rp in reps:
        top = next(rate for top_, rate in STANDARD if book[rp] <= top_)
        comm = round(book[rp] * top, 2)
        rec = round(sum(rf["amount"] * top for rf in d["refunds"] if rf["line"]["rep"] == rp), 2)
        out[rp] = {"bookings": round(book[rp], 2), "commission": comm, "recoveries": rec, "net": round(comm - rec, 2)}
    return out


def acceptable(d: dict) -> bool:
    if d.get("bad"):
        return False
    reps, st, refunds = d["reps"], d["stmt"], d["refunds"]
    A, B, H, C, D = reps
    # every pinned figure moves by more than 2% under each shortcut on its own
    a = st[A]
    whole_rate = a["bookings"] * next(rate for top, rate in STANDARD if a["bookings"] <= top)
    if abs(whole_rate - a["commission"]) < 0.05 * a["commission"]:
        return False
    full_split = sum(dl["amount"] for dl in d["aug"] if A in dl["reps"])
    if abs(graduated(STANDARD, full_split) - a["commission"]) < 0.03 * a["commission"]:
        return False
    for rp in (B, H, C):
        s = st[rp]
        plan = SENIOR if rp == H else STANDARD
        top_rate = next(rate for top, rate in plan if s["bookings"] <= top)
        rec_top = sum(rf["amount"] * top_rate for rf in refunds if rf["line"]["rep"] == rp)
        if abs((s["commission"] - rec_top) - s["net"]) < 0.02 * s["net"]:
            return False
        if s["recoveries"] < 0.02 * s["commission"]:
            return False
    h = st[H]
    if abs(graduated(STANDARD, h["bookings"]) - h["commission"]) < 0.03 * h["commission"]:
        return False
    # Brooks's current band must differ from the 8% her refunded July deal was paid at
    if st[B]["bookings"] > 50000:
        return False
    # no single deal, credited half, July commission line or refund sits within 1% of a pinned figure, so a
    # detail sheet listing a rep's deals cannot pass for the statement line
    pinned = [a["commission"], st[B]["net"], st[C]["net"], st[H]["net"], d["total_net"]]
    small = [dl["amount"] for dl in d["aug"] + d["jul"] + d["noise"]] + [rf["amount"] for rf in refunds]
    small += [ln["credit"] for m in (d["aug_lines"], d["jul_lines"]) for lines in m.values() for ln in lines]
    small += [ln["commission"] for lines in d["jul_lines"].values() for ln in lines]
    if any(abs(v - p) <= 0.01 * p for v in small for p in pinned):
        return False
    noise_amt = sum(n["amount"] for n in d["noise"])
    if noise_amt < 0.05 * sum(s["bookings"] for s in st.values()):
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def statement_sheets(d: dict, aug_rows: list[list], ref_rows: list[list]) -> dict:
    n_o = len(aug_rows) + 1
    n_r = len(ref_rows) + 1
    rows = []
    for i, rp in enumerate(d["reps"], start=2):
        plan = d["stmt"][rp]["plan"]
        if plan == "Senior":
            comm = f"=ROUND(MIN(C{i},40000)*0.05+MAX(C{i}-40000,0)*0.09,2)"
        else:
            comm = f"=ROUND(MIN(C{i},20000)*0.03+MAX(MIN(C{i},50000)-20000,0)*0.05+MAX(C{i}-50000,0)*0.08,2)"
        rows.append([rp, plan, f"=ROUND(SUMIFS(Deals!$D$2:$D${n_o},Deals!$C$2:$C${n_o},A{i}),2)", comm,
                     f"=ROUND(SUMIFS(Refunds!$G$2:$G${n_r},Refunds!$D$2:$D${n_r},A{i}),2)", f"=D{i}-E{i}"])
    last = 1 + len(d["reps"])
    rows.append(["Total", ""] + [f"=SUM({c}2:{c}{last})" for c in "CDEF"])
    return {
        "August 2026": {"header": ["Rep", "Plan", "Closed won (credited)", "Commission", "Refund recoveries", "Net payout"], "rows": rows,
                        "widths": {"A": 18, "C": 20, "D": 14, "E": 18, "F": 14}},
        "Deals": {"header": ["order", "close_date", "rep", "credited_amount"], "rows": aug_rows, "widths": {"C": 18}},
        "Refunds": {"header": ["refund", "processed", "order", "rep", "refund_amount", "rate_paid", "recovery"], "rows": ref_rows,
                    "widths": {"D": 18}},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    reps, st = d["reps"], d["stmt"]
    A, B, H, C, D = reps
    r = rng(seed + 12)

    # ---- August CRM export ----
    crm = []
    for dl in d["aug"]:
        crm.append({"id": dl["id"], "date": dl["date"], "owner": " / ".join(dl["reps"]), "stage": "Closed Won", "amount": dl["amount"],
                    "acct": r.choice(ACCOUNTS), "k": dl["k"]})
    for n in d["noise"]:
        crm.append({"id": n["id"], "date": n["date"], "owner": n["rep"], "stage": n["stage"], "amount": n["amount"], "acct": r.choice(ACCOUNTS),
                    "k": n["k"]})
    crm.sort(key=lambda x: x["id"])
    write_csv(os.path.join(ws, "crm_opportunities_2026-08.csv"), ["Order #", "Close Date", "Account", "Owner", "Stage", "Amount"],
              [[x["id"], x["date"].strftime("%m/%d/%Y"), x["acct"], x["owner"], x["stage"], f"${x['amount']:,.2f}"] for x in crm],
              preamble=["Team Sales - Opportunities by close date", "Close date 08/01/2026 - 08/31/2026"], crlf=True)

    # ---- July statement (static, as issued) ----
    jl = [ln for rp in reps for ln in d["jul_lines"][rp]]
    jl.sort(key=lambda ln: (ln["date"], ln["id"], ln["rep"]))
    deal_rows = [[ln["id"], ln["date"], ln["rep"], ln["credit"], f"{ln['rate'] * 100:.0f}%" if ln["rate"] is not None else "split band",
                  ln["commission"]] for ln in jl]
    summ = []
    for rp in reps:
        bk = round(sum(ln["credit"] for ln in d["jul_lines"][rp]), 2)
        cm = round(graduated(STANDARD, bk), 2)
        summ.append([rp, "Standard", bk, cm, 0.0, cm])
    write_xlsx(os.path.join(ws, "commission_statement_2026-07.xlsx"), {
        "Summary": {"merged_title": "Commission statement - July 2026 (paid 08/15/2026)",
                    "header": ["Rep", "Plan", "Closed won", "Commission", "Recoveries", "Net paid"], "rows": summ,
                    "number_formats": {c: "#,##0.00" for c in "CDEF"}, "widths": {"A": 18, "C": 14}},
        "Deal detail": {"header": ["Order #", "Close date", "Rep", "Credited amount", "Band rate", "Commission paid"], "rows": deal_rows,
                        "number_formats": {"D": "#,##0.00", "F": "#,##0.00"}, "widths": {"A": 11, "B": 12, "C": 18, "D": 16}},
    }, creator="Payroll")

    # ---- refunds log ----
    write_csv(os.path.join(ws, "refunds_processed_august.csv"), ["Refund #", "Processed", "Order #", "Account", "Refund amount"],
              [[rf["id"], rf["date"].strftime("%Y-%m-%d"), rf["line"]["id"], r.choice(ACCOUNTS), f"{rf['amount']:.2f}"] for rf in d["refunds"]])

    # ---- plan PDF ----
    write_pdf_document(os.path.join(ws, "team_sales_commission_plan_2026.pdf"), [
        ("title", "Granite Peak Outfitters"), ("h", "Team Sales Commission Plan - effective January 1, 2026"), ("hr", None),
        ("h", "1. What is commissionable"),
        ("p", "Opportunities marked Closed Won in the CRM, credited to the calendar month of their close date. Quotes, open "
              "negotiations and lost opportunities are not commissionable. The CRM amount already excludes tax and freight."),
        ("h", "2. Standard plan"),
        ("p", "Commission is graduated on the rep's cumulative closed-won amount for the calendar month."),
        ("table", [["Band", "Cumulative monthly amount", "Rate"], ["1", "first $20,000", "3%"], ["2", "$20,000 to $50,000", "5%"],
                   ["3", "above $50,000", "8%"]], {"col_widths": [40, 200, 60], "shade_header": True}),
        ("p", "Each dollar is paid at the rate of the band it falls in. Deals are taken in close-date order, with the order number "
              "breaking a tie, so a deal that crosses a threshold is split across the two bands. Reaching a higher band never "
              "re-rates dollars already earned in a lower one."),
        ("h", "3. Split deals"),
        ("p", "When the CRM names two reps as owners of one opportunity, each rep is credited with half of the amount."),
        ("h", "4. Refunds"),
        ("p", "When an order is refunded in whole or in part, the commission paid on the refunded amount is recovered at the rate "
              "at which it was paid. Recoveries are deducted from the payout for the month in which the refund is processed. They "
              "do not reduce that month's cumulative amount and do not change its bands."),
        ("h", "5. Plan changes"),
        ("p", "Individual plan changes are confirmed in writing by the Director of Sales and apply from the date stated."),
    ], font="Helvetica", base_size=10.5)

    write_email_thread(os.path.join(ws, "email_from_marcus.txt"), [
        {"from": "Marcus Bennett <marcus@granitepeak.com>", "to": "Team Sales", "date": "Fri, 31 Jul 2026 16:22",
         "subject": "Laila - senior plan",
         "body": ("Confirming what we discussed at the review: Laila Haddad moves to the Senior plan for deals closing from "
                  "August 1. Senior plan is 5% on her first $40,000 of closed-won in a month and 9% on everything above that, "
                  "same graduated rules as the standard plan. Everything she closed in July was paid under the standard plan and "
                  "stays that way.\n\nCongratulations Laila.\n\nMarcus")},
        {"from": "Marcus Bennett <marcus@granitepeak.com>", "to": "ops@granitepeak.com", "date": "Wed, 2 Sep 2026 08:47",
         "subject": "August commissions",
         "body": ("August commissions are due to payroll on the 15th. One line per rep: what they closed, the commission, any refund "
                  "recoveries and the net we pay. Build it so the numbers work from the formulas - payroll re-checks it.\n\nMarcus")},
    ])

    # ---- reference ----
    aug_rows = []
    for rp in reps:
        for ln in d["aug_lines"][rp]:
            aug_rows.append([ln["id"], ln["date"].isoformat(), rp, ln["credit"]])
    aug_rows.sort(key=lambda x: (x[1], x[0], x[2]))
    ref_rows = [[rf["id"], rf["date"].isoformat(), rf["line"]["id"], rf["line"]["rep"], rf["amount"], rf["rate"], f"=ROUND(E{i}*F{i},2)"]
                for i, rf in enumerate(d["refunds"], start=2)]
    write_xlsx(os.path.join(sol, "commissions.xlsx"), statement_sheets(d, aug_rows, ref_rows), creator="reference")
    write_csv(os.path.join(ref, "statement_2026-08.csv"), ["rep", "plan", "closed_won", "commission", "recoveries", "net_payout"],
              [[rp, st[rp]["plan"], f"{st[rp]['bookings']:.2f}", f"{st[rp]['commission']:.2f}", f"{st[rp]['recoveries']:.2f}",
                f"{st[rp]['net']:.2f}"] for rp in reps] + [["Total", "", "", "", "", f"{d['total_net']:.2f}"]])
    write_json(os.path.join(ref, "notes.json"), {
        "refunds": [{"id": rf["id"], "order": rf["line"]["id"], "rep": rf["line"]["rep"], "origin": rf["origin"], "amount": rf["amount"],
                     "rate_paid": rf["rate"], "recovery": rf["recovery"]} for rf in d["refunds"]],
        "split_deals": [dl["id"] for dl in d["aug"] if len(dl["reps"]) == 2], "noise_rows": [n["id"] for n in d["noise"]],
        "naive_statement": naive_stmt(d)})

    rb = next(rf for rf in d["refunds"] if rf["line"]["rep"] == B)
    rc = next(rf for rf in d["refunds"] if rf["line"]["rep"] == C)
    write_task_yaml(HERE, {
        "id": "commission-calculation", "track": "desk", "category": "spreadsheet",
        "title": "August sales commissions with refund recoveries",
        "ask": ("Work out August commissions for the team sales reps and save them as commissions.xlsx. Everything you need is in "
                "the folder - the plan, July's statement, the CRM export, the refunds and Marcus's emails.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the bands are graduated on each rep's cumulative month: every dollar earns its own band's rate, so paying the whole month "
            f"at the top band reached overpays {A} by hundreds and rating each deal by its own size is also wrong (check: Osei commission)",
            f"refunds are recovered at the rate the refunded deal was paid: {B}'s refunded July deal sat in the 8% band on July's "
            "statement although her August never leaves the lower bands, and "
            f"{C}'s partly refunded August deal ({rc['line']['id']}) was one of her first of the month at 3% although her month ends "
            "in the 8% band (checks: Brooks net payout; Kim net payout)",
            f"{H} moved to the Senior plan (5% to $40,000, 9% above) from August 1, stated only in Marcus's email; her fully refunded "
            "July deal was paid at the standard 3% and is recovered at 3%, not at a senior rate (check: Haddad net payout)",
            "two August deals name two owners ('Kwame Osei / Daniel Kim'); each rep is credited half, which moves both reps' "
            "bands (checks: Osei commission; total net payout)",
            f"the CRM export carries {len(d['noise'])} quotes, negotiations and lost deals with amounts under a two-line preamble; only "
            "Closed Won counts (check: total net payout)",
            "Marcus wants the numbers to work from formulas; a pasted-values sheet fails (check: live formulas)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "commissions.xlsx", "min_count": 10},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "commissions.xlsx"},
            {"type": "xlsx_value_present", "name": "Osei commission (graduated bands, split deals halved)", "path": "commissions.xlsx",
             "expected": st[A]["commission"], "rel_tol": cent_tol(st[A]["commission"], 0.004), "near_text": "osei"},
            {"type": "xlsx_value_present", "name": "Brooks net payout (July deal recovered at 8%)", "path": "commissions.xlsx",
             "expected": st[B]["net"], "rel_tol": cent_tol(st[B]["net"], 0.004), "near_text": "brooks"},
            {"type": "xlsx_value_present", "name": "Kim net payout (August deal recovered at 3%)", "path": "commissions.xlsx",
             "expected": st[C]["net"], "rel_tol": cent_tol(st[C]["net"], 0.004), "near_text": "kim"},
            {"type": "xlsx_value_present", "name": "Haddad net payout (senior plan, July deal at the standard rate)", "path": "commissions.xlsx",
             "expected": st[H]["net"], "rel_tol": cent_tol(st[H]["net"], 0.004), "near_text": "haddad"},
            {"type": "xlsx_value_present", "name": "total net payout", "path": "commissions.xlsx",
             "expected": d["total_net"], "rel_tol": cent_tol(d["total_net"], 0.004), "near_text": "total"},
        ],
    })
    print(f"seed={seed} aug_deals={len(d['aug'])} jul_deals={len(d['jul'])} total_net={d['total_net']}")
    for rp in reps:
        print("  ", rp, st[rp])
    print("  naive:", naive_stmt(d))


def write_naive(d: dict, out: str) -> None:
    os.makedirs(out, exist_ok=True)
    ns = naive_stmt(d)
    rows = [[rp, s["bookings"], s["commission"], s["recoveries"], s["net"]] for rp, s in ns.items()]
    rows.append(["Total", round(sum(s["bookings"] for s in ns.values()), 2), round(sum(s["commission"] for s in ns.values()), 2),
                 round(sum(s["recoveries"] for s in ns.values()), 2), round(sum(s["net"] for s in ns.values()), 2)])
    write_xlsx(os.path.join(out, "commissions.xlsx"), {"August": {"header": ["Rep", "Sales", "Commission", "Clawback", "Net"], "rows": rows}},
               creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(800):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 800 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
