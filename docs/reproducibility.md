# Reproducibility and evidence

Use the named campaign and its declared workload as the unit of comparison. Task
inventory, a proposed catalog, an executed campaign and independently reviewed
acceptance are different evidence states. Current scope is in [STATUS.md](../STATUS.md).

## From a claim to its record

| Claim | Public evidence | What the public check establishes |
|---|---|---|
| Desk 507/561 versus 473/561 | [`results/latest/`](../results/latest/) ledger, summary and provenance | Complete declared matrix, aggregate arithmetic and frozen-scorer file identity |
| Desk check-level/repetition analysis | Per-check frozen verdicts in `attempts.jsonl`; `docs/paper_details.py` | Recalculated diagnostics, not independent judgments of the private artifacts |
| Process pilot 30/30 per system | [`pilot-process-2026-09-27`](../results/process/pilot-process-2026-09-27/) | Six tasks × two cells × five repetitions, all seed 0; local-mode conditions |
| Seven process task packs | `tasks/process/*/task.yaml` | Implemented inventory; the seventh task has no published campaign result |
| Twenty build packs | `tasks/build/`, `bench/validate_build.py` | Pack structure and seed/reference consistency, not application acceptance |
| Public paper | `paper/benchmark.md`, generated TeX/Markdown and PDF build receipt | Source/artifact identity and successful compilation; business validity remains separate |
| v2 and human baseline | `docs/v2/` | Proposed protocol, catalog and budget estimate; no completed study |

Public hashes identify private artifacts but cannot reconstruct them. Full independent
re-adjudication would require access to those artifacts and the relevant historical
environment. A new run with changed tools, route, model or runtime is a new cell.

## Verify the published records without a model

From the repository root, after installing `requirements.txt`:

```bash
python bench/export_campaign.py --verify
python bench/export_process_campaign.py --verify
python bench/release_manifest.py
python docs/paper_artifact.py --verify
python -m unittest discover -s tests -v
```

The test suite runs deterministic test adapters and process oracles; it makes no paid
agent calls. It is broader than ledger verification and can take several minutes.
Use a separate checkout when another campaign is active: process scenarios are cached
under `.cache/process/`, and validation must not regenerate a live campaign's inputs.

The public desk verifier checks the current ledger/scorer files. Verification of
private original-result bytes and receipt identity occurred during export; a public
checkout cannot repeat that private-artifact step. Process verification checks the
declared task/cell/seed/repetition matrix, hash and summary, not original database
contents. [Historical validation and fixture notices](validation.md) remain separate.

## Record a new experiment before running it

Retain a manifest with task identifiers and fixture hashes; fixed seed/instance or
held-out template status; scorer code and thresholds; repetitions; effective model,
provider, runtime, image/dependency and tool/skill configuration; resource budgets;
home/session policy; concurrency and machine details; and the analysis plan. Declare
which factors vary if comparing systems. Keep raw artifacts, execution outcomes and
missing usage instead of selecting only accepted attempts.

Use fresh labels. Do not edit tasks, scenario caches or graders during a campaign.
Desk `bench/run.py` scores with the current `bench/grade.py`; it does not automatically
produce `conservative-v7` receipts. The historical desk exporter imports a particular
retained campaign and is not a general one-command exporter for arbitrary new desk
runs. Preserve original results and publish any retrospective scoring as a distinct
named snapshot, never as a silently updated subset.

## Publishing a new process campaign

The process runner's `--task all` currently selects seven tasks, while the historical
pilot selected six. Freeze the intended list explicitly. The exporter reads
`results/<label>/campaign.json`; a minimal one-task declaration has this shape:

```json
{
  "campaign": "my-process-study",
  "track": "process",
  "tasks": ["procure-to-pay-week"],
  "seed": 0,
  "repetitions": 5,
  "bench_commit_at_run": "REPLACE_WITH_ACTUAL_COMMIT",
  "cells": {
    "codex-sol": {
      "system": "REPLACE_WITH_ACTUAL_SYSTEM",
      "harness": "REPLACE_WITH_CLI_VERSION",
      "model": "REPLACE_WITH_EFFECTIVE_MODEL",
      "route": "REPLACE_WITH_ACTUAL_ROUTE",
      "effort": "REPLACE_WITH_EFFECTIVE_EFFORT"
    }
  },
  "conditions": ["REPLACE_WITH_ACTUAL_ISOLATION_HOME_BUDGET_AND_CONCURRENCY_CONDITIONS"]
}
```

Replace all placeholders and match the label, task set, seed and repetition count to
the declared run. This is a schema example, not historical provenance. After checking
raw attempts and publication scope, run:

```bash
python bench/export_process_campaign.py --label my-process-study
python bench/export_process_campaign.py --verify
```

The exporter rejects duplicate, missing or unexpected task/cell/repetition entries and
seed mismatches. It cannot infer tasks omitted from the declaration; that is why the
list must be fixed before execution. The export-time task-tree hash is not a substitute
for the actual run commit, fixture hashes or a prospectively frozen scorer.

Raw workspaces, databases, homes and traces remain private. Review what is published;
the exporter emits selected fields and hashes, not a raw artifact bundle. File hashes
do not prove that a run obeyed its declared isolation or configuration.

## Metric conventions to retain

- The desk attempt rate gives each scheduled attempt one vote. With equal repetitions
  it also weights tasks equally. Pooled predicate fractions instead weight by check
  count; mean within-attempt fractions are the direct conjunction comparison.
- All-k acceptance and at-least-one acceptance refer to the observed repetitions of
  fixed fixtures. The latter assumes hindsight and is not a measured retry/selection policy.
- Desk p90 uses nearest rank. The historical process summary uses sorted zero-based
  index `floor(0.9*n)`, capped at `n-1`. Its verifier retains that convention; a new
  comparison should declare a consistent quantile definition.
- Captured-usage model-cost estimates are not invoices or total operating cost.
  Missing usage is unknown; review, repair and infrastructure are excluded.

## Rebuild and publish derived artifacts

`python docs/build_latex.py` assembles the shared paper and compiles the canonical PDF
with XeLaTeX. Its build receipt records the source/generated-input hashes and the
published PDF hash; verification detects stale source/artifact pairs without assuming
byte-identical output across TeX versions. A receipt is build provenance, not an
independent content or visual review. See [paper build instructions](../paper/README.md).

The website consumes `SPEC.md`, task exports and named result ledgers. Run the site
export check, tests and build before publication; a CI build is not proof that the
public deployment contains it. Verify live HTML and downloadable artifacts after the
deployment completes. Changes to runner/adapter/task source require a reviewed refresh
of `release-manifest.json`; refreshing a manifest alone is not validation.
