# The Anti-Bluffing Doctrine

> A claim is a lie until there is a receipt.

This harness exists to stop the failure mode where the agent *says* work is done —
"tests pass", "the build is green", "I implemented X" — when it isn't. The fix is
not better intentions; it's making "done" **mechanically require evidence**.

## The three rules

1. **Done requires a receipt.** A task may only be marked `passing` when there is a
   real, captured command result (exit 0) proving it. Receipts are produced *only*
   by `hooks/capture.py`, which runs the actual command and records its true exit
   code. The agent cannot type its way to green.

2. **The receipt must be current — until the work is committed.** Every receipt
   pins the project's code state (git sha + a digest of the working-tree diff,
   excluding `.temper/`). While the work is *uncommitted*, a passing claim is a
   live assertion about the current tree: if the code changes after capture, the
   receipt is **stale** and no longer counts — re-verify. This prevents "it passed
   an hour and three edits ago". Once the work is **committed**, a post-commit hook
   *seals* the task to that commit (`"sealed": {"commit": "<sha>"}`): the claim
   becomes a historical receipt, and the standing audit confirms the commit still
   exists rather than re-validating it against the current tree. The seal is
   **signed** with the repo key over `(task_id, commit)` — like a receipt, dodging
   freshness by hand means forging a signed seal, not just writing a plausible sha.
   Without this, a
   task proven and shipped on one branch reads as "unbacked" the moment you check
   out a sibling branch that doesn't carry its diff — Temper shares one local
   ledger across all branches, so "settled" must be decided by commit, not branch.

3. **The contract is append-only.** The task list never loses or reorders tasks,
   and a task never silently reverts `passing → failing`. You can't make red look
   green by editing the contract.

## How it's enforced (not just asked for)

| Layer | Mechanism | Catches |
|---|---|---|
| `hooks/capture.py` | runs commands, writes **signed** receipts, exits with the command's real code | faking a pass; "I ran it" with no proof |
| `hooks/evidence_gate.py` (PreToolUse) | blocks any plan edit that flips a task to `passing` without a valid current receipt, or that breaks append-only | bluffing the task list mid-session |
| `hooks/session_integrity.py` (Stop) | re-audits all plans on session end; blocks stopping if any *unsealed* `passing` task lacks current evidence | the end-of-turn "I'm done!" bluff |
| `hooks/seal.py` (post-commit) | seals each passing task to the commit that ships it, so a shipped claim isn't re-litigated on other branches | "proven elsewhere" misread as unbacked |
| separate review (`review-rubric.md`) | a fresh-context skeptical pass over the diff | self-graded quality |

## Threat model (stated honestly)

The HMAC signature on receipts is **tamper-evidence, not cryptographic security**
against an agent that deliberately reads `.temper/.capture_key` and forges a
record. Its job is to turn "lazily declare done" (common) into "deliberately forge
a signed, state-pinned receipt" (rare and obviously adversarial). The freshness
pin (rule 2) is the stronger guarantee: even a hand-written receipt must match the
exact current code state, which is hard to fake by accident.

The hooks **fail open** on internal error — a bug in a gate must never brick the
session. The layers overlap (PreToolUse + Stop) so a single fail-open gap is still
caught by the other.

## What this is NOT

- It does not judge whether your verify *command* is meaningful — `capture.py -- true`
  yields a real but worthless receipt. Choose acceptance commands that actually test
  the task (that's what `acceptance` in the plan and the review gate are for).
- It does not replace human judgment; it removes the cheapest, most common lie so
  human and evaluator attention goes to the claims that are genuinely hard to check.
