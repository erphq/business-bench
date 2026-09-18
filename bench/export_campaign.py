#!/usr/bin/env python3
"""Export a complete recorded desk campaign without homes, logs or private paths."""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ARMS = ('codex-sol', 'proto-deepseek', 'proto-glm', 'proto-qwen')


def aggregate(rows):
    summaries = []
    for arm in ARMS:
        selected = [r for r in rows if r['harness'] == arm]
        tasks = collections.defaultdict(list)
        for row in selected:
            tasks[row['task']].append(row)
        expected = {p.parent.name for p in (ROOT / 'tasks/desk').glob('*/task.yaml')}
        if set(tasks) != expected or any(sorted(r['run'] for r in rs) != [1, 2, 3] for rs in tasks.values()):
            raise ValueError(f'{arm}: not a complete three-repetition task matrix')
        passes = sum(r['passed'] for r in selected)
        costs = [r['cost_usd'] for r in selected if r['cost_usd'] is not None]
        summaries.append(dict(harness=arm, tasks=len(tasks), attempts=len(selected), passed=passes,
            pass_rate=passes / len(selected), all_three_pass=sum(all(r['passed'] for r in rs) for rs in tasks.values()),
            by_repetition={str(i): sum(r['passed'] for r in selected if r['run'] == i) for i in (1, 2, 3)},
            timed_out=sum(r['timed_out'] for r in selected),
            nonzero_exit=sum(r['exit_code'] != 0 for r in selected),
            passing_abnormal_exit=sum(r['passed'] and (r['timed_out'] or r['exit_code'] != 0) for r in selected),
            grader_error_attempts=sum(r['grader_error_count'] > 0 for r in selected),
            usage_missing=sum(not r['usage'].get('by_model') for r in selected),
            cost_observations=len(costs), estimated_cost_sum_usd=round(sum(costs), 4),
            estimated_cost_mean_usd=round(statistics.mean(costs), 4) if costs else None,
            median_wall_s=statistics.median(r['wall_s'] for r in selected),
            by_category={c: {'attempts': len(cr), 'passed': sum(r['passed'] for r in cr)}
                for c in sorted({r['category'] for r in selected})
                for cr in [[r for r in selected if r['category'] == c]]}))
    return summaries


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', help='results directory containing full-1-*; local or remote with --ssh')
    ap.add_argument('--ssh', help='operator-provided SSH host alias')
    ap.add_argument('--verify', action='store_true', help='recompute summary from the published ledger')
    a = ap.parse_args()
    target = ROOT / 'results/latest'
    if a.verify:
        ledger = (target / 'attempts.jsonl').read_text()
        rows = [json.loads(line) for line in ledger.splitlines()]
        assert aggregate(rows) == json.loads((target / 'summary.json').read_text())
        assert hashlib.sha256(ledger.encode()).hexdigest() == json.loads((target / 'provenance.json').read_text())['ledger_sha256']
        print(f'Verified {len(rows)} attempts across {len(ARMS)} complete arms')
        return
    if not a.source:
        ap.error('--source is required for export')
    # Only result.json is read; unbounded logs, session content and credentials are never transferred.
    program = '''import pathlib,json,hashlib,sys
root=pathlib.Path(sys.argv[1])
for arm in ('codex-sol','proto-deepseek','proto-glm','proto-qwen'):
 for p in sorted((root/('full-1-'+arm)).glob('*/result.json')):
  raw=p.read_bytes(); r=json.loads(raw)
  fields=('run_id','task','category','harness','run','exit_code','timed_out','wall_s','passed','cost_usd')
  out={k:r.get(k) for k in fields}
  out['source_sha256']=hashlib.sha256(raw).hexdigest()
  out['source_modified_utc']=__import__('datetime').datetime.fromtimestamp(p.stat().st_mtime,__import__('datetime').timezone.utc).isoformat()
  out['grader_error_count']=len(r.get('grader_errors') or [])
  out['checks']=[{k:c.get(k) for k in ('name','type','required','passed')} for c in r.get('checks',[])]
  usage=r.get('usage') or {}
  out['usage']={k:usage.get(k,0) for k in ('requests','input','cached_input','output','reasoning')}
  out['usage']['by_model']={m:{k:v for k,v in d.items() if isinstance(v,(int,float))} for m,d in usage.get('by_model',{}).items()}
  print(json.dumps(out,sort_keys=True))
'''
    import shlex
    command = ['python3', '-c', program, a.source]
    if a.ssh:
        command = ['ssh', a.ssh, shlex.join(command)]
    content = subprocess.check_output(command, text=True)
    rows = [json.loads(line) for line in content.splitlines()]
    summary = aggregate(rows)
    target.mkdir(parents=True, exist_ok=True)
    if (target / 'attempts.jsonl').exists():
        raise FileExistsError('Released ledger already exists; export a new release in a separate checkout')
    (target / 'attempts.jsonl').write_text(content)
    (target / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    provenance = dict(campaign='full-1', track='desk', release_kind='recorded scoring snapshot',
        exported_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ledger_sha256=hashlib.sha256(content.encode()).hexdigest(),
        included_arms=list(ARMS), expected_tasks_per_arm=187, repetitions=3,
        launch_configuration={'image_tag':'business-bench:v38','runtime_revision_recorded_by_launcher':'53a303309',
            'codex_cli_version_in_image_recipe':'0.154.0','reasoning_effort':'high',
            'api_arm_parallelism':5,'codex_parallelism':2,'cpus_per_attempt':2,'memory_per_attempt':'6g',
            'recalculation_image':'bench-recalc:v1'},
        scorer_provenance='Original result records lack per-attempt scorer hashes. No uniform immutable scorer identity is asserted. Results are exported as recorded, not rescored with release source.',
        runtime_provenance='Image tag and short revision are launcher metadata, not a recovered image digest. Historical runtime binaries and credential-dependent skill installations are not distributed.',
        build_status='No completed, fully acceptance-validated build campaign included.',
        exclusions='Incomplete arms, development comparisons, pilots, tuning history, raw outputs, session traces, homes and credentials.')
    (target / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
