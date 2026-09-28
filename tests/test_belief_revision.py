"""Belief revision on the process track: `stale_derived_entry` finds a derived entry left standing after its source
changed (a receipt reversed, a rate corrected), including one "corrected" by a difference entry beside it, and finds
nothing in a clean log; logs are built through the agent's API on freight-accrual-revision's scenario, with the
simulator changing the facts between the turns."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

import process_run  # noqa: E402
from bberp import api, sim  # noqa: E402
from bberp.core import Erp  # noqa: E402
from procgen.episode import load_meta  # noqa: E402
from process_rules import RULES  # noqa: E402

TASK = 'freight-accrual-revision'
MONTH_END, REVISED, TURN2 = '2026-09-30', '2026-10-01', '2026-10-02'


class StaleDerivedEntry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        scenario = process_run.ensure_scenario(TASK, 0)
        self.meta = load_meta(scenario)
        self.truth = json.load(open(os.path.join(scenario, 'truth.json')))['values']
        self.start_db = os.path.join(scenario, 'scenario.db')
        db = os.path.join(self.tmp.name, 'company.db')
        shutil.copyfile(self.start_db, db)
        self.erp = Erp(db, world=json.load(open(os.path.join(scenario, 'world.json'))))
        self.p = {'agent': self.meta['agent_user'], 'token_id': self.meta['token_id'], 'start': self.meta['start']}
        self.misdelivered = self.truth['misdelivered']
        self.relaned = sorted(r['ref'] for r in self.truth['revised_sources'] if r['ref'] != self.misdelivered)
        steady = self.erp.val("SELECT r.id FROM receipts r JOIN purchase_orders p ON p.id = r.po_id "
                              "WHERE p.vendor = 'V-10004' AND r.receipt_date >= '2026-09-01' ORDER BY r.id")
        # turn 1: one accrual per receipt, before the facts change
        self.je = {rid: self.book(rid, 40.0) for rid in (self.misdelivered, *self.relaned, steady)}
        self.steady = steady
        sim.advance(self.erp, REVISED)          # the warehouse reverses the misdelivered receipt
        sim.advance(self.erp, TURN2)
        self.assertEqual(self.erp.val('SELECT status FROM receipts WHERE id = ?', self.misdelivered), 'reversed')

    def tearDown(self):
        self.erp.close()
        self.tmp.cleanup()

    def call(self, method, path, body=None):
        s, _, data = api.handle(self.erp, method, path, {'Authorization': f'Bearer {self.meta["token"]}'},
                                json.dumps(body).encode() if body is not None else None)
        self.assertLess(s, 300, data)
        return json.loads(data)['data']

    def book(self, rid, amount, memo=None, lines=None):
        je = self.call('POST', '/journal-entries', {
            'entry_date': MONTH_END, 'memo': memo or f'Freight accrual {rid}',
            'lines': lines or [{'account': '5100', 'debit': amount}, {'account': '2100', 'credit': amount}]})
        self.call('POST', f'/journal-entries/{je["id"]}/post')
        return je['id']

    def reverse(self, rid):
        self.call('POST', f'/journal-entries/{self.je[rid]}/reverse', {'reverse_date': MONTH_END, 'reason': 'revised'})

    def findings(self, declared=True):
        self.erp.db.commit()
        final = sqlite3.connect(self.erp.path)
        start = sqlite3.connect(f'file:{self.start_db}?mode=ro', uri=True)
        spec = {'revised': [{'ref': r, 'on': REVISED} for r in self.relaned]} if declared else {}
        try:
            return RULES['stale_derived_entry'](final, start, self.p, spec)
        finally:
            final.close()
            start.close()

    def test_nothing_done_after_the_revision(self):
        found = self.findings()
        self.assertEqual(sorted(f.split()[0] for f in found),
                         sorted(self.je[r] for r in (self.misdelivered, *self.relaned)))
        self.assertFalse(any(self.je[self.steady] in f for f in found))

    def test_reversed_receipts_are_found_without_being_declared(self):
        self.assertEqual([f.split()[0] for f in self.findings(declared=False)], [self.je[self.misdelivered]])

    def test_a_difference_entry_beside_the_old_one_is_still_stale(self):
        self.book(self.misdelivered, 0, memo=f'Freight accrual adjustment {self.misdelivered}',
                  lines=[{'account': '2100', 'debit': 40.0}, {'account': '5100', 'credit': 40.0}])
        for rid in self.relaned:
            self.book(rid, 0, memo=f'Freight accrual adjustment {rid}',
                      lines=[{'account': '2100', 'debit': 6.0}, {'account': '5100', 'credit': 6.0}])
        found = self.findings()
        self.assertEqual(len(found), 1 + len(self.relaned))
        self.assertTrue(all('adjustment' not in f for f in found), found)   # the originals, not the corrections

    def test_clean_log(self):
        self.reverse(self.misdelivered)
        for rid in self.relaned:
            self.reverse(rid)
            self.book(rid, 34.0, memo=f'Freight accrual {rid}, lane L3 at the corrected rate')
        self.book(self.steady, 12.0, memo=f'Freight accrual {self.steady}, a late addition')   # prepared after: not stale
        self.assertEqual(self.findings(), [])

    def test_a_reference_is_a_whole_token(self):
        rid = self.misdelivered
        longer = rid + '0'
        with self.erp.tx():
            self.erp.update('journal_entries', {'id': self.je[rid]}, {'memo': f'Freight accrual {longer}'})
        self.assertFalse(any(self.je[rid] in f for f in self.findings(declared=False)))


if __name__ == '__main__':
    unittest.main()
