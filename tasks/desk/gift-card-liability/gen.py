#!/usr/bin/env python3
"""gift-card-liability: outstanding gift card liability per card at 31 August 2026 for a day spa.

    python gen.py [--seed N] [--naive DIR]

Business: a day spa that sold gift cards on an old salon system until March 2023 and on a new POS since; the
accountant wants the liability schedule per card for the year-end file.

Traps (each caught by a check, see task.yaml):
  * a redemption's Ticket Total is the whole bill; only Card Amount came off the card     (check: liability per card)
  * reloads add money and restart the five-year clock; redemptions and reversals do not   (checks: liability; status)
  * cards expire five years after the last load, and the legacy file holds the load dates; the
    2023-04-01 Balance Import rows are not loads                                            (checks: liability; status)
  * the Balance Import rows repeat the legacy balances; adding the legacy file on top doubles them (check: liability)
  * promo cards (Promo Issue, or an Activation on a $0.00 ticket) and a voided activation are not sold cards
                                                                                          (check: every card we sold, once)
  * a June balance report sits in the folder and is stale                                  (check: liability per card)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

AS_OF = date(2026, 8, 31)
MIGRATION = date(2023, 4, 1)
SERVICES = [("Swedish massage 60", 110.00), ("Deep tissue 90", 165.00), ("Signature facial", 135.00), ("Hot stone 75", 145.00),
            ("Mani-pedi", 78.00), ("Couples massage", 240.00), ("Brow and lash tint", 65.00), ("Body scrub", 95.00),
            ("Hydrafacial", 185.00), ("Reflexology 45", 72.00)]
VALUES = [50.0, 75.0, 100.0, 150.0, 200.0, 250.0]


def five_years(d: date) -> date:
    try:
        return d.replace(year=d.year + 5)
    except ValueError:
        return d.replace(year=d.year + 5, day=28)


def build(seed: int) -> dict:
    r = rng(seed)
    used = set()

    def last4():
        while True:
            x = r.randint(1102, 8987)
            if x not in used and x % 1111:
                used.add(x)
                return str(x)

    def t(d):  # a time on a day
        return datetime(d.year, d.month, d.day, r.randint(9, 19), r.choice([0, 5, 12, 20, 34, 41, 48, 55]))

    staff = [f for f, _ in people(r, 6)]
    cards = []   # {last4, kind: legacy|new|promo|void, events: [...], legacy: {...}}

    def redeem(card, when, balance, want_split=False):
        svc, price = r.choice(SERVICES)
        if want_split:
            price = max(price, balance + r.choice([35.0, 60.0, 85.0]))
        amt = round(min(balance, price), 2)
        card["events"].append({"type": "Redemption", "at": t(when), "ticket_total": price, "card_amount": amt,
                               "note": (f"split: card {amt:.2f} / Visa {price - amt:.2f}" if price > amt else svc)})
        return round(balance - amt, 2)

    # ---- legacy cards (old system until 2023-03-31, imported on 2023-04-01) ----
    legacy_specs = [
        ("expired_untouched", date(2020, 11, 6), None, None),
        ("expired_after_redemption", date(2021, 5, 20), None, "redeem_2024"),
        ("legacy_reload", date(2020, 9, 18), date(2022, 2, 11), None),
        ("pos_reload", date(2021, 2, 9), None, "reload_2025"),
        ("boundary", date(2021, 9, 14), None, None),
        ("plain_active", date(2022, 6, 3), None, None),
    ]
    for i in range(8):
        legacy_specs.append((f"legacy_{i}", date(2021, 10, 1) + timedelta(days=r.randint(0, 520)), None,
                             r.choice([None, "redeem_some", "redeem_some", "redeem_all"])))
    for i in range(2):
        legacy_specs.append((f"legacy_old_{i}", date(2020, 3, 1) + timedelta(days=r.randint(0, 300)), None, None))
    for tag, sold, reload, later in legacy_specs:
        orig = r.choice(VALUES[1:])
        bal_mig = round(orig - r.choice([0.0, 0.0, 35.0, 55.0, 72.0]) if orig > 100 else orig, 2)
        if tag == "expired_after_redemption":
            orig, bal_mig = 200.0, 150.0
        card = {"last4": last4(), "kind": "legacy", "tag": tag, "sold": sold, "legacy_reload": reload, "orig": orig,
                "bal_mig": bal_mig, "purchaser": " ".join(person(r)), "events": []}
        card["events"].append({"type": "Balance Import", "at": datetime(2023, 4, 1, 6, 0), "ticket_total": 0.0,
                               "card_amount": bal_mig, "note": "Oakleaf SpaBook migration"})
        bal = bal_mig
        if later == "redeem_2024":
            bal = redeem(card, date(2024, 3, 9), bal)
            card["events"][-1].update({"ticket_total": 110.0, "card_amount": 60.0, "note": "split: card 60.00 / cash 50.00"})
            bal = 90.0
        elif later == "reload_2025":
            bal = redeem(card, date(2023, 8, 19), bal)
            card["events"].append({"type": "Reload", "at": t(date(2025, 10, 4)), "ticket_total": 100.0, "card_amount": 100.0, "note": "reload"})
            bal = round(bal + 100.0, 2)
            bal = redeem(card, date(2026, 2, 14), bal)
        elif later == "redeem_some":
            d0 = MIGRATION + timedelta(days=r.randint(30, 700))
            bal = redeem(card, d0, bal)
        elif later == "redeem_all":
            d0 = MIGRATION + timedelta(days=r.randint(30, 400))
            while bal > 0:
                bal = redeem(card, d0, bal, want_split=True)
                d0 += timedelta(days=r.randint(20, 90))
        card["balance_before_expiry"] = bal
        cards.append(card)

    # ---- new POS cards ----
    forced = ["split_tender", "partial_twice", "reversal", "june_activity", "reload_new", "unused"]
    for i in range(30):
        tag = forced[i] if i < len(forced) else "new"
        sold = MIGRATION + timedelta(days=r.randint(3, (AS_OF - MIGRATION).days - 75))
        if tag == "june_activity":
            sold = date(2025, 11, 22)
        value = r.choice(VALUES)
        card = {"last4": last4(), "kind": "new", "tag": tag, "sold": sold, "events": []}
        card["events"].append({"type": "Activation", "at": t(sold), "ticket_total": value, "card_amount": value,
                               "note": r.choice(["gift purchase", "front desk", "online order", "holiday sale"])})
        bal = value
        if tag == "split_tender":
            bal = redeem(card, sold + timedelta(days=40), bal, want_split=True)
        elif tag == "partial_twice":
            card["events"][0].update({"ticket_total": 250.0, "card_amount": 250.0}); bal = 250.0
            for k in range(2):
                bal = redeem(card, sold + timedelta(days=30 + 60 * k), bal)
        elif tag == "reversal":
            card["events"][0].update({"ticket_total": 200.0, "card_amount": 200.0}); bal = 200.0
            bal = redeem(card, sold + timedelta(days=21), bal)
            back = card["events"][-1]["card_amount"]
            card["events"].append({"type": "Redemption Reversal", "at": t(sold + timedelta(days=23)), "ticket_total": 0.0,
                                   "card_amount": back, "note": "appointment cancelled - returned to card"})
            bal = round(bal + back, 2)
        elif tag == "june_activity":
            card["events"][0].update({"ticket_total": 250.0, "card_amount": 250.0}); bal = 250.0
            bal = redeem(card, date(2026, 2, 2), bal)
            bal = redeem(card, date(2026, 7, 18), bal)
        elif tag == "reload_new":
            bal = redeem(card, sold + timedelta(days=15), bal)
            card["events"].append({"type": "Reload", "at": t(sold + timedelta(days=50)), "ticket_total": 75.0, "card_amount": 75.0, "note": "reload"})
            bal = round(bal + 75.0, 2)
        elif tag == "new":
            k = r.choice([0, 1, 1, 2, 3])
            d0 = sold
            for _ in range(k):
                d0 = d0 + timedelta(days=r.randint(10, 160))
                if d0 >= AS_OF or bal <= 0:
                    break
                bal = redeem(card, d0, bal, want_split=r.random() < 0.3)
        card["balance_before_expiry"] = bal
        cards.append(card)

    # ---- promo cards and a voided activation (never sold) ----
    for i in range(5):
        d0 = date(2025, 11, 28) + timedelta(days=r.randint(0, 30))
        card = {"last4": last4(), "kind": "promo", "tag": "promo", "sold": d0, "events": []}
        if i < 3:
            card["events"].append({"type": "Promo Issue", "at": t(d0), "ticket_total": 0.0, "card_amount": 25.0, "note": "Black Friday bonus card"})
        else:
            card["events"].append({"type": "Activation", "at": t(d0), "ticket_total": 0.0, "card_amount": 25.0, "note": "promo - buy $200 get $25"})
        if i % 2 == 0:
            card["events"].append({"type": "Redemption", "at": t(d0 + timedelta(days=20)), "ticket_total": 95.0, "card_amount": 25.0,
                                   "note": "split: card 25.00 / Visa 70.00"})
        cards.append(card)
    d0 = date(2026, 5, 8)
    void = {"last4": last4(), "kind": "void", "tag": "void", "sold": d0, "events": [
        {"type": "Activation", "at": datetime(2026, 5, 8, 11, 14), "ticket_total": 150.0, "card_amount": 150.0, "note": "front desk"},
        {"type": "Void", "at": datetime(2026, 5, 8, 11, 31), "ticket_total": -150.0, "card_amount": -150.0, "note": "keyed wrong card - refunded to Visa"}]}
    cards.append(void)

    # ---- truth ----
    for c in cards:
        if c["kind"] in ("promo", "void"):
            continue
        loads = [e["at"].date() for e in c["events"] if e["type"] in ("Activation", "Reload")]
        if c["kind"] == "legacy":
            loads += [c["sold"]] + ([c["legacy_reload"]] if c["legacy_reload"] else [])
        last_load = max(loads)
        c["last_load"] = last_load
        c["expires"] = five_years(last_load)
        bal = c["balance_before_expiry"]
        if bal <= 0:
            c["status"], c["liability"] = "redeemed", 0.0
        elif c["expires"] <= AS_OF:
            c["status"], c["liability"] = "expired", 0.0
        else:
            c["status"], c["liability"] = "active", round(bal, 2)
    return {"cards": cards, "staff": staff}


def acceptable(d: dict) -> bool:
    by = {c["tag"]: c for c in d["cards"]}
    if by["expired_untouched"]["status"] != "expired" or by["expired_after_redemption"]["status"] != "expired":
        return False
    if by["legacy_reload"]["status"] != "active" or by["pos_reload"]["status"] != "active" or by["boundary"]["status"] != "active":
        return False
    if by["split_tender"]["status"] != "redeemed" or by["june_activity"]["liability"] <= 0:
        return False
    if by["partial_twice"]["liability"] <= 0 or by["reversal"]["liability"] <= 0 or by["pos_reload"]["liability"] <= 0:
        return False
    for c in d["cards"]:   # nothing redeemed after it expired
        if c.get("expires"):
            if any(e["type"] == "Redemption" and e["at"].date() >= c["expires"] for e in c["events"]):
                return False
    if sum(1 for c in d["cards"] if c.get("status") == "expired") < 3:
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    cards = d["cards"]
    r = rng(seed + 7)

    # POS transaction export
    ev = []
    for c in cards:
        for e in c["events"]:
            ev.append((e["at"], c["last4"], e))
    ev.sort(key=lambda x: (x[0], x[1]))
    rows = []
    for i, (at, l4, e) in enumerate(ev):
        rows.append([at.strftime("%Y-%m-%d %H:%M"), f"T{604100 + i * 3}", l4, e["type"], money_str(e["ticket_total"], 1),
                     money_str(e["card_amount"], 1), e["note"], "system" if e["type"] == "Balance Import" else r.choice(d["staff"])])
    write_csv(os.path.join(ws, "cedarline_giftcard_activity_2023-04-01_to_2026-08-31.csv"),
              ["Date/Time", "Ticket", "Card Last 4", "Type", "Ticket Total", "Card Amount", "Note", "Employee"], rows,
              preamble=["Cedarline POS - Gift Card Activity Detail", "Location: Lantern Row Day Spa | 04/01/2023 - 08/31/2026"])

    # legacy balances at migration
    lrows = []
    for c in sorted([c for c in cards if c["kind"] == "legacy"], key=lambda c: c["sold"]):
        lrows.append([c["last4"], c["purchaser"], c["sold"].strftime("%m/%d/%Y"),
                      c["legacy_reload"].strftime("%m/%d/%Y") if c["legacy_reload"] else "", c["orig"], c["bal_mig"]])
    write_xlsx(os.path.join(ws, "oakleaf_spabook_giftcards_at_migration.xlsx"), {"Open cards": {
        "merged_title": "Oakleaf SpaBook - open gift certificates exported for Cedarline migration",
        "preamble": [["Balances as of close 03/31/2023. Cards with no balance were not migrated."]],
        "header": ["Card #", "Purchaser", "Date Sold", "Last Reload", "Original Amount", "Balance"],
        "rows": lrows, "number_formats": {"E": "#,##0.00", "F": "#,##0.00"}, "widths": {"B": 22, "C": 12, "D": 12}}},
        creator="Oakleaf SpaBook")

    # stale June report (Cedarline's own balance report, which ignores expiry and lists promo cards)
    june = []
    cut = datetime(2026, 6, 30, 23, 59)
    for c in cards:
        if c["kind"] == "void":
            continue
        bal = 0.0
        for e in c["events"]:
            if e["at"] > cut:
                continue
            if e["type"] in ("Redemption",):
                bal -= e["card_amount"]
            else:
                bal += e["card_amount"]
        if round(bal, 2) > 0:
            june.append([c["last4"], f"{bal:.2f}"])
    june.sort()
    write_csv(os.path.join(ws, "cedarline_giftcard_balances_2026-06-30.csv"), ["Card Last 4", "Balance"], june,
              preamble=["Gift card balances as of 06/30/2026"])

    write_text(os.path.join(ws, "gift_card_terms.md"), """# Lantern Row Day Spa gift cards - terms (printed on the card carrier)

- Gift cards never lose value while they are active and carry no fees.
- A purchased gift card expires **five years after the date money was last loaded onto it** - the original purchase
  or the most recent reload, whichever is later. Using the card does not extend it.
- Promotional bonus cards (for example "buy $200, get a $25 bonus card") have no cash value, are not for sale and
  expire 90 days after issue.
- Cards cannot be redeemed for cash.
""")
    write_email_thread(os.path.join(ws, "email_from_hannah_cpa.txt"), [
        {"from": "Hannah Reyes <hannah@reyesbooks.cpa>", "to": "Olivia <olivia@lanternrowspa.com>", "date": "Tue, 1 Sep 2026 16:05",
         "subject": "gift card liability for the year-end file",
         "body": ("Hi Olivia,\n\nFor the August 31 year end I need the gift card liability card by card. A few things from last year:\n\n"
                  "- The liability is only what customers paid for and have not used. The bonus cards you give away in promotions "
                  "are not a liability. Cedarline logs them as Promo Issue, although the front desk sometimes rang them up as an "
                  "Activation on a $0.00 ticket instead.\n"
                  "- When a card only covers part of a bill, Cedarline puts the whole bill in Ticket Total. What actually came off "
                  "the card is the Card Amount.\n"
                  "- The Balance Import lines on 1 April 2023 are the Oakleaf SpaBook balances being carried over, not new money. The dates "
                  "those cards were sold and last reloaded are only in the Oakleaf SpaBook export.\n"
                  "- A card whose five years have run out (see the terms) comes off the liability; I book that balance as breakage. "
                  "A card that was used up is just zero.\n"
                  "- Cedarline's own balance report is not good enough, it ignores expiry.\n\n"
                  "Please send a CSV with one line per card you sold: card_last4, liability (what you still owe on it at 31 August), "
                  "and status - active, redeemed or expired.\n\nThanks,\nHannah")}])

    # reference and solution
    sold = sorted([c for c in cards if c["kind"] in ("legacy", "new")], key=lambda c: c["last4"])
    header = ["card_last4", "liability", "status"]
    out = [[c["last4"], f"{c['liability']:.2f}", c["status"]] for c in sold]
    write_csv(os.path.join(ref, "gift_cards.csv"), header, out)
    write_csv(os.path.join(sol, "gift_cards.csv"), header, out)
    detail = [[c["last4"], c["kind"], c["tag"], c["sold"].isoformat(), c["last_load"].isoformat(), c["expires"].isoformat(),
               f"{c['balance_before_expiry']:.2f}", f"{c['liability']:.2f}", c["status"]] for c in sold]
    write_csv(os.path.join(ref, "card_detail.csv"), ["card_last4", "kind", "tag", "sold", "last_load", "expires",
                                                     "balance_before_expiry", "liability", "status"], detail)
    total = round(sum(c["liability"] for c in sold), 2)
    write_json(os.path.join(ref, "notes.json"), {"as_of": AS_OF.isoformat(), "total_liability": total,
                                                  "breakage": round(sum(c["balance_before_expiry"] for c in sold if c["status"] == "expired"), 2),
                                                  "promo_cards": [c["last4"] for c in cards if c["kind"] == "promo"],
                                                  "void_card": [c["last4"] for c in cards if c["kind"] == "void"]})
    by = {c["tag"]: c for c in cards}
    lk = lambda tag: by[tag]["last4"]
    liability_keys = [lk(x) for x in ("expired_after_redemption", "pos_reload", "legacy_reload", "boundary", "plain_active",
                                      "split_tender", "partial_twice", "reversal", "june_activity", "reload_new")]
    status_keys = [lk(x) for x in ("expired_untouched", "expired_after_redemption", "legacy_reload", "pos_reload", "boundary", "split_tender")]
    promo = [c["last4"] for c in cards if c["kind"] in ("promo", "void")]
    write_task_yaml(HERE, {
        "id": "gift-card-liability", "track": "desk", "category": "bookkeeping",
        "title": "Gift card liability per card at year end",
        "ask": ("Hannah needs our gift card liability as of August 31 for the year-end file. Everything from the old Oakleaf SpaBook "
                "system and Cedarline is in the folder, along with her email. Save it as gift_cards.csv.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            f"a redemption's Ticket Total is the whole bill while Card Amount is what came off the card; card {lk('split_tender')} "
            "paid part of a bigger bill and is used up, and subtracting Ticket Total drives several cards negative "
            "(check: liability per card)",
            f"expiry runs five years from the last load, and for migrated cards the sale and reload dates exist only in the "
            f"Oakleaf SpaBook workbook: {lk('expired_untouched')} and {lk('expired_after_redemption')} have expired (the second after a "
            f"2024 partial redemption, which does not restart the clock), {lk('legacy_reload')} was reloaded in Oakleaf SpaBook in 2022 "
            f"and {lk('pos_reload')} in Cedarline in 2025 so both are active, and {lk('boundary')} was sold 14 September 2021 "
            "and is still active on 31 August (checks: liability per card; card status)",
            "the 2023-04-01 Balance Import rows carry the Oakleaf SpaBook balances; treating them as loads means nothing ever expires, "
            "and adding the Oakleaf SpaBook Balance column on top doubles every migrated card (checks: liability per card; card status)",
            f"promo bonus cards are logged as Promo Issue or as an Activation on a $0.00 ticket, and card {by['void']['last4']} "
            "was activated and voided the same morning; none of them were sold (check: every card we sold, once)",
            f"a redemption reversal puts money back on {lk('reversal')} without being a load (check: liability per card)",
            f"Cedarline's June balance report is stale and ignores expiry; {lk('june_activity')} was used again in July "
            "(check: liability per card)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "schedule columns", "path": "gift_cards.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every card we sold, once", "path": "gift_cards.csv", "column": "card_last4",
             "ref": "gift_cards.csv", "normalize": ["digits"]},
            {"type": "csv_row_count", "name": "row count", "path": "gift_cards.csv", "equals_ref": "gift_cards.csv"},
            {"type": "csv_values_match", "name": "liability per card", "path": "gift_cards.csv", "ref": "gift_cards.csv",
             "key": "card_last4", "columns": ["liability"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0,
             "must_match_keys": liability_keys},
            {"type": "csv_values_match", "name": "card status", "path": "gift_cards.csv", "ref": "gift_cards.csv",
             "key": "card_last4", "columns": ["status"], "min_accuracy": 1.0, "must_match_keys": status_keys},
            {"type": "text_not_contains", "name": "promo and voided cards left out", "path": "gift_cards.csv", "phrases": promo},
        ],
    })
    print(f"seed={seed} cards sold={len(sold)} total liability={total}")
    for c in sold:
        if c["tag"] not in ("new",) and not c["tag"].startswith("legacy_"):
            print(" ", c["last4"], c["tag"], c["last_load"], c["expires"], c["balance_before_expiry"], c["liability"], c["status"])


def write_naive(d: dict, out: str) -> None:
    """Every card in the export, balance = Oakleaf SpaBook balance + every Cedarline line with Redemptions at Ticket Total
    subtracted, no expiry, status active unless zero."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for c in sorted(d["cards"], key=lambda c: c["last4"]):
        bal = c.get("bal_mig", 0.0)
        for e in c["events"]:
            bal += -e["ticket_total"] if e["type"] == "Redemption" else e["card_amount"]
        rows.append([c["last4"], f"{max(bal, 0):.2f}", "active" if bal > 0 else "redeemed"])
    write_csv(os.path.join(out, "gift_cards.csv"), ["card_last4", "liability", "status"], rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(300):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
