#!/usr/bin/env python3
"""fundraising-appeal: a land trust's campaign notes, the donor database's gift export, the matching foundation's
letter and last year's appeal become this fall's appeal letter with the right figures.

    python gen.py [--seed N]

Business: a small regional land trust raising money to buy and protect a farm. The development director keeps
running notes; the executive director wants the fall appeal letter drafted from them.

Traps (each caught by a check, see task.yaml):
  * the notes start with a $450,000 goal; a later entry says the board raised it to $525,000 after the appraisal
                                                                     (checks: campaign figures; outdated figures absent)
  * raised so far comes from the gift export, not the notes' stale August figure: campaign fund only, pledges out
    until paid (pledge payments in), a bounced check and a refunded duplicate card charge out, general-fund gifts out
                                                                     (check: campaign figures)
  * what is left to raise is the new goal less the raised figure    (check: campaign figures)
  * the notes say the match runs through December 31; the foundation's letter says gifts received by November 30
                                                                     (check: match amount and deadline)
  * last year's appeal is in the folder with its own goal, raised figure, match and deadline  (check: outdated figures absent)
  * the export has a report preamble, a BOM, CRLF endings and amounts as "$1,250.00" text  (check: campaign figures)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
from decimal import Decimal
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

ORG = "Low Meadow Land Trust"
DOMAIN = "lowmeadowlandtrust.org"
OLD_GOAL = 450000
GOAL = 525000
MATCH = 50000
MATCH_END = date(2026, 11, 30)
NOTES_MATCH_END = date(2026, 12, 31)
EXPORT = date(2026, 9, 10)


def build(seed: int) -> dict:
    r = rng(seed * 37 + 17)
    donors, seen = [], set()
    while len(donors) < 70:
        f, l = person(r)
        if (f, l) in seen:
            continue
        seen.add((f, l))
        donors.append({"id": f"D{r.randint(10000, 99999)}", "name": f"{f} {l}", "first": f, "last": l})
    ids = set()
    def gid():
        while True:
            g = r.randint(40000, 49999)
            if g not in ids:
                ids.add(g); return f"G-{g}"
    gifts = []
    start = date(2026, 6, 3)
    def add(donor, day, amount, fund, gtype, status="Posted", note=""):
        gifts.append(dict(id=gid(), donor=donor, day=day, amount=Decimal(str(amount)), fund=fund, type=gtype, status=status, note=note))
    # campaign gifts
    add({"id": "D00417", "name": "Whitcomb Family Foundation", "first": "", "last": ""}, date(2026, 6, 18), 100000, "HATCH", "Check", note="Lead gift")
    for dn in r.sample(donors, 4):
        add(dn, day_in(r, start, EXPORT), r.choice([10000, 15000, 20000, 25000]), "HATCH", r.choice(["Check", "Stock"]), note="Major gift")
    for dn in donors[:48]:
        add(dn, day_in(r, start, EXPORT), money(r, 50, 2500, cents=r.random() < 0.3), "HATCH", r.choice(["Credit Card", "Check", "Credit Card", "Online"]))
    # general fund gifts (not campaign)
    for dn in r.sample(donors, 22):
        add(dn, day_in(r, start, EXPORT), money(r, 25, 1500, cents=r.random() < 0.3), "GEN", r.choice(["Credit Card", "Check", "Online"]))
    # pledges and pledge payments
    pledgers = r.sample(donors[48:], 4)
    for dn in pledgers:
        total = r.choice([5000, 6000, 10000, 12000])
        add(dn, day_in(r, start, date(2026, 7, 15)), total, "HATCH", "Pledge", note="3 annual installments" if total >= 10000 else "2 installments")
        add(dn, day_in(r, date(2026, 7, 16), EXPORT), total // (3 if total >= 10000 else 2), "HATCH", "Pledge Payment", note="Installment 1")
    # bounced check and its replacement
    bounce = donors[5]
    bamt = r.choice([750, 1000, 1200])
    add(bounce, date(2026, 7, 9), bamt, "HATCH", "Check", status="Returned", note="NSF - returned by bank 7/16")
    add(bounce, date(2026, 7, 21), bamt, "HATCH", "Credit Card", note="Replaces returned check")
    # duplicate card charge refunded
    dup = donors[9]
    damt = money(r, 150, 600, cents=False)
    add(dup, date(2026, 8, 12), damt, "HATCH", "Online")
    add(dup, date(2026, 8, 12), damt, "HATCH", "Online", status="Refunded", note="Duplicate charge - refunded 8/13")
    r.shuffle(gifts)
    gifts.sort(key=lambda g: g["day"])
    counted = lambda g: g["fund"] == "HATCH" and g["type"] != "Pledge" and g["status"] == "Posted"
    raised = sum((g["amount"] for g in gifts if counted(g)), Decimal("0"))
    naive = {
        "all_rows": sum((g["amount"] for g in gifts), Decimal("0")),
        "with_pledges": raised + sum((g["amount"] for g in gifts if g["fund"] == "HATCH" and g["type"] == "Pledge"), Decimal("0")),
        "with_returned": raised + sum((g["amount"] for g in gifts if g["fund"] == "HATCH" and g["status"] != "Posted"), Decimal("0")),
        "with_gen": raised + sum((g["amount"] for g in gifts if g["fund"] == "GEN"), Decimal("0")),
        "no_pledge_payments": raised - sum((g["amount"] for g in gifts if g["type"] == "Pledge Payment"), Decimal("0")),
    }
    remaining = Decimal(GOAL) - raised
    # the notes' stale figure: the August board report counted pledges at face value
    aug = sum((g["amount"] for g in gifts if g["fund"] == "HATCH" and g["status"] == "Posted" and g["type"] != "Pledge Payment" and g["day"] <= date(2026, 8, 31)), Decimal("0"))
    stale_note = int((aug + 999) // 1000) * 1000
    stale = {"old_goal_left": Decimal(OLD_GOAL) - raised}
    ppl = people(r, 4)
    P = {k: f"{f} {l}" for k, (f, l) in zip(["ed", "dev", "foundation", "board"], ppl)}
    return dict(gifts=gifts, raised=raised, remaining=remaining, naive=naive, stale=stale, P=P, stale_note=stale_note)


def usd(x) -> str:
    x = Decimal(x)
    return f"${x:,.2f}" if x != x.to_integral() else f"${int(x):,}"


def emit(seed: int) -> None:
    d = build(seed)
    P = d["P"]
    ws, ref, sol = task_dirs(HERE)
    rows = [[g["id"], g["donor"]["id"], g["donor"]["name"], g["day"].strftime("%m/%d/%Y"), money_str(float(g["amount"]), 1), g["fund"], g["type"], g["status"], g["note"]]
            for g in d["gifts"]]
    write_csv(os.path.join(ws, "gifts_export_2026-09-10.csv"), ["Gift ID", "Donor ID", "Donor Name", "Gift Date", "Amount", "Fund Code", "Gift Type", "Status", "Notes"], rows,
              preamble=[f"{ORG} - Gift Detail Report", f"Gift dates 06/01/2026 to {EXPORT.strftime('%m/%d/%Y')}; all funds; all statuses", ""], bom=True, crlf=True)

    raised = d["raised"]
    write_text(os.path.join(ws, "campaign_notes_hatch_farm.md"),
        f"# Hatch Farm campaign - running notes\n\n_{P['dev']}, development director_\n\n"
        "Fund codes in the database: HATCH = Hatch Farm campaign, GEN = general operating.\n\n"
        "## June 3\n\nKickoff. Board approved a campaign to buy and protect the 212-acre Hatch Farm on Cold Spring Road. "
        f"Goal: ${OLD_GOAL:,} (purchase price estimate). Lead gift of $100,000 from the Whitcomb Family Foundation expected this month.\n\n"
        "## July 22\n\nThe appraisal came in higher than the estimate. The board voted to raise the campaign goal to "
        f"${GOAL:,} to cover the purchase, closing costs and a stewardship endowment for the land.\n\n"
        "## August 30\n\nGood news: the Osei Family Foundation will match new campaign gifts dollar for dollar up to "
        f"${MATCH:,}, through December 31. Formal letter to follow.\n\n"
        f"## September 8\n\nFall appeal planning. Raised so far is about ${d['stale_note']:,} as of the August 31 board report.\n\n"
        "How we count 'raised so far' for anything public: gifts actually received for the HATCH fund (cash, checks, cards, online "
        "gifts and stock at its value when received). Pledges don't count until they're paid; each pledge payment counts when it comes in. "
        "Returned checks and refunded charges don't count. General fund gifts are not campaign money.\n\n"
        f"The appeal letter goes to everyone who has given to us before, signed by {P['ed']}. It should tell people the goal, how much "
        "we've raised so far and how much is left to raise, and explain the match and its deadline so people give in time. Use exact dollar "
        "figures from the database as of the latest export, not rounded ones; donors notice when our numbers don't add up.\n")

    write_pdf_document(os.path.join(ws, "osei_foundation_match_letter.pdf"), [
        ("title", "Osei Family Foundation"),
        ("small", "118 Harbor Street, Portland, ME 04101"),
        ("spacer", 10),
        ("p", "September 4, 2026"),
        ("spacer", 6),
        ("p", f"{P['ed']}<br/>Executive Director<br/>{ORG}"),
        ("spacer", 8),
        ("p", f"Dear {P['ed'].split()[0]},"),
        ("p", f"I am pleased to confirm that the Board of the Osei Family Foundation has approved a challenge grant in support of the Hatch Farm campaign. "
              f"The Foundation will match, dollar for dollar, gifts received by {ORG} for the Hatch Farm campaign between September 1, 2026 and "
              f"November 30, 2026, up to a total match of ${MATCH:,}."),
        ("p", "Gifts received after November 30, 2026, pledges not paid by that date, and gifts from foundations or government sources are not "
              "eligible for the match. Please send us a list of eligible gifts by December 15, 2026, and we will release the matching funds within 30 days."),
        ("p", "We are proud to support the permanent protection of Hatch Farm."),
        ("spacer", 8),
        ("p", f"Sincerely,<br/><br/>{P['foundation']}<br/>President"),
    ], font="Times-Roman", base_size=11)

    write_text(os.path.join(ws, "appeal_letter_2025_yearend.md"),
        f"{ORG}\n\nNovember 2025\n\nDear Friend of the Land,\n\n"
        "This year you helped us open the Birch Hollow Trail, and we are so close to finishing the boardwalk across the wetland. "
        "So far we've raised $182,400 of our $240,000 goal.\n\n"
        "Thanks to the Carver Fund, every gift made by December 31, 2025 will be matched up to $25,000. That means your $100 becomes $200 "
        "for the trail.\n\n"
        "Please give today using the enclosed envelope or at lowmeadowlandtrust.org/give.\n\n"
        f"With gratitude,\n\n{P['ed']}\nExecutive Director\n")

    facts = {"goal": GOAL, "old_goal": OLD_GOAL, "raised": float(raised), "remaining": float(d["remaining"]), "match": MATCH,
             "match_end": MATCH_END.isoformat(), "notes_match_end": NOTES_MATCH_END.isoformat(),
             "naive": {k: float(v) for k, v in d["naive"].items()}}
    write_json(os.path.join(ref, "facts.json"), facts)
    letter = (f"{ORG}\n\nSeptember 2026\n\nDear Friend of the Land,\n\n"
              "For generations Hatch Farm has been a patchwork of hayfields, hedgerows and wet meadow along Cold Spring Road. "
              f"This year we have the chance to buy and protect all 212 acres, forever.\n\n"
              f"Our campaign goal is {usd(GOAL)}, which covers the purchase, closing costs and a stewardship endowment to care for the land. "
              f"Thanks to neighbors and friends like you, we have raised {usd(raised)} so far. We have {usd(d['remaining'])} left to raise.\n\n"
              f"Here is the best part: the Osei Family Foundation will match every dollar given to the Hatch Farm campaign, up to {usd(MATCH)}, "
              "for gifts received by November 30, 2026. A gift of $100 today becomes $200 for Hatch Farm.\n\n"
              "Please give today with the enclosed envelope or at lowmeadowlandtrust.org/give, and make sure your gift reaches us by November 30 "
              "so it is matched.\n\n"
              f"With gratitude,\n\n{P['ed']}\nExecutive Director, {ORG}\n")
    write_text(os.path.join(sol, "appeal.md"), letter)

    vals = [GOAL, float(raised), float(d["remaining"])]
    assert len({round(v, 2) for v in vals + [float(v) for v in d["naive"].values()] + [float(Decimal(GOAL) - v) for v in d["naive"].values()]}) == \
        3 + 2 * len(d["naive"]), "naive readings must move the figures"
    write_task_yaml(HERE, {
        "id": "fundraising-appeal", "track": "desk", "category": "drafting",
        "title": "Fall appeal letter for the Hatch Farm campaign",
        "ask": (f"Please draft this fall's appeal letter for the Hatch Farm campaign. {P['dev'].split()[0]}'s campaign notes say what it needs, "
                "and the gift export and the foundation's letter are in the folder. Save it as appeal.md.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"the notes open with a ${OLD_GOAL:,} goal; the July 22 entry raises it to ${GOAL:,} (checks: campaign figures; outdated figures absent)",
            f"raised so far is {usd(raised)} from the export: HATCH fund only, pledges out (their payments in), the returned check and the refunded duplicate charge out; the notes' 'about ${d['stale_note']:,}' (the August board report, pledges at face value) is stale, every row gives {usd(d['naive']['all_rows'])}, adding pledges {usd(d['naive']['with_pledges'])}, adding the general fund {usd(d['naive']['with_gen'])} (check: campaign figures)",
            f"left to raise is the new goal less raised so far, {usd(d['remaining'])}; against the old goal it would be {usd(d['stale']['old_goal_left'])} (check: campaign figures)",
            f"the notes say the match runs through December 31; the foundation's letter says gifts received by November 30, 2026 (check: match amount and deadline)",
            "last year's appeal is in the folder with a $240,000 goal, $182,400 raised, a $25,000 Carver Fund match and a December 31, 2025 deadline (check: outdated figures absent)",
            "the export has a three-line report preamble, a BOM, CRLF endings and amounts as '$1,250.00' text (check: campaign figures)",
        ],
        "checks": [
            {"type": "file_exists", "name": "appeal.md exists", "path": "appeal.md"},
            {"type": "text_numbers_present", "name": "campaign figures", "path": "appeal.md",
             "numbers": [GOAL, float(raised), float(d["remaining"])], "rel_tol": 0.000001},
            {"type": "text_not_contains", "name": "outdated figures absent", "path": "appeal.md",
             "phrases": [f"{OLD_GOAL:,}", f"{d['stale_note']:,}", "182,400", "240,000", "Carver"]},
            {"type": "custom", "name": "match amount and deadline", "module": "check.py"},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
