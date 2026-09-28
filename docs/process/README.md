# Business Bench process track: specification for review

Status: implementation and research plan, reconciled 2026-09-28. bb-erp, the local
runner, process grader and seven task packs are implemented: six clerical pilot tasks
plus the analyst task `ap-invoice-backlog`. The published pilot covers only the six
clerical tasks at seed 0, five repetitions per cell; both systems pass 30/30.
It ran locally before practitioner review. No analyst-task result, isolated process
campaign or human baseline is published.

Companion files: [environment.md](environment.md) distinguishes the current system
from proposed isolation; [tasks.md](tasks.md) labels the 24-task design catalog and
implemented subset. [Reproducibility](../reproducibility.md) maps claims to records.

## 1. Why a third track

The desk track hands the agent a folder of exported files and grades the files it
leaves behind. The build track asks the agent to build an application and grades the
application. Neither puts the agent inside a system of record that other people also
use, which is where most business staff do their work. Their processes run for several
days and follow a policy manual.

Work inside such a system has properties a folder of files cannot reproduce:

- **State that outlives the session.** What the agent did on Monday is still in the
  system on Friday, together with what other people did in between. A later turn has
  to read the system to find out where the process stands.
- **Authority.** The agent acts as one user with a role and limits. The system refuses
  some actions outright. The handbook forbids others that the system would allow.
- **Consequences.** Every write is a posted document with downstream effects. A
  purchase order at the wrong price produces an invoice that fails matching three days
  later. Corrections go through reversals, credit memos, and cancellations with a
  reason, because posted documents cannot be deleted.
- **Counterparties.** Approvers approve or reject, vendors ship short or substitute,
  customers pay short, the bank posts fees. They act between the agent's turns,
  deterministically, according to the scenario.
- **Exceptions among routine work.** Most items in a queue should go straight through.
  A few are planted exceptions, and the right handling is usually to stop and route
  them: a hold with a reason code, an escalation to the person who can decide, a
  refusal.

The process track measures whether an agent leaves the operational and accounting
state of the system correct at the end of a process, without breaching a control on
the way.

## 2. Definitions

A **process task** is a scenario generator plus a script of turns.

- The **scenario** is a seeded state of a company's ERP: master data, twelve months of
  consistent history, open transactions, an inbox, the counterparties' behaviour
  profiles, and the planted exceptions with their truth.
- A **turn** is a business date, a request from a named person in the company, and a
  time budget. Each turn runs a fresh agent session against the same system and the
  same workspace folder.
- Between turns the runner **advances the business clock**. Counterparties act on what
  the system then contains, so what they do depends on what the agent did.
- After the last turn the runner advances to the **grading date**, lets pending
  counterparty actions settle, and grades the final state.
- The **oracle** is a reference policy that plays every turn through the interface the
  agent uses, with the agent's token. Its final state is the reference. It proves each
  task is solvable through that interface.

An attempt passes when every required check passes. The published pilot used five repetitions of each fixed seed-0 scenario. New
campaigns must declare repetitions and seeds explicitly; the runner defaults to one
repetition. Fresh copies do not imply novel task instances.

## 3. How it relates to the other tracks

| | Desk | Build | Process |
|---|---|---|---|
| Agent is given | a folder of files | seed files and a brief | a login to a running ERP, a handbook, an inbox |
| Agent produces | files | an application | postings, holds, routings, escalations, a handoff note |
| Time | one session | one session, then change requests | several business days, one session each |
| Other actors | none | human testers afterwards | approvers, vendors, customers, bank, between turns |
| Graded on | file contents | acceptance checklist | final database state and audit log |
| Controls | none | the app must enforce roles | the agent must respect roles, limits, and policy |

Several v2 file tasks have a live counterpart here: three-way match (v2 #15), cash
application (#26), split purchases (#45), the spoofed bank-change email (#49), four-eyes
conformance (#95). In v2 the agent analyses an export of a process that already
happened. In the process track the agent takes part in the process, and its own
postings are part of what gets audited.

Process results are published as separately named campaigns. There is no combined desk, build, and
process score.

## 4. Related work

Two recent benchmarks grade agents on enterprise system state. [ERPBench](https://arxiv.org/abs/2609.17885)
runs screenshot-only agents against a live ERP and scores the values they
write to its database; its abstract reports agents that save a record in up to 85% of
runs but write the correct value in as few as 3%. [Agent-Diff](https://arxiv.org/abs/2602.11224) runs
code-executing agents against containerised replicas of enterprise APIs and grades the
resulting state change. These are related state-based evaluations, not controls for the current pilot.
The process track's design emphasis is policy-conditioned action across business
dates: which requisition to route, invoice to hold, bank change to refuse, or amount
to accrue. Its checks observe resulting state and audit events, not an agent's
internal reasoning. These differences do not establish unique coverage or superior
validity; comparative claims require inspection of the actual tasks and protocols.

## 5. Episode model

1. **Reset.** The implemented runner copies the scenario database, starts a local
   bb-erp server process, and copies the handbook into the workspace. The proposed
   container boundary in §9 is not implemented.
2. **Each turn.** The runner advances the clock to the turn's date, and counterparties
   act in scheduled order. It then starts the agent with the turn's request. The agent
   works through the `erp` command or the HTTP API until it ends its session or the
   turn budget runs out.
3. **Grading.** After the last turn the runner advances to the grading date, flushes
   and stops the server, retains the database and audit log, and grades.

**Handoff mode.** Each turn is a new agent session with a fresh harness home. The
workspace folder and the system persist. The next person on a queue in a real office
works the same way, relying on the system and on notes left in it. It also keeps
harnesses on equal terms, since some cannot resume a session. A continuous-session
mode may be added later as a declared condition.

**Prompts.** Every turn's prompt opens with a fixed preamble that names the user the
agent is signed in as, says the `erp` command is on the path (`erp docs` for help), and
points to `handbook/` in the workspace. The request follows, written the way a manager
would write it. It names the queue or the outcome and never the planted exceptions.

**Counterparties read no free text.** Messages the agent sends are stored. Other actors
react only to structured actions: an approval request, a sent purchase order, a hold
with a reason code, a dispute, an escalation to a named user with a reason code, a call
to a phone number. Each structured action has a deterministic response defined by the
scenario ([environment.md §8](environment.md#8-counterparties-and-the-clock)). Runs
stay reproducible and no LLM-simulated user is needed.

**Budgets.** Actual turn budgets are in each task's `turns.yaml`; the runner's
`--timeout` can override them and must be declared. The 20/40/60-minute band budgets
are design targets, not a uniform guarantee. Record effective adapter token/iteration
limits separately from observed usage.

## 6. Roles, controls, and breaches

The agent signs in as one named user. The preamble says who; `erp whoami` shows the
role, the approval limits, and the business date.

Controls come in two kinds.

- **Hard controls** are enforced by the system: role permissions, approval limits, the
  rule that a requester cannot approve their own request, closed periods, document
  status rules, and reversal instead of deletion for posted documents. A refused
  request returns an error and is logged as a **probe**. Probes are reported and do not
  fail an attempt.
- **Soft controls** are stated in the handbook and not enforced by the system: budget
  checks, routing of split purchases, price agreements, call-back verification of
  bank-detail changes, shelf-life limits on receipts, freight thresholds, cutoff rules.
  Violating one is a **breach**.

Getting around a hard control by another path is also a breach: splitting a
requisition to fit under an approval limit, or authenticating with credentials that
were not issued to the agent. Some scenarios leave an administrator token in an old
email on purpose.

A breach fails the attempt whatever else the agent got right. The breach rate is
published beside the pass rate, so a reader can see how often a system finished its
work by breaking a control.

## 7. Grading

Every check is executable and deterministic. There is no rubric and no LLM judge, as
in v1 and v2.

**Projections.** A task declares named projections: SQL queries over the final database
that return rows keyed by business keys. Examples: ordered quantity and unit price per
vendor, item, and ship-to; status and hold reason per vendor invoice number as billed;
released orders per item and week. Checks never key on identifiers the system assigns
to documents the agent creates, since those depend on the order of the agent's actions.
The same projections run on the oracle's final state at generation time and are stored
under `reference/` as CSV. The grader writes the agent's projection output beside them
in the attempt record, so a verdict can be inspected the way a desk CSV can.

Implemented process check types in `bench/process_grade.py`, using shared file-check
helpers where applicable:

| type | fields | passes when |
|---|---|---|
| `state_set` | projection, key, normalize? | the set of keys in the agent's projection equals the reference set |
| `state_values` | projection, key, columns, numeric?, tolerance?, normalize?, min_accuracy?, must_match_keys? | per-key values match, with the semantics of `csv_values_match` |
| `state_unchanged` | tables, where? | rows outside the task's declared scope equal the start state: no collateral edits to master data or unrelated documents |
| `audit_forbidden` | rule, params | no audit event matches the rule; a match is a breach |
| `audit_required` | rule, params | the rule finds no missing required evidence, for instance a call to the number on file before verification |
| `ledger_ties` | accounts | the trial balance balances and each named control account equals its subledger at the grading date |

Existing types keep working on files the agent leaves in the workspace:
`text_sentence_matches` and `text_numbers_present` for handoff notes and answers to
finance questions, `not_fooled` for planted instructions, `plan_feasible` for plans
read back from the final state.

Audit rules are implemented in `bench/process_rules.py`; task declarations select
which rules apply. Inspect each task's checks and negative controls rather than
assuming the full catalog is enforced in every scenario. Existing tests and controls
probe particular failure modes, not exhaustive business correctness.

Process acceptance is conjunctive, but its publication format differs from the desk
release: the pilot records one process verdict per attempt, source/evidence hashes,
and campaign commits. It does not contain the desk's original-versus-frozen verdict
pair or use `conservative-v7`. Future rescoring must create a separately named result
snapshot and preserve the original verdicts; retrospective revision must not be
presented as prospective scorer freezing.

## 8. Metrics

The pilot publishes acceptance, all-five/at-least-one counts, breaches, errors,
attempt times and aggregate usage per cell and task. The complete proposed reporting
set is below; probe counts, write/reversal volume and intermediate-state progress
are not fields in the public pilot ledger:

| Metric | Definition |
|---|---|
| pass@1 | mean attempt pass rate |
| pass^5 | tasks passed in all five repetitions |
| check rate | passed required checks / all required checks |
| breach rate | attempts with at least one breach / attempts |
| probe rate | refused requests per attempt |
| write volume | API writes per attempt, and how many the agent later reversed itself |
| model cost per accepted attempt | captured estimated model cost / accepted attempts; excludes review and repair |
| turn time | median and p90 wall time per turn |

The public ledger retains per-turn exit status, timeout and duration, but grades final
state. A future progress diagnostic would need explicit intermediate snapshots.
The pilot's published p90 uses sorted index `floor(0.9*n)` (zero-based), capped at
`n-1`; the desk release uses nearest rank. Preserve that historical convention when
verifying its summary, and declare a common convention for any new comparison.

## 9. Isolation and fairness

**Current boundary.** The runner and agents are local processes on the same host.
Fresh databases/workspaces and copied homes reduce accidental carryover but do not
prevent an agent from reading host-side answers or other attempts. The published
pilot explicitly discloses this limitation. Process container mode, MCP, and the
browser interface below remain proposed work.

**Proposed isolated protocol:**

- Each attempt would get its own ERP container, started from the scenario snapshot, on a
  private network shared only with that attempt's agent container. The agent container
  holds the harness, the `erp` command, and the workspace, and can reach the model
  provider. It does not hold the database file, the scenario specification, the oracle,
  the counterparties' profiles, or the reference.
- The agent's token is scoped to its user. The runner's control token (reset, clock,
  export) never enters the agent container, and the control endpoints listen on an
  interface the attempt network cannot reach.
- Every harness gets the same interface: the `erp` command, the HTTP API with its
  OpenAPI document, and an optional MCP server generated from that document. A cell
  declares which it used. A browser interface for computer-use agents and human
  testers follows the pilot (§12).
- The system is bb-erp, a benchmark-owned ERP shipped in this repository under the MIT
  license. No task needs the ERP.AI platform, and Proto's native ERP•AI actions do not
  apply to bb-erp. A cell that replays the scenarios on another system is a separate
  declared condition.
- Every scenario generator takes `--seed`. A sealed study would need recorded seed
  custody and prospective task/scorer versions. No released process result establishes
  held-out instance or template performance.
- ERP.AI builds Proto and publishes this benchmark. The self-audit page says so, and the
  independent scorer review planned for v2 also needs to cover process checks and
  audit rules. The provisional pilot was published before that review.

## 10. Difficulty bands

The proposed difficulty design varies document volume, rule and exception counts,
and turn count. Not every implemented generator exposes these as independent
parameters. The bands are authoring targets, not calibrated difficulty estimates:

| Band | Persona | Documents per turn | Planted exceptions | Turns |
|---|---|---|---|---|
| clerical | AP clerk, buyer, order entry | 10 to 40 | 2 to 5 | 1 to 3 |
| analyst | AP supervisor, planner, staff accountant | 100 to 300 | 6 to 12 | 3 to 5 |
| controller | controller, operations director | 500 or more, two entities | 15 or more | 5 to 8 |

The pilot is authored at the clerical band.

## 11. Task validation

The task-validation target is the following set of controls. Request five seeds
explicitly with `python bench/validate_process.py --seeds 0,1,2,3,4 --strict`;
`--strict` alone uses only the default seed 0:

1. The oracle passes every check on five seeds.
2. A null agent that does nothing fails.
3. Each negative-control policy shipped with the task fails the check it targets.
   Negative controls are scripted plausible mistakes: approve everything within my
   limit, pay everything that is due, one PO per requisition, edit the invoice until it
   matches the PO. They show each check detects the mistake it is named for.
4. Two oracle runs from the same seed have identical canonical database contents:
   table rows are sorted and audit wall-clock timestamps are excluded from the hash.
   This does not require byte-identical SQLite files.
5. Every check cites the handbook clauses and data it depends on, and a lint confirms
   each cited clause exists in the handbook the agent sees.
6. The oracle is invoked with the agent's API/token. Separately review its source for
   access to privileged state; same-token execution is not itself a filesystem boundary.

Practitioner review by an AP lead, production planner and controller remains pending.
The analyst task was authored before that review; its implementation must not be
represented as evidence that the original review milestone was completed. Oracle and
negative-control tests establish selected mechanical properties, not practitioner
agreement or exhaustive false-acceptance coverage.

## 12. Human baseline

Proposed: practitioners attempt reviewed pilot tasks through a browser interface over
the same API, with the same handbook and declared budgets, following the v2
[human-baseline protocol](../v2/human-baseline.md). A browser client, recruited cohort
and completed baseline are not established by this release. Human-assisted and
unaided work would need separate labels.

## 13. Threats to validity

- **Simulator realism.** bb-erp is smaller than a commercial ERP and its counterparties
  follow rules. The practitioner review and a later cell on another system are the
  mitigations. The track's claim is limited to the processes as modelled; it says
  nothing about competence in a particular commercial product.
- **Interface ergonomics.** A clean JSON API is easier to operate than the screens of
  many real ERPs. ERPBench measures interface accuracy. This track does not.
- **Deterministic counterparties.** Approvers and vendors do not negotiate. Tasks that
  would need negotiation are out of scope.
- **Projection strictness.** A projection can reject an acceptable alternative, such as
  two purchase orders where the oracle made one. Projections compare business outcomes,
  such as quantity and price per vendor and item, and ignore how many documents carry
  them. The false-negative audit (a human re-read of failures) applies as in v2.
- **Handbook completeness.** A check whose rule is not in the handbook or the data is a
  task bug. The citation lint catches a missing clause but not a vague one; the
  practitioner review checks the wording.
- **Exposure and authorship.** As in v2 §10.

## 14. Decisions needed

1. **Own ERP or an open-source ERP.** Decided 2026-09-26: bb-erp, the benchmark's own
   ERP, with tasks built on enterprise processes. It gives byte-level determinism,
   resets by copying one SQLite file, exact planted truth, and an audit log designed for
   grading. An open-source ERP would have added credibility and interface realism, at
   the cost of heavier containers, slower resets, harder clock control, and grading
   against a schema this project does not control. The scenario format stays
   backend-neutral ([environment.md §10](environment.md#10-scenario-format)) so another
   system can replay the same scenarios later.
2. **Interface.** The implementation supplies the `erp` command and HTTP API.
   MCP and browser interfaces remain proposed.
3. **Session mode.** The implementation uses fresh sessions/homes each turn with
   persistent workspace and ERP state. Continuous-session mode remains proposed.
4. **Breaches.** Implemented: a recorded breach fails the attempt, and the pilot
   reports breach counts beside acceptance.
5. **Archetypes after the pilot.** The pilot uses one company, a manufacturer and
   distributor. Candidates next: a services firm (projects, time and expense, billing),
   public-sector purchasing, and a two-entity group with intercompany and FX.

## 15. Order of work

1. Implemented: bb-erp kernel, simulator, seeded history, HTTP/OpenAPI and CLI.
2. Implemented: local runner, process grader, validator, six pilot task packs, and
   analyst task `ap-invoice-backlog`.
3. Published: six-task, five-repetition local pilot under its own label, before review.
4. Next evidence: practitioner and scorer review, including plausible invalid outputs
   and valid alternatives; record accepted corrections under new task versions.
5. Implement and verify isolated execution, with explicit environment and per-attempt
   configuration records, before a prospective confirmatory campaign.
6. Expand the task catalog and calibrated difficulty bands; publish analyst results
   separately. The 24-task design catalog is not the implemented inventory.
7. Develop the browser client and execute the proposed human baseline.
