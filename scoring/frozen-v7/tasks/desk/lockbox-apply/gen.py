#!/usr/bin/env python3
"""lockbox-apply: a bank lockbox transmission (record-type file) applied to open receivables.

    python gen.py [--seed N] [--naive DIR]

Business: Ironwood Fabrication sells steel fabrication to contractors and marinas. Customers mail checks to the
bank's lockbox; each morning the bank sends a transmission file: batch headers, one record per check, the
remittance lines keyed from each check stub, batch and file trailers. Amounts are in cents with no decimal point.
The AR lead's email carries the application rules.

Traps (each caught by a check, see task.yaml):
  * record layout: check amount on type 6, invoice amounts on the type 4 lines under it, trailers carry totals,
    amounts in implied cents, ragged rows                                               (checks: applied per invoice; cash ties)
  * one invoice paid by two checks in the same batch                                     (check: applied per invoice)
  * a holding company's check pays invoices of two different customer accounts           (checks: applied per invoice; check lines)
  * short pays of $10.00 or less close the invoice with a write-off; larger ones stay open (checks: write-offs; applied per invoice)
  * a check larger than its stub lines leaves the excess unapplied                        (checks: unapplied checks; unapplied amounts)
  * a check with no stub goes unapplied even though it equals an open invoice             (checks: unapplied checks; nothing misapplied and cash ties to the file total)
  * yesterday's transmission, already posted, is in the folder                            (checks: nothing misapplied; cash ties)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

TODAY = date(2026, 9, 10)
YESTERDAY = date(2026, 9, 9)
TOL = 10.00
CUSTOMERS = [("C1004", "Pinnacle Roofing"), ("C1011", "Harbor Light Marine"), ("C1012", "Kingfisher Charters"), ("C1019", "Westbrook Plumbing"),
             ("C1023", "Dorsey Freight"), ("C1027", "Tamarack Brewing"), ("C1031", "Valley Forge Storage"), ("C1036", "Hollowell Electric"),
             ("C1040", "Pemberton HVAC"), ("C1044", "Redwood Property Mgmt"), ("C1052", "Northfield Auto Body"), ("C1058", "Saltmarsh Kayaks"),
             ("C1063", "Silverline Logistics"), ("C1067", "Granite Peak Outfitters")]
HOLDING = "HARBOR LIGHT HOLDINGS LLC"


def cents(x: float) -> str:
    return f"{int(round(x * 100)):010d}"


def build(seed: int) -> dict:
    r = rng(seed)
    # ---- open AR ----
    inv_nums = sorted(r.sample(range(48100, 48990), 60))
    invoices = []
    k = 0
    for cid, cname in CUSTOMERS:
        for _ in range(r.randint(3, 5)):
            n = inv_nums[k]; k += 1
            d = day_in(r, date(2026, 6, 15), date(2026, 8, 31))
            orig = money(r, 480, 9800)
            bal = orig if r.random() < 0.85 else round(orig - money(r, 100, orig * 0.5), 2)
            invoices.append({"num": n, "cid": cid, "customer": cname, "date": d, "orig": orig, "open": bal})
    invoices.sort(key=lambda i: i["num"])
    by_cust = {}
    for inv in invoices:
        by_cust.setdefault(inv["cid"], []).append(inv)
    used = set()

    def take(cid, n=1):
        pool = [i for i in by_cust[cid] if i["num"] not in used]
        got = r.sample(pool, n)
        for g in got:
            used.add(g["num"])
        return got

    checks = []   # {batch, seq, check_no, amount, remitter, aba, acct, lines:[{ref, amount, inv, kind}], kind}
    check_nos = set()

    def new_check_no():
        while True:
            c_ = str(r.randint(1001, 98999))
            if c_ not in check_nos:
                check_nos.add(c_); return c_

    def ref_text(n):
        return r.choice([f"{n}", f"INV-{n}", f"INV {n}", f"#{n}", f"Inv{n}", f"INV-0{n}"])

    def regular(cid, cname, n_lines):
        invs = take(cid, n_lines)
        lines = [{"ref": ref_text(i["num"]), "amount": i["open"], "inv": i, "kind": "full"} for i in invs]
        return {"amount": round(sum(l["amount"] for l in lines), 2), "remitter": cname.upper(), "lines": lines, "kind": "regular", "cid": cid}

    plan = []
    ids = [c for c in CUSTOMERS if c[0] not in ("C1011", "C1012")]
    r.shuffle(ids)
    # special checks
    cid, cname = ids[0]
    split_inv = take(cid, 1)[0]
    part = round(split_inv["open"] * r.uniform(0.45, 0.65), 0)
    plan.append({"amount": part, "remitter": cname.upper(), "cid": cid, "kind": "split_1",
                 "lines": [{"ref": ref_text(split_inv["num"]), "amount": part, "inv": split_inv, "kind": "split"}]})
    rest = round(split_inv["open"] - part, 2)
    plan.append({"amount": rest, "remitter": cname.upper(), "cid": cid, "kind": "split_2",
                 "lines": [{"ref": ref_text(split_inv["num"]), "amount": rest, "inv": split_inv, "kind": "split"}]})
    hl = take("C1011", 2); kf = take("C1012", 1)
    plan.append({"amount": round(sum(i["open"] for i in hl + kf), 2), "remitter": HOLDING, "cid": None, "kind": "holding",
                 "lines": [{"ref": ref_text(i["num"]), "amount": i["open"], "inv": i, "kind": "full"} for i in hl + kf]})
    cid, cname = ids[1]
    a, b = take(cid, 2)
    short1 = round(r.choice([3.5, 6.0, 7.25, 8.4, 4.75]), 2)
    plan.append({"amount": round(a["open"] - short1 + b["open"], 2), "remitter": cname.upper(), "cid": cid, "kind": "short_small",
                 "lines": [{"ref": ref_text(a["num"]), "amount": round(a["open"] - short1, 2), "inv": a, "kind": "short_small"},
                           {"ref": ref_text(b["num"]), "amount": b["open"], "inv": b, "kind": "full"}]})
    cid, cname = ids[2]
    a = take(cid, 1)[0]
    plan.append({"amount": round(a["open"] - TOL, 2), "remitter": cname.upper(), "cid": cid, "kind": "short_exact",
                 "lines": [{"ref": ref_text(a["num"]), "amount": round(a["open"] - TOL, 2), "inv": a, "kind": "short_exact"}]})
    cid, cname = ids[3]
    a = take(cid, 1)[0]
    big_short = float(r.choice([35, 48, 60, 85, 120]))
    plan.append({"amount": round(a["open"] - big_short, 2), "remitter": cname.upper(), "cid": cid, "kind": "short_big",
                 "lines": [{"ref": ref_text(a["num"]), "amount": round(a["open"] - big_short, 2), "inv": a, "kind": "short_big"}]})
    cid, cname = ids[4]
    a, b = take(cid, 2)
    over = float(r.choice([150, 225, 90, 310]))
    plan.append({"amount": round(a["open"] + b["open"] + over, 2), "remitter": cname.upper(), "cid": cid, "kind": "overpay", "over": over,
                 "lines": [{"ref": ref_text(a["num"]), "amount": a["open"], "inv": a, "kind": "full"},
                           {"ref": ref_text(b["num"]), "amount": b["open"], "inv": b, "kind": "full"}]})
    cid, cname = ids[5]
    target = [i for i in by_cust[cid] if i["num"] not in used]
    target = target[0]
    plan.append({"amount": target["open"], "remitter": cname.upper(), "cid": cid, "kind": "no_stub", "lines": [], "lookalike": target})
    used.add(target["num"])           # nobody else pays it
    for cid, cname in ids[6:]:
        plan.append(regular(cid, cname, r.choice([1, 1, 2, 3])))
    # batches: the two split checks land in the same batch
    specials = [p for p in plan if p["kind"] not in ("split_1", "split_2")]
    r.shuffle(specials)
    batches = [[], [], []]
    for i, p in enumerate(specials):
        batches[i % 3].append(p)
    sb = r.randrange(3)
    batches[sb] += [plan[0], plan[1]]
    r.shuffle(batches[sb])
    for bi, bt in enumerate(batches, start=1):
        for si, p in enumerate(bt, start=1):
            p["batch"], p["seq"], p["check_no"] = bi, si, new_check_no()
            p["aba"] = r.choice(["125000024", "123006800", "325070760", "121000358", "322271627"])
            p["acct"] = f"****{r.randint(1000, 9999)}"
            checks.append(p)

    # ---- yesterday's already-posted file (invoices no longer open) ----
    y_checks = []
    for si in range(1, 5):
        cid, cname = r.choice(CUSTOMERS)
        n = r.randint(48000, 48099)
        amt = money(r, 600, 7000)
        y_checks.append({"batch": 1, "seq": si, "check_no": new_check_no(), "amount": amt, "remitter": cname.upper(),
                         "aba": "125000024", "acct": f"****{r.randint(1000, 9999)}", "lines": [{"ref": f"INV-{n}", "amount": amt}]})

    # ---- truth ----
    applied, unapplied = [], []
    for c_ in checks:
        tot = 0.0
        for l in c_["lines"]:
            inv = l["inv"]
            wo = 0.0
            if l["kind"] in ("short_small", "short_exact"):
                wo = round(inv["open"] - l["amount"], 2)
            applied.append({"check_no": c_["check_no"], "inv": inv["num"], "amount": l["amount"], "write_off": wo, "kind": l["kind"]})
            tot += l["amount"]
        left = round(c_["amount"] - tot, 2)
        if c_["kind"] == "no_stub":
            unapplied.append({"check_no": c_["check_no"], "amount": c_["amount"], "reason": "no remittance advice with the check - customer to confirm what it pays"})
        elif left > 0.004:
            unapplied.append({"check_no": c_["check_no"], "amount": left, "reason": "overpayment - check exceeds the invoices on the stub; hold on account"})
    per_inv = {}
    for a_ in applied:
        e = per_inv.setdefault(a_["inv"], {"applied": 0.0, "write_off": 0.0})
        e["applied"] = round(e["applied"] + a_["amount"], 2)
        e["write_off"] = round(e["write_off"] + a_["write_off"], 2)
    return {"invoices": invoices, "checks": checks, "batches": batches, "y_checks": y_checks, "applied": applied, "unapplied": unapplied,
            "per_inv": per_inv, "split_inv": split_inv["num"]}


def transmission(checks_by_batch: list[list], day: date, file_seq: str) -> list[list]:
    rows = [["1", "LBX2291", day.strftime("%Y%m%d"), "HARBOR TRUST", "IRONWOOD FABRICATION", file_seq]]
    n_items = 0; file_total = 0
    for bi, bt in enumerate(checks_by_batch, start=1):
        if not bt:
            continue
        rows.append(["5", f"{bi:03d}", day.strftime("%Y%m%d"), "LBX2291"])
        btot = 0
        for c_ in bt:
            rows.append(["6", f"{bi:03d}", f"{c_['seq']:04d}", c_["check_no"], cents(c_["amount"]), c_["remitter"], c_["aba"], c_["acct"]])
            for l in c_["lines"]:
                rows.append(["4", f"{bi:03d}", f"{c_['seq']:04d}", l["ref"], cents(l["amount"])])
            btot += int(round(c_["amount"] * 100))
        rows.append(["7", f"{bi:03d}", f"{len(bt):04d}", f"{btot:012d}"])
        n_items += len(bt); file_total += btot
    rows.append(["9", f"{len([b for b in checks_by_batch if b]):03d}", f"{n_items:05d}", f"{file_total:014d}"])
    return rows


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)

    write_csv(os.path.join(ws, "LBX2291_20260910.csv"), None, transmission(d["batches"], TODAY, "0412"))
    write_csv(os.path.join(ws, "LBX2291_20260909.csv"), None, transmission([d["y_checks"]], YESTERDAY, "0411"))
    write_text(os.path.join(ws, "lockbox_file_layout.txt"), (
        "HARBOR TRUST TREASURY SERVICES - WHOLESALE LOCKBOX TRANSMISSION, CSV LAYOUT v3\n"
        "\n"
        "One transmission per business day. Each line is one record; the first field is the record type.\n"
        "Records have different numbers of fields. All amounts are unsigned whole cents with no decimal point\n"
        "(0000124850 = 1,248.50).\n"
        "\n"
        "Type 1  File header      1, lockbox number, deposit date YYYYMMDD, bank, client name, file sequence\n"
        "Type 5  Batch header     5, batch number, deposit date YYYYMMDD, lockbox number\n"
        "Type 6  Payment          6, batch number, item sequence, check number, check amount, remitter name,\n"
        "                         routing number, account (masked)\n"
        "Type 4  Remittance       4, batch number, item sequence, invoice reference as keyed from the stub, amount\n"
        "                         paid on that invoice. Zero or more type 4 records follow the type 6 record they\n"
        "                         belong to and carry the same batch number and item sequence. A payment with no\n"
        "                         type 4 records arrived without a readable stub.\n"
        "Type 7  Batch trailer    7, batch number, item count, batch total\n"
        "Type 9  File trailer     9, batch count, item count, file total\n"
        "\n"
        "Invoice references are keyed exactly as the customer wrote them.\n"))
    ar_rows = [[f"INV-{i['num']}", i["cid"], i["customer"], i["date"], i["orig"], i["open"]] for i in d["invoices"]]
    write_xlsx(os.path.join(ws, "open_ar_2026-09-09.xlsx"), {"Open invoices": {
        "merged_title": "Ironwood Fabrication - open receivables at close of business 9 Sep 2026",
        "header": ["Invoice", "Customer ID", "Customer", "Invoice date", "Original amount", "Open balance"],
        "rows": ar_rows, "widths": {"A": 12, "B": 11, "C": 26, "D": 12, "E": 15, "F": 14},
        "number_formats": {"E": "#,##0.00", "F": "#,##0.00"}}}, creator="Ironwood AR")
    write_email_thread(os.path.join(ws, "email_from_lucia.txt"), [
        {"from": "Lucia Mensah <lucia@ironwoodfab.com>", "to": "you", "date": "Thu, 10 Sep 2026 08:20",
         "subject": "today's lockbox",
         "body": ("Can you apply today's lockbox file? Yesterday's is already posted - the open AR report is from after it went in.\n\n"
                  "Go by the stub: each remittance line tells you which invoice and how much. Some customers pay one invoice with "
                  "two checks, and the Harbor Light holding company pays for both Harbor Light Marine and Kingfisher Charters on one "
                  "check - that's fine, apply to whichever account the invoice belongs to.\n\n"
                  "Short pays: if a customer pays an invoice short by $10.00 or less, apply what they paid and write off the "
                  "difference so the invoice closes. More than $10.00 short, apply what they paid and leave the rest open - "
                  "no write-off, I'll chase it.\n\n"
                  "Anything that doesn't go onto an invoice stays unapplied: the extra when a check is bigger than the invoices "
                  "on its stub, and any check that came without a stub. Don't guess from the amount, I'll call them.\n\n"
                  "I need applied.csv with check_number, invoice_number, amount_applied and write_off, one line per check and "
                  "invoice, and unapplied.csv with check_number, amount and reason. Everything in today's file should end up "
                  "in one or the other.")}])

    # ---- reference and solution ----
    ap_rows = [[a["check_no"], f"INV-{a['inv']}", f"{a['amount']:.2f}", f"{a['write_off']:.2f}"] for a in d["applied"]]
    un_rows = [[u["check_no"], f"{u['amount']:.2f}", u["reason"]] for u in d["unapplied"]]
    for base in (ref, sol):
        write_csv(os.path.join(base, "applied.csv"), ["check_number", "invoice_number", "amount_applied", "write_off"], ap_rows)
        write_csv(os.path.join(base, "unapplied.csv"), ["check_number", "amount", "reason"], un_rows)
    holding = next(c_ for c_ in d["checks"] if c_["kind"] == "holding")
    split = [c_ for c_ in d["checks"] if c_["kind"] in ("split_1", "split_2")]
    trap_invs = sorted({a["inv"] for a in d["applied"] if a["kind"] != "full"} | {l["inv"]["num"] for l in holding["lines"]})
    file_total = round(sum(c_["amount"] for c_ in d["checks"]), 2)
    write_json(os.path.join(ref, "lockbox.json"), {
        "per_invoice": {str(k): v for k, v in sorted(d["per_inv"].items())}, "trap_invoices": trap_invs,
        "multi_line_checks": {holding["check_no"]: [l["inv"]["num"] for l in holding["lines"]],
                              **{c_["check_no"]: [c_["lines"][0]["inv"]["num"]] for c_ in split}},
        "file_total": file_total, "no_stub_lookalike_invoice": next(c_ for c_ in d["checks"] if c_["kind"] == "no_stub")["lookalike"]["num"],
        "yesterday_check_numbers": [c_["check_no"] for c_ in d["y_checks"]]})

    write_task_yaml(HERE, {
        "id": "lockbox-apply", "track": "desk", "category": "bookkeeping",
        "title": "Apply today's lockbox checks to open invoices",
        "ask": ("Please apply this morning's lockbox file against our open invoices - Lucia's email has how she wants it done "
                "and the bank's file layout is in the folder. Save applied.csv and unapplied.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the transmission is a record-type file with ragged rows: the check amount is on the type 6 record, the invoice "
            "amounts on the type 4 stub lines under it, batch and file trailers carry totals, and every amount is whole "
            "cents with no decimal point (checks: applied per invoice and write-offs; nothing misapplied and cash ties to the file total)",
            "one customer pays a single invoice with two checks in the same batch; both applications stand and the invoice "
            "closes (check: applied per invoice and write-offs)",
            f"{HOLDING} is not a customer, but its check's stub pays two Harbor Light Marine invoices and one Kingfisher "
            "Charters invoice; matching by remitter leaves it unapplied (checks: applied per invoice and write-offs; "
            "unapplied checks)",
            "one invoice is short by a few dollars and another by exactly $10.00; both close with the shortfall as a write-off, "
            "while a short pay of more than $10.00 applies only what was paid with no write-off (check: applied per invoice "
            "and write-offs)",
            "a check is larger than the invoices on its stub; the stub lines are applied and the excess goes to unapplied "
            "(checks: unapplied checks; unapplied amounts)",
            "a check arrived without a stub and equals one of that customer's open invoices to the cent; the email says do not "
            "guess from the amount, so it is unapplied in full (checks: unapplied checks; nothing misapplied and cash ties to the file total)",
            "yesterday's transmission is in the folder and already posted; its invoices are no longer open and none of its "
            "checks belong in either file (checks: nothing misapplied and cash ties to the file total; unapplied checks)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "applied.csv columns", "path": "applied.csv",
             "columns": ["check_number", "invoice_number", "amount_applied", "write_off"]},
            {"type": "csv_columns", "name": "unapplied.csv columns", "path": "unapplied.csv", "columns": ["check_number", "amount", "reason"]},
            {"type": "custom", "name": "applied per invoice and write-offs", "module": "check.py"},
            {"type": "custom", "name": "nothing misapplied and cash ties to the file total", "module": "check_ties.py"},
            {"type": "csv_set_equal", "name": "unapplied checks", "path": "unapplied.csv", "column": "check_number", "ref": "unapplied.csv"},
            {"type": "csv_values_match", "name": "unapplied amounts", "path": "unapplied.csv", "ref": "unapplied.csv", "key": "check_number",
             "columns": ["amount"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0},
        ],
    })
    print(f"seed={seed}: {len(d['checks'])} checks in {len(d['batches'])} batches, {len(d['applied'])} applications, "
          f"{len(d['unapplied'])} unapplied, file total {file_total:,.2f}")


def write_naive(d: dict, out: str) -> None:
    """Read the amount field as dollars, apply each check to its remitter's open invoice with the same amount,
    otherwise to the remitter's oldest invoice; no write-offs; everything else unapplied."""
    os.makedirs(out, exist_ok=True)
    name_to_cid = {n.upper(): c for c, n in CUSTOMERS}
    ap, un = [], []
    open_by = {}
    for inv in d["invoices"]:
        open_by.setdefault(inv["cid"], []).append(inv)
    for c_ in d["checks"]:
        cid = name_to_cid.get(c_["remitter"])
        invs = open_by.get(cid, [])
        hit = next((i for i in invs if abs(i["open"] - c_["amount"]) < 0.005), None) or (invs[0] if invs else None)
        if hit:
            ap.append([c_["check_no"], f"INV-{hit['num']}", f"{c_['amount']:.2f}", "0.00"])
        else:
            un.append([c_["check_no"], f"{c_['amount']:.2f}", "no matching customer"])
    write_csv(os.path.join(out, "applied.csv"), ["check_number", "invoice_number", "amount_applied", "write_off"], ap)
    write_csv(os.path.join(out, "unapplied.csv"), ["check_number", "amount", "reason"], un)


if __name__ == "__main__":
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--seed", type=int, default=0)
    ap_.add_argument("--naive", default=None)
    a_ = ap_.parse_args()
    emit(a_.seed, a_.naive)
