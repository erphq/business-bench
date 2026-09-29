#!/usr/bin/env python3
"""Export and verify named desk campaigns under results/desk/<campaign>/.

A campaign is declared in results/desk/<campaign>/campaign.json: its arms (each with the private run label, or list
of labels, it was executed under and its configuration), repetitions, execution window and limitations. Export reads every attempt's
original result and conservative-v7 receipt over ssh, checks that each receipt scored exactly that result with the
frozen scorer, and writes attempts.jsonl, summary.json and provenance.json. --verify checks every published desk
campaign here: the complete task x arm x repetition matrix, summary arithmetic, the paired bootstrap, the ledger hash
and the frozen scorer fingerprint. The 2026-09-16 comparison in results/latest keeps its own verifier.
"""
import argparse
import collections
import hashlib
import json
import math
import random
import shlex
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESK = ROOT / 'results/desk'
SCORER = ROOT / 'scoring/frozen-v7'
SCORER_HASH = 'b4720db00f2a55461ca70767a4baf8dd2d25aa9d301e8fe22ea13d21ccca358f'

REMOTE = r'''
import hashlib, json, pathlib, sys
source, receipts = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
for arm, label, rename, omit_cost in json.load(sys.stdin):
    for result_path in sorted((source / label).glob('*/result.json')):
        raw = result_path.read_bytes(); r = json.loads(raw); run_id = result_path.parent.name
        rb = (receipts / label / (run_id + '.json')).read_bytes(); receipt = json.loads(rb)
        assert receipt['run_id'] == run_id, run_id
        assert receipt['original_result_sha256'] == hashlib.sha256(raw).hexdigest(), run_id
        rep = int(receipt.get('logical_repetition') or r.get('run') or 1)
        out = {k: r.get(k) for k in ('task', 'category', 'exit_code', 'timed_out', 'wall_s', 'cost_usd')}
        if omit_cost:
            out['cost_usd'] = None
        out.update(harness=arm, run=rep, run_id=f"{r['task']}__{arm}__r{rep}", passed=bool(receipt['verdict']['passed']),
                   raw_passed=bool(r.get('passed')), source_sha256=receipt['original_result_sha256'],
                   receipt_sha256=hashlib.sha256(rb).hexdigest(), scorer_manifest_sha256=receipt['scorer_manifest_sha256'],
                   grader_error_count=len(receipt['verdict'].get('grader_errors') or []),
                   raw_grader_error_count=len(r.get('grader_errors') or []))
        out['checks'] = [{k: c.get(k) for k in ('name', 'type', 'required', 'passed')} for c in receipt['verdict']['checks']]
        out['artifact_hashes'] = receipt['artifact_hashes']
        u = r.get('usage') or {}
        out['usage'] = {k: u.get(k, 0) for k in ('requests', 'input', 'cached_input', 'output', 'reasoning')}
        out['usage']['by_model'] = {rename.get(m, m): {k: v for k, v in d.items() if isinstance(v, (int, float))}
                                    for m, d in (u.get('by_model') or {}).items()}
        print(json.dumps(out, sort_keys=True))
'''


def expected_tasks():
    return {p.parent.name for p in (ROOT / 'tasks/desk').glob('*/task.yaml')}


def aggregate(rows, arms, repetitions):
    output, expected = [], expected_tasks()
    for arm in arms:
        rs = [r for r in rows if r['harness'] == arm]
        tasks = collections.defaultdict(list)
        for r in rs:
            tasks[r['task']].append(r)
        if set(tasks) != expected or any(sorted(r['run'] for r in ts) != list(range(1, repetitions + 1))
                                         for ts in tasks.values()):
            raise ValueError('Incomplete or duplicate matrix: ' + arm)
        costs = [r['cost_usd'] for r in rs if r['cost_usd'] is not None]
        times = sorted(r['wall_s'] for r in rs)
        usage = {k: sum(r['usage'].get(k, 0) or 0 for r in rs) for k in ('input', 'cached_input', 'output')}
        usage['uncached_input'] = usage['input'] - usage['cached_input']
        output.append(dict(
            harness=arm, tasks=len(tasks), attempts=len(rs), passed=sum(r['passed'] for r in rs),
            raw_passed=sum(r['raw_passed'] for r in rs), pass_rate=sum(r['passed'] for r in rs) / len(rs),
            all_repetitions_pass=sum(all(r['passed'] for r in ts) for ts in tasks.values()),
            by_repetition={str(i): sum(r['passed'] for r in rs if r['run'] == i) for i in range(1, repetitions + 1)},
            raw_by_repetition={str(i): sum(r['raw_passed'] for r in rs if r['run'] == i)
                               for i in range(1, repetitions + 1)},
            timed_out=sum(r['timed_out'] for r in rs), nonzero_exit=sum(r['exit_code'] != 0 for r in rs),
            passing_abnormal_exit=sum(r['passed'] and (r['timed_out'] or r['exit_code'] != 0) for r in rs),
            grader_error_attempts=sum(r['grader_error_count'] > 0 for r in rs),
            raw_grader_error_attempts=sum(r['raw_grader_error_count'] > 0 for r in rs),
            usage_missing=sum(not r['usage'].get('by_model') for r in rs), cost_observations=len(costs),
            estimated_cost_sum_usd=round(sum(costs), 4) if costs else None,
            estimated_cost_mean_usd=round(statistics.mean(costs), 4) if costs else None,
            median_wall_s=statistics.median(times), p90_wall_s=times[math.ceil(.9 * len(times)) - 1],
            sum_wall_s=round(sum(times), 1), usage=usage,
            by_category={c: dict(attempts=len(cr), passed=sum(r['passed'] for r in cr))
                         for c in sorted({r['category'] for r in rs}) for cr in [[r for r in rs if r['category'] == c]]}))
    return output


def paired_bootstrap(rows, first, second, seed, samples):
    """Task-clustered paired bootstrap of the pass-rate difference (percentage points), repetitions kept together."""
    rate = {}
    for arm in (first, second):
        by_task = collections.defaultdict(list)
        for r in rows:
            if r['harness'] == arm:
                by_task[r['task']].append(r['passed'])
        rate[arm] = {t: sum(v) / len(v) for t, v in by_task.items()}
    tasks = sorted(rate[first])
    diffs = [rate[first][t] - rate[second][t] for t in tasks]
    rng = random.Random(seed)
    draws = sorted(sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs) for _ in range(samples))
    lo, hi = draws[int(.025 * samples)], draws[int(.975 * samples) - 1]
    return dict(arms=[first, second], difference_percentage_points=100 * sum(diffs) / len(diffs),
                bootstrap_95_percent_interval_pp=[100 * lo, 100 * hi],
                resampling_unit='task, with its repetitions kept together', seed=seed, samples=samples,
                limitation='Descriptive uncertainty for these task families; not evidence of unseen superiority.')


def scorer_fingerprint():
    assert hashlib.sha256((SCORER / 'manifest.json').read_bytes()).hexdigest() == SCORER_HASH
    for p, h in json.loads((SCORER / 'manifest.json').read_text())['files'].items():
        assert hashlib.sha256((SCORER / p).read_bytes()).hexdigest() == h, p


def verify_campaign(folder: Path):
    decl = json.loads((folder / 'campaign.json').read_text())
    data = (folder / 'attempts.jsonl').read_bytes()
    rows = [json.loads(line) for line in data.splitlines()]
    arms, reps = list(decl['arms']), decl['repetitions']
    assert len(rows) == len({(r['harness'], r['task'], r['run']) for r in rows}) == len(arms) * len(expected_tasks()) * reps
    summary = aggregate(rows, arms, reps)
    assert summary == json.loads((folder / 'summary.json').read_text()), 'summary.json does not match the ledger'
    provenance = json.loads((folder / 'provenance.json').read_text())
    assert provenance['campaign'] == decl['campaign'] == folder.name
    assert hashlib.sha256(data).hexdigest() == provenance['ledger_sha256'], 'ledger hash'
    assert {r['scorer_manifest_sha256'] for r in rows} == {SCORER_HASH}
    scorer_fingerprint()
    pair = decl.get('paired_comparison')
    if pair:
        got = paired_bootstrap(rows, *pair['arms'], pair['seed'], pair['samples'])
        want = provenance['paired_task_bootstrap']
        assert got['arms'] == want['arms'] and all(
            math.isclose(got[k], want[k], abs_tol=1e-9) for k in ('difference_percentage_points',)) and all(
            math.isclose(a, b, abs_tol=1e-9) for a, b in zip(got['bootstrap_95_percent_interval_pp'],
                                                            want['bootstrap_95_percent_interval_pp'])), 'bootstrap'
    scores = ', '.join(f"{s['harness']} {s['passed']}/{s['attempts']}" for s in summary)
    print(f'Verified {folder.name}: {len(rows)} attempts ({scores}); frozen scorer fingerprint verified')
    return summary


def verify_all():
    folders = sorted(p.parent for p in DESK.glob('*/campaign.json'))
    for folder in folders:
        verify_campaign(folder)
    if not folders:
        print('No desk campaigns under results/desk')


def export(campaign, ssh, source, receipts):
    folder = DESK / campaign
    decl = json.loads((folder / 'campaign.json').read_text())
    spec = [[arm, label, cfg.get('usage_model_rename', {}), bool(cfg.get('omit_cost'))]
            for arm, cfg in decl['arms'].items() for label in cfg.get('labels') or [cfg['label']]]
    data = subprocess.check_output(['ssh', ssh, shlex.join(['python3', '-c', REMOTE, source, receipts])],
                                   input=json.dumps(spec), text=True)
    rows = [json.loads(line) for line in data.splitlines()]
    other = {r['run_id'] for r in rows if r['scorer_manifest_sha256'] != SCORER_HASH}
    if other:
        raise ValueError(f'{len(other)} receipts come from another scorer, e.g. {sorted(other)[0]}')
    arms, reps = list(decl['arms']), decl['repetitions']
    summary = aggregate(rows, arms, reps)
    (folder / 'attempts.jsonl').write_text(data)
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    provenance = dict(
        campaign=decl['campaign'], track='desk', repetitions=reps, expected_tasks_per_arm=len(expected_tasks()),
        included_arms=arms, execution_window_utc=decl['execution_window_utc'],
        ledger_sha256=hashlib.sha256(data.encode()).hexdigest(), scorer_manifest_sha256=SCORER_HASH,
        configurations={arm: cfg['configuration'] for arm, cfg in decl['arms'].items()},
        evidence_verification='Every attempt: the receipt names this run, its original_result_sha256 equals the hash of '
                              'the original result.json, and it was scored by the frozen conservative-v7 package.',
        cost_note=decl['cost_note'], usage_note=decl['usage_note'], limitations=decl['limitations'],
        exclusions=decl['exclusions'])
    if decl.get('conditions_by_repetition'):
        provenance['conditions_by_repetition'] = decl['conditions_by_repetition']
    pair = decl.get('paired_comparison')
    if pair:
        provenance['paired_task_bootstrap'] = paired_bootstrap(rows, *pair['arms'], pair['seed'], pair['samples'])
    (folder / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    verify_campaign(folder)
    print(json.dumps(summary, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', action='store_true', help='verify every published campaign under results/desk')
    ap.add_argument('--export', metavar='CAMPAIGN', help='campaign folder name under results/desk')
    ap.add_argument('--ssh', help='host holding the private run results')
    ap.add_argument('--source', help='root folder holding <label>/<run_id>/result.json on that host')
    ap.add_argument('--receipts', help='root folder holding <label>/<run_id>.json frozen receipts on that host')
    a = ap.parse_args()
    if a.export:
        if not all((a.ssh, a.source, a.receipts)):
            ap.error('--export needs --ssh, --source and --receipts')
        return export(a.export, a.ssh, a.source, a.receipts)
    return verify_all()


if __name__ == '__main__':
    main()
