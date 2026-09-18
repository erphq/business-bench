"""Regular and overtime hours per person per payroll week (over 40 in the week, across crews). See check.py."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location("timesheet_check_base", os.path.join(os.path.dirname(os.path.abspath(__file__)), "check.py"))
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)


def check(ws, ref):
    return _base.evaluate(ws, ref, ["regular", "overtime"], "overtime per person-week")
