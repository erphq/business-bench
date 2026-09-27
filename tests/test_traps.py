"""Trap switches, trap citations, the measurement graph, and the difficulty fit."""
import argparse, filecmp, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tasks' / 'lib'))
sys.path.insert(0, str(ROOT / 'bench'))
from bizgen.traps import TrapSet, add_trap_args, parse_trap_args, active_trap_text  # noqa: E402
from trap_links import citations, resolve, trap_links  # noqa: E402
import measure_graph  # noqa: E402
import difficulty  # noqa: E402

PM = ROOT / 'tasks' / 'desk' / 'project-margin'


def gen(*args):
    r = subprocess.run([sys.executable, str(PM / 'gen.py'), *args], capture_output=True, text=True)
    return r


def load(p):
    with open(p) as f:
        return yaml.safe_load(f)


def same_tree(a, b):
    c = filecmp.dircmp(a, b)
    if c.left_only or c.right_only:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, c.common_files, shallow=False)
    return not mismatch and not errors and all(same_tree(os.path.join(a, d), os.path.join(b, d)) for d in c.common_dirs)


class TrapSetTests(unittest.TestCase):
    def setUp(self):
        self.t = TrapSet({'a': '', 'b': '', 'c': ''}, {'z': ''}, {'a': 'b'})

    def test_default_is_canonical_and_all_on(self):
        self.assertTrue(self.t.canonical)
        self.assertTrue(all(self.t.on(n) for n in self.t.names))

    def test_switch_off_and_requirement_closure(self):
        v = self.t.with_off(['b'])
        self.assertEqual(v.off, frozenset({'a', 'b'}))   # a only exists inside b
        self.assertFalse(v.canonical)
        self.assertTrue(v.on('c') and v.on('z'))

    def test_fixed_and_unknown_cannot_be_switched(self):
        with self.assertRaises(ValueError):
            self.t.with_off(['z'])
        with self.assertRaises(ValueError):
            self.t.with_off(['nope'])
        with self.assertRaises(KeyError):
            self.t.on('typo')

    def test_active_trap_text(self):
        v = self.t.with_off(['c'])
        self.assertEqual(active_trap_text(['A', 'C', 'Z'], ['a', 'c', 'z'], v), ['A', 'Z'])

    def test_flags_never_write_over_the_task_folder(self):
        ap = argparse.ArgumentParser(); add_trap_args(ap)
        with self.assertRaises(SystemExit):
            parse_trap_args(ap.parse_args(['--traps-off', 'a']), self.t)
        with self.assertRaises(SystemExit):
            parse_trap_args(ap.parse_args(['--mutant', 'a', '--out', '/tmp/x']), self.t, mutants={})
        self.assertEqual(parse_trap_args(ap.parse_args(['--traps-off', 'c', '--out', '/tmp/x']), self.t).off,
                         frozenset({'c'}))


class TrapLinkTests(unittest.TestCase):
    NAMES = ['margins.xlsx exists', 'Cedar Point cost (unbilled time in, credits netted)', 'review list',
             'review list says why', 'memo names both loss-making jobs', 'page structure', 'row count']

    def test_citations(self):
        self.assertEqual(citations('x y (checks: A; B)'), ['A', 'B'])
        self.assertEqual(citations('x y (check: A)'), ['A'])
        self.assertEqual(citations('no citation here'), [])

    def test_resolve(self):
        self.assertEqual(resolve('Cedar Point cost', self.NAMES), (self.NAMES[1], 'ok'))
        self.assertEqual(resolve('review list', self.NAMES), ('review list', 'ok'))          # exact beats prefix
        self.assertEqual(resolve('memo names both loss-makers', self.NAMES)[1], 'ok')       # makers ~ making
        self.assertEqual(resolve('memo names the worst site', self.NAMES), (None, 'unresolved'))

    def test_parts_and_values(self):
        t = {'checks': [{'name': n, 'type': 'x'} for n in self.NAMES],
             'traps': ['a (checks: page structure: top donors; row count, 27 rows)']}
        cites = trap_links(t)[0]['cites']
        self.assertEqual([(c['check'], c['part'], c['status']) for c in cites],
                         [('page structure', 'top donors', 'ok'), ('row count', '27 rows', 'ok')])


class ProjectMarginSwitches(unittest.TestCase):
    """The retrofitted template generator: a copy reproduces the published answer, every variant keeps it,
    and every trap has a mutant. Written to temp folders; the task folder is never touched."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='pm-traps-')
        cls.decl = json.loads(gen('--list-traps').stdout)
        r = gen('--out', os.path.join(cls.tmp, 'canon'))
        assert r.returncode == 0, r.stderr

    def test_declaration_covers_every_trap_sentence(self):
        published = load(PM / 'task.yaml')
        self.assertEqual(len(self.decl['sentence_keys']), len(published['traps']))
        self.assertEqual(set(self.decl['sentence_keys']), set(self.decl['switchable']) | set(self.decl['fixed']))
        self.assertEqual(set(self.decl['mutants']), set(self.decl['sentence_keys']))

    def test_copy_reproduces_published_answer(self):
        canon = os.path.join(self.tmp, 'canon')
        self.assertTrue(same_tree(os.path.join(canon, 'reference'), PM / 'reference'))
        self.assertEqual(load(os.path.join(canon, 'task.yaml')),
                         load(PM / 'task.yaml'))

    def test_each_variant_keeps_the_answer_and_changes_the_workspace(self):
        canon = os.path.join(self.tmp, 'canon')
        base = load(os.path.join(canon, 'task.yaml'))
        for trap in self.decl['switchable']:
            out = os.path.join(self.tmp, 'v-' + trap)
            r = gen('--traps-off', trap, '--out', out)
            self.assertEqual(r.returncode, 0, r.stderr)
            v = load(os.path.join(out, 'task.yaml'))
            self.assertEqual(v['checks'], base['checks'], trap)
            self.assertIn(trap, v['variant']['traps_off'])
            self.assertTrue(same_tree(os.path.join(out, 'reference'), os.path.join(canon, 'reference')), trap)
            self.assertTrue(same_tree(os.path.join(out, 'reference_solution'),
                                      os.path.join(canon, 'reference_solution')), trap)
            self.assertFalse(same_tree(os.path.join(out, 'workspace'), os.path.join(canon, 'workspace')), trap)

    def test_mutants_write_a_deliverable(self):
        for trap in self.decl['mutants']:
            out = os.path.join(self.tmp, 'm-' + trap)
            r = gen('--mutant', trap, '--out', out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(out, 'margins.xlsx')) and os.path.isfile(os.path.join(out, 'memo.md')))

    def test_refuses_to_write_variant_into_task_folder(self):
        self.assertNotEqual(gen('--traps-off', 'drafts').returncode, 0)


class GraphAndDifficulty(unittest.TestCase):
    def test_graph_and_ledger_join(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, 't1'))
        with open(os.path.join(d, 't1', 'task.yaml'), 'w') as fh:
            yaml.safe_dump({'id': 't1', 'category': 'reports',
                            'traps': ['trap one (check: total)', 'trap two (checks: total; rows)', 'uncited'],
                            'checks': [{'type': 'file_exists', 'name': 'exists'},
                                       {'type': 'xlsx_value_present', 'name': 'total margin'},
                                       {'type': 'csv_row_count', 'name': 'rows'}]}, fh)
        g = measure_graph.build_graph(measure_graph.load_tasks(d), use_gen=False)
        cites = [(e['src'], e['dst']) for e in g['edges'] if e['rel'] == 'cites']
        self.assertEqual(len(cites), 3)
        led = os.path.join(d, 'ledger.jsonl')
        with open(led, 'w') as f:
            for i, (sysname, ok_rows) in enumerate([('s1', True), ('s1', False), ('s2', True)]):
                f.write(json.dumps({'task': 't1', 'harness': sysname, 'passed': ok_rows, 'checks': [
                    {'name': 'exists', 'passed': True, 'required': True},
                    {'name': 'total margin', 'passed': True, 'required': True},
                    {'name': 'rows', 'passed': ok_rows, 'required': True}]}) + '\n')
        g = measure_graph.join_ledger(g, led)
        by = {n['id']: n for n in g['nodes']}
        self.assertEqual(by['trap:t1:1']['ledger']['s1'], {'attempts': 2, 'bitten': 1, 'exclusive': 1})
        self.assertEqual(by['trap:t1:0']['ledger']['s1']['bitten'], 0)
        self.assertIn('Traps that cite no check: 1', measure_graph.report(g))

    def test_fit_recovers_direction(self):
        rng = np.random.default_rng(1)
        n_t, reps = 120, 6
        x = rng.normal(size=(n_t, 1))
        theta = np.array([1.0, 2.0])
        rows_S, rows_X, y = [], [], []
        for t in range(n_t):
            for s in range(2):
                for _ in range(reps):
                    p = 1 / (1 + np.exp(-(theta[s] - 1.5 * x[t, 0])))
                    rows_S.append(np.eye(2)[s]); rows_X.append(x[t]); y.append(float(rng.random() < p))
        beta = difficulty.fit(np.array(rows_S), np.array(rows_X), np.array(y), l2=0.01)
        self.assertGreater(beta[2], 0.8)             # harder feature recovered with the right sign
        self.assertGreater(beta[1], beta[0])         # stronger system recovered


if __name__ == '__main__':
    unittest.main()
