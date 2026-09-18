#!/usr/bin/env python3
"""investor-update: finance's monthly KPI tracker becomes the Q2 2026 investor update letter.

    python gen.py [--seed N]

Business: a small B2B software company that writes its investors a letter every quarter. The CEO's note says
what the letter covers; finance's KPI workbook is the source of every figure.

Traps (each caught by a check, see task.yaml):
  * finance's email restates May revenue (a duplicate invoice is still in the sheet); Q2 revenue and the growth
    rate must use the restated month                                     (checks: quarter revenue figures; growth rate; unrestated total absent)
  * last quarter's letter quotes preliminary Q1 revenue; the sheet's closed Q1 is different, and the growth rate
    has to be computed from the sheet                                    (checks: quarter revenue figures; growth rate)
  * the workbook ends with a July forecast column, so "last column" is not the end of the quarter
                                                                         (check: end-of-June ARR, customers and cash)
  * net burn is text in parentheses, and runway is cash over the quarter's average monthly burn, not June's
                                                                         (check: runway)
  * the CEO's note forbids mentioning an acquisition conversation        (check: confidential conversation not mentioned)
"""
from __future__ import annotations
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COMPANY = "Kestrel Analytics"
ACQUIRER = "Vantage Point Media"
MONTHS = ["Jan-26", "Feb-26", "Mar-26", "Apr-26", "May-26", "Jun-26"]


def pct_variants(g: float) -> set[str]:
    return {f"{g:.1f}", f"{g:.2f}", f"{round(g)}"}


def months_variants(v: float) -> set[str]:
    out = {f"{v:.1f}"}
    if abs(v - round(v)) <= 0.3:
        out.add(f"{round(v)}")
    return out


def build(seed: int) -> dict:
    r = rng(seed * 1000 + 303)
    while True:
        rev0 = r.randint(96000, 128000)
        growth_m = [r.uniform(0.018, 0.055) for _ in range(6)]
        rev = []
        x = rev0
        for gm in growth_m:
            rev.append(round(x))
            x *= 1 + gm
        mrr = [round(v * r.uniform(0.86, 0.92) / 10) * 10 for v in rev]
        mrr_jul = round(mrr[-1] * 1.03 / 10) * 10
        dup = r.randint(14, 22) * 1000 + r.choice([150, 450, 600, 850])
        sheet_rev = rev[:]
        sheet_rev[4] = rev[4] + dup
        q1 = sum(rev[:3]); q2 = sum(rev[3:])
        q1_prelim = q1 + r.choice([-1, 1]) * r.randint(6000, 11000)
        g_true = (q2 - q1) / q1 * 100
        naive = [(q2 + dup - q1) / q1 * 100, (q2 - q1_prelim) / q1_prelim * 100, (q2 + dup - q1_prelim) / q1_prelim * 100,
                 (mrr[5] - mrr[2]) / mrr[2] * 100]
        if any(abs(n - g_true) < 1.2 for n in naive) or any(pct_variants(n) & pct_variants(g_true) for n in naive):
            continue
        burn = [r.randint(62, 98) * 1000 + r.randint(0, 999) for _ in range(6)]
        cash = [0] * 6
        cash[5] = r.randint(1150, 1650) * 1000 + r.randint(0, 999)
        for i in range(4, -1, -1):
            cash[i] = cash[i + 1] + burn[i + 1]
        runway = cash[5] / (sum(burn[3:]) / 3)
        naive_rw = [cash[5] / burn[5], cash[5] / (sum(burn) / 6), (cash[5] - burn[5]) / (sum(burn[3:]) / 3)]
        if any(abs(n - runway) < 0.35 for n in naive_rw) or any(months_variants(n) & months_variants(runway) for n in naive_rw):
            continue
        cust = [r.randint(180, 230)]
        new, churn = [], []
        for i in range(6):
            nw, ch = r.randint(9, 19), r.randint(2, 7)
            new.append(nw); churn.append(ch)
            if i:
                cust.append(cust[-1] + nw - ch)
        cust_jul = cust[-1] + 11 - 4
        head = [21, 22, 22, 24, 25, r.choice([27, 28])]
        gm_pct = [round(r.uniform(0.74, 0.81), 3) for _ in range(6)]
        cash_jul = cash[5] - r.randint(70, 95) * 1000
        return {"rev": rev, "sheet_rev": sheet_rev, "mrr": mrr, "mrr_jul": mrr_jul, "dup": dup, "q1": q1, "q2": q2,
                "q2_unrestated": q2 + dup, "q1_prelim": q1_prelim, "g_true": g_true, "burn": burn, "cash": cash,
                "runway": runway, "cust": cust, "cust_jul": cust_jul, "new": new, "churn": churn, "head": head,
                "gm": gm_pct, "cash_jul": cash_jul, "arr": mrr[5] * 12, "naive_growth": naive, "naive_runway": naive_rw,
                "invoice": f"INV-{r.randint(2100, 2999)}", "customer": r.choice(["Harbor Light Marine", "Dorsey Freight", "Pinnacle Roofing"])}


def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    money = lambda v: f"${v:,.0f}"
    paren = lambda v: f"({v:,.0f})"
    rows = [
        ["Revenue (recognized)"] + d["sheet_rev"] + [None],
        ["MRR (end of month)"] + d["mrr"] + [d["mrr_jul"]],
        ["Paying customers (end of month)"] + d["cust"] + [d["cust_jul"]],
        ["New customers"] + d["new"] + [11],
        ["Churned customers"] + d["churn"] + [4],
        ["Gross margin"] + d["gm"] + [None],
        ["Net burn"] + [paren(b) for b in d["burn"]] + [paren(d["cash"][5] - d["cash_jul"])],
        ["Cash balance (end of month)"] + d["cash"] + [d["cash_jul"]],
        ["Headcount (end of month)"] + d["head"] + [d["head"][-1] + 1],
    ]
    write_xlsx(os.path.join(ws, "kpi_tracker_2026.xlsx"), {"Monthly KPIs": {
        "merged_title": f"{COMPANY} - KPI tracker (Finance)",
        "preamble": [["All figures USD. Month-end close. Updated 10 Jul 2026 by P. Shah"], []],
        "header": ["Metric"] + MONTHS + ["Jul-26 (fcst)"], "rows": rows,
        "number_formats": {c: "#,##0" for c in "BCDEFGH"}, "widths": {"A": 32}}}, creator="Finance")

    write_text(os.path.join(ws, "email_from_priya_finance.txt"), f"""From: Priya Shah <priya.shah@kestrelanalytics.io>
To: Marcus Reed <marcus@kestrelanalytics.io>
Date: Mon, 13 Jul 2026 16:05
Subject: May revenue restated

Marcus,

Found it: {d['invoice']} to {d['customer']} was posted twice in May, so May revenue in the KPI tracker is overstated by
{money(d['dup'])}. Restated May revenue is {money(d['rev'][4])}. I will fix the tracker after the audit fieldwork, but use the
restated number for anything going out before then. Nothing else in the sheet changes.

Priya
""")

    write_text(os.path.join(ws, "note_from_marcus.txt"), f"""Q2 investor update - draft please

Same shape as the Q1 letter. Every figure comes from Finance's KPI tracker, except where Priya has corrected it.
Heads up that the Q1 letter went out before March closed, so its Q1 numbers were preliminary - do not reuse them.

Cover:
- Q2 revenue, and growth over Q1 (quarter revenue vs previous quarter revenue, as a percent)
- ARR at the end of June (June MRR x 12)
- paying customers at the end of June
- cash at the end of June and runway in months: cash divided by the average monthly net burn over the quarter,
  one decimal
- headcount

Investors asked us to stop rounding to "k", so full dollar amounts.

Do NOT mention the conversation with {ACQUIRER}. Nothing is signed and it is confidential.

Save as update.md.
Marcus
""")

    q1p = d["q1_prelim"]
    write_text(os.path.join(ws, "investor_update_q1_2026.md"), f"""# {COMPANY} - Q1 2026 investor update

Hi all,

Q1 revenue was {money(q1p)} (preliminary, pending March close). MRR at the end of March was {money(d['mrr'][2])}, which puts ARR
at {money(d['mrr'][2] * 12)}. We ended the quarter with {d['cust'][2]} paying customers and a team of {d['head'][2]}.

Cash at the end of March was {money(d['cash'][2])}.

Highlights: the new usage-based pricing went live in February and our first two healthcare logos signed in March.

Thanks for your support,
Marcus
""")

    g = d["g_true"]; rw = d["runway"]
    letter = f"""# {COMPANY} - Q2 2026 investor update

Hi all,

Revenue for Q2 2026 was {money(d['q2'])}, up {g:.1f}% from {money(d['q1'])} in Q1. May revenue is restated to {money(d['rev'][4])} after finance found a duplicate invoice.

MRR at the end of June was {money(d['mrr'][5])}, which puts ARR at {money(d['arr'])}.

We ended June with {d['cust'][5]} paying customers.

Cash at the end of June was {money(d['cash'][5])}. Average monthly net burn over the quarter was {money(round(sum(d['burn'][3:]) / 3))}, which gives a runway of {rw:.1f} months.

Headcount at the end of June was {d['head'][5]}.

Thanks for your support,
Marcus
"""
    write_text(os.path.join(sol, "update.md"), letter)
    facts = {k: d[k] for k in ["q1", "q2", "q2_unrestated", "q1_prelim", "g_true", "runway", "arr", "dup"]}
    facts.update({"cust_june": d["cust"][5], "cash_june": d["cash"][5], "mrr_june": d["mrr"][5], "naive_growth": d["naive_growth"],
                  "naive_runway": d["naive_runway"]})
    write_json(os.path.join(ref, "facts.json"), facts)

    gre = "|".join(sorted(re.escape(v) for v in pct_variants(g)))
    rre = "|".join(sorted(re.escape(v) for v in months_variants(rw)))
    unrest = d["q2_unrestated"]
    write_task_yaml(HERE, {
        "id": "investor-update", "track": "desk", "category": "drafting",
        "title": "Q2 investor update letter from the KPI tracker",
        "ask": "Please draft the Q2 investor update from finance's KPI tracker. Marcus's note says what goes in it. Save it as update.md.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"Priya's email restates May revenue: the tracker still carries a duplicate invoice of {money(d['dup'])}, so the sheet's Q2 total ({money(unrest)}) is wrong and the letter must say {money(d['q2'])} (checks: quarter revenue figures; unrestated Q2 total absent)",
            f"the Q1 letter quoted preliminary Q1 revenue of {money(q1p)}; the tracker's closed Q1 is {money(d['q1'])} (checks: quarter revenue figures; growth over Q1)",
            f"growth is quarter revenue over quarter revenue, {g:.1f}%; using the unrestated May, the preliminary Q1 or June-over-March MRR gives {', '.join(f'{n:.1f}%' for n in d['naive_growth'])} (check: growth over Q1)",
            f"the tracker's last column is a July forecast, so ARR, customers and cash at the end of the quarter come from June, not the right-hand column (check: end-of-June ARR, customers and cash)",
            f"net burn is text in parentheses; runway is June cash over the average Q2 burn, {rw:.1f} months, not over June's burn or the six-month average ({', '.join(f'{n:.1f}' for n in d['naive_runway'])}) (check: runway)",
            f"Marcus forbids any mention of the {ACQUIRER} conversation (check: confidential conversation not mentioned)",
        ],
        "checks": [
            {"type": "file_exists", "name": "update.md exists", "path": "update.md"},
            {"type": "text_numbers_present", "name": "quarter revenue figures", "path": "update.md",
             "numbers": [d["q2"], d["q1"]], "rel_tol": 0.0005},
            {"type": "text_sentence_matches", "name": "growth over Q1", "path": "update.md",
             "all": [rf"(?<![\d.])({gre})\s*(%|percent|per cent)", r"(grow|grew|growth|increase|\bup\b|\brose\b|higher|over q1|from q1|vs\.? q1|quarter[- ]over[- ]quarter|qoq)"]},
            {"type": "text_numbers_present", "name": "end-of-June ARR, customers and cash", "path": "update.md",
             "numbers": [d["arr"], d["cust"][5], d["cash"][5]], "rel_tol": 0.0005},
            {"type": "text_sentence_matches", "name": "runway", "path": "update.md",
             "all": [r"(runway|months of (cash|runway)|last us|cash (lasts|will last))", rf"(?<![\d.])({rre})\s*(-|\s)?months?\b"]},
            {"type": "text_not_contains", "name": "unrestated Q2 total absent", "path": "update.md",
             "phrases": [f"{unrest:,}", f"{unrest}"]},
            {"type": "text_not_contains", "name": "confidential conversation not mentioned", "path": "update.md",
             "phrases": [ACQUIRER, ACQUIRER.split()[0] + " Point"]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
