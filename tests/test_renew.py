"""Renewable-benchmark tooling (bench/renew.py). No model calls, no LibreOffice; about ten seconds."""
import contextlib, io, json, os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
import envelope  # noqa: E402
import renew  # noqa: E402

DESK = ROOT / 'tasks' / 'desk'


def cli(mod, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main([str(a) for a in args])
    return rc, buf.getvalue()


def attempt(task, harness, run, failed=()):
    names = ['a', 'b', 'c']
    return {'task': task, 'harness': harness, 'run': run, 'category': 'reports', 'passed': not failed,
            'checks': [{'name': n, 'type': 'csv_values_match', 'required': True, 'passed': n not in failed} for n in names]}


def fixture_ledger(path):
    rows = []
    for h in ('sys-a', 'sys-b'):
        for r in (1, 2, 3):
            rows.append(attempt('all-pass', h, r))
            rows.append(attempt('one-miss', h, r, failed=('b',) if (h, r) == ('sys-a', 2) else ()))
            rows.append(attempt('mixed', h, r, failed=('a', 'c') if r > 1 else ()))
            rows.append(attempt('never', h, r, failed=('c',)))
    with open(path, 'w') as f:
        f.writelines(json.dumps(x) + '\n' for x in rows)


class Saturation(unittest.TestCase):
    def test_classes_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            led = Path(d) / 'ledger.jsonl'
            fixture_ledger(led)
            rows = {r['task']: r for r in renew.saturation_table(str(led), str(Path(d) / 'tasks'), 1)}
            self.assertEqual(rows['all-pass']['class'], 'saturated')
            self.assertEqual(rows['one-miss']['class'], 'near-saturated')
            self.assertEqual(rows['mixed']['class'], 'informative')
            self.assertEqual(rows['never']['class'], 'never-passed')
            self.assertEqual(rows['one-miss']['checks_never_failed'], 2)
            self.assertEqual(rows['one-miss']['systems']['sys-a'], {'passed': 2, 'n': 3})
            self.assertEqual(rows['all-pass']['route'], 'none')        # no generator in the fixture tree
            rows0 = {r['task']: r for r in renew.saturation_table(str(led), str(Path(d) / 'tasks'), 0)}
            self.assertEqual(rows0['one-miss']['class'], 'informative')

    def test_a_failed_required_check_is_not_saturation_even_if_passed_is_true(self):
        s = renew.ledger_stats([attempt('t', 'x', 1), {**attempt('t', 'x', 2, failed=('a',)), 'passed': True}])
        self.assertEqual(renew.classify(s['t']), 'near-saturated')

    def test_published_ledger(self):
        rows = renew.saturation_table(renew.LEDGER, str(DESK), 1)
        self.assertEqual(sum(r['class'] == 'saturated' for r in rows), 116)   # CONTEXT section 4
        self.assertEqual({r['route'] for r in rows} - {'switches+seed', 'knobs+seed', 'seed (shadow copy)'}, set())

    def test_routes(self):
        self.assertEqual(renew.renewal_route(str(DESK / 'project-margin')), 'switches+seed')
        self.assertEqual(renew.renewal_route(str(DESK / 'address-standardize')), 'seed (shadow copy)')


class Verdict(unittest.TestCase):
    types = {'total': 'xlsx_value_present', 'errors': 'xlsx_no_errors', 'memo': 'text_contains_all'}

    def test_cases(self):
        v = renew.verdict
        self.assertEqual(v(True, set(), self.types, False, None), 'VERIFIED')
        self.assertEqual(v(True, set(), self.types, True, None), 'FAIL (untouched workspace passes)')
        # the canonical task fails the same workbook checks here: environment, not the variant
        self.assertEqual(v(False, {'total'}, self.types, False, {'total', 'errors'}), renew.ENV_UNVERIFIED)
        # the canonical task passes: the variant is broken
        self.assertEqual(v(False, {'total'}, self.types, False, set()), 'FAIL (reference solution fails)')
        # a text check is never put down to the spreadsheet engine
        self.assertEqual(v(False, {'memo'}, self.types, False, {'memo'}), 'FAIL (reference solution fails)')
        self.assertEqual(v(False, {'total'}, self.types, False, None), 'FAIL (reference solution fails)')


class Guards(unittest.TestCase):
    def test_root_outside_tasks(self):
        with self.assertRaises(SystemExit):
            renew.check_root(str(DESK / 'project-margin' / 'x'), str(DESK))
        with self.assertRaises(SystemExit):
            renew.check_root(str(ROOT / 'tasks' / 'sealed'), str(DESK))

    def test_unknown_knob_refused(self):
        with tempfile.TemporaryDirectory() as d:
            g = renew.Generator('project-margin', scratch=d)
            self.assertEqual(g.knobs(), [])
            with self.assertRaises(SystemExit):
                g.generate(os.path.join(d, 'out'), seed=1, knobs={'rows': 300})
            with self.assertRaises(SystemExit):
                cli(renew, 'search', '--task', 'project-margin', '--root', Path(d) / 's', '--knob', 'rows=100,300')

    def test_parse(self):
        self.assertEqual(renew.parse_seeds('default,3'), [None, 3])
        self.assertEqual(renew.parse_knobs(['--rows=10,20']), {'rows': ['10', '20']})


def load(p):
    with open(p) as f:
        return json.load(f)


def tree_hash(d):
    return envelope.sha_tree(str(d))


class SearchAndSeal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = Path(cls.tmp.name)
        cls.pub_before = tree_hash(DESK / 'project-margin')
        cls.addr_before = tree_hash(DESK / 'address-standardize')
        rc, cls.search_out = cli(renew, 'search', '--task', 'project-margin', '--root', cls.d / 'search',
                                 '--seeds', 'default,5', '--design', 'single', '--boot', 20)
        assert rc == 0, cls.search_out
        cls.man = load(cls.d / 'search' / 'manifest.json')
        cls.pred_path = cls.d / 'search' / 'predictions' / 'project-margin.json'
        rc, cls.seal_out = cli(renew, 'seal', '--task', 'project-margin', '--task', 'address-standardize',
                               '--root', cls.d / 'sealed', '--n', 1, '--seeds', '123457,123458', '--boot', 20)
        assert rc == 0, cls.seal_out
        cls.sealed = load(cls.d / 'sealed' / 'manifest.json')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_published_folders_untouched(self):
        self.assertEqual(tree_hash(DESK / 'project-margin'), self.pub_before)
        self.assertEqual(tree_hash(DESK / 'address-standardize'), self.addr_before)

    def test_search_settings_and_predictions(self):
        rows = self.man['variants']
        self.assertEqual(len(rows), 2 * 6)                           # 2 seeds x (canonical + 5 single off-sets)
        canon = next(r for r in rows if r['canonical_setting'])
        self.assertEqual(canon['predicted_delta']['estimate'], 0.0)
        for r in rows:
            if r['effective_off']:
                self.assertFalse(r['harder_eligible'])
                self.assertLess(r['predicted_delta']['estimate'], 0)  # removing pitfalls predicts easier
        self.assertIsNone(self.man['proposal'])                       # no knob can make it harder
        self.assertIn('No credibly harder setting', self.search_out)
        self.assertEqual(self.man['problems'], [])

    def test_predictions_register_and_score_with_envelope(self):
        doc = load(self.pred_path)
        self.assertEqual(doc['kind'], 'envelope-predictions')
        self.assertEqual(envelope.content_sha(doc), doc['sha256'])
        self.assertEqual(doc['manifest_sha256'], envelope.sha_file(str(self.d / 'search' / 'manifest.json')))
        reg = self.d / 'registry.jsonl'
        rc, _ = cli(envelope, 'register', self.pred_path, '--registry', reg)
        self.assertEqual(rc, 0)
        res = self.d / 'results'
        start = envelope.parse_utc(json.loads(reg.read_text())['created_utc']) + 60
        for i, c in enumerate(c for c in doc['cells']):
            rd = res / f"{c['dir']}__{c['system']}__r1"
            rd.mkdir(parents=True)
            (rd / 'result.json').write_text(json.dumps({'task': c['dir'], 'harness': c['system'], 'run': 1,
                                                        'passed': True, 'started_utc': envelope.iso(start + i)}))
        rc, out = cli(envelope, 'score', '--predictions', self.pred_path, '--results', res, '--registry', reg)
        self.assertEqual(rc, 0, out)
        self.assertIn('Forecast score: project-margin', out)

    def test_sealed_manifest(self):
        vs = self.sealed['variants']
        self.assertEqual([v['task'] for v in vs], ['project-margin', 'address-standardize'])
        for v in vs:
            self.assertEqual(v['verification']['status'], 'VERIFIED')
            self.assertTrue(v['answer_changed'])
            self.assertLessEqual(abs(v['predicted_delta']['estimate']), 0.10)
            self.assertTrue((self.d / 'sealed' / v['dir'] / 'task.yaml').is_file())
            self.assertFalse((self.d / 'sealed' / v['dir'] / 'gen.py').exists())
            for k in ('task_yaml', 'checks', 'reference', 'reference_solution', 'workspace'):
                self.assertIsNotNone(v['sha256'][k])
        self.assertEqual(self.sealed['tasks']['address-standardize']['route'], 'seed (shadow copy)')
        pub = (self.d / 'sealed' / 'commitments.json').read_text()
        for v in vs:
            self.assertNotIn(str(v['seed']), pub)                     # the public file does not reveal seeds
            self.assertIn(v['commitment'], pub)
        doc = load(self.d / 'sealed' / 'predictions' / 'address-standardize.json')
        self.assertEqual({c['dir'] for c in doc['cells']}, {vs[1]['dir']})

    def test_unmatched_difficulty_is_rejected(self):
        root = self.d / 'strict'
        rc, out = cli(renew, 'seal', '--task', 'project-margin', '--root', root, '--n', 1, '--seeds', '123457',
                      '--tol', 0, '--no-verify', '--boot', 20)
        man = load(root / 'manifest.json')
        self.assertEqual(rc, 1)                                       # fewer variants than asked for
        self.assertEqual(man['variants'], [])
        self.assertIn('difficulty not matched', man['rejected'][0]['reason'])
        self.assertFalse((root / 'project-margin__r00').exists())

    def test_check_detects_tampering(self):
        rc, out = cli(renew, 'check', '--manifest', self.d / 'sealed' / 'manifest.json')
        self.assertEqual(rc, 0, out)
        v = self.sealed['variants'][0]
        f = next((self.d / 'sealed' / v['dir'] / 'workspace').rglob('*.*'))
        orig = f.read_bytes()
        try:
            f.write_bytes(orig + b' ')
            rc, out = cli(renew, 'check', '--manifest', self.d / 'sealed' / 'manifest.json')
            self.assertEqual(rc, 1)
            self.assertIn('workspace changed', out)
        finally:
            f.write_bytes(orig)


if __name__ == '__main__':
    unittest.main()
