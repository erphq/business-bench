# Latest complete desk comparison

**Proto + DeepSeek V4.1 Flash: 507/561 (90.4%). Codex + GPT-5.6-sol: 473/561 (84.3%).**

All 187 tasks, three repetitions per system, one shared conservative-v7 scorer. All 1,122 attempts are retained. The lead is 34 passes, or 6.06 percentage points. This is the completed 2026-09-16 comparison, not a later Proto-vs-Proto development experiment.

| Measure | Proto + DeepSeek V4.1 Flash | Codex + GPT-5.6-sol |
|---|---|---|
| Repetition 1 | 171/187 | 152/187 |
| Repetition 2 | 167/187 | 160/187 |
| Repetition 3 | 169/187 | 161/187 |
| Frozen score | **507/561 (90.4%)** | **473/561 (84.3%)** |
| All three attempts pass | 147/187 | 141/187 |
| Original raw score | 447/561 (79.7%) | 431/561 (76.8%) |

## Resources

| Measure | Proto + DeepSeek | Codex + Sol |
|---|---|---|
| Input tokens | 823,587,929 | 165,959,457 |
| Cached input | 775,672,448 | 150,329,088 |
| Uncached input | 47,915,481 | 15,630,369 |
| Output tokens | 20,910,907 | 4,823,643 |
| Estimated model cost (USD) | 22.06 | 219.13 |
| Median task duration (s) | 124.9 | 135.2 |
| p90 task duration (s) | 455.6 | 403.3 |
| Summed task duration (s) | 113,460.1 | 111,218.8 |

Costs are captured-usage API-equivalent estimates, not billed subscription charges. Uncaptured errored requests may add unknown cost. Summed parallel task time is not elapsed campaign wall time.

## Scoring and scope

Every frozen pass also completed normally. Proto had three timeouts overall; Codex had none. Original grader errors (four Proto, three Codex) are retained separately; the frozen scorer has zero grader errors. Raw and frozen verdicts are distinct fields, never mixed.

The paired task-clustered bootstrap reports a descriptive 95% interval of +1.25 to +11.05 percentage points (20,000 samples, seed 20260916). The task set was used during development, and models, sampling controls, and cohort timing differ. This establishes a lead for the reported configurations on this workload, not a causal harness-only or unseen-generalization result. Proto did not reach 90% in every repetition: repetition two was 167/187 (89.3%).

The release includes the frozen scorer at `scoring/frozen-v7/`, an allowlisted ledger, original-result and receipt hashes, artifact hashes, and provenance. `python bench/export_campaign.py --verify` checks matrix completeness, score arithmetic and the complete scorer fingerprint. Raw artifacts remain private; their hashes do not reconstruct their contents. No completed build leaderboard is claimed.

## Category results

| Category | Proto + DeepSeek | Codex + Sol |
|---|---|---|
| bookkeeping | 99/108 | 98/108 |
| drafting | 49/57 | 37/57 |
| extraction | 70/78 | 69/78 |
| reformatting | 74/78 | 78/78 |
| reports | 81/90 | 56/90 |
| spreadsheet | 115/123 | 109/123 |
| tooling | 19/27 | 26/27 |
