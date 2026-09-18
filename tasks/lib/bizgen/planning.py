"""Constraint-checker scaffold for plan_feasible tasks (v2 axis 5).

A task's plan_check.py builds a list of Constraint objects and an objective, then calls
`evaluate`. The generator uses the same constraints to certify its reference plan and record the
reference objective, so grader and generator can never disagree about feasibility.

    from bizgen.planning import Constraint, evaluate, capacity, coverage, time_windows, local_search
"""
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass
class Constraint:
    name: str
    check: Callable[[list[dict], dict], list[str]]   # (plan rows, data) -> violations

    def __call__(self, plan: list[dict], data: dict) -> list[str]:
        return [f"{self.name}: {v}" for v in self.check(plan, data)]


def evaluate(plan: list[dict], data: dict, constraints: Iterable[Constraint], objective: Callable[[list[dict], dict], float],
             reference_objective: float) -> dict:
    """The dict shape plan_feasible expects from evaluate(ws, ref)."""
    violations: list[str] = []
    for c in constraints: violations.extend(c(plan, data))
    obj = float(objective(plan, data)) if not violations else float("nan")
    return {"feasible": not violations, "violations": violations, "objective": obj, "reference_objective": float(reference_objective)}


# ---- reusable constraint builders ----

def capacity(group_key: str, weight_key: str | None, limits: dict, name: str = "capacity") -> Constraint:
    """Sum of weight_key (or row count) per group_key must not exceed limits[group]."""
    def check(plan, data):
        load: dict = {}
        for row in plan:
            g = row[group_key]; load[g] = load.get(g, 0) + (float(row[weight_key]) if weight_key else 1)
        out = [f"{g} carries {round(v, 2)} over limit {limits[g]}" for g, v in load.items() if g in limits and v > limits[g] + 1e-9]
        out += [f"unknown {group_key} {g!r}" for g in load if g not in limits]
        return out
    return Constraint(name, check)


def coverage(item_key: str, required: Iterable, name: str = "coverage", exactly_once: bool = True) -> Constraint:
    """Every required item appears in the plan (exactly once by default); nothing unknown appears."""
    req = set(required)
    def check(plan, data):
        seen: dict = {}
        for row in plan: seen[row[item_key]] = seen.get(row[item_key], 0) + 1
        out = [f"{i} not planned" for i in sorted(req - set(seen))]
        out += [f"{i} not a known {item_key}" for i in sorted(set(seen) - req)]
        if exactly_once: out += [f"{i} planned {n} times" for i, n in sorted(seen.items()) if i in req and n != 1]
        return out
    return Constraint(name, check)


def time_windows(item_key: str, start_key: str, windows: dict, name: str = "time window") -> Constraint:
    """windows[item] = (earliest, latest); the planned start must fall inside, values comparable (numbers or ISO strings)."""
    def check(plan, data):
        out = []
        for row in plan:
            w = windows.get(row[item_key])
            if w and not (w[0] <= row[start_key] <= w[1]):
                out.append(f"{row[item_key]} starts {row[start_key]} outside {w[0]}..{w[1]}")
        return out
    return Constraint(name, check)


def no_overlap(group_key: str, start_key: str, end_key: str, name: str = "overlap") -> Constraint:
    """Within a group (a crew, a room, a vehicle) intervals must not overlap."""
    def check(plan, data):
        out = []
        by: dict = {}
        for row in plan: by.setdefault(row[group_key], []).append(row)
        for g, rows in by.items():
            rows = sorted(rows, key=lambda x: x[start_key])
            for a, b in zip(rows, rows[1:]):
                if b[start_key] < a[end_key]: out.append(f"{g}: {a.get('id', a[start_key])} and {b.get('id', b[start_key])} overlap")
        return out
    return Constraint(name, check)


# ---- reference solutions ----

def local_search(r: random.Random, plan: list[dict], neighbours: Callable[[random.Random, list[dict]], list[dict]],
                 cost: Callable[[list[dict]], float | None], iters: int = 2000) -> tuple[list[dict], float]:
    """First-improvement local search over caller-supplied neighbour moves. `cost` returns None for an
    infeasible plan. Deterministic given r. Used by generators to produce a reference plan whose objective
    the task pins; the task states the resulting gap policy, not a claim of global optimality."""
    best = [dict(x) for x in plan]; best_cost = cost(best)
    if best_cost is None: raise ValueError("initial plan must be feasible")
    for _ in range(iters):
        cand = neighbours(r, best)
        c = cost(cand)
        if c is not None and c < best_cost - 1e-9:
            best, best_cost = cand, c
    return best, best_cost
