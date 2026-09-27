"""Episodes: the scenario directory, a running bb-erp server, the turn preamble, and a client for oracle policies.

A scenario directory (written by a task's gen.py, completed by the runner with the oracle's reference) holds:
  scenario.db     the company at the start of turn 1
  world.json      counterparty profiles (never visible to the agent)
  meta.json       task, seed, agent user and token, start and grading dates, turns
  handbook/       the policy manual copied into the agent's workspace
  truth.json      planted situation and the values the reference must contain
  reference/      the oracle's projections, written by the runner
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ERP_DIR = os.path.join(ROOT, 'erp')


# ------------------------------------------------------------------------------------------- scenario files

def write_scenario(out: str, erp, world: dict, meta: dict, handbook: dict[str, str], truth: dict) -> None:
    """Write everything except the reference. `erp` is closed and its file copied."""
    os.makedirs(out, exist_ok=True)
    for sub in ('handbook', 'reference'):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    erp.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    erp.db.execute('VACUUM')
    erp.close()
    if os.path.abspath(erp.path) != os.path.abspath(os.path.join(out, 'scenario.db')):
        shutil.copyfile(erp.path, os.path.join(out, 'scenario.db'))
    json.dump(world, open(os.path.join(out, 'world.json'), 'w'), indent=1, sort_keys=True)
    json.dump(meta, open(os.path.join(out, 'meta.json'), 'w'), indent=1, sort_keys=True)
    json.dump(truth, open(os.path.join(out, 'truth.json'), 'w'), indent=1, sort_keys=True)
    os.makedirs(os.path.join(out, 'handbook'))
    for name, text in sorted(handbook.items()):
        with open(os.path.join(out, 'handbook', name), 'w', encoding='utf-8') as f:
            f.write(text.strip() + '\n')


def load_meta(scenario: str) -> dict:
    return json.load(open(os.path.join(scenario, 'meta.json'), encoding='utf-8'))


def preamble(meta: dict, turn: dict) -> str:
    d = date.fromisoformat(turn['date'])
    return (f'You are signed in to the ERP of {meta["company"]} as {meta["agent_name"]}, {meta["agent_title"]}. '
            f'The business date is {d.strftime("%A")} {d.day} {d.strftime("%B %Y")}.\n'
            'The `erp` command on your PATH talks to the ERP: `erp docs` lists what it can do and `erp whoami` shows '
            'your access. The company handbook is in ./handbook. Do the work in the ERP; put any notes you are asked '
            'for in this folder.\n\n'
            f'Message from {turn["from_name"]} ({turn["from_title"]}):\n{turn["request"].strip()}\n')


# ------------------------------------------------------------------------------------------- the server

def free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Server:
    """A local bb-erp process on its own ports. Not an isolation boundary; official runs use containers."""

    def __init__(self, db: str, world: str, control_token: str, log: str):
        self.port, self.cport, self.token = free_port(), free_port(), control_token
        env = dict(os.environ, PYTHONPATH=ERP_DIR)
        self.proc = subprocess.Popen(
            [sys.executable, '-m', 'bberp.server', '--db', db, '--world', world, '--port', str(self.port),
             '--control-port', str(self.cport), '--control-token', control_token],
            stdout=open(log, 'ab'), stderr=subprocess.STDOUT, env=env, cwd=ERP_DIR, start_new_session=True)
        for _ in range(200):
            try:
                self.control('GET', '/control/health')
                return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError('bb-erp did not start; see ' + log)

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.port}'

    def control(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(f'http://127.0.0.1:{self.cport}{path}', method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header('Authorization', f'Bearer {self.token}')
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())

    def advance(self, to: str) -> dict:
        return self.control('POST', '/control/advance', {'to': to})

    def stop(self) -> None:
        try:
            self.control('POST', '/control/flush', {})
            self.control('POST', '/control/shutdown', {})
        except OSError:
            pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


# ------------------------------------------------------------------------------------------- oracle client

class ApiError(Exception):
    def __init__(self, status: int, problem: dict):
        super().__init__(f'{status} {problem.get("title")}: {problem.get("detail")}')
        self.status, self.problem = status, problem
        self.code = problem.get('title')


class Api:
    """What an oracle policy sees: the agent's API with the agent's token, nothing else."""

    def __init__(self, url: str, token: str):
        self.url, self.token = url.rstrip('/'), token
        self.calls = 0

    def request(self, method: str, path: str, body: dict | None = None, query: dict | None = None, raw: bool = False):
        import urllib.parse
        target = self.url + path + ('?' + urllib.parse.urlencode(query) if query else '')
        req = urllib.request.Request(target, method=method, data=json.dumps(body).encode() if body is not None else None)
        req.add_header('Authorization', f'Bearer {self.token}')
        if body is not None:
            req.add_header('Content-Type', 'application/json')
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
                return data if raw else json.loads(data)['data']
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, json.loads(e.read() or b'{}'))

    def get(self, path: str, **query):
        return self.request('GET', path, query=query or None)

    def post(self, path: str, body: dict | None = None):
        return self.request('POST', path, body or {})

    def patch(self, path: str, body: dict):
        return self.request('PATCH', path, body)

    def items(self, path: str, **query) -> list[dict]:
        return self.get(path, limit=1000, **query)['items']


# ------------------------------------------------------------------------------------------- vendor documents

def pdf_text(data: bytes) -> str:
    """Text of a PDF, laid out in columns (pdftotext -layout when present, else pdfplumber)."""
    exe = shutil.which('pdftotext')
    if exe:
        p = subprocess.run([exe, '-layout', '-', '-'], input=data, capture_output=True, check=True)
        return p.stdout.decode('utf-8', 'replace')
    import io
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return '\n'.join(page.extract_text(layout=True) or '' for page in pdf.pages)


def _num(s: str) -> float:
    return float(s.replace(',', '').replace('$', ''))


def parse_invoice(text: str) -> dict:
    """Invoice number, date, PO, item lines, freight and total from a bb-erp vendor invoice."""
    out = {'number': re.search(r'Invoice no\.:\s*(\S+)', text).group(1),
           'date': re.search(r'Invoice date:\s*(\S+)', text).group(1),
           'po': re.search(r'Your PO:\s*(\S+)', text).group(1), 'lines': [], 'freight': 0.0}
    for m in re.finditer(r'^\s*(\d+)\s+(\S+)\s+(.+?)\s{2,}([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)\s*$', text, re.M):
        out['lines'].append({'po_line': int(m.group(1)), 'sku': m.group(2), 'description': m.group(3).strip(),
                             'qty': _num(m.group(4)), 'unit_price': _num(m.group(5)), 'amount': _num(m.group(6))})
    f = re.search(r'Freight\s+([\d,.]+)', text)
    if f:
        out['freight'] = _num(f.group(1))
    out['total'] = _num(re.search(r'TOTAL DUE\s+([\d,.]+)', text).group(1))
    return out


def parse_packing_slip(text: str) -> dict:
    """Slip number, PO and shipped lines (item, qty, lot, expiry, substitute-for) from a bb-erp packing slip."""
    out = {'slip': re.search(r'Slip no\.:\s*(\S+)', text).group(1),
           'po': re.search(r'Your PO:\s*(\S+)', text).group(1), 'lines': []}
    for line in text.splitlines():
        m = re.match(r'^\s*(\d+)\s+([A-Z][A-Z0-9-]+)\s{2,}(.+?)\s{2,}([\d,.]+)(?:\s{2,}(\S+))?'
                     r'(?:\s{2,}(\d{4}-\d{2}-\d{2}))?(?:\s{2,}(.*))?$', line)
        if not m:
            continue
        desc = m.group(3).strip()
        note = (m.group(7) or '').strip()
        if desc == 'BACKORDERED':
            out['lines'].append({'po_line': int(m.group(1)), 'sku': m.group(2), 'backordered': _num(m.group(4)),
                                 'note': note})
            continue
        sub = re.search(r'substitute for (\S+)', note)
        out['lines'].append({'po_line': int(m.group(1)), 'sku': m.group(2), 'description': desc,
                             'qty': _num(m.group(4)), 'lot': m.group(5), 'expiry': m.group(6),
                             'substitute_for': sub.group(1) if sub else None})
    return out
