#!/usr/bin/env python3
"""insurance-certificates: vendor certificates of insurance to a policy log with expired policies flagged.

    python gen.py [--seed N]

Business: a property management company requires every contractor to keep liability, auto and workers'
compensation coverage on file. The compliance coordinator wants one row per policy with the carrier, limits and
dates, and which policies have lapsed as of the review date.

Traps (each caught by a check, see task.yaml):
  * every certificate carries two to four policies; one row per policy                (checks: one row per policy; row count)
  * carriers are named once in an INSURER A/B/C list and each policy row carries only the letter (check: insureds and carriers)
  * three policies expired before the 15 September review date, one of them the day before; one expiring
    30 September is still active                                                      (check: status)
  * limits carry $ and commas, one certificate writes GL limits as "1,000,000 / 2,000,000", and a products-completed
    operations aggregate differs from the general aggregate                           (check: limits)
  * last year's Hollowell certificate is still in the folder; the newer one replaces it  (checks: one row per policy; row count)
  * the Cedar and Pine certificate is an image-only scan                               (checks: one row per policy; status)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HOLDER = "Redwood Property Management LLC"
HOLDER_ADDR = "600 Market St, Suite 210, Tacoma, WA 98402"
ASOF = date(2026, 9, 15)
MM = 2.8346
CARRIERS = ["Granite State Casualty Company", "Bluewater Mutual Insurance Company", "Old Harbor Indemnity Co.", "Tri-State Specialty Insurance Company",
            "Keel Point Assurance Company", "Northern Pines Casualty Co.", "Lantern Rock Insurance Company", "Stillwater General Insurance Co."]
AGENCIES = ["Summit Ridge Insurance Agency", "Cascade Risk Partners", "Baylor and Finch Insurance Services", "Copperline Insurance Brokers"]
LABEL = {"general_liability": "COMMERCIAL GENERAL LIABILITY", "auto_liability": "AUTOMOBILE LIABILITY (ANY AUTO)", "umbrella": "UMBRELLA LIAB - OCCUR",
         "workers_comp": "WORKERS COMPENSATION AND EMPLOYERS' LIABILITY"}


def usd(x): return f"${x:,.0f}"
def mdy(d): return d.strftime("%m/%d/%Y")
def yr(d, n=1): return date(d.year + n, d.month, d.day)


def build(seed: int) -> dict:
    r = rng(seed)
    carriers = r.sample(CARRIERS, 8)
    ci = iter(carriers)
    used = set()

    def pno(fmt):
        while True:
            v = fmt.format(a=r.randint(1000000, 9999999), b=r.randint(10, 99), c=r.randint(100000, 999999), d=r.randint(1000, 9999))
            if v not in used:
                used.add(v); return v

    def pol(cov, carrier, eff, occ, agg, fmt):
        return dict(cov=cov, carrier=carrier, eff=eff, exp=yr(eff), occ=occ, agg=agg, no=pno(fmt))

    certs = {}
    # Hollowell Electric: new certificate (A/B letters) plus last year's certificate (superseded)
    A, B = next(ci), next(ci)
    e_new = date(2026, 8, 31)
    certs["hollowell"] = dict(insured="Hollowell Electric LLC", agency=AGENCIES[0], issued=date(2026, 9, 2), letters={"A": A, "B": B}, policies=[
        dict(pol("general_liability", A, e_new, 1000000, 2000000, "GLP {a}-{b}"), ltr="A", prod_agg=2000000),
        dict(pol("auto_liability", B, e_new, 1000000, 0, "BAP-{a}"), ltr="B"),
        dict(pol("workers_comp", B, e_new, 500000, 0, "WC {b}-{c}-26"), ltr="B")])
    certs["hollowell_old"] = dict(insured="Hollowell Electric LLC", agency=AGENCIES[0], issued=date(2025, 9, 4), letters={"A": A, "B": B}, policies=[
        dict(pol("general_liability", A, date(2025, 8, 31), 1000000, 2000000, "GLP {a}-{b}"), ltr="A", prod_agg=2000000),
        dict(pol("auto_liability", B, date(2025, 8, 31), 1000000, 0, "BAP-{a}"), ltr="B"),
        dict(pol("workers_comp", B, date(2025, 8, 31), 500000, 0, "WC {b}-{c}-25"), ltr="B")])
    # Pemberton HVAC: GL active, umbrella expired in August (A, B, C letters, umbrella on C)
    A, B, C = next(ci), next(ci), next(ci)
    certs["pemberton"] = dict(insured="Pemberton HVAC Services, Inc.", agency=AGENCIES[1], issued=date(2026, 3, 12), letters={"A": A, "B": B, "C": C}, policies=[
        dict(pol("general_liability", A, date(2026, 3, 1), 2000000, 4000000, "CGL{c}{b}"), ltr="A", prod_agg=2000000),
        dict(pol("auto_liability", B, date(2026, 3, 1), 1000000, 0, "CA {d}-{c}"), ltr="B"),
        dict(pol("umbrella", C, date(2025, 8, 1), 5000000, 5000000, "UMB{a}"), ltr="C")])
    # Westbrook Plumbing: auto expired the day before review; WC expires 30 September (active)
    A = next(ci)
    certs["westbrook"] = dict(insured="Westbrook Plumbing Inc", agency=AGENCIES[2], issued=date(2025, 11, 3), letters={"A": A}, policies=[
        dict(pol("general_liability", A, date(2025, 11, 1), 1000000, 2000000, "PK{c}"), ltr="A", prod_agg=2000000),
        dict(pol("auto_liability", A, date(2025, 9, 14), 1000000, 0, "AU{c}"), ltr="A"),
        dict(pol("workers_comp", A, date(2025, 9, 30), 1000000, 0, "WCP{c}"), ltr="A")])
    # Cedar and Pine (scan): GL active, auto expired in July
    A, B = next(ci), next(ci)
    certs["cedar"] = dict(insured="Cedar and Pine Landscaping LLC", agency=AGENCIES[3], issued=date(2026, 6, 10), letters={"A": A, "B": B}, policies=[
        dict(pol("general_liability", A, date(2026, 6, 1), 1000000, 2000000, "CPL-{c}"), ltr="A"),
        dict(pol("auto_liability", B, date(2025, 7, 31), 1000000, 0, "BA {d}-00{b}"), ltr="B")])
    # Pinnacle Roofing: broker's evidence-of-insurance letter, no letters; GL as "1,000,000 / 2,000,000"
    G, U = certs["pemberton"]["letters"]["A"], certs["hollowell"]["letters"]["B"]
    W = certs["cedar"]["letters"]["A"]
    certs["pinnacle"] = dict(insured="Pinnacle Roofing Co.", agency=AGENCIES[1], issued=date(2026, 9, 3), policies=[
        pol("general_liability", G, date(2026, 9, 1), 1000000, 2000000, "TSG-{c}"),
        pol("umbrella", U, date(2026, 9, 1), 2000000, 2000000, "XS {a}"),
        pol("workers_comp", W, date(2026, 5, 15), 1000000, 0, "WC-{d}-{c}")])
    # products-completed ops aggregate differs from the general aggregate on Hollowell's new GL
    certs["hollowell"]["policies"][0]["prod_agg"] = 1000000
    return dict(certs=certs, coord=person(r))


def limits_cell(p):
    if p["cov"] == "general_liability":
        return (f"EACH OCCURRENCE {usd(p['occ'])}<br/>DAMAGE TO RENTED PREMISES $300,000<br/>MED EXP (any one person) $10,000<br/>"
                f"PERSONAL &amp; ADV INJURY {usd(p['occ'])}<br/>GENERAL AGGREGATE {usd(p['agg'])}<br/>PRODUCTS - COMP/OP AGG {usd(p['prod_agg'])}")
    if p["cov"] == "auto_liability":
        return f"COMBINED SINGLE LIMIT (Ea accident) {usd(p['occ'])}<br/>BODILY INJURY (Per person)<br/>PROPERTY DAMAGE (Per accident)"
    if p["cov"] == "umbrella":
        return f"EACH OCCURRENCE {usd(p['occ'])}<br/>AGGREGATE {usd(p['agg'])}"
    return f"PER STATUTE<br/>E.L. EACH ACCIDENT {usd(p['occ'])}<br/>E.L. DISEASE - EA EMPLOYEE {usd(p['occ'])}<br/>E.L. DISEASE - POLICY LIMIT {usd(p['occ'])}"


def emit(seed: int) -> None:
    d = build(seed); C = d["certs"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "certificates"); os.makedirs(F, exist_ok=True)

    def form(fn, cert, font, pagesize, grid, holder_first=False):
        letters = [(f"INSURER {k}", v) for k, v in sorted(cert["letters"].items())]
        head = [("title", "CERTIFICATE OF LIABILITY INSURANCE"),
                ("small", "This certificate is issued as a matter of information only and confers no rights upon the certificate holder. "
                          "It does not amend, extend or alter the coverage afforded by the policies below."),
                ("kv", [("DATE (MM/DD/YYYY)", mdy(cert["issued"])), ("PRODUCER", cert["agency"]), ("INSURED", cert["insured"])] + letters,
                 {"col_widths": [42 * MM, 128 * MM]})]
        holder = [("h", "CERTIFICATE HOLDER"), ("p", f"{HOLDER}<br/>{HOLDER_ADDR}")]
        table = [["INSR LTR", "TYPE OF INSURANCE", "POLICY NUMBER", "POLICY EFF", "POLICY EXP", "LIMITS"]]
        for p in cert["policies"]:
            table.append([p["ltr"], LABEL[p["cov"]], p["no"], mdy(p["eff"]), mdy(p["exp"]), limits_cell(p)])
        body = [("spacer", 6), ("table", table, {"col_widths": [11 * MM, 35 * MM, 31 * MM, 24 * MM, 24 * MM, 53 * MM], "grid": grid, "shade_header": grid}),
                ("spacer", 6), ("small", "DESCRIPTION OF OPERATIONS: Certificate holder is included as additional insured on the general liability policy where required by written contract."),
                ("spacer", 8), ("p", "AUTHORIZED REPRESENTATIVE: /s/ " + cert["agency"])]
        blocks = (holder + head + body) if holder_first else (head + holder + body)
        write_pdf_document(os.path.join(F, fn), blocks, pagesize=pagesize, font=font, base_size=8)

    form("COI_Hollowell_Electric_2026.pdf", C["hollowell"], "Helvetica", "letter", True)
    form("Hollowell COI 2025-09.pdf", C["hollowell_old"], "Helvetica", "letter", True)
    form("pemberton_hvac_certificate.pdf", C["pemberton"], "Times-Roman", "a4", False, holder_first=True)
    form("Westbrook-COI.pdf", C["westbrook"], "Courier", "letter", True)

    # ---- Cedar and Pine: image-only scan
    ce = C["cedar"]
    lines = ["CERTIFICATE OF LIABILITY INSURANCE", f"DATE ISSUED {mdy(ce['issued'])}", f"PRODUCER: {ce['agency']}", f"INSURED: {ce['insured']}"]
    for k, v in sorted(ce["letters"].items()):
        lines.append(f"INSURER {k}: {v}")
    lines += [f"HOLDER: {HOLDER}", ""]
    for p in ce["policies"]:
        if p["cov"] == "general_liability":
            lines += [f"LTR {p['ltr']} GENERAL LIABILITY", f"  POLICY {p['no']}", f"  EFF {mdy(p['eff'])} EXP {mdy(p['exp'])}",
                      f"  EACH OCCURRENCE {p['occ']:,}", f"  GENERAL AGGREGATE {p['agg']:,}", ""]
        else:
            lines += [f"LTR {p['ltr']} AUTOMOBILE LIABILITY", f"  POLICY {p['no']}", f"  EFF {mdy(p['eff'])} EXP {mdy(p['exp'])}",
                      f"  COMBINED SINGLE LIMIT {p['occ']:,}", ""]
    lines += ["AUTHORIZED REPRESENTATIVE", f"/s/ {ce['agency']}"]
    write_scan_pdf(os.path.join(F, "scan_cedar_pine_coi.pdf"), lines, font_size=32, seed=seed * 29 + 4, skew_deg=-0.3, noise=240)

    # ---- Pinnacle: broker's evidence of insurance letter
    pn = C["pinnacle"]
    gl, um, wc = pn["policies"]
    write_pdf_document(os.path.join(F, "Pinnacle_Roofing_evidence_of_insurance.pdf"), [
        ("title", pn["agency"]), ("small", "Commercial lines  |  certificates@cascaderisk.example"), ("hr", None),
        ("right", pn["issued"].strftime("%B %-d, %Y")),
        ("p", f"To: {HOLDER}"), ("p", f"Re: Evidence of insurance for {pn['insured']}"), ("spacer", 6),
        ("p", "At the request of our client, we confirm that the following policies are in force as of the date of this letter:"), ("spacer", 4),
        ("p", f"<b>Commercial General Liability</b> - {gl['carrier']}, policy no. {gl['no']}, effective {gl['eff']:%B %-d, %Y} to {gl['exp']:%B %-d, %Y}. "
              f"Limits {gl['occ']:,} / {gl['agg']:,} (each occurrence / general aggregate)."),
        ("p", f"<b>Umbrella Liability</b> - {um['carrier']}, policy no. {um['no']}, effective {um['eff']:%B %-d, %Y} to {um['exp']:%B %-d, %Y}. "
              f"Limits {usd(um['occ'])} each occurrence and {usd(um['agg'])} aggregate, following form over the general liability policy."),
        ("p", f"<b>Workers' Compensation and Employers' Liability</b> - {wc['carrier']}, policy no. {wc['no']}, effective {wc['eff']:%B %-d, %Y} to "
              f"{wc['exp']:%B %-d, %Y}. Statutory benefits; employers' liability {usd(wc['occ'])} each accident."),
        ("spacer", 6), ("p", "Pinnacle Roofing Co. does not own vehicles; hired and non-owned auto coverage is included under the general liability policy."),
        ("spacer", 10), ("p", "Sincerely,<br/><br/>Account Manager, Commercial Lines"),
    ], font="Times-Roman", base_size=10.5)

    co = d["coord"]
    write_text(os.path.join(ws, "compliance_note.txt"),
        "Vendor insurance review - 15 September 2026\n\n"
        "The certificates vendors sent us are in the certificates folder. For the compliance log I need coi.csv with one row per insurance policy:\n\n"
        "  policy_number    as printed\n"
        "  insured          the vendor named as the insured\n"
        "  carrier          the insurance company that wrote the policy (not the agency)\n"
        "  coverage         general_liability, auto_liability, umbrella or workers_comp\n"
        "  each_occurrence  general liability and umbrella: each occurrence limit; auto: combined single limit; workers comp: employers' liability each accident\n"
        "  aggregate        general liability: general aggregate; umbrella: aggregate; 0 for auto and workers comp\n"
        "  effective_date   YYYY-MM-DD\n"
        "  expiry_date      YYYY-MM-DD\n"
        "  status           expired if the policy's expiry date is before 15 September 2026, otherwise active\n\n"
        "Limits as plain numbers. If a vendor sent more than one certificate, only log the most recent one.\n\n"
        f"{co[0]} {co[1]}, Compliance\n")

    header = ["policy_number", "insured", "carrier", "coverage", "each_occurrence", "aggregate", "effective_date", "expiry_date", "status"]
    rows = []
    for key in ("hollowell", "pemberton", "westbrook", "cedar", "pinnacle"):
        c = C[key]
        for p in c["policies"]:
            rows.append([p["no"], c["insured"], p["carrier"], p["cov"], p["occ"], p["agg"], p["eff"].isoformat(), p["exp"].isoformat(),
                         "expired" if p["exp"] < ASOF else "active"])
    write_csv(os.path.join(ref, "coi.csv"), header, rows)
    write_csv(os.path.join(sol, "coi.csv"), header, rows)
    expired = [r_[0] for r_ in rows if r_[8] == "expired"]
    pnos = {k: [p["no"] for p in C[k]["policies"]] for k in C}
    write_json(os.path.join(ref, "notes.json"), {"expired": expired, "old_certificate_policies": pnos["hollowell_old"], "day_before": pnos["westbrook"][1],
                                                 "active_late_sept": pnos["westbrook"][2], "slash_limits": pnos["pinnacle"][0],
                                                 "prod_agg_differs": pnos["hollowell"][0], "prod_agg_value": 1000000,
                                                 "letter_B_policies": [pnos["hollowell"][1], pnos["hollowell"][2], pnos["pemberton"][1], pnos["cedar"][1]],
                                                 "first_insurer": {pnos["hollowell"][1]: C["hollowell"]["letters"]["A"], pnos["pemberton"][2]: C["pemberton"]["letters"]["A"]}})
    for_old = pnos["hollowell_old"]
    write_task_yaml(HERE, {
        "id": "insurance-certificates", "track": "desk", "category": "extraction",
        "title": "Log vendor insurance certificates and flag lapsed policies",
        "ask": "Can you log the vendor insurance certificates into coi.csv for our compliance review? They're in the certificates folder; the compliance note says what goes in it.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "each certificate lists two to four policies in one table, with the limits for each stacked in a single cell; one row per policy (checks: one row per policy; row count)",
            "carriers appear once in the INSURER A/B/C list and each policy row carries only the letter; the producer is an agency, not a carrier, and the Pemberton umbrella sits on insurer C (check: insureds and carriers)",
            "the Pemberton umbrella expired in August and the Cedar and Pine auto in July, and the Westbrook auto expired 14 September, the day before the review; the Westbrook workers comp policy expiring 30 September is still active (check: status)",
            "limits carry $ and commas, the broker's letter writes the GL limits as '1,000,000 / 2,000,000', and Hollowell's products-completed operations aggregate ($1,000,000) is printed under a $2,000,000 general aggregate (check: limits)",
            "last year's Hollowell certificate is still in the folder with three expired policies; the September 2026 certificate replaces it, so none of its policies are logged (checks: one row per policy; row count)",
            "the Cedar and Pine certificate is an image-only scan (checks: one row per policy; status)",
            "the broker's evidence-of-insurance letter for Pinnacle has no form, no insurer letters and long-form dates ('September 1, 2026') (checks: policy dates; insureds and carriers)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "coi.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per policy", "path": "coi.csv", "column": "policy_number", "ref": "coi.csv", "normalize": ["alnum"]},
            {"type": "csv_row_count", "name": "row count", "path": "coi.csv", "equals_ref": "coi.csv"},
            {"type": "csv_values_match", "name": "insureds and carriers", "path": "coi.csv", "ref": "coi.csv", "key": "policy_number",
             "columns": ["insured", "carrier"], "normalize": ["alnum"], "min_accuracy": 1.0,
             "must_match_keys": [pnos["hollowell"][1], pnos["pemberton"][2], pnos["cedar"][1], pnos["pinnacle"][1]]},
            {"type": "csv_values_match", "name": "coverage types", "path": "coi.csv", "ref": "coi.csv", "key": "policy_number", "columns": ["coverage"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "limits", "path": "coi.csv", "ref": "coi.csv", "key": "policy_number",
             "columns": ["each_occurrence", "aggregate"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [pnos["pinnacle"][0], pnos["hollowell"][0], pnos["hollowell"][1], pnos["cedar"][0]]},
            {"type": "csv_values_match", "name": "policy dates", "path": "coi.csv", "ref": "coi.csv", "key": "policy_number",
             "columns": ["effective_date", "expiry_date"], "min_accuracy": 1.0, "must_match_keys": pnos["pinnacle"] + [pnos["cedar"][1]]},
            {"type": "csv_values_match", "name": "status", "path": "coi.csv", "ref": "coi.csv", "key": "policy_number",
             "columns": ["status"], "min_accuracy": 1.0, "must_match_keys": expired + [pnos["westbrook"][2]]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
