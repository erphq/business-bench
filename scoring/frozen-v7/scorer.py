"""Frozen diagnostic v7 scorer. Grades outputs; never repairs or overwrites them."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import zipfile
from xml.etree.ElementTree import ParseError

import openpyxl

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / 'tasks' / 'desk'


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load_module(ROOT / 'bench' / 'grade.py', 'frozen_base_grade')
sys.modules['grade'] = base
original_custom = base.c_custom
CUSTOM = {
    'price-list-page': 'price-list-check.py',
    'event-schedule-page': 'event-schedule-check.py',
    'returns-analysis': 'returns-check.py',
    'rent-roll-build': 'rent-check.py',
    'minutes-from-transcript': 'minutes-check.py',
    'refund-apology-letter': 'refund-check.py',
    'sop-from-thread': 'sop-check.py',
}
custom_modules = {
    task: load_module(ROOT / 'equivalences' / filename, 'frozen_' + task.replace('-', '_'))
    for task, filename in CUSTOM.items()
}
for checker in custom_modules.values():
    if hasattr(checker, '_recalculated'):
        checker._recalculated = base.recalculated_workbook


def custom_check(ws, ref, spec, task_dir=None):
    task = Path(task_dir).name
    if task not in custom_modules:
        return original_custom(ws, ref, spec, task_dir=task_dir)
    checks = custom_modules[task].check(ws, ref)
    return (
        all(check['passed'] for check in checks),
        '; '.join(check['name'] + ': ' + str(check['detail']) for check in checks),
    )


def unwrap(text: str) -> str:
    lines = []
    block = re.compile(r'^\s*(?:#{1,6}\s|[-*+•]\s|\d+[.)]\s|\||>)')
    for line in text.splitlines():
        previous = lines[-1].strip() if lines else ''
        if (
            previous and re.match(r'^\s*[a-z(]', line)
            and not block.match(line) and not block.match(previous)
            and not re.search(r'[.!?;:|]\**\s*$', previous)
        ):
            lines[-1] += ' ' + line.strip()
        else:
            lines.append(line)
    return '\n'.join(lines)


def sentence_check(ws, ref, spec):
    path = base.find_file(ws, spec['path'])
    if not path:
        return False, 'output file missing'
    sentences = base.split_sentences(unwrap(base.read_text(path)))
    required = spec.get('all', [])
    forbidden = spec.get('none', [])
    window = max(1, int(spec.get('window', 1)))
    spans = [
        ' '.join(sentences[i:i + size])
        for size in range(1, window + 1)
        for i in range(len(sentences) - size + 1)
    ]
    for sentence in spans:
        if all(re.search(p, sentence, re.I) for p in required) and not any(
            re.search(p, sentence, re.I) for p in forbidden
        ):
            return True, f'sentence: {sentence[:160]!r}'
    return False, f'no single sentence matches all of {required}' + (
        f' without {forbidden}' if forbidden else ''
    )


def normalized(value) -> str:
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


def component_totals(workbook, target: str, year: str):
    for sheet in workbook:
        rows = list(sheet.values)
        for index, row in enumerate(rows):
            names = [normalized(value) for value in row]
            identifiers = [j for j, name in enumerate(names) if name in ('contract', 'contractid', 'contractnumber')]
            components = [j for j, name in enumerate(names) if name == 'component']
            revenues = [j for j, name in enumerate(names) if name in (
                'revenuerecognized' + year, 'revenuerecognizedin' + year, year + 'revenuerecognized',
            )]
            if len(identifiers) != 1 or len(components) != 1 or len(revenues) != 1:
                continue
            key, component, revenue = identifiers[0], components[0], revenues[0]
            parts = [
                (normalized(record[component]), base.cell_num(record[revenue]))
                for record in rows[index + 1:] if normalized(record[key]) == target
            ]
            if len(parts) < 2 or any(not name or amount is None for name, amount in parts):
                continue
            if len({name for name, _ in parts}) != len(parts):
                continue
            yield sheet.title, len(parts), sum(amount for _, amount in parts)


def value_check(ws, ref, spec):
    original = base.c_xlsx_value_present(ws, ref, spec)
    if original[0]:
        return original
    task = Path(ref).parent.name
    if task == 'complaints-summary' and spec.get('name') == 'worst month total':
        return base.c_xlsx_value_present(ws, ref, {**spec, 'near_text': 'all complaints'})
    if task != 'deferred-revenue-schedule' or spec.get('name') != 'upgraded contract':
        return original
    path = base.find_file(ws, spec['path'])
    if not path:
        return original
    periods = json.loads((Path(ref) / 'notes.json').read_text())['recognized_by_month']
    years = {str(month).split('-')[0] for month in periods}
    if len(years) != 1:
        return original
    year = next(iter(years))
    expected = float(spec['expected'])
    workbook = openpyxl.load_workbook(base.recalculated_workbook(path), data_only=True)
    for sheet, count, total in component_totals(workbook, normalized(spec['near_text']), year):
        if abs(total - expected) <= max(abs(expected) * float(spec.get('rel_tol', 0.01)), 0.01):
            return True, f'{sheet}: {count} distinct components sum to {total} recognized in {year}'
    return original


base.c_custom = custom_check
base.CHECKS['text_sentence_matches'] = sentence_check
base.CHECKS['xlsx_value_present'] = value_check


def unreadable_workbook(ws, task):
    inspected = set()
    for check in task.get('checks', []):
        pattern = check.get('path', '')
        if not pattern.lower().endswith('.xlsx'):
            continue
        path = base.find_file(ws, pattern)
        if not path or path in inspected:
            continue
        inspected.add(path)
        try:
            with zipfile.ZipFile(path) as archive:
                member = archive.testzip()
                if member:
                    raise zipfile.BadZipFile('Bad CRC-32 for member ' + member)
            workbook = openpyxl.load_workbook(path, data_only=False)
            workbook.close()
        except (zipfile.BadZipFile, ParseError) as error:
            return f'{Path(path).name}: {type(error).__name__}: {error}'
    return None


def grade(task_id: str, ws: str) -> dict:
    # The package owns the frozen task definitions, never a caller-supplied scorer.
    task_id = Path(task_id).name
    task_dir = TASKS / task_id
    task = base.yaml.safe_load((task_dir / 'task.yaml').read_text())
    error = unreadable_workbook(ws, task)
    if error:
        return {
            'task': task_id, 'passed': False, 'grader_errors': [],
            'checks': [{'name': 'deliverable readable', 'type': 'artifact_readability',
                        'required': True, 'passed': False, 'detail': error}],
        }
    return base.grade(str(task_dir), ws)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task')
    parser.add_argument('workspace')
    args = parser.parse_args()
    print(json.dumps(grade(args.task, args.workspace), indent=2))
