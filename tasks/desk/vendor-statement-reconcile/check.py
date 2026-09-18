"""The variance: the difference column adds up to the gap between the supplier's total due and our open balance.

Per-row checks grade each line; this one grades the reconciliation's bottom line the way the office manager will read
it. The expected variance comes from reference/notes.json. A total line, if the file has one, is ignored (a row whose
reference is blank or reads "total").
"""
import glob
import json
import os
import re
import sys


def _bench():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, os.path.join(root, "bench"))
    import grade  # noqa: E402
    return grade


def check(ws, ref):
    name = "variance ties to the balances"
    hits = sorted(glob.glob(os.path.join(ws, "vendor_recon.csv"))) or sorted(
        glob.glob(os.path.join(ws, "**", "vendor_recon.csv"), recursive=True))
    if not hits:
        return [{"name": name, "passed": False, "detail": "vendor_recon.csv not found"}]
    try:
        grade = _bench()
        df = grade.read_table(hits[0])
        want = float(json.load(open(os.path.join(ref, "notes.json")))["variance"])
    except Exception as e:
        return [{"name": name, "passed": False, "detail": f"unreadable: {e}"}]
    if "difference" not in df.columns or "reference" not in df.columns:
        return [{"name": name, "passed": False, "detail": f"need reference and difference columns; have {list(df.columns)}"}]
    total = 0.0
    for ref_v, diff in zip(df["reference"], df["difference"]):
        if not str(ref_v).strip() or re.search(r"total", str(ref_v), re.I):
            continue
        text = str(diff)
        try:
            x = float(re.sub(r"[^0-9.]", "", text) or 0)
        except ValueError:
            continue
        total += -x if ("(" in text or "-" in text or "\u2212" in text) else x
    ok = abs(total - want) <= 0.01
    return [{"name": name, "passed": ok, "detail": f"differences sum to {total:.2f}; expected {want:.2f}"}]
