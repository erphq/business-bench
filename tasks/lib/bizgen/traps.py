"""Individually switchable traps and per-trap mutants for task generators.

A generator declares its traps once, beside the prose in task.yaml:

    TRAPS = TrapSet(
        switchable={"drafts": "draft and written-off invoices are not revenue", ...},
        fixed={"zero_div": "margin % must survive a job with zero revenue"},
    )

`switchable` traps can be turned off. Turning one off must remove the pitfall and leave the correct answer
unchanged, so the variant's checks, reference, and reference solution equal the canonical task's and the only
thing that moved is how hard the task is. `fixed` traps are part of the answer and cannot be removed
without changing it; they are declared so the measurement graph still sees them.

Cost and determinism rules the generators follow:

* With no flags every trap is on and the generator's output is byte-identical to the unswitched generator.
  A switch is one frozenset lookup.
* A trap that is off never changes how many random numbers are drawn: the generator draws as usual and
  neutralises the result, so variant and canonical share one underlying draw ("same seed, one thing
  different"). The acceptance loop always runs with every trap on and the variant reuses the draw it picked.
* Variants and mutants are written under --out, never over the canonical task folder. --out with no other
  trap flag writes the full task there, which is how a sealed seed is generated without touching the
  published files.

A mutant is a deliverable that falls for exactly one trap. `bench/validate_traps.py` checks that every
mutant fails every check its trap names, which makes each trap's check a tested negative control.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil


class TrapSet:
    __slots__ = ("switchable", "fixed", "requires", "off")

    def __init__(self, switchable: dict[str, str], fixed: dict[str, str] | None = None,
                 requires: dict[str, str] | None = None, off: frozenset[str] = frozenset()):
        """`requires` maps a trap to the trap it only exists inside: {"credit_brackets": "format_noise"}
        means brackets are a formatting pitfall, so removing the formatting noise removes them too."""
        fixed = dict(fixed or {}); requires = dict(requires or {})
        overlap = set(switchable) & set(fixed)
        if overlap:
            raise ValueError(f"trap declared both switchable and fixed: {sorted(overlap)}")
        for a, b in requires.items():
            if a not in switchable or b not in switchable:
                raise ValueError(f"requires {a!r} -> {b!r}: both must be switchable traps")
        unknown = set(off) - set(switchable)
        if unknown:
            raise ValueError(f"cannot switch off {sorted(unknown)}: not a switchable trap "
                             f"(switchable: {sorted(switchable)}; fixed: {sorted(fixed)})")
        off = set(off)
        changed = True
        while changed:  # close over chains of requirements
            extra = {a for a, b in requires.items() if b in off and a not in off}
            off |= extra; changed = bool(extra)
        self.switchable = dict(switchable)
        self.fixed = fixed
        self.requires = requires
        self.off = frozenset(off)

    def with_off(self, names) -> "TrapSet":
        return TrapSet(self.switchable, self.fixed, self.requires, frozenset(names))

    def on(self, name: str) -> bool:
        """True unless `name` was switched off. Raises on a name that is not declared, so a typo in a
        generator fails loudly instead of silently leaving a trap on."""
        if name in self.off:
            return False
        if name in self.switchable or name in self.fixed:
            return True
        raise KeyError(f"undeclared trap {name!r}")

    @property
    def canonical(self) -> bool:
        return not self.off

    @property
    def names(self) -> list[str]:
        return list(self.switchable) + list(self.fixed)

    def describe(self) -> dict:
        return {"switchable": self.switchable, "fixed": self.fixed, "requires": self.requires,
                "off": sorted(self.off)}


def add_trap_args(ap: argparse.ArgumentParser) -> None:
    g = ap.add_argument_group("trap switches (difficulty variants and mutation testing)")
    g.add_argument("--traps-off", default="", help="comma-separated switchable traps to remove; needs --out")
    g.add_argument("--mutant", default=None, help="write a deliverable that falls for this one trap to --out")
    g.add_argument("--out", default=None, help="folder for a variant task or a mutant; alone, a copy of the task "
                                               "(e.g. a sealed seed) written there instead of the task folder")
    g.add_argument("--list-traps", action="store_true", help="print the trap declaration as JSON and exit")


def parse_trap_args(a: argparse.Namespace, traps: TrapSet, mutants: dict | None = None,
                    sentence_keys: list[str] | None = None) -> TrapSet:
    """Validate the trap flags and return the configured TrapSet. Exits after --list-traps.
    `sentence_keys[i]` is the trap described by the i-th sentence of task.yaml `traps`."""
    if a.list_traps:
        desc = traps.describe()
        desc["mutants"] = sorted(mutants or {})
        desc["sentence_keys"] = list(sentence_keys or [])
        print(json.dumps(desc, indent=2))
        raise SystemExit(0)
    off = [t.strip() for t in a.traps_off.split(",") if t.strip()]
    if (off or a.mutant) and not a.out:
        raise SystemExit("--traps-off and --mutant write to --out; the canonical task folder is never overwritten")
    if a.mutant is not None and a.mutant not in (mutants or {}):
        raise SystemExit(f"no mutant for {a.mutant!r}; available: {sorted(mutants or {})}")
    try:
        return traps.with_off(off)
    except ValueError as e:
        raise SystemExit(str(e))


def variant_dirs(out: str) -> tuple[str, str, str]:
    """(workspace, reference, reference_solution) under a variant folder, wiped clean."""
    dirs = tuple(os.path.join(out, d) for d in ("workspace", "reference", "reference_solution"))
    for d in dirs:
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    return dirs  # type: ignore[return-value]


def active_trap_text(texts: list[str], keys: list[str], traps: TrapSet) -> list[str]:
    """The task.yaml `traps` prose for the traps still on. `keys[i]` names the trap behind `texts[i]`."""
    if len(texts) != len(keys):
        raise ValueError("one trap key per trap sentence")
    return [t for t, k in zip(texts, keys) if traps.on(k)]

