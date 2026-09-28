# Trap-envelope forecast, 2026-09-28

These are pre-registered forecasts of pass rates for single-trap-off variants of six desk tasks (`envelope.py plan --design single`):
price-increase-notice, proposal-from-notes, inventory-count-reconcile, onboarding-welcome-email, vendor-1099-totals and policy-update-memo.

- **System:** Proto (CLI 0.2.119, `main` 4d974743) with DeepSeek V4.1 Flash, called directly through api.deepseek.com, k = 3.
- **Method:** each prediction starts from the published proto-deepseek canonical rate. Every trap is removed under a Normal(0.5, 1.0) logit prior, so these are prior forecasts, not fitted ones.
- **Different cell:** the forecast uses a different system cell (build and route) from the ledger it draws on. That difference is part of what the score measures.
- **Record:** `registry.jsonl` keeps each prediction's hash, its manifest's hash, and the time and git HEAD at registration. It was committed before any variant attempt ran.
