# Treasury (TRE)

**TRE-1.1** The operating account must not fall below its minimum balance (on the bank account record in the ERP)
once a payment run is released.

**TRE-1.2** When paying everything PAY-2.1 and PAY-2.2 call for would take the operating account below its minimum,
build the run in this order: first, invoices whose discount expires before the next run; then past-due invoices,
earliest due date first; then the other invoices due before the next run, earliest due date first. Go down the
list and add each invoice that still fits above the minimum. Skip an invoice that would breach it and consider the
next one. Everything left waits for the next run.
