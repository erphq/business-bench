"""Northgate Valve Co.: the company every pilot process task runs in.

A small manufacturer and distributor of brass valves with one plant (Dayton) and a distribution warehouse (Reno).
`build()` creates the master data and then twelve months of ordinary, clean business through bb-erp's own service
functions, so every document, balance and subledger is consistent before a task plants anything. Tasks then add
their situation on top (see episode.py).

Standard costs of finished goods are material only (the rolled-up BOM), so work orders close without variance;
labour and overhead are expensed through payroll and overhead entries.
"""
from __future__ import annotations

import hashlib
import os
import random
import sys
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, 'erp'))

from bberp import ledger, setup  # noqa: E402
from bberp.core import Erp, ext_cents  # noqa: E402

COMPANY = 'Northgate Valve Co.'
DOMAIN = 'northgatevalve.com'

DEPARTMENTS = [('ADMIN', 'Administration', 'erin.walsh'), ('FIN', 'Finance', 'priya.raman'),
               ('PUR', 'Purchasing', 'maya.chen'), ('WH', 'Warehouse', 'luis.ortega'),
               ('PROD', 'Production', 'dana.whitfield'), ('MAINT', 'Maintenance', 'kofi.mensah'),
               ('QA', 'Quality', 'alex.ng'), ('SALES', 'Sales', 'grace.kim')]

# id, name, title, department, roles, limits in dollars, manager, extension
USERS = [
    ('erin.walsh', 'Erin Walsh', 'President', 'ADMIN', ['staff', 'dept_head'],
     {'requisition': 250000, 'payment_run': 2000000, 'journal_entry': 2000000}, None, '101'),
    ('priya.raman', 'Priya Raman', 'Controller', 'FIN', ['staff', 'controller', 'dept_head'],
     {'requisition': 50000, 'payment_run': 500000, 'journal_entry': 250000}, 'erin.walsh', '120'),
    ('omar.haddad', 'Omar Haddad', 'Staff accountant', 'FIN', ['staff', 'staff_accountant'], {}, 'priya.raman', '121'),
    ('hannah.brooks', 'Hannah Brooks', 'AP supervisor', 'FIN', ['staff', 'ap_supervisor'], {}, 'priya.raman', '122'),
    ('nina.patel', 'Nina Patel', 'Credit and receivables', 'FIN', ['staff', 'credit_manager', 'ar_clerk'], {},
     'priya.raman', '123'),
    ('maya.chen', 'Maya Chen', 'Operations manager', 'PUR', ['staff', 'purchasing_manager', 'dept_head'],
     {'requisition': 10000}, 'erin.walsh', '140'),
    ('riley.park', 'Riley Park', 'Buyer and AP clerk', 'PUR', ['staff', 'buyer', 'receiver', 'ap_clerk'], {},
     'maya.chen', '141'),
    ('luis.ortega', 'Luis Ortega', 'Warehouse lead', 'WH',
     ['staff', 'receiver', 'shipping', 'inventory_controller', 'dept_head'], {'requisition': 1000}, 'maya.chen', '150'),
    ('ben.carter', 'Ben Carter', 'Shipping clerk', 'WH', ['staff', 'shipping'], {}, 'luis.ortega', '151'),
    ('dana.whitfield', 'Dana Whitfield', 'Production manager', 'PROD', ['staff', 'dept_head', 'production_supervisor'],
     {'requisition': 2500}, 'erin.walsh', '160'),
    ('sam.whitaker', 'Sam Whitaker', 'Production supervisor', 'PROD', ['staff', 'production_supervisor'], {},
     'dana.whitfield', '161'),
    ('jordan.lee', 'Jordan Lee', 'Production planner', 'PROD', ['staff', 'planner'], {'purchase_order': 25000},
     'dana.whitfield', '162'),
    ('mateo.garcia', 'Mateo Garcia', 'Machinist', 'PROD', ['staff'], {}, 'sam.whitaker', '163'),
    ('kofi.mensah', 'Kofi Mensah', 'Maintenance lead', 'MAINT', ['staff', 'dept_head'], {'requisition': 2500},
     'dana.whitfield', '170'),
    ('aisha.okafor', 'Aisha Okafor', 'Maintenance technician', 'MAINT', ['staff'], {}, 'kofi.mensah', '171'),
    ('alex.ng', 'Alex Ng', 'Quality lead', 'QA', ['staff', 'dept_head'], {'requisition': 2500}, 'dana.whitfield', '180'),
    ('grace.kim', 'Grace Kim', 'Sales manager', 'SALES', ['staff', 'dept_head', 'order_entry'], {'requisition': 2500},
     'erin.walsh', '190'),
    ('tom.reyes', 'Tom Reyes', 'Customer service', 'SALES', ['staff', 'order_entry'], {}, 'grace.kim', '191'),
]

WAREHOUSES = [('DAY', 'Dayton plant', 'east', [('DAY-STK', 'Dayton stock', 'stock'), ('DAY-RCV', 'Dayton dock', 'receiving'),
                                               ('DAY-QA', 'Dayton quarantine', 'quarantine'),
                                               ('DAY-PRD', 'Dayton production floor', 'production')]),
              ('RNO', 'Reno distribution', 'west', [('RNO-STK', 'Reno stock', 'stock')])]

# vendor key -> (id, name, terms, phone, email, address, bank)
VENDORS = {
    'midstate': ('V-10001', 'Mid-State Metals', '2/10N30', '(937) 555-0142', 'ar@midstatemetals.com',
                 '2200 Mill Road\nDayton, OH 45404', ('First Ohio Bank', '042000314', '5512047718')),
    'coastline': ('V-10002', 'Coastline Seals', 'NET30', '(207) 555-0199', 'billing@coastlineseals.com',
                  '14 Wharf Street\nPortland, ME 04101', ('Casco Bay Bank', '011200365', '7730021944')),
    'pacific': ('V-10003', 'Pacific Seal', 'NET30', '(503) 555-0107', 'orders@pacificseal.com',
                '880 Industrial Way\nSalem, OR 97301', ('Willamette Savings', '123206707', '3380166201')),
    'dayton': ('V-10004', 'Dayton Castings', 'NET45', '(937) 555-0170', 'sales@daytoncastings.com',
               '47 Foundry Lane\nDayton, OH 45402', ('Miami Valley Bank', '042101190', '9021556038')),
    'keystone': ('V-10005', 'Keystone Fasteners', 'NET30', '(717) 555-0123', 'invoices@keystonefasteners.com',
                 '300 Commerce Drive\nYork, PA 17402', ('Susquehanna Trust', '031301422', '6604418825')),
    'ohiopack': ('V-10006', 'Ohio Packaging', 'NET30', '(614) 555-0188', 'ar@ohiopackaging.com',
                 '91 Carton Court\nColumbus, OH 43215', ('Scioto National', '044000037', '1188320547')),
    'tricounty': ('V-10007', 'Tri-County Plastics', 'NET30', '(513) 555-0136', 'billing@tricountyplastics.com',
                  '12 Resin Road\nHamilton, OH 45011', ('Great Miami Bank', '042202196', '4471900312')),
    'greatlakes': ('V-10008', 'Great Lakes Industrial Supply', 'NET30', '(419) 555-0165', 'ar@glisupply.com',
                   '5 Harbor View\nToledo, OH 43604', ('Maumee Bank', '041215032', '2290375516')),
    'buckeye': ('V-10009', 'Buckeye Power & Light', 'DUE', '(800) 555-0110', 'billing@buckeyepower.com',
                'PO Box 1100\nColumbus, OH 43216', ('Central Ohio Bank', '044115443', '8800012277')),
    'riverside': ('V-10010', 'Riverside Properties', 'DUE', '(937) 555-0155', 'leasing@riversideprops.com',
                  '1 Riverside Plaza\nDayton, OH 45402', ('Miami Valley Bank', '042101190', '9077430216')),
}

# sku: (name, type, uom, std cost, lead workdays, safety stock, moq, lot-controlled, shelf days, preferred vendor key)
ITEMS = {
    'BR-0500': ('Brass bar 1/2in C360', 'purchased', 'ft', 2.95, 2, 400, 0, 0, None, 'midstate'),
    'BR-0750': ('Brass bar 3/4in C360', 'purchased', 'ft', 3.90, 2, 400, 0, 0, None, 'midstate'),
    'BR-1000': ('Brass bar 1in C360', 'purchased', 'ft', 5.60, 2, 300, 0, 0, None, 'midstate'),
    'CAST-1-BODY': ('Valve body casting 1in', 'purchased', 'ea', 18.40, 15, 60, 0, 0, None, 'dayton'),
    'CAST-2-BODY': ('Valve body casting 2in', 'purchased', 'ea', 31.00, 15, 30, 0, 0, None, 'dayton'),
    'SEAL-212': ('O-ring 212 Viton', 'purchased', 'ea', 1.40, 2, 300, 0, 1, 1095, 'coastline'),
    'SEAL-214': ('O-ring 214 Viton', 'purchased', 'ea', 1.55, 2, 150, 0, 1, 1095, 'coastline'),
    'GASKET-7': ('Gasket 7 PTFE', 'purchased', 'ea', 0.22, 3, 800, 0, 0, None, 'keystone'),
    'GASKET-9': ('Gasket 9 PTFE', 'purchased', 'ea', 0.30, 3, 150, 1000, 0, None, 'keystone'),
    'GASKET-9B': ('Gasket 9 PTFE, alternate cut', 'purchased', 'ea', 0.30, 3, 0, 1000, 0, None, 'keystone'),
    'HEX-NUT-10': ('Hex nut M10 brass', 'purchased', 'ea', 0.09, 3, 800, 0, 0, None, 'keystone'),
    'HEX-NUT-10Z': ('Hex nut M10 zinc-plated steel', 'purchased', 'ea', 0.06, 3, 0, 0, 0, None, 'keystone'),
    'HANDLE-L': ('Lever handle, vinyl grip', 'purchased', 'ea', 2.20, 5, 100, 0, 0, None, 'tricounty'),
    'BOX-S': ('Carton, small', 'purchased', 'ea', 0.45, 5, 200, 0, 0, None, 'ohiopack'),
    'BOX-M': ('Carton, medium', 'purchased', 'ea', 0.70, 5, 100, 0, 0, None, 'ohiopack'),
}

# vendor key, sku, [(min qty, unit price)]
AGREEMENTS = [
    ('midstate', 'BR-0500', [(0, 3.05), (500, 2.88)]), ('midstate', 'BR-0750', [(0, 4.12), (500, 3.87)]),
    ('midstate', 'BR-1000', [(0, 5.85), (500, 5.52)]),
    ('dayton', 'CAST-1-BODY', [(0, 18.40)]), ('dayton', 'CAST-2-BODY', [(0, 31.00)]),
    ('coastline', 'SEAL-212', [(0, 1.46)]), ('coastline', 'SEAL-214', [(0, 1.62)]),
    ('pacific', 'SEAL-212', [(0, 1.35)]),
    ('keystone', 'GASKET-7', [(0, 0.23)]), ('keystone', 'GASKET-9', [(0, 0.31)]), ('keystone', 'GASKET-9B', [(0, 0.31)]),
    ('keystone', 'HEX-NUT-10', [(0, 0.09)]),
    ('tricounty', 'HANDLE-L', [(0, 2.20)]),
    ('ohiopack', 'BOX-S', [(0, 0.45)]), ('ohiopack', 'BOX-M', [(0, 0.70)]),
]

# finished good: (name, list price, monthly base volume, BOM [(component, qty per)])
FINISHED = {
    'BV-100': ('Ball valve 1in, full port', 74.00, 1300, [('CAST-1-BODY', 1), ('BR-0750', 0.5), ('SEAL-212', 2),
                                                        ('GASKET-7', 2), ('HEX-NUT-10', 1), ('HANDLE-L', 1),
                                                        ('BOX-S', 1)]),
    'BV-200': ('Ball valve 2in, full port', 121.00, 620, [('CAST-2-BODY', 1), ('BR-1000', 0.75), ('SEAL-214', 2),
                                                         ('GASKET-7', 2), ('HEX-NUT-10', 2), ('HANDLE-L', 1),
                                                         ('BOX-M', 1)]),
    'GV-100': ('Gate valve 1in', 81.00, 430, [('CAST-1-BODY', 1), ('BR-0750', 1.0), ('BR-0500', 0.5), ('SEAL-212', 1),
                                             ('GASKET-9', 1), ('HEX-NUT-10', 4), ('BOX-S', 1)]),
}

# Invoice numbering per vendor: prefix and the first number history uses.
INVOICE_SERIES = {'midstate': ('MS-', 87960), 'coastline': ('41-', 7650), 'pacific': ('PS', 55012),
                  'dayton': ('DC-', 31120), 'keystone': ('KF-', 20290), 'ohiopack': ('OP', 9410),
                  'tricounty': ('TCP-', 6120), 'greatlakes': ('GL', 118800), 'buckeye': ('BPL-', 7702100),
                  'riverside': ('RP-', 2410)}

CUSTOMERS = [
    ('C-20001', 'Harbor Supply Co.', 'east', 'DIST', 60000, '1/10N30', 'prompt'),
    ('C-20002', 'Midwest Plumbing Distributors', 'east', 'DIST', 80000, 'NET30', 'on_time'),
    ('C-20003', 'Lakeshore Mechanical', 'east', 'CONT', 25000, 'NET30', 'late'),
    ('C-20004', 'Allegheny Pipe & Valve', 'east', 'DIST', 70000, 'NET45', 'on_time'),
    ('C-20005', 'Tri-State Industrial', 'east', 'CONT', 30000, 'NET30', 'on_time'),
    ('C-20006', 'Great Plains Irrigation', 'west', 'DIST', 50000, 'NET30', 'late'),
    ('C-20007', 'Pioneer Contractors', 'west', 'CONT', 20000, 'NET30', 'on_time'),
    ('C-20008', 'Summit HVAC Supply', 'west', 'DIST', 45000, '1/10N30', 'prompt'),
    ('C-20009', 'Riverbend Utilities', 'east', 'CONT', 35000, 'NET45', 'on_time'),
    ('C-20010', 'Cascade Water Works', 'west', 'CONT', 30000, 'NET30', 'on_time'),
    ('C-20011', 'Frontier Supply', 'west', 'DIST', 40000, 'NET30', 'late'),
    ('C-20012', 'Metro Facilities Group', 'east', 'CONT', 25000, 'NET30', 'on_time'),
]


@dataclass
class Company:
    erp: Erp
    seed: int
    start: str
    tokens: dict = field(default_factory=dict)
    vendors: dict = field(default_factory=lambda: {k: v[0] for k, v in VENDORS.items()})

    def token(self, user: str) -> str:
        return self.tokens[user]


def secret(seed: int, user: str) -> str:
    return 'bb_' + hashlib.sha256(f'northgate:{seed}:{user}'.encode()).hexdigest()[:32]


def fg_std(sku: str) -> float:
    return round(sum(ITEMS[c][3] * q for c, q in FINISHED[sku][3]), 4)


def master_data(erp: Erp, seed: int, since: str) -> dict:
    """Everything that is not a transaction. Returns user id -> API token secret."""
    tokens = {}
    for code, name, _head in DEPARTMENTS:
        setup.add_department(erp, code, name, None)
    for uid, name, title, dept, roles, limits, manager, ext in USERS:
        setup.add_user(erp, uid, name, roles, dept, {k: v * 100 for k, v in limits.items()},
                       email=f'{uid}@{DOMAIN}', title=title, manager=manager, phone=f'(937) 555-0{ext}')
        tokens[uid] = secret(seed, uid)
        setup.add_token(erp, f'tok-{uid}', uid, tokens[uid], f'{name} API token')
    for code, _name, head in DEPARTMENTS:
        erp.update('departments', {'code': code}, {'head': head})
    for code, name, region, locs in WAREHOUSES:
        setup.add_warehouse(erp, code, name, region, locs)
    for k, v in {'default_warehouse': 'DAY', 'default_bank': 'OPER', 'default_production_location': 'DAY-PRD',
                 'company_domain': DOMAIN}.items():
        erp.set_meta(k, v)
    setup.add_bank_account(erp, 'OPER', 'Operating account, First Ohio Bank', '1000', min_balance_cents=5000000)
    setup.add_bank_account(erp, 'PAYR', 'Payroll account, First Ohio Bank', '1010')
    for key, (vid, name, terms, phone, email, address, bank) in VENDORS.items():
        h = int(hashlib.sha256(name.encode()).hexdigest(), 16)
        setup.add_vendor(erp, vid, name, terms, bank, phone=phone, email=email, address=address, since=since,
                         tin=f'{10 + h % 89:02d}-{h // 97 % 10_000_000:07d}')
    for sku, (name, typ, uom, cost, lead, safety, moq, lot, shelf, vkey) in ITEMS.items():
        setup.add_item(erp, sku=sku, name=name, type=typ, uom=uom, std_cost=cost, lead_time_days=lead,
                       safety_stock=safety, moq=moq, lot_controlled=lot, shelf_life_days=shelf,
                       preferred_vendor=VENDORS[vkey][0], default_location='DAY-STK', category='component',
                       planner='jordan.lee')
    for sku, (name, price, base, bom) in FINISHED.items():
        setup.add_item(erp, sku=sku, name=name, type='manufactured', uom='ea', std_cost=fg_std(sku), list_price=price,
                       lead_time_days=3, safety_stock=round(base * 0.4), default_location='DAY-STK',
                       category='finished', planner='jordan.lee')
        for comp, q in bom:
            erp.insert('boms', {'parent': sku, 'component': comp, 'qty_per': q, 'scrap_pct': 0})
    for i, (vkey, sku, breaks) in enumerate(AGREEMENTS, 1):
        for mn, price in breaks:
            erp.insert('price_agreements', {'id': f'PA-{3000 + i}', 'vendor': VENDORS[vkey][0], 'sku': sku,
                                            'valid_from': since, 'valid_to': '2027-12-31', 'min_qty': mn,
                                            'unit_price': price})
    erp.insert('approved_substitutes', {'sku': 'GASKET-9', 'substitute': 'GASKET-9B'})
    for cid, name, region, pl, limit, terms, _behaviour in CUSTOMERS:
        setup.add_customer(erp, cid, name, limit * 100, terms, region=region, price_list=pl,
                           email=f'ap@{name.lower().split()[0].strip(".,&")}.example', phone='(555) 555-0100')
    for sku, (name, price, base, bom) in FINISHED.items():
        erp.insert('price_lists', {'code': 'DIST', 'sku': sku, 'unit_price': round(price * 0.8, 2)})
        erp.insert('price_lists', {'code': 'CONT', 'sku': sku, 'unit_price': price})
    return tokens


def rng(seed: int, *salt) -> random.Random:
    return random.Random(hashlib.sha256(f'{seed}:{":".join(map(str, salt))}'.encode()).digest())


def opening_balances(erp: Erp, day: str, need: dict[str, float]) -> None:
    """Opening stock (a month of component usage, most of a month of finished goods) and balances."""
    ctx = setup.as_user(erp, 'priya.raman')
    value = 0
    stock = {sku: q * 1.2 for sku, q in need.items()}
    stock.update({sku: v[2] * 0.8 for sku, v in FINISHED.items()})
    for sku in sorted(stock):
        qty = round(stock[sku])
        lot = expiry = None
        if sku in ITEMS and ITEMS[sku][7]:
            lot, expiry = f'OB-{sku[-3:]}', '2027-03-31'
            erp.insert('lots', {'sku': sku, 'lot': lot, 'expiry': expiry})
        std = ITEMS[sku][3] if sku in ITEMS else fg_std(sku)
        v = ext_cents(qty, std)
        erp.insert('inventory_txns', {'txn_date': day, 'sku': sku, 'location': 'DAY-STK', 'lot': lot, 'qty': qty,
                                      'unit_cost': std, 'value_cents': v, 'kind': 'opening', 'ref_type': 'opening',
                                      'ref_id': 'OPENING', 'user_id': 'priya.raman'})
        value += v
    ledger.post(erp, ctx, day, 'opening', 'OPENING', [
        ('1000', 45_000_000, 0), ('1010', 3_000_000, 0), ('1300', value, 0), ('1400', 1_650_000, 0),
        ('1500', 36_600_000, 0), ('1550', 0, 12_000_000), ('3000', 0, 20_000_000),
        ('3100', 0, 45_000_000 + 3_000_000 + value + 1_650_000 + 36_600_000 - 12_000_000 - 20_000_000)],
        memo='Opening balances')
