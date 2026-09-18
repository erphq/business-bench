#!/usr/bin/env python3
"""complaints-summary: a courier's complaint log plus web-form export -> complaints by category and month, with a memo.

    python gen.py [--seed N] [--naive DIR]

Business: Dorsey Freight runs local deliveries and pickups. Customer service keeps a shared log with one row per
update on a ticket; web-form tickets are exported separately and then picked up in the log under the same ticket id.

Traps (each caught by a check, see task.yaml):
  * the log has one row per update (new, escalated, resolved) and a few pasted duplicates; a ticket counts once
                                                                    (checks: complaints in the half; worst month total; memo names the worst month)
  * web-form tickets are in a separate export with reason codes and also appear in the log under the same id
                                                                    (check: complaints in the half)
  * categories are free text and codes; the ops note maps every spelling to six reporting categories, and
    compliments and questions are logged but are not complaints     (checks: complaints in the half; Damaged goods total)
  * investigation recategorises tickets (a "late delivery" turns out to be a missed pickup); the latest entry's
    category wins                                                    (check: Missed pickup total)
  * a ticket belongs to the month it was opened, even when it is resolved the next month (check: worst month total)
  * the log mixes real dates with typed "3/31/2026" text dates      (check: worst month total)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CATS = ["Late delivery", "Missed pickup", "Damaged goods", "Driver conduct", "Billing", "Tracking & communication"]
SPELL = {
    "Late delivery": ["Late delivery", "late", "Delivery late", "LATE DELIVERY", "delayed shipment"],
    "Missed pickup": ["Missed pickup", "missed pick-up", "driver no-show", "Pickup missed"],
    "Damaged goods": ["Damaged", "damaged goods", "Broken item", "crushed carton"],
    "Driver conduct": ["Driver rude", "driver behaviour", "Unsafe driving", "Driver conduct"],
    "Billing": ["Billing error", "overcharged", "Invoice wrong", "billing"],
    "Tracking & communication": ["No tracking update", "no call back", "Tracking", "communication"],
    None: ["Compliment", "Thank you", "General question", "Quote request"],
}
CODES = {"Late delivery": "DLV-LATE", "Missed pickup": "PKP-MISS", "Damaged goods": "DMG-GOODS", "Driver conduct": "STF-DRV",
         "Billing": "BIL-ERR", "Tracking & communication": "CSR-COMM", None: "INQ-GEN"}
MONTHS = [1, 2, 3, 4, 5, 6]
MNAME = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June"}
AGENTS = ["Tasha", "Luis", "Priya", "Owen", "Mei"]
STATUSES = ["New", "In progress", "Escalated", "Resolved", "Closed"]
DAYS = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30}


def build(seed: int) -> dict:
    r = rng(seed)
    weights = {m: r.randint(30, 46) for m in MONTHS}
    storm = r.choice([2, 3])                     # the month with the escalation storm: many rows per ticket
    tickets = []
    tid = 400 + r.randint(0, 60)
    custs = [c[0] for c in COMPANIES]
    for m in MONTHS:
        n = weights[m]
        for _ in range(n + r.randint(3, 6)):     # a few non-complaints mixed in
            tid += r.randint(1, 3)
            opened = datetime(2026, m, r.randint(1, DAYS[m]), r.randint(7, 18), r.randint(0, 59))
            is_complaint = _ < n
            cat = r.choices(CATS, [26, 14, 18, 10, 14, 18])[0] if is_complaint else None
            final = cat
            if cat == "Late delivery" and r.random() < 0.3:
                final = "Missed pickup"
            elif cat == "Tracking & communication" and r.random() < 0.15:
                final = "Late delivery"
            web = r.random() < 0.35
            k = r.randint(2, 4) if m == storm else r.choice([1, 1, 2, 2, 3])
            if not is_complaint:
                k = 1
            tickets.append({"id": f"T-26-{tid:05d}", "opened": opened, "cat": cat, "final": final, "web": web, "k": k,
                            "cust": r.choice(custs)})
    tickets.sort(key=lambda t: t["opened"])
    tid = 400 + r.randint(0, 60)
    for t in tickets:                             # the helpdesk numbers tickets as they open
        tid += r.randint(1, 3)
        t["id"] = f"T-26-{tid:05d}"
    # month-end tickets whose updates spill into the next month
    for t in tickets:
        if t["opened"].day >= DAYS[t["opened"].month] - 2 and t["k"] == 1 and t["cat"]:
            t["k"] = 2
    entries = []                                  # log rows
    web_rows = []
    for t in tickets:
        when = t["opened"]
        rows = []
        if t["web"]:
            web_rows.append({"t": t, "when": when, "code": CODES[t["cat"]]})
            when = when + timedelta(hours=r.randint(2, 30))
        n_log = t["k"] if not t["web"] else (t["k"] - 1 if t["cat"] else 0)
        for j in range(n_log):
            last = j == n_log - 1
            cat = t["final"] if (last or (j > 0 and r.random() < 0.5)) else t["cat"]
            status = "New" if j == 0 and not t["web"] else ("Resolved" if last and n_log > 1 else r.choice(["In progress", "Escalated"]))
            rows.append({"t": t, "when": when, "cat": cat, "status": status})
            gap = r.randint(20, 80) if t["opened"].day >= DAYS[t["opened"].month] - 2 else r.randint(3, 60)
            when = when + timedelta(hours=gap)
        entries += rows
    # a few pasted duplicate rows
    for e in r.sample([e for e in entries if e["t"]["cat"]], 8):
        entries.append(dict(e))
    entries.sort(key=lambda e: (e["when"], e["t"]["id"]))
    web_rows.sort(key=lambda w: w["when"])
    comp = [t for t in tickets if t["cat"]]
    by_cm = {(c, m): 0 for c in CATS for m in MONTHS}
    for t in comp:
        by_cm[(t["final"], t["opened"].month)] += 1
    month_tot = {m: sum(by_cm[(c, m)] for c in CATS) for m in MONTHS}
    cat_tot = {c: sum(by_cm[(c, m)] for m in MONTHS) for c in CATS}
    total = len(comp)
    # naive readings
    rows_month = {m: 0 for m in MONTHS}
    for e in entries:
        if e["t"]["cat"] and e["when"].month in rows_month:
            rows_month[e["when"].month] += 1
    for w in web_rows:
        if w["t"]["cat"]:
            rows_month[w["when"].month] += 1
    first_cat = {c: sum(1 for t in comp if t["cat"] == c) for c in CATS}
    last_month = {m: 0 for m in MONTHS}
    for t in comp:
        lm = max([e["when"] for e in entries if e["t"] is t] + [t["opened"]]).month
        if lm in last_month:
            last_month[lm] += 1
    log_only = sum(1 for t in comp if any(e["t"] is t for e in entries))
    with_noncomplaints = len(tickets)
    return {"tickets": tickets, "entries": entries, "web_rows": web_rows, "by_cm": by_cm, "month_tot": month_tot, "cat_tot": cat_tot,
            "total": total, "storm": storm,
            "naive": {"rows_month": rows_month, "first_cat": first_cat, "last_month": last_month, "log_only": log_only,
                      "with_noncomplaints": with_noncomplaints, "row_total": sum(rows_month.values())}}


def worst(d: dict) -> int:
    return max(MONTHS, key=lambda m: d["month_tot"][m])


def acceptable(d: dict) -> bool:
    mt, n = d["month_tot"], d["naive"]
    w = worst(d)
    ordered = sorted(mt.values(), reverse=True)
    if ordered[0] - ordered[1] < 3:
        return False
    if w == 5:                       # "may" is also an English verb; a memo sentence check on it would pass on "this may be"
        return False
    if mt[w] in d["cat_tot"].values() or mt[w] == d["total"]:
        return False
    if max(MONTHS, key=lambda m: n["rows_month"][m]) == w:
        return False
    if n["last_month"][w] == mt[w]:
        return False
    if n["first_cat"]["Missed pickup"] == d["cat_tot"]["Missed pickup"]:
        return False
    # pinned values unique on their rows (months across + total)
    tot_row = [mt[m] for m in MONTHS]
    if tot_row.count(mt[w]) != 1 or d["total"] in tot_row:
        return False
    for c in ("Missed pickup", "Damaged goods"):
        row = [d["by_cm"][(c, m)] for m in MONTHS]
        if d["cat_tot"][c] in row:
            return False
    if len(set(d["cat_tot"].values())) != len(CATS):
        return False
    return True


def text_date(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}/{dt.year}"


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 3)
    log_rows = []
    for e in d["entries"]:
        t = e["t"]
        spelled = r.choice(SPELL[e["cat"]])
        when = e["when"]
        log_rows.append([text_date(when) if r.random() < 0.15 else datetime(when.year, when.month, when.day), t["id"],
                         "Web" if t["web"] else r.choice(["Phone", "Phone", "Email"]), t["cust"], spelled, e["status"], r.choice(AGENTS),
                         {"New": "logged", "In progress": "checking with dispatch", "Escalated": "escalated to ops lead",
                          "Resolved": "customer informed, closed"}[e["status"]] if r.random() < 0.7 else ""])
    write_xlsx(os.path.join(ws, "customer_complaints_log_2026.xlsx"), {"Log": {
        "merged_title": "Customer service log - one row per update", "header": ["Date", "Ticket", "Channel", "Customer", "Category", "Status", "Agent", "Notes"],
        "rows": log_rows, "widths": {"A": 12, "B": 13, "D": 28, "E": 22, "H": 30}}}, creator="Customer Service")
    write_csv(os.path.join(ws, "web_form_tickets_2026-01-01_2026-06-30.csv"), ["submitted_at", "ticket_id", "reason_code", "customer", "message_excerpt"],
              [[w["when"].strftime("%Y-%m-%dT%H:%M:%S"), w["t"]["id"], w["code"], w["t"]["cust"],
                "Thanks for the great service" if w["t"]["cat"] is None else r.choice(["Please call me back", "See attached photo", "Order ref in subject", "Second time this month"])]
               for w in d["web_rows"]], crlf=True)
    table = "\n".join(f"  {c}: {', '.join(SPELL[c])}; web code {CODES[c]}" for c in CATS)
    write_text(os.path.join(ws, "note_from_ops_manager.txt"),
               "Complaints report - how we count\n\n"
               "Board wants complaints by category and by month for January to June, and I want a short memo that says which month was "
               "worst and anything else that jumps out.\n\n"
               "The log has a row for every update on a ticket (new, in progress, escalated, resolved), so the same ticket id shows up "
               "several times - and people paste rows twice sometimes. Web-form tickets come in through the website export first and then "
               "get worked in the log under the same ticket id. Count each ticket once:\n"
               "  - in the month it was opened (its earliest entry in either file), even if it was resolved the next month\n"
               "  - under the category on its most recent entry - investigation often changes it\n\n"
               "Categories are typed by hand. These are the six we report and the spellings that belong to each:\n"
               f"{table}\n\n"
               f"Compliments, thank-yous, general questions and quote requests ({', '.join(SPELL[None])}; web code {CODES[None]}) get logged "
               "too. They are not complaints - leave them out.\n\n- Grace\n")
    bc, mt, ct = d["by_cm"], d["month_tot"], d["cat_tot"]
    w = worst(d)
    write_csv(os.path.join(ref, "complaints_by_category_month.csv"), ["category"] + [f"2026-{m:02d}" for m in MONTHS] + ["total"],
              [[c] + [bc[(c, m)] for m in MONTHS] + [ct[c]] for c in CATS] + [["TOTAL"] + [mt[m] for m in MONTHS] + [d["total"]]])
    write_json(os.path.join(ref, "notes.json"), {"worst_month": f"2026-{w:02d}", "worst_count": mt[w], "total": d["total"], "naive": d["naive"],
                                                  "tickets": len(d["tickets"]), "log_rows": len(d["entries"]), "web_rows": len(d["web_rows"])})
    tk = sorted([t for t in d["tickets"] if t["cat"]], key=lambda t: t["opened"])
    ntk = len(tk) + 1
    rows = []
    for i, c in enumerate(CATS, start=3):
        rows.append([c] + [f'=COUNTIFS(Tickets!$C$2:$C${ntk},$A{i},Tickets!$B$2:$B${ntk},{chr(66 + j)}$2)' for j in range(6)] + [f"=SUM(B{i}:G{i})"])
    last = 2 + len(CATS)
    rows.append(["Total"] + [f"=SUM({c}3:{c}{last})" for c in "BCDEFGH"])
    write_xlsx(os.path.join(sol, "complaints.xlsx"), {
        "Summary": {"merged_title": "Complaints by category and month, January-June 2026 (one per ticket)",
                    "header": ["Category"] + [f"2026-{m:02d}" for m in MONTHS] + ["Total"], "rows": rows, "widths": {"A": 26}},
        "Tickets": {"header": ["ticket_id", "month_opened", "category", "opened"],
                    "rows": [[t["id"], f"2026-{t['opened'].month:02d}", t["final"], t["opened"].date()] for t in tk], "widths": {"A": 13, "C": 24}}},
        creator="reference")
    second = sorted(MONTHS, key=lambda m: -mt[m])[1]
    top_cat = max(CATS, key=lambda c: ct[c])
    write_text(os.path.join(sol, "memo.md"),
               f"# Complaints, January to June 2026\n\n"
               f"We received {d['total']} complaints in the half, counting each ticket once.\n\n"
               f"{MNAME[w]} was the worst month, with {mt[w]} complaints; the next highest was {MNAME[second]} with {mt[second]}.\n\n"
               f"{top_cat} is the largest category at {ct[top_cat]} complaints. "
               + (f"Missed pickups come to {ct['Missed pickup']} once investigated tickets are counted under their final category.\n\n"
                  if top_cat != "Missed pickup" else
                  "That includes tickets first logged as late deliveries that turned out to be missed pickups.\n\n")
               + f"{MNAME[d['storm']]} looks busier in the raw log only because its tickets were escalated and updated many times; "
               "by ticket it is not the peak. Compliments and general questions are left out.\n")
    write_task_yaml(HERE, {
        "id": "complaints-summary", "track": "desk", "category": "reports",
        "title": "First-half complaints by category and month",
        "ask": ("Grace needs the first-half complaints broken down by category and month for the board, plus a short memo on what stands out. "
                "The log, the web-form export and her note on how to count are in the folder. Save them as complaints.xlsx and memo.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the log has one row per update and {len(d['entries'])} rows for far fewer tickets, plus eight pasted duplicate rows; counting "
            f"rows makes {MNAME[max(MONTHS, key=lambda m: d['naive']['rows_month'][m])]} look worst because its tickets were escalated repeatedly "
            "(checks: complaints in the half; worst month total; memo names the worst month)",
            "web-form tickets are in a separate CSV with reason codes and are also worked in the log under the same ticket id; some never "
            "reach the log (check: complaints in the half)",
            "categories are hand-typed spellings and web codes that the note maps to six categories; compliments, thank-yous, questions "
            "and quote requests are logged too and are not complaints (checks: complaints in the half; Damaged goods total)",
            "investigation recategorises tickets, mostly late deliveries that were really missed pickups; the most recent entry's "
            "category wins, so keeping the first row's category undercounts missed pickups (check: Missed pickup total)",
            "tickets opened in the last days of a month are resolved in the next; the month is the month opened, not the month of the "
            "latest update (check: worst month total)",
            "about one log date in seven is typed text like \"3/31/2026\" instead of a real date, and web timestamps are ISO with a T "
            "(check: worst month total)",
        ],
        "checks": [
            {"type": "file_exists", "name": "complaints.xlsx exists", "path": "complaints.xlsx"},
            {"type": "xlsx_no_errors", "name": "no formula errors", "path": "complaints.xlsx"},
            {"type": "xlsx_value_present", "name": "complaints in the half", "path": "complaints.xlsx", "expected": d["total"], "rel_tol": 0.001, "near_text": "total"},
            {"type": "xlsx_value_present", "name": "worst month total", "path": "complaints.xlsx", "expected": mt[w], "rel_tol": 0.001, "near_text": "total"},
            {"type": "xlsx_value_present", "name": "Missed pickup total", "path": "complaints.xlsx", "expected": ct["Missed pickup"], "rel_tol": 0.001, "near_text": "missed pickup"},
            {"type": "xlsx_value_present", "name": "Damaged goods total", "path": "complaints.xlsx", "expected": ct["Damaged goods"], "rel_tol": 0.001, "near_text": "damaged"},
            {"type": "text_numbers_present", "name": "memo states the half total and the worst month's count", "path": "memo.md",
             "numbers": [d["total"], mt[w]], "rel_tol": 0.001},
            {"type": "text_sentence_matches", "name": "memo names the worst month", "path": "memo.md",
             "all": [rf"(\b{MNAME[w].lower()}\b|\b2026-{w:02d}\b|\b{w:02d}/2026\b)",
                     r"(\bworst\b|\bmost\b|\bhighest\b|\bpeak\b|\bbusiest\b|\blargest\b|\bbiggest\b|\bmore complaints than\b|\btop month\b)"],
             "none": [r"\bnot (the |a )?(worst|highest|peak|busiest)\b"]},
        ],
    })
    print(f"seed={seed} tickets={len(d['tickets'])} complaints={d['total']} log_rows={len(d['entries'])} web={len(d['web_rows'])} "
          f"months={mt} worst={w} storm={d['storm']} cats={ct}")
    print("naive:", d["naive"])


def write_naive(d: dict, out: str) -> None:
    """The obvious pivot: every log row is a complaint, category as typed, month of the row date (text dates dropped),
    web export ignored."""
    os.makedirs(out, exist_ok=True)
    r = rng(3)
    piv = {}
    for e in d["entries"]:
        c = r.choice(SPELL[e["cat"]])
        if e["when"].month in MONTHS:
            piv.setdefault(c, {m: 0 for m in MONTHS})[e["when"].month] += 1
    rows = [[c] + [v[m] for m in MONTHS] + [sum(v.values())] for c, v in sorted(piv.items())]
    rows.append(["Total"] + [sum(v[m] for v in piv.values()) for m in MONTHS] + [sum(sum(v.values()) for v in piv.values())])
    write_xlsx(os.path.join(out, "complaints.xlsx"), {"Pivot": {"header": ["Category"] + [MNAME[m] for m in MONTHS] + ["Total"], "rows": rows}}, creator="naive")
    mt = {m: sum(v[m] for v in piv.values()) for m in MONTHS}
    wm = max(MONTHS, key=lambda m: mt[m])
    write_text(os.path.join(out, "memo.md"), f"# Complaints\n\n{MNAME[wm]} was the worst month with {mt[wm]} complaints logged.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(3000):
        d_ = build(a.seed * 10000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 10000 + attempt, a.naive)
