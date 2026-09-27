"""Order to cash: sales orders with an automatic credit check, shipments (first-expiry-first), customer invoices,
and cash receipts with applications.

Hard controls: an order that would take the customer over its credit limit, or a customer on credit hold, is
entered on hold and ships only after someone with authority releases it; shipments never exceed the open quantity
or the stock on hand; invoices post in open periods only.

Postings: shipment Dr cost of goods sold, Cr inventory at standard; invoice Dr receivables, Cr revenue; cash
receipt Dr bank, Cr unapplied cash; application Dr unapplied cash (and sales discounts), Cr receivables.
"""
from __future__ import annotations

from . import inventory, ledger
from .core import (Ctx, Erp, add_days, ext_cents, invalid, not_found, period_of, q4, refused, to_cents)


def _so(erp: Erp, so_id: str) -> dict:
    so = erp.one('SELECT * FROM sales_orders WHERE id = ?', so_id)
    if so is None:
        raise not_found('sales order', so_id)
    return so


def customer_price(erp: Erp, customer: dict, sku: str) -> float | None:
    if customer.get('price_list'):
        p = erp.val('SELECT unit_price FROM price_lists WHERE code = ? AND sku = ?', customer['price_list'], sku)
        if p is not None:
            return p
    return erp.val('SELECT list_price FROM items WHERE sku = ?', sku)


def open_order_cents(erp: Erp, customer: str, exclude: str | None = None) -> int:
    rows = erp.all("SELECT l.qty, l.qty_shipped, l.unit_price FROM so_lines l JOIN sales_orders s ON s.id = l.so_id "
                   "WHERE s.customer = ? AND s.status IN ('entered', 'on_hold', 'released', 'partially_shipped') "
                   "AND l.status = 'open' AND s.id != ?", customer, exclude or '')
    return sum(ext_cents(max(r['qty'] - r['qty_shipped'], 0), r['unit_price']) for r in rows)


def exposure_cents(erp: Erp, customer: str, exclude: str | None = None) -> int:
    return ar_open_by_customer(erp, customer) + open_order_cents(erp, customer, exclude)


def create_so(erp: Erp, ctx: Ctx, customer: str, lines: list[dict], customer_po: str | None = None,
              ship_from: str | None = None, note: str | None = None) -> str:
    ctx.require('so.create')
    c = erp.one('SELECT * FROM customers WHERE id = ?', customer)
    if c is None:
        raise not_found('customer', customer)
    if c['status'] != 'active':
        raise refused('customer_inactive', f'{customer} is inactive')
    ship_from = ship_from or erp.meta('default_warehouse')
    if not erp.val('SELECT 1 FROM warehouses WHERE code = ?', ship_from):
        raise not_found('warehouse', ship_from)
    if not lines:
        raise invalid('a sales order needs at least one line')
    so_id = erp.next_id('SO')
    erp.insert('sales_orders', {'id': so_id, 'customer': customer, 'order_date': erp.today, 'customer_po': customer_po,
                                'ship_from': ship_from, 'status': 'entered', 'entered_by': ctx.user, 'note': note})
    total = 0
    for i, ln in enumerate(lines, 1):
        sku = ln.get('sku')
        if not erp.val('SELECT 1 FROM items WHERE sku = ? AND active = 1', sku):
            raise invalid(f'line {i}: no active item {sku!r}')
        qty = q4(ln.get('qty') or 0)
        if qty <= 0:
            raise invalid(f'line {i}: quantity must be positive')
        price = ln.get('unit_price')
        if price is None:
            price = customer_price(erp, c, sku)
        if price is None:
            raise invalid(f'line {i}: no price for {sku}; give unit_price')
        amount = ext_cents(qty, price)
        total += amount
        erp.insert('so_lines', {'so_id': so_id, 'line': i, 'sku': sku, 'qty': qty, 'unit_price': q4(price),
                                'amount_cents': amount,
                                'promise_date': ln.get('promise_date') or erp.add_workdays(erp.today, 5)})
    status, reason = 'released', None
    if c['credit_hold']:
        status, reason = 'on_hold', 'credit: customer on credit hold'
    elif exposure_cents(erp, customer, exclude=so_id) + total > c['credit_limit_cents']:
        status, reason = 'on_hold', 'credit: over credit limit'
    erp.update('sales_orders', {'id': so_id}, {'total_cents': total, 'status': status, 'hold_reason': reason})
    erp.touch('sales_order', so_id, created=True)
    return so_id


def release_so(erp: Erp, ctx: Ctx, so_id: str, note: str) -> None:
    ctx.require('so.release_hold')
    so = _so(erp, so_id)
    if so['status'] != 'on_hold':
        raise refused('bad_status', f'{so_id} is {so["status"]}')
    if not note:
        raise invalid('say why the hold is released')
    erp.touch('sales_order', so_id)
    erp.update('sales_orders', {'id': so_id}, {'status': 'released', 'hold_reason': None,
                                               'note': ((so['note'] or '') + f' | released: {note}').strip(' |')})


def hold_so(erp: Erp, ctx: Ctx, so_id: str, reason: str) -> None:
    ctx.require('so.create')
    so = _so(erp, so_id)
    if so['status'] not in ('entered', 'released', 'partially_shipped'):
        raise refused('bad_status', f'{so_id} is {so["status"]}')
    erp.touch('sales_order', so_id)
    erp.update('sales_orders', {'id': so_id}, {'status': 'on_hold', 'hold_reason': reason})


def update_so_line(erp: Erp, ctx: Ctx, so_id: str, line: int, changes: dict) -> None:
    ctx.require('so.create')
    so = _so(erp, so_id)
    sl = erp.one('SELECT * FROM so_lines WHERE so_id = ? AND line = ?', so_id, line)
    if sl is None:
        raise not_found('sales order line', f'{so_id}/{line}')
    bad = set(changes) - {'promise_date', 'qty', 'unit_price'}
    if bad:
        raise invalid(f'cannot change {sorted(bad)}')
    if ('qty' in changes or 'unit_price' in changes) and so['status'] not in ('entered', 'on_hold', 'released'):
        raise refused('bad_status', f'{so_id} has shipped; quantities and prices are frozen')
    upd = {k: changes[k] for k in changes}
    if 'qty' in upd:
        upd['qty'] = q4(upd['qty'])
        if upd['qty'] < sl['qty_shipped']:
            raise invalid('quantity below what has shipped')
    if 'unit_price' in upd:
        upd['unit_price'] = q4(upd['unit_price'])
    if 'qty' in upd or 'unit_price' in upd:
        upd['amount_cents'] = ext_cents(upd.get('qty', sl['qty']), upd.get('unit_price', sl['unit_price']))
    erp.touch('sales_order', so_id)
    erp.update('so_lines', {'so_id': so_id, 'line': line}, upd)
    erp.update('sales_orders', {'id': so_id}, {'total_cents': erp.val(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM so_lines WHERE so_id = ? AND status != 'cancelled'", so_id)})


def _refresh_so(erp: Erp, so_id: str) -> None:
    lines = erp.all("SELECT * FROM so_lines WHERE so_id = ? AND status != 'cancelled'", so_id)
    so = _so(erp, so_id)
    if so['status'] in ('on_hold', 'cancelled', 'closed'):
        return
    if lines and all(l['qty_shipped'] >= l['qty'] - 1e-9 or l['status'] == 'closed' for l in lines):
        st = 'shipped'
    elif any(l['qty_shipped'] > 0 for l in lines):
        st = 'partially_shipped'
    else:
        st = 'released'
    erp.update('sales_orders', {'id': so_id}, {'status': st})


def ship(erp: Erp, ctx: Ctx, so_id: str, lines: list[dict], ship_date: str | None = None) -> str:
    ctx.require('so.ship')
    so = _so(erp, so_id)
    if so['status'] not in ('released', 'partially_shipped'):
        raise refused('not_released', f'{so_id} is {so["status"]}; only released orders ship')
    day = ship_date or erp.today
    sid = erp.next_id('SHP')
    erp.insert('shipments', {'id': sid, 'so_id': so_id, 'ship_date': day, 'warehouse': so['ship_from'],
                             'status': 'shipped', 'shipped_by': ctx.user})
    erp.touch('sales_order', so_id)
    value, n = 0, 0
    for ln in lines:
        sl = erp.one('SELECT * FROM so_lines WHERE so_id = ? AND line = ?', so_id, ln.get('so_line'))
        if sl is None or sl['status'] != 'open':
            raise not_found('open sales order line', f'{so_id}/{ln.get("so_line")}')
        qty = q4(ln.get('qty') or 0)
        if qty <= 0 or sl['qty_shipped'] + qty > sl['qty'] + 1e-9:
            raise invalid(f'line {sl["line"]}: ship between 0 and the open quantity {sl["qty"] - sl["qty_shipped"]:g}')
        loc = ln.get('location') or erp.val("SELECT code FROM locations WHERE warehouse = ? AND kind = 'stock' "
                                            "ORDER BY code LIMIT 1", so['ship_from'])
        v, used = inventory.take(erp, ctx, day, sl['sku'], loc, qty, 'shipment', 'shipment', sid, ln.get('lot'))
        value += v
        for lot, q in used:
            n += 1
            erp.insert('shipment_lines', {'shipment_id': sid, 'line': n, 'so_line': sl['line'], 'sku': sl['sku'],
                                          'qty': q, 'lot': lot, 'location': loc})
        erp.update('so_lines', {'so_id': so_id, 'line': sl['line']}, {'qty_shipped': q4(sl['qty_shipped'] + qty)})
    ledger.post(erp, ctx, day, 'shipping', sid, [('cogs', -value, 0), ('inventory', value, 0)],
                memo=f'Shipment {sid} for {so_id}')
    _refresh_so(erp, so_id)
    erp.touch('shipment', sid, created=True)
    return sid


def invoice_shipment(erp: Erp, ctx: Ctx, shipment_id: str, invoice_date: str | None = None) -> str:
    ctx.require('ar.invoice')
    sh = erp.one('SELECT * FROM shipments WHERE id = ?', shipment_id)
    if sh is None:
        raise not_found('shipment', shipment_id)
    if sh['status'] != 'shipped':
        raise refused('bad_status', f'{shipment_id} is {sh["status"]}')
    so = _so(erp, sh['so_id'])
    c = erp.one('SELECT * FROM customers WHERE id = ?', so['customer'])
    day = invoice_date or erp.today
    ledger.ensure_open(erp, day)
    inv_id = erp.next_id('INV')
    rows, total = [], 0
    grouped: dict[int, float] = {}
    for sl in erp.all('SELECT * FROM shipment_lines WHERE shipment_id = ? ORDER BY line', shipment_id):
        grouped[sl['so_line']] = grouped.get(sl['so_line'], 0) + sl['qty']
    for i, (so_line, qty) in enumerate(sorted(grouped.items()), 1):
        l = erp.one('SELECT * FROM so_lines WHERE so_id = ? AND line = ?', so['id'], so_line)
        amt = ext_cents(qty, l['unit_price'])
        total += amt
        rows.append({'inv_id': inv_id, 'line': i, 'sku': l['sku'], 'qty': q4(qty), 'unit_price': l['unit_price'],
                     'amount_cents': amt, 'account': erp.account('revenue'), 'description': None})
    t = erp.one('SELECT * FROM terms WHERE code = ?', c['terms']) or {'net_days': 30, 'discount_pct': 0, 'discount_days': 0}
    je = ledger.post(erp, ctx, day, 'billing', inv_id, [('ar', total, 0), ('revenue', 0, total)],
                     memo=f'Invoice {inv_id} to {c["id"]}')
    erp.insert('ar_invoices', {'id': inv_id, 'customer': c['id'], 'invoice_date': day, 'period': period_of(day),
                               'so_id': so['id'], 'shipment_id': shipment_id, 'total_cents': total, 'status': 'open',
                               'due_date': add_days(day, t['net_days']),
                               'discount_date': add_days(day, t['discount_days']) if t['discount_pct'] else None,
                               'discount_cents': to_cents(total / 100 * t['discount_pct'] / 100) if t['discount_pct'] else 0,
                               'created_by': ctx.user, 'posted_je': je})
    for r in rows:
        erp.insert('ar_invoice_lines', r)
    erp.touch('shipment', shipment_id)
    erp.update('shipments', {'id': shipment_id}, {'status': 'invoiced'})
    erp.touch('ar_invoice', inv_id, created=True)
    return inv_id


def ar_applied_cents(erp: Erp, inv_id: str) -> int:
    return erp.val('SELECT COALESCE(SUM(amount_cents + discount_cents), 0) FROM cash_applications WHERE inv_id = ?',
                   inv_id)


def ar_open_cents(erp: Erp, inv_id: str) -> int:
    inv = erp.one('SELECT * FROM ar_invoices WHERE id = ?', inv_id)
    if inv is None:
        raise not_found('customer invoice', inv_id)
    return 0 if inv['status'] == 'voided' else inv['total_cents'] - ar_applied_cents(erp, inv_id)


def ar_open_by_customer(erp: Erp, customer: str) -> int:
    return erp.val("SELECT COALESCE(SUM(i.total_cents), 0) - COALESCE((SELECT SUM(a.amount_cents + a.discount_cents) "
                   "FROM cash_applications a JOIN ar_invoices j ON j.id = a.inv_id WHERE j.customer = ? "
                   "AND j.status != 'voided'), 0) FROM ar_invoices i WHERE i.customer = ? AND i.status != 'voided'",
                   customer, customer)


def enter_cash_receipt(erp: Erp, ctx: Ctx, amount_cents: int, reference: str | None, customer: str | None = None,
                       bank_account: str | None = None, receipt_date: str | None = None) -> str:
    ctx.require('ar.cash')
    if amount_cents <= 0:
        raise invalid('amount must be positive')
    if customer and not erp.val('SELECT 1 FROM customers WHERE id = ?', customer):
        raise not_found('customer', customer)
    bank = erp.one('SELECT * FROM bank_accounts WHERE code = ?', bank_account or erp.meta('default_bank'))
    if bank is None:
        raise not_found('bank account', bank_account)
    day = receipt_date or erp.today
    rid = erp.next_id('CR')
    je = ledger.post(erp, ctx, day, 'cash', rid, [(bank['gl_account'], amount_cents, 0),
                                                  ('unapplied_cash', 0, amount_cents)], memo=f'Cash receipt {reference or ""}')
    erp.insert('cash_receipts', {'id': rid, 'customer': customer, 'receipt_date': day, 'amount_cents': amount_cents,
                                 'reference': reference, 'bank_account': bank['code'], 'status': 'unapplied',
                                 'entered_by': ctx.user, 'posted_je': je})
    erp.touch('cash_receipt', rid, created=True)
    return rid


def apply_cash(erp: Erp, ctx: Ctx, receipt_id: str, applications: list[dict]) -> None:
    ctx.require('ar.cash')
    cr = erp.one('SELECT * FROM cash_receipts WHERE id = ?', receipt_id)
    if cr is None:
        raise not_found('cash receipt', receipt_id)
    applied = erp.val('SELECT COALESCE(SUM(amount_cents), 0) FROM cash_applications WHERE receipt_id = ?', receipt_id)
    erp.touch('cash_receipt', receipt_id)
    post = []
    for a in applications:
        inv = erp.one('SELECT * FROM ar_invoices WHERE id = ?', a.get('inv_id'))
        if inv is None or inv['status'] != 'open':
            raise not_found('open customer invoice', a.get('inv_id'))
        amt, disc = int(a.get('amount_cents') or 0), int(a.get('discount_cents') or 0)
        if amt <= 0 or disc < 0:
            raise invalid('application amounts must be positive')
        if amt + disc > ar_open_cents(erp, inv['id']):
            raise invalid(f'{inv["id"]} has only {ar_open_cents(erp, inv["id"]) / 100:.2f} open')
        if applied + amt > cr['amount_cents']:
            raise invalid(f'{receipt_id} has only {(cr["amount_cents"] - applied) / 100:.2f} unapplied')
        if cr['customer'] and inv['customer'] != cr['customer'] and not erp.val(
                'SELECT 1 FROM customers WHERE id = ? AND parent = ?', inv['customer'], cr['customer']):
            raise invalid(f'{inv["id"]} belongs to {inv["customer"]}, not {cr["customer"]} or its subsidiaries')
        applied += amt
        erp.touch('ar_invoice', inv['id'])
        prev = erp.one('SELECT * FROM cash_applications WHERE receipt_id = ? AND inv_id = ?', receipt_id, inv['id'])
        if prev:
            erp.update('cash_applications', {'receipt_id': receipt_id, 'inv_id': inv['id']},
                       {'amount_cents': prev['amount_cents'] + amt, 'discount_cents': prev['discount_cents'] + disc})
        else:
            erp.insert('cash_applications', {'receipt_id': receipt_id, 'inv_id': inv['id'], 'amount_cents': amt,
                                             'discount_cents': disc, 'applied_on': erp.today, 'applied_by': ctx.user})
        post += [('unapplied_cash', amt, 0), ('sales_discounts', disc, 0), ('ar', 0, amt + disc)]
        if ar_open_cents(erp, inv['id']) <= 0:
            erp.update('ar_invoices', {'id': inv['id']}, {'status': 'paid'})
    ledger.post(erp, ctx, erp.today, 'cash', receipt_id, post, memo=f'Application of {receipt_id}')
    status = 'applied' if applied >= cr['amount_cents'] else ('partially_applied' if applied else 'unapplied')
    erp.update('cash_receipts', {'id': receipt_id}, {'status': status})


def ar_subledger_cents(erp: Erp, as_of: str | None = None) -> int:
    isql = "SELECT COALESCE(SUM(total_cents), 0) FROM ar_invoices WHERE status != 'voided'"
    asql = ("SELECT COALESCE(SUM(a.amount_cents + a.discount_cents), 0) FROM cash_applications a "
            "JOIN ar_invoices i ON i.id = a.inv_id WHERE i.status != 'voided'")
    args = []
    if as_of:
        isql += ' AND invoice_date <= ?'; asql += ' AND a.applied_on <= ?'; args = [as_of]
    return erp.val(isql, *args) - erp.val(asql, *args)


def unapplied_cash_cents(erp: Erp, as_of: str | None = None) -> int:
    rsql = "SELECT COALESCE(SUM(amount_cents), 0) FROM cash_receipts WHERE status != 'reversed'"
    asql = "SELECT COALESCE(SUM(amount_cents), 0) FROM cash_applications"
    args = []
    if as_of:
        rsql += ' AND receipt_date <= ?'; asql += ' WHERE applied_on <= ?'; args = [as_of]
    return erp.val(rsql, *args) - erp.val(asql, *args)
