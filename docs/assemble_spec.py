#!/usr/bin/env python3
"""Assemble the paper premise, technical specification and latest evidence tables."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = {'codex-sol': 'Codex / gpt-5.6-sol', 'proto-deepseek': 'Proto / DeepSeek V4.1 Flash',
          'proto-glm': 'Proto / GLM-5.3-Flash', 'proto-qwen': 'Proto / Qwen 3.8 Flash'}


def result_markdown():
    rows = json.loads((ROOT / 'results/latest/summary.json').read_text())
    lines = ['# Latest full-arm results: campaign full-1', '',
        'This is the recorded desk scoring snapshot from the four complete arms of the latest full benchmark campaign. Each arm covers all 187 tasks three times (561 attempts); the release contains 2,244 attempts. It is not a Proto development comparison. The overall campaign included additional incomplete arms; they are not represented as complete results here. No fully acceptance-validated full build campaign is included.', '',
        '## Recorded artifact scores', '',
        '| System | Passes / 561 | Pass rate | All 3 / 187 | Median min |',
        '|---|---|---|---|---|']
    for r in rows:
        lines.append(f"| {MODELS[r['harness']]} | {r['passed']} | {r['pass_rate']:.2%} | {r['all_three_pass']} | {r['median_wall_s']/60:.2f} |")
    lines += ['', 'Codex / gpt-5.6-sol has the highest recorded artifact pass rate in this release. The cells use different models; these numbers do not isolate a harness effect or establish performance beyond this workload.', '',
        '## Repetition and execution accounting', '',
        '| System | R1 / 187 | R2 / 187 | R3 / 187 | Timeouts | Nonzero exits |',
        '|---|---|---|---|---|---|']
    for r in rows:
        p = r['by_repetition']
        lines.append(f"| {r['harness']} | {p['1']} | {p['2']} | {p['3']} | {r['timed_out']} | {r['nonzero_exit']} |")
    lines += ['', '| System | Passing, abnormal exit | Grader-error attempts | Missing usage |', '|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['harness']} | {r['passing_abnormal_exit']} | {r['grader_error_attempts']} | {r['usage_missing']} |")
    lines += ['', 'Timeout and nonzero-exit columns can overlap. Artifact pass is the stored grader verdict, not normal process completion. All attempts remain in the denominator. Grader-error counts and missing usage describe unresolved evidence; they are not silently repaired or removed.', '',
        '## Estimated model cost', '',
        '| System | Observations / 561 | Mean USD, observed | Sum USD, observed |', '|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['harness']} | {r['cost_observations']} | {r['estimated_cost_mean_usd']:.4f} | {r['estimated_cost_sum_usd']:.4f} |")
    lines += ['', 'Costs are recorded estimates under the historical price assumptions, not invoices or current-price claims. Means exclude missing cost observations; sums are observed sums, not complete billed totals when observations are missing. The price table is in bench/prices.json.', '',
        '## Category counts', '',
        '| Category | Codex sol | Proto DeepSeek | Proto GLM | Proto Qwen |', '|---|---|---|---|---|']
    for c in rows[0]['by_category']:
        cells = [f"{r['by_category'][c]['passed']} / {r['by_category'][c]['attempts']}" for r in rows]
        lines.append('| ' + c + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', '## Provenance and interpretation', '',
        'The launcher names image business-bench:v38 and runtime revision 53a303309; it sets high reasoning effort, first-party provider routes for the three API models, native workbook recalculation, and three repetitions. These are recorded launch settings, not independently recovered per-request configurations. Model usage is retained in the ledger; the Codex usage extractor may infer the configured model name when its event stream omits it.', '',
        'Original result.json files lack per-attempt scorer hashes. Their source file hashes are retained, but a uniform immutable historical grader cannot be established from these records. The published snapshot preserves the recorded verdicts without applying current release code retrospectively. Treat the table as descriptive campaign evidence, not a scorer-controlled causal experiment or independently certified leaderboard.', '',
        'attempts.jsonl contains every included result with allowlisted check verdicts, execution fields, usage, costs, source hashes, and source modification timestamps. File modification times are not asserted to be run start times. summary.json is reproducible from that ledger. provenance.json defines inclusion and known gaps. Raw workspaces, homes, trace logs, and secret-bearing reviewer sheets are deliberately absent.', '']
    return '\n'.join(lines)


def main():
    results = result_markdown()
    (ROOT / 'results/latest/README.md').write_text(results)
    premise = (ROOT / 'paper/premise.md').read_text()
    technical = (ROOT / 'docs/technical-spec.md').read_text()
    # Preserve the premise's references, then restart result headings below the technical sections.
    results_spec = results.replace('# Latest full-arm results: campaign full-1', '## 12. Latest full-arm results: campaign full-1')
    results_spec = '\n'.join('### ' + line[3:] if line.startswith('## ') and not line.startswith('## 12.') else line for line in results_spec.splitlines())
    (ROOT / 'SPEC.md').write_text(premise + '\n' + technical + '\n' + results_spec + '\n')
    print('Assembled SPEC.md and results/latest/README.md')


if __name__ == '__main__':
    main()
