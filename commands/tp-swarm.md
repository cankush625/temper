---
description: Parallel multi-agent thermo-nuclear review for large/high-risk diffs.
argument-hint: "[task-id] [git range or PR#]"
---
Run a swarm review for: $ARGUMENTS

Load the `review` skill (`.claude/skills/review/SKILL.md`) and run its **Swarm mode**:
1. Partition the review into parallel **lanes** (not files): security, correctness, performance, style.
   Drop any lane that doesn't apply to the diff.
2. Spawn one fresh-context review subagent per lane **in parallel**, each applying the full rubric
   (`docs/review-rubric.md`) in its lane, returning findings as What · Where · Impact · Value · Fix · Severity.
3. Merge into one severity-ordered verdict: dedupe overlaps, `block` if ANY lane has an unresolved
   `Must fix`. **Record it as a signed receipt**: `temper review-capture --in <verdict.json>`
   (`"reviewer": "tp-swarm"`). Print one consolidated severity-ranked table.

Use this only when the diff is large or high-risk; otherwise `/tp-review` is cheaper and enough.
