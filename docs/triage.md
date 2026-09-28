# Failure triage: which failures to audit first

The plan calls for a 50-task human audit of failed attempts. Some failures are the grader's fault, not the
agent's. `bench/triage.py` ranks failed attempts, and the failed checks inside them, by how likely each failure
is a grader error. The audit can then start with the most suspicious ones. The tool is offline and opt-in.
Nothing in the runner or the graders imports it. It makes no network or LLM calls. It never writes to a run
directory.

```
python bench/triage.py metamorphic --view snapshot:87f624e --out docs/triage/metamorphic-snapshot.json   # ~20 s
python bench/triage.py metamorphic --view frozen           --out docs/triage/metamorphic-frozen.json     # ~20 s
python bench/triage.py fit                                   # cross-validates, writes docs/triage/{model,evaluation}.json
python bench/triage.py rank --ledger results/latest/attempts.jsonl --out docs/triage   # the published queue
python bench/triage.py rank --run results/<label>            # a local run: adds the artifact layer
```

## Labels, and why raw per-check verdicts were recoverable

The published ledger (`results/latest/attempts.jsonl`) holds two verdicts for each attempt:

- `raw_passed`: from the scorer at run time;
- `passed`: from the frozen-v7 scorer.

The ledger records per-check results only for the frozen scorer. The scorer revision moved 104 verdicts.
103 went from fail to pass, so they are known grader errors. The one pass-to-fail case is a codex-sol attempt
of `tuition-collections`.

Per-check raw verdicts are not in the published ledger. They are, however, in git: the superseded four-arm
release at `87f624e` (2026-09-17). Its 561 codex-sol attempts have the same `source_sha256` as the 561 published
codex-sol attempts, and its verdicts equal their `raw_passed` in 561 of 561 cases. The published proto-deepseek
arm is a different cohort, and none of its sources match. So check-level labels exist for codex-sol only:

- **Unit:** one failed required check under the raw scorer.
- **Label = 1:** the frozen scorer passes that check.
- **Redesigned checks:** three tasks (delivery-performance, energy-usage-sites, occupancy-report) and one check
  of retention-cohorts were renamed at the freeze. A raw failure whose check the frozen task no longer has is
  labelled 1 when the frozen attempt passes (every raw failure was then an error). Otherwise it is dropped.
- **Result:** 324 rows, 88 positives, 61 tasks. The positives are concentrated in 21 tasks. The effective
  sample size is closer to 21 clusters than to 324 rows.

## Two views: features never come from the scorer that supplies the label

Every feature is computed from what the scorer that *produced* the failure could see:

| | training (raw view) | ranking the published ledger (frozen view) | ranking a local run |
|---|---|---|---|
| per-check verdicts | `87f624e` ledger (4 arms × 3 reps) | published frozen verdicts (2 arms × 3 reps) | `result.json` files |
| task specs | `87f624e` `tasks/desk` | `scoring/frozen-v7/tasks` | `tasks/desk` |
| grader for metamorphic probes | `87f624e` `bench/grade.py` | `scoring/frozen-v7/scorer.py` | `bench/grade.py` |

Leakage the design avoids:

- **Frozen specs and equivalence modules are never features.** Examples are `column_match`, `ref_alternatives`,
  `equals_any` and the 7 equivalence checkers. Several of these *are* the revision, so "has `column_match`"
  would predict the label almost perfectly.
- **Other attempts' frozen verdicts are never used in training.** If the revision fixed a check, every
  attempt's frozen verdict on it passes. The raw verdicts of the other attempts are used instead.
- **Check-type rates are never global target encodings.** The check-type prior is learned inside each training
  fold only.
- **Cross-validation holds out whole tasks.** Repetitions and both systems share a task's checks, so a
  row-level split would leak each check's fate.
- **`raw_grader_error_count` is excluded.** It is 0 for every frozen verdict, so a weight learned on it could
  not transfer to the ranking view.
- **Residual risk:** the metamorphic transforms were written after the revision's problems were known. The
  feature turned out not to predict (see below), so the risk is moot here, but it is named.

## Features (one row per failed required check)

| feature | meaning |
|---|---|
| `fam_*` (9) | check family: sentence, text, numbers, custom, xlsx value, xlsx structure, csv values, csv shape, file |
| `near_miss`, `log_n_failed` | the attempt failed exactly one required check; how many it failed |
| `panel_pass_other` | share of the task's other attempts that pass this check |
| `same_system_pass`, `other_system_pass` | this system's other repetitions pass it (share); any attempt by another system passes it |
| `metamorphic_fn` | this check fails the task's own reference solution under an invariant text transform (per-check re-run of `bench/metamorphic.py` transforms, in the view's grader) |
| `abnormal_exit` | timeout or non-zero exit |
| `log_terms`, `near_text`, `exact_columns` | spec strictness: literal terms demanded, a label-anchored workbook value, an exact template |

The metamorphic scan re-runs each check alone, so a workbook check never blocks a text check. It uses only
csv, md, html and ics transforms. Without LibreOffice, the Python `formulas` engine reads COUNTIFS/SUMIFS and
similar as `#NAME?`. About 175 workbook checks therefore fail their own reference locally. They get
`metamorphic_fn = 0`, which means "not tested", not "robust".

- **Snapshot grader:** 24 (task, check) pairs fail a reformatted reference.
- **Frozen scorer:** 13 pairs fail. Its line-unwrap removed most of them, but 40-column wraps still break
  `minutes-from-transcript`, `policy-update-memo` and 9 others.

## Model and evaluation

- **Model:** L2-regularised logistic regression by Newton's method, in numpy, with no other dependency.
- **Candidates:** full features at λ = 1 and λ = 10; a compact set (panel, same-system, other-system,
  near-miss, failure count, metamorphic, exit) at λ = 1 and λ = 10; and the panel feature alone.
- **Selection is nested.** Each outer fold picks its configuration by an inner grouped CV on its own training
  tasks only.
- **Cross-validation:** grouped 5-fold by task, repeated. Leave-one-task-out was tried first and dropped. With
  sparse binary features it produces a large held-out-task intercept artefact: a one-feature model scored AUC
  0.009.
- **Intervals:** 95% intervals come from a task-cluster bootstrap with 2,000 resamples.
- **Attempt score:** the product of the attempt's check probabilities, i.e. the chance that *every* failure is
  a grader error, so that the verdict itself is wrong. This was declared before evaluation.
- **Heuristic baselines** are unfitted, with the direction stated beforehand.

**Check level** (codex-sol, n = 324, 88 positives):

| scorer | AUC [95% CI] | P@10 | P@50 |
|---|---|---|---|
| **model, nested selection** | **0.843 [0.72, 0.94]** | **1.00 [0.70, 1.00]** | **0.84 [0.40, 1.00]** |
| check type only (fitted in-fold) | 0.613 [0.40, 0.82] | 0.00 | 0.46 |
| near-miss (a priori) | 0.551 [0.47, 0.67] | 0.39 | 0.39 |
| fewest failed checks (a priori) | 0.725 [0.58, 0.85] | 0.39 | 0.39 |
| metamorphic FN (a priori) | 0.504 [0.47, 0.56] | 0.31 | 0.28 |
| other attempts pass it (a priori) | 0.137 [0.06, 0.24] | 0.03 | 0.04 |
| everyone else fails it (**post hoc**: reverse of the row above) | 0.863 [0.76, 0.94] | 0.94 | 0.82 |
| base rate | 0.500 | 0.27 | 0.27 |

**Attempt level** (codex-sol raw-failed attempts, n = 130, 43 positives):

| scorer | AUC [95% CI] | P@10 [CI] | P@50 [CI] |
|---|---|---|---|
| **model, product** (declared) | **0.783 [0.65, 0.90]** | **0.80 [0.40, 1.00]** | **0.56 [0.34, 0.80]** |
| model, max (sensitivity) | 0.832 [0.71, 0.94] | 0.95 [0.65, 1.00] | 0.62 [0.36, 0.84] |
| near-miss only | 0.555 [0.42, 0.69] | 0.39 [0.21, 0.56] | 0.39 [0.21, 0.56] |
| everyone else fails (post hoc) | 0.863 [0.75, 0.95] | 0.90 [0.67, 1.00] | 0.63 [0.40, 0.85] |
| base rate | 0.500 | 0.33 | 0.33 |

**Ledger-only attempt model, both arms** (no per-check raw verdicts needed; n = 244, 103 positives):

- **Features:** the task's other attempts' `raw_passed`, split by same and other system; exit status; the
  task's check-type mix; whether the task has a metamorphic false negative.
- **Result:** AUC 0.757 [0.66, 0.85], P@10 0.63, P@50 0.64. The base rate is 0.42.
- **Per arm:** codex-sol 0.815 and proto-deepseek 0.734. The Proto arm has no check-level labels, so it is
  evaluated here only.

The inner loop picked the compact model (λ = 10) or the panel-only model in 24 of 25 outer folds. The final fit
is compact at λ = 10. All of its weights are negative except near-miss, which is about 0:

| feature | weight (standardised) |
|---|---|
| `panel_pass_other` | −0.83 |
| `same_system_pass` | −0.70 |
| `other_system_pass` | −0.46 |
| `log_n_failed` | −0.34 |
| `metamorphic_fn` | −0.09 |

### What the data says

1. **Grader errors are systematic.** The strongest single signal is that the other attempts, across systems
   and repetitions, fail the same check. The "other system passed it, so the agent erred" intuition runs the
   wrong way: its AUC is 0.14, below chance. The model's lift over its best single feature is nil. Its value
   is that it was chosen without peeking. "Everyone else fails it" alone scores 0.86, but its direction was
   found on this data.
2. **Near-miss is not a grader-error signal** (AUC 0.55). Proto's high near-miss share (63%) says nothing about
   grader error by itself.
3. **The check family matters weakly across tasks** (0.61). The per-check metamorphic flag, as scanned here,
   does not predict which *agent* failures were errors (0.50). Metamorphic false negatives are about how the
   reference is formatted. The agents' outputs failed for other reasons, such as headers, row sets,
   alternative answers and custom logic.
4. **The panel size matters.** Ranking uses six attempts per task, where training used twelve. Refitting with
   the training panel restricted to the two published systems gives:
   - check AUC 0.800 (was 0.843);
   - attempt AUC 0.736 (was 0.783);
   - P@10 0.40 (was 0.80).

   The published queue should be read with that lower figure in mind.

## The published queue

The full outputs are in `docs/triage/`:

- `queue.md`: attempts, with the most suspicious failed check and a one-line reason;
- `queue.csv`: every failed check of every failed attempt;
- `tasks.csv`: tasks as audit units.

The queue covers all 142 frozen-failed attempts (88 codex-sol, 54 proto-deepseek) and 346 failed checks.

**Top 10 tasks** (as audit units; an attempt-level top 10 is in `queue.md`):

| # | task | score | failed attempts | the check to look at first | why |
|---|---|---|---|---|---|
| 1 | tenant-statements | 0.824 | 6 (both systems, all reps) | one row per entry (`csv_set_equal`) | 0/5 other attempts pass it; already flagged for audit in the planning notes (both systems fail the same two checks every time) |
| 2 | staff-utilization | 0.513 | 4 | utilization per person (`custom`) | Proto fails only this check on all 3 reps; 2/3 Codex pass. Its `check.py` path-lookup fallback is a pending decision |
| 3 | clinic-visits-summary | 0.379 | 3 (codex) | clinic total visits (`xlsx_value_present`) | only failed check; all 3 Codex reps fail it, Proto 3/3 pass |
| 4 | investor-update | 0.379 | 3 (codex) | quarter revenue figures (`text_numbers_present`) | only failed check on all 3 Codex reps; Proto 3/3 pass |
| 5 | minutes-from-transcript | 0.379 | 3 (codex) | minutes facts (`custom`) | only failed check on all 3 Codex reps; another check of this task fails a 40-column-wrapped reference under frozen |
| 6 | overdue-reminders | 0.379 | 3 (codex) | per-customer reminder facts (`custom`) | only failed check on every Codex rep |
| 7 | price-increase-notice | 0.379 | 4 | lobby arrangement: new price and rounded percent (`text_sentence_matches`) | only failed check on 2 Codex reps; another check of this task fails a wrapped reference under frozen |
| 8 | supplier-dispute-letter | 0.379 | 3 (codex) | price clause cited (`text_sentence_matches`) | only failed check on all Codex reps |
| 9 | vendor-1099-totals | 0.379 | 3 (proto) | which vendors (`custom`) | only failed check on all Proto reps; Codex 3/3 pass |
| 10 | weekly-kpi-dashboard | 0.379 | 3 (codex) | total sales, six weeks (`xlsx_value_present`) | only failed check; Proto 3/3 pass |

**How to read the scores:**

- **They are calibrated to the training panel, not to this one.** A 0.38 means "ranked high", not "38%
  likely".
- **Ties are real.** Rows 3–10 share a feature vector: the only failed check, every rep of this system fails
  it, and the other system passes it on every rep. The model cannot separate a systematic grader
  blind spot for one system's formatting from one system's systematic mistake. That is exactly what the human
  audit decides.
- **The pass-to-fail attempt** (`tuition-collections__codex-sol__r3`) ranks 48th of 142.

## Artifact layer (`rank --run`)

When raw workspaces exist locally (`results/<label>/<run_id>/ws`, from `bench/run.py`), each failed check is
re-run by itself. The run is always on a temporary copy of the agent's own files, never in place:

1. **As recorded.** If the recorded fail does not reproduce locally, the row says so.
2. **Under each invariant transform** of the files the check reads, using the `bench/metamorphic.py` classes
   and classification. A flip to pass puts the check in **tier 1**: correct-looking work fails only because of
   formatting.
3. **Under "formatted differently" probes.** A flip puts the check in **tier 2**. Probes relax the contract a
   little, so they are weaker evidence:
   - typographic quotes, dashes and NBSP to ASCII, with Markdown emphasis stripped;
   - whitespace collapsed within paragraphs;
   - CSV headers renamed when their word set matches a required column;
   - CSV text compared alphanumerically;
   - a workbook value present but not beside its label;
   - a workbook value present when rounded to whole units;
   - the deliverable present under another extension.

**Ordering.** Attempts are ranked by (tier, score). An attempt's tier is its *weakest* check's tier, because
the verdict flips only if every failure is an error. Each row carries the probe outcomes in its reason.

**Workbook checks are lower-confidence locally.** Without LibreOffice (as on this Mac), recalculation falls
back to `formulas`, which returns `#NAME?` for COUNTIFS/SUMIFS. Rows whose check reads a workbook are marked
`LOW CONFIDENCE`. Set `BENCH_RECALC_DOCKER_IMAGE` to use the bench-recalc container instead.

The artifact layer has **no labels yet**. The tiers are a rule, not a fitted model. The unit tests check only
two things:

- a hard-wrapped memo sentence reaches tier 1 while a genuinely missing phrase stays tier 3;
- the run directory's bytes are unchanged.

## Limits

- **The labels are positive-unlabelled.** A negative means "the frozen scorer still fails it", not "a human
  confirmed the agent erred". Undiscovered grader errors sit among the negatives (the queue's whole purpose),
  so the reported precision is a lower bound on what an audit would find, and the AUC is biased in an unknown
  direction.
- **One revision, one arm, few clusters.**
  - The model learns what the v7 revision fixed: header naming, alternative answers, row-count options,
    sentence unwrap and seven equivalence modules.
  - It is trained on codex-sol's failures, spread over 21 tasks with positives.
  - A future revision that fixes a different class of bug may not look like this one.
- **The raw view is a proxy.** `87f624e`'s `grade.py` and task files stand in for the exact run-time scorer.
  The verdicts themselves are the recorded raw ones.
- **Panel shift.** Training sees 12 attempts per task over 4 arms. Ranking sees 6 over 2. The two-arm
  sensitivity above is the more honest estimate for the published queue.
- **Repetitions are not independent.** Three reps of one task usually move together. Use `tasks.csv` for the
  audit and treat attempt-level P@k as optimistic about coverage.
- **Local workbook recalculation** is unreliable without LibreOffice (see above). The metamorphic scan leaves
  workbook checks untested.
- **`rank --run` needs a fitted model** (`docs/triage/model.json`). It scores with the ledger-trained model and
  therefore inherits every limit above.

## Future work

- **Retrain on the audit.** Once the 50-task audit labels exist, refit on human labels (both arms) and replace
  the proxy.
- **Check-detail features.** Record the grader's `detail` string in the ledger. Examples: "missing
  ['store credit']" and "accuracy 0.97; wrong=[...]". This is cheap, public-safe and far more informative than
  the verdict bit.
- **A PR-quality-style classifier.** A fine-tuned model over (check spec, grader detail, a redacted excerpt of
  the agent's deliverable) could score "the value is there, the grader missed it" directly. It needs private
  artifacts and audit labels to train, and must stay out of the scoring path: it only orders the audit queue.
  Not built.
