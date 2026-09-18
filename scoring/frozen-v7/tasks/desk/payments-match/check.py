"""Custom grader for payments-match: does matches.csv apply the bank lines correctly?

Four named results:
  * paid invoices applied correctly  - for at least 90% of invoices that received
    money, the total applied and the set of bank lines used both match the reference
  * duplicate bank line applied once - the glitched duplicate line is used at most
    once and its invoice is not over-applied
  * multi-invoice payments applied   - a line that covers several invoices (the ACH naming two
    numbers, the customer-only wire equal to two invoices) is applied to all of them
  * supplier refund not applied      - the unrelated deposit never appears
"""
from __future__ import annotations

import glob
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
    if path.lower().endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(path, dtype=str)
    else:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding_errors="replace")
    df.columns = [_norm_col(c) for c in df.columns]
    return df.fillna("")


def _num(v):
    try:
        return float(re.sub(r"[^0-9.\-eE]", "", str(v)))
    except Exception:
        return None


def _k(v) -> str:
    return str(v).strip().lower()


def check(ws: str, ref: str) -> list[dict]:
    p = _find(ws, "matches.csv")
    if not p:
        return [{"name": "matches.csv present", "passed": False, "detail": "no matches.csv in workspace"}]
    df = _read(p)
    need = ["invoice_id", "line_id", "amount_applied"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        return [{"name": "matches.csv columns", "passed": False,
                 "detail": f"missing {missing}; have {list(df.columns)}"}]

    with open(os.path.join(ref, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    rdf = _read(os.path.join(ref, "matches.csv"))

    exp: dict[str, dict] = {}
    for r in rdf.to_dict("records"):
        e = exp.setdefault(_k(r["invoice_id"]), {"total": 0.0, "lines": set()})
        e["total"] += float(r["amount_applied"])
        e["lines"].add(_k(r["line_id"]))

    rows = df.to_dict("records")
    got: dict[str, dict] = {}
    unreadable = 0
    for r in rows:
        amt = _num(r["amount_applied"])
        if amt is None:
            unreadable += 1
            continue
        g = got.setdefault(_k(r["invoice_id"]), {"total": 0.0, "lines": set()})
        g["total"] += amt
        g["lines"].add(_k(r["line_id"]))

    correct = [k for k, e in exp.items()
               if k in got and abs(got[k]["total"] - e["total"]) <= 0.01 and got[k]["lines"] == e["lines"]]
    wrong = sorted(set(exp) - set(correct))
    acc = len(correct) / len(exp) if exp else 0.0
    out = [{"name": "paid invoices applied correctly (>=90%)", "passed": acc >= 0.90,
            "detail": f"{len(correct)}/{len(exp)} = {acc:.3f}; wrong={wrong[:8]}"
                      + (f"; {unreadable} rows with unreadable amount" if unreadable else "")}]

    dup_line = _k(meta["duplicate_line_id"])
    dup_inv_id = meta["duplicate_invoice_id"]
    dup_inv = _k(dup_inv_id)
    inv_amt = float(meta["invoice_amounts"][dup_inv_id])
    dup_rows = sum(1 for r in rows if _k(r["line_id"]) == dup_line)
    dup_total = got.get(dup_inv, {"total": 0.0})["total"]
    ok = dup_rows <= 1 and dup_total <= inv_amt + 0.01
    out.append({"name": "duplicate bank line applied once", "passed": ok,
                "detail": f"{meta['duplicate_line_id']} used {dup_rows}x; {dup_inv_id} applied "
                          f"{dup_total:.2f} of {inv_amt:.2f}"})

    # One payment covering several invoices (the ACH that names both numbers, the wire that
    # names only the customer and equals the sum of two invoices) must be applied to every
    # invoice it covers, from that line. The 90% floor above must not absorb this trap.
    ref_by_line: dict[str, dict[str, float]] = {}
    for r in rdf.to_dict("records"):
        ref_by_line.setdefault(_k(r["line_id"]), {})[_k(r["invoice_id"])] = float(r["amount_applied"])
    got_by_line: dict[str, dict[str, float]] = {}
    for r in rows:
        amt = _num(r["amount_applied"])
        if amt is None:
            continue
        g = got_by_line.setdefault(_k(r["line_id"]), {})
        g[_k(r["invoice_id"])] = g.get(_k(r["invoice_id"]), 0.0) + amt
    multi = {ln: inv for ln, inv in ref_by_line.items() if len(inv) >= 2}
    bad = []
    for ln, inv in sorted(multi.items()):
        g = got_by_line.get(ln, {})
        if set(g) != set(inv) or any(abs(g[k] - v) > 0.01 for k, v in inv.items()):
            bad.append(f"{ln.upper()} -> expected {sorted(k.upper() for k in inv)}, got {sorted(k.upper() for k in g)}")
    out.append({"name": "multi-invoice payments applied to every invoice they cover", "passed": not bad,
                "detail": f"{len(multi) - len(bad)}/{len(multi)} multi-invoice lines right" + (f"; wrong: {bad}" if bad else "")})

    refund = _k(meta["refund_line_id"])
    n = sum(1 for r in rows if _k(r["line_id"]) == refund)
    out.append({"name": "supplier refund not applied", "passed": n == 0,
                "detail": f"{meta['refund_line_id']} appears {n}x in matches.csv"})
    return out
