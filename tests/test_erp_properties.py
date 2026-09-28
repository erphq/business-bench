"""bb-erp properties: random call sequences keep every invariant, a write that fails partway leaves no trace, the same
calls give the same export, and (slow, opt-in) a killed server recovers to a consistent file.

The machinery is bench/erp_fuzz.py; these tests run it small enough for the default suite (about a minute on two
shared CPUs). Heavier runs:

    ERP_FUZZ_STEPS=400 ERP_FUZZ_SEQUENCES=4 python3 -m unittest tests.test_erp_properties
    ERP_FUZZ_CRASH=5 python3 -m unittest tests.test_erp_properties.Crash
    python3 bench/erp_fuzz.py --task procure-to-pay-week --seed 0 --steps 500 --sequences 5

Known kernel bugs have a minimal reproduction below, marked expectedFailure: when one is fixed its test starts to
"unexpectedly succeed", which is the cue to drop the marker and take the bug out of erp_fuzz.KNOWN_BUGS.
"""
import json
import os
import shutil
import sqlite3
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))
sys.path.insert(0, os.path.join(ROOT, 'erp'))

import erp_fuzz as fz  # noqa: E402
from bberp import core, receiving, reports, sim  # noqa: E402

TASK = os.environ.get('ERP_FUZZ_TASK', 'payment-run')
SEED = int(os.environ.get('ERP_FUZZ_SEED', '0'))
STEPS = int(os.environ.get('ERP_FUZZ_STEPS', '300'))
SEQUENCES = int(os.environ.get('ERP_FUZZ_SEQUENCES', '2'))
ATOMIC_POINTS = int(os.environ.get('ERP_FUZZ_ATOMIC_POINTS', '0')) or None     # None: every statement
CRASH_KILLS = int(os.environ.get('ERP_FUZZ_CRASH', '0'))

SCENARIO = None
WORK = None


def setUpModule():
    global SCENARIO, WORK
    SCENARIO = fz.ensure_scenario(TASK, SEED)
    WORK = fz.scratch_dir('erp-props-')


def tearDownModule():
    shutil.rmtree(WORK, ignore_errors=True)


def work(name: str) -> str:
    d = os.path.join(WORK, name)
    shutil.rmtree(d, ignore_errors=True)
    return d


def show(violations: list) -> str:
    return json.dumps(violations[:5], indent=1)[:4000]


class Fuzz(unittest.TestCase):
    def test_random_sequences_keep_every_invariant(self):
        writes_ok = refused = 0
        for i in range(SEQUENCES):
            r = fz.fuzz_sequence(SCENARIO, SEED, i, STEPS, work(f'fuzz-{i}'))
            self.assertEqual(r['violations'], [], f'sequence {i}:\n{show(r["violations"])}')
            for kind, statuses in r['kinds'].items():
                for status, n in statuses.items():
                    if status.isdigit() and 200 <= int(status) < 300 and kind.split('.')[0] not in ('read', 'x'):
                        writes_ok += n
                    if kind.startswith('x.') and status.isdigit() and 400 <= int(status) < 500:
                        refused += n
        # not vacuous: the sequences changed the company and probed its controls
        self.assertGreater(writes_ok, SEQUENCES * STEPS // 5)
        self.assertGreater(refused, SEQUENCES * STEPS // 10)

    def test_the_checker_sees_a_receipt_that_skips_its_posting(self):
        """A kernel that forgets the ledger side of a receipt is caught at the call that does it."""
        h = fz.Harness(SCENARIO, work('mutant'))
        try:
            po = h.erp.one("SELECT p.id FROM purchase_orders p WHERE p.status = 'sent' AND EXISTS (SELECT 1 FROM po_lines "
                           "l WHERE l.po_id = p.id AND l.sku IS NOT NULL AND l.sku NOT LIKE 'SEAL%') ORDER BY p.id")
            line = h.erp.one("SELECT line, qty FROM po_lines WHERE po_id = ? AND sku IS NOT NULL ORDER BY line", po['id'])
            call = fz.Call('luis.ortega', 'POST', '/receipts', {'po_id': po['id'], 'lines': [
                {'po_line': line['line'], 'qty_received': line['qty']}]}, 'rcv.post')
            with mock.patch.object(receiving.ledger, 'post', lambda *a, **k: None):
                status, _ = h.step(call)
            self.assertEqual(status, 201)
            self.assertIn('ledger_ties', {v.invariant for v in h.violations})
        finally:
            h.close()


class Atomicity(unittest.TestCase):
    CALLS = ['receive', 'post invoice', 'pay', 'post journal', 'close period']

    def test_a_write_that_fails_partway_leaves_no_trace(self):
        res = fz.atomicity_sweep(SCENARIO, work('atomic'), names=self.CALLS, max_points=ATOMIC_POINTS)
        self.assertEqual(sorted(r['call'].split(' (')[0] for r in res), sorted(self.CALLS))
        for r in res:
            with self.subTest(call=r['call']):
                self.assertGreater(r['statements'], 5)
                if ATOMIC_POINTS is None:
                    self.assertEqual(r['points'], r['statements'])      # a fault before every statement
                self.assertEqual(r['failures'], [])

    def test_the_sweep_sees_a_kernel_that_commits_on_error(self):
        """Sanity check of the sweep itself: a transaction that commits instead of rolling back is caught."""
        from contextlib import contextmanager

        @contextmanager
        def leaky_tx(self):
            with self.lock:
                outer = self._depth == 0
                if outer:
                    self.db.execute('BEGIN IMMEDIATE')
                self._depth += 1
                try:
                    yield self
                finally:
                    self._depth -= 1
                    if outer:
                        self.db.execute('COMMIT')
        with mock.patch.object(core.Erp, 'tx', leaky_tx):
            res = fz.atomicity_sweep(SCENARIO, work('leaky'), names=['post journal'], max_points=6)
        self.assertTrue(res and res[0]['failures'], res)
        self.assertTrue(any('database changed' in f['problem'] for f in res[0]['failures']))


class Replay(unittest.TestCase):
    def test_same_scenario_and_calls_give_identical_exports(self):
        res = fz.replay_check(SCENARIO, SEED, max(STEPS // 2, 60), work('replay'))
        self.assertTrue(res['generator_deterministic'], res)
        self.assertTrue(res['responses_identical'], res)
        self.assertEqual(res['tables_differ'], [], res)
        self.assertTrue(res['identical'], res)


@unittest.skipUnless(CRASH_KILLS, 'slow: set ERP_FUZZ_CRASH=<kills> to SIGKILL a live server')
class Crash(unittest.TestCase):
    def test_a_killed_server_recovers_to_a_consistent_file(self):
        res = fz.crash_test(SCENARIO, SEED, CRASH_KILLS, work('crash'))
        for r in res:
            with self.subTest(kill=r['kill']):
                self.assertEqual(r['integrity'], 'ok')
                self.assertEqual(r['problems'], [])


# ---------------------------------------------------------------------------------------------- known kernel bugs

class KnownBugs(unittest.TestCase):
    """Minimal reproductions of the bugs in erp_fuzz.KNOWN_BUGS. Each asserts the correct behaviour and is expected to
    fail until bb-erp is fixed; the fuzzer keeps these calls out of its random sequences meanwhile."""

    def setUp(self):
        self.h = fz.Harness(SCENARIO, work(self.id().rsplit('.', 1)[-1]), check=False)
        self.erp = self.h.erp

    def tearDown(self):
        self.h.close()

    def call(self, user, method, path, body=None):
        return self.h.request(fz.Call(user, method, path, body))

    @unittest.expectedFailure
    def test_gl_reversal_of_a_subledger_entry_is_refused(self):
        """KNOWN_BUGS['gl_reverse_subledger_entry']: reversing an AP invoice's posting from the journal-entry API is
        accepted, the invoice stays approved and payable, and AP and GRNI stop tying to their subledgers."""
        inv = self.erp.one("SELECT id, posted_je FROM ap_invoices WHERE status = 'approved' AND po_id IS NOT NULL "
                           "ORDER BY id")
        self.assertTrue(reports.control_ties(self.erp)['all_tie'])
        status, _ = self.call('priya.raman', 'POST', f'/journal-entries/{inv["posted_je"]}/reverse',
                              {'reason': 'posted twice'})
        ties = reports.control_ties(self.erp)
        self.assertEqual(self.erp.val('SELECT status FROM ap_invoices WHERE id = ?', inv['id']), 'approved')
        self.assertTrue(status >= 400 or ties['all_tie'],
                        f'{status}; differences: ' + json.dumps({k: v['difference_cents'] for k, v in
                                                                 ties['controls'].items()}))

    @unittest.expectedFailure
    def test_a_failed_commit_rolls_back_and_the_kernel_keeps_serving(self):
        """KNOWN_BUGS['commit_failure_leaves_transaction_open']: another connection holding a read lock makes COMMIT
        fail with 'database is locked'; Erp.tx() leaves the transaction open, so every later request answers 500."""
        self.erp.db.execute('PRAGMA busy_timeout = 50')
        reader = sqlite3.connect(self.h.db_path, isolation_level=None)
        reader.execute('BEGIN')
        reader.execute('SELECT COUNT(*) FROM meta').fetchone()              # holds a SHARED lock
        status, _ = self.call('omar.haddad', 'POST', '/outbox', {'to': 'a@example.com', 'subject': 'hello'})
        reader.execute('COMMIT')
        reader.close()
        self.assertEqual(status, 500)                                       # the write could not commit
        after, _ = self.call('omar.haddad', 'GET', '/whoami')
        self.assertFalse(self.erp.db.in_transaction, 'the failed transaction is still open')
        self.assertEqual(after, 200)

    @unittest.expectedFailure
    def test_malformed_input_is_refused_not_a_server_error(self):
        """KNOWN_BUGS['malformed_input_500']: wrongly typed input reaches Python code that raises, so the API answers
        500 server_error where a 422 problem is due. Nothing is written (the transaction rolls back)."""
        po = self.erp.val("SELECT id FROM purchase_orders WHERE status = 'sent' ORDER BY id")
        probes = [
            ('riley.park', 'POST', '/purchase-orders', {'vendor': 'V-10001', 'lines': 7}),
            ('riley.park', 'POST', '/receipts', {'po_id': po, 'lines': 'all of it'}),
            ('riley.park', 'POST', '/ap-invoices', {'vendor': 'V-10001', 'invoice_no': 'M-1', 'invoice_date': '2026-10-08',
                                                    'lines': [1, 2]}),
            ('nina.patel', 'POST', '/cash-receipts', {'amount': 'abc'}),
            ('luis.ortega', 'POST', '/inventory/transfers', {'sku': 'BR-0750', 'from': 'DAY-STK', 'to': 'DAY-QA',
                                                             'qty': 'five'}),
            ('omar.haddad', 'POST', '/journal-entries', {'entry_date': '2026-10-08', 'memo': [], 'lines': [
                {'account': '6100', 'debit': 5}, {'account': '2100', 'credit': 5}]}),
            ('riley.park', 'PATCH', f'/purchase-orders/{po}/lines/one', {'note': 'x'}),
            ('jordan.lee', 'POST', '/work-orders', {'sku': 'BV-100', 'qty': 5, 'start_date': '2026-10-08',
                                                    'due_date': {}}),
            ('riley.park', 'GET', '/ap-invoices?limit=all', None),
        ]
        statuses = {f'{m} {p}': self.call(u, m, p, b)[0] for u, m, p, b in probes}
        self.assertEqual({k: s for k, s in statuses.items() if s >= 500}, {})

    @unittest.expectedFailure
    def test_releasing_a_held_partial_shipment_keeps_it_partially_shipped(self):
        """KNOWN_BUGS['so_release_forgets_partial_shipment']: hold and release a partially shipped order and it reads
        'released' although part of it has shipped."""
        so = self.erp.val("SELECT id FROM sales_orders WHERE status = 'partially_shipped' ORDER BY id")
        self.assertEqual(self.call('tom.reyes', 'POST', f'/sales-orders/{so}/hold', {'reason': 'credit review'})[0], 201)
        self.assertEqual(self.call('nina.patel', 'POST', f'/sales-orders/{so}/release', {'note': 'paid up'})[0], 201)
        self.assertEqual(self.erp.val('SELECT status FROM sales_orders WHERE id = ?', so), 'partially_shipped')

    @unittest.expectedFailure
    def test_dates_are_validated(self):
        """KNOWN_BUGS['unvalidated_dates']: an impossible entry date is created and posted, and a payment run takes
        any string as its pay date."""
        je, _ = self.call('omar.haddad', 'POST', '/journal-entries', {'entry_date': '2026-10-99', 'memo': 'accrual',
                                                                      'lines': [{'account': '6100', 'debit': 5},
                                                                                {'account': '2100', 'credit': 5}]})
        run, _ = self.call('hannah.brooks', 'POST', '/payment-runs', {'pay_date': 'next friday', 'bank_account': 'OPER'})
        self.assertEqual((je, run), (422, 422))

    @unittest.expectedFailure
    def test_an_approved_run_is_never_stuck(self):
        """KNOWN_BUGS['approved_run_dead_end']: void an invoice that sits in an approved run and the run can neither be
        released nor returned, and the invoices with it can never be paid."""
        invs = [r['id'] for r in self.erp.all(
            "SELECT i.id FROM ap_invoices i JOIN vendors v ON v.id = i.vendor JOIN vendor_bank_accounts b ON b.id = "
            "v.remit_account AND b.status = 'verified' WHERE i.status = 'approved' AND NOT EXISTS (SELECT 1 FROM holds h "
            "WHERE h.doc_id = i.id AND h.released_on IS NULL) ORDER BY i.id LIMIT 2")]
        status, out = self.call('hannah.brooks', 'POST', '/payment-runs', {'pay_date': '2026-10-08', 'bank_account': 'OPER'})
        run = json.loads(out)['data']['id']
        for inv in invs:
            self.assertEqual(self.call('hannah.brooks', 'POST', f'/payment-runs/{run}/invoices', {'inv_id': inv})[0], 201)
        self.assertEqual(self.call('hannah.brooks', 'POST', f'/payment-runs/{run}/submit')[0], 201)
        self.assertEqual(self.call('priya.raman', 'POST', f'/payment-runs/{run}/approve', {})[0], 201)
        void, _ = self.call('hannah.brooks', 'POST', f'/ap-invoices/{invs[0]}/void', {'reason': 'duplicate'})
        release, _ = self.call('priya.raman', 'POST', f'/payment-runs/{run}/release')
        back, _ = self.call('priya.raman', 'POST', f'/payment-runs/{run}/return', {'reason': 'rebuild'})
        # either the void is refused while the invoice is in a live run, or the run can still go out or come back
        self.assertTrue(void >= 400 or release < 400 or back < 400, (void, release, back))

    @unittest.expectedFailure
    def test_a_clock_advance_that_fails_can_be_retried(self):
        """KNOWN_BUGS['clock_advance_not_atomic']: a database error in the middle of a day's counterparty actions
        leaves the date advanced and the rest of the day undone; advancing again does not redo it."""
        invs = [r['id'] for r in self.erp.all(
            "SELECT i.id FROM ap_invoices i JOIN vendors v ON v.id = i.vendor JOIN vendor_bank_accounts b ON b.id = "
            "v.remit_account AND b.status = 'verified' WHERE i.status = 'approved' AND NOT EXISTS (SELECT 1 FROM holds h "
            "WHERE h.doc_id = i.id AND h.released_on IS NULL) ORDER BY i.id LIMIT 3")]
        _, out = self.call('hannah.brooks', 'POST', '/payment-runs', {'pay_date': '2026-10-08', 'bank_account': 'OPER'})
        run = json.loads(out)['data']['id']
        for inv in invs:
            self.call('hannah.brooks', 'POST', f'/payment-runs/{run}/invoices', {'inv_id': inv})
        self.call('hannah.brooks', 'POST', f'/payment-runs/{run}/submit')
        self.call('priya.raman', 'POST', f'/payment-runs/{run}/approve', {})
        self.assertEqual(self.call('priya.raman', 'POST', f'/payment-runs/{run}/release')[0], 201)
        n_payments = self.erp.val('SELECT COUNT(*) FROM payments WHERE run_id = ?', run)
        self.assertGreater(n_payments, 1)
        fc = fz.FaultyConnection(self.erp.db, fail_on=('UPDATE payments', 2))  # the bank clears the second payment
        self.erp.db, fc.armed = fc, True
        with self.assertRaises(sqlite3.OperationalError):
            sim.advance(self.erp, '2026-10-09')
        self.erp.db = fc._conn
        sim.advance(self.erp, '2026-10-09')                     # the runner would retry the advance
        cleared = self.erp.val("SELECT COUNT(*) FROM payments WHERE run_id = ? AND status = 'cleared'", run)
        self.assertEqual(cleared, n_payments)


if __name__ == '__main__':
    unittest.main()
