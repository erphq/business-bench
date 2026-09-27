"""Manufacturing: bills of materials (with effectivity dates and phantom assemblies), work orders, component
issues, completions, and closing variances.

Hard controls: releasing a work order checks that every component is on hand in the work order's warehouse;
issues and completions only on released or in-progress orders; stock never goes negative.

Postings at standard cost: issue Dr WIP, Cr inventory; completion Dr inventory, Cr WIP; close posts whatever
remains in WIP for the order to manufacturing variance.
"""
from __future__ import annotations

from . import inventory, ledger
from .core import Ctx, Erp, invalid, not_found, q4, refused


def bom(erp: Erp, parent: str, day: str) -> list[dict]:
    return erp.all('SELECT * FROM boms WHERE parent = ? AND valid_from <= ? AND valid_to >= ? ORDER BY component',
                   parent, day, day)


def explode(erp: Erp, parent: str, qty: float, day: str) -> dict[str, float]:
    """Component requirements for qty of parent, one level, with phantoms blown through and scrap included."""
    need: dict[str, float] = {}
    for b in bom(erp, parent, day):
        q = qty * b['qty_per'] * (1 + (b['scrap_pct'] or 0) / 100)
        comp = inventory.item(erp, b['component'])
        if comp['type'] == 'phantom':
            for k, v in explode(erp, b['component'], q, day).items():
                need[k] = need.get(k, 0) + v
        else:
            need[b['component']] = need.get(b['component'], 0) + q
    return {k: q4(v) for k, v in need.items()}


def _wo(erp: Erp, wo_id: str) -> dict:
    wo = erp.one('SELECT * FROM work_orders WHERE id = ?', wo_id)
    if wo is None:
        raise not_found('work order', wo_id)
    return wo


def issued(erp: Erp, wo_id: str) -> dict[str, float]:
    rows = erp.all('SELECT sku, SUM(qty) AS q FROM wo_issues WHERE wo_id = ? GROUP BY sku', wo_id)
    return {r['sku']: q4(r['q']) for r in rows}


def create_wo(erp: Erp, ctx: Ctx, sku: str, qty: float, start_date: str, due_date: str,
              location: str | None = None, note: str | None = None) -> str:
    ctx.require('wo.create')
    it = inventory.item(erp, sku)
    if it['type'] != 'manufactured':
        raise invalid(f'{sku} is not a manufactured item')
    qty = q4(qty)
    if qty <= 0:
        raise invalid('quantity must be positive')
    if due_date < start_date:
        raise invalid('due date is before start date')
    loc = location or it['default_location'] or erp.meta('default_production_location')
    inventory.location(erp, loc)
    wo_id = erp.next_id('WO')
    erp.insert('work_orders', {'id': wo_id, 'sku': sku, 'qty': qty, 'start_date': start_date, 'due_date': due_date,
                               'status': 'planned', 'location': loc, 'created_by': ctx.user, 'created_on': erp.today,
                               'note': note})
    erp.touch('work_order', wo_id, created=True)
    return wo_id


def shortages(erp: Erp, wo: dict) -> dict[str, float]:
    wh = erp.val('SELECT warehouse FROM locations WHERE code = ?', wo['location'])
    need = explode(erp, wo['sku'], wo['qty'] - wo['qty_completed'] - wo['qty_scrapped'], wo['start_date'])
    done = issued(erp, wo['id'])
    short = {}
    for sku, q in need.items():
        have = erp.val('SELECT COALESCE(SUM(t.qty), 0) FROM inventory_txns t JOIN locations l ON l.code = t.location '
                       'WHERE t.sku = ? AND l.warehouse = ?', sku, wh)
        missing = q4(q - done.get(sku, 0) - have)
        if missing > 1e-9:
            short[sku] = missing
    return short


def release_wo(erp: Erp, ctx: Ctx, wo_id: str) -> None:
    ctx.require('wo.release')
    wo = _wo(erp, wo_id)
    if wo['status'] != 'planned':
        raise refused('bad_status', f'{wo_id} is {wo["status"]}')
    short = shortages(erp, wo)
    if short:
        raise refused('components_short', f'{wo_id} cannot be released; short: ' +
                      ', '.join(f'{k} {v:g}' for k, v in sorted(short.items())), short=short)
    erp.touch('work_order', wo_id)
    erp.update('work_orders', {'id': wo_id}, {'status': 'released'})


def issue(erp: Erp, ctx: Ctx, wo_id: str, components: list[dict] | None = None, units: float | None = None) -> None:
    """Issue components: an explicit list, or backflush the BOM for `units` of the parent."""
    ctx.require('wo.issue')
    wo = _wo(erp, wo_id)
    if wo['status'] not in ('released', 'in_progress'):
        raise refused('bad_status', f'{wo_id} is {wo["status"]}; release it first')
    if components is None:
        if not units or units <= 0:
            raise invalid('give components, or units to backflush')
        components = [{'sku': k, 'qty': v} for k, v in sorted(explode(erp, wo['sku'], units, erp.today).items())]
    value = 0
    erp.touch('work_order', wo_id)
    for c in components:
        qty = q4(c.get('qty') or 0)
        if qty <= 0:
            raise invalid('issue quantities must be positive')
        loc = c.get('location') or inventory.item(erp, c['sku'])['default_location'] or wo['location']
        v, used = inventory.take(erp, ctx, erp.today, c['sku'], loc, qty, 'wo_issue', 'work_order', wo_id, c.get('lot'))
        value += v
        for lot, q in used:
            erp.insert('wo_issues', {'wo_id': wo_id, 'sku': c['sku'], 'qty': q, 'lot': lot, 'location': loc,
                                     'issue_date': erp.today, 'user_id': ctx.user})
    ledger.post(erp, ctx, erp.today, 'production', wo_id, [('wip', -value, 0), ('inventory', value, 0)],
                memo=f'Issue to {wo_id}')
    erp.update('work_orders', {'id': wo_id}, {'status': 'in_progress'})


def reverse_issue(erp: Erp, ctx: Ctx, issue_id: int, reason: str) -> None:
    ctx.require('wo.issue')
    row = erp.one('SELECT * FROM wo_issues WHERE id = ?', issue_id)
    if row is None:
        raise not_found('issue', issue_id)
    if row['reversal_of'] is not None or row['qty'] < 0:
        raise invalid('that line is itself a reversal')
    if erp.val('SELECT 1 FROM wo_issues WHERE reversal_of = ?', issue_id):
        raise refused('bad_status', f'issue {issue_id} was already reversed')
    wo = _wo(erp, row['wo_id'])
    if wo['status'] == 'closed':
        raise refused('bad_status', f'{wo["id"]} is closed')
    erp.touch('work_order', wo['id'])
    value = inventory.move(erp, ctx, erp.today, row['sku'], row['location'], row['qty'], 'wo_issue_reversal',
                           'work_order', wo['id'], lot=row['lot'])
    erp.insert('wo_issues', {'wo_id': wo['id'], 'sku': row['sku'], 'qty': -row['qty'], 'lot': row['lot'],
                             'location': row['location'], 'issue_date': erp.today, 'user_id': ctx.user,
                             'reversal_of': issue_id})
    ledger.post(erp, ctx, erp.today, 'production', wo['id'], [('inventory', value, 0), ('wip', -value, 0)],
                memo=f'Reversal of issue {issue_id} on {wo["id"]}: {reason}')


def complete(erp: Erp, ctx: Ctx, wo_id: str, qty: float, scrap_qty: float = 0, lot: str | None = None,
             expiry: str | None = None) -> None:
    ctx.require('wo.complete')
    wo = _wo(erp, wo_id)
    if wo['status'] not in ('released', 'in_progress'):
        raise refused('bad_status', f'{wo_id} is {wo["status"]}')
    qty, scrap_qty = q4(qty), q4(scrap_qty)
    if qty < 0 or scrap_qty < 0 or qty + scrap_qty <= 0:
        raise invalid('give a positive quantity completed and/or scrapped')
    if wo['qty_completed'] + wo['qty_scrapped'] + qty + scrap_qty > wo['qty'] + 1e-9:
        raise refused('over_completion', f'{wo_id} is for {wo["qty"]:g}; completing more is refused')
    erp.touch('work_order', wo_id)
    if lot:
        inventory.register_lot(erp, wo['sku'], lot, expiry)
    value = inventory.move(erp, ctx, erp.today, wo['sku'], wo['location'], qty, 'wo_completion', 'work_order', wo_id,
                           lot=lot) if qty else 0
    ledger.post(erp, ctx, erp.today, 'production', wo_id, [('inventory', value, 0), ('wip', 0, value)],
                memo=f'Completion of {qty:g} on {wo_id}')
    done = q4(wo['qty_completed'] + qty)
    scrapped = q4(wo['qty_scrapped'] + scrap_qty)
    status = 'completed' if done + scrapped >= wo['qty'] - 1e-9 else 'in_progress'
    erp.update('work_orders', {'id': wo_id}, {'qty_completed': done, 'qty_scrapped': scrapped, 'status': status})


def wip_cents(erp: Erp, wo_id: str | None = None, as_of: str | None = None) -> int:
    """WIP value: components issued less completions and closing variances, from the order's own postings."""
    sql = ("SELECT COALESCE(SUM(l.debit_cents - l.credit_cents), 0) FROM journal_lines l "
           "JOIN journal_entries e ON e.id = l.je_id WHERE e.source = 'production' AND l.account = ?")
    args = [erp.account('wip')]
    if wo_id:
        sql += ' AND e.source_ref = ?'; args.append(wo_id)
    if as_of:
        sql += ' AND e.entry_date <= ?'; args.append(as_of)
    return erp.val(sql, *args)


def close_wo(erp: Erp, ctx: Ctx, wo_id: str) -> None:
    ctx.require('wo.close')
    wo = _wo(erp, wo_id)
    if wo['status'] not in ('completed', 'in_progress', 'released'):
        raise refused('bad_status', f'{wo_id} is {wo["status"]}')
    erp.touch('work_order', wo_id)
    left = wip_cents(erp, wo_id)
    ledger.post(erp, ctx, erp.today, 'production', wo_id, [('mfg_variance', left, 0), ('wip', 0, left)],
                memo=f'Close {wo_id}')
    erp.update('work_orders', {'id': wo_id}, {'status': 'closed', 'closed_on': erp.today})


def cancel_wo(erp: Erp, ctx: Ctx, wo_id: str, reason: str) -> None:
    ctx.require('wo.create')
    wo = _wo(erp, wo_id)
    if wo['status'] not in ('planned', 'released') or issued(erp, wo_id):
        raise refused('bad_status', f'{wo_id} is {wo["status"]} or has issues; close it instead')
    erp.touch('work_order', wo_id)
    erp.update('work_orders', {'id': wo_id}, {'status': 'cancelled', 'note': reason})
