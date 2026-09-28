"""bench/triage.py: metrics, the logistic model, leakage-safe training rows, panel features, grouped folds, the
probes, and the artifact layer end to end on a synthetic run directory (read-only on the workspace)."""
import hashlib, json, math, os, random, shutil, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
import triage as tr  # noqa: E402


def chk(name, passed, type_='text_contains_all', required=True):
    return {'name': name, 'passed': passed, 'required': required, 'type': type_}


def attempt(task, harness, run, checks, passed=None, raw_passed=None, src=None):
    a = {'task': task, 'harness': harness, 'run': run, 'run_id': f'{task}__{harness}__r{run}', 'checks': checks,
         'passed': all(c['passed'] for c in checks if c['required']) if passed is None else passed,
         'exit_code': 0, 'timed_out': False, 'source_sha256': src or f'{task}-{harness}-{run}'}
    a['raw_passed'] = a['passed'] if raw_passed is None else raw_passed
    return a


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        f.write(text)


def tree_hash(d):
    h = hashlib.sha256()
    for base, _, files in sorted(os.walk(d)):
        for f in sorted(files):
            p = os.path.join(base, f)
            h.update(os.path.relpath(p, d).encode())
            with open(p, 'rb') as fh:
                h.update(fh.read())
    return h.hexdigest()


class Metrics(unittest.TestCase):
    def test_auc(self):
        self.assertEqual(tr.auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]), 1.0)
        self.assertEqual(tr.auc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]), 0.0)
        self.assertEqual(tr.auc([0.5] * 4, [0, 1, 0, 1]), 0.5)
        self.assertIsNone(tr.auc([0.1, 0.2], [1, 1]))

    def test_precision_at_ties_in_expectation(self):
        self.assertEqual(tr.precision_at([3, 2, 1], [1, 0, 1], 1), 1.0)
        self.assertAlmostEqual(tr.precision_at([1, 1, 1, 1], [1, 0, 0, 0], 2), 0.25)
        self.assertAlmostEqual(tr.precision_at([2, 1, 1], [1, 1, 0], 2), 0.75)

    def test_cluster_bootstrap_brackets_the_estimate(self):
        y = [1, 0] * 20
        s = [0.9 if t else 0.1 for t in y]
        s[0], s[1] = 0.1, 0.9  # one inversion so the interval is not a point
        groups = [f'g{i // 4}' for i in range(len(y))]
        lo, hi = tr.cluster_bootstrap(groups, lambda idx: tr.auc([s[i] for i in idx], [y[i] for i in idx]), reps=300)
        est = tr.auc(s, y)
        self.assertLessEqual(lo, est)
        self.assertGreaterEqual(hi, est)


class Model(unittest.TestCase):
    def test_logreg_learns_direction(self):
        rng = random.Random(1)
        X, y = [], []
        for _ in range(400):
            a, b = rng.gauss(0, 1), rng.gauss(0, 1)
            X.append([a, b])
            y.append(1 if rng.random() < 1 / (1 + math.exp(-(2 * a - 1 * b))) else 0)
        m = tr.fit_logreg(X, y, lam=1.0)
        self.assertGreater(m['w'][0], 0.5)
        self.assertLess(m['w'][1], -0.2)
        p = tr.predict(m, [[2, 0], [-2, 0]])
        self.assertGreater(p[0], p[1])

    def test_constant_feature_is_harmless(self):
        m = tr.fit_logreg([[1.0, 0.0], [1.0, 1.0], [1.0, 2.0], [1.0, 3.0]], [0, 0, 1, 1])
        self.assertTrue(all(math.isfinite(w) for w in m['w']))

    def test_model_cols_select_features(self):
        m = tr.fit_logreg([[0.0], [1.0], [2.0], [3.0]], [0, 0, 1, 1])
        m['cols'] = [2]
        self.assertEqual(tr.model_x(m, [9, 9, 3.0]), [3.0])
        self.assertEqual(len(tr.model_predict(m, [[0, 0, 0.0], [0, 0, 3.0]])), 2)

    def test_grouped_folds_partition_tasks(self):
        rows = [{'task': f't{i % 7}', 'label': i % 2, 'x': [0.0]} for i in range(40)]
        for seed in range(3):
            folds = tr._folds(rows, 5, seed)
            seen = [t for f in folds for t in f]
            self.assertEqual(sorted(seen), sorted({r['task'] for r in rows}))
            self.assertEqual(len(seen), len(set(seen)))

    def test_cv_never_trains_on_the_held_out_task(self):
        # the single feature is the task's index: the stub model remembers what it was trained on and the stub
        # predict fails if asked about a task it saw
        from unittest import mock
        rows = [{'task': f't{t}', 'label': (t + j) % 2, 'x': [float(t)]} for t in range(12) for j in range(3)]

        def fit(X, y, lam=1.0):
            return {'seen': {x[0] for x in X}}

        def pred(m, X):
            for x in X:
                assert x[0] not in m['seen'], f'task {x[0]} leaked into its own training fold'
            return [0.5] * len(X)
        with mock.patch.object(tr, 'fit_logreg', fit), mock.patch.object(tr, 'predict', pred):
            p = tr.cv_predict(rows, repeats=3)
            n, _ = tr.nested_predict(rows, ['f'], configs=[('only', None, 1.0)], repeats=2)
        self.assertEqual(len(p), len(rows))
        self.assertEqual(len(n), len(rows))


class Features(unittest.TestCase):
    def test_training_rows_use_raw_view_and_frozen_label(self):
        # raw (snapshot) verdicts: memo check failed; frozen (published) verdicts: everything passes
        raw = attempt('t', 'codex-sol', 1, [chk('memo', False), chk('file', True, 'file_exists')], src='s1')
        raw_other = attempt('t', 'proto-x', 1, [chk('memo', False), chk('file', True, 'file_exists')], src='s2')
        pub = attempt('t', 'codex-sol', 1, [chk('memo', True), chk('file', True, 'file_exists')],
                      raw_passed=False, src='s1')
        # a frozen-only failure on a raw pass must never become a training row
        pub2 = attempt('u', 'codex-sol', 1, [chk('x', False)], raw_passed=True, src='s3')
        raw2 = attempt('u', 'codex-sol', 1, [chk('x', True)], src='s3')
        rows = tr.training_rows([pub, pub2], [raw, raw_other, raw2], None, None)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        fi = {f: i for i, f in enumerate(tr.FEATURES)}
        self.assertEqual(r['label'], 1)
        self.assertEqual(r['x'][fi['near_miss']], 1.0)
        self.assertEqual(r['x'][fi['panel_pass_other']], 0.0)   # the raw panel, not the frozen pass
        self.assertEqual(r['x'][fi['fam_text']], 1.0)

    def test_redesigned_check_labelled_only_when_attempt_flips(self):
        raw = attempt('t', 'codex-sol', 1, [chk('old name', False)], src='s1')
        flipped = attempt('t', 'codex-sol', 1, [chk('new name', True)], raw_passed=False, src='s1')
        self.assertEqual([r['label'] for r in tr.training_rows([flipped], [raw], None, None)], [1])
        still = attempt('t', 'codex-sol', 1, [chk('new name', False)], raw_passed=False, src='s1')
        self.assertEqual(tr.training_rows([still], [raw], None, None), [])

    def test_ranking_rows_panel_counts(self):
        att = [attempt('t', 'a', 1, [chk('c', False), chk('d', True)]),
               attempt('t', 'a', 2, [chk('c', False), chk('d', True)]),
               attempt('t', 'b', 1, [chk('c', True), chk('d', True)])]
        rows = tr.ranking_rows(att, None, None)
        self.assertEqual(len(rows), 2)
        fi = {f: i for i, f in enumerate(tr.FEATURES)}
        r = rows[0]
        self.assertEqual(r['panel_counts'], (0, 1, 1, 1))
        self.assertEqual(r['x'][fi['same_system_pass']], 0.0)
        self.assertEqual(r['x'][fi['other_system_pass']], 1.0)
        self.assertAlmostEqual(r['x'][fi['panel_pass_other']], 0.5)

    def test_queue_ranks_product_and_task_view(self):
        att = [attempt('t', 'a', 1, [chk('c', False)]), attempt('u', 'a', 1, [chk('c', False), chk('d', False)])]
        rows = tr.ranking_rows(att, None, None)
        m = tr.fit_logreg([[0.0] * len(tr.FEATURES)] * 2, [0, 1])
        q = tr.build_queue(rows, [0.6, 0.9, 0.5], m)
        self.assertEqual([a['attempt'] for a in q], ['t__a__r1', 'u__a__r1'])   # 0.6 > 0.9 * 0.5
        self.assertAlmostEqual(q[1]['score'], 0.45)
        self.assertEqual(q[1]['checks'][0]['check'], 'c')                       # checks ranked inside
        self.assertEqual([t['task'] for t in tr.task_queue(q)], ['t', 'u'])


class Probes(unittest.TestCase):
    def test_collapse_ws_and_text_normalise(self):
        self.assertEqual(tr.probe_collapse_ws(b'a refund\nwithin 30 days.\n\nNext para.'),
                         b'a refund within 30 days.\n\nNext para.')
        self.assertEqual(tr.probe_text_normalise('**30 days** — it’s'.encode()), b"30 days - it's")

    def test_csv_header_probe(self):
        out = tr.probe_csv_headers(b'Invoice,Amount (USD)\n1,2\n', ['invoice', 'amount'])
        self.assertTrue(out.startswith(b'Invoice,amount'))
        self.assertIsNone(tr.probe_csv_headers(b'invoice,amount\n1,2\n', ['invoice', 'amount']))

    def test_spec_probes(self):
        p = tr.spec_probes({'type': 'xlsx_value_present', 'expected': 1234.5, 'near_text': 'total'})
        self.assertNotIn('near_text', p['value_elsewhere'])
        self.assertGreater(p['value_rounded']['rel_tol'], 0.0)
        self.assertEqual(tr.spec_probes({'type': 'csv_values_match', 'numeric': True}), {})


TASK_YAML = """id: tiny-memo
category: drafting
ask: Write memo.md for the owner.
checks:
  - {type: file_exists, name: memo exists, path: memo.md}
  - {type: text_sentence_matches, name: refund window, path: memo.md, all: ['refund', '30 days']}
  - {type: text_contains_all, name: store credit, path: memo.md, phrases: ['store credit']}
"""
MEMO = 'Customers may ask for a refund\nwithin 30 days of delivery.\n'


class ArtifactLayer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='triage-test-')
        self.tasks = os.path.join(self.tmp, 'tasks')
        write(os.path.join(self.tasks, 'tiny-memo', 'task.yaml'), TASK_YAML)
        os.makedirs(os.path.join(self.tasks, 'tiny-memo', 'reference'))
        self.run = os.path.join(self.tmp, 'results', 'lbl')
        for i in (1, 2):
            d = os.path.join(self.run, f'tiny-memo__h__r{i}')
            write(os.path.join(d, 'ws', 'memo.md'), MEMO)
            res = {'run_id': f'tiny-memo__h__r{i}', 'task': 'tiny-memo', 'harness': 'h', 'run': i, 'passed': False,
                   'exit_code': 0, 'timed_out': False,
                   'checks': [chk('memo exists', True, 'file_exists'),
                              chk('refund window', False, 'text_sentence_matches'),
                              chk('store credit', False)]}
            write(os.path.join(d, 'result.json'), json.dumps(res))
        m = tr.fit_logreg([[0.0] * len(tr.FEATURES)] * 2, [0, 1])
        m.update({'features': tr.FEATURES, 'cols': None})
        self.model = os.path.join(self.tmp, 'model.json')
        write(self.model, json.dumps({'check_model': m}))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_probe_flags_wrapped_sentence_and_leaves_ws_alone(self):
        view = tr.open_view('current', self.tasks)
        ws = os.path.join(self.run, 'tiny-memo__h__r1', 'ws')
        before = tree_hash(self.run)
        pr = tr.artifact_probe(view, 'tiny-memo', {'name': 'refund window'}, ws)
        self.assertTrue(pr['reproduced'])
        self.assertIn('md_unwrap', pr['transform_flips'])
        self.assertIn('collapse_ws', pr['probe_flips'])
        real = tr.artifact_probe(view, 'tiny-memo', {'name': 'store credit'}, ws)
        self.assertTrue(real['reproduced'])
        self.assertEqual(real['transform_flips'], [])
        self.assertEqual(real['probe_flips'], [])
        self.assertEqual(tree_hash(self.run), before)

    def test_rank_run_end_to_end(self):
        out = os.path.join(self.tmp, 'out')
        before = tree_hash(self.run)
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            rc = tr.main(['rank', '--run', self.run, '--tasks-root', self.tasks, '--model', self.model, '--out', out])
        self.assertEqual(rc, 0)
        self.assertEqual(tree_hash(self.run), before)
        with open(os.path.join(out, 'queue.json')) as f:
            q = json.load(f)
        self.assertEqual(len(q), 2)
        for a in q:
            by = {c['check']: c for c in a['checks']}
            self.assertEqual(by['refund window']['tier'], 1)
            self.assertEqual(by['store credit']['tier'], 3)
            self.assertEqual(a['tier'], 3)   # the verdict needs every failure to be an error
            self.assertIn('md_unwrap', by['refund window']['reason'])
        for f in ('queue.csv', 'queue.md', 'tasks.csv'):
            self.assertTrue(os.path.isfile(os.path.join(out, f)))


if __name__ == '__main__':
    unittest.main()
