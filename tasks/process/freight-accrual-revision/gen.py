#!/usr/bin/env python3
"""freight-accrual-revision: Omar Haddad, staff accountant. Wednesday 30 September 2026: book September's inbound
freight accruals, one entry per receipt, from the receipts in the ERP and the carrier's rate schedule. Friday 2
October: two of the facts behind them have changed; retract or adjust every accrual derived from them, and nothing
else, before the controller closes September.

  python gen.py --seed 0 --out DIR

Planted (docs/process/tasks.md, belief revision): the carrier's September schedule and an older August one (use the
month's); receipts from prepaid vendors that carry no accrual; a pallet of racking hardware from Great Lakes received
on 29 September. Between the turns the counterparties change two facts on Thursday 1 October: the warehouse reverses
the Great Lakes receipt as a receiving error (the pallet was addressed to a neighbour), and the carrier corrects the
September rate of lane L3 (Coastline Seals, every receipt on it). Turn 2 must reverse the misdelivered receipt's
accrual, reverse and rebook each lane-L3 accrual at the corrected rate (reversals dated 30 September), and leave the
other accruals standing.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

from bberp import comms, purchasing, setup  # noqa: E402
from procgen.company import build  # noqa: E402
from procgen.episode import write_scenario  # noqa: E402
from procgen.northgate import COMPANY, USERS, VENDORS, rng  # noqa: E402

START, TURN2, GRADE = '2026-09-30', '2026-10-02', '2026-10-05'
REVISED_ON = '2026-10-01'
MONTH = ('2026-09-01', '2026-09-30')
AGENT = 'omar.haddad'
V = {k: v[0] for k, v in VENDORS.items()}
NAME = {v[0]: v[1] for v in VENDORS.values()}
# lane, origin, shippers (vendor keys) on MVF's freight-collect schedule; every other vendor ships prepaid
LANES = [('L1', 'Dayton, OH', ['midstate', 'dayton']), ('L2', 'Toledo, OH', ['greatlakes']),
         ('L3', 'Portland, ME', ['coastline'])]
CORRECTED_LANE = 'L3'
CARRIER, CARRIER_ADDR = 'Miami Valley Freight Lines', 'billing@mvfreight.com'


def settings(seed: int) -> dict:
    r = rng(seed, 'freight-accrual-revision')
    sept = {'L1': r.choice([1.45, 1.55, 1.60, 1.65, 1.70]), 'L2': r.choice([1.95, 2.10, 2.25, 2.40]),
            'L3': r.choice([3.30, 3.40, 3.55, 3.65])}
    aug = {'L1': round(sept['L1'] - 0.10, 2), 'L2': sept['L2'], 'L3': round(sept['L3'] - 0.15, 2)}
    corrected = round(sept['L3'] - r.choice([0.45, 0.50, 0.60]), 2)
    racking = round(r.uniform(2200, 3900), 2)
    return {'sept': sept, 'aug': aug, 'corrected': corrected, 'racking': racking}


def accrual_cents(value_cents: int, pct: float) -> int:
    """FRT-1.2: value times the lane rate, to the nearest cent, half a cent up."""
    return int((Decimal(value_cents) * Decimal(str(pct)) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def fmt(cents: int) -> str:
    """How a projection writes ROUND(cents / 100.0, 2)."""
    return f'{cents / 100:.4f}'.rstrip('0').rstrip('.')


def schedule_body(month: str, rates: dict) -> str:
    rows = '\n'.join(f'{lane}    {origin:<14}  {", ".join(NAME[V[k]] for k in keys):<40}  {rates[lane]:.2f}%'
                     for lane, origin, keys in LANES)
    return (f'Northgate Valve Co., account NG-4471.\n\nFreight-collect rates for inbound deliveries to Dayton, {month}, '
            'as a percentage of the goods value of each delivery:\n\n'
            f'Lane  Origin          Shippers                                  Rate\n{rows}\n\n'
            'Deliveries from shippers not listed are not carried or billed by MVF. We bill each month\'s deliveries '
            'on the 12th of the following month.\n\nMiami Valley Freight Lines, customer accounts')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    s = settings(a.seed)
    planted: dict = {}

    def racking_order(erp, h) -> None:
        """A maintenance order the warehouse receives on 29 September; the pallet turns out not to be ours."""
        ctx = setup.as_user(erp, 'jordan.lee')
        po = purchasing.create_po(erp, ctx, V['greatlakes'], [
            {'description': 'Pallet racking hardware and anchors', 'qty': 1, 'unit_price': s['racking'],
             'account': '6200', 'department': 'MAINT', 'need_date': '2026-09-29'}], 'DAY')
        purchasing.send_po(erp, ctx, po)
        planted['po'] = po

    co = build(os.path.join(a.out, 'scenario.db'), seed=a.seed, start=START, close_through='2026-08',
               events={'2026-09-22': [racking_order]})
    erp = co.erp
    misdelivered = erp.val("SELECT id FROM receipts WHERE po_id = ? AND status = 'posted'", planted['po'])
    if not misdelivered:
        raise SystemExit('the planted Great Lakes order was not received on 29 September')
    with erp.tx():
        comms.deliver(erp, 'accounting', 'MVF rate schedule, August 2026', schedule_body('August 2026', s['aug']),
                      CARRIER, CARRIER_ADDR, '2026-08-03')
        comms.deliver(erp, 'accounting', 'MVF rate schedule, September 2026',
                      schedule_body('September 2026', s['sept']), CARRIER, CARRIER_ADDR, '2026-09-01')
        comms.deliver(erp, 'accounting', 'Corrected September rate for lane L3',
                      f'Northgate Valve Co., account NG-4471.\n\nOur September 2026 schedule overstated lane L3 '
                      f'(Portland, ME): the fuel surcharge was counted twice. The correct September 2026 rate for lane '
                      f'L3 is {s["corrected"]:.2f}%, not {s["sept"]["L3"]:.2f}%. Lanes L1 and L2 are unchanged. We will '
                      'bill September at the corrected rate on 12 October.\n\nMiami Valley Freight Lines, customer '
                      'accounts', CARRIER, CARRIER_ADDR, REVISED_ON)

    lane_of = {V[k]: lane for lane, _o, keys in LANES for k in keys}
    receipts = erp.all("SELECT r.id, r.status, p.vendor, (SELECT COALESCE(SUM(l.grni_cents), 0) FROM receipt_lines l "
                       "WHERE l.receipt_id = r.id) AS value_cents FROM receipts r JOIN purchase_orders p "
                       "ON p.id = r.po_id WHERE r.receipt_date BETWEEN ? AND ? ORDER BY r.id", *MONTH)
    booked, final = {}, {}
    for r in receipts:
        lane = lane_of.get(r['vendor'])
        booked[r['id']] = accrual_cents(r['value_cents'], s['sept'][lane]) if lane and r['status'] == 'posted' else 0
        rate = s['corrected'] if lane == CORRECTED_LANE else s['sept'].get(lane)
        final[r['id']] = 0 if r['id'] == misdelivered or not lane or r['status'] != 'posted' else \
            accrual_cents(r['value_cents'], rate)
    relaned = [r['id'] for r in receipts if lane_of.get(r['vendor']) == CORRECTED_LANE and r['status'] == 'posted']
    if len(relaned) < 2:
        raise SystemExit(f'seed {a.seed}: fewer than two September receipts on lane {CORRECTED_LANE}')
    changed = sorted([misdelivered] + relaned)
    unchanged = sorted(k for k, v in booked.items() if v and k not in changed)

    users = {u[0]: u for u in USERS}
    agent = users[AGENT]

    def turn(n, date, request):
        return {'n': n, 'date': date, 'budget_s': 1200, 'from_user': 'priya.raman',
                'from_name': users['priya.raman'][1], 'from_title': users['priya.raman'][2], 'request': request}
    meta = {'task': 'freight-accrual-revision', 'seed': a.seed, 'company': COMPANY, 'start': START,
            'grading_date': GRADE, 'agent_user': AGENT, 'agent_name': agent[1], 'agent_title': agent[2],
            'token': co.token(AGENT), 'token_id': f'tok-{AGENT}',
            'turns': [turn(1, START, "Please book September's inbound freight accruals today, from the receipts in the "
                                     "system and MVF's rate schedule. I'll review them and close September on "
                                     'Monday.'),
                      turn(2, TURN2, 'Before I close September on Monday, please make sure the freight accruals you '
                                     "booked on Wednesday still hold, and bring them up to date if they don't. Leave "
                                     'me a short note in freight-accruals.md saying which accruals you changed and '
                                     'why.')]}
    world = {'agent_users': [AGENT], 'actors': {'vendor': 'sys-vendor', 'bank': 'sys-bank'},
             'receipt_reversals': [{
                 'day': REVISED_ON, 'user': 'luis.ortega', 'receipt': misdelivered,
                 'reason': 'Receiving error: this pallet was addressed to Northgate Plastics next door, not to us, and '
                           'MVF collected it on 1 October. Great Lakes will ship our order again.'}]}
    total = sum(final.values())
    c = f'{s["corrected"]:.2f}'
    rate_re = re.escape(c[:-1]) + ('0?' if c.endswith('0') else c[-1]) + '%'   # 2.90% or 2.9%
    values = {'misdelivered': misdelivered, 'reversed_receipt': misdelivered,
              'corrected_rate_re': rate_re,
              'rates_september': s['sept'], 'rates_august': s['aug'], 'corrected_rate': s['corrected'],
              'revised_sources': [{'ref': rid, 'on': REVISED_ON} for rid in changed],
              'accrued_total': fmt(total)}
    truth = {
        'values': values, 'po': planted['po'],
        'planted': [
            f'September schedule L1 {s["sept"]["L1"]:.2f}%, L2 {s["sept"]["L2"]:.2f}%, L3 {s["sept"]["L3"]:.2f}%; the '
            f'August schedule (L1 {s["aug"]["L1"]:.2f}%, L3 {s["aug"]["L3"]:.2f}%) is not the month\'s (FRT-1.2)',
            'Receipts from Keystone, Ohio Packaging, Tri-County and Pacific Seal are prepaid: no accrual (FRT-1.1)',
            f'{misdelivered}: Great Lakes racking, {s["racking"]:,.2f}, received 29 Sep, reversed by the warehouse on '
            '1 Oct as a receiving error: reverse its accrual, book nothing (FRT-1.1, FRT-2.1)',
            f'Lane L3 corrected on 1 Oct from {s["sept"]["L3"]:.2f}% to {s["corrected"]:.2f}%: reverse and rebook '
            f'{", ".join(relaned)} (FRT-1.2, FRT-2.1, FRT-2.2)',
            f'Accruals that stay as booked: {", ".join(unchanged)} (FRT-2.3)'],
        'expect': {'accruals_by_receipt': [{'receipt': k, 'accrued': fmt(v)} for k, v in sorted(final.items())],
                   'accruals_reversed': [{'receipt': k} for k in changed],
                   'september_freight': [{'account': '2100', 'net': fmt(-total)}, {'account': '5100', 'net': fmt(total)}]},
        'absent': {'accruals_reversed': [{'receipt': k} for k in unchanged]},
    }
    handbook = {f: open(os.path.join(HERE, 'handbook', f), encoding='utf-8').read()
                for f in sorted(os.listdir(os.path.join(HERE, 'handbook')))}
    write_scenario(a.out, erp, world, meta, handbook, truth)


if __name__ == '__main__':
    main()
