#!/usr/bin/env python3
"""lead-source-rollup: Q2 leads and won revenue per marketing source for a flight school.

    python gen.py [--seed N] [--naive DIR]

Business: Blue Mesa Flight Training in Santa Fe. The website form stores a campaign code in a hidden field,
the site builder bolts tracking tags onto it, and the marketing lead wants leads and closed-won training
revenue per source for April to June from the CRM export and the campaign code sheet.

Traps (each caught by a check, see task.yaml):
  * codes arrive with tracking noise: '?utm_source=...', '&gclid=...', '|utm_medium=video', '%20', stray
    spaces and lower case; an exact lookup sends most leads to Untracked      (checks: leads per source; sources)
  * codes that are not on the sheet (a mistyped Q3 code, an old Facebook code) carry utm_source tags that point
    at a real source; the email says they go to Untracked, not to the source the tag suggests
                                                                               (check: leads per source)
  * revenue counts closed-won deals only; proposals and lost deals carry quoted values too
                                                                               (check: won revenue per source)
  * the export runs from late March into July and holds staff test leads    (check: leads per source)
  * Radio has no Q2 leads and still gets a row                               (checks: sources; row count)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CAMPAIGNS = [  # code, campaign, source, owner, start, end
    ("GADS-PPL-Q2", "Private pilot search - Q2", "Google Ads", "Sofia", "2026-04-01", "2026-06-30"),
    ("GADS-DISC-Q2", "Discovery flight search - Q2", "Google Ads", "Sofia", "2026-04-01", "2026-06-30"),
    ("GADS-IFR-Q1", "Instrument rating search - Q1 (left running)", "Google Ads", "Sofia", "2026-01-05", ""),
    ("IG-DISC-SPRING", "Discovery flight reels", "Instagram", "Marcus", "2026-03-15", "2026-05-31"),
    ("IG-REEL-CHECKRIDE", "Checkride day stories", "Instagram", "Marcus", "2026-04-10", ""),
    ("YT-FIRSTSOLO", "First solo compilation", "YouTube", "Marcus", "2026-02-01", ""),
    ("YT-PREROLL-PPL", "Pre-roll: learn to fly", "YouTube", "Sofia", "2026-04-15", "2026-06-15"),
    ("EVT-SF-OUTDOOR-EXPO", "Santa Fe Outdoor Expo booth", "Airshows & Events", "Dmitri", "2026-04-18", "2026-04-19"),
    ("EVT-KAEG-FLYIN", "Double Eagle fly-in", "Airshows & Events", "Dmitri", "2026-05-23", "2026-05-23"),
    ("REF-EAA-1257", "EAA chapter referral card", "Flight Club Referrals", "Dmitri", "2025-09-01", ""),
    ("REF-CAP-SQDN", "Civil Air Patrol squadron referral", "Flight Club Referrals", "Dmitri", "2026-03-01", ""),
    ("NEWS-APR", "April newsletter", "Email Newsletter", "Sofia", "2026-04-02", "2026-04-30"),
    ("NEWS-JUN", "June newsletter", "Email Newsletter", "Sofia", "2026-06-04", "2026-06-30"),
    ("KSFR-SPOT", "KSFR morning spot", "Radio", "Dmitri", "2026-01-12", "2026-03-27"),
]
SOURCES = ["Google Ads", "Instagram", "YouTube", "Airshows & Events", "Flight Club Referrals", "Email Newsletter", "Radio"]
UNTRACKED = "Untracked"
EMPTY_SOURCE = "Radio"
WEIGHT = {"GADS-PPL-Q2": 9, "GADS-DISC-Q2": 8, "GADS-IFR-Q1": 3, "IG-DISC-SPRING": 7, "IG-REEL-CHECKRIDE": 4, "YT-FIRSTSOLO": 4,
          "YT-PREROLL-PPL": 3, "EVT-SF-OUTDOOR-EXPO": 3, "EVT-KAEG-FLYIN": 2, "REF-EAA-1257": 3, "REF-CAP-SQDN": 2,
          "NEWS-APR": 2, "NEWS-JUN": 2, "KSFR-SPOT": 0}
UTM = {"Google Ads": "google", "Instagram": "instagram", "YouTube": "youtube", "Airshows & Events": "event",
       "Flight Club Referrals": "referral", "Email Newsletter": "newsletter"}
# unknown codes with a utm tail that suggests a real source
UNKNOWN_CODES = [("GADS-PPL-Q3", "google"), ("FB-DISC-FLY", "facebook"), ("IG-SUMMER-SOLO", "instagram"), ("PROMO-FATHERSDAY", "newsletter")]
INTEREST = [("Discovery Flight", 0.40, (189, 189)), ("Private Pilot Package", 0.33, (13900, 16400)),
            ("Instrument Rating", 0.15, (9800, 11200)), ("Commercial Pilot", 0.06, (22500, 27800)), ("Block Time 10 hrs", 0.06, (2450, 2450))]
STAGES_OPEN = ["New", "Contacted", "Discovery Flight Scheduled", "Proposal Sent"]


def noisy(r, code: str, source: str | None, style: int) -> str:
    utm = UTM.get(source, "site")
    return [
        code,
        code.lower(),
        f"{code}?utm_source={utm}&utm_medium=cpc&utm_campaign={code.lower()}",
        f"{code}&gclid=Cj0KCQjw{code_str(r, 14)}",
        f" {code} ",
        f"{code}%20",
        f"{code}|utm_medium=video",
        f"{code.lower()}?utm_source={utm}",
    ][style % 8]


def code_str(r, n):
    return code(r, n, "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ0123456789")


def build(seed: int) -> dict:
    r = rng(seed)
    codes = [c[0] for c in CAMPAIGNS]
    src_of = {c[0]: c[2] for c in CAMPAIGNS}
    leads = []
    lid = 5100 + r.randint(0, 400)
    start, end = date(2026, 3, 20), date(2026, 7, 1)
    pool = [c for c in codes for _ in range(WEIGHT[c])]
    n = r.randint(205, 240)
    names = people(r, n + 10)
    for i in range(n):
        f, l = names[i]
        created = day_in(r, start, end)
        k = r.random()
        if k < 0.10:
            raw_code, code_val = "", None
        elif k < 0.15:
            uc, utm = r.choice(UNKNOWN_CODES)
            raw_code, code_val = r.choice([f"{uc}?utm_source={utm}&utm_medium=social", f"{uc}|utm_source={utm}", uc]), uc
        elif k < 0.18:
            src = r.choice(list(UTM))
            raw_code, code_val = f"utm_source={UTM[src]}&utm_medium=organic", None
        else:
            code_val = r.choice(pool)
            raw_code = noisy(r, code_val, src_of[code_val], r.randrange(8) if r.random() < 0.62 else 0)
        acc, interest = r.random(), INTEREST[0]
        for it in INTEREST:
            if acc < it[1]:
                interest = it
                break
            acc -= it[1]
        value = float(r.randint(*interest[2])) if interest[2][0] != interest[2][1] else float(interest[2][0])
        value = round(value / 50) * 50.0 if value > 1000 else value
        s = r.random()
        stage = "Closed Won" if s < 0.24 else "Closed Lost" if s < 0.44 else r.choice(STAGES_OPEN)
        show_value = stage in ("Closed Won", "Closed Lost", "Proposal Sent") or r.random() < 0.3
        closed = min(created + timedelta(days=r.randint(2, 40)), date(2026, 7, 1)) if stage.startswith("Closed") else None
        leads.append({"id": f"L-{lid + i}", "created": datetime(created.year, created.month, created.day, r.randint(6, 21), r.randint(0, 59)),
                      "first": f, "last": l, "email": email_for(r, f, l), "phone": phone_digits(r), "interest": interest[0],
                      "raw_code": raw_code, "code": code_val, "stage": stage, "value": value if show_value else None,
                      "closed": closed, "test": False})
    # staff test leads
    for j, (f, l) in enumerate([("Test", "Lead"), (names[n][0], names[n][1]), ("Sofia", "Test")]):
        created = date(2026, 4 + j, r.randint(3, 25))
        c = r.choice(codes[:4])
        leads.append({"id": "", "created": datetime(created.year, created.month, created.day, 9, 12 + j), "first": f, "last": l,
                      "email": f"{f.lower()}.{l.lower()}@bluemesaflight.com" if j != 1 else f"test{j}@bluemesaflight.com",
                      "phone": phone_digits(r), "interest": "Discovery Flight", "raw_code": noisy(r, c, src_of[c], 2), "code": c,
                      "stage": "Closed Won" if j == 0 else "New", "value": 189.0, "closed": created, "test": True})
    leads.sort(key=lambda x: x["created"])
    for i, x in enumerate(leads):
        x["id"] = f"L-{lid + i}"

    # ---- truth ----
    q2 = [x for x in leads if date(2026, 4, 1) <= x["created"].date() <= date(2026, 6, 30) and not x["test"]]
    count = {s: 0 for s in SOURCES + [UNTRACKED]}
    rev = {s: 0.0 for s in SOURCES + [UNTRACKED]}
    for x in q2:
        s = src_of.get(x["code"], UNTRACKED) if x["code"] in src_of else UNTRACKED
        x["source"] = s
        count[s] += 1
        if x["stage"] == "Closed Won" and x["value"]:
            rev[s] += x["value"]
    rev = {k: round(v, 2) for k, v in rev.items()}
    return {"leads": leads, "q2": q2, "count": count, "rev": rev}


def naive(d: dict) -> tuple[dict, dict]:
    """Exact lookup on the raw code text, every quoted value as revenue, no date or test filter."""
    src_of = {c[0]: c[2] for c in CAMPAIGNS}
    count = {s: 0 for s in SOURCES + [UNTRACKED]}
    rev = {s: 0.0 for s in SOURCES + [UNTRACKED]}
    for x in d["leads"]:
        s = src_of.get(x["raw_code"], UNTRACKED)
        count[s] += 1
        rev[s] += x["value"] or 0
    return count, {k: round(v, 2) for k, v in rev.items()}


def utm_guess(d: dict) -> dict:
    """Leads per source if unknown codes are assigned by their utm_source tag."""
    guess = {"google": "Google Ads", "instagram": "Instagram", "newsletter": "Email Newsletter", "youtube": "YouTube"}
    count = dict(d["count"])
    for x in d["q2"]:
        if x["source"] == UNTRACKED and "utm_source=" in x["raw_code"]:
            tag = x["raw_code"].split("utm_source=")[1].split("&")[0]
            if tag in guess:
                count[UNTRACKED] -= 1
                count[guess[tag]] += 1
    return count


def acceptable(d: dict) -> bool:
    c, rv = d["count"], d["rev"]
    if c[EMPTY_SOURCE] != 0:
        return False
    if any(c[s] < 3 for s in SOURCES if s != EMPTY_SOURCE):
        return False
    if any(rv[s] <= 0 for s in ("Google Ads", "Instagram", "YouTube", "Flight Club Referrals")):
        return False
    # every real source has at least one lead whose code only matches after cleaning
    for s in SOURCES:
        if s == EMPTY_SOURCE:
            continue
        if not any(x["source"] == s and x["raw_code"] != x["code"] for x in d["q2"]):
            return False
    # unknown codes with utm tags pointing at Google and Instagram are in Q2
    g = utm_guess(d)
    if g["Google Ads"] == c["Google Ads"] or g["Instagram"] == c["Instagram"]:
        return False
    # quoted values on lost / open deals move revenue for the big sources
    for s in ("Google Ads", "Instagram"):
        lost = sum(x["value"] or 0 for x in d["q2"] if x["source"] == s and x["stage"] != "Closed Won")
        if lost < 1000:
            return False
    # the export edges and test leads matter
    if not any(x["created"].date() < date(2026, 4, 1) for x in d["leads"]) or not any(x["created"].date() > date(2026, 6, 30) for x in d["leads"]):
        return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["source", "leads", "revenue"]
    order = SOURCES + [UNTRACKED]
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        cnt, rv = naive(d)
        write_csv(os.path.join(naive_dir, "lead_sources.csv"), header, [[s, cnt[s], f"{rv[s]:.2f}"] for s in order])
        return
    ws, ref, sol = task_dirs(HERE)

    # ---- workspace ----
    rows = []
    for x in d["leads"]:
        rows.append([x["id"], x["created"].strftime("%m/%d/%Y %I:%M %p"), x["first"], x["last"], x["email"],
                     phone_variant(x["phone"], sum(map(ord, x["id"])) % 4), x["interest"], x["raw_code"], x["stage"],
                     money_str(x["value"], 1) if x["value"] else "", x["closed"].strftime("%m/%d/%Y") if x["closed"] else ""])
    write_csv(os.path.join(ws, "crm_leads_export_2026-07-02.csv"),
              ["Lead ID", "Created", "First Name", "Last Name", "Email", "Phone", "Interested In", "Campaign Code",
               "Stage", "Deal Value", "Close Date"], rows, bom=True)
    write_xlsx(os.path.join(ws, "campaign_codes_2026.xlsx"), {"Codes": {
        "header": ["Code", "Campaign", "Source", "Owner", "Start", "End"],
        "rows": [list(c[:4]) + [date.fromisoformat(c[4]), date.fromisoformat(c[5]) if c[5] else "running"] for c in CAMPAIGNS],
        "widths": {"A": 22, "B": 40, "C": 22, "E": 12, "F": 12}, "freeze": "A2"}}, creator="Sofia Reyes")
    write_email_thread(os.path.join(ws, "email_from_sofia.txt"), [
        {"from": "Dmitri Alvarez <dmitri@bluemesaflight.com>", "to": "Sofia Reyes <sofia@bluemesaflight.com>",
         "date": "Wed, 1 Jul 2026 17:02", "subject": "Q2 marketing - where did students come from?",
         "body": "Before we set the Q3 budget I want to see, for each marketing source, how many leads came in during "
                 "April, May and June and how much training revenue they turned into. Can you get that together?"},
        {"from": "Sofia Reyes <sofia@bluemesaflight.com>", "to": "you", "date": "Thu, 2 Jul 2026 08:41",
         "subject": "FW: Q2 marketing - where did students come from?",
         "body": "Could you do this one for Dmitri? The CRM export and my campaign code sheet are in the folder.\n\n"
                 "How to count it:\n"
                 "- A lead belongs to the quarter it came in (the Created date), April 1 to June 30. The export runs a "
                 "bit either side.\n"
                 "- Ignore anything we submitted ourselves to test the form - those are all bluemesaflight.com addresses.\n"
                 "- The website builder tacks tracking onto the campaign code, so you'll see things like "
                 "GADS-PPL-Q2?utm_source=google&utm_medium=cpc or ig-disc-spring%20. The code is just the part in front "
                 "of the junk, and capitals don't matter.\n"
                 "- The source is whatever my sheet says for that code. If the code isn't on my sheet, or there's no "
                 "code at all, put the lead under Untracked. Please don't go by the utm tags - the builder fills those "
                 "in on its own and they're wrong half the time.\n"
                 "- Revenue is the deal value on Closed Won leads only. Proposals and lost deals have quoted prices on "
                 "them; those aren't money.\n\n"
                 "Save it as lead_sources.csv with source, leads, revenue - one line for every source on my sheet "
                 "(even if it got nothing) plus Untracked.\n\nThanks!\nSofia"}])

    # ---- reference ----
    ref_rows = [[s, d["count"][s], f"{d['rev'][s]:.2f}"] for s in order]
    write_csv(os.path.join(ref, "lead_sources.csv"), header, ref_rows)
    write_csv(os.path.join(sol, "lead_sources.csv"), header, ref_rows)
    write_json(os.path.join(ref, "notes.json"), {"q2_leads": len(d["q2"]), "utm_guess_counts": utm_guess(d),
                                                  "naive": dict(zip(("count", "rev"), naive(d)))})

    write_task_yaml(HERE, {
        "id": "lead-source-rollup", "track": "desk", "category": "spreadsheet",
        "title": "Q2 leads and won revenue by marketing source",
        "ask": ("Dmitri wants to know where our Q2 leads came from and what they turned into, by marketing source. "
                "Use the CRM export and Sofia's code sheet and save lead_sources.csv - her email explains how to count.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the Campaign Code field carries tracking noise ('?utm_source=google&utm_medium=cpc', '&gclid=...', "
            "'|utm_medium=video', '%20', padding and lower case); an exact lookup against the sheet sends most leads "
            "to Untracked (checks: leads per source; won revenue per source)",
            f"codes that are not on the sheet ({', '.join(c for c, _ in UNKNOWN_CODES)}) carry utm_source tags naming "
            "Google, Instagram or the newsletter; the email puts them under Untracked, so assigning them by the tag "
            "inflates Google Ads and Instagram (check: leads per source)",
            "revenue is closed-won only; Proposal Sent and Closed Lost leads carry quoted deal values in the same column "
            "(check: won revenue per source)",
            "the export runs from 20 March to 1 July and includes three staff test submissions on bluemesaflight.com "
            "addresses, one of them Closed Won (checks: leads per source; won revenue per source)",
            f"{EMPTY_SOURCE} ran until March and has no Q2 leads, but the email wants a line for every source on the "
            "sheet plus Untracked (checks: every source plus Untracked; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "lead_sources.csv", "columns": header},
            {"type": "csv_set_equal", "name": "every source plus Untracked", "path": "lead_sources.csv", "column": "source",
             "ref": "lead_sources.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "lead_sources.csv", "equals_ref": "lead_sources.csv"},
            {"type": "csv_values_match", "name": "leads per source", "path": "lead_sources.csv", "ref": "lead_sources.csv",
             "key": "source", "columns": ["leads"], "numeric": True, "tolerance": 0, "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "won revenue per source", "path": "lead_sources.csv", "ref": "lead_sources.csv",
             "key": "source", "columns": ["revenue"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0},
        ],
    })
    print(f"seed={seed} leads={len(d['leads'])} q2={len(d['q2'])}")
    print("count:", d["count"]); print("rev:", d["rev"]); print("utm guess:", utm_guess(d))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(500):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 500 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
