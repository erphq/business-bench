"""The standard role catalogue every scenario installs. A user holds one or more roles; a role is a set of actions.

Reading is open to every staff role except the audit log (auditor, admin) and boxes, which are per role.
Counterparty roles (vendor_bot, bank_bot, ...) belong to the simulator's system users.
"""
from __future__ import annotations

ROLES: dict[str, tuple[str, list[str]]] = {
    'staff': ('Any employee', ['req.create', 'msg.send', 'escalate', 'call', 'box.general']),
    'dept_head': ('Department head', ['req.approve', 'box.general']),
    'purchasing_manager': ('Purchasing manager', [
        'req.approve', 'req.cancel_any', 'po.create', 'po.send', 'vendor.request', 'vendor.update', 'box.purchasing',
        'msg.dispose']),
    'buyer': ('Buyer', ['po.create', 'po.send', 'vendor.request', 'box.purchasing', 'box.receiving', 'msg.dispose']),
    'receiver': ('Receiving', ['rcv.post', 'inv.transfer', 'box.receiving', 'msg.dispose']),
    'ap_clerk': ('Accounts payable clerk', [
        'ap.enter', 'ap.hold', 'ap.validate', 'vendor.bank.request', 'vendor.request', 'box.ap', 'msg.dispose']),
    'ap_supervisor': ('Accounts payable supervisor', [
        'ap.enter', 'ap.hold', 'ap.validate', 'ap.release_hold', 'ap.approve', 'ap.void', 'pay.prepare', 'vendor.create',
        'vendor.update', 'vendor.bank.request', 'vendor.bank.verify', 'vendor.request', 'box.ap', 'msg.dispose']),
    'controller': ('Controller', [
        'je.create', 'je.approve', 'je.post', 'period.close', 'period.reopen', 'pay.approve', 'pay.release',
        'ap.approve', 'ap.release_hold', 'ap.void', 'req.approve', 'so.release_hold', 'inv.adjust', 'box.accounting',
        'msg.dispose']),
    'staff_accountant': ('Staff accountant', ['je.create', 'je.post', 'box.accounting', 'msg.dispose']),
    'planner': ('Production planner', [
        'wo.create', 'wo.release', 'po.create', 'po.send', 'vendor.request', 'item.plan', 'mrp.run', 'mrp.release',
        'so.promise', 'box.planning', 'box.purchasing', 'msg.dispose']),
    'production_supervisor': ('Production supervisor', [
        'wo.release', 'wo.issue', 'wo.complete', 'wo.close', 'inv.transfer', 'box.production', 'msg.dispose']),
    'inventory_controller': ('Inventory controller', ['inv.adjust', 'inv.transfer', 'box.warehouse', 'msg.dispose']),
    'order_entry': ('Order entry', ['so.create', 'box.sales', 'msg.dispose']),
    'shipping': ('Shipping and billing', ['so.ship', 'ar.invoice', 'box.shipping', 'msg.dispose']),
    'credit_manager': ('Credit manager', ['so.release_hold', 'so.create', 'box.credit', 'msg.dispose']),
    'ar_clerk': ('Accounts receivable clerk', ['ar.cash', 'box.ar', 'msg.dispose']),
    'auditor': ('Auditor (read-only)', ['audit.read', 'box.*']),
    'analyst': ('Financial analyst (read-only)', ['box.general']),
    'admin': ('Administrator', ['*']),
    # counterparties, used only by the simulator's system users
    'vendor_bot': ('Vendor counterparty', ['po.acknowledge']),
    'bank_bot': ('Bank', ['bank.post']),
    'mail_bot': ('Mail', []),
}

# Which boxes messages are delivered to by default, per topic.
BOXES = ('ap', 'receiving', 'purchasing', 'accounting', 'sales', 'credit', 'ar', 'planning', 'production',
         'warehouse', 'shipping', 'general')


def install(erp) -> None:
    for code, (name, actions) in ROLES.items():
        erp.insert('roles', {'code': code, 'name': name, 'description': ''})
        for a in sorted(set(actions)):
            erp.insert('role_permissions', {'role': code, 'action': a})
