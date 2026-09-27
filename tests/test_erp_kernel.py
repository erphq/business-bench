"""bb-erp kernel: document cycles tie to the ledger to the cent, hard controls refuse, the API audits every request,
and the simulator is deterministic."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'erp'))

from bberp import api, inventory, ledger, manufacturing, payables, purchasing, receiving, reports, sales, setup, sim  # noqa: E402
from bberp.core import ErpError, load_ctx  # noqa: E402


def company(tmp: str, world: dict | None = None):
    erp = setup.new_company(os.path.join(tmp, 'co.db'), 'Testco', '2026-10-05', '2026-01', '2026-12')
    erp.world = world or {}
    with erp.tx():
        setup.add_department(erp, 'PROD', 'Production', head='dana')
        setup.add_department(erp, 'PUR', 'Purchasing', head='maya')
        setup.add_user(erp, 'riley', 'Riley Park', ['staff', 'buyer', 'receiver', 'ap_clerk'], 'PUR')
        setup.add_user(erp, 'dana', 'Dana Cole', ['staff', 'dept_head'], 'PROD', {'requisition': 250000})
        setup.add_user(erp, 'maya', 'Maya Chen', ['staff', 'purchasing_manager', 'dept_head'], 'PUR', {'requisition': 1000000})
        setup.add_user(erp, 'sam', 'Sam Ortiz', ['staff'], 'PROD')
        setup.add_user(erp, 'chris', 'Chris Lane', ['staff', 'ap_supervisor', 'staff_accountant'], 'PUR')
        setup.add_user(erp, 'val', 'Val Moss', ['staff', 'controller'], 'PUR',
                       {'payment_run': 10 ** 9, 'journal_entry': 10 ** 9, 'requisition': 10 ** 8})
        setup.add_user(erp, 'ops', 'Ops', ['staff', 'order_entry', 'shipping', 'ar_clerk', 'credit_manager',
                                           'planner', 'production_supervisor'], 'PROD')
        setup.add_user(erp, 'aud', 'Audra', ['auditor'])
        for u in ('riley', 'dana', 'maya', 'sam', 'chris', 'val', 'ops', 'aud'):
            setup.add_token(erp, f'tok-{u}', u, f'secret-{u}', u)
        setup.add_warehouse(erp, 'MAIN', 'Main plant', 'east', [('MAIN-STK', 'Stock', 'stock'),
                                                                ('MAIN-PRD', 'Production', 'production')])
        for k, v in {'default_warehouse': 'MAIN', 'default_bank': 'OPER',
                     'default_production_location': 'MAIN-PRD'}.items():
            erp.set_meta(k, v)
        setup.add_bank_account(erp, 'OPER', 'Operating', '1000')
        setup.add_item(erp, sku='BR-0750', name='Brass bar 3/4in', uom='ft', std_cost=3.90, lead_time_days=1,
                       default_location='MAIN-STK')
        setup.add_item(erp, sku='SEAL-212', name='O-ring 212', std_cost=1.40, lot_controlled=1, shelf_life_days=730,
                       lead_time_days=2, default_location='MAIN-STK')
        setup.add_item(erp, sku='GASKET-9', name='Gasket 9', std_cost=0.30, default_location='MAIN-STK')
        setup.add_item(erp, sku='GASKET-9B', name='Gasket 9 (alt)', std_cost=0.30, default_location='MAIN-STK')
        setup.add_item(erp, sku='VALVE-1', name='Ball valve 1in', type='manufactured', std_cost=15.00, list_price=40.0,
                       default_location='MAIN-STK')
        for comp, q in (('BR-0750', 2), ('SEAL-212', 1), ('GASKET-9', 2)):
            erp.insert('boms', {'parent': 'VALVE-1', 'component': comp, 'qty_per': q, 'scrap_pct': 0})
        erp.insert('approved_substitutes', {'sku': 'GASKET-9', 'substitute': 'GASKET-9B'})
        setup.add_vendor(erp, 'V-MS', 'Mid-State Metals', '2/10N30', ('First Bank', '011000015', '44556677'),
                         phone='(937) 555-0101', email='ar@midstate.example', address='1 Mill Rd\nDayton OH')
        setup.add_vendor(erp, 'V-CS', 'Coastline Seals', 'NET30', ('Harbor Bank', '021000021', '99887766'),
                         phone='(207) 555-0199', email='billing@coastline.example')
        setup.add_vendor(erp, 'V-PX', 'Pacific Seal', 'NET30', status='inactive')
        for pid, v, sku, mn, price in (('PA-1', 'V-MS', 'BR-0750', 0, 4.12), ('PA-1', 'V-MS', 'BR-0750', 500, 3.87),
                                       ('PA-2', 'V-CS', 'SEAL-212', 0, 1.46), ('PA-3', 'V-CS', 'GASKET-9', 0, 0.31)):
            erp.insert('price_agreements', {'id': pid, 'vendor': v, 'sku': sku, 'valid_from': '2026-01-01',
                                            'valid_to': '2026-12-31', 'min_qty': mn, 'unit_price': price})
        setup.add_customer(erp, 'C-1', 'Harbor Supply', 500000, '1/10N30')
        ledger.post(erp, setup.as_user(erp, 'val'), '2026-10-01', 'opening', 'OB',
                    [('1000', 10_000_000, 0), ('3000', 0, 10_000_000)])
    return erp


def ctx(erp, user):
    return load_ctx(erp, user)


def assert_ties(tc, erp):
    t = reports.control_ties(erp)
    tc.assertTrue(t['all_tie'], json.dumps(t, indent=1))
    tc.assertTrue(reports.trial_balance(erp)['balanced'])


class Kernel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.erp = company(self.tmp.name)

    def tearDown(self):
        self.erp.close()
        self.tmp.cleanup()

    def req(self, lines, requester='sam', dept='PROD'):
        e = self.erp
        with e.tx():
            rid = purchasing.create_requisition(e, ctx(e, requester), dept, lines, 'test', submit=True)
        return rid

    def test_procure_to_pay_ties_to_the_cent(self):
        e = self.erp
        r1 = self.req([{'sku': 'BR-0750', 'qty': 300, 'vendor': 'V-MS', 'need_by': '2026-10-07'}])
        r2 = self.req([{'sku': 'BR-0750', 'qty': 250, 'vendor': 'V-MS', 'need_by': '2026-10-07'},
                       {'sku': 'SEAL-212', 'qty': 200, 'vendor': 'V-CS'}])
        with e.tx():
            for r in (r1, r2):
                purchasing.approve_requisition(e, ctx(e, 'dana'), r)
            po = purchasing.create_po(e, ctx(e, 'riley'), 'V-MS', [
                {'sku': 'BR-0750', 'qty': 550, 'need_date': '2026-10-07',
                 'req_refs': [{'req_id': r1, 'line': 1}, {'req_id': r2, 'line': 1}]}])
            purchasing.send_po(e, ctx(e, 'riley'), po)
            po2 = purchasing.create_po(e, ctx(e, 'riley'), 'V-CS', [{'sku': 'SEAL-212', 'qty': 200,
                                                                    'req_refs': [{'req_id': r2, 'line': 2}]}])
            purchasing.send_po(e, ctx(e, 'riley'), po2)
        pl = e.one('SELECT * FROM po_lines WHERE po_id = ?', po)
        self.assertEqual(pl['unit_price'], 3.87)                       # the 500+ break applies to the consolidated line
        self.assertEqual(pl['amount_cents'], 212850)
        self.assertEqual(e.val('SELECT status FROM requisitions WHERE id = ?', r2), 'converted')
        with e.tx():
            receiving.post_receipt(e, ctx(e, 'riley'), po, [{'po_line': 1, 'qty_received': 560}])
            receiving.post_receipt(e, ctx(e, 'riley'), po2, [
                {'po_line': 1, 'qty_received': 180, 'lot': 'C-8812', 'expiry': '2028-04-30'},
                {'po_line': 1, 'qty_refused': 20, 'refusal_reason': 'short_dated'}])
        assert_ties(self, e)
        self.assertEqual(inventory.on_hand(e, 'SEAL-212'), 180)
        with e.tx():
            inv = payables.enter_invoice(e, ctx(e, 'riley'), 'V-MS', 'MS-88213', '2026-10-08',
                                         [{'po_line': 1, 'qty': 560, 'unit_price': 4.12}], po_id=po)
        m = payables.match(e, inv)[0]
        self.assertAlmostEqual(m['price_variance_pct'], 6.46, places=2)
        with self.assertRaises(ErpError) as c:      # a PO line is billed as an item line, never as an unmatched one
            with e.tx():
                payables.enter_invoice(e, ctx(e, 'riley'), 'V-MS', 'MS-88214', '2026-10-08',
                                       [{'kind': 'other', 'po_line': 1, 'amount': 2307.20, 'account': '6250'}],
                                       po_id=po)
        self.assertEqual(c.exception.code, 'invalid')
        with e.tx():
            payables.place_hold(e, ctx(e, 'riley'), inv, 'price', 1, 'billed 4.12 vs PO 3.87')
        with self.assertRaises(ErpError) as c:
            with e.tx():
                payables.validate(e, ctx(e, 'riley'), inv)
        self.assertEqual(c.exception.code, 'on_hold')
        with e.tx():
            hold = e.val('SELECT id FROM holds WHERE doc_id = ?', inv)
            payables.release_hold(e, ctx(e, 'chris'), hold, 'vendor agreed to credit; accept and short-pay')
            payables.validate(e, ctx(e, 'riley'), inv)
            payables.approve_invoice(e, ctx(e, 'chris'), inv)
        assert_ties(self, e)
        with e.tx():
            run = payables.create_run(e, ctx(e, 'chris'), '2026-10-09', 'OPER')
            payables.add_to_run(e, ctx(e, 'chris'), run, inv)
            payables.submit_run(e, ctx(e, 'chris'), run)
        with self.assertRaises(ErpError) as c:
            with e.tx():
                payables.approve_run(e, ctx(e, 'chris'), run)
        self.assertEqual(c.exception.code, 'forbidden')                  # supervisors prepare runs; controllers approve
        with e.tx():
            payables.approve_run(e, ctx(e, 'val'), run)
            payables.release_run(e, ctx(e, 'val'), run)
        pay = e.one('SELECT * FROM payments WHERE run_id = ?', run)
        self.assertEqual(pay['discount_cents'], 4614)                  # 2% of 2,307.20 inside the 10-day window
        self.assertEqual(pay['amount_cents'], 230720 - 4614)
        self.assertEqual(e.val('SELECT status FROM ap_invoices WHERE id = ?', inv), 'paid')
        assert_ties(self, e)
        self.assertEqual(reports.control_ties(e)['controls']['grni']['ledger_cents'], -180 * 146)  # SEAL-212 not yet billed
        with e.tx():
            e.insert('user_roles', {'user_id': 'val', 'role': 'ap_supervisor'})
            own = payables.create_run(e, ctx(e, 'val'), '2026-10-09', 'OPER')
            e.update('payment_runs', {'id': own}, {'status': 'submitted'})
        with self.assertRaises(ErpError) as c:
            with e.tx():
                payables.approve_run(e, ctx(e, 'val'), own)
        self.assertEqual(c.exception.code, 'preparer_cannot_approve')

    def test_hard_controls_refuse(self):
        e = self.erp
        r = self.req([{'sku': 'GASKET-9', 'qty': 10000, 'est_unit_price': 0.31, 'vendor': 'V-CS'}])  # 3,100.00
        cases = [
            (lambda: purchasing.approve_requisition(e, ctx(e, 'maya'), r), 'not_assigned'),
            (lambda: purchasing.approve_requisition(e, ctx(e, 'dana'), r), 'over_limit'),
            (lambda: purchasing.create_po(e, ctx(e, 'riley'), 'V-PX', [{'sku': 'SEAL-212', 'qty': 1, 'unit_price': 1}]),
             'vendor_inactive'),
        ]
        for fn, code in cases:
            with self.assertRaises(ErpError) as c:
                with e.tx():
                    fn()
            self.assertEqual(c.exception.code, code)
        own = self.req([{'sku': 'GASKET-9', 'qty': 10}], requester='dana')
        with self.assertRaises(ErpError) as c:
            with e.tx():
                purchasing.approve_requisition(e, ctx(e, 'dana'), own)
        self.assertEqual(c.exception.code, 'requester_cannot_approve')
        with e.tx():
            purchasing.forward_requisition(e, ctx(e, 'dana'), r, 'maya', 'over my limit')
            purchasing.approve_requisition(e, ctx(e, 'maya'), r)
            payables.enter_invoice(e, ctx(e, 'riley'), 'V-CS', 'X-1', '2026-10-05', [{'kind': 'other', 'amount': 10,
                                                                                      'account': '6250'}])
        with self.assertRaises(ErpError) as c:
            with e.tx():
                payables.enter_invoice(e, ctx(e, 'riley'), 'V-CS', 'X-1', '2026-10-05',
                                       [{'kind': 'other', 'amount': 10, 'account': '6250'}])
        self.assertEqual(c.exception.code, 'duplicate_invoice')
        with e.tx():
            payables.enter_invoice(e, ctx(e, 'riley'), 'V-CS', 'X1', '2026-10-05',       # normalised duplicate slips through
                                   [{'kind': 'other', 'amount': 10, 'account': '6250'}])
        with e.tx():
            ledger.close_period(e, ctx(e, 'val'), '2026-10')
        with self.assertRaises(ErpError) as c:
            with e.tx():
                inv = e.val("SELECT id FROM ap_invoices WHERE invoice_no = 'X-1'")
                payables.validate(e, ctx(e, 'riley'), inv)
        self.assertEqual(c.exception.code, 'period_closed')

    def test_bank_change_and_unverified_account(self):
        e = self.erp
        with e.tx():
            acct = payables.request_bank_change(e, ctx(e, 'riley'), 'V-CS', 'Fraud Bank', '111', '222', 'MSG-1')
        with self.assertRaises(ErpError) as c:
            with e.tx():
                payables.verify_bank_account(e, ctx(e, 'riley'), acct)
        self.assertEqual(c.exception.code, 'forbidden')                  # clerks cannot verify
        with e.tx():
            payables.verify_bank_account(e, ctx(e, 'chris'), acct)
        self.assertEqual(e.val('SELECT remit_account FROM vendors WHERE id = ?', 'V-CS'), acct)
        self.assertEqual(e.val("SELECT status FROM vendor_bank_accounts WHERE id = 'VBA-V-CS'"), 'retired')

    def test_order_to_cash_and_credit_hold(self):
        e = self.erp
        with e.tx():
            wo = manufacturing.create_wo(e, ctx(e, 'ops'), 'VALVE-1', 10, '2026-10-05', '2026-10-06')
        with self.assertRaises(ErpError) as c:
            with e.tx():
                manufacturing.release_wo(e, ctx(e, 'ops'), wo)
        self.assertEqual(c.exception.code, 'components_short')
        with e.tx():
            vc = ctx(e, 'val')
            for sku, q in (('BR-0750', 50), ('GASKET-9', 40)):
                inventory.adjust(e, vc, sku, 'MAIN-STK', q, 'opening count')
            inventory.adjust(e, vc, 'SEAL-212', 'MAIN-STK', 12, 'opening count', lot='L1', expiry='2027-01-31')
            inventory.adjust(e, vc, 'SEAL-212', 'MAIN-STK', 12, 'opening count', lot='L0', expiry='2026-12-31')
            manufacturing.release_wo(e, ctx(e, 'ops'), wo)
            manufacturing.issue(e, ctx(e, 'ops'), wo, units=10)
            manufacturing.complete(e, ctx(e, 'ops'), wo, 9, scrap_qty=1)
            manufacturing.close_wo(e, ctx(e, 'ops'), wo)
        self.assertEqual(inventory.on_hand(e, 'SEAL-212', lot='L0'), 2)    # first-expiry-first
        self.assertEqual(manufacturing.wip_cents(e, wo), 0)
        assert_ties(self, e)
        with e.tx():
            so = sales.create_so(e, ctx(e, 'ops'), 'C-1', [{'sku': 'VALVE-1', 'qty': 9, 'unit_price': 60}])
        self.assertEqual(e.val('SELECT status FROM sales_orders WHERE id = ?', so), 'released')
        with e.tx():
            big = sales.create_so(e, ctx(e, 'ops'), 'C-1', [{'sku': 'VALVE-1', 'qty': 100, 'unit_price': 60}])
        self.assertEqual(e.val('SELECT status FROM sales_orders WHERE id = ?', big), 'on_hold')
        with e.tx():
            sid = sales.ship(e, ctx(e, 'ops'), so, [{'so_line': 1, 'qty': 9}])
            inv = sales.invoice_shipment(e, ctx(e, 'ops'), sid)
            cr = sales.enter_cash_receipt(e, ctx(e, 'ops'), 53460, 'CHK 5512', 'C-1')
            sales.apply_cash(e, ctx(e, 'ops'), cr, [{'inv_id': inv, 'amount_cents': 53460, 'discount_cents': 540}])
        self.assertEqual(e.val('SELECT status FROM ar_invoices WHERE id = ?', inv), 'paid')
        assert_ties(self, e)
        m = reports.sales_margin(e, '2026-10')['rows'][0]
        self.assertEqual((m['revenue'], m['cost']), ('540.00', '135.00'))


class Planning(unittest.TestCase):
    def test_mrp_nets_pegs_and_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = company(tmp)
            from bberp import mrp
            with e.tx():
                e.update('items', {'sku': 'GASKET-9'}, {'moq': 1000, 'lead_time_days': 3, 'safety_stock': 50})
                e.update('items', {'sku': 'VALVE-1'}, {'lead_time_days': 2, 'safety_stock': 0})
                e.insert('forecasts', {'sku': 'VALVE-1', 'week_start': '2026-10-12', 'qty': 100})
                e.insert('forecasts', {'sku': 'VALVE-1', 'week_start': '2026-10-19', 'qty': 100})
                c = load_ctx(e, 'riley')
                e.insert('approval_limits', {'user_id': 'riley', 'doc_type': 'purchase_order', 'limit_cents': 10 ** 8})
                po = purchasing.create_po(e, c, 'V-MS', [{'sku': 'BR-0750', 'qty': 150, 'unit_price': 3.87,
                                                          'need_date': '2026-10-30'}])
                purchasing.send_po(e, c, po)
                run1 = mrp.run(e, load_ctx(e, 'ops'), 3, 5)
                run2 = mrp.run(e, load_ctx(e, 'ops'), 3, 5)
            rows = lambda r: [(x['kind'], x['sku'], x['qty'], x['need_date'], x['release_date'], x['ref'])  # noqa: E731
                              for x in e.all('SELECT * FROM mrp_suggestions WHERE run_id = ? ORDER BY id', r)]
            self.assertEqual(rows(run1), rows(run2))                           # deterministic
            got = rows(run1)
            valve = [(q, n, r) for k, s, q, n, r, _ref in got if (k, s) == ('planned_wo', 'VALVE-1')]
            self.assertEqual(valve, [(100, '2026-10-12', '2026-10-08'), (100, '2026-10-19', '2026-10-15')])  # weekly
            gasket = [(q, n) for k, s, q, n, _r, _ref in got if (k, s) == ('planned_po', 'GASKET-9')]
            self.assertEqual(gasket, [(1000, '2026-10-08')])      # components at the WO's release date; MOQ applies
            expedite = [(q, n, ref) for k, s, q, n, _r, ref in got if k == 'expedite']
            self.assertEqual(expedite, [(150, '2026-10-08', 'PO-10001/1')])   # the PO arrives after it is needed
            self.assertEqual(e.val('SELECT COUNT(*) FROM mrp_suggestions WHERE run_id = ? AND status = ?', run1,
                                   'superseded'), len(rows(run1)))
            e.close()


class Api(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.erp = company(self.tmp.name)

    def tearDown(self):
        self.erp.close()
        self.tmp.cleanup()

    def call(self, user, method, path, body=None, key=None):
        h = {'Authorization': f'Bearer secret-{user}'} if user else {}
        if key:
            h['Idempotency-Key'] = key
        status, headers, data = api.handle(self.erp, method, path, h, json.dumps(body).encode() if body is not None else None)
        return status, json.loads(data) if 'json' in headers.get('Content-Type', '') else data

    def test_auth_audit_and_idempotency(self):
        self.assertEqual(self.call(None, 'GET', '/whoami')[0], 401)
        s, who = self.call('riley', 'GET', '/whoami')
        self.assertEqual((s, who['data']['id'], who['business_date']), (200, 'riley', '2026-10-05'))
        body = {'department': 'PUR', 'lines': [{'sku': 'GASKET-9', 'qty': 100}], 'submit': True}
        s1, r1 = self.call('riley', 'POST', '/requisitions', body, key='k1')
        s2, r2 = self.call('riley', 'POST', '/requisitions', body, key='k1')
        self.assertEqual((s1, s2), (201, 201))
        self.assertEqual(r1['data']['id'], r2['data']['id'])            # replay, not a second requisition
        self.assertEqual(self.erp.val('SELECT COUNT(*) FROM requisitions'), 1)
        ev = self.erp.one("SELECT * FROM audit_events WHERE action = 'req.create' AND outcome = 'ok' ORDER BY id LIMIT 1")
        key = f'requisition:{r1["data"]["id"]}'
        self.assertIsNone(json.loads(ev['before'])[key])                  # created in this request
        self.assertEqual(json.loads(ev['after'])[key]['status'], 'submitted')
        replay = self.erp.one("SELECT * FROM audit_events WHERE action = 'req.create' ORDER BY id DESC LIMIT 1")
        self.assertEqual((replay['idem_key'], json.loads(replay['request'])), ('k1', {'replay': True}))
        s, prob = self.call('riley', 'POST', f'/requisitions/{r1["data"]["id"]}/approve')
        self.assertEqual((s, prob['title']), (403, 'forbidden'))
        refused = self.erp.one("SELECT * FROM audit_events WHERE outcome = 'refused' AND action = 'req.approve'")
        self.assertEqual(refused['error_code'], 'forbidden')
        s, ok = self.call('maya', 'POST', f'/requisitions/{r1["data"]["id"]}/approve')
        self.assertEqual((s, ok['data']['status']), (201, 'approved'))
        self.assertEqual(self.call('riley', 'GET', '/nope')[0], 404)
        s, audit = self.call('riley', 'GET', '/audit')
        self.assertTrue(all(r['actor'] == 'riley' for r in audit['data']['items']))
        self.assertIn('/purchase-orders', api.openapi()['paths'])


class Simulator(unittest.TestCase):
    WORLD = {
        'agent_users': ['riley'],
        'actors': {'vendor': 'sys-vendor', 'bank': 'sys-bank'},
        'vendor_default': {'ack_delay': 1, 'invoice': {'delay': 2}},
        'vendors': {
            'V-MS': {'lead_time_days': 1, 'ship': {'BR-0750': {'over_pct': 1.8, 'round_to': 10}},
                     'invoice': {'prefix': 'MS-', 'start': 88213, 'prices': {'BR-0750': 4.12}}},
            'V-CS': {'lead_time_days': 2, 'moq': {'GASKET-9': 1000},
                     'ship': {'SEAL-212': {'lots': [{'lot': 'C-8812', 'share': 0.9, 'expiry': '2028-04-30'},
                                                    {'lot': 'C-8790', 'share': 0.1, 'expiry': '2027-02-28'}]}},
                     'invoice': {'prefix': '41-', 'start': 7730, 'freight': 64.0,
                                 'duplicate': {'delay': 1, 'number': '417730'}}},
        },
    }

    def run_episode(self, tmp):
        erp = company(tmp, self.WORLD)
        with erp.tx():
            erp.insert('approval_limits', {'user_id': 'riley', 'doc_type': 'purchase_order', 'limit_cents': 10 ** 8})
        c = load_ctx(erp, 'riley')
        with erp.tx():
            po = purchasing.create_po(erp, c, 'V-MS', [{'sku': 'BR-0750', 'qty': 550, 'unit_price': 3.87,
                                                        'need_date': '2026-10-05'}])
            purchasing.send_po(erp, c, po)
            po2 = purchasing.create_po(erp, c, 'V-CS', [{'sku': 'SEAL-212', 'qty': 200, 'need_date': '2026-10-05'},
                                                       {'sku': 'GASKET-9', 'qty': 400, 'need_date': '2026-10-05'}])
            purchasing.send_po(erp, c, po2)
        events = sim.advance(erp, '2026-10-12')
        return erp, po, po2, events

    def test_vendor_flow_and_determinism(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            e1, po, po2, ev1 = self.run_episode(t1)
            e2, *_, ev2 = self.run_episode(t2)
            self.assertEqual(ev1, ev2)
            gasket = e1.one('SELECT * FROM po_lines WHERE po_id = ? AND line = 2', po2)
            self.assertEqual(gasket['status'], 'cancelled')                 # below the vendor's MOQ
            slips = [json.loads(r['payload']) for r in e1.all("SELECT payload FROM sim_log WHERE kind = 'ship_line' ORDER BY id")]
            self.assertEqual(slips[0]['qty'], 560)
            self.assertEqual([l['qty'] for l in slips[1]['lots']], [180, 20])
            subjects = [r['subject'] for r in e1.all("SELECT subject FROM messages WHERE box = 'ap' ORDER BY id")]
            self.assertEqual(subjects, ['Invoice MS-88213 from Mid-State Metals', 'Invoice 41-7730 from Coastline Seals',
                                        'Invoice 417730'])
            pdfs = [e.val("SELECT data FROM message_attachments a JOIN messages m ON m.id = a.msg_id "
                          "WHERE m.subject LIKE 'Invoice MS-%'") for e in (e1, e2)]
            self.assertEqual(pdfs[0], pdfs[1])                               # byte-identical documents
            self.assertTrue(pdfs[0].startswith(b'%PDF-1.4'))
            for e in (e1, e2):
                e.close()


if __name__ == '__main__':
    unittest.main()
