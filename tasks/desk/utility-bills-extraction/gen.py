#!/usr/bin/env python3
"""utility-bills-extraction: electricity and water bills to usage and charges per account per month.

    python gen.py [--seed N]

Business: a Montessori school pays electricity for its main building, its annex and its parking lot lights,
and water for the main building. The business manager wants July and August usage and charges per account
for the facilities budget.

Traps (each caught by a check, see task.yaml):
  * the co-op's summary bill carries two accounts (main building and annex); each is its own row and the bill
    total is neither                                                     (checks: one row per account per month; current charges)
  * the annex's August read and the water July read are estimates, coded E in the read column (check: read types and units)
  * late payment charges sit inside the annex's July charges and on the August lighting bill; they belong in
    late_fee, not current_charges; amount due also carries a previous balance (checks: current charges; late fees)
  * water is billed in CCF; the note wants gallons (748 per CCF, explained on the bill) (check: usage)
  * the lighting bills are dated the month after the service period ends; the row month is the period's end month
    (check: one row per account per month)
  * the July lighting bill is an image-only scan                          (checks: usage; current charges)
"""
from __future__ import annotations
import os, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

SCHOOL = "Fernbrook Montessori School"
MM = 2.8346
GAL_PER_CCF = 748


def m(x): return f"${x:,.2f}"


def build(seed: int) -> dict:
    r = rng(seed)
    acct = lambda: f"{r.randint(3300, 3399)}-{r.randint(1000, 9999)}"
    base = acct()
    E_MAIN = dict(no=f"{base}-01", name="Main Building", addr="1400 Laurel Ct", utility="electric", unit="kWh")
    E_ANNEX = dict(no=f"{base}-02", name="Annex", addr="1412 Laurel Ct", utility="electric", unit="kWh")
    E_LIGHT = dict(no=f"{r.randint(7700, 7799)}-{r.randint(1000, 9999)}-{r.randint(10, 99)}", name="Parking lot lighting", addr="1400 Laurel Ct LOT", utility="electric", unit="kWh")
    W_MAIN = dict(no=f"WTR-{r.randint(40000, 49999)}", name="Main Building", addr="1400 Laurel Ct", utility="water", unit="gallons")
    rate = round(r.uniform(0.108, 0.126), 4)
    bills = {}

    def elec(a, month, prev, kwh, basic, estimated=False, late=0.0, period=None):
        energy = round(kwh * rate, 2); ppc = round(energy * 0.03, 2); tax = round((basic + energy + ppc) * 0.015, 2)
        cur = round(basic + energy + ppc + tax, 2)
        return dict(acct=a, month=month, prev=prev, curr=prev + kwh, usage=kwh, basic=basic, energy=energy, ppc=ppc, tax=tax, current=cur,
                    late=late, read="estimated" if estimated else "actual", period=period)

    mp = r.randint(40000, 60000); ap = r.randint(15000, 25000); lp = r.randint(8000, 12000)
    k = [r.randint(3400, 4600), r.randint(3600, 4900)]
    ka = [r.randint(1100, 1700), r.randint(1200, 1800)]
    kl = [r.randint(820, 980), r.randint(760, 940)]
    late_annex = round(r.choice([9.75, 11.40, 12.85, 14.10]), 2)
    late_light = round(r.choice([5.00, 6.25, 7.50]), 2)
    bills["E_MAIN_07"] = elec(E_MAIN, "2026-07", mp, k[0], 42.00, period=(date(2026, 6, 18), date(2026, 7, 17)))
    bills["E_MAIN_08"] = elec(E_MAIN, "2026-08", mp + k[0], k[1], 42.00, period=(date(2026, 7, 18), date(2026, 8, 17)))
    bills["E_ANNEX_07"] = elec(E_ANNEX, "2026-07", ap, ka[0], 24.00, late=late_annex, period=(date(2026, 6, 18), date(2026, 7, 17)))
    bills["E_ANNEX_08"] = elec(E_ANNEX, "2026-08", ap + ka[0], ka[1], 24.00, estimated=True, period=(date(2026, 7, 18), date(2026, 8, 17)))
    bills["E_LIGHT_07"] = elec(E_LIGHT, "2026-07", lp, kl[0], 11.50, period=(date(2026, 6, 26), date(2026, 7, 27)))
    bills["E_LIGHT_08"] = elec(E_LIGHT, "2026-08", lp + kl[0], kl[1], 11.50, late=late_light, period=(date(2026, 7, 28), date(2026, 8, 26)))

    def water(month, prev, ccf, estimated, period):
        wbase = 28.40; t1 = min(ccf, 15); t2 = ccf - t1
        wuse = round(t1 * 3.12 + t2 * 4.05, 2); sewer = round(ccf * 5.26, 2); storm = 11.75
        cur = round(wbase + wuse + sewer + storm, 2)
        return dict(acct=W_MAIN, month=month, prev=prev, curr=prev + ccf, ccf=ccf, usage=ccf * GAL_PER_CCF, t1=t1, t2=t2, wbase=wbase, wuse=wuse,
                    sewer=sewer, storm=storm, current=cur, late=0.0, read="estimated" if estimated else "actual", period=period)
    wp = r.randint(1100, 1400); c1 = r.randint(24, 34); c2 = r.randint(18, 30)
    bills["W_MAIN_07"] = water("2026-07", wp, c1, True, (date(2026, 6, 12), date(2026, 7, 11)))
    bills["W_MAIN_08"] = water("2026-08", wp + c1, c2, False, (date(2026, 7, 12), date(2026, 8, 11)))
    prev_bal = {"07": round(r.uniform(500, 900), 2), "08": None}
    return dict(bills=bills, rate=rate, accts=[E_MAIN, E_ANNEX, E_LIGHT, W_MAIN], prev_bal=prev_bal, mgr=person(r))


def emit(seed: int) -> None:
    d = build(seed); B = d["bills"]; rate = d["rate"]
    ws, ref, sol = task_dirs(HERE)
    F = os.path.join(ws, "utility_bills"); os.makedirs(F, exist_ok=True)

    # ---- Northfork combined summary bills (Helvetica, letter)
    for mo, bill_date, due in (("07", "July 24, 2026", "August 14, 2026"), ("08", "August 24, 2026", "September 14, 2026")):
        main, annex = B[f"E_MAIN_{mo}"], B[f"E_ANNEX_{mo}"]
        acc_total = lambda b: round(b["current"] + b["late"], 2)
        new_charges = round(acc_total(main) + acc_total(annex), 2)
        if mo == "07":
            prev = d["prev_bal"]["07"]; paid = round(prev - (annex["late"] and round(prev * 0.35, 2)), 2)
        else:
            prev = round(acc_total(B["E_MAIN_07"]) + acc_total(B["E_ANNEX_07"]) + (d["prev_bal"]["07"] - round(d["prev_bal"]["07"] - round(d["prev_bal"]["07"] * 0.35, 2), 2)), 2)
            paid = prev
        due_amt = round(prev - paid + new_charges, 2)
        blocks = [
            ("title", "Northfork Electric Cooperative"), ("small", "PO Box 880, Madison, WI 53701  |  Member services 608-555-0170  |  northfork.example"),
            ("hr", None),
            ("kv", [("Member", SCHOOL), ("Summary bill number", f"SB-{d['accts'][0]['no'][:9]}-{mo}"), ("Bill date", bill_date), ("Due date", due)],
             {"col_widths": [45 * MM, 120 * MM]}),
            ("h", "Summary of accounts"),
            ("table", [["Account", "Service location", "Service period", "Charges"],
                       [main["acct"]["no"], f"{main['acct']['addr']} ({main['acct']['name']})", f"{main['period'][0]:%m/%d/%Y} - {main['period'][1]:%m/%d/%Y}", m(acc_total(main))],
                       [annex["acct"]["no"], f"{annex['acct']['addr']} ({annex['acct']['name']})", f"{annex['period'][0]:%m/%d/%Y} - {annex['period'][1]:%m/%d/%Y}", m(acc_total(annex))]],
             {"col_widths": [32 * MM, 58 * MM, 50 * MM, 30 * MM], "shade_header": True}),
            ("spacer", 6),
            ("kv", [("Previous balance", m(prev)), ("Payment received - thank you", f"-{m(paid)}"), ("New charges, all accounts", m(new_charges)),
                    ("TOTAL AMOUNT DUE", m(due_amt))], {"col_widths": [70 * MM, 40 * MM]}),
        ]
        for b in (main, annex):
            a = b["acct"]
            code = "E" if b["read"] == "estimated" else "A"
            rows = [["Charge", "Detail", "Amount"], ["Basic service charge", "", m(b["basic"])],
                    ["Energy charge", f"{b['usage']:,} kWh x ${rate:.4f}", m(b["energy"])], ["Public purpose charge", "3% of energy", m(b["ppc"])],
                    ["State utility tax", "1.5%", m(b["tax"])]]
            if b["late"]:
                rows.append(["Late payment charge", "past-due balance", m(b["late"])])
            rows.append(["Total this account", "", m(acc_total(b))])
            blocks += [
                ("h", f"Account {a['no']} - {a['name']}"),
                ("table", [["Meter", "Previous read", "Current read", "kWh used"],
                           [f"M{a['no'][-2:]}{a['no'][5:9]}", f"{b['prev']:,} A", f"{b['curr']:,} {code}", f"{b['usage']:,}"]],
                 {"col_widths": [40 * MM, 40 * MM, 40 * MM, 40 * MM]}),
                ("spacer", 3),
                ("table", rows, {"col_widths": [60 * MM, 60 * MM, 40 * MM]}),
            ]
        blocks += [("spacer", 8), ("small", "Read codes: A = actual meter read, E = estimated read (meter not accessible). Estimated reads are trued up on your next actual read. "
                                          "A late payment charge applies to balances unpaid after the due date.")]
        write_pdf_document(os.path.join(F, f"Northfork_summary_bill_{'Jul' if mo == '07' else 'Aug'}2026.pdf"), blocks, font="Helvetica", base_size=9)

    # ---- lighting July: image-only scan
    L7 = B["E_LIGHT_07"]; la = L7["acct"]
    write_scan_pdf(os.path.join(F, "scan_lot_lighting_bill.pdf"), [
        "NORTHFORK ELECTRIC COOPERATIVE", "", f"Account: {la['no']}", f"Service: {la['name']}", f"Location: {la['addr']}", "Bill date: 08/03/2026",
        f"Service period: {L7['period'][0]:%m/%d/%Y} to {L7['period'][1]:%m/%d/%Y}", "",
        f"Previous read: {L7['prev']:,} A", f"Current read: {L7['curr']:,} A", f"Energy used: {L7['usage']:,} kWh", "",
        f"Basic service charge {m(L7['basic'])}", f"Energy {L7['usage']} kWh x {rate:.4f} {m(L7['energy'])}", f"Public purpose charge {m(L7['ppc'])}",
        f"State utility tax {m(L7['tax'])}", f"Current charges {m(L7['current'])}", "", f"Amount due by 08/24/2026: {m(L7['current'])}"],
        font_size=32, seed=seed * 11 + 5, skew_deg=-0.3, noise=260)

    # ---- lighting August: Courier text bill with late charge and past due
    L8 = B["E_LIGHT_08"]
    past_due = L7["current"]
    write_pdf_document(os.path.join(F, "lighting_acct_statement_0902.pdf"), [
        ("right", "Statement date: 09/02/2026"), ("title", "NORTHFORK ELECTRIC CO-OP"),
        ("p", f"{SCHOOL}<br/>1400 Laurel Ct, Madison, WI 53703"), ("hr", None),
        ("table", [["ACCOUNT", "SERVICE", "PERIOD"], [la["no"], la["name"], f"{L8['period'][0]:%m/%d/%y}-{L8['period'][1]:%m/%d/%y}"]], {"col_widths": [55 * MM, 55 * MM, 60 * MM], "grid": True}),
        ("spacer", 6),
        ("table", [["METER READS", "PREVIOUS", "PRESENT", "USAGE"], ["kWh", f"{L8['prev']}", f"{L8['curr']}", f"{L8['usage']}"]], {"col_widths": [45 * MM, 40 * MM, 40 * MM, 40 * MM], "grid": True}),
        ("small", "All reads this period are actual reads."),
        ("spacer", 6),
        ("h", "ACCOUNT ACTIVITY"),
        ("table", [["", "AMOUNT"], ["Balance from last statement", m(past_due)], ["Payments received", "$0.00"], ["Past due", m(past_due)],
                   ["Late payment charge", m(L8["late"])], ["Basic service charge", m(L8["basic"])], [f"Energy charge {L8['usage']} kWh", m(L8["energy"])],
                   ["Public purpose charge", m(L8["ppc"])], ["State utility tax", m(L8["tax"])],
                   ["TOTAL DUE 09/23/2026", m(round(past_due + L8["late"] + L8["current"], 2))]], {"col_widths": [110 * MM, 50 * MM]}),
        ("spacer", 8), ("p", "Your account is past due. Please pay the past due amount immediately to avoid disconnection of service."),
    ], font="Courier", base_size=9)

    # ---- water bills (Times-Roman, A4)
    for mo, bdate in (("07", "07/20/2026"), ("08", "08/19/2026")):
        wb = B[f"W_MAIN_{mo}"]; wa = wb["acct"]
        code = "E" if wb["read"] == "estimated" else "A"
        prev_code = "E" if mo == "08" else "A"
        write_pdf_document(os.path.join(F, f"RiverbendWater_{mo}-2026.pdf"), [
            ("title", "Riverbend Water District"), ("small", "Customer service 608-555-0188  |  220 River St, Madison, WI 53703"), ("hr", None),
            ("kv", [("Customer", SCHOOL), ("Account number", wa["no"]), ("Service address", wa["addr"]), ("Bill date", bdate),
                    ("Billing period", f"{wb['period'][0]:%B %-d, %Y} to {wb['period'][1]:%B %-d, %Y}")], {"col_widths": [40 * MM, 120 * MM]}),
            ("spacer", 6),
            ("table", [["Meter", "Prior read", "Code", "Current read", "Code", "Consumption (CCF)"],
                       [f"W-{wa['no'][4:]}", str(wb["prev"]), prev_code, str(wb["curr"]), code, str(wb["ccf"])]],
             {"col_widths": [25 * MM, 25 * MM, 15 * MM, 28 * MM, 15 * MM, 40 * MM], "grid": True, "shade_header": True}),
            ("spacer", 6),
            ("table", [["Charges", "", "Amount"], ["Water base charge", "", m(wb["wbase"])],
                       ["Water usage", f"{wb['t1']} CCF x $3.12" + (f" + {wb['t2']} CCF x $4.05" if wb["t2"] else ""), m(wb["wuse"])],
                       ["Sewer", f"{wb['ccf']} CCF x $5.26", m(wb["sewer"])], ["Stormwater utility fee", "", m(wb["storm"])],
                       ["Current charges", "", m(wb["current"])]], {"col_widths": [55 * MM, 70 * MM, 35 * MM]}),
            ("spacer", 6),
            ("kv", [("Previous balance", m(B["W_MAIN_07"]["current"]) if mo == "08" else "$0.00"),
                    ("Payments", f"-{m(B['W_MAIN_07']['current'])}" if mo == "08" else "$0.00"), ("Amount due", m(wb["current"]))], {"col_widths": [40 * MM, 40 * MM]}),
            ("h", "Understanding your bill"),
            ("small", "Consumption is measured in CCF (one hundred cubic feet). 1 CCF = 748 gallons. Read codes: A = actual read, E = estimated read. "
                      "When a meter cannot be read, consumption is estimated from your history and corrected at the next actual read."),
        ], pagesize="a4", font="Times-Roman", base_size=10)

    mg = d["mgr"]
    write_text(os.path.join(ws, "note_from_business_manager.txt"),
        "For the facilities budget I need July and August usage and charges for every utility account, one row per account per month, "
        "in utility_usage.csv:\n\n"
        "row_id - account number, underscore, month (e.g. 1234-5678_2026-07)\n"
        "account_number - as printed on the bill\n"
        "utility - electric or water\n"
        "service_month - YYYY-MM of the month the service period ends in (not the bill date)\n"
        "usage - electricity in kWh, water in gallons\n"
        "usage_unit - kWh or gallons\n"
        "read_type - actual or estimated (the current read for that period)\n"
        "current_charges - the charges for that period's service only: no late fees, no previous balance\n"
        "late_fee - any late payment charge on that account's bill for the month, 0 if none\n\n"
        f"Thanks - {mg[0]} {mg[1]}, Business Manager\n")

    header = ["row_id", "account_number", "utility", "service_month", "usage", "usage_unit", "read_type", "current_charges", "late_fee"]
    rows = []
    for key in ["E_MAIN_07", "E_MAIN_08", "E_ANNEX_07", "E_ANNEX_08", "E_LIGHT_07", "E_LIGHT_08", "W_MAIN_07", "W_MAIN_08"]:
        b = B[key]; a = b["acct"]
        rows.append([f"{a['no']}_{b['month']}", a["no"], a["utility"], b["month"], b["usage"], a["unit"], b["read"], f"{b['current']:.2f}", f"{b['late']:.2f}"])
    write_csv(os.path.join(ref, "utility_usage.csv"), header, rows)
    write_csv(os.path.join(sol, "utility_usage.csv"), header, rows)
    rid = lambda k: f"{B[k]['acct']['no']}_{B[k]['month']}"
    write_json(os.path.join(ref, "notes.json"), {"estimated": [rid("E_ANNEX_08"), rid("W_MAIN_07")], "late": {rid("E_ANNEX_07"): B["E_ANNEX_07"]["late"], rid("E_LIGHT_08"): B["E_LIGHT_08"]["late"]},
                                                 "water_ccf": {rid("W_MAIN_07"): B["W_MAIN_07"]["ccf"], rid("W_MAIN_08"): B["W_MAIN_08"]["ccf"]},
                                                 "lighting_bill_months": {"2026-07": "2026-08", "2026-08": "2026-09"}, "light_account": B["E_LIGHT_07"]["acct"]["no"]})
    write_task_yaml(HERE, {
        "id": "utility-bills-extraction", "track": "desk", "category": "extraction",
        "title": "Monthly usage and charges from the utility bills",
        "ask": "Can you pull July and August usage and charges off our electric and water bills into utility_usage.csv? The bills are in the folder and my note has the layout I need for the budget.\n",
        "followup": None, "timeout_s": 1800,
        "traps": [
            "each Northfork summary bill carries two accounts, the main building and the annex, with a summary table, a previous balance, a payment and a total due; each account is its own row and neither the new-charges line nor the total due is an account's charges (checks: one row per account per month; current charges)",
            "the annex's August current read and the water July current read are coded E, explained only in a footnote; the water August bill's prior read is also coded E, which does not make August estimated (check: read types and units)",
            "a late payment charge sits inside the annex's July charge table, whose 'Total this account' includes it, and another on the August lighting statement between the past-due balance and the service charges; both go in late_fee and stay out of current_charges (checks: current charges; late fees)",
            "water consumption is billed in CCF and the note wants gallons, 748 per CCF per the bill's explanation (check: usage)",
            "the lighting bills are dated 3 August and 2 September for periods ending 27 July and 26 August; filing them by bill date shifts both rows a month (check: one row per account per month)",
            "the July lighting bill is an image-only scan (checks: usage; current charges)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": "utility_usage.csv", "columns": header},
            {"type": "csv_set_equal", "name": "one row per account per month", "path": "utility_usage.csv", "column": "row_id", "ref": "utility_usage.csv", "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": "utility_usage.csv", "equals_ref": "utility_usage.csv"},
            {"type": "csv_values_match", "name": "account, utility and month", "path": "utility_usage.csv", "ref": "utility_usage.csv", "key": "row_id",
             "columns": ["account_number", "utility", "service_month"], "min_accuracy": 1.0},
            {"type": "csv_values_match", "name": "usage", "path": "utility_usage.csv", "ref": "utility_usage.csv", "key": "row_id",
             "columns": ["usage"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": [rid("W_MAIN_07"), rid("W_MAIN_08"), rid("E_LIGHT_07")]},
            {"type": "csv_values_match", "name": "read types and units", "path": "utility_usage.csv", "ref": "utility_usage.csv", "key": "row_id",
             "columns": ["read_type", "usage_unit"], "min_accuracy": 1.0, "must_match_keys": [rid("E_ANNEX_08"), rid("W_MAIN_07"), rid("W_MAIN_08")]},
            {"type": "csv_values_match", "name": "current charges", "path": "utility_usage.csv", "ref": "utility_usage.csv", "key": "row_id",
             "columns": ["current_charges"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0,
             "must_match_keys": [rid("E_MAIN_07"), rid("E_ANNEX_07"), rid("E_LIGHT_07"), rid("E_LIGHT_08")]},
            {"type": "csv_values_match", "name": "late fees", "path": "utility_usage.csv", "ref": "utility_usage.csv", "key": "row_id",
             "columns": ["late_fee"], "numeric": True, "tolerance": 0.01, "min_accuracy": 1.0, "must_match_keys": [rid("E_ANNEX_07"), rid("E_LIGHT_08"), rid("E_MAIN_07")]},
        ],
    })


if __name__ == "__main__":
    emit(argparse_seed())
