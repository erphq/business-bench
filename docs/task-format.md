# Task format

Every task lives in `tasks/<track>/<id>/`.

## Desk track

```
tasks/desk/<id>/
  task.yaml        # ask, category, checks, timeout
  gen.py           # deterministic generator: `python gen.py` rebuilds workspace/ and reference/
  workspace/       # exactly what the harness sees, copied fresh for every run
  reference/       # ground truth for the grader; never mounted for the harness
  check.py         # optional custom grader (type: custom)
```

`task.yaml`:

```yaml
id: payments-match
track: desk
category: bookkeeping          # spreadsheet | reports | extraction | drafting | reformatting | bookkeeping | tooling
title: Match bank payments to open invoices
ask: |
  One or two sentences, exactly as a non-technical owner would type them.
  Name the output files you expect.
followup: null                 # optional second-turn prompt, sent on the same session (not run in v0)
timeout_s: 1200
traps:                         # authoring notes only, never shown to the harness
  - partial payment on INV-2026-0417
checks:
  - type: csv_set_equal
    name: unpaid invoice ids
    path: unpaid.csv
    column: invoice_id
    ref: unpaid.csv
```

Rules for authors:

- The ask is business English. No column specs beyond what a real owner would type, but do name the output files.
- Inputs are messy on purpose: merged header rows, currency strings, mixed date formats, duplicates, requirement buried in an email thread.
- Where the ask cannot be answered from the files, the correct deliverable says so; guessing fails.
- `gen.py` takes an optional `--seed` so entity names and amounts can be re-rolled for a sealed variant.
- Every check must pass on the reference solution. Run `python bench/grade.py tasks/desk/<id> tasks/desk/<id>/reference_solution` if you keep one.

## Check types (bench/grade.py)

| type | fields | passes when |
|---|---|---|
| `file_exists` | path | a file matches the glob |
| `csv_columns` | path, columns, exact? | required columns present (or exact order) |
| `csv_row_count` | path, equals \| equals_ref, tolerance? | row count matches |
| `csv_set_equal` | path, column, ref, ref_column?, normalize? | set of values equals the reference set |
| `csv_values_match` | path, ref, key, columns, min_accuracy?, numeric?, tolerance?, must_match_keys? | per-key values match at or above the accuracy floor, and every must-match key is right. `key` may be a list of columns (a composite key); a must-match key for a composite is a list or a `a|b` string. In numeric mode a blank reference cell requires a blank deliverable cell |
| `xlsx_has_formulas` | path, sheet?, min_count | at least N live formula cells |
| `xlsx_value_present` | path, expected, rel_tol?, near_text?, sheet?, rounding?, raw_value_ok? | some numeric cell equals expected after recalculation, optionally on a row or column mentioning near_text. Text cells count only when they read as one figure ("$1,240.00", "(30.00)", "12.5%"), never dates or ids. Tolerance is max(expected x rel_tol, 0.01); the strict validator requires it to be at most 1.00 unless the check sets `rounding: <reason>` (conversion, proration, estimate), which allows rel_tol up to 0.001. `raw_value_ok: true` declares that the figure legitimately appears in the raw inputs (the validator otherwise rejects pins an agent could satisfy by pasting the export) |
| `xlsx_no_errors` | path, sheet?, max_errors? | no formula cell evaluates to an Excel error (`#NAME?`, `#VALUE!`, `#REF!`, ...) after recalculation; added after the audit found error cells outside the pinned cells passing |
| `text_contains_all` / `_any` / `text_not_contains` | path, phrases | case-insensitive phrase checks |
| `text_matches_all` | path, patterns | every regex matches somewhere in the text |
| `text_numbers_present` | path, numbers, rel_tol?, min_count? | the figures appear in the text within tolerance, ignoring currency symbols, commas, and parentheses |
| `text_sentence_matches` | path, all, none? | one sentence matches every regex in `all` and none in `none`; use it when scattered phrases would pass on unrelated sentences or on a negation |
| `custom` | module | `check(ws, ref)` returns a list of `{name, passed, detail}` |

Paths are globs relative to the workspace. CSV readers also accept `.xlsx`. Column names are matched case- and punctuation-insensitively.

## Build track

```
tasks/build/<id>/
  task.yaml        # ask, seed files, change requests, timeout per turn
  seed/            # messy CSV exports the app must import
  checklist.md     # 15-25 binary acceptance items, each tagged Exact | Rule | Permission | Automation | Persistence | Delivery
  changes/1.md 2.md 3.md
```

The harness must leave `RESULT.json` in the workspace with `{url, admin: {user, password}, restricted: {user, password}, notes, start_command, port}`. Automated probes generate a tester sheet; the remaining items require explicit acceptance testing. This release does not claim a completed independently human-graded sealed set. See `docs/build-baseline.md` and each task's checklist for the current item contract.
