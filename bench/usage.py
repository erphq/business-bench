#!/usr/bin/env python3
"""Token usage extraction per harness.

proto : <ws>/.proto-logs/*.full.jsonl  RESPONSE_FULL records carry usage per request/model
codex : <out>/codex_events.jsonl        turn.completed usage, or last token_count total
"""
import glob, json, os

def _empty():
    return {'requests': 0, 'input': 0, 'cached_input': 0, 'output': 0, 'reasoning': 0, 'by_model': {}}

def proto_usage(ws: str, out: str) -> dict:
    u = _empty()
    for path in glob.glob(os.path.join(ws, '.proto-logs', '*.full.jsonl')):
        for line in open(path, encoding='utf-8', errors='replace'):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('type') != 'RESPONSE_FULL':
                continue
            us = (r.get('response') or {}).get('usage') or {}
            m = r.get('model', '?')
            bm = u['by_model'].setdefault(m, {'requests': 0, 'input': 0, 'cached_input': 0, 'output': 0, 'reasoning': 0})
            pt, ct = int(us.get('promptTokens') or 0), int(us.get('completionTokens') or 0)
            cached, reas = int(us.get('cachedTokens') or 0), int(us.get('reasoningTokens') or 0)
            for d in (u, bm):
                d['requests'] += 1; d['input'] += pt; d['cached_input'] += cached; d['output'] += ct; d['reasoning'] += reas
    return u

def codex_usage(ws: str, out: str) -> dict:
    u = _empty()
    path = os.path.join(out, 'codex_events.jsonl')
    if not os.path.exists(path):
        return u
    last_total = None
    turn_sum = None
    model = None
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            e = json.loads(line)
        except Exception:
            continue
        t = e.get('type', '')
        if t == 'thread.started' or t == 'session_configured':
            model = e.get('model') or model
        if t == 'turn.completed' and isinstance(e.get('usage'), dict):
            us = e['usage']
            turn_sum = turn_sum or {'input': 0, 'cached_input': 0, 'output': 0}
            turn_sum['input'] += int(us.get('input_tokens') or 0)
            turn_sum['cached_input'] += int(us.get('cached_input_tokens') or 0)
            turn_sum['output'] += int(us.get('output_tokens') or 0)
        info = e.get('info') if t == 'token_count' else None
        if isinstance(info, dict) and isinstance(info.get('total_token_usage'), dict):
            tt = info['total_token_usage']
            last_total = {'input': int(tt.get('input_tokens') or 0),
                          'cached_input': int(tt.get('cached_input_tokens') or 0),
                          'output': int(tt.get('output_tokens') or 0),
                          'reasoning': int(tt.get('reasoning_output_tokens') or 0)}
    pick = turn_sum or last_total
    if pick:
        u.update({k: pick.get(k, 0) for k in ('input', 'cached_input', 'output', 'reasoning')})
        u['requests'] = 1
        u['by_model'] = {model or 'gpt-5.6-sol': dict(pick)}
    return u

EXTRACTORS = {'proto': proto_usage, 'codex': codex_usage}

def cost_usd(usage: dict, prices: dict) -> float | None:
    total = 0.0; known = False
    for m, d in usage.get('by_model', {}).items():
        p = prices.get(m)
        if not p or p.get('input') is None:
            return None
        known = True
        uncached = max(d.get('input', 0) - d.get('cached_input', 0), 0)
        total += uncached * p['input'] / 1e6
        total += d.get('cached_input', 0) * (p.get('cached_input') or p['input']) / 1e6
        total += d.get('output', 0) * p['output'] / 1e6
    return round(total, 4) if known else None
