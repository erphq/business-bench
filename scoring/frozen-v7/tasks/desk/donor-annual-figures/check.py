"""donor-annual-figures custom check: the FY2026 donor retention rate, written as a fraction (0.6123) or a
percentage (61.23 or '61.23%'), on a row or column that mentions retention."""
from __future__ import annotations
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "bench"))


def _find(ws: str, pattern: str):
    hits = sorted(glob.glob(os.path.join(ws, pattern))) or sorted(glob.glob(os.path.join(ws, "**", pattern), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _num(v):
    if isinstance(v, bool) or v is None:
        return None, False
    if isinstance(v, (int, float)):
        return float(v), False
    s = str(v).strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*%", s)
    if m:
        return float(m.group(1)), True
    try:
        return float(s.replace(",", "")), False
    except ValueError:
        return None, False


def check(ws: str, ref: str) -> list[dict]:
    name = "donor retention rate"
    try:
        want = float(json.load(open(os.path.join(ref, "notes.json")))["retention_rate"])
    except Exception as e:  # pragma: no cover
        return [{"name": name, "passed": False, "detail": f"reference unreadable: {e}"}]
    p = _find(ws, "annual_figures.xlsx")
    if not p:
        return [{"name": name, "passed": False, "detail": "annual_figures.xlsx missing"}]
    try:
        from grade import recalculated_workbook
        from openpyxl import load_workbook
        wb = load_workbook(recalculated_workbook(p), data_only=True)
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"workbook unreadable: {e}"}]
    for sh in wb.worksheets:
        grid = [list(row) for row in sh.iter_rows()]
        cols: dict[int, str] = {}
        for row in grid:
            for j, c in enumerate(row):
                if c.value is not None:
                    cols[j] = cols.get(j, "") + " " + str(c.value).lower()
        for row in grid:
            text = " ".join(str(c.value).lower() for c in row if c.value is not None)
            for j, c in enumerate(row):
                v, pct = _num(c.value)
                if v is None:
                    continue
                if "retain" not in text and "retention" not in text and "retain" not in cols.get(j, ""):
                    continue
                fmt = str(getattr(c, "number_format", "") or "")
                if (not pct and abs(v - want) <= 0.0015) or ((pct or "%" not in fmt) and abs(v - want * 100) <= 0.15):
                    return [{"name": name, "passed": True, "detail": f"{sh.title}!{c.coordinate} = {c.value}"}]
    return [{"name": name, "passed": False, "detail": f"no cell = {want} (or {want * 100:.2f}%) near a retention label"}]
