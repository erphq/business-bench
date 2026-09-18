#!/usr/bin/env python3
"""project-budget-burn: a maritime museum's gallery renovation, budget against purchase orders, change orders and invoices.

    python gen.py [--seed N] [--naive DIR]

Business: the Tidewater Maritime Museum is renovating its West Gallery. The board approved a budget by cost code; the
facilities director issues purchase orders to contractors, logs change orders and passes invoices to AP. The
director wants spent, committed and remaining per cost code for the board's capital committee, following her
definitions: committed is what is left on open POs after approved change orders and invoices, never below zero.

Traps (each caught by a check, see task.yaml):
  * invoices billed against a PO are already inside the PO; spent plus the PO's full value counts them twice
                                                                                   (checks: fabrication committed; total committed)
  * approved change orders (one of them deductive) change the PO; pending and rejected ones do not
                                                                                   (check: fabrication committed)
  * the HVAC contractor has billed work on a change order still pending, so its invoices exceed the PO; spent takes
    every posted invoice and committed stops at zero                               (check: HVAC remaining)
  * the electrical PO was closed short after its final invoice; nothing is still committed on it (check: electrical remaining)
  * a voided lighting invoice and PO references keyed four ways                      (check: lighting spent)
  * design and permit invoices have no PO and carry their cost code directly         (check: design fees spent)
  * a cancelled AV PO commits nothing                                                 (checks: total committed; total remaining)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

D = Decimal
CODES = [("WG-01", "General conditions"), ("WG-02", "Demolition and abatement"), ("WG-03", "Electrical"), ("WG-04", "HVAC"), ("WG-05", "Exhibit fabrication"),
         ("WG-06", "Gallery lighting"), ("WG-07", "AV and interactive media"), ("WG-08", "Design and engineering fees"), ("WG-09", "Permits and inspections"),
         ("WG-10", "Owner contingency")]
NAME = dict(CODES)


def k(r, lo, hi, step=1) -> Decimal:
    return D(r.randrange(lo, hi, step))


def cents(r, lo, hi) -> Decimal:
    return D(r.randint(int(lo * 100), int(hi * 100))) / 100


def build(seed: int) -> dict:
    r = rng(seed)
    pos, cos, invs = [], [], []
    po_n = [r.randint(8, 20)]
    inv_seen = set()

    def po(code, vendor, desc, amount, status, issued):
        po_n[0] += r.randint(1, 3)
        p = {"no": f"PO-2026-{po_n[0]:03d}", "n": po_n[0], "code": code, "vendor": vendor, "desc": desc, "amount": D(amount), "status": status,
             "issued": issued}
        pos.append(p)
        return p

    def co(p, amount, status, desc, when):
        c = {"no": f"CO-{len(cos) + 1:02d}", "po": p, "amount": D(amount), "status": status, "desc": desc, "date": when}
        cos.append(c)
        return c

    def inv(vendor, amount, when, p=None, code=None, status="Posted", prefix=""):
        while True:
            no = f"{prefix}{r.randint(1000, 9999)}"
            if no not in inv_seen:
                inv_seen.add(no)
                break
        i = {"no": no, "vendor": vendor, "amount": D(amount), "date": when, "po": p, "code": code or (p["code"] if p else None), "status": status}
        invs.append(i)
        return i

    start = date(2026, 1, 12)
    gc = po("WG-01", "Harbor & Finch Builders", "General contractor fee and site supervision", k(r, 84000, 118000, 500), "Open", start)
    for m in range(2, 9):
        inv(gc["vendor"], (gc["amount"] / 10).quantize(D("0.01")), date(2026, m, r.randint(25, 28)), gc, prefix="HF-")
    demo = po("WG-02", "Coastline Demolition & Abatement", "Selective demolition, lead paint abatement", k(r, 38000, 56000, 250), "Closed", start + timedelta(days=9))
    inv(demo["vendor"], (demo["amount"] * D("0.6")).quantize(D("0.01")), date(2026, 2, r.randint(10, 20)), demo, prefix="CDA-")
    inv(demo["vendor"], demo["amount"] - (demo["amount"] * D("0.6")).quantize(D("0.01")), date(2026, 3, r.randint(5, 15)), demo, prefix="CDA-")
    elec = po("WG-03", "Brightwire Electrical Contractors", "Branch circuits, panel upgrade, exhibit power", k(r, 72000, 108000, 500), "Closed",
              date(2026, 2, r.randint(2, 12)))
    e_bill = [(elec["amount"] * D(x)).quantize(D("0.01")) for x in ("0.35", "0.40")]
    e_final = (elec["amount"] * D(str(r.choice([0.17, 0.18, 0.19, 0.21])))).quantize(D("0.01"))
    for i_, amt in enumerate(e_bill + [e_final]):
        inv(elec["vendor"], amt, date(2026, 3 + i_ * 2, r.randint(3, 20)), elec, prefix="BW")
    elec2 = po("WG-03", "Brightwire Electrical Contractors", "Exhibit case outlets (added scope)", k(r, 6000, 11000, 100), "Open", date(2026, 6, r.randint(2, 20)))
    inv(elec2["vendor"], (elec2["amount"] * D("0.5")).quantize(D("0.01")), date(2026, 7, r.randint(8, 24)), elec2, prefix="BW")
    hvac = po("WG-04", "Seaboard Mechanical", "Gallery HVAC with humidity control", k(r, 64000, 92000, 500), "Open", date(2026, 2, r.randint(16, 27)))
    hvac_pending = co(hvac, k(r, 7000, 13000, 50), "Pending", "Added dehumidifier for ship-model cases", date(2026, 6, r.randint(3, 20)))
    hvac_bills = [(hvac["amount"] * D(x)).quantize(D("0.01")) for x in ("0.30", "0.45")]
    hvac_bills.append(hvac["amount"] - sum(hvac_bills) + hvac_pending["amount"])
    for i_, amt in enumerate(hvac_bills):
        inv(hvac["vendor"], amt, date(2026, 4 + i_ * 2, r.randint(4, 22)), hvac, prefix="SM-")
    fab = po("WG-05", "Keelhaul Exhibit Studio", "Exhibit fabrication and installation", k(r, 185000, 255000, 1000), "Open", date(2026, 3, r.randint(2, 13)))
    co(fab, k(r, 12000, 28000, 250), "Approved", "Interactive tide table build-out", date(2026, 5, r.randint(4, 20)))
    co(fab, -k(r, 3000, 8000, 50), "Approved", "Delete second graphics rail", date(2026, 6, r.randint(1, 15)))
    co(fab, k(r, 8000, 15000, 250), "Pending", "Replica figurehead upgrade", date(2026, 7, r.randint(6, 24)))
    co(fab, k(r, 4000, 9000, 250), "Rejected", "Walnut veneer in lieu of paint", date(2026, 6, r.randint(16, 28)))
    for x, m in (("0.20", 5), ("0.22", 6), ("0.18", 8)):
        inv(fab["vendor"], (fab["amount"] * D(x)).quantize(D("0.01")), date(2026, m, r.randint(2, 26)), fab, prefix="KES-")
    light = po("WG-06", "Lumenharbor Lighting", "Track lighting and fixtures", k(r, 42000, 64000, 250), "Open", date(2026, 4, r.randint(1, 20)))
    l1 = inv(light["vendor"], (light["amount"] * D("0.40")).quantize(D("0.01")), date(2026, 6, r.randint(3, 12)), light, prefix="LH")
    inv(light["vendor"], l1["amount"], l1["date"] + timedelta(days=r.randint(1, 4)), light, status="Void", prefix="LH")
    inv(light["vendor"], (light["amount"] * D("0.25")).quantize(D("0.01")), date(2026, 8, r.randint(3, 20)), light, prefix="LH")
    av = po("WG-07", "Signal & Tide Media", "Projection and touchscreen interactives", k(r, 56000, 84000, 500), "Open", date(2026, 5, r.randint(4, 22)))
    av_old = po("WG-07", "Northbeam AV Integration", "Projection package (vendor replaced)", k(r, 52000, 80000, 500), "Cancelled", date(2026, 4, r.randint(1, 20)))
    inv(av["vendor"], cents(r, 4000, 9000), date(2026, 8, r.randint(10, 26)), av, prefix="STM-")
    # no-PO invoices
    for _ in range(4):
        inv("Marlow Pike Architects", cents(r, 6200, 18800), day_in(r, date(2026, 1, 20), date(2026, 8, 28), weekday_only=True), code="WG-08", prefix="MPA-")
    inv("Holloway Structural Engineers", cents(r, 3800, 7900), date(2026, 3, r.randint(2, 27)), code="WG-08", prefix="HSE-")
    inv("City of Tidewater Permits", cents(r, 2100, 4800), date(2026, 2, r.randint(2, 27)), code="WG-09", prefix="BLD-")
    inv("City of Tidewater Permits", cents(r, 350, 900), date(2026, 7, r.randint(2, 27)), code="WG-09", prefix="INSP-")

    budget = {}
    for code, _ in CODES:
        need = sum(p["amount"] + sum(c["amount"] for c in cos if c["po"] is p and c["status"] != "Rejected") for p in pos
                   if p["code"] == code and p["status"] != "Cancelled")
        need += sum(i["amount"] for i in invs if i["po"] is None and i["code"] == code) * D("1.6")
        step = 500 if code == "WG-09" else 1000
        budget[code] = (need * D(str(r.uniform(1.06, 1.22))) / step).quantize(D("1")) * step if need else D(r.randrange(60000, 90000, 5000))

    # ---- truth
    rows = {}
    for code, _ in CODES:
        spent = sum(i["amount"] for i in invs if i["status"] == "Posted" and i["code"] == code)
        committed = D("0")
        for p in pos:
            if p["code"] != code or p["status"] != "Open":
                continue
            value = p["amount"] + sum(c["amount"] for c in cos if c["po"] is p and c["status"] == "Approved")
            billed = sum(i["amount"] for i in invs if i["po"] is p and i["status"] == "Posted")
            committed += max(D("0"), value - billed)
        rows[code] = {"budget": budget[code], "spent": spent, "committed": committed, "remaining": budget[code] - spent - committed}
    tot = {kk: sum(v[kk] for v in rows.values()) for kk in ("budget", "spent", "committed", "remaining")}
    return {"pos": pos, "cos": cos, "invs": invs, "rows": rows, "tot": tot, "roles": {"hvac": hvac, "elec": elec, "fab": fab, "light": light,
                                                                                      "av_old": av_old}}


def naive(d: dict) -> dict:
    out = {}
    for code, _ in CODES:
        # invoices joined to POs through the PO number only (voids kept, no-PO invoices dropped)
        spent = sum(i["amount"] for i in d["invs"] if i["po"] is not None and i["po"]["code"] == code)
        committed = sum(p["amount"] + sum(c["amount"] for c in d["cos"] if c["po"] is p) for p in d["pos"] if p["code"] == code)
        out[code] = {"budget": d["rows"][code]["budget"], "spent": spent, "committed": committed}
        out[code]["remaining"] = out[code]["budget"] - spent - committed
    return out


def acceptable(d: dict) -> bool:
    rows, nv = d["rows"], naive(d)
    pins = [("WG-05", "committed"), ("WG-04", "remaining"), ("WG-03", "remaining"), ("WG-06", "spent"), ("WG-08", "spent")]
    for code, field in pins:
        v = rows[code][field]
        others = [rows[code][f] for f in ("budget", "spent", "committed", "remaining") if f != field]
        if any(abs(v - o) <= 1 for o in others):
            return False
    for code, field in (("WG-05", "committed"), ("WG-04", "remaining"), ("WG-03", "remaining"), ("WG-06", "spent")):
        if abs(nv[code][field] - rows[code][field]) < 100:
            return False
    # the HVAC floor matters and the remaining figures are positive where the story says so
    if rows["WG-04"]["committed"] != 0:
        return False
    if any(rows[c]["remaining"] < 0 for c in rows):
        return False
    t = d["tot"]
    if len({t["budget"], t["spent"], t["committed"], t["remaining"]}) < 4:
        return False
    return True


# --------------------------------------------------------------------------- deliverable

def workbook(d: dict) -> dict:
    pos, cos, invs = d["pos"], d["cos"], d["invs"]
    nco, ninv, npo = len(cos) + 1, len(invs) + 1, len(pos) + 1
    co_rows = [[c["no"], c["po"]["no"], c["date"].isoformat(), c["desc"], float(c["amount"]), c["status"]] for c in cos]
    inv_rows = [[i["no"], i["vendor"], i["date"].isoformat(), i["po"]["no"] if i["po"] else "", i["code"], float(i["amount"]), i["status"]] for i in invs]
    po_rows = []
    for j, p in enumerate(pos, start=2):
        po_rows.append([p["no"], p["vendor"], p["code"], p["desc"], p["status"], float(p["amount"]),
                        f'=SUMIFS(\'Change orders\'!$E$2:$E${nco},\'Change orders\'!$B$2:$B${nco},A{j},\'Change orders\'!$F$2:$F${nco},"Approved")',
                        f'=SUMIFS(Invoices!$F$2:$F${ninv},Invoices!$D$2:$D${ninv},A{j},Invoices!$G$2:$G${ninv},"Posted")',
                        f'=IF(E{j}="Open",MAX(0,F{j}+G{j}-H{j}),0)'])
    burn = []
    for j, (code, name) in enumerate(CODES, start=2):
        burn.append([code, name, float(d["rows"][code]["budget"]),
                     f'=SUMIFS(Invoices!$F$2:$F${ninv},Invoices!$E$2:$E${ninv},A{j},Invoices!$G$2:$G${ninv},"Posted")',
                     f"=SUMIFS(POs!$I$2:$I${npo},POs!$C$2:$C${npo},A{j})", f"=C{j}-D{j}-E{j}"])
    last = len(CODES) + 1
    burn.append(["", "Total", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})", f"=SUM(E2:E{last})", f"=SUM(F2:F{last})"])
    money = {c: "#,##0.00" for c in "CDEF"}
    return {
        "Burn": {"header": ["Cost code", "Description", "Budget", "Spent", "Committed", "Remaining"], "rows": burn, "number_formats": money,
                 "widths": {"B": 30, "C": 14, "D": 14, "E": 14, "F": 14}},
        "POs": {"header": ["PO", "Vendor", "Cost code", "Description", "Status", "Original amount", "Approved change orders", "Invoiced",
                           "Still committed"], "rows": po_rows, "widths": {"B": 30, "D": 40}},
        "Invoices": {"header": ["Invoice", "Vendor", "Date", "PO", "Cost code", "Amount", "Status"], "rows": inv_rows, "widths": {"B": 30}},
        "Change orders": {"header": ["CO", "PO", "Date", "Description", "Amount", "Status"], "rows": co_rows, "widths": {"D": 40}},
    }


def naive_workbook(d: dict) -> dict:
    nv = naive(d)
    rows = [[code, name, float(nv[code]["budget"]), float(nv[code]["spent"]), float(nv[code]["committed"]), f"=C{j}-D{j}-E{j}"]
            for j, (code, name) in enumerate(CODES, start=2)]
    rows.append(["", "Total", "=SUM(C2:C11)", "=SUM(D2:D11)", "=SUM(E2:E11)", "=SUM(F2:F11)"])
    return {"Burn": {"header": ["Cost code", "Description", "Budget", "Spent", "Committed", "Remaining"], "rows": rows}}


# --------------------------------------------------------------------------- emit

def emit(seed: int, naive_dir: str | None) -> None:
    d = build(seed)
    if naive_dir:
        os.makedirs(naive_dir, exist_ok=True)
        write_xlsx(os.path.join(naive_dir, "burn.xlsx"), naive_workbook(d), creator="naive")
        return
    ws, ref, sol = task_dirs(HERE)
    r = rng(seed + 29)

    write_xlsx(os.path.join(ws, "west_gallery_budget_board_approved.xlsx"), {"Budget": {
        "merged_title": "West Gallery Renovation - capital budget (approved by the Board, 14 Jan 2026)",
        "header": ["Cost code", "Description", "Approved budget", "Notes"],
        "rows": [[code, name, float(d["rows"][code]["budget"]), "Held by the director; release needs committee vote" if code == "WG-10" else ""]
                 for code, name in CODES] + [["", "TOTAL", float(d["tot"]["budget"]), ""]],
        "number_formats": {"C": "#,##0"}, "widths": {"B": 32, "C": 16, "D": 44}}}, creator="Finance")

    po_rows = [[p["no"], p["vendor"], f"{p['code']} {NAME[p['code']]}", p["desc"], p["issued"].strftime("%m/%d/%Y"), f"${p['amount']:,.2f}", p["status"]]
               for p in d["pos"]]
    write_csv(os.path.join(ws, "purchase_orders_west_gallery.csv"), ["PO Number", "Vendor", "Cost Code", "Description", "Issued", "PO Amount", "Status"],
              po_rows, preamble=["Purchase orders - project WG-26 West Gallery"], crlf=True)

    write_xlsx(os.path.join(ws, "change_order_log.xlsx"), {"Log": {
        "header": ["CO #", "PO", "Date", "Description", "Amount", "Status"],
        "rows": [[c["no"], c["po"]["no"].replace("PO-2026-", "PO "), c["date"], c["desc"], float(c["amount"]), c["status"]] for c in d["cos"]],
        "number_formats": {"E": "#,##0.00"}, "widths": {"B": 10, "C": 12, "D": 44}}}, creator="Facilities")

    styles = [lambda p: p["no"], lambda p: p["no"].replace("PO-", ""), lambda p: f"PO {p['n']}", lambda p: f"PO#{p['n']:03d}"]
    inv_rows = []
    for i in sorted(d["invs"], key=lambda i: (i["date"], i["no"])):
        ref_txt = styles[r.randrange(4)](i["po"]) if i["po"] else ""
        inv_rows.append([i["no"], i["vendor"], i["date"].strftime("%m/%d/%Y"), ref_txt, "" if i["po"] else i["code"], money_str(float(i["amount"]), 1),
                         i["status"]])
    write_csv(os.path.join(ws, "ap_invoices_project_WG-26.csv"), ["Invoice #", "Vendor", "Invoice Date", "PO Ref", "Cost Code (non-PO)", "Amount",
                                                                  "Status"], inv_rows, bom=True)

    write_email_thread(os.path.join(ws, "email_from_director.txt"), [
        {"from": "Alma Reyes <areyes@tidewatermaritime.org>", "to": "Finance <finance@tidewatermaritime.org>", "date": "Mon, 7 Sep 2026 08:31",
         "subject": "West Gallery - budget burn for the capital committee",
         "body": ("The capital committee meets on the 15th and wants to see where the West Gallery project stands against the board budget, "
                  "cost code by cost code: budget, spent, committed and remaining, with totals. Please keep the math live so the "
                  "treasurer can follow it.\n\n"
                  "How I count:\n"
                  "- Spent is every posted invoice. Invoices against a PO belong to that PO's cost code; invoices with no PO carry their own "
                  "cost code. Voided invoices are not spent.\n"
                  "- Committed is what we still owe on open POs: the PO amount plus approved change orders, less what has been invoiced "
                  "against it - never less than zero. Pending and rejected change orders are not commitments yet. Closed and cancelled POs "
                  "have nothing left committed.\n"
                  "- Remaining is budget less spent less committed.\n\n"
                  "The AP export writes the PO reference however the clerk typed it, sorry.\n\nAlma")}])

    write_csv(os.path.join(ref, "burn.csv"), ["cost_code", "description", "budget", "spent", "committed", "remaining"],
              [[code, name, f"{d['rows'][code]['budget']:.2f}", f"{d['rows'][code]['spent']:.2f}", f"{d['rows'][code]['committed']:.2f}",
                f"{d['rows'][code]['remaining']:.2f}"] for code, name in CODES])
    write_xlsx(os.path.join(sol, "burn.xlsx"), workbook(d), creator="Tidewater Maritime Museum")

    rows, tot, ro = d["rows"], d["tot"], d["roles"]

    def pin(name, code, field, near):
        v = float(rows[code][field])
        return {"type": "xlsx_value_present", "name": name, "path": "burn.xlsx", "expected": v, "rel_tol": 1e-07, "near_text": near}

    write_task_yaml(HERE, {
        "id": "project-budget-burn", "track": "desk", "category": "bookkeeping",
        "title": "West Gallery budget burn for the capital committee",
        "ask": "Alma needs the West Gallery budget burn for the capital committee - where each cost code stands. Her email explains how she counts it. Save it as burn.xlsx.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            f"invoices billed against {ro['fab']['no']} are already inside the PO; adding them to spent and the PO's full value to committed "
            "counts the fabrication work twice (checks: exhibit fabrication committed; total committed)",
            f"{ro['fab']['no']} has two approved change orders, one of them a deduction, plus a pending and a rejected one that are not "
            "commitments (check: exhibit fabrication committed)",
            f"Seaboard Mechanical's final invoice on {ro['hvac']['no']} includes the dehumidifier on a change order that is still pending, so "
            "its invoices exceed the PO: spent takes every posted invoice and committed stops at zero instead of going negative "
            "(check: HVAC remaining)",
            f"{ro['elec']['no']} was closed short after the final invoice; the unbilled balance is not committed, while the small open "
            "electrical PO still is (check: electrical remaining)",
            "one Lumenharbor Lighting invoice was entered twice and the copy voided, and the AP export writes PO references as "
            f"'{ro['light']['no']}', '{ro['light']['no'][3:]}', 'PO {ro['light']['n']}' and 'PO#{ro['light']['n']:03d}' "
            "(check: gallery lighting spent)",
            "the architect's, engineer's and permit invoices have no PO and carry their cost code directly; a join through POs alone drops "
            "them (check: design fees spent)",
            f"{ro['av_old']['no']} to the replaced AV integrator was cancelled and commits nothing; the change order log writes POs as "
            f"'PO {ro['fab']['n']}' and the budget sheet has a static TOTAL row (checks: total committed; total remaining)",
        ],
        "checks": [
            {"type": "xlsx_has_formulas", "name": "live formulas", "path": "burn.xlsx", "min_count": 12},
            {"type": "xlsx_no_errors", "name": "no error cells", "path": "burn.xlsx"},
            pin("exhibit fabrication committed", "WG-05", "committed", "fabrication"),
            pin("HVAC remaining", "WG-04", "remaining", "hvac"),
            pin("electrical remaining", "WG-03", "remaining", "electrical"),
            pin("gallery lighting spent", "WG-06", "spent", "lighting"),
            pin("design fees spent", "WG-08", "spent", "design"),
            {"type": "xlsx_value_present", "name": "total committed", "path": "burn.xlsx", "expected": float(tot["committed"]), "rel_tol": 1e-07,
             "near_text": "total"},
            {"type": "xlsx_value_present", "name": "total remaining", "path": "burn.xlsx", "expected": float(tot["remaining"]), "rel_tol": 1e-07,
             "near_text": "total"},
        ],
    })
    print(f"seed={seed} " + " ".join(f"{c}:{v['spent']}/{v['committed']}/{v['remaining']}" for c, v in rows.items()) + f" tot={tot}")


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
