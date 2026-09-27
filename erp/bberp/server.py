"""Run bb-erp: the agent API on one port and the runner's control API on another.

    python -m bberp.server --db company.db --world world.json --port 8080 --control-port 8081 --control-token T

The control API (reset is a fresh process on a copied database; this API only moves the clock and flushes):
    GET  /control/health
    POST /control/advance   {"to": "YYYY-MM-DD"}   run the counterparties day by day up to that date
    POST /control/flush                           checkpoint the database so the file can be copied
    POST /control/shutdown
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import api
from .core import Erp, ErpError


def _read_body(h: BaseHTTPRequestHandler) -> bytes:
    n = int(h.headers.get('Content-Length') or 0)
    return h.rfile.read(n) if n > 0 else b''


def _reply(h: BaseHTTPRequestHandler, status: int, headers: dict, body: bytes) -> None:
    h.send_response(status)
    for k, v in headers.items():
        h.send_header(k, v)
    h.send_header('Content-Length', str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def agent_handler(erp: Erp):
    class H(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'bb-erp/1'

        def log_message(self, *a):  # quiet: the audit log is the record
            pass

        def _do(self):
            status, headers, body = api.handle(erp, self.command, self.path, dict(self.headers.items()),
                                               _read_body(self))
            _reply(self, status, headers, body)

        do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _do
    return H


def control_handler(erp: Erp, token: str, stop):
    class C(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *a):
            pass

        def _auth(self) -> bool:
            got = (self.headers.get('Authorization') or '')[7:]
            return bool(token) and hmac.compare_digest(got.encode(), token.encode())

        def _json(self, status, payload):
            _reply(self, status, {'Content-Type': 'application/json'}, json.dumps(payload, default=str).encode())

        def do_GET(self):
            if self.path == '/control/health':
                return self._json(200, {'ok': True, 'business_date': erp.today})
            self._json(404, {'error': 'no such control endpoint'})

        def do_POST(self):
            if not self._auth():
                return self._json(401, {'error': 'control token required'})
            body = _read_body(self)
            try:
                b = json.loads(body) if body.strip() else {}
                if self.path == '/control/advance':
                    from . import sim
                    events = sim.advance(erp, b['to'])
                    return self._json(200, {'business_date': erp.today, 'events': events})
                if self.path == '/control/flush':
                    with erp.lock:
                        erp.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                    return self._json(200, {'ok': True})
                if self.path == '/control/shutdown':
                    self._json(200, {'ok': True})
                    threading.Thread(target=stop, daemon=True).start()
                    return
            except ErpError as e:
                return self._json(e.status, e.problem())
            except Exception as e:  # report, keep serving
                return self._json(500, {'error': f'{type(e).__name__}: {e}'})
            self._json(404, {'error': 'no such control endpoint'})
    return C


def serve(db: str, world_path: str | None, host: str, port: int, control_host: str, control_port: int,
          control_token: str) -> None:
    world = json.load(open(world_path, encoding='utf-8')) if world_path else {}
    erp = Erp(db, world=world)
    agent = ThreadingHTTPServer((host, port), agent_handler(erp))
    servers = [agent]

    def stop():
        for s in servers:
            s.shutdown()
    control = ThreadingHTTPServer((control_host, control_port), control_handler(erp, control_token, stop))
    servers.append(control)
    threading.Thread(target=control.serve_forever, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=stop, daemon=True).start())
    print(json.dumps({'agent': f'http://{host}:{agent.server_address[1]}',
                      'control': f'http://{control_host}:{control.server_address[1]}', 'pid': os.getpid()}),
          flush=True)
    try:
        agent.serve_forever()
    finally:
        with erp.lock:
            erp.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        erp.close()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True)
    ap.add_argument('--world')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--control-host', default='127.0.0.1')
    ap.add_argument('--control-port', type=int, default=8081)
    ap.add_argument('--control-token', default=os.environ.get('BBERP_CONTROL_TOKEN', ''))
    a = ap.parse_args(argv)
    if not a.control_token:
        sys.exit('set --control-token or BBERP_CONTROL_TOKEN')
    serve(a.db, a.world, a.host, a.port, a.control_host, a.control_port, a.control_token)


if __name__ == '__main__':
    main()
