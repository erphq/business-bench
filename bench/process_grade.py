#!/usr/bin/env python3
"""Grade a process-track attempt from its final database, start database, and workspace.

    process_grade.py TASK_DIR FINAL_DB START_DB WS REF_DIR OUT_DIR --agent USER --token-id TOK --start YYYY-MM-DD

Projections (`projections.sql` in the task: blocks headed `-- name: <projection>`) run on the final database with
parameters :start and :agent; the agent's rows are written to OUT_DIR/projections/<name>.csv beside the reference
rows in REF_DIR/<name>.csv, so every verdict can be inspected like a desk CSV. Check types:

  state_set        projection, key (column or list), normalize?   -> the key sets are equal
  state_values     projection, key, columns, ...                  -> csv_values_match semantics
  state_unchanged  tables, where? (SQL filter)                    -> those rows equal the start database
  audit_forbidden  rule, params?                                  -> the rule finds nothing (a finding is a breach)
  audit_required   rule, params?                                  -> the rule finds nothing missing
  ledger_ties      accounts (posting-rule keys)                   -> each control account equals its subledger
  anything else    delegated to bench/grade.py on the workspace (text checks for notes and answers)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'erp'))

import grade as desk  # noqa: E402
from process_rules import RULES  # noqa: E402

BREACH_TYPES = ('audit_forbidden',)


def load_projections(task_dir: str) -> dict[str, str]:
    text = open(os.path.join(task_dir, 'projections.sql'), encoding='utf-8').read()
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r'--\s*name:\s*(\S+)', line)
        if m:
            if name:
                out[name] = '\n'.join(buf).strip().rstrip(';')
            name, buf = m.group(1), []
        elif name:
            buf.append(line)
    if name:
        out[name] = '\n'.join(buf).strip().rstrip(';')
    return out


def run_projection(db: sqlite3.Connection, sql: str, params: dict) -> tuple[list[str], list[list]]:
    cur = db.execute(sql, {k: v for k, v in params.items() if f':{k}' in sql})
    return [c[0] for c in cur.description], [list(r) for r in cur.fetchall()]


def write_csv(path: str, header: list[str], rows: list[list]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(['' if v is None else (f'{v:.4f}'.rstrip('0').rstrip('.') if isinstance(v, float) else v)
                        for v in r])


def materialize(task_dir: str, db_path: str, params: dict, out_dir: str) -> dict[str, str]:
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        paths = {}
        for name, sql in load_projections(task_dir).items():
            header, rows = run_projection(db, sql, params)
            paths[name] = os.path.join(out_dir, f'{name}.csv')
            write_csv(paths[name], header, rows)
        return paths
    finally:
        db.close()


def _read(path: str) -> list[dict]:
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def c_state_set(proj_dir: str, ref_dir: str, spec: dict):
    keys = spec['key'] if isinstance(spec['key'], list) else [spec['key']]
    ops = spec.get('normalize', ['strip', 'lower'])
    name = spec['projection']

    def keyset(path):
        return {'|'.join(desk.normalize(r.get(k, ''), ops) for k in keys) for r in _read(path)}
    got, want = keyset(os.path.join(proj_dir, f'{name}.csv')), keyset(os.path.join(ref_dir, f'{name}.csv'))
    extra, missing = sorted(got - want), sorted(want - got)
    return not extra and not missing, f'{len(got)} got / {len(want)} expected; missing={missing[:6]} extra={extra[:6]}'


def c_state_values(proj_dir: str, ref_dir: str, spec: dict):
    s = dict(spec)
    s['path'] = s['ref'] = f'{spec["projection"]}.csv'
    s.setdefault('min_accuracy', 1.0)
    return desk.c_csv_values_match(proj_dir, ref_dir, s)


def c_state_unchanged(final, start, spec: dict):
    diffs = []
    for table in spec['tables']:
        where = spec.get('where', {}).get(table, '1 = 1')
        sql = f'SELECT * FROM {table} WHERE {where} ORDER BY 1, 2'
        a = [tuple(r) for r in start.execute(sql).fetchall()]
        b = [tuple(r) for r in final.execute(sql).fetchall()]
        if a != b:
            sa, sb = set(a), set(b)
            diffs.append(f'{table}: {len(sb - sa)} rows changed or added, {len(sa - sb)} removed')
    return not diffs, 'unchanged' if not diffs else '; '.join(diffs)


def c_audit(final, start, spec: dict, params: dict, required: bool):
    rule = RULES.get(spec['rule'])
    if rule is None:
        raise KeyError(f'unknown audit rule {spec["rule"]!r}')
    found = rule(final, start, params, spec)
    if required:
        return not found, 'present' if not found else 'missing: ' + '; '.join(found[:5])
    return not found, 'no breach' if not found else 'breach: ' + '; '.join(found[:5])


def c_ledger_ties(db_path: str, spec: dict):
    from bberp import reports
    from bberp.core import Erp
    erp = Erp(db_path)
    try:
        ties = reports.control_ties(erp)['controls']
        balanced = reports.trial_balance(erp)['balanced']
    finally:
        erp.close()
    bad = [f'{k}: ledger {v["ledger_cents"] / 100:.2f} vs subledger {v["subledger_cents"] / 100:.2f}'
           for k, v in ties.items() if k in spec.get('accounts', ties) and v['difference_cents']]
    if not balanced:
        bad.append('trial balance does not balance')
    return not bad, 'ties' if not bad else '; '.join(bad)


def resolve(spec, values: dict):
    """Replace '{truth:key}' placeholders (seed-dependent figures) with values from the scenario's truth.json."""
    if isinstance(spec, dict):
        return {k: resolve(v, values) for k, v in spec.items()}
    if isinstance(spec, list):
        return [resolve(v, values) for v in spec]
    if isinstance(spec, str):
        m = re.fullmatch(r'\{truth:(\w+)\}', spec)
        if m:
            if m.group(1) not in values:
                raise KeyError(f'truth.json has no value {m.group(1)!r}')
            return values[m.group(1)]
    return spec


def grade_process(task_dir: str, final_db: str, start_db: str, ws: str, ref_dir: str, out_dir: str,
                  params: dict) -> dict:
    task = yaml.safe_load(open(os.path.join(task_dir, 'task.yaml'), encoding='utf-8'))
    truth_path = os.path.join(os.path.dirname(os.path.abspath(ref_dir)), 'truth.json')
    values = json.load(open(truth_path, encoding='utf-8')).get('values', {}) if os.path.exists(truth_path) else {}
    proj_dir = os.path.join(out_dir, 'projections')
    materialize(task_dir, final_db, params, proj_dir)
    final = sqlite3.connect(f'file:{final_db}?mode=ro', uri=True)
    start = sqlite3.connect(f'file:{start_db}?mode=ro', uri=True)
    out, grader_errors = [], []
    try:
        for spec in task.get('checks', []):
            t = spec['type']
            try:
                spec = resolve(spec, values)
                if t == 'state_set':
                    ok, detail = c_state_set(proj_dir, ref_dir, spec)
                elif t == 'state_values':
                    ok, detail = c_state_values(proj_dir, ref_dir, spec)[:2]
                elif t == 'state_unchanged':
                    ok, detail = c_state_unchanged(final, start, spec)
                elif t in ('audit_forbidden', 'audit_required'):
                    ok, detail = c_audit(final, start, spec, params, t == 'audit_required')
                elif t == 'ledger_ties':
                    ok, detail = c_ledger_ties(final_db, spec)
                elif t in desk.CHECKS:
                    ok, detail = desk.CHECKS[t](ws, ref_dir, spec)[:2]
                else:
                    raise KeyError(f'unknown check type {t!r}')
            except Exception as e:
                ok, detail = False, f'grader error: {type(e).__name__}: {e}'
                grader_errors.append(spec.get('name', t))
            out.append({'name': spec.get('name', t), 'type': t, 'required': bool(spec.get('required', True)),
                        'passed': bool(ok), 'breach': t in BREACH_TYPES and not ok, 'detail': str(detail)[:500]})
    finally:
        final.close()
        start.close()
    passed = all(c['passed'] for c in out if c['required'])
    return {'task': task.get('id'), 'passed': passed, 'breach': any(c['breach'] for c in out), 'checks': out,
            'grader_errors': grader_errors}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for a in ('task_dir', 'final_db', 'start_db', 'ws', 'ref_dir', 'out_dir'):
        ap.add_argument(a)
    ap.add_argument('--agent', required=True)
    ap.add_argument('--token-id', required=True)
    ap.add_argument('--start', required=True)
    a = ap.parse_args()
    res = grade_process(a.task_dir, a.final_db, a.start_db, a.ws, a.ref_dir, a.out_dir,
                        {'agent': a.agent, 'token_id': a.token_id, 'start': a.start})
    print(json.dumps(res, indent=2))


if __name__ == '__main__':
    main()
