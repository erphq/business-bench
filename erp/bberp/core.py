"""Core of bb-erp: the database handle, errors, the acting user, money, the calendar, document numbers,
and the before/after snapshots the audit log records.

Every service function takes `(erp, ctx, ...)`: `erp` is the open company database, `ctx` says who is acting.
Nothing in bb-erp reads the wall clock except the audit log's `wall_time` column, which grading ignores.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')


class ErpError(Exception):
    """A refused or invalid request. `code` is the machine code clients branch on."""

    def __init__(self, code: str, message: str, status: int = 400, **detail):
        super().__init__(message)
        self.code, self.message, self.status, self.detail = code, message, status, detail

    def problem(self) -> dict:
        out = {'type': f'https://businessbench.org/erp/errors/{self.code}', 'title': self.code,
               'status': self.status, 'detail': self.message}
        if self.detail:
            out['context'] = self.detail
        return out


def refused(code: str, message: str, **detail) -> ErpError:
    """A hard control said no (HTTP 409). Logged as a probe."""
    return ErpError(code, message, 409, **detail)


def forbidden(message: str, **detail) -> ErpError:
    return ErpError('forbidden', message, 403, **detail)


def not_found(what: str, key) -> ErpError:
    return ErpError('not_found', f'{what} {key} does not exist', 404)


def invalid(message: str, **detail) -> ErpError:
    return ErpError('invalid', message, 422, **detail)


# ----------------------------------------------------------------------------------------------- money

def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def to_cents(amount) -> int:
    return int((D(amount) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def ext_cents(qty, price) -> int:
    """Extended amount of qty x unit price, in cents, rounded half up."""
    return to_cents(D(qty) * D(price))


def q4(x) -> float:
    return float(D(x).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP))


def dollars(cents: int) -> str:
    sign = '-' if cents < 0 else ''
    return f'{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}'


# ----------------------------------------------------------------------------------------------- dates

def parse_day(s: str) -> date:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        raise invalid(f'not a date: {s!r} (use YYYY-MM-DD)')


def add_days(day: str, n: int) -> str:
    return (parse_day(day) + timedelta(days=n)).isoformat()


def period_of(day: str) -> str:
    return str(day)[:7]


# ----------------------------------------------------------------------------------------------- acting user

@dataclass(frozen=True)
class Ctx:
    user: str
    roles: frozenset = field(default_factory=frozenset)
    permissions: frozenset = field(default_factory=frozenset)
    token_id: str | None = None
    channel: str = 'api'          # api (an agent or person), sim (a counterparty), setup (the generator)

    def can(self, action: str) -> bool:
        return '*' in self.permissions or action in self.permissions

    def require(self, action: str) -> None:
        if not self.can(action):
            raise forbidden(f'{self.user} is not permitted to {action}', action=action)


# ----------------------------------------------------------------------------------------------- snapshots

# object type -> (table, key column, [(child table, foreign key, order by)])
OBJECTS = {
    'requisition': ('requisitions', 'id', [('requisition_lines', 'req_id', 'line')]),
    'approval_request': ('approval_requests', 'id', []),
    'purchase_order': ('purchase_orders', 'id', [('po_lines', 'po_id', 'line')]),
    'receipt': ('receipts', 'id', [('receipt_lines', 'receipt_id', 'line')]),
    'ap_invoice': ('ap_invoices', 'id', [('ap_invoice_lines', 'inv_id', 'line')]),
    'hold': ('holds', 'id', []),
    'payment_run': ('payment_runs', 'id', []),
    'payment': ('payments', 'id', [('payment_allocations', 'payment_id', 'inv_id')]),
    'vendor': ('vendors', 'id', []),
    'vendor_bank_account': ('vendor_bank_accounts', 'id', []),
    'customer': ('customers', 'id', []),
    'item': ('items', 'sku', []),
    'journal_entry': ('journal_entries', 'id', [('journal_lines', 'je_id', 'line')]),
    'period': ('periods', 'period', []),
    'work_order': ('work_orders', 'id', []),
    'sales_order': ('sales_orders', 'id', [('so_lines', 'so_id', 'line')]),
    'shipment': ('shipments', 'id', [('shipment_lines', 'shipment_id', 'line')]),
    'ar_invoice': ('ar_invoices', 'id', [('ar_invoice_lines', 'inv_id', 'line')]),
    'cash_receipt': ('cash_receipts', 'id', [('cash_applications', 'receipt_id', 'inv_id')]),
    'message': ('messages', 'id', []),
    'escalation': ('escalations', 'id', []),
    'call': ('calls', 'id', []),
    'stock_move': ('inventory_txns', 'ref_id', []),
    'vendor_request': ('vendor_requests', 'id', []),
}


class Erp:
    """One company's database. Thread-safe by serialising every transaction on one lock."""

    def __init__(self, path: str, world: dict | None = None):
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys = ON')
        self.lock = threading.RLock()
        self.world = world or {}
        self._depth = 0
        self._touched: dict | None = None

    @classmethod
    def create(cls, path: str) -> 'Erp':
        if os.path.exists(path):
            os.remove(path)
        erp = cls(path)
        with open(SCHEMA, encoding='utf-8') as f:
            erp.db.executescript(f.read())
        return erp

    def close(self) -> None:
        self.db.close()

    # queries --------------------------------------------------------------------------------------
    def run(self, sql: str, *args) -> sqlite3.Cursor:
        return self.db.execute(sql, args)

    def one(self, sql: str, *args) -> dict | None:
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row is not None else None

    def all(self, sql: str, *args) -> list[dict]:
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def val(self, sql: str, *args):
        row = self.db.execute(sql, args).fetchone()
        return row[0] if row is not None else None

    def insert(self, table: str, row: dict) -> None:
        cols = list(row)
        self.db.execute(f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({", ".join("?" * len(cols))})',
                        [row[c] for c in cols])

    def update(self, table: str, key: dict, changes: dict) -> None:
        if not changes:
            return
        sets = ', '.join(f'{c} = ?' for c in changes)
        where = ' AND '.join(f'{c} = ?' for c in key)
        self.db.execute(f'UPDATE {table} SET {sets} WHERE {where}', [*changes.values(), *key.values()])

    # transactions ---------------------------------------------------------------------------------
    @contextmanager
    def tx(self):
        """Outermost call opens BEGIN IMMEDIATE; nested calls join it. Any exception rolls back everything."""
        with self.lock:
            outer = self._depth == 0
            if outer:
                self.db.execute('BEGIN IMMEDIATE')
            self._depth += 1
            try:
                yield self
            except BaseException:
                self._depth -= 1
                if outer:
                    self.db.execute('ROLLBACK')
                raise
            else:
                self._depth -= 1
                if outer:
                    self.db.execute('COMMIT')

    # company state --------------------------------------------------------------------------------
    def meta(self, key: str, default=None):
        v = self.val('SELECT value FROM meta WHERE key = ?', key)
        return default if v is None else v

    def set_meta(self, key: str, value) -> None:
        self.run('INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                 key, str(value))

    @property
    def today(self) -> str:
        return self.meta('business_date')

    def set_today(self, day: str) -> None:
        self.set_meta('business_date', parse_day(day).isoformat())

    def setting(self, key: str, default=None):
        """Numeric company settings stored in meta (tolerances, thresholds)."""
        v = self.meta(key)
        if v is None:
            return default
        try:
            return int(v)
        except ValueError:
            return float(v)

    def next_id(self, prefix: str) -> str:
        row = self.one('SELECT next FROM seq WHERE prefix = ?', prefix)
        n = row['next'] if row else 10001
        self.run('INSERT INTO seq (prefix, next) VALUES (?, ?) ON CONFLICT(prefix) DO UPDATE SET next = excluded.next',
                 prefix, n + 1)
        return f'{prefix}-{n}'

    def account(self, key: str) -> str:
        """Resolve a posting-rule key (inventory, grni, ap, ...) or pass through an account code."""
        acct = self.val('SELECT account FROM posting_rules WHERE key = ?', key)
        if acct:
            return acct
        if self.val('SELECT 1 FROM accounts WHERE code = ?', key):
            return key
        raise invalid(f'no account or posting rule {key!r}')

    # calendar -------------------------------------------------------------------------------------
    def is_workday(self, day: str) -> bool:
        v = self.val('SELECT workday FROM calendar WHERE day = ?', day)
        if v is not None:
            return bool(v)
        return parse_day(day).weekday() < 5

    def add_workdays(self, day: str, n: int) -> str:
        d = day
        step = 1 if n >= 0 else -1
        left = abs(n)
        while left:
            d = add_days(d, step)
            if self.is_workday(d):
                left -= 1
        return d

    def workdays_between(self, start: str, end: str) -> int:
        """Workdays after `start` up to and including `end`."""
        n, d = 0, start
        while d < end:
            d = add_days(d, 1)
            if self.is_workday(d):
                n += 1
        return n

    # audit snapshots ------------------------------------------------------------------------------
    def snapshot(self, otype: str, oid) -> dict | None:
        spec = OBJECTS.get(otype)
        if not spec:
            return None
        table, key, children = spec
        if otype == 'stock_move':
            rows = self.all('SELECT * FROM inventory_txns WHERE ref_id = ? ORDER BY id', oid)
            return {'lines': rows} if rows else None
        head = self.one(f'SELECT * FROM {table} WHERE {key} = ?', oid)
        if head is None:
            return None
        for ctable, fk, order in children:
            head[ctable] = self.all(f'SELECT * FROM {ctable} WHERE {fk} = ? ORDER BY {order}', oid)
        if otype == 'ap_invoice':
            head['holds'] = self.all("SELECT * FROM holds WHERE doc_type = 'ap_invoice' AND doc_id = ? ORDER BY id", oid)
        return head

    def begin_audit(self) -> None:
        self._touched = {}

    def touch(self, otype: str, oid, created: bool = False) -> None:
        """Call before changing an existing object, or with created=True right after inserting a new one."""
        if self._touched is None:
            return
        k = f'{otype}:{oid}'
        if k not in self._touched:
            self._touched[k] = (otype, oid, None if created else self.snapshot(otype, oid))

    def end_audit(self) -> tuple[dict, dict]:
        touched, self._touched = self._touched or {}, None
        before, after = {}, {}
        for k, (otype, oid, snap) in touched.items():
            before[k] = snap
            after[k] = self.snapshot(otype, oid)
        return before, after

    def audit(self, ctx: Ctx | None, *, method=None, path=None, action=None, object_type=None, object_id=None,
              before=None, after=None, outcome='ok', error_code=None, idem_key=None, request=None,
              wall_time=None) -> None:
        self.insert('audit_events', {
            'business_date': self.today, 'wall_time': wall_time, 'channel': ctx.channel if ctx else 'api',
            'actor': ctx.user if ctx else None, 'token_id': ctx.token_id if ctx else None,
            'method': method, 'path': path, 'action': action, 'object_type': object_type,
            'object_id': object_id, 'before': json.dumps(before, sort_keys=True, default=str) if before else None,
            'after': json.dumps(after, sort_keys=True, default=str) if after else None,
            'outcome': outcome, 'error_code': error_code, 'idem_key': idem_key,
            'request': json.dumps(request, sort_keys=True, default=str)[:20000] if request is not None else None})


def load_ctx(erp: Erp, user_id: str, token_id: str | None = None, channel: str = 'api') -> Ctx:
    user = erp.one('SELECT * FROM users WHERE id = ?', user_id)
    if user is None or not user['active']:
        raise ErpError('unauthorized', 'unknown or inactive user', 401)
    roles = frozenset(r['role'] for r in erp.all('SELECT role FROM user_roles WHERE user_id = ?', user_id))
    perms = frozenset(p['action'] for p in erp.all(
        f'SELECT DISTINCT action FROM role_permissions WHERE role IN ({",".join("?" * len(roles)) or "NULL"})', *roles))
    return Ctx(user=user_id, roles=roles, permissions=perms, token_id=token_id, channel=channel)


def limit_cents(erp: Erp, user: str, doc_type: str) -> int:
    return erp.val('SELECT limit_cents FROM approval_limits WHERE user_id = ? AND doc_type = ?', user, doc_type) or 0


def user_on_leave(erp: Erp, user: str, day: str) -> bool:
    return bool(erp.val('SELECT 1 FROM leave WHERE user_id = ? AND start_date <= ? AND end_date >= ?', user, day, day))


def delegate_of(erp: Erp, user: str, day: str) -> str | None:
    return erp.val('SELECT delegate FROM delegations WHERE user_id = ? AND start_date <= ? AND end_date >= ?',
                   user, day, day)
