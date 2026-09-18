#!/usr/bin/env python3
"""mrr-report: monthly recurring revenue and churn for a small analytics SaaS, from a billing event log.

    python gen.py [--seed N] [--naive DIR]

Business: a 50-account B2B analytics product. Billing writes one row per subscription event; nobody has
ever turned that into an MRR schedule, and the board now wants one.

Traps (each caught by a check, see task.yaml):
  * upgrade / downgrade rows carry the new full price, not the change   (checks: March ending MRR; June ending MRR)
  * annual contracts carry the yearly amount and count at one twelfth   (checks: March ending MRR; June ending MRR)
  * cancellations have a notice period, so the effective date is what ends the subscription
                                                                        (checks: worst month churn; June ending MRR)
  * trials carry the list price and are not revenue until they convert  (checks: March ending MRR; June ending MRR)
  * a churned account reactivates later in the half                     (check: June ending MRR)
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


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))



# bizgen.write_xlsx leaves openpyxl's save-time wall clock in docProps/core.xml, so two runs a
# second apart produce different bytes and the validator's determinism check fails intermittently.
# Local workaround (tasks/lib is not ours to change): pin dcterms:modified and re-freeze the zip.
import io as _io  # noqa: E402
import re as _re  # noqa: E402
import zipfile as _zip  # noqa: E402


def stable_xlsx(path: str, sheets: dict, creator: str = "Export") -> None:
    write_xlsx(path, sheets, creator=creator)
    with _zip.ZipFile(path) as z:
        items = sorted((n, z.read(n)) for n in z.namelist())
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as out:
        for name, data in items:
            if name == "docProps/core.xml":
                data = _re.sub(rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>",
                               b'<dcterms:modified xsi:type="dcterms:W3CDTF">2026-01-15T09:00:00Z</dcterms:modified>',
                               data)
            zi = _zip.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = _zip.ZIP_DEFLATED
            out.writestr(zi, data)
    write_bytes(path, buf.getvalue())

MONTHS = ["2025-12"] + [f"2026-{m:02d}" for m in range(1, 7)]
REPORT_MONTHS = MONTHS[1:]
PLANS = {"Starter": 49.00, "Team": 199.00, "Business": 499.00, "Scale": 1190.00}
ANNUAL = {"Starter (annual)": 528.00, "Team (annual)": 2148.00, "Business (annual)": 5388.00, "Scale (annual)": 12840.00}
WORST = "2026-05"     # the month the memo has to name
N_ACCOUNTS = 52


def month_end(m: str) -> date:
    y, mm = int(m[:4]), int(m[5:])
    return date(y, mm, calendar.monthrange(y, mm)[1])


def monthly_value(plan: str, amount: float) -> float:
    return round(amount / 12.0, 2) if plan in ANNUAL else amount


def build(seed: int) -> dict:
    r = rng(seed)
    names = [c[0] for c in COMPANIES]
    while len(names) < N_ACCOUNTS:
        names = names + [f"{n} Group" for n in names]
    names = names[:N_ACCOUNTS]
    plan_names = sorted(PLANS) + sorted(ANNUAL)
    accounts = []
    ev = 9000
    for i, nm in enumerate(names):
        plan = r.choice(plan_names)
        amount = PLANS.get(plan) or ANNUAL[plan]
        if i < 34:                       # already on the book before the report period
            start = day_in(r, date(2024, 6, 1), date(2025, 11, 20))
        elif i < N_ACCOUNTS - 6:         # signed during the half
            start = date(2026, r.randint(1, 6), r.randint(1, 27))
        else:                            # trials, list price shown, not billed
            start = date(2026, r.randint(2, 6), r.randint(1, 20))
        accounts.append({"name": nm, "plan": plan, "amount": amount, "start": start,
                         "trial": i >= N_ACCOUNTS - 6, "events": [], "points": []})

    def add(a, kind, d, plan, amount, note="", effective=None):
        nonlocal ev
        ev += 1
        a["events"].append({"id": f"EV-{ev}", "date": d, "effective": effective or d, "kind": kind,
                            "plan": plan, "amount": amount, "note": note, "k": r.random()})

    for a in accounts:
        if a["trial"]:
            add(a, "trial", a["start"], a["plan"], a["amount"], "14-day trial, not billed")
            continue
        add(a, "new", a["start"], a["plan"], a["amount"], "")
        a["points"].append((a["start"], monthly_value(a["plan"], a["amount"])))

    # two trials convert to paying during the half
    for a in [x for x in accounts if x["trial"]][:2]:
        conv = min(a["start"] + timedelta(days=14), date(2026, 6, 20))
        plan = r.choice(sorted(PLANS))
        add(a, "new", conv, plan, PLANS[plan], "converted from trial")
        a["points"].append((conv, PLANS[plan]))

    live = [a for a in accounts if a["points"] and a["points"][0][0] < date(2026, 5, 1)]
    # upgrades and downgrades: the row carries the NEW full price
    for a in r.sample([x for x in live if x["points"][0][0] < date(2026, 4, 1)], 18):
        d = date(2026, r.randint(1, 6), r.randint(1, 27))
        if d <= a["points"][-1][0]:
            continue
        up = r.random() < 0.62
        pool = sorted(PLANS) if a["plan"] in PLANS else sorted(ANNUAL)
        cur = a["points"][-1][1]
        cands = [p for p in pool if (monthly_value(p, PLANS.get(p) or ANNUAL[p]) > cur) == up
                 and monthly_value(p, PLANS.get(p) or ANNUAL[p]) != cur]
        if not cands:
            continue
        plan = r.choice(cands)
        amount = PLANS.get(plan) or ANNUAL[plan]
        add(a, "upgrade" if up else "downgrade", d, plan, amount, "new price effective today")
        a["points"].append((d, monthly_value(plan, amount)))

    # cancellations: four land in the month the memo must name, two give notice in June for a
    # July end date (so they are still on the book at the end of the half)
    cancel_pool = [x for x in live if x["points"][0][0] < date(2026, 3, 1)]
    heavy = sorted(cancel_pool, key=lambda x: -x["points"][-1][1])[:10]
    cancels = r.sample(heavy, 6) + r.sample([x for x in cancel_pool if x not in heavy], 8)
    for i, a in enumerate(cancels):
        if i == 0:                                   # notice given a month and a half ahead
            eff = date(int(WORST[:4]), int(WORST[5:]), r.randint(6, 20))
            logged = date(2026, 3, r.randint(12, 26))
        elif i < 4:                                  # concentrated in the month the memo must name
            eff = date(int(WORST[:4]), int(WORST[5:]), r.randint(3, 24))
            logged = eff - timedelta(days=r.choice([2, 32, 38]))
        elif i < 6:                                  # logged in June, effective in July
            logged = date(2026, 6, r.randint(8, 20))
            eff = date(2026, 7, r.randint(5, 25))
        else:
            eff = date(2026, r.choice([2, 3, 4, 6]), r.randint(3, 24))
            logged = eff - timedelta(days=r.choice([0, 0, 3]))
        if logged <= a["points"][-1][0]:
            logged = a["points"][-1][0] + timedelta(days=1)
        if eff <= logged:
            eff = logged + timedelta(days=2)
        add(a, "cancellation", logged, a["events"][-1]["plan"], a["events"][-1]["amount"],
            f"effective {eff.isoformat()}" if eff != logged else "effective immediately", effective=eff)
        a["points"].append((eff, 0.0))

    # two accounts come back
    for a in [x for x in cancels if x["points"][-1][0] < date(2026, 5, 10)][:2]:
        back = a["points"][-1][0] + timedelta(days=r.randint(25, 55))
        if back > date(2026, 6, 25):
            continue
        plan = r.choice(sorted(PLANS))
        add(a, "reactivation", back, plan, PLANS[plan], "came back on a monthly plan")
        a["points"].append((back, PLANS[plan]))

    for a in accounts:
        a["points"].sort(key=lambda p: p[0])
        a["events"].sort(key=lambda e: (e["date"], e["id"]))

    # ---- truth ----
    def value_on(a, d: date) -> float:
        v = 0.0
        for pd, pv in a["points"]:
            if pd <= d:
                v = pv
        return v

    ending, churned, paying = {}, {}, {}
    for m in MONTHS:
        me = month_end(m)
        ending[m] = round(sum(value_on(a, me) for a in accounts), 2)
        paying[m] = sum(1 for a in accounts if value_on(a, me) > 0)
        lost = 0.0
        for a in accounts:
            for j, (pd, pv) in enumerate(a["points"]):
                if pv == 0.0 and j > 0 and f"{pd.year}-{pd.month:02d}" == m:
                    lost += a["points"][j - 1][1]
        churned[m] = round(lost, 2)
    events = sorted([dict(e, acct=a["name"], trial=a["trial"]) for a in accounts for e in a["events"]],
                    key=lambda e: (e["date"], e["id"]))
    return {"accounts": accounts, "events": events, "ending": ending, "churned": churned,
            "paying": paying, "value_on": value_on,
            "churn_total": round(sum(churned[m] for m in REPORT_MONTHS), 2)}


def acceptable(d: dict) -> bool:
    ending, churned = d["ending"], d["churned"]
    if churned[WORST] < 1.4 * max(churned[m] for m in REPORT_MONTHS if m != WORST):
        return False
    if min(ending[m] for m in REPORT_MONTHS) < 1000:
        return False
    for m in ("2026-03", "2026-06"):
        me = month_end(m)
        # trials priced at list, counted naively
        trial = sum(a["amount"] for a in d["accounts"]
                    if a["trial"] and a["start"] <= me and d["value_on"](a, me) == 0)
        # annual contracts counted at their yearly amount
        annual = sum((a["amount"] - monthly_value(a["plan"], a["amount"])) for a in d["accounts"]
                     if a["plan"] in ANNUAL and d["value_on"](a, me) > 0)
        # cancellations that a log-date reading would retire a month early
        early = sum(a["points"][j - 1][1] for a in d["accounts"] for j, (pd, pv) in enumerate(a["points"])
                    if pv == 0.0 and j > 0 and any(e["kind"] == "cancellation" and e["date"] <= me < e["effective"]
                                                   for e in a["events"]))
        if trial < 0.015 * ending[m] or annual < 0.05 * ending[m] or early < 0.015 * ending[m]:
            return False
        # no other month's ending MRR sits on top of the pinned one
        if sum(1 for mm in MONTHS if abs(ending[mm] - ending[m]) <= 0.01 * ending[m]) > 1:
            return False
    if abs(churned[WORST] - d["churn_total"]) <= 0.02 * d["churn_total"]:
        return False
    if sum(1 for m in MONTHS if abs(d["ending"][m] - churned[WORST]) <= 0.01 * churned[WORST]) > 0:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(data_rows: list[list]) -> dict:
    n = len(data_rows) + 1
    rows = []
    for i, m in enumerate(MONTHS, start=2):
        label = m + (" (opening)" if i == 2 else "")
        rows.append([label,
                     f"=SUMIFS(Data!$C$2:$C${n},Data!$B$2:$B${n},\"{m}\")",
                     f"=SUMIFS(Data!$D$2:$D${n},Data!$B$2:$B${n},\"{m}\")",
                     "" if i == 2 else f"=B{i}-B{i - 1}",
                     f"=SUMIFS(Data!$E$2:$E${n},Data!$B$2:$B${n},\"{m}\")"])
    last = 1 + len(MONTHS)
    rows.append(["H1 2026 total", "", f"=SUM(C3:C{last})", f"=B{last}-B2", ""])
    return {
        "Data": {"header": ["account", "month", "month_end_mrr", "churned_mrr", "paying"], "rows": data_rows,
                 "widths": {"A": 28, "C": 15, "D": 14}},
        "Report": {"header": ["Month", "Ending MRR", "Churned MRR", "Net change", "Paying accounts"], "rows": rows,
                   "widths": {"A": 18, "B": 13, "C": 14, "D": 12, "E": 16}},
    }


def clean_rows(d: dict) -> list[list]:
    out = []
    for a in sorted(d["accounts"], key=lambda x: x["name"]):
        for m in MONTHS:
            me = month_end(m)
            v = round(d["value_on"](a, me), 2)
            lost = 0.0
            for j, (pd, pv) in enumerate(a["points"]):
                if pv == 0.0 and j > 0 and f"{pd.year}-{pd.month:02d}" == m:
                    lost += a["points"][j - 1][1]
            out.append([a["name"], m, v, round(lost, 2), 1 if v > 0 else 0])
    return out


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    ending, churned = d["ending"], d["churned"]

    # ---- workspace ----
    rows = []
    for e in d["events"]:
        st = sum(ord(c) for c in e["id"]) % 3
        period = "" if st == 0 and e["plan"] in ANNUAL else ("Annual" if e["plan"] in ANNUAL else "Monthly")
        rows.append([e["id"], date_variant(e["date"], [0, 1, 2][st]), e["acct"],
                     {"new": "new", "upgrade": "Upgrade", "downgrade": "Downgrade", "cancellation": "Cancellation",
                      "reactivation": "Reactivation", "trial": "Trial start"}[e["kind"]],
                     e["plan"], period, money_str(e["amount"], [1, 0, 6][st]),
                     e["effective"].isoformat() if e["effective"] != e["date"] else "", e["note"]])
    write_csv(os.path.join(ws, "subscription_events_2026.csv"),
              ["Event ID", "Logged", "Account", "Event", "Plan", "Billing period", "Contract amount",
               "Effective date", "Note"], rows,
              preamble=["Billing event log", "Exported 07/02/2026 - includes the 2025 book"], crlf=True)
    opening = [(a["name"], round(d["value_on"](a, month_end("2025-12")), 2)) for a in d["accounts"]]
    opening = sorted([x for x in opening if x[1] > 0])
    stable_xlsx(os.path.join(ws, "opening_book_dec2025.xlsx"), {"Book": {
        "merged_title": "Subscriptions on the book at 31 Dec 2025",
        "header": ["Account", "Monthly value"], "rows": [[n, v] for n, v in opening],
        "number_formats": {"B": "#,##0.00"}, "widths": {"A": 30, "B": 16}}}, creator="Finance")
    write_email_thread(os.path.join(ws, "email_from_finance.txt"), [
        {"from": "Marcus Lindqvist <marcus@kestrelanalytics.io>", "to": "you", "date": "Thu, 2 Jul 2026 09:20",
         "subject": "MRR schedule for the board pack",
         "body": ("The board wants MRR by month for the first half and a clear view of what we lost to churn. "
                  "Everything is in the billing event log; the December book is there as the starting point.\n\n"
                  "MRR is what the active subscriptions are worth on the last day of the month. Annual contracts "
                  "are written at the yearly amount in the log - they count at a twelfth of that.")},
        {"from": "Marcus Lindqvist <marcus@kestrelanalytics.io>", "to": "you", "date": "Thu, 2 Jul 2026 09:41",
         "subject": "RE: MRR schedule for the board pack",
         "body": ("Two things the log does not make obvious. When somebody moves plan, the amount on that row is the "
                  "new price they pay from that day - it is not the increase. And a cancellation ends on its "
                  "effective date, not the day support logged it; the big ones give us notice, so the money keeps "
                  "coming until the effective date.\n\nTrials are on list price in the log but we do not bill them. "
                  "They are not revenue until the account converts.\n\nIn the memo, tell me which month the churn "
                  "landed in and what it cost us.")}])

    # ---- reference ----
    write_csv(os.path.join(ref, "mrr_by_month.csv"), ["month", "ending_mrr", "churned_mrr", "paying_accounts"],
              [[m, f"{ending[m]:.2f}", f"{churned[m]:.2f}", d["paying"][m]] for m in MONTHS])
    write_json(os.path.join(ref, "notes.json"), {
        "worst_churn_month": WORST, "worst_churn_mrr": churned[WORST], "h1_churn_total": d["churn_total"],
        "ending_mrr": ending, "events": len(d["events"]),
        "annual_accounts": sum(1 for a in d["accounts"] if a["plan"] in ANNUAL),
        "trial_accounts": sum(1 for a in d["accounts"] if a["trial"])})

    # ---- reference solution ----
    stable_xlsx(os.path.join(sol, "mrr.xlsx"), report_sheets(clean_rows(d)), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    month_word = {"2026-01": "January", "2026-02": "February", "2026-03": "March", "2026-04": "April",
                  "2026-05": "May", "2026-06": "June"}[WORST]
    write_task_yaml(HERE, {
        "id": "mrr-report", "track": "desk", "category": "reports",
        "title": "MRR by month and churn for the first half",
        "ask": ("The board pack needs our MRR month by month for the first half and what we lost to churn. Build it "
                "as mrr.xlsx with live formulas and write memo.md alongside it. Marcus's email says how he wants "
                "the subscriptions counted.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "upgrade and downgrade rows carry the account's new full price, not the change; adding them to the "
            "previous price inflates MRR from the month of the move onwards "
            "(checks: March ending MRR; June ending MRR)",
            f"{sum(1 for a in d['accounts'] if a['plan'] in ANNUAL)} accounts are on annual contracts written at the "
            "yearly amount, which counts at one twelfth; the billing-period column is blank on some of those rows "
            "(checks: March ending MRR; June ending MRR)",
            "cancellations carry a separate effective date after the notice period, so the subscription is still "
            "live at the end of the month it was logged in; four of them move a whole month "
            "(checks: worst month churned MRR; June ending MRR)",
            f"{sum(1 for a in d['accounts'] if a['trial'])} trial accounts are logged at list price and are not "
            "revenue until they convert; two of them convert during the half "
            "(checks: March ending MRR; June ending MRR)",
            "two churned accounts reactivate later in the half and count again from their reactivation date "
            "(check: June ending MRR)",
            "amounts are '$199.00' / '$5,388.00' text, dates come in three formats and the export has a two-line "
            "preamble with CRLF endings (check: March ending MRR)",
            f"the churn is concentrated in one month ({month_word}) behind the notice periods, so a memo written off "
            "the logged dates names the wrong month (check: memo names the month the churn landed in)",
        ],
        "checks": [
            {"type": "file_exists", "name": "mrr.xlsx exists", "path": "mrr.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "mrr.xlsx", "min_count": 10},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "mrr.xlsx"},
            {"type": "xlsx_value_present", "name": "March ending MRR", "path": "mrr.xlsx",
             "expected": ending["2026-03"], "rel_tol": cent_tol(ending["2026-03"], 0.005), "near_text": "mrr"},
            {"type": "xlsx_value_present", "name": "June ending MRR", "path": "mrr.xlsx",
             "expected": ending["2026-06"], "rel_tol": cent_tol(ending["2026-06"], 0.005), "near_text": "mrr"},
            {"type": "xlsx_value_present", "name": f"churned MRR in {month_word}", "path": "mrr.xlsx",
             "expected": churned[WORST], "rel_tol": cent_tol(churned[WORST], 0.005), "near_text": "churn"},
            {"type": "xlsx_value_present", "name": "churned MRR for the half", "path": "mrr.xlsx",
             "expected": d["churn_total"], "rel_tol": cent_tol(d["churn_total"], 0.005), "near_text": "churn"},
            {"type": "text_numbers_present", "name": "memo carries the June MRR and the churn figure", "path": "memo.md",
             "numbers": [ending["2026-06"], churned[WORST]], "rel_tol": 0.005},
            {"type": "text_sentence_matches", "name": "memo names the month the churn landed in", "path": "memo.md",
             "all": [rf"(\b{month_word.lower()}\b|\b{WORST}\b|\b{WORST[5:]}/2026\b)",
                     r"(\bchurn|\bcancel|\blost\b|\bleft\b)"],
             "none": [r"\bno churn\b", r"\bnothing churned\b"]},
        ],
    })
    print(f"seed={seed} accounts={len(d['accounts'])} events={len(d['events'])}")
    print("ending:", {m: f"{ending[m]:.2f}" for m in MONTHS})
    print("churned:", {m: f"{churned[m]:.2f}" for m in MONTHS}, "h1 churn:", d["churn_total"])
    print("paying:", d["paying"])


def memo_text(d: dict) -> str:
    ending, churned = d["ending"], d["churned"]
    month_word = {"2026-05": "May", "2026-04": "April", "2026-03": "March"}[WORST]
    growth = round(ending["2026-06"] - ending["2025-12"], 2)
    return f"""# MRR and churn, first half 2026

We opened the year at {ending['2025-12']:,.2f} MRR and closed June at {ending['2026-06']:,.2f}, a net change of
{growth:,.2f} over the half. March ended at {ending['2026-03']:,.2f}.

**Churn landed in {month_word}.** {churned[WORST]:,.2f} of MRR cancelled with an effective date in {month_word},
which is more than the rest of the half put together; total churn for the six months was {d['churn_total']:,.2f}.
Those cancellations were logged weeks earlier - the notice period is why the money only leaves in {month_word}.

Two things to keep in mind when reading the schedule:

1. Annual contracts are in the event log at their yearly amount and are counted here at one twelfth. Trials sit in
   the log at list price and are excluded until the account converts; two converted during the half.
2. Plan changes carry the new full price on the event row, so the schedule tracks the price in force at each
   month end rather than adding the row amounts together.
"""


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: take each account's latest event amount as its MRR, at face value,
    with trials and annual contracts included as written and cancellations applied when logged."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for a in sorted(d["accounts"], key=lambda x: x["name"]):
        for m in MONTHS:
            me = month_end(m)
            seen = [e for e in a["events"] if e["date"] <= me]
            v = 0.0 if not seen or seen[-1]["kind"] == "cancellation" else seen[-1]["amount"]
            lost = sum(e["amount"] for e in a["events"]
                       if e["kind"] == "cancellation" and f"{e['date'].year}-{e['date'].month:02d}" == m)
            rows.append([a["name"], m, round(v, 2), round(lost, 2), 1 if v > 0 else 0])
    stable_xlsx(os.path.join(out, "mrr.xlsx"), report_sheets(rows), creator="naive")
    write_text(os.path.join(out, "memo.md"),
               "# MRR and churn\n\nMRR grew over the first half and a handful of accounts cancelled along the way. "
               "The schedule in mrr.xlsx shows the month-by-month figures straight from the billing log.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(600):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 600 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
