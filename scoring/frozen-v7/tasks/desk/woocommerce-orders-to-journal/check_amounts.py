"""woocommerce-orders-to-journal: account amounts per journal; journal dates.

account amounts per journal: for every (Journal No, account) pair the net amount (debits minus credits, lines for
the same account added together) equals the reference within one cent, and the file has no non-zero pair the
reference lacks. Account Code is read from its leading four digits, so "4000" and "4000 Coffee Sales" both count.

journal dates: every reference journal carries its reference date (the order date, or the refund date for -R
journals) on all of its lines; dates are compared after reading YYYY-MM-DD, MM/DD/YYYY or a real spreadsheet date.
"""
from __future__ import annotations
import importlib.util, os, re
from datetime import datetime

# Load the shared readers from check.py by path under a task-unique name, so no module called "check" from another
# task can be picked up from sys.modules and no __pycache__ is written into the task folder.
_spec = importlib.util.spec_from_file_location("woocommerce_journal_check_helpers",
                                               os.path.join(os.path.dirname(os.path.abspath(__file__)), "check.py"))
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)  # type: ignore[union-attr]
_find, amount, read_rows = _helpers._find, _helpers.amount, _helpers.read_rows


def _acct(v) -> str:
    m = re.match(r"\s*(\d{4})", str(v or ""))
    return m.group(1) if m else str(v or "").strip().lower()


def _date(v) -> str:
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return s


def _nets(rows):
    nets: dict[tuple, float] = {}
    dates: dict[str, set] = {}
    for row in rows:
        jn = row.get("journal_no", "").strip().lower()
        dr, cr = amount(row.get("debit")) or 0.0, amount(row.get("credit")) or 0.0
        key = (jn, _acct(row.get("account_code")))
        nets[key] = nets.get(key, 0.0) + dr - cr
        dates.setdefault(jn, set()).add(_date(row.get("journal_date")))
    return nets, dates


def check(ws: str, ref: str) -> list[dict]:
    names = ["account amounts per journal", "journal dates"]
    p = _find(ws, "journal.csv")
    if not p:
        return [{"name": n, "passed": False, "detail": "journal.csv not found"} for n in names]
    try:
        got_n, got_d = _nets(read_rows(p))
    except Exception as e:
        return [{"name": n, "passed": False, "detail": f"unreadable: {e}"} for n in names]
    want_n, want_d = _nets(read_rows(os.path.join(ref, "journal.csv")))
    wrong = []
    for key, v in sorted(want_n.items()):
        g = got_n.get(key, 0.0)
        if abs(g - v) > 0.01:
            wrong.append(f"{key[0]} {key[1]}: {g:.2f} vs {v:.2f}")
    extra = [f"{k[0]} {k[1]}: {v:.2f}" for k, v in sorted(got_n.items()) if k not in want_n and abs(v) > 0.005]
    ok = not wrong and not extra
    out = [{"name": names[0], "passed": ok, "detail": (f"{len(want_n)} journal/account amounts match" if ok else
            f"{len(wrong)} wrong, {len(extra)} unexpected: " + "; ".join((wrong + extra)[:6]))}]
    bad_dates = [f"{j}: {sorted(got_d.get(j, {'missing'}))} vs {sorted(ds)}" for j, ds in sorted(want_d.items()) if got_d.get(j) != ds]
    out.append({"name": names[1], "passed": not bad_dates,
                "detail": f"{len(want_d)} journals dated correctly" if not bad_dates else f"{len(bad_dates)} wrong: " + "; ".join(bad_dates[:5])})
    return out
