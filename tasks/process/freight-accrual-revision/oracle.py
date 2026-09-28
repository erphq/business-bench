"""Reference policy and negative controls for freight-accrual-revision. Every policy acts only through the agent's
API with the agent's token, and reads its facts (receipts, the carrier's schedules and corrections) the way an agent
would: from the ERP and the accounting inbox.

Turn 1 books one accrual per September receipt from a vendor on the month's schedule (FRT-1.1 to FRT-1.3). Turn 2
recomputes each accrual from the sources as they now stand and, for exactly those whose figure changed, reverses the
entry dated 30 September and rebooks it when freight is still owed (FRT-2.1 to FRT-2.3), then writes the note."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from procgen.episode import Api

MONTH_END = '2026-09-30'
MONTH_LABEL = 'September 2026'
RECEIPT = re.compile(r'(?<![\w-])(RCV-\d+)(?!\w)')


def accrual_cents(value_cents: int, pct: float) -> int:
    return int((Decimal(value_cents) * Decimal(str(pct)) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Policy:
    schedule_month: str = MONTH_LABEL     # the schedule turn 1 reads (neg:august_rates reads last month's)
    revise: bool = True                   # turn 2 acts on changed sources
    reverse_all: bool = False             # turn 2 reverses every accrual and rebooks from scratch
    by_difference: bool = False           # turn 2 posts the difference beside the old entry
    reversal_dated_today: bool = False    # turn 2 dates reversals in October

    def __call__(self, turn: int, api: Api, ws: str, meta: dict) -> None:
        (self.book if turn == 1 else self.update)(api, ws)

    # ------------------------------------------------------------------------------------------------ facts
    def rates(self, api: Api) -> dict[str, tuple[str, float]]:
        """Vendor id -> (lane, rate %) from the month's schedule with any later corrections applied."""
        vendors = {v['name']: v['id'] for v in api.items('/vendors')}
        msgs = [api.get(f'/inbox/{m["id"]}') for m in api.items('/inbox', box='accounting')]
        sched = next(m for m in msgs if m['subject'].startswith('MVF rate schedule') and
                     self.schedule_month in m['subject'])
        lanes: dict[str, float] = {}
        shippers: dict[str, str] = {}
        for line in sched['body'].splitlines():
            m = re.match(r'^(L\d)\s{2,}(.+?)\s{2,}(.+?)\s{2,}([\d.]+)%\s*$', line)
            if m:
                lanes[m.group(1)] = float(m.group(4))
                for name in m.group(3).split(', '):
                    shippers[vendors[name.strip()]] = m.group(1)
        for m in msgs:
            c = re.search(r'correct (\w+ \d{4}) rate for lane (L\d) is ([\d.]+)%', m['body'])
            if c and c.group(1) == MONTH_LABEL:
                lanes[c.group(2)] = float(c.group(3))
        return {v: (lane, lanes[lane]) for v, lane in shippers.items()}

    def receipts(self, api: Api) -> dict[str, dict]:
        """September receipts with vendor, status and value at PO prices (cents)."""
        vendor_of = {p['id']: p['vendor'] for p in api.items('/purchase-orders')}
        out = {}
        for r in api.items('/receipts'):
            if not ('2026-09-01' <= r['receipt_date'] <= MONTH_END):
                continue
            full = api.get(f'/receipts/{r["id"]}')
            out[r['id']] = {'vendor': vendor_of[r['po_id']], 'status': full['status'],
                            'value_cents': sum(l['grni_cents'] for l in full['lines'])}
        return out

    def owed(self, api: Api) -> dict[str, tuple[int, str, float]]:
        """Receipt -> (accrual cents, lane, rate) for every September receipt that carries one now."""
        rates, out = self.rates(api), {}
        for rid, r in sorted(self.receipts(api).items()):
            if r['status'] == 'posted' and r['vendor'] in rates:
                lane, pct = rates[r['vendor']]
                out[rid] = (accrual_cents(r['value_cents'], pct), lane, pct)
        return out

    def _book(self, api: Api, rid: str, cents: int, lane: str, pct: float, vendor: str, note: str = '') -> str:
        amount = cents / 100
        je = api.post('/journal-entries', {
            'entry_date': MONTH_END, 'memo': f'Freight accrual {rid}, {vendor}, lane {lane} at {pct:.2f}%{note}',
            'lines': [{'account': '5100', 'debit': amount}, {'account': '2100', 'credit': amount}]})
        api.post(f'/journal-entries/{je["id"]}/post')
        return je['id']

    # ------------------------------------------------------------------------------------------------ turns
    def book(self, api: Api, ws: str) -> None:
        names = {v['id']: v['name'] for v in api.items('/vendors')}
        vendor_of = {p['id']: p['vendor'] for p in api.items('/purchase-orders')}
        receipt_po = {r['id']: r['po_id'] for r in api.items('/receipts')}
        for rid, (cents, lane, pct) in self.owed(api).items():
            if cents:
                self._book(api, rid, cents, lane, pct, names[vendor_of[receipt_po[rid]]])

    def update(self, api: Api, ws: str) -> None:
        me = api.get('/whoami')['id']
        names = {v['id']: v['name'] for v in api.items('/vendors')}
        vendor_of = {p['id']: p['vendor'] for p in api.items('/purchase-orders')}
        receipts = {r['id']: r for r in api.items('/receipts')}
        owed = self.owed(api)
        changes = []
        live = [je for je in api.items('/journal-entries', period='2026-09', source='manual')
                if je['preparer'] == me and je['status'] == 'posted']
        for je in live:
            m = RECEIPT.search(je['memo'] or '')
            if not m or not self.revise:
                continue
            rid = m.group(1)
            booked = round(api.get(f'/journal-entries/{je["id"]}')['total'] * 100)
            now, lane, pct = owed.get(rid, (0, None, None))
            if now == booked and not self.reverse_all:
                continue
            r = receipts[rid]
            vendor = names[vendor_of[r['po_id']]]
            why = (f'{rid} was reversed on {r["reversed_on"]} ({r["reversal_reason"]})' if r['status'] == 'reversed'
                   else f'MVF corrected the lane {lane} rate to {pct:.2f}%' if now != booked else 'rebooked with the rest')
            if self.by_difference and now != booked:
                diff = (now - booked) / 100
                lines = ([{'account': '5100', 'debit': diff}, {'account': '2100', 'credit': diff}] if diff > 0 else
                         [{'account': '2100', 'debit': -diff}, {'account': '5100', 'credit': -diff}])
                adj = api.post('/journal-entries', {'entry_date': MONTH_END, 'lines': lines,
                                                    'memo': f'Freight accrual adjustment {rid}, {vendor}: {why}'})
                api.post(f'/journal-entries/{adj["id"]}/post')
                changes.append((rid, vendor, booked, now, why))
                continue
            body = {'reason': why}
            if not self.reversal_dated_today:
                body['reverse_date'] = MONTH_END
            api.post(f'/journal-entries/{je["id"]}/reverse', body)
            if now:
                self._book(api, rid, now, lane, pct, vendor, note=f' (replaces {je["id"]})')
            changes.append((rid, vendor, booked, now, why))
        with open(os.path.join(ws, 'freight-accruals.md'), 'w', encoding='utf-8') as f:
            f.write('# September freight accruals: changes since Wednesday\n\n')
            if not changes:
                f.write('No changes: every accrual still matches its receipt and rate.\n')
            for rid, vendor, booked, now, why in changes:
                if now:
                    f.write(f'- {rid} ({vendor}): reversed the {booked / 100:,.2f} accrual and rebooked {now / 100:,.2f} '
                            f'because {why} (FRT-2.1).\n')
                else:
                    f.write(f'- {rid} ({vendor}): reversed the {booked / 100:,.2f} accrual and booked nothing, because '
                            f'{why} (FRT-1.1, FRT-2.1).\n')
            f.write('\nEvery other accrual stands as booked on Wednesday (FRT-2.3).\n')


ORACLE = Policy()
POLICIES = {
    'oracle': ORACLE,
    'neg:ignore_revision': replace(ORACLE, revise=False),
    'neg:reverse_everything': replace(ORACLE, reverse_all=True),
    'neg:adjust_without_reversal': replace(ORACLE, by_difference=True),
    'neg:reverse_in_october': replace(ORACLE, reversal_dated_today=True),
    'neg:august_rates': replace(ORACLE, schedule_month='August 2026'),
}
