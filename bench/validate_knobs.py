#!/usr/bin/env python3
"""Validate a generator's difficulty knobs (tasks/lib/bizgen/knobs.py).

    validate_knobs.py [task_id ...] [--seeds default,1] [--no-naive] [--json PATH] [--keep DIR]

Runs only on generators that declare knobs (`gen.py --list-knobs`); others are skipped. A knob, unlike a trap
switch, is expected to move the answer. What must hold instead, for every declared level of every knob and for
every knob at its top level at once, per seed:

  1. complete and self-consistent: the reference solution passes the task's own (recomputed) checks and the
     untouched workspace fails them; task.yaml records the settings as `variant.knobs`;
  2. alive: the workspace differs from the default setting of the same seed (a knob that changes nothing is dead);
  3. deterministic: the same flags twice give byte-identical folders;
  4. monotone in content: the knob's declared `measure` in `--describe` strictly increases along its levels;
  5. default untouched: with no knob flag the generator reproduces the published task folder byte for byte (in
     this interpreter), and the published folder is unchanged after the run.

Without LibreOffice, workbook checks are recalculated by the `formulas` engine, which cannot evaluate SUMIFS and
similar functions. A reference failure is put down to the environment only when every failed check is a workbook
(or task-module) check that the published task's own reference also fails here; it is then reported as
UNVERIFIED-XLSX (env), not as a defect. If the generator has --naive, the naive solution for each setting is graded
too and its failed checks are reported (informational: how many pitfalls a careless worker hits).

--seeds picks draws; `default` is the published seed. Generation uses BENCH_GEN_PYTHON (the interpreter without
lxml, like check_retrofit.py) or this interpreter. Offline authoring tooling; the runner and grader are unchanged.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grade import grade  # noqa: E402
from validate_traps import failed, same_tree  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESK = os.path.join(ROOT, "tasks", "desk")
PARTS = ("workspace", "reference", "reference_solution")
XLSX_TYPES = {"xlsx_value_present", "xlsx_no_errors", "xlsx_has_formulas", "custom", "plan_feasible"}
ENV_UNVERIFIED = "UNVERIFIED-XLSX (env)"


def gen_python() -> str:
    return os.environ.get("BENCH_GEN_PYTHON") or sys.executable


def declares_knobs(task_dir: str) -> bool:
    gen = os.path.join(task_dir, "gen.py")
    if not os.path.isfile(gen):
        return False
    with open(gen) as f:
        return "add_knob_args" in f.read()


def run_gen(task_dir: str, *args: str) -> str:
    r = subprocess.run([gen_python(), os.path.join(task_dir, "gen.py"), *args], capture_output=True, text=True,
                       cwd=task_dir)
    if r.returncode != 0:
        raise RuntimeError(f"gen.py {' '.join(args)} failed:\n{r.stderr[-2000:]}")
    return r.stdout


def knob_flags(decl: dict, values: dict) -> list[str]:
    """Command-line flags for {knob name: value}."""
    by = {k["name"]: k for k in decl["knobs"]}
    args, tc = [], []
    for n, v in values.items():
        k = by[n]
        if k["kind"] == "trap-count":
            tc.append(f"{k['trap']}={v}")
        else:
            args += [k["flag"], str(v)]
    if tc:
        args += ["--trap-count", "+".join(tc)]
    return args


def measure(counts: dict, path: str):
    cur = counts
    for p in path.split("."):
        cur = cur[p]
    return cur


def tree_digest(d: str) -> dict:
    import hashlib
    out = {}
    for base, _, files in sorted(os.walk(d)):
        for f in sorted(files):
            p = os.path.join(base, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, d)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def published_digest(td: str) -> dict:
    return {k: v for k, v in tree_digest(td).items() if k.split(os.sep)[0] in PARTS or k == "task.yaml"}


def settings(decl: dict) -> list[tuple[str, dict]]:
    """(label, {knob: value}) for every non-default level of every knob, then every knob at its top level."""
    out = []
    for k in decl["knobs"]:
        for v in k["levels"][1:]:
            out.append((f"{k['name']}={v}", {k["name"]: v}))
    if len(decl["knobs"]) > 1:
        out.append(("ALL-MAX", {k["name"]: k["levels"][-1] for k in decl["knobs"]}))
    return out


def verdict(ref: dict, canon_failed: set[str]) -> str:
    bad = failed(ref)
    if ref["passed"] and not bad:
        return "VERIFIED"
    types = {c["name"]: c["type"] for c in ref["checks"]}
    if bad <= canon_failed and all(types.get(n) in XLSX_TYPES for n in bad):
        return ENV_UNVERIFIED
    return "FAIL"


def validate(task_id: str, seeds: list[str | None], naive: bool = True, keep: str | None = None) -> dict:
    td = os.path.join(DESK, task_id)
    decl = json.loads(run_gen(td, "--list-knobs"))
    work = keep or tempfile.mkdtemp(prefix=f"knobs-{task_id}-")
    os.makedirs(work, exist_ok=True)
    before = published_digest(td)
    has_naive = "--naive" in run_gen(td, "--help")
    canon_failed = failed(grade(td, os.path.join(td, "reference_solution")))
    report = {"task": task_id, "declared": decl, "python": gen_python(), "settings": [], "problems": [],
              "published_reference_fails_here": sorted(canon_failed)}
    for k in decl["knobs"]:
        if not k.get("measure"):
            report["problems"].append(f"knob {k['name']} declares no measure")
        if k["levels"][0] != k["default"]:
            report["problems"].append(f"knob {k['name']}: levels do not start at the default")

    for seed in seeds:
        sargs = [] if seed is None else ["--seed", str(seed)]
        tag = "default" if seed is None else f"s{seed}"
        base = os.path.join(work, f"{tag}__base")
        run_gen(td, *sargs, "--out", base)
        if seed is None:
            got = tree_digest(base)
            pub = published_digest(td)
            if got != pub:
                diff = sorted(set(k for k in set(got) | set(pub) if got.get(k) != pub.get(k)))
                report["problems"].append(f"no knob flag does not reproduce the published task here: {diff[:6]}")
        base_desc = json.loads(run_gen(td, *sargs, "--describe"))["counts"]
        for label, vals in settings(decl):
            flags = knob_flags(decl, vals)
            out = os.path.join(work, f"{tag}__{label.replace('=', '-').replace('.', '_')}")
            rec = {"seed": seed, "setting": label, "knobs": vals, "problems": []}
            try:
                run_gen(td, *sargs, *flags, "--out", out)
                run_gen(td, *sargs, *flags, "--out", out + "__again")
                desc = json.loads(run_gen(td, *sargs, *flags, "--describe"))
            except RuntimeError as e:
                rec["problems"].append(str(e).splitlines()[0] + " " + str(e).splitlines()[-1])
                report["settings"].append(rec)
                report["problems"] += [f"{tag} {label}: {p}" for p in rec["problems"]]
                continue
            rec["counts"] = desc["counts"]
            if not same_tree(out, out + "__again"):
                rec["problems"].append("not deterministic: the same flags twice give different bytes")
            shutil.rmtree(out + "__again", ignore_errors=True)
            spec = yaml.safe_load(open(os.path.join(out, "task.yaml")))
            got = (spec.get("variant") or {}).get("knobs")
            if got != vals:
                rec["problems"].append(f"task.yaml variant.knobs is {got}, expected {vals}")
            if same_tree(os.path.join(out, "workspace"), os.path.join(base, "workspace")):
                rec["problems"].append("workspace identical to the default setting: the knob does nothing")
            rec["answer_moved"] = not same_tree(os.path.join(out, "reference"), os.path.join(base, "reference"))
            ref = grade(out, os.path.join(out, "reference_solution"))
            ws = grade(out, os.path.join(out, "workspace"))
            rec["reference"] = verdict(ref, canon_failed)
            rec["reference_failed"] = sorted(failed(ref))
            if rec["reference"] == "FAIL":
                rec["problems"].append(f"reference solution fails its own checks: {rec['reference_failed']}")
            if ws["passed"]:
                rec["problems"].append("untouched workspace passes")
            if has_naive and naive:
                nd = os.path.join(work, f"{tag}__naive__{label.replace('=', '-').replace('.', '_')}")
                try:
                    run_gen(td, *sargs, *flags, "--naive", nd, "--out", nd + "__unused")
                    rec["naive_failed"] = sorted(failed(grade(out, nd)))
                except RuntimeError as e:
                    rec["naive_failed"] = [f"(naive generation failed: {str(e).splitlines()[-1]})"]
                shutil.rmtree(nd + "__unused", ignore_errors=True)
            if len(vals) == 1:
                (name, v), = vals.items()
                k = next(x for x in decl["knobs"] if x["name"] == name)
                i = k["levels"].index(v)
                prev = k["levels"][i - 1]
                try:
                    now_m = measure(desc["counts"], k["measure"])
                    if i == 1:
                        prev_m = measure(base_desc, k["measure"])
                    else:
                        prev_m = next(measure(s["counts"], k["measure"]) for s in report["settings"]
                                      if s["seed"] == seed and s["knobs"] == {name: prev} and "counts" in s)
                    rec["measure"] = {k["measure"]: [prev_m, now_m]}
                    if not now_m > prev_m:
                        rec["problems"].append(f"measure {k['measure']} does not increase: {prev} -> {v} gives "
                                               f"{prev_m} -> {now_m}")
                except (KeyError, StopIteration, TypeError) as e:
                    rec["problems"].append(f"measure {k['measure']} not readable from --describe: {e!r}")
            report["settings"].append(rec)
            report["problems"] += [f"{tag} {label}: {p}" for p in rec["problems"]]
    if published_digest(td) != before:
        report["problems"].append("the published task folder changed during validation")
    if not keep:
        shutil.rmtree(work, ignore_errors=True)
    report["ok"] = not report["problems"]
    return report


def main(argv: list[str]) -> int:
    args, json_out, keep, seeds, naive = [], None, None, [None], True
    it = iter(argv)
    for a in it:
        if a == "--json":
            json_out = next(it)
        elif a == "--keep":
            keep = next(it)
        elif a == "--seeds":
            seeds = [None if s.strip() in ("", "default") else int(s) for s in next(it).split(",")]
        elif a == "--no-naive":
            naive = False
        else:
            args.append(a)
    ids = args or sorted(d for d in os.listdir(DESK) if declares_knobs(os.path.join(DESK, d)))
    reports, bad = [], 0
    for tid in ids:
        if not declares_knobs(os.path.join(DESK, tid)):
            print(f"{tid}: no knobs declared, skipped")
            continue
        r = validate(tid, seeds, naive, os.path.join(keep, tid) if keep else None)
        reports.append(r)
        print(f"{tid}: {'OK' if r['ok'] else 'PROBLEMS'}  {len(r['declared']['knobs'])} knobs, "
              f"{len(r['settings'])} settings")
        for s in r["settings"]:
            seed = "default" if s["seed"] is None else s["seed"]
            m = "; ".join(f"{k} {a}->{b}" for k, (a, b) in s.get("measure", {}).items())
            nv = f"; naive fails {len(s['naive_failed'])}" if "naive_failed" in s else ""
            st = "ok" if not s["problems"] else "; ".join(s["problems"])
            print(f"  [{seed}] {s['setting']:44} ref {s.get('reference', '-'):22} "
                  f"answer {'moved' if s.get('answer_moved') else 'same '}  {m}{nv}  {st}")
        for p in r["problems"]:
            print(f"  ! {p}")
        bad += not r["ok"]
    if json_out:
        with open(json_out, "w") as f:
            json.dump(reports, f, indent=2, default=str)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
