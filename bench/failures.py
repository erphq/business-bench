#!/usr/bin/env python3
"""List failing checks per run:  failures.py results/<label> [...]"""
import glob, json, os, sys
for d in sys.argv[1:]:
    for rp in sorted(glob.glob(os.path.join(d, '*', 'result.json'))):
        r = json.load(open(rp))
        if r['passed']:
            continue
        print(f"{os.path.basename(os.path.dirname(rp))}  {r['wall_s']/60:.1f} min")
        for c in r['checks']:
            if not c['passed']:
                print(f"    {c['name'][:46]} | {c['detail'][:170]}")
