#!/usr/bin/env python3
"""Deterministic seed generator for the purchase-requests-approvals build task.

    python gen.py [--seed N]

Writes:
  seed/budgets.csv          90 rows -> 72 budget lines for fiscal year 2026-27 (12 lines from 2025-26 mixed in,
                            exact duplicates, account codes written 01-3600-4300 / 01.3600.4300 / 0136004300,
                            department names written several ways, amounts partly as "$48,000.00" strings)
  seed/vendors.csv          90 rows -> 84 vendors (exact duplicates, the same vendor under a tax ID written with and
                            without its hyphen and "Inc." vs "Inc", inactive vendors)
  seed/requests.csv         130 purchase requests entered so far this year (account codes and departments in the
                            variants above, amounts partly as currency strings, PO numbers written PO-27-0045 /
                            PO27-0045 / PO-27-9, mixed dates, one impossible negative amount on a rejected request)
  reference/counts.json     every number checklist.md and changes/*.md quote, computed from the truth

Seed 0 is the canonical public variant (checklist.md quotes its numbers). Other seeds re-roll vendors, budgets, and
requests; the pinned checklist lines keep their budgets. counts.json is recomputed from the truth.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "lib"))
from bizgen import argparse_seed, date_variant, write_csv  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
REF_DIR = os.path.join(HERE, "reference")

TODAY = date(2026, 9, 13)
THRESHOLD = 250000  # cents: 2,500.00 and above needs the business office too
DEPTS = [  # (department, fund, function, approver, requesters)
    ("Transportation", "01", "3600", "Denise Harlan", ["Luis Ferreira", "Karen Whitlock", "Omar Siddiqui"]),
    ("Facilities & Maintenance", "01", "8100", "Marcus Bell", ["Tom Okonkwo", "Rita Delgado", "Sean Mulligan", "Ada Park"]),
    ("Technology", "01", "7700", "Anita Rao", ["Jordan Blake", "Mei Chen", "Victor Hale"]),
    ("Food Services", "13", "3700", "Gloria Vance", ["Pam Russo", "Hector Ibanez"]),
    ("Special Education", "01", "1180", "Terrence Holt", ["Naomi Fisher", "Carl Jensen", "Priya Nair"]),
    ("Curriculum & Instruction", "01", "2100", "Yvonne Castillo", ["Ben Adler", "Lucia Moreno", "Grant Howell"]),
]
RESTRICTED_DEPT = "Transportation"
DEPT_VARIANTS = {"Transportation": ["TRANSPORTATION", "Transp.", "transportation"], "Facilities & Maintenance": ["Facilities and Maintenance", "M&O", "FACILITIES & MAINTENANCE"],
                 "Technology": ["Tech", "IT", "technology"], "Food Services": ["Food Service", "Nutrition Services", "FOOD SERVICES"],
                 "Special Education": ["Special Ed", "SPED", "special education"], "Curriculum & Instruction": ["Curriculum and Instruction", "C&I", "CURRICULUM & INSTRUCTION"]}
OBJECTS = [("4100", "Textbooks & Core Materials", (10000, 90000), (200, 6000)), ("4200", "Books & Reference", (2000, 15000), (60, 900)), ("4300", "Materials & Supplies", (20000, 120000), (80, 4800)),
           ("4400", "Non-capital Equipment", (15000, 90000), (400, 4900)), ("5200", "Travel & Conferences", (4000, 20000), (150, 2400)),
           ("5300", "Dues & Memberships", (1500, 8000), (95, 1500)), ("5500", "Operations & Housekeeping", (10000, 60000), (120, 3500)),
           ("5600", "Rentals, Leases & Repairs", (20000, 150000), (300, 12000)), ("5800", "Professional Services", (25000, 180000), (800, 18000)),
           ("5900", "Communications", (5000, 40000), (100, 3000)), ("6400", "Equipment", (40000, 300000), (5000, 38000)),
           ("6500", "Equipment Replacement", (60000, 450000), (3000, 36000)), ("4700", "Food & Food Supplies", (80000, 600000), (500, 9000))]
N_PRIOR_YEAR_ROWS = 12
N_BUDGET_EXACT_DUPES = 4
N_BUDGET_CODE_DUPES = 2
N_VENDORS = 84
N_VENDOR_EXACT_DUPES = 3
N_VENDOR_EIN_DUPES = 3
N_INACTIVE = 6
N_REQUESTS = 130
VENDOR_NAMES = [
    "Acme Bus Parts", "Allied Fleet Supply", "Bluewater Janitorial", "BrightPath Learning", "Cascade Office Products", "Central Valley Tire",
    "Clearview Glass & Glazing", "Coastline Uniforms", "Cornerstone HVAC Services", "Delta Diesel Repair", "Evergreen Landscaping",
    "First Student Transit Parts", "Golden State Food Distributors", "Granite Roofing", "Harbor Electrical Contractors", "Heartland Paper Co",
    "Horizon Educational Publishing", "Ironclad Security Systems", "Jefferson Plumbing", "Keystone Therapy Associates", "Lakeside Printing",
    "Liberty Playground Equipment", "Lumen Classroom Technology", "Meridian Speech Services", "Metro Fire Protection", "Mission Linen Service",
    "Northstar Assessment Group", "Oakridge Lumber", "Pacific Coast Dairy", "Paramount Network Solutions", "Pinnacle Behavioral Health",
    "Precision Auto Glass", "Redwood Science Supply", "Ridgeline Transportation Consulting", "Riverbend Produce", "Sierra Paint Supply",
    "Silverline Audio Visual", "Summit Adaptive Equipment", "Sunrise Bakery Wholesale", "Tri-County Waste Services", "Union Pest Control",
    "Valley Fleet Fuel", "Westfield Elevator", "Wildwood Music Supply", "Zenith Copier Leasing", "Apex Floor Care", "Beacon Medical Supply",
    "Canyon Water Treatment", "Crescent Library Services", "Dayspring Occupational Therapy", "Eagle Signs & Graphics", "Frontier Computer Recycling",
    "Gateway Staffing", "Highland Athletic Supply", "Insight Software Licensing", "Juniper Kitchen Equipment", "Kingsley Moving & Storage",
    "Landmark Surveying", "Madrone Mental Health", "Nimbus Cloud Services", "Orchard Fresh Farms", "Patriot Locksmith", "Quantum Robotics Kits",
    "Rolling Hills Charter Bus", "Stellar Science Kits", "Timberline Furniture", "Upland Irrigation", "Vista Hearing Services", "Wavecrest Telecom",
    "Yosemite Bus Sales", "Anchor Legal Group", "Bridgewater Auditors", "Cobalt Cybersecurity", "Driftwood Art Supply", "Emerald Textbook Depot",
    "Foothill Transmission", "Guardian Background Checks", "Hilltop Mailing Services", "Integrity Translation Services", "Jadeite Lab Equipment",
    "Keel Marine & Outdoor Ed", "Lantern Special Needs Transport", "Monarch Classroom Furniture", "Northgate Uniform Rental", "Olympus Testing Labs",
]
REQ_COLUMNS = ["Request #", "Date", "Requester", "Department", "Vendor", "Account Code", "Description", "Amount", "Status",
               "Dept Approver", "Business Office Approval", "PO Number"]
BUDGET_COLUMNS = ["Fiscal Year", "Account Code", "Department", "Description", "Adopted Budget"]
VENDOR_COLUMNS = ["Vendor", "Tax ID", "Contact Email", "Phone", "Status", "W-9 on File", "City"]
D_STYLES = [0, 1, 2, 3, 4, 6]


def money(c: int) -> float:
    return round(c / 100, 2)


def fmt(c: int, dollar: bool) -> str:
    return f"${c / 100:,.2f}" if dollar else f"{c / 100:.2f}"


def code_variant(code: str, rng: random.Random) -> str:
    return rng.choices([code, code.replace("-", "."), code.replace("-", ""), code.replace("-", " ")], [70, 12, 12, 6])[0]


def build(rng: random.Random, seed: int) -> dict:
    # ------------------------------------------------------------------ budgets (cents)
    lines = []
    for dept, fund, func, approver, _ in DEPTS:
        pool = [o for o in OBJECTS if o[0] != ("4100" if dept == "Food Services" else "4700")]
        chosen = sorted(rng.sample(pool, 12), key=lambda o: o[0])
        for obj, desc, (lo, hi), spend in chosen:
            lines.append({"code": f"{fund}-{func}-{obj}", "dept": dept, "desc": f"{dept} - {desc}",
                          "budget": rng.randint(lo // 500, hi // 500) * 50000, "spend": spend, "obj": obj})
    by_code = {ln["code"]: ln for ln in lines}
    assert len(by_code) == 72
    supplies, dues, replacement = "01-3600-4300", "01-3600-5300", "01-3600-6500"
    for c in (supplies, dues, replacement):
        if c not in by_code:
            obj = c.split("-")[2]
            o = next(o for o in OBJECTS if o[0] == obj)
            victim = next(ln for ln in lines if ln["dept"] == "Transportation" and ln["code"] not in (supplies, dues, replacement))
            victim.update(code=c, desc=f"Transportation - {o[1]}", spend=o[3], obj=obj)
    by_code = {ln["code"]: ln for ln in lines}
    by_code[supplies]["budget"] = 4800000
    by_code[dues]["budget"] = 350000
    by_code[replacement]["budget"] = 42000000

    # ------------------------------------------------------------------ vendors
    names = rng.sample(VENDOR_NAMES, N_VENDORS)
    vendors = []
    eins = rng.sample(range(10000000, 99999999), N_VENDORS)
    for i, n in enumerate(names):
        ein = f"{rng.randint(10, 99)}{eins[i]:07d}"[:9]
        suffix = rng.choice(["", " Inc.", " LLC", ""])
        slug = n.lower().replace("&", "and").replace(" ", "").replace("-", "")
        vendors.append({"name": n + suffix, "ein": ein, "email": rng.choice(["orders", "billing", "sales", "ar"]) + f"@{slug}.com",
                        "phone": f"{rng.choice(['209', '559', '916', '530'])}-555-{rng.randint(1000, 9999)}", "active": True,
                        "w9": rng.random() < 0.9, "city": rng.choice(["Modesto", "Fresno", "Stockton", "Merced", "Turlock", "Visalia"])})
    inactive = rng.sample(range(N_VENDORS), N_INACTIVE)
    for i in inactive:
        vendors[i]["active"] = False
    active_vendors = [v for v in vendors if v["active"]]

    # ------------------------------------------------------------------ requests
    requests = []
    approvers = {d: a for d, _, _, a, _ in DEPTS}
    requesters = {d: r for d, _, _, _, r in DEPTS}
    weights = {"Transportation": 20, "Facilities & Maintenance": 26, "Technology": 22, "Food Services": 16, "Special Education": 14, "Curriculum & Instruction": 18}
    items = {"4200": ["reference books", "binder sets", "manuals"], "4300": ["replacement filters", "classroom supplies", "brake pads", "cleaning supplies", "cable and connectors"],
             "4400": ["label printer", "shop vacuum", "document camera", "tablet cart"], "5200": ["conference registration", "mileage and lodging", "training travel"],
             "5300": ["association dues", "annual membership"], "5500": ["custodial service", "waste hauling"], "5600": ["equipment repair", "copier lease", "lift rental"],
             "5800": ["consulting services", "assessment services", "therapy services"], "5900": ["phone service", "radio licenses"],
             "6400": ["equipment purchase", "capital equipment", "installed equipment"], "6500": ["equipment replacement", "replacement unit", "end-of-life replacement"],
             "4100": ["textbooks", "core curriculum kits", "workbooks"], "4700": ["produce", "dairy", "frozen entrees", "bakery items"]}

    def add(dept, code, amount, status, vendor=None, d=None, desc=None):
        ln = by_code[code]
        r = {"dept": dept, "code": code, "amount": amount, "status": status, "vendor": vendor or rng.choice(active_vendors),
             "date": d or (date(2026, 7, 1) + timedelta(days=rng.randint(0, 70))), "requester": rng.choice(requesters[dept]),
             "desc": desc or rng.choice(items[ln["obj"]])}
        requests.append(r)
        return r

    # pinned: the dues line ends with 1,234.50 left; the supplies line has three approvals and a submitted request
    add("Transportation", dues, 126550, "Approved")
    add("Transportation", dues, 100000, "Approved")
    sup = [add("Transportation", supplies, a, "Approved") for a in (412575, 238940, 91260)]
    sup_submitted = add("Transportation", supplies, 184000, "Submitted")
    neg = add("Facilities & Maintenance", next(ln["code"] for ln in lines if ln["dept"] == "Facilities & Maintenance" and ln["obj"] == "4300"),
              -48000, "Rejected", desc="credit for returned supplies")
    tech_submitted = add("Technology", next(ln["code"] for ln in lines if ln["dept"] == "Technology" and ln["obj"] == "4300"), 164990, "Submitted")
    pinned_codes = {supplies, dues}
    while len(requests) < N_REQUESTS:
        dept = rng.choices(list(weights), list(weights.values()))[0]
        ln = rng.choice([x for x in lines if x["dept"] == dept and x["code"] not in pinned_codes])
        lo, hi = ln["spend"]
        amount = rng.randint(lo * 100, hi * 100)
        amount -= amount % 5
        if amount >= THRESHOLD:
            status = rng.choices(["Approved", "Dept Approved", "Submitted", "Rejected"], [60, 15, 12, 13])[0]
        else:
            status = rng.choices(["Approved", "Submitted", "Rejected"], [70, 18, 12])[0]
        approved_so_far = sum(r["amount"] for r in requests if r["code"] == ln["code"] and r["status"] == "Approved")
        if status == "Approved" and approved_so_far + amount > ln["budget"] * 0.8:
            continue
        add(dept, ln["code"], amount, status)
    requests.sort(key=lambda r: (r["date"], r["dept"], r["amount"]))
    for k, r in enumerate(requests, start=1):
        r["no"] = f"PR-27-{k:04d}"
    approved = [r for r in requests if r["status"] == "Approved"]
    for r in approved:
        r["approved_on"] = min(r["date"] + timedelta(days=rng.randint(1, 6)), TODAY - timedelta(days=1))
    approved.sort(key=lambda r: (r["approved_on"], r["no"]))
    for k, r in enumerate(approved, start=1):
        r["po"] = k
    n_po = len(approved)
    top = max(requests, key=lambda r: r["amount"])
    assert sum(1 for r in requests if r["amount"] == top["amount"]) == 1

    # ------------------------------------------------------------------ written files
    fy27_rows = []
    for ln in lines:
        dept_w = ln["dept"] if rng.random() < 0.7 else rng.choice(DEPT_VARIANTS[ln["dept"]])
        fy27_rows.append(["2026-27", code_variant(ln["code"], rng) if ln["code"] not in pinned_codes else ln["code"], dept_w, ln["desc"],
                          fmt(ln["budget"], rng.random() < 0.35)])
    prior = rng.sample(lines, N_PRIOR_YEAR_ROWS)
    prior_rows = [["2025-26", ln["code"], ln["dept"], ln["desc"], fmt(int(ln["budget"] * rng.uniform(0.85, 1.05)) // 100 * 100, rng.random() < 0.35)] for ln in prior]
    budget_rows = fy27_rows + prior_rows
    exact_src = rng.sample(range(len(fy27_rows)), N_BUDGET_EXACT_DUPES)
    for i in exact_src:
        budget_rows.append(list(fy27_rows[i]))
    code_src = rng.sample([i for i in range(len(fy27_rows)) if i not in exact_src and lines[i]["code"] not in pinned_codes], N_BUDGET_CODE_DUPES)
    code_dupes = []
    for i in code_src:
        row = list(fy27_rows[i])
        code = lines[i]["code"]
        row[1] = next(w for w in (code.replace("-", ""), code.replace("-", "."), code.replace("-", " "), code) if w != fy27_rows[i][1])
        row[4] = fmt(lines[i]["budget"], True)
        budget_rows.append(row)
        code_dupes.append({"code": lines[i]["code"], "written": [fy27_rows[i][1], row[1]]})
    rng.shuffle(budget_rows)

    vendor_rows = []
    for v in vendors:
        vendor_rows.append([v["name"], f"{v['ein'][:2]}-{v['ein'][2:]}", v["email"], v["phone"], "Active" if v["active"] else "Inactive",
                            "Y" if v["w9"] else "N", v["city"]])
    v_exact = rng.sample(range(N_VENDORS), N_VENDOR_EXACT_DUPES)
    for i in v_exact:
        vendor_rows.append(list(vendor_rows[i]))
    v_ein = rng.sample([i for i in range(N_VENDORS) if i not in v_exact and vendors[i]["active"]], N_VENDOR_EIN_DUPES)
    ein_groups = []
    for i in v_ein:
        v = vendors[i]
        alt_name = v["name"][:-1] if v["name"].endswith("Inc.") else (v["name"] + " Inc" if not v["name"].endswith("LLC") else v["name"].replace(" LLC", ", LLC"))
        vendor_rows.append([alt_name, v["ein"], v["email"].upper(), v["phone"].replace("-", "."), "Active", "Y" if v["w9"] else "N", v["city"]])
        ein_groups.append({"vendor": v["name"], "names_as_written": [v["name"], alt_name], "tax_ids_as_written": [f"{v['ein'][:2]}-{v['ein'][2:]}", v["ein"]]})
    rng.shuffle(vendor_rows)

    def po_written(k):
        if k == n_po:
            return f"PO-27-{k:04d}"
        if k == 9:
            return "PO-27-9"
        return rng.choices([f"PO-27-{k:04d}", f"PO27-{k:04d}", f"PO-27-{k}"], [80, 10, 10])[0]

    req_rows = []
    for r in requests:
        dept_w = r["dept"] if rng.random() < 0.75 else rng.choice(DEPT_VARIANTS[r["dept"]])
        big = r["amount"] >= THRESHOLD
        dept_ok = r["status"] in ("Approved", "Dept Approved") or (r["status"] == "Rejected" and rng.random() < 0.5)
        bo = "Approved" if (r["status"] == "Approved" and big) else ("Rejected" if r["status"] == "Rejected" and big and dept_ok else "")
        amt_w = "-480.00" if r is neg else fmt(r["amount"], r["amount"] >= 100000 and rng.random() < 0.5 or r is top)
        req_rows.append([r["no"], date_variant(r["date"], rng.choice(D_STYLES)), r["requester"], dept_w, r["vendor"]["name"],
                         code_variant(r["code"], rng) if r["code"] not in pinned_codes else r["code"], r["desc"], amt_w, r["status"],
                         approvers[r["dept"]] if dept_ok else "", bo, po_written(r["po"]) if r["status"] == "Approved" else ""])

    # ------------------------------------------------------------------ truth
    def approved_on(code=None, dept=None):
        return sum(r["amount"] for r in requests if r["status"] == "Approved" and (code is None or r["code"] == code) and (dept is None or r["dept"] == dept))

    def pending_on(dept=None):
        return sum(r["amount"] for r in requests if r["status"] in ("Submitted", "Dept Approved") and (dept is None or r["dept"] == dept))

    budget_total = sum(ln["budget"] for ln in lines)
    dept_rows = {}
    for d, *_ in DEPTS:
        b = sum(ln["budget"] for ln in lines if ln["dept"] == d)
        a = approved_on(dept=d)
        dept_rows[d] = {"budget": money(b), "approved": money(a), "pending": money(pending_on(d)), "remaining": money(b - a),
                        "percent_used": round(100 * a / b, 1)}
    by_vendor = {}
    for r in requests:
        by_vendor.setdefault(r["vendor"]["name"], []).append(r)
    search_vendor = sorted(n for n, rs in by_vendor.items() if len(rs) == 3 and not any(n.lower() in m["name"].lower() for m in vendors if m["name"] != n))
    search_vendor = search_vendor[0] if search_vendor else sorted(n for n, rs in by_vendor.items() if len(rs) == 2)[0]
    by_text_amount = sorted(req_rows, key=lambda row: row[7], reverse=True)
    trans = [r for r in requests if r["dept"] == RESTRICTED_DEPT]
    awaiting = [r for r in requests if r["status"] in ("Submitted", "Dept Approved")]
    dues_remaining = by_code[dues]["budget"] - approved_on(dues)
    sup_remaining = by_code[supplies]["budget"] - approved_on(supplies)
    inactive_names = sorted(vendors[i]["name"] for i in inactive)
    test_vendor = sorted((v for v in active_vendors if v["name"] not in by_vendor and v["name"] not in [g["vendor"] for g in ein_groups]), key=lambda v: v["name"])
    test_vendor = test_vendor[0] if test_vendor else sorted(active_vendors, key=lambda v: v["name"])[0]
    tech_line = tech_submitted["code"]

    counts = {
        "seed": seed,
        "district": {"departments": [d for d, *_ in DEPTS], "approvers": approvers, "restricted_login": approvers[RESTRICTED_DEPT],
                     "restricted_department": RESTRICTED_DEPT, "fiscal_year": "2026-27",
                     "roles": {"admin": "Admin (business office)", "staff": "Department Approver", "viewer": "Auditor (read-only)", "extra": "Requester"},
                     "approval_rule": "under 2,500.00: department approver only; 2,500.00 or more: department approver, then business office",
                     "po_rule": "PO numbers PO-27-#### are issued in sequence only on final approval", "today": TODAY.isoformat()},
        "tester_records": {"department": RESTRICTED_DEPT, "account_code": supplies, "vendor": test_vendor["name"], "amount": 100.00,
                           "description": "Checklist test", "status": "Submitted",
                           "note": "requests the tester creates without named details use these and are deleted when the item is done"},
        "budgets": {
            "file_rows_excluding_header": len(budget_rows),
            "prior_year_rows": N_PRIOR_YEAR_ROWS,
            "exact_duplicate_rows": N_BUDGET_EXACT_DUPES,
            "code_format_duplicate_rows": N_BUDGET_CODE_DUPES,
            "fy2026_27_lines": len(lines),
            "code_rule": "an account code is fund-function-object; 01.3600.4300, 0136004300, and '01 3600 4300' all mean 01-3600-4300",
            "wrong_counts": {"all_rows": len(budget_rows), "fy27_rows_without_dedupe": len(budget_rows) - N_PRIOR_YEAR_ROWS,
                             "exact_dedupe_only": len(budget_rows) - N_PRIOR_YEAR_ROWS - N_BUDGET_EXACT_DUPES,
                             "prior_year_included_after_dedupe": len(lines) + N_PRIOR_YEAR_ROWS},
            "code_format_duplicates": code_dupes,
            "per_department_lines": {d: sum(1 for ln in lines if ln["dept"] == d) for d, *_ in DEPTS},
            "budget_total": money(budget_total),
            "budget_total_if_prior_year_included": money(budget_total + sum(int(float(r[4].replace("$", "").replace(",", "")) * 100) for r in prior_rows)),
            "supplies_line": {"code": supplies, "description": by_code[supplies]["desc"], "budget": money(by_code[supplies]["budget"]),
                              "approved_requests": [{"request": r["no"], "amount": money(r["amount"])} for r in sorted(sup, key=lambda r: r["no"])],
                              "approved_total": money(approved_on(supplies)), "remaining": money(sup_remaining),
                              "submitted_request_not_counted": {"request": sup_submitted["no"], "amount": money(sup_submitted["amount"]),
                                                                "wrong_remaining_if_deducted": money(sup_remaining - sup_submitted["amount"])}},
            "dues_line": {"code": dues, "budget": money(by_code[dues]["budget"]), "approved_total": money(approved_on(dues)), "remaining": money(dues_remaining)},
            "replacement_line": {"code": replacement, "budget": money(by_code[replacement]["budget"]), "approved_total": money(approved_on(replacement)),
                                 "remaining": money(by_code[replacement]["budget"] - approved_on(replacement))},
        },
        "vendors": {
            "file_rows_excluding_header": len(vendor_rows),
            "exact_duplicate_rows": N_VENDOR_EXACT_DUPES,
            "tax_id_format_duplicate_rows": N_VENDOR_EIN_DUPES,
            "unique_vendors": N_VENDORS,
            "dedupe_rule": "one vendor per Tax ID with the hyphen removed",
            "wrong_counts": {"no_dedupe": len(vendor_rows), "exact_rows_only": len(vendor_rows) - N_VENDOR_EXACT_DUPES},
            "tax_id_groups": ein_groups,
            "inactive": N_INACTIVE, "inactive_vendors": inactive_names, "active": N_VENDORS - N_INACTIVE,
        },
        "requests": {
            "file_rows_excluding_header": len(req_rows),
            "requests": len(requests),
            "per_status": {s: sum(1 for r in requests if r["status"] == s) for s in ("Submitted", "Dept Approved", "Approved", "Rejected")},
            "awaiting_approval": len(awaiting),
            "approved_total": money(approved_on()),
            "pos_issued": n_po,
            "highest_po": f"PO-27-{n_po:04d}", "next_po": f"PO-27-{n_po + 1:04d}", "next_po_after": f"PO-27-{n_po + 2:04d}",
            "po_written_unpadded_example": "PO-27-9", "po_text_sort_would_pick": sorted((row[11] for row in req_rows if row[11]), reverse=True)[0],
            "negative_amount": {"request": neg["no"], "department": neg["dept"], "status": "Rejected", "file_value": "-480.00"},
            "largest_request": {"request": top["no"], "department": top["dept"], "amount": money(top["amount"]), "file_value": fmt(top["amount"], True),
                                "text_sort_would_put_first": by_text_amount[0][0]},
            "restricted": {"requests": len(trans), "awaiting_approval": sum(1 for r in trans if r["status"] in ("Submitted", "Dept Approved"))},
            "search_check": {"term": search_vendor, "expected_results": len(by_vendor[search_vendor])},
            "filter_check": {"field": "Status", "value": "Submitted", "expected_results": sum(1 for r in requests if r["status"] == "Submitted")},
            "sort_check": {"field": "Amount", "direction": "descending", "first": top["no"]},
            "export_check": {"rows": len(requests), "columns": ["Request #", "Department", "Vendor", "Amount", "Status", "PO Number"]},
            "out_of_scope_request": {"request": tech_submitted["no"], "department": "Technology", "amount": money(tech_submitted["amount"]), "status": "Submitted"},
        },
        "dashboard": {"awaiting_approval": len(awaiting), "budget_remaining": money(budget_total - approved_on()),
                      "approved_this_year": money(approved_on()), "pos_issued": n_po,
                      "restricted_awaiting_approval": sum(1 for r in trans if r["status"] in ("Submitted", "Dept Approved"))},
        "checks": {
            "one_step": {"amount": 2499.99, "code": supplies, "remaining_after": money(sup_remaining - 249999), "po": f"PO-27-{n_po + 1:04d}"},
            "two_step": {"amount": 2500.00, "code": supplies, "remaining_after_department_step": money(sup_remaining - 249999),
                         "remaining_after_business_office": money(sup_remaining - 249999 - 250000), "po": f"PO-27-{n_po + 2:04d}"},
            "wrong_line": {"department": RESTRICTED_DEPT, "other_department_code": tech_line},
            "reject": {"request": sup_submitted["no"], "amount": money(sup_submitted["amount"])},
            "other_department": {"request": tech_submitted["no"]},
        },
        "changes": {
            "1_budget_report": {"per_department": dept_rows,
                                "district": {"budget": money(budget_total), "approved": money(approved_on()), "pending": money(pending_on()),
                                             "remaining": money(budget_total - approved_on()), "percent_used": round(100 * approved_on() / budget_total, 1)}},
            "2_no_overspend": {"line": dues, "remaining": money(dues_remaining), "over": money(dues_remaining + 1), "exact": money(dues_remaining),
                               "remaining_after_exact": 0.00, "two_step_over": 2600.00},
            "3_superintendent": {"threshold": 25000.00, "line": replacement, "at_threshold": 25000.00, "below": 24999.99,
                                 "remaining_before": money(by_code[replacement]["budget"] - approved_on(replacement)),
                                 "remaining_after_25000": money(by_code[replacement]["budget"] - approved_on(replacement) - 2500000),
                                 "remaining_after_both": money(by_code[replacement]["budget"] - approved_on(replacement) - 2500000 - 2499999)},
        },
    }
    return {"budget_rows": budget_rows, "vendor_rows": vendor_rows, "req_rows": req_rows, "counts": counts}


def main() -> None:
    seed = argparse_seed(0)
    rng = random.Random(seed)
    os.makedirs(SEED_DIR, exist_ok=True)
    os.makedirs(REF_DIR, exist_ok=True)
    out = build(rng, seed)
    write_csv(os.path.join(SEED_DIR, "budgets.csv"), BUDGET_COLUMNS, out["budget_rows"])
    write_csv(os.path.join(SEED_DIR, "vendors.csv"), VENDOR_COLUMNS, out["vendor_rows"])
    write_csv(os.path.join(SEED_DIR, "requests.csv"), REQ_COLUMNS, out["req_rows"], bom=True, crlf=True)
    with open(os.path.join(REF_DIR, "counts.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out["counts"], indent=2) + "\n")
    b, v, r = out["counts"]["budgets"], out["counts"]["vendors"], out["counts"]["requests"]
    print(f"budgets.csv: {b['file_rows_excluding_header']} rows -> {b['fy2026_27_lines']} lines; total {b['budget_total']:.2f}")
    print(f"vendors.csv: {v['file_rows_excluding_header']} rows -> {v['unique_vendors']} vendors")
    print(f"requests.csv: {r['requests']} requests {r['per_status']}; approved {r['approved_total']:.2f}; restricted {r['restricted']}")


if __name__ == "__main__":
    main()
