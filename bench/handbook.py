#!/usr/bin/env python3
"""Executable handbook: each process task's policies written once, in `tasks/process/<task>/policies.yaml`.

    handbook.py render TASK [--out DIR | --write]   print the handbook the registry generates (or write it)
    handbook.py check [--task all|ID[,ID]]          the generated handbook is byte-identical to the committed one
    handbook.py lint  [--task all|ID[,ID]]          citations and rule bindings are sound; report unenforced clauses

A registry has two parts:

    handbook:                     # the files of handbook/, in order, as blocks joined by one blank line
      README.md:
        - |-                      # a literal markdown block (headings, preambles, tables that are not clauses)
          # Northgate Valve Co. handbook
          ...
      payables.md:
        - '# Accounts payable (AP)'
        - AP-3.1                  # a block that is exactly a clause id places that clause here
    policies:
      AP-3.1:
        params: {freight_limit: 100}           # optional; filled into {name} or {name:format-spec} in the text
        text: |-                               # rendered as '**AP-3.1** ' + text, line breaks as written
          Freight of up to ${freight_limit:,.2f} per invoice is accepted ...
        rules: [edit_billed_amounts]           # optional; audit rules (bench/process_rules.RULES) that enforce it

A declared variant of a task (a sibling folder, like payment-run-need-to-know) adds `extends: <task>`: its registry
then holds only what it adds or replaces. The effective registry is the parent's with the variant's handbook files
laid over it (a file of the same name replaces the parent's) and the variant's clauses added (redefining a parent
clause is an error). The variant's handbook/ folder commits only its own files, and `check` and `render --write`
touch only those; the parent's files stay the parent's, byte for byte. `lint` works on the effective registry.

`text` and `params` are what the agent reads. `rules` is grader-side: a guard or policy compiled for an agent (the
AgentWarden idea) must come from the rendered text only, never from `rules`, or it would be compiled from the grader.

`lint` errors (exit 1): a check cites a clause the registry lacks; an audit check names a rule that does not exist or
that none of its cited clauses binds; a registry binds an unknown rule; a clause cross-references an unknown clause;
a clause is placed zero or several times; a template names an undefined parameter or a parameter goes unused.
`lint` reports, without failing: clauses no check cites and no rule binds (unenforced), checks that cite nothing,
and bound rules no check in the task runs. Tasks without a registry are skipped.
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TASKS = os.path.join(ROOT, 'tasks', 'process')
REGISTRY = 'policies.yaml'

CLAUSE_ID = re.compile(r'[A-Z]{2,5}-\d+(?:\.\d+)*')
CLAUSE_REF = re.compile(r'(?<![A-Za-z0-9-])[A-Z]{2,5}-\d+\.\d+(?:\.\d+)*(?![0-9])')
PLACEHOLDER = re.compile(r'\{\{|\}\}|\{([A-Za-z_]\w*)(?::([^{}]*))?\}|[{}]')
POLICY_KEYS = {'text', 'params', 'rules'}


class RegistryError(ValueError):
    pass


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys (PyYAML would keep the last one silently)."""


def _unique_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise RegistryError(f'duplicate key {key!r} (line {key_node.start_mark.line + 1})')
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


# ------------------------------------------------------------------------------------------------------ registry

def task_dir(task: str) -> str:
    """A task id under tasks/process/, or a path to a task folder (tests, copies under --out)."""
    d = os.path.join(TASKS, task)
    return d if os.path.isfile(os.path.join(d, 'task.yaml')) else task


def registry_path(task: str) -> str:
    return os.path.join(task_dir(task), REGISTRY)


def has_registry(task: str) -> bool:
    return os.path.isfile(registry_path(task))


def load(task: str, _seen: tuple = ()) -> dict:
    """The task's effective registry, shape-checked. Raises RegistryError on a malformed one. For a registry that
    `extends` a parent, the result also carries `own_files`: the handbook files the variant itself commits."""
    reg = _load_one(task)
    parent = reg.pop('extends', None)
    if parent is None:
        return reg
    if not isinstance(parent, str) or not has_registry(parent):
        raise RegistryError(f'extends names {parent!r}, which has no {REGISTRY}')
    if parent in _seen:
        raise RegistryError(f'extends loops through {parent}')
    base = load(parent, _seen + (task,))
    redefined = sorted(set(base['policies']) & set(reg['policies']))
    if redefined:
        raise RegistryError(f'redefines clauses of {parent}: {redefined}')
    return {'handbook': {**base['handbook'], **reg['handbook']}, 'policies': {**base['policies'], **reg['policies']},
            'own_files': list(reg['handbook'])}


def _load_one(task: str) -> dict:
    with open(registry_path(task), encoding='utf-8') as f:
        try:
            reg = yaml.load(f, Loader=_UniqueKeyLoader)  # noqa: S506 (a SafeLoader subclass)
        except yaml.YAMLError as e:
            raise RegistryError(f'not valid YAML: {e}') from None
    if not isinstance(reg, dict) or set(reg) - {'extends'} != {'handbook', 'policies'}:
        raise RegistryError('a registry has exactly two top-level keys: handbook and policies (and optionally extends)')
    if not isinstance(reg['handbook'], dict) or not isinstance(reg['policies'], dict):
        raise RegistryError('handbook and policies are mappings')
    for name, blocks in reg['handbook'].items():
        if not isinstance(blocks, list) or not all(isinstance(b, str) for b in blocks):
            raise RegistryError(f'handbook file {name} is a list of strings (literal blocks or clause ids)')
    for cid, pol in reg['policies'].items():
        if not isinstance(cid, str) or not CLAUSE_ID.fullmatch(cid):
            raise RegistryError(f'{cid!r} is not a clause id (like AP-1.1)')
        if not isinstance(pol, dict) or 'text' not in pol or set(pol) - POLICY_KEYS:
            raise RegistryError(f'{cid}: a policy has text and optionally params and rules, got {sorted(pol or {})}')
        if not isinstance(pol['text'], str):
            raise RegistryError(f'{cid}: text is a string')
        if not isinstance(pol.get('params', {}), dict):
            raise RegistryError(f'{cid}: params is a mapping')
        rules = pol.get('rules', [])
        if not isinstance(rules, list) or not all(isinstance(r, str) for r in rules):
            raise RegistryError(f'{cid}: rules is a list of rule names')
    return reg


def fill(template: str, params: dict, cid: str = '?') -> tuple[str, set[str]]:
    """Fill {name} and {name:spec} from params ({{ and }} are literal braces). Returns the text and the names used."""
    used: set[str] = set()

    def sub(m):
        tok = m.group(0)
        if tok in ('{{', '}}'):
            return tok[0]
        if m.group(1) is None:
            raise RegistryError(f'{cid}: stray {tok!r} in text (write {tok * 2} for a literal brace)')
        name = m.group(1)
        if name not in params:
            raise RegistryError(f'{cid}: text uses {{{name}}}, which params does not define')
        used.add(name)
        return format(params[name], m.group(2) or '')

    return PLACEHOLDER.sub(sub, template), used


def clause_text(reg: dict, cid: str) -> str:
    pol = reg['policies'][cid]
    return fill(pol['text'], pol.get('params') or {}, cid)[0]


def render(reg: dict) -> dict[str, str]:
    """handbook file name -> content."""
    out = {}
    for name, blocks in reg['handbook'].items():
        parts = []
        for b in blocks:
            if CLAUSE_ID.fullmatch(b):
                if b not in reg['policies']:
                    raise RegistryError(f'{name} places {b}, which policies does not define')
                parts.append(f'**{b}** {clause_text(reg, b)}')
            else:
                parts.append(b)
        out[name] = '\n\n'.join(parts) + '\n'
    return out


# --------------------------------------------------------------------------------------------------------- check

def check(task: str) -> list[str]:
    """Differences between the generated handbook and the committed handbook/ folder (empty when byte-identical)."""
    try:
        reg = load(task)
        files = render(reg)
    except RegistryError as e:
        return [f'registry: {e}']
    if 'own_files' in reg:
        files = {name: files[name] for name in reg['own_files']}
    hb = os.path.join(task_dir(task), 'handbook')
    on_disk = set(os.listdir(hb)) if os.path.isdir(hb) else set()
    problems = [f'handbook/{f} is committed but the registry does not generate it' for f in sorted(on_disk - set(files))]
    for name, text in files.items():
        if name not in on_disk:
            problems.append(f'handbook/{name} is generated but not committed')
            continue
        with open(os.path.join(hb, name), 'rb') as f:
            committed = f.read()
        if committed != text.encode('utf-8'):
            diff = list(difflib.unified_diff(committed.decode('utf-8').splitlines(), text.splitlines(),
                                             f'committed/{name}', f'generated/{name}', lineterm='', n=0))
            problems.append(f'handbook/{name} differs from the generated text:\n      ' + '\n      '.join(diff[:20]))
    return problems


# ---------------------------------------------------------------------------------------------------------- lint

def _rules() -> dict:
    sys.path.insert(0, HERE)
    from process_rules import RULES
    return RULES


def lint(task: str) -> tuple[list[str], list[str]]:
    """(errors, report). Errors fail; the report lists what nothing enforces."""
    try:
        reg = load(task)
        render(reg)
    except RegistryError as e:
        return [f'registry: {e}'], []
    rules = _rules()
    spec = yaml.safe_load(open(os.path.join(task_dir(task), 'task.yaml'), encoding='utf-8'))
    checks = spec.get('checks') or []
    policies = reg['policies']
    errors: list[str] = []

    placed: dict[str, int] = {}
    for blocks in reg['handbook'].values():
        for b in blocks:
            if CLAUSE_ID.fullmatch(b):
                placed[b] = placed.get(b, 0) + 1
            else:
                for ref in CLAUSE_REF.findall(b):
                    if ref not in policies:
                        errors.append(f'the handbook text refers to {ref}, which the registry lacks')
    for cid, pol in policies.items():
        if placed.get(cid, 0) != 1:
            errors.append(f'{cid} is placed in the handbook {placed.get(cid, 0)} times (once expected)')
        text, used = fill(pol['text'], pol.get('params') or {}, cid)
        for name in sorted(set(pol.get('params') or {}) - used):
            errors.append(f'{cid}: parameter {name} is not used in the text')
        for ref in CLAUSE_REF.findall(text):
            if ref not in policies:
                errors.append(f'{cid} refers to {ref}, which the registry lacks')
        for r in pol.get('rules', []):
            if r not in rules:
                errors.append(f'{cid} binds unknown audit rule {r}')

    cited: set[str] = set()
    ran: set[str] = set()
    report: list[str] = []
    for c in checks:
        cites = c.get('cites') or []
        cited.update(cites)
        for cid in cites:
            if cid not in policies:
                errors.append(f'check {c["name"]!r} cites {cid}, which the registry lacks')
        if c.get('type') in ('audit_forbidden', 'audit_required'):
            r = c.get('rule')
            ran.add(r)
            if r not in rules:
                errors.append(f'check {c["name"]!r} runs unknown audit rule {r}')
            elif not any(r in policies.get(cid, {}).get('rules', []) for cid in cites):
                errors.append(f'check {c["name"]!r} runs {r}, but none of its cited clauses '
                              f'{cites} binds that rule')
        if not cites:
            report.append(f'check {c["name"]!r} ({c.get("type")}) cites no clause')

    bound = {cid: pol.get('rules', []) for cid, pol in policies.items()}
    for cid in policies:
        if cid not in cited and not bound[cid]:
            report.append(f'{cid} is not enforced: no check cites it and no audit rule is bound to it')
    for cid, rs in bound.items():
        for r in rs:
            if r in rules and r not in ran:
                report.append(f'{cid} binds {r}, but no check in this task runs it')
    return errors, report


def problems(task: str) -> list[str]:
    """Everything that should fail validation for a task with a registry: byte differences and lint errors."""
    if not has_registry(task):
        return []
    diffs = check(task)
    return diffs + [e for e in lint(task)[0] if e not in diffs]


# ----------------------------------------------------------------------------------------------------------- cli

def _tasks(arg: str) -> list[str]:
    if arg != 'all':
        return arg.split(',')
    return sorted(d for d in os.listdir(TASKS) if os.path.isfile(os.path.join(TASKS, d, 'task.yaml')))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('render', help='print or write the generated handbook')
    r.add_argument('task')
    g = r.add_mutually_exclusive_group()
    g.add_argument('--out', help='write the files into this directory')
    g.add_argument('--write', action='store_true',
                   help="overwrite the task's handbook/ (for new tasks and deliberate, reviewed clause changes)")
    for name in ('check', 'lint'):
        p = sub.add_parser(name)
        p.add_argument('--task', default='all')
    a = ap.parse_args(argv)

    if a.cmd == 'render':
        reg = load(a.task)
        files = render(reg)
        if a.write and 'own_files' in reg:
            files = {name: files[name] for name in reg['own_files']}
        out = os.path.join(task_dir(a.task), 'handbook') if a.write else a.out
        if not out:
            for name, text in files.items():
                sys.stdout.write(f'==> {name} <==\n{text}')
            return 0
        os.makedirs(out, exist_ok=True)
        for name, text in files.items():
            with open(os.path.join(out, name), 'w', encoding='utf-8', newline='') as f:
                f.write(text)
        print(f'wrote {len(files)} file(s) to {out}')
        return 0

    bad = 0
    bound_anywhere: set[str] = set()
    for t in _tasks(a.task):
        if not has_registry(t):
            print(f'--   {t}: no {REGISTRY}')
            continue
        if a.cmd == 'check':
            found, extra = check(t), []
        else:
            found, extra = lint(t)
            try:
                bound_anywhere.update(r for pol in load(t)['policies'].values() for r in pol.get('rules', []))
            except RegistryError:
                pass
        print(f'{"ok  " if not found else "FAIL"} {t}')
        for p in found:
            print(f'     - {p}')
        for p in extra:
            print(f'     . {p}')
        bad += bool(found)
    if a.cmd == 'lint' and a.task == 'all':
        for r in sorted(set(_rules()) - bound_anywhere):
            print(f'     . audit rule {r} is bound to no clause in any registry')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
