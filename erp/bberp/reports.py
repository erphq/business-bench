"""Read-only reports. Every report takes keyword filters and returns plain JSON-able data."""
from __future__ import annotations

from datetime import timedelta

from . import inventory, manufacturing, payables, receiving, sales
from .core import Erp, add_days, dollars, ext_cents, invalid, parse_day, period_of, q4
from .ledger import balance_cents


def trial_balance(erp: Erp, as_of: str | None = None, period: str | None = None) -> dict:
    sql = ("SELECT a.code, a.name, a.type, COALESCE(SUM(l.debit_cents), 0) AS dr, COALESCE(SUM(l.credit_cents), 0) AS cr "
           "FROM accounts a LEFT JOIN journal_lines l ON l.account = a.code "
           "LEFT JOIN journal_entries e ON e.id = l.je_id WHERE (e.id IS NULL OR (e.status IN ('posted', 'reversed')")
    args = []
    if as_of:
        sql += ' AND e.entry_date <= ?'; args.append(as_of)
    if period:
        sql += ' AND e.period = ?'; args.append(period)
    sql += ')) GROUP BY a.code ORDER BY a.code'
    rows, tdr, tcr = [], 0, 0
    for r in erp.all(sql, *args):
        if not r['dr'] and not r['cr']:
            continue
        bal = r['dr'] - r['cr']
        tdr, tcr = tdr + r['dr'], tcr + r['cr']
        rows.append({'account': r['code'], 'name': r['name'], 'type': r['type'], 'debit': dollars(r['dr']),
                     'credit': dollars(r['cr']), 'balance': dollars(bal), 'balance_cents': bal})
    return {'as_of': as_of or erp.today, 'period': period, 'accounts': rows, 'total_debit': dollars(tdr),
            'total_credit': dollars(tcr), 'balanced': tdr == tcr}


def control_ties(erp: Erp, as_of: str | None = None) -> dict:
    """Each control account against its subledger. `difference` is ledger minus subledger (debit-positive)."""
    as_of = as_of or erp.today
    subs = {
        'ap': -payables.ap_subledger_cents(erp, as_of),
        'grni': -receiving.grni_cents(erp, as_of),
        'inventory': inventory.valuation_cents(erp, as_of),
        'ar': sales.ar_subledger_cents(erp, as_of),
        'unapplied_cash': -sales.unapplied_cash_cents(erp, as_of),
        'wip': manufacturing.wip_cents(erp, as_of=as_of),
    }
    out = {}
    for key, sub in subs.items():
        acct = erp.val('SELECT account FROM posting_rules WHERE key = ?', key)
        if not acct:
            continue
        gl = balance_cents(erp, acct, as_of)
        out[key] = {'account': acct, 'ledger_cents': gl, 'subledger_cents': sub, 'difference_cents': gl - sub}
    return {'as_of': as_of, 'controls': out, 'all_tie': all(v['difference_cents'] == 0 for v in out.values())}


def _bucket(days: int) -> str:
    if days <= 0:
        return 'current'
    if days <= 30:
        return '1-30'
    if days <= 60:
        return '31-60'
    if days <= 90:
        return '61-90'
    return '90+'


def ap_aging(erp: Erp, as_of: str | None = None, vendor: str | None = None) -> dict:
    as_of = as_of or erp.today
    sql = "SELECT * FROM ap_invoices WHERE status IN ('entered', 'matched', 'on_hold', 'approved')"
    args = []
    if vendor:
        sql += ' AND vendor = ?'; args.append(vendor)
    rows = []
    for inv in erp.all(sql + ' ORDER BY due_date, id', *args):
        open_ = payables.open_cents(erp, inv['id'])
        if open_ <= 0:
            continue
        late = (parse_day(as_of) - parse_day(inv['due_date'])).days
        rows.append({'invoice': inv['id'], 'vendor': inv['vendor'], 'invoice_no': inv['invoice_no'],
                     'invoice_date': inv['invoice_date'], 'due_date': inv['due_date'], 'status': inv['status'],
                     'posted': bool(inv['posted_je']), 'open': dollars(open_), 'open_cents': open_, 'days_past_due': max(late, 0),
                     'bucket': _bucket(late), 'discount_date': inv['discount_date'],
                     'discount': dollars(inv['discount_cents']),
                     'holds': [h['reason'] for h in payables.active_holds(erp, inv['id'])]})
    return {'as_of': as_of, 'invoices': rows}


def ar_aging(erp: Erp, as_of: str | None = None, customer: str | None = None) -> dict:
    as_of = as_of or erp.today
    sql = "SELECT * FROM ar_invoices WHERE status = 'open'"
    args = []
    if customer:
        sql += ' AND customer = ?'; args.append(customer)
    rows = []
    for inv in erp.all(sql + ' ORDER BY due_date, id', *args):
        open_ = sales.ar_open_cents(erp, inv['id'])
        if open_ <= 0:
            continue
        late = (parse_day(as_of) - parse_day(inv['due_date'])).days
        rows.append({'invoice': inv['id'], 'customer': inv['customer'], 'invoice_date': inv['invoice_date'],
                     'due_date': inv['due_date'], 'open': dollars(open_), 'open_cents': open_,
                     'days_past_due': max(late, 0),
                     'bucket': _bucket(late)})
    return {'as_of': as_of, 'invoices': rows}


def grni(erp: Erp, as_of: str | None = None) -> dict:
    as_of = as_of or erp.today
    rows = []
    for pl in erp.all("SELECT l.*, p.vendor, p.status AS po_status FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id "
                      "WHERE p.status != 'draft' ORDER BY l.po_id, l.line"):
        rec = erp.val("SELECT COALESCE(SUM(rl.grni_cents), 0) FROM receipt_lines rl JOIN receipts r ON r.id = rl.receipt_id "
                      "WHERE r.po_id = ? AND rl.po_line = ? AND r.status = 'posted' AND r.receipt_date <= ?",
                      pl['po_id'], pl['line'], as_of)
        billed = erp.val("SELECT COALESCE(SUM(il.grni_cents), 0) FROM ap_invoice_lines il JOIN ap_invoices i "
                         "ON i.id = il.inv_id WHERE i.po_id = ? AND il.po_line = ? AND il.grni_cents IS NOT NULL",
                         pl['po_id'], pl['line'])
        if rec - billed:
            rows.append({'po': pl['po_id'], 'line': pl['line'], 'vendor': pl['vendor'], 'sku': pl['sku'],
                         'qty_received': pl['qty_received'], 'qty_billed': pl['qty_billed'],
                         'unit_price': pl['unit_price'], 'received_not_invoiced': dollars(rec - billed)})
    return {'as_of': as_of, 'lines': rows, 'total': dollars(receiving.grni_cents(erp, as_of))}


def open_purchase_orders(erp: Erp, vendor: str | None = None, sku: str | None = None) -> dict:
    sql = ("SELECT p.id AS po, p.vendor, p.order_date, p.status, p.ship_to, l.line, l.sku, l.qty, l.qty_received, "
           "l.qty_refused, l.unit_price, l.need_date, l.confirmed_date, l.at_risk FROM po_lines l "
           "JOIN purchase_orders p ON p.id = l.po_id WHERE p.status IN ('draft', 'sent', 'partially_received') "
           "AND l.status = 'open'")
    args = []
    if vendor:
        sql += ' AND p.vendor = ?'; args.append(vendor)
    if sku:
        sql += ' AND l.sku = ?'; args.append(sku)
    rows = erp.all(sql + ' ORDER BY p.id, l.line', *args)
    for r in rows:
        r['qty_open'] = q4(max(r['qty'] - r['qty_received'], 0))
        r['at_risk'] = bool(r['at_risk'])
    return {'lines': rows}


def on_hand(erp: Erp, sku: str | None = None, location: str | None = None, as_of: str | None = None) -> dict:
    sql = ("SELECT t.sku, i.name, t.location, t.lot, l.expiry, ROUND(SUM(t.qty), 4) AS qty, "
           "SUM(t.value_cents) AS value_cents FROM inventory_txns t JOIN items i ON i.sku = t.sku "
           "LEFT JOIN lots l ON l.sku = t.sku AND l.lot = t.lot WHERE 1 = 1")
    args = []
    if sku:
        sql += ' AND t.sku = ?'; args.append(sku)
    if location:
        sql += ' AND t.location = ?'; args.append(location)
    if as_of:
        sql += ' AND t.txn_date <= ?'; args.append(as_of)
    rows = erp.all(sql + ' GROUP BY t.sku, t.location, t.lot HAVING ABS(SUM(t.qty)) > 0.00001 '
                         'ORDER BY t.sku, t.location, l.expiry, t.lot', *args)
    for r in rows:
        r['value'] = dollars(r.pop('value_cents'))
    return {'as_of': as_of or erp.today, 'stock': rows}


def item_usage(erp: Erp, sku: str | None = None, months: int = 6, as_of: str | None = None) -> dict:
    """Average monthly consumption (work-order issues and shipments, net of reversals) over the last whole months."""
    as_of = as_of or erp.today
    end = parse_day(as_of).replace(day=1)
    start = end
    for _ in range(months):
        start = (start - timedelta(days=1)).replace(day=1)
    sql = ("SELECT sku, -ROUND(SUM(qty), 4) AS used FROM inventory_txns WHERE kind IN "
           "('wo_issue', 'wo_issue_reversal', 'shipment') AND txn_date >= ? AND txn_date < ?")
    args = [start.isoformat(), end.isoformat()]
    if sku:
        sql += ' AND sku = ?'; args.append(sku)
    rows = erp.all(sql + ' GROUP BY sku ORDER BY sku', *args)
    return {'from': start.isoformat(), 'to': add_days(end.isoformat(), -1), 'months': months,
            'items': [{'sku': r['sku'], 'used': r['used'], 'avg_per_month': q4(r['used'] / months)} for r in rows]}


def budget_vs_actual(erp: Erp, department: str | None = None, period_from: str | None = None,
                     period_to: str | None = None) -> dict:
    """Budget, posted actuals by department and account, and commitments: open PO value from requisitions."""
    period_to = period_to or period_of(erp.today)
    period_from = period_from or period_to[:4] + '-01'
    args = [period_from, period_to]
    dsql = ' AND department = ?' if department else ''
    budget = erp.all('SELECT department, account, SUM(amount_cents) AS c FROM budgets WHERE period BETWEEN ? AND ?'
                     + dsql + ' GROUP BY department, account', *args, *([department] if department else []))
    actual = erp.all("SELECT l.department, l.account, SUM(l.debit_cents - l.credit_cents) AS c FROM journal_lines l "
                     "JOIN journal_entries e ON e.id = l.je_id WHERE e.status IN ('posted', 'reversed') AND e.period "
                     "BETWEEN ? AND ? AND l.department IS NOT NULL" + dsql.replace('department', 'l.department') +
                     ' GROUP BY l.department, l.account', *args, *([department] if department else []))
    commit_rows = erp.all(
        "SELECT r.department, rl.account, pl.qty, pl.qty_received, pl.qty_billed, pl.unit_price FROM requisition_lines rl "
        "JOIN requisitions r ON r.id = rl.req_id JOIN po_lines pl ON pl.po_id = rl.po_id AND pl.line = rl.po_line "
        "JOIN purchase_orders p ON p.id = pl.po_id WHERE p.status IN ('sent', 'partially_received', 'received') "
        "AND pl.status = 'open'" + (' AND r.department = ?' if department else ''), *([department] if department else []))
    unconverted = erp.all(
        "SELECT r.department, rl.account, rl.amount_cents FROM requisition_lines rl JOIN requisitions r ON r.id = rl.req_id "
        "WHERE r.status IN ('approved', 'converted') AND rl.po_id IS NULL" + (' AND r.department = ?' if department else ''),
        *([department] if department else []))
    table: dict[tuple, dict] = {}

    def cell(d, a):
        return table.setdefault((d, a), {'department': d, 'account': a, 'budget_cents': 0, 'actual_cents': 0,
                                         'committed_cents': 0})
    for r in budget:
        cell(r['department'], r['account'])['budget_cents'] += r['c']
    for r in actual:
        cell(r['department'], r['account'])['actual_cents'] += r['c']
    for r in commit_rows:
        open_qty = max(r['qty'] - max(r['qty_received'], r['qty_billed']), 0)
        cell(r['department'], r['account'])['committed_cents'] += ext_cents(open_qty, r['unit_price'])
    for r in unconverted:
        cell(r['department'], r['account'])['committed_cents'] += r['amount_cents']
    rows = []
    for (d, a), c in sorted(table.items(), key=lambda kv: (kv[0][0] or '', kv[0][1] or '')):
        rem = c['budget_cents'] - c['actual_cents'] - c['committed_cents']
        rows.append({'department': d, 'account': a, 'budget': dollars(c['budget_cents']),
                     'actual': dollars(c['actual_cents']), 'committed': dollars(c['committed_cents']),
                     'remaining': dollars(rem)})
    return {'from': period_from, 'to': period_to, 'lines': rows}


def cash_position(erp: Erp, days: int = 30) -> dict:
    end = add_days(erp.today, days)
    banks = [{'bank_account': b['code'], 'balance': dollars(balance_cents(erp, b['gl_account'])),
              'min_balance': dollars(b['min_balance_cents'])} for b in erp.all('SELECT * FROM bank_accounts ORDER BY code')]
    ap = [r for r in ap_aging(erp)['invoices'] if r['due_date'] <= end]
    ar = [r for r in ar_aging(erp)['invoices'] if r['due_date'] <= end]
    return {'as_of': erp.today, 'through': end, 'banks': banks,
            'ap_due': dollars(sum(r['open_cents'] for r in ap)),
            'ar_due': dollars(sum(r['open_cents'] for r in ar))}


def sales_margin(erp: Erp, period: str | None = None, by: str = 'item') -> dict:
    period = period or period_of(erp.today)
    if by not in ('item', 'customer'):
        raise invalid('by is item or customer')
    key = 'l.sku' if by == 'item' else 'i.customer'
    rev = {r['k']: r['c'] for r in erp.all(
        f"SELECT {key} AS k, SUM(l.amount_cents) AS c FROM ar_invoice_lines l JOIN ar_invoices i ON i.id = l.inv_id "
        f"WHERE i.period = ? AND i.status != 'voided' GROUP BY {key}", period)}
    skey = 't.sku' if by == 'item' else 's.customer'
    cogs = {r['k']: -r['c'] for r in erp.all(
        f"SELECT {skey} AS k, SUM(t.value_cents) AS c FROM inventory_txns t JOIN shipments h ON h.id = t.ref_id "
        f"JOIN sales_orders s ON s.id = h.so_id WHERE t.kind = 'shipment' AND substr(t.txn_date, 1, 7) = ? "
        f"GROUP BY {skey}", period)}
    rows = []
    for k in sorted(set(rev) | set(cogs)):
        r, c = rev.get(k, 0), cogs.get(k, 0)
        rows.append({by: k, 'revenue': dollars(r), 'cost': dollars(c), 'margin': dollars(r - c),
                     'margin_pct': round((r - c) / r * 100, 2) if r else None})
    return {'period': period, 'by': by, 'rows': rows}


REPORTS = {
    'trial-balance': trial_balance, 'control-ties': control_ties, 'ap-aging': ap_aging, 'ar-aging': ar_aging,
    'grni': grni, 'open-purchase-orders': open_purchase_orders, 'on-hand': on_hand, 'item-usage': item_usage,
    'budget-vs-actual': budget_vs_actual, 'cash-position': cash_position, 'sales-margin': sales_margin,
}
