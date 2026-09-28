#!/usr/bin/env python3
"""Renewable benchmark: find saturated desk tasks, search generator settings for harder ones, and generate sealed
variants at matched predicted difficulty.

    renew.py saturation [--ledger L] [--near-max-fails 1] [--json OUT]
    renew.py search  --task project-margin --root DIR [--seeds default,1,2,3,4] [--design single]
                     [--knob NAME=V1,V2 ...] [--tol 0.10]
    renew.py seal    --task project-margin [--task T2 ...] --root DIR --n 3 [--tol 0.10] [--seeds S1,S2,...]
    renew.py check   --manifest DIR/manifest.json
    (then)   bench/envelope.py register DIR/predictions/<task>.json --registry <committed path>
             bench/run.py --tasks-root DIR --tasks all ...
             bench/envelope.py score --predictions DIR/predictions/<task>.json --results results/<label> --registry ...

Saturation (from the published ledger). A task is SATURATED when every attempt in the ledger passed, i.e. no
required check failed in any attempt of any system. It is NEAR-SATURATED when it is not saturated but at most
`--near-max-fails` attempts (default 1) failed. The rest are informative (some pass, some fail) or never passed.

Settings. A setting is (seed, switchable traps off, knob values). Seeds work on every generator: retrofitted ones
write to --out; the others are run from a private copy of the task folder (a "shadow" copy, with tasks/lib linked)
so the published folder is never written. Trap switches come from `gen.py --list-traps`. Knobs are any other
flag a generator's --help lists; `--knob` refuses a flag the generator does not have. No generator exposes a
size / rule / noise knob today (docs/renewable.md lists the ones that would help).

Predicted difficulty of a setting, relative to the canonical setting (published seed, every trap on), in logits,
positive = harder:

    delta = sum_k w_k (x_k(setting) - x_k(canonical))  -  sum_{j switched off} e_j

w_k are bench/difficulty.py's task-feature weights (LLTM fit on the ledger; task-clustered bootstrap draws) over
every feature except the between-task trap count; e_j ~ Normal(0.5, 1.0) is the per-trap effect prior
bench/envelope.py uses before any variant has been run. Removing a pitfall never adds one (authoring rule 6), so a
setting with a trap off is never proposed as harder, whatever the model says. Per system s,

    P(pass) = sigmoid(logit p_s - delta),   p_s ~ Beta(passes + 0.5, fails + 0.5) on the published task

and predictions are written in envelope.py's predictions format, so `envelope.py register` and `score` work on them
unchanged.

Sealed variants are written under --root (never under tasks/): one folder per accepted setting, a private
manifest.json (task, seed, settings, predicted difficulty, content hashes, verification, nonce) and a public
commitments.json (one hash per variant, plus the manifest hash) that can be published now and opened later.
Every accepted variant's reference solution passes its own checks and its untouched workspace fails them, graded by
bench/grade.py; without LibreOffice a workbook failure that the canonical task shows too is recorded as
"UNVERIFIED-XLSX (env)", not as a defect.

Offline, opt-in tooling: nothing here runs during an evaluation; the runner, grader and published task files are
unchanged. READ docs/renewable.md BEFORE QUOTING A PREDICTION: the difficulty model is fitted on two systems.
"""
from __future__ import annotations

import argparse
import collections
import glob
import itertools
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import envelope as env  # noqa: E402
from difficulty import LedgerModel, task_features  # noqa: E402

ROOT = env.ROOT
TASKS = env.TASKS
LEDGER = os.path.join(ROOT, "results", "latest", "attempts.jsonl")
RESERVED = {"help", "seed", "out", "traps-off", "mutant", "list-traps", "naive"}
EXCLUDED_FEATURES = {"traps"}  # between-task correlate, not a within-task effect: trap switches use the prior
XLSX_TYPES = {"xlsx_value_present", "xlsx_no_errors", "xlsx_has_formulas", "custom", "plan_feasible"}
ENV_UNVERIFIED = "UNVERIFIED-XLSX (env)"
SEED_RANGE = (10_000, 4_000_000)  # generators draw build(seed * 1000 + attempt); keep that under 2**32
DRAWS = 4000


def gen_python() -> str:
    return os.environ.get("BENCH_GEN_PYTHON") or sys.executable


# ----------------------------------------------------------------------------------------------- saturation

def ledger_stats(att: list[dict]) -> dict[str, dict]:
    per: dict[str, dict] = {}
    for a in att:
        s = per.setdefault(a["task"], {"n": 0, "passed": 0, "systems": collections.defaultdict(lambda: [0, 0]),
                                       "check_fails": collections.Counter(), "checks": set(),
                                       "category": a.get("category")})
        failed = [c["name"] for c in a.get("checks") or [] if c.get("required", True) and not c["passed"]]
        ok = bool(a["passed"]) and not failed
        s["n"] += 1; s["passed"] += ok
        s["systems"][a["harness"]][0] += ok; s["systems"][a["harness"]][1] += 1
        s["check_fails"].update(failed)
        s["checks"].update(c["name"] for c in a.get("checks") or [] if c.get("required", True))
    return per


def classify(s: dict, near_max_fails: int = 1) -> str:
    fails = s["n"] - s["passed"]
    if s["n"] and fails == 0:
        return "saturated"
    if s["passed"] == 0:
        return "never-passed"
    if fails <= near_max_fails:
        return "near-saturated"
    return "informative"


def renewal_route(task_dir: str) -> str:
    """How new settings can be drawn without touching the published folder (read from the source, nothing run)."""
    g = os.path.join(task_dir, "gen.py")
    if not os.path.isfile(g):
        return "none"
    with open(g) as f:
        src = f.read()
    if "add_trap_args" in src:
        return "switches+seed"
    if re.search(r"""add_argument\(\s*['"]--seed|argparse_seed\(""", src):
        return "seed (shadow copy)"
    return "none"


def saturation_table(ledger: str, tasks_dir: str, near_max_fails: int) -> list[dict]:
    att = [json.loads(l) for l in env.read_lines(ledger)]
    rows = []
    for t, s in sorted(ledger_stats(att).items()):
        rows.append({"task": t, "category": s["category"], "class": classify(s, near_max_fails),
                     "attempts": s["n"], "passed": s["passed"],
                     "systems": {k: {"passed": v[0], "n": v[1]} for k, v in sorted(s["systems"].items())},
                     "checks": len(s["checks"]), "checks_never_failed": len(s["checks"] - set(s["check_fails"])),
                     "route": renewal_route(os.path.join(tasks_dir, t))})
    return rows


def cmd_saturation(a) -> int:
    rows = saturation_table(a.ledger, a.tasks_dir, a.near_max_fails)
    by = collections.Counter(r["class"] for r in rows)
    routes = collections.Counter((r["class"], r["route"]) for r in rows)
    n_att = collections.Counter(r["attempts"] for r in rows)
    L = [f"# Saturation: {len(rows)} tasks in {os.path.relpath(a.ledger, ROOT)} "
         f"(attempts per task: {', '.join(f'{k} x{v}' for k, v in sorted(n_att.items()))})\n",
         "saturated = every attempt passed (no required check failed in any attempt); "
         f"near-saturated = not saturated, at most {a.near_max_fails} failed attempt(s).\n",
         "| class | tasks | switches+seed | seed (shadow copy) | none |", "|---|---|---|---|---|"]
    for c in ("saturated", "near-saturated", "informative", "never-passed"):
        L.append(f"| {c} | {by[c]} | {routes[(c, 'switches+seed')]} | {routes[(c, 'seed (shadow copy)')]} | "
                 f"{routes[(c, 'none')]} |")
    for c in ("saturated", "near-saturated"):
        sw = [r["task"] for r in rows if r["class"] == c and r["route"] == "switches+seed"]
        L.append(f"\n{c} with trap switches ({len(sw)}): {', '.join(sw) or '-'}")
    print("\n".join(L))
    if a.json:
        env.write_json(a.json, {"kind": "renewal-saturation", "ledger": os.path.relpath(a.ledger, ROOT),
                                "ledger_sha256": env.sha_file(a.ledger), "near_max_fails": a.near_max_fails,
                                "counts": dict(by), "tasks": rows})
    return 0


# ----------------------------------------------------------------------------------------------- generation

class Generator:
    """Run one task's generator with existing flags only, writing somewhere other than the published folder."""

    def __init__(self, task: str, tasks_dir: str = TASKS, scratch: str | None = None):
        self.task, self.gen = env.generator_path(task, tasks_dir)
        self.dir = os.path.dirname(self.gen)
        self.route = renewal_route(self.dir)
        if self.route == "none":
            raise SystemExit(f"{self.task}: generator takes no --seed; it cannot be renewed without a new flag")
        self._scratch = scratch or tempfile.mkdtemp(prefix=f"renew-{self.task}-")
        self.decl = env.list_traps(self.gen) if self.route == "switches+seed" else None
        self.flags = self._flags()

    def _shadow(self) -> str:
        """A private copy of the task folder with tasks/lib linked, so a generator without --out writes there."""
        base = os.path.join(self._scratch, "shadow")
        d = os.path.join(base, "tasks", "desk", self.task)
        if os.path.isdir(d):
            shutil.rmtree(d)
        shutil.copytree(self.dir, d, ignore=shutil.ignore_patterns("__pycache__"))
        lib = os.path.join(base, "tasks", "lib")
        if not os.path.exists(lib):
            os.symlink(os.path.join(os.path.dirname(os.path.dirname(self.dir)), "lib"), lib)
        return d

    def _run(self, gen: str, args: list[str], cwd: str) -> None:
        r = subprocess.run([gen_python(), gen, *args], capture_output=True, text=True, cwd=cwd)
        if r.returncode != 0:
            raise RuntimeError(f"{self.task}: gen.py {' '.join(args)} failed:\n{r.stderr[-1500:]}")

    def _flags(self) -> set[str]:
        """Long flags from --help. Run in the shadow copy for a generator that is not known to parse arguments
        before writing (argparse exits on --help first, but the published folder is never the place to find out)."""
        if self.route == "switches+seed":
            gen, cwd = self.gen, self.dir
        else:
            cwd = self._shadow(); gen = os.path.join(cwd, "gen.py")
        r = subprocess.run([gen_python(), gen, "--help"], capture_output=True, text=True, cwd=cwd)
        return set(re.findall(r"--([a-z0-9][a-z0-9-]*)", r.stdout))

    def knobs(self) -> list[str]:
        return sorted(self.flags - RESERVED)

    def generate(self, out: str, seed: int | None = None, off=(), knobs: dict | None = None) -> None:
        args = [] if seed is None else ["--seed", str(seed)]
        for k, v in (knobs or {}).items():
            if k not in self.flags or k in RESERVED:
                raise SystemExit(f"{self.task}: generator has no --{k} knob (knobs: {self.knobs() or 'none'})")
            args += [f"--{k}", str(v)]
        if os.path.isdir(out):
            shutil.rmtree(out)
        if self.route == "switches+seed":
            if off:
                args += ["--traps-off", ",".join(sorted(off))]
            self._run(self.gen, args + ["--out", out], self.dir)
            return
        if off:
            raise SystemExit(f"{self.task}: no trap switches; only seeds and knobs can vary")
        d = self._shadow()
        self._run(os.path.join(d, "gen.py"), args, d)
        shutil.copytree(d, out, ignore=shutil.ignore_patterns("__pycache__", "gen.py"))


def check_root(root: str, tasks_dir: str) -> str:
    root = os.path.abspath(root)
    for protected in (os.path.abspath(tasks_dir), os.path.join(ROOT, "tasks")):
        if os.path.commonpath([root, protected]) == protected:
            raise SystemExit("--root must be outside the published task tree")
    return root


def tracked_risk(root: str) -> str | None:
    """A warning when sealed material would sit where git could pick it up."""
    if os.path.commonpath([root, ROOT]) != ROOT:
        return None
    r = subprocess.run(["git", "-C", ROOT, "check-ignore", "-q", root], capture_output=True)
    return None if r.returncode == 0 else f"{root} is inside the repository and not git-ignored: do not commit it"


def seed_visible(vdir: str, seed: int | None) -> list[str]:
    """Text files that contain the seed literally (a sealed seed should not be readable from its own files)."""
    if seed is None or seed < 1000:
        return []
    hits, pat = [], re.compile(rf"(?<!\d){seed}(?!\d)")
    for p in sorted(glob.glob(os.path.join(vdir, "**", "*"), recursive=True)):
        if os.path.isfile(p) and os.path.splitext(p)[1].lower() in {".yaml", ".yml", ".txt", ".md", ".csv", ".json", ".html"}:
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    if pat.search(f.read()):
                        hits.append(os.path.relpath(p, vdir))
            except OSError:
                pass
    return hits


# ----------------------------------------------------------------------------------------------- prediction

class Predictor:
    """Ledger-anchored difficulty deltas from bench/difficulty.py's task-feature model plus envelope.py's trap prior."""

    def __init__(self, ledger: str, tasks_dir: str, boot: int = 200, seed: int = 0,
                 effect_prior: tuple[float, float] = env.PREDICT_EFFECT_PRIOR):
        self.model = LedgerModel(ledger, tasks_dir, boot=boot, seed=seed)
        S = len(self.model.systems)
        keep = np.array([0.0 if n in EXCLUDED_FEATURES else 1.0 for n in self.model.names])
        self.W = self.model.boot[:, S:] * keep      # bootstrap draws of feature weights
        self.w = self.model.weights * keep          # point estimate
        self.effect_prior = effect_prior
        self.rng = np.random.default_rng(seed)
        att = [json.loads(l) for l in env.read_lines(ledger)]
        self.counts = collections.Counter((x["task"], x["harness"], bool(x["passed"])) for x in att)
        self.systems = self.model.systems
        self._base: dict[tuple[str, str], np.ndarray] = {}

    def features(self, task_dir: str) -> dict:
        return task_features(task_dir)

    def delta(self, feats: dict, canon_feats: dict, n_off: int) -> dict:
        dx = self.model.row(feats) - self.model.row(canon_feats)
        B = self.W @ dx
        draws = B[np.arange(DRAWS) % len(B)]
        if n_off:
            mu, sd = self.effect_prior
            draws = draws - self.rng.normal(mu, sd, size=(DRAWS, n_off)).sum(1)
        est = float(self.w @ dx) - n_off * self.effect_prior[0]
        lo, hi = np.percentile(draws, [5, 95])
        changed = [n for n, v in zip(self.model.names, dx) if abs(v) > 1e-12 and n not in EXCLUDED_FEATURES]
        return {"estimate": round(est, 4), "lo90": round(float(lo), 4), "hi90": round(float(hi), 4),
                "features_changed": changed, "_draws": draws}

    def anchor(self, task: str, system: str) -> tuple[int, int]:
        return self.counts[(task, system, True)], self.counts[(task, system, False)]

    def base(self, task: str, system: str) -> np.ndarray:
        """Logit draws of the system's pass rate on the published task; one set per (task, system), shared by every
        setting so that differences between settings come from delta alone."""
        if (task, system) not in self._base:
            k1, k0 = self.anchor(task, system)
            self._base[(task, system)] = env.logit(self.rng.beta(k1 + 0.5, k0 + 0.5, DRAWS))
        return self._base[(task, system)]

    def cells(self, task: str, vid: str, vdir: str, off: list[str], draws: np.ndarray, systems: list[str], k: int) -> list[dict]:
        out = []
        for s in systems:
            p = env.sigmoid(self.base(task, s) - draws)
            out.append({"system": s, "variant": vid, "dir": vdir, "effective_off": sorted(off),
                        "p_mean": round(float(p.mean()), 6), "p_q": env.quantile_points(p),
                        "passk": round(float((p ** k).mean()), 6)})
        return out

    def predictions_doc(self, task: str, manifest_path: str, systems: list[str], k: int, cells: list[dict],
                        difficulty: list[dict]) -> dict:
        mu, sd = self.effect_prior
        doc = {"kind": "envelope-predictions", "task": task, "manifest_sha256": env.sha_file(manifest_path),
               "created_utc": env.utcnow(), "systems": systems, "k": k,
               "method": "renew: ledger anchor + task-feature delta + trap prior",
               "method_note": (
                   "Per system, the pass rate on the published task (every trap on, published seed) is a Jeffreys "
                   "Beta(passes+0.5, fails+0.5) posterior from the ledger. A setting moves the logit by -delta: delta is "
                   "bench/difficulty.py's task-feature weights (two-system LLTM, task-clustered bootstrap draws; the "
                   "between-task trap-count feature left out) applied to the change in task features from the "
                   f"regenerated canonical, plus a Normal({mu}, {sd}) logit cost for each switchable trap switched off "
                   "(envelope.py's prior). Weak by construction: every feature weight's interval crosses zero."),
               "effect_prior": {"mean": mu, "sd": sd}, "notes": [],
               "evidence": {"records": sum(sum(self.anchor(task, s)) for s in systems),
                            "canonical_counts": {s: dict(zip(("pass", "fail"), self.anchor(task, s))) for s in systems},
                            "sources": [os.path.relpath(LEDGER, ROOT)], "synthetic": False},
               "fitted_params": None,
               "baseline_p": {s: (self.anchor(task, s)[0] + 0.5) / (sum(self.anchor(task, s)) + 1.0) for s in systems},
               "cell_fields": {"p_mean": "predicted probability a single attempt passes",
                               "p_q": f"{env.NQ} equal-mass points of the predictive distribution of that probability",
                               "passk": f"predicted probability that {k} independent repetitions all pass"},
               "difficulty": difficulty, "cells": cells}
        doc["sha256"] = env.content_sha(doc)
        return doc


def public_delta(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ----------------------------------------------------------------------------------------------- verification

def failed(res: dict) -> set[str]:
    return {c["name"] for c in res["checks"] if c["required"] and not c["passed"]}


def verdict(ref_passed: bool, ref_failed: set[str], types: dict[str, str], ws_passed: bool,
            canon_failed: set[str] | None) -> str:
    """VERIFIED, UNVERIFIED-XLSX (env) or a FAIL reason. A reference failure is put down to the environment only when
    every failed check is a workbook (or task-module) check that the published task's own reference also fails here."""
    if ws_passed:
        return "FAIL (untouched workspace passes)"
    if ref_passed:
        return "VERIFIED"
    if canon_failed is not None and ref_failed <= canon_failed and all(types.get(n) in XLSX_TYPES for n in ref_failed):
        return ENV_UNVERIFIED
    return "FAIL (reference solution fails)"


def verify(vdir: str, canon: dict | None) -> dict:
    """Reference solution must pass its checks and the untouched workspace must fail them. `canon` is the in-repo
    grade of the published task's reference solution, used to tell an environment failure from a variant defect."""
    from grade import grade
    ref = grade(vdir, os.path.join(vdir, "reference_solution"))
    ws = grade(vdir, os.path.join(vdir, "workspace"))
    types = {c["name"]: c["type"] for c in ref["checks"]}
    out = {"reference_failed": sorted(failed(ref)), "workspace_failed": sorted(failed(ws)),
           "grader_errors": sorted(set(ref["grader_errors"]) | set(ws["grader_errors"])),
           "status": verdict(ref["passed"], failed(ref), types, ws["passed"],
                             set(canon["failed"]) if canon is not None else None)}
    if out["status"] == ENV_UNVERIFIED:
        out["note"] = ("reference fails only workbook checks that the published task's own reference also fails in "
                       "this environment (no LibreOffice); re-verify with LibreOffice before release")
    return out


def canonical_grade(task_dir: str) -> dict:
    from grade import grade
    r = grade(task_dir, os.path.join(task_dir, "reference_solution"))
    return {"passed": r["passed"], "failed": sorted(failed(r))}


# ----------------------------------------------------------------------------------------------- search

def parse_seeds(s: str) -> list[int | None]:
    return [None if x.strip() in ("default", "") else int(x) for x in s.split(",")]


def parse_knobs(items: list[str]) -> dict[str, list[str]]:
    out = {}
    for it in items or []:
        name, _, vals = it.partition("=")
        if not vals:
            raise SystemExit(f"--knob {it!r}: expected NAME=V1,V2")
        out[name.strip().lstrip("-")] = [v.strip() for v in vals.split(",") if v.strip()]
    return out


def reference_canonical(gen: Generator, work: str) -> tuple[str, dict]:
    """Regenerate the canonical setting (published seed, all traps on) in this environment, and compare it with the
    published files."""
    d = os.path.join(work, "_canonical")
    gen.generate(d)
    got, pub = env.task_hashes(d), env.task_hashes(gen.dir)
    return d, {k: got[k] == pub[k] for k in ("checks", "reference", "reference_solution", "workspace")}


def cmd_search(a) -> int:
    root = check_root(a.root, a.tasks_dir)
    man_path = os.path.join(root, "manifest.json")
    if os.path.exists(man_path) and not a.force:
        raise SystemExit(f"{man_path} exists; pass --force")
    os.makedirs(root, exist_ok=True)
    gen = Generator(a.task, a.tasks_dir, scratch=os.path.join(root, ".scratch"))
    knobs = parse_knobs(a.knob)
    for k in knobs:
        if k not in gen.flags or k in RESERVED:
            raise SystemExit(f"{gen.task}: generator has no --{k} knob (available knobs: {gen.knobs() or 'none'}); "
                             "report it rather than editing the generator")
    offs = env.choose_variants(gen.decl, a.design)[0] if gen.decl and gen.decl.get("switchable") else \
        [{"requested": [], "effective": frozenset()}]
    seeds = parse_seeds(a.seeds)
    knob_grid = [dict(zip(knobs, vals)) for vals in itertools.product(*knobs.values())] if knobs else [{}]
    pred = Predictor(a.ledger, a.tasks_dir, boot=a.boot, seed=a.random_seed)
    systems = [s.strip() for s in a.systems.split(",")] if a.systems else pred.systems
    canon_dir, reproduces = reference_canonical(gen, os.path.join(root, ".scratch"))
    canon_feats = task_features(canon_dir)
    rows, cells, diff, problems = [], [], [], []
    same_seed_ref: dict = {}
    for i, (seed, v, kn) in enumerate(itertools.product(seeds, offs, knob_grid)):
        vid = f"v{i:02d}"; vdir = f"{gen.task}__{vid}"; out = os.path.join(root, vdir)
        off = sorted(v["effective"])
        gen.generate(out, seed, off, kn)
        h = env.task_hashes(out)
        key = (seed, tuple(sorted(kn.items())))
        if not off:
            same_seed_ref[key] = h
        elif key in same_seed_ref:
            for part in ("checks", "reference"):
                if h[part] != same_seed_ref[key][part]:
                    problems.append(f"{vid}: {part} differs from the same draw with every trap on (answer moved)")
        d = pred.delta(task_features(out), canon_feats, len(off))
        eligible = not off
        rows.append({"id": vid, "dir": vdir, "seed": seed, "effective_off": off, "knobs": kn,
                     "canonical_setting": seed is None and not off and not kn,
                     "predicted_delta": public_delta(d),
                     "harder_eligible": eligible,
                     "harder_ineligible_reason": None if eligible else
                     "switches a pitfall off (authoring rule 6: removing a pitfall never adds one)",
                     "credibly_harder": eligible and d["lo90"] > 0,
                     "matched": abs(d["estimate"]) <= a.tol, "sha256": h})
        diff.append({"variant": vid, "dir": vdir, **public_delta(d)})
        cells += pred.cells(gen.task, vid, vdir, off, d["_draws"], systems, a.k)
    harder = sorted((r for r in rows if r["credibly_harder"]), key=lambda r: -r["predicted_delta"]["estimate"])
    best = max((r for r in rows if r["harder_eligible"] and not r["canonical_setting"]),
               key=lambda r: r["predicted_delta"]["estimate"], default=None)
    proposal = harder[0]["id"] if harder else None
    man = {"kind": "renewal-search", "task": gen.task, "generator": os.path.relpath(gen.gen, ROOT),
           "generator_sha256": env.sha_file(gen.gen), "route": gen.route, "created_utc": env.utcnow(),
           **env.git_state(), "python": gen_python(), "design": a.design, "seeds": seeds, "knobs": knobs,
           "available_knobs": gen.knobs(), "tolerance_logit": a.tol,
           "traps": gen.decl and {k: gen.decl.get(k, {}) for k in ("switchable", "fixed", "requires")},
           "canonical_reproduces_published": reproduces, "ledger_sha256": env.sha_file(a.ledger),
           "proposal": proposal, "variants": rows, "problems": problems,
           "run_hint": f"python bench/run.py --tasks-root {root} --tasks all --harness <h1,h2> --runs {a.k} --label <label>"}
    env.write_json(man_path, man)
    shutil.rmtree(os.path.join(root, ".scratch"), ignore_errors=True)
    doc = pred.predictions_doc(gen.task, man_path, systems, a.k, cells, diff)
    pp = os.path.join(root, "predictions", f"{gen.task}.json")
    env.write_json(pp, doc)

    L = [f"# Setting search: {gen.task}  ({len(rows)} settings; route {gen.route}; knobs available: "
         f"{', '.join(gen.knobs()) or 'none'})\n",
         f"canonical regenerated here matches published: "
         f"{', '.join(f'{k}={v}' for k, v in reproduces.items())}",
         f"ledger anchor: " + ", ".join(f"{s} {pred.anchor(gen.task, s)[0]}/{sum(pred.anchor(gen.task, s))}" for s in systems),
         "\n| id | seed | traps off | knobs | delta (logit, + harder) | 90% | features moved | "
         + " | ".join(f"P({s})" for s in systems) + " |",
         "|---|---|---|---|---|---|---|" + "---|" * len(systems)]
    pm = {(c["variant"], c["system"]): c["p_mean"] for c in cells}
    for r in rows:
        d = r["predicted_delta"]
        L.append(f"| {r['id']} | {'default' if r['seed'] is None else r['seed']} | {'+'.join(r['effective_off']) or '-'} | "
                 f"{','.join(f'{k}={v}' for k, v in r['knobs'].items()) or '-'} | {d['estimate']:+.3f} | "
                 f"{d['lo90']:+.2f} to {d['hi90']:+.2f} | {', '.join(d['features_changed']) or '-'} | "
                 + " | ".join(f"{pm[(r['id'], s)]:.3f}" for s in systems) + " |")
    if proposal:
        L.append(f"\nProposed harder setting: {proposal} (delta {harder[0]['predicted_delta']['estimate']:+.3f}, "
                 f"90% lower bound {harder[0]['predicted_delta']['lo90']:+.3f} > 0).")
    else:
        top = (f"; the largest predicted delta among non-canonical settings with every trap on is "
               f"{best['id']} at {best['predicted_delta']['estimate']:+.3f} "
               f"(90% {best['predicted_delta']['lo90']:+.2f} to {best['predicted_delta']['hi90']:+.2f})") if best else ""
        L.append("\nNo credibly harder setting in the reachable space (no setting's 90% interval is above zero)" + top +
                 ". Trap switches only remove pitfalls, so every trap on is already the top of that axis; a harder "
                 "task needs a size / rule / noise knob the generator does not expose.")
    L += [f"\nmanifest: {man_path}", f"predictions: {pp}  sha256={doc['sha256']}",
          f"register before any run: python bench/envelope.py register {pp} --registry <committed path>"]
    if problems:
        L += ["PROBLEMS:"] + problems
    print("\n".join(L))
    return 1 if problems else 0


# ----------------------------------------------------------------------------------------------- seal

def commitment(v: dict) -> str:
    return env.sha_bytes(env.canon({k: v[k] for k in ("task", "seed", "traps_off", "knobs", "sha256", "nonce")}))


def cmd_seal(a) -> int:
    root = check_root(a.root, a.tasks_dir)
    man_path = os.path.join(root, "manifest.json")
    if os.path.exists(man_path) and not a.force:
        raise SystemExit(f"{man_path} exists; pass --force")
    os.makedirs(root, exist_ok=True)
    warn = tracked_risk(root)
    pred = Predictor(a.ledger, a.tasks_dir, boot=a.boot, seed=a.random_seed)
    systems = [s.strip() for s in a.systems.split(",")] if a.systems else pred.systems
    explicit = parse_seeds(a.seeds) if a.seeds else None
    knobs = {k: v[0] for k, v in parse_knobs(a.knob).items()}
    off = sorted(t.strip() for t in a.traps_off.split(",") if t.strip())
    variants, rejected, per_task, tasks_meta = [], [], collections.defaultdict(list), {}
    scratch = os.path.join(root, ".scratch")
    for task in a.task:
        gen = Generator(task, a.tasks_dir, scratch=os.path.join(scratch, task))
        canon_dir, reproduces = reference_canonical(gen, os.path.join(scratch, task))
        canon_feats = task_features(canon_dir)
        cg = canonical_grade(gen.dir) if a.verify else None
        pub = env.task_hashes(gen.dir)
        seen_ws = {pub["workspace"], env.task_hashes(canon_dir)["workspace"]}
        tasks_meta[gen.task] = {"generator": os.path.relpath(gen.gen, ROOT), "generator_sha256": env.sha_file(gen.gen),
                                "route": gen.route, "canonical_reproduces_published": reproduces,
                                "canonical_in_repo_grade": cg, "published_sha256": pub,
                                "ledger_anchor": {s: dict(zip(("pass", "fail"), pred.anchor(gen.task, s))) for s in systems}}
        pool = list(explicit) if explicit else None
        tries, accepted = 0, 0
        while accepted < a.n and tries < a.max_tries:
            if pool is not None:
                if not pool:
                    break
                seed = pool.pop(0)
            else:
                seed = SEED_RANGE[0] + secrets.randbelow(SEED_RANGE[1] - SEED_RANGE[0])
            tries += 1
            vid = f"r{len([v for v in variants if v['task'] == gen.task]):02d}"
            vdir = f"{gen.task}__{vid}"
            out = os.path.join(root, vdir)
            try:
                gen.generate(out, seed, off, knobs)
            except RuntimeError as e:
                rejected.append({"task": gen.task, "seed": seed, "reason": f"generation failed: {str(e)[-300:]}"})
                continue
            h = env.task_hashes(out)
            reason = None
            if h["workspace"] in seen_ws:
                reason = "duplicate draw (workspace identical to the published task or an earlier variant)"
            d = pred.delta(task_features(out), canon_feats, len(off))
            if reason is None and abs(d["estimate"]) > a.tol:
                reason = f"difficulty not matched: delta {d['estimate']:+.3f} outside +/-{a.tol}"
            ver = verify(out, cg) if a.verify and reason is None else None
            if ver and ver["status"].startswith("FAIL"):
                reason = ver["status"] + f": reference failed {ver['reference_failed']}"
            if reason:
                rejected.append({"task": gen.task, "seed": seed, "reason": reason,
                                 "predicted_delta": public_delta(d)})
                shutil.rmtree(out, ignore_errors=True)
                continue
            seen_ws.add(h["workspace"])
            v = {"id": vid, "dir": vdir, "task": gen.task, "seed": seed, "traps_off": off, "knobs": knobs,
                 "predicted_delta": public_delta(d), "sha256": h,
                 "answer_changed": h["checks"] != pub["checks"] or h["reference"] != pub["reference"],
                 "seed_visible_in": seed_visible(out, seed),
                 "verification": ver or {"status": "NOT VERIFIED (--no-verify)"}, "nonce": secrets.token_hex(16)}
            v["commitment"] = commitment(v)
            variants.append(v)
            per_task[gen.task].append((v, d["_draws"]))
            accepted += 1
        tasks_meta[gen.task].update({"requested": a.n, "accepted": accepted, "tries": tries})
    shutil.rmtree(scratch, ignore_errors=True)
    man = {"kind": "renewal-sealed-manifest", "PRIVATE": "keep this file private until release: it holds the seeds",
           "created_utc": env.utcnow(), **env.git_state(), "python": gen_python(),
           "ledger_sha256": env.sha_file(a.ledger), "tolerance_logit": a.tol, "settings": {"traps_off": off, "knobs": knobs},
           "systems": systems, "k": a.k, "tasks": tasks_meta, "variants": variants, "rejected": rejected,
           "warnings": [warn] if warn else [],
           "run_hint": f"python bench/run.py --tasks-root {root} --tasks all --harness <h1,h2> --runs {a.k} --label <label>"}
    env.write_json(man_path, man)
    man_sha = env.sha_file(man_path)
    preds = {}
    for task, vs in per_task.items():
        cells = [c for v, dr in vs for c in pred.cells(task, v["id"], v["dir"], v["traps_off"], dr, systems, a.k)]
        doc = pred.predictions_doc(task, man_path, systems, a.k, cells,
                                   [{"variant": v["id"], "dir": v["dir"], **v["predicted_delta"]} for v, _ in vs])
        pp = os.path.join(root, "predictions", f"{task}.json")
        env.write_json(pp, doc)
        preds[task] = {"path": os.path.relpath(pp, root), "sha256": doc["sha256"]}
    env.write_json(os.path.join(root, "commitments.json"),
                   {"kind": "renewal-commitments", "created_utc": man["created_utc"], "git_head": man["git_head"],
                    "manifest_sha256": man_sha,
                    "note": "Each commitment is sha256 of {task, seed, traps_off, knobs, content hashes, nonce} from the "
                            "private manifest. Publish this file now; publish the manifest when the variants are released.",
                    "predictions": preds,
                    "variants": [{"dir": v["dir"], "task": v["task"], "commitment": v["commitment"]} for v in variants]})
    L = [f"# Sealed variants -> {root}\n", "| task | variant | delta (logit) | 90% | answer changed | verification |",
         "|---|---|---|---|---|---|"]
    for v in variants:
        d = v["predicted_delta"]
        L.append(f"| {v['task']} | {v['id']} | {d['estimate']:+.3f} | {d['lo90']:+.2f} to {d['hi90']:+.2f} | "
                 f"{'yes' if v['answer_changed'] else 'NO'} | {v['verification']['status']} |")
    for t, m in tasks_meta.items():
        L.append(f"\n{t}: {m['accepted']}/{m['requested']} accepted in {m['tries']} tries; canonical regenerated "
                 f"here matches published: {', '.join(f'{k}={x}' for k, x in m['canonical_reproduces_published'].items())}"
                 + (f"; published reference grades {'pass' if m['canonical_in_repo_grade']['passed'] else 'FAIL ' + str(m['canonical_in_repo_grade']['failed'])} here"
                    if m["canonical_in_repo_grade"] else ""))
    for r in rejected:
        L.append(f"  rejected {r['task']}: {r['reason']}")
    for v in variants:
        if v["seed_visible_in"]:
            L.append(f"  warning: {v['dir']} shows its seed in {v['seed_visible_in']}")
    if warn:
        L.append(f"  warning: {warn}")
    L += [f"\nprivate manifest: {man_path}  sha256={man_sha}", f"public commitments: {os.path.join(root, 'commitments.json')}"]
    print("\n".join(L))
    short = any(m["accepted"] < m["requested"] for m in tasks_meta.values())
    return 1 if short else 0


# ----------------------------------------------------------------------------------------------- check

def cmd_check(a) -> int:
    man = env.read_json(a.manifest)
    root = os.path.dirname(os.path.abspath(a.manifest))
    bad = []
    com = {}
    cp = os.path.join(root, "commitments.json")
    if os.path.isfile(cp):
        c = env.read_json(cp)
        com = {v["dir"]: v["commitment"] for v in c["variants"]}
        if c["manifest_sha256"] != env.sha_file(a.manifest):
            bad.append("manifest.json does not match the hash in commitments.json")
    for v in man["variants"]:
        h = env.task_hashes(os.path.join(root, v["dir"]))
        for k, x in v["sha256"].items():
            if h.get(k) != x:
                bad.append(f"{v['dir']}: {k} changed since sealing")
        if commitment(v) != v["commitment"] or (com and com.get(v["dir"]) != v["commitment"]):
            bad.append(f"{v['dir']}: commitment does not match")
    print("\n".join(bad) if bad else f"OK: {len(man['variants'])} sealed variants match their hashes and commitments")
    return 1 if bad else 0


# ----------------------------------------------------------------------------------------------- cli

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--ledger", default=LEDGER); p.add_argument("--tasks-dir", default=TASKS)

    def model_args(p):
        p.add_argument("--systems", default=None, help="default: every system in the ledger")
        p.add_argument("--k", type=int, default=3, help="repetitions for pass^k (the ledger has 3)")
        p.add_argument("--tol", type=float, default=0.10, help="matched difficulty: |delta| <= tol logits")
        p.add_argument("--boot", type=int, default=200); p.add_argument("--random-seed", type=int, default=0)
        p.add_argument("--knob", action="append", default=[], help="NAME=V1,V2: an existing generator flag")
        p.add_argument("--force", action="store_true")

    p = sub.add_parser("saturation", help="classify tasks by the ledger"); common(p)
    p.add_argument("--near-max-fails", type=int, default=1); p.add_argument("--json", default=None)
    p.set_defaults(fn=cmd_saturation)

    p = sub.add_parser("search", help="enumerate settings of one task and predict their difficulty"); common(p); model_args(p)
    p.add_argument("--task", required=True); p.add_argument("--root", required=True)
    p.add_argument("--seeds", default="default,1,2,3,4", help="comma list; 'default' is the generator's own seed")
    p.add_argument("--design", default="single", help="trap off-sets: single | pairs | full | random:N")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("seal", help="generate sealed variants at matched predicted difficulty"); common(p); model_args(p)
    p.add_argument("--task", action="append", required=True); p.add_argument("--root", required=True)
    p.add_argument("--n", type=int, default=3, help="variants per task")
    p.add_argument("--seeds", default=None, help="explicit seeds (default: secret random seeds)")
    p.add_argument("--traps-off", default="", help="seal an easier setting instead of the full task (rarely wanted)")
    p.add_argument("--max-tries", type=int, default=10)
    p.add_argument("--no-verify", dest="verify", action="store_false")
    p.set_defaults(fn=cmd_seal)

    p = sub.add_parser("check", help="re-hash sealed variants against the manifest and commitments")
    p.add_argument("--manifest", required=True); p.set_defaults(fn=cmd_check)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
