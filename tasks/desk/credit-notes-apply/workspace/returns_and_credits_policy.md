# Returns and credit notes

_Kibble Crate Distributors - accounts receivable procedure, revised March 2026_

## When a return earns credit

- Only lines the warehouse marks **Accepted** at inspection are credited. Rejected lines get nothing. Lines still pending inspection wait for next month's run.
- The credit for a line is the quantity returned times the unit price the customer actually paid on the original invoice (after their account discount), not the list price.

## Restocking fee

- Returns for **Ordered in error** or **Overstock** carry a 15% restocking fee: 15% of that line's credit, rounded to the cent, line by line.
- No fee when the return is our fault or the maker's: damaged in transit, defective, wrong item shipped, recalls.

## Credit notes

- One credit note per RMA, numbered with the RMA number. Its amount is the credited lines less any restocking fees.
- Apply credit notes in RMA number order.
- Apply a credit note first to the invoice named on the RMA, up to that invoice's open balance. Whatever is left goes to the same customer's other open invoices, oldest invoice date first. If the named invoice is already paid, start with the oldest open invoice.
- Anything still left stays on the customer's account as unapplied credit. We do not cut refund checks from this run.

## What to hand back

- `credit_notes.csv`: rma, customer, restocking_fee, credit_amount, applied, unapplied - one row per credit note issued.
- `invoice_balances.csv`: invoice, customer, balance - every invoice on the open AR report, with its balance after the credit notes (0.00 when a credit clears it).
