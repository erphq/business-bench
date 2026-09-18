#!/usr/bin/env python3
"""duplicate-payments: money a commercial furniture workshop has already paid twice, from its AP payment register.

    python gen.py [--seed N] [--naive DIR]

Business: Oakline Furniture Works builds booths, bars and reception desks for restaurants and offices. AP runs
checks twice a month plus ACH and the odd wire. The vendor master has grown duplicate records, so the same supplier
is paid under two vendor IDs. The controller wants every payment that paid an invoice already paid, with the
payment it duplicates and how much went out too much, before asking the vendors for the money back.

Traps (each caught by a check, see task.yaml):
  * one supplier sits in the vendor master twice; its second payment is under the other vendor ID and names the
    invoice without the INV- prefix                                                (checks: duplicate payments; original payment)
  * an invoice paid in half first and then in full overpaid only the first half's worth (check: amount overpaid)
  * invoice numbers with leading zeros on one payment and none on the other            (check: duplicate payments)
  * a voided check reissued, and a stopped check replaced by ACH, are one payment each (check: look-alikes not listed)
  * monthly rent and two genuine same-amount orders from one vendor are recurring, not duplicates
                                                                                   (check: look-alikes not listed)
  * an invoice paid in two instalments that add up to it is not overpaid               (check: look-alikes not listed)
  * a duplicate the vendor has already refunded is money back, not money to chase      (checks: duplicate payments; row count)
  * two different vendors (different tax IDs) share an invoice number and amount       (check: look-alikes not listed)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, timedelta
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

D = Decimal
SUPPLIERS = [("Cascade Hardwoods", "Hardwood lumber"), ("Northline Plywood & Panel", "Sheet goods"), ("Keller Hinge & Slide", "Hardware"),
             ("Finish Line Coatings", "Finishing supplies"), ("Tri-State Freight Lines", "Freight"), ("Lumen Glass & Mirror", "Glass"),
             ("Pacific Upholstery Supply", "Upholstery fabric"), ("Precision CNC Tooling", "Tooling"), ("Ridgeway Powder Coat", "Metal finishing"),
             ("Anchor Fastener Co", "Fasteners"), ("Harmon Edgebanding", "Edgebanding"), ("Summit Abrasives", "Abrasives"),
             ("Valley Welding Supply", "Welding gas"), ("Greenleaf Waste Hauling", "Waste"), ("Metro Electric Utility", "Utilities"),
             ("Bayside Stone Tops", "Countertops"), ("Crestline Leather", "Leather"), ("Ironside Steel Service", "Steel tube")]
LANDLORD = ("Millrace Industrial Partners", "Rent")


def cents(r, lo, hi) -> Decimal:
    return D(r.randint(int(lo * 100), int(hi * 100))) / 100


def inv_key(s: str) -> str:
    s = re.sub(r"(?i)^(inv(oice)?|no\.?|#)\s*[-#:]?\s*", "", s.strip())
    s = re.sub(r"[^0-9A-Za-z]", "", s)
    return s.lstrip("0").upper()


def build(seed: int) -> dict:
    r = rng(seed)
    vendors = []
    vid = r.randint(1010, 1040)
    for name, cat in SUPPLIERS + [LANDLORD]:
        vid += r.randint(2, 9)
        tin = f"{r.randint(20, 94)}-{r.randint(1000000, 9999999)}"
        vendors.append({"id": f"V{vid}", "name": name, "cat": cat, "tin": tin, "addr": address(r)})
    by_name = {v["name"]: v for v in vendors}
    dup_vendor = by_name["Cascade Hardwoods"]
    alias = {"id": f"V{vid + r.randint(40, 90)}", "name": "Cascade Hardwood Supply Inc", "cat": "Hardwood lumber", "tin": dup_vendor["tin"].replace("-", ""),
             "addr": dup_vendor["addr"]}
    vendors.append(alias)
    twin = by_name["Anchor Fastener Co"]
    other = by_name["Summit Abrasives"]

    pays = []   # one row per payment application: pid, date, method, ref, vendor, invoice, inv_amount, paid, status, memo, role

    def pay(when, method, vendor, invoice, inv_amount, paid, status="Cleared", role="", memo=""):
        row = {"date": when, "method": method, "ref": "", "vendor": vendor, "invoice": invoice, "inv_amount": D(inv_amount), "paid": D(paid),
               "status": status, "role": role, "memo": memo, "k": r.random()}
        pays.append(row)
        return row

    def inv_no(prefix="INV-"):
        return f"{prefix}{r.randint(10000, 99999)}"

    # ordinary traffic
    for v in vendors[:-2]:
        if v["name"] in (LANDLORD[0],):
            continue
        for _ in range(r.randint(3, 7)):
            amt = cents(r, 180, 9800)
            pay(day_in(r, date(2026, 1, 5), date(2026, 8, 28), weekday_only=True), r.choice(["Check", "Check", "ACH"]), v,
                r.choice([inv_no(), inv_no(""), inv_no("#")]), amt, amt)
    # a multi-invoice check
    mv = by_name["Northline Plywood & Panel"]
    when = date(2026, 5, 15)
    multi = []
    for _ in range(3):
        amt = cents(r, 400, 2600)
        multi.append(pay(when, "Check", mv, inv_no(), amt, amt, role="multi"))
    # rent, the same every month
    rent = cents(r, 6800, 9400).quantize(D("1"))
    for m in range(1, 9):
        pay(date(2026, m, 1) if date(2026, m, 1).weekday() < 5 else date(2026, m, 1) + timedelta(days=(7 - date(2026, m, 1).weekday())),
            "ACH", by_name[LANDLORD[0]], f"RENT-2026-{m:02d}", rent, rent, role="rent" if m > 1 else "", memo=f"Unit 4 rent {m:02d}/2026")

    # D1: same invoice, check run printed twice
    v1 = by_name["Finish Line Coatings"]
    inv1, a1 = inv_no(), cents(r, 1800, 5200)
    d1 = day_in(r, date(2026, 3, 2), date(2026, 4, 20), weekday_only=True)
    p1a = pay(d1, "Check", v1, inv1, a1, a1)
    p1b = pay(d1 + timedelta(days=r.choice([7, 14])), "Check", v1, inv1, a1, a1, role="dup_check_twice")
    # D2: duplicate vendor record, second paid by ACH without prefix
    inv2, a2 = inv_no(), cents(r, 4200, 11800)
    d2 = day_in(r, date(2026, 2, 2), date(2026, 5, 29), weekday_only=True)
    p2a = pay(d2, "Check", dup_vendor, inv2, a2, a2)
    p2b = pay(d2 + timedelta(days=r.randint(18, 40)), "ACH", alias, inv2.replace("INV-", ""), a2, a2, role="dup_vendor_record")
    # D3: half first, then the whole invoice
    v3 = by_name["Bayside Stone Tops"]
    inv3, a3 = inv_no(), cents(r, 5200, 12400)
    half = (a3 / 2).quantize(D("0.01"))
    d3 = day_in(r, date(2026, 4, 1), date(2026, 6, 15), weekday_only=True)
    p3a = pay(d3, "Check", v3, inv3, a3, half, memo="50% deposit per quote")
    p3b = pay(d3 + timedelta(days=r.randint(25, 45)), "ACH", v3, inv3, a3, a3, role="dup_over_half")
    # D4: leading zeros, wire then check
    v4 = by_name["Ironside Steel Service"]
    n4 = r.randint(100, 999)
    a4 = cents(r, 2400, 7600)
    d4 = day_in(r, date(2026, 5, 4), date(2026, 7, 24), weekday_only=True)
    p4a = pay(d4, "Wire", v4, f"000{n4}", a4, a4)
    p4b = pay(d4 + timedelta(days=r.randint(9, 20)), "Check", v4, f"{n4}", a4, a4, role="dup_leading_zero")
    # L1: void and reissue
    v5 = by_name["Tri-State Freight Lines"]
    inv5, a5 = inv_no(""), cents(r, 900, 3100)
    d5 = day_in(r, date(2026, 2, 2), date(2026, 7, 10), weekday_only=True)
    pay(d5, "Check", v5, inv5, a5, a5, status="Voided", memo="Wrong remit address")
    l1 = pay(d5 + timedelta(days=3), "Check", v5, inv5, a5, a5, role="void_reissue")
    # L2: stopped check replaced by ACH
    v6 = by_name["Pacific Upholstery Supply"]
    inv6, a6 = inv_no(), cents(r, 1400, 4800)
    d6 = day_in(r, date(2026, 3, 2), date(2026, 7, 10), weekday_only=True)
    pay(d6, "Check", v6, inv6, a6, a6, status="Stopped", memo="Lost in mail - stop payment")
    l2 = pay(d6 + timedelta(days=r.randint(12, 20)), "ACH", v6, inv6, a6, a6, role="stop_replaced")
    # L4: instalments that add up
    v7 = by_name["Precision CNC Tooling"]
    inv7, a7 = inv_no(), cents(r, 6000, 14000)
    first = (a7 * D("0.4")).quantize(D("0.01"))
    d7 = day_in(r, date(2026, 2, 2), date(2026, 5, 29), weekday_only=True)
    pay(d7, "Check", v7, inv7, a7, first, memo="Instalment 1 of 2")
    l4 = pay(d7 + timedelta(days=30), "Check", v7, inv7, a7, a7 - first, role="instalment", memo="Instalment 2 of 2")
    # L5: a duplicate the vendor already refunded
    v8 = by_name["Lumen Glass & Mirror"]
    inv8, a8 = inv_no(), cents(r, 1200, 3900)
    d8 = day_in(r, date(2026, 2, 2), date(2026, 6, 30), weekday_only=True)
    pay(d8, "Check", v8, inv8, a8, a8)
    l5 = pay(d8 + timedelta(days=r.randint(6, 12)), "ACH", v8, inv8, a8, a8, role="refunded_dup")
    refund = {"date": l5["date"] + timedelta(days=r.randint(15, 30)), "vendor": v8, "amount": a8, "invoice": inv8}
    # L6: two genuine identical orders
    v9 = by_name["Keller Hinge & Slide"]
    a9 = cents(r, 800, 2400)
    d9 = day_in(r, date(2026, 3, 2), date(2026, 7, 20), weekday_only=True)
    pay(d9, "Check", v9, inv_no(), a9, a9)
    l6 = pay(d9 + timedelta(days=r.randint(2, 6)), "Check", v9, inv_no(), a9, a9, role="same_amount_new_invoice")
    # L7: two vendors, same invoice number and amount
    shared_inv, a10 = inv_no(""), cents(r, 500, 1900)
    d10 = day_in(r, date(2026, 4, 1), date(2026, 8, 14), weekday_only=True)
    pay(d10, "Check", twin, shared_inv, a10, a10)
    l7 = pay(d10 + timedelta(days=r.randint(1, 5)), "Check", other, shared_inv, a10, a10, role="other_vendor_same_invoice")

    # ids and check numbers in date order
    pays.sort(key=lambda p: (p["date"], p["role"] != "multi", p["k"]))
    pid = r.randint(300, 360)
    chk = r.randint(14100, 14400)
    last_key = None
    for p in pays:
        key = (p["date"], p["vendor"]["id"], p["method"], p["role"] == "multi")
        if p["role"] == "multi" and last_key == key:
            p["pid"], p["ref"] = pays[pays.index(p) - 1]["pid"], pays[pays.index(p) - 1]["ref"]
            continue
        pid += 1
        p["pid"] = f"PMT-26-{pid:04d}"
        if p["method"] == "Check":
            chk += r.randint(1, 4)
            p["ref"] = str(chk)
        elif p["method"] == "ACH":
            p["ref"] = f"ACH{p['date'].strftime('%m%d')}{r.randint(10, 99)}"
        else:
            p["ref"] = f"FW{r.randint(100000, 999999)}"
        last_key = key

    # ---- truth by the controller's rules
    tin = lambda v: re.sub(r"\D", "", v["tin"])
    groups = {}
    for p in pays:
        if p["status"] != "Cleared":
            continue
        groups.setdefault((tin(p["vendor"]), inv_key(p["invoice"])), []).append(p)
    refunded = {(tin(refund["vendor"]), inv_key(refund["invoice"]))}
    dups = []
    for key, ps in groups.items():
        ps.sort(key=lambda p: (p["date"], p["pid"]))
        inv_amount = ps[0]["inv_amount"]
        running = D("0")
        for i, p in enumerate(ps):
            before = running
            running += p["paid"]
            if running > inv_amount and i > 0:
                over = min(p["paid"], running - max(before, inv_amount))
                if key in refunded:
                    continue
                dups.append({"pid": p["pid"], "orig": ps[0]["pid"], "vendor": p["vendor"]["name"], "invoice": p["invoice"], "over": over, "role": p["role"]})
    dups.sort(key=lambda x: x["pid"])
    roles = {p["role"]: p for p in pays if p["role"]}
    return {"vendors": vendors, "alias": alias, "pays": pays, "dups": dups, "refund": refund, "roles": roles,
            "lookalikes": [roles[k]["pid"] for k in ("void_reissue", "stop_replaced", "rent", "instalment", "refunded_dup", "same_amount_new_invoice",
                                                     "other_vendor_same_invoice")]}


def acceptable(d: dict) -> bool:
    roles = {x["role"] for x in d["dups"]}
    if roles != {"dup_check_twice", "dup_vendor_record", "dup_over_half", "dup_leading_zero"}:
        return False
    # the multi-invoice check shares one payment id; nothing else does
    multi = {p["pid"] for p in d["pays"] if p["role"] == "multi"}
    return len(multi) == 1 and len({p["pid"] for p in d["pays"]}) == len(d["pays"]) - 2


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["payment_id", "original_payment_id", "vendor", "invoice", "amount_overpaid", "reason"]
    if naive_dir:
        # same vendor id and same invoice text, any status, full amount of the later payment
        rows, first = [], {}
        for p in d["pays"]:
            k = (p["vendor"]["id"], p["invoice"])
            if k in first and first[k]["pid"] != p["pid"]:
                rows.append([p["pid"], first[k]["pid"], p["vendor"]["name"], p["invoice"], f"{p['paid']:.2f}", "same invoice"])
            first.setdefault(k, p)
        # plus anything with the same vendor and amount within 10 days
        for i, p in enumerate(d["pays"]):
            for q in d["pays"][:i]:
                if q["vendor"]["id"] == p["vendor"]["id"] and q["paid"] == p["paid"] and 0 < (p["date"] - q["date"]).days <= 10 and q["pid"] != p["pid"]:
                    rows.append([p["pid"], q["pid"], p["vendor"]["name"], p["invoice"], f"{p['paid']:.2f}", "same amount"])
        write_csv(os.path.join(naive_dir, "duplicate_payments.csv"), header, rows)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 21)

    rows = []
    for p in d["pays"]:
        name = p["vendor"]["name"]
        rows.append([p["pid"], p["date"].strftime("%m/%d/%Y"), p["method"], p["ref"], p["vendor"]["id"], name.upper() if r.random() < 0.15 else name,
                     p["invoice"], money_str(float(p["inv_amount"]), 0), money_str(float(p["paid"]), 0), p["status"], p["memo"]])
    write_csv(os.path.join(ws, "ap_payments_register_2026-01-01_to_2026-08-31.csv"),
              ["Payment ID", "Payment Date", "Method", "Check / Ref #", "Vendor ID", "Vendor", "Invoice #", "Invoice Amount", "Amount Paid",
               "Status", "Memo"], rows, preamble=["Oakline Furniture Works - AP payment detail", "Payment date 01/01/2026 - 08/31/2026"], crlf=True)

    vm = []
    for v in sorted(d["vendors"], key=lambda v: v["id"]):
        line, city, st, z = v["addr"]
        vm.append([v["id"], v["name"], v["cat"], f"{line}, {city}, {st} {z}", v["tin"], "Active"])
    write_xlsx(os.path.join(ws, "vendor_master_2026-09-01.xlsx"), {"Vendors": {
        "header": ["Vendor ID", "Vendor name", "Category", "Remit-to address", "Tax ID", "Status"], "rows": vm,
        "widths": {"B": 32, "C": 18, "D": 40, "E": 14}}}, creator="AP")

    rf = d["refund"]
    dep = [[rf["date"].strftime("%m/%d/%Y"), rf["vendor"]["name"], f"Refund of duplicate payment - inv {rf['invoice']}", f"{rf['amount']:,.2f}"],
           [(rf["date"] + timedelta(days=r.randint(10, 30))).strftime("%m/%d/%Y"), "Tri-State Freight Lines", "Rebate - fuel surcharge credit Q2",
            f"{cents(r, 80, 240):,.2f}"],
           [date(2026, 7, r.randint(6, 24)).strftime("%m/%d/%Y"), "Keller Hinge & Slide", "Credit memo refund - returned drawer slides",
            f"{cents(r, 120, 480):,.2f}"]]
    dep.sort(key=lambda x: x[0])
    write_csv(os.path.join(ws, "vendor_refunds_received_2026.csv"), ["Date received", "From", "Description", "Amount"], dep)

    write_text(os.path.join(ws, "note_from_controller.txt"),
               "Duplicate payments - before I call anyone\n\n"
               "Our bank flagged a supplier who told us we had paid them twice, which means there are probably more. Go through the\n"
               "payment register for this year and find money we have paid twice.\n\n"
               "How I want it judged:\n"
               "- Only payments that actually went out count. Voided and stopped checks never left the building.\n"
               "- The vendor master has some suppliers set up twice under different vendor IDs. Same tax ID = same supplier.\n"
               "- Invoice numbers get keyed with and without INV-, #, dashes and leading zeros. Ignore those when comparing.\n"
               "- A supplier can be paid more than once on one invoice if we pay in instalments - that is only a problem when what we\n"
               "  paid on the invoice adds up to more than the invoice.\n"
               "- If the supplier already sent the money back (see the refunds file), leave it off.\n\n"
               "Send me duplicate_payments.csv with one row for each payment that took us over: payment_id, original_payment_id (the\n"
               "first payment on that invoice), vendor, invoice, amount_overpaid (just the part that was too much) and a short reason\n"
               "I can read out on the phone.\n\n"
               "- Hannah\n")

    why = {"dup_check_twice": "Same invoice paid again by a second check",
           "dup_vendor_record": "Same invoice paid again under the supplier's duplicate vendor record",
           "dup_over_half": "Paid the invoice in full after already paying a 50% deposit on it",
           "dup_leading_zero": "Same invoice paid again, keyed without its leading zeros"}
    out = [[x["pid"], x["orig"], x["vendor"], x["invoice"], f"{x['over']:.2f}", why[x["role"]]] for x in d["dups"]]
    for base in (ref, sol):
        write_csv(os.path.join(base, "duplicate_payments.csv"), header, out)
    write_json(os.path.join(ref, "notes.json"), {"duplicates": {x["pid"]: x["role"] for x in d["dups"]},
                                                  "lookalikes": {d["roles"][k]["pid"]: k for k in ("void_reissue", "stop_replaced", "rent", "instalment",
                                                                                                  "refunded_dup", "same_amount_new_invoice",
                                                                                                  "other_vendor_same_invoice")}})
    ro = d["roles"]
    byrole = {x["role"]: x for x in d["dups"]}
    write_task_yaml(HERE, {
        "id": "duplicate-payments", "track": "desk", "category": "bookkeeping",
        "title": "Find supplier payments we made twice",
        "ask": "A supplier says we paid them twice this year - can you find every payment we have made twice? Hannah's note says how to judge it. Save the list as duplicate_payments.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"Cascade Hardwoods is in the vendor master twice ({d['alias']['id']} as '{d['alias']['name']}', its tax ID written without the "
            f"dash); {ro['dup_vendor_record']['pid']} pays the same invoice by ACH under the second ID and without the INV- prefix, so "
            "matching on vendor ID or invoice text misses it (checks: duplicate payments; original payment)",
            f"{ro['dup_over_half']['pid']} pays a stone-top invoice in full after a 50% deposit; only the deposit's worth "
            f"({byrole['dup_over_half']['over']:,.2f}) was paid too much, not the whole payment (check: amount overpaid)",
            f"{ro['dup_leading_zero']['pid']} pays steel invoice {ro['dup_leading_zero']['invoice']} that an earlier wire paid as "
            f"000{ro['dup_leading_zero']['invoice']} (check: duplicate payments)",
            f"a check voided for a wrong address and reissued ({ro['void_reissue']['pid']}) and a check stopped in the mail and replaced by "
            f"ACH ({ro['stop_replaced']['pid']}) paid their invoices once (check: look-alikes not listed)",
            "the landlord is paid the same rent by ACH every month and Keller Hinge & Slide sent two genuine orders for the same amount a "
            "few days apart; same vendor and amount is not the test (check: look-alikes not listed)",
            f"{ro['instalment']['pid']} is the second of two instalments that add up to the invoice (check: look-alikes not listed)",
            f"{ro['refunded_dup']['pid']} really did pay a glass invoice twice, but the refunds file shows the supplier sent it back "
            "(checks: duplicate payments; row count)",
            f"Anchor Fastener Co and Summit Abrasives share invoice number {ro['other_vendor_same_invoice']['invoice']} and amount days "
            "apart; different tax IDs, different invoices (check: look-alikes not listed)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "duplicate_payments.csv",
             "columns": ["payment_id", "original_payment_id", "invoice", "amount_overpaid", "reason"]},
            {"type": "csv_set_equal", "name": "duplicate payments", "path": "duplicate_payments.csv", "column": "payment_id",
             "ref": "duplicate_payments.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "duplicate_payments.csv", "equals_ref": "duplicate_payments.csv"},
            {"type": "csv_values_match", "name": "original payment", "path": "duplicate_payments.csv", "ref": "duplicate_payments.csv",
             "key": "payment_id", "columns": ["original_payment_id"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "amount overpaid", "path": "duplicate_payments.csv", "ref": "duplicate_payments.csv",
             "key": "payment_id", "columns": ["amount_overpaid"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [ro["dup_over_half"]["pid"], ro["dup_vendor_record"]["pid"]]},
            {"type": "text_not_contains", "name": "look-alikes not listed", "path": "duplicate_payments.csv", "phrases": d["lookalikes"]},
        ],
    })
    print(f"seed={seed} payments={len(d['pays'])} dups={[(x['pid'], x['role'], str(x['over'])) for x in d['dups']]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
