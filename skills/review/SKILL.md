---
name: review
description: Run a brutally strict structural code review (thermo-nuclear rubric) over a diff or PR, as a skeptical evaluator separate from the code's author. Emits severity-ordered blocking findings and a verdict file. Backs /tp-review (single) and /tp-swarm (parallel); also usable standalone for PR review.
---

# /review — thermo-nuclear code review

You are the **evaluator, not the author**. Judge the code as written; do not assume the
author's good intent excuses structural problems. Full rubric:
[`docs/review-rubric.md`](../../docs/review-rubric.md). Read it before reviewing.

## Inputs
- A diff: default `git diff HEAD` (or a named range / PR). For a GitHub PR use
  `gh pr diff <n>`.
- Optionally the task id being reviewed, to write a verdict file.

## Process
1. **Baseline analysis.** Read the diff in full. For each meaningful change, ask: is there
   a "code judo" move that makes this dramatically simpler while preserving behavior?
2. **Apply the seven standards** and the **presumptive approval blockers** from the rubric.
   Check file sizes (flag >~1000 lines), ad-hoc branching in shared paths, leaked
   feature-specific logic, unnecessary optionality / casts, duplicated helpers.
3. **Report highest-severity first** (structural regressions → simplifications → branching
   → boundaries → file size → modularity → legibility). High-conviction findings only; skip
   nits. Fewer comments, larger structural impact. Direct and serious, never rude.

## Output
Write `.temper/eval_feedback/<task>.json`:
```json
{
  "task": "T1",
  "verdict": "pass",
  "findings": [
    {"severity": "structural-regression", "where": "path:line", "what": "...", "fix": "..."}
  ]
}
```
- `verdict: "block"` if any presumptive blocker is present and unjustified. A blocked
  review is the same bar as a failing receipt: the task must not be marked passing until
  resolved.
- Also print a short summary to the conversation.

## Swarm mode (/tp-swarm) — for high-risk or large diffs
When invoked as a swarm, parallelize the single review above:
1. **Partition** the diff by area (e.g. by top-level dir or coherent file group) into 2–4 slices.
2. **Spawn one review subagent per slice in parallel**, each with a fresh context and this same
   rubric, reviewing only its slice. Subagents return findings as the JSON `findings` array.
3. **Merge** all findings into one verdict: dedupe, re-sort by the rubric's severity order, and set
   `verdict: "block"` if *any* slice blocks. Write the single merged
   `.temper/eval_feedback/<task>.json` and print a consolidated summary.

Use swarm only when the diff is large or high-risk; for ordinary changes the single pass is
cheaper and sufficient (the rubric: evaluator value is highest at the edge of model capability).

## Do not
- Do not rubber-stamp merely-working code.
- Do not propose rewrites that change behavior; this is a quality review, not a redesign of
  intent. Simplifications must preserve behavior.
