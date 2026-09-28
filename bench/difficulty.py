#!/usr/bin/env python3
"""First difficulty model for the desk track, fitted on the attempt ledger.

    difficulty.py [--ledger results/latest/attempts.jsonl] [--out DIR] [--boot 200]

An explanatory item-response model (the linear logistic test model): each system s has an ability theta_s,
each task's difficulty is a weighted sum of observable task features, and

    P(attempt passes) = sigmoid(theta_s - sum_k w_k * x_tk)

Because difficulty is shared through features instead of a free parameter per task, the model can be fitted
with few systems and can score a task no system has attempted, which is what the generator settings need.
Features come from the task files only (check counts by kind, trap count, workspace size, formats,
category), so the model never sees an outcome through its inputs.

Reported: system abilities; feature weights with task-clustered bootstrap intervals; leave-task-out
predictive log loss against a per-system base rate (does task structure predict failure at all?); per-task
observed difficulty and how well it separates systems; saturated tasks; verification headroom
(pass@k - pass^k).

READ THIS BEFORE QUOTING IT: two systems are too few to separate ability from difficulty with any
confidence. The numbers are a pipeline check and a first look, not findings. The panel of 8-12
configurations planned before v2 authoring is what makes them usable.

Offline tooling, numpy only. Newton-Raphson on a few hundred rows; runs in about a second.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os

import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALUE = {"xlsx_value_present", "csv_values_match", "text_numbers_present", "forecast_error"}
SET = {"csv_set_equal", "csv_row_count"}
TEXT = {"text_sentence_matches", "text_contains_all", "text_contains_any", "text_not_contains", "text_matches_all"}
STRUCT = {"file_exists", "csv_columns", "xlsx_has_formulas", "xlsx_no_errors"}


def task_features(task_dir: str) -> dict[str, float]:
    t = yaml.safe_load(open(os.path.join(task_dir, "task.yaml"))) or {}
    checks = [c for c in t.get("checks") or [] if c.get("required", True)]
    kinds = collections.Counter("value" if c["type"] in VALUE else "set" if c["type"] in SET else
                                "text" if c["type"] in TEXT else "struct" if c["type"] in STRUCT else "custom"
                                for c in checks)
    files = [p for p in glob.glob(os.path.join(task_dir, "workspace", "**", "*"), recursive=True) if os.path.isfile(p)]
    size = sum(os.path.getsize(p) for p in files)
    ext = collections.Counter(os.path.splitext(p)[1].lower() for p in files)
    return {
        "log_checks": math.log(max(1, len(checks))),
        "value_checks": kinds["value"], "set_checks": kinds["set"], "text_checks": kinds["text"],
        "custom_checks": kinds["custom"],
        "traps": len(t.get("traps") or []),
        "log_workspace_kb": math.log1p(size / 1024),
        "files": len(files),
        "has_pdf": float(ext[".pdf"] > 0), "has_xlsx_input": float(ext[".xlsx"] > 0),
        "wants_xlsx": float(any(str(c.get("path", "")).endswith(".xlsx") for c in checks)),
        "category": t.get("category", "?"),
    }


def raw_row(f: dict, num: list[str], cats: list[str]) -> list[float]:
    """One task's unstandardized design row: numeric features, then one-hot category (first category dropped)."""
    return [f[k] for k in num] + [float(f["category"] == c) for c in cats[1:]]


def design_raw(tasks: list[str], feats: dict[str, dict], cats: list[str]) -> tuple[np.ndarray, list[str], np.ndarray, np.ndarray]:
    """(standardized X, names, column means, column sds) so rows for new tasks can be put on the same scale."""
    num = [k for k in next(iter(feats.values())) if k != "category"]
    X = np.array([raw_row(feats[t], num, cats) for t in tasks])
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    return (X - mu) / sd, num + [f"category={c}" for c in cats[1:]], mu, sd


def design(tasks: list[str], feats: dict[str, dict], cats: list[str]) -> tuple[np.ndarray, list[str]]:
    X, names, _, _ = design_raw(tasks, feats, cats)
    return X, names


def fit(S: np.ndarray, X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 50) -> np.ndarray:
    """Logistic regression with rows [system one-hot | -features]; L2 on feature weights only."""
    Z = np.hstack([S, -X])
    beta = np.zeros(Z.shape[1])
    pen = np.r_[np.zeros(S.shape[1]), np.full(X.shape[1], l2)]
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ beta, -30, 30)))
        g = Z.T @ (y - p) - pen * beta
        H = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(pen) + 1e-9 * np.eye(len(beta))
        step = np.linalg.solve(H, g)
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    return beta


class LedgerModel:
    """The fitted model as a reusable object, for tools that score tasks no system has attempted (bench/renew.py).

    `difficulty(task_dir)` is sum_k w_k * x_k on the ledger's standardized scale (positive = harder); `boot` holds
    task-clustered bootstrap draws of the full parameter vector [theta | w] for predictive uncertainty."""

    def __init__(self, ledger: str, tasks_dir: str, boot: int = 200, seed: int = 0):
        att = [json.loads(l) for l in open(ledger)]
        self.systems = sorted({x["harness"] for x in att})
        self.tasks = sorted({x["task"] for x in att if os.path.isdir(os.path.join(tasks_dir, x["task"]))})
        self.feats = {t: task_features(os.path.join(tasks_dir, t)) for t in self.tasks}
        self.cats = sorted({f["category"] for f in self.feats.values()})
        Xt, self.names, self.mu, self.sd = design_raw(self.tasks, self.feats, self.cats)
        self.num = [k for k in next(iter(self.feats.values())) if k != "category"]
        ti = {t: i for i, t in enumerate(self.tasks)}
        rows = [x for x in att if x["task"] in ti]
        S = np.array([[float(x["harness"] == s) for s in self.systems] for x in rows])
        tix = np.array([ti[x["task"]] for x in rows])
        X, y = Xt[tix], np.array([float(x["passed"]) for x in rows])
        self.beta = fit(S, X, y)
        rng = np.random.default_rng(seed)
        by_task = collections.defaultdict(list)
        for r, t in enumerate(tix):
            by_task[t].append(r)
        draws = []
        for _ in range(boot):
            pick = rng.integers(0, len(self.tasks), len(self.tasks))
            idx = np.concatenate([by_task[t] for t in pick])
            draws.append(fit(S[idx], X[idx], y[idx]))
        self.boot = np.array(draws) if draws else self.beta[None, :]

    @property
    def weights(self) -> np.ndarray:
        return self.beta[len(self.systems):]

    def row(self, feats: dict) -> np.ndarray:
        """Standardized design row for any task's features (a category unseen in the ledger is all zeros)."""
        return (np.array(raw_row(feats, self.num, self.cats)) - self.mu) / self.sd

    def row_for(self, task_dir: str) -> np.ndarray:
        return self.row(task_features(task_dir))


def logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", default=os.path.join(ROOT, "results", "latest", "attempts.jsonl"))
    ap.add_argument("--tasks", default=os.path.join(ROOT, "tasks", "desk"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "measurement"))
    ap.add_argument("--boot", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    att = [json.loads(l) for l in open(a.ledger)]
    systems = sorted({x["harness"] for x in att})
    tasks = sorted({x["task"] for x in att if os.path.isdir(os.path.join(a.tasks, x["task"]))})
    feats = {t: task_features(os.path.join(a.tasks, t)) for t in tasks}
    cats = sorted({f["category"] for f in feats.values()})
    Xt, names = design(tasks, feats, cats)
    ti = {t: i for i, t in enumerate(tasks)}
    rows = [x for x in att if x["task"] in ti]
    S = np.array([[float(x["harness"] == s) for s in systems] for x in rows])
    tix = np.array([ti[x["task"]] for x in rows])
    X = Xt[tix]
    y = np.array([float(x["passed"]) for x in rows])

    beta = fit(S, X, y)
    theta, w = beta[:len(systems)], beta[len(systems):]

    # task-clustered bootstrap for the weights
    rng = np.random.default_rng(a.seed)
    by_task = collections.defaultdict(list)
    for r, t in enumerate(tix):
        by_task[t].append(r)
    boots = []
    for _ in range(a.boot):
        pick = rng.integers(0, len(tasks), len(tasks))
        idx = np.concatenate([by_task[t] for t in pick])
        boots.append(fit(S[idx], X[idx], y[idx])[len(systems):])
    lo, hi = np.percentile(np.array(boots), [5, 95], axis=0)

    # leave-task-out prediction vs a per-system base rate
    folds = 10
    order = rng.permutation(len(tasks))
    pm, pb = np.zeros(len(y)), np.zeros(len(y))
    for f in range(folds):
        held = set(order[f::folds].tolist())
        te = np.array([t in held for t in tix]); tr = ~te
        b = fit(S[tr], X[tr], y[tr])
        pm[te] = 1 / (1 + np.exp(-(np.hstack([S[te], -X[te]]) @ b)))
        for k in range(len(systems)):
            m = tr & (S[:, k] == 1)
            pb[te & (S[:, k] == 1)] = y[m].mean()
    ll_model, ll_base = logloss(pm, y), logloss(pb, y)

    # observed per-task stats
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for x in rows:
        per[x["task"]][x["harness"]].append(bool(x["passed"]))
    pred_task = 1 / (1 + np.exp(-(theta.mean() - Xt @ w)))
    table = []
    for t in tasks:
        rates = {s: sum(per[t][s]) / len(per[t][s]) for s in systems if per[t][s]}
        pooled = sum(sum(v) for v in per[t].values()) / sum(len(v) for v in per[t].values())
        table.append({"task": t, "category": feats[t]["category"], "pass_rate": pooled,
                      "separation": max(rates.values()) - min(rates.values()) if len(rates) > 1 else 0.0,
                      "predicted": float(pred_task[ti[t]]), **{f"rate_{s}": r for s, r in rates.items()}})
    saturated = [r for r in table if r["pass_rate"] == 1.0]
    informative = [r for r in table if 0 < r["pass_rate"] < 1]

    L = ["# Difficulty model, first fit\n",
         f"Ledger: {len(rows)} attempts, {len(tasks)} tasks, {len(systems)} systems.\n",
         "> Two systems cannot separate ability from difficulty with confidence. Treat everything below as a "
         "check that the pipeline works and a first look, not as findings. A panel of 8-12 configurations "
         "is needed before these numbers carry weight.\n",
         "## Does task structure predict failure?\n",
         f"Leave-task-out log loss: model {ll_model:.4f} vs per-system base rate {ll_base:.4f} "
         f"({'better' if ll_model < ll_base else 'not better'} by {abs(ll_base - ll_model):.4f}).\n",
         "## System ability (logit, relative)\n"]
    for s, th in zip(systems, theta):
        L.append(f"- {s}: {th:+.2f}")
    L += ["\n## Feature weights (positive = makes the task harder; standardized features; 90% task bootstrap)\n",
          "| feature | weight | 90% interval |", "|---|---|---|"]
    for k in np.argsort(-np.abs(w)):
        flag = "" if lo[k] > 0 or hi[k] < 0 else " (crosses 0)"
        L.append(f"| {names[k]} | {w[k]:+.2f} | {lo[k]:+.2f} to {hi[k]:+.2f}{flag} |")
    hk = []
    for s in systems:
        tt = [t for t in tasks if per[t][s]]
        pk = sum(any(per[t][s]) for t in tt) / len(tt)
        pa = sum(all(per[t][s]) for t in tt) / len(tt)
        hk.append(f"- {s}: pass@k {pk:.1%}, pass^k {pa:.1%}, headroom {pk - pa:.1%}")
    L += ["\n## Verification headroom (pass@k - pass^k)\n"] + hk
    L += ["\n## Where the signal is\n",
          f"- Saturated (every attempt passed): {len(saturated)} tasks",
          f"- Informative (some pass, some fail): {len(informative)} tasks",
          f"- Never passed: {sum(1 for r in table if r['pass_rate'] == 0)} tasks\n",
          "Tasks that separate the systems most:\n", "| task | category | " + " | ".join(systems) + " |",
          "|---|---|" + "---|" * len(systems)]
    for r in sorted(table, key=lambda r: -r["separation"])[:15]:
        L.append(f"| {r['task']} | {r['category']} | " + " | ".join(f"{r.get('rate_' + s, float('nan')):.0%}" for s in systems) + " |")
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "difficulty.md"), "w") as f:
        f.write("\n".join(L) + "\n")
    with open(os.path.join(a.out, "difficulty.json"), "w") as f:
        json.dump({"systems": dict(zip(systems, theta.tolist())),
                   "weights": {n: {"w": float(w[i]), "lo": float(lo[i]), "hi": float(hi[i])} for i, n in enumerate(names)},
                   "logloss": {"model": ll_model, "base": ll_base}, "tasks": table}, f, indent=1)
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
