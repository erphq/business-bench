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

## Non-goals

- A single combined desk plus build score.
- Claims of universal business competence or unattended production readiness.
- Weakening a task to improve any participant's score.
