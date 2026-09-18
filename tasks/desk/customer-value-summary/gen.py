#!/usr/bin/env python3
"""customer-value-summary: per-customer lifetime value, first and last order, and order count from a shop export.

    python gen.py [--seed N] [--naive DIR]

Business: a small coffee roaster selling beans online since January 2024. The store was migrated from an older
platform in March 2025 and duplicate customer accounts get merged now and then, so one person can have orders
under two or three customer ids.

Traps (each caught by a check, see task.yaml):
  * the export has one row per line item; order fields are only on the first row (check: order count)
  * customer id changes (migration and merges, one chain of two)          (checks: customer list; lifetime value; first and last order)
  * partial refunds net; fully refunded orders count for nothing          (checks: lifetime value; first and last order)
  * test orders: a staff test account and tagged tests on a real account  (checks: customer list; order count)
  * voided orders                                                         (check: order count)
  * the customers export's Total Spent column is stale and gross          (check: lifetime value)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

START, END = date(2024, 1, 8), date(2026, 8, 30)
MIGRATION = date(2025, 3, 10)
COFFEES = [("Ethiopia Guji 12oz", 21.0), ("Colombia Huila 12oz", 19.0), ("House Espresso 12oz", 17.5),
           ("Decaf Swiss Water 12oz", 19.5), ("Kenya AA 12oz", 23.0), ("Espresso 5lb", 78.0), ("Pour-over kit", 42.0),
           ("Nightjar mug", 16.0), ("Guatemala Antigua 12oz", 20.0)]
SHIPPING = [0.0, 6.95, 8.50]


def build(seed: int) -> dict:
    r = rng(seed)
    n = 54
    ppl = people(r, n + 1)
    ids = sorted({r.randint(7300000000, 7399999999) for _ in range(n * 3)})
    r.shuffle(ids)
    customers = []
    for i, (f, l) in enumerate(ppl[:n]):
        customers.append({"id": str(ids[i]), "name": f"{f} {l}", "email": email_for(r, f, l), "old": []})
    spare = [str(x) for x in ids[n:]]
    # migrated customers: pre-migration orders under an SQ- id
    migrated = customers[:9]
    for c in migrated:
        c["old"].append({"id": f"SQ-{r.randint(100, 999):05d}", "until": MIGRATION, "reason": "Migrated from old store"})
    # merged duplicate accounts: older shopify id until a merge date
    merged = customers[9:13]
    for c in merged:
        md = MIGRATION + timedelta(days=r.randint(60, 420))
        c["old"].append({"id": spare.pop(), "until": md, "reason": "Merged duplicate account"})
    # one chain: SQ id -> intermediate shopify id -> current id
    chain = customers[0]
    chain_mid = spare.pop()
    chain_merge = MIGRATION + timedelta(days=r.randint(120, 330))
    chain["old"] = [{"id": chain["old"][0]["id"], "until": MIGRATION, "reason": "Migrated from old store", "to": chain_mid},
                    {"id": chain_mid, "until": chain_merge, "reason": "Merged duplicate account"}]

    def id_on(c, day):
        for o in sorted(c["old"], key=lambda z: z["until"]):
            if day < o["until"]:
                return o["id"]
        return c["id"]

    orders = []
    onum = 1001
    for c in customers:
        k = r.choice([1, 2, 2, 3, 3, 4, 5, 6, 8])
        if c in migrated or c in merged:
            k = max(k, 4)
        days = sorted(START + timedelta(days=r.randint(0, (END - START).days)) for _ in range(k))
        if c is chain:
            days = sorted([MIGRATION - timedelta(days=r.randint(30, 300)), MIGRATION + timedelta(days=r.randint(5, 100)),
                           chain_merge + timedelta(days=r.randint(5, 200)), END - timedelta(days=r.randint(3, 90))])
        if c in merged or c in migrated[1:]:
            old = c["old"][0]["until"]
            if not any(dd < old for dd in days):
                days[0] = old - timedelta(days=r.randint(10, 200))
            if not any(dd >= old for dd in days):
                days[-1] = old + timedelta(days=r.randint(10, 150))
            days.sort()
        for dd in days:
            lines = [(nm, pr, r.choice([1, 1, 1, 2])) for nm, pr in r.sample(COFFEES, r.choice([1, 1, 2, 2, 3]))]
            sub = round(sum(pr * q for _, pr, q in lines), 2)
            ship = r.choice(SHIPPING) if sub < 60 else 0.0
            tax = round(sub * 0.0, 2)
            orders.append({"day": dd, "cust": c, "cid": id_on(c, dd), "email": c["email"], "lines": lines,
                           "total": round(sub + ship + tax, 2), "status": "paid", "refunded": 0.0, "tags": "", "kind": "normal"})
    orders.sort(key=lambda o: (o["day"], o["cid"]))
    for o in orders:
        o["name"] = f"#{onum}"; onum += 1
        o["ts"] = datetime(o["day"].year, o["day"].month, o["day"].day, r.randint(7, 16), r.randint(0, 59), r.randint(0, 59))
    by_c = lambda c: [o for o in orders if o["cust"] is c]  # noqa: E731
    pool = [c for c in customers if len(by_c(c)) >= 3 and c is not chain]
    r.shuffle(pool)
    # full refund on a first order, a last order, and a whole customer; partial refunds elsewhere
    first_ref, last_ref = pool[0], pool[1]
    by_c(first_ref)[0].update(status="refunded", kind="full_refund")
    by_c(last_ref)[-1].update(status="refunded", kind="full_refund")
    all_ref = next(c for c in customers if len(by_c(c)) == 1 and c not in migrated and c not in merged)
    by_c(all_ref)[0].update(status="refunded", kind="full_refund")
    for c in pool[2:12]:
        o = r.choice(by_c(c))
        o.update(status="partially_refunded", kind="partial")
    for o in orders:
        if o["status"] == "refunded":
            o["refunded"] = o["total"]
        elif o["status"] == "partially_refunded":
            o["refunded"] = round(o["total"] * r.uniform(0.15, 0.45), 2)
    # a partial refund on the chain customer's migrated-era order
    co = by_c(chain)[1]
    co.update(status="partially_refunded", kind="partial", refunded=round(co["total"] * 0.3, 2))
    # voided
    for c in pool[12:15]:
        o = r.choice(by_c(c))
        if o["kind"] == "normal":
            o.update(status="voided", kind="voided")
    # tagged tests on a real account (the owner testing checkout on her own account)
    owner = pool[15]
    tests_on_owner = []
    for _ in range(2):
        dd = START + timedelta(days=r.randint(0, (END - START).days))
        lines = [("House Espresso 12oz", 17.5, 1)]
        o = {"day": dd, "cust": owner, "cid": owner["id"] if dd >= MIGRATION or not owner["old"] else id_on(owner, dd),
             "email": owner["email"], "lines": lines, "total": 17.5 + 6.95, "status": "paid", "refunded": 0.0,
             "tags": r.choice(["TEST", "test order - ignore"]), "kind": "test",
             "ts": datetime(dd.year, dd.month, dd.day, r.randint(7, 16), r.randint(0, 59), 0)}
        tests_on_owner.append(o)
    # staff test account
    staff = {"id": spare.pop(), "name": "Nightjar Test", "email": "ops@nightjar.coffee", "old": []}
    staff_orders = []
    for _ in range(4):
        dd = START + timedelta(days=r.randint(0, (END - START).days))
        staff_orders.append({"day": dd, "cust": staff, "cid": staff["id"], "email": staff["email"],
                             "lines": [("Pour-over kit", 42.0, 1)], "total": 42.0, "status": "paid", "refunded": 0.0,
                             "tags": "" if _ % 2 else "test", "kind": "test",
                             "ts": datetime(dd.year, dd.month, dd.day, r.randint(7, 16), r.randint(0, 59), 0)})
    allo = orders + tests_on_owner + staff_orders
    allo.sort(key=lambda o: o["ts"])
    for i, o in enumerate(allo):
        o["name"] = f"#{1001 + i}"

    # ---- truth ----
    out = {}
    for o in allo:
        if o["kind"] in ("test", "voided", "full_refund"):
            continue
        c = o["cust"]
        row = out.setdefault(c["id"], {"id": c["id"], "first": o["day"], "last": o["day"], "orders": 0, "ltv": 0.0})
        row["first"] = min(row["first"], o["day"]); row["last"] = max(row["last"], o["day"])
        row["orders"] += 1
        row["ltv"] = round(row["ltv"] + o["total"] - o["refunded"], 2)
    mapping = []
    for c in customers:
        for j, old in enumerate(sorted(c["old"], key=lambda z: z["until"])):
            to = old.get("to") or c["id"]
            mapping.append([old["id"], to, old["until"], old["reason"]])
    mapping.sort(key=lambda m: m[2])
    return {"customers": customers, "staff": staff, "orders": allo, "out": out, "mapping": mapping, "chain": chain,
            "chain_mid": chain_mid, "first_ref": first_ref, "last_ref": last_ref, "all_ref": all_ref, "owner": owner,
            "migrated": migrated, "merged": merged, "voided": [o for o in allo if o["kind"] == "voided"]}


def acceptable(d: dict) -> bool:
    out = d["out"]
    for c in (d["chain"], d["first_ref"], d["last_ref"], d["owner"]):
        if c["id"] not in out:
            return False
    if d["all_ref"]["id"] in out:
        return False
    if len(d["voided"]) < 2:
        return False
    # the chain customer's first order must be under the SQ id, and the mid id must hold an order too
    ch = [o for o in d["orders"] if o["cust"] is d["chain"]]
    return {o["cid"] for o in ch} >= {d["chain"]["id"], d["chain_mid"], d["chain"]["old"][0]["id"]}


HEADER = ["customer_id", "first_order", "last_order", "orders", "lifetime_value"]


def export_rows(d: dict) -> list[list]:
    rows = []
    for o in d["orders"]:
        for i, (nm, pr, q) in enumerate(o["lines"]):
            first = i == 0
            rows.append([o["name"], o["email"], o["ts"].strftime("%Y-%m-%d %H:%M:%S -0700"),
                         o["cid"] if first else o["cid"],
                         o["status"] if first else "", f"{o['total']:.2f}" if first else "",
                         f"{o['refunded']:.2f}" if first else "", o["tags"] if first else "", nm, q, f"{pr:.2f}"])
    return rows


def naive_rows(d: dict) -> list[list]:
    """Group every export row by the Customer ID as written, count rows, sum Total, ignore status and tags."""
    agg = {}
    for row in export_rows(d):
        cid = row[3]
        a = agg.setdefault(cid, {"first": row[2][:10], "last": row[2][:10], "n": 0, "v": 0.0})
        a["first"] = min(a["first"], row[2][:10]); a["last"] = max(a["last"], row[2][:10])
        a["n"] += 1
        a["v"] += float(row[5]) if row[5] else 0.0
    return [[k, v["first"], v["last"], v["n"], f"{v['v']:.2f}"] for k, v in sorted(agg.items())]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_csv(os.path.join(naive_dir, "customer_value.csv"), HEADER, naive_rows(d))
        return
    ws, ref, sol = task_dirs(HERE)
    write_csv(os.path.join(ws, "orders_export_all_time.csv"),
              ["Name", "Email", "Created at", "Customer ID", "Financial Status", "Total", "Refunded Amount", "Tags",
               "Lineitem name", "Lineitem quantity", "Lineitem price"], export_rows(d), bom=True)
    write_csv(os.path.join(ws, "customer_id_changes.csv"), ["old_customer_id", "new_customer_id", "changed_on", "reason"],
              [[m[0], m[1], m[2].isoformat(), m[3]] for m in d["mapping"]])
    # a stale customers export: gross of refunds, includes voids and tests, as of June
    cust_rows = []
    cutoff = date(2026, 6, 1)
    for c in d["customers"] + [d["staff"]]:
        os_ = [o for o in d["orders"] if o["cust"] is c and o["cid"] == c["id"] and o["day"] < cutoff]
        if not os_:
            continue
        first, last = c["name"].split(" ", 1)
        cust_rows.append([c["id"], first, last, c["email"], len(os_), f"{sum(o['total'] for o in os_):.2f}"])
    write_csv(os.path.join(ws, "customers_export_2026-06.csv"),
              ["Customer ID", "First Name", "Last Name", "Email", "Orders Count", "Total Spent"], cust_rows)
    write_text(os.path.join(ws, "note_from_maya.txt"), (
        "For the loyalty program launch I need a lifetime value per customer: what each customer has actually "
        "paid us since we opened, how many orders, and their first and last order dates.\n\n"
        "A few things you need to know:\n\n"
        "- We moved stores in March 2025 and customer ids changed, and every so often we merge two accounts that "
        "belong to the same person. customer_id_changes.csv has every change. Report everyone under the id they "
        "have now.\n"
        "- Refunds come off. If an order was refunded in full it doesn't count at all - not as an order and not "
        "for the first or last order date.\n"
        "- Voided orders never got paid, leave them out.\n"
        "- Test orders: anything tagged as a test, and anything from our own ops@nightjar.coffee account. Leave "
        "those out too.\n"
        "- The customers export from June is out of date, don't trust its totals.\n\n"
        "Columns: customer_id, first_order, last_order, orders, lifetime_value. Dates like 2025-03-10. One row "
        "per customer who has bought something.\n\n"
        "Thanks! Maya\n"))

    rows = [[k, v["first"].isoformat(), v["last"].isoformat(), v["orders"], f"{v['ltv']:.2f}"] for k, v in sorted(d["out"].items())]
    write_csv(os.path.join(ref, "customer_value.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "customer_value.csv"), HEADER, rows)
    must = [d["chain"]["id"], d["first_ref"]["id"], d["last_ref"]["id"], d["owner"]["id"]] + \
           [c["id"] for c in d["merged"][:2]] + [c["id"] for c in d["migrated"][1:3]] + [o["cust"]["id"] for o in d["voided"]]
    must = list(dict.fromkeys(must))
    write_json(os.path.join(ref, "notes.json"), {"chain": [d["chain"]["old"][0]["id"], d["chain_mid"], d["chain"]["id"]],
                                                  "full_refund_first": d["first_ref"]["id"], "full_refund_last": d["last_ref"]["id"],
                                                  "all_refunded_customer": d["all_ref"]["id"], "test_tag_owner": d["owner"]["id"],
                                                  "staff_account": d["staff"]["id"], "must": must})
    write_task_yaml(HERE, {
        "id": "customer-value-summary", "track": "desk", "category": "spreadsheet",
        "title": "Lifetime value per customer from the shop export",
        "ask": ("Maya wants lifetime value for every customer before the loyalty launch. Work it out from the order "
                "export and save customer_value.csv - her note explains the ids, refunds and test orders.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the export has one row per line item; Financial Status, Total, Refunded Amount and Tags are only on an "
            "order's first row, so counting rows counts line items, not orders (check: order count)",
            "customer ids changed in the March 2025 migration and in account merges; one customer went SQ id -> "
            "an intermediate id -> today's id, so a single lookup of the change file leaves their oldest orders "
            "under a dead id (checks: customer list; lifetime value; first and last order)",
            "partial refunds come off the order, and a fully refunded order counts for nothing - including when it "
            "is a customer's first or last order, which moves their dates (checks: lifetime value; first and last order)",
            "test orders are both the ops@nightjar.coffee account (only half of its orders carry a test tag) and "
            "two tagged test orders on a real customer's account (checks: customer list; order count)",
            "voided orders have a Total but were never paid (check: order count)",
            "the June customers export has Orders Count and Total Spent columns that look like the answer but are "
            "stale, gross of refunds and split across old ids (check: lifetime value)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "customer_value.csv", "columns": HEADER},
            {"type": "csv_set_equal", "name": "customer list", "path": "customer_value.csv", "column": "customer_id",
             "ref": "customer_value.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "customer_value.csv", "equals_ref": "customer_value.csv"},
            {"type": "csv_values_match", "name": "order count", "path": "customer_value.csv", "ref": "customer_value.csv",
             "key": "customer_id", "columns": ["orders"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0,
             "must_match_keys": must},
            {"type": "csv_values_match", "name": "lifetime value", "path": "customer_value.csv", "ref": "customer_value.csv",
             "key": "customer_id", "columns": ["lifetime_value"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": must},
            {"type": "csv_values_match", "name": "first and last order", "path": "customer_value.csv",
             "ref": "customer_value.csv", "key": "customer_id", "columns": ["first_order", "last_order"],
             "min_accuracy": 1.0, "must_match_keys": must},
        ],
    })
    print(f"seed={seed} orders={len(d['orders'])} customers_out={len(rows)} rows_export={len(export_rows(d))}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
