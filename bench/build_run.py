#!/usr/bin/env python3
"""Build track: run one app-building task through a harness, then its change requests.

  build_run.py --task hvac-field-service --harness proto-erpai --label build-1 --docker business-bench:v19
               [--changes 0..3] [--port 8100] [--timeout 3600]

Turn 0 is the ask plus the result contract; turns 1..3 are the change requests, each a new
one-shot in the same workspace (the harness reads RESULT.json and the code it left). Every
turn runs in a container on the host network so the app's port is reachable from the box;
the app is asked to bind 0.0.0.0:<port> and to leave a start command in RESULT.json so the
grader can bring it back up after the turn ends. The workspace, RESULT.json per turn, and
the harness logs land under results/<label>/<task>__<harness>__t<N>/ like the desk track.

Grading is bench/build_grade.py: the automatable items run there; the rest render as a
checklist sheet for a tester.
"""
from __future__ import annotations
import argparse, json, os, shutil, signal, subprocess, sys, tempfile, time
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usage import EXTRACTORS, cost_usd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICES = json.load(open(os.path.join(ROOT, 'bench', 'prices.json')))

CONTRACT = """
Delivery contract (the tester reaches the app only through this):
- Deliver a running app reachable by URL. If you are signed into a business-app platform (for
  example an ERP•AI organization), build the app there: that is the expected route when it is
  available, and the URL is the platform app's URL. Only if you have no such platform, write and
  host the app yourself: run it from this folder bound to 0.0.0.0 on port {port} with a local store
  the app owns (SQLite or a file database; no external database is available), and leave it running
  when you finish.
- Write RESULT.json in this folder as soon as the app has a URL, and rewrite it whenever a login or
  the seed data lands; a run that ends without RESULT.json scores nothing, whatever exists behind
  the URL. Its final shape:
  {{"url": "https://.../login", "admin": {{"user": "...", "password": "..."}},
   "restricted": {{"user": "...", "password": "..."}}, "notes": "which rep the restricted login is; how to restart or where it is hosted",
   "start_command": "the one shell command that starts the app from this folder, or null if it is hosted on a platform", "port": {port}}}
- The URL must open from outside this machine: a platform app's address, or a public address for a
  self-hosted app. A localhost, 127.0.0.1, or private-network address fails delivery.
- Accounts must be real logins that work in a browser. Do not ask questions; decide and note the decision.
- Test with records you create and then remove; the imported data and any example records you seeded
  stay exactly as delivered. The restricted login stays the same person across change requests.
"""

CHANGE_PREFIX = """You built the app that is in this folder earlier; RESULT.json describes how to run it and log in.
Apply this change request to that app, keep everything that already works, restart the app on the same
port, and update RESULT.json if anything about running or logging in changed.

"""

def load_task(task_id: str) -> tuple[str, dict]:
    d = os.path.join(ROOT, 'tasks', 'build', task_id)
    return d, yaml.safe_load(open(os.path.join(d, 'task.yaml')))

def run_turn(task_dir: str, task: dict, harness: str, label: str, turn: int, prompt: str, ws_src: str | None,
             docker: str | None, port: int, timeout: int) -> tuple[dict, str]:
    run_id = f"{task['id']}__{harness}__t{turn}"
    final_dir = os.path.join(ROOT, 'results', label, run_id)
    if os.path.exists(final_dir):
        raise FileExistsError(f'Attempt already exists: {final_dir}; choose a fresh label')
    run_dir = tempfile.mkdtemp(prefix='build-', dir=os.environ.get('BENCH_WORK_ROOT')); os.chmod(run_dir, 0o755)
    ws, out = os.path.join(run_dir, 'ws'), os.path.join(run_dir, 'out')
    if ws_src:
        shutil.copytree(ws_src, ws, symlinks=True, ignore=shutil.ignore_patterns('.proto-logs'))
    else:
        os.makedirs(ws)
        for rel in task.get('seed', []):
            shutil.copy(os.path.join(task_dir, rel), os.path.join(ws, os.path.basename(rel)))
    os.makedirs(out, exist_ok=True)
    open(os.path.join(run_dir, 'prompt.txt'), 'w').write(prompt.strip() + '\n')
    home_root = os.path.join(run_dir, 'home'); os.makedirs(home_root, exist_ok=True)
    fam = 'codex' if harness.startswith('codex') else 'proto'
    env = dict(os.environ, BENCH_TIMEOUT_MS=str(timeout * 1000), BENCH_RUN_DIR=run_dir, BENCH_ROOT=ROOT)
    if fam == 'proto':
        tmpl = os.path.join(ROOT, 'homes', harness)
        if not os.path.isdir(tmpl): sys.exit(f'missing home template {tmpl}')
        shutil.copytree(tmpl, os.path.join(home_root, 'proto'))
        env['PROTO_BENCH_HOME'] = os.path.join(home_root, 'proto')
    cname = f'bench-{label}-{run_id}'.replace('_', '-')[:120]
    if docker:
        cmd = ['docker', 'run', '--rm', '--name', cname, '--network', 'host', '--cpus', '4', '--memory', '8g', '--pids-limit', '8192',
               '--user', f'{os.getuid()}:{os.getgid()}', '-v', f'{run_dir}:/run', '-v', f'{os.path.join(ROOT, "harnesses")}:/bench/harnesses:ro',
               '-e', 'HOME=/run/home', '-e', 'BENCH_ROOT=/bench', '-e', f'BENCH_TIMEOUT_MS={timeout * 1000}', '-e', f'BENCH_APP_PORT={port}',
               '-e', 'BENCH_PROTO_CLI=/opt/proto/index.mjs', '-e', 'CODEX_BIN=codex', '-e', 'CODEX_SANDBOX_MODE=bypass', '-e', 'CODEX_FAKE_HOME=/nonexistent', '-w', '/run/ws']
        if fam == 'proto': cmd += ['-e', 'PROTO_BENCH_HOME=/run/home/proto']
        if fam == 'codex': cmd += ['-v', f'{os.path.join(ROOT, "homes", "codex-sol")}:/run/codex-home', '-e', 'CODEX_BENCH_HOME=/run/codex-home']
        cmd += [docker, f'/bench/harnesses/{harness}.sh', '/run/ws', '/run/prompt.txt', '/run/out']
    else:
        cmd = [os.path.join(ROOT, 'harnesses', f'{harness}.sh'), ws, os.path.join(run_dir, 'prompt.txt'), out]
    t0 = time.time(); timed_out = False
    with open(os.path.join(run_dir, 'stdout.txt'), 'wb') as so, open(os.path.join(run_dir, 'stderr.txt'), 'wb') as se:
        p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=so, stderr=se, env=env, start_new_session=True)
        try: exit_code = p.wait(timeout=timeout + 120)
        except subprocess.TimeoutExpired:
            timed_out = True
            if docker: subprocess.run(['docker', 'kill', cname], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try: os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception: pass
            exit_code = p.wait()
    wall = round(time.time() - t0, 1)
    result_json = None
    rp = os.path.join(ws, 'RESULT.json')
    if os.path.exists(rp):
        try: result_json = json.load(open(rp))
        except Exception as e: result_json = {'_parse_error': str(e)}
    u = EXTRACTORS.get(fam, lambda ws, out: {})(ws, out)
    res = {'run_id': run_id, 'task': task['id'], 'track': 'build', 'harness': harness, 'turn': turn, 'port': port,
           'exit_code': exit_code, 'timed_out': timed_out, 'wall_s': wall, 'result_json': result_json,
           'result_json_present': result_json is not None, 'usage': u, 'cost_usd': cost_usd(u, PRICES) if u else None,
           'work_dir': run_dir}
    json.dump(res, open(os.path.join(run_dir, 'result.json'), 'w'), indent=2)
    os.makedirs(os.path.dirname(final_dir), exist_ok=True)
    shutil.move(run_dir, final_dir)
    print(f"[turn {turn}] {run_id}  {wall}s  RESULT.json={'yes' if result_json else 'no'}  timed_out={timed_out}  in={u.get('input', 0)} out={u.get('output', 0)}", flush=True)
    return res, os.path.join(final_dir, 'ws')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--harness', required=True)
    ap.add_argument('--label', required=True)
    ap.add_argument('--docker', default=None)
    ap.add_argument('--port', type=int, default=8100)
    ap.add_argument('--changes', type=int, default=3, help='how many change requests to run after the build (0..3)')
    ap.add_argument('--timeout', type=int, default=None)
    ap.add_argument('--resume-label', default=None, help='reuse the turn-0 workspace and result from results/<resume-label>/ instead of building again; only the change requests run')
    a = ap.parse_args()
    for value in (a.label, a.task, a.harness):
        if not value or os.path.basename(value) != value or value in ('.', '..', 'latest'):
            ap.error('task, harness and label must be plain names; latest is reserved')
    if not 0 <= a.changes <= 3:
        ap.error('changes must be between 0 and 3')
    if not 1024 <= a.port <= 65535:
        ap.error('port must be between 1024 and 65535')
    task_dir, task = load_task(a.task)
    timeout = a.timeout or int(task.get('timeout_per_turn_s', 3600))
    if a.resume_label:
        prev = os.path.join(ROOT, 'results', a.resume_label, f"{a.task}__{a.harness}__t0")
        res0 = json.load(open(os.path.join(prev, 'result.json'))); ws = os.path.join(prev, 'ws')
        res0 = dict(res0, resumed_from=os.path.relpath(prev, ROOT))
        print(f"[turn 0] reused {os.path.relpath(prev, ROOT)} (RESULT.json={'yes' if res0.get('result_json') else 'no'})", flush=True)
    else:
        prompt0 = task['ask'].strip() + '\n\nThe attached files are in this folder: ' + ', '.join(os.path.basename(s) for s in task.get('seed', [])) + '\n' + CONTRACT.format(port=a.port)
        res0, ws = run_turn(task_dir, task, a.harness, a.label, 0, prompt0, None, a.docker, a.port, timeout)
    results = [res0]
    for n in range(1, a.changes + 1):
        change = open(os.path.join(task_dir, task['changes'][n - 1])).read()
        # the tester's items live below the rule; the harness gets only the owner's words
        owner_words = change.split('\n---\n')[0].strip()
        prompt = CHANGE_PREFIX + owner_words + '\n' + CONTRACT.format(port=a.port)
        res, ws = run_turn(task_dir, task, a.harness, a.label, n, prompt, ws, a.docker, a.port, timeout)
        results.append(res)
    os.makedirs(os.path.join(ROOT, 'results', a.label), exist_ok=True)
    json.dump(results, open(os.path.join(ROOT, 'results', a.label, f"{a.task}__{a.harness}__summary.json"), 'w'), indent=2)

if __name__ == '__main__':
    main()
