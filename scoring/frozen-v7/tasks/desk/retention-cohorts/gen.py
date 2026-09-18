#!/usr/bin/env python3
"""retention-cohorts: web-shop orders to a monthly cohort retention table (customers, not orders).

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * the cohort is the month of a customer's FIRST EVER order; the folder also holds last year's export
    (different column names) and customers who bought in 2025 are not new in 2026     (check: January new customers)
  * fully refunded orders (Refunded equals Total) and Cancelled orders do not count as orders; a partial
    refund still counts; a customer whose only January order was refunded is not a January customer
                                                                                         (checks: January and February new customers)
  * the same customer's email varies in case and whitespace across orders                 (check: total new customers)
  * a customer with three orders in a month is active once that month; counting orders inflates
    the later-month cells                                                                (check: January cohort month 1)
  * the summary must be live formulas over the cleaned data                              (check: live formulas)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COHORTS = [f"2026-{m:02d}" for m in range(1, 7)]
OLD_MONTHS = [f"2025-{m:02d}" for m in range(7, 13)]
OFFSETS = ["Month 1", "Month 2", "Month 3", "Month 4", "Month 5"]
ITEMS = [("Ethiopia Guji 12oz", 18.0), ("Colombia Huila 12oz", 17.0), ("House Espresso 2lb", 42.0), ("Decaf Peru 12oz", 17.5),
         ("Subscription box", 34.0), ("Pour-over kit", 56.0), ("Cold brew pack", 24.0), ("Gift card", 50.0)]

def _mk(d: date) -> str: return f"{d.year}-{d.month:02d}"
def _month_days(mk: str) -> int:
    y, m = int(mk[:4]), int(mk[5:]); return [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
def _offset(cohort: str, mk: str) -> int:
    return (int(mk[:4]) - int(cohort[:4])) * 12 + int(mk[5:]) - int(cohort[5:])

def build(seed: int) -> dict:
    for attempt in range(400):
        r = rng(seed * 1000 + attempt)
        d = _draw(r)
        if _acceptable(d): return d
    raise SystemExit("no acceptable draw")

def _draw(r) -> dict:
    ppl = people(r, 240)
    customers = []
    for i, (f, l) in enumerate(ppl):
        customers.append({"cid": i, "name": f"{f} {l}", "email": email_for(r, f, l), "orders": []})
    old_cust = customers[:70]; new_cust = customers[70:]
    orders = []  # dict: date, cust, total, refunded, status, kind
    def add_order(c, mk, kind="ok"):
        y, m = int(mk[:4]), int(mk[5:])
        dt = datetime(y, m, r.randint(1, _month_days(mk)), r.randint(6, 22), r.randint(0, 59))
        n_items = r.choice([1, 1, 1, 2, 2, 3])
        total = round(sum(r.choice(ITEMS)[1] for _ in range(n_items)) + r.choice([0, 0, 5.0, 7.5]), 2)
        o = {"date": dt, "cust": c, "total": total, "refunded": 0.0, "status": "Fulfilled", "kind": kind}
        if kind == "refund": o["refunded"] = total; o["status"] = "Refunded"
        elif kind == "partial": o["refunded"] = round(r.choice([0.25, 0.5]) * total, 2); o["status"] = "Partially refunded"
        elif kind == "cancel": o["status"] = "Cancelled"
        else: o["status"] = r.choice(["Fulfilled", "Fulfilled", "Fulfilled", "Delivered", "Paid"])
        orders.append(o); c["orders"].append(o); return o
    # old customers: orders in 2025, ~40% come back in 2026 (they are NOT new)
    for c in old_cust:
        first = r.choice(OLD_MONTHS)
        add_order(c, first)
        for mk in OLD_MONTHS[OLD_MONTHS.index(first) + 1:]:
            if r.random() < 0.3: add_order(c, mk)
        if r.random() < 0.45:
            for mk in COHORTS:
                if r.random() < 0.35: add_order(c, mk)
    # new customers: first order in 2026, decaying retention
    weights = [1.3, 1.0, 1.1, 0.9, 1.0, 0.8]
    for c in new_cust:
        first = r.choices(COHORTS, weights)[0]
        add_order(c, first)
        if r.random() < 0.35: add_order(c, first)             # second order same month
        p = 0.45
        for mk in COHORTS[COHORTS.index(first) + 1:]:
            if r.random() < p:
                add_order(c, mk)
                if r.random() < 0.3: add_order(c, mk)         # multiple orders in the active month
                if r.random() < 0.15: add_order(c, mk)
            p = max(0.18, p - 0.06)
    # refund / cancel traps on new customers
    firsts = [c for c in new_cust if c["orders"][0]["date"].year == 2026]
    r.shuffle(firsts)
    shifted = firsts[:8]         # first order fully refunded (cohort shifts to the next counted order or vanishes)
    for c in shifted:
        c["orders"][0]["kind"] = "refund"; c["orders"][0]["refunded"] = c["orders"][0]["total"]; c["orders"][0]["status"] = "Refunded"
    for c in firsts[8:14]:       # a later-month order refunded: retention cell changes
        later = [o for o in c["orders"] if _mk(o["date"].date()) != _mk(c["orders"][0]["date"].date())]
        if later:
            o = r.choice(later); o["kind"] = "refund"; o["refunded"] = o["total"]; o["status"] = "Refunded"
    for c in firsts[14:19]:      # cancelled first order
        c["orders"][0]["kind"] = "cancel"; c["orders"][0]["status"] = "Cancelled"
    for c in firsts[19:31]:      # partial refunds still count
        o = r.choice(c["orders"]); o["kind"] = "partial"; o["refunded"] = round(r.choice([0.25, 0.5]) * o["total"], 2); o["status"] = "Partially refunded"
    orders.sort(key=lambda o: o["date"])
    for i, o in enumerate(orders):
        o["num"] = 10400 + i
        e = o["cust"]["email"]
        o["email_shown"] = email_case_noise(r, e) if r.random() < 0.3 else e
    # ---- truth
    def counted(o): return o["status"] not in ("Cancelled",) and not (o["refunded"] >= o["total"] - 1e-9)
    truth_cohort = {}; activity = {}   # cid -> cohort ; cid -> set(months)
    for c in customers:
        cm = sorted({_mk(o["date"].date()) for o in c["orders"] if counted(o)})
        if not cm or cm[0] < "2026-01": continue
        truth_cohort[c["cid"]] = cm[0]; activity[c["cid"]] = set(cm)
    table = {}
    for cid, co in truth_cohort.items():
        table.setdefault(co, {"new": 0, **{k: 0 for k in range(1, 6)}})["new"] += 1
        for mk in activity[cid]:
            k = _offset(co, mk)
            if 1 <= k <= 5: table[co][k] += 1
    for co in COHORTS: table.setdefault(co, {"new": 0, **{k: 0 for k in range(1, 6)}})
    # ---- naive variants
    def variant(count_orders=False, keep_refunds=False, raw_email=False, ignore_2025=False):
        groups = {}
        for o in orders:
            if o["date"].year < 2026 and ignore_2025: continue
            ok = True if keep_refunds else counted(o)
            if not ok: continue
            key = o["email_shown"] if raw_email else o["cust"]["cid"]
            groups.setdefault(key, []).append(o)
        t = {co: {"new": 0, **{k: 0 for k in range(1, 6)}} for co in COHORTS}
        for key, os_ in groups.items():
            ms = sorted(_mk(o["date"].date()) for o in os_)
            if ms[0] < "2026-01": continue
            co = ms[0]; t[co]["new"] += 1
            seen = set()
            for mk in ms:
                k = _offset(co, mk)
                if 1 <= k <= 5:
                    if count_orders: t[co][k] += 1
                    elif mk not in seen: t[co][k] += 1; seen.add(mk)
        return t
    variants = [variant(ignore_2025=True), variant(keep_refunds=True), variant(raw_email=True), variant(count_orders=True)]
    return {"customers": customers, "orders": orders, "table": table, "variants": variants, "truth_cohort": truth_cohort, "activity": activity,
            "n_shifted": len(shifted), "counted": counted}

def _acceptable(d) -> bool:
    t = d["table"]
    pins = [("2026-01", "new"), ("2026-02", "new"), ("2026-01", 1), ("2026-03", 2)]
    total_new = sum(t[co]["new"] for co in COHORTS)
    for co, k in pins:
        v = t[co][k]
        if v < 6: return False
        # every naive variant moves at least one pinned cell? stronger: each pin moved by the variant it targets
        row_vals = [t[co][kk] for kk in ["new", 1, 2, 3, 4, 5] if kk != k]
        col_vals = [t[c2][k] for c2 in COHORTS if c2 != co]
        pct = [round(t[co][kk] / t[co]["new"] * 100, 1) for kk in range(1, 6)] if t[co]["new"] else []
        if v in row_vals or v in col_vals or any(abs(p - v) <= 0.05 for p in pct): return False
    v0, v1, v2, v3 = d["variants"]
    if v0["2026-01"]["new"] == t["2026-01"]["new"]: return False              # 2025 customers counted as new
    if v1["2026-01"]["new"] == t["2026-01"]["new"] or v1["2026-02"]["new"] == t["2026-02"]["new"]: return False
    if sum(v2[co]["new"] for co in COHORTS) == total_new: return False        # raw email splits customers
    if v3["2026-01"][1] == t["2026-01"][1]: return False                      # orders counted instead of customers
    if any(abs(total_new - t[co][kk]) < 1 for co in COHORTS for kk in ["new", 1, 2, 3, 4, 5]): return False
    # a pinned count must not also be an order total or refund on a row a cleaned orders sheet would tie to that
    # cohort label (order month or the customer's cohort), or the check passes on data rows instead of the table
    for co, k in pins:
        v = t[co][k]
        amts = {a for o in d["orders"] for a in (o["total"], o["refunded"])
                if _mk(o["date"].date()) == co or d["truth_cohort"].get(o["cust"]["cid"]) == co}
        if any(abs(a - v) < 0.05 for a in amts): return False
    if any(abs(a - total_new) < 0.2 for o in d["orders"] for a in (o["total"], o["refunded"])): return False
    return True

def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    orders = d["orders"]
    new_rows, old_rows = [], []
    for o in orders:
        if o["date"].year == 2026:
            new_rows.append([f"#{o['num']}", o["date"].strftime("%Y-%m-%d %H:%M"), o["email_shown"], o["cust"]["name"], o["status"],
                             money_str(o["total"], 1), money_str(o["refunded"], 1) if o["refunded"] else ""])
        else:
            old_rows.append([str(o["num"]), o["date"].strftime("%m/%d/%Y"), o["email_shown"], o["cust"]["name"], money_str(o["total"], 2),
                             {"Cancelled": "cancelled", "Refunded": "refunded", "Partially refunded": "partial_refund"}.get(o["status"], "complete")])
    write_csv(os.path.join(ws, "orders_export_2026-01-01_2026-06-30.csv"), ["Order #", "Order Date", "Customer Email", "Customer Name", "Status", "Total", "Refunded"], new_rows, bom=True)
    write_csv(os.path.join(ws, "orders_2025_jul-dec.csv"), ["Order", "Placed", "Buyer E-mail", "Buyer", "Amount", "State"], old_rows, crlf=True)
    write_text(os.path.join(ws, "cohort_notes.txt"),
        "Cohort table - notes for whoever builds it (Leila)\n\n"
        "A customer's cohort is the month of their first ever order with us. The web shop opened in July 2025, so between the\n"
        "two exports in this folder you have the complete order history. Anyone who bought in 2025 is an existing customer,\n"
        "not a new one, and does not belong in a 2026 cohort even if they ordered again this year.\n\n"
        "An order that was cancelled, or refunded in full, never happened as far as this table is concerned. A partial refund\n"
        "is still a real order.\n\n"
        "I want to see, for each month January to June, how many new customers we got, and then how many of those same people\n"
        "ordered again one month later, two months later, and so on. A person counts once in a month no matter how many orders\n"
        "they placed. Where a later month has not happened yet, leave the cell blank or mark it n/a.\n")
    # ---- reference
    t = d["table"]
    write_csv(os.path.join(ref, "cohorts.csv"), ["cohort", "new_customers", "month_1", "month_2", "month_3", "month_4", "month_5"],
              [[co, t[co]["new"]] + [(t[co][k] if _offset(co, "2026-06") >= k else "") for k in range(1, 6)] for co in COHORTS])
    write_json(os.path.join(ref, "notes.json"), {"total_new_customers": sum(t[co]["new"] for co in COHORTS), "orders_2026": len([o for o in orders if o["date"].year == 2026]),
                                                  "orders_2025": len([o for o in orders if o["date"].year == 2025]), "first_order_refunded_customers": d["n_shifted"],
                                                  "returning_2025_customers_in_2026": len({o["cust"]["cid"] for o in orders if o["date"].year == 2026 and o["cust"]["cid"] not in d["truth_cohort"]})})
    # ---- reference solution: Customers (email, cohort), Activity (email, cohort, offset label, 1), Summary with formulas
    cust_rows, act_rows = [], []
    for c in d["customers"]:
        co = d["truth_cohort"].get(c["cid"])
        if not co: continue
        cust_rows.append([c["email"], c["name"], co])
        for mk in sorted(d["activity"][c["cid"]]):
            k = _offset(co, mk)
            if 1 <= k <= 5: act_rows.append([c["email"], co, mk, f"Month {k}", 1])
    cust_rows.sort(key=lambda x: (x[2], x[0])); act_rows.sort(key=lambda x: (x[1], x[0], x[2]))
    nc, na = len(cust_rows) + 1, len(act_rows) + 1
    summary = []
    for i, co in enumerate(COHORTS, start=2):
        row = [co, f"=COUNTIF(Customers!$C$2:$C${nc},$A{i})"]
        for j, lab in enumerate(OFFSETS, start=1):
            L = "CDEFG"[j - 1]
            row.append(f"=SUMIFS(Activity!$E$2:$E${na},Activity!$B$2:$B${na},$A{i},Activity!$D$2:$D${na},{L}$1)" if _offset(co, "2026-06") >= j else "n/a")
        summary.append(row)
    summary.append(["Total", "=SUM(B2:B7)"])
    summary.append([]); summary.append(["Retention % of new customers"])
    base = len(summary) + 2
    for i, co in enumerate(COHORTS):
        srow = i + 2; prow = base + i
        row = [co, f"=B{srow}"]
        for j in range(1, 6):
            L = "CDEFG"[j - 1]
            row.append(f'=IF(B{prow}=0,"",ROUND({L}{srow}/B{prow}*100,1))' if _offset(co, "2026-06") >= j else "n/a")
        summary.append(row)
    summary.append([]); summary.append(["Cohort = month of first ever order (2025 buyers excluded); cancelled and fully refunded orders not counted; a customer counts once per month."])
    write_xlsx(os.path.join(sol, "cohorts.xlsx"), {
        "Summary": {"header": ["Cohort", "New customers"] + OFFSETS, "rows": summary, "widths": {"A": 12, "B": 15}},
        "Customers": {"header": ["email", "name", "cohort"], "rows": cust_rows, "widths": {"A": 32, "B": 22}},
        "Activity": {"header": ["email", "cohort", "active_month", "offset", "one"], "rows": act_rows, "widths": {"A": 32}}}, creator="reference")
    total_new = sum(t[co]["new"] for co in COHORTS)
    write_task_yaml(HERE, {
        "id": "retention-cohorts", "track": "desk", "category": "reports",
        "title": "Customer cohort retention table for the first half",
        "ask": "Build me a cohort retention table for January to June this year from the shop order exports, cohort months down the side written like 2026-01. My notes in the folder explain what I mean. Save it as cohorts.xlsx with the counts as formulas.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the cohort is the month of the first EVER order; last year's export (different column names, US dates, CRLF) is in the folder and its customers who reorder in 2026 are not new (check: January new customers)",
            "fully refunded orders (Refunded equals Total, status Refunded) and Cancelled orders never happened; eight customers' first orders are fully refunded so their cohort shifts or disappears, six later-month orders are refunded so a retention cell changes (checks: January new customers; February new customers)",
            "partial refunds still count as orders (check: February new customers)",
            "the same customer's email appears in different case and with stray spaces; a raw group-by splits customers (check: total new customers)",
            "customers place two or three orders in an active month; counting orders instead of customers inflates the later-month cells (check: January cohort month 1)",
            "the summary counts must be live formulas over cleaned data (check: live formulas)",
        ],
        "checks": [
            {"type": "file_exists", "name": "cohorts.xlsx exists", "path": "cohorts.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "cohorts.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "cohorts.xlsx"},
            {"type": "xlsx_value_present", "name": "January new customers", "path": "cohorts.xlsx", "expected": t["2026-01"]["new"], "rel_tol": 0.001, "near_text": "2026-01"},
            {"type": "xlsx_value_present", "name": "February new customers", "path": "cohorts.xlsx", "expected": t["2026-02"]["new"], "rel_tol": 0.001, "near_text": "2026-02"},
            {"type": "xlsx_value_present", "name": "January cohort month 1", "path": "cohorts.xlsx", "expected": t["2026-01"][1], "rel_tol": 0.001, "near_text": "2026-01"},
            {"type": "xlsx_value_present", "name": "March cohort month 2", "path": "cohorts.xlsx", "expected": t["2026-03"][2], "rel_tol": 0.001, "near_text": "2026-03"},
            {"type": "xlsx_value_present", "name": "total new customers", "path": "cohorts.xlsx", "expected": total_new, "rel_tol": 0.001, "near_text": "total"},
        ],
    })
    print(f"seed={seed} orders={len(orders)} table={t} total_new={total_new}")

if __name__ == "__main__":
    emit(argparse_seed())
