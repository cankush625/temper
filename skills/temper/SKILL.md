---
name: temper
description: Run one anti-bluffing work session — orient, verify a green baseline, do ONE task, prove it with a captured receipt, get a skeptical review, then commit. Backs the /tp-impl command. Use in a repo wired with Temper (.temper/ present).
---

# Temper — one anti-bluffing session

Read [`docs/anti-bluffing.md`](../../docs/anti-bluffing.md) once. The rule: **a claim is a
lie until there is a receipt.** You may not mark a task `passing` without a real, current,
exit-0 receipt produced by `capture.py`. Hooks enforce this; don't fight them. "Tempered"
work is proven under trial, not asserted.

`TEMPER` below = the Temper repo root (the dir containing `hooks/capture.py`):
`/Users/ankushchavan/Documents/GyaanAI/temper`.

Verify commands come from the **`## Temper` toml block in this project's CLAUDE.md**
(not a separate config file). If it's missing, run `/tp-init` first.

## Protocol — in order, one task only

### 1. Orient
- Read `.temper/progress.md`, the active `.temper/plans/<slug>.json`, and `git log -5`.
- Read `CLAUDE.md`, including its `## Temper` block (the `[commands]` you'll run).

### 2. Verify baseline (never build on red)
Run each `[commands].baseline` entry **through capture**, against a baseline task id:
```
python3 TEMPER/hooks/capture.py --task BASELINE --kind baseline -- <baseline command>
```
If a baseline command fails, this session is about getting back to green (or stop and
report) — do not start new work on a red tree.

### 3. Select ONE task
Highest-priority `failing` task in the plan. One per session. If none, stop and say so.

### 4. Implement
Full implementation, no stubs/placeholders. Found an unrelated bug? Append it to the plan
as a new `failing` task; don't silently fix-and-forget.

### 5. Verify for real — earn the receipt
Run each `[commands].verify` entry through capture, tagged with the task id:
```
python3 TEMPER/hooks/capture.py --task <ID> --claim "what this proves" -- <verify command>
```
- Non-zero exit ⇒ not done. Fix and re-capture. Do not touch the plan.
- Use acceptance commands that actually exercise the task. `-- true` is a worthless receipt.
- If the code changes after a receipt, that receipt is stale — re-capture.

### 6. Skeptical review (separate judgment)
Run `/tp-review` (or `/tp-swarm` for high-risk diffs) — a fresh-context evaluator, because
you are the author and don't grade yourself. Apply any `block` findings. Writes
`.temper/eval_feedback/<ID>.json`.

### 7. Update state
- Edit the plan: set the task `status: "passing"` and add the receipt path(s) to `evidence`.
  The `evidence_gate` hook allows this only because step 5 produced a valid current receipt.
  If it blocks you, you skipped or invalidated the receipt — go back.
- Append a dated entry to `.temper/progress.md`: what you did, what you verified, bugs, next.
- Commit with a descriptive message referencing the task id. (No Claude attribution line.)

### 8. Clean exit
Ending the session triggers `session_integrity` (Stop hook). If it blocks you, a task is
marked passing without current evidence — re-capture or revert it to `failing`. Don't bypass
the hook; it is the point.

## Hard rules
- Append-only plan: never delete or reorder tasks.
- Never revert `passing → failing` to dodge a check, except to honestly retract a premature claim.
- Never hand-author an evidence file. Receipts come only from `capture.py`.
