#!/usr/bin/env python3
"""Deterministic seed generator for the crm-sales-pipeline build task.

    python gen.py [--seed N]

Writes:
  seed/accounts.csv       80 rows from a shared spreadsheet -> 72 accounts (exact duplicates, website-variant
                          duplicates with the name in capitals, blank websites, revenue as mixed strings)
  seed/contacts.csv       150 rows (BOM + CRLF) -> 142 contacts (exact and email-case duplicates, blank emails,
                          two different people with the same name, account names in caps or with trailing spaces)
  seed/deals.csv          90 deals under a two-line report preamble: stage case variants and "Closed Won/Lost",
                          currency-string amounts, blank amounts on early deals, mixed date formats, contact
                          emails in a different case, owner names in lower case, one impossible negative amount
  reference/counts.json   every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the canonical public variant (checklist.md quotes its numbers). Other seeds re-roll companies,
people, owners, stages, and amounts; counts.json is recomputed from the truth, so a sealed variant
re-derives its checklist numbers from it.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import FIRST, LAST, argparse_seed, date_variant, phone_variant, write_csv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

REPS = [("Tomasz Nowak", 28), ("Leila Haddad", 26), ("Rahul Patel", 18)]  # accounts per rep -> 72
RESTRICTED_REP = "Leila Haddad"
OTHER_REP = "Tomasz Nowak"
STAGES = ["Lead", "Qualified", "Proposal", "Negotiation", "Won", "Lost"]
OPEN_STAGES = ["Lead", "Qualified", "Proposal", "Negotiation"]
PROB = {"Lead": 0.10, "Qualified": 0.25, "Proposal": 0.50, "Negotiation": 0.75, "Won": 1.0, "Lost": 0.0}
STAGE_COUNTS = {"Lead": 18, "Qualified": 20, "Proposal": 17, "Negotiation": 12, "Won": 13, "Lost": 10}  # 90
LOST_REASONS = ["Price", "Timing", "Competitor", "No decision", "Scope"]

N_ACCOUNTS = 72
N_ACCOUNT_EXACT_DUPES = 5
N_ACCOUNT_WEBSITE_DUPES = 3
N_ACCOUNT_BLANK_WEBSITE = 4
N_CONTACTS = 142
N_CONTACT_EXACT_DUPES = 2
N_CONTACT_EMAIL_CASE_DUPES = 6
N_CONTACT_BLANK_EMAIL = 5
N_CONTACT_TRAILING_SPACE_ACCOUNT = 4
N_DEALS = 90
N_BLANK_AMOUNT_LEADS = 4
NEGATIVE_AMOUNT = -4500.0
MAX_AMOUNT = 185000.0
LATEST_CLOSE = date(2027, 6, 30)

ACCOUNT_COLUMNS = ["Account", "Website", "Industry", "City", "State", "Owner", "Annual Revenue", "Created", "Notes"]
CONTACT_COLUMNS = ["First Name", "Last Name", "Title", "Email", "Phone", "Account", "Primary"]
DEAL_COLUMNS = ["Deal", "Account", "Contact Email", "Owner", "Stage", "Amount", "Expected Close", "Created", "Lost Reason", "Source"]

COMPANIES = [
    ("Ashgrove Manufacturing", "ashgrovemfg.com", "Manufacturing"), ("Bellwether Logistics", "bellwetherlogistics.com", "Logistics"),
    ("Cairn Health Partners", "cairnhealth.org", "Healthcare"), ("Delta Ridge Foods", "deltaridgefoods.com", "Food & Beverage"),
    ("Evergreen Credit Union", "evergreencu.org", "Financial"), ("Fairhaven Senior Living", "fairhavensl.com", "Healthcare"),
    ("Granite State Tooling", "granitestatetooling.com", "Manufacturing"), ("Harborview Insurance Group", "harborviewins.com", "Insurance"),
    ("Ironbark Construction", "ironbarkbuild.com", "Construction"), ("Juniper Software", "junipersoft.io", "Software"),
    ("Kestrel Aviation Services", "kestrelaviation.com", "Aviation"), ("Lumen Dental Group", "lumendental.com", "Healthcare"),
    ("Marlow & Finch LLP", "marlowfinch.com", "Legal"), ("Northwind Energy Cooperative", "northwindenergy.coop", "Energy"),
    ("Oakline Furniture", "oaklinefurniture.com", "Manufacturing"), ("Pinecrest Schools Trust", "pinecrestschools.org", "Education"),
    ("Quarterdeck Marine", "quarterdeckmarine.com", "Marine"), ("Redstone Property Group", "redstonepg.com", "Real Estate"),
    ("Silverbrook Pharmacy Network", "silverbrookrx.com", "Healthcare"), ("Tidewater Packaging", "tidewaterpkg.com", "Manufacturing"),
    ("Umber Creative Agency", "umbercreative.com", "Media"), ("Vantage Fleet Solutions", "vantagefleet.com", "Logistics"),
    ("Westbridge Community Bank", "westbridgebank.com", "Financial"), ("Yarrow Organics", "yarroworganics.com", "Food & Beverage"),
    ("Zenith Precision Optics", "zenithoptics.com", "Manufacturing"), ("Alder Street Clinics", "alderclinics.com", "Healthcare"),
    ("Brightwater Utilities", "brightwaterutil.com", "Utilities"), ("Coppermine Analytics", "copperminedata.com", "Software"),
    ("Dunmore Hospitality", "dunmorehotels.com", "Hospitality"), ("Ellery Textiles", "ellerytextiles.com", "Manufacturing"),
    ("Foxhollow Veterinary Group", "foxhollowvets.com", "Healthcare"), ("Glenmoor Title & Escrow", "glenmoortitle.com", "Real Estate"),
    ("Highfield Robotics", "highfieldrobotics.com", "Manufacturing"), ("Inlet Seafood Distributors", "inletseafood.com", "Food & Beverage"),
    ("Jasper Ridge Winery", "jasperridgewine.com", "Food & Beverage"), ("Kingsway Transit Authority", "kingswaytransit.gov", "Public Sector"),
    ("Larkfield Printing", "larkfieldprint.com", "Print"), ("Millbrook Orthopedics", "millbrookortho.com", "Healthcare"),
    ("Nightingale Home Care", "nightingalehc.com", "Healthcare"), ("Orchard Valley Farms Co-op", "orchardvalleycoop.com", "Agriculture"),
    ("Parkstone Engineering", "parkstoneeng.com", "Engineering"), ("Quillon Cybersecurity", "quillonsec.com", "Software"),
    ("Riverlane Apartments", "riverlaneliving.com", "Real Estate"), ("Stonefield Auto Group", "stonefieldauto.com", "Automotive"),
    ("Thornbury Chemicals", "thornburychem.com", "Chemicals"), ("Ultramar Shipping", "ultramarshipping.com", "Logistics"),
    ("Verity Accounting Partners", "verityaccounting.com", "Professional Services"), ("Wolfcreek Outdoor Co.", "wolfcreekoutdoor.com", "Retail"),
    ("Amberly Cosmetics", "amberlybeauty.com", "Consumer Goods"), ("Blackmoor Steel", "blackmoorsteel.com", "Manufacturing"),
    ("Crestline Charter Schools", "crestlinecharter.org", "Education"), ("Driftwood Studios", "driftwoodstudios.tv", "Media"),
    ("Eastgate Medical Supply", "eastgatemed.com", "Healthcare"), ("Fenwick Elevator Co.", "fenwickelevator.com", "Construction"),
    ("Goldleaf Tea Importers", "goldleaftea.com", "Food & Beverage"), ("Hartwell Plastics", "hartwellplastics.com", "Manufacturing"),
    ("Islandview Resorts", "islandviewresorts.com", "Hospitality"), ("Juno Pet Foods", "junopetfoods.com", "Consumer Goods"),
    ("Kettleridge Brewing", "kettleridgebrew.com", "Food & Beverage"), ("Lindenwood Assisted Living", "lindenwoodal.com", "Healthcare"),
    ("Mosaic Staffing", "mosaicstaffing.com", "Professional Services"), ("Norwich Tool & Die", "norwichtool.com", "Manufacturing"),
    ("Opaline Jewelers", "opalinejewelers.com", "Retail"), ("Pilgrim Freight Lines", "pilgrimfreight.com", "Logistics"),
    ("Quenchwell Beverages", "quenchwell.com", "Food & Beverage"), ("Rosemont Law Group", "rosemontlaw.com", "Legal"),
    ("Sable Point Lighthouse Foundation", "sablepointlh.org", "Nonprofit"), ("Trailhead Bicycles", "trailheadbikes.com", "Retail"),
    ("Underwood Paper Mills", "underwoodpaper.com", "Manufacturing"), ("Valencia Solar", "valenciasolar.com", "Energy"),
    ("Whitlock Aerospace Components", "whitlockaero.com", "Aerospace"), ("Xander Data Centers", "xanderdc.com", "Software"),
    ("Yellowstone Ranch Supply", "yellowstoneranch.com", "Agriculture"), ("Zephyr Cold Chain", "zephyrcoldchain.com", "Logistics"),
    ("Arbor Lane Childcare", "arborlanekids.com", "Education"), ("Brixton Fasteners", "brixtonfasteners.com", "Manufacturing"),
    ("Clearwater Dialysis Centers", "clearwaterdialysis.com", "Healthcare"), ("Dovetail Cabinetry", "dovetailcabinets.com", "Manufacturing"),
]
CITIES = [("Portland", "OR"), ("Seattle", "WA"), ("Tacoma", "WA"), ("Boise", "ID"), ("Spokane", "WA"), ("Eugene", "OR"),
          ("Bend", "OR"), ("Salem", "OR"), ("Bellevue", "WA"), ("Vancouver", "WA"), ("Olympia", "WA"), ("Medford", "OR")]
TITLES = ["CEO", "CFO", "COO", "VP Operations", "VP Finance", "Controller", "Director of Operations", "Head of Procurement",
          "Office Manager", "General Manager", "Owner", "Managing Partner", "Director of IT", "HR Director", "Plant Manager"]
SERVICES = ["Pricing study", "Operations assessment", "Market entry plan", "Annual retainer", "Strategy offsite",
            "Supply chain review", "Sales playbook", "Customer research", "Due diligence support", "Interim CFO",
            "Process redesign", "Data strategy", "Cost reduction program", "Succession planning", "Board advisory"]
SOURCES = ["Referral", "Inbound", "Event", "Outbound", "Partner", ""]
NOTES = ["", "", "", "", "Prefers email", "Budget resets in January", "Met at trade show", "Referred by a client",
         "Slow to pay - net 60", "Board approves over 50k", "Decision maker is the COO", "Renewal each October"]
AMOUNT_POOL = [8000, 9500, 12000, 15000, 18000, 20000, 22500, 25000, 28000, 30000, 32000, 35000, 40000, 42000, 45000,
               48000, 50000, 55000, 60000, 65000, 72000, 75000, 80000, 85000, 90000, 96000, 105000, 110000, 120000,
               125000, 135000, 140000, 150000, 160000, 175000]
D_STYLES = [0, 1, 2, 3, 4, 6]  # never day-first


def money(v: float) -> str:
    return f"${v:,.2f}"


def build(rng: random.Random) -> dict:
    rep_names = [r for r, _ in REPS]
    rep_first = {r.split()[0] for r in rep_names}
    rep_last = {r.split()[1] for r in rep_names}

    # ------------------------------------------------------------------ accounts
    pool = list(COMPANIES)
    rng.shuffle(pool)
    owners = [rep for rep, n in REPS for _ in range(n)]
    rng.shuffle(owners)
    accounts = []
    for i, (name, domain, industry) in enumerate(pool[:N_ACCOUNTS]):
        city, st = rng.choice(CITIES)
        accounts.append({
            "name": name, "domain": domain, "industry": industry, "city": city, "state": st, "owner": owners[i],
            "revenue": rng.choice([0, 0, 800000, 1200000, 2500000, 4200000, 6000000, 9500000, 15000000, 22000000, 40000000]),
            "created": date(2023, 1, 9) + timedelta(days=rng.randint(0, 1300)), "notes": rng.choice(NOTES),
        })
    idx = list(range(N_ACCOUNTS))
    rng.shuffle(idx)
    blank_web = idx[:N_ACCOUNT_BLANK_WEBSITE]
    web_dupe_src = idx[N_ACCOUNT_BLANK_WEBSITE:N_ACCOUNT_BLANK_WEBSITE + N_ACCOUNT_WEBSITE_DUPES]
    k = N_ACCOUNT_BLANK_WEBSITE + N_ACCOUNT_WEBSITE_DUPES
    exact_src = idx[k:k + N_ACCOUNT_EXACT_DUPES]
    for i, a in enumerate(accounts):
        a["website_written"] = "" if i in blank_web else rng.choice(
            [a["domain"], "www." + a["domain"], "https://" + a["domain"], "https://www." + a["domain"] + "/"])

    def account_row(a, name_written=None, website_written=None, created=None):
        rev = a["revenue"]
        rev_s = "" if rev == 0 else [f"{rev}", f"${rev:,.0f}", f"{rev:,}"][rng.randrange(3)]
        return [name_written or a["name"], a["website_written"] if website_written is None else website_written,
                a["industry"], a["city"], a["state"], a["owner"], rev_s,
                date_variant(created or a["created"], rng.choice(D_STYLES)), a["notes"]]

    account_rows = [(i, "unique", account_row(a)) for i, a in enumerate(accounts)]
    for i in exact_src:
        account_rows.append((i, "exact_duplicate", list(account_rows[i][2])))
    web_groups = []
    for i in web_dupe_src:
        a = accounts[i]
        variant = rng.choice(["WWW." + a["domain"].upper(), "http://www." + a["domain"] + "/", a["domain"].upper()])
        account_rows.append((i, "website_variant_duplicate",
                             account_row(a, name_written=a["name"].upper(), website_written=variant,
                                         created=a["created"] - timedelta(days=rng.randint(30, 400)))))
        web_groups.append({"account": a["name"], "owner": a["owner"], "websites_as_written": [a["website_written"], variant],
                           "names_as_written": [a["name"], a["name"].upper()]})
    rng.shuffle(account_rows)

    # ------------------------------------------------------------------ contacts
    name_pairs = [(f, l) for f in FIRST for l in LAST if f not in rep_first and l not in rep_last]
    rng.shuffle(name_pairs)
    per_account = [1] * N_ACCOUNTS
    extra = N_CONTACTS - N_ACCOUNTS
    while extra > 0:
        j = rng.randrange(N_ACCOUNTS)
        if per_account[j] < 3:
            per_account[j] += 1
            extra -= 1
    contacts = []
    pi = 0
    for ai, a in enumerate(accounts):
        for c in range(per_account[ai]):
            first, last = name_pairs[pi]
            pi += 1
            contacts.append({"first": first, "last": last, "title": rng.choice(TITLES),
                             "email": f"{first}.{last}@{a['domain']}".lower(),
                             "phone": phone_variant(f"{rng.choice(['206', '503', '425', '971', '360'])}555{rng.randint(1000, 9999):04d}", rng.randrange(7)),
                             "account_index": ai, "primary": "Y" if c == 0 else "N"})
    # two different people with the same name at different accounts (a name-based dedupe merges them)
    secondaries = [i for i, c in enumerate(contacts) if c["primary"] == "N"]
    twin_a, twin_b = rng.sample(secondaries, 2)
    while contacts[twin_a]["account_index"] == contacts[twin_b]["account_index"]:
        twin_a, twin_b = rng.sample(secondaries, 2)
    contacts[twin_b]["first"], contacts[twin_b]["last"] = contacts[twin_a]["first"], contacts[twin_a]["last"]
    contacts[twin_b]["email"] = f"{contacts[twin_a]['first'][0]}{contacts[twin_a]['last']}@{accounts[contacts[twin_b]['account_index']]['domain']}".lower()
    reserved = {twin_a, twin_b}
    blank_pool = [i for i in secondaries if i not in reserved]
    rng.shuffle(blank_pool)
    blank_email_c = blank_pool[:N_CONTACT_BLANK_EMAIL]
    rest = [i for i in range(N_CONTACTS) if i not in reserved and i not in blank_email_c]
    rng.shuffle(rest)
    case_dupe_c = rest[:N_CONTACT_EMAIL_CASE_DUPES]
    exact_dupe_c = rest[N_CONTACT_EMAIL_CASE_DUPES:N_CONTACT_EMAIL_CASE_DUPES + N_CONTACT_EXACT_DUPES]
    k = N_CONTACT_EMAIL_CASE_DUPES + N_CONTACT_EXACT_DUPES
    trailing_c = rest[k:k + N_CONTACT_TRAILING_SPACE_ACCOUNT]
    for i in blank_email_c:
        contacts[i]["email"] = ""

    def contact_row(c, email=None, account_written=None, phone=None, title=None):
        a = accounts[c["account_index"]]
        return [c["first"], c["last"], title or c["title"], c["email"] if email is None else email, phone or c["phone"],
                a["name"] if account_written is None else account_written, c["primary"]]

    contact_rows = []
    for i, c in enumerate(contacts):
        a = accounts[c["account_index"]]
        written = a["name"].upper() if (c["account_index"] in web_dupe_src and rng.random() < 0.5) else a["name"]
        if i in trailing_c:
            written += " "
        contact_rows.append((i, "unique", contact_row(c, account_written=written)))
    for i in exact_dupe_c:
        contact_rows.append((i, "exact_duplicate", list(contact_rows[i][2])))
    case_groups = []
    for i in case_dupe_c:
        c = contacts[i]
        local, _, dom = c["email"].partition("@")
        variant = rng.choice([c["email"].upper(), local.title() + "@" + dom, local + "@" + dom.upper()])
        digits = "".join(ch for ch in c["phone"] if ch.isdigit())[-10:]
        contact_rows.append((i, "email_case_duplicate",
                             contact_row(c, email=variant, phone=phone_variant(digits, rng.randrange(7)), title=rng.choice(TITLES))))
        case_groups.append({"contact": f"{c['first']} {c['last']}", "account": accounts[c["account_index"]]["name"],
                            "emails_as_written": [c["email"], variant]})
    rng.shuffle(contact_rows)

    # ------------------------------------------------------------------ deals
    stage_list = [s for s, n in STAGE_COUNTS.items() for _ in range(n)]
    rng.shuffle(stage_list)
    deal_acct, per_acct_deals = [], [0] * N_ACCOUNTS
    order = list(range(N_ACCOUNTS))
    rng.shuffle(order)
    for ai in order[:60]:
        deal_acct.append(ai)
        per_acct_deals[ai] += 1
    while len(deal_acct) < N_DEALS:
        ai = rng.randrange(N_ACCOUNTS)
        if per_acct_deals[ai] < 3:
            deal_acct.append(ai)
            per_acct_deals[ai] += 1
    rng.shuffle(deal_acct)
    deals, used_names = [], set()
    for n in range(N_DEALS):
        ai = deal_acct[n]
        a = accounts[ai]
        stage = stage_list[n]
        name = f"{a['name']} - {rng.choice(SERVICES)}"
        while name in used_names:
            name = f"{a['name']} - {rng.choice(SERVICES)}"
        used_names.add(name)
        if stage in ("Won", "Lost"):
            created = date(2025, 9, 1) + timedelta(days=rng.randint(0, 300))
            close = created + timedelta(days=rng.randint(20, 120))
        else:
            created = date(2026, 1, 5) + timedelta(days=rng.randint(0, 240))
            close = date(2026, 10, 1) + timedelta(days=rng.randint(0, 270))
        with_email = [ci for ci, c in enumerate(contacts) if c["account_index"] == ai and c["email"]]
        contact = rng.choice(with_email) if (stage not in ("Lead", "Qualified") or rng.random() < 0.5) else None
        deals.append({"name": name, "account_index": ai, "owner": a["owner"], "stage": stage,
                      "amount": float(rng.choice(AMOUNT_POOL)), "created": created, "close": close, "contact": contact,
                      "lost_reason": rng.choice(LOST_REASONS) if stage == "Lost" else "", "source": rng.choice(SOURCES)})

    def pick_deal(cond, exclude=()):
        return sorted((i for i, d in enumerate(deals) if cond(d) and i not in exclude), key=lambda i: deals[i]["name"])

    max_deal = rng.choice(pick_deal(lambda d: d["stage"] in ("Qualified", "Proposal", "Negotiation")))
    deals[max_deal]["amount"] = MAX_AMOUNT
    neg_deal = rng.choice(pick_deal(lambda d: d["stage"] == "Lost"))
    deals[neg_deal]["amount"] = NEGATIVE_AMOUNT
    late_deal = rng.choice(pick_deal(lambda d: d["stage"] in ("Qualified", "Proposal"), exclude=(max_deal,)))
    deals[late_deal]["close"] = LATEST_CLOSE
    blank_amount = rng.sample(pick_deal(lambda d: d["stage"] == "Lead" and d["owner"] != RESTRICTED_REP), N_BLANK_AMOUNT_LEADS)
    for i in blank_amount:
        deals[i]["amount"] = 0.0
        deals[i]["contact"] = None
    taken = {max_deal, neg_deal, late_deal, *blank_amount}

    # the restricted rep needs a Proposal deal of 55k-150k (weighted move; later the >50k Won approval) and a
    # Negotiation deal of 50k or less (change 1 win-rate move); swap stages with another of her deals if the draw lacks one
    def ensure(stage, lo, hi):
        c = pick_deal(lambda d: d["owner"] == RESTRICTED_REP and d["stage"] == stage and lo <= d["amount"] <= hi, exclude=taken)
        if c:
            return c[0]
        c = pick_deal(lambda d: d["owner"] == RESTRICTED_REP and d["stage"] == stage, exclude=taken)
        donor = pick_deal(lambda d: d["owner"] == RESTRICTED_REP and d["stage"] in OPEN_STAGES and lo <= d["amount"] <= hi, exclude=taken)
        i, j = c[0], donor[0]
        deals[i]["amount"], deals[j]["amount"] = deals[j]["amount"], deals[i]["amount"]
        return i

    move_deal = ensure("Proposal", 55000, 150000)
    taken.add(move_deal)
    win_deal = ensure("Negotiation", 8000, 50000)
    taken.add(win_deal)
    assert [sum(1 for d in deals if d["stage"] == s) for s in STAGES] == [STAGE_COUNTS[s] for s in STAGES]

    currency_idx = set(rng.sample([i for i in range(N_DEALS) if i not in taken], 20)) | {max_deal}
    stage_variants = {"Lead": ["lead", "LEAD"], "Qualified": ["qualified", "QUALIFIED"], "Proposal": ["proposal", "PROPOSAL"],
                      "Negotiation": ["negotiation", "NEGOTIATION"], "Won": ["won", "Closed Won", "Closed Won"],
                      "Lost": ["lost", "Closed Lost", "Closed Lost"]}
    deal_rows = []
    for i, d in enumerate(deals):
        if i == neg_deal:
            amt_w = "-4,500.00"
        elif d["amount"] == 0:
            amt_w = ""
        elif i in currency_idx:
            amt_w = money(d["amount"])
        else:
            amt_w = f"{d['amount']:.0f}"
        stage_w = rng.choice(stage_variants[d["stage"]]) if rng.random() < 0.35 else d["stage"]
        owner_w = d["owner"].lower() if rng.random() < 0.12 else d["owner"]
        email_w = ""
        if d["contact"] is not None:
            email_w = contacts[d["contact"]]["email"]
            if rng.random() < 0.15:
                email_w = email_w.upper()
        close_style = 6 if i == late_deal else rng.choice(D_STYLES)
        deal_rows.append((i, [d["name"], accounts[d["account_index"]]["name"], email_w, owner_w, stage_w, amt_w,
                              date_variant(d["close"], close_style), date_variant(d["created"], rng.choice(D_STYLES)),
                              d["lost_reason"], d["source"]]))
    rng.shuffle(deal_rows)

    # ------------------------------------------------------------------ truth
    def amt(d):
        return max(d["amount"], 0.0)

    def open_deals(owner=None):
        return [d for d in deals if d["stage"] in OPEN_STAGES and (owner is None or d["owner"] == owner)]

    def weighted(owner=None):
        return round(sum(amt(d) * PROB[d["stage"]] for d in open_deals(owner)), 2)

    def won_value(owner=None):
        return round(sum(amt(d) for d in deals if d["stage"] == "Won" and (owner is None or d["owner"] == owner)), 2)

    per_rep = {}
    for r in rep_names:
        acct_ids = [i for i, a in enumerate(accounts) if a["owner"] == r]
        won = sum(1 for d in deals if d["stage"] == "Won" and d["owner"] == r)
        lost = sum(1 for d in deals if d["stage"] == "Lost" and d["owner"] == r)
        per_rep[r] = {
            "accounts": len(acct_ids), "contacts": sum(1 for c in contacts if c["account_index"] in acct_ids),
            "deals": sum(1 for d in deals if d["owner"] == r), "open_deals": len(open_deals(r)),
            "open_pipeline_value": round(sum(amt(d) for d in open_deals(r)), 2), "weighted_pipeline": weighted(r),
            "won_deals": won, "lost_deals": lost, "won_value": won_value(r),
            "win_rate_percent": round(100.0 * won / (won + lost), 1) if won + lost else None,
        }

    two_deal = [ai for ai in range(N_ACCOUNTS) if per_acct_deals[ai] == 2
                and not any(accounts[ai]["name"].lower() in accounts[o]["name"].lower() for o in range(N_ACCOUNTS) if o != ai)
                and not any(accounts[ai]["name"].lower() in s.lower() for s in SERVICES)]
    search_ai = sorted(two_deal, key=lambda ai: accounts[ai]["name"])[0]
    oos_deal = deals[pick_deal(lambda d: d["owner"] == OTHER_REP and d["stage"] in OPEN_STAGES and d["account_index"] != search_ai, exclude=taken)[0]]
    oos_acct = sorted((a for a in accounts if a["owner"] == OTHER_REP), key=lambda a: a["name"])[0]
    trailing_first = sorted(trailing_c)[0]
    trailing_acct_ai = contacts[trailing_first]["account_index"]
    by_amount_text = sorted(deal_rows, key=lambda r: r[1][5], reverse=True)
    by_close_text = sorted(deal_rows, key=lambda r: r[1][6], reverse=True)
    mv, wd = deals[move_deal], deals[win_deal]
    special = set(blank_web) | set(web_dupe_src) | set(exact_src) | {search_ai} | {d["account_index"] for d in (deals[i] for i in taken)}
    test_ai = sorted((ai for ai, a in enumerate(accounts) if a["owner"] == "Rahul Patel" and ai not in special),
                     key=lambda ai: accounts[ai]["name"])[0]
    test_contact = next(c for c in contacts if c["account_index"] == test_ai and c["email"])
    w_all = weighted()
    lr = per_rep[RESTRICTED_REP]

    counts = {
        "seed": None,
        "firm": {"people": 9, "reps": rep_names, "restricted_rep": RESTRICTED_REP, "other_rep": OTHER_REP,
                 "roles": {"admin": "Admin (managing partner)", "staff": "Rep", "viewer": "Analyst (read-only)"}},
        "tester_records": {"account": accounts[test_ai]["name"], "owner": accounts[test_ai]["owner"],
                           "contact": f"{test_contact['first']} {test_contact['last']}", "stage": "Lead", "amount": 10000.00,
                           "note": "deals the tester creates go on this account and are deleted when the item is done"},
        "accounts": {
            "file_rows_excluding_header": len(account_rows),
            "exact_duplicate_rows": N_ACCOUNT_EXACT_DUPES,
            "website_variant_duplicate_rows": N_ACCOUNT_WEBSITE_DUPES,
            "unique_accounts_after_dedupe": N_ACCOUNTS,
            "dedupe_rule": ("Two rows are the same account when Website matches after lowercasing and stripping http(s)://, "
                            "www., and a trailing slash. Rows with a blank Website are distinct accounts (their names differ)."),
            "wrong_counts": {"no_dedupe": len(account_rows), "exact_rows_only": len(account_rows) - N_ACCOUNT_EXACT_DUPES,
                             "blank_websites_collapsed_into_one": N_ACCOUNTS - N_ACCOUNT_BLANK_WEBSITE + 1},
            "blank_website_accounts": sorted(accounts[i]["name"] for i in blank_web),
            "website_variant_groups": web_groups,
            "exact_duplicate_accounts": sorted(accounts[i]["name"] for i in exact_src),
            "per_owner": {r: per_rep[r]["accounts"] for r in rep_names},
            "out_of_scope_account": {"name": oos_acct["name"], "owner": oos_acct["owner"]},
        },
        "contacts": {
            "file_rows_excluding_header": len(contact_rows),
            "exact_duplicate_rows": N_CONTACT_EXACT_DUPES,
            "email_case_duplicate_rows": N_CONTACT_EMAIL_CASE_DUPES,
            "unique_contacts_after_dedupe": N_CONTACTS,
            "dedupe_rule": ("Two rows are the same contact when Email matches after trimming and lowercasing. Blank-email rows are "
                            "distinct contacts. Two contacts share a name but have different emails and accounts: they are two people. "
                            "Account links to accounts.csv by name after trimming, case-insensitive."),
            "wrong_counts": {"no_dedupe": len(contact_rows), "exact_rows_only": len(contact_rows) - N_CONTACT_EXACT_DUPES,
                             "blank_emails_collapsed_into_one": N_CONTACTS - N_CONTACT_BLANK_EMAIL + 1,
                             "same_name_merged": N_CONTACTS - 1},
            "blank_email_contacts": sorted(f"{contacts[i]['first']} {contacts[i]['last']}" for i in blank_email_c),
            "email_case_groups": case_groups,
            "same_name_different_people": {"name": f"{contacts[twin_a]['first']} {contacts[twin_a]['last']}",
                                           "accounts": sorted([accounts[contacts[twin_a]['account_index']]['name'],
                                                               accounts[contacts[twin_b]['account_index']]['name']])},
            "rows_with_trailing_space_in_account": N_CONTACT_TRAILING_SPACE_ACCOUNT,
            "trailing_space_link_check": {
                "account": accounts[trailing_acct_ai]["name"],
                "contacts_on_account": sorted(f"{c['first']} {c['last']}" for c in contacts if c["account_index"] == trailing_acct_ai),
                "contact_count": sum(1 for c in contacts if c["account_index"] == trailing_acct_ai),
                "contact_written_with_trailing_space": f"{contacts[trailing_first]['first']} {contacts[trailing_first]['last']}",
            },
            "per_owner": {r: per_rep[r]["contacts"] for r in rep_names},
        },
        "deals": {
            "file_rows_excluding_header_and_preamble": N_DEALS,
            "preamble_lines_before_header": 2,
            "stage_order": STAGES,
            "stage_probabilities": PROB,
            "per_stage_count": {s: sum(1 for d in deals if d["stage"] == s) for s in STAGES},
            "stage_written_variants": "mixed case plus 'Closed Won' / 'Closed Lost'",
            "open_deals": len(open_deals()),
            "open_pipeline_value": round(sum(amt(d) for d in open_deals()), 2),
            "weighted_pipeline": w_all,
            "won_value": won_value(),
            "won_deals": STAGE_COUNTS["Won"], "lost_deals": STAGE_COUNTS["Lost"],
            "blank_amount_lead_deals": sorted(deals[i]["name"] for i in blank_amount),
            "currency_string_amount_rows": len(currency_idx),
            "negative_amount_deal": {"deal": deals[neg_deal]["name"], "owner": deals[neg_deal]["owner"], "stage": "Lost",
                                     "file_value": "-4,500.00",
                                     "note": "Lost, so it is outside every open-pipeline and won figure whether flagged, zeroed, or kept."},
            "highest_amount": {"deal": deals[max_deal]["name"], "owner": deals[max_deal]["owner"], "stage": deals[max_deal]["stage"],
                               "file_value": money(MAX_AMOUNT), "numeric": MAX_AMOUNT,
                               "text_sort_would_put_first": by_amount_text[0][1][0]},
            "latest_expected_close": {"deal": deals[late_deal]["name"], "owner": deals[late_deal]["owner"],
                                      "file_value": date_variant(LATEST_CLOSE, 6), "iso": LATEST_CLOSE.isoformat(),
                                      "text_sort_would_put_first": by_close_text[0][1][0],
                                      "text_sort_first_file_value": by_close_text[0][1][6]},
            "per_rep": per_rep,
            "search_check": {"term": accounts[search_ai]["name"], "expected_results": 2,
                             "deals": sorted(d["name"] for d in deals if d["account_index"] == search_ai)},
            "filter_check": {"field": "Stage", "value": "Proposal", "expected_results": STAGE_COUNTS["Proposal"]},
            "sort_check": {"field": "Amount", "direction": "descending", "first": deals[max_deal]["name"]},
            "export_check": {"rows": N_DEALS, "columns": ["Deal", "Account", "Owner", "Stage", "Amount", "Expected Close"]},
            "out_of_scope_deal": {"deal": oos_deal["name"], "owner": oos_deal["owner"], "stage": oos_deal["stage"]},
            "weighted_move_check": {"deal": mv["name"], "owner": mv["owner"], "amount": mv["amount"], "from_stage": "Proposal",
                                    "to_stage": "Negotiation", "probability_change": 0.25,
                                    "weighted_increase": round(mv["amount"] * 0.25, 2),
                                    "company_weighted_after_if_nothing_else_changed": round(w_all + mv["amount"] * 0.25, 2),
                                    "restricted_weighted_before": lr["weighted_pipeline"],
                                    "restricted_weighted_after": round(lr["weighted_pipeline"] + mv["amount"] * 0.25, 2)},
        },
        "changes": {
            "1_win_rate": {
                "definition": "win rate = Won deals / (Won + Lost deals) per rep, as a percent to one decimal",
                "per_rep": {r: {"won": per_rep[r]["won_deals"], "lost": per_rep[r]["lost_deals"],
                                "win_rate_percent": per_rep[r]["win_rate_percent"]} for r in rep_names},
                "company": {"won": STAGE_COUNTS["Won"], "lost": STAGE_COUNTS["Lost"],
                            "win_rate_percent": round(100.0 * STAGE_COUNTS["Won"] / (STAGE_COUNTS["Won"] + STAGE_COUNTS["Lost"]), 1)},
                "company_won_after_mark_won": STAGE_COUNTS["Won"] + 1,
                "company_win_rate_after_mark_won_percent": round(100.0 * (STAGE_COUNTS["Won"] + 1) / (STAGE_COUNTS["Won"] + 1 + STAGE_COUNTS["Lost"]), 1),
                "mark_won_check": {"deal": wd["name"], "owner": wd["owner"], "stage": wd["stage"], "amount": wd["amount"],
                                   "restricted_won_after": lr["won_deals"] + 1, "restricted_lost": lr["lost_deals"],
                                   "restricted_win_rate_after_percent": round(100.0 * (lr["won_deals"] + 1) / (lr["won_deals"] + 1 + lr["lost_deals"]), 1),
                                   "restricted_won_value_after": round(lr["won_value"] + wd["amount"], 2)},
            },
            "2_kickoff_task": {"close_date": "2026-09-17", "close_weekday": "Thursday", "due_date": "2026-09-22",
                               "friday_close_date": "2026-09-18", "friday_due_date": "2026-09-23",
                               "rule": "due three working days after the close date, skipping Saturday and Sunday"},
            "3_verbal_commit": {"stage_order": ["Lead", "Qualified", "Proposal", "Negotiation", "Verbal commit", "Won", "Lost"],
                                "verbal_commit_probability": 0.90, "rep_won_limit": 50000.00,
                                "move_deal": mv["name"], "move_amount": mv["amount"],
                                "weighted_increase_negotiation_to_verbal": round(mv["amount"] * 0.15, 2),
                                "won_value_increase_on_approval": mv["amount"], "boundary_test_amount": 50000.00,
                                "won_value_after_approval": round(won_value() + mv["amount"], 2),
                                "activity_check": {"deal": mv["name"], "type": "call", "date": "2026-09-14", "note": "Pricing follow-up"}},
        },
    }
    return {"account_rows": [r for _, _, r in account_rows], "contact_rows": [r for _, _, r in contact_rows],
            "deal_rows": [r for _, r in deal_rows], "counts": counts}


def main() -> None:
    seed = argparse_seed(0)
    rng = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    out = build(rng)
    write_csv(os.path.join(SEED_DIR, "accounts.csv"), ACCOUNT_COLUMNS, out["account_rows"])
    write_csv(os.path.join(SEED_DIR, "contacts.csv"), CONTACT_COLUMNS, out["contact_rows"], bom=True, crlf=True)
    write_csv(os.path.join(SEED_DIR, "deals.csv"), DEAL_COLUMNS, out["deal_rows"],
              preamble=["Pipeline export - all owners - generated 2026-09-10 08:14", ""])
    counts = out["counts"]
    counts["seed"] = seed
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(counts, indent=2) + "\n")
    a, c, d = counts["accounts"], counts["contacts"], counts["deals"]
    print(f"accounts.csv: {a['file_rows_excluding_header']} rows -> {a['unique_accounts_after_dedupe']} accounts {a['per_owner']}")
    print(f"contacts.csv: {c['file_rows_excluding_header']} rows -> {c['unique_contacts_after_dedupe']} contacts {c['per_owner']}")
    print(f"deals.csv: {d['file_rows_excluding_header_and_preamble']} deals; open {d['open_deals']}, weighted {d['weighted_pipeline']:.2f}, "
          f"open value {d['open_pipeline_value']:.2f}, won {d['won_value']:.2f}")


if __name__ == "__main__":
    main()
