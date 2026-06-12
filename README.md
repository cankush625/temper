# claude-harness — anti-bluffing edition

A minimal Claude harness whose organizing purpose is to **stop the agent from bluffing**:
claiming work is done when it isn't. "Done" is made to mechanically require evidence.

> A claim is a lie until there is a receipt. → [`docs/anti-bluffing.md`](docs/anti-bluffing.md)

## How it works
1. Every task lives in an append-only JSON list (`.harness/plans/<slug>.json`) and starts `failing`.
2. To make a task `passing`, you must produce a **receipt** with `hooks/capture.py`, which runs
   the real verify command and records its true exit code, signed and pinned to the current code state.
3. `hooks/evidence_gate.py` (PreToolUse) blocks any plan edit that flips a task to passing without a
   valid current receipt, or that breaks append-only.
4. `hooks/session_integrity.py` (Stop) blocks ending the session while any passing task lacks evidence.
5. A separate `review` skill applies the thermo-nuclear rubric to the diff — you don't grade your own work.

## Layout
```
docs/   best-practices.md · anti-bluffing.md · review-rubric.md · research/
skills/ harness/ (the session protocol) · review/ (thermo-nuclear)
hooks/  capture.py · evidence_gate.py · session_integrity.py
lib/    evidence.py · plan_schema.py · config.py
templates/ config.forge.toml · config.python-make.toml
```

## Use in a project
1. Copy `templates/config.<kind>.toml` to `<project>/.harness/config.toml`; set its `[commands]`.
2. Create `<project>/.harness/plans/<slug>.json` (start every task `failing`) and `progress.md`.
3. Wire hooks in `<project>/.claude/settings.json` pointing at this repo's `hooks/` by absolute path
   (see the forge wiring for an example). Don't clobber an existing `settings.local.json`.
4. Install the `harness` + `review` skills (symlink or copy `skills/*` into the project's
   `.claude/skills/`, or `~/.claude/skills/`).
5. Run `/harness` and work one task per session.

Pilot: **forge** (Terraform IaC). Verify is credential-free (`just validate dev`, `pre-commit`);
`just plan dev` (needs AWS SSO) is an opt-in escalation, not a default gate.

## Requirements
Python 3.11+ (uses `tomllib`), `git`. Per-project tools (terraform/just/make/pre-commit) come from
that project. Built for Opus 4.x — strip scaffolding as models improve (`best-practices.md` §8).
