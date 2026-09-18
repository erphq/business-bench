#!/usr/bin/env python3
"""multi-currency-sales: first-half sales in dollars by month for a skincare maker selling in USD, EUR and GBP.

    python gen.py [--seed N] [--naive DIR]

Business: Fennwick Botanicals, a small-batch skincare maker in Asheville. It sells on its own US web store
(USD), through a European marketplace that pays out mid-month to mid-month (EUR, German number format), and
wholesale to UK stockists (GBP). The owner needs January to June in dollars for a loan application.

Traps (each caught by a check, see task.yaml):
  * marketplace statements run 16th to 15th and are labelled with the payout month; a sale is converted at the
    rate for the month it was made, and December and July sales ride in the first and last statements
    (checks: March total in dollars; EU marketplace H1 in dollars)
  * the marketplace export is semicolon-separated with German numbers ("1.234,56"); a plain number parse turns
    "45,90" into 4590                                                     (check: EU marketplace H1 in dollars)
  * the marketplace columns carry the item total and the payout after its fee; sales are the item total
                                                                           (check: EU marketplace H1 in dollars)
  * the April GBP average is missing from the rate sheet; the month is flagged and those pounds stay out of
    the dollar totals rather than borrowing March or May                  (checks: April flagged; H1 total)
  * the totals must be live formulas                                      (check: live formulas)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]
RATE_MONTHS = ["2025-12"] + MONTHS + ["2026-07"]
GAP_MONTH = "2026-04"          # GBP average missing
PIN_MONTH = "2026-03"
FEE_RATE = 0.12
ROUNDING = "currency conversion at monthly average rates, rounded to the cent per month"


def mkey(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def last_day(y: int, m: int) -> int:
    return ((date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)).day


def build(seed: int) -> dict:
    r = rng(seed)
    # ---- rates: USD per 1 EUR / GBP, monthly average ----
    eur, gbp, rates = 1.0 + r.uniform(0.07, 0.11), 1.0 + r.uniform(0.24, 0.30), {}
    for m in RATE_MONTHS:
        eur = round(eur * (1 + r.choice([-1, 1]) * r.uniform(0.012, 0.028)), 4)
        gbp = round(gbp * (1 + r.choice([-1, 1]) * r.uniform(0.010, 0.024)), 4)
        rates[m] = {"EUR": eur, "GBP": gbp}
    # ---- US web store ----
    us = []
    n = 1000 + r.randint(100, 900)
    for m in range(1, 7):
        for _ in range(r.randint(48, 72)):
            n += 1
            d = date(2026, m, r.randint(1, last_day(2026, m)))
            us.append({"id": f"#{n}", "dt": datetime(2026, m, d.day, r.randint(7, 22), r.randint(0, 59), r.randint(0, 59)),
                       "date": d, "amt": money(r, 24, 168)})
    us.sort(key=lambda x: x["dt"])
    for i, x in enumerate(us):
        x["id"] = f"#{n - len(us) + 1 + i}"
    # ---- EU marketplace: orders 16 Dec 2025 .. 15 Jul 2026 ----
    eu = []
    day = date(2025, 12, 16)
    k = 0
    while day <= date(2026, 7, 15):
        for _ in range(r.choice([0, 1, 1, 1, 2, 2])):
            k += 1
            amt = money(r, 1020, 1680) if r.random() < 0.035 else money(r, 19, 138)
            fee = round(amt * FEE_RATE + 0.30, 2)
            eu.append({"id": f"{r.randint(302, 306)}-{r.randint(1000000, 9999999)}-{r.randint(1000000, 9999999)}",
                       "date": day, "amt": amt, "fee": fee, "payout": round(amt - fee, 2),
                       "country": r.choice(["DE", "DE", "DE", "AT", "NL", "FR", "BE", "IE"])})
        day += timedelta(days=1)
    for x in eu:
        pay_m = x["date"].month if x["date"].day <= 15 else x["date"].month % 12 + 1
        pay_y = x["date"].year + (1 if x["date"].month == 12 and x["date"].day > 15 else 0)
        x["statement"] = f"{pay_y}-{pay_m:02d}"
    # ---- UK stockists ----
    stockists = ["Bramble & Birch, Bath", "The Apothecary Shelf, York", "Fern House, Brighton", "Wildflower Lane, Harrogate",
                 "Lark Rise Pharmacy, Oxford", "Seven Dials Beauty, London", "Hollin Hill Gifts, Keswick"]
    uk = []
    inv = r.randint(210, 260)
    for m in range(1, 7):
        for _ in range(r.randint(5, 9)):
            inv += 1
            uk.append({"id": f"FB-UK-{inv}", "date": date(2026, m, r.randint(1, last_day(2026, m))),
                       "stockist": r.choice(stockists), "amt": money(r, 280, 2350)})
    uk.sort(key=lambda x: (x["date"], x["id"]))
    for i, x in enumerate(uk):
        x["id"] = f"FB-UK-{inv - len(uk) + 1 + i}"

    # ---- truth ----
    native = {(m, c): 0.0 for m in MONTHS for c in ("USD", "EUR", "GBP")}
    for x in us:
        native[(mkey(x["date"]), "USD")] += x["amt"]
    for x in eu:
        if mkey(x["date"]) in MONTHS:
            native[(mkey(x["date"]), "EUR")] += x["amt"]
    for x in uk:
        native[(mkey(x["date"]), "GBP")] += x["amt"]
    native = {k: round(v, 2) for k, v in native.items()}
    usd = {}
    for m in MONTHS:
        usd[(m, "USD")] = native[(m, "USD")]
        usd[(m, "EUR")] = round(native[(m, "EUR")] * rates[m]["EUR"], 2)
        usd[(m, "GBP")] = None if m == GAP_MONTH else round(native[(m, "GBP")] * rates[m]["GBP"], 2)
    month_total = {m: round(sum(v for (mm, _), v in usd.items() if mm == m and v is not None), 2) for m in MONTHS}
    h1 = {c: round(sum(usd[(m, c)] for m in MONTHS if usd[(m, c)] is not None), 2) for c in ("USD", "EUR", "GBP")}
    grand = round(sum(month_total.values()), 2)
    return {"rates": rates, "us": us, "eu": eu, "uk": uk, "native": native, "usd": usd, "month_total": month_total,
            "h1": h1, "grand": grand}


def naive_figures(d: dict) -> dict:
    """What the shortcuts produce: statement month for EU sales, statement-month rate, borrowed GBP rate."""
    rates = d["rates"]
    by_stmt = {}
    for x in d["eu"]:
        if x["statement"] in MONTHS:
            by_stmt[x["statement"]] = by_stmt.get(x["statement"], 0.0) + x["amt"]
    eu_stmt = {m: round(by_stmt.get(m, 0.0) * rates[m]["EUR"], 2) for m in MONTHS}
    # sale month, but the statement month's rate
    eu_rate_only = {m: 0.0 for m in MONTHS}
    for x in d["eu"]:
        if mkey(x["date"]) in MONTHS:
            eu_rate_only[mkey(x["date"])] += x["amt"] * rates[x["statement"]]["EUR"]
    gbp_apr = d["native"][(GAP_MONTH, "GBP")]
    borrowed = [round(gbp_apr * rates[m]["GBP"], 2) for m in ("2026-03", "2026-05")]
    # a lookup by position: every month takes the previous month's rates
    prev = RATE_MONTHS[RATE_MONTHS.index(PIN_MONTH) - 1]
    shifted = round(d["native"][(PIN_MONTH, "USD")] + d["native"][(PIN_MONTH, "EUR")] * rates[prev]["EUR"]
                    + d["native"][(PIN_MONTH, "GBP")] * rates[prev]["GBP"], 2)
    return {"eu_stmt": eu_stmt, "eu_rate_only": eu_rate_only, "borrowed": borrowed, "shifted": shifted}


def acceptable(d: dict) -> bool:
    nv = naive_figures(d)
    tol_m = d["month_total"][PIN_MONTH] * 0.0005
    # March moves under statement-month bucketing and under statement-month rates alone
    if abs(nv["eu_stmt"][PIN_MONTH] - d["usd"][(PIN_MONTH, "EUR")]) < 20 * tol_m:
        return False
    if abs(nv["eu_rate_only"][PIN_MONTH] - d["usd"][(PIN_MONTH, "EUR")]) < 4 * tol_m:
        return False
    # H1 EUR moves under the rate-only shortcut too
    if abs(sum(nv["eu_rate_only"].values()) - d["h1"]["EUR"]) < 4 * d["h1"]["EUR"] * 0.0005:
        return False
    # the borrowed rates differ from each other and from any real figure
    b = nv["borrowed"]
    if abs(b[0] - b[1]) < 20:
        return False
    if abs(nv["shifted"] - d["month_total"][PIN_MONTH]) < 4 * tol_m:
        return False
    real = [v for v in d["usd"].values() if v is not None] + list(d["native"].values()) + list(d["month_total"].values())
    if any(abs(x - y) < 1 for x in b for y in real):
        return False
    # at least a few marketplace sales cross 1.000 EUR in the half year
    if sum(1 for x in d["eu"] if x["amt"] >= 1000 and mkey(x["date"]) in MONTHS) < 3:
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def workbook(sales_rows: list[list], rate_rows: list[list]) -> dict:
    n = len(sales_rows) + 1
    nr = len(rate_rows) + 1
    S = lambda c: f"Sales!${c}$2:${c}${n}"
    rows = []
    for i, m in enumerate(MONTHS, start=2):
        miss = f'COUNTIFS(Rates!$A$2:$A${nr},$A{i},Rates!$C$2:$C${nr},">0")=0'
        rows.append([
            m,
            f'=ROUND(SUMIFS({S("E")},{S("D")},$A{i},{S("B")},"USD"),2)',
            f'=ROUND(SUMIFS({S("E")},{S("D")},$A{i},{S("B")},"EUR"),2)',
            f"=ROUND(C{i}*VLOOKUP($A{i},Rates!$A$2:$C${nr},2,FALSE),2)",
            f'=ROUND(SUMIFS({S("E")},{S("D")},$A{i},{S("B")},"GBP"),2)',
            f'=IF({miss},"rate missing",ROUND(E{i}*VLOOKUP($A{i},Rates!$A$2:$C${nr},3,FALSE),2))',
            f"=SUM(B{i},D{i},F{i})",
            f'=IF({miss},"GBP average rate missing for this month - pounds not converted and not in the total","")',
        ])
    last = 1 + len(MONTHS)
    rows.append(["H1 total"] + [f"=SUM({c}2:{c}{last})" for c in "BCDEFG"] + [""])
    return {
        "Summary": {"header": ["Month", "US web store (USD)", "EU marketplace (EUR)", "EU marketplace (USD)",
                               "UK stockists (GBP)", "UK stockists (USD)", "Total (USD)", "Flag"],
                    "rows": rows, "widths": {"A": 10, "B": 18, "C": 20, "D": 20, "E": 18, "F": 18, "G": 14, "H": 60}},
        "Sales": {"header": ["reference", "currency", "sale date", "month", "amount"], "rows": sales_rows,
                  "widths": {"A": 26, "C": 12}},
        "Rates": {"header": ["month", "USD per EUR", "USD per GBP"], "rows": rate_rows},
    }


def clean_sales(d: dict) -> list[list]:
    out = [[x["id"], "USD", x["date"].isoformat(), mkey(x["date"]), x["amt"]] for x in d["us"]]
    out += [[x["id"], "EUR", x["date"].isoformat(), mkey(x["date"]), x["amt"]] for x in d["eu"] if mkey(x["date"]) in MONTHS]
    out += [[x["id"], "GBP", x["date"].isoformat(), mkey(x["date"]), x["amt"]] for x in d["uk"]]
    return out


def clean_rates(d: dict) -> list[list]:
    return [[m, d["rates"][m]["EUR"], None if m == GAP_MONTH else d["rates"][m]["GBP"]] for m in MONTHS]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    rates = d["rates"]

    # ---- workspace ----
    write_csv(os.path.join(ws, "us_webstore_orders_2026-01-01_to_2026-06-30.csv"),
              ["Name", "Created at", "Financial Status", "Currency", "Total"],
              [[x["id"], x["dt"].strftime("%Y-%m-%d %H:%M:%S ") + ("-0400" if x["dt"] >= datetime(2026, 3, 8, 2) else "-0500"), "paid", "USD", f"{x['amt']:.2f}"] for x in d["us"]])
    eu_rows = []
    for x in sorted(d["eu"], key=lambda x: (x["statement"], x["date"], x["id"])):
        y, mm = int(x["statement"][:4]), int(x["statement"][5:])
        start = date(y - (mm == 1), (mm - 2) % 12 + 1, 16)
        end = date(y, mm, 15)
        eu_rows.append([x["statement"], f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}", x["date"].strftime("%d.%m.%Y"),
                        x["id"], x["country"], eu_money_str(x["amt"]), eu_money_str(-x["fee"]), eu_money_str(x["payout"])])
    write_csv(os.path.join(ws, "eu_marketplace_statements_2026.csv"),
              ["Statement", "Settlement period", "Order date", "Order no.", "Ship country", "Item total (EUR)",
               "Marketplace fee (EUR)", "Payout (EUR)"], eu_rows, delimiter=";", bom=True, crlf=True)
    write_xlsx(os.path.join(ws, "uk_stockist_invoices_2026H1.xlsx"), {"Invoices": {
        "merged_title": "UK wholesale invoices - January to June 2026 (GBP)",
        "header": ["Invoice", "Invoice date", "Stockist", "Net (GBP)", "Paid"],
        "rows": [[x["id"], x["date"], x["stockist"], x["amt"], "Yes"] for x in d["uk"]],
        "number_formats": {"D": "#,##0.00"}, "widths": {"A": 12, "B": 13, "C": 30, "D": 12}}}, creator="Fennwick Botanicals")
    rate_rows = []
    for m in RATE_MONTHS:
        g = None if m == GAP_MONTH else rates[m]["GBP"]
        note = "GBP not on the bank's April sheet - chasing" if m == GAP_MONTH else ""
        rate_rows.append([m, rates[m]["EUR"], g, note])
    write_xlsx(os.path.join(ws, "fx_monthly_average_rates.xlsx"), {"Monthly average": {
        "preamble": [["Monthly average rates from the bank's FX sheet (USD for one unit of currency)"]],
        "header": ["Month", "USD per 1 EUR", "USD per 1 GBP", "Notes"], "rows": rate_rows,
        "widths": {"A": 10, "B": 14, "C": 14, "D": 44}}}, creator="Beatrix Mensah")
    write_text(os.path.join(ws, "note_from_claire.txt"),
               "Beatrix - first-half sales in dollars for the loan application\n"
               "\n"
               "The bank wants January to June 2026 sales in US dollars, month by month, across all three places we\n"
               "sell: the US web store, the EU marketplace and the UK stockists. Here is how I want it done so it\n"
               "matches what I told the loan officer:\n"
               "\n"
               "- Use your monthly average rates, and convert each sale at the rate for the month the sale was made.\n"
               "  The marketplace pays us out mid-month to mid-month and names each statement after the month it\n"
               "  pays, so a statement month is not the month the sales happened.\n"
               "- Marketplace sales are the item totals customers paid, before the marketplace takes its fee.\n"
               "- That export comes out of their German office, so the numbers are written 1.234,56.\n"
               "- Rounding: add up each month's euros and each month's pounds, convert the month total at that\n"
               "  month's rate, and round the dollar figure to the cent.\n"
               "- If a rate is missing for a month, do not borrow another month's rate. Leave those sales\n"
               "  unconverted, keep them out of the dollar totals, and flag the month so I can fill it in later.\n"
               "\n"
               "One line per month, 2026-01 to 2026-06, with the dollars from each of the three channels and a total\n"
               "for the month, and a half-year total underneath. Keep the totals as formulas please - the bank\n"
               "sometimes asks us to change things.\n"
               "\n"
               "Claire\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "month_usd.csv"), ["month", "usd_store", "eur_native", "eur_usd", "gbp_native", "gbp_usd", "total_usd", "flag"],
              [[m, f"{d['usd'][(m, 'USD')]:.2f}", f"{d['native'][(m, 'EUR')]:.2f}", f"{d['usd'][(m, 'EUR')]:.2f}",
                f"{d['native'][(m, 'GBP')]:.2f}", "" if d["usd"][(m, "GBP")] is None else f"{d['usd'][(m, 'GBP')]:.2f}",
                f"{d['month_total'][m]:.2f}", "GBP rate missing" if m == GAP_MONTH else ""] for m in MONTHS]
              + [["H1", f"{d['h1']['USD']:.2f}", "", f"{d['h1']['EUR']:.2f}", "", f"{d['h1']['GBP']:.2f}", f"{d['grand']:.2f}", ""]])
    nv = naive_figures(d)
    write_json(os.path.join(ref, "notes.json"), {
        "gap_month": GAP_MONTH, "gap_currency": "GBP", "gbp_native_gap_month": d["native"][(GAP_MONTH, "GBP")],
        "borrowed_rate_figures": nv["borrowed"], "pin_month": PIN_MONTH, "rates": rates,
        "eu_statement_month_figures": nv["eu_stmt"]})

    # ---- reference solution ----
    write_xlsx(os.path.join(sol, "sales_usd.xlsx"), workbook(clean_sales(d), clean_rates(d)), creator="reference")

    mt = d["month_total"]
    write_task_yaml(HERE, {
        "id": "multi-currency-sales", "track": "desk", "category": "spreadsheet",
        "title": "First-half sales in dollars across three currencies",
        "ask": ("The bank wants our January to June sales in dollars, month by month, from the three sales files in "
                "this folder. Save it as sales_usd.xlsx with live totals - my note to Beatrix says how to convert.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "the marketplace statements run from the 16th to the 15th and are named for the payout month, so a "
            "statement month is not the sale month; converting or bucketing by statement moves every month's euros, "
            "and the first and last statements carry December 2025 and July 2026 sales (checks: March total in dollars; EU "
            "marketplace H1 in dollars)",
            "the marketplace export is semicolon-separated with German numbers ('1.234,56', '45,90'); stripping "
            "everything but digits and dots reads 45,90 as 4590 and 1.234,56 as 1.23456 (check: EU marketplace H1 "
            "in dollars)",
            "the marketplace rows carry the item total, a negative fee and the payout; sales are the item total, "
            "so summing payouts understates the euros by about 12% (check: EU marketplace H1 in dollars)",
            f"the April GBP average is blank on the rate sheet; the note forbids borrowing March or May, so April's "
            "pounds stay unconverted, out of the dollar totals, and the month is flagged "
            "(checks: April flagged, no borrowed rate; H1 total in dollars)",
            "the rate sheet has a one-line preamble and also lists December 2025 and July 2026, which a lookup by "
            "position rather than by month misaligns (check: March total in dollars)",
            "the month and half-year totals must be live formulas that recalculate clean (checks: live formulas; "
            "no error cells)",
        ],
        "checks": [
            {"type": "file_exists", "name": "sales_usd.xlsx exists", "path": "sales_usd.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "sales_usd.xlsx", "min_count": 7},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "sales_usd.xlsx"},
            {"type": "xlsx_value_present", "name": "March total in dollars", "path": "sales_usd.xlsx",
             "expected": mt[PIN_MONTH], "rel_tol": 0.0005, "rounding": ROUNDING, "near_text": PIN_MONTH},
            {"type": "xlsx_value_present", "name": "EU marketplace H1 in dollars", "path": "sales_usd.xlsx",
             "expected": d["h1"]["EUR"], "rel_tol": 0.0002, "rounding": ROUNDING, "near_text": "eu"},
            {"type": "xlsx_value_present", "name": "H1 total in dollars", "path": "sales_usd.xlsx",
             "expected": d["grand"], "rel_tol": 0.0001, "rounding": ROUNDING, "near_text": "total"},
            {"type": "custom", "name": "April flagged, no borrowed rate", "module": "check.py"},
        ],
    })
    print(f"seed={seed} us={len(d['us'])} eu={len(d['eu'])} uk={len(d['uk'])}")
    print("month totals:", mt, "H1:", d["h1"], "grand:", d["grand"])
    print("naive:", nv["borrowed"], nv["eu_stmt"][PIN_MONTH], round(nv["eu_rate_only"][PIN_MONTH], 2), d["usd"][(PIN_MONTH, "EUR")])


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcuts: bucket and convert marketplace sales by statement month, keep December and July
    statement rows that land in the first and last statements, and borrow March's GBP rate for April."""
    os.makedirs(out, exist_ok=True)
    sales = [[x["id"], "USD", x["date"].isoformat(), mkey(x["date"]), x["amt"]] for x in d["us"]]
    sales += [[x["id"], "EUR", x["date"].isoformat(), x["statement"], x["amt"]] for x in d["eu"] if x["statement"] in MONTHS]
    sales += [[x["id"], "GBP", x["date"].isoformat(), mkey(x["date"]), x["amt"]] for x in d["uk"]]
    rates = [[m, d["rates"][m]["EUR"], d["rates"]["2026-03"]["GBP"] if m == GAP_MONTH else d["rates"][m]["GBP"]] for m in MONTHS]
    write_xlsx(os.path.join(out, "sales_usd.xlsx"), workbook(sales, rates), creator="naive")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 400 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
