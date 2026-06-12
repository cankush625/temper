# Source Research

The principles in [`../best-practices.md`](../best-practices.md) and the review
standard in [`../review-rubric.md`](../review-rubric.md) are synthesized from these.

| Source | Author | Key contribution to this harness |
|---|---|---|
| [Harness Design for Long-Running Apps](https://www.anthropic.com/engineering/harness-design-long-running-apps) | Anthropic | File-based handoffs; sprint contracts; evaluator separation; grading with hard thresholds; context resets over summarization |
| [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | Anthropic | JSON feature list with strongly-worded "do not delete tests" rules; `claude-progress.txt`; baseline check at session start; "only mark passing after careful testing"; browser automation to catch false completion |
| [Harness Engineering](https://openai.com/index/harness-engineering/) | OpenAI | Agent-first harness design; encode invariants as lint/CI; optimize codebases for agent legibility; technical-debt garbage collection |
| [Ralph Wiggum as a Software Engineer](https://ghuntley.com/ralph/) | Geoffrey Huntley | The minimal "loop one task per fresh context" pattern; deferred to v2 (`runner.py`) — v1 is the interactive `/harness` skill |
| [thermo-nuclear-code-quality-review](https://github.com/cursor/plugins/blob/main/cursor-team-kit/skills/thermo-nuclear-code-quality-review/SKILL.md) | cursor team-kit | The review stage's rubric: structural simplification, 1000-line smell, severity order, presumptive approval blockers |

Reference implementation that inspired the file layout:
[celesteanders/harness](https://github.com/celesteanders/harness)
(`.harness/runner.py`, `.harness/evaluator.py`, JSON plans, `progress.md`). This
harness keeps the same skeleton but makes the **evidence gate** the centerpiece and
defers the headless runner + separate evaluator process.
