---
description: Post-merge tidy — verify the task, delete the merged branch, update tracker, log it.
argument-hint: "[task-id]"
---
After the PR for $ARGUMENTS is merged:

- Confirm the task is `passing` with valid evidence (don't clean up unverified work).
- Delete the merged feature branch; update the tracker/issue status if CLAUDE.md configures one.
- Append a closing entry to `.temper/progress.md`.

Do NOT delete plans or evidence records — the append-only ledger is the audit trail.
