"""Inventory at standard cost: on-hand by location and lot, moves, first-expiry-first picking, transfers,
adjustments. Every move stores the value it posted, so the inventory subledger ties to the ledger exactly."""
from __future__ import annotations

from . import ledger
from .core import Ctx, Erp, ext_cents, invalid, not_found, q4, refused

EPS = 1e-9


def item(erp: Erp, sku: str) -> dict:
    it = erp.one('SELECT * FROM items WHERE sku = ?', sku)
    if it is None:
        raise not_found('item', sku)
    return it


def location(erp: Erp, code: str) -> dict:
    loc = erp.one('SELECT * FROM locations WHERE code = ?', code)
    if loc is None:
        raise not_found('location', code)
    return loc


def on_hand(erp: Erp, sku: str, location: str | None = None, lot: str | None = None, as_of: str | None = None) -> float:
    sql, args = 'SELECT COALESCE(SUM(qty), 0) FROM inventory_txns WHERE sku = ?', [sku]
    if location:
        sql += ' AND location = ?'; args.append(location)
    if lot:
        sql += ' AND lot = ?'; args.append(lot)
    if as_of:
        sql += ' AND txn_date <= ?'; args.append(as_of)
    return q4(erp.val(sql, *args))


def lots_on_hand(erp: Erp, sku: str, location: str) -> list[dict]:
    """Lots with stock at a location, earliest expiry first (lots without expiry last, then by lot code)."""
    return erp.all(
        "SELECT t.lot, l.expiry, ROUND(SUM(t.qty), 4) AS qty FROM inventory_txns t "
        "LEFT JOIN lots l ON l.sku = t.sku AND l.lot = t.lot WHERE t.sku = ? AND t.location = ? "
        "GROUP BY t.lot HAVING SUM(t.qty) > 0.00001 "
        "ORDER BY l.expiry IS NULL, l.expiry, t.lot", sku, location)


def move(erp: Erp, ctx: Ctx, day: str, sku: str, loc: str, qty: float, kind: str, ref_type: str | None,
         ref_id: str | None, lot: str | None = None, unit_cost: float | None = None) -> int:
    """Record one stock movement and return its value in cents (negative for stock out)."""
    it = item(erp, sku)
    location(erp, loc)
    qty = q4(qty)
    if abs(qty) < EPS:
        return 0
    if it['lot_controlled'] and not lot:
        raise invalid(f'{sku} is lot-controlled; give a lot')
    if qty < 0:
        have = on_hand(erp, sku, loc, lot)
        if have + qty < -EPS:
            where = f'{loc}' + (f' lot {lot}' if lot else '')
            raise refused('insufficient_stock', f'only {have:g} {sku} on hand at {where}', sku=sku, on_hand=have)
    cost = it['std_cost'] if unit_cost is None else unit_cost
    value = ext_cents(qty, cost)
    erp.insert('inventory_txns', {'txn_date': day, 'sku': sku, 'location': loc, 'lot': lot, 'qty': qty,
                                  'unit_cost': cost, 'value_cents': value, 'kind': kind, 'ref_type': ref_type,
                                  'ref_id': ref_id, 'user_id': ctx.user})
    return value


def take(erp: Erp, ctx: Ctx, day: str, sku: str, loc: str, qty: float, kind: str, ref_type: str, ref_id: str,
         lot: str | None = None) -> tuple[int, list[tuple[str | None, float]]]:
    """Remove qty, from the named lot or first-expiry-first. Returns (value cents, [(lot, qty)])."""
    it = item(erp, sku)
    if not it['lot_controlled'] or lot:
        return move(erp, ctx, day, sku, loc, -qty, kind, ref_type, ref_id, lot=lot), [(lot, qty)]
    left, value, used = q4(qty), 0, []
    for l in lots_on_hand(erp, sku, loc):
        if left <= EPS:
            break
        n = min(left, l['qty'])
        value += move(erp, ctx, day, sku, loc, -n, kind, ref_type, ref_id, lot=l['lot'])
        used.append((l['lot'], n))
        left = q4(left - n)
    if left > EPS:
        raise refused('insufficient_stock', f'short {left:g} {sku} at {loc}', sku=sku, short=left)
    return value, used


def register_lot(erp: Erp, sku: str, lot: str, expiry: str | None) -> None:
    have = erp.one('SELECT * FROM lots WHERE sku = ? AND lot = ?', sku, lot)
    if have is None:
        erp.insert('lots', {'sku': sku, 'lot': lot, 'expiry': expiry})
    elif expiry and have['expiry'] and have['expiry'] != expiry:
        raise invalid(f'lot {lot} of {sku} is already recorded with expiry {have["expiry"]}')


def transfer(erp: Erp, ctx: Ctx, sku: str, from_loc: str, to_loc: str, qty: float, lot: str | None = None,
             note: str | None = None) -> str:
    ctx.require('inv.transfer')
    if qty <= 0:
        raise invalid('transfer quantity must be positive')
    if from_loc == to_loc:
        raise invalid('from and to locations are the same')
    location(erp, to_loc)
    tid = erp.next_id('TRF')
    value, used = take(erp, ctx, erp.today, sku, from_loc, qty, 'transfer_out', 'transfer', tid, lot)
    for l, n in used:
        move(erp, ctx, erp.today, sku, to_loc, n, 'transfer_in', 'transfer', tid, lot=l)
    erp.touch('stock_move', tid, created=True)
    return tid


def adjust(erp: Erp, ctx: Ctx, sku: str, loc: str, qty_delta: float, reason: str, lot: str | None = None,
           expiry: str | None = None) -> str:
    """Book a count difference. The offset goes to the inventory adjustment account."""
    ctx.require('inv.adjust')
    if not reason:
        raise invalid('an adjustment needs a reason')
    aid = erp.next_id('ADJ')
    if qty_delta > 0:
        if lot:
            register_lot(erp, sku, lot, expiry)
        value = move(erp, ctx, erp.today, sku, loc, qty_delta, 'adjustment', 'adjustment', aid, lot=lot)
    else:
        value, _ = take(erp, ctx, erp.today, sku, loc, -qty_delta, 'adjustment', 'adjustment', aid, lot)
    ledger.post(erp, ctx, erp.today, 'inventory', aid,
                [('inventory', value, 0), ('inventory_adjustment', 0, value)], memo=f'Adjustment {sku} {loc}: {reason}')
    erp.touch('stock_move', aid, created=True)
    return aid


def valuation_cents(erp: Erp, as_of: str | None = None) -> int:
    sql, args = 'SELECT COALESCE(SUM(value_cents), 0) FROM inventory_txns', []
    if as_of:
        sql += ' WHERE txn_date <= ?'; args.append(as_of)
    return erp.val(sql, *args)
