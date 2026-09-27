# bb-erp: the system the agent operates

Status: draft for review, 2026-09-26. Companion to [README.md](README.md).

bb-erp is a small ERP written for this benchmark. It covers purchasing, receiving,
payables, sales, receivables, inventory, manufacturing, and the general ledger for one
company, with the controls and the audit trail that process tasks need. It is Python
and SQLite behind a standard-library HTTP server, so a scenario is one database file
and a reset is a file copy.

## 1. Topology

One attempt:

```
runner (host)
 ├─ control API: reset, advance clock, export      (host-only port, runner token)
 ├─ erp container:   bb-erp HTTP API on :8080, SQLite on a volume only this container mounts
 │        ▲
 │        │  private network "attempt-<id>"
 │        │
 └─ agent container: harness, `erp` command, /run/ws workspace; egress to the model provider
```

The grader reads the exported database and audit log after the final clock advance.

## 2. Company archetype for the pilot

Northgate Valve Co. makes brass valves and fittings in one plant and sells to
distributors and contractors from two warehouses. Scale at the clerical band:

| Area | Contents |
|---|---|
| Users | 20 named users in purchasing, receiving, AP, sales, credit, production, accounting, and management, each with a role, department, approval limit, manager, and leave calendar |
| Items | about 120: bar stock, castings, seals and gaskets (lot-controlled, with expiry), purchased fittings, subassemblies including one phantom, finished valves |
| Bills of materials | multi-level, with scrap rates, effectivity dates, and one pending engineering change |
| Work centers | four, with daily capacity and a plant calendar |
| Vendors | about 30, with terms, TINs, verified bank accounts, status, quality-hold flag, preferred items, price agreements with quantity breaks and validity dates, and approved substitutes |
| Customers | about 60, with credit limits, terms, price lists, ship-to addresses, tax status, and payment behaviour profiles |
| Chart of accounts | about 60 accounts; AP, AR, inventory, GRNI, and cash are control accounts |
| Budgets | per department, account, and month for the fiscal year |
| History | twelve months of transactions produced by running the simulator with the oracle policies, so aging, usage averages, margins, and every subledger tie from the first turn |

Names, amounts, dates, and the positions of planted exceptions come from the seed.

## 3. Data model

| Domain | Tables |
|---|---|
| Organisation | users, roles, role_permissions, approval_limits, delegations, departments, calendar |
| Master data | items, lots, warehouses, locations, boms, bom_lines, work_centers, routings, vendors, vendor_bank_accounts, price_agreements, approved_substitutes, customers, ship_to, price_lists, tax_codes, terms, accounts, budgets |
| Purchasing | requisitions, requisition_lines, approval_requests, purchase_orders, po_lines, po_acknowledgements |
| Receiving | receipts, receipt_lines, returns_to_vendor |
| Payables | ap_invoices, ap_invoice_lines, holds, payment_runs, payments, payment_allocations, vendor_credits |
| Sales | quotes, sales_orders, so_lines, allocations, shipments, shipment_lines, rmas |
| Receivables | ar_invoices, ar_invoice_lines, cash_receipts, applications, deductions, dunning_actions |
| Inventory | inventory_transactions, transfers, cycle_counts, adjustments (on-hand is derived from transactions) |
| Manufacturing | work_orders, wo_material_issues, wo_completions, mrp_runs, mrp_suggestions |
| Ledger | periods, journal_entries, journal_lines, bank_accounts, bank_statement_lines, bank_matches |
| Communication | messages (inbox and outbox, with attachments), dispositions, escalations, calls |
| Audit | audit_events |

Every document row carries its creator, its business and wall-clock creation times, a
status, and a reason for each status change.

## 4. Document lifecycles

| Document | States | Notes |
|---|---|---|
| Requisition | draft, submitted, approved, returned, rejected, converted | approval requests follow the delegation-of-authority table; routing to the next approver is an action the agent takes |
| Purchase order | draft, approved, sent, partially received, received, closed, cancelled | only a sent PO can be received; vendors act only on sent POs |
| Receipt | posted, reversed | lot and expiry are captured for lot-controlled items; refused quantity is recorded with a reason; a different item can be received as a substitution for a PO line |
| AP invoice | entered, matched, on hold, approved for payment, paid, rejected, voided | holds carry reason codes; lines record amounts as billed |
| Payment | proposed (in a run), released, cleared, voided | pays only to a verified bank account |
| Sales order | entered, on hold (credit or pricing), released, allocated, partially shipped, shipped, invoiced, cancelled | |
| Work order | planned, released, in progress, completed, closed | release checks component availability; closing posts variances |
| Journal entry | draft, submitted, approved, posted, reversed | preparer and approver must differ above the handbook threshold |
| Period | open, closing, closed | postings dated in a closed period are refused |

## 5. Hard controls

The system refuses these requests and logs each refusal as a probe:

- any action outside the user's role permissions;
- an approval above the user's limit;
- an approval by the request's requester or the document's preparer;
- a posting dated in a closed period;
- a receipt against a purchase order that has not been sent;
- a payment of an invoice that is on hold or not approved for payment;
- a payment to a bank account that is not verified;
- a new PO or payment for a vendor whose status is inactive;
- deleting a posted document, or editing one beyond the actions its lifecycle allows.

Everything else the handbook asks for is a soft control: the system accepts the request
and the grader judges it. Examples: ordering from a vendor with the quality-hold flag
set, accepting an over-shipment above the handbook's tolerance, receiving a substitute
that is not on the approved list, marking a new bank account verified without a call to
the number on file.

## 6. API

- JSON over HTTP with a bearer token per user. Every response carries the business date.
- Resources: `/requisitions`, `/purchase-orders`, `/receipts`, `/ap-invoices`,
  `/payment-runs`, `/payments`, `/vendors`, `/items`, `/boms`, `/sales-orders`,
  `/shipments`, `/ar-invoices`, `/cash-receipts`, `/work-orders`, `/inventory`,
  `/journal-entries`, `/periods`, `/budgets`, `/reports/{name}`, `/mrp`, `/inbox`,
  `/outbox`, `/escalations`, `/calls`, `/audit` (the caller's own events; all events for
  the auditor role).
- Listing supports filters and cursor pagination. `GET /{resource}/{id}` returns the
  document with its lines, status history, holds, and links to related documents.
- State changes are POSTs to named actions (`/purchase-orders/{id}/send`,
  `/ap-invoices/{id}/holds`, `/requisitions/{id}/route`). There is no generic status
  edit.
- Every POST accepts an `Idempotency-Key`. A retry with the same key returns the first
  result. A retry without one can create a duplicate document, and the duplicate is the
  agent's error.
- Errors are `application/problem+json` with a machine code (`over_limit`,
  `period_closed`, `requester_cannot_approve`, and so on) and one sentence.
- The OpenAPI 3.1 document is at `/openapi.json`.

Reports: trial balance, GL detail, AP aging, AR aging, GRNI, inventory valuation, open
purchase orders, open sales orders, budget against actual with commitments, cash
position, sales and margin by item and customer, work-order status, MRP exceptions.

## 7. The `erp` command

```
erp whoami                                   # user, role, limits, business date
erp docs [topic]                             # API reference and the handbook's contents
erp get /purchase-orders --query status=sent vendor=V-0142
erp post /purchase-orders --data @po.json --key po-2026-10-05-1
erp inbox list --box ap --unread
erp inbox read MSG-2231
erp inbox attachment MSG-2231 1 -o invoice.pdf
erp inbox mark MSG-2238 --disposition duplicate --ref APINV-5512
erp escalate APINV-5519 --to maya.chen --reason price_variance --note "..."
erp call vendor V-0142 --number on-file
erp report grni --as-of 2026-10-09
erp mrp run --horizon 8w
```

Output is JSON by default and a table with `--table`. The command reads `ERP_URL` and
`ERP_TOKEN` from the environment. It is a thin client over the HTTP API; curl can do
everything it does.

## 8. Counterparties and the clock

The business clock moves only when the runner advances it. On each advance the
simulator processes the days in order and, within a day, the actors in a fixed order:
bank, vendors, customers, warehouse, approvers, managers. Each actor is a named user in
the system. Its actions are ordinary API calls and appear in the audit log.

| Actor | Reacts to | Behaviour, from the scenario's profiles |
|---|---|---|
| Approver | approval requests assigned to them | next business day, approve or reject by their rules (limit, budget, support attached); a request sent to someone on leave waits unless it is routed to their delegate |
| Vendor | sent POs, disputes, expedite requests, calls | acknowledge with a confirmed date and any price notice; ship on that date with the planted fill, lot, and substitution pattern for each item; invoice after the planted delay with the planted billing defects; answer a dispute with a credit memo or a refusal; answer a call with the scripted facts |
| Customer | invoices, dunning, holds | place scheduled orders by email; pay by profile (on time, late, short with a reason, wrong reference, parent paying for a subsidiary); give a promise-to-pay date when dunned |
| Bank | released payments, customer payments | statement lines on the next business day, plus planted fees and a returned payment |
| Warehouse | transfers, count requests | move stock; report counts and damage by message |
| Manager | escalations with a reason code, journal entries submitted for approval | reply with the scenario's decision for that record and reason (accept the variance, keep the hold, write it off); approve entries with support attached and return entries without |

Vendor behaviour keys on the item and the PO line the agent actually sent. A vendor
whose profile ships 1.8% over ships 1.8% over whatever quantity the agent ordered, so
consequences follow the agent's actions.

A structured action sent to the wrong person or with the wrong reason code gets the
response the scenario defines for it, which is usually no action. Free-text messages
are stored, and no actor reads them.

## 9. Audit log

One row per API request, refused requests included: event id, business date, wall time,
actor, token id, method, path, action code, object type and id, before and after images
for writes, outcome (ok, or refused with the error code), and idempotency key. Reads
are logged too, for diagnostics. The grader's audit rules read this table; for example
`bank_change_without_callback` looks for a call to the number on file between the
change request and the verification.

## 10. Scenario format

A task's `gen.py --seed N` writes a scenario directory:

| File | Contents | Visible to the agent |
|---|---|---|
| `scenario.db` | the seeded database at the start of turn 1 | through the API only |
| `world.json` | counterparty profiles and the scheduled events | no |
| `turns.yaml` | business date, sender, request, and budget for each turn | one request per turn, as the prompt |
| `handbook/` | the policy manual, one Markdown file per policy, clauses numbered | yes, copied to the workspace |
| `truth.json` | the planted exceptions and the clauses each one exercises | no |

For a later cell on another system, `gen.py` also writes the scenario as neutral
records (JSON Lines per document type) that an importer for that system can load.

## 11. Runner control API

`reset(snapshot)`, `advance(to_date)`, `export()` (a copy of the database and the audit
log), and `health`. It listens on a host-only port and accepts only the runner token.
