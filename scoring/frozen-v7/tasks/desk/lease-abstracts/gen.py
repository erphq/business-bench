#!/usr/bin/env python3
"""lease-abstracts: the leases for a six-suite retail plaza abstracted for the lender before a refinance.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * base rent is stated per month (101, 106, 108), per year payable monthly (102) and per rentable square foot per
    year (104, 110); the lender wants the monthly figure                                (check: rent in effect on 1 October 2026)
  * the rent in effect on 1 October 2026 is the starting rent rolled forward by every increase that has already
    happened; percent increases compound                                                (check: rent in effect on 1 October 2026)
  * fixed increases are written per rentable square foot per year (102), per year (110) and per month (106);
    the tracker wants the step in monthly rent                          (checks: escalation type; escalation amount)
  * 101 and 102 give a commencement date and a term but no expiration date; 101's lands on 29 February 2028
                                                                                        (check: lease dates)
  * notice windows are written as "no earlier than 12 months and no later than 6 months" and "no more than twelve
    months and no less than 270 days"; the deadline uses the shorter lead time, not the first number
                                                                                        (check: option notice deadline)
  * CAM caps read "104% of the prior year" (4) and "105%" (5), 104 has no cap and prints an 8.9% proportionate
    share that is not a cap                                             (check: option count and CAM cap)
  * the 2019 lease of the previous Suite 106 tenant, long expired, is in the folder     (checks: tenant names; expired lease left out)
  * the current Suite 106 lease summary is an image-only scan                           (checks: one row per suite; tenant names)
"""
from __future__ import annotations
import os, sys
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

CUTOFF = date(2026, 10, 1)
PLAZA = "Hawthorn Commons"
PLAZA_ADDR = "2150 Market St, Sacramento, CA 95814"
LANDLORD = "Hawthorn Commons Retail LLC"
LENDER = "Cascade Credit Union"
MANAGER = "Marisol Reyes"

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

def words(n: int) -> str:
    if n < 20: return ONES[n]
    if n < 100: return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    if n < 1000: return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + words(n % 100))
    return words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + words(n % 1000))

def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, d.day)

def month_end(y: int, m: int) -> date:
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))

def minus_months_month_end(d: date, n: int) -> date:
    """A month-end date moved back n months lands on that month's end; only used where both readings agree."""
    y, m = divmod(d.month - 1 - n, 12)
    out = month_end(d.year + y, m + 1)
    assert out.day == d.day, (d, n, out)
    return out

def long(d: date) -> str: return d.strftime("%B %-d, %Y")
def usd(x: float) -> str: return f"${x:,.2f}"

def increases_by(start: date, first_bump: date, cutoff: date) -> int:
    n, b = 0, first_bump
    while b <= cutoff:
        n += 1; b = date(b.year + 1, b.month, b.day)
    return n

def build(seed: int) -> dict:
    r = rng(seed)
    pool = [c for c in COMPANIES if "&" not in c[0] and c[2] in ("food", "clinic", "retail", "fitness", "services", "design", "print", "craft")]
    comps = pick(r, pool, 7)
    sfx = [", LLC", ", Inc.", " LLC", ", Inc.", ", LLC", " Inc.", ", LLC"]
    names = [c[0] + sfx[i] for i, c in enumerate(comps)]
    L = {}
    # 101: commencement + 60 months, no expiration printed (lands on 29 Feb 2028); monthly rent; 3% compounding
    s = date(2023, 3, 1); e = add_months(s, 60) - timedelta(days=1)
    base = float(r.choice([3200, 3450, 3700, 3950])); p = r.choice([3.0, 3.5])
    n = increases_by(s, date(2024, 3, 1), CUTOFF)
    L["101"] = dict(tenant=names[0], start=s, end=e, rsf=r.choice([1450, 1600, 1850]), base=base, esc_type="percent", esc=p,
                    rent=round(base * (1 + p / 100) ** n, 2), options=1, opt_years=5, notice=e - timedelta(days=180), cam=6.0)
    # 102: seven years, no expiration printed; annual rent payable monthly; +$0.50/RSF per year
    s = date(2021, 8, 1); e = add_months(s, 84) - timedelta(days=1)
    rsf = r.choice([1800, 2160, 2400]); annual = float(r.choice([48000, 51600, 57600]))
    step = round(0.50 * rsf / 12, 2); n = increases_by(s, date(2022, 8, 1), CUTOFF)
    L["102"] = dict(tenant=names[1], start=s, end=e, rsf=rsf, annual=annual, esc_type="fixed", esc=step,
                    rent=round(annual / 12 + n * step, 2), options=2, opt_years=3, notice=minus_months_month_end(e, 6), cam=4.0)
    # 104: per-RSF rates in a lease-year table, 3%; no options; no CAM cap
    s = date(2024, 5, 1); e = date(2031, 4, 30)
    rsf = r.choice([2250, 2500, 3000]); rate1 = r.choice([21.00, 22.00, 24.00])
    rates = [rate1]
    for _ in range(6):
        rates.append(round(rates[-1] * 1.03 + 1e-9, 2))
    ly = increases_by(s, date(2025, 5, 1), CUTOFF)  # index of the lease year in effect
    L["104"] = dict(tenant=names[2], start=s, end=e, rsf=rsf, rates=rates, share=8.9, esc_type="percent", esc=3.0,
                    rent=round(rates[ly] * rsf / 12, 2), options=0, opt_years=0, notice=None, cam=0.0)
    # 106: scanned summary; monthly rent; +$X per month each anniversary; 120 days' notice
    s = date(2025, 2, 1); e = date(2030, 1, 31)
    base = float(r.choice([2850, 3100, 3325])); step = float(r.choice([75, 90, 100]))
    n = increases_by(s, date(2026, 2, 1), CUTOFF)
    L["106"] = dict(tenant=names[3], start=s, end=e, rsf=r.choice([1200, 1350]), base=base, esc_type="fixed", esc=step,
                    rent=round(base + n * step, 2), options=1, opt_years=5, notice=e - timedelta(days=120), cam=4.5)
    # 108: expiration printed; 2.5%; notice "no more than twelve months and no less than 270 days"
    s = date(2022, 12, 1); e = date(2027, 11, 30)
    base = float(r.choice([5200, 5600, 6100])); n = increases_by(s, date(2023, 12, 1), CUTOFF)
    L["108"] = dict(tenant=names[4], start=s, end=e, rsf=r.choice([2800, 3100]), base=base, esc_type="percent", esc=2.5,
                    rent=round(base * 1.025 ** n, 2), options=1, opt_years=5, notice=e - timedelta(days=270), cam=3.0)
    # 110: anchor restaurant; per-RSF annual rent; +$X per year each June 1; 105% CAM; nine months' notice
    s = date(2020, 6, 1); e = date(2030, 5, 31)
    rsf = r.choice([4200, 4800, 5400]); rate = r.choice([18.00, 19.50, 20.00]); annual_step = float(r.choice([1800, 2400]))
    n = increases_by(s, date(2021, 6, 1), CUTOFF)
    L["110"] = dict(tenant=names[5], start=s, end=e, rsf=rsf, rate=rate, esc_type="fixed", esc=round(annual_step / 12, 2), annual_step=annual_step,
                    rent=round(rate * rsf / 12 + n * annual_step / 12, 2), options=3, opt_years=5, notice=minus_months_month_end(e, 9), cam=5.0)
    old = dict(tenant=names[6], start=date(2019, 11, 1), end=date(2024, 10, 31), base=float(r.choice([2400, 2550, 2700])))
    return dict(L=L, old=old)

def emit(seed: int) -> None:
    d = build(seed); L = d["L"]; old = d["old"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "leases"); os.makedirs(F, exist_ok=True)

    # ---- 101: Helvetica, basic provisions box first, clauses after
    a = L["101"]
    write_pdf_document(os.path.join(F, "Suite101_Lease_Basic_Provisions.pdf"), [
        ("title", "Retail Lease - Basic Lease Provisions"), ("small", f"{PLAZA}, {PLAZA_ADDR}"), ("hr", None),
        ("kv", [("Landlord", LANDLORD), ("Tenant", a["tenant"]), ("Premises", f"Suite 101, approximately {a['rsf']:,} rentable square feet"),
                ("Commencement Date", long(a["start"])), ("Term", "Sixty (60) months from the Commencement Date"),
                ("Monthly Base Rent", f"{usd(a['base'])} per month"), ("Security Deposit", usd(a["base"] * 2)),
                ("Permitted Use", "Retail sales and related services")]),
        ("spacer", 8),
        ("p", "<b>3. Rent Adjustments.</b> On each anniversary of the Commencement Date, Monthly Base Rent shall increase by "
              f"{words(int(a['esc'])) if a['esc'] == int(a['esc']) else 'three and one-half'} percent ({a['esc']:g}%) over the Monthly Base Rent in effect "
              "immediately before the adjustment."),
        ("spacer", 4),
        ("p", "<b>5. Common Area Maintenance.</b> Tenant shall pay its proportionate share of Operating Expenses monthly with Base Rent, provided that "
              "Tenant's share of Controllable Operating Expenses shall not increase by more than six percent (6%) in any Lease Year over the prior Lease Year."),
        ("spacer", 4),
        ("p", "<b>18. Option to Extend.</b> Provided Tenant is not in default, Tenant shall have one (1) option to extend the Term for five (5) years, "
              "exercisable by written notice given to Landlord not less than one hundred eighty (180) days prior to the expiration of the Term. "
              "Base Rent for the option term shall be ninety-five percent (95%) of fair market rent."),
        ("spacer", 10), ("small", "Initials: Landlord ____  Tenant ____          Page 1 of 1 (Basic Lease Provisions and selected sections)")],
        font="Helvetica", base_size=10)

    # ---- 102: Times-Roman prose articles, annual rent, per-RSF fixed step, two options with a window
    b = L["102"]
    write_pdf_document(os.path.join(F, "Lease_102_executed.pdf"), [
        ("title", "SHOPPING CENTER LEASE"), ("p", f"This Lease is made as of June 14, 2021 between {LANDLORD} (\"Landlord\") and {b['tenant'].upper()} (\"Tenant\")."),
        ("h", "ARTICLE 1. PREMISES AND TERM"),
        ("p", f"1.1 Landlord leases to Tenant Suite 102 of {PLAZA} containing approximately {b['rsf']:,} rentable square feet (the \"Premises\")."),
        ("p", "1.2 The term of this Lease shall be seven (7) years commencing on " + long(b["start"]) + " (the \"Commencement Date\")."),
        ("h", "ARTICLE 3. RENT"),
        ("p", f"3.1 Tenant shall pay annual base rent of {words(int(b['annual'])).title()} Dollars ({usd(b['annual'])}), payable in equal monthly "
              "installments in advance on the first day of each calendar month."),
        ("p", "3.2 On each anniversary of the Commencement Date, annual base rent shall increase by Fifty Cents ($0.50) per rentable square foot of the Premises."),
        ("p", "3.3 Rent not received by the fifth day of the month bears a late charge of five percent (5%) of the overdue amount."),
        ("h", "ARTICLE 6. OPERATING EXPENSES"),
        ("p", "6.4 Notwithstanding anything to the contrary, Tenant's share of Controllable CAM Charges for any Lease Year shall not exceed one hundred four "
              "percent (104%) of Tenant's share of Controllable CAM Charges for the preceding Lease Year."),
        ("h", "ARTICLE 22. RENEWAL"),
        ("p", "22.1 Tenant shall have two (2) successive options to renew the term for three (3) years each. Tenant shall exercise each option by written "
              "notice delivered to Landlord no earlier than twelve (12) months and no later than six (6) months prior to the expiration of the then-current term."),
        ("spacer", 12), ("p", f"LANDLORD: {LANDLORD}          TENANT: {b['tenant']}")],
        font="Times-Roman", base_size=11)

    # ---- 104: Courier on A4, rent schedule exhibit with a gridded table of per-RSF rates
    c = L["104"]
    rows = [["Lease Year", "Period", "Annual Base Rent per RSF"]]
    for i, rate in enumerate(c["rates"]):
        ps = date(c["start"].year + i, 5, 1); pe = date(c["start"].year + i + 1, 4, 30)
        rows.append([str(i + 1), f"{date_variant(ps, 1)} - {date_variant(pe, 1)}", f"${rate:,.2f}"])
    write_pdf_document(os.path.join(F, "104_rent_schedule_exhibit.pdf"), [
        ("title", "EXHIBIT C - RENT SCHEDULE"), ("small", f"Attached to the Lease dated March 18, 2024 - {PLAZA}"), ("hr", None),
        ("kv", [("Tenant", c["tenant"]), ("Premises", f"Suite 104 ({c['rsf']:,} RSF)"), ("Lease Commencement", date_variant(c["start"], 1)),
                ("Lease Expiration", date_variant(c["end"], 1)), ("Proportionate Share", f"{c['share']}%")]),
        ("spacer", 6),
        ("p", "Base Rent shall increase by three percent (3%) on the first day of each Lease Year after the first, as shown below. "
              "Monthly installments equal the annual rate multiplied by the rentable area of the Premises, divided by twelve."),
        ("spacer", 4),
        ("table", rows, {"grid": True, "shade_header": True, "col_widths": [70, 210, 150]}),
        ("spacer", 8),
        ("p", "Operating Expenses: Tenant pays its Proportionate Share of all Operating Expenses of the Center. There is no cap or limit on increases in Operating Expenses."),
        ("spacer", 4),
        ("p", "Renewal: None. Tenant has no option to extend or renew the Term.")],
        font="Courier", pagesize="a4", base_size=9)

    # ---- 106: image-only scan of the current lease summary
    dd = L["106"]
    write_scan_pdf(os.path.join(F, "scan_suite_106_lease_summary.pdf"), [
        f"{PLAZA.upper()} - LEASE SUMMARY", "", "SUITE: 106", f"TENANT: {dd['tenant']}", f"AREA: {dd['rsf']:,} RSF", "",
        f"LEASE START: {date_variant(dd['start'], 3)}", f"LEASE END:   {date_variant(dd['end'], 3)}", "",
        f"BASE RENT: {usd(dd['base'])} / month", f"INCREASES: +{usd(dd['esc'])} per month", "   on each lease anniversary", "",
        "CAM: pro rata share, increases", "   capped at 4.5% per year", "",
        "OPTIONS: one (1) renewal of 5 years", "NOTICE: at least 120 days before", "   lease end, in writing", "",
        "Summary prepared from executed lease", f"for {LENDER} file. - M.R."], font_size=31, seed=seed + 7, skew_deg=0.7, noise=650)

    # ---- 106 (old): the previous tenant's expired 2019 lease, Helvetica
    write_pdf_document(os.path.join(F, "Suite_106_Lease_2019.pdf"), [
        ("title", "Retail Lease"), ("small", f"{PLAZA}, {PLAZA_ADDR}"), ("hr", None),
        ("kv", [("Tenant", old["tenant"]), ("Premises", "Suite 106"), ("Commencement Date", long(old["start"])),
                ("Expiration Date", long(old["end"])), ("Monthly Base Rent", usd(old["base"])), ("Annual Increase", "Three percent (3%)")]),
        ("spacer", 6),
        ("p", "Option to Extend: one (1) option of five (5) years on not less than one hundred eighty (180) days' written notice prior to the Expiration Date."),
        ("p", "CAM: Tenant's share of controllable expenses shall not increase more than five percent (5%) per year.")], font="Helvetica", base_size=10)

    # ---- 108: Helvetica A4, riders before the basic terms
    e8 = L["108"]
    write_pdf_document(os.path.join(F, "Suite108_lease_riders.pdf"), [
        ("h", "RIDER 1 - OPTION TO EXTEND"),
        ("p", "Tenant shall have one (1) option to extend the Term for a period of five (5) years. To exercise the option Tenant shall give Landlord written "
              "notice no more than twelve (12) months and no less than two hundred seventy (270) days before the Expiration Date."),
        ("h", "RIDER 2 - COMMON AREA CHARGES"),
        ("p", "Increases in Tenant's share of controllable Common Area Charges are capped at three percent (3%) per calendar year, non-cumulative."),
        ("hr", None),
        ("title", "Lease - Basic Terms"),
        ("table", [["Item", "Term"], ["Premises", f"Suite 108, {PLAZA} ({e8['rsf']:,} RSF)"], ["Tenant", e8["tenant"]],
                   ["Commencement Date", date_variant(e8["start"], 2)], ["Expiration Date", date_variant(e8["end"], 2)],
                   ["Monthly Base Rent", f"{usd(e8['base'])}"],
                   ["Rent Increases", "Two and one-half percent (2.5%) on each anniversary of the Commencement Date"],
                   ["Security Deposit", usd(e8["base"])]], {"col_widths": [120, 330]})],
        font="Helvetica", pagesize="a4", base_size=10)

    # ---- 110: Times-Roman excerpt, per-RSF minimum rent with a fixed annual step
    f10 = L["110"]
    write_pdf_document(os.path.join(F, "Suite110_lease_excerpt.pdf"), [
        ("right", "EXCERPT - Sections 2, 4, 7 and 30"), ("title", f"Lease: {f10['tenant']}"), ("small", f"Suite 110, {PLAZA}"), ("spacer", 6),
        ("p", f"<b>Section 2.1 Term.</b> The Term begins {long(f10['start'])} and ends {long(f10['end'])}, unless extended as provided in Article 30."),
        ("spacer", 4),
        ("p", f"<b>Section 4.1 Minimum Rent.</b> Tenant shall pay Minimum Annual Rent at the rate of {usd(f10['rate'])} per rentable square foot per annum "
              f"on {f10['rsf']:,} rentable square feet, in twelve equal monthly installments."),
        ("p", f"<b>Section 4.2 Adjustment.</b> On June 1, 2021 and on each June 1 thereafter during the Term, Minimum Annual Rent shall increase by "
              f"{words(int(f10['annual_step'])).title()} Dollars ({usd(f10['annual_step'])})."),
        ("spacer", 4),
        ("p", "<b>Section 7.3 CAM Contribution.</b> Tenant's CAM contribution for any calendar year shall not exceed one hundred five percent (105%) "
              "of its CAM contribution for the prior calendar year."),
        ("spacer", 4),
        ("p", "<b>Article 30. Options.</b> Tenant shall have three (3) options to extend the Term for five (5) years each, each exercised by written notice "
              "given at least nine (9) months prior to the expiration of the then current Term.")],
        font="Times-Roman", base_size=11)

    write_text(os.path.join(ws, "note_from_marisol.txt"),
        f"Hi,\n\n{LENDER} wants a lease abstract for every tenant currently in {PLAZA} before the refinance closes. "
        "All the leases I could find are in the leases folder. Please put them in lease_abstracts.csv, one row per suite, with these columns:\n\n"
        "suite - the suite number only (101, not Suite 101)\n"
        "tenant - the tenant's legal name as written in the lease\n"
        "commencement_date, expiration_date - YYYY-MM-DD\n"
        "monthly_base_rent - base rent per month in effect on October 1, 2026, after any increases that have already happened\n"
        "escalation_type - percent or fixed\n"
        "escalation_amount - for percent increases the percent as a number (3.5 for 3.5%); for fixed increases the dollar amount "
        "monthly rent goes up by each time\n"
        "renewal_options - how many renewal options the tenant has (0 if none)\n"
        "notice_deadline - the last day the tenant can give notice to exercise its next renewal option, YYYY-MM-DD, blank if no options\n"
        "cam_cap_pct - the cap on yearly increases in CAM charges as a percent (4 for 4%), 0 if uncapped\n\n"
        f"Thanks,\n{MANAGER}\nRedwood Property Mgmt\n")

    header = ["suite", "tenant", "commencement_date", "expiration_date", "monthly_base_rent", "escalation_type", "escalation_amount",
              "renewal_options", "notice_deadline", "cam_cap_pct"]
    order = ["101", "102", "104", "106", "108", "110"]
    rows = []
    for k in order:
        v = L[k]
        rows.append([k, v["tenant"], v["start"].isoformat(), v["end"].isoformat(), f"{v['rent']:.2f}", v["esc_type"], f"{v['esc']:g}",
                     v["options"], v["notice"].isoformat() if v["notice"] else "", f"{v['cam']:g}"])
    write_csv(os.path.join(ref, "lease_abstracts.csv"), header, rows)
    write_csv(os.path.join(sol, "lease_abstracts.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {
        "cutoff": CUTOFF.isoformat(), "expired_tenant": old["tenant"],
        "starting_rent_naive": {"101": L["101"]["base"], "102": L["102"]["annual"], "104": L["104"]["rates"][0], "106": L["106"]["base"],
                                "108": L["108"]["base"], "110": L["110"]["rate"]},
        "naive_notice_first_number": {"102": add_months(L["102"]["end"], -12).isoformat(), "108": (L["108"]["end"] - timedelta(days=365)).isoformat()}})
    old_key = old["tenant"].split(",")[0].replace(" LLC", "").replace(" Inc.", "")
    write_task_yaml(HERE, {
        "id": "lease-abstracts", "track": "desk", "category": "extraction",
        "title": "Abstract the plaza leases for the lender",
        "ask": "The bank wants lease abstracts for everyone in the plaza before the refinance closes. Go through the leases folder and put them in "
               "lease_abstracts.csv - Marisol's note says what she needs.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "base rent is written per month (101, 106, 108), per year payable monthly (102) and per rentable square foot per year (104, 110); the note wants the monthly figure (check: rent in effect on 1 October 2026)",
            "rent must be rolled forward through every increase already taken by 1 October 2026 (five for 102, six for 110, three compounding percent steps for 101); copying the starting rent fails (check: rent in effect on 1 October 2026)",
            "fixed increases are written per rentable square foot per year (102: $0.50 x RSF / 12), per year (110: annual step / 12) and per month (106); the note wants the monthly step (checks: escalation type; escalation amount)",
            "101 and 102 print a commencement date and a term but no expiration date; expiration is commencement plus the term less one day, and 101's is 29 February 2028 (check: lease dates)",
            "the 102 window reads no earlier than twelve and no later than six months, and 108 reads no more than twelve months and no less than 270 days; the deadline uses the shorter lead time, not the first number (check: option notice deadline)",
            "CAM caps read 104% and 105% of the prior year (4 and 5), 104 has no cap and prints an 8.9% proportionate share that is not a cap (check: option count and CAM cap)",
            "the previous Suite 106 tenant's 2019 lease, expired in 2024, sits in the folder beside the current one (checks: tenant names; expired lease left out)",
            "the current Suite 106 lease summary is an image-only scan (checks: one row per suite; tenant names)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "lease_abstracts.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per suite", "path": "lease_abstracts.csv", "column": "suite", "ref": "lease_abstracts.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_values_match", "name": "tenant names", "path": "lease_abstracts.csv", "ref": "lease_abstracts.csv", "key": "suite",
             "columns": ["tenant"], "normalize": ["alnum"], "min_accuracy": 1.0, "must_match_keys": ["106"]},
            {"type": "csv_values_match", "name": "lease dates", "path": "lease_abstracts.csv", "ref": "lease_abstracts.csv", "key": "suite",
             "columns": ["commencement_date", "expiration_date"], "min_accuracy": 1.0, "must_match_keys": ["101", "102"]},
            {"type": "csv_values_match", "name": "rent in effect on 1 October 2026", "path": "lease_abstracts.csv", "ref": "lease_abstracts.csv", "key": "suite",
             "columns": ["monthly_base_rent"], "numeric": True, "tolerance": 1.0, "min_accuracy": 1.0, "must_match_keys": ["101", "102", "104", "110"]},
            {"type": "csv_values_match", "name": "escalation type", "path": "lease_abstracts.csv", "ref": "lease_abstracts.csv", "key": "suite",
             "columns": ["escalation_type"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "escalation amount", "path": "lease_abstracts.csv", "ref": "lease_abstracts.csv", "key": "suite",
             "columns": ["escalation_amount"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": ["102", "110"]},
            {"type": "csv_values_match", "name": "option count and CAM cap", "path": "lease_abstracts.csv", "ref": "lease_abstracts.csv", "key": "suite",
             "columns": ["renewal_options", "cam_cap_pct"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": ["102", "104", "110"]},
            {"type": "csv_values_match", "name": "option notice deadline", "path": "lease_abstracts.csv", "ref": "lease_abstracts.csv", "key": "suite",
             "columns": ["notice_deadline"], "min_accuracy": 1.0, "must_match_keys": ["101", "102", "108"]},
            {"type": "text_not_contains", "name": "expired lease left out", "path": "lease_abstracts.csv", "phrases": [old_key]},
        ],
    })

if __name__ == "__main__":
    emit(argparse_seed())
