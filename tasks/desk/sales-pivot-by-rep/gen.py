#!/usr/bin/env python3
"""sales-pivot-by-rep: a brewery's invoice-line export into reps down the side, January to June across.

    python gen.py [--seed N] [--naive DIR]

Business: a craft brewery that self-distributes kegs and cases to bars, restaurants and bottle shops with
six field reps. The brewery system exports invoice lines; the order desk types the rep name by hand.

Traps (each caught by a check, see task.yaml):
  * one rep is typed four ways (Dana Cruz, D. Cruz, Cruz, Dana, DANA CRUZ) and another two ways; a
    group-by on the raw column splits them                                (checks: Cruz H1 total; Walker H1 total)
  * credit memos are exported with a trailing minus ("182.00-"); stripping to digits books them as sales,
    a strict number parse drops them                                        (checks: Walker sensitive month; H1 total)
  * keg deposit and deposit-return lines are pass-through money, not sales (the note)  (checks: sensitive month; H1 total)
  * one rep was on leave in April and has no rows; her April cell must read 0, not blank (check: April zero)
  * totals across and down must be live formulas                           (check: live formulas)
  * the export has a two-line preamble and text amounts with thousands separators; last half-year's
    report sits beside it with a rep who has since left                    (check: H1 total)
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


MONTHS = [f"2026-{m:02d}" for m in range(1, 7)]
MONTH_DAYS = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30}
BEERS = ["Tamarack IPA", "Lakeshore Pilsner", "Ridgeline Amber", "Hazy Hollow", "Stout No. 9", "Cedar Sour"]
PACKS = [("1/2 bbl keg", 165.0, 212.0, True), ("1/6 bbl keg", 72.0, 96.0, True), ("case 24x12oz cans", 38.0, 56.0, False)]
MERCH = [("Pint glasses (dozen)", 54.0), ("Tap handle", 42.0), ("Coasters (500)", 36.0)]
DEPOSIT = 30.0
BAR_WORDS = ["Tavern", "Taproom", "Bistro", "Bottle Shop", "Grill", "Pub", "Kitchen", "Social Club", "Market", "Alehouse"]
BAR_FIRST = ["Copper", "Old Mill", "Fox & Hound", "Harbor", "Juniper", "Ironwood", "Lantern", "Magnolia", "North End", "Pine Knot",
             "Red Door", "Saltbox", "Thistle", "Union", "Willow", "Anchor", "Birchwood", "Crow's Nest", "Driftwood", "Elm Street"]

LEAVE_MONTH = "2026-04"


def build(seed: int) -> dict:
    r = rng(seed)
    reps = []
    while len(reps) < 6:
        f, l = person(r)
        if l in {x[1] for x in reps} or f[0] in {x[0][0] for x in reps} or l in ("Cruz", "Walker", "Patel"):
            continue
        reps.append((f, l))
    # the three trap roles keep fixed names so the checks' labels read naturally; the other three re-roll
    reps[0] = ("Dana", "Cruz")          # four spellings
    reps[1] = ("Christopher", "Walker")  # two spellings, sensitive month
    reps[2] = ("Priya", "Patel")         # on leave in April
    names = [f"{f} {l}" for f, l in reps]
    spell = {
        names[0]: ["Dana Cruz", "D. Cruz", "Cruz, Dana", "DANA CRUZ"],
        names[1]: ["Christopher Walker", "Walker, Christopher"],
    }
    accounts = {n: [f"{a} {b}" for a, b in zip(r.sample(BAR_FIRST, 6), [r.choice(BAR_WORDS) for _ in range(6)])] for n in names}
    lines = []   # truth rows: {doc, date, rep, typed, account, item, qty, amount, kind}
    seq = 26000
    for mi, m in enumerate(MONTHS, start=1):
        for ri, n in enumerate(names):
            if n == names[2] and m == LEAVE_MONTH:
                continue
            for _ in range(r.randint(9, 14)):
                seq += 1
                d = date(2026, mi, r.randint(1, MONTH_DAYS[mi]))
                acct = r.choice(accounts[n])
                doc = f"INV-{seq}"
                k = r.random()
                n_lines = r.randint(1, 3)
                for _li in range(n_lines):
                    if r.random() < 0.08:
                        item, price = r.choice(MERCH)
                        qty = r.randint(1, 3)
                        lines.append({"doc": doc, "type": "INV", "date": d, "rep": n, "account": acct, "item": item, "qty": qty,
                                      "amount": round(price * qty, 2), "kind": "sale", "k": k})
                        continue
                    pack, lo, hi, keg = r.choice(PACKS)
                    qty = r.randint(1, 4) if keg else r.randint(2, 10)
                    unit = money(r, lo, hi)
                    lines.append({"doc": doc, "type": "INV", "date": d, "rep": n, "account": acct, "item": f"{r.choice(BEERS)} {pack}",
                                  "qty": qty, "amount": round(unit * qty, 2), "kind": "sale", "k": k})
                    if keg:
                        lines.append({"doc": doc, "type": "INV", "date": d, "rep": n, "account": acct, "item": "KEG DEPOSIT",
                                      "qty": qty, "amount": round(DEPOSIT * qty, 2), "kind": "deposit", "k": k})
            # empty shells come back: deposit returns on their own credit docs
            for _ in range(r.randint(1, 3)):
                seq += 1
                qty = r.randint(1, 4)
                lines.append({"doc": f"CRM-{seq}", "type": "CRM", "date": date(2026, mi, r.randint(1, MONTH_DAYS[mi])), "rep": n,
                              "account": r.choice(accounts[n]), "item": "KEG DEPOSIT RETURN", "qty": qty,
                              "amount": -round(DEPOSIT * qty, 2), "kind": "deposit", "k": r.random()})
            # product credits: spoiled or short-shipped beer
            if r.random() < 0.45 or (n == names[1]):
                for _ in range(r.randint(1, 2)):
                    seq += 1
                    lines.append({"doc": f"CRM-{seq}", "type": "CRM", "date": date(2026, mi, r.randint(1, MONTH_DAYS[mi])), "rep": n,
                                  "account": r.choice(accounts[n]), "item": f"Credit - {r.choice(['spoiled', 'short ship', 'price adj', 'damaged'])}",
                                  "qty": 1, "amount": -money(r, 90, 520), "kind": "credit", "k": r.random()})
    lines.sort(key=lambda x: (x["date"], x["k"], x["doc"]))
    # typed rep names: spread each variant across the half so every spelling carries real money
    typed_doc = {}
    for x in lines:
        opts = spell.get(x["rep"])
        if not opts:
            x["typed"] = x["rep"]
        else:
            if x["doc"] not in typed_doc:
                typed_doc[x["doc"]] = opts[r.randrange(len(opts))]
            x["typed"] = typed_doc[x["doc"]]
    net = {}
    for x in lines:
        if x["kind"] == "deposit":
            continue
        key = (x["rep"], x["date"].strftime("%Y-%m"))
        net[key] = round(net.get(key, 0.0) + x["amount"], 2)
    for n in names:
        for m in MONTHS:
            net.setdefault((n, m), 0.0)
    totals = {n: round(sum(net[(n, m)] for m in MONTHS), 2) for n in names}
    grand = round(sum(totals.values()), 2)
    # sensitive cell: Walker's month with the largest credit
    walker = names[1]
    cred_by_month = {m: sum(-x["amount"] for x in lines if x["rep"] == walker and x["kind"] == "credit" and x["date"].strftime("%Y-%m") == m)
                     for m in MONTHS}
    sens_month = max(MONTHS, key=lambda m: (cred_by_month[m], m))
    return {"reps": names, "spell": spell, "lines": lines, "net": net, "totals": totals, "grand": grand,
            "sens_month": sens_month, "accounts": accounts}


def naive_values(d: dict) -> dict:
    """What the one-liner produces: raw rep column, digits-only amounts (credits turn positive), deposits kept."""
    out = {}
    for x in d["lines"]:
        key = (x["typed"], x["date"].strftime("%Y-%m"))
        out[key] = round(out.get(key, 0.0) + abs(x["amount"]), 2)
    return out


def acceptable(d: dict) -> bool:
    names, net, totals, lines = d["reps"], d["net"], d["totals"], d["lines"]
    cruz, walker = names[0], names[1]
    # every spelling carries at least 8% of Cruz's half and the raw-name row cannot pass for the merged total
    for opts, n in ((d["spell"][cruz], cruz), (d["spell"][walker], walker)):
        for s in opts:
            part = sum(x["amount"] for x in lines if x["typed"] == s and x["kind"] != "deposit")
            if part < 0.08 * totals[n]:
                return False
    sm = d["sens_month"]
    cell = net[(walker, sm)]
    credits = sum(-x["amount"] for x in lines if x["rep"] == walker and x["kind"] == "credit" and x["date"].strftime("%Y-%m") == sm)
    deposits = sum(x["amount"] for x in lines if x["rep"] == walker and x["kind"] == "deposit" and x["date"].strftime("%Y-%m") == sm)
    if credits < 0.03 * cell or abs(deposits) < 0.03 * cell:
        return False
    # no other number on Walker's row within 1.5% of the sensitive cell
    row = [net[(walker, m)] for m in MONTHS if m != sm] + [totals[walker]]
    if any(abs(v - cell) <= 0.015 * cell for v in row):
        return False
    # the shortcut moves the grand total by more than 3%
    naive_grand = sum(abs(x["amount"]) for x in lines)
    if abs(naive_grand - d["grand"]) < 0.03 * d["grand"]:
        return False
    # the net-of-credits but deposits-kept reading (or credits dropped) must also move the Walker cell
    with_dep = cell + deposits
    no_cred = cell + credits
    if abs(with_dep - cell) <= 0.01 * cell or abs(no_cred - cell) <= 0.01 * cell:
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def pivot_sheets(data_rows: list[list], reps: list[str], label_total: str = "Total") -> dict:
    n = len(data_rows) + 1
    rows = []
    for i, rep in enumerate(reps, start=2):
        line = [rep]
        for j, _m in enumerate(MONTHS):
            c = chr(ord("B") + j)
            line.append(f"=SUMIFS(Data!$E$2:$E${n},Data!$D$2:$D${n},$A{i},Data!$C$2:$C${n},{c}$1)")
        line.append(f"=SUM(B{i}:G{i})")
        rows.append(line)
    last = 1 + len(reps)
    rows.append([label_total] + [f"=SUM({c}2:{c}{last})" for c in "BCDEFGH"])
    return {
        "By Rep": {"header": ["Rep"] + MONTHS + ["H1 Total"], "rows": rows, "widths": {"A": 22, "H": 14}},
        "Data": {"header": ["doc_no", "doc_date", "month", "rep", "amount"], "rows": data_rows, "widths": {"D": 22}},
    }


def clean_rows(d: dict) -> list[list]:
    return [[x["doc"], x["date"].isoformat(), x["date"].strftime("%Y-%m"), x["rep"], x["amount"]]
            for x in d["lines"] if x["kind"] != "deposit"]


def amount_text(v: float) -> str:
    return f"{abs(v):,.2f}-" if v < 0 else f"{v:,.2f}"


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    ws, ref, sol = task_dirs(HERE)
    names, net, totals = d["reps"], d["net"], d["totals"]
    cruz, walker, patel = names[0], names[1], names[2]
    sm = d["sens_month"]

    rows = [[x["type"], x["doc"], x["date"].strftime("%m/%d/%Y"), x["account"], x["typed"], x["item"], x["qty"], amount_text(x["amount"])]
            for x in d["lines"]]
    write_csv(os.path.join(ws, "invoice_lines_2026-01_to_2026-06.csv"),
              ["Doc Type", "Doc No", "Doc Date", "Account", "Sales Rep", "Item", "Qty", "Ext Amount"], rows,
              preamble=["Tamarack Brewing - Invoice line detail", "Doc dates 01/01/2026 - 06/30/2026"], crlf=True)

    # distractor: last half-year's report, static numbers, with a rep who has since left
    old_r = rng(seed + 404)
    old_reps = [n for n in names if n != names[5]] + ["Gary Lindqvist"]
    old_months = [f"2025-{m:02d}" for m in range(7, 13)]
    old_rows = []
    for n in old_reps:
        vals = [money(old_r, 9000, 21000) for _ in old_months]
        old_rows.append([n] + vals + [round(sum(vals), 2)])
    old_rows.append(["Total"] + [round(sum(rw[j] for rw in old_rows), 2) for j in range(1, 8)])
    write_xlsx(os.path.join(ws, "rep_sales_2025H2.xlsx"), {"Reps": {
        "merged_title": "Rep sales July - December 2025", "header": ["Rep"] + old_months + ["Total"], "rows": old_rows,
        "widths": {"A": 22}}}, creator="Sales")

    others = ", ".join(names[3:])
    write_text(os.path.join(ws, "note_from_kwame.txt"),
               "Rep numbers for January to June\n"
               "\n"
               f"Our reps this half: {cruz}, {walker}, {patel}, {others}.\n"
               "The order desk types the rep on every invoice by hand, so expect the names to be all over the place.\n"
               "\n"
               "What counts: everything we invoiced for beer and merch, less credit memos. Keg deposits are not sales -\n"
               "that is the customer's money and we hand it back when the empty shell comes in - so the deposit lines\n"
               "and the deposit returns stay out of it.\n"
               "\n"
               f"Every rep gets a row and every month gets a number, even if it is zero ({patel.split()[0]} was on leave in April).\n"
               "The commission sheet reads straight across and chokes on blanks. Totals across and down, and keep it\n"
               "live so I can drop corrections in later.\n"
               "\n"
               "- Kwame\n")

    write_csv(os.path.join(ref, "rep_month.csv"), ["rep", "month", "net_sales"],
              [[n, m, f"{net[(n, m)]:.2f}"] for n in names for m in MONTHS])
    write_csv(os.path.join(ref, "rep_totals.csv"), ["rep", "net_sales"], [[n, f"{totals[n]:.2f}"] for n in names] + [["ALL", f"{d['grand']:.2f}"]])
    dep_total = round(sum(x["amount"] for x in d["lines"] if x["kind"] == "deposit"), 2)
    cred_total = round(sum(x["amount"] for x in d["lines"] if x["kind"] == "credit"), 2)
    write_json(os.path.join(ref, "notes.json"), {"zero_cell": {"rep": patel, "surname": "Patel", "month": LEAVE_MONTH},
                                                 "spellings": d["spell"], "sensitive": {"rep": walker, "month": sm, "value": net[(walker, sm)]},
                                                 "deposit_lines_net": dep_total, "credit_total": cred_total, "grand_total": d["grand"]})
    write_xlsx(os.path.join(sol, "sales_by_rep.xlsx"), pivot_sheets(clean_rows(d), names), creator="reference")

    month_word = date(2026, int(sm[-2:]), 1).strftime("%B")
    write_task_yaml(HERE, {
        "id": "sales-pivot-by-rep", "track": "desk", "category": "spreadsheet",
        "title": "Rep by month sales table from the invoice export",
        "ask": ("Kwame needs January to June sales for each rep by month, with totals, from the invoice export in this folder. "
                "Save it as sales_by_rep.xlsx and keep it live. His note has what counts.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "the order desk typed Dana Cruz four ways (Dana Cruz, D. Cruz, 'Cruz, Dana', DANA CRUZ) and Christopher Walker two ways; "
            "a group-by on the raw Sales Rep column splits both across several rows (checks: Cruz H1 total; Walker H1 total)",
            "credit memos are exported with a trailing minus ('182.00-'); stripping to digits books them as sales and a strict "
            f"number parse silently drops them (checks: Walker {month_word}; H1 total, all reps)",
            "every keg line carries a KEG DEPOSIT line and empty shells come back as KEG DEPOSIT RETURN credits; the note says deposits "
            f"are not sales, and a plain sum of Ext Amount keeps them (checks: Walker {month_word}; H1 total, all reps)",
            f"{patel} was on leave in April and has no rows at all; a pivot leaves her April cell blank where the note wants a 0 "
            "(check: Patel April reads 0)",
            "totals across and down must be live formulas, not pasted values (check: live formulas)",
            "the export carries a two-line preamble, CRLF endings and text amounts with thousands separators, and last half-year's "
            "report with a departed rep sits beside it (check: H1 total, all reps)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "sales_by_rep.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "sales_by_rep.xlsx"},
            {"type": "xlsx_value_present", "name": "Cruz H1 total (four spellings merged)", "path": "sales_by_rep.xlsx",
             "expected": totals[cruz], "rel_tol": cent_tol(totals[cruz], 0.003), "near_text": "cruz"},
            {"type": "xlsx_value_present", "name": "Walker H1 total (two spellings merged)", "path": "sales_by_rep.xlsx",
             "expected": totals[walker], "rel_tol": cent_tol(totals[walker], 0.003), "near_text": "walker"},
            {"type": "xlsx_value_present", "name": f"Walker {month_word} (credits netted, deposits out)", "path": "sales_by_rep.xlsx",
             "expected": net[(walker, sm)], "rel_tol": cent_tol(net[(walker, sm)], 0.003), "near_text": "walker"},
            {"type": "xlsx_value_present", "name": "H1 total, all reps", "path": "sales_by_rep.xlsx",
             "expected": d["grand"], "rel_tol": cent_tol(d["grand"], 0.003), "near_text": "total"},
            {"type": "custom", "name": "Patel April reads 0", "module": "check.py"},
        ],
    })
    print(f"seed={seed} lines={len(d['lines'])} grand={d['grand']} cruz={totals[cruz]} walker={totals[walker]} "
          f"walker_{sm}={net[(walker, sm)]}")


def write_naive(d: dict, out: str) -> None:
    """Raw rep column as the row label, digits-only amounts, deposits kept, pasted values, blanks where no rows."""
    os.makedirs(out, exist_ok=True)
    vals = naive_values(d)
    reps = sorted({x["typed"] for x in d["lines"]})
    rows = []
    for rep in reps:
        cells = [vals.get((rep, m), None) for m in MONTHS]
        rows.append([rep] + cells + [round(sum(c for c in cells if c), 2)])
    rows.append(["Total"] + [round(sum(rw[j] or 0 for rw in rows), 2) for j in range(1, 8)])
    write_xlsx(os.path.join(out, "sales_by_rep.xlsx"), {"Pivot": {"header": ["Sales Rep"] + MONTHS + ["Total"], "rows": rows}}, creator="naive")


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
