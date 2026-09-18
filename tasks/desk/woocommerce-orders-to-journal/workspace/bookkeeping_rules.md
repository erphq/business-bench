# Web store sales into the books

From Grace (Mossbank Accounting). I import journals with `journal_import_template.csv`: those six columns in that
order, one line per account per journal, amounts positive with the Debit or the Credit filled (never both), and no
zero lines. Account Code is the four-digit number only. Dates are YYYY-MM-DD.

## Chart of accounts (the ones the web store touches)

| Code | Account |
|---|---|
| 1000 | Business Checking |
| 1210 | Stripe Clearing |
| 1220 | PayPal Clearing |
| 2200 | Sales Tax Payable |
| 4000 | Coffee Sales |
| 4010 | Equipment Sales |
| 4020 | Subscription Sales |
| 4030 | Merchandise Sales |
| 4100 | Shipping Income |
| 4900 | Sales Discounts |
| 4950 | Sales Returns & Refunds |

## Which orders

Book an order only if it was paid: `completed` and `processing` orders, and `refunded` orders (they were paid first).
`cancelled`, `failed`, `pending` (payment) and `on-hold` (waiting for a bank transfer that has not arrived) are not
sales yet and stay out.

## Sale journal

One journal per paid order, Journal No `WC-<order number>`, dated the day the order was placed.

- Debit the clearing account for the payment method with the order total: Credit Card (Stripe) 1210, PayPal 1220,
  Direct bank transfer 1000.
- Debit 4900 Sales Discounts with the cart discount. Do not net the discount out of product sales.
- Credit product sales with the line subtotals (before discount) by category: Coffee 4000, Brewing Equipment 4010,
  Subscriptions 4020, Merch 4030. Subscription products also carry a Coffee category in WooCommerce; they are
  subscription sales.
- Credit 4100 Shipping Income with the shipping charged and 2200 Sales Tax Payable with the tax.

## Refunds

A refund gets its own journal, Journal No `WC-<order number>-R`, dated the refund date: debit 4950 Sales Returns &
Refunds and credit the same clearing account the order was paid through, for the refunded amount. Do not split tax
out of refunds; I true up sales tax on returns at quarter end. A fully refunded order therefore has two journals.

This file is for August only. Anything dated in September waits for next month's file.
