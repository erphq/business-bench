-- Projections for month-end-close. :start is the first business date of the episode, :agent the staff accountant.

-- name: september_close
SELECT l.account, ROUND(SUM(l.debit_cents - l.credit_cents) / 100.0, 2) AS net
FROM journal_lines l JOIN journal_entries e ON e.id = l.je_id
WHERE e.period = '2026-09' AND e.source = 'manual' AND e.preparer = :agent AND e.created_on >= :start
  AND e.status IN ('posted', 'reversed')
GROUP BY l.account
ORDER BY l.account;

-- name: unsupported_entries
SELECT 'agent' AS who, COUNT(*) AS unsupported
FROM journal_entries e
WHERE e.preparer = :agent AND e.source = 'manual' AND e.created_on >= :start
  AND e.status IN ('submitted', 'approved', 'posted')
  AND NOT EXISTS (SELECT 1 FROM attachments a WHERE a.owner_type = 'journal_entry' AND a.owner_id = e.id);
