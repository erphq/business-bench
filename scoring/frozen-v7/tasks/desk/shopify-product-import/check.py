"""Custom grader for shopify-product-import.

  * first-row product fields: for every product in reference/products.json, the first row carrying its handle (in
    file order) has the product's Title, Option1 Name, Option2 Name, Status and Published, as Shopify's sample does
  * compare-at prices: per Variant SKU, Variant Compare At Price is blank where the reference is blank and equals the
    reference otherwise
  * bare-number prices: every Variant Price and non-blank Compare At Price is a plain number (no $ or commas)
Text comparisons ignore case and surrounding whitespace.
"""
from __future__ import annotations

import glob
import io
import json
import os
import re

import pandas as pd


def _norm_col(c) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _find(ws: str, name: str):
    hits = sorted(glob.glob(os.path.join(ws, name)))
    if not hits:
        hits = sorted(glob.glob(os.path.join(ws, "**", name), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _read(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xlsm")):
        df = pd.read_excel(path, dtype=str)
    else:
        text = open(path, "rb").read().decode("utf-8", errors="replace").replace("\r\n", "\n")
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    df.columns = [_norm_col(c) for c in df.columns]
    return df.fillna("")


def _t(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().lower()


def check(ws: str, ref: str) -> list[dict]:
    p = _find(ws, "shopify_products.csv")
    if not p:
        return [{"name": "shopify_products.csv present", "passed": False, "detail": "no shopify_products.csv in workspace"}]
    df = _read(p)
    need = ["handle", "title", "option1_name", "option2_name", "status", "published", "variant_sku", "variant_price", "variant_compare_at_price"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        return [{"name": "template columns present", "passed": False, "detail": f"missing {miss}"}]
    rows = df.to_dict("records")
    products = json.load(open(os.path.join(ref, "products.json"), encoding="utf-8"))
    bad_first = []
    for prod in products:
        first = next((r for r in rows if _t(r["handle"]) == prod["handle"]), None)
        if first is None:
            bad_first.append(f"{prod['handle']}: no rows"); continue
        for col, key in [("title", "title"), ("option1_name", "option1_name"), ("option2_name", "option2_name"), ("status", "status"), ("published", "published")]:
            if _t(first[col]) != _t(prod[key]):
                bad_first.append(f"{prod['handle']}: {col}={first[col]!r}, expected {prod[key]!r}")
    out = [{"name": "first-row product fields", "passed": not bad_first, "detail": "; ".join(bad_first[:6]) if bad_first else f"{len(products)} products correct on their first row"}]

    rdf = _read(os.path.join(ref, "shopify_products.csv"))
    gmap = {_t(r["variant_sku"]): r for r in rows}
    bad_cmp = []
    for rr in rdf.to_dict("records"):
        g = gmap.get(_t(rr["variant_sku"]))
        want = rr["variant_compare_at_price"].strip()
        got = (g or {}).get("variant_compare_at_price", "").strip()
        if g is None:
            bad_cmp.append(f"{rr['variant_sku']}: missing"); continue
        if not want:
            if got and got not in ("0", "0.00"):
                bad_cmp.append(f"{rr['variant_sku']}: {got!r}, expected blank")
        else:
            try:
                ok = abs(float(re.sub(r"[^0-9.\-]", "", got)) - float(want)) <= 0.005
            except ValueError:
                ok = False
            if not ok:
                bad_cmp.append(f"{rr['variant_sku']}: {got!r}, expected {want}")
    out.append({"name": "compare-at prices", "passed": not bad_cmp, "detail": "; ".join(bad_cmp[:6]) if bad_cmp else "all match"})

    bare = re.compile(r"^\d+(\.\d{1,2})?$")
    bad_num = [f"{r['variant_sku']}: {r['variant_price']!r}" for r in rows if not bare.match(str(r["variant_price"]).strip())]
    bad_num += [f"{r['variant_sku']}: compare {r['variant_compare_at_price']!r}" for r in rows
                if str(r["variant_compare_at_price"]).strip() and not bare.match(str(r["variant_compare_at_price"]).strip())]
    out.append({"name": "bare-number prices", "passed": not bad_num, "detail": "; ".join(bad_num[:6]) if bad_num else "all prices are plain numbers"})
    return out
