"""Twelve months of ordinary Northgate business, operated through bb-erp's services under the real users.

Policies (clean, no anomalies): the planner replenishes components on a reorder-point policy with POs inside his
limit; departments raise expense requisitions that go up the approval chain; the warehouse receives on the need
date; AP enters invoices as billed two workdays after receipt, validates and approves them; payment runs go out
every Friday and clear the next workday; production runs weekly; sales orders ship the next workday and are
invoiced; customers pay by profile; payroll, overheads and depreciation post on schedule; periods close on the
fourth workday of the following month, up to `close_through`.
"""
from __future__ import annotations

import math
from datetime import timedelta

from bberp import inventory, ledger, manufacturing, payables, purchasing, receiving, sales, setup  # noqa: F401
from bberp.core import Erp, add_days, ext_cents, parse_day, period_of, q4

from .northgate import CUSTOMERS, FINISHED, INVOICE_SERIES, ITEMS, VENDORS, rng

WAGES = {'ADMIN': 7000, 'FIN': 8000, 'PUR': 5000, 'WH': 4500, 'PROD': 12500, 'MAINT': 4000, 'QA': 3000, 'SALES': 5500}
MRO = [  # department, requester, vendor key, account, description, monthly dollars range
    ('MAINT', 'aisha.okafor', 'greatlakes', '6200', 'Maintenance parts: bearings, belts, filters', (1200, 2600)),
    ('PROD', 'mateo.garcia', 'greatlakes', '6250', 'Shop supplies: cutting fluid, inserts, rags', (700, 1500)),
    ('QA', 'alex.ng', 'greatlakes', '6250', 'Gauge calibration supplies', (250, 700)),
    ('ADMIN', 'omar.haddad', 'greatlakes', '6300', 'Office supplies', (150, 450)),
]
APPROVAL_CHAIN = ['maya.chen', 'priya.raman', 'erin.walsh']


# department, account, monthly budget in dollars (fiscal year = calendar year)
BUDGETS = [(d, '6000', w * 1.03) for d, w in WAGES.items()] + [(d, '6050', w * 0.2 * 1.03) for d, w in WAGES.items()] + [
    ('ADMIN', '6100', 8000), ('PROD', '6150', 3700), ('MAINT', '6200', 2100), ('PROD', '6250', 1200),
    ('QA', '6250', 500), ('MAINT', '6250', 400), ('ADMIN', '6300', 320), ('ADMIN', '6450', 1500),
    ('PROD', '6550', 3200)]


def install_budgets(erp: Erp, years: list[int]) -> None:
    for y in years:
        for m in range(1, 13):
            for dept, acct, dollars in BUDGETS:
                erp.insert('budgets', {'department': dept, 'account': acct, 'period': f'{y}-{m:02d}',
                                       'amount_cents': round(dollars * 100)})


def monthly_component_need() -> dict[str, float]:
    need: dict[str, float] = {}
    for sku, (_n, _p, base, bom) in FINISHED.items():
        for comp, q in bom:
            need[comp] = need.get(comp, 0) + base * q
    return need


class History:
    def __init__(self, erp: Erp, seed: int, start: str, end: str, close_through: str, events: dict | None = None,
                 skip_month_end: set | None = None):
        self.erp, self.seed, self.start, self.end, self.close_through = erp, seed, start, end, close_through
        self.events = events or {}
        self.skip_month_end = skip_month_end or set()
        self.r = rng(seed, 'history')
        self.inv_no = {k: v[1] for k, v in INVOICE_SERIES.items()}
        self.vkey = {v[0]: k for k, v in VENDORS.items()}
        self.need = monthly_component_need()
        self.pending_ship: list[str] = []
        self.sales_credit = 0.0
        self.short_weeks: list[tuple] = []

    def ctx(self, user: str):
        return setup.as_user(self.erp, user)

    # ------------------------------------------------------------------------------------------- driver
    def run(self) -> None:
        erp, day = self.erp, self.start
        while day <= self.end:
            with erp.tx():
                erp.set_today(day)
                if erp.is_workday(day):
                    self.workday(day)
            day = add_days(day, 1)

    def nth_workday(self, day: str) -> int:
        return sum(1 for d in setup.month_days(self.erp, period_of(day)) if d <= day)

    def first_workday_of_week(self, day: str) -> bool:
        d = parse_day(day)
        monday = (d - timedelta(days=d.weekday())).isoformat()
        return day == (monday if self.erp.is_workday(monday) else self.erp.add_workdays(monday, 1))

    def last_workday(self, day: str) -> bool:
        return setup.month_days(self.erp, period_of(day))[-1] == day

    def workday(self, day: str) -> None:
        n = self.nth_workday(day)
        self.bank_clear(day)
        for fn in self.events.get(day, []):
            fn(self.erp, self)
        if n == 1:
            self.rent(day)
            self.mro_requisitions(day)
        if n == 4:
            self.close_previous(day)
        if self.first_workday_of_week(day):
            self.replenish(day)
            self.produce(day)
        self.convert_requisitions(day)
        self.receive(day)
        self.vendor_invoices(day)
        self.ship_and_bill(day)
        self.new_orders(day)
        self.customer_payments(day)
        if n == 14:
            self.utilities(day)
        if n == 11 or self.last_workday(day):
            self.payroll(day)
        if parse_day(day).weekday() == 4:
            self.payment_run(day)
        if self.last_workday(day) and period_of(day) not in self.skip_month_end:
            self.month_end_entries(day)

    # ------------------------------------------------------------------------------------------- purchasing
    def replenish(self, day: str) -> None:
        erp, ctx = self.erp, self.ctx('jordan.lee')
        orders: dict[str, list] = {}
        for sku, monthly in sorted(self.need.items()):
            it = erp.one('SELECT * FROM items WHERE sku = ?', sku)
            daily = monthly / 21
            on_hand = inventory.on_hand(erp, sku)
            on_order = erp.val("SELECT COALESCE(SUM(l.qty - l.qty_received), 0) FROM po_lines l JOIN purchase_orders p "
                               "ON p.id = l.po_id WHERE l.sku = ? AND l.status = 'open' AND p.status IN "
                               "('sent', 'partially_received')", sku)
            rop = daily * (it['lead_time_days'] + 5) + it['safety_stock']
            if on_hand + on_order >= rop:
                continue
            target = daily * (it['lead_time_days'] + 15) + it['safety_stock']
            step = 10 if it['uom'] == 'ft' else 50
            qty = max(math.ceil((target - on_hand - on_order) / step) * step, it['moq'] or 0)
            orders.setdefault(it['preferred_vendor'], []).append((sku, qty, it['lead_time_days']))
        for vendor, lines in sorted(orders.items()):
            batch, total = [], 0
            for sku, qty, lead in lines:
                price = purchasing.agreement_price(erp, vendor, sku, qty, day)
                chunks = max(1, math.ceil(ext_cents(qty, price) / 2_400_000))
                sizes = [qty // chunks] * chunks
                sizes[-1] += qty - sum(sizes)
                for q in sizes:
                    a = ext_cents(q, purchasing.agreement_price(erp, vendor, sku, q, day))
                    if total + a > 2_400_000 and batch:
                        self._send(ctx, vendor, batch)
                        batch, total = [], 0
                    batch.append({'sku': sku, 'qty': q, 'need_date': erp.add_workdays(day, lead)})
                    total += a
            if batch:
                self._send(ctx, vendor, batch)

    def _send(self, ctx, vendor: str, lines: list[dict]) -> str:
        po = purchasing.create_po(self.erp, ctx, vendor, lines, 'DAY')
        purchasing.send_po(self.erp, ctx, po)
        return po

    def mro_requisitions(self, day: str) -> None:
        erp = self.erp
        for dept, requester, vkey, acct, desc, (lo, hi) in MRO:
            amount = round(self.r.uniform(lo, hi), 2)
            rid = purchasing.create_requisition(erp, self.ctx(requester), dept, [
                {'description': desc, 'qty': 1, 'est_unit_price': amount, 'vendor': VENDORS[vkey][0], 'account': acct,
                 'ship_to': 'DAY', 'need_by': erp.add_workdays(day, 5)}], f'Monthly {desc.lower()}', submit=True)
            approver = purchasing.pending_request(erp, rid)['approver']
            if approver == requester:          # a head's own request goes to their manager
                approver = erp.val('SELECT manager FROM users WHERE id = ?', requester)
                purchasing.forward_requisition(erp, self.ctx(requester), rid, approver, 'my own request')
            self._approve_up(rid, approver)

    def _approve_up(self, rid: str, approver: str) -> None:
        erp = self.erp
        total = erp.val('SELECT total_cents FROM requisitions WHERE id = ?', rid)
        who = approver
        while True:
            lim = erp.val("SELECT limit_cents FROM approval_limits WHERE user_id = ? AND doc_type = 'requisition'", who) or 0
            if total <= lim:
                purchasing.approve_requisition(erp, self.ctx(who), rid, 'OK')
                return
            nxt = next(u for u in APPROVAL_CHAIN if (erp.val(
                "SELECT limit_cents FROM approval_limits WHERE user_id = ? AND doc_type = 'requisition'", u) or 0) > lim)
            purchasing.forward_requisition(erp, self.ctx(who), rid, nxt, 'over my limit')
            who = nxt

    def convert_requisitions(self, day: str) -> None:
        erp, ctx = self.erp, self.ctx('riley.park')
        rows = erp.all("SELECT l.*, r.department FROM requisition_lines l JOIN requisitions r ON r.id = l.req_id "
                       "WHERE r.status = 'approved' AND l.po_id IS NULL ORDER BY l.req_id, l.line")
        by_vendor: dict[str, list] = {}
        for l in rows:
            by_vendor.setdefault(l['vendor'], []).append(l)
        for vendor, ls in sorted(by_vendor.items()):
            lines = [{'sku': l['sku'], 'description': l['description'], 'qty': l['qty'],
                      'unit_price': l['est_unit_price'], 'account': l['account'], 'need_date': l['need_by'] or day,
                      'req_refs': [{'req_id': l['req_id'], 'line': l['line']}]} for l in ls]
            self._send(ctx, vendor, lines)

    def receive(self, day: str) -> None:
        erp, ctx = self.erp, self.ctx('luis.ortega')
        for po in erp.all("SELECT * FROM purchase_orders WHERE status IN ('sent', 'partially_received') ORDER BY id"):
            lines = []
            for pl in erp.all("SELECT * FROM po_lines WHERE po_id = ? AND status = 'open' AND need_date <= ? "
                              "AND qty_received < qty ORDER BY line", po['id'], day):
                ln = {'po_line': pl['line'], 'qty_received': q4(pl['qty'] - pl['qty_received'])}
                if pl['sku'] and ITEMS.get(pl['sku'], (None,) * 9)[7]:
                    shelf = ITEMS[pl['sku']][8]
                    ln.update({'lot': f'{pl["sku"][-3:]}-{parse_day(day).strftime("%y%m%d")}-{pl["line"]}',
                               'expiry': add_days(day, shelf - self.r.randint(60, 240))})
                lines.append(ln)
            if lines:
                receiving.post_receipt(erp, ctx, po['id'], lines, packing_slip=f'PS-{po["id"][-5:]}')

    def vendor_invoices(self, day: str) -> None:
        erp = self.erp
        ready = erp.add_workdays(day, -2)
        for r in erp.all("SELECT r.*, p.vendor FROM receipts r JOIN purchase_orders p ON p.id = r.po_id "
                         "WHERE r.status = 'posted' AND r.receipt_date <= ? AND NOT EXISTS (SELECT 1 FROM ap_invoices i "
                         "WHERE i.note = r.id) ORDER BY r.id", ready):
            key = self.vkey[r['vendor']]
            prefix, _ = INVOICE_SERIES[key]
            number = f'{prefix}{self.inv_no[key]}'
            self.inv_no[key] += 1
            lines = []
            for rl in erp.all('SELECT * FROM receipt_lines WHERE receipt_id = ? ORDER BY line', r['id']):
                pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', r['po_id'], rl['po_line'])
                lines.append({'kind': 'item', 'po_line': rl['po_line'], 'qty': rl['qty_received'],
                              'unit_price': pl['unit_price'], 'description': pl['description']})
            inv = payables.enter_invoice(erp, self.ctx('riley.park'), r['vendor'], number, add_days(r['receipt_date'], 1),
                                         lines, po_id=r['po_id'], note=r['id'])
            payables.validate(erp, self.ctx('riley.park'), inv)
            payables.approve_invoice(erp, self.ctx('hannah.brooks'), inv)

    def _non_po_invoice(self, day: str, vkey: str, amount: float, account: str, dept: str, desc: str) -> None:
        erp = self.erp
        prefix, _ = INVOICE_SERIES[vkey]
        number = f'{prefix}{self.inv_no[vkey]}'
        self.inv_no[vkey] += 1
        inv = payables.enter_invoice(erp, self.ctx('riley.park'), VENDORS[vkey][0], number, day,
                                     [{'kind': 'other', 'amount': amount, 'account': account, 'department': dept,
                                       'description': desc}])
        payables.validate(erp, self.ctx('riley.park'), inv)
        payables.approve_invoice(erp, self.ctx('hannah.brooks'), inv)

    def rent(self, day: str) -> None:
        self._non_po_invoice(day, 'riverside', 8000.00, '6100', 'ADMIN', f'Rent {parse_day(day).strftime("%B %Y")}')

    def utilities(self, day: str) -> None:
        self._non_po_invoice(day, 'buckeye', round(self.r.uniform(3100, 3900), 2), '6150', 'PROD',
                             f'Electricity, service to {day}')

    def payment_run(self, day: str) -> None:
        erp = self.erp
        horizon = erp.add_workdays(day, 5)
        due = erp.all("SELECT * FROM ap_invoices WHERE status = 'approved' AND (due_date <= ? OR "
                      "(discount_date IS NOT NULL AND discount_date >= ? AND discount_date <= ?)) ORDER BY id",
                      horizon, day, horizon)
        if not due:
            return
        run = payables.create_run(erp, self.ctx('hannah.brooks'), day, 'OPER', 'Weekly run')
        for inv in due:
            payables.add_to_run(erp, self.ctx('hannah.brooks'), run, inv['id'])
        payables.submit_run(erp, self.ctx('hannah.brooks'), run)
        payables.approve_run(erp, self.ctx('priya.raman'), run, 'Approved')
        payables.release_run(erp, self.ctx('priya.raman'), run)

    def bank_clear(self, day: str) -> None:
        erp = self.erp
        for p in erp.all("SELECT p.id FROM payments p JOIN journal_entries e ON e.id = p.posted_je "
                         "WHERE p.status = 'released' AND e.entry_date < ? ORDER BY p.id", day):
            payables.clear_payment(erp, self.ctx('sys-bank'), p['id'])

    # ------------------------------------------------------------------------------------------- production and sales
    def produce(self, day: str) -> None:
        erp = self.erp
        for sku, (_n, _p, base, _bom) in sorted(FINISHED.items()):
            qty = round(base * 12 / 52 * self.r.uniform(0.9, 1.1))
            short = manufacturing.shortages(erp, {'id': '', 'sku': sku, 'qty': qty, 'qty_completed': 0,
                                                  'qty_scrapped': 0, 'start_date': day, 'location': 'DAY-PRD'})
            if short:
                self.short_weeks.append((day, sku, qty, dict(short)))
                qty = self._feasible(sku, qty, day)
                if qty <= 0:
                    continue
            wo = manufacturing.create_wo(erp, self.ctx('jordan.lee'), sku, qty, day, erp.add_workdays(day, 2), 'DAY-STK')
            manufacturing.release_wo(erp, self.ctx('sam.whitaker'), wo)
            manufacturing.issue(erp, self.ctx('sam.whitaker'), wo, units=qty)
            manufacturing.complete(erp, self.ctx('sam.whitaker'), wo, qty)
            manufacturing.close_wo(erp, self.ctx('sam.whitaker'), wo)

    def _feasible(self, sku: str, qty: int, day: str) -> int:
        erp = self.erp
        per = manufacturing.explode(erp, sku, 1, day)
        return int(min(inventory.on_hand(erp, c) / q for c, q in per.items()))

    def new_orders(self, day: str) -> None:
        erp = self.erp
        monthly = sum(v[2] for v in FINISHED.values())
        self.sales_credit += monthly / 21 * self.r.uniform(0.85, 1.15)
        weights = [3 if c[3] == 'DIST' else 1 for c in CUSTOMERS]
        while self.sales_credit > 0:
            units = 0
            cust = self.r.choices(CUSTOMERS, weights)[0]
            n = self.r.choice((1, 1, 2))
            pool = sorted(FINISHED)
            skus = [self.r.choices(pool, [FINISHED[k][2] for k in pool])[0]]
            if n == 2:
                rest = [k for k in pool if k != skus[0]]
                skus.append(self.r.choices(rest, [FINISHED[k][2] for k in rest])[0])
            lines = []
            for sku in skus:
                q = self.r.choice((10, 20, 25, 30, 40, 50, 60, 80, 100)) * (2 if cust[3] == 'DIST' else 1)
                lines.append({'sku': sku, 'qty': q, 'promise_date': erp.add_workdays(day, 3)})
                units += q
            self.sales_credit -= units
            so = sales.create_so(erp, self.ctx('tom.reyes'), cust[0], lines, f'PO{self.r.randint(10000, 99999)}',
                                 'DAY')
            if erp.val('SELECT status FROM sales_orders WHERE id = ?', so) == 'on_hold':
                sales.release_so(erp, self.ctx('nina.patel'), so, 'Good payment history; released')
            self.pending_ship.append(so)

    def ship_and_bill(self, day: str) -> None:
        erp = self.erp
        keep = []
        for so in self.pending_ship:
            lines = []
            for l in erp.all("SELECT * FROM so_lines WHERE so_id = ? AND status = 'open' AND qty_shipped < qty", so):
                avail = inventory.on_hand(erp, l['sku'], 'DAY-STK')
                q = min(l['qty'] - l['qty_shipped'], avail)
                if q > 0:
                    lines.append({'so_line': l['line'], 'qty': q})
            if lines:
                sid = sales.ship(erp, self.ctx('ben.carter'), so, lines)
                sales.invoice_shipment(erp, self.ctx('ben.carter'), sid)
            if erp.val("SELECT 1 FROM so_lines WHERE so_id = ? AND status = 'open' AND qty_shipped < qty", so):
                keep.append(so)
        self.pending_ship = keep

    def customer_payments(self, day: str) -> None:
        erp = self.erp
        behaviour = {c[0]: c[6] for c in CUSTOMERS}
        for inv in erp.all("SELECT * FROM ar_invoices WHERE status = 'open' ORDER BY id"):
            b = behaviour[inv['customer']]
            if b == 'prompt' and inv['discount_date']:
                pay_on, disc = inv['discount_date'], inv['discount_cents']
            elif b == 'late':
                pay_on, disc = add_days(inv['due_date'], 18), 0
            else:
                pay_on, disc = inv['due_date'], 0
            if pay_on > day:
                continue
            amount = sales.ar_open_cents(erp, inv['id']) - disc
            cr = sales.enter_cash_receipt(erp, self.ctx('nina.patel'), amount, f'ACH {inv["id"]}', inv['customer'])
            sales.apply_cash(erp, self.ctx('nina.patel'), cr, [{'inv_id': inv['id'], 'amount_cents': amount,
                                                               'discount_cents': disc}])

    # ------------------------------------------------------------------------------------------- finance
    def payroll(self, day: str) -> None:
        erp = self.erp
        lines, total = [], 0
        for dept, monthly in sorted(WAGES.items()):
            gross = round(monthly / 2 * self.r.uniform(0.98, 1.03) * 100)
            taxes = round(gross * 0.2)
            lines += [{'account': '6000', 'debit_cents': gross, 'department': dept},
                      {'account': '6050', 'debit_cents': taxes, 'department': dept}]
            total += gross + taxes
        ledger.post(erp, self.ctx('omar.haddad'), day, 'transfer', 'payroll funding',
                    [('1010', total, 0), ('1000', 0, total)], memo='Fund payroll account')
        lines.append({'account': '1010', 'credit_cents': total})
        je = ledger.create_manual(erp, self.ctx('omar.haddad'), day, lines, f'Payroll {day}')
        ledger.submit(erp, self.ctx('omar.haddad'), je)
        ledger.approve(erp, self.ctx('priya.raman'), je, 'Approved')
        ledger.post_manual(erp, self.ctx('omar.haddad'), je)

    def month_end_entries(self, day: str) -> None:
        erp, ctx = self.erp, self.ctx('omar.haddad')
        for memo, dr, cr, amount, dept in (('Depreciation', '6550', '1550', 3200.00, 'PROD'),
                                           ('Insurance amortization', '6450', '1400', 1500.00, 'ADMIN')):
            if cr == '1400' and ledger.balance_cents(erp, '1400') < round(amount * 100):
                continue           # the policy is fully amortized
            je = ledger.create_manual(erp, ctx, day, [{'account': dr, 'debit': amount, 'department': dept},
                                                      {'account': cr, 'credit': amount}], f'{memo} {period_of(day)}')
            ledger.post_manual(erp, ctx, je)

    def close_previous(self, day: str) -> None:
        prev = period_of(add_days(day[:8] + '01', -1))
        if prev <= self.close_through and self.erp.val("SELECT status FROM periods WHERE period = ?", prev) == 'open':
            ledger.close_period(self.erp, self.ctx('priya.raman'), prev)


def run(erp: Erp, seed: int, start: str, end: str, close_through: str, events: dict | None = None,
        skip_month_end: set | None = None) -> History:
    h = History(erp, seed, start, end, close_through, events, skip_month_end)
    h.run()
    return h
