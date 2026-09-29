import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
import run
import grade
import export_campaign
import yaml


class ReleaseTests(unittest.TestCase):
    def test_detail_analysis_reconciles(self):
        from collections import Counter, defaultdict
        rows = [json.loads(line) for line in (ROOT / 'results/latest/attempts.jsonl').read_text().splitlines()]
        expected = {'proto-deepseek': {0: 3, 1: 8, 2: 29, 3: 147},
                    'codex-sol': {0: 13, 1: 16, 2: 17, 3: 141}}
        contract_counts = {
            'proto-deepseek': {'accepted': 507, 'checks_passed': 3698, 'checks_total': 3801,
                               'single_check_failures': 34, 'failed': 54},
            'codex-sol': {'accepted': 473, 'checks_passed': 3558, 'checks_total': 3801,
                          'single_check_failures': 39, 'failed': 88},
        }
        mean_fractions = {'proto-deepseek': 0.9733780380839204, 'codex-sol': 0.9441802157042799}
        outside_passes = {'proto-deepseek': 377, 'codex-sol': 380}
        pairs = {}
        for system in expected:
            selected = [row for row in rows if row['harness'] == system]
            required = [[check for check in row['checks'] if check['required']] for row in selected]
            self.assertEqual({
                'accepted': sum(row['passed'] for row in selected),
                'checks_passed': sum(check['passed'] for checks in required for check in checks),
                'checks_total': sum(len(checks) for checks in required),
                'single_check_failures': sum(sum(not check['passed'] for check in checks) == 1
                                             for checks in required),
                'failed': sum(not row['passed'] for row in selected),
            }, contract_counts[system])
            mean_fraction = sum(sum(check['passed'] for check in checks) / len(checks)
                                for checks in required) / len(selected)
            self.assertAlmostEqual(mean_fraction, mean_fractions[system], places=12)
            outside = [row for row in selected if row['category'] not in ('reports', 'drafting')]
            self.assertEqual(len({row['task'] for row in outside}), 138)
            self.assertEqual(len(outside), 414)
            self.assertEqual(sum(row['passed'] for row in outside), outside_passes[system])
            grouped = defaultdict(list)
            for row in selected:
                grouped[row['task']].append(row)
            self.assertEqual(Counter(sum(r['passed'] for r in group) for group in grouped.values()), expected[system])
            pairs[system] = {(r['task'], r['run']): r['passed'] for r in selected}
        matrix = Counter((value, pairs['codex-sol'][key]) for key, value in pairs['proto-deepseek'].items())
        self.assertEqual(matrix, {(True, True): 431, (True, False): 76, (False, True): 42, (False, False): 12})
        sys.path.insert(0, str(ROOT / 'docs'))
        from paper_details import detail_tables
        spec = (ROOT / 'SPEC.md').read_text()
        for marker, output in detail_tables().items():
            self.assertIn(output, spec)
            self.assertNotIn(marker, spec)

    def test_paper_layout_and_embedded_typography(self):
        from pypdf import PdfReader
        reader = PdfReader(ROOT / 'docs/business-harness-bench-spec.pdf')
        self.assertGreaterEqual(len(reader.pages), 7)
        self.assertLessEqual(len(reader.pages), 11)
        self.assertIn('LaTeX', str(reader.metadata.get('/Creator')))
        self.assertIn('xdvipdfmx', str(reader.metadata.get('/Producer')))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for heading in ['Introduction', 'Benchmark design', 'Evaluation protocol',
                        'Category results', 'Worked example', 'Scoring integrity', 'Conclusion',
                        'Formal definitions', 'References']:
            self.assertIn(heading, text)
        for page in reader.pages:
            self.assertGreater(len(page.extract_text()), 450, 'Unexpected near-empty page')
        embedded = set()
        for page in reader.pages:
            for ref in page['/Resources']['/Font'].get_object().values():
                font = ref.get_object()
                candidates = [font] + [item.get_object() for item in font.get('/DescendantFonts', [])]
                for candidate in candidates:
                    if 'Libertinus' in str(candidate.get('/BaseFont')) and '/FontDescriptor' in candidate:
                        descriptor = candidate['/FontDescriptor'].get_object()
                        self.assertTrue('/FontFile2' in descriptor or '/FontFile3' in descriptor)
                        embedded.add(str(candidate['/BaseFont']))
        self.assertGreaterEqual(len(embedded), 2, 'Regular and bold must both be embedded')
        first_page = reader.pages[0].extract_text()
        for row in json.loads((ROOT / 'results/latest/summary.json').read_text()):
            for passed in row['by_repetition'].values():
                self.assertIn(f'{passed / 187 * 100:.1f}', first_page)

    def test_frozen_scorer_and_paper_agree(self):
        from frozen_release import verify
        verify()
        from pypdf import PdfReader
        text = '\n'.join(page.extract_text() for page in PdfReader(ROOT / 'docs/business-harness-bench-spec.pdf').pages)
        self.assertIn('90.4%', text)
        self.assertIn('84.3%', text)
        self.assertIn('507', text)
        self.assertIn('473', text)
        self.assertNotIn('2,244', text)

    def test_inventory(self):
        for track, count in [('desk', 187), ('build', 20)]:
            files = list((ROOT / 'tasks' / track).glob('*/task.yaml'))
            self.assertEqual(len(files), count)
            for path in files:
                task = yaml.safe_load(path.read_text())
                self.assertEqual(task['id'], path.parent.name)
                self.assertTrue(task['ask'].strip())
                self.assertTrue((path.parent / 'gen.py').is_file())
                if track == 'desk':
                    self.assertTrue((path.parent / 'workspace').is_dir())
                    self.assertTrue((path.parent / 'reference_solution').is_dir())
                    self.assertTrue(task['checks'])
                else:
                    self.assertEqual(len(task['changes']), 3)
                    for rel in task['seed'] + task['changes'] + [task['checklist'], task['reference']]:
                        self.assertTrue((path.parent / rel).is_file(), str(path.parent / rel))

    def test_published_ledger(self):
        rows = [json.loads(s) for s in (ROOT / 'results/latest/attempts.jsonl').read_text().splitlines()]
        expected = json.loads((ROOT / 'results/latest/summary.json').read_text())
        self.assertEqual(export_campaign.aggregate(rows), expected)
        self.assertEqual(len({r['run_id'] for r in rows}), 1122)
        self.assertEqual([s['passed'] for s in expected], [507, 473])
        self.assertTrue(all('work_dir' not in r and len(r['source_sha256']) == 64 for r in rows))

    def test_incomplete_arm_is_rejected(self):
        rows = [json.loads(s) for s in (ROOT / 'results/latest/attempts.jsonl').read_text().splitlines()]
        with self.assertRaises(ValueError):
            export_campaign.aggregate(rows[1:])

    def test_real_subprocess_runner_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='bench-smoke-') as directory:
            root = Path(directory)
            taskdir = root / 'tasks' / 'simple'
            (taskdir / 'workspace').mkdir(parents=True)
            (taskdir / 'reference').mkdir()
            (taskdir / 'task.yaml').write_text(yaml.safe_dump(dict(id='simple', category='reformatting',
                ask='Write output.csv with the amount.', checks=[dict(name='deliverable', type='csv_columns',
                    path='output.csv', columns=['amount'])])))
            (root / 'bench').mkdir()
            (root / 'bench/prices.json').write_text('{}')
            (root / 'harnesses').mkdir()
            adapter = root / 'harnesses/smoke.sh'
            adapter.write_text('#!/bin/sh\nprintf "amount\\n7\\n" > "$1/output.csv"\n')
            adapter.chmod(0o755)
            with patch.object(run, 'ROOT', str(root)):
                result = run.run_one(str(root / 'tasks'), 'simple', 'smoke', 1, 'smoke-test', 5)
                self.assertTrue(result['passed'])
                self.assertEqual(result['exit_code'], 0)
                with self.assertRaises(FileExistsError):
                    run.run_one(str(root / 'tasks'), 'simple', 'smoke', 1, 'smoke-test', 5)

    def test_reference_positive_and_empty_negative(self):
        task = ROOT / 'tasks/desk/address-standardize'
        self.assertTrue(grade.grade(str(task), str(task / 'reference_solution'))['passed'])
        self.assertFalse(grade.grade(str(task), str(task / 'workspace'))['passed'])


if __name__ == '__main__':
    unittest.main()
