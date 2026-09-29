# Status

Repository evidence snapshot: 2026-09-28. Public site: [businessbench.org](https://businessbench.org).
Implemented means source is present; published means a named result ledger is released.
Neither label establishes independent review or deployment readiness.

## Published evidence

| Track | Implemented inventory | Published evaluation | Boundary |
|---|---|---|---|
| Desk | 187 tasks | `complete-desk-comparison-2026-09-16`: 561 attempts per system; Proto + DeepSeek V4.1 Flash 507 accepted, Codex + GPT-5.6-sol 473. `complete-desk-comparison-2026-09-28`: 187 attempts per system, one repetition; Proto + DeepSeek V4.1 Flash 171, Proto + gpt-6-sol 165, Codex + gpt-6-sol 162 | Development-exposed fixtures and a retrospective common scorer. The release compares different models and non-contemporaneous cohorts; the later campaign matches model, account and window for the gpt-6-sol pair but has one repetition |
| Build | 20 task packs, each with three changes | No completed acceptance-validated campaign | Packs and probes are available; application correctness has not been established by a published build evaluation |
| Process | Six clerical pilot tasks plus analyst task `ap-invoice-backlog` | `pilot-process-2026-09-27`: the six pilot tasks at seed 0, five repetitions per system; both systems 30/30, zero recorded breaches | Local mode, no practitioner review, no published analyst-task result |

The desk ledger retains original and frozen verdicts: 447 versus 431 original passes,
507 versus 473 under `conservative-v7`. The research paper separates complete
acceptance, partial-check fractions, repeated success, workload composition, evaluator
sensitivity, and resource use. [Evidence map and verification commands](docs/reproducibility.md).

The 28 September desk campaign ran Proto and Codex on gpt-6-sol at high reasoning in the
same window, on the same subscription account and host. Proto passed 165 and Codex 162
of 187 tasks: a paired difference of +1.60 points with a descriptive interval of −3.21
to +6.42. A third cell, Proto on DeepSeek V4.1 Flash through DeepSeek's own API, passed
171. It is not pooled with the release. Its ledger and conditions are in
[`results/desk/complete-desk-comparison-2026-09-28/`](results/desk/complete-desk-comparison-2026-09-28/).

The process pilot names Proto CLI 0.2.119 and Codex CLI 0.158.0-alpha.2.1, both using
gpt-5.6-sol through a ChatGPT subscription. Its median attempt times are 290 s and
164 s; these are observations from the released local pilot, not isolated estimates
of harness efficiency. Its ledger and exact conditions are in
[`results/process/pilot-process-2026-09-27/`](results/process/pilot-process-2026-09-27/).

An earlier four-arm `full-1` snapshot exists in Git history. Its original-grader
results are not pooled with the current frozen-scorer comparison.

## Implemented without a new score claim

- bb-erp, process runner, state/audit checks, oracle and negative-control validation.
  The runner starts local processes; process container isolation is still planned.
- `ap-invoice-backlog`, the first analyst-band process task, with 16 negative controls.
  Its source and validation are distinct from a completed agent campaign.
- `plan_feasible`, `forecast_error`, and `not_fooled`, plus planning, event-log and
  adversarial generator helpers. These are infrastructure for the [v2 design](docs/v2/README.md),
  not a released 100-task v2 suite or a human baseline.
- The wiki site, shared paper manuscript, generated Markdown/TeX, and published PDF.
  CI builds the site and paper; a successful build alone is not a live deployment check.
- Measurement science and grader integrity ([docs/measurement-science.md](docs/measurement-science.md)):
  - trap switches and per-trap mutants on 71 desk generators, and difficulty settings on 10 saturated tasks;
  - measurement graph, difficulty model, delegation-envelope and renewable-benchmark tooling, and a failure-triage queue;
  - metamorphic tests and a scorer-change gate;
  - bb-erp property, crash and replay tests, and fault injection;
  - two new process tasks, belief revision and need-to-know;
  - policy registries that regenerate every process handbook.

  With no flags, generators, runner and grader behave as before. The first agent runs and the pre-registered trap
  forecast recorded there are development observations, not a published campaign.

## Next evidence to obtain

1. Independently review accepted and rejected artifacts, including plausible wrong
   outputs and valid alternatives. Publish sampling rules and adjudications, with
   false-acceptance and false-rejection estimates under that sampling design.
2. Review the process handbooks and exceptions with practitioners. Expand beyond the
   saturated six-task local pilot only with reviewed contracts and documented isolation.
3. Freeze scorer, fixtures, environments and configurations before a new campaign.
   Separate fixed-fixture repetition, new seeded instances and held-out templates;
   control model and environment when claiming a harness comparison.
4. Execute the proposed human baseline and a complete build acceptance campaign.
   Protocols and budget estimates exist; participant recruitment, completed attempts,
   and independent verdict records are not established by this repository.
5. Record effective runtime/image/dependency and skill configuration per attempt.
   The adapters accept environment overrides, and current homes differ across tracks.

The planned sequence and non-goals are in [GOALS.md](GOALS.md). Historical design
documents describe intended extensions; their status notes distinguish those plans
from the inventory and campaigns above.
