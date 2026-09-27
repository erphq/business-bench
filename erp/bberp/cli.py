#!/usr/bin/env python3
"""erp: command-line client for bb-erp. Standard library only; install by copying this file as `erp`.

Reads ERP_URL and ERP_TOKEN from the environment.

  erp whoami                                     who you are, your roles, limits, and the business date
  erp docs [word]                                endpoints (optionally only those mentioning a word)
  erp get /purchase-orders status=sent           GET with query parameters as key=value
  erp post /ap-invoices --data @inv.json         POST a JSON body from a file ...
  erp post /ap-invoices/APINV-10001/holds reason=price note="price above PO"   ... or as key=value fields
  erp patch PATH ... | erp put PATH ... | erp delete PATH
  erp inbox [--box ap] [--unread]                list messages in the boxes you can read
  erp read MSG-10001                             read a message; lists its attachments
  erp attachment MSG-10001 1 [-o file.pdf]       download an attachment (default: its own file name)
  erp report ap-aging [as_of=2026-10-09]         run a report (erp get /reports lists them)

Values in key=value are parsed as JSON when they can be (numbers, true, [..], {..}); otherwise they are strings.
--key KEY sends an Idempotency-Key so a retried write is not applied twice.
Output is JSON. A refused or failed request prints the problem and exits with status 1.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _value(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def _pairs(args):
    out = {}
    for a in args:
        if '=' not in a:
            raise SystemExit(f'expected key=value, got {a!r}')
        k, v = a.split('=', 1)
        out[k] = _value(v)
    return out


def _request(method, path, query=None, body=None, key=None, raw=False):
    base = os.environ.get('ERP_URL', '').rstrip('/')
    token = os.environ.get('ERP_TOKEN', '')
    if not base or not token:
        raise SystemExit('set ERP_URL and ERP_TOKEN')
    if not path.startswith('/'):
        path = '/' + path
    url = base + path
    if query:
        url += '?' + urllib.parse.urlencode({k: v if isinstance(v, str) else json.dumps(v) for k, v in query.items()})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', f'Bearer {token}')
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    if key:
        req.add_header('Idempotency-Key', key)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = r.read()
            ctype = r.headers.get('Content-Type', '')
            disp = r.headers.get('Content-Disposition', '')
            return r.status, ctype, disp, payload
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type', ''), '', e.read()
    except urllib.error.URLError as e:
        raise SystemExit(f'cannot reach {base}: {e.reason}')


def _print(status, ctype, payload):
    if 'json' in ctype:
        try:
            print(json.dumps(json.loads(payload), indent=2))
        except ValueError:
            sys.stdout.write(payload.decode('utf-8', 'replace'))
    else:
        sys.stdout.write(payload.decode('utf-8', 'replace'))
    if status >= 400:
        sys.exit(1)


def _body(args):
    body, key, rest = {}, None, []
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--data':
            src = args[i + 1]
            text = open(src[1:], encoding='utf-8').read() if src.startswith('@') else src
            body.update(json.loads(text))
            i += 2
        elif a == '--key':
            key = args[i + 1]
            i += 2
        else:
            rest.append(a)
            i += 1
    body.update(_pairs(rest))
    return body, key


def docs(word=None):
    status, ctype, _, payload = _request('GET', '/openapi.json')
    spec = json.loads(payload)
    for path, ops in spec['paths'].items():
        for method, op in ops.items():
            line = f'{method.upper():6} {path}  {op["summary"]}'
            fields = op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {}).get(
                'properties', {})
            params = [p['name'] for p in op.get('parameters', []) if p['in'] == 'query']
            text = line + ''.join(f'\n         body {k}: {v.get("description", "")}' for k, v in fields.items())
            if params:
                text += '\n         query ' + ', '.join(params)
            if not word or word.lower() in text.lower():
                print(text)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help', 'help'):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == 'whoami':
        return _print(*_pick(_request('GET', '/whoami')))
    if cmd == 'docs':
        return docs(args[0] if args else None)
    if cmd == 'get':
        return _print(*_pick(_request('GET', args[0], query=_pairs(args[1:]))))
    if cmd in ('post', 'patch', 'put', 'delete'):
        body, key = _body(args[1:])
        return _print(*_pick(_request(cmd.upper(), args[0], body=body if cmd != 'delete' or body else None, key=key)))
    if cmd == 'inbox':
        q = {}
        if '--box' in args:
            q['box'] = args[args.index('--box') + 1]
        if '--unread' in args:
            q['unread'] = 'true'
        return _print(*_pick(_request('GET', '/inbox', query=q)))
    if cmd == 'read':
        return _print(*_pick(_request('GET', f'/inbox/{args[0]}')))
    if cmd == 'attachment':
        status, ctype, disp, payload = _request('GET', f'/inbox/{args[0]}/attachments/{args[1]}')
        if status >= 400:
            return _print(status, ctype, payload)
        out = args[args.index('-o') + 1] if '-o' in args else (disp.split('filename=')[-1].strip('"') or 'attachment')
        with open(out, 'wb') as f:
            f.write(payload)
        print(json.dumps({'saved': out, 'bytes': len(payload), 'content_type': ctype}))
        return
    if cmd == 'report':
        return _print(*_pick(_request('GET', f'/reports/{args[0]}', query=_pairs(args[1:]))))
    raise SystemExit(f'unknown command {cmd!r}; run erp help')


def _pick(r):
    status, ctype, _, payload = r
    return status, ctype, payload


if __name__ == '__main__':
    main()
