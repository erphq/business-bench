#!/usr/bin/env python3
"""procure-to-pay-week: Northgate on Monday 5 October 2026. A week of approved requisitions goes out as purchase
orders, the deliveries are received on Wednesday, and the invoices are matched on Friday.

  python gen.py --seed 0 --out DIR

Planted (see docs/process/tasks.md section 4): two BR-0750 requisitions that reach Mid-State's 500 ft price break
only when consolidated; a SEAL-212 requisition naming Pacific Seal, on quality hold; a CAST-1-BODY need date inside
the 15-workday lead time; GASKET-9 below Keystone's MOQ with usage that justifies the MOQ; deliveries with a 1.8%
over-shipment, a short-dated lot, an approved and an unapproved substitute; invoices billing the pre-break price,
the refused lot, the refused nuts, freight, and a duplicate sent again without its dash.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

from bberp import purchasing, setup  # noqa: E402
from procgen.company import build  # noqa: E402
from procgen.episode import write_scenario  # noqa: E402
from procgen.northgate import COMPANY, INVOICE_SERIES, USERS, VENDORS  # noqa: E402

START, GRADE = '2026-10-05', '2026-10-12'
NEED_BY = '2026-10-12'
AGENT = 'riley.park'

# requester, department, created on, justification, lines (sku or description, qty, requested vendor key, account)
REQUISITIONS = [
    ('mateo.garcia', 'PROD', '2026-10-01', 'Bar stock and seals for the GV-100 run', [
        ('BR-0750', 300, 'midstate', None), ('SEAL-212', 200, 'pacific', None), ('SEAL-214', 150, 'coastline', None)]),
    ('aisha.okafor', 'MAINT', '2026-10-01', 'Fixture repairs; safety stock for the shop', [
        ('BR-0750', 250, 'midstate', None), ('Safety glasses and nitrile gloves', 1, 'greatlakes', '6250')]),
    ('sam.whitaker', 'PROD', '2026-10-02', 'Warranty replacement order for Riverbend Utilities', [
        ('CAST-1-BODY', 120, 'dayton', None), ('HEX-NUT-10', 500, 'keystone', None)]),
    ('alex.ng', 'QA', '2026-10-02', 'Gaskets for GV-100 rework after the leak test', [
        ('GASKET-9', 400, 'keystone', None)]),
    ('luis.ortega', 'WH', '2026-10-02', 'Packaging and handles for October', [
        ('BOX-S', 500, 'ohiopack', None), ('BOX-M', 300, 'ohiopack', None), ('HANDLE-L', 200, 'tricounty', None),
        ('GASKET-7', 1000, 'keystone', None)]),
]
MRO_PRICE = 236.40

TURNS = [
    {'n': 1, 'date': '2026-10-05', 'from': 'maya.chen', 'budget_s': 1200,
     'request': "Morning. This week's approved requisitions are in the system. Get the POs out today. "
                "I'm travelling until Friday."},
    {'n': 2, 'date': '2026-10-07', 'from': 'luis.ortega', 'budget_s': 1200,
     'request': 'Trucks came in yesterday and this morning. The packing slips are in the receiving inbox. '
                'Please get everything received today.'},
    {'n': 3, 'date': '2026-10-09', 'from': 'maya.chen', 'budget_s': 1200,
     'request': "Invoices for this week's deliveries are in the AP inbox. Enter and match them. Anything that "
                "doesn't match goes on hold with the reason. Leave me a short note in handoff.md saying what's on "
                "hold and why."},
]


def next_invoice_number(erp, vkey: str) -> int:
    prefix, start = INVOICE_SERIES[vkey]
    nums = [int(m.group(1)) for (no,) in erp.db.execute(
        'SELECT invoice_no FROM ap_invoices WHERE vendor = ?', (VENDORS[vkey][0],)).fetchall()
        if (m := re.fullmatch(re.escape(prefix) + r'(\d+)', no))]
    return (max(nums) if nums else start - 1) + 1


def plant_requisitions(erp) -> list[str]:
    ids = []
    for requester, dept, day, why, lines in REQUISITIONS:
        erp.set_today(day)
        body = []
        for what, qty, vkey, account in lines:
            vendor = VENDORS[vkey][0]
            if account:
                body.append({'description': what, 'qty': qty, 'est_unit_price': MRO_PRICE, 'vendor': vendor,
                             'account': account, 'ship_to': 'DAY', 'need_by': NEED_BY})
            else:
                body.append({'sku': what, 'qty': qty, 'vendor': vendor, 'ship_to': 'DAY', 'need_by': NEED_BY})
        rid = purchasing.create_requisition(erp, setup.as_user(erp, requester), dept, body, why, submit=True)
        approver = purchasing.pending_request(erp, rid)['approver']
        if approver == requester:
            approver = erp.val('SELECT manager FROM users WHERE id = ?', requester)
            purchasing.forward_requisition(erp, setup.as_user(erp, requester), rid, approver, 'my own request')
        purchasing.approve_requisition(erp, setup.as_user(erp, approver), rid, 'OK to order')
        ids.append(rid)
    erp.set_today(START)
    return ids


def world(erp, V: dict) -> dict:
    n = {k: next_invoice_number(erp, k) for k in VENDORS}

    def inv(k, **extra):
        return {'prefix': INVOICE_SERIES[k][0], 'start': n[k], **extra}
    return {
        'agent_users': [AGENT],
        'actors': {'vendor': 'sys-vendor', 'bank': 'sys-bank'},
        'vendor_default': {'ack_delay': 1, 'ship_early': True, 'invoice': {'delay': 2}},
        'vendors': {
            V['midstate']: {'lead_time_days': 1, 'ship': {'BR-0750': {'over_pct': 1.8, 'round_to': 10}},
                            'invoice': inv('midstate', prices={'BR-0750': 4.12})},
            V['coastline']: {'lead_time_days': 2, 'ship': {'SEAL-212': {'lots': [
                {'lot': 'C-8812', 'share': 0.9, 'expiry': '2028-04-30'},
                {'lot': 'C-8790', 'share': 0.1, 'expiry': '2027-02-26'}]}}, 'invoice': inv('coastline')},
            V['keystone']: {'lead_time_days': 1, 'moq': {'GASKET-9': 1000, 'GASKET-9B': 1000},
                            'ship': {'GASKET-9': {'substitute': 'GASKET-9B'}, 'HEX-NUT-10': {'substitute': 'HEX-NUT-10Z'}},
                            'invoice': inv('keystone', freight=64.0, duplicate={'delay': 1, 'strip': '-'})},
            V['ohiopack']: {'lead_time_days': 1, 'invoice': inv('ohiopack')},
            V['tricounty']: {'lead_time_days': 2, 'invoice': inv('tricounty')},
            V['greatlakes']: {'lead_time_days': 2, 'invoice': inv('greatlakes')},
            V['pacific']: {'lead_time_days': 2, 'invoice': inv('pacific')},
            V['dayton']: {'lead_time_days': 15, 'ship_early': False, 'invoice': inv('dayton')},
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    co = build(os.path.join(a.out, 'scenario.db'), seed=a.seed, start=START)
    erp, V = co.erp, co.vendors
    with erp.tx():
        erp.update('vendors', {'id': V['pacific']}, {
            'quality_hold': 1, 'note': 'Quality hold from 14 Aug 2026: O-ring lot failed the hardness test (QA-0817).'})
        reqs = plant_requisitions(erp)
    users = {u[0]: u for u in USERS}
    agent = users[AGENT]
    meta = {'task': 'procure-to-pay-week', 'seed': a.seed, 'company': COMPANY, 'start': START, 'grading_date': GRADE,
            'agent_user': AGENT, 'agent_name': agent[1], 'agent_title': agent[2], 'token': co.token(AGENT),
            'token_id': f'tok-{AGENT}',
            'turns': [{**{k: v for k, v in t.items() if k != 'from'}, 'from_user': t['from'],
                       'from_name': users[t['from']][1], 'from_title': users[t['from']][2]} for t in TURNS]}
    truth = {
        'requisitions': reqs,
        'planted': [
            'BR-0750 300 ft (Production) + 250 ft (Maintenance): one Mid-State line of 550 ft at the 3.87 break (PUR-4.2)',
            'SEAL-212 requisition names Pacific Seal, on quality hold: order from Coastline at 1.46 (PUR-3.1)',
            'CAST-1-BODY need-by 12 Oct inside the 15-workday lead time: order for 26 Oct, at risk (PUR-5.3)',
            'GASKET-9 400 below MOQ 1000; about 430 used a month, so order 1000 (PUR-4.5)',
            'Mid-State ships 560 ft (1.8% over): receive all (REC-2.1)',
            'Coastline lot C-8790 expires 26 Feb 2027: refuse 20 as short_dated (REC-3.2)',
            'Keystone GASKET-9B for GASKET-9 is approved: receive; HEX-NUT-10Z for HEX-NUT-10 is not: refuse (REC-4.1)',
            'Mid-State bills 4.12: hold price; Coastline bills 200 for 180 received: hold quantity; Keystone bills '
            'the refused nuts: hold no_receipt; Keystone resends its invoice without the dash: duplicate (AP-1.6)',
        ],
        'expect': {
            'po_lines': [
                {'vendor': V['midstate'], 'item': 'BR-0750', 'qty_ordered': '550', 'unit_price': '3.87', 'lines': '1'},
                {'vendor': V['coastline'], 'item': 'SEAL-212', 'qty_ordered': '200', 'unit_price': '1.46'},
                {'vendor': V['dayton'], 'item': 'CAST-1-BODY', 'need_date': '2026-10-26', 'at_risk': '1'},
                {'vendor': V['keystone'], 'item': 'GASKET-9', 'qty_ordered': '1000'},
            ],
            'receipt_lines': [
                {'vendor': V['midstate'], 'item': 'BR-0750', 'qty_received': '560', 'qty_refused': '0'},
                {'vendor': V['coastline'], 'item': 'SEAL-212', 'qty_received': '180', 'qty_refused': '20',
                 'refusal_reason': 'short_dated'},
                {'vendor': V['keystone'], 'item': 'GASKET-9', 'qty_received': '1000', 'received_as': 'GASKET-9B'},
                {'vendor': V['keystone'], 'item': 'HEX-NUT-10', 'qty_received': '0', 'qty_refused': '500',
                 'refusal_reason': 'wrong_item'},
            ],
            'ap_invoices': [
                {'vendor': V['midstate'], 'status': 'on_hold', 'hold_reasons': 'price'},
                {'vendor': V['coastline'], 'status': 'on_hold', 'hold_reasons': 'quantity'},
                {'vendor': V['keystone'], 'status': 'on_hold', 'hold_reasons': 'no_receipt'},
                {'vendor': V['ohiopack'], 'status': 'matched', 'hold_reasons': ''},
            ],
        },
    }
    handbook = {f: open(os.path.join(HERE, 'handbook', f), encoding='utf-8').read()
                for f in sorted(os.listdir(os.path.join(HERE, 'handbook')))}
    write_scenario(a.out, erp, world(erp, V), meta, handbook, truth)
    shutil.rmtree(os.path.join(a.out, 'scenario.db-wal'), ignore_errors=True)


if __name__ == '__main__':
    main()
