# Status

Business Bench: a runnable benchmark for agents doing business work.
Public site: https://businessbench.org. Repo: erphq/business-bench (public from v1.0.0).

## Current state (2026-09-17)

v1.0.0 is the first public release. It contains 187 desk tasks, 20 build task
packs, the runner and grader, the frozen `conservative-v7` scorer, and the
complete desk comparison `complete-desk-comparison-2026-09-16`: Proto + DeepSeek
V4.1 Flash 507/561 (raw 447) versus Codex + GPT-5.6-sol 473/561 (raw 431),
1,122 attempts, raw and frozen verdicts both in the ledger. Build scores are not
published: no arm has completed a human acceptance pass.

An earlier snapshot (commit 87f624e, campaign `full-1`) recorded four arms under
the original grader with Codex ahead of three flash-tier Proto cells. It is in
git history and the site's self-audit names it; the two snapshots are not on one
leaderboard.

The site under `site/` is built from the repo itself (task export + ledger +
frozen scorer + SPEC.md) and deployed to Cloudflare Workers.

## Recently shipped

- 2026-09-27: process track pilot campaign `pilot-process-2026-09-27`. Proto CLI
  0.2.119 and Codex CLI 0.158.0-alpha.2.1, both on gpt-5.6-sol through a ChatGPT
  subscription, each ran the six pilot tasks five times from seed 0. Both passed
  30/30 with no breaches. Median time per attempt: Proto 290 s, Codex 164 s.
  Input tokens: Proto 38.8M (47% cached), Codex 22.7M (89% cached). Local mode,
  before the practitioner review; published as provisional with its ledger in
  `results/process/`, verified in CI by `export_process_campaign.py --verify`.

- 2026-09-26: process track pilot. bb-erp (the benchmark's own ERP: purchasing,
  receiving, payables, ledger, sales, manufacturing, MRP; hard controls; audit
  log; business clock; counterparty simulator), a runner that drives agents
  turn by turn through harness adapters, six check types plus audit rules, and
  six validated pilot tasks with oracles and negative controls. Smoke attempts
  by Proto and Codex CLI (both gpt-5.6-sol) found three task defects, all fixed;
  no process scores are published. Site redesigned (serif text, figures with
  task-bootstrap intervals, process track pages, sitemap with lastmod, new
  share image).

- 2026-09-18: v1.1.0. Grader gains the three v2 check types (`plan_feasible`,
  `forecast_error`, `not_fooled`) with strict-validator rules and tests; generator
  library gains the event-log emitter with planted deviations, the planning
  constraint scaffold, and the adversarial injector; paper retitled Business Bench
  with authors Somesh Misra, Somnath Misra, Shashank Dixit; Findings page live.

- 2026-09-18: v2 direction agreed and published: thesis for an AI-research
  audience, seven capability axes, 100 tasks with planted truth and check type
  (`docs/v2/`), human-baseline protocol with approved budget, /roadmap page.

- 2026-09-18: v1.0.0 initial commit (full-1 snapshot), then the corrected
  two-system frozen-scorer comparison and redesigned paper (collaborator).
- 2026-09-17: businessbench.org site (`site/`), MIT license, `Site` workflow,
  self-audit page that states the conflict of interest, the scorer's effect on
  every verdict, and the earlier snapshot up front.

## Next up

0. v2 order of work (docs/v2/README.md section 11): steps 1 and 2 done in v1.1.0;
   next is authoring axes 4, 6, 7 (42 tasks, three bands each) on the new library.
1. Independent stratified audit of 50 desk tasks (7 per category) by reviewers
   outside ERP.AI, verdicts committed under `docs/audits/`.
2. Independent review of the 7 equivalence graders against adversarial wrong
   answers; plausible-wrong negative controls per check type.
3. Human re-read of a sample of remaining failures to estimate the residual
   false-negative rate.
4. Contemporaneous rerun: same task version, same scorer, 5 repetitions per
   system, plus a same-model harness control pair. Proto on the ERP.AI platform
   cell (`harnesses/proto-erpai.sh`) runs in the same campaign. Needs a Linux
   Docker host, a Proto runtime bundle, and an ERP.AI test org.
5. Container digests and runtime revision recorded per attempt by the runner.
6. Cloudflare deploy secrets in the repo so the `Site` workflow deploys on push.
