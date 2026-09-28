#!/usr/bin/env python3
"""Validate process-track tasks before they enter a release.

  validate_process.py [--task ID[,ID]] [--seeds 0,1,2] [--strict]

For each task and seed:
  1. both oracle repetitions complete and pass every required check;
  2. a null agent that does nothing fails;
  3. each negative control fails every check task.yaml says it targets (and the run completes);
  4. two oracle runs from the same seed end in the same state (canonical dump without wall-clock columns);
  5. every clause a check cites exists in the handbook the agent sees.
Every policy must record each expected turn, exit successfully without a timeout, and have no runner or
grader errors before its verdict is used. Exit status 1 when anything fails. --strict additionally reports
controls whose only failures are outside their declared targets; incidental additional failures are allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import process_run as pr  # noqa: E402

VOLATILE = {'audit_events': ('wall_time',)}


def canonical_hash(db_path: str) -> str:
    """Hash of every table's rows, sorted, without wall-clock columns."""
    db = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    h = hashlib.sha256()
    for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                               "ORDER BY name"):
        cols = [c[1] for c in db.execute(f'PRAGMA table_info({table})') if c[1] not in VOLATILE.get(table, ())]
        rows = db.execute(f'SELECT {", ".join(cols)} FROM {table}').fetchall()
        h.update(table.encode())
        for r in sorted(map(repr, rows)):
            h.update(r.encode())
    db.close()
    return h.hexdigest()


def cited_clauses(task: dict) -> set[str]:
    return {c for spec in task.get('checks', []) for c in spec.get('cites', [])}


def handbook_clauses(scenario: str) -> set[str]:
    text = ''.join(open(os.path.join(scenario, 'handbook', f), encoding='utf-8').read()
                   for f in os.listdir(os.path.join(scenario, 'handbook')))
    return set(re.findall(r'\*\*([A-Z]{2,5}-\d+(?:\.\d+)*)\*\*', text))


def completion_problems(result: dict, expected_turns: list[int]) -> list[str]:
    """A control's failed checks are evidence only after the policy and grader complete."""
    problems = []
    if result.get('error'):
        problems.append(f'runner error: {result["error"]}')
    if result.get('grader_errors'):
        problems.append(f'grader errors: {result["grader_errors"]}')
    if not isinstance(result.get('passed'), bool):
        problems.append('missing boolean grading verdict')
    turns = result.get('turns')
    if not isinstance(turns, list) or any(not isinstance(t, dict) for t in turns):
        problems.append('missing or invalid turn records')
        return problems
    observed = [t.get('n') for t in turns]
    if observed != expected_turns:
        problems.append(f'turn records {observed} do not match expected {expected_turns}')
    for turn in turns:
        code = turn.get('exit_code')
        if type(code) is not int or code != 0:
            problems.append(f'turn {turn.get("n")}: nonzero or unknown exit code {code!r}')
        if turn.get('timed_out') is not False:
            problems.append(f'turn {turn.get("n")}: timeout or unknown timeout status')
    return problems


def validate(task: str, seed: int, strict: bool) -> list[str]:
    problems = []
    tdir = pr.task_dir(task)
    with open(os.path.join(tdir, 'task.yaml'), encoding='utf-8') as source:
        spec = yaml.safe_load(source)
    scenario = pr.ensure_scenario(task, seed)
    with open(os.path.join(scenario, 'meta.json'), encoding='utf-8') as source:
        expected_turns = [t['n'] for t in json.load(source)['turns']]
    missing = cited_clauses(spec) - handbook_clauses(scenario)
    if missing:
        problems.append(f'checks cite clauses the handbook lacks: {sorted(missing)}')
    names = {c['name'] for c in spec['checks']}
    with tempfile.TemporaryDirectory(prefix='validate-') as tmp:
        o1 = pr.run_attempt(task, 'oracle', seed, 1, tmp, scenario)
        o2 = pr.run_attempt(task, 'oracle', seed, 2, tmp, scenario)
        oracle_complete = []
        for repetition, result in enumerate((o1, o2), 1):
            incomplete = completion_problems(result, expected_turns)
            problems.extend(f'oracle repetition {repetition}: {p}' for p in incomplete)
            oracle_complete.append(not incomplete)
            if not incomplete and not result['passed']:
                problems.append(f'oracle repetition {repetition} fails: ' +
                                ', '.join(c['name'] for c in result['checks'] if not c['passed']))
        if all(oracle_complete):
            if canonical_hash(os.path.join(o1['work_dir'], 'final.db')) != canonical_hash(os.path.join(o2['work_dir'], 'final.db')):
                problems.append('two oracle runs from the same seed end in different states')
        null = pr.run_attempt(task, 'null', seed, 1, tmp, scenario)
        incomplete = completion_problems(null, expected_turns)
        problems.extend(f'null: {p}' for p in incomplete)
        if not incomplete and null['passed']:
            problems.append('a null agent passes')
        for neg, targets in (spec.get('negative_controls') or {}).items():
            unknown = set(targets) - names
            if unknown:
                problems.append(f'{neg} targets unknown checks {sorted(unknown)}')
            r = pr.run_attempt(task, neg, seed, 1, tmp, scenario)
            incomplete = completion_problems(r, expected_turns)
            problems.extend(f'{neg}: {p}' for p in incomplete)
            if incomplete:
                continue
            failed = {c['name'] for c in r['checks'] if not c['passed']}
            if r['passed']:
                problems.append(f'{neg} passes')
            not_failed = [t for t in targets if t not in failed]
            if not_failed:
                problems.append(f'{neg} does not fail {not_failed}')
            if strict and failed - set(targets) and not (failed & set(targets)):
                problems.append(f'{neg} fails only checks it does not target: {sorted(failed)}')
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--task', default='all')
    ap.add_argument('--seeds', default='0')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    tasks = sorted(d for d in os.listdir(pr.TASKS) if os.path.isfile(os.path.join(pr.TASKS, d, 'task.yaml'))) \
        if a.task == 'all' else a.task.split(',')
    bad = 0
    for t in tasks:
        for seed in (int(s) for s in a.seeds.split(',')):
            problems = validate(t, seed, a.strict)
            print(f'{"ok  " if not problems else "FAIL"} {t} seed {seed}')
            for p in problems:
                print(f'     - {p}')
            bad += bool(problems)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
