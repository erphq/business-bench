-- Projections for procure-to-pay-week. Each block runs on the final database with :start (the first business
-- date of the episode) and :agent (the agent's user id). Keys are business keys: vendor, item, invoice number.
-- Documents from before the episode are excluded by date.

-- name: po_lines
SELECT p.vendor, COALESCE(l.sku, l.description) AS item, p.ship_to,
       ROUND(SUM(l.qty), 4) AS qty_ordered, MIN(l.unit_price) AS unit_price, COUNT(*) AS lines,
       MIN(l.need_date) AS need_date, MAX(l.at_risk) AS at_risk
FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id
WHERE p.order_date >= :start AND p.status NOT IN ('draft', 'cancelled') AND l.status != 'cancelled'
GROUP BY p.vendor, item, p.ship_to
ORDER BY p.vendor, item;

-- name: po_vendors
SELECT DISTINCT p.vendor
FROM purchase_orders p
WHERE p.order_date >= :start AND p.status NOT IN ('draft', 'cancelled')
ORDER BY p.vendor;

-- name: receipt_lines
SELECT p.vendor, COALESCE(pl.sku, pl.description) AS item,
       ROUND(SUM(rl.qty_received), 4) AS qty_received, ROUND(SUM(rl.qty_refused), 4) AS qty_refused,
       COALESCE(GROUP_CONCAT(DISTINCT rl.refusal_reason), '') AS refusal_reason,
       COALESCE(GROUP_CONCAT(DISTINCT CASE WHEN rl.substitute_for IS NOT NULL AND rl.qty_received > 0
                                           THEN rl.sku END), '') AS received_as
FROM receipt_lines rl
JOIN receipts r ON r.id = rl.receipt_id
JOIN po_lines pl ON pl.po_id = r.po_id AND pl.line = rl.po_line
JOIN purchase_orders p ON p.id = r.po_id
WHERE r.receipt_date >= :start AND r.status = 'posted'
GROUP BY p.vendor, item
ORDER BY p.vendor, item;

-- name: ap_invoices
SELECT i.vendor, REPLACE(REPLACE(REPLACE(UPPER(i.invoice_no), '-', ''), ' ', ''), '/', '') AS invoice_no, i.status,
       COALESCE((SELECT GROUP_CONCAT(reason, ',') FROM (
           SELECT DISTINCT h.reason FROM holds h
           WHERE h.doc_type = 'ap_invoice' AND h.doc_id = i.id AND h.released_on IS NULL ORDER BY h.reason)), '')
         AS hold_reasons
FROM ap_invoices i
WHERE i.entered_on >= :start AND i.status NOT IN ('rejected', 'voided')
ORDER BY i.vendor, invoice_no;

-- name: ap_invoice_entries
SELECT i.vendor, REPLACE(REPLACE(REPLACE(UPPER(i.invoice_no), '-', ''), ' ', ''), '/', '') AS invoice_no,
       COUNT(*) AS entries
FROM ap_invoices i
WHERE i.entered_on >= :start AND i.status NOT IN ('rejected', 'voided')
GROUP BY i.vendor, 2
ORDER BY i.vendor, 2;

-- name: ap_invoice_lines
SELECT i.vendor, REPLACE(REPLACE(REPLACE(UPPER(i.invoice_no), '-', ''), ' ', ''), '/', '') AS invoice_no,
       CASE WHEN l.kind = 'item' THEN COALESCE(l.sku, pl.description, 'item') ELSE l.kind END AS item,
       ROUND(SUM(l.qty), 4) AS qty_billed, MAX(l.unit_price) AS unit_price_billed,
       ROUND(SUM(l.amount_cents) / 100.0, 2) AS amount
FROM ap_invoice_lines l
JOIN ap_invoices i ON i.id = l.inv_id
LEFT JOIN po_lines pl ON pl.po_id = i.po_id AND pl.line = l.po_line
WHERE i.entered_on >= :start AND i.status NOT IN ('rejected', 'voided')
GROUP BY i.vendor, 2, item
ORDER BY i.vendor, 2, item;
