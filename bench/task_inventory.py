#!/usr/bin/env python3
"""One line per authored desk task: id, category, title, the business named in the workspace notes, files.
Authors run this before choosing a business or a data shape so batches do not collide.

    .venv/bin/python bench/task_inventory.py [--category reports]
"""
import glob, os, re, sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cat = sys.argv[sys.argv.index('--category') + 1] if '--category' in sys.argv else None
for p in sorted(glob.glob(os.path.join(ROOT, 'tasks', 'desk', '*', 'task.yaml'))):
    tid = os.path.basename(os.path.dirname(p))
    if tid.startswith('_validate_'): continue
    try: y = yaml.safe_load(open(p)) or {}
    except Exception: continue
    if cat and y.get('category') != cat: continue
    ws = os.path.join(os.path.dirname(p), 'workspace')
    files = sorted(os.path.relpath(f, ws) for f in glob.glob(os.path.join(ws, '**', '*'), recursive=True) if os.path.isfile(f))
    business = ''
    for f in files:
        if f.endswith(('.txt', '.md')):
            text = open(os.path.join(ws, f), encoding='utf-8', errors='replace').read()
            m = re.search(r'@([a-z0-9.-]+\.[a-z]{2,})', text) or re.search(r'\b([A-Z][A-Za-z&\']+(?: [A-Z][A-Za-z&\']+){1,3} (?:Co\.|Inc\.|LLC|Ltd|Studio|Clinic|Bakery|Brewing|Roasters|Marina|Nursery|Seafood|Catering|Optical|Tea Co\.))', text)
            if m: business = m.group(1); break
    print(f"{tid:32} {str(y.get('category')):12} {business[:30]:30} {str(y.get('title'))[:60]:60} {', '.join(files)[:120]}")
