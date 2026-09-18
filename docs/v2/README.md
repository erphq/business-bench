# Business Bench v2: specification for discussion

Status: agreed direction, 2026-09-18. Task authoring has not started. This document
is the contract the v2 tasks will be written against. It supersedes nothing in v1;
v1's 187 tasks become the clerical band of v2's difficulty axis.

## 1. Why this benchmark exists

Agent evaluation has split into two camps. Code benchmarks have exact verifiers but a
narrow domain, and the well-known ones are now contaminated and reward-hacked. Work
benchmarks have economic breadth but grade with rubrics, pairwise human preference,
or LLM judges, so they measure plausibility rather than correctness.

Business work is the one large economic domain where both properties hold at once.
The inputs are messy, long-horizon, and spread across many documents. The deliverable
has a ground truth: a reconciliation balances or it does not, a tax treatment is right
or it is not, a schedule is feasible or it is not. That makes it the natural place to
measure three things the field cannot currently measure well:

1. **Conjunctive correctness.** A task passes only when every required check passes.
   Agents routinely satisfy 90% of checks and earn nothing, which is the property that
   separates a demo from delegation. The per-check versus per-task gap is a first-class
   published number.
2. **Reliability, not capability.** The unit is pass-all-k over repeated attempts, not
   pass@k. An owner runs the process every month. Three repetitions today, five in v2.
3. **Procedurally generated, verifiable economics.** Every task is a generator with a
   seed and a planted truth. That yields contamination-resistant sealed variants, a
   tunable difficulty axis, and, when we choose to release it as such, an RL
   environment for economically valuable work with dense exact rewards.

The benchmark is published on businessbench.org and in this repository. It does not
depend on any third party to validate it. What replaces institutional review is a
release discipline anyone can check: hashed task manifests, receipts binding each
verdict to a scorer, raw and frozen verdicts side by side, a public dispute process,
seeds held back for sealed variants, and a human baseline whose raw sheets are
published.

## 2. Definitions

A task *t* declares a set of required checks *C_t* over the artifacts left in the
workspace. An attempt passes iff every *c* in *C_t* passes. Each task is run *k* times
in a fresh workspace (*k* = 3 in the current release, 5 from the first v2 campaign).

| Symbol | Definition | Reading |
|---|---|---|
| pass@1 | mean attempt pass rate over all scheduled attempts | headline rate |
| pass@k | fraction of tasks with at least one passing repetition | what a demo shows |
| pass^k | fraction of tasks passed in all *k* repetitions (τ-bench) | what an owner experiences |
| check rate *c̄* | passed required checks / all required checks, pooled | per-check view |
| conjunctive gap | *c̄* − pass@1 | partial credit a conjunctive grader refuses |
| near-miss share | failed attempts with exactly one failed check / failed attempts | verification failures |
| gap to optimum | (objective − reference optimum) / reference optimum, for axis 5 | recorded diagnostic |
| cost per pass | captured-usage cost at list price / passing attempts | buyer's unit |

Current values for the released comparison are computed on businessbench.org/analysis
from the ledger at build time.

## 3. Capability axes

v2 tasks are organised by the capability they isolate. Departments (finance, ops,
legal, HR) are how a task is instantiated, not how it is reported.

| Axis | Tasks | Isolates | Primary check types |
|---|---|---|---|
| 1. Rule-stack application | 14 | Many interacting rules, one correct outcome per entity | rule, keyed, pin |
| 2. Cross-document state tracking | 14 | The answer exists only after reconciling many files | set, keyed, pin |
| 3. Evidence sufficiency | 12 | Saying "cannot be determined" when the files do not support it | must-state, pin |
| 4. Adversarial robustness | 16 | Planted fraud, plausible unauthorized instructions, injected documents | set, not-fooled |
| 5. Constrained quantitative planning | 18 | Schedules and plans graded by feasibility plus gap to a known optimum | feasible+bound, held-out |
| 6. Self-verification and handoff | 12 | Whether the agent checks its own output against the source before handing over | pin, keyed, must-state |
| 7. Process discovery and conformance | 14 | Recovering the process from event logs and finding where it breaks | set, keyed, held-out |

The full list with planted truth and check per task is in [tasks.md](tasks.md).

Axes 4, 6, and 7 are the ones this benchmark contributes that others do not. Axes 1
and 2 are where v1 already lives and are deliberately the smallest.

## 4. Grading vocabulary

Every v2 task is graded by executable checks against truth the generator planted. No
rubric, no LLM judge, no pairwise preference. Existing v1 check types cover most of
the vocabulary; three additions are needed in `bench/grade.py` before authoring
starts.

| Name | Meaning | Status |
|---|---|---|
| set | exact identifier set equals reference | v1 `csv_set_equal` |
| keyed | per-key values within tolerance, with must-match keys | v1 `csv_values_match` |
| pin | recalculated workbook figure equals expected | v1 `xlsx_value_present` + `xlsx_no_errors` |
| rule | per-entity categorical outcome equals reference | v1 `csv_values_match` on a category column |
| must-state | a sentence names the exception, gap, or refusal | v1 `text_sentence_matches` |
| feasible+bound | task-specific constraint checker passes and objective is within X% of the reference optimum | `plan_feasible` (module + `max_gap`), shipped v1.1.0 |
| held-out | forecast scored against generated future truth at a stated error bound | `forecast_error` (metric, bound), shipped v1.1.0 |
| not-fooled | a planted adversarial instruction was not acted on; the artifact shows the pre-instruction state | `not_fooled` (planted keys, forbidden text, flag), shipped v1.1.0 |

Partial credit: none at task level. For feasible+bound tasks the gap is recorded as a
diagnostic field so a gap curve can be published; the pass threshold is stated in the
task.

## 5. Difficulty axis

Every v2 generator exposes three parameters: `size` (rows and files), `rules` (count of
interacting rules), and `noise` (rate of formatting and data defects). Each task
declares three bands built from the same generator:

| Band | Persona | Typical size | Time budget |
|---|---|---|---|
| clerical | bookkeeper or office manager | hundreds of rows, 3 to 6 files | 20 min |
| analyst | staff accountant or ops analyst | thousands of rows, 6 to 15 files | 40 min |
| controller | controller, FP&A lead, ops director | tens of thousands of rows, 15+ files | 60 min |

Results are reported per band. The v1 set is the clerical band. A system's score is a
curve, not a number.

## 6. Sealed variants and contamination

The public task set is exposed by design. Each generator accepts `--seed`. A sealed
variant is the same task with re-rolled entities, amounts, dates, and planted
positions. Sealed seeds are held by the maintainers and used for a private evaluation
when a public score is disputed or when a system is suspected of having trained on the
public set. A public score and its sealed-variant score are published side by side
when both exist; a gap larger than the repetition variance is reported as such.

## 7. Human baseline

A commissioned baseline is part of the v2 release, not an afterthought. Protocol and
contractor brief: [human-baseline.md](human-baseline.md). Summary: stratified sample of
50 tasks, two independent human attempts per task at the analyst band, humans use the
same files and the same checks, raw time and verdict sheets published.

## 8. What a business harness has to do

Proto is one of the evaluated systems and competes on its merits. It is also the
worked example this project uses to show what a business harness needs, because no
public harness has been designed for this work. The properties below are evidenced by
the adapters, runner, and grader in this repository. The Proto-specific write-up with
attempt traces is pending trace access and will be published as its own page.

- Artifact-first delivery: the deliverable is the files left in the workspace, not the
  final message. Nothing an agent says is graded.
- Native recalculation: workbooks are recalculated in LibreOffice after cached values
  are stripped; a harness that writes formulas must verify them the same way before
  handing over.
- Isolation per attempt: a fresh workspace and a per-run copy of a bare home, so
  memory and skills never leak between attempts.
- Provider pinning and budgets: one adapter, one cell, model and route pinned, with
  explicit iteration, token, and time budgets recorded in provenance.
- Self-verification before handoff: the harness should recompute its own control
  totals and tie-outs against the source before ending the turn. Axis 6 measures this.
- Refusal as a first-class outcome: when evidence is insufficient, the correct
  deliverable says so. Axis 3 measures this.

## 9. Release discipline

- Task set versions are semver; any change to a task, check, or scorer bumps it.
- Every campaign is labeled; results are never merged across labels.
- Raw and frozen verdicts are both retained per attempt with receipts.
- Disputes are GitHub issues; accepted corrections change the version.
- Five repetitions per cell from the first v2 campaign.
- The self-audit page is updated with every release and lists what a reviewer would
  find first.

## 10. Threats to validity

Stated here so that no reviewer has to discover them.

- **Construct.** Executable checks measure contract satisfaction, not editorial quality
  or owner delight. A memo can pass every check and still be badly written. We accept
  this: the contract is what was delegated.
- **Check strictness.** A conjunctive grader turns every strict check into a task
  failure. The near-miss share confounds "did not verify" with "check too strict".
  The false-negative audit (human re-read of failures) is the only way to separate
  them and is on the order of work.
- **Scorer authorship.** The scorer is written by the organisation that builds one of
  the evaluated systems, after outputs exist. Mitigations: hashed frozen packages,
  raw verdicts published beside frozen, and an independent scorer review before the
  first v2 campaign is reported.
- **Cohorts and configurations.** Systems differ in model, sampling, and timing.
  Results are end-to-end configuration comparisons until a same-model control pair
  is run.
- **Exposure.** The public set was used during development of one system and is
  public now. Sealed variants and the difficulty axis are the mitigations; a public
  score is never presented as an unseen-generalisation result.
- **Reward-hacking surface.** Agents never see checks, references, or traps; only the
  workspace is mounted, and the deliverable is graded as files. The remaining surface
  is the network, through which a public task could be found. Sealed variants close it
  for private evaluations.
- **Repetitions.** *k* = 3 estimates pass^k coarsely. v2 uses *k* = 5 and reports a
  task-clustered bootstrap interval for every headline difference.

## 11. Order of work

1. Done (v1.1.0): the three check types in `bench/grade.py`, rules in `bench/check_rules.py`,
   tests in `tests/test_checks_v2.py`.
2. Done (v1.1.0): `tasks/lib/bizgen/eventlog.py`, `planning.py`, `adversarial.py`, tests in
   `tests/test_bizgen_v2.py`.
3. Author axes 4, 6, 7 first (42 tasks), then 3 and 5, then 1 and 2.
4. Commission the human baseline on the first 50 authored v2 tasks plus v1 sample.
5. First v2 campaign: five repetitions, sealed variant for the top system, published
   with the per-check gap and the difficulty curve.
