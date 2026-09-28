"""Executable handbook: every process task's policy registry regenerates its committed handbook byte for byte, and
the lint catches checks that cite missing clauses or run rules no cited clause binds."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))

import handbook  # noqa: E402

TASKS = sorted(d for d in os.listdir(handbook.TASKS) if os.path.isfile(os.path.join(handbook.TASKS, d, 'task.yaml')))


class Committed(unittest.TestCase):
    def test_every_process_task_has_a_registry(self):
        self.assertEqual([t for t in TASKS if not handbook.has_registry(t)], [])

    def test_registries_reproduce_the_handbooks_byte_for_byte(self):
        for task in TASKS:
            with self.subTest(task=task):
                self.assertEqual(handbook.check(task), [])

    def test_lint_has_no_errors(self):
        for task in TASKS:
            with self.subTest(task=task):
                self.assertEqual(handbook.lint(task)[0], [])

    def test_lint_reports_unenforced_clauses_without_failing(self):
        errors, report = handbook.lint('payment-run')
        self.assertEqual(errors, [])
        self.assertIn('PAY-1.1 is not enforced: no check cites it and no audit rule is bound to it', report)
        self.assertTrue(any('control accounts tie' in r and 'cites no clause' in r for r in report))

    def test_parameters_render_into_the_clause(self):
        reg = handbook.load('procure-to-pay-week')
        self.assertIn('Freight above $100.00: hold', handbook.clause_text(reg, 'AP-3.1'))
        reg['policies']['AP-3.1']['params']['freight_limit'] = 250
        self.assertIn('Freight above $250.00: hold', handbook.render(reg)['payables.md'])

    def test_cli(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(handbook.main(['check', '--task', 'payment-run,margin-bridge']), 0)
            self.assertEqual(handbook.main(['lint', '--task', 'payment-run']), 0)
        self.assertIn('ok   payment-run', out.getvalue())
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            self.assertEqual(handbook.main(['render', 'payment-run', '--out', tmp]), 0)
            src = os.path.join(handbook.TASKS, 'payment-run', 'handbook')
            for f in os.listdir(src):
                with open(os.path.join(src, f), 'rb') as a, open(os.path.join(tmp, f), 'rb') as b:
                    self.assertEqual(a.read(), b.read())


class Fill(unittest.TestCase):
    def test_format_spec_and_literal_braces(self):
        self.assertEqual(handbook.fill('up to ${x:,.2f} {{ok}}', {'x': 5000})[0], 'up to $5,000.00 {ok}')

    def test_undefined_parameter_and_stray_brace(self):
        with self.assertRaises(handbook.RegistryError):
            handbook.fill('{missing}', {})
        with self.assertRaises(handbook.RegistryError):
            handbook.fill('a { b', {})


class Broken(unittest.TestCase):
    """A copy of payment-run with one defect planted at a time."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.task = os.path.join(self.tmp, 'payment-run')
        src = os.path.join(handbook.TASKS, 'payment-run')
        os.makedirs(self.task)
        for f in ('task.yaml', 'policies.yaml'):
            shutil.copy(os.path.join(src, f), self.task)
        shutil.copytree(os.path.join(src, 'handbook'), os.path.join(self.task, 'handbook'))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, name, old, new):
        path = os.path.join(self.task, name)
        text = open(path, encoding='utf-8').read()
        self.assertIn(old, text)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text.replace(old, new, 1))

    def test_the_copy_is_clean(self):
        self.assertEqual(handbook.problems(self.task), [])

    def test_check_citing_a_missing_clause(self):
        self.edit('task.yaml', 'cites: [VEN-2.3]', 'cites: [VEN-2.3, VEN-9.9]')
        self.assertIn("check 'fraud escalated to the controller' cites VEN-9.9, which the registry lacks",
                      handbook.lint(self.task)[0])

    def test_audit_check_whose_rule_no_cited_clause_binds(self):
        self.edit('policies.yaml', '    rules: [pay_held_invoice]\n', '')
        errors = handbook.lint(self.task)[0]
        self.assertTrue(any('runs pay_held_invoice, but none of its cited clauses' in e for e in errors), errors)

    def test_unknown_rules(self):
        self.edit('task.yaml', 'rule: pay_held_invoice', 'rule: pay_held_invoice_v2')
        self.edit('policies.yaml', 'rules: [pay_held_invoice]', 'rules: [pay_held_invoice, no_such_rule]')
        errors = handbook.lint(self.task)[0]
        self.assertIn("check 'no hold released by the preparer' runs unknown audit rule pay_held_invoice_v2", errors)
        self.assertIn('PAY-2.3 binds unknown audit rule no_such_rule', errors)

    def test_clause_placed_twice_or_referring_to_a_missing_clause(self):
        self.edit('policies.yaml', '    - PAY-2.5\n', '    - PAY-2.5\n    - PAY-2.4\n')
        self.edit('policies.yaml', 'When paying everything PAY-2.1', 'When paying everything PAY-7.1')
        errors = handbook.lint(self.task)[0]
        self.assertIn('PAY-2.4 is placed in the handbook 2 times (once expected)', errors)
        self.assertIn('TRE-1.2 refers to PAY-7.1, which the registry lacks', errors)

    def test_unused_parameter(self):
        self.edit('policies.yaml', '  PAY-1.1:\n', '  PAY-1.1:\n    params: {day: Friday}\n')
        self.assertIn('PAY-1.1: parameter day is not used in the text', handbook.lint(self.task)[0])

    def test_duplicate_policy_id(self):
        self.edit('policies.yaml', '  PAY-2.2:\n', '  PAY-2.1:\n    text: again\n  PAY-2.2:\n')
        with self.assertRaises(handbook.RegistryError):
            handbook.load(self.task)
        self.assertTrue(handbook.lint(self.task)[0][0].startswith('registry: duplicate key'))

    def test_edited_handbook_is_a_byte_difference(self):
        self.edit('handbook/payments.md', 'on Fridays', 'on Thursdays')
        problems = handbook.check(self.task)
        self.assertEqual(len(problems), 1)
        self.assertIn('-**PAY-1.1** Payment runs go out on Thursdays', problems[0])
        self.assertIn('+**PAY-1.1** Payment runs go out on Fridays', problems[0])
        self.assertEqual(handbook.problems(self.task), problems)

    def test_handbook_file_the_registry_does_not_generate(self):
        with open(os.path.join(self.task, 'handbook', 'extra.md'), 'w') as f:
            f.write('# Extra\n')
        self.assertEqual(handbook.check(self.task),
                         ['handbook/extra.md is committed but the registry does not generate it'])

    def test_a_task_without_a_registry_is_skipped(self):
        os.remove(os.path.join(self.task, 'policies.yaml'))
        self.assertEqual(handbook.problems(self.task), [])


if __name__ == '__main__':
    unittest.main()
