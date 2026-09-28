#!/usr/bin/env python3
"""fx-invoice-gains: realized FX gain or loss per EUR invoice for a US maker of guitar parts selling to EU dealers.

    python gen.py [--seed N] [--naive DIR]
    python gen.py --list-traps
    python gen.py --traps-off rate_gaps,usd_invoices --out DIR   # same draw, those pitfalls removed, same answer
    python gen.py --mutant short_fee --out DIR                   # a deliverable that falls for one trap

Business: a small US manufacturer of guitar hardware that invoices European dealers in euros and receives the
money into a US dollar account; the bank converts on arrival. The controller books everything at the ECB rate.

Traps (each caught by a check, see task.yaml):
  * the invoice is booked at the ECB rate of its own date and each receipt at the ECB rate of its value date; a
    weekend or TARGET holiday takes the last rate published before it (blank rows in the ECB file)  (check: fx per invoice)
  * partial payments settle part of an invoice at their own rate                                      (checks: fx; open)
  * one wire pays two invoices, split by the remittance line                                          (check: fx per invoice)
  * the bank's own rate and USD credited include its spread; that is bank charges, not FX            (check: fx per invoice)
  * a receipt short by the payer's bank charge (25 EUR or less, remittance says so) settles in full   (checks: fx; open)
  * two dealers are invoiced in US dollars and have no FX                                              (check: which invoices)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403
from bizgen.traps import TrapSet, add_trap_args, parse_trap_args, variant_dirs, active_trap_text  # noqa: E402

# Every trap in task.yaml, keyed. Switchable traps are removed at render time only, so build() and its
# random draws are identical in every variant and the correct answer never moves.
TRAPS = TrapSet(
    switchable={
        "rate_gaps": "ECB file skips weekends and leaves TARGET holidays blank (every day carries the last rate when off)",
        "bank_spread": "wire report carries the bank's rate and USD credited",
        "two_in_one": "one wire pays two invoices, split in German number format (two wire lines when off)",
        "usd_invoices": "two dealers invoiced in US dollars, in the register and the wire report",
    },
    fixed={
        "partial": "partial payments settle part of an invoice at their own rate; the rest stays open",
        "short_fee": "a receipt short by the payer's bank charge settles in full",
    },
)
# task.yaml trap sentences, in order, and the trap each one describes
TRAP_KEYS = ["rate_gaps", "bank_spread", "partial", "two_in_one", "short_fee", "usd_invoices"]

TARGET_HOLIDAYS = {date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1)}
DEALERS = [("Klangwerk Musikhaus GmbH", "DE"), ("Atelier Corde Paris SARL", "FR"), ("Luthiers Van Dijk B.V.", "NL"),
           ("Chitarre Bellini S.r.l.", "IT"), ("Gitarrenbau Huber OG", "AT"), ("Nordic Tonewood Oy", "FI"),
           ("Casa Ruiz Guitarras S.L.", "ES"), ("Strangenmeister KG", "DE")]
USD_DEALERS = [("Dublin Fret Works Ltd", "IE"), ("Lisboa Guitar Supply Lda", "PT")]


def r2(x: float) -> float:
    return float(f"{x + (1e-9 if x >= 0 else -1e-9):.2f}")


def build(seed: int) -> dict:
    r = rng(seed)
    # ECB USD per 1 EUR, TARGET business days Jan to Aug 2026
    rates, lvl, day = {}, 1.0840, date(2026, 1, 1)
    while day <= date(2026, 8, 31):
        if day.weekday() < 5 and day not in TARGET_HOLIDAYS:
            lvl = max(1.02, min(1.16, lvl + r.gauss(0.0002, 0.0046)))
            rates[day] = round(lvl, 4)
        day += timedelta(days=1)

    def ecb(d: date) -> float:
        while d not in rates:
            d -= timedelta(days=1)
        return rates[d]

    inv = []
    seq = 26001
    # forced dates carry the holiday/weekend traps
    forced_dates = {"weekend_invoice": date(2026, 2, 14), "good_friday_invoice": date(2026, 4, 3),
                    "partial": date(2026, 1, 22), "two_in_one_a": date(2026, 3, 10), "two_in_one_b": date(2026, 3, 12),
                    "short_fee": date(2026, 2, 26), "unpaid": date(2026, 6, 19), "easter_monday_receipt": date(2026, 3, 2),
                    "partial_open": date(2026, 5, 7)}
    tags = list(forced_dates) + [f"plain_{i}" for i in range(7)]
    for tag in tags:
        d0 = forced_dates.get(tag) or date(2026, 1, 5) + timedelta(days=r.randint(0, 170))
        dealer = r.choice(DEALERS)
        amt = float(r.randrange(2400, 38000, 5)) + r.choice([0.0, 0.5, 0.25, 0.8])
        while any(abs(amt - y["amount"]) < 1 for y in inv):
            amt += 35.0
        inv.append({"no": f"AF-{seq}", "tag": tag, "date": d0, "dealer": dealer[0], "ccy": "EUR", "amount": amt})
        seq += 1
    for i, dealer in enumerate(USD_DEALERS):
        inv.append({"no": f"AF-{seq}", "tag": f"usd_{i}", "date": date(2026, 2, 3) + timedelta(days=37 * i + 5), "dealer": dealer[0],
                    "ccy": "USD", "amount": float(r.randrange(3000, 15000, 10))})
        seq += 1
    inv.sort(key=lambda x: x["date"])
    for i, x in enumerate(inv):
        x["no"] = f"AF-{26001 + i * 3}"
    by = {x["tag"]: x for x in inv}

    receipts = []   # {date, payer, apps: [(invoice, eur_applied, fee_eur)], note}

    def pay_date(d0, lo=20, hi=60):
        d = d0 + timedelta(days=r.randint(lo, hi))
        return d if d.weekday() < 5 else d + timedelta(days=7 - d.weekday())

    for x in inv:
        if x["ccy"] != "EUR" or x["tag"] in ("unpaid", "two_in_one_a", "two_in_one_b"):
            continue
        t = x["tag"]
        if t == "partial":
            first = r2(round(x["amount"] * 0.4, 0))
            receipts.append({"date": pay_date(x["date"], 25, 30), "payer": x["dealer"], "apps": [(x, first, 0.0)],
                             "info": f"{x['no']} part payment 1/2"})
            receipts.append({"date": date(2026, 4, 6), "payer": x["dealer"], "apps": [(x, r2(x["amount"] - first), 0.0)],
                             "info": f"{x['no']} final payment 2/2"})
        elif t == "partial_open":
            first = r2(round(x["amount"] * 0.5, 0))
            receipts.append({"date": pay_date(x["date"], 30, 40), "payer": x["dealer"], "apps": [(x, first, 0.0)],
                             "info": f"Rechnung {x['no']} Teilzahlung"})
        elif t == "short_fee":
            fee = float(r.choice([15, 18, 20, 25]))
            receipts.append({"date": pay_date(x["date"], 30, 45), "payer": x["dealer"], "apps": [(x, r2(x["amount"] - fee), fee)],
                             "info": f"INV {x['no']} - our bank charges deducted EUR {fee:.2f}"})
        elif t == "easter_monday_receipt":
            receipts.append({"date": date(2026, 4, 6), "payer": x["dealer"], "apps": [(x, x["amount"], 0.0)], "info": f"{x['no']}"})
        elif t == "good_friday_invoice":
            receipts.append({"date": pay_date(x["date"], 28, 35), "payer": x["dealer"], "apps": [(x, x["amount"], 0.0)],
                             "info": f"Invoice {x['no']}"})
        else:
            receipts.append({"date": pay_date(x["date"]), "payer": x["dealer"], "apps": [(x, x["amount"], 0.0)],
                             "info": r.choice([f"{x['no']}", f"Invoice {x['no']}", f"Payment {x['no']} thank you", f"Fact. {x['no']}"])})
    a, b = by["two_in_one_a"], by["two_in_one_b"]
    b["dealer"] = a["dealer"]
    receipts.append({"date": date(2026, 4, 21), "payer": a["dealer"], "apps": [(a, a["amount"], 0.0), (b, b["amount"], 0.0)],
                     "info": f"{a['no']} {eu_money_str(a['amount'])} / {b['no']} {eu_money_str(b['amount'])}"})
    for x in inv:
        if x["ccy"] == "USD":
            receipts.append({"date": pay_date(x["date"]), "payer": x["dealer"], "apps": [(x, x["amount"], 0.0)], "info": f"{x['no']}", "usd": True})
    receipts.sort(key=lambda z: (z["date"], z["payer"]))

    # truth
    for x in inv:
        x["rate"] = ecb(x["date"]) if x["ccy"] == "EUR" else None
        x["settled"], x["gain"] = 0.0, 0.0
    for rc in receipts:
        rc["eur"] = r2(sum(e for _, e, _ in rc["apps"]))
        if rc.get("usd"):
            continue
        rc["rate"] = ecb(rc["date"])
        rc["bank_rate"] = round(rc["rate"] - r.choice([0.0105, 0.0110, 0.0120, 0.0125]), 4)
        rc["usd_credited"] = r2(rc["eur"] * rc["bank_rate"])
        for x, eur, fee in rc["apps"]:
            settle = r2(eur + fee)
            x["settled"] = r2(x["settled"] + settle)
            x["gain"] = r2(x["gain"] + r2(settle * rc["rate"]) - r2(settle * x["rate"]))
    for x in inv:
        x["open"] = r2(x["amount"] - x["settled"]) if x["ccy"] == "EUR" else None
    return {"rates": rates, "inv": inv, "receipts": receipts, "by": by, "ecb": ecb}


def acceptable(d: dict) -> bool:
    by, rates, ecb = d["by"], d["rates"], d["ecb"]
    # holiday/weekend lookups must differ from the next published rate (a forward lookup would move the figure)
    def nxt(day):
        while day not in rates:
            day += timedelta(days=1)
        return rates[day]
    for day in (by["weekend_invoice"]["date"], by["good_friday_invoice"]["date"], date(2026, 4, 6)):
        if abs(nxt(day) - ecb(day)) < 0.002:
            return False
    for tag in ("partial", "two_in_one_a", "short_fee", "easter_monday_receipt", "weekend_invoice", "good_friday_invoice"):
        if abs(by[tag]["gain"]) < 25:
            return False
    return True


def miriam_note(traps: TrapSet) -> str:
    """The controller's rules. A rule about a pitfall that a variant removed is dropped."""
    gaps = ("- If the ECB did not publish a rate on the date (weekend, holiday), use the last rate it published before that date.\n"
            if traps.on("rate_gaps") else "")
    spread = ("- Do not use the bank's rate or the USD amount the bank credited. The bank takes a spread; that difference goes to\n"
              "  bank charges, not to FX.\n" if traps.on("bank_spread") else "")
    usd = "- Invoices billed in US dollars have no FX and do not belong in this file.\n" if traps.on("usd_invoices") else ""
    return ("""FX on the euro invoices - how we book it

Our books are in dollars. Every euro invoice is booked at the ECB reference rate (the USD per 1 euro file) for the
invoice date. When the money arrives, the euros it settles are valued at the ECB rate for the value date on the bank
line. The difference is our realized FX gain (positive) or loss (negative).

""" + gaps + spread + """- A partial payment settles only the euros it pays, at its own rate. Whatever is still unpaid stays open; I do not
  want unrealized FX on open balances in this file.
- Some dealers' banks take their charge out of the wire. If the remittance says so and the charge is 25 euros or
  less, the invoice counts as settled in full: convert the full invoice amount it settles, and I book the charge
  separately.
- Rounding: for each receipt, convert the euros it settles at the receipt's rate and at the invoice's rate, round each
  to the cent, then subtract. An invoice's result is the sum over its receipts.
""" + usd + """
For the auditors I need one line per euro invoice from January to June: invoice, eur_settled, fx_gain_loss
(USD) and eur_open.

Miriam
""")


def emit(seed: int, naive_dir: str | None, traps: TrapSet = TRAPS, out: str | None = None,
         mutant: str | None = None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    if mutant:
        write_mutant(d, mutant, out)
        return
    here = out or HERE
    ws, ref, sol = task_dirs(HERE) if out is None else variant_dirs(out)
    inv, receipts, rates = d["inv"], d["receipts"], d["rates"]
    usd_on, spread_on, gaps_on = traps.on("usd_invoices"), traps.on("bank_spread"), traps.on("rate_gaps")

    write_xlsx(os.path.join(ws, "ar_invoice_register_2026-H1.xlsx"), {"Invoices": {
        "merged_title": "Alder & Finch Guitar Parts - export invoices January to June 2026",
        "header": ["Invoice", "Invoice Date", "Dealer", "Currency", "Amount", "Terms"],
        "rows": [[x["no"], x["date"], x["dealer"], x["ccy"], x["amount"], "Net 30"] for x in inv if usd_on or x["ccy"] != "USD"],
        "number_formats": {"E": "#,##0.00"}, "widths": {"C": 30, "B": 12}}}, creator="Alder & Finch")

    brows = []
    for rc in receipts:
        if rc.get("usd"):
            if usd_on:
                brows.append([rc["date"].strftime("%d/%m/%Y"), "Incoming wire", rc["payer"], rc["info"], f"{rc['eur']:,.2f}", "USD", "", f"{rc['eur']:,.2f}"])
        elif len(rc["apps"]) > 1 and not traps.on("two_in_one"):  # the combined wire as one line per invoice
            for x, eur, _ in rc["apps"]:
                brows.append([rc["date"].strftime("%d/%m/%Y"), "Incoming wire FX", rc["payer"], x["no"], f"{eur:,.2f}", "EUR",
                              f"{rc['bank_rate']:.4f}", f"{r2(eur * rc['bank_rate']):,.2f}"])
        else:
            brows.append([rc["date"].strftime("%d/%m/%Y"), "Incoming wire FX", rc["payer"], rc["info"], f"{rc['eur']:,.2f}", "EUR",
                          f"{rc['bank_rate']:.4f}", f"{rc['usd_credited']:,.2f}"])
    bheader = ["Value Date (DD/MM/YYYY)", "Transaction", "Ordering Party", "Remittance Information", "Original Amount",
               "Original Ccy", "Bank Rate USD per EUR", "Amount Credited USD"]
    if not spread_on:  # no bank rate and no USD credited to be tempted by
        bheader = bheader[:6]
        brows = [b[:6] for b in brows]
    write_csv(os.path.join(ws, "harbor_trust_incoming_wires_2026-01-01_to_2026-08-31.csv"),
              bheader, brows,
              preamble=["Harbor Trust - Business Checking x2291 - incoming international payments"], bom=True)

    erows = []
    day = date(2026, 1, 1)
    last = None
    while day <= date(2026, 8, 31):
        if gaps_on:
            if day.weekday() < 5:
                erows.append([day.isoformat(), day.strftime("%d %b %Y"), f"{rates[day]:.4f}" if day in rates else ""])
        else:  # every calendar day, carrying the last published rate: the lookup the controller asks for, done
            last = rates.get(day, last)
            if last is not None:
                erows.append([day.isoformat(), day.strftime("%d %b %Y"), f"{last:.4f}"])
        day += timedelta(days=1)
    write_csv(os.path.join(ws, "ecb_reference_rate_usd_2026.csv"), ["DATE", "TIME PERIOD", "US dollar/Euro (EXR.D.USD.EUR.SP00.A)"], erows,
              preamble=["Series key,EXR.D.USD.EUR.SP00.A", "Title,ECB reference exchange rate - US dollar per 1 euro - 2:15 pm (C.E.T.)",
                        "Note,No rate is published on TARGET closing days; those dates are blank" if gaps_on else
                        "Note,Weekends and TARGET closing days carry the last rate published before them", ""])

    write_text(os.path.join(ws, "note_from_miriam_controller.txt"), miriam_note(traps))

    eur = [x for x in inv if x["ccy"] == "EUR"]
    header = ["invoice", "eur_settled", "fx_gain_loss", "eur_open"]
    out = [[x["no"], f"{x['settled']:.2f}", f"{x['gain']:.2f}", f"{x['open']:.2f}"] for x in eur]
    write_csv(os.path.join(ref, "fx_results.csv"), header, out)
    write_csv(os.path.join(sol, "fx_results.csv"), header, out)
    write_json(os.path.join(ref, "notes.json"), {x["no"]: {"tag": x["tag"], "date": x["date"].isoformat(), "rate": x["rate"],
                                                           "amount": x["amount"], "gain": x["gain"], "open": x["open"]} for x in eur})
    by = d["by"]
    no = lambda t: by[t]["no"]
    rounding = "EUR converted at ECB rates, each side rounded to the cent per receipt as the controller's note states"
    spec = {
        "id": "fx-invoice-gains", "track": "desk", "category": "bookkeeping",
        "title": "Realized FX gain or loss on the euro invoices",
        "ask": ("The auditors want the FX gain or loss on each of our euro invoices from the first half. The invoice register, the "
                "bank's wire report and the ECB rates are in the folder, and Miriam's note says how she books it. Save it as fx_results.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": active_trap_text([
            f"rates come from the ECB file, which leaves weekends out and has blank rows on TARGET holidays: {no('weekend_invoice')} is "
            f"dated Saturday 14 February, {no('good_friday_invoice')} Good Friday 3 April and {no('easter_monday_receipt')} is paid "
            "on Easter Monday 6 April, all of which take the last rate published before, not the next one "
            "(check: fx gain or loss per invoice)",
            f"the bank's rate and USD credited include a spread of about a cent per euro, so gains taken from the bank columns are "
            "understated on every invoice; that difference is bank charges (check: fx gain or loss per invoice)",
            f"{no('partial')} is paid in two parts, the second on Easter Monday, and {no('partial_open')} only half, so each part "
            "is valued at its own receipt rate and the unpaid half stays open without FX (checks: fx gain or loss per invoice; euros still open)",
            f"one wire pays {no('two_in_one_a')} and {no('two_in_one_b')} together, with the split in German number format in the "
            "remittance line (check: fx gain or loss per invoice)",
            f"{no('short_fee')} arrived short by the dealer's bank charge; under the 25 euro rule it is settled in full and the FX "
            "is on the whole invoice, not the euros received (checks: fx gain or loss per invoice; euros still open)",
            "two dealers are billed in US dollars and their wires carry no FX; they are not euro invoices "
            "(checks: which invoices; row count)",
        ], TRAP_KEYS, traps),
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "fx_results.csv", "columns": header},
            {"type": "csv_set_equal", "name": "which invoices", "path": "fx_results.csv", "column": "invoice", "ref": "fx_results.csv",
             "normalize": ["alnum"]},
            {"type": "csv_row_count", "name": "row count", "path": "fx_results.csv", "equals_ref": "fx_results.csv"},
            {"type": "csv_values_match", "name": "fx gain or loss per invoice", "path": "fx_results.csv", "ref": "fx_results.csv",
             "key": "invoice", "columns": ["fx_gain_loss"], "numeric": True, "tolerance": 0.011, "rounding": rounding,
             "min_accuracy": 1.0, "must_match_keys": [no(t) for t in ("weekend_invoice", "good_friday_invoice", "easter_monday_receipt",
                                                                       "partial", "partial_open", "two_in_one_a", "two_in_one_b", "short_fee")]},
            {"type": "csv_values_match", "name": "euros still open", "path": "fx_results.csv", "ref": "fx_results.csv",
             "key": "invoice", "columns": ["eur_open"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0,
             "must_match_keys": [no(t) for t in ("partial", "partial_open", "short_fee", "unpaid")]},
        ],
    }
    if not traps.canonical:
        spec["variant"] = {"of": "fx-invoice-gains", "draw": seed, "traps_off": sorted(traps.off)}
    write_task_yaml(here, spec)
    print(f"seed={seed} eur invoices={len(eur)} receipts={len(receipts)}")
    for x in eur:
        print(f"  {x['no']} {x['tag']:22} {x['date']} rate={x['rate']} amt={x['amount']:>10.2f} settled={x['settled']:>10.2f} gain={x['gain']:>8.2f} open={x['open']:.2f}")


def write_naive(d: dict, out: str) -> None:
    """Gain from the bank: USD credited less euros received at the invoice rate (looked up forward on a missing date),
    open balance = invoice less euros received, USD invoices included at zero."""
    os.makedirs(out, exist_ok=True)
    rates = d["rates"]

    def fwd(day):
        while day not in rates:
            day += timedelta(days=1)
        return rates[day]
    rows = []
    for x in d["inv"]:
        got, gain = 0.0, 0.0
        for rc in d["receipts"]:
            for xx, eur, fee in rc["apps"]:
                if xx is x and not rc.get("usd"):
                    share = eur / rc["eur"]
                    got += eur
                    gain += rc["usd_credited"] * share - eur * fwd(x["date"])
        rows.append([x["no"], f"{got:.2f}", f"{gain:.2f}", f"{x['amount'] - got:.2f}"])
    write_csv(os.path.join(out, "fx_results.csv"), ["invoice", "eur_settled", "fx_gain_loss", "eur_open"], rows)


# --------------------------------------------------------------------------- per-trap mutants

def mutant_rows(d: dict, trap: str) -> list[list]:
    """fx_results.csv worked by the controller's rules except for the one `trap` the agent fell for."""
    if trap not in TRAP_KEYS:
        raise KeyError(trap)
    rates, ecb = d["rates"], d["ecb"]

    def rate(day: date) -> float:
        if trap == "rate_gaps":           # the next published rate for a missing date
            while day not in rates:
                day += timedelta(days=1)
            return rates[day]
        return ecb(day)

    eur = [x for x in d["inv"] if x["ccy"] == "EUR"]
    res = {x["no"]: [0.0, 0.0] for x in eur}   # settled, gain
    last_receipt = {}
    for rc in d["receipts"]:
        if rc.get("usd"):
            continue
        apps = rc["apps"]
        if trap == "two_in_one" and len(apps) > 1:   # '12.345,50' read as 12.3455: the first invoice gets cents, the second the rest
            (a, ea, fa), (b, eb, fb) = apps
            misread = r2(float(eu_money_str(ea).replace(",", "")))
            apps = [(a, misread, fa), (b, r2(rc["eur"] - misread), fb)]
        for x, amt, fee in apps:
            settle = amt if trap == "short_fee" else r2(amt + fee)   # short_fee: only the euros received are settled
            rr = rc["bank_rate"] if trap == "bank_spread" else rate(rc["date"])
            res[x["no"]][0] = r2(res[x["no"]][0] + settle)
            res[x["no"]][1] = r2(res[x["no"]][1] + r2(settle * rr) - r2(settle * rate(x["date"])))
            last_receipt[x["no"]] = rc["date"]
    if trap == "partial":                 # a part-paid invoice treated as settled in full at its latest receipt's rate
        for x in eur:
            if x["tag"] in ("partial", "partial_open"):
                res[x["no"]] = [x["amount"], r2(r2(x["amount"] * rate(last_receipt[x["no"]])) - r2(x["amount"] * rate(x["date"])))]
    rows = [[x["no"], f"{res[x['no']][0]:.2f}", f"{res[x['no']][1]:.2f}", f"{r2(x['amount'] - res[x['no']][0]):.2f}"] for x in eur]
    if trap == "usd_invoices":            # dollar invoices listed too, at zero FX
        rows += [[x["no"], f"{x['amount']:.2f}", "0.00", "0.00"] for x in d["inv"] if x["ccy"] == "USD"]
        rows.sort(key=lambda row: row[0])
    return rows


def write_mutant(d: dict, trap: str, out: str) -> None:
    os.makedirs(out, exist_ok=True)
    write_csv(os.path.join(out, "fx_results.csv"), ["invoice", "eur_settled", "fx_gain_loss", "eur_open"], mutant_rows(d, trap))


MUTANTS = {k: write_mutant for k in TRAP_KEYS}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    add_trap_args(ap)
    a = ap.parse_args()
    traps = parse_trap_args(a, TRAPS, MUTANTS, TRAP_KEYS)
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    # The acceptance loop always runs on the full task, so a variant or mutant shares the canonical draw.
    emit(a.seed * 1000 + attempt, a.naive, traps, a.out, a.mutant)
