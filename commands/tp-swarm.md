---
description: Parallel multi-agent thermo-nuclear review for large/high-risk diffs.
argument-hint: "[task-id] [git range or PR#]"
---
Run a swarm review for: $ARGUMENTS

Load the `review` skill (`.claude/skills/review/SKILL.md`) and run its **Swarm mode**:
1. Partition the diff into 2–4 coherent slices (by top-level dir / file group).
2. Spawn one fresh-context review subagent per slice **in parallel**, each applying the full rubric to its slice only.
3. Merge findings into a single severity-ordered verdict at `.temper/eval_feedback/<task>.json` —
   `block` if ANY slice blocks. Print one consolidated summary.

Use this only when the diff is large or high-risk; otherwise `/tp-review` is cheaper and enough.
