#!/usr/bin/env python3
"""Property-based, crash and determinism testing for bb-erp, the process track's ERP.

Every process-track verdict is computed from bb-erp's final database and audit log, so a kernel bug (a write that
half-applies, a subledger that stops tying, a nondeterministic export) could move a score through no fault of the
agent. This tool drives bb-erp through the same request handler agents use (`bberp.api.handle`, which the HTTP server
calls) with random but seeded call sequences drawn from a generated process-task scenario, and checks invariants
after every call. It is a development tool: nothing in the runner or the grader imports it.

    erp_fuzz.py --task payment-run --seed 0 --steps 300 --sequences 5          # fuzz
    erp_fuzz.py --task payment-run --seed 0 --atomicity                        # fault-injection sweep
    erp_fuzz.py --task payment-run --seed 0 --replay-check                     # deterministic replay
    erp_fuzz.py --task payment-run --seed 0 --crash 5                          # SIGKILL the server (slow)
    erp_fuzz.py --replay-file calls.json                                       # re-run a saved sequence

Invariants checked after every call (`Checker`):
  no_5xx               no 5xx and no unhandled exception; invalid calls are refused with a 4xx problem
  expected_refusal     a call the generator built to be invalid (wrong id, over limit, closed period, wrong status,
                       wrong role, delete of a posted document, ...) is refused, not accepted
  one_audit_row        each request appends exactly one audit row whose outcome matches the status
  refused_unchanged    a refused (4xx) or failed (5xx) call leaves every table except audit_events unchanged
  reads_unchanged      a GET changes nothing but the audit log (and message read marks)
  replay_unchanged     an Idempotency-Key replay returns the first response and changes nothing
  audit_append_only    earlier audit rows are never changed or removed (per call, and a prefix hash)
  trial_balance        the trial balance balances, and every posted entry balances on its own
  ledger_ties          each control account equals its subledger (bberp.reports.control_ties, the grader's
                       ledger_ties logic); a call may not change any difference
  documents_kept       document rows are never deleted (only unreleased proposed payments may be)
  posted_immutable     posted journal entries and lines, receipts, posted AP invoices, released payments,
                       shipments, AR invoices, cash receipts, stock moves, WO issues and bank lines keep their content
  lifecycle            every status change (and every new document's first status) is legal for its document type
  consistency          derived facts hold: stock never negative, payments equal their allocations, paid invoices
                       have nothing open, PO and SO statuses agree with their lines, dates are well formed

Known kernel bugs (KNOWN_BUGS) are kept out of the random generator by default so a fuzz run finds new problems;
--include-known puts them back. tests/test_erp_properties.py has a minimal reproduction of each.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (os.path.join(ROOT, 'erp'), os.path.join(ROOT, 'tasks', 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bberp import api, reports, sim  # noqa: E402
from bberp.core import Erp, add_days  # noqa: E402

CACHE = os.path.join(ROOT, '.cache', 'erp_fuzz')
FULL_EVERY = 20          # every 20th call is checked against every table, not only the ones it wrote to
TASKS = os.path.join(ROOT, 'tasks', 'process')
TIES = ('ap', 'grni', 'inventory', 'ar', 'unapplied_cash', 'wip')

# Known bb-erp problems. The generator avoids the triggering calls unless --include-known is given.
KNOWN_BUGS = {
    'gl_reverse_subledger_entry': (
        'POST /journal-entries/{id}/reverse reverses any posted entry, including ones posted by a subledger document '
        '(an AP invoice, receipt, payment, shipment, cash receipt, work order). The document keeps its status and '
        'its subledger amount, so the control account stops tying to its subledger (ledger_ties fails) and the '
        'document can no longer be voided through its own lifecycle.'),
    'commit_failure_leaves_transaction_open': (
        'Erp.tx() does not roll back when COMMIT itself raises (SQLITE_BUSY, I/O error): the transaction stays open '
        'on the shared connection, the error audit row cannot be written, and every later request fails with 500 '
        '("cannot start a transaction within a transaction") while the uncommitted write is visible to that '
        'connection only.'),
    'so_release_forgets_partial_shipment': (
        'POST /sales-orders/{id}/release sets a partially shipped order that was put on hold back to "released", '
        'although some of it has shipped; the status stays wrong until the next shipment recomputes it, so any '
        'projection or report keyed on sales-order status misreads the order.'),
    'unvalidated_dates': (
        'Several date inputs are stored without being parsed: a manual journal entry dated "2026-10-99" is created and '
        'posted (its period is taken from the first seven characters), and a payment run accepts pay_date '
        '"next friday". Date filters compare strings, so such rows fall outside or inside as-of reports by accident.'),
    'approved_run_dead_end': (
        'An approved payment run has no way back: it can only be released, but release is refused for reasons that can '
        'arise after approval (an invoice in it voided or put on hold, the vendor made inactive, the vendor\'s bank '
        'account changed). There is no return or cancel for an approved run, so it stays approved with proposed '
        'payments forever, and its other invoices can never be paid (adding them to another run is refused as '
        'already_proposed). Voiding an invoice that sits in a live run is accepted.'),
    'clock_advance_not_atomic': (
        'sim.advance commits the new business date before running the day\'s counterparties, one transaction per '
        'action. If an action fails with anything other than ErpError (a database error), advance raises with the day '
        'half done, and a retry to the same date is a no-op: the remaining actions of that day (a bank clearing, a '
        'vendor shipment, an approval) never happen.'),
    'malformed_input_500': (
        'Type-malformed input (a non-integer line number in the path, a non-numeric qty or amount, lines that are '
        'not a list of objects, a non-integer limit) raises inside the handler and is answered 500 server_error '
        'instead of a 4xx problem. The write is rolled back, so no state is corrupted.'),
}


# ============================================================================================ scenarios

def ensure_scenario(task: str, seed: int) -> str:
    """Generate the task's scenario with its own gen.py (no oracle run, no reference) into a private cache."""
    out = os.path.join(CACHE, task, f'seed-{seed}')
    if os.path.exists(os.path.join(out, 'meta.json')):
        return out
    tdir = os.path.join(TASKS, task)
    if not os.path.isfile(os.path.join(tdir, 'gen.py')):
        raise SystemExit(f'unknown process task {task!r}')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=f'seed-{seed}-', dir=os.path.dirname(out))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(ROOT, 'erp'), os.path.join(ROOT, 'tasks', 'lib')]))
    subprocess.run([sys.executable, 'gen.py', '--seed', str(seed), '--out', tmp], cwd=tdir, env=env, check=True,
                   stdout=subprocess.DEVNULL)
    try:
        os.replace(tmp, out)
    except OSError:                       # another process won the race
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def scratch_dir(prefix: str = 'erp-fuzz-') -> str:
    """A temporary directory, in memory (/dev/shm) when available: the kernel fsyncs every commit."""
    shm = '/dev/shm'
    base = shm if os.path.isdir(shm) and os.access(shm, os.W_OK) else None
    return tempfile.mkdtemp(prefix=prefix, dir=base)


def read_json(path: str):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def copy_db(src: str, dst: str) -> None:
    for suffix in ('-journal', '-wal', '-shm'):
        if os.path.exists(dst + suffix):
            os.remove(dst + suffix)
    shutil.copyfile(src, dst)


# ============================================================================================ calls

@dataclass
class Call:
    user: str | None
    method: str
    path: str
    body: dict | list | None = None
    kind: str = ''
    expect: str = 'any'          # ok | refuse | any
    raw: bytes | None = None     # a body sent verbatim (malformed input)
    idem: str | None = None
    token: str | None = None     # overrides the user's token (bad-token probes)
    replay_of: int | None = None  # index of the call this replays with the same Idempotency-Key

    def to_json(self) -> dict:
        d = {'user': self.user, 'method': self.method, 'path': self.path, 'kind': self.kind, 'expect': self.expect}
        if self.body is not None:
            d['body'] = self.body
        if self.raw is not None:
            d['raw'] = base64.b64encode(self.raw).decode()
        for k in ('idem', 'token', 'replay_of'):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        return d

    @classmethod
    def from_json(cls, d: dict) -> 'Call':
        return cls(user=d.get('user'), method=d['method'], path=d['path'], body=d.get('body'), kind=d.get('kind', ''),
                   expect=d.get('expect', 'any'), raw=base64.b64decode(d['raw']) if d.get('raw') else None,
                   idem=d.get('idem'), token=d.get('token'), replay_of=d.get('replay_of'))


@dataclass
class Advance:
    to: str
    kind: str = 'clock.advance'

    def to_json(self) -> dict:
        return {'advance': self.to}


def step_from_json(d: dict):
    return Advance(d['advance']) if 'advance' in d else Call.from_json(d)


# ============================================================================================ invariants

# table -> (key expression, initial statuses of new rows, legal transitions)
LIFECYCLE = {
    'requisitions': ('id', {'draft', 'submitted'}, {
        'draft': {'submitted', 'cancelled'}, 'submitted': {'approved', 'rejected', 'returned', 'cancelled'},
        'returned': {'submitted', 'cancelled'}, 'approved': {'converted', 'cancelled'}, 'converted': {'approved'}}),
    'approval_requests': ('id', {'pending'}, {'pending': {'approved', 'rejected', 'returned', 'forwarded', 'cancelled'}}),
    'purchase_orders': ('id', {'draft', 'sent'}, {
        'draft': {'sent', 'cancelled'}, 'sent': {'partially_received', 'received', 'cancelled'},
        'partially_received': {'received', 'sent'}, 'received': {'partially_received', 'sent'}}),
    'po_lines': ("po_id || '/' || line", {'open'}, {'open': {'closed', 'cancelled'}}),
    'receipts': ('id', {'posted'}, {'posted': {'reversed'}}),
    'ap_invoices': ('id', {'entered'}, {
        'entered': {'on_hold', 'matched', 'rejected'}, 'on_hold': {'entered', 'matched', 'rejected', 'voided'},
        'matched': {'approved', 'on_hold', 'voided'}, 'approved': {'paid', 'on_hold', 'voided'}}),
    'payment_runs': ('id', {'draft'}, {'draft': {'submitted'}, 'submitted': {'approved', 'draft'},
                                       'approved': {'released'}}),
    'payments': ('id', {'proposed'}, {'proposed': {'released'}, 'released': {'cleared'}}),
    'journal_entries': ('id', {'draft', 'posted'}, {
        'draft': {'submitted', 'posted'}, 'submitted': {'approved', 'returned', 'posted'}, 'returned': {'submitted'},
        'approved': {'posted'}, 'posted': {'reversed'}}),
    'periods': ('period', {'open'}, {'open': {'closed'}, 'closed': {'open'}}),
    'vendor_bank_accounts': ('id', {'pending'}, {'pending': {'verified', 'rejected'}, 'verified': {'retired'}}),
    'sales_orders': ('id', {'released', 'on_hold'}, {
        'on_hold': {'released'}, 'released': {'on_hold', 'partially_shipped', 'shipped'},
        'partially_shipped': {'on_hold', 'shipped'}}),
    'shipments': ('id', {'shipped'}, {'shipped': {'invoiced'}}),
    'ar_invoices': ('id', {'open'}, {'open': {'paid'}}),
    'cash_receipts': ('id', {'unapplied'}, {'unapplied': {'partially_applied', 'applied'},
                                            'partially_applied': {'applied'}}),
    'work_orders': ('id', {'planned'}, {
        'planned': {'released', 'cancelled'}, 'released': {'in_progress', 'completed', 'closed', 'cancelled'},
        'in_progress': {'completed', 'closed'}, 'completed': {'closed'}}),
    'mrp_suggestions': ('id', {'open'}, {'open': {'released', 'superseded'}}),
    'vendor_requests': ('id', {'open'}, {'open': {'accepted', 'declined'}}),
    'escalations': ('id', {'open'}, {'open': {'answered'}}),
}
# rows that may disappear: unreleased proposed payments (a run's draft contents) and their allocations
DELETABLE = {'payments': "status = 'proposed'"}

# (name, table, columns that never change, snapshot filter): rows matching the filter keep these columns forever
IMMUTABLE = [
    ('posted journal entries', 'journal_entries',
     'id, entry_date, period, source, source_ref, memo, preparer, approver, posted_on, created_on, reverses',
     "status IN ('posted', 'reversed')"),
    ('lines of posted journal entries', 'journal_lines', '*',
     "je_id IN (SELECT id FROM {s}.journal_entries WHERE status IN ('posted', 'reversed'))"),
    ('receipts', 'receipts', 'id, po_id, receipt_date, received_by, packing_slip', '1'),
    ('receipt lines', 'receipt_lines', '*', '1'),
    ('posted AP invoices', 'ap_invoices', 'id, vendor, invoice_no, invoice_date, po_id, total_cents, posted_je, period',
     'posted_je IS NOT NULL'),
    ('lines of posted AP invoices', 'ap_invoice_lines', 'inv_id, line, kind, po_line, sku, qty, unit_price, amount_cents, '
     'account, department', 'inv_id IN (SELECT id FROM {s}.ap_invoices WHERE posted_je IS NOT NULL)'),
    ('released payments', 'payments', 'id, run_id, vendor, vendor_account, pay_date, amount_cents, discount_cents, '
     'posted_je', "status IN ('released', 'cleared')"),
    ('allocations of released payments', 'payment_allocations', '*',
     "payment_id IN (SELECT id FROM {s}.payments WHERE status IN ('released', 'cleared'))"),
    ('shipments', 'shipments', 'id, so_id, ship_date, warehouse, shipped_by', '1'),
    ('shipment lines', 'shipment_lines', '*', '1'),
    ('AR invoices', 'ar_invoices', 'id, customer, invoice_date, period, so_id, shipment_id, total_cents, posted_je', '1'),
    ('AR invoice lines', 'ar_invoice_lines', '*', '1'),
    ('cash receipts', 'cash_receipts', 'id, customer, receipt_date, amount_cents, bank_account, posted_je', '1'),
    ('stock moves', 'inventory_txns', '*', '1'),
    ('work-order issues', 'wo_issues', '*', '1'),
    ('bank statement lines', 'bank_statement_lines', '*', '1'),
    ('holds', 'holds', 'id, doc_type, doc_id, line, reason, placed_by, placed_on', '1'),
    ('attachments', 'attachments', '*', '1'),
]

# consistency checks on the live database: name -> SQL returning offending keys
CONSISTENCY = {
    'stock never negative': "SELECT sku || '@' || location || '/' || COALESCE(lot, '') FROM {s}.inventory_txns "
                            "GROUP BY sku, location, lot HAVING SUM(qty) < -0.00001",
    'posted entry balances': "SELECT e.id FROM {s}.journal_entries e JOIN {s}.journal_lines l ON l.je_id = e.id "
                             "WHERE e.status IN ('posted', 'reversed') GROUP BY e.id "
                             "HAVING SUM(l.debit_cents) != SUM(l.credit_cents)",
    'entry period matches its date': "SELECT id FROM {s}.journal_entries WHERE period != substr(entry_date, 1, 7)",
    'payment equals its allocations': (
        "SELECT p.id FROM {s}.payments p LEFT JOIN {s}.payment_allocations a ON a.payment_id = p.id GROUP BY p.id "
        "HAVING p.amount_cents != COALESCE(SUM(a.amount_cents), 0) "
        "OR p.discount_cents != COALESCE(SUM(a.discount_cents), 0)"),
    'paid AP invoice has nothing open': (
        "SELECT i.id FROM {s}.ap_invoices i WHERE i.status = 'paid' AND i.total_cents > (SELECT "
        "COALESCE(SUM(a.amount_cents + a.discount_cents), 0) FROM {s}.payment_allocations a JOIN {s}.payments p "
        "ON p.id = a.payment_id WHERE a.inv_id = i.id AND p.status IN ('released', 'cleared'))"),
    'AP invoice paid in full is marked paid': (
        "SELECT i.id FROM {s}.ap_invoices i WHERE i.status IN ('matched', 'approved') AND i.total_cents > 0 AND "
        "i.total_cents <= (SELECT COALESCE(SUM(a.amount_cents + a.discount_cents), 0) FROM {s}.payment_allocations a "
        "JOIN {s}.payments p ON p.id = a.payment_id WHERE a.inv_id = i.id AND p.status IN ('released', 'cleared'))"),
    'AP invoice never overpaid': (
        "SELECT i.id FROM {s}.ap_invoices i WHERE i.total_cents >= 0 AND i.total_cents < (SELECT "
        "COALESCE(SUM(a.amount_cents + a.discount_cents), 0) FROM {s}.payment_allocations a JOIN {s}.payments p "
        "ON p.id = a.payment_id WHERE a.inv_id = i.id AND p.status IN ('released', 'cleared'))"),
    'AR invoice never over-applied': (
        "SELECT i.id FROM {s}.ar_invoices i WHERE i.total_cents < (SELECT COALESCE(SUM(amount_cents + discount_cents), "
        "0) FROM {s}.cash_applications a WHERE a.inv_id = i.id)"),
    'cash receipt never over-applied': (
        "SELECT r.id FROM {s}.cash_receipts r WHERE r.amount_cents < (SELECT COALESCE(SUM(amount_cents), 0) "
        "FROM {s}.cash_applications a WHERE a.receipt_id = r.id)"),
    'PO status agrees with its lines': (
        "SELECT p.id FROM {s}.purchase_orders p WHERE p.status IN ('sent', 'partially_received', 'received') AND "
        "p.status != (SELECT CASE WHEN COUNT(*) = 0 THEN 'cancelled' "
        "WHEN SUM(CASE WHEN l.status = 'closed' OR l.qty_received >= l.qty - 1e-9 THEN 1 ELSE 0 END) = COUNT(*) "
        "THEN 'received' WHEN SUM(CASE WHEN l.qty_received > 0 THEN 1 ELSE 0 END) > 0 THEN 'partially_received' "
        "ELSE 'sent' END FROM {s}.po_lines l WHERE l.po_id = p.id AND l.status != 'cancelled')"),
    'PO line quantities are non-negative': (
        "SELECT po_id || '/' || line FROM {s}.po_lines WHERE qty_received < -1e-9 OR qty_refused < -1e-9 "
        "OR qty_billed < -1e-9"),
    'SO status agrees with its lines': (
        "SELECT s.id FROM {s}.sales_orders s WHERE (s.status = 'released' AND EXISTS (SELECT 1 FROM {s}.so_lines l "
        "WHERE l.so_id = s.id AND l.qty_shipped > 0)) OR (s.status = 'partially_shipped' AND NOT EXISTS (SELECT 1 "
        "FROM {s}.so_lines l WHERE l.so_id = s.id AND l.qty_shipped > 0))"),
    'work order not over-completed': (
        "SELECT id FROM {s}.work_orders WHERE qty_completed + qty_scrapped > qty + 1e-9"),
    'converted requisition has every line on a PO': (
        "SELECT r.id FROM {s}.requisitions r WHERE r.status = 'converted' AND EXISTS (SELECT 1 FROM "
        "{s}.requisition_lines l WHERE l.req_id = r.id AND l.po_id IS NULL)"),
}
DATE_COLUMNS = {
    'journal_entries': ['entry_date', 'auto_reverse_on'], 'ap_invoices': ['invoice_date', 'due_date', 'discount_date'],
    'ar_invoices': ['invoice_date', 'due_date'], 'payment_runs': ['pay_date'], 'payments': ['pay_date'],
    'work_orders': ['start_date', 'due_date'], 'po_lines': ['need_date', 'confirmed_date'],
    'so_lines': ['promise_date'], 'requisition_lines': ['need_by'], 'vendor_requests': ['wanted_date'],
    'lots': ['expiry'], 'shipments': ['ship_date'], 'cash_receipts': ['receipt_date'],
}
for _t, _cols in DATE_COLUMNS.items():
    CONSISTENCY[f'{_t} dates are YYYY-MM-DD'] = ' UNION '.join(
        f"SELECT '{c}=' || {c} FROM {{s}}.{_t} WHERE {c} IS NOT NULL AND (length({c}) != 10 OR date({c}) IS NOT {c})"
        for c in _cols)


CONSISTENCY_TABLES = {name: set(re.findall(r'\{s\}\.(\w+)', sql)) for name, sql in CONSISTENCY.items()}
LEDGER_TABLES = {'journal_entries', 'journal_lines', 'inventory_txns', 'ap_invoices', 'ap_invoice_lines', 'payments',
                 'payment_allocations', 'receipts', 'receipt_lines', 'ar_invoices', 'cash_receipts', 'cash_applications',
                 'posting_rules', 'accounts'}
WRITE_RX = re.compile(r'\s*(?:INSERT(?:\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|UPDATE(?:\s+OR\s+\w+)?|DELETE\s+FROM)\s+'
                      r'["`\[]?(\w+)', re.I)


@dataclass
class Violation:
    invariant: str
    detail: str
    step: int = -1
    call: dict | None = None
    status: int | None = None
    response: str | None = None

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class Checker:
    """Holds a snapshot of the database before each call (in `chk`'s main schema, filled with the SQLite backup API)
    and compares the live file (attached read-only as `live`) with it afterwards."""

    def __init__(self, erp: Erp, snap_path: str):
        self.erp = erp
        self.chk = sqlite3.connect(snap_path, uri=True, isolation_level=None)
        self.chk.execute('PRAGMA synchronous = OFF')      # a scratch copy: no fsync
        self.chk.execute('PRAGMA journal_mode = MEMORY')
        self.chk.execute(f"ATTACH DATABASE 'file:{erp.path}?mode=ro' AS live")
        self.tables = [r[0] for r in erp.db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()]
        self.audit_hash = hashlib.sha256()
        self.audit_last = 0
        self._hash_new_audit_rows()
        self.prefix = (self.audit_last, self.audit_hash.hexdigest())
        self.ties = self._ties()
        self.balanced = reports.trial_balance(erp)['balanced']
        self.snapshot()
        self.known = {name: self._offenders('live', sql) for name, sql in CONSISTENCY.items()}
        self.touched: set[str] = set()
        erp.db.set_trace_callback(self._trace)

    def close(self) -> None:
        self.chk.close()

    # helpers ----------------------------------------------------------------------------------------------
    def q(self, sql: str, *args) -> list:
        return self.chk.execute(sql, args).fetchall()

    def snapshot(self) -> None:
        self.erp.db.backup(self.chk)
        self.snap_audit_max = self.q('SELECT COALESCE(MAX(id), 0) FROM main.audit_events')[0][0]

    def _ties(self) -> dict:
        return {k: v['difference_cents'] for k, v in reports.control_ties(self.erp)['controls'].items()}

    def _offenders(self, schema: str, sql: str) -> set:
        return {r[0] for r in self.q(sql.format(s=schema))}

    def _hash_new_audit_rows(self) -> None:
        for row in self.erp.db.execute('SELECT * FROM audit_events WHERE id > ? ORDER BY id', (self.audit_last,)):
            self.audit_hash.update(json.dumps(list(row), default=str).encode())
            self.audit_last = row[0]

    def audit_prefix_ok(self) -> bool:
        """Recompute the hash of the audit rows up to the checkpoint and compare it with the rolling hash."""
        n, want = self.prefix
        h = hashlib.sha256()
        for row in self.erp.db.execute('SELECT * FROM audit_events WHERE id <= ? ORDER BY id', (n,)):
            h.update(json.dumps(list(row), default=str).encode())
        return h.hexdigest() == want

    def table_diff(self, table: str) -> tuple[int, int]:
        """(rows only in the snapshot, rows only in the live file)."""
        gone = self.q(f'SELECT COUNT(*) FROM (SELECT * FROM main."{table}" EXCEPT SELECT * FROM live."{table}")')[0][0]
        new = self.q(f'SELECT COUNT(*) FROM (SELECT * FROM live."{table}" EXCEPT SELECT * FROM main."{table}")')[0][0]
        if not gone and not new:
            a = self.q(f'SELECT COUNT(*) FROM main."{table}"')[0][0]
            b = self.q(f'SELECT COUNT(*) FROM live."{table}"')[0][0]
            if a != b:                                   # duplicate rows that EXCEPT folds together
                return max(a - b, 0), max(b - a, 0)
        return gone, new

    def changed_tables(self, ignore: tuple = (), only: set | None = None) -> list[str]:
        out = []
        for t in self.tables:
            if t in ignore or t == 'audit_events' or (only is not None and t not in only):
                continue
            if t == 'sqlite_sequence':
                a = self.q("SELECT * FROM main.sqlite_sequence WHERE name != 'audit_events' ORDER BY name")
                b = self.q("SELECT * FROM live.sqlite_sequence WHERE name != 'audit_events' ORDER BY name")
                if a != b:
                    out.append(t)
                continue
            gone, new = self.table_diff(t)
            if gone or new:
                out.append(f'{t} (-{gone} +{new})')
        return out

    def _trace(self, sql: str) -> None:
        m = WRITE_RX.match(sql)
        if m:
            self.touched.add(m.group(1))

    # the checks -------------------------------------------------------------------------------------------
    def after(self, call: Call | None, status: int | None, body: bytes | None, first: tuple | None = None,
              full: bool = False) -> list[Violation]:
        """Check the live database after one request (call is None after a clock advance). Table-level checks run on
        the tables the request wrote to (seen through the connection's trace callback, so rolled-back writes count);
        with `full`, on every table, which also cross-checks the trace."""
        v: list[Violation] = []
        touched = set(self.touched) | ({'sqlite_sequence'} if self.touched else set())
        self.touched = set()
        scope = None if full else touched

        def bad(name, detail):
            v.append(Violation(name, detail))

        def diff():
            changed = self.changed_tables(only=scope)
            if full:
                stray = [c.split(' ')[0] for c in changed if c.split(' ')[0] not in touched]
                if stray:
                    bad('checker', f'tables changed without a traced write: {stray}')
            return changed

        new_audit = self.q('SELECT id, channel, path, outcome, error_code, request FROM live.audit_events '
                           'WHERE id > ? ORDER BY id', self.snap_audit_max)
        if call is not None:
            if status >= 500:
                trace = ''
                if new_audit and new_audit[-1][5]:
                    try:
                        trace = json.loads(new_audit[-1][5]).get('trace', '')[-600:]
                    except (ValueError, AttributeError):
                        pass
                bad('no_5xx', f'{status} for {call.method} {call.path}; {trace}')
            if call.expect == 'refuse' and status < 400:
                bad('expected_refusal', f'{call.kind}: {call.method} {call.path} was accepted ({status})')
            api_rows = [r for r in new_audit if r[1] == 'api']
            want = 'ok' if status < 400 else ('refused' if status < 500 else 'error')
            if call.path == '/openapi.json':             # the API description is public and not audited
                pass
            elif len(new_audit) != 1 or len(api_rows) != 1:
                bad('one_audit_row', f'{len(new_audit)} audit rows ({len(api_rows)} api) for one request')
            elif api_rows[0][3] != want:
                bad('one_audit_row', f'audit outcome {api_rows[0][3]!r} for status {status}')
            if status >= 400:
                changed = diff()
                if changed:
                    bad('refused_unchanged', f'{status} but changed: {", ".join(changed)}')
            elif call.replay_of is not None and first is not None and first[0] < 400:
                changed = diff()
                if changed:
                    bad('replay_unchanged', f'idempotent replay changed: {", ".join(changed)}')
                if (status, body) != first:
                    bad('replay_unchanged', f'replay answered {status}, first answer was {first[0]}; bodies differ: '
                                            f'{body != first[1]}')
            elif call.method == 'GET':
                changed = [c for c in diff() if not c.startswith('message_reads ')]
                if changed:
                    bad('reads_unchanged', f'GET {call.path} changed: {", ".join(changed)}')
            elif full:
                diff()
        elif full:
            diff()
        # the audit log is append-only
        gone = self.q('SELECT COUNT(*) FROM (SELECT * FROM main.audit_events EXCEPT SELECT * FROM live.audit_events)')[0][0]
        if gone:
            bad('audit_append_only', f'{gone} earlier audit rows changed or removed')
        self._hash_new_audit_rows()

        def hit(tables) -> bool:
            return scope is None or bool(scope & set(tables))
        # ledger
        if hit(LEDGER_TABLES):
            tb = reports.trial_balance(self.erp)['balanced']
            if self.balanced and not tb:
                bad('trial_balance', 'the trial balance no longer balances')
            self.balanced = tb
            ties = self._ties()
            for k, d in ties.items():
                if d != self.ties.get(k, 0):
                    bad('ledger_ties', f'{k}: ledger minus subledger moved from {self.ties.get(k, 0)} to {d} cents')
            self.ties = ties
        # documents are kept; posted content is immutable; lifecycles are legal
        for table, (key, initial, moves) in LIFECYCLE.items():
            if not hit([table]):
                continue
            keep = DELETABLE.get(table)
            lost = self.q(f'SELECT {key} FROM main.{table}' + (f' WHERE NOT ({keep})' if keep else '') +
                          f' EXCEPT SELECT {key} FROM live.{table}')
            if lost:
                bad('documents_kept', f'{table}: {len(lost)} rows deleted, e.g. {lost[0][0]}')
            for k, a, b in self.q(f'SELECT s.k, s.status, l.status FROM (SELECT {key} AS k, status FROM main.{table}) s '
                                  f'JOIN (SELECT {key} AS k, status FROM live.{table}) l ON l.k = s.k '
                                  'WHERE s.status != l.status'):
                if b not in moves.get(a, ()):
                    bad('lifecycle', f'{table} {k}: {a} -> {b}')
            for k, b in self.q(f'SELECT k, status FROM (SELECT {key} AS k, status FROM live.{table}) WHERE k NOT IN '
                               f'(SELECT {key} FROM main.{table})'):
                if b not in initial:
                    bad('lifecycle', f'{table} {k}: new document starts {b}')
        for name, table, cols, where in IMMUTABLE:
            if not hit([table]):
                continue
            n = self.q(f'SELECT COUNT(*) FROM (SELECT {cols} FROM main.{table} WHERE {where.format(s="main")} '
                       f'EXCEPT SELECT {cols} FROM live.{table})')[0][0]
            if n:
                bad('posted_immutable', f'{name}: {n} rows changed or removed')
        for name, sql in CONSISTENCY.items():
            if not hit(CONSISTENCY_TABLES[name]):
                continue
            now = self._offenders('live', sql)
            fresh = sorted(now - self.known[name])
            if fresh:
                bad('consistency', f'{name}: {", ".join(map(str, fresh[:4]))}')
            self.known[name] = now
        return v


# ============================================================================================ one fuzzed company

class Harness:
    """A working copy of a scenario, the tokens of every staff user, and the checker."""

    def __init__(self, scenario: str, work: str, check: bool = True):
        os.makedirs(work, exist_ok=True)
        self.work = work
        self.db_path = os.path.join(work, 'live.db')
        copy_db(os.path.join(scenario, 'scenario.db'), self.db_path)
        world = read_json(os.path.join(scenario, 'world.json'))
        self.meta = read_json(os.path.join(scenario, 'meta.json'))
        self.erp = Erp(self.db_path, world=world)
        self.tokens = {r['user_id']: r['secret'] for r in self.erp.all('SELECT user_id, secret FROM tokens ORDER BY id')}
        snap = os.path.join(work, 'snap.db')
        if os.path.exists(snap):
            os.remove(snap)
        self.checker = Checker(self.erp, snap) if check else None
        self.responses = hashlib.sha256()
        self.log: list[dict] = []
        self.results: list[tuple] = []
        self.violations: list[Violation] = []

    def close(self) -> None:
        if self.checker:
            self.checker.close()
        self.erp.close()

    def request(self, c: Call) -> tuple[int, bytes]:
        headers = {}
        tok = c.token if c.token is not None else self.tokens.get(c.user)
        if tok:
            headers['Authorization'] = f'Bearer {tok}'
        if c.idem:
            headers['Idempotency-Key'] = c.idem
        body = c.raw if c.raw is not None else (json.dumps(c.body).encode() if c.body is not None else None)
        if body is not None:
            headers['Content-Type'] = 'application/json'
        status, _hdr, out = api.handle(self.erp, c.method, c.path, headers, body)
        return status, out

    def step(self, s) -> tuple[int | None, object]:
        n = len(self.log)
        self.log.append(s.to_json())
        if self.checker:
            self.checker.snapshot()
        if isinstance(s, Advance):
            try:
                sim.advance(self.erp, s.to)
                status, out = None, b''
            except Exception as e:                       # a simulator crash is a kernel failure too
                status, out = 599, f'{type(e).__name__}: {e}'.encode()
            first = None
            call = None
            if status:
                self.violations.append(Violation('no_5xx', f'clock advance crashed: {out.decode()}', n, s.to_json()))
        else:
            call = s
            try:
                status, out = self.request(s)
            except Exception as e:                       # handle() must never raise
                status, out = 599, f'unhandled {type(e).__name__}: {e}'.encode()
            first = self.results[s.replay_of] if s.replay_of is not None and s.replay_of < len(self.results) else None
        self.results.append((status, out))
        self.responses.update(json.dumps([status, out.decode('utf-8', 'replace')]).encode())
        if self.checker:
            for v in self.checker.after(call, status if call else None, out, first, full=n % FULL_EVERY == 0):
                v.step, v.call, v.status = n, s.to_json(), status
                v.response = out[:400].decode('utf-8', 'replace') if isinstance(out, bytes) else None
                self.violations.append(v)
        data = None
        if status and status < 400 and out[:1] == b'{':
            try:
                data = json.loads(out).get('data')
            except ValueError:
                pass
        return status, data

    def export(self) -> dict:
        """Canonical export: every table's rows (audit wall_time blanked, as grading ignores it) and the responses."""
        return export_db(self.db_path, self.erp.db) | {'responses': self.responses.hexdigest()}


def export_db(path: str, conn: sqlite3.Connection | None = None) -> dict:
    own = conn is None
    conn = conn or sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        h = hashlib.sha256()
        per = {}
        for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall():
            th = hashlib.sha256()
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")').fetchall()]
            for row in conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid'):
                row = list(row)
                if t == 'audit_events':
                    row[cols.index('wall_time')] = None
                th.update(json.dumps(row, default=lambda b: b.hex() if isinstance(b, bytes) else str(b)).encode())
            per[t] = th.hexdigest()
            h.update(f'{t}:{per[t]}'.encode())
        return {'db': h.hexdigest(), 'tables': per}
    finally:
        if own:
            conn.close()


# ============================================================================================ the generator

class Gen:
    """Builds the next call from the current state. Valid calls are drawn from what exists (open documents, real
    vendors and items); invalid ones break exactly one rule. Deterministic given the RNG."""

    def __init__(self, erp: Erp, rng: random.Random, tag: str, malformed: bool = False, include_known: bool = False,
                 max_days: int = 2):
        self.erp, self.rng, self.tag = erp, rng, tag
        self.malformed, self.include_known = malformed, include_known
        self.days_left = max_days
        self.n = 0
        self.last_write: tuple[int, Call] | None = None
        self.perm_users: dict[str, list[str]] = {}
        staff = {r['user_id'] for r in erp.all("SELECT t.user_id FROM tokens t JOIN users u ON u.id = t.user_id "
                                               "WHERE u.kind = 'staff' AND u.active = 1")}
        self.staff = sorted(staff)
        self.valid = [(w, f) for w, f in VALID]
        self.invalid = [(w, f) for w, f in INVALID]

    # state helpers --------------------------------------------------------------------------------------
    def all(self, sql, *a):
        return self.erp.all(sql, *a)

    def one(self, sql, *a):
        return self.erp.one(sql, *a)

    def val(self, sql, *a):
        return self.erp.val(sql, *a)

    def pick(self, seq):
        seq = list(seq)
        return self.rng.choice(seq) if seq else None

    def who(self, action: str, exclude=()) -> str | None:
        if action not in self.perm_users:
            rows = self.all('SELECT DISTINCT ur.user_id FROM user_roles ur JOIN role_permissions rp ON rp.role = ur.role '
                            "WHERE rp.action IN (?, '*') ORDER BY ur.user_id", action)
            self.perm_users[action] = [r['user_id'] for r in rows if r['user_id'] in self.staff]
        return self.pick(u for u in self.perm_users[action] if u not in exclude)

    def lacking(self, action: str) -> str | None:
        self.who(action)
        return self.pick(u for u in self.staff if u not in self.perm_users[action])

    @property
    def today(self) -> str:
        return self.erp.today

    def period_open(self, day: str | None = None) -> bool:
        return self.val('SELECT status FROM periods WHERE period = ?', (day or self.today)[:7]) == 'open'

    def post_expect(self) -> str:
        """Posting today is refused when today's period is closed."""
        return 'any' if self.period_open() else 'refuse'

    def uid(self, prefix: str) -> str:
        self.n += 1
        return f'{prefix}-{self.tag}-{self.n}'

    def money(self, lo=1, hi=5000) -> float:
        return round(self.rng.uniform(lo, hi), 2)

    # the next step --------------------------------------------------------------------------------------
    def next(self, index: int):
        r = self.rng.random()
        if self.days_left and r < 0.012:
            self.days_left -= 1
            return Advance(add_days(self.today, 1))
        if self.last_write and r < 0.04:
            i, c = self.last_write
            return Call(c.user, c.method, c.path, c.body, kind='idempotent.replay', idem=c.idem, replay_of=i)
        table = self.invalid if r < 0.32 else self.valid
        for _ in range(30):
            w = [x[0] for x in table]
            fn = self.rng.choices([x[1] for x in table], weights=w)[0]
            c = fn(self)
            if c and (c.user or c.token is not None):
                break
        else:
            c = read_call(self)
        if self.malformed and self.rng.random() < 0.15 and c.method != 'GET':
            c = malform(self, c)
        if c.method in api.WRITE_METHODS and not c.kind.startswith('x.') and self.rng.random() < 0.3:
            c.idem = self.uid('key')
            self.last_write = (index, c)
        return c


# ---- valid calls ---------------------------------------------------------------------------------------------

def read_call(g: Gen) -> Call:
    paths = ['/whoami', '/users', '/accounts', '/periods', '/vendors', '/items', '/customers', '/requisitions',
             '/purchase-orders', '/receipts', '/ap-invoices', '/payment-runs', '/payments', '/journal-entries?limit=50',
             '/sales-orders', '/work-orders', '/inventory/on-hand', '/approvals', '/inbox', '/outbox', '/audit',
             '/reports/trial-balance', '/reports/control-ties', '/reports/ap-aging', '/reports/grni',
             '/reports/cash-position', '/reports/budget-vs-actual', '/vendor-bank-accounts', '/openapi.json',
             '/mrp/suggestions', '/reports/open-purchase-orders', '/reports/sales-margin']
    for table, prefix in (('ap_invoices', '/ap-invoices'), ('purchase_orders', '/purchase-orders'),
                          ('receipts', '/receipts'), ('journal_entries', '/journal-entries'),
                          ('payment_runs', '/payment-runs'), ('work_orders', '/work-orders')):
        oid = g.val(f'SELECT id FROM {table} ORDER BY id DESC LIMIT 1 OFFSET ?', g.rng.randrange(5))
        if oid:
            paths.append(f'{prefix}/{oid}')
    msg = g.one("SELECT id FROM messages WHERE direction = 'in' AND visible_on <= ? ORDER BY id DESC LIMIT 1", g.today)
    user = g.pick(g.staff)
    if msg and g.rng.random() < 0.2:
        return Call(g.who('box.ap') or user, 'GET', f'/inbox/{msg["id"]}', kind='read.message')
    return Call(user, 'GET', g.pick(paths), kind='read')


def v_req_create(g: Gen):
    u = g.pick(g.staff)
    dept = g.val('SELECT department FROM users WHERE id = ?', u) or g.pick(r['code'] for r in g.all('SELECT code FROM departments'))
    lines = []
    for _ in range(g.rng.randint(1, 2)):
        pa = g.pick(g.all('SELECT vendor, sku FROM price_agreements WHERE valid_from <= ? AND valid_to >= ? ORDER BY id',
                          g.today, g.today))
        if pa is None:
            return None
        lines.append({'sku': pa['sku'], 'qty': g.rng.choice([5, 20, 50, 200, 1000]), 'vendor': pa['vendor'],
                      'need_by': add_days(g.today, g.rng.randint(3, 20))})
    return Call(u, 'POST', '/requisitions', {'department': dept, 'lines': lines, 'justification': 'fuzz',
                                             'submit': g.rng.random() < 0.7}, 'req.create', 'ok')


def v_req_submit(g: Gen):
    r = g.pick(g.all("SELECT id, requester FROM requisitions WHERE status IN ('draft', 'returned') ORDER BY id"))
    return r and Call(r['requester'], 'POST', f'/requisitions/{r["id"]}/submit', None, 'req.submit', 'ok')


def _pending_req(g: Gen):
    return g.pick(g.all("SELECT r.id, r.requester, r.total_cents, a.approver FROM requisitions r JOIN approval_requests a "
                        "ON a.doc_id = r.id AND a.doc_type = 'requisition' AND a.status = 'pending' "
                        "WHERE r.status = 'submitted' ORDER BY r.id"))


def v_req_decide(g: Gen):
    r = _pending_req(g)
    if r is None or r['approver'] not in g.staff:
        return None
    verb = g.rng.choice(['approve', 'approve', 'reject', 'return', 'forward'])
    if verb == 'approve':
        lim = g.val("SELECT limit_cents FROM approval_limits WHERE user_id = ? AND doc_type = 'requisition'",
                    r['approver']) or 0
        ok = r['total_cents'] <= lim and r['requester'] != r['approver']
        return Call(r['approver'], 'POST', f'/requisitions/{r["id"]}/approve', {'note': 'ok'}, 'req.approve',
                    'ok' if ok else 'refuse')
    if verb == 'forward':
        to = g.who('req.approve', exclude=(r['approver'],))
        return to and Call(r['approver'], 'POST', f'/requisitions/{r["id"]}/forward', {'to': to, 'reason': 'over_limit'},
                           'req.forward', 'ok')
    return Call(r['approver'], 'POST', f'/requisitions/{r["id"]}/{verb}', {'reason': 'fuzz'}, f'req.{verb}', 'ok')


def v_req_cancel(g: Gen):
    r = g.pick(g.all("SELECT r.id, r.requester FROM requisitions r WHERE r.status IN ('draft', 'submitted', 'returned', "
                     "'approved') AND NOT EXISTS (SELECT 1 FROM requisition_lines l WHERE l.req_id = r.id AND "
                     "l.po_id IS NOT NULL) ORDER BY r.id"))
    return r and Call(r['requester'], 'POST', f'/requisitions/{r["id"]}/cancel', {'reason': 'no longer needed'},
                      'req.cancel', 'ok')


def v_po_create(g: Gen):
    buyer = g.who('po.create')
    vendors = [r['id'] for r in g.all("SELECT id FROM vendors WHERE status = 'active' ORDER BY id")]
    if not vendors:
        return None
    if g.rng.random() < 0.4:                      # from an approved requisition line
        rl = g.pick(g.all("SELECT l.req_id, l.line, l.sku, l.qty, l.vendor FROM requisition_lines l JOIN requisitions r "
                          "ON r.id = l.req_id WHERE r.status = 'approved' AND l.po_id IS NULL AND l.sku IS NOT NULL "
                          "AND l.vendor IN (SELECT id FROM vendors WHERE status = 'active') ORDER BY l.req_id, l.line"))
        if rl:
            return Call(buyer, 'POST', '/purchase-orders', {'vendor': rl['vendor'], 'lines': [
                {'sku': rl['sku'], 'qty': rl['qty'], 'req_refs': [{'req_id': rl['req_id'], 'line': rl['line']}]}]},
                'po.create.from_req', 'any')
    v = g.pick(vendors)
    skus = [r['sku'] for r in g.all('SELECT DISTINCT sku FROM price_agreements WHERE vendor = ? ORDER BY sku', v)]
    items = [r['sku'] for r in g.all("SELECT sku FROM items WHERE active = 1 AND type = 'purchased' ORDER BY sku")]
    lines = []
    for _ in range(g.rng.randint(1, 3)):
        if skus and g.rng.random() < 0.7:
            lines.append({'sku': g.pick(skus), 'qty': g.rng.choice([10, 40, 100, 250, 600])})
        elif g.rng.random() < 0.8:
            lines.append({'sku': g.pick(items), 'qty': g.rng.choice([5, 30, 120]), 'unit_price': g.money(0.1, 40)})
        else:
            lines.append({'description': 'Service call', 'account': '6200', 'qty': 1, 'unit_price': g.money(50, 900),
                          'department': 'MAINT'})
    return Call(buyer, 'POST', '/purchase-orders', {'vendor': v, 'lines': lines}, 'po.create', 'ok')


def v_po_edit(g: Gen):
    po = g.pick(g.all("SELECT id FROM purchase_orders WHERE status = 'draft' ORDER BY id"))
    if po is None:
        return None
    u = g.who('po.create')
    if g.rng.random() < 0.5:
        line = g.val("SELECT line FROM po_lines WHERE po_id = ? AND status = 'open' ORDER BY line LIMIT 1", po['id'])
        if line is None:
            return None
        return Call(u, 'PATCH', f'/purchase-orders/{po["id"]}/lines/{line}',
                    {'qty': g.rng.choice([5, 15, 60]), 'unit_price': g.money(0.5, 20)}, 'po.update_line', 'ok')
    sku = g.val("SELECT sku FROM items WHERE type = 'purchased' AND active = 1 ORDER BY sku LIMIT 1 OFFSET ?",
                g.rng.randrange(10))
    return Call(u, 'POST', f'/purchase-orders/{po["id"]}/lines', {'sku': sku, 'qty': 12, 'unit_price': g.money(0.5, 9)},
                'po.add_line', 'ok')


def v_po_send(g: Gen):
    po = g.pick(g.all("SELECT id FROM purchase_orders WHERE status = 'draft' ORDER BY id"))
    return po and Call(g.who('po.send'), 'POST', f'/purchase-orders/{po["id"]}/send', None, 'po.send', 'any')


def v_po_cancel(g: Gen):
    po = g.pick(g.all("SELECT p.id FROM purchase_orders p WHERE p.status IN ('draft', 'sent') AND NOT EXISTS "
                      "(SELECT 1 FROM po_lines l WHERE l.po_id = p.id AND l.qty_received > 0) ORDER BY p.id"))
    return po and Call(g.who('po.create'), 'POST', f'/purchase-orders/{po["id"]}/cancel', {'reason': 'fuzz'},
                       'po.cancel', 'ok')


def v_po_close_line(g: Gen):
    pl = g.pick(g.all("SELECT l.po_id, l.line FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id WHERE "
                      "l.status = 'open' AND p.status IN ('sent', 'partially_received') ORDER BY l.po_id, l.line"))
    return pl and Call(g.who('po.create'), 'POST', f'/purchase-orders/{pl["po_id"]}/lines/{pl["line"]}/close',
                       {'reason': 'short-closed'}, 'po.close_line', 'ok')


def v_receive(g: Gen):
    po = g.pick(g.all("SELECT id FROM purchase_orders WHERE status IN ('sent', 'partially_received') ORDER BY id"))
    if po is None:
        return None
    lines = []
    for pl in g.all("SELECT l.*, i.lot_controlled FROM po_lines l LEFT JOIN items i ON i.sku = l.sku "
                    "WHERE l.po_id = ? AND l.status = 'open' ORDER BY l.line", po['id']):
        left = pl['qty'] - pl['qty_received']
        if left <= 0 or g.rng.random() < 0.2:
            continue
        got = left if g.rng.random() < 0.6 else max(round(left * g.rng.uniform(0.2, 0.9), 2), 0.01)
        ln = {'po_line': pl['line'], 'qty_received': got}
        if g.rng.random() < 0.15:
            ln.update({'qty_refused': 1, 'refusal_reason': 'damaged'})
        if pl['lot_controlled']:
            ln.update({'lot': g.uid('LOT'), 'expiry': add_days(g.today, 700)})
        lines.append(ln)
    if not lines:
        return None
    return Call(g.who('rcv.post'), 'POST', '/receipts', {'po_id': po['id'], 'packing_slip': g.uid('PS'), 'lines': lines},
                'rcv.post', g.post_expect())


def v_receipt_reverse(g: Gen):
    r = g.pick(g.all("SELECT id FROM receipts WHERE status = 'posted' ORDER BY id DESC LIMIT 20"))
    return r and Call(g.who('rcv.post'), 'POST', f'/receipts/{r["id"]}/reverse', {'reason': 'received in error'},
                      'rcv.reverse', 'any' if g.period_open() else 'refuse')


def v_ap_enter(g: Gen):
    u = g.who('ap.enter')
    if g.rng.random() < 0.25:
        v = g.val('SELECT id FROM vendors ORDER BY id LIMIT 1 OFFSET ?', g.rng.randrange(8))
        return Call(u, 'POST', '/ap-invoices', {
            'vendor': v, 'invoice_no': g.uid('BILL'), 'invoice_date': g.today,
            'lines': [{'kind': 'other', 'amount': g.money(20, 2000), 'account': '6100', 'department': 'ADMIN'}]},
            'ap.enter.non_po', 'ok')
    po = g.pick(g.all("SELECT p.id, p.vendor FROM purchase_orders p WHERE p.status IN ('sent', 'partially_received', "
                      "'received') AND EXISTS (SELECT 1 FROM po_lines l WHERE l.po_id = p.id AND l.qty_received > "
                      "l.qty_billed + 1e-9) ORDER BY p.id DESC LIMIT 25"))
    if po is None:
        return None
    lines = []
    for pl in g.all('SELECT * FROM po_lines WHERE po_id = ? AND qty_received > qty_billed + 1e-9 ORDER BY line', po['id']):
        price = pl['unit_price'] if g.rng.random() < 0.7 else round(pl['unit_price'] * g.rng.uniform(0.9, 1.1), 4)
        lines.append({'kind': 'item', 'po_line': pl['line'], 'qty': round(pl['qty_received'] - pl['qty_billed'], 4),
                      'unit_price': price})
    if g.rng.random() < 0.3:
        lines.append({'kind': 'freight', 'amount': g.money(10, 200)})
    return Call(u, 'POST', '/ap-invoices', {'vendor': po['vendor'], 'invoice_no': g.uid('INV'), 'invoice_date': g.today,
                                            'po_id': po['id'], 'lines': lines}, 'ap.enter', 'ok')


def v_ap_flow(g: Gen):
    inv = g.pick(g.all("SELECT id, status, entered_by, posted_je FROM ap_invoices WHERE status IN ('entered', 'matched', "
                       "'on_hold', 'approved') ORDER BY id DESC LIMIT 30"))
    if inv is None:
        return None
    held = g.val("SELECT id FROM holds WHERE doc_id = ? AND released_on IS NULL ORDER BY id LIMIT 1", inv['id'])
    i, st = inv['id'], inv['status']
    choice = g.rng.random()
    if held:
        if choice < 0.6:
            return Call(g.who('ap.release_hold'), 'POST', f'/holds/{held}/release', {'note': 'vendor credit agreed'},
                        'ap.release_hold', 'ok')
        if not inv['posted_je']:
            return Call(g.who('ap.enter'), 'POST', f'/ap-invoices/{i}/reject', {'reason': 'not ours'}, 'ap.reject', 'ok')
        return Call(g.who('ap.void'), 'POST', f'/ap-invoices/{i}/void', {'reason': 'billed in error'}, 'ap.void',
                    'any' if g.period_open() else 'refuse')
    if choice < 0.15:
        return Call(g.who('ap.hold'), 'POST', f'/ap-invoices/{i}/holds', {'reason': g.rng.choice(['price', 'quantity']),
                                                                          'note': 'fuzz'}, 'ap.hold', 'ok')
    if st == 'entered':
        if choice < 0.25:
            line = g.val('SELECT line FROM ap_invoice_lines WHERE inv_id = ? ORDER BY line LIMIT 1', i)
            kind = g.val('SELECT kind FROM ap_invoice_lines WHERE inv_id = ? AND line = ?', i, line)
            body = {'unit_price': g.money(0.1, 30)} if kind == 'item' else {'amount': g.money(5, 500)}
            return Call(g.who('ap.enter'), 'PATCH', f'/ap-invoices/{i}/lines/{line}', body, 'ap.update_line', 'ok')
        return Call(g.who('ap.validate'), 'POST', f'/ap-invoices/{i}/validate', None, 'ap.validate', g.post_expect())
    if st == 'matched':
        if choice < 0.25:
            return Call(g.who('ap.void'), 'POST', f'/ap-invoices/{i}/void', {'reason': 'duplicate'}, 'ap.void',
                        'any' if g.period_open() else 'refuse')
        return Call(g.who('ap.approve', exclude=(inv['entered_by'],)), 'POST', f'/ap-invoices/{i}/approve',
                    {'note': 'ok to pay'}, 'ap.approve', 'ok')
    return None


def v_run(g: Gen):
    run = g.pick(g.all("SELECT * FROM payment_runs WHERE status IN ('draft', 'submitted', 'approved') ORDER BY id"))
    prep = g.who('pay.prepare')
    if run is None or g.rng.random() < 0.15:
        return Call(prep, 'POST', '/payment-runs', {'pay_date': add_days(g.today, g.rng.choice([0, 1, 3])),
                                                    'bank_account': 'OPER', 'note': 'fuzz run'}, 'pay.create_run', 'ok')
    rid = run['id']
    if run['status'] == 'draft':
        r = g.rng.random()
        if r < 0.55:
            inv = g.pick(g.all("SELECT i.id, i.total_cents FROM ap_invoices i JOIN vendors v ON v.id = i.vendor WHERE "
                               "i.status = 'approved' AND NOT EXISTS (SELECT 1 FROM holds h WHERE h.doc_id = i.id AND "
                               "h.released_on IS NULL) AND NOT EXISTS (SELECT 1 FROM payment_allocations a JOIN payments p "
                               "ON p.id = a.payment_id WHERE a.inv_id = i.id AND p.status = 'proposed') ORDER BY i.id"))
            if inv is None:
                return None
            body = {'inv_id': inv['id']}
            if g.rng.random() < 0.2 and inv['total_cents'] > 200:
                body['amount'] = round(inv['total_cents'] / 200, 2)
            return Call(run['created_by'], 'POST', f'/payment-runs/{rid}/invoices', body, 'pay.add', 'any')
        if r < 0.7:
            inv = g.val('SELECT a.inv_id FROM payment_allocations a JOIN payments p ON p.id = a.payment_id '
                        'WHERE p.run_id = ? ORDER BY a.inv_id LIMIT 1', rid)
            return inv and Call(run['created_by'], 'DELETE', f'/payment-runs/{rid}/invoices/{inv}', None, 'pay.remove',
                                'ok')
        return Call(run['created_by'], 'POST', f'/payment-runs/{rid}/submit', None, 'pay.submit', 'any')
    if run['status'] == 'submitted':
        approver = g.who('pay.approve', exclude=(run['created_by'],))
        if g.rng.random() < 0.2:
            return Call(approver, 'POST', f'/payment-runs/{rid}/return', {'reason': 'check the floor'}, 'pay.return', 'ok')
        return Call(approver, 'POST', f'/payment-runs/{rid}/approve', {'note': 'ok'}, 'pay.approve', 'any')
    return Call(g.who('pay.release'), 'POST', f'/payment-runs/{rid}/release', None, 'pay.release', 'any')


def v_bank(g: Gen):
    pend = g.pick(g.all("SELECT id, requested_by FROM vendor_bank_accounts WHERE status = 'pending' ORDER BY id"))
    if pend and g.rng.random() < 0.7:
        verb = g.rng.choice(['verify', 'reject'])
        u = g.who('vendor.bank.verify', exclude=(pend['requested_by'],))
        body = {'note': 'called the number on file'} if verb == 'verify' else {'reason': 'vendor denied it'}
        return Call(u, 'POST', f'/vendor-bank-accounts/{pend["id"]}/{verb}', body, f'vendor.bank.{verb}', 'ok')
    v = g.val('SELECT id FROM vendors ORDER BY id LIMIT 1 OFFSET ?', g.rng.randrange(10))
    return Call(g.who('vendor.bank.request'), 'POST', f'/vendors/{v}/bank-accounts',
                {'bank_name': 'Fuzz Bank', 'routing': '0' + str(g.rng.randrange(10 ** 8, 10 ** 9)),
                 'account_no': str(g.rng.randrange(10 ** 7, 10 ** 9))}, 'vendor.bank.request', 'ok')


def v_vendor_update(g: Gen):
    v = g.pick(g.all('SELECT id, status FROM vendors ORDER BY id'))
    if v is None:
        return None
    body = {'status': 'inactive' if v['status'] == 'active' and g.rng.random() < 0.3 else 'active'}
    if g.rng.random() < 0.5:
        body = {'quality_hold': g.rng.random() < 0.5, 'phone': '(555) 555-0100'}
    return Call(g.who('vendor.update'), 'PATCH', f'/vendors/{v["id"]}', body, 'vendor.update', 'ok')


def _je_lines(g: Gen, amount: float) -> list[dict]:
    accts = [r['code'] for r in g.all("SELECT code FROM accounts WHERE active = 1 AND (control IS NULL OR control = 'cash') "
                                      "ORDER BY code")]
    a, b = g.rng.sample(accts, 2)
    return [{'account': a, 'debit': amount, 'department': 'FIN'}, {'account': b, 'credit': amount}]


def v_je_create(g: Gen):
    amt = g.money(10, 4000) if g.rng.random() < 0.7 else g.money(6000, 40000)
    day = g.today if g.rng.random() < 0.8 else add_days(g.today, g.rng.randint(1, 20))
    return Call(g.who('je.create'), 'POST', '/journal-entries', {'entry_date': day, 'memo': 'fuzz accrual',
                                                                 'lines': _je_lines(g, amt)}, 'je.create', 'ok')


def v_je_flow(g: Gen):
    je = g.pick(g.all("SELECT id, status, preparer, entry_date FROM journal_entries WHERE source = 'manual' AND status IN "
                      "('draft', 'submitted', 'approved', 'returned') ORDER BY id DESC LIMIT 20"))
    if je is None:
        return None
    i, st, prep = je['id'], je['status'], je['preparer']
    total = g.val('SELECT SUM(debit_cents) FROM journal_lines WHERE je_id = ?', i) or 0
    small = total < (g.erp.setting('je_approval_threshold_cents', 0) or 0)
    post_exp = 'any' if g.period_open(je['entry_date']) else 'refuse'
    r = g.rng.random()
    if st in ('draft', 'returned'):
        if r < 0.2 and prep in g.staff:
            return Call(prep, 'PUT', f'/journal-entries/{i}/lines', {'lines': _je_lines(g, g.money(10, 3000))}, 'je.edit',
                        'ok')
        if r < 0.3 and prep in g.staff:
            return Call(prep, 'POST', f'/journal-entries/{i}/attachments',
                        {'name': 'support.txt', 'content_base64': base64.b64encode(b'support').decode()}, 'je.attach', 'ok')
        if st == 'draft' and small and r < 0.6:
            return Call(prep, 'POST', f'/journal-entries/{i}/post', None, 'je.post.own', post_exp)
        return Call(prep, 'POST', f'/journal-entries/{i}/submit', None, 'je.submit', 'ok')
    if st == 'submitted':
        u = g.who('je.approve', exclude=(prep,))
        if r < 0.2:
            return Call(u, 'POST', f'/journal-entries/{i}/return', {'reason': 'attach support'}, 'je.return', 'ok')
        return Call(u, 'POST', f'/journal-entries/{i}/approve', {'note': 'ok'}, 'je.approve', 'any')
    return Call(g.who('je.post'), 'POST', f'/journal-entries/{i}/post', None, 'je.post', post_exp)


def v_je_reverse(g: Gen):
    where = "status = 'posted'" + ('' if g.include_known else " AND source = 'manual'")
    je = g.pick(g.all(f'SELECT id FROM journal_entries WHERE {where} ORDER BY id DESC LIMIT 15'))
    return je and Call(g.who('je.post'), 'POST', f'/journal-entries/{je["id"]}/reverse', {'reason': 'fuzz reversal'},
                       'je.reverse', 'any' if g.period_open() else 'refuse')


def v_period(g: Gen):
    closed = [r['period'] for r in g.all("SELECT period FROM periods WHERE status = 'closed' ORDER BY period")]
    cur = g.today[:7]
    if not g.period_open() and g.rng.random() < 0.8:
        return Call(g.who('period.reopen'), 'POST', f'/periods/{cur}/reopen', None, 'period.reopen', 'ok')
    if g.rng.random() < 0.25:
        return Call(g.who('period.close'), 'POST', f'/periods/{cur}/close', None, 'period.close', 'ok')
    if closed and g.rng.random() < 0.5:
        p = closed[-1]
        return Call(g.who('period.reopen'), 'POST', f'/periods/{p}/reopen', None, 'period.reopen', 'ok')
    opened = [r['period'] for r in g.all("SELECT period FROM periods WHERE status = 'open' AND period < ? ORDER BY period",
                                         cur)]
    return opened and Call(g.who('period.close'), 'POST', f'/periods/{opened[-1]}/close', None, 'period.close', 'ok')


def v_sales(g: Gen):
    r = g.rng.random()
    if r < 0.3:
        c = g.val("SELECT id FROM customers WHERE status = 'active' ORDER BY id LIMIT 1 OFFSET ?", g.rng.randrange(8))
        sku = g.val("SELECT sku FROM items WHERE type = 'manufactured' AND active = 1 ORDER BY sku LIMIT 1 OFFSET ?",
                    g.rng.randrange(3))
        return c and sku and Call(g.who('so.create'), 'POST', '/sales-orders',
                                  {'customer': c, 'lines': [{'sku': sku, 'qty': g.rng.choice([2, 10, 40, 400])}]},
                                  'so.create', 'ok')
    if r < 0.4:
        so = g.pick(g.all("SELECT id FROM sales_orders WHERE status = 'on_hold' ORDER BY id"))
        return so and Call(g.who('so.release_hold'), 'POST', f'/sales-orders/{so["id"]}/release',
                           {'note': 'credit ok'}, 'so.release_hold', 'ok')
    if r < 0.47:
        held = "('released', 'partially_shipped')" if g.include_known else "('released')"
        so = g.pick(g.all(f"SELECT id FROM sales_orders WHERE status IN {held} ORDER BY id"))
        return so and Call(g.who('so.create'), 'POST', f'/sales-orders/{so["id"]}/hold', {'reason': 'credit review'},
                           'so.hold', 'ok')
    if r < 0.7:
        sl = g.pick(g.all("SELECT l.so_id, l.line, l.sku, l.qty - l.qty_shipped AS open FROM so_lines l JOIN sales_orders s "
                          "ON s.id = l.so_id WHERE s.status IN ('released', 'partially_shipped') AND l.status = 'open' "
                          "AND l.qty > l.qty_shipped ORDER BY l.so_id, l.line"))
        if sl is None:
            return None
        loc = g.val("SELECT l.code FROM locations l JOIN sales_orders s ON s.ship_from = l.warehouse WHERE s.id = ? "
                    "AND l.kind = 'stock' ORDER BY l.code LIMIT 1", sl['so_id'])
        have = g.val('SELECT COALESCE(SUM(qty), 0) FROM inventory_txns WHERE sku = ? AND location = ?', sl['sku'], loc) or 0
        qty = min(sl['open'], max(have, 0))
        if qty <= 0:
            return None
        qty = qty if g.rng.random() < 0.6 else max(round(qty / 2, 2), 0.01)
        return Call(g.who('so.ship'), 'POST', '/shipments', {'so_id': sl['so_id'], 'lines': [{'so_line': sl['line'],
                                                                                              'qty': qty}]},
                    'so.ship', g.post_expect())
    if r < 0.8:
        sh = g.pick(g.all("SELECT id FROM shipments WHERE status = 'shipped' ORDER BY id"))
        return sh and Call(g.who('ar.invoice'), 'POST', f'/shipments/{sh["id"]}/invoice', {}, 'ar.invoice',
                           g.post_expect())
    if r < 0.9:
        inv = g.pick(g.all("SELECT id, customer FROM ar_invoices WHERE status = 'open' ORDER BY id DESC LIMIT 20"))
        return inv and Call(g.who('ar.cash'), 'POST', '/cash-receipts', {'amount': g.money(50, 3000),
                                                                         'customer': inv['customer'],
                                                                         'reference': g.uid('REF')}, 'ar.cash',
                            g.post_expect())
    cr = g.pick(g.all("SELECT r.id, r.customer, r.amount_cents - COALESCE((SELECT SUM(amount_cents) FROM cash_applications "
                      "a WHERE a.receipt_id = r.id), 0) AS left FROM cash_receipts r WHERE r.status IN ('unapplied', "
                      "'partially_applied') AND r.customer IS NOT NULL ORDER BY r.id"))
    if cr is None or cr['left'] <= 0:
        return None
    inv = g.pick(g.all("SELECT i.id, i.total_cents - COALESCE((SELECT SUM(amount_cents + discount_cents) FROM "
                       "cash_applications a WHERE a.inv_id = i.id), 0) AS open FROM ar_invoices i WHERE i.status = 'open' "
                       "AND i.customer = ? ORDER BY i.id", cr['customer']))
    if inv is None or inv['open'] <= 0:
        return None
    amt = min(cr['left'], inv['open'])
    return Call(g.who('ar.cash'), 'POST', f'/cash-receipts/{cr["id"]}/apply',
                {'applications': [{'inv_id': inv['id'], 'amount': amt / 100}]}, 'ar.apply', g.post_expect())


def v_stock(g: Gen):
    row = g.pick(g.all("SELECT sku, location, lot, ROUND(SUM(qty), 4) AS q FROM inventory_txns GROUP BY sku, location, lot "
                       "HAVING SUM(qty) > 1 ORDER BY sku, location, lot"))
    if row is None:
        return None
    if g.rng.random() < 0.5:
        to = g.pick(r['code'] for r in g.all('SELECT code FROM locations WHERE code != ? ORDER BY code', row['location']))
        body = {'sku': row['sku'], 'from': row['location'], 'to': to, 'qty': round(min(row['q'], g.rng.choice([1, 5, 20])), 4)}
        if row['lot']:
            body['lot'] = row['lot']
        return Call(g.who('inv.transfer'), 'POST', '/inventory/transfers', body, 'inv.transfer', 'ok')
    delta = -round(min(row['q'], 2), 4) if g.rng.random() < 0.5 else 3
    body = {'sku': row['sku'], 'location': row['location'], 'qty_delta': delta, 'reason': 'cycle count'}
    if row['lot']:
        body['lot'] = row['lot']
    return Call(g.who('inv.adjust'), 'POST', '/inventory/adjustments', body, 'inv.adjust', g.post_expect())


def v_wo(g: Gen):
    wo = g.pick(g.all("SELECT * FROM work_orders WHERE status IN ('planned', 'released', 'in_progress', 'completed') "
                      "ORDER BY id"))
    if wo is None or g.rng.random() < 0.2:
        sku = g.val("SELECT sku FROM items WHERE type = 'manufactured' AND active = 1 ORDER BY sku LIMIT 1 OFFSET ?",
                    g.rng.randrange(3))
        return sku and Call(g.who('wo.create'), 'POST', '/work-orders',
                            {'sku': sku, 'qty': g.rng.choice([2, 5, 20]), 'start_date': g.today,
                             'due_date': add_days(g.today, 5)}, 'wo.create', 'ok')
    i, st = wo['id'], wo['status']
    pe = g.post_expect()
    if st == 'planned':
        if g.rng.random() < 0.2:
            return Call(g.who('wo.create'), 'POST', f'/work-orders/{i}/cancel', {'reason': 'not needed'}, 'wo.cancel', 'ok')
        return Call(g.who('wo.release'), 'POST', f'/work-orders/{i}/release', None, 'wo.release', 'any')
    if st == 'completed':
        return Call(g.who('wo.close'), 'POST', f'/work-orders/{i}/close', None, 'wo.close', pe)
    r = g.rng.random()
    if r < 0.4:
        return Call(g.who('wo.issue'), 'POST', f'/work-orders/{i}/issue', {'units': g.rng.choice([1, 2])}, 'wo.issue', 'any')
    if r < 0.5:
        iss = g.val('SELECT id FROM wo_issues w WHERE wo_id = ? AND reversal_of IS NULL AND qty > 0 AND NOT EXISTS '
                    '(SELECT 1 FROM wo_issues x WHERE x.reversal_of = w.id) ORDER BY id LIMIT 1', i)
        return iss and Call(g.who('wo.issue'), 'POST', f'/wo-issues/{iss}/reverse', {'reason': 'wrong lot'},
                            'wo.reverse_issue', 'any')
    if r < 0.8:
        left = wo['qty'] - wo['qty_completed'] - wo['qty_scrapped']
        if left <= 0:
            return None
        return Call(g.who('wo.complete'), 'POST', f'/work-orders/{i}/complete',
                    {'qty': min(left, g.rng.choice([1, 2, left])), 'scrap_qty': 0}, 'wo.complete', pe)
    return Call(g.who('wo.close'), 'POST', f'/work-orders/{i}/close', None, 'wo.close', pe)


def v_comms(g: Gen):
    u = g.pick(g.staff)
    r = g.rng.random()
    if r < 0.3:
        return Call(u, 'POST', '/outbox', {'to': 'someone@example.com', 'subject': 'fuzz', 'body': 'hello'}, 'msg.send',
                    'ok')
    if r < 0.55:
        inv = g.val('SELECT id FROM ap_invoices ORDER BY id DESC LIMIT 1')
        to = g.pick(u2 for u2 in g.staff if u2 != u)
        return Call(u, 'POST', '/escalations', {'record_type': 'ap_invoice', 'record_id': inv, 'to': to,
                                                'reason': 'price_variance', 'note': 'please decide'}, 'escalate', 'ok')
    if r < 0.8:
        v = g.val('SELECT id FROM vendors ORDER BY id LIMIT 1 OFFSET ?', g.rng.randrange(10))
        return Call(u, 'POST', '/calls', {'party_type': 'vendor', 'party_id': v}, 'call', 'any')
    msg = g.one("SELECT id, box FROM messages WHERE direction = 'in' AND visible_on <= ? ORDER BY id", g.today)
    if msg is None:
        return None
    u = g.who(f'box.{msg["box"]}')
    return u and Call(u, 'POST', f'/inbox/{msg["id"]}/disposition', {'disposition': 'processed', 'ref': 'fuzz'},
                      'msg.dispose', 'ok')


def v_vendor_request(g: Gen):
    pl = g.pick(g.all("SELECT l.po_id, l.line, p.vendor FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id "
                      "WHERE p.status IN ('sent', 'partially_received') AND l.status = 'open' ORDER BY l.po_id, l.line"))
    if pl is None:
        return None
    if g.rng.random() < 0.5:
        return Call(g.who('vendor.request'), 'POST', '/vendor-requests', {
            'vendor': pl['vendor'], 'kind': 'expedite', 'po_id': pl['po_id'], 'po_line': pl['line'],
            'wanted_date': add_days(g.today, 2)}, 'vendor.request', 'ok')
    return Call(g.who('vendor.request'), 'POST', '/vendor-requests', {
        'vendor': pl['vendor'], 'kind': 'dispute', 'inv_ref': 'X-1', 'amount': 12.5, 'note': 'short shipped'},
        'vendor.request', 'ok')


def v_mrp(g: Gen):
    s = g.pick(g.all("SELECT id FROM mrp_suggestions WHERE status = 'open' AND kind IN ('planned_po', 'planned_wo') "
                     "ORDER BY id LIMIT 10"))
    if s and g.rng.random() < 0.6:
        return Call(g.who('mrp.release'), 'POST', f'/mrp/suggestions/{s["id"]}/release', {}, 'mrp.release', 'any')
    return Call(g.who('mrp.run'), 'POST', '/mrp/runs', {'horizon_weeks': 4}, 'mrp.run', 'ok')


VALID = [(12, read_call), (5, v_req_create), (2, v_req_submit), (5, v_req_decide), (1, v_req_cancel), (6, v_po_create),
         (2, v_po_edit), (5, v_po_send), (1, v_po_cancel), (1, v_po_close_line), (8, v_receive), (2, v_receipt_reverse),
         (8, v_ap_enter), (12, v_ap_flow), (12, v_run), (3, v_bank), (1, v_vendor_update), (4, v_je_create),
         (6, v_je_flow), (2, v_je_reverse), (1, v_period), (8, v_sales), (3, v_stock), (5, v_wo), (3, v_comms),
         (1, v_vendor_request), (1, v_mrp)]


# ---- invalid calls: each breaks one rule and must be refused -------------------------------------------------

def x_missing(g: Gen):
    ghost = 'NOPE-' + str(g.rng.randrange(10 ** 6))
    user, method, path, body = g.rng.choice([
        (g.who('ap.validate'), 'POST', f'/ap-invoices/{ghost}/validate', None),
        (g.who('ap.approve'), 'POST', f'/ap-invoices/{ghost}/approve', {}),
        (g.who('ap.void'), 'POST', f'/ap-invoices/{ghost}/void', {'reason': 'x'}),
        (g.who('rcv.post'), 'POST', '/receipts', {'po_id': ghost, 'lines': [{'po_line': 1, 'qty_received': 1}]}),
        (g.who('rcv.post'), 'POST', f'/receipts/{ghost}/reverse', {'reason': 'x'}),
        (g.who('po.send'), 'POST', f'/purchase-orders/{ghost}/send', None),
        (g.who('pay.release'), 'POST', f'/payment-runs/{ghost}/release', None),
        (g.who('pay.prepare'), 'POST', f'/payment-runs/{ghost}/invoices', {'inv_id': ghost}),
        (g.who('je.post'), 'POST', f'/journal-entries/{ghost}/post', None),
        (g.who('je.post'), 'POST', f'/journal-entries/{ghost}/reverse', {'reason': 'x'}),
        (g.who('period.close'), 'POST', '/periods/2031-13/close', None),
        (g.who('ap.release_hold'), 'POST', f'/holds/{ghost}/release', {'note': 'x'}),
        (g.who('ap.enter'), 'POST', '/ap-invoices', {'vendor': ghost, 'invoice_no': 'Z1', 'invoice_date': g.today,
                                                     'lines': [{'kind': 'other', 'amount': 5, 'account': '6100'}]}),
        (g.who('po.create'), 'POST', '/purchase-orders', {'vendor': ghost, 'lines': [{'sku': 'BR-0750', 'qty': 1}]}),
        (g.who('so.ship'), 'POST', '/shipments', {'so_id': ghost, 'lines': [{'so_line': 1, 'qty': 1}]}),
        (g.who('wo.complete'), 'POST', f'/work-orders/{ghost}/complete', {'qty': 1}),
        (g.who('vendor.bank.verify'), 'POST', f'/vendor-bank-accounts/{ghost}/verify', {}),
        (g.pick(g.staff), 'GET', f'/purchase-orders/{ghost}', None),
    ])
    return Call(user, method, path, body, 'x.missing_id', 'refuse')


def x_no_route(g: Gen):
    je = g.val("SELECT id FROM journal_entries WHERE status = 'posted' ORDER BY id DESC LIMIT 1")
    rc = g.val("SELECT id FROM receipts ORDER BY id DESC LIMIT 1")
    inv = g.val("SELECT id FROM ap_invoices WHERE posted_je IS NOT NULL ORDER BY id DESC LIMIT 1")
    pay = g.val("SELECT id FROM payments WHERE status != 'proposed' ORDER BY id DESC LIMIT 1")
    ar = g.val("SELECT id FROM ar_invoices ORDER BY id DESC LIMIT 1")
    user = g.pick(['priya.raman', 'hannah.brooks', 'omar.haddad', 'riley.park'])
    method, path = g.rng.choice([('DELETE', f'/journal-entries/{je}'), ('DELETE', f'/receipts/{rc}'),
                                 ('DELETE', f'/ap-invoices/{inv}'), ('DELETE', f'/payments/{pay}'),
                                 ('DELETE', f'/ar-invoices/{ar}'), ('PATCH', f'/journal-entries/{je}'),
                                 ('PUT', f'/receipts/{rc}'), ('PATCH', f'/ap-invoices/{inv}'),
                                 ('POST', f'/journal-entries/{je}/delete'), ('DELETE', '/audit')])
    return Call(user, method, path, {'status': 'draft', 'total_cents': 1}, 'x.delete_or_edit_posted', 'refuse')


def x_bad_auth(g: Gen):
    tok = g.rng.choice(['', 'bb_notatoken', 'Bearer', 'x' * 64])
    return Call(None, 'POST', '/journal-entries', {'entry_date': g.today, 'memo': 'x', 'lines': []}, 'x.bad_token',
                'refuse', token=tok)


def x_forbidden(g: Gen):
    cases = []
    for action, method, path, body in [
            ('je.post', 'POST', '/journal-entries', {'entry_date': g.today, 'memo': 'x', 'lines': _je_lines(g, 10)}),
            ('pay.approve', 'POST', '/payment-runs/{run}/approve', {}),
            ('ap.release_hold', 'POST', '/holds/{hold}/release', {'note': 'x'}),
            ('period.close', 'POST', '/periods/{cur}/close', None),
            ('ap.enter', 'POST', '/ap-invoices', {'vendor': 'V-10001', 'invoice_no': 'F1', 'invoice_date': g.today,
                                                  'lines': [{'kind': 'other', 'amount': 5, 'account': '6100'}]}),
            ('rcv.post', 'POST', '/receipts', {'po_id': '{po}', 'lines': [{'po_line': 1, 'qty_received': 1}]}),
            ('inv.adjust', 'POST', '/inventory/adjustments', {'sku': 'BR-0750', 'location': 'DAY-STK', 'qty_delta': 5,
                                                              'reason': 'x'}),
            ('vendor.bank.verify', 'POST', '/vendor-bank-accounts/{vba}/verify', {}),
            ('audit.read', 'GET', '/audit?actor=priya.raman', None)]:
        cases.append((action, method, path, body))
    action, method, path, body = g.pick(cases)
    if action == 'je.post':
        action = 'je.create'
    u = g.lacking(action)
    fill = {'run': g.val("SELECT id FROM payment_runs WHERE status = 'submitted' LIMIT 1"),
            'hold': g.val('SELECT id FROM holds WHERE released_on IS NULL LIMIT 1'), 'cur': g.today[:7],
            'po': g.val("SELECT id FROM purchase_orders WHERE status = 'sent' LIMIT 1"),
            'vba': g.val("SELECT id FROM vendor_bank_accounts WHERE status = 'pending' LIMIT 1")}
    if any(f'{{{k}}}' in path + json.dumps(body) and not v for k, v in fill.items()):
        return None
    path = path.format(**fill)
    if body and 'po_id' in body:
        body = dict(body, po_id=fill['po'])
    if action == 'audit.read':                       # without audit.read you see only your own events: not a refusal
        return None
    return u and Call(u, method, path, body, f'x.forbidden.{action}', 'refuse')


def x_wrong_status(g: Gen):
    cands = []
    paid = g.val("SELECT id FROM ap_invoices WHERE status = 'paid' ORDER BY id DESC LIMIT 1")
    if paid:
        cands += [(g.who('ap.validate'), 'POST', f'/ap-invoices/{paid}/validate', None, 'validate paid'),
                  (g.who('ap.void'), 'POST', f'/ap-invoices/{paid}/void', {'reason': 'x'}, 'void paid'),
                  (g.who('ap.enter'), 'POST', f'/ap-invoices/{paid}/reject', {'reason': 'x'}, 'reject paid'),
                  (g.who('ap.enter'), 'PATCH', f'/ap-invoices/{paid}/lines/1', {'unit_price': 1}, 'edit paid'),
                  (g.who('ap.hold'), 'POST', f'/ap-invoices/{paid}/holds', {'reason': 'price'}, 'hold paid')]
    posted = g.val("SELECT id FROM ap_invoices WHERE status IN ('matched', 'approved') ORDER BY id DESC LIMIT 1")
    if posted:
        cands += [(g.who('ap.enter'), 'PATCH', f'/ap-invoices/{posted}/lines/1', {'unit_price': 1}, 'edit posted'),
                  (g.who('ap.validate'), 'POST', f'/ap-invoices/{posted}/validate', None, 'validate twice'),
                  (g.who('ap.enter'), 'POST', f'/ap-invoices/{posted}/reject', {'reason': 'x'}, 'reject posted')]
    held = g.val("SELECT doc_id FROM holds WHERE released_on IS NULL ORDER BY id DESC LIMIT 1")
    draft_run = g.one("SELECT id, created_by FROM payment_runs WHERE status = 'draft' ORDER BY id DESC LIMIT 1")
    if held:
        cands.append((g.who('ap.validate'), 'POST', f'/ap-invoices/{held}/validate', None, 'validate held'))
        cands.append((g.who('ap.approve'), 'POST', f'/ap-invoices/{held}/approve', {}, 'approve held'))
        if draft_run:
            cands.append((draft_run['created_by'], 'POST', f'/payment-runs/{draft_run["id"]}/invoices',
                          {'inv_id': held}, 'pay held invoice'))
    unapproved = g.val("SELECT id FROM ap_invoices WHERE status IN ('entered', 'matched') ORDER BY id DESC LIMIT 1")
    if unapproved and draft_run:
        cands.append((draft_run['created_by'], 'POST', f'/payment-runs/{draft_run["id"]}/invoices',
                      {'inv_id': unapproved}, 'pay unapproved invoice'))
    rel = g.val("SELECT id FROM payment_runs WHERE status = 'released' ORDER BY id DESC LIMIT 1")
    if rel:
        inv = g.val('SELECT a.inv_id FROM payment_allocations a JOIN payments p ON p.id = a.payment_id WHERE p.run_id = ? '
                    'LIMIT 1', rel)
        cands += [(g.who('pay.release'), 'POST', f'/payment-runs/{rel}/release', None, 'release twice'),
                  (g.who('pay.approve'), 'POST', f'/payment-runs/{rel}/approve', {}, 'approve released run'),
                  (g.who('pay.prepare'), 'DELETE', f'/payment-runs/{rel}/invoices/{inv}', None, 'delete paid allocation')]
    run_draft = g.val("SELECT id FROM payment_runs WHERE status IN ('draft', 'submitted') ORDER BY id DESC LIMIT 1")
    if run_draft:
        cands.append((g.who('pay.release'), 'POST', f'/payment-runs/{run_draft}/release', None, 'release unapproved run'))
    sent = g.val("SELECT id FROM purchase_orders WHERE status != 'draft' ORDER BY id DESC LIMIT 1")
    if sent:
        cands += [(g.who('po.send'), 'POST', f'/purchase-orders/{sent}/send', None, 'send twice'),
                  (g.who('po.create'), 'PATCH', f'/purchase-orders/{sent}/lines/1', {'qty': 99999}, 'edit sent PO qty'),
                  (g.who('po.create'), 'POST', f'/purchase-orders/{sent}/lines', {'sku': 'BR-0750', 'qty': 1},
                   'add line to sent PO')]
    draft_po = g.val("SELECT id FROM purchase_orders WHERE status IN ('draft', 'received', 'cancelled') "
                     'ORDER BY id DESC LIMIT 1')
    if draft_po:
        cands.append((g.who('rcv.post'), 'POST', '/receipts', {'po_id': draft_po, 'lines': [{'po_line': 1,
                                                                                            'qty_received': 1}]},
                      'receive unsent/closed PO'))
    rcv_po = g.val("SELECT id FROM purchase_orders WHERE status IN ('partially_received', 'received') ORDER BY id DESC "
                   'LIMIT 1')
    if rcv_po:
        cands.append((g.who('po.create'), 'POST', f'/purchase-orders/{rcv_po}/cancel', {'reason': 'x'},
                      'cancel received PO'))
    rev = g.val("SELECT id FROM receipts WHERE status = 'reversed' ORDER BY id DESC LIMIT 1")
    if rev:
        cands.append((g.who('rcv.post'), 'POST', f'/receipts/{rev}/reverse', {'reason': 'x'}, 'reverse twice'))
    je = g.one("SELECT id, preparer FROM journal_entries WHERE status IN ('posted', 'reversed') AND source = 'manual' "
               'ORDER BY id DESC LIMIT 1') or g.one("SELECT id, preparer FROM journal_entries WHERE status = 'reversed' "
                                                    'ORDER BY id DESC LIMIT 1')
    if je:
        cands += [(g.who('je.post'), 'POST', f'/journal-entries/{je["id"]}/post', None, 'post posted entry'),
                  (g.who('je.approve'), 'POST', f'/journal-entries/{je["id"]}/approve', {}, 'approve posted entry'),
                  (je['preparer'] if je['preparer'] in g.staff else g.who('je.create'), 'PUT',
                   f'/journal-entries/{je["id"]}/lines', {'lines': _je_lines(g, 5)}, 'edit posted entry')]
    je_rev = g.val("SELECT id FROM journal_entries WHERE status = 'reversed' ORDER BY id DESC LIMIT 1")
    if je_rev:
        cands.append((g.who('je.post'), 'POST', f'/journal-entries/{je_rev}/reverse', {}, 'reverse twice'))
    vba = g.val("SELECT id FROM vendor_bank_accounts WHERE status != 'pending' ORDER BY id DESC LIMIT 1")
    if vba:
        cands.append((g.who('vendor.bank.verify'), 'POST', f'/vendor-bank-accounts/{vba}/verify', {}, 'verify decided'))
    wo = g.val("SELECT id FROM work_orders WHERE status IN ('closed', 'cancelled') ORDER BY id DESC LIMIT 1")
    if wo:
        cands += [(g.who('wo.complete'), 'POST', f'/work-orders/{wo}/complete', {'qty': 1}, 'complete closed WO'),
                  (g.who('wo.issue'), 'POST', f'/work-orders/{wo}/issue', {'units': 1}, 'issue to closed WO')]
    so = g.val("SELECT id FROM sales_orders WHERE status IN ('on_hold', 'shipped') ORDER BY id DESC LIMIT 1")
    if so:
        cands.append((g.who('so.ship'), 'POST', '/shipments', {'so_id': so, 'lines': [{'so_line': 1, 'qty': 1}]},
                      'ship held/shipped SO'))
    shp = g.val("SELECT id FROM shipments WHERE status = 'invoiced' ORDER BY id DESC LIMIT 1")
    if shp:
        cands.append((g.who('ar.invoice'), 'POST', f'/shipments/{shp}/invoice', {}, 'invoice twice'))
    c = g.pick(cands)
    return c and Call(c[0], c[1], c[2], c[3], f'x.status.{c[4]}', 'refuse')


def x_controls(g: Gen):
    """Hard controls: separation of duties, limits, closed periods, over-receipt, duplicates, inactive vendors."""
    r = g.rng.random()
    if r < 0.12:                                   # the requester approves their own requisition
        head = g.one("SELECT code, head FROM departments WHERE head IN (SELECT user_id FROM tokens) ORDER BY code "
                     'LIMIT 1 OFFSET ?', g.rng.randrange(4))
        req = head and g.val("SELECT r.id FROM requisitions r JOIN approval_requests a ON a.doc_id = r.id AND "
                             "a.status = 'pending' WHERE r.status = 'submitted' AND r.requester = ? AND a.approver = ?",
                             head['head'], head['head'])
        return req and Call(head['head'], 'POST', f'/requisitions/{req}/approve', {}, 'x.sod.requester_approves',
                            'refuse')
    if r < 0.24:                                   # over the approver's limit
        req = _pending_req(g)
        if req is None:
            return None
        lim = g.val("SELECT limit_cents FROM approval_limits WHERE user_id = ? AND doc_type = 'requisition'",
                    req['approver']) or 0
        if req['total_cents'] <= lim:
            return None
        return Call(req['approver'], 'POST', f'/requisitions/{req["id"]}/approve', {}, 'x.over_limit.requisition',
                    'refuse')
    if r < 0.34:                                   # the preparer approves their own journal entry
        je = g.one("SELECT id, preparer FROM journal_entries WHERE status = 'submitted' ORDER BY id DESC LIMIT 1")
        if je is None or je['preparer'] not in g.staff:
            return None
        return Call(je['preparer'], 'POST', f'/journal-entries/{je["id"]}/approve', {}, 'x.sod.preparer_approves',
                    'refuse')
    if r < 0.44:                                   # an entry dated in a closed period is never posted
        p = g.val("SELECT period FROM periods WHERE status = 'closed' ORDER BY period DESC LIMIT 1")
        if p is None:
            return None
        prep = g.who('je.create')
        je = g.one("SELECT id, preparer FROM journal_entries WHERE status IN ('draft', 'approved', 'submitted') AND "
                   "period IN (SELECT period FROM periods WHERE status = 'closed') ORDER BY id DESC LIMIT 1")
        if je and je['preparer'] in g.staff:
            return Call(g.who('je.post') if g.rng.random() < 0.5 else je['preparer'], 'POST',
                        f'/journal-entries/{je["id"]}/post', None, 'x.closed_period.post_entry', 'refuse')
        return Call(prep, 'POST', '/journal-entries', {'entry_date': f'{p}-15', 'memo': 'late accrual',
                                                       'lines': _je_lines(g, 25)}, 'je.create.closed_period', 'ok')
    if r < 0.52:                                   # a customer invoice dated in a closed period
        p = g.val("SELECT period FROM periods WHERE status = 'closed' ORDER BY period DESC LIMIT 1")
        sh = g.val("SELECT id FROM shipments WHERE status = 'shipped' ORDER BY id LIMIT 1")
        return p and sh and Call(g.who('ar.invoice'), 'POST', f'/shipments/{sh}/invoice', {'invoice_date': f'{p}-28'},
                                 'x.closed_period.ar_invoice', 'refuse')
    if r < 0.62:                                   # receive over the ceiling
        pl = g.pick(g.all("SELECT l.po_id, l.line, l.qty, l.qty_received, i.lot_controlled FROM po_lines l JOIN "
                          "purchase_orders p ON p.id = l.po_id LEFT JOIN items i ON i.sku = l.sku WHERE p.status IN "
                          "('sent', 'partially_received') AND l.status = 'open' ORDER BY l.po_id, l.line"))
        if pl is None:
            return None
        ln = {'po_line': pl['line'], 'qty_received': round(pl['qty'] * 1.5 - pl['qty_received'] + 1, 4)}
        if pl['lot_controlled']:
            ln.update({'lot': 'LOT-OVER', 'expiry': add_days(g.today, 500)})
        return Call(g.who('rcv.post'), 'POST', '/receipts', {'po_id': pl['po_id'], 'lines': [ln]},
                    'x.over_receipt_ceiling', 'refuse')
    if r < 0.72:                                   # a duplicate vendor invoice number
        inv = g.one('SELECT vendor, invoice_no FROM ap_invoices ORDER BY id DESC LIMIT 1 OFFSET ?', g.rng.randrange(5))
        return inv and Call(g.who('ap.enter'), 'POST', '/ap-invoices', {
            'vendor': inv['vendor'], 'invoice_no': inv['invoice_no'], 'invoice_date': g.today,
            'lines': [{'kind': 'other', 'amount': 10, 'account': '6100'}]}, 'x.duplicate_invoice', 'refuse')
    if r < 0.78:                                   # an inactive vendor gets no PO
        v = g.val("SELECT id FROM vendors WHERE status = 'inactive' ORDER BY id LIMIT 1")
        return v and Call(g.who('po.create'), 'POST', '/purchase-orders', {'vendor': v, 'lines': [
            {'sku': 'BR-0750', 'qty': 1, 'unit_price': 1}]}, 'x.inactive_vendor', 'refuse')
    if r < 0.84:                                   # the AP clerk approves an invoice they entered
        inv = g.one("SELECT i.id, i.entered_by FROM ap_invoices i WHERE i.status = 'matched' AND i.total_cents > 0 AND "
                    "i.entered_by IN (SELECT ur.user_id FROM user_roles ur JOIN role_permissions rp ON rp.role = ur.role "
                    "WHERE rp.action = 'ap.approve') AND NOT EXISTS (SELECT 1 FROM holds h WHERE h.doc_id = i.id AND "
                    "h.released_on IS NULL) ORDER BY i.id DESC LIMIT 1")
        return inv and Call(inv['entered_by'], 'POST', f'/ap-invoices/{inv["id"]}/approve', {},
                            'x.sod.enterer_approves', 'refuse')
    if r < 0.92:                                   # stock may not go negative
        row = g.one("SELECT sku, location, ROUND(SUM(qty), 4) AS q FROM inventory_txns GROUP BY sku, location, lot "
                    "HAVING SUM(qty) > 0 AND lot IS NULL ORDER BY sku LIMIT 1 OFFSET ?", g.rng.randrange(5))
        return row and Call(g.who('inv.transfer'), 'POST', '/inventory/transfers',
                            {'sku': row['sku'], 'from': row['location'], 'to': 'DAY-QA' if row['location'] != 'DAY-QA'
                             else 'DAY-STK', 'qty': row['q'] + 10 ** 6}, 'x.insufficient_stock', 'refuse')
    body = g.rng.choice([b'{"lines": ', b'[1, 2, 3]', b'"just a string"', b'\xff\xfe'])
    return Call(g.who('je.create'), 'POST', '/journal-entries', None, 'x.body_not_json_object', 'refuse', raw=body)


def x_values(g: Gen):
    """Well-typed but out-of-range values."""
    entered = g.val("SELECT id FROM ap_invoices WHERE status = 'entered' ORDER BY id LIMIT 1")
    po = g.one("SELECT l.po_id, l.line FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id WHERE p.status IN "
               "('sent', 'partially_received') AND l.status = 'open' ORDER BY l.po_id LIMIT 1")
    c = g.pick([c for c in [
        (g.who('rcv.post'), 'POST', '/receipts', po and {'po_id': po['po_id'], 'lines': [{'po_line': po['line'],
                                                                                         'qty_received': 0}]}),
        (g.who('rcv.post'), 'POST', '/receipts', po and {'po_id': po['po_id'], 'lines': [{'po_line': po['line'],
                                                                                         'qty_received': -5}]}),
        (g.who('ar.cash'), 'POST', '/cash-receipts', {'amount': -25}),
        (g.who('inv.transfer'), 'POST', '/inventory/transfers', {'sku': 'BR-0750', 'from': 'DAY-STK', 'to': 'DAY-STK',
                                                                 'qty': 1}),
        (g.who('inv.transfer'), 'POST', '/inventory/transfers', {'sku': 'BR-0750', 'from': 'DAY-STK', 'to': 'DAY-QA',
                                                                 'qty': 0}),
        (g.who('je.create'), 'POST', '/journal-entries', {'entry_date': g.today, 'memo': 'x', 'lines': [
            {'account': '6100', 'debit': 10}, {'account': '1000', 'credit': 9}]}),
        (g.who('je.create'), 'POST', '/journal-entries', {'entry_date': g.today, 'memo': 'x', 'lines': [
            {'account': '6100', 'debit': 10, 'credit': 10}, {'account': '1000', 'credit': 0}]}),
        (g.who('je.create'), 'POST', '/journal-entries', {'entry_date': '2040-01-15', 'memo': 'x',
                                                          'lines': _je_lines(g, 10)}),
        (g.who('po.create'), 'POST', '/purchase-orders', {'vendor': 'V-10001', 'lines': [{'sku': 'BR-0750', 'qty': -3}]}),
        (g.who('po.create'), 'POST', '/purchase-orders', {'vendor': 'V-10001', 'lines': []}),
        (g.who('ap.enter'), 'POST', '/ap-invoices', {'vendor': 'V-10001', 'invoice_no': '   ', 'invoice_date': g.today,
                                                     'lines': [{'kind': 'other', 'amount': 1, 'account': '6100'}]}),
        (g.who('ap.enter'), 'POST', '/ap-invoices', {'vendor': 'V-10001', 'invoice_no': g.uid('Q'),
                                                     'invoice_date': g.today, 'lines': [{'kind': 'bribe', 'amount': 1}]}),
        (g.who('pay.prepare'), 'POST', '/payment-runs', {'pay_date': '2020-01-01', 'bank_account': 'OPER'}),
        (g.who('pay.prepare'), 'POST', '/payment-runs', {'pay_date': g.today, 'bank_account': 'NOPE'}),
        (g.who('mrp.run'), 'POST', '/mrp/runs', {'horizon_weeks': 500}),
        (g.who('wo.create'), 'POST', '/work-orders', {'sku': 'BR-0750', 'qty': 5, 'start_date': g.today,
                                                      'due_date': g.today}),
        (g.who('ap.hold'), 'POST', f'/ap-invoices/{entered or "X"}/holds', {'reason': 'because'}),
    ] if c[3] is not None] + ([
        (g.who('je.create'), 'POST', '/journal-entries', {'entry_date': g.today[:8] + '99', 'memo': 'x',
                                                          'lines': _je_lines(g, 10)}),
        (g.who('pay.prepare'), 'POST', '/payment-runs', {'pay_date': 'next friday', 'bank_account': 'OPER'}),
    ] if g.include_known else []))
    return c and Call(c[0], c[1], c[2], c[3], 'x.bad_value', 'refuse')


INVALID = [(4, x_missing), (2, x_no_route), (1, x_bad_auth), (3, x_forbidden), (6, x_wrong_status), (5, x_controls),
           (3, x_values)]


# ---- malformed input (--malformed): wrong JSON types; bb-erp should answer 4xx, not 500 -----------------------

def malform(g: Gen, c: Call) -> Call:
    body = json.loads(json.dumps(c.body)) if isinstance(c.body, dict) else {}
    r = g.rng.random()
    path = c.path
    if r < 0.2 and '/lines/' in path:
        path = path.rsplit('/', 1)[0] + '/one' if path[-1].isdigit() else path.replace('/lines/', '/lines/x')
    elif r < 0.4 and body.get('lines') is not None:
        body['lines'] = g.rng.choice(['many', 7, [1, 2], [{'qty': 'lots'}]])
    elif r < 0.6 and body:
        k = g.pick(sorted(body))
        body[k] = g.rng.choice([None, [], {}, 'abc', -1, 1e308, True])
    else:
        body[g.rng.choice(['qty', 'amount', 'po_line', 'units', 'qty_delta'])] = g.rng.choice(['abc', [], {'x': 1}])
    # lenient acceptance of an odd value is not a bug; only a 5xx is
    return Call(c.user, c.method, path, body, 'x.malformed.' + c.kind, 'any')


# ============================================================================================ runs

def fuzz_sequence(scenario: str, seed: int, index: int, steps: int, work: str, malformed: bool = False,
                  include_known: bool = False, max_days: int = 2, check: bool = True) -> dict:
    h = Harness(scenario, os.path.join(work, f'seq-{index}'), check=check)
    g = Gen(h.erp, random.Random(f'{seed}:{index}'), f'{seed}.{index}', malformed, include_known, max_days)
    kinds: dict[str, dict] = {}
    t0 = time.time()
    try:
        for i in range(steps):
            s = g.next(i)
            status, _ = h.step(s)
            k = kinds.setdefault(s.kind, {})
            k[str(status)] = k.get(str(status), 0) + 1
        if h.checker and not h.checker.audit_prefix_ok():
            h.violations.append(Violation('audit_append_only', 'prefix hash of the first audit rows changed'))
        return {'seed': seed, 'sequence': index, 'steps': steps, 'seconds': round(time.time() - t0, 2),
                'kinds': kinds, 'violations': [v.to_json() for v in h.violations], 'calls': h.log,
                'export': h.export()}
    finally:
        h.close()


def replay(scenario: str, calls: list[dict], work: str, check: bool = True) -> dict:
    h = Harness(scenario, work, check=check)
    try:
        for d in calls:
            h.step(step_from_json(d))
        return {'violations': [v.to_json() for v in h.violations], 'export': h.export()}
    finally:
        h.close()


def replay_check(scenario: str, seed: int, steps: int, work: str, include_known: bool = False) -> dict:
    """The same scenario and the same call sequence, run twice, give identical exports (database and audit log)."""
    first = fuzz_sequence(scenario, seed, 0, steps, os.path.join(work, 'a'), include_known=include_known, check=False)
    second = replay(scenario, first['calls'], os.path.join(work, 'b'), check=False)
    again = fuzz_sequence(scenario, seed, 0, steps, os.path.join(work, 'c'), include_known=include_known, check=False)
    a, b = first['export'], second['export']
    diff = sorted(t for t in a['tables'] if a['tables'][t] != b['tables'].get(t))
    return {'identical': a['db'] == b['db'] and a['responses'] == b['responses'], 'tables_differ': diff,
            'responses_identical': a['responses'] == b['responses'],
            'generator_deterministic': again['calls'] == first['calls'], 'steps': steps}


# ---- atomicity under injected failure -------------------------------------------------------------------------

class InjectedFault(sqlite3.OperationalError):
    pass


class FaultyConnection:
    """Wraps the sqlite3 connection of an Erp. Counts statements while armed and raises before the N-th one."""

    def __init__(self, conn: sqlite3.Connection, fail_at: int | None = None, faults_commit: bool = False,
                 fail_on: tuple[str, int] | None = None):
        """fail_at: raise before the N-th counted statement; fail_on: (text, k) raise before the k-th statement that
        contains text."""
        self._conn, self.fail_at, self.faults_commit, self.fail_on = conn, fail_at, faults_commit, fail_on
        self.seen = 0
        self.count = 0
        self.armed = False
        self.fired = None
        self.statements: list[str] = []

    def execute(self, sql, params=()):
        if self.armed:
            head = sql.lstrip().split(None, 1)[0].upper()
            if head != 'ROLLBACK' and (head != 'COMMIT' or self.faults_commit):
                self.count += 1
                self.statements.append(' '.join(sql.split())[:90])
                hit = self.count == self.fail_at
                if self.fail_on and self.fail_on[0] in sql:
                    self.seen += 1
                    hit = hit or self.seen == self.fail_on[1]
                if hit:
                    self.armed = False
                    self.fired = self.statements[-1]
                    raise InjectedFault(f'injected fault before statement {self.count}')
        return self._conn.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _prepare(h: Harness, calls: list[Call]) -> None:
    for c in calls:
        status, out = h.request(c)
        if status >= 400:
            raise RuntimeError(f'preparing {c.method} {c.path} failed: {status} {out[:300]!r}')


def atomic_recipes(h: Harness) -> list[tuple[str, list[Call], Call]]:
    """(name, preparation calls, the write call under test) for representative write calls, built from the scenario.
    Preparation runs once; the call under test runs against a fresh copy for every fault position."""
    e = h.erp
    recipes = []

    def perm(action, exclude=()):
        for (u,) in e.db.execute("SELECT DISTINCT ur.user_id FROM user_roles ur JOIN role_permissions rp ON rp.role = "
                                 "ur.role WHERE rp.action = ? AND ur.user_id IN (SELECT user_id FROM tokens) ORDER BY 1",
                                 (action,)).fetchall():
            if u not in exclude:
                return u
    sent = e.one("SELECT p.id, p.vendor FROM purchase_orders p WHERE p.status = 'sent' AND EXISTS (SELECT 1 FROM po_lines l "
                 "WHERE l.po_id = p.id AND l.sku IS NOT NULL) ORDER BY p.id")
    rcv_user, ap_user = perm('rcv.post'), perm('ap.validate')
    if sent:
        lines = []
        for pl in e.all("SELECT l.*, i.lot_controlled FROM po_lines l LEFT JOIN items i ON i.sku = l.sku WHERE l.po_id = ? "
                        "AND l.status = 'open' ORDER BY l.line", sent['id']):
            ln = {'po_line': pl['line'], 'qty_received': pl['qty'] - pl['qty_received']}
            if pl['lot_controlled']:
                ln.update({'lot': 'L-ATOM', 'expiry': add_days(e.today, 600)})
            lines.append(ln)
        receive = Call(rcv_user, 'POST', '/receipts', {'po_id': sent['id'], 'lines': lines}, 'rcv.post')
        recipes.append(('receive (rcv.post)', [], receive))
        inv_lines = [{'kind': 'item', 'po_line': ln['po_line'], 'qty': ln['qty_received'],
                      'unit_price': e.val('SELECT unit_price FROM po_lines WHERE po_id = ? AND line = ?', sent['id'],
                                          ln['po_line']) * 1.03} for ln in lines]
        inv_lines.append({'kind': 'freight', 'amount': 42.5})
        enter = Call(ap_user, 'POST', '/ap-invoices', {'vendor': sent['vendor'], 'invoice_no': 'ATOM-1',
                                                       'invoice_date': e.today, 'po_id': sent['id'], 'lines': inv_lines},
                     'ap.enter')
        recipes.append(('enter invoice (ap.enter)', [receive], enter))
        # validate needs the invoice id: the preparation creates APINV-<next>
        nxt = e.val("SELECT next FROM seq WHERE prefix = 'APINV'") or 10001
        recipes.append(('post invoice (ap.validate)', [receive, enter],
                        Call(ap_user, 'POST', f'/ap-invoices/APINV-{nxt}/validate', None, 'ap.validate')))
        nxt_rcv = e.val("SELECT next FROM seq WHERE prefix = 'RCV'") or 10001
        recipes.append(('reverse receipt (rcv.reverse)', [receive],
                        Call(rcv_user, 'POST', f'/receipts/RCV-{nxt_rcv}/reverse', {'reason': 'wrong PO'}, 'rcv.reverse')))
    prep = perm('pay.prepare')
    invs = [r['id'] for r in e.all("SELECT i.id FROM ap_invoices i JOIN vendors v ON v.id = i.vendor JOIN "
                                   "vendor_bank_accounts b ON b.id = v.remit_account AND b.status = 'verified' WHERE "
                                   "i.status = 'approved' AND v.status = 'active' AND NOT EXISTS (SELECT 1 FROM holds h "
                                   "WHERE h.doc_id = i.id AND h.released_on IS NULL) ORDER BY i.id LIMIT 3")]
    if prep and invs:
        appr = perm('pay.approve', exclude=(prep,))
        rel = perm('pay.release')
        run = f'RUN-{e.val("SELECT next FROM seq WHERE prefix = ?", "RUN") or 10001}'
        calls = [Call(prep, 'POST', '/payment-runs', {'pay_date': e.today, 'bank_account': 'OPER'})]
        calls += [Call(prep, 'POST', f'/payment-runs/{run}/invoices', {'inv_id': i}) for i in invs]
        calls += [Call(prep, 'POST', f'/payment-runs/{run}/submit'), Call(appr, 'POST', f'/payment-runs/{run}/approve', {})]
        recipes.append(('pay (pay.release)', calls, Call(rel, 'POST', f'/payment-runs/{run}/release', None, 'pay.release')))
    je_user = perm('je.create')
    if je_user:
        nxt = e.val("SELECT next FROM seq WHERE prefix = 'JE'") or 10001
        create = Call(je_user, 'POST', '/journal-entries', {'entry_date': e.today, 'memo': 'accrual', 'lines': [
            {'account': '6100', 'debit': 125.40, 'department': 'ADMIN'}, {'account': '2100', 'credit': 125.40}]})
        recipes.append(('post journal (je.post)', [create],
                        Call(je_user, 'POST', f'/journal-entries/JE-{nxt}/post', None, 'je.post')))
    closer = perm('period.close')
    if closer:
        recipes.append(('close period (period.close)', [],
                        Call(closer, 'POST', f'/periods/{e.today[:7]}/close', None, 'period.close')))
    return recipes


def _compare_files(base: str, trial: str) -> list[str]:
    """Tables that differ between two database files (audit_events and its sequence row compared separately)."""
    c = sqlite3.connect(f'file:{base}?mode=ro', uri=True)
    try:
        c.execute(f"ATTACH DATABASE 'file:{trial}?mode=ro' AS t")
        out = []
        for (tbl,) in c.execute("SELECT name FROM main.sqlite_master WHERE type = 'table' ORDER BY name").fetchall():
            if tbl == 'audit_events':
                continue
            where = " WHERE name != 'audit_events'" if tbl == 'sqlite_sequence' else ''
            a = c.execute(f'SELECT COUNT(*) FROM (SELECT * FROM main."{tbl}"{where} EXCEPT SELECT * FROM t."{tbl}"{where})'
                          ).fetchone()[0]
            b = c.execute(f'SELECT COUNT(*) FROM (SELECT * FROM t."{tbl}"{where} EXCEPT SELECT * FROM main."{tbl}"{where})'
                          ).fetchone()[0]
            if a or b:
                out.append(f'{tbl} (-{a} +{b})')
        gone = c.execute('SELECT COUNT(*) FROM (SELECT * FROM main.audit_events EXCEPT SELECT * FROM t.audit_events)'
                         ).fetchone()[0]
        if gone:
            out.append(f'audit_events ({gone} earlier rows changed)')
        return out
    finally:
        c.close()


def atomicity_sweep(scenario: str, work: str, names: list[str] | None = None, faults_commit: bool = False,
                    max_points: int | None = None) -> list[dict]:
    """For each representative write call: count its statements, then for every N make the N-th statement raise and
    check the database is row-identical to before the call, the connection is not left in a transaction, the error
    is audited, and the same call then succeeds."""
    os.makedirs(work, exist_ok=True)
    setup = Harness(scenario, os.path.join(work, 'setup'), check=False)
    world = setup.erp.world
    tokens = setup.tokens
    try:
        recipes = [r for r in atomic_recipes(setup) if names is None or any(n in r[0] for n in names)]
    finally:
        setup.close()
    results = []
    for name, prep_calls, call in recipes:
        slug = ''.join(ch if ch.isalnum() else '_' for ch in name)[:40]
        rdir = os.path.join(work, slug)
        h = Harness(scenario, rdir, check=False)
        try:
            _prepare(h, prep_calls)
            h.erp.db.execute('PRAGMA wal_checkpoint')
        finally:
            h.close()
        base = os.path.join(rdir, 'base.db')
        copy_db(os.path.join(rdir, 'live.db'), base)
        trial = os.path.join(rdir, 'trial.db')

        def run(fail_at):
            copy_db(base, trial)
            erp = Erp(trial, world=world)
            fc = FaultyConnection(erp.db, fail_at, faults_commit)
            erp.db = fc
            hh = Harness.__new__(Harness)
            hh.erp, hh.tokens = erp, tokens
            fc.armed = True
            try:
                status, out = hh.request(call)
            except Exception as ex:                         # handle() must never raise
                status, out = 599, f'unhandled {type(ex).__name__}: {ex}'.encode()
            fc.armed = False
            return erp, fc, status, out
        erp, fc, ref_status, ref_out = run(None)
        n_statements = fc.count
        stmts = list(fc.statements)
        erp.close()
        res = {'call': name, 'path': f'{call.method} {call.path}', 'reference_status': ref_status,
               'statements': n_statements, 'points': 0, 'failures': []}
        if ref_status >= 400:
            res['failures'].append({'at': None, 'problem': f'the call itself fails without a fault: {ref_status} '
                                                           f'{ref_out[:300]!r}'})
            results.append(res)
            continue
        points = list(range(1, n_statements + 1))
        if max_points and len(points) > max_points:
            step = len(points) / max_points
            points = sorted({points[int(i * step)] for i in range(max_points)} | {points[-1]})
        for n in points:
            erp, fc, status, out = run(n)
            problems = []
            if fc.fired is None:
                problems.append('fault did not fire')
            if status < 500:
                problems.append(f'status {status} after an injected fault')
            if status == 599:
                problems.append(out.decode('utf-8', 'replace'))
            open_tx = erp.db.in_transaction
            if open_tx:
                problems.append('connection left inside a transaction')
                try:
                    erp.db.execute('ROLLBACK')
                except sqlite3.Error:
                    pass
            erp.close()
            diff = _compare_files(base, trial)
            if diff:
                problems.append('database changed: ' + ', '.join(diff))
            c = sqlite3.connect(f'file:{trial}?mode=ro', uri=True)
            base_max = sqlite3.connect(f'file:{base}?mode=ro', uri=True).execute(
                'SELECT COALESCE(MAX(id), 0) FROM audit_events').fetchone()[0]
            new = c.execute('SELECT outcome FROM audit_events WHERE id > ?', (base_max,)).fetchall()
            c.close()
            if [r[0] for r in new] != ['error']:
                problems.append(f'audit rows after the fault: {[r[0] for r in new]} (want one error row)')
            # the same call succeeds afterwards on the same file (a retry is safe)
            erp2 = Erp(trial, world=world)
            hh = Harness.__new__(Harness)
            hh.erp, hh.tokens = erp2, tokens
            st2, _ = hh.request(call)
            erp2.close()
            if st2 != ref_status:
                problems.append(f'retry after the fault answered {st2}, want {ref_status}')
            res['points'] += 1
            if problems:
                res['failures'].append({'at': n, 'statement': fc.fired or (stmts[n - 1] if n <= len(stmts) else None),
                                        'problem': '; '.join(problems)})
        results.append(res)
    return results


# ---- crash durability (slow) -----------------------------------------------------------------------------------

def crash_test(scenario: str, seed: int, kills: int, work: str) -> list[dict]:
    """Run the real server as a subprocess, drive writes over HTTP, SIGKILL it at a random moment, reopen the file,
    and check integrity, the ledger invariants, and that every acknowledged write is present."""
    from procgen.episode import Server
    rng = random.Random(f'crash:{seed}')
    out = []
    for k in range(kills):
        kdir = os.path.join(work, f'kill-{k}')
        os.makedirs(kdir, exist_ok=True)
        db = os.path.join(kdir, 'company.db')
        copy_db(os.path.join(scenario, 'scenario.db'), db)
        srv = Server(db, os.path.join(scenario, 'world.json'), 'crash-token', os.path.join(kdir, 'erp.log'))
        reader = Erp(db)
        tokens = {r['user_id']: r['secret'] for r in reader.all('SELECT user_id, secret FROM tokens')}
        g = Gen(reader, random.Random(f'{seed}:crash:{k}'), f'c{k}', max_days=0)
        acked, stop = [], threading.Event()
        errors = []

        def drive():
            import urllib.error
            import urllib.request
            i = 0
            while not stop.is_set():
                try:
                    c = g.next(i)
                except Exception as ex:                 # the reader saw a half-written file: that is fine here
                    errors.append(f'generator: {ex}')
                    time.sleep(0.01)
                    continue
                i += 1
                if isinstance(c, Advance) or c.method == 'GET':
                    continue
                req = urllib.request.Request(srv.url + c.path, method=c.method,
                                             data=c.raw if c.raw is not None else json.dumps(c.body or {}).encode())
                tok = c.token if c.token is not None else tokens.get(c.user, '')
                req.add_header('Authorization', f'Bearer {tok}')
                req.add_header('Content-Type', 'application/json')
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        data = json.loads(r.read())['data']
                        acked.append((c.path, data.get('id') if isinstance(data, dict) else None))
                except urllib.error.HTTPError:
                    pass
                except OSError:
                    return
        t = threading.Thread(target=drive, daemon=True)
        t.start()
        time.sleep(rng.uniform(0.3, 1.5))
        if k % 2:                                  # odd kills: wait until a write transaction has dirtied the file
            deadline = time.time() + 10
            while not os.path.exists(db + '-journal') and time.time() < deadline:
                pass
        os.killpg(srv.proc.pid, signal.SIGKILL)
        srv.proc.wait()
        stop.set()
        t.join(timeout=15)
        reader.close()
        hot = os.path.exists(db + '-journal') and os.path.getsize(db + '-journal') > 0
        c = sqlite3.connect(db)
        integrity = c.execute('PRAGMA integrity_check').fetchone()[0]
        c.close()
        erp = Erp(db)
        problems = []
        if integrity != 'ok':
            problems.append(f'integrity_check: {integrity}')
        if not reports.trial_balance(erp)['balanced']:
            problems.append('trial balance does not balance')
        ties = reports.control_ties(erp)
        if not ties['all_tie']:
            problems.append('control accounts do not tie: ' + json.dumps(
                {k: v['difference_cents'] for k, v in ties['controls'].items() if v['difference_cents']}))
        for name, sql in CONSISTENCY.items():
            bad = [r[0] for r in erp.db.execute(sql.format(s='main')).fetchall()]
            if bad:
                problems.append(f'{name}: {bad[:3]}')
        created = [(p, i) for p, i in acked if i and p.count('/') == 1]
        for p, i in created:
            table = {'/receipts': 'receipts', '/ap-invoices': 'ap_invoices', '/journal-entries': 'journal_entries',
                     '/purchase-orders': 'purchase_orders', '/payment-runs': 'payment_runs',
                     '/requisitions': 'requisitions', '/sales-orders': 'sales_orders', '/work-orders': 'work_orders',
                     '/cash-receipts': 'cash_receipts'}.get(p)
            if table and not erp.val(f'SELECT 1 FROM {table} WHERE id = ?', i):
                problems.append(f'acknowledged {p} {i} is missing after the crash')
        n_api = erp.val("SELECT COUNT(*) FROM audit_events WHERE channel = 'api' AND method != 'GET' AND outcome = 'ok'")
        if n_api < len(acked):
            problems.append(f'{len(acked)} writes acknowledged but only {n_api} ok write rows in the audit log')
        erp.close()
        # the server comes back on the recovered file and takes a write
        srv2 = Server(db, os.path.join(scenario, 'world.json'), 'crash-token', os.path.join(kdir, 'erp2.log'))
        try:
            import urllib.request
            u = next(iter(sorted(tokens)))
            req = urllib.request.Request(srv2.url + '/outbox', method='POST', data=json.dumps(
                {'to': 'x@example.com', 'subject': 'after crash'}).encode())
            req.add_header('Authorization', f'Bearer {tokens[u]}')
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status != 201:
                    problems.append(f'write after restart answered {r.status}')
        except Exception as ex:
            problems.append(f'server did not take a write after the crash: {ex}')
        finally:
            srv2.stop()
        out.append({'kill': k, 'acknowledged_writes': len(acked), 'hot_journal': hot, 'integrity': integrity,
                    'problems': problems})
    return out


# ============================================================================================ CLI

def summarize(runs: list[dict]) -> dict:
    kinds: dict[str, dict] = {}
    viol: dict[str, dict] = {}
    for r in runs:
        for k, sts in r['kinds'].items():
            d = kinds.setdefault(k, {})
            for s, n in sts.items():
                d[s] = d.get(s, 0) + n
        for v in r['violations']:
            key = f'{v["invariant"]}: {(v.get("call") or {}).get("kind", "")}: ' + v['detail'][:80]
            e = viol.setdefault(key, {'count': 0, 'first': dict(v, sequence=r['sequence'])})
            e['count'] += 1
    return {'calls_by_kind': dict(sorted(kinds.items())), 'violations': viol}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--task', default='payment-run', help='process task whose generator builds the scenario')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--steps', type=int, default=200, help='calls per sequence')
    ap.add_argument('--sequences', type=int, default=1)
    ap.add_argument('--malformed', action='store_true', help='also send wrongly typed input (finds 500s)')
    ap.add_argument('--include-known', action='store_true', help='let the generator trigger KNOWN_BUGS too')
    ap.add_argument('--atomicity', action='store_true', help='fault-injection sweep over representative writes')
    ap.add_argument('--fault-commit', action='store_true', help='the sweep also fails COMMIT itself')
    ap.add_argument('--replay-check', action='store_true', help='deterministic replay of one sequence')
    ap.add_argument('--crash', type=int, default=0, metavar='KILLS', help='SIGKILL the server this many times')
    ap.add_argument('--replay-file', help='replay a JSON list of calls (from --save-calls) and check invariants')
    ap.add_argument('--save-calls', help='write every sequence\'s calls to this JSON file')
    ap.add_argument('--work', help='working directory (default: a temporary one)')
    ap.add_argument('--json', action='store_true', help='print the full result as JSON')
    a = ap.parse_args(argv)
    work = a.work or scratch_dir()
    scenario = ensure_scenario(a.task, a.seed)
    result: dict = {'task': a.task, 'seed': a.seed, 'scenario': scenario}
    failed = False
    if a.replay_file:
        calls = read_json(a.replay_file)
        calls = calls[0]['calls'] if calls and isinstance(calls[0], dict) and 'calls' in calls[0] else calls
        r = replay(scenario, calls, os.path.join(work, 'replay'))
        result['replay'] = r
        failed |= bool(r['violations'])
    elif not (a.atomicity or a.replay_check or a.crash):
        runs = []
        t0 = time.time()
        for i in range(a.sequences):
            r = fuzz_sequence(scenario, a.seed, i, a.steps, work, a.malformed, a.include_known)
            runs.append(r)
            print(f'sequence {i}: {a.steps} calls in {r["seconds"]}s, {len(r["violations"])} violations',
                  file=sys.stderr)
        result['fuzz'] = {'sequences': a.sequences, 'steps': a.steps, 'seconds': round(time.time() - t0, 1),
                          **summarize(runs)}
        if a.save_calls:
            with open(a.save_calls, 'w', encoding='utf-8') as f:
                json.dump([{'sequence': r['sequence'], 'calls': r['calls']} for r in runs], f, indent=1)
        failed |= bool(result['fuzz']['violations'])
    if a.atomicity:
        res = atomicity_sweep(scenario, os.path.join(work, 'atomicity'), faults_commit=a.fault_commit)
        result['atomicity'] = res
        failed |= any(r['failures'] for r in res)
    if a.replay_check:
        res = replay_check(scenario, a.seed, a.steps, os.path.join(work, 'replay-check'), a.include_known)
        result['replay_check'] = res
        failed |= not (res['identical'] and res['generator_deterministic'])
    if a.crash:
        res = crash_test(scenario, a.seed, a.crash, os.path.join(work, 'crash'))
        result['crash'] = res
        failed |= any(r['problems'] for r in res)
    if a.json:
        print(json.dumps(result, indent=1, default=str))
    else:
        if 'fuzz' in result:
            f = result['fuzz']
            print(f'{f["sequences"]} sequences x {f["steps"]} calls in {f["seconds"]}s')
            for k, sts in f['calls_by_kind'].items():
                print(f'  {k:40s} {sts}')
            print(f'{len(f["violations"])} distinct violations')
            for key, v in f['violations'].items():
                print(f'  [{v["count"]}x] {key}\n      first: seq {v["first"]["sequence"]} step {v["first"]["step"]}: '
                      f'{json.dumps(v["first"].get("call"))[:300]}\n      {v["first"]["detail"][:400]}')
        if 'replay' in result:
            print(json.dumps(result['replay']['violations'], indent=1))
        for r in result.get('atomicity', []):
            print(f'atomicity {r["call"]:34s} {r["statements"]:4d} statements, {r["points"]:4d} faults injected, '
                  f'{len(r["failures"])} failures')
            for x in r['failures'][:5]:
                print(f'    at {x["at"]}: {x.get("statement")}: {x["problem"][:300]}')
        if 'replay_check' in result:
            print('replay:', json.dumps(result['replay_check']))
        for r in result.get('crash', []):
            print(f'crash {r["kill"]}: {r["acknowledged_writes"]} writes acknowledged, killed mid-transaction: '
              f'{r["hot_journal"]}, integrity {r["integrity"]}, '
                  f'problems: {r["problems"] or "none"}')
    if not a.work:
        shutil.rmtree(work, ignore_errors=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
