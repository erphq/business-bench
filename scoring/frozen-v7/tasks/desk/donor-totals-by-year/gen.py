#!/usr/bin/env python3
"""donor-totals-by-year: 2024 and 2025 giving per donor household from three separate gift records.

    python gen.py [--seed N] [--naive DIR]

Business: a community food bank. Online gifts come from the giving platform, checks are typed into the
bookkeeper's deposit log, and gifts made at the spring luncheon and the fall gala come from the event app.
The development director wants one clean line per donor household for the year-end appeal segmentation.

Traps (each caught by a check, see task.yaml):
  * donors are written differently in every source ("SMITH, ROBERT J", "Bob Smith", a work email)
                                                                         (checks: 2024 totals; 2025 totals)
  * the CRM is by household: spouses give separately and count once, under the household id
                                                                         (checks: one row per household; 2025 totals)
  * online refunds live in a Refunded Amount column (full and partial)  (check: 2024 totals)
  * gala pledges are promises: unpaid ones never count, paid ones arrive later as checks
                                                                         (checks: donors who gave; 2025 totals)
  * peer-to-peer soft-credit rows repeat the gift under the fundraiser's name; a volunteer with only soft credits
    did not give                                                          (checks: donors who gave; 2025 totals)
  * checks dated in December and deposited in January count in the year on the check
                                                                         (checks: 2024 totals; 2025 totals)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

NICK = {"Robert": "Bob", "William": "Bill", "Elizabeth": "Liz", "Michael": "Mike", "Jennifer": "Jen", "Richard": "Rick",
        "James": "Jim", "Joseph": "Joe", "Thomas": "Tom", "Patricia": "Pat", "Margaret": "Peggy", "Christopher": "Chris",
        "Daniel": "Dan", "Anthony": "Tony", "Kimberly": "Kim", "Deborah": "Deb", "Rebecca": "Becky", "Kenneth": "Ken",
        "Steven": "Steve", "Timothy": "Tim", "Nicholas": "Nick", "Jonathan": "Jon", "Matthew": "Matt", "Andrew": "Andy"}
MIDDLE = "ABCDEHJKLMRST"
LUNCHEON = date(2024, 4, 18)
GALA = date(2025, 10, 11)


def build(seed: int) -> dict:
    r = rng(seed)
    lasts_used = set()
    households = []
    while len(households) < 34:
        f1, l = person(r)
        if l in lasts_used:
            continue
        lasts_used.add(l)
        couple = r.random() < 0.4
        f2 = None
        if couple:
            while True:
                f2 = r.choice(FIRST)
                if f2 != f1:
                    break
        hid = f"D-{10400 + len(households) * 13}"
        name = f"{f1} and {f2} {l}" if couple else f"{f1} {l}"
        people_ = [{"first": f1, "last": l, "email": email_for(r, f1, l), "alt": email_for(r, f1, l, r.choice(["gmail.com", r.choice(COMPANIES)[1], "outlook.com"]))}]
        if couple:
            people_.append({"first": f2, "last": l, "email": email_for(r, f2, l), "alt": email_for(r, f2, l, "gmail.com")})
        households.append({"id": hid, "name": name, "people": people_, "couple": couple, "role": "donor",
                           "street": address(r)[0]})
    # roles for the special households
    households[-1]["role"] = "soft_only"       # a volunteer who ran a fundraising page and never gave
    households[-2]["role"] = "pledge_only"     # pledged at the gala, never paid
    couples = [h for h in households[:-2] if h["couple"]]
    gifts = []      # truth rows: {"hid", "source", "date", "amount", "net", "person", ...}

    def g(h, source, d, amount, **kw):
        row = {"hid": h["id"], "source": source, "date": d, "amount": amount, "net": amount, "person": r.choice(h["people"]),
               "k": r.random()}
        row.update(kw)
        gifts.append(row)
        return row

    donors = [h for h in households if h["role"] == "donor"]
    for h in donors:
        for year in (2024, 2025):
            if r.random() < 0.15:
                continue
            for _ in range(r.randint(0, 3)):
                g(h, "online", day_in(r, date(year, 1, 3), date(year, 12, 29)), float(r.choice([25, 50, 50, 75, 100, 100, 150, 250, 500])))
            for _ in range(r.randint(0, 2)):
                cd = day_in(r, date(year, 1, 3), date(year, 11, 28))
                g(h, "check", cd, float(r.choice([100, 150, 200, 250, 500, 1000])), deposit=cd + timedelta(days=r.randint(2, 9)))
    for h in r.sample(donors, 4):             # monthly givers online
        amt = float(r.choice([15, 20, 25, 40]))
        start = r.randint(1, 6)
        for m in range(start, 13):
            g(h, "online", date(2025, m, min(28, 3 + start)), amt, recurring=True)
    # spouses giving separately in the same year: force both spouses to appear in different sources
    for h in couples[:4]:
        g(h, "online", day_in(r, date(2025, 2, 1), date(2025, 6, 30)), 100.0)["person"] = h["people"][1]
        cd = day_in(r, date(2025, 3, 1), date(2025, 9, 30))
        g(h, "check", cd, 250.0, deposit=cd + timedelta(days=4))["person"] = h["people"][0]
    # year-end checks dated December, deposited in January
    for h, year in zip(r.sample(donors, 5), (2024, 2024, 2024, 2025, 2025)):
        cd = date(year, 12, r.randint(22, 31))
        g(h, "check", cd, float(r.choice([500, 1000, 1500, 2500])), deposit=date(year + 1, 1, r.randint(3, 9)), yearend=True)
    # luncheon 2024 (paid at the event) and gala 2025 (paid by card, or pledged)
    for h in r.sample(donors, 8):
        g(h, "event", LUNCHEON, float(r.choice([100, 250, 500])), event="Spring Luncheon 2024", status="Paid")
    gala = r.sample(donors, 10)
    for h in gala[:5]:
        g(h, "event", GALA, float(r.choice([250, 500, 1000])), event="Harvest Gala 2025", status="Paid")
    pledges = []
    for h in gala[5:9]:
        row = g(h, "event", GALA, float(r.choice([1000, 2500, 5000])), event="Harvest Gala 2025", status="Pledged")
        row["net"] = 0.0
        pledges.append(row)
    ph = households[-2]
    row = g(ph, "event", GALA, 2500.0, event="Harvest Gala 2025", status="Pledged")
    row["net"] = 0.0
    for p in pledges[:2]:                     # two pledges paid by check afterwards
        h = next(x for x in households if x["id"] == p["hid"])
        cd = day_in(r, date(2025, 10, 20), date(2025, 11, 25))
        g(h, "check", cd, p["amount"], deposit=cd + timedelta(days=3), memo="Gala pledge")
    # refunds on online gifts
    online = [x for x in gifts if x["source"] == "online" and not x.get("recurring")]
    full = r.sample([x for x in online if x["date"].year == 2024 and x["amount"] >= 100], 2)
    for x in full:
        x["refunded"] = x["amount"]; x["net"] = 0.0
    part = r.sample([x for x in online if x["date"].year == 2025 and x["amount"] >= 150 and "refunded" not in x], 2)
    for x in part:
        x["refunded"] = round(x["amount"] / 2, 2); x["net"] = x["amount"] - x["refunded"]
    part24 = r.sample([x for x in online if x["date"].year == 2024 and x["amount"] >= 150 and "refunded" not in x], 1)
    for x in part24:
        x["refunded"] = 50.0; x["net"] = x["amount"] - 50.0
    # soft credits: gifts through two fundraising pages, credited to the page owner as a second row
    page_owners = [households[-1], r.choice([h for h in donors if not h["couple"]])]
    soft = []
    for owner in page_owners:
        for x in r.sample([x for x in gifts if x["source"] == "online" and x["date"].year == 2025 and x["hid"] != owner["id"]
                           and "refunded" not in x and not x.get("recurring")], 3):
            x["page"] = f"Run for Hunger 2025 - Team {owner['people'][0]['last']}"
            soft.append({"owner": owner, "gift": x})
    totals = {}
    for x in gifts:
        yr = x["date"].year
        totals.setdefault(x["hid"], {2024: 0.0, 2025: 0.0})
        totals[x["hid"]][yr] = round(totals[x["hid"]][yr] + x["net"], 2)
    gave = {hid: t for hid, t in totals.items() if t[2024] > 0 or t[2025] > 0}
    return {"households": households, "gifts": gifts, "soft": soft, "totals": gave, "page_owners": page_owners}


def naive_totals(d: dict) -> dict:
    """Every row's gross amount, pledges and soft credits included, checks by deposit year."""
    out = {}
    for x in d["gifts"]:
        yr = (x.get("deposit") or x["date"]).year
        if yr not in (2024, 2025):
            continue
        out.setdefault(x["hid"], {2024: 0.0, 2025: 0.0})
        out[x["hid"]][yr] += x["amount"]
    for s in d["soft"]:
        out.setdefault(s["owner"]["id"], {2024: 0.0, 2025: 0.0})
        out[s["owner"]["id"]][2025] += s["gift"]["amount"]
    return out


def acceptable(d: dict) -> bool:
    t, n = d["totals"], naive_totals(d)
    if d["households"][-1]["id"] in t or d["households"][-2]["id"] in t:
        return False
    wrong24 = sum(1 for h, v in t.items() if abs(n.get(h, {}).get(2024, 0) - v[2024]) > 0.01)
    wrong25 = sum(1 for h, v in t.items() if abs(n.get(h, {}).get(2025, 0) - v[2025]) > 0.01)
    return wrong24 >= 3 and wrong25 >= 6 and len(t) >= 28


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    hh = {h["id"]: h for h in d["households"]}
    header = ["donor_id", "donor_name", "total_2024", "total_2025"]
    if naive_dir:
        n = naive_totals(d)
        write_csv(os.path.join(naive_dir, "donor_totals.csv"), header,
                  [[hid, hh[hid]["name"], f"{v[2024]:.2f}", f"{v[2025]:.2f}"] for hid, v in sorted(n.items())])
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 9)

    # ---- CRM household list ----
    crm = []
    for h in d["households"]:
        p1 = h["people"][0]
        p2 = h["people"][1] if h["couple"] else None
        informal = " and ".join(NICK.get(p["first"], p["first"]) for p in h["people"])
        crm.append([h["id"], h["name"], p1["first"], p1["last"], p2["first"] if p2 else "", p2["last"] if p2 else "", informal,
                    p1["email"], p2["email"] if p2 else "", h["street"]])
    write_csv(os.path.join(ws, "crm_donor_households.csv"),
              ["Donor ID", "Household Name", "Primary First", "Primary Last", "Secondary First", "Secondary Last", "Informal Salutation",
               "Primary Email", "Secondary Email", "Street"], crm)

    # ---- online platform export ----
    orows = []
    tid = 880000
    for x in sorted([x for x in d["gifts"] if x["source"] == "online"], key=lambda x: (x["date"], x["k"])):
        tid += r.randint(3, 40)
        x["txn"] = f"GV-{tid}"
        p = x["person"]
        first = NICK[p["first"]] if (p["first"] in NICK and r.random() < 0.35) else p["first"]
        email = p["alt"] if r.random() < 0.3 else p["email"]
        stamp = datetime(x["date"].year, x["date"].month, x["date"].day, r.randint(7, 22), r.randint(0, 59), r.randint(0, 57))
        x["stamp"] = stamp
        refunded = x.get("refunded", 0.0)
        status = "Refunded" if refunded and refunded >= x["amount"] else ("Partially Refunded" if refunded else "Succeeded")
        orows.append([x["txn"], stamp.strftime("%Y-%m-%d %H:%M:%S"), first, p["last"], email, f"{x['amount']:.2f}", f"{refunded:.2f}",
                      status, "Recurring" if x.get("recurring") else "One-time", "Donation", x.get("page", ""), ""])
    for s in d["soft"]:
        o = s["owner"]["people"][0]
        x = s["gift"]
        stamp = x["stamp"] + timedelta(seconds=2)
        orows.append([f"SC-{x['txn'][3:]}", stamp.strftime("%Y-%m-%d %H:%M:%S"), o["first"], o["last"], o["email"], f"{x['amount']:.2f}",
                      "0.00", "Succeeded", "One-time", "Soft Credit", x["page"], f"soft credit for {x['txn']}"])
    orows.sort(key=lambda row: row[1])
    write_csv(os.path.join(ws, "online_giving_export_2024-2025.csv"),
              ["Transaction ID", "Created", "First Name", "Last Name", "Email", "Amount", "Refunded Amount", "Status", "Frequency",
               "Type", "Fundraising Page", "Memo"], orows, bom=True)

    # ---- bookkeeper's check deposit log ----
    crows = []
    for x in sorted([x for x in d["gifts"] if x["source"] == "check"], key=lambda x: (x["deposit"], x["k"])):
        h = hh[x["hid"]]
        p = x["person"]
        style = r.randrange(5)
        if h["couple"] and style == 0:
            nm = f"{h['people'][0]['first']} & {h['people'][1]['first']} {p['last']}"
        elif style == 1:
            nm = f"{p['last'].upper()}, {p['first'].upper()} {MIDDLE[(len(p['first']) * 7 + len(p['last'])) % len(MIDDLE)]}"
        elif style == 2:
            nm = f"{p['first']} {MIDDLE[(len(p['first']) * 7 + len(p['last'])) % len(MIDDLE)]}. {p['last']}"
        elif style == 3:
            nm = f"{NICK.get(p['first'], p['first'])} {p['last']}"
        else:
            nm = f"{p['first']} {p['last']}"
        crows.append([x["deposit"], str(r.randint(1001, 9899)), date_variant(x["date"], 1), nm, money_str(x["amount"], 1),
                      x.get("memo", r.choice(["", "", "", "general", "in memory of Ruth", "for the backpack program", ""]))])
    write_xlsx(os.path.join(ws, "check_deposit_log.xlsx"), {"Deposits": {
        "merged_title": "Check deposit log - general account", "preamble": [["Kept by: Janelle (bookkeeping)"]],
        "header": ["Deposit Date", "Check #", "Check Date", "Name on Check", "Amount", "Memo"], "rows": crows,
        "widths": {"A": 12, "C": 12, "D": 30, "F": 28}}}, creator="Janelle")

    # ---- event app export ----
    erows = []
    for x in sorted([x for x in d["gifts"] if x["source"] == "event"], key=lambda x: (x["date"], x["k"])):
        p = x["person"]
        erows.append([x["event"], date_variant(x["date"], 1), f"{NICK.get(p['first'], p['first']) if r.random() < 0.4 else p['first']} {p['last']}",
                      p["email"] if r.random() < 0.6 else "", "Paddle Raise" if x["event"].startswith("Harvest") else "Fund-a-Need",
                      money_str(x["amount"], 1), x["status"]])
    write_csv(os.path.join(ws, "event_gifts_export.csv"), ["Event", "Date", "Guest", "Email", "Gift Type", "Amount", "Payment Status"], erows)

    write_email_thread(os.path.join(ws, "email_from_development.txt"), [
        {"from": "Maya Ellison <maya@riversidefoodbank.org>", "to": "you", "date": "Thu, 15 Jan 2026 10:22",
         "subject": "donor totals for the appeal list",
         "body": ("Before we segment the year-end appeal list I need one clean line per donor with what they gave us in 2024 "
                  "and in 2025. The gifts are in three places: the giving platform export, Janelle's check log and the event app.\n\n"
                  "We count giving by household, the way the CRM is set up. If Linda gives online and Robert mails a check, "
                  "that's one household. Use the CRM donor ID.\n\n"
                  "Only count money we actually received. Refunds come off. Gala pledges are promises until the check shows up "
                  "(and when it does, it's in Janelle's log). Soft credits on the platform are just there so fundraisers can see "
                  "their page totals - the money is already counted under the person who gave it.\n\n"
                  "A check counts in the year written on the check, even when we didn't deposit it until January.\n\n"
                  "Only donors who actually gave something in 2024 or 2025, please. Columns: donor_id, donor_name, "
                  "total_2024, total_2025.\n\nMaya")}])

    rows = [[hid, hh[hid]["name"], f"{v[2024]:.2f}", f"{v[2025]:.2f}"] for hid, v in sorted(d["totals"].items())]
    write_csv(os.path.join(ref, "donor_totals.csv"), header, rows)
    write_csv(os.path.join(sol, "donor_totals.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {"soft_only_household": d["households"][-1]["id"], "pledge_only_household": d["households"][-2]["id"],
                                                  "grand_2024": round(sum(v[2024] for v in d["totals"].values()), 2),
                                                  "grand_2025": round(sum(v[2025] for v in d["totals"].values()), 2)})
    write_task_yaml(HERE, {
        "id": "donor-totals-by-year", "track": "desk", "category": "spreadsheet",
        "title": "Per-donor giving totals for 2024 and 2025",
        "ask": ("Maya wants each donor's total giving for 2024 and 2025 pulled together from the three gift records in this folder, "
                "for the appeal list. Save it as donor_totals.csv. Her email has the counting rules.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the same donor is written differently in each source - 'SMITH, ROBERT J' or 'Bob Smith' on a check, a nickname "
            "or a personal email online, no email at all in the event app - and has to be matched to the CRM household "
            "(checks: 2024 totals; 2025 totals)",
            "the CRM is by household and spouses give separately (one online, one by check); a row per person splits the "
            "household and duplicates its id (checks: one row per household; 2025 totals)",
            "online refunds sit in a Refunded Amount column, two full refunds in 2024 and partial refunds in both years; "
            "summing Amount ignores them (check: 2024 totals)",
            "Harvest Gala pledges (Payment Status 'Pledged') are not money: two were later paid by check and are already in "
            "the check log, and one household's only activity is an unpaid pledge, so it must not appear "
            "(checks: donors who gave; 2025 totals)",
            "'Soft Credit' rows repeat six page gifts under the fundraising page owner; one owner is a volunteer who never "
            "gave (checks: donors who gave; 2025 totals)",
            "five year-end checks are dated in late December and deposited in January; Maya counts them in the year on "
            "the check (checks: 2024 totals; 2025 totals)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "donor_totals.csv", "columns": ["donor_id", "total_2024", "total_2025"]},
            {"type": "csv_set_equal", "name": "donors who gave", "path": "donor_totals.csv", "column": "donor_id", "ref": "donor_totals.csv",
             "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "one row per household", "path": "donor_totals.csv", "equals_ref": "donor_totals.csv"},
            {"type": "csv_values_match", "name": "2024 totals", "path": "donor_totals.csv", "ref": "donor_totals.csv", "key": "donor_id",
             "columns": ["total_2024"], "numeric": True, "tolerance": 0.01},
            {"type": "csv_values_match", "name": "2025 totals", "path": "donor_totals.csv", "ref": "donor_totals.csv", "key": "donor_id",
             "columns": ["total_2025"], "numeric": True, "tolerance": 0.01},
        ],
    })
    print(f"seed={seed} households_gave={len(d['totals'])} gifts={len(d['gifts'])} soft={len(d['soft'])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(500):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
