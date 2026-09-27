"""Process track: every task validates (oracle passes, runs are deterministic, the null agent and each negative
control fail what they should), and vendor documents parse back into the data they were printed from."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))
sys.path.insert(0, os.path.join(ROOT, 'erp'))
sys.path.insert(0, os.path.join(ROOT, 'tasks', 'lib'))

import validate_process  # noqa: E402
from bberp import sim  # noqa: E402
from bberp.pdf import business_document  # noqa: E402
from procgen.episode import parse_invoice, parse_packing_slip, pdf_text  # noqa: E402

TASKS = sorted(d for d in os.listdir(os.path.join(ROOT, 'tasks', 'process'))
               if os.path.isfile(os.path.join(ROOT, 'tasks', 'process', d, 'task.yaml')))


class Tasks(unittest.TestCase):
    def test_every_task_validates(self):
        for task in TASKS:
            with self.subTest(task=task):
                self.assertEqual(validate_process.validate(task, 0, strict=True), [])


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
