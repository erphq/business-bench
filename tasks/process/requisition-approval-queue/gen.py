#!/usr/bin/env python3
"""requisition-approval-queue: Maya Chen, purchasing manager, clears the requisitions waiting for her on Monday
5 October 2026.

  python gen.py --seed 0 --out DIR

Planted (docs/process/tasks.md, A1): a request above her limit; her own request; two requests from one requester
to one vendor that split a purchase to fit under her limit; a request within her limit that the maintenance
budget cannot carry once commitments are counted; a request naming an inactive vendor; and a duplicate. The rest
are routine approvals.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

from bberp import purchasing, reports, setup  # noqa: E402
from bberp.core import to_cents  # noqa: E402
from procgen.company import build  # noqa: E402
from procgen.episode import write_scenario  # noqa: E402
from procgen.northgate import COMPANY, USERS, VENDORS  # noqa: E402

START, GRADE = '2026-10-05', '2026-10-06'
AGENT = 'maya.chen'
NEW_VENDORS = [  # id, name, status, terms, phone, email, address
    ('V-10011', 'Precision Metrology Inc.', 'active', 'NET30', '(614) 555-0177', 'sales@precisionmetrology.example',
     '8 Gauge Street\nColumbus, OH 43215'),
    ('V-10012', 'Buckeye Storage Systems', 'active', 'NET30', '(937) 555-0128', 'orders@buckeyestorage.example',
     '400 Rack Way\nSpringfield, OH 45502'),
    ('V-10013', 'Apex Tooling', 'inactive', 'NET30', '(513) 555-0161', 'ar@apextooling.example',
     '71 Carbide Court\nCincinnati, OH 45202'),
    ('V-10014', 'Midwest Hydraulics', 'active', 'NET30', '(419) 555-0149', 'service@midwesthydraulics.example',
     '15 Piston Park\nLima, OH 45801'),
]
GL = VENDORS['greatlakes'][0]

# key, requester, department, created on, justification, vendor, account, [(description, qty, unit price)]
QUEUE = [
    ('R1', 'riley.park', 'PUR', '2026-09-30', 'Label printer ribbons and shipping labels for Q4', GL, '6300',
     [('Thermal transfer ribbons, 110mm', 20, 14.50), ('Shipping labels 4x6, case', 12, 29.17)]),
    ('R1dup', 'riley.park', 'PUR', '2026-10-01', 'Label printer ribbons and shipping labels for Q4', GL, '6300',
     [('Thermal transfer ribbons, 110mm', 20, 14.50), ('Shipping labels 4x6, case', 12, 29.17)]),
    ('R2', 'luis.ortega', 'WH', '2026-09-30', 'Pallet wrap and strapping for October', GL, '6250',
     [('Stretch wrap 18in, case', 25, 58.00), ('Poly strapping coil', 10, 40.00)]),
    ('R3', 'mateo.garcia', 'PROD', '2026-10-01', 'Collet set for lathe 2; the old set is worn out of tolerance', GL,
     '6250', [('ER40 collet set, 23 pc', 1, 3200.00)]),
    ('R4', 'aisha.okafor', 'MAINT', '2026-10-01', 'Annual service of the main air compressor', GL, '6250',
     [('Compressor service kit and labour', 1, 2900.00)]),
    ('R6', 'alex.ng', 'QA', '2026-09-29', 'Replacement touch probe for the CMM', 'V-10011', '6250',
     [('Touch trigger probe, TP20 compatible', 1, 4100.00)]),
    ('P1', 'sam.whitaker', 'PROD', '2026-09-29', 'Pallet racking for bay 4 to free the production aisle', 'V-10012',
     '1500', [('Selective pallet racking, 6 bays installed', 1, 14200.00)]),
    ('P2', 'maya.chen', 'PUR', '2026-10-01', 'Barcode scanners for receiving and the stockroom', GL, '6350',
     [('Rugged barcode scanner with cradle', 6, 800.00)]),
    ('P3a', 'sam.whitaker', 'PROD', '2026-09-30', 'Spare 7.5 HP motor for the coolant pump', GL, '6200',
     [('Motor 7.5 HP TEFC 213T', 1, 6400.00)]),
    ('P3b', 'sam.whitaker', 'PROD', '2026-10-01', 'Spare gearbox for the coolant pump drive', GL, '6200',
     [('Right-angle gearbox 20:1', 1, 5900.00)]),
    ('P4', 'aisha.okafor', 'MAINT', '2026-10-02', 'Hydraulic press seal kit and service visit', 'V-10014', '6200',
     [('Press seal kit and service visit', 1, 3800.00)]),
    ('P5', 'mateo.garcia', 'PROD', '2026-10-02', 'Carbide inserts for the new stainless job', 'V-10013', '6250',
     [('CNMG 432 carbide inserts, box of 10', 25, 106.00)]),
]
# Remaining budget (budget - actual - commitments, January to October) each touched account should show.
BUDGET_ROOM = {('PUR', '6300'): 5000, ('WH', '6250'): 6000, ('PROD', '6250'): 12000, ('MAINT', '6250'): 6000,
               ('QA', '6250'): 8000, ('PUR', '6350'): 9000, ('PROD', '6200'): 20000}
MAINT_6200_ACTUAL_ROOM = 5400        # budget less actual only
MAINT_6200_EXTRA_COMMITMENT = 1284   # an approved maintenance requisition not yet ordered


def route_to_maya(erp, rid: str, requester: str) -> None:
    """Walk the requisition up the chain the way the heads did last week, until it waits for Maya."""
    approver = purchasing.pending_request(erp, rid)['approver']
    if approver == requester and requester != AGENT:     # Maya's own request stays in her queue for her to route
        mgr = erp.val('SELECT manager FROM users WHERE id = ?', requester)
        purchasing.forward_requisition(erp, setup.as_user(erp, requester), rid, mgr, 'my own request')
        approver = mgr
    while approver != AGENT:
        purchasing.forward_requisition(erp, setup.as_user(erp, approver), rid, AGENT, 'above my approval limit')
        approver = AGENT


def set_budget_room(erp, dept: str, acct: str, room_cents: int, actual_only: bool = False) -> None:
    """Set October's budget so the year-to-date remaining is `room_cents` (after commitments unless actual_only)."""
    line = next((l for l in reports.budget_vs_actual(erp, department=dept)['lines'] if l['account'] == acct), None)
    budget = to_cents(line['budget']) if line else 0
    actual = to_cents(line['actual']) if line else 0
    committed = 0 if actual_only or line is None else to_cents(line['committed'])
    october = erp.val('SELECT amount_cents FROM budgets WHERE department = ? AND account = ? AND period = ?',
                      dept, acct, '2026-10') or 0
    target = actual + committed + room_cents
    new_oct = october + (target - budget)
    erp.run('INSERT INTO budgets (department, account, period, amount_cents) VALUES (?, ?, ?, ?) '
            'ON CONFLICT(department, account, period) DO UPDATE SET amount_cents = excluded.amount_cents',
            dept, acct, '2026-10', new_oct)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    co = build(os.path.join(a.out, 'scenario.db'), seed=a.seed, start=START)
    erp = co.erp
    ids = {}
    with erp.tx():
        for vid, name, status, terms, phone, email, address in NEW_VENDORS:
            setup.add_vendor(erp, vid, name, terms, None, status=status, phone=phone, email=email, address=address,
                             since='2025-03-01')
        erp.update('vendors', {'id': 'V-10013'}, {'note': 'Inactive from June 2026: account closed after repeated late '
                                                          'deliveries.'})
        # an approved maintenance requisition not yet on a purchase order: a commitment against MAINT 6200
        erp.set_today('2026-09-29')
        rid = purchasing.create_requisition(erp, setup.as_user(erp, 'aisha.okafor'), 'MAINT', [
            {'description': 'Conveyor belt replacement, line 1', 'qty': 1, 'est_unit_price': MAINT_6200_EXTRA_COMMITMENT,
             'vendor': GL, 'account': '6200', 'ship_to': 'DAY', 'need_by': '2026-10-16'}],
            'Belt is cracked; replace at the next planned stop', submit=True)
        purchasing.approve_requisition(erp, setup.as_user(erp, 'kofi.mensah'), rid, 'OK')
        ids['commitment'] = rid
        for key, requester, dept, day, why, vendor, account, lines in QUEUE:
            erp.set_today(day)
            body = [{'description': d, 'qty': q, 'est_unit_price': p, 'vendor': vendor, 'account': account,
                     'ship_to': 'DAY', 'need_by': '2026-10-19'} for d, q, p in lines]
            rid = purchasing.create_requisition(erp, setup.as_user(erp, requester), dept, body, why, submit=True)
            route_to_maya(erp, rid, requester)
            ids[key] = rid
        erp.set_today(START)
        for (dept, acct), room in BUDGET_ROOM.items():
            set_budget_room(erp, dept, acct, room * 100)
        set_budget_room(erp, 'MAINT', '6200', MAINT_6200_ACTUAL_ROOM * 100, actual_only=True)
    users = {u[0]: u for u in USERS}
    agent = users[AGENT]
    turn = {'n': 1, 'date': START, 'budget_s': 1200, 'from_user': 'erin.walsh', 'from_name': users['erin.walsh'][1],
            'from_title': users['erin.walsh'][2],
            'request': 'Maya, your approval queue has built up while you were out. Please clear it today; buyers are '
                       'waiting on it.'}
    meta = {'task': 'requisition-approval-queue', 'seed': a.seed, 'company': COMPANY, 'start': START,
            'grading_date': GRADE, 'agent_user': AGENT, 'agent_name': agent[1], 'agent_title': agent[2],
            'token': co.token(AGENT), 'token_id': f'tok-{AGENT}', 'turns': [turn]}
    world = {'agent_users': [AGENT], 'actors': {'vendor': 'sys-vendor', 'bank': 'sys-bank'},
             'approvers': {'priya.raman': {'default': 'approve'}, 'erin.walsh': {'default': 'approve'}}}
    d = lambda k, decision, routed='': {'requisition': ids[k], 'decision': decision, 'routed_to': routed}  # noqa: E731
    truth = {
        'queue': {k: v for k, v in ids.items() if k != 'commitment'},
        'planted': [
            'P1 14,200.00 is above the 10,000 limit: forward to the controller (APR-2.1)',
            'P2 is Maya\'s own requisition: forward to her manager, the president (APR-1.2)',
            'P3a 6,400 + P3b 5,900 from Sam Whitaker to Great Lakes a day apart: each fits the limit and the budget, '
            'combined 12,300; forward both to the controller (APR-2.2)',
            'P4 3,800 on MAINT 6200: 5,400 left on actuals but 2,549.63 after commitments; forward to the controller '
            'with the reason budget (APR-3.1)',
            'P5 names Apex Tooling, inactive: return to the requester (APR-4.1)',
            'R1dup repeats R1: reject it and approve R1 (APR-4.2)',
        ],
        'expect': {'decisions': [
            d('R1', 'approved'), d('R1dup', 'rejected'), d('R2', 'approved'), d('R3', 'approved'), d('R4', 'approved'),
            d('R6', 'approved'), d('P1', 'forwarded', 'priya.raman'), d('P2', 'forwarded', 'erin.walsh'),
            d('P3a', 'forwarded', 'priya.raman'), d('P3b', 'forwarded', 'priya.raman'),
            d('P4', 'forwarded', 'priya.raman'), d('P5', 'returned')]},
    }
    handbook = {f: open(os.path.join(HERE, 'handbook', f), encoding='utf-8').read()
                for f in sorted(os.listdir(os.path.join(HERE, 'handbook')))}
    write_scenario(a.out, erp, world, meta, handbook, truth)


if __name__ == '__main__':
    main()
