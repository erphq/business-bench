#!/usr/bin/env python3
"""Validate a task's trap switches and per-trap mutants.

    validate_traps.py [task_id ...] [--json PATH] [--keep DIR]

Runs only on generators that declare traps (`gen.py --list-traps`); others are skipped. For each task:

Variants (difficulty knobs). For every switchable trap, and for all of them at once, the generator writes the
task with that pitfall removed. A variant must
  1. keep the answer: checks identical to the canonical task.yaml, reference/ and reference_solution/
     byte-identical to a canonical copy generated in the same environment;
  2. actually change the workspace (a switch that changes nothing is a dead knob);
  3. stay solvable and non-trivial: the reference solution passes, the untouched workspace fails.

Mutants (grader sensitivity). For every trap, switchable or fixed, the generator writes a deliverable that
is right except that it falls for that one trap. The mutant must fail every check the trap's sentence in
task.yaml cites. Extra failed checks are reported, not failures: they mean the prose under-cites.

This is offline authoring tooling. The runner and the grader are unchanged, and nothing here runs during an
evaluation. Cost is one generator run and one grade per variant and per mutant.
"""
from __future__ import annotations

import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade import grade  # noqa: E402
from trap_links import trap_links  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESK = os.path.join(ROOT, "tasks", "desk")


def declares_traps(task_dir: str) -> bool:
    gen = os.path.join(task_dir, "gen.py")
    if not os.path.isfile(gen):
        return False
    with open(gen) as f:
        return "add_trap_args" in f.read()


def run_gen(task_dir: str, *args: str) -> str:
    r = subprocess.run([sys.executable, os.path.join(task_dir, "gen.py"), *args],
                       capture_output=True, text=True, cwd=task_dir)
    if r.returncode != 0:
        raise RuntimeError(f"gen.py {' '.join(args)} failed:\n{r.stderr[-2000:]}")
    return r.stdout


def same_tree(a: str, b: str) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    return not mismatch and not errors and all(same_tree(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)


def failed(result: dict) -> set[str]:
    return {c["name"] for c in result["checks"] if c["required"] and not c["passed"]}


def validate(task_id: str, keep: str | None = None) -> dict:
    td = os.path.join(DESK, task_id)
    decl = json.loads(run_gen(td, "--list-traps"))
    canon = yaml.safe_load(open(os.path.join(td, "task.yaml")))
    links = trap_links(canon)
    work = keep or tempfile.mkdtemp(prefix=f"traps-{task_id}-")
    report = {"task": task_id, "declared": decl, "variants": [], "mutants": [], "problems": []}

    # Which trap key each task.yaml sentence belongs to, in sentence order.
    keys = decl.get("sentence_keys") or []
    if len(keys) != len(links):
        report["problems"].append(f"{len(keys)} trap keys for {len(links)} trap sentences in task.yaml")
        return report
    cites_by_key: dict[str, set[str]] = {}
    for k, link in zip(keys, links):
        for c in link["cites"]:
            if c["status"] == "ok":
                cites_by_key.setdefault(k, set()).add(c["check"])
            else:
                report["problems"].append(f"trap {k!r} cites {c['cite']!r}, which matches no single check")

    # A fresh canonical copy from this environment, so byte comparisons are like for like (xlsx bytes
    # depend on the XML serialiser installed, not on the task).
    base = os.path.join(work, "canonical")
    run_gen(td, "--out", base)
    if yaml.safe_load(open(os.path.join(base, "task.yaml"))).get("checks") != canon.get("checks"):
        report["problems"].append("regenerating the task does not reproduce the published checks")
    if not same_tree(os.path.join(base, "reference"), os.path.join(td, "reference")):
        report["problems"].append("regenerating the task does not reproduce the published reference/")

    # ---- variants ----
    switchable = list(decl["switchable"])
    for off in [[t] for t in switchable] + [switchable]:
        label = ",".join(off)
        out = os.path.join(work, "variant-" + ("ALL" if len(off) > 1 else label))
        run_gen(td, "--traps-off", label, "--out", out)
        v = yaml.safe_load(open(os.path.join(out, "task.yaml")))
        rec = {"off": off, "effective_off": v.get("variant", {}).get("traps_off", off), "problems": []}
        if v.get("checks") != canon.get("checks"):
            rec["problems"].append("checks differ from the canonical task: the answer moved")
        if not same_tree(os.path.join(out, "reference"), os.path.join(base, "reference")):
            rec["problems"].append("reference/ differs from the canonical task: the answer moved")
        if not same_tree(os.path.join(out, "reference_solution"), os.path.join(base, "reference_solution")):
            rec["problems"].append("reference_solution/ differs from the canonical task")
        if same_tree(os.path.join(out, "workspace"), os.path.join(base, "workspace")):
            rec["problems"].append("workspace identical to the canonical task: the switch does nothing")
        ref_res = grade(out, os.path.join(out, "reference_solution"))
        if not ref_res["passed"]:
            rec["problems"].append(f"reference solution fails: {sorted(failed(ref_res))}")
        ws_res = grade(out, os.path.join(out, "workspace"))
        if ws_res["passed"]:
            rec["problems"].append("untouched workspace passes")
        report["variants"].append(rec)
        report["problems"] += [f"variant off={label}: {p}" for p in rec["problems"]]

    # ---- mutants ----
    for trap in decl.get("mutants", []):
        out = os.path.join(work, "mutant-" + trap)
        if os.path.isdir(out):
            shutil.rmtree(out)
        run_gen(td, "--mutant", trap, "--out", out)
        res = grade(td, out)
        want = cites_by_key.get(trap, set())
        got = failed(res)
        rec = {"trap": trap, "cited": sorted(want), "failed": sorted(got),
               "missed": sorted(want - got), "extra": sorted(got - want)}
        if not want:
            rec["note"] = "trap cites no check"
        if want - got:
            report["problems"].append(f"mutant {trap!r} passes cited check(s) {sorted(want - got)}: "
                                      "the check does not detect the mistake its trap names")
        if not got:
            report["problems"].append(f"mutant {trap!r} passes every check: the grader cannot see this trap")
        report["mutants"].append(rec)
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    report["ok"] = not report["problems"]
    return report


def main(argv: list[str]) -> int:
    args, json_out, keep = [], None, None
    it = iter(argv)
    for a in it:
        if a == "--json":
            json_out = next(it)
        elif a == "--keep":
            keep = next(it)
        else:
            args.append(a)
    ids = args or sorted(d for d in os.listdir(DESK) if declares_traps(os.path.join(DESK, d)))
    reports, bad = [], 0
    for tid in ids:
        if not declares_traps(os.path.join(DESK, tid)):
            print(f"{tid}: no trap switches declared, skipped")
            continue
        r = validate(tid, os.path.join(keep, tid) if keep else None)
        reports.append(r)
        print(f"{tid}: {'OK' if r['ok'] else 'PROBLEMS'}  "
              f"{len(r['variants'])} variants, {len(r['mutants'])} mutants")
        for v in r["variants"]:
            print(f"  variant off={','.join(v['off']):40} {'ok' if not v['problems'] else '; '.join(v['problems'])}")
        for m in r["mutants"]:
            status = "ok" if not m["missed"] and m["failed"] else "MISSED " + ", ".join(m["missed"] or ["(nothing failed)"])
            extra = f"  (also fails: {', '.join(m['extra'])})" if m["extra"] else ""
            print(f"  mutant {m['trap']:18} {status}{extra}")
        for p in r["problems"]:
            print(f"  ! {p}")
        bad += not r["ok"]
    if json_out:
        with open(json_out, "w") as f:
            json.dump(reports, f, indent=2)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
