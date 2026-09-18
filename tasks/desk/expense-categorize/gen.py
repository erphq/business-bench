#!/usr/bin/env python3
"""Generator for desk/expense-categorize.

Writes workspace/ (transactions.csv, expense_policy.md, thread.txt),
reference/categorized.csv (ground truth) and reference_solution/categorized.csv
(a correct deliverable used only to validate the grader).

Deterministic: same --seed -> byte-identical output. Different seeds re-roll
names, amounts, codes, dates and row order but keep the trap structure:
  * 5 Uber rides before 09:00 or after 19:00  -> Commuting (thread override)
  * 2 Blue Bottle bean/subscription charges  -> Meals     (thread override)
  * 1 Notion charge                          -> Software  (thread override)
  * 3 opaque merchant strings                -> REVIEW
Trap rows keep fixed txn_ids across seeds so task.yaml must_match_keys stay valid.
"""
from __future__ import annotations
import argparse, csv, os, random
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

# Fixed ids for the rows task.yaml pins with must_match_keys (seed-invariant).
TRAP_IDS = {
    "uber_early_1": "TXN-4K7QD2",
    "uber_early_2": "TXN-9MW3XA",
    "uber_early_3": "TXN-2HV8PL",
    "uber_late_1":  "TXN-7RZ5NC",
    "uber_late_2":  "TXN-5TQ1JE",
    "bb_sub":       "TXN-8CX6WM",
    "bb_beans":     "TXN-3PN2YK",
    "notion":       "TXN-6LD9RT",
    "review_1":     "TXN-1SF4HB",
    "review_2":     "TXN-0GJ7VU",
    "review_3":     "TXN-2BK5ZD",
}

OWNERS = [("Dana Whitfield", "dana"), ("Marcus Oyelaran", "marcus"), ("Priya Raghavan", "priya"),
          ("Tomas Lindqvist", "tomas"), ("Elena Moreau", "elena")]
BOOKKEEPERS = [("Sam Delgado", "sam"), ("Ruth Adebayo", "ruth"), ("Kenji Okamoto", "kenji"),
               ("Leah Brennan", "leah"), ("Victor Hale", "victor")]
COMPANIES = [("Larkspur Analytics", "larkspur.co"), ("Northgate Robotics", "northgate.io"),
             ("Fernwood Studio", "fernwood.design"), ("Copperline Labs", "copperline.dev"),
             ("Halcyon Freight Software", "halcyonfs.com")]

MONTH_START = date(2026, 8, 1)
MONTH_DAYS = 28  # 1..28 August


def money(rng: random.Random, lo: float, hi: float, cents: bool = True) -> float:
    v = rng.uniform(lo, hi)
    return round(v, 2) if cents else float(round(v))


def code(rng: random.Random, n: int, alphabet: str = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789") -> str:
    return "".join(rng.choice(alphabet) for _ in range(n))


def digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def hhmm(rng: random.Random, lo_h: int, lo_m: int, hi_h: int, hi_m: int) -> str:
    lo, hi = lo_h * 60 + lo_m, hi_h * 60 + hi_m
    m = rng.randint(lo, hi)
    return f"{m // 60:02d}:{m % 60:02d}"


def rand_day(rng: random.Random, weekday_only: bool = False) -> date:
    while True:
        d = MONTH_START + timedelta(days=rng.randint(0, MONTH_DAYS - 1))
        if not weekday_only or d.weekday() < 5:
            return d


def build_rows(rng: random.Random, cards: list[str]):
    rows = []  # dicts: id, date, time, description, amount, card, category, tag

    def add(desc, amount, category, *, time=None, day=None, tid=None, tag=""):
        rows.append({
            "txn_id": tid,
            "date": day or rand_day(rng),
            "time": time or hhmm(rng, 6, 0, 22, 59),
            "description": desc,
            "amount": amount,
            "card_last4": rng.choice(cards),
            "category": category,
            "tag": tag,
        })

    # ---- trap rows (thread overrides) ----
    for k in ("uber_early_1", "uber_early_2", "uber_early_3"):
        add(f"UBER *TRIP {code(rng, 4)}", money(rng, 14, 38), "Commuting",
            time=hhmm(rng, 6, 5, 8, 50), day=rand_day(rng, True), tid=TRAP_IDS[k], tag=k)
    for k in ("uber_late_1", "uber_late_2"):
        add(f"UBER *TRIP {code(rng, 4)}", money(rng, 16, 44), "Commuting",
            time=hhmm(rng, 19, 10, 23, 30), day=rand_day(rng, True), tid=TRAP_IDS[k], tag=k)
    add("BLUE BOTTLE COFFEE SUBSCRIPTION", money(rng, 44, 68), "Meals",
        time=hhmm(rng, 3, 0, 6, 30), tid=TRAP_IDS["bb_sub"], tag="bb_sub")
    add("BLUEBOTTLECOFFEE.COM OAKLAND CA", money(rng, 28, 52), "Meals",
        tid=TRAP_IDS["bb_beans"], tag="bb_beans")
    add("NOTION LABS INC", money(rng, 80, 160), "Software",
        time=hhmm(rng, 0, 5, 5, 55), tid=TRAP_IDS["notion"], tag="notion")

    # ---- genuinely unplaceable rows -> REVIEW ----
    add(f"PAYPAL *{rng.choice(['RMARTINEZ', 'JKOWALSKI', 'DNGUYEN', 'AFERREIRA'])} 4029357733",
        money(rng, 180, 520), "REVIEW", tid=TRAP_IDS["review_1"], tag="review_1")
    pos_day = rand_day(rng)
    add(f"PURCHASE {pos_day.month:02d}{pos_day.day:02d} TERM {digits(rng, 4)} SAN JOSE CA",
        money(rng, 40, 140), "REVIEW", day=pos_day, tid=TRAP_IDS["review_2"], tag="review_2")
    add(f"SP HLDNGS CO {digits(rng, 4)} REF {digits(rng, 5)}",
        money(rng, 120, 340), "REVIEW", tid=TRAP_IDS["review_3"], tag="review_3")

    # ---- controls that look like traps but are not ----
    for _ in range(3):  # midday Ubers stay Travel
        add(f"UBER *TRIP {code(rng, 4)}", money(rng, 12, 46), "Travel", time=hhmm(rng, 10, 5, 17, 40))
    for _ in range(2):  # Lyft, midday only (thread only speaks about Uber)
        add(f"LYFT *RIDE {rng.choice(['MON', 'TUE', 'WED', 'THU', 'FRI'])} {rng.randint(1, 4)}PM",
            money(rng, 11, 34), "Travel", time=hhmm(rng, 11, 0, 16, 30))
    add("SQ *BLUE BOTTLE COFFEE", money(rng, 6, 14), "Meals", time=hhmm(rng, 8, 0, 11, 0))
    add("UBER *EATS PENDING", money(rng, 38, 92), "Meals", time=hhmm(rng, 12, 0, 13, 30))

    # ---- fillers ----
    software = [
        (f"GOOGLE *GSUITE_{code(rng, 6).lower()}", (72, 210)), (f"SLACK T0{code(rng, 7)}", (60, 180)),
        ("ZOOM.US 888-799-9666", (14, 60)), ("GITHUB INC", (16, 84)),
        ("ADOBE *CREATIVE CLOUD", (54, 120)), ("FIGMA MONTHLY RENEWAL", (15, 75)),
        ("1PASSWORD", (7, 40)), (f"DROPBOX*{code(rng, 8)}", (11, 60)),
        ("AMAZON WEB SERVICES AWS.AMAZON.CO", (140, 620)), ("LINEAR ORBIT INC", (24, 96)),
        ("VERCEL INC", (20, 120)), ("OPENAI *CHATGPT SUBSCR", (20, 60)),
        ("TWILIO INC", (18, 90)), ("ATLASSIAN", (30, 110)), ("SENTRY.IO", (26, 80)),
        ("HUBSPOT INC", (45, 180)),
    ]
    travel = [
        (f"DELTA AIR 006{digits(rng, 10)}", (240, 720)), (f"UNITED 016{digits(rng, 10)}", (210, 640)),
        (f"ALASKA AIR 027{digits(rng, 10)}", (150, 420)), ("MARRIOTT SF MARQUIS", (260, 540)),
        ("HILTON GARDEN INN AUSTIN", (180, 320)), ("HERTZ RENT-A-CAR", (120, 380)),
        ("SFO LONG TERM PARKING", (36, 110)), ("AMTRAK .COM", (40, 160)),
        ("HOTELTONIGHT", (140, 300)), (f"SOUTHWEST 526{digits(rng, 10)}", (120, 380)),
        ("HYATT REGENCY DENVER", (200, 450)),
    ]
    meals = [
        ("DOORDASH*SWEETGREEN", (28, 96)), ("TST* SOUVLA - HAYES", (24, 88)),
        (f"CHIPOTLE {digits(rng, 4)}", (11, 48)), (f"STARBUCKS STORE {digits(rng, 5)}", (5, 22)),
        ("PHILZ COFFEE", (5, 18)), ("SQ *TARTINE BAKERY", (9, 42)),
        ("GRUBHUB*THAI HOUSE", (30, 110)), ("SQ *SIGHTGLASS COFFEE", (6, 20)),
        ("TST* NOPA", (60, 240)), ("PANERA BREAD #4412", (14, 70)),
        ("ZUNI CAFE", (70, 260)), ("SQ *THE MILL", (6, 24)), ("CAVIAR*CATERING", (120, 420)),
    ]
    office = [
        (f"AMZN Mktp US*{code(rng, 9)}", (12, 240)), (f"AMZN Mktp US*{code(rng, 9)}", (12, 240)),
        (f"AMZN Mktp US*{code(rng, 9)}", (12, 240)), (f"AMZN Mktp US*{code(rng, 9)}", (12, 240)),
        (f"AMZN Mktp US*{code(rng, 9)}", (12, 240)), (f"AMAZON.COM*{code(rng, 8)}", (20, 180)),
        (f"STAPLES {digits(rng, 5)}", (18, 140)), ("WEWORK 535 MISSION", (2200, 3400)),
        (f"COSTCO WHSE #{digits(rng, 4)}", (80, 320)), ("IKEA EMERYVILLE", (60, 480)),
        (f"OFFICE DEPOT #{digits(rng, 4)}", (15, 120)), (f"THE HOME DEPOT #{digits(rng, 4)}", (20, 160)),
        ("SPARKLE OFFICE CLEANING", (180, 320)), ("INSTACART*KITCHEN", (60, 190)),
        ("CB2 STORE 0231", (90, 420)),
    ]
    commuting = [
        ("CLIPPER SYSTEMS AUTOLOAD", (20, 80)), ("BART SFIA", (4, 16)), ("CALTRAIN MOBILE", (6, 30)),
        ("FASTRAK CSC", (25, 75)), (f"IMPARK {digits(rng, 5)} SF", (12, 40)),
        (f"SP+ PARKING {digits(rng, 5)}", (14, 45)), ("CLIPPER SYSTEMS AUTOLOAD", (20, 80)),
        ("BART EMBR", (4, 16)),
    ]
    marketing = [
        (f"GOOGLE *ADS {digits(rng, 10)}", (300, 1800)), (f"FACEBK *{code(rng, 9)}", (150, 900)),
        ("MAILCHIMP", (40, 160)), (f"CANVA* {digits(rng, 5)}-{digits(rng, 4)}", (13, 60)),
        ("LINKEDIN *ADS", (120, 600)), ("VISTAPRINT", (60, 260)), ("EVENTBRITE SPONSORSHIP", (250, 900)),
        ("SEMRUSH", (100, 260)), ("MOO.COM PRINT", (40, 140)),
    ]
    shipping = [
        (f"USPS PO {digits(rng, 10)}", (6, 60)), (f"FEDEX {digits(rng, 11)}", (14, 120)),
        (f"UPS*1Z{code(rng, 16, '0123456789ABCDEFGHJKLMNPQRSTUVWXYZ')}", (12, 90)),
        ("SHIPSTATION", (30, 110)), ("ULINE *SHIP SUPPLIES", (60, 380)), ("STAMPS.COM", (18, 40)),
        ("DHL EXPRESS", (40, 180)), (f"USPS PO {digits(rng, 10)}", (6, 60)),
    ]
    profees = [
        ("GUSTO PAYROLL FEE", (80, 260)), ("BILL.COM", (45, 120)), ("LEGALZOOM.COM", (80, 360)),
        (f"UPWORK -{digits(rng, 7)}", (200, 1400)), ("NORTHWEST REGISTERED AGENT", (100, 160)),
        ("RIVERA & CO CPA", (400, 1200)), ("ROCKET LAWYER", (40, 90)),
    ]
    for cat, items in (("Software", software), ("Travel", travel), ("Meals", meals), ("Office", office),
                       ("Commuting", commuting), ("Marketing", marketing), ("Shipping", shipping),
                       ("Professional Fees", profees)):
        for desc, (lo, hi) in items:
            add(desc, money(rng, lo, hi), cat)

    # Second filler pass to reach ~120 rows.
    extra = [
        ("Office", f"AMZN Mktp US*{code(rng, 9)}", (12, 240)),
        ("Office", f"AMZN Mktp US*{code(rng, 9)}", (12, 240)),
        ("Office", f"AMZN Mktp US*{code(rng, 9)}", (12, 240)),
        ("Software", "GOOGLE *CLOUD " + digits(rng, 8), (30, 260)),
        ("Software", "MICROSOFT*M365 BUSINESS", (25, 150)),
        ("Meals", "DOORDASH*CHIPOTLE", (24, 70)),
        ("Meals", f"SQ *BOBA GUYS {digits(rng, 3)}", (8, 30)),
        ("Shipping", f"FEDEX {digits(rng, 11)}", (14, 120)),
        ("Marketing", f"GOOGLE *ADS {digits(rng, 10)}", (300, 1800)),
        ("Travel", "HERTZ RENT-A-CAR", (120, 380)),
        ("Commuting", "CALTRAIN MOBILE", (6, 30)),
    ]
    for cat, desc, (lo, hi) in extra:
        add(desc, money(rng, lo, hi), cat)
    for _ in range(2):  # two more midday Ubers (Travel)
        add(f"UBER *TRIP {code(rng, 4)}", money(rng, 12, 46), "Travel", time=hhmm(rng, 10, 5, 17, 40))

    # A couple of refunds (negative) to keep the export honest.
    add(f"AMZN Mktp US*{code(rng, 9)} REFUND", -money(rng, 18, 90), "Office")
    add(f"DELTA AIR 006{digits(rng, 10)} REFUND", -money(rng, 60, 220), "Travel")
    return rows


def assign_ids(rng: random.Random, rows):
    used = set(TRAP_IDS.values())
    for r in rows:
        if r["txn_id"]:
            continue
        while True:
            c = f"TXN-{code(rng, 6, '0123456789ABCDEFGHJKLMNPQRSTUVWXYZ')}"
            if c not in used:
                used.add(c)
                r["txn_id"] = c
                break


def policy_md(company: str) -> str:
    return f"""# {company} — card expense policy (v3, effective January 2026)

Every card charge gets exactly one category. Use only the categories below.

| Category | Rule |
|---|---|
| Software | SaaS and cloud subscriptions: Google Workspace, Slack, Zoom, GitHub, AWS, Figma, Adobe, 1Password, Dropbox, Linear, Vercel, Twilio, Atlassian and similar. |
| Travel | Airfare, hotels, rental cars, rideshare (Uber, Lyft), airport parking, Amtrak and train tickets for trips. |
| Meals | Restaurants, cafes, coffee shops, food delivery (DoorDash, Grubhub, Uber Eats, Caviar), catering, meeting snacks. |
| Office | Office supplies, furniture, kitchen stock, cleaning, coworking rent (WeWork), Amazon purchases by default, and the office coffee-bean subscription (Blue Bottle). |
| Commuting | Clipper, BART, Caltrain, monthly parking garages (Impark, SP+), FasTrak tolls. |
| Marketing | Ad platforms (Google Ads, Meta/Facebook, LinkedIn Ads), Mailchimp, Canva, Semrush, Notion (content calendar), event sponsorships, print collateral (Vistaprint, Moo). |
| Shipping | USPS, FedEx, UPS, DHL, ShipStation, Stamps.com, Uline packaging. |
| Professional Fees | Legal, accounting, registered agent, payroll and contractor platform fees (Gusto, Bill.com), Upwork contractors, LegalZoom, Rocket Lawyer. |

Notes

- Refunds take the same category as the original charge.
- If the description does not let you place a charge, mark it REVIEW rather than guessing. The owner clears REVIEW items at month end.
"""


def thread_txt(owner, bk, company, domain) -> str:
    oname, ofirst = owner
    bname, bfirst = bk
    return f"""From: {bname} <{bfirst}@{domain}>
To: {oname} <{ofirst}@{domain}>
Date: Sat, 29 Aug 2026 09:12
Subject: August card coding — a few questions

Hi {ofirst.capitalize()},

Starting on the August card statement today. Before I code everything per the
January policy, a few things I noticed:

- A lot of Uber rides this month, several at odd hours (early morning / late night).
- Blue Bottle shows up as both the bean subscription and cafe stops.
- Notion billed again.
- A few charges I can't identify at all from the description.

Should I just follow the policy doc as written?

{bname}
Bookkeeper, {company}


From: {oname} <{ofirst}@{domain}>
To: {bname} <{bfirst}@{domain}>
Date: Sat, 29 Aug 2026 14:47
Subject: Re: August card coding — a few questions

Mostly yes, the policy stands. Amazon is Office unless I tell you otherwise.
For the ones you can't identify, don't guess — flag them and I'll look.
Let me think about the Uber thing, I'll come back to you on it.

{oname}


From: {bname} <{bfirst}@{domain}>
To: {oname} <{ofirst}@{domain}>
Date: Sun, 30 Aug 2026 18:03
Subject: Re: August card coding — a few questions

Thanks. Draft is done: all Ubers under Travel per policy, the Blue Bottle
subscription under Office and the cafe stops under Meals, Notion under Marketing
like last month. Tell me if you want anything changed before I close August.

{bname}


From: {oname} <{ofirst}@{domain}>
To: {bname} <{bfirst}@{domain}>
Date: Mon, 31 Aug 2026 08:21
Subject: Re: August card coding — a few questions

Three changes for August, please:

1. Uber: rides before 9am or after 7pm are people getting to and from the
   office. Code those as Commuting, not Travel. Midday Ubers are client visits
   and stay Travel.
2. Blue Bottle: put anything from Blue Bottle under Meals — subscription, beans,
   cafe, all of it. I don't want to keep splitting it.
3. Notion: engineering took the workspace over this month, so the Notion charge
   is Software from this month on, not Marketing.

Everything else exactly per the policy doc. Anything you genuinely can't place,
mark it REVIEW and I'll clear it.

{oname}


From: {bname} <{bfirst}@{domain}>
To: {oname} <{ofirst}@{domain}>
Date: Mon, 31 Aug 2026 09:02
Subject: Re: August card coding — a few questions

Got it — applying those three to the August file now. Final version tonight.

{bname}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    owner = OWNERS[args.seed % len(OWNERS)]
    bk = BOOKKEEPERS[(args.seed // len(OWNERS)) % len(BOOKKEEPERS)]
    company, domain = COMPANIES[(args.seed // 3) % len(COMPANIES)]
    cards = rng.sample(["4417", "8830", "2291", "6104", "7752"], 3)

    rows = build_rows(rng, cards)
    assign_ids(rng, rows)
    rows.sort(key=lambda r: (r["date"], r["time"], r["txn_id"]))

    ws = os.path.join(HERE, "workspace")
    ref = os.path.join(HERE, "reference")
    sol = os.path.join(HERE, "reference_solution")
    for d in (ws, ref, sol):
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))

    in_cols = ["txn_id", "date", "time", "description", "amount", "card_last4"]
    with open(os.path.join(ws, "transactions.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(in_cols)
        for r in rows:
            w.writerow([r["txn_id"], r["date"].isoformat(), r["time"], r["description"],
                        f"{r['amount']:.2f}", r["card_last4"]])
    with open(os.path.join(ws, "expense_policy.md"), "w") as f:
        f.write(policy_md(company))
    with open(os.path.join(ws, "thread.txt"), "w") as f:
        f.write(thread_txt(owner, bk, company, domain))

    out_cols = in_cols + ["category"]
    for d in (ref, sol):
        with open(os.path.join(d, "categorized.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(out_cols)
            for r in rows:
                w.writerow([r["txn_id"], r["date"].isoformat(), r["time"], r["description"],
                            f"{r['amount']:.2f}", r["card_last4"], r["category"]])

    n_trap = sum(1 for r in rows if r["tag"] and not r["tag"].startswith("review"))
    n_rev = sum(1 for r in rows if r["category"] == "REVIEW")
    print(f"seed={args.seed} rows={len(rows)} trap_rows={n_trap} review_rows={n_rev}")
    print("must_match_keys:", ", ".join(sorted(TRAP_IDS.values())))


if __name__ == "__main__":
    main()
