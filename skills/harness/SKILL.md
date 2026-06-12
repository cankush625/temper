---
name: harness
description: Run one anti-bluffing work session — orient, verify a green baseline, do ONE task, prove it with a captured receipt, get a skeptical review, then commit. Use when working a task in a repo wired with the anti-bluffing harness (.harness/ present).
---

# /harness — one anti-bluffing session

Read [`docs/anti-bluffing.md`](../../docs/anti-bluffing.md) once. The rule: **a claim
is a lie until there is a receipt.** You may not mark a task `passing` without a real,
current, exit-0 receipt produced by `capture.py`. Hooks enforce this; don't fight them.

`HARNESS` below = the harness repo root (the dir containing `hooks/capture.py`). In
forge it is `/Users/ankushchavan/Documents/GyaanAI/claude-harness`.

## Protocol — do these in order, one task only

### 1. Orient
- Read `.harness/progress.md`, the active `.harness/plans/<slug>.json`, and `git log -5`.
- Read the repo's `CLAUDE.md`. Load `.harness/config.toml` to learn the verify commands.

### 2. Verify baseline (never build on red)
Run each `[commands].baseline` entry **through capture**, against a baseline task id:
```
python3 HARNESS/hooks/capture.py --task BASELINE --kind baseline -- <baseline command>
```
If any baseline command fails, your job this session is to get back to green (or stop
and report) — do not start new work on a red tree.

### 3. Select ONE task
Pick the highest-priority `failing` task. One per session. If none, stop and say so.

### 4. Implement
Write the change. No placeholders or stubs — full implementations only. If you find an
unrelated bug, append it to the plan as a new `failing` task; don't silently fix-and-forget.

### 5. Verify for real — earn the receipt
Run each `[commands].verify` entry through capture, tagged with the task id:
```
python3 HARNESS/hooks/capture.py --task <ID> --claim "what this proves" -- <verify command>
```
- If it exits non-zero, the task is **not** done. Fix and re-capture. Do not touch the plan.
- Pick acceptance commands that actually exercise the task. `-- true` is a worthless receipt.
- If the code changes after a receipt, that receipt is stale — re-capture.

### 6. Skeptical review (separate judgment)
Invoke the `review` skill on your diff in a fresh-context subagent (you are the author;
you don't get to grade yourself). Apply any `block` findings before proceeding. The
review writes `.harness/eval_feedback/<ID>.json`.

### 7. Update state
- Edit the plan to set the task `status: "passing"` and add the receipt path(s) to its
  `evidence` list. The `evidence_gate` hook will allow this only because step 5 produced a
  valid current receipt. If it blocks you, you skipped or invalidated the receipt — go back.
- Append a dated entry to `.harness/progress.md`: what you did, what you verified, bugs
  found, next priority.
- Commit with a descriptive message referencing the task id.

### 8. Clean exit
Ending the session triggers `session_integrity` (Stop hook). If it blocks you, a task is
marked passing without current evidence — fix it (re-capture) or revert it to `failing`.
Do not try to bypass the hook; it is the point.

## Hard rules
- Never delete or reorder tasks in the plan (append-only).
- Never revert a task `passing → failing` to dodge a check, except to honestly retract a
  premature claim.
- Never hand-author an evidence file. Receipts come only from `capture.py`.
