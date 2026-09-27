"""Receiving against purchase orders.

A receipt line records what arrived for one PO line: the quantity taken into stock, the quantity refused at the
dock with a reason, the lot and expiry for lot-controlled items, and, when the vendor shipped a different item,
the item actually received (`sku`) with the ordered item in `substitute_for`. The system accepts any substitute;
which substitutes are acceptable is company policy.

Posting (standard costing): Dr inventory at standard, Cr GRNI at the PO price, the difference to purchase price
variance. Hard controls: the PO must be sent and the line open; lot-controlled receipts need a lot and expiry;
the line may not be received above its quantity plus the system over-receipt ceiling.
"""
from __future__ import annotations

from . import inventory, ledger, purchasing
from .core import Ctx, Erp, ext_cents, invalid, not_found, q4, refused

REFUSAL_REASONS = ('damaged', 'short_dated', 'wrong_item', 'not_ordered', 'over_shipment', 'quality', 'other')


def _stock_location(erp: Erp, sku: str, warehouse: str) -> str:
    it = inventory.item(erp, sku)
    if it['default_location'] and erp.val('SELECT 1 FROM locations WHERE code = ? AND warehouse = ?',
                                          it['default_location'], warehouse):
        return it['default_location']
    loc = erp.val("SELECT code FROM locations WHERE warehouse = ? AND kind = 'stock' ORDER BY code LIMIT 1", warehouse)
    if not loc:
        raise invalid(f'warehouse {warehouse} has no stock location')
    return loc


def post_receipt(erp: Erp, ctx: Ctx, po_id: str, lines: list[dict], packing_slip: str | None = None,
                 note: str | None = None) -> str:
    ctx.require('rcv.post')
    po = erp.one('SELECT * FROM purchase_orders WHERE id = ?', po_id)
    if po is None:
        raise not_found('purchase order', po_id)
    if po['status'] not in ('sent', 'partially_received'):
        raise refused('po_not_open', f'{po_id} is {po["status"]}; only sent purchase orders can be received')
    if not lines:
        raise invalid('a receipt needs at least one line')
    ceiling = erp.setting('over_receipt_ceiling_pct', 10) / 100
    rid = erp.next_id('RCV')
    erp.insert('receipts', {'id': rid, 'po_id': po_id, 'receipt_date': erp.today, 'received_by': ctx.user,
                            'packing_slip': packing_slip, 'status': 'posted', 'note': note})
    erp.touch('purchase_order', po_id)
    inv_total = grni_total = 0
    expense: list[tuple] = []
    seen: dict[int, float] = {}
    for i, ln in enumerate(lines, 1):
        n = ln.get('po_line')
        pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', po_id, n)
        if pl is None:
            raise not_found('PO line', f'{po_id}/{n}')
        if pl['status'] != 'open':
            raise refused('line_not_open', f'{po_id} line {n} is {pl["status"]}')
        got, refused_qty = q4(ln.get('qty_received') or 0), q4(ln.get('qty_refused') or 0)
        if got < 0 or refused_qty < 0 or got + refused_qty <= 0:
            raise invalid(f'line {i}: give a positive qty_received and/or qty_refused')
        reason = ln.get('refusal_reason')
        if refused_qty > 0 and reason not in REFUSAL_REASONS:
            raise invalid(f'line {i}: refusal_reason must be one of {", ".join(REFUSAL_REASONS)}')
        seen[n] = seen.get(n, pl['qty_received']) + got
        if pl['sku'] is None:                       # non-stock line: expensed at the PO price on receipt
            if seen[n] > pl['qty'] * (1 + ceiling) + 1e-9:
                raise refused('over_receipt_ceiling', f'{po_id} line {n}: receiving {seen[n]:g} of {pl["qty"]:g} '
                              f'ordered is over the system ceiling of {ceiling:.0%}', ordered=pl['qty'], receiving=seen[n])
            grni = ext_cents(got, pl['unit_price'])
            grni_total += grni
            expense.append((pl['account'], grni, 0, pl['department']))
            erp.insert('receipt_lines', {'receipt_id': rid, 'line': i, 'po_line': n, 'sku': None, 'qty_received': got,
                                         'qty_refused': refused_qty, 'refusal_reason': reason if refused_qty else None,
                                         'value_cents': 0, 'grni_cents': grni})
            erp.update('po_lines', {'po_id': po_id, 'line': n}, {'qty_received': q4(pl['qty_received'] + got),
                                                                 'qty_refused': q4(pl['qty_refused'] + refused_qty)})
            continue
        sku = ln.get('sku') or pl['sku']
        if not erp.val('SELECT 1 FROM items WHERE sku = ? AND active = 1', sku):
            raise invalid(f'line {i}: no active item {sku}')
        if seen[n] > pl['qty'] * (1 + ceiling) + 1e-9:
            raise refused('over_receipt_ceiling', f'{po_id} line {n}: receiving {seen[n]:g} of {pl["qty"]:g} ordered is '
                          f'over the system ceiling of {ceiling:.0%}', ordered=pl['qty'], receiving=seen[n])
        it = inventory.item(erp, sku)
        lot, expiry = ln.get('lot'), ln.get('expiry')
        if got > 0 and it['lot_controlled']:
            if not lot or not expiry:
                raise invalid(f'line {i}: {sku} is lot-controlled; give lot and expiry')
            inventory.register_lot(erp, sku, lot, expiry)
        loc = ln.get('location') or _stock_location(erp, sku, po['ship_to'])
        value = inventory.move(erp, ctx, erp.today, sku, loc, got, 'receipt', 'receipt', rid, lot=lot) if got else 0
        grni = ext_cents(got, pl['unit_price'])
        inv_total += value
        grni_total += grni
        erp.insert('receipt_lines', {'receipt_id': rid, 'line': i, 'po_line': n, 'sku': sku, 'qty_received': got,
                                     'qty_refused': refused_qty, 'refusal_reason': reason if refused_qty else None,
                                     'lot': lot if got else None, 'expiry': expiry if got else None,
                                     'location': loc, 'substitute_for': pl['sku'] if sku != pl['sku'] else None,
                                     'value_cents': value, 'grni_cents': grni})
        erp.update('po_lines', {'po_id': po_id, 'line': n}, {'qty_received': q4(pl['qty_received'] + got),
                                                             'qty_refused': q4(pl['qty_refused'] + refused_qty)})
    stock_grni = grni_total - sum(e[1] for e in expense)
    ledger.post(erp, ctx, erp.today, 'receiving', rid,
                [('inventory', inv_total, 0), ('ppv', stock_grni - inv_total, 0), *expense, ('grni', 0, grni_total)],
                memo=f'Receipt {rid} against {po_id}')
    purchasing._refresh_po(erp, po_id)
    erp.touch('receipt', rid, created=True)
    return rid


def reverse_receipt(erp: Erp, ctx: Ctx, rid: str, reason: str) -> None:
    ctx.require('rcv.post')
    if not reason:
        raise invalid('give a reason')
    r = erp.one('SELECT * FROM receipts WHERE id = ?', rid)
    if r is None:
        raise not_found('receipt', rid)
    if r['status'] != 'posted':
        raise refused('bad_status', f'{rid} is already {r["status"]}')
    erp.touch('receipt', rid)
    erp.touch('purchase_order', r['po_id'])
    inv_total = grni_total = 0
    expense: list[tuple] = []
    for ln in erp.all('SELECT * FROM receipt_lines WHERE receipt_id = ? ORDER BY line', rid):
        pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', r['po_id'], ln['po_line'])
        if ln['sku'] is None:
            expense.append((pl['account'], 0, ln['grni_cents'], pl['department']))
        elif ln['qty_received']:
            inv_total += inventory.move(erp, ctx, erp.today, ln['sku'], ln['location'], -ln['qty_received'],
                                        'receipt_reversal', 'receipt', rid, lot=ln['lot'])
        grni_total += ln['grni_cents']
        erp.update('po_lines', {'po_id': r['po_id'], 'line': ln['po_line']},
                   {'qty_received': q4(pl['qty_received'] - ln['qty_received']),
                    'qty_refused': q4(pl['qty_refused'] - ln['qty_refused'])})
    stock_grni = grni_total - sum(e[2] for e in expense)
    ledger.post(erp, ctx, erp.today, 'receiving', rid,
                [('inventory', inv_total, 0), ('ppv', -stock_grni - inv_total, 0), *expense, ('grni', grni_total, 0)],
                memo=f'Reversal of receipt {rid}: {reason}')
    erp.update('receipts', {'id': rid}, {'status': 'reversed', 'reversed_by': ctx.user, 'reversed_on': erp.today,
                                         'reversal_reason': reason})
    purchasing._refresh_po(erp, r['po_id'])


def grni_cents(erp: Erp, as_of: str | None = None) -> int:
    """Received-not-invoiced at PO prices: receipt values less the PO-price value of posted invoice lines."""
    rsql = ("SELECT COALESCE(SUM(l.grni_cents), 0) FROM receipt_lines l JOIN receipts r ON r.id = l.receipt_id "
            "WHERE r.status IN ('posted', 'reversed')")
    rev = ("SELECT COALESCE(SUM(l.grni_cents), 0) FROM receipt_lines l JOIN receipts r ON r.id = l.receipt_id "
           "WHERE r.status = 'reversed'")
    isql = ("SELECT COALESCE(SUM(l.grni_cents), 0) FROM ap_invoice_lines l JOIN ap_invoices i ON i.id = l.inv_id "
            "WHERE l.grni_cents IS NOT NULL AND i.posted_je IS NOT NULL")
    args_r, args_rev, args_i = [], [], []
    if as_of:
        rsql += ' AND r.receipt_date <= ?'; args_r.append(as_of)
        rev += ' AND r.reversed_on <= ?'; args_rev.append(as_of)
        isql += " AND (SELECT entry_date FROM journal_entries WHERE id = i.posted_je) <= ?"; args_i.append(as_of)
    return erp.val(rsql, *args_r) - erp.val(rev, *args_rev) - erp.val(isql, *args_i)
