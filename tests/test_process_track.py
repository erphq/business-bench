"""Process track: every task validates (oracle passes, runs are deterministic, the null agent and each negative
control fail what they should), and vendor documents parse back into the data they were printed from."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

import export_process_campaign  # noqa: E402
import process_run  # noqa: E402
import validate_process  # noqa: E402
from bberp import sim  # noqa: E402
from bberp.pdf import business_document  # noqa: E402
from procgen.episode import load_meta, parse_invoice, parse_packing_slip, pdf_text  # noqa: E402

TASKS = sorted(d for d in os.listdir(os.path.join(ROOT, 'tasks', 'process'))
               if os.path.isfile(os.path.join(ROOT, 'tasks', 'process', d, 'task.yaml')))


class Tasks(unittest.TestCase):
    def test_every_task_validates(self):
        for task in TASKS:
            with self.subTest(task=task):
                self.assertEqual(validate_process.validate(task, 0, strict=True), [])


class ShellHarness(unittest.TestCase):
    """The path real agents take: the runner calls harnesses/<name>.sh once per turn with ERP_URL, ERP_TOKEN and the
    `erp` command on PATH, keeps the folder between turns, and grades the final state."""
    ADAPTER = """#!/usr/bin/env bash
set -eu
WS=$1; PROMPT_FILE=$2; OUT=$3
erp whoami > "$OUT/whoami.json"
cp "$PROMPT_FILE" "$OUT/prompt-seen.txt"
echo "turn $BENCH_TURN" >> "$WS/notes.md"
"""

    def test_adapter_reaches_the_erp_every_turn(self):
        task = 'month-end-close'
        meta = load_meta(process_run.ensure_scenario(task, 0))
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as results:
            os.makedirs(os.path.join(root, 'harnesses'))
            os.symlink(os.path.join(ROOT, 'erp'), os.path.join(root, 'erp'))
            adapter = os.path.join(root, 'harnesses', 'selftest.sh')
            open(adapter, 'w').write(self.ADAPTER)
            os.chmod(adapter, 0o755)
            with mock.patch.object(process_run, 'ROOT', root):
                res = process_run.run_attempt(task, 'selftest', 0, 1, results)
            self.assertEqual([(t['n'], t['exit_code'], t['timed_out']) for t in res['turns']],
                             [(t['n'], 0, False) for t in meta['turns']])
            for t in meta['turns']:
                turn_dir = os.path.join(res['work_dir'], 'turns', str(t['n']))
                who = json.load(open(os.path.join(turn_dir, 'out', 'whoami.json')))
                self.assertEqual((who['data']['id'], who['business_date']), (meta['agent_user'], t['date']))
                self.assertEqual(open(os.path.join(turn_dir, 'out', 'prompt-seen.txt')).read(),
                                 open(os.path.join(turn_dir, 'prompt.txt')).read())
            self.assertEqual(open(os.path.join(res['work_dir'], 'ws', 'notes.md')).read(),
                             ''.join(f'turn {t["n"]}\n' for t in meta['turns']))
            db = sqlite3.connect(os.path.join(res['work_dir'], 'final.db'))
            reads = db.execute("SELECT business_date FROM audit_events WHERE channel = 'api' AND actor = ? AND "
                               "token_id = ? AND path = '/whoami' ORDER BY id",
                               (meta['agent_user'], meta['token_id'])).fetchall()
            db.close()
            self.assertEqual([r[0] for r in reads], [t['date'] for t in meta['turns']])
            self.assertEqual(res['grader_errors'], [])
            self.assertFalse(res['passed'])

    def test_harness_home_is_fresh_each_turn_and_keeps_no_login(self):
        task = 'month-end-close'
        meta = load_meta(process_run.ensure_scenario(task, 0))
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as results:
            os.makedirs(os.path.join(root, 'harnesses'))
            os.symlink(os.path.join(ROOT, 'erp'), os.path.join(root, 'erp'))
            login = os.path.join(root, 'operator-auth.json')
            open(login, 'w').write('{"tokens": "operator"}')
            os.makedirs(os.path.join(root, 'homes', 'codex-selftest'))
            os.symlink(login, os.path.join(root, 'homes', 'codex-selftest', 'auth.json'))
            adapter = os.path.join(root, 'harnesses', 'codex-selftest.sh')
            open(adapter, 'w').write('#!/usr/bin/env bash\nset -eu\ntest -L "$CODEX_BENCH_HOME/auth.json"\n'
                                     'ls "$CODEX_BENCH_HOME" > "$3/home-at-start.txt"\n'
                                     'echo "turn $BENCH_TURN" > "$CODEX_BENCH_HOME/session.txt"\n')
            os.chmod(adapter, 0o755)
            with mock.patch.object(process_run, 'ROOT', root):
                res = process_run.run_attempt(task, 'codex-selftest', 0, 1, results)
            self.assertEqual([t['exit_code'] for t in res['turns']], [0] * len(meta['turns']))
            for t in meta['turns']:
                turn_dir = os.path.join(res['work_dir'], 'turns', str(t['n']))
                self.assertEqual(open(os.path.join(turn_dir, 'out', 'home-at-start.txt')).read(), 'auth.json\n')
                self.assertEqual(os.listdir(os.path.join(turn_dir, 'home')), ['session.txt'])
            self.assertEqual(open(login).read(), '{"tokens": "operator"}')

    def test_provider_keys_are_redacted_from_kept_homes(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as results:
            os.makedirs(os.path.join(root, 'harnesses'))
            os.symlink(os.path.join(ROOT, 'erp'), os.path.join(root, 'erp'))
            cfg_dir = os.path.join(root, 'homes', 'proto-selftest', '.proto')
            os.makedirs(cfg_dir)
            cfg = {'llmProviders': {'custom': {'enabled': True, 'apiKey': 'sk-or-test-secret',
                                               'baseUrl': 'https://openrouter.ai/api/v1'}},
                   'selectedModel': 'custom::deepseek/deepseek-v4.1-flash', 'llm': {'maxTokens': 65536}}
            json.dump(cfg, open(os.path.join(cfg_dir, 'config.json'), 'w'))
            adapter = os.path.join(root, 'harnesses', 'proto-selftest.sh')
            open(adapter, 'w').write('#!/usr/bin/env bash\nset -eu\n'
                                     'grep -q sk-or-test-secret "$PROTO_BENCH_HOME/.proto/config.json"\n')
            os.chmod(adapter, 0o755)
            with mock.patch.object(process_run, 'ROOT', root):
                res = process_run.run_attempt('margin-bridge', 'proto-selftest', 0, 1, results)
            self.assertEqual([t['exit_code'] for t in res['turns']], [0])        # the harness saw the key
            kept = json.load(open(os.path.join(res['work_dir'], 'turns', '1', 'home', '.proto', 'config.json')))
            self.assertEqual(kept['llmProviders']['custom']['apiKey'], '[redacted]')
            self.assertEqual(kept['llm']['maxTokens'], 65536)
            self.assertEqual(json.load(open(os.path.join(cfg_dir, 'config.json'))), cfg)
            found = subprocess.run(['grep', '-r', 'sk-or-test-secret', res['work_dir']], capture_output=True)
            self.assertEqual(found.returncode, 1)                                 # nowhere in the kept attempt

    def test_a_harness_that_does_not_start_is_an_error_not_a_failure(self):
        task = 'month-end-close'
        process_run.ensure_scenario(task, 0)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as results:
            os.makedirs(os.path.join(root, 'harnesses'))
            os.symlink(os.path.join(ROOT, 'erp'), os.path.join(root, 'erp'))
            adapter = os.path.join(root, 'harnesses', 'selftest.sh')
            open(adapter, 'w').write('#!/usr/bin/env bash\nexec /nonexistent/agent "$@"\n')
            os.chmod(adapter, 0o755)
            with mock.patch.object(process_run, 'ROOT', root):
                res = process_run.run_attempt(task, 'selftest', 0, 1, results)
            self.assertEqual([t['n'] for t in res['turns']], [1])            # the episode stops at the first turn
            self.assertIn(res['turns'][0]['exit_code'], (126, 127))
            self.assertIn('did not start', res['error'])


class CampaignExport(unittest.TestCase):
    """A campaign exports to a ledger without local paths, and --verify catches a summary that no longer matches."""

    def test_export_and_verify(self):
        with tempfile.TemporaryDirectory() as root:
            raw = os.path.join(root, 'results', 'demo')
            os.makedirs(raw)
            json.dump({'campaign': 'demo', 'track': 'process', 'seed': 0, 'repetitions': 2,
                       'cells': {'cell-a': {}, 'cell-b': {}}, 'conditions': []}, open(os.path.join(raw, 'campaign.json'), 'w'))
            for cell in ('cell-a', 'cell-b'):
                for run in (1, 2):
                    d = os.path.join(raw, f'task-x__{cell}__s0__r{run}')
                    os.makedirs(os.path.join(d, 'ws', '.proto'))
                    open(os.path.join(d, 'final.db'), 'wb').write(b'db')
                    open(os.path.join(d, 'ws', 'note.md'), 'w').write('note')
                    open(os.path.join(d, 'ws', '.proto', 'session.json'), 'w').write('{}')
                    passed = cell == 'cell-a' or run == 1
                    json.dump({'run_id': os.path.basename(d), 'task': 'task-x', 'harness': cell, 'seed': 0, 'run': run,
                               'passed': passed, 'breach': False, 'error': None, 'work_dir': d,
                               'checks': [{'name': 'c', 'type': 'state_set', 'passed': passed, 'detail': 'x'}],
                               'turns': [{'n': 1, 'date': '2026-10-05', 'exit_code': 0, 'timed_out': False, 'wall_s': 5.0}],
                               'wall_s': 6.0, 'usage': {'input': 10, 'cached_input': 5, 'output': 2}, 'cost_usd': None},
                              open(os.path.join(d, 'result.json'), 'w'))
            with mock.patch.object(export_process_campaign, 'ROOT', root), \
                    mock.patch.object(export_process_campaign, 'PUBLISHED', os.path.join(root, 'results', 'process')):
                export_process_campaign.export('demo')
                out = os.path.join(root, 'results', 'process', 'demo')
                ledger = open(os.path.join(out, 'attempts.jsonl')).read()
                self.assertNotIn(root, ledger)                      # no local paths
                self.assertNotIn('.proto', ledger)                  # harness session files are not the agent's work
                summary = json.load(open(os.path.join(out, 'summary.json')))
                self.assertEqual((summary['cell-a']['passed'], summary['cell-b']['passed']), (2, 1))
                self.assertEqual((summary['cell-a']['tasks_passed_every_time'], summary['cell-b']['tasks_passed_every_time']), (1, 0))
                summary['cell-b']['passed'] = 2
                json.dump(summary, open(os.path.join(out, 'summary.json'), 'w'))
                with self.assertRaises(SystemExit):
                    export_process_campaign.verify_one(out)


class Documents(unittest.TestCase):
    VENDOR = {'id': 'V-1', 'name': 'Keystone Fasteners', 'address': '300 Commerce Drive\nYork, PA 17402',
              'phone': '(717) 555-0123', 'email': 'invoices@keystone.example'}

    def test_invoice_round_trip(self):
        lines = [{'po_line': 1, 'sku': 'HEX-NUT-10', 'description': 'Hex nut M10 brass', 'qty': 500, 'unit_price': 0.09},
                 {'po_line': 3, 'sku': None, 'description': 'Safety glasses', 'qty': 1, 'unit_price': 236.4}]
        doc = parse_invoice(pdf_text(sim._invoice_pdf(self.VENDOR, 'KF-20323', '2026-10-08', 'PO-10178', lines, 64.0,
                                                      'NET30')))
        self.assertEqual((doc['number'], doc['date'], doc['po'], doc['freight'], doc['total']),
                         ('KF-20323', '2026-10-08', 'PO-10178', 64.0, 345.4))
        self.assertEqual([(l['po_line'], l['sku'], l['qty'], l['unit_price']) for l in doc['lines']],
                         [(1, 'HEX-NUT-10', 500, 0.09), (3, 'MISC', 1, 236.4)])

    def test_packing_slip_round_trip(self):
        rows = [['1', 'SEAL-212', 'O-ring 212 Viton', '180', 'C-8812', '2028-04-30', ''],
                ['1', 'SEAL-212', 'O-ring 212 Viton', '20', 'C-8790', '2027-02-26', ''],
                ['2', 'HEX-NUT-10Z', 'Hex nut M10 zinc-plated', '500', '', '', 'substitute for HEX-NUT-10']]
        pdf = business_document('PACKING SLIP', ['York, PA'], [('Slip no.', 'PS-10176-1'), ('Your PO', 'PO-10176')],
                                [('PO line', 54), ('Item', 92), ('Description', 170), ('Qty', 300), ('Lot', 340),
                                 ('Expiry', 395), ('Note', 455)], rows, heading='Coastline Seals')
        slip = parse_packing_slip(pdf_text(pdf))
        self.assertEqual(slip['po'], 'PO-10176')
        self.assertEqual([(l['po_line'], l['sku'], l['qty'], l['lot'], l['expiry'], l['substitute_for'])
                          for l in slip['lines']],
                         [(1, 'SEAL-212', 180, 'C-8812', '2028-04-30', None), (1, 'SEAL-212', 20, 'C-8790', '2027-02-26', None),
                          (2, 'HEX-NUT-10Z', 500, None, None, 'HEX-NUT-10')])


if __name__ == '__main__':
    unittest.main()
