#!/usr/bin/env python3
"""Validate build-track tasks.

    .venv/bin/python bench/validate_build.py [task_id ...]

Per task: gen.py regenerates seed/ and reference/counts.json byte-identically in a scratch copy (never in
place); task.yaml loads and every referenced file exists; the checklist parses with build_grade's pattern
into 24 or more consecutive items starting at 1 (HVAC: 31); (CORE) marks equal core_items; the first 14
items carry the enterprise baseline tags in order (tasks authored before the baseline carry them as 21-31);
no <PLACEHOLDER> remains; each of the three change files adds exactly three items continuing the
numbering; and every multi-digit number the checklist and change files quote appears somewhere in
counts.json or in the seed files (a quoted figure a tester cannot derive is a task defect).
"""
from __future__ import annotations
import hashlib, json, os, re, shutil, subprocess, sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, 'tasks', 'build')
ITEM = re.compile(r'^(\d+)\. (\(CORE\) )?\[(\w+)\] ', re.M)
BASELINE_TAGS = ['Delivery', 'Delivery', 'Sharing', 'Sharing', 'Permission', 'Permission', 'API', 'Dashboard',
                 'Dashboard', 'Exact', 'Exact', 'Audit', 'Rule', 'Persistence']
PRE_BASELINE = {'hvac-field-service'}

def tree_hash(d: str) -> str:
    h = hashlib.sha256()
    for base, _, files in sorted(os.walk(d)):
        for f in sorted(files):
            p = os.path.join(base, f); h.update(os.path.relpath(p, d).encode()); h.update(open(p, 'rb').read())
    return h.hexdigest()

def numbers_in(text: str) -> set[str]:
    out = set()
    for m in re.finditer(r'(?<![\w.-])\$?(\d{1,3}(?:,\d{3})+|\d{2,})(?:\.(\d+))?(?![\w-])', text):
        whole = m.group(1).replace(',', '')
        out.add(whole + ('.' + m.group(2) if m.group(2) else ''))
    return out

def haystack(td: str) -> str:
    parts = [open(os.path.join(td, 'reference', 'counts.json')).read()]
    for base, _, files in os.walk(os.path.join(td, 'seed')):
        for f in files: parts.append(open(os.path.join(base, f), encoding='utf-8', errors='replace').read())
    return '\n'.join(parts).replace(',', '')

def validate(tid: str) -> list[str]:
    td = os.path.join(BUILD, tid); errs = []
    try: task = yaml.safe_load(open(os.path.join(td, 'task.yaml')))
    except Exception as e: return [f'task.yaml: {e}']
    for key in ('id', 'ask', 'seed', 'checklist', 'reference', 'core_items', 'changes'):
        if key not in task: errs.append(f'task.yaml missing {key}')
    for rel in list(task.get('seed') or []) + [task.get('checklist'), task.get('reference')] + list(task.get('changes') or []):
        if rel and not os.path.exists(os.path.join(td, str(rel).split('#')[0].strip())): errs.append(f'missing file {rel}')
    if errs: return errs
    # determinism, in a scratch copy
    scratch = os.path.join(BUILD, f'_validate_{tid}'); hashes = []
    for _ in range(2):
        shutil.rmtree(scratch, ignore_errors=True); shutil.copytree(td, scratch, ignore=shutil.ignore_patterns('__pycache__'))
        r = subprocess.run([sys.executable, os.path.join(scratch, 'gen.py')], capture_output=True, text=True, cwd=scratch)
        if r.returncode != 0: errs.append(f'gen.py failed: {r.stderr.strip()[-200:]}'); break
        hashes.append((tree_hash(os.path.join(scratch, 'seed')), tree_hash(os.path.join(scratch, 'reference'))))
    committed = (tree_hash(os.path.join(td, 'seed')), tree_hash(os.path.join(td, 'reference')))
    shutil.rmtree(scratch, ignore_errors=True)
    if len(hashes) == 2 and hashes[0] != hashes[1]: errs.append('gen.py is not deterministic')
    if hashes and hashes[0] != committed: errs.append('committed seed/ or counts.json differ from gen.py output')
    checklist = open(os.path.join(td, task['checklist'])).read()
    items = [(int(m.group(1)), bool(m.group(2)), m.group(3)) for m in ITEM.finditer(checklist)]
    nums = [n for n, _, _ in items]
    if nums != list(range(1, len(nums) + 1)): errs.append(f'checklist items not consecutive from 1: {nums}')
    minimum = 31 if tid in PRE_BASELINE else 24
    if len(items) < minimum: errs.append(f'checklist has {len(items)} items, expected at least {minimum}')
    core = sorted(n for n, c, _ in items if c)
    if core != sorted(task['core_items']): errs.append(f'(CORE) marks {core} != core_items {sorted(task["core_items"])}')
    tags = [t for _, _, t in items]
    base = tags[20:31] if tid in PRE_BASELINE else tags[:14]
    want = BASELINE_TAGS[2:13] if tid in PRE_BASELINE else BASELINE_TAGS
    if base != want: errs.append(f'baseline tags {base} != {want}')
    if re.search(r'<[A-Z][A-Z0-9_]+>', checklist): errs.append('unfilled <PLACEHOLDER> in checklist')
    nxt = len(items) + 1; change_text = ''
    for rel in task['changes']:
        txt = open(os.path.join(td, rel)).read(); change_text += txt
        cn = [int(m.group(1)) for m in ITEM.finditer(txt)]
        if cn != list(range(nxt, nxt + 3)): errs.append(f'{rel}: items {cn}, expected {list(range(nxt, nxt + 3))}')
        nxt += 3
        if re.search(r'<[A-Z][A-Z0-9_]+>', txt): errs.append(f'unfilled placeholder in {rel}')
    hay = haystack(td)
    text = checklist + change_text
    # procedure, not data: loopback and private addresses, screen sizes, rounding examples
    text = re.sub(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', ' ', text)
    text = re.sub(r'\b\d{3,4}\s*[x×]\s*\d{3,4}\b', ' ', text)
    text = re.sub(r'\([^)]*\bpasses for\b[^)]*\)', ' ', text)
    quoted = numbers_in(text)
    # a worked figure is derivable when it is the sum, difference, or product of two figures on its line
    derived = set()
    for line in text.splitlines():
        vals = [float(x) for x in numbers_in(line)] + [float(m) for m in re.findall(r'(?<![\w.])(\d+(?:\.\d+)?)(?![\w.])', line)]
        for a in vals:
            for b in vals:
                for r in (a + b, a - b, a * b):
                    derived.add(f'{r:.2f}'); derived.add(f'{r:.1f}'); derived.add(str(int(r)) if float(r).is_integer() else '')
    # numbers that are procedure, not data: item references, years, ports, HTTP codes
    ignore = {str(n) for n in range(1, 60)} | {'401', '403', '404', '2024', '2025', '2026', '2027', '2028', '100'}
    def _ok(q):
        if q in hay or q.rstrip('0').rstrip('.') in hay: return True
        try: return f'{float(q):.2f}' in derived or f'{float(q):.1f}' in derived
        except ValueError: return False
    missing = sorted(q for q in quoted - ignore if not _ok(q))
    if missing: errs.append(f'quoted figures not derivable from counts.json or seed files: {missing[:12]}')
    return errs

def main():
    ids = [a for a in sys.argv[1:] if not a.startswith('--')] or sorted(
        d for d in os.listdir(BUILD) if not d.startswith('_') and os.path.isfile(os.path.join(BUILD, d, 'task.yaml')))
    bad = 0
    for tid in ids:
        errs = validate(tid)
        print(f"{'ok ' if not errs else 'BAD'} {tid}")
        for e in errs: print(f'      {e}')
        bad += bool(errs)
    sys.exit(1 if bad else 0)

if __name__ == '__main__':
    main()
