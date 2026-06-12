---
description: Implement ONE task with Temper's anti-bluffing protocol (baseline → one task → captured-receipt verify → review → commit → PR).
argument-hint: "[task-id or plan slug]"
---
Run a single Temper work session for: $ARGUMENTS

Load the `temper` skill (`.claude/skills/temper/SKILL.md`) and follow its 8-step protocol
exactly — do not improvise around it.

Non-negotiables:
- Verify commands come from the `## Temper` toml block in CLAUDE.md. If absent, run `/tp-init` first.
- A task may only become `passing` after `capture.py` returns a real **exit-0** receipt on the
  CURRENT code. The evidence_gate (pre-edit) and session_integrity (stop) hooks enforce this — if
  one blocks you, fix the work or re-capture; never try to bypass it.
- Step 6 is a separate review: run `/tp-review`, or `/tp-swarm` for a large/high-risk diff.
- One task per session. Commit messages must not include any Claude attribution line.
