#!/usr/bin/env python3
"""Print the tool-call sequence of a Proto run: trace_tools.py results/<label>/<run_dir> [max_chars]"""
import glob, json, os, sys
run = sys.argv[1]; width = int(sys.argv[2]) if len(sys.argv) > 2 else 170
files = sorted(glob.glob(os.path.join(run, 'ws', '.proto-logs', '*.full.jsonl')))
rows = []
for f in files:
    label = os.path.basename(f).split('-', 1)[1].replace('.full.jsonl', '')
    for line in open(f, encoding='utf-8', errors='replace'):
        try: r = json.loads(line)
        except Exception: continue
        if r.get('type') != 'RESPONSE_FULL': continue
        resp = r.get('response') or {}
        for c in resp.get('functionCalls') or []:
            a = c.get('args') or {}
            key = a.get('command') or a.get('file_path') or a.get('path') or a.get('prompt') or a.get('description') or json.dumps(a)[:width]
            rows.append((r['timestamp'], label, c.get('name'), str(key).replace('\n', ' ⏎ ')[:width]))
        if resp.get('finishReason') == 'stop' and (resp.get('text') or ''):
            rows.append((r['timestamp'], label, '<final text>', (resp.get('text') or '')[:width].replace('\n', ' ⏎ ')))
for t, label, name, key in sorted(rows):
    print(f"{t[11:19]} {label[:12]:12} {name:16} {key}")
