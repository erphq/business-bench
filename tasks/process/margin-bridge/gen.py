#!/usr/bin/env python3
"""margin-bridge: Monday 12 October 2026. The president asks why gross margin fell from August to September; a
read-only analyst answers from the ledger in answer.md.

  python gen.py --seed 0 --out DIR

Planted in September, inside history so every document and balance is consistent: Dayton Castings raises
CAST-1-BODY from 18.40 to 21.00 on 1 September (purchase price variance on every casting received); an air-freight
bill for expedited castings; BV-100 valves scrapped for body porosity; and a retroactive customer rebate once Harbor
Supply's purchases pass the contract threshold.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

from bberp import inventory, ledger, payables, setup  # noqa: E402
from bberp.core import dollars, to_cents  # noqa: E402
from procgen.company import build  # noqa: E402
from procgen.episode import write_scenario  # noqa: E402
from procgen.northgate import COMPANY, DOMAIN, INVOICE_SERIES, USERS, VENDORS, secret  # noqa: E402

START = '2026-10-12'
AGENT = 'noah.kim'
DAYTON = VENDORS['dayton'][0]
HARBOR = 'C-20001'
OLD_PRICE, NEW_PRICE = 18.40, 21.00
FREIGHT = 1850.00
SCRAP_SKU, SCRAP_QTY = 'BV-100', 100
REVENUE = ('4000', '4100', '4200')
COST = ('5000', '5050', '5060', '5070', '5080', '5100', '5150')
facts: dict = {}


def price_increase(erp) -> None:
    pa = erp.one("SELECT * FROM price_agreements WHERE vendor = ? AND sku = 'CAST-1-BODY'", DAYTON)
    erp.update('price_agreements', {'id': pa['id'], 'min_qty': pa['min_qty']}, {'valid_to': '2026-08-31'})
    erp.insert('price_agreements', {'id': 'PA-3901', 'vendor': DAYTON, 'sku': 'CAST-1-BODY', 'valid_from': '2026-09-01',
                                    'valid_to': '2027-12-31', 'min_qty': 0, 'unit_price': NEW_PRICE})


def air_freight(erp, h) -> None:
    prefix = INVOICE_SERIES['dayton'][0]
    number = f'{prefix}{h.inv_no["dayton"]}'
    h.inv_no['dayton'] += 1
    riley = setup.as_user(erp, 'riley.park')
    inv = payables.enter_invoice(erp, riley, DAYTON, number, erp.today, [
        {'kind': 'freight', 'amount': FREIGHT, 'department': 'PROD',
         'description': 'Air freight, expedited CAST-1-BODY castings'}],
        note='Expedite requested by production after a casting shortage')
    payables.validate(erp, riley, inv)
    payables.approve_invoice(erp, setup.as_user(erp, 'hannah.brooks'), inv)
    facts['freight_invoice'] = number


def scrap(erp, h) -> None:
    qty = min(SCRAP_QTY, int(inventory.on_hand(erp, SCRAP_SKU, 'DAY-STK')))
    assert qty > 0, f'no {SCRAP_SKU} on hand to scrap on {erp.today}'
    aid = inventory.adjust(erp, setup.as_user(erp, 'luis.ortega'), SCRAP_SKU, 'DAY-STK', -qty,
                           'Scrapped after final test: body porosity found in a returned batch (QA-0924)')
    facts['scrap_qty'], facts['scrap_ref'] = qty, aid


def rebate(erp, h) -> None:
    ytd = lambda to: erp.val("SELECT COALESCE(SUM(total_cents), 0) FROM ar_invoices WHERE customer = ? AND "  # noqa: E731
                             "invoice_date BETWEEN '2026-01-01' AND ? AND status != 'voided'", HARBOR, to)
    before, after = ytd('2026-08-31'), ytd('2026-09-30')
    threshold = (before + (after - before) // 2) // 500_000 * 500_000
    amount = to_cents(after / 100 * 0.02)
    omar, priya = setup.as_user(erp, 'omar.haddad'), setup.as_user(erp, 'priya.raman')
    je = ledger.create_manual(erp, omar, '2026-09-30', [
        {'account': '4200', 'debit_cents': amount, 'department': 'SALES'},
        {'account': '2300', 'credit_cents': amount}],
        f'Harbor Supply volume rebate: 2% on 2026 purchases of {dollars(after)}, retroactive once purchases passed '
        f'{dollars(threshold)} in September (contract clause 4.2)')
    ledger.submit(erp, omar, je)
    ledger.approve(erp, priya, je, 'Approved')
    ledger.post_manual(erp, omar, je)
    facts.update({'rebate_je': je, 'rebate_cents': amount, 'harbor_ytd_cents': after, 'threshold_cents': threshold})


def period_totals(erp, period: str) -> tuple[int, int]:
    def total(accts, sign):
        return sign * erp.val(f"SELECT COALESCE(SUM(l.debit_cents - l.credit_cents), 0) FROM journal_lines l "
                              f"JOIN journal_entries e ON e.id = l.je_id WHERE e.period = ? AND e.status IN "
                              f"('posted', 'reversed') AND l.account IN ({','.join('?' * len(accts))})", period, *accts)
    return total(REVENUE, -1), total(COST, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    co = build(os.path.join(a.out, 'scenario.db'), seed=a.seed, start=START, before_history=price_increase,
               events={'2026-09-18': [air_freight], '2026-09-24': [scrap], '2026-10-01': [rebate]})
    erp = co.erp
    with erp.tx():
        setup.add_user(erp, AGENT, 'Noah Kim', ['analyst'], 'FIN', email=f'{AGENT}@{DOMAIN}', title='Financial analyst',
                       manager='priya.raman', phone='(937) 555-0124')
        setup.add_token(erp, f'tok-{AGENT}', AGENT, secret(a.seed, AGENT), 'Noah Kim API token')
    values = {}
    for period, key in (('2026-08', 'aug'), ('2026-09', 'sep')):
        rev, cost = period_totals(erp, period)
        values[f'gm_{key}'] = round((rev - cost) / rev * 100, 1)
        values[f'revenue_{key}'], values[f'cost_{key}'] = rev / 100, cost / 100
    ppv = lambda period: erp.val("SELECT COALESCE(SUM(l.debit_cents - l.credit_cents), 0) FROM journal_lines l "  # noqa: E731
                                 "JOIN journal_entries e ON e.id = l.je_id WHERE e.period = ? AND l.account = '5050'",
                                 period)
    cast_ppv = erp.val("SELECT COALESCE(SUM(rl.grni_cents - rl.value_cents), 0) FROM receipt_lines rl JOIN receipts r "
                       "ON r.id = rl.receipt_id WHERE rl.sku = 'CAST-1-BODY' AND r.receipt_date LIKE '2026-09%' "
                       "AND r.status = 'posted'")
    delta = ppv('2026-09') - ppv('2026-08')
    values.update({
        'price_increase': cast_ppv / 100, 'ppv_delta': delta / 100,
        'price_tol': round(max(0.02, abs(delta - cast_ppv) / cast_ppv + 0.005), 4),
        'freight': FREIGHT, 'writeoff': round(facts['scrap_qty'] * erp.val('SELECT std_cost FROM items WHERE sku = ?',
                                                                          SCRAP_SKU), 2),
        'rebate': facts['rebate_cents'] / 100,
    })
    users = {u[0]: u for u in USERS}
    turn = {'n': 1, 'date': START, 'budget_s': 1200, 'from_user': 'erin.walsh', 'from_name': users['erin.walsh'][1],
            'from_title': users['erin.walsh'][2],
            'request': "Priya is out today and I need this for tomorrow's board call. Gross margin went down in "
                       "September compared with August. What drove it? Write it up in answer.md, with the amount "
                       "behind each cause."}
    meta = {'task': 'margin-bridge', 'seed': a.seed, 'company': COMPANY, 'start': START, 'grading_date': START,
            'agent_user': AGENT, 'agent_name': 'Noah Kim', 'agent_title': 'Financial analyst',
            'token': secret(a.seed, AGENT), 'token_id': f'tok-{AGENT}', 'turns': [turn]}
    truth = {
        'values': values, 'facts': facts,
        'planted': [
            f'Dayton raised CAST-1-BODY from {OLD_PRICE} to {NEW_PRICE} on 1 Sep: {values["price_increase"]:,.2f} of '
            f'purchase price variance (5050) on September castings',
            f'Air freight for expedited castings: {FREIGHT:,.2f} (5100), Dayton invoice {facts["freight_invoice"]}',
            f'{facts["scrap_qty"]} {SCRAP_SKU} scrapped: {values["writeoff"]:,.2f} (5080), {facts["scrap_ref"]}',
            f'Harbor Supply retroactive 2% rebate: {values["rebate"]:,.2f} (4200), {facts["rebate_je"]}',
            f'Gross margin {values["gm_aug"]}% in August, {values["gm_sep"]}% in September (RPT-1.1)',
        ],
    }
    handbook = {f: open(os.path.join(HERE, 'handbook', f), encoding='utf-8').read()
                for f in sorted(os.listdir(os.path.join(HERE, 'handbook')))}
    write_scenario(a.out, erp, {'agent_users': [AGENT]}, meta, handbook, truth)


if __name__ == '__main__':
    main()
