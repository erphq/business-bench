#!/usr/bin/env python3
"""shipment-manifests: a week of carrier manifests and postage logs from three carriers -> one row per shipment.

    python gen.py [--seed N] [--naive DIR]

Business: Saltbox Candle Co., a Portland, Maine candle maker, ships wholesale cartons by ground, retail parcels by post and
export orders by air. The owner wants one line per shipment with tracking, total weight in pounds and what it cost us, to
check shipping charged on each order.

Traps (each caught by a check, see task.yaml):
  * AeroPac prints kilograms with a chargeable (volumetric) kilogram column beside the actual weight; the postage log
    prints "2 lb 7 oz"; Northline prints decimal pounds                              (check: weights)
  * Northline multi-package shipments print one row per package, each with its own tracking number under the master;
    one row per shipment on the master tracking, packages counted, weight and cost summed (checks: one row per shipment; row count; packages; weights; cost)
  * voided labels: VOID rows in the postage log and on the scanned manifest, and a Northline package voided and
    re-labelled under a new tracking number for the same order                     (checks: one row per shipment; row count)
  * cost is the carrier's total to us: Northline adds fuel and residential surcharges, AeroPac prints duties billed to
    the receiver and a declared value beside its charges, the post adds insurance    (check: cost)
  * order references are printed "#SB-10482", "Ref SB10482" and "SB-10482"          (check: carrier, date and order)
  * Friday's postal manifest is an image-only scan                                 (checks: one row per shipment; weights)
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *  # noqa: E402,F403

HEADER = ["tracking_no", "carrier", "ship_date", "order_no", "packages", "weight_lb", "cost"]
KG = 2.20462


def lboz(oz: int) -> str:
    lb, o = divmod(oz, 16)
    return f"{lb} lb {o} oz" if lb else f"{o} oz"


def words(oz: int) -> str:
    lb, o = divmod(oz, 16)
    return (f"{lb} pound{'s' if lb > 1 else ''} " if lb else "") + f"{o} ounce{'s' if o != 1 else ''}"


def build(seed: int) -> dict:
    r = rng(seed)
    used = set()

    def uniq(f):
        while True:
            v = f()
            if v not in used:
                used.add(v); return v
    orders = iter(sorted(r.sample(range(10400, 10999), 30)))
    nl = lambda: uniq(lambda: f"NL{r.randint(10**11, 10**12 - 1)}")
    ap = lambda: uniq(lambda: f"AP{r.randint(10**9, 10**10 - 1)}")
    pp = lambda: uniq(lambda: f"9402{r.randint(10**15, 10**16 - 1)}")
    S = []   # shipments (truth)
    V = []   # voided labels
    # ---- Northline ground, two manifests
    def nl_pkg(resi):
        base = round(r.uniform(11.5, 38.0), 2)
        fuel = round(base * 0.165, 2)
        rs = 5.45 if resi else 0.0
        return {"trk": nl(), "wt": round(r.uniform(6.0, 42.0), 1), "base": base, "fuel": fuel, "resi": rs, "total": round(base + fuel + rs, 2),
                "dims": f"{r.choice([12, 14, 16, 18])}x{r.choice([10, 12, 14])}x{r.choice([8, 10, 12])}", "dv": float(r.choice([150, 250, 400, 600]))}
    for day, counts in ((date(2026, 9, 8), [1, 3, 1, 1]), (date(2026, 9, 10), [2, 1, 1])):
        for n in counts:
            resi = r.random() < 0.35
            pk = [nl_pkg(resi) for _ in range(n)]
            S.append({"carrier": "Northline", "date": day, "order": f"SB-{next(orders)}", "pkgs": pk, "trk": pk[0]["trk"], "src": f"NL{day.day}",
                      "wt_lb": round(sum(p["wt"] for p in pk), 2), "cost": round(sum(p["total"] for p in pk), 2)})
    # Northline void + relabel on the second manifest: the voided label sits right before its replacement
    reb = [s for s in S if s["src"] == "NL10" and len(s["pkgs"]) == 1][0]
    V.append({"carrier": "Northline", "date": reb["date"], "order": reb["order"], "pkg": nl_pkg(False), "before": reb["trk"]})
    # ---- AeroPac export
    for pieces in (1, 2, 1):
        kg = [round(r.uniform(1.8, 9.5), 1) for _ in range(pieces)]
        dims = [(r.choice([30, 35, 40, 45]), r.choice([25, 30, 35]), r.choice([20, 25, 30])) for _ in range(pieces)]
        vol = round(sum(a * b * c / 5000 for a, b, c in dims), 1)
        gross = round(sum(kg), 1)
        freight = round(r.uniform(58, 160), 2)
        fuel = round(freight * 0.18, 2)
        remote = r.choice([0.0, 0.0, 28.50])
        S.append({"carrier": "AeroPac", "date": date(2026, 9, 9), "order": f"SB-{next(orders)}", "trk": ap(), "src": "AP", "pieces": pieces,
                  "kg": gross, "vol": max(vol, gross), "dims": dims, "freight": freight, "fuel": fuel, "remote": remote,
                  "duties": round(r.uniform(9, 48), 2), "dv": float(r.choice([180, 240, 320, 450])), "dest": r.choice(["CA", "GB", "DE", "AU", "JP"]),
                  "wt_lb": round(gross * KG, 2), "cost": round(freight + fuel + remote, 2)})
    # ---- PostPoint postage log (Wednesday) and scanned manifest (Friday)
    for day, n, src in ((date(2026, 9, 9), 4, "PPLOG"), (date(2026, 9, 11), 3, "PPSCAN")):
        for _ in range(n):
            oz = r.randint(7, 70)
            post = round(r.uniform(5.2, 17.8), 2)
            ins = r.choice([0.0, 0.0, 2.85, 3.60])
            S.append({"carrier": "PostPoint", "date": day, "order": f"SB-{next(orders)}", "trk": pp(), "src": src, "oz": oz, "postage": post,
                      "ins": ins, "wt_lb": round(oz / 16, 2), "cost": round(post + ins, 2)})
        oz = r.randint(7, 40)
        V.append({"carrier": "PostPoint", "date": day, "order": f"SB-{next(orders)}", "trk": pp(), "src": src, "oz": oz,
                  "postage": round(r.uniform(5.2, 12.0), 2), "ins": 0.0})
    rows = [[s["trk"], s["carrier"], s["date"].isoformat(), s["order"], str(len(s["pkgs"]) if "pkgs" in s else s.get("pieces", 1)),
             f"{s['wt_lb']:.2f}", f"{s['cost']:.2f}"] for s in S]
    rows.sort(key=lambda x: (x[2], x[1], x[0]))
    return {"S": S, "V": V, "rows": rows}


def render(ws: str, d: dict, seed: int) -> dict:
    P = os.path.join(ws, "manifests")
    os.makedirs(P, exist_ok=True)
    S, V = d["S"], d["V"]
    files = {}
    shipper = "SALTBOX CANDLE CO. - 77 Commercial St, Portland ME 04101 - acct 4471-0922"
    # Northline manifests: Helvetica, one row per package, master/child
    nl_void = [v for v in V if v["carrier"] == "Northline"][0]
    for day, key in ((8, "NL8"), (10, "NL10")):
        ship = [s for s in S if s["src"] == key]
        rows = [["Tracking no.", "Master", "Pkg", "Reference", "Wt (lb)", "Dims (in)", "Decl. value", "Base", "Fuel", "Resi", "Total"]]
        n_pk = 0; wt = 0.0; tot = 0.0
        for s in ship:
            if key == "NL10" and s["trk"] == nl_void["before"]:
                p = nl_void["pkg"]
                rows.append([f"{p['trk']}<br/><b>VOIDED</b>", "", "1/1", f"#{nl_void['order']}", f"{p['wt']:.1f}", p["dims"], f"{p['dv']:.2f}",
                             f"{p['base']:.2f}", f"{p['fuel']:.2f}", "0.00", f"{p['total']:.2f}"])
            for i, p in enumerate(s["pkgs"], 1):
                rows.append([p["trk"], "" if i == 1 else s["trk"], f"{i}/{len(s['pkgs'])}", f"#{s['order']}", f"{p['wt']:.1f}", p["dims"],
                             f"{p['dv']:.2f}", f"{p['base']:.2f}", f"{p['fuel']:.2f}", f"{p['resi']:.2f}", f"{p['total']:.2f}"])
                n_pk += 1; wt += p["wt"]; tot += p["total"]
        files[key] = f"Northline_manifest_2026-09-{day:02d}.pdf"
        write_pdf_document(os.path.join(P, files[key]), [
            ("title", "NORTHLINE GROUND - Daily Shipping Manifest"), ("small", shipper), ("hr", None),
            ("kv", [("Manifest date", f"09/{day:02d}/2026"), ("Pickup", "Scheduled, 4:30 PM"), ("Service", "Ground commercial / residential")],
             {"col_widths": [100, 250]}), ("spacer", 6),
            ("table", rows, {"col_widths": [74, 72, 28, 50, 34, 46, 38, 34, 30, 30, 36], "grid": True, "shade_header": True}), ("spacer", 6),
            ("kv", [("Packages tendered", str(n_pk)), ("Total weight (lb)", f"{wt:.1f}"), ("Total charges", f"${tot:,.2f}")], {"col_widths": [120, 100]}),
            ("small", "Voided labels are listed for your records and are not billed. Multi-piece shipments list each piece under its master tracking number.")],
            pagesize="letter", font="Helvetica", base_size=7.5)
    # AeroPac: Times, A4, kg, chargeable weight, duties billed to receiver
    ship = [s for s in S if s["src"] == "AP"]
    rows = [["AWB", "Shipper ref", "Dest.", "Pieces", "Actual kg", "Chargeable kg", "Declared value USD", "Freight", "Fuel", "Remote area", "Duties/taxes (receiver)"]]
    for s in ship:
        rows.append([s["trk"], f"Ref SB{s['order'][3:]}", s["dest"], s["pieces"], f"{s['kg']:.1f}", f"{s['vol']:.1f}", f"{s['dv']:.2f}",
                     f"{s['freight']:.2f}", f"{s['fuel']:.2f}", f"{s['remote']:.2f}", f"{s['duties']:.2f}"])
    files["AP"] = "AeroPac_export_manifest_09Sep2026.pdf"
    write_pdf_document(os.path.join(P, files["AP"]), [
        ("right", "AeroPac Express<br/>International Export Manifest"), ("spacer", 4),
        ("p", f"Account: SALTBOX CANDLE CO (US-4471)<br/>Manifest date: 9 Sep 2026<br/>Terms: DAP - duties and taxes billed to receiver"), ("spacer", 6),
        ("table", rows, {"col_widths": [62, 58, 28, 32, 36, 46, 46, 38, 32, 36, 50], "grid": True}), ("spacer", 6),
        ("small", "Weights in kilograms. Charges to shipper are freight, fuel and remote area surcharge. Chargeable weight is the greater of actual and volumetric (L x W x H / 5000)."),
        ("small", "Duties and taxes are collected from the receiver and are not invoiced to the shipper account.")], pagesize="a4", font="Times-Roman", base_size=7.5)
    # PostPoint postage log: Courier, lb/oz, VOID row
    ship = [s for s in S if s["src"] == "PPLOG"]
    vv = [v for v in V if v.get("src") == "PPLOG"][0]
    items = ship[:2] + [vv] + ship[2:]
    rows = [["TRACKING", "ORDER", "WEIGHT", "POSTAGE", "INSURANCE", "STATUS"]]
    for s in items:
        void = s is vv
        rows.append([s["trk"], s["order"], lboz(s["oz"]), f"{s['postage']:.2f}", f"{s['ins']:.2f}", "VOID - REFUND REQUESTED" if void else "PRINTED"])
    files["PPLOG"] = "postpoint_postage_log_2026-09-09.pdf"
    write_pdf_document(os.path.join(P, files["PPLOG"]), [
        ("h", "SHIPDESK POSTAGE LOG - POSTPOINT"), ("p", "ACCOUNT SALTBOX CANDLE CO<br/>DATE 2026-09-09<br/>LABELS 5"), ("spacer", 6),
        ("table", rows, {"col_widths": [150, 60, 70, 60, 70, 110]}), ("spacer", 6),
        ("small", "VOID LABELS ARE REFUNDED TO THE POSTAGE BALANCE WITHIN 15 DAYS.")], pagesize="letter", font="Courier", base_size=8)
    # PostPoint scanned manifest (Friday)
    ship = [s for s in S if s["src"] == "PPSCAN"]
    vv = [v for v in V if v.get("src") == "PPSCAN"][0]
    items = [ship[0], vv] + ship[1:]
    lines = ["POSTPOINT SHIPMENT MANIFEST", "SALTBOX CANDLE CO  PORTLAND ME", "MAILING DATE 09/11/2026", "",
             "TRACKING  ORDER  WEIGHT  POSTAGE  INS", ""]
    for s in items:
        lines.append(f"{s['trk']}  {s['order']}")
        lines.append(f"   {words(s['oz'])}  POSTAGE {s['postage']:.2f}  INS {s['ins']:.2f}" + ("  VOID" if s is vv else ""))
    lines += ["", f"PIECES {len(ship)}  VOIDED 1", "ACCEPTANCE SCAN  09/11/2026  16:05"]
    files["PPSCAN"] = "scan_postpoint_manifest_0911.pdf"
    write_scan_pdf(os.path.join(P, files["PPSCAN"]), lines, font_size=30, skew_deg=0.4, noise=400, seed=seed * 7 + 2)
    return files


def emit(seed: int, d: dict, naive_dir: str | None) -> None:
    if naive_dir:
        return write_naive(d, naive_dir)
    ws, ref, sol = task_dirs(HERE)
    files = render(ws, d, seed)
    write_text(os.path.join(ws, "note_from_hollis.txt"),
               "Shipping check, week of Sept 8\n\n"
               "All of last week's manifests are in the manifests folder - Northline for wholesale cartons, AeroPac for export, and "
               "PostPoint labels from ShipDesk. I want to compare what shipping cost us against what we charged on each order, so I need "
               "shipments.csv with one row per shipment:\n\n"
               "tracking_no - the shipment's tracking or AWB number, no spaces. If a shipment went as several boxes, use the master "
               "(first box's) number.\n"
               "carrier - Northline, AeroPac or PostPoint.\n"
               "ship_date - the manifest date, YYYY-MM-DD.\n"
               "order_no - our order number as SB-12345.\n"
               "packages - how many boxes went in that shipment.\n"
               "weight_lb - actual total weight in pounds, 2 decimals (1 kg = 2.20462 lb, 16 oz = 1 lb). Not the billed or "
               "dimensional weight.\n"
               "cost - everything that carrier charges us for the shipment, surcharges and insurance included. Duties the customer pays "
               "and declared values are not our cost.\n\n"
               "Labels we voided never shipped and don't belong in the list.\n\nHollis\n")
    write_csv(os.path.join(ref, "shipments.csv"), HEADER, d["rows"])
    write_csv(os.path.join(sol, "shipments.csv"), HEADER, d["rows"])
    S = d["S"]
    by_src = lambda src: [s["trk"] for s in S if s["src"] == src]
    multi = [s["trk"] for s in S if len(s.get("pkgs", [])) > 1]
    sc = [s for s in S if s["src"] == "PPSCAN"]
    vs = [v for v in d["V"] if v.get("src") == "PPSCAN"][0]
    scan_figs = [x for s in sc for x in (s["trk"], s["order"], words(s["oz"]), f"{s['postage']:.2f}", f"INS {s['ins']:.2f}")] + [vs["trk"], "VOID"]
    write_json(os.path.join(ref, "notes.json"), {"files": files, "voided": [v.get("trk") or v["pkg"]["trk"] for v in d["V"]], "multi_package": multi,
                                                  "scan_figures": {f"manifests/{files['PPSCAN']}": scan_figs}})
    num = {"numeric": True, "min_accuracy": 1.0}
    P = "shipments.csv"
    write_task_yaml(HERE, {
        "id": "shipment-manifests", "track": "desk", "category": "extraction",
        "title": "Shipment weights and costs from last week's manifests",
        "ask": ("Last week's carrier manifests are in the folder. Can you pull every shipment into shipments.csv so I can check shipping "
                "against what we charged? Hollis's note says what he needs.\n"),
        "followup": None, "timeout_s": 1800,
        "traps": [
            "AeroPac prints actual kilograms next to a larger chargeable (volumetric) kilogram column, the postage log prints '2 lb 7 oz' and the scan '3 pounds 11 ounces'"
            ", and Northline prints decimal pounds; the note wants actual pounds (check: weights)",
            f"Northline prints each box of a multi-piece shipment as its own row with its own tracking number under the master ({len(multi)} "
            "shipments, three and two boxes); one row per shipment on the master number with the boxes counted and weight and cost summed "
            "(checks: one row per shipment; row count; packages; weights; cost)",
            "voided labels are listed with weights and postage: a VOID row in the PostPoint log, a VOID line on the scanned manifest, and a "
            "Northline label marked VOIDED just above the replacement label for the same order (checks: one row per shipment; row count)",
            "cost is the carrier's total to us: Northline adds fuel and residential surcharges in their own columns, PostPoint adds insurance, "
            "and AeroPac prints duties billed to the receiver and a declared value beside freight, fuel and remote-area charges (check: cost)",
            "order references are printed '#SB-10482' (Northline), 'Ref SB10482' (AeroPac) and 'SB-10482' (PostPoint) (check: carrier, date and order)",
            "Friday's PostPoint manifest is an image-only scan (checks: one row per shipment; weights; cost)",
        ],
        "checks": [
            {"type": "csv_columns", "name": "requested columns", "path": P, "columns": HEADER},
            {"type": "csv_set_equal", "name": "one row per shipment", "path": P, "column": "tracking_no", "ref": P, "normalize": ["strip", "lower"]},
            {"type": "csv_row_count", "name": "row count", "path": P, "equals_ref": P},
            {"type": "csv_values_match", "name": "carrier, date and order", "path": P, "ref": P, "key": "tracking_no",
             "columns": ["carrier", "ship_date", "order_no"], "min_accuracy": 1.0, "must_match_keys": by_src("AP")},
            {"type": "csv_values_match", "name": "packages", "path": P, "ref": P, "key": "tracking_no", "columns": ["packages"],
             "tolerance": 0.01, "must_match_keys": multi + by_src("AP"), **num},
            {"type": "csv_values_match", "name": "weights", "path": P, "ref": P, "key": "tracking_no", "columns": ["weight_lb"],
             "tolerance": 0.03, "must_match_keys": multi + by_src("AP") + by_src("PPLOG") + by_src("PPSCAN"), **num},
            {"type": "csv_values_match", "name": "cost", "path": P, "ref": P, "key": "tracking_no", "columns": ["cost"],
             "tolerance": 0.01, "must_match_keys": multi + by_src("AP") + by_src("PPSCAN"), **num},
        ],
    })
    print(f"seed={seed} shipments={len(d['rows'])} voids={len(d['V'])}")


def write_naive(d: dict, out: str) -> None:
    """The obvious transcription: one row per printed label row (child boxes and voided labels too), weights as printed
    (kilograms left as kilograms, ounces read as the pound figure), cost = the Total column for Northline, freight plus
    duties for AeroPac, postage only for PostPoint."""
    os.makedirs(out, exist_ok=True)
    rows = []
    for s in d["S"]:
        if s["carrier"] == "Northline":
            for p in s["pkgs"]:
                rows.append([p["trk"], "Northline", s["date"].isoformat(), s["order"], 1, f"{p['wt']:.2f}", f"{p['total']:.2f}"])
        elif s["carrier"] == "AeroPac":
            rows.append([s["trk"], "AeroPac", s["date"].isoformat(), s["order"], s["pieces"], f"{s['kg']:.2f}", f"{s['freight'] + s['duties']:.2f}"])
        else:
            rows.append([s["trk"], "PostPoint", s["date"].isoformat(), s["order"], 1, f"{s['oz'] // 16}.{s['oz'] % 16:02d}", f"{s['postage']:.2f}"])
    for v in d["V"]:
        if v["carrier"] == "Northline":
            p = v["pkg"]; rows.append([p["trk"], "Northline", v["date"].isoformat(), v["order"], 1, f"{p['wt']:.2f}", f"{p['total']:.2f}"])
        else:
            rows.append([v["trk"], "PostPoint", v["date"].isoformat(), v["order"], 1, f"{v['oz'] / 16:.2f}", f"{v['postage']:.2f}"])
    write_csv(os.path.join(out, "shipments.csv"), HEADER, rows)


if __name__ == "__main__":
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--seed", type=int, default=0)
    ap_.add_argument("--naive", default=None)
    a = ap_.parse_args()
    emit(a.seed, build(a.seed), a.naive)
