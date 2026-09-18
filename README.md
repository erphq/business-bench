# Business Bench

**Does the agent deliver business work that an owner can actually use?**

Site: [businessbench.org](https://businessbench.org) (results, task pages, methods, paper, self-audit). License: MIT.

Business Bench tests the handoff, not the agent's confidence: reconciled files, correct imports, source-grounded reports, and applications whose behavior holds up under use and subsequent changes.

- **Desk:** 187 tasks across seven categories, each with inputs, an ask, checks, a generator, and a reference solution.
- **Build:** 20 business applications, each with seed data, an acceptance checklist, and three change requests.
- **Latest complete comparison:** **Proto + DeepSeek V4.1 Flash: 507/561 (90.4%)**, versus **Codex + GPT-5.6-sol: 473/561 (84.3%)**. All 187 tasks × 3 repetitions × 2 systems = **1,122 attempts**, evaluated by the same frozen conservative-v7 scorer. Every pass and failure is retained. No incomplete build scores are published.

This is the benchmark repository. It does not contain the Proto application, private runtime binaries, credentials, tuning experiments, or a development diary. The repository is public; its task set is therefore exposed, not an independent sealed holdout. Each generator takes a `--seed` for re-rolled private variants.

## Read the paper and specification

- [Research paper](SPEC.md)
- [Complete specification](SPEC.md)
- [Specification PDF](docs/business-harness-bench-spec.pdf)
- [Latest full-arm results and limitations](results/latest/README.md)
- [Machine-readable summary](results/latest/summary.json) and [sanitized attempt ledger](results/latest/attempts.jsonl)
- [Provenance](results/latest/provenance.json)
- [Release verification and fixture notices](docs/validation.md)
- [Task format](docs/task-format.md), [desk authoring guide](docs/authoring-guide.md), [build authoring guide](docs/authoring-guide-build.md), and [enterprise baseline](docs/build-baseline.md)

## Requirements

Use Linux for official containerized runs and application hosting. Python **3.11 or 3.12**, Docker Engine, Bash, and Git are required. Node 22 and the Codex CLI are installed in the agent image. Host-side grading uses Python plus the LibreOffice recalculation image. Local-process mode is available for development but is **not a reference-answer isolation boundary**; do not use it for official model evaluations on a host with benchmark answers or unrelated secrets accessible to the agent.

Paid model runs require your own authorized model access. Codex requires a benchmark-owned login. Proto requires a separately obtained compiled CLI runtime and a benchmark-owned configuration. The benchmark contains the adapters, not third-party or private agent implementations. Models and CLI versions may cease to be available; changed configurations must be reported as a new cell, not claimed to reproduce the historical campaign.

## Install and verify without calling a model

```bash
git clone git@github.com:erphq/business-bench.git
cd business-bench
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python bench/export_campaign.py --verify
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

Every invocation needs a fresh label. Existing desk labels and attempt directories are refused instead of overwritten. A task failure is a valid recorded outcome; missing attempt records cause the runner to return an error. The adapter selects the recorded model identifier `gpt-5.6-sol` with high reasoning effort. Adjust an adapter only in an explicitly documented new configuration. Plugin/skill manifests are operator-supplied: this release does not assert that a bare login reproduces the historical campaign's full skill environment.

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

## Results and reproducibility

`results/latest/` is the only result release tracked here. New runs stay ignored. Recompute its summary with `python bench/export_campaign.py --verify`; this checks the complete matrix and arithmetic, **not the original artifacts' correctness**. The release ledger keeps per-check verdicts, original result hashes, resource records, and execution status, without private paths or logs.

The release includes the exact [frozen scorer](scoring/frozen-v7/scorer.py) and its fingerprinted task definitions. Run `python scoring/frozen-v7/scorer.py TASK_ID WORKSPACE` with native recalculation configured to score an output workspace. The standard runner's original-grade field and this frozen verdict are distinct; retain both. The verifier checks the full frozen package fingerprint as well as result arithmetic. The original result and receipt hashes were checked against the server records for every exported attempt.

For a new official campaign, freeze the repository commit, task manifest, agent image digest, model/provider route, authorized skill inventory, budgets, dependency versions, and scorer before launch. Retain raw artifacts securely so a later scorer can produce a separately named scoring snapshot. Do not mix rescored subsets into the published aggregate. This completed comparison uses different model/harness configurations and non-contemporaneous cohorts; see provenance for the exact scope.

The optional `bench/audit.py` can prepare a reviewer bundle with `--dry-run`; without that option it sends task and run content to the configured model provider. Use only synthetic/authorized data. The reviewer supplements deterministic checks and cannot turn an incomplete evaluation into a certified result. `regrade.py` and `recost.py` are operator utilities that can change local run records; use them only on a copy, never on the released snapshot.

## Rebuild the PDF

```bash
python docs/build_latex.py
```

The paper is compiled with **XeLaTeX**, using native booktabs tables, PGFPlots figures, numbered equations, linked cross-references, and a BibTeX bibliography. See [paper/README.md](paper/README.md) for the TeX/Pandoc prerequisites and the direct `.tex` build. The shared manuscript and complete generated TeX sources are tracked. The paper embeds the bundled SIL Open Font License Libertinus Serif fonts; attribution and license are in `docs/assets/fonts/`. Generated previews and build intermediates remain ignored.

## Site

The public site under `site/` is generated from this repository: task metadata via `python3 site/scripts/export_tasks.py`, results from `results/latest/`, and the paper from `SPEC.md`. Build with `cd site && bun install && bun run build`; deploy with `bunx wrangler deploy` (Cloudflare account access required). The `Site` workflow checks the export is fresh, runs the site tests, and builds on every push.
