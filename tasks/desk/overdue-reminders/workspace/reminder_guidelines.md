# Past-due reminders - how we do them

_Nadia Haddad, updated August 2026_

Reminders go out once a month from the open invoice export. The statement date is the date the export was run.

## Who gets one

- Every customer with a balance past due on the statement date gets **one** reminder, however many invoices they have.
- Days past due count from the invoice's due date. If the due date is blank in the export, it is the invoice date plus the terms.
- Invoices that are not due yet, or that have a zero balance, are not part of the reminder.
- Anything marked disputed in the memo is with Dale. Leave it out of the reminder completely and don't mention it.

## What a standard reminder says

- Each past-due invoice: invoice number, the balance still owed (not the original amount if they paid part of it), and how many days past due it is.
- The total past due.
- Tone: friendly up to 30 days, firmer after that. Always polite, never threatening.
- If any invoice is more than 60 days past due, add the credit hold paragraph: new service calls for the account are on credit hold (COD only) until the past-due balance is paid.

## Customers on a payment plan

Customers with an active plan in payment_plans.csv get the plan reminder instead: thank them for keeping to the plan and give the amount and due date of their next installment. Don't list invoices and don't mention credit hold, even if old invoices are still open.

## Files

One file per customer, named after the customer, in a reminders folder.
