"""Reference weekly planning cycle and negative controls for mrp-planner-week. Every policy acts only through the
agent's API with the agent's token."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from procgen.episode import Api


@dataclass(frozen=True)
class Policy:
    read_inbox: bool = True
    firm_only: bool = True
    action_messages: bool = True

    def __call__(self, turn: int, api: Api, ws: str, meta: dict) -> None:
        if self.read_inbox:
            for m in api.items('/inbox', box='planning'):
                if m['disposition']:
                    continue
                msg = api.get(f'/inbox/{m["id"]}')
                change = re.search(r'\(your ([A-Z0-9-]+)\) is (\d+) working days', msg['body'])
                if change:
                    api.patch(f'/items/{change.group(1)}', {'lead_time_days': int(change.group(2))})
                api.post(f'/inbox/{m["id"]}/disposition', {'disposition': 'processed' if change else 'no_action'})
        api.post('/mrp/runs', {'horizon_weeks': 8, 'firm_days': 5})
        asked = {(r['kind'], r['po_id'], r['po_line']) for r in api.items('/vendor-requests')}
        for s in api.items('/mrp/suggestions', status='open'):
            if s['kind'] in ('planned_po', 'planned_wo'):
                if self.firm_only and not s['firm']:
                    continue
                made = api.post(f'/mrp/suggestions/{s["id"]}/release')['created']
                if s['kind'] == 'planned_po' and s['late'] and self.action_messages:
                    po = api.get(f'/purchase-orders/{made}')
                    api.post('/vendor-requests', {'vendor': po['vendor'], 'kind': 'expedite', 'po_id': made,
                                                  'po_line': 1, 'wanted_date': s['need_date'],
                                                  'note': f'late planned order from {s["id"]} (PLN-2.2)'})
                    asked.add(('expedite', made, 1))
            elif self.action_messages:
                po_id, line = s['ref'].split('/')
                if (s['kind'], po_id, int(line)) in asked:
                    continue
                po = api.get(f'/purchase-orders/{po_id}')
                api.post('/vendor-requests', {'vendor': po['vendor'], 'kind': s['kind'], 'po_id': po_id,
                                              'po_line': int(line),
                                              **({'wanted_date': s['need_date']} if s['kind'] != 'cancel' else {}),
                                              'note': f'MRP {s["kind"]} from {s["id"]} (PLN-3.1)'})
                asked.add((s['kind'], po_id, int(line)))


ORACLE = Policy()
POLICIES = {
    'oracle': ORACLE,
    'neg:ignore_inbox': replace(ORACLE, read_inbox=False),
    'neg:release_everything': replace(ORACLE, firm_only=False),
    'neg:ignore_action_messages': replace(ORACLE, action_messages=False),
}
