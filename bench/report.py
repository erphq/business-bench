#!/usr/bin/env python3
"""Aggregate results into markdown tables.

  report.py results/<label> [results/<label2> ...]     one table per harness × label, plus a task matrix
"""
import glob, json, os, statistics as st, sys

def load(dirs):
    rows = []
    for d in dirs:
        label = os.path.basename(os.path.normpath(d))
        for p in glob.glob(os.path.join(d, '*', 'result.json')):
            r = json.load(open(p)); r['label'] = label; rows.append(r)
    return rows

def main(dirs):
    rows = load(dirs)
    if not rows:
        print('no results'); return
    key = lambda r: f"{r['harness']} [{r['label']}]" if len(dirs) > 1 else r['harness']
    groups: dict[str, list] = {}
    for r in rows: groups.setdefault(key(r), []).append(r)
    print(f"\n## {', '.join(os.path.basename(os.path.normpath(d)) for d in dirs)}  ({len(rows)} runs)\n")
    print('| cell | runs | pass | timeouts | median min | mean min | in tok/run | out tok/run | cost/run |')
    print('|---|---|---|---|---|---|---|---|---|')
    for k, rs in sorted(groups.items()):
        n = len(rs); passed = sum(r['passed'] for r in rs); to = sum(r['timed_out'] for r in rs)
        walls = [r['wall_s'] / 60 for r in rs]
        tin = st.mean([r['usage'].get('input', 0) for r in rs]); tout = st.mean([r['usage'].get('output', 0) for r in rs])
        costs = [r['cost_usd'] for r in rs if r.get('cost_usd') is not None]
        cost = f'${st.mean(costs):.3f}' if costs and len(costs) == n else 'n/a'
        print(f'| {k} | {n} | {passed}/{n} ({100*passed/n:.0f}%) | {to} | {st.median(walls):.1f} | {st.mean(walls):.1f} | {tin:,.0f} | {tout:,.0f} | {cost} |')
    tasks = sorted({r['task'] for r in rows}); cols = sorted(groups)
    print('\n| task | ' + ' | '.join(cols) + ' |')
    print('|---|' + '---|' * len(cols))
    for t in tasks:
        cells = []
        for c in cols:
            rs = [r for r in groups[c] if r['task'] == t]
            if not rs: cells.append('—'); continue
            p = sum(r['passed'] for r in rs)
            mark = 'pass' if p == len(rs) else ('FAIL' if p == 0 else f'{p}/{len(rs)}')
            cells.append(f"{mark} · {st.mean([r['wall_s'] for r in rs])/60:.1f}m")
        print(f'| {t} | ' + ' | '.join(cells) + ' |')
    print()
    for r in sorted(rows, key=lambda r: (r['task'], r['harness'], r['label'], r['run'])):
        if not r['passed']:
            bad = [f"{c['name']}: {c['detail'][:100]}" for c in r['checks'] if not c['passed']]
            print(f"- {r['label']}/{r['run_id']}: " + ' | '.join(bad))

if __name__ == '__main__':
    main(sys.argv[1:])
