# Best Practices for an Agent Harness

Synthesized from four sources (see `research/`):
- Anthropic — [Harness Design for Long-Running Apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- Anthropic — [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- OpenAI — [Harness Engineering](https://openai.com/index/harness-engineering/)
- Geoffrey Huntley — [Ralph Wiggum as a Software Engineer](https://ghuntley.com/ralph/)

The ideas that appear in all four:

## Core principles
1. **Separate generation from evaluation.** Agents reliably overrate their own work. A standalone skeptical evaluator is far easier to tune than a self-critical generator. → see [`anti-bluffing.md`](anti-bluffing.md) and [`review-rubric.md`](review-rubric.md).
2. **Context windows constrain; structured files solve.** A JSON task list, progress notes, and git history bridge sessions. If it's not in the repo, it doesn't exist for the agent.
3. **One task per session.** Prevents more failures than almost anything else. Relax as reliability proves out; tighten if quality drops.
4. **Verify before building.** Always run a baseline check at session start. Compounding bugs across sessions is a top failure mode.
5. **Wire fast feedback loops.** Type checkers, linters, tests, scanners as backpressure — they must cycle quickly.
6. **Repository as system of record.** Push decisions, patterns, and context into the repo; undiscoverable info is illegible to the agent.
7. **Humans steer, agents execute.** Engineers design the environment and feedback; agents write code.
8. **Strip harness complexity with each model upgrade.** Every component encodes an assumption about what the model can't do. These go stale fast — build for stripping down, not adding up.

## State management
- **Task list = JSON, not Markdown** — corruption-resistant, append-only. Never remove or reorder items; only flip status from incomplete to complete *after verification*.
- **Progress notes** — free-form session log: what got done, bugs found/fixed, next priorities, decisions. Written at each session's end.
- **Plan/spec file** — original requirements stored in-repo.
- **Git history** — descriptive commits as a recovery + memory mechanism; read recent commits at session start.
- **CLAUDE.md / AGENTS.md = map, not encyclopedia** (~100 lines): a table of contents into a deeper `docs/`.

## Session protocol
Orient → Setup → **Verify baseline** → Select ONE task → Implement → **Test for real** (not just unit tests; exercise the actual UI/API/CLI) → Update state (mark done, commit, write progress) → Clean exit.

## Feedback & backpressure
- Automated verification rejects invalid output; feedback must be fast.
- Browser/UI or real CLI automation so "complete" requires genuine interaction, not a self-assessment.
- Evaluator uses **concrete, gradable criteria with hard thresholds**, weighted toward model weaknesses — not "is this good?".

## How Temper applies the above
- The task list and its one-way status rule live in `.temper/plans/*.json` and are enforced by `hooks/evidence_gate.py`.
- "Test for real" is enforced by routing every verification through `hooks/capture.py`, which records a signed receipt; status can't flip to passing without one.
- Baseline-before-build, one-task-per-session, and the review gate live in the `temper` skill (`skills/temper/SKILL.md`), driven by `/tp-impl`.
- Per-project verify commands are config-driven (a `## Temper` toml block in `CLAUDE.md`) — the engine never hardcodes `pytest` or `terraform`.
