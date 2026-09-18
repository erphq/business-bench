"""occupancy-report custom check: occupancy rates written as a fraction (0.7727) or a percentage (77.27 or '77.27%'),
on the row of the cabin. The pins are per-cabin monthly rates (the ask wants one row per cabin, January to March
across); a portfolio or quarter figure is not pinned because nobody asked for one. Each pinned rate is unique on its
row."""
from __future__ import annotations
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "bench"))
LABEL = {"Fox Den Cabin": "fox den", "Aspen Hollow": "aspen", "Bear Creek Lodge": "bear creek", "Cedar Loft": "cedar loft",
         "Summit A-Frame": "summit", "total": "total"}


def _find(ws: str, pattern: str):
    hits = sorted(glob.glob(os.path.join(ws, pattern))) or sorted(glob.glob(os.path.join(ws, "**", pattern), recursive=True))
    hits = [h for h in hits if os.path.isfile(h) and "/.proto" not in h and "/.codex" not in h]
    return hits[0] if hits else None


def _num(v):
    if isinstance(v, bool) or v is None:
        return None, False
    if isinstance(v, (int, float)):
        return float(v), False
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*%\s*", str(v))
    if m:
        return float(m.group(1)), True
    try:
        return float(str(v).replace(",", "")), False
    except ValueError:
        return None, False


def check(ws: str, ref: str) -> list[dict]:
    try:
        pins = json.load(open(os.path.join(ref, "notes.json")))["rate_pins"]
    except Exception as e:  # pragma: no cover
        return [{"name": "occupancy rates", "passed": False, "detail": f"reference unreadable: {e}"}]
    names = [f"occupancy {p} {m}" for p, m, _ in pins]
    p = _find(ws, "occupancy.xlsx")
    if not p:
        return [{"name": n, "passed": False, "detail": "occupancy.xlsx missing"} for n in names]
    try:
        from grade import recalculated_workbook
        from openpyxl import load_workbook
        wb = load_workbook(recalculated_workbook(p), data_only=True)
    except Exception as e:
        return [{"name": n, "passed": False, "detail": f"workbook unreadable: {e}"} for n in names]
    grids = [(sh.title, [list(row) for row in sh.iter_rows()]) for sh in wb.worksheets]
    out = []
    for (prop, month, want), name in zip(pins, names):
        label = LABEL[prop]
        hit = None
        for title, grid in grids:
            for row in grid:
                text = " ".join(str(c.value).lower() for c in row if c.value is not None)
                if label not in text:
                    continue
                for c in row:
                    v, pct = _num(c.value)
                    if v is None:
                        continue
                    if (not pct and abs(v - want) <= 0.0015) or abs(v - want * 100) <= 0.15:
                        hit = f"{title}!{c.coordinate} = {c.value}"
                        break
                if hit:
                    break
            if hit:
                break
        out.append({"name": name, "passed": bool(hit), "detail": hit or f"no cell = {want} (or {want * 100:.2f}%) on a row mentioning {label!r}"})
    return out
