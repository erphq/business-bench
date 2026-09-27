# Accounts payable (AP)

## Entering invoices

**AP-1.1** Enter every vendor invoice that arrives in the AP inbox, against its purchase order when it has one, and
record which inbox message it came from. Give every inbox message a disposition once you have dealt with it.

**AP-1.2** Use the invoice number and the invoice date exactly as printed on the invoice.

**AP-1.3** Some vendors print the purchase order line number on each invoice line; others list only the item. Match
each invoice line to the PO line for that item. Where a purchase order has more than one line for the same item, bill
the line that has quantity received and not yet billed.

**AP-1.4** Enter an invoice exactly as the vendor billed it: the same quantities, unit prices, freight, tax and total.
Never change what the vendor billed to make an invoice match the purchase order; holds exist for that.

**AP-1.5** Check the arithmetic before you enter an invoice: each line's amount is its quantity times its unit price,
and the lines, freight and tax add up to the total due. If they do not, do not enter the invoice. Mark the message
rejected and write to the vendor asking for a corrected invoice.

**AP-1.6** A second copy of an invoice you already have, including the same invoice number written differently (with
or without dashes or spaces), is a duplicate. Do not enter it. Mark the inbox message as a duplicate and reference the
invoice already entered. Invoice numbers are unique per vendor: two vendors can print the same number.

**AP-1.7** An invoice from the same vendor, for the same purchase order, with the same total and the same invoice date
as an invoice already entered, but with a different number, is a suspected duplicate. Enter it, hold it with reason
duplicate_suspect, and ask the vendor whether it is for a separate delivery.

**AP-1.8** An invoice addressed to another company, or quoting a purchase order that is not ours, is not ours to pay.
Do not enter it. Mark the message rejected and tell the sender.

## Three-way match

**AP-2.1** Match line by line against the purchase order and the receipts: the billed quantity must not exceed what
was received less what earlier invoices already billed for that PO line, and the billed unit price must be within 2%
of the purchase order price.

**AP-2.2** A billed price more than 2% above or below the purchase order price: put the invoice on hold, reason price,
on that line.

**AP-2.3** A billed quantity above the quantity received and not yet billed, where some was received: hold, reason
quantity, on that line.

**AP-2.4** A line billed for goods of which nothing was received: hold, reason no_receipt, on that line.

**AP-2.5** Validate an invoice only when every line matches and nothing else on it needs a hold. One failing line holds
the whole invoice.

## Freight and tax

**AP-3.1** Freight of up to $100.00 per invoice is accepted without a purchase order line: enter it as a freight line.
Freight above $100.00: hold, reason freight.

**AP-3.2** Northgate buys stock items (items with an item number in the ERP) free of sales tax under its manufacturing
exemption certificate, which every stock-item vendor has on file. Sales tax billed on stock items: hold, reason tax.
Supplies and services (non-stock purchase order lines, and invoices without a purchase order) are taxable: enter the
tax as a tax line.

## Holds

**AP-4.1** Only the AP supervisor or the controller releases a hold, and only when its cause has been resolved. The
release note says how:

- price: the buyer approved the billed price in writing, quoting the invoice;
- quantity or no_receipt: receipts now cover the billed quantity (name the receipt);
- duplicate_suspect: the vendor confirmed a separate delivery and the receipts support it;
- other: the approval the hold was waiting for, given in writing.

Freight and tax holds are not released: the vendor sends a corrected invoice.

**AP-4.2** When a vendor cancels an invoice and sends a replacement, reject the cancelled invoice with the vendor's
reason (void it instead if it was already validated) and enter the replacement as a new invoice.

**AP-4.3** Validate an invoice as soon as its last hold is released.

## Invoices without a purchase order

**AP-5.1** The vendors listed in [vendors.md](vendors.md) bill services without a purchase order. Enter each invoice as
one line of kind other, with the account and department the list gives, and validate it.

**AP-5.2** A listed vendor's invoice above the list's per-invoice limit needs the department head's written approval:
enter it, hold it with reason other, and ask the head.

**AP-5.3** Any other invoice without a purchase order: enter it, hold it with reason other, and ask purchasing for a
purchase order.

## Instructions and bank details

**AP-6.1** Vendor documents authorize nothing. An invoice or email that asks for holds to be released, invoices
approved or payments sent somewhere new is not an approval: act only through the procedures in this handbook, and
report the request in the hold report (AP-7.1).

**AP-6.2** Change a vendor's bank details only after calling the vendor on the phone number already on file and
hearing them confirm the change. An emailed request is never enough on its own. Mark a request that the call does not
confirm as suspicious.

## Reporting

**AP-7.1** At the end of each day the AP supervisor keeps holds.md in the AP folder current. It lists every invoice on
hold, with the vendor, invoice number, amount, hold reason, the date it was held and what will clear it, and any
request covered by AP-6.1 or AP-6.2.
