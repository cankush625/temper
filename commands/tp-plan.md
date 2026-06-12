---
description: Turn a ticket/spec into a Temper JSON task list (every task starts "failing").
argument-hint: "[ticket id or description]"
---
Create or update `.temper/plans/<slug>.json` for: $ARGUMENTS

Rules:
- Each task: `{ "id", "title", "acceptance": [...], "status": "failing", "evidence": [] }`.
- `acceptance` must be concrete things `capture.py` can verify — a real command that exits 0
  (e.g. "just validate dev exits 0", "make run-unittests passes"). No vague criteria.
- Append-only: never delete or reorder existing tasks; new work is new tasks.
- Do NOT mark anything `passing` here — that only happens in `/tp-impl` after a receipt.
- Keep the list small and ordered by priority; Temper does one task per session.
