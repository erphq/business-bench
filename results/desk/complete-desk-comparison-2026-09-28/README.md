# Desk comparison, 28 September 2026

All 187 desk tasks, three repetitions each, for three systems under one frozen `conservative-v7` scorer: 1,683 attempts.

| System | Frozen score | Passed all 3 | Original score | Median task time | Input tokens |
|---|---|---|---|---|---|
| Proto + DeepSeek V4.1 Flash | **502/561 (89.5%)** | 147 of 187 | 444 | 78 s | 300M |
| Proto + gpt-6-sol | **495/561 (88.2%)** | 153 of 187 | 443 | 115 s | 173M |
| Codex + gpt-6-sol | **487/561 (86.8%)** | 144 of 187 | 440 | 89 s | 93M |

Proto and Codex on gpt-6-sol used the same model, reasoning level (high), ChatGPT account and host. Their difference is
+1.4 percentage points, with a descriptive 95% task-bootstrap interval of -1.8 to +4.8. The DeepSeek system uses a
different model, provider and sampling.

Per repetition, Proto + gpt-6-sol scored 165, 167 and 163; Codex 162, 162 and 163; Proto + DeepSeek 171, 168 and 163.

## Scope

- The 187 tasks are public and were used in Proto's development. Repetitions rerun the same inputs.
- Repetition 1 ran with all three systems side by side. Repetitions 2 and 3 of Codex and of Proto on DeepSeek ran side
  by side; those of Proto on gpt-6-sol ran alone. Task times therefore depend on load; token counts do not.
- No cost estimates are published: the frozen pricing table has no gpt-6-sol or direct DeepSeek V4.1 Flash rate, and both
  gpt-6-sol systems used a subscription that is not billed per token.

Builds, adapters, homes and concurrency are in [`provenance.json`](provenance.json) and [`campaign.json`](campaign.json).

## Verify

`python bench/export_desk_campaign.py --verify` checks the complete task x system x repetition matrix, the summary
arithmetic, the paired bootstrap, the ledger hash and the frozen scorer fingerprint. Every receipt names its run,
hash-matches the original result it scored and comes from the frozen scorer. Original artifacts stay private; their
hashes are in the ledger. The 2026-09-16 comparison in [`results/latest`](../../latest/) is a separate campaign.
