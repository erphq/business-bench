"""lockbox-apply: nothing applied that the stubs do not support, and today's file fully accounted for.

1. applied.csv names only invoices the stubs pay: not the open invoice that a stubless check happens to equal, and no
   check from yesterday's transmission appears in either file.
2. total amount_applied plus total unapplied amount equals today's file total to the cent (write-offs are not cash).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check import _find, chk_key, inv_key, num, read_rows  # noqa: E402


def check(ws, ref):
    pa, pu = _find(ws, "applied.csv"), _find(ws, "unapplied.csv")
    if not pa or not pu:
        return [{"name": "applied.csv and unapplied.csv present", "passed": False, "detail": f"applied={bool(pa)} unapplied={bool(pu)}"}]
    ra, ru = read_rows(pa), read_rows(pu)
    lb = json.load(open(os.path.join(ref, "lockbox.json")))
    out = []
    want = set(lb["per_invoice"])
    extra = sorted({inv_key(r.get("invoice_number", "")) for r in ra} - want - {""})
    yest = {chk_key(c) for c in lb["yesterday_check_numbers"]}
    y_hits = sorted({chk_key(r.get("check_number", "")) for r in ra + ru} & yest)
    out.append({"name": "nothing applied without a stub line", "passed": not extra and not y_hits,
                "detail": ("no extra invoices" if not extra else f"invoices no stub pays: {extra[:6]}")
                          + (f"; yesterday's checks present: {y_hits}" if y_hits else "")})
    try:
        tot = sum(num(r.get("amount_applied", "")) or 0.0 for r in ra) + sum(num(r.get("amount", "")) or 0.0 for r in ru)
    except Exception as e:
        return out + [{"name": "cash ties to the file total", "passed": False, "detail": f"unreadable: {e}"}]
    ok = abs(tot - lb["file_total"]) <= 0.011
    out.append({"name": "cash ties to the file total", "passed": ok, "detail": f"applied + unapplied = {tot:,.2f}; file total {lb['file_total']:,.2f}"})
    return out
