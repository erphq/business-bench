# Authoring guide for desk tasks

This is the contract every task in `tasks/desk/` follows. The validator enforces the mechanical parts
(`bench/validate_tasks.py --strict <id>`); the rest is judgment, and the trajectory reviewer will read
your task's runs with these rules in hand.

## What a task is

A folder in a small business. Someone who is not technical types one to three sentences, names the files
they want back, and walks away. The files in the folder are exports and documents as they really come out
of systems: title rows above the header, currency as text, five date formats, duplicates, a rule that only
exists in the fourth message of an email thread. The deliverable is graded by deterministic checks against
a reference solution. Where the files cannot support an answer, the correct deliverable says so.

```
tasks/desk/<id>/
  gen.py                # deterministic generator: python gen.py [--seed N] rebuilds everything below
  task.yaml             # id, category, title, ask, followup, timeout_s, traps, checks
  workspace/            # exactly what the agent sees
  reference/            # grader ground truth, never mounted for the agent
  reference_solution/   # what a perfect agent leaves behind: the deliverables the ask names, nothing else
  check.py              # optional custom check: check(ws, ref) -> [{name, passed, detail}]
```

Use the shared library. From `gen.py`:

```python
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lib"))
from bizgen import *          # pools, noise, deterministic writers, task_dirs, write_task_yaml, argparse_seed
```

Read `tasks/lib/bizgen/__init__.py` once; it has name and company pools, phone, date and money formatters
with numbered styles, deterministic CSV, XLSX, PDF (text and scanned image), email thread and SQLite
writers, and `write_task_yaml`. `tasks/desk/vendor-contact-merge/gen.py` is the worked example: read it
before writing your first task.

## Rules

1. **Identity.** `id` is kebab-case, unique across the repo, describes the business job (`ar-aging-report`,
   not `task17`). `category` is one of `spreadsheet | reports | extraction | drafting | reformatting |
   bookkeeping | tooling`. `title` is a short owner's phrase.
2. **The ask** is one to three sentences in an owner's words. It names the output files. It never states
   column lists, formulas, or the traps. It may point to a message or note in the folder that carries the
   rules ("Priya's email has the rules"). Write the ask as the last thing, after you know what the data says.
3. **The workspace** has two to six files with realistic names (`orders_export_2026-08.csv`, not `data.csv`).
   At least one file is messy in a way that changes the answer if handled naively. Include a distractor file
   where natural (an old version, an unrelated export). Text files use `\n`; CSV exports may carry a BOM,
   CRLF, or a preamble line, and say so in traps.
4. **Traps** are three to eight per task, listed in `traps:` as authoring notes, each ending with the check
   that catches it in parentheses: `- twelve exact duplicate rows inflate every total (check: regional totals)`.
   A trap no check catches is not a trap; remove it or add the check. At least one trap must defeat the
   obvious one-liner (a plain sum, a plain dedupe, a plain lookup).
5. **The reference** is computed from the ground-truth structures in `gen.py`, never by parsing the messy
   files you just wrote. `reference/` holds what the checks read; `reference_solution/` holds exactly the
   deliverables the ask names, produced from the same truth, so the validator can grade it as if an agent
   had left it.
6. **Checks** are four to ten per task, using the types in `docs/task-format.md`. Prefer exact set and per-key
   value checks with a tolerance over floors. A floor (`min_accuracy`) is allowed only with
   `must_match_keys` pinning every trap row. Every workbook deliverable carries `xlsx_no_errors`. Memo and
   letter facts use `text_sentence_matches` or `text_numbers_present`, never scattered phrase lists. Grade
   facts a deliverable must state, never the judgment it makes; where two answers are defensible, grade
   what both must contain. Where the ask cannot be answered, require the sentence that says so.
7. **Custom checks** (`check.py`) only when no built-in type expresses the rule. Signature
   `check(ws: str, ref: str) -> list[dict(name, passed, detail)]`; open files with the same tolerance for
   case and whitespace the built-ins have; never crash on a missing file, report a failed check.
8. **Determinism.** `python gen.py` twice gives byte-identical output; `--seed N` re-rolls entities and
   amounts while keeping the trap structure. Fixed document properties, fixed zip timestamps, no clock.
   If a check pins seed-dependent values (an id list), `gen.py` writes `task.yaml` itself.
9. **Difficulty.** A competent office worker with Excel finishes in 20 to 60 minutes. `timeout_s` is 1200,
   or 1800 for tasks with more than four input files or any OCR. No task requires the web or a login.
10. **Distinctness.** Different business, different data shape, different deliverable, different trap set
    from every other task in the repo, including the ones your batchmates are writing. Reusing the library
    is expected; reusing a trap list is not. Two tasks may not share an output schema unless the plan says so.
11. **Neutral formats only.** CSV, XLSX, PDF, TXT, MD, SQLite, HTML, ICS. Nothing one harness reads better
    than another.
12. **Honesty.** Do not tune a task to a harness you know. Do not hint at tools. Do not put the answer in a
    file name.

## Category notes

- **spreadsheet**: merges, pivots, lookups, reconciliations. Deliverable CSV or XLSX; XLSX totals should be
  live formulas (`xlsx_has_formulas`) and the workbook must recalculate clean.
- **reports**: XLSX with a summary sheet plus a short memo (`.md` or `.txt`). Pin figures with
  `xlsx_value_present` near a label, plus `text_numbers_present` for the memo; one `text_sentence_matches`
  for the anomaly the memo must name (a gap, a spike, a duplicate batch).
- **extraction**: three to ten PDFs with varied layouts from `write_pdf_document` (vary fonts, block order,
  table styles, page size) and at least one `write_scan_pdf` image-only document. Amounts in different
  currencies or formats across documents. Deliverable CSV; `csv_values_match` on every extracted field.
- **drafting**: input is notes, a thread, a policy, a data sheet; output is a letter, memo, posting, or
  procedure as `.md`/`.txt`. Grade the facts that must appear (names, amounts, dates, counts) and facts that
  must not (a promise the policy forbids) with `text_*` checks. Include one fact the notes get wrong or
  contradict, which the draft must resolve the way the authoritative source says.
- **reformatting**: a target template file in the workspace (`shopify_template.csv`, a sample row) and a
  source in another shape. `csv_columns` with `exact: true`, `csv_set_equal` on the key, `csv_values_match`
  on mapped fields; picklist values must be the target's spellings.
- **bookkeeping**: ledgers, statements, registers. Reconciliations produce a matched list, an unmatched
  list, and a variance; schedules produce one row per period; the sum must tie to the cent (`tolerance: 0.01`).
- **tooling**: one self-contained `index.html` built from the data, no external assets. Check with
  `file_exists`, `text_contains_all` (every entity name), `text_numbers_present` (totals), and a small
  `check.py` that parses the table rows and counts them. Do not require JavaScript to be executed.

## Process

```bash
.venv/bin/python tasks/desk/<id>/gen.py                # build workspace, reference, reference_solution, task.yaml
.venv/bin/python bench/validate_tasks.py --strict <id> # gen twice -> identical; solution passes; empty fails; >=4 checks; >=3 traps
.venv/bin/python bench/grade.py tasks/desk/<id> tasks/desk/<id>/reference_solution   # per-check detail if needed
```

Also grade a deliberately naive solution once (the plain sum, the first-row dedupe) and confirm at least one
check fails; note which in the trap line. When your batch is done, report per task: id, category, files in
the workspace, number of checks and traps, validator line, and one sentence on the hardest trap.
