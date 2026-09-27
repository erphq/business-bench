"""General ledger: postings from documents, manual journal entries, attachments, and periods."""
from __future__ import annotations

from .core import Ctx, Erp, ErpError, forbidden, invalid, limit_cents, not_found, period_of, refused, to_cents


def ensure_open(erp: Erp, day: str) -> str:
    p = erp.one('SELECT * FROM periods WHERE period = ?', period_of(day))
    if p is None:
        raise refused('period_missing', f'there is no accounting period for {day}')
    if p['status'] != 'open':
        raise refused('period_closed', f'period {p["period"]} is closed; date the entry in an open period',
                      period=p['period'])
    return p['period']


def _normalise(erp: Erp, lines) -> list[tuple]:
    rows = []
    for ln in lines:
        acct, dr, cr = ln[0], int(ln[1] or 0), int(ln[2] or 0)
        dept = ln[3] if len(ln) > 3 else None
        memo = ln[4] if len(ln) > 4 else None
        net = dr - cr
        if net == 0:
            continue
        rows.append((erp.account(acct), max(net, 0), max(-net, 0), dept, memo))
    return rows


def post(erp: Erp, ctx: Ctx, day: str, source: str, source_ref: str | None, lines, memo: str | None = None) -> str | None:
    """Post a system entry from a document. `lines` are (account key or code, debit cents, credit cents
    [, department[, memo]]); a negative amount moves to the other side. Returns the entry id, or None when
    every line nets to zero."""
    period = ensure_open(erp, day)
    rows = _normalise(erp, lines)
    if not rows:
        return None
    tdr, tcr = sum(r[1] for r in rows), sum(r[2] for r in rows)
    if tdr != tcr:
        raise ErpError('unbalanced', f'posting for {source_ref} does not balance ({tdr} vs {tcr})', 500)
    je = erp.next_id('JE')
    erp.insert('journal_entries', {'id': je, 'entry_date': day, 'period': period, 'source': source,
                                   'source_ref': source_ref, 'memo': memo, 'status': 'posted', 'preparer': ctx.user,
                                   'created_on': erp.today, 'posted_on': erp.today})
    for i, (acct, dr, cr, dept, m) in enumerate(rows, 1):
        erp.insert('journal_lines', {'je_id': je, 'line': i, 'account': acct, 'department': dept,
                                     'debit_cents': dr, 'credit_cents': cr, 'memo': m})
    return je


# ------------------------------------------------------------------------------------------- manual entries

def _je(erp: Erp, je_id: str) -> dict:
    je = erp.one('SELECT * FROM journal_entries WHERE id = ?', je_id)
    if je is None:
        raise not_found('journal entry', je_id)
    return je


def je_total(erp: Erp, je_id: str) -> int:
    return erp.val('SELECT COALESCE(SUM(debit_cents), 0) FROM journal_lines WHERE je_id = ?', je_id)


def _check_lines(erp: Erp, lines: list[dict]) -> list[dict]:
    if not lines or len(lines) < 2:
        raise invalid('a journal entry needs at least two lines')
    out = []
    for i, ln in enumerate(lines, 1):
        acct = str(ln.get('account', ''))
        a = erp.one('SELECT * FROM accounts WHERE code = ?', acct)
        if a is None or not a['active']:
            raise invalid(f'line {i}: no active account {acct!r}')
        dr, cr = int(ln.get('debit_cents') or 0), int(ln.get('credit_cents') or 0)
        if 'debit' in ln or 'credit' in ln:
            dr, cr = to_cents(ln.get('debit') or 0), to_cents(ln.get('credit') or 0)
        if dr < 0 or cr < 0 or (dr and cr) or not (dr or cr):
            raise invalid(f'line {i}: give either a positive debit or a positive credit')
        out.append({'account': acct, 'debit_cents': dr, 'credit_cents': cr,
                    'department': ln.get('department'), 'memo': ln.get('memo')})
    if sum(l['debit_cents'] for l in out) != sum(l['credit_cents'] for l in out):
        raise invalid('debits and credits do not balance')
    return out


def create_manual(erp: Erp, ctx: Ctx, entry_date: str, lines: list[dict], memo: str,
                  auto_reverse_on: str | None = None, note: str | None = None) -> str:
    ctx.require('je.create')
    if not erp.val('SELECT 1 FROM periods WHERE period = ?', period_of(entry_date)):
        raise refused('period_missing', f'there is no accounting period for {entry_date}')
    rows = _check_lines(erp, lines)
    je = erp.next_id('JE')
    erp.insert('journal_entries', {'id': je, 'entry_date': entry_date, 'period': period_of(entry_date),
                                   'source': 'manual', 'memo': memo, 'status': 'draft', 'preparer': ctx.user,
                                   'auto_reverse_on': auto_reverse_on, 'created_on': erp.today, 'note': note})
    for i, r in enumerate(rows, 1):
        erp.insert('journal_lines', {'je_id': je, 'line': i, **r})
    erp.touch('journal_entry', je, created=True)
    return je


def replace_lines(erp: Erp, ctx: Ctx, je_id: str, lines: list[dict], memo: str | None = None) -> None:
    je = _je(erp, je_id)
    if je['status'] not in ('draft', 'returned'):
        raise refused('not_editable', f'{je_id} is {je["status"]}; only draft or returned entries can be edited')
    if je['preparer'] != ctx.user:
        raise forbidden(f'only the preparer can edit {je_id}')
    rows = _check_lines(erp, lines)
    erp.touch('journal_entry', je_id)
    erp.run('DELETE FROM journal_lines WHERE je_id = ?', je_id)
    for i, r in enumerate(rows, 1):
        erp.insert('journal_lines', {'je_id': je_id, 'line': i, **r})
    if memo is not None:
        erp.update('journal_entries', {'id': je_id}, {'memo': memo})


def submit(erp: Erp, ctx: Ctx, je_id: str) -> None:
    ctx.require('je.create')
    je = _je(erp, je_id)
    if je['status'] not in ('draft', 'returned'):
        raise refused('bad_status', f'{je_id} is {je["status"]}')
    if je['preparer'] != ctx.user:
        raise forbidden(f'only the preparer can submit {je_id}')
    erp.touch('journal_entry', je_id)
    erp.update('journal_entries', {'id': je_id}, {'status': 'submitted'})


def approve(erp: Erp, ctx: Ctx, je_id: str, note: str | None = None) -> None:
    ctx.require('je.approve')
    je = _je(erp, je_id)
    if je['status'] != 'submitted':
        raise refused('bad_status', f'{je_id} is {je["status"]}; only submitted entries can be approved')
    if je['preparer'] == ctx.user:
        raise refused('preparer_cannot_approve', f'{ctx.user} prepared {je_id} and cannot approve it')
    total = je_total(erp, je_id)
    if total > limit_cents(erp, ctx.user, 'journal_entry'):
        raise refused('over_limit', f'{je_id} is above {ctx.user}\'s approval limit', total_cents=total)
    erp.touch('journal_entry', je_id)
    erp.update('journal_entries', {'id': je_id}, {'status': 'approved', 'approver': ctx.user,
                                                 'note': note if note is not None else je['note']})


def return_entry(erp: Erp, ctx: Ctx, je_id: str, reason: str) -> None:
    ctx.require('je.approve')
    je = _je(erp, je_id)
    if je['status'] != 'submitted':
        raise refused('bad_status', f'{je_id} is {je["status"]}')
    erp.touch('journal_entry', je_id)
    erp.update('journal_entries', {'id': je_id}, {'status': 'returned', 'note': reason})


def post_manual(erp: Erp, ctx: Ctx, je_id: str) -> None:
    ctx.require('je.post')
    je = _je(erp, je_id)
    threshold = erp.setting('je_approval_threshold_cents', 0)
    total = je_total(erp, je_id)
    if je['status'] == 'approved':
        pass
    elif je['status'] in ('draft', 'submitted') and total < threshold:
        if je['preparer'] != ctx.user:
            raise forbidden(f'only the preparer can post an unapproved {je_id}')
    else:
        raise refused('approval_required', f'{je_id} is {je["status"]}; entries of {total / 100:.2f} need approval '
                      f'by someone other than the preparer before posting', total_cents=total)
    ensure_open(erp, je['entry_date'])
    erp.touch('journal_entry', je_id)
    erp.update('journal_entries', {'id': je_id}, {'status': 'posted', 'posted_on': erp.today})


def reverse(erp: Erp, ctx: Ctx, je_id: str, reverse_date: str | None = None, reason: str | None = None) -> str:
    ctx.require('je.post')
    je = _je(erp, je_id)
    if je['status'] != 'posted':
        raise refused('bad_status', f'{je_id} is {je["status"]}; only posted entries can be reversed')
    day = reverse_date or erp.today
    lines = erp.all('SELECT * FROM journal_lines WHERE je_id = ? ORDER BY line', je_id)
    rev = post(erp, ctx, day, 'reversal', je_id,
               [(l['account'], l['credit_cents'], l['debit_cents'], l['department'], l['memo']) for l in lines],
               memo=f'Reversal of {je_id}' + (f': {reason}' if reason else ''))
    erp.touch('journal_entry', je_id)
    erp.update('journal_entries', {'id': je_id}, {'status': 'reversed', 'reversed_by': rev})
    erp.update('journal_entries', {'id': rev}, {'reverses': je_id})
    erp.touch('journal_entry', rev, created=True)
    return rev


# ------------------------------------------------------------------------------------------- attachments

def attach(erp: Erp, ctx: Ctx, owner_type: str, owner_id: str, name: str, content_type: str, data: bytes) -> str:
    aid = erp.next_id('ATT')
    erp.insert('attachments', {'id': aid, 'owner_type': owner_type, 'owner_id': owner_id, 'name': name,
                               'content_type': content_type, 'data': data, 'added_by': ctx.user,
                               'added_on': erp.today})
    return aid


# ------------------------------------------------------------------------------------------- periods

def close_period(erp: Erp, ctx: Ctx, period: str) -> None:
    ctx.require('period.close')
    p = erp.one('SELECT * FROM periods WHERE period = ?', period)
    if p is None:
        raise not_found('period', period)
    if p['status'] == 'closed':
        raise refused('period_closed', f'period {period} is already closed')
    erp.touch('period', period)
    erp.update('periods', {'period': period}, {'status': 'closed', 'closed_by': ctx.user, 'closed_on': erp.today})


def reopen_period(erp: Erp, ctx: Ctx, period: str) -> None:
    ctx.require('period.reopen')
    p = erp.one('SELECT * FROM periods WHERE period = ?', period)
    if p is None:
        raise not_found('period', period)
    erp.touch('period', period)
    erp.update('periods', {'period': period}, {'status': 'open', 'closed_by': None, 'closed_on': None})


def balance_cents(erp: Erp, account: str, as_of: str | None = None) -> int:
    """Debit-positive balance of posted and reversed entries (a reversed entry and its reversal both count)."""
    sql = ("SELECT COALESCE(SUM(l.debit_cents - l.credit_cents), 0) FROM journal_lines l "
           "JOIN journal_entries e ON e.id = l.je_id WHERE l.account = ? AND e.status IN ('posted', 'reversed')")
    args = [erp.account(account)]
    if as_of:
        sql += ' AND e.entry_date <= ?'
        args.append(as_of)
    return erp.val(sql, *args)
