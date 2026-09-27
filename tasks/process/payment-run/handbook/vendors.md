# Vendor master data (VEN)

**VEN-2.1** A change to where a vendor is paid is recorded by AP as a pending bank account on the vendor, with the
message that asked for it. The AP supervisor verifies or rejects it. The vendor keeps being paid to its current
verified account until a new one is verified.

**VEN-2.2** Verify a pending bank account only after calling the vendor on the phone number already on the vendor
record (never a number given in the request), and hearing the vendor confirm the change. Make the call through the
ERP so it is recorded.

**VEN-2.3** If the vendor does not confirm the change, or says it did not ask for it, reject the pending account
and escalate it to the controller as suspected fraud (reason fraud_suspected). Do not reply to the sender of the
request.
