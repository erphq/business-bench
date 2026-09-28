#!/usr/bin/env python3
"""Failure triage: rank failed desk attempts (and the failed checks inside them) by how likely the failure is a
GRADER error rather than an agent error, so a human audit starts with the most suspicious ones.

    triage.py metamorphic --view snapshot:87f624e|frozen|current [--tasks a,b] --out PATH
    triage.py fit   [--ledger results/latest/attempts.jsonl] [--snapshot 87f624e] [--out docs/triage]
    triage.py rank  --ledger results/latest/attempts.jsonl [--model docs/triage/model.json] [--out DIR]
    triage.py rank  --run results/<label> [--tasks-root tasks/desk] [--model ...] [--out DIR] [--no-artifacts]

Two layers (docs/triage.md has the method, the evaluation and the limits):

1. Ledger-only model. Labels come from the scorer revision: a raw-scorer failure the frozen scorer passes is a
   known grader error. Features are computed in the view of the scorer that produced the failure, never from
   the scorer that labels it:
     training   raw verdicts per check from the pre-freeze ledger snapshot in git (`--snapshot`, the four-arm
                2026-09-17 release, whose codex-sol attempts are byte-identical sources to the published ones),
                task specs and grade.py from that same commit;
     ranking    frozen verdicts from the published ledger, task specs and scorer from scoring/frozen-v7 (or,
                for `--run`, result.json verdicts, the current tasks and bench/grade.py).
   The model is a small L2-regularised logistic regression over one row per failed required check; an
   attempt's score is the product of its failed checks' scores (the chance that every failure is a grader
   error, i.e. that the verdict itself is wrong). Evaluated with leave-one-task-out cross-validation.

2. Artifact layer (`rank --run`, only where raw workspaces exist locally): every failed check is re-run alone on
   a temporary copy of the agent's own files under the invariant transforms of bench/metamorphic.py and under
   "formatted differently" probes. A transform that flips the check to pass is strong evidence of a grader
   false negative; a probe that flips it is weaker evidence (probes relax the contract). The run directory is
   never written.

Offline, opt-in tooling: nothing in the runner or the graders imports this module; no network, no LLM.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import fnmatch
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Iterable

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

DEFAULT_SNAPSHOT = '87f624e'          # pre-freeze four-arm release: raw per-check verdicts
DEFAULT_LEDGER = os.path.join(ROOT, 'results', 'latest', 'attempts.jsonl')
DEFAULT_OUT = os.path.join(ROOT, 'docs', 'triage')
FROZEN = os.path.join(ROOT, 'scoring', 'frozen-v7')
TRAIN_ARM = 'codex-sol'               # the only arm whose raw per-check verdicts are public
LAMBDA = 1.0                          # L2 strength, fixed a priori (no tuning on the evaluation folds)
BOOT = 2000
SEED = 20260927

# ======================================================================================= small numerics


def fit_logreg(X: list[list[float]], y: list[int], lam: float = LAMBDA, iters: int = 50) -> dict:
    """L2-regularised logistic regression by Newton-Raphson (IRLS) on standardised features.
    The intercept is not penalised. Returns {mean, scale, w, b}."""
    import numpy as np
    A = np.asarray(X, dtype=float)
    t = np.asarray(y, dtype=float)
    n, d = A.shape
    mu = A.mean(axis=0) if n else np.zeros(d)
    sd = A.std(axis=0) if n else np.ones(d)
    sd[sd < 1e-9] = 1.0
    Z = np.hstack([np.ones((n, 1)), (A - mu) / sd])
    w = np.zeros(d + 1)
    P = np.eye(d + 1) * lam
    P[0, 0] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - t) + P @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + P + np.eye(d + 1) * 1e-9
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return {'mean': mu.tolist(), 'scale': sd.tolist(), 'b': float(w[0]), 'w': w[1:].tolist()}


def predict(model: dict, X: list[list[float]]) -> list[float]:
    out = []
    for x in X:
        z = model['b'] + sum(wi * (xi - m) / s for wi, xi, m, s in zip(model['w'], x, model['mean'], model['scale']))
        out.append(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z)))))
    return out


def contributions(model: dict, x: list[float]) -> list[float]:
    return [wi * (xi - m) / s for wi, xi, m, s in zip(model['w'], x, model['mean'], model['scale'])]


def model_x(model: dict, x: list[float]) -> list[float]:
    """The columns of a full FEATURES row that `model` was fitted on (all when it records none)."""
    cols = model.get('cols')
    return x if cols is None else [x[i] for i in cols]


def model_predict(model: dict, X: list[list[float]]) -> list[float]:
    return predict(model, [model_x(model, x) for x in X])


def auc(scores: list[float], y: list[int]) -> float | None:
    """Mann-Whitney AUC with ties counted half. None when one class is empty."""
    pos = [s for s, t in zip(scores, y) if t]
    neg = [s for s, t in zip(scores, y) if not t]
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    rp = sum(r for r, t in zip(ranks, y) if t)
    return (rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def precision_at(scores: list[float], y: list[int], k: int) -> float:
    """Expected precision of the top k, with ties at the cut-off resolved at random (in expectation)."""
    k = min(k, len(scores))
    if k <= 0:
        return float('nan')
    s = sorted(scores, reverse=True)
    cut = s[k - 1]
    above = [t for sc, t in zip(scores, y) if sc > cut]
    tied = [t for sc, t in zip(scores, y) if sc == cut]
    need = k - len(above)
    return (sum(above) + need * (sum(tied) / len(tied))) / k


def cluster_bootstrap(groups: list[str], stat: Callable[[list[int]], float | None], reps: int = BOOT,
                      seed: int = SEED) -> tuple[float, float]:
    """95% percentile interval of stat(indices) resampling whole groups (tasks) with replacement."""
    by: dict[str, list[int]] = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    keys = sorted(by)
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        idx = [i for _ in keys for i in by[keys[rng.randrange(len(keys))]]]
        v = stat(idx)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            vals.append(v)
    if not vals:
        return (float('nan'), float('nan'))
    vals.sort()
    return (vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))])

# ======================================================================================= task specs and views


def _load_yaml(path: str) -> dict:
    import yaml
    with open(path) as f:
        return yaml.safe_load(f) or {}


class View:
    """Where a scorer's task definitions and grader live. kind: snapshot | frozen | current."""

    def __init__(self, kind: str, tasks_root: str, grade_path: str | None, scorer_path: str | None = None,
                 cleanup: str | None = None, label: str = ''):
        self.kind, self.tasks_root, self.grade_path, self.scorer_path = kind, tasks_root, grade_path, scorer_path
        self.cleanup, self.label = cleanup, label or kind
        self._specs: dict[str, dict] = {}
        self._grader = None

    def task(self, task_id: str) -> dict:
        if task_id not in self._specs:
            p = os.path.join(self.tasks_root, task_id, 'task.yaml')
            self._specs[task_id] = _load_yaml(p) if os.path.isfile(p) else {}
        return self._specs[task_id]

    def spec(self, task_id: str, check_name: str) -> dict:
        for c in self.task(task_id).get('checks') or []:
            if c.get('name', c.get('type')) == check_name:
                return c
        return {}

    def task_dir(self, task_id: str) -> str:
        return os.path.join(self.tasks_root, task_id)

    def grader(self):
        """The grade module whose CHECKS / c_custom the verdicts came from (loaded once, isolated name)."""
        if self._grader is None:
            if self.scorer_path:
                spec = importlib.util.spec_from_file_location(f'triage_scorer_{self.kind}', self.scorer_path)
                mod = importlib.util.module_from_spec(spec)
                saved = sys.modules.get('grade')
                with contextlib.redirect_stdout(io.StringIO()):
                    spec.loader.exec_module(mod)  # type: ignore
                if saved is not None:
                    sys.modules['grade'] = saved
                self._grader = mod.base
            else:
                spec = importlib.util.spec_from_file_location(f'triage_grade_{self.kind}', self.grade_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                self._grader = mod
            _install_recalc_cache(self._grader)
        return self._grader

    def close(self):
        if self.cleanup:
            shutil.rmtree(self.cleanup, ignore_errors=True)


def _install_recalc_cache(g) -> None:
    """Content-keyed memo over the grader's recalculated_workbook (temp copies of one workbook share a result)."""
    if getattr(g, '_triage_cache', False) or not hasattr(g, 'recalculated_workbook'):
        return
    orig = g.recalculated_workbook
    memo: dict[str, str] = {}

    def cached(path: str) -> str:
        try:
            with open(path, 'rb') as f:
                h = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return orig(path)
        hit = memo.get(h)
        if hit and os.path.exists(hit):
            return hit
        out = orig(path)
        if out != path:
            memo[h] = out
        return out
    g.recalculated_workbook = cached
    g._triage_cache = True


def open_view(name: str, tasks_root: str | None = None) -> View:
    if name == 'frozen':
        return View('frozen', os.path.join(FROZEN, 'tasks', 'desk'), None, os.path.join(FROZEN, 'scorer.py'),
                    label='frozen-v7')
    if name == 'current':
        return View('current', tasks_root or os.path.join(ROOT, 'tasks', 'desk'), os.path.join(HERE, 'grade.py'),
                    label='current')
    if name.startswith('snapshot:'):
        ref = name.split(':', 1)[1]
        tmp = tempfile.mkdtemp(prefix='triage-snap-')
        arc = subprocess.run(['git', '-C', ROOT, 'archive', ref, 'tasks/desk', 'bench/grade.py'],
                             capture_output=True, check=True).stdout
        subprocess.run(['tar', '-x', '-C', tmp], input=arc, check=True)
        return View('snapshot', os.path.join(tmp, 'tasks', 'desk'), os.path.join(tmp, 'bench', 'grade.py'),
                    cleanup=tmp, label=name)
    raise SystemExit(f'unknown view {name!r}: snapshot:<ref>, frozen or current')


def read_jsonl(text: str) -> list[dict]:
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def load_ledger(path: str) -> list[dict]:
    with open(path) as f:
        return read_jsonl(f.read())


def load_snapshot_ledger(ref: str) -> list[dict]:
    out = subprocess.run(['git', '-C', ROOT, 'show', f'{ref}:results/latest/attempts.jsonl'],
                         capture_output=True, text=True, check=True).stdout
    return read_jsonl(out)

# ======================================================================================= single-check grading


def run_check(g, task_dir: str, spec: dict, ws: str) -> tuple[bool | None, str]:
    """Run one check of `spec` with grade module `g`. (passed, detail); passed None on a grader crash."""
    ref = os.path.join(task_dir, 'reference')
    t = spec.get('type')
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            if t == 'custom':
                res = g.c_custom(ws, ref, spec, task_dir=task_dir)
            elif t in getattr(g, 'TASK_DIR_CHECKS', {}):
                res = g.TASK_DIR_CHECKS[t](ws, ref, spec, task_dir=task_dir)
            else:
                res = g.CHECKS[t](ws, ref, spec)
        return bool(res[0]), str(res[1])[:300]
    except Exception as e:  # noqa: BLE001 - a crash is data here, never fatal
        return None, f'{type(e).__name__}: {e}'[:300]


def _custom_sources(task_dir: str, task: dict) -> dict[str, str]:
    src = {}
    for c in task.get('checks') or []:
        if c.get('type') in ('custom', 'plan_feasible'):
            mod = c.get('module', 'check.py' if c['type'] == 'custom' else 'plan_check.py')
            p = os.path.join(task_dir, mod)
            if os.path.isfile(p):
                with open(p, encoding='utf-8', errors='replace') as f:
                    src[mod] = f.read()
    return src


def reads_file(spec: dict, relpath: str, sources: dict[str, str]) -> bool:
    """Does check `spec` read deliverable `relpath`? Built-ins by path glob; custom modules by source mention."""
    import metamorphic as mt
    if spec.get('type') in ('custom', 'plan_feasible'):
        mod = spec.get('module', 'check.py' if spec['type'] == 'custom' else 'plan_check.py')
        return bool(mt.custom_reads({mod: sources.get(mod, '')}, relpath))
    return spec in mt.checks_on({'checks': [spec]}, relpath)


def files_under(d: str) -> list[str]:
    out = []
    for base, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in ('.proto', '.codex', 'node_modules', '.git', '__pycache__')]
        for f in files:
            out.append(os.path.relpath(os.path.join(base, f), d))
    return sorted(out)


def _copy_ws(src: str, dst: str) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('.proto', '.codex', 'node_modules', '.git'),
                    symlinks=True)


def text_transforms() -> list[str]:
    """Invariant-by-default transforms that need no workbook recalculation (xlsx ones are left out: without
    LibreOffice the Python engine returns #NAME? on COUNTIFS/SUMIFS, which would read as grader failures)."""
    import metamorphic as mt
    return [n for n, t in mt.TRANSFORMS.items() if t.kind in ('csv', 'md', 'html', 'ics') and t.default_class == mt.INVARIANT
            or n == 'csv_bom']


def transform_check(g, view_task_dir: str, task: dict, spec: dict, src_ws: str, tnames: list[str],
                    sources: dict[str, str]) -> list[dict]:
    """Apply each invariant transform to the files `spec` reads in `src_ws` (a copy; src_ws is not written) and
    re-run the check. Returns one record per applicable transform: {transform, files, passed, detail}."""
    import metamorphic as mt
    files = files_under(src_ws)
    targets = [f for f in files if reads_file(spec, f, sources)]
    out = []
    for tn in tnames:
        t = mt.TRANSFORMS[tn]
        tf = [f for f in targets if mt.file_kind(f) == t.kind]
        if not tf:
            continue
        cls = [mt.classify(tn, task, f, sources)[0] for f in tf]
        if any(c != mt.INVARIANT for c in cls):
            continue
        work = tempfile.mkdtemp(prefix='triage-mt-')
        try:
            ws = os.path.join(work, 'ws')
            changed = mt.apply_transform(tn, src_ws, ws, tf)
            if not changed:
                continue
            ok, detail = run_check(g, view_task_dir, spec, ws)
            out.append({'transform': tn, 'files': changed, 'passed': ok, 'detail': detail})
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return out


def metamorphic_scan(view: View, task_ids: list[str], sol_root: str | None = None, log=None) -> dict:
    """Per-check metamorphic false negatives on the reference solutions under `view`'s grader.
    For every (task, check) whose baseline passes, run the check alone under every applicable invariant
    text transform of the files it reads. -> {task: {check: {'tried': n, 'fn': [transforms]}}, '_skipped': ...}"""
    g = view.grader()
    tnames = text_transforms()
    out: dict = {'_view': view.label, '_transforms': tnames, '_skipped': {}}
    for tid in task_ids:
        td = view.task_dir(tid)
        task = view.task(tid)
        sol = os.path.join(sol_root or view.tasks_root, tid, 'reference_solution')
        if not task or not os.path.isdir(sol):
            out['_skipped'][tid] = 'no task or reference solution'
            continue
        sources = _custom_sources(td, task)
        rec = {}
        for spec in task.get('checks') or []:
            if not spec.get('required', True):
                continue
            name = spec.get('name', spec['type'])
            base_ok, detail = run_check(g, td, spec, sol)
            if not base_ok:
                rec[name] = {'tried': 0, 'fn': [], 'baseline': 'fail' if base_ok is False else 'error',
                             'detail': detail[:160]}
                continue
            res = transform_check(g, td, task, spec, sol, tnames, sources)
            rec[name] = {'tried': len(res), 'fn': [r['transform'] for r in res if r['passed'] is not True]}
        out[tid] = rec
        if log:
            n = sum(1 for v in rec.values() if v['fn'])
            log(f'  {tid}: {len(rec)} checks, {n} with a metamorphic false negative')
    return out

# ======================================================================================= features

FAMILIES = {
    'text_sentence_matches': 'sentence', 'text_contains_all': 'text', 'text_contains_any': 'text',
    'text_not_contains': 'text', 'text_matches_all': 'text', 'text_numbers_present': 'numbers',
    'custom': 'custom', 'plan_feasible': 'custom', 'not_fooled': 'custom', 'forecast_error': 'csv_values',
    'xlsx_value_present': 'xlsx_value', 'xlsx_no_errors': 'xlsx_struct', 'xlsx_has_formulas': 'xlsx_struct',
    'csv_values_match': 'csv_values', 'csv_set_equal': 'csv_values', 'csv_columns': 'csv_shape',
    'csv_row_count': 'csv_shape', 'file_exists': 'file', 'artifact_readability': 'file',
}
FAMILY_ORDER = ['sentence', 'text', 'numbers', 'custom', 'xlsx_value', 'xlsx_struct', 'csv_values', 'csv_shape', 'file']

FEATURES = ['fam_' + f for f in FAMILY_ORDER] + [
    'near_miss',              # the attempt failed exactly one required check
    'log_n_failed',           # log(1 + failed required checks in the attempt)
    'panel_pass_other',       # share of the other attempts on the task that pass this check (0.5 if none)
    'other_system_pass',      # some attempt by another system passes this check
    'same_system_pass',       # share of this system's other repetitions that pass this check (0.5 if none)
    'metamorphic_fn',         # the check fails the reference solution under an invariant transform
    'abnormal_exit',          # timeout or non-zero exit: the agent did not finish normally
    'log_terms',              # log(1 + phrases / patterns / numbers / columns the check demands)
    'near_text',              # xlsx_value_present anchored to a label (layout-sensitive)
    'exact_columns',          # csv_columns exact:true (fixed template)
]

# (phrase when the feature is HIGH, phrase when it is LOW); a reason names the side that raised the score
REASON = {
    'near_miss': ('near-miss', 'one of several failures'),
    'log_n_failed': ('many failed checks', 'few failed checks'),
    'panel_pass_other': ('other attempts pass it', 'systematic: other attempts fail it too'),
    'other_system_pass': ('the other system passes it', 'the other system fails it too'),
    'same_system_pass': ('same system passes it on other reps', 'same system fails it on every rep'),
    'metamorphic_fn': ('the reference fails it when reformatted', 'reformatting the reference does not break it'),
    'abnormal_exit': ('agent did not exit normally', 'agent exited normally'),
    'log_terms': ('many literal terms demanded', 'few terms demanded'),
    'near_text': ('value must sit beside a label', 'no label anchor'),
    'exact_columns': ('exact template columns', 'columns matched by name'),
}


def _n_terms(spec: dict) -> int:
    for k in ('phrases', 'patterns', 'numbers', 'columns', 'all'):
        if isinstance(spec.get(k), list):
            return len(spec[k])
    return 1


def build_panel(attempts: list[dict], checks_of: Callable[[dict], list[dict]]) -> dict:
    """task -> check name -> list of (attempt key, harness, passed)."""
    panel: dict = {}
    for a in attempts:
        for c in checks_of(a):
            if not c.get('required', True):
                continue
            panel.setdefault(a['task'], {}).setdefault(c['name'], []).append((_akey(a), a['harness'], bool(c['passed'])))
    return panel


def _akey(a: dict) -> str:
    return a.get('run_id') or f"{a['task']}__{a['harness']}__r{a.get('run')}"


def check_features(a: dict, check: dict, failed: list[dict], n_required: int, panel: dict, view: View | None,
                   meta: dict | None) -> list[float]:
    fam = FAMILIES.get(check.get('type'), 'custom')
    x = [1.0 if fam == f else 0.0 for f in FAMILY_ORDER]
    others = [p for k, h, p in panel.get(a['task'], {}).get(check['name'], []) if k != _akey(a)]
    same = [p for k, h, p in panel.get(a['task'], {}).get(check['name'], []) if k != _akey(a) and h == a['harness']]
    other_sys = [p for k, h, p in panel.get(a['task'], {}).get(check['name'], []) if h != a['harness']]
    spec = view.spec(a['task'], check['name']) if view else {}
    m = ((meta or {}).get(a['task']) or {}).get(check['name']) or {}
    x += [
        1.0 if len(failed) == 1 else 0.0,
        math.log1p(len(failed)),
        sum(others) / len(others) if others else 0.5,
        1.0 if any(other_sys) else 0.0,
        sum(same) / len(same) if same else 0.5,
        1.0 if m.get('fn') else 0.0,
        1.0 if a.get('timed_out') or (a.get('exit_code') not in (0, None)) else 0.0,
        math.log1p(_n_terms(spec)) if spec else 0.0,
        1.0 if spec.get('near_text') else 0.0,
        1.0 if spec.get('type') == 'csv_columns' and spec.get('exact') else 0.0,
    ]
    return x


def failed_required(checks: list[dict]) -> list[dict]:
    return [c for c in checks if c.get('required', True) and not c['passed']]


def training_rows(published: list[dict], snapshot: list[dict], view: View, meta: dict | None,
                  arm: str = TRAIN_ARM) -> list[dict]:
    """One row per raw-failed required check of `arm`, features in the RAW view (snapshot verdicts, snapshot
    task specs, metamorphic under the snapshot grader), label from the frozen verdict in the published ledger.
    A raw-failed check the frozen task no longer has (redesigned) is labelled only when the frozen attempt
    passes (then every raw failure was a grader error); otherwise it is dropped as unlabelled."""
    by_src = {r['source_sha256']: r for r in snapshot if r.get('source_sha256')}
    panel = build_panel(snapshot, lambda a: a['checks'])
    rows = []
    for a in published:
        if a['harness'] != arm or a['raw_passed']:
            continue
        raw = by_src.get(a['source_sha256'])
        if raw is None:
            continue
        fz = {c['name']: c for c in a['checks']}
        failed = failed_required(raw['checks'])
        n_req = sum(1 for c in raw['checks'] if c.get('required', True))
        for c in failed:
            f = fz.get(c['name'])
            if f is not None:
                label = 1 if f['passed'] else 0
            elif a['passed']:
                label = 1
            else:
                continue
            rows.append({'task': a['task'], 'attempt': a['run_id'], 'harness': a['harness'], 'check': c['name'],
                         'type': c['type'], 'label': label, 'attempt_label': int(bool(a['passed'])),
                         'x': check_features(raw | {'run_id': raw.get('run_id') or a['run_id']}, c, failed, n_req,
                                             panel, view, meta)})
    return rows


def ranking_rows(attempts: list[dict], view: View, meta: dict | None) -> list[dict]:
    """One row per failed required check of every failed attempt, features in the view of the scorer whose
    verdicts these are."""
    panel = build_panel(attempts, lambda a: a['checks'])
    rows = []
    for a in attempts:
        if a['passed']:
            continue
        failed = failed_required(a['checks'])
        n_req = sum(1 for c in a['checks'] if c.get('required', True))
        for c in failed:
            pl = [(h, p) for k, h, p in panel.get(a['task'], {}).get(c['name'], []) if k != _akey(a)]
            counts = (sum(p for h, p in pl if h == a['harness']), sum(1 for h, p in pl if h == a['harness']),
                      sum(p for h, p in pl if h != a['harness']), sum(1 for h, p in pl if h != a['harness']))
            rows.append({'task': a['task'], 'attempt': _akey(a), 'harness': a['harness'], 'check': c['name'],
                         'type': c['type'], 'n_failed': len(failed), 'n_required': n_req, 'panel_counts': counts,
                         'x': check_features(a, c, failed, n_req, panel, view, meta)})
    return rows


# attempt-level ledger-only features (both arms; no per-check raw verdicts needed)
ATTEMPT_FEATURES = ['others_raw_pass', 'other_system_raw_pass', 'same_system_raw_pass', 'abnormal_exit',
                    'log_n_required', 'share_sentence_text', 'share_custom', 'share_xlsx', 'share_csv',
                    'task_metamorphic_fn']


def attempt_rows(published: list[dict], view: View, meta: dict | None) -> list[dict]:
    """One row per raw-failed attempt of either arm; label = the frozen scorer passes it. Uses only raw
    attempt verdicts of the other attempts and the raw-view task spec (never frozen verdicts)."""
    by_task: dict[str, list[dict]] = {}
    for a in published:
        by_task.setdefault(a['task'], []).append(a)
    rows = []
    for a in published:
        if a['raw_passed']:
            continue
        others = [o for o in by_task[a['task']] if o['run_id'] != a['run_id']]
        osys = [o['raw_passed'] for o in others if o['harness'] != a['harness']]
        same = [o['raw_passed'] for o in others if o['harness'] == a['harness']]
        specs = [c for c in view.task(a['task']).get('checks') or [] if c.get('required', True)]
        fams = [FAMILIES.get(c['type'], 'custom') for c in specs] or ['file']
        n = len(fams)
        m = (meta or {}).get(a['task']) or {}
        x = [sum(o['raw_passed'] for o in others) / len(others) if others else 0.5,
             sum(osys) / len(osys) if osys else 0.5,
             sum(same) / len(same) if same else 0.5,
             1.0 if a.get('timed_out') or a.get('exit_code') not in (0, None) else 0.0,
             math.log1p(n),
             sum(f in ('sentence', 'text', 'numbers') for f in fams) / n,
             sum(f == 'custom' for f in fams) / n,
             sum(f in ('xlsx_value', 'xlsx_struct') for f in fams) / n,
             sum(f in ('csv_values', 'csv_shape') for f in fams) / n,
             1.0 if any(v.get('fn') for v in m.values()) else 0.0]
        rows.append({'task': a['task'], 'attempt': a['run_id'], 'harness': a['harness'],
                     'label': int(bool(a['passed'])), 'x': x})
    return rows

# ======================================================================================= evaluation

COMPACT = ['panel_pass_other', 'same_system_pass', 'other_system_pass', 'near_miss', 'log_n_failed',
           'metamorphic_fn', 'abnormal_exit']
# candidate specifications for nested selection: (name, feature names or None for all, lambda)
CONFIGS = [('full', None, 1.0), ('full', None, 10.0), ('compact', COMPACT, 1.0), ('compact', COMPACT, 10.0),
           ('panel', ['panel_pass_other'], 1.0)]


def _cols(names: list[str] | None, features: list[str]) -> list[int] | None:
    return None if names is None else [features.index(n) for n in names]


def _folds(rows: list[dict], k: int, seed: int) -> list[set[str]]:
    tasks = sorted({r['task'] for r in rows})
    random.Random(seed).shuffle(tasks)
    return [set(tasks[i::k]) for i in range(min(k, len(tasks)))]


def cv_predict(rows: list[dict], cols: list[int] | None = None, lam: float = LAMBDA, k: int = 5,
               repeats: int = 10, seed: int = SEED) -> list[float]:
    """Out-of-fold probabilities from grouped k-fold (whole tasks held out), averaged over `repeats` random fold
    assignments. Every prediction for a row comes from a model that never saw the row's task."""
    sel = (lambda x: [x[i] for i in cols]) if cols is not None else (lambda x: x)
    acc = [0.0] * len(rows)
    for rep in range(repeats):
        for held in _folds(rows, k, seed + rep):
            tr = [r for r in rows if r['task'] not in held]
            te = [i for i, r in enumerate(rows) if r['task'] in held]
            ys = [r['label'] for r in tr]
            if len(set(ys)) < 2:
                ps = [sum(ys) / len(ys) if ys else 0.5] * len(te)
            else:
                m = fit_logreg([sel(r['x']) for r in tr], ys, lam)
                ps = predict(m, [sel(rows[i]['x']) for i in te])
            for i, p in zip(te, ps):
                acc[i] += p / repeats
    return acc


def select_config(rows: list[dict], features: list[str], configs=CONFIGS, seed: int = SEED) -> tuple:
    """The config with the best grouped-CV AUC on `rows` (ties: the earlier-listed one)."""
    best, best_auc = configs[0], -1.0
    for cfg in configs:
        a = auc(cv_predict(rows, _cols(cfg[1], features), cfg[2], repeats=2, seed=seed),
                [r['label'] for r in rows]) or 0.0
        if a > best_auc + 1e-12:
            best, best_auc = cfg, a
    return best


def nested_predict(rows: list[dict], features: list[str], configs=CONFIGS, k: int = 5, repeats: int = 5,
                   seed: int = SEED) -> tuple[list[float], dict]:
    """Outer grouped k-fold; inside each outer fold the config is chosen by grouped CV on the training tasks
    only, so the outer predictions carry no selection optimism."""
    acc = [0.0] * len(rows)
    chosen: dict[str, int] = {}
    for rep in range(repeats):
        for held in _folds(rows, k, seed + 1000 + rep):
            tr = [r for r in rows if r['task'] not in held]
            te = [i for i, r in enumerate(rows) if r['task'] in held]
            cfg = select_config(tr, features, configs, seed=seed + rep)
            key = f'{cfg[0]}/lambda={cfg[2]:g}'
            chosen[key] = chosen.get(key, 0) + 1
            cols = _cols(cfg[1], features)
            sel = (lambda x, cols=cols: [x[i] for i in cols]) if cols is not None else (lambda x: x)
            m = fit_logreg([sel(r['x']) for r in tr], [r['label'] for r in tr], cfg[2])
            for i, p in zip(te, predict(m, [sel(rows[i]['x']) for i in te])):
                acc[i] += p / repeats
    return acc, chosen


def aggregate(rows: list[dict], probs: list[float], how: str = 'product') -> dict[str, float]:
    """Attempt score from its failed checks' scores. product: P(every failure is a grader error)."""
    acc: dict[str, list[float]] = {}
    for r, p in zip(rows, probs):
        acc.setdefault(r['attempt'], []).append(p)
    if how == 'max':
        return {k: max(v) for k, v in acc.items()}
    return {k: math.prod(v) for k, v in acc.items()}


def metric_block(scores: list[float], y: list[int], groups: list[str], ks=(10, 50)) -> dict:
    out = {'n': len(y), 'positives': sum(y), 'auc': auc(scores, y)}
    out['auc_ci'] = cluster_bootstrap(groups, lambda idx: auc([scores[i] for i in idx], [y[i] for i in idx]))
    for k in ks:
        out[f'p@{k}'] = precision_at(scores, y, k)
        out[f'p@{k}_ci'] = cluster_bootstrap(
            groups, lambda idx, k=k: precision_at([scores[i] for i in idx], [y[i] for i in idx], k))
    return out


def evaluate(check_rows: list[dict], att_rows: list[dict]) -> dict:
    """Out-of-fold metrics (repeated grouped 5-fold by task). Heuristic baselines are unfitted scores whose
    direction is stated before looking (near-miss and fewer failures = suspicious; a metamorphic false negative
    = suspicious; other attempts passing = suspicious). `everyone_else_fails` is the reverse of the last one: its
    direction was found on this data, so it is reported but is not an a-priori baseline."""
    fi = {f: i for i, f in enumerate(FEATURES)}
    res: dict = {'features': FEATURES, 'configs': [[c[0], c[1], c[2]] for c in CONFIGS],
                 'cv': 'grouped 5-fold by task, 10 repeats (nested: 5 outer repeats, inner grouped 5-fold x2)',
                 'check_level': {}, 'attempt_level_codex': {}, 'attempt_level_ledger': {}}
    y = [r['label'] for r in check_rows]
    g = [r['task'] for r in check_rows]
    nested, chosen = nested_predict(check_rows, FEATURES)
    res['nested_choices'] = chosen
    x = lambda f: [r['x'][fi[f]] for r in check_rows]  # noqa: E731
    variants = {'model (nested selection)': nested}
    for name, cols, lam in CONFIGS:
        variants[f'{name}/lambda={lam:g} (not selection-adjusted)'] = cv_predict(check_rows, _cols(cols, FEATURES), lam)
    variants.update({
        'check_type_only (fitted in-fold)': cv_predict(check_rows, [fi['fam_' + f] for f in FAMILY_ORDER]),
        'near_miss': x('near_miss'),
        'fewest_failed_checks': [-v for v in x('log_n_failed')],
        'metamorphic_fn': x('metamorphic_fn'),
        'others_pass_it': x('panel_pass_other'),
        'everyone_else_fails (post hoc)': [1 - v for v in x('panel_pass_other')],
        'base_rate': [0.0] * len(check_rows),
    })
    for name, s in variants.items():
        res['check_level'][name] = metric_block(s, y, g)
    att_label: dict[str, int] = {}
    att_task: dict[str, str] = {}
    for r in check_rows:
        att_label[r['attempt']] = r['attempt_label']
        att_task[r['attempt']] = r['task']
    keys = sorted(att_label)
    ya = [att_label[k] for k in keys]
    ga = [att_task[k] for k in keys]
    for name, s in variants.items():
        # heuristic 0/1 scores aggregate by max (any suspicious check); probabilities by product (all errors)
        hows = ('product', 'max') if name.startswith('model') else \
            (('product',) if '(not selection' in name or 'fitted' in name else ('max',))
        for how in hows:
            agg = aggregate(check_rows, s, how)
            res['attempt_level_codex'][f'{name}:{how}'] = metric_block([agg[k] for k in keys], ya, ga)
    ya2 = [r['label'] for r in att_rows]
    ga2 = [r['task'] for r in att_rows]
    ai = {f: i for i, f in enumerate(ATTEMPT_FEATURES)}
    res['attempt_level_ledger']['model (all attempt features, lambda=1)'] = metric_block(cv_predict(att_rows), ya2, ga2)
    res['attempt_level_ledger']['others_pass_task (raw)'] = metric_block(
        [r['x'][ai['others_raw_pass']] for r in att_rows], ya2, ga2)
    res['attempt_level_ledger']['everyone_else_fails_task (post hoc)'] = metric_block(
        [1 - r['x'][ai['others_raw_pass']] for r in att_rows], ya2, ga2)
    res['attempt_level_ledger']['base_rate'] = metric_block([0.0] * len(att_rows), ya2, ga2)
    res['attempt_level_ledger']['positives_by_harness'] = {
        h: [sum(r['label'] for r in att_rows if r['harness'] == h), sum(1 for r in att_rows if r['harness'] == h)]
        for h in sorted({r['harness'] for r in att_rows})}
    return res


# ======================================================================================= reasons and queue


def reason_line(model: dict, row: dict, extra: list[str] | None = None) -> str:
    fi = {f: i for i, f in enumerate(FEATURES)}
    x = row['x']
    parts = list(extra or [])
    fam = next((f for f in FAMILY_ORDER if x[fi['fam_' + f]]), 'other')
    parts.append(f"{row['type']}")
    if x[fi['near_miss']]:
        parts.append('near-miss: only failed check')
    else:
        parts.append(f"{row.get('n_failed', '?')} failed checks")
    pc = row.get('panel_counts')
    if pc:
        parts.append(f"passed by {pc[0]}/{pc[1]} other reps of this system, {pc[2]}/{pc[3]} attempts of others")
    if x[fi['metamorphic_fn']]:
        parts.append('reference fails it when reformatted')
    if x[fi['abnormal_exit']]:
        parts.append('agent did not exit normally')
    names = model.get('features', FEATURES)
    c = contributions(model, model_x(model, x))
    top = sorted(((v, i) for i, v in enumerate(c) if not names[i].startswith('fam_')), reverse=True)[:2]
    sig = []
    for v, i in top:
        if v > 0.1 and names[i] in REASON:
            high = (model_x(model, x)[i] - model['mean'][i]) > 0
            sig.append(REASON[names[i]][0 if high else 1])
    if sig:
        parts.append('raised by: ' + ', '.join(sig))
    if fam in ('xlsx_value', 'xlsx_struct'):
        parts.append('workbook recalculation involved')
    return '; '.join(parts)


def build_queue(rows: list[dict], probs: list[float], model: dict, extra: dict | None = None,
                tier: dict | None = None) -> list[dict]:
    """Attempts ranked by (tier, score), each with its failed checks ranked by score."""
    extra = extra or {}
    tier = tier or {}
    att: dict[str, dict] = {}
    for r, p in zip(rows, probs):
        a = att.setdefault(r['attempt'], {'attempt': r['attempt'], 'task': r['task'], 'harness': r['harness'],
                                          'checks': [], 'score': 1.0, 'tier': 3})
        a['checks'].append({'check': r['check'], 'type': r['type'], 'score': p,
                            'tier': tier.get((r['attempt'], r['check']), 3),
                            'reason': reason_line(model, r, extra.get((r['attempt'], r['check'])))})
        a['score'] *= p
    for a in att.values():
        a['checks'].sort(key=lambda c: (c['tier'], -c['score']))
        # an attempt's tier is its weakest check's tier: the verdict flips only if every failure is an error
        a['tier'] = max(c['tier'] for c in a['checks'])
        a['n_failed'] = len(a['checks'])
    return sorted(att.values(), key=lambda a: (a['tier'], -a['score'], a['attempt']))


def write_queue(queue: list[dict], out_dir: str, title: str, preface: str = '', top: int | None = None) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'queue.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['rank', 'attempt', 'task', 'harness', 'attempt_score', 'tier', 'n_failed', 'check',
                    'check_type', 'check_score', 'reason'])
        for i, a in enumerate(queue, 1):
            for c in a['checks']:
                w.writerow([i, a['attempt'], a['task'], a['harness'], f"{a['score']:.4f}", a['tier'], a['n_failed'],
                            c['check'], c['type'], f"{c['score']:.4f}", c['reason']])
    L = [f'# {title}\n', preface, '',
         '| # | attempt | score | tier | failed | most suspicious failed check | reason |',
         '|---|---|---|---|---|---|---|']
    for i, a in enumerate(queue[:top] if top else queue, 1):
        c = a['checks'][0]
        L.append(f"| {i} | `{a['attempt']}` | {a['score']:.3f} | {a['tier']} | {a['n_failed']} | "
                 f"{c['check'].replace('|', '/')} | {c['reason'].replace('|', '/')} |")
    tq = task_queue(queue)
    with open(os.path.join(out_dir, 'tasks.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['rank', 'task', 'best_attempt_score', 'failed_attempts', 'harnesses', 'top_check', 'reason'])
        for i, t in enumerate(tq, 1):
            w.writerow([i, t['task'], f"{t['score']:.4f}", t['failed_attempts'], ' '.join(t['harnesses']),
                        t['top_check'], t['reason']])
    L += ['', '## By task (audit units)', '',
          'One artifact review usually settles every repetition of the same check, so tasks are ranked by their '
          'most suspicious failed attempt.', '',
          '| # | task | best score | failed attempts | systems | most suspicious check |', '|---|---|---|---|---|---|']
    for i, t in enumerate(tq[:top] if top else tq, 1):
        L.append(f"| {i} | {t['task']} | {t['score']:.3f} | {t['failed_attempts']} | {', '.join(t['harnesses'])} | "
                 f"{t['top_check'].replace('|', '/')} |")
    with open(os.path.join(out_dir, 'queue.md'), 'w') as f:
        f.write('\n'.join(L) + '\n')


def task_queue(queue: list[dict]) -> list[dict]:
    """Tasks ranked by their best-ranked failed attempt (queue order), with the attempts and systems involved."""
    out: dict[str, dict] = {}
    for a in queue:
        t = out.setdefault(a['task'], {'task': a['task'], 'score': a['score'], 'tier': a['tier'], 'failed_attempts': 0,
                                       'harnesses': [], 'top_check': a['checks'][0]['check'],
                                       'reason': a['checks'][0]['reason']})
        t['failed_attempts'] += 1
        if a['harness'] not in t['harnesses']:
            t['harnesses'].append(a['harness'])
    return list(out.values())

# ======================================================================================= artifact layer

# probes: "the value is there, formatted differently". Weaker evidence than an invariant transform, since each
# relaxes the contract a little (a human decides whether the relaxation is fair for the task).
_EMPH = re.compile(r'(\*\*|__|`)')


def _probe_text(s: str) -> str:
    s = s.replace(' ', ' ').replace('’', "'").replace('‘', "'").replace('“', '"') \
         .replace('”', '"').replace('–', '-').replace('—', '-')
    s = _EMPH.sub('', s)
    return s


def probe_text_normalise(data: bytes) -> bytes:
    """Typographic quotes/dashes to ASCII, NBSP to space, Markdown emphasis and code ticks removed."""
    return _probe_text(data.decode('utf-8', errors='replace')).encode('utf-8')


def probe_collapse_ws(data: bytes) -> bytes:
    """Every whitespace run (line breaks included) to one space, paragraph breaks kept."""
    t = data.decode('utf-8', errors='replace')
    paras = re.split(r'\n\s*\n', t)
    return '\n\n'.join(' '.join(p.split()) for p in paras).encode('utf-8')


TEXT_PROBES = {'text_normalise': probe_text_normalise, 'collapse_ws': probe_collapse_ws}
TEXT_FAMILIES = {'sentence', 'text', 'numbers'}


def _header_tokens(h: str) -> set[str]:
    return {w for w in re.findall(r'[a-z0-9]+', h.lower()) if w not in ('the', 'of', 'a', 'no', 'number', 'num')}


def probe_csv_headers(data: bytes, wanted: list[str]) -> bytes | None:
    """Rename deliverable headers whose word set matches (or contains) a wanted column's word set."""
    import metamorphic as mt
    rows, bom, term, trailing, d = mt._csv_parse(data)
    if not rows:
        return None
    head = list(rows[0])
    changed = False
    have = {re.sub(r'[^a-z0-9]+', '_', h.strip().lower()).strip('_') for h in head}
    for want in wanted:
        wn = re.sub(r'[^a-z0-9]+', '_', str(want).strip().lower()).strip('_')
        if wn in have:
            continue
        wt = _header_tokens(str(want))
        for j, h in enumerate(head):
            ht = _header_tokens(h)
            if wt and ht and (wt <= ht or ht <= wt):
                head[j] = str(want); changed = True; have.add(wn)
                break
    if not changed:
        return None
    rows[0] = head
    return mt._csv_write(rows, bom, term, trailing, d)


def spec_probes(spec: dict) -> dict[str, dict]:
    """Relaxed copies of a check spec: value present but not beside its label, or rounded to whole units;
    text compared ignoring punctuation."""
    out = {}
    t = spec.get('type')
    if t == 'xlsx_value_present':
        if spec.get('near_text'):
            out['value_elsewhere'] = {k: v for k, v in spec.items() if k != 'near_text'}
        exp = abs(float(spec.get('expected', 0) or 0))
        if exp >= 10:
            out['value_rounded'] = dict(spec, rel_tol=max(float(spec.get('rel_tol', 0.01)), 0.5 / exp))
    if t in ('csv_values_match', 'csv_set_equal') and not spec.get('numeric'):
        out['values_alnum'] = dict(spec, normalize=['alnum'])
    return out


def artifact_probe(view: View, task_id: str, check: dict, ws: str) -> dict:
    """Re-run one failed check on a copy of the agent's files: as recorded, under invariant transforms, and
    under probes. `ws` is only read. -> {reproduced, local_detail, transform_flips, probe_flips, low_confidence}"""
    g = view.grader()
    td = view.task_dir(task_id)
    task = view.task(task_id)
    spec = view.spec(task_id, check['name'])
    out = {'reproduced': None, 'transform_flips': [], 'probe_flips': [], 'low_confidence': []}
    if not spec:
        out['note'] = 'check not in current task definition'
        return out
    fam = FAMILIES.get(spec.get('type'), 'custom')
    sources = _custom_sources(td, task)
    work = tempfile.mkdtemp(prefix='triage-art-')
    try:
        base = os.path.join(work, 'base')
        _copy_ws(ws, base)
        reads_xlsx = any(f.lower().endswith(('.xlsx', '.xlsm')) and reads_file(spec, f, sources) for f in files_under(base))
        if reads_xlsx and not (shutil.which('soffice') or shutil.which('libreoffice') or
                               os.environ.get('BENCH_RECALC_DOCKER_IMAGE')):
            out['low_confidence'].append('workbook recalculated with the Python formulas engine (no LibreOffice): '
                                         'COUNTIFS/SUMIFS and similar read #NAME?')
        ok, detail = run_check(g, td, spec, base)
        out['reproduced'] = (ok is False)
        out['local_detail'] = detail
        if ok is not False:
            # the recorded fail does not reproduce locally: report it, do not probe a check that passes here
            return out
        for r in transform_check(g, td, task, spec, base, text_transforms(), sources):
            if r['passed']:
                out['transform_flips'].append(r['transform'])
        targets = [f for f in files_under(base) if reads_file(spec, f, sources)]
        if fam in TEXT_FAMILIES:
            for name, fn in TEXT_PROBES.items():
                d = os.path.join(work, name)
                _copy_ws(base, d)
                touched = False
                for f in targets:
                    if os.path.splitext(f)[1].lower() in ('.md', '.markdown', '.txt', '.html', '.htm'):
                        p = os.path.join(d, f)
                        with open(p, 'rb') as fh:
                            before = fh.read()
                        after = fn(before)
                        if after != before:
                            with open(p, 'wb') as fh:
                                fh.write(after)
                            touched = True
                if touched and run_check(g, td, spec, d)[0]:
                    out['probe_flips'].append(name)
        if fam in ('csv_values', 'csv_shape'):
            wanted = list(spec.get('columns') or [])
            for k in ('key', 'column'):
                v = spec.get(k)
                wanted += v if isinstance(v, list) else ([v] if v else [])
            d = os.path.join(work, 'csv_headers')
            _copy_ws(base, d)
            touched = False
            for f in targets:
                if f.lower().endswith(('.csv', '.tsv')):
                    p = os.path.join(d, f)
                    with open(p, 'rb') as fh:
                        new = probe_csv_headers(fh.read(), wanted)
                    if new is not None:
                        with open(p, 'wb') as fh:
                            fh.write(new)
                        touched = True
            if touched and run_check(g, td, spec, d)[0]:
                out['probe_flips'].append('csv_headers')
        if fam == 'file' and spec.get('path'):
            stem = os.path.splitext(os.path.basename(spec['path']))[0].lower()
            alt = [f for f in files_under(base) if os.path.splitext(os.path.basename(f))[0].lower() == stem]
            if alt:
                out['probe_flips'].append('same_name_other_extension')
        for name, s2 in spec_probes(spec).items():
            if run_check(g, td, s2, base)[0]:
                out['probe_flips'].append(name)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def load_run(run_dir: str) -> list[dict]:
    """Attempts of a bench/run.py label directory: <run_dir>/<run_id>/result.json (+ ws/)."""
    out = []
    for name in sorted(os.listdir(run_dir)):
        rp = os.path.join(run_dir, name, 'result.json')
        if os.path.isfile(rp):
            with open(rp) as f:
                r = json.load(f)
            r['_ws'] = os.path.join(run_dir, name, 'ws')
            out.append(r)
    return out

# ======================================================================================= commands


def _log(s: str) -> None:
    print(s, file=sys.stderr, flush=True)


def cmd_metamorphic(a) -> int:
    view = open_view(a.view, a.tasks_root)
    try:
        ids = [t for t in (a.tasks.split(',') if a.tasks else sorted(os.listdir(view.tasks_root)))
               if os.path.isfile(os.path.join(view.tasks_root, t, 'task.yaml'))]
        sol_root = a.solutions or (os.path.join(ROOT, 'tasks', 'desk') if view.kind == 'frozen' else None)
        res = metamorphic_scan(view, ids, sol_root, None if a.quiet else _log)
    finally:
        view.close()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w') as f:
        json.dump(res, f, indent=1, sort_keys=True)
    n = sum(1 for t, v in res.items() if not t.startswith('_') for c in v.values() if c['fn'])
    print(f'{n} (task, check) pairs fail an invariant transform of the reference; written {a.out}')
    return 0


def _load_json(p: str | None) -> dict | None:
    if p and os.path.isfile(p):
        with open(p) as f:
            return json.load(f)
    return None


def cmd_fit(a) -> int:
    published = load_ledger(a.ledger)
    snapshot = load_snapshot_ledger(a.snapshot)
    meta = _load_json(a.meta_snapshot)
    if meta is None:
        _log(f'no metamorphic cache at {a.meta_snapshot}: metamorphic_fn is 0 everywhere '
             f'(run `triage.py metamorphic --view snapshot:{a.snapshot} --out {a.meta_snapshot}`)')
    view = open_view(f'snapshot:{a.snapshot}')
    try:
        rows = training_rows(published, snapshot, view, meta)
        arows = attempt_rows(published, view, meta)
    finally:
        view.close()
    ev = evaluate(rows, arows)
    name, names, lam = select_config(rows, FEATURES)
    cols = _cols(names, FEATURES)
    model = fit_logreg([r['x'] if cols is None else [r['x'][i] for i in cols] for r in rows],
                       [r['label'] for r in rows], lam)
    model.update({'config': name, 'features': names or FEATURES, 'cols': cols, 'lambda': lam, 'trained_on': {
        'arm': TRAIN_ARM, 'rows': len(rows), 'positives': sum(r['label'] for r in rows),
        'tasks': len({r['task'] for r in rows}), 'snapshot': a.snapshot,
        'ledger_sha256': hashlib.sha256(open(a.ledger, 'rb').read()).hexdigest()}})
    amodel = fit_logreg([r['x'] for r in arows], [r['label'] for r in arows])
    amodel.update({'features': ATTEMPT_FEATURES})
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'model.json'), 'w') as f:
        json.dump({'check_model': model, 'attempt_model': amodel}, f, indent=1)
    with open(os.path.join(a.out, 'evaluation.json'), 'w') as f:
        json.dump(ev, f, indent=1)
    print(render_eval(ev, model))
    return 0


def _fmt(b: dict, k: str) -> str:
    v = b.get(k)
    ci = b.get(k + '_ci')
    if v is None:
        return 'n/a'
    return f'{v:.3f} [{ci[0]:.2f}, {ci[1]:.2f}]' if ci else f'{v:.3f}'


def render_eval(ev: dict, model: dict | None = None) -> str:
    L = []
    for sec, title in (('check_level', 'Check level (codex-sol raw failures)'),
                       ('attempt_level_codex', 'Attempt level (codex-sol raw-failed attempts)'),
                       ('attempt_level_ledger', 'Attempt level, ledger-only model (both arms)')):
        blk = {k: v for k, v in ev[sec].items() if isinstance(v, dict) and 'auc' in v}
        if not blk:
            continue
        any_b = next(iter(blk.values()))
        L.append(f"\n{title}: n={any_b['n']}, positives={any_b['positives']}")
        L.append(f"  {'scorer':52} {'AUC [95% CI]':22} {'P@10':20} {'P@50':20}")
        for k, b in blk.items():
            L.append(f"  {k:52} {_fmt(b, 'auc'):22} {_fmt(b, 'p@10'):20} {_fmt(b, 'p@50'):20}")
    if ev.get('nested_choices'):
        L.append(f"\nConfigs chosen by the inner loop across outer folds: {ev['nested_choices']}")
    if model:
        L.append(f"\nFinal model: {model.get('config')} lambda={model.get('lambda')}; "
                 'weights on standardised features (full-data fit):')
        for f, w in sorted(zip(model['features'], model['w']), key=lambda t: -abs(t[1])):
            L.append(f'  {f:20} {w:+.3f}')
    return '\n'.join(L)


def cmd_rank(a) -> int:
    m = _load_json(a.model)
    if m is None:
        raise SystemExit(f'no model at {a.model}; run `triage.py fit` first')
    model = m['check_model']
    if a.run:
        attempts = load_run(a.run)
        view = open_view('current', a.tasks_root)
        meta = _load_json(a.meta)
        if meta is None:
            # cheap (text transforms only): scan just the tasks that have a failed attempt
            meta = metamorphic_scan(view, sorted({x['task'] for x in attempts if not x['passed']}))
    else:
        attempts = load_ledger(a.ledger)
        view = open_view('frozen')
        meta = _load_json(a.meta)
        if meta is None:
            _log(f'no metamorphic cache at {a.meta}: metamorphic_fn is 0 everywhere')
    rows = ranking_rows(attempts, view, meta)
    probs = model_predict(model, [r['x'] for r in rows])
    extra, tier = {}, {}
    if a.run and not a.no_artifacts:
        ws_of = {_akey(x): x['_ws'] for x in attempts}
        for r in rows:
            ws = ws_of.get(r['attempt'])
            if not ws or not os.path.isdir(ws):
                extra[(r['attempt'], r['check'])] = ['no local workspace']
                continue
            pr = artifact_probe(view, r['task'], {'name': r['check']}, ws)
            notes = []
            t = 3
            if pr['reproduced'] is False:
                notes.append('recorded fail does NOT reproduce locally (' + pr.get('local_detail', '')[:60] + ')')
            if pr['transform_flips']:
                t = 1
                notes.append('passes after invariant ' + ','.join(pr['transform_flips']))
            elif pr['probe_flips']:
                t = 2
                notes.append('passes under probe ' + ','.join(pr['probe_flips']))
            notes += ['LOW CONFIDENCE: ' + x for x in pr['low_confidence']]
            extra[(r['attempt'], r['check'])] = notes
            tier[(r['attempt'], r['check'])] = t
    view.close()
    queue = build_queue(rows, probs, model, extra, tier)
    src = a.run or os.path.relpath(a.ledger, ROOT)
    pre = (f'{len(queue)} failed attempts from `{src}`, {len(rows)} failed required checks. Score = product of '
           f'the failed checks\' grader-error probabilities (the chance the verdict itself is wrong). '
           f'Tier 1: an invariant transform of the agent\'s own output passes; 2: a formatting probe passes; '
           f'3: model only.')
    write_queue(queue, a.out, 'Grader-error audit queue', pre, a.top)
    with open(os.path.join(a.out, 'queue.json'), 'w') as f:
        json.dump(queue, f, indent=1)
    for i, q in enumerate(queue[:a.show], 1):
        c = q['checks'][0]
        print(f"{i:3} {q['score']:.3f} t{q['tier']} {q['attempt']:55} {c['check'][:40]:40} {c['reason']}")
    print(f'written {a.out}/queue.csv, queue.md, queue.json')
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('metamorphic', help='per-check metamorphic false negatives on reference solutions')
    p.add_argument('--view', required=True, help='snapshot:<ref> | frozen | current')
    p.add_argument('--tasks', help='comma-separated task ids (default: all)')
    p.add_argument('--tasks-root', help='tasks root for --view current')
    p.add_argument('--solutions', help='root holding <task>/reference_solution (default: the view; tasks/desk for frozen)')
    p.add_argument('--out', required=True)
    p.add_argument('-q', '--quiet', action='store_true')
    p = sub.add_parser('fit', help='fit and cross-validate the ledger model')
    p.add_argument('--ledger', default=DEFAULT_LEDGER)
    p.add_argument('--snapshot', default=DEFAULT_SNAPSHOT)
    p.add_argument('--meta-snapshot', default=os.path.join(DEFAULT_OUT, 'metamorphic-snapshot.json'))
    p.add_argument('--out', default=DEFAULT_OUT)
    p = sub.add_parser('rank', help='rank failed attempts of a ledger or a local run')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--ledger')
    g.add_argument('--run', help='results/<label> directory written by bench/run.py')
    p.add_argument('--tasks-root', default=os.path.join(ROOT, 'tasks', 'desk'))
    p.add_argument('--model', default=os.path.join(DEFAULT_OUT, 'model.json'))
    p.add_argument('--meta', default=None, help='metamorphic cache for the ranking view '
                   '(default for --ledger: docs/triage/metamorphic-frozen.json)')
    p.add_argument('--no-artifacts', action='store_true', help='--run: skip the artifact layer')
    p.add_argument('--out', default=os.path.join(ROOT, 'results', 'triage'))
    p.add_argument('--top', type=int, default=None, help='rows in queue.md (default: all)')
    p.add_argument('--show', type=int, default=10)
    a = ap.parse_args(argv)
    if a.cmd == 'metamorphic':
        return cmd_metamorphic(a)
    if a.cmd == 'fit':
        return cmd_fit(a)
    if a.meta is None and a.ledger:
        a.meta = os.path.join(DEFAULT_OUT, 'metamorphic-frozen.json')
    return cmd_rank(a)


if __name__ == '__main__':
    sys.exit(main())
