"""Publish the complete two-system comparison, preserving raw and frozen verdicts."""
import argparse, collections, hashlib, json, math, shlex, statistics, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ARMS = ('proto-deepseek', 'codex-sol')
SCORER_HASH = 'b4720db00f2a55461ca70767a4baf8dd2d25aa9d301e8fe22ea13d21ccca358f'

def aggregate(rows):
    output = []
    expected = {p.parent.name for p in (ROOT / 'tasks/desk').glob('*/task.yaml')}
    for arm in ARMS:
        rs = [r for r in rows if r['harness'] == arm]
        tasks = collections.defaultdict(list)
        for r in rs: tasks[r['task']].append(r)
        if set(tasks) != expected or any(sorted(r['run'] for r in ts) != [1,2,3] for ts in tasks.values()):
            raise ValueError('Incomplete or duplicate matrix: ' + arm)
        costs = [r['cost_usd'] for r in rs if r['cost_usd'] is not None]
        times = sorted(r['wall_s'] for r in rs)
        usage = {k: sum(r['usage'].get(k,0) or 0 for r in rs) for k in ('input','cached_input','output')}
        usage['uncached_input'] = usage['input'] - usage['cached_input']
        output.append(dict(harness=arm,tasks=len(tasks),attempts=len(rs),passed=sum(r['passed'] for r in rs),
            raw_passed=sum(r['raw_passed'] for r in rs),pass_rate=sum(r['passed'] for r in rs)/len(rs),
            all_three_pass=sum(all(r['passed'] for r in ts) for ts in tasks.values()),
            by_repetition={str(i):sum(r['passed'] for r in rs if r['run']==i) for i in (1,2,3)},
            raw_by_repetition={str(i):sum(r['raw_passed'] for r in rs if r['run']==i) for i in (1,2,3)},
            timed_out=sum(r['timed_out'] for r in rs),nonzero_exit=sum(r['exit_code']!=0 for r in rs),
            passing_abnormal_exit=sum(r['passed'] and (r['timed_out'] or r['exit_code']!=0) for r in rs),
            grader_error_attempts=sum(r['grader_error_count']>0 for r in rs),
            raw_grader_error_attempts=sum(r['raw_grader_error_count']>0 for r in rs),
            usage_missing=sum(not r['usage'].get('by_model') for r in rs),cost_observations=len(costs),
            estimated_cost_sum_usd=round(sum(costs),4),estimated_cost_mean_usd=round(statistics.mean(costs),4),
            median_wall_s=statistics.median(times),p90_wall_s=times[math.ceil(.9*len(times))-1],
            sum_wall_s=round(sum(times),1),usage=usage,
            by_category={c:dict(attempts=len(cr),passed=sum(r['passed'] for r in cr))
                for c in sorted({r['category'] for r in rs}) for cr in [[r for r in rs if r['category']==c]]}))
    return output

def verify():
    target=ROOT/'results/latest'; data=(target/'attempts.jsonl').read_bytes()
    rows=[json.loads(line) for line in data.splitlines()]
    assert len(rows)==len({(r['harness'],r['task'],r['run']) for r in rows})==1122
    assert aggregate(rows)==json.loads((target/'summary.json').read_text())
    assert hashlib.sha256(data).hexdigest()==json.loads((target/'provenance.json').read_text())['ledger_sha256']
    frozen=ROOT/'scoring/frozen-v7'
    assert hashlib.sha256((frozen/'manifest.json').read_bytes()).hexdigest()==SCORER_HASH
    for p,h in json.loads((frozen/'manifest.json').read_text())['files'].items():
        assert hashlib.sha256((frozen/p).read_bytes()).hexdigest()==h,p
    assert {r['scorer_manifest_sha256'] for r in rows}=={SCORER_HASH}
    assert [r['passed'] for r in aggregate(rows)]==[507,473]
    print('Verified 1122 attempts: 507/561 vs 473/561; frozen scorer fingerprint verified')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify',action='store_true'); ap.add_argument('--ssh'); ap.add_argument('--source')
    ap.add_argument('--scorecard'); ap.add_argument('--replace-release',action='store_true')
    a=ap.parse_args()
    if a.verify: return verify()
    if not all((a.ssh,a.source,a.scorecard,a.replace_release)): ap.error('Export requires all source arguments and --replace-release')
    card=json.loads(Path(a.scorecard).read_text())
    program='''import pathlib,json,hashlib,sys
root=pathlib.Path(sys.argv[1]); card=json.load(sys.stdin)
for a in card['attempts']:
 p=root/a['label']/a['run_id']/'result.json'; raw=p.read_bytes(); r=json.loads(raw)
 rp=root/'frozen-v7-receipts'/a['label']/(a['run_id']+'.json'); rb=rp.read_bytes(); receipt=json.loads(rb)
 assert hashlib.sha256(raw).hexdigest()==a['original_result_sha256'],str(p)
 assert receipt['original_result_sha256']==a['original_result_sha256']
 assert receipt['scorer_manifest_sha256']==a['scorer_manifest_sha256']
 assert receipt['verdict']['passed']==a['frozen_passed']
 out={k:r.get(k) for k in ('task','category','harness','exit_code','timed_out','wall_s','cost_usd')}
 out.update(run=a['repetition'],run_id=a['task']+'__'+r['harness']+'__r'+str(a['repetition']),passed=a['frozen_passed'],raw_passed=a['raw_passed'],source_sha256=a['original_result_sha256'],receipt_sha256=hashlib.sha256(rb).hexdigest(),scorer_manifest_sha256=a['scorer_manifest_sha256'],grader_error_count=len(a['grader_errors']),raw_grader_error_count=len(a['raw_grader_errors']))
 out['checks']=[{k:c.get(k) for k in ('name','type','required','passed')} for c in receipt['verdict']['checks']]
 out['artifact_hashes']=receipt['artifact_hashes']; u=r.get('usage') or {}
 out['usage']={k:u.get(k,0) for k in ('requests','input','cached_input','output','reasoning')}
 out['usage']['by_model']={m:{k:v for k,v in d.items() if isinstance(v,(int,float))} for m,d in u.get('by_model',{}).items()}
 print(json.dumps(out,sort_keys=True))
'''
    data=subprocess.check_output(['ssh',a.ssh,shlex.join(['python3','-c',program,a.source])],input=json.dumps(card),text=True)
    rows=[json.loads(s) for s in data.splitlines()]; summary=aggregate(rows)
    assert [r['passed'] for r in summary]==[507,473]
    target=ROOT/'results/latest'
    (target/'attempts.jsonl').write_text(data); (target/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    provenance=dict(campaign='complete-desk-comparison-2026-09-16',track='desk',repetitions=3,expected_tasks_per_arm=187,
        included_arms=list(ARMS),scorecard_snapshot_utc=card['snapshot_utc'],
        ledger_sha256=hashlib.sha256(data.encode()).hexdigest(),scorer_manifest_sha256=SCORER_HASH,
        original_scorecard_sha256=hashlib.sha256(Path(a.scorecard).read_bytes()).hexdigest(),
        configurations={'proto-deepseek':dict(runtime_commit='c8f62dd60',model='deepseek/deepseek-v4.1-flash',provider='DeepSeek only',fallbacks=False,reasoning='high',temperature=0,max_tokens=65536),
            'codex-sol':dict(model='gpt-5.6-sol',reasoning='high',cli_version='0.154.0',sampling='CLI-managed; not asserted matched to Proto')},
        source_cohorts={'proto-deepseek':['broad-desk-v43-c8f62dd60 r1','repeat-desk-v43-c8f62dd60 local r1/r2 map to logical r2/r3'],'codex-sol':['full-1-codex-sol r1/r2/r3']},
        evidence_verification='Original result hashes, receipt scorer identity and frozen verdicts checked for every attempt during export; frozen scorer package file hashes verified.',
        scorer_note='Immutable manifest retains original assembly-status text; subsequent 1341-attempt replay reported zero differences. Original bytes are preserved.',
        paired_task_bootstrap=card['paired_task_bootstrap'],cost_note=card['cost_label'],
        limitations='Development task set; different models and non-contemporaneous cohorts. Not a causal harness-only or unseen-generalization comparison. Raw artifacts remain private; hashes identify but do not reconstruct them.',
        build_status='No completed fully acceptance-validated build campaign published.',
        exclusions='Later Proto-vs-Proto experiments, pilots, tuning history, unrelated old arms, raw traces and credentials.')
    (target/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n'); verify(); print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
