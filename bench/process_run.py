#!/usr/bin/env python3
"""Run process-track tasks: one ERP per attempt, one agent session per turn, graded on the final state.

  process_run.py --task procure-to-pay-week --harness oracle --label dev-oracle
  process_run.py --task procure-to-pay-week --harness proto-deepseek --runs 5 --parallel 2 --label pilot-proto
  process_run.py --task payment-run --harness oracle --faults lost-writes --label dev-faults
  process_run.py --task payment-run --harness oracle --faults 'lost_response:POST /payment-runs@1' --label dev-f1

--faults declares transport faults on the agent API (erp/bberp/faults.py): a spec, or the name of a profile in the
task's `fault_profiles`. The condition is part of the attempt's identity (run id suffix, `condition` and `cell` in
result.json, condition.json in the label): a label holds one condition, and faulted attempts are never pooled with
clean ones. The reference is always built without faults.

Harnesses are the desk track's shell adapters (harnesses/<name>.sh WS PROMPT OUT), called once per turn with
ERP_URL, ERP_TOKEN and the `erp` command on PATH, or the task's own policies: `oracle`, `null`, `neg:<name>`, which
drive the same HTTP API with the same token.

Scenarios are generated once per seed into .cache/process/<task>/seed-<n>/ (gen.py), and the reference is the
oracle's projections, checked against the task's planted truth before it is used. Local runs start bb-erp as a
local process: not an isolation boundary, for development only.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

from process_grade import grade_process, materialize  # noqa: E402
from bberp.faults import FaultPlan  # noqa: E402
from procgen.episode import ERP_DIR, Api, Server, free_port, load_meta, preamble  # noqa: E402
from process_rules import fault_metrics  # noqa: E402
from usage import EXTRACTORS, cost_usd, merge  # noqa: E402

TASKS = os.path.join(ROOT, 'tasks', 'process')
CACHE = os.path.join(ROOT, '.cache', 'process')


def task_dir(task: str) -> str:
    d = os.path.join(TASKS, task)
    if not os.path.isfile(os.path.join(d, 'task.yaml')):
        sys.exit(f'unknown process task {task!r}')
    return d


_POLICY_LOCK = threading.Lock()


def load_policies(task: str) -> dict:
    path = os.path.join(task_dir(task), 'oracle.py')
    name = f'oracle_{task.replace("-", "_")}'
    with _POLICY_LOCK:
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod           # dataclasses resolve annotations through sys.modules
            try:
                spec.loader.exec_module(mod)
            except BaseException:
                del sys.modules[name]
                raise
        return {'null': lambda *a, **k: None, **sys.modules[name].POLICIES}


# ------------------------------------------------------------------------------------------- scenario and reference

def scenario_dir(task: str, seed: int) -> str:
    return os.path.join(CACHE, task, f'seed-{seed}')


def ensure_scenario(task: str, seed: int, rebuild: bool = False) -> str:
    out = scenario_dir(task, seed)
    if rebuild:
        shutil.rmtree(out, ignore_errors=True)
    if not os.path.exists(os.path.join(out, 'meta.json')):
        os.makedirs(out, exist_ok=True)
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(ROOT, 'erp'), os.path.join(ROOT, 'tasks', 'lib')]))
        subprocess.run([sys.executable, 'gen.py', '--seed', str(seed), '--out', out], cwd=task_dir(task), env=env,
                       check=True)
    ref = os.path.join(out, 'reference')
    if not os.path.exists(os.path.join(ref, '.complete')):
        with tempfile.TemporaryDirectory(prefix='oracle-') as tmp:
            res = run_attempt(task, 'oracle', seed, 0, tmp, out, reference_pass=True)
            if res.get('error'):
                raise RuntimeError(f'oracle failed while building the reference: {res["error"]}')
            os.makedirs(ref, exist_ok=True)
            meta = load_meta(out)
            materialize(task_dir(task), os.path.join(res['work_dir'], 'final.db'),
                        {'start': meta['start'], 'agent': meta['agent_user']}, ref)
        check_truth(task, out)
        open(os.path.join(ref, '.complete'), 'w').write('ok\n')
    return out


def check_truth(task: str, scenario: str) -> None:
    """Every row the task says must be in the reference is there: the oracle reproduces the planted truth."""
    import csv
    truth = json.load(open(os.path.join(scenario, 'truth.json'), encoding='utf-8'))
    problems = []
    def rows(proj):
        return list(csv.DictReader(open(os.path.join(scenario, 'reference', f'{proj}.csv'), encoding='utf-8')))

    def matches(h, want):
        return all(str(h.get(k, '')) == str(v) for k, v in want.items())
    for proj, wanted in truth.get('expect', {}).items():
        have = rows(proj)
        for want in wanted:
            if not any(matches(h, want) for h in have):
                problems.append(f'{proj}: no row {want}')
    for proj, unwanted in truth.get('absent', {}).items():
        have = rows(proj)
        for bad in unwanted:
            if any(matches(h, bad) for h in have):
                problems.append(f'{proj}: has a row it must not have {bad}')
    if problems:
        raise RuntimeError('reference does not contain the planted truth:\n  ' + '\n  '.join(problems))


# ------------------------------------------------------------------------------------------- the fault condition

def resolve_faults(task: str, spec: str | None) -> dict | None:
    """The fault condition for an attempt: None (the default, clean condition) or {name, spec} with the spec in
    canonical form. `spec` is a fault spec or the name of a profile in the task's `fault_profiles`."""
    if spec is None or not spec.strip() or spec.strip().lower() == 'none':
        return None
    spec = spec.strip()
    profiles = (yaml.safe_load(open(os.path.join(task_dir(task), 'task.yaml'), encoding='utf-8'))
                .get('fault_profiles') or {})
    name = None
    if spec in profiles:
        name, spec = spec, profiles[spec]['faults']
    plan = FaultPlan.parse(spec)
    if plan is None:
        return None
    canonical = plan.canonical()
    import hashlib
    return {'name': name or 'faults-' + hashlib.sha256(canonical.encode()).hexdigest()[:8], 'spec': canonical}


class FaultServer(Server):
    """procgen.episode.Server with a declared fault plan on the agent API. The fault log is written beside the
    attempt's other runner files, outside the agent's folder and the ERP database."""

    def __init__(self, db: str, world: str, control_token: str, log: str, faults: str, fault_log: str):
        self.port, self.cport, self.token = free_port(), free_port(), control_token
        env = dict(os.environ, PYTHONPATH=ERP_DIR)
        self.proc = subprocess.Popen(
            [sys.executable, '-m', 'bberp.server', '--db', db, '--world', world, '--port', str(self.port),
             '--control-port', str(self.cport), '--control-token', control_token, '--faults', faults,
             '--fault-log', fault_log],
            stdout=open(log, 'ab'), stderr=subprocess.STDOUT, env=env, cwd=ERP_DIR, start_new_session=True)
        for _ in range(200):
            try:
                self.control('GET', '/control/health')
                return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError('bb-erp did not start; see ' + log)


# ------------------------------------------------------------------------------------------- one attempt

def _erp_bin(dirpath: str) -> str:
    os.makedirs(dirpath, exist_ok=True)
    dst = os.path.join(dirpath, 'erp')
    src = open(os.path.join(ROOT, 'erp', 'bberp', 'cli.py'), encoding='utf-8').read()
    if not src.startswith('#!'):
        src = '#!/usr/bin/env python3\n' + src
    open(dst, 'w', encoding='utf-8').write(src.replace('#!/usr/bin/env python3', f'#!{sys.executable}', 1))
    os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return dirpath


CREDENTIAL_FILES = ('auth.json', 'codex-oauth.json')
SECRET_FIELD = re.compile(r'(api[_-]?key|token|secret|password)$', re.I)


def _redact(obj):
    if isinstance(obj, dict):
        return {k: '[redacted]' if isinstance(v, str) and v and SECRET_FIELD.search(k) else _redact(v)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def _scrub(home: str) -> None:
    """Remove credentials from a per-turn harness home before it is kept with the results. Symlinks go (a template's
    login is a symlink to the operator's, so this removes the link and never its target), a harness's own imported
    login is deleted, and provider keys in JSON settings, such as an OpenRouter key in .proto/config.json, are
    redacted in place."""
    for dirpath, _dirs, files in os.walk(home):
        for f in files:
            path = os.path.join(dirpath, f)
            if os.path.islink(path) or f in CREDENTIAL_FILES:
                os.unlink(path)
            elif f.endswith('.json'):
                try:
                    data = json.load(open(path, encoding='utf-8'))
                except (OSError, ValueError, UnicodeDecodeError):
                    continue
                clean = _redact(data)
                if clean != data:
                    json.dump(clean, open(path, 'w', encoding='utf-8'), indent=2)


def _run_shell(harness: str, ws: str, prompt_file: str, out: str, env: dict, timeout: int) -> tuple:
    adapter = os.path.join(ROOT, 'harnesses', f'{harness}.sh')
    t0 = time.time()
    with open(os.path.join(out, 'stdout.txt'), 'wb') as so, open(os.path.join(out, 'stderr.txt'), 'wb') as se:
        p = subprocess.Popen([adapter, ws, prompt_file, out], stdin=subprocess.DEVNULL, stdout=so, stderr=se, env=env,
                             start_new_session=True, cwd=ws)
        try:
            code, timed_out = p.wait(timeout=timeout + 60), False
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:
                pass
            code = p.wait()
    return code, timed_out, round(time.time() - t0, 1)


def run_attempt(task: str, harness: str, seed: int, run_idx: int, results_root: str, scenario: str | None = None,
                reference_pass: bool = False, timeout_override: int | None = None, faults: str | None = None) -> dict:
    tdir = task_dir(task)
    condition = resolve_faults(task, faults)
    if condition and reference_pass:
        raise ValueError('the reference is built without faults')
    scenario = scenario or ensure_scenario(task, seed)
    meta = load_meta(scenario)
    run_id = f'{task}__{harness.replace(":", "-")}__s{seed}__r{run_idx}' + \
        (f'__{condition["name"]}' if condition else '')
    run_dir = os.path.join(results_root, run_id)
    if os.path.exists(run_dir):
        raise FileExistsError(f'attempt already exists: {run_dir}; choose a fresh label')
    os.makedirs(run_dir)
    # The agent's working folder and the ERP's files live in separate temporary directories.
    ws = tempfile.mkdtemp(prefix='ws-')
    erp_dir = tempfile.mkdtemp(prefix='erp-')
    shutil.copytree(os.path.join(scenario, 'handbook'), os.path.join(ws, 'handbook'))
    db = os.path.join(erp_dir, 'company.db')
    shutil.copyfile(os.path.join(scenario, 'scenario.db'), db)
    world = os.path.join(erp_dir, 'world.json')
    shutil.copyfile(os.path.join(scenario, 'world.json'), world)
    ctl = os.urandom(16).hex()
    fault_log = os.path.join(run_dir, 'faults.jsonl') if condition else None
    server = FaultServer(db, world, ctl, os.path.join(run_dir, 'erp.log'), condition['spec'], fault_log) \
        if condition else Server(db, world, ctl, os.path.join(run_dir, 'erp.log'))
    bin_dir = _erp_bin(os.path.join(erp_dir, 'bin'))
    policies = load_policies(task) if not os.path.isfile(os.path.join(ROOT, 'harnesses', f'{harness}.sh')) else None
    if policies is not None and harness not in policies:
        server.stop()
        raise ValueError(f'unknown harness or policy {harness!r}; policies: {sorted(policies)}')
    fam = 'proto' if harness.startswith('proto') else harness.split('-')[0]
    turns, error, t_start = [], None, time.time()
    try:
        for turn in meta['turns']:
            n = turn['n']
            server.advance(turn['date'])
            tdir_n = os.path.join(run_dir, 'turns', str(n))
            out = os.path.join(tdir_n, 'out')
            os.makedirs(out)
            prompt = preamble(meta, turn)
            prompt_file = os.path.join(tdir_n, 'prompt.txt')
            open(prompt_file, 'w', encoding='utf-8').write(prompt)
            budget = int(timeout_override or turn.get('budget_s', 1200))
            if policies is None:
                env = dict(os.environ, ERP_URL=server.url, ERP_TOKEN=meta['token'], BENCH_TIMEOUT_MS=str(budget * 1000),
                           BENCH_RUN_DIR=run_dir, BENCH_ROOT=ROOT, BENCH_TURN=str(n),
                           PATH=bin_dir + os.pathsep + os.environ.get('PATH', ''))
                # A fresh harness home every turn: nothing carries over but the ERP and the folder. A login in the
                # template is a symlink to the operator's and stays one (symlinks=True), so no credential is copied.
                tmpl, home = os.path.join(ROOT, 'homes', harness), os.path.join(tdir_n, 'home')
                if os.path.isdir(tmpl):
                    shutil.copytree(tmpl, home, symlinks=True)
                    env['CODEX_BENCH_HOME' if fam == 'codex' else 'PROTO_BENCH_HOME'] = home
                if fam == 'proto':
                    # Request logs carry token usage; they go beside the turn's output, outside the agent's folder.
                    env['PROTO_PROVIDER_TRACE_DIR'] = os.path.join(out, 'proto-logs')
                    if harness.endswith('-sub'):   # the ChatGPT subscription: Proto imports the Codex login, read-only
                        env.setdefault('CODEX_BENCH_HOME', os.path.join(ROOT, 'homes', 'codex-sol'))
                try:
                    code, timed_out, wall = _run_shell(harness, ws, prompt_file, out, env, budget)
                finally:
                    _scrub(home)
                if code in (126, 127) and wall < 5:   # the harness binary is missing or not executable
                    error = f'turn {n}: the harness did not start (exit {code}); see turns/{n}/out/stderr.txt'
                    turns.append({'n': n, 'date': turn['date'], 'exit_code': code, 'timed_out': False, 'wall_s': wall})
                    break
            else:
                t0, code, timed_out = time.time(), 0, False
                try:
                    policies[harness](n, Api(server.url, meta['token']), ws, meta)
                except Exception:
                    code = 1
                    open(os.path.join(out, 'traceback.txt'), 'w').write(traceback.format_exc())
                    if harness == 'oracle':
                        error = f'turn {n}: ' + traceback.format_exc(limit=3)
                wall = round(time.time() - t0, 1)
            turns.append({'n': n, 'date': turn['date'], 'exit_code': code, 'timed_out': timed_out, 'wall_s': wall})
        server.advance(meta['grading_date'])
    finally:
        server.stop()
    final_db = os.path.join(run_dir, 'final.db')
    shutil.copyfile(db, final_db)
    shutil.copytree(ws, os.path.join(run_dir, 'ws'), ignore=shutil.ignore_patterns('handbook'))
    shutil.rmtree(erp_dir, ignore_errors=True)
    usage = {}
    if fam in EXTRACTORS:
        outs = [os.path.join(run_dir, 'turns', str(t['n']), 'out') for t in turns]
        usage = merge([EXTRACTORS[fam](ws if i == 0 else None, o) for i, o in enumerate(outs)])
    shutil.rmtree(ws, ignore_errors=True)
    params = {'start': meta['start'], 'agent': meta['agent_user'], 'token_id': meta['token_id']}
    if reference_pass:
        g = {'passed': None, 'breach': None, 'checks': [], 'grader_errors': []}
    else:
        g = grade_process(tdir, final_db, os.path.join(scenario, 'scenario.db'), os.path.join(run_dir, 'ws'),
                          os.path.join(scenario, 'reference'), run_dir, params)
    prices = json.load(open(os.path.join(HERE, 'prices.json')))
    res = {'run_id': run_id, 'task': task, 'track': 'process', 'harness': harness, 'seed': seed, 'run': run_idx,
           'condition': {'faults': condition}, 'cell': harness + (f'+{condition["name"]}' if condition else ''),
           'passed': g['passed'], 'breach': g['breach'], 'checks': g['checks'], 'grader_errors': g['grader_errors'],
           'turns': turns, 'wall_s': round(time.time() - t_start, 1), 'usage': usage,
           'cost_usd': cost_usd(usage, prices) if usage.get('by_model') else None, 'work_dir': run_dir, 'error': error}
    if condition:
        res['fault_metrics'] = fault_metrics(final_db, fault_log, params)
    json.dump(res, open(os.path.join(run_dir, 'result.json'), 'w'), indent=2)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--task', required=True, help='task id, comma-separated ids, or all')
    ap.add_argument('--harness', required=True, help='adapter name(s) or oracle | null | neg:<name>, comma-separated')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--runs', type=int, default=1)
    ap.add_argument('--parallel', type=int, default=1)
    ap.add_argument('--label', required=True)
    ap.add_argument('--timeout', type=int, default=None, help='override every turn budget (seconds)')
    ap.add_argument('--rebuild', action='store_true', help='regenerate the scenario and reference')
    ap.add_argument('--faults', help="declared transport faults: a spec or a task's fault profile name (see above)")
    a = ap.parse_args()
    if os.path.basename(a.label) != a.label or a.label in ('', '.', '..', 'latest'):
        ap.error('label must be a directory name other than latest')
    tasks = sorted(d for d in os.listdir(TASKS) if os.path.isfile(os.path.join(TASKS, d, 'task.yaml'))) \
        if a.task == 'all' else [t.strip() for t in a.task.split(',')]
    for t in tasks:
        ensure_scenario(t, a.seed, a.rebuild)
    try:
        conditions = {t: resolve_faults(t, a.faults) for t in tasks}
    except ValueError as e:
        ap.error(str(e))
    root = os.path.join(ROOT, 'results', a.label)
    os.makedirs(root, exist_ok=False)
    # One condition per label: results are never pooled across conditions.
    json.dump({'faults': conditions if a.faults else None}, open(os.path.join(root, 'condition.json'), 'w'), indent=2)
    jobs = [(t, h.strip(), r) for t in tasks for h in a.harness.split(',') for r in range(1, a.runs + 1)]
    print(f'{len(jobs)} process attempts -> results/{a.label}', flush=True)
    results = []
    with cf.ThreadPoolExecutor(max_workers=a.parallel) as ex:
        futs = {ex.submit(run_attempt, t, h, a.seed, r, root, None, False, a.timeout, a.faults): (t, h, r)
                for t, h, r in jobs}
        for f in cf.as_completed(futs):
            try:
                res = f.result()
            except Exception as e:
                print(f'[ERROR] {futs[f]}: {type(e).__name__}: {e}', flush=True)
                continue
            results.append(res)
            flag = 'ERROR' if res['error'] else 'PASS' if res['passed'] else ('BREACH' if res['breach'] else 'FAIL')
            failed = [c['name'] for c in res['checks'] if not c['passed']]
            fm = res.get('fault_metrics')
            extra = f'  faults={fm["faults_injected"]} retried={fm["faulted_requests_retried"]} ' \
                    f'duplicates={fm["duplicates"]}' if fm else ''
            print(f'[{flag}] {res["run_id"]}  {res["wall_s"]}s' + (f'  failed={failed}' if failed else '') + extra,
                  flush=True)
    json.dump(results, open(os.path.join(root, 'summary.json'), 'w'), indent=2)
    if len(results) != len(jobs):
        sys.exit('incomplete matrix: one or more attempts could not produce a result')


if __name__ == '__main__':
    main()
