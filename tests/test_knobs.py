"""Difficulty knobs: the bizgen.knobs helper, a knobbed generator, and renew.py's use of them. No LibreOffice."""
import argparse, contextlib, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tasks' / 'lib'))
sys.path.insert(0, str(ROOT / 'bench'))
from bizgen.knobs import Knob, KnobSet, Settings, add_knob_args, parse_knob_args, record, steps, measure_value  # noqa: E402
from bizgen.traps import TrapSet, add_trap_args, parse_trap_args  # noqa: E402

DP = ROOT / 'tasks' / 'desk' / 'duplicate-payments'


def ks():
    return KnobSet(
        Knob('scale', 'scale', default=1, levels=(1, 2, 4), changes='more rows', measure='rows'),
        Knob('noise', 'noise', default=0.15, levels=(0.15, 0.3, 0.5), changes='messier names', measure='noise_rate'),
        Knob('trap_count.drafts', 'trap-count', default=1, levels=(1, 2, 3), changes='more drafts',
             measure='trap_instances.drafts'),
        Knob('cross_doc', 'cross-doc', default=0, levels=(0, 1), changes='rates in a second file', measure='documents'),
    )


def parse(argv, k=None):
    k = k or ks()
    ap = argparse.ArgumentParser(); add_knob_args(ap, k)
    return parse_knob_args(ap.parse_args(argv), k)


class Declaration(unittest.TestCase):
    def test_levels_start_at_default_and_increase(self):
        with self.assertRaises(ValueError):
            Knob('scale', 'scale', default=2, levels=(1, 2), changes='', measure='rows')
        with self.assertRaises(ValueError):
            Knob('scale', 'scale', default=1, levels=(1, 3, 2), changes='', measure='rows')

    def test_names_follow_kinds(self):
        with self.assertRaises(ValueError):
            Knob('rows', 'scale', default=1, levels=(1, 2), changes='', measure='rows')
        with self.assertRaises(ValueError):
            Knob('drafts', 'trap-count', default=1, levels=(1, 2), changes='', measure='x')
        with self.assertRaises(ValueError):
            Knob('scale', 'size', default=1, levels=(1, 2), changes='', measure='rows')
        self.assertEqual(Knob('trap_count.drafts', 'trap-count', default=1, levels=(1, 2), changes='',
                              measure='x').trap, 'drafts')
        with self.assertRaises(ValueError):
            KnobSet(ks().knobs['scale'], ks().knobs['scale'])

    def test_types(self):
        k = ks().knobs
        self.assertIs(k['scale'].type, int)
        self.assertIs(k['noise'].type, float)
        self.assertEqual(k['cross_doc'].flag, 'cross-doc')
        self.assertEqual(k['trap_count.drafts'].flag, 'trap-count')

    def test_list_knobs_json(self):
        ap = argparse.ArgumentParser(); add_knob_args(ap, ks())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as e:
            parse_knob_args(ap.parse_args(['--list-knobs']), ks())
        self.assertEqual(e.exception.code, 0)
        doc = json.loads(buf.getvalue())
        self.assertEqual([k['name'] for k in doc['knobs']], ['scale', 'noise', 'trap_count.drafts', 'cross_doc'])
        self.assertEqual(doc['knobs'][2]['trap'], 'drafts')
        self.assertIn('monotone', doc['knobs'][0])


class Flags(unittest.TestCase):
    def test_no_flags_is_the_published_task(self):
        s = parse([])
        self.assertTrue(s.canonical)
        self.assertEqual((s['scale'], s['noise'], s.trap_count('drafts'), s['cross_doc']), (1, 0.15, 1, 0))
        self.assertEqual(record({'id': 'x'}, 'x', 7, s), {'id': 'x'})   # task.yaml unchanged

    def test_a_default_value_is_still_canonical(self):
        self.assertTrue(parse(['--scale', '1', '--noise', '0.15']).canonical)

    def test_knob_needs_out(self):
        with self.assertRaises(SystemExit):
            parse(['--scale', '2'])
        self.assertEqual(parse(['--scale', '2', '--out', '/tmp/x'])['scale'], 2)
        self.assertEqual(parse(['--scale', '2', '--describe'])['scale'], 2)       # describe writes nothing

    def test_trap_count_syntax(self):
        s = parse(['--trap-count', 'drafts=3', '--out', '/tmp/x'])
        self.assertEqual(s.trap_count('drafts'), 3)
        with self.assertRaises(SystemExit):
            parse(['--trap-count', 'voids=2', '--out', '/tmp/x'])
        with self.assertRaises(SystemExit):
            parse(['--trap-count', 'drafts', '--out', '/tmp/x'])

    def test_range_and_type(self):
        with self.assertRaises(SystemExit):
            parse(['--scale', '9', '--out', '/tmp/x'])
        with self.assertRaises(SystemExit):
            parse(['--scale', 'two', '--out', '/tmp/x'])
        with self.assertRaises(SystemExit):
            parse(['--noise', '0.9', '--out', '/tmp/x'])
        with self.assertRaises(KeyError):
            parse([])['rules']                                                   # undeclared knob fails loudly

    def test_record_merges_with_a_trap_variant(self):
        s = parse(['--noise', '0.3', '--cross-doc', '1', '--out', '/tmp/x'])
        spec = {'variant': {'of': 'x', 'draw': 7, 'traps_off': ['a']}}
        record(spec, 'x', 7, s)
        self.assertEqual(spec['variant'], {'of': 'x', 'draw': 7, 'traps_off': ['a'],
                                           'knobs': {'noise': 0.3, 'cross_doc': 1}})

    def test_coexists_with_trap_args(self):
        ap = argparse.ArgumentParser(); add_trap_args(ap); add_knob_args(ap, ks())   # --out declared once
        a = ap.parse_args(['--scale', '4', '--out', '/tmp/x'])
        self.assertEqual(parse_knob_args(a, ks())['scale'], 4)
        self.assertTrue(parse_trap_args(a, TrapSet({'t': ''})).canonical)

    def test_steps_and_measure(self):
        k = ks().knobs['scale']
        self.assertEqual([steps(k, v) for v in (1, 2, 3, 4, 8)], [0, 1, 1.5, 2, 4])
        self.assertEqual(measure_value({'trap_instances': {'drafts': 3}}, 'trap_instances.drafts'), 3)


def gen(*args):
    return subprocess.run([sys.executable, str(DP / 'gen.py'), *map(str, args)], capture_output=True, text=True, cwd=DP)


class KnobbedGenerator(unittest.TestCase):
    """duplicate-payments: the first generator with knobs (CSV-graded, so this needs no LibreOffice)."""

    def test_list_and_describe(self):
        decl = json.loads(gen('--list-knobs').stdout)
        self.assertEqual({k['name'] for k in decl['knobs']},
                         {'scale', 'trap_count.dup_vendor_record', 'trap_count.dup_leading_zero'})
        base = json.loads(gen('--describe').stdout)
        more = json.loads(gen('--describe', '--trap-count', 'dup_vendor_record=3').stdout)
        self.assertEqual(base['non_default'], {})
        self.assertEqual(base['counts']['trap_instances']['dup_vendor_record'], 1)
        self.assertEqual(more['counts']['trap_instances']['dup_vendor_record'], 3)
        self.assertEqual(gen('--describe', '--trap-count', 'dup_vendor_record=3').stdout, gen(
            '--describe', '--trap-count', 'dup_vendor_record=3').stdout)

    def test_refuses_to_write_a_knob_into_the_task_folder(self):
        r = gen('--scale', '2')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('--out', r.stderr)

    def test_default_copy_and_knobbed_task(self):
        from grade import grade
        with tempfile.TemporaryDirectory() as d:
            base, hard = Path(d) / 'base', Path(d) / 'hard'
            self.assertEqual(gen('--out', base).returncode, 0)
            # the published answer; the xlsx input depends on lxml, so compare the csv and task.yaml only
            self.assertEqual((base / 'task.yaml').read_bytes(), (DP / 'task.yaml').read_bytes())
            for f in ('reference/duplicate_payments.csv', 'workspace/ap_payments_register_2026-01-01_to_2026-08-31.csv'):
                self.assertEqual((base / f).read_bytes(), (DP / f).read_bytes())
            r = gen('--scale', 2, '--trap-count', 'dup_vendor_record=3', '--out', hard)
            self.assertEqual(r.returncode, 0, r.stderr)
            spec = yaml.safe_load((hard / 'task.yaml').read_text())
            self.assertEqual(spec['variant']['knobs'], {'scale': 2, 'trap_count.dup_vendor_record': 3})
            self.assertNotEqual((hard / 'reference/duplicate_payments.csv').read_bytes(),
                                (base / 'reference/duplicate_payments.csv').read_bytes())   # the answer moved
            self.assertTrue(grade(str(hard), str(hard / 'reference_solution'))['passed'])
            self.assertFalse(grade(str(hard), str(hard / 'workspace'))['passed'])


class RenewUsesKnobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import renew
        cls.renew = renew
        cls.tmp = tempfile.TemporaryDirectory()
        cls.g = renew.Generator('duplicate-payments', scratch=cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_route_flags_and_grid(self):
        self.assertEqual(self.g.route, 'knobs+seed')
        self.assertEqual(self.g.knobs(), ['scale', 'trap-count'])       # --list-knobs / --describe are reserved
        grid = self.g.knob_grid('single+max')
        self.assertEqual(grid[0], {})
        self.assertEqual(len(grid), 1 + 3 + 3 + 2 + 1)
        self.assertIn({'trap-count': 'dup_vendor_record=4'}, grid)
        self.assertEqual(grid[-1], {'scale': 8, 'trap-count': 'dup_vendor_record=4+dup_leading_zero=3'})
        self.assertEqual(self.g.knob_grid('none'), [{}])

    def test_steps(self):
        self.assertEqual(self.g.knob_steps({'scale': '4', 'trap-count': 'dup_vendor_record=3'}),
                         {'scale': 2.0, 'trap_count.dup_vendor_record': 2.0})
        self.assertEqual(self.g.knob_steps({'scale': '1'}), {})

    def test_knob_prior_is_positive_and_scales_with_levels(self):
        p = self.renew.Predictor(self.renew.LEDGER, str(ROOT / 'tasks' / 'desk'), boot=10)
        f = self.renew.task_features(str(DP))
        one = p.delta(f, f, 0, {'scale': 1.0})
        three = p.delta(f, f, 0, {'scale': 1.0, 'trap_count.x': 2.0})
        self.assertAlmostEqual(one['estimate'], 0.5)
        self.assertAlmostEqual(three['estimate'], 1.5)
        self.assertGreater(one['lo90'], 0)                          # sign fixed by the declaration
        self.assertEqual(one['knob_prior_part'], 0.5)
        self.assertEqual(p.delta(f, f, 0)['estimate'], 0.0)


if __name__ == '__main__':
    unittest.main()
