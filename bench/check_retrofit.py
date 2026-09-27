#!/usr/bin/env python3
"""Acceptance check for adding trap switches to an existing desk generator.

    check_retrofit.py TASK_ID [TASK_ID ...] [--runs 5] [--skip-validate] [--python PATH]

For each task:
  1. Byte identity. The generator at HEAD and the working-tree generator are run in the same Python
     environment; the working-tree one writes a canonical copy with `--out`. workspace/, reference/,
     reference_solution/ and task.yaml must be byte-identical. Neither run touches the task folder:
     the HEAD generator runs from a temporary copy of the task.
  2. Speed. Median wall time over --runs runs of each; the switched generator may not be slower than
     HEAD by more than 10% + 50 ms (process start-up noise).
  3. Trap validation: bench/validate_traps.py on the task (variants keep the answer, mutants are caught).

--python (or BENCH_GEN_PYTHON) picks the interpreter for step 1 and 2. Use the environment the published
files were generated in: without lxml, since openpyxl serialises differently when lxml is installed.

Exit status is non-zero if any task fails any step. Offline authoring tooling only.
"""
from __future__ import annotations

import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_traps import same_tree, validate  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESK = os.path.join(ROOT, "tasks", "desk")
PARTS = ("workspace", "reference", "reference_solution")


def head_copy(task_id: str, dst: str) -> str:
    """A temporary tree tmp/tasks/desk/<id> holding HEAD's gen.py (plus any task-local modules at HEAD),
    with tmp/tasks/lib pointing at the real library, so HEAD's generator writes only inside tmp."""
    td = os.path.join(dst, "tasks", "desk", task_id)
    os.makedirs(td)
    os.symlink(os.path.join(ROOT, "tasks", "lib"), os.path.join(dst, "tasks", "lib"))
    files = subprocess.run(["git", "-C", ROOT, "ls-tree", "-r", "--name-only", "HEAD", f"tasks/desk/{task_id}/"],
                           capture_output=True, text=True, check=True).stdout.split()
    for f in files:
        rel = os.path.relpath(f, f"tasks/desk/{task_id}")
        if rel.split(os.sep)[0] in PARTS:
            continue
        data = subprocess.run(["git", "-C", ROOT, "show", f"HEAD:{f}"], capture_output=True, check=True).stdout
        os.makedirs(os.path.dirname(os.path.join(td, rel)) or td, exist_ok=True)
        with open(os.path.join(td, rel), "wb") as fh:
            fh.write(data)
    return td


def timed(cmd: list[str], cwd: str) -> float:
    t = time.perf_counter()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{r.stderr[-1500:]}")
    return time.perf_counter() - t


def check(task_id: str, runs: int, do_validate: bool, py: str = sys.executable) -> list[str]:
    problems = []
    tmp = tempfile.mkdtemp(prefix=f"retrofit-{task_id}-")
    try:
        old_dir = head_copy(task_id, tmp)
        new_out = os.path.join(tmp, "new")
        new_gen = os.path.join(DESK, task_id, "gen.py")
        t_old = [timed([py, "gen.py"], old_dir) for _ in range(runs)]
        t_new = [timed([py, new_gen, "--out", new_out], os.path.join(DESK, task_id)) for _ in range(runs)]
        for part in PARTS:
            a, b = os.path.join(old_dir, part), os.path.join(new_out, part)
            if os.path.isdir(a) != os.path.isdir(b) or (os.path.isdir(a) and not same_tree(a, b)):
                problems.append(f"{part}/ differs from HEAD's output")
        with open(os.path.join(old_dir, "task.yaml"), "rb") as fa, open(os.path.join(new_out, "task.yaml"), "rb") as fb:
            if fa.read() != fb.read():
                problems.append("task.yaml differs from HEAD's output")
        mo, mn = statistics.median(t_old), statistics.median(t_new)
        speed = f"{mo * 1000:.0f} ms -> {mn * 1000:.0f} ms"
        if mn > mo * 1.10 + 0.05:
            problems.append(f"generator slower: {speed}")
        print(f"{task_id}: bytes {'identical' if not problems else 'DIFFER'}; median {speed}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if do_validate:
        r = validate(task_id)
        problems += r["problems"]
        print(f"{task_id}: validate_traps {'OK' if r['ok'] else 'PROBLEMS'} "
              f"({len(r['variants'])} variants, {len(r['mutants'])} mutants)")
    for p in problems:
        print(f"  ! {p}")
    return problems


def main(argv: list[str]) -> int:
    runs, do_validate, ids = 5, True, []
    py = os.environ.get("BENCH_GEN_PYTHON", sys.executable)
    it = iter(argv)
    for a in it:
        if a == "--runs":
            runs = int(next(it))
        elif a == "--python":
            py = next(it)
        elif a == "--skip-validate":
            do_validate = False
        else:
            ids.append(a)
    if not ids:
        print(__doc__)
        return 2
    bad = sum(bool(check(t, runs, do_validate, py)) for t in ids)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
