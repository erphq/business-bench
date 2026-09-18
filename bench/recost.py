"""Recompute cost_usd in every results/*/*/result.json from its stored usage and bench/prices.json.

    python bench/recost.py [--write] [--label LABEL ...]

Without --write it only prints the per-label, per-harness table (runs, mean tokens, mean $/run).
"""
import glob, json, os, statistics as st, sys
sys.path.insert(0, os.path.dirname(__file__))
from usage import cost_usd  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
PRICES = json.load(open(os.path.join(ROOT, 'bench', 'prices.json')))
write = '--write' in sys.argv
labels = [a for a in sys.argv[1:] if not a.startswith('--')]

rows = {}
changed = 0
paths = glob.glob(os.path.join(ROOT, 'results', '*', '*', 'result.json')) + glob.glob(os.path.join(ROOT, 'results', 'box', '*', '*', 'result.json'))
for path in sorted(paths):
    label, run_id = path.split(os.sep)[-3], path.split(os.sep)[-2]
    if labels and label not in labels:
        continue
    try:
        r = json.load(open(path))
    except Exception:
        continue
    u = r.get('usage') or {}
    if not u.get('by_model'):
        continue
    harness = r.get('harness') or run_id.split('__')[1]
    c = cost_usd(u, PRICES)
    if write and c != r.get('cost_usd'):
        r['cost_usd'] = c
        json.dump(r, open(path, 'w'), indent=1)
        changed += 1
    row = rows.setdefault((label, harness), {'n': 0, 'in': [], 'cached': [], 'out': [], 'cost': [], 'models': set()})
    row['n'] += 1
    for m, d in u['by_model'].items():
        row['models'].add(m)
    row['in'].append(sum(d.get('input', 0) for d in u['by_model'].values()))
    row['cached'].append(sum(d.get('cached_input', 0) for d in u['by_model'].values()))
    row['out'].append(sum(d.get('output', 0) for d in u['by_model'].values()))
    if c is not None:
        row['cost'].append(c)

hdr = ('label', 'harness', 'n', 'in/run', 'cached/run', 'out/run', 'mean $/run', 'median $/run', 'total $', 'models')
print('%-26s %-13s %4s %11s %12s %9s %11s %13s %9s  %s' % hdr)
for (label, harness), r in sorted(rows.items()):
    n = r['n']
    cost = r['cost']
    mean_c = '$%.3f' % st.mean(cost) if len(cost) == n else 'n/a(%d/%d)' % (len(cost), n)
    med_c = '$%.3f' % st.median(cost) if len(cost) == n else ''
    tot = '$%.2f' % sum(cost) if cost else ''
    print('%-26s %-13s %4d %11d %12d %9d %11s %13s %9s  %s' % (
        label, harness, n, st.mean(r['in']), st.mean(r['cached']), st.mean(r['out']), mean_c, med_c, tot, ','.join(sorted(r['models']))))
if write:
    print('rewrote cost_usd in %d result files' % changed)
