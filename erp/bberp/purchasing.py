"""Purchasing: requisitions and their approval requests, purchase orders, vendor acknowledgements, and requests
to vendors (expedite, defer, cancel).

Hard controls enforced here: approval only by the assigned approver, never by the requester, never above the
approver's limit; purchase orders only to active vendors; requisition lines on a PO must be approved and unconverted;
PO quantities and prices are frozen once the PO is sent.
"""
from __future__ import annotations

import json

from .core import Ctx, Erp, ext_cents, forbidden, invalid, limit_cents, load_ctx, not_found, q4, refused

REQ_OPEN = ('submitted',)


# ------------------------------------------------------------------------------------------- requisitions

def _req(erp: Erp, rid: str) -> dict:
    r = erp.one('SELECT * FROM requisitions WHERE id = ?', rid)
    if r is None:
        raise not_found('requisition', rid)
    return r


def _default_price(erp: Erp, sku: str | None, vendor: str | None, qty: float, day: str) -> float | None:
    if sku and vendor:
        p = agreement_price(erp, vendor, sku, qty, day)
        if p is not None:
            return p
    if sku:
        return erp.val('SELECT std_cost FROM items WHERE sku = ?', sku)
    return None


def create_requisition(erp: Erp, ctx: Ctx, department: str, lines: list[dict], justification: str | None = None,
                       submit: bool = False, requester: str | None = None) -> str:
    ctx.require('req.create')
    requester = requester or ctx.user
    if requester != ctx.user and not ctx.can('req.create_for_others'):
        raise forbidden('you can only raise requisitions for yourself')
    if not erp.val('SELECT 1 FROM departments WHERE code = ?', department):
        raise not_found('department', department)
    if not lines:
        raise invalid('a requisition needs at least one line')
    rid = erp.next_id('REQ')
    erp.insert('requisitions', {'id': rid, 'requester': requester, 'department': department,
                                'created_on': erp.today, 'status': 'draft', 'justification': justification})
    total = 0
    for i, ln in enumerate(lines, 1):
        sku = ln.get('sku')
        if sku and not erp.val('SELECT 1 FROM items WHERE sku = ? AND active = 1', sku):
            raise invalid(f'line {i}: no active item {sku}')
        if not sku and not ln.get('description'):
            raise invalid(f'line {i}: give an item or a description')
        qty = q4(ln.get('qty') or 0)
        if qty <= 0:
            raise invalid(f'line {i}: quantity must be positive')
        price = ln.get('est_unit_price')
        if price is None:
            price = _default_price(erp, sku, ln.get('vendor'), qty, erp.today)
        if price is None:
            raise invalid(f'line {i}: give an estimated unit price')
        account = ln.get('account') or (erp.account('inventory') if sku else None)
        if not account or not erp.val('SELECT 1 FROM accounts WHERE code = ?', account):
            raise invalid(f'line {i}: give a valid account')
        ship_to = ln.get('ship_to') or erp.meta('default_warehouse')
        if not erp.val('SELECT 1 FROM warehouses WHERE code = ?', ship_to):
            raise invalid(f'line {i}: no warehouse {ship_to}')
        amount = ext_cents(qty, price)
        total += amount
        erp.insert('requisition_lines', {'req_id': rid, 'line': i, 'sku': sku, 'description': ln.get('description'),
                                         'qty': qty, 'est_unit_price': q4(price), 'amount_cents': amount,
                                         'vendor': ln.get('vendor'), 'account': account, 'ship_to': ship_to,
                                         'need_by': ln.get('need_by'), 'note': ln.get('note')})
    erp.update('requisitions', {'id': rid}, {'total_cents': total})
    erp.touch('requisition', rid, created=True)
    if submit:
        submit_requisition(erp, ctx, rid)
    return rid


def first_approver(erp: Erp, req: dict) -> str:
    """The system assigns every submitted requisition to its department head; routing onward is the approver's job."""
    head = erp.val('SELECT head FROM departments WHERE code = ?', req['department'])
    if not head:
        raise refused('no_approver', f'department {req["department"]} has no head to approve requisitions')
    return head


def submit_requisition(erp: Erp, ctx: Ctx, rid: str) -> str:
    req = _req(erp, rid)
    if req['requester'] != ctx.user:
        raise forbidden(f'only the requester can submit {rid}')
    if req['status'] not in ('draft', 'returned'):
        raise refused('bad_status', f'{rid} is {req["status"]}')
    erp.touch('requisition', rid)
    erp.update('requisitions', {'id': rid}, {'status': 'submitted', 'submitted_on': erp.today})
    return _assign(erp, ctx, rid, first_approver(erp, req))


def _assign(erp: Erp, ctx: Ctx, rid: str, approver: str, note: str | None = None) -> str:
    aid = erp.next_id('APR')
    erp.insert('approval_requests', {'id': aid, 'doc_type': 'requisition', 'doc_id': rid, 'approver': approver,
                                     'requested_by': ctx.user, 'requested_on': erp.today, 'status': 'pending',
                                     'note': note})
    erp.touch('approval_request', aid, created=True)
    return aid


def pending_request(erp: Erp, rid: str) -> dict | None:
    return erp.one("SELECT * FROM approval_requests WHERE doc_type = 'requisition' AND doc_id = ? "
                   "AND status = 'pending' ORDER BY id DESC LIMIT 1", rid)


def _assigned(erp: Erp, ctx: Ctx, rid: str) -> tuple[dict, dict]:
    req = _req(erp, rid)
    if req['status'] not in REQ_OPEN:
        raise refused('bad_status', f'{rid} is {req["status"]}; there is nothing to decide')
    ar = pending_request(erp, rid)
    if ar is None or ar['approver'] != ctx.user:
        who = ar['approver'] if ar else 'nobody'
        raise refused('not_assigned', f'{rid} is waiting for {who}, not {ctx.user}', assigned_to=who)
    return req, ar


def _decide(erp: Erp, ctx: Ctx, rid: str, status: str, reason: str | None, note: str | None,
            forwarded_to: str | None = None) -> tuple[dict, dict]:
    req, ar = _assigned(erp, ctx, rid)
    erp.touch('approval_request', ar['id'])
    erp.update('approval_requests', {'id': ar['id']}, {'status': status, 'decided_on': erp.today,
                                                      'decided_by': ctx.user, 'reason': reason, 'note': note,
                                                      'forwarded_to': forwarded_to})
    erp.touch('requisition', rid)
    return req, ar


def approve_requisition(erp: Erp, ctx: Ctx, rid: str, note: str | None = None) -> None:
    ctx.require('req.approve')
    req, _ = _assigned(erp, ctx, rid)
    if req['requester'] == ctx.user:
        raise refused('requester_cannot_approve', f'{ctx.user} raised {rid} and cannot approve it')
    limit = limit_cents(erp, ctx.user, 'requisition')
    if req['total_cents'] > limit:
        raise refused('over_limit', f'{rid} totals {req["total_cents"] / 100:.2f}, above {ctx.user}\'s approval '
                      f'limit of {limit / 100:.2f}; forward it to an approver with a higher limit',
                      total_cents=req['total_cents'], limit_cents=limit)
    _decide(erp, ctx, rid, 'approved', None, note)
    erp.update('requisitions', {'id': rid}, {'status': 'approved', 'decided_by': ctx.user, 'decided_on': erp.today})


def reject_requisition(erp: Erp, ctx: Ctx, rid: str, reason: str, note: str | None = None) -> None:
    ctx.require('req.approve')
    if not reason:
        raise invalid('give a reason')
    _decide(erp, ctx, rid, 'rejected', reason, note)
    erp.update('requisitions', {'id': rid}, {'status': 'rejected', 'decided_by': ctx.user, 'decided_on': erp.today,
                                             'decision_reason': reason})


def return_requisition(erp: Erp, ctx: Ctx, rid: str, reason: str, note: str | None = None) -> None:
    """Send it back to the requester to change and resubmit."""
    ctx.require('req.approve')
    if not reason:
        raise invalid('give a reason')
    _decide(erp, ctx, rid, 'returned', reason, note)
    erp.update('requisitions', {'id': rid}, {'status': 'returned', 'decided_by': ctx.user, 'decided_on': erp.today,
                                             'decision_reason': reason})


def forward_requisition(erp: Erp, ctx: Ctx, rid: str, to_user: str, reason: str | None = None,
                        note: str | None = None) -> str:
    ctx.require('req.approve')
    target = erp.one('SELECT * FROM users WHERE id = ?', to_user)
    if target is None or not target['active'] or target['kind'] != 'staff':
        raise not_found('user', to_user)
    if to_user == ctx.user:
        raise invalid('cannot forward to yourself')
    if not load_ctx(erp, to_user).can('req.approve'):
        raise refused('not_an_approver', f'{to_user} does not approve requisitions')
    _decide(erp, ctx, rid, 'forwarded', reason, note, forwarded_to=to_user)
    return _assign(erp, ctx, rid, to_user, note)


def cancel_requisition(erp: Erp, ctx: Ctx, rid: str, reason: str) -> None:
    req = _req(erp, rid)
    if req['requester'] != ctx.user and not ctx.can('req.cancel_any'):
        raise forbidden(f'only the requester can cancel {rid}')
    if req['status'] in ('converted', 'cancelled', 'rejected'):
        raise refused('bad_status', f'{rid} is {req["status"]}')
    if erp.val('SELECT 1 FROM requisition_lines WHERE req_id = ? AND po_id IS NOT NULL', rid):
        raise refused('req_line_converted', f'{rid} already has lines on a purchase order')
    erp.touch('requisition', rid)
    ar = pending_request(erp, rid)
    if ar:
        erp.touch('approval_request', ar['id'])
        erp.update('approval_requests', {'id': ar['id']}, {'status': 'cancelled', 'decided_on': erp.today})
    erp.update('requisitions', {'id': rid}, {'status': 'cancelled', 'decision_reason': reason})


# ------------------------------------------------------------------------------------------- purchase orders

def agreement_price(erp: Erp, vendor: str, sku: str, qty: float, day: str) -> float | None:
    """Unit price from the vendor's valid agreement at the highest break the line quantity reaches."""
    return erp.val('SELECT unit_price FROM price_agreements WHERE vendor = ? AND sku = ? AND valid_from <= ? '
                   'AND valid_to >= ? AND min_qty <= ? ORDER BY min_qty DESC LIMIT 1', vendor, sku, day, day, qty)


def _po(erp: Erp, po_id: str) -> dict:
    po = erp.one('SELECT * FROM purchase_orders WHERE id = ?', po_id)
    if po is None:
        raise not_found('purchase order', po_id)
    return po


def _refresh_po(erp: Erp, po_id: str) -> None:
    lines = erp.all("SELECT * FROM po_lines WHERE po_id = ?", po_id)
    total = sum(l['amount_cents'] for l in lines if l['status'] != 'cancelled')
    po = _po(erp, po_id)
    changes = {'total_cents': total}
    if po['status'] in ('sent', 'partially_received', 'received'):
        live = [l for l in lines if l['status'] != 'cancelled']
        if not live:
            changes['status'] = 'cancelled'
        elif all(l['status'] == 'closed' or l['qty_received'] >= l['qty'] - 1e-9 for l in live):
            changes['status'] = 'received'
        elif any(l['qty_received'] > 0 for l in live):
            changes['status'] = 'partially_received'
        else:
            changes['status'] = 'sent'
    erp.update('purchase_orders', {'id': po_id}, changes)


def _add_line(erp: Erp, ctx: Ctx, po: dict, ln: dict, line_no: int) -> None:
    """A stock line names an item; a non-stock line (services, supplies) gives a description and an expense account."""
    sku = ln.get('sku')
    if sku:
        it = erp.one('SELECT * FROM items WHERE sku = ?', sku)
        if it is None or not it['active']:
            raise invalid(f'line {line_no}: no active item {sku!r}')
    else:
        if not ln.get('description') or not ln.get('account'):
            raise invalid(f'line {line_no}: give an item, or a description and an expense account')
        if ln.get('unit_price') is None:
            raise invalid(f'line {line_no}: non-stock lines need unit_price')
        it = {'lead_time_days': 5}
    qty = q4(ln.get('qty') or 0)
    if qty <= 0:
        raise invalid(f'line {line_no}: quantity must be positive')
    price = ln.get('unit_price')
    if price is None and sku:
        price = agreement_price(erp, po['vendor'], sku, qty, erp.today)
        if price is None:
            raise invalid(f'line {line_no}: {po["vendor"]} has no price agreement for {sku}; give unit_price')
    price = q4(price)
    if price < 0:
        raise invalid(f'line {line_no}: unit price cannot be negative')
    need = ln.get('need_date') or erp.add_workdays(erp.today, it['lead_time_days'] or 0)
    refs = ln.get('req_refs') or []
    account = ln.get('account')
    department = ln.get('department')
    for ref in refs:
        rid, rline = ref.get('req_id'), ref.get('line')
        req = erp.one('SELECT * FROM requisitions WHERE id = ?', rid)
        rl = erp.one('SELECT * FROM requisition_lines WHERE req_id = ? AND line = ?', rid, rline)
        if req is None or rl is None:
            raise not_found('requisition line', f'{rid}/{rline}')
        if req['status'] not in ('approved', 'converted'):
            raise refused('req_not_approved', f'{rid} is {req["status"]}; only approved requisitions go on a PO')
        if rl['po_id']:
            raise refused('req_line_converted', f'{rid} line {rline} is already on {rl["po_id"]}')
        if rl['sku'] != sku:
            raise invalid(f'{rid} line {rline} is for {rl["sku"]}, not {sku}')
        account = account or rl['account']
        department = department or req['department']
        erp.touch('requisition', rid)
        erp.update('requisition_lines', {'req_id': rid, 'line': rline}, {'po_id': po['id'], 'po_line': line_no})
        if not erp.val('SELECT 1 FROM requisition_lines WHERE req_id = ? AND po_id IS NULL', rid):
            erp.update('requisitions', {'id': rid}, {'status': 'converted'})
    if account and not erp.val('SELECT 1 FROM accounts WHERE code = ? AND active = 1', account):
        raise invalid(f'line {line_no}: no active account {account}')
    erp.insert('po_lines', {'po_id': po['id'], 'line': line_no, 'sku': sku, 'description': ln.get('description'),
                            'department': department, 'qty': qty, 'unit_price': price,
                            'amount_cents': ext_cents(qty, price), 'need_date': need,
                            'account': (account or erp.account('inventory')) if sku else account,
                            'note': ln.get('note'), 'at_risk': 1 if ln.get('at_risk') else 0})


def create_po(erp: Erp, ctx: Ctx, vendor: str, lines: list[dict], ship_to: str | None = None,
              note: str | None = None) -> str:
    ctx.require('po.create')
    v = erp.one('SELECT * FROM vendors WHERE id = ?', vendor)
    if v is None:
        raise not_found('vendor', vendor)
    if v['status'] != 'active':
        raise refused('vendor_inactive', f'{vendor} {v["name"]} is inactive')
    ship_to = ship_to or erp.meta('default_warehouse')
    if not erp.val('SELECT 1 FROM warehouses WHERE code = ?', ship_to):
        raise not_found('warehouse', ship_to)
    if not lines:
        raise invalid('a purchase order needs at least one line')
    po_id = erp.next_id('PO')
    erp.insert('purchase_orders', {'id': po_id, 'vendor': vendor, 'buyer': ctx.user, 'order_date': erp.today,
                                   'status': 'draft', 'ship_to': ship_to, 'terms': v['terms'], 'note': note})
    po = _po(erp, po_id)
    for i, ln in enumerate(lines, 1):
        _add_line(erp, ctx, po, ln, i)
    _refresh_po(erp, po_id)
    erp.touch('purchase_order', po_id, created=True)
    return po_id


def add_po_line(erp: Erp, ctx: Ctx, po_id: str, ln: dict) -> int:
    ctx.require('po.create')
    po = _po(erp, po_id)
    if po['status'] != 'draft':
        raise refused('po_sent', f'{po_id} has been sent; add lines to a new PO')
    erp.touch('purchase_order', po_id)
    n = (erp.val('SELECT MAX(line) FROM po_lines WHERE po_id = ?', po_id) or 0) + 1
    _add_line(erp, ctx, po, ln, n)
    _refresh_po(erp, po_id)
    return n


def update_po_line(erp: Erp, ctx: Ctx, po_id: str, line: int, changes: dict) -> None:
    ctx.require('po.create')
    po = _po(erp, po_id)
    pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', po_id, line)
    if pl is None:
        raise not_found('PO line', f'{po_id}/{line}')
    allowed_any = {'at_risk', 'note'}
    allowed_draft = {'qty', 'unit_price', 'need_date', 'account'}
    bad = set(changes) - allowed_any - allowed_draft
    if bad:
        raise invalid(f'cannot change {sorted(bad)} on a PO line')
    if set(changes) & allowed_draft and po['status'] != 'draft':
        raise refused('po_sent', f'{po_id} has been sent; quantities, prices and dates are frozen')
    upd = {}
    if 'qty' in changes:
        upd['qty'] = q4(changes['qty'])
        if upd['qty'] <= 0:
            raise invalid('quantity must be positive')
    if 'unit_price' in changes:
        upd['unit_price'] = q4(changes['unit_price'])
    if 'need_date' in changes:
        upd['need_date'] = changes['need_date']
    if 'account' in changes:
        upd['account'] = changes['account']
    if 'at_risk' in changes:
        upd['at_risk'] = 1 if changes['at_risk'] else 0
    if 'note' in changes:
        upd['note'] = changes['note']
    if 'qty' in upd or 'unit_price' in upd:
        upd['amount_cents'] = ext_cents(upd.get('qty', pl['qty']), upd.get('unit_price', pl['unit_price']))
    erp.touch('purchase_order', po_id)
    erp.update('po_lines', {'po_id': po_id, 'line': line}, upd)
    _refresh_po(erp, po_id)


def send_po(erp: Erp, ctx: Ctx, po_id: str) -> None:
    ctx.require('po.send')
    po = _po(erp, po_id)
    if po['status'] != 'draft':
        raise refused('bad_status', f'{po_id} is {po["status"]}')
    v = erp.one('SELECT * FROM vendors WHERE id = ?', po['vendor'])
    if v['status'] != 'active':
        raise refused('vendor_inactive', f'{po["vendor"]} is inactive')
    lines = erp.all("SELECT * FROM po_lines WHERE po_id = ? AND status != 'cancelled'", po_id)
    if not lines:
        raise refused('empty_po', f'{po_id} has no lines')
    unreferenced = sum(l['amount_cents'] for l in lines if not erp.val(
        'SELECT 1 FROM requisition_lines WHERE po_id = ? AND po_line = ?', po_id, l['line']))
    if unreferenced:
        limit = limit_cents(erp, ctx.user, 'purchase_order')
        if unreferenced > limit:
            raise refused('over_limit', f'{po_id} has {unreferenced / 100:.2f} not covered by approved '
                          f'requisitions, above {ctx.user}\'s purchase order limit of {limit / 100:.2f}',
                          uncovered_cents=unreferenced, limit_cents=limit)
    erp.touch('purchase_order', po_id)
    erp.update('purchase_orders', {'id': po_id}, {'status': 'sent', 'sent_on': erp.today})
    _refresh_po(erp, po_id)


def _release_req_lines(erp: Erp, po_id: str, line: int | None = None) -> None:
    rows = erp.all('SELECT req_id, line FROM requisition_lines WHERE po_id = ?' + (' AND po_line = ?' if line else ''),
                   *([po_id, line] if line else [po_id]))
    for r in rows:
        erp.touch('requisition', r['req_id'])
        erp.update('requisition_lines', {'req_id': r['req_id'], 'line': r['line']}, {'po_id': None, 'po_line': None})
        erp.update('requisitions', {'id': r['req_id']}, {'status': 'approved'})


def cancel_po(erp: Erp, ctx: Ctx, po_id: str, reason: str) -> None:
    ctx.require('po.create')
    po = _po(erp, po_id)
    if po['status'] not in ('draft', 'sent'):
        raise refused('bad_status', f'{po_id} is {po["status"]}; received POs are closed, not cancelled')
    if erp.val('SELECT 1 FROM po_lines WHERE po_id = ? AND qty_received > 0', po_id):
        raise refused('has_receipts', f'{po_id} has receipts')
    erp.touch('purchase_order', po_id)
    erp.run("UPDATE po_lines SET status = 'cancelled' WHERE po_id = ?", po_id)
    erp.update('purchase_orders', {'id': po_id}, {'status': 'cancelled', 'note': reason})
    _release_req_lines(erp, po_id)


def close_po_line(erp: Erp, ctx: Ctx, po_id: str, line: int, reason: str) -> None:
    """Short-close a line: no more is expected. Unreceived lines are cancelled instead."""
    ctx.require('po.create')
    pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', po_id, line)
    if pl is None:
        raise not_found('PO line', f'{po_id}/{line}')
    if pl['status'] != 'open':
        raise refused('bad_status', f'{po_id} line {line} is {pl["status"]}')
    erp.touch('purchase_order', po_id)
    status = 'closed' if pl['qty_received'] > 0 else 'cancelled'
    note = (pl['note'] + '; ' if pl['note'] else '') + reason
    erp.update('po_lines', {'po_id': po_id, 'line': line}, {'status': status, 'note': note})
    if status == 'cancelled' and _po(erp, po_id)['status'] == 'draft':
        _release_req_lines(erp, po_id, line)
    _refresh_po(erp, po_id)


def acknowledge(erp: Erp, ctx: Ctx, po_id: str, lines: list[dict], note: str | None = None) -> str:
    """A vendor confirms or rejects each line. Used by the vendor simulator."""
    ctx.require('po.acknowledge')
    po = _po(erp, po_id)
    if po['status'] not in ('sent', 'partially_received'):
        raise refused('bad_status', f'{po_id} is {po["status"]}')
    erp.touch('purchase_order', po_id)
    for ln in lines:
        upd = {}
        if ln.get('status') == 'rejected':
            upd['status'] = 'cancelled'
            upd['note'] = 'rejected by vendor: ' + (ln.get('note') or '')
        else:
            if ln.get('confirmed_date'):
                upd['confirmed_date'] = ln['confirmed_date']
            if ln.get('confirmed_price') is not None:
                upd['confirmed_price'] = q4(ln['confirmed_price'])
        erp.update('po_lines', {'po_id': po_id, 'line': ln['line']}, upd)
    aid = erp.next_id('ACK')
    erp.insert('po_acknowledgements', {'id': aid, 'po_id': po_id, 'ack_date': erp.today,
                                       'lines': json.dumps(lines, sort_keys=True), 'note': note})
    _refresh_po(erp, po_id)
    return aid


# ------------------------------------------------------------------------------------------- requests to vendors

def vendor_request(erp: Erp, ctx: Ctx, vendor: str, kind: str, po_id: str | None = None, po_line: int | None = None,
                   inv_ref: str | None = None, wanted_date: str | None = None, amount_cents: int | None = None,
                   note: str | None = None) -> str:
    ctx.require('vendor.request')
    if not erp.val('SELECT 1 FROM vendors WHERE id = ?', vendor):
        raise not_found('vendor', vendor)
    if kind not in ('expedite', 'defer', 'cancel', 'dispute', 'copy_request'):
        raise invalid('kind must be expedite, defer, cancel, dispute, or copy_request')
    if kind in ('expedite', 'defer', 'cancel'):
        pl = erp.one('SELECT l.* FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id '
                     'WHERE l.po_id = ? AND l.line = ? AND p.vendor = ?', po_id, po_line, vendor)
        if pl is None:
            raise not_found('PO line for this vendor', f'{po_id}/{po_line}')
        if kind != 'cancel' and not wanted_date:
            raise invalid('give wanted_date')
    rid = erp.next_id('VRQ')
    erp.insert('vendor_requests', {'id': rid, 'vendor': vendor, 'kind': kind, 'po_id': po_id, 'po_line': po_line,
                                   'inv_ref': inv_ref, 'wanted_date': wanted_date, 'amount_cents': amount_cents,
                                   'note': note, 'created_by': ctx.user, 'created_on': erp.today, 'status': 'open'})
    erp.touch('vendor_request', rid, created=True)
    return rid
