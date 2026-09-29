#!/usr/bin/env python3
"""Verify that the published paper is the artifact recorded by a successful build.

This checks source/generated/PDF identity, not business validity or reproducible PDF
bytes across TeX versions. Only the canonical build writes the receipt.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = Path('paper/build-receipt.json')
PDF = Path('docs/business-harness-bench-spec.pdf')
SOURCE_FILES = (
    'paper/benchmark.md', 'paper/main.tex', 'paper/references.bib',
    'docs/build_latex.py', 'docs/assemble_spec.py', 'docs/paper_details.py',
    'docs/paper_artifact.py', 'results/latest/summary.json', 'results/latest/attempts.jsonl',
)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root=ROOT):
    sources = [root / name for name in SOURCE_FILES]
    sources += sorted((root / 'paper/figures').glob('*.tex'))
    sources += sorted((root / 'docs/assets/fonts').glob('*.ttf'))
    generated = [root / 'SPEC.md'] + sorted((root / 'paper/generated').glob('*.tex'))
    generated += sorted((root / 'paper/generated').glob('*.dat'))
    return {
        'format': 1,
        'sources': {str(path.relative_to(root)): _hash(path) for path in sources},
        'generated': {str(path.relative_to(root)): _hash(path) for path in generated},
        'pdf': {'path': str(PDF), 'sha256': _hash(root / PDF)},
    }


def record(root=ROOT):
    """Called only after build_latex successfully writes the canonical PDF."""
    receipt = root / RECEIPT
    receipt.write_text(json.dumps(snapshot(root), indent=2, sort_keys=True) + '\n')
    print('Recorded published paper inputs and PDF:', receipt)


def verify(root=ROOT):
    try:
        recorded = json.loads((root / RECEIPT).read_text())
        current = snapshot(root)
    except (OSError, ValueError) as error:
        raise SystemExit(f'Paper build receipt unavailable: {error}; run python docs/build_latex.py') from error
    if recorded != current:
        changed = [section for section in ('sources', 'generated', 'pdf', 'format')
                   if recorded.get(section) != current[section]]
        raise SystemExit('Published paper is stale or changed (' + ', '.join(changed) +
                         '); run python docs/build_latex.py and review the rebuilt artifact')
    print('Verified published paper source, generated content and PDF receipt')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', required=True)
    parser.parse_args()
    verify()
