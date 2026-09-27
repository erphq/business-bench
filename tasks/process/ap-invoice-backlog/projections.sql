-- Projections for ap-invoice-backlog. Each block runs on the final database with :start (the first business date of
-- the episode) and :agent (the agent's user id). Keys are business keys: the vendor, and the invoice number with
-- dashes, spaces and slashes removed. Invoices entered before the episode are excluded by date.

-- name: ap_invoices
-- Every invoice entered during the episode, rejected and voided ones included; holds count only on live invoices.
SELECT i.vendor, REPLACE(REPLACE(REPLACE(UPPER(i.invoice_no), '-', ''), ' ', ''), '/', '') AS invoice_no, i.status,
       CASE WHEN i.status IN ('rejected', 'voided') THEN '' ELSE COALESCE((SELECT GROUP_CONCAT(reason, ',') FROM (
           SELECT DISTINCT h.reason FROM holds h
           WHERE h.doc_type = 'ap_invoice' AND h.doc_id = i.id AND h.released_on IS NULL ORDER BY h.reason)), '')
       END AS hold_reasons,
       i.invoice_date
FROM ap_invoices i
WHERE i.entered_on >= :start
ORDER BY 1, 2, 3;

-- name: ap_invoice_entries
SELECT i.vendor, REPLACE(REPLACE(REPLACE(UPPER(i.invoice_no), '-', ''), ' ', ''), '/', '') AS invoice_no,
       COUNT(*) AS entries
FROM ap_invoices i
WHERE i.entered_on >= :start AND i.status NOT IN ('rejected', 'voided')
GROUP BY i.vendor, 2
ORDER BY 1, 2;

-- name: ap_invoice_lines
SELECT i.vendor, REPLACE(REPLACE(REPLACE(UPPER(i.invoice_no), '-', ''), ' ', ''), '/', '') AS invoice_no,
       CASE WHEN l.kind = 'item' THEN COALESCE(l.sku, pl.description, 'item') ELSE l.kind END AS item,
       ROUND(SUM(l.qty), 4) AS qty_billed, MAX(l.unit_price) AS unit_price_billed,
       ROUND(SUM(l.amount_cents) / 100.0, 2) AS amount
FROM ap_invoice_lines l
JOIN ap_invoices i ON i.id = l.inv_id
LEFT JOIN po_lines pl ON pl.po_id = i.po_id AND pl.line = l.po_line
WHERE i.entered_on >= :start AND i.status NOT IN ('rejected', 'voided') AND i.po_id IS NOT NULL
GROUP BY i.vendor, 2, item
ORDER BY 1, 2, 3;

-- name: non_po_coding
SELECT i.vendor, REPLACE(REPLACE(REPLACE(UPPER(i.invoice_no), '-', ''), ' ', ''), '/', '') AS invoice_no,
       GROUP_CONCAT(DISTINCT l.account) AS account, COALESCE(GROUP_CONCAT(DISTINCT l.department), '') AS department,
       ROUND(SUM(l.amount_cents) / 100.0, 2) AS amount
FROM ap_invoice_lines l
JOIN ap_invoices i ON i.id = l.inv_id
WHERE i.entered_on >= :start AND i.status NOT IN ('rejected', 'voided') AND i.po_id IS NULL
GROUP BY i.vendor, 2
ORDER BY 1, 2;

-- name: screened_messages
-- Inbox messages set aside rather than entered: duplicates, documents returned to the sender, suspicious requests.
SELECT m.id AS message, m.disposition
FROM messages m
WHERE m.box = 'ap' AND m.direction = 'in' AND m.disposition IN ('duplicate', 'rejected', 'suspicious')
ORDER BY m.id;
