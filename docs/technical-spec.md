## 7. Task inventory and contracts

The release contains 187 desk tasks and 20 build tasks. Every task includes a generator and evaluator-side materials. Only workspace inputs and the owner's request are provided to the evaluated agent; reference answers, check definitions, traps, and task author notes are not mounted into the agent container.

| Desk category | Tasks | Typical deliverable |
|---|---|---|
| Spreadsheet | 41 | Reconciled, calculated, or reshaped workbook |
| Bookkeeping | 36 | Reconciliation, schedule, transaction classifications |
| Reports | 30 | Data summary and source-grounded memo |
| Reformatting | 26 | Destination-compatible import file |
| Extraction | 26 | Structured records extracted from documents |
| Drafting | 19 | Business text preserving required facts and rules |
| Tooling | 9 | Small file-based tool or static page |
| Total | 187 | Three repetitions per complete desk arm |

A desk task directory contains task.yaml, gen.py, workspace/, reference/, reference_solution/, and, when required, check.py. The YAML declares the ask, category, time budget, and checks. Files in reference_solution/ provide a positive control, not an agent solution to ship in the run workspace. A generator creates reproducible task fixtures; a regenerated seed is a related variant, not evidence of an independently sourced held-out task distribution.

A build task directory contains task.yaml, gen.py, seed/, reference/counts.json, checklist.md, and three change-request files. The application inventory covers CRM, inventory, orders, field service, leave, purchase approvals, time and invoicing, memberships, events, assets, helpdesk, vendors, expenses, quotes, donors, appointments, property maintenance, recruiting, work orders, and point of sale.

The build acceptance baseline covers delivery, invitations, role management, server-side access control, scoped live dashboards, exact lists/exports, audit metadata, validation, and persistence. App-specific requirements add domain behavior. The supplied checklists, including the field-service task's distinct baseline placement, are authoritative; no uniform item count is inferred merely from the number of tasks.

## 8. Execution protocol

### 8.1 Agent boundary

The desk runner copies only the task workspace into an opaque temporary directory, writes the request separately, and invokes a harness adapter with three arguments: workspace, prompt file, and output directory. In Docker mode the agent sees /run/ws and the per-run home; the benchmark task tree and reference answers stay on the host. Read-only adapters are mounted separately. The container runs as the host user with CPU, memory, and process-count limits. Network access remains available for model requests and permitted tooling; this is not an offline benchmark or a complete defense against discovering published tasks online.

Local-process mode exists for operator development and smoke tests. It does not hide host files from an agent with shell access and is not appropriate for a reference-isolated official comparison. Containers must not receive a Docker socket, broad home mount, production credentials, or unrelated data.

### 8.2 Desk attempts

Tasks run in a fresh workspace per repetition. The default timeout comes from task.yaml unless the operator explicitly overrides it. The recorded full campaign used 2 CPUs and 6 GB per container, API-cell concurrency of five, and Codex concurrency of two. The runner allows a shutdown grace interval, so elapsed wall time can exceed the nominal task budget. Full arms contain exactly one record for every task-repetition pair.

The historical protocol is single-turn desk execution. Follow-up fields in legacy design notes do not imply that this runner implements scripted desk follow-ups. A future multi-turn desk experiment needs an explicit protocol and separate results.

### 8.3 Build sequences

The build runner executes the initial request followed by up to three changes. Each turn is a new one-shot invocation with the prior workspace carried forward, not a claim of preserved conversational state. Only the owner's portion of a change file is sent; its tester checklist remains outside the agent view. RESULT.json records the application URL, working admin and restricted logins, notes, start command, and port. The restricted identity must remain consistent across changes.

Self-hosted builds use a dedicated port and a local data store. Linux host networking permits the grader to reach that port but does not establish reachability from another network. A platform-backed build needs an authorized test organization. A killed container can stop a hosted process; restarting it locally supports testing but does not erase a failure of the originally handed-over public URL. Record those observations separately.

## 9. Grading and reporting

### 9.1 Desk outcome

The recorded artifact-pass field is true when all required checks pass. Checks include file existence and structure, exact identifier sets and row counts, keyed values, workbook formulas and values, text requirements, and task-specific rules. Optional checks remain diagnostic. Required-check conjunction is the headline task-level criterion; a percentage of checks is not the same as a passed task.

Workbook grading should use native LibreOffice recalculation after cached values are stripped. Set BENCH_RECALC_DOCKER_IMAGE to the supplied recalculation image. The legacy grader also has a Python-formula/cached-value fallback when no native engine is configured; this fallback is development-only and must not be presented as equivalent official scoring. Configured native-engine failures are reported, not silently converted into passes.

Execution status is independent of artifact pass. The publication retains timeouts, nonzero exits, grader-error counts, and missing usage. A passing artifact written before abnormal termination remains a recorded artifact pass, not evidence of a clean completed run. The tables show how many such cases occur. Grader-error attempts stay in the denominator; no selective rerun or omission improves the headline.

### 9.2 Build outcome

The build grader performs limited delivery/probe checks and generates a tester sheet for unautomated requirements. A tester must verify role boundaries, server-side authorization, invitations, live data, rules, and persistence where the checklist requires them. Score the initial checklist, the new change items, and regressions of previously passing requirements separately. Automated reachability or a login-shaped page alone does not establish working credentials or an accepted application.

### 9.3 Metrics

- Attempt pass rate: passing artifacts divided by every scheduled attempt in a complete arm; this release's denominator is 561 per arm.
- All-three success: tasks passing in all three repetitions, divided by 187. This is observed repeated-task consistency, not a confidence interval or long-horizon service guarantee.
- Resource measures: median elapsed time, recorded usage, and estimated model cost, with missing observations stated. Cached input is priced separately from uncached input using the bundled price assumptions.
- Build measures: accepted baseline items, core delivery criteria, new change requirements, regressions, time and cost across the sequence. No combined desk/build score is defined.

The included price table is a historical estimate input, not verified current billing advice. Missing costs are not zero. Subscription-equivalent API estimates do not equal subscription charges. Human review, infrastructure, and external platform charges are outside these model-cost estimates.

## 10. Validity, safety, and release boundary

Most task authoring used model assistance. Positive/negative controls, deterministic regeneration, and planted-trap checks provide mechanical validation; independent practitioner review and a human performance baseline are not established by this release. The suite was developed by an organization that also develops one of the evaluated harnesses. Exposure to the task set and benchmark-driven development limit claims about unseen generalization.

The latest result release is a recorded snapshot of the complete arms of campaign full-1. Incomplete arms, build drafts, development comparisons, and tuning pilots are excluded rather than merged into a leaderboard. Historical attempt records do not carry immutable scorer identities, and the original image tag is not an image digest. The portable release source therefore supports new runs but does not guarantee byte-for-byte reconstruction of the historical agent environment or scores.

Task generators and custom checks are executable code. Review them before running on sensitive infrastructure. Raw attempt folders can contain configuration keys, session traces, generated app credentials, and sensitive model responses; keep them private. The released ledger is deliberately allowlisted and contains neither these folders nor generated app logins. Audit-model tools can send authorized task and run contents to an external provider; they are opt-in and separate from deterministic grading.

## 11. Reproduction and extension

README.md contains the complete setup and run commands. Install the pinned direct Python dependencies, build the agent and recalculation images, provision benchmark-only model access, and validate the task packs. Start with a single-task smoke run before launching all 187 tasks with three repetitions. Use a new label for every campaign; the release runner refuses to overwrite an existing desk label or attempt directory.

Release verification passed the reference-solution and untouched-workspace checks for all 187 desk tasks using native recalculation, and the build-task validator passed all 20 application packs. The strict desk validator also reported 28 cases where regenerated files differ from the supplied fixture bytes, despite repeated regeneration being deterministic within the check. The supplied fixtures are preserved as the release inputs; do not replace them implicitly with regenerated versions. These notices are documented in docs/validation.md and do not establish semantic equivalence between the two byte sets.

For new comparisons, record the repository commit, task file hashes, full container digests, model and provider route, reasoning settings, installed skill/plugin inventory, time and resource budgets, dependency resolution, and scorer digest before launch. Persist all scheduled outcomes and validate matrix completeness before reporting. If a scorer changes, rescore retained artifacts into a separately named snapshot, preserving the original evidence and declaring exactly what changed.

New harnesses implement the same workspace/prompt/output adapter contract and supply usage extraction when available. New tasks require explicit deliverables, source-supported business rules, a reference solution, meaningful negative controls, and deterministic inputs. Do not weaken a task to improve a participant's score. Do not claim universal business competence from performance on this finite suite.
