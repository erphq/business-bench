"""Custom grader for xero-sales-invoices-import: the lines of every invoice.

For each invoice number in the reference, the output rows with that number (case and whitespace ignored) must form
the same multiset of lines as the reference, where a line is (Quantity, UnitAmount, Discount, AccountCode, TaxType).
Quantity, UnitAmount and Discount must parse as plain numbers (a trailing % on Discount is tolerated; a blank
Discount is 0) and match to the cent; AccountCode compares as text; TaxType ignores case and surrounding spaces.
Descriptions are not compared, so the order of lines and the wording of the delivery line are free.
"""
from __future__ import annotations

import glob
import io
import os
import re
from collections import Counter

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


def _num(v, blank_zero=False, pct=False):
    s = str(v).strip()
    if pct:
        s = s.rstrip("%").strip()
    if not s:
        return 0.0 if blank_zero else None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _line(row: dict):
    return (_num(row.get("quantity")), _num(row.get("unitamount")), _num(row.get("discount"), blank_zero=True, pct=True),
            str(row.get("accountcode", "")).strip(), str(row.get("taxtype", "")).strip().lower())


def check(ws: str, ref: str) -> list[dict]:
    name = "invoice lines"
    p = _find(ws, "xero_invoices.csv")
    if not p:
        return [{"name": name, "passed": False, "detail": "no xero_invoices.csv in workspace"}]
    df = _read(p)
    need = ["invoicenumber", "quantity", "unitamount", "discount", "accountcode", "taxtype"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        return [{"name": name, "passed": False, "detail": f"missing columns {miss}; have {list(df.columns)}"}]
    got: dict[str, Counter] = {}
    for row in df.to_dict("records"):
        got.setdefault(str(row["invoicenumber"]).strip().lower(), Counter())[_line(row)] += 1
    want: dict[str, Counter] = {}
    for row in _read(os.path.join(ref, "xero_invoices.csv")).to_dict("records"):
        want.setdefault(str(row["invoicenumber"]).strip().lower(), Counter())[_line(row)] += 1
    bad = []
    for inv, lines in want.items():
        g = got.get(inv, Counter())
        if g != lines:
            missing = list((lines - g).elements())[:2]
            extra = list((g - lines).elements())[:2]
            bad.append(f"{inv}: missing {missing} extra {extra}")
    return [{"name": name, "passed": not bad, "detail": "; ".join(bad[:4]) if bad else f"{len(want)} invoices have the right lines"}]
