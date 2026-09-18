"""Build the paper and result report from the verified two-system ledger summary."""
import json
from pathlib import Path
from paper_details import detail_tables
ROOT=Path(__file__).resolve().parents[1]

def tables():
    a,b=json.loads((ROOT/'results/latest/summary.json').read_text())
    result=['| Measure | Proto + DeepSeek V4.1 Flash | Codex + GPT-5.6-sol |','|---|---|---|']
    for i in (1,2,3):
        result.append(f"| Repetition {i} | {a['by_repetition'][str(i)]}/187 | {b['by_repetition'][str(i)]}/187 |")
    result += [f"| Frozen score | **{a['passed']}/561 (90.4%)** | **{b['passed']}/561 (84.3%)** |",
        f"| All three attempts pass | {a['all_three_pass']}/187 | {b['all_three_pass']}/187 |",
        f"| Original raw score | {a['raw_passed']}/561 (79.7%) | {b['raw_passed']}/561 (76.8%) |"]
    efficiency=['| Measure | Proto + DeepSeek | Codex + Sol |','|---|---|---|']
    for label,key in [('Input tokens','input'),('Cached input','cached_input'),('Uncached input','uncached_input'),('Output tokens','output')]:
        efficiency.append(f"| {label} | {a['usage'][key]:,} | {b['usage'][key]:,} |")
    for label,key,fmt in [('Estimated model cost (USD)','estimated_cost_sum_usd',',.2f'),('Median task duration (s)','median_wall_s',',.1f'),('p90 task duration (s)','p90_wall_s',',.1f'),('Summed task duration (s)','sum_wall_s',',.1f')]:
        efficiency.append(f"| {label} | {a[key]:{fmt}} | {b[key]:{fmt}} |")
    return '\n'.join(result),'\n'.join(efficiency)

def main():
    result,efficiency=tables()
    paper=(ROOT/'paper/benchmark.md').read_text().replace('<!-- result-table -->',result).replace('<!-- efficiency-table -->',efficiency)
    for marker, generated in detail_tables().items():
        paper = paper.replace(marker, generated)
    (ROOT/'SPEC.md').write_text(paper)
    report='# Latest complete desk comparison\n\n**Proto + DeepSeek V4.1 Flash: 507/561 (90.4%). Codex + GPT-5.6-sol: 473/561 (84.3%).**\n\n'
    report+='All 187 tasks, three repetitions per system, one shared conservative-v7 scorer. All 1,122 attempts are retained. The lead is 34 passes, or 6.06 percentage points. This is the completed 2026-09-16 comparison, not a later Proto-vs-Proto development experiment.\n\n'+result+'\n\n'
    report+='## Resources\n\n'+efficiency+'\n\nCosts are captured-usage API-equivalent estimates, not billed subscription charges. Uncaptured errored requests may add unknown cost. Summed parallel task time is not elapsed campaign wall time.\n\n'
    report+='## Scoring and scope\n\nEvery frozen pass also completed normally. Proto had three timeouts overall; Codex had none. Original grader errors (four Proto, three Codex) are retained separately; the frozen scorer has zero grader errors. Raw and frozen verdicts are distinct fields, never mixed.\n\n'
    report+='The paired task-clustered bootstrap reports a descriptive 95% interval of +1.25 to +11.05 percentage points (20,000 samples, seed 20260916). The task set was used during development, and models, sampling controls, and cohort timing differ. This establishes a lead for the reported configurations on this workload, not a causal harness-only or unseen-generalization result. Proto did not reach 90% in every repetition: repetition two was 167/187 (89.3%).\n\n'
    report+='The release includes the frozen scorer at `scoring/frozen-v7/`, an allowlisted ledger, original-result and receipt hashes, artifact hashes, and provenance. `python bench/export_campaign.py --verify` checks matrix completeness, score arithmetic and the complete scorer fingerprint. Raw artifacts remain private; their hashes do not reconstruct their contents. No completed build leaderboard is claimed.\n\n'
    report+='## Category results\n\n| Category | Proto + DeepSeek | Codex + Sol |\n|---|---|---|\n'
    a,b=json.loads((ROOT/'results/latest/summary.json').read_text())
    for category in a['by_category']:
        x,y=a['by_category'][category],b['by_category'][category]
        report+=f"| {category} | {x['passed']}/{x['attempts']} | {y['passed']}/{y['attempts']} |\n"
    (ROOT/'results/latest/README.md').write_text(report)
    print('Assembled paper and corrected results')

if __name__=='__main__': main()
