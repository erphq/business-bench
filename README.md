# Business Bench

A benchmark of configured AI systems delivering business work. Desk and process tasks use generated inputs, planted truth, and executable acceptance checks; a passing attempt satisfies every required check. Build tasks require explicit application acceptance testing. These verdicts establish the declared contract, not every property a business user might need.

[businessbench.org](https://businessbench.org) · [paper](https://businessbench.org/paper) · [desk results](https://businessbench.org/results) · [findings](https://businessbench.org/analysis) · [process track](https://businessbench.org/process) · [self-audit](https://businessbench.org/audit)

**Three tracks**

- **Desk**, 187 tasks. The agent turns a folder of business files and a short request into deliverables, graded on identifier sets, keyed values, recalculated workbooks and sentence-level text rules. *Complete two-system comparison, 1,122 attempts, and a separate one-repetition three-system comparison, 561 attempts.*
- **Build**, 20 applications. The agent builds an internal application from a requirement and seed data, then makes three changes; a tester works a 14-item enterprise baseline and an application checklist. *Tasks released, no scores published.*
- **Process**, 7 implemented tasks: 6 clerical pilot tasks and the analyst task `ap-invoice-backlog`. The agent holds a role in bb-erp and works over several business dates; checks inspect ERP state, the audit log, control-account ties and requested notes. *A provisional campaign covers the six pilot tasks only; no published result covers the analyst task.*

**Desk comparison**, release `complete-desk-comparison-2026-09-16`, frozen `conservative-v7` scorer:

| System | Passed | Rate |
|---|---:|---:|
| Proto + DeepSeek V4.1 Flash | 507 / 561 | 90.4% |
| Codex + GPT-5.6-sol | 473 / 561 | 84.3% |

The paired task-bootstrap difference is +6.06 points (descriptive 95% interval +1.25 to +11.05). It resamples task identifiers with their three repetitions, and does not account for related families, scorer selection, or development exposure. The two systems differ in model, harness and run dates. ERP.AI publishes the benchmark and develops Proto; the [self-audit](https://businessbench.org/audit) discloses that conflict and retrospective scoring changes.

**Desk comparison, 28 September 2026**, label `complete-desk-comparison-2026-09-28`: every desk task once per system under the same frozen scorer. It is a separate campaign, not pooled with the release above.

| System | Passed | Rate |
|---|---:|---:|
| Proto + DeepSeek V4.1 Flash (DeepSeek API) | 171 / 187 | 91.4% |
| Proto + gpt-6-sol | 165 / 187 | 88.2% |
| Codex + gpt-6-sol | 162 / 187 | 86.6% |

Proto and Codex on gpt-6-sol shared the model, reasoning level (high), subscription account, host and time window. Their paired difference is +1.60 points (descriptive 95% interval −3.21 to +6.42), so this workload shows no clear difference in acceptance between them. It is one repetition on the same development-exposed tasks. [Conditions and data](results/desk/complete-desk-comparison-2026-09-28/).

**Process pilot campaign**, label `pilot-process-2026-09-27`: both harnesses on gpt-5.6-sol through a ChatGPT subscription, each of six fixed seed-0 scenarios run five times (60 attempts total).

| System | Passed | Median time per attempt | Input tokens (cached) |
|---|---:|---:|---:|
| Proto CLI 0.2.119 | 30 / 30 | 290 s | 38.8M (47%) |
| Codex CLI 0.158.0-alpha.2.1 | 30 / 30 | 164 s | 22.7M (89%) |

It ran in local mode, before practitioner review. Identical 30/30 acceptance does not establish equivalence, held-out generalization, or operational readiness; timing and token totals describe this pilot's conditions. [Conditions and data](https://businessbench.org/process#campaign).

This is the benchmark repository. It does not contain the Proto application, private runtime binaries, credentials or tuning experiments. Public templates are exposed. Re-rolling a generator seed tests a new instance of a known template; it does not by itself establish resistance to contamination or performance on unseen work.

## Repository layout

| Path | Contents |
|---|---|
| `tasks/desk`, `tasks/build`, `tasks/process` | Task generators, inputs, checks, handbooks and reference solutions |
| `erp/bberp` | bb-erp, the ERP the process track runs agents in |
| `bench/` | Runners, graders, validators and result exporters |
| `harnesses/` | One adapter script per evaluated cell, and the [adapter contract](harnesses/contract.md) |
| `scoring/frozen-v7` | The frozen desk scorer |
| `results/latest`, `results/desk`, `results/process` | Published result ledgers: the desk release, later desk campaigns and process campaigns |
| `site/` | businessbench.org, built from this repository |
| `docs/`, `paper/` | Paper sources, the v2 specification and the process-track specification |

For the shortest path from a claim to its evidence, see [reproducibility and evidence](docs/reproducibility.md). [STATUS.md](STATUS.md) separates published results, implemented components, and planned studies; [GOALS.md](GOALS.md) records the research priorities.

## Read the paper and specification

- [Paper](https://businessbench.org/paper) ([Markdown](SPEC.md), [PDF](docs/business-harness-bench-spec.pdf))
- [Desk results and limitations](results/latest/README.md): [summary](results/latest/summary.json), [attempt ledger](results/latest/attempts.jsonl), [provenance](results/latest/provenance.json)
- [Desk comparison, 28 September 2026](results/desk/complete-desk-comparison-2026-09-28/README.md): [summary](results/desk/complete-desk-comparison-2026-09-28/summary.json), [attempt ledger](results/desk/complete-desk-comparison-2026-09-28/attempts.jsonl), [provenance](results/desk/complete-desk-comparison-2026-09-28/provenance.json)
- [Process track specification](docs/process/README.md), [the ERP](docs/process/environment.md) and [the tasks](docs/process/tasks.md)
- [v2 specification](docs/v2/README.md)
- [Release verification and fixture notices](docs/validation.md)
- [Task format](docs/task-format.md), [desk authoring guide](docs/authoring-guide.md), [build authoring guide](docs/authoring-guide-build.md) and [enterprise baseline](docs/build-baseline.md)

## Requirements

Use Linux for official containerized runs and application hosting. Python **3.11 or 3.12**, Docker Engine, Bash, and Git are required. Node 22 and the Codex CLI are installed in the agent image. Host-side grading uses Python plus the LibreOffice recalculation image. Local-process mode is available for development but is **not a reference-answer isolation boundary**; do not use it for official model evaluations on a host with benchmark answers or unrelated secrets accessible to the agent.

Paid model runs require your own authorized model access. Codex requires a benchmark-owned login. Proto requires a separately obtained compiled CLI runtime and a benchmark-owned configuration. The benchmark contains the adapters, not third-party or private agent implementations. Models and CLI versions may cease to be available; changed configurations must be reported as a new cell, not claimed to reproduce the historical campaign.

## Install and verify without calling a model

```bash
git clone https://github.com/erphq/business-bench.git
cd business-bench
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python bench/export_campaign.py --verify
python bench/export_desk_campaign.py --verify
python bench/export_process_campaign.py --verify
python bench/validate_build.py
bash docker/build.sh
export BENCH_RECALC_DOCKER_IMAGE=bench-recalc:release
python bench/validate_tasks.py --strict
```

The unit tests include a real subprocess runner smoke test using a deterministic test adapter; they do not spend model credits. Full task validation checks generators and reference/empty outcomes. It can take several minutes with native workbook recalculation. Do not regenerate canonical inputs in place to make a validation failure disappear: investigate the failure and version any task changes explicitly.

## Run the desk track with Codex

Use a dedicated account/home with only the authorized tools and skills for this benchmark. Do not copy a personal home wholesale. Authenticate with the CLI's normal login flow in `homes/codex-sol` before running. On a host where Codex is installed:

```bash
mkdir -p homes/codex-sol
printf '[features]\napps = false\nplugins = false\n' > homes/codex-sol/config.toml
CODEX_HOME="$PWD/homes/codex-sol" codex login
export BENCH_RECALC_DOCKER_IMAGE=bench-recalc:release
python bench/run.py --docker business-bench:release \
  --harness codex-sol --tasks address-standardize \
  --runs 1 --parallel 1 --label codex-smoke
python bench/run.py --docker business-bench:release \
  --harness codex-sol --tasks all \
  --runs 3 --parallel 2 --label codex-full
python bench/report.py results/codex-full
```

Every invocation needs a fresh label. Existing desk labels and attempt directories are refused instead of overwritten. A task failure is a valid recorded outcome; missing attempt records cause the runner to return an error. The adapter defaults to `gpt-5.6-sol` with high reasoning effort, but `CODEX_MODEL` can override it; record the effective configuration. Plugin/skill manifests are operator-supplied: this release does not assert that a bare login reproduces the historical campaign's full skill environment. Desk and build Codex adapters reuse the configured home; unlike process turns, the runner does not create a fresh Codex home per attempt. See the [adapter contract](harnesses/contract.md) before interpreting repetition isolation.

## Optional Proto adapters

Supply `PROTO_RUNTIME` as an absolute directory containing `index.mjs` and all runtime assets needed by that build. The optional image builder copies it into a temporary build context and produces `business-bench:release-proto`; it never downloads or vendors Proto source into this repository. The temporary context path is printed for operator-managed disposal.

```bash
# Set PROTO_RUNTIME to your separately supplied runtime directory first.
bash docker/build.sh
# Supply OPENROUTER_API_KEY through your secret manager/environment first.
BENCH_HOME_NAME=proto-glm BENCH_GLM_MODEL=z-ai/glm-5.3-flash \
  python bench/setup_home.py
BENCH_HOME_NAME=proto-deepseek BENCH_GLM_MODEL=deepseek/deepseek-v4.1-flash \
  python bench/setup_home.py
BENCH_HOME_NAME=proto-qwen BENCH_GLM_MODEL=qwen/qwen3.8-flash \
  python bench/setup_home.py
export BENCH_RECALC_DOCKER_IMAGE=bench-recalc:release
python bench/run.py --docker business-bench:release-proto \
  --harness proto-glm --tasks all --runs 3 --parallel 5 --label glm-full
```

Use `proto-deepseek` and `proto-qwen` with distinct labels for the other API cells. Subscription-route and platform adapters are also supplied, but require their corresponding authenticated homes; `setup_home.py` configures **OpenRouter only**, not subscription login or ERP application access. Never commit the resulting `homes/` directories.

## Run the build track

Use a dedicated Linux evaluation host and non-production data. Build runs use host networking; allocate a free port, arrange the intended external reachability, and do not expose an unreviewed generated app on a production host. Platform-backed runs need a dedicated test organization and appropriately scoped access.

```bash
python bench/build_run.py --task hvac-field-service \
  --harness codex-sol --docker business-bench:release \
  --label hvac-codex-1 --port 8100 --changes 3 --timeout 3600
python bench/build_grade.py \
  results/hvac-codex-1/hvac-field-service__codex-sol__t0 \
  --serve --docker business-bench:release --probe
```

Grade each turn, complete its tester sheet, and recheck previous requirements after every change. `--serve` executes the generated start command inside the specified container; inspect untrusted artifacts and use an isolated host. A responding URL or generated sheet is not a completed acceptance test. Report the initial checklist, new requirements, regressions, external reachability, and costs separately. Tester sheets contain generated app logins and must remain private.

## Run the process track

Process tasks run an agent inside bb-erp over several turns on a business clock. `process_run.py` starts one bb-erp server per attempt, calls the harness adapter once per turn with `ERP_URL`, `ERP_TOKEN` and the `erp` command on `PATH`, lets the counterparty simulator act between turns, and grades the final database and audit log. It runs bb-erp and the agent as local processes, which is not an isolation boundary; container mode is on the roadmap.

```bash
python bench/validate_process.py --seeds 0,1,2,3,4 --strict
python bench/process_run.py --task procure-to-pay-week --harness oracle --label dev-oracle
# Paid run over all 7 currently implemented tasks; this is not the six-task historical pilot.
python bench/process_run.py --task all --harness codex-sol --runs 5 --parallel 2 --label my-campaign
```

`validate_process.py` checks, for each requested task and seed, that the oracle passes, an agent that does nothing fails, each negative control fails the checks it targets, two runs end in the same database, and every cited handbook clause exists. Its default is seed 0; the five seeds above are explicit. Real agents use the desk adapters (`harnesses/<cell>.sh`); set `CODEX_BIN` or `BENCH_PROTO_CLI` as the adapter describes. Use a separate checkout for validation or scenario regeneration while a campaign is active, because scenarios are cached in `.cache/process/`.

Before a paid campaign, declare its exact task list, seed, repetitions and cells. Before publication, create `results/<label>/campaign.json` with that declaration and the actual conditions, then run `python bench/export_process_campaign.py --label <label>`. The [export checklist and description schema](docs/reproducibility.md#publishing-a-new-process-campaign) explain the required record. Export is a publication step, not part of running an agent.

## Results and reproducibility

`results/latest/` holds the desk release, `results/desk/` later desk campaigns and `results/process/` the published process campaigns; other runs stay ignored. Recompute them with `python bench/export_campaign.py --verify`, `python bench/export_desk_campaign.py --verify` and `python bench/export_process_campaign.py --verify`; these check the complete matrix and the arithmetic, **not the original artifacts' correctness**. The release ledger keeps per-check verdicts, original result hashes, resource records, and execution status, without private paths or logs.

The release includes the exact [frozen scorer](scoring/frozen-v7/scorer.py) and its fingerprinted task definitions. Run `python scoring/frozen-v7/scorer.py TASK_ID WORKSPACE` with native recalculation configured to score an output workspace. The standard runner's original-grade field and this frozen verdict are distinct; retain both. The verifier checks the full frozen package fingerprint as well as result arithmetic. The original result and receipt hashes were checked against the server records for every exported attempt.

For a new official campaign, freeze the repository commit, task manifest, agent image digest, model/provider route, authorized skill inventory, budgets, dependency versions, and scorer before launch. Retain raw artifacts securely so a later scorer can produce a separately named scoring snapshot. Do not mix rescored subsets into the published aggregate. This completed comparison uses different model/harness configurations and non-contemporaneous cohorts; see provenance for the exact scope.

The optional `bench/audit.py` can prepare a reviewer bundle with `--dry-run`; without that option it sends task and run content to the configured model provider. Use only synthetic/authorized data. This model-assisted review is not independent practitioner adjudication and never changes the primary acceptance definition. `regrade.py` and `recost.py` can change local run records; use them only on a copy, never on a released snapshot. Desk/build raw attempt directories can retain authenticated homes, and all raw workspaces and traces require review before sharing; public exporters publish allowlisted records rather than those directories.

## Rebuild the PDF

```bash
python docs/build_latex.py
```

The paper is compiled with **XeLaTeX**, using native booktabs tables, PGFPlots figures, numbered equations, linked cross-references, and a BibTeX bibliography. See [paper/README.md](paper/README.md) for the TeX/Pandoc prerequisites and the direct `.tex` build. The shared manuscript and complete generated TeX sources are tracked. The paper embeds the bundled SIL Open Font License Libertinus Serif fonts; attribution and license are in `docs/assets/fonts/`. Generated previews and build intermediates remain ignored.

## Site

The public site under `site/` is generated from this repository: task metadata via `python3 site/scripts/export_tasks.py`, results from `results/latest/`, `results/desk/` and `results/process/`, the process-track pages from `tasks/process/` and `docs/process/`, and the paper from `SPEC.md`. Build with `cd site && bun install && bun run build`; deploy with `bunx wrangler deploy` (Cloudflare account access required). The `Site` workflow checks the export is fresh, runs the site tests, and builds on every push.
