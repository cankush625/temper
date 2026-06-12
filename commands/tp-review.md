---
description: Thermo-nuclear structural code review of the current diff (single, fresh-context evaluator).
argument-hint: "[task-id] [git range or PR#]"
---
Run a single-pass review for: $ARGUMENTS

Load the `review` skill (`.claude/skills/review/SKILL.md`) and apply the thermo-nuclear rubric.
You are the **evaluator, not the author**. Default diff is `git diff HEAD` (or the given range / `gh pr diff <n>`).
Report highest-severity findings first; high-conviction only. Write the verdict to
`.temper/eval_feedback/<task>.json`. `verdict: "block"` is the same bar as a failing receipt —
the task must not be marked passing until the blocking findings are resolved.
