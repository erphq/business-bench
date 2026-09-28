"""Counterparties and the business clock.

`advance(erp, to)` moves the clock one day at a time. On each workday the actors run in a fixed order: bank,
scheduled receipts, vendors (acknowledge, ship, invoice, answer requests), approvers, managers (escalations, journal
entries, payment runs). Every action goes through the same service functions as the API, under the actor's own user,
and is written to the audit log with channel 'sim'. Behaviour comes from the scenario's world file (`erp.world`);
nothing is random at run time, so the same agent actions always produce the same counterparty responses.

World file shape (all keys optional):
  agent_users: [user ids the agent signs in as; the simulator never acts for them]
  actors: {vendor: user, bank: user, mail: user}
  vendor_default: vendor profile applied under every vendor's own profile
  vendors: {vendor id: profile}
    profile: ack_delay (workdays), lead_time_days, moq {sku: qty}, ship {sku|*: ship rule}, invoice {...},
             requests {expedite: {accept, best_date}, dispute: {accept, answer_delay}, ...}, contact {name, email}
    ship rule: lead_time_days, over_pct, round_to, fill, backorder_days, substitute, lots [{lot, share, expiry}]
    invoice: delay (workdays), prefix, start, prices {sku: unit price}, freight, duplicate {delay, number}
  approvers: {user: {default: approve|reject|none, decisions: {doc id: {decision, reason, to}}}}
  escalations: [{record_id, to, reason?, decision, response, actions: [{kind: release_hold, note}]}]
  journal_approver: {user, require_support: bool}
  payment_run_approver: {user, release: bool}
  calls: [{party_type, party_id, number, transcript, from?}]
  receipts: [{day, user, po_id, packing_slip?, lines: [{po_line, qty_received}]}]
    deliveries a colleague receives on that day (background operations between turns)
  receipt_reversals: [{day, user, receipt, reason}]
    receipts a colleague reverses on that day, for example a receiving error found after posting (a fact that
    changes between turns); absent, nothing is reversed
"""
from __future__ import annotations

import json

from . import comms, ledger, payables, purchasing, receiving
from .core import Erp, ErpError, add_days, ext_cents, invalid, load_ctx, q4, user_on_leave
from .pdf import business_document


# ------------------------------------------------------------------------------------------- plumbing

def _log(erp: Erp, actor: str, kind: str, ref: str, payload: dict) -> None:
    erp.insert('sim_log', {'day': erp.today, 'actor': actor, 'kind': kind, 'ref': ref,
                           'payload': json.dumps(payload, sort_keys=True)})


def _logged(erp: Erp, kind: str, ref: str) -> list[dict]:
    return [dict(r, payload=json.loads(r['payload'])) for r in
            erp.all('SELECT * FROM sim_log WHERE kind = ? AND ref = ? ORDER BY id', kind, ref)]


def act(erp: Erp, user: str, action: str, otype: str | None, oid: str | None, fn, events: list) -> object:
    """Run one counterparty action in its own transaction and audit it like an API call."""
    ctx = load_ctx(erp, user, channel='sim')
    try:
        with erp.tx():
            erp.begin_audit()
            try:
                result = fn(ctx)
            finally:
                before, after = erp.end_audit()
            erp.audit(ctx, method='SIM', path=action, action=action, object_type=otype, object_id=oid,
                      before=before or None, after=after or None, outcome='ok')
        events.append({'day': erp.today, 'actor': user, 'action': action, 'object': oid})
        return result
    except ErpError as e:
        with erp.tx():
            erp.audit(ctx, method='SIM', path=action, action=action, object_type=otype, object_id=oid,
                      outcome='refused', error_code=e.code, request={'detail': e.message})
        events.append({'day': erp.today, 'actor': user, 'action': action, 'object': oid, 'refused': e.code})
        return None


def _agent_users(erp: Erp) -> set[str]:
    return set(erp.world.get('agent_users', []))


def _actor(erp: Erp, role: str) -> str:
    return erp.world.get('actors', {}).get(role, f'sys-{role}')


def vendor_profile(erp: Erp, vendor: str) -> dict:
    base = dict(erp.world.get('vendor_default', {}))
    own = erp.world.get('vendors', {}).get(vendor, {})
    out = {**base, **own}
    for k in ('ship', 'invoice', 'requests', 'moq', 'contact'):
        out[k] = {**base.get(k, {}), **own.get(k, {})}
    return out


def ship_rule(vp: dict, sku: str) -> dict:
    return {**vp['ship'].get('*', {}), **vp['ship'].get(sku, {})}


def _vendor_contact(erp: Erp, vendor: dict, vp: dict) -> tuple[str, str]:
    c = vp.get('contact') or {}
    return c.get('name') or vendor['name'], c.get('email') or vendor['email'] or f'orders@{vendor["id"].lower()}.example'


def _letterhead(vendor: dict) -> list[str]:
    """Address block under the vendor-name heading."""
    return [*(vendor['address'] or '').split('\n'), f'Phone {vendor["phone"] or ""}'.strip()]


# ------------------------------------------------------------------------------------------- vendors

def vendor_acks(erp: Erp, events: list) -> None:
    for po in erp.all("SELECT * FROM purchase_orders WHERE status IN ('sent', 'partially_received') ORDER BY id"):
        if erp.val('SELECT 1 FROM po_acknowledgements WHERE po_id = ?', po['id']):
            continue
        vp = vendor_profile(erp, po['vendor'])
        if erp.add_workdays(po['sent_on'], int(vp.get('ack_delay', 1))) > erp.today:
            continue
        vendor = erp.one('SELECT * FROM vendors WHERE id = ?', po['vendor'])
        lines, body = [], []
        for pl in erp.all("SELECT * FROM po_lines WHERE po_id = ? AND status = 'open' ORDER BY line", po['id']):
            rule = ship_rule(vp, pl['sku'])
            moq = vp['moq'].get(pl['sku'])
            if moq and pl['qty'] < moq:
                note = f'below our minimum order quantity of {moq:g}'
                lines.append({'line': pl['line'], 'status': 'rejected', 'note': note})
                body.append(f'Line {pl["line"]} {label}: cannot accept, {note}.')
                continue
            lead = int(rule.get('lead_time_days', vp.get('lead_time_days',
                       erp.val('SELECT lead_time_days FROM items WHERE sku = ?', pl['sku']) or 5)))
            label = pl['sku'] or pl['description']
            earliest = erp.add_workdays(po['sent_on'], lead)
            confirmed = earliest if vp.get('ship_early') else max(pl['need_date'], earliest)
            if not erp.is_workday(confirmed):
                confirmed = erp.add_workdays(confirmed, 1)
            lines.append({'line': pl['line'], 'status': 'accepted', 'confirmed_date': confirmed,
                          'confirmed_price': pl['unit_price']})
            body.append(f'Line {pl["line"]} {label} qty {pl["qty"]:g} at {pl["unit_price"]:.4f}: '
                        f'confirmed for delivery {confirmed}.')
        if not lines:
            continue
        name, addr = _vendor_contact(erp, vendor, vp)

        def do(ctx, po=po, lines=lines, body=body, name=name, addr=addr):
            purchasing.acknowledge(erp, ctx, po['id'], lines)
            comms.deliver(erp, 'purchasing', f'Order acknowledgement {po["id"]}',
                          f'Thank you for purchase order {po["id"]}.\n\n' + '\n'.join(body) + f'\n\n{name}',
                          name, addr, erp.today, created_by=ctx.user)
        act(erp, _actor(erp, 'vendor'), 'vendor.acknowledge', 'purchase_order', po['id'], do, events)


def _ship_qty(rule: dict, remaining: float) -> tuple[float, float]:
    """(quantity shipped now, quantity backordered)."""
    fill = float(rule.get('fill', 1.0))
    now = q4(remaining * fill)
    back = q4(remaining - now)
    if rule.get('over_pct') and not back:
        now = q4(now * (1 + float(rule['over_pct']) / 100))
    if rule.get('round_to'):
        step = float(rule['round_to'])
        now = q4(round(now / step) * step)
    return now, back


def vendor_shipments(erp: Erp, events: list) -> None:
    today = erp.today
    due: dict[str, list] = {}
    for pl in erp.all("SELECT l.*, p.vendor, p.ship_to FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id "
                      "WHERE p.status IN ('sent', 'partially_received') AND l.status = 'open' "
                      "AND l.confirmed_date IS NOT NULL ORDER BY l.po_id, l.line"):
        ref = f'{pl["po_id"]}/{pl["line"]}'
        shipped = sum(s['payload']['qty'] for s in _logged(erp, 'ship_line', ref))
        backorders = [b for b in _logged(erp, 'backorder', ref)]
        pending_back = backorders[-1]['payload'] if backorders and not backorders[-1]['payload'].get('done') else None
        if shipped == 0 and pl['confirmed_date'] <= today:
            due.setdefault(pl['po_id'], []).append((pl, pl['qty'], False))
        elif pending_back and pending_back['date'] <= today:
            due.setdefault(pl['po_id'], []).append((pl, pending_back['qty'], True))
    for po_id, items in sorted(due.items()):
        po = erp.one('SELECT * FROM purchase_orders WHERE id = ?', po_id)
        vendor = erp.one('SELECT * FROM vendors WHERE id = ?', po['vendor'])
        vp = vendor_profile(erp, po['vendor'])
        slip_no = f'PS-{po_id.split("-")[-1]}-{len(_logged(erp, "packing_slip", po_id)) + 1}'
        rows, shipped_lines = [], []
        for pl, qty, is_back in items:
            rule = ship_rule(vp, pl['sku'] or '')
            now, back = (qty, 0.0) if is_back else _ship_qty(rule, qty)
            sku = rule.get('substitute') or pl['sku']
            desc = (erp.val('SELECT name FROM items WHERE sku = ?', sku) if sku else pl['description']) or ''
            lots = []
            if rule.get('lots'):
                left = now
                for i, l in enumerate(rule['lots']):
                    q = left if i == len(rule['lots']) - 1 else q4(round(now * float(l['share'])))
                    left = q4(left - q)
                    lots.append({'lot': l['lot'], 'qty': q, 'expiry': l.get('expiry')})
            elif sku and erp.val('SELECT lot_controlled FROM items WHERE sku = ?', sku):
                lots.append({'lot': f'{vendor["id"][-3:]}{po_id[-4:]}{pl["line"]}', 'qty': now,
                             'expiry': add_days(erp.today, 720)})
            note = f'substitute for {pl["sku"]}' if sku != pl['sku'] else ''
            code = sku or 'MISC'
            ln = str(pl['line'])
            if lots:
                for l in lots:
                    rows.append([ln, code, desc[:26], f'{l["qty"]:g}', l['lot'], l['expiry'] or '', note])
            else:
                rows.append([ln, code, desc[:26], f'{now:g}', '', '', note])
            if back:
                rows.append([ln, pl['sku'] or 'MISC', 'BACKORDERED', f'{back:g}', '', '',
                             f'ships {erp.add_workdays(today, int(rule.get("backorder_days", 5)))}'])
            shipped_lines.append((pl, sku, now, lots, back, rule))
        pdf = business_document(
            'PACKING SLIP', _letterhead(vendor),
            [('Slip no.', slip_no), ('Ship date', today), ('Your PO', po_id), ('Ship to', po['ship_to'])],
            [('PO line', 54), ('Item', 92), ('Description', 170), ('Qty', 300), ('Lot', 340), ('Expiry', 395),
             ('Note', 455)], rows,
            notes=['Please report any discrepancy within 48 hours.'], heading=vendor['name'])
        name, addr = _vendor_contact(erp, vendor, vp)

        def do(ctx, po=po, shipped_lines=shipped_lines, slip_no=slip_no, pdf=pdf, name=name, addr=addr):
            for pl, sku, now, lots, back, rule in shipped_lines:
                ref = f'{pl["po_id"]}/{pl["line"]}'
                _log(erp, ctx.user, 'ship_line', ref, {'qty': now, 'sku': sku, 'lots': lots, 'slip': slip_no,
                                                       'ordered_sku': pl['sku']})
                prev = _logged(erp, 'backorder', ref)
                if prev and not prev[-1]['payload'].get('done'):
                    _log(erp, ctx.user, 'backorder', ref, {**prev[-1]['payload'], 'done': True})
                if back:
                    _log(erp, ctx.user, 'backorder', ref, {'qty': back, 'date': erp.add_workdays(
                        erp.today, int(rule.get('backorder_days', 5)))})
            _log(erp, ctx.user, 'packing_slip', po['id'], {'slip': slip_no, 'day': erp.today})
            comms.deliver(erp, 'receiving', f'Delivery {slip_no} for {po["id"]}',
                          f'Delivered today against {po["id"]}. Packing slip attached.\n\n{name}', name, addr,
                          erp.today, attachments=[(f'{slip_no}.pdf', 'application/pdf', pdf)], created_by=ctx.user)
        act(erp, _actor(erp, 'vendor'), 'vendor.ship', 'purchase_order', po_id, do, events)


def _invoice_pdf(vendor: dict, number: str, day: str, po_id: str, lines: list[dict], freight: float,
                 terms: str | None) -> bytes:
    rows, total = [], 0
    for l in lines:
        amt = ext_cents(l['qty'], l['unit_price'])
        total += amt
        p = l['unit_price']
        rows.append([str(l['po_line']), l['sku'] or 'MISC', l['description'][:30], f'{l["qty"]:g}',
                     f'{p:.2f}' if round(p, 2) == p else f'{p:.4f}', f'{amt / 100:,.2f}'])
    totals = [('Subtotal', f'{total / 100:,.2f}')]
    if freight:
        totals.append(('Freight', f'{freight:,.2f}'))
        total += round(freight * 100)
    totals.append(('TOTAL DUE', f'{total / 100:,.2f}'))
    return business_document(
        'INVOICE', _letterhead(vendor),
        [('Invoice no.', number), ('Invoice date', day), ('Your PO', po_id), ('Terms', terms or 'Net 30')],
        [('PO line', 54), ('Item', 100), ('Description', 190), ('Qty', 350), ('Unit price', 400), ('Amount', 480)],
        rows, totals,
        notes=[f'Remit to {vendor["name"]}. Questions: {vendor["email"] or ""}'], heading=vendor['name'])


def vendor_invoices(erp: Erp, events: list) -> None:
    for slip in erp.all("SELECT * FROM sim_log WHERE kind = 'packing_slip' ORDER BY id"):
        p = json.loads(slip['payload'])
        if erp.val("SELECT 1 FROM sim_log WHERE kind = 'invoice' AND ref = ?", p['slip']):
            continue
        po = erp.one('SELECT * FROM purchase_orders WHERE id = ?', slip['ref'])
        vendor = erp.one('SELECT * FROM vendors WHERE id = ?', po['vendor'])
        vp = vendor_profile(erp, po['vendor'])
        inv = vp['invoice']
        if erp.add_workdays(p['day'], int(inv.get('delay', 2))) > erp.today:
            continue
        shipped = [dict(r, payload=json.loads(r['payload'])) for r in erp.all(
            "SELECT * FROM sim_log WHERE kind = 'ship_line' AND ref LIKE ? ORDER BY id", f'{po["id"]}/%')]
        lines = []
        for s in shipped:
            if s['payload']['slip'] != p['slip']:
                continue
            line_no = int(s['ref'].split('/')[-1])
            pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', po['id'], line_no)
            sku = s['payload']['ordered_sku']
            price = inv.get('prices', {}).get(sku or '', pl['unit_price'])
            lines.append({'po_line': line_no, 'sku': sku, 'qty': s['payload']['qty'], 'unit_price': float(price),
                          'description': (erp.val('SELECT name FROM items WHERE sku = ?', sku) if sku else
                                          pl['description']) or ''})
        if not lines:
            continue
        n = erp.val("SELECT COUNT(*) FROM sim_log WHERE kind = 'invoice' AND actor = ? AND payload LIKE ?",
                    _actor(erp, 'vendor'), f'%"vendor": "{vendor["id"]}"%')
        number = f'{inv.get("prefix", "INV-")}{int(inv.get("start", 1001)) + n}'
        freight = float(inv.get('freight', 0) or 0)
        pdf = _invoice_pdf(vendor, number, erp.today, po['id'], lines, freight, vendor['terms'])
        name, addr = _vendor_contact(erp, vendor, vp)
        dup = inv.get('duplicate')

        def do(ctx, p=p, number=number, pdf=pdf, lines=lines, freight=freight, name=name, addr=addr, vendor=vendor,
               po=po, dup=dup):
            _log(erp, ctx.user, 'invoice', p['slip'], {'vendor': vendor['id'], 'number': number, 'po': po['id'],
                                                       'lines': lines, 'freight': freight})
            comms.deliver(erp, 'ap', f'Invoice {number} from {vendor["name"]}',
                          f'Please find attached invoice {number} for your PO {po["id"]}.\n\n{name}', name, addr,
                          erp.today, attachments=[(f'{number}.pdf', 'application/pdf', pdf)], created_by=ctx.user)
            if dup:
                dup_no = dup.get('number') or (number.replace(dup['strip'], '') if dup.get('strip') else number)
                _log(erp, ctx.user, 'invoice_dup_due', p['slip'], {
                    'date': erp.add_workdays(erp.today, int(dup.get('delay', 1))), 'number': dup_no,
                    'vendor': vendor['id'], 'po': po['id'], 'lines': lines, 'freight': freight})
        act(erp, _actor(erp, 'vendor'), 'vendor.invoice', 'purchase_order', po['id'], do, events)
    for due in erp.all("SELECT * FROM sim_log WHERE kind = 'invoice_dup_due' ORDER BY id"):
        d = json.loads(due['payload'])
        if d['date'] > erp.today or erp.val("SELECT 1 FROM sim_log WHERE kind = 'invoice_dup' AND ref = ?", due['ref']):
            continue
        vendor = erp.one('SELECT * FROM vendors WHERE id = ?', d['vendor'])
        vp = vendor_profile(erp, vendor['id'])
        name, addr = _vendor_contact(erp, vendor, vp)
        pdf = _invoice_pdf(vendor, d['number'], erp.today, d['po'], d['lines'], d['freight'], vendor['terms'])

        def do(ctx, due=due, d=d, pdf=pdf, name=name, addr=addr, vendor=vendor):
            _log(erp, ctx.user, 'invoice_dup', due['ref'], d)
            comms.deliver(erp, 'ap', f'Invoice {d["number"]}',
                          f'Resending our invoice {d["number"]} for PO {d["po"]} for payment.\n\n{name}', name, addr,
                          erp.today, attachments=[(f'{d["number"]}.pdf', 'application/pdf', pdf)], created_by=ctx.user)
        act(erp, _actor(erp, 'vendor'), 'vendor.invoice', 'purchase_order', d['po'], do, events)


def vendor_request_answers(erp: Erp, events: list) -> None:
    for r in erp.all("SELECT * FROM vendor_requests WHERE status = 'open' AND created_on < ? ORDER BY id", erp.today):
        vp = vendor_profile(erp, r['vendor'])
        rule = vp['requests'].get(r['kind'], {})
        if erp.add_workdays(r['created_on'], int(rule.get('answer_delay', 1))) > erp.today:
            continue
        vendor = erp.one('SELECT * FROM vendors WHERE id = ?', r['vendor'])
        name, addr = _vendor_contact(erp, vendor, vp)
        accept = bool(rule.get('accept', r['kind'] in ('defer', 'copy_request')))

        def do(ctx, r=r, rule=rule, accept=accept, name=name, addr=addr):
            response = rule.get('response')
            if r['kind'] in ('expedite', 'defer') and r['po_line']:
                pl = erp.one('SELECT * FROM po_lines WHERE po_id = ? AND line = ?', r['po_id'], r['po_line'])
                if accept:
                    new = r['wanted_date']
                elif r['kind'] == 'expedite' and rule.get('best_date'):
                    new = max(rule['best_date'], erp.today)
                else:
                    new = pl['confirmed_date']
                if new != pl['confirmed_date']:
                    erp.update('po_lines', {'po_id': r['po_id'], 'line': r['po_line']}, {'confirmed_date': new})
                response = response or (f'We can deliver {r["po_id"]} line {r["po_line"]} on {new}.' if accept or
                                        new != pl['confirmed_date'] else f'We cannot change the date; it stays {new}.')
            elif r['kind'] == 'cancel' and accept:
                erp.update('po_lines', {'po_id': r['po_id'], 'line': r['po_line']},
                           {'status': 'cancelled', 'note': 'cancelled at our request'})
                purchasing._refresh_po(erp, r['po_id'])
                response = response or 'Cancelled as requested.'
            response = response or ('Agreed.' if accept else 'We are unable to agree to this request.')
            erp.touch('vendor_request', r['id'])
            erp.update('vendor_requests', {'id': r['id']}, {'status': 'accepted' if accept else 'declined',
                                                            'response': response, 'responded_on': erp.today})
            box = 'ap' if r['kind'] in ('dispute', 'copy_request') else 'purchasing'
            comms.deliver(erp, box, f'Re: your {r["kind"].replace("_", " ")} request {r["id"]}', response + f'\n\n{name}',
                          name, addr, erp.today, created_by=ctx.user)
        act(erp, _actor(erp, 'vendor'), f'vendor.answer_{r["kind"]}', 'vendor_request', r['id'], do, events)


# ------------------------------------------------------------------------------------------- colleagues

def _next_workday_after(erp: Erp, day: str) -> str:
    return erp.add_workdays(day, 1)


def approvers(erp: Erp, events: list) -> None:
    profiles = erp.world.get('approvers', {})
    agents = _agent_users(erp)
    for ar in erp.all("SELECT * FROM approval_requests WHERE status = 'pending' AND doc_type = 'requisition' ORDER BY id"):
        user = ar['approver']
        if user in agents or user not in profiles or user_on_leave(erp, user, erp.today):
            continue
        if _next_workday_after(erp, ar['requested_on']) > erp.today:
            continue
        prof = profiles[user]
        d = prof.get('decisions', {}).get(ar['doc_id'], {'decision': prof.get('default', 'none')})
        if d['decision'] == 'none':
            continue

        def do(ctx, ar=ar, d=d):
            if d['decision'] == 'approve':
                purchasing.approve_requisition(erp, ctx, ar['doc_id'], d.get('note'))
            elif d['decision'] == 'reject':
                purchasing.reject_requisition(erp, ctx, ar['doc_id'], d.get('reason', 'not approved'), d.get('note'))
            elif d['decision'] == 'return':
                purchasing.return_requisition(erp, ctx, ar['doc_id'], d.get('reason', 'needs changes'), d.get('note'))
            elif d['decision'] == 'forward':
                purchasing.forward_requisition(erp, ctx, ar['doc_id'], d['to'], d.get('reason'), d.get('note'))
            else:
                raise invalid(f'unknown decision {d["decision"]}')
        act(erp, user, f'req.{d["decision"]}', 'requisition', ar['doc_id'], do, events)


def escalations(erp: Erp, events: list) -> None:
    rules = erp.world.get('escalations', [])
    agents = _agent_users(erp)
    for e in erp.all("SELECT * FROM escalations WHERE status = 'open' ORDER BY id"):
        if e['to_user'] in agents or _next_workday_after(erp, e['created_on']) > erp.today:
            continue
        rule = next((r for r in rules if r.get('record_id') == e['record_id'] and r.get('to', e['to_user']) == e['to_user']
                     and r.get('reason', e['reason']) == e['reason']), None)
        if rule is None:
            rule = next((r for r in rules if r.get('record_id') == '*' and r.get('to', e['to_user']) == e['to_user']), None)
        if rule is None:
            rule = {'decision': 'none', 'response': 'Thanks. Please handle it under the handbook.'}

        def do(ctx, e=e, rule=rule):
            comms.answer_escalation(erp, ctx, e['id'], rule['decision'], rule['response'])
            for a in rule.get('actions', []):
                if a['kind'] == 'release_hold':
                    for h in payables.active_holds(erp, e['record_id']):
                        if a.get('reason') in (None, h['reason']):
                            payables.release_hold(erp, ctx, h['id'], a.get('note', rule['response']))
                elif a['kind'] == 'approve_invoice':
                    payables.approve_invoice(erp, ctx, e['record_id'], a.get('note'))
                elif a['kind'] == 'verify_bank_account':
                    payables.verify_bank_account(erp, ctx, a['account'], a.get('note'))
                else:
                    raise invalid(f'unknown escalation action {a["kind"]}')
        act(erp, e['to_user'], 'escalation.answer', 'escalation', e['id'], do, events)


def journal_approvals(erp: Erp, events: list) -> None:
    cfg = erp.world.get('journal_approver')
    if not cfg:
        return
    user = cfg['user']
    for je in erp.all("SELECT * FROM journal_entries WHERE status = 'submitted' AND preparer != ? ORDER BY id", user):
        last = erp.val("SELECT MAX(business_date) FROM audit_events WHERE object_id = ? AND action = 'je.submit' "
                       "AND outcome = 'ok'", je['id']) or je['created_on']
        if _next_workday_after(erp, last) > erp.today:
            continue
        has_support = erp.val("SELECT 1 FROM attachments WHERE owner_type = 'journal_entry' AND owner_id = ?", je['id'])
        decision = cfg.get('decisions', {}).get(je['id'])

        def do(ctx, je=je, has_support=has_support, decision=decision):
            if decision == 'return' or (cfg.get('require_support') and not has_support):
                ledger.return_entry(erp, ctx, je['id'], 'Returned: attach the support for this entry and resubmit.')
            else:
                ledger.approve(erp, ctx, je['id'], 'Approved.')
        act(erp, user, 'je.review', 'journal_entry', je['id'], do, events)


def payment_run_approvals(erp: Erp, events: list) -> None:
    cfg = erp.world.get('payment_run_approver')
    if not cfg:
        return
    user = cfg['user']
    for run in erp.all("SELECT * FROM payment_runs WHERE status IN ('submitted', 'approved') ORDER BY id"):
        if run['created_by'] == user:
            continue
        if run['status'] == 'submitted':
            last = erp.val("SELECT MAX(business_date) FROM audit_events WHERE object_id = ? AND action = 'pay.submit' "
                           "AND outcome = 'ok'", run['id']) or run['created_on']
            if _next_workday_after(erp, last) > erp.today:
                continue
            act(erp, user, 'pay.approve', 'payment_run', run['id'],
                lambda ctx, run=run: payables.approve_run(erp, ctx, run['id'], 'Approved.'), events)
        if cfg.get('release', True) and erp.val("SELECT status FROM payment_runs WHERE id = ?", run['id']) == 'approved':
            act(erp, user, 'pay.release', 'payment_run', run['id'],
                lambda ctx, run=run: payables.release_run(erp, ctx, run['id']), events)


def bank(erp: Erp, events: list) -> None:
    user = _actor(erp, 'bank')
    for pay in erp.all("SELECT p.* FROM payments p JOIN journal_entries e ON e.id = p.posted_je "
                       "WHERE p.status = 'released' AND e.entry_date < ? ORDER BY p.id", erp.today):
        act(erp, user, 'bank.clear', 'payment', pay['id'], lambda ctx, pay=pay: payables.clear_payment(erp, ctx, pay['id']),
            events)


def scheduled_receipts(erp: Erp, events: list) -> None:
    for r in erp.world.get('receipts', []):
        if r['day'] != erp.today:
            continue
        act(erp, r['user'], 'rcv.post', 'purchase_order', r['po_id'],
            lambda ctx, r=r: receiving.post_receipt(erp, ctx, r['po_id'], r['lines'], packing_slip=r.get('packing_slip')),
            events)


def scheduled_reversals(erp: Erp, events: list) -> None:
    for r in erp.world.get('receipt_reversals', []):
        if r['day'] != erp.today:
            continue
        act(erp, r['user'], 'rcv.reverse', 'receipt', r['receipt'],
            lambda ctx, r=r: receiving.reverse_receipt(erp, ctx, r['receipt'], r['reason']), events)


# ------------------------------------------------------------------------------------------- the clock

def run_day(erp: Erp) -> list[dict]:
    events: list[dict] = []
    if not erp.is_workday(erp.today):
        return events
    bank(erp, events)
    scheduled_receipts(erp, events)
    scheduled_reversals(erp, events)
    vendor_acks(erp, events)
    vendor_shipments(erp, events)
    vendor_invoices(erp, events)
    vendor_request_answers(erp, events)
    approvers(erp, events)
    escalations(erp, events)
    journal_approvals(erp, events)
    payment_run_approvals(erp, events)
    return events


def advance(erp: Erp, to: str) -> list[dict]:
    with erp.lock:
        if to < erp.today:
            raise invalid(f'cannot move the clock back from {erp.today} to {to}')
        events: list[dict] = []
        while erp.today < to:
            with erp.tx():
                erp.set_today(add_days(erp.today, 1))
            events += run_day(erp)
        return events

