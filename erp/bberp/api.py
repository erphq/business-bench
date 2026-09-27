"""The HTTP API: routes, authentication, idempotency, and one audit row per request.

`handle()` is framework-free so the server, the oracle harness and the tests all go through the same code.
Every response is JSON `{"business_date": ..., "data": ...}` except attachments, which are returned as bytes, and
errors, which are `application/problem+json`.
"""
from __future__ import annotations

import base64
import json
import re
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from . import comms, inventory, ledger, manufacturing, mrp, payables, purchasing, receiving, reports, sales
from .core import Ctx, Erp, ErpError, forbidden, invalid, limit_cents, load_ctx, not_found, to_cents

WRITE_METHODS = ('POST', 'PATCH', 'PUT', 'DELETE')


@dataclass
class Route:
    method: str
    pattern: str
    regex: re.Pattern
    action: str
    fn: object
    summary: str
    body: dict
    query: dict
    otype: str | None


ROUTES: list[Route] = []


def route(method: str, pattern: str, summary: str, action: str | None = None, body: dict | None = None,
          query: dict | None = None, otype: str | None = None):
    rx = re.compile('^' + re.sub(r'\{(\w+)\}', r'(?P<\1>[^/]+)', pattern) + '$')

    def deco(fn):
        ROUTES.append(Route(method, pattern, rx, action or fn.__name__, fn, summary, body or {}, query or {}, otype))
        return fn
    return deco


class Raw:
    """A non-JSON response body."""

    def __init__(self, data: bytes, content_type: str, filename: str | None = None):
        self.data, self.content_type, self.filename = data, content_type, filename


def _page(rows: list, q: dict) -> dict:
    limit = min(int(q.get('limit') or 200), 1000)
    offset = int(q.get('offset') or 0)
    return {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit}


def _filters(q: dict, allowed: dict) -> tuple[str, list]:
    """allowed: query name -> SQL column. Returns (' AND ...', args)."""
    sql, args = '', []
    for k, col in allowed.items():
        if q.get(k) not in (None, ''):
            sql += f' AND {col} = ?'
            args.append(q[k])
    return sql, args


def _need(b: dict, *keys):
    missing = [k for k in keys if b.get(k) in (None, '')]
    if missing:
        raise invalid(f'missing {", ".join(missing)}')


def _mask(acct: dict) -> dict:
    a = dict(acct)
    a['account_no'] = '*' * max(len(a['account_no']) - 4, 0) + a['account_no'][-4:]
    return a


# =========================================================================================== session and reference

@route('GET', '/whoami', 'Who you are signed in as, your roles, permissions, limits, boxes, and the business date')
def whoami(erp, ctx, p, q, b):
    u = erp.one('SELECT id, name, email, title, department, manager FROM users WHERE id = ?', ctx.user)
    limits = {r['doc_type']: r['limit_cents'] / 100 for r in
              erp.all('SELECT * FROM approval_limits WHERE user_id = ?', ctx.user)}
    return {**u, 'roles': sorted(ctx.roles), 'permissions': sorted(ctx.permissions), 'approval_limits': limits,
            'boxes': comms.boxes(ctx), 'company': erp.meta('company_name'), 'business_date': erp.today}


@route('GET', '/users', 'Colleagues: roles, department, manager, leave and delegations')
def list_users(erp, ctx, p, q, b):
    rows = erp.all("SELECT id, name, email, title, phone, department, manager FROM users WHERE kind = 'staff' "
                   "AND active = 1 ORDER BY id")
    for r in rows:
        r['roles'] = [x['role'] for x in erp.all('SELECT role FROM user_roles WHERE user_id = ? ORDER BY role', r['id'])]
    return _page(rows, q)


@route('GET', '/users/{id}', 'One colleague, with approval limits, leave and delegations')
def get_user(erp, ctx, p, q, b):
    u = erp.one("SELECT id, name, email, title, phone, department, manager FROM users WHERE id = ? AND kind = 'staff'",
                p['id'])
    if u is None:
        raise not_found('user', p['id'])
    u['roles'] = [x['role'] for x in erp.all('SELECT role FROM user_roles WHERE user_id = ? ORDER BY role', u['id'])]
    u['approval_limits'] = {r['doc_type']: r['limit_cents'] / 100 for r in
                            erp.all('SELECT * FROM approval_limits WHERE user_id = ?', u['id'])}
    u['leave'] = erp.all('SELECT start_date, end_date, kind FROM leave WHERE user_id = ? ORDER BY start_date', u['id'])
    u['delegations'] = erp.all('SELECT delegate, start_date, end_date FROM delegations WHERE user_id = ? '
                               'ORDER BY start_date', u['id'])
    return u


@route('GET', '/departments', 'Departments and their heads')
def list_departments(erp, ctx, p, q, b):
    return _page(erp.all('SELECT * FROM departments ORDER BY code'), q)


@route('GET', '/accounts', 'Chart of accounts')
def list_accounts(erp, ctx, p, q, b):
    return _page(erp.all('SELECT code, name, type, control, active FROM accounts ORDER BY code'), q)


@route('GET', '/periods', 'Accounting periods and whether they are open')
def list_periods(erp, ctx, p, q, b):
    return _page(erp.all('SELECT * FROM periods ORDER BY period'), q)


@route('GET', '/terms', 'Payment terms')
def list_terms(erp, ctx, p, q, b):
    return _page(erp.all('SELECT * FROM terms ORDER BY code'), q)


@route('GET', '/warehouses', 'Warehouses and their locations')
def list_warehouses(erp, ctx, p, q, b):
    rows = erp.all('SELECT * FROM warehouses ORDER BY code')
    for r in rows:
        r['locations'] = erp.all('SELECT code, name, kind FROM locations WHERE warehouse = ? ORDER BY code', r['code'])
    return _page(rows, q)


@route('GET', '/calendar', 'The company calendar: workdays and holidays', query={'from': 'YYYY-MM-DD', 'to': 'YYYY-MM-DD'})
def get_calendar(erp, ctx, p, q, b):
    start, end = q.get('from') or erp.today, q.get('to') or erp.add_workdays(erp.today, 30)
    return {'from': start, 'to': end,
            'holidays': erp.all('SELECT day, note FROM calendar WHERE workday = 0 AND day BETWEEN ? AND ? ORDER BY day',
                                start, end)}


# =========================================================================================== items, vendors, customers

@route('GET', '/items', 'Items', query={'type': 'purchased|manufactured|phantom', 'category': '', 'q': 'text search'})
def list_items(erp, ctx, p, q, b):
    sql, args = _filters(q, {'type': 'type', 'category': 'category', 'preferred_vendor': 'preferred_vendor'})
    if q.get('q'):
        sql += ' AND (sku LIKE ? OR name LIKE ?)'
        args += [f'%{q["q"]}%'] * 2
    return _page(erp.all('SELECT * FROM items WHERE 1 = 1' + sql + ' ORDER BY sku', *args), q)


@route('GET', '/items/{id}', 'An item with its bill of materials, substitutes, price agreements and stock')
def get_item(erp, ctx, p, q, b):
    it = inventory.item(erp, p['id'])
    it['bom'] = erp.all('SELECT component, qty_per, scrap_pct, valid_from, valid_to FROM boms WHERE parent = ? '
                        'ORDER BY valid_from, component', it['sku'])
    it['approved_substitutes'] = [r['substitute'] for r in
                                  erp.all('SELECT substitute FROM approved_substitutes WHERE sku = ?', it['sku'])]
    it['price_agreements'] = erp.all('SELECT * FROM price_agreements WHERE sku = ? ORDER BY vendor, valid_from, min_qty',
                                     it['sku'])
    it['on_hand'] = reports.on_hand(erp, sku=it['sku'])['stock']
    return it


@route('PATCH', '/items/{id}', 'Change planning data on an item', action='item.update', otype='item',
       body={'lead_time_days': 'int', 'safety_stock': 'number', 'moq': 'number', 'order_multiple': 'number',
             'preferred_vendor': 'vendor id', 'planner': 'user id'})
def patch_item(erp, ctx, p, q, b):
    ctx.require('item.plan')
    inventory.item(erp, p['id'])
    allowed = {'lead_time_days', 'safety_stock', 'moq', 'order_multiple', 'preferred_vendor', 'planner'}
    bad = set(b) - allowed
    if bad:
        raise invalid(f'cannot change {sorted(bad)} here')
    if b.get('preferred_vendor') and not erp.val('SELECT 1 FROM vendors WHERE id = ?', b['preferred_vendor']):
        raise not_found('vendor', b['preferred_vendor'])
    erp.touch('item', p['id'])
    erp.update('items', {'sku': p['id']}, b)
    return inventory.item(erp, p['id'])


@route('GET', '/boms/{id}', 'Bill of materials valid on a date, with phantoms exploded', query={'date': 'YYYY-MM-DD'})
def get_bom(erp, ctx, p, q, b):
    day = q.get('date') or erp.today
    return {'parent': p['id'], 'date': day, 'components': manufacturing.bom(erp, p['id'], day),
            'exploded_per_unit': manufacturing.explode(erp, p['id'], 1, day)}


@route('GET', '/vendors', 'Vendors', query={'status': 'active|inactive', 'q': 'text search'})
def list_vendors(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status'})
    if q.get('q'):
        sql += ' AND (id LIKE ? OR name LIKE ?)'
        args += [f'%{q["q"]}%'] * 2
    return _page(erp.all('SELECT * FROM vendors WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('GET', '/vendors/{id}', 'A vendor with bank accounts (masked) and price agreements')
def get_vendor(erp, ctx, p, q, b):
    v = erp.one('SELECT * FROM vendors WHERE id = ?', p['id'])
    if v is None:
        raise not_found('vendor', p['id'])
    v['bank_accounts'] = [_mask(a) for a in erp.all('SELECT * FROM vendor_bank_accounts WHERE vendor = ? ORDER BY id',
                                                    v['id'])]
    v['price_agreements'] = erp.all('SELECT * FROM price_agreements WHERE vendor = ? ORDER BY sku, valid_from, min_qty',
                                    v['id'])
    return v


@route('POST', '/vendors', 'Create a vendor', action='vendor.create', otype='vendor',
       body={'name': 'required', 'tin': '', 'terms': 'terms code', 'phone': '', 'email': '', 'address': '', 'note': ''})
def post_vendor(erp, ctx, p, q, b):
    return {'id': payables.create_vendor(erp, ctx, b)}


@route('PATCH', '/vendors/{id}', 'Change vendor master data (not bank details)', action='vendor.update', otype='vendor',
       body={'name': '', 'phone': '', 'email': '', 'address': '', 'terms': '', 'status': 'active|inactive',
             'quality_hold': 'bool', 'note': ''})
def patch_vendor(erp, ctx, p, q, b):
    payables.update_vendor(erp, ctx, p['id'], b)
    return erp.one('SELECT * FROM vendors WHERE id = ?', p['id'])


@route('POST', '/vendors/{id}/bank-accounts', 'Record a request to change where a vendor is paid; it starts pending',
       action='vendor.bank.request', otype='vendor_bank_account',
       body={'bank_name': 'required', 'routing': 'required', 'account_no': 'required',
             'source_ref': 'message or document that asked for it', 'note': ''})
def post_bank_account(erp, ctx, p, q, b):
    _need(b, 'bank_name', 'routing', 'account_no')
    return {'id': payables.request_bank_change(erp, ctx, p['id'], b['bank_name'], b['routing'], b['account_no'],
                                               b.get('source_ref'), b.get('note'))}


@route('GET', '/vendor-bank-accounts', 'Vendor bank accounts (masked), for example the pending changes to verify',
       query={'status': 'pending|verified|rejected|retired', 'vendor': ''})
def list_bank_accounts(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status', 'vendor': 'vendor'})
    return _page([_mask(a) for a in erp.all('SELECT * FROM vendor_bank_accounts WHERE 1 = 1' + sql + ' ORDER BY id',
                                            *args)], q)


@route('POST', '/vendor-bank-accounts/{id}/verify', 'Mark a pending bank account verified; the vendor is paid there',
       action='vendor.bank.verify', otype='vendor_bank_account', body={'note': ''})
def verify_bank_account(erp, ctx, p, q, b):
    payables.verify_bank_account(erp, ctx, p['id'], b.get('note'))
    return _mask(erp.one('SELECT * FROM vendor_bank_accounts WHERE id = ?', p['id']))


@route('POST', '/vendor-bank-accounts/{id}/reject', 'Reject a pending bank account', action='vendor.bank.reject',
       otype='vendor_bank_account', body={'reason': 'required'})
def reject_bank_account(erp, ctx, p, q, b):
    payables.reject_bank_account(erp, ctx, p['id'], b.get('reason'))
    return _mask(erp.one('SELECT * FROM vendor_bank_accounts WHERE id = ?', p['id']))


@route('POST', '/vendor-bank-accounts/{id}/withdraw', 'Withdraw a pending bank-account request you made',
       action='vendor.bank.withdraw', otype='vendor_bank_account', body={'reason': 'required'})
def withdraw_bank_account(erp, ctx, p, q, b):
    payables.cancel_bank_request(erp, ctx, p['id'], b.get('reason'))
    return _mask(erp.one('SELECT * FROM vendor_bank_accounts WHERE id = ?', p['id']))


@route('GET', '/price-agreements', 'Vendor price agreements and quantity breaks', query={'vendor': '', 'sku': ''})
def list_agreements(erp, ctx, p, q, b):
    sql, args = _filters(q, {'vendor': 'vendor', 'sku': 'sku'})
    return _page(erp.all('SELECT * FROM price_agreements WHERE 1 = 1' + sql + ' ORDER BY vendor, sku, valid_from, min_qty',
                         *args), q)


@route('GET', '/approved-substitutes', 'Approved substitute items', query={'sku': ''})
def list_substitutes(erp, ctx, p, q, b):
    sql, args = _filters(q, {'sku': 'sku'})
    return _page(erp.all('SELECT * FROM approved_substitutes WHERE 1 = 1' + sql + ' ORDER BY sku, substitute', *args), q)


@route('GET', '/customers', 'Customers', query={'q': 'text search'})
def list_customers(erp, ctx, p, q, b):
    sql, args = '', []
    if q.get('q'):
        sql, args = ' AND (id LIKE ? OR name LIKE ?)', [f'%{q["q"]}%'] * 2
    return _page(erp.all('SELECT * FROM customers WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('GET', '/customers/{id}', 'A customer with credit exposure')
def get_customer(erp, ctx, p, q, b):
    c = erp.one('SELECT * FROM customers WHERE id = ?', p['id'])
    if c is None:
        raise not_found('customer', p['id'])
    c['open_ar'] = sales.ar_open_by_customer(erp, c['id']) / 100
    c['open_orders'] = sales.open_order_cents(erp, c['id']) / 100
    c['credit_limit'] = c.pop('credit_limit_cents') / 100
    return c


# =========================================================================================== requisitions

def _req_view(erp, rid):
    r = erp.one('SELECT * FROM requisitions WHERE id = ?', rid)
    if r is None:
        raise not_found('requisition', rid)
    r['lines'] = erp.all('SELECT * FROM requisition_lines WHERE req_id = ? ORDER BY line', rid)
    r['approvals'] = erp.all("SELECT * FROM approval_requests WHERE doc_type = 'requisition' AND doc_id = ? ORDER BY id",
                             rid)
    r['total'] = r['total_cents'] / 100
    return r


@route('GET', '/requisitions', 'Requisitions', query={'status': '', 'department': '', 'requester': ''})
def list_requisitions(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status', 'department': 'department', 'requester': 'requester'})
    rows = erp.all('SELECT * FROM requisitions WHERE 1 = 1' + sql + ' ORDER BY id', *args)
    for r in rows:
        r['total'] = r['total_cents'] / 100
    return _page(rows, q)


@route('GET', '/requisitions/{id}', 'A requisition with lines and approval history')
def get_requisition(erp, ctx, p, q, b):
    return _req_view(erp, p['id'])


@route('POST', '/requisitions', 'Raise a requisition', action='req.create', otype='requisition',
       body={'department': 'required', 'justification': '', 'submit': 'bool',
             'lines': '[{sku | description, qty, est_unit_price?, vendor?, account?, ship_to?, need_by?, note?}]'})
def post_requisition(erp, ctx, p, q, b):
    _need(b, 'department', 'lines')
    rid = purchasing.create_requisition(erp, ctx, b['department'], b['lines'], b.get('justification'),
                                        bool(b.get('submit')))
    return _req_view(erp, rid)


@route('POST', '/requisitions/{id}/submit', 'Submit your requisition for approval', action='req.submit',
       otype='requisition')
def submit_requisition(erp, ctx, p, q, b):
    purchasing.submit_requisition(erp, ctx, p['id'])
    return _req_view(erp, p['id'])


@route('POST', '/requisitions/{id}/approve', 'Approve a requisition assigned to you', action='req.approve',
       otype='requisition', body={'note': ''})
def approve_requisition(erp, ctx, p, q, b):
    purchasing.approve_requisition(erp, ctx, p['id'], b.get('note'))
    return _req_view(erp, p['id'])


@route('POST', '/requisitions/{id}/reject', 'Reject a requisition assigned to you', action='req.reject',
       otype='requisition', body={'reason': 'required', 'note': ''})
def reject_requisition(erp, ctx, p, q, b):
    purchasing.reject_requisition(erp, ctx, p['id'], b.get('reason'), b.get('note'))
    return _req_view(erp, p['id'])


@route('POST', '/requisitions/{id}/return', 'Return a requisition to its requester for changes', action='req.return',
       otype='requisition', body={'reason': 'required', 'note': ''})
def return_requisition(erp, ctx, p, q, b):
    purchasing.return_requisition(erp, ctx, p['id'], b.get('reason'), b.get('note'))
    return _req_view(erp, p['id'])


@route('POST', '/requisitions/{id}/forward', 'Forward a requisition assigned to you to another approver',
       action='req.forward', otype='requisition', body={'to': 'user id, required', 'reason': '', 'note': ''})
def forward_requisition(erp, ctx, p, q, b):
    _need(b, 'to')
    purchasing.forward_requisition(erp, ctx, p['id'], b['to'], b.get('reason'), b.get('note'))
    return _req_view(erp, p['id'])


@route('POST', '/requisitions/{id}/cancel', 'Cancel a requisition', action='req.cancel', otype='requisition',
       body={'reason': 'required'})
def cancel_requisition(erp, ctx, p, q, b):
    purchasing.cancel_requisition(erp, ctx, p['id'], b.get('reason'))
    return _req_view(erp, p['id'])


@route('GET', '/approvals', 'Approval requests; by default the pending ones assigned to you',
       query={'status': 'pending|approved|...', 'approver': 'user id', 'doc_type': ''})
def list_approvals(erp, ctx, p, q, b):
    q = dict(q)
    q.setdefault('status', 'pending')
    q.setdefault('approver', ctx.user)
    sql, args = _filters(q, {'status': 'status', 'approver': 'approver', 'doc_type': 'doc_type'})
    return _page(erp.all('SELECT * FROM approval_requests WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


# =========================================================================================== purchase orders

def _po_view(erp, po_id):
    po = erp.one('SELECT * FROM purchase_orders WHERE id = ?', po_id)
    if po is None:
        raise not_found('purchase order', po_id)
    po['lines'] = erp.all('SELECT * FROM po_lines WHERE po_id = ? ORDER BY line', po_id)
    for l in po['lines']:
        l['requisition_lines'] = erp.all('SELECT req_id, line FROM requisition_lines WHERE po_id = ? AND po_line = ?',
                                         po_id, l['line'])
        l['at_risk'] = bool(l['at_risk'])
    po['acknowledgements'] = erp.all('SELECT * FROM po_acknowledgements WHERE po_id = ? ORDER BY id', po_id)
    for a in po['acknowledgements']:
        a['lines'] = json.loads(a['lines'])
    po['receipts'] = [r['id'] for r in erp.all('SELECT id FROM receipts WHERE po_id = ? ORDER BY id', po_id)]
    po['invoices'] = [r['id'] for r in erp.all('SELECT id FROM ap_invoices WHERE po_id = ? ORDER BY id', po_id)]
    po['total'] = po['total_cents'] / 100
    return po


@route('GET', '/purchase-orders', 'Purchase orders', query={'status': '', 'vendor': '', 'buyer': ''})
def list_pos(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status', 'vendor': 'vendor', 'buyer': 'buyer'})
    rows = erp.all('SELECT * FROM purchase_orders WHERE 1 = 1' + sql + ' ORDER BY id', *args)
    for r in rows:
        r['total'] = r['total_cents'] / 100
    return _page(rows, q)


@route('GET', '/purchase-orders/{id}', 'A purchase order with lines, acknowledgements, receipts and invoices')
def get_po(erp, ctx, p, q, b):
    return _po_view(erp, p['id'])


@route('POST', '/purchase-orders', 'Create a draft purchase order', action='po.create', otype='purchase_order',
       body={'vendor': 'required', 'ship_to': 'warehouse code', 'note': '',
             'lines': '[{sku, qty, unit_price? (default: price agreement), need_date?, '
                      'req_refs?: [{req_id, line}], at_risk?, note?}]'})
def post_po(erp, ctx, p, q, b):
    _need(b, 'vendor', 'lines')
    return _po_view(erp, purchasing.create_po(erp, ctx, b['vendor'], b['lines'], b.get('ship_to'), b.get('note')))


@route('POST', '/purchase-orders/{id}/lines', 'Add a line to a draft purchase order', action='po.add_line',
       otype='purchase_order', body={'sku': '', 'qty': '', 'unit_price': '', 'need_date': '', 'req_refs': ''})
def post_po_line(erp, ctx, p, q, b):
    purchasing.add_po_line(erp, ctx, p['id'], b)
    return _po_view(erp, p['id'])


@route('PATCH', '/purchase-orders/{id}/lines/{line}', 'Change a PO line (qty, price and dates only while draft)',
       action='po.update_line', otype='purchase_order',
       body={'qty': '', 'unit_price': '', 'need_date': '', 'account': '', 'at_risk': 'bool', 'note': ''})
def patch_po_line(erp, ctx, p, q, b):
    purchasing.update_po_line(erp, ctx, p['id'], int(p['line']), b)
    return _po_view(erp, p['id'])


@route('POST', '/purchase-orders/{id}/send', 'Send a draft purchase order to the vendor', action='po.send',
       otype='purchase_order')
def send_po(erp, ctx, p, q, b):
    purchasing.send_po(erp, ctx, p['id'])
    return _po_view(erp, p['id'])


@route('POST', '/purchase-orders/{id}/cancel', 'Cancel an unreceived purchase order', action='po.cancel',
       otype='purchase_order', body={'reason': 'required'})
def cancel_po(erp, ctx, p, q, b):
    _need(b, 'reason')
    purchasing.cancel_po(erp, ctx, p['id'], b['reason'])
    return _po_view(erp, p['id'])


@route('POST', '/purchase-orders/{id}/lines/{line}/close', 'Short-close a PO line: nothing more is expected',
       action='po.close_line', otype='purchase_order', body={'reason': 'required'})
def close_po_line(erp, ctx, p, q, b):
    _need(b, 'reason')
    purchasing.close_po_line(erp, ctx, p['id'], int(p['line']), b['reason'])
    return _po_view(erp, p['id'])


@route('GET', '/vendor-requests', 'Requests sent to vendors and their answers', query={'vendor': '', 'status': ''})
def list_vendor_requests(erp, ctx, p, q, b):
    sql, args = _filters(q, {'vendor': 'vendor', 'status': 'status', 'kind': 'kind'})
    return _page(erp.all('SELECT * FROM vendor_requests WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('POST', '/vendor-requests', 'Ask a vendor to expedite, defer or cancel a PO line, to credit a disputed '
       'amount, or to send an invoice copy', action='vendor.request', otype='vendor_request',
       body={'vendor': 'required', 'kind': 'expedite|defer|cancel|dispute|copy_request', 'po_id': '', 'po_line': '',
             'inv_ref': 'vendor invoice number', 'wanted_date': '', 'amount': '', 'note': ''})
def post_vendor_request(erp, ctx, p, q, b):
    _need(b, 'vendor', 'kind')
    rid = purchasing.vendor_request(erp, ctx, b['vendor'], b['kind'], b.get('po_id'),
                                    int(b['po_line']) if b.get('po_line') is not None else None, b.get('inv_ref'),
                                    b.get('wanted_date'), to_cents(b['amount']) if b.get('amount') is not None else None,
                                    b.get('note'))
    return erp.one('SELECT * FROM vendor_requests WHERE id = ?', rid)


# =========================================================================================== receiving

def _receipt_view(erp, rid):
    r = erp.one('SELECT * FROM receipts WHERE id = ?', rid)
    if r is None:
        raise not_found('receipt', rid)
    r['lines'] = erp.all('SELECT * FROM receipt_lines WHERE receipt_id = ? ORDER BY line', rid)
    return r


@route('GET', '/receipts', 'Receipts', query={'po': '', 'status': ''})
def list_receipts(erp, ctx, p, q, b):
    sql, args = _filters(q, {'po': 'po_id', 'status': 'status'})
    return _page(erp.all('SELECT * FROM receipts WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('GET', '/receipts/{id}', 'A receipt with its lines')
def get_receipt(erp, ctx, p, q, b):
    return _receipt_view(erp, p['id'])


@route('POST', '/receipts', 'Receive against a sent purchase order', action='rcv.post', otype='receipt',
       body={'po_id': 'required', 'packing_slip': '', 'note': '',
             'lines': '[{po_line, qty_received, qty_refused?, refusal_reason? (damaged|short_dated|wrong_item|'
                      'not_ordered|over_shipment|quality|other), sku? (item actually received if different), lot?, '
                      'expiry?, location?}]'})
def post_receipt(erp, ctx, p, q, b):
    _need(b, 'po_id', 'lines')
    return _receipt_view(erp, receiving.post_receipt(erp, ctx, b['po_id'], b['lines'], b.get('packing_slip'),
                                                     b.get('note')))


@route('POST', '/receipts/{id}/reverse', 'Reverse a posted receipt', action='rcv.reverse', otype='receipt',
       body={'reason': 'required'})
def reverse_receipt(erp, ctx, p, q, b):
    receiving.reverse_receipt(erp, ctx, p['id'], b.get('reason'))
    return _receipt_view(erp, p['id'])


# =========================================================================================== payables

def _inv_view(erp, inv_id):
    inv = erp.one('SELECT * FROM ap_invoices WHERE id = ?', inv_id)
    if inv is None:
        raise not_found('AP invoice', inv_id)
    inv['lines'] = erp.all('SELECT * FROM ap_invoice_lines WHERE inv_id = ? ORDER BY line', inv_id)
    inv['holds'] = erp.all("SELECT * FROM holds WHERE doc_type = 'ap_invoice' AND doc_id = ? ORDER BY id", inv_id)
    inv['match'] = payables.match(erp, inv_id)
    inv['total'] = inv['total_cents'] / 100
    inv['open'] = payables.open_cents(erp, inv_id) / 100
    inv['payments'] = erp.all('SELECT a.*, p.status, p.pay_date FROM payment_allocations a JOIN payments p '
                              'ON p.id = a.payment_id WHERE a.inv_id = ? ORDER BY p.id', inv_id)
    return inv


@route('GET', '/ap-invoices', 'Vendor invoices', query={'status': '', 'vendor': '', 'po': '', 'invoice_no': ''})
def list_ap_invoices(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status', 'vendor': 'vendor', 'po': 'po_id', 'invoice_no': 'invoice_no'})
    rows = erp.all('SELECT * FROM ap_invoices WHERE 1 = 1' + sql + ' ORDER BY id', *args)
    for r in rows:
        r['total'] = r['total_cents'] / 100
    return _page(rows, q)


@route('GET', '/ap-invoices/{id}', 'A vendor invoice with lines, holds, the three-way match and payments')
def get_ap_invoice(erp, ctx, p, q, b):
    return _inv_view(erp, p['id'])


@route('POST', '/ap-invoices', 'Enter a vendor invoice exactly as billed', action='ap.enter', otype='ap_invoice',
       body={'vendor': 'required', 'invoice_no': 'required, as printed', 'invoice_date': 'required', 'po_id': '',
             'source_msg': 'inbox message id', 'note': '',
             'lines': '[{kind: item|freight|tax|other, po_line?, sku?, description?, qty?, unit_price?, amount?, '
                      'account?, department?}]'})
def post_ap_invoice(erp, ctx, p, q, b):
    _need(b, 'vendor', 'invoice_no', 'invoice_date', 'lines')
    return _inv_view(erp, payables.enter_invoice(erp, ctx, b['vendor'], b['invoice_no'], b['invoice_date'], b['lines'],
                                                 b.get('po_id'), b.get('source_msg'), b.get('note')))


@route('PATCH', '/ap-invoices/{id}/lines/{line}', 'Correct an entry error on an unposted invoice line',
       action='ap.update_line', otype='ap_invoice',
       body={'qty': '', 'unit_price': '', 'amount': '', 'account': '', 'po_line': '', 'description': ''})
def patch_ap_line(erp, ctx, p, q, b):
    payables.update_invoice_line(erp, ctx, p['id'], int(p['line']), b)
    return _inv_view(erp, p['id'])


@route('POST', '/ap-invoices/{id}/holds', 'Put an invoice on hold', action='ap.hold', otype='ap_invoice',
       body={'reason': 'price|quantity|no_receipt|duplicate_suspect|vendor|tax|freight|other', 'line': '', 'note': ''})
def post_hold(erp, ctx, p, q, b):
    _need(b, 'reason')
    payables.place_hold(erp, ctx, p['id'], b['reason'], int(b['line']) if b.get('line') is not None else None,
                        b.get('note'))
    return _inv_view(erp, p['id'])


@route('POST', '/holds/{id}/release', 'Release a hold', action='ap.release_hold', otype='hold', body={'note': 'required'})
def release_hold(erp, ctx, p, q, b):
    payables.release_hold(erp, ctx, p['id'], b.get('note'))
    return erp.one('SELECT * FROM holds WHERE id = ?', p['id'])


@route('POST', '/ap-invoices/{id}/validate', 'Accept an invoice as matched and post it', action='ap.validate',
       otype='ap_invoice')
def validate_invoice(erp, ctx, p, q, b):
    payables.validate(erp, ctx, p['id'])
    return _inv_view(erp, p['id'])


@route('POST', '/ap-invoices/{id}/approve', 'Approve a matched invoice for payment', action='ap.approve',
       otype='ap_invoice', body={'note': ''})
def approve_invoice(erp, ctx, p, q, b):
    payables.approve_invoice(erp, ctx, p['id'], b.get('note'))
    return _inv_view(erp, p['id'])


@route('POST', '/ap-invoices/{id}/reject', 'Reject an unposted invoice', action='ap.reject', otype='ap_invoice',
       body={'reason': 'required'})
def reject_invoice(erp, ctx, p, q, b):
    payables.reject_invoice(erp, ctx, p['id'], b.get('reason'))
    return _inv_view(erp, p['id'])


@route('POST', '/ap-invoices/{id}/void', 'Void a posted, unpaid invoice', action='ap.void', otype='ap_invoice',
       body={'reason': 'required'})
def void_invoice(erp, ctx, p, q, b):
    payables.void_invoice(erp, ctx, p['id'], b.get('reason'))
    return _inv_view(erp, p['id'])


def _run_view(erp, run_id):
    r = erp.one('SELECT * FROM payment_runs WHERE id = ?', run_id)
    if r is None:
        raise not_found('payment run', run_id)
    r['payments'] = erp.all('SELECT * FROM payments WHERE run_id = ? ORDER BY id', run_id)
    for pay in r['payments']:
        pay['allocations'] = erp.all('SELECT * FROM payment_allocations WHERE payment_id = ? ORDER BY inv_id', pay['id'])
    r['total'] = payables.run_total_cents(erp, run_id) / 100
    return r


@route('GET', '/payment-runs', 'Payment runs', query={'status': ''})
def list_runs(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status'})
    return _page(erp.all('SELECT * FROM payment_runs WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('GET', '/payment-runs/{id}', 'A payment run with its payments')
def get_run(erp, ctx, p, q, b):
    return _run_view(erp, p['id'])


@route('POST', '/payment-runs', 'Start a draft payment run', action='pay.create_run', otype='payment_run',
       body={'pay_date': 'required', 'bank_account': 'required', 'note': ''})
def post_run(erp, ctx, p, q, b):
    _need(b, 'pay_date', 'bank_account')
    return _run_view(erp, payables.create_run(erp, ctx, b['pay_date'], b['bank_account'], b.get('note')))


@route('POST', '/payment-runs/{id}/invoices', 'Add an approved invoice to a draft run', action='pay.add',
       otype='payment_run', body={'inv_id': 'required', 'amount': 'partial amount (no discount)',
                                  'take_discount': 'bool, default true'})
def post_run_invoice(erp, ctx, p, q, b):
    _need(b, 'inv_id')
    payables.add_to_run(erp, ctx, p['id'], b['inv_id'], to_cents(b['amount']) if b.get('amount') is not None else None,
                        b.get('take_discount', True) is not False)
    return _run_view(erp, p['id'])


@route('DELETE', '/payment-runs/{id}/invoices/{inv}', 'Take an invoice out of a draft run', action='pay.remove',
       otype='payment_run')
def delete_run_invoice(erp, ctx, p, q, b):
    payables.remove_from_run(erp, ctx, p['id'], p['inv'])
    return _run_view(erp, p['id'])


@route('POST', '/payment-runs/{id}/submit', 'Submit a run for approval', action='pay.submit', otype='payment_run')
def submit_run(erp, ctx, p, q, b):
    payables.submit_run(erp, ctx, p['id'])
    return _run_view(erp, p['id'])


@route('POST', '/payment-runs/{id}/approve', 'Approve a submitted run', action='pay.approve', otype='payment_run',
       body={'note': ''})
def approve_run(erp, ctx, p, q, b):
    payables.approve_run(erp, ctx, p['id'], b.get('note'))
    return _run_view(erp, p['id'])


@route('POST', '/payment-runs/{id}/return', 'Return a submitted run to its preparer', action='pay.return',
       otype='payment_run', body={'reason': 'required'})
def return_run(erp, ctx, p, q, b):
    payables.return_run(erp, ctx, p['id'], b.get('reason'))
    return _run_view(erp, p['id'])


@route('POST', '/payment-runs/{id}/release', 'Release an approved run to the bank', action='pay.release',
       otype='payment_run')
def release_run(erp, ctx, p, q, b):
    payables.release_run(erp, ctx, p['id'])
    return _run_view(erp, p['id'])


@route('GET', '/payments', 'Payments', query={'vendor': '', 'status': ''})
def list_payments(erp, ctx, p, q, b):
    sql, args = _filters(q, {'vendor': 'vendor', 'status': 'status', 'run': 'run_id'})
    return _page(erp.all('SELECT * FROM payments WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


# =========================================================================================== sales and receivables

def _so_view(erp, so_id):
    so = erp.one('SELECT * FROM sales_orders WHERE id = ?', so_id)
    if so is None:
        raise not_found('sales order', so_id)
    so['lines'] = erp.all('SELECT * FROM so_lines WHERE so_id = ? ORDER BY line', so_id)
    so['shipments'] = [r['id'] for r in erp.all('SELECT id FROM shipments WHERE so_id = ? ORDER BY id', so_id)]
    so['total'] = so['total_cents'] / 100
    return so


@route('GET', '/sales-orders', 'Sales orders', query={'status': '', 'customer': ''})
def list_sos(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status', 'customer': 'customer'})
    return _page(erp.all('SELECT * FROM sales_orders WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('GET', '/sales-orders/{id}', 'A sales order with lines and shipments')
def get_so(erp, ctx, p, q, b):
    return _so_view(erp, p['id'])


@route('POST', '/sales-orders', 'Enter a sales order (credit-checked on entry)', action='so.create',
       otype='sales_order', body={'customer': 'required', 'customer_po': '', 'ship_from': '', 'note': '',
                                  'lines': '[{sku, qty, unit_price? (default: customer price list), promise_date?}]'})
def post_so(erp, ctx, p, q, b):
    _need(b, 'customer', 'lines')
    return _so_view(erp, sales.create_so(erp, ctx, b['customer'], b['lines'], b.get('customer_po'), b.get('ship_from'),
                                         b.get('note')))


@route('PATCH', '/sales-orders/{id}/lines/{line}', 'Change a sales order line', action='so.update_line',
       otype='sales_order', body={'promise_date': '', 'qty': '', 'unit_price': ''})
def patch_so_line(erp, ctx, p, q, b):
    sales.update_so_line(erp, ctx, p['id'], int(p['line']), b)
    return _so_view(erp, p['id'])


@route('POST', '/sales-orders/{id}/release', 'Release a sales order from hold', action='so.release_hold',
       otype='sales_order', body={'note': 'required'})
def release_so(erp, ctx, p, q, b):
    sales.release_so(erp, ctx, p['id'], b.get('note'))
    return _so_view(erp, p['id'])


@route('POST', '/sales-orders/{id}/hold', 'Put a sales order on hold', action='so.hold', otype='sales_order',
       body={'reason': 'required'})
def hold_so(erp, ctx, p, q, b):
    _need(b, 'reason')
    sales.hold_so(erp, ctx, p['id'], b['reason'])
    return _so_view(erp, p['id'])


@route('POST', '/shipments', 'Ship against a released sales order', action='so.ship', otype='shipment',
       body={'so_id': 'required', 'lines': '[{so_line, qty, lot?, location?}]'})
def post_shipment(erp, ctx, p, q, b):
    _need(b, 'so_id', 'lines')
    sid = sales.ship(erp, ctx, b['so_id'], b['lines'])
    return {**erp.one('SELECT * FROM shipments WHERE id = ?', sid),
            'lines': erp.all('SELECT * FROM shipment_lines WHERE shipment_id = ? ORDER BY line', sid)}


@route('GET', '/shipments/{id}', 'A shipment')
def get_shipment(erp, ctx, p, q, b):
    s = erp.one('SELECT * FROM shipments WHERE id = ?', p['id'])
    if s is None:
        raise not_found('shipment', p['id'])
    s['lines'] = erp.all('SELECT * FROM shipment_lines WHERE shipment_id = ? ORDER BY line', p['id'])
    return s


@route('POST', '/shipments/{id}/invoice', 'Invoice a shipment', action='ar.invoice', otype='ar_invoice',
       body={'invoice_date': 'default today'})
def invoice_shipment(erp, ctx, p, q, b):
    inv = sales.invoice_shipment(erp, ctx, p['id'], b.get('invoice_date'))
    return get_ar_invoice(erp, ctx, {'id': inv}, {}, {})


@route('GET', '/ar-invoices', 'Customer invoices', query={'status': '', 'customer': ''})
def list_ar_invoices(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status', 'customer': 'customer'})
    return _page(erp.all('SELECT * FROM ar_invoices WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('GET', '/ar-invoices/{id}', 'A customer invoice with lines and applications')
def get_ar_invoice(erp, ctx, p, q, b):
    inv = erp.one('SELECT * FROM ar_invoices WHERE id = ?', p['id'])
    if inv is None:
        raise not_found('customer invoice', p['id'])
    inv['lines'] = erp.all('SELECT * FROM ar_invoice_lines WHERE inv_id = ? ORDER BY line', p['id'])
    inv['applications'] = erp.all('SELECT * FROM cash_applications WHERE inv_id = ?', p['id'])
    inv['open'] = sales.ar_open_cents(erp, p['id']) / 100
    return inv


@route('GET', '/cash-receipts', 'Customer cash receipts', query={'status': '', 'customer': ''})
def list_cash_receipts(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status', 'customer': 'customer'})
    return _page(erp.all('SELECT * FROM cash_receipts WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('POST', '/cash-receipts', 'Record a customer payment received', action='ar.cash', otype='cash_receipt',
       body={'amount': 'required', 'reference': '', 'customer': '', 'bank_account': ''})
def post_cash_receipt(erp, ctx, p, q, b):
    _need(b, 'amount')
    rid = sales.enter_cash_receipt(erp, ctx, to_cents(b['amount']), b.get('reference'), b.get('customer'),
                                   b.get('bank_account'))
    return erp.one('SELECT * FROM cash_receipts WHERE id = ?', rid)


@route('POST', '/cash-receipts/{id}/apply', 'Apply a receipt to invoices', action='ar.apply', otype='cash_receipt',
       body={'applications': '[{inv_id, amount, discount?}]'})
def apply_cash(erp, ctx, p, q, b):
    _need(b, 'applications')
    apps = [{'inv_id': a.get('inv_id'), 'amount_cents': to_cents(a.get('amount') or 0),
             'discount_cents': to_cents(a.get('discount') or 0)} for a in b['applications']]
    sales.apply_cash(erp, ctx, p['id'], apps)
    return {**erp.one('SELECT * FROM cash_receipts WHERE id = ?', p['id']),
            'applications': erp.all('SELECT * FROM cash_applications WHERE receipt_id = ?', p['id'])}


# =========================================================================================== manufacturing and stock

def _wo_view(erp, wo_id):
    wo = erp.one('SELECT * FROM work_orders WHERE id = ?', wo_id)
    if wo is None:
        raise not_found('work order', wo_id)
    wo['issues'] = erp.all('SELECT * FROM wo_issues WHERE wo_id = ? ORDER BY id', wo_id)
    wo['requirements'] = manufacturing.explode(erp, wo['sku'], wo['qty'], wo['start_date'])
    wo['shortages'] = manufacturing.shortages(erp, wo) if wo['status'] == 'planned' else {}
    wo['wip'] = manufacturing.wip_cents(erp, wo_id) / 100
    return wo


@route('GET', '/work-orders', 'Work orders', query={'status': '', 'sku': ''})
def list_wos(erp, ctx, p, q, b):
    sql, args = _filters(q, {'status': 'status', 'sku': 'sku'})
    return _page(erp.all('SELECT * FROM work_orders WHERE 1 = 1' + sql + ' ORDER BY id', *args), q)


@route('GET', '/work-orders/{id}', 'A work order with issues, requirements and shortages')
def get_wo(erp, ctx, p, q, b):
    return _wo_view(erp, p['id'])


@route('POST', '/work-orders', 'Plan a work order', action='wo.create', otype='work_order',
       body={'sku': 'required', 'qty': 'required', 'start_date': 'required', 'due_date': 'required', 'location': '',
             'note': ''})
def post_wo(erp, ctx, p, q, b):
    _need(b, 'sku', 'qty', 'start_date', 'due_date')
    return _wo_view(erp, manufacturing.create_wo(erp, ctx, b['sku'], b['qty'], b['start_date'], b['due_date'],
                                                 b.get('location'), b.get('note')))


@route('POST', '/work-orders/{id}/release', 'Release a work order (checks component availability)',
       action='wo.release', otype='work_order')
def release_wo(erp, ctx, p, q, b):
    manufacturing.release_wo(erp, ctx, p['id'])
    return _wo_view(erp, p['id'])


@route('POST', '/work-orders/{id}/issue', 'Issue components: a list, or backflush `units` of the parent',
       action='wo.issue', otype='work_order', body={'components': '[{sku, qty, lot?, location?}]', 'units': ''})
def issue_wo(erp, ctx, p, q, b):
    manufacturing.issue(erp, ctx, p['id'], b.get('components'), b.get('units'))
    return _wo_view(erp, p['id'])


@route('POST', '/wo-issues/{id}/reverse', 'Reverse one component issue line', action='wo.reverse_issue',
       otype='work_order', body={'reason': 'required'})
def reverse_wo_issue(erp, ctx, p, q, b):
    _need(b, 'reason')
    manufacturing.reverse_issue(erp, ctx, int(p['id']), b['reason'])
    wo = erp.val('SELECT wo_id FROM wo_issues WHERE id = ?', int(p['id']))
    return _wo_view(erp, wo)


@route('POST', '/work-orders/{id}/complete', 'Report finished and scrapped quantity', action='wo.complete',
       otype='work_order', body={'qty': 'required', 'scrap_qty': '', 'lot': '', 'expiry': ''})
def complete_wo(erp, ctx, p, q, b):
    manufacturing.complete(erp, ctx, p['id'], b.get('qty') or 0, b.get('scrap_qty') or 0, b.get('lot'), b.get('expiry'))
    return _wo_view(erp, p['id'])


@route('POST', '/work-orders/{id}/close', 'Close a work order and post its variance', action='wo.close',
       otype='work_order')
def close_wo(erp, ctx, p, q, b):
    manufacturing.close_wo(erp, ctx, p['id'])
    return _wo_view(erp, p['id'])


@route('POST', '/work-orders/{id}/cancel', 'Cancel a work order with nothing issued', action='wo.cancel',
       otype='work_order', body={'reason': 'required'})
def cancel_wo(erp, ctx, p, q, b):
    manufacturing.cancel_wo(erp, ctx, p['id'], b.get('reason') or '')
    return _wo_view(erp, p['id'])


@route('GET', '/inventory/on-hand', 'Stock on hand by item, location and lot', query={'sku': '', 'location': ''})
def get_on_hand(erp, ctx, p, q, b):
    return reports.on_hand(erp, q.get('sku'), q.get('location'))


@route('POST', '/inventory/transfers', 'Move stock between locations', action='inv.transfer', otype='stock_move',
       body={'sku': 'required', 'from': 'required', 'to': 'required', 'qty': 'required', 'lot': '', 'note': ''})
def post_transfer(erp, ctx, p, q, b):
    _need(b, 'sku', 'from', 'to', 'qty')
    tid = inventory.transfer(erp, ctx, b['sku'], b['from'], b['to'], float(b['qty']), b.get('lot'), b.get('note'))
    return {'id': tid, 'moves': erp.all('SELECT * FROM inventory_txns WHERE ref_id = ? ORDER BY id', tid)}


@route('POST', '/inventory/adjustments', 'Book a count difference', action='inv.adjust', otype='stock_move',
       body={'sku': 'required', 'location': 'required', 'qty_delta': 'required (+ gain, - loss)', 'reason': 'required',
             'lot': '', 'expiry': ''})
def post_adjustment(erp, ctx, p, q, b):
    _need(b, 'sku', 'location', 'qty_delta', 'reason')
    aid = inventory.adjust(erp, ctx, b['sku'], b['location'], float(b['qty_delta']), b['reason'], b.get('lot'),
                           b.get('expiry'))
    return {'id': aid, 'moves': erp.all('SELECT * FROM inventory_txns WHERE ref_id = ? ORDER BY id', aid)}


# =========================================================================================== planning

@route('POST', '/mrp/runs', 'Run MRP over a horizon of weeks; earlier open suggestions are superseded',
       action='mrp.run', otype='mrp_run', body={'horizon_weeks': 'default 8', 'firm_days': 'workdays, default 5'})
def post_mrp_run(erp, ctx, p, q, b):
    rid = mrp.run(erp, ctx, int(b.get('horizon_weeks', 8)), int(b.get('firm_days', 5)))
    rows = erp.all('SELECT kind, COUNT(*) AS n, SUM(firm) AS firm, SUM(late) AS late FROM mrp_suggestions '
                   'WHERE run_id = ? GROUP BY kind ORDER BY kind', rid)
    return {**erp.one('SELECT * FROM mrp_runs WHERE id = ?', rid), 'summary': rows}


@route('GET', '/mrp/runs', 'MRP runs')
def list_mrp_runs(erp, ctx, p, q, b):
    return _page(erp.all('SELECT * FROM mrp_runs ORDER BY id'), q)


@route('GET', '/mrp/suggestions', 'Suggestions of the latest MRP run (or ?run=)',
       query={'run': '', 'kind': 'planned_po|planned_wo|expedite|defer|cancel', 'sku': '', 'firm': '1',
              'status': 'open|released|superseded'})
def list_mrp_suggestions(erp, ctx, p, q, b):
    run_id = q.get('run') or erp.val('SELECT id FROM mrp_runs ORDER BY id DESC LIMIT 1')
    sql, args = _filters(q, {'kind': 'kind', 'sku': 'sku', 'firm': 'firm', 'status': 'status'})
    return _page(erp.all('SELECT * FROM mrp_suggestions WHERE run_id = ?' + sql + ' ORDER BY id', run_id, *args), q)


@route('POST', '/mrp/suggestions/{id}/release', 'Release a planned order: a sent purchase order, or a planned work '
       'order', action='mrp.release', otype='mrp_suggestion', body={'qty': 'override', 'need_date': 'override',
                                                                    'vendor': 'override (purchase orders)'})
def release_mrp_suggestion(erp, ctx, p, q, b):
    made = mrp.release(erp, ctx, p['id'], b.get('qty'), b.get('need_date'), b.get('vendor'))
    return {**erp.one('SELECT * FROM mrp_suggestions WHERE id = ?', p['id']), 'created': made}


# =========================================================================================== ledger

def _je_view(erp, je_id):
    je = erp.one('SELECT * FROM journal_entries WHERE id = ?', je_id)
    if je is None:
        raise not_found('journal entry', je_id)
    je['lines'] = erp.all('SELECT * FROM journal_lines WHERE je_id = ? ORDER BY line', je_id)
    je['attachments'] = erp.all("SELECT id, name, content_type, added_by, added_on FROM attachments "
                                "WHERE owner_type = 'journal_entry' AND owner_id = ?", je_id)
    je['total'] = ledger.je_total(erp, je_id) / 100
    return je


@route('GET', '/journal-entries', 'Journal entries',
       query={'period': 'YYYY-MM', 'source': '', 'status': '', 'account': '', 'source_ref': ''})
def list_jes(erp, ctx, p, q, b):
    sql, args = _filters(q, {'period': 'e.period', 'source': 'e.source', 'status': 'e.status',
                             'source_ref': 'e.source_ref'})
    if q.get('account'):
        sql += ' AND EXISTS (SELECT 1 FROM journal_lines l WHERE l.je_id = e.id AND l.account = ?)'
        args.append(q['account'])
    return _page(erp.all('SELECT e.* FROM journal_entries e WHERE 1 = 1' + sql + ' ORDER BY e.entry_date, e.id', *args), q)


@route('GET', '/journal-entries/{id}', 'A journal entry with lines and attachments')
def get_je(erp, ctx, p, q, b):
    return _je_view(erp, p['id'])


@route('POST', '/journal-entries', 'Prepare a manual journal entry (draft)', action='je.create', otype='journal_entry',
       body={'entry_date': 'required', 'memo': 'required', 'auto_reverse_on': '', 'note': '',
             'lines': '[{account, debit | credit, department?, memo?}]'})
def post_je(erp, ctx, p, q, b):
    _need(b, 'entry_date', 'memo', 'lines')
    return _je_view(erp, ledger.create_manual(erp, ctx, b['entry_date'], b['lines'], b['memo'],
                                              b.get('auto_reverse_on'), b.get('note')))


@route('PUT', '/journal-entries/{id}/lines', 'Replace the lines of a draft or returned entry', action='je.edit',
       otype='journal_entry', body={'lines': 'required', 'memo': ''})
def put_je_lines(erp, ctx, p, q, b):
    _need(b, 'lines')
    ledger.replace_lines(erp, ctx, p['id'], b['lines'], b.get('memo'))
    return _je_view(erp, p['id'])


@route('POST', '/journal-entries/{id}/attachments', 'Attach support to an entry (base64 content)',
       action='je.attach', otype='journal_entry', body={'name': 'required', 'content_type': '', 'content_base64': 'required'})
def post_je_attachment(erp, ctx, p, q, b):
    _need(b, 'name', 'content_base64')
    je = erp.one('SELECT * FROM journal_entries WHERE id = ?', p['id'])
    if je is None:
        raise not_found('journal entry', p['id'])
    if je['preparer'] != ctx.user and not ctx.can('je.approve'):
        raise forbidden('only the preparer or an approver can attach support')
    try:
        data = base64.b64decode(b['content_base64'], validate=True)
    except Exception:
        raise invalid('content_base64 is not valid base64')
    erp.touch('journal_entry', p['id'])
    ledger.attach(erp, ctx, 'journal_entry', p['id'], b['name'], b.get('content_type') or 'application/octet-stream', data)
    return _je_view(erp, p['id'])


@route('GET', '/attachments/{id}', 'Download an attachment')
def get_attachment(erp, ctx, p, q, b):
    a = erp.one('SELECT * FROM attachments WHERE id = ?', p['id'])
    if a is None:
        raise not_found('attachment', p['id'])
    return Raw(a['data'], a['content_type'], a['name'])


for _verb, _fn, _summary in (('submit', 'submit', 'Submit your entry for approval'),
                             ('approve', 'approve', 'Approve a submitted entry you did not prepare'),
                             ('post', 'post_manual', 'Post an approved entry (or a small one of your own)')):
    def _make(fn_name):
        def h(erp, ctx, p, q, b):
            f = getattr(ledger, fn_name)
            if fn_name == 'approve':
                f(erp, ctx, p['id'], b.get('note'))
            else:
                f(erp, ctx, p['id'])
            return _je_view(erp, p['id'])
        return h
    route('POST', f'/journal-entries/{{id}}/{_verb}', _summary, action=f'je.{_verb}', otype='journal_entry')(_make(_fn))


@route('POST', '/journal-entries/{id}/return', 'Return a submitted entry to its preparer', action='je.return',
       otype='journal_entry', body={'reason': 'required'})
def return_je(erp, ctx, p, q, b):
    _need(b, 'reason')
    ledger.return_entry(erp, ctx, p['id'], b['reason'])
    return _je_view(erp, p['id'])


@route('POST', '/journal-entries/{id}/reverse', 'Reverse a posted entry', action='je.reverse', otype='journal_entry',
       body={'reverse_date': 'default today', 'reason': ''})
def reverse_je(erp, ctx, p, q, b):
    rev = ledger.reverse(erp, ctx, p['id'], b.get('reverse_date'), b.get('reason'))
    return _je_view(erp, rev)


@route('POST', '/periods/{id}/close', 'Close an accounting period', action='period.close', otype='period')
def close_period(erp, ctx, p, q, b):
    ledger.close_period(erp, ctx, p['id'])
    return erp.one('SELECT * FROM periods WHERE period = ?', p['id'])


@route('POST', '/periods/{id}/reopen', 'Reopen an accounting period', action='period.reopen', otype='period')
def reopen_period(erp, ctx, p, q, b):
    ledger.reopen_period(erp, ctx, p['id'])
    return erp.one('SELECT * FROM periods WHERE period = ?', p['id'])


# =========================================================================================== communication

@route('GET', '/inbox', 'Messages in the boxes you can read', query={'box': '', 'unread': 'true to hide read ones'})
def get_inbox(erp, ctx, p, q, b):
    return _page(comms.list_messages(erp, ctx, q.get('box'), str(q.get('unread', '')).lower() == 'true'), q)


@route('GET', '/inbox/{id}', 'Read a message (marks it read for you)')
def get_message(erp, ctx, p, q, b):
    return comms.read_message(erp, ctx, p['id'])


@route('GET', '/inbox/{id}/attachments/{n}', 'Download a message attachment')
def get_message_attachment(erp, ctx, p, q, b):
    a = comms.attachment(erp, ctx, p['id'], int(p['n']))
    return Raw(a['data'], a['content_type'], a['name'])


@route('POST', '/inbox/{id}/disposition', 'Record what was done with a message', action='msg.dispose', otype='message',
       body={'disposition': 'processed|duplicate|rejected|escalated|suspicious|no_action|forwarded', 'ref': '', 'note': ''})
def post_disposition(erp, ctx, p, q, b):
    _need(b, 'disposition')
    comms.dispose(erp, ctx, p['id'], b['disposition'], b.get('ref'), b.get('note'))
    return erp.one('SELECT * FROM messages WHERE id = ?', p['id'])


@route('GET', '/outbox', 'Messages you have sent')
def get_outbox(erp, ctx, p, q, b):
    return _page(erp.all("SELECT * FROM messages WHERE direction = 'out' AND created_by = ? ORDER BY id", ctx.user), q)


@route('POST', '/outbox', 'Send a message (stored; other people act only on structured actions)', action='msg.send',
       otype='message', body={'to': 'required', 'subject': 'required', 'body': ''})
def post_outbox(erp, ctx, p, q, b):
    _need(b, 'to', 'subject')
    return erp.one('SELECT * FROM messages WHERE id = ?', comms.send(erp, ctx, b['to'], b['subject'], b.get('body', '')))


@route('GET', '/escalations', 'Escalations you raised or received')
def get_escalations(erp, ctx, p, q, b):
    return _page(erp.all('SELECT * FROM escalations WHERE from_user = ? OR to_user = ? ORDER BY id', ctx.user, ctx.user), q)


@route('POST', '/escalations', 'Escalate a record to a colleague for a decision', action='escalate', otype='escalation',
       body={'record_type': 'required', 'record_id': 'required', 'to': 'user id, required',
             'reason': ', '.join(comms.ESCALATION_REASONS), 'note': ''})
def post_escalation(erp, ctx, p, q, b):
    _need(b, 'record_type', 'record_id', 'to', 'reason')
    eid = comms.escalate(erp, ctx, b['record_type'], b['record_id'], b['to'], b['reason'], b.get('note'))
    return erp.one('SELECT * FROM escalations WHERE id = ?', eid)


@route('GET', '/calls', 'Calls you made')
def get_calls(erp, ctx, p, q, b):
    return _page(erp.all('SELECT * FROM calls WHERE caller = ? ORDER BY id', ctx.user), q)


@route('POST', '/calls', 'Phone a vendor, customer or colleague; without a number, the number on file is dialled',
       action='call', otype='call', body={'party_type': 'vendor|customer|user', 'party_id': 'required', 'number': ''})
def post_call(erp, ctx, p, q, b):
    _need(b, 'party_type', 'party_id')
    return comms.call(erp, ctx, b['party_type'], b['party_id'], b.get('number'))


# =========================================================================================== reports and audit

@route('GET', '/reports', 'Available reports')
def list_reports(erp, ctx, p, q, b):
    return {'reports': sorted(reports.REPORTS)}


@route('GET', '/reports/{id}', 'Run a report; filters are query parameters (see GET /reports)')
def get_report(erp, ctx, p, q, b):
    fn = reports.REPORTS.get(p['id'])
    if fn is None:
        raise not_found('report', p['id'])
    kw = {k.replace('-', '_'): v for k, v in q.items() if k not in ('limit', 'offset')}
    for k in ('months', 'days'):
        if k in kw:
            kw[k] = int(kw[k])
    try:
        return fn(erp, **kw)
    except TypeError as e:
        raise invalid(f'bad report parameters: {e}')


@route('GET', '/audit', 'The audit log; your own events unless you hold audit.read',
       query={'actor': '', 'action': '', 'object_id': '', 'since': 'business date'})
def get_audit(erp, ctx, p, q, b):
    sql, args = _filters(q, {'actor': 'actor', 'action': 'action', 'object_id': 'object_id'})
    if not ctx.can('audit.read'):
        sql += ' AND actor = ?'
        args.append(ctx.user)
    if q.get('since'):
        sql += ' AND business_date >= ?'
        args.append(q['since'])
    rows = erp.all('SELECT id, business_date, actor, method, path, action, object_type, object_id, outcome, error_code '
                   "FROM audit_events WHERE channel != 'setup'" + sql + ' ORDER BY id', *args)
    return _page(rows, q)


# =========================================================================================== request handling

def openapi() -> dict:
    paths: dict = {}
    for r in ROUTES:
        params = [{'name': n, 'in': 'path', 'required': True, 'schema': {'type': 'string'}}
                  for n in re.findall(r'\{(\w+)\}', r.pattern)]
        params += [{'name': n, 'in': 'query', 'required': False, 'schema': {'type': 'string'}, 'description': d}
                   for n, d in r.query.items()]
        op = {'summary': r.summary, 'operationId': r.action if r.method != 'GET' else f'get_{r.fn.__name__}',
              'parameters': params, 'responses': {'200': {'description': 'OK'}, '4XX': {'description': 'problem+json'}}}
        if r.body:
            op['requestBody'] = {'content': {'application/json': {'schema': {
                'type': 'object', 'properties': {k: {'description': v} for k, v in r.body.items()}}}}}
        paths.setdefault(r.pattern, {})[r.method.lower()] = op
    return {'openapi': '3.1.0', 'info': {'title': 'bb-erp', 'version': '1',
                                         'description': 'Business Bench ERP. Authenticate with Authorization: Bearer '
                                                        '<token>. Send Idempotency-Key on writes to make retries safe.'},
            'paths': paths}


def _match(method: str, path: str):
    for r in ROUTES:
        if r.method == method:
            m = r.regex.match(path)
            if m:
                return r, m.groupdict()
    return None, None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def _json(status: int, payload, business_date: str | None) -> tuple[int, dict, bytes]:
    body = json.dumps({'business_date': business_date, 'data': payload}, default=str, indent=1).encode()
    return status, {'Content-Type': 'application/json'}, body


def _problem(e: ErpError) -> tuple[int, dict, bytes]:
    return e.status, {'Content-Type': 'application/problem+json'}, json.dumps(e.problem(), default=str).encode()


def authenticate(erp: Erp, headers: dict) -> Ctx:
    auth = headers.get('authorization') or headers.get('Authorization') or ''
    token = auth[7:].strip() if auth.lower().startswith('bearer ') else ''
    if not token:
        raise ErpError('unauthorized', 'send Authorization: Bearer <token>', 401)
    row = erp.one('SELECT * FROM tokens WHERE secret = ?', token)
    if row is None:
        raise ErpError('unauthorized', 'unknown token', 401)
    return load_ctx(erp, row['user_id'], token_id=row['id'], channel='api')


def handle(erp: Erp, method: str, target: str, headers: dict | None = None, body: bytes | None = None
           ) -> tuple[int, dict, bytes]:
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    parts = urlsplit(target)
    path = parts.path.rstrip('/') or '/'
    query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
    if method == 'GET' and path == '/openapi.json':
        return 200, {'Content-Type': 'application/json'}, json.dumps(openapi(), indent=1).encode()
    wall = _now()
    ctx = None
    idem = headers.get('idempotency-key')
    r = None
    try:
        with erp.lock:
            ctx = authenticate(erp, headers)
            r, params = _match(method, path)
            if r is None:
                raise ErpError('no_route', f'no endpoint {method} {path}; see /openapi.json', 404)
            try:
                b = json.loads(body.decode('utf-8')) if body and body.strip() else {}
            except (ValueError, UnicodeDecodeError):
                raise invalid('the request body is not JSON')
            if not isinstance(b, dict):
                raise invalid('the request body must be a JSON object')
            if method in WRITE_METHODS and idem:
                prev = erp.one('SELECT * FROM idempotency WHERE user_id = ? AND key = ?', ctx.user, idem)
                if prev:
                    with erp.tx():
                        erp.audit(ctx, method=method, path=path, action=r.action, outcome='ok', idem_key=idem,
                                  request={'replay': True}, wall_time=wall)
                    return prev['status'], {'Content-Type': 'application/json', 'Idempotent-Replay': 'true'}, \
                        prev['response'].encode()
            with erp.tx():
                erp.begin_audit()
                try:
                    result = r.fn(erp, ctx, params, query, b)
                finally:
                    before, after = erp.end_audit()
                if isinstance(result, Raw):
                    erp.audit(ctx, method=method, path=path, action='read', outcome='ok', wall_time=wall)
                    hdr = {'Content-Type': result.content_type}
                    if result.filename:
                        hdr['Content-Disposition'] = f'attachment; filename="{result.filename}"'
                    return 200, hdr, result.data
                status = 201 if method == 'POST' else 200
                oid = params.get('id') or (result.get('id') if isinstance(result, dict) else None)
                erp.audit(ctx, method=method, path=path, action=r.action if method in WRITE_METHODS else 'read',
                          object_type=r.otype, object_id=oid, before=before or None, after=after or None,
                          outcome='ok', idem_key=idem, request=b if method in WRITE_METHODS else query or None,
                          wall_time=wall)
                resp = _json(status, result, erp.today)
                if method in WRITE_METHODS and idem:
                    erp.insert('idempotency', {'user_id': ctx.user, 'key': idem, 'status': status,
                                               'response': resp[2].decode()})
                return resp
    except ErpError as e:
        try:
            with erp.lock, erp.tx():
                erp.audit(ctx, method=method, path=path, action=r.action if r else None,
                          object_type=r.otype if r else None, object_id=None, outcome='refused',
                          error_code=e.code, idem_key=idem, request=_safe_body(body), wall_time=wall)
        except Exception:
            pass
        return _problem(e)
    except Exception as e:  # a server bug: log it and answer 500 without leaking internals
        try:
            with erp.lock, erp.tx():
                erp.audit(ctx, method=method, path=path, action=r.action if r else None, outcome='error',
                          error_code=type(e).__name__, request={'trace': traceback.format_exc()[-2000:]},
                          wall_time=wall)
        except Exception:
            pass
        return _problem(ErpError('server_error', 'the server failed on this request; it has been logged', 500))


def _safe_body(body: bytes | None):
    if not body:
        return None
    try:
        return json.loads(body.decode('utf-8'))
    except Exception:
        return {'unparsed': body[:2000].decode('utf-8', 'replace')}
