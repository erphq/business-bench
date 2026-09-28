# Delegation envelopes: forecast, then measure, which pitfalls a system handles

A business that hands a recurring job to an agent system wants to know more than one pass rate. It wants
to know which kinds of mess the system copes with every time, and which single kind of mess breaks it.
For example: "passes all 5 repetitions at least 95% of the time with draft invoices on the revenue sheet
and costs in a separate file; below 70% once format noise is added." That statement is a **delegation
envelope**.

Desk generators with trap switches (see [authoring-traps.md](authoring-traps.md)) make this measurable.
`gen.py --traps-off a,b --out DIR` writes the same task from the same random draw with those pitfalls
removed and the same correct answer. Because the answer stays the same, a change in pass rate can only
come from the pitfalls. `bench/envelope.py` turns this into a workflow. The forecast is committed before
any run and scored in public afterwards, misses included, because that is what makes the envelope
believable.

## Workflow

```bash
# 1. Plan: choose variants and write them as runnable task folders plus a manifest
python bench/envelope.py plan --task project-margin --design single --root /data/env/pm
#    designs: single (canonical + each trap off alone), pairs, full (factorial), random:N

# 2. Predict: per system x variant, P(pass) and pass^k, before anything is run
python bench/envelope.py predict --manifest /data/env/pm/manifest.json \
    --systems proto-deepseek,codex-sol --from-ledger results/latest/attempts.jsonl \
    --k 5 --out forecasts/pm-2026-10.json

# 3. Register: append the predictions hash, manifest hash, time and git HEAD to the registry
python bench/envelope.py register forecasts/pm-2026-10.json --registry <committed path>/registry.jsonl
#    then commit and push (or otherwise publish) the registry line BEFORE step 4

# 4. Run the variants like ordinary tasks (the variant folder is a tasks root)
python bench/run.py --tasks-root /data/env/pm --tasks all --harness proto-deepseek,codex-sol \
    --runs 5 --label pm-env-1

# 5. Fit per-trap effects and system abilities from the runs
python bench/envelope.py fit --manifest /data/env/pm/manifest.json --results results/pm-env-1 --out fit.json

# 6. Score the registered forecast against the runs (refuses if not pre-registered)
python bench/envelope.py score --predictions forecasts/pm-2026-10.json --results results/pm-env-1 \
    --registry <committed path>/registry.jsonl --manifest /data/env/pm/manifest.json --out score.json

# 7. State the envelope in business terms
python bench/envelope.py envelope --fit fit.json --system codex-sol --k 5 --threshold 0.95 --floor 0.70
```

`simulate --manifest M --effects JSON --systems a,b --reps K --out DIR` writes result records drawn from
per-trap effects you choose. It exists so that steps 5 to 7 can be shown and tested without calling a
model. Every simulated record carries `"synthetic": true` and a note, the folder contains `SYNTHETIC.txt`,
and `fit`, `score` and `envelope` print a SYNTHETIC banner whenever any input record is synthetic.

## What each step writes and checks

**plan** reads `gen.py --list-traps`, picks the requested off-sets, and closes each one under `requires`
(turning `format_noise` off also turns `credit_brackets` off). Off-sets that come out the same after
closure are the same task, so only one is kept and the rest go under `duplicates_dropped`. Each variant
is written to `ROOT/<task>__vNN` (`v00` is the canonical task with every trap on, regenerated with
`--out`). `manifest.json` records, per variant, the requested and effective `traps_off`, which traps
remain on, and sha256 hashes of `task.yaml`, the `checks`, `reference/`, `reference_solution/` and
`workspace/`. Plan fails if any variant's checks or reference differ from the canonical ones, because
that means the answer moved (authoring rule 4). It warns if a variant's workspace is identical to the
canonical one, because then the switch did nothing. It also records whether the regenerated canonical
matches the published task. Workspaces often differ at the byte level only because of the library
environment (lxml). `--dry-run` writes the manifest without generating anything, which is useful for
counting runs before paying for them. Variant ids are short (`vNN`) on purpose, so that
`run.py`'s container names are not truncated into collisions.

**predict** has two methods, and the file says which one it used:

* *canonical-rate + prior*: used when no variant has been run yet. Each system's canonical pass rate
  comes from its observed attempts on the published task, with a Jeffreys Beta(passes + 0.5, fails + 0.5)
  posterior. Removing trap *j* adds *w_j* to the logit, with *w_j* ~ Normal(0.5, 1.0) independently for
  each trap: the prior guess is that a trap costs about half a logit and could plausibly be anywhere from
  mildly helpful to strong (`--effect-prior mean,sd`). A system with no attempts gets a uniform guess and
  a note saying so.
* *laplace*: used when variant attempts exist (`--from-results`). It fits the model below with the same
  effect prior and averages over a Gaussian approximation to the posterior.

Each cell stores `p_mean`, 20 equal-mass points of the predictive distribution of *p* (used by `score`
to decide what counts as a miss), and `passk` = E[*p*^k]. The file also stores each system's canonical
rate as the "traps do not matter" baseline. It carries a content sha256, and any edit breaks the hash.

**register** appends `{predictions_sha256, manifest_sha256, task, systems, k, created_utc, git_head,
git_dirty}` to a JSONL registry. The default path, `results/forecasts/registry.jsonl`, is git-ignored,
like everything under `results/` except `results/latest`. A local file proves nothing to anyone else.
For a public forecast, point `--registry` at a tracked path and commit and push it, or publish the line
somewhere timestamped, before the runs start.

**fit** reads run.py result records: `results/<label>/<run_id>/result.json`, with fields `task`,
`harness`, `run` and `passed`. Attempts on the published task (for example from a ledger) count as the
canonical variant. The model:

    logit P(pass | system s, variant v) = alpha_s - sum_j w_j * [trap j on in v]

Here *alpha_s* is the system's logit pass rate with every switchable trap removed. It is reported as a
task baseline *b* = mean(*alpha*) plus abilities *theta_s* = *alpha_s* - *b*, so with a single task an
ability is only relative to the other systems in the fit. Fixed traps are always present and are part of
*b*. The fit is MAP logistic regression with weak priors: intercept N(0, 3), effect N(0, 2.5), and
optional per-system trap deviations N(0, 0.5) with `--interactions`. The 90% intervals come from a
bootstrap that resamples repetitions within each system × variant cell (the default), or whole variants
with `--cluster variant`. The latter is wider and honest about the fact that each effect in a `single`
design rests on one variant.

**score** refuses, with exit code 2, when:

* the predictions no longer match their hash;
* the hash is not in the registry;
* the registry entry names a different manifest;
* any matched attempt has no start time;
* the earliest registration is not strictly earlier than the first attempt's start.

Start times come from a record's `started_utc` when it has one. Otherwise they come from file times in
the run folder: `prompt.txt` is written just before the agent starts, and `result.json`'s mtime minus
`wall_s` is a later bound. The report states which kind of evidence was used. When scoring goes ahead,
it reports:

* attempt-level Brier score and log loss;
* the Brier score of the "traps do not matter" baseline, and the skill against it;
* Brier score for pass^k on cells with k repetitions;
* a reliability table;
* every cell, with misses marked. A miss is an observed pass count outside the central 90% of the
  predictive distribution, so about 10% of cells should be misses if the forecast is calibrated.

**envelope** goes through every feasible combination of switchable traps and computes pass^k for the
chosen system, with a 90% interval from the bootstrap draws. It lists the largest combinations that are
still at or above the threshold (with `--conservative`, judged by the interval's lower end), in the trap
descriptions from `--list-traps`. It lists the single traps whose addition takes the system out of the
envelope, and marks with `--floor` those that drop below a second level. It marks as `[extrapolated]` any
combination that was not itself run. `--all` prints the whole table.

## What is and is not established

Established by the tooling alone, for one task and one draw:

* Variants are the same task with the same answer (hash-checked in the manifest). A difference in pass
  rate between variants is therefore caused by the pitfalls, not by a different problem.
* A forecast was fixed before the runs (hash plus registry time, and only as strong as the registry is
  public) and was scored in full, misses included.
* For the systems that were run: which traps cost them how much on this task, with sampling intervals.

Not established without a panel of systems and more tasks:

* **Abilities are relative.** With one task, a system's ability is only defined against the other
  systems in the same fit. Two systems give one contrast. Claims such as "this system handles format
  noise in general" need the same traps measured across several tasks (several generators retrofitted
  with the same trap kinds) and a panel of 8 to 12 configurations, as `bench/difficulty.py` also warns.
* **One draw.** A manifest is one seed. The variation from one draw to the next is not in the intervals.
  To include it, plan several seeds (`--seed`) and fit them together.
* **Additive effects.** The model assumes trap costs add up on the logit scale and do not interact.
  Combinations that were not run are extrapolations and are marked as such. A `full` or `pairs` design
  can test the assumption, and cells that the model fits poorly show up in the fit table and as score
  misses. `--interactions` allows per-system deviations, but not trap-by-trap interactions.
* **Independent repetitions.** pass^k = E[*p*^k] treats repetitions as independent given *p*. If
  failures are correlated within a system (the same mistake every time), pass^k from the model is
  optimistic for low *p* and pessimistic for high *p*. Observed all-k outcomes are scored separately so
  that this shows up.
* **Prior forecasts are guesses.** Before any variant has been run, the per-trap effects come from a
  stated prior. The first scored forecast mainly tests that prior. The Brier skill against the "traps do
  not matter" baseline is the number to watch.
* **Pre-registration strength.** `run.py` does not record a start time, so a normal run is timed from
  file mtimes. Copying or archiving can reset those. Having `run.py` write `started_utc` into
  `result.json` would make the check robust. That is a proposed change, not yet made.
* **Synthetic output is not evidence.** Anything produced by `simulate` shows only that the pipeline
  works.

## Cost of a design

With T switchable traps, k repetitions and S systems, a design needs (number of variants) × k × S runs:

| design | variants | runs for project-margin (5 traps, 1 requires), k=5, S=2 |
|---|---|---|
| single | 1 + T | 6 variants → 60 runs |
| pairs | 1 + T + T(T-1)/2, minus duplicates | 15 variants → 150 runs |
| full | distinct closed subsets | 24 variants → 240 runs |
| random:N | 1 + N | chosen to fit a budget |

`single` identifies every effect under the additive model at the lowest cost. Use `pairs` or `full`
when the question is whether traps compound.
