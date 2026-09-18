# Status

Business Harness Bench: a runnable benchmark for agents doing business work.
Public site: https://businessbench.org. Repo: erphq/business-bench (public from v1.0.0).

## Current state (2026-09-17)

v1.0.0 is the first public release. It contains 187 desk tasks, 20 build task
packs, the runner and grader, and the recorded desk results of campaign
`full-1` (four complete arms, 2,244 attempts). Build scores are not published:
no arm has completed a human acceptance pass. The site under `site/` is built
from the repo itself (task export + ledger + SPEC.md) and deployed to
Cloudflare Workers.

## Recently shipped

- 2026-09-18: v1.0.0. Complete benchmark release with full-run snapshot and
  specification (initial commit).
- 2026-09-17: businessbench.org site (`site/`), MIT license, `Site` workflow,
  Epoch-style self-audit page listing every known gap.

## Next up

1. Fix the desk budget for flash-tier Proto cells (20% involuntary termination
   on Qwen) and rerun the three Proto arms as a new labeled campaign.
2. Independent stratified audit of 50 desk tasks (7 per category), verdicts
   committed under `docs/audits/`.
3. Human re-read of a sample of failed full-1 artifacts to estimate the
   false-negative rate of text checks (drafting, reports).
4. Proto on the ERP.AI platform cell (`harnesses/proto-erpai.sh`) and a matched
   same-model no-platform control, 5 repetitions each. Needs a Linux Docker host,
   a Proto runtime bundle, and an ERP.AI test org.
5. Per-attempt scorer digest and image digest recorded by the runner.
6. Cloudflare deploy secrets in the repo so the `Site` workflow deploys on push.
