# Trap switches and mutants: authoring guide

A trap is a pitfall a desk task plants in its inputs (a draft invoice on the revenue sheet, credits in
brackets, a job missing from one export). Every trap is described by one sentence in `task.yaml`
`traps`, ending with the checks that catch it: `(checks: Harborview revenue; total margin)`.

This guide adds two things to a generator, following `tasks/desk/project-margin/gen.py`:

* **Switches.** Each trap that can be removed without changing the correct answer can be turned off.
  The generator then writes the same task, from the same random draw, with that pitfall gone. Variants
  are how difficulty is measured by experiment instead of guessed.
* **Mutants.** For every trap, the generator can write a deliverable that is right in every respect
  except that it falls for that one trap. The grader must fail it on the checks the trap cites. Mutants
  are how the grader is tested.

Library: `tasks/lib/bizgen/traps.py`. Checks: `bench/validate_traps.py`, `bench/check_retrofit.py`.

Switches only make a task easier. To make one harder (more rows, rules, noise, planted instances, a rule that needs
a second document) add **difficulty knobs** instead: `docs/authoring-knobs.md`. A knob moves the answer; a switch
must not.

## Rules

1. **No flags, no change.** With no trap flag the generator's output is byte-identical to before, in
   the same Python environment. `check_retrofit.py` enforces this against HEAD.
2. **No slower.** A switch is `traps.on("name")`, a frozenset lookup. Do not add passes over the data on
   the default path. `check_retrofit.py` fails a generator more than 10% + 50 ms slower than HEAD.
3. **Same draw.** Never change what `build()` draws or the order it draws it in. Neutralise a trap at
   render time (when writing the workspace files) whenever you can. If the trap is created inside
   `build()`, draw exactly as before and override the result afterwards. The acceptance loop in
   `__main__` runs unchanged, with every trap on; variants reuse the draw it picked.
4. **Same answer.** A switchable trap, turned off, must leave `checks`, `reference/` and
   `reference_solution/` byte-identical. If removing the pitfall would change the correct answer, the
   trap is **fixed**, not switchable. Declare it anyway, so the graph sees it and it gets a mutant.
5. **Never write over the task folder.** Variants and mutants go to `--out`. `parse_trap_args` refuses
   otherwise. `--out` alone writes a full copy of the task there (this is also how sealed seeds are made).
6. **Removing a pitfall must not add one.** If the pitfall lives in a file the agent is told about (a
   note says "the hours in the unbilled file..."), update that sentence in the variant so the agent is
   not sent looking for something that is not there. Keep every other word identical.
7. **Dependencies.** A trap that only exists inside another (bracketed credits are a formatting pitfall)
   is declared with `requires={"credit_brackets": "format_noise"}`; turning the outer one off turns the
   inner one off.

## Steps

1. Read `task.yaml` `traps` and the generator. Give each trap sentence a short key (`drafts`,
   `join_key`). Several sentences can share a key only if they describe the same pitfall.
2. Decide switchable or fixed for each. Ask: can the pitfall be removed while every expected value in
   `checks` and every file in `reference/` stays the same? Typical switchable traps: formatting noise,
   extra rows the answer excludes (drafts, voids, duplicates), a second file the answer needs (merge it
   into the main one), a noisy join key (use the clean key), an ambiguous label (use the clear one).
   Typical fixed traps: an entity with no rows that must still be reported, a zero that must not divide.
3. Declare, after the imports:
   ```python
   from bizgen.traps import TrapSet, add_trap_args, parse_trap_args, variant_dirs, active_trap_text
   TRAPS = TrapSet(switchable={...}, fixed={...}, requires={...})
   TRAP_KEYS = [...]   # one key per task.yaml trap sentence, in order
   ```
4. Thread `traps` into the code that writes the workspace. Keep dicts built in the same key order
   when every trap is on. Wrap the trap sentences in `task.yaml` with
   `active_trap_text([...], TRAP_KEYS, traps)`; write `task.yaml` to `out or HERE`, and add
   `spec["variant"] = {"of": <id>, "draw": seed, "traps_off": sorted(traps.off)}` when
   `not traps.canonical`. Use `task_dirs(HERE)` when `out is None`, else `variant_dirs(out)`.
5. Mutants: `write_mutant(d, trap, out)` writes the deliverable files into `out`, right except for that
   trap, reusing the reference-solution code with the one mistake applied. It should look like what an
   agent that fell for the trap would hand over (including a memo that follows from its own numbers).
   `MUTANTS = {k: write_mutant for k in TRAP_KEYS}`.
6. `__main__`: `add_trap_args(ap)` after the existing arguments; `traps = parse_trap_args(a, TRAPS,
   MUTANTS, TRAP_KEYS)`; pass `traps, a.out, a.mutant` into `emit`. `--list-traps` must exit before the
   acceptance loop.
7. Accept:
   ```bash
   python bench/check_retrofit.py <task> --python <interpreter without lxml>
   ```
   Byte identity and speed use the interpreter given (the published files were generated without
   lxml); trap validation grades every variant and mutant with LibreOffice.

## Cases met in the first 24 retrofits

* **Task-local check modules.** If `task.yaml` uses a `custom` check or `plan_feasible` with a module in
  the task folder (`check.py`), copy it into `--out` so a variant or copy can be graded on its own.
* **Hand-written `task.yaml`.** Some generators never write `task.yaml`. With `--out`, copy it byte for
  byte; for a variant, load it, filter `traps` with `active_trap_text`, add the `variant` record, and
  dump it.
* **Random draws at render time.** Some generators also draw in `emit()`. Draw for every row exactly as
  before and drop the removed rows afterwards, so the rest of the file does not change.
* **Composite sentences.** When one sentence describes a removable part and a part the answer depends
  on, the switch removes only the removable part; say so in the trap description. If nothing can be
  removed without moving the answer, the trap is fixed.
* **Notes that are not traps.** A sentence such as "expected values pinned to seed 0" is declared fixed
  and has no mutant.
* **Grader-blind mutants.** A faithful mutant that passes a check its trap cites is a grader finding:
  keep the function, leave it out of `MUTANTS`, and record the check and reason in a comment next to
  `MUTANTS`.

## Reading validation output

* `variant ... workspace identical`: the switch does nothing. Fix the switch, or the trap is not real.
* `reference/ differs`: the answer moved. The trap is fixed, not switchable, or the neutralisation leaks.
* `mutant 'x' passes cited check(s)`: either the mutant is not a faithful mistake, or the check does not
  catch the mistake its trap names. The second is a grader finding: report it, do not weaken the mutant.
* `also fails: ...` is informational: a mistake usually knocks over more checks than the trap cites.
* A trap citation that resolves to no check is a documentation defect in `task.yaml`; list it in the
  report rather than rewriting published task files.
