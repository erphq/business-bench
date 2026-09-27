#!/usr/bin/env python3
"""mrp-planner-week: Jordan Lee, production planner, runs the weekly MRP cycle on Monday 12 October 2026.

  python gen.py --seed 0 --out DIR

Planted: Dayton Castings confirms by email on Friday that CAST-2-BODY now takes 25 workdays, not 15; the item record
still says 15, so running MRP before updating it releases the castings too late. Northgate is already behind on
2-inch valves, so several castings are late and need expediting; Dayton declines expedites. A casting purchase
order arrives two weeks before it is needed (defer). A newsletter with no planning content sits beside the note.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

from bberp import comms  # noqa: E402
from procgen.company import build  # noqa: E402
from procgen.episode import write_scenario  # noqa: E402
from procgen.northgate import COMPANY, USERS, VENDORS  # noqa: E402

START, GRADE = '2026-10-12', '2026-10-13'
AGENT = 'jordan.lee'
NEW_LEAD = 25


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    co = build(os.path.join(a.out, 'scenario.db'), seed=a.seed, start=START)
    erp = co.erp
    with erp.tx():
        old = erp.val("SELECT lead_time_days FROM items WHERE sku = 'CAST-2-BODY'")
        comms.deliver(erp, 'planning', 'Lead time change: 2in valve bodies',
                      'Hello Jordan,\n\nA furnace rebuild at our Dayton foundry means that, effective immediately, our '
                      f'lead time for the 2in valve body (your CAST-2-BODY) is {NEW_LEAD} working days, up from {old}. '
                      'The 1in body (CAST-1-BODY) is unchanged. Orders already confirmed keep their dates.\n\n'
                      'We expect to be back to normal in January and will write again then.\n\nTed Novak\nCustomer '
                      'service, Dayton Castings', 'Ted Novak', 'sales@daytoncastings.com', '2026-10-09')
        comms.deliver(erp, 'planning', 'Mid-State Metals: 2027 price list',
                      'Dear customer,\n\nOur 2027 price list will be published in December and take effect on 1 '
                      'January 2027. Current price agreements stay in force until then.\n\nMid-State Metals',
                      'Mid-State Metals', 'news@midstatemetals.com', '2026-10-09')
    users = {u[0]: u for u in USERS}
    agent = users[AGENT]

    def turn(n, date, request):
        return {'n': n, 'date': date, 'budget_s': 1500, 'from_user': 'dana.whitfield',
                'from_name': users['dana.whitfield'][1], 'from_title': users['dana.whitfield'][2], 'request': request}
    meta = {'task': 'mrp-planner-week', 'seed': a.seed, 'company': COMPANY, 'start': START, 'grading_date': GRADE,
            'agent_user': AGENT, 'agent_name': agent[1], 'agent_title': agent[2], 'token': co.token(AGENT),
            'token_id': f'tok-{AGENT}',
            'turns': [turn(1, '2026-10-12', 'Morning Jordan. Please do the weekly planning cycle. A couple of vendor '
                                            'notes came in on Friday; they are in the planning inbox.')]}
    world = {'agent_users': [AGENT], 'actors': {'vendor': 'sys-vendor', 'bank': 'sys-bank'},
             'vendor_default': {'ack_delay': 1, 'ship_early': False, 'invoice': {'delay': 2},
                                'requests': {'expedite': {'accept': True}}},
             'vendors': {VENDORS['dayton'][0]: {'requests': {'expedite': {'accept': False},
                                                             'defer': {'accept': True}}}}}
    truth = {
        'planted': [f'CAST-2-BODY lead time {old} -> {NEW_LEAD} workdays by Dayton email on 9 Oct: update the item '
                    'before running MRP (PLN-1.1)',
                    'Release only firm planned orders, with MRP quantities and need dates (PLN-2.1)',
                    'Late planned purchase orders: release and ask the vendor to expedite (PLN-2.2); Dayton declines',
                    'Casting PO arriving 19 Oct is needed in November: ask Dayton to defer (PLN-3.1)'],
        'expect': {'planning_data': [{'sku': 'CAST-2-BODY', 'lead_time_days': str(NEW_LEAD)}]},
    }
    handbook = {f: open(os.path.join(HERE, 'handbook', f), encoding='utf-8').read()
                for f in sorted(os.listdir(os.path.join(HERE, 'handbook')))}
    write_scenario(a.out, erp, world, meta, handbook, truth)


if __name__ == '__main__':
    main()
