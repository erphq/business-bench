#!/usr/bin/env python3
"""Deterministic seed generator for the donor-management build task. All donors are fictional.

    python gen.py [--seed N]

Writes:
  seed/donors.csv         one row per person: couples at the same address written two ways (Street/St,
                          case, periods), apartment neighbours at one street address, online donors with no
                          address, exact duplicate rows, and people re-entered under a second donor id
  seed/gifts.csv          gifts since January 2025: duplicated rows, "$1,000.00" strings, donor and pledge ids
                          padded three ways, program names in mixed case, acknowledgement written five ways
  seed/pledges.csv        pledges with their schedules; one pledge ends before it starts
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the public variant checklist.md quotes. Other seeds re-roll names, addresses, gifts, and
pledges; counts.json is recomputed. Year-to-date figures assume a test date in 2026 after 2026-09-05,
the last gift date in the seed.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, write_csv, write_text  # noqa: E402

SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")
ORG = "Harbor Lights Community Fund"
PROGRAMS = ["Youth Literacy", "Scholarships", "Food Pantry", "Senior Meals", "General Operating"]
PROGRAM_WEIGHTS = [25, 12, 28, 20, 15]
OFFICERS = {"Nia Robinson": ["Youth Literacy", "Scholarships"], "Omar Haddad": ["Food Pantry"], "Grace Kim": ["Senior Meals"]}
RESTRICTED = "Nia Robinson"
LETTER_THRESHOLD = 250.00
LAST_GIFT_DATE = date(2026, 9, 5)
N_SINGLES, N_COUPLES = 124, 26
N_ONLINE, N_NEIGHBOUR_PAIRS = 6, 3
N_EXACT_DUP_ROWS, N_REENTERED = 8, 6
N_PLEDGES = 64
N_DUP_GIFTS = 7
STREET_NAMES = ["Birch", "Harbor", "Ocean", "Forest", "Pleasant", "Brackett", "Congress", "Deering", "Stevens", "Washington",
                "Cumberland", "Pine", "Spring", "Danforth", "Vaughan", "Bramhall", "Clifford", "Highland", "Mackworth", "Veranda",
                "Allen", "Ludlow", "Baxter", "Woodford", "Shore", "Summit", "Maple", "Elm", "Chestnut", "Grant"]
SUFFIXES = [("Street", "St"), ("Avenue", "Ave"), ("Road", "Rd"), ("Drive", "Dr"), ("Lane", "Ln"), ("Court", "Ct")]
PLACES = [("Portland", "ME", "04101"), ("Portland", "ME", "04102"), ("Portland", "ME", "04103"), ("South Portland", "ME", "04106"),
          ("Westbrook", "ME", "04092"), ("Falmouth", "ME", "04105"), ("Cape Elizabeth", "ME", "04107"), ("Scarborough", "ME", "04074")]
EMAIL_DOMAINS = ["gmail.com", "gmail.com", "yahoo.com", "outlook.com", "icloud.com", "maine.rr.com", "comcast.net"]
SAFE_DATE_STYLES = [0, 1, 2, 3, 4]
AMOUNTS = [25, 25, 50, 50, 50, 100, 100, 100, 125, 150, 200, 250, 250, 300, 500, 500, 750, 1000, 1500, 2500]


def did(n: int) -> str:
    return f"D-{n:05d}"


def norm_address(street: str, zipc: str) -> str:
    s = street.lower().replace(".", " ").replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    for full, short in SUFFIXES:
        s = re.sub(rf"\b{full.lower()}\b", short.lower(), s)
    return f"{s}|{zipc}"


def build(seed: int) -> dict:
    rng = random.Random(seed)

    # ------------------------------------------------------------------ people and households
    officer_names = {w for n in OFFICERS for w in n.split()}
    names = [(f, l) for f in FIRST for l in LAST if f not in officer_names and l not in officer_names]
    rng.shuffle(names)
    name_iter = iter(names)
    used_streets: set[str] = set()

    def new_street(unit: str = "") -> tuple[str, str, str, str, tuple[str, str]]:
        while True:
            num = rng.randint(3, 1480)
            sname = rng.choice(STREET_NAMES)
            suffix = rng.choice(SUFFIXES)
            key = f"{num} {sname} {suffix[0]}"
            if key not in used_streets:
                used_streets.add(key)
                break
        city, st, z = rng.choice(PLACES)
        return f"{num} {sname} {suffix[0]}" + (f" {unit}" if unit else ""), city, st, z, suffix

    households: list[dict] = []
    people: list[dict] = []

    def person(first: str, last: str, hh: dict) -> dict:
        p = {"first": first, "last": last, "hh": hh}
        style = rng.randrange(4)
        local = [f"{first}.{last}", f"{first[0]}{last}", f"{first}{last}{rng.randint(10, 99)}", f"{last}.{first}"][style].lower()
        p["email"] = f"{local}@{rng.choice(EMAIL_DOMAINS)}"
        p["phone"] = f"207555{rng.randint(100, 999):03d}{rng.randint(0, 9)}"
        p["since"] = date(2012, 1, 1) + timedelta(days=rng.randint(0, 5000))
        p["pref"] = rng.choice(["Email", "Email", "Mail", "Phone", "Email"])
        people.append(p)
        hh["members"].append(p)
        return p

    for i in range(N_SINGLES + N_COUPLES):
        couple = i >= N_SINGLES
        unit = rng.choice(["Apt 2", "Apt 3B", "Unit 4", "Apt 1"]) if rng.random() < 0.12 else ""
        street, city, st, z, suffix = new_street(unit)
        hh = {"street": street, "city": city, "state": st, "zip": z, "suffix": suffix, "members": [], "kind": "couple" if couple else "single"}
        households.append(hh)
        f, l = next(name_iter)
        person(f, l, hh)
        if couple:
            f2, l2 = next(name_iter)
            while f2 == f:
                f2, l2 = next(name_iter)
            person(f2, l if rng.random() < 0.7 else l2, hh)
    singles = [h for h in households if h["kind"] == "single" and not re.search(r"(Apt|Unit)", h["street"])]
    online = rng.sample(singles, N_ONLINE)
    for h in online:
        h.update(street="", city="", state="", zip="", kind="online")
    remaining = [h for h in singles if h not in online]
    neighbour_pairs = []
    for k in range(N_NEIGHBOUR_PAIRS):
        a, b = rng.sample([h for h in remaining if h["kind"] == "single"], 2)
        base_street = a["street"]
        a["street"], b["street"] = f"{base_street} Apt {k + 2}", f"{base_street} Apt {k + 5}"
        b["city"], b["state"], b["zip"], b["suffix"] = a["city"], a["state"], a["zip"], a["suffix"]
        a["kind"] = b["kind"] = "neighbour"
        neighbour_pairs.append((a, b))
    assert len(households) == 150 and len(people) == 176
    assert len({norm_address(h["street"], h["zip"]) for h in households if h["street"]}) == 150 - N_ONLINE

    ids = list(range(1, len(people) + 1))
    rng.shuffle(ids)
    for p, n in zip(people, ids):
        p["num"], p["id"] = n, did(n)
        p["alias"] = None

    def street_variant(street: str, suffix: tuple[str, str]) -> str:
        full, short = suffix
        s = re.sub(rf"\b{full}\b", rng.choice([short, short + "."]), street)
        return s.upper() if rng.random() < 0.4 else s

    rows: list[dict] = []
    for h in households:
        for j, p in enumerate(h["members"]):
            street = h["street"]
            if h["kind"] == "couple" and j == 1:
                street = street_variant(street, h["suffix"])
                if rng.random() < 0.3:
                    street = street.replace(" ", "  ", 1)
            rows.append({"p": p, "role": "unique", "cells": [
                p["id"], p["first"], p["last"], p["email"], f"({p['phone'][:3]}) {p['phone'][3:6]}-{p['phone'][6:]}" if rng.random() < 0.5 else p["phone"],
                street, h["city"], h["state"], h["zip"], date_variant(p["since"], rng.choice(SAFE_DATE_STYLES)), p["pref"]]})
    couples = [h for h in households if h["kind"] == "couple"]
    plain_single_people = [h["members"][0] for h in households if h["kind"] == "single"]
    reentered = rng.sample(plain_single_people, N_REENTERED)
    next_id = len(people) + 1
    for p in reentered:
        p["alias"] = did(next_id)
        next_id += 1
        h = p["hh"]
        rows.append({"p": p, "role": "reentered", "cells": [
            p["alias"], p["first"], p["last"], p["email"].upper() if rng.random() < 0.5 else p["email"].capitalize(),
            p["phone"], street_variant(h["street"], h["suffix"]), h["city"], h["state"], h["zip"],
            date_variant(date(2026, rng.randint(1, 8), rng.randint(1, 28)), rng.choice(SAFE_DATE_STYLES)), "Email"]})
    dup_src = rng.sample([r for r in rows if r["role"] == "unique" and r["p"] not in reentered], N_EXACT_DUP_ROWS)
    rows += [{"p": r["p"], "role": "exact_duplicate", "cells": list(r["cells"])} for r in dup_src]
    rng.shuffle(rows)
    for line, r in enumerate(rows, start=2):
        r["line"] = line

    # ------------------------------------------------------------------ pledges
    pledges: list[dict] = []
    pledge_hh = rng.sample(households, N_PLEDGES - 4) + rng.sample(households, 4)
    for i, h in enumerate(pledge_hh):
        p = rng.choice(h["members"])
        installments = rng.choice([1, 1, 2, 2, 2, 4, 4])
        per = rng.choice([100, 125, 250, 300, 500, 625, 1250]) if installments > 1 else rng.choice([500, 1000, 2500, 5000])
        if installments == 12:
            per = rng.choice([25, 50, 100])
        amount = float(per * installments)
        start = date(2025, 1, 1) + timedelta(days=rng.randint(0, 520))
        start = start.replace(day=1)
        end = date(start.year + 1, start.month, 1) - timedelta(days=1)
        step = {1: 12, 2: 6, 4: 3, 12: 1}[installments]
        due = []
        for k in range(installments):
            m = start.month - 1 + k * step
            due.append(date(start.year + m // 12, m % 12 + 1, min(15, 28)))
        pledges.append({"no": f"PL-{i + 1:04d}", "num": i + 1, "person": p, "hh": h, "program": rng.choices(PROGRAMS, PROGRAM_WEIGHTS)[0],
                        "amount": amount, "per": float(per), "installments": installments, "start": start, "end": end,
                        "pledged_on": start - timedelta(days=rng.randint(5, 40)), "due": due, "payments": [],
                        "schedule": {1: "Annual", 2: "Semiannual", 4: "Quarterly", 12: "Monthly"}[installments]})
    rng.shuffle(pledges)
    for i, pl in enumerate(pledges):
        pl["no"], pl["num"] = f"PL-{i + 1:04d}", i + 1

    # ------------------------------------------------------------------ gifts
    gifts: list[dict] = []

    def add_gift(p: dict, d: date, amount: float, program: str, kind: str, pledge=None) -> dict:
        g = {"person": p, "hh": p["hh"], "date": d, "amount": round(amount, 2), "program": program, "kind": kind, "pledge": pledge}
        gifts.append(g)
        return g

    for pl in pledges:
        behind = rng.choice([0, 0, 0, 1, 2])
        paid_due = [d for d in pl["due"] if d <= LAST_GIFT_DATE]
        paid_due = paid_due[:max(0, len(paid_due) - behind)]
        for d in paid_due:
            pl["payments"].append(add_gift(pl["person"], d + timedelta(days=rng.randint(-3, 9)), pl["per"], pl["program"], "Pledge payment", pl))
    for h in households:
        n = rng.choices([0, 1, 2, 3], [33, 45, 17, 5])[0]
        for _ in range(n):
            amt = float(rng.choice(AMOUNTS))
            if rng.random() < 0.08:
                amt += rng.choice([0.5, 0.25, 12.5])
            d = date(2025, 1, 6) + timedelta(days=rng.randint(0, (LAST_GIFT_DATE - date(2025, 1, 6)).days))
            add_gift(rng.choice(h["members"]), d, amt, rng.choices(PROGRAMS, PROGRAM_WEIGHTS)[0], "One-time")

    # forced cases
    pledge_payment_gifts = [g for g in gifts if g["kind"] == "Pledge payment"]
    # the impossible pledge: end before start, fully paid
    bad_pledge = next(pl for pl in pledges if pl["installments"] == 1 and len(pl["payments"]) == 1)
    bad_pledge["end"] = bad_pledge["start"] - timedelta(days=366)
    # item 20: a quarterly pledge with exactly 3 payments; one payment filed under the unpadded pledge id
    item20 = next((pl for pl in pledges if pl["installments"] == 4 and len(pl["payments"]) == 3 and pl["per"] >= 250 and pl is not bad_pledge), None)
    if item20 is None:  # sealed variants: reshape one pledge into a 1,000.00 quarterly pledge with three payments made
        item20 = next(pl for pl in pledges if pl is not bad_pledge and pl["program"] not in ("General Operating",))
        gifts[:] = [g for g in gifts if g["pledge"] is not item20]
        item20.update(installments=4, per=250.0, amount=1000.0, schedule="Quarterly", start=date(2025, 4, 1), end=date(2026, 3, 31),
                      pledged_on=date(2025, 3, 10), due=[date(2025, 4, 15), date(2025, 7, 15), date(2025, 10, 15), date(2026, 1, 15)], payments=[])
        for d0 in item20["due"][:3]:
            item20["payments"].append(add_gift(item20["person"], d0, 250.0, item20["program"], "Pledge payment", item20))
    # item 22/23: a pledge with a remaining balance of at least 1,000 and in general operating or food pantry
    item22 = next(pl for pl in pledges if pl["amount"] - sum(g["amount"] for g in pl["payments"]) >= 1000 and pl is not item20
                  and pl is not bad_pledge and pl["program"] not in OFFICERS[RESTRICTED])
    # item 25: a household that gave to Youth Literacy and to Food Pantry
    shared_hh = next(h for h in households if h["kind"] == "single" and h["members"][0] not in reentered and
                     not any(g["hh"] is h for g in gifts))
    add_gift(shared_hh["members"][0], date(2026, 2, 14), 150.0, "Youth Literacy", "One-time")
    add_gift(shared_hh["members"][0], date(2026, 5, 3), 200.0, "Food Pantry", "One-time")
    add_gift(shared_hh["members"][0], date(2025, 11, 28), 75.0, "Food Pantry", "One-time")
    # every re-entered person gives under both ids; guarantee one clear example with gifts in both years
    re_example = reentered[0]
    add_gift(re_example, date(2025, 12, 12), 500.0, "Senior Meals", "One-time")["alias"] = True
    add_gift(re_example, date(2026, 4, 20), 100.0, "Senior Meals", "One-time")
    # three unacknowledged gifts of exactly 250.00 in 2026
    for k in range(3):
        h = rng.choice([h for h in households if h is not shared_hh])
        add_gift(rng.choice(h["members"]), date(2026, 3 + k * 2, 9 + k), 250.0, rng.choice(PROGRAMS), "One-time")["force_unack"] = True
    # a couple with different surnames where both partners give in 2026 (item 16)
    pledged_hh = {id(pl["hh"]) for pl in pledges}
    forced_couple = next(h for h in couples if h["members"][0]["last"] != h["members"][1]["last"])
    add_gift(forced_couple["members"][0], date(2026, 1, 18), 120.0, "Food Pantry", "One-time")
    add_gift(forced_couple["members"][1], date(2026, 4, 2), 80.0, "Senior Meals", "One-time")
    # a couple where one partner gave in 2025 and only the other gave in 2026 (change request 1)
    partner_hh = next(h for h in couples if h is not forced_couple and id(h) not in pledged_hh)
    gifts[:] = [g for g in gifts if g["hh"] is not partner_hh]
    add_gift(partner_hh["members"][0], date(2025, 10, 10), 100.0, "Food Pantry", "One-time")
    add_gift(partner_hh["members"][1], date(2026, 3, 22), 50.0, "Senior Meals", "One-time")
    # the top gift: a single major gift written as a dollar string
    major_hh = rng.choice([h for h in couples if h is not partner_hh and h is not forced_couple])
    top_gift = add_gift(major_hh["members"][0], date(2026, 6, 30), 15000.0, "Scholarships", "One-time")
    top_gift["force_dollar"] = True

    gifts.sort(key=lambda g: (g["date"], g["person"]["id"], g["amount"]))
    for i, g in enumerate(gifts):
        g["id"] = f"G-{10001 + i}"
        is_2026 = g["date"].year == 2026
        if g["amount"] >= LETTER_THRESHOLD:
            if g.get("force_unack"):
                g["ack"] = False
            elif g is top_gift:
                g["ack"] = True
            else:
                g["ack"] = (not is_2026) or rng.random() < 0.8
        else:
            g["ack"] = rng.random() < 0.5
    assert max(g["amount"] for g in gifts if g is not top_gift) < top_gift["amount"]

    # gift rows
    def id_text(p: dict, use_alias: bool) -> str:
        if use_alias and p["alias"]:
            return p["alias"]
        k = rng.random()
        return p["id"] if k < 0.75 else (f"D-{p['num']}" if k < 0.9 else str(p["num"]))

    def name_text(p: dict) -> str:
        return f"{p['last']}, {p['first']}" if rng.random() < 0.2 else f"{p['first']} {p['last']}"

    def amount_text(g: dict) -> str:
        v = g["amount"]
        if g.get("force_dollar"):
            return f"${v:,.2f}"
        k = rng.random()
        if k < 0.2:
            return f"${v:,.2f}"
        if k < 0.35 and v == int(v):
            return f"{int(v)}"
        return f"{v:,.2f}" if v >= 1000 and k < 0.6 else f"{v:.2f}"

    def ack_text(g: dict) -> str:
        if g["ack"]:
            return rng.choice(["Y", "Yes", "yes", f"Sent {date_variant(g['date'] + timedelta(days=rng.randint(3, 20)), 1)}"])
        return rng.choice(["", "N", ""]) if g["amount"] >= LETTER_THRESHOLD else rng.choice(["", "", "N", "n/a"])

    def pledge_id_text(pl: dict, force_unpadded: bool = False) -> str:
        if force_unpadded:
            return str(pl["num"])
        k = rng.random()
        return pl["no"] if k < 0.8 else (f"PL-{pl['num']}" if k < 0.93 else str(pl["num"]))

    gift_rows: list[dict] = []
    unpadded_done = False
    for g in gifts:
        p = g["person"]
        use_alias = bool(p["alias"]) and (g.get("alias") or rng.random() < 0.5)
        pledge_txt = ""
        if g["pledge"]:
            force = g["pledge"] is item20 and not unpadded_done and g is item20["payments"][1]
            if force:
                unpadded_done = True
            pledge_txt = pledge_id_text(g["pledge"], force)
        prog = g["program"] if rng.random() > 0.15 else rng.choice([g["program"].lower(), g["program"].upper(), g["program"] + " "])
        gift_rows.append({"g": g, "dup": False, "cells": [
            g["id"], id_text(p, use_alias), name_text(p), date_variant(g["date"], rng.choice(SAFE_DATE_STYLES)), amount_text(g),
            prog, g["kind"], pledge_txt, rng.choice(["Check", "Credit card", "Credit card", "ACH", "Cash", "Online"]), ack_text(g)]})
    assert unpadded_done
    dup_candidates = [r for r in gift_rows if r["g"]["date"].year == 2026 and r["g"] is not top_gift and r["g"]["pledge"] is None
                      and r["g"]["hh"] is not shared_hh and not r["g"].get("force_unack")]
    dup_rows = rng.sample(dup_candidates, N_DUP_GIFTS)
    gift_rows += [dict(r, cells=list(r["cells"]), dup=True) for r in dup_rows]
    order = {g["id"]: i for i, g in enumerate(gifts)}
    gift_rows.sort(key=lambda r: (order[r["g"]["id"]], r["dup"]))
    for line, r in enumerate(gift_rows, start=2):
        r["line"] = line

    # pledge rows
    pledge_rows = []
    for pl in pledges:
        p = pl["person"]
        amt = pl["amount"]
        amt_txt = f"${amt:,.2f}" if rng.random() < 0.35 else (f"{amt:,.2f}" if amt >= 1000 else f"{amt:.2f}")
        pledge_rows.append([pl["no"], id_text(p, False), name_text(p), pl["program"], amt_txt,
                            date_variant(pl["pledged_on"], rng.choice(SAFE_DATE_STYLES)), date_variant(pl["start"], rng.choice(SAFE_DATE_STYLES)),
                            date_variant(pl["end"], rng.choice(SAFE_DATE_STYLES)), pl["schedule"],
                            rng.choice(["", "", "", "Matched by employer", "Memorial pledge", "Paying by check"])])

    # ------------------------------------------------------------------ figures
    def balance(pl: dict) -> float:
        return round(pl["amount"] - sum(g["amount"] for g in pl["payments"]), 2)

    assert all(balance(pl) >= 0 for pl in pledges) and balance(bad_pledge) == 0
    ytd = [g for g in gifts if g["date"].year == 2026]
    raised_ytd = round(sum(g["amount"] for g in ytd), 2)
    ytd_one_time = round(sum(g["amount"] for g in ytd if g["kind"] == "One-time"), 2)
    ytd_pledge_pay = round(sum(g["amount"] for g in ytd if g["kind"] == "Pledge payment"), 2)
    pledged_2026 = round(sum(pl["amount"] for pl in pledges if pl["pledged_on"].year == 2026), 2)
    outstanding = round(sum(balance(pl) for pl in pledges), 2)
    owed = [g for g in gifts if g["amount"] >= LETTER_THRESHOLD and not g["ack"]]
    owed_strict = [g for g in owed if g["amount"] > LETTER_THRESHOLD]
    nia_programs = OFFICERS[RESTRICTED]
    scope_gifts = [g for g in gifts if g["program"] in nia_programs]
    nia_ytd = round(sum(g["amount"] for g in ytd if g["program"] in nia_programs), 2)
    nia_households = {id(h) for h in households if any(g["hh"] is h and g["program"] in nia_programs for g in gifts)
                      or any(pl["hh"] is h and pl["program"] in nia_programs for pl in pledges)}
    by_program = {pr: sum(1 for g in gifts if g["program"] == pr) for pr in PROGRAMS}

    # search: a single-person household with a unique surname and two to four gifts
    search_p = None
    for h in sorted(households, key=lambda h: h["members"][0]["id"]):
        if h["kind"] not in ("single", "neighbour") or h["members"][0]["alias"]:
            continue
        p = h["members"][0]
        n = sum(1 for g in gifts if g["person"] is p)
        if 2 <= n <= 4 and sum(1 for q in people if p["last"].lower() in (q["first"] + " " + q["last"]).lower()) == 1:
            search_p = p
            break
    assert search_p
    oos = next(g for g in gifts if g["program"] == "Food Pantry" and g["date"].year == 2026 and g["hh"] is not shared_hh)
    couple_example = forced_couple
    couple_rows = [r for r in rows if r["p"]["hh"] is couple_example and r["role"] == "unique"]

    def hh_total(h: dict, year=None) -> float:
        return round(sum(g["amount"] for g in gifts if g["hh"] is h and (year is None or g["date"].year == year)), 2)

    def ginfo(g: dict) -> dict:
        return {"gift": g["id"], "donor": f"{g['person']['first']} {g['person']['last']}", "date": g["date"].isoformat(),
                "amount": g["amount"], "program": g["program"], "type": g["kind"],
                "file_lines": [r["line"] for r in gift_rows if r["g"] is g]}

    def plinfo(pl: dict) -> dict:
        return {"pledge": pl["no"], "donor": f"{pl['person']['first']} {pl['person']['last']}", "program": pl["program"],
                "amount": pl["amount"], "schedule": pl["schedule"], "start": pl["start"].isoformat(), "end": pl["end"].isoformat(),
                "payments": [{"gift": g["id"], "amount": g["amount"], "pledge_id_as_written": next(r["cells"][7] for r in gift_rows if r["g"] is g)} for g in pl["payments"]],
                "balance": balance(pl)}

    def household_names(h: dict) -> list[str]:
        return [f"{m['first']} {m['last']}" for m in h["members"]]

    lapsed = [h for h in households if hh_total(h, 2025) > 0 and hh_total(h, 2026) == 0]
    lapsed_via_partner = [h for h in couples if hh_total(h, 2025) > 0 and hh_total(h, 2026) > 0 and
                          not any(g["hh"] is h and g["date"].year == 2026 and g["person"] is h["members"][0] for g in gifts) and
                          any(g["hh"] is h and g["date"].year == 2025 and g["person"] is h["members"][0] for g in gifts)]
    nia_lapsed = [h for h in households if any(g["hh"] is h and g["date"].year == 2025 and g["program"] in nia_programs for g in gifts)
                  and not any(g["hh"] is h and g["date"].year == 2026 and g["program"] in nia_programs for g in gifts)]
    major = [h for h in households if hh_total(h, 2026) >= 1000]
    near_major = sorted([h for h in households if 600 <= hh_total(h, 2026) < 1000 and h["kind"] == "single"],
                        key=lambda h: h["members"][0]["id"])
    near = near_major[0]

    counts = {
        "seed": seed,
        "organization": ORG,
        "admin": "the executive director",
        "program_officers": OFFICERS,
        "restricted_login": RESTRICTED,
        "letter_threshold": LETTER_THRESHOLD,
        "valid_for_test_dates": "year-to-date figures assume a test date from 2026-09-06 to 2026-12-31",
        "baseline": {
            "staff_role": "Program Officer",
            "viewer_role": "Viewer",
            "main_entity": "gift",
            "main_entity_plural": "gifts",
            "scope_rule": f"gifts to {RESTRICTED}'s programs, Youth Literacy and Scholarships",
            "scope_count": len(scope_gifts),
            "scope_count_if_program_matched_as_written": sum(1 for r in gift_rows if not r["dup"] and r["cells"][5] in nia_programs),
            "out_of_scope_example": ginfo(oos),
            "kpis": [
                {"name": "Raised year to date (gifts dated 2026)", "value": raised_ytd},
                {"name": "Donor households", "value": len(households)},
                {"name": "Outstanding pledges (pledge amount minus payments, summed)", "value": outstanding},
                {"name": "Acknowledgement letters owed (gifts of 250.00 or more not acknowledged)", "value": len(owed)},
            ],
            "scoped_kpi_1": nia_ytd,
            "search": {"term": search_p["last"], "donor": f"{search_p['first']} {search_p['last']}",
                       "count": sum(1 for g in gifts if g["person"] is search_p), "gifts": [g["id"] for g in gifts if g["person"] is search_p]},
            "filter": {"field": "Program", "value": "Food Pantry", "count": by_program["Food Pantry"],
                       "count_if_matched_as_written": sum(1 for r in gift_rows if not r["dup"] and r["cells"][5] == "Food Pantry")},
            "sort": {"field": "Amount", "top": ginfo(top_gift), "top_file_value": f"${top_gift['amount']:,.2f}"},
            "export": {"rows": len(gifts), "columns": ["Gift ID", "Donor", "Gift Date", "Amount", "Program"]},
            "required_field": "Program",
        },
        "donors": {
            "file_rows_excluding_header": len(rows),
            "exact_duplicate_rows": N_EXACT_DUP_ROWS,
            "reentered_rows": N_REENTERED,
            "people": len(people),
            "households": len(households),
            "household_rule": "People are one household when their street address (including any apartment or unit) and ZIP match after ignoring case, periods, extra spaces, and Street/St, Avenue/Ave, Road/Rd, Drive/Dr, Lane/Ln, Court/Ct. People with no address are each their own household. A person entered twice has the same name and the same email ignoring case.",
            "wrong_counts": {"no_dedupe": len(rows), "exact_rows_only": len(rows) - N_EXACT_DUP_ROWS, "people_not_households": len(people),
                             "units_ignored": len(households) - N_NEIGHBOUR_PAIRS, "no_address_collapsed": len(households) - (N_ONLINE - 1)},
            "couples": N_COUPLES,
            "couple_example": {"members": household_names(couple_example),
                               "streets_as_written": [r["cells"][5] for r in couple_rows], "file_lines": [r["line"] for r in couple_rows],
                               "giving_2026": hh_total(couple_example, 2026), "giving_all": hh_total(couple_example),
                               "per_member_2026": {f"{m['first']} {m['last']}": round(sum(g["amount"] for g in gifts if g["person"] is m and g["date"].year == 2026), 2) for m in couple_example["members"]}},
            "neighbour_pairs": [{"a": household_names(a)[0], "a_street": a["street"], "b": household_names(b)[0], "b_street": b["street"]} for a, b in neighbour_pairs],
            "no_address_donors": sorted(household_names(h)[0] for h in online),
            "reentered_example": {"name": f"{re_example['first']} {re_example['last']}", "ids": [re_example["id"], re_example["alias"]],
                                  "rows_as_written": sorted(({"line": r["line"], "donor_id": r["cells"][0], "email": r["cells"][3], "street": r["cells"][5]}
                                                             for r in rows if r["p"] is re_example), key=lambda x: x["line"]),
                                  "lifetime_giving": hh_total(re_example["hh"]),
                                  "giving_if_second_id_lost": round(hh_total(re_example["hh"]) - sum(r["g"]["amount"] for r in gift_rows if not r["dup"] and r["g"]["person"] is re_example and r["cells"][1] == re_example["alias"]), 2),
                                  "giving_under_second_id": round(sum(r["g"]["amount"] for r in gift_rows if not r["dup"] and r["g"]["person"] is re_example and r["cells"][1] == re_example["alias"]), 2)},
        },
        "gifts": {
            "file_rows_excluding_header": len(gift_rows),
            "duplicate_rows": N_DUP_GIFTS,
            "gifts": len(gifts),
            "per_program": by_program,
            "raised_ytd": {"total": raised_ytd, "one_time": ytd_one_time, "pledge_payments": ytd_pledge_pay,
                           "with_2026_pledge_commitments_added": round(raised_ytd + pledged_2026, 2),
                           "with_duplicate_rows_kept": round(raised_ytd + sum(r["g"]["amount"] for r in dup_rows), 2)},
            "letters_owed": {"count": len(owed), "count_if_strictly_over_250": len(owed_strict),
                             "exactly_250_unacknowledged": [ginfo(g) for g in owed if g["amount"] == LETTER_THRESHOLD]},
            "top_gift_household": household_names(major_hh),
        },
        "pledges": {
            "file_rows_excluding_header": len(pledge_rows),
            "pledges": len(pledges),
            "outstanding_total": outstanding,
            "item20_pledge": {**plinfo(item20), "household": household_names(item20["hh"])},
            "item22_pledge": {**plinfo(item22), "household": household_names(item22["hh"])},
            "end_before_start": {**plinfo(bad_pledge), "file_values": {"start": pledge_rows[pledges.index(bad_pledge)][6], "end": pledge_rows[pledges.index(bad_pledge)][7]}},
        },
        "app_items": {
            "payment_test": {"pledge": item22["no"], "payment": 500.0, "balance_before": balance(item22), "balance_after": round(balance(item22) - 500, 2),
                             "outstanding_after": round(outstanding - 500, 2), "raised_ytd_after": round(raised_ytd + 500, 2),
                             "overpayment_rejected": round(balance(item22) - 500 + 0.01, 2)},
            "letter_test": {"flagged": 250.00, "not_flagged": 249.99, "owed_after_250_gift": len(owed) + 1,
                            "donor_with_no_gifts_or_pledges": next(household_names(h)[0] for h in sorted(households, key=lambda h: h["members"][0]["id"])
                                                                  if h["kind"] == "single" and not any(g["hh"] is h for g in gifts) and not any(pl["hh"] is h for pl in pledges))},
            "restricted_households": len(nia_households),
            "restricted_gift_test_amount": 40.00,
            "shared_household": {"donor": household_names(shared_hh)[0], "visible_gifts_for_restricted": [ginfo(g) for g in gifts if g["hh"] is shared_hh and g["program"] in nia_programs],
                                 "hidden_gifts_for_restricted": [ginfo(g) for g in gifts if g["hh"] is shared_hh and g["program"] not in nia_programs]},
        },
        "changes": {
            "1_lapsed_households": len(lapsed),
            "1_lapsed_households_after_items_22_23_26": len(lapsed) - (1 if any(h is item22["hh"] for h in lapsed) else 0) - (1 if any(h is shared_hh for h in lapsed) else 0),
            "1_lapsed_example": {"household": household_names(lapsed[0]), "giving_2025": hh_total(lapsed[0], 2025)},
            "1_not_lapsed_partner_gave_2026": ({"household": household_names(lapsed_via_partner[0]), "giving_2025": hh_total(lapsed_via_partner[0], 2025),
                                                "giving_2026": hh_total(lapsed_via_partner[0], 2026)} if lapsed_via_partner else None),
            "1_lapsed_households_if_counted_per_person": sum(1 for p in people if any(g["person"] is p and g["date"].year == 2025 for g in gifts)
                                                             and not any(g["person"] is p and g["date"].year == 2026 for g in gifts)),
            "1_restricted_lapsed_households": len(nia_lapsed),
            "1_payment_test_household_in_lapsed_list": any(h is item22["hh"] for h in lapsed),
            "1_shared_household_in_lapsed_list": any(h is shared_hh for h in lapsed),
            "2_major_donor_households_2026": len(major),
            "2_payment_test_household_2026_before_and_after_items_22_23": [hh_total(item22["hh"], 2026), round(hh_total(item22["hh"], 2026) + 1000, 2)],
            "2_shared_household_2026_before_and_after_item_26": [hh_total(shared_hh, 2026), round(hh_total(shared_hh, 2026) + 40, 2)],
            "2_major_donor_households_after_items_22_23_26": len(major) + (1 if hh_total(item22["hh"], 2026) < 1000 <= hh_total(item22["hh"], 2026) + 1000 else 0)
                                                             + (1 if hh_total(shared_hh, 2026) < 1000 <= hh_total(shared_hh, 2026) + 40 else 0),
            "2_top_gift_household_tagged": household_names(major_hh),
            "2_major_threshold": 1000.00,
            "2_near_major_household": {"donor": household_names(near)[0], "giving_2026": hh_total(near, 2026), "gift_to_reach_threshold": round(1000 - hh_total(near, 2026), 2)},
        },
    }
    assert counts["changes"]["1_not_lapsed_partner_gave_2026"] is not None

    header_d = ["Donor ID", "First Name", "Last Name", "Email", "Phone", "Street", "City", "State", "ZIP", "Donor Since", "Preferred Contact"]
    header_g = ["Gift ID", "Donor ID", "Donor", "Gift Date", "Amount", "Program", "Gift Type", "Pledge ID", "Payment Method", "Acknowledged"]
    header_p = ["Pledge ID", "Donor ID", "Donor", "Program", "Pledge Amount", "Pledged On", "Start Date", "End Date", "Schedule", "Notes"]
    return {"counts": counts, "donors": (header_d, [r["cells"] for r in rows]), "gifts": (header_g, [r["cells"] for r in gift_rows]),
            "pledges": (header_p, pledge_rows)}


def main() -> None:
    seed = argparse_seed()
    out = build(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    write_csv(os.path.join(SEED_DIR, "donors.csv"), *out["donors"])
    write_csv(os.path.join(SEED_DIR, "gifts.csv"), *out["gifts"])
    write_csv(os.path.join(SEED_DIR, "pledges.csv"), *out["pledges"])
    write_text(os.path.join(REF_DIR, "counts.json"), json.dumps(out["counts"], indent=2) + "\n")
    c = out["counts"]
    print(f"donors.csv {c['donors']['file_rows_excluding_header']} rows -> {c['donors']['people']} people -> {c['donors']['households']} households; "
          f"gifts.csv {c['gifts']['file_rows_excluding_header']} rows -> {c['gifts']['gifts']}; pledges.csv {c['pledges']['file_rows_excluding_header']}; "
          f"scope {c['baseline']['scope_count']}")


if __name__ == "__main__":
    main()
