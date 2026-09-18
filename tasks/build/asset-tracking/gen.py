#!/usr/bin/env python3
"""Deterministic seed generator for the asset-tracking build task.

    python gen.py [--seed N]

Writes:
  seed/assets.csv         IT asset register: tags written IT-000418 / IT-418 / 418 / 000418 with the
                          same asset repeated under two spellings, exact duplicate rows, site names in
                          several forms, purchase costs as currency strings, warranty lengths as
                          "36" / "3 years" / "36 months" / "3 yr", mixed dates
  seed/assignments.csv    who had each asset and when: tags in the same spellings, open assignments with a
                          blank return date, mixed dates, and one return dated before its assignment
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Warranty end dates (purchase date plus warranty length) avoid 2026-09-01 to 2027-04-30, so the expired
count holds and no imported asset enters a 60-day expiry alert for any test date from 2026-09-01 to
2027-02-28. Site manager names are fixed across seeds (the ask names Owen Pratt); other seeds re-roll
assets, people, and dates, and counts.json is recomputed from the truth.
"""
from __future__ import annotations

import calendar
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, write_csv, write_json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

SITES = {"Denver": 100, "Salt Lake City": 58, "Boise": 42, "Omaha": 40}
SITE_SPELLINGS = {"Denver": ["Denver", "Denver", "Denver HQ", "DENVER"], "Salt Lake City": ["Salt Lake City", "Salt Lake City", "SLC", "salt lake city"],
                  "Boise": ["Boise", "Boise", "Boise ", "BOISE"], "Omaha": ["Omaha", "Omaha", "omaha", "Omaha "]}
MANAGERS = {"Denver": "Grace Liu", "Salt Lake City": "Tyler Brooks", "Boise": "Owen Pratt", "Omaha": "Renee Castillo"}
RESTRICTED_SITE = "Boise"
# type -> list of (make, model, cost cents, warranty months choices, assignable)
CATALOG = {
    "Laptop": [("Dell", "Latitude 5440", 124900, [36]), ("Dell", "Latitude 7440", 168900, [36]), ("Lenovo", "ThinkPad T14", 138900, [36]),
               ("Apple", "MacBook Pro 14", 219900, [12, 36]), ("HP", "EliteBook 840", 132900, [36])],
    "Monitor": [("Dell", "P2723DE", 38900, [36]), ("LG", "27UP850", 44900, [12]), ("Dell", "U3423WE", 89900, [36, 60])],
    "Dock": [("Dell", "WD19S", 22900, [12, 0]), ("Lenovo", "ThinkPad USB-C Dock", 24900, [12, 0])],
    "Phone": [("Apple", "iPhone 15", 79900, [12, 24]), ("Samsung", "Galaxy S24", 85900, [12, 24])],
    "Printer": [("HP", "LaserJet M507", 74900, [12]), ("Brother", "MFC-L8900", 69900, [12])],
    "Server": [("Dell", "PowerEdge R660", 980000, [60])],
    "Switch": [("Cisco", "C9200L-24P", 315000, [60]), ("Ubiquiti", "USW-Pro-24", 69900, [12])],
}
TYPE_COUNTS = {"Laptop": 95, "Monitor": 60, "Dock": 28, "Phone": 32, "Printer": 8, "Server": 5, "Switch": 12}
ASSIGNABLE = {"Laptop", "Monitor", "Dock", "Phone"}
WIPE_TYPES = {"Laptop", "Phone"}
TOP_COST = 1845000  # one PowerEdge R760, the unique most expensive asset
GAP_START, GAP_END = date(2026, 9, 1), date(2027, 4, 30)
ALERT_DAYS = 60
N_EXACT_DUPES, N_TAG_DUPES = 4, 6
DISPOSAL_METHODS = ["Recycled", "Sold", "Destroyed", "Donated"]


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def rand_date(r, a: date, b: date) -> date:
    return a + timedelta(days=r.randint(0, (b - a).days))


def tag(n: int, style: int) -> str:
    return [f"IT-{n:06d}", f"IT-{n}", f"{n}", f"{n:06d}"][style]


def usd(c: int) -> str:
    return f"{c / 100:,.2f}"


def warranty_str(m: int, style: int) -> str:
    if m == 0:
        return ""
    y = m // 12
    return [f"{m}", f"{m} months", f"{y} years" if y > 1 else "1 year", f"{y} yr" if y else f"{m} mo"][style]


def main() -> None:
    seed = argparse_seed()
    r = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)

    # ------------------------------------------------------------------ assets
    n_total = sum(TYPE_COUNTS.values())
    types = [t for t, n in TYPE_COUNTS.items() for _ in range(n)]
    sites = [s for s, n in SITES.items() for _ in range(n)]
    r.shuffle(types)
    r.shuffle(sites)
    tag_numbers = r.sample(range(12, 4800), n_total)
    assets = []
    for i in range(n_total):
        t = types[i]
        make, model, cost, wchoices = r.choice(CATALOG[t])
        wm = r.choice(wchoices)
        while True:
            pd = rand_date(r, date(2019, 3, 1), date(2026, 8, 20))
            end = add_months(pd, wm) if wm else None
            if end is None or not (GAP_START <= end <= GAP_END):
                break
        assets.append({"num": tag_numbers[i], "type": t, "make": make, "model": model, "cost": cost, "wm": wm, "purchased": pd,
                       "warranty_end": end, "site": sites[i], "serial": f"{make[:2].upper()}{r.randint(10**7, 10**8 - 1)}"})
    # the unique top-cost server
    srv = next(a for a in assets if a["type"] == "Server")
    srv.update(model="PowerEdge R760", cost=TOP_COST)
    assert sum(1 for a in assets if a["cost"] == TOP_COST) == 1

    # status: infrastructure is In service; others assigned / in stock / in repair / disposed
    for a in assets:
        if a["type"] not in ASSIGNABLE:
            a["status"] = r.choices(["In service", "Disposed"], weights=[90, 10])[0]
        else:
            a["status"] = r.choices(["Assigned", "In stock", "In repair", "Disposed"], weights=[62, 20, 5, 13])[0]
        if a["status"] == "Disposed" and a["purchased"] > date(2025, 6, 1):
            a["status"] = "In stock" if a["type"] in ASSIGNABLE else "In service"

    # ------------------------------------------------------------------ people and assignments
    pairs = [(f, l) for f in FIRST for l in LAST]
    r.shuffle(pairs)
    people = {s: [] for s in SITES}
    k = 0
    for s, n in SITES.items():
        for _ in range(int(n * 0.9)):
            f, l = pairs[k]
            k += 1
            people[s].append({"name": f"{f} {l}", "email": f"{f[0]}{l}@calderfreight.com".lower(), "site": s})
    assignments = []

    def history(a, n_closed, open_one):
        start = a["purchased"] + timedelta(days=r.randint(1, 20))
        end_limit = date(2026, 8, 25)
        span = (end_limit - start).days
        if span < 30 * (n_closed + 1):
            n_closed = max(0, span // 60 - 1)
        cuts = sorted(r.sample(range(10, max(11, span - 5)), 2 * n_closed)) if n_closed else []
        d = start
        for j in range(n_closed):
            a_on = start + timedelta(days=cuts[2 * j]) if j else d
            ret = start + timedelta(days=cuts[2 * j + 1])
            if ret <= a_on:
                ret = a_on + timedelta(days=7)
            assignments.append({"asset": a, "person": r.choice(people[a["site"]]), "on": a_on, "ret": ret})
            d = ret + timedelta(days=r.randint(1, 10))
        if open_one:
            on = max(d, start) if n_closed else start
            if on > end_limit:
                on = end_limit
            assignments.append({"asset": a, "person": r.choice(people[a["site"]]), "on": on, "ret": None})

    for a in assets:
        if a["type"] not in ASSIGNABLE:
            continue
        if a["status"] == "Assigned":
            history(a, r.choice([0, 0, 0, 1, 1, 2]), True)
        elif a["status"] == "In stock":
            history(a, r.choice([0, 1, 1]), False)
        elif a["status"] == "In repair":
            history(a, r.choice([0, 1]), False)
        else:
            history(a, 1, False)
        if a["status"] == "Disposed":
            last_ret = max([x["ret"] for x in assignments if x["asset"] is a] or [a["purchased"]])
            a["disposed_on"] = min(last_ret + timedelta(days=r.randint(5, 60)), date(2026, 8, 28))
            a["disposal_method"] = r.choice(DISPOSAL_METHODS)

    # disposed infrastructure has no assignment history; date its disposal without drawing from the generator
    for a in assets:
        if a["status"] == "Disposed" and "disposal_method" not in a:
            a["disposed_on"] = min(add_months(a["purchased"], 36), date(2026, 8, 28))
            a["disposal_method"] = DISPOSAL_METHODS[a["num"] % len(DISPOSAL_METHODS)]

    # sanity: sequential, one open at most
    for a in assets:
        hs = sorted([x for x in assignments if x["asset"] is a], key=lambda x: x["on"])
        assert sum(1 for x in hs if x["ret"] is None) == (1 if a["status"] == "Assigned" else 0)
        for x, y in zip(hs, hs[1:]):
            assert x["ret"] is not None and x["ret"] <= y["on"], (x, y)

    # ------------------------------------------------------------------ named roles
    roles = {}

    def assign_role(name, a):
        a["role"] = name
        roles[name] = a
        return a

    def n_hist(a):
        return sum(1 for x in assignments if x["asset"] is a)

    def pick2(cond, fallback, mutate=None):
        c = [a for a in assets if cond(a) and not a.get("role")]
        if c:
            return r.choice(c)
        a = r.choice([a for a in assets if fallback(a) and not a.get("role")])
        if mutate:
            mutate(a)
        return a

    def rebuild_history(a):
        assignments[:] = [x for x in assignments if x["asset"] is not a]
        a["purchased"] = date(2021, 2, 1) + timedelta(days=r.randint(0, 300))
        a["warranty_end"] = add_months(a["purchased"], a["wm"]) if a["wm"] else None
        history(a, 2, True)

    h = assign_role("history", pick2(lambda a: a["type"] == "Laptop" and a["status"] == "Assigned" and a["site"] == "Salt Lake City" and a["wm"] == 36
                                     and a["purchased"] < date(2022, 1, 1),
                                     lambda a: a["type"] == "Laptop" and a["status"] == "Assigned" and a["site"] == "Salt Lake City" and a["wm"] == 36))
    rebuild_history(h)
    assert n_hist(h) == 3
    assign_role("repair", pick2(lambda a: a["status"] == "In repair" and a["site"] == "Salt Lake City",
                                lambda a: a["status"] == "In stock" and a["site"] == "Salt Lake City", lambda a: a.update(status="In repair")))
    assign_role("disposed_old", pick2(lambda a: a["status"] == "Disposed" and a["type"] == "Laptop" and a["warranty_end"] and a["warranty_end"] < GAP_START,
                                      lambda a: a["status"] == "Disposed" and a["warranty_end"] and a["warranty_end"] < GAP_START))

    def make_t14(a):
        a.update(make="Lenovo", model="ThinkPad T14", cost=138900)

    assign_role("dispose", pick2(lambda a: a["type"] == "Laptop" and a["status"] == "Assigned" and a["site"] == "Denver" and a["model"] == "ThinkPad T14",
                                 lambda a: a["type"] == "Laptop" and a["status"] == "Assigned" and a["site"] == "Denver" and a["wm"] == 36, make_t14))
    assign_role("out_of_scope", pick2(lambda a: a["type"] == "Laptop" and a["site"] == "Denver" and a["status"] == "Assigned", lambda a: False))
    assign_role("boise_return", pick2(lambda a: a["site"] == RESTRICTED_SITE and a["status"] == "Assigned" and a["type"] == "Monitor",
                                      lambda a: a["site"] == RESTRICTED_SITE and a["status"] == "Assigned"))
    assign_role("expired_in_stock", pick2(lambda a: a["status"] == "In stock" and a["warranty_end"] and a["warranty_end"] < GAP_START, lambda a: False))
    assign_role("no_warranty", pick2(lambda a: a["type"] == "Dock" and a["wm"] == 0 and a["status"] != "Disposed", lambda a: False))
    assign_role("wipe_return", pick2(lambda a: a["type"] == "Laptop" and a["status"] == "Assigned" and a["site"] == "Omaha", lambda a: False))
    def boise_spare(a):
        return a["site"] == RESTRICTED_SITE and a["type"] in ("Monitor", "Dock")

    def to_stock(a):
        assignments[:] = [x for x in assignments if not (x["asset"] is a and x["ret"] is None)]
        a["status"] = "In stock"

    assign_role("request_disposal", pick2(lambda a: boise_spare(a) and a["status"] == "In stock", lambda a: boise_spare(a) and a["status"] == "Assigned", to_stock))
    assign_role("request_reject", pick2(lambda a: boise_spare(a) and a["status"] == "In stock", lambda a: boise_spare(a) and a["status"] == "Assigned", to_stock))
    # the impossible assignment: a closed row whose return date is before its assignment date
    bad_cands = [x for x in assignments if x["ret"] is not None and not x["asset"].get("role") and (x["ret"] - x["on"]).days > 40]
    bad = r.choice(bad_cands)
    bad["bad"] = True
    # new holder for the reassignment item: a Salt Lake City person with no open assignment
    open_people = {x["person"]["email"] for x in assignments if x["ret"] is None}
    new_holder = r.choice([p for p in people["Salt Lake City"] if p["email"] not in open_people])

    # ------------------------------------------------------------------ text for the files
    for a in assets:
        a["tag_style"] = r.choices([0, 1, 2, 3], weights=[70, 10, 12, 8])[0]
        a["site_str"] = r.choice(SITE_SPELLINGS[a["site"]])
        a["cost_str"] = r.choice([f"${a['cost'] / 100:,.2f}", f"{a['cost'] // 100}" if a["cost"] % 100 == 0 else f"{a['cost'] / 100:.2f}", f"{a['cost'] / 100:,.2f}"])
        a["warranty_str"] = warranty_str(a["wm"], r.randrange(4)) if a["wm"] else r.choice(["", "none"])
        a["purchased_str"] = date_variant(a["purchased"], r.choice([0, 1, 2, 3, 4]))
        a["status_str"] = r.choice([a["status"], a["status"], a["status"].lower(), a["status"].upper()])
        a["notes"] = ""
        if a["status"] == "Disposed":
            a["notes"] = f"{a['disposal_method']} {a['disposed_on'].isoformat()}"
    roles["history"]["tag_style"] = 0
    srv["cost_str"] = "$18,450.00"
    roles["dispose"]["cost_str"] = "1389"

    asset_cols = ["Asset Tag", "Serial Number", "Type", "Make", "Model", "Site", "Purchase Date", "Purchase Cost", "Warranty", "Status", "Notes"]

    def arow(a, style=None):
        return [tag(a["num"], a["tag_style"] if style is None else style), a["serial"], a["type"] if r.random() < 0.85 else a["type"].lower(),
                a["make"], a["model"], a["site_str"], a["purchased_str"], a["cost_str"], a["warranty_str"], a["status_str"], a["notes"]]

    rows = [{"a": a, "kind": "unique", "cols": arow(a)} for a in assets]
    dup_pool = [a for a in assets if not a.get("role") and a is not srv]
    r.shuffle(dup_pool)
    exact = dup_pool[:N_EXACT_DUPES]
    tagdup = dup_pool[N_EXACT_DUPES:N_EXACT_DUPES + N_TAG_DUPES]
    for a in exact:
        rows.append({"a": a, "kind": "exact_duplicate", "cols": list(rows[assets.index(a)]["cols"])})
    for a in tagdup:
        rows[assets.index(a)]["cols"][0] = tag(a["num"], 0)
        a["tag_style"] = 0
        rows.append({"a": a, "kind": "same_tag_written_differently", "cols": arow(a, style=r.choice([1, 2, 3]))})
    r.shuffle(rows)
    for i, row in enumerate(rows, start=2):
        row["line"] = i
    write_csv(os.path.join(SEED_DIR, "assets.csv"), asset_cols, [row["cols"] for row in rows])

    assignments.sort(key=lambda x: (x["on"], x["asset"]["num"]))
    arows = []
    for x in assignments:
        on, ret = x["on"], x["ret"]
        if x.get("bad"):
            ret_written = on - timedelta(days=(x["ret"] - x["on"]).days)
        else:
            ret_written = ret
        x["ret_written"] = ret_written
        x["tag_str"] = tag(x["asset"]["num"], r.choices([0, 1, 2, 3], weights=[60, 15, 15, 10])[0])
        x["on_str"] = date_variant(on, r.choice([0, 1, 2, 3, 4]))
        x["ret_str"] = date_variant(ret_written, r.choice([0, 1, 2, 3, 4])) if ret_written else ""
        arows.append(x)
    hist = sorted([x for x in assignments if x["asset"] is roles["history"]], key=lambda x: x["on"])
    for x, st in zip(hist, [3, 1, 0]):
        x["on_str"] = date_variant(x["on"], st)
    hist[0]["tag_str"] = tag(roles["history"]["num"], 2)
    for i, x in enumerate(arows, start=2):
        x["line"] = i
    write_csv(os.path.join(SEED_DIR, "assignments.csv"), ["Asset Tag", "Employee", "Email", "Assigned On", "Returned On", "Assigned By"],
              [[x["tag_str"], x["person"]["name"], x["person"]["email"], x["on_str"], x["ret_str"], r.choice(["jmorales", "it-helpdesk", "kpatel", "IT Helpdesk"])]
               for x in arows])

    # ------------------------------------------------------------------ figures
    live = [a for a in assets if a["status"] != "Disposed"]
    value = sum(a["cost"] for a in live)
    assigned = [a for a in assets if a["status"] == "Assigned"]
    expired = [a for a in live if a["warranty_end"] and a["warranty_end"] < GAP_START]
    in_stock = [a for a in assets if a["status"] == "In stock"]
    boise = [a for a in assets if a["site"] == RESTRICTED_SITE]

    def label(a):
        return {"tag": tag(a["num"], 0), "type": a["type"], "model": f"{a['make']} {a['model']}", "site": a["site"], "status": a["status"],
                "cost": usd(a["cost"]), "file_cost": a["cost_str"], "purchased": a["purchased"].isoformat(), "file_purchased": a["purchased_str"],
                "warranty_months": a["wm"], "file_warranty": a["warranty_str"],
                "warranty_end": a["warranty_end"].isoformat() if a["warranty_end"] else None,
                "file_tags": sorted({rw["cols"][0] for rw in rows if rw["a"] is a}), "file_lines": sorted(rw["line"] for rw in rows if rw["a"] is a)}

    def hlabel(x):
        return {"employee": x["person"]["name"], "email": x["person"]["email"], "assigned_on": x["on"].isoformat(), "file_assigned_on": x["on_str"],
                "returned_on": x["ret"].isoformat() if x["ret"] else None, "file_returned_on": x["ret_str"], "file_tag": x["tag_str"], "file_line": x["line"]}

    search_model = "Latitude 7440"
    warranty_examples = []
    for st in range(4):
        c = sorted([a for a in assets if a["wm"] and a["warranty_str"] == warranty_str(a["wm"], st) and a["wm"] % 12 == 0 and a["wm"] >= 24
                    and not a.get("role") and a not in exact and a not in tagdup], key=lambda a: a["num"])
        if c:
            warranty_examples.append(label(r.choice(c)))
    by_type_site = {}
    for a in live:
        d = by_type_site.setdefault(a["site"], {}).setdefault(a["type"], {"count": 0, "value_cents": 0})
        d["count"] += 1
        d["value_cents"] += a["cost"]
    by_type_site_out = {s: {t: {"count": v["count"], "value": usd(v["value_cents"])} for t, v in sorted(ts.items())} for s, ts in sorted(by_type_site.items())}
    rq, rj, wr = roles["request_disposal"], roles["request_reject"], roles["wipe_return"]
    wr_open = next(x for x in assignments if x["asset"] is wr and x["ret"] is None)
    br_open = next(x for x in assignments if x["asset"] is roles["boise_return"] and x["ret"] is None)
    dp_open = next(x for x in assignments if x["asset"] is roles["dispose"] and x["ret"] is None)

    counts = {
        "seed": seed,
        "valid_test_dates": ["2026-09-01", "2027-02-28"],
        "date_dependence": "No imported warranty ends between 2026-09-01 and 2027-04-30: the expired count holds and no imported asset is inside a 60-day expiry alert for any test date in the valid window.",
        "rules": {
            "tag": "IT- followed by six digits; 418, IT-418 and 000418 are IT-000418",
            "value": "sum of purchase cost over assets that are not disposed",
            "warranty_end": "purchase date plus the warranty length; blank or 'none' means no warranty",
            "warranty_expired": "not disposed, has a warranty, warranty end before the test date",
            "alert": f"warranty ends within the next {ALERT_DAYS} days",
            "disposal": "not while assigned; laptops and phones need a confirmed data wipe",
        },
        "assets": {
            "file_rows_excluding_header": len(rows), "exact_duplicate_rows": N_EXACT_DUPES, "same_tag_rows": N_TAG_DUPES, "unique_assets": n_total, "wrong_count_only_exact_duplicates_removed": len(rows) - N_EXACT_DUPES,
            "per_site": {s: sum(1 for a in assets if a["site"] == s) for s in SITES},
            "value_per_site": {s: usd(sum(a["cost"] for a in live if a["site"] == s)) for s in SITES},
            "per_type": {t: sum(1 for a in assets if a["type"] == t) for t in TYPE_COUNTS},
            "per_status": {st: sum(1 for a in assets if a["status"] == st) for st in ["Assigned", "In stock", "In service", "In repair", "Disposed"]},
            "same_tag_example": label(tagdup[0]), "same_tag_example_2": label(tagdup[1]), "exact_duplicate_example": label(exact[0]),
            "site_spellings": {s: sorted(set(v)) for s, v in SITE_SPELLINGS.items()},
            "warranty_examples": warranty_examples,
            "no_warranty": sum(1 for a in assets if not a["wm"]),
            "top_cost": label(srv),
            "wrong_value_including_disposed": usd(sum(a["cost"] for a in assets)),
            "wrong_expired_including_disposed": sum(1 for a in assets if a["warranty_end"] and a["warranty_end"] < GAP_START),
        },
        "assignments": {
            "file_rows_excluding_header": len(arows), "open": sum(1 for x in assignments if x["ret"] is None),
            "impossible_row": hlabel(bad) | {"asset": tag(bad["asset"]["num"], 0), "file_returned_on": bad["ret_str"], "note": "returned before assigned"},
            "history_asset": label(roles["history"]) | {"history": [hlabel(x) for x in hist], "current_holder": hist[-1]["person"]["name"]},
            "new_holder": new_holder,
        },
        "baseline": {
            "STAFF_ROLE": "Site manager", "VIEWER_ROLE": "Read-only", "MAIN_ENTITY": "asset", "MAIN_ENTITY_PLURAL": "assets",
            "SCOPE_RULE": f"assets at the {RESTRICTED_SITE} site", "SCOPE_COUNT": len(boise),
            "OUT_OF_SCOPE_EXAMPLE": label(roles["out_of_scope"]),
            "KPI_1": "Asset value", "KPI_1_VALUE": usd(value),
            "KPI_2": "Assets assigned to people", "KPI_2_VALUE": len(assigned),
            "KPI_3": "Warranties expired", "KPI_3_VALUE": len(expired),
            "KPI_4": "Assets in stock", "KPI_4_VALUE": len(in_stock),
            "SCOPED_KPI_1_VALUE": usd(sum(a["cost"] for a in live if a["site"] == RESTRICTED_SITE)),
            "SEARCH_TERM": search_model, "SEARCH_COUNT": sum(1 for a in assets if a["model"] == search_model),
            "FILTER_FIELD": "Type", "FILTER_VALUE": "Monitor", "FILTER_COUNT": TYPE_COUNTS["Monitor"],
            "SORT_FIELD": "Purchase Cost", "SORT_TOP": label(srv),
            "EXPORT_ROWS": n_total, "EXPORT_COLUMNS": ["Asset Tag", "Type", "Site", "Status", "Purchase Cost", "Warranty End"],
            "REQUIRED_FIELD": "Site",
        },
        "roles": {k: label(v) for k, v in sorted(roles.items())},
        "reassign_check": {"asset": tag(roles["history"]["num"], 0), "from": hist[-1]["person"]["name"], "to": new_holder["name"], "history_rows_after": len(hist) + 1},
        "dispose_check": {"asset": label(roles["dispose"]), "holder": dp_open["person"]["name"], "value_drop": usd(roles["dispose"]["cost"]),
                          "denver_value_after": usd(sum(a["cost"] for a in live if a["site"] == "Denver") - roles["dispose"]["cost"])},
        "restricted_return": label(roles["boise_return"]) | {"holder": br_open["person"]["name"]},
        "expired_list": {"count": len(expired), "count_after_dispose_check": len(expired) - (1 if roles["dispose"] in expired else 0), "includes": label(roles["expired_in_stock"]), "excludes_disposed": label(roles["disposed_old"]),
                         "excludes_no_warranty": label(roles["no_warranty"])},
        "change_1_by_type_site": by_type_site_out,
        "change_2_wipe": label(wr) | {"holder": wr_open["person"]["name"]},
        "change_3_disposal_request": {"approve": label(rq), "reject": label(rj),
                                      "boise_value_after_approval": usd(sum(a["cost"] for a in live if a["site"] == RESTRICTED_SITE) - rq["cost"])},
    }
    write_json(os.path.join(REF_DIR, "counts.json"), counts)
    b = counts["baseline"]
    print(f"assets {len(rows)} rows -> {n_total}; assignments {len(arows)} rows ({counts['assignments']['open']} open); value {b['KPI_1_VALUE']}; "
          f"assigned {b['KPI_2_VALUE']}; expired {b['KPI_3_VALUE']}; in stock {b['KPI_4_VALUE']}; Boise {b['SCOPE_COUNT']}")


if __name__ == "__main__":
    main()
