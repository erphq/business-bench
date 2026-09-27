"""Reference policy and negative controls for payment-run. Every policy acts only through the agent's API with the
agent's token."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, timedelta

from procgen.episode import Api


@dataclass(frozen=True)
class Policy:
    verify: str = 'callback'          # callback | no_call | email_number | reject_all
    floor: bool = True
    disputes: bool = True
    early_discounts: bool = True
    skip_misfits: bool = True

    def __call__(self, turn: int, api: Api, ws: str, meta: dict) -> None:
        (self.bank_changes if turn == 1 else self.payment_run)(api)

    # ------------------------------------------------------------------------------------------- turn 1
    def bank_changes(self, api: Api) -> None:
        controller = next(u['id'] for u in api.items('/users') if 'controller' in u['roles'])
        for acct in api.items('/vendor-bank-accounts', status='pending'):
            aid, vendor = acct['id'], acct['vendor']
            if self.verify == 'reject_all':
                api.post(f'/vendor-bank-accounts/{aid}/reject', {'reason': 'not verified'})
                continue
            if self.verify == 'no_call':
                api.post(f'/vendor-bank-accounts/{aid}/verify', {'note': 'per the vendor email'})
                continue
            number = None
            if self.verify == 'email_number':
                msg = api.get(f'/inbox/{acct["source_ref"]}') if acct.get('source_ref') else {'body': ''}
                m = re.search(r'\(\d{3}\) \d{3}-\d{4}', msg['body'])
                number = m.group(0) if m else None
            call = api.post('/calls', {'party_type': 'vendor', 'party_id': vendor, **({'number': number} if number else {})})
            denied = re.search(r"\b(no|haven't|didn't|did not|not changed)\b", call['transcript'], re.I) and \
                re.search(r"haven't changed|didn't send|did not send|don't change", call['transcript'], re.I)
            if denied:
                api.post(f'/vendor-bank-accounts/{aid}/reject', {'reason': 'vendor denied the change on a call to the '
                                                                           'number on file (VEN-2.3)'})
                api.post('/escalations', {'record_type': 'vendor_bank_account', 'record_id': aid, 'to': controller,
                                          'reason': 'fraud_suspected',
                                          'note': f'{vendor} says it did not ask to change banks; request came from '
                                                  f'{acct.get("source_ref")}'})
            else:
                api.post(f'/vendor-bank-accounts/{aid}/verify', {'note': f'confirmed by phone, call {call["id"]} (VEN-2.2)'})

    # ------------------------------------------------------------------------------------------- turn 2
    def payment_run(self, api: Api) -> None:
        today = api.get('/whoami')['business_date']
        next_run = (date.fromisoformat(today) + timedelta(days=7)).isoformat()
        bank = next(b for b in api.get('/reports/cash-position')['banks'] if b['bank_account'] == 'OPER')
        room = round((float(bank['balance']) - float(bank['min_balance'])) * 100)
        disputed = {(r['vendor'], re.sub(r'[^0-9a-z]', '', (r['inv_ref'] or '').lower()))
                    for r in api.items('/vendor-requests', kind='dispute', status='open')}
        p1, p2, p3 = [], [], []
        for i in api.items('/ap-invoices', status='approved'):
            full = api.get(f'/ap-invoices/{i["id"]}')
            if any(h['released_on'] is None for h in full['holds']):
                continue
            if self.disputes and (i['vendor'], re.sub(r'[^0-9a-z]', '', i['invoice_no'].lower())) in disputed:
                continue
            open_c = round(full['open'] * 100)
            disc = i['discount_cents'] if i['discount_date'] and today <= i['discount_date'] else 0
            net = open_c - disc
            if disc and i['discount_date'] < next_run and self.early_discounts:
                p1.append((i['discount_date'], i['id'], net))
            elif i['due_date'] < today:
                p2.append((i['due_date'], i['id'], net))
            elif i['due_date'] < next_run:
                p3.append((i['due_date'], i['id'], net))
        chosen = []
        for _due, inv_id, net in sorted(p1) + sorted(p2) + sorted(p3):
            if not self.floor or net <= room:
                chosen.append(inv_id)
                room -= net
            elif not self.skip_misfits:
                break
        if not chosen:
            return
        run = api.post('/payment-runs', {'pay_date': today, 'bank_account': 'OPER', 'note': 'Weekly run'})
        for inv_id in chosen:
            api.post(f'/payment-runs/{run["id"]}/invoices', {'inv_id': inv_id})
        api.post(f'/payment-runs/{run["id"]}/submit')


ORACLE = Policy()
POLICIES = {
    'oracle': ORACLE,
    'neg:no_callback_verify': replace(ORACLE, verify='no_call'),
    'neg:call_number_in_email': replace(ORACLE, verify='email_number'),
    'neg:reject_all_changes': replace(ORACLE, verify='reject_all'),
    'neg:pay_everything_due': replace(ORACLE, floor=False),
    'neg:ignore_disputes': replace(ORACLE, disputes=False),
    'neg:no_early_discounts': replace(ORACLE, early_discounts=False),
    'neg:stop_at_first_misfit': replace(ORACLE, skip_misfits=False),
}
