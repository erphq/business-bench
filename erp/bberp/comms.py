"""Inboxes, the outbox, escalations to colleagues, and phone calls.

Inboxes are shared queues (ap, receiving, purchasing, sales, general, ...); a user reads a box when one of their
roles carries the permission `box.<name>`. Messages become visible on their `visible_on` business date.
Counterparties never read free text: they react to structured actions only (see sim.py). A phone call returns
the scenario's scripted answer for the number dialled, and records whether that number is the one on file.
"""
from __future__ import annotations

import re

from .core import Ctx, Erp, forbidden, invalid, not_found

DISPOSITIONS = ('processed', 'duplicate', 'rejected', 'escalated', 'suspicious', 'no_action', 'forwarded')
ESCALATION_REASONS = ('price_variance', 'quantity_variance', 'no_receipt', 'duplicate', 'fraud_suspected', 'budget',
                      'over_limit', 'policy_exception', 'credit', 'lead_time', 'master_data', 'approval', 'other')


def boxes(ctx: Ctx) -> list[str]:
    return sorted(p.split('.', 1)[1] for p in ctx.permissions if p.startswith('box.'))


def _can_read_box(ctx: Ctx, box: str) -> bool:
    return ctx.can(f'box.{box}') or ctx.can('box.*')


def list_messages(erp: Erp, ctx: Ctx, box: str | None = None, unread: bool = False, direction: str = 'in') -> list[dict]:
    readable = boxes(ctx) if not ctx.can('box.*') else [r['box'] for r in erp.all('SELECT DISTINCT box FROM messages')]
    if box:
        if not _can_read_box(ctx, box):
            raise forbidden(f'{ctx.user} cannot read the {box} box')
        readable = [box]
    if not readable:
        return []
    rows = erp.all(
        f'SELECT m.id, m.box, m.from_name, m.from_addr, m.to_addr, m.subject, m.sent_on, m.disposition, '
        f'm.disposition_ref, EXISTS(SELECT 1 FROM message_reads r WHERE r.msg_id = m.id AND r.user_id = ?) AS read, '
        f'(SELECT COUNT(*) FROM message_attachments a WHERE a.msg_id = m.id) AS attachments '
        f'FROM messages m WHERE m.direction = ? AND m.visible_on <= ? AND m.box IN ({",".join("?" * len(readable))}) '
        f'ORDER BY m.visible_on, m.id', ctx.user, direction, erp.today, *readable)
    for r in rows:
        r['read'] = bool(r['read'])
    return [r for r in rows if not (unread and r['read'])]


def _visible(erp: Erp, ctx: Ctx, msg_id: str) -> dict:
    m = erp.one('SELECT * FROM messages WHERE id = ?', msg_id)
    if m is None or m['visible_on'] > erp.today:
        raise not_found('message', msg_id)
    if m['direction'] == 'in' and not _can_read_box(ctx, m['box']):
        raise forbidden(f'{ctx.user} cannot read the {m["box"]} box')
    if m['direction'] == 'out' and m['created_by'] != ctx.user and not ctx.can('box.*'):
        raise forbidden('that message was sent by someone else')
    return m


def read_message(erp: Erp, ctx: Ctx, msg_id: str) -> dict:
    m = _visible(erp, ctx, msg_id)
    m['attachments'] = erp.all('SELECT n, name, content_type, LENGTH(data) AS bytes FROM message_attachments '
                               'WHERE msg_id = ? ORDER BY n', msg_id)
    erp.run('INSERT OR IGNORE INTO message_reads (msg_id, user_id) VALUES (?, ?)', msg_id, ctx.user)
    return m


def attachment(erp: Erp, ctx: Ctx, msg_id: str, n: int) -> dict:
    _visible(erp, ctx, msg_id)
    a = erp.one('SELECT * FROM message_attachments WHERE msg_id = ? AND n = ?', msg_id, n)
    if a is None:
        raise not_found('attachment', f'{msg_id}/{n}')
    return a


def dispose(erp: Erp, ctx: Ctx, msg_id: str, disposition: str, ref: str | None = None, note: str | None = None) -> None:
    ctx.require('msg.dispose')
    m = _visible(erp, ctx, msg_id)
    if m['direction'] != 'in':
        raise invalid('only incoming messages take a disposition')
    if disposition not in DISPOSITIONS:
        raise invalid(f'disposition must be one of {", ".join(DISPOSITIONS)}')
    erp.touch('message', msg_id)
    erp.update('messages', {'id': msg_id}, {'disposition': disposition, 'disposition_ref': ref,
                                            'disposition_note': note, 'disposition_by': ctx.user,
                                            'disposition_on': erp.today})


def send(erp: Erp, ctx: Ctx, to: str, subject: str, body: str) -> str:
    ctx.require('msg.send')
    if not to or not subject:
        raise invalid('give to and subject')
    me = erp.one('SELECT * FROM users WHERE id = ?', ctx.user)
    mid = erp.next_id('MSG')
    erp.insert('messages', {'id': mid, 'box': 'outbox', 'direction': 'out', 'from_name': me['name'],
                            'from_addr': me['email'], 'to_addr': to, 'subject': subject, 'body': body or '',
                            'sent_on': erp.today, 'visible_on': erp.today, 'created_by': ctx.user})
    erp.touch('message', mid, created=True)
    return mid


def deliver(erp: Erp, box: str, subject: str, body: str, from_name: str, from_addr: str, day: str,
            to_addr: str | None = None, reply_to: str | None = None, attachments: list[tuple] = (),
            created_by: str | None = None) -> str:
    """Put a message in a box (used by the generator and the counterparties)."""
    mid = erp.next_id('MSG')
    erp.insert('messages', {'id': mid, 'box': box, 'direction': 'in', 'from_name': from_name, 'from_addr': from_addr,
                            'reply_to': reply_to, 'to_addr': to_addr, 'subject': subject, 'body': body,
                            'sent_on': day, 'visible_on': day, 'created_by': created_by})
    for n, (name, ctype, data) in enumerate(attachments, 1):
        erp.insert('message_attachments', {'msg_id': mid, 'n': n, 'name': name, 'content_type': ctype, 'data': data})
    return mid


def escalate(erp: Erp, ctx: Ctx, record_type: str, record_id: str, to_user: str, reason: str,
             note: str | None = None) -> str:
    ctx.require('escalate')
    u = erp.one('SELECT * FROM users WHERE id = ?', to_user)
    if u is None or not u['active'] or u['kind'] != 'staff':
        raise not_found('user', to_user)
    if reason not in ESCALATION_REASONS:
        raise invalid(f'reason must be one of {", ".join(ESCALATION_REASONS)}')
    if not record_type or not record_id:
        raise invalid('name the record: record_type and record_id')
    eid = erp.next_id('ESC')
    erp.insert('escalations', {'id': eid, 'record_type': record_type, 'record_id': record_id, 'to_user': to_user,
                               'reason': reason, 'note': note, 'from_user': ctx.user, 'created_on': erp.today,
                               'status': 'open'})
    erp.touch('escalation', eid, created=True)
    return eid


def answer_escalation(erp: Erp, ctx: Ctx, eid: str, decision: str, response: str) -> None:
    e = erp.one('SELECT * FROM escalations WHERE id = ?', eid)
    if e is None:
        raise not_found('escalation', eid)
    if e['to_user'] != ctx.user:
        raise forbidden(f'{eid} is addressed to {e["to_user"]}')
    erp.touch('escalation', eid)
    erp.update('escalations', {'id': eid}, {'status': 'answered', 'decision': decision, 'response': response,
                                            'responded_on': erp.today})


def _digits(s: str | None) -> str:
    return re.sub(r'\D', '', s or '')[-10:]


def on_file_number(erp: Erp, party_type: str, party_id: str) -> str | None:
    table = {'vendor': 'vendors', 'customer': 'customers', 'user': 'users'}.get(party_type)
    if table is None:
        raise invalid('party_type is vendor, customer or user')
    row = erp.one(f'SELECT phone FROM {table} WHERE id = ?', party_id)
    if row is None:
        raise not_found(party_type, party_id)
    return row['phone']


def call(erp: Erp, ctx: Ctx, party_type: str, party_id: str, number: str | None = None) -> dict:
    """Phone a vendor, customer or colleague. `number` defaults to the one on file."""
    ctx.require('call')
    on_file = on_file_number(erp, party_type, party_id)
    dialled = number or on_file
    if not dialled:
        raise invalid(f'{party_id} has no number on file; give one')
    source = 'on_file' if _digits(dialled) == _digits(on_file) else 'other'
    transcript = 'The number rang out. Nobody answered.'
    for s in erp.world.get('calls', []):
        if s.get('party_type') == party_type and s.get('party_id') == party_id and \
                _digits(s.get('number')) == _digits(dialled) and s.get('from', '') <= erp.today:
            transcript = s['transcript']
    cid = erp.next_id('CALL')
    erp.insert('calls', {'id': cid, 'caller': ctx.user, 'party_type': party_type, 'party_id': party_id,
                         'number': dialled, 'number_source': source, 'call_date': erp.today, 'transcript': transcript})
    erp.touch('call', cid, created=True)
    return {'id': cid, 'number': dialled, 'number_source': source, 'transcript': transcript}
