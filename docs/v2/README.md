# Business Bench v2: specification for discussion

Status: proposed research program, reviewed against repository state 2026-09-28.
The three new check types and generator helpers exist; the 100 task descriptions
below are a design catalog, not a released v2 task suite. No v2 campaign or human
baseline is published. The separate process track has seven implemented tasks.
Existing desk tasks have not been empirically calibrated to the proposed bands.

## 1. Why this benchmark exists

Business tasks often combine heterogeneous evidence with an output whose required
properties can be tested: a reconciliation, a destination-compatible import, or a
feasible schedule. Executable checks make the acceptance boundary inspectable, but
cannot establish that the boundary captures every relevant business requirement.
Human and model-assisted review can evaluate properties that a mechanical contract
omits; neither evaluation approach is a universal substitute for the other.

The proposed v2 program studies three questions:

1. **Conjunctive correctness.** A task passes only when every required check passes.
   A high fraction of passed predicates need not produce an accepted artifact.
   Report both quantities with explicit weighting; predicate decomposition changes
   the partial-check fraction.
2. **Execution repeatability.** Report attempt acceptance, all-k acceptance and
   at-least-one acceptance separately. Repeating one fixture is not the same as
   completing new monthly work. The proposed v2 campaign uses five repetitions.
3. **Generated instances and declared difficulty.** Seeded generators can create
   new instances of known templates. Separately held-out templates and practitioner
   review are needed to test broader transfer and validate difficulty bands.
   Training-environment use remains a possible extension, not a current result.

The benchmark is published on businessbench.org and in this repository. Hashed
manifests, receipts and original/frozen verdicts support traceability. They do not
replace independent review of task realism, valid alternatives or plausible invalid
outputs. Human baselines, sealed evaluations and independent adjudications remain
planned evidence, with no completed records claimed here.

## 2. Definitions

A task *t* declares a set of required checks *C_t* over the artifacts left in the
workspace. An attempt passes iff every *c* in *C_t* passes. Each task is run *k* times
in a fresh workspace (*k* = 3 in the current release, 5 from the first v2 campaign).

| Symbol | Definition | Reading |
|---|---|---|
| pass@1 | mean attempt pass rate over all scheduled attempts | headline rate |
| observed at-least-one | fraction of tasks with at least one passing repetition | availability with hindsight, not a measured selection policy |
| pass^k | fraction of tasks passed in all *k* repetitions (τ-bench) | observed repeated acceptance on fixed fixtures |
| check rate *c̄* | passed required checks / all required checks, pooled | per-check view |
| within-attempt check fraction | mean of each attempt's fraction of required predicates passed | gives each attempt equal weight |
| conjunctive gap | within-attempt check fraction − pass@1 | isolates conjunction without extra check-count weighting |
| single-predicate failure share | failed attempts with exactly one failed required predicate / failed attempts | diagnostic; not an error count or root cause |
| gap to reference objective | sense-aware relative gap under `plan_feasible`, for axis 5 | a reference is not a proven optimum unless certified |
| model cost per accepted attempt | captured-usage model cost / accepted attempts | ex-post accounting; excludes review and repair |

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
| 6. Verification and handoff | 12 | Consistency of the handoff with the source; process claims require trace evidence | pin, keyed, must-state |
| 7. Process discovery and conformance | 14 | Recovering the process from event logs and finding where it breaks | set, keyed, held-out |

The full list with planted truth and check per task is in [tasks.md](tasks.md).

Axes 4, 6 and 7 are proposed priorities, not claims of exclusive coverage relative
to other benchmarks. The axes organize hypotheses; cross-task construct validation
and actual task authoring are still required.

## 4. Grading vocabulary

Every v2 task is graded by executable checks against truth the generator planted. No
rubric, no LLM judge, no pairwise preference. Existing v1 check types cover most of
the vocabulary; the three additions below are already implemented in
`bench/grade.py` and covered by focused tests.

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

The proposed v2 generator interface exposes three parameters: `size` (rows and files), `rules` (count of
interacting rules), and `noise` (rate of formatting and data defects). Each task
declares three bands built from the same generator:

| Band | Persona | Typical size | Time budget |
|---|---|---|---|
| clerical | bookkeeper or office manager | hundreds of rows, 3 to 6 files | 20 min |
| analyst | staff accountant or ops analyst | thousands of rows, 6 to 15 files | 40 min |
| controller | controller, FP&A lead, ops director | tens of thousands of rows, 15+ files | 60 min |

The plan is to report results per band after task authoring and human calibration.
The existing v1 set is a starting point, not a validated clerical difficulty band.

## 6. Sealed variants and contamination

The public task set is exposed by design. Each generator accepts `--seed`. A sealed
variant is the same task with re-rolled entities, amounts, dates, and planted
positions. A future sealed evaluation must record seed custody, task version, scorer and
analysis plan before execution. No released campaign currently establishes this
procedure. Re-rolling known templates does not erase template exposure. Compare
public instances, new instances and held-out templates separately, with an analysis
that accounts for both task and execution variation.

## 7. Human baseline

A human baseline is a proposed release requirement; this repository does not
establish commissioning, recruitment or completed attempts. Protocol and draft
contractor brief: [human-baseline.md](human-baseline.md). Summary: stratified sample of
50 tasks, two independent human attempts per task at the analyst band, humans use the
same files and the same checks, raw time and verdict sheets published.

## 8. What a business harness has to do

Proto is one evaluated system, developed by the benchmark publisher. The properties
below are proposed design requirements for any configured system. The repository's
runner and adapters implement only the portions described in the
[adapter contract](../../harnesses/contract.md); the list is not evidence that a
particular harness satisfies every requirement. Independent artifact and trace review
would be needed for a system-specific explanation.

- Artifact-first delivery: the deliverable is the files left in the workspace, not the
  final message. Nothing an agent says is graded.
- Native recalculation: workbooks are recalculated in LibreOffice after cached values
  are stripped; a harness that writes formulas must verify them the same way before
  handing over.
- Declared state boundaries: fresh workspaces, explicit home/configuration handling,
  and a tested isolation boundary. Current desk/build Codex runs reuse a configured
  home; process turns copy homes but run as local processes.
- Effective configuration records: declare model, route, runtime and budgets,
  including environment overrides. Adapter defaults are not proof of the settings
  used in an arbitrary run.
- Self-verification before handoff: the harness should recompute its own control
  totals and tie-outs against the source before ending the turn. Axis 6's artifact
  checks can measure consistency; proving that the system performed verification
  requires trajectory evidence and an explicit process measure.
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
  or owner satisfaction. A memo can pass every check and still be unusable. Review
  accepted artifacts as well as rejected ones to identify omitted requirements.
- **Check strictness.** A conjunctive grader turns every strict check into a task
  failure. The near-miss share confounds "did not verify" with "check too strict".
  Independent adjudication of accepted and rejected outputs, supplemented by targeted
  mutations and valid alternatives, is planned to investigate both error types.
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
- **Evaluation leakage.** Containerized desk runs omit host-side checks and references
  from mounts; local runs provide no such boundary. Network access and known template
  structure remain exposure paths. Private instances reduce direct answer lookup but
  do not eliminate contamination or evaluator exploitation.
- **Repetitions.** *k* = 3 estimates pass^k coarsely. v2 uses *k* = 5 and reports a
  task-clustered bootstrap interval for every headline difference.

## 11. Order of work

1. Done (v1.1.0): the three check types in `bench/grade.py`, rules in `bench/check_rules.py`,
   tests in `tests/test_checks_v2.py`.
2. Done (v1.1.0): `tasks/lib/bizgen/eventlog.py`, `planning.py`, `adversarial.py`, tests in
   `tests/test_bizgen_v2.py`.
3. Author axes 4, 6, 7 first (42 tasks), then 3 and 5, then 1 and 2.
4. Review tasks, recruit participants and commission the proposed baseline only after
   documenting the sample, tools, consent, compensation and adjudication procedure.
5. First v2 campaign: five repetitions, sealed variant for the top system, published
   with the per-check gap and the difficulty curve.
