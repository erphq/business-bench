#!/usr/bin/env python3
"""The human's interface to the bench: attempt a task by hand, then grade it like a harness.

  attempt.py list                              # tasks with category and ask
  attempt.py start <task> [--dir ~/Desktop/x]  # copy the workspace + ASK.md to a folder (no traps, no checks)
  attempt.py grade <folder>                    # grade the folder, record results/human/<task>__human__rN

Why: a task nobody can do by hand is a task problem, not a model problem. Human attempts
give the bench a ceiling and a time baseline per task, and the same grader and report as
every harness cell. The person sees exactly what the agent saw: the files and the ask.
"""
from __future__ import annotations
import argparse, json, os, shutil, sys, time
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade import grade  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = os.path.join(ROOT, 'tasks', 'desk')

def task_dirs() -> dict[str, str]:
    return {d: os.path.join(TASKS, d) for d in sorted(os.listdir(TASKS))
            if os.path.isfile(os.path.join(TASKS, d, 'task.yaml')) and not d.startswith('_')}

def cmd_list(_):
    for tid, d in task_dirs().items():
        t = yaml.safe_load(open(os.path.join(d, 'task.yaml')))
        print(f"{tid:22} {t.get('category', ''):14} {t['ask'].strip().splitlines()[0][:90]}")

def cmd_start(a):
    d = task_dirs().get(a.task) or sys.exit(f'unknown task {a.task!r}; see attempt.py list')
    t = yaml.safe_load(open(os.path.join(d, 'task.yaml')))
    dest = os.path.abspath(os.path.expanduser(a.dir or os.path.join('~', 'Desktop', f'bench-{a.task}')))
    if os.path.exists(dest) and os.listdir(dest):
        sys.exit(f'{dest} exists and is not empty; pick another --dir')
    shutil.copytree(os.path.join(d, 'workspace'), dest, dirs_exist_ok=True)
    open(os.path.join(dest, 'ASK.md'), 'w').write(f"# The ask\n\n{t['ask'].strip()}\n\nSave your deliverables in this folder, then run:\n\n    bench/attempt.py grade {dest}\n")
    json.dump({'task': a.task, 'started_at': time.time(), 'who': a.who or os.environ.get('USER', 'human')},
              open(os.path.join(dest, '.attempt.json'), 'w'))
    print(f'ready: {dest}\nopen ASK.md, do the work with whatever tools you normally use, then grade it.')

def cmd_grade(a):
    folder = os.path.abspath(os.path.expanduser(a.folder))
    meta_p = os.path.join(folder, '.attempt.json')
    meta = json.load(open(meta_p)) if os.path.exists(meta_p) else {}
    task = meta.get('task') or a.task or sys.exit('folder has no .attempt.json; pass --task')
    d = task_dirs().get(task) or sys.exit(f'unknown task {task!r}')
    t = yaml.safe_load(open(os.path.join(d, 'task.yaml')))
    wall = round(time.time() - meta['started_at'], 1) if meta.get('started_at') else None
    g = grade(d, folder)
    label_dir = os.path.join(ROOT, 'results', 'human'); os.makedirs(label_dir, exist_ok=True)
    n = 1 + sum(1 for x in os.listdir(label_dir) if x.startswith(f'{task}__human__r'))
    run_id = f'{task}__human__r{n}'
    run_dir = os.path.join(label_dir, run_id); os.makedirs(run_dir)
    shutil.copytree(folder, os.path.join(run_dir, 'ws'), ignore=shutil.ignore_patterns('.attempt.json'))
    res = {'run_id': run_id, 'task': task, 'category': t.get('category'), 'harness': 'human', 'run': n,
           'exit_code': 0, 'timed_out': False, 'wall_s': wall, 'passed': g['passed'], 'checks': g['checks'],
           'usage': {}, 'cost_usd': None, 'work_dir': folder, 'who': meta.get('who'), 'notes': a.notes}
    json.dump(res, open(os.path.join(run_dir, 'result.json'), 'w'), indent=2)
    print(f"{'PASS' if g['passed'] else 'FAIL'}  {run_id}" + (f"  {wall/60:.1f} min" if wall else ''))
    for c in g['checks']:
        print(f"  [{'ok' if c['passed'] else 'FAIL'}] {c['name']}: {c['detail'][:140]}")
    print(f'recorded results/human/{run_id}; bench/report.py results/human folds it into the tables.')

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list').set_defaults(fn=cmd_list)
    s = sub.add_parser('start'); s.add_argument('task'); s.add_argument('--dir'); s.add_argument('--who'); s.set_defaults(fn=cmd_start)
    g = sub.add_parser('grade'); g.add_argument('folder'); g.add_argument('--task'); g.add_argument('--notes', default=''); g.set_defaults(fn=cmd_grade)
    a = ap.parse_args(); a.fn(a)

if __name__ == '__main__':
    main()
