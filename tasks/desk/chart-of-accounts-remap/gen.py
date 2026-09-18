#!/usr/bin/env python3
"""chart-of-accounts-remap: an electrical contractor's year-to-date GL lines restated on the CPA's new chart of accounts.

    python gen.py [--seed N] [--naive DIR]

Business: Tanager Electric is moving to new books at the start of September. Their CPA built a new, shorter chart
of accounts and a crosswalk from the old QuickBooks codes, and wants January to August restated line by line on the
new codes so the comparatives load.

Traps (each caught by a check, see task.yaml):
  * the Account column is QuickBooks' "parent:child" path ("6300 · Vehicle Expense:6310 · Fuel"); the child code is
    the one that maps, and some lines sit on the parent itself                    (check: new account code and name)
  * several old accounts collapse into one new account                           (check: new account code and name)
  * old 6180 Tools & Equipment splits by the CPA's rule: a line of $2,500.00 or more is capitalized to 1520, less
    goes to 6150; lines sit at exactly 2,500.00 and 2,499.99                     (check: new account code and name)
  * the crosswalk workbook still carries the v1 draft sheet with different mappings (check: new account code and name)
  * two old codes are on no crosswalk: the line stays, New Account blank, Mapping Note NEEDS MAPPING
                                                                                  (checks: new account code and name; unmapped lines flagged)
  * amounts carry thousands separators and credits in parentheses                (check: amount)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["Line ID", "Date", "Old Account", "New Account", "New Account Name", "Amount", "Memo", "Mapping Note"]
DOT = "·"
# old code: (old name, parent code or None, (lo, hi), weight, sign)
OLD = {
    "4010": ("Residential Service", "4000", (180, 2400), 10, 1),
    "4020": ("Commercial Service", "4000", (900, 9800), 7, 1),
    "4030": ("Materials Resale", None, (60, 1800), 4, 1),
    "5010": ("Wire & Conduit", "5000", (80, 2200), 8, 1),
    "5020": ("Fixtures & Devices", "5000", (40, 1600), 7, 1),
    "5030": ("Subcontract Labor", None, (400, 6200), 3, 1),
    "6110": ("Telephone", "6100", (60, 140), 2, 1),
    "6120": ("Internet", "6100", (89, 89), 2, 1),
    "6130": ("Cell Phones", "6100", (180, 420), 3, 1),
    "6170": ("Shop Supplies", None, (15, 380), 5, 1),
    "6180": ("Tools & Equipment", None, (40, 4800), 6, 1),
    "6300": ("Vehicle Expense", None, (20, 300), 2, 1),
    "6310": ("Fuel", "6300", (45, 260), 8, 1),
    "6320": ("Vehicle Repairs", "6300", (90, 1900), 3, 1),
    "6330": ("Vehicle Insurance", "6300", (410, 410), 2, 1),
    "6440": ("Permits", None, (35, 450), 5, 1),
    "6450": ("Licenses", None, (75, 600), 1, 1),
    "6510": ("General Liability", "6500", (640, 640), 2, 1),
    "6520": ("Workers Comp", "6500", (380, 1250), 3, 1),
    "6725": ("Charitable Contributions", None, (50, 500), 2, 1),
    "6999": ("Ask My Accountant", None, (12, 900), 2, 1),
}
PARENTS = {"4000": "Service Revenue", "5000": "Job Materials", "6100": "Utilities & Telephone", "6300": "Vehicle Expense",
           "6500": "Insurance"}
NEW = {"4100": "Service Revenue", "4200": "Materials Billed", "5100": "Job Materials", "5200": "Subcontractors",
       "6150": "Small Tools & Supplies", "1520": "Tools & Equipment", "6400": "Vehicle Expenses", "6600": "Telecommunications",
       "6700": "Insurance", "6800": "Licenses & Permits"}
CROSSWALK_V2 = {"4010": "4100", "4020": "4100", "4030": "4200", "5010": "5100", "5020": "5100", "5030": "5200",
                "6110": "6600", "6120": "6600", "6130": "6600", "6170": "6150", "6180": "SPLIT", "6300": "6400",
                "6310": "6400", "6320": "6400", "6330": "6400", "6440": "6800", "6450": "6800", "6510": "6700", "6520": "6700"}
CROSSWALK_V1 = dict(CROSSWALK_V2, **{"6130": "6610", "6180": "6150", "6520": "6710", "6450": "6810"})
V1_NAMES = dict(NEW, **{"6610": "Mobile Phones", "6710": "Workers Comp Insurance", "6810": "Licenses"})
THRESHOLD = 2500.00
CUSTOMERS = ["Harborview HOA", "Linden Dental Group", "R. Castillo", "M. Okafor", "Pinecrest Apartments", "Brightside Bakery",
             "Alder Creek School District", "J. Nguyen", "Riverside Storage"]
VENDORS = {"5010": ["Graybar", "CED Portland", "Platt Electric Supply"], "5020": ["Platt Electric Supply", "Home Depot Pro", "CED Portland"],
           "5030": ["Voltline Subcontracting", "Brightwire Trenching"], "6110": ["Lumen"], "6120": ["Comcast Business"],
           "6130": ["Verizon Wireless"], "6170": ["Grainger", "Fastenal"], "6180": ["Milwaukee Tool", "Fluke Direct", "Grainger", "Home Depot Pro"],
           "6300": ["Clean Machine Car Wash", "SP+ Parking"], "6310": ["Chevron", "Shell", "Pacific Pride"], "6320": ["Les Schwab", "Firestone Complete Auto"],
           "6330": ["Progressive Commercial"], "6440": ["City of Portland BDS", "Multnomah County"], "6450": ["State of Oregon CCB", "Oregon BCD"],
           "6510": ["Hartford"], "6520": ["SAIF Corporation"], "6725": ["Oregon Food Bank", "Habitat for Humanity"],
           "6999": ["Amazon", "Costco", "Venmo transfer"]}


def vendor_pool(code: str) -> list:
    return CUSTOMERS if code.startswith("4") else VENDORS[code]


def new_for(code: str, amt: float) -> str:
    m = CROSSWALK_V2.get(code, "")
    if m == "SPLIT":
        return "1520" if amt >= THRESHOLD else "6150"
    return m


def build(seed: int) -> dict:
    r = rng(seed)
    codes = list(OLD)
    weights = [OLD[c][3] for c in codes]
    lines = []
    for _ in range(150):
        c = r.choices(codes, weights)[0]
        name, parent, (lo, hi), _, sign = OLD[c]
        amt = lo if lo == hi else money(r, lo, hi)
        if c == "6180" and r.random() < 0.6:
            amt = money(r, 40, 1800)      # most tool buys are small
        lines.append({"code": c, "amt": round(sign * amt, 2), "date": day_in(r, date(2026, 1, 2), date(2026, 8, 31))})
    # boundary tool purchases and a vendor credit on a mapped expense
    lines.append({"code": "6180", "amt": 2500.00, "date": date(2026, 5, 14)})
    lines.append({"code": "6180", "amt": 2499.99, "date": date(2026, 6, 3)})
    lines.append({"code": "6180", "amt": money(r, 3100, 5200), "date": date(2026, 3, 19)})
    lines.append({"code": "5020", "amt": -money(r, 60, 400), "date": date(2026, 4, 22)})
    lines.append({"code": "6310", "amt": -money(r, 10, 40), "date": date(2026, 7, 9)})
    lines.append({"code": "4010", "amt": -money(r, 90, 300), "date": date(2026, 2, 26)})
    lines.sort(key=lambda x: (x["date"], x["code"]))
    ids = r.sample(range(1000, 9999), len(lines))
    for x, i in zip(lines, ids):
        x["id"] = f"JL-{i:05d}"
        x["vendor"] = r.choice(vendor_pool(x["code"]))
        x["new"] = new_for(x["code"], abs(x["amt"]) if x["code"] != "6180" else x["amt"])
        x["new_name"] = NEW.get(x["new"], "")
        x["note"] = "" if x["new"] else "NEEDS MAPPING"
        x["type"] = "Invoice" if x["code"].startswith("4") else r.choice(["Bill", "Check", "Credit Card Charge"])
        if x["amt"] < 0:
            x["type"] = "Credit Memo" if x["code"].startswith("4") else "Bill Credit"
    return {"lines": lines}


def acceptable(d: dict) -> bool:
    ls = d["lines"]
    big = [x for x in ls if x["code"] == "6180" and x["amt"] >= THRESHOLD]
    small = [x for x in ls if x["code"] == "6180" and x["amt"] < THRESHOLD]
    unm = [x for x in ls if not x["new"]]
    return len(big) >= 3 and len(small) >= 5 and len({x["code"] for x in unm}) == 2 and len(unm) >= 3 \
        and sum(1 for x in ls if x["code"] == "6300") >= 1 and sum(1 for x in ls if x["code"] in ("6130", "6520")) >= 3


def acct_path(code: str) -> str:
    name, parent = OLD[code][0], OLD[code][1]
    leaf = f"{code} {DOT} {name}"
    return f"{parent} {DOT} {PARENTS[parent]}:{leaf}" if parent else leaf


def amt_text(v: float) -> str:
    return f"({abs(v):,.2f})" if v < 0 else f"{v:,.2f}"


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 3)
    memo_words = {"4": "Job", "5": "Materials job", "6": ""}
    src = []
    for x in d["lines"]:
        memo = f"{memo_words[x['code'][0]]} {r.randint(2201, 2399)}".strip() if x["code"][0] in "45" else r.choice(["", "", "reimb", "monthly", "see receipt"])
        if x["code"] == "6180":
            memo = r.choice(["Impact driver kit", "Cable puller", "Fluke meter", "Bender set", "Crimper", "Hydraulic knockout set",
                             "Trailer-mounted wire puller", "Scissor lift deposit"]) if x["amt"] >= 1000 else r.choice(["Bits", "Tape & blades", "Fish tape", "Strippers"])
        src.append([x["id"], x["type"], x["date"].strftime("%m/%d/%Y"), x["vendor"], memo, acct_path(x["code"]), amt_text(x["amt"])])
        x["memo"] = memo
    write_csv(os.path.join(ws, "gl_detail_2026-01_to_2026-08.csv"),
              ["Line ID", "Type", "Date", "Name", "Memo", "Account", "Amount"], src,
              preamble=["Tanager Electric LLC", "Transaction Detail by Account", "January 1 through August 31, 2026", ""])
    v2_rows, v1_rows = [], []
    for c, (name, *_rest) in OLD.items():
        m2, m1 = CROSSWALK_V2.get(c), CROSSWALK_V1.get(c)
        if m2:
            v2_rows.append([int(c) if r.random() < 0.6 else f"{c} ", name, "see note" if m2 == "SPLIT" else int(m2),
                            "" if m2 == "SPLIT" else NEW[m2], "Split by amount - see Marcus's email" if m2 == "SPLIT" else ""])
        if m1:
            v1_rows.append([int(c), name, int(m1), V1_NAMES[m1], ""])
    r.shuffle(v2_rows)
    write_xlsx(os.path.join(ws, "coa_crosswalk.xlsx"), {
        "v1 draft": {"merged_title": "DRAFT - do not use", "header": ["Old Code", "Old Account", "New Code", "New Account", "Notes"],
                     "rows": v1_rows, "widths": {"B": 26, "D": 28}},
        "v2 final": {"merged_title": "Crosswalk v2 - final (Aug 2026)", "header": ["Old Code", "Old Account", "New Code", "New Account", "Notes"],
                     "rows": v2_rows, "widths": {"B": 26, "D": 28, "E": 36}},
        "New chart": {"header": ["Code", "Account", "Type"],
                      "rows": [[int(k), v, "Fixed Asset" if k.startswith("1") else "Income" if k.startswith("4") else
                                "Cost of Goods Sold" if k.startswith("5") else "Expense"] for k, v in sorted(NEW.items())]}},
        creator="Mossgiel CPA")
    write_csv(os.path.join(ws, "remap_template.csv"), HEADER,
              [["JL-00000", "01/01/2026", "6310", "6400", "Vehicle Expenses", "52.10", "example", ""]])
    write_email_thread(os.path.join(ws, "email_from_marcus_cpa.txt"), [
        {"from": "Marcus Bell <marcus@mossgielcpa.com>", "to": "Dee Tanager <dee@tanagerelectric.com>", "date": "Thu, 3 Sep 2026 16:20",
         "subject": "Crosswalk for the new books",
         "body": ("Dee,\n\nThe crosswalk is attached - use the v2 final tab. v1 was my first pass before we talked, a few of those "
                  "accounts changed.\n\nWhat I need back is every line from the January-August detail report restated on the new "
                  "codes, one row per line, on the template I sent (remapped.csv is fine as a name).\n\n"
                  "- Map on the account the line was actually posted to. QuickBooks shows sub-accounts as Parent:Child, so the "
                  "child is the one that counts; a few lines were posted straight to a parent account, which has its own row on "
                  "the crosswalk.\n"
                  "- Old 6180 Tools & Equipment splits. Any single line of $2,500.00 or more is capitalized: 1520 Tools & Equipment. "
                  "Anything under $2,500.00 goes to 6150 Small Tools & Supplies.\n"
                  "- If an old account isn't on the crosswalk at all, don't guess and don't drop the line. Leave New Account and New "
                  "Account Name empty and put NEEDS MAPPING in Mapping Note. Otherwise leave Mapping Note empty.\n"
                  "- Amount: same sign as the report, as a plain number.\n\nThanks,\nMarcus")}])

    rows = [[x["id"], x["date"].strftime("%m/%d/%Y"), x["code"], x["new"], x["new_name"], f"{x['amt']:.2f}", x["memo"], x["note"]]
            for x in d["lines"]]
    write_csv(os.path.join(ref, "remapped.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "remapped.csv"), HEADER, rows)
    ls = d["lines"]
    acct_pins = sorted({x["id"] for x in ls if x["code"] in ("6180", "6130", "6520", "6450", "6300", "6725", "6999")} |
                       {x["id"] for x in ls if x["code"] in ("6310", "6320", "6110", "6510")})
    unmapped = sorted(x["id"] for x in ls if not x["new"])
    neg = sorted(x["id"] for x in ls if x["amt"] < 0) + [x["id"] for x in ls if x["amt"] >= 1000][:4]
    write_json(os.path.join(ref, "notes.json"), {"lines": len(rows), "unmapped": unmapped,
                                                  "split_big": sorted(x["id"] for x in ls if x["code"] == "6180" and x["amt"] >= THRESHOLD)})
    write_task_yaml(HERE, {
        "id": "chart-of-accounts-remap", "track": "desk", "category": "reformatting",
        "title": "Restate this year's GL lines on the new chart of accounts",
        "ask": ("Marcus needs our January to August transactions moved onto the new chart of accounts for the new books. "
                "His email and the crosswalk are in the folder; please send it back as remapped.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the Account column is QuickBooks' Parent:Child path ('6300 · Vehicle Expense:6310 · Fuel'); taking the first "
            "code maps every sub-account line by its parent, which for 6100 and 6500 is not on the crosswalk at all "
            "(check: new account code and name)",
            "many-to-one: Telephone, Internet and Cell Phones all become 6600 Telecommunications; Fuel, Vehicle Repairs, "
            "Vehicle Insurance and the 6300 parent all become 6400 (check: new account code and name)",
            "old 6180 Tools & Equipment has no single target; the email capitalizes lines of $2,500.00 or more to 1520 and "
            "sends the rest to 6150, with lines at exactly 2,500.00 (1520) and 2,499.99 (6150) "
            "(check: new account code and name)",
            "coa_crosswalk.xlsx opens on the 'v1 draft' tab, which maps Cell Phones to 6610, Workers Comp to 6710, "
            "Licenses to 6810 and all of 6180 to 6150; the email says to use v2 final (check: new account code and name)",
            "6725 Charitable Contributions and 6999 Ask My Accountant are on no crosswalk; the lines stay with New Account "
            "blank and NEEDS MAPPING in Mapping Note, not dropped and not guessed "
            "(checks: new account code and name; unmapped lines flagged; one row per GL line)",
            "amounts are text with thousands separators ('4,240.74') and credits in parentheses ('(212.40)') on a customer "
            "credit memo and two vendor credits; they stay negative as plain numbers (check: amount)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns, exact order", "path": "remapped.csv", "columns": HEADER, "exact": True},
            {"type": "csv_set_equal", "name": "one row per GL line", "path": "remapped.csv", "column": "Line ID", "ref": "remapped.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "remapped.csv", "equals_ref": "remapped.csv"},
            {"type": "csv_values_match", "name": "new account code and name", "path": "remapped.csv", "ref": "remapped.csv",
             "key": "Line ID", "columns": ["New Account", "New Account Name"], "min_accuracy": 1.0, "must_match_keys": acct_pins},
            {"type": "csv_values_match", "name": "unmapped lines flagged", "path": "remapped.csv", "ref": "remapped.csv",
             "key": "Line ID", "columns": ["Mapping Note"], "min_accuracy": 0.9, "must_match_keys": unmapped},
            {"type": "csv_values_match", "name": "amount", "path": "remapped.csv", "ref": "remapped.csv", "key": "Line ID",
             "columns": ["Amount"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": sorted(set(neg))},
        ],
    })
    print(f"seed={seed} lines={len(rows)} unmapped={len(unmapped)} acct_pins={len(acct_pins)}")


def write_naive(d: dict, out: str) -> None:
    """The obvious lookup: the first four digits of the Account column against the first crosswalk tab (v1), no split,
    unmapped lines left blank with no note, amounts with the parentheses read as positive."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for x in d["lines"]:
        code = OLD[x["code"]][1] or x["code"]
        new = CROSSWALK_V1.get(code, "")
        rows.append([x["id"], x["date"].strftime("%m/%d/%Y"), code, new, V1_NAMES.get(new, ""), f"{abs(x['amt']):.2f}", "", ""])
    write_csv(os.path.join(out, "remapped.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(300):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
