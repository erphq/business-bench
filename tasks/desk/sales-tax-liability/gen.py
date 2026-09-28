#!/usr/bin/env python3
"""sales-tax-liability: a garden centre's second-quarter sales into tax due per local jurisdiction for the return.

    python gen.py [--seed N] [--naive DIR]
    python gen.py --list-knobs
    python gen.py --rules 3 --trap-count expired_cert=3 --out DIR    # a harder task; the answer moves
    python gen.py --describe [--scale N ...]                          # content counts of this draw

Business: Quarry Road Nursery sells plants, stone and soil from two yards (Cedar Falls and Millbrook) and delivers to
homeowners and landscapers around the county. Landscapers buying for resale give exemption certificates. The state
return wants each local jurisdiction's gross, exempt and taxable sales and the tax due.

Traps (each caught by a check, see task.yaml):
  * deliveries are taxed where they are delivered, by ZIP; the town in the address is the post office's (checks: gross; taxable)
  * certificate exemptions by sale date: one landscaper's certificate expired mid-quarter and the POS kept exempting
                                                                                           (checks: exempt; taxable; tax due)
  * Millbrook's rate went up on 1 May; the POS kept the old rate for a week                (check: tax due)
  * tax is computed on each jurisdiction's taxable sales and rounded once, not summed from penny-rounded receipts (check: tax due)
  * voided invoices are still in the export                                                (checks: gross; taxable)
  * a jurisdiction in the rate table has no sales and gets no row                          (check: one row per jurisdiction)
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
from bizgen.knobs import Knob, KnobSet, add_knob_args, describe_json, output_dirs, parse_knob_args, record  # noqa: E402

# Difficulty knobs (docs/authoring-knobs.md). The defaults are the published task and leave every draw as it was.
KNOBS = KnobSet(
    Knob("scale", "scale", default=1, levels=(1, 2, 4),
         changes="ordinary POS sales per trading day are multiplied by N (about 250 invoices at 1)", measure="rows"),
    Knob("rules", "rules", default=1, levels=(1, 2, 3),
         changes="jurisdictions whose rate changes mid-quarter while the POS lags a week behind (1 = Millbrook only; "
                 "2 adds Pine Ridge on 1 June; 3 adds Lake Haven on 15 May)", measure="rules"),
    Knob("trap_count.expired_cert", "trap-count", default=1, levels=(1, 2, 3),
         changes="landscapers whose resale certificate expires mid-quarter while the POS keeps exempting them",
         measure="trap_instances.expired_cert"),
)
# Extra mid-quarter rate changes (rules > 1): (code, town, old rate, new rate, effective, POS updated).
EXTRA_CHANGES = [("3205", "Pine Ridge", "0.0685", "0.0710", date(2026, 6, 1), date(2026, 6, 9)),
                 ("3210", "Lake Haven", "0.0710", "0.0735", date(2026, 5, 15), date(2026, 5, 22))]
# Extra certificates that expire mid-quarter (trap_count.expired_cert > 1): (customer id, expiry).
EXTRA_EXPIRED = [("L-2214", date(2026, 6, 5)), ("L-2201", date(2026, 4, 24))]

Q0, Q1 = date(2026, 4, 1), date(2026, 6, 30)
CHANGE = date(2026, 5, 1)
POS_UPDATED = date(2026, 5, 8)
TEMPLATE = ["jurisdiction_code", "jurisdiction_name", "gross_sales", "exempt_sales", "taxable_sales", "tax_due"]
# code, name, zips, rate(s): [(from, to, rate)]
JURIS = [
    ("3101", "City of Cedar Falls", ["98011", "98012"], [(None, None, "0.0725")]),
    ("3102", "City of Millbrook", ["98031"], [(None, date(2026, 4, 30), "0.0775"), (CHANGE, None, "0.0800")]),
    ("3205", "City of Pine Ridge", ["98045", "98046"], [(None, None, "0.0685")]),
    ("3210", "Town of Lake Haven", ["98052"], [(None, None, "0.0710")]),
    ("3301", "Oak County - unincorporated", ["98013", "98033", "98060"], [(None, None, "0.0650")]),
    ("3320", "City of Stoneleigh", ["98071"], [(None, None, "0.0735")]),
]
POSTAL_TOWN = {"98011": "Cedar Falls", "98012": "Cedar Falls", "98013": "Cedar Falls", "98031": "Millbrook", "98033": "Millbrook",
               "98045": "Pine Ridge", "98046": "Pine Ridge", "98052": "Lake Haven", "98060": "Pine Ridge", "98071": "Stoneleigh"}
STORES = {"Cedar Falls yard": "98011", "Millbrook yard": "98031"}
ITEMS = [("Bark mulch (yd)", 42.0), ("Topsoil blend (yd)", 48.0), ("Flagstone (ton)", 385.0), ("River rock (ton)", 165.0), ("Japanese maple 5gal", 129.0),
         ("Boxwood 3gal", 34.0), ("Perennial flat", 58.0), ("Drip irrigation kit", 89.0), ("Compost (yd)", 39.0), ("Arborvitae 6ft", 149.0)]


def D(x) -> Decimal:
    return Decimal(str(x))


def r2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rate_for(code, day, juris=JURIS):
    for c_, _, _, rates in juris:
        if c_ == code:
            for f, t, rt in rates:
                if (f is None or day >= f) and (t is None or day <= t):
                    return D(rt)
    raise KeyError(code)


def zip_juris(z):
    for c_, _, zips, _ in JURIS:
        if z in zips:
            return c_
    raise KeyError(z)


def knob_juris(n: int) -> tuple[list, list]:
    """The rate table and the POS lags with n jurisdictions changing rate mid-quarter (n > 1 only)."""
    juris = [list(j) for j in JURIS]
    lags = [("3102", CHANGE, POS_UPDATED)]
    for code_, _, old, new, eff, upd in EXTRA_CHANGES[:n - 1]:
        j = next(j for j in juris if j[0] == code_)
        j[3] = [(None, eff - timedelta(days=1), old), (eff, None, new)]
        lags.append((code_, eff, upd))
    return [tuple(j) for j in juris], lags


def build(seed: int, knobs=KNOBS.defaults()) -> dict:
    r = rng(seed)
    scale = knobs["scale"]
    homeowners = [f"{f} {l}" for f, l in people(r, 40)]
    landscapers = [("L-2201", "Cedar & Pine Landscaping"), ("L-2207", "Greenway Grounds LLC"), ("L-2214", "Ridgeback Hardscapes"),
                   ("L-2219", "Blue Heron Garden Design"), ("L-2226", "Oak County Parks Dept")]
    certs = {
        "L-2201": {"type": "Resale", "no": f"RS-{r.randint(100000, 999999)}", "expires": date(2027, 3, 31)},
        "L-2207": {"type": "Resale", "no": f"RS-{r.randint(100000, 999999)}", "expires": date(2026, 5, 15)},   # expires mid-quarter
        "L-2214": {"type": "Resale", "no": f"RS-{r.randint(100000, 999999)}", "expires": date(2028, 1, 31)},
        "L-2226": {"type": "Government", "no": "GOV-EXEMPT", "expires": None},
    }
    # L-2219 has no certificate on file (the POS never exempted them either)
    invoices = []
    n = 0
    day = Q0
    while day <= Q1:
        for _ in range(r.randint(1, 4) * scale if day.weekday() < 6 else 0):
            n += 1
            kind = r.random()
            if kind < 0.45:
                cust_id, cust = "", "Walk-in"
                store = r.choice(list(STORES))
                fulfil, z = f"Pickup - {store}", STORES[store]
                ship_town = ""
            elif kind < 0.75:
                cust_id, cust = f"H-{3000 + homeowners.index(r.choice(homeowners))}", None
                cust = homeowners[int(cust_id[2:]) - 3000]
                fulfil = "Delivery"
                z = r.choice(["98011", "98012", "98013", "98031", "98033", "98045", "98046", "98052", "98060"])
                ship_town = POSTAL_TOWN[z]
            else:
                cust_id, cust = r.choice(landscapers)
                if r.random() < 0.5:
                    store = r.choice(list(STORES)); fulfil, z, ship_town = f"Pickup - {store}", STORES[store], ""
                else:
                    fulfil = "Delivery"
                    z = r.choice(["98011", "98013", "98031", "98033", "98045", "98052", "98060"]); ship_town = POSTAL_TOWN[z]
            lines = r.sample(ITEMS, r.randint(1, 3))
            amt = D("0")
            for _, price in lines:
                qty = r.randint(1, 6) if price < 100 else r.randint(1, 2)
                amt += D(price) * qty
            if r.random() < 0.3:
                amt = r2(amt * D("0.9"))    # 10% off
            invoices.append({"no": f"QR-{24000 + n}", "date": day, "cust_id": cust_id, "cust": cust, "fulfil": fulfil, "zip": z,
                             "town": ship_town, "amount": amt, "void": False, "items": "; ".join(x for x, _ in lines)})
        day += timedelta(days=1)
    # voids: a handful of invoices re-keyed
    for inv in r.sample(invoices, 6):
        inv["void"] = True
    # make sure L-2207 buys both before and after the expiry, and Millbrook deliveries sit in the POS-stale week
    def add(day, cust_id, cust, fulfil, z, amount, items):
        nonlocal n
        n += 1
        invoices.append({"no": f"QR-{24000 + n}", "date": day, "cust_id": cust_id, "cust": cust, "fulfil": fulfil, "zip": z,
                         "town": POSTAL_TOWN[z] if fulfil == "Delivery" else "", "amount": D(amount), "void": False, "items": items})
    add(date(2026, 5, 20), "L-2207", "Greenway Grounds LLC", "Delivery", "98045", r.choice([2310, 1985, 2740]), "Flagstone (ton); River rock (ton)")
    add(date(2026, 6, 11), "L-2207", "Greenway Grounds LLC", "Pickup - Cedar Falls yard", "98011", r.choice([1540, 1265, 1820]), "Arborvitae 6ft")
    add(date(2026, 5, 4), "", "Walk-in", "Pickup - Millbrook yard", "98031", r.choice([915, 1245, 780]), "Flagstone (ton)")
    add(date(2026, 5, 6), f"H-{3001}", homeowners[1], "Delivery", "98031", r.choice([652, 548, 1033]), "Topsoil blend (yd); Bark mulch (yd)")

    # knob-only content, drawn from its own stream after every default draw (none of this runs at the defaults)
    juris, lags = JURIS, None
    if knobs["rules"] > 1 or knobs.trap_count("expired_cert") > 1:
        rk = rng(seed + 7_000_003)
        names_ = dict(landscapers)
        if knobs["rules"] > 1:
            juris, lags = knob_juris(knobs["rules"])
            for code_, eff, upd in lags[1:]:
                z = next(j for j in juris if j[0] == code_)[2]
                for _ in range(2):
                    k = rk.randrange(40)
                    add(eff + timedelta(days=rk.randint(0, (upd - eff).days - 1)), f"H-{3000 + k}", homeowners[k], "Delivery",
                        rk.choice(z), rk.choice([486, 735, 1120, 1395]), "; ".join(x for x, _ in rk.sample(ITEMS, 2)))
        for cid, exp in EXTRA_EXPIRED[:knobs.trap_count("expired_cert") - 1]:
            certs[cid]["expires"] = exp
            for when, fulfil, z in ((exp - timedelta(days=rk.randint(3, 12)), "Delivery", rk.choice(["98011", "98052"])),
                                    (exp + timedelta(days=rk.randint(4, 14)), "Delivery", rk.choice(["98045", "98052", "98011"])),
                                    (exp + timedelta(days=rk.randint(15, 30)), "Pickup - Millbrook yard", "98031")):
                add(min(when, Q1), cid, names_[cid], fulfil, z, rk.choice([1180, 1465, 1930, 2215]),
                    "; ".join(x for x, _ in rk.sample(ITEMS, 2)))
    invoices.sort(key=lambda i: (i["date"], i["no"]))
    for k, inv in enumerate(invoices):
        inv["no"] = f"QR-{24001 + k}"

    # ---- truth ----
    agg = {c_: {"gross": D(0), "exempt": D(0), "tax_raw": D(0), "receipt_tax": D(0), "pos_tax": D(0)} for c_, *_ in JURIS}
    for inv in invoices:
        code_ = zip_juris(inv["zip"])
        inv["juris"] = code_
        cert = certs.get(inv["cust_id"])
        exempt = bool(cert) and (cert["expires"] is None or inv["date"] <= cert["expires"])
        pos_exempt = bool(cert)                       # POS never noticed the expiry
        rate = rate_for(code_, inv["date"])
        pos_rate = rate_for(code_, min(inv["date"], date(2026, 4, 30))) if code_ == "3102" and inv["date"] < POS_UPDATED else rate
        if lags:
            rate = rate_for(code_, inv["date"], juris)
            pos_rate = next((rate_for(code_, eff - timedelta(days=1), juris) for c2_, eff, upd in lags
                             if c2_ == code_ and eff <= inv["date"] < upd), rate)
        inv["tax_collected"] = D(0) if pos_exempt else r2(inv["amount"] * pos_rate)
        inv["pos_exempt"] = pos_exempt
        inv["exempt"] = exempt
        if inv["void"]:
            continue
        a = agg[code_]
        a["gross"] += inv["amount"]
        if exempt:
            a["exempt"] += inv["amount"]
        else:
            a["tax_raw"] += inv["amount"] * rate
            a["receipt_tax"] += r2(inv["amount"] * rate)
        a["pos_tax"] += inv["tax_collected"]
    for a in agg.values():
        a["taxable"] = a["gross"] - a["exempt"]
        a["tax_due"] = r2(a["tax_raw"])
    return {"invoices": invoices, "agg": agg, "certs": certs, "landscapers": landscapers, "juris": juris, "lags": lags}


def acceptable(d):
    agg = d["agg"]
    if agg["3320"]["gross"] != 0:
        return False
    diffs = [abs(a["tax_due"] - a["receipt_tax"]) for c_, a in agg.items() if a["gross"] > 0]
    if sum(1 for x in diffs if x >= D("0.02")) < 3:
        return False
    for a in agg.values():                       # no half-cent ties anywhere
        frac = (a["tax_raw"] * 100) % 1
        if abs(frac - D("0.5")) < D("0.0001"):
            return False
    # expired certificate matters on the Pine Ridge and Cedar Falls rows
    return True


def counts(d: dict, knobs) -> dict:
    """--describe: what this draw contains."""
    changes = sum(len(j[3]) > 1 for j in d["juris"])
    expired = sum(1 for c in d["certs"].values() if c["expires"] and Q0 <= c["expires"] < Q1)
    return {"rows": len(d["invoices"]), "entities": len(d["juris"]), "rules": 4 + changes, "documents": 5,
            "rate_changes": changes,
            "trap_instances": {"expired_cert": expired, "voided": sum(i["void"] for i in d["invoices"]), "rate_change": changes}}


def emit(seed, naive_dir, knobs=KNOBS.defaults(), out=None):
    d = build(seed, knobs)
    if naive_dir:
        write_naive(d, naive_dir)
        return
    here, (ws, ref, sol) = output_dirs(HERE, out, task_dirs)
    r = rng(seed + 1)
    inv = d["invoices"]
    write_csv(os.path.join(ws, "pos_sales_detail_2026-Q2.csv"),
              ["Invoice", "Date", "Customer ID", "Customer", "Fulfillment", "Ship-to town", "Ship-to ZIP", "Items", "Net sales", "Tax exempt", "Tax collected", "Status"],
              [[i["no"], date_variant(i["date"], 1), i["cust_id"], i["cust"], i["fulfil"], i["town"], i["zip"] if i["fulfil"] == "Delivery" else "",
                i["items"], money_str(float(i["amount"]), r.choice([0, 1, 2])), "Y" if i["pos_exempt"] else "N",
                f"{i['tax_collected']:.2f}", "VOID" if i["void"] else "Posted"] for i in inv],
              preamble=["Quarry Road Nursery - Sales detail with tax", "04/01/2026 - 06/30/2026", ""], bom=True, crlf=True)
    rate_rows = []
    for c_, name, zips, rates in d["juris"]:
        for f, t, rt in rates:
            rate_rows.append([c_, name, " ".join(zips), f"{float(rt) * 100:.2f}%", f.isoformat() if f else "2025-01-01", t.isoformat() if t else ""])
    write_csv(os.path.join(ws, "dor_local_rates_2026.csv"), ["Jurisdiction code", "Jurisdiction", "ZIP codes", "Combined rate", "Effective from", "Effective to"], rate_rows)
    cert_rows = [[cid, name, d["certs"][cid]["type"], d["certs"][cid]["no"], d["certs"][cid]["expires"] or "none"] for cid, name in d["landscapers"] if cid in d["certs"]]
    cert_rows.append(["L-2219", "Blue Heron Garden Design", "Resale", "requested 3/2 - not received", ""])
    write_xlsx(os.path.join(ws, "exemption_certificates.xlsx"), {"Certificates": {
        "merged_title": "Exemption certificates on file",
        "header": ["Customer ID", "Customer", "Type", "Certificate no.", "Expires"], "rows": cert_rows,
        "widths": {"A": 12, "B": 28, "C": 12, "D": 28, "E": 12}}}, creator="Quarry Road")
    write_csv(os.path.join(ws, "return_upload_template.csv"), TEMPLATE, [["9999", "Example City", "10000.00", "2500.00", "7500.00", "543.75"]])
    went_up = "Millbrook went up on 1 May."
    more_rate = more_cert = ""
    if d["lags"]:
        # with more rate changes the email and the trap name them all (the default text is unchanged)
        ex = [c for c in EXTRA_CHANGES if c[0] in {l[0] for l in d["lags"]}]
        went_up = ("Millbrook went up on 1 May, " + ", ".join(f"{t} on {e.day} {e.strftime('%B')}" for _, t, _, _, e, _ in ex[:-1])
                   + (", and " if len(ex) > 1 else "and ") + f"{ex[-1][1]} on {ex[-1][4].day} {ex[-1][4].strftime('%B')}. "
                   "The POS picked up each change about a week late.")
        more_rate = "".join(f"; {t}'s rose from {float(o) * 100:.2f}% to {float(n) * 100:.2f}% on {e.day} {e.strftime('%B')} and the "
                            f"POS kept the old rate until {u.day} {u.strftime('%B')}" for _, t, o, n, e, u in ex)
    ex_cert = [(cid, exp) for cid, exp in EXTRA_EXPIRED if d["certs"][cid]["expires"] == exp]
    if ex_cert:
        nm = dict(d["landscapers"])
        more_cert = "; so did " + " and ".join(f"{nm[cid]}{chr(39) if nm[cid].endswith('s') else chr(39) + 's'} on {exp.day} "
                                                f"{exp.strftime('%B')}" for cid, exp in ex_cert)
    write_email_thread(os.path.join(ws, "email_from_hannah.txt"), [
        {"from": "Hannah Osei <hannah@mossbank.cpa>", "to": "you", "date": "Tue, 7 Jul 2026 09:40",
         "subject": "Q2 sales tax return",
         "body": ("Please build the Q2 upload for the return on the template - one row per local jurisdiction you had sales in, "
                  "with gross, exempt and taxable sales and the tax due.\n\n"
                  "How the state wants it:\n"
                  "- Pickups at a yard are taxed where the yard is. Deliveries are taxed where they were delivered, and the "
                  "jurisdiction goes by the ZIP code in the rate table. The town in the address is only the post office name - "
                  "a lot of the county outside the city limits still has a Cedar Falls or Millbrook address.\n"
                  "- A sale is exempt only if the customer's certificate was valid on the sale date. The POS doesn't check "
                  "expiry dates, so don't trust its exempt flag.\n"
                  f"- Use the rate in force on the sale date. {went_up}\n"
                  "- Work out the tax on each jurisdiction's taxable sales (at each rate if its rate changed), add it up and round "
                  "once to the cent for the jurisdiction. The POS rounds every receipt, so its tax collected column will not "
                  "match what we owe, and that's expected.\n"
                  "- Voided invoices are not sales.")}])
    agg = d["agg"]
    names = {c_: n_ for c_, n_, *_ in d["juris"]}
    rows = [[c_, names[c_], f"{a['gross']:.2f}", f"{a['exempt']:.2f}", f"{a['taxable']:.2f}", f"{a['tax_due']:.2f}"]
            for c_, a in agg.items() if a["gross"] > 0]
    write_csv(os.path.join(ref, "tax_liability.csv"), TEMPLATE, rows)
    write_csv(os.path.join(sol, "tax_liability.csv"), TEMPLATE, rows)
    write_json(os.path.join(ref, "notes.json"), {c_: {k: str(v) for k, v in a.items()} for c_, a in agg.items()})
    codes = [row[0] for row in rows]
    spec = {
        "id": "sales-tax-liability", "track": "desk", "category": "bookkeeping",
        "title": "Second-quarter sales tax due by local jurisdiction",
        "ask": ("Hannah needs our Q2 sales tax figures for the return, by jurisdiction, on the upload template. The POS export, the "
                "state's rate table, our exemption certificates and her email are in the folder. Save it as tax_liability.csv.\n"),
        "followup": None, "timeout_s": 1200,
        "traps": [
            "deliveries are taxed by the delivery ZIP from the rate table, not by the ship-to town: 98013, 98033 and 98060 carry "
            "Cedar Falls, Millbrook and Pine Ridge post-office names but are unincorporated Oak County, and pickups are taxed at "
            "the yard (checks: gross sales; taxable sales; tax due)",
            "exemption goes by the certificate on the sale date: Greenway Grounds' certificate expired 15 May and the POS kept "
            f"flagging its later purchases exempt{more_cert}, Blue Heron never delivered one, and the county parks department is exempt "
            "(checks: exempt sales; taxable sales; tax due)",
            "Millbrook's rate rose from 7.75% to 8.00% on 1 May but the POS kept charging the old rate until 8 May" + more_rate +
            ", so the tax collected column is short for that week (check: tax due)",
            "tax is computed on each jurisdiction's taxable sales and rounded once; adding up the POS's penny-rounded receipts "
            "is off by a few cents in several jurisdictions (check: tax due)",
            "six voided invoices stay in the export with their amounts, and the export has a preamble, a BOM and amounts "
            "written '$1,240.00' or '1240.00' (checks: gross sales; taxable sales)",
            "the rate table lists Stoneleigh, where nothing was sold; the return wants rows only for jurisdictions with sales "
            "(check: one row per jurisdiction)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "template columns", "path": "tax_liability.csv", "columns": TEMPLATE, "exact": True},
            {"type": "csv_set_equal", "name": "one row per jurisdiction", "path": "tax_liability.csv", "column": "jurisdiction_code",
             "ref": "tax_liability.csv", "normalize": ["digits"]},
            {"type": "csv_values_match", "name": "gross sales", "path": "tax_liability.csv", "ref": "tax_liability.csv", "key": "jurisdiction_code",
             "columns": ["gross_sales"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": codes},
            {"type": "csv_values_match", "name": "exempt sales", "path": "tax_liability.csv", "ref": "tax_liability.csv", "key": "jurisdiction_code",
             "columns": ["exempt_sales"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": codes},
            {"type": "csv_values_match", "name": "taxable sales", "path": "tax_liability.csv", "ref": "tax_liability.csv", "key": "jurisdiction_code",
             "columns": ["taxable_sales"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": codes},
            {"type": "csv_values_match", "name": "tax due", "path": "tax_liability.csv", "ref": "tax_liability.csv", "key": "jurisdiction_code",
             "columns": ["tax_due"], "numeric": True, "tolerance": 0.005, "min_accuracy": 1.0, "must_match_keys": codes},
        ],
    }
    write_task_yaml(here, record(spec, "sales-tax-liability", seed, knobs))
    print(f"seed={seed}: {len(inv)} invoices")
    for c_, a in agg.items():
        print(f"  {c_} gross {a['gross']:>10} exempt {a['exempt']:>9} taxable {a['taxable']:>10} due {a['tax_due']:>8} receipts {a['receipt_tax']:>8} pos {a['pos_tax']:>8}")


def write_naive(d, out):
    """Jurisdiction by the ship-to town (or the yard), POS exempt flag, POS tax collected summed, voids included."""
    os.makedirs(out, exist_ok=True)
    town_code = {"Cedar Falls": "3101", "Millbrook": "3102", "Pine Ridge": "3205", "Lake Haven": "3210", "Stoneleigh": "3320"}
    names = {c_: n_ for c_, n_, *_ in JURIS}
    agg = {}
    for i in d["invoices"]:
        c_ = town_code[i["town"]] if i["fulfil"] == "Delivery" else zip_juris(i["zip"])
        a = agg.setdefault(c_, {"g": D(0), "e": D(0), "t": D(0)})
        a["g"] += i["amount"]
        if i["pos_exempt"]:
            a["e"] += i["amount"]
        a["t"] += i["tax_collected"]
    rows = [[c_, names[c_], f"{a['g']:.2f}", f"{a['e']:.2f}", f"{a['g'] - a['e']:.2f}", f"{a['t']:.2f}"] for c_, a in sorted(agg.items())]
    write_csv(os.path.join(out, "tax_liability.csv"), TEMPLATE, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--naive", default=None)
    add_knob_args(ap, KNOBS)
    a = ap.parse_args()
    knobs = parse_knob_args(a, KNOBS)
    for attempt in range(300):
        s = a.seed * 1000 + attempt
        d = build(s, knobs)
        if acceptable(d):
            break
    else:
        raise SystemExit("no acceptable draw")
    if a.describe:
        print(describe_json("sales-tax-liability", s, knobs, counts(d, knobs)))
        raise SystemExit(0)
    emit(s, a.naive, knobs, a.out)
