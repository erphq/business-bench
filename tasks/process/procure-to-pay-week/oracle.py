"""Reference policy and negative controls for procure-to-pay-week.

Every policy acts only through the agent's API with the agent's token, and reads vendor documents the way an agent
must: by downloading the PDF from the inbox and extracting its text. The oracle applies the handbook; each negative
control is the oracle with one judgment switched off, and must fail the checks named in task.yaml.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta

from procgen.episode import Api, pdf_text, parse_invoice, parse_packing_slip


def alnum(s: str) -> str:
    return re.sub(r'[^0-9a-z]', '', (s or '').lower())


@dataclass(frozen=True)
class Policy:
    consolidate: bool = True
    respect_quality_hold: bool = True
    moq_rule: bool = True
    lead_time_rule: bool = True
    receiving_rules: bool = True
    enter_as_billed: bool = True
    hold_mismatches: bool = True
    detect_duplicates: bool = True

    def __call__(self, turn: int, api: Api, ws: str, meta: dict) -> None:
        {1: self.order, 2: self.receive, 3: self.match}[turn](api, ws)

    # ------------------------------------------------------------------------------------------- turn 1
    def order(self, api: Api, ws: str) -> None:
        today = api.get('/whoami')['business_date']
        holidays = {h['day'] for h in api.get('/calendar', **{'from': today, 'to': '2027-01-31'})['holidays']}
        vendors = {v['id']: v for v in api.items('/vendors')}
        lines = []
        for r in api.items('/requisitions', status='approved'):
            full = api.get(f'/requisitions/{r["id"]}')
            for l in full['lines']:
                if not l['po_id']:
                    lines.append({**l, 'requester': r['requester']})

        def usable(vid: str | None) -> bool:
            v = vendors.get(vid or '')
            return bool(v) and v['status'] == 'active' and (not v['quality_hold'] or not self.respect_quality_hold)

        groups: dict[tuple, list] = {}
        for i, l in enumerate(lines):
            if l['sku']:
                item = api.get(f'/items/{l["sku"]}')
                agreed = {a['vendor'] for a in item['price_agreements']}
                if not self.respect_quality_hold:
                    vendor = l['vendor']
                elif usable(l['vendor']) and l['vendor'] in agreed:
                    vendor = l['vendor']
                else:
                    vendor = item['preferred_vendor']
            else:
                vendor = l['vendor']
            key = (vendor, l['sku'] or l['description'], l['ship_to']) if self.consolidate else (i,)
            groups.setdefault(key, []).append({**l, 'vendor': vendor})
        by_vendor: dict[str, list] = {}
        at_risk_notes = []
        for key, ls in groups.items():
            vendor, sku = ls[0]['vendor'], ls[0]['sku']
            qty = sum(l['qty'] for l in ls)
            need = min(l['need_by'] for l in ls)
            line = {'qty': qty, 'need_date': need, 'req_refs': [{'req_id': l['req_id'], 'line': l['line']} for l in ls]}
            if sku:
                item = api.get(f'/items/{sku}')
                if self.moq_rule and item['moq'] and qty < item['moq']:
                    usage = api.get('/reports/item-usage', sku=sku, months='6')['items']
                    per_month = usage[0]['avg_per_month'] if usage else 0
                    if per_month and (item['moq'] - qty) <= per_month * 90 / 30:
                        qty = item['moq']
                earliest = _add_workdays(today, item['lead_time_days'], holidays)
                if self.lead_time_rule and need < earliest:
                    line.update({'need_date': earliest, 'at_risk': True})
                    at_risk_notes.append((ls, sku, need, earliest))
                line.update({'sku': sku, 'qty': qty})
            else:
                line.update({'description': ls[0]['description'], 'account': ls[0]['account'],
                             'unit_price': ls[0]['est_unit_price'], 'qty': qty})
            by_vendor.setdefault(vendor, []).append(line)
        for vendor, ls in sorted(by_vendor.items()):
            if self.consolidate:
                po = api.post('/purchase-orders', {'vendor': vendor, 'ship_to': 'DAY', 'lines': ls})
                api.post(f'/purchase-orders/{po["id"]}/send')
            else:
                for l in ls:
                    po = api.post('/purchase-orders', {'vendor': vendor, 'ship_to': 'DAY', 'lines': [l]})
                    api.post(f'/purchase-orders/{po["id"]}/send')
        for ls, sku, need, earliest in at_risk_notes:
            for l in ls:
                api.post('/outbox', {'to': l['requester'], 'subject': f'{sku} will arrive after your need-by date',
                                     'body': f'{l["req_id"]} line {l["line"]}: {sku} is ordered, but with the '
                                             f'lead time it arrives {earliest}, not {need} (PUR-5.3).'})

    # ------------------------------------------------------------------------------------------- turn 2
    def receive(self, api: Api, ws: str) -> None:
        today = api.get('/whoami')['business_date']
        for m in api.items('/inbox', box='receiving'):
            if m['disposition'] or not m['attachments']:
                continue
            msg = api.get(f'/inbox/{m["id"]}')
            slip = parse_packing_slip(pdf_text(api.request('GET', f'/inbox/{m["id"]}/attachments/1', raw=True)))
            po = api.get(f'/purchase-orders/{slip["po"]}')
            received: dict[int, float] = {}
            lines = []
            for sl in slip['lines']:
                if 'backordered' in sl:
                    continue
                pl = next((l for l in po['lines'] if l['line'] == sl['po_line'] and l['status'] == 'open'), None)
                if pl is None:
                    continue
                qty = sl['qty']
                ln = {'po_line': pl['line']}
                if not self.receiving_rules:
                    ln.update({'qty_received': qty})
                    if sl['substitute_for']:
                        ln['sku'] = sl['sku']
                    if sl['lot']:
                        ln.update({'lot': sl['lot'], 'expiry': sl['expiry']})
                    lines.append(ln)
                    continue
                if sl['substitute_for']:
                    subs = api.get(f'/items/{sl["substitute_for"]}')['approved_substitutes']
                    if sl['sku'] in subs:
                        ln.update({'qty_received': qty, 'sku': sl['sku']})
                    else:
                        ln.update({'qty_received': 0, 'qty_refused': qty, 'refusal_reason': 'wrong_item'})
                elif sl['lot']:
                    if date.fromisoformat(sl['expiry']) < date.fromisoformat(today) + timedelta(days=182):
                        ln.update({'qty_received': 0, 'qty_refused': qty, 'refusal_reason': 'short_dated'})
                    else:
                        ln.update({'qty_received': qty, 'lot': sl['lot'], 'expiry': sl['expiry']})
                else:
                    open_qty = pl['qty'] - pl['qty_received'] - received.get(pl['line'], 0)
                    if qty > open_qty * 1.05:
                        ln.update({'qty_received': open_qty, 'qty_refused': qty - open_qty,
                                   'refusal_reason': 'over_shipment'})
                    else:
                        ln.update({'qty_received': qty})
                received[pl['line']] = received.get(pl['line'], 0) + ln.get('qty_received', 0)
                lines.append(ln)
            if lines:
                rcv = api.post('/receipts', {'po_id': po['id'], 'packing_slip': slip['slip'], 'lines': lines})
                api.post(f'/inbox/{msg["id"]}/disposition', {'disposition': 'processed', 'ref': rcv['id']})

    # ------------------------------------------------------------------------------------------- turn 3
    def match(self, api: Api, ws: str) -> None:
        vendors = {v['id']: v for v in api.items('/vendors')}
        known = {(i['vendor'], alnum(i['invoice_no'])): i['id'] for i in api.items('/ap-invoices')}
        held = []
        for m in api.items('/inbox', box='ap'):
            if m['disposition'] or not m['attachments']:
                continue
            doc = parse_invoice(pdf_text(api.request('GET', f'/inbox/{m["id"]}/attachments/1', raw=True)))
            po = api.get(f'/purchase-orders/{doc["po"]}')
            vendor = po['vendor']
            if self.detect_duplicates and (vendor, alnum(doc['number'])) in known:
                api.post(f'/inbox/{m["id"]}/disposition', {'disposition': 'duplicate',
                                                          'ref': known[(vendor, alnum(doc['number']))],
                                                          'note': 'second copy of an invoice already entered (AP-1.6)'})
                continue
            lines = []
            for l in doc['lines']:
                pl = next(p for p in po['lines'] if p['line'] == l['po_line'])
                qty, price = l['qty'], l['unit_price']
                if not self.enter_as_billed:          # "fix" the invoice to what was ordered and received
                    qty, price = min(qty, pl['qty_received'] - pl['qty_billed']), pl['unit_price']
                    if qty <= 0:
                        continue
                lines.append({'kind': 'item', 'po_line': pl['line'], 'qty': qty, 'unit_price': price})
            if doc['freight']:
                lines.append({'kind': 'freight', 'amount': doc['freight']})
            inv = api.post('/ap-invoices', {'vendor': vendor, 'invoice_no': doc['number'], 'invoice_date': doc['date'],
                                            'po_id': po['id'], 'source_msg': m['id'], 'lines': lines})
            known[(vendor, alnum(doc['number']))] = inv['id']
            holds = []
            if self.hold_mismatches:
                for row in inv['match']:
                    if row['kind'] != 'item':
                        continue
                    what = row['sku'] or f'PO line {row["po_line"]}'
                    if abs(row['price_variance_pct'] or 0) > 2:
                        holds.append(('price', row['line'], f'billed {row["billed_price"]:g} vs PO {row["po_price"]:g} '
                                      f'on {what}'))
                    elif row['qty_over_received'] > 0:
                        if row['unbilled_received_qty'] > 0:
                            holds.append(('quantity', row['line'], f'billed {row["billed_qty"]:g} {what}, '
                                          f'received {row["unbilled_received_qty"]:g}'))
                        else:
                            holds.append(('no_receipt', row['line'], f'nothing received for {what}'))
                if doc['freight'] > 100:
                    holds.append(('freight', None, f'freight {doc["freight"]:.2f} above 100.00'))
            for reason, line, note in holds:
                api.post(f'/ap-invoices/{inv["id"]}/holds', {'reason': reason, 'line': line, 'note': note})
            if not holds:
                api.post(f'/ap-invoices/{inv["id"]}/validate')
            else:
                held.append((vendors[vendor]['name'], doc['number'], holds))
            api.post(f'/inbox/{m["id"]}/disposition', {'disposition': 'processed', 'ref': inv['id']})
        words = {'price': 'price', 'quantity': 'quantity', 'no_receipt': 'no receipt', 'freight': 'freight'}
        with open(os.path.join(ws, 'handoff.md'), 'w', encoding='utf-8') as f:
            f.write('# AP holds, week of 5 October\n\n')
            for name, number, holds in held:
                for reason, _line, note in holds:
                    f.write(f'- {name} invoice {number} is on hold for {words[reason]}: {note}.\n')
            f.write('\nDuplicates were not entered; the inbox messages are marked duplicate.\n')


def _add_workdays(day: str, n: int, holidays: set[str]) -> str:
    d = date.fromisoformat(day)
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in holidays:
            n -= 1
    return d.isoformat()


ORACLE = Policy()
POLICIES = {
    'oracle': ORACLE,
    'neg:one_po_per_requisition': replace(ORACLE, consolidate=False, respect_quality_hold=False),
    'neg:exact_quantities': replace(ORACLE, moq_rule=False),
    'neg:ignore_lead_times': replace(ORACLE, lead_time_rule=False),
    'neg:receive_everything': replace(ORACLE, receiving_rules=False),
    'neg:force_match': replace(ORACLE, enter_as_billed=False, hold_mismatches=False),
    'neg:enter_everything': replace(ORACLE, detect_duplicates=False),
}
