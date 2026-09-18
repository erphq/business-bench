#!/usr/bin/env python3
"""card-expense-coding: an electrical contractor's company-card export coded to GL accounts by the kind of
purchase (merchant category code), with a travel meal per diem, personal charges and a review list.

    python gen.py [--seed N] [--naive DIR]

Business: Hollowell Electric gives five field and office staff company cards. The policy codes by item type
(the merchant category on the card feed) plus the job number in the cardholder's memo, not by merchant name:
the same Home Depot can be job materials, shop supplies or capitalised equipment.

Traps (each caught by a check, see task.yaml):
  * same merchant, three accounts: job number -> 5100, else $2,500 or more -> 1520, else 6120  (check: gl accounts)
  * travel meals on approved trip days capped per person per day, 75% on travel days          (checks: gl accounts; employee owes)
  * a meal the day after the trip ends is ordinary 6400, uncapped                              (checks: gl accounts; employee owes)
  * personal item types and memos marked personal -> 1350, owed in full, on the review list    (checks: gl accounts; employee owes; review list)
  * general merchandise without a job number and categories the table lacks -> review, blank   (checks: gl accounts; review list)
  * declined authorisations in the export are not charges                                      (check: row count)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

RATE, TRAVEL_DAY = 70.00, 52.50
MONTH0, MONTH1 = date(2026, 8, 1), date(2026, 8, 31)
TEMPLATE = ["txn_id", "cardholder", "amount", "gl_account", "employee_owes"]

SUPPLY = {  # mcc: (category text, merchants)
    "5065": ("Electrical Parts and Equipment", ["GRAYBAR ELECTRIC 0412", "CED CONSOLIDATED ELEC", "PLATT ELECTRIC SUPPLY", "BORDER STATES #118"]),
    "5251": ("Hardware Stores", ["ACE HARDWARE #7714", "TRUE VALUE 2231"]),
    "5200": ("Home Supply Warehouse Stores", ["THE HOME DEPOT #4402", "LOWES #01872"]),
    "5085": ("Industrial Supplies", ["GRAINGER 912", "FASTENAL CO01ORBOI"]),
}
FUEL = {"5541": ("Service Stations", ["SHELL OIL 57444", "CHEVRON 0204377"]), "5542": ("Automated Fuel Dispensers", ["PACIFIC PRIDE 118", "MAVERIK #412"])}
AUTO = {"5533": ("Automotive Parts and Accessories Stores", ["OREILLY AUTO 3321", "NAPA AUTO PARTS 44"]), "7538": ("Automotive Service Shops", ["JIFFY LUBE #1442"])}
TRAVEL = {"7011": ("Hotels, Motels, Resorts", ["HAMPTON INN BOISE DT", "MARRIOTT SPOKANE DT"]), "4511": ("Airlines, Air Carriers", ["ALASKA AIR 0272154488213"]),
          "7512": ("Car Rental Agencies", ["ENTERPRISE RENT-A-CAR"])}
MEALS = {"5812": ("Eating Places, Restaurants", ["RED ROBIN #212", "OLIVE GARDEN 1120", "TST* ANTHEM TACOMA"]),
         "5814": ("Fast Food Restaurants", ["CHIPOTLE 1882", "MCDONALD'S F12344", "SUBWAY 04411"])}
MEAL_PLACES = {  # where the meals happen: (restaurant merchants, fast-food merchants)
    "home": (["RED ROBIN #212", "OLIVE GARDEN 1120", "TST* ANTHEM TACOMA"], ["CHIPOTLE 1882", "MCDONALD'S F12344", "SUBWAY 04411"]),
    "Boise": (["TST* FORK BOISE", "SQ *BASQUE MARKET BOISE", "BARDENAY BOISE"], ["BOISE FRY CO", "PAPA MURPHYS 0412 BOISE"]),
    "Spokane": (["TST* RIVER CAFE SPOKANE", "DAVENPORT GRILL SPOKANE"], ["SQ *ROCKET BAKERY SPOK", "WENDYS #3312 SPOKANE"]),
    "Portland": (["TST* PINE STATE PDX", "DESCHUTES PUB PDX"], ["BURGERVILLE #22 PDX"]),
}
SOFTWARE = {"5734": ("Computer Software Stores", ["AUTODESK *ACAD LT"]), "5817": ("Digital Goods: Applications", ["DROPBOX*7HQ2KD"]),
            "7372": ("Computer Programming, Data Processing", ["SERVICETITAN INC", "PROCORE TECHNOLOGIES"])}
GOV = {"9399": ("Government Services", ["CITY OF BOISE PERMITS", "L&I ELECTRICAL PERMIT"])}
GENERAL = {"5399": ("Misc. General Merchandise", ["AMAZON MKTPL*2K4JR7", "AMAZON MKTPL*8Q1ZM3"]), "5300": ("Wholesale Clubs", ["COSTCO WHSE #0891"]),
           "5310": ("Discount Stores", ["TARGET 00012345"]), "5311": ("Department Stores", ["WALMART #3401"])}
PERSONAL = {"5813": ("Drinking Places (Alcoholic Beverages)", ["THE TAPROOM BOISE"]), "5921": ("Package Stores - Beer, Wine, Liquor", ["TOTAL WINE #1102"]),
            "4899": ("Cable, Satellite and Other Pay Television", ["NETFLIX.COM"]), "7832": ("Motion Picture Theaters", ["REGAL CINEMAS 0661"])}
UNLISTED = {"7399": ("Business Services - Not Elsewhere Classified", ["SQ *JMR SERVICES"]), "5999": ("Miscellaneous and Specialty Retail", ["PAYPAL *KLINEMARKET"])}


def build(seed: int) -> dict:
    r = rng(seed)
    names = [f"{f} {l}" for f, l in people(r, 5)]
    field_a, field_b, office, field_c, field_d = names
    jobs = [f"J-{n}" for n in r.sample(range(4400, 4620), 6)]
    txns = []

    def add(holder, day, mcc_table, mcc, amount, memo="", kind="", merchant=None, status="Posted"):
        cat, merchants = mcc_table[mcc]
        txns.append({"holder": holder, "date": day, "mcc": mcc, "category": cat, "merchant": merchant or r.choice(merchants),
                     "amount": round(amount, 2), "memo": memo, "kind": kind, "status": status})

    def wd(lo=MONTH0, hi=MONTH1):
        return day_in(r, lo, hi, weekday_only=True)

    # ---- trips ----
    trip_a = (date(2026, 8, 10), date(2026, 8, 13), field_a, "Boise", jobs[0])
    trip_b = (date(2026, 8, 24), date(2026, 8, 26), field_b, "Spokane", "NECA code-update training")
    trips = [trip_a, trip_b]

    # ---- supply-house purchases: job number / shop / capitalised ----
    for holder in (field_a, field_b, field_c, field_d):
        for _ in range(r.randint(3, 5)):
            mcc = r.choice(list(SUPPLY))
            job = r.choice(jobs)
            memo = r.choice([f"{job} conduit + boxes", f"wire for {job}", f"{job} panel parts", f"breakers {job}", f"{job}"])
            add(holder, wd(), SUPPLY, mcc, money(r, 38, 1900), memo, "job")
        for _ in range(r.randint(1, 3)):
            mcc = r.choice(list(SUPPLY))
            memo = r.choice(["shop stock - wire nuts, tape", "van restock", "drill bits", "", "replacement fish tape", "ladder hooks for van"])
            add(holder, wd(), SUPPLY, mcc, money(r, 18, 640), memo, "shop")
    add(field_c, wd(), SUPPLY, "5200", 2500.00, "Milwaukee cable puller - shop", "cap_exact", merchant="THE HOME DEPOT #4402")
    add(field_d, wd(), SUPPLY, "5085", money(r, 2650, 4800), "thermal imaging camera", "cap", merchant="GRAINGER 912")
    add(field_a, wd(), SUPPLY, "5200", money(r, 2380, 2499), "rolling job box + gang box", "shop_just_under", merchant="THE HOME DEPOT #4402")
    add(field_b, wd(), SUPPLY, "5065", money(r, 2800, 5200), f"{jobs[1]} switchgear order", "job_big", merchant="GRAYBAR ELECTRIC 0412")

    # ---- fuel, auto, software, permits ----
    for holder in (field_a, field_b, field_c, field_d):
        for _ in range(r.randint(2, 4)):
            mcc = r.choice(list(FUEL))
            add(holder, wd(), FUEL, mcc, money(r, 48, 128), "", "fuel")
    add(field_c, wd(), AUTO, "5533", money(r, 40, 260), "van 7 brake light + fuses", "auto")
    add(field_d, wd(), AUTO, "7538", money(r, 70, 140), "van 3 oil change", "auto")
    for mcc in SOFTWARE:
        add(office, wd(), SOFTWARE, mcc, money(r, 15, 480), "", "software")
    add(office, wd(), GOV, "9399", money(r, 85, 420), f"{jobs[2]} permit", "permit")
    add(field_b, wd(), GOV, "9399", money(r, 60, 180), "permit", "permit")

    # ---- travel: lodging / air / car ----
    add(field_a, trip_a[0], TRAVEL, "7011", money(r, 420, 690), "Boise job - 3 nights", "travel", merchant="HAMPTON INN BOISE DT")
    add(field_a, trip_a[0] - timedelta(days=9), TRAVEL, "4511", money(r, 240, 460), "flight to Boise", "travel")
    add(field_b, trip_b[0], TRAVEL, "7011", money(r, 300, 520), "training hotel", "travel", merchant="MARRIOTT SPOKANE DT")
    add(field_b, trip_b[0], TRAVEL, "7512", money(r, 140, 260), "", "travel")

    # ---- meals ----
    def meal(holder, day, amount, kind, place="home"):
        rest, fast = MEAL_PLACES[place]
        mcc = "5814" if amount < 30 and r.random() < 0.6 else "5812"
        add(holder, day, MEALS, mcc, amount, r.choice(["", "", "dinner", "lunch", "breakfast"]), kind,
            merchant=r.choice(fast if mcc == "5814" else rest))

    # trip A: depart day under the 75% cap, a full day with two meals over 70, a full day under, return day over 52.50
    meal(field_a, trip_a[0], money(r, 24, 49), "trip_meal", "Boise")
    m1 = money(r, 14, 24); meal(field_a, trip_a[0] + timedelta(days=1), m1, "trip_meal", "Boise")
    meal(field_a, trip_a[0] + timedelta(days=1), round(money(r, 76, 96) - m1, 2), "trip_meal", "Boise")
    meal(field_a, trip_a[0] + timedelta(days=2), money(r, 56, 66), "trip_meal", "Boise")
    meal(field_a, trip_a[1], money(r, 57, 68), "trip_meal", "Boise")
    meal(field_a, trip_a[1] + timedelta(days=1), money(r, 74, 118), "local_meal")          # day after return, back home
    # trip B: travel day over 52.50 but under 70, full day with three meals, return day under
    meal(field_b, trip_b[0], money(r, 55, 67), "trip_meal", "Spokane")
    for amt in (money(r, 9, 16), money(r, 17, 26), money(r, 48, 72)):
        meal(field_b, trip_b[0] + timedelta(days=1), amt, "trip_meal", "Spokane")
    meal(field_b, trip_b[1], money(r, 18, 40), "trip_meal", "Spokane")
    # a trip that was never approved: meals are ordinary 6400
    meal(field_c, date(2026, 8, 18), money(r, 58, 68), "pending_trip_meal", "Portland")
    meal(field_c, date(2026, 8, 19), money(r, 78, 112), "pending_trip_meal", "Portland")
    # ordinary meals at home, some large
    for holder in (office, field_d, field_b):
        for _ in range(r.randint(1, 2)):
            day = wd(MONTH0, date(2026, 8, 21))
            meal(holder, day, money(r, 22, 180), "local_meal")

    # ---- general merchandise ----
    add(office, wd(), GENERAL, "5399", money(r, 30, 240), "", "review_blank", merchant="AMAZON MKTPL*2K4JR7")
    add(field_c, wd(), GENERAL, "5300", money(r, 60, 210), "crew water + snacks", "review_nojob", merchant="COSTCO WHSE #0891")
    add(field_d, wd(), GENERAL, "5311", money(r, 25, 160), f"{jobs[3]} extension cords + work lights", "gen_job", merchant="WALMART #3401")
    add(office, wd(), GENERAL, "5399", money(r, 20, 140), f"label tape for {jobs[4]} panel schedule", "gen_job", merchant="AMAZON MKTPL*8Q1ZM3")
    add(field_b, wd(), GENERAL, "5310", money(r, 40, 120), "personal - sorry, grabbed the wrong card, will pay back", "personal_memo",
        merchant="TARGET 00012345")
    # ---- personal item types ----
    add(field_a, trip_a[0] + timedelta(days=2), PERSONAL, "5813", money(r, 28, 74), "", "personal_type", merchant="THE TAPROOM BOISE")
    add(office, wd(), PERSONAL, "4899", 22.99, "", "personal_type", merchant="NETFLIX.COM")
    add(field_c, wd(), PERSONAL, "5921", money(r, 30, 90), "crew bbq", "personal_type", merchant="TOTAL WINE #1102")
    # ---- categories the policy table does not list ----
    add(office, wd(), UNLISTED, "7399", money(r, 120, 480), "", "review_unlisted")
    add(field_d, wd(), UNLISTED, "5999", money(r, 35, 150), "misc", "review_unlisted")
    # ---- declined ----
    add(field_c, wd(), FUEL, "5541", money(r, 60, 110), "", "declined", status="Declined")
    add(office, wd(), SOFTWARE, "7372", money(r, 199, 399), "", "declined", status="Declined")
    add(field_a, trip_a[0] + timedelta(days=1), TRAVEL, "7011", money(r, 150, 210), "", "declined", merchant="HAMPTON INN BOISE DT", status="Declined")

    txns.sort(key=lambda t: (t["date"], t["holder"], t["merchant"]))
    used = set()
    for t in txns:
        while True:
            tid = "CX" + code(r, 8, "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ")
            if tid not in used:
                used.add(tid); t["id"] = tid; break

    # ---- truth ----
    trip_days = {}
    for d0, d1, holder, _, _ in trips:
        k = d0
        while k <= d1:
            trip_days[(holder, k)] = TRAVEL_DAY if k in (d0, d1) else RATE
            k += timedelta(days=1)
    day_meals = {}
    for t in txns:
        if t["status"] != "Posted":
            continue
        t["owes"] = 0.0
        if t["mcc"] in PERSONAL or t["kind"] == "personal_memo":
            t["gl"], t["owes"], t["review"] = "1350", t["amount"], "personal charge - cardholder owes it back"
        elif t["mcc"] in SUPPLY or t["mcc"] in GENERAL:
            has_job = any(j in t["memo"] for j in jobs)
            if has_job:
                t["gl"], t["review"] = "5100", ""
            elif t["mcc"] in GENERAL:
                t["gl"], t["review"] = "", "general merchandise with no job number - cannot tell what was bought"
            elif t["amount"] >= 2500:
                t["gl"], t["review"] = "1520", ""
            else:
                t["gl"], t["review"] = "6120", ""
        elif t["mcc"] in FUEL:
            t["gl"], t["review"] = "6210", ""
        elif t["mcc"] in AUTO:
            t["gl"], t["review"] = "6220", ""
        elif t["mcc"] in TRAVEL:
            t["gl"], t["review"] = "6310", ""
        elif t["mcc"] in SOFTWARE:
            t["gl"], t["review"] = "6510", ""
        elif t["mcc"] in GOV:
            t["gl"], t["review"] = "6610", ""
        elif t["mcc"] in MEALS:
            if (t["holder"], t["date"]) in trip_days:
                t["gl"], t["review"] = "6320", ""
                day_meals.setdefault((t["holder"], t["date"]), []).append(t)
            else:
                t["gl"], t["review"] = "6400", ""
        else:
            t["gl"], t["review"] = "", "merchant category not covered by the policy"
    overage = {}
    for key, ms in day_meals.items():
        cap = trip_days[key]
        total = round(sum(m["amount"] for m in ms), 2)
        over = round(max(0.0, total - cap), 2)
        overage[key] = {"cap": cap, "total": total, "over": over, "ids": [m["id"] for m in ms]}
        if over > 0:
            biggest = max(ms, key=lambda m: (m["amount"], m["id"]))
            biggest["owes"] = over
            biggest["review"] = f"travel meals over the per diem on {key[1].isoformat()} (cap {cap:.2f}, spent {total:.2f})"
    return {"txns": txns, "trips": trips, "jobs": jobs, "overage": overage, "names": names}


def posted(d):
    return [t for t in d["txns"] if t["status"] == "Posted"]


def acceptable(d: dict) -> bool:
    ov = d["overage"]
    a_days = sorted(k for k in ov if k[0] == d["trips"][0][2])
    b_days = sorted(k for k in ov if k[0] == d["trips"][1][2])
    if len(a_days) != 4 or len(b_days) != 3:
        return False
    # A: depart under cap, day 2 over 70, day 3 under, return over 52.50; B: travel day between 52.50 and 70, day 2 over, return under
    want = [ov[a_days[0]]["over"] == 0, ov[a_days[1]]["over"] > 3, ov[a_days[2]]["over"] == 0, ov[a_days[3]]["over"] > 3,
            52.5 + 1 < ov[b_days[0]]["total"] < 70 - 1, ov[b_days[1]]["over"] > 3, ov[b_days[2]]["over"] == 0]
    if not all(want):
        return False
    # per-meal capping must differ from per-day capping on the multi-meal days
    for k in (a_days[1], b_days[1]):
        per_meal = 0  # every single meal under the daily cap
        ms = [t for t in d["txns"] if t["id"] in ov[k]["ids"]]
        if any(m["amount"] > RATE for m in ms):
            return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 3)
    tx = d["txns"]

    write_csv(os.path.join(ws, "card_transactions_2026-08.csv"),
              ["Transaction ID", "Date", "Cardholder", "Merchant", "MCC", "Merchant Category", "Amount", "Status", "Memo"],
              [[t["id"], date_variant(t["date"], 0), t["holder"], t["merchant"], t["mcc"], t["category"], f"{t['amount']:.2f}", t["status"], t["memo"]]
               for t in tx])
    trip_rows = [[holder, dest, date_variant(d0, 1), date_variant(d1, 1), purpose, "Approved"] for d0, d1, holder, dest, purpose in d["trips"]]
    trip_rows.insert(1, [d["names"][3], "Portland", "08/18/2026", "08/19/2026", "Vendor visit - Platt regional office", "Pending"])
    write_csv(os.path.join(ws, "approved_travel_2026-08.csv"), ["Traveler", "Destination", "Depart", "Return", "Purpose", "Status"], trip_rows)
    write_csv(os.path.join(ws, "coding_import_template.csv"), TEMPLATE, [["CX00000000", "Jane Example", "125.40", "6120", "0.00"]])
    write_text(os.path.join(ws, "card_policy_2026.md"), policy_text())

    # ---- reference / solution ----
    p = posted(d)
    rows = [[t["id"], t["holder"], f"{t['amount']:.2f}", t["gl"], f"{t['owes']:.2f}"] for t in p]
    write_csv(os.path.join(ref, "coded.csv"), TEMPLATE, rows)
    write_csv(os.path.join(sol, "coded.csv"), TEMPLATE, rows)
    rv = [[t["id"], t["holder"], f"{t['amount']:.2f}", t["review"]] for t in p if t["review"]]
    write_csv(os.path.join(ref, "review.csv"), ["txn_id", "cardholder", "amount", "reason"], rv)
    write_csv(os.path.join(sol, "review.csv"), ["txn_id", "cardholder", "amount", "reason"], rv)
    write_json(os.path.join(ref, "owes.json"), {
        "review_required": sorted(t["id"] for t in p if t["review"] and t["mcc"] not in MEALS),
        "meal_days_over": [v["ids"] for k, v in sorted(d["overage"].items()) if v["over"] > 0],
        "meal_days": [{"cardholder": k[0], "date": k[1].isoformat(), "cap": v["cap"], "spent": v["total"], "over": v["over"], "txn_ids": v["ids"]}
                      for k, v in sorted(d["overage"].items())],
        "personal": {t["id"]: t["amount"] for t in p if t["gl"] == "1350"},
        "total_owed": round(sum(t["owes"] for t in p), 2)})

    trap_ids = sorted(t["id"] for t in p if t["kind"] in ("cap", "cap_exact", "shop_just_under", "job_big", "trip_meal", "local_meal", "review_blank",
                                                         "review_nojob", "gen_job", "personal_memo", "personal_type", "review_unlisted", "pending_trip_meal")
                      and not (t["kind"] == "local_meal" and t["holder"] not in (d["trips"][0][2],)))
    a = d["trips"][0]
    write_task_yaml(HERE, {
        "id": "card-expense-coding", "track": "desk", "category": "bookkeeping",
        "title": "Code August company-card charges to the ledger by item type",
        "ask": ("Please code August's company card charges to our accounts following the card policy, and give me coded.csv for "
                "the import plus review.csv with everything I need to look at. Everything you need is in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the policy codes by merchant category and the memo, not by merchant name: Home Depot, Graybar or Grainger is 5100 "
            "when the memo carries a job number, otherwise 6120, or 1520 when a single charge is $2,500 or more; a merchant-name "
            "lookup cannot get all three (check: gl accounts)",
            "one shop tool costs exactly $2,500.00 and capitalises, a job box at just under stays 6120, and a switchgear order "
            "over $2,500 with a job number stays job materials (check: gl accounts)",
            "restaurant charges on approved trip days are travel meals capped at $70 per person per day and $52.50 on the "
            "departure and return days; meals on the same day are added together before the cap, and the excess is owed back "
            "(checks: gl accounts; employee owes)",
            f"{a[2]} eats out the day after the Boise trip ends and that meal is ordinary 6400, uncapped; {d['names'][3]}'s Portland "
            "trip in the travel file was never approved, so those meals are 6400 with nothing owed (checks: gl accounts; employee owes)",
            "bars, liquor stores and streaming are item types the policy never pays and a Target charge's memo says it was "
            "personal; all go to 1350, owed in full, and onto the review list (checks: gl accounts; employee owes; review list)",
            "general-merchandise merchants (Amazon, Costco) without a job number and two merchant categories the policy "
            "table does not cover get a blank account and go to review rather than a guess (checks: gl accounts; review list)",
            "three declined authorisations sit in the export with amounts; they never charged the card (checks: one row per charge; "
            "review list)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "import columns", "path": "coded.csv", "columns": ["txn_id", "gl_account", "employee_owes"]},
            {"type": "csv_row_count", "name": "one row per charge", "path": "coded.csv", "equals_ref": "coded.csv"},
            {"type": "csv_set_equal", "name": "every posted charge coded", "path": "coded.csv", "column": "txn_id", "ref": "coded.csv"},
            {"type": "csv_values_match", "name": "gl accounts", "path": "coded.csv", "ref": "coded.csv", "key": "txn_id",
             "columns": ["gl_account"], "normalize": ["strip", "lower"], "min_accuracy": 0.97, "must_match_keys": trap_ids},
            {"type": "custom", "name": "employee owes", "module": "check.py"},
            {"type": "custom", "name": "review list", "module": "check_review.py"},
            {"type": "csv_columns", "name": "review list says why", "path": "review.csv", "columns": ["txn_id", "reason"]},
        ],
    })
    print(f"seed={seed}: {len(tx)} rows, {len(p)} posted, {len(rv)} to review, owed {sum(t['owes'] for t in p):.2f}")
    for k, v in sorted(d["overage"].items()):
        print("  ", k[0], k[1], v)


def policy_text() -> str:
    return """# Hollowell Electric - company card policy (revised March 2026)

Every posted charge on a company card is coded to one account below, or sent to review. We code by **what kind of
purchase it is** - the merchant category (MCC) the card network reports - together with the cardholder's memo.
Do not code from the merchant's name: the same store sells job materials, shop supplies and equipment.

## Accounts

| Account | Name |
|---|---|
| 1350 | Due from employee |
| 1520 | Tools & equipment (capitalised) |
| 5100 | Job materials (billable) |
| 6120 | Shop supplies & small tools |
| 6210 | Vehicle fuel |
| 6220 | Vehicle repairs & parts |
| 6310 | Travel - lodging, air, car rental |
| 6320 | Travel meals (per diem) |
| 6400 | Meals - team & client |
| 6510 | Software & subscriptions |
| 6610 | Permits & licences |

## Item types

| Merchant categories (MCC) | How to code |
|---|---|
| 5065 Electrical parts & equipment, 5251 Hardware stores, 5200 Home supply warehouse, 5085 Industrial supplies | If the memo carries a job number (J- and four digits), 5100 whatever the amount. Otherwise it is for the shop: 6120, except that a single charge of $2,500.00 or more is equipment and goes to 1520. |
| 5541 Service stations, 5542 Automated fuel dispensers | 6210 |
| 5533 Automotive parts, 7538 Automotive service shops | 6220 |
| 7011 Hotels, 4511 Airlines, 7512 Car rental | 6310 |
| 5812 Restaurants, 5814 Fast food | On an approved trip day: 6320, subject to the per diem below. Any other day: 6400. |
| 5734 Software stores, 5817 Digital goods: applications, 7372 Computer programming / data processing | 6510 |
| 9399 Government services | 6610 |
| 5399 Misc. general merchandise, 5300 Wholesale clubs, 5310 Discount stores, 5311 Department stores | These stores sell everything, so the category tells us nothing. 5100 if the memo carries a job number; otherwise send it to review with no account. |
| 5813 Drinking places, 5921 Package stores (beer, wine, liquor), 4899 Cable / streaming TV, 7832 Movie theatres | Never company expenses. Personal - see below. |

A merchant category that is not in this table goes to review with no account.

## Travel meal per diem

On an approved trip (see the travel approvals file; only trips with status Approved count) meals are covered up
to **$70.00 per person per day**, all meals that day added together. On the day you leave and the day you come
back the limit is 75%, **$52.50**. Code the meals to 6320 and record anything above the day's limit as owed by the
cardholder (take it off that day's largest meal). Trip days run from the departure date to the return date, both
included.

## Personal charges

Anything in a personal category above, and any charge whose memo says it was personal, is coded 1350 Due from
employee and the cardholder owes the full amount back.

## For the import and the review list

coded.csv follows coding_import_template.csv: one row per posted charge. gl_account is the four-digit account, or
blank when the charge goes to review without one. employee_owes is what the cardholder has to pay back (0.00 when
nothing). Declined authorisations are not charges.

review.csv lists every charge you could not code and every charge where the cardholder owes money back - one row per
transaction with its txn_id, cardholder, amount and a short reason.
"""


def write_naive(d: dict, out: str) -> None:
    """Code by merchant name keyword, every meal to 6400, nothing owed, review only blank-account rows, declined rows kept."""
    os.makedirs(out, exist_ok=True)
    rows, rv = [], []
    for t in d["txns"]:
        m = t["mcc"]
        gl = "6120" if m in SUPPLY else "6210" if m in FUEL else "6220" if m in AUTO else "6310" if m in TRAVEL else \
             "6400" if m in MEALS else "6510" if m in SOFTWARE else "6610" if m in GOV else "6120" if m in GENERAL else ""
        rows.append([t["id"], t["holder"], f"{t['amount']:.2f}", gl, "0.00"])
        if not gl:
            rv.append([t["id"], t["holder"], f"{t['amount']:.2f}", "unknown"])
    write_csv(os.path.join(out, "coded.csv"), TEMPLATE, rows)
    write_csv(os.path.join(out, "review.csv"), ["txn_id", "cardholder", "amount", "reason"], rv)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        s = a.seed * 1000 + attempt
        if acceptable(build(s)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(s, a.naive)
