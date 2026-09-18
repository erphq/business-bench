#!/usr/bin/env python3
"""tenant-ledger-balances: a manufactured-home community's August resident balances and the late fees the software skipped.

    python gen.py [--seed N] [--naive DIR]

Business: Pine Hollow is a 30-lot manufactured home community. Residents own their homes and rent the lot, and are
billed lot rent plus water/sewer and trash on the 1st. The property software's late-fee job did not run in August
after an update, so the manager needs every resident's balance at 31 August with the late fees worked out by hand
from the community rules: a grace period through the 5th, the received date rather than the posted date, payments to
the oldest balance first, 10% of the unpaid lot rent with a minimum, and move-outs charged only to the move-out day.

Traps (each caught by a check, see task.yaml):
  * a payment received on the 5th is on time and one received on the 6th is not        (check: late fee per lot)
  * mailed payments are posted days after they are received; the received date counts  (checks: late fee; balance)
  * payments go to the balance brought forward first, so a resident who paid exactly the rent on time still owes
    part of it after the 5th; the $15 minimum applies                                  (check: late fee per lot)
  * a partial payment by the 5th leaves 10% of the rest, not 10% of the rent            (check: late fee per lot)
  * water, sewer and trash left unpaid never earn a late fee                           (check: late fee per lot)
  * two move-outs were billed a full month; rent runs only through the move-out day    (checks: balance per lot; late fee)
  * a payment received on 31 August but posted in September counts for August; one received on 1 September does not
                                                                                          (check: balance per lot)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

D = Decimal
TRASH = D("24.00")
GRACE_END = date(2026, 8, 5)


def c2(x) -> Decimal:
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def cents(r, lo, hi) -> Decimal:
    return D(r.randint(int(lo * 100), int(hi * 100))) / 100


ROLES = ["on_5th", "on_6th", "mailed_posted_late", "partial", "prior_balance", "utilities_unpaid", "moveout_paid", "moveout_unpaid",
         "credit_forward", "received_sept", "received_aug31"]


def build(seed: int) -> dict:
    r = rng(seed)
    lots = [f"{row}-{n:02d}" for row in "ABC" for n in range(1, 11)]
    vacant = set(r.sample(lots, 4))
    occupied = [l for l in lots if l not in vacant]
    names = people(r, len(occupied))
    residents = []
    roles = ROLES + ["plain"] * (len(occupied) - len(ROLES))
    r.shuffle(roles)
    for lot, (f, l), role in zip(occupied, names, roles):
        rent = D(r.choice([545, 565, 585, 610, 635, 660]))
        water = cents(r, 38, 92)
        res = {"lot": lot, "name": f"{f} {l}", "rent": rent, "water": water, "role": role, "bf": D("0.00"), "move_out": None,
               "move_in": date(r.randint(2012, 2025), r.randint(1, 12), r.randint(1, 28)), "pays": []}
        full = rent + water + TRASH

        def p(amount, received, posted=None, method="Check"):
            res["pays"].append({"amount": c2(amount), "received": received, "posted": posted or received, "method": method})

        if role == "plain":
            p(full, date(2026, 8, r.randint(1, 4)), method=r.choice(["ACH", "Check", "Money order"]))
        elif role == "on_5th":
            p(full, GRACE_END, method="Drop box")
        elif role == "on_6th":
            p(full, date(2026, 8, 6), method="Check")
        elif role == "mailed_posted_late":
            p(full, date(2026, 8, r.randint(3, 4)), posted=date(2026, 8, r.randint(7, 10)), method="Mailed check")
        elif role == "partial":
            first = c2(rent * D(str(r.choice([0.5, 0.6, 0.45]))))
            p(first, date(2026, 8, r.randint(1, 4)), method="Money order")
            p(full - first, date(2026, 8, r.randint(15, 22)), method="Money order")
        elif role == "prior_balance":
            res["bf"] = cents(r, 42, 138)
            p(rent, date(2026, 8, r.randint(1, 3)), method="ACH")
        elif role == "utilities_unpaid":
            p(rent, date(2026, 8, r.randint(1, 4)), method="Check")
        elif role == "moveout_paid":
            res["move_out"] = date(2026, 8, r.randint(10, 17))
            p(full, date(2026, 8, 1), method="ACH")
        elif role == "moveout_unpaid":
            res["move_out"] = date(2026, 8, r.randint(19, 25))
        elif role == "credit_forward":
            res["bf"] = -cents(r, 45, 140)
            p(full + res["bf"], date(2026, 8, r.randint(1, 4)), method="Check")
        elif role == "received_sept":
            res["bf"] = D("0.00")
            p(full, date(2026, 9, 1), posted=date(2026, 9, 2), method="Drop box")
        elif role == "received_aug31":
            p(full, date(2026, 8, 31), posted=date(2026, 9, 2), method="Drop box")
        residents.append(res)

    # truth
    for res in residents:
        days = 31 if res["move_out"] is None else res["move_out"].day
        rent_due = c2(res["rent"] * days / 31)
        res["rent_due"] = rent_due
        if res["role"] == "moveout_unpaid":
            res["pays"].append({"amount": rent_due, "received": res["move_out"], "posted": res["move_out"], "method": "Cashier's check"})
        on_time = sum(x["amount"] for x in res["pays"] if x["received"] <= GRACE_END)
        # oldest first: balance brought forward, then lot rent, then utilities; a credit forward pays rent
        avail = on_time - res["bf"]
        unpaid_rent = max(D("0"), rent_due - max(D("0"), avail))
        fee = max(D("15.00"), c2(unpaid_rent * D("0.10"))) if unpaid_rent > 0 else D("0.00")
        received_aug = sum(x["amount"] for x in res["pays"] if x["received"] <= date(2026, 8, 31))
        res["fee"] = fee
        res["unpaid_rent"] = unpaid_rent
        res["balance"] = res["bf"] + rent_due + res["water"] + TRASH + fee - received_aug
    return {"residents": sorted(residents, key=lambda x: x["lot"]), "vacant": sorted(vacant)}


def acceptable(d: dict) -> bool:
    by = {x["role"]: x for x in d["residents"]}
    if by["prior_balance"]["fee"] != D("15.00") or by["prior_balance"]["unpaid_rent"] * D("0.10") >= 15:
        return False
    if by["partial"]["fee"] <= D("15.00"):
        return False
    if by["moveout_unpaid"]["fee"] <= D("15.00"):
        return False
    # proration moves the move-out figures by more than a dollar, and the numbers stay off the rent grid
    for k in ("moveout_paid", "moveout_unpaid"):
        x = by[k]
        if abs(x["rent"] - x["rent_due"]) < 50:
            return False
    if by["moveout_paid"]["balance"] >= 0:
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["lot", "resident", "late_fee", "balance"]
    if naive_dir:
        # posted dates, 10% of the full rent for anyone posted after the 5th, no proration, every payment in the export
        rows = []
        for x in d["residents"]:
            paid_by_5 = sum(p["amount"] for p in x["pays"] if p["posted"] <= GRACE_END and x["role"] != "moveout_unpaid")
            fee = c2(x["rent"] * D("0.10")) if paid_by_5 < x["rent"] + x["water"] + TRASH else D("0")
            paid = sum(p["amount"] for p in x["pays"] if x["role"] != "moveout_unpaid" or True)
            bal = x["bf"] + x["rent"] + x["water"] + TRASH + fee - paid
            rows.append([x["lot"], x["name"], f"{fee:.2f}", f"{bal:.2f}"])
        write_csv(os.path.join(naive_dir, "tenant_balances.csv"), header, rows)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 17)

    led = []
    for x in d["residents"]:
        if x["bf"] != 0:
            led.append([x["lot"], x["name"], "07/31/2026", "", "Balance Forward", "Balance at 07/31/2026",
                        f"{x['bf']:.2f}" if x["bf"] > 0 else "", f"{-x['bf']:.2f}" if x["bf"] < 0 else ""])
        led.append([x["lot"], x["name"], "08/01/2026", "", "Lot Rent", "Lot rent August 2026", f"{x['rent']:.2f}", ""])
        led.append([x["lot"], x["name"], "08/01/2026", "", "Water/Sewer", "Water/sewer - July meter read", f"{x['water']:.2f}", ""])
        led.append([x["lot"], x["name"], "08/01/2026", "", "Trash", "Trash service August", f"{TRASH:.2f}", ""])
        for p in x["pays"]:
            led.append([x["lot"], x["name"], p["posted"].strftime("%m/%d/%Y"), p["received"].strftime("%m/%d/%Y"), "Payment",
                        f"Payment - {p['method']}", "", f"{p['amount']:.2f}"])
    led.sort(key=lambda row: (row[0], row[2][6:] + row[2][:5], row[4] != "Balance Forward"))
    write_csv(os.path.join(ws, "parkledger_resident_ledger_2026-07-31_to_2026-09-03.csv"),
              ["Lot", "Resident", "Date Posted", "Date Received", "Type", "Description", "Charge", "Payment"], led,
              preamble=["ParkLedger - Resident ledger detail", "Pine Hollow Community | Posted 07/31/2026 - 09/03/2026",
                        "NOTE: automatic late fees disabled 08/01/2026 - 08/31/2026 (v6 upgrade)"], bom=True, crlf=True)

    roster = []
    for lot in sorted([x["lot"] for x in d["residents"]] + d["vacant"]):
        x = next((y for y in d["residents"] if y["lot"] == lot), None)
        if x is None:
            roster.append([lot, "", "", "", "", "Vacant"])
        else:
            roster.append([lot, x["name"], f"${x['rent']:,.2f}/mo", x["move_in"], x["move_out"] or "", "Moved out" if x["move_out"] else "Occupied"])
    write_xlsx(os.path.join(ws, "lot_roster_2026-09-01.xlsx"), {"Lots": {
        "merged_title": "Pine Hollow Community - lot roster",
        "header": ["Lot", "Resident", "Lot rent", "Move-in", "Move-out", "Status"], "rows": roster,
        "widths": {"B": 22, "C": 14, "D": 12, "E": 12}}}, creator="Office")

    write_text(os.path.join(ws, "community_rules_rent_section.txt"),
               "PINE HOLLOW COMMUNITY - RULES AND REGULATIONS (excerpt)\n\n"
               "Section 4. Rent, charges and fees\n\n"
               "4.1 Lot rent and utility charges (water/sewer and trash) are billed on the 1st of each month and are due that day.\n\n"
               "4.2 Grace period. Payments received on or before the 5th day of the month are on time. A payment counts on the day the\n"
               "    office receives it (in person, drop box, mail or ACH), not the day it is entered in the ledger.\n\n"
               "4.3 Application of payments. Payments are applied first to any balance carried from earlier months, then to the current\n"
               "    month's lot rent, then to utility charges. A credit carried from an earlier month counts as a payment received on the 1st.\n\n"
               "4.4 Late fee. If any of the month's lot rent is still unpaid at the end of the 5th, a late fee of 10% of the unpaid lot rent,\n"
               "    rounded to the cent, with a minimum of $15.00, is charged once for the month. Unpaid utility charges do not earn a late fee.\n\n"
               "4.5 Move-out. A resident who moves out during a month owes lot rent through the move-out date only: the monthly lot rent\n"
               "    times the days from the 1st through the move-out date, divided by the days in the month, rounded to the cent. Utility\n"
               "    charges for the month are owed in full. Security deposits are settled separately and are not part of the ledger.\n")

    write_email_thread(os.path.join(ws, "email_from_denise.txt"), [
        {"from": "Denise Moreau <office@pinehollowcommunity.com>", "to": "bookkeeper@pinehollowcommunity.com", "date": "Thu, 3 Sep 2026 17:20",
         "subject": "August balances - late fees did not run",
         "body": ("The ledger upgrade switched off automatic late fees for all of August, and the two move-outs were billed a full month "
                  "anyway. The owners want every resident's balance as of August 31 with the correct late fee included, following section 4 "
                  "of the rules.\n\n"
                  "Please send tenant_balances.csv with one row per resident who lived here in August (including the two who moved out): "
                  "lot, resident, late_fee and balance at August 31. Show a credit as a negative number.\n\nDenise")}])

    rows = [[x["lot"], x["name"], f"{x['fee']:.2f}", f"{x['balance']:.2f}"] for x in d["residents"]]
    for base in (ref, sol):
        write_csv(os.path.join(base, "tenant_balances.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {x["lot"]: {"role": x["role"], "rent_due": f"{x['rent_due']:.2f}", "unpaid_rent_after_5th":
                                                           f"{x['unpaid_rent']:.2f}"} for x in d["residents"]})
    by = {x["role"]: x for x in d["residents"]}
    L = lambda k: by[k]["lot"]
    write_task_yaml(HERE, {
        "id": "tenant-ledger-balances", "track": "desk", "category": "bookkeeping",
        "title": "August resident balances with late fees",
        "ask": "The late fees did not run in August and the owners want everyone's balance. Denise's email and the community rules explain it. Save it as tenant_balances.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"lot {L('on_5th')} paid in the drop box on 5 August, which is on time; lot {L('on_6th')} paid in full on the 6th and owes "
            "10% of its lot rent (check: late fee per lot)",
            f"lot {L('mailed_posted_late')}'s mailed check was received on {by['mailed_posted_late']['pays'][0]['received'].isoformat()} but "
            "posted days later; judging by the posted date charges a fee the rules do not allow (check: late fee per lot)",
            f"lot {L('prior_balance')} carried {by['prior_balance']['bf']:,.2f} from July and paid exactly the lot rent on time; the payment "
            f"clears July first, so {by['prior_balance']['unpaid_rent']:,.2f} of August rent is unpaid after the 5th and the $15.00 "
            "minimum applies (check: late fee per lot)",
            f"lot {L('partial')} paid part of its rent by the 5th and the rest later; the fee is 10% of the part still unpaid, not of the "
            "whole rent (check: late fee per lot)",
            f"lot {L('utilities_unpaid')} paid its lot rent on time but not water, sewer or trash, which never earn a late fee "
            "(checks: late fee per lot; balance per lot)",
            f"lots {L('moveout_paid')} and {L('moveout_unpaid')} moved out on {by['moveout_paid']['move_out'].isoformat()} and "
            f"{by['moveout_unpaid']['move_out'].isoformat()} but were billed a full month: {L('moveout_paid')} had prepaid and is owed a "
            f"credit, and {L('moveout_unpaid')} paid its prorated rent only on moving out, so its late fee is 10% of the prorated rent "
            "(checks: balance per lot; late fee per lot)",
            f"lot {L('received_aug31')}'s payment was received on 31 August and posted in September, so it counts for August, while lot "
            f"{L('received_sept')}'s was received on 1 September and does not; lot {L('credit_forward')} carries a July credit "
            "(check: balance per lot)",
            "the ledger export runs to 3 September under a three-line preamble with a BOM and CRLF endings, credits sit in the Payment "
            "column, and the roster writes rent as '$585.00/mo' and lists four vacant lots (check: balance per lot)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "tenant_balances.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every August resident", "path": "tenant_balances.csv", "column": "lot", "ref": "tenant_balances.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "tenant_balances.csv", "equals_ref": "tenant_balances.csv"},
            {"type": "csv_values_match", "name": "late fee per lot", "path": "tenant_balances.csv", "ref": "tenant_balances.csv", "key": "lot",
             "columns": ["late_fee"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [L(k) for k in ("on_5th", "on_6th", "mailed_posted_late", "prior_balance", "partial", "utilities_unpaid",
                                                 "moveout_unpaid", "received_aug31")]},
            {"type": "csv_values_match", "name": "balance per lot", "path": "tenant_balances.csv", "ref": "tenant_balances.csv", "key": "lot",
             "columns": ["balance"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [L(k) for k in ("moveout_paid", "moveout_unpaid", "credit_forward", "received_sept", "received_aug31",
                                                 "utilities_unpaid", "prior_balance")]},
        ],
    })
    print(f"seed={seed} residents={len(d['residents'])} " + " ".join(f"{x['lot']}:{x['role']}:{x['fee']}/{x['balance']}" for x in d["residents"] if x["role"] != "plain"))


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
