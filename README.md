# Temper

**An anti-bluffing harness for Claude Code.** Temper's one job is to stop the agent from
*bluffing* — claiming work is done when it isn't, inventing APIs, or grading its own
homework. It does this by making "done" **mechanically require evidence**: a task cannot be
marked complete until a real command has been run and its passing result captured as a
signed receipt.

> **A claim is a lie until there is a receipt.**

The name fits the doctrine: *tempering* proves and hardens steel under controlled trial.
Tempered work is proven, not asserted.

- Full doctrine & threat model → [`docs/anti-bluffing.md`](docs/anti-bluffing.md)
- Design principles (synthesis of 4 sources) → [`docs/best-practices.md`](docs/best-practices.md)
- Review rubric (thermo-nuclear) → [`docs/review-rubric.md`](docs/review-rubric.md)

---

## Why

Long-running coding agents reliably (a) overrate their own work and (b) declare victory as
the context window fills. Asking the model to "be more careful" doesn't fix this. Temper
removes the cheapest, most common lie — "it works" with nothing behind it — so that human
and reviewer attention goes to the claims that are genuinely hard to check.

Temper is the *verification spine*. It composes with workflow harnesses (e.g. the
[build-rite](https://github.com/abhishekvm/build-rite) command set) rather than replacing
them — it supplies the hard evidence gates those tools lack.

---

## Quickstart

```bash
# Bootstrap a repo (links commands+skills, wires hooks, scaffolds .temper/, adds a CLAUDE.md block)
bin/temper init /path/to/your/project        # or, from inside the repo: temper init

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
| `/tp-init` | Detect this repo's verify commands → write the `## Temper` block in `CLAUDE.md`. |
| `/tp-plan` | Turn a ticket/spec into `.temper/plans/<slug>.json`; every task starts `failing`. |
| `/tp-impl` | Work **one** task: baseline → implement → **capture receipt** → review → commit → PR. |
| `/tp-review` | Thermo-nuclear structural review of the diff (single, fresh-context evaluator). |
| `/tp-swarm` | Parallel multi-agent review for large / high-risk diffs. |
| `/tp-cleanup` | Post-merge tidy: verify, delete branch, update tracker, log it. |

---

## The session workflow (`/tp-impl`)

One task per session, in order — defined in [`skills/temper/SKILL.md`](skills/temper/SKILL.md):

1. **Orient** — read `.temper/progress.md`, the plan, `git log -5`, and the `## Temper` block.
2. **Verify baseline** — run the configured baseline *through* `capture.py`. Never build on red.
3. **Select ONE task** — the highest-priority `failing` task.
4. **Implement** — full implementation, no stubs.
5. **Verify for real** — re-run the verify commands through `capture.py`; only an exit-0 receipt counts.
6. **Skeptical review** — `/tp-review` (or `/tp-swarm`) in a fresh context; you don't grade yourself.
7. **Update state** — mark the task `passing` (the gate allows it only with a valid receipt), log progress, commit.
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
    {"id": "T1", "title": "…", "acceptance": ["just validate dev exits 0"],
     "status": "failing", "evidence": []}
  ]
}
```

### Evidence receipts
Produced **only** by `hooks/capture.py`:

```bash
python3 hooks/capture.py --task T1 --claim "validate passes" -- just validate dev
```

It runs the real command, streams its output, and writes a signed record to
`.temper/evidence/T1/<ts>.json` containing: the command, true `exit_code`, stdout/stderr tails,
timestamps, and the **code state** it was run against (git sha + a digest of the working-tree
diff, excluding `.temper/`). `capture.py` exits with the command's own code — you cannot type
your way to green.

**Freshness is the strong guarantee:** a receipt only counts if its code-state digest matches
the current tree. Change the code after capturing, and the receipt is stale — re-verify.

### The three gates

| Layer | Mechanism | Catches |
|---|---|---|
| `capture.py` | runs commands, writes **signed**, state-pinned receipts, exits with the real code | faking a pass; "I ran it" with no proof |
| `evidence_gate.py` (PreToolUse) | blocks any plan edit that flips a task to `passing` without a valid current receipt, or breaks append-only | bluffing the task list mid-session |
| `session_integrity.py` (Stop) | re-audits all plans on session end; blocks stopping if any `passing` task lacks evidence | the end-of-session "I'm done!" bluff |

Both hooks **fail open** on internal error (a bug must never brick the session); the two
layers overlap so a single fail-open gap is still caught by the other.

### Config from CLAUDE.md
Verify commands live in a fenced ```toml block under `## Temper` in each project's `CLAUDE.md`
— one human-readable source, no separate config file to drift (`lib/claude_md.py`):

```markdown
## Temper

```toml
[project]
name = "forge"
kind = "terraform"

[commands]
baseline = ["just fmt", "just validate dev", "pre-commit run --all-files"]
verify   = ["just validate dev", "pre-commit run --all-files"]
review   = "thermo-nuclear"
```
```

`/tp-init` (via `lib/detect.py`) auto-detects this by scanning for `Makefile` / `justfile` /
`samconfig.toml` / package managers and proposing the block. Temper never hardcodes `pytest`
or `terraform`.

### Review (separate judgment)
`/tp-review` applies the thermo-nuclear rubric (structural simplification, the ~1000-line
smell, presumptive approval blockers) in a context separate from the author, and writes a
verdict to `.temper/eval_feedback/<task>.json`. `/tp-swarm` parallelizes it across diff slices
for large/high-risk changes. `verdict: "block"` is the same bar as a failing receipt.

---

## Repository layout
```
docs/      best-practices.md · anti-bluffing.md · review-rubric.md · research/
commands/  tp-init · tp-plan · tp-impl · tp-review · tp-swarm · tp-cleanup   (slash commands)
skills/    temper/ (session protocol) · review/ (thermo-nuclear)
hooks/     capture.py · evidence_gate.py · session_integrity.py
lib/       evidence.py · plan_schema.py · config.py · claude_md.py · detect.py
bin/temper local bootstrap CLI (temper init)
templates/ config.forge.toml · config.python-make.toml · config.sam.toml
```

---

## Bootstrap (what `temper init <project>` does)
Idempotent, and conservative about a project's own files:

- Symlinks `tp-*` commands and the `temper`/`review` skills into `<project>/.claude/`.
- Merges the two hooks into `<project>/.claude/settings.json` by absolute path — **never**
  touches `settings.local.json`, and won't duplicate hooks on re-run.
- Scaffolds `<project>/.temper/` (`plans/`, `progress.md`, `.gitignore` for the signing key).
- Ensures a `## Temper` block exists in `CLAUDE.md` (runs detection if absent).
- Excludes `.temper/` from git locally (`.git/info/exclude`) so it won't pollute the repo
  until the team chooses to adopt it.

`temper init <project> --dry-run` runs detection only and prints the block — no wiring.
(A remote updater for the engine itself — build-rite-style — would be a separate `temper sync`,
not part of `init`; it's deferred.)

---

## Project compatibility

Temper is config-driven, so it spans very different repos. Verified detections:

| Project | Kind | Credential-free verify |
|---|---|---|
| forge | terraform | `just fmt`, `just validate dev`, `pre-commit` (`just plan` = AWS-escalation) |
| forge-sam | sam | `compileall src`, `sam validate --lint` (deploy/plan = AWS-escalation) |
| crystal-backend | python | `make check`, `make run-unittests`, `make run-checkmigrations` |
| diq-backend | python | `make lint`, `make run-unittests`, `make run-apitests`, `make run-checkmigrations` |
| nexus | python | `make check` (ruff + format + pyright) |

---

## Honest threat model
The HMAC signature on receipts is **tamper-evidence, not cryptographic security** against an
agent that deliberately reads `.temper/.capture_key` and forges a record. Its purpose is to
turn "lazily declare done" (common) into "deliberately forge a signed, state-pinned receipt"
(rare and plainly adversarial). The freshness pin is the stronger guarantee. Temper also does
not judge whether your verify *command* is meaningful — `capture.py -- true` yields a real but
worthless receipt; choosing acceptance commands that actually exercise the task is on you (and
the review gate).

---

## Relationship to build-rite & roadmap
Temper adopts five ideas from the architect's [build-rite](https://github.com/abhishekvm/build-rite)
harness — the `/tp-impl` verify step, a local bootstrap CLI, config-in-CLAUDE.md, `/tp-review` +
`/tp-swarm`, and `/tp-init` detection — while keeping its own evidence spine as the enforcement
build-rite lacks.

**Deferred (start simple, add when needed):** a remote engine updater (`temper sync` +
`.tp-pin`, build-rite-style), a separate evaluator *process*, and a headless
multi-session runner. Built for Opus 4.x — strip scaffolding as models improve
(`best-practices.md` §8).

## Provenance
Principles synthesized from Anthropic's two "long-running agents" articles, OpenAI's "Harness
Engineering", and Geoffrey Huntley's "Ralph Wiggum"; review rubric from cursor's
`thermo-nuclear-code-quality-review`; file skeleton inspired by `celesteanders/harness`. See
[`docs/research/sources.md`](docs/research/sources.md).
