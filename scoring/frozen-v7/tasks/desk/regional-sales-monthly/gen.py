#!/usr/bin/env python3
"""regional-sales-monthly: Q2 sales by territory for a dental-supply distributor, one export per month.

    python gen.py [--seed N] [--naive DIR]

Business: a dental and orthodontic supply distributor whose ERP is exported once a month, one file per
month, with an overlapping date range at each boundary. The prior-quarter file is still in the folder.

Traps (each caught by a check, see task.yaml):
  * each monthly export overlaps the previous month, so late orders are listed in two files (checks: Pacific May; Atlantic quarter)
  * the April file re-lists late-March orders, which belong to Q1                    (check: Atlantic quarter)
  * credit memos are negative amounts in parentheses, netted in their own month      (checks: Pacific May; quarter total)
  * two files end with a TOTAL line that a plain sum of the amount column swallows   (check: quarter total)
  * Mountain has no rows at all in the May file; the memo must say so                (checks: Mountain quarter; memo anomaly)
  * amounts are "$1,234.50" / "1,234.50 USD" text and the June export renamed its columns
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

TERRITORIES = ["Atlantic", "Gulf", "Great Lakes", "Mountain", "Pacific"]
MONTHS = ["2026-04", "2026-05", "2026-06"]
MONTH_DAYS = {3: 31, 4: 30, 5: 31, 6: 30}
GAP = ("Mountain", 5)          # territory with no rows at all in the May file
SENSITIVE = ("Pacific", 5)     # cell forced to carry a re-listed duplicate and a credit memo
N_CREDITS = 13
OVERLAP_FROM = {4: 3, 5: 4, 6: 5}   # each file re-lists the tail of the previous month


def mkey(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def build(seed: int) -> dict:
    r = rng(seed)
    customers = [c[0] for c in COMPANIES]
    orders = []
    seq = 40000
    for m in (3, 4, 5, 6):
        for t in TERRITORIES:
            if (t, m) == GAP:
                continue
            for _ in range(r.randint(24, 31)):
                seq += 1
                orders.append({"id": f"SO-{seq}", "date": date(2026, m, r.randint(1, MONTH_DAYS[m])),
                               "terr": t, "cust": r.choice(customers), "amt": money(r, 320, 9200), "k": r.random()})
    orders.sort(key=lambda o: (o["date"], o["k"]))

    # credit memos, issued in Q2, netted against the month they were issued in
    q2 = [o for o in orders if o["date"].month in (4, 5, 6) and 6 <= o["date"].day <= 22]
    forced = [o for o in q2 if o["terr"] == SENSITIVE[0] and o["date"].month == SENSITIVE[1] and o["amt"] > 5000]
    chosen = [r.choice(forced)] if forced else []
    for t in TERRITORIES:
        cands = [o for o in q2 if o["terr"] == t and o not in chosen and o["amt"] > 4000]
        if cands:
            chosen.append(r.choice(cands))
    while len(chosen) < N_CREDITS:
        c = r.choice([o for o in q2 if o not in chosen])
        chosen.append(c)
    credits = []
    for i, o in enumerate(chosen):
        credits.append({"id": f"CM-{7100 + i}", "date": o["date"], "terr": o["terr"], "cust": o["cust"],
                        "amt": -o["amt"], "ref": o["id"], "k": r.random()})

    # ---- truth: Q2 only, each order counted once, credits netted into their month ----
    net = {}
    for row in orders + credits:
        if row["date"].month not in (4, 5, 6):
            continue
        key = (row["terr"], mkey(row["date"]))
        net[key] = round(net.get(key, 0.0) + row["amt"], 2)
    totals = {t: round(sum(v for (tt, _), v in net.items() if tt == t), 2) for t in TERRITORIES}
    grand = round(sum(totals.values()), 2)
    month_tot = {m: round(sum(v for (_, mm), v in net.items() if mm == m), 2) for m in MONTHS}

    # ---- the four exported files ----
    files = {}
    for m in (3, 4, 5, 6):
        rows = []
        prev = OVERLAP_FROM.get(m)
        if prev:
            tail_start = MONTH_DAYS[prev] - 4
            rows += [o for o in orders if o["date"].month == prev and o["date"].day >= tail_start]
        rows += [o for o in orders if o["date"].month == m]
        rows += [c for c in credits if c["date"].month == m]
        rows.sort(key=lambda x: (x["date"], x["k"]))
        files[m] = rows
    return {"orders": orders, "credits": credits, "files": files, "net": net,
            "totals": totals, "grand": grand, "month_tot": month_tot}


def acceptable(d: dict) -> bool:
    """Every pinned figure has to move when the shortcut is taken."""
    net, totals, files = d["net"], d["totals"], d["files"]
    sens = (SENSITIVE[0], f"2026-{SENSITIVE[1]:02d}")
    if sens not in net:
        return False
    # duplicates re-listed from May into the June file, inside the sensitive cell
    dup_amt = sum(o["amt"] for o in files[6] if o["date"].month == 5 and o["terr"] == SENSITIVE[0])
    cred_amt = sum(-c["amt"] for c in d["credits"] if c["terr"] == SENSITIVE[0] and c["date"].month == SENSITIVE[1])
    if dup_amt < 0.02 * net[sens] or cred_amt < 0.02 * net[sens]:
        return False
    # no other cell on the sensitive row sits within 2% of it
    row_vals = [v for (t, _), v in net.items() if t == SENSITIVE[0]] + [totals[SENSITIVE[0]]]
    if sum(1 for v in row_vals if abs(v - net[sens]) <= 0.02 * net[sens]) > 1:
        return False
    for t in TERRITORIES:
        # re-listed March rows (Q1) that a file-is-the-month reading would count as April
        march_tail = sum(o["amt"] for o in files[4] if o["date"].month == 3 and o["terr"] == t)
        dups = sum(o["amt"] for f in (5, 6) for o in files[f] if o["date"].month == f - 1 and o["terr"] == t)
        creds = sum(-c["amt"] for c in d["credits"] if c["terr"] == t)
        if march_tail < 0.012 * totals[t] or dups < 0.012 * totals[t] or creds < 0.012 * totals[t]:
            return False
        if abs(totals[t] - net.get((t, "2026-04"), 0)) <= 0.02 * totals[t]:
            return False
    # the Mountain row must be visibly short a month
    if len([1 for (t, _) in net if t == GAP[0]]) != 2:
        return False
    return True


# --------------------------------------------------------------------------- deliverables

def report_sheets(data_rows: list[list]) -> dict:
    n = len(data_rows) + 1
    rows = []
    for i, t in enumerate(TERRITORIES, start=2):
        line = [t]
        for j, m in enumerate(MONTHS):
            c = chr(ord("B") + j)
            line.append(f'=IF(COUNTIFS(Data!$D$2:$D${n},$A{i},Data!$C$2:$C${n},{c}$1)=0,"no data",'
                        f'SUMIFS(Data!$E$2:$E${n},Data!$D$2:$D${n},$A{i},Data!$C$2:$C${n},{c}$1))')
        line.append(f"=SUM(B{i}:D{i})")
        rows.append(line)
    last = 1 + len(TERRITORIES)
    rows.append(["Total"] + [f"=SUM({c}2:{c}{last})" for c in "BCDE"])
    rows.append([])
    rows.append(["Mountain has no rows in the 2026-05 export - a gap in the file, not a month of zero sales."])
    return {
        "Data": {"header": ["doc_no", "doc_date", "month", "territory", "amount"], "rows": data_rows,
                 "widths": {"B": 12, "D": 14}},
        "Report": {"header": ["Territory"] + MONTHS + ["Total"], "rows": rows,
                   "widths": {"A": 14, "B": 14, "C": 14, "D": 14, "E": 14}},
    }


def clean_rows(d: dict) -> list[list]:
    seen, out = set(), []
    for row in sorted(d["orders"] + d["credits"], key=lambda x: (x["date"], x["id"])):
        if row["date"].month not in (4, 5, 6) or row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append([row["id"], row["date"].isoformat(), mkey(row["date"]), row["terr"], round(row["amt"], 2)])
    return out


def file_rows(rows: list[dict], style_amt, style_date) -> list[list]:
    return [[x["id"], date_variant(x["date"], style_date(x)), x["terr"], x["cust"], money_str(x["amt"], style_amt(x))]
            for x in rows]


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    net, totals = d["net"], d["totals"]

    def amt_style(x):
        return 5 if x["amt"] < 0 else [1, 0, 4][sum(ord(c) for c in x["id"]) % 3]

    def date_style(x):
        return [0, 1, 2][sum(ord(c) for c in x["id"]) % 3]

    hdr = ["Doc No", "Doc Date", "Territory", "Customer", "Amount"]
    for m, label, rng_text in ((3, "2026-03", "02/24/2026 - 03/31/2026"), (4, "2026-04", "03/27/2026 - 04/30/2026"),
                               (5, "2026-05", "04/26/2026 - 05/31/2026"), (6, "2026-06", "05/27/2026 - 06/30/2026")):
        rows = file_rows(d["files"][m], amt_style, date_style)
        if m in (4, 6):   # the ERP prints a total line at the end of these runs
            rows = rows + [["TOTAL", "", "", "", money_str(sum(x["amt"] for x in d["files"][m]), 1)]]
        if m == 6:        # the June run came out of the upgraded ERP with renamed columns
            write_csv(os.path.join(ws, f"sales_{label}.csv"),
                      ["Document", "Posting Date", "Sales Territory", "Customer Name", "Net Amount"], rows,
                      preamble=["Sales by territory (v2 export)", f"Range {rng_text}"], quote_all=True)
        else:
            write_csv(os.path.join(ws, f"sales_{label}.csv"), hdr, rows,
                      preamble=["Sales by territory", f"Range {rng_text}"], crlf=(m == 5), bom=(m == 4))
    write_text(os.path.join(ws, "note_from_ramona.txt"),
               "Quarterly territory numbers - what I need\n"
               "\n"
               "The board looks at April, May and June only. Last quarter's file is still in the folder because\n"
               "the reps were arguing about March; ignore it for this report.\n"
               "\n"
               "Sales are net of credit memos. A credit belongs to the month we issued it, not the month of the\n"
               "original order - that is how finance closes the books and how the board has always seen it.\n"
               "\n"
               "Put anything that looks wrong with the data in the memo. I would rather hear it from you than\n"
               "from Terrence in the meeting.\n"
               "\n"
               "- Ramona\n")

    # ---- reference ----
    write_csv(os.path.join(ref, "territory_month.csv"), ["territory", "month", "net_sales", "note"],
              [[t, m, f"{net[(t, m)]:.2f}" if (t, m) in net else "", "" if (t, m) in net else "no rows in the export (gap, not zero sales)"]
               for t in TERRITORIES for m in MONTHS])
    write_csv(os.path.join(ref, "territory_totals.csv"), ["territory", "net_sales"],
              [[t, f"{totals[t]:.2f}"] for t in TERRITORIES] + [["ALL", f"{d['grand']:.2f}"]])
    write_json(os.path.join(ref, "notes.json"), {
        "gap": {"territory": GAP[0], "month": f"2026-{GAP[1]:02d}"}, "credit_memos": len(d["credits"]),
        "credit_total": round(sum(c["amt"] for c in d["credits"] if c["date"].month in (4, 5, 6)), 2),
        "month_totals": d["month_tot"], "grand_total": d["grand"]})

    # ---- reference solution ----
    stable_xlsx(os.path.join(sol, "regional.xlsx"), report_sheets(clean_rows(d)), creator="reference")
    write_text(os.path.join(sol, "memo.md"), memo_text(d))

    write_task_yaml(HERE, {
        "id": "regional-sales-monthly", "track": "desk", "category": "reports",
        "title": "Q2 sales by territory from the monthly exports",
        "ask": ("Ramona needs the Q2 sales by territory - territories down the side, months across - from the monthly "
                "exports in this folder. Save it as regional.xlsx with live formulas, plus memo.md with what she "
                "should know. Her note says how she counts them.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "every monthly export overlaps the previous month by a few days, so the last orders of April are in both "
            "the April and May files and the last orders of May are in both the May and June files; each order counts "
            "once, in the month of its own date (checks: Pacific May; Atlantic quarter total)",
            "the April file opens with late-March orders, which belong to Q1 and are not April sales; reading the file "
            "name as the month counts them twice over (check: Atlantic quarter total)",
            f"{len(d['credits'])} credit memos (CM- ids) carry negative amounts written in parentheses and must be "
            "netted into the month they were issued, not dropped and not added as positives "
            "(checks: Pacific May; quarter total)",
            "the April and June exports end with a TOTAL line whose amount a plain sum of the column swallows, "
            "roughly doubling the quarter (check: quarter total)",
            f"{GAP[0]} has no rows at all in the 2026-05 export - a gap in the file, not a month of zero sales; its "
            "quarter total covers two months and the memo must say the month is missing "
            "(checks: Mountain quarter total; memo names the missing month)",
            "amounts are '$1,234.50', '1,234.50 USD' and plain text, dates come in three formats, the June export "
            "renamed every column and quotes every field, and two files carry a BOM or CRLF endings "
            "(check: quarter total, all territories)",
        ],
        "checks": [
            {"type": "file_exists", "name": "regional.xlsx exists", "path": "regional.xlsx"},
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "regional.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "regional.xlsx"},
            {"type": "xlsx_value_present", "name": "Atlantic quarter total", "path": "regional.xlsx",
             "expected": totals["Atlantic"], "rel_tol": cent_tol(totals["Atlantic"], 0.005), "near_text": "atlantic"},
            {"type": "xlsx_value_present", "name": "Mountain quarter total (two months, no invented May)", "path": "regional.xlsx",
             "expected": totals["Mountain"], "rel_tol": cent_tol(totals["Mountain"], 0.005), "near_text": "mountain"},
            {"type": "xlsx_value_present", "name": "Pacific May (duplicate rows and a credit memo)", "path": "regional.xlsx",
             "expected": net[(SENSITIVE[0], f"2026-{SENSITIVE[1]:02d}")], "rel_tol": cent_tol(net[(SENSITIVE[0], f"2026-{SENSITIVE[1]:02d}")], 0.005), "near_text": "pacific"},
            {"type": "xlsx_value_present", "name": "quarter total, all territories", "path": "regional.xlsx",
             "expected": d["grand"], "rel_tol": cent_tol(d["grand"], 0.005), "near_text": "total"},
            {"type": "text_numbers_present", "name": "memo carries the quarter and Mountain totals", "path": "memo.md",
             "numbers": [d["grand"], totals["Mountain"]], "rel_tol": 0.005},
            {"type": "text_sentence_matches", "name": "memo says Mountain is missing from the May export", "path": "memo.md",
             "all": [r"\bmountain\b", r"(\bmay\b|\b2026-05\b|\b05/2026\b)",
                     r"(\bno\b[^.;]{0,40}\b(rows|data|orders|sales|records|entries)\b|\bmissing\b|\bgap\b|\babsent\b|"
                     r"\bnot (in|present in|included in) the (export|file|data)\b|\bblank\b|\bempty\b)"],
             "none": [r"(rather than (a |an )?(missing|gap)|\bnot (a |an )?(missing|gap)\b|no evidence of (a |an )?(missing|gap))"]},
        ],
    })
    print(f"seed={seed} orders={len(d['orders'])} credits={len(d['credits'])} "
          f"file_rows={ {m: len(v) for m, v in d['files'].items()} }")
    print("territory totals:", {t: f"{v:.2f}" for t, v in totals.items()}, "grand:", d["grand"])
    print("sensitive:", SENSITIVE, net[(SENSITIVE[0], f"2026-{SENSITIVE[1]:02d}")])


def memo_text(d: dict) -> str:
    totals, net = d["totals"], d["net"]
    cred_total = round(sum(-c["amt"] for c in d["credits"] if c["date"].month in (4, 5, 6)), 2)
    best = max(TERRITORIES, key=lambda t: totals[t])
    return f"""# Q2 2026 net sales by territory

Net sales for April to June came to {d['grand']:,.2f} across the five territories. {best} was the strongest at
{totals[best]:,.2f}; monthly totals were {d['month_tot']['2026-04']:,.2f} in April, {d['month_tot']['2026-05']:,.2f}
in May and {d['month_tot']['2026-06']:,.2f} in June.

Three things to know before this goes to the board:

1. Mountain has no rows at all in the 2026-05 export - the month is missing from the file, not a month of zero
   sales. Its quarter total of {totals['Mountain']:,.2f} covers April and June only, and the May column shows
   "no data" rather than a zero. Please have May re-exported for that territory.
2. The monthly exports overlap at each boundary, so the last few days of one month are listed again at the top of
   the next file, and the April file starts with late-March orders that belong to Q1. Each order is counted once,
   in the month of its own date.
3. {len(d['credits'])} credit memos worth {cred_total:,.2f} are netted into the month they were issued. The April and
   June files also end with a TOTAL line, which is the export's own footer and is not a sale.

Pacific's May figure of {net[('Pacific', '2026-05')]:,.2f} is net of both of those corrections.
"""


def write_naive(d: dict, out: str) -> None:
    """The obvious shortcut: concatenate every file, treat the file name as the month,
    keep duplicate rows, read amounts as positive numbers, keep the TOTAL footer lines."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for m in (3, 4, 5, 6):
        label = f"2026-{m:02d}"
        for x in d["files"][m]:
            rows.append([x["id"], x["date"].isoformat(), label, x["terr"], round(abs(x["amt"]), 2)])
        if m in (4, 6):
            rows.append(["TOTAL", "", label, "", round(sum(abs(x["amt"]) for x in d["files"][m]), 2)])
    stable_xlsx(os.path.join(out, "regional.xlsx"), report_sheets(rows), creator="naive")
    write_text(os.path.join(out, "memo.md"),
               "# Q2 sales by territory\n\nAll five territories are reported for April, May and June. "
               "Sales rose through the quarter and the numbers come straight from the monthly exports.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None, help="write a deliberately naive solution to this directory instead")
    a = ap.parse_args()
    for attempt in range(300):
        d_ = build(a.seed * 1000 + attempt)
        if acceptable(d_):
            break
    else:
        raise SystemExit("no acceptable draw in 300 attempts")
    emit(a.seed * 1000 + attempt, a.naive)
