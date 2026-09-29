from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
import export_desk_campaign as desk


class DeskCampaignTests(unittest.TestCase):
    def test_published_campaigns_verify(self):
        folders = sorted(p.parent for p in desk.DESK.glob('*/campaign.json'))
        self.assertTrue(folders)
        for folder in folders:
            with self.subTest(campaign=folder.name):
                desk.verify_campaign(folder)

    def test_2026_09_28_three_repetitions_and_scores(self):
        summary = desk.verify_campaign(desk.DESK / 'complete-desk-comparison-2026-09-28')
        self.assertEqual({s['harness']: (s['attempts'], s['passed'], s['raw_passed']) for s in summary}, {
            'proto-sol6-sub': (561, 495, 443),
            'codex-sol6': (561, 487, 440),
            'proto-deepseek-direct': (561, 502, 444),
        })

    def test_incomplete_matrix_is_rejected(self):
        rows = [{'harness': 'a', 'task': 'missing-task', 'run': 1, 'passed': True, 'raw_passed': True,
                 'cost_usd': None, 'wall_s': 1.0, 'usage': {}, 'timed_out': False, 'exit_code': 0,
                 'grader_error_count': 0, 'raw_grader_error_count': 0, 'category': 'reports'}]
        with self.assertRaises(ValueError):
            desk.aggregate(rows, ['a'], 1)


if __name__ == '__main__':
    unittest.main()
