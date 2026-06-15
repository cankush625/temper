---
description: Thermo-nuclear code review (full superset rubric) of the current diff, single fresh-context evaluator. Records a signed verdict receipt.
argument-hint: "[task-id] [git range or PR#]"
---
Run a single-pass review for: $ARGUMENTS

Load the `temper-review` skill (`.claude/skills/temper-review/SKILL.md`) and apply the full rubric
(`docs/review-rubric.md`) — the ten lanes (full superset). You are the **evaluator, not
the author**. Default diff is `git diff HEAD` (or the given range / `gh pr diff <n>`).
Report highest-severity findings first (Must/Should/Open/Nice); high-conviction only; each with
What · Where · Impact · Value · Fix. Then **record the verdict as a signed receipt**:
`temper review-capture --in <verdict.json>` (do not hand-write the receipt). `verdict: "block"`
is the same bar as a failing receipt — the task cannot be marked passing until the blocking
findings are fixed and review is re-run on the fixed code.
