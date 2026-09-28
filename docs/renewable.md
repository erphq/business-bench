# Renewable benchmark: re-hardening saturated tasks and sealing new variants

A task that every system passes every time tells a buyer nothing. The ledger in `results/latest/attempts.jsonl`
(187 desk tasks, 3 repetitions each for two systems) has 116 such tasks. Because every desk task comes from a
generator, the bench can do two things a fixed benchmark cannot:

* **Re-harden.** Move a saturated task to a setting that is predicted to be harder, register that forecast,
  run it, and publish the result, misses included.
* **Seal.** Draw new variants of a task that are predicted to be as hard as the published one but have different
  numbers, and keep them private. A later campaign runs on those variants, so a system cannot have seen the
  answers.

`bench/renew.py` does both. It is offline, opt-in tooling. The runner, the grader and the published task files
are not changed, and nothing here runs during an evaluation.

## Workflow

```bash
# 1. Which tasks are saturated, and how can each one be renewed?
python bench/renew.py saturation [--near-max-fails 1] [--json sat.json]

# 2. Enumerate the settings of one task and predict how hard each one is
python bench/renew.py search --task project-margin --root /data/renew/pm \
    --seeds default,1,2,3,4 --design single [--knob NAME=V1,V2]

# 3. Seal new variants at matched difficulty (secret seeds unless --seeds is given)
python bench/renew.py seal --task project-margin --task address-standardize --root /data/sealed/2026-10 --n 3

# 4. Register the forecast before any run (envelope.py's registry, unchanged)
python bench/envelope.py register /data/sealed/2026-10/predictions/project-margin.json --registry <committed path>

# 5. Run the variants like ordinary tasks, then score the registered forecast
python bench/run.py --tasks-root /data/sealed/2026-10 --tasks all --harness proto-deepseek,codex-sol --runs 3 --label sealed-1
python bench/envelope.py score --predictions /data/sealed/2026-10/predictions/project-margin.json \
    --results results/sealed-1 --registry <committed path>

# 6. At release time, prove nothing changed since sealing
python bench/renew.py check --manifest /data/sealed/2026-10/manifest.json
```

Run generation in the Python environment without lxml (`BENCH_GEN_PYTHON=~/.venvs/bb-nolxml/bin/python`, or run
`renew.py` with that interpreter). The published files were generated without lxml. `canonical_reproduces_published`
in each manifest shows whether this environment reproduces them.

## Saturation criterion

Per task, over every attempt in the ledger (all systems, all repetitions):

| class | rule | count in the published ledger |
|---|---|---|
| saturated | every attempt passed: no required check failed in any attempt | 116 |
| near-saturated | not saturated, and at most `--near-max-fails` attempts failed (default 1, i.e. 5 of 6 passed) | 29 |
| informative | some attempts passed, more than `--near-max-fails` failed | 41 |
| never passed | no attempt passed | 1 |

An attempt counts as failed if it did not pass or any required check failed. The ledger has no optional checks,
so the two agree. The saturated count matches the 116 in CONTEXT §4. The numbers use the published (revised)
verdicts. Under the raw verdicts before the scorer revision, 101 tasks would be saturated.

`saturation` also reports the **route** by which each task can be renewed:

| route | meaning | saturated | near-saturated |
|---|---|---|---|
| switches+seed | retrofitted generator: `--out`, `--seed`, `--traps-off` | 1 (project-margin) | 29 |
| knobs+seed | difficulty knobs: `--out`, `--seed`, knob flags, `--describe` | 10 | 0 |
| seed (shadow copy) | not retrofitted: only `--seed`, and it writes into its own folder | 105 | 0 |

The retrofit targets were chosen for signal, so they are almost all tasks that already discriminate. Of the 116
saturated tasks, only project-margin has trap switches and ten have difficulty knobs. For the other 105, the seed is the only lever. A generator
without `--out` is run from a **shadow copy**: the task folder is copied to scratch space, `tasks/lib` is linked
beside it, and `gen.py --seed N` is run there. The results are copied to the output folder without `gen.py`.
The published folder is never written. The unit tests hash it before and after to check this. `--help` is also
only ever run in the shadow copy for these generators.

## Settings and how they are searched

A setting is (seed, set of switchable traps turned off, values of any other generator flag). `search`
enumerates the product of:

* **Seeds**: `--seeds default,1,2,...`, where `default` is the generator's own seed (the published draw).
* **Trap off-sets**: from `gen.py --list-traps`, closed under `requires`, chosen with `envelope.py`'s designs
  (`single`, `pairs`, `full`, `random:N`). These are available only on retrofitted generators.
* **Knobs**: `--knob NAME=V1,V2` for any flag the generator's `--help` lists, other than the reserved ones
  (`seed`, `out`, `traps-off`, `mutant`, `list-traps`, `naive`, `list-knobs`, `describe`). A flag the generator
  does not have is refused; the generator is not edited. Ten saturated generators declare **difficulty knobs**
  (`tasks/lib/bizgen/knobs.py`, `docs/authoring-knobs.md`): size, rules, noise, trap count and cross-document
  rules. For them, with no `--knob`, `search` enumerates the declared levels (`--knob-design`, default
  `single+max`: each knob alone at each level, then every knob at its top level) and records each setting's
  `--describe` content counts in the manifest. Their route is `knobs+seed`: written with `--out`, no shadow copy.

Each setting is generated into `ROOT/<task>__vNN` and hashed. Within one draw, a trap-off setting must leave
`checks` and `reference/` equal to the same seed with every trap on. Otherwise the answer moved, and it is
reported as a problem.

## Predicted difficulty

Difficulty is predicted relative to the **canonical setting** (published seed, every trap on), which is
regenerated in the current environment. It is measured in logits, and positive means harder:

    delta = sum_k w_k * (x_k(setting) - x_k(canonical))  -  sum_{j switched off} e_j  +  sum_m s_m * u_m

* `w_k` are the task-feature weights of the difficulty model (`bench/difficulty.py`, an LLTM fitted on the
  ledger), with task-clustered bootstrap draws. `difficulty.LedgerModel` exposes the same fit that
  `difficulty.py` reports. `x_k` are that model's features, read from the generated task folder: check counts
  by kind, workspace size, file count, formats and category.
* The between-task **trap count** feature is left out. Its fitted weight is -0.12 (interval -0.37 to +0.17): it
  says that tasks with more trap sentences are, if anything, easier. That is a correlation across different
  tasks, not the effect of a pitfall within one task. Turning a trap off instead moves the logit by
  `e_j ~ Normal(0.5, 1.0)`, the prior `envelope.py predict` uses before any variant has been run. Both tools
  therefore forecast trap effects the same way.
* **Knob prior.** `s_m` is how many declared levels knob *m* sits above its default (the published task; linear
  between levels) and `u_m ~ HalfNormal` with mean 0.5 logit: one level is worth about one trap, with the sign
  fixed by the knob's declaration that each level is harder. One draw per knob, scaled by its levels, so levels of
  one knob are assumed to add alike, and knobs are assumed to add to each other. This is a design assumption, like
  the trap prior, until variants at that level have been run; `validate_knobs.py` only checks that the declared
  content count grows. The manifest splits each delta into `model_part` and `knob_prior_part`.
* **Monotonicity by construction.** Removing a pitfall never adds one (authoring rule 6). A setting with any trap
  off, or any knob below its default, is therefore marked `harder_eligible: false` and is never proposed as harder,
  whatever the model says.

Per system *s*, the forecast is anchored on that system's observed attempts on the published task:

    P(pass | s, setting) = sigmoid(logit p_s - delta),   p_s ~ Beta(passes + 0.5, fails + 0.5)

The anchor draws are shared by every setting of a task, so differences between settings come from `delta`
alone. A setting is **credibly harder** when the 5th percentile of `delta` is above 0. The **proposal** is the
credibly harder setting with the largest `delta`. A setting is **matched** when `|delta| <= --tol` (default 0.10
logit, about 1 point of pass rate near p = 0.9).

### Pre-registrable output

Both `search` and `seal` write `predictions/<task>.json` in `envelope.py`'s `envelope-predictions` format. It
carries a content sha256, the manifest sha256, one cell per system × setting (`p_mean`, 20 equal-mass quantile
points, `passk`) and the ledger rates as the "settings do not matter" baseline. It also has an extra
`difficulty` list with `delta` per setting. `envelope.py register` and `envelope.py score` accept it
unchanged; `test_renew` registers and scores one. When scoring sealed variants, do not pass `--manifest` to
`score`. The sealed manifest has no canonical variant, and none is needed.

## Sealed variants

`seal` draws seeds with `secrets` from [10 000, 4 000 000), so that `seed * 1000 + attempt` stays below 2^32 for
generators that seed numpy. For each draw it generates the task under `--root`, which is refused if it is
inside `tasks/`, and warned about if it is inside the repository and not git-ignored. It then applies these
rules in order:

1. **New draw.** The workspace hash differs from the published task and from every earlier variant.
2. **Matched difficulty.** `|delta| <= --tol`.
3. **Verified.** Graded by `bench/grade.py`. The reference solution must pass the variant's own checks, and the
   untouched workspace must fail them. Without LibreOffice, `grade.py` recalculates workbooks with the `formulas`
   engine, which returns `#NAME?` for COUNTIFS, SUMIFS and similar functions. So the published task's own
   reference solution is graded in place first. If a variant's reference fails only workbook (or task-module)
   checks, and the published reference fails those same checks here too, the variant is recorded as
   **`UNVERIFIED-XLSX (env)`**, not as a defect. Every other failure rejects the draw.

Rejected draws are deleted and listed under `rejected` with the reason. The command exits 1 if any task ends
up with fewer variants than `--n`, after `--max-tries` draws per task.

Outputs under `--root`:

* `<task>__rNN/`: runnable task folders (`task.yaml`, `workspace/`, `reference/`, `reference_solution/`, and
  `check.py` where the task has one). Names carry an index, not the seed.
* `manifest.json`: **private**. Per task: generator path and sha256, route, whether the canonical setting
  reproduces the published files, the in-repo canonical grade, the published hashes and the ledger anchor. Per
  variant, as in this real entry from the demo:

  ```json
  {"id": "r00", "dir": "project-margin__r00", "task": "project-margin", "seed": 2299532,
   "traps_off": [], "knobs": {},
   "predicted_delta": {"estimate": -0.0012, "lo90": -0.028, "hi90": 0.0302, "features_changed": ["log_workspace_kb"]},
   "sha256": {"task_yaml": "f80e…", "checks": "da63…", "reference": "8af7…", "reference_solution": "3142…", "workspace": "3284…"},
   "answer_changed": true, "seed_visible_in": [],
   "verification": {"status": "VERIFIED", "reference_failed": [], "workspace_failed": ["…10 checks…"], "grader_errors": []},
   "nonce": "4577…", "commitment": "4daf…"}
  ```

  The manifest also records the git HEAD and dirty flag, the interpreter, the ledger sha256, the tolerance,
  and the rejected draws.
* `commitments.json`: **public**. The manifest sha256, each prediction file's sha256, and per variant
  `sha256({task, seed, traps_off, knobs, content hashes, nonce})`. It contains no seed. Publish it when sealing.
  Publish the manifest when the variants are released, and anyone can check each commitment.
* `predictions/<task>.json`: the forecast, ready to register.

`seed_visible_in` lists text files that contain the seed literally. None did in the demo, but a generator that
writes its seed into `task.yaml` would leak it.

`check --manifest M` re-hashes every variant folder, recomputes each commitment, and compares the manifest
with `commitments.json`. Run it before a sealed campaign and at release.

## Demo (this branch, macOS, no LibreOffice, `bb-nolxml` interpreter)

**search on project-margin** (the one saturated task with switches; ledger 3/3 and 3/3). Seeds default, 1 to 4,
and design `single`, give 30 settings in 3.9 s. The canonical setting has delta 0. Every setting with every trap
on (seeds 1 to 4) has |delta| ≤ 0.003 logit (90% within ±0.07); only the workspace size moved. Single traps off
give delta ≈ -0.50 (90% -2.2 to +1.2), `unbilled` off -0.62 (it also removes a file), and
`format_noise`+`credit_brackets` -1.00. The predicted P(pass) goes from 0.874 to 0.89–0.91. **No credibly
harder setting exists**, so nothing is proposed. contract-renewal-summary (9 settings) and event-attendee-merge
(21 settings) give the same result.

**seal**, n = 3 on eight tasks (24 variants, 7.5 s) and n = 2 on eight more (16 variants, 8.4 s). Every draw was
accepted on the first try. Every |delta| ≤ 0.002, and every variant changed the answer (new `checks` and
`reference/`).

| task | class | route | result |
|---|---|---|---|
| project-margin | saturated | switches | 3 VERIFIED |
| address-standardize, inventory-valuation, menu-cost-sheet, petty-cash-reconcile | saturated | shadow | 3 VERIFIED each |
| budget-vs-actual | saturated | shadow | 3 UNVERIFIED-XLSX (env): the published reference fails 6 workbook checks here |
| tip-pooling, contract-renewal-summary | near-saturated | switches | 3 VERIFIED each |
| menu-item-performance, event-attendee-merge, shopify-product-import | near-saturated | switches | 2 VERIFIED each |
| incident-summary, monthly-report, quarterly-sales-report, regional-sales-monthly, commission-calculation | near-saturated | switches | 2 UNVERIFIED-XLSX (env) each |

In every case the untouched workspace failed. `check` confirmed all 24 hashes and commitments of the first
batch. The canonical workspaces of petty-cash-reconcile, contract-renewal-summary and commission-calculation do
not regenerate byte-identically in this environment (for contract-renewal-summary, the PDFs differ). Their checks
and references do. Hashes are therefore environment-specific: seal and check in the same environment.

## Limits: read before quoting a number

* **The difficulty model is weak.** It is fitted on two systems. Its leave-task-out log loss is 0.3733 against a
  base rate of 0.3782, and every feature weight's 90% interval crosses zero (`bench/difficulty.py`). `delta` is
  close to a prior guess. "Matched difficulty" means matched *on the features the model sees*, and for a new
  seed those barely move (mostly workspace size). Seed-to-seed variation in true difficulty is not in the
  intervals. The first scored forecast on sealed variants measures it; `envelope.py score` reports the misses.
* **Trap effects are a prior**, Normal(0.5, 1.0) per trap, until variants have been run (`envelope.py fit`).
* **The ledger anchor is 3 repetitions per system.** A saturated task's anchor is Beta(3.5, 0.5), mean 0.875.
  So a forecast for a saturated task says "about 0.87, wide", not "certainly passes".
* **"Credibly harder" is almost entirely the knob prior.** On the ten knobbed tasks the model part of every delta
  is between 0.00 and +0.26 logit; the rest is the stated prior. The task-feature model sees a knob only through
  workspace size and file count, whose weights cross zero, so it can *widen* the interval (four `scale` settings
  are not credibly harder for that reason) but never supply evidence that a level is harder. A proposal is a
  pre-registrable hypothesis, not a measurement: register it, run it, and publish the score (`envelope.py score`).
  After a first run, the per-level effect should be fitted per knob kind (as `envelope.py fit` does for traps).
* **Stacking is additive by assumption.** The all-knobs-at-max setting is always the proposal (delta 3 to 4 logit,
  predicted P(pass) about 0.37 to 0.48 from 0.87). That is the most extreme setting searched, not the most useful
  one: for re-hardening, pick the setting whose forecast is nearest the target pass rate (for example the single
  knob levels at delta 1.0 to 1.5, P about 0.69 to 0.76), and seed several levels so the dose-response is measured.
* **Only ten saturated generators have knobs.** The other 106 saturated tasks can still only be re-rolled by seed,
  and for them `search` still proposes nothing.
* **Seal matches the canonical setting.** `seal --knob` generates at a knob setting, but "matched difficulty" is
  measured against the published setting, so a knobbed draw is rejected by `--tol`. Sealing at a harder setting needs
  the knobbed setting as the anchor; not built.
* **Environment.** Without LibreOffice, workbook tasks cannot be fully verified here. `UNVERIFIED-XLSX (env)`
  variants must be re-verified where LibreOffice is available (`BENCH_RECALC_DOCKER_IMAGE`, or `soffice` on
  PATH) before release.
* **Sealing is only as strong as the private manifest.** Anyone with the manifest, or the seeds, can regenerate
  the variants from the public generators. Keep `--root` outside the repository, or git-ignored.
* Hand-written `task.yaml` files with expected values pinned to one seed do not follow a new seed. For those, the
  reference fails its checks and the draw is rejected. It is never accepted silently.

## Knobs (pilot on ten saturated tasks)

The flags this section asked for now exist on ten saturated generators (`docs/authoring-knobs.md` has the pattern;
`bench/validate_knobs.py` checks every level: reference passes, untouched workspace fails, workspace moves, same
flags give the same bytes, the declared content count grows, the default reproduces the published folder):

| task | knobs (levels; first is the published task) |
|---|---|
| duplicate-payments | scale 1,2,4,8; trap_count.dup_vendor_record 1-4; trap_count.dup_leading_zero 1-3 |
| mileage-reimbursement | scale 1-4 (clinicians); trap_count.odometer 1-3 (paper odometer workbooks); trap_count.personal 1-3 |
| tenant-ledger-balances | scale 1-3 (lots); trap_count.moveout 2-5; trap_count.mailed 1-4 |
| shift-coverage-gaps | rules 5-8; trap_count.split 2-4; trap_count.cancelled 1-3 |
| phones-to-e164 | scale 1-4; noise 0.5,0.7,0.9 (blank Country column rate); trap_count.invalid_number 7,10,14 |
| gift-card-liability | scale 1-4; trap_count.reload 3,5,7; trap_count.promo_card 5,8,12 |
| plan-change-proration | scale 1-4; rules 1-3 (discount classes); cross_doc 0,1 (nonprofit status in a second document) |
| sales-tax-liability | scale 1,2,4; rules 1-3; trap_count.expired_cert 1-3 |
| commission-clawbacks | scale 1-3; rules 5-7 (recall and small-clawback clauses); trap_count.two_partials 1-3 |
| credit-notes-apply | scale 1,2,4; cross_doc 0-2 (discounts in customer price agreements); trap_count.spill_over 1-3 |

Search on the published seed, `--knob-design single+max` (this branch, macOS, `bb-nolxml`): 78 knob settings, 74
credibly harder (90% lower bound of delta above 0). The four that are not are `scale` settings (duplicate-payments
8, mileage-reimbursement 2, sales-tax-liability 2 and 4) whose workspace-size term widens the interval below zero.
Single-knob top levels give delta +1.0 to +1.5 logit (predicted P(pass) 0.68 to 0.76 for both systems, from 0.87);
all knobs at max give +3.0 to +4.0 (P 0.37 to 0.48). See "Limits" before quoting either.

Still wanted:

* `--rows N` / `--scale F`: volume (invoices, ledger lines, attendees) per task.
* `--rules N`: number of business rules in play (commission bands, rate tiers, policy clauses).
* `--noise F`: rate of formatting noise and malformed records, beyond the single planted instance.
* `--trap-count name=N`: **trap intensity**, i.e. how many instances of a switchable trap are planted (three
  draft invoices instead of one). This is the most direct "harder" lever and fits the existing TrapSet design.
* `--cross-doc`: a rule that needs a second document (the "<70% once a rule needs a second document" line of the
  delegation-envelope pitch).
* `--describe`: print per-draw counts (rows, trap instances) as JSON, so seeds can be matched on content rather
  than on file sizes.
* Knobs, `--describe` and `--out` on the remaining generators (the pattern is in `docs/authoring-knobs.md`).
* A fitted per-level effect per knob kind, once knobbed variants have been run, to replace the prior.
