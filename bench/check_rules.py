"""Strict-validator rules for the v2 check types (docs/v2/README.md, section 4).

Each rule returns a list of human-readable problems; an empty list means the task's use of the
check type is acceptable. Kept separate from validate_tasks.py so the rules are importable
and unit-tested."""
from __future__ import annotations
import hashlib, os

MAX_GAP_DEFAULT = 0.10       # plan_feasible: more than 10% from the reference optimum needs a stated reason
MAX_ERROR_DEFAULT = 0.25     # forecast_error: more than 25% error bound needs a stated reason


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def plan_feasible_rules(td: str, c: dict) -> list[str]:
    out = []
    mod = os.path.join(td, c.get('module', 'plan_check.py'))
    if not os.path.isfile(mod):
        out.append(f"{c.get('name')!r}: module {os.path.relpath(mod, td)} missing")
    elif 'def evaluate(' not in open(mod, encoding='utf-8').read():
        out.append(f"{c.get('name')!r}: module has no evaluate(ws, ref)")
    gap = float(c.get('max_gap', 0.0))
    if gap < 0: out.append(f"{c.get('name')!r}: negative max_gap")
    if gap > MAX_GAP_DEFAULT and not c.get('gap_reason'):
        out.append(f"{c.get('name')!r}: max_gap {gap} exceeds {MAX_GAP_DEFAULT} without gap_reason")
    if c.get('sense', 'min') not in ('min', 'max'):
        out.append(f"{c.get('name')!r}: sense must be min or max")
    return out


def forecast_error_rules(td: str, c: dict) -> list[str]:
    out = []
    for k in ('path', 'ref', 'key', 'column', 'max_error'):
        if k not in c: out.append(f"{c.get('name')!r}: missing {k}")
    if out: return out
    refp = os.path.join(td, 'reference', c['ref'])
    if not os.path.isfile(refp):
        out.append(f"{c.get('name')!r}: reference {c['ref']} missing"); return out
    mx = float(c['max_error'])
    if mx > MAX_ERROR_DEFAULT and not c.get('error_reason'):
        out.append(f"{c.get('name')!r}: max_error {mx} exceeds {MAX_ERROR_DEFAULT} without error_reason")
    if c.get('metric', 'wape') not in ('wape', 'mape', 'mae', 'rmse'):
        out.append(f"{c.get('name')!r}: unknown metric {c.get('metric')!r}")
    # Held-out means held out: the truth file must not be in the workspace by name or by content.
    ws = os.path.join(td, 'workspace'); h = _sha(refp)
    for base, _, files in os.walk(ws):
        for f in files:
            p = os.path.join(base, f)
            if f == os.path.basename(refp):
                out.append(f"{c.get('name')!r}: workspace contains a file named like the truth ({f})")
            elif _sha(p) == h:
                out.append(f"{c.get('name')!r}: workspace file {os.path.relpath(p, ws)} is byte-identical to the truth")
    return out


def not_fooled_rules(td: str, c: dict) -> list[str]:
    out = []
    has_keys = bool(c.get('planted_keys')); has_text = bool(c.get('forbidden_text')); has_flag = bool(c.get('flag'))
    if not (has_keys or has_text or has_flag):
        out.append(f"{c.get('name')!r}: declares none of planted_keys, forbidden_text, flag")
    if has_keys:
        for k in ('path', 'ref', 'key', 'columns'):
            if k not in c: out.append(f"{c.get('name')!r}: planted_keys needs {k}")
        if 'ref' in c and not os.path.isfile(os.path.join(td, 'reference', c['ref'])):
            out.append(f"{c.get('name')!r}: reference {c['ref']} missing")
    for item in c.get('forbidden_text') or []:
        if not item.get('path') or not item.get('phrases'):
            out.append(f"{c.get('name')!r}: forbidden_text item needs path and phrases")
    if has_flag and not (c['flag'].get('path') and c['flag'].get('all')):
        out.append(f"{c.get('name')!r}: flag needs path and all")
    return out


RULES = {'plan_feasible': plan_feasible_rules, 'forecast_error': forecast_error_rules, 'not_fooled': not_fooled_rules}


def v2_check_problems(td: str, checks: list[dict]) -> list[str]:
    out = []
    for c in checks or []:
        fn = RULES.get(c.get('type'))
        if fn: out.extend(fn(td, c))
    return out
