# Difficulty knobs: authoring guide

A trap switch removes a pitfall and leaves the answer where it was (`docs/authoring-traps.md`). A **knob** goes the
other way: it makes a task bigger, stricter or messier, and the answer is expected to move with it. Knobs are how a
saturated task is re-hardened (`docs/renewable.md`) and how the delegation envelope gets its axes: volume, rule
count, exception rate, and rules that need a second document.

Library: `tasks/lib/bizgen/knobs.py`. Checks: `bench/validate_knobs.py`, `bench/check_retrofit.py`.
Worked example: `tasks/desk/duplicate-payments/gen.py`.

## Kinds and flags

Every knob takes a value, so `bench/renew.py search --knob NAME=V1,V2` can pass any of them.

| kind | knob name | flag | what it moves |
|---|---|---|---|
| scale | `scale` | `--scale N` | rows or entities (invoices, clinicians, lots) |
| rules | `rules` | `--rules N` | number of business rules in play (bands, rate changes, policy clauses) |
| noise | `noise` | `--noise F` | rate of malformed or messy records, 0..1 |
| trap-count | `trap_count.<trap>` | `--trap-count TRAP=N[+TRAP=N]` | planted instances of an existing trap |
| cross-doc | `cross_doc` | `--cross-doc N` | rules that need a second document (0/1 or a count) |

Every generator with knobs also answers:

* `--list-knobs`: the declaration as JSON (name, kind, flag, default, levels, range, what it changes, the
  `--describe` count it moves). Exits before the acceptance loop.
* `--describe`: the content of this draw as JSON (rows, entities, rules, documents, noise rate, planted trap
  instances), for any seed and knob setting. Nothing is written. Seeds can be matched on content with it.
* `--out DIR`: where a knobbed task is written. With no knob, `--out` writes a full copy of the published task, so
  renew.py no longer needs a shadow copy.

## Rules

1. **No flags, no change.** With no knob flag the output is byte-identical to HEAD and no slower
   (`check_retrofit.py`, in the interpreter without lxml). The defaults *are* the published task.
2. **Never change the default draws.** Code that only runs at a non-default value goes behind
   `if knobs[...] != default`. Draw knob-only content from its own stream (`rk = rng(seed + <large odd constant>)`)
   after the default draws where you can, so a harder task is the published one plus more. A multiplier on an
   existing draw (`r.randint(3, 7) * knobs["scale"]`) is fine: at the default it multiplies by 1. A noise rate that
   replaces a literal (`r.random() < 0.15`) must default to exactly that float.
3. **Complete and self-consistent.** A knobbed task is a whole task in `--out`: workspace, `reference/`,
   `reference_solution/`, and `task.yaml` with every check recomputed from the new draw (`must_match_keys`, phrases,
   counts). `record(spec, id, draw, knobs)` adds `variant: {of, draw, knobs}`. Notes and emails in the workspace must
   stay true: if a rules knob adds a rule, the policy states it; if prose says "30 lots", it says the new number
   (only in knobbed output). Trap sentences name the extra planted instances.
4. **Checks computed from data.** A task whose `task.yaml` is hand-written, or whose expected values are pinned to
   one seed, cannot be knobbed self-consistently. Do not knob it; note it (see "Rejected candidates").
5. **Monotone.** Levels start at the default and increase in intended difficulty. `measure` names the
   `--describe` count the knob moves; it must strictly increase along the levels. That is a content check, not a
   difficulty measurement: whether the level is harder for agents is what running it tests.
6. **Never write over the task folder.** `parse_knob_args` refuses a knob without `--out` (or `--describe`).
7. **Acceptance still holds.** The generator's acceptance loop runs on the knobbed draw. Adapt it only in ways that
   are no-ops at the defaults; if a level cannot be accepted, shrink the range.

## Steps

1. Read the generator and `task.yaml`. Pick knobs that are natural for the business: a bigger register, more
   suppliers set up twice, more rate changes in the quarter, a discount moved into a separate agreement.
2. Declare after the imports:
   ```python
   from bizgen.knobs import Knob, KnobSet, add_knob_args, describe_json, output_dirs, parse_knob_args, record
   KNOBS = KnobSet(
       Knob("scale", "scale", default=1, levels=(1, 2, 4, 8), changes="...", measure="rows"),
       Knob("trap_count.dup_vendor_record", "trap-count", default=1, levels=(1, 2, 3, 4), changes="...",
            measure="trap_instances.dup_vendor_record"),
   )
   ```
3. `build(seed, knobs=KNOBS.defaults())`; read values with `knobs["scale"]` or `knobs.trap_count("x")`.
4. `counts(d, knobs)` returns the `--describe` dict; it must contain every declared `measure`.
5. `emit(seed, naive_dir, knobs=KNOBS.defaults(), out=None)`:
   `here, (ws, ref, sol) = output_dirs(HERE, out, task_dirs)` and `write_task_yaml(here, record(spec, id, seed, knobs))`.
6. `__main__`: `add_knob_args(ap, KNOBS)` after the existing arguments (after `add_trap_args` if the generator has
   trap switches; `--out` is then shared); `knobs = parse_knob_args(a, KNOBS)`; the acceptance loop calls
   `build(seed * 1000 + attempt, knobs)`; `--describe` prints `describe_json(...)` and exits before `emit`.
7. Accept:
   ```bash
   BENCH_GEN_PYTHON=~/.venvs/bb-nolxml/bin/python ~/.venvs/bb-nolxml/bin/python bench/check_retrofit.py <task> --runs 3 --skip-validate
   BENCH_GEN_PYTHON=~/.venvs/bb-nolxml/bin/python ~/.venvs/bb-nolxml/bin/python bench/validate_knobs.py <task> --seeds default,1
   ```

## What validate_knobs.py checks

For every declared level of every knob, and every knob at its top level together, per seed:

* the reference solution passes the recomputed checks and the untouched workspace fails them;
* the workspace differs from the default setting (a dead knob is reported);
* the same flags twice give byte-identical folders;
* `task.yaml` records `variant.knobs` exactly;
* the declared `measure` strictly increases from the previous level;
* with no knob flag the generator reproduces the published folder byte for byte, and the published folder is
  unchanged after the run.

If the generator has `--naive`, the naive solution for each setting is graded too, and the checks it fails are
listed (informational). Without LibreOffice, a reference failure is `UNVERIFIED-XLSX (env)` only when every failed
check is a workbook check that the published reference also fails here.

## Knobs vs trap switches

| | trap switch | knob |
|---|---|---|
| direction | removes a pitfall (easier) | adds volume, rules, noise, instances (harder) |
| answer | must not move | expected to move; recomputed |
| task.yaml | `variant.traps_off` | `variant.knobs` |
| renew.py prior | Normal(0.5, 1.0) logit per trap off, subtracted | HalfNormal mean 0.5 logit per level, added |
| validator | `validate_traps.py` | `validate_knobs.py` |

A generator can have both; `--out` is shared, and `record` merges both into one `variant` record.

## Rejected candidates

Saturated tasks that cannot take knobs without first rewriting how their `task.yaml` is made:

* `payments-match`, `payments-match-v2`: `task.yaml` is hand-written; the generator keeps the partial invoice at
  INV-2026-0417 in every draw so the pinned `must_match_keys` stay valid.
* `quote-comparison`: `task.yaml` expected values are pinned to seed 0 (the generator says so).
* `customer-dedupe`: `task.yaml` is hand-written and patched on one line; the row counts in its structure are fixed.
* `budget-vs-actual` and other workbook-graded tasks: fine to knob, but they cannot be verified without LibreOffice
  (their published reference fails workbook checks here), so they were not in the pilot.

## Findings from the pilot

* **commission-clawbacks (HEAD bug, published seed unaffected).** `add_refunds` drops refunds dated after
  31 August. When the planted ">120 days" refund (`outside_window`) lands after that date, it is dropped, and
  `emit` then fails looking up its refund ID for the trap sentence and `must_match_keys`. The published draw keeps
  it, so the published task is correct, but other seeds can crash. The knobbed path rejects any draw that lost a
  planted refund (a no-op at the defaults, so the default output is unchanged); the default path is left as it was
  and is reported here rather than fixed, since fixing it changes which draw some seeds accept.
* **"Workspace fails" is weak evidence for these tasks.** Every untouched workspace fails because the deliverable
  file is missing. The naive solutions (`--naive`, where a generator has one) fail 1 to 5 checks at every level;
  that count does not grow with the knob, so it is not a difficulty signal either. Difficulty at a knob level is
  only measured by running agents on it.
* **credit-notes-apply cross_doc=1 keeps the answer.** Moving the discounts into a second document changes where
  the agent must look, not the result; the validator reports it as alive (workspace moved) with the answer
  unchanged, which is intended.
