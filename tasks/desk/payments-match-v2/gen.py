#!/usr/bin/env python3
"""Generator for the payments-match desk task.

    python gen.py [--seed N]

Rewrites workspace/, reference/ and reference_solution/ for the seed.
Re-running with the same seed is byte-identical. Different seeds re-roll
customers, invoice numbers, dates and amounts; the trap structure is fixed:

  * invoice references in bank descriptions come in many formats
    ("INV-2026-0413", "INV 2026-0413", "inv2026-0413", "Payment 0413 Acme",
    "INV#20260413", a bare "0413", "INVOICE 413")
  * 6 payments carry only the customer name plus an exact amount
  * 1 line pays two invoices and names both
  * 1 line pays two invoices and names only the customer (it equals the sum
    of two of that customer's three open invoices; the third stays open)
  * 1 partial payment (60%) on INV-2026-0417 - the remainder stays open
  * 1 unrelated deposit (a supplier refund)
  * 1 exact duplicate bank line (export glitch, same line_id twice)
  * 7 invoices with no payment at all
  * ~20 debit lines and a small interest credit as background noise

The partial invoice is always INV-2026-0417 so task.yaml's must_match_keys
stays valid for every seed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import shutil
from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))

CUSTOMERS = [
    "Acme Industrial LLC", "Brightwater Dental Group", "Cedar & Pine Landscaping",
    "Dorsey Freight Inc", "Ellington Bakeries", "Foxglove Interiors",
    "Granite Peak Outfitters", "Harbor Light Marine", "Ironwood Fabrication Co",
    "Juniper Street Cafe", "Kestrel Analytics", "Lakeside Veterinary Clinic",
    "Meridian Title Services", "Northfield Auto Body", "Oakhurst Pediatrics",
    "Pinnacle Roofing", "Quarry Road Nursery", "Redwood Property Management",
    "Silverline Logistics", "Tamarack Brewing Co", "Uptown Fitness Studio",
    "Vantage Point Media", "Westbrook Plumbing & Heating", "Yellowtail Seafood Market",
]
SUPPLIERS = ["Northgate Office Supply", "Uline", "Grainger", "Staples Business", "Sysco"]
DEBITS = [
    ("PAYROLL GUSTO", 8000, 21000), ("RENT 44 MARKET ST PROPERTIES", 3200, 6400),
    ("AMAZON WEB SERVICES", 140, 900), ("PG&E UTILITY PMT", 180, 620),
    ("HARTFORD INSURANCE", 400, 1300), ("VERIZON WIRELESS", 120, 380),
    ("ULINE SHIPPING SUPPLIES", 90, 700), ("CARD PURCHASE STAPLES", 20, 260),
    ("QUICKBOOKS ONLINE", 30, 90), ("FEDEX", 25, 320), ("STATE TAX PMT", 600, 4200),
    ("IRS USATAXPYMT", 1500, 9000), ("CHECK 2041", 200, 2400), ("CHECK 2042", 200, 2400),
    ("CHECK 2043", 200, 2400), ("ZELLE TO JORDAN LEE", 100, 900), ("COMCAST BUSINESS", 110, 260),
    ("WEWORK MEMBERSHIP", 450, 1600), ("CARD PURCHASE HOME DEPOT", 30, 480),
    ("ADP PAYROLL FEES", 60, 240), ("CHEVRON FUEL", 40, 160),
]

REF_FMTS = [
    lambda al, sh, n: f"ACH CREDIT {al} INV-2026-{n}",
    lambda al, sh, n: f"WIRE IN {al} REF INV 2026-{n}",
    lambda al, sh, n: f"DEPOSIT {al} inv2026-{n}",
    lambda al, sh, n: f"ONLINE PMT Payment {n} {sh}",
    lambda al, sh, n: f"ACH CREDIT {al} INV#2026{n}",
    lambda al, sh, n: f"CHECK DEP {al} 2026-{n}",
    lambda al, sh, n: f"ACH CREDIT {al} {n}",
    lambda al, sh, n: f"WIRE IN {al} INVOICE {int(n)}",
]
NAME_ONLY_FMTS = [
    lambda al: f"ACH CREDIT {al}",
    lambda al: f"WIRE IN {al}",
    lambda al: f"DEPOSIT {al} THANK YOU",
    lambda al: f"ONLINE PMT {al} INVOICE",
]

N_INV = 55
EXPORT_START = date(2026, 7, 1)
EXPORT_END = date(2026, 9, 10)  # "this morning" is 2026-09-11
PARTIAL_ID = "INV-2026-0417"
PARTIAL_NUM = 417


def bank_alias(name: str) -> str:
    s = re.sub(r"[^A-Z0-9 ]", "", name.upper().replace("&", " "))
    words = [w for w in s.split() if w not in {"LLC", "INC", "CO", "LTD"}]
    return " ".join(words)[:20].rstrip()


def short_name(name: str) -> str:
    return name.split()[0]


def cents(x: float) -> int:
    return int(round(x * 100))


def amounts_ok(amounts: list[float], cust_of: list[str]) -> bool:
    c = [cents(a) for a in amounts]
    if len(set(c)) != len(c):
        return False
    singles = set(c)
    pair_sums: set[int] = set()
    by_cust: dict[str, list[int]] = defaultdict(list)
    for cust, a in zip(cust_of, c):
        by_cust[cust].append(a)
    for lst in by_cust.values():
        sums = [sum(k) for r in (1, 2, 3) for k in combinations(lst, r)]
        if len(set(sums)) != len(sums):
            return False
        pair_sums.update(sum(k) for k in combinations(lst, 2))
    return not (singles & pair_sums)


def write_csv(path: str, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def money(x: float) -> str:
    return f"{x:,.2f}"


def build(seed: int) -> dict:
    rng = random.Random(seed)

    # --- customers and invoice roster -------------------------------------
    customers = rng.sample(CUSTOMERS, 16)
    counts = [6, 5, 5, 5, 4, 4, 4, 3, 3, 3, 3, 3, 2, 2, 2, 1]  # sums to 55
    rng.shuffle(counts)
    cust_of: list[str] = []
    for c, n in zip(customers, counts):
        cust_of += [c] * n
    rng.shuffle(cust_of)

    ids: list[str] = []
    n = 401
    while len(ids) < N_INV:
        if n != PARTIAL_NUM and rng.random() < 0.15:  # gap = invoice settled earlier
            n += 1
            continue
        ids.append(f"INV-2026-{n:04d}")
        n += 1
    assert PARTIAL_ID in ids

    d0 = date(2026, 6, 15)
    inv_dates = sorted(d0 + timedelta(days=rng.randint(0, 70)) for _ in range(N_INV))

    while True:
        amounts = [round(rng.uniform(180, 9800), 2) for _ in range(N_INV)]
        if amounts_ok(amounts, cust_of):
            break
    all_cents = {cents(a) for a in amounts}
    by_cust_idx: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(cust_of):
        by_cust_idx[c].append(i)
    pair_cents = {cents(amounts[a]) + cents(amounts[b])
                  for lst in by_cust_idx.values() for a, b in combinations(lst, 2)}
    forbidden = all_cents | pair_cents

    invoices = [dict(invoice_id=ids[i], customer=cust_of[i], invoice_date=inv_dates[i],
                     amount=amounts[i]) for i in range(N_INV)]

    # --- trap assignment ---------------------------------------------------
    partial = ids.index(PARTIAL_ID)
    used = {partial}

    three = [c for c in customers if len(by_cust_idx[c]) == 3 and partial not in by_cust_idx[c]]
    c_name_combo = rng.choice(three)
    a, b, c3 = rng.sample(by_cust_idx[c_name_combo], 3)
    used |= {a, b, c3}

    four_plus = [c for c in customers if len(by_cust_idx[c]) >= 4
                 and len([i for i in by_cust_idx[c] if i not in used]) >= 2]
    c_explicit = rng.choice(four_plus)
    e1, e2 = rng.sample([i for i in by_cust_idx[c_explicit] if i not in used], 2)
    used |= {e1, e2}

    cands = [i for i in range(N_INV) if i not in used and len(by_cust_idx[cust_of[i]]) >= 2]
    rng.shuffle(cands)
    name_only: list[int] = []
    per: Counter = Counter()
    for i in cands:
        if per[cust_of[i]] < 2:
            name_only.append(i)
            per[cust_of[i]] += 1
        if len(name_only) == 6:
            break
    used |= set(name_only)

    remaining = [i for i in range(N_INV) if i not in used]
    recent = sorted(remaining, key=lambda i: (invoices[i]["invoice_date"], i), reverse=True)[:15]
    unpaid_extra = rng.sample(recent, 6)
    unpaid = sorted([c3] + unpaid_extra)
    used |= set(unpaid)

    ref_singles = [i for i in range(N_INV) if i not in used]

    # --- v2 traps: judgment the reference-and-amount ladder cannot encode ----
    # card remittance net of the processor fee, an international wire short by bank charges,
    # a payment for an invoice closed last month, and a reference that names another
    # customer's invoice while the payer and amount say otherwise.
    rng.shuffle(ref_singles)
    i_card = ref_singles.pop()
    i_fx = ref_singles.pop()
    # wrong reference: payer A's invoice, description names an invoice of a different customer B
    i_wrong = next(i for i in ref_singles if any(cust_of[j] != cust_of[i] for j in range(N_INV)))
    ref_singles.remove(i_wrong)
    j_other = rng.choice([j for j in range(N_INV) if cust_of[j] != cust_of[i_wrong] and j not in (i_card, i_fx)])
    ref_singles.sort()

    # --- bank lines --------------------------------------------------------
    def pay_date(i: int) -> date:
        d = invoices[i]["invoice_date"] + timedelta(days=rng.randint(12, 40))
        return min(max(d, EXPORT_START), EXPORT_END)

    def rand_date() -> date:
        return EXPORT_START + timedelta(days=rng.randint(0, (EXPORT_END - EXPORT_START).days))

    lines: list[dict] = []  # date, desc, amount, type, applies=[(idx, amt)], tag

    fmt_order = list(range(len(REF_FMTS)))
    rng.shuffle(fmt_order)
    for k, i in enumerate(ref_singles):
        inv = invoices[i]
        fmt = REF_FMTS[fmt_order[k % len(fmt_order)]]
        num = inv["invoice_id"][-4:]
        lines.append(dict(date=pay_date(i), desc=fmt(bank_alias(inv["customer"]), short_name(inv["customer"]), num),
                          amount=inv["amount"], type="CREDIT", applies=[(i, inv["amount"])], tag="ref"))

    for k, i in enumerate(name_only):
        inv = invoices[i]
        lines.append(dict(date=pay_date(i), desc=NAME_ONLY_FMTS[k % len(NAME_ONLY_FMTS)](bank_alias(inv["customer"])),
                          amount=inv["amount"], type="CREDIT", applies=[(i, inv["amount"])], tag="name_only"))

    # one line, two invoices named
    ea, eb = sorted((e1, e2))
    lines.append(dict(date=pay_date(eb),
                      desc=f"ACH CREDIT {bank_alias(c_explicit)} INV 2026-{ids[ea][-4:]} 2026-{ids[eb][-4:]}",
                      amount=round(amounts[ea] + amounts[eb], 2), type="CREDIT",
                      applies=[(ea, amounts[ea]), (eb, amounts[eb])], tag="combo_explicit"))

    # one line, two invoices, customer name only (third invoice stays open)
    na, nb = sorted((a, b))
    lines.append(dict(date=pay_date(nb), desc=f"WIRE IN {bank_alias(c_name_combo)}",
                      amount=round(amounts[na] + amounts[nb], 2), type="CREDIT",
                      applies=[(na, amounts[na]), (nb, amounts[nb])], tag="combo_name"))

    # partial payment, 60%
    part_amt = round(amounts[partial] * 0.60, 2)
    lines.append(dict(date=pay_date(partial),
                      desc=REF_FMTS[0](bank_alias(cust_of[partial]), short_name(cust_of[partial]), PARTIAL_ID[-4:]),
                      amount=part_amt, type="CREDIT", applies=[(partial, part_amt)], tag="partial"))

    # v2: card payment net of Stripe's fee (2.9% + 0.30); the invoice is paid in full
    card_amt = round(amounts[i_card] - (amounts[i_card] * 0.029 + 0.30), 2)
    lines.append(dict(date=pay_date(i_card), desc=f"STRIPE TRANSFER ST-{rng.randint(100000, 999999)} {bank_alias(cust_of[i_card])}",
                      amount=card_amt, type="CREDIT", applies=[(i_card, amounts[i_card])], tag="card_net"))
    # v2: international wire short by intermediary charges (1.2%); paid in full per the note
    fx_amt = round(amounts[i_fx] * (1 - 0.012), 2)
    lines.append(dict(date=pay_date(i_fx), desc=f"INTL WIRE IN {bank_alias(cust_of[i_fx])} SWIFT OUR REF {rng.randint(10**7, 10**8 - 1)}",
                      amount=fx_amt, type="CREDIT", applies=[(i_fx, amounts[i_fx])], tag="fx_short"))
    # v2: payment against an invoice closed last month (number not in the open list)
    closed_num = 300 + rng.randint(0, 80)
    while True:
        closed_amt = round(rng.uniform(300, 6000), 2)
        if cents(closed_amt) not in forbidden:
            break
    closed_cust = rng.choice(customers)
    lines.append(dict(date=rand_date(), desc=f"ACH CREDIT {bank_alias(closed_cust)} INV-2026-{closed_num:04d}",
                      amount=closed_amt, type="CREDIT", applies=[], tag="closed_invoice"))
    # v2: payer A, amount of A's invoice, but the reference names B's invoice number
    lines.append(dict(date=pay_date(i_wrong), desc=f"ACH CREDIT {bank_alias(cust_of[i_wrong])} INV-2026-{ids[j_other][-4:]}",
                      amount=amounts[i_wrong], type="CREDIT", applies=[(i_wrong, amounts[i_wrong])], tag="wrong_ref"))

    # unrelated deposit: supplier refund
    supplier = rng.choice(SUPPLIERS)
    while True:
        refund_amt = round(rng.uniform(80, 900), 2)
        if cents(refund_amt) not in forbidden:
            break
    lines.append(dict(date=rand_date(), desc=f"REFUND {supplier.upper()} ORD {rng.randint(10000, 99999)}",
                      amount=refund_amt, type="CREDIT", applies=[], tag="refund"))

    # interest
    lines.append(dict(date=date(2026, 8, 31), desc="INTEREST PAID", amount=round(rng.uniform(1.2, 8.9), 2),
                      type="CREDIT", applies=[], tag="interest"))

    # debits
    for desc, lo, hi in rng.sample(DEBITS, 19):
        while True:
            amt = round(rng.uniform(lo, hi), 2)
            if cents(amt) not in forbidden:
                break
        lines.append(dict(date=rand_date(), desc=desc, amount=amt, type="DEBIT", applies=[], tag="debit"))
    lines.append(dict(date=date(2026, 8, 31), desc="MONTHLY SERVICE FEE", amount=25.00, type="DEBIT",
                      applies=[], tag="debit"))

    # order, ids, duplicate
    for k, ln in enumerate(lines):
        ln["_k"] = k
    lines.sort(key=lambda ln: (ln["date"], ln["_k"]))
    base = rng.randint(30000, 90000)
    for k, ln in enumerate(lines):
        ln["line_id"] = f"BK-{base + k}"
    dup_cands = [ln for ln in lines if ln["tag"] == "ref"]
    dup_line = rng.choice(dup_cands)
    dup_line["dup"] = True

    return dict(invoices=invoices, lines=lines, dup_line=dup_line, partial=partial,
                refund_line=next(ln for ln in lines if ln["tag"] == "refund"),
                unpaid=unpaid, part_amt=part_amt,
                card_line=next(ln for ln in lines if ln["tag"] == "card_net"), i_card=i_card, card_amt=card_amt,
                fx_line=next(ln for ln in lines if ln["tag"] == "fx_short"), i_fx=i_fx, fx_amt=fx_amt,
                closed_line=next(ln for ln in lines if ln["tag"] == "closed_invoice"),
                wrong_line=next(ln for ln in lines if ln["tag"] == "wrong_ref"), i_wrong=i_wrong, j_other=j_other,
                interest_line=next(ln for ln in lines if ln["tag"] == "interest"))


def emit(seed: int) -> None:
    data = build(seed)
    invoices, lines = data["invoices"], data["lines"]

    ws = os.path.join(HERE, "workspace")
    ref = os.path.join(HERE, "reference")
    sol = os.path.join(HERE, "reference_solution")
    for d in (ws, ref, sol):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    # workspace ------------------------------------------------------------
    write_csv(os.path.join(ws, "open_invoices.csv"),
              ["invoice_id", "customer", "invoice_date", "amount"],
              [[i["invoice_id"], i["customer"], i["invoice_date"].isoformat(), f"{i['amount']:.2f}"]
               for i in invoices])

    bank_rows = []
    for ln in lines:
        row = [ln["line_id"], ln["date"].strftime("%m/%d/%Y"), ln["desc"], money(ln["amount"]), ln["type"]]
        bank_rows.append(row)
        if ln.get("dup"):
            bank_rows.append(list(row))
    write_csv(os.path.join(ws, "bank_export.csv"),
              ["line_id", "date", "description", "amount", "type"], bank_rows)

    with open(os.path.join(ws, "note.txt"), "w", encoding="utf-8") as f:
        f.write("Bank export is from this morning. Anything partially paid is still open for the remainder.\n\n"
                "Three things that trip people up:\n"
                "- Card payments come through Stripe net of their fee (2.9% plus 30 cents). The invoice is paid in full; apply the invoice amount and the difference is our card fee.\n"
                "- International wires arrive a little short because intermediary banks take charges, up to about 2%. Treat those as paid in full too.\n"
                "- When a reference number and the payer disagree, trust the payer and the amount; people copy the wrong invoice number more often than they pay the wrong bill.\n"
                "Anything that is not a payment for an open invoice (a refund, interest, a payment for something already closed) goes in unapplied.csv with the reason, so I can see it.\n\n- Dana\n")

    # reference ------------------------------------------------------------
    applied: dict[int, float] = defaultdict(float)
    matches = []
    for ln in lines:
        for idx, amt in ln["applies"]:
            applied[idx] += amt
            matches.append([invoices[idx]["invoice_id"], ln["line_id"], f"{amt:.2f}"])
    matches.sort(key=lambda r: (r[0], r[1]))

    unpaid_rows = []
    for i, inv in enumerate(invoices):
        out = round(inv["amount"] - applied.get(i, 0.0), 2)
        if out > 0.005:
            unpaid_rows.append([inv["invoice_id"], inv["customer"], f"{out:.2f}"])
    assert len(unpaid_rows) == 8, len(unpaid_rows)

    write_csv(os.path.join(ref, "unpaid.csv"), ["invoice_id", "customer", "amount_outstanding"], unpaid_rows)
    write_csv(os.path.join(ref, "matches.csv"), ["invoice_id", "line_id", "amount_applied"], matches)
    unapplied_rows = [
        [data["refund_line"]["line_id"], f"{data['refund_line']['amount']:.2f}", "supplier refund, not a customer payment"],
        [data["interest_line"]["line_id"], f"{data['interest_line']['amount']:.2f}", "bank interest"],
        [data["closed_line"]["line_id"], f"{data['closed_line']['amount']:.2f}", "invoice already closed; not in the open list"],
    ]
    unapplied_rows.sort()
    write_csv(os.path.join(ref, "unapplied.csv"), ["line_id", "amount", "reason"], unapplied_rows)

    dup = data["dup_line"]
    meta = dict(
        seed=seed,
        partial_invoice_id=PARTIAL_ID,
        partial_amount_applied=f"{data['part_amt']:.2f}",
        duplicate_line_id=dup["line_id"],
        duplicate_invoice_id=invoices[dup["applies"][0][0]]["invoice_id"],
        refund_line_id=data["refund_line"]["line_id"],
        paid_invoice_ids=sorted({invoices[i]["invoice_id"] for i in applied}),
        card_line_id=data["card_line"]["line_id"], card_invoice_id=invoices[data["i_card"]]["invoice_id"], card_bank_amount=f"{data['card_amt']:.2f}",
        fx_line_id=data["fx_line"]["line_id"], fx_invoice_id=invoices[data["i_fx"]]["invoice_id"], fx_bank_amount=f"{data['fx_amt']:.2f}",
        closed_line_id=data["closed_line"]["line_id"],
        wrong_ref_line_id=data["wrong_line"]["line_id"], wrong_ref_invoice_id=invoices[data["i_wrong"]]["invoice_id"],
        wrong_ref_named_invoice_id=invoices[data["j_other"]]["invoice_id"],
        invoice_amounts={i["invoice_id"]: f"{i['amount']:.2f}" for i in invoices},
    )
    with open(os.path.join(ref, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
        f.write("\n")

    # reference_solution: a correct deliverable set, used only to validate the grader
    shutil.copyfile(os.path.join(ref, "unpaid.csv"), os.path.join(sol, "unpaid.csv"))
    shutil.copyfile(os.path.join(ref, "matches.csv"), os.path.join(sol, "matches.csv"))
    shutil.copyfile(os.path.join(ref, "unapplied.csv"), os.path.join(sol, "unapplied.csv"))

    print(f"seed={seed}: {len(invoices)} invoices, {len(bank_rows)} bank lines "
          f"({len(matches)} match rows, {len(unpaid_rows)} open); partial={PARTIAL_ID} "
          f"dup={dup['line_id']} refund={data['refund_line']['line_id']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    emit(ap.parse_args().seed)
