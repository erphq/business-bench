"""Reference analysis and negative controls for margin-bridge. Read-only: every policy only reads the ledger through
the agent's API and writes answer.md in the workspace."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace

from procgen.episode import Api

REVENUE = ('4000', '4100', '4200')
COST = ('5000', '5050', '5060', '5070', '5080', '5100', '5150')


@dataclass(frozen=True)
class Policy:
    cost_accounts: tuple = COST
    drivers: tuple = ('price', 'rebate', 'writeoff', 'freight')
    driver_month: str = '2026-09'

    def __call__(self, turn: int, api: Api, ws: str, meta: dict) -> None:
        gm = {}
        for p in ('2026-08', '2026-09'):
            rows = {r['account']: r['balance_cents'] for r in api.get('/reports/trial-balance', period=p)['accounts']}
            rev = -sum(rows.get(a, 0) for a in REVENUE)
            cost = sum(rows.get(a, 0) for a in self.cost_accounts)
            gm[p] = (rev - cost) / rev * 100
        lines = [f'# Why gross margin fell in September\n',
                 f'Gross margin was {gm["2026-08"]:.1f}% in August and {gm["2026-09"]:.1f}% in September '
                 f'(RPT-1.1, RPT-1.2).\n', 'Discrete causes in September (RPT-2.1):\n']
        month = self.driver_month

        def entries(account):
            out = []
            for je in api.items('/journal-entries', period=month, account=account):
                full = api.get(f'/journal-entries/{je["id"]}')
                amt = sum(l['debit_cents'] - l['credit_cents'] for l in full['lines'] if l['account'] == account)
                out.append((full, amt))
            return out
        if 'price' in self.drivers:
            ppv, detail = 0, None
            for full, amt in entries('5050'):
                m = re.search(r'against (PO-\d+)', full['memo'] or '')
                if not m or not amt:
                    continue
                po = api.get(f'/purchase-orders/{m.group(1)}')
                skus = {l['sku'] for l in po['lines']}
                if 'CAST-1-BODY' in skus:
                    ppv += amt
                    detail = po['vendor']
            agreements = api.items('/price-agreements', sku='CAST-1-BODY')
            new = max(agreements, key=lambda a: a['valid_from'])
            old = min(agreements, key=lambda a: a['valid_from'])
            lines.append(f'- Dayton Castings ({detail}) raised the CAST-1-BODY casting price from {old["unit_price"]:.2f} '
                         f'to {new["unit_price"]:.2f} on {new["valid_from"]}: {ppv / 100:,.2f} of purchase price '
                         f'variance in 5050 on September casting receipts.\n')
        if 'rebate' in self.drivers:
            for full, amt in entries('4200'):
                lines.append(f'- Harbor Supply volume rebate accrued in 4200 ({full["id"]}): {amt / 100:,.2f}. '
                             f'{full["memo"]}.\n')
        if 'writeoff' in self.drivers:
            for full, amt in entries('5080'):
                lines.append(f'- Scrapped finished goods written off in 5080 ({full["source_ref"]}): {amt / 100:,.2f}. '
                             f'{full["memo"]}.\n')
        if 'freight' in self.drivers:
            for full, amt in entries('5100'):
                lines.append(f'- Air freight on expedited castings in 5100 (from {full["source_ref"]}): '
                             f'{amt / 100:,.2f}. {full["memo"]}.\n')
        lines.append('\nThe rest of the change is ordinary movement in volume and mix (RPT-2.2).\n')
        with open(os.path.join(ws, 'answer.md'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


ORACLE = Policy()
POLICIES = {
    'oracle': ORACLE,
    'neg:cogs_only': replace(ORACLE, cost_accounts=('5000',), drivers=()),
    'neg:revenue_side_only': replace(ORACLE, drivers=('rebate',)),
    'neg:miss_price_increase': replace(ORACLE, drivers=('rebate', 'writeoff', 'freight')),
    'neg:august_amounts': replace(ORACLE, driver_month='2026-08'),
}
