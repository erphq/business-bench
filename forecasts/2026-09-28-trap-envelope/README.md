# Trap-envelope forecast, 2026-09-28

These are pre-registered forecasts of pass rates for single-trap-off variants of six desk tasks (`envelope.py plan --design single`):
price-increase-notice, proposal-from-notes, inventory-count-reconcile, onboarding-welcome-email, vendor-1099-totals and policy-update-memo.

- **System:** Proto (CLI 0.2.119, `main` 4d974743) with DeepSeek V4.1 Flash, called directly through api.deepseek.com, k = 3.
- **Method:** each prediction starts from the published proto-deepseek canonical rate. Every trap is removed under a Normal(0.5, 1.0) logit prior, so these are prior forecasts, not fitted ones.
- **Different cell:** the forecast uses a different system cell (build and route) from the ledger it draws on. That difference is part of what the score measures.
- **Record:** `registry.jsonl` keeps each prediction's hash, its manifest's hash, and the time and git HEAD at registration. It was committed before any variant attempt ran.

## Result (scored 2026-09-29, `scores/`)

The run had 99 attempts (33 variants × 3) and 54 passed. 2 of 33 forecast cells missed, against about 3.3 expected by chance.

| Task | All traps on | One trap off |
|---|---|---|
| vendor-1099-totals | 1/3 | resubmitted 3/3, two_names 3/3, card_only 2/3, processor_methods 0/3 |
| inventory-count-reconcile | 0/3 | 0/3 for every switchable trap |
| price-increase-notice | 2/3 | annual_list 3/3, lobby_price 1/3, date 0/3, old_notice 0/3 |
| proposal-from-notes | 2/3 | disposal, highbay_count and poles 3/3; lift and old_rates 2/3; old_proposal 1/3 |
| onboarding-welcome-email | 2/3 | arrival 3/3; desk_phone, manager and start_date 2/3; kit 1/3 |
| policy-update-memo | 2/3 | effective_date 3/3; the rest 2/3 |

**Reading:**
- **Unequal traps.** The equal-effect prior is wrong. In vendor-1099-totals, the resubmitted-form and two-names traps cause the failures, and the others don't matter.
- **Unexplained failure.** inventory-count-reconcile fails whichever switchable trap is removed. It goes to the audit queue as a fixed-trap, task or grader question.
- **Wrong direction.** In price-increase-notice, turning date or old_notice off made the task worse. That would come from the variant's wording or from noise at n = 3, and needs checking before it is trusted.
- **Sample size.** Three repetitions per cell is small, so these are directions, not estimates.

## Commit ids after the 2026-09-29 history rewrite

On 2026-09-29 the branch history was rewritten to correct commit authorship. File contents and commit dates are unchanged, but commit ids changed. `registry.jsonl` and `scores/` keep the ids that were current at registration:

| Recorded | Now |
|---|---|
| `d03d97f` (HEAD at registration) | `113efdf` |
| `7a13f0a` (the registration commit, pushed 2026-09-28T23:50Z) | `165ad79` |
