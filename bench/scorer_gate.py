#!/usr/bin/env python3
"""Scorer-change gate: show exactly which verdicts a proposed scorer change moves, blind to system identity.

    scorer_gate.py [--base SPEC] [--candidate SPEC] [--tasks a,b | --all | --sample N]
                   [--artifacts DIR] [--corpus-ref REF] [--kinds K,..] [--out DIR]

A scorer SPEC is one of
    frozen:scoring/frozen-v7   the frozen release package (its scorer.py and its own task definitions)
    git:<ref>                  bench/grade.py and tasks/ as committed at <ref> (read with `git archive`)
    worktree                   bench/grade.py and tasks/ as they are on disk now (snapshotted first)

Two things are scored under both scorers:

1. A control corpus with known expected outcomes, built on the fly in a temp dir from --corpus-ref
   (default HEAD, so concurrent edits to generators cannot move it mid-run):
     reference   the task's reference_solution/                      expected PASS
     empty       an empty directory                                   expected FAIL
     untouched   the task's workspace/ as handed to the agent         expected FAIL
     naive       `gen.py --naive DIR` (generators that support it)    expected FAIL
     mutant      `gen.py --mutant T --out DIR` per declared trap      expected FAIL on every check the trap cites
     metamorphic the reference under transforms bench/metamorphic.py classes invariant for the task
                 (only if that module exists; --max-metamorphic per task, default 2)  expected PASS
   A VIOLATION is a control item whose expectation the base scorer meets and the candidate does not.
   Items the base already gets wrong are listed as pre-existing, not counted against the candidate.

2. Optionally, real attempt artifacts laid out DIR/<system>/<task>/<attempt>/. Every attempt is copied to
   a directory named by an opaque id (assigned after a seeded shuffle), both scorers see only
   (task, opaque workspace) in shuffled order, the blind verdicts are written and hashed, and only then is
   the key joined back to report per-system flip counts. The report records that order.

Exit status: 0 no violations, 1 at least one violation, 2 the gate itself could not run.

Offline tooling: the runner and graders are untouched, git is only read (rev-parse, ls-tree, archive), and
grading runs in subprocesses with bytecode writing disabled so nothing lands in the frozen package.
Cost is one generator run per naive/mutant item and one grade per item per scorer; workbook items pay a
LibreOffice recalculation (~2-5 s) each time, so the default is a 3-task seeded sample, run serially.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Iterable

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from trap_links import trap_links  # noqa: E402

GATE_VERSION = 1
DEFAULT_SAMPLE = 3
DEFAULT_SEED = 20260927
ALL_KINDS = ("reference", "empty", "untouched", "naive", "mutant", "metamorphic")
EXPECT = {"reference": "pass", "empty": "fail", "untouched": "fail", "naive": "fail", "mutant": "fail",
          "metamorphic": "pass"}


# ---------------------------------------------------------------------------------------------------------
# Verdicts. A scorer is any callable (task_id, workspace_dir) -> result, where result is either the grade
# dict the real graders return ({passed, checks: [{name, passed, required}], grader_errors}) or a plain
# {check_name: passed} mapping (stubs); normalise() turns both into one shape.
# ---------------------------------------------------------------------------------------------------------

def normalise(raw) -> dict:
    """{passed: bool|None, checks: {name: bool}, failed_required: [names], ungraded: bool, error: str|None}"""
    if not isinstance(raw, dict):
        return {"passed": None, "checks": {}, "failed_required": [], "ungraded": True,
                "error": f"scorer returned {type(raw).__name__}"}
    if "crash" in raw:
        return {"passed": None, "checks": {}, "failed_required": [], "ungraded": True, "error": raw["crash"]}
    if "checks" in raw and isinstance(raw["checks"], list):
        checks, failed_req, seen = {}, [], {}
        for c in raw["checks"]:
            name = str(c.get("name", c.get("type", "?")))
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                name = f"{name} #{seen[name]}"
            checks[name] = bool(c.get("passed"))
            if c.get("required", True) and not c.get("passed"):
                failed_req.append(name)
        errors = list(raw.get("grader_errors") or [])
        return {"passed": None if errors else bool(raw.get("passed")), "checks": checks,
                "failed_required": failed_req, "ungraded": bool(errors),
                "error": f"grader errors: {errors}" if errors else None}
    checks = {str(k): bool(v) for k, v in raw.items()}
    return {"passed": all(checks.values()) if checks else False, "checks": checks,
            "failed_required": [k for k, v in checks.items() if not v], "ungraded": False, "error": None}


class Scorer:
    """Wraps a callable scorer. `score_many` exists so subprocess scorers can batch; stubs just loop."""

    def __init__(self, fn: Callable[[str, str], object], label: str = "stub", fingerprint: dict | None = None):
        self.fn, self.label, self.fingerprint = fn, label, fingerprint or {"kind": "stub"}

    def __call__(self, task_id: str, ws: str) -> dict:
        return normalise(self.fn(task_id, ws))

    def score_many(self, items: list[tuple[str, str]]) -> list[dict]:
        out = []
        for t, ws in items:
            try:
                out.append(self(t, ws))
            except Exception as e:  # a crashing scorer is an ungraded item, never a crashed gate
                out.append(normalise({"crash": f"{type(e).__name__}: {e}"}))
        return out


# The grading driver runs in its own interpreter per scorer so two graders (both import a module named
# `grade`, and task check.py files `import grade`) never share module state.
_DRIVER = r'''
import contextlib, importlib.util, json, os, sys
mode, root = sys.argv[1], sys.argv[2]
out = sys.stdout
if mode == "frozen":
    spec = importlib.util.spec_from_file_location("frozen_gate_scorer", os.path.join(root, "scorer.py"))
    m = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(m)
    fn = lambda t, ws: m.grade(t, ws)
else:
    sys.path.insert(0, os.path.join(root, "bench"))
    with contextlib.redirect_stdout(sys.stderr):
        import grade as g
    fn = lambda t, ws: g.grade(os.path.join(root, "tasks", "desk", t), ws)
for line in sys.stdin:
    it = json.loads(line)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            r = fn(it["task"], it["ws"])
    except BaseException as e:
        r = {"crash": f"{type(e).__name__}: {e}"}
    out.write(json.dumps({"i": it["i"], "result": r}, default=str) + "\n"); out.flush()
'''


class SubprocessScorer(Scorer):
    def __init__(self, mode: str, root: str, label: str, fingerprint: dict, timeout_per_item: int = 600):
        super().__init__(lambda t, ws: None, label, fingerprint)
        self.mode, self.root, self.timeout_per_item = mode, root, timeout_per_item

    def __call__(self, task_id, ws):
        return self.score_many([(task_id, ws)])[0]

    def score_many(self, items):
        if not items:
            return []
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TQDM_DISABLE="1")
        payload = "".join(json.dumps({"i": i, "task": t, "ws": ws}) + "\n" for i, (t, ws) in enumerate(items))
        try:
            r = subprocess.run([sys.executable, "-c", _DRIVER, self.mode, self.root], input=payload,
                               capture_output=True, text=True, cwd=self.root, env=env,
                               timeout=self.timeout_per_item * len(items))
            stdout, stderr = r.stdout, r.stderr
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = "timeout"
        got = {}
        for line in stdout.splitlines():
            try:
                rec = json.loads(line)
                got[rec["i"]] = normalise(rec["result"])
            except (ValueError, KeyError):
                continue
        return [got.get(i) or normalise({"crash": f"no result from {self.label} driver: {stderr.strip()[-300:]}"})
                for i in range(len(items))]


# ---------------------------------------------------------------------------------------------------------
# Scorer specs and task trees (read-only git)
# ---------------------------------------------------------------------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", REPO, *args], check=True, capture_output=True, text=True).stdout


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tree_digest(root: str, rels: Iterable[str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(rels):
        p = os.path.join(root, rel)
        files = [p] if os.path.isfile(p) else sorted(
            os.path.join(d, f) for d, ds, fs in os.walk(p) for f in fs
            if "__pycache__" not in d and not f.endswith(".pyc"))
        for fp in files:
            h.update(os.path.relpath(fp, root).encode() + b"\0" + _sha(fp).encode() + b"\n")
    return h.hexdigest()


def task_definition_digests(desk: str, tasks: list[str]) -> dict[str, str | None]:
    """Per task, a digest of what defines its answer to a scorer: task.yaml, reference/ and task-local check
    modules (every .py except gen.py). Two scorers with different digests for a task are not only running
    different scorer code; the task itself (expected values, check list) moved."""
    out = {}
    for t in tasks:
        td = os.path.join(desk, t)
        if not os.path.isfile(os.path.join(td, "task.yaml")):
            out[t] = None
            continue
        rels = ["task.yaml"] + (["reference"] if os.path.isdir(os.path.join(td, "reference")) else []) + sorted(
            f for f in os.listdir(td) if f.endswith(".py") and f != "gen.py")
        out[t] = tree_digest(td, rels)
    return out


def materialise_tree(source: str, tasks: list[str], dest: str) -> tuple[str, dict]:
    """Copy bench/, tasks/lib and the named desk tasks from `source` ('worktree' or a git ref) into dest.
    Returns (root, provenance). Tasks absent from the source are skipped and listed."""
    os.makedirs(dest, exist_ok=True)
    prov: dict = {"source": source}
    if source == "worktree":
        present = [t for t in tasks if os.path.isfile(os.path.join(REPO, "tasks", "desk", t, "task.yaml"))]
        ign = shutil.ignore_patterns("__pycache__", "*.pyc")
        shutil.copytree(os.path.join(REPO, "bench"), os.path.join(dest, "bench"), ignore=ign)
        shutil.copytree(os.path.join(REPO, "tasks", "lib"), os.path.join(dest, "tasks", "lib"), ignore=ign)
        for t in present:
            shutil.copytree(os.path.join(REPO, "tasks", "desk", t), os.path.join(dest, "tasks", "desk", t), ignore=ign)
        try:
            prov["head"] = _git("rev-parse", "HEAD").strip()
            dirty = _git("status", "--porcelain", "--", "bench/grade.py", *[f"tasks/desk/{t}" for t in present])
            prov["dirty_paths"] = [l[3:] for l in dirty.splitlines()]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    else:
        commit = _git("rev-parse", "--verify", f"{source}^{{commit}}").strip()
        have = set(_git("ls-tree", "-d", "--name-only", commit, "tasks/desk/").split())
        present = [t for t in tasks if f"tasks/desk/{t}" in have]
        paths = ["bench", "tasks/lib"] + [f"tasks/desk/{t}" for t in present]
        arch = subprocess.run(["git", "-C", REPO, "archive", "--format=tar", commit, *paths],
                              check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", dest], input=arch, check=True)
        prov["commit"] = commit
    prov["tasks_missing"] = sorted(set(tasks) - set(present))
    prov["digest"] = tree_digest(dest, ["bench/grade.py"] + [f"tasks/desk/{t}" for t in present])
    return dest, prov


def verify_frozen(root: str, tasks: list[str]) -> dict:
    manifest_path = os.path.join(root, "manifest.json")
    manifest = json.load(open(manifest_path))
    wanted = [p for p in manifest["files"]
              if not p.startswith("tasks/") or any(p.startswith(f"tasks/desk/{t}/") for t in tasks)]
    bad = [p for p in wanted if not os.path.isfile(os.path.join(root, p))
           or _sha(os.path.join(root, p)) != manifest["files"][p]]
    return {"kind": "frozen", "root": os.path.relpath(root, REPO), "manifest_sha256": _sha(manifest_path),
            "files_verified": len(wanted) - len(bad), "files_mismatched": bad,
            "tasks_missing": [t for t in tasks if not os.path.isdir(os.path.join(root, "tasks", "desk", t))]}


def make_scorer(spec: str, tasks: list[str], work: str) -> Scorer:
    if spec.startswith("frozen:"):
        root = os.path.abspath(os.path.join(REPO, spec.split(":", 1)[1]))
        if not os.path.isfile(os.path.join(root, "scorer.py")):
            raise SystemExit(f"{spec}: no scorer.py under {root}")
        fp = verify_frozen(root, tasks)
        fp["task_digests"] = task_definition_digests(os.path.join(root, "tasks", "desk"), tasks)
        return SubprocessScorer("frozen", root, spec, fp)
    if spec == "worktree" or spec.startswith("git:"):
        src = "worktree" if spec == "worktree" else spec.split(":", 1)[1]
        root, prov = materialise_tree(src, tasks, os.path.join(work, "scorer-" + re.sub(r"\W+", "_", spec)))
        prov["task_digests"] = task_definition_digests(os.path.join(root, "tasks", "desk"), tasks)
        return SubprocessScorer("tree", root, spec, {"kind": "tree", **prov})
    raise SystemExit(f"unknown scorer spec {spec!r}: use frozen:<dir>, git:<ref> or worktree")


# ---------------------------------------------------------------------------------------------------------
# Control corpus
# ---------------------------------------------------------------------------------------------------------

@dataclass
class ControlItem:
    id: str
    task: str
    kind: str
    ws: str
    expect: str                      # 'pass' | 'fail'
    cited: list[str] = field(default_factory=list)   # mutants: checks that must fail
    note: str = ""


def _run_gen(task_dir: str, *args: str, timeout: int = 600) -> str:
    r = subprocess.run([sys.executable, os.path.join(task_dir, "gen.py"), *args], capture_output=True, text=True,
                       cwd=task_dir, timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if r.returncode != 0:
        raise RuntimeError(f"gen.py {' '.join(args)} failed: {r.stderr.strip()[-400:]}")
    return r.stdout


def _metamorphic_variants(task_dir: str, task: dict, out: str, limit: int) -> tuple[list[tuple[str, str]], str]:
    """(name, workspace) pairs: the reference solution under transforms bench/metamorphic.py classes as
    INVARIANT for this task (correct work must stay correct). Import-guarded: the module is optional and
    its interface may still be settling, so any mismatch skips the kind with a note instead of failing.
    Non-workbook transforms go first because each workbook variant costs a recalculation per scorer."""
    sol = os.path.join(task_dir, "reference_solution")
    if limit <= 0 or not os.path.isdir(sol):
        return [], ""
    try:
        import importlib
        try:
            mm = importlib.import_module("metamorphic")
        except ModuleNotFoundError as e:
            if e.name == "metamorphic":
                return [], ""          # module not present: the kind is simply unavailable
            raise
        transforms, classify, apply_transform = mm.TRANSFORMS, mm.classify, mm.apply_transform
        invariant, files = mm.INVARIANT, mm.deliverables(sol)
    except Exception as e:
        return [], f"metamorphic variants skipped ({type(e).__name__}: {e})"
    sources = {}
    for c in task.get("checks") or []:
        if c.get("type") in ("custom", "plan_feasible"):
            mod = c.get("module", "check.py" if c["type"] == "custom" else "plan_check.py")
            if os.path.isfile(os.path.join(task_dir, mod)):
                sources[mod] = open(os.path.join(task_dir, mod), encoding="utf-8", errors="replace").read()
    pairs = []
    try:
        for name in sorted(transforms, key=lambda n: (transforms[n].kind == "xlsx", n)):
            if len(pairs) >= limit:
                break
            if transforms[name].kind == "workspace":
                continue
            ws = os.path.join(out, name)
            changed = apply_transform(name, sol, ws, files)
            if not changed or any(classify(name, task, rel, sources)[0] != invariant for rel in changed):
                shutil.rmtree(ws, ignore_errors=True)
                continue
            pairs.append((name, ws))
    except Exception as e:
        return pairs, f"metamorphic variants stopped early ({type(e).__name__}: {e})"
    return pairs, ""


def build_controls(src_root: str, tasks: list[str], work: str, kinds: Iterable[str],
                   max_metamorphic: int = 2) -> tuple[list[ControlItem], list[str]]:
    kinds, items, problems = set(kinds), [], []
    for t in tasks:
        td = os.path.join(src_root, "tasks", "desk", t)
        if not os.path.isfile(os.path.join(td, "task.yaml")):
            problems.append(f"{t}: not in corpus source")
            continue
        task = yaml.safe_load(open(os.path.join(td, "task.yaml"))) or {}
        seed = task.get("generator_seed")
        seed_args = ["--seed", str(seed)] if seed is not None else []
        base = os.path.join(work, "controls", t)
        os.makedirs(base, exist_ok=True)
        gen_src = open(os.path.join(td, "gen.py")).read() if os.path.isfile(os.path.join(td, "gen.py")) else ""

        def add(kind, ws, **kw):
            items.append(ControlItem(f"{t}/{kind}" + (f":{kw.pop('suffix')}" if "suffix" in kw else ""),
                                     t, kind, ws, EXPECT[kind], **kw))

        if "reference" in kinds:
            if os.path.isdir(os.path.join(td, "reference_solution")):
                add("reference", os.path.join(td, "reference_solution"))
            else:
                problems.append(f"{t}: no reference_solution/")
        if "empty" in kinds:
            os.makedirs(os.path.join(base, "empty"), exist_ok=True)
            add("empty", os.path.join(base, "empty"))
        if "untouched" in kinds and os.path.isdir(os.path.join(td, "workspace")):
            add("untouched", os.path.join(td, "workspace"))
        if "naive" in kinds and "--naive" in gen_src:
            out = os.path.join(base, "naive")
            os.makedirs(out, exist_ok=True)
            try:
                _run_gen(td, *seed_args, "--naive", out)
                if any(fs for _, _, fs in os.walk(out)):
                    add("naive", out)
                else:
                    problems.append(f"{t}: gen.py --naive wrote nothing")
            except Exception as e:
                problems.append(f"{t}: naive: {e}")
        if "mutant" in kinds and ("add_trap_args" in gen_src or "--list-traps" in gen_src):
            try:
                decl = json.loads(_run_gen(td, "--list-traps"))
            except Exception as e:
                problems.append(f"{t}: --list-traps: {e}")
                decl = {}
            try:
                links = trap_links(task)
            except Exception as e:
                problems.append(f"{t}: trap sentences unreadable ({e}); mutant expectations fall back to overall FAIL")
                links = []
            keys = decl.get("sentence_keys") or []
            cites: dict[str, list[str]] = {}
            if decl and len(keys) != len(links):
                problems.append(f"{t}: {len(keys)} trap keys for {len(links)} trap sentences; cited checks unknown")
            else:
                for k, link in zip(keys, links):
                    for c in link["cites"]:
                        if c["status"] == "ok" and c["check"] not in cites.setdefault(k, []):
                            cites[k].append(c["check"])
            for trap in decl.get("mutants", []):
                out = os.path.join(base, "mutant-" + trap)
                try:
                    _run_gen(td, *seed_args, "--mutant", trap, "--out", out)
                    add("mutant", out, suffix=trap, cited=sorted(cites.get(trap, [])),
                        note="" if cites.get(trap) else "trap cites no check: expectation is overall FAIL")
                except Exception as e:
                    problems.append(f"{t}: mutant {trap}: {e}")
        if "metamorphic" in kinds:
            pairs, note = _metamorphic_variants(td, task, os.path.join(base, "metamorphic"), max_metamorphic)
            if note:
                problems.append(f"{t}: {note}")
            for name, ws in pairs:
                add("metamorphic", ws, suffix=name)
    return items, problems


def meets(item: ControlItem, v: dict) -> tuple[bool | None, str]:
    """Does verdict v meet the item's expectation? None when ungraded."""
    if v["ungraded"]:
        return None, "ungraded: " + (v["error"] or "")
    if item.expect == "pass":
        return bool(v["passed"]), "" if v["passed"] else f"failed {v['failed_required']}"
    if v["passed"]:
        return False, "passes overall"
    missing = [c for c in item.cited if c not in v["checks"]]
    passing = [c for c in item.cited if v["checks"].get(c)]
    if missing:
        return False, f"cited check(s) absent: {missing}"
    if passing:
        return False, f"cited check(s) pass: {passing}"
    return True, ""


def check_flips(b: dict, c: dict) -> list[dict]:
    out = []
    for name in sorted(set(b["checks"]) | set(c["checks"])):
        bv, cv = b["checks"].get(name), c["checks"].get(name)
        if bv != cv:
            out.append({"check": name, "base": bv, "candidate": cv})
    return out


def _word(v: dict) -> str:
    return "UNGRADED" if v["ungraded"] else ("PASS" if v["passed"] else "FAIL")


def definitions_changed(base: Scorer, cand: Scorer) -> list[str]:
    b, c = base.fingerprint.get("task_digests") or {}, cand.fingerprint.get("task_digests") or {}
    return sorted(t for t in set(b) & set(c) if b[t] != c[t])


def evaluate_controls(items: list[ControlItem], base: Scorer, cand: Scorer) -> dict:
    changed = set(definitions_changed(base, cand))
    pairs = [(i.task, i.ws) for i in items]
    bv, cv = base.score_many(pairs), cand.score_many(pairs)
    rows, flips, violations, preexisting = [], [], [], []
    for it, b, c in zip(items, bv, cv):
        bm, bwhy = meets(it, b)
        cm, cwhy = meets(it, c)
        row = {"id": it.id, "task": it.task, "kind": it.kind, "expect": it.expect.upper(), "cited": it.cited,
               "base": _word(b), "candidate": _word(c), "base_meets": bm, "candidate_meets": cm,
               "base_why": bwhy, "candidate_why": cwhy, "check_flips": check_flips(b, c), "note": it.note,
               "base_failed": b["failed_required"], "candidate_failed": c["failed_required"],
               "task_definition_changed": it.task in changed}
        row["violation"] = bm is True and cm is not True
        rows.append(row)
        if row["base"] != row["candidate"] or row["check_flips"]:
            flips.append({k: row[k] for k in ("id", "base", "candidate", "check_flips", "task_definition_changed")})
        if row["violation"]:
            violations.append({"id": it.id, "expect": row["expect"], "base": row["base"],
                               "candidate": row["candidate"], "why": cwhy,
                               "task_definition_changed": row["task_definition_changed"]})
        if bm is not True:
            preexisting.append({"id": it.id, "expect": row["expect"], "base": row["base"], "why": bwhy,
                                "candidate_meets": cm})
    return {"items": rows, "flips": flips, "violations": violations, "preexisting": preexisting,
            "task_definition_changed": sorted(changed)}


# ---------------------------------------------------------------------------------------------------------
# Blind artifact scoring
# ---------------------------------------------------------------------------------------------------------

def discover_artifacts(root: str, tasks: set[str] | None) -> list[dict]:
    """DIR/<system>/<task>/<attempt>/ -> [{system, task, attempt, path}]"""
    out = []
    for system in sorted(os.listdir(root)):
        sd = os.path.join(root, system)
        if not os.path.isdir(sd) or system.startswith("."):
            continue
        for task in sorted(os.listdir(sd)):
            if tasks is not None and task not in tasks:
                continue
            td = os.path.join(sd, task)
            if not os.path.isdir(td):
                continue
            for attempt in sorted(os.listdir(td)):
                if os.path.isdir(os.path.join(td, attempt)):
                    out.append({"system": system, "task": task, "attempt": attempt,
                                "path": os.path.join(td, attempt)})
    return out


class BlindLedger:
    """Seals attempts behind opaque ids. The scorers only ever receive (task, sealed copy); the key that maps an
    id back to its system is held here and released by `reveal`, which refuses until every sealed id has a
    verdict under both scorers."""

    def __init__(self, attempts: list[dict], work: str, seed: int = DEFAULT_SEED):
        order = list(range(len(attempts)))
        random.Random(seed).shuffle(order)
        self.seed, self._key, self.items = seed, {}, []
        width = max(4, len(str(len(attempts))))
        sealed_root = tempfile.mkdtemp(prefix="sealed-", dir=work)
        for n, idx in enumerate(order):
            a = attempts[idx]
            oid = f"x{n:0{width}d}"
            ws = os.path.join(sealed_root, oid)
            shutil.copytree(a["path"], ws, symlinks=False)
            self._key[oid] = {"system": a["system"], "task": a["task"], "attempt": a["attempt"]}
            self.items.append({"id": oid, "task": a["task"], "ws": ws})
        self.revealed = False

    def key_digest(self) -> str:
        return hashlib.sha256(json.dumps(self._key, sort_keys=True).encode()).hexdigest()

    def reveal(self, verdicts: dict[str, dict]) -> dict[str, dict]:
        missing = [i["id"] for i in self.items if i["id"] not in verdicts
                   or "base" not in verdicts[i["id"]] or "candidate" not in verdicts[i["id"]]]
        if missing:
            raise RuntimeError(f"refusing to reveal labels: {len(missing)} sealed attempts have no verdict yet")
        self.revealed = True
        return dict(self._key)


def score_blind(ledger: BlindLedger, base: Scorer, cand: Scorer, out_dir: str | None = None) -> dict:
    changed = set(definitions_changed(base, cand))
    pairs = [(i["task"], i["ws"]) for i in ledger.items]          # shuffled order; no labels
    bv, cv = base.score_many(pairs), cand.score_many(pairs)
    verdicts = {i["id"]: {"task": i["task"], "base": b, "candidate": c}
                for i, b, c in zip(ledger.items, bv, cv)}
    blob = json.dumps(verdicts, sort_keys=True).encode()
    scored_at = _now()
    if out_dir:
        with open(os.path.join(out_dir, "blind_verdicts.json"), "wb") as f:
            f.write(blob)
    # ---- only now are the labels joined back ----
    key = ledger.reveal(verdicts)
    joined_at = _now()
    per_system: dict[str, dict] = {}
    flips = []
    for oid, v in verdicts.items():
        k = key[oid]
        s = per_system.setdefault(k["system"], {"attempts": 0, "base_pass": 0, "candidate_pass": 0,
                                                "fail_to_pass": 0, "pass_to_fail": 0, "ungraded": 0})
        s["attempts"] += 1
        b, c = v["base"], v["candidate"]
        if b["ungraded"] or c["ungraded"]:
            s["ungraded"] += 1
            continue
        s["base_pass"] += bool(b["passed"])
        s["candidate_pass"] += bool(c["passed"])
        if b["passed"] != c["passed"]:
            s["fail_to_pass" if c["passed"] else "pass_to_fail"] += 1
            flips.append({"id": oid, **k, "base": _word(b), "candidate": _word(c),
                          "check_flips": check_flips(b, c), "task_definition_changed": k["task"] in changed})
    if out_dir:
        with open(os.path.join(out_dir, "blinding_key.json"), "w") as f:
            json.dump(key, f, indent=2, sort_keys=True)
    return {"attempts": len(verdicts), "per_system": per_system,
            "flips": sorted(flips, key=lambda f: (f["system"], f["task"], f["attempt"])),
            "blinding": {"seed": ledger.seed, "labels_joined_after_scoring": True,
                         "scorer_inputs": "task id and a copy of the workspace under an opaque id, shuffled order",
                         "blind_verdicts_sha256": hashlib.sha256(blob).hexdigest(),
                         "key_sha256": ledger.key_digest(), "verdicts_complete_at": scored_at,
                         "labels_joined_at": joined_at,
                         "limit": "file contents can still betray a system (e.g. its scratch scripts); "
                                  "blinding removes paths, names and order, not content"}}


# ---------------------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------------------

def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def render_markdown(rep: dict) -> str:
    L = [f"# Scorer gate: {rep['verdict']}", "",
         f"- base: `{rep['base']['spec']}`  candidate: `{rep['candidate']['spec']}`",
         f"- corpus: `{rep.get('corpus', {}).get('source', '-')}`  tasks ({len(rep.get('tasks', []))}): "
         f"{', '.join(rep.get('tasks', []))}",
         f"- control items: {len(rep['controls']['items'])}; flips: {len(rep['controls']['flips'])}; "
         f"violations: {len(rep['controls']['violations'])}; base already wrong: {len(rep['controls']['preexisting'])}",
         ""]
    for side in ("base", "candidate"):
        fp = rep[side]["fingerprint"]
        bits = {k: fp[k] for k in ("manifest_sha256", "files_mismatched", "commit", "head", "digest", "dirty_paths",
                                   "tasks_missing") if k in fp and fp[k] not in (None, [], "")}
        L.append(f"- {side} fingerprint: " + ", ".join(f"{k}={v}" for k, v in bits.items()))
    if rep["controls"].get("task_definition_changed"):
        L += ["", "Task definitions (task.yaml, reference/, check modules) differ between the two scorers for: "
              + ", ".join(rep["controls"]["task_definition_changed"]) + ". Flips on those tasks mix a scorer-code "
              "change with a task change; the control corpus is built from the corpus ref, so its reference "
              "solution can embody an answer only one side expects."]
    L += ["", "## Control corpus", "", "| item | expect | base | candidate | status |", "|---|---|---|---|---|"]
    for r in rep["controls"]["items"]:
        status = ("**VIOLATION** " + r["candidate_why"] if r["violation"] else
                  ("pre-existing: " + r["base_why"] if r["base_meets"] is not True else
                   ("changed checks" if r["check_flips"] else "ok")))
        if r.get("task_definition_changed"):
            status += " (task definition differs)"
        L.append(f"| {r['id']} | {r['expect']} | {r['base']} | {r['candidate']} | {status} |")
    if rep["controls"]["flips"]:
        L += ["", "## Flips on the control corpus", ""]
        for f in rep["controls"]["flips"]:
            cf = "; ".join(f"{x['check']}: {x['base']} -> {x['candidate']}" for x in f["check_flips"])
            L.append(f"- {f['id']}: {f['base']} -> {f['candidate']}" + (f" ({cf})" if cf else "")
                     + (" [task definition differs]" if f.get("task_definition_changed") else ""))
    if rep["controls"]["violations"]:
        L += ["", "## Violations (candidate breaks an expectation the base met)", ""]
        L += [f"- {v['id']}: expected {v['expect']}, base {v['base']}, candidate {v['candidate']}: {v['why']}"
              for v in rep["controls"]["violations"]]
    if rep.get("corpus", {}).get("problems"):
        L += ["", "## Corpus problems", ""] + [f"- {p}" for p in rep["corpus"]["problems"]]
    art = rep.get("artifacts")
    if art:
        b = art["blinding"]
        L += ["", "## Real attempts (scored blind)", "",
              f"{art['attempts']} attempts were scored under both scorers as opaque ids in shuffled order (seed "
              f"{b['seed']}); blind verdicts sha256 `{b['blind_verdicts_sha256'][:16]}...` were fixed at "
              f"{b['verdicts_complete_at']}, and system labels were joined afterwards at {b['labels_joined_at']}.",
              "", "| system | attempts | base pass | candidate pass | fail->pass | pass->fail | ungraded |",
              "|---|---|---|---|---|---|---|"]
        for s, v in sorted(art["per_system"].items()):
            L.append(f"| {s} | {v['attempts']} | {v['base_pass']} | {v['candidate_pass']} | {v['fail_to_pass']} | "
                     f"{v['pass_to_fail']} | {v['ungraded']} |")
        if art["flips"]:
            L += ["", "Flipped attempts (labels joined after scoring):", ""]
            for f in art["flips"][:100]:
                cf = "; ".join(f"{x['check']}: {x['base']} -> {x['candidate']}" for x in f["check_flips"])
                L.append(f"- {f['system']} / {f['task']} / {f['attempt']} ({f['id']}): {f['base']} -> {f['candidate']}"
                         + (f" ({cf})" if cf else "") + (" [task definition differs]" if f["task_definition_changed"] else ""))
            if len(art["flips"]) > 100:
                L.append(f"- ... {len(art['flips']) - 100} more in gate.json")
        L += ["", f"Limit: {b['limit']}."]
    L += ["", f"Exit status {rep['exit_code']}. Generated {rep['created_utc']} by bench/scorer_gate.py v{GATE_VERSION}."]
    return "\n".join(L) + "\n"


def choose_tasks(universe: list[str], tasks: str | None, all_: bool, sample: int | None, seed: int) -> list[str]:
    if tasks:
        want = [t.strip() for t in tasks.split(",") if t.strip()]
        unknown = [t for t in want if t not in universe]
        if unknown:
            raise SystemExit(f"unknown task(s): {unknown}")
        return want
    if all_:
        return list(universe)
    n = sample if sample is not None else DEFAULT_SAMPLE
    return sorted(random.Random(seed).sample(universe, min(n, len(universe))))


def run_gate(base: Scorer, cand: Scorer, controls: list[ControlItem], *, artifacts: list[dict] | None = None,
             work: str, out_dir: str | None = None, seed: int = DEFAULT_SEED, meta: dict | None = None) -> dict:
    ctl = evaluate_controls(controls, base, cand)
    rep = {"gate_version": GATE_VERSION, "created_utc": _now(),
           "base": {"spec": base.label, "fingerprint": base.fingerprint},
           "candidate": {"spec": cand.label, "fingerprint": cand.fingerprint},
           **(meta or {}), "controls": ctl}
    if artifacts:
        rep["artifacts"] = score_blind(BlindLedger(artifacts, work, seed), base, cand, out_dir)
    rep["exit_code"] = 1 if ctl["violations"] else 0
    rep["verdict"] = "FAIL (violations)" if ctl["violations"] else "PASS (no violations)"
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="frozen:scoring/frozen-v7")
    ap.add_argument("--candidate", default="worktree")
    sel = ap.add_mutually_exclusive_group()
    sel.add_argument("--tasks", help="comma-separated task ids")
    sel.add_argument("--all", action="store_true", help="every task (slow: minutes to hours)")
    sel.add_argument("--sample", type=int, help=f"seeded sample of N tasks (default {DEFAULT_SAMPLE})")
    ap.add_argument("--artifacts", help="DIR/<system>/<task>/<attempt>/ workspaces to score blind")
    ap.add_argument("--corpus-ref", default="HEAD", help="git ref, or 'worktree', to build the control corpus from")
    ap.add_argument("--kinds", default=",".join(ALL_KINDS), help="control kinds to build")
    ap.add_argument("--max-metamorphic", type=int, default=2,
                    help="invariant metamorphic variants per task (default 2; 0 disables)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="task sample and blinding shuffle seed")
    ap.add_argument("--out", help="report directory (default results/scorer-gate/<utc stamp>, git-ignored)")
    ap.add_argument("--keep-work", action="store_true", help="keep the temp dir with corpus and snapshots")
    a = ap.parse_args(argv)

    kinds = [k.strip() for k in a.kinds.split(",") if k.strip()]
    if set(kinds) - set(ALL_KINDS):
        ap.error(f"unknown kinds {sorted(set(kinds) - set(ALL_KINDS))}; choose from {ALL_KINDS}")
    attempts = discover_artifacts(a.artifacts, None) if a.artifacts else None
    if a.artifacts and not attempts:
        ap.error(f"no attempts found under {a.artifacts} (layout DIR/<system>/<task>/<attempt>/)")
    universe = sorted({x["task"] for x in attempts}) if attempts else sorted(
        d for d in os.listdir(os.path.join(REPO, "tasks", "desk"))
        if os.path.isfile(os.path.join(REPO, "tasks", "desk", d, "task.yaml")))
    tasks = choose_tasks(universe, a.tasks, a.all, a.sample, a.seed)
    if attempts:
        attempts = [x for x in attempts if x["task"] in set(tasks)]

    out_dir = a.out or os.path.join(REPO, "results", "scorer-gate", _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="scorer-gate-")
    try:
        try:
            base = make_scorer(a.base, tasks, work)
            cand = make_scorer(a.candidate, tasks, work)
            src, corpus_prov = materialise_tree(a.corpus_ref, tasks, os.path.join(work, "corpus-src"))
        except subprocess.CalledProcessError as e:
            print(f"git failed: {e.stderr}", file=sys.stderr)
            return 2
        print(f"scorer gate: {a.base} vs {a.candidate}; corpus {a.corpus_ref}; tasks {', '.join(tasks)}", file=sys.stderr)
        for side in (base, cand):
            if side.fingerprint.get("files_mismatched"):
                print(f"  ! {side.label}: frozen files do not match manifest: {side.fingerprint['files_mismatched']}",
                      file=sys.stderr)
        controls, problems = build_controls(src, tasks, work, kinds, a.max_metamorphic)
        print(f"  {len(controls)} control items built; scoring under both scorers...", file=sys.stderr)
        meta = {"tasks": tasks, "corpus": {"source": a.corpus_ref, "provenance": corpus_prov, "kinds": kinds,
                                           "problems": problems},
                "selection": {"max_metamorphic": a.max_metamorphic, "tasks": a.tasks, "all": a.all, "sample": a.sample, "seed": a.seed}}
        rep = run_gate(base, cand, controls, artifacts=attempts, work=work, out_dir=out_dir, seed=a.seed, meta=meta)
    finally:
        if a.keep_work:
            print(f"  work dir kept: {work}", file=sys.stderr)
        else:
            shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(out_dir, "gate.json"), "w") as f:
        json.dump(rep, f, indent=2, default=str)
    md = render_markdown(rep)
    with open(os.path.join(out_dir, "gate.md"), "w") as f:
        f.write(md)
    print(md)
    print(f"report: {os.path.relpath(out_dir, REPO) if out_dir.startswith(REPO) else out_dir}/gate.{{json,md}}",
          file=sys.stderr)
    return rep["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
