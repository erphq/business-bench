-- Projections for mrp-planner-week. :start is the first business date of the episode, :agent the planner. Orders
-- the planner creates are keyed by item and need date, requests by kind, item and wanted date: ids depend on the
-- order in which things were done.

-- name: planning_data
SELECT sku, lead_time_days, moq, order_multiple, safety_stock
FROM items
ORDER BY sku;

-- name: released_orders
SELECT kind, sku, need_date, qty FROM (
  SELECT 'PO' AS kind, l.sku, l.need_date, ROUND(SUM(l.qty), 4) AS qty
  FROM po_lines l JOIN purchase_orders p ON p.id = l.po_id
  WHERE p.order_date >= :start AND p.buyer = :agent AND p.status NOT IN ('draft', 'cancelled') AND l.status != 'cancelled'
  GROUP BY l.sku, l.need_date
  UNION ALL
  SELECT 'WO', sku, due_date, ROUND(SUM(qty), 4)
  FROM work_orders
  WHERE created_on >= :start AND created_by = :agent AND status != 'cancelled'
  GROUP BY sku, due_date)
ORDER BY kind, sku, need_date;

-- name: vendor_requests
SELECT r.kind, l.sku, COALESCE(r.wanted_date, '') AS wanted_date, COUNT(*) AS requests
FROM vendor_requests r JOIN po_lines l ON l.po_id = r.po_id AND l.line = r.po_line
WHERE r.created_by = :agent
GROUP BY r.kind, l.sku, r.wanted_date
ORDER BY r.kind, l.sku, r.wanted_date;
