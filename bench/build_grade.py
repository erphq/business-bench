#!/usr/bin/env python3
"""Build track grading: the automatable items, then a checklist sheet for a tester.

  build_grade.py results/<label>/<task>__<harness>__t<N>            # grade one turn
  build_grade.py results/<label>/<task>__<harness>__t<N> --serve    # bring the app back up first (start_command from RESULT.json)
  build_grade.py --score <sheet.md>                                 # total a filled-in sheet

Automated: RESULT.json present with every contract field; the URL answers HTTP; the login page
is HTML with a form or a JS app shell; the URL is not localhost/private when the task demands it;
the main list's count (read from the task's own export and scope items) when the app exposes JSON (best effort).
Everything else is a human item; the sheet lists the checklist with the run's URL and logins
filled in and a [ ] per item. --score reads [x]/[ ] and reports total, core, and per tag.
"""
from __future__ import annotations
import argparse, json, os, re, socket, subprocess, sys, time, urllib.request
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load(run_dir: str):
    res = json.load(open(os.path.join(run_dir, 'result.json')))
    task_dir = os.path.join(ROOT, 'tasks', 'build', res['task'])
    task = yaml.safe_load(open(os.path.join(task_dir, 'task.yaml')))
    return res, task_dir, task

def http(url: str, timeout: float = 8.0):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'business-bench-grader'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(200_000).decode('utf-8', errors='replace')
            return r.status, dict(r.headers), body
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(50_000).decode('utf-8', errors='replace')
    except Exception as e:
        return None, {}, str(e)

def is_private(host: str) -> bool:
    return host in ('localhost', '127.0.0.1', '0.0.0.0', '::1') or host.startswith(('10.', '192.168.', '172.16.', '172.17.', '172.18.', '172.19.', '172.2', '172.30.', '172.31.'))

def serve(run_dir: str, res: dict, docker: str | None) -> subprocess.Popen | None:
    rj = res.get('result_json') or {}
    cmd = rj.get('start_command')
    if not cmd: print('no start_command in RESULT.json; cannot restart the app'); return None
    ws = os.path.abspath(os.path.join(run_dir, 'ws'))  # docker needs an absolute host path
    if docker:
        full = ['docker', 'run', '--rm', '--name', f"bench-serve-{res['run_id']}".replace('_', '-')[:100], '--network', 'host',
                '--user', f'{os.getuid()}:{os.getgid()}', '-v', f'{ws}:/run/ws', '-e', 'HOME=/tmp', '-w', '/run/ws', docker, 'bash', '-lc', cmd]
    else:
        full = ['bash', '-lc', cmd]
    p = subprocess.Popen(full, cwd=ws, stdout=open(os.path.join(run_dir, 'serve.log'), 'ab'), stderr=subprocess.STDOUT, start_new_session=True)
    port = rj.get('port') or res.get('port')
    for _ in range(60):
        time.sleep(1)
        try:
            with socket.create_connection(('127.0.0.1', int(port)), timeout=1): return p
        except Exception: continue
    print(f'app did not open port {port} within 60s; see serve.log'); return p


def probe_spec(task_dir: str, task: dict) -> dict:
    """What the automated probes count, read from the task's own checklist so every app is graded on its
    own numbers: the baseline export item gives the admin's main-list total, the row-level scope item gives
    the restricted login's count (one number, or several when the restricted login may be any of a few
    named people), and the API item's number receives the unauthenticated-endpoint finding. task.yaml may
    add `probe_paths` (candidate list URLs) and `probe_extra` (more lists: item, name, paths, expected)."""
    checklist = open(os.path.join(task_dir, task['checklist'])).read()
    spec = {'main': None, 'scope': None, 'api_item': None, 'extra': list(task.get('probe_extra') or [])}
    m = re.search(r'^(\d+)\. (?:\(CORE\) )?\[Exact\] Export of the main list to CSV produces exactly \**([\d,]+)\** data rows', checklist, re.M)
    if m: spec['main'] = {'item': int(m.group(1)), 'expected': int(m.group(2).replace(',', ''))}
    m = re.search(r'^(\d+)\. (?:\(CORE\) )?\[Permission\] Row-level scope: the restricted login sees only .+?, exactly (.+?), and cannot open', checklist, re.M)
    if m:
        part = m.group(2).replace('*', '')
        counts = [int(x.replace(',', '')) for x in re.findall(r'\b\d[\d,]*\b', part)]
        plural = re.sub(r'^.*\d[\d,]*\)?\s*(?:\([^)]*\)\s*)?', '', part).strip()
        spec['scope'] = {'item': int(m.group(1)), 'expected_any': counts, 'plural': plural}
    m = re.search(r'^(\d+)\. (?:\(CORE\) )?\[API\] ', checklist, re.M)
    if m: spec['api_item'] = int(m.group(1))
    plural = (spec['scope'] or {}).get('plural') or ''
    words = re.findall(r'[a-z]+', plural.lower())
    slugs = []
    if words:
        slugs = ['-'.join(words), '_'.join(words), ''.join(words), words[-1], words[0]]
    paths = list(task.get('probe_paths') or []) + [f'/{x}' for x in slugs]
    spec['paths'] = list(dict.fromkeys(paths))
    spec['words'] = list(dict.fromkeys(words + [plural.lower()])) if plural else []
    return spec

def automated(res: dict, task: dict, local_base: str | None = None) -> list[dict]:
    out = []
    rj = res.get('result_json')
    fields = ['url', 'admin.user', 'admin.password', 'restricted.user', 'restricted.password', 'notes']
    def get(d, path):
        for k in path.split('.'):
            if not isinstance(d, dict) or k not in d: return None
            d = d[k]
        return d
    missing = [f for f in fields if not get(rj or {}, f)]
    out.append({'item': 1, 'name': 'RESULT.json carries the contract fields', 'passed': rj is not None and not missing, 'detail': 'missing ' + ', '.join(missing) if missing else 'all present', 'automated': 'partial (logins are checked by the tester)'})
    url = get(rj or {}, 'url')
    if url:
        host = re.sub(r'^https?://', '', url).split('/')[0].split(':')[0]
        status, headers, body = http(url)
        html = (headers.get('Content-Type', '') or '').startswith('text/html') or '<html' in body.lower()
        form = bool(re.search(r'<form|type=["\']password|<input', body, re.I)) or bool(re.search(r'<div id=["\'](root|app)', body, re.I))
        recorded_ok = status is not None and status < 400 and html and form
        if local_base and not recorded_ok:
            # The recorded URL is gone (a tunnel that died with the turn's container); the grader has the
            # app back up locally from start_command, so the login-page item is judged there and the
            # recorded URL's state is kept in the detail.
            s2, h2, b2 = http(local_base + '/login')
            html2 = (h2.get('Content-Type', '') or '').startswith('text/html') or '<html' in b2.lower()
            form2 = bool(re.search(r'<form|type=["\']password|<input', b2, re.I)) or bool(re.search(r'<div id=["\'](root|app)', b2, re.I))
            out.append({'item': 1, 'name': 'URL answers with a login page', 'passed': s2 is not None and s2 < 400 and html2 and form2, 'detail': f'recorded URL: {("HTTP " + str(status)) if status else "no response"}; restarted app at {local_base}: HTTP {s2}; html={html2}; form-or-app-shell={form2}', 'automated': 'yes (judged on the restarted app; the recorded URL did not answer)'})
        else:
            out.append({'item': 1, 'name': 'URL answers with a login page', 'passed': recorded_ok, 'detail': f'HTTP {status}; html={html}; form-or-app-shell={form}' if status else f'no response: {body[:120]}', 'automated': 'yes'})
        # A public hostname that no longer answers is not a URL a tester can open: the item fails
        # even when the app itself came back up locally for the other checks.
        out.append({'item': 2, 'name': 'URL is not localhost or a private address, and answers', 'passed': (not is_private(host)) and recorded_ok, 'detail': host + ('' if recorded_ok else ' (public address, but it no longer answers: a tunnel that died with the build turn; the tester needs a URL that outlives it)' if not is_private(host) else ''), 'automated': 'yes (reachability from another network is the tester\'s)'})
        # best-effort unauthenticated JSON probes for the main list: a count that answers without a login is
        # itself a finding for the API item
        spec = task.get('_probe_spec') or {}
        base = url.split('/login')[0].rstrip('/')
        lists = []
        if spec.get('main'): lists.append((spec['main']['item'], spec.get('paths') or [], [spec['main']['expected']], 'main list'))
        for x in spec.get('extra') or []: lists.append((x['item'], x.get('paths') or [], [x['expected']], x.get('name', 'list')))
        for item, paths, want, what in lists:
            for path in [('/api' + p) for p in paths] + list(paths):
                s2, h2, b2 = http(base + path)
                if not (s2 and s2 < 400 and b2.strip().startswith(('[', '{'))): continue
                try:
                    data = json.loads(b2)
                    if isinstance(data, list): n = len(data)
                    else: n = len(next((v for v in data.values() if isinstance(v, list)), []))
                except Exception: continue
                out.append({'item': item, 'name': f'{what} count via {path} with no login', 'passed': n in want,
                            'detail': f'{n} rows (want {" or ".join(map(str, want))}); a data endpoint that answers without a login is a finding for item {spec.get("api_item")}', 'automated': 'best effort'})
                break
    return out

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Replace the default redirect handler so a 3xx surfaces as HTTPError: a login that redirects is a
    success, a list page that redirects is a bounce to the login page."""
    def redirect_request(self, *a, **k): return None


def _cookie_session():
    import http.cookiejar
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NoRedirect()), jar


def _login(opener, base: str, user: str, password: str) -> bool:
    """Log in through the app's own form: find the login form's field names, post the credentials,
    and treat a redirect or a page without a password field as success. Works for the HTML apps the
    harnesses build; a JS-only login (platform apps) returns False and leaves those items to the tester."""
    import urllib.parse
    try:
        with opener.open(base + '/login', timeout=10) as r: page = r.read(200_000).decode('utf-8', errors='replace')
    except Exception: return False
    names = re.findall(r"<input[^>]*name=[\"']?([A-Za-z_\[\]0-9-]+)[\"']?[^>]*>", page, re.I)
    if not names: return False
    user_field = next((n for n in names if re.search(r'user|email|login', n, re.I)), None)
    pass_field = next((n for n in names if re.search(r'pass', n, re.I)), None)
    if not user_field or not pass_field: return False
    fields = {user_field: user, pass_field: password}
    for m in re.finditer(r"<input[^>]*type=[\"']hidden[\"'][^>]*>", page, re.I):
        n = re.search(r"name=[\"']?([^\"'\s>]+)", m.group(0)); v = re.search(r"value=[\"']([^\"']*)", m.group(0))
        if n and n.group(1) not in fields: fields[n.group(1)] = v.group(1) if v else ''
    data = urllib.parse.urlencode(fields).encode()
    try:
        opener.open(urllib.request.Request(base + '/login', data=data, headers={'User-Agent': 'business-bench-grader'}), timeout=10)
        return False  # 200 back on the login page: rejected
    except urllib.error.HTTPError as e:
        return 300 <= e.code < 400
    except Exception:
        return False


def _rows(opener, url: str, words: list[str] | None = None) -> int | None:
    try:
        with opener.open(url, timeout=10) as r: page = r.read(2_000_000).decode('utf-8', errors='replace')
    except Exception: return None  # a redirect here is a bounce to the login page
    if 'type="password"' in page or "type='password'" in page: return None  # bounced to login
    caption = '|'.join(re.escape(w) for w in (words or []) + ['records', 'rows', 'results', 'items', 'entries'])
    m = re.search(r'\b(\d{1,4})\s+(' + caption + r')\b', page, re.I)
    if m: return int(m.group(1))
    tr = len(re.findall(r'<tr\b', page, re.I))
    return max(0, tr - 1) if tr else None


def probe(res: dict, task: dict, local_base: str | None = None) -> list[dict]:
    """Best-effort checklist items against the live HTML app: log in as admin and as the restricted
    user through the app's own form, then count the main list as each. Items the probe cannot
    reach stay with the tester."""
    out = []
    rj = res.get('result_json') or {}
    url = rj.get('url')
    if not url: return out
    base = url.split('/login')[0].rstrip('/')
    if local_base:
        s0, _, _ = http(base + '/login')
        if s0 is None or s0 >= 500: base = local_base  # recorded URL gone; use the restarted app
    admin, restricted = rj.get('admin') or {}, rj.get('restricted') or {}
    opener, _ = _cookie_session()
    ok = _login(opener, base, admin.get('user', ''), admin.get('password', ''))
    out.append({'item': 1, 'name': 'admin login accepted by the app form', 'passed': ok, 'detail': 'redirected after posting the form' if ok else 'no HTML login form found, or the credentials were rejected', 'automated': 'best effort'})
    spec = task.get('_probe_spec') or {}
    words = spec.get('words') or []
    def first_count(op, paths):
        for path in paths:
            n = _rows(op, base + path, words)
            if n is not None: return n, path
        return None, None
    if ok:
        if spec.get('main'):
            n, path = first_count(opener, spec.get('paths') or [])
            if n is not None: out.append({'item': spec['main']['item'], 'name': f"main list shows {spec['main']['expected']} rows as admin", 'passed': n == spec['main']['expected'], 'detail': f'{n} rows at {path}', 'automated': 'best effort (row count or an "N <entities>" caption)'})
        for x in spec.get('extra') or []:
            n, path = first_count(opener, x.get('paths') or [])
            if n is not None: out.append({'item': x['item'], 'name': f"{x.get('name', 'list')} shows {x['expected']} rows as admin", 'passed': n == x['expected'], 'detail': f'{n} rows at {path}', 'automated': 'best effort'})
    opener2, _ = _cookie_session()
    ok2 = _login(opener2, base, restricted.get('user', ''), restricted.get('password', ''))
    out.append({'item': 1, 'name': 'restricted login accepted by the app form', 'passed': ok2, 'detail': 'redirected after posting the form' if ok2 else 'no HTML login form found, or the credentials were rejected', 'automated': 'best effort'})
    if ok2 and spec.get('scope'):
        n, path = first_count(opener2, spec.get('paths') or [])
        want = spec['scope']['expected_any']
        for scope_item in [spec['scope']['item']] + list(task.get('probe_scope_also') or []):
            if n is not None: out.append({'item': scope_item, 'name': f"restricted login sees its scope ({' or '.join(map(str, want))} {spec['scope']['plural']})", 'passed': n in want, 'detail': f'{n} rows at {path}', 'automated': 'best effort (the tester confirms the scope field on the records)'})
    return out


def sheet(run_dir: str, res: dict, task_dir: str, task: dict, auto: list[dict]) -> str:
    rj = res.get('result_json') or {}
    checklist = open(os.path.join(task_dir, task['checklist'])).read()
    lines = [f"# Tester sheet: {task['id']} / {res['harness']} / turn {res['turn']}", '',
             f"URL: {rj.get('url', '(missing)')}", f"Admin: {(rj.get('admin') or {}).get('user', '(missing)')} / {(rj.get('admin') or {}).get('password', '(missing)')}",
             f"Restricted: {(rj.get('restricted') or {}).get('user', '(missing)')} / {(rj.get('restricted') or {}).get('password', '(missing)')}",
             f"Notes: {rj.get('notes', '')}", f"Restart: {rj.get('start_command', '(none given)')}", '',
             '## Automated results', ''] + [f"- [{'x' if a['passed'] else ' '}] item {a['item']}: {a['name']} — {a['detail']} ({a['automated']})" for a in auto] + ['', '## Checklist (tick [x] when the item passes; leave [ ] otherwise)', '']
    for m in re.finditer(r'^(\d+)\. (\(CORE\) )?\[(\w+)\] (.+?)\n((?:\s{2,}.+\n?)*)', checklist, re.M):
        n, core, tag, text, how = m.groups()
        lines.append(f"- [ ] {n}. {'(CORE) ' if core else ''}[{tag}] {text.strip()}")
        for hl in (how or '').strip().splitlines(): lines.append(f"      {hl.strip()}")
    if res['turn'] >= 1:
        change = open(os.path.join(task_dir, task['changes'][res['turn'] - 1])).read()
        extra = change.split('\n---\n')[1] if '\n---\n' in change else ''
        lines += ['', f"## Change request {res['turn']} items", '']
        for m in re.finditer(r'^(\d+)\. \[(\w+)\] (.+?)\n((?:\s{2,}.+\n?)*)', extra, re.M):
            n, tag, text, how = m.groups()
            lines.append(f"- [ ] {n}. [{tag}] {text.strip()}")
            for hl in (how or '').strip().splitlines(): lines.append(f"      {hl.strip()}")
    p = os.path.join(run_dir, 'tester-sheet.md')
    if os.path.exists(p) and re.search(r'^- \[[xX]\] \d+\.', open(p).read(), re.M):
        # a tester has already ticked checklist items here; never overwrite their work
        p = os.path.join(run_dir, f"tester-sheet.regraded-{time.strftime('%Y%m%d-%H%M%S')}.md")
        print(f'existing tester sheet has hand-ticked items; writing the fresh sheet to {os.path.basename(p)}')
    open(p, 'w').write('\n'.join(lines) + '\n')
    return p

def score(sheet_path: str) -> dict:
    text = open(sheet_path).read()
    items = re.findall(r'^- \[( |x|X)\] (\d+)\. (\(CORE\) )?\[(\w+)\]', text, re.M)
    total = len(items); passed = sum(1 for m in items if m[0].lower() == 'x')
    core = [m for m in items if m[2]]; core_passed = sum(1 for m in core if m[0].lower() == 'x')
    by_tag = {}
    for m in items: t = by_tag.setdefault(m[3], [0, 0]); t[1] += 1; t[0] += m[0].lower() == 'x'
    return {'items': total, 'passed': passed, 'core': f'{core_passed} of {len(core)}', 'first_usable': core_passed == len(core) and len(core) > 0, 'by_tag': {k: f'{v[0]} of {v[1]}' for k, v in by_tag.items()}}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_dir', nargs='?')
    ap.add_argument('--serve', action='store_true')
    ap.add_argument('--docker', default=None)
    ap.add_argument('--score', default=None)
    ap.add_argument('--spec', default=None, help='print the probe spec read from a task id and exit')
    ap.add_argument('--probe', action='store_true', help='also log in through the app form and count the main list as admin and as the restricted login')
    a = ap.parse_args()
    if a.spec:
        td = os.path.join(ROOT, 'tasks', 'build', a.spec); t = yaml.safe_load(open(os.path.join(td, 'task.yaml')))
        print(json.dumps(probe_spec(td, t), indent=1)); return
    if a.score:
        print(json.dumps(score(a.score), indent=2)); return
    if not a.run_dir: ap.error('run_dir or --score required')
    res, task_dir, task = load(a.run_dir)
    task['_probe_spec'] = probe_spec(task_dir, task)
    proc = serve(a.run_dir, res, a.docker) if a.serve else None
    port = (res.get('result_json') or {}).get('port') or res.get('port')
    local_base = f'http://127.0.0.1:{port}' if proc and port else None
    auto = automated(res, task, local_base)
    if a.probe: auto += probe(res, task, local_base)
    for x in auto: print(f"[{'PASS' if x['passed'] else 'FAIL'}] item {x['item']}: {x['name']} — {x['detail']}")
    p = sheet(a.run_dir, res, task_dir, task, auto)
    gp = os.path.join(a.run_dir, 'grade.json')
    if os.path.exists(gp):
        os.makedirs(os.path.join(a.run_dir, 'grade-history'), exist_ok=True)
        os.replace(gp, os.path.join(a.run_dir, 'grade-history', f"grade-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    json.dump({'run_id': res['run_id'], 'automated': auto}, open(gp, 'w'), indent=2)
    print(f'tester sheet: {os.path.relpath(p, ROOT)}' + ('  (app left running for the tester)' if proc else ''))

if __name__ == '__main__':
    main()
