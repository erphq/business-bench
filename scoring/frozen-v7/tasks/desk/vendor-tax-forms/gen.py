#!/usr/bin/env python3
"""vendor-tax-forms: new-vendor tax forms to the vendor tax log, TINs masked and incomplete forms flagged.

    python gen.py [--seed N]

Business: a brewery is opening a taproom and onboarding nine vendors. Accounts payable needs each vendor's legal
name, entity type, masked TIN and tax address before the first payment, and needs to know whose paperwork is not usable.

Traps (each caught by a check, see task.yaml):
  * purchasing's vendor list uses trade names; forms carry a legal name and a separate business/DBA name,
    and one letterhead shows the trade name in large type                   (check: legal and DBA names)
  * every form prints all entity options with [ ] and one [X]; the LLC box carries a tax-classification letter,
    and a single-member LLC checks the individual box                         (check: entity types)
  * one form has no box checked and no signature: form_status incomplete     (checks: form status; entity types)
  * one vendor on the list never returned a form: form_status missing         (checks: one row per vendor; form status)
  * the letterhead vendor prints a remit-to PO Box above its tax address       (check: tax addresses)
  * full TINs must not appear in the file; only the last four digits         (checks: masked TINs; no full TIN in the file)
  * a sole proprietor gives an SSN while a single-member LLC gives an EIN     (check: TIN types)
  * one form is an image-only scan                                           (checks: entity types; masked TINs)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MM = 2.8346
BIZ = "Tamarack Brewing"
EIN_PREFIX = ["07", "08", "09", "17", "18", "19", "28", "29", "49", "69", "70", "78", "79", "89", "97"]  # never issued: fictional by construction
OPTIONS = [("individual", "Individual/sole proprietor or single-member LLC"), ("c_corporation", "C corporation"), ("s_corporation", "S corporation"),
           ("partnership", "Partnership"), ("trust_estate", "Trust/estate"), ("llc", "Limited liability company. Tax classification (C=C corporation, S=S corporation, P=Partnership):")]


def build(seed: int) -> dict:
    r = rng(seed)
    ppl = people(r, 12)
    ppl = [ppl[0]] + [p for p in ppl[1:] if p[1] not in (ppl[0][1], ppl[7][1])][:6] + [ppl[7]] + ppl[8:]
    used = set()

    def ssn():
        while True:
            v = f"9{r.randint(10, 99)}-4{r.randint(0, 9)}-{r.randint(1000, 9999)}"   # 9xx area with a 40-49 group is neither an SSN nor an ITIN
            if v[-4:] not in used:
                used.add(v[-4:]); return v

    def ein():
        while True:
            v = f"{r.choice(EIN_PREFIX)}-{r.randint(1000000, 9999999)}"
            if v[-4:] not in used:
                used.add(v[-4:]); return v

    def addr():
        a, c, s, z = address(r)
        return dict(street=a, city=c, state=s, zip=z)

    p0, p7 = ppl[0], ppl[7]
    V = [
        dict(key="soleprop", legal=f"{p0[0]} {p0[1]}", dba=f"{p0[1]} Tile and Stone", trade=f"{p0[1]} Tile", entity="individual", tin_type="SSN", tin=ssn(), cat="Construction"),
        dict(key="llc_s", legal=r.choice(["Brightwork Electrical LLC", "Livewire Electric LLC", "Current Craft Electric LLC"]), dba="", entity="llc_s", llc="S", tin_type="EIN", tin=ein(), cat="Construction"),
        dict(key="letterhead", legal=r.choice(["Sparkle Services Group, Inc.", "Clearview Services Group, Inc."]), dba="", entity="c_corporation", tin_type="EIN", tin=ein(), cat="Cleaning"),
        dict(key="scan", legal=r.choice(["Hopper and Vance Refrigeration", "Ruiz and Lund Refrigeration", "Coldline Partners"]), dba="", entity="partnership", tin_type="EIN", tin=ein(), cat="Equipment"),
        dict(key="scorp", legal=r.choice(["Kettle Creek Signs Inc.", "Blue Oar Signs Inc."]), entity="s_corporation", tin_type="EIN", tin=ein(), cat="Signage"),
        dict(key="incomplete", legal=r.choice(["Northside Linen Supply LLC", "Riverside Linen Supply LLC"]), dba="", entity="", tin_type="EIN", tin=ein(), cat="Linen"),
        dict(key="trust", legal=f"{ppl[5][1]} Family Trust", dba=f"{ppl[5][1]} Properties", entity="trust_estate", tin_type="EIN", tin=ein(), cat="Rent"),
        dict(key="smllc", legal=f"{p7[0]} {p7[1]}", dba=f"{p7[1]} Pest Solutions LLC", trade=f"{p7[1]} Pest Solutions", entity="individual", tin_type="EIN", tin=ein(), cat="Pest control"),
        dict(key="missing", legal="", dba="", trade=r.choice(["Hop Valley Produce", "Green Crate Produce"]), entity="", tin_type="", tin="", cat="Food"),
    ]
    by = {v["key"]: v for v in V}
    by["letterhead"]["dba"] = by["letterhead"]["legal"].split(" Services")[0] + " Window Washing"
    by["letterhead"]["trade"] = by["letterhead"]["dba"]
    by["scorp"]["dba"] = "".join(w[0] for w in by["scorp"]["legal"].split()[:2]) + " Sign Works"
    by["scorp"]["trade"] = by["scorp"]["dba"]
    by["llc_s"]["trade"] = by["llc_s"]["legal"].replace(" LLC", "")
    by["scan"]["trade"] = by["scan"]["legal"]
    by["incomplete"]["trade"] = by["incomplete"]["legal"].replace(" Supply LLC", "")
    by["trust"]["trade"] = by["trust"]["dba"]
    for v in V:
        a = addr() if v["key"] != "missing" else dict(street="", city="", state="", zip="")
        v.update(a)
    for n, v in enumerate(V):
        sp = ppl[{1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 5}.get(n, 8)]
        v["signer"] = v["legal"] if v["key"] in ("soleprop", "smllc") else f"{sp[0]} {sp[1]}"
    by["letterhead"]["remit"] = f"PO Box {r.randint(1000, 9999)}, {by['letterhead']['city']}, {by['letterhead']['state']} {by['letterhead']['zip']}"
    ids = r.sample(range(2030, 2099), len(V))
    for v, i in zip(V, ids):
        v["id"] = f"V-{i}"
        v["form_status"] = "missing" if v["key"] == "missing" else ("incomplete" if v["key"] == "incomplete" else "complete")
    return dict(V=V, by=by, ap=person(r))


def boxes(v, checked=True, style="[X]"):
    out = []
    for code, label in OPTIONS:
        mark = style if checked and (code == v["entity"] or (code == "llc" and v["entity"].startswith("llc_"))) else "[ ]"
        if code == "llc":
            letter = v.get("llc", "") if mark != "[ ]" else "____"
            out.append(f"{mark} {label} {letter}")
        else:
            out.append(f"{mark} {label}")
    return out


def emit(seed: int) -> None:
    d = build(seed); V = d["V"]; by = d["by"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "vendor_tax_forms"); os.makedirs(F, exist_ok=True)

    def our_form(fn, v, font, pagesize, signed=True, checked=True, version="rev. 03/2024"):
        blocks = [("title", "Vendor Tax Information Form"), ("small", f"{BIZ} - Accounts Payable  |  {version}  |  Return to ap@tamarackbrewing.example"), ("hr", None),
                  ("kv", [("1. Name (as shown on your income tax return)", v["legal"]), ("2. Business name / disregarded entity name, if different", v["dba"] or "")],
                   {"col_widths": [70 * MM, 100 * MM]}),
                  ("h", "3. Federal tax classification (check only one)")]
        for ln in boxes(v, checked):
            blocks.append(("p", ln))
        blocks += [("spacer", 4),
                   ("kv", [("4. Address (number, street, suite)", v["street"]), ("5. City, state, ZIP", f"{v['city']}, {v['state']} {v['zip']}")],
                    {"col_widths": [70 * MM, 100 * MM]}),
                   ("h", "6. Taxpayer identification number"),
                   ("kv", [("Social security number", v["tin"] if v["tin_type"] == "SSN" else "___-__-____"),
                           ("Employer identification number", v["tin"] if v["tin_type"] == "EIN" else "__-_______")], {"col_widths": [70 * MM, 100 * MM]}),
                   ("h", "7. Certification"),
                   ("small", "Under penalties of perjury, I certify that the number shown on this form is my correct taxpayer identification number."),
                   ("kv", [("Signature", f"/s/ {v['signer']}" if signed else "________________________"), ("Date", "08/2{}/2026".format(len(v["key"]) % 10) if signed else "__________")],
                    {"col_widths": [70 * MM, 100 * MM]})]
        write_pdf_document(os.path.join(F, fn), blocks, font=font, pagesize=pagesize, base_size=9.5)

    our_form(f"{by['soleprop']['legal'].replace(' ', '_')}_vendor_form.pdf", by["soleprop"], "Helvetica", "letter")
    our_form(f"tax_form_{by['llc_s']['legal'].split()[0].lower()}.pdf", by["llc_s"], "Times-Roman", "a4")
    our_form(f"{by['incomplete']['trade'].replace(' ', '')}_taxform.pdf", by["incomplete"], "Times-Roman", "letter", signed=False, checked=False)
    our_form(f"VendorForm_{by['smllc']['legal'].split()[1]}.pdf", by["smllc"], "Helvetica", "a4", version="rev. 01/2026")

    # ---- S corporation: older form version laid out as a grid table
    s = by["scorp"]
    grid = [["Field", "Vendor entry"], ["Legal name", s["legal"]], ["Trade name (DBA)", s["dba"]],
            ["Tax classification", "<br/>".join(boxes(s))], ["Mailing address", f"{s['street']}<br/>{s['city']}, {s['state']} {s['zip']}"],
            ["TIN", f"EIN {s['tin']}"], ["Signed", f"/s/ {s['signer']}, President, 08/19/2026"]]
    write_pdf_document(os.path.join(F, f"{s['dba'].replace(' ', '_')}_tax_info.pdf"), [
        ("title", "New Vendor Setup - Tax Information"), ("small", f"{BIZ} Accounts Payable (form rev. 2019)"), ("spacer", 6),
        ("table", grid, {"col_widths": [45 * MM, 125 * MM], "grid": True, "shade_header": True}),
    ], font="Helvetica", base_size=9.5)

    # ---- letterhead vendor (C corporation), trade name large, remit-to PO Box above the tax address
    lh = by["letterhead"]
    write_pdf_document(os.path.join(F, f"{lh['dba'].split()[0]}_taxpayer_letter.pdf"), [
        ("title", lh["dba"].upper()), ("small", "Commercial and storefront window cleaning since 2004"), ("hr", None),
        ("right", "August 21, 2026"), ("p", f"Accounts Payable<br/>{BIZ}"), ("spacer", 6),
        ("p", "<b>Re: Taxpayer identification information</b>"), ("spacer", 4),
        ("p", f"As requested, here is our tax information for your vendor file. {lh['dba']} is a trade name of {lh['legal']}, "
              "which is the legal entity that files our tax returns. We are taxed as a C corporation."),
        ("spacer", 4),
        ("kv", [("Remit payments to", lh["remit"]), ("Legal name", lh["legal"]), ("Employer identification number", lh["tin"]),
                ("Address for tax reporting", f"{lh['street']}, {lh['city']}, {lh['state']} {lh['zip']}")], {"col_widths": [60 * MM, 110 * MM]}),
        ("spacer", 6), ("p", "Our completed classification checklist is below."),
    ] + [("small", ln) for ln in boxes(lh)] + [
        ("spacer", 10), ("p", f"Sincerely,<br/><br/>/s/ {lh['signer']}<br/>Controller, {lh['legal']}"),
    ], font="Courier", base_size=9)

    # ---- trust (Times-Roman, letter, our form with a note)
    our_form(f"{by['trust']['dba'].split()[0]}_Properties_tax_form.pdf", by["trust"], "Times-Roman", "letter", version="rev. 03/2024")

    # ---- partnership: image-only scan of our form filled on paper
    sc = by["scan"]
    lines = ["VENDOR TAX INFORMATION FORM", f"{BIZ} - Accounts Payable", "", f"1. Name: {sc['legal']}", "2. Business name: (blank)", "",
             "3. Tax classification (check one):"]
    for ln in boxes(sc):
        lines.append("  " + ln.replace("Limited liability company. Tax classification (C=C corporation, S=S corporation, P=Partnership):", "LLC - class (C/S/P):"))
    lines += ["", f"4. Address: {sc['street']}", f"5. City/State/ZIP: {sc['city']}, {sc['state']} {sc['zip']}", "", f"6. EIN: {sc['tin']}", "",
              f"Signature: /s/ {sc['signer']}", "Date: 08/24/2026"]
    write_scan_pdf(os.path.join(F, "scan_20260825_0912.pdf"), lines, font_size=30, seed=seed * 37 + 6, skew_deg=0.25, noise=220)

    # ---- purchasing's vendor list (trade names)
    rv = rng(seed + 77)
    vrows = []
    for v in sorted(V, key=lambda x: x["id"]):
        vrows.append([v["id"], v["trade"], v["cat"], rv.choice(["Kelsey", "Marco", "Dana"]), "08/1{}/2026".format(rv.randint(0, 9))])
    write_csv(os.path.join(ws, "new_vendor_requests.csv"), ["Vendor ID", "Vendor", "Category", "Requested by", "Requested"], vrows)

    ap = d["ap"]
    write_text(os.path.join(ws, "ap_instructions.txt"),
        "New vendor tax log\n\n"
        "Every vendor on new_vendor_requests.csv needs a row in vendor_tax.csv before we can pay them. Their tax forms are in vendor_tax_forms.\n\n"
        "Columns:\n"
        "  vendor_id     from the request list\n"
        "  legal_name    the name the vendor files taxes under\n"
        "  dba_name      business, trade or DBA name if different from the legal name, otherwise blank\n"
        "  entity_type   individual, c_corporation, s_corporation, partnership, trust_estate, llc_c, llc_s or llc_p\n"
        "  tin_type      SSN or EIN\n"
        "  tin_masked    last four digits only, masked like ***-**-1234 or **-***1234. Never type a full SSN or EIN into the log.\n"
        "  address, city, state, zip   the address on the tax form (not a remit-to address)\n"
        "  form_status   complete; incomplete if no tax classification is checked, the TIN is missing, or it isn't signed; missing if we have no form\n\n"
        "Fill in whatever a form does give you, even if it's incomplete. Leave fields blank when there is no form.\n\n"
        f"- {ap[0]}, AP\n")

    header = ["vendor_id", "legal_name", "dba_name", "entity_type", "tin_type", "tin_masked", "address", "city", "state", "zip", "form_status"]
    rows = []
    for v in sorted(V, key=lambda x: x["id"]):
        mask = "" if not v["tin"] else ("***-**-" + v["tin"][-4:] if v["tin_type"] == "SSN" else "**-***" + v["tin"][-4:])
        rows.append([v["id"], v["legal"], v["dba"], v["entity"], v["tin_type"], mask, v["street"], v["city"], v["state"], v["zip"], v["form_status"]])
    write_csv(os.path.join(ref, "vendor_tax.csv"), header, rows)
    write_csv(os.path.join(sol, "vendor_tax.csv"), header, rows)
    full = []
    for v in V:
        if v["tin"]:
            full += [v["tin"], v["tin"].replace("-", "")]
    write_json(os.path.join(ref, "notes.json"), {k: {"id": by[k]["id"], "legal": by[k]["legal"], "dba": by[k]["dba"], "trade": by[k]["trade"], "tin": by[k]["tin"],
                                                     "entity": by[k]["entity"], "remit": by[k].get("remit", "")} for k in by})
    kid = lambda *ks: [by[k]["id"] for k in ks]
    write_task_yaml(HERE, {
        "id": "vendor-tax-forms", "track": "desk", "category": "extraction",
        "title": "Log new vendors' tax forms with masked TINs",
        "ask": "We can't pay the new taproom vendors until their tax info is logged. Can you fill in vendor_tax.csv from the forms they sent? AP's instructions are in the folder.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the request list names vendors by trade name; the forms put the legal name on line 1 and the DBA on line 2, so a sole proprietor's legal name is a person, a single-member LLC's line 1 is its owner, and the letterhead vendor prints its trade name in capitals above the legal name (check: legal and DBA names)",
            "every form prints all seven classification options with [ ] and marks one [X]; the LLC option carries a tax-classification letter (S), and the single-member LLC checks the individual box (check: entity types)",
            "one form has no classification box checked and a blank signature line; form_status is incomplete with entity_type blank and everything else filled in (checks: form status; entity types)",
            "one vendor on the request list never sent a form; it still gets a row with form_status missing (checks: one row per vendor; row count; form status)",
            "the letterhead vendor gives a remit-to PO Box above its address for tax reporting; the log wants the tax address (check: tax addresses)",
            "the forms print full SSNs and EINs; the log must carry only the last four digits and no full number in any format (checks: masked TINs; no full TIN in the file)",
            "the sole proprietor gives an SSN and the single-member LLC an EIN although both are entity type individual (check: TIN types)",
            "the partnership's form is an image-only scan (checks: entity types; masked TINs)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "vendor_tax.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per vendor", "path": "vendor_tax.csv", "column": "vendor_id", "ref": "vendor_tax.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "vendor_tax.csv", "equals_ref": "vendor_tax.csv"},
            {"type": "csv_values_match", "name": "legal and DBA names", "path": "vendor_tax.csv", "ref": "vendor_tax.csv", "key": "vendor_id",
             "columns": ["legal_name", "dba_name"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": kid("soleprop", "smllc", "letterhead", "scorp", "trust")},
            {"type": "csv_values_match", "name": "entity types", "path": "vendor_tax.csv", "ref": "vendor_tax.csv", "key": "vendor_id",
             "columns": ["entity_type"], "min_accuracy": 1.0, "must_match_keys": kid("llc_s", "smllc", "incomplete", "scan")},
            {"type": "csv_values_match", "name": "TIN types", "path": "vendor_tax.csv", "ref": "vendor_tax.csv", "key": "vendor_id",
             "columns": ["tin_type"], "min_accuracy": 1.0, "must_match_keys": kid("soleprop", "smllc")},
            {"type": "csv_values_match", "name": "masked TINs", "path": "vendor_tax.csv", "ref": "vendor_tax.csv", "key": "vendor_id",
             "columns": ["tin_masked"], "normalize": ["digits"], "min_accuracy": 1.0, "must_match_keys": kid("soleprop", "scan", "incomplete")},
            {"type": "text_not_contains", "name": "no full TIN in the file", "path": "vendor_tax.csv", "phrases": full},
            {"type": "csv_values_match", "name": "tax addresses", "path": "vendor_tax.csv", "ref": "vendor_tax.csv", "key": "vendor_id",
             "columns": ["address", "city", "state", "zip"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": kid("letterhead", "scan")},
            {"type": "csv_values_match", "name": "form status", "path": "vendor_tax.csv", "ref": "vendor_tax.csv", "key": "vendor_id",
             "columns": ["form_status"], "min_accuracy": 1.0, "must_match_keys": kid("incomplete", "missing", "letterhead")},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
