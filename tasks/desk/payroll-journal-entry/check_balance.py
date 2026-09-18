"""payroll-journal-entry: the entry balances - total debits equal total credits to the cent - and it is the whole
payroll: total debits equal the reference entry's total (gross wages, employer taxes and benefits, reimbursements)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check import _find, read_lines  # noqa: E402


def check(ws, ref):
    name = "debits equal credits"
    p = _find(ws, "payroll_je.csv")
    if not p:
        return [{"name": name, "passed": False, "detail": "payroll_je.csv not found"}]
    lines, err = read_lines(p)
    if lines is None:
        return [{"name": name, "passed": False, "detail": err}]
    dr = sum(x[1] for x in lines)
    cr = sum(x[2] for x in lines)
    want = json.load(open(os.path.join(ref, "je.json")))["total_debits"]
    bal = abs(dr - cr) <= 0.005
    whole = abs(dr - want) <= 0.011
    return [{"name": "debits equal credits", "passed": bal, "detail": f"debits {dr:,.2f} credits {cr:,.2f}"},
            {"name": "entry covers the whole payroll cost", "passed": whole, "detail": f"total debits {dr:,.2f}; expected {want:,.2f}"}]
