"""Difficulty knobs for task generators: size, rules, noise, trap intensity and cross-document rules.

A trap switch removes a pitfall and must leave the answer where it is (bizgen/traps.py). A knob is the other
direction: it makes the task bigger, stricter or messier, and the answer is *expected* to move. A generator
declares its knobs once:

    KNOBS = KnobSet(
        Knob("scale", "scale", default=1, levels=(1, 2, 3, 4),
             changes="suppliers' ordinary payments per vendor are multiplied by N", measure="rows"),
        Knob("trap_count.dup_vendor_record", "trap-count", default=1, levels=(1, 2, 3),
             changes="suppliers set up twice in the vendor master and paid under the second ID",
             measure="trap_instances.dup_vendor_record"),
    )

Flags (every knob takes a value, so `bench/renew.py search --knob NAME=V1,V2` can pass any of them):

    --scale N              volume: rows / entities multiplied (kind "scale")
    --rules N              number of business rules in play (kind "rules")
    --noise F              rate of malformed or messy records, 0..1 (kind "noise")
    --trap-count T=N       planted instances of trap T; several as T1=N+T2=M (kind "trap-count")
    --cross-doc N          0 or 1 (or a count): rules that need a second document (kind "cross-doc")
    --list-knobs           print the declaration as JSON and exit
    --describe             print this draw's content counts as JSON (rows, rules, trap instances, noise) and exit
    --out DIR              where a knobbed task is written; never the task folder

Rules the generators follow (docs/authoring-knobs.md):

* **Default untouched.** With no knob flag the generator's output is byte-identical to before and no slower. The
  default values are exactly the published task, and the default code path draws the same random numbers in the
  same order. Reading a knob is a dict lookup.
* **Complete and self-consistent.** With any knob off its default the generator writes a whole task to --out:
  workspace, reference/, reference_solution/ and a task.yaml whose checks are recomputed from the new draw, so the
  reference solution passes and the untouched workspace fails. task.yaml records the settings under
  `variant: {of, draw, knobs}`.
* **Monotone.** Each knob's levels are ordered from the published task (the default) upward in intended
  difficulty. `measure` names the --describe count that must grow along the levels; bench/validate_knobs.py
  checks it, and that every level is solvable, non-trivial and deterministic.
"""
from __future__ import annotations

import argparse
import json

from .traps import variant_dirs

KINDS = {
    "scale": "volume: more rows or entities to process",
    "rules": "more business rules in play",
    "noise": "a higher rate of malformed or messy records",
    "trap-count": "more planted instances of an existing trap",
    "cross-doc": "a rule that needs a second document",
}
FLAG = {"scale": "scale", "rules": "rules", "noise": "noise", "cross-doc": "cross-doc"}


class Knob:
    __slots__ = ("name", "kind", "default", "levels", "lo", "hi", "type", "changes", "measure", "trap")

    def __init__(self, name: str, kind: str, default, levels, changes: str, measure: str,
                 lo=None, hi=None, trap: str | None = None):
        if kind not in KINDS:
            raise ValueError(f"knob {name!r}: kind must be one of {sorted(KINDS)}")
        if kind == "trap-count":
            trap = trap or name.split(".", 1)[-1]
            if name != f"trap_count.{trap}":
                raise ValueError(f"a trap-count knob is named trap_count.<trap>, got {name!r}")
        elif name != FLAG[kind].replace("-", "_"):
            raise ValueError(f"a {kind} knob is named {FLAG[kind].replace('-', '_')!r}, got {name!r}")
        levels = tuple(levels)
        if not levels or levels[0] != default:
            raise ValueError(f"knob {name!r}: levels start at the default (the published task)")
        if any(b <= a for a, b in zip(levels, levels[1:])):
            raise ValueError(f"knob {name!r}: levels must increase (ordered by intended difficulty)")
        self.type = float if any(isinstance(v, float) for v in levels) else int
        self.name, self.kind, self.default, self.levels = name, kind, self.type(default), tuple(map(self.type, levels))
        self.lo = self.type(lo if lo is not None else levels[0])
        self.hi = self.type(hi if hi is not None else levels[-1])
        self.changes, self.measure, self.trap = changes, measure, trap

    @property
    def flag(self) -> str:
        return "trap-count" if self.kind == "trap-count" else FLAG[self.kind]

    def coerce(self, raw) -> int | float:
        try:
            v = self.type(raw) if self.type is float else int(str(raw))
        except ValueError:
            raise SystemExit(f"--{self.flag}: {raw!r} is not a {self.type.__name__} for knob {self.name}")
        if not self.lo <= v <= self.hi:
            raise SystemExit(f"--{self.flag}: {self.name}={v} outside its range {self.lo}..{self.hi}")
        return v

    def describe(self) -> dict:
        return {"name": self.name, "kind": self.kind, "flag": f"--{self.flag}", "type": self.type.__name__,
                "default": self.default, "levels": list(self.levels), "min": self.lo, "max": self.hi,
                "monotone": "harder as the value increases; the default is the published task",
                "changes": self.changes, "measure": self.measure, "trap": self.trap}


class KnobSet:
    __slots__ = ("knobs",)

    def __init__(self, *knobs: Knob):
        names = [k.name for k in knobs]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate knob names: {names}")
        self.knobs = {k.name: k for k in knobs}

    def defaults(self) -> "Settings":
        return Settings(self, {})

    def describe(self) -> dict:
        return {"knobs": [k.describe() for k in self.knobs.values()], "kinds": KINDS}


class Settings:
    """Knob values for one run. `s["scale"]` is the value (default when not set); `s.canonical` is True when every
    knob is at its default, i.e. the published task."""
    __slots__ = ("set", "values")

    def __init__(self, ks: KnobSet, values: dict):
        self.set = ks
        vals = {}
        for n, v in values.items():
            if n not in ks.knobs:
                raise SystemExit(f"no knob {n!r}; declared: {sorted(ks.knobs)}")
            v = ks.knobs[n].coerce(v)
            if v != ks.knobs[n].default:
                vals[n] = v
        self.values = vals

    def __getitem__(self, name: str):
        if name in self.values:
            return self.values[name]
        return self.set.knobs[name].default   # KeyError on an undeclared knob, so a typo fails loudly

    def trap_count(self, trap: str) -> int:
        return self[f"trap_count.{trap}"]

    @property
    def canonical(self) -> bool:
        return not self.values

    def record(self) -> dict:
        """The non-default settings, in declaration order, for task.yaml."""
        return {n: self.values[n] for n in self.set.knobs if n in self.values}


def add_knob_args(ap: argparse.ArgumentParser, ks: KnobSet) -> None:
    g = ap.add_argument_group("difficulty knobs (answer moves; written to --out)")
    kinds = {k.kind for k in ks.knobs.values()}
    for kind in ("scale", "rules", "noise", "cross-doc"):
        if kind in kinds:
            k = ks.knobs[FLAG[kind].replace("-", "_")]
            g.add_argument(f"--{k.flag}", default=None, help=f"{k.changes} (default {k.default}, levels {list(k.levels)})")
    if "trap-count" in kinds:
        traps = [k for k in ks.knobs.values() if k.kind == "trap-count"]
        g.add_argument("--trap-count", default=None,
                       help="TRAP=N[+TRAP=N]: planted instances; " + "; ".join(
                           f"{k.trap} (default {k.default}, levels {list(k.levels)}): {k.changes}" for k in traps))
    g.add_argument("--list-knobs", action="store_true", help="print the knob declaration as JSON and exit")
    g.add_argument("--describe", action="store_true", help="print this draw's content counts as JSON and exit")
    if "--out" not in ap._option_string_actions:
        g.add_argument("--out", default=None, help="folder for a knobbed task, or a full copy of the task with no knob "
                                                   "set; the task folder is never overwritten by a knob")


def parse_knob_args(a: argparse.Namespace, ks: KnobSet) -> Settings:
    """Validate the knob flags and return the Settings. Exits after --list-knobs. A knob off its default needs
    --out (or --describe, which writes nothing)."""
    if a.list_knobs:
        print(json.dumps(ks.describe(), indent=2))
        raise SystemExit(0)
    vals = {}
    for k in ks.knobs.values():
        if k.kind != "trap-count":
            raw = getattr(a, k.flag.replace("-", "_"), None)
            if raw is not None:
                vals[k.name] = raw
    raw_tc = getattr(a, "trap_count", None)
    if raw_tc:
        for part in raw_tc.replace(",", "+").split("+"):
            t, eq, n = part.partition("=")
            if not eq:
                raise SystemExit(f"--trap-count {raw_tc!r}: expected TRAP=N[+TRAP=N]")
            name = f"trap_count.{t.strip()}"
            if name not in ks.knobs:
                raise SystemExit(f"--trap-count: no trap-count knob for {t.strip()!r}; declared: "
                                 f"{sorted(k.trap for k in ks.knobs.values() if k.kind == 'trap-count')}")
            vals[name] = n.strip()
    s = Settings(ks, vals)
    if not s.canonical and not a.out and not a.describe:
        raise SystemExit("a knob moves the answer, so the task is written to --out; the task folder is never overwritten")
    return s


def output_dirs(here: str, out: str | None, task_dirs) -> tuple[str, tuple[str, str, str]]:
    """(folder for task.yaml, (workspace, reference, reference_solution)). The task folder when out is None, else a
    clean --out folder. `task_dirs` is bizgen.task_dirs, passed in so this module does not import the package."""
    if out is None:
        return here, task_dirs(here)
    return out, variant_dirs(out)


def record(spec: dict, task_id: str, draw: int, s: Settings) -> dict:
    """Add the knob settings to task.yaml's `variant` record (merged with a trap variant's record if there is one).
    Nothing is added for the published settings, so the default task.yaml is unchanged."""
    if not s.canonical:
        v = spec.setdefault("variant", {"of": task_id, "draw": draw})
        v["knobs"] = s.record()
    return spec


def describe_json(task_id: str, draw: int, s: Settings, counts: dict) -> str:
    """--describe output: the settings, the draw the acceptance loop picked, and the generator's content counts.
    Standard count keys: rows, entities, rules, documents, noise_rate, trap_instances {trap: n}."""
    return json.dumps({"task": task_id, "draw": draw, "knobs": {n: s[n] for n in s.set.knobs},
                       "non_default": s.record(), "counts": counts}, indent=2, sort_keys=False)


def measure_value(counts: dict, measure: str):
    """Look up a dotted measure ("trap_instances.dup_vendor_record") in a --describe counts dict."""
    cur = counts
    for p in measure.split("."):
        cur = cur[p]
    return cur


def steps(k: Knob, v) -> float:
    """How many declared levels above the default a value is (linear between levels; negative below the default)."""
    L = k.levels
    if v <= L[0]:
        return (v - L[0]) / ((L[1] - L[0]) if len(L) > 1 else 1)
    for i, (a, b) in enumerate(zip(L, L[1:])):
        if v <= b:
            return i + (v - a) / (b - a)
    return len(L) - 1 + (v - L[-1]) / ((L[-1] - L[-2]) if len(L) > 1 else 1)
