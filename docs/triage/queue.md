# Grader-error audit queue

142 failed attempts from `results/latest/attempts.jsonl`, 346 failed required checks. Score = product of the failed checks' grader-error probabilities (the chance the verdict itself is wrong). Tier 1: an invariant transform of the agent's own output passes; 2: a formatting probe passes; 3: model only.

| # | attempt | score | tier | failed | most suspicious failed check | reason |
|---|---|---|---|---|---|---|
| 1 | `tenant-statements__codex-sol__r1` | 0.824 | 3 | 2 | one row per entry | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 0/3 attempts of others; raised by: systematic: other attempts fail it too, the other system fails it too |
| 2 | `tenant-statements__codex-sol__r2` | 0.824 | 3 | 2 | one row per entry | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 0/3 attempts of others; raised by: systematic: other attempts fail it too, the other system fails it too |
| 3 | `tenant-statements__codex-sol__r3` | 0.824 | 3 | 2 | one row per entry | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 0/3 attempts of others; raised by: systematic: other attempts fail it too, the other system fails it too |
| 4 | `tenant-statements__proto-deepseek__r1` | 0.824 | 3 | 2 | one row per entry | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 0/3 attempts of others; raised by: systematic: other attempts fail it too, the other system fails it too |
| 5 | `tenant-statements__proto-deepseek__r2` | 0.824 | 3 | 2 | one row per entry | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 0/3 attempts of others; raised by: systematic: other attempts fail it too, the other system fails it too |
| 6 | `tenant-statements__proto-deepseek__r3` | 0.824 | 3 | 2 | one row per entry | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 0/3 attempts of others; raised by: systematic: other attempts fail it too, the other system fails it too |
| 7 | `staff-utilization__proto-deepseek__r1` | 0.513 | 3 | 1 | utilization per person | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 2/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 8 | `staff-utilization__proto-deepseek__r2` | 0.513 | 3 | 1 | utilization per person | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 2/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 9 | `staff-utilization__proto-deepseek__r3` | 0.513 | 3 | 1 | utilization per person | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 2/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 10 | `clinic-visits-summary__codex-sol__r1` | 0.379 | 3 | 1 | clinic total visits | xlsx_value_present; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks; workbook recalculation involved |
| 11 | `clinic-visits-summary__codex-sol__r3` | 0.379 | 3 | 1 | clinic total visits | xlsx_value_present; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks; workbook recalculation involved |
| 12 | `investor-update__codex-sol__r1` | 0.379 | 3 | 1 | quarter revenue figures | text_numbers_present; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 13 | `investor-update__codex-sol__r2` | 0.379 | 3 | 1 | quarter revenue figures | text_numbers_present; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 14 | `investor-update__codex-sol__r3` | 0.379 | 3 | 1 | quarter revenue figures | text_numbers_present; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 15 | `minutes-from-transcript__codex-sol__r1` | 0.379 | 3 | 1 | minutes facts | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 16 | `minutes-from-transcript__codex-sol__r2` | 0.379 | 3 | 1 | minutes facts | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 17 | `overdue-reminders__codex-sol__r1` | 0.379 | 3 | 1 | per-customer reminder facts | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 18 | `overdue-reminders__codex-sol__r2` | 0.379 | 3 | 1 | per-customer reminder facts | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 19 | `overdue-reminders__codex-sol__r3` | 0.379 | 3 | 1 | per-customer reminder facts | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 20 | `price-increase-notice__codex-sol__r1` | 0.379 | 3 | 1 | lobby arrangement: new price and rounded percent | text_sentence_matches; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 21 | `price-increase-notice__codex-sol__r2` | 0.379 | 3 | 1 | lobby arrangement: new price and rounded percent | text_sentence_matches; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 22 | `supplier-dispute-letter__codex-sol__r1` | 0.379 | 3 | 1 | price clause cited | text_sentence_matches; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 23 | `supplier-dispute-letter__codex-sol__r2` | 0.379 | 3 | 1 | price clause cited | text_sentence_matches; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 24 | `supplier-dispute-letter__codex-sol__r3` | 0.379 | 3 | 1 | price clause cited | text_sentence_matches; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 25 | `vendor-1099-totals__proto-deepseek__r1` | 0.379 | 3 | 1 | which vendors | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 26 | `vendor-1099-totals__proto-deepseek__r2` | 0.379 | 3 | 1 | which vendors | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 27 | `vendor-1099-totals__proto-deepseek__r3` | 0.379 | 3 | 1 | which vendors | custom; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 28 | `weekly-kpi-dashboard__codex-sol__r2` | 0.379 | 3 | 1 | total sales, six weeks | xlsx_value_present; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks; workbook recalculation involved |
| 29 | `weekly-kpi-dashboard__codex-sol__r3` | 0.379 | 3 | 1 | total sales, six weeks | xlsx_value_present; near-miss: only failed check; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks; workbook recalculation involved |
| 30 | `refund-apology-letter__codex-sol__r1` | 0.311 | 3 | 1 | no promise the policy forbids and no wrong order number | custom; near-miss: only failed check; passed by 1/2 other reps of this system, 1/3 attempts of others; raised by: few failed checks, systematic: other attempts fail it too |
| 31 | `refund-apology-letter__codex-sol__r2` | 0.311 | 3 | 1 | no promise the policy forbids and no wrong order number | custom; near-miss: only failed check; passed by 1/2 other reps of this system, 1/3 attempts of others; raised by: few failed checks, systematic: other attempts fail it too |
| 32 | `refund-apology-letter__proto-deepseek__r2` | 0.311 | 3 | 1 | no promise the policy forbids and no wrong order number | custom; near-miss: only failed check; passed by 1/2 other reps of this system, 1/3 attempts of others; raised by: few failed checks, systematic: other attempts fail it too |
| 33 | `refund-apology-letter__proto-deepseek__r3` | 0.311 | 3 | 1 | no promise the policy forbids and no wrong order number | custom; near-miss: only failed check; passed by 1/2 other reps of this system, 1/3 attempts of others; raised by: few failed checks, systematic: other attempts fail it too |
| 34 | `supplier-invoices-to-csv__codex-sol__r1` | 0.187 | 3 | 2 | one row per line | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 2/3 attempts of others; raised by: same system fails it on every rep, systematic: other attempts fail it too |
| 35 | `supplier-invoices-to-csv__codex-sol__r2` | 0.187 | 3 | 2 | one row per line | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 2/3 attempts of others; raised by: same system fails it on every rep, systematic: other attempts fail it too |
| 36 | `supplier-invoices-to-csv__codex-sol__r3` | 0.187 | 3 | 2 | one row per line | csv_set_equal; 2 failed checks; passed by 0/2 other reps of this system, 2/3 attempts of others; raised by: same system fails it on every rep, systematic: other attempts fail it too |
| 37 | `supplier-invoices-to-csv__proto-deepseek__r2` | 0.142 | 3 | 2 | one row per line | csv_set_equal; 2 failed checks; passed by 2/2 other reps of this system, 0/3 attempts of others; raised by: the other system fails it too, systematic: other attempts fail it too |
| 38 | `ap-aging__proto-deepseek__r2` | 0.131 | 3 | 1 | memo names the most overdue bill | text_sentence_matches; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 39 | `ap-aging__proto-deepseek__r3` | 0.131 | 3 | 1 | memo names the most overdue bill | text_sentence_matches; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 40 | `chargeback-tracker__codex-sol__r2` | 0.131 | 3 | 1 | status | csv_values_match; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 41 | `chargeback-tracker__codex-sol__r3` | 0.131 | 3 | 1 | status | csv_values_match; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 42 | `donor-annual-figures__codex-sol__r1` | 0.131 | 3 | 1 | no error cells | xlsx_no_errors; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 43 | `donor-annual-figures__codex-sol__r2` | 0.131 | 3 | 1 | no error cells | xlsx_no_errors; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 44 | `mrr-report__proto-deepseek__r3` | 0.131 | 3 | 1 | churned MRR in May | xlsx_value_present; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 45 | `notes-to-activities__proto-deepseek__r1` | 0.131 | 3 | 1 | owner | csv_values_match; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 46 | `notes-to-activities__proto-deepseek__r2` | 0.131 | 3 | 1 | owner | csv_values_match; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 47 | `policy-update-memo__codex-sol__r2` | 0.131 | 3 | 1 | moved clause and effective date | custom; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 48 | `tuition-collections__codex-sol__r3` | 0.131 | 3 | 1 | total still owed | custom; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 49 | `vendor-price-sheets__codex-sol__r1` | 0.131 | 3 | 1 | vendor names | csv_values_match; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 50 | `vendor-price-sheets__codex-sol__r2` | 0.131 | 3 | 1 | vendor names | csv_values_match; near-miss: only failed check; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 51 | `fifo-cogs__codex-sol__r3` | 0.061 | 3 | 1 | no formula errors | xlsx_no_errors; near-miss: only failed check; passed by 2/2 other reps of this system, 2/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 52 | `kpi-scorecard-page__codex-sol__r3` | 0.061 | 3 | 1 | page structure | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 2/3 attempts of others; raised by: few failed checks |
| 53 | `kpi-scorecard-page__proto-deepseek__r2` | 0.061 | 3 | 1 | page structure | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 2/3 attempts of others; raised by: few failed checks |
| 54 | `sop-from-thread__codex-sol__r2` | 0.061 | 3 | 1 | steps in the right order | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 2/3 attempts of others; raised by: few failed checks |
| 55 | `sop-from-thread__proto-deepseek__r3` | 0.061 | 3 | 1 | steps in the right order | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 2/3 attempts of others; raised by: few failed checks |
| 56 | `business-cards-scanned__proto-deepseek__r1` | 0.036 | 3 | 1 | mobile phones | csv_values_match; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 57 | `commission-calculation__codex-sol__r1` | 0.036 | 3 | 1 | total net payout | xlsx_value_present; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 58 | `contract-renewal-summary__proto-deepseek__r3` | 0.036 | 3 | 1 | term, notice and the vendor's figures | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 59 | `dept-expense-report__codex-sol__r1` | 0.036 | 3 | 1 | memo says Sales is over budget | text_sentence_matches; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 60 | `dept-expense-report__proto-deepseek__r1` | 0.036 | 3 | 1 | memo says Production is over budget | text_sentence_matches; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 61 | `donor-annual-figures__proto-deepseek__r3` | 0.036 | 3 | 1 | FY2025 net cash raised | xlsx_value_present; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 62 | `energy-usage-sites__proto-deepseek__r2` | 0.036 | 3 | 1 | no error cells | xlsx_no_errors; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 63 | `event-attendee-merge__proto-deepseek__r3` | 0.036 | 3 | 1 | guests per booking | csv_values_match; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 64 | `event-schedule-page__proto-deepseek__r2` | 0.036 | 3 | 1 | page structure | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 65 | `expense-categorize__codex-sol__r3` | 0.036 | 3 | 1 | category per txn_id (thread-override rows, REVIEW rows, and policy-settled furniture and supplies merchants must be right) | csv_values_match; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 66 | `fundraiser-progress-page__proto-deepseek__r2` | 0.036 | 3 | 1 | page structure | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 67 | `incident-report__proto-deepseek__r2` | 0.036 | 3 | 1 | no fault language | text_not_contains; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 68 | `incident-summary__codex-sol__r1` | 0.036 | 3 | 1 | memo carries the incident and near-miss totals | text_numbers_present; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 69 | `mrr-report__codex-sol__r2` | 0.036 | 3 | 1 | memo names the month the churn landed in | text_sentence_matches; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 70 | `onboarding-welcome-email__proto-deepseek__r1` | 0.036 | 3 | 1 | start date, manager and desk phone | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 71 | `orders-status-page__proto-deepseek__r1` | 0.036 | 3 | 1 | test orders left off | text_not_contains; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 72 | `price-increase-notice__proto-deepseek__r3` | 0.036 | 3 | 1 | no discount code | text_not_contains; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 73 | `price-list-page__proto-deepseek__r1` | 0.036 | 3 | 1 | page structure | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 74 | `price-list-page__proto-deepseek__r2` | 0.036 | 3 | 1 | discontinued lines left off | text_not_contains; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 75 | `project-status-board__proto-deepseek__r3` | 0.036 | 3 | 1 | page structure | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 76 | `proposal-from-notes__proto-deepseek__r1` | 0.036 | 3 | 1 | pole lights dropped | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 77 | `quarterly-sales-report__codex-sol__r1` | 0.036 | 3 | 1 | memo names the duplicate batch | text_sentence_matches; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 78 | `rent-roll-build__codex-sol__r3` | 0.036 | 3 | 1 | every unit with tenant, rent and renewal flag | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 79 | `returns-analysis__proto-deepseek__r3` | 0.036 | 3 | 1 | total units returned | xlsx_value_present; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 80 | `vendor-tax-forms__codex-sol__r1` | 0.036 | 3 | 1 | legal and DBA names | csv_values_match; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 81 | `xero-sales-invoices-import__proto-deepseek__r1` | 0.036 | 3 | 1 | invoice lines | custom; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 82 | `donor-annual-figures__proto-deepseek__r1` | 0.023 | 3 | 1 | memo says the foundation gift was refunded | text_sentence_matches; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; reference fails it when reformatted; raised by: few failed checks |
| 83 | `regional-sales-monthly__codex-sol__r3` | 0.023 | 3 | 1 | memo says Mountain is missing from the May export | text_sentence_matches; near-miss: only failed check; passed by 2/2 other reps of this system, 3/3 attempts of others; reference fails it when reformatted; raised by: few failed checks |
| 84 | `ar-aging-report__codex-sol__r2` | 0.010 | 3 | 2 | total receivables as of 31 August | xlsx_value_present; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 85 | `deferred-revenue-schedule__codex-sol__r2` | 0.010 | 3 | 2 | upgraded contract | xlsx_value_present; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 86 | `fx-invoice-gains__codex-sol__r1` | 0.010 | 3 | 2 | requested columns | csv_columns; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 87 | `fx-invoice-gains__codex-sol__r2` | 0.010 | 3 | 2 | requested columns | csv_columns; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 88 | `inventory-count-reconcile__proto-deepseek__r2` | 0.010 | 3 | 2 | items that are off | csv_set_equal; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 89 | `inventory-count-reconcile__proto-deepseek__r3` | 0.010 | 3 | 2 | items that are off | csv_set_equal; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 90 | `minutes-from-transcript__codex-sol__r3` | 0.008 | 3 | 2 | minutes facts | custom; 2 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 91 | `price-increase-notice__codex-sol__r3` | 0.008 | 3 | 2 | lobby arrangement: new price and rounded percent | text_sentence_matches; 2 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep, few failed checks |
| 92 | `subscription-status-monthly__codex-sol__r1` | 0.006 | 3 | 3 | active and cancelled by month | custom; 3 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep |
| 93 | `subscription-status-monthly__codex-sol__r2` | 0.006 | 3 | 3 | active and cancelled by month | custom; 3 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep |
| 94 | `helpdesk-tickets-report__codex-sol__r1` | 0.006 | 3 | 3 | Network SLA breaches (business hours, holiday skipped) | xlsx_value_present; 3 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 95 | `monthly-report-v9__codex-sol__r1` | 0.003 | 3 | 2 | one sentence says North has no March data (a gap, not zero sales) | text_sentence_matches; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 96 | `mrr-report__proto-deepseek__r2` | 0.003 | 3 | 2 | churned MRR in May | xlsx_value_present; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 97 | `tuition-collections__codex-sol__r2` | 0.003 | 3 | 2 | total still owed | custom; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 98 | `cash-flow-monthly__proto-deepseek__r2` | 0.002 | 3 | 2 | June money out (fees and the IRS payment from savings) | xlsx_value_present; 2 failed checks; passed by 2/2 other reps of this system, 2/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 99 | `policy-update-memo__codex-sol__r1` | 0.002 | 3 | 2 | moved clause and effective date | custom; 2 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 100 | `bank-reconciliation__proto-deepseek__r2` | 0.001 | 3 | 2 | adjusted balance | xlsx_value_present; 2 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 101 | `gradebook-weighted__codex-sol__r1` | 0.001 | 3 | 2 | no error cells | xlsx_no_errors; 2 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 102 | `lease-abstracts__proto-deepseek__r2` | 0.001 | 3 | 2 | lease dates | csv_values_match; 2 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 103 | `mrr-report__codex-sol__r1` | 0.001 | 3 | 2 | March ending MRR | xlsx_value_present; 2 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks; workbook recalculation involved |
| 104 | `shipping-rate-lookup__proto-deepseek__r2` | 0.001 | 3 | 2 | zone | csv_values_match; 2 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 105 | `shopify-product-import__proto-deepseek__r3` | 0.001 | 3 | 2 | variant price | csv_values_match; 2 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 106 | `team-directory-page__proto-deepseek__r1` | 0.001 | 3 | 2 | every current staff member named | text_contains_all; 2 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 107 | `tip-pooling__proto-deepseek__r3` | 0.001 | 3 | 2 | payout sheet columns | csv_columns; 2 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; raised by: few failed checks |
| 108 | `vendor-spend-categories__codex-sol__r1` | 0.000 | 3 | 5 | no error cells | xlsx_no_errors; 5 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 109 | `subscription-status-monthly__codex-sol__r3` | 0.000 | 3 | 4 | active and cancelled by month | custom; 4 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep |
| 110 | `helpdesk-tickets-report__codex-sol__r3` | 0.000 | 3 | 4 | Network SLA breaches (business hours, holiday skipped) | xlsx_value_present; 4 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 111 | `ar-aging-report__codex-sol__r1` | 0.000 | 3 | 3 | total receivables as of 31 August | xlsx_value_present; 3 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 112 | `weekly-kpi-dashboard__codex-sol__r1` | 0.000 | 3 | 3 | total sales, six weeks | xlsx_value_present; 3 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 113 | `vendor-spend-categories__codex-sol__r2` | 0.000 | 3 | 6 | no error cells | xlsx_no_errors; 6 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 114 | `vendor-spend-categories__codex-sol__r3` | 0.000 | 3 | 6 | no error cells | xlsx_no_errors; 6 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 115 | `production-yield__codex-sol__r1` | 0.000 | 3 | 7 | no error cells | xlsx_no_errors; 7 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 116 | `production-yield__codex-sol__r2` | 0.000 | 3 | 7 | no error cells | xlsx_no_errors; 7 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 117 | `production-yield__codex-sol__r3` | 0.000 | 3 | 7 | no error cells | xlsx_no_errors; 7 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 118 | `ap-aging__codex-sol__r1` | 0.000 | 3 | 4 | 1-30 bucket total | xlsx_value_present; 4 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 119 | `delivery-performance__codex-sol__r2` | 0.000 | 3 | 5 | no error cells | xlsx_no_errors; 5 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 120 | `delivery-performance__codex-sol__r3` | 0.000 | 3 | 5 | no error cells | xlsx_no_errors; 5 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 121 | `sales-pivot-by-rep__codex-sol__r1` | 0.000 | 3 | 5 | no error cells | xlsx_no_errors; 5 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 122 | `sales-pivot-by-rep__codex-sol__r2` | 0.000 | 3 | 5 | no error cells | xlsx_no_errors; 5 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 123 | `helpdesk-tickets-report__codex-sol__r2` | 0.000 | 3 | 5 | Network SLA breaches (business hours, holiday skipped) | xlsx_value_present; 5 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 124 | `energy-usage-sites__codex-sol__r1` | 0.000 | 3 | 4 | Riverside total (both meters) | xlsx_value_present; 4 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 125 | `refund-reconciliation__proto-deepseek__r2` | 0.000 | 3 | 4 | one row per refund | csv_set_equal; 4 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others |
| 126 | `returns-analysis__codex-sol__r1` | 0.000 | 3 | 4 | no formula errors | xlsx_no_errors; 4 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 127 | `bom-cost-rollup__codex-sol__r1` | 0.000 | 3 | 6 | no error cells | xlsx_no_errors; 6 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 128 | `bom-cost-rollup__codex-sol__r3` | 0.000 | 3 | 6 | no error cells | xlsx_no_errors; 6 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 129 | `ap-aging__codex-sol__r3` | 0.000 | 3 | 5 | 1-30 bucket total | xlsx_value_present; 5 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 130 | `menu-item-performance__proto-deepseek__r3` | 0.000 | 3 | 5 | Smashed Avocado Toast quantity | xlsx_value_present; 5 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 131 | `promo-code-analysis__proto-deepseek__r1` | 0.000 | 3 | 5 | codes used | csv_set_equal; 5 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others |
| 132 | `retention-cohorts__codex-sol__r1` | 0.000 | 3 | 7 | no error cells | xlsx_no_errors; 7 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 133 | `retention-cohorts__codex-sol__r3` | 0.000 | 3 | 7 | no error cells | xlsx_no_errors; 7 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 134 | `clinic-visits-summary__codex-sol__r2` | 0.000 | 3 | 6 | clinic total visits | xlsx_value_present; 6 failed checks; passed by 0/2 other reps of this system, 3/3 attempts of others; raised by: same system fails it on every rep; workbook recalculation involved |
| 135 | `cash-flow-monthly__codex-sol__r2` | 0.000 | 3 | 6 | June money out (fees and the IRS payment from savings) | xlsx_value_present; 6 failed checks; passed by 2/2 other reps of this system, 2/3 attempts of others; workbook recalculation involved |
| 136 | `staff-utilization__codex-sol__r1` | 0.000 | 3 | 7 | utilization per person | custom; 7 failed checks; passed by 2/2 other reps of this system, 0/3 attempts of others; raised by: the other system fails it too, systematic: other attempts fail it too |
| 137 | `deferred-revenue-schedule__codex-sol__r3` | 0.000 | 3 | 7 | upgraded contract | xlsx_value_present; 7 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 138 | `permission-forms-scanned__proto-deepseek__r1` | 0.000 | 3 | 9 | requested columns | csv_columns; 9 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; agent did not exit normally |
| 139 | `permission-forms-scanned__proto-deepseek__r3` | 0.000 | 3 | 9 | requested columns | csv_columns; 9 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others; agent did not exit normally |
| 140 | `monthly-report__codex-sol__r1` | 0.000 | 3 | 7 | no formula evaluates to an error | xlsx_no_errors; 7 failed checks; passed by 2/2 other reps of this system, 3/3 attempts of others; workbook recalculation involved |
| 141 | `monthly-report-v9__codex-sol__r3` | 0.000 | 3 | 8 | one sentence says North has no March data (a gap, not zero sales) | text_sentence_matches; 8 failed checks; passed by 1/2 other reps of this system, 3/3 attempts of others |
| 142 | `fifo-cogs__proto-deepseek__r1` | 0.000 | 3 | 9 | no formula errors | xlsx_no_errors; 9 failed checks; passed by 2/2 other reps of this system, 2/3 attempts of others; agent did not exit normally; workbook recalculation involved |

## By task (audit units)

One artifact review usually settles every repetition of the same check, so tasks are ranked by their most suspicious failed attempt.

| # | task | best score | failed attempts | systems | most suspicious check |
|---|---|---|---|---|---|
| 1 | tenant-statements | 0.824 | 6 | codex-sol, proto-deepseek | one row per entry |
| 2 | staff-utilization | 0.513 | 4 | proto-deepseek, codex-sol | utilization per person |
| 3 | clinic-visits-summary | 0.379 | 3 | codex-sol | clinic total visits |
| 4 | investor-update | 0.379 | 3 | codex-sol | quarter revenue figures |
| 5 | minutes-from-transcript | 0.379 | 3 | codex-sol | minutes facts |
| 6 | overdue-reminders | 0.379 | 3 | codex-sol | per-customer reminder facts |
| 7 | price-increase-notice | 0.379 | 4 | codex-sol, proto-deepseek | lobby arrangement: new price and rounded percent |
| 8 | supplier-dispute-letter | 0.379 | 3 | codex-sol | price clause cited |
| 9 | vendor-1099-totals | 0.379 | 3 | proto-deepseek | which vendors |
| 10 | weekly-kpi-dashboard | 0.379 | 3 | codex-sol | total sales, six weeks |
| 11 | refund-apology-letter | 0.311 | 4 | codex-sol, proto-deepseek | no promise the policy forbids and no wrong order number |
| 12 | supplier-invoices-to-csv | 0.187 | 4 | codex-sol, proto-deepseek | one row per line |
| 13 | ap-aging | 0.131 | 4 | proto-deepseek, codex-sol | memo names the most overdue bill |
| 14 | chargeback-tracker | 0.131 | 2 | codex-sol | status |
| 15 | donor-annual-figures | 0.131 | 4 | codex-sol, proto-deepseek | no error cells |
| 16 | mrr-report | 0.131 | 4 | proto-deepseek, codex-sol | churned MRR in May |
| 17 | notes-to-activities | 0.131 | 2 | proto-deepseek | owner |
| 18 | policy-update-memo | 0.131 | 2 | codex-sol | moved clause and effective date |
| 19 | tuition-collections | 0.131 | 2 | codex-sol | total still owed |
| 20 | vendor-price-sheets | 0.131 | 2 | codex-sol | vendor names |
| 21 | fifo-cogs | 0.061 | 2 | codex-sol, proto-deepseek | no formula errors |
| 22 | kpi-scorecard-page | 0.061 | 2 | codex-sol, proto-deepseek | page structure |
| 23 | sop-from-thread | 0.061 | 2 | codex-sol, proto-deepseek | steps in the right order |
| 24 | business-cards-scanned | 0.036 | 1 | proto-deepseek | mobile phones |
| 25 | commission-calculation | 0.036 | 1 | codex-sol | total net payout |
| 26 | contract-renewal-summary | 0.036 | 1 | proto-deepseek | term, notice and the vendor's figures |
| 27 | dept-expense-report | 0.036 | 2 | codex-sol, proto-deepseek | memo says Sales is over budget |
| 28 | energy-usage-sites | 0.036 | 2 | proto-deepseek, codex-sol | no error cells |
| 29 | event-attendee-merge | 0.036 | 1 | proto-deepseek | guests per booking |
| 30 | event-schedule-page | 0.036 | 1 | proto-deepseek | page structure |
| 31 | expense-categorize | 0.036 | 1 | codex-sol | category per txn_id (thread-override rows, REVIEW rows, and policy-settled furniture and supplies merchants must be right) |
| 32 | fundraiser-progress-page | 0.036 | 1 | proto-deepseek | page structure |
| 33 | incident-report | 0.036 | 1 | proto-deepseek | no fault language |
| 34 | incident-summary | 0.036 | 1 | codex-sol | memo carries the incident and near-miss totals |
| 35 | onboarding-welcome-email | 0.036 | 1 | proto-deepseek | start date, manager and desk phone |
| 36 | orders-status-page | 0.036 | 1 | proto-deepseek | test orders left off |
| 37 | price-list-page | 0.036 | 2 | proto-deepseek | page structure |
| 38 | project-status-board | 0.036 | 1 | proto-deepseek | page structure |
| 39 | proposal-from-notes | 0.036 | 1 | proto-deepseek | pole lights dropped |
| 40 | quarterly-sales-report | 0.036 | 1 | codex-sol | memo names the duplicate batch |
| 41 | rent-roll-build | 0.036 | 1 | codex-sol | every unit with tenant, rent and renewal flag |
| 42 | returns-analysis | 0.036 | 2 | proto-deepseek, codex-sol | total units returned |
| 43 | vendor-tax-forms | 0.036 | 1 | codex-sol | legal and DBA names |
| 44 | xero-sales-invoices-import | 0.036 | 1 | proto-deepseek | invoice lines |
| 45 | regional-sales-monthly | 0.023 | 1 | codex-sol | memo says Mountain is missing from the May export |
| 46 | ar-aging-report | 0.010 | 2 | codex-sol | total receivables as of 31 August |
| 47 | deferred-revenue-schedule | 0.010 | 2 | codex-sol | upgraded contract |
| 48 | fx-invoice-gains | 0.010 | 2 | codex-sol | requested columns |
| 49 | inventory-count-reconcile | 0.010 | 2 | proto-deepseek | items that are off |
| 50 | subscription-status-monthly | 0.006 | 3 | codex-sol | active and cancelled by month |
| 51 | helpdesk-tickets-report | 0.006 | 3 | codex-sol | Network SLA breaches (business hours, holiday skipped) |
| 52 | monthly-report-v9 | 0.003 | 2 | codex-sol | one sentence says North has no March data (a gap, not zero sales) |
| 53 | cash-flow-monthly | 0.002 | 2 | proto-deepseek, codex-sol | June money out (fees and the IRS payment from savings) |
| 54 | bank-reconciliation | 0.001 | 1 | proto-deepseek | adjusted balance |
| 55 | gradebook-weighted | 0.001 | 1 | codex-sol | no error cells |
| 56 | lease-abstracts | 0.001 | 1 | proto-deepseek | lease dates |
| 57 | shipping-rate-lookup | 0.001 | 1 | proto-deepseek | zone |
| 58 | shopify-product-import | 0.001 | 1 | proto-deepseek | variant price |
| 59 | team-directory-page | 0.001 | 1 | proto-deepseek | every current staff member named |
| 60 | tip-pooling | 0.001 | 1 | proto-deepseek | payout sheet columns |
| 61 | vendor-spend-categories | 0.000 | 3 | codex-sol | no error cells |
| 62 | production-yield | 0.000 | 3 | codex-sol | no error cells |
| 63 | delivery-performance | 0.000 | 2 | codex-sol | no error cells |
| 64 | sales-pivot-by-rep | 0.000 | 2 | codex-sol | no error cells |
| 65 | refund-reconciliation | 0.000 | 1 | proto-deepseek | one row per refund |
| 66 | bom-cost-rollup | 0.000 | 2 | codex-sol | no error cells |
| 67 | menu-item-performance | 0.000 | 1 | proto-deepseek | Smashed Avocado Toast quantity |
| 68 | promo-code-analysis | 0.000 | 1 | proto-deepseek | codes used |
| 69 | retention-cohorts | 0.000 | 2 | codex-sol | no error cells |
| 70 | permission-forms-scanned | 0.000 | 2 | proto-deepseek | requested columns |
| 71 | monthly-report | 0.000 | 1 | codex-sol | no formula evaluates to an error |
