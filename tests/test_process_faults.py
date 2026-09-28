"""Process track, fault-injection condition: the fault plan is deterministic, the HTTP layer commits or not as
declared and shows the agent only an ordinary 503, the default path is untouched, `duplicate_effect` finds an effect
applied twice (and nothing in a clean log), and payment-run's oracle survives the task's fault profile while the
blind-retry control does not."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

import process_run  # noqa: E402
from bberp import api, server  # noqa: E402
from bberp.core import Erp  # noqa: E402
from bberp.faults import FaultLog, FaultPlan, FaultSpecError  # noqa: E402
from procgen.episode import load_meta  # noqa: E402
from process_rules import RULES, duplicate_effect, fault_metrics  # noqa: E402

TASK = 'payment-run'


class Plan(unittest.TestCase):
    def test_parse_and_canonical(self):
        self.assertIsNone(FaultPlan.parse(None))
        self.assertIsNone(FaultPlan.parse(' none '))
        p = FaultPlan.parse('lost_response:post /payment-runs/*/release@2, fail_before:POST /payments,'
                            'slow:PATCH /items/**@1,delay=3,flaky-writes:seed=3,rate=0.25')
        self.assertEqual(p.canonical(), 'lost_response:POST /payment-runs/*/release@2,fail_before:POST /payments@1,'
                                        'slow:PATCH /items/**@1,delay=3,flaky-writes:seed=3,rate=0.25,lost=0.5')
        self.assertEqual(FaultPlan.parse(p.canonical()).canonical(), p.canonical())
        for bad in ('explode:POST /x', 'lost_response:/x', 'lost_response:POST /x@0', 'flaky-writes:rate=2',
                    'fail_before:POST /x@1,delay=5', 'flaky-writes:speed=1'):
            with self.subTest(bad=bad), self.assertRaises(FaultSpecError):
                FaultPlan.parse(bad)

    def test_rules_count_matches_and_hit_the_nth(self):
        p = FaultPlan.parse('lost_response:POST /payment-runs/*/invoices@2,fail_before:* /whoami@1')
        seq = [('POST', '/payment-runs/RUN-1/invoices'), ('GET', '/payment-runs/RUN-1'),
               ('POST', '/payment-runs/RUN-1/invoices?x=1'), ('POST', '/payment-runs/RUN-1/invoices'),
               ('GET', '/whoami'), ('GET', '/whoami')]
        self.assertEqual([p.decide(m, path) for m, path in seq],
                         [None, None, ('lost_response', 130.0), None, ('fail_before', 130.0), None])

    def test_profile_is_deterministic_and_touches_only_writes(self):
        def run():
            p = FaultPlan.parse('flaky-writes:seed=7,rate=0.3,max=5')
            return [p.decide(m, '/x') for m in ['POST', 'GET'] * 60]
        a, b = run(), run()
        self.assertEqual(a, b)
        self.assertTrue(all(h is None for h in a[1::2]))                 # reads are never hit
        self.assertEqual(sum(h is not None for h in a), 5)                # capped by max
        self.assertEqual({h[0] for h in a if h}, {'lost_response', 'fail_before'})
        other = FaultPlan.parse('flaky-writes:seed=8,rate=0.3,max=5')
        self.assertNotEqual(a, [other.decide(m, '/x') for m in ['POST', 'GET'] * 60])


def _scenario_copy(tmp):
    scenario = process_run.ensure_scenario(TASK, 0)
    meta = load_meta(scenario)
    db = os.path.join(tmp, 'company.db')
    shutil.copyfile(os.path.join(scenario, 'scenario.db'), db)
    world = json.load(open(os.path.join(scenario, 'world.json')))
    return Erp(db, world=world), meta, scenario


class Http(unittest.TestCase):
    """The agent handler on a real socket, as the runner's bb-erp process serves it."""

    def start(self, spec):
        self.tmp = tempfile.TemporaryDirectory()
        self.erp, self.meta, _ = _scenario_copy(self.tmp.name)
        self.log = os.path.join(self.tmp.name, 'faults.jsonl')
        plan = FaultPlan.parse(spec)
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.agent_handler(
            self.erp, plan, FaultLog(self.log) if plan else None))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}'

    def tearDown(self):
        if hasattr(self, 'httpd'):
            self.httpd.shutdown()
            self.httpd.server_close()
            self.erp.close()
            self.tmp.cleanup()

    def post(self, path, body, key=None, timeout=30):
        req = urllib.request.Request(self.url + path, method='POST', data=json.dumps(body).encode())
        req.add_header('Authorization', f'Bearer {self.meta["token"]}')
        req.add_header('Content-Type', 'application/json')
        if key:
            req.add_header('Idempotency-Key', key)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def runs(self):
        return self.erp.val('SELECT COUNT(*) FROM payment_runs')

    def test_default_path_is_the_plain_handler(self):
        H = server.agent_handler(object())
        self.assertIs(H.do_POST, H._do)
        F = server.agent_handler(object(), FaultPlan.parse('fail_before:POST /x'), FaultLog(None))
        self.assertIs(F.do_POST, F._do_faulted)

    def test_lost_response_commits_fail_before_does_not_and_both_look_alike(self):
        self.start('fail_before:POST /payment-runs@1,lost_response:POST /payment-runs@2')
        body = {'pay_date': self.meta['start'], 'bank_account': 'OPER', 'note': 'Weekly run'}
        n0 = self.runs()
        s1, h1, b1 = self.post('/payment-runs', body)
        self.assertEqual(self.runs(), n0)                                   # nothing committed
        s2, h2, b2 = self.post('/payment-runs', body, key='k-1')
        self.assertEqual(self.runs(), n0 + 1)                               # committed behind the 503
        self.assertEqual((s1, b1, h1['Content-Type']), (s2, b2, h2['Content-Type']))
        self.assertEqual(s1, 503)
        self.assertNotIn(b'inject', b1.lower() + b2.lower())
        self.assertNotIn('fault', json.dumps(h1).lower())
        s3, h3, b3 = self.post('/payment-runs', body, key='k-1')           # the safe retry
        self.assertEqual((s3, h3.get('Idempotent-Replay')), (201, 'true'))
        self.assertEqual(self.runs(), n0 + 1)
        log = [json.loads(line) for line in open(self.log)]
        self.assertEqual([(f['kind'], f['committed'], f['served_status'], f['client_status']) for f in log],
                         [('fail_before', False, None, 503), ('lost_response', True, 201, 503)])
        self.assertEqual(log[1]['idem_key'], 'k-1')

    def test_slow_response_commits_and_outlasts_the_client(self):
        self.start('slow:POST /payment-runs@1,delay=1.5')
        body = {'pay_date': self.meta['start'], 'bank_account': 'OPER'}
        n0 = self.runs()
        with self.assertRaises((TimeoutError, urllib.error.URLError, OSError)):
            self.post('/payment-runs', body, timeout=0.3)
        self.assertEqual(self.runs(), n0 + 1)
        self.assertEqual(json.loads(open(self.log).readline())['kind'], 'slow')


class DuplicateEffect(unittest.TestCase):
    """`duplicate_effect` against violating and clean logs built through the API on payment-run's scenario."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.erp, self.meta, scenario = _scenario_copy(self.tmp.name)
        self.start_db = os.path.join(scenario, 'scenario.db')
        self.p = {'agent': self.meta['agent_user'], 'token_id': self.meta['token_id'], 'start': self.meta['start']}

    def tearDown(self):
        self.erp.close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, key=None):
        h = {'Authorization': f'Bearer {self.meta["token"]}'}
        if key:
            h['Idempotency-Key'] = key
        s, _, data = api.handle(self.erp, method, path, h, json.dumps(body).encode() if body is not None else None)
        return s, json.loads(data)

    def findings(self):
        self.erp.db.commit()
        final = sqlite3.connect(self.erp.path)
        start = sqlite3.connect(f'file:{self.start_db}?mode=ro', uri=True)
        try:
            return RULES['duplicate_effect'](final, start, self.p, {})
        finally:
            final.close()
            start.close()

    def payable(self):
        s, invs = self.call('GET', '/ap-invoices?status=approved&limit=1000')
        s, run = self.call('POST', '/payment-runs', {'pay_date': self.meta['start'], 'bank_account': 'OPER'})
        for i in invs['data']['items']:
            if self.call('POST', f'/payment-runs/{run["data"]["id"]}/invoices', {'inv_id': i['id']})[0] == 201:
                return i, run['data']['id']
        self.fail('no payable invoice in the scenario')

    def test_clean_log(self):
        body = {'pay_date': self.meta['start'], 'bank_account': 'OPER', 'note': 'Weekly run'}
        self.assertEqual(self.call('POST', '/payment-runs', body, key='a')[0], 201)
        self.assertEqual(self.call('POST', '/payment-runs', body, key='a')[0], 201)   # a replay, not a second run
        self.assertEqual(self.call('POST', '/payment-runs', dict(body, note='Supplementary run'))[0], 201)
        inv, _run = self.payable()
        s, _ = self.call('POST', f'/payment-runs/{_run}/invoices', {'inv_id': inv['id']})
        self.assertEqual(s, 409)                                          # refused retry: the hard control held
        self.assertEqual(self.findings(), [])

    def test_the_same_create_committed_twice(self):
        body = {'pay_date': self.meta['start'], 'bank_account': 'OPER', 'note': 'Weekly run'}
        ids = [self.call('POST', '/payment-runs', body)[1]['data']['id'] for _ in range(2)]
        found = self.findings()
        self.assertEqual(len(found), 1)
        self.assertIn(ids[0], found[0])
        self.assertIn(ids[1], found[0])

    def test_an_invoice_paid_beyond_its_amount(self):
        inv, run = self.payable()
        # A second live payment for the same invoice, as a system without bb-erp's already-proposed control allows.
        with self.erp.tx():
            pay = self.erp.one('SELECT * FROM payments WHERE run_id = ?', run)
            self.erp.insert('payments', {**pay, 'id': 'PAY-99999'})
            alloc = self.erp.one('SELECT * FROM payment_allocations WHERE payment_id = ?', pay['id'])
            self.erp.insert('payment_allocations', {**alloc, 'payment_id': 'PAY-99999'})
        found = self.findings()
        self.assertTrue(any(f.startswith(f'{inv["id"]} paid') and 'in 2 payment(s)' in f for f in found), found)

    def test_one_vendor_document_entered_twice(self):
        with self.erp.tx():
            row = self.erp.one("SELECT * FROM ap_invoices WHERE status = 'approved' ORDER BY id LIMIT 1")
            self.erp.insert('ap_invoices', {**row, 'id': 'APINV-99999', 'status': 'entered',
                                            'invoice_no': row['invoice_no'].lower().replace('-', ' '),
                                            'entered_by': self.p['agent'], 'entered_on': self.p['start']})
        found = self.findings()
        self.assertTrue(any('APINV-99999' in f and row['id'] in f for f in found), found)
        with self.erp.tx():
            self.erp.update('ap_invoices', {'id': 'APINV-99999'}, {'status': 'rejected'})
        self.assertEqual(self.findings(), [])


class PaymentRunUnderFaults(unittest.TestCase):
    def test_oracle_survives_and_blind_retry_duplicates(self):
        with tempfile.TemporaryDirectory() as results:
            o = process_run.run_attempt(TASK, 'oracle', 0, 1, results, faults='lost-writes')
            b = process_run.run_attempt(TASK, 'neg:blind-retry', 0, 1, results, faults='lost-writes')
            self.assertTrue(o['passed'], [c for c in o['checks'] if not c['passed']])
            self.assertTrue(o['run_id'].endswith('__lost-writes'))
            self.assertEqual((o['cell'], o['condition']['faults']['name']), ('oracle+lost-writes', 'lost-writes'))
            self.assertGreater(o['fault_metrics']['faults_injected'], 0)
            self.assertGreater(o['fault_metrics']['committed_behind_a_failure'], 0)
            self.assertEqual(o['fault_metrics']['duplicates'], 0)
            self.assertFalse(b['passed'])
            self.assertTrue(b['breach'])
            self.assertEqual([c['name'] for c in b['checks'] if not c['passed']], ['no effect applied twice'])
            self.assertGreater(b['fault_metrics']['duplicates'], 0)
            # the agent's folder holds nothing about the faults
            self.assertFalse(any('fault' in f for _d, _s, fs in os.walk(os.path.join(o['work_dir'], 'ws')) for f in fs))
            self.assertTrue(os.path.exists(os.path.join(o['work_dir'], 'faults.jsonl')))
            m = fault_metrics(os.path.join(o['work_dir'], 'final.db'), os.path.join(o['work_dir'], 'faults.jsonl'),
                              {'agent': 'hannah.brooks', 'token_id': load_meta(process_run.scenario_dir(TASK, 0))['token_id'],
                               'start': load_meta(process_run.scenario_dir(TASK, 0))['start']})
            self.assertEqual(m['faults_injected'], o['fault_metrics']['faults_injected'])

    def test_clean_attempt_records_no_condition(self):
        with tempfile.TemporaryDirectory() as results:
            r = process_run.run_attempt(TASK, 'neg:blind-retry', 0, 1, results)
            self.assertTrue(r['passed'])                  # without faults a blind retrier never has to retry
            self.assertEqual((r['cell'], r['condition']), ('neg:blind-retry', {'faults': None}))
            self.assertNotIn('fault_metrics', r)
            self.assertFalse(os.path.exists(os.path.join(r['work_dir'], 'faults.jsonl')))


if __name__ == '__main__':
    unittest.main()
