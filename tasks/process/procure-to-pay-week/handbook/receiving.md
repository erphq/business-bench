# Receiving (REC)

**REC-1.1** Receive against the purchase order, from the packing slip and what physically arrived. Record every
line that arrived: what you take into stock and what you refuse, with the refusal reason.

**REC-2.1** Accept an over-shipment of up to 5% of the ordered quantity and receive it in full. For more than
5% over, receive the ordered quantity and refuse the excess (reason: over_shipment).

**REC-3.1** For lot-controlled items, record each lot and its expiry date as printed on the packing slip.

**REC-3.2** Refuse any lot with less than six months (182 days) of shelf life left on the day it is received
(reason: short_dated). Accept the other lots of the same shipment.

**REC-4.1** Receive a substitute item only if it is on the ordered item's approved substitutes list, and receive
it against the ordered item's purchase order line. Refuse any other substitute (reason: wrong_item).

**REC-5.1** Goods refused at the dock go back to the vendor on their truck or the next pickup; there is nothing
further to record.
