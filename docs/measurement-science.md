# Measurement science and grader integrity

This work adds three things to Business Bench:

- **Designed difficulty.** Difficulty is set by controlled experiment. The generators have pitfalls that switch on and off, and difficulty settings.
- **A grader that tests itself.** Planted mistakes must be caught, harmless rewrites must still pass, and scorer changes are gated.
- **Deeper process-track tests.** Faults, facts that change mid-process, need-to-know controls, and handbooks generated from a policy registry.

Everything here is offline authoring tooling or an opt-in, declared condition. Without flags:
- every generator writes byte-identical output and is no slower;
- the runner and the grader behave as before;
- published campaigns still verify.

A benchmark that tests itself reports its own defects, so the findings section below is part of the deliverable.

## What was built

| # | Item | Where | Status |
|---|---|---|---|
| 1 | Trap switches and per-trap mutants | `tasks/lib/bizgen/traps.py`, `bench/validate_traps.py`, `bench/check_retrofit.py`, `docs/authoring-traps.md` | 72 generators: all 71 targets plus project-margin |
| 1 | Difficulty settings (size, rules, noise, trap count) | `tasks/lib/bizgen/knobs.py` | pilot on saturated tasks |
| 2 | Measurement graph | `bench/measure_graph.py`, `bench/trap_links.py` | built |
| 3 | Difficulty model | `bench/difficulty.py` | first fit (2 systems) |
| 4 | Delegation envelope | `bench/envelope.py`, `docs/envelope.md` | built; `run.py` now records `started_utc` |
| 5 | Renewable benchmark | `bench/renew.py`, `docs/renewable.md` | saturation, setting search, sealed variants |
| 6 | Mutation testing | `bench/validate_traps.py` | built. Mutants whose cited checks also fail on the reference are reported as unproven |
| 7 | Metamorphic testing | `bench/metamorphic.py` | built |
| 8 | Scorer-change gate | `bench/scorer_gate.py` | built |
| 9 | Failure triage | `bench/triage.py`, `docs/triage.md`, `docs/triage/` | ledger model: check-level AUC 0.84 (grouped CV); artifact probes |
| 10 | bb-erp property, crash and replay testing | `bench/erp_fuzz.py`, `tests/test_erp_properties.py` | built; 7 bugs, each with an expected-failure test |
| 11 | First-divergence diagnosis | | deferred |
| 12 | Fault injection | `erp/bberp/faults.py`, `process_run.py --faults`, `duplicate_effect` | built; payment-run `lost-writes` profile |
| 13 | Belief revision | `tasks/process/freight-accrual-revision/`, `stale_derived_entry` | new task, strict validation seeds 0–4 |
| 14 | Information-flow controls | `erp/bberp/infoflow.py`, `disclose_restricted`, `tasks/process/payment-run-need-to-know/` | sibling task; payment-run unchanged |
| 15 | Executable handbook | `bench/handbook.py`, `tasks/process/*/policies.yaml` | all handbooks regenerate byte for byte; lint in `validate_process.py --strict` |

**Checks passed on the integration branch (macOS, Python 3.12, no LibreOffice, no pdftotext):**
- **Unit tests:** `python -m unittest discover -s tests` fails only the 3 environment tests that also fail on `main` here: packing-slip PDF parsing, ap-invoice-backlog and procure-to-pay-week.
- **Desk validation:** `bench/validate_tasks.py --strict` gives task-for-task the same results as `main` in the same environment.
- **Campaign exports:** `bench/export_campaign.py --verify` verifies 1,122 attempts and the frozen scorer fingerprint. `bench/export_process_campaign.py --verify` passes.
- **Process validation:** `bench/validate_process.py --strict` passes on every task whose scenario builds without pdftotext, and on payment-run with `--faults lost-writes`. The one exception is mrp-planner-week seed 2 (see task defects), which fails on `main` too.
- **Scorer gate:** the `check.py` fallback (commit `dbd13bf`) has 70 control items, 0 flips and 0 violations.

## Findings

### Grader (desk)

**Metamorphic false negatives.**
- `split_sentences` ends a sentence at every line break. So `text_sentence_matches` fails correct hard-wrapped Markdown:
  - 29 of 31 candidate false negatives across 16 tasks;
  - a 72-column wrap fails 6 of 37 Markdown tasks, and a 40-column wrap fails 16.
- `refund-apology-letter/check.py` splits sentences the same way.
- `text_contains_all` doesn't collapse whitespace. For example, "Umber\nCeramics Studio" in project-margin fails.

**Grader errors and case handling.**
- `customer-dedupe/check.py` `check_phones` returns a dict when the file is missing. That raises a TypeError, recorded as a grader error rather than a fail.
- `c_csv_set_equal` raises a KeyError on a missing key column, so it's recorded as a grader error; `csv_values_match` fails cleanly instead.
- Custom checks look files up case-sensitively, whereas `find_file` ignores case.

**`csv_set_equal` can't see repeated rows.** A duplicated row passes "one row per …", and only "row count" catches it. Seen in business-cards-scanned, chargeback-tracker, tenant-statements and event-attendee-merge.

**Mutants a cited check misses.** In each case the mutant is kept in code, out of `MUTANTS`, with a comment.
- **monthly-report and monthly-report-v9, layout:** `xlsx_value_present` accepts the value anywhere in the same row *or* column, so layout doesn't matter and the trap text is stale.
- **overdue-reminders:**
  - dale_hold: the cited check tests a different customer.
  - excluded: "reminder files" is satisfied by any `.md` file.
- **inventory-count-reconcile, export_format:** the values check scores only the reference rows.
- **incident-summary, near_misses:** the cited warehouse check passes; only the total catches it.
- **incident-report:** naming the co-worker as the injured person passes "injured person named", because the witness line puts the real surname next to "injury".
- **bank-reconciliation:** "adjusted balance" passes if any cell near "adjusted" holds the right figure, so the carried, july_cleared and export_format mistakes pass it. "Both sides tie" catches all three.
- **notes-to-activities:** "activity date and type" can't see extra rows.
- **supplier-dispute-letter:** disputing an extra line isn't penalised by "disputed lines with amounts".
- **proposal-from-notes, sensors:** folding the option into the main total passes "priced separately".
- **rent-roll-build, released:** a row kept for the ended lease passes the custom check.
- **expense-categorize, refunds:** both refund rows can be wrong and pass, because of `min_accuracy` 0.95 and no `must_match_keys`.
- **Earlier reports:** event-attendee-merge (repeated rows), tuition-collections (scholarships), minutes-from-transcript (bins decision) and retention-cohorts (orders counted instead of customers).

**Scorer drift.**
- The worktree scorer for `sop-from-thread` lost frozen-v7's line unwrap and 5-sentence window, so it fails a correct reference that the frozen scorer passes.
- The complaints-summary answer moved from 46 to 49 after the freeze.
- 26 of 187 `task.yaml` files differ between the worktree and frozen-v7. `grade.py` also differs: `column_match` and `equals_any`.
- Raw against frozen, the ledger has 104 verdict changes: 103 from fail to pass (60 Proto, 43 Codex) and 1 from pass to fail (Codex).

### Task defects

**Citations that don't resolve:**
- incident-summary: "memo names the worst site"
- mrr-report: "worst month churned MRR" (the real check is "churned MRR in May")
- regional-sales-monthly: "memo names the missing month"
- schedule-change-notices: "notice for each affected agent"

**Over-citation.** In lease-abstracts, step_basis cites "escalation type", which that mistake can't fail.

**Citations missing entirely.** expense-categorize has hand-written trap sentences with no "(checks: …)". monthly-report and monthly-report-v9 have several trap sentences that cite no check, and some of their "traps" are only notes.

**tenant-statements** was failed by both systems on all 6 attempts, on "one row per entry" and "row count" only. Every value check passed.
- The only mistakes that reproduce this pattern are booking the three "Prepaid rent applied" lines as credits, or keeping the 29 June payment.
- Excluding the prepaid lines rests on one phrase in the owner's note. The landlord's statement prints them as credits with their own transaction ids, and without them the reference ledger's storage balance is $495 against the landlord's $0.
- This is a probable specification defect and the top item in the triage queue. It goes first in the human audit.

**Reproducibility:**
- monthly-report-v9's data differs even with the HEAD generator.
- monthly-report and quote-comparison differ in xlsx/pdf bytes.
- contract-renewal-summary (PDF), commission-calculation and petty-cash-reconcile workspaces don't regenerate byte-identically across environments. Their checks and references do.
- bom-cost-rollup's `notes.json` differs between Python 3.11 and 3.12 through float summation. No check depends on it.
- 12 generators had an lxml timestamp bug (`stable_xlsx`), now fixed.

**Process track.** mrp-planner-week seed 2: the `ignore_inbox` negative control doesn't fail "orders released". Seed 2's inbox doesn't change which orders get released, so the control can't show anything. This fails on `main` too.

### bb-erp

The first seven bugs below each have an expected-failure test in `tests/test_erp_properties.py`. They aren't fixed, because a fix changes process behaviour under the provisional pilot campaign.

1. **`gl_reverse_subledger_entry`:** reversing a journal entry that a subledger posted breaks `ledger_ties`, and the document stays payable. Fix: refuse to reverse when the source isn't manual.
2. **Failed commit:** a commit failure leaves the transaction open, and every later request returns 500.
3. **Clock advance isn't atomic:** `sim.advance` commits the date first.
4. **Approved payment runs** have no way forward (a dead end).
5. **Dates aren't validated:** a journal entry dated 2026-10-99 posts, and "next friday" is accepted as a pay date.
6. **Sales-order release** forgets a partial shipment.
7. **Malformed input** returns 500 instead of 422; the transaction is rolled back.

Suspicious but unconfirmed:
- Reusing an idempotency key across different requests returns the first response.
- Manual entries to control accounts are accepted.
- `/openapi.json` hasn't been audited.

Process audit coverage, from `bench/handbook.py lint`:
- **Clauses nothing enforces** (report only): AP-5.3, VEN-1.2, VEN-1.3, RPT-2.2, SEC-1.2, JNL-1.3, PAY-1.1, PUR-1.2, REC-3.1, REC-5.1, APR-1.1.
- **Audit rules bound to no clause:** `callback_before_verify`, `post_to_closed_period`, `plug_to_control_account`.
- **Hard-coded value:** `split_to_fit_limit` builds in APR-2.2's 5-business-day window.

### Renewal

**Saturation.** 116 of 187 tasks are saturated, meaning every published attempt passed. Only one of them has trap switches, because the retrofit targets were chosen for discrimination.

**Why settings were needed.** With trap switches and seeds alone, no setting is credibly harder than the published one, since switches only make a task easier. That is why item 1 now includes difficulty settings.

**Sealed variants** at matched predicted difficulty verify on the tasks where the reference solution passes locally.

### Triage

**Labels.** The ledger model is trained on check-level labels. Codex's raw per-check verdicts in commit `87f624e` match the published attempts byte for byte, and each raw fail that the frozen scorer passes counts as a known grader error.

**What predicts a grader error.** The failure being systematic: other attempts fail the same check too. Near-misses and metamorphic flags don't predict it.

**The queue** (`docs/triage/queue.md`, `tasks.csv`) ranks tenant-statements first, then staff-utilization and clinic-visits-summary.

## Environment notes

- **Byte identity** is checked with an interpreter that has no lxml. The published files were made without it, and openpyxl serialises differently when it's installed.
- **Without LibreOffice,** the grader recalculates workbooks with the `formulas` engine, which gives `#NAME?` on SUMIFS and COUNTIFS. Workbook checks then fail even on the canonical reference.
  - `validate_traps` reports the affected mutants as unproven.
  - The retrofits marked UNVERIFIED-XLSX still need a LibreOffice run: energy-usage-sites, ar-aging-report, clinic-visits-summary, returns-analysis, subscription-status-monthly, plus 14 sealed variants.
- **Without pdftotext,** PDF text falls back to pdfplumber's layout. The packing-slip parser and two process scenarios need pdftotext.

## Open decisions

1. Should an empty duplicate payment run fail an attempt (`duplicate_effect`)? bb-erp already refuses to pay an invoice twice, so a blind retry leaves a second, empty run.
2. Fix the metamorphic strictness findings (`split_sentences`, `text_contains_all`) and the `csv_set_equal` duplicate blindness? These are scorer changes, so they go through the gate and a version bump.
3. Fix the 7 bb-erp bugs? That changes process behaviour, and the pilot results are provisional.
4. Resume first-divergence diagnosis (item 11)?
5. Restore frozen-v7's line unwrap and sentence window in the `sop-from-thread` worktree scorer?
6. Human audit of tenant-statements, with a task fix if confirmed.
