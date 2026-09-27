"""Accounts payable: vendor invoices, three-way match, holds, validation (posting), approval for payment, payment
runs, and vendor master data including bank-account changes.

The system shows the match between invoice, PO and receipts but does not place holds itself: deciding what to
hold, and why, is the AP clerk's job. Hard controls: an exact duplicate invoice number per vendor is refused;
a held invoice cannot be validated, approved or paid; payment only to a verified bank account of an active vendor;
a payment run is approved by someone other than its preparer, within their limit.

Posting at validation: Dr GRNI at PO price for PO-matched quantity, invoice price variance for the difference,
freight and other lines to their accounts; Cr accounts payable for the total.
"""
from __future__ import annotations

from . import ledger
from .core import (Ctx, Erp, ErpError, add_days, ext_cents, forbidden, invalid, limit_cents, not_found, q4,
                   refused, to_cents)

HOLD_REASONS = ('price', 'quantity', 'no_receipt', 'duplicate_suspect', 'vendor', 'tax', 'freight', 'other')
LINE_KINDS = ('item', 'freight', 'tax', 'other')


# ------------------------------------------------------------------------------------------- invoices

def _inv(erp: Erp, inv_id: str) -> dict:
    inv = erp.one('SELECT * FROM ap_invoices WHERE id = ?', inv_id)
    if inv is None:
        raise not_found('AP invoice', inv_id)
    return inv


def active_holds(erp: Erp, inv_id: str) -> list[dict]:
    return erp.all("SELECT * FROM holds WHERE doc_type = 'ap_invoice' AND doc_id = ? AND released_on IS NULL "
                   "ORDER BY id", inv_id)


def _terms(erp: Erp, code: str | None) -> dict:
    t = erp.one('SELECT * FROM terms WHERE code = ?', code) if code else None
    return t or {'code': None, 'net_days': 30, 'discount_pct': 0, 'discount_days': 0}


def _check_line(erp: Erp, inv: dict, ln: dict, i: int) -> dict:
    kind = ln.get('kind') or ('item' if ln.get('po_line') or ln.get('sku') else 'other')
    if kind not in LINE_KINDS:
        raise invalid(f'line {i}: kind must be one of {", ".join(LINE_KINDS)}')
    row = {'kind': kind, 'po_line': ln.get('po_line'), 'sku': ln.get('sku'), 'description': ln.get('description'),
           'qty': None, 'unit_price': None, 'account': ln.get('account'), 'department': ln.get('department')}
    if kind == 'item':
        if row['po_line'] is not None:
            if not inv['po_id']:
                raise invalid(f'line {i}: po_line given but the invoice has no po_id')
            pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', inv['po_id'], row['po_line'])
            if pl is None:
                raise not_found('PO line', f'{inv["po_id"]}/{row["po_line"]}')
            row['sku'] = row['sku'] or pl['sku']
        if ln.get('qty') is None or ln.get('unit_price') is None:
            raise invalid(f'line {i}: item lines need qty and unit_price as billed')
        row['qty'], row['unit_price'] = q4(ln['qty']), q4(ln['unit_price'])
        row['amount_cents'] = to_cents(ln['amount']) if ln.get('amount') is not None else ext_cents(row['qty'], row['unit_price'])
        if row['po_line'] is None and not row['account']:
            raise invalid(f'line {i}: an item line without a PO line needs an account')
    else:
        if row['po_line'] is not None:
            raise invalid(f'line {i}: a line billed against a PO line is an item line (kind item, with qty and '
                          'unit_price as billed), for non-stock PO lines too; freight, tax and other lines are not '
                          'matched to the PO')
        if ln.get('amount') is None:
            raise invalid(f'line {i}: {kind} lines need an amount')
        row['amount_cents'] = to_cents(ln['amount'])
        if kind == 'freight':
            row['account'] = row['account'] or erp.account('freight_in')
        elif kind == 'tax':
            row['account'] = row['account'] or erp.account('purchase_tax')
        elif not row['account']:
            raise invalid(f'line {i}: other lines need an account')
    if row['account'] and not erp.val('SELECT 1 FROM accounts WHERE code = ? AND active = 1', row['account']):
        raise invalid(f'line {i}: no active account {row["account"]}')
    return row


def enter_invoice(erp: Erp, ctx: Ctx, vendor: str, invoice_no: str, invoice_date: str, lines: list[dict],
                  po_id: str | None = None, source_msg: str | None = None, note: str | None = None) -> str:
    ctx.require('ap.enter')
    v = erp.one('SELECT * FROM vendors WHERE id = ?', vendor)
    if v is None:
        raise not_found('vendor', vendor)
    invoice_no = (invoice_no or '').strip()
    if not invoice_no:
        raise invalid('give the vendor invoice number')
    dup = erp.one('SELECT id, status FROM ap_invoices WHERE vendor = ? AND invoice_no = ?', vendor, invoice_no)
    if dup:
        raise refused('duplicate_invoice', f'{vendor} invoice {invoice_no} is already entered as {dup["id"]}',
                      existing=dup['id'])
    if po_id:
        po = erp.one('SELECT * FROM purchase_orders WHERE id = ?', po_id)
        if po is None:
            raise not_found('purchase order', po_id)
        if po['vendor'] != vendor:
            raise invalid(f'{po_id} belongs to {po["vendor"]}, not {vendor}')
    if source_msg and not erp.val('SELECT 1 FROM messages WHERE id = ?', source_msg):
        raise not_found('message', source_msg)
    if not lines:
        raise invalid('an invoice needs at least one line')
    inv_id = erp.next_id('APINV')
    head = {'id': inv_id, 'vendor': vendor, 'invoice_no': invoice_no, 'invoice_date': invoice_date,
            'po_id': po_id, 'total_cents': 0, 'status': 'entered', 'terms': v['terms'],
            'due_date': invoice_date, 'entered_by': ctx.user, 'entered_on': erp.today,
            'source_msg': source_msg, 'note': note}
    rows = [_check_line(erp, head, ln, i) for i, ln in enumerate(lines, 1)]
    total = sum(r['amount_cents'] for r in rows)
    t = _terms(erp, v['terms'])
    head.update({'total_cents': total, 'due_date': add_days(invoice_date, t['net_days'])})
    if t['discount_pct']:
        head['discount_date'] = add_days(invoice_date, t['discount_days'])
        head['discount_cents'] = to_cents(total / 100 * t['discount_pct'] / 100)
    erp.insert('ap_invoices', head)
    for i, r in enumerate(rows, 1):
        erp.insert('ap_invoice_lines', {'inv_id': inv_id, 'line': i, **r})
    erp.touch('ap_invoice', inv_id, created=True)
    return inv_id


def update_invoice_line(erp: Erp, ctx: Ctx, inv_id: str, line: int, changes: dict) -> None:
    ctx.require('ap.enter')
    inv = _inv(erp, inv_id)
    if inv['status'] not in ('entered', 'on_hold') or inv['posted_je']:
        raise refused('bad_status', f'{inv_id} is {inv["status"]}; posted invoices cannot be edited')
    cur = erp.one('SELECT * FROM ap_invoice_lines WHERE inv_id = ? AND line = ?', inv_id, line)
    if cur is None:
        raise not_found('invoice line', f'{inv_id}/{line}')
    merged = {k: cur[k] for k in ('kind', 'po_line', 'sku', 'description', 'qty', 'unit_price', 'account',
                                  'department')}
    merged['amount'] = None
    merged.update(changes)
    row = _check_line(erp, inv, merged, line)
    erp.touch('ap_invoice', inv_id)
    erp.update('ap_invoice_lines', {'inv_id': inv_id, 'line': line}, row)
    _retotal(erp, inv_id)


def _retotal(erp: Erp, inv_id: str) -> None:
    inv = _inv(erp, inv_id)
    total = erp.val('SELECT COALESCE(SUM(amount_cents), 0) FROM ap_invoice_lines WHERE inv_id = ?', inv_id)
    t = _terms(erp, inv['terms'])
    disc = to_cents(total / 100 * t['discount_pct'] / 100) if t['discount_pct'] else 0
    erp.update('ap_invoices', {'id': inv_id}, {'total_cents': total, 'discount_cents': disc})


def match(erp: Erp, inv_id: str) -> list[dict]:
    """Per item line: what was ordered, received and billed before, against what this invoice bills."""
    inv = _inv(erp, inv_id)
    out = []
    for ln in erp.all("SELECT * FROM ap_invoice_lines WHERE inv_id = ? ORDER BY line", inv_id):
        row = {'line': ln['line'], 'kind': ln['kind'], 'billed_qty': ln['qty'], 'billed_price': ln['unit_price'],
               'billed_amount': ln['amount_cents'] / 100}
        if ln['kind'] == 'item' and ln['po_line'] is not None and inv['po_id']:
            pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', inv['po_id'], ln['po_line'])
            billed_before = erp.val(
                "SELECT COALESCE(SUM(l.qty), 0) FROM ap_invoice_lines l JOIN ap_invoices i ON i.id = l.inv_id "
                "WHERE i.po_id = ? AND l.po_line = ? AND i.id != ? AND i.status IN ('matched', 'approved', 'paid')",
                inv['po_id'], ln['po_line'], inv_id)
            price_var = (ln['unit_price'] - pl['unit_price']) / pl['unit_price'] * 100 if pl['unit_price'] else None
            row.update({'po_line': ln['po_line'], 'sku': pl['sku'], 'po_qty': pl['qty'], 'po_price': pl['unit_price'],
                        'received_qty': pl['qty_received'], 'refused_qty': pl['qty_refused'],
                        'billed_before_qty': q4(billed_before),
                        'unbilled_received_qty': q4(pl['qty_received'] - billed_before),
                        'price_variance_pct': round(price_var, 2) if price_var is not None else None,
                        'qty_over_received': q4(max(0.0, billed_before + ln['qty'] - pl['qty_received']))})
        out.append(row)
    return out


def place_hold(erp: Erp, ctx: Ctx, inv_id: str, reason: str, line: int | None = None, note: str | None = None) -> str:
    ctx.require('ap.hold')
    inv = _inv(erp, inv_id)
    if inv['status'] in ('paid', 'rejected', 'voided'):
        raise refused('bad_status', f'{inv_id} is {inv["status"]}')
    if reason not in HOLD_REASONS:
        raise invalid(f'reason must be one of {", ".join(HOLD_REASONS)}')
    if line is not None and not erp.val('SELECT 1 FROM ap_invoice_lines WHERE inv_id = ? AND line = ?', inv_id, line):
        raise not_found('invoice line', f'{inv_id}/{line}')
    hid = erp.next_id('HOLD')
    erp.touch('ap_invoice', inv_id)
    erp.insert('holds', {'id': hid, 'doc_type': 'ap_invoice', 'doc_id': inv_id, 'line': line, 'reason': reason,
                         'note': note, 'placed_by': ctx.user, 'placed_on': erp.today})
    erp.update('ap_invoices', {'id': inv_id}, {'status': 'on_hold'})
    erp.touch('hold', hid, created=True)
    return hid


def release_hold(erp: Erp, ctx: Ctx, hold_id: str, note: str) -> None:
    ctx.require('ap.release_hold')
    h = erp.one('SELECT * FROM holds WHERE id = ?', hold_id)
    if h is None:
        raise not_found('hold', hold_id)
    if h['released_on']:
        raise refused('bad_status', f'{hold_id} was already released')
    if not note:
        raise invalid('say why the hold is released')
    erp.touch('hold', hold_id)
    erp.touch('ap_invoice', h['doc_id'])
    erp.update('holds', {'id': hold_id}, {'released_by': ctx.user, 'released_on': erp.today, 'release_note': note})
    if not active_holds(erp, h['doc_id']):
        inv = _inv(erp, h['doc_id'])
        if inv['status'] == 'on_hold':
            erp.update('ap_invoices', {'id': inv['id']}, {'status': 'matched' if inv['posted_je'] else 'entered'})


def validate(erp: Erp, ctx: Ctx, inv_id: str) -> str:
    """Accept the invoice as matched and post it. The clerk decides it matches; the system only refuses holds."""
    ctx.require('ap.validate')
    inv = _inv(erp, inv_id)
    if active_holds(erp, inv_id):
        raise refused('on_hold', f'{inv_id} has active holds; a supervisor must release them first')
    if inv['status'] != 'entered' or inv['posted_je']:
        raise refused('bad_status', f'{inv_id} is {inv["status"]}')
    lines = erp.all('SELECT * FROM ap_invoice_lines WHERE inv_id = ? ORDER BY line', inv_id)
    post = []
    for ln in lines:
        if ln['kind'] == 'item' and ln['po_line'] is not None:
            pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', inv['po_id'], ln['po_line'])
            grni = ext_cents(ln['qty'], pl['unit_price'])
            erp.update('ap_invoice_lines', {'inv_id': inv_id, 'line': ln['line']}, {'grni_cents': grni})
            erp.update('po_lines', {'po_id': inv['po_id'], 'line': ln['po_line']},
                       {'qty_billed': q4(pl['qty_billed'] + ln['qty'])})
            post += [('grni', grni, 0), ('ipv', ln['amount_cents'] - grni, 0)]
        else:
            post.append((ln['account'] or erp.account('freight_in'), ln['amount_cents'], 0, ln['department']))
    post.append(('ap', 0, inv['total_cents']))
    erp.touch('ap_invoice', inv_id)
    je = ledger.post(erp, ctx, erp.today, 'payables', inv_id, post,
                     memo=f'{inv["vendor"]} invoice {inv["invoice_no"]}')
    erp.update('ap_invoices', {'id': inv_id}, {'status': 'matched', 'posted_je': je, 'period': erp.today[:7]})
    return je


def approve_invoice(erp: Erp, ctx: Ctx, inv_id: str, note: str | None = None) -> None:
    ctx.require('ap.approve')
    inv = _inv(erp, inv_id)
    if active_holds(erp, inv_id):
        raise refused('on_hold', f'{inv_id} has active holds')
    if inv['status'] != 'matched':
        raise refused('bad_status', f'{inv_id} is {inv["status"]}; validate it before approving for payment')
    if inv['entered_by'] == ctx.user and inv['total_cents'] > erp.setting('ap_self_approval_limit_cents', 0):
        raise refused('preparer_cannot_approve', f'{ctx.user} entered {inv_id} and cannot approve it for payment')
    erp.touch('ap_invoice', inv_id)
    erp.update('ap_invoices', {'id': inv_id}, {'status': 'approved', 'approved_by': ctx.user,
                                              'note': note if note is not None else inv['note']})


def reject_invoice(erp: Erp, ctx: Ctx, inv_id: str, reason: str) -> None:
    ctx.require('ap.enter')
    inv = _inv(erp, inv_id)
    if inv['posted_je'] or inv['status'] not in ('entered', 'on_hold'):
        raise refused('bad_status', f'{inv_id} is {inv["status"]}; posted invoices are voided, not rejected')
    if not reason:
        raise invalid('give a reason')
    erp.touch('ap_invoice', inv_id)
    erp.update('ap_invoices', {'id': inv_id}, {'status': 'rejected', 'reject_reason': reason})


def void_invoice(erp: Erp, ctx: Ctx, inv_id: str, reason: str) -> None:
    ctx.require('ap.void')
    inv = _inv(erp, inv_id)
    if not inv['posted_je'] or inv['status'] not in ('matched', 'approved', 'on_hold'):
        raise refused('bad_status', f'{inv_id} is {inv["status"]}')
    if paid_cents(erp, inv_id):
        raise refused('has_payments', f'{inv_id} has payments; void them first')
    erp.touch('ap_invoice', inv_id)
    ledger.reverse_posting(erp, ctx, inv['posted_je'], reason=reason)
    for ln in erp.all("SELECT * FROM ap_invoice_lines WHERE inv_id = ? AND grni_cents IS NOT NULL", inv_id):
        pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', inv['po_id'], ln['po_line'])
        erp.update('po_lines', {'po_id': inv['po_id'], 'line': ln['po_line']},
                   {'qty_billed': q4(pl['qty_billed'] - ln['qty'])})
        erp.update('ap_invoice_lines', {'inv_id': inv_id, 'line': ln['line']}, {'grni_cents': None})
    erp.update('ap_invoices', {'id': inv_id}, {'status': 'voided', 'reject_reason': reason})


def paid_cents(erp: Erp, inv_id: str) -> int:
    return erp.val("SELECT COALESCE(SUM(a.amount_cents + a.discount_cents), 0) FROM payment_allocations a "
                   "JOIN payments p ON p.id = a.payment_id WHERE a.inv_id = ? AND p.status IN ('released', 'cleared')",
                   inv_id)


def open_cents(erp: Erp, inv_id: str) -> int:
    return _inv(erp, inv_id)['total_cents'] - paid_cents(erp, inv_id)


def ap_subledger_cents(erp: Erp, as_of: str | None = None) -> int:
    """Credit-positive: posted invoices less released payments and discounts."""
    isql = ("SELECT COALESCE(SUM(i.total_cents), 0) FROM ap_invoices i JOIN journal_entries e ON e.id = i.posted_je "
            "WHERE i.posted_je IS NOT NULL")
    vsql = ("SELECT COALESCE(SUM(i.total_cents), 0) FROM ap_invoices i JOIN journal_entries e ON e.reverses = i.posted_je "
            "WHERE i.status = 'voided'")
    psql = ("SELECT COALESCE(SUM(a.amount_cents + a.discount_cents), 0) FROM payment_allocations a "
            "JOIN payments p ON p.id = a.payment_id JOIN journal_entries e ON e.id = p.posted_je "
            "WHERE p.status IN ('released', 'cleared')")
    args = []
    if as_of:
        isql += ' AND e.entry_date <= ?'; vsql += ' AND e.entry_date <= ?'; psql += ' AND e.entry_date <= ?'
        args = [as_of]
    return erp.val(isql, *args) - erp.val(vsql, *args) - erp.val(psql, *args)


# ------------------------------------------------------------------------------------------- payment runs

def _run(erp: Erp, run_id: str) -> dict:
    r = erp.one('SELECT * FROM payment_runs WHERE id = ?', run_id)
    if r is None:
        raise not_found('payment run', run_id)
    return r


def create_run(erp: Erp, ctx: Ctx, pay_date: str, bank_account: str, note: str | None = None) -> str:
    ctx.require('pay.prepare')
    if not erp.val('SELECT 1 FROM bank_accounts WHERE code = ?', bank_account):
        raise not_found('bank account', bank_account)
    if pay_date < erp.today:
        raise invalid('pay date is in the past')
    rid = erp.next_id('RUN')
    erp.insert('payment_runs', {'id': rid, 'pay_date': pay_date, 'bank_account': bank_account, 'status': 'draft',
                                'created_by': ctx.user, 'created_on': erp.today, 'note': note})
    erp.touch('payment_run', rid, created=True)
    return rid


def _payable_checks(erp: Erp, inv: dict) -> dict:
    if inv['status'] != 'approved':
        raise refused('not_approved', f'{inv["id"]} is {inv["status"]}; only invoices approved for payment are paid')
    if active_holds(erp, inv['id']):
        raise refused('on_hold', f'{inv["id"]} has active holds')
    v = erp.one('SELECT * FROM vendors WHERE id = ?', inv['vendor'])
    if v['status'] != 'active':
        raise refused('vendor_inactive', f'{v["id"]} is inactive')
    acct = erp.one("SELECT * FROM vendor_bank_accounts WHERE id = ? AND status = 'verified'", v['remit_account'] or '')
    if acct is None:
        raise refused('no_verified_account', f'{v["id"]} has no verified bank account to pay')
    return acct


def _refresh_payment(erp: Erp, pay_id: str) -> None:
    amt = erp.val('SELECT COALESCE(SUM(amount_cents), 0) FROM payment_allocations WHERE payment_id = ?', pay_id)
    disc = erp.val('SELECT COALESCE(SUM(discount_cents), 0) FROM payment_allocations WHERE payment_id = ?', pay_id)
    if not erp.val('SELECT 1 FROM payment_allocations WHERE payment_id = ?', pay_id):
        erp.run('DELETE FROM payments WHERE id = ?', pay_id)
    else:
        erp.update('payments', {'id': pay_id}, {'amount_cents': amt, 'discount_cents': disc})


def add_to_run(erp: Erp, ctx: Ctx, run_id: str, inv_id: str, amount_cents: int | None = None,
               take_discount: bool = True) -> str:
    ctx.require('pay.prepare')
    run = _run(erp, run_id)
    if run['status'] != 'draft':
        raise refused('bad_status', f'{run_id} is {run["status"]}')
    inv = _inv(erp, inv_id)
    acct = _payable_checks(erp, inv)
    if erp.val("SELECT 1 FROM payment_allocations a JOIN payments p ON p.id = a.payment_id "
               "WHERE a.inv_id = ? AND p.status = 'proposed'", inv_id):
        raise refused('already_proposed', f'{inv_id} is already in a payment run')
    open_ = open_cents(erp, inv_id)
    discount = 0
    if amount_cents is None:
        if take_discount and inv['discount_cents'] and inv['discount_date'] and run['pay_date'] <= inv['discount_date'] \
                and paid_cents(erp, inv_id) == 0:
            discount = inv['discount_cents']
        amount_cents = open_ - discount
    elif amount_cents <= 0 or amount_cents > open_:
        raise invalid(f'amount must be between 0.01 and the open balance {open_ / 100:.2f}')
    erp.touch('payment_run', run_id)
    pay = erp.one("SELECT * FROM payments WHERE run_id = ? AND vendor = ? AND status = 'proposed'", run_id, inv['vendor'])
    if pay is None:
        pid = erp.next_id('PAY')
        erp.insert('payments', {'id': pid, 'run_id': run_id, 'vendor': inv['vendor'], 'vendor_account': acct['id'],
                                'pay_date': run['pay_date'], 'amount_cents': 0, 'status': 'proposed'})
        erp.touch('payment', pid, created=True)
    else:
        pid = pay['id']
        erp.touch('payment', pid)
    erp.insert('payment_allocations', {'payment_id': pid, 'inv_id': inv_id, 'amount_cents': amount_cents,
                                       'discount_cents': discount})
    _refresh_payment(erp, pid)
    return pid


def remove_from_run(erp: Erp, ctx: Ctx, run_id: str, inv_id: str) -> None:
    ctx.require('pay.prepare')
    run = _run(erp, run_id)
    if run['status'] != 'draft':
        raise refused('bad_status', f'{run_id} is {run["status"]}')
    pay = erp.one("SELECT p.* FROM payments p JOIN payment_allocations a ON a.payment_id = p.id "
                  "WHERE p.run_id = ? AND a.inv_id = ?", run_id, inv_id)
    if pay is None:
        raise not_found('invoice in run', inv_id)
    erp.touch('payment_run', run_id)
    erp.touch('payment', pay['id'])
    erp.run('DELETE FROM payment_allocations WHERE payment_id = ? AND inv_id = ?', pay['id'], inv_id)
    _refresh_payment(erp, pay['id'])


def run_total_cents(erp: Erp, run_id: str) -> int:
    return erp.val("SELECT COALESCE(SUM(amount_cents), 0) FROM payments WHERE run_id = ? AND status != 'voided'", run_id)


def submit_run(erp: Erp, ctx: Ctx, run_id: str) -> None:
    ctx.require('pay.prepare')
    run = _run(erp, run_id)
    if run['status'] != 'draft':
        raise refused('bad_status', f'{run_id} is {run["status"]}')
    if not erp.val('SELECT 1 FROM payments WHERE run_id = ?', run_id):
        raise refused('empty_run', f'{run_id} has no payments')
    erp.touch('payment_run', run_id)
    erp.update('payment_runs', {'id': run_id}, {'status': 'submitted'})


def approve_run(erp: Erp, ctx: Ctx, run_id: str, note: str | None = None) -> None:
    ctx.require('pay.approve')
    run = _run(erp, run_id)
    if run['status'] != 'submitted':
        raise refused('bad_status', f'{run_id} is {run["status"]}')
    if run['created_by'] == ctx.user:
        raise refused('preparer_cannot_approve', f'{ctx.user} prepared {run_id} and cannot approve it')
    total = run_total_cents(erp, run_id)
    if total > limit_cents(erp, ctx.user, 'payment_run'):
        raise refused('over_limit', f'{run_id} totals {total / 100:.2f}, above {ctx.user}\'s limit')
    erp.touch('payment_run', run_id)
    erp.update('payment_runs', {'id': run_id}, {'status': 'approved', 'approved_by': ctx.user,
                                               'note': note if note is not None else run['note']})


def return_run(erp: Erp, ctx: Ctx, run_id: str, reason: str) -> None:
    ctx.require('pay.approve')
    run = _run(erp, run_id)
    if run['status'] != 'submitted':
        raise refused('bad_status', f'{run_id} is {run["status"]}')
    erp.touch('payment_run', run_id)
    erp.update('payment_runs', {'id': run_id}, {'status': 'draft', 'note': reason})


def release_run(erp: Erp, ctx: Ctx, run_id: str) -> list[str]:
    ctx.require('pay.release')
    run = _run(erp, run_id)
    if run['status'] != 'approved':
        raise refused('bad_status', f'{run_id} is {run["status"]}; runs are released after approval')
    bank = erp.one('SELECT * FROM bank_accounts WHERE code = ?', run['bank_account'])
    erp.touch('payment_run', run_id)
    released = []
    for pay in erp.all("SELECT * FROM payments WHERE run_id = ? AND status = 'proposed' ORDER BY id", run_id):
        allocs = erp.all('SELECT * FROM payment_allocations WHERE payment_id = ? ORDER BY inv_id', pay['id'])
        for a in allocs:
            acct = _payable_checks(erp, _inv(erp, a['inv_id']))
            if acct['id'] != pay['vendor_account']:
                raise refused('account_changed', f'{pay["vendor"]}\'s verified account changed after {pay["id"]} '
                              'was proposed; rebuild the run')
        erp.touch('payment', pay['id'])
        je = ledger.post(erp, ctx, erp.today, 'payments', pay['id'],
                         [('ap', pay['amount_cents'] + pay['discount_cents'], 0), (bank['gl_account'], 0, pay['amount_cents']),
                          ('purchase_discounts', 0, pay['discount_cents'])], memo=f'Payment {pay["id"]} to {pay["vendor"]}')
        erp.update('payments', {'id': pay['id']}, {'status': 'released', 'posted_je': je})
        for a in allocs:
            if open_cents(erp, a['inv_id']) <= 0:
                erp.touch('ap_invoice', a['inv_id'])
                erp.update('ap_invoices', {'id': a['inv_id']}, {'status': 'paid'})
        released.append(pay['id'])
    erp.update('payment_runs', {'id': run_id}, {'status': 'released', 'released_by': ctx.user})
    return released


def clear_payment(erp: Erp, ctx: Ctx, pay_id: str) -> str:
    """The bank reports the payment. Used by the bank simulator."""
    ctx.require('bank.post')
    pay = erp.one('SELECT * FROM payments WHERE id = ?', pay_id)
    if pay is None or pay['status'] != 'released':
        raise refused('bad_status', f'{pay_id} is not a released payment')
    run = _run(erp, pay['run_id']) if pay['run_id'] else None
    line = erp.next_id('BSL')
    acct = erp.one('SELECT * FROM vendor_bank_accounts WHERE id = ?', pay['vendor_account'])
    erp.insert('bank_statement_lines', {'id': line, 'bank_account': run['bank_account'] if run else erp.meta('default_bank'),
                                        'line_date': erp.today, 'amount_cents': -pay['amount_cents'],
                                        'description': f'ACH {acct["bank_name"]} ...{acct["account_no"][-4:]}',
                                        'reference': pay_id, 'matched_to': pay_id})
    erp.touch('payment', pay_id)
    erp.update('payments', {'id': pay_id}, {'status': 'cleared', 'cleared_on': erp.today})
    return line


# ------------------------------------------------------------------------------------------- vendors

VENDOR_FIELDS = ('name', 'phone', 'email', 'address', 'terms', 'status', 'quality_hold', 'note', 'tin')


def create_vendor(erp: Erp, ctx: Ctx, fields: dict) -> str:
    ctx.require('vendor.create')
    bad = set(fields) - set(VENDOR_FIELDS)
    if bad:
        raise invalid(f'unknown vendor fields {sorted(bad)}; bank details are added as a bank-account request')
    if not fields.get('name'):
        raise invalid('a vendor needs a name')
    if fields.get('terms') and not erp.val('SELECT 1 FROM terms WHERE code = ?', fields['terms']):
        raise invalid(f'no payment terms {fields["terms"]}')
    vid = erp.next_id('V')
    erp.insert('vendors', {'id': vid, 'status': 'active', 'since': erp.today, **{k: fields.get(k) for k in VENDOR_FIELDS
                                                                                 if k != 'status' and k in fields}})
    erp.touch('vendor', vid, created=True)
    return vid


def update_vendor(erp: Erp, ctx: Ctx, vid: str, changes: dict) -> None:
    ctx.require('vendor.update')
    if not erp.val('SELECT 1 FROM vendors WHERE id = ?', vid):
        raise not_found('vendor', vid)
    bad = set(changes) - set(VENDOR_FIELDS)
    if bad:
        raise invalid(f'cannot change {sorted(bad)}; bank details change through a bank-account request')
    if 'status' in changes and changes['status'] not in ('active', 'inactive'):
        raise invalid('status is active or inactive')
    if 'quality_hold' in changes:
        changes['quality_hold'] = 1 if changes['quality_hold'] else 0
    erp.touch('vendor', vid)
    erp.update('vendors', {'id': vid}, changes)


def request_bank_change(erp: Erp, ctx: Ctx, vid: str, bank_name: str, routing: str, account_no: str,
                        source_ref: str | None = None, note: str | None = None) -> str:
    ctx.require('vendor.bank.request')
    if not erp.val('SELECT 1 FROM vendors WHERE id = ?', vid):
        raise not_found('vendor', vid)
    if not (bank_name and routing and account_no):
        raise invalid('give bank_name, routing and account_no')
    aid = erp.next_id('VBA')
    erp.insert('vendor_bank_accounts', {'id': aid, 'vendor': vid, 'bank_name': bank_name, 'routing': str(routing),
                                        'account_no': str(account_no), 'status': 'pending', 'requested_by': ctx.user,
                                        'requested_on': erp.today, 'source_ref': source_ref, 'note': note})
    erp.touch('vendor_bank_account', aid, created=True)
    return aid


def verify_bank_account(erp: Erp, ctx: Ctx, acct_id: str, note: str | None = None) -> None:
    ctx.require('vendor.bank.verify')
    a = erp.one('SELECT * FROM vendor_bank_accounts WHERE id = ?', acct_id)
    if a is None:
        raise not_found('vendor bank account', acct_id)
    if a['status'] != 'pending':
        raise refused('bad_status', f'{acct_id} is {a["status"]}')
    if a['requested_by'] == ctx.user:
        raise refused('requester_cannot_approve', f'{ctx.user} requested {acct_id} and cannot verify it')
    erp.touch('vendor_bank_account', acct_id)
    erp.touch('vendor', a['vendor'])
    for old in erp.all("SELECT id FROM vendor_bank_accounts WHERE vendor = ? AND status = 'verified'", a['vendor']):
        erp.touch('vendor_bank_account', old['id'])
        erp.update('vendor_bank_accounts', {'id': old['id']}, {'status': 'retired'})
    erp.update('vendor_bank_accounts', {'id': acct_id}, {'status': 'verified', 'verified_by': ctx.user,
                                                         'verified_on': erp.today, 'note': note or a['note']})
    erp.update('vendors', {'id': a['vendor']}, {'remit_account': acct_id})


def reject_bank_account(erp: Erp, ctx: Ctx, acct_id: str, reason: str) -> None:
    ctx.require('vendor.bank.verify')
    a = erp.one('SELECT * FROM vendor_bank_accounts WHERE id = ?', acct_id)
    if a is None:
        raise not_found('vendor bank account', acct_id)
    if a['status'] != 'pending':
        raise refused('bad_status', f'{acct_id} is {a["status"]}')
    if not reason:
        raise invalid('give a reason')
    erp.touch('vendor_bank_account', acct_id)
    erp.update('vendor_bank_accounts', {'id': acct_id}, {'status': 'rejected', 'note': reason})


def cancel_bank_request(erp: Erp, ctx: Ctx, acct_id: str, reason: str) -> None:
    """The requester withdraws a pending bank-detail change."""
    ctx.require('vendor.bank.request')
    a = erp.one('SELECT * FROM vendor_bank_accounts WHERE id = ?', acct_id)
    if a is None:
        raise not_found('vendor bank account', acct_id)
    if a['status'] != 'pending':
        raise refused('bad_status', f'{acct_id} is {a["status"]}')
    if a['requested_by'] != ctx.user and not ctx.can('vendor.bank.verify'):
        raise forbidden('only the requester can withdraw this request')
    erp.touch('vendor_bank_account', acct_id)
    erp.update('vendor_bank_accounts', {'id': acct_id}, {'status': 'rejected', 'note': f'withdrawn: {reason}'})
