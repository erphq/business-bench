"""Scorer-change gate: blind mapping, per-system flip counts, violations and exit codes, with stub scorers."""
import io, json, os, shutil, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
import scorer_gate as sg  # noqa: E402

TASK = 'tiny-total'


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        f.write(text)


def load_json(p):
    with open(p) as f:
        return json.load(f)


def total_of(ws):
    try:
        with open(os.path.join(ws, 'total.txt')) as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return None


def strict(task, ws):
    """The base: the deliverable must exist and hold exactly 42."""
    t = total_of(ws)
    return {'file exists': t is not None, 'total is 42': t == 42.0}


def lenient(task, ws):
    """A candidate that accepts any number within 5: turns 40 into a pass."""
    t = total_of(ws)
    return {'file exists': t is not None, 'total is 42': t is not None and abs(t - 42) <= 5}


def harsher(task, ws):
    """A candidate that also demands a memo: turns some passes into fails, breaks no FAIL expectation."""
    return {**strict(task, ws), 'memo': os.path.exists(os.path.join(ws, 'memo.txt'))}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='gate-test-')
        c = os.path.join(self.tmp, 'controls')
        write(os.path.join(c, 'ref', 'total.txt'), '42')
        os.makedirs(os.path.join(c, 'empty'))
        write(os.path.join(c, 'naive', 'total.txt'), '40')         # off by the trap's amount
        write(os.path.join(c, 'mutant', 'total.txt'), '39')
        self.controls = [
            sg.ControlItem(f'{TASK}/reference', TASK, 'reference', os.path.join(c, 'ref'), 'pass'),
            sg.ControlItem(f'{TASK}/empty', TASK, 'empty', os.path.join(c, 'empty'), 'fail'),
            sg.ControlItem(f'{TASK}/naive', TASK, 'naive', os.path.join(c, 'naive'), 'fail'),
            sg.ControlItem(f'{TASK}/mutant:credits', TASK, 'mutant', os.path.join(c, 'mutant'), 'fail',
                           cited=['total is 42']),
        ]
        # real attempts: alpha 3 (42, 40, 41), beta 2 (42, 30)
        a = os.path.join(self.tmp, 'artifacts')
        for system, values in (('alpha', ['42', '40', '41']), ('beta', ['42', '30'])):
            for n, v in enumerate(values, 1):
                write(os.path.join(a, system, TASK, f'r{n}', 'total.txt'), v)
        self.artifacts = sg.discover_artifacts(a, None)
        self.work = os.path.join(self.tmp, 'work'); os.makedirs(self.work)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def gate(self, base, cand, artifacts=True, out_dir=None):
        return sg.run_gate(sg.Scorer(base, 'base'), sg.Scorer(cand, 'candidate'), self.controls,
                           artifacts=self.artifacts if artifacts else None, work=self.work, out_dir=out_dir)


class BlindingTests(Fixture):
    def test_scorer_never_sees_system_labels_and_order_is_mixed(self):
        seen = []

        def spy(task, ws):
            seen.append(ws)
            return strict(task, ws)

        ledger = sg.BlindLedger(self.artifacts, self.work, seed=7)
        sg.score_blind(ledger, sg.Scorer(spy), sg.Scorer(spy))
        self.assertEqual(len(seen), 10)
        for ws in seen:
            self.assertNotIn('alpha', ws); self.assertNotIn('beta', ws)
            self.assertNotIn(os.path.join(self.tmp, 'artifacts'), ws)
            self.assertRegex(os.path.basename(ws), r'^x\d+$')
        # item ids carry no label and the key is not reachable from the items
        for it in ledger.items:
            self.assertEqual(set(it), {'id', 'task', 'ws'})

    def test_shuffle_is_seeded_and_reproducible(self):
        k1 = sg.BlindLedger(self.artifacts, self.work, seed=3)._key
        k2 = sg.BlindLedger(self.artifacts, self.work, seed=3)._key
        k3 = sg.BlindLedger(self.artifacts, self.work, seed=4)._key
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)

    def test_labels_revealed_only_after_all_verdicts(self):
        ledger = sg.BlindLedger(self.artifacts, self.work)
        partial = {ledger.items[0]['id']: {'base': {}, 'candidate': {}}}
        with self.assertRaises(RuntimeError):
            ledger.reveal(partial)
        self.assertFalse(ledger.revealed)
        events = []
        orig = ledger.reveal

        def reveal(verdicts):
            events.append(('reveal', len(verdicts)))
            return orig(verdicts)

        def spy(task, ws):
            events.append(('score', ws))
            return strict(task, ws)

        ledger.reveal = reveal
        res = sg.score_blind(ledger, sg.Scorer(spy), sg.Scorer(spy))
        self.assertEqual(events[-1], ('reveal', 5))
        self.assertTrue(all(e[0] == 'score' for e in events[:-1]))
        self.assertTrue(res['blinding']['labels_joined_after_scoring'])
        self.assertLessEqual(res['blinding']['verdicts_complete_at'], res['blinding']['labels_joined_at'])

    def test_blind_verdicts_on_disk_hold_no_labels(self):
        out = os.path.join(self.tmp, 'out'); os.makedirs(out)
        rep = self.gate(strict, lenient, out_dir=out)
        with open(os.path.join(out, 'blind_verdicts.json')) as f:
            blob = f.read()
        self.assertNotIn('alpha', blob); self.assertNotIn('beta', blob)
        import hashlib
        self.assertEqual(hashlib.sha256(blob.encode()).hexdigest(),
                         rep['artifacts']['blinding']['blind_verdicts_sha256'])
        key = load_json(os.path.join(out, 'blinding_key.json'))
        self.assertEqual(sorted({v['system'] for v in key.values()}), ['alpha', 'beta'])


class FlipAndViolationTests(Fixture):
    def test_per_system_flip_counts(self):
        rep = self.gate(strict, lenient)
        ps = rep['artifacts']['per_system']
        self.assertEqual(ps['alpha'], {'attempts': 3, 'base_pass': 1, 'candidate_pass': 3,
                                       'fail_to_pass': 2, 'pass_to_fail': 0, 'ungraded': 0})
        self.assertEqual(ps['beta'], {'attempts': 2, 'base_pass': 1, 'candidate_pass': 1,
                                      'fail_to_pass': 0, 'pass_to_fail': 0, 'ungraded': 0})
        self.assertEqual({(f['system'], f['attempt']) for f in rep['artifacts']['flips']},
                         {('alpha', 'r2'), ('alpha', 'r3')})

    def test_pass_to_fail_counted(self):
        rep = self.gate(strict, harsher)
        ps = rep['artifacts']['per_system']
        self.assertEqual((ps['alpha']['pass_to_fail'], ps['beta']['pass_to_fail']), (1, 1))
        self.assertEqual((ps['alpha']['fail_to_pass'], ps['beta']['fail_to_pass']), (0, 0))

    def test_lenient_candidate_violates_naive_and_mutant(self):
        rep = self.gate(strict, lenient, artifacts=False)
        self.assertEqual(sorted(v['id'] for v in rep['controls']['violations']),
                         [f'{TASK}/mutant:credits', f'{TASK}/naive'])
        self.assertEqual(rep['exit_code'], 1)
        mutant = [v for v in rep['controls']['violations'] if 'mutant' in v['id']][0]
        self.assertIn('passes overall', mutant['why'])

    def test_breaking_the_reference_is_a_violation(self):
        rep = self.gate(strict, harsher, artifacts=False)
        self.assertEqual([v['id'] for v in rep['controls']['violations']], [f'{TASK}/reference'])
        self.assertEqual(rep['exit_code'], 1)

    def test_identical_scorers_pass_with_no_flips(self):
        rep = self.gate(strict, strict)
        self.assertEqual(rep['exit_code'], 0)
        self.assertEqual(rep['controls']['flips'], [])
        self.assertEqual(rep['controls']['violations'], [])
        self.assertTrue(all(v['fail_to_pass'] == v['pass_to_fail'] == 0 for v in rep['artifacts']['per_system'].values()))

    def test_cited_check_passing_is_a_violation_even_if_task_still_fails(self):
        def cand(task, ws):  # the cited check goes blind; another check still fails the mutant
            r = lenient(task, ws)
            if total_of(ws) == 39:
                r['extra'] = False
            return r
        rep = self.gate(strict, cand, artifacts=False)
        v = {x['id']: x for x in rep['controls']['violations']}
        self.assertIn('cited check(s) pass', v[f'{TASK}/mutant:credits']['why'])

    def test_preexisting_base_failures_are_not_violations(self):
        def broken_base(task, ws):
            return {'anything': True}  # passes everything, so misses every FAIL expectation
        rep = self.gate(broken_base, strict, artifacts=False)
        self.assertEqual(rep['controls']['violations'], [])
        self.assertEqual(len(rep['controls']['preexisting']), 3)
        self.assertEqual(rep['exit_code'], 0)

    def test_candidate_crash_is_ungraded_and_a_violation(self):
        def crash(task, ws):
            raise ValueError('boom')
        rep = self.gate(strict, crash, artifacts=False)
        self.assertEqual(len(rep['controls']['violations']), 4)
        self.assertTrue(all(r['candidate'] == 'UNGRADED' for r in rep['controls']['items']))

    def test_ungraded_attempts_are_not_flips(self):
        def errs(task, ws):
            return {'passed': False, 'checks': [], 'grader_errors': ['recalc']}
        rep = self.gate(strict, errs)
        self.assertEqual(sum(v['ungraded'] for v in rep['artifacts']['per_system'].values()), 5)
        self.assertEqual(rep['artifacts']['flips'], [])

    def test_normalise_full_grade_dict_uses_required(self):
        v = sg.normalise({'passed': True, 'grader_errors': [], 'checks': [
            {'name': 'a', 'passed': True, 'required': True},
            {'name': 'b', 'passed': False, 'required': False}]})
        self.assertTrue(v['passed']); self.assertEqual(v['failed_required'], [])
        self.assertEqual(v['checks'], {'a': True, 'b': False})

    def test_markdown_mentions_blinding_and_violations(self):
        md = sg.render_markdown(self.gate(strict, lenient))
        self.assertIn('VIOLATION', md)
        self.assertIn('joined afterwards', md)
        self.assertIn('| alpha | 3 | 1 | 3 | 2 | 0 | 0 |', md)


GEN = """
import argparse, json, os
ap = argparse.ArgumentParser()
ap.add_argument('--seed', type=int, default=0); ap.add_argument('--naive'); ap.add_argument('--out')
ap.add_argument('--mutant'); ap.add_argument('--list-traps', action='store_true')
a = ap.parse_args()
if a.list_traps:
    print(json.dumps({'switchable': [], 'mutants': ['credits'], 'sentence_keys': ['credits']})); raise SystemExit
target = a.naive or a.out
os.makedirs(target, exist_ok=True)
open(os.path.join(target, 'total.txt'), 'w').write('40' if a.naive else '39')
"""


class CorpusTests(unittest.TestCase):
    """build_controls against a tiny synthetic task with a generator (no LibreOffice, no real task)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='gate-corpus-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        td = os.path.join(self.tmp, 'src', 'tasks', 'desk', TASK)
        write(os.path.join(td, 'gen.py'), GEN)
        write(os.path.join(td, 'task.yaml'), 'id: tiny-total\nchecks:\n- {name: file exists, type: file_exists}\n'
              '- {name: total is 42, type: custom}\ntraps:\n- "credits are negative (check: total is 42)"\n')
        write(os.path.join(td, 'reference_solution', 'total.txt'), '42')
        write(os.path.join(td, 'workspace', 'inputs.csv'), 'a,b\n')

    def test_builds_every_kind_with_expectations_and_citations(self):
        items, problems = sg.build_controls(os.path.join(self.tmp, 'src'), [TASK], os.path.join(self.tmp, 'w'),
                                            sg.ALL_KINDS, max_metamorphic=0)
        self.assertEqual(problems, [])
        got = {i.id: (i.expect, i.cited) for i in items}
        self.assertEqual(got, {f'{TASK}/reference': ('pass', []), f'{TASK}/empty': ('fail', []),
                               f'{TASK}/untouched': ('fail', []), f'{TASK}/naive': ('fail', []),
                               f'{TASK}/mutant:credits': ('fail', ['total is 42'])})
        rep = sg.run_gate(sg.Scorer(strict), sg.Scorer(lenient), items, work=self.tmp)
        self.assertEqual(sorted(v['id'] for v in rep['controls']['violations']),
                         [f'{TASK}/mutant:credits', f'{TASK}/naive'])

    def test_missing_task_is_reported_not_fatal(self):
        items, problems = sg.build_controls(os.path.join(self.tmp, 'src'), ['nope'], os.path.join(self.tmp, 'w'),
                                            ['reference'])
        self.assertEqual(items, [])
        self.assertIn('not in corpus source', problems[0])


class CliTests(Fixture):
    def _main(self, cand):
        scorers = {'base': sg.Scorer(strict, 'base'), 'cand': sg.Scorer(cand, 'cand')}
        out = os.path.join(self.tmp, 'out-' + cand.__name__)
        with mock.patch.object(sg, 'make_scorer', lambda spec, tasks, work: scorers[spec]), \
             mock.patch.object(sg, 'materialise_tree', lambda src, tasks, dest: (dest, {'source': src})), \
             mock.patch.object(sg, 'build_controls', lambda *a, **k: (self.controls, [])), \
             mock.patch('sys.stdout', new=io.StringIO()), mock.patch('sys.stderr', new=io.StringIO()):
            code = sg.main(['--base', 'base', '--candidate', 'cand', '--artifacts',
                            os.path.join(self.tmp, 'artifacts'), '--out', out])
        return code, out

    def test_exit_codes_and_outputs(self):
        code, out = self._main(strict)
        self.assertEqual(code, 0)
        rep = load_json(os.path.join(out, 'gate.json'))
        self.assertEqual(rep['tasks'], [TASK])
        self.assertTrue(rep['artifacts']['blinding']['labels_joined_after_scoring'])
        self.assertTrue(os.path.exists(os.path.join(out, 'gate.md')))
        code, _ = self._main(lenient)
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
