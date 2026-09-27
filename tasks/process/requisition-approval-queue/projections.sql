-- Projections for requisition-approval-queue. :start is the first business date of the episode, :agent the
-- approver. The queue is every approval request assigned to the agent before the episode began; its requisitions
-- existed before the episode, so they are keyed by id.

-- name: decisions
SELECT ar.doc_id AS requisition, ar.status AS decision, COALESCE(ar.forwarded_to, '') AS routed_to
FROM approval_requests ar
WHERE ar.approver = :agent AND ar.doc_type = 'requisition' AND ar.requested_on < :start
ORDER BY ar.doc_id;

-- name: approvals_by_agent
SELECT r.id AS requisition, ROUND(r.total_cents / 100.0, 2) AS total
FROM requisitions r
WHERE r.decided_by = :agent AND r.decided_on >= :start AND r.status IN ('approved', 'converted')
ORDER BY r.id;
