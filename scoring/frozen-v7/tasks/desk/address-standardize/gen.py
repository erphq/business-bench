#!/usr/bin/env python3
"""address-standardize: a seed company's catalog mailing list cleaned to the mail house's USPS-style standard.

    python gen.py [--seed N] [--naive DIR]

Business: Stillwater Heirloom Seeds mails a printed winter catalog. The list is a mix of web-store accounts and
trade-show sign-ups typed by hand. Keystone Mailing Services wants USPS Publication 28 style addresses and
will charge for every duplicate piece.

Traps (each caught by a check, see task.yaml):
  * suffixes, directionals and unit designators are spelled out, abbreviated with periods, or in odd
    spellings (Str, Av, Pky, Terr); the standard wants the USPS abbreviation     (check: delivery address line)
  * a direction word that is the street name itself stays spelled out (45 NORTH ST)  (check: delivery address line)
  * the unit is sometimes on Address Line 2 and belongs at the end of the delivery line; a bare # is "# 12"
                                                                                  (check: delivery address line)
  * ZIPs typed as numbers lost their leading zero, and some ZIP+4 came through as 8 or 9 bare digits;
    ZIP+4 must be kept as 12345-6789                                              (check: city, state and ZIP)
  * states written out in full                                                     (check: city, state and ZIP)
  * the same household appears twice under different spellings; only the standardized form reveals it, and
    the earlier Date Added wins, while two different apartments at one building both stay
                                                                                  (checks: one row per mailing address; row count)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["Customer ID", "Full Name", "Delivery Address", "City", "State", "ZIP Code"]
STREET_NAMES = ["Maple", "Oak", "Cedar", "Elm", "Pine", "Birch", "Willow", "Spruce", "Hickory", "Chestnut", "Walnut",
                "Poplar", "Sycamore", "Magnolia", "Laurel", "Juniper", "Hawthorn", "Alder", "Dogwood", "Main", "Church",
                "Mill", "Park", "Lake", "Ridge", "River", "Union", "Market", "Water", "Bridge", "School", "Prospect",
                "Highland", "Orchard", "Meadow", "Fairview", "Glen", "Summit"]
SUFFIX = {"ST": ["Street", "St", "St.", "Str"], "AVE": ["Avenue", "Ave", "Ave.", "Av"], "RD": ["Road", "Rd", "Rd."],
          "DR": ["Drive", "Dr", "Dr."], "LN": ["Lane", "Ln", "Ln."], "CT": ["Court", "Ct", "Ct."],
          "BLVD": ["Boulevard", "Blvd", "Blvd."], "PL": ["Place", "Pl", "Pl."], "CIR": ["Circle", "Cir", "Cir."],
          "PKWY": ["Parkway", "Pkwy", "Pky"], "TER": ["Terrace", "Ter", "Terr"], "TRL": ["Trail", "Trl"], "WAY": ["Way"]}
DIRS = {"N": ["North", "N", "N."], "S": ["South", "S", "S."], "E": ["East", "E", "E."], "W": ["West", "W", "W."],
        "NE": ["Northeast", "NE", "N.E."], "NW": ["Northwest", "NW", "N.W."], "SE": ["Southeast", "SE", "S.E."],
        "SW": ["Southwest", "SW", "S.W."]}
DIR_WORD = {"N": "NORTH", "S": "SOUTH", "E": "EAST", "W": "WEST"}
UNITS = {"APT": ["Apartment", "Apt", "Apt.", "apt"], "STE": ["Suite", "Ste", "Ste."], "UNIT": ["Unit"],
         "BLDG": ["Building", "Bldg"], "FL": ["Floor", "Fl"], "RM": ["Room", "Rm"], "#": ["#"]}
STATE_NAMES = {"OR": "Oregon", "TX": "Texas", "CO": "Colorado", "WI": "Wisconsin", "NC": "North Carolina", "ID": "Idaho",
               "VT": "Vermont", "NM": "New Mexico", "MI": "Michigan", "GA": "Georgia", "WA": "Washington", "AZ": "Arizona",
               "VA": "Virginia", "CA": "California", "OH": "Ohio", "NE": "Nebraska", "RI": "Rhode Island"}
ZERO_CITIES = [("Burlington", "VT", "05401"), ("Providence", "RI", "02903")]


def std_line(a: dict) -> str:
    if a.get("pobox"):
        return f"PO BOX {a['pobox']}"
    parts = [str(a["num"])]
    if a.get("pre"):
        parts.append(a["pre"])
    parts.append(a["name"].upper())
    parts.append(a["suffix"])
    if a.get("post"):
        parts.append(a["post"])
    if a.get("unit"):
        d, n = a["unit"]
        parts.append(f"{d} {n}")
    return " ".join(parts)


def zip_out(a: dict) -> str:
    return a["zip5"] + (f"-{a['zip4']}" if a.get("zip4") else "")


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = people(r, 80)
    recs = []
    used_lines = set()

    def new_addr(kind: str = "plain", unit_kind: str | None = None) -> dict:
        while True:
            city, st, z5 = r.choice(ZERO_CITIES) if kind == "zero" else r.choice(CITIES)
            a = {"num": r.randint(12, 9899), "name": r.choice(STREET_NAMES), "suffix": r.choice(list(SUFFIX)),
                 "city": city, "state": st, "zip5": z5, "zip4": f"{r.randint(1, 9999):04d}" if r.random() < 0.3 else None}
            if kind == "pre":
                a["pre"] = r.choice(list(DIRS))
            if kind == "post":
                a["post"] = r.choice(["NE", "NW", "SE", "SW"])
            if kind == "unit":
                d = unit_kind or r.choice(list(UNITS))
                a["unit"] = (d, r.choice(["4B", "210", "C", "12", "3", "118", "2A", "305"]) if d not in ("FL",) else str(r.randint(2, 6)))
            if kind == "dirname":
                a["name"] = DIR_WORD[r.choice(list(DIR_WORD))].title()
                a["suffix"] = r.choice(["ST", "AVE", "RD"])
            if kind == "pobox":
                a = {"pobox": r.randint(11, 2400), "city": city, "state": st, "zip5": z5, "zip4": None}
            key = (std_line(a), a["city"], a["zip5"])
            if key not in used_lines:
                used_lines.add(key)
                return a

    kinds = (["plain"] * 22 + ["pre"] * 8 + ["post"] * 4 + ["unit"] * 12 + ["dirname"] * 2 + ["pobox"] * 3 + ["zero"] * 4)
    r.shuffle(kinds)
    forced_units = ["APT", "#", "STE", "APT", "UNIT", "FL"]
    for i, k in enumerate(kinds):
        a = new_addr(k, forced_units.pop(0) if k == "unit" and forced_units else None)
        if k == "zero" and r.random() < 0.5:
            a["zip4"] = f"{r.randint(1, 9999):04d}"
        f, l = ppl[i]
        recs.append({"first": f, "last": l, "addr": a, "added": date(2021, 3, 1) + timedelta(days=r.randint(0, 1900))})
    # force the tricky ZIP shapes onto zero-ZIP records
    zeros = [x for x in recs if x["addr"]["zip5"].startswith("0")]
    zeros[0]["addr"]["zip4"] = f"{r.randint(1000, 9999):04d}"; zeros[0]["zip_style"] = "digits9num"   # 54011234 as a number
    zeros[1]["addr"]["zip4"] = None; zeros[1]["zip_style"] = "num5"                                     # 5401 as a number
    # two apartments in one building: same street line, different units, both stay
    base = next(x for x in recs if x["addr"].get("unit") and x["addr"]["unit"][0] == "APT")
    twin = dict(base["addr"]); twin["unit"] = ("APT", "7" if base["addr"]["unit"][1] != "7" else "8")
    f, l = ppl[len(recs)]
    recs.append({"first": f, "last": l, "addr": twin, "added": base["added"] + timedelta(days=40)})
    # duplicates: same household typed again later (one under a spouse's first name)
    dup_sources = r.sample([x for x in recs if x is not base], 5)
    dups = []
    for j, src in enumerate(dup_sources):
        first = src["first"] if j else r.choice([p[0] for p in ppl[60:]])
        dups.append({"first": first, "last": src["last"], "addr": src["addr"], "added": min(src["added"] + timedelta(days=r.randint(30, 600)), date(2026, 8, 28) - timedelta(days=j)),
                     "dup_of": src})
    if r.random() < 0.5:   # sometimes the earlier record is the second one typed in the list
        dups[1]["added"], dup_sources[1]["added"] = dup_sources[1]["added"], dups[1]["added"]
    allrecs = recs + dups
    r.shuffle(allrecs)
    ids = r.sample(range(10400, 19999), len(allrecs))
    for x, cid in zip(allrecs, ids):
        x["id"] = f"C{cid}"
    # keep the earliest Date Added in each standardized group
    groups = {}
    for x in allrecs:
        groups.setdefault((std_line(x["addr"]), x["addr"]["city"].upper(), x["addr"]["state"], x["addr"]["zip5"]), []).append(x)
    kept, dropped = [], []
    for g in groups.values():
        g.sort(key=lambda x: x["added"])
        kept.append(g[0]); dropped += g[1:]
    kept_ids = {x["id"] for x in kept}
    final = [x for x in allrecs if x["id"] in kept_ids]
    return {"all": allrecs, "final": final, "dropped": dropped, "twin": (base, twin), "zeros": zeros[:2]}


def render(r, x: dict) -> list:
    a = x["addr"]
    case = r.random()

    def cs(s: str) -> str:
        return s.upper() if case < 0.15 else s.lower() if case < 0.25 else s

    line2 = ""
    if a.get("pobox"):
        line1 = r.choice(["P.O. Box", "PO Box", "Post Office Box", "P O Box"]) + f" {a['pobox']}"
    else:
        parts = [str(a["num"])]
        if a.get("pre"):
            parts.append(r.choice(DIRS[a["pre"]]))
        parts.append(a["name"])
        parts.append(r.choice(SUFFIX[a["suffix"]]))
        if a.get("post"):
            parts.append(r.choice(DIRS[a["post"]]))
        line1 = " ".join(parts)
        if a.get("unit"):
            d, n = a["unit"]
            word = r.choice(UNITS[d])
            unit = f"#{n}" if d == "#" and r.random() < 0.6 else f"{word} {n}"
            if r.random() < 0.55:
                line2 = unit
            else:
                line1 = line1 + r.choice([", ", " "]) + unit
    line1 = cs(line1)
    if r.random() < 0.15:
        line1 = line1.replace(" ", "  ", 1)
    if r.random() < 0.1:
        line1 += " "
    st = a["state"]
    state = STATE_NAMES[st] if r.random() < 0.2 else (st.lower() if r.random() < 0.15 else st)
    style = x.get("zip_style")
    if style == "digits9num":
        z = int(a["zip5"] + a["zip4"])
    elif style == "num5":
        z = int(a["zip5"])
    elif a.get("zip4"):
        z = r.choice([f"{a['zip5']}-{a['zip4']}", f"{a['zip5']}-{a['zip4']}", f"{a['zip5']}{a['zip4']}", f"{a['zip5']} {a['zip4']}"])
    else:
        z = int(a["zip5"]) if not a["zip5"].startswith("0") and r.random() < 0.5 else a["zip5"]
    city = a["city"].upper() if r.random() < 0.2 else a["city"]
    name = f"{x['first']} {x['last']}"
    return [x["id"], name if r.random() > 0.1 else name.upper(), line1, line2, city, state, z, x["added"],
            r.choice(["Web store", "Web store", "Trade show", "Seed swap sign-up"])]


def acceptable(d: dict) -> bool:
    # one duplicate pair must have the earlier customer later in the file, and the pair must not be one of the
    # two zero-ZIP records whose ZIP shape is pinned
    swap = any(x["dup_of"]["added"] > x["added"] and d["all"].index(x) < d["all"].index(x["dup_of"])
               for x in d["all"] if x.get("dup_of"))
    zero_dup = any(x.get("dup_of") in d["zeros"] for x in d["all"])
    return swap and not zero_dup


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    r = rng(seed + 5)
    by_id = {x["id"]: render(r, x) for x in d["all"] if not x.get("dup_of")}
    for x in d["all"]:
        if x.get("dup_of"):
            src = by_id[x["dup_of"]["id"]]
            for _ in range(50):   # a duplicate only shows up once the address is standardized
                row = render(r, x)
                if naive_key(row) != naive_key(src):
                    break
            by_id[x["id"]] = row
    raw = [by_id[x["id"]] for x in d["all"]]
    if naive_dir:
        write_naive(raw, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    write_xlsx(os.path.join(ws, "catalog_mailing_list.xlsx"), {"Mailing list": {
        "header": ["Customer ID", "Name", "Address Line 1", "Address Line 2", "City", "State", "ZIP", "Date Added", "Source"],
        "rows": raw, "widths": {"B": 22, "C": 34, "D": 16, "E": 14, "H": 12, "I": 18}}}, creator="Stillwater")
    write_csv(os.path.join(ws, "keystone_import_template.csv"), HEADER,
              [["SAMPLE1", "JANE SAMPLE", "1200 W HIGHLAND AVE STE 4", "SPRINGFIELD", "IL", "62704-1123"]])
    suffix_lines = "\n".join(f"  {k:5} {', '.join(v)}" for k, v in SUFFIX.items())
    write_text(os.path.join(ws, "keystone_address_standards.txt"),
               "KEYSTONE MAILING SERVICES - address standards for client lists\n"
               "(condensed from USPS Publication 28; lists that do not meet this are returned or surcharged)\n"
               "\n"
               "1. Capital letters. No periods or commas anywhere in the address.\n"
               "2. Delivery Address is one line: number, pre-directional, street name, suffix,\n"
               "   post-directional, then the secondary unit. Anything on a second address line\n"
               "   (apartment, suite, unit) moves to the end of the Delivery Address.\n"
               "3. Street suffixes use the USPS abbreviation. Accepted spellings we see on client lists:\n"
               f"{suffix_lines}\n"
               "4. Directionals: NORTH N, SOUTH S, EAST E, WEST W, NORTHEAST NE, NORTHWEST NW,\n"
               "   SOUTHEAST SE, SOUTHWEST SW, before or after the street name.\n"
               "   Exception: when the direction word IS the street name (the word right before the\n"
               "   suffix, e.g. 45 North Street), keep it spelled out: 45 NORTH ST.\n"
               "5. Secondary unit designators: APARTMENT APT, SUITE STE, UNIT UNIT, BUILDING BLDG,\n"
               "   FLOOR FL, ROOM RM. If the list only shows #, write # then a space then the number\n"
               "   (22 OAK ST # 5).\n"
               "6. Post office boxes: PO BOX 123.\n"
               "7. City in capitals. State as the two-letter postal code.\n"
               "8. ZIP Code: five digits, keeping leading zeros (05401). If the list has the ZIP+4, keep it\n"
               "   as 12345-6789.\n"
               "\n"
               "Import file columns, in this order: Customer ID, Full Name, Delivery Address, City, State,\n"
               "ZIP Code. Full Name in capitals.\n")
    write_email_thread(os.path.join(ws, "email_from_ruth.txt"), [
        {"from": "Ruth Anders <ruth@stillwaterseeds.com>", "to": "you", "date": "Tue, 8 Sep 2026 10:05",
         "subject": "winter catalog list for Keystone",
         "body": ("Keystone needs the mailing list in their format by Friday - their standards sheet is in the folder, "
                  "and the template.\n\n"
                  "One catalog per address, please. People sign up at the shows and again online, and last year we "
                  "paid to mail the same house two or three times. Once the addresses are cleaned up, if two "
                  "customers land on the same address, keep whichever one has been with us longest (earliest Date "
                  "Added) and leave the other off. Different apartments in the same building are different "
                  "addresses, of course.\n\nThanks!\nRuth")}])

    rows = [[x["id"], f"{x['first']} {x['last']}".upper(), std_line(x["addr"]), x["addr"]["city"].upper(), x["addr"]["state"],
             zip_out(x["addr"])] for x in sorted(d["final"], key=lambda x: x["id"])]
    write_csv(os.path.join(ref, "addresses_clean.csv"), HEADER, rows)
    write_csv(os.path.join(sol, "addresses_clean.csv"), HEADER, rows)
    fin = d["final"]
    line_pins = sorted({x["id"] for x in fin if x["addr"].get("unit") or x["addr"].get("pre") or x["addr"].get("post")
                        or x["addr"].get("pobox") or x["addr"].get("name", "").upper() in DIR_WORD.values()})
    zip_pins = sorted({x["id"] for x in fin if x["addr"]["zip5"].startswith("0") or x["addr"].get("zip4")})
    write_json(os.path.join(ref, "notes.json"), {"dropped": [{"id": x["id"], "kept": next(k["id"] for k in fin if std_line(k["addr"]) == std_line(x["addr"]) and k["addr"]["zip5"] == x["addr"]["zip5"])} for x in d["dropped"]],
                                                  "twin_units": [d["twin"][0]["id"]], "zero_zip_ids": [x["id"] for x in d["zeros"]]})
    write_task_yaml(HERE, {
        "id": "address-standardize", "track": "desk", "category": "reformatting",
        "title": "Clean the catalog mailing list for the mail house",
        "ask": ("Keystone is mailing our winter catalog. Please clean up the mailing list to their address standard and "
                "save it as addresses_clean.csv - Ruth's email, their standards sheet and the template are in the folder.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "street suffixes, directionals and unit designators are spelled out (Street, Northeast, Apartment), "
            "abbreviated with periods (Blvd., N.W., Ste.) or in odd spellings (Str, Av, Pky, Terr); uppercasing and "
            "stripping punctuation is not enough (check: delivery address line)",
            "a direction word that is the street name itself (the word right before the suffix: "
            + " and ".join(f"'{row[2].strip()}' -> {std_line(x['addr'])}" for x, row in ((x, by_id[x['id']]) for x in d["final"])
                           if x["addr"].get("name", "").upper() in DIR_WORD.values())
            + ") stays spelled out, while a real directional before or after another name is abbreviated; an "
            "abbreviate-every-direction pass gets these wrong (check: delivery address line)",
            "the unit is on Address Line 2 for about half the apartments and must move to the end of the delivery "
            "line; a bare #12 becomes # 12 (check: delivery address line)",
            "Burlington and Providence ZIPs typed as numbers lost their leading zero (5401), one ZIP+4 came through "
            "as the bare number 54011234, and others are 972091234 or '97209 1234'; the output keeps five digits "
            "with the zero and ZIP+4 as 12345-6789 (check: city, state and ZIP)",
            "about a fifth of the states are written out in full (Oregon, North Carolina) and must become the "
            "two-letter code (check: city, state and ZIP)",
            f"{len(d['dropped'])} customers repeat an address that is only visibly the same after standardizing "
            "(one under a spouse's first name, one where the later row in the file is the earlier customer); the "
            "earliest Date Added stays, and two different apartments in one building both stay "
            "(checks: one row per mailing address; row count)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "Keystone template columns, exact order", "path": "addresses_clean.csv",
             "columns": HEADER, "exact": True},
            {"type": "csv_set_equal", "name": "one row per mailing address", "path": "addresses_clean.csv",
             "column": "Customer ID", "ref": "addresses_clean.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "addresses_clean.csv", "equals_ref": "addresses_clean.csv"},
            {"type": "csv_values_match", "name": "delivery address line", "path": "addresses_clean.csv",
             "ref": "addresses_clean.csv", "key": "Customer ID", "columns": ["Delivery Address"], "normalize": ["strip"],
             "min_accuracy": 1.0, "must_match_keys": line_pins},
            {"type": "csv_values_match", "name": "city, state and ZIP", "path": "addresses_clean.csv",
             "ref": "addresses_clean.csv", "key": "Customer ID", "columns": ["City", "State", "ZIP Code"], "normalize": ["strip"],
             "min_accuracy": 1.0, "must_match_keys": zip_pins},
        ],
    })
    print(f"seed={seed} raw={len(d['all'])} final={len(d['final'])} dropped={[x['id'] for x in d['dropped']]}")


def naive_key(row: list) -> tuple:
    import re
    line = re.sub(r"\s+", " ", re.sub(r"[.,]", "", f"{row[2]} {row[3]}".upper())).strip()
    return line, str(row[4]).upper()


def write_naive(raw: list, out: str) -> None:
    """The obvious clean-up: uppercase, strip periods and commas, glue line 2 on, ZIP as str(int), states as
    typed, dedupe on the raw address text."""
    import re
    os.makedirs(out, exist_ok=True)
    seen, rows = set(), []
    for row in raw:
        cid, name, l1, l2, city, state, z, added, src = row
        key = naive_key(row)
        line = key[0]
        if key in seen:
            continue
        seen.add(key)
        rows.append([cid, name.upper(), line, str(city).upper(), str(state).upper(), str(z)])
    write_csv(os.path.join(out, "addresses_clean.csv"), HEADER, rows)


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
