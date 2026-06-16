---
description: Implement ONE task with Temper's anti-bluffing protocol (baseline → one task → captured-receipt verify → review → commit → PR).
argument-hint: "[task-id or plan slug]"
---
Run a single Temper work session for: $ARGUMENTS

Load the `temper` skill (`.claude/skills/temper/SKILL.md`) and follow its 8-step protocol
exactly — do not improvise around it.

Non-negotiables:
- Verify commands come from the `## Temper` toml block in CLAUDE.md. If absent, run `/tp-init` first.
- A task may only become `passing` when it holds TWO fresh receipts on the CURRENT code: a green
  **command receipt** from `capture.py` (step 5) AND a verdict=pass **review receipt** from
  `/tp-review` (step 6). The evidence_gate (pre-edit) and session_integrity (stop) hooks enforce
  both — if one blocks you, fix the work or re-capture/re-review; never try to bypass it.
- Step 6 is a separate review that records a signed verdict: run `/tp-review`, or `/tp-swarm` for a
  large/high-risk diff. A `block` verdict must be resolved and re-reviewed.
- One task per session. Commits are a HARD RULE (`docs/commit-style.md`): Conventional Commits
  subject `type(area): message`, signed off with `-s` (`git commit -s -m "..."`), scoped to the
  staged diff, with no attribution/identity line.
