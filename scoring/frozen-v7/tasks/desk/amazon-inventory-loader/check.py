"""amazon-inventory-loader: quantity and fulfillment.

Per sku, fulfillment-center-id must equal the reference (DEFAULT or AMAZON_NA, case-insensitive) and quantity must
be a whole number equal to the reference for shop-shipped items and blank for FBA items. A built-in numeric match
cannot require a blank, so this check does both columns. Every reference sku is compared.
"""
from __future__ import annotations
import csv, glob, io, os, re


def _norm_col(c) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _find(ws: str, name: str):
    hits = sorted(glob.glob(os.path.join(ws, name))) or sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _rows(path: str) -> list[dict]:
    if path.lower().endswith((".xlsx", ".xlsm")):
        import pandas as pd
        df = pd.read_excel(path, dtype=str).fillna("")
        return [{_norm_col(k): str(v) for k, v in rec.items()} for rec in df.to_dict("records")]
    raw = open(path, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    dialect = "excel-tab" if raw.split("\n", 1)[0].count("\t") > raw.split("\n", 1)[0].count(",") else "excel"
    return [{_norm_col(k): (v or "") for k, v in rec.items() if k is not None} for rec in csv.DictReader(io.StringIO(raw), dialect=dialect)]


def _qty(v: str):
    s = str(v).strip()
    if not s:
        return ""
    m = re.fullmatch(r"(\d+)(\.0+)?", s)
    return int(m.group(1)) if m else None


def check(ws: str, ref: str) -> list[dict]:
    name = "quantity and fulfillment"
    p = _find(ws, "amazon_inventory.csv")
    if not p:
        return [{"name": name, "passed": False, "detail": "amazon_inventory.csv not found"}]
    try:
        got = {r.get("sku", "").strip().lower(): r for r in _rows(p)}
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"unreadable: {e}"}]
    want_rows = _rows(os.path.join(ref, "amazon_inventory.csv"))
    bad = []
    for w in want_rows:
        k = w["sku"].strip().lower()
        g = got.get(k)
        if g is None:
            bad.append(f"{k}: missing"); continue
        gq, wq = _qty(g.get("quantity", "")), _qty(w["quantity"])
        if gq != wq:
            bad.append(f"{k}: quantity {g.get('quantity', '')!r} vs {w['quantity']!r}")
        if g.get("fulfillment_center_id", "").strip().upper() != w["fulfillment_center_id"].strip().upper():
            bad.append(f"{k}: fulfillment-center-id {g.get('fulfillment_center_id', '')!r} vs {w['fulfillment_center_id']!r}")
    return [{"name": name, "passed": not bad,
             "detail": f"{len(want_rows)} skus match" if not bad else f"{len(bad)} wrong: " + "; ".join(bad[:6])}]
