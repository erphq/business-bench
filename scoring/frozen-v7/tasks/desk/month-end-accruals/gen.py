#!/usr/bin/env python3
"""month-end-accruals: a regional theatre's August accrual entry from the AP register, the receiving log and July's entry.

    python gen.py [--seed N] [--naive DIR]

Business: Lantern Street Theatre, a nonprofit playhouse closing August 2026. AP keeps entering bills into
mid-September; the production manager keeps a log of what arrived without a bill; July's accrual entry auto-reversed
on 1 August. The controller's email carries the rules: what counts as "in August AP" (the posting period), bill beats
estimate, August days only for a bill that straddles the month, re-accrue July items still unbilled, a $250 floor.

Traps (each caught by a check, see task.yaml):
  * bills dated in September for August work (stagehand crew, a repair) must be accrued at the bill  (checks: accrued items; amount)
  * a bill dated in August but entered into the September period is not in August AP                   (checks: accrued items; amount)
  * a lighting rental billed for 20 Aug to 18 Sep is accrued for its August days only                   (check: amount)
  * July's accrual reversed on 1 August: two July items still have no bill and must be accrued again, one
    was billed in September and takes the bill, two were billed in August and are done                 (checks: accrued items; amount)
  * two log items were billed in September at a different figure than the log estimate; the bill wins
    and the PO line must not be accrued as well; two log items were billed in August already           (checks: accrued items; row count)
  * September services and a royalty advance billed in September are not August costs                   (check: accrued items)
  * items under $250 are skipped                                                                         (check: row count)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

GL = {"5110": "Production labor", "5120": "Lighting and sound rental", "5130": "Scenic and costume materials", "5140": "Royalties",
      "6110": "Utilities", "6120": "Building repairs and maintenance", "6210": "Professional fees", "6310": "Marketing and printing",
      "6410": "Office and administration"}
VENDORS = [  # name, gl, invoice prefix
    ("Rigging Hands Staffing", "5110", "RH-"), ("Brightfield Stage Lighting", "5120", "BSL"), ("Soundcraft AV Rentals", "5120", "SAV-"),
    ("Northgate Lumber & Hardware", "5130", "NG"), ("Fabric Row Textiles", "5130", "FR-"), ("Dramatists Licensing Group", "5140", "DLG-"),
    ("Harbor City Power & Light", "6110", "HCPL-"), ("Keel & Mast Plumbing", "6120", "KM"), ("Evergreen Pest Control", "6120", "EPC-"),
    ("Hollis & Webb LLP", "6210", "HW-"), ("Arden Printing Co", "6310", "AP-"), ("Martin Keys Piano Service", "6120", "MK"),
    ("Tri-County Waste Services", "6110", "TCW"), ("Cobalt Scenic Paints", "5130", "CSP-"), ("Wexford Audit Partners", "6210", "WAP-"),
    ("Lakeshore Office Supply", "6410", "LOS"), ("Crescent Janitorial", "6120", "CJ-"), ("Boxline Ticketing", "6410", "BXT-"),
    ("Pier Street Signs", "6310", "PSS-")]
ORDINARY = {  # vendors that only ever send ordinary August bills: what they bill for, and the usual range
    "Hollis & Webb LLP": ("Legal services - July 2026 (lease review)", 900, 2600),
    "Martin Keys Piano Service": ("Piano regulation - rehearsal hall", 280, 640),
    "Rigging Hands Staffing": ("Stage crew, Tempest tech week 08/03 - 08/07", 1800, 3400),
    "Evergreen Pest Control": ("Quarterly pest service 08/05/2026", 180, 420),
    "Lakeshore Office Supply": ("Toner and copy paper", 120, 560), "Crescent Janitorial": ("Janitorial service July 2026", 1100, 2200),
    "Boxline Ticketing": ("Ticketing platform fees July 2026", 600, 1900), "Pier Street Signs": ("Lobby banner - Tempest", 240, 880),
    "Keel & Mast Plumbing": ("Annual backflow test", 180, 390), "Dramatists Licensing Group": ("Royalties - Tempest performances 1-8", 1400, 3300),
    "Brightfield Stage Lighting": ("Gel and lamp replacement", 300, 1200)}


def c2(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build(seed: int) -> dict:
    r = rng(seed)
    used_inv = set()

    def inv(prefix: str) -> str:
        while True:
            s = f"{prefix}{r.randint(1000, 98999)}"
            if s not in used_inv:
                used_inv.add(s)
                return s

    po_seq = iter(sorted(r.sample(range(310, 480), 30)))

    def po() -> str:
        return f"PO-26-{next(po_seq):04d}"

    def amt(lo, hi):
        return c2(r.uniform(lo, hi))

    vend = {v[0]: v for v in VENDORS}
    bills, log, july = [], [], []   # bills: invoice, vendor, bill_date, period, gl, desc, amount, po
    accrue = []                     # reference, vendor, gl, amount, role
    excluded = []                   # (reference, role)

    def bill(vname, bill_date, period, desc, amount, po_no="", role=""):
        v = vend[vname]
        b = {"inv": inv(v[2]), "vendor": vname, "date": bill_date, "period": period, "gl": v[1], "desc": desc, "amount": amount,
             "po": po_no, "role": role}
        bills.append(b)
        return b

    # A: ordinary August bills
    for vname in r.sample(sorted(ORDINARY), 9):
        d = day_in(r, date(2026, 8, 3), date(2026, 8, 28), weekday_only=True)
        what, lo, hi = ORDINARY[vname]
        bill(vname, d, "2026-08", what, amt(lo, hi), role="aug")

    # B: September-dated bills for August work
    crew = bill("Rigging Hands Staffing", date(2026, 9, r.randint(2, 4)), "2026-09",
                f"Stage crew, Tempest run 08/{r.randint(6, 8):02d} - 08/{r.randint(28, 30):02d}", amt(5200, 8600), role="sep_for_aug")
    repair = bill("Keel & Mast Plumbing", date(2026, 9, r.randint(7, 10)), "2026-09",
                  f"Emergency repair - lobby restroom supply line 08/{r.randint(24, 29):02d}", amt(640, 1450), role="sep_for_aug")
    # D: bill dated in August, entered to September
    late_entry = bill("Hollis & Webb LLP", date(2026, 8, r.randint(26, 31)), "2026-09", "Legal services - August 2026 (board governance)",
                      amt(1800, 3900), role="aug_date_sep_period")
    # E: a rental that straddles the month end
    straddle_start = date(2026, 8, r.randint(17, 24))
    straddle_end = straddle_start + timedelta(days=r.choice([27, 29, 30]))
    straddle = bill("Brightfield Stage Lighting", date(2026, 9, r.randint(1, 3)), "2026-09",
                    f"Lighting package rental {straddle_start.strftime('%m/%d/%Y')} - {straddle_end.strftime('%m/%d/%Y')}", amt(3900, 6400),
                    role="straddle")
    period_days = (straddle_end - straddle_start).days + 1
    aug_days = (date(2026, 8, 31) - straddle_start).days + 1
    straddle_accrual = c2(straddle["amount"] * aug_days / period_days)
    # C/N: September costs billed in September
    sep1 = bill("Soundcraft AV Rentals", date(2026, 9, 1), "2026-09", "September rehearsal sound system rental 09/01 - 09/30", amt(900, 1900),
                role="sep_service")
    sep2 = bill("Dramatists Licensing Group", date(2026, 9, r.randint(4, 9)), "2026-09", "Royalty advance - November production", amt(1500, 3200),
                role="sep_service")
    sep3 = bill("Harbor City Power & Light", date(2026, 9, r.randint(8, 11)), "2026-09", "Electric service 08/01/2026 - 08/31/2026", amt(2100, 3300),
                role="sep_for_aug")
    small_sep = bill("Evergreen Pest Control", date(2026, 9, r.randint(2, 9)), "2026-09", "Pest service 08/27/2026", amt(95, 210), role="small")

    for b in (crew, repair, late_entry, sep3):
        accrue.append({"ref": b["inv"], "vendor": b["vendor"], "gl": b["gl"], "amount": b["amount"], "role": b["role"]})
    accrue.append({"ref": straddle["inv"], "vendor": straddle["vendor"], "gl": straddle["gl"], "amount": straddle_accrual, "role": "straddle"})
    for b in (sep1, sep2):
        excluded.append((b["inv"], "sep_service"))
    excluded.append((small_sep["inv"], "small"))

    # receiving log
    def log_item(vname, desc, est, when, role):
        item = {"log": f"RNB-{len(log) + 41:03d}", "po": po(), "vendor": vname, "gl": vend[vname][1], "desc": desc, "est": est,
                "date": when, "role": role}
        log.append(item)
        return item

    g1 = log_item("Northgate Lumber & Hardware", "Platform lumber and hardware for Tempest set", amt(1200, 2900), date(2026, 8, r.randint(3, 12)), "unbilled")
    g2 = log_item("Fabric Row Textiles", "Muslin and duvetyne, 60 yds", amt(420, 980), date(2026, 8, r.randint(10, 20)), "unbilled")
    g3 = log_item("Cobalt Scenic Paints", "Scenic paint order", amt(510, 1300), date(2026, 8, r.randint(14, 27)), "unbilled")
    h1 = log_item("Arden Printing Co", "Season brochures - 4,000 pcs", amt(2400, 3600), date(2026, 8, r.randint(18, 26)), "billed_sep")
    h2 = log_item("Soundcraft AV Rentals", "Wireless mic kit rental for Tempest (August)", amt(700, 1600), date(2026, 8, r.randint(5, 9)), "billed_sep")
    f1 = log_item("Northgate Lumber & Hardware", "Casters and hinges", amt(300, 700), date(2026, 8, r.randint(3, 8)), "billed_aug")
    f2 = log_item("Martin Keys Piano Service", "Piano tuning before opening", amt(260, 480), date(2026, 8, r.randint(4, 9)), "billed_aug")
    i1 = log_item("Fabric Row Textiles", "Thread and notions", amt(40, 190), date(2026, 8, r.randint(10, 25)), "small")
    for g in (g1, g2, g3):
        accrue.append({"ref": g["po"], "vendor": g["vendor"], "gl": g["gl"], "amount": g["est"], "role": "unbilled"})
    for h in (h1, h2):
        diff = amt(35, 260) * r.choice([1, -1])
        b = bill(h["vendor"], date(2026, 9, r.randint(1, 10)), "2026-09", h["desc"], h["est"] + diff, po_no=h["po"], role="log_billed_sep")
        accrue.append({"ref": b["inv"], "vendor": b["vendor"], "gl": b["gl"], "amount": b["amount"], "role": "log_billed_sep"})
        excluded.append((h["po"], "log_billed_sep_po"))
    for f in (f1, f2):
        b = bill(f["vendor"], f["date"] + timedelta(days=r.randint(2, 8)), "2026-08", f["desc"], f["est"], po_no=f["po"], role="log_billed_aug")
        excluded.append((b["inv"], "log_billed_aug"))
        excluded.append((f["po"], "log_billed_aug_po"))
    excluded.append((i1["po"], "small"))

    # July's accrual entry
    def jul(vname, desc, amount, role, ref=None):
        item = {"ref": ref or po(), "vendor": vname, "gl": vend[vname][1], "desc": desc, "amount": amount, "role": role}
        july.append(item)
        return item

    j1 = jul("Wexford Audit Partners", "FY2026 audit fieldwork - July (estimate)", amt(2600, 4800), "jul_unbilled")
    j2 = jul("Tri-County Waste Services", "Dumpster swaps after strike - July", amt(380, 760), "jul_unbilled")
    j3 = jul("Cobalt Scenic Paints", "Paint and sundries - July", amt(600, 1400), "jul_billed_sep")
    j4 = jul("Rigging Hands Staffing", "Stage crew load-in 07/27 - 07/31", amt(2200, 3900), "jul_billed_aug")
    j5 = jul("Harbor City Power & Light", "Electric service July (estimate)", amt(1900, 2900), "jul_billed_aug")
    for j in (j1, j2):
        accrue.append({"ref": j["ref"], "vendor": j["vendor"], "gl": j["gl"], "amount": j["amount"], "role": "jul_unbilled"})
    b3 = bill(j3["vendor"], date(2026, 9, r.randint(2, 9)), "2026-09", j3["desc"].replace(" - July", ", July delivery"),
              j3["amount"] + amt(20, 140), po_no=j3["ref"], role="jul_billed_sep")
    accrue.append({"ref": b3["inv"], "vendor": b3["vendor"], "gl": b3["gl"], "amount": b3["amount"], "role": "jul_billed_sep"})
    excluded.append((j3["ref"], "jul_billed_sep_po"))
    for j in (j4, j5):
        b = bill(j["vendor"], date(2026, 8, r.randint(4, 14)), "2026-08", j["desc"].replace(" (estimate)", ""), j["amount"] + amt(-80, 80),
                 po_no=j["ref"] if j is j4 else "", role="jul_billed_aug")
        excluded.append((j["ref"], "jul_billed_aug"))

    bills.sort(key=lambda b: (b["period"], b["date"], b["inv"]))
    accrue.sort(key=lambda a: a["ref"])
    return {"bills": bills, "log": log, "july": july, "accrue": accrue, "excluded": excluded, "straddle": straddle,
            "straddle_days": (aug_days, period_days), "roles": {"crew": crew, "late_entry": late_entry, "straddle": straddle,
                                                               "h1": h1, "j1": j1, "j3": j3}, "k": r.random()}


def acceptable(d: dict) -> bool:
    refs = [a["ref"] for a in d["accrue"]]
    if len(set(refs)) != len(refs):
        return False
    if any(a["amount"] < 250 for a in d["accrue"]):
        return False
    s = d["straddle"]
    aug, per = d["straddle_days"]
    full = s["amount"]
    # the prorated figure is not a whole-cent coincidence of a naive split
    if abs(full * aug / per - (full * aug / per).quantize(Decimal("0.01"))) < Decimal("0.001"):
        return False
    for b in d["bills"]:
        if b["role"] in ("log_billed_aug", "jul_billed_aug") and b["amount"] < 250:
            return False
    return True


def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    header = ["reference", "vendor", "gl_account", "amount"]
    if naive_dir:
        # every log line at its estimate, plus every September-posted bill in full
        rows = [[x["po"], x["vendor"], x["gl"], f"{x['est']:.2f}"] for x in d["log"]]
        rows += [[b["inv"], b["vendor"], b["gl"], f"{b['amount']:.2f}"] for b in d["bills"] if b["period"] == "2026-09"]
        write_csv(os.path.join(naive_dir, "accruals.csv"), header, rows)
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 7)

    reg_rows = []
    for b in d["bills"]:
        style = r.randrange(3)
        reg_rows.append([b["inv"], b["vendor"] if r.random() > 0.2 else b["vendor"].upper(), date_variant(b["date"], [0, 1, 4][style]),
                         {"2026-08": "Aug 2026", "2026-09": "Sep 2026"}[b["period"]], f"{b['gl']} {GL[b['gl']]}", b["po"], b["desc"],
                         money_str(float(b["amount"]), [1, 0, 6][r.randrange(3)])])
    write_csv(os.path.join(ws, "ap_bill_register_entered_2026-08-01_to_2026-09-12.csv"),
              ["Invoice #", "Vendor", "Bill Date", "Posting Period", "GL Account", "PO #", "Description", "Amount"], reg_rows,
              preamble=["Lantern Street Theatre - AP bill register", "Entered 08/01/2026 through 09/12/2026, all periods"], crlf=True)

    log_rows = [[x["log"], x["date"], x["vendor"], x["po"], x["desc"], float(x["est"]), f"{x['gl']} {GL[x['gl']]}"] for x in d["log"]]
    r.shuffle(log_rows)
    log_rows.sort(key=lambda row: row[1])
    write_xlsx(os.path.join(ws, "received_not_invoiced_log_aug2026.xlsx"), {"August": {
        "merged_title": "Received / performed - waiting on invoice (production office)",
        "preamble": [["Kept by the production manager. Estimates are the PO or quote amount.", "", "", "", "", "", ""]],
        "header": ["Log #", "Received", "Vendor", "PO #", "What", "Estimate", "Charge to"],
        "rows": log_rows, "number_formats": {"F": "#,##0.00"}, "widths": {"C": 28, "E": 42, "G": 30}}}, creator="Production")

    je = []
    for j in d["july"]:
        je.append(["07/31/2026", j["ref"], j["vendor"], j["gl"], j["desc"], f"{j['amount']:,.2f}", ""])
    total = sum(j["amount"] for j in d["july"])
    je.append(["07/31/2026", "", "", "2150", "Accrued expenses - July close", "", f"{total:,.2f}"])
    write_csv(os.path.join(ws, "accrual_entry_2026-07.csv"), ["Date", "Reference", "Vendor", "Account", "Memo", "Debit", "Credit"], je,
              preamble=["JE-2026-07-31-ACC  Month-end accruals July 2026", "Auto-reverse on 08/01/2026: YES"])

    ctrl = "Renata Mensah"
    write_email_thread(os.path.join(ws, "email_from_renata.txt"), [
        {"from": f"{ctrl} <renata@lanternstreettheatre.org>", "to": "Sam Ortiz <sam@lanternstreettheatre.org>",
         "date": "Sat, 12 Sep 2026 16:40", "subject": "August close - accruals",
         "body": ("Sam,\n\nCould you put together the August accrual entry before I close the month on Monday? Same approach as July:\n\n"
                  "1. We accrue anything that was delivered or performed on or before 31 August that is not already in August's AP. "
                  "\"In August's AP\" means the bill is posted to the Aug 2026 period in the register - the bill date on its own does "
                  "not tell you that.\n"
                  "2. If the vendor's bill has come in (the register runs to today), accrue the bill amount and use its invoice number as "
                  "the reference. If there is no bill yet, use the PO number and the estimate.\n"
                  "3. If a bill covers days on both sides of 31 August, accrue only the August share: the bill amount times the number of "
                  "service days in August divided by the number of days in the billing period, counting both the first and the last day, "
                  "rounded to the cent.\n"
                  "4. July's accrual entry reversed on 1 August. Anything on it that has been billed into August is taken care of; "
                  "anything still waiting on a bill has to be accrued again.\n"
                  "5. Skip anything under $250 - not worth the entry.\n\n"
                  "Nothing for September services or deposits on future shows, obviously.\n\n"
                  "Send it back as accruals.csv with one line per item: reference, vendor, gl_account (the four-digit account) and "
                  "amount. No total line and no credit side - I post the 2150 credit myself.\n\nThanks,\nRenata")}])

    rows = [[a["ref"], a["vendor"], a["gl"], f"{a['amount']:.2f}"] for a in d["accrue"]]
    write_csv(os.path.join(ref, "accruals.csv"), header, rows)
    write_csv(os.path.join(sol, "accruals.csv"), header, rows)
    write_json(os.path.join(ref, "notes.json"), {"accrued": {a["ref"]: a["role"] for a in d["accrue"]},
                                                  "excluded": {k: v for k, v in d["excluded"]}, "total": f"{sum(a['amount'] for a in d['accrue']):.2f}",
                                                  "straddle_days": d["straddle_days"]})
    ro = d["roles"]
    by_role = {}
    for a in d["accrue"]:
        by_role.setdefault(a["role"], []).append(a["ref"])
    must = [ro["crew"]["inv"], ro["late_entry"]["inv"], ro["straddle"]["inv"], ro["j1"]["ref"]] + by_role["log_billed_sep"] + by_role["jul_billed_sep"]
    aug, per = d["straddle_days"]
    s = ro["straddle"]
    write_task_yaml(HERE, {
        "id": "month-end-accruals", "track": "desk", "category": "bookkeeping",
        "title": "August accrual entry for the theatre",
        "ask": "Renata needs the August accruals before she closes the month; her email explains how we do them. Save the entry as accruals.csv.\n",
        "followup": None, "timeout_s": 1200,
        "traps": [
            f"bills dated in September for August work ({ro['crew']['vendor']} {ro['crew']['inv']} for the August run, a plumbing repair, "
            "August electricity) are posted to the September period and must be accrued at the bill amount (checks: accrued items; amount per item)",
            f"{ro['late_entry']['vendor']} {ro['late_entry']['inv']} is dated in August but entered into Sep 2026, so it is not in August AP; "
            "filtering on bill date skips it (checks: accrued items; amount per item)",
            f"{s['vendor']} {s['inv']} covers {s['desc'][-23:]}: only {aug} of its {per} days are August, "
            "so the accrual is that share of the bill, not all of it and not half (check: amount per item)",
            "July's accrual entry reversed on 1 August: two July items still have no bill and must be accrued again at July's figure, "
            "one was billed into September and takes the bill's number and amount, and two were billed into August and are done "
            "(checks: accrued items; amount per item)",
            "two receiving-log items were billed into September for a different amount than the log estimate; the bill replaces the PO "
            "line, and two other log items were already billed into August (checks: accrued items; row count)",
            "a September sound rental and a royalty advance for the November show are September-posted bills that are not August costs, "
            "and a pest-control bill and a log line fall under the $250 floor (checks: accrued items; row count)",
            "the register has a two-line preamble, CRLF endings, upper-cased vendors, three date formats and amounts as '$ 1,234.00' text; "
            "the July entry has its 2150 credit line in the same columns (check: amount per item)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "accruals.csv", "columns": header},
            {"type": "csv_set_equal", "name": "accrued items", "path": "accruals.csv", "column": "reference", "ref": "accruals.csv"},
            {"type": "csv_row_count", "name": "row count", "path": "accruals.csv", "equals_ref": "accruals.csv"},
            {"type": "csv_values_match", "name": "amount per item", "path": "accruals.csv", "ref": "accruals.csv", "key": "reference",
             "columns": ["amount"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": must},
            {"type": "csv_values_match", "name": "account per item", "path": "accruals.csv", "ref": "accruals.csv", "key": "reference",
             "columns": ["gl_account"], "normalize": ["digits"], "min_accuracy": 1.0},
        ],
    })
    print(f"seed={seed} accrued={len(d['accrue'])} total={sum(a['amount'] for a in d['accrue'])} straddle={aug}/{per}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    a = ap.parse_args()
    for attempt in range(400):
        if acceptable(build(a.seed * 1000 + attempt)):
            break
    else:
        raise SystemExit("no acceptable draw")
    emit(a.seed * 1000 + attempt, a.naive)
