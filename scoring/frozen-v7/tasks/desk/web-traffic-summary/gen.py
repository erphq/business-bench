#!/usr/bin/env python3
"""web-traffic-summary: GA4 daily traffic exports to a spring monthly summary, with a crawler day taken out.

    python gen.py [--seed N] [--naive DIR]

Business: an online kayak and paddle shop. The owner wants March to May traffic by month. Her SEO agency ran
a site crawl one day in April and GA4 counted it as visitors; Tom's note describes the crawler but not the day.

Traps (each caught by a check, see task.yaml):
  * one April day carries thousands of Unassigned sessions with zero engagement: the crawler      (checks: April sessions; memo)
  * the spring-sale email a few days earlier is a real spike and stays                           (check: April sessions)
  * daily users cannot be added up; monthly users come from the monthly export                   (check: May users)
  * the export is GA4's "last 100 days" with a '#' comment preamble and YYYYMMDD dates, so it starts in February
                                                                                                 (check: sessions March to May)
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


START, END = date(2026, 2, 21), date(2026, 5, 31)
MONTHS = ["2026-03", "2026-04", "2026-05"]
MNAME = {"2026-03": "March", "2026-04": "April", "2026-05": "May"}
CHANNELS = ["Organic Search", "Direct", "Paid Search", "Organic Social", "Email", "Referral", "Unassigned"]
BASE = {"Organic Search": 176, "Direct": 84, "Paid Search": 58, "Organic Social": 33, "Email": 14, "Referral": 13, "Unassigned": 0.6}
ENGAGE = {"Organic Search": 0.64, "Direct": 0.58, "Paid Search": 0.55, "Organic Social": 0.41, "Email": 0.71, "Referral": 0.62, "Unassigned": 0.2}
CONV = {"Organic Search": 0.012, "Direct": 0.019, "Paid Search": 0.016, "Organic Social": 0.005, "Email": 0.03, "Referral": 0.01, "Unassigned": 0.0}
DEDUP = {"2026-02": 0.80, "2026-03": 0.74, "2026-04": 0.71, "2026-05": 0.69}


def season(d: date) -> float:
    return 1.0 + 0.9 * max(0, (d - date(2026, 2, 21)).days) / 99


def build(seed: int) -> dict:
    r = rng(seed)
    crawl_day = date(2026, 4, r.choice([7, 8, 9, 14, 15, 16, 21, 22]))
    sale_day = crawl_day - timedelta(days=r.choice([3, 5, 6]))
    while sale_day.weekday() >= 5:
        sale_day -= timedelta(days=1)
    rows = []
    d = START
    while d <= END:
        wk = 0.82 if d.weekday() >= 5 else 1.0
        for ch in CHANNELS:
            mu = BASE[ch] * season(d) * wk * r.uniform(0.8, 1.2)
            if ch == "Email":
                if d == sale_day:
                    mu *= 26
                elif d.weekday() == 3:
                    mu *= 3.2           # the Thursday newsletter
            if ch == "Unassigned":
                if d == crawl_day:
                    continue
                s = r.choice([0, 0, 0, 1, 1, 2])
            else:
                s = max(1, int(round(mu)))
            if s == 0:
                continue
            eng = int(round(s * ENGAGE[ch] * r.uniform(0.92, 1.08)))
            users = max(1, int(round(s * r.uniform(0.84, 0.93))))
            new = int(round(users * r.uniform(0.55, 0.8)))
            views = int(round(s * r.uniform(2.6, 3.6)))
            ke = sum(1 for _ in range(s) if r.random() < CONV[ch] * (1.8 if d == sale_day and ch == "Email" else 1))
            rev = round(sum(r.uniform(45, 620) for _ in range(ke)), 2)
            rows.append({"date": d, "ch": ch, "s": s, "eng": eng, "users": users, "new": new, "views": views, "ke": ke, "rev": rev, "crawl": False})
        if d == crawl_day:
            s = r.randint(4100, 6400)
            users = int(round(s * r.uniform(0.96, 0.99)))
            rows.append({"date": d, "ch": "Unassigned", "s": s, "eng": 0, "users": users, "new": users, "views": int(round(s * r.uniform(1.01, 1.12))),
                         "ke": 0, "rev": 0.0, "crawl": True})
        d += timedelta(days=1)
    rows.sort(key=lambda x: (x["date"], -x["s"]))
    mk = lambda x: f"{x['date'].year}-{x['date'].month:02d}"
    months = ["2026-02"] + MONTHS
    agg = {m: {"s": 0, "s_all": 0, "views": 0, "views_all": 0, "ke": 0, "rev": 0.0, "daily_users": 0, "daily_users_clean": 0} for m in months}
    crawler = next(x for x in rows if x["crawl"])
    for x in rows:
        a = agg[mk(x)]
        a["s_all"] += x["s"]; a["views_all"] += x["views"]; a["daily_users"] += x["users"]
        if not x["crawl"]:
            a["s"] += x["s"]; a["views"] += x["views"]; a["ke"] += x["ke"]; a["rev"] += x["rev"]; a["daily_users_clean"] += x["users"]
    monthly = {}
    for m in months:
        u = int(round(agg[m]["daily_users_clean"] * DEDUP[m] * r.uniform(0.97, 1.03)))
        nu = int(round(u * r.uniform(0.66, 0.74)))
        if m == "2026-04":
            u += crawler["users"]; nu += crawler["users"]
        monthly[m] = {"users": u, "new": nu, "sessions": agg[m]["s_all"]}
    for m in months:
        agg[m]["rev"] = round(agg[m]["rev"], 2)
    users_clean = {m: monthly[m]["users"] - (crawler["users"] if m == "2026-04" else 0) for m in MONTHS}
    return {"rows": rows, "crawl_day": crawl_day, "sale_day": sale_day, "crawler": crawler, "agg": agg, "monthly": monthly,
            "users_clean": users_clean, "total_sessions": sum(agg[m]["s"] for m in MONTHS)}


def acceptable(d: dict) -> bool:
    a, mo = d["agg"], d["monthly"]
    apr = a["2026-04"]["s"]
    pins = [apr, d["total_sessions"], mo["2026-05"]["users"]]
    naive = [a["2026-04"]["s_all"], d["total_sessions"] + a["2026-02"]["s_all"] + d["crawler"]["s"], a["2026-05"]["daily_users"]]
    if any(abs(p - n) <= 0.03 * p for p, n in zip(pins, naive)):
        return False
    others = [a[m]["s"] for m in MONTHS] + [a[m]["s_all"] for m in MONTHS] + [mo[m]["users"] for m in MONTHS] + [mo[m]["new"] for m in MONTHS] + \
             [a[m]["views"] for m in MONTHS] + [d["crawler"]["s"], d["crawler"]["users"]] + list(d["users_clean"].values())
    for p in pins:
        if any(o != p and abs(o - p) <= 0.01 * p for o in set(others)):
            return False
    # the sale-day email spike must be big enough to look like a spike, and still smaller than the crawl
    email_sale = next(x["s"] for x in d["rows"] if x["date"] == d["sale_day"] and x["ch"] == "Email")
    if not (email_sale > 400 and email_sale < 0.4 * d["crawler"]["s"]):
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_workbook(daily: list[list], monthly_rows: list[list], crawl_label: str) -> dict:
    """daily: [date, month, channel, sessions, engaged, users, new_users, views, key_events, revenue, crawler]
    monthly_rows: [month, total_users, new_users, crawler_users]"""
    n = len(daily) + 1
    summ = []
    for i, m in enumerate(MONTHS, start=2):
        mrow = 2 + i - 2
        crit = f"Daily!$B$2:$B${n},$A{i},Daily!$K$2:$K${n},0"
        summ.append([m, f"=SUMIFS(Daily!$D$2:$D${n},{crit})", f"=Users!B{mrow}-Users!D{mrow}", f"=SUMIFS(Daily!$H$2:$H${n},{crit})",
                     f"=SUMIFS(Daily!$I$2:$I${n},{crit})", f"=ROUND(SUMIFS(Daily!$J$2:$J${n},{crit}),2)", f"=ROUND(E{i}/B{i},4)"])
    summ.append(["Total, March to May", "=SUM(B2:B4)", "n/a - users do not add across months", "=SUM(D2:D4)", "=SUM(E2:E4)",
                 "=ROUND(SUM(F2:F4),2)", "=ROUND(E5/B5,4)"])
    summ.append([])
    summ.append([f"Crawler removed ({crawl_label})", f'=SUMIFS(Daily!$D$2:$D${n},Daily!$K$2:$K${n},1)',
                 f'=SUMIFS(Daily!$F$2:$F${n},Daily!$K$2:$K${n},1)'])
    summ.append([])
    summ.append(["Sessions, views, key events and revenue are summed from the daily export without the crawler row. Users are "
                 "GA4's monthly unique users (daily users count the same person again every day), less the crawler's users in April."])
    return {
        "Summary": {"header": ["Month", "Sessions", "Users", "Views", "Key events", "Revenue", "Key events per session"], "rows": summ,
                    "widths": {"A": 26, "C": 14, "G": 22}},
        "Daily": {"header": ["date", "month", "channel", "sessions", "engaged_sessions", "users", "new_users", "views", "key_events",
                             "revenue", "crawler"], "rows": daily, "widths": {"C": 16}},
        "Users": {"header": ["month", "total_users", "new_users", "crawler_users"], "rows": monthly_rows},
    }


def memo_text(d: dict) -> str:
    a, cr = d["agg"], d["crawler"]
    day = d["crawl_day"]
    dayname = f"{day.strftime('%A')} {day.day} April 2026"
    return f"""# Website traffic, March to May 2026

Sessions were {a['2026-03']['s']:,} in March, {a['2026-04']['s']:,} in April and {a['2026-05']['s']:,} in May,
{d['total_sessions']:,} for the three months. May had {d['monthly']['2026-05']['users']:,} users.

The crawler ran on {dayname}: {cr['s']:,} sessions that day were the SEO agency's bot, not visitors, and they are
taken out of April. Before that correction April showed {a['2026-04']['s_all']:,} sessions; the real figure is
{a['2026-04']['s']:,}.

The email spike on {d['sale_day'].day} April was the spring sale launch and is real traffic, so it stays in.

Users are GA4's monthly unique users. Adding up daily users would count a returning visitor once for every day they came back.
"""


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    rows, a, mo, cr = d["rows"], d["agg"], d["monthly"], d["crawler"]
    day = d["crawl_day"]

    # ---- workspace
    body = []
    for x in rows:
        er = f"{x['eng'] / x['s']:.4f}".rstrip("0").rstrip(".") if x["s"] else "0"
        body.append([x["date"].strftime("%Y%m%d"), x["ch"], x["s"], x["eng"], er, x["users"], x["new"], x["views"], x["ke"],
                     f"{x['rev']:.2f}".rstrip("0").rstrip(".") if x["rev"] else "0"])
    write_csv(os.path.join(ws, "ga4_traffic_acquisition_daily.csv"),
              ["Date", "Session default channel group", "Sessions", "Engaged sessions", "Engagement rate", "Total users", "New users",
               "Views", "Key events", "Total revenue"], body,
              preamble=["# ----------------------------------------", "# Traffic acquisition: Session default channel group",
                        "# Account: Saltmarsh Kayaks", "# Property: saltmarshkayaks.com - GA4", "# ----------------------------------------",
                        "#", f"# Start date: {START.strftime('%Y%m%d')}", f"# End date: {END.strftime('%Y%m%d')}"])
    write_csv(os.path.join(ws, "ga4_users_by_month.csv"), ["Month", "Total users", "New users", "Sessions"],
              [[m.replace("-", ""), mo[m]["users"], mo[m]["new"], mo[m]["sessions"]] for m in ["2026-02"] + MONTHS],
              preamble=["# ----------------------------------------", "# Exploration: users by month", "# Property: saltmarshkayaks.com - GA4",
                        "# ----------------------------------------"])
    r = rng(seed + 5)
    sc = []
    dd = date(2026, 3, 1)
    while dd <= END:
        clicks = int(round(BASE["Organic Search"] * season(dd) * r.uniform(0.62, 0.8)))
        impr = int(clicks * r.uniform(18, 30))
        sc.append([dd.isoformat(), clicks, impr, f"{clicks / impr:.2%}", f"{r.uniform(9.5, 14.5):.1f}"])
        dd += timedelta(days=1)
    write_csv(os.path.join(ws, "search_console_performance_2026-03-01_2026-05-31.csv"), ["Date", "Clicks", "Impressions", "CTR", "Position"], sc)
    write_text(os.path.join(ws, "note_from_tom.txt"),
               "Hi Leila,\n\n"
               "Before you send the spring numbers round, two things about the Google Analytics exports I dropped in the folder.\n\n"
               "1. Lindqvist Digital ran their site audit one day in April - a full crawl of every product page to find broken\n"
               "links. Their crawler runs a headless browser, and GA4 did not filter it, so it went in as real visits. You will\n"
               "see it: thousands of sessions in a single day, none of them engaged, nobody bought anything, and GA4 could not\n"
               "work out where they came from. Please take all of that traffic out and say in the memo which day it was, because\n"
               "Mira keeps asking why April looked so good. Do not confuse it with the spring sale email earlier in April - that\n"
               "spike was real customers.\n\n"
               "2. For users, use the monthly users export, not the daily one. GA4 counts a person once per day in the daily\n"
               "numbers, so adding them up counts a returning visitor over and over.\n\n"
               "The daily export is the standard last-100-days download, so it starts in February.\n\n"
               "Tom\n")

    # ---- reference
    write_csv(os.path.join(ref, "monthly_summary.csv"), ["month", "sessions", "users", "views", "key_events", "revenue"],
              [[m, a[m]["s"], d["users_clean"][m], a[m]["views"], a[m]["ke"], f"{a[m]['rev']:.2f}"] for m in MONTHS])
    write_json(os.path.join(ref, "notes.json"), {
        "crawl_day": day.isoformat(), "crawler_sessions": cr["s"], "crawler_users": cr["users"], "sale_email_day": d["sale_day"].isoformat(),
        "april_sessions_with_crawler": a["2026-04"]["s_all"], "may_daily_users_summed": a["2026-05"]["daily_users"],
        "february_sessions_in_export": a["2026-02"]["s_all"], "total_sessions_mar_may": d["total_sessions"]})

    # ---- reference solution
    daily = [[x["date"].isoformat(), f"{x['date'].year}-{x['date'].month:02d}", x["ch"], x["s"], x["eng"], x["users"], x["new"], x["views"],
              x["ke"], x["rev"], 1 if x["crawl"] else 0] for x in rows]
    monthly_rows = [[m, mo[m]["users"], mo[m]["new"], cr["users"] if m == "2026-04" else 0] for m in MONTHS]
    write_xlsx(os.path.join(sol, "traffic.xlsx"), report_workbook(daily, monthly_rows, day.isoformat()), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    dn = day.day
    day_re = (rf"(\b{dn}(st|nd|rd|th)?\s+(of\s+)?apr(il)?\b|\bapr(il)?\.?\s+{dn}(st|nd|rd|th)?\b|\b2026-04-{dn:02d}\b|"
              rf"\b0?4/{dn}(/(20)?26)?\b|\b{dn}/0?4(/(20)?26)?\b|\b202604{dn:02d}\b)")
    write_task_yaml(HERE, {
        "id": "web-traffic-summary", "track": "desk", "category": "reports",
        "title": "Spring website traffic by month, crawler taken out",
        "ask": ("Mira wants the website traffic for March, April and May as a monthly summary with a total for the three months. "
                "Save it as traffic.xlsx with live formulas, and put what she should know in memo.md. Tom's note explains the "
                "Google Analytics files.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the SEO agency's crawler ran on {day.isoformat()}: one Unassigned row that day carries {cr['s']:,} sessions with zero engaged "
            "sessions and no key events; Tom's note describes the crawler but not the day, so it has to be found and taken out of April "
            "(checks: April sessions, crawler removed; sessions, March to May)",
            "the memo has to name the crawl day and how much traffic was removed (checks: memo names the crawl day; memo carries the "
            "crawler sessions and corrected April sessions)",
            f"the spring-sale email on {d['sale_day'].isoformat()} is a genuine spike of engaged, converting sessions a few days before "
            "the crawl; removing it instead of (or as well as) the crawler moves April (check: April sessions, crawler removed)",
            "daily Total users cannot be added up - GA4 counts a returning visitor once per day - and Tom's note points to the "
            "monthly users export; summing the daily column overstates May by about 40% (check: May users)",
            "the daily export is GA4's last-100-days download starting 21 February, with an eight-line '#' comment preamble and "
            "YYYYMMDD dates; February rows are not spring (check: sessions, March to May)",
            "a Search Console clicks export sits in the folder; clicks are not sessions (check: sessions, March to May)",
        ],
        "checks": [
            {"type": "file_exists", "name": "traffic.xlsx exists", "path": "traffic.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "traffic.xlsx", "min_count": 6},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "traffic.xlsx"},
            {"type": "xlsx_value_present", "name": "April sessions, crawler removed", "path": "traffic.xlsx",
             "expected": a["2026-04"]["s"], "rel_tol": cent_tol(a["2026-04"]["s"], 0.005), "near_text": "sessions"},
            {"type": "xlsx_value_present", "name": "sessions, March to May", "path": "traffic.xlsx",
             "expected": d["total_sessions"], "rel_tol": cent_tol(d["total_sessions"], 0.005), "near_text": "sessions"},
            {"type": "xlsx_value_present", "name": "May users (monthly unique, not summed daily)", "path": "traffic.xlsx",
             "expected": mo["2026-05"]["users"], "rel_tol": cent_tol(mo["2026-05"]["users"], 0.005), "near_text": "users", "raw_value_ok": True},
            {"type": "text_sentence_matches", "name": "memo names the crawl day", "path": "memo.md",
             "all": [day_re, r"(crawl|\bbots?\b|spider|scrap|\bspike\b|headless|automated|non-human|not real|fake|audit)"]},
            {"type": "text_numbers_present", "name": "memo carries the crawler sessions and corrected April sessions", "path": "memo.md",
             "numbers": [cr["s"], a["2026-04"]["s"]], "rel_tol": 0.005},
        ],
    })
    print(f"seed={seed} rows={len(rows)} crawl={day} sale={d['sale_day']} crawler={cr['s']} agg={ {m: (a[m]['s'], a[m]['s_all']) for m in a} } "
          f"monthly={mo} total={d['total_sessions']}")


def write_naive(d: dict, out: str) -> None:
    """Every row by month including February and the crawler, users summed from the daily column."""
    os.makedirs(out, exist_ok=True)
    daily = [[x["date"].isoformat(), f"{x['date'].year}-{x['date'].month:02d}", x["ch"], x["s"], x["eng"], x["users"], x["new"], x["views"],
              x["ke"], x["rev"], 0] for x in d["rows"]]
    n = len(daily) + 1
    summ = []
    for i, m in enumerate(MONTHS, start=2):
        summ.append([m, f"=SUMIFS(Daily!$D$2:$D${n},Daily!$B$2:$B${n},$A{i})", f"=SUMIFS(Daily!$F$2:$F${n},Daily!$B$2:$B${n},$A{i})"])
    summ.append(["Total", f"=SUM(Daily!D2:D{n})", f"=SUM(Daily!F2:F{n})"])
    write_xlsx(os.path.join(out, "traffic.xlsx"), {"Summary": {"header": ["Month", "Sessions", "Users"], "rows": summ},
                                                   "Daily": {"header": ["date", "month", "channel", "sessions", "engaged", "users", "new_users",
                                                                        "views", "key_events", "revenue", "crawler"], "rows": daily}})
    write_text(os.path.join(out, "memo.md"), "# Spring traffic\n\nApril was our best month ever for sessions, with a big spike mid-month. "
               "Traffic grew steadily through the spring.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a_ = ap.parse_args()
    for attempt in range(500):
        d_ = build(a_.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a_.seed * 1000 + attempt, a_.naive)
