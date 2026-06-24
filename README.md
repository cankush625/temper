# Temper

**An anti-bluffing harness for Claude Code.** Temper's one job is to stop the agent from
*bluffing* — claiming work is done when it isn't, inventing APIs, or grading its own
homework. It does this by making "done" **mechanically require evidence**: a task cannot be
marked complete until a real command has been run and its passing result captured as a
signed receipt — **and** a fresh-context review has signed off on the same code.

> **A claim is a lie until there is a receipt.**

The name fits the doctrine: *tempering* proves and hardens steel under controlled trial.
Tempered work is proven, not asserted.

- Operating safety rails (prod is read-only, etc.) → [`docs/safety.md`](docs/safety.md)
- Commit message format (Conventional Commits, `-s` sign-off) → [`docs/commit-style.md`](docs/commit-style.md)
- Full doctrine & threat model → [`docs/anti-bluffing.md`](docs/anti-bluffing.md)
- Design principles (synthesis of 4 sources) → [`docs/best-practices.md`](docs/best-practices.md)
- Review rubric (thermo-nuclear) → [`docs/review-rubric.md`](docs/review-rubric.md)

---

## Why

Long-running coding agents reliably (a) overrate their own work and (b) declare victory as
the context window fills. Asking the model to "be more careful" doesn't fix this. Temper
removes the cheapest, most common lie — "it works" with nothing behind it — so that human
and reviewer attention goes to the claims that are genuinely hard to check.

Temper is the *verification spine*. It composes with workflow / command harnesses rather
than replacing them — it supplies the hard evidence gates that instruction-level tooling
lacks.

---

## Quickstart

```bash
# One-time: put `temper` on your PATH (any dir on $PATH works; ~/.local/bin is a good default)
ln -sf "$PWD/bin/temper" ~/.local/bin/temper

# Bootstrap a repo (links commands+skills, wires hooks, scaffolds .temper/, adds a CLAUDE.local.md block)
cd /path/to/your/project && temper init       # defaults to the current dir; --dry-run to preview

# In Claude Code, inside that project:
/tp-init      # detect & confirm this repo's verify commands
/tp-plan      # break a ticket into an append-only JSON task list
/tp-impl      # implement ONE task, prove it, review it, commit it
```

Requirements: Python 3.11+ (`tomllib`) and `git`. Per-project tooling
(terraform / just / make / sam / pre-commit) comes from the project itself.

---

## Commands

Claude Code slash commands, prefix `tp` (thin wrappers that delegate to richer skills):

| Command | What it does |
|---|---|
| `/tp-init` | Detect this repo's verify commands → write the `## Temper` block in `CLAUDE.local.md` (never the shared `CLAUDE.md`). |
| `/tp-plan` | Turn a ticket/spec into `.temper/plans/<slug>.json`; every task starts `failing`. |
| `/tp-impl` | Work **one** task: baseline → implement → **capture receipt** → review (signs a verdict receipt) → commit → PR. |
| `/tp-review` | Full-rubric review of the diff (single, fresh-context evaluator); records a signed verdict receipt. |
| `/tp-swarm` | Parallel multi-agent review (security/correctness/performance/style lanes) for large / high-risk diffs. |
| `/tp-cleanup` | Post-merge tidy: verify, delete branch, update tracker, log it. |

---

## The session workflow (`/tp-impl`)

One task per session, in order — defined in [`skills/temper/SKILL.md`](skills/temper/SKILL.md):

1. **Orient** — read `.temper/progress.md`, the plan, `git log -5`, and the `## Temper` block.
2. **Verify baseline** — run the configured baseline *through* `capture.py`. Never build on red.
3. **Select ONE task** — the highest-priority `failing` task.
4. **Implement** — full implementation, no stubs.
5. **Verify for real** — re-run the verify commands through `capture.py`; only an exit-0 receipt counts.
6. **Skeptical review** — `/tp-review` (or `/tp-swarm`) in a fresh context; you don't grade yourself. It signs a verdict receipt.
7. **Update state** — mark the task `passing` (the gate allows it only with both a command and a review receipt), log progress, commit.
8. **Clean exit** — the Stop hook re-audits the ledger before the session can end.

---

## Core concepts

### The task list (the contract)
`.temper/plans/<slug>.json` — an **append-only** list. Tasks may only move `failing → passing`,
never the reverse; nothing is deleted or reordered. This is what stops the agent from quietly
editing the contract to make red look green. Schema (`lib/plan_schema.py`):

```json
{
  "slug": "demo",
  "tasks": [
    {"id": "T1", "title": "…", "acceptance": ["make test passes"],
     "status": "failing", "evidence": []}
  ]
}
```

### Two kinds of receipt
A task needs **both** to be marked `passing` — and both must be fresh for the current tree:

**Command receipt** — produced **only** by `temper capture` (over `hooks/capture.py`):
```bash
temper capture --task T1 --claim "tests pass" -- make test
```
It runs the real command, streams its output, and writes a signed record to
`.temper/evidence/T1/<ts>.json` containing: the command, true `exit_code`, stdout/stderr tails,
timestamps, and the **code state** it ran against (git sha + a digest of the working-tree diff,
excluding `.temper/`). `capture.py` exits with the command's own code — you cannot type your way
to green.

**Review receipt** — produced **only** by `temper review-capture` (over `hooks/review_capture.py`):
```bash
temper review-capture --in verdict.json     # verdict from /tp-review, pinned to this tree
```
It signs a fresh-context review verdict (pass/block) into the same evidence stream, pinned to the
same code state. This turns the review from advice into a gate: a `pass` verdict is proof about
*this* exact tree, and goes stale the moment the code changes — so a passing review can't be
recycled across edits.

**Freshness is the strong guarantee:** a receipt only counts if its code-state digest matches the
current tree. Change the code after capturing or reviewing, and that receipt is stale — re-verify
/ re-review.

### The gates

| Layer | Mechanism | Catches |
|---|---|---|
| `capture.py` | runs commands, writes **signed**, state-pinned command receipts, exits with the real code | faking a pass; "I ran it" with no proof |
| `review_capture.py` | signs a fresh-context review verdict into a state-pinned review receipt (exit 0 pass / 1 block) | "I reviewed it" with no proof; recycling a stale approval |
| `evidence_gate.py` (PreToolUse) | blocks any plan edit that flips a task to `passing` without **both** a current command receipt **and** a current (independent) review receipt, that removes tests on net, or that breaks append-only | bluffing the task list mid-session |
| `session_integrity.py` (Stop) | re-audits all plans on session end; blocks stopping if any `passing` task lacks either receipt or its diff deleted tests | the end-of-session "I'm done!" bluff |

The review-receipt requirement, reviewer-independence (two-key), and test-deletion guard are
each toggleable per project under `[gate]` in the `## Temper` block (all default on). A
legitimate test removal is opted in per task with `"allow_test_removal": true`.

Both hooks **fail open** on internal error (a bug must never brick the session); the two
layers overlap so a single fail-open gap is still caught by the other.

### Config from CLAUDE.local.md
Verify commands live in a fenced ```toml block under `## Temper`. `temper init` / `/tp-init`
always write it to the project's **`CLAUDE.local.md`** (personal, uncommitted) and never touch
the shared `CLAUDE.md` — so your setup doesn't land on teammates. Temper still *reads*
`CLAUDE.local.md` first, then `CLAUDE.md`, so a team that wants to adopt it can commit a block in
`CLAUDE.md` deliberately. One human-readable source, no separate config file to drift
(`lib/claude_md.py`):

```markdown
## Temper

```toml
[project]
name = "my-service"
kind = "python"

[commands]
baseline = ["make check"]
verify   = ["make check", "make test"]
review   = "thermo-nuclear"

[gate]
require_review      = true   # a passing task needs a review receipt too; false = command receipt only
independent_review  = true   # the review's reviewer must differ from the author (two-key)
guard_test_deletion = true   # block a passing task whose diff removes tests on net
```
```

`/tp-init` (via `lib/detect.py`) auto-detects this by scanning for `Makefile` / `justfile` /
`samconfig.toml` / package managers and proposing the block. Temper never hardcodes `pytest`
or `terraform`. Every `[gate]` key defaults to `true` even if the block omits it.

### Review (separate, enforced judgment)
`/tp-review` applies the [review rubric](docs/review-rubric.md) — the thermo-nuclear structural
core **plus** a superset of the concerns an instruction-level review raises (correctness,
security + secret scan, migration safety, performance, conventions, test meaningfulness, intent
& coverage, pattern conformance, API docs) — in a context separate from the author. It records a
**signed verdict receipt** via `review-capture` (mirrored to `.temper/eval_feedback/<task>.json`
for humans). `/tp-swarm` fans it out across parallel security/correctness/performance/style
lanes for large/high-risk changes. `verdict: "block"` is the same bar as a failing receipt; a
`pass` is required — and enforced by the gate — before a task can be marked passing.

---

## Repository layout
```
docs/      best-practices.md · anti-bluffing.md · review-rubric.md · safety.md · commit-style.md · research/
commands/  tp-init · tp-plan · tp-impl · tp-review · tp-swarm · tp-cleanup   (slash commands)
skills/    temper/ (session protocol) · temper-review/ (thermo-nuclear)
hooks/     capture.py · review_capture.py · evidence_gate.py · session_integrity.py
lib/       evidence.py · plan_schema.py · config.py · claude_md.py · detect.py · test_evidence.py
bin/temper local bootstrap CLI (temper init)
templates/ config.terraform.toml · config.python.toml · config.sam.toml
scripts/   git-hooks/commit-msg  (strips any AI/bot attribution line from commits)
           git-hooks/post-commit (seals proven-and-committed task claims)
```

> Commit hygiene: this repo installs `scripts/git-hooks/commit-msg` at `.git/hooks/commit-msg`
> to strip any AI/assistant/bot attribution — `Co-Authored-By: …Claude/Anthropic/[bot]`,
> `Generated with …Claude`, `claude.com/claude-code`, or a `🤖` footer (a human co-author is
> kept). The no-attribution rule **overrides any harness/tool default** to add such a line, in
> commit messages *and* PR bodies (see [`docs/safety.md`](docs/safety.md)); the hook is only a
> backstop for commits. `temper init` wires it automatically; re-install after a fresh clone:
> `ln -sf ../../scripts/git-hooks/commit-msg .git/hooks/commit-msg`

---

## Bootstrap (what `temper init <project>` does)
Idempotent, and conservative about a project's own files:

- Symlinks `tp-*` commands and the `temper`/`temper-review` skills into `<project>/.claude/`
  (skill names are tool-namespaced so they don't shadow Claude Code's built-in `/review` etc.).
- Merges the two hooks into `<project>/.claude/settings.local.json` by absolute path — the
  personal, gitignored file (higher precedence than the shared `settings.json`), since the hook
  command is machine-specific. **Never** writes the shared `settings.json`; migrates hooks a
  prior init left there, and won't duplicate hooks on re-run.
- Scaffolds `<project>/.temper/` (`plans/`, `progress.md`, `.gitignore` for the signing key).
- Ensures a `## Temper` block exists in **`CLAUDE.local.md`** (personal, uncommitted) — never
  the shared `CLAUDE.md`. Runs detection to seed it if absent.
- Excludes `.temper/` **and `CLAUDE.local.md`** from git locally (`.git/info/exclude`) so neither
  pollutes the repo until the team chooses to adopt it.

`temper init <project> --dry-run` runs detection only and prints the block — no wiring.
(A remote updater for the engine itself — rustup/nvm-style — would be a separate `temper sync`,
not part of `init`; it's deferred.)

---

## Supported project kinds

Temper is config-driven, so it spans very different repos. `/tp-init` detects a kind and
proposes commands; you confirm/edit them into the `## Temper` block.

| Kind | Detected from | Example credential-free verify |
|---|---|---|
| `terraform` | `*.tf` + `justfile`/`Makefile` | `terraform fmt -check`, `terraform validate` (live `plan`/`apply` = escalation) |
| `sam` | `template.yaml` / `samconfig.toml` | `compileall src`, `sam validate --lint` (deploy = escalation) |
| `python` | `Makefile` / `pyproject.toml` / `requirements.txt` | `make check`, `make test`, `pytest` |
| `make` | `Makefile` (non-Python) | `make check`, `make test` |

Detection only recognizes common, non-org-specific target names — anything bespoke you add
by hand in the block.

---

## Honest threat model
The HMAC signature on receipts is **tamper-evidence, not cryptographic security** against an
agent that deliberately reads `.temper/.capture_key` and forges a record. Its purpose is to
turn "lazily declare done" (common) into "deliberately forge a signed, state-pinned receipt"
(rare and plainly adversarial). The freshness pin is the stronger guarantee. Temper also does
not judge whether your verify *command* is meaningful — `capture.py -- true` yields a real but
worthless receipt; choosing acceptance commands that actually exercise the task is on you (and
the review gate). Reviewer **independence** is enforced only by name — a single agent can't be
*proven* to have reviewed in a fresh context, so the two-key rule raises self-approval friction
(and is strongest when `/tp-review` actually runs as a separate subagent) rather than making it
impossible. The test-deletion guard is a high-precision heuristic, not full coverage analysis.

---

## Roadmap
Temper pairs a workflow surface (the `/tp-impl` verify step, a local bootstrap CLI,
config-in-CLAUDE.md, `/tp-review` + `/tp-swarm`, and `/tp-init` detection) with its evidence
spine — the enforcement that instruction-level harnesses lack.

**Deferred (start simple, add when needed):** a remote engine updater (`temper sync` +
`.tp-pin`), a separate evaluator *process*, and a headless multi-session runner. Built for
Opus 4.x — strip scaffolding as models improve (`best-practices.md` §8).

## Provenance
Principles synthesized from Anthropic's two "long-running agents" articles, OpenAI's "Harness
Engineering", and Geoffrey Huntley's "Ralph Wiggum"; review rubric from cursor's
`thermo-nuclear-code-quality-review`; file skeleton inspired by `celesteanders/harness`. See
[`docs/research/sources.md`](docs/research/sources.md).
