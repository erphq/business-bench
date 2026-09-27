"""Reference policy and negative controls for requisition-approval-queue. Every policy acts only through the
agent's API with the agent's token."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

from procgen.episode import Api, ApiError


@dataclass(frozen=True)
class Policy:
    duplicates: bool = True
    vendors: bool = True
    own_to_manager: bool = True
    splits: bool = True
    budget: bool = True

    def __call__(self, turn: int, api: Api, ws: str, meta: dict) -> None:
        me = api.get('/whoami')
        limit = me['approval_limits'].get('requisition', 0)
        today = me['business_date']
        queue = [api.get(f'/requisitions/{a["doc_id"]}') for a in api.items('/approvals')
                 if a['doc_type'] == 'requisition']
        queue.sort(key=lambda r: r['id'])
        vendors = {v['id']: v for v in api.items('/vendors')}
        approvers = []
        for u in api.items('/users'):
            full = api.get(f'/users/{u["id"]}')
            lim = full['approval_limits'].get('requisition')
            if lim and u['id'] != me['id']:
                approvers.append((lim, u['id']))
        approvers.sort()
        controller = next(u['id'] for u in api.items('/users') if 'controller' in u['roles'])

        def covering(total: float) -> str:
            return next(uid for lim, uid in approvers if lim >= total)

        def signature(r):
            return (r['requester'], tuple((l['sku'], l['description'], l['qty'], l['est_unit_price'], l['vendor'])
                                          for l in r['lines']))
        seen, dups = {}, set()
        for r in queue:
            s = signature(r)
            if s in seen and self.duplicates:
                dups.add(r['id'])
            seen.setdefault(s, r['id'])

        def vendor_of(r):
            return r['lines'][0]['vendor']
        groups: dict[tuple, list] = {}
        for r in queue:
            if r['id'] not in dups:
                groups.setdefault((r['requester'], vendor_of(r)), []).append(r)

        def within_five(a, b):
            d1, d2 = sorted((date.fromisoformat(a['created_on']), date.fromisoformat(b['created_on'])))
            n, d = 0, d1
            while d < d2:
                d += timedelta(days=1)
                n += d.weekday() < 5
            return n <= 5
        split_total = {}
        if self.splits:
            for rs in groups.values():
                for r in rs:
                    mates = [x for x in rs if within_five(r, x)]
                    if len(mates) > 1:
                        split_total[r['id']] = sum(x['total'] for x in mates)
        for r in queue:
            rid = r['id']
            if rid in dups:
                api.post(f'/requisitions/{rid}/reject', {'reason': 'duplicate', 'note': 'repeats an open requisition '
                                                                                         '(APR-4.2)'})
                continue
            v = vendors.get(vendor_of(r) or '')
            if self.vendors and v and (v['status'] != 'active' or v['quality_hold']):
                api.post(f'/requisitions/{rid}/return', {'reason': f'{v["name"]} is {"inactive" if v["status"] != "active" else "on quality hold"}; '
                                                                   'choose an approved vendor (APR-4.1)'})
                continue
            if r['requester'] == me['id']:
                to = me['manager'] if self.own_to_manager else controller
                api.post(f'/requisitions/{rid}/forward', {'to': to, 'reason': 'my own requisition (APR-1.2)'})
                continue
            total = split_total.get(rid, r['total'])
            if total > limit:
                api.post(f'/requisitions/{rid}/forward', {'to': covering(total), 'reason':
                         'combined with related requisitions (APR-2.2)' if rid in split_total else 'above my limit (APR-2.1)'})
                continue
            if self.budget and self._over_budget(api, r, today):
                api.post(f'/requisitions/{rid}/forward', {'to': controller, 'reason': 'budget (APR-3.1)'})
                continue
            try:
                api.post(f'/requisitions/{rid}/approve', {'note': 'OK'})
            except ApiError as e:
                if e.code == 'over_limit':
                    api.post(f'/requisitions/{rid}/forward', {'to': covering(r['total']), 'reason': 'above my limit'})
                else:
                    raise

    @staticmethod
    def _over_budget(api: Api, r: dict, today: str) -> bool:
        need: dict[str, float] = {}
        for l in r['lines']:
            if l['account'] != '1500':
                need[l['account']] = need.get(l['account'], 0) + l['amount_cents'] / 100
        if not need:
            return False
        report = api.get('/reports/budget-vs-actual', department=r['department'], period_to=today[:7])
        for acct, amount in need.items():
            row = next((x for x in report['lines'] if x['account'] == acct), None)
            remaining = float(row['remaining']) if row else 0.0
            if amount > remaining:
                return True
        return False


ORACLE = Policy()
NAIVE = Policy(duplicates=False, vendors=False, own_to_manager=False, splits=False, budget=False)
POLICIES = {
    'oracle': ORACLE,
    'neg:approve_within_limit': NAIVE,
    'neg:ignore_budget': replace(ORACLE, budget=False),
    'neg:ignore_splits': replace(ORACLE, splits=False),
    'neg:own_to_controller': replace(ORACLE, own_to_manager=False),
    'neg:approve_duplicates': replace(ORACLE, duplicates=False),
    'neg:ignore_vendor_status': replace(ORACLE, vendors=False),
}
