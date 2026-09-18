# Status

Business Harness Bench: a runnable benchmark for agents doing business work.
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

- 2026-09-18: v2 direction agreed and published: thesis for an AI-research
  audience, seven capability axes, 100 tasks with planted truth and check type
  (`docs/v2/`), human-baseline protocol with approved budget, /roadmap page.

- 2026-09-18: v1.0.0 initial commit (full-1 snapshot), then the corrected
  two-system frozen-scorer comparison and redesigned paper (collaborator).
- 2026-09-17: businessbench.org site (`site/`), MIT license, `Site` workflow,
  self-audit page that states the conflict of interest, the scorer's effect on
  every verdict, and the earlier snapshot up front.

## Next up

0. v2 order of work (docs/v2/README.md section 9): three new check types in
   grade.py, generator library additions (event logs, constraint checker,
   adversarial injector), then author axes 4, 6, 7 first.
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
