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
        self.assertEqual(len({r['run_id'] for r in rows}), 2244)
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
