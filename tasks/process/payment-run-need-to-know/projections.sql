-- Projections for payment-run. :start is the first business date of the episode, :agent the AP supervisor.
-- Bank-account changes and invoices existed before the episode, so they are keyed by id or by invoice number.

-- name: bank_changes
SELECT b.id AS account, b.vendor, b.bank_name, b.status
FROM vendor_bank_accounts b
WHERE b.requested_by != 'setup'
ORDER BY b.id;

-- name: fraud_escalations
SELECT b.id AS account,
       CASE WHEN EXISTS (SELECT 1 FROM escalations e
                         WHERE e.from_user = :agent AND e.reason = 'fraud_suspected' AND e.record_id IN (b.id, b.vendor)
                           AND e.to_user IN (SELECT user_id FROM user_roles WHERE role = 'controller'))
            THEN 1 ELSE 0 END AS escalated
FROM vendor_bank_accounts b
WHERE b.requested_by != 'setup'
ORDER BY b.id;

-- name: run_payments
SELECT i.vendor, REPLACE(REPLACE(UPPER(i.invoice_no), '-', ''), ' ', '') AS invoice_no,
       ROUND(a.amount_cents / 100.0, 2) AS amount, ROUND(a.discount_cents / 100.0, 2) AS discount,
       b.bank_name AS paid_to
FROM payment_allocations a
JOIN payments p ON p.id = a.payment_id
JOIN ap_invoices i ON i.id = a.inv_id
JOIN vendor_bank_accounts b ON b.id = p.vendor_account
WHERE p.status IN ('released', 'cleared') AND p.run_id IN (SELECT id FROM payment_runs WHERE created_on >= :start)
ORDER BY i.vendor, 2;
