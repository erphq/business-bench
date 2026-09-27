# Goals

The benchmark's job: answer, for a stated operating environment and budget,
how reliably a configured agent system delivers business work that satisfies
the owner's requirements. Reviewable by design; the release states its own gaps.

## Milestones

- [x] Desk track: 187 tasks with generators, checks, references, strict validation
- [x] Build track: 20 packs with seed data, enterprise baseline checklist, 3 changes
- [x] Runner, grader, native workbook recalculation, release manifest, ledger export
- [x] Complete desk comparison: two systems, 1,122 attempts, one frozen scorer, raw verdicts retained
- [x] Per-attempt receipts: original result hash, artifact hashes, scorer manifest hash
- [x] Specification and paper (SPEC.md, PDF)
- [x] v1.0.0 public release, MIT
- [x] businessbench.org: results, task pages, methods, paper, reproduce, self-audit
- [ ] Independent review of the frozen scorer's equivalence graders
- [ ] Independent 50-task audit with committed verdicts
- [ ] False-negative estimate from failed artifacts; plausible-wrong negative controls
- [ ] Contemporaneous rerun: five repetitions per cell; matched same-model harness control pair
- [ ] Proto on ERP.AI platform cell published as its own campaign
- [ ] Container digest and runtime revision recorded per attempt by the runner
- [ ] First complete build arm with human acceptance; publish build measures
- [ ] Human completability baseline on the audited sample
- [ ] External review request (Epoch AI Benchmark Reviews) once the above land

## v2 (spec in docs/v2)

- [x] Thesis and capability axes agreed; 100 tasks listed with planted truth and checks
- [x] Human baseline protocol and budget approved
- [x] Check types `plan_feasible`, `forecast_error`, `not_fooled` in grade.py with validator rules (v1.1.0)
- [x] Generator library: event-log emitter, constraint-checker scaffold, adversarial injector (v1.1.0)
- [ ] Axes 4, 6, 7 authored (42 tasks, three bands each)
- [ ] Axes 3 and 5, then 1 and 2
- [ ] Human baseline run on 20 v1 pilot + 50 v2 tasks, raw sheets published
- [ ] First v2 campaign: five repetitions, sealed variant for the top system, difficulty curve
- [ ] Proto reference-harness page with attempt traces
- [ ] Environment release (generators as RL environment) after the benchmark is established

## Process track (spec in docs/process)

- [ ] Spec reviewed and the five open decisions settled (docs/process/README.md section 14)
- [x] bb-erp kernel: lifecycles, hard controls, audit log, clock, reports, HTTP API, `erp` command
- [x] Counterparty simulator, scenario format, twelve-month history generation
- [x] Runner, the six process check types and audit rules, `validate_process.py`
- [x] Pilot: six tasks with oracles and negative controls passing validation
- [ ] Practitioner review of the pilot (AP lead, production planner, controller)
- [x] Pilot campaign: five repetitions per cell, published under its own label (`pilot-process-2026-09-27`, local mode)
- [ ] The pilot campaign repeated in containers
- [ ] Remaining 18 tasks, then the analyst and controller bands
- [ ] Browser interface and human baseline on the pilot

## Non-goals

- A single combined score across the desk, build, and process tracks.
- Claims of universal business competence or unattended production readiness.
- Weakening a task to improve any participant's score.
