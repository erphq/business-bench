# Desk comparison, 2026-09-28

**Proto + DeepSeek V4.1 Flash: 171/187 (91.4%). Proto + gpt-6-sol: 165/187 (88.2%). Codex + gpt-6-sol: 162/187 (86.6%).**

All 187 desk tasks, one repetition per system, one shared conservative-v7 scorer. All 561 attempts are retained.
Proto and Codex on gpt-6-sol ran in the same window on the same subscription account, host, model and reasoning
level, so that pair is the closest to a harness comparison this repository has published. Their difference is
1.6 percentage points with a descriptive 95% task-bootstrap interval of -3.2 to +6.4: no clear difference in
acceptance for this workload.

| Measure | Proto + DeepSeek V4.1 Flash | Proto + gpt-6-sol | Codex + gpt-6-sol |
|---|---|---|---|
| Frozen score | **171/187 (91.4%)** | **165/187 (88.2%)** | **162/187 (86.6%)** |
| Original raw score | 154/187 | 148/187 | 146/187 |
| Timed out | 0 | 1 | 0 |
| Original grader errors | 2 | 1 | 1 |

## Resources

| Measure | Proto + DeepSeek | Proto + gpt-6-sol | Codex + gpt-6-sol |
|---|---|---|---|
| Median task duration (s) | 78.3 | 129.5 | 97.1 |
| p90 task duration (s) | 182.2 | 249.1 | 276.8 |
| Summed task duration (s) | 19,572.1 | 28,982.6 | 26,795.5 |
| Input tokens | 100,329,787 | 66,266,058 | 31,569,817 |
| Cached input | 92,237,696 | 59,328,768 | 27,541,120 |
| Uncached input | 8,092,091 | 6,937,290 | 4,028,697 |
| Output tokens | 3,503,419 | 942,855 | 1,015,735 |

On the same model, Codex finished the median task faster and used about half the input tokens; Proto's p90 was
lower. No cost estimates are published: the frozen pricing table has no gpt-6-sol or direct DeepSeek V4.1 Flash rate,
and both gpt-6-sol cells used a subscription that is not billed per token. Summed parallel task time is not elapsed
campaign time.

## Category results

| Category | Proto + DeepSeek | Proto + gpt-6-sol | Codex + gpt-6-sol |
|---|---|---|---|
| Bookkeeping | 33/36 | 32/36 | 30/36 |
| Drafting | 17/19 | 14/19 | 14/19 |
| Extraction | 26/26 | 23/26 | 24/26 |
| Reformatting | 24/26 | 25/26 | 26/26 |
| Reports | 24/30 | 23/30 | 22/30 |
| Spreadsheet | 40/41 | 40/41 | 38/41 |
| Tooling | 7/9 | 8/9 | 8/9 |

## Scoring and scope

One repetition per task, so each system's score is a single draw; this campaign does not report repeated success.
The task set was used during development: Proto's configuration was developed using traces from runs on these tasks,
so this is not evidence of unseen generalization. The DeepSeek cell differs from the gpt-6-sol cells in model,
provider and sampling (temperature 0.7). Exact builds, adapters, homes and concurrency are in
[`provenance.json`](provenance.json) and [`campaign.json`](campaign.json). Codex CLI results carried the usage
extractor's default model label gpt-5.6-sol; the CLI's own session context records gpt-6-sol at high effort, and the
ledger renames that key.

`python bench/export_desk_campaign.py --verify` checks the complete task x system matrix, the summary arithmetic,
the paired bootstrap, the ledger hash and the frozen scorer fingerprint. During export every receipt was checked to
name its run, to hash-match the original result it scored and to come from the frozen scorer. Raw artifacts remain
private; their hashes identify but do not reconstruct them. The 2026-09-16 comparison in
[`results/latest`](../../latest/) is a separate campaign and is not pooled with this one.
