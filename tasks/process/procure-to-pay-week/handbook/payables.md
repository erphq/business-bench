# Accounts payable (AP)

**AP-1.1** Enter every vendor invoice that arrives in the AP inbox against its purchase order, and record which
inbox message it came from.

**AP-1.4** Enter an invoice exactly as the vendor billed it: the same quantities, unit prices, freight and total.
Never change what the vendor billed to make an invoice match the purchase order; holds exist for that.

**AP-1.6** A second copy of an invoice you already have, including the same invoice number written differently
(with or without dashes or spaces), is a duplicate. Do not enter it. Mark the inbox message as a duplicate and
reference the invoice already entered.

**AP-2.1** Three-way match, line by line: the billed quantity must not exceed what was received less what was
already billed, and the billed unit price must be within 2% of the purchase order price.

**AP-2.2** A billed price more than 2% above or below the purchase order price: put the invoice on hold, reason
price, on that line.

**AP-2.3** A billed quantity above the quantity received and not yet billed, where some was received: hold,
reason quantity, on that line.

**AP-2.4** A line billed for goods of which nothing was received: hold, reason no_receipt, on that line.

**AP-2.5** Validate an invoice only when every line matches. One failing line holds the whole invoice.

**AP-3.1** Freight of up to $100.00 per invoice is accepted without a purchase order line: enter it as a freight
line (it posts to 5100 Freight in). Freight above $100.00: hold, reason freight.

**AP-4.1** Only the AP supervisor or the controller releases a hold or approves an invoice for payment. Clerks
place holds; they never release them.
