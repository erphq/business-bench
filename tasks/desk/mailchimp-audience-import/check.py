"""Custom grader for mailchimp-audience-import: tags per subscriber.

For every address in the reference, the output row with that address (case and whitespace ignored) carries exactly
the reference's set of tags. The Tags cell is split on commas; each tag is compared after trimming, ignoring case,
so "Farmers Market, Workshop" and "workshop,farmers market" both pass, while "Farmers' Market" or a missing
source tag fails.
"""
from __future__ import annotations

import glob
import io
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


def _tags(v) -> frozenset:
    return frozenset(t.strip().strip('"').lower() for t in str(v).split(",") if t.strip())


def check(ws: str, ref: str) -> list[dict]:
    name = "tags per subscriber"
    p = _find(ws, "mailchimp_import.csv")
    if not p:
        return [{"name": name, "passed": False, "detail": "no mailchimp_import.csv in workspace"}]
    df = _read(p)
    if "email_address" not in df.columns or "tags" not in df.columns:
        return [{"name": name, "passed": False, "detail": f"need Email Address and Tags columns; have {list(df.columns)}"}]
    got = {}
    for e, t in zip(df["email_address"], df["tags"]):
        got.setdefault(str(e).strip().lower(), set()).update(_tags(t))
    rdf = _read(os.path.join(ref, "mailchimp_import.csv"))
    bad = []
    for e, t in zip(rdf["email_address"], rdf["tags"]):
        k = str(e).strip().lower()
        if k not in got:
            bad.append(f"{k}: missing"); continue
        if got[k] != set(_tags(t)):
            bad.append(f"{k}: {sorted(got[k])} != {sorted(_tags(t))}")
    return [{"name": name, "passed": not bad, "detail": "; ".join(bad[:6]) if bad else f"{len(rdf)} subscribers carry the right tags"}]
