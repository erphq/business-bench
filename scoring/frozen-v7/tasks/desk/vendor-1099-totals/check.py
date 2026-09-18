"""Custom grader for vendor-1099-totals, check "which vendors": the set of TINs on vendor_totals.csv, one line each.

Tamsin's rule 3 ("the most recent submission replaces the earlier one") drops Luis Ortiz (SSN ending 5105), whose
2025-05-19 resubmission is for Ortiz Lighting & Rigging Inc, an S corporation. Her rule 6 treats the TIN as the
vendor's identity, though, and that resubmission carries a different TIN (EIN ending 3408); check #2671 for $636.73
(05/15/2025) was paid to Ortiz before the S-corporation form existed. Reporting that pre-incorporation payment under
the SSN is a defensible reading, so TIN 5105 is an optional row:

  * vendor set: the TINs (digits only, blanks ignored) equal reference/vendor_totals.csv, or that set plus 5105
  * optional pre-incorporation row: when 5105 is present its reportable_total is 636.73 (the only reportable payment
    before 2025-05-19 15:22; every later Ortiz payment belongs to the S corporation and is excluded)
  * one line per vendor: the file has one row per TIN in the set, so the "row count" check's 12-or-13 allowance
    only admits the 5105 row, never a repeated or blank-TIN row

The optional row's figures come from reference/optional_rows.json.
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


def _find(ws: str, pattern: str):
    hits = sorted(glob.glob(os.path.join(ws, pattern)))
    if not hits:
        hits = sorted(glob.glob(os.path.join(ws, "**", pattern), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    if not hits:
        import fnmatch
        for base, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if d not in (".proto", ".codex", "node_modules", ".git")]
            hits += [os.path.join(base, f) for f in files if fnmatch.fnmatch(f.lower(), pattern.lower())]
        hits.sort()
    return hits[0] if hits else None


def _read_table(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(path, dtype=str)
    else:
        text = open(path, "rb").read().decode("utf-8", errors="replace").replace("\r\r\n", "\n").replace("\r\n", "\n")
        try:
            df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
        except pd.errors.ParserError:
            df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, engine="python", on_bad_lines="skip")
    df.columns = [_norm_col(c) for c in df.columns]
    return df.fillna("")


def _digits(v) -> str:
    return re.sub(r"\D", "", str(v))


def _num(v):
    try:
        return float(re.sub(r"[^0-9.\-eE]", "", str(v)))
    except ValueError:
        return None


def _result(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(ok), "detail": detail}


def check(ws, ref):
    names = ["vendor set", "optional pre-incorporation row", "one line per vendor"]
    p = _find(ws, "vendor_totals.csv")
    if not p:
        return [_result(n, False, "output file missing") for n in names]
    opt = json.load(open(os.path.join(ref, "optional_rows.json"), encoding="utf-8"))
    tin, total, tol = str(opt["tin_last4"]), float(opt["reportable_total"]), float(opt.get("tolerance", 0.005))
    df = _read_table(p)
    if "tin_last4" not in df.columns:
        return [_result(n, False, f"column 'tin_last4' not found; have {list(df.columns)}") for n in names]
    rdf = _read_table(os.path.join(ref, "vendor_totals.csv"))
    want = {_digits(v) for v in rdf["tin_last4"] if str(v).strip()}
    tins = [_digits(v) for v in df["tin_last4"]]
    got = {t for t, raw in zip(tins, df["tin_last4"]) if str(raw).strip()}
    extra, missing = sorted(got - want), sorted(want - got)
    set_ok = not missing and (not extra or extra == [tin])
    set_detail = f"{len(got)} got / {len(want)} expected; missing={missing[:8]} extra={extra[:8]}" + \
                 (f" (TIN {tin} is optional)" if tin in extra else "")

    opt_rows = [r for r, t in zip(df.to_dict("records"), tins) if t == tin]
    if not opt_rows:
        opt_ok, opt_detail = True, f"TIN {tin} not listed"
    else:
        vals = [_num(r.get("reportable_total", "")) for r in opt_rows]
        opt_ok = all(v is not None and abs(v - total) <= tol for v in vals)
        opt_detail = f"TIN {tin} reportable_total {[r.get('reportable_total', '') for r in opt_rows]}" + \
                     ("" if opt_ok else f", expected {total:.2f} (payments before the S-corporation W-9 only)")

    n_rows = len(df)
    lines_ok = n_rows == len(got)
    lines_detail = f"{n_rows} rows for {len(got)} TINs" + ("" if lines_ok else ": a TIN repeats or a row has no TIN")
    return [_result(names[0], set_ok, set_detail), _result(names[1], opt_ok, opt_detail), _result(names[2], lines_ok, lines_detail)]
