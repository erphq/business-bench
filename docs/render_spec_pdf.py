#!/usr/bin/env python3
"""Compatibility command: the paper is now compiled exclusively with XeLaTeX."""
from pathlib import Path
import sys
from build_latex import ROOT, build, generate

if __name__ == '__main__':
    if len(sys.argv) > 1 and Path(sys.argv[1]).resolve() != ROOT / 'SPEC.md':
        raise SystemExit('The paper build uses SPEC.md; use docs/build_latex.py for build options')
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else ROOT / 'docs/business-harness-bench-spec.pdf'
    generate()
    build(output)
