#!/usr/bin/env python3
"""Drive one process-track episode by hand: for human baselines and for smoke-testing an agent turn by turn.

  process_episode.py start --task procure-to-pay-week --dir /path/to/episode [--seed 0]
      starts bb-erp for the scenario, creates the workspace, prints the environment and the turn-1 prompt
  process_episode.py next --dir /path/to/episode
      advances the clock to the next turn and prints its prompt (or says every turn is done)
  process_episode.py finish --dir /path/to/episode
      advances to the grading date, stops bb-erp, grades, and prints the verdicts

The workspace is DIR/ws; the person or agent works there with ERP_URL, ERP_TOKEN and PATH as printed. State lives
in DIR/episode.json. Not an isolation boundary.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import process_run as pr  # noqa: E402
from process_grade import grade_process  # noqa: E402
from procgen.episode import Server, load_meta, preamble  # noqa: E402


def _state(d: str) -> dict:
    return json.load(open(os.path.join(d, 'episode.json'), encoding='utf-8'))


def _save(d: str, st: dict) -> None:
    json.dump(st, open(os.path.join(d, 'episode.json'), 'w'), indent=1)


def _control(st: dict, method: str, path: str, body=None) -> dict:
    s = Server.__new__(Server)
    s.cport, s.token = st['control_port'], st['control_token']
    return s.control(method, path, body)


def _env(st: dict, meta: dict) -> str:
    return (f'export ERP_URL={st["url"]}\nexport ERP_TOKEN={meta["token"]}\n'
            f'export PATH={st["bin"]}:$PATH\ncd {st["ws"]}')


def start(a) -> None:
    d = os.path.abspath(a.dir)
    if os.path.exists(os.path.join(d, 'episode.json')):
        sys.exit(f'{d} already holds an episode')
    scenario = pr.ensure_scenario(a.task, a.seed)
    meta = load_meta(scenario)
    ws, erp_dir = os.path.join(d, 'ws'), os.path.join(d, 'erp')
    os.makedirs(erp_dir)
    shutil.copytree(os.path.join(scenario, 'handbook'), os.path.join(ws, 'handbook'))
    shutil.copyfile(os.path.join(scenario, 'scenario.db'), os.path.join(erp_dir, 'company.db'))
    shutil.copyfile(os.path.join(scenario, 'world.json'), os.path.join(erp_dir, 'world.json'))
    token = os.urandom(16).hex()
    server = Server(os.path.join(erp_dir, 'company.db'), os.path.join(erp_dir, 'world.json'), token,
                    os.path.join(d, 'erp.log'))
    st = {'task': a.task, 'seed': a.seed, 'scenario': scenario, 'ws': ws, 'erp_dir': erp_dir,
          'bin': pr._erp_bin(os.path.join(erp_dir, 'bin')), 'url': server.url, 'control_port': server.cport,
          'control_token': token, 'pid': server.proc.pid, 'turn': 0}
    _save(d, st)
    print(_env(st, meta) + '\n')
    _next(d)


def _next(d: str) -> None:
    st = _state(d)
    meta = load_meta(st['scenario'])
    if st['turn'] >= len(meta['turns']):
        print('every turn is done; run finish')
        return
    turn = meta['turns'][st['turn']]
    _control(st, 'POST', '/control/advance', {'to': turn['date']})
    st['turn'] += 1
    _save(d, st)
    prompt = preamble(meta, turn)
    open(os.path.join(d, f'prompt-{turn["n"]}.txt'), 'w', encoding='utf-8').write(prompt)
    print(f'--- turn {turn["n"]} of {len(meta["turns"])} ---\n{prompt}')


def finish(a) -> None:
    d = os.path.abspath(a.dir)
    st = _state(d)
    meta = load_meta(st['scenario'])
    _control(st, 'POST', '/control/advance', {'to': meta['grading_date']})
    _control(st, 'POST', '/control/flush', {})
    _control(st, 'POST', '/control/shutdown', {})
    import time
    time.sleep(1.0)
    final = os.path.join(d, 'final.db')
    shutil.copyfile(os.path.join(st['erp_dir'], 'company.db'), final)
    res = grade_process(pr.task_dir(st['task']), final, os.path.join(st['scenario'], 'scenario.db'), st['ws'],
                        os.path.join(st['scenario'], 'reference'), d,
                        {'start': meta['start'], 'agent': meta['agent_user'], 'token_id': meta['token_id']})
    json.dump(res, open(os.path.join(d, 'result.json'), 'w'), indent=2)
    print(('PASS' if res['passed'] else 'BREACH' if res['breach'] else 'FAIL') + f'  {st["task"]}')
    for c in res['checks']:
        print(f'  [{"ok" if c["passed"] else "FAIL"}] {c["name"]}: {c["detail"][:160]}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('start')
    s.add_argument('--task', required=True)
    s.add_argument('--dir', required=True)
    s.add_argument('--seed', type=int, default=0)
    n = sub.add_parser('next')
    n.add_argument('--dir', required=True)
    f = sub.add_parser('finish')
    f.add_argument('--dir', required=True)
    a = ap.parse_args()
    if a.cmd == 'start':
        start(a)
    elif a.cmd == 'next':
        _next(os.path.abspath(a.dir))
    else:
        finish(a)


if __name__ == '__main__':
    main()
