#!/usr/bin/env python3
"""Run desk-track tasks through harness adapters and grade them.

  run.py --harness proto-glm,codex-sol --tasks all --runs 1 --parallel 4 --label first-pass
"""
from __future__ import annotations
import argparse, concurrent.futures as cf, json, os, shutil, signal, subprocess, sys, tempfile, time
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade import grade  # noqa: E402
from usage import EXTRACTORS, cost_usd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_FAMILY = {'proto-glm': 'proto', 'codex-sol': 'codex'}

def load_tasks(tasks_root: str, which: str) -> list[str]:
    ids = sorted(d for d in os.listdir(tasks_root)
                 if os.path.isfile(os.path.join(tasks_root, d, 'task.yaml')) and not d.startswith('_'))
    if which != 'all':
        want = [w.strip() for w in which.split(',') if w.strip()]
        missing = [w for w in want if w not in ids]
        if missing:
            sys.exit(f'unknown tasks: {missing}')
        ids = want
    return ids

def run_one(tasks_root: str, task_id: str, harness: str, run_idx: int, label: str, timeout_override: int | None, docker: str | None = None, cpus: str = '2', memory: str = '6g') -> dict:
    task_dir = os.path.join(tasks_root, task_id)
    task = yaml.safe_load(open(os.path.join(task_dir, 'task.yaml')))
    run_id = f'{task_id}__{harness}__r{run_idx}'
    final_dir = os.path.join(ROOT, 'results', label, run_id)
    if os.path.exists(final_dir):
        raise FileExistsError(f'Attempt already exists: {final_dir}; choose a fresh label')
    # The agent works in an opaque directory outside the bench repo: its cwd must not
    # reveal the task name, the cell, the benchmark, or the tasks/ tree with the
    # reference answers. In container mode the agent only ever sees /run/ws.
    run_dir = tempfile.mkdtemp(prefix='work-', dir=os.environ.get('BENCH_WORK_ROOT'))
    os.chmod(run_dir, 0o755)
    ws, out = os.path.join(run_dir, 'ws'), os.path.join(run_dir, 'out')
    shutil.copytree(os.path.join(task_dir, 'workspace'), ws)
    os.makedirs(out, exist_ok=True)
    prompt_file = os.path.join(run_dir, 'prompt.txt')
    open(prompt_file, 'w').write(task['ask'].strip() + '\n')
    timeout = int(timeout_override or task.get('timeout_s', 1200))
    env = dict(os.environ, BENCH_TIMEOUT_MS=str(timeout * 1000), BENCH_RUN_DIR=run_dir, BENCH_ROOT=ROOT)
    fam = HARNESS_FAMILY.get(harness, harness.split('-')[0])
    home_root = os.path.join(run_dir, 'home'); os.makedirs(home_root, exist_ok=True)
    if fam == 'proto':
        tmpl = os.path.join(ROOT, 'homes', harness)
        home = os.path.join(home_root, 'proto')
        if os.path.isdir(tmpl):
            shutil.copytree(tmpl, home)
        else:
            raise FileNotFoundError(f'missing home template {tmpl}; run bench/setup_home.py')
        env['PROTO_BENCH_HOME'] = home
    adapter = os.path.join(ROOT, 'harnesses', f'{harness}.sh')
    cname = f'bench-{label}-{run_id}'.replace('_', '-')[:120]
    if docker:
        # The container is the sandbox: workspace and per-run home are bind-mounted at /run,
        # the adapters read-only at /bench/harnesses, the process runs as the host uid.
        cmd = ['docker', 'run', '--rm', '--name', cname, '--cpus', cpus, '--memory', memory, '--pids-limit', '4096',
               '--user', f'{os.getuid()}:{os.getgid()}', '-v', f'{run_dir}:/run',
               '-v', f'{os.path.join(ROOT, "harnesses")}:/bench/harnesses:ro',
               '-e', 'HOME=/run/home', '-e', 'BENCH_ROOT=/bench', '-e', f'BENCH_TIMEOUT_MS={timeout * 1000}',
               '-e', 'BENCH_PROTO_CLI=/opt/proto/index.mjs', '-e', 'CODEX_BIN=codex', '-e', 'CODEX_SANDBOX_MODE=bypass',
               '-e', 'CODEX_FAKE_HOME=/nonexistent', '-w', '/run/ws']
        if fam == 'proto':
            cmd += ['-e', 'PROTO_BENCH_HOME=/run/home/proto']
        if fam == 'codex':
            codex_home = os.path.join(ROOT, 'homes', 'codex-sol')
            cmd += ['-v', f'{codex_home}:/run/codex-home', '-e', 'CODEX_BENCH_HOME=/run/codex-home']
        if fam == 'proto' and harness.endswith('-sub'):
            # Proto on the ChatGPT subscription reads the same Codex login, read-only: it imports the tokens into its
            # per-run home and never writes back, so the shared login is not rotated by parallel bench runs.
            codex_home = os.path.join(ROOT, 'homes', 'codex-sol')
            cmd += ['-v', f'{codex_home}:/run/codex-home:ro', '-e', 'CODEX_BENCH_HOME=/run/codex-home']
        cmd += [docker, f'/bench/harnesses/{harness}.sh', '/run/ws', '/run/prompt.txt', '/run/out']
    else:
        cmd = [adapter, ws, prompt_file, out]
    t0 = time.time(); timed_out = False; exit_code = None
    with open(os.path.join(run_dir, 'stdout.txt'), 'wb') as so, open(os.path.join(run_dir, 'stderr.txt'), 'wb') as se:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=so, stderr=se, env=env, start_new_session=True)
        try:
            exit_code = p.wait(timeout=timeout + 60)
        except subprocess.TimeoutExpired:
            timed_out = True
            if docker:
                subprocess.run(['docker', 'kill', cname], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception: pass
            exit_code = p.wait()
    wall = round(time.time() - t0, 1)
    g = grade(task_dir, ws)
    u = EXTRACTORS.get(fam, lambda ws, out: {})(ws, out)
    prices = json.load(open(os.path.join(ROOT, 'bench', 'prices.json')))
    res = {'run_id': run_id, 'task': task_id, 'category': task.get('category'), 'harness': harness, 'run': run_idx,
           'exit_code': exit_code, 'timed_out': timed_out, 'wall_s': wall, 'passed': g['passed'],
           'checks': g['checks'], 'grader_errors': g.get('grader_errors', []),
           'usage': u, 'cost_usd': cost_usd(u, prices) if u else None,
           'work_dir': run_dir}
    json.dump(res, open(os.path.join(run_dir, 'result.json'), 'w'), indent=2)
    # Keep everything (workspace, logs, per-run home) under results/ for trajectory analysis.
    os.makedirs(os.path.dirname(final_dir), exist_ok=True)
    shutil.move(run_dir, final_dir)
    flag = 'PASS' if res['passed'] else ('TIMEOUT' if timed_out else ('UNGRADED' if g.get('grader_errors') else 'FAIL'))
    failed = [c['name'] for c in g['checks'] if not c['passed']]
    print(f"[{flag}] {run_id}  {wall}s  in={u.get('input',0)} out={u.get('output',0)}" + (f"  failed={failed}" if failed else ''), flush=True)
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tasks-root', default=os.path.join(ROOT, 'tasks', 'desk'))
    ap.add_argument('--tasks', default='all')
    ap.add_argument('--harness', default='proto-glm')
    ap.add_argument('--runs', type=int, default=1)
    ap.add_argument('--parallel', type=int, default=2)
    ap.add_argument('--timeout', type=int, default=None)
    ap.add_argument('--label', default=time.strftime('%Y%m%d-%H%M%S'))
    ap.add_argument('--docker', default=None, help='run adapters inside this image (e.g. business-bench:v0)')
    ap.add_argument('--cpus', default='2')
    ap.add_argument('--memory', default='6g')
    a = ap.parse_args()
    if not a.label or os.path.basename(a.label) != a.label or a.label in ('.', '..', 'latest'):
        ap.error('label must be a directory name other than latest, . or ..')
    if a.runs < 1 or a.parallel < 1:
        ap.error('runs and parallel must be positive')
    ids = load_tasks(a.tasks_root, a.tasks)
    harnesses = [h.strip() for h in a.harness.split(',') if h.strip()]
    if not harnesses or len(set(harnesses)) != len(harnesses):
        ap.error('provide distinct harness names')
    for h in harnesses:
        if os.path.basename(h) != h or not os.path.isfile(os.path.join(ROOT, 'harnesses', h + '.sh')):
            ap.error(f'unknown harness: {h}')
    os.makedirs(os.path.join(ROOT, 'results', a.label), exist_ok=False)
    jobs = [(t, h, i) for t in ids for h in harnesses for i in range(1, a.runs + 1)]
    print(f'{len(jobs)} runs -> results/{a.label}  (tasks={len(ids)} harnesses={harnesses} runs={a.runs} parallel={a.parallel})', flush=True)
    results = []
    with cf.ThreadPoolExecutor(max_workers=a.parallel) as ex:
        futs = [ex.submit(run_one, a.tasks_root, t, h, i, a.label, a.timeout, a.docker, a.cpus, a.memory) for t, h, i in jobs]
        for f in cf.as_completed(futs):
            try: results.append(f.result())
            except Exception as e: print(f'[ERROR] {type(e).__name__}: {e}', flush=True)
    outp = os.path.join(ROOT, 'results', a.label, 'summary.json')
    json.dump(results, open(outp, 'w'), indent=2)
    subprocess.run([sys.executable, os.path.join(ROOT, 'bench', 'report.py'), os.path.join(ROOT, 'results', a.label)])
    if len(results) != len(jobs):
        sys.exit('incomplete matrix: one or more attempts could not produce a result')

if __name__ == '__main__':
    main()
