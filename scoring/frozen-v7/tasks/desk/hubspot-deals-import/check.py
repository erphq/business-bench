"""hubspot-deals-import: amount.

Per Bid Number, Amount must be a plain number equal to the reference within 50 cents, and blank where the
reference is blank (TBD bids). A built-in numeric match cannot express "blank equals blank", so this check does it.
Every reference bid is compared; a missing bid or a non-numeric amount ("48.5k", "$1.15M") fails.
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
    text = open(path, "rb").read().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    return [{_norm_col(k): (v or "") for k, v in rec.items() if k is not None} for rec in csv.DictReader(io.StringIO(text))]


def _plain_number(v: str):
    s = str(v).strip()
    if not s:
        return ""
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    return float(s)


def check(ws: str, ref: str) -> list[dict]:
    name = "amount"
    p = _find(ws, "hubspot_deals.csv")
    if not p:
        return [{"name": name, "passed": False, "detail": "hubspot_deals.csv not found"}]
    try:
        got = {r.get("bid_number", "").strip().lower(): r for r in _rows(p)}
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"unreadable: {e}"}]
    bad = []
    want_rows = _rows(os.path.join(ref, "hubspot_deals.csv"))
    for w in want_rows:
        k = w["bid_number"].strip().lower()
        g = got.get(k)
        if g is None:
            bad.append(f"{k}: missing"); continue
        gv, wv = _plain_number(g.get("amount", "")), _plain_number(w["amount"])
        if gv is None:
            bad.append(f"{k}: not a plain number {g.get('amount')!r}")
        elif wv == "" or gv == "":
            if gv != wv:
                bad.append(f"{k}: {g.get('amount')!r} vs {w['amount']!r}")
        elif abs(gv - wv) > 0.5:
            bad.append(f"{k}: {gv} vs {wv}")
    return [{"name": name, "passed": not bad,
             "detail": f"{len(want_rows)} amounts match" if not bad else f"{len(bad)} wrong: " + "; ".join(bad[:6])}]
