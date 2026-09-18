# Human baseline protocol

Budget approved 2026-09-18. Purpose: establish that the tasks are completable by the
people who do this work, how long they take, and how often they get them right under
the same checks the agents face. Without it, no reviewer can say whether a 60% agent
score is impressive or embarrassing.

## Sample

- 50 tasks, stratified: 7 from each of the seven v2 axes plus 1 extra in axis 5, drawn
  at random with a published seed once the v2 tasks exist. Until then, a pilot of 20
  v1 tasks (3 per category, 2 in tooling) at the clerical band.
- Analyst band for v2 tasks; clerical band for the v1 pilot.

## Participants

- 10 bookkeepers or staff accountants and 2 controllers, recruited on Upwork or
  equivalent, US or UK based, 5+ years of experience, screened with one unscored task.
- Each task is attempted independently by two participants who do not see each other's
  work. Controllers take the axis 5 and axis 7 tasks.
- Participants use their own machines and any software they normally use, including
  spreadsheets and, if they choose, AI tools. Whether they used AI is recorded per task
  and published; the baseline is "a competent human with their usual tools".

## Procedure

1. Participant receives the workspace folder and the ask, exactly as an agent would.
   No checks, no reference, no traps.
2. Time starts at download and stops at upload of the deliverables. Self-reported
   interruptions are subtracted only if logged at the time.
3. Deliverables are graded by the same checks as agents, with the frozen scorer, and
   by nothing else.
4. After grading, the participant sees the failed checks and answers two questions:
   was the ask clear, and do they dispute the check. Disputes are logged as task
   issues and count toward the task-correctness audit.

## Published outputs

- Per task: participant id (anonymised), time, pass or fail, failed checks, AI-use flag,
  clarity rating, dispute flag.
- Aggregate: human pass rate per axis, median and p90 time per band, dispute rate,
  and the agent-to-human ratio on the same 50 tasks.
- Raw sheets under `results/human-baseline/<label>/`, same allowlisting rules as agent
  ledgers.

## Budget

| Item | Estimate |
|---|---|
| 50 tasks × 2 attempts × ~45 min analyst band | 75 hours |
| 20-task v1 pilot × 2 attempts × ~25 min | 17 hours |
| Screening, onboarding, post-task questions | 15 hours |
| Total contractor time | ~107 hours |
| At $40 to $70 per hour blended | $4,300 to $7,500 |

## Contractor brief (copy for the posting)

We are measuring how long real business tasks take and how accurately they are done.
You will receive a folder of business files (spreadsheets, PDFs, emails) and a short
request written the way a business owner would write it. Produce the requested files
using whatever tools you normally use. There are no trick questions, but the files are
as messy as real exports: duplicate rows, inconsistent dates, a requirement buried in
an email. If the files cannot support an answer, say so in the deliverable rather than
guessing. Record your start and end time. You will be paid per task at an hourly rate
with a cap per task; accuracy is checked automatically and shared with you afterwards.
Expect 20 to 60 minutes per task. Anonymised timing and accuracy data will be published
as part of an open benchmark; your name will not.
