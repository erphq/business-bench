#!/usr/bin/env python3
"""business-cards-scanned: ten scanned business cards from a trade show -> one CRM contact row per person.

    python gen.py [--seed N] [--naive DIR]

Business: Lumen & Ash, a Denver architectural lighting maker, came back from an international lighting expo with a stack of
business cards. The sales coordinator scanned each card on the office scanner; marketing wants them in the CRM.

Traps (each caught by a check, see task.yaml):
  * titles vs names: one card prints the title above the name, one company is named like a person, and names carry an
    honorific ("Dr") or post-nominal ("P.Eng.") that the CRM does not want            (checks: names; titles and companies)
  * the French card prints the surname first in capitals ("LAURENT Camille")        (check: names)
  * two phones labelled T/M, Main/Mobile, Standard/Mob, Desk/Mobile, Switchboard/Mobile, printed mobile-first on two cards; one card has a fax and no mobile
                                                                                     (checks: office phones; mobile phones)
  * international format: "+44 (0)20 ..." keeps a trunk zero that E.164 drops, Australian numbers are printed domestically,
    North American numbers carry no +1                                               (checks: office phones; mobile phones)
  * one card was scanned twice                                                        (checks: one row per contact; row count)
  * every card is a small image-only scan                                             (checks: names; one row per contact)
"""
from __future__ import annotations
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["email", "first_name", "last_name", "title", "company", "office_phone", "mobile_phone", "country"]


def build(seed: int) -> dict:
    r = rng(seed)
    used = set()

    def u(f):
        while True:
            v = f()
            if v not in used:
                used.add(v); return v
    xx = lambda: u(lambda: f"{r.randint(0, 99):02d}")      # North American 555-01xx
    x3 = lambda: u(lambda: f"{r.randint(0, 999):03d}")
    fn = pick(r, ["Priya", "Tomasz", "Nadia", "Marcus", "Ingrid", "Kwame", "Sofia", "Rahul", "Leila", "Dmitri", "Chloe", "Mateo"], 9)
    ln = pick(r, ["Raman", "Novak", "Haddad", "Oyelaran", "Ashworth", "Mensah", "Mendes", "Kapoor", "Farah", "Volkov", "Brennan", "Duarte"], 9)
    C = []

    def card(key, i, title, company, office, mobile, country, email, lines):
        C.append({"key": key, "first": fn[i], "last": ln[i], "title": title, "company": company, "office": office, "mobile": mobile,
                  "country": country, "email": email, "lines": lines})
    # 1 UK, honorific, company first, T/M with (0)
    a, b = x3(), x3()
    e = f"{fn[0].lower()}@halcyonacoustics.example"
    card("uk_dr", 0, "Head of Specification", "Halcyon Acoustics Ltd", f"+442079460{a}",
         f"+447700900{b}", "United Kingdom", e,
         ["HALCYON ACOUSTICS LTD", "", f"Dr {fn[0]} {ln[0]}", "Head of Specification", "", f"T +44 (0)20 7946 0{a}",
          f"M +44 (0)7700 900{b}", e, "London EC2A 4NE  United Kingdom"])
    # 2 US, title above the name, company named like a person
    a, b = xx(), xx()
    e = f"{fn[1].lower()}.{ln[1].lower()}@morganhale.example"
    card("us_title_first", 1, "VP, Business Development", "Morgan Hale", f"+120655501{a}", f"+120655501{b}", "United States", e,
         ["VP, Business Development", f"{fn[1]} {ln[1]}", "", "MORGAN HALE", "Lighting and daylight design", "1550 Western Ave  Seattle WA",
          f"Main (206) 555-01{a}", f"Mobile (206) 555-01{b}", e])
    # 3 France, surname first in capitals, Tel./Mob. with (0)
    a, b = f"{r.randint(10, 99)} {r.randint(10, 99)}", f"{r.randint(10, 99)} {r.randint(10, 99)}"
    e = f"{fn[2].lower()}.{ln[2].lower()}@lumierevive.example"
    card("fr", 2, "Responsable Export", "Atelier Lumiere Vive", "+3346571" + a.replace(" ", ""), "+3363998" + b.replace(" ", ""), "France", e,
         ["ATELIER LUMIERE VIVE", "", f"{ln[2].upper()} {fn[2]}", "Responsable Export", "", "8 quai Saint-Vincent  69001 Lyon  France",
          f"Standard +33 (0)4 65 71 {a}", f"Mob +33 (0)6 39 98 {b}", e])
    # 4 Australia, domestic formats, mobile printed first
    a, b = f"{r.randint(1000, 9999)}", f"{r.randint(6, 999):03d}"
    e = f"{fn[3].lower()}@southernlux.example"
    card("au", 3, "Senior Lighting Designer", "Southern Lux Studio", f"+6125550{a}", f"+61491570{b}", "Australia", e,
         [f"{fn[3]} {ln[3]}", "Senior Lighting Designer", "SOUTHERN LUX STUDIO", "", f"Mobile 0491 570 {b}", f"Main (02) 5550 {a}", e,
          "Surry Hills NSW 2010  Australia"])
    # 5 Canada, post-nominal, Direct/Cell
    a, b = xx(), xx()
    e = f"{fn[4].lower()}@northshorephoto.example"
    card("ca_peng", 4, "Principal Lighting Engineer", "Northshore Photometrics Inc", f"+160455501{a}", f"+160455501{b}", "Canada", e,
         ["NORTHSHORE PHOTOMETRICS INC", "", f"{fn[4]} {ln[4]}, P.Eng.", "Principal Lighting Engineer", "", f"Desk 604-555-01{a}",
          f"Mobile 604-555-01{b}", e, "Vancouver BC  Canada"])
    # 6 UK Manchester, fax line and no mobile
    a = x3()
    e = f"{fn[5].lower()}.{ln[5].lower()}@penninebuild.example"
    card("uk_fax", 5, "Procurement Manager", "Pennine Build Group", f"+441614960{a}", "", "United Kingdom", e,
         ["PENNINE BUILD GROUP", f"{fn[5]} {ln[5]}", "Procurement Manager", "", f"T +44 (0)161 496 0{a}", "F +44 (0)161 496 0999", e,
          "Manchester M1 3BE  United Kingdom"])
    # 7 US, one number marked (mobile)
    a = xx()
    e = f"{fn[6].lower()}@brightlineelectric.example"
    card("us_mobile", 6, "Owner", "Brightline Electrical Contractors", "", f"+141555501{a}", "United States", e,
         [f"{fn[6].upper()} {ln[6].upper()}", "OWNER", "", "BRIGHTLINE ELECTRICAL CONTRACTORS", "Oakland California", "", f"Ph 415-555-01{a} (mobile)", e])
    # 8 UK, domestic numbers, mobile first
    a, b = x3(), x3()
    e = f"{fn[7].lower()}@kfarchitects.example"
    card("uk_mobile_first", 7, "Director", "Kapoor Farah Architects", f"+442079460{b}", f"+447700900{a}", "United Kingdom", e,
         [f"{fn[7]} {ln[7]}", "Director", "", "KAPOOR FARAH ARCHITECTS", "", f"Mobile  07700 900{a}", f"Office  020 7946 0{b}", e, "London SE1 9PG"])
    # 9 US, plain
    a, b = xx(), xx()
    e = f"{fn[8].lower()}.{ln[8].lower()}@cascadehealth.example"
    card("us_plain", 8, "Facilities Planning Lead", "Cascade Health System", f"+120655501{a}", f"+120655501{b}", "United States", e,
         ["Cascade Health System", "", f"{fn[8]} {ln[8]}", "Facilities Planning Lead", "", f"Switchboard (206) 555-01{a}", f"Mobile (206) 555-01{b}", e,
          "Seattle Washington 98104"])
    for c in C:
        for k in ("office", "mobile"):
            assert c[k] == "" or (c[k].startswith("+") and 11 <= len(c[k]) - 1 <= 12), c
    rows = sorted([[c["email"], c["first"], c["last"], c["title"], c["company"], c["office"], c["mobile"], c["country"]] for c in C])
    return {"C": C, "rows": rows}


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    S = os.path.join(ws, "expo_cards")
    os.makedirs(S, exist_ok=True)
    C = d["C"]
    r = rng(seed + 3)
    stack = list(C) + [C[0]]
    order = list(range(len(stack)))
    r.shuffle(order)
    files = {}
    for i, idx in enumerate(order, 1):
        c = stack[idx]
        fname = f"Scan_2026-09-17_{i:03d}.pdf"
        files.setdefault(c["key"], []).append(fname)
        write_scan_pdf(os.path.join(S, fname), c["lines"], width=r.choice([1050, 1100]), height=640, font_size=r.choice([30, 32]),
                       skew_deg=round(r.uniform(-0.5, 0.5), 2), noise=r.randint(120, 220), seed=seed * 37 + i)
    write_text(os.path.join(ws, "note_from_jess.txt"),
               "Expo cards\n\n"
               "I scanned every business card we brought back from the expo (expo_cards folder, one scan per card - I may have run one "
               "through twice). Marketing needs contacts.csv for the CRM import, one row per person:\n\n"
               "email, first_name, last_name, title, company, office_phone, mobile_phone, country\n\n"
               "- Names as the person would write them: first name, last name, no Dr / Mr / Ms and no letters after the name.\n"
               "- Title is the job title on the card. Company is the company name without the tagline.\n"
               "- Phones in international format with the country code, like +13035550100 - no spaces, no (0). Office is the main, "
               "direct or landline number; mobile is the cell. Leave one blank if the card doesn't have it. We don't keep fax numbers.\n"
               "- Country written out in full (United States, United Kingdom, Canada, ...).\n\nJess\n")
    write_csv(os.path.join(ref, "contacts.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "contacts.csv"), HEADER, d["rows"])
    figs = {}
    for c in C:
        want = [x for x in c["lines"] if x and (re.search(r"\d{3}", x) is None or "@" in x or re.search(r"\d{3}.*\d{2}", x))]
        want = [x for x in want if not re.search(r"(Ave|NSW|Lyon|Manchester|London|Oakland|Seattle|Vancouver)\b", x) or x.endswith(("Kingdom", "Canada", "France", "Australia"))]
        want = [w if not w.endswith(("Kingdom", "Canada", "France", "Australia")) else w.split("  ")[-1] for w in want]
        for fname in files[c["key"]]:
            figs[f"expo_cards/{fname}"] = want
    write_json(os.path.join(ref, "notes.json"), {"files": files, "scan_figures": figs})
    K = {c["key"]: c["email"] for c in C}
    P = "contacts.csv"
    write_task_yaml(HERE, {
        "id": "business-cards-scanned", "track": "desk", "category": "extraction",
        "title": "CRM contacts from the scanned expo business cards",
        "ask": "Jess scanned the business cards from the expo. Can you turn them into contacts.csv for the CRM? Her note says how marketing wants it.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "titles vs names: the Morgan Hale card prints 'VP, Business Development' above the person's name and the company is named like a "
            "person, and the Halcyon and Northshore cards carry 'Dr' and ', P.Eng.' around the name (checks: names; titles and companies)",
            "the French card prints the surname first in capitals ('LAURENT Camille' style), so the first line is not first name then last "
            "name (check: names)",
            "two phones with different labels on each card (T/M, Main/Mobile, Standard/Mob, Desk/Mobile, Switchboard/Mobile, Mobile/Office); the Kapoor Farah and Southern Lux cards "
            "print the mobile first, the Pennine card has an F fax line and no mobile, and the Brightline card has only a Ph number marked "
            "(mobile) (checks: office phones; mobile phones)",
            "international format: UK and French numbers print '+44 (0)20' and '+33 (0)4' with a trunk zero E.164 drops, the Australian and "
            "one London card print domestic numbers ('(02) 5550 1234', '0491 570 156', '020 7946 0123') that need +61 and +44, and North "
            "American numbers need +1 (checks: office phones; mobile phones)",
            "the Halcyon Acoustics card was scanned twice (checks: one row per contact; row count)",
            "every card is a small image-only scan with no text layer (checks: names; one row per contact)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per contact", "path": P, "column": "email", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "names", "path": P, "ref": P, "key": "email", "columns": ["first_name", "last_name"],
             "normalize": ["alnum"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "titles and companies", "path": P, "ref": P, "key": "email", "columns": ["title", "company"],
             "normalize": ["alnum"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "office phones", "path": P, "ref": P, "key": "email", "columns": ["office_phone"],
             "normalize": ["digits"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "mobile phones", "path": P, "ref": P, "key": "email", "columns": ["mobile_phone"],
             "normalize": ["digits"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "countries", "path": P, "ref": P, "key": "email", "columns": ["country"],
             "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": [K["uk_mobile_first"], K["us_mobile"]]},
        ],
    })
    print(f"seed={seed} contacts={len(d['rows'])} scans={len(stack)}")


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: one row per scan (the duplicate kept), the first line with two words as the name split at the
    first space (honorifics kept), the next line as title, phones as printed digits in printed order (first = office, second =
    mobile, fax counted), country from the address line only."""
    import re
    os.makedirs(out, exist_ok=True)
    rows = []
    for c in d["C"] + [d["C"][0]]:
        lines = [x for x in c["lines"] if x]
        phones = [re.sub(r"[^0-9+]", "", x) for x in lines if re.search(r"\d{3}.*\d{3}", x) and "@" not in x and not re.search(r"[A-Z]{1,2}\d", x.split()[-1])]
        name_i = next(i for i, x in enumerate(lines) if len(x.split()) >= 2 and "@" not in x and not re.search(r"\d", x))
        parts = lines[name_i].split(" ", 1)
        title = lines[name_i + 1] if name_i + 1 < len(lines) else ""
        country = next((k for k in ("United Kingdom", "United States", "France", "Canada", "Australia") if any(k in x for x in lines)), "")
        rows.append([c["email"], parts[0], parts[1] if len(parts) > 1 else "", title, c["company"], phones[0] if phones else "",
                     phones[1] if len(phones) > 1 else "", country])
    write_csv(os.path.join(out, "contacts.csv"), HEADER, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    emit(a.seed, build(a.seed), a.naive)
