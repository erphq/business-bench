# Purchasing (PUR)

**PUR-1.1** Buy only against approved requisitions. Every purchase order line references the requisition line or
lines it fills.

**PUR-1.2** Send purchase orders on the day the requisitions are released to purchasing, unless a clause below
says to go back to the requester.

**PUR-3.1** Never order from a vendor that is inactive or on quality hold (the quality-hold flag on the vendor
record). Order the item from its preferred vendor instead. If the item has no usable preferred vendor, return
the requisition line to the requester.

**PUR-3.2** A requisition may name a vendor. Use it when it is active, not on quality hold, and holds a price
agreement for the item; otherwise PUR-3.1 applies.

**PUR-4.2** Consolidate requisition lines for the same item, vendor and ship-to raised in the same week into one
purchase order line. Vendor price agreements price each purchase order line on its own quantity, so split lines
can miss a quantity break.

**PUR-4.3** Price every line at the vendor's price agreement for that line's quantity. Do not type over agreement
prices.

**PUR-4.4** A requisition line without an item number (supplies, repairs and other non-stock purchases) is ordered
as a non-stock line from the vendor the requisition names, at the requisition's estimated price, charged to the
account on the requisition line. PUR-3.2 and PUR-4.3 apply to item lines only; if the named vendor is inactive or
on quality hold, return the line to the requester.

**PUR-4.5** When the quantity needed is below the vendor's minimum order quantity (the item's MOQ), order the MOQ
if the excess will be used within 90 days at the item's average monthly usage over the last six months (the
item-usage report). Otherwise return the requisition line to the requester.

**PUR-5.1** Order for the requisition's need-by date.

**PUR-5.3** When a need-by date is inside the item's lead time (the lead time on the item record, in workdays from
today), order for the earliest date the lead time allows, mark the purchase order line at risk, and tell the
requester.
