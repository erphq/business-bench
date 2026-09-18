#!/usr/bin/env python3
"""weekly-kpi-dashboard: an optician's five small system exports to a one-page weekly KPI workbook.

    python gen.py [--seed N]

Business: Glassworks Optical, a mall optician with its own glazing lab and a web store for contacts and sunglasses. The owner wants one page
with the last six full weeks side by side before the Tuesday staff meeting. Every system exports its own way
and on its own date range.

Traps (each caught by a check, see task.yaml):
  * the scheduling export carries a "Pay week (Sun-Sat)" column; the dashboard weeks run Monday to Sunday, so
    grouping on that column moves every Sunday into the wrong week   (checks: staff hours week of 17 Aug; sales per staff hour)
  * every export starts and ends mid-week; only the six full weeks 3 Aug - 13 Sep count (check: total sales six weeks)
  * the web store export carries refunded, voided and pending orders; only paid orders are sales
                                                                     (check: online sales week of 24 Aug)
  * web timestamps carry a -0700 offset; converting to UTC pushes late-Sunday orders into Monday's week
                                                                     (check: online sales week of 24 Aug)
  * glasses jobs count in the week the lab finished them, not the week they were ordered, and jobs still
    waiting on lenses are not finished                               (check: glasses jobs finished week of 7 Sep)
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

WEEKS = [date(2026, 8, 3) + timedelta(days=7 * i) for i in range(6)]       # Mondays
W_START, W_END = WEEKS[0], WEEKS[-1] + timedelta(days=6)                   # 3 Aug .. 13 Sep
STAFF = ["Kwame Osei", "Leila Mensah", "Mateo Ruiz", "Yuki Tanaka", "Dmitri Petrov", "Amara Cole", "Jonah Reed",
         "Sofia Castillo", "Omar Haddad", "Ingrid Lindqvist", "Marcus Bennett"]
JOB_TYPES = [("Single vision", 89), ("Progressive", 240), ("Bifocal", 160), ("Lens replacement", 120),
             ("Frame repair", 25), ("Prescription sunglasses", 180), ("Blue-light upgrade", 65)]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def sunday_start(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def days(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def week_label(m: date) -> str:
    """A text key that no spreadsheet engine reads as a date inside SUMIFS criteria."""
    return f"Week of {m.day} {m.strftime('%b')}"


def build(seed: int) -> dict:
    r = rng(seed)
    # ---- POS: open Tuesday to Sunday ----
    pos = []
    for d in days(date(2026, 7, 29), date(2026, 9, 14)):
        if d.weekday() == 0:
            pos.append({"date": d, "gross": 0.0, "disc": 0.0, "ret": 0.0, "net": 0.0, "txns": 0, "closed": True})
            continue
        base = {5: 5200, 6: 3900}.get(d.weekday(), 2900) * r.uniform(0.7, 1.3)
        disc = round(base * r.uniform(0.01, 0.05), 2)
        ret = round(base * r.uniform(0, 0.06), 2) if r.random() < 0.5 else 0.0
        gross = round(base, 2)
        pos.append({"date": d, "gross": gross, "disc": disc, "ret": ret, "net": round(gross - disc - ret, 2),
                    "txns": int(base / r.uniform(70, 110)), "closed": False})

    # ---- web orders ----
    web = []
    num = 20410
    for d in days(date(2026, 7, 30), date(2026, 9, 15)):
        for _ in range(r.randint(3, 9)):
            num += 1
            t = datetime(d.year, d.month, d.day, r.randint(6, 23), r.randint(0, 59), r.randint(0, 59))
            status = r.choices(["paid", "refunded", "voided", "pending"], weights=[86, 6, 4, 4])[0]
            web.append({"num": f"#{num}", "ts": t, "status": status, "total": round(r.choice([32, 45, 58, 79, 118, 149, 189, 245, 329, 410])
                                                                                    * r.uniform(0.95, 1.05), 2)})
    # a paid late-Sunday order on the last day of the checked week, and a refunded order inside it
    num += 1
    web.append({"num": f"#{num}", "ts": datetime(2026, 8, 30, 22, 41, 7), "status": "paid", "total": 389.50})
    num += 1
    web.append({"num": f"#{num}", "ts": datetime(2026, 8, 26, 12, 5, 51), "status": "refunded", "total": 412.00})
    web.sort(key=lambda o: o["ts"])
    for i, o in enumerate(web):          # the store numbers orders in the order they arrive
        o["num"] = f"#{20411 + i}"

    # ---- lab jobs ----
    tickets = []
    tnum = 7700
    for d in days(date(2026, 7, 14), date(2026, 9, 14)):
        if d.weekday() == 0:
            continue
        for _ in range(r.randint(2, 6)):
            tnum += 1
            kind, price = r.choice(JOB_TYPES)
            wait = r.choices([0, 1, 2, 3, 5, 8, 12], weights=[10, 20, 20, 15, 12, 8, 5])[0]
            done = d + timedelta(days=wait)
            if done.weekday() == 0:
                done += timedelta(days=1)
            parts = r.random() < 0.08
            if parts or done > date(2026, 9, 14):
                status, done = ("Waiting on lenses" if parts else "In lab"), None
            else:
                status = r.choice(["Ready for pickup", "Picked up"])
            tickets.append({"num": f"J-{tnum}", "opened": d, "done": done, "status": status, "kind": kind,
                            "labor": round(price * r.uniform(0.9, 1.2), 2)})

    # ---- staff shifts ----
    shifts = []
    for d in days(date(2026, 7, 26), date(2026, 9, 19)):
        if d.weekday() == 0:
            if r.random() < 0.35:     # Monday stock-take
                shifts.append({"date": d, "who": r.choice(STAFF[:3]), "hours": r.choice([4.0, 5.0, 6.0])})
            continue
        n = {5: 9, 6: r.choice([4, 4, 5, 8, 9])}.get(d.weekday(), 6)       # Sunday staffing swings with trunk shows
        for who in r.sample(STAFF, min(n, len(STAFF))):
            shifts.append({"date": d, "who": who, "hours": r.choice([6.0, 7.5, 8.0, 8.0, 9.0, 5.5])})

    # ---- newsletter signups ----
    signups = []
    for d in days(date(2026, 8, 1), date(2026, 9, 15)):
        for _ in range(r.randint(0, 6)):
            f, l = person(r)
            signups.append({"ts": datetime(d.year, d.month, d.day, r.randint(0, 23), r.randint(0, 59)),
                            "email": email_for(r, f, l), "source": r.choice(["Checkout", "Footer form", "In-store tablet", "Eye exam booking"]),
                            "status": r.choices(["subscribed", "unsubscribed", "cleaned"], weights=[90, 7, 3])[0]})
    signups.sort(key=lambda s: s["ts"])

    # ---- truth ----
    k = {w: {"store": 0.0, "online": 0.0, "orders": 0, "repairs": 0, "hours": 0.0, "subs": 0} for w in WEEKS}
    naive = {w: {"hours_sun": 0.0, "repairs_opened": 0, "online_all": 0.0, "online_utc": 0.0} for w in WEEKS}
    for p in pos:
        if W_START <= p["date"] <= W_END:
            k[monday(p["date"])]["store"] += p["net"]
    for o in web:
        d = o["ts"].date()
        if o["status"] == "paid" and W_START <= d <= W_END:
            k[monday(d)]["online"] += o["total"]; k[monday(d)]["orders"] += 1
        if W_START <= d <= W_END:
            naive[monday(d)]["online_all"] += o["total"]
        du = (o["ts"] + timedelta(hours=7)).date()
        if o["status"] == "paid" and W_START <= du <= W_END:
            naive[monday(du)]["online_utc"] += o["total"]
    for t in tickets:
        if t["done"] and W_START <= t["done"] <= W_END:
            k[monday(t["done"])]["repairs"] += 1
        if W_START <= t["opened"] <= W_END:
            naive[monday(t["opened"])]["repairs_opened"] += 1
    for s in shifts:
        if W_START <= s["date"] <= W_END:
            k[monday(s["date"])]["hours"] += s["hours"]
        ss = sunday_start(s["date"]) + timedelta(days=1)       # the Monday a pay-week label gets mistaken for
        if ss in naive:
            naive[ss]["hours_sun"] += s["hours"]
    for sgn in signups:
        d = sgn["ts"].date()
        if sgn["status"] == "subscribed" and W_START <= d <= W_END:
            k[monday(d)]["subs"] += 1
    for w in WEEKS:
        x = k[w]
        x["store"] = round(x["store"], 2); x["online"] = round(x["online"], 2)
        x["total"] = round(x["store"] + x["online"], 2)
        x["per_hour"] = round(x["total"] / x["hours"], 2)
        naive[w]["per_hour_sun"] = round(x["total"] / naive[w]["hours_sun"], 2) if naive[w]["hours_sun"] else 0
    six = {"store": round(sum(k[w]["store"] for w in WEEKS), 2), "online": round(sum(k[w]["online"] for w in WEEKS), 2),
           "hours": sum(k[w]["hours"] for w in WEEKS), "repairs": sum(k[w]["repairs"] for w in WEEKS),
           "orders": sum(k[w]["orders"] for w in WEEKS), "subs": sum(k[w]["subs"] for w in WEEKS)}
    six["total"] = round(six["store"] + six["online"], 2)
    six["per_hour"] = round(six["total"] / six["hours"], 2)
    return {"pos": pos, "web": web, "tickets": tickets, "shifts": shifts, "signups": signups, "k": k, "naive": naive, "six": six}


def acceptable(d: dict) -> bool:
    k, nv = d["k"], d["naive"]
    w3, w4, w6 = WEEKS[2], WEEKS[3], WEEKS[5]
    if abs(k[w3]["hours"] - nv[w3]["hours_sun"]) < max(8, 0.03 * k[w3]["hours"]):
        return False
    if abs(k[w3]["per_hour"] - nv[w3]["per_hour_sun"]) < 0.03 * k[w3]["per_hour"]:
        return False
    if abs(k[w4]["online"] - nv[w4]["online_utc"]) < 0.03 * k[w4]["online"] or abs(k[w4]["online"] - nv[w4]["online_all"]) < 0.03 * k[w4]["online"]:
        return False
    if k[w6]["repairs"] == nv[w6]["repairs_opened"]:
        return False

    def unique(v, others, rel):
        return all(abs(v - o) > max(abs(v) * rel, 0.5) for o in others)
    # staff hours and sales per staff hour live in clearly different ranges, naive readings included
    hours_all = [k[w]["hours"] for w in WEEKS] + [nv[w]["hours_sun"] for w in WEEKS]
    rate_all = [k[w]["per_hour"] for w in WEEKS] + [nv[w]["per_hour_sun"] for w in WEEKS] + [d["six"]["per_hour"]]
    if min(hours_all) < 1.4 * max(rate_all):
        return False
    # no naive reading of any week lands on a checked figure
    if not unique(k[w3]["hours"], [nv[w]["hours_sun"] for w in WEEKS], 0.01) or \
            not unique(k[w3]["per_hour"], [nv[w]["per_hour_sun"] for w in WEEKS], 0.01) or \
            not unique(k[w4]["online"], [nv[w][x] for w in WEEKS for x in ("online_all", "online_utc")], 0.01) or \
            k[w6]["repairs"] in [nv[w]["repairs_opened"] for w in WEEKS]:
        return False
    for key, w, rel in (("hours", w3, 0.01), ("per_hour", w3, 0.01), ("online", w4, 0.01), ("repairs", w6, 0.0)):
        row = [k[x][key] for x in WEEKS if x != w] + [d["six"][key]]
        if not unique(k[w][key], row, rel):
            return False
    # the checked week's hours and sales per hour must not collide with any other KPI in its column
    col = [k[w3][x] for x in ("store", "online", "orders", "repairs", "total", "subs")]
    if not unique(k[w3]["hours"], col + [k[w3]["per_hour"]], 0.01) or not unique(k[w3]["per_hour"], col, 0.01):
        return False
    six = [d["six"][x] for x in ("store", "online", "hours", "repairs", "orders", "subs", "per_hour")]
    return unique(d["six"]["total"], six + [k[w]["total"] for w in WEEKS], 0.01)


# --------------------------------------------------------------------------- deliverables

def kpi_sheets(d: dict) -> dict:
    wk = lambda x: week_label(monday(x))
    pos = [[p["date"].isoformat(), wk(p["date"]), p["net"]] for p in d["pos"] if W_START <= p["date"] <= W_END]
    web = [[o["num"], o["ts"].date().isoformat(), wk(o["ts"].date()), o["total"], o["status"]] for o in d["web"]
           if W_START <= o["ts"].date() <= W_END]
    rep = [[t["num"], t["done"].isoformat(), wk(t["done"]), 1] for t in d["tickets"] if t["done"] and W_START <= t["done"] <= W_END]
    hrs = [[s["date"].isoformat(), wk(s["date"]), s["who"], s["hours"]] for s in d["shifts"] if W_START <= s["date"] <= W_END]
    sub = [[s["ts"].date().isoformat(), wk(s["ts"].date()), 1] for s in d["signups"]
           if s["status"] == "subscribed" and W_START <= s["ts"].date() <= W_END]
    n = {k_: len(v) + 1 for k_, v in (("pos", pos), ("web", web), ("rep", rep), ("hrs", hrs), ("sub", sub))}
    cols = "BCDEFG"
    lines = [
        ("Store net sales", lambda c: f"=ROUND(SUMIFS(POS!$C$2:$C${n['pos']},POS!$B$2:$B${n['pos']},{c}$2),2)"),
        ("Online sales (paid orders)", lambda c: f'=ROUND(SUMIFS(Web!$D$2:$D${n["web"]},Web!$C$2:$C${n["web"]},{c}$2,Web!$E$2:$E${n["web"]},"paid"),2)'),
        ("Total sales", lambda c: f"={c}3+{c}4"),
        ("Online orders", lambda c: f'=COUNTIFS(Web!$C$2:$C${n["web"]},{c}$2,Web!$E$2:$E${n["web"]},"paid")'),
        ("Glasses jobs finished", lambda c: f"=COUNTIF(Jobs!$C$2:$C${n['rep']},{c}$2)"),
        ("Staff hours", lambda c: f"=SUMIFS(Staff!$D$2:$D${n['hrs']},Staff!$B$2:$B${n['hrs']},{c}$2)"),
        ("Sales per staff hour", lambda c: f"=IF({c}8=0,0,ROUND({c}5/{c}8,2))"),
        ("New subscribers", lambda c: f"=COUNTIF(Signups!$B$2:$B${n['sub']},{c}$2)"),
    ]
    rows = [["Week (Mon-Sun)"] + [week_label(w) for w in WEEKS] + ["6 weeks"]]
    for i, (label, f) in enumerate(lines, start=3):
        tail = "=IF(H8=0,0,ROUND(H5/H8,2))" if label == "Sales per staff hour" else (
            "=H3+H4" if label == "Total sales" else f"=SUM(B{i}:G{i})")
        rows.append([label] + [f(c) for c in cols] + [tail])
    rows.append([])
    rows.append(["Weeks run Monday to Sunday, 3 Aug to 13 Sep 2026. Online sales are paid orders only; glasses jobs count in the week "
                 "the lab finished them; staff hours are regrouped from shift dates, not the pay-week column."])
    return {
        "KPIs": {"merged_title": "Glassworks Optical - weekly KPIs", "header": None, "rows": rows, "widths": {"A": 28}},
        "POS": {"header": ["date", "week", "net sales"], "rows": pos},
        "Web": {"header": ["order", "date", "week", "total", "status"], "rows": web},
        "Jobs": {"header": ["job", "finished", "week", "count"], "rows": rep},
        "Staff": {"header": ["date", "week", "employee", "hours"], "rows": hrs},
        "Signups": {"header": ["date", "week", "count"], "rows": sub},
    }



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
    k, six = d["k"], d["six"]

    # ---- workspace ----
    write_csv(os.path.join(ws, "pos_end_of_day_report.csv"),
              ["Business Date", "Gross Sales", "Discounts", "Returns", "Net Sales", "Transactions"],
              [[p["date"].strftime("%a %m/%d/%Y"), "CLOSED" if p["closed"] else money_str(p["gross"], 1),
                "" if p["closed"] else money_str(p["disc"], 1), "" if p["closed"] else money_str(p["ret"], 1),
                "" if p["closed"] else money_str(p["net"], 1), "" if p["closed"] else p["txns"]] for p in d["pos"]],
              preamble=["Glassworks Optical - End of Day Summary", "Location: Westgate Mall"])
    write_csv(os.path.join(ws, "webstore_orders.csv"),
              ["Name", "Created at", "Financial Status", "Total", "Currency"],
              [[o["num"], o["ts"].strftime("%Y-%m-%d %H:%M:%S -0700"), o["status"], f"{o['total']:.2f}", "USD"] for o in d["web"]])
    write_csv(os.path.join(ws, "lab_jobs.csv"),
              ["Job", "Ordered", "Type", "Status", "Finished", "Lab charge"],
              [[t["num"], t["opened"].strftime("%m/%d/%Y"), t["kind"], t["status"], t["done"].strftime("%m/%d/%Y") if t["done"] else "",
                f"{t['labor']:.2f}"] for t in d["tickets"]])
    write_csv(os.path.join(ws, "schedule_hours_export.csv"),
              ["Pay week (Sun-Sat)", "Shift date", "Employee", "Hours"],
              [[sunday_start(s["date"]).isoformat(), s["date"].isoformat(), s["who"], f"{s['hours']:.2f}"] for s in d["shifts"]],
              bom=True, crlf=True)
    write_csv(os.path.join(ws, "newsletter_audience.csv"),
              ["Email Address", "Source", "Status", "Optin Time"],
              [[s["email"], s["source"], s["status"], s["ts"].strftime("%Y-%m-%d %H:%M")] for s in d["signups"]])
    write_text(os.path.join(ws, "note_from_kwame.txt"),
               "For Tuesday's staff meeting I want one page with the last six full weeks side by side, oldest on the left:\n"
               "store sales (net, from the till report), online sales, total sales, online orders, glasses jobs finished,\n"
               "staff hours, sales per staff hour (total sales divided by staff hours) and new newsletter subscribers.\n\n"
               "Our weeks run Monday to Sunday - that is how the till and the meeting think about it.\n"
               "Online only counts orders that were actually paid. A glasses job counts in the week the lab finished it.\n"
               "New subscribers are people still subscribed.\n\n"
               "Kwame\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "kpis_by_week.csv"),
              ["week_start", "store_net_sales", "online_sales", "total_sales", "online_orders", "glasses_jobs_finished", "staff_hours",
               "sales_per_staff_hour", "new_subscribers"],
              [[w.isoformat(), f"{k[w]['store']:.2f}", f"{k[w]['online']:.2f}", f"{k[w]['total']:.2f}", k[w]["orders"], k[w]["repairs"],
                f"{k[w]['hours']:.2f}", f"{k[w]['per_hour']:.2f}", k[w]["subs"]] for w in WEEKS])
    write_json(os.path.join(ref, "notes.json"), {"six_weeks": six, "naive": {w.isoformat(): v for w, v in d["naive"].items()}})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "kpi.xlsx"), kpi_sheets(d), creator="reference")

    w3, w4, w6 = WEEKS[2], WEEKS[3], WEEKS[5]
    write_task_yaml(HERE, cent_tolerant({
        "id": "weekly-kpi-dashboard", "track": "desk", "category": "reports",
        "title": "One-page weekly KPIs from five system exports",
        "ask": ("Kwame wants a one-page weekly KPI sheet for the staff meeting built from the five exports in this folder. "
                "Save it as kpi.xlsx with live formulas; his note lists what goes on it.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the scheduling export groups shifts under 'Pay week (Sun-Sat)' while the dashboard weeks run Monday to Sunday; "
            f"grouping on that column puts each Sunday in the following week, so the week of {w3.isoformat()} carries the "
            "wrong Sunday (checks: staff hours week of 17 Aug; sales per staff hour week of 17 Aug)",
            "every export starts and stops mid-week (till report from Wednesday 29 Jul, web orders to 15 Sep, shifts from "
            "26 Jul, lab jobs ordered from mid-July); only the six full weeks 3 Aug - 13 Sep belong on the page "
            "(check: total sales, six weeks)",
            "the web store export carries refunded, voided and pending orders that are not sales, including a large "
            "refunded order on 26 Aug (check: online sales week of 24 Aug)",
            "web timestamps carry a -0700 offset; converting them to UTC moves a paid 22:41 order on Sunday 30 Aug into "
            "the next week (check: online sales week of 24 Aug)",
            "glasses jobs count in the week the lab finished them, not the week they were ordered, and jobs waiting on "
            "lenses or still in the lab have no finish date (check: glasses jobs finished week of 7 Sep)",
            "the till report shows Mondays as CLOSED text rows and carries a two-line preamble; the scheduling export has "
            "a BOM and CRLF endings (check: total sales, six weeks)",
        ],
        "checks": [
            {"type": "file_exists", "name": "kpi.xlsx exists", "path": "kpi.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "kpi.xlsx", "min_count": 24},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "kpi.xlsx"},
            {"type": "xlsx_value_present", "name": "staff hours week of 17 Aug (Monday weeks)", "path": "kpi.xlsx",
             "expected": k[w3]["hours"], "rel_tol": 0.003, "near_text": "hour"},
            {"type": "xlsx_value_present", "name": "sales per staff hour week of 17 Aug", "path": "kpi.xlsx",
             "expected": k[w3]["per_hour"], "rel_tol": 0.005, "near_text": "hour"},
            {"type": "xlsx_value_present", "name": "online sales week of 24 Aug (paid only)", "path": "kpi.xlsx",
             "expected": k[w4]["online"], "rel_tol": 0.005, "near_text": "online"},
            {"type": "xlsx_value_present", "name": "glasses jobs finished week of 7 Sep", "path": "kpi.xlsx",
             "expected": k[w6]["repairs"], "rel_tol": 0.0, "near_text": "job"},
            {"type": "xlsx_value_present", "name": "total sales, six weeks", "path": "kpi.xlsx",
             "expected": six["total"], "rel_tol": 0.003, "near_text": "total"},
        ],
    }))
    print(f"seed={seed} pos={len(d['pos'])} web={len(d['web'])} tickets={len(d['tickets'])} shifts={len(d['shifts'])} signups={len(d['signups'])}")
    for w in WEEKS:
        print("  ", w, k[w], d["naive"][w])
    print("  six:", six)


if __name__ == "__main__":
    s = argparse_seed()
    for attempt in range(800):
        if acceptable(build(s * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 800 attempts")
    emit(s * 1000 + attempt)
