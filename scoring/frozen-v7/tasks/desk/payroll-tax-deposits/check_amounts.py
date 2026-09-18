"""payroll-tax-deposits: see check.py (amounts)."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location("payroll_tax_deposits_core", os.path.join(os.path.dirname(os.path.abspath(__file__)), "check.py"))
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)


def check(ws, ref):
    return _core.check_amounts(ws, ref)
