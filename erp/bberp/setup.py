"""Building a company: the standard chart of accounts and posting rules, and helpers the scenario generators and
tests use to add users, tokens, periods, warehouses, items, vendors and customers. Nothing here is reachable from
the API; generators call it before an episode starts."""
from __future__ import annotations

from datetime import date

from . import roles
from .core import Ctx, Erp, add_days, load_ctx, parse_day, period_of

ACCOUNTS = [
    ('1000', 'Operating cash', 'asset', 'cash'), ('1010', 'Payroll cash', 'asset', 'cash'),
    ('1200', 'Accounts receivable', 'asset', 'ar'), ('1250', 'Allowance for doubtful accounts', 'asset', None),
    ('1300', 'Inventory', 'asset', 'inventory'), ('1350', 'Work in process', 'asset', 'wip'),
    ('1400', 'Prepaid expenses', 'asset', None), ('1500', 'Machinery and equipment', 'asset', None),
    ('1550', 'Accumulated depreciation', 'asset', None), ('1600', 'Vendor receivables', 'asset', None),
    ('2000', 'Accounts payable', 'liability', 'ap'), ('2050', 'Goods received not invoiced', 'liability', 'grni'),
    ('2100', 'Accrued liabilities', 'liability', None), ('2150', 'Accrued payroll', 'liability', None),
    ('2200', 'Sales tax payable', 'liability', None), ('2250', 'Unapplied customer cash', 'liability', 'unapplied_cash'),
    ('2300', 'Customer rebates payable', 'liability', None), ('2500', 'Line of credit', 'liability', None),
    ('3000', 'Owner equity', 'equity', None), ('3100', 'Retained earnings', 'equity', None),
    ('4000', 'Product sales', 'revenue', None), ('4100', 'Sales discounts', 'revenue', None),
    ('4200', 'Customer rebates', 'revenue', None), ('4900', 'Other income', 'revenue', None),
    ('5000', 'Cost of goods sold', 'expense', None), ('5050', 'Purchase price variance', 'expense', None),
    ('5060', 'Invoice price variance', 'expense', None), ('5070', 'Manufacturing variance', 'expense', None),
    ('5080', 'Inventory adjustments and write-offs', 'expense', None), ('5100', 'Freight in', 'expense', None),
    ('5150', 'Purchase discounts taken', 'expense', None),
    ('6000', 'Wages and salaries', 'expense', None), ('6050', 'Payroll taxes and benefits', 'expense', None),
    ('6100', 'Rent', 'expense', None), ('6150', 'Utilities', 'expense', None), ('6200', 'Maintenance and repairs', 'expense', None),
    ('6250', 'Shop supplies', 'expense', None), ('6300', 'Office supplies', 'expense', None),
    ('6350', 'Software and subscriptions', 'expense', None), ('6400', 'Travel', 'expense', None),
    ('6450', 'Insurance', 'expense', None), ('6500', 'Professional fees', 'expense', None),
    ('6550', 'Depreciation', 'expense', None), ('6600', 'Bank fees', 'expense', None),
    ('6700', 'Marketing', 'expense', None), ('6800', 'Purchase tax', 'expense', None), ('7000', 'Interest expense', 'expense', None),
]

POSTING_RULES = {
    'cash': '1000', 'ar': '1200', 'inventory': '1300', 'wip': '1350', 'ap': '2000', 'grni': '2050',
    'unapplied_cash': '2250', 'revenue': '4000', 'sales_discounts': '4100', 'cogs': '5000', 'ppv': '5050',
    'ipv': '5060', 'mfg_variance': '5070', 'inventory_adjustment': '5080', 'freight_in': '5100',
    'purchase_discounts': '5150', 'purchase_tax': '6800',
}

TERMS = [('NET30', 'Net 30', 30, 0, 0), ('NET45', 'Net 45', 45, 0, 0), ('NET60', 'Net 60', 60, 0, 0),
         ('2/10N30', '2% 10, net 30', 30, 2, 10), ('1/10N30', '1% 10, net 30', 30, 1, 10), ('DUE', 'Due on receipt', 0, 0, 0)]

DEFAULT_SETTINGS = {
    'over_receipt_ceiling_pct': 10,
    'je_approval_threshold_cents': 500000,
    'ap_self_approval_limit_cents': 0,
}


def new_company(path: str, name: str, business_date: str, first_period: str, last_period: str,
                settings: dict | None = None, holidays: dict | None = None) -> Erp:
    erp = Erp.create(path)
    with erp.tx():
        roles.install(erp)
        erp.set_meta('company_name', name)
        erp.set_today(business_date)
        for k, v in {**DEFAULT_SETTINGS, **(settings or {})}.items():
            erp.set_meta(k, v)
        for code, nm, typ, control in ACCOUNTS:
            erp.insert('accounts', {'code': code, 'name': nm, 'type': typ, 'control': control, 'active': 1})
        for key, acct in POSTING_RULES.items():
            erp.insert('posting_rules', {'key': key, 'account': acct})
        for code, desc, net, pct, days in TERMS:
            erp.insert('terms', {'code': code, 'description': desc, 'net_days': net, 'discount_pct': pct,
                                 'discount_days': days})
        add_periods(erp, first_period, last_period)
        for day, note in sorted((holidays or {}).items()):
            erp.insert('calendar', {'day': day, 'workday': 0, 'note': note})
        for uid, role in (('sys-vendor', 'vendor_bot'), ('sys-bank', 'bank_bot'), ('sys-mail', 'mail_bot')):
            add_user(erp, uid, uid.replace('sys-', '').title() + ' (system)', [role], kind='system')
    return erp


def add_periods(erp: Erp, first: str, last: str) -> None:
    y, m = int(first[:4]), int(first[5:7])
    while f'{y:04d}-{m:02d}' <= last:
        start = date(y, m, 1)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        erp.insert('periods', {'period': f'{y:04d}-{m:02d}', 'start_date': start.isoformat(),
                               'end_date': add_days(nxt.isoformat(), -1), 'status': 'open'})
        y, m = nxt.year, nxt.month


def close_periods_before(erp: Erp, period: str, by: str = 'setup') -> None:
    erp.run("UPDATE periods SET status = 'closed', closed_by = ?, closed_on = end_date WHERE period < ?", by, period)


def add_user(erp: Erp, uid: str, name: str, role_codes: list[str], department: str | None = None,
             limits: dict | None = None, email: str | None = None, title: str | None = None, manager: str | None = None,
             phone: str | None = None, kind: str = 'staff') -> None:
    erp.insert('users', {'id': uid, 'name': name, 'email': email, 'title': title, 'phone': phone,
                         'department': department, 'manager': manager, 'active': 1, 'kind': kind})
    for r in role_codes:
        erp.insert('user_roles', {'user_id': uid, 'role': r})
    for doc_type, cents in (limits or {}).items():
        erp.insert('approval_limits', {'user_id': uid, 'doc_type': doc_type, 'limit_cents': cents})


def add_token(erp: Erp, token_id: str, user: str, secret: str, label: str) -> None:
    erp.insert('tokens', {'id': token_id, 'secret': secret, 'user_id': user, 'label': label})


def add_department(erp: Erp, code: str, name: str, head: str | None = None) -> None:
    erp.insert('departments', {'code': code, 'name': name, 'head': head})


def add_warehouse(erp: Erp, code: str, name: str, region: str, locations: list[tuple[str, str, str]]) -> None:
    erp.insert('warehouses', {'code': code, 'name': name, 'region': region})
    for loc, nm, kind in locations:
        erp.insert('locations', {'code': loc, 'warehouse': code, 'name': nm, 'kind': kind})


def add_item(erp: Erp, **fields) -> None:
    row = {'type': 'purchased', 'uom': 'ea', 'active': 1, 'lot_controlled': 0, 'lead_time_days': 5,
           'safety_stock': 0, 'moq': 0, 'order_multiple': 0}
    row.update(fields)
    erp.insert('items', row)


def add_vendor(erp: Erp, vid: str, name: str, terms: str = 'NET30', bank: tuple | None = None, **fields) -> None:
    row = {'id': vid, 'name': name, 'status': 'active', 'quality_hold': 0, 'terms': terms}
    row.update(fields)
    erp.insert('vendors', row)
    if bank:
        bank_name, routing, account_no = bank
        aid = f'VBA-{vid}'
        erp.insert('vendor_bank_accounts', {'id': aid, 'vendor': vid, 'bank_name': bank_name, 'routing': routing,
                                            'account_no': account_no, 'status': 'verified', 'requested_by': 'setup',
                                            'requested_on': fields.get('since') or erp.today, 'verified_by': 'setup',
                                            'verified_on': fields.get('since') or erp.today})
        erp.update('vendors', {'id': vid}, {'remit_account': aid})


def add_customer(erp: Erp, cid: str, name: str, credit_limit_cents: int, terms: str = 'NET30', **fields) -> None:
    row = {'id': cid, 'name': name, 'status': 'active', 'terms': terms, 'credit_limit_cents': credit_limit_cents}
    row.update(fields)
    erp.insert('customers', row)


def add_bank_account(erp: Erp, code: str, name: str, gl_account: str, min_balance_cents: int = 0) -> None:
    erp.insert('bank_accounts', {'code': code, 'name': name, 'gl_account': gl_account,
                                 'min_balance_cents': min_balance_cents})


def as_user(erp: Erp, user: str) -> Ctx:
    """The acting context for history: the real user's permissions, on the setup channel (not audited)."""
    return load_ctx(erp, user, channel='setup')


def month_days(erp: Erp, period: str) -> list[str]:
    start = parse_day(period + '-01')
    out, d = [], start.isoformat()
    while period_of(d) == period:
        if erp.is_workday(d):
            out.append(d)
        d = add_days(d, 1)
    return out
