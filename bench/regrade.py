#!/usr/bin/env python3
"""Re-grade finished runs in place after a grader fix: regrade.py results/<label> [...]
Rewrites passed/checks in each result.json (agent outputs are untouched)."""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade import grade
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in sys.argv[1:]:
    for rp in sorted(glob.glob(os.path.join(d, '*', 'result.json'))):
        r = json.load(open(rp)); run_dir = os.path.dirname(rp)
        track_root = os.path.join(ROOT, 'tasks', 'desk')
        g = grade(os.path.join(track_root, r['task']), os.path.join(run_dir, 'ws'))
        before = r['passed']; r['passed'] = g['passed']; r['checks'] = g['checks']; r['grader_errors'] = g.get('grader_errors', [])
        json.dump(r, open(rp, 'w'), indent=2)
        tag = 'UNGRADED' if g.get('grader_errors') else ('CHANGED' if before != g['passed'] else 'same   ')
        print(f"{tag} {os.path.basename(d)}/{r['run_id']}: {before} -> {g['passed']}" + (f"  grader errors: {g['grader_errors']}" if g.get('grader_errors') else ''))
