# Latest full-arm results: campaign full-1

This is the recorded desk scoring snapshot from the four complete arms of the latest full benchmark campaign. Each arm covers all 187 tasks three times (561 attempts); the release contains 2,244 attempts. It is not a Proto development comparison. The overall campaign included additional incomplete arms; they are not represented as complete results here. No fully acceptance-validated full build campaign is included.

## Recorded artifact scores

| System | Passes / 561 | Pass rate | All 3 / 187 | Median min |
|---|---|---|---|---|
| Codex / gpt-5.6-sol | 431 | 76.83% | 126 | 2.25 |
| Proto / DeepSeek V4.1 Flash | 374 | 66.67% | 90 | 4.29 |
| Proto / GLM-5.3-Flash | 355 | 63.28% | 77 | 4.03 |
| Proto / Qwen 3.8 Flash | 381 | 67.91% | 105 | 7.03 |

Codex / gpt-5.6-sol has the highest recorded artifact pass rate in this release. The cells use different models; these numbers do not isolate a harness effect or establish performance beyond this workload.

## Repetition and execution accounting

| System | R1 / 187 | R2 / 187 | R3 / 187 | Timeouts | Nonzero exits |
|---|---|---|---|---|---|
| codex-sol | 138 | 145 | 148 | 0 | 0 |
| proto-deepseek | 125 | 126 | 123 | 56 | 78 |
| proto-glm | 122 | 116 | 117 | 34 | 45 |
| proto-qwen | 129 | 126 | 126 | 112 | 117 |

| System | Passing, abnormal exit | Grader-error attempts | Missing usage |
|---|---|---|---|
| codex-sol | 0 | 3 | 0 |
| proto-deepseek | 10 | 5 | 21 |
| proto-glm | 5 | 2 | 11 |
| proto-qwen | 32 | 3 | 5 |

Timeout and nonzero-exit columns can overlap. Artifact pass is the stored grader verdict, not normal process completion. All attempts remain in the denominator. Grader-error counts and missing usage describe unresolved evidence; they are not silently repaired or removed.

## Estimated model cost

| System | Observations / 561 | Mean USD, observed | Sum USD, observed |
|---|---|---|---|
| codex-sol | 561 | 0.3906 | 219.1257 |
| proto-deepseek | 540 | 0.0617 | 33.3271 |
| proto-glm | 550 | 0.0461 | 25.3543 |
| proto-qwen | 556 | 0.0472 | 26.2309 |

Costs are recorded estimates under the historical price assumptions, not invoices or current-price claims. Means exclude missing cost observations; sums are observed sums, not complete billed totals when observations are missing. The price table is in bench/prices.json.

## Category counts

| Category | Codex sol | Proto DeepSeek | Proto GLM | Proto Qwen |
|---|---|---|---|---|
| bookkeeping | 91 / 108 | 70 / 108 | 68 / 108 | 72 / 108 |
| drafting | 28 / 57 | 21 / 57 | 27 / 57 | 20 / 57 |
| extraction | 66 / 78 | 56 / 78 | 56 / 78 | 69 / 78 |
| reformatting | 78 / 78 | 68 / 78 | 66 / 78 | 78 / 78 |
| reports | 45 / 90 | 47 / 90 | 35 / 90 | 34 / 90 |
| spreadsheet | 98 / 123 | 94 / 123 | 90 / 123 | 94 / 123 |
| tooling | 25 / 27 | 18 / 27 | 13 / 27 | 14 / 27 |

## Provenance and interpretation

The launcher names image business-bench:v38 and runtime revision 53a303309; it sets high reasoning effort, first-party provider routes for the three API models, native workbook recalculation, and three repetitions. These are recorded launch settings, not independently recovered per-request configurations. Model usage is retained in the ledger; the Codex usage extractor may infer the configured model name when its event stream omits it.

Original result.json files lack per-attempt scorer hashes. Their source file hashes are retained, but a uniform immutable historical grader cannot be established from these records. The published snapshot preserves the recorded verdicts without applying current release code retrospectively. Treat the table as descriptive campaign evidence, not a scorer-controlled causal experiment or independently certified leaderboard.

attempts.jsonl contains every included result with allowlisted check verdicts, execution fields, usage, costs, source hashes, and source modification timestamps. File modification times are not asserted to be run start times. summary.json is reproducible from that ledger. provenance.json defines inclusion and known gaps. Raw workspaces, homes, trace logs, and secret-bearing reviewer sheets are deliberately absent.
