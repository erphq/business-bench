# Research goals

Measure, for a stated workload and operating environment, how often a configured
system delivers work accepted by an explicit contract. Establish separately whether
those contracts capture business requirements and how results transfer to new work.
[STATUS.md](STATUS.md) records current evidence; checkmarks below mean repository
artifacts or published records exist, not that external validity has been established.

## Released foundation

- [x] 187 desk tasks with generators, references, checks and validation tooling.
- [x] 20 build packs with seed data, acceptance checklists and three changes each.
- [x] Complete desk comparison: two systems, 1,122 attempts, shared frozen scorer,
  original verdicts retained, and per-attempt evidence hashes.
- [x] Research paper, executable evidence verification, public wiki and MIT license.
- [x] Process kernel, local runner, checks, and oracle/negative-control validator.
- [x] Six clerical process tasks and one analyst task, `ap-invoice-backlog`.
- [x] Six-task local process pilot, five repetitions per cell, published separately.

## Highest-priority validation

- [ ] Independent artifact adjudication on a declared stratified sample of accepted
  and rejected attempts; publish reviewer agreement, disputes, and both error types.
- [ ] Independent review of the seven frozen equivalence graders, including plausible
  invalid artifacts and valid alternative representations.
- [ ] Practitioner review of process rules and planted exceptions; record changes
  before evaluating the revised tasks.
- [ ] Prospective campaign with frozen scorer, explicit configuration and workload,
  retained evidence, and controlled same-model comparisons where appropriate.
- [ ] Separate results for fresh seeded instances and held-out templates; repeated
  exposed fixtures are not a substitute for either experiment.
- [ ] Human completability baseline and complete build acceptance campaign, including
  direct authorization requests, actual restart persistence and change regressions.
- [ ] Effective container digest, runtime, dependency and authorized skill inventory
  captured per attempt; verified process isolation beyond local mode.

## Proposed v2 research program

- [x] Seven-axis, 100-task design catalog and proposed difficulty bands documented.
- [x] Human baseline protocol and budget estimate documented; no completed baseline
  or commissioned participant cohort is claimed.
- [x] `plan_feasible`, `forecast_error`, `not_fooled` and generator helpers implemented.
- [ ] Author and review the v2 task packs, beginning with axes 4, 6 and 7 (42 proposed
  tasks). A catalog entry is not an implemented generator or validated task.
- [ ] Run the proposed 20-task v1 human pilot, then a stratified 50-task v2 baseline;
  distinguish unaided and AI-assisted work in the published record.
- [ ] Evaluate five repetitions per declared cell and report per-band results,
  predicate granularity, instance/template exposure and measured resource limits.

The [v2 specification](docs/v2/README.md) and [process specification](docs/process/README.md)
describe the hypotheses and acceptance conditions for this work. Process catalog
expansion, browser/MCP interfaces, additional company archetypes and training-environment
use remain proposals, not evidence of current performance.

## Non-goals

- Combining desk, build and process scores into one rank.
- Claiming universal competence, causal model/harness superiority, or unattended
  production readiness from the current observations.
- Weakening a task to improve a participant's score, or silently revising a released
  evaluator, fixture or result ledger.
- Treating hashes, generated truth, or model-assisted review as substitutes for
  independent validation of the acceptance contract.
