---
name: review
description: Run a brutally strict structural code review (thermo-nuclear rubric) over a diff or PR, as a skeptical evaluator separate from the code's author. Emits severity-ordered blocking findings and a verdict file. Use for the harness review stage or standalone PR review.
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
Write `.harness/eval_feedback/<task>.json`:
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

## Do not
- Do not rubber-stamp merely-working code.
- Do not propose rewrites that change behavior; this is a quality review, not a redesign of
  intent. Simplifications must preserve behavior.
