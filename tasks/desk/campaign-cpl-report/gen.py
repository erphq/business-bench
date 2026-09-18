#!/usr/bin/env python3
"""campaign-cpl-report: paid-media spend (finance xlsx) and CRM leads (csv) to cost per lead per channel.

    python gen.py [--seed N]

Traps (each caught by a check, see task.yaml):
  * channel names differ: the finance sheet says "Meta Ads", the CRM tags leads "facebook", "instagram",
    "fb / paid", "ig"; Dana's email carries the mapping                          (check: Meta cost per lead)
  * LinkedIn is billed in euros; the sheet's Currency column says EUR and the email gives the
    quarter's rate                                                                  (check: LinkedIn cost per lead)
  * the finance sheet has a "Subtotal <month>" line after every month block and a "Total Q2" line;
    a plain SUM of the Spend column doubles everything                             (check: Q2 spend total)
  * Direct Mail spent money and produced no tracked leads: it must appear with its spend and a cost per
    lead that is not a division error                                               (checks: Direct Mail spend; no error cells)
  * the CRM export runs from March into July and carries Spam and Test leads; only April-June real
    leads count                                                                     (check: total leads)
"""
from __future__ import annotations
import os, sys
from datetime import date, datetime, timedelta
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


MONTHS = [(2026, 4), (2026, 5), (2026, 6)]
MKEY = [f"{y}-{m:02d}" for y, m in MONTHS]
MNAME = {"2026-04": "April", "2026-05": "May", "2026-06": "June"}
EUR_RATE = 1.08
# finance name, currency, CRM source spellings, campaign names, monthly spend range, leads-per-$1000 range
CHANNELS = [
    ("Google Ads", "USD", ["google / cpc", "Google Ads", "adwords", "google"], ["Brand search", "AC repair - Portland", "Furnace tune-up", "Heat pump rebate"], (5200, 8800), (4.5, 6.5)),
    ("Meta Ads", "USD", ["facebook", "instagram", "fb / paid", "ig", "Facebook"], ["Summer AC promo", "Retargeting", "Lead form - IG"], (2400, 4600), (5.0, 8.0)),
    ("LinkedIn Ads", "EUR", ["linkedin", "LinkedIn Sponsored"], ["Property managers", "Commercial HVAC"], (1500, 2600), (2.0, 3.5)),
    ("Yelp Ads", "USD", ["yelp", "Yelp"], ["Yelp enhanced profile", "Yelp CPC"], (900, 1500), (6.0, 9.0)),
    ("Nextdoor", "USD", ["nextdoor", "Nextdoor local deal"], ["Neighborhood sponsorship"], (400, 900), (4.0, 7.0)),
    ("Direct Mail", "USD", [], ["Spring mailer - 8,000 pcs"], (0, 0), (0, 0)),
]
UNPAID = ["organic", "referral", "direct", "(none)", "word of mouth"]
STATUSES = ["New", "Contacted", "Quoted", "Won", "Lost", "Lost", "Contacted", "Quoted"]

def _r2(x): return round(x + 1e-9, 2)

def build(seed: int) -> dict:
    for attempt in range(200):
        r = rng(seed * 1000 + attempt)
        d = _draw(r)
        if _acceptable(d):
            return d
    raise SystemExit("no acceptable draw")

def _draw(r) -> dict:
    spend_rows = []          # (month_key, channel, campaign, currency, native_amount)
    truth_spend = {}         # (channel, month) -> usd
    for name, cur, _, camps, (lo, hi), _ in CHANNELS:
        for mk in MKEY:
            if name == "Direct Mail":
                if mk != "2026-05": continue
                amt = money(r, 3800, 5200); spend_rows.append((mk, name, camps[0], cur, amt))
                truth_spend[(name, mk)] = amt; continue
            month_total = money(r, lo, hi)
            camps_used = r.sample(camps, min(len(camps), r.randint(2, 3))) if len(camps) > 1 else camps
            # split month_total across campaigns
            weights = [r.uniform(0.5, 1.5) for _ in camps_used]
            parts = [_r2(month_total * w / sum(weights)) for w in weights]
            parts[-1] = _r2(month_total - sum(parts[:-1]))
            for c, p in zip(camps_used, parts):
                spend_rows.append((mk, name, c, cur, p))
            truth_spend[(name, mk)] = _r2(month_total * (EUR_RATE if cur == "EUR" else 1.0))
    # leads
    leads = []               # dict rows
    lid = 40210
    truth_leads = {name: 0 for name, *_ in CHANNELS}
    excluded = {name: 0 for name, *_ in CHANNELS}
    ig_count = 0
    for name, cur, sources, camps, _, (lpk_lo, lpk_hi) in CHANNELS:
        if not sources: continue
        for mk in MKEY:
            usd = truth_spend[(name, mk)]
            n = max(3, int(round(usd / 1000 * r.uniform(lpk_lo, lpk_hi))))
            y, m = int(mk[:4]), int(mk[5:])
            for _ in range(n):
                day = date(y, m, r.randint(1, 30 if m in (4, 6) else 31))
                src = r.choice(sources)
                if name == "Meta Ads" and src in ("instagram", "ig"): ig_count += 1
                leads.append(_lead(r, lid, day, src, camps, "real")); lid += 1
                truth_leads[name] += 1
        # excluded leads for this channel: at least 1 spam/test inside the quarter, at least 1 out of quarter
        for kind in ("spam", "test"):
            if r.random() < 0.7 or kind == "spam":
                day = day_in(r, date(2026, 4, 1), date(2026, 6, 30))
                leads.append(_lead(r, lid, day, r.choice(sources), camps, kind)); lid += 1; excluded[name] += 1
        for _ in range(r.randint(1, 4)):
            day = r.choice([day_in(r, date(2026, 3, 3), date(2026, 3, 31)), day_in(r, date(2026, 7, 1), date(2026, 7, 5))])
            leads.append(_lead(r, lid, day, r.choice(sources), camps, "real")); lid += 1; excluded[name] += 1
    # unpaid sources: real leads that are simply not paid channels
    for _ in range(r.randint(35, 55)):
        day = day_in(r, date(2026, 3, 3), date(2026, 7, 5))
        leads.append(_lead(r, lid, day, r.choice(UNPAID), ["-"], "real")); lid += 1
    leads.sort(key=lambda x: x["created"])
    for x in leads: x["lead_id"] = f"L-{x['lead_id']}"
    # instagram must matter for the Meta merge trap
    if ig_count < 3:
        return {"bad": True}
    q2 = {name: _r2(sum(v for (n, mk), v in truth_spend.items() if n == name)) for name, *_ in CHANNELS}
    cpl = {name: (_r2(q2[name] / truth_leads[name]) if truth_leads[name] else None) for name in q2}
    return {"spend_rows": spend_rows, "truth_spend": truth_spend, "truth_leads": truth_leads, "leads": leads, "q2": q2, "cpl": cpl,
            "excluded": excluded, "ig_count": ig_count}

def _lead(r, lid, day, src, camps, kind):
    f, l = person(r)
    created = datetime(day.year, day.month, day.day, r.randint(7, 20), r.randint(0, 59), r.randint(0, 59))
    if kind == "spam":
        f, l, status = r.choice(["SEO", "Crypto", "Backlinks", "Marketing"]), r.choice(["Services", "Team", "Pro", "Agency"]), "Spam"
    elif kind == "test":
        f, l, status = "Test", r.choice(["Lead", "Form", "Zap"]), "Test"
    else:
        status = r.choice(STATUSES)
    return {"lead_id": lid, "created": created, "name": f"{f} {l}", "email": email_for(r, f, l), "source": src, "campaign": r.choice(camps), "status": status}

def _acceptable(d) -> bool:
    if d.get("bad"): return False
    q2, leads, cpl = d["q2"], d["truth_leads"], d["cpl"]
    # naive variants must move each pinned figure by more than 1% (checks use 0.5%)
    def far(a, b): return abs(a - b) > 0.01 * abs(a)
    # LinkedIn not converted
    li_naive = _r2(q2["LinkedIn Ads"] / EUR_RATE / leads["LinkedIn Ads"])
    if not far(cpl["LinkedIn Ads"], li_naive): return False
    for name in ("Google Ads", "Meta Ads", "LinkedIn Ads"):
        if d["excluded"][name] < 2: return False
        naive_leads = leads[name] + d["excluded"][name]
        if not far(cpl[name], _r2(q2[name] / naive_leads)): return False
    meta_fb_only = leads["Meta Ads"] - d["ig_count"]
    if meta_fb_only <= 0 or not far(cpl["Meta Ads"], _r2(q2["Meta Ads"] / meta_fb_only)): return False
    # pinned values must be distinct from one another (row/column text sharing)
    # the finance sheet's own "Total Q2" line adds EUR to USD unconverted; copying it must not pass the spend check
    native_total = sum(x[4] for x in d["spend_rows"])
    if not far(sum(q2.values()), native_total): return False
    pins = [cpl["Google Ads"], cpl["Meta Ads"], cpl["LinkedIn Ads"], q2["Direct Mail"], sum(leads.values()), sum(q2.values())]
    for i, a in enumerate(pins):
        for b in pins[i + 1:]:
            if not far(a, b): return False
    return True

def emit(seed: int) -> None:
    d = build(seed)
    ws, ref, sol = task_dirs(HERE)
    # ---- workspace: finance spend sheet with month blocks, subtotals and a grand total
    rows = []
    for mk in MKEY:
        block = [x for x in d["spend_rows"] if x[0] == mk]
        for (m, ch, camp, cur, amt) in block:
            rows.append([MNAME[m] + " 2026", ch, camp, cur, amt])
        rows.append([f"Subtotal {MNAME[mk]}", "", "", "", _r2(sum(x[4] for x in block))])
        rows.append([])
    rows.append(["Total Q2", "", "", "", _r2(sum(x[4] for x in d["spend_rows"]))])
    write_xlsx(os.path.join(ws, "ad_spend_q2_2026.xlsx"), {"Q2 spend": {
        "merged_title": "Paid media spend - Q2 2026 (finance export, invoices booked)",
        "preamble": [["Prepared by: A. Okafor, AP", "", "", "", "Run 07/03/2026"], []],
        "header": ["Month", "Platform", "Campaign", "Currency", "Spend"], "rows": rows,
        "number_formats": {"E": "#,##0.00"}, "widths": {"A": 16, "B": 16, "C": 30, "E": 14}}}, creator="Finance")
    # ---- workspace: CRM leads export
    lrows = [[x["lead_id"], x["created"].strftime("%Y-%m-%d %H:%M:%S"), x["name"], x["email"], x["source"], x["campaign"], x["status"]] for x in d["leads"]]
    write_csv(os.path.join(ws, "crm_leads_export_2026-07-06.csv"), ["Lead ID", "Created At", "Name", "Email", "Source", "Campaign", "Status"], lrows,
              preamble=["Leads export - generated 07/06/2026 09:14 - filter: Created At after 03/01/2026", ""], crlf=True)
    # ---- workspace: the email with the rules
    write_email_thread(os.path.join(ws, "email_from_dana.txt"), [
        {"from": "Dana Whitfield <dana@pembertonhvac.com>", "to": "you", "date": "Mon, 6 Jul 2026 09:31", "subject": "Q2 cost per lead",
         "body": ("Can you put together cost per lead by channel for the second quarter (April through June)? Finance sent over the "
                  "paid media spend sheet and I exported the leads from the CRM this morning.\n\n"
                  "Report by the channel names finance uses. The CRM tags sources differently: google / cpc, adwords and google are "
                  "all Google Ads; facebook, fb / paid, instagram and ig are all Meta Ads (one line, we buy them together); linkedin "
                  "and LinkedIn Sponsored are LinkedIn Ads; yelp is Yelp Ads; nextdoor is Nextdoor. Organic, referral, direct and "
                  "word of mouth are not paid channels, leave them out of this.\n\n"
                  f"LinkedIn bills our Irish entity in euros. Finance books it at {EUR_RATE:.2f} US dollars per euro for the quarter, use that.\n\n"
                  "Leads marked Spam or Test are not leads. The Direct Mail line has no tracked leads, we did the spring mailer in May "
                  "and the phone number was never set up, but show it anyway so the spend is visible.")},
        {"from": "you", "to": "Dana Whitfield <dana@pembertonhvac.com>", "date": "Mon, 6 Jul 2026 09:40", "subject": "RE: Q2 cost per lead",
         "body": "Will do. Anything else you want on it?"},
        {"from": "Dana Whitfield <dana@pembertonhvac.com>", "to": "you", "date": "Mon, 6 Jul 2026 09:52", "subject": "RE: Q2 cost per lead",
         "body": "Spend per month and for the quarter, leads for the quarter, and cost per lead, one row per channel with a total line. "
                 "Keep the totals as formulas please, Marcus will change numbers in it."}])
    # ---- reference
    names = [c[0] for c in CHANNELS]
    write_csv(os.path.join(ref, "cpl.csv"), ["channel", "q2_spend_usd", "leads", "cost_per_lead"],
              [[n, f"{d['q2'][n]:.2f}", d["truth_leads"][n], "" if d["cpl"][n] is None else f"{d['cpl'][n]:.2f}"] for n in names])
    write_json(os.path.join(ref, "notes.json"), {"eur_rate": EUR_RATE, "spend_by_channel_month_usd": {f"{k[0]}|{k[1]}": v for k, v in d["truth_spend"].items()},
                                                  "excluded_leads_by_channel": d["excluded"], "instagram_leads": d["ig_count"],
                                                  "total_leads": sum(d["truth_leads"].values()), "total_spend_usd": _r2(sum(d["q2"].values()))})
    # ---- reference solution workbook: cleaned Spend and Leads sheets, Summary driven by formulas
    spend_data = []
    for (mk, ch, camp, cur, amt) in d["spend_rows"]:
        rate = EUR_RATE if cur == "EUR" else 1.0
        spend_data.append([mk, ch, camp, cur, amt, rate, _r2(amt * rate)])
    ns = len(spend_data) + 1
    lead_data = []
    src_map = {s.lower(): name for name, _, sources, *_ in CHANNELS for s in sources}
    for x in d["leads"]:
        mk = x["created"].strftime("%Y-%m")
        ch = src_map.get(x["source"].lower(), "")
        if mk in MKEY and ch and x["status"] not in ("Spam", "Test"):
            lead_data.append([x["lead_id"], x["created"].date(), mk, ch, x["status"]])
    nl = len(lead_data) + 1
    summary = []
    for i, n in enumerate(names, start=2):
        row = [n]
        for j, mk in enumerate(MKEY):
            L = "BCD"[j]
            row.append(f"=SUMIFS(Spend!$G$2:$G${ns},Spend!$B$2:$B${ns},$A{i},Spend!$A$2:$A${ns},{L}$1)")
        row.append(f"=ROUND(SUM(B{i}:D{i}),2)")
        row.append(f"=COUNTIF(Leads!$D$2:$D${nl},$A{i})")
        row.append(f'=IF(F{i}=0,"n/a",ROUND(E{i}/F{i},2))')
        summary.append(row)
    t = len(names) + 1
    summary.append(["Total"] + [f"=ROUND(SUM({L}2:{L}{t}),2)" for L in "BCDE"] + [f"=SUM(F2:F{t})", f'=IF(F{t+1}=0,"n/a",ROUND(E{t+1}/F{t+1},2))'])
    summary.append([])
    summary.append([f"Spend in USD; LinkedIn converted from EUR at {EUR_RATE:.2f}. Leads are CRM leads created April-June 2026 excluding Spam and Test. Direct Mail had no tracked leads."])
    write_xlsx(os.path.join(sol, "cpl.xlsx"), {
        "Summary": {"header": ["Channel"] + MKEY + ["Q2 spend (USD)", "Leads", "Cost per lead"], "rows": summary, "widths": {"A": 16, "E": 16, "G": 14}},
        "Spend": {"header": ["month", "channel", "campaign", "currency", "spend_native", "rate_to_usd", "spend_usd"], "rows": spend_data, "widths": {"C": 28}},
        "Leads": {"header": ["lead_id", "created", "month", "channel", "status"], "rows": lead_data}}, creator="reference")
    tot_leads = sum(d["truth_leads"].values()); tot_spend = _r2(sum(d["q2"].values()))
    write_task_yaml(HERE, {
        "id": "campaign-cpl-report", "track": "desk", "category": "reports",
        "title": "Cost per lead by channel for the quarter",
        "ask": "Work out our cost per lead by channel for the second quarter from the finance spend sheet and the CRM leads export. Dana's email has the details. Save it as cpl.xlsx.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the CRM tags sources differently from the finance sheet (facebook, instagram, fb / paid and ig are all Meta Ads; google / cpc, adwords and google are Google Ads); Dana's email carries the mapping and a naive join on the raw source loses the Instagram leads (check: Meta cost per lead)",
            f"LinkedIn is billed in euros: the finance sheet's Currency column says EUR and the email gives {EUR_RATE:.2f} USD per EUR; unconverted spend is off by 8% (check: LinkedIn cost per lead)",
            "the finance sheet has a Subtotal line after each month block and a Total Q2 line inside the data; a plain SUM of the Spend column doubles the quarter (check: Q2 spend total)",
            "Direct Mail spent money in May and has no tracked leads; it must stay on the report with its spend and a cost per lead that is not #DIV/0! (checks: Direct Mail spend; no error cells)",
            "the CRM export runs from March into July and carries Spam and Test leads, all in the same file; only real leads created April-June count (check: total leads)",
            "unpaid sources (organic, referral, direct, word of mouth) are in the CRM export and are not channels on the report (check: total leads)",
        ],
        "checks": [
            {"type": "file_exists", "name": "cpl.xlsx exists", "path": "cpl.xlsx"},
            {"type": "xlsx_has_formulas", "name": "totals are live formulas", "path": "cpl.xlsx", "min_count": 8},
            {"type": "xlsx_no_errors", "name": "no error cells (Direct Mail has zero leads)", "path": "cpl.xlsx"},
            {"type": "xlsx_value_present", "name": "Google Ads cost per lead", "path": "cpl.xlsx", "expected": d["cpl"]["Google Ads"], "rel_tol": cent_tol(d["cpl"]["Google Ads"], 0.005), "near_text": "google"},
            {"type": "xlsx_value_present", "name": "Meta cost per lead (facebook + instagram merged)", "path": "cpl.xlsx", "expected": d["cpl"]["Meta Ads"], "rel_tol": cent_tol(d["cpl"]["Meta Ads"], 0.005), "near_text": "meta"},
            {"type": "xlsx_value_present", "name": "LinkedIn cost per lead (EUR converted)", "path": "cpl.xlsx", "expected": d["cpl"]["LinkedIn Ads"], "rel_tol": 0.001, "rounding": f"LinkedIn spend converted from EUR at {EUR_RATE:.2f}", "near_text": "linkedin"},
            {"type": "xlsx_value_present", "name": "Direct Mail spend shown", "path": "cpl.xlsx", "expected": d["q2"]["Direct Mail"], "rel_tol": cent_tol(d["q2"]["Direct Mail"], 0.005), "near_text": "direct mail", "raw_value_ok": True},
            {"type": "xlsx_value_present", "name": "total leads (quarter only, no spam/test)", "path": "cpl.xlsx", "expected": tot_leads, "rel_tol": cent_tol(tot_leads, 0.001), "near_text": "total"},
            {"type": "xlsx_value_present", "name": "Q2 spend total (no subtotal double count)", "path": "cpl.xlsx", "expected": tot_spend, "rel_tol": 0.0001, "rounding": f"includes LinkedIn spend converted from EUR at {EUR_RATE:.2f}", "near_text": "total"},
        ],
    })
    print(f"seed={seed} spend_rows={len(d['spend_rows'])} leads={len(d['leads'])} q2={d['q2']} leads={d['truth_leads']} cpl={d['cpl']}")

if __name__ == "__main__":
    emit(argparse_seed())
