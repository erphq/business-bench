#!/usr/bin/env python3
"""project-margin: revenue, cost and margin per job for an interiors studio, with the loss-makers flagged.

    python gen.py [--seed N] [--naive DIR]

Business: a nine-job interior fit-out studio. Revenue and costs live on separate sheets of the same
workbook and are keyed differently, and the hours nobody has invoiced yet are in their own export.

Traps (each caught by a check, see task.yaml):
  * costs sit on another sheet keyed by job name, revenue by job code (checks: Cedar Point cost; total margin)
  * draft and written-off invoices are not revenue                    (checks: Harborview revenue; total margin)
  * unbilled hours are real cost at the cost rate                     (checks: Cedar Point cost; worst job margin)
  * vendor credits are negative cost rows in parentheses              (check: Cedar Point cost)
  * one job has no revenue at all and must still be on the report     (checks: worst job margin; memo names both loss-makers)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403


def cent_tol(expected: float, rel: float = 0.01) -> float:
    """rel_tol for a workbook figure that ties to the cent: the largest power of ten keeping expected x rel_tol
    under 1.00 (never looser than rel). Figures involving conversion, proration or an estimate declare
    `rounding: <reason>` on the check instead and keep rel_tol at most 0.001."""
    import math
    e = abs(float(expected))
    if e <= 1.0:
        return rel
    return min(rel, float(f"1e{-(math.floor(math.log10(e)) + 1)}"))



# bizgen.write_xlsx leaves openpyxl's save-time wall clock in docProps/core.xml, so two runs a
# second apart produce different bytes and the validator's determinism check fails intermittently.
# Local workaround (tasks/lib is not ours to change): pin dcterms:modified and re-freeze the zip.
import io as _io  # noqa: E402
import re as _re  # noqa: E402
import zipfile as _zip  # noqa: E402


def stable_xlsx(path: str, sheets: dict, creator: str = "Export") -> None:
    write_xlsx(path, sheets, creator=creator)
    with _zip.ZipFile(path) as z:
        items = sorted((n, z.read(n)) for n in z.namelist())
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as out:
        for name, data in items:
            if name == "docProps/core.xml":
                data = _re.sub(rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>",
                               b'<dcterms:modified xsi:type="dcterms:W3CDTF">2026-01-15T09:00:00Z</dcterms:modified>',
                               data)
            zi = _zip.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = _zip.ZIP_DEFLATED
            out.writestr(zi, data)
    write_bytes(path, buf.getvalue())

JOBS = [("P-2401", "Harborview Lofts", "Harborview Development LLC"),
        ("P-2402", "Cedar Point Clinic", "Cedar Point Health"),
        ("P-2403", "Tamarack Taproom", "Tamarack Brewing"),
        ("P-2404", "Silverline HQ", "Silverline Logistics"),
        ("P-2405", "Quarry Road Nursery", "Quarry Road Garden Co"),
        ("P-2406", "Ellington Bakery", "Ellington Bakeries"),
        ("P-2407", "Wren & Sparrow Bookshop", "Wren & Sparrow"),
        ("P-2408", "Northfield Auto Body", "Northfield Auto"),
        ("P-2409", "Umber Ceramics Studio", "Umber Ceramics")]
NO_REVENUE = "P-2409"      # every invoice still in draft
FLIPS = "P-2405"           # only negative once the unbilled hours are costed
COST_CATS = ["Labour", "Materials", "Subcontractor", "Travel", "Permits"]
ROLES = [("Principal", 96.0), ("Project architect", 72.0), ("Designer", 58.0), ("Drafter", 44.0), ("Site manager", 65.0)]
WORK = ["schematic design", "construction documents", "site visit", "millwork detailing", "client revisions",
        "permit set", "FF&E schedule", "punch list"]


def build(seed: int) -> dict:
    r = rng(seed)
    jobs = []
    for code, name, client in JOBS:
        rev_target = money(r, 45000, 85000, cents=False) if code == NO_REVENUE else money(r, 90000, 420000, cents=False)
        jobs.append({"code": code, "name": name, "client": client, "rev_target": rev_target})

    # ---- fees raised: exactly one invoice per job never went out (all of them on the unbilled job) ----
    invoices, inv_no = [], 700
    for j in jobs:
        n = r.randint(3, 6)
        parts = [r.uniform(0.6, 1.4) for _ in range(n)]
        scale = j["rev_target"] / sum(parts)
        unsent = r.randrange(n)
        for i, p in enumerate(parts):
            inv_no += 1
            if j["code"] == NO_REVENUE:
                status = "Draft"
            elif i == unsent:
                status = r.choice(["Draft", "Written off"])
            else:
                status = "Invoiced"
            invoices.append({"no": f"INV-{inv_no}", "job": j, "status": status,
                             "date": day_in(r, date(2026, 1, 6), date(2026, 6, 26)),
                             "amount": round(p * scale, 2),
                             "desc": f"{r.choice(['Fee instalment', 'Progress claim', 'Design fee', 'Stage payment'])} "
                                     f"{i + 1} of {n}"})
    for j in jobs:
        j["revenue"] = round(sum(x["amount"] for x in invoices if x["job"] is j and x["status"] == "Invoiced"), 2)
        if j["code"] == NO_REVENUE:
            j["cost_target"] = round(j["rev_target"] * r.uniform(0.66, 0.82), 2)
        elif j["code"] == FLIPS:
            j["cost_target"] = round(j["revenue"] * r.uniform(1.08, 1.16), 2)
        else:
            j["cost_target"] = round(j["revenue"] * r.uniform(0.60, 0.84), 2)

    # ---- booked costs on the Costs sheet, plus vendor credits ----
    costs, cost_no = [], 5000
    for j in jobs:
        booked = j["cost_target"] * r.uniform(0.74, 0.86)
        n = r.randint(14, 24)
        parts = [r.uniform(0.4, 1.8) for _ in range(n)]
        scale = booked / sum(parts)
        for p in parts:
            cost_no += 1
            costs.append({"id": f"C-{cost_no}", "job": j, "cat": r.choice(COST_CATS),
                          "date": day_in(r, date(2026, 1, 8), date(2026, 6, 28)),
                          "amount": round(p * scale, 2),
                          "desc": f"{r.choice(['Invoice', 'Purchase', 'Allocation'])} - {r.choice(WORK)}"})
    credits = []
    for j in jobs:
        for _ in range(r.randint(1, 2)):
            cost_no += 1
            base = [c for c in costs if c["job"] is j and c["cat"] in ("Materials", "Subcontractor")] \
                or [c for c in costs if c["job"] is j]
            src = max(r.sample(base, min(5, len(base))), key=lambda c: c["amount"])
            credits.append({"id": f"C-{cost_no}", "job": j, "cat": src["cat"],
                            "date": src["date"], "amount": -round(src["amount"] * r.uniform(0.35, 0.7), 2),
                            "desc": f"Vendor credit against {src['id']}"})
    costs += credits

    # ---- unbilled hours ----
    unbilled = []
    for j in jobs:
        booked = sum(c["amount"] for c in costs if c["job"] is j)
        want = max(j["cost_target"] - booked, 1200.0)
        while want > 0:
            role, rate = r.choice(ROLES)
            hours = round(r.uniform(6, 38) * 2) / 2
            amt = round(hours * rate, 2)
            unbilled.append({"job": j, "role": role, "rate": rate, "hours": hours,
                             "date": day_in(r, date(2026, 4, 1), date(2026, 6, 30)),
                             "who": " ".join(person(r)), "task": r.choice(WORK), "amount": amt})
            want -= amt

    for j in jobs:
        j["booked_cost"] = round(sum(c["amount"] for c in costs if c["job"] is j), 2)
        j["unbilled_cost"] = round(sum(u["amount"] for u in unbilled if u["job"] is j), 2)
        j["cost"] = round(j["booked_cost"] + j["unbilled_cost"], 2)
        j["margin"] = round(j["revenue"] - j["cost"], 2)
    invoices.sort(key=lambda x: (x["date"], x["no"]))
    costs.sort(key=lambda x: (x["date"], x["id"]))
    unbilled.sort(key=lambda x: (x["date"], x["job"]["code"], x["who"]))
    tot = {"revenue": round(sum(j["revenue"] for j in jobs), 2), "cost": round(sum(j["cost"] for j in jobs), 2)}
    tot["margin"] = round(tot["revenue"] - tot["cost"], 2)
    negatives = [j for j in jobs if j["margin"] < 0]
    return {"jobs": jobs, "invoices": invoices, "costs": costs, "unbilled": unbilled, "tot": tot,
            "negatives": sorted(negatives, key=lambda j: j["margin"])}


def acceptable(d: dict) -> bool:
    jobs = {j["code"]: j for j in d["jobs"]}
    neg = d["negatives"]
    if len(neg) != 2 or {j["code"] for j in neg} != {NO_REVENUE, FLIPS}:
        return False
    if neg[0]["code"] != NO_REVENUE and abs(neg[0]["margin"] - neg[1]["margin"]) < 5000:
        return False
    # the naive read (every invoice is revenue, only the Costs sheet, credits as positives)
    naive_neg = []
    for j in d["jobs"]:
        rev = sum(x["amount"] for x in d["invoices"] if x["job"] is j)
        cost = sum(abs(c["amount"]) for c in d["costs"] if c["job"] is j)
        if rev - cost < 0:
            naive_neg.append(j["code"])
    if set(naive_neg) == {NO_REVENUE, FLIPS} or FLIPS in naive_neg:
        return False
    h = jobs["P-2401"]
    dropped = sum(x["amount"] for x in d["invoices"] if x["job"] is h and x["status"] != "Invoiced")
    if dropped < 0.05 * h["revenue"]:
        return False
    c = jobs["P-2402"]
    cr = sum(-x["amount"] for x in d["costs"] if x["job"] is c and x["amount"] < 0)
    if c["unbilled_cost"] < 0.05 * c["cost"] or cr < 0.02 * c["cost"]:
        return False

    def unique(job, v):
        row = [job["revenue"], job["cost"], job["margin"]]
        return sum(1 for x in row if abs(x - v) <= max(abs(v) * 0.005, 0.01)) == 1
    if not (unique(h, h["revenue"]) and unique(c, c["cost"]) and unique(neg[0], neg[0]["margin"])):
        return False
    trow = [d["tot"]["revenue"], d["tot"]["cost"], d["tot"]["margin"]]
    if sum(1 for x in trow if abs(x - d["tot"]["margin"]) <= abs(d["tot"]["margin"]) * 0.005) != 1:
        return False
    if d["tot"]["margin"] < 50000:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(rev_rows, cost_rows, jobs) -> dict:
    n, m = len(rev_rows) + 1, len(cost_rows) + 1
    rows = []
    for i, j in enumerate(jobs, start=2):
        rows.append([j["name"], j["code"],
                     f"=SUMIF(Revenue!$B$2:$B${n},$A{i},Revenue!$C$2:$C${n})",
                     f"=SUMIF(Costs!$B$2:$B${m},$A{i},Costs!$D$2:$D${m})",
                     f"=C{i}-D{i}",
                     f'=IF(C{i}=0,"n/a",ROUND(E{i}/C{i},4))',
                     f'=IF(E{i}<0,"NEGATIVE","")'])
    last = 1 + len(jobs)
    rows.append(["Total - all jobs", "", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})", f"=SUM(E2:E{last})",
                 f'=IF(C{last + 1}=0,"n/a",ROUND(E{last + 1}/C{last + 1},4))', ""])
    rows.append([])
    rows.append(["Revenue is invoiced work only (drafts and write-offs excluded). Cost includes unbilled hours at "
                 "cost rate and is net of vendor credits."])
    return {
        "Revenue": {"header": ["invoice_no", "job", "amount"], "rows": rev_rows, "widths": {"B": 26}},
        "Costs": {"header": ["cost_id", "job", "category", "amount"], "rows": cost_rows, "widths": {"B": 26, "C": 16}},
        "Report": {"header": ["Job", "Code", "Revenue", "Cost", "Margin", "Margin %", "Flag"], "rows": rows,
                   "widths": {"A": 26, "C": 14, "D": 14, "E": 14, "F": 10, "G": 11}},
    }


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    jobs = {j["code"]: j for j in d["jobs"]}
    neg = d["negatives"]
    worst = neg[0]

    # ---- workspace ----
    stable_xlsx(os.path.join(ws, "project_ledger_2026_h1.xlsx"), {
        "Revenue": {"merged_title": "Fees raised - first half 2026",
                    "preamble": [["Status: Invoiced = sent to the client. Draft = not sent."]],
                    "header": ["Invoice No", "Date", "Job Code", "Description", "Amount", "Status"],
                    "rows": [[x["no"], date_variant(x["date"], sum(ord(c) for c in x["no"]) % 3), x["job"]["code"],
                              x["desc"], money_str(x["amount"], 1), x["status"]] for x in d["invoices"]],
                    "widths": {"A": 12, "C": 12, "D": 30, "E": 14}},
        "Costs": {"merged_title": "Job costs - first half 2026",
                  "preamble": [["Entered against the job name. Credits from suppliers show in brackets."]],
                  "header": ["Cost ID", "Date", "Job", "Category", "Detail", "Amount"],
                  "rows": [[x["id"], date_variant(x["date"], sum(ord(c) for c in x["id"]) % 3),
                            name_noise(rng(sum(ord(c) for c in x["id"])), x["job"]["name"]), x["cat"], x["desc"],
                            money_str(x["amount"], 5 if x["amount"] < 0 else 1)] for x in d["costs"]],
                  "widths": {"A": 12, "C": 26, "D": 16, "E": 34, "F": 14}},
        "Jobs": {"merged_title": "Job list", "header": ["Job Code", "Job", "Client", "Status"],
                 "rows": [[j["code"], j["name"], j["client"], "Live" if j["code"] != "P-2403" else "Practical completion"]
                          for j in d["jobs"]], "widths": {"B": 26, "C": 28}},
    }, creator="Studio admin")
    write_csv(os.path.join(ws, "unbilled_time_to_date.csv"),
              ["Date", "Job Code", "Staff", "Role", "Task", "Hours", "Cost rate"],
              [[date_variant(u["date"], 0), u["job"]["code"], u["who"], u["role"], u["task"],
                f"{u['hours']:.1f}", money_str(u["rate"], 2)] for u in d["unbilled"]],
              preamble=["Time logged but not yet invoiced", "as at 06/30/2026"])
    write_text(os.path.join(ws, "note_from_the_principal.txt"),
               "Job margins for the partners' meeting\n"
               "\n"
               "I want to see, job by job, what we have actually earned against what it has actually cost us, and\n"
               "I want the ones that are under water flagged so we stop arguing about which they are.\n"
               "\n"
               "Revenue is what we have invoiced. A draft invoice is not revenue - it is a hope. Anything we wrote\n"
               "off is not revenue either.\n"
               "\n"
               "Cost is everything the job has consumed. The hours in the unbilled file are hours we have paid for,\n"
               "so they are cost at the cost rate on the row, whether or not the client ever sees a bill for them.\n"
               "Supplier credits come off the cost of the job they were raised against.\n"
               "\n"
               "Every job on the job list goes on the report, including the ones we have not billed yet.\n"
               "\n"
               "- Fatima\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "job_margins.csv"), ["code", "job", "revenue", "cost", "margin"],
              [[j["code"], j["name"], f"{j['revenue']:.2f}", f"{j['cost']:.2f}", f"{j['margin']:.2f}"] for j in d["jobs"]] +
              [["ALL", "All jobs", f"{d['tot']['revenue']:.2f}", f"{d['tot']['cost']:.2f}", f"{d['tot']['margin']:.2f}"]])
    write_json(os.path.join(ref, "notes.json"), {
        "negative_jobs": [{"code": j["code"], "name": j["name"], "margin": j["margin"]} for j in neg],
        "worst_job": worst["name"], "worst_margin": worst["margin"],
        "unbilled_cost_total": round(sum(j["unbilled_cost"] for j in d["jobs"]), 2),
        "draft_and_writeoff_total": round(sum(x["amount"] for x in d["invoices"] if x["status"] != "Invoiced"), 2),
        "vendor_credits": round(sum(-c["amount"] for c in d["costs"] if c["amount"] < 0), 2)})

    # ---- reference solution ----
    rev_rows = [[x["no"], x["job"]["name"], x["amount"]] for x in d["invoices"] if x["status"] == "Invoiced"]
    cost_rows = [[c["id"], c["job"]["name"], c["cat"], c["amount"]] for c in d["costs"]]
    cost_rows += [[f"UB-{i + 1:03d}", u["job"]["name"], "Unbilled time", round(u["amount"], 2)]
                  for i, u in enumerate(d["unbilled"])]
    stable_xlsx(os.path.join(sol, "margins.xlsx"), report_sheets(rev_rows, cost_rows, d["jobs"]), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    tok = worst["name"].split()[0].lower()
    write_task_yaml(HERE, {
        "id": "project-margin", "track": "desk", "category": "reports",
        "title": "Margin by job, with the loss-makers flagged",
        "ask": ("Fatima wants to see, job by job, what we have earned against what the job has cost us, with the ones "
                "losing money flagged. Save it as margins.xlsx with live formulas and write memo.md with the "
                "headline. Her note says what counts as revenue and cost.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "costs are on a second sheet of the workbook keyed by job name (with case and spacing noise) while "
            "revenue is keyed by job code, so the two only join through the Jobs sheet "
            "(checks: Cedar Point cost; total margin)",
            "draft and written-off invoices sit in the Revenue sheet and are not revenue; every job has at least one "
            "and one job's invoices are all still drafts (checks: Harborview revenue; total margin)",
            "the unbilled time export is cost the studio has already paid for, at the cost rate on each row "
            "(hours x rate); ignoring it lifts every margin and hides a loss-making job "
            "(checks: Cedar Point cost; worst job margin; memo names both loss-makers)",
            "vendor credits are negative cost rows written in brackets; taking the absolute value of the amount "
            "column inflates cost (check: Cedar Point cost)",
            f"{jobs[NO_REVENUE]['name']} has no invoiced revenue at all, so a report built from the revenue sheet "
            "drops it; it is the deepest loss on the list (checks: worst job margin; memo names both loss-makers)",
            "margin percentage has to survive a job with zero revenue without an error cell (check: no error cells)",
            "amounts are '$12,345.67' text with bracketed negatives, dates come in three formats, and the two "
            "ledger sheets each carry a merged title and an instruction row (check: total margin across all jobs)",
        ],
        "checks": [
            {"type": "file_exists", "name": "margins.xlsx exists", "path": "margins.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "margins.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "margins.xlsx"},
            {"type": "xlsx_value_present", "name": "Harborview revenue (invoiced only)", "path": "margins.xlsx",
             "expected": jobs["P-2401"]["revenue"], "rel_tol": cent_tol(jobs["P-2401"]["revenue"], 0.005), "near_text": "harborview"},
            {"type": "xlsx_value_present", "name": "Cedar Point cost (unbilled time in, credits netted)", "path": "margins.xlsx",
             "expected": jobs["P-2402"]["cost"], "rel_tol": cent_tol(jobs["P-2402"]["cost"], 0.005), "near_text": "cedar point"},
            {"type": "xlsx_value_present", "name": "worst job margin", "path": "margins.xlsx",
             "expected": worst["margin"], "rel_tol": cent_tol(worst["margin"], 0.005), "near_text": tok},
            {"type": "xlsx_value_present", "name": "total margin across all jobs", "path": "margins.xlsx",
             "expected": d["tot"]["margin"], "rel_tol": cent_tol(d["tot"]["margin"], 0.005), "near_text": "total"},
            {"type": "text_numbers_present", "name": "memo carries the studio totals and the worst margin", "path": "memo.md",
             "numbers": [d["tot"]["revenue"], d["tot"]["cost"], worst["margin"]], "rel_tol": 0.005},
            {"type": "text_contains_all", "name": "memo names both loss-making jobs", "path": "memo.md",
             "phrases": [j["name"] for j in neg]},
            {"type": "text_sentence_matches", "name": "memo says the worst job is losing money", "path": "memo.md",
             "all": [rf"\b{tok}\b",
                     r"(\bnegative\b|\bloss\b|\blosing\b|\blost money\b|\bunder ?water\b|\bin the red\b|"
                     r"\bbelow zero\b|\bunprofitable\b|\bovers?pent\b)"],
             "none": [r"\bbroke even\b", r"\bno (loss|losses)\b"]},
        ],
    })
    print(f"seed={seed} invoices={len(d['invoices'])} costs={len(d['costs'])} unbilled={len(d['unbilled'])}")
    for j in d["jobs"]:
        print(f"  {j['code']} {j['name']:24} rev={j['revenue']:>12,.2f} cost={j['cost']:>12,.2f} margin={j['margin']:>12,.2f}")
    print("totals:", d["tot"], "negatives:", [(j["name"], j["margin"]) for j in neg])


def memo_text(d: dict) -> str:
    neg, tot = d["negatives"], d["tot"]
    worst, other = neg[0], neg[1]
    best = max(d["jobs"], key=lambda j: j["margin"])
    return f"""# Job margins, first half 2026

Across the nine jobs we invoiced {tot['revenue']:,.2f} against costs of {tot['cost']:,.2f}, a margin of
{tot['margin']:,.2f}. {best['name']} is the strongest job at {best['margin']:,.2f}.

**Two jobs are losing money.** {worst['name']} is the worst at {worst['margin']:,.2f} - it has
{worst['revenue']:,.2f} of invoiced revenue against {worst['cost']:,.2f} of cost. {other['name']} is also under
water at {other['margin']:,.2f}; it only turns negative once the hours we have not billed are costed in.

Two things that move these numbers:

1. Revenue here is invoiced work only. Draft and written-off invoices are excluded, which is why
   {worst['name']} shows the revenue it does.
2. Cost includes {sum(1 for _ in d['unbilled'])} unbilled time entries worth
   {sum(j['unbilled_cost'] for j in d['jobs']):,.2f} at cost rate, and is net of the supplier credits raised
   against each job.
"""


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: every invoice is revenue, cost is whatever the Costs sheet says
    with the brackets read as plain numbers, and the unbilled time file is never opened."""
    os.makedirs(out, exist_ok=True)
    rev_rows = [[x["no"], x["job"]["name"], x["amount"]] for x in d["invoices"]]
    cost_rows = [[c["id"], c["job"]["name"], c["cat"], abs(c["amount"])] for c in d["costs"]]
    jobs = [j for j in d["jobs"] if any(x["job"] is j for x in d["invoices"])]
    stable_xlsx(os.path.join(out, "margins.xlsx"), report_sheets(rev_rows, cost_rows, jobs), creator="naive")
    write_text(os.path.join(out, "memo.md"),
               "# Job margins\n\nAll nine jobs are in the report. Margins look healthy across the board and the "
               "studio is comfortably ahead for the half.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
