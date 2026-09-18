#!/usr/bin/env python3
"""Generator for the customer-dedupe desk task.

    python gen.py [--seed N]

Rewrites workspace/, reference/ and reference_solution/ for the seed and
patches the one seed-dependent line in task.yaml (the `must_match_keys:`
flow list of VIP emails). Re-running with the same seed is byte-identical;
the xlsx is written with fixed document properties and zip timestamps.

Different seeds re-roll people, companies, emails and phones; the trap
structure is fixed:

  * customers.xlsx has a title row and a blank row before the header (row 3)
  * 180 data rows: 136 distinct people with an email, 32 duplicate rows
    (30 people twice, 2 people three times) whose emails differ only by
    case and/or surrounding whitespace, 12 rows with no usable email
    (blank, "n/a" or "-"), 3 of which are name-duplicates of emailed people
  * phones in seven formats; duplicate rows repeat the same digits in a
    different format, and in three cases one of the rows has a blank phone
  * names with trailing/leading spaces, ALL CAPS, a few lowercase, some
    with a middle initial
  * vip.txt lists 15 emails, 6 of them in a different case than the sheet
    and 2 with trailing whitespace; 4 VIPs are among the duplicated people
  * email_from_sarah.txt carries the rules: lead vs customer, drop no-email
    rows, one row per person, HubSpot template columns
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import random
import re
import shutil
import zipfile
from datetime import datetime, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

HERE = os.path.dirname(os.path.abspath(__file__))

FIRST = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "David",
         "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah",
         "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy", "Matthew", "Betty", "Anthony",
         "Margaret", "Mark", "Sandra", "Donald", "Ashley", "Steven", "Kimberly", "Paul", "Emily",
         "Andrew", "Donna", "Joshua", "Michelle", "Kenneth", "Carol", "Kevin", "Amanda", "Brian",
         "Dorothy", "George", "Melissa", "Timothy", "Deborah", "Ronald", "Stephanie", "Edward",
         "Rebecca", "Jason", "Sharon", "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen",
         "Gary", "Amy", "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna", "Stephen",
         "Brenda", "Larry", "Pamela", "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen",
         "Priya", "Wei", "Carlos", "Fatima", "Hiroshi", "Amara", "Luis", "Ingrid", "Omar", "Sofia"]
LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez",
        "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore",
        "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
        "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres",
        "Nguyen", "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell",
        "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker",
        "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales", "Murphy", "Cook",
        "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey", "Reed", "Kelly",
        "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks", "Chavez", "Wood",
        "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes", "Price", "Alvarez", "Castillo", "Sanders",
        "Patel", "Myers", "Long", "Ross", "Foster", "Okafor", "Tanaka", "Lindqvist", "Haddad"]
COMPANIES = [
    ("Acme Industrial", "acmeindustrial.com"), ("Brightwater Dental", "brightwaterdental.com"),
    ("Cedar & Pine Landscaping", "cedarpine.co"), ("Dorsey Freight", "dorseyfreight.com"),
    ("Ellington Bakeries", "ellingtonbakes.com"), ("Foxglove Interiors", "foxgloveinteriors.com"),
    ("Granite Peak Outfitters", "granitepeak.com"), ("Harbor Light Marine", "harborlightmarine.com"),
    ("Ironwood Fabrication", "ironwoodfab.com"), ("Juniper Street Cafe", "juniperstreet.cafe"),
    ("Kestrel Analytics", "kestrelanalytics.io"), ("Lakeside Veterinary", "lakesidevet.com"),
    ("Meridian Title", "meridiantitle.com"), ("Northfield Auto Body", "northfieldauto.com"),
    ("Oakhurst Pediatrics", "oakhurstpeds.org"), ("Pinnacle Roofing", "pinnacleroofing.com"),
    ("Quarry Road Nursery", "quarryroad.com"), ("Redwood Property Mgmt", "redwoodpm.com"),
    ("Silverline Logistics", "silverlinelogistics.com"), ("Tamarack Brewing", "tamarackbrewing.com"),
    ("Uptown Fitness", "uptownfit.com"), ("Vantage Point Media", "vantagepointmedia.com"),
    ("Westbrook Plumbing", "westbrookplumbing.com"), ("Yellowtail Seafood", "yellowtailseafood.com"),
    ("Blue Heron Consulting", "blueheronconsulting.com"), ("Copperfield Law", "copperfieldlaw.com"),
    ("Driftwood Studio", "driftwoodstudio.design"), ("Everline Insurance", "everline.com"),
    ("Fairmont Realty", "fairmontrealty.com"), ("Glasshouse Florals", "glasshouseflorals.com"),
    ("Hollowell & Sons", "hollowellsons.com"), ("Ivy Lane Books", "ivylanebooks.com"),
    ("Jasper Creek Farms", "jaspercreekfarms.com"), ("Kingfisher Tech", "kingfishertech.io"),
    ("Larkspur Wellness", "larkspurwellness.com"), ("Mosaic Architecture", "mosaicarch.com"),
]
PERSONAL = ["gmail.com", "gmail.com", "gmail.com", "yahoo.com", "outlook.com", "icloud.com", "hotmail.com"]
AREAS = ["415", "510", "650", "212", "312", "617", "206", "303", "512", "702"]
NOTES = ["", "", "", "", "", "Met at trade show 2024", "Referred by Karen", "Do not call before 10am",
         "Prefers email", "Renewal due Q4", "Sent brochure", "Asked for quote", "Switched from competitor",
         "Left voicemail", "Interested in premium tier", "Billing contact", "Moved offices 2025"]
DUP_NOTES = ["", "", "re-entered by JT", "duplicate?", "new record - could not find old one", "re-entered 2023", ""]

N_PEOPLE = 136        # distinct people with an email
N_DUP_PEOPLE = 30     # 28 x one extra row, 2 x two extra rows  -> 32 extra rows
N_NO_EMAIL = 12       # 3 name-dups of emailed people + 9 new people
N_VIP = 15

PHONE_FMTS = [
    lambda a, x: f"({a}) 555-{x}",
    lambda a, x: f"{a}.555.{x}",
    lambda a, x: f"+1 {a} 555 {x}",
    lambda a, x: f"{a}-555-{x}",
    lambda a, x: f"{a}555{x}",
    lambda a, x: f"1-{a}-555-{x}",
    lambda a, x: f"+1 ({a}) 555-{x}",
]


FIXED_STAMP = "2026-09-10T07:42:00Z"


def freeze_zip(path: str) -> None:
    """Rewrite an xlsx with fixed zip entry timestamps and a fixed dcterms:modified
    (openpyxl stamps now() on save) so the output is byte-identical."""
    with zipfile.ZipFile(path) as zin:
        items = [(zi.filename, zin.read(zi.filename)) for zi in zin.infolist()]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items:
            if name == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                              rb"\g<1>" + FIXED_STAMP.encode() + rb"\g<2>", data)
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zout.writestr(zi, data)
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def fmt_phone_canonical(p):
    return f"({p[0]}) 555-{p[1]}" if p else ""


def name_variant(rng: random.Random, first: str, last: str, kind: str) -> str:
    full = f"{first} {last}"
    if kind == "trail":
        return full + " " * rng.randint(1, 2)
    if kind == "lead":
        return " " + full
    if kind == "caps":
        return full.upper()
    if kind == "lower":
        return full.lower()
    return full


def email_variant(rng: random.Random, canon: str, kind: str) -> str:
    local, dom = canon.split("@")
    if kind == "title":
        return ".".join(p.capitalize() for p in local.split(".")) + "@" + dom
    if kind == "domcaps":
        return local + "@" + dom.upper()
    if kind == "caps":
        return canon.upper()
    if kind == "ws":
        return " " * rng.randint(1, 2) + canon + " " * rng.randint(0, 1)
    if kind == "title_ws":
        return " " + ".".join(p.capitalize() for p in local.split(".")) + "@" + dom + " "
    return canon


def build(seed: int) -> dict:
    rng = random.Random(seed)

    # people --------------------------------------------------------------
    pairs = set()
    people: list[dict] = []
    while len(people) < N_PEOPLE + 9:
        f, l = rng.choice(FIRST), rng.choice(LAST)
        if (f, l) in pairs:
            continue
        pairs.add((f, l))
        people.append(dict(first=f, last=l))
    emailed, no_email_new = people[:N_PEOPLE], people[N_PEOPLE:]

    used_emails: set[str] = set()
    used_phones: set[tuple[str, str]] = set()
    for p in emailed + no_email_new:
        p["company"] = rng.choice(COMPANIES) if rng.random() < 0.72 else None
        p["middle"] = rng.choice("ABCDEJKLMRST") + "." if rng.random() < 0.08 else ""
        if rng.random() < 0.08:
            p["phone"] = None
        else:
            while True:
                ph = (rng.choice(AREAS), f"{rng.randint(100, 199):04d}")
                if ph not in used_phones:
                    used_phones.add(ph)
                    p["phone"] = ph
                    break
    for p in emailed:
        f, l = p["first"].lower(), p["last"].lower()
        while True:
            dom = p["company"][1] if p["company"] and rng.random() < 0.6 else rng.choice(PERSONAL)
            pat = rng.randint(0, 4)
            local = [f"{f}.{l}", f"{f[0]}{l}", f"{f}_{l}", f"{f}{l}{rng.randint(1, 99)}", f"{f}.{l[0]}"][pat]
            em = f"{local}@{dom}"
            if em not in used_emails:
                used_emails.add(em)
                p["email"] = em
                break

    # rows ----------------------------------------------------------------
    rows: list[dict] = []  # name, email, phone, company, notes, person(index or None)

    def make_row(p: dict, idx, is_dup: bool, blank_phone: bool = False) -> dict:
        r = rng.random()
        if is_dup:
            nk = "caps" if r < 0.35 else "trail" if r < 0.6 else "lead" if r < 0.7 else "lower" if r < 0.78 else "clean"
        else:
            nk = "clean" if r < 0.66 else "trail" if r < 0.8 else "caps" if r < 0.9 else "lead" if r < 0.96 else "lower"
        first = f"{p['first']} {p['middle']}".strip() if p["middle"] else p["first"]
        name = name_variant(rng, first, p["last"], nk)
        if is_dup:
            ek = rng.choice(["title", "domcaps", "caps", "ws", "title_ws"])
        else:
            r2 = rng.random()
            ek = "clean" if r2 < 0.82 else "title" if r2 < 0.94 else "ws"
        email = email_variant(rng, p["email"], ek) if p.get("email") else None
        phone = "" if (p["phone"] is None or blank_phone) else rng.choice(PHONE_FMTS)(*p["phone"])
        if is_dup:
            company = "" if not p["company"] or rng.random() < 0.3 else p["company"][0]
            notes = rng.choice(DUP_NOTES)
        else:
            company = p["company"][0] if p["company"] else ""
            notes = rng.choice(NOTES)
        return dict(name=name, email=email, phone=phone, company=company, notes=notes, person=idx)

    for i, p in enumerate(emailed):
        rows.append(make_row(p, i, False))

    dup_people = rng.sample(range(N_PEOPLE), N_DUP_PEOPLE)
    triple = set(dup_people[:2])
    blank_phone_people = set(dup_people[2:5])  # dup row carries a blank phone
    for i in dup_people:
        p = emailed[i]
        # make sure the duplicate's raw email string differs from the primary row's
        while True:
            d = make_row(p, i, True, blank_phone=(i in blank_phone_people))
            if d["email"] != rows[i]["email"]:
                break
        rows.append(d)
        if i in triple:
            while True:
                d2 = make_row(p, i, True)
                if d2["email"] not in (rows[i]["email"], d["email"]):
                    break
            rows.append(d2)
    # one of the blank-phone people: swap so the PRIMARY row is the blank one
    swap_i = sorted(blank_phone_people)[0]
    prim = rows[swap_i]
    dup_row = next(r for r in rows[N_PEOPLE:] if r["person"] == swap_i)
    prim["phone"], dup_row["phone"] = dup_row["phone"], prim["phone"]

    # rows with no usable email
    no_email_rows: list[dict] = []
    name_dup_people = rng.sample([i for i in range(N_PEOPLE) if i not in dup_people], 3)
    for i in name_dup_people:
        p = emailed[i]
        r = make_row(p, i, False)
        r["email"] = None
        r["notes"] = rng.choice(["", "no email on file", "call only"])
        no_email_rows.append(r)
    for p in no_email_new:
        r = make_row(p, None, False)
        r["email"] = None
        no_email_rows.append(r)
    junk = rng.sample(range(len(no_email_rows)), 3)
    for k, val in zip(junk, ["n/a", "n/a", "-"]):
        no_email_rows[k]["email"] = val
    rows += no_email_rows
    assert len(rows) == 180, len(rows)

    order = list(range(len(rows)))
    rng.shuffle(order)
    rows = [rows[k] for k in order]
    # duplicates should be re-entries: push every dup row after its person's first row
    seen: set[int] = set()
    firsts, later = [], []
    for r in rows:
        if r["person"] is not None and r["person"] in seen and r["email"] not in (None, "n/a", "-"):
            later.append(r)
        else:
            firsts.append(r)
            if r["person"] is not None:
                seen.add(r["person"])
    rows = firsts
    for r in later:
        pos = rng.randint(rows.index(next(x for x in rows if x["person"] == r["person"])) + 1, len(rows))
        rows.insert(pos, r)

    day = datetime(2019, 3, 4)
    for r in rows:
        day += timedelta(days=rng.randint(0, 9))
        r["created"] = day + timedelta(hours=rng.randint(8, 17), minutes=rng.randint(0, 59))

    # vips ----------------------------------------------------------------
    vip_idx = dup_people[:4] + rng.sample([i for i in range(N_PEOPLE) if i not in dup_people[:4]], N_VIP - 4)
    rng.shuffle(vip_idx)
    vip_lines = []
    variants = ["title", "domcaps", "caps", "title", "domcaps", "caps"]
    for k, i in enumerate(vip_idx):
        em = emailed[i]["email"]
        if k < 6:
            em = email_variant(rng, em, variants[k])
        if k in (1, 7):
            em = em + "  "
        vip_lines.append(em)
    extra_vip = next(i for i in vip_idx if i not in dup_people[:4])
    must_match = sorted(emailed[i]["email"] for i in dup_people[:4] + [extra_vip])

    return dict(emailed=emailed, rows=rows, vip_idx=vip_idx, vip_lines=vip_lines, must_match=must_match)


def patch_task_yaml(must_match: list[str]) -> None:
    path = os.path.join(HERE, "task.yaml")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new_list = "[" + ", ".join(must_match) + "]"
    patched, n = re.subn(r"^(\s*must_match_keys:\s*)\[[^\]]*\]", lambda m: m.group(1) + new_list, text,
                         count=1, flags=re.M)
    if n and patched != text:
        with open(path, "w", encoding="utf-8") as f:
            f.write(patched)


def emit(seed: int) -> None:
    data = build(seed)
    emailed, rows = data["emailed"], data["rows"]

    ws = os.path.join(HERE, "workspace")
    ref = os.path.join(HERE, "reference")
    sol = os.path.join(HERE, "reference_solution")
    for d in (ws, ref, sol):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    # customers.xlsx --------------------------------------------------------
    wb = Workbook()
    sh = wb.active
    sh.title = "Customers"
    fixed = datetime(2026, 9, 10, 7, 42, 0)
    wb.properties.created = fixed
    wb.properties.modified = fixed
    wb.properties.creator = "LegacyCRM Export"
    wb.properties.lastModifiedBy = "LegacyCRM Export"
    sh["A1"] = "Customer Export - LegacyCRM 4.2 - generated 09/10/2026 07:42 - all active contacts"
    sh["A1"].font = Font(bold=True, size=13)
    sh.merge_cells("A1:F1")
    headers = ["Full Name", "E-mail", "Phone", "Company", "Notes", "Created"]
    for j, h in enumerate(headers, 1):
        c = sh.cell(row=3, column=j, value=h)
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="left")
    for i, r in enumerate(rows, start=4):
        sh.cell(row=i, column=1, value=r["name"])
        sh.cell(row=i, column=2, value=r["email"] if r["email"] else None)
        sh.cell(row=i, column=3, value=r["phone"] if r["phone"] else None)
        sh.cell(row=i, column=4, value=r["company"] if r["company"] else None)
        sh.cell(row=i, column=5, value=r["notes"] if r["notes"] else None)
        c = sh.cell(row=i, column=6, value=r["created"])
        c.number_format = "m/d/yyyy h:mm"
    for col_letter, width in zip("ABCDEF", (26, 34, 20, 26, 34, 18)):
        sh.column_dimensions[col_letter].width = width
    xlsx_path = os.path.join(ws, "customers.xlsx")
    wb.save(xlsx_path)
    freeze_zip(xlsx_path)

    # template, vip list, email -------------------------------------------
    with open(os.path.join(ws, "hubspot_template.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("First Name,Last Name,Email,Phone Number,Company Name,Lifecycle Stage\n")
    with open(os.path.join(ws, "vip.txt"), "w", encoding="utf-8") as f:
        f.write("VIP customers\n\n")
        for line in data["vip_lines"]:
            f.write(line + "\n")
    with open(os.path.join(ws, "email_from_sarah.txt"), "w", encoding="utf-8") as f:
        f.write(
            "From: Sarah Whitfield\n"
            "Sent: Wednesday, September 10, 2026 4:51 PM\n"
            "Subject: RE: HubSpot import - old customer list\n"
            "\n"
            "Hi,\n"
            "\n"
            "Before the old customer export goes into HubSpot, a few rules so the import wizard\n"
            "doesn't choke and we don't end up with a mess:\n"
            "\n"
            "1. Use HubSpot's template columns exactly (hubspot_template.csv is in the folder).\n"
            "2. Lifecycle stage: set everyone to \"lead\", except the people in vip.txt - they are\n"
            "   existing accounts, so they should be \"customer\".\n"
            "3. Drop anyone we don't have an email address for. HubSpot keys contacts on email\n"
            "   and there is nothing we can do with the rest.\n"
            "4. The old system double-entered a lot of people over the years. One row per\n"
            "   person, please - it's the same person if it's the same email.\n"
            "5. Don't spend time prettifying names - whatever casing the export has is fine,\n"
            "   HubSpot's dedupe and the reps will tidy those up later.\n"
            "\n"
            "The export itself is untouched from the old system, so expect it to be ugly.\n"
            "\n"
            "Thanks!\n"
            "Sarah\n"
        )

    # reference ------------------------------------------------------------
    vip_set = set(data["vip_idx"])
    by_person: dict[int, list[dict]] = {}
    for r in rows:
        if r["person"] is not None and r["email"] not in (None, "n/a", "-"):
            by_person.setdefault(r["person"], []).append(r)
    out_rows = []
    for i, p in enumerate(emailed):
        prs = by_person[i]
        company = next((r["company"] for r in prs if r["company"]), "")
        first = f"{p['first']} {p['middle']}".strip() if p["middle"] else p["first"]
        out_rows.append([first, p["last"], p["email"], fmt_phone_canonical(p["phone"]), company,
                         "customer" if i in vip_set else "lead"])
    out_rows.sort(key=lambda r: (r[1].lower(), r[0].lower(), r[2]))
    header = ["First Name", "Last Name", "Email", "Phone Number", "Company Name", "Lifecycle Stage"]
    for d in (ref, sol):
        with open(os.path.join(d, "hubspot_import.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(header)
            w.writerows(out_rows)
    with open(os.path.join(ref, "notes.txt"), "w", encoding="utf-8") as f:
        f.write(f"seed={seed}\nvip_emails={sorted(emailed[i]['email'] for i in vip_set)}\n"
                f"must_match_keys={data['must_match']}\n")

    patch_task_yaml(data["must_match"])

    n_dup = sum(len(v) - 1 for v in by_person.values())
    n_noemail = sum(1 for r in rows if r["email"] in (None, "n/a", "-"))
    print(f"seed={seed}: {len(rows)} sheet rows = {len(emailed)} people + {n_dup} duplicate rows + "
          f"{n_noemail} no-email rows; {len(vip_set)} VIPs; must_match_keys={data['must_match']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    emit(ap.parse_args().seed)
