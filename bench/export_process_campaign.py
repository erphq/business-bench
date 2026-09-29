#!/usr/bin/env python3
"""Export a process-track campaign for publication, or verify published exports.

  export_process_campaign.py --label pilot-process-2026-09-27
  export_process_campaign.py --verify

Reads the raw attempt directories under results/<label>/ (result.json, final.db, ws/) and the campaign description
results/<label>/campaign.json, and writes results/process/<label>/:

  attempts.jsonl   one line per attempt: verdict, breach, error, each check's verdict, turns, time, usage, and
                   SHA-256 hashes of the original result.json, the final ERP database and the files the agent left
  summary.json     per cell: passes, pass^k, breaches, errors, time and tokens, by task
  provenance.json  the campaign description, the benchmark commit, the task tree hash and the ledger hash

Raw databases, workspaces and harness traces stay private; their hashes are in the ledger. --verify recomputes every
published summary from its ledger and checks the ledger hash, without the raw attempts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISHED = os.path.join(ROOT, 'results', 'process')


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def attempt_record(run_dir: str) -> dict:
    raw = open(os.path.join(run_dir, 'result.json'), 'rb').read()
    r = json.loads(raw)
    ws = os.path.join(run_dir, 'ws')
    files = {}
    for dp, _, fs in os.walk(ws):
        for f in fs:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ws)
            if rel.startswith('.proto/') or rel.startswith('.proto-logs/'):
                continue   # the harness's own session files, not work the agent was asked for
            files[rel] = sha256_file(p)
    u = r.get('usage') or {}
    return {
        'run_id': r['run_id'], 'task': r['task'], 'harness': r['harness'], 'seed': r['seed'], 'run': r['run'],
        'passed': bool(r['passed']), 'breach': bool(r.get('breach')), 'error': bool(r.get('error')),
        'checks': [{'name': c['name'], 'type': c['type'], 'passed': bool(c['passed']), 'breach': bool(c.get('breach'))}
                   for c in r['checks']],
        'turns': [{k: t[k] for k in ('n', 'date', 'exit_code', 'timed_out', 'wall_s')} for t in r['turns']],
        'wall_s': r['wall_s'],
        'usage': {k: u.get(k, 0) for k in ('requests', 'input', 'cached_input', 'output', 'reasoning')},
        'cost_usd': r.get('cost_usd'),
        'result_sha256': hashlib.sha256(raw).hexdigest(),
        'final_db_sha256': sha256_file(os.path.join(run_dir, 'final.db')),
        'workspace_sha256': dict(sorted(files.items())),
    }


def summarize(rows: list[dict], repetitions: int) -> dict:
    out = {}
    for cell in sorted({r['harness'] for r in rows}):
        rs = [r for r in rows if r['harness'] == cell]
        by_task = {}
        for t in sorted({r['task'] for r in rs}):
            ts = [r for r in rs if r['task'] == t]
            by_task[t] = {'attempts': len(ts), 'passed': sum(r['passed'] for r in ts),
                          'breaches': sum(r['breach'] for r in ts), 'errors': sum(r['error'] for r in ts)}
        walls = sorted(r['wall_s'] for r in rs)
        usage = {k: sum(r['usage'][k] for r in rs) for k in ('requests', 'input', 'cached_input', 'output', 'reasoning')}
        costs = [r['cost_usd'] for r in rs if r['cost_usd'] is not None]
        out[cell] = {
            'attempts': len(rs), 'passed': sum(r['passed'] for r in rs),
            'pass_rate': round(sum(r['passed'] for r in rs) / len(rs), 4),
            'breaches': sum(r['breach'] for r in rs), 'errors': sum(r['error'] for r in rs),
            'tasks': len(by_task),
            'tasks_passed_every_time': sum(1 for v in by_task.values() if v['passed'] == v['attempts'] == repetitions),
            'tasks_passed_at_least_once': sum(1 for v in by_task.values() if v['passed'] > 0),
            'median_wall_s': round(statistics.median(walls), 1),
            'p90_wall_s': round(walls[min(len(walls) - 1, int(0.9 * len(walls)))], 1),
            'usage': usage,
            'estimated_cost_usd': round(sum(costs), 4) if costs else None,
            'by_task': by_task,
        }
    return out


def ledger_text(rows: list[dict]) -> str:
    rows = sorted(rows, key=lambda r: (r['task'], r['harness'], r['run']))
    return ''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows)


def validate_matrix(rows: list[dict], description: dict) -> None:
    """Require the declared experiment, not merely the expected number of rows."""
    tasks = description.get('tasks')
    cells = description.get('cells')
    repetitions = description.get('repetitions')
    seed = description.get('seed')
    if not isinstance(tasks, list) or not tasks or any(not isinstance(t, str) or not t for t in tasks):
        raise SystemExit('campaign must declare a nonempty tasks list before export')
    if len(tasks) != len(set(tasks)):
        raise SystemExit('campaign tasks must be distinct')
    if not isinstance(cells, dict) or not cells or any(not isinstance(c, str) or not c for c in cells):
        raise SystemExit('campaign must declare nonempty cells')
    if type(repetitions) is not int or repetitions < 1 or type(seed) is not int:
        raise SystemExit('campaign repetitions must be a positive integer and seed an integer')
    expected = {(task, cell, seed, run) for task in tasks for cell in cells
                for run in range(1, repetitions + 1)}
    seen, run_ids = set(), set()
    for row in rows:
        if (not isinstance(row.get('task'), str) or not isinstance(row.get('harness'), str)
                or type(row.get('seed')) is not int or type(row.get('run')) is not int):
            raise SystemExit('attempt task/cell must be strings and seed/repetition integers')
        identity = (row['task'], row['harness'], row['seed'], row['run'])
        if identity in seen:
            raise SystemExit(f'duplicate attempt identity: {identity}')
        seen.add(identity)
        run_id = row.get('run_id')
        if not isinstance(run_id, str) or not run_id or run_id in run_ids:
            raise SystemExit(f'missing or duplicate run_id: {run_id!r}')
        run_ids.add(run_id)
    missing, unexpected = expected - seen, seen - expected
    if missing or unexpected:
        raise SystemExit(f'campaign matrix mismatch: {len(missing)} missing, {len(unexpected)} unexpected; '
                         'check declared tasks, cells, seed and repetition identifiers')


def export(label: str) -> None:
    src = os.path.join(ROOT, 'results', label)
    desc = json.load(open(os.path.join(src, 'campaign.json'), encoding='utf-8'))
    runs = sorted(d for d in os.listdir(src) if os.path.isfile(os.path.join(src, d, 'result.json')))
    rows = [attempt_record(os.path.join(src, d)) for d in runs]
    validate_matrix(rows, desc)
    text = ledger_text(rows)
    out = os.path.join(PUBLISHED, label)
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, 'attempts.jsonl'), 'w', encoding='utf-8').write(text)
    summary = summarize(rows, desc['repetitions'])
    json.dump(summary, open(os.path.join(out, 'summary.json'), 'w', encoding='utf-8'), indent=2, sort_keys=True)
    git = lambda *a: subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    provenance = {
        **desc,
        'tasks': sorted({r['task'] for r in rows}),
        'attempts': len(rows),
        'bench_commit_at_export': git('rev-parse', 'HEAD'),
        'task_tree_sha1': git('rev-parse', 'HEAD:tasks/process'),
        'ledger_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'exported_utc': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    json.dump(provenance, open(os.path.join(out, 'provenance.json'), 'w', encoding='utf-8'), indent=2)
    verify_one(out)
    print(f'exported {len(rows)} attempts to {os.path.relpath(out, ROOT)}')
    for cell, s in summary.items():
        print(f'  {cell}: {s["passed"]}/{s["attempts"]} passed, {s["tasks_passed_every_time"]}/{s["tasks"]} tasks every time, '
              f'{s["breaches"]} breaches, {s["errors"]} errors')


def verify_one(out: str) -> None:
    data = open(os.path.join(out, 'attempts.jsonl'), 'rb').read()
    prov = json.load(open(os.path.join(out, 'provenance.json'), encoding='utf-8'))
    if hashlib.sha256(data).hexdigest() != prov['ledger_sha256']:
        raise SystemExit(f'{out}: ledger hash does not match provenance')
    rows = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
    validate_matrix(rows, prov)
    if ledger_text(rows).encode() != data:
        raise SystemExit(f'{out}: ledger is not in canonical order')
    if len(rows) != prov['attempts'] or len(rows) != len(prov['cells']) * prov['repetitions'] * len(prov['tasks']):
        raise SystemExit(f'{out}: ledger has {len(rows)} attempts; provenance expects a complete matrix')
    if summarize(rows, prov['repetitions']) != json.load(open(os.path.join(out, 'summary.json'), encoding='utf-8')):
        raise SystemExit(f'{out}: summary.json does not match the ledger')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--label')
    ap.add_argument('--verify', action='store_true')
    a = ap.parse_args()
    if a.verify:
        dirs = sorted(d for d in os.listdir(PUBLISHED) if os.path.isfile(os.path.join(PUBLISHED, d, 'provenance.json'))) \
            if os.path.isdir(PUBLISHED) else []
        for d in dirs:
            verify_one(os.path.join(PUBLISHED, d))
        print(f'verified {len(dirs)} published process campaign(s)')
        return
    if not a.label:
        ap.error('--label or --verify')
    export(a.label)


if __name__ == '__main__':
    main()
