#!/usr/bin/env python3
"""cv-batch-extraction: ten resumes for one opening to a candidate list with contact details and experience.

    python gen.py [--seed N]

Business: a freight broker is hiring an operations coordinator. The hiring manager wants one row per applicant
with contact details, current role, and years of experience worked out to a fixed date.

Traps (each caught by a check, see task.yaml):
  * phones in six formats, two with a +1 or 1- prefix; the note wants 10 digits          (check: phones)
  * ongoing jobs say Present, Current or "to date"; they count through August 2026 and give the current role
    (checks: current roles; years of experience)
  * two candidates have gaps (a career break, eight months between jobs) that do not count (check: years of experience)
  * one candidate's part-time freelance role overlaps a full-time job                  (check: years of experience)
  * one candidate's last job ended in June 2026, so current title and employer are blank  (check: current roles)
  * one applicant sent a 2025 resume and a 2026 resume with a new email and a newer job   (checks: one row per candidate; current roles)
  * education date ranges sit beside job dates; one chronological resume lists school first (check: years of experience)
  * one resume is an image-only scan                                                     (check: one row per candidate)
"""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MM = 2.8346
ASOF = (2026, 8)
DOMAINS = ["example.com", "example.net", "example.org", "mail.example", "inbox.example"]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
TITLES = ["Dispatch Coordinator", "Logistics Assistant", "Operations Specialist", "Office Manager", "Customer Service Lead", "Inventory Analyst",
          "Shipping Supervisor", "Purchasing Assistant", "Operations Analyst", "Account Coordinator", "Warehouse Team Lead", "Scheduling Coordinator",
          "Administrative Assistant", "Traffic Coordinator", "Fleet Coordinator", "Order Processing Specialist"]
EMPLOYERS = ["Dorsey Freight", "Silverline Logistics", "Acme Industrial", "Granite Peak Outfitters", "Harbor Light Marine", "Ironwood Fabrication",
             "Valley Forge Storage", "Pinnacle Roofing", "Tamarack Brewing", "Northfield Auto Body", "Kestrel Analytics", "Redwood Property Mgmt",
             "Yellowtail Seafood", "Westbrook Plumbing", "Ellington Bakeries", "Quarry Road Nursery", "Everline Insurance", "Meridian Title"]
CITIES_ = ["Denver, CO", "Aurora, CO", "Lakewood, CO", "Boulder, CO", "Littleton, CO", "Golden, CO"]
SCHOOLS = ["Metro State University", "Front Range Community College", "Colorado Mesa University", "Red Rocks Community College"]


def ym(y, m): return y * 12 + (m - 1)
def unym(i): return divmod(i, 12)[0], divmod(i, 12)[1] + 1


def months_worked(jobs):
    s = set()
    for j in jobs:
        end = ym(*ASOF) if j["end"] is None else j["end"]
        s.update(range(j["start"], end + 1))
    return len(s)


def fmt(i, style):
    y, m = unym(i)
    return {"mon": f"{MON[m - 1]} {y}", "month": f"{MONTH[m - 1]} {y}", "slash": f"{m:02d}/{y}", "iso": f"{y}-{m:02d}"}[style]


def build(seed: int) -> dict:
    r = rng(seed)
    names = people(r, 9)
    titles = r.sample(TITLES, len(TITLES)); emps = r.sample(EMPLOYERS, len(EMPLOYERS))
    ti = iter(titles * 3); ei = iter(emps * 3)

    def job(sy, sm, ey=None, em=None, part=False):
        return dict(start=ym(sy, sm), end=None if ey is None else ym(ey, em), title=next(ti), employer=next(ei), part=part)

    def jitter(y, m, k):
        return unym(ym(y, m) + r.randint(-k, k))

    def phone():
        return f"{r.choice([303, 720, 970, 719])}5550{r.randint(100, 199)}"

    C = []
    specs = [
        # (layout, date style, present word, phone style index into PHONE_STYLES, jobs builder)
        ("L1", "mon", "Present", 0, lambda: [job(*jitter(2016, 5, 2), 2019, 2), job(2019, 3, 2022, 7), job(2022, 8)]),
        ("L2", "month", "Current", 1, lambda: [job(*jitter(2015, 9, 2), 2020, 6), job(2020, 7), job(2021, 1, 2023, 12, part=True)]),
        ("L5", "mon", "Present", 6, lambda: [job(*jitter(2013, 2, 2), 2018, 10), job(2020, 1)]),
        ("L3", "slash", None, 3, lambda: [job(*jitter(2014, 6, 2), 2017, 8), job(2017, 9, 2021, 3), job(2021, 4, 2026, 6)]),
        ("SCAN", "mon", "present", 3, lambda: [job(*jitter(2018, 1, 2), 2020, 2), job(2020, 3)]),
        ("L6", "iso", "to date", 4, lambda: [job(*jitter(2017, 4, 2), 2019, 12), job(2020, 1, 2023, 5), job(2023, 6)]),
        ("L5b", "month", "Present", 5, lambda: [job(*jitter(2012, 9, 2), 2016, 4), job(2017, 1)]),
        ("DUP", "mon", "Present", 2, lambda: [job(*jitter(2015, 1, 2), 2019, 6), job(2019, 7, 2025, 10), job(2025, 11)]),
        ("L3b", "mon", "Present", 0, lambda: [job(*jitter(2016, 2, 2), 2019, 7), job(2019, 8)]),
    ]
    for i, (layout, dstyle, pw, pstyle, jb) in enumerate(specs):
        first, last = names[i]
        jobs = jb()
        # keep the rounded year figure unambiguous: total months never 3 mod 6
        while months_worked(jobs) % 6 == 3:
            jobs[0]["start"] -= 1
        mw = months_worked(jobs)
        cur = [j for j in jobs if j["end"] is None and not j["part"]]
        email = f"{first}.{last}{r.randint(1, 99) if i % 3 == 0 else ''}@{r.choice(DOMAINS)}".lower()
        edu_end = ym(*unym(jobs[0]["start"])) // 12
        C.append(dict(i=i, layout=layout, dstyle=dstyle, pw=pw, pstyle=pstyle, first=first, last=last, name=f"{first} {last}", email=email,
                      phone=phone(), city=r.choice(CITIES_), jobs=jobs, months=mw, years=round(mw / 12, 1),
                      cur_title=cur[0]["title"] if cur else "", cur_emp=cur[0]["employer"] if cur else "",
                      edu=(r.choice(SCHOOLS), edu_end - 4, edu_end), naive_span=ym(*ASOF) - min(j["start"] for j in jobs) + 1))
    dup = C[7]
    old_email = f"{dup['first'][0]}{dup['last']}@{r.choice(DOMAINS)}".lower()
    dup["old"] = dict(email=old_email, jobs=[dict(dup["jobs"][0]), dict(dup["jobs"][1], end=None)])
    return dict(C=C, mgr=person(r))


def daterange(c, j):
    s = fmt(j["start"], c["dstyle"])
    e = c["pw"] if j["end"] is None else fmt(j["end"], c["dstyle"])
    return s, e


def bullets(r, title):
    pool = ["Scheduled daily pickups and deliveries for 40+ accounts", "Resolved carrier billing disputes and claims", "Maintained inventory records in the ERP",
            "Trained three new hires on order entry", "Cut late shipments by tracking exceptions daily", "Prepared weekly KPI reports for management",
            "Coordinated vendor onboarding and insurance certificates", "Handled inbound customer calls and email", "Built a shared shipping calendar"]
    return r.sample(pool, 2)


def emit(seed: int) -> None:
    d = build(seed); C = d["C"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "resumes"); os.makedirs(F, exist_ok=True)
    rb = rng(seed + 404)

    def phone_s(c, digits=None, style=None):
        return phone_variant(digits or c["phone"], c["pstyle"] if style is None else style)

    def jobs_desc(c, jobs):
        return sorted(jobs, key=lambda j: -j["start"])

    for c in C:
        L = c["layout"]
        if L in ("L1", "DUP"):
            variants = [(c["email"], c["jobs"], "Updated September 2026", "Resume")]
            if L == "DUP":
                variants.append((c["old"]["email"], c["old"]["jobs"], "Updated March 2025", "Resume_old"))
            for email, jobs, upd, tag in variants:
                blocks = [("title", c["name"]), ("p", f"{c['city']}  |  {email}  |  {phone_s(c)}"), ("small", upd), ("hr", None),
                          ("h", "Summary"), ("p", "Operations professional who keeps freight, inventory and people moving on schedule."), ("h", "Experience")]
                for j in jobs_desc(c, jobs):
                    s, e = daterange(c, j)
                    blocks += [("p", f"<b>{j['title']}</b>, {j['employer']}"), ("small", f"{s} - {e}")]
                    for b in bullets(rb, j["title"]):
                        blocks.append(("p", f"- {b}"))
                blocks += [("h", "Education"), ("p", f"{c['edu'][0]}, B.S. Business Administration, {c['edu'][1]} - {c['edu'][2]}")]
                fn = {"Resume": f"{c['first']}_{c['last']}_Resume.pdf", "Resume_old": f"Resume-{c['last']}-{c['first'][0]}-2025.pdf"}[tag]
                if L == "DUP" and tag == "Resume":
                    fn = f"{c['last']}_{c['first']}_resume_sept2026.pdf"
                write_pdf_document(os.path.join(F, fn), blocks, font="Helvetica" if tag != "Resume_old" else "Times-Roman", base_size=10)
        elif L == "L2":
            rows = [["Dates", "Position", "Employer"]]
            for j in jobs_desc(c, c["jobs"]):
                s, e = daterange(c, j)
                rows.append([f"{s} - {e}", j["title"] + (" (part-time, freelance)" if j["part"] else ""), j["employer"] if not j["part"] else "Self-employed"])
            write_pdf_document(os.path.join(F, f"CV {c['name']}.pdf"), [
                ("title", c["name"].upper()),
                ("kv", [("Email", c["email"]), ("Mobile", phone_s(c)), ("Location", c["city"])], {"col_widths": [30 * MM, 120 * MM]}),
                ("hr", None), ("h", "Professional experience"),
                ("table", rows, {"col_widths": [55 * MM, 70 * MM, 50 * MM], "grid": True}),
                ("spacer", 6), ("h", "Education"),
                ("table", [["Dates", "School", "Qualification"], [f"{c['edu'][1]} - {c['edu'][2]}", c["edu"][0], "B.A. Economics"]], {"col_widths": [55 * MM, 70 * MM, 50 * MM]}),
                ("h", "Skills"), ("p", "Excel (pivot tables, lookups), TMS and WMS systems, carrier rate negotiation, Spanish (conversational)"),
            ], pagesize="a4", font="Times-Roman", base_size=10.5)
            if any(j["part"] for j in c["jobs"]):
                for j in c["jobs"]:
                    if j["part"]:
                        j["employer"] = "Self-employed"
        elif L in ("L3", "L3b"):
            jobs = sorted(c["jobs"], key=lambda j: j["start"]) if L == "L3" else jobs_desc(c, c["jobs"])
            blocks = [("title", c["name"]), ("p", f"{phone_s(c)} / {c['email']} / {c['city']}"), ("hr", None)]
            edu = [("h", "EDUCATION"), ("p", f"{c['edu'][1]} - {c['edu'][2]}  {c['edu'][0]}, Associate of Applied Science, Supply Chain")]
            exp = [("h", "EMPLOYMENT HISTORY" if L == "L3" else "WORK EXPERIENCE")]
            for j in jobs:
                s, e = daterange(c, j)
                exp.append(("p", f"{s} - {e}  {j['title']}, {j['employer']}"))
                exp.append(("small", "; ".join(bullets(rb, j["title"]))))
            if L == "L3":
                blocks += [("p", "Objective: seeking a full-time operations role after completing a contract assignment in June 2026.")] + edu + exp
            else:
                blocks += exp + edu
            write_pdf_document(os.path.join(F, f"{c['last'].lower()}_{c['first'].lower()}_cv.pdf"), blocks, font="Courier", base_size=9,
                               pagesize="letter" if L == "L3" else "a4")
        elif L == "SCAN":
            lines = [c["name"].upper(), c["city"], f"Phone: {phone_s(c)}", f"Email: {c['email']}", "", "EXPERIENCE", ""]
            for j in jobs_desc(c, c["jobs"]):
                s, e = daterange(c, j)
                lines += [f"{j['title']}", f"{j['employer']}", f"{s} - {e}", ""]
            lines += ["EDUCATION", f"{c['edu'][0]}", f"Certificate in Logistics, {c['edu'][2]}", "", "Forklift certified. Bilingual English/Spanish."]
            write_scan_pdf(os.path.join(F, "scanned_resume_walkin.pdf"), lines, font_size=34, seed=seed * 23 + 1, skew_deg=0.3, noise=220)
        elif L == "L6":
            blocks = [("title", c["name"]), ("right", f"{c['email']}<br/>{phone_s(c)}<br/>{c['city']}"), ("hr", None), ("h", "Career history")]
            for j in jobs_desc(c, c["jobs"]):
                s, e = daterange(c, j)
                blocks += [("p", f"<b>{s} {e}</b>" if j["end"] is None else f"<b>{s} to {e}</b>"), ("p", f"{j['employer']} - {j['title']}")]
            blocks += [("h", "Education and training"), ("p", f"{c['edu'][0]} ({c['edu'][1]}-{c['edu'][2]})"), ("p", "APICS CPIM Part 1 (2022)")]
            write_pdf_document(os.path.join(F, f"Application_{c['first']}{c['last']}.pdf"), blocks, font="Times-Roman", base_size=11)
        elif L in ("L5", "L5b"):
            blocks = [("title", c["name"]), ("small", f"{c['email']}  -  {phone_s(c)}"), ("h", "Skills"),
                      ("p", "Route planning, customer escalations, QuickBooks, Excel, SAP Business One, OSHA 10"), ("h", "Experience")]
            for j in jobs_desc(c, c["jobs"]):
                s, e = daterange(c, j)
                blocks += [("right", f"{s} - {e}"), ("p", f"<b>{j['employer']}</b>  {j['title']}")]
            if L == "L5":
                blocks.append(("p", "Career break 2018 - 2019: full-time family caregiver."))
            blocks += [("h", "Education"), ("p", f"{c['edu'][0]}, {c['edu'][2]}")]
            write_pdf_document(os.path.join(F, f"{c['first']}-{c['last']}-resume.pdf"), blocks, font="Helvetica", base_size=10, pagesize="a4")

    mg = d["mgr"]
    write_text(os.path.join(ws, "note_from_hiring_manager.txt"),
        "Operations Coordinator applicants\n\n"
        "All the resumes that came in are in the resumes folder (one was a walk-in, I scanned it). Before I start calling people I want "
        "candidates.csv, one row per applicant, with:\n\n"
        "  email             their email address\n"
        "  full_name\n"
        "  phone             10 digits, nothing else\n"
        "  current_title     the job they're in now; blank if they're not working right now\n"
        "  current_employer  blank if they're not working right now\n"
        "  years_experience  years of work experience, one decimal\n\n"
        "For experience: count each calendar month someone was working once, including the start and end months (Mar 2019 to Jun 2021 is 28 months). "
        "Overlapping jobs don't count twice, gaps between jobs don't count, and school doesn't count. For a job that's still going, count through "
        "August 2026. Then divide the months by 12.\n\n"
        "If somebody sent us more than one resume, use the most recent one.\n\n"
        f"- {mg[0]}\n")

    header = ["email", "full_name", "phone", "current_title", "current_employer", "years_experience"]
    rows = [[c["email"], c["name"], c["phone"], c["cur_title"], c["cur_emp"], f"{c['years']:.1f}"] for c in C]
    write_csv(os.path.join(ref, "candidates.csv"), header, rows)
    write_csv(os.path.join(sol, "candidates.csv"), header, rows)
    by = {c["layout"]: c for c in C}
    write_json(os.path.join(ref, "notes.json"), {
        "duplicate": {"new_email": by["DUP"]["email"], "old_email": by["DUP"]["old"]["email"], "old_title": by["DUP"]["jobs"][1]["title"], "old_employer": by["DUP"]["jobs"][1]["employer"]},
        "not_employed": by["L3"]["email"], "gap_emails": [by["L5"]["email"], by["L5b"]["email"]], "overlap_email": by["L2"]["email"],
        "naive_years_first_start_to_asof": {c["email"]: round(c["naive_span"] / 12, 1) for c in C},
        "last_job": {by["L3"]["email"]: [by["L3"]["jobs"][2]["title"], by["L3"]["jobs"][2]["employer"]]}})
    keys = lambda *ls: [by[l]["email"] for l in ls]
    write_task_yaml(HERE, {
        "id": "cv-batch-extraction", "track": "desk", "category": "extraction",
        "title": "Applicant list from the operations coordinator resumes",
        "ask": "Please go through the resumes for the operations coordinator job and put the applicants into candidates.csv, one row per person. My note says what I need.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "phones come as (303) 555-0142, 303.555.0142, +1 (303) 555-0142, 303-555-0142, 3035550142 and 1-303-555-0142; the note wants 10 digits, so the +1 and 1- prefixes go (check: phones)",
            "ongoing jobs end in 'Present', 'Current', 'present' or 'to date'; they count through August 2026 and supply the current title and employer (checks: current roles; years of experience)",
            "two candidates have gaps, a career break of more than a year and eight months between jobs; counting from the first start date to August 2026 overstates both (check: years of experience)",
            "one candidate lists a part-time freelance role that overlaps a full-time job for three years; adding up job lengths counts those months twice (check: years of experience)",
            "one candidate's last contract ended in June 2026 (a chronological resume with school listed first); current title and employer are blank and the months stop at June 2026 (checks: current roles; years of experience)",
            "one applicant sent a March 2025 resume and a September 2026 resume with a different email and a newer job; one row, from the newer resume, and the old email must not appear (checks: one row per candidate; current roles)",
            "the month rule counts both end months, so subtracting dates or counting a job from Mar 2019 to Jun 2021 as 27 months moves most figures (check: years of experience)",
            "the walk-in resume is an image-only scan (checks: one row per candidate; current roles)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "candidates.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per candidate", "path": "candidates.csv", "column": "email", "ref": "candidates.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "candidates.csv", "equals_ref": "candidates.csv"},
            {"type": "csv_values_match", "name": "names", "path": "candidates.csv", "ref": "candidates.csv", "key": "email", "columns": ["full_name"], "normalize": ["alnum"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "phones", "path": "candidates.csv", "ref": "candidates.csv", "key": "email", "columns": ["phone"], "normalize": ["digits"], "min_accuracy": 1.0,
             "must_match_keys": keys("L5", "L5b", "DUP")},
            {"type": "csv_values_match", "name": "current roles", "path": "candidates.csv", "ref": "candidates.csv", "key": "email",
             "columns": ["current_title", "current_employer"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": keys("L3", "DUP", "L2", "L6")},
            {"type": "csv_values_match", "name": "years of experience", "path": "candidates.csv", "ref": "candidates.csv", "key": "email",
             "columns": ["years_experience"], "numeric": True, "tolerance": 0.05, "min_accuracy": 1.0, "must_match_keys": keys("L2", "L5", "L5b", "L3", "DUP")},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
