# Authoring guide for build tasks

A build task is a business asking for an application. The harness has one hour per turn to hand back a
URL, logins, and a `RESULT.json`; a tester then works a checklist; three change requests follow on the
same app. `tasks/build/hvac-field-service/` is the worked example (its checklist predates the enterprise
baseline; new tasks include the baseline from the start).

```
tasks/build/<id>/
  gen.py               # deterministic seeds + reference/counts.json (python gen.py [--seed N])
  task.yaml            # id, category, title, ask, seed, timeout_per_turn_s, result_contract, checklist, reference, core_items, changes, traps
  seed/                # two to four messy CSV exports the app must import
  reference/counts.json# every number the checklist quotes, computed from the ground truth
  checklist.md         # baseline items 1-14 (docs/build-baseline.md, placeholders filled) + app items 15-26
  changes/1.md 2.md 3.md   # owner-words change requests, each followed by 3 numbered checklist items
```

## Rules

1. **The ask** is three to six sentences in an owner's words: who they are, what they track, what must be
   imported (attached), who needs access with what visibility, and that they want a dashboard. It names the
   admin login and one restricted login they expect back. It never names technologies.
2. **Seeds** are messy exports as in the desk track: duplicates to collapse, currency strings, mixed dates,
   padded ids, one impossible value (negative stock, end before start) that must be flagged, not imported
   silently. Two to four files, 60 to 300 rows each. Every count the checklist quotes comes from
   `reference/counts.json`, computed in `gen.py` from the truth, not from re-parsing the files.
3. **The checklist** is the baseline (items 1 to 14 verbatim from `docs/build-baseline.md` with every
   `<PLACEHOLDER>` replaced by this task's entity, rule, and numbers) followed by 10 to 12 app items
   (15 onward): import counts and hygiene, the app's rules (`[Rule]`), automations (`[Automation]`), exact
   computations (`[Exact]`) with worked numbers, and scoped permissions beyond the baseline. Each item is
   binary, has a "How to check" line, and passes only if every stated condition holds. `core_items` lists
   the baseline core (1, 3, 5, 6, 8, 14) plus two or three app items.
4. **Change requests** are one or two owner sentences each, realistic, and each carries three new items
   numbered after the last checklist item (27 to 29, 30 to 32, 33 to 35). One change extends the dashboard
   or a report; one adds a rule or automation; one touches permissions or a workflow stage.
5. **Traps** in `task.yaml` are authoring notes, each naming the item that catches it.
6. **Determinism**: `gen.py` byte-identical for a seed; `--seed N` re-rolls names and amounts, and
   `counts.json` is recomputed, so a sealed variant re-derives its checklist numbers from it.
7. **Parsability**: `bench/build_grade.py` reads items with the pattern `N. (CORE)? [Tag] text` followed by
   indented "How to check" lines. Keep that exact shape. Run
   `.venv/bin/python -c "import re;t=open('tasks/build/<id>/checklist.md').read();print(len(re.findall(r'^(\d+)\. (\(CORE\) )?\[(\w+)\] ', t, re.M)))"`
   and confirm it prints the item count.
8. **Distinctness**: each app is a different business with different entities, scope rule, dashboard
   figures, and automations; no two tasks share their app items.

## Process

```bash
.venv/bin/python tasks/build/<id>/gen.py
.venv/bin/python -c "import yaml;t=yaml.safe_load(open('tasks/build/<id>/task.yaml'));print(t['id'],t['core_items'],len(t['changes']))"
```

Then read the checklist once as the tester would, with only `counts.json` beside it, and fix any item
whose expected value cannot be read off the seed data. Report per task: id, seed files and row counts,
number of items, core items, the three change titles, and the trap you think will fail most agents.
