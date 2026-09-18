#!/usr/bin/env python3
"""grant-award-letters: eight funder letters (award letters, one amendment, one declination) to grants.csv.

    python gen.py [--seed N]

A community kitchen nonprofit received a season of funder correspondence. The development coordinator
wants one row per grant for the tracker. Traps (each caught by a check, see task.yaml):
  * two grants are multi-year and state the award by year; total is the sum, the year columns are split
    (check: award amounts)
  * three letters give the reporting schedule as a rule in prose ("six months after the grant period
    begins", "within 60 days after the period ends") and the dates must be computed  (check: report due dates)
  * one letter names the amount requested before the smaller amount awarded         (check: award amounts)
  * one amendment letter raises a grant and extends its period; its final report moves to 60 days after
    the new end date, which lands on 29 February 2028; the amendment is not a separate row
    (checks: one row per awarded grant; award amounts; grant period; report due dates)
  * one letter is a declination and must not appear                                  (check: declined request absent)
  * one award letter is an image-only scan                                           (check: one row per awarded grant)
  * dates appear in five formats across the letters; the tracker wants ISO            (check: grant period)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

# write_pdf_document builds "<font>-Bold"; reportlab has Times-Roman/Times-Bold, so alias "Times" -> Times-Roman.
from reportlab.pdfbase import pdfmetrics  # noqa: E402
try:
    pdfmetrics.registerFont(pdfmetrics.Font("Times", "Times-Roman", "WinAnsiEncoding"))
except Exception:
    pass

GRANTEE = "Cedar Hollow Community Kitchen"
GRANTEE_ADDR = "418 Mill Rd, Eugene, OR 97401"
COORD = "Dana Okafor"

def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, d.day)

def long(d: date) -> str: return d.strftime("%B %-d, %Y")
def iso(d: date) -> str: return d.isoformat()
def usd0(x: float) -> str: return f"${x:,.0f}"
WORDS = {15000: "Fifteen Thousand Dollars", 20000: "Twenty Thousand Dollars", 25000: "Twenty-Five Thousand Dollars",
         30000: "Thirty Thousand Dollars", 60000: "Sixty Thousand Dollars", 70000: "Seventy Thousand Dollars",
         80000: "Eighty Thousand Dollars", 90000: "Ninety Thousand Dollars", 100000: "One Hundred Thousand Dollars",
         110000: "One Hundred Ten Thousand Dollars", 120000: "One Hundred Twenty Thousand Dollars"}

def build(seed: int) -> dict:
    r = rng(seed)
    ed_f, ed_l = person(r)
    ed = f"{ed_f} {ed_l}"
    officers = people(r, 8)
    starts = [date(2026, m, 1) for m in (7, 8, 9, 10, 11, 12)]
    g = {}
    # G1 Alder Family Foundation: one year, everything explicit
    s = r.choice(starts); e = add_months(s, 12) - timedelta(days=1); amt = r.choice([20000, 25000, 30000])
    g["alder"] = dict(ref=f"AFF-{s.year}-{r.randint(100, 399)}", funder="Alder Family Foundation", total=amt, y1=amt, y2=0,
                      start=s, end=e, interim=add_months(s, 6) + timedelta(days=14), final=e + timedelta(days=45), officer=officers[0])
    # G2 Harbor Trust Community Fund: two years, amounts by year in prose, reporting rule in prose
    s = r.choice(starts); e = add_months(s, 24) - timedelta(days=1); y1 = r.choice([60000, 70000, 80000]); y2 = y1 - r.choice([10000, 20000])
    g["harbor"] = dict(ref=f"HTCF-{r.randint(2600, 2999)}", funder="Harbor Trust Community Fund", total=y1 + y2, y1=y1, y2=y2,
                       start=s, end=e, interim=add_months(s, 6), final=e + timedelta(days=60), officer=officers[1])
    # G3 Meridian Health Foundation: requested more than awarded; final report 90 days after close
    s = r.choice(starts); e = add_months(s, 12) - timedelta(days=1); req = r.choice([90000, 100000, 110000]); amt = req - r.choice([20000, 25000, 30000])
    g["meridian"] = dict(ref=f"MHF-G{r.randint(10000, 19999)}", funder="Meridian Health Foundation", total=amt, y1=amt, y2=0, requested=req,
                         start=s, end=e, interim=add_months(s, 6) - timedelta(days=1), final=e + timedelta(days=90), officer=officers[2])
    # G4 Northgate Savings Charitable Trust: image-only scan, one year, explicit
    s = r.choice(starts); e = add_months(s, 12) - timedelta(days=1); amt = r.choice([15000, 20000])
    g["northgate"] = dict(ref=f"NSCT-{s.year % 100}-{r.randint(200, 899):03d}", funder="Northgate Savings Charitable Trust", total=amt, y1=amt, y2=0,
                          start=s, end=e, interim=add_months(s, 5) + timedelta(days=14), final=e + timedelta(days=30), officer=officers[3])
    # G5 Sycamore Fund: two equal years in a table, total in words; final 45 days after end
    s = r.choice(starts); e = add_months(s, 24) - timedelta(days=1); y = r.choice([40000, 45000, 50000])
    g["sycamore"] = dict(ref=f"SF/{s.year}/{r.randint(40, 99)}", funder="Sycamore Fund", total=2 * y, y1=y, y2=y,
                         start=s, end=e, interim=add_months(s, 11), final=e + timedelta(days=45), officer=officers[4])
    # G6 Willow Creek Foundation: original letter then an amendment (more money, longer period, final report moves)
    s = date(2026, 7, 1); e = date(2027, 6, 30); amt = r.choice([55000, 60000, 65000]); bump = r.choice([10000, 12500, 15000])
    new_end = date(2027, 12, 31)
    g["willow"] = dict(ref=f"WCF-{r.randint(2026001, 2026999)}", funder="Willow Creek Foundation", total=amt + bump, y1=amt + bump, y2=0,
                       start=s, end=new_end, interim=date(2027, 1, 15), final=new_end + timedelta(days=60), officer=officers[5],
                       orig_total=amt, orig_end=e, orig_final=date(2027, 8, 31), bump=bump)
    declined = dict(ref=f"GPF-{r.randint(1000, 4999)}", funder="Granite Peak Foundation", requested=r.choice([35000, 40000, 50000]), officer=officers[6])
    return dict(g=g, declined=declined, ed=ed, coord=COORD)

def letter_common(fund: dict, dt: date, ed: str, opening: str):
    return [("small", f"{GRANTEE}\nAttn: {ed}, Executive Director\n{GRANTEE_ADDR}"), ("spacer", 6), ("p", f"Dear {ed.split()[0]},"), ("spacer", 4), ("p", opening)]

def emit(seed: int) -> None:
    d = build(seed); g = d["g"]; ed = d["ed"]
    ws, ref, sol = task_dirs(HERE)
    L = os.path.join(ws, "funder_letters"); os.makedirs(L, exist_ok=True)  # write_pdf_document does not create parents

    # --- G1 Alder: Helvetica letter, details in a kv box after the prose
    a = g["alder"]; off = f"{a['officer'][0]} {a['officer'][1]}"
    write_pdf_document(os.path.join(L, "Alder_Family_Foundation_award.pdf"), [
        ("title", "Alder Family Foundation"), ("small", "2200 Prospect Ave, Suite 410, Portland, OR 97209  |  grants@alderff.org"), ("hr", None),
        ("right", long(a["start"] - timedelta(days=40))),
        *letter_common(a, a["start"], ed, f"On behalf of the trustees, I am pleased to inform you that {GRANTEE} has been awarded a grant of "
                                          f"{usd0(a['total'])} in support of the weekday meal program. The details of the award are summarized below."),
        ("spacer", 6),
        ("kv", [("Grant reference", a["ref"]), ("Award amount", usd0(a["total"])), ("Grant period", f"{long(a['start'])} through {long(a['end'])}"),
                ("Interim report due", long(a["interim"])), ("Final report due", long(a["final"])), ("Payment", "Single payment upon receipt of the countersigned agreement")]),
        ("spacer", 8),
        ("p", "Please countersign the enclosed grant agreement and return it within thirty days. Reports should follow the Foundation's narrative and financial templates."),
        ("spacer", 10), ("p", f"Warm regards,\n\n{off}\nProgram Officer, Alder Family Foundation")], font="Helvetica", base_size=10)

    # --- G2 Harbor Trust: Times on A4, everything in prose, no box
    h = g["harbor"]; off = f"{h['officer'][0]} {h['officer'][1]}"
    write_pdf_document(os.path.join(L, "HarborTrust_grant_letter.pdf"), [
        ("right", date_variant(h["start"] - timedelta(days=52), 3)), ("spacer", 6),
        ("title", "Harbor Trust Community Fund"), ("small", "Grants Office  |  1 Harbor Way, Tacoma, WA 98402"), ("spacer", 8),
        *letter_common(h, h["start"], ed, f"Thank you for your proposal to expand the mobile pantry route. The Fund's board met on {long(h['start'] - timedelta(days=60))} and "
                                          f"approved a two-year grant to {GRANTEE} totaling {usd0(h['total'])}, to be paid as {usd0(h['y1'])} in the first year of the grant "
                                          f"and {usd0(h['y2'])} in the second year, subject to satisfactory progress. Please quote reference {h['ref']} in all correspondence."),
        ("spacer", 4),
        ("p", f"The grant period begins {date_variant(h['start'], 1)} and ends {date_variant(h['end'], 1)}. An interim narrative and financial report is due six months "
              f"after the grant period begins, and a final report is due within 60 days after the grant period ends. Second-year funds are released on approval of the interim report."),
        ("spacer", 4),
        ("p", "Funds may be used only for the purposes described in the proposal; any material change requires the Fund's written consent."),
        ("spacer", 10), ("p", f"Sincerely,\n\n{off}\nSenior Program Director"),
        ("spacer", 16), ("hr", None), ("small", "Harbor Trust Community Fund is a donor-advised fund administered by Harbor Trust. EIN 91-0000000.")],
        font="Times", pagesize="a4", base_size=11)

    # --- G3 Meridian: Courier, terms in a table; requested vs awarded in the prose
    m = g["meridian"]; off = f"{m['officer'][0]} {m['officer'][1]}"
    write_pdf_document(os.path.join(L, "Meridian_Health_Fdn_notice_of_award.pdf"), [
        ("title", "NOTICE OF AWARD"), ("small", "Meridian Health Foundation  -  Community Nutrition Initiative"), ("hr", None),
        ("kv", [("Grantee", GRANTEE), ("Award number", m["ref"]), ("Date of notice", date_variant(m["start"] - timedelta(days=33), 0))]),
        ("spacer", 8),
        ("p", f"Dear {ed}: The review committee considered your request of {usd0(m['requested'])} for the Nutrition Education Program. The committee approved partial funding, and "
              f"the Foundation is pleased to award {GRANTEE} the amount of {usd0(m['total'])} for a twelve-month project period. The award is subject to the terms below."),
        ("spacer", 8),
        ("table", [["Term", "Provision"],
                   ["Project period", f"{date_variant(m['start'], 2)} to {date_variant(m['end'], 2)}"],
                   ["Amount awarded", usd0(m["total"])],
                   ["Interim progress report", f"Due on or before {date_variant(m['interim'], 2)}"],
                   ["Final report", "Due within 90 days of the close of the project period"],
                   ["Disbursement", "Two installments: 60% at execution, 40% on acceptance of the interim report"]], {"col_widths": [55 * 2.83, 115 * 2.83], "grid": True, "shade_header": True}),
        ("spacer", 10), ("p", f"Questions about reporting may be directed to {off}, Grants Manager."), ("spacer", 8), ("p", f"{off}\nGrants Manager, Meridian Health Foundation")],
        font="Courier", base_size=9.5)

    # --- G4 Northgate: image-only scan
    n = g["northgate"]; off = f"{n['officer'][0]} {n['officer'][1]}"
    write_scan_pdf(os.path.join(L, "scan_northgate_letter.pdf"), [
        "NORTHGATE SAVINGS CHARITABLE TRUST", "310 Union St, Boise, ID 83702", "", date_variant(n["start"] - timedelta(days=25), 3), "",
        f"{GRANTEE}", f"Attn: {ed}", "", f"Re: Grant {n['ref']}", "",
        f"Dear {ed.split()[0]},", "", "The Trustees are pleased to award your", f"organization a grant of {usd0(n['total'])} for the",
        "community breakfast program.", "", f"Grant period: {long(n['start'])}", f"              to {long(n['end'])}", "",
        f"Progress report due: {long(n['interim'])}", f"Final report due:    {long(n['final'])}", "",
        "A check will follow under separate cover.", "Please acknowledge receipt in writing.", "", "With best wishes,", "",
        f"{off}", "Trust Administrator"], font_size=32, seed=seed + 11, skew_deg=-0.8, noise=700)

    # --- G5 Sycamore: Helvetica letter, box first, table of years, total in words; final 45 days after end
    s5 = g["sycamore"]; off = f"{s5['officer'][0]} {s5['officer'][1]}"
    write_pdf_document(os.path.join(L, "Sycamore-Fund-2026-award.pdf"), [
        ("kv", [("Grant ID", s5["ref"]), ("Grantee", GRANTEE), ("Program", "Farm-to-Kitchen Sourcing"), ("Letter date", long(s5["start"] - timedelta(days=45)))]),
        ("hr", None), ("title", "Grant Award Letter"), ("small", "Sycamore Fund  |  PO Box 2210, Madison, WI 53703"), ("spacer", 6),
        ("p", f"Dear {ed},"), ("spacer", 4),
        ("p", f"We are delighted to award {GRANTEE} a two-year grant in the total amount of {WORDS[s5['total']]} ({usd0(s5['total'])}), payable according to the schedule below. "
              f"The grant period runs from {date_variant(s5['start'], 4)} to {date_variant(s5['end'], 4)}."),
        ("spacer", 6),
        ("table", [["Grant year", "Period", "Amount"],
                   ["Year 1", f"{date_variant(s5['start'], 4)} - {date_variant(add_months(s5['start'], 12) - timedelta(days=1), 4)}", usd0(s5["y1"])],
                   ["Year 2", f"{date_variant(add_months(s5['start'], 12), 4)} - {date_variant(s5['end'], 4)}", usd0(s5["y2"])]], {"col_widths": [30 * 2.83, 80 * 2.83, 40 * 2.83], "align_right": [2]}),
        ("spacer", 8),
        ("p", f"Reporting: an interim report is due {long(s5['interim'])}. A final narrative and financial report is due no later than 45 days after the end of the grant period. "
              "Year 2 funds will be released after the interim report has been reviewed."),
        ("spacer", 10), ("p", f"Congratulations,\n\n{off}\nExecutive Director, Sycamore Fund")], font="Helvetica", base_size=10.5)

    # --- G6 Willow Creek: original letter and a later amendment (Times)
    w = g["willow"]; off = f"{w['officer'][0]} {w['officer'][1]}"
    write_pdf_document(os.path.join(L, "WillowCreek_original_award_2026-05.pdf"), [
        ("title", "Willow Creek Foundation"), ("small", "88 Church St, Burlington, VT 05401"), ("right", long(date(2026, 5, 20))), ("hr", None),
        *letter_common(w, w["start"], ed, f"The Foundation is pleased to award {GRANTEE} {usd0(w['orig_total'])} for the Cold Storage and Distribution project. "
                                          f"Reference {w['ref']}."),
        ("spacer", 4),
        ("kv", [("Grant period", f"{date_variant(w['start'], 6)} - {date_variant(w['orig_end'], 6)}"), ("Amount", usd0(w["orig_total"])),
                ("Interim report", f"due {long(w['interim'])}"), ("Final report", f"due {long(w['orig_final'])}")]),
        ("spacer", 8), ("p", "Please sign and return the attached agreement."), ("spacer", 10), ("p", f"Sincerely,\n\n{off}\nGrants Director")],
        font="Times", base_size=11)
    write_pdf_document(os.path.join(L, "WillowCreek_amendment_letter.pdf"), [
        ("title", "Willow Creek Foundation"), ("small", "88 Church St, Burlington, VT 05401"), ("right", long(date(2026, 8, 24))), ("hr", None),
        ("h", f"Amendment No. 1 to Grant {w['ref']}"),
        ("p", f"Dear {ed.split()[0]},"), ("spacer", 4),
        ("p", f"Following your letter of {long(date(2026, 8, 10))} about the delayed delivery of the walk-in cooler, the Board has approved the following changes to grant {w['ref']}, "
              f"originally awarded on {long(date(2026, 5, 20))}:"),
        ("spacer", 4),
        ("p", f"1. The grant period is extended by six months and now ends {long(w['end'])}. The start date is unchanged.\n"
              f"2. The award is increased by {usd0(w['bump'])}, for a revised total of {usd0(w['total'])}. The additional funds will be paid with the second installment.\n"
              f"3. The final report is now due 60 days after the revised end date. The interim report date of {long(w['interim'])} is unchanged."),
        ("spacer", 6), ("p", "All other terms of the grant agreement remain in effect. Please countersign below and return one copy to our office."),
        ("spacer", 10), ("p", f"Sincerely,\n\n{off}\nGrants Director"), ("spacer", 14),
        ("p", f"Acknowledged for {GRANTEE}:  ______________________   Date: __________")], font="Times", base_size=11)

    # --- Declination (distractor)
    dc = d["declined"]; off = f"{dc['officer'][0]} {dc['officer'][1]}"
    write_pdf_document(os.path.join(L, "Granite_Peak_Foundation_response.pdf"), [
        ("title", "Granite Peak Foundation"), ("small", "500 Ridge Rd, Denver, CO 80202"), ("right", long(date(2026, 8, 5))), ("hr", None),
        ("p", f"Dear {ed},"), ("spacer", 4),
        ("p", f"Thank you for your application (reference {dc['ref']}) requesting {usd0(dc['requested'])} for kitchen equipment. We received many more strong proposals than we can fund this cycle, "
              "and we regret that we are unable to award a grant for this request. We encourage you to apply again in the spring cycle."),
        ("spacer", 10), ("p", f"Sincerely,\n\n{off}\nProgram Associate")], font="Helvetica", base_size=10)

    write_text(os.path.join(ws, "note_from_dana.txt"),
        f"Hi - the funder letters from this year are in the funder_letters folder (I scanned the Northgate one from the paper copy).\n"
        "For the tracker I need grants.csv with these columns, in this order:\n\n"
        "grant_ref, funder, total_amount, year1_amount, year2_amount, period_start, period_end, interim_report_due, final_report_due\n\n"
        "grant_ref is the funder's own reference/award number exactly as printed. Amounts as plain numbers (no $ or commas). "
        "For a one-year grant put the whole award in year1_amount and 0 in year2_amount so the columns add up. "
        "Dates as YYYY-MM-DD so the sheet sorts. Where a letter gives a deadline as a rule rather than a date, work the date out.\n\n"
        f"Thanks, {COORD}\n")

    header = ["grant_ref", "funder", "total_amount", "year1_amount", "year2_amount", "period_start", "period_end", "interim_report_due", "final_report_due"]
    order = ["alder", "harbor", "meridian", "northgate", "sycamore", "willow"]
    rows = [[g[k]["ref"], g[k]["funder"], g[k]["total"], g[k]["y1"], g[k]["y2"], iso(g[k]["start"]), iso(g[k]["end"]), iso(g[k]["interim"]), iso(g[k]["final"])] for k in order]
    write_csv(os.path.join(ref, "grants.csv"), header, rows)
    write_csv(os.path.join(sol, "grants.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {"declined_ref": dc["ref"], "amended_ref": g["willow"]["ref"], "amended_original": {"total": w["orig_total"], "end": iso(w["orig_end"]), "final": iso(w["orig_final"])},
                                                  "multi_year_refs": [g["harbor"]["ref"], g["sycamore"]["ref"]], "requested_vs_awarded": {"ref": m["ref"], "requested": m["requested"]},
                                                  "scan_ref": n["ref"]})
    write_task_yaml(HERE, {
        "id": "grant-award-letters", "track": "desk", "category": "extraction",
        "title": "Log this year's grant award letters into the tracker",
        "ask": "Go through the funder letters in the folder and put the key details of every grant into grants.csv, one row per grant. Dana's note has the columns I need.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "two grants are multi-year and state the award by year, one in prose and one in a table; the total is the sum and the year columns are split, and one-year grants carry 0 in year 2 (check: award amounts)",
            "three letters give a reporting deadline as a rule (six months after the period begins; within 60, 45 or 90 days after it ends) and the date must be computed (check: report due dates)",
            "one letter names the amount requested before the smaller amount awarded (check: award amounts)",
            "one grant has an amendment letter that raises the award, extends the period and moves the final report to 60 days after the new end date, which is 29 February 2028; the row must carry the amended values and the amendment is not a second row (checks: award amounts; grant period; report due dates; one row per awarded grant)",
            "one letter is a declination and must not produce a row (check: declined request absent)",
            "one award letter is an image-only scan (checks: one row per awarded grant; grant period)",
            "dates appear in five formats across the letters; the tracker wants YYYY-MM-DD (check: grant period)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "grants.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per awarded grant", "path": "grants.csv", "column": "grant_ref", "ref": "grants.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "grants.csv", "equals_ref": "grants.csv"},
            {"type": "csv_values_match", "name": "funder names", "path": "grants.csv", "ref": "grants.csv", "key": "grant_ref", "columns": ["funder"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "award amounts", "path": "grants.csv", "ref": "grants.csv", "key": "grant_ref",
             "columns": ["total_amount", "year1_amount", "year2_amount"], "numeric": True, "tolerance": 0.5, "min_accuracy": 1.0,
             "must_match_keys": [g["harbor"]["ref"], g["sycamore"]["ref"], g["meridian"]["ref"], g["willow"]["ref"]]},
            {"type": "csv_values_match", "name": "grant period", "path": "grants.csv", "ref": "grants.csv", "key": "grant_ref",
             "columns": ["period_start", "period_end"], "min_accuracy": 1.0, "must_match_keys": [g["willow"]["ref"], g["northgate"]["ref"]]},
            {"type": "csv_values_match", "name": "report due dates", "path": "grants.csv", "ref": "grants.csv", "key": "grant_ref",
             "columns": ["interim_report_due", "final_report_due"], "min_accuracy": 1.0,
             "must_match_keys": [g["harbor"]["ref"], g["meridian"]["ref"], g["sycamore"]["ref"], g["willow"]["ref"]]},
            {"type": "text_not_contains", "name": "declined request absent", "path": "grants.csv", "phrases": [dc["ref"], "granite peak"]},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
