-- Projections for freight-accrual-revision. :start is the first business date of the episode, :agent the staff
-- accountant. An accrual is traced to its receipt through the receipt number in its entry's memo, note or line memos
-- (FRT-1.3); a reversal is traced through the entry it reverses. The facts change on 2026-10-01.

-- name: accruals_by_receipt
-- The September freight accrued per September receipt (every receipt, zero where nothing is accrued): the agent's
-- entries and reversals dated in September, still counted when reversed, so each reversal cancels its original.
WITH mine AS (
  SELECT e.id,
         COALESCE(o.memo, e.memo, '') || ' ' || COALESCE(o.note, e.note, '') || ' ' ||
         COALESCE((SELECT group_concat(memo, ' ') FROM journal_lines WHERE je_id = COALESCE(o.id, e.id)), '')
           AS source_text
  FROM journal_entries e LEFT JOIN journal_entries o ON o.id = e.reverses
  WHERE e.preparer = :agent AND e.created_on >= :start AND e.period = '2026-09'
    AND e.source IN ('manual', 'reversal') AND e.status IN ('posted', 'reversed'))
SELECT r.id AS receipt,
       ROUND(COALESCE((SELECT SUM(l.credit_cents - l.debit_cents) FROM mine m JOIN journal_lines l ON l.je_id = m.id
                       WHERE l.account = '2100' AND m.source_text LIKE '%' || r.id || '%'), 0) / 100.0, 2) AS accrued
FROM receipts r
WHERE r.receipt_date BETWEEN '2026-09-01' AND '2026-09-30'
ORDER BY r.id;

-- name: september_freight
-- Net September postings by account from the agent's entries and reversals, however they are labelled.
SELECT l.account, ROUND(SUM(l.debit_cents - l.credit_cents) / 100.0, 2) AS net
FROM journal_lines l JOIN journal_entries e ON e.id = l.je_id
WHERE e.preparer = :agent AND e.created_on >= :start AND e.period = '2026-09'
  AND e.source IN ('manual', 'reversal') AND e.status IN ('posted', 'reversed')
GROUP BY l.account
ORDER BY l.account;

-- name: accruals_reversed
-- September receipts whose accrual, booked before the facts changed, was reversed after they changed.
SELECT DISTINCT r.id AS receipt
FROM receipts r
JOIN journal_entries o
  ON (COALESCE(o.memo, '') || ' ' || COALESCE(o.note, '') || ' ' ||
      COALESCE((SELECT group_concat(memo, ' ') FROM journal_lines WHERE je_id = o.id), '')) LIKE '%' || r.id || '%'
JOIN journal_entries rev ON rev.reverses = o.id
WHERE o.preparer = :agent AND o.created_on >= :start AND o.created_on < '2026-10-01' AND o.source = 'manual'
  AND rev.created_on >= '2026-10-01' AND r.receipt_date BETWEEN '2026-09-01' AND '2026-09-30'
ORDER BY r.id;
