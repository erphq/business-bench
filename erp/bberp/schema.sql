-- bb-erp schema. Money is integer cents; quantities and unit prices are REAL rounded to 4 places.
-- Dates are ISO strings (YYYY-MM-DD) on the business clock; nothing here reads the wall clock.
PRAGMA foreign_keys = ON;

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE seq (prefix TEXT PRIMARY KEY, next INTEGER NOT NULL);

-- Organisation ------------------------------------------------------------------------------------
CREATE TABLE departments (code TEXT PRIMARY KEY, name TEXT NOT NULL, head TEXT);
CREATE TABLE roles (code TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '');
CREATE TABLE role_permissions (
  role TEXT NOT NULL REFERENCES roles(code), action TEXT NOT NULL, PRIMARY KEY (role, action));
CREATE TABLE users (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, title TEXT, phone TEXT,
  department TEXT REFERENCES departments(code), manager TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  kind TEXT NOT NULL DEFAULT 'staff' CHECK (kind IN ('staff', 'external', 'system')));
CREATE TABLE user_roles (
  user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL REFERENCES roles(code),
  PRIMARY KEY (user_id, role));
CREATE TABLE approval_limits (
  user_id TEXT NOT NULL REFERENCES users(id), doc_type TEXT NOT NULL, limit_cents INTEGER NOT NULL,
  PRIMARY KEY (user_id, doc_type));
CREATE TABLE delegations (
  user_id TEXT NOT NULL REFERENCES users(id), delegate TEXT NOT NULL REFERENCES users(id),
  start_date TEXT NOT NULL, end_date TEXT NOT NULL);
CREATE TABLE leave (
  user_id TEXT NOT NULL REFERENCES users(id), start_date TEXT NOT NULL, end_date TEXT NOT NULL, kind TEXT);
CREATE TABLE calendar (day TEXT PRIMARY KEY, workday INTEGER NOT NULL, note TEXT);
CREATE TABLE tokens (
  id TEXT PRIMARY KEY, secret TEXT NOT NULL UNIQUE, user_id TEXT NOT NULL REFERENCES users(id),
  label TEXT NOT NULL);

-- Ledger ------------------------------------------------------------------------------------------
CREATE TABLE accounts (
  code TEXT PRIMARY KEY, name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('asset', 'liability', 'equity', 'revenue', 'expense')),
  control TEXT, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE posting_rules (key TEXT PRIMARY KEY, account TEXT NOT NULL REFERENCES accounts(code));
CREATE TABLE periods (
  period TEXT PRIMARY KEY, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'closed')), closed_by TEXT, closed_on TEXT);
CREATE TABLE journal_entries (
  id TEXT PRIMARY KEY, entry_date TEXT NOT NULL, period TEXT NOT NULL REFERENCES periods(period),
  source TEXT NOT NULL, source_ref TEXT, memo TEXT,
  status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'posted', 'reversed', 'returned')),
  preparer TEXT NOT NULL, approver TEXT, reverses TEXT, reversed_by TEXT, auto_reverse_on TEXT,
  created_on TEXT NOT NULL, posted_on TEXT, note TEXT);
CREATE TABLE journal_lines (
  je_id TEXT NOT NULL REFERENCES journal_entries(id), line INTEGER NOT NULL,
  account TEXT NOT NULL REFERENCES accounts(code), department TEXT,
  debit_cents INTEGER NOT NULL DEFAULT 0, credit_cents INTEGER NOT NULL DEFAULT 0, memo TEXT,
  PRIMARY KEY (je_id, line));
CREATE TABLE attachments (
  id TEXT PRIMARY KEY, owner_type TEXT NOT NULL, owner_id TEXT NOT NULL, name TEXT NOT NULL,
  content_type TEXT NOT NULL, data BLOB NOT NULL, added_by TEXT NOT NULL, added_on TEXT NOT NULL);
CREATE TABLE budgets (
  department TEXT NOT NULL REFERENCES departments(code), account TEXT NOT NULL REFERENCES accounts(code),
  period TEXT NOT NULL, amount_cents INTEGER NOT NULL, PRIMARY KEY (department, account, period));

-- Master data -------------------------------------------------------------------------------------
CREATE TABLE terms (
  code TEXT PRIMARY KEY, description TEXT NOT NULL, net_days INTEGER NOT NULL,
  discount_pct REAL NOT NULL DEFAULT 0, discount_days INTEGER NOT NULL DEFAULT 0);
CREATE TABLE warehouses (code TEXT PRIMARY KEY, name TEXT NOT NULL, region TEXT);
CREATE TABLE locations (
  code TEXT PRIMARY KEY, warehouse TEXT NOT NULL REFERENCES warehouses(code), name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'stock' CHECK (kind IN ('stock', 'receiving', 'quarantine', 'production')));
CREATE TABLE items (
  sku TEXT PRIMARY KEY, name TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('purchased', 'manufactured', 'phantom')),
  category TEXT, uom TEXT NOT NULL, std_cost REAL NOT NULL, list_price REAL,
  lot_controlled INTEGER NOT NULL DEFAULT 0, shelf_life_days INTEGER,
  lead_time_days INTEGER NOT NULL DEFAULT 0, safety_stock REAL NOT NULL DEFAULT 0,
  moq REAL NOT NULL DEFAULT 0, order_multiple REAL NOT NULL DEFAULT 0,
  preferred_vendor TEXT, planner TEXT, default_location TEXT, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE lots (sku TEXT NOT NULL REFERENCES items(sku), lot TEXT NOT NULL, expiry TEXT, PRIMARY KEY (sku, lot));
CREATE TABLE vendors (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, tin TEXT,
  status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
  quality_hold INTEGER NOT NULL DEFAULT 0, terms TEXT REFERENCES terms(code),
  phone TEXT, email TEXT, address TEXT, remit_account TEXT, since TEXT, note TEXT);
CREATE TABLE vendor_bank_accounts (
  id TEXT PRIMARY KEY, vendor TEXT NOT NULL REFERENCES vendors(id), bank_name TEXT NOT NULL,
  routing TEXT NOT NULL, account_no TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'verified', 'rejected', 'retired')),
  requested_by TEXT, requested_on TEXT, source_ref TEXT, verified_by TEXT, verified_on TEXT, note TEXT);
CREATE TABLE price_agreements (
  id TEXT NOT NULL, vendor TEXT NOT NULL REFERENCES vendors(id), sku TEXT NOT NULL REFERENCES items(sku),
  valid_from TEXT NOT NULL, valid_to TEXT NOT NULL, min_qty REAL NOT NULL DEFAULT 0, unit_price REAL NOT NULL,
  PRIMARY KEY (id, min_qty));
CREATE TABLE approved_substitutes (
  sku TEXT NOT NULL REFERENCES items(sku), substitute TEXT NOT NULL REFERENCES items(sku),
  PRIMARY KEY (sku, substitute));
CREATE TABLE customers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
  terms TEXT REFERENCES terms(code), credit_limit_cents INTEGER NOT NULL DEFAULT 0, credit_hold INTEGER NOT NULL DEFAULT 0,
  region TEXT, parent TEXT, price_list TEXT, phone TEXT, email TEXT, address TEXT);
CREATE TABLE price_lists (code TEXT NOT NULL, sku TEXT NOT NULL REFERENCES items(sku), unit_price REAL NOT NULL,
  PRIMARY KEY (code, sku));
CREATE TABLE boms (
  parent TEXT NOT NULL REFERENCES items(sku), component TEXT NOT NULL REFERENCES items(sku),
  qty_per REAL NOT NULL, scrap_pct REAL NOT NULL DEFAULT 0,
  valid_from TEXT NOT NULL DEFAULT '0001-01-01', valid_to TEXT NOT NULL DEFAULT '9999-12-31',
  PRIMARY KEY (parent, component, valid_from));
CREATE TABLE work_centers (code TEXT PRIMARY KEY, name TEXT NOT NULL, hours_per_day REAL NOT NULL);
CREATE TABLE routings (
  sku TEXT NOT NULL REFERENCES items(sku), step INTEGER NOT NULL, work_center TEXT NOT NULL REFERENCES work_centers(code),
  setup_hours REAL NOT NULL DEFAULT 0, hours_per_unit REAL NOT NULL, PRIMARY KEY (sku, step));

-- Purchasing --------------------------------------------------------------------------------------
CREATE TABLE requisitions (
  id TEXT PRIMARY KEY, requester TEXT NOT NULL REFERENCES users(id), department TEXT NOT NULL,
  created_on TEXT NOT NULL, submitted_on TEXT,
  status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'returned', 'rejected', 'converted', 'cancelled')),
  total_cents INTEGER NOT NULL DEFAULT 0, justification TEXT,
  decided_by TEXT, decided_on TEXT, decision_reason TEXT);
CREATE TABLE requisition_lines (
  req_id TEXT NOT NULL REFERENCES requisitions(id), line INTEGER NOT NULL,
  sku TEXT REFERENCES items(sku), description TEXT, qty REAL NOT NULL, est_unit_price REAL NOT NULL,
  amount_cents INTEGER NOT NULL, vendor TEXT, account TEXT NOT NULL, ship_to TEXT NOT NULL, need_by TEXT,
  po_id TEXT, po_line INTEGER, note TEXT, PRIMARY KEY (req_id, line));
CREATE TABLE approval_requests (
  id TEXT PRIMARY KEY, doc_type TEXT NOT NULL, doc_id TEXT NOT NULL, approver TEXT NOT NULL REFERENCES users(id),
  requested_by TEXT NOT NULL, requested_on TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'returned', 'forwarded', 'cancelled')),
  decided_on TEXT, decided_by TEXT, reason TEXT, note TEXT, forwarded_to TEXT);
CREATE TABLE purchase_orders (
  id TEXT PRIMARY KEY, vendor TEXT NOT NULL REFERENCES vendors(id), buyer TEXT NOT NULL, order_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft', 'sent', 'partially_received', 'received', 'closed', 'cancelled')),
  ship_to TEXT NOT NULL, terms TEXT, sent_on TEXT, total_cents INTEGER NOT NULL DEFAULT 0, note TEXT);
CREATE TABLE po_lines (
  po_id TEXT NOT NULL REFERENCES purchase_orders(id), line INTEGER NOT NULL, sku TEXT REFERENCES items(sku),
  description TEXT, department TEXT,
  qty REAL NOT NULL, unit_price REAL NOT NULL, amount_cents INTEGER NOT NULL, need_date TEXT NOT NULL,
  confirmed_date TEXT, confirmed_price REAL,
  qty_received REAL NOT NULL DEFAULT 0, qty_refused REAL NOT NULL DEFAULT 0, qty_billed REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'cancelled')),
  at_risk INTEGER NOT NULL DEFAULT 0, account TEXT, note TEXT, PRIMARY KEY (po_id, line));
CREATE TABLE vendor_requests (
  id TEXT PRIMARY KEY, vendor TEXT NOT NULL REFERENCES vendors(id),
  kind TEXT NOT NULL CHECK (kind IN ('expedite', 'defer', 'cancel', 'dispute', 'copy_request')),
  po_id TEXT, po_line INTEGER, inv_ref TEXT, wanted_date TEXT, amount_cents INTEGER, note TEXT,
  created_by TEXT NOT NULL, created_on TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'accepted', 'declined')), response TEXT, responded_on TEXT);
CREATE TABLE po_acknowledgements (
  id TEXT PRIMARY KEY, po_id TEXT NOT NULL REFERENCES purchase_orders(id), ack_date TEXT NOT NULL,
  lines TEXT NOT NULL, note TEXT);

-- Receiving and inventory -------------------------------------------------------------------------
CREATE TABLE receipts (
  id TEXT PRIMARY KEY, po_id TEXT NOT NULL REFERENCES purchase_orders(id), receipt_date TEXT NOT NULL,
  received_by TEXT NOT NULL, packing_slip TEXT,
  status TEXT NOT NULL CHECK (status IN ('posted', 'reversed')),
  reversed_by TEXT, reversed_on TEXT, reversal_reason TEXT, note TEXT);
CREATE TABLE receipt_lines (
  receipt_id TEXT NOT NULL REFERENCES receipts(id), line INTEGER NOT NULL, po_line INTEGER NOT NULL,
  sku TEXT, qty_received REAL NOT NULL DEFAULT 0, qty_refused REAL NOT NULL DEFAULT 0,
  refusal_reason TEXT, lot TEXT, expiry TEXT, location TEXT, substitute_for TEXT,
  value_cents INTEGER NOT NULL DEFAULT 0, grni_cents INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (receipt_id, line));
CREATE TABLE inventory_txns (
  id INTEGER PRIMARY KEY AUTOINCREMENT, txn_date TEXT NOT NULL, sku TEXT NOT NULL REFERENCES items(sku),
  location TEXT NOT NULL REFERENCES locations(code), lot TEXT, qty REAL NOT NULL, unit_cost REAL NOT NULL,
  value_cents INTEGER NOT NULL, kind TEXT NOT NULL, ref_type TEXT, ref_id TEXT, user_id TEXT NOT NULL);

-- Manufacturing -----------------------------------------------------------------------------------
CREATE TABLE work_orders (
  id TEXT PRIMARY KEY, sku TEXT NOT NULL REFERENCES items(sku), qty REAL NOT NULL,
  start_date TEXT NOT NULL, due_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('planned', 'released', 'in_progress', 'completed', 'closed', 'cancelled')),
  location TEXT NOT NULL, qty_completed REAL NOT NULL DEFAULT 0, qty_scrapped REAL NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL, created_on TEXT NOT NULL, closed_on TEXT, note TEXT);
CREATE TABLE wo_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT, wo_id TEXT NOT NULL REFERENCES work_orders(id), sku TEXT NOT NULL,
  qty REAL NOT NULL, lot TEXT, location TEXT NOT NULL, issue_date TEXT NOT NULL, user_id TEXT NOT NULL,
  reversal_of INTEGER);

-- Sales and receivables ---------------------------------------------------------------------------
CREATE TABLE sales_orders (
  id TEXT PRIMARY KEY, customer TEXT NOT NULL REFERENCES customers(id), order_date TEXT NOT NULL,
  customer_po TEXT, ship_from TEXT NOT NULL REFERENCES warehouses(code),
  status TEXT NOT NULL CHECK (status IN ('entered', 'on_hold', 'released', 'partially_shipped', 'shipped', 'closed', 'cancelled')),
  hold_reason TEXT, total_cents INTEGER NOT NULL DEFAULT 0, entered_by TEXT NOT NULL, note TEXT);
CREATE TABLE so_lines (
  so_id TEXT NOT NULL REFERENCES sales_orders(id), line INTEGER NOT NULL, sku TEXT NOT NULL REFERENCES items(sku),
  qty REAL NOT NULL, unit_price REAL NOT NULL, amount_cents INTEGER NOT NULL, promise_date TEXT,
  qty_shipped REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'cancelled')), PRIMARY KEY (so_id, line));
CREATE TABLE shipments (
  id TEXT PRIMARY KEY, so_id TEXT NOT NULL REFERENCES sales_orders(id), ship_date TEXT NOT NULL,
  warehouse TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('shipped', 'invoiced', 'reversed')),
  shipped_by TEXT NOT NULL);
CREATE TABLE shipment_lines (
  shipment_id TEXT NOT NULL REFERENCES shipments(id), line INTEGER NOT NULL, so_line INTEGER NOT NULL,
  sku TEXT NOT NULL, qty REAL NOT NULL, lot TEXT, location TEXT NOT NULL, PRIMARY KEY (shipment_id, line));
CREATE TABLE ar_invoices (
  id TEXT PRIMARY KEY, customer TEXT NOT NULL REFERENCES customers(id), invoice_date TEXT NOT NULL,
  period TEXT NOT NULL, so_id TEXT, shipment_id TEXT, total_cents INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'paid', 'voided')), due_date TEXT NOT NULL,
  discount_date TEXT, discount_cents INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL, posted_je TEXT);
CREATE TABLE ar_invoice_lines (
  inv_id TEXT NOT NULL REFERENCES ar_invoices(id), line INTEGER NOT NULL, sku TEXT, description TEXT,
  qty REAL, unit_price REAL, amount_cents INTEGER NOT NULL, account TEXT NOT NULL, PRIMARY KEY (inv_id, line));
CREATE TABLE cash_receipts (
  id TEXT PRIMARY KEY, customer TEXT REFERENCES customers(id), receipt_date TEXT NOT NULL,
  amount_cents INTEGER NOT NULL, reference TEXT, bank_account TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('unapplied', 'partially_applied', 'applied', 'reversed')),
  entered_by TEXT NOT NULL, posted_je TEXT);
CREATE TABLE cash_applications (
  receipt_id TEXT NOT NULL REFERENCES cash_receipts(id), inv_id TEXT NOT NULL REFERENCES ar_invoices(id),
  amount_cents INTEGER NOT NULL, discount_cents INTEGER NOT NULL DEFAULT 0, applied_on TEXT NOT NULL,
  applied_by TEXT NOT NULL, PRIMARY KEY (receipt_id, inv_id));

-- Payables and cash -------------------------------------------------------------------------------
CREATE TABLE ap_invoices (
  id TEXT PRIMARY KEY, vendor TEXT NOT NULL REFERENCES vendors(id), invoice_no TEXT NOT NULL,
  invoice_date TEXT NOT NULL, po_id TEXT, total_cents INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('entered', 'matched', 'on_hold', 'approved', 'paid', 'rejected', 'voided')),
  terms TEXT, due_date TEXT NOT NULL, discount_date TEXT, discount_cents INTEGER NOT NULL DEFAULT 0,
  entered_by TEXT NOT NULL, entered_on TEXT NOT NULL, source_msg TEXT, posted_je TEXT, period TEXT,
  approved_by TEXT, reject_reason TEXT, note TEXT, UNIQUE (vendor, invoice_no));
CREATE TABLE ap_invoice_lines (
  inv_id TEXT NOT NULL REFERENCES ap_invoices(id), line INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('item', 'freight', 'tax', 'other')),
  po_line INTEGER, sku TEXT, description TEXT, qty REAL, unit_price REAL, amount_cents INTEGER NOT NULL,
  account TEXT, department TEXT, grni_cents INTEGER, PRIMARY KEY (inv_id, line));
CREATE TABLE holds (
  id TEXT PRIMARY KEY, doc_type TEXT NOT NULL, doc_id TEXT NOT NULL, line INTEGER, reason TEXT NOT NULL, note TEXT,
  placed_by TEXT NOT NULL, placed_on TEXT NOT NULL, released_by TEXT, released_on TEXT, release_note TEXT);
CREATE TABLE bank_accounts (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, gl_account TEXT NOT NULL REFERENCES accounts(code),
  min_balance_cents INTEGER NOT NULL DEFAULT 0);
CREATE TABLE payment_runs (
  id TEXT PRIMARY KEY, pay_date TEXT NOT NULL, bank_account TEXT NOT NULL REFERENCES bank_accounts(code),
  status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'approved', 'released', 'cancelled')),
  created_by TEXT NOT NULL, created_on TEXT NOT NULL, approved_by TEXT, released_by TEXT, note TEXT);
CREATE TABLE payments (
  id TEXT PRIMARY KEY, run_id TEXT REFERENCES payment_runs(id), vendor TEXT NOT NULL REFERENCES vendors(id),
  vendor_account TEXT NOT NULL, pay_date TEXT NOT NULL, amount_cents INTEGER NOT NULL,
  discount_cents INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('proposed', 'released', 'cleared', 'voided')),
  posted_je TEXT, cleared_on TEXT);
CREATE TABLE payment_allocations (
  payment_id TEXT NOT NULL REFERENCES payments(id), inv_id TEXT NOT NULL REFERENCES ap_invoices(id),
  amount_cents INTEGER NOT NULL, discount_cents INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (payment_id, inv_id));
CREATE TABLE bank_statement_lines (
  id TEXT PRIMARY KEY, bank_account TEXT NOT NULL REFERENCES bank_accounts(code), line_date TEXT NOT NULL,
  amount_cents INTEGER NOT NULL, description TEXT NOT NULL, reference TEXT, matched_to TEXT);

-- Communication -----------------------------------------------------------------------------------
CREATE TABLE messages (
  id TEXT PRIMARY KEY, box TEXT NOT NULL, direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
  from_name TEXT, from_addr TEXT, reply_to TEXT, to_addr TEXT, subject TEXT NOT NULL, body TEXT NOT NULL,
  sent_on TEXT NOT NULL, visible_on TEXT NOT NULL, created_by TEXT,
  disposition TEXT, disposition_ref TEXT, disposition_note TEXT, disposition_by TEXT, disposition_on TEXT);
CREATE TABLE message_reads (msg_id TEXT NOT NULL REFERENCES messages(id), user_id TEXT NOT NULL,
  PRIMARY KEY (msg_id, user_id));
CREATE TABLE message_attachments (
  msg_id TEXT NOT NULL REFERENCES messages(id), n INTEGER NOT NULL, name TEXT NOT NULL,
  content_type TEXT NOT NULL, data BLOB NOT NULL, PRIMARY KEY (msg_id, n));
CREATE TABLE escalations (
  id TEXT PRIMARY KEY, record_type TEXT NOT NULL, record_id TEXT NOT NULL, to_user TEXT NOT NULL REFERENCES users(id),
  reason TEXT NOT NULL, note TEXT, from_user TEXT NOT NULL, created_on TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'answered')), decision TEXT, response TEXT, responded_on TEXT);
CREATE TABLE calls (
  id TEXT PRIMARY KEY, caller TEXT NOT NULL, party_type TEXT NOT NULL, party_id TEXT NOT NULL,
  number TEXT NOT NULL, number_source TEXT NOT NULL, call_date TEXT NOT NULL, transcript TEXT NOT NULL);

-- Simulator state (what counterparties have done; not exposed through the API) --------------------
CREATE TABLE sim_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL,
  ref TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX ix_sim_log ON sim_log (kind, ref);

-- Audit -------------------------------------------------------------------------------------------
CREATE TABLE audit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, business_date TEXT NOT NULL, wall_time TEXT,
  channel TEXT NOT NULL CHECK (channel IN ('api', 'sim', 'setup')),
  actor TEXT, token_id TEXT, method TEXT, path TEXT, action TEXT, object_type TEXT, object_id TEXT,
  before TEXT, after TEXT, outcome TEXT NOT NULL CHECK (outcome IN ('ok', 'refused', 'error')),
  error_code TEXT, idem_key TEXT, request TEXT);
CREATE TABLE idempotency (
  user_id TEXT NOT NULL, key TEXT NOT NULL, status INTEGER NOT NULL, response TEXT NOT NULL,
  PRIMARY KEY (user_id, key));

CREATE INDEX ix_inv_sku ON inventory_txns (sku, location);
CREATE INDEX ix_jl_account ON journal_lines (account);
CREATE INDEX ix_je_period ON journal_entries (period, status);
CREATE INDEX ix_audit_actor ON audit_events (actor, action);
CREATE INDEX ix_msg_box ON messages (box, visible_on);
CREATE INDEX ix_req_lines_po ON requisition_lines (po_id, po_line);
CREATE INDEX ix_holds_doc ON holds (doc_type, doc_id);
