#!/usr/bin/env python3
"""phones-to-e164: a CRM contact export with phones in every format the office ever typed, converted to the
new phone system's import template (E.164 numbers, extensions in their own column, unusable numbers flagged).

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * the Country column is blank on about half the rows; the city, state/province and postcode decide it,
    and Perth "WA" with a four-digit postcode is Australia, not Washington            (checks: country codes; e164 numbers)
  * GB, AU and DE numbers carry a trunk 0 that E.164 drops; some are written "+44 (0)20 ..." or "0044 ..."
                                                                                       (check: e164 numbers)
  * a dozen numbers carry extensions in six spellings; the extension goes to its own column   (checks: e164 numbers; extensions)
  * seven contacts have unusable numbers (7 digits, 9 digits, 11 digits, an email, "TBD", blank); they stay
    in the file with a blank number and status "invalid"                                (checks: import status; one row per contact)
  * the xlsx has a merged title row and an export-date line above the header             (check: one row per contact)
  * US and Canadian numbers both map to +1 but the country column must say US vs CA      (check: country codes)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

COUNTRY_LABELS = {
    "US": ["United States", "USA", "US", "U.S."],
    "CA": ["Canada", "CA"],
    "GB": ["United Kingdom", "UK", "England", "GB"],
    "AU": ["Australia", "AU"],
    "DE": ["Germany", "Deutschland", "DE"],
}
CA_CITIES = [("Toronto", "ON", "M5V 2T6", "416"), ("Vancouver", "BC", "V6B 1A1", "604"), ("Calgary", "AB", "T2P 1J9", "403"),
             ("Montreal", "QC", "H3B 2Y5", "514"), ("Ottawa", "ON", "K1P 5G4", "613")]
# (city, region, postcode, area code without trunk 0, subscriber prefix)
GB_CITIES = [("London", "Greater London", "SW1A 1AA", "20", "79460"), ("London", "", "EC2A 3AR", "20", "79460"),
             ("Manchester", "", "M1 1AE", "161", "4960"), ("Edinburgh", "Scotland", "EH1 1YZ", "131", "4960"),
             ("Cardiff", "Wales", "CF10 1EP", "29", "20180"), ("Leeds", "West Yorkshire", "LS1 4AP", "113", "4960")]
AU_CITIES = [("Sydney", "NSW", "2000", "2"), ("Melbourne", "VIC", "3000", "3"), ("Brisbane", "QLD", "4000", "7"), ("Perth", "WA", "6000", "8")]
DE_CITIES = [("Berlin", "Berlin", "10115", "30"), ("München", "Bayern", "80331", "89"), ("Hamburg", "Hamburg", "20095", "40"),
             ("Frankfurt am Main", "Hessen", "60311", "69"), ("Köln", "Nordrhein-Westfalen", "50667", "221")]
EXT_STYLES = [" x{n}", " ext. {n}", " ext {n}", " #{n}", ", extension {n}", " Ext: {n}"]
INVALID = ["555-0142", "TBD", "(503) 555-014", "50355501423", "{email}", "", "call the office"]

TEMPLATE_HEADER = ["contact_id", "display_name", "e164_number", "extension", "country", "import_status"]


def render_us(r, digits10: str) -> str:
    return phone_variant(digits10, r.randrange(len(PHONE_STYLES)))


def render_gb(r, area: str, rest: str) -> str:
    grp = f"{rest[:4]} {rest[4:]}" if len(rest) == 8 else f"{rest[:3]} {rest[3:]}"
    styles = [f"0{area} {grp}", f"+44 {area} {grp}", f"0044 {area} {grp}", f"+44 (0){area} {grp}",
              f"(0{area}) {grp}", f"0{area}-{grp.replace(' ', '-')}", f"0{area}{rest}"]
    return styles[r.randrange(len(styles))]


def render_gb_mobile(r, rest: str) -> str:  # rest = 6 digits after 07700
    styles = [f"07700 {rest}", f"+44 7700 {rest}", f"07700{rest}", f"+44 (0)7700 {rest}", f"0044 7700 {rest}"]
    return styles[r.randrange(len(styles))]


def render_au(r, area: str, rest: str) -> str:  # rest = 8 digits
    grp = f"{rest[:4]} {rest[4:]}"
    styles = [f"(0{area}) {grp}", f"0{area} {grp}", f"+61 {area} {grp}", f"+61 (0){area} {grp}", f"0{area}{rest}", f"0{area}-{grp.replace(' ', '-')}"]
    return styles[r.randrange(len(styles))]


def render_au_mobile(r, rest: str) -> str:  # rest = 3 digits after 0491 570
    styles = [f"0491 570 {rest}", f"+61 491 570 {rest}", f"0491570{rest}", f"+61 (0)491 570 {rest}"]
    return styles[r.randrange(len(styles))]


def render_de(r, area: str, rest: str) -> str:  # rest = 7 digits
    styles = [f"0{area} {rest}", f"0{area}/{rest}", f"+49 {area} {rest}", f"0049 {area} {rest}", f"+49 (0){area} {rest}",
              f"(0{area}) {rest[:3]} {rest[3:]}", f"0{area} {rest[:3]} {rest[3:5]} {rest[5:]}"]
    return styles[r.randrange(len(styles))]


def render_de_mobile(r, rest: str) -> str:  # rest = 7 digits after 0171
    styles = [f"0171 {rest}", f"+49 171 {rest}", f"0171{rest}", f"+49 (0)171 {rest}"]
    return styles[r.randrange(len(styles))]


def build(seed: int) -> dict:
    r = rng(seed)
    plan = ["US"] * 30 + ["CA"] * 9 + ["GB"] * 11 + ["AU"] * 9 + ["DE"] * 9
    r.shuffle(plan)
    ppl = people(r, len(plan) + 8)
    contacts = []
    for k, country in enumerate(plan):
        f, l = ppl[k]
        c = {"first": f, "last": l, "country": country, "company": r.choice(COMPANIES)[0], "ext": "", "tag": "plain"}
        if country == "US":
            city, st, z = r.choice(CITIES)
            d = phone_digits(r)
            c.update(city=city, region=st, postcode=z, street=f"{r.randint(12, 9899)} {r.choice(STREETS)}", e164=f"+1{d}", phone=render_us(r, d))
        elif country == "CA":
            city, st, z, area = r.choice(CA_CITIES)
            d = f"{area}555{r.randint(100, 999):03d}{r.randint(0, 9)}"
            c.update(city=city, region=st, postcode=z, street=f"{r.randint(12, 2899)} {r.choice(STREETS)}", e164=f"+1{d}", phone=render_us(r, d))
        elif country == "GB":
            city, region, z, area, pre = r.choice(GB_CITIES)
            if r.random() < 0.25:
                rest = f"900{r.randint(100, 999)}"
                c.update(e164=f"+447700{rest}", phone=render_gb_mobile(r, rest))
            else:
                rest = pre + "".join(r.choice("0123456789") for _ in range(10 - len(area) - len(pre)))
                c.update(e164=f"+44{area}{rest}", phone=render_gb(r, area, rest))
            c.update(city=city, region=region, postcode=z, street=f"{r.randint(1, 240)} {r.choice(['High Street', 'Station Road', 'Church Lane', 'Victoria Road', 'King Street', 'Queens Road'])}")
        elif country == "AU":
            city, st, z, area = r.choice(AU_CITIES)
            if r.random() < 0.3:
                rest = f"{r.randint(100, 999)}"
                c.update(e164=f"+61491570{rest}", phone=render_au_mobile(r, rest))
            else:
                rest = f"5550{r.randint(1000, 9999)}"
                c.update(e164=f"+61{area}{rest}", phone=render_au(r, area, rest))
            c.update(city=city, region=st, postcode=z, street=f"{r.randint(1, 480)} {r.choice(['George St', 'Pitt St', 'Collins St', 'Queen St', 'Hay St', 'Elizabeth St'])}")
        else:  # DE
            city, land, z, area = r.choice(DE_CITIES)
            rest = f"{r.randint(1000000, 9999999)}"
            if r.random() < 0.3:
                c.update(e164=f"+49171{rest}", phone=render_de_mobile(r, rest))
            else:
                c.update(e164=f"+49{area}{rest}", phone=render_de(r, area, rest))
            c.update(city=city, region=land, postcode=z, street=f"{r.choice(['Hauptstraße', 'Bahnhofstraße', 'Schillerstraße', 'Gartenweg', 'Lindenallee'])} {r.randint(1, 180)}")
        c["country_label"] = "" if r.random() < 0.5 else r.choice(COUNTRY_LABELS[country])
        contacts.append(c)
    # extensions on twelve +1 rows
    plus1 = [c for c in contacts if c["country"] in ("US", "CA")]
    for k, c in enumerate(r.sample(plus1, 12)):
        n = r.choice([r.randint(1, 9), r.randint(10, 99), r.randint(100, 999)])
        c["ext"] = str(n); c["phone"] = c["phone"] + EXT_STYLES[k % len(EXT_STYLES)].format(n=n); c["tag"] = "ext"
    # seven invalid rows (US/CA/GB/AU/DE mix) - make them distinct contacts appended so every country keeps its count
    for k, bad in enumerate(INVALID):
        f, l = ppl[len(plan) + k]
        country = ["US", "US", "US", "CA", "GB", "AU", "DE"][k]
        if country == "US":
            city, st, z = r.choice(CITIES)
        elif country == "CA":
            city, st, z, _ = r.choice(CA_CITIES)
        elif country == "GB":
            city, st, z, _, _ = r.choice(GB_CITIES)
        elif country == "AU":
            city, st, z, _ = r.choice(AU_CITIES)
        else:
            city, st, z, _ = r.choice(DE_CITIES)
        contacts.append({"first": f, "last": l, "country": country, "company": r.choice(COMPANIES)[0], "ext": "", "tag": "invalid",
                         "city": city, "region": st, "postcode": z, "street": f"{r.randint(12, 999)} {r.choice(STREETS)}", "e164": "",
                         "phone": bad.format(email=email_for(r, f, l)), "country_label": "" if r.random() < 0.5 else r.choice(COUNTRY_LABELS[country])})
    # make sure Perth (AU, "WA") appears at least once with a blank country label
    perth = [c for c in contacts if c["city"] == "Perth"]
    if not perth:
        c = next(c for c in contacts if c["country"] == "AU" and c["tag"] == "plain")
        rest = c["e164"][len("+61") + 1:]
        c.update(city="Perth", region="WA", postcode="6000", e164=f"+618{rest}", phone=render_au(r, "8", rest))
        perth = [c]
    perth[0]["country_label"] = ""; perth[0]["tag"] = perth[0]["tag"] if perth[0]["tag"] != "plain" else "perth"
    r.shuffle(contacts)
    for k, c in enumerate(contacts):
        c["id"] = f"C-{1001 + k}"
    return {"contacts": contacts}


def emit(seed: int) -> None:
    d = build(seed)
    contacts = d["contacts"]
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 991)
    xrows = []
    for c in contacts:
        first = name_noise(r, c["first"]); last = name_noise(r, c["last"])
        xrows.append([c["id"], first, last, c["company"], c["phone"], c["street"], c["city"], c["region"], c["postcode"], c["country_label"]])
    write_xlsx(os.path.join(ws, "contacts_export.xlsx"), {"Contacts": {
        "merged_title": "Kestrel Analytics - CRM contact export", "preamble": [["Exported 2026-09-08 by Marcus", "", "", "", "", "", "", "", "", "All active contacts"]],
        "header": ["Contact ID", "First Name", "Last Name", "Company", "Phone", "Street", "City", "State/Province", "Postal Code", "Country"],
        "rows": xrows, "widths": {"D": 28, "E": 24, "F": 26, "G": 18, "H": 22}, "freeze": "A4"}}, creator="Kestrel CRM")
    write_csv(os.path.join(ws, "ringline_import_template.csv"), TEMPLATE_HEADER, [["C-0001", "Jane Example", "+15035550123", "", "US", "ok"]])
    write_text(os.path.join(ws, "ringline_import_notes.txt"), (
        "Ringline contact import - file notes (from your onboarding specialist)\n"
        "\n"
        "Use ringline_import_template.csv exactly: same six columns, same order, same spelling of the header. One row per\n"
        "contact in your export, including contacts we will not be able to dial.\n"
        "\n"
        "contact_id      your CRM id, unchanged.\n"
        "display_name    First Last.\n"
        "e164_number     the full international number in E.164: a plus sign, the country calling code, then the national\n"
        "                number with no spaces, dashes, brackets or trunk zero (so 020 7946 0958 in the UK becomes\n"
        "                +442079460958 and (02) 5550 1234 in Australia becomes +61255501234). Never include an extension\n"
        "                here. Leave it blank when import_status is invalid.\n"
        "extension       digits only, blank when the contact has no extension.\n"
        "country         two-letter ISO code of the contact's address (US, CA, GB, AU, DE, ...). We use it to pick the\n"
        "                calling code and to validate the number, so fill it in even when your export left it blank.\n"
        "import_status   ok when the number is complete and dialable, invalid when it is not (missing digits, extra digits,\n"
        "                not a phone number at all). A complete national number is 10 digits for US and CA, 10 for GB after\n"
        "                the leading zero, 9 for AU, and 9 to 11 for DE.\n"
        "\n"
        "Rows marked invalid still import as name-only contacts, so keep them in the file.\n"))
    header = TEMPLATE_HEADER
    out = sorted(contacts, key=lambda c: c["id"])
    rows = [[c["id"], f"{c['first']} {c['last']}", c["e164"], c["ext"], c["country"], "invalid" if c["tag"] == "invalid" else "ok"] for c in out]
    write_csv(os.path.join(ref, "contacts_e164.csv"), header, rows)
    write_csv(os.path.join(sol, "contacts_e164.csv"), header, rows)
    trap_ids = sorted(c["id"] for c in out if c["tag"] != "plain" or c["country"] not in ("US", "CA") or c["country_label"] == "")
    write_json(os.path.join(ref, "notes.json"), {"invalid_ids": sorted(c["id"] for c in out if c["tag"] == "invalid"),
                                                  "extension_ids": sorted(c["id"] for c in out if c["tag"] == "ext"),
                                                  "perth_id": next(c["id"] for c in out if c["city"] == "Perth" and c["country_label"] == ""),
                                                  "blank_country_ids": sorted(c["id"] for c in out if c["country_label"] == "")})
    write_task_yaml(HERE, {
        "id": "phones-to-e164", "track": "desk", "category": "reformatting",
        "title": "Convert the CRM contact phones to the new phone system's import file",
        "ask": ("We are moving our phones to Ringline and they need every contact's number in their import format; their template "
                "and notes are in the folder. Convert contacts_export.xlsx and save the result as contacts_e164.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the Country column is blank on about half the rows; city, state/province and postcode decide it, and Perth \"WA\" with a four-digit postcode is Australia, not Washington (check: country codes)",
            "GB, AU and DE numbers carry a trunk 0 that E.164 drops; some are written \"+44 (0)20 ...\", \"0044 ...\" or \"030/1234567\" (check: e164 numbers)",
            "twelve numbers carry extensions in six spellings (x204, ext. 12, #3, \", extension 45\"); the extension goes to its own column and never into the number (check: e164 numbers; extensions)",
            "seven contacts have unusable numbers (7 digits, 9 digits, 11 digits not starting with 1, an email address, \"TBD\", blank, \"call the office\"); they stay in the file with a blank number and status invalid (check: import status; one row per contact)",
            "the xlsx has a merged title row and an export-date line above the header (check: one row per contact)",
            "US and Canadian numbers both map to +1, but the country column must say US or CA from the address (check: country codes)",
            "the template's six columns in exact order and the template's status spellings ok / invalid (check: template columns; import status)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns", "path": "contacts_e164.csv", "columns": header, "exact": True},
            {"type": "csv_set_equal", "name": "one row per contact", "path": "contacts_e164.csv", "column": "contact_id", "ref": "contacts_e164.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "contacts_e164.csv", "equals_ref": "contacts_e164.csv"},
            {"type": "csv_values_match", "name": "e164 numbers", "path": "contacts_e164.csv", "ref": "contacts_e164.csv", "key": "contact_id",
             "columns": ["e164_number"], "min_accuracy": 1.0, "must_match_keys": trap_ids},
            {"type": "csv_values_match", "name": "extensions", "path": "contacts_e164.csv", "ref": "contacts_e164.csv", "key": "contact_id",
             "columns": ["extension"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "country codes", "path": "contacts_e164.csv", "ref": "contacts_e164.csv", "key": "contact_id",
             "columns": ["country"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "import status", "path": "contacts_e164.csv", "ref": "contacts_e164.csv", "key": "contact_id",
             "columns": ["import_status"], "min_accuracy": 1.0},
        ],
    })
    print(f"seed={seed}: {len(contacts)} contacts, {sum(1 for c in contacts if c['tag'] == 'invalid')} invalid, "
          f"{sum(1 for c in contacts if c['tag'] == 'ext')} with extensions, {sum(1 for c in contacts if c['country_label'] == '')} blank countries")


if __name__ == "__main__":
    emit(argparse_seed())
