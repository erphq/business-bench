# Inbound freight accruals (FRT)

Northgate pays Miami Valley Freight Lines (MVF) for inbound deliveries from the vendors that ship freight
collect. MVF bills a month's deliveries on the 12th of the following month, so the freight on each month's
receipts is accrued at month end from MVF's rate schedule for that month. MVF sends its schedules, and any
corrections to them, to the accounting inbox.

**FRT-1.1** Accrue freight for each receipt posted in the month from a vendor on MVF's rate schedule. Vendors that are not
on the schedule ship prepaid and bill freight on their own invoices: accrue nothing for their receipts. A
receipt that has been reversed was not a delivery to us: accrue nothing for it.

**FRT-1.2** The accrual for a receipt is the receipt's value at PO prices (the quantity received times the PO line price)
times the rate of the vendor's lane on MVF's schedule for that month, rounded to the nearest cent (half a cent
rounds up). A correction MVF sends replaces the rate it corrects, for the month it names.

**FRT-1.3** Book one journal entry per receipt, dated the last day of the month: debit 5100 Freight in, credit 2100
Accrued liabilities. Put the receipt number in the entry's memo (for example "Freight accrual RCV-10123,
Mid-State Metals, lane L1"), so every accrual can be traced to the receipt it comes from.

## When a source changes

**FRT-2.1** An accrual is only as good as its source. Until the controller closes the month, when a receipt behind an
accrual is reversed or the rate used for it is corrected, reverse that accrual's entry with a reversal dated
the last day of the month it was booked in, and, if freight is still owed on the receipt, book a new entry at
the corrected figures as in FRT-1.3.

**FRT-2.2** Correct an accrual by reversing its entry, never by posting a difference beside it: an entry left standing
next to a correction still states the old figure, and the auditors trace each receipt's freight to one live
entry.

**FRT-2.3** Leave every other accrual alone. An accrual whose receipt and rate have not changed is not reversed or booked
again, even while the entries around it are being corrected.

**FRT-2.4** Before the month is closed, check each accrual's source again: the receipt's status in the ERP and the latest
word from MVF in the accounting inbox. Tell the controller in writing which accruals you changed and why.
