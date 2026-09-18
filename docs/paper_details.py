"""Generate paper-only detail tables from the immutable released attempt ledger."""
from collections import Counter, defaultdict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def table(headers, rows):
    return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                      '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(str(value) for value in row) + ' |' for row in rows])


def detail_tables():
    summary = json.loads((ROOT / 'results/latest/summary.json').read_text())
    attempts = [json.loads(line) for line in (ROOT / 'results/latest/attempts.jsonl').read_text().splitlines()]
    proto, codex = summary
    categories = []
    for name, p in proto['by_category'].items():
        c = codex['by_category'][name]
        categories.append([name.title(), p['attempts'] // 3,
            f"{p['passed']}/{p['attempts']} ({p['passed']/p['attempts']:.1%})",
            f"{c['passed']}/{c['attempts']} ({c['passed']/c['attempts']:.1%})",
            f"{100*(p['passed']-c['passed'])/p['attempts']:+.1f}"])
    distributions, transitions = [], []
    for system in ('proto-deepseek', 'codex-sol'):
        rows = [r for r in attempts if r['harness'] == system]
        tasks = defaultdict(list)
        for row in rows:
            tasks[row['task']].append(row)
        distributions.append(Counter(sum(r['passed'] for r in group) for group in tasks.values()))
        transitions.append(Counter(('ungraded' if r['raw_grader_error_count'] else 'pass' if r['raw_passed'] else 'fail',
            'pass' if r['passed'] else 'fail') for r in rows))
    states = [('pass', 'pass'), ('fail', 'pass'), ('ungraded', 'pass'), ('pass', 'fail'), ('fail', 'fail')]
    return {
        '<!-- category-table -->': table(['Category', 'Tasks', 'Proto + DeepSeek', 'Codex + Sol', 'Gap (pp)'], categories),
        '<!-- repeatability-table -->': table(['Passing attempts per task', 'Proto + DeepSeek', 'Codex + Sol'],
            [[f'{i} of 3', distributions[0][i], distributions[1][i]] for i in (3, 2, 1, 0)]),
        '<!-- transition-table -->': table(['Original verdict → Frozen verdict', 'Proto + DeepSeek', 'Codex + Sol'],
            [[f'{a.title()} to {b}', transitions[0][(a,b)], transitions[1][(a,b)]] for a,b in states]),
    }
