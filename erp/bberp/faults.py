"""Declared, deterministic transport faults on the agent API: the process track's fault-injection condition.

A fault plan is written as a comma-separated spec. Explicit rules name a kind, a request pattern and which matching
request (1-based, counted per rule over the whole episode) is hit:

    lost_response:POST /payment-runs/*/release@1,fail_before:POST /payments@2
    slow:POST /ap-invoices@1,delay=130

Profiles fault a deterministic pseudo-random share of every write:

    flaky-writes:seed=3,rate=0.1[,lost=0.5][,max=N]

Kinds:
  fail_before    the request is answered 503 and never reaches the ERP: nothing is committed.
  lost_response  the request runs and commits; the client gets the same 503 instead of the success body.
  slow           the request runs and commits; the real response is sent after `delay` seconds (default 130, beyond
                 the `erp` command's 120-second client timeout).

The fault layer sits in the HTTP handler, outside the ERP's transactions: a fault never interrupts a transaction or a
COMMIT. `*` in a pattern matches one path segment, `**` the rest of the path, and a method of `*` any method. Given
the plan and the sequence of requests, which requests are hit is fixed. A 503 from fail_before and one from
lost_response are byte-identical, and neither says it was injected. Every fault is written to a sidecar log (JSON
lines) that lives with the runner's files, never in the agent's workspace or the ERP database.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field

KINDS = ('fail_before', 'lost_response', 'slow')
WRITE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')
PROFILES = ('flaky-writes',)
DEFAULT_DELAY_S = 130.0

UNAVAILABLE_BODY = json.dumps({'type': 'https://businessbench.org/erp/errors/service_unavailable',
                               'title': 'service_unavailable', 'status': 503,
                               'detail': 'the service is temporarily unavailable; try again later'}).encode()
UNAVAILABLE_HEADERS = {'Content-Type': 'application/problem+json', 'Retry-After': '1'}


class FaultSpecError(ValueError):
    pass


@dataclass
class Rule:
    kind: str
    method: str
    pattern: tuple
    nth: int
    delay: float = DEFAULT_DELAY_S
    seen: int = 0

    def text(self) -> str:
        s = f'{self.kind}:{self.method} /{"/".join(self.pattern)}@{self.nth}'
        return s + (f',delay={self.delay:g}' if self.kind == 'slow' and self.delay != DEFAULT_DELAY_S else '')


@dataclass
class Profile:
    name: str
    seed: int = 0
    rate: float = 0.1
    lost: float = 0.5
    max: int | None = None
    fired: int = 0

    def text(self) -> str:
        s = f'{self.name}:seed={self.seed},rate={self.rate:g},lost={self.lost:g}'
        return s + (f',max={self.max}' if self.max is not None else '')


def _segments(path: str) -> tuple:
    return tuple(s for s in path.split('?', 1)[0].strip('/').split('/') if s)


def _match(pattern: tuple, path: tuple) -> bool:
    for i, p in enumerate(pattern):
        if p == '**':
            return True
        if i >= len(path) or (p != '*' and p != path[i]):
            return False
    return len(pattern) == len(path)


def _unit(*parts) -> float:
    """A number in [0, 1) fixed by its inputs."""
    h = hashlib.sha256(':'.join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], 'big') / 2 ** 64


def _params(tokens: list[str], allowed: dict) -> dict:
    out = {}
    for t in tokens:
        k, sep, v = t.partition('=')
        k = k.strip()
        if not sep or k not in allowed:
            raise FaultSpecError(f'unknown fault parameter {t!r}; expected one of {sorted(allowed)}')
        try:
            out[k] = allowed[k](v.strip())
        except ValueError:
            raise FaultSpecError(f'bad value in {t!r}')
    return out


@dataclass
class FaultPlan:
    rules: list = field(default_factory=list)
    profiles: list = field(default_factory=list)
    writes: int = 0
    requests: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def parse(cls, spec: str | None) -> 'FaultPlan | None':
        """None for an empty spec or 'none': the default, fault-free condition."""
        spec = (spec or '').strip()
        if not spec or spec.lower() == 'none':
            return None
        items: list[list[str]] = []
        for tok in (t.strip() for t in spec.split(',')):
            if not tok:
                continue
            if ':' not in tok and '=' in tok and ' ' not in tok and items:
                items[-1].append(tok)          # a parameter of the item before it
            else:
                items.append([tok])
        plan = cls()
        for head, *params in items:
            kind, sep, rest = head.partition(':')
            kind = kind.strip()
            if kind in PROFILES:
                if not sep:
                    rest = ''
                p = _params([x for x in [rest.strip()] + params if x],
                            {'seed': int, 'rate': float, 'lost': float, 'max': int})
                if not 0 <= p.get('rate', 0.1) <= 1 or not 0 <= p.get('lost', 0.5) <= 1:
                    raise FaultSpecError('rate and lost are fractions between 0 and 1')
                plan.profiles.append(Profile(kind, **p))
                continue
            if kind not in KINDS or not sep:
                raise FaultSpecError(f'unknown fault {head!r}; kinds are {", ".join(KINDS)}, profiles '
                                     f'{", ".join(PROFILES)}')
            target, at, nth = rest.strip().rpartition('@') if '@' in rest else (rest.strip(), '', '1')
            method, _, path = target.strip().partition(' ')
            if not path.strip().startswith('/'):
                raise FaultSpecError(f'expected "{kind}:METHOD /path[@n]", got {head!r}')
            try:
                n = int(nth)
            except ValueError:
                raise FaultSpecError(f'bad request number in {head!r}')
            if n < 1:
                raise FaultSpecError(f'request numbers start at 1 in {head!r}')
            extra = _params(params, {'delay': float})
            if extra and kind != 'slow':
                raise FaultSpecError(f'delay applies to slow faults only ({head!r})')
            plan.rules.append(Rule(kind, method.strip().upper(), _segments(path.strip()), n, **extra))
        return plan

    def canonical(self) -> str:
        return ','.join([r.text() for r in self.rules] + [p.text() for p in self.profiles])

    def decide(self, method: str, path: str) -> tuple[str, float] | None:
        """Called once per request, in arrival order. Returns (kind, delay) for a faulted request, else None."""
        segs = _segments(path)
        with self.lock:
            self.requests += 1
            hit = None
            for r in self.rules:
                if (r.method in ('*', method)) and _match(r.pattern, segs):
                    r.seen += 1
                    if hit is None and r.seen == r.nth:
                        hit = (r.kind, r.delay)
            if method in WRITE_METHODS:
                self.writes += 1
                for p in self.profiles:
                    if hit is None and (p.max is None or p.fired < p.max) and _unit(p.seed, 'w', self.writes) < p.rate:
                        p.fired += 1
                        hit = ('lost_response' if _unit(p.seed, 'k', self.writes) < p.lost else 'fail_before',
                               DEFAULT_DELAY_S)
            return hit


class FaultLog:
    """Append-only JSON lines, one per injected fault, flushed as written."""

    def __init__(self, path: str | None):
        self.path, self.lock, self.n = path, threading.Lock(), 0

    def write(self, rec: dict) -> None:
        with self.lock:
            self.n += 1
            rec = {'seq': self.n, **rec}
            if self.path:
                with open(self.path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(rec, sort_keys=True) + '\n')


def body_digest(body: bytes) -> str | None:
    """Canonical hash of a JSON body, comparable with the audit log's `request` column."""
    if not body or not body.strip():
        return None
    try:
        return hashlib.sha256(json.dumps(json.loads(body.decode('utf-8')), sort_keys=True, default=str).encode()
                              ).hexdigest()
    except (ValueError, UnicodeDecodeError):
        return hashlib.sha256(body).hexdigest()


def serve_faulted(plan: FaultPlan, log: FaultLog, erp, handle, method: str, target: str, headers: dict, body: bytes):
    """Run one request under the plan. Returns (status, headers, body, delay_s). `handle` is api.handle."""
    hit = plan.decide(method, target)
    if hit is None:
        status, hdr, out = handle(erp, method, target, headers, body)
        return status, hdr, out, 0.0
    kind, delay = hit
    rec = {'kind': kind, 'method': method, 'path': target.split('?', 1)[0], 'body_sha256': body_digest(body),
           'idem_key': {k.lower(): v for k, v in headers.items()}.get('idempotency-key'),
           'business_date': erp.today}
    with erp.lock:
        rec['audit_before'] = erp.val('SELECT COALESCE(MAX(id), 0) FROM audit_events')
    if kind == 'fail_before':
        log.write({**rec, 'served_status': None, 'committed': False, 'client_status': 503})
        return 503, dict(UNAVAILABLE_HEADERS), UNAVAILABLE_BODY, 0.0
    status, hdr, out = handle(erp, method, target, headers, body)
    with erp.lock:
        rec['audit_after'] = erp.val('SELECT COALESCE(MAX(id), 0) FROM audit_events')
    committed = method in WRITE_METHODS and 200 <= status < 300
    if kind == 'lost_response':
        log.write({**rec, 'served_status': status, 'committed': committed, 'client_status': 503})
        return 503, dict(UNAVAILABLE_HEADERS), UNAVAILABLE_BODY, 0.0
    log.write({**rec, 'served_status': status, 'committed': committed, 'client_status': status, 'delay_s': delay})
    return status, hdr, out, delay
