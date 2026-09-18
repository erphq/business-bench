#!/usr/bin/env python3
"""Hash release task, runner and adapter source; verify without invoking providers."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'release-manifest.json'


def manifest():
    paths = []
    for folder in ('tasks', 'bench', 'harnesses', 'docker'):
        paths.extend(p for p in (ROOT / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    paths.append(ROOT / 'requirements.txt')
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    current = manifest()
    if a.write:
        OUT.write_text(json.dumps(current, indent=2) + '\n')
    elif json.loads(OUT.read_text()) != current:
        raise SystemExit('Release source differs from release-manifest.json')
    print(f'Verified release inventory: {len(current)} files')


if __name__ == '__main__':
    main()
