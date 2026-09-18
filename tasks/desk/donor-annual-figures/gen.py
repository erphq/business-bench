#!/usr/bin/env python3
"""donor-annual-figures: a donor CRM gift export to fiscal-year totals, top donors and donor retention.

    python gen.py [--seed N] [--naive DIR]

Business: an animal rescue with a July-June fiscal year. The treasurer needs FY2026 against FY2025 for the
board: net cash raised, the top ten donors and donor retention, counted the way the gift reporting policy says.

Traps (each caught by a check, see task.yaml):
  * the fiscal year runs 1 July - 30 June and the export starts in January 2024      (checks: FY2025 and FY2026 totals)
  * fully refunded gifts keep a positive amount with Status Refunded; partial refunds and chargebacks are separate
    negative rows, netted against the original gift's fiscal year (one crosses the year end)
                                                                                     (checks: FY totals; top donor; memo)
  * in-kind gifts are excluded from totals, donor counts and retention (a donated van would top the list)
                                                                                     (checks: FY2026 total; retention)
  * donor names are written several ways under one Donor ID                          (checks: top donor; retained donors)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))


ORGS = ["Marlowe Family Foundation", "Cascade Community Fund", "Riverside Rotary Club", "Pinecrest Dental Group", "Ashgrove Veterinary Partners",
        "Kessler Charitable Trust", "Blue Ridge Credit Union", "Tamarack Brewing", "Halvorsen Foundation", "Northgate Savings"]
METHODS = ["Credit card", "Credit card", "Credit card", "Check", "ACH", "PayPal"]
CAMPAIGNS = ["Spring Appeal", "Year-End Appeal", "Gala", "Monthly Guardians", "Kitten Season", "General"]
INKIND = [("Donated cargo van (fair market value)", 30500, 41500), ("Pallets of dog food", 900, 3400), ("Kennel panels", 700, 2600),
          ("Veterinary supplies", 300, 1800), ("Blankets and towels", 80, 400), ("Office laptops (2)", 600, 1500)]


def fy_of(d: date) -> str:
    return f"FY{d.year + 1 if d.month >= 7 else d.year}"


def build(seed: int) -> dict:
    r = rng(seed)
    donors = []
    for i, (f, l) in enumerate(people(r, 240)):
        donors.append({"id": f"D-{10001 + i}", "kind": "person", "first": f, "last": l, "name": f"{f} {l}"})
    for j, org in enumerate(r.sample(ORGS, 8)):
        donors.append({"id": f"D-{10241 + j}", "kind": "org", "name": org, "first": "", "last": org.split()[0]})
    r.shuffle(donors)
    gifts = []

    def add(dn, d, amt, typ="Credit card", status="Posted", camp=None, note="", kind="cash"):
        g = {"donor": dn, "date": d, "amt": round(amt, 2), "type": typ, "status": status, "camp": camp or r.choice(CAMPAIGNS),
             "note": note, "kind": kind}
        gifts.append(g)
        return g

    periods = {"FY2024": (date(2024, 1, 2), date(2024, 6, 30)), "FY2025": (date(2024, 7, 1), date(2025, 6, 30)),
               "FY2026": (date(2025, 7, 1), date(2026, 6, 30))}
    for dn in donors:
        if dn["kind"] == "org":
            p = {"FY2024": 0.3, "FY2025": 0.8, "FY2026": 0.75}
        else:
            p = {"FY2024": 0.18, "FY2025": 0.55, "FY2026": 0.55}
        monthly = dn["kind"] == "person" and r.random() < 0.08
        active_prev = False
        for fy in ("FY2024", "FY2025", "FY2026"):
            q = p[fy] + (0.12 if active_prev else 0)
            if r.random() >= q:
                active_prev = False
                continue
            active_prev = True
            s, e = periods[fy]
            if monthly:
                d = s + timedelta(days=r.randint(0, 20))
                amt = r.choice([15, 20, 25, 35, 50])
                while d <= e:
                    add(dn, d, amt, "Credit card", camp="Monthly Guardians")
                    d = (d.replace(day=1) + timedelta(days=32)).replace(day=min(d.day, 28))
                continue
            for _ in range(r.choice([1, 1, 1, 2, 2, 3])):
                if dn["kind"] == "org":
                    amt = r.choice([money(r, 1000, 5000, cents=False), money(r, 2500, 12000, cents=False)])
                else:
                    amt = r.choice([money(r, 25, 250, cents=False)] * 5 + [money(r, 250, 1500, cents=False), money(r, 1000, 6000, cents=False)])
                add(dn, day_in(r, s, e), amt, r.choice(METHODS + (["Stock", "DAF grant"] if amt > 1000 else [])))
    people_ = [x for x in donors if x["kind"] == "person"]
    orgs = [x for x in donors if x["kind"] == "org"]

    # the top donor: several gifts under name variants, one partially refunded
    top = r.choice([x for x in people_ if any(g["donor"] is x for g in gifts if fy_of(g["date"]) == "FY2025")])
    top["variants"] = [f"{top['first']} {top['last']}", f"{top['last']}, {top['first']}", f"{top['first']} & {r.choice(FIRST)} {top['last']}"]
    big = [add(top, day_in(r, date(2025, 8, 1), date(2026, 5, 31)), money(r, 7000, 12000, cents=False), "Stock"),
           add(top, day_in(r, date(2025, 7, 10), date(2026, 6, 20)), money(r, 4000, 8000, cents=False), "Check"),
           add(top, day_in(r, date(2025, 11, 15), date(2025, 12, 31)), money(r, 3000, 6000, cents=False), "DAF grant", camp="Year-End Appeal")]
    part = big[1]
    part_amt = round(part["amt"] * r.choice([0.25, 0.3, 0.4]), 0)
    add(top, part["date"] + timedelta(days=r.randint(5, 9)), -part_amt, "Refund", note="", kind="refund").update({"of": part})

    # the major gift that was refunded in full (status Refunded, amount still positive)
    fdn = next((x for x in orgs if any(w in x["name"] for w in ("Foundation", "Trust", "Fund"))), orgs[0])
    major = add(fdn, day_in(r, date(2025, 9, 1), date(2026, 3, 31)), r.choice([25000, 30000, 35000]), "ACH", status="Refunded", camp="General")
    major["refund_note"] = True

    # a chargeback that crosses the fiscal year end: gift in June 2025, reversed in July 2025
    cb_donor = r.choice([x for x in people_ if x is not top])
    cb_gift = add(cb_donor, date(2025, 6, r.randint(18, 29)), money(r, 4000, 6000, cents=False), "Credit card", camp="Spring Appeal")
    add(cb_donor, date(2025, 7, r.randint(6, 14)), -cb_gift["amt"], "Chargeback", kind="refund").update({"of": cb_gift})

    # more full refunds (status) and partial refunds (rows), including an FY2025 donor whose only FY2026 gift is refunded
    fy25_donors = {id(g["donor"]) for g in gifts if fy_of(g["date"]) == "FY2025" and g["amt"] > 0}
    lone = [x for x in people_ if id(x) in fy25_donors and x is not top and x is not cb_donor
            and sum(1 for g in gifts if g["donor"] is x and fy_of(g["date"]) == "FY2026") == 1]
    for x in r.sample(lone, min(3, len(lone))):
        g = next(g for g in gifts if g["donor"] is x and fy_of(g["date"]) == "FY2026")
        g["status"] = "Refunded"
    others = [g for g in gifts if g["status"] == "Posted" and g["kind"] == "cash" and g["amt"] >= 100 and g["donor"] is not top
              and g["donor"] is not cb_donor]
    for g in r.sample(others, 6):
        add(g["donor"], g["date"] + timedelta(days=r.randint(2, 20)), -round(g["amt"] * r.choice([0.2, 0.5]), 0), "Refund", kind="refund").update({"of": g})
    for g in r.sample([g for g in others if g["status"] == "Posted" and g["amt"] < 600], 3):
        g["status"] = "Refunded"

    # in-kind: a van that would top the list, and smaller items; some from donors with no cash gifts at all
    van_donor = r.choice([x for x in orgs if x is not fdn])
    add(van_donor, day_in(r, date(2025, 10, 1), date(2026, 4, 30)), 0, "In-kind", camp="General", kind="inkind").update(
        {"amt": money(r, *INKIND[0][1:], cents=False), "note": INKIND[0][0]})
    no_cash = [x for x in people_ if not any(g["donor"] is x for g in gifts)]
    for i in range(10):
        dn = no_cash[i] if i < 5 and i < len(no_cash) else r.choice(people_)
        item = r.choice(INKIND[1:])
        fy = r.choice(["FY2025", "FY2026"])
        add(dn, day_in(r, *periods[fy]), money(r, item[1], item[2], cents=False), "In-kind", camp="General", kind="inkind").update({"note": item[0]})

    # ids in date order; refund rows name the gift they reverse
    gifts.sort(key=lambda g: (g["date"], g["donor"]["id"], -g["amt"]))
    for i, g in enumerate(gifts):
        g["gid"] = f"G-{50001 + i}"
    for g in gifts:
        if g["kind"] == "refund":
            g["note"] = f"{g['type']} of {g['of']['gid']}"
        if g.get("refund_note"):
            g["note"] = "Returned at donor's request - grant terms not met"
    return {"donors": donors, "gifts": gifts, "top": top, "fdn": fdn, "major": major, "cb_gift": cb_gift, "van_donor": van_donor}


def credit(g) -> tuple[str | None, float]:
    """(fiscal year credited, net cash amount) under the policy"""
    if g["kind"] == "inkind":
        return None, 0.0
    if g["kind"] == "refund":
        return fy_of(g["of"]["date"]), g["amt"]
    if g["status"] == "Refunded":
        return fy_of(g["date"]), 0.0
    return fy_of(g["date"]), g["amt"]


def figures(gifts, credit_fn=credit, key=lambda g: g["donor"]["id"]) -> dict:
    net = {}
    tot = {"FY2024": 0.0, "FY2025": 0.0, "FY2026": 0.0}
    for g in gifts:
        fy, amt = credit_fn(g)
        if fy not in tot:
            continue
        tot[fy] += amt
        net.setdefault(key(g), {}).setdefault(fy, 0.0)
        net[key(g)][fy] += amt
    gave = {fy: {k for k, v in net.items() if v.get(fy, 0) > 0.005} for fy in tot}
    retained = gave["FY2025"] & gave["FY2026"]
    ranking = sorted(((round(v.get("FY2026", 0), 2), k) for k, v in net.items() if v.get("FY2026", 0) > 0), reverse=True)
    return {"tot": {k: round(v, 2) for k, v in tot.items()}, "net": net, "gave": gave, "retained": len(retained),
            "rate": round(len(retained) / len(gave["FY2025"]), 4), "ranking": ranking}


def variants(d) -> dict:
    G = d["gifts"]
    cal = lambda g: (None, 0.0) if g["kind"] == "inkind" or g["status"] == "Refunded" else (f"FY{g['date'].year}" if g["date"].year in (2025, 2026) else None, g["amt"])
    by_date = lambda g: (None, 0.0) if g["kind"] == "inkind" else (fy_of(g["date"]), 0.0 if g["status"] == "Refunded" else g["amt"])
    inkind = lambda g: (fy_of(g["date"]), g["amt"]) if g["kind"] == "inkind" else credit(g)
    status = lambda g: (fy_of(g["date"]), g["amt"]) if g["status"] == "Refunded" else credit(g)
    no_neg = lambda g: (None, 0.0) if g["kind"] == "refund" else credit(g)
    shown = d["shown_name"]
    return {"calendar": figures(G, cal), "refund_by_date": figures(G, by_date), "inkind": figures(G, inkind), "status_ignored": figures(G, status),
            "refund_rows_dropped": figures(G, no_neg), "by_name": figures(G, key=lambda g: shown[g["gid"]])}


def acceptable(d: dict) -> bool:
    f = figures(d["gifts"])
    d["f"] = f
    r = rng(len(d["gifts"]))
    shown = {}
    for g in d["gifts"]:
        dn = g["donor"]
        if dn is d["top"]:
            shown[g["gid"]] = dn["variants"][len(shown) % 3]
        elif dn["kind"] == "person" and r.random() < 0.25:
            shown[g["gid"]] = r.choice([f"{dn['last']}, {dn['first']}", dn["name"].upper(), f"{dn['first'][0]}. {dn['last']}"])
        else:
            shown[g["gid"]] = dn["name"]
    d["shown_name"] = shown
    v = variants(d)
    d["v"] = v
    if f["ranking"][0][1] != d["top"]["id"]:
        return False
    top_total = f["ranking"][0][0]
    if len(f["ranking"]) < 11 or f["ranking"][1][0] > 0.85 * top_total:
        return False
    van = next(g for g in d["gifts"] if g["kind"] == "inkind" and g["donor"] is d["van_donor"] and g["amt"] > 20000)
    if van["amt"] <= top_total or d["major"]["amt"] <= top_total:
        return False
    def far(a, b, rel=0.01): return abs(a - b) > rel * abs(a)
    for k in ("calendar", "refund_by_date", "inkind", "status_ignored"):
        if not far(f["tot"]["FY2026"], v[k]["tot"]["FY2026"]) and not far(f["tot"]["FY2025"], v[k]["tot"]["FY2025"]):
            return False
    if not far(f["tot"]["FY2025"], v["refund_by_date"]["tot"]["FY2025"]) or not far(f["tot"]["FY2026"], v["refund_by_date"]["tot"]["FY2026"]):
        return False
    for k in ("inkind", "status_ignored", "by_name", "calendar"):
        if v[k]["retained"] == f["retained"]:
            return False
    if abs(v["inkind"]["rate"] - f["rate"]) < 0.004 or abs(v["status_ignored"]["rate"] - f["rate"]) < 0.004:
        return False
    # the top donor's own total moves when the name variants split them or the refund row is dropped
    by_name_top = max(v["by_name"]["net"].get(n, {}).get("FY2026", 0) for n in d["top"]["variants"])
    if not far(top_total, by_name_top) or not far(top_total, v["refund_rows_dropped"]["net"][d["top"]["id"]]["FY2026"]):
        return False
    if f["retained"] in (len(f["gave"]["FY2025"]), len(f["gave"]["FY2026"])):
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_workbook(gift_rows: list[list], donor_rows: list[list], top_ids: list[str], name_of: dict) -> dict:
    """gift_rows: [gift_id, donor_id, date, type, status, amount, credited_fy, net_cash]; donor_rows: [donor_id, name]"""
    n = len(gift_rows) + 1
    drows = []
    for i, (did, name) in enumerate(donor_rows, start=2):
        drows.append([did, name, f'=SUMIFS(Gifts!$H$2:$H${n},Gifts!$B$2:$B${n},$A{i},Gifts!$G$2:$G${n},"FY2025")',
                      f'=SUMIFS(Gifts!$H$2:$H${n},Gifts!$B$2:$B${n},$A{i},Gifts!$G$2:$G${n},"FY2026")'])
    m = len(donor_rows) + 1
    row_of = {did: i for i, (did, _) in enumerate(donor_rows, start=2)}
    summ = [
        ["Net cash raised", f'=ROUND(SUMIFS(Gifts!$H$2:$H${n},Gifts!$G$2:$G${n},"FY2025"),2)', f'=ROUND(SUMIFS(Gifts!$H$2:$H${n},Gifts!$G$2:$G${n},"FY2026"),2)'],
        ["Donors who gave cash", f'=COUNTIF(Donors!$C$2:$C${m},">0")', f'=COUNTIF(Donors!$D$2:$D${m},">0")'],
        ["Retained donors (gave in FY2025 and again in FY2026)", "", f'=COUNTIFS(Donors!$C$2:$C${m},">0",Donors!$D$2:$D${m},">0")'],
        ["Donor retention rate", "", "=ROUND(C4/B3,4)"],
        [],
        ["Policy: fiscal year 1 July - 30 June; in-kind gifts excluded; refunds and chargebacks netted against the original gift's fiscal year."],
    ]
    top = [[k + 1, did, name_of[did], f"=Donors!D{row_of[did]}"] for k, did in enumerate(top_ids)]
    return {"Summary": {"header": ["Measure", "FY2025", "FY2026"], "rows": summ, "widths": {"A": 50, "B": 14, "C": 14}},
            "Top donors FY2026": {"header": ["Rank", "Donor ID", "Donor", "FY2026 net cash"], "rows": top, "widths": {"C": 30, "D": 16}},
            "Donors": {"header": ["donor_id", "donor", "FY2025", "FY2026"], "rows": drows, "widths": {"B": 30}},
            "Gifts": {"header": ["gift_id", "donor_id", "date", "type", "status", "amount", "credited_fy", "net_cash"], "rows": gift_rows}}


def memo_text(d: dict) -> str:
    f = d["f"]
    t = f["tot"]
    top_id = f["ranking"][0][1]
    name = {x["id"]: x["name"] for x in d["donors"]}
    change = t["FY2026"] - t["FY2025"]
    return f"""# FY2026 fundraising figures

Net cash raised in FY2026 (1 July 2025 - 30 June 2026) was ${t['FY2026']:,.2f}, against ${t['FY2025']:,.2f} in FY2025,
a change of ${change:,.2f}. {len(f['gave']['FY2026'])} donors gave cash in FY2026.

Donor retention was {f['rate']:.1%}: {f['retained']} of the {len(f['gave']['FY2025'])} FY2025 donors gave again in FY2026.

The top donor was {name[top_id]} at ${f['ranking'][0][0]:,.2f}.

Things to know:

- The ${d['major']['amt']:,.0f} gift from {d['fdn']['name']} was refunded in full, so it is not in FY2026.
- The donated van from {d['van_donor']['name']} and the other in-kind gifts are left out of totals, donor counts and retention
  under the gift reporting policy.
- A ${d['cb_gift']['amt']:,.0f} June 2025 card gift was charged back in July; it comes off FY2025, the year of the gift.
"""


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    acceptable(d)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    G, f = d["gifts"], d["f"]
    name = {x["id"]: x["name"] for x in d["donors"]}

    # ---- workspace
    r = rng(seed + 3)
    body = []
    for g in G:
        amt = g["amt"]
        amt_s = f"({abs(amt):,.2f})" if amt < 0 and r.random() < 0.5 else (f"-{abs(amt):,.2f}" if amt < 0 else f"{amt:,.2f}")
        body.append([g["gid"], g["donor"]["id"], d["shown_name"][g["gid"]], g["date"].strftime("%m/%d/%Y"), amt_s, g["type"],
                     g["camp"], g["status"], g["note"]])
    write_csv(os.path.join(ws, "gifts_export_2024-01-01_to_2026-06-30.csv"),
              ["Gift ID", "Donor ID", "Donor Name", "Gift Date", "Amount", "Gift Type", "Campaign", "Status", "Notes"], body, bom=True)
    write_text(os.path.join(ws, "gift_reporting_policy.txt"),
               "Riverbend Animal Rescue - Gift reporting policy (board approved, March 2024)\n\n"
               "1. Fiscal year. Our fiscal year runs from 1 July to 30 June and is named for the year in which it ends:\n"
               "   FY2026 is 1 July 2025 to 30 June 2026. All board figures are by fiscal year.\n\n"
               "2. What counts as raised. Cash gifts count at the amount received: card, check, ACH, PayPal, gifts of stock\n"
               "   (at the value on the day received) and donor-advised fund grants.\n\n"
               "3. In-kind gifts. Goods and services are recorded at fair market value so we can thank the donor, but they\n"
               "   are not fundraising revenue. Leave them out of totals, donor counts, rankings and retention.\n\n"
               "4. Refunds and chargebacks. A gift refunded in full shows Status 'Refunded' and did not happen. A partial refund\n"
               "   or a card chargeback is entered as its own negative line naming the gift it reverses; net it against that\n"
               "   original gift, in the original gift's fiscal year, even when the refund is processed later.\n\n"
               "5. Donors. A donor is a Donor ID. The CRM prints the name as it was typed on each gift.\n\n"
               "6. Retention. Donor retention for a year is the number of donors who gave in the prior fiscal year and gave\n"
               "   again in this one, divided by the number of donors who gave in the prior fiscal year. 'Gave' means net\n"
               "   cash giving above zero in that year.\n")
    write_email_thread(os.path.join(ws, "email_from_treasurer.txt"), [
        {"from": "Nadia Haddad <treasurer@riverbendrescue.org>", "to": "you", "date": "Thu, 9 Jul 2026 19:22",
         "subject": "annual figures for the board packet",
         "body": ("Now that the year has closed, can you pull the annual fundraising figures for the board packet? This year "
                  "against last year, our top ten donors for the year, and donor retention. The CRM export is in the shared "
                  "folder along with the gift reporting policy - please count everything the policy way, the auditors check it.\n\n"
                  "A short cover memo with the headlines would be great, and flag anything unusual - the board always asks.")}])

    # ---- reference
    top10 = f["ranking"][:10]
    write_csv(os.path.join(ref, "top_donors_fy2026.csv"), ["rank", "donor_id", "donor", "fy2026_net_cash"],
              [[k + 1, did, name[did], f"{amt:.2f}"] for k, (amt, did) in enumerate(top10)])
    write_json(os.path.join(ref, "notes.json"), {
        "fy_totals": f["tot"], "donors_gave": {k: len(v) for k, v in f["gave"].items()}, "retained_donors": f["retained"],
        "retention_rate": f["rate"], "top_donor": {"id": f["ranking"][0][1], "name": name[f["ranking"][0][1]], "fy2026": f["ranking"][0][0]},
        "refunded_major_gift": {"donor": d["fdn"]["name"], "amount": d["major"]["amt"], "gift_id": d["major"]["gid"]},
        "cross_year_chargeback": {"gift_id": d["cb_gift"]["gid"], "amount": d["cb_gift"]["amt"]},
        "naive": {k: {"tot": d["v"][k]["tot"], "retained": d["v"][k]["retained"], "rate": d["v"][k]["rate"]} for k in d["v"]}})

    # ---- reference solution
    gift_rows = []
    for g in G:
        fy, net = credit(g)
        gift_rows.append([g["gid"], g["donor"]["id"], g["date"].isoformat(), g["type"], g["status"], g["amt"], fy or "", round(net, 2)])
    active = sorted({g["donor"]["id"] for g in G if credit(g)[0] in ("FY2025", "FY2026") and g["kind"] != "inkind"})
    donor_rows = [[did, name[did]] for did in active]
    write_xlsx(os.path.join(sol, "annual_figures.xlsx"), report_workbook(gift_rows, donor_rows, [did for _, did in top10], name), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    top_id = f["ranking"][0][1]
    top_last = d["top"]["last"].lower()
    fdn_word = d["fdn"]["name"].split()[0].lower()
    write_task_yaml(HERE, {
        "id": "donor-annual-figures", "track": "desk", "category": "reports",
        "title": "FY2026 fundraising figures for the board",
        "ask": ("Nadia needs this year's fundraising figures for the board packet - totals against last year, the top ten donors "
                "and donor retention. Put them in annual_figures.xlsx with live formulas and write a cover memo as memo.md. "
                "Her email and the gift policy are in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the fiscal year runs 1 July - 30 June and is named for the year it ends in; the export starts in January 2024 and a "
            "calendar-year reading shifts both years (checks: FY2026 net cash raised; FY2025 net cash raised)",
            f"fully refunded gifts keep their positive amount and only say Status 'Refunded' - including the "
            f"${d['major']['amt']:,.0f} {d['fdn']['name']} grant, which would otherwise be the year's biggest gift; the memo has to "
            "say it came back (checks: FY2026 net cash raised; memo says the foundation gift was refunded)",
            "partial refunds and chargebacks are separate negative rows (some written in parentheses) naming the gift they reverse; "
            f"a ${d['cb_gift']['amt']:,.0f} June 2025 gift charged back in July must come off FY2025, not FY2026 "
            "(checks: FY2025 net cash raised; FY2026 net cash raised)",
            "in-kind gifts carry a fair-market value in the Amount column; the policy leaves them out of totals, donor counts and "
            f"retention, and five in-kind donors never gave cash; the donated van from {d['van_donor']['name']} would top the donor "
            "list (checks: FY2026 net cash raised; retained donors; donor retention rate)",
            f"the top donor's gifts are typed three ways ('{d['top']['variants'][0]}', '{d['top']['variants'][1]}', "
            f"'{d['top']['variants'][2]}') under one Donor ID, one of their gifts is partly refunded, and other donors vary in "
            "case and initials; grouping by name splits donors (checks: top donor FY2026 total; retained donors)",
            "an FY2025 donor whose only FY2026 gift was refunded did not give in FY2026 and is not retained (check: retained donors)",
        ],
        "checks": [
            {"type": "file_exists", "name": "annual_figures.xlsx exists", "path": "annual_figures.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "annual_figures.xlsx", "min_count": 6},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "annual_figures.xlsx"},
            {"type": "xlsx_value_present", "name": "FY2026 net cash raised", "path": "annual_figures.xlsx",
             "expected": f["tot"]["FY2026"], "rel_tol": cent_tol(f["tot"]["FY2026"], 0.003), "near_text": "fy"},
            {"type": "xlsx_value_present", "name": "FY2025 net cash raised", "path": "annual_figures.xlsx",
             "expected": f["tot"]["FY2025"], "rel_tol": cent_tol(f["tot"]["FY2025"], 0.003), "near_text": "fy"},
            {"type": "xlsx_value_present", "name": "top donor FY2026 total", "path": "annual_figures.xlsx",
             "expected": f["ranking"][0][0], "rel_tol": cent_tol(f["ranking"][0][0], 0.003), "near_text": top_last},
            {"type": "xlsx_value_present", "name": "retained donors", "path": "annual_figures.xlsx",
             "expected": f["retained"], "rel_tol": cent_tol(f["retained"], 0.001), "near_text": "retain"},
            {"type": "custom", "name": "donor retention rate", "module": "check.py"},
            {"type": "text_numbers_present", "name": "memo carries both years' totals", "path": "memo.md",
             "numbers": [f["tot"]["FY2026"], f["tot"]["FY2025"]], "rel_tol": 0.003},
            {"type": "text_sentence_matches", "name": "memo says the foundation gift was refunded", "path": "memo.md",
             "all": [rf"\b{fdn_word}\b", r"(refund|returned|\breturn\b|revers|charge ?back|cancel|given back|sent back|paid back|withdrawn|clawed back)"],
             "none": [r"\b(not|never)\b[^.;]{0,12}\b(refund|returned|revers)"]},
        ],
    })
    print(f"seed={seed} gifts={len(G)} tot={f['tot']} gave={ {k: len(v) for k, v in f['gave'].items()} } retained={f['retained']} "
          f"rate={f['rate']} top={f['ranking'][:3]} naive={ {k: (d['v'][k]['tot']['FY2026'], d['v'][k]['retained']) for k in d['v']} }")


def write_naive(d: dict, out: str) -> None:
    """Calendar years, every amount at face value (in-kind, refunded status), negatives dated when processed, names as typed."""
    os.makedirs(out, exist_ok=True)
    G = d["gifts"]
    shown = d["shown_name"]
    gift_rows = []
    for g in G:
        fy = f"FY{g['date'].year}" if g["date"].year in (2025, 2026) else ""
        gift_rows.append([g["gid"], shown[g["gid"]], g["date"].isoformat(), g["type"], g["status"], g["amt"], fy, g["amt"]])
    names = sorted({shown[g["gid"]] for g in G})
    net26 = {}
    for g in G:
        if g["date"].year == 2026:
            net26[shown[g["gid"]]] = net26.get(shown[g["gid"]], 0) + g["amt"]
    top = [n for _, n in sorted(((v, k) for k, v in net26.items()), reverse=True)[:10]]
    wb = report_workbook(gift_rows, [[n, n] for n in names], top, {n: n for n in names})
    write_xlsx(os.path.join(out, "annual_figures.xlsx"), wb, creator="naive")
    write_text(os.path.join(out, "memo.md"), "# Fundraising figures\n\nGiving was up this year, helped by a large foundation grant and a donated van.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(600):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 600 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
