# Business Harness Bench: Measuring Reliable Completion of Business Work

## Abstract

The relevant output of a business agent is not its explanation of the work, but the work it leaves behind. A reconciliation must account for the right transactions, an import must preserve the destination's contract, and an application must enforce its permissions when someone actually uses it. Business Harness Bench evaluates this handoff through two complementary tracks: 187 desk tasks that transform folders of business files into checkable deliverables, and 20 application-building tasks that require a working application followed by three change requests. Desk tasks combine explicit business rules, heterogeneous inputs, deterministic checks, and reference solutions. Build tasks combine seed-data requirements with an enterprise acceptance baseline covering access control, sharing, live data, auditability, and persistence. The unit of comparison is the configured agent system: harness, model, tools, and execution substrate. Repeated attempts distinguish occasional success from repeatable completion; time, recorded usage, and estimated model cost describe the resources required. This release includes the four complete desk arms of the latest full benchmark campaign, totaling 2,244 attempts, and does not present incomplete application evaluations as a build leaderboard. The benchmark is a controlled test of specified business-work contracts, not a claim to represent all business activity or to establish unattended production readiness.

## 1. The problem: completion is a contract, not a conversation

A small business does not delegate a reconciliation to obtain a convincing description of reconciliation. It delegates the work because a payment decision, a report, or the next import depends on the result. The handoff is therefore the right place to evaluate an agent. Can the owner open the files, trust the specified calculations, identify what remains unresolved, and continue the business process without repairing the deliverable?

The distinction matters because business correctness is often conjunctive. A workbook can contain the right total while using broken formulas. An import can be well-formed while silently dropping customers. A payment can match an amount while belonging to a different invoice. A summary can sound polished while recommending an option contradicted by its sources. In an application, a hidden button is not an authorization boundary, and a successful demonstration is not evidence that records survive a restart. These are not cosmetic shortcomings around an otherwise correct answer. They break the contract under which the work was delegated.

Business Harness Bench makes that contract explicit and executable where possible. The central question is: **under a stated operating environment and resource budget, how reliably does a configured agent system deliver business work that satisfies the owner's requirements?** Success is attached to the resulting artifacts and observable behavior, not to confidence, verbosity, a self-reported completion message, or the number of actions performed.

## 2. Two handoffs, one evaluation principle

The desk track starts with a folder and a short request. The agent receives business-shaped exports, spreadsheets, documents, and contextual instructions, then leaves the requested deliverables. Tasks test not only transformation mechanics but the application of supplied rules: which record is authoritative, how an exception should be treated, what must remain unchanged, and when the evidence is insufficient to support a conclusion. Inputs are generated fixtures, not a claim that the suite consists of privately collected customer engagements. The tasks use ordinary formats so the tested capability is producing the deliverable, rather than access to a proprietary input representation.

The build track starts with a business requirement and seed data. The agent must hand over an application that a tester can reach and operate, then accommodate three changes without discarding earlier requirements. The initial build tests delivery; the subsequent turns test continuity. A system that can produce a plausible first screen but cannot preserve access restrictions or existing records across a change has not completed the same business job as a system that can. Automated probes support this evaluation, but they do not substitute for the unautomated acceptance checklist.

The tracks are reported separately. They share a completion principle, not a common denominator: passing a file check is not interchangeable with enforcing an application's role boundary. Combining them into one headline score would obscure what was actually tested.

## 3. Evaluate the system that does the work

A model does not act alone. Its harness determines how it receives instructions, reads files, invokes tools, manages context, recovers from errors, and delivers artifacts. Available skills, document utilities, model routing, and an application platform can change both the feasible solution and its cost. The benchmark therefore identifies each experimental cell by its harness, model configuration, tools, and substrate.

An end-to-end comparison answers a buyer's question: which configured system completed this workload under these conditions? It does not, by itself, isolate the causal contribution of the harness or establish that one underlying model is better. Those questions require matched controls, including the same model and substrate where possible. Likewise, access to a business-app platform is a declared experimental condition, not an invisible advantage. A useful result describes the system that ran, including material configuration gaps, rather than attributing every difference to one component.

## 4. Reliability and resources belong beside accuracy

A single successful attempt establishes possibility, not repeatability. The desk protocol uses three attempts per task and reports both attempt-level pass rate and the fraction of tasks that pass all three attempts. The former describes performance across the executed matrix; the latter identifies work completed consistently within those repetitions. Neither estimates long-term reliability with high precision from only three observations per task.

Every included full arm retains failures as well as successes. Execution errors, timeouts, missing usage, and grader errors remain visible instead of being silently removed from the denominator. Artifact checks and normal process completion are distinct observations: an agent may leave a passing file before timing out, or exit normally without delivering correct work. Reporting both prevents a convenient process status from standing in for the business outcome.

Time and estimated cost further qualify the result. A correct deliverable that requires substantially more time or expenditure represents a different operating point. Recorded token counts and the bundled price table support a transparent estimate; they are not an invoice and do not account for every infrastructure, subscription, or human-review cost. The benchmark's purpose is to expose these tradeoffs, not to collapse them into an unexplained composite score.

## 5. The evaluator must also earn trust

A deterministic grader is repeatable, but not automatically correct. A check can reject a valid alternative, accept a superficial match, or rely on a stale spreadsheet cache. The task package therefore includes explicit checks and reference solutions, and its validation tools test regeneration and basic positive and negative cases. Native spreadsheet recalculation is important when the contract requires live formulas. These mechanisms make the scoring inspectable; they do not establish exhaustive semantic coverage.

The scope of the claim must stay aligned with the evidence. Mechanical authoring checks are not independent practitioner review. A public generated suite is not an unseen holdout. Benchmark-specific development creates exposure that must be disclosed rather than relabeled as generalization. Recorded campaign scores without a per-attempt scorer digest are a historical scoring snapshot, not proof that every artifact was evaluated by an identical immutable scorer. Missing build acceptance work is missing evidence, not a zero that can be filled by an optimistic narrative.

This is the benchmark's intended contribution: a runnable, inspectable way to evaluate whether agents satisfy concrete business-work contracts, with enough separation between task validity, execution, grading, and reporting to make disagreements diagnosable. The release is not an account of one product's tuning history, and its premise does not depend on which system ranks first.

## 6. Positioning and boundaries

Business Harness Bench sits alongside existing approaches to evaluating work. WorkArena evaluates agents performing knowledge-work tasks in enterprise software. SpreadsheetBench evaluates spreadsheet manipulation grounded in real-world scenarios. TheAgentCompany evaluates professional tasks in a simulated workplace. These works establish relevant neighboring settings; this paper does not claim that business work or artifact-based evaluation is new. The particular emphasis here is the combination of portable file-delivery contracts and application handoff with subsequent changes, reported at the configured-system level.

The present suite contains authored business-shaped tasks, not a representative sample of the economy. Task families may share generators and failure modes; three attempts per task are not independent samples of business demand. Document checks do not establish editorial quality in every respect, and file tasks do not exercise live SaaS state, organizational coordination, or every security property. Platform-backed builds require appropriately scoped external access. Results should guide investigation and comparison within this defined workload, not be presented as a guarantee of safe autonomous deployment.

## References

1. WorkArena: How Capable Are Web Agents at Solving Common Knowledge Work Tasks? https://arxiv.org/abs/2403.07718
2. SpreadsheetBench: Towards Challenging Real World Spreadsheet Manipulation. https://arxiv.org/abs/2406.14991
3. TheAgentCompany: Benchmarking LLM Agents on Consequential Real World Tasks. https://arxiv.org/abs/2412.14161
