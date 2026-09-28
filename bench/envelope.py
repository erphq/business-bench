#!/usr/bin/env python3
"""Delegation envelope: which combinations of pitfalls an agent system handles reliably, forecast before the runs
and scored after them.

    envelope.py plan     --task project-margin --design single --root /tmp/pm-variants
    envelope.py predict  --manifest /tmp/pm-variants/manifest.json --systems proto-deepseek,codex-sol --out P.json
    envelope.py register P.json --registry results/forecasts/registry.jsonl
    (run)        bench/run.py --tasks-root /tmp/pm-variants --harness proto-deepseek,codex-sol --runs 5 --label pm-env
    envelope.py fit      --manifest M --results results/pm-env --out F.json
    envelope.py score    --predictions P.json --results results/pm-env --registry results/forecasts/registry.jsonl
    envelope.py envelope --fit F.json --system codex-sol --k 5 --threshold 0.95
    envelope.py simulate --manifest M --effects effects.json --systems a,b --reps 5 --out DIR   (synthetic records)

Model, one task at a time. Every variant is the canonical task from the same draw with a set of switchable traps
removed (bizgen.traps: the answer does not move). For system s and variant v,

    logit P(attempt passes) = b + theta_s - sum_j w_j * on_j(v)      [+ optional per-system deviations d_sj]

b is the task baseline with every switchable trap off, theta_s the system's ability (centred on the systems in the fit), and
w_j the cost in logits of trap j being present (positive = harder). Fixed traps are always present and live in b.
pass^k is the probability that k independent repetitions all pass: E[p^k] over parameter uncertainty.

Offline tooling. numpy + yaml; no model calls. See docs/envelope.md for what this does and does not establish.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import hashlib
import itertools
import json
import math
import os
import random
import subprocess
import sys

import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS = os.path.join(ROOT, "tasks", "desk")
SYNTHETIC_NOTE = ("SYNTHETIC: outcome drawn by bench/envelope.py simulate from stated per-trap effects; "
                  "no agent ran and nothing was graded")
# Prior used by `predict` when a trap's effect has not been measured: a trap being present costs about half a
# logit on average, and 95% of prior mass lies between about -1.5 (the trap helps) and +2.5 (a strong trap).
PREDICT_EFFECT_PRIOR = (0.5, 1.0)
# Priors used by `fit`: centred on zero and weak, so the data decide the sign.
FIT_PRIOR = {"system": (0.0, 3.0), "effect": (0.0, 2.5), "interaction": (0.0, 0.5)}
NQ = 20  # predictive distribution of p stored as 20 equal-mass points (quantiles at 2.5%, 7.5%, ..., 97.5%)


# ----------------------------------------------------------------------------------------------- hashing / io

def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: str) -> str:
    with open(p, "rb") as f:
        return sha_bytes(f.read())


def sha_tree(d: str) -> str | None:
    """Hash of a directory: sorted relative paths and file bytes. None if the directory is missing."""
    if not os.path.isdir(d):
        return None
    h = hashlib.sha256()
    for p in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
        if os.path.isfile(p):
            rel = os.path.relpath(p, d).replace(os.sep, "/")
            h.update(rel.encode() + b"\0" + sha_file(p).encode() + b"\n")
    return h.hexdigest()


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def content_sha(doc: dict) -> str:
    """sha256 of a JSON document with its own `sha256` field left out."""
    return sha_bytes(canon({k: v for k, v in doc.items() if k != "sha256"}))


def write_json(path: str, doc: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=False)
        f.write("\n")


def read_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def read_lines(path: str) -> list[str]:
    with open(path) as f:
        return [l for l in f if l.strip()]


def read_yaml(path: str):
    with open(path) as f:
        return yaml.safe_load(f)


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


# ----------------------------------------------------------------------------------------------- traps

def generator_path(task: str, tasks_dir: str = TASKS) -> tuple[str, str]:
    """(task id, gen.py path) from a task id or a task folder."""
    d = task if os.path.isdir(task) else os.path.join(tasks_dir, task)
    g = os.path.join(d, "gen.py")
    if not os.path.isfile(g):
        raise SystemExit(f"no generator at {g}")
    return os.path.basename(os.path.normpath(d)), g


def list_traps(gen: str) -> dict:
    r = subprocess.run([sys.executable, gen, "--list-traps"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{gen} --list-traps failed (is the generator retrofitted with trap switches?)\n{r.stderr[-800:]}")
    return json.loads(r.stdout)


def closure(off, requires: dict) -> frozenset:
    """Turning a trap off also turns off every trap that only exists inside it (bizgen.traps.TrapSet)."""
    off = set(off)
    while True:
        extra = {a for a, b in requires.items() if b in off and a not in off}
        if not extra:
            return frozenset(off)
        off |= extra


def order_key(s) -> tuple:
    return (len(s), sorted(s))


def feasible_off_sets(decl: dict) -> list[frozenset]:
    """Every distinct effective off-set (closed under `requires`)."""
    names = list(decl["switchable"])
    seen = {closure(c, decl.get("requires", {}))
            for r in range(len(names) + 1) for c in itertools.combinations(names, r)}
    return sorted(seen, key=order_key)


def choose_variants(decl: dict, design: str, seed: int = 0) -> tuple[list[dict], list[dict]]:
    """Requested off-sets for a design, deduplicated after `requires` closure.
    Returns (variants [{requested, effective}], duplicates [{requested, same_as_effective}])."""
    names = list(decl["switchable"])
    req = decl.get("requires", {})
    if design == "single":
        asked = [()] + [(t,) for t in names]
    elif design == "pairs":
        asked = [()] + [(t,) for t in names] + list(itertools.combinations(names, 2))
    elif design == "full":
        asked = [c for r in range(len(names) + 1) for c in itertools.combinations(names, r)]
    elif design.startswith("random:"):
        n = int(design.split(":", 1)[1])
        rng = random.Random(seed)
        asked, eff_seen, tries = [()], {frozenset()}, 0
        n_feasible = len(feasible_off_sets(decl)) - 1
        while len(eff_seen) - 1 < min(n, n_feasible) and tries < 10000:
            tries += 1
            c = tuple(t for t in names if rng.random() < 0.5)
            asked.append(c)
            eff_seen.add(closure(c, req))
    else:
        raise SystemExit(f"unknown design {design!r}: single, pairs, full or random:N")
    variants, dups, by_eff = [], [], {}
    for c in asked:
        eff = closure(c, req)
        if eff in by_eff:
            if tuple(sorted(c)) != tuple(sorted(by_eff[eff]["requested"])):
                dups.append({"requested": sorted(c), "same_as_effective": sorted(eff)})
            continue
        by_eff[eff] = {"requested": sorted(c), "effective": eff}
        variants.append(by_eff[eff])
    variants.sort(key=lambda v: order_key(v["effective"]))
    return variants, dups


def on_vector(effective_off, names: list[str]) -> np.ndarray:
    return np.array([0.0 if n in effective_off else 1.0 for n in names])


# ----------------------------------------------------------------------------------------------- plan

def task_hashes(d: str) -> dict:
    ty = os.path.join(d, "task.yaml")
    spec = read_yaml(ty) if os.path.isfile(ty) else {}
    return {"task_yaml": sha_file(ty) if os.path.isfile(ty) else None,
            "checks": sha_bytes(canon(spec.get("checks"))) if spec else None,
            "reference": sha_tree(os.path.join(d, "reference")),
            "reference_solution": sha_tree(os.path.join(d, "reference_solution")),
            "workspace": sha_tree(os.path.join(d, "workspace"))}


def cmd_plan(a) -> int:
    task, gen = generator_path(a.task, a.tasks_dir)
    decl = list_traps(gen)
    if not decl.get("switchable"):
        raise SystemExit(f"{task} declares no switchable traps; nothing to vary")
    root = os.path.abspath(a.root)
    if os.path.commonpath([root, os.path.abspath(a.tasks_dir)]) == os.path.abspath(a.tasks_dir):
        raise SystemExit("--root must be outside the published task tree")
    man_path = os.path.join(root, "manifest.json")
    if os.path.exists(man_path) and not a.force:
        raise SystemExit(f"{man_path} exists; pass --force to replan into the same folder")
    os.makedirs(root, exist_ok=True)
    variants, dups = choose_variants(decl, a.design, a.random_seed)
    names = list(decl["switchable"])
    rows, problems, warnings = [], [], []
    for i, v in enumerate(variants):
        vid = f"v{i:02d}"
        vdir = f"{task}__{vid}"
        eff = sorted(v["effective"])
        row = {"id": vid, "dir": vdir, "traps_off": v["requested"], "effective_off": eff,
               "traps_on": [n for n in names if n not in v["effective"]], "canonical": not eff}
        if not a.dry_run:
            out = os.path.join(root, vdir)
            cmd = [sys.executable, gen, "--out", out]
            if eff:
                cmd += ["--traps-off", ",".join(eff)]
            if a.seed is not None:
                cmd += ["--seed", str(a.seed)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit(f"generation failed for {vid} {eff}: {r.stderr[-800:]}")
            row["sha256"] = task_hashes(out)
            spec = read_yaml(os.path.join(out, "task.yaml"))
            got = sorted((spec.get("variant") or {}).get("traps_off", []))
            if got != eff:
                problems.append(f"{vid}: task.yaml records traps_off {got}, expected {eff}")
        rows.append(row)
    published = None
    if not a.dry_run:
        c = rows[0]["sha256"]
        for r in rows[1:]:
            h = r["sha256"]
            for part in ("checks", "reference"):
                if h[part] != c[part]:
                    problems.append(f"{r['id']} ({'+'.join(r['effective_off'])}): {part} differs from canonical: "
                                    "the answer moved, so the trap is not switchable (docs/authoring-traps.md rule 4)")
            if h["workspace"] == c["workspace"]:
                warnings.append(f"{r['id']}: workspace identical to canonical; the switch does nothing")
        pub = task_hashes(os.path.dirname(gen))
        published = {k: pub[k] == c[k] for k in ("checks", "reference", "workspace")}
        if not published["workspace"]:
            warnings.append("the regenerated canonical workspace is not byte-identical to the published task "
                            "(typically a library difference such as lxml in the generating environment); canonical "
                            "ledger attempts are still used as the all-on baseline")
    man = {"kind": "envelope-manifest", "task": task, "generator": os.path.relpath(gen, ROOT),
           "generator_sha256": sha_file(gen), "seed": a.seed, "design": a.design,
           "random_seed": a.random_seed if a.design.startswith("random:") else None,
           "created_utc": utcnow(), "materialized": not a.dry_run,
           "traps": {"switchable": decl["switchable"], "fixed": decl.get("fixed", {}),
                     "requires": decl.get("requires", {})},
           "variants": rows, "duplicates_dropped": dups, "canonical_matches_published": published,
           "warnings": warnings,
           "run_hint": f"python bench/run.py --tasks-root {root} --tasks all --harness <h1,h2> --runs 5 --label <label>"}
    write_json(man_path, man)
    print(f"{task}: {len(rows)} variants ({a.design}), {len(dups)} duplicate(s) dropped after `requires` closure")
    for r in rows:
        print(f"  {r['id']}  off={'+'.join(r['effective_off']) or '(none: canonical)'}")
    for w in warnings:
        print(f"  warning: {w}")
    print(f"manifest: {man_path}  sha256={sha_file(man_path)}")
    if problems:
        print("\n".join(["PROBLEMS:"] + problems), file=sys.stderr)
        return 1
    return 0


# ----------------------------------------------------------------------------------------------- records

def load_records(paths: list[str]) -> list[dict]:
    """Attempt records from run.py result folders (results/<label>/<run_id>/result.json), a results/<label>
    folder, a single run folder, or a ledger (.jsonl). Each record gets `_start` (epoch or None) and
    `_start_evidence`."""
    out = []
    for p in paths:
        if os.path.isfile(p) and p.endswith(".jsonl"):
            for line in read_lines(p):
                r = json.loads(line)
                r["_start"], r["_start_evidence"] = start_time(r, None)
                r["_source"] = p
                out.append(r)
            continue
        files = [os.path.join(p, "result.json")] if os.path.isfile(os.path.join(p, "result.json")) else \
            sorted(glob.glob(os.path.join(p, "*", "result.json")))
        for f in files:
            r = read_json(f)
            r["_start"], r["_start_evidence"] = start_time(r, os.path.dirname(f))
            r["_source"] = f
            out.append(r)
    return out


def start_time(r: dict, run_dir: str | None) -> tuple[float | None, str]:
    """When the attempt started. run.py does not record it, so fall back to file times in the run folder:
    prompt.txt is written just before the agent starts; result.json mtime minus wall time is a later bound."""
    if r.get("started_utc"):
        return parse_utc(r["started_utc"]), "recorded started_utc"
    if run_dir:
        cands = []
        pr = os.path.join(run_dir, "prompt.txt")
        if os.path.isfile(pr):
            cands.append(os.path.getmtime(pr))
        rj = os.path.join(run_dir, "result.json")
        if os.path.isfile(rj) and r.get("wall_s") is not None:
            cands.append(os.path.getmtime(rj) - float(r["wall_s"]))
        if cands:
            return min(cands), "file mtimes (weak: lost or reset by copying)"
    return None, "none"


def assign(records: list[dict], man: dict) -> tuple[list[tuple[str, str, bool, dict]], int]:
    """(system, variant id, passed, record) for records that belong to the manifest's variants. Attempts on the
    published task itself count as the canonical (all traps on) variant."""
    by_dir = {v["dir"]: v["id"] for v in man["variants"]}
    canon_id = next(v["id"] for v in man["variants"] if v["canonical"]) if any(v["canonical"] for v in man["variants"]) else None
    rows, skipped = [], 0
    for r in records:
        t = r.get("task")
        vid = by_dir.get(t) or (canon_id if t == man["task"] else None)
        if vid is None or "passed" not in r or "harness" not in r:
            skipped += 1
            continue
        rows.append((r["harness"], vid, bool(r["passed"]), r))
    return rows, skipped


# ----------------------------------------------------------------------------------------------- model

class Model:
    """Parameter layout: [system intercept per system, effect per switchable trap, (interaction per system x trap)].

    The intercept alpha_s is system s's logit pass rate on this task with every switchable trap removed. The task
    baseline b and the abilities theta_s of the docstring are reported as b = mean(alpha), theta_s = alpha_s - b;
    with one task, only this split is identified (an ability is relative to the other systems in the fit)."""

    def __init__(self, systems: list[str], traps: list[str], interactions: bool = False):
        self.systems, self.traps, self.interactions = list(systems), list(traps), interactions
        self.names = [f"system:{s}" for s in systems] + [f"effect:{t}" for t in traps]
        if interactions:
            self.names += [f"interaction:{s}:{t}" for s in systems for t in traps]

    def row(self, system: str, on: np.ndarray) -> np.ndarray:
        S, J = len(self.systems), len(self.traps)
        z = np.zeros(len(self.names))
        si = self.systems.index(system)
        z[si] = 1.0
        z[S:S + J] = -on
        if self.interactions:
            z[S + J + si * J:S + J + (si + 1) * J] = -on
        return z

    def prior(self, spec: dict) -> tuple[np.ndarray, np.ndarray]:
        mean, sd = [], []
        for n in self.names:
            m, s = spec[n.split(":")[0]]
            mean.append(m); sd.append(s)
        return np.array(mean), np.array(sd)

    def derived(self, beta: np.ndarray) -> dict:
        """Task baseline, centred abilities and per-trap effects from one parameter vector."""
        S, J = len(self.systems), len(self.traps)
        b = float(beta[:S].mean())
        out = {"baseline": b}
        out.update({f"ability:{s}": float(beta[i] - b) for i, s in enumerate(self.systems)})
        out.update({f"effect:{t}": float(beta[S + j]) for j, t in enumerate(self.traps)})
        if self.interactions:
            out.update({n: float(x) for n, x in zip(self.names[S + J:], beta[S + J:])})
        return out


def log_post(Z, y, beta, pm, P) -> float:
    eta = Z @ beta
    return float((y * eta - np.logaddexp(0, eta)).sum() - 0.5 * (P * (beta - pm) ** 2).sum())


def map_fit(Z: np.ndarray, y: np.ndarray, pm: np.ndarray, psd: np.ndarray, iters: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """MAP logistic regression with independent Gaussian priors (Newton with backtracking; the log posterior is
    strictly concave). Returns (beta, posterior precision at the mode)."""
    beta = pm.copy()
    P = 1.0 / psd ** 2
    cur = log_post(Z, y, beta, pm, P)
    for _ in range(iters):
        p = sigmoid(Z @ beta)
        g = Z.T @ (y - p) - P * (beta - pm)
        H = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(P)
        step = np.linalg.solve(H, g)
        t = 1.0
        while t > 1e-6:
            new = log_post(Z, y, beta + t * step, pm, P)
            if new >= cur - 1e-12:
                break
            t /= 2
        beta, cur = beta + t * step, new
        if np.abs(t * step).max() < 1e-9:
            break
    p = sigmoid(Z @ beta)
    H = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(P)
    return beta, H


def design_rows(rows, man, model) -> tuple[np.ndarray, np.ndarray, list[tuple[str, str]]]:
    eff = {v["id"]: set(v["effective_off"]) for v in man["variants"]}
    Z = np.array([model.row(s, on_vector(eff[v], model.traps)) for s, v, _, _ in rows]).reshape(len(rows), len(model.names))
    y = np.array([float(p) for _, _, p, _ in rows])
    return Z, y, [(s, v) for s, v, _, _ in rows]


def quantile_points(draws: np.ndarray) -> list[float]:
    return [round(float(q), 6) for q in np.quantile(draws, (np.arange(NQ) + 0.5) / NQ)]


# ----------------------------------------------------------------------------------------------- predict

def cmd_predict(a) -> int:
    man = read_json(a.manifest)
    systems = [s.strip() for s in a.systems.split(",") if s.strip()]
    traps = list(man["traps"]["switchable"])
    recs = load_records(([a.from_ledger] if a.from_ledger else []) + (a.from_results or []))
    rows, _ = assign(recs, man)
    rows = [r for r in rows if r[0] in systems]
    canon_id = next(v["id"] for v in man["variants"] if v["canonical"])
    has_variant_data = any(v != canon_id for _, v, _, _ in rows)
    mu, sd = a.effect_prior
    rng = np.random.default_rng(a.seed)
    M = a.draws
    counts = collections.Counter((s, p) for s, v, p, _ in rows if v == canon_id)
    baseline_p = {s: (counts[(s, True)] + 0.5) / (counts[(s, True)] + counts[(s, False)] + 1.0) for s in systems}
    notes = []
    if not has_variant_data:
        method = "canonical-rate + prior"
        method_note = (
            "No attempts on any non-canonical variant were available, so nothing about the individual traps has "
            "been measured yet. Each system's pass rate on the canonical task (every trap on) is taken from its "
            "observed attempts with a Jeffreys Beta(passes+0.5, fails+0.5) posterior; removing trap j adds w_j to "
            f"the logit, with w_j drawn from a weakly-informative Normal(mean {mu}, sd {sd}) prior, independently per "
            "trap. These are prior forecasts: their calibration is what `score` will test.")
        draws = {}
        for s in systems:
            k1, k0 = counts[(s, True)], counts[(s, False)]
            if k1 + k0 == 0:
                notes.append(f"{s}: no canonical attempts found; its canonical pass rate is a uniform Beta(1,1) guess")
                pc = rng.beta(1.0, 1.0, M)
            else:
                pc = rng.beta(k1 + 0.5, k0 + 0.5, M)
            draws[s] = logit(pc)
        W = rng.normal(mu, sd, size=(M, len(traps)))
        def cell_draws(s, eff):
            off = 1.0 - on_vector(eff, traps)
            return sigmoid(draws[s] + W @ off)
        params = None
    else:
        method = "laplace"
        seen = {s for s, *_ in rows}
        notes += [f"{s}: no attempts found; its predictions rest on the priors alone" for s in systems if s not in seen]
        prior = dict(FIT_PRIOR, effect=(mu, sd))
        model = Model(systems, traps, interactions=a.interactions)
        Z, y, _ = design_rows(rows, man, model)
        pm, psd = model.prior(prior)
        beta, H = map_fit(Z, y, pm, psd)
        cov = np.linalg.inv(H)
        B = rng.multivariate_normal(beta, (cov + cov.T) / 2, size=M)
        method_note = (
            "Attempts on non-canonical variants were available, so the logistic model (baseline + system ability - "
            "sum of per-trap effects) was fitted to them by MAP with priors "
            f"system intercept (all switchable traps off) N{FIT_PRIOR['system']}, trap effect N({mu}, {sd}), "
            f"interaction N{FIT_PRIOR['interaction']} if enabled; "
            "predictions average over a Laplace (Gaussian) approximation to the posterior.")
        def cell_draws(s, eff):
            return sigmoid(B @ model.row(s, on_vector(eff, traps)))
        params = {n: round(v, 4) for n, v in model.derived(beta).items()}
    cells = []
    for s in systems:
        for v in man["variants"]:
            p = cell_draws(s, set(v["effective_off"]))
            cells.append({"system": s, "variant": v["id"], "dir": v["dir"], "effective_off": v["effective_off"],
                          "p_mean": round(float(p.mean()), 6), "p_q": quantile_points(p),
                          "passk": round(float((p ** a.k).mean()), 6)})
    doc = {"kind": "envelope-predictions", "task": man["task"], "manifest_sha256": sha_file(a.manifest),
           "created_utc": utcnow(), "systems": systems, "k": a.k, "method": method, "method_note": method_note,
           "effect_prior": {"mean": mu, "sd": sd}, "notes": notes,
           "evidence": {"records": len(rows), "canonical_counts": {s: {"pass": counts[(s, True)], "fail": counts[(s, False)]} for s in systems},
                        "sources": sorted({r["_source"] for _, _, _, r in rows}),
                        "synthetic": any(r.get("synthetic") for _, _, _, r in rows)},
           "fitted_params": params, "baseline_p": baseline_p,
           "cell_fields": {"p_mean": "predicted probability a single attempt passes",
                           "p_q": f"{NQ} equal-mass points of the predictive distribution of that probability",
                           "passk": f"predicted probability that {a.k} independent repetitions all pass"},
           "cells": cells}
    doc["sha256"] = content_sha(doc)
    write_json(a.out, doc)
    print(f"{len(cells)} predictions ({method}) -> {a.out}\nsha256={doc['sha256']}")
    for n in notes:
        print(f"  note: {n}")
    print("Register before running anything:  bench/envelope.py register " + a.out)
    return 0


# ----------------------------------------------------------------------------------------------- register

def git_state() -> dict:
    def g(*args):
        r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    head = g("rev-parse", "HEAD")
    st = g("status", "--porcelain", "--untracked-files=no")
    return {"git_head": head, "git_dirty": None if st is None else bool(st)}


def cmd_register(a) -> int:
    doc = read_json(a.predictions)
    if doc.get("kind") != "envelope-predictions":
        raise SystemExit("not a predictions file")
    if content_sha(doc) != doc.get("sha256"):
        raise SystemExit("predictions content does not match its sha256; regenerate the file instead of editing it")
    entry = {"predictions_sha256": doc["sha256"], "manifest_sha256": doc["manifest_sha256"], "task": doc["task"],
             "systems": doc["systems"], "k": doc["k"], "created_utc": utcnow(),
             "predictions_path": os.path.abspath(a.predictions), **git_state()}
    os.makedirs(os.path.dirname(os.path.abspath(a.registry)), exist_ok=True)
    with open(a.registry, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    print(f"registered {doc['sha256'][:16]} at {entry['created_utc']} in {a.registry}")
    print("The registry is only evidence if others can see it was written before the runs: commit and push it, "
          "or publish the line, before starting bench/run.py.")
    return 0


# ----------------------------------------------------------------------------------------------- fit

def fit_model(rows, man, systems, interactions=False, prior=None, boot=200, cluster="cell", seed=0):
    prior = prior or FIT_PRIOR
    traps = list(man["traps"]["switchable"])
    model = Model(systems, traps, interactions)
    Z, y, keys = design_rows(rows, man, model)
    pm, psd = model.prior(prior)
    beta, H = map_fit(Z, y, pm, psd)
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    rng = np.random.default_rng(seed)
    groups = collections.defaultdict(list)
    for i, (s, v) in enumerate(keys):
        groups[(s, v) if cluster == "cell" else v].append(i)
    glist = list(groups.values())
    B = []
    for _ in range(boot):
        if cluster == "cell":   # resample repetitions within each system x variant cell
            idx = np.concatenate([rng.choice(g, len(g)) for g in glist])
        else:                   # resample whole variants (all systems' attempts on it)
            pick = rng.integers(0, len(glist), len(glist))
            idx = np.concatenate([glist[j] for j in pick])
        B.append(map_fit(Z[idx], y[idx], pm, psd, iters=40)[0])
    B = np.array(B) if B else beta[None, :]
    return model, beta, se, B, Z, y, keys


def cmd_fit(a) -> int:
    man = read_json(a.manifest)
    recs = load_records(a.results)
    rows, skipped = assign(recs, man)
    if not rows:
        raise SystemExit("no attempt records match the manifest's variants")
    systems = sorted({s for s, _, _, _ in rows})
    model, beta, se, B, Z, y, keys = fit_model(rows, man, systems, a.interactions, boot=a.boot,
                                                cluster=a.cluster, seed=a.seed)
    lo, hi = np.percentile(B, [5, 95], axis=0)
    synthetic = any(r.get("synthetic") for _, _, _, r in rows)
    observed = collections.defaultdict(lambda: [0, 0])
    for s, v, p, _ in rows:
        observed[(s, v)][0] += p; observed[(s, v)][1] += 1
    fitted = sigmoid(Z @ beta)
    fp = {}
    for (s, v), f in zip(keys, fitted):
        fp[(s, v)] = float(f)
    doc = {"kind": "envelope-fit", "task": man["task"], "manifest_sha256": sha_file(a.manifest),
           "created_utc": utcnow(), "synthetic": synthetic, "systems": systems,
           "traps": man["traps"], "interactions": a.interactions, "prior": FIT_PRIOR,
           "bootstrap": {"n": a.boot, "cluster": a.cluster},
           "param_names": model.names, "params": [float(b) for b in beta], "laplace_se": [float(x) for x in se],
           "interval90": {n: [float(l), float(h)] for n, l, h in zip(model.names, lo, hi)},
           "boot_draws": np.round(B, 5).tolist(),
           "observed_variants": sorted({v["id"] for v in man["variants"] if any(vv == v["id"] for _, vv, _, _ in rows)}),
           "variants": [{k: v[k] for k in ("id", "dir", "effective_off")} for v in man["variants"]],
           "cells": [{"system": s, "variant": v, "passed": observed[(s, v)][0], "n": observed[(s, v)][1],
                      "fitted_p": round(fp[(s, v)], 4)} for (s, v) in sorted(observed)],
           "records": len(rows), "records_skipped": skipped, "sources": sorted({r["_source"] for *_, r in rows})[:50]}
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.manifest)), "fit.json")
    L = []
    if synthetic:
        L.append("SYNTHETIC RECORDS: this fit demonstrates the pipeline on simulated outcomes, not agent behaviour.\n")
    der = model.derived(beta)
    dB = [model.derived(b) for b in B]
    dlo = {n: float(np.percentile([d[n] for d in dB], 5)) for n in der}
    dhi = {n: float(np.percentile([d[n] for d in dB], 95)) for n in der}
    doc["derived"] = {n: {"estimate": der[n], "lo90": dlo[n], "hi90": dhi[n]} for n in der}
    write_json(out, doc)
    L += [f"# Envelope fit: {man['task']}  ({len(rows)} attempts, {len(systems)} systems, "
          f"{len(doc['observed_variants'])} of {len(man['variants'])} variants observed)\n",
          "| parameter | estimate | 90% bootstrap |", "|---|---|---|"]
    for n in der:
        L.append(f"| {n} | {der[n]:+.2f} | {dlo[n]:+.2f} to {dhi[n]:+.2f} |")
    L += ["\nbaseline = task logit pass rate with every switchable trap off, averaged over systems; ability = a "
          "system's offset from that average (relative to the systems in this fit); effect = logit cost of the trap "
          "being present (positive = harder). Bootstrap resamples "
          f"{'repetitions within each system x variant cell' if a.cluster == 'cell' else 'whole variants'}.",
          "\n| system | variant | passed/n | fitted p |", "|---|---|---|---|"]
    for c in doc["cells"]:
        L.append(f"| {c['system']} | {c['variant']} | {c['passed']}/{c['n']} | {c['fitted_p']:.3f} |")
    print("\n".join(L))
    print(f"\nfit -> {out}")
    return 0


# ----------------------------------------------------------------------------------------------- score

def mix_binom_pvalue(q: list[float], n: int, x: int) -> float:
    """Two-sided predictive p-value of x passes in n attempts, p drawn from the stored equal-mass points."""
    pmf = np.zeros(n + 1)
    for p in q:
        pmf += np.array([math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)])
    pmf /= len(q)
    lo, hi = pmf[:x + 1].sum(), pmf[x:].sum()
    return float(min(1.0, 2 * min(lo, hi)))


def cmd_score(a) -> int:
    doc = read_json(a.predictions)
    if content_sha(doc) != doc.get("sha256"):
        print("REFUSED: the predictions file does not match its own sha256 (edited after it was written).")
        return 2
    reg = []
    if os.path.isfile(a.registry):
        reg = [json.loads(l) for l in read_lines(a.registry)]
    hits = sorted((e for e in reg if e.get("predictions_sha256") == doc["sha256"]), key=lambda e: e["created_utc"])
    if not hits:
        print(f"REFUSED: predictions {doc['sha256'][:16]} are not in {a.registry}: not pre-registered.")
        return 2
    entry = hits[0]
    if entry.get("manifest_sha256") != doc["manifest_sha256"]:
        print("REFUSED: registry entry names a different manifest than the predictions.")
        return 2
    man = read_json(a.manifest) if a.manifest else None
    recs = load_records(a.results)
    by_dir = {c["dir"]: c["variant"] for c in doc["cells"]}
    cellmap = {(c["system"], c["variant"]): c for c in doc["cells"]}
    rows = []
    for r in recs:
        vid = by_dir.get(r.get("task"))
        if vid is None and man and r.get("task") == man["task"]:
            vid = next(v["id"] for v in man["variants"] if v["canonical"])
        if vid is not None and (r.get("harness"), vid) in cellmap and "passed" in r:
            rows.append((r["harness"], vid, bool(r["passed"]), r))
    if not rows:
        print("REFUSED: no attempt records match the predicted (system, variant) cells.")
        return 2
    untimed = [r for *_, r in rows if r["_start"] is None]
    if untimed:
        print(f"REFUSED: {len(untimed)} attempt(s) carry no start time, so pre-registration cannot be checked "
              f"(e.g. {untimed[0]['_source']}).")
        return 2
    first = min(r["_start"] for *_, r in rows)
    reg_t = parse_utc(entry["created_utc"])
    if not reg_t < first:
        print(f"REFUSED: registered {entry['created_utc']}, but the first attempt started {iso(first)}: "
              "not pre-registered.")
        return 2
    evidence = sorted({r["_start_evidence"] for *_, r in rows})
    synthetic = any(r.get("synthetic") for *_, r in rows)
    p = np.array([cellmap[(s, v)]["p_mean"] for s, v, _, _ in rows])
    y = np.array([float(x) for _, _, x, _ in rows])
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    brier = float(((p - y) ** 2).mean())
    ll = float(-(y * np.log(pc) + (1 - y) * np.log(1 - pc)).mean())
    base = np.array([doc["baseline_p"].get(s, 0.5) for s, *_ in rows])
    brier_base = float(((base - y) ** 2).mean())
    k = doc["k"]
    per = collections.defaultdict(list)
    for s, v, x, r in rows:
        per[(s, v)].append((r.get("run", 0), x))
    cells = []
    for (s, v), obs in sorted(per.items()):
        c = cellmap[(s, v)]
        n, x = len(obs), sum(o for _, o in obs)
        first_k = [o for _, o in sorted(obs)[:k]]
        cells.append({"system": s, "variant": v, "off": "+".join(c["effective_off"]) or "(canonical)",
                      "n": n, "passed": x, "p_pred": c["p_mean"], "passk_pred": c["passk"],
                      "allk": (all(first_k) if len(first_k) == k else None),
                      "pvalue": mix_binom_pvalue(c["p_q"], n, x)})
    pk = [(c["passk_pred"], float(c["allk"])) for c in cells if c["allk"] is not None]
    brier_k = float(np.mean([(q - o) ** 2 for q, o in pk])) if pk else None
    edges = [0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0000001]
    L = []
    if synthetic:
        L.append("SYNTHETIC RECORDS: this score demonstrates the pipeline on simulated outcomes, not agent behaviour.\n")
    L += [f"# Forecast score: {doc['task']}  predictions {doc['sha256'][:16]} ({doc['method']})\n",
          f"- Registered {entry['created_utc']} (git {str(entry.get('git_head'))[:12]}{', dirty tree' if entry.get('git_dirty') else ''}); "
          f"first attempt started {iso(first)}; start-time evidence: {'; '.join(evidence)}.",
          f"- {len(rows)} attempts in {len(cells)} system x variant cells.",
          f"- Attempt-level Brier {brier:.4f}, log loss {ll:.4f}. "
          f"'Traps do not matter' baseline (each system's canonical rate everywhere) Brier {brier_base:.4f}; "
          f"skill {1 - brier / brier_base:+.3f}." if brier_base > 0 else
          f"- Attempt-level Brier {brier:.4f}, log loss {ll:.4f}.",
          (f"- pass^{k} (cells with {k}+ repetitions, first {k} by run index): Brier {brier_k:.4f} over {len(pk)} cells."
           if pk else f"- pass^{k}: no cell has {k} repetitions yet."),
          "\n## Reliability (attempt level)\n", "| predicted | attempts | mean predicted | observed |", "|---|---|---|---|"]
    for lo_, hi_ in zip(edges[:-1], edges[1:]):
        m = (p >= lo_) & (p < hi_)
        if m.any():
            L.append(f"| {lo_:.2f}-{min(hi_, 1):.2f} | {int(m.sum())} | {p[m].mean():.3f} | {y[m].mean():.3f} |")
    misses = [c for c in cells if c["pvalue"] < 0.10]
    L += ["\n## Every cell (misses marked: observed count outside the central 90% of the predictive distribution)\n",
          f"| system | variant | traps off | passed/n | predicted p | predicted pass^{k} | all {k} passed | miss |",
          "|---|---|---|---|---|---|---|---|"]
    for c in cells:
        allk = "n/a" if c["allk"] is None else ("yes" if c["allk"] else "no")
        L.append(f"| {c['system']} | {c['variant']} | {c['off']} | {c['passed']}/{c['n']} | {c['p_pred']:.3f} | "
                 f"{c['passk_pred']:.3f} | {allk} | {'MISS' if c['pvalue'] < 0.10 else ''} |")
    L.append(f"\n{len(misses)} miss(es) of {len(cells)} cells; about {0.10 * len(cells):.1f} expected by chance "
             "if the forecasts are calibrated.")
    print("\n".join(L))
    if a.out:
        write_json(a.out, {"kind": "envelope-score", "predictions_sha256": doc["sha256"], "registry_entry": entry,
                           "first_attempt_utc": iso(first), "start_evidence": evidence, "synthetic": synthetic,
                           "brier": brier, "log_loss": ll, "brier_baseline": brier_base, "brier_passk": brier_k,
                           "cells": cells})
    return 0


# ----------------------------------------------------------------------------------------------- envelope

def describe(names, traps_desc) -> str:
    return "; ".join(traps_desc[n] for n in names) if names else "none of the switchable pitfalls"


def envelope_table(fit: dict, system: str, k: int) -> list[dict]:
    names = fit["param_names"]
    traps = list(fit["traps"]["switchable"])
    model = Model(fit["systems"], traps, fit["interactions"])
    assert model.names == names
    beta = np.array(fit["params"]); B = np.array(fit["boot_draws"])
    decl = {"switchable": fit["traps"]["switchable"], "requires": fit["traps"]["requires"]}
    observed = {frozenset(v["effective_off"]) for v in fit["variants"] if v["id"] in fit["observed_variants"]}
    out = []
    for off in feasible_off_sets(decl):
        z = model.row(system, on_vector(off, traps))
        p = float(sigmoid(z @ beta)); pb = sigmoid(B @ z)
        lo, hi = np.percentile(pb ** k, [5, 95])
        out.append({"on": [t for t in traps if t not in off], "off": sorted(off), "p": p, "passk": p ** k,
                    "passk_lo": float(lo), "passk_hi": float(hi), "observed": off in observed})
    return out


def cmd_envelope(a) -> int:
    fit = read_json(a.fit)
    if a.system not in fit["systems"]:
        raise SystemExit(f"{a.system} not in fit (systems: {fit['systems']})")
    desc = fit["traps"]["switchable"]
    req = fit["traps"]["requires"]
    tab = envelope_table(fit, a.system, a.k)
    key = "passk_lo" if a.conservative else "passk"
    inside = [r for r in tab if r[key] >= a.threshold]
    ins = {frozenset(r["on"]) for r in inside}
    by_on = {frozenset(r["on"]): r for r in tab}
    maximal = [r for r in inside if not any(frozenset(r["on"]) < o for o in ins)]
    L = []
    if fit.get("synthetic"):
        L.append("SYNTHETIC: fitted on simulated outcomes. The sentences below demonstrate the format; they say nothing "
                 "about any real system.\n")
    crit = "the lower end of its 90% interval" if a.conservative else "the fitted estimate"
    L += [f"# Delegation envelope: {a.system} on {fit['task']}\n",
          f"Reliable here means: passes all {a.k} repetitions with probability at least {a.threshold:.0%} "
          f"(judged by {crit}).",
          f"Always present, because they are part of the answer: {'; '.join(fit['traps']['fixed'].values()) or 'nothing'}.\n"]
    if not inside:
        allo = by_on[frozenset()]
        L.append(f"Not reliable even with every switchable pitfall removed: pass^{a.k} {allo['passk']:.2f} "
                 f"(90% {allo['passk_lo']:.2f}-{allo['passk_hi']:.2f}).")
    else:
        full = by_on[frozenset(desc)]
        if full[key] >= a.threshold:
            L.append(f"Reliable on the task as published, with every pitfall present: pass^{a.k} {full['passk']:.2f} "
                     f"(90% {full['passk_lo']:.2f}-{full['passk_hi']:.2f}).")
        L.append(f"## The most pitfalls it handles reliably ({len(maximal)} combination(s))\n")
        for r in sorted(maximal, key=lambda r: (-len(r["on"]), -r["passk"])):
            tag = "" if r["observed"] else " [extrapolated: this combination was not run]"
            L.append(f"- With these present: {describe(r['on'], desc)}. "
                     f"Passes all {a.k} with probability {r['passk']:.2f} (90% {r['passk_lo']:.2f}-{r['passk_hi']:.2f}){tag}.")
            breakers = []
            for t in desc:
                if t in r["on"]:
                    continue
                on2, x = set(r["on"]) | {t}, t
                while x in req:            # a trap that lives inside another brings it along
                    x = req[x]; on2.add(x)
                r2 = by_on.get(frozenset(on2))
                if r2 and r2[key] < a.threshold:
                    sharp = " -- below the floor" if a.floor is not None and r2["passk"] < a.floor else ""
                    breakers.append(f"{desc[t]} (pass^{a.k} falls to {r2['passk']:.2f}{sharp})")
            if breakers:
                L.append("  Adding any one of these takes it out of the envelope: " + "; ".join(breakers) + ".")
        L.append(f"\n{len(inside)} of {len(tab)} possible combinations are inside the envelope.")
    if a.all:
        L += ["\n| pitfalls present | pass^k | 90% | run? |", "|---|---|---|---|"]
        for r in sorted(tab, key=lambda r: -r["passk"]):
            L.append(f"| {', '.join(r['on']) or '(none)'} | {r['passk']:.3f} | {r['passk_lo']:.2f}-{r['passk_hi']:.2f} | "
                     f"{'yes' if r['observed'] else 'no'} |")
    print("\n".join(L))
    if a.json:
        write_json(a.json, {"system": a.system, "k": a.k, "threshold": a.threshold, "conservative": a.conservative,
                            "synthetic": fit.get("synthetic", False), "combinations": tab})
    return 0


# ----------------------------------------------------------------------------------------------- simulate

def cmd_simulate(a) -> int:
    man = read_json(a.manifest)
    eff = json.loads(a.effects) if a.effects.strip().startswith("{") else read_json(a.effects)
    systems = [s.strip() for s in a.systems.split(",") if s.strip()]
    traps = list(man["traps"]["switchable"])
    unknown = set(eff.get("effects", {})) - set(traps)
    if unknown:
        raise SystemExit(f"effects for undeclared traps: {sorted(unknown)}")
    if os.path.isdir(a.out) and os.listdir(a.out) and not a.force:
        raise SystemExit(f"{a.out} is not empty; pass --force")
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    t0 = parse_utc(a.start_utc) if a.start_utc else dt.datetime.now(dt.timezone.utc).timestamp()
    w = np.array([eff.get("effects", {}).get(t, 0.0) for t in traps])
    res, i = [], 0
    for s in systems:
        th = eff.get("abilities", {}).get(s, 0.0)
        inter = np.array([eff.get("interactions", {}).get(s, {}).get(t, 0.0) for t in traps])
        for v in man["variants"]:
            on = on_vector(set(v["effective_off"]), traps)
            p = float(sigmoid(eff.get("baseline", 0.0) + th - on @ (w + inter)))
            for r in range(1, a.reps + 1):
                passed = bool(rng.random() < p)
                run_id = f"{v['dir']}__{s}__r{r}"
                rec = {"run_id": run_id, "task": v["dir"], "category": None, "harness": s, "run": r,
                       "exit_code": 0, "timed_out": False, "wall_s": 0.0, "passed": passed, "checks": [],
                       "grader_errors": [], "usage": {}, "cost_usd": None, "work_dir": None,
                       "started_utc": iso(t0 + i), "synthetic": True, "synthetic_note": SYNTHETIC_NOTE,
                       "synthetic_true_p": round(p, 6)}
                os.makedirs(os.path.join(a.out, run_id), exist_ok=True)
                write_json(os.path.join(a.out, run_id, "result.json"), rec)
                res.append(rec); i += 1
    write_json(os.path.join(a.out, "summary.json"), {"synthetic": True, "note": SYNTHETIC_NOTE, "effects": eff,
                                                     "records": len(res)})
    with open(os.path.join(a.out, "SYNTHETIC.txt"), "w") as f:
        f.write(SYNTHETIC_NOTE + "\n")
    print(f"{len(res)} SYNTHETIC records -> {a.out}")
    return 0


# ----------------------------------------------------------------------------------------------- cli

def prior_arg(s: str) -> tuple[float, float]:
    m, sd = (float(x) for x in s.split(","))
    return m, sd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="materialize trap variants of one task and write manifest.json")
    p.add_argument("--task", required=True); p.add_argument("--root", required=True)
    p.add_argument("--design", default="single", help="single | pairs | full | random:N")
    p.add_argument("--seed", type=int, default=None, help="generator --seed (default: the generator's own)")
    p.add_argument("--random-seed", type=int, default=0, help="seed for --design random:N")
    p.add_argument("--tasks-dir", default=TASKS)
    p.add_argument("--dry-run", action="store_true", help="write the manifest without generating variants")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("predict", help="forecast pass probability and pass^k per system x variant")
    p.add_argument("--manifest", required=True); p.add_argument("--systems", required=True)
    p.add_argument("--from-ledger", default=None, help="ledger .jsonl (e.g. results/latest/attempts.jsonl)")
    p.add_argument("--from-results", nargs="*", default=[], help="run.py results folders")
    p.add_argument("--out", required=True); p.add_argument("--k", type=int, default=5)
    p.add_argument("--effect-prior", type=prior_arg, default=PREDICT_EFFECT_PRIOR, help="mean,sd of a trap's logit cost")
    p.add_argument("--interactions", action="store_true", help="per-system trap deviations (laplace method)")
    p.add_argument("--draws", type=int, default=4000); p.add_argument("--seed", type=int, default=0)
    p.set_defaults(fn=cmd_predict)

    p = sub.add_parser("register", help="append a predictions hash to the registry before any run")
    p.add_argument("predictions")
    p.add_argument("--registry", default=os.path.join(ROOT, "results", "forecasts", "registry.jsonl"))
    p.set_defaults(fn=cmd_register)

    p = sub.add_parser("fit", help="fit trap effects and system abilities from variant runs")
    p.add_argument("--manifest", required=True); p.add_argument("--results", nargs="+", required=True)
    p.add_argument("--out", default=None); p.add_argument("--boot", type=int, default=200)
    p.add_argument("--cluster", choices=("cell", "variant"), default="cell")
    p.add_argument("--interactions", action="store_true"); p.add_argument("--seed", type=int, default=0)
    p.set_defaults(fn=cmd_fit)

    p = sub.add_parser("score", help="score registered predictions against runs")
    p.add_argument("--predictions", required=True); p.add_argument("--results", nargs="+", required=True)
    p.add_argument("--registry", default=os.path.join(ROOT, "results", "forecasts", "registry.jsonl"))
    p.add_argument("--manifest", default=None, help="lets attempts on the published task count as canonical")
    p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("envelope", help="business-readable envelope for one system")
    p.add_argument("--fit", required=True); p.add_argument("--system", required=True)
    p.add_argument("--k", type=int, default=5); p.add_argument("--threshold", type=float, default=0.95)
    p.add_argument("--floor", type=float, default=None, help="also flag additions that fall below this pass^k")
    p.add_argument("--conservative", action="store_true", help="judge by the 5th percentile, not the estimate")
    p.add_argument("--all", action="store_true", help="print every combination")
    p.add_argument("--json", default=None)
    p.set_defaults(fn=cmd_envelope)

    p = sub.add_parser("simulate", help="SYNTHETIC result records from known effects")
    p.add_argument("--manifest", required=True)
    p.add_argument("--effects", required=True, help='JSON file or inline: {"baseline":3,"abilities":{..},"effects":{..}}')
    p.add_argument("--systems", required=True); p.add_argument("--reps", type=int, default=5)
    p.add_argument("--out", required=True); p.add_argument("--seed", type=int, default=0)
    p.add_argument("--start-utc", default=None, help="recorded start of the first synthetic attempt (default now)")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_simulate)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
