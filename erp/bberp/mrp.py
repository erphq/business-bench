"""Material requirements planning.

A run nets demand against stock and scheduled receipts, item by item in low-level-code order, over a horizon of
workdays, and writes suggestions:

  planned_po / planned_wo   a new order: quantity (MOQ and order multiple applied), need date, release date (need
                            date less the item's lead time in workdays), firm when it releases inside the firm fence,
                            late when its release date has passed
  expedite / defer / cancel a scheduled receipt that arrives after it is needed, well before it is needed (more than
                            ten workdays), or is not needed within the horizon

Demand: open sales order lines at their promise dates; for items with a weekly forecast, whatever of the forecast
the week's orders have not consumed, on the week's first workday; the unissued components of open work orders at
their start dates; the components of planned work orders at their release dates, from the bill of materials valid
on that date. Planned orders are batched by week: one order per item per week, due on the week's first shortage.
Supply: stock on hand, open purchase order lines (confirmed date, else need date), open work orders (due date).
Scheduled receipts are pegged to demand in date order; the plan assumes action messages are carried out, as MRP
conventionally does. Deterministic: ties break on document ids.
"""
from __future__ import annotations

import math

from . import manufacturing, purchasing
from .inventory import on_hand
from datetime import timedelta

from .core import Ctx, Erp, invalid, not_found, parse_day, q4, refused

DEFER_TOLERANCE = 10     # workdays early before a receipt is worth deferring


def low_level_codes(erp: Erp) -> dict[str, int]:
    llc = {r['sku']: 0 for r in erp.all('SELECT sku FROM items')}
    edges = erp.all('SELECT DISTINCT parent, component FROM boms')
    for _ in range(len(llc)):
        changed = False
        for e in edges:
            if llc[e['component']] < llc[e['parent']] + 1:
                llc[e['component']] = llc[e['parent']] + 1
                changed = True
        if not changed:
            break
    return llc


def week_of(day: str) -> str:
    d = parse_day(day)
    return (d - timedelta(days=d.weekday())).isoformat()


def _lot(short: float, moq: float, mult: float) -> float:
    qty = max(short, moq or 0)
    if mult:
        qty = math.ceil(qty / mult - 1e-9) * mult
    return q4(qty)


def run(erp: Erp, ctx: Ctx, horizon_weeks: int = 8, firm_days: int = 5) -> str:
    ctx.require('mrp.run')
    if not 1 <= horizon_weeks <= 52:
        raise invalid('horizon_weeks must be between 1 and 52')
    today = erp.today
    horizon = erp.add_workdays(today, horizon_weeks * 5)
    fence = erp.add_workdays(today, firm_days)
    run_id = erp.next_id('MRP')
    erp.insert('mrp_runs', {'id': run_id, 'run_by': ctx.user, 'run_on': today, 'horizon_end': horizon,
                            'firm_fence': fence})
    erp.run("UPDATE mrp_suggestions SET status = 'superseded' WHERE status = 'open'")
    llc = low_level_codes(erp)
    items = {r['sku']: r for r in erp.all("SELECT * FROM items WHERE active = 1 AND type != 'phantom'")}
    demand: dict[str, list] = {s: [] for s in items}
    supply: dict[str, list] = {s: [] for s in items}

    def add_demand(sku: str, day: str, qty: float, src: str) -> None:
        if qty > 1e-9 and sku in demand and day <= horizon:
            demand[sku].append((max(day, today), q4(qty), src))

    for l in erp.all("SELECT l.*, s.status AS so_status FROM so_lines l JOIN sales_orders s ON s.id = l.so_id WHERE "
                     "s.status IN ('entered', 'on_hold', 'released', 'partially_shipped') AND l.status = 'open' "
                     "ORDER BY l.so_id, l.line"):
        add_demand(l['sku'], l['promise_date'] or today, l['qty'] - l['qty_shipped'], f'{l["so_id"]}/{l["line"]}')
    ordered: dict[tuple, float] = {}
    for sku, rows in demand.items():
        for day, qty, _src in rows:
            ordered[(sku, week_of(day))] = ordered.get((sku, week_of(day)), 0) + qty
    for f in erp.all('SELECT * FROM forecasts WHERE week_start <= ? ORDER BY sku, week_start', horizon):
        wk_end = (parse_day(f['week_start']) + timedelta(days=6)).isoformat()
        if wk_end < today:
            continue
        first = f['week_start'] if erp.is_workday(f['week_start']) else erp.add_workdays(f['week_start'], 1)
        add_demand(f['sku'], first, f['qty'] - ordered.get((f['sku'], f['week_start']), 0), f'forecast {f["week_start"]}')
    for wo in erp.all("SELECT * FROM work_orders WHERE status IN ('planned', 'released', 'in_progress') ORDER BY id"):
        remaining = wo['qty'] - wo['qty_completed'] - wo['qty_scrapped']
        if remaining > 1e-9:
            supply.setdefault(wo['sku'], []).append((max(wo['due_date'], today), q4(remaining), wo['id']))
        need = manufacturing.explode(erp, wo['sku'], wo['qty'], wo['start_date'])
        done = manufacturing.issued(erp, wo['id'])
        for comp, q in sorted(need.items()):
            add_demand(comp, wo['start_date'], q - done.get(comp, 0), wo['id'])
    for l in erp.all("SELECT l.*, p.vendor FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id WHERE p.status IN "
                     "('sent', 'partially_received') AND l.status = 'open' AND l.sku IS NOT NULL ORDER BY l.po_id, l.line"):
        open_qty = l['qty'] - l['qty_received']
        if open_qty > 1e-9 and l['sku'] in supply:
            supply[l['sku']].append((max(l['confirmed_date'] or l['need_date'], today), q4(open_qty),
                                     f'{l["po_id"]}/{l["line"]}'))
    n = 0

    def suggest(**row):
        nonlocal n
        n += 1
        erp.insert('mrp_suggestions', {'id': f'{run_id}-{n:04d}', 'run_id': run_id, **row})

    for sku in sorted(items, key=lambda s: (llc.get(s, 0), s)):
        it = items[sku]
        balance = on_hand(erp, sku)
        safety = it['safety_stock'] or 0
        receipts = sorted(supply.get(sku, []))
        weekly: dict[str, list] = {}
        for day, qty, src in sorted(demand[sku]):
            weekly.setdefault(week_of(day), []).append((day, qty))
        buckets = [(weekly[wk][0][0], q4(sum(q for _d, q in weekly[wk]))) for wk in sorted(weekly)]
        for day, qty in buckets:
            balance = q4(balance - qty)
            while balance < safety - 1e-9 and receipts:
                due, rq, ref = receipts.pop(0)
                balance = q4(balance + rq)
                if ref.startswith('PO-'):
                    if due > day:
                        suggest(sku=sku, kind='expedite', qty=rq, need_date=day, ref=ref, current_date=due)
                    elif erp.workdays_between(due, day) > DEFER_TOLERANCE:
                        suggest(sku=sku, kind='defer', qty=rq, need_date=day, ref=ref, current_date=due)
            if balance < safety - 1e-9:
                qty_order = _lot(safety - balance, it['moq'], it['order_multiple'])
                release = erp.add_workdays(day, -(it['lead_time_days'] or 0))
                kind = 'planned_wo' if it['type'] == 'manufactured' else 'planned_po'
                suggest(sku=sku, kind=kind, qty=qty_order, need_date=day, release_date=release,
                        vendor=it['preferred_vendor'] if kind == 'planned_po' else None,
                        firm=1 if release <= fence else 0, late=1 if release < today else 0)
                balance = q4(balance + qty_order)
                if kind == 'planned_wo':
                    start = max(release, today)
                    for comp, q in sorted(manufacturing.explode(erp, sku, qty_order, start).items()):
                        add_demand(comp, start, q, f'planned {sku}')
        for due, rq, ref in receipts:
            if ref.startswith('PO-') and due <= horizon:
                suggest(sku=sku, kind='cancel', qty=rq, need_date=due, ref=ref, current_date=due)
    erp.touch('mrp_run', run_id, created=True)
    return run_id


def release(erp: Erp, ctx: Ctx, suggestion_id: str, qty: float | None = None, need_date: str | None = None,
            vendor: str | None = None) -> str:
    """Turn a planned order into a sent purchase order or a planned work order."""
    ctx.require('mrp.release')
    s = erp.one('SELECT * FROM mrp_suggestions WHERE id = ?', suggestion_id)
    if s is None:
        raise not_found('MRP suggestion', suggestion_id)
    if s['status'] != 'open':
        raise refused('bad_status', f'{suggestion_id} is {s["status"]}; run MRP again for current suggestions')
    if s['kind'] not in ('planned_po', 'planned_wo'):
        raise invalid(f'{suggestion_id} is an action message; act on it with a request to the vendor')
    qty = q4(qty if qty is not None else s['qty'])
    need = need_date or s['need_date']
    erp.touch('mrp_suggestion', suggestion_id)
    if s['kind'] == 'planned_po':
        po = purchasing.create_po(erp, ctx, vendor or s['vendor'], [{'sku': s['sku'], 'qty': qty, 'need_date': need}],
                                  note=f'Released from {suggestion_id}')
        purchasing.send_po(erp, ctx, po)
        made = po
    else:
        it = erp.one('SELECT * FROM items WHERE sku = ?', s['sku'])
        start = max(erp.add_workdays(need, -(it['lead_time_days'] or 0)), erp.today)
        made = manufacturing.create_wo(erp, ctx, s['sku'], qty, start, need, note=f'Released from {suggestion_id}')
    erp.update('mrp_suggestions', {'id': suggestion_id}, {'status': 'released', 'released_as': made})
    return made
